# -*- coding: utf-8 -*-
"""TRACE 考生适配器(批 33-H2)。

TRACE = arXiv:2607.00339 "State-Aware Query Processing over Temporal Evidence
Graphs for Conversational Data";代码 https://github.com/MorinWang/TRACE (MIT)。

协议镜像 scripts/repro_batch4.py(60 题标定场同台口径):
  * 同 15 库抽样(repro_batch2.sample_stores)/ 同题源 / k=10;
  * 读者 = claude-haiku-4-5,temp 0,max_tokens 300,READER_SYS(同 repro_batch2);
  * 判官 = qvf.judge.ClaudeJudge(冻结默认判官模型);
  * 只取对手系统检索到的证据交我方读者(与 cognee / LightRAG / Graphiti 同处理)。

TRACE 侧全部调用其原仓代码,不复刻任何机制:
  ingest_longmemeval.ingest_memories / build_summaries
  build_graph_longmemeval.build_graph
  eval_locomo.TRACEGraphAgent + trace.trace_pipeline.TRACEPipeline.retrieve
本脚本只做三件事:(1) 把 WikiState 库转成 LongMemEval 记录格式喂给它原生的
LongMemEvalAdapter;(2) 取出它 pipeline 返回的 hybrid context;(3) 记账。

用法(必须用隔离环境 .venv_trace):
  TRACE_REPO=<path to TRACE clone> \
  .venv_trace/Scripts/python.exe scripts/trace_contestant.py \
      --questions data/lb_sample60.jsonl --out-suffix "" --shard 0 --nshards 1
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

TRACE_REPO = os.environ.get("TRACE_REPO", "").strip()
if not TRACE_REPO:
    raise SystemExit("TRACE_REPO env var must point at the TRACE clone")
sys.path.insert(0, TRACE_REPO)

import anthropic  # noqa: E402
import openai  # noqa: E402

# --- token 记账:包住 openai 同步 chat.completions.create -----------------
_USAGE = {"in": 0, "out": 0, "calls": 0}
_orig_create = openai.resources.chat.completions.Completions.create


def _counted_create(self, *a, **kw):
    r = _orig_create(self, *a, **kw)
    try:
        _USAGE["in"] += int(r.usage.prompt_tokens or 0)
        _USAGE["out"] += int(r.usage.completion_tokens or 0)
        _USAGE["calls"] += 1
    except Exception:  # noqa: BLE001
        pass
    return r


openai.resources.chat.completions.Completions.create = _counted_create

from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch2 import READER_MODEL, READER_SYS, VOLS, sample_stores  # noqa: E402

# --- TRACE 原仓 ------------------------------------------------------------
_cwd = os.getcwd()
os.chdir(TRACE_REPO)
from build_graph_longmemeval import build_graph, load_config  # noqa: E402
from eval_locomo import (  # noqa: E402
    TRACEGraphAgent, expand_pipeline_config, expand_reasoner_config,
)
from eval_longmemeval import (  # noqa: E402
    allowed_notes_for_question, expand_lme_token_opt_config,
    filter_graph_by_note_ids, load_longmemeval_memories, make_memory_view,
)
from ingest_longmemeval import build_summaries, ingest_memories  # noqa: E402
from memory_layer_robust import RobustLLMController  # noqa: E402
from trace.causal_graph import CausalGraph  # noqa: E402
from trace.dataset_adapter import LongMemEvalAdapter  # noqa: E402
from trace.session_summarizer import SessionSummarizer  # noqa: E402
import numpy as np  # noqa: E402
os.chdir(_cwd)

TAG = "global"


def parse_turn(turn_text) -> dict:
    """WikiState turns 以 str(dict) 存;还原 role/content(同 run_mem0_baseline)。"""
    if isinstance(turn_text, dict):
        return {"role": str(turn_text.get("role", "user")),
                "content": str(turn_text.get("content", ""))}
    s = str(turn_text).strip()
    if s.startswith("{"):
        try:
            d = ast.literal_eval(s)
            if isinstance(d, dict) and "content" in d:
                role = str(d.get("role", "user"))
                if role not in ("user", "assistant"):
                    role = "user"
                return {"role": role, "content": str(d["content"])}
        except (ValueError, SyntaxError):
            pass
    return {"role": "user", "content": s}


def to_longmemeval(uid, sessions, questions) -> list:
    """一库 -> LongMemEval 记录列表(每题一条,haystack = 该库全部会话)。"""
    sids, dates, turns_list = [], [], []
    for i, s in enumerate(sessions):
        sids.append(f"{uid}#s{i:03d}")
        dates.append(str(s.get("date", "")))
        turns_list.append([parse_turn(t) for t in s.get("turns", [])])
    recs = []
    for q in questions:
        recs.append({
            "question_id": q["qid"],
            # question_type 只影响 CATEGORY_MAP;LongMemEval 路径下 token_opt
            # 默认关闭,category 对检索无作用(见 trace_pipeline 第 649 行)。
            "question_type": "multi-session",
            "question": q["question"],
            "answer": str(q["gold"]),
            "question_date": None,
            "haystack_session_ids": list(sids),
            "haystack_dates": list(dates),
            "haystack_sessions": turns_list,
        })
    return recs


def run_uid(uid, sessions, questions, cfg, store_root: Path, judge, client,
            fh, done: set) -> None:
    qs = [q for q in questions if q["qid"] not in done]
    if not qs:
        return
    base = store_root / uid
    mem_dir = base / "memories"
    sum_dir = base / "summaries"
    graph_dir = base / "graphs"
    for d in (mem_dir, sum_dir, graph_dir):
        d.mkdir(parents=True, exist_ok=True)
    ds_path = base / "dataset_longmemeval.json"
    ds_path.write_text(json.dumps(to_longmemeval(uid, sessions, questions),
                                  ensure_ascii=False), encoding="utf-8")

    u0 = dict(_USAGE)
    t0 = time.time()

    api_key = cfg.get("api_key") or os.getenv("OPENAI_API_KEY")
    api_base = cfg.get("api_base") or None
    llm = RobustLLMController(backend=cfg.get("backend", "openai"),
                              model=cfg["model"], api_key=api_key,
                              api_base=api_base).llm
    summarizer = SessionSummarizer(
        llm=llm, cache_path=str(sum_dir / "longmemeval_session_summaries_cache.json"))
    adapter = LongMemEvalAdapter(dataset_path=str(ds_path), summarizer=summarizer)
    ingest_memories(adapter=adapter, config=cfg, memories_dir=mem_dir,
                    tag=TAG, force=False)
    build_summaries(adapter, sum_dir, TAG, batch_size=20)
    build_graph(config=cfg, memories_dir=mem_dir, summaries_dir=sum_dir,
                output_dir=graph_dir, tag=TAG, force=False)
    ingest_s = time.time() - t0
    ing = {k: _USAGE[k] - u0[k] for k in u0}

    # --- 查询期:完全走 eval_longmemeval 的过滤 + TRACEGraphAgent ----------
    graph_file = graph_dir / f"event_graph_longmemeval_{TAG}.json"
    graph = CausalGraph.load(str(graph_file)) if graph_file.exists() else None
    agent = TRACEGraphAgent(
        model=cfg["model"], backend=cfg.get("backend", "openai"),
        retrieve_k=int(cfg.get("retrieve_k", 10)),
        temperature_c5=float(cfg.get("temperature_c5", 0.5)),
        api_key=api_key, api_base=api_base, skip_evolution=True, graph=None,
        reasoner_config=expand_reasoner_config(cfg.get("reasoner")),
        pipeline_config=expand_pipeline_config(cfg.get("pipeline")),
        token_opt_config=expand_lme_token_opt_config(cfg.get("longmemeval_token_opt")),
        lite_mode=False,
    )
    base_memories, base_retriever, note_map = load_longmemeval_memories(
        mem_dir, TAG, agent)
    qa_pairs = {p["question_id"]: p for p in
                LongMemEvalAdapter(str(ds_path)).get_all_qa_pairs()}

    for q in qs:
        t1 = time.time()
        u1 = dict(_USAGE)
        qa = qa_pairs[q["qid"]]
        row = {"question_id": q["qid"], "mode": "trace", "uid": uid,
               "question_type": q["qtype"], "question": q["question"],
               "gold_answer": q["gold"],
               "ingest_seconds": round(ingest_s, 1),
               "build_s": round(ingest_s, 1),
               "trace_ingest_input_tokens": ing["in"],
               "trace_ingest_output_tokens": ing["out"],
               "trace_ingest_llm_calls": ing["calls"]}
        context = ""
        try:
            allowed = allowed_notes_for_question(note_map, qa["haystack_session_ids"])
            fmem, fretr = make_memory_view(base_memories, base_retriever, allowed)
            agent.memory_system.memories = fmem
            agent.memory_system.retriever = fretr
            fgraph = filter_graph_by_note_ids(graph, allowed)
            if fgraph is not None:
                agent.set_graph(fgraph, sample=None)
            else:
                agent.graph, agent.pipeline = None, None

            keywords = agent.generate_query_llm(qa["question"])
            if agent.pipeline is None:
                context = agent.retrieve_memory(keywords, k=agent.retrieve_k)
                row["trace_path_mode"] = "amem_fallback"
            else:
                idx = agent.memory_system.retriever.search(
                    keywords, k=agent.retrieve_k)
                if not isinstance(idx, np.ndarray):
                    idx = np.array(idx)
                qemb = agent.memory_system.retriever.model.encode([keywords])[0]
                res = agent.pipeline.retrieve(
                    query=qa["question"], retrieval_indices=idx,
                    memory_system=agent.memory_system, query_embedding=qemb,
                    final_k=agent.retrieve_k, question_category=int(qa["category"]))
                context = res.context
                row["trace_path_mode"] = ("paths" if res.explanation
                                          else "no_paths")
                row["trace_path_explanation"] = str(res.explanation or "")[:1500]
        except Exception:  # noqa: BLE001
            row["retrieval_error"] = traceback.format_exc(limit=3)
        row["trace_retrieval_latency_s"] = round(time.time() - t1, 2)
        rq = {k: _USAGE[k] - u1[k] for k in u1}
        row["trace_query_input_tokens"] = rq["in"]
        row["trace_query_output_tokens"] = rq["out"]
        row["trace_query_llm_calls"] = rq["calls"]
        row["trace_context_chars"] = len(context or "")
        row["trace_context_head"] = (context or "")[:3000]

        memtext = context if (context or "").strip() else "(no memories retrieved)"
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
                print(f"reader retry {attempt}: {type(e).__name__}", flush=True)
                time.sleep(3)
        v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
        row.update({"answer": ans, "usage_input_tokens": ti,
                    "usage_output_tokens": to, "judge_correct": v.correct,
                    "judge_reason": v.reason,
                    "latency_s": round(time.time() - t1, 2)})
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
    print(f"[{uid}] ingest {ingest_s:.0f}s ({ing['calls']} llm calls), "
          f"answered {len(qs)}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="", help="题源 jsonl;空=v1 418 题源")
    ap.add_argument("--vols", default="", help="逗号分隔语料 json;空=repro_batch2.VOLS")
    ap.add_argument("--uids-file", default="", help="uid 清单;空=sample_stores 15 库")
    ap.add_argument("--all-uids", action="store_true",
                    help="用题源里出现的全部 uid(v2.4 576 全场用)")
    ap.add_argument("--limit-stores", type=int, default=0)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--out-suffix", default="")
    ap.add_argument("--out", default="",
                    help="结果 jsonl 完整路径;空=results/wsc_s5_trace{suffix}.jsonl")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--api-base", default="", help="空=OpenAI 官方端点")
    ap.add_argument("--update-detection", action="store_true",
                    help="打开 TRACE Phase 3(update/contradiction 检测 + 有效性传播);"
                         "其 LongMemEval 出厂 config 默认关闭")
    ap.add_argument("--evolution", action="store_true",
                    help="把 A-Mem 记忆演化改回 TRACE 的 LoCoMo 预设"
                         "(TRACEAgent/ingest_locomo 默认 skip_evolution=False);"
                         "其 LongMemEval 入口硬编码 skip_evolution=True")
    ap.add_argument("--store-root", default="")
    a = ap.parse_args()

    cfg = load_config(str(Path(TRACE_REPO) / "configs" / "longmemeval_main.json"))
    cfg["model"] = a.model
    cfg["backend"] = "openai"
    cfg["api_base"] = a.api_base or None
    if a.update_detection:
        cfg["longmemeval_skip_update_detection"] = False
    if a.evolution:
        # 只改构造参数(与 ingest_locomo.py 走的 TRACEAgent 默认一致),不改其代码。
        import ingest_longmemeval as _ilme
        import memory_layer_robust as _mlr

        _Base = _mlr.RobustAgenticMemorySystem

        class _EvoMemory(_Base):
            def __init__(self, *args, **kw):
                kw["skip_evolution"] = False
                super().__init__(*args, **kw)

        _mlr.RobustAgenticMemorySystem = _EvoMemory
        _ilme.RobustAgenticMemorySystem = _EvoMemory

    vols = a.vols.split(",") if a.vols else VOLS
    entries = {}
    for v in vols:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)

    picked, by_uid = sample_stores()
    if a.questions:
        by_uid = {}
        for q in (json.loads(l) for l in
                  open(ROOT / a.questions, encoding="utf-8") if l.strip()):
            by_uid.setdefault(q["uid"], []).append(q)
        if a.uids_file:
            picked = [u.strip() for u in
                      open(ROOT / a.uids_file, encoding="utf-8") if u.strip()]
        elif a.all_uids:
            picked = sorted(by_uid)
        picked = [u for u in picked if u in by_uid]
    if a.limit_stores:
        picked = picked[:a.limit_stores]
    picked = [u for i, u in enumerate(picked) if i % a.nshards == a.shard]

    out_p = (ROOT / a.out) if a.out else (
        ROOT / f"results/wsc_s5_trace{a.out_suffix}.jsonl")
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in
                open(out_p, encoding="utf-8") if l.strip()}
    store_root = Path(a.store_root) if a.store_root else (
        ROOT / "results" / "trace_stores" / f"trace{a.out_suffix}")
    store_root.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    fh = open(out_p, "a", encoding="utf-8")
    for uid in picked:
        if uid not in entries:
            print(f"[{uid}] no corpus entry — skipped", flush=True)
            continue
        sessions = sorted(entries[uid].get("sessions", []),
                          key=lambda s: s.get("date", ""))
        try:
            run_uid(uid, sessions, by_uid[uid], cfg, store_root, judge, client,
                    fh, done)
        except Exception:  # noqa: BLE001
            print(f"[{uid}] FAILED:\n{traceback.format_exc(limit=5)}", flush=True)
    fh.close()
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8") if l.strip()]
    if rows:
        acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
        print(f"\ntrace{a.out_suffix}: {acc:.2f}% (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
