# -*- coding: utf-8 -*-
"""scripts/repro_batch4.py — 考生批 8:txtai / langgraph InMemoryStore ×
WikiState 聚合题(A-MEM/cognee 另行适配)。
预注册:results/repro_batch4_prereg.md。协议镜像 repro_batch2:同 15 库 60 题、
同读者同判官;k=10。
用法: python repro_batch4.py --system txtai|lgstore
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic
from qvf.judge import ClaudeJudge
from repro_batch2 import sample_stores, VOLS, ROOT, READER_MODEL, READER_SYS


def sess_text(s):
    turns = s.get("turns", [])[:6]
    return f"(session date: {s.get('date','undated')})\n" + \
        "\n".join(str(t)[:400] for t in turns)


class TxtaiSystem:
    """本地嵌入 flat-RAG 锚:零 LLM 摄入,sentence-transformers 检索。"""
    name = "txtai"

    def __init__(self):
        from txtai import Embeddings
        self._E = Embeddings
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        emb = self._E(content=True)
        emb.index([(i, sess_text(s), None) for i, s in enumerate(sessions)])
        self.stores[uid] = emb

    def search(self, uid, query):
        emb = self.stores.get(uid)
        if emb is None:
            return []
        return [f"- {r['text'][:400]}" for r in emb.search(query, limit=10)]


class LgStoreSystem:
    """langgraph InMemoryStore:官方记忆基建,openai 嵌入语义索引。"""
    name = "lgstore"

    def __init__(self):
        from langgraph.store.memory import InMemoryStore
        from langchain_openai import OpenAIEmbeddings
        self.store = InMemoryStore(index={
            "embed": OpenAIEmbeddings(model="text-embedding-3-small"),
            "dims": 1536})

    def ingest(self, uid, sessions):
        for i, s in enumerate(sessions):
            self.store.put((uid, "sessions"), f"s{i}", {"text": sess_text(s)})

    def search(self, uid, query):
        hits = self.store.search((uid, "sessions"), query=query, limit=10)
        return [f"- {h.value['text'][:400]}" for h in hits]


class Bm25System:
    """词面检索锚:rank_bm25,零 LLM 摄入。"""
    name = "bm25"

    def __init__(self):
        from rank_bm25 import BM25Okapi
        self._cls = BM25Okapi
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        docs = [sess_text(s) for s in sessions]
        toks = [d.lower().split() for d in docs]
        self.stores[uid] = (self._cls(toks), docs)

    def search(self, uid, query):
        st = self.stores.get(uid)
        if st is None:
            return []
        bm, docs = st
        import numpy as np
        scores = bm.get_scores(query.lower().split())
        idx = np.argsort(scores)[::-1][:10]
        return [f"- {docs[i][:400]}" for i in idx]


class AmemSystem:
    """A-MEM(agiresearch):Zettelkasten 演化笔记;llm_backend=openai
    gpt-4o-mini(其原生支持面),嵌入本地 MiniLM。每 add_note 触发 LLM
    笔记构造+链接演化——抽样先行。"""
    name = "amem"

    def __init__(self):
        sys.path.insert(0, r"C:/Users/25243/AppData/Local/Temp/claude/"
                           r"D--ZZL-cluade/2b238d36-0e89-4591-ac1c-f5ffd6578795/"
                           r"scratchpad/A-mem")
        from agentic_memory.memory_system import AgenticMemorySystem
        self._cls = AgenticMemorySystem
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        m = self._cls(model_name="all-MiniLM-L6-v2",
                      llm_backend="openai", llm_model="gpt-4o-mini")
        for s in sessions:
            for attempt in range(3):
                try:
                    m.add_note(sess_text(s), time=s.get("date", ""))
                    break
                except TypeError:
                    try:
                        m.add_note(sess_text(s))
                        break
                    except Exception:  # noqa: BLE001
                        time.sleep(3)
                except Exception as e:  # noqa: BLE001
                    print(f"[{uid}] add retry {attempt}: "
                          f"{type(e).__name__}: {str(e)[:80]}", flush=True)
                    time.sleep(3)
        self.stores[uid] = m

    def search(self, uid, query):
        m = self.stores.get(uid)
        if m is None:
            return []
        try:
            hits = m.search_agentic(query, k=10)
            out = []
            for h in hits:
                txt = h.get("content", h) if isinstance(h, dict) else str(h)
                out.append(f"- {str(txt)[:400]}")
            return out
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}", flush=True)
            return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["txtai", "lgstore", "amem", "bm25"],
                    required=True)
    ap.add_argument("--limit-stores", type=int, default=0,
                    help="只跑前 N 库(抽样先行)")
    a = ap.parse_args()
    sysm = {"txtai": TxtaiSystem, "lgstore": LgStoreSystem,
            "amem": AmemSystem, "bm25": Bm25System}[a.system]()
    out_p = ROOT / f"results/wsc_s5_{sysm.name}.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}
    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    if a.limit_stores:
        picked = picked[:a.limit_stores]
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    fh = open(out_p, "a", encoding="utf-8")
    for uid in picked:
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            continue
        t0 = time.time()
        sessions = sorted(entries[uid].get("sessions", []),
                          key=lambda s: s.get("date", ""))
        sysm.ingest(uid, sessions)
        ingest_s = time.time() - t0
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
                    print(f"retry {attempt}: {type(e).__name__}", flush=True)
                    time.sleep(3)
            v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
            fh.write(json.dumps({
                "question_id": q["qid"], "mode": sysm.name, "uid": uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": ans, "memories_n": len(mems),
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
                "latency_s": round(time.time() - t1, 2)},
                ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] ingested {len(sessions)} in {ingest_s:.0f}s, "
              f"answered {len(qs)}", flush=True)
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\n{sysm.name}: {acc:.2f}% (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
