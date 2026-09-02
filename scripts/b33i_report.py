# -*- coding: utf-8 -*-
"""批 33-I 汇总:逐格 acc / 配对精确 McNemar / 自助 CI / 逐题成本($0 复算)。"""
from __future__ import annotations
import json, os, statistics as st, sys
sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from b33i_stats import load, compare, sign_p, boot_ci, key  # noqa: E402

P_IN, P_OUT = 1.00, 5.00
J_IN, J_OUT = 5.00, 25.00
EMB = 0.02


def merge(paths):
    seen, rows = set(), []
    for p in paths:
        for r in load(p):
            if r["question_id"] in seen:
                continue
            seen.add(r["question_id"])
            rows.append(r)
    return rows


def cell(tag, rows):
    rows = [r for r in rows if "judge_correct" in r]
    n = len(rows)
    if not n:
        print(f"{tag}: EMPTY"); return
    a = sum(1 for r in rows if r.get("judge_correct"))
    i = sum(r.get("usage_input_tokens", 0) or 0 for r in rows)
    o = sum(r.get("usage_output_tokens", 0) or 0 for r in rows)
    ji = sum(r.get("judge_input_tokens", 0) or 0 for r in rows)
    jo = sum(r.get("judge_output_tokens", 0) or 0 for r in rows)
    rd = i / 1e6 * P_IN + o / 1e6 * P_OUT
    jd = ji / 1e6 * J_IN + jo / 1e6 * J_OUT
    lat = st.mean(r.get("latency_s", 0) or 0 for r in rows)
    print(f"{tag}: n={n} acc={a}/{n}={100*a/n:.2f}% in/q={i/n:.0f} out/q={o/n:.0f} "
          f"read$={rd:.4f} read$/q={rd/n:.5f} judge$={jd:.4f}"
          f"{' (unlogged)' if jd == 0 else ''} lat={lat:.1f}s")


if __name__ == "__main__":
    print("=" * 78)
    print("A. LongMemEval single-session-preference (28/30 uids, 1 q/uid)")
    cell("  smoc  ", load("results/b33i_lme_ssp_smoc.jsonl"))
    cell("  direct", load("results/b33i_lme_ssp_direct.jsonl"))
    compare("  LME-SSP smoc vs direct",
            load("results/b33i_lme_ssp_smoc.jsonl"),
            load("results/b33i_lme_ssp_direct.jsonl"))
    print()
    print("B. MemoryAgentBench-FC mh_6k (100 q)")
    cell("  wt    ", load("results/b33i_mabfc_mh6k_wt.jsonl"))
    cell("  direct", load("results/b33i_mabfc_mh6k_direct.jsonl"))
    compare("  mh_6k wt vs direct",
            load("results/b33i_mabfc_mh6k_wt.jsonl"),
            load("results/b33i_mabfc_mh6k_direct.jsonl"))
    print()
    print("C. MemoryAgentBench-FC mh_32k (100 q)")
    wt32 = merge(["results/b33i_mabfc_mh32k_wt.jsonl",
                  "results/b33i_mabfc_mh32k_wt_p0.jsonl",
                  "results/b33i_mabfc_mh32k_wt_p1.jsonl"])
    cell("  wt    ", wt32)
    cell("  direct", load("results/b33i_mabfc_mh32k_direct.jsonl"))
    compare("  mh_32k wt vs direct", wt32,
            load("results/b33i_mabfc_mh32k_direct.jsonl"))
    print()
    print("D. 建卡成本(usage token 口径)")
    tot = 0.0
    for d in ("results/wt_cards_b33i_lme", "results/wt_cards_b33i_mab"):
        ti = to = 0; n = 0
        for f in sorted(os.listdir(d)):
            c = json.load(open(os.path.join(d, f), encoding="utf-8"))
            ti += c.get("usage_in", 0); to += c.get("usage_out", 0); n += 1
        u = ti / 1e6 * P_IN + to / 1e6 * P_OUT
        tot += u
        print(f"  {d}: n={n} in={ti:,} out={to:,} USD=${u:.4f} per-store=${u/n:.4f}")
    print(f"  build subtotal = ${tot:.4f}")
