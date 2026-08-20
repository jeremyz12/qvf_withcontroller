# -*- coding: utf-8 -*-
"""scripts/langmem_s5_agg.py — LangMem × WikiState 聚合题集(按库抽样)。

预注册:results/langmem_s5_prereg.md(提交 22881f5,先于本文件运行)。
协议镜像 scripts/langmem_baseline.py(摄入/读者/判官逐字同款),
题目改从聚合题清单按 uid 分组。
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
from langgraph.store.memory import InMemoryStore
from langmem import create_memory_store_manager
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-stores", type=int, default=15)
    ap.add_argument("--store-offset", type=int, default=0)
    ap.add_argument("--out", default="results/wsc_s5_langmem.jsonl")
    a = ap.parse_args()

    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    # 418 题重建(与 raw_select 同来源:归档 filter 行含全部题面字段)
    qrows = [json.loads(l) for l in open(ROOT / "results/wsc_s5_filter_only.jsonl",
                                         encoding="utf-8")]
    by_uid: dict = {}
    for r in qrows:
        by_uid.setdefault(r["uid"], []).append(
            {"qid": r["question_id"], "qtype": r["question_type"],
             "question": r["question"], "gold": r["gold_answer"]})
    uids = sorted(by_uid)
    n = len(uids)
    picked = [uids[(a.store_offset + i) * n // a.n_stores % n]
              for i in range(a.n_stores)] if a.store_offset == 0 else \
             [uids[(i * n // a.n_stores + a.store_offset) % n]
              for i in range(a.n_stores)]
    picked = list(dict.fromkeys(picked))
    print(f"抽中 {len(picked)} 库,共 {sum(len(by_uid[u]) for u in picked)} 题",
          flush=True)

    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    outp = ROOT / a.out
    done = set()
    if outp.exists():
        done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")}
    fh = open(outp, "a", encoding="utf-8")
    for uid in picked:
        it = entries.get(uid)
        if not it:
            continue
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs:
            continue
        store = InMemoryStore(index={"dims": 1536,
                                     "embed": "openai:text-embedding-3-small"})
        manager = create_memory_store_manager(
            "anthropic:claude-haiku-4-5", namespace=("memories", uid), store=store)
        t0 = time.time()
        sessions = sorted(it.get("sessions", []), key=lambda s: s.get("date", ""))
        for si, sess in enumerate(sessions):
            text = "\n".join(str(t)[:400] for t in sess.get("turns", [])[:6])
            msg = f"(session date: {sess.get('date','undated')})\n{text}"
            for attempt in range(3):
                try:
                    manager.invoke({"messages": [{"role": "user", "content": msg}]})
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[{uid}] s{si} attempt {attempt}: "
                          f"{type(e).__name__}: {str(e)[:80]}", flush=True)
                    time.sleep(2)
        ingest_s = time.time() - t0
        for q in qs:
            t1 = time.time()
            mems = []
            try:
                found = store.search(("memories", uid), query=q["question"], limit=10)
                for m in found:
                    mems.append(f"- {json.dumps(m.value, ensure_ascii=False)[:300]}")
            except Exception as e:  # noqa: BLE001
                print(f"[{q['qid']}] search fail: {type(e).__name__}", flush=True)
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
                    time.sleep(2)
            v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
            fh.write(json.dumps({
                "question_id": q["qid"], "mode": "langmem", "uid": uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": ans, "memories_n": len(mems),
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
                "latency_s": round(time.time() - t1, 2)},
                ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] ingested {len(sessions)} sessions in {ingest_s:.0f}s, "
              f"answered {len(qs)}", flush=True)
    rows = [json.loads(l) for l in open(outp, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\nLangMem 聚合题:{acc:.2f}% (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
