# -*- coding: utf-8 -*-
"""批 30-A:无结构摘要臂——压缩-结构分解(prereg results/opt_batch30_prereg.md)。

阶段一 --phase sum:haiku 对 144 店原语料整段摘要(通用提示词,无任何
卡片/槽位/日期 schema 指令,max_tokens=3000 对齐账目预算档)。
阶段二 --phase read:haiku + PLAIN_PROMPT(冻结件逐字)读摘要答 576 题,
ClaudeJudge 同栈——与 smwplain/smoc 各臂同口径可配对。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import PLAIN_PROMPT, render_transcript  # noqa: E402

SUM_DIR = ROOT / "results/wt_summaries_v2"
SUM_SYS = ("You are a careful assistant that summarizes conversation "
           "histories.")
SUM_USER = ("Summarize the following conversation history comprehensively "
            "and faithfully, in plain prose, so that questions about the "
            "user could be answered later from your summary alone. Do not "
            "omit factual details about the user.\n\n{transcript}")


def haiku(client, system, user, max_tokens):
    r = client.messages.create(model="claude-haiku-4-5",
                               max_tokens=max_tokens, temperature=0.0,
                               system=system,
                               messages=[{"role": "user", "content": user}])
    return ("".join(b.text for b in r.content if b.type == "text"),
            r.usage.input_tokens, r.usage.output_tokens)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["sum", "read"], required=True)
    # [批33-A 新增] 三个覆盖旗标;不给时逐字节等同冻结件默认路径
    ap.add_argument("--data", default="data/wikistate_full_ALL.json")
    ap.add_argument("--sum-dir", default="results/wt_summaries_v2")
    ap.add_argument("--questions", default="data/wsc_s5_v2.jsonl")
    ap.add_argument("--out", default="results/wsc_v2_summary_arm.jsonl")
    a = ap.parse_args()
    global SUM_DIR
    SUM_DIR = ROOT / a.sum_dir
    entries = {e["uid"]: e for e in json.loads(
        (ROOT / a.data).read_text(encoding="utf-8"))}
    client = anthropic.Anthropic()
    if a.phase == "sum":
        SUM_DIR.mkdir(parents=True, exist_ok=True)
        for i, (uid, e) in enumerate(sorted(entries.items()), 1):
            f = SUM_DIR / f"{uid}.txt"
            if f.exists():
                continue
            tr = render_transcript(e.get("sessions", []))
            for attempt in range(3):
                try:
                    txt, ti, to = haiku(client, SUM_SYS,
                                        SUM_USER.format(transcript=tr), 3000)
                    f.write_text(txt, encoding="utf-8")
                    print(f"[sum {i}/144] {uid} in={ti} out={to}", flush=True)
                    break
                except Exception as ex:  # noqa: BLE001
                    print(f"retry {attempt}: {str(ex)[:80]}", flush=True)
                    time.sleep(5)
        print("SUM DONE", len(list(SUM_DIR.glob("*.txt"))))
        return 0
    qs = [json.loads(l) for l in
          open(ROOT / a.questions, encoding="utf-8")]
    outp = ROOT / a.out
    done = {json.loads(l)["question_id"] for l in
            open(outp, encoding="utf-8")} if outp.exists() else set()
    fh = open(outp, "a", encoding="utf-8")
    judge = ClaudeJudge()
    n = ok = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done:
            continue
        summ = (SUM_DIR / f"{uid}.txt").read_text(encoding="utf-8")
        user = PLAIN_PROMPT.format(question=q["question"],
                                   transcript="Summary of the conversation "
                                   "history:\n" + summ)
        t0 = time.time()
        raw, ti, to = "", 0, 0
        for attempt in range(3):
            try:
                raw, ti, to = haiku(client, "", user, 800)
                break
            except Exception as ex:  # noqa: BLE001
                print(f"retry {attempt}: {str(ex)[:80]}", flush=True)
                time.sleep(5)
        v = judge.judge(q["question"], str(q["gold"]), raw, q.get("qtype"))
        fh.write(json.dumps({
            "question_id": qid, "mode": "summary_arm", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": raw[:2000],
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "latency_s": round(time.time() - t0, 2)}, ensure_ascii=False)
            + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct}", flush=True)
    print(f"SUMMARY ARM DONE: {ok}/{n} = {ok / max(1, n) * 100:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
