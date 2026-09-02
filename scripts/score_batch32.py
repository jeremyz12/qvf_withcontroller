# -*- coding: utf-8 -*-
"""批 32 评分:新题型(语料 C)双臂 + 第三人称干扰(语料 D)vs v2.4 基线。"""
import json
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(p):
    p = ROOT / p
    if not p.exists():
        return {}
    return {json.loads(l)["question_id"]: json.loads(l)
            for l in open(p, encoding="utf-8")}


def acc(d, ks):
    return sum(d[q]["judge_correct"] for q in ks) / len(ks) * 100 if ks else float("nan")


def mcn(A, B, ks):
    b = sum(1 for q in ks if A[q]["judge_correct"] and not B[q]["judge_correct"])
    c = sum(1 for q in ks if not A[q]["judge_correct"] and B[q]["judge_correct"])
    n = b + c
    p = min(1.0, sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n * 2) if n else 1.0
    return b, c, p


def main():
    print("=== 32-A 新题型(语料 C)===")
    sC, dC = load("results/b32_smoc_C.jsonl"), load("results/b32_direct_C.jsonl")
    qs = [json.loads(l) for l in open(ROOT / "data/wsc_v3_new.jsonl", encoding="utf-8")]
    maj = {t: Counter(q["gold"] for q in qs if q["qtype"] == t).most_common(1)[0][1] / 144 * 100
           for t in ("correction_date", "correction_count", "scoped_count")}
    for t in ("correction_date", "correction_count", "scoped_count"):
        ks = [q["qid"] for q in qs if q["qtype"] == t and q["qid"] in sC and q["qid"] in dC]
        if not ks:
            print(f"  {t:17s} (未完成)  多数类基线 {maj[t]:.1f}")
            continue
        b, c, p = mcn(dC, sC, ks)
        print(f"  {t:17s} smoc {acc(sC, ks):5.1f}  direct {acc(dC, ks):5.1f}  "
              f"Δ {acc(sC, ks) - acc(dC, ks):+5.1f}  p={p:.3g}  多数类基线 {maj[t]:.1f}  n={len(ks)}")
    allk = [q["qid"] for q in qs if q["qid"] in sC and q["qid"] in dC]
    if allk:
        print(f"  {'ALL 432':17s} smoc {acc(sC, allk):5.1f}  direct {acc(dC, allk):5.1f}")

    print("\n=== 32-B 第三人称干扰(语料 D)vs v2.4 ===")
    sD, dD = load("results/b32_smoc_D.jsonl"), load("results/b32_direct_D.jsonl")
    s24 = {**load("results/b31_smoc_v22_full.jsonl"), **load("results/b31_smoc_v23.jsonl"),
           **load("results/b31_smoc_v24.jsonl")}
    d24 = {**load("results/b31_direct_v21.jsonl"), **load("results/b31_direct_v22_rest.jsonl")}
    for name, base, new in (("smoc", s24, sD), ("direct", d24, dD)):
        ks = sorted(set(base) & set(new))
        if not ks:
            print(f"  {name}: (未完成)")
            continue
        b, c, p = mcn(base, new, ks)
        print(f"  {name:6s} v2.4 {acc(base, ks):5.2f} → D {acc(new, ks):5.2f}  "
              f"Δ {acc(new, ks) - acc(base, ks):+5.2f}  b={b}/c={c} p={p:.3g}  n={len(ks)}")
        bt = defaultdict(lambda: [0, 0, 0])
        for q in ks:
            t = new[q]["question_type"]
            bt[t][0] += base[q]["judge_correct"]; bt[t][1] += new[q]["judge_correct"]; bt[t][2] += 1
        print("     逐题型:", "  ".join(f"{t} {a/n*100:.0f}→{b_/n*100:.0f}" for t, (a, b_, n) in sorted(bt.items())))


if __name__ == "__main__":
    main()
