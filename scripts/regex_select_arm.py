# -*- coding: utf-8 -*-
"""scripts/regex_select_arm.py — 正则选择基线臂(独立脚本,不触碰冻结文件)。

预注册:results/regex_select_prereg.md(提交 88aba9c,先于本文件运行)。
选择 = 固定词表匹配店内全部轮(不知槽位/问题);渲染同 raw_select;
同读者(complex_query_arm.READER_SYSTEM / MODEL)同判官(qvf.judge)。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic
from qvf.judge import ClaudeJudge
from scripts.complex_query_arm import MODEL, READER_SYSTEM, _query_date

ROOT = Path(r"D:\ZZL_cluade")
VOLS = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
        "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
QUESTIONS = Path(r"C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade"
                 r"\2b238d36-0e89-4591-ac1c-f5ffd6578795\scratchpad\s5_subset100.jsonl")
OUT = ROOT / "results/wsc_s5_regex_select_100.jsonl"
TEMPL = re.compile(r"\b(start(ed|ing)?|mov(ed|ing)|join(ed|ing)|sign(ed|ing)|"
                   r"officially|switch(ed|ing)|became|began)\b", re.I)
CAP = 12


def main() -> int:
    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    qs = [json.loads(l) for l in open(QUESTIONS, encoding="utf-8")]
    done = set()
    if OUT.exists():
        done = {json.loads(l)["question_id"] for l in open(OUT, encoding="utf-8")}
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    with OUT.open("a", encoding="utf-8") as f:
        for q in qs:
            if q["qid"] in done:
                continue
            t0 = time.time()
            e = entries[q["uid"]]
            lines = []
            for sess in e.get("sessions", []):
                d = str(sess.get("date", ""))
                for t in sess.get("turns", []):
                    txt = t.get("content", "") if isinstance(t, dict) else str(t)
                    if TEMPL.search(txt):
                        lines.append((d, txt))
            lines.sort(key=lambda x: x[0])
            ev = [f"[{d or 'undated'}] {txt}" for d, txt in lines[:CAP]]
            qdate = _query_date(e, q["question"])
            body = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
            body += ev or ["(no matching records found in memory)"]
            body.append("")
            if qdate:
                body += [f"TODAY'S DATE: {qdate}", ""]
            body.append(f"USER'S NEW MESSAGE: {q['question']}")
            rr = client.messages.create(
                model=MODEL, max_tokens=1000, temperature=0.0,
                system=[{"type": "text", "text": READER_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": "\n".join(body)}])
            answer = "".join(b.text for b in rr.content if b.type == "text")
            v = judge.judge(q["question"], str(q["gold"]), answer, q["qtype"])
            f.write(json.dumps({
                "question_id": q["qid"], "mode": "regex_select", "uid": q["uid"],
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": answer,
                "evidence_n": len(ev),
                "usage_input_tokens": rr.usage.input_tokens,
                "usage_output_tokens": rr.usage.output_tokens,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "reader_model": MODEL,
                "latency_s": round(time.time() - t0, 2)},
                ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{q['qid']}] ev={len(ev)} judge={v.correct} "
                  f"({time.time() - t0:.1f}s)", flush=True)
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\nregex_select: {acc:.2f}% (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
