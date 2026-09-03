# -*- coding: utf-8 -*-
"""scripts/repro_batch33h_memos.py — 批 33-H4 对手系统 MemOS(MemTensor,Apache-2.0)
× WikiState 60 题标定场。

协议镜像 scripts/repro_batch2.py / repro_batch4.py:同 15 库 60 题抽样、同读者
(claude-haiku-4-5)、同判官(qvf.judge.ClaudeJudge)、k=10。

MemOS 侧(全部走其官方 API,不复刻任何机制):
  - 每条目一只全新 MemCube:GeneralMemCubeConfig(text_mem=general_text)
  - 写入:按会话时间序,cube.text_mem.extract(messages) → .add(memories)
    (extract 用 MemOS 自带 SIMPLE_STRUCT_MEM_READER_PROMPT + 其 extractor_llm)
  - 读取:cube.text_mem.search(query, top_k=10)
  - 向量库:Qdrant 本地嵌入模式(每条目独立 path/collection),无 Docker
  - 抽取 LLM:--llm-model(默认 gpt-4.1-mini / OpenAI 官方端点)。
    claude-haiku-4-5 走 Anthropic OpenAI 兼容端点会被 400 拒:
    "`temperature` and `top_p` cannot both be specified for this model"
    ——MemOS 的 OpenAILLM._build_request_body 永远同时发 temperature 与 top_p,
    无配置项可关闭,故按预注册允许的 gpt-4.1-mini 备选口径钉住并如实入档。

隔离 venv:.venv_memos(python 3.12,MemoryOS==2.0.32)。
用法:
  PYTHONUTF8=1 .venv_memos/Scripts/python.exe scripts/repro_batch33h_memos.py \
      --limit-stores 1 --out-suffix _smoke
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback

from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")

from dotenv import load_dotenv

load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic  # noqa: E402

from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch2 import ROOT, READER_MODEL, READER_SYS, VOLS, sample_stores  # noqa: E402
from repro_batch4 import sess_text  # noqa: E402

TOP_K = 10


_ACTIVE = threading.local()  # 每工作线程当前条目的计数器


class UsageCounter:
    """MemOS 不自报 token 用量;包住其 openai 客户端如实计数。

    注意:MemOS 的 LLMFactory/EmbedderFactory 带 @singleton_factory,配置相同
    的抽取器/嵌入器在所有 MemCube 之间共享同一实例,故不能"每条目各包一层"
    (会层层嵌套、跨条目重复计数)。改为:全局只包一次,按线程本地
    _ACTIVE.counter 归属到当前条目。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.llm_in = self.llm_out = self.llm_calls = 0
        self.emb_tok = self.emb_calls = 0
        self.n_mem = 0
        self.errs = 0

    def add_llm(self, i, o):
        with self.lock:
            self.llm_in += int(i or 0)
            self.llm_out += int(o or 0)
            self.llm_calls += 1

    def add_emb(self, t):
        with self.lock:
            self.emb_tok += int(t or 0)
            self.emb_calls += 1

    def snap(self):
        with self.lock:
            return dict(llm_in=self.llm_in, llm_out=self.llm_out,
                        llm_calls=self.llm_calls, emb_tok=self.emb_tok,
                        emb_calls=self.emb_calls)


