# -*- coding: utf-8 -*-
"""批 33-E 检索计划生成器(离线,零读者调用)。

产出"每题选中的记忆 id 有序表"(= 计划 jsonl),交 scripts/lb_reader_arm_b33.py
的 --arm plan 照单渲染。把慢的 CPU 重排与便宜的 numpy 融合从读者跑批里剥离,
使三条臂共用**同一份** text-embedding-3-small 嵌入底座(b33e_embed_cache.py),
消除"基线更强是不是换了嵌入器"的混淆。

模式:
  dense     参照复算:纯稠密 top-k(应与 lb_reader_arm.py --arm direct 逐题一致)
  rerank    E1:稠密 top-pool(50)→ BAAI/bge-reranker-v2-m3 交叉编码重排 → top-k(10)
  temporal  E2:TempRALM 式时间融合 score = cos + alpha * exp(-|Δdays|/tau),
            在**全库**记忆上打分(嵌入已缓存,全量打分与 top-pool 打分同价),
            Δdays = session_date − 问题里的 (Today is X.) 日期
  verify    用缓存复算 dense top-10,与现场 OpenAIDenseRetriever 逐题比对

选中集合一律按记忆流原序(时序)呈现给读者 —— 与 OllamaDenseRetriever.retrieve
的 `sorted(top)` 口径逐字一致,保证与 direct 臂唯一的差别是"选了哪 10 条"。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import numpy as np  # noqa: E402

from ext_direct_arm import _memories, _query_date  # noqa: E402

EMB_MODEL = "text-embedding-3-small"


def _norm(a: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(a, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return a / n


def load_all(data_path: str, emb_path: str):
    entries = {e["uid"]: e for e in
               json.loads(Path(data_path).read_text(encoding="utf-8"))}
    z = np.load(emb_path)
    mems = {uid: _memories(e) for uid, e in entries.items()}
    embs = {uid: _norm(np.asarray(z[uid], dtype="float32")) for uid in mems}
    for uid in mems:
        assert len(mems[uid]) == embs[uid].shape[0], uid
    return entries, mems, embs


def embed_queries(questions, cache_path: str):
    """问题向量:与检索器同模型同批量;落盘缓存,网格 6 格只嵌一次。"""
    p = Path(cache_path)
    if p.exists():
        z = np.load(p)
        got = {k: z[k] for k in z.files}
        if all(q["qid"] in got for q in questions):
            return {k: got[k] for k in got}
    from openai import OpenAI
    cli = OpenAI()
    texts = [q["question"] for q in questions]
    out, tok = [], 0
    for i in range(0, len(texts), 256):
        r = cli.embeddings.create(model=EMB_MODEL, input=texts[i:i + 256])
        out.extend(d.embedding for d in r.data)
        tok += r.usage.total_tokens
    mat = np.asarray(out, dtype="float32")
    store = {q["qid"]: mat[i] for i, q in enumerate(questions)}
    p.parent.mkdir(parents=True, exist_ok=True)
    np.savez(p, **store)
    print(f"query embeddings: {len(store)} tokens={tok} "
          f"cost=${tok / 1e6 * 0.02:.5f}", flush=True)
    return store


def _days(a: str, b: str):
    try:
        ya, ma, da = (int(x) for x in a.split("-")[:3])
        yb, mb, db = (int(x) for x in b.split("-")[:3])
        return (date(ya, ma, da) - date(yb, mb, db)).days
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dense", "rerank", "temporal",
                                       "verify"], required=True)
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--questions", default="data/wsc_s5_v2.jsonl")
    ap.add_argument("--emb", required=True)
    ap.add_argument("--qemb", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--pool", type=int, default=50)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--tau", type=float, default=365.0)
    ap.add_argument("--shard", default="")       # "i/j" -> questions[i::j]
    ap.add_argument("--n", type=int, default=20)  # verify 抽样题数
    ap.add_argument("--max-length", type=int, default=384)
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()

    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    if a.shard:
        i, j = (int(x) for x in a.shard.split("/"))
        qs = qs[i::j]
    entries, mems, embs = load_all(a.data, a.emb)
    qemb = embed_queries(
        [json.loads(l) for l in open(a.questions, encoding="utf-8")
         if l.strip()], a.qemb)

    # ── verify:缓存 vs 现场检索 ────────────────────────────────
    if a.mode == "verify":
        os.environ["QVF_EMBED_BACKEND"] = "openai"
        from ext_direct_arm import _retriever_cls
        cls = _retriever_cls()
        same = 0
        sample = qs[:: max(1, len(qs) // a.n)][:a.n]
        for q in sample:
            uid = q["uid"]
            qv = _norm(np.asarray(qemb[q["qid"]], dtype="float32"))
            sc = embs[uid] @ qv
            top = sorted(sorted(range(len(sc)), key=lambda i: -float(sc[i]))
                         [:a.topk])
            cached = [mems[uid][i].memory_id for i in top]
            live = [m.memory_id for m in
                    cls(mems[uid]).retrieve(q["question"], top_k=a.topk)]
            same += (cached == live)
            if cached != live:
                print(f"MISMATCH {q['qid']}\n cached={cached}\n live={live}")
        print(f"VERIFY: {same}/{len(sample)} identical top-{a.topk}")
        return 0 if same == len(sample) else 1

    # ── rerank:交叉编码器 ─────────────────────────────────────
    ce = None
    if a.mode == "rerank":
        import torch
        if a.threads:
            torch.set_num_threads(a.threads)
        from sentence_transformers import CrossEncoder
        t0 = time.time()
        ce = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=a.max_length)
        print(f"reranker loaded {time.time() - t0:.0f}s device={ce.model.device}",
              flush=True)

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if outp.exists():
        done = {json.loads(l)["qid"] for l in open(outp, encoding="utf-8")
                if l.strip()}
    fh = open(outp, "a", encoding="utf-8")
    t0 = time.time()
    for k, q in enumerate(qs):
        if q["qid"] in done:
            continue
        uid = q["uid"]
        M, E = mems[uid], embs[uid]
        qv = _norm(np.asarray(qemb[q["qid"]], dtype="float32"))
        cos = E @ qv
        if a.mode == "dense":
            top = sorted(range(len(cos)), key=lambda i: -float(cos[i]))[:a.topk]
            extra = {}
        elif a.mode == "temporal":
            qd = _query_date(entries[uid], q["question"])
            tr = np.zeros(len(M), dtype="float32")
            for i, m in enumerate(M):
                d = _days((m.metadata or {}).get("session_date", ""), qd)
                tr[i] = 0.0 if d is None else float(np.exp(-abs(d) / a.tau))
            fused = cos + a.alpha * tr
            top = sorted(range(len(fused)),
                         key=lambda i: -float(fused[i]))[:a.topk]
            extra = {"alpha": a.alpha, "tau": a.tau, "query_date": qd}
        else:  # rerank
            pool = sorted(range(len(cos)),
                          key=lambda i: -float(cos[i]))[:a.pool]
            pairs = [(q["question"], M[i].content) for i in pool]
            sc = ce.predict(pairs, batch_size=16, show_progress_bar=False)
            order = sorted(range(len(pool)), key=lambda j: -float(sc[j]))
            top = [pool[j] for j in order[:a.topk]]
            extra = {"pool": a.pool,
                     "rerank_scores": [round(float(sc[j]), 5)
                                       for j in order[:a.topk]]}
        sel = sorted(top)  # 时序呈现,同 OllamaDenseRetriever.retrieve
        fh.write(json.dumps({
            "qid": q["qid"], "uid": uid, "mode": a.mode, "topk": a.topk,
            "memory_ids": [M[i].memory_id for i in sel], **extra},
            ensure_ascii=False) + "\n")
        fh.flush()
        if k % 25 == 0:
            print(f"[{k}/{len(qs)}] {q['qid']} ({time.time() - t0:.0f}s)",
                  flush=True)
    fh.close()
    print(f"PLAN DONE {a.mode} -> {outp} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
