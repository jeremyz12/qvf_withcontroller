# -*- coding: utf-8 -*-
"""增量摘要记忆基线(ChatGPT 式画像记忆,写入时整理范式第二代表)。

每会话按日期序增量更新用户画像(haiku),答题只看最终画像。
与 Mem0 同属"写入时整理",但形态为自由文本画像而非记忆条目。"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

MODEL = "claude-haiku-4-5"
UPDATE_PROMPT = (
    "You maintain a running USER PROFILE from chat history. Update the profile "
    "with any new or changed facts about the user from the new session. Keep "
    "it under 400 words, keep dates when stated, drop nothing still true. "
    "Return ONLY the updated profile text."
)
ANSWER_SYS = (
    "You are the user's personal AI assistant. You have a PROFILE summarizing "
    "your past conversations with this user. Reply to the user's new message "
    "naturally and helpfully in 1-3 sentences, as you would in an everyday chat."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--items", type=int, default=0)
    a = ap.parse_args()
    items = json.loads(Path(a.data).read_text(encoding="utf-8"))
    if a.items:
        items = items[:a.items]
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
        profile = ""
        prof_in = prof_out = 0
        sessions = sorted(it.get("sessions", []), key=lambda s: s.get("date", ""))
        for sess in sessions:
            text = "\n".join(str(t)[:400] for t in sess.get("turns", [])[:6])
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=MODEL, max_tokens=700, temperature=0.0,
                        system=UPDATE_PROMPT,
                        messages=[{"role": "user", "content":
                                   f"CURRENT PROFILE:\n{profile or '(empty)'}\n\n"
                                   f"NEW SESSION ({sess.get('date','undated')}):\n{text}"}])
                    profile = "".join(b.text for b in r.content if b.type == "text")
                    prof_in += r.usage.input_tokens
                    prof_out += r.usage.output_tokens
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2)
        last_date = it["chain"][-1]["date"] if it.get("chain") else ""
        for dim, q in it.get("probing_queries", {}).items():
            qid = f"{uid}_{dim}_query"
            if qid in done:
                continue
            ans = ""
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=MODEL, max_tokens=300, temperature=0.0,
                        system=ANSWER_SYS,
                        messages=[{"role": "user", "content":
                                   f"USER PROFILE:\n{profile}\n\n"
                                   f"TODAY'S DATE: {last_date}\n\n"
                                   f"USER'S NEW MESSAGE: {q['q']}"}])
                    ans = "".join(b.text for b in r.content if b.type == "text")
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2)
            v = judge.judge(q["q"], str(q["gold"]), ans, qid)
            fh.write(json.dumps({
                "question_id": qid, "mode": "summary_memory",
                "question": q["q"], "gold_answer": str(q["gold"]),
                "answer": ans, "judge_correct": v.correct,
                "judge_reason": v.reason,
                "profile_tokens_in": prof_in, "profile_tokens_out": prof_out,
            }, ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] profile {len(profile)} chars, answered", flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
