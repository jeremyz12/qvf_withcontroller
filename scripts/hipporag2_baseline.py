# -*- coding: utf-8 -*-
"""scripts/hipporag2_baseline.py — 批 33-H1 考生:HippoRAG 2(ICML 2025,
OSU-NLP-Group/HippoRAG, MIT 许可)× WikiState 60 题标定场。

协议完全镜像 scripts/repro_batch4.py(txtai / lgstore / bm25 / cognee /
graphiti / lightrag 同一 harness):
  * 同 15 库抽样(repro_batch2.sample_stores)、同 60 题、同 sess_text 段落化
    (日期逐字前缀 "(session date: YYYY-MM-DD)")、按日期升序逐条摄入;
  * 每题 retrieve top-10 → 同 READER_SYS / claude-haiku-4-5 / max_tokens=300 /
    temperature=0 读者 → qvf.judge.ClaudeJudge 冻结判官;
  * 记忆条目同样按 `- {text[:400]}` 截断(与全部 16 系统一致);
    --no-truncate 可跑不截断的稳健性对照。

HippoRAG 2 侧一律用官方 pip 包(hipporag==2.0.0a3)与 README 默认:
  llm_name=gpt-4o-mini(BaseConfig 出厂默认)、openie_mode=online、
  embedding_model_name=text-embedding-3-small(官方 OpenAIEmbeddingModel 分支;
  默认的 nvidia/NV-Embed-v2 为 7B 本地模型,本机 16GB 显存不保险,且用 OpenAI
  嵌入与本项目 direct 臂 / lgstore / sumrag 同款嵌入器,口径可比)。
  每条目一座全新的 save_dir(per-item fresh index),库间零共享。

本文件不重写 HippoRAG 任何算法:OpenIE、同义边、事实检索、recognition
memory 重排、PPR 全部走官方包代码。唯一环境垫片是把 POSIX-only 的 vllm
(import resource)在 sys.modules 里打桩——HippoRAG.py 顶层无条件 import 了
离线 OpenIE 路径,而我们跑的是 online 路径,不触碰 vllm 任何函数。

用法(须用隔离环境 .venv_hipporag):
  .venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py --limit-stores 1
  .venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

# --- vllm 垫片(见 docstring):必须在 import hipporag 之前 ------------------
_vllm_stub = types.ModuleType("vllm")
_vllm_stub.SamplingParams = object
_vllm_stub.LLM = object
sys.modules.setdefault("vllm", _vllm_stub)

# --- multiprocessing.Manager 垫片 ------------------------------------------
# hipporag/embedding_model/base.py 在模块级(类体里)执行 multiprocessing.
# Manager(),而 EmbeddingCache 这个类在整个包里没有任何引用点(grep 全包只有
# 定义处一行)——是死代码。在 Windows + Store Python 的 venv 里,这次 spawn 会
# 拉起一个不带本 venv site-packages 的解释器并挂死。故在 import 前把 Manager
# 换成同接口的本地假货;不触及任何被真正调用的代码路径。
import multiprocessing as _mp  # noqa: E402


class _LocalManager:
    def dict(self, *a, **k):
        return dict(*a, **k)

    def list(self, *a, **k):
        return list(*a, **k)


_mp_manager_orig = _mp.Manager
_mp.Manager = lambda *a, **k: _LocalManager()

import anthropic  # noqa: E402
import hipporag.information_extraction.openie_openai as _openie_mod  # noqa: E402
from hipporag import HippoRAG  # noqa: E402
from hipporag.utils.config_utils import BaseConfig  # noqa: E402

from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch2 import READER_MODEL, READER_SYS, VOLS, sample_stores  # noqa: E402

_mp.Manager = _mp_manager_orig  # 垫片只在 import 期间生效

# 并行上限 4:HippoRAG 内部 OpenIE 用 ThreadPoolExecutor() 默认 min(32,cpu+4)。
# 只压并发,不改任何抽取逻辑(逐段落独立,结果与线程数无关)。
_openie_mod.ThreadPoolExecutor = functools.partial(ThreadPoolExecutor, max_workers=4)

LLM_NAME = "gpt-4o-mini"
EMBED_NAME = "text-embedding-3-small"
TOP_K = 10

# 官方定价(2026-09,USD / 1M tokens),用于按实测 token 折算 $
PRICE = {
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
}


def sess_text(s):
    """与 repro_batch4.sess_text 逐字一致。"""
    turns = s.get("turns", [])[:6]
    return f"(session date: {s.get('date','undated')})\n" + \
        "\n".join(str(t)[:400] for t in turns)


class Counter:
    def __init__(self):
        self.lock = threading.Lock()
        self.d = {"llm_in": 0, "llm_out": 0, "llm_calls": 0, "llm_cache_hits": 0,
                  "emb_tok": 0, "emb_calls": 0}

    def add(self, **kw):
        with self.lock:
            for k, v in kw.items():
                self.d[k] += v

    def snap(self):
        with self.lock:
            return dict(self.d)

    def reset(self):
        with self.lock:
            for k in self.d:
                self.d[k] = 0


def instrument(hr: HippoRAG, c: Counter):
    """挂计数器到官方 infer / embeddings.create 上(只读,不改行为)。"""
    orig_infer = hr.llm_model.infer

    def infer(*a, **kw):
        out = orig_infer(*a, **kw)
        try:
            msg, meta, hit = out
            if hit:
                c.add(llm_cache_hits=1)
            else:
                c.add(llm_in=int(meta.get("prompt_tokens", 0)),
                      llm_out=int(meta.get("completion_tokens", 0)),
                      llm_calls=1)
        except Exception:  # noqa: BLE001
            pass
        return out

    hr.llm_model.infer = infer
    hr.rerank_filter.llm_infer_fn = infer  # DSPyFilter 在 __init__ 里绑定了旧引用

    emb_client = hr.embedding_model.client
    orig_create = emb_client.embeddings.create

    def create(**kw):
        r = orig_create(**kw)
        try:
            c.add(emb_tok=int(r.usage.prompt_tokens), emb_calls=1)
        except Exception:  # noqa: BLE001
            pass
        return r

    emb_client.embeddings.create = create


def build_config(save_dir: Path) -> BaseConfig:
    cfg = BaseConfig()
    cfg.save_dir = str(save_dir)
    cfg.llm_name = LLM_NAME
    cfg.embedding_model_name = EMBED_NAME
    cfg.openie_mode = "online"          # README 默认(离线需 vllm)
    cfg.retrieval_top_k = TOP_K
    cfg.force_index_from_scratch = True  # per-item fresh index
    cfg.force_openie_from_scratch = True
    cfg.save_openie = True
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-stores", type=int, default=0)
    ap.add_argument("--store-offset", type=int, default=0)
    ap.add_argument("--out-suffix", default="")
    ap.add_argument("--no-truncate", action="store_true",
                    help="记忆条目不做 400 字符截断(稳健性对照臂)")
    ap.add_argument("--store-root", default="results/hipporag_stores")
    ap.add_argument("--reuse-store", action="store_true",
                    help="复用既有 per-item 店,不重建索引(只换读者侧变量的对照臂)")
    ap.add_argument("--rerank-llm", default="",
                    help="只把 recognition-memory 重排(DSPyFilter)的 LLM 换掉,"
                         "索引仍是 gpt-4o-mini 建的;诊断臂,非 README 默认")
    a = ap.parse_args()

    out_p = ROOT / f"results/wsc_s5_hipporag2{a.out_suffix}.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}

    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    picked = picked[a.store_offset:]
    if a.limit_stores:
        picked = picked[:a.limit_stores]
    print(f"stores={len(picked)} questions={sum(len(by_uid[u]) for u in picked)}",
          flush=True)

    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    fh = open(out_p, "a", encoding="utf-8")
    store_root = ROOT / a.store_root

    for uid in picked:
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            continue
        sessions = sorted(entries[uid].get("sessions", []),
                          key=lambda s: s.get("date", ""))
        docs = [sess_text(s) for s in sessions]

        c = Counter()
        save_dir = store_root / uid
        cfg = build_config(save_dir)
        reuse = a.reuse_store and save_dir.exists()
        if reuse:
            cfg.force_index_from_scratch = False
            cfg.force_openie_from_scratch = False
        t0 = time.time()
        hr = HippoRAG(global_config=cfg)
        instrument(hr, c)
        if a.rerank_llm:
            hr.rerank_filter.model_name = a.rerank_llm
        if not reuse:
            hr.index(docs)
        ingest_s = time.time() - t0
        ing = c.snap()
        c.reset()
        try:
            ginfo = hr.get_graph_info()
        except Exception:  # noqa: BLE001
            ginfo = {}
        print(f"[{uid}] indexed {len(docs)} passages in {ingest_s:.0f}s; "
              f"openie tok {ing['llm_in']}/{ing['llm_out']} in {ing['llm_calls']} "
              f"calls; emb {ing['emb_tok']} tok; graph {ginfo}", flush=True)

        for q in qs:
            t1 = time.time()
            qc_before = c.snap()
            tr = time.time()
            try:
                sol = hr.retrieve(queries=[q["question"]], num_to_retrieve=TOP_K)[0]
                passages = list(sol.docs)
            except Exception as e:  # noqa: BLE001
                print(f"[{q['qid']}] retrieve fail: {type(e).__name__}: {e}",
                      flush=True)
                passages = []
            retrieve_s = time.time() - tr
            mems = [f"- {p if a.no_truncate else p[:400]}" for p in passages]
            memtext = "\n".join(mems) if mems else "(no memories retrieved)"

            ans, ti, to = "", 0, 0
            tread = time.time()
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=READER_MODEL, max_tokens=300, temperature=0.0,
                        system=READER_SYS,
                        messages=[{"role": "user", "content":
                                   f"MEMORIES:\n{memtext}\n\n"
                                   f"USER'S NEW MESSAGE: {q['question']}"}])
                    ans = "".join(b.text for b in r.content if b.type == "text")
                    ti, to = r.usage.input_tokens, r.usage.output_tokens
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"retry {attempt}: {type(e).__name__}", flush=True)
                    time.sleep(3)

            read_s = time.time() - tread
            v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
            qc_after = c.snap()
            q_llm_in = qc_after["llm_in"] - qc_before["llm_in"]
            q_llm_out = qc_after["llm_out"] - qc_before["llm_out"]
            q_emb = qc_after["emb_tok"] - qc_before["emb_tok"]

            fh.write(json.dumps({
                "question_id": q["qid"], "mode": "hipporag2", "uid": uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": ans,
                "memories_n": len(mems),
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
                "latency_s": round(time.time() - t1, 2),
                "retrieve_s": round(retrieve_s, 2),
                "read_s": round(read_s, 2),
                # HippoRAG 内部用量(gpt-4o-mini + text-embedding-3-small)
                "hr_ingest_llm_in": ing["llm_in"], "hr_ingest_llm_out": ing["llm_out"],
                "hr_ingest_llm_calls": ing["llm_calls"],
                "hr_ingest_emb_tok": ing["emb_tok"],
                "hr_query_llm_in": q_llm_in, "hr_query_llm_out": q_llm_out,
                "hr_query_emb_tok": q_emb,
                "n_passages": len(docs), "graph_info": ginfo,
                "hipporag_llm": LLM_NAME, "hipporag_embed": EMBED_NAME,
                "truncate_400": not a.no_truncate,
                "rerank_llm": a.rerank_llm or LLM_NAME,
            }, ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] answered {len(qs)}", flush=True)

    fh.close()
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / max(len(rows), 1) * 100
    print(f"\nhipporag2: {acc:.2f}% (n={len(rows)})")
    ju = getattr(judge, "total_usage", None)
    if ju:
        print("judge usage:", ju)
    return 0


if __name__ == "__main__":
    sys.exit(main())
