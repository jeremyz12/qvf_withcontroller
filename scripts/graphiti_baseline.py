# -*- coding: utf-8 -*-
"""Zep/Graphiti(时序知识图谱记忆)基线 × WikiState。

镜像 Mem0 协议:P39 条目 6-25(20 条 80 问),同 haiku 读者、同 opus 判官;
Graphiti 按其默认栈(OpenAI LLM+嵌入)做图谱构建与检索,facts(含
valid_at/invalid_at)作为记忆摘录投喂修正框定读者。条目间以 group_id 隔离。"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from graphiti_core import Graphiti  # noqa: E402
from graphiti_core.nodes import EpisodeType  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

READER_MODEL = "claude-haiku-4-5"
READER_SYS = (
    "You are the user's personal AI assistant. You will be shown FACTS "
    "retrieved from a memory system about this user (each may carry a "
    "validity period), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)


def parse_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return datetime(2020, 1, 1, tzinfo=timezone.utc)


async def run(a):
    items = json.loads(Path(a.data).read_text(encoding="utf-8"))
    items = items[a.item_offset:a.item_offset + a.items]
    g = Graphiti("bolt://localhost:17687", "neo4j", "qvftest123")
    await g.build_indices_and_constraints()
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    out_f = Path(a.out)
    done = set()
    if out_f.exists():
        for l in open(out_f, encoding="utf-8"):
            done.add(json.loads(l)["question_id"])
    fh = open(out_f, "a", encoding="utf-8")
    for it in items:
        uid = it["uid"]
        qids = [f"{uid}_{dim}_query" for dim in it.get("probing_queries", {})]
        if qids and all(q in done for q in qids):
            continue
        t0 = time.time()
        sessions = sorted(it.get("sessions", []), key=lambda s: s.get("date", ""))
        for si, sess in enumerate(sessions):
            body = "\n".join(str(t)[:400] for t in sess.get("turns", [])[:6])
            for attempt in range(3):
                try:
                    await g.add_episode(
                        name=f"{uid}-s{si}",
                        episode_body=body,
                        source=EpisodeType.message,
                        source_description="chat session",
                        reference_time=parse_date(sess.get("date", "")),
                        group_id=uid,
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[{uid}] s{si} attempt {attempt}: {type(e).__name__}: {str(e)[:80]}",
                          flush=True)
                    await asyncio.sleep(2)
        ingest_s = time.time() - t0
        last_date = it["chain"][-1]["date"] if it.get("chain") else ""
        for dim, q in it.get("probing_queries", {}).items():
            qid = f"{uid}_{dim}_query"
            if qid in done:
                continue
            facts = []
            try:
                results = await g.search(q["q"], group_ids=[uid], num_results=10)
                for r in results:
                    f = getattr(r, "fact", None) or str(r)
                    va = getattr(r, "valid_at", None)
                    ia = getattr(r, "invalid_at", None)
                    span = ""
                    if va or ia:
                        span = f" (valid {str(va)[:10] if va else '?'} → {str(ia)[:10] if ia else 'now'})"
                    facts.append(f"- {f}{span}")
            except Exception as e:  # noqa: BLE001
                print(f"[{qid}] search fail: {type(e).__name__}", flush=True)
            mem = "\n".join(facts) if facts else "(no facts retrieved)"
            ans = ""
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=READER_MODEL, max_tokens=300, temperature=0.0,
                        system=READER_SYS,
                        messages=[{"role": "user", "content":
                                   f"FACTS FROM MEMORY:\n{mem}\n\n"
                                   f"TODAY'S DATE: {last_date}\n\n"
                                   f"USER'S NEW MESSAGE: {q['q']}"}])
                    ans = "".join(b.text for b in r.content if b.type == "text")
                    break
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(2)
            v = judge.judge(q["q"], str(q["gold"]), ans, qid)
            fh.write(json.dumps({
                "question_id": qid, "mode": "graphiti",
                "question": q["q"], "gold_answer": str(q["gold"]),
                "answer": ans, "facts_n": len(facts),
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
            }, ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] ingested {len(sessions)} sessions in {ingest_s:.0f}s, answered",
              flush=True)
    await g.close()
    print("DONE")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=r"data/wikistate_full.json")
    ap.add_argument("--out", default=r"results/wiki_graphiti.jsonl")
    ap.add_argument("--items", type=int, default=20)
    ap.add_argument("--item-offset", type=int, default=5, dest="item_offset")
    asyncio.run(run(ap.parse_args()))
