# -*- coding: utf-8 -*-
"""scripts/s8_relaxed_rejudge.py — S8 受影响题错答的放宽读法重判。

预注册:results/s8_convention_audit_prereg.md(提交 e852771,先于本文件运行)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic

ROOT = Path(r"D:\ZZL_cluade")
AFFECTED = json.load(open(ROOT / "scratchpad/s8_concurrency_affected.json",
                          encoding="utf-8"))
ARMS = {
    "algebra_off": "results/s8_heldout_algebra_off_p2.jsonl",
    "algebra_on":  "results/s8_heldout_algebra_on_p2.jsonl",
    "flat":        "results/s8_heldout_flat_p2.jsonl",
}
OUT = ROOT / "results/s8_relaxed_rejudge_20260820.jsonl"
MODEL = "claude-haiku-4-5"

RELAXED = """You are re-judging a QA answer under a RELAXED reading for a corpus
whose gold answers forced concurrent facts into a single-value convention.

QUESTION: {q}
GOLD (single-value convention): {gold}
MODEL ANSWER: {a}

Under the relaxed reading, the answer is CORRECT if EITHER:
- it states that multiple values hold concurrently AND includes the gold value; or
- it says the most recent value is the gold value while earlier ones may still hold; or
- it matches the gold value outright.
Otherwise it stays INCORRECT.

Reply ONLY JSON: {{"correct": true/false, "reason": "<one sentence>"}}"""


def uid_of(r):
    return r.get("uid") or r["question_id"].split("_s8")[0]


def main() -> int:
    client = anthropic.Anthropic()
    done = set()
    if OUT.exists():
        done = {(json.loads(l)["arm"], json.loads(l)["question_id"])
                for l in open(OUT, encoding="utf-8")}
    res = {}
    with OUT.open("a", encoding="utf-8") as f:
        for arm, path in ARMS.items():
            rows = [json.loads(l) for l in open(ROOT / path, encoding="utf-8")]
            aff = [r for r in rows if uid_of(r) in AFFECTED]
            wrong = [r for r in aff if not r.get("judge_correct")]
            flips = 0
            for r in wrong:
                key = (arm, r["question_id"])
                if key in done:
                    continue
                rr = client.messages.create(
                    model=MODEL, max_tokens=300, temperature=0.0,
                    messages=[{"role": "user", "content": RELAXED.format(
                        q=r["question"], gold=r["gold_answer"],
                        a=r.get("answer") or "")}])
                txt = "".join(b.text for b in rr.content if b.type == "text")
                try:
                    v = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
                    ok = bool(v.get("correct"))
                except Exception:
                    ok = False
                f.write(json.dumps({"arm": arm, "question_id": r["question_id"],
                                    "relaxed_correct": ok},
                                   ensure_ascii=False) + "\n")
                f.flush()
            # 汇总(含续跑行)
            got = {json.loads(l)["question_id"]: json.loads(l)["relaxed_correct"]
                   for l in open(OUT, encoding="utf-8")
                   if json.loads(l)["arm"] == arm}
            flips = sum(1 for r in wrong if got.get(r["question_id"]))
            orig = sum(1 for r in aff if r.get("judge_correct"))
            n = len(aff)
            res[arm] = (n, orig, flips)
            print(f"{arm:12s} 受影响 {n} 题:原判对 {orig}({orig/n*100:.1f}%) "
                  f"→ 放宽后 {orig+flips}({(orig+flips)/n*100:.1f}%) "
                  f"Δ=+{flips/n*100:.1f}pp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