class MemOSSystem:
    """MemOS 2.0.32,general_text MemCube(Qdrant 本地嵌入模式)。"""

    name = "memos"

    def __init__(self, llm_model: str, llm_api_base: str | None,
                 llm_api_key: str, embed_model: str, embed_dims: int,
                 store_root: Path, top_k: int = TOP_K,
                 drop_top_p: bool = False):
        from memos.configs.mem_cube import GeneralMemCubeConfig

        self._cube_cfg_cls = GeneralMemCubeConfig
        self.drop_top_p = drop_top_p
        self.llm_model = llm_model
        self.llm_api_base = llm_api_base or "https://api.openai.com/v1"
        self.llm_api_key = llm_api_key
        self.embed_model = embed_model
        self.embed_dims = embed_dims
        self.store_root = store_root
        self.top_k = top_k
        self.cubes: dict = {}
        self.counters: dict = {}

    def _cube_config(self, uid: str):
        return self._cube_cfg_cls.model_validate({
            "user_id": uid,
            "cube_id": f"memos_{uid}",
            "text_mem": {
                "backend": "general_text",
                "config": {
                    "cube_id": f"memos_{uid}",
                    "extractor_llm": {
                        "backend": "openai",
                        "config": {
                            "model_name_or_path": self.llm_model,
                            "api_key": self.llm_api_key,
                            "api_base": self.llm_api_base,
                        },
                    },
                    "vector_db": {
                        "backend": "qdrant",
                        "config": {
                            "collection_name": f"memos_{uid}",
                            "vector_dimension": self.embed_dims,
                            "distance_metric": "cosine",
                            "path": str(self.store_root / uid / "qdrant"),
                        },
                    },
                    "embedder": {
                        "backend": "universal_api",
                        "config": {
                            "provider": "openai",
                            "api_key": os.environ["OPENAI_API_KEY"],
                            "model_name_or_path": self.embed_model,
                            "embedding_dims": self.embed_dims,
                        },
                    },
                },
            },
            "act_mem": {"backend": "uninitialized", "config": {}},
            "para_mem": {"backend": "uninitialized", "config": {}},
            "pref_mem": {"backend": "uninitialized", "config": {}},
        })

    def _instrument(self, mem):
        """幂等包装:同一 client 只包一次,用量按线程本地计数器归属。"""
        try:
            c = mem.extractor_llm.client
            if not getattr(c.chat.completions.create, "_memos_wrapped", False):
                orig = c.chat.completions.create
                drop_top_p = self.drop_top_p

                def wrapped(**kw):
                    if drop_top_p:
                        # Anthropic 的 OpenAI 兼容端点不接受 temperature 与
                        # top_p 同时出现(400)。MemOS 的 _build_request_body
                        # 无条件同时发两者且无配置项可关,故在传输层丢掉
                        # top_p——只改这一个不被支持的采样参数,不改 MemOS
                        # 的提示词/流程/解析。偏离如实入档。
                        kw.pop("top_p", None)
                    r = orig(**kw)
                    cnt = getattr(_ACTIVE, "counter", None)
                    if cnt is not None:
                        try:
                            cnt.add_llm(r.usage.prompt_tokens,
                                        r.usage.completion_tokens)
                        except Exception:  # noqa: BLE001
                            pass
                    return r

                wrapped._memos_wrapped = True
                c.chat.completions.create = wrapped
        except Exception:  # noqa: BLE001
            print("[warn] extractor LLM not instrumented", flush=True)
        try:
            ec = mem.embedder.client
            if not getattr(ec.embeddings.create, "_memos_wrapped", False):
                eorig = ec.embeddings.create

                def ewrapped(**kw):
                    r = eorig(**kw)
                    cnt = getattr(_ACTIVE, "counter", None)
                    if cnt is not None:
                        try:
                            cnt.add_emb(r.usage.total_tokens)
                        except Exception:  # noqa: BLE001
                            pass
                    return r

                ewrapped._memos_wrapped = True
                ec.embeddings.create = ewrapped
        except Exception:  # noqa: BLE001
            print("[warn] embedder not instrumented", flush=True)

    def ingest(self, uid, sessions):
        from memos.mem_cube.general import GeneralMemCube

        (self.store_root / uid).mkdir(parents=True, exist_ok=True)
        cube = GeneralMemCube(self._cube_config(uid))
        counter = UsageCounter()
        _ACTIVE.counter = counter
        self._instrument(cube.text_mem)
        self.cubes[uid] = cube
        self.counters[uid] = counter
        n_mem = 0
        errs = 0
        for s in sessions:  # 时间序由调用方保证
            msgs = [{"role": "user", "content": sess_text(s)}]
            for attempt in range(3):
                try:
                    mems = cube.text_mem.extract(msgs)
                    if mems:
                        cube.text_mem.add(mems)
                        n_mem += len(mems)
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        errs += 1
                        print(f"[{uid}] extract/add gave up: "
                              f"{type(e).__name__}: {str(e)[:120]}", flush=True)
                    else:
                        time.sleep(3)
        counter.n_mem = n_mem
        counter.errs = errs
        return n_mem, errs

    def search(self, uid, query):
        cube = self.cubes.get(uid)
        if cube is None:
            return []
        try:
            items = cube.text_mem.search(query, top_k=self.top_k)
            return [f"- {it.memory}" for it in items]
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}: {str(e)[:120]}",
                  flush=True)
            return []

    def close(self, uid):
        cube = self.cubes.pop(uid, None)
        if cube is None:
            return
        try:
            cube.text_mem.vector_db.client.close()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-stores", type=int, default=0)
    ap.add_argument("--out-suffix", default="")
    ap.add_argument("--llm-model", default="gpt-4.1-mini")
    ap.add_argument("--llm-api-base", default="https://api.openai.com/v1")
    ap.add_argument("--llm-api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--embed-model", default="text-embedding-3-small")
    ap.add_argument("--embed-dims", type=int, default=1536)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--drop-top-p", action="store_true",
                    help="传输层丢弃 top_p(Anthropic OpenAI 兼容端点要求 "
                         "temperature/top_p 二选一);其余请求原样。")
    # b35c 接线(仅装载段;协议常量与 MemOSSystem/run_uid 不动)
    ap.add_argument("--vols", default="",
                    help="逗号分隔语料 json;默认保持 repro_batch2.VOLS")
    ap.add_argument("--uids-file", default="",
                    help="uid 清单(每行一个);给出时替代 sample_stores() 的 picked")
    ap.add_argument("--questions-file", default="",
                    help="题集 jsonl(uid/qid/qtype/question/gold);给出时 by_uid 从它重建")
    ap.add_argument("--out", default="",
                    help="结果 jsonl 完整路径;默认 results/wsc_s5_memos{suffix}.jsonl")
    ap.add_argument("--store-root", default="",
                    help="店根目录;默认 results/memos_stores{suffix or _60q}")
    a = ap.parse_args()

    store_root = (ROOT / a.store_root if a.store_root else
                  ROOT / "results" / f"memos_stores{a.out_suffix or '_60q'}")
    store_root.mkdir(parents=True, exist_ok=True)
    sysm = MemOSSystem(
        llm_model=a.llm_model, llm_api_base=a.llm_api_base,
        llm_api_key=os.environ[a.llm_api_key_env],
        embed_model=a.embed_model, embed_dims=a.embed_dims,
        store_root=store_root, top_k=a.top_k, drop_top_p=a.drop_top_p)

    out_p = (ROOT / a.out if a.out else
             ROOT / f"results/wsc_s5_{sysm.name}{a.out_suffix}.jsonl")
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"]
                for l in open(out_p, encoding="utf-8")}
    vols = a.vols.split(",") if a.vols else VOLS
    entries = {}
    for v in vols:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    if a.questions_file:
        by_uid = {}
        for q in (json.loads(l) for l in
                  open(ROOT / a.questions_file, encoding="utf-8") if l.strip()):
            by_uid.setdefault(q["uid"], []).append(q)
    if a.uids_file:
        picked = [u.strip() for u in
                  open(ROOT / a.uids_file, encoding="utf-8") if u.strip()]
    picked = [u for u in picked if u in by_uid]
    if a.limit_stores:
        picked = picked[:a.limit_stores]

    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    fh = open(out_p, "a", encoding="utf-8")
    lock = threading.Lock()

    def run_uid(uid):
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            return
        sessions = sorted(entries[uid].get("sessions", []),
                          key=lambda s: s.get("date", ""))
        t0 = time.time()
        try:
            n_mem, errs = sysm.ingest(uid, sessions)
        except Exception:  # noqa: BLE001
            print(f"[{uid}] INGEST FAILED\n{traceback.format_exc(limit=3)}",
                  flush=True)
            return
        ingest_s = time.time() - t0
        u = sysm.counters[uid].snap()
        for q in qs:
            t1 = time.time()
            mems = sysm.search(uid, q["question"])
            memtext = "\n".join(mems) if mems else "(no memories retrieved)"
            ans, ti, to = "", 0, 0
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
                    print(f"reader retry {attempt}: {type(e).__name__}",
                          flush=True)
                    time.sleep(3)
            v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
            row = {
                "question_id": q["qid"], "mode": sysm.name, "uid": uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": ans,
                "memories_n": len(mems),
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
                "build_s": round(ingest_s, 1),
                "latency_s": round(time.time() - t1, 2),
                # MemOS 侧写入成本(每条目一次,逐题重复记录以便聚合)
                "memos_llm_model": a.llm_model,
                "memos_kept_memories": n_mem,
                "memos_extract_errors": errs,
                "memos_session_count": len(sessions),
                "memos_ingest_llm_in": u["llm_in"],
                "memos_ingest_llm_out": u["llm_out"],
                "memos_ingest_llm_calls": u["llm_calls"],
                "memos_ingest_embed_tokens": u["emb_tok"],
                "memos_retrieved": mems[:TOP_K],
            }
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
        print(f"[{uid}] {len(sessions)} sessions -> {n_mem} memories in "
              f"{ingest_s:.0f}s (llm {u['llm_in']}/{u['llm_out']} tok, "
              f"emb {u['emb_tok']} tok), answered {len(qs)}", flush=True)
        sysm.close(uid)

    if a.workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            list(ex.map(run_uid, picked))
    else:
        for uid in picked:
            run_uid(uid)
    fh.close()

    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / max(len(rows), 1) * 100
    print(f"\n{sysm.name}: {acc:.2f}% (n={len(rows)})")
    print(f"judge usage: {judge.total_usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
