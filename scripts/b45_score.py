# -*- coding: utf-8 -*-
"""批 45 记分器:OpenAI 族(gpt-5-mini)复判 vs 归档 Claude 族(opus-5)判官。

预注册:results/opt_batch45_prereg.md。
McNemar 精确二项符号检验函数与 scripts/b33A_score.py 的 sign_p 同源。

用法: PYTHONUTF8=1 python scripts/b45_score.py > results/b45_score_out.txt
"""
from __future__ import annotations

import json
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
P_IN, P_OUT = 0.25, 2.00  # gpt-5-mini $/M, per results/ladder_decontamination_20260902.md

ARMS = [
    ("direct", "results/b33A_direct.jsonl"),
    ("smoc_v45", "results/b33A_smoc_v45.jsonl"),
    ("smw", "results/b33A_smw.jsonl"),
    ("smwplain", "results/b33A_smwplain.jsonl"),
]


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def load_orig(path):
    d = {}
    for line in open(ROOT / path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "error" in r:
            continue
        q = r["question_id"]
        if q not in d:  # keep first occurrence, matches b33A_score.py
            d[q] = r
    return d


def load_rejudge(arm):
    d = {}
    tin = tout = 0
    for line in open(ROOT / f"results/b45_rejudge_{arm}.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        d[r["question_id"]] = r
        u = r.get("usage") or {}
        tin += u.get("input_tokens") or 0
        tout += u.get("output_tokens") or 0
    return d, tin, tout


def kappa(pairs):
    """pairs: list of (claude_bool, gpt_bool)."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(1 for c, g in pairs if c == g) / n
    pc_true = sum(1 for c, _ in pairs if c) / n
    pg_true = sum(1 for _, g in pairs if g) / n
    pe = pc_true * pg_true + (1 - pc_true) * (1 - pg_true)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def main():
    orig = {n: load_orig(p) for n, p in ARMS}
    rej = {}
    usage_totals = {}
    for n, _ in ARMS:
        d, tin, tout = load_rejudge(n)
        rej[n] = d
        usage_totals[n] = (tin, tout)

    print("# Batch 45 score: OpenAI-family (gpt-5-mini) re-judge vs archived "
          "Claude-family (opus-5) judge\n")
    print("Pre-registration: results/opt_batch45_prereg.md\n")

    # ---- 0. integrity check ----
    print("## 0. Row-count / qid-set integrity\n")
    print("| arm | orig rows | rejudge rows | qid symdiff | fallback_gpt |")
    print("|---|---|---|---|---|")
    for n, _ in ARMS:
        o, r = orig[n], rej[n]
        symdiff = len(set(o) ^ set(r))
        fb = sum(1 for v in r.values() if v["judge_reason_gpt"].startswith("FALLBACK"))
        print(f"| {n} | {len(o)} | {len(r)} | {symdiff} | {fb} |")

    # ---- 1. per-arm accuracy under each judge ----
    print("\n## 1. Per-arm accuracy under each judge (n=576 each)\n")
    print("| arm | claude acc | gpt acc | delta (gpt-claude) |")
    print("|---|---|---|---|")
    arm_acc = {}
    for n, _ in ARMS:
        r = rej[n]
        qids = sorted(r)
        ca = sum(r[q]["judge_correct_claude"] for q in qids) / len(qids) * 100
        ga = sum(r[q]["judge_correct_gpt"] for q in qids) / len(qids) * 100
        arm_acc[n] = (ca, ga)
        print(f"| {n} | {ca:.2f} | {ga:.2f} | {ga-ca:+.2f} |")

    # ---- 2. per-row agreement + kappa ----
    print("\n## 2. Per-row agreement and Cohen's kappa\n")
    print("| arm | agree | n | agreement% | kappa |")
    print("|---|---|---|---|---|")
    arm_agree = {}
    for n, _ in ARMS:
        r = rej[n]
        pairs = [(r[q]["judge_correct_claude"], r[q]["judge_correct_gpt"]) for q in r]
        agree = sum(1 for c, g in pairs if c == g)
        pct = agree / len(pairs) * 100
        k = kappa(pairs)
        arm_agree[n] = pct
        print(f"| {n} | {agree} | {len(pairs)} | {pct:.2f}% | {k:.3f} |")

    # ---- 3. disagreement direction + examples ----
    print("\n## 3. Disagreement counts by direction + 10 examples per arm\n")
    for n, path in ARMS:
        r = rej[n]
        o = orig[n]
        claude_right_gpt_wrong = []  # claude=True, gpt=False
        claude_wrong_gpt_right = []  # claude=False, gpt=True
        for q, v in r.items():
            c, g = v["judge_correct_claude"], v["judge_correct_gpt"]
            if c and not g:
                claude_right_gpt_wrong.append(q)
            elif (not c) and g:
                claude_wrong_gpt_right.append(q)
        print(f"### {n}")
        print(f"claude=correct & gpt=incorrect: {len(claude_right_gpt_wrong)}  |  "
              f"claude=incorrect & gpt=correct: {len(claude_wrong_gpt_right)}\n")
        examples = (claude_right_gpt_wrong[:5] + claude_wrong_gpt_right[:5])
        if examples:
            print("| question_id | qtype | claude_correct | gpt_correct | gold | answer(trunc) | claude_reason(trunc) | gpt_reason(trunc) |")
            print("|---|---|---|---|---|---|---|---|")
            for q in examples:
                v = r[q]
                orow = o.get(q, {})
                ans = str(orow.get("answer", ""))[:80].replace("|", "/").replace("\n", " ")
                gold = str(orow.get("gold_answer", ""))[:40].replace("|", "/")
                creas = str(orow.get("judge_reason", ""))[:80].replace("|", "/").replace("\n", " ")
                greas = str(v.get("judge_reason_gpt", ""))[:80].replace("|", "/").replace("\n", " ")
                print(f"| {q} | {orow.get('question_type','')} | {v['judge_correct_claude']} | "
                      f"{v['judge_correct_gpt']} | {gold} | {ans} | {creas} | {greas} |")
        print()

    # ---- 4. per-question-type agreement ----
    print("## 4. Per-question-type agreement\n")
    print("| arm | qtype | n | agreement% |")
    print("|---|---|---|---|")
    for n, _ in ARMS:
        r = rej[n]
        o = orig[n]
        by_type = defaultdict(list)
        for q, v in r.items():
            qt = o.get(q, {}).get("question_type", "?")
            by_type[qt].append(v["judge_correct_claude"] == v["judge_correct_gpt"])
        for qt in sorted(by_type):
            vals = by_type[qt]
            print(f"| {n} | {qt} | {len(vals)} | {sum(vals)/len(vals)*100:.2f}% |")

    # ---- 5. re-judged ladder deltas under gpt judge ----
    print("\n## 5. Re-judged ladder deltas under gpt judge (McNemar exact sign test)\n")

    def mcnemar_delta(name_a, name_b, key="judge_correct_gpt"):
        ra, rb = rej[name_a], rej[name_b]
        qids = sorted(set(ra) & set(rb))
        acc_a = sum(ra[q][key] for q in qids) / len(qids) * 100
        acc_b = sum(rb[q][key] for q in qids) / len(qids) * 100
        delta = acc_b - acc_a
        b = sum(1 for q in qids if ra[q][key] and not rb[q][key])  # a right, b wrong
        c = sum(1 for q in qids if not ra[q][key] and rb[q][key])  # a wrong, b right
        p = sign_p(b, c)
        print(f"### {name_b} - {name_a}  (gpt judge)")
        print(f"  n={len(qids)} | {name_a} acc={acc_a:.2f} | {name_b} acc={acc_b:.2f} | "
              f"delta={delta:+.2f}pp  b/c={b}/{c}  McNemar p={p:.3g}\n")
        return delta

    d_smoc_direct = mcnemar_delta("direct", "smoc_v45")
    d_smw_smwplain = mcnemar_delta("smwplain", "smw")
    d_smoc_smw = mcnemar_delta("smw", "smoc_v45")

    # ---- 6. H1-H3 outcomes ----
    print("## 6. H1-H3 pre-registered outcomes\n")
    h1_pass = {n: arm_agree[n] >= 90.0 for n, _ in ARMS}
    print("### H1: per-row agreement >= 90% per arm")
    for n, _ in ARMS:
        print(f"  {n}: {arm_agree[n]:.2f}% -> {'PASS' if h1_pass[n] else 'FAIL'}")
    h1_overall = all(h1_pass.values())
    print(f"  H1 overall: {'PASS' if h1_overall else 'FAIL'}\n")

    claude_headline = 41.49
    h2_pass = abs(d_smoc_direct - claude_headline) <= 5.0
    print("### H2: smoc-direct delta under gpt judge within +-5pp of Claude-judge "
          f"headline (+{claude_headline}pp)")
    print(f"  gpt-judge delta = {d_smoc_direct:+.2f}pp | "
          f"|delta - {claude_headline}| = {abs(d_smoc_direct-claude_headline):.2f}pp -> "
          f"{'PASS' if h2_pass else 'FAIL'}\n")

    print("### H3: no arm's accuracy moves by more than 5pp (gpt vs claude judge, same rows)")
    h3_pass = {}
    for n, _ in ARMS:
        ca, ga = arm_acc[n]
        move = abs(ga - ca)
        h3_pass[n] = move <= 5.0
        print(f"  {n}: claude={ca:.2f} gpt={ga:.2f} move={move:.2f}pp -> "
              f"{'PASS' if h3_pass[n] else 'FAIL'}")
    h3_overall = all(h3_pass.values())
    print(f"  H3 overall: {'PASS' if h3_overall else 'FAIL'}\n")

    # ---- 7. cost ----
    print("## 7. Cost (gpt-5-mini judge, $0.25/M in $2.00/M out)\n")
    print("| arm | in tok | out tok | $ |")
    print("|---|---|---|---|")
    tot_in = tot_out = 0.0
    for n, _ in ARMS:
        tin, tout = usage_totals[n]
        tot_in += tin
        tot_out += tout
        cost = tin / 1e6 * P_IN + tout / 1e6 * P_OUT
        print(f"| {n} | {tin} | {tout} | ${cost:.4f} |")
    total_cost = tot_in / 1e6 * P_IN + tot_out / 1e6 * P_OUT
    print(f"| **total** | {int(tot_in)} | {int(tot_out)} | **${total_cost:.4f}** |")


if __name__ == "__main__":
    main()
