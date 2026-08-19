# -*- coding: utf-8 -*-
"""scripts/crossjudge_s5_twin.py — 判官交叉审计:gpt-5-mini 重判分层抽样。

预注册:results/crossjudge_s5_twin_prereg.md(提交 6654f4c,先于本文件运行)。
沿用 scripts/cross_judge_generic.py 的判官管线(同 JUDGE_SYSTEM_PROMPT、同解析)。
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

from openai import OpenAI
from qvf.judge import JUDGE_SYSTEM_PROMPT

ROOT = Path(r"D:\ZZL_cluade")
OUT = ROOT / "results/crossjudge_s5_twin.jsonl"

ARMS = {
    "s5_direct":  "results/wsc_direct_s5_all_b1_union.jsonl",
    "s5_filter":  "results/wsc_s5_filter_only.jsonl",
    "s5_compile": "results/wsc_s5_test_v42b1_union.jsonl",
    "twinR_direct": "results/twinC_repl_direct.jsonl",
    "twinR_wtmf":   "results/twinC_repl_wt_mf.jsonl",
    "twinS_direct": "results/twinC_set_direct.jsonl",
    "twinS_setsem": "results/twinC_set_compile_setsem.jsonl",
}


def pick(rows, k):
    rows = sorted(rows, key=lambda r: r["question_id"])
    n = len(rows)
    return [rows[i * n // k] for i in range(min(k, n))]


def sample():
    out = []
    for arm, path in ARMS.items():
        rows = [json.loads(l) for l in open(ROOT / path, encoding="utf-8")]
        rows = [r for r in rows if r.get("answer")]
        if arm.startswith("s5"):
            for qt in sorted({r.get("question_type") for r in rows}):
                out += [(arm, r) for r in pick(
                    [r for r in rows if r.get("question_type") == qt], 13)]
        else:
            out += [(arm, r) for r in pick(rows, 25)]
    return out


def main() -> int:
    todo = sample()
    print(f"sampled {len(todo)} rows", file=sys.stderr)
    client = OpenAI()
    done = set()
    if OUT.exists():
        for l in open(OUT, encoding="utf-8"):
            try:
                d = json.loads(l)
                done.add((d["arm"], d["question_id"]))
            except Exception:
                pass
    with OUT.open("a", encoding="utf-8") as f:
        for i, (arm, r) in enumerate(todo):
            if (arm, r["question_id"]) in done:
                continue
            user = (f"QUESTION: {r['question']}\n\n"
                    f"GOLD ANSWER: {r['gold_answer']}\n\n"
                    f"MODEL RESPONSE: {r.get('answer','')}\n\n"
                    f"QUESTION TYPE: {r.get('question_type')}\n"
                    "ABSTENTION QUESTION: no\n\n"
                    "Reply with ONLY a JSON object: "
                    '{"correct": true/false, "reason": "<one sentence>"}')
            try:
                resp = client.chat.completions.create(
                    model="gpt-5-mini", max_completion_tokens=2048,
                    messages=[{"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                              {"role": "user", "content": user}])
                text = resp.choices[0].message.content or ""
                v = json.loads(text[text.index("{"):text.rindex("}") + 1])
                f.write(json.dumps({
                    "arm": arm, "question_id": r["question_id"],
                    "qtype": r.get("question_type"),
                    "claude_correct": bool(r.get("judge_correct")),
                    "gpt_correct": bool(v.get("correct")),
                    "gpt_reason": str(v.get("reason", ""))[:200]},
                    ensure_ascii=False) + "\n")
            except Exception as e:  # noqa: BLE001
                f.write(json.dumps({"arm": arm, "question_id": r["question_id"],
                                    "error": str(e)[:200]}) + "\n")
            f.flush()
            if (i + 1) % 40 == 0:
                print(f"{i+1}/{len(todo)}", file=sys.stderr)

    # ── 分析 ──
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")
            if "error" not in l]
    def binom2(k, n):
        if n == 0:
            return float("nan")
        tail = sum(comb(n, x) for x in range(0, min(k, n - k) + 1)) / 2 ** n
        return min(1.0, 2 * tail)
    print("\n| 臂 | n | 一致率 | claude对gpt错 | claude错gpt对 | flip binomial p |")
    print("|---|---|---|---|---|---|")
    for arm in ARMS:
        sub = [r for r in rows if r["arm"] == arm]
        if not sub:
            continue
        ag = sum(1 for r in sub if r["claude_correct"] == r["gpt_correct"])
        cw = sum(1 for r in sub if r["claude_correct"] and not r["gpt_correct"])
        cl = sum(1 for r in sub if not r["claude_correct"] and r["gpt_correct"])
        print(f"| {arm} | {len(sub)} | {ag/len(sub)*100:.1f}% | {cw} | {cl} | "
              f"{binom2(min(cw, cl), cw + cl):.3g} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
