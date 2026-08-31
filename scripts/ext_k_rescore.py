# -*- coding: utf-8 -*-
"""批 29-K:条件完整度 K 移植——对既有 STALE/COND 外场答案做三档重判。

用法: python scripts/ext_k_rescore.py
产物: results/ext_k_rescore_20260831.jsonl + 汇总(C/P/F/K 双臂 + 配对)。
"""
from __future__ import annotations

import json
import re
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

STALE_SYS = (
    "You grade an assistant answer about a user's CURRENT situation, given "
    "the user's OLD statement and NEW statement (the new one supersedes the "
    "old). Grades: complete = the answer correctly reflects the current "
    "state (consistent with the NEW statement) AND explicitly acknowledges "
    "that the situation changed or references the earlier state; partial = "
    "correctly reflects the current state but never acknowledges the change "
    "or the earlier state; failed = asserts the outdated state as current, "
    "answers as if a false premise were true, or is wrong/evasive. Return "
    'JSON only: {"grade": "complete|partial|failed", "reasoning": "..."}')
COND_SYS = (
    "You grade an assistant answer against a gold answer that has a "
    "CONDITIONAL structure (different values under different conditions, "
    "e.g. contexts, times, or branches). Grades: complete = the answer "
    "reproduces the full conditional structure: the condition(s) and the "
    "value(s) for every branch present in the gold; partial = states "
    "correct value(s) but drops or garbles the condition, or covers only "
    "one branch; failed = contradicts the gold or is wrong/evasive. Return "
    'JSON only: {"grade": "complete|partial|failed", "reasoning": "..."}')


def judge(system: str, user: str) -> str:
    from openai import OpenAI
    cli = judge._c = getattr(judge, "_c", None) or OpenAI()
    for _ in range(3):
        r = cli.chat.completions.create(
            model="gpt-5-mini", max_completion_tokens=2000,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        m = re.search(r"(complete|partial|failed)",
                      r.choices[0].message.content or "")
        if m:
            return m.group(1)
    return "failed"


def stale_map():
    src = json.load(open(ROOT / "data/stale_T1_T2_400_FULL.json",
                         encoding="utf-8"))
    m = {}
    for it in src:
        for q in it["probing_queries"].values():
            m[" ".join(q.split())] = (it["M_old"], it["M_new"])
    return m


def mcnemar(a: dict, b: dict) -> float:
    qs = sorted(set(a) & set(b))
    x = sum(1 for q in qs if a[q] == "complete" and b[q] != "complete")
    y = sum(1 for q in qs if a[q] != "complete" and b[q] == "complete")
    n = x + y
    if not n:
        return 1.0
    return min(1.0, sum(comb(n, i) for i in range(min(x, y) + 1)) / 2 ** n * 2)


def main() -> int:
    outp = ROOT / "results/ext_k_rescore_20260831.jsonl"
    done = {(json.loads(l)["file"], json.loads(l)["question_id"])
            for l in open(outp, encoding="utf-8")} if outp.exists() else set()
    fh = open(outp, "a", encoding="utf-8")
    smap = stale_map()
    jobs = [
        ("stale", "smoc", "results/ext_stale_smoc_b19.rejudged.jsonl"),
        ("stale", "direct", "results/ext_stale_direct_b19.rejudged.jsonl"),
        ("cond", "smoc", "results/ext_memconflict_smoc_b20_cond.jsonl"),
        ("cond", "direct", "results/ext_memconflict_direct_b20.jsonl"),
        ("stale", "smoc_cite", "results/ext_stale_smoc_b19_cite.jsonl"),
        ("cond", "smoc_cite",
         "results/ext_memconflict_smoc_b20_cond_cite.jsonl"),
    ]
    jobs = [(k, a, p) for k, a, p in jobs if (ROOT / p).exists()]
    grades = {}
    unmatched = 0
    for kind, arm, path in jobs:
        g = grades.setdefault((kind, arm), {})
        for line in open(ROOT / path, encoding="utf-8"):
            r = json.loads(line)
            qid = r["question_id"]
            if (path, qid) in done:
                continue
            if kind == "stale":
                key = " ".join(r["question"].split())
                if key not in smap:
                    unmatched += 1
                    continue
                old, new = smap[key]
                user = (f"Question: {r['question']}\nOLD statement: {old}\n"
                        f"NEW statement: {new}\nAnswer: {r['answer']}")
                grade = judge(STALE_SYS, user)
            else:
                user = (f"Question: {r['question']}\nGold (conditional): "
                        f"{r['gold_answer']}\nAnswer: {r['answer']}")
                grade = judge(COND_SYS, user)
            fh.write(json.dumps({"file": path, "kind": kind, "arm": arm,
                                 "question_id": qid, "grade": grade},
                                ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{kind}/{arm}] {qid} {grade}", flush=True)
    for l in open(outp, encoding="utf-8"):
        r = json.loads(l)
        grades.setdefault((r["kind"], r["arm"]), {})[r["question_id"]] = \
            r["grade"]
    print(f"\n未回连 STALE 行: {unmatched}")
    for kind in ("stale", "cond"):
        for arm in ("smoc", "direct", "smoc_cite"):
            g = grades.get((kind, arm), {})
            n = len(g)
            c = sum(1 for v in g.values() if v == "complete") / max(n, 1) * 100
            p = sum(1 for v in g.values() if v == "partial") / max(n, 1) * 100
            f = sum(1 for v in g.values() if v == "failed") / max(n, 1) * 100
            k = c / max(c + p, 1e-9) * 100
            print(f"{kind:5s} {arm:6s} n={n} C={c:.1f} P={p:.1f} F={f:.1f} "
                  f"K={k:.1f}")
        for a in ("smoc", "smoc_cite"):
            pv = mcnemar(grades.get((kind, a), {}),
                         grades.get((kind, "direct"), {}))
            print(f"{kind:5s} {a}-vs-direct complete 配对 McNemar p={pv:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
