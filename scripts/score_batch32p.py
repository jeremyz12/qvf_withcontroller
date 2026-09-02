# -*- coding: utf-8 -*-
"""批 32′ 评分:A′(corr_longer/corr_tenure,翻转子集,忽视更正机制)
+ B′(写侧归属闸 / 读侧只计本人 vs D vs v2.4,逐题型,干净题不回退)。"""
import glob
import json
import re
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_glob(pat):
    d = {}
    for f in sorted(glob.glob(str(ROOT / pat))):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            d[r["question_id"]] = r
    return d


def acc(d, ks):
    return sum(d[q]["judge_correct"] for q in ks) / len(ks) * 100 if ks else float("nan")


def mcn(A, B, ks):
    b = sum(1 for q in ks if A[q]["judge_correct"] and not B[q]["judge_correct"])
    c = sum(1 for q in ks if not A[q]["judge_correct"] and B[q]["judge_correct"])
    n = b + c
    return b, c, (min(1.0, sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n * 2) if n else 1.0)


def main():
    print("=== 32-A′ 更正题重设计(语料 C,v3C 店)===")
    qs = {q["qid"]: q for q in (json.loads(l) for l in open(ROOT / "data/wsc_v3_corrprime.jsonl", encoding="utf-8"))}
    sC, dC = load_glob("results/b32p_smoc_C_shard*.jsonl"), load_glob("results/b32p_direct_C_shard*.jsonl")
    for t in ("corr_longer", "corr_tenure"):
        ks = [q for q in qs if qs[q]["qtype"] == t and q in sC and q in dC]
        if not ks:
            print(f"  {t:12s} (未完成)"); continue
        b, c, p = mcn(dC, sC, ks)
        maj = Counter(qs[q]["gold"] for q in ks).most_common(1)[0][1] / len(ks) * 100
        print(f"  {t:12s} smoc {acc(sC, ks):5.1f}  direct {acc(dC, ks):5.1f}  Δ {acc(sC, ks)-acc(dC, ks):+5.1f}  p={p:.3g}  多数类 {maj:.1f}  n={len(ks)}")
        # 翻转子集(更正前后金标不同)
        fl = [q for q in ks if (qs[q].get("flip") if t == "corr_longer" else qs[q]["gold"] != qs[q].get("old_gold"))]
        if fl:
            b2, c2, p2 = mcn(dC, sC, fl)
            print(f"     翻转子集 n={len(fl)}: smoc {acc(sC, fl):5.1f}  direct {acc(dC, fl):5.1f}  Δ {acc(sC, fl)-acc(dC, fl):+5.1f}  p={p2:.3g}")
        # 机制:答错者中答"更正前"金标的比例(忽视更正)
        for name, arm in (("smoc", sC), ("direct", dC)):
            wrong = [q for q in ks if not arm[q]["judge_correct"]]
            old = sum(1 for q in wrong if str(qs[q].get("old_gold", "")).lower() and str(qs[q]["old_gold"]).lower() in (arm[q]["answer"] or "").lower())
            print(f"     {name}: 答错 {len(wrong)},其中答了更正前结果 {old}({old/max(1,len(wrong))*100:.0f}%)")

    print("\n=== 32-B′ 归属闸(语料 D)===")
    v24 = {**load_glob("results/b31_smoc_v22_full.jsonl"), **load_glob("results/b31_smoc_v23.jsonl"), **load_glob("results/b31_smoc_v24.jsonl")}
    D = load_glob("results/b32_smoc_D.jsonl")
    gate = load_glob("results/b32p_smoc_Dgate_shard*.jsonl")
    rd = load_glob("results/b32p_smoc_Dread_shard*.jsonl")
    for name, arm in (("D 原店(无闸)", D), ("B′ 写侧闸店", gate), ("B′-read 读侧只计本人", rd)):
        ks = sorted(set(v24) & set(arm))
        if not ks:
            print(f"  {name}: (未完成)"); continue
        b, c, p = mcn(v24, arm, ks)
        bt = defaultdict(lambda: [0, 0])
        for q in ks:
            bt[arm[q]["question_type"]][0] += v24[q]["judge_correct"]; bt[arm[q]["question_type"]][1] += arm[q]["judge_correct"]
        n_t = Counter(arm[q]["question_type"] for q in ks)
        print(f"  {name:22s} v2.4 {acc(v24, ks):5.2f} → {acc(arm, ks):5.2f}  Δ {acc(arm, ks)-acc(v24, ks):+6.2f}  b={b}/c={c} p={p:.3g}  n={len(ks)}")
        print("     逐题型:", "  ".join(f"{t} {a/n_t[t]*100:.0f}→{b_/n_t[t]*100:.0f}" for t, (a, b_) in sorted(bt.items())))
    if gate and D:
        ks = sorted(set(gate) & set(D))
        b, c, p = mcn(D, gate, ks)
        print(f"  闸店 vs 无闸店:{acc(D, ks):.2f} → {acc(gate, ks):.2f}  Δ {acc(gate, ks)-acc(D, ks):+.2f}  b={b}/c={c} p={p:.3g}")
    if rd and gate:
        ks = sorted(set(rd) & set(gate))
        b, c, p = mcn(rd, gate, ks)
        print(f"  写侧闸 vs 读侧只计本人:{acc(rd, ks):.2f} vs {acc(gate, ks):.2f}  Δ(写−读) {acc(gate, ks)-acc(rd, ks):+.2f}  p={p:.3g}")


if __name__ == "__main__":
    main()
