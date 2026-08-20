# -*- coding: utf-8 -*-
"""scripts/repro_batch2.py — Mem0(出厂默认)与 摘要RAG harness × WikiState 聚合题。

预注册:results/repro_batch2_prereg.md(先于本文件运行提交)。
协议镜像 scripts/langmem_s5_agg.py:同 15 库抽样、同读者、同判官。
用法: python repro_batch2.py --system mem0|sumrag
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic
from qvf.judge import ClaudeJudge

ROOT = Path(r"D:\ZZL_cluade")
VOLS = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
        "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
READER_MODEL = "claude-haiku-4-5"
READER_SYS = (
    "You are the user's personal AI assistant. You will be shown MEMORIES "
    "retrieved from a memory system about this user (each may carry dates), "
    "followed by the user's new message. Reply to the new message naturally "
    "and helpfully in 1-3 sentences, as you would in an everyday chat.")


def sample_stores(n_stores=15):
    """与 langmem_s5_agg 同一抽法:418 题 uid 排序后等距。"""
    qrows = [json.loads(l) for l in open(ROOT / "results/wsc_s5_filter_only.jsonl",
                                         encoding="utf-8")]
    by_uid: dict = {}
    for r in qrows:
        by_uid.setdefault(r["uid"], []).append(
            {"qid": r["question_id"], "qtype": r["question_type"],
             "question": r["question"], "gold": r["gold_answer"]})
    uids = sorted(by_uid)
    n = len(uids)
    picked = list(dict.fromkeys(uids[i * n // n_stores % n]
                                for i in range(n_stores)))
    return picked, by_uid


class Mem0System:
    name = "mem0"

    def __init__(self):
        from mem0 import Memory
        self.m = Memory()          # 出厂默认:openai LLM + text-embedding-3-small

    def ingest(self, uid, sessions):
        for s in sessions:
            text = "\n".join(str(t)[:400] for t in s.get("turns", [])[:6])
            msg = f"(session date: {s.get('date','undated')})\n{text}"
            for attempt in range(3):
                try:
                    self.m.add([{"role": "user", "content": msg}], user_id=uid)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[{uid}] add retry {attempt}: {type(e).__name__}: "
                          f"{str(e)[:80]}", flush=True)
                    time.sleep(3)

    def search(self, uid, query):
        try:
            r = self.m.search(query, user_id=uid, limit=10)
            hits = r.get("results", r) if isinstance(r, dict) else r
            return [f"- {json.dumps(h.get('memory', h), ensure_ascii=False)[:300]}"
                    for h in hits]
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}", flush=True)
            return []


class SumRagSystem:
    name = "sumrag"

    def __init__(self):
        self.client = anthropic.Anthropic()
        from qvf.retrieval import OpenAIDenseRetriever  # text-embedding-3-small
        self._retr_cls = OpenAIDenseRetriever
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        sums = []
        for s in sessions:
            text = "\n".join(str(t)[:400] for t in s.get("turns", [])[:6])
            for attempt in range(3):
                try:
                    r = self.client.messages.create(
                        model=READER_MODEL, max_tokens=250, temperature=0.0,
                        messages=[{"role": "user", "content":
                                   "Summarize the USER-relevant facts in this "
                                   "chat session in 1-3 bullet lines. Keep "
                                   "every date, name and number; prefix with "
                                   f"the session date {s.get('date','?')}.\n\n"
                                   + text}])
                    sums.append("".join(b.text for b in r.content
                                        if b.type == "text"))
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(3)
        # 复用项目内 openai 稠密检索器(与直读臂同款嵌入)
        class _M:
            def __init__(self, c, d):
                self.content, self.metadata = c, {"session_date": d}
                self.memory_id = d
        mems = [_M(t, t[:10]) for t in sums]
        self.stores[uid] = (self._retr_cls(mems), sums)

    def search(self, uid, query):
        retr, _ = self.stores.get(uid, (None, None))
        if retr is None:
            return []
        try:
            hits = retr.retrieve(query, top_k=10)
            return [f"- [{(h.metadata or {}).get('session_date','')}] "
                    f"{h.content[:300]}" for h in hits]
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}", flush=True)
            return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["mem0", "sumrag"], required=True)
    a = ap.parse_args()
    sysm = Mem0System() if a.system == "mem0" else SumRagSystem()
    out_p = ROOT / f"results/wsc_s5_{sysm.name}.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}

    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
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
                except Exception:  # noqa: BLE001
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
