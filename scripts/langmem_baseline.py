# -*- coding: utf-8 -*-
"""LangMem(LangChain 官方记忆库,Mem0 论文基线之一)× WikiState。

镜像 Mem0 协议:P39 条目 6-25(20 条 80 问);LangMem 记忆管理器逐会话
摄入(haiku 抽取),问题经语义检索取回记忆条目,喂给同款修正框定读者,
同 opus 判官。"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402
from langmem import create_memory_store_manager  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

READER_MODEL = "claude-haiku-4-5"
READER_SYS = (
    "You are the user's personal AI assistant. You will be shown MEMORIES "
    "retrieved from a memory system about this user (each may carry dates), "
    "followed by the user's new message. Reply to the new message naturally "
    "and helpfully in 1-3 sentences, as you would in an everyday chat."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=r"data/wikistate_full.json")
    ap.add_argument("--out", default=r"results/wiki_langmem.jsonl")
    ap.add_argument("--items", type=int, default=20)
    ap.add_argument("--item-offset", type=int, default=5, dest="item_offset")
    a = ap.parse_args()
    items = json.loads(Path(a.data).read_text(encoding="utf-8"))
    items = items[a.item_offset:a.item_offset + a.items]
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
        store = InMemoryStore(index={"dims": 1536, "embed": "openai:text-embedding-3-small"})
        manager = create_memory_store_manager(
            "anthropic:claude-haiku-4-5",
            namespace=("memories", uid),
            store=store,
        )
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
                    print(f"[{uid}] s{si} attempt {attempt}: {type(e).__name__}: {str(e)[:80]}",
                          flush=True)
                    time.sleep(2)
        ingest_s = time.time() - t0
        last_date = it["chain"][-1]["date"] if it.get("chain") else ""
        for dim, q in it.get("probing_queries", {}).items():
            qid = f"{uid}_{dim}_query"
            if qid in done:
                continue
            mems = []
            try:
                found = store.search(("memories", uid), query=q["q"], limit=10)
                for m in found:
                    mems.append(f"- {json.dumps(m.value, ensure_ascii=False)[:300]}")
            except Exception as e:  # noqa: BLE001
                print(f"[{qid}] search fail: {type(e).__name__}", flush=True)
            memtext = "\n".join(mems) if mems else "(no memories retrieved)"
            ans = ""
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=READER_MODEL, max_tokens=300, temperature=0.0,
                        system=READER_SYS,
                        messages=[{"role": "user", "content":
                                   f"MEMORIES:\n{memtext}\n\n"
                                   f"TODAY'S DATE: {last_date}\n\n"
                                   f"USER'S NEW MESSAGE: {q['q']}"}])
                    ans = "".join(b.text for b in r.content if b.type == "text")
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2)
            v = judge.judge(q["q"], str(q["gold"]), ans, qid)
            fh.write(json.dumps({
                "question_id": qid, "mode": "langmem",
                "question": q["q"], "gold_answer": str(q["gold"]),
                "answer": ans, "memories_n": len(mems),
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
            }, ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] {len(sessions)} sessions ingested in {ingest_s:.0f}s, answered",
              flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
