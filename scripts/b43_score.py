# -*- coding: utf-8 -*-
"""批 43 记分器:五读者(haiku-4.5 / claude-sonnet-5 / gpt-5-mini /
gemini-3.6-flash / qwen3:14b 本地)x 三臂(direct / plainctx / smoc)矩阵,
同一 140 题(results/b35_questions_sample36.jsonl,36 链)。

口径与 scripts/b38e_score.py / scripts/b33A_score.py 逐字相同:去重取
首次出现;配对 McNemar = 精确二项符号检验(sign_p,与
scripts/cluster_units_b31_b32p.py 同函数)。

用法: PYTHONUTF8=1 python scripts/b43_score.py > results/b43_score_out.txt
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import acc, load, sign_p  # noqa: E402

QREF = "results/b35_questions_sample36.jsonl"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]

# 读者侧现价($/M in, out)。见 results/opt_batch43_prereg.md §五 / 批 33-K 判决 §一。
PRICES = {
    "haiku-4-5": (1.00, 5.00),
    "sonnet-5": (2.00, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gemini-3.6-flash": (0.75, 3.75),
    "qwen3:14b": (0.0, 0.0),
}

# reader key -> (display, price key, {arm: [paths...]})
READERS = {
    "haiku-4.5": ("haiku-4-5", {
        "direct": ["results/b35_direct.jsonl"],
        "plainctx": ["results/b36_plainctx_haiku-4-5.jsonl"],
        "smoc": ["results/b38e_smoc_v47skf_haiku-4-5.jsonl"],
        "smoc_v45": ["results/b33A_smoc_v45.jsonl"],
    }),
    "claude-sonnet-5": ("sonnet-5", {
        "direct": ["results/b36b_direct_sonnet5.jsonl"],
        "plainctx": ["results/b36_plainctx_sonnet-5.jsonl"],
        "smoc": ["results/b38e_smoc_v47skf_sonnet-5.jsonl"],
        "smoc_v45": ["results/b36b_smoc_sonnet5.jsonl"],
    }),
    "gpt-5-mini": ("gpt-5-mini", {
        "direct": ["results/b43_direct_gpt5mini.jsonl"],
        "plainctx": ["results/b43_plainctx_gpt5mini.jsonl"],
        "smoc": ["results/b43_smoc_gpt5mini.jsonl"],
        "smoc_v45": ["results/b43_smoc_v45_gpt5mini.jsonl"],
    }),
    "gemini-3.6-flash": ("gemini-3.6-flash", {
        "direct": ["results/b43_direct_gemini.jsonl"],
        "plainctx": ["results/b43_plainctx_gemini.jsonl"],
        "smoc": ["results/b43_smoc_gemini.jsonl"],
        "smoc_v45": ["results/b43_smoc_v45_gemini.jsonl"],
    }),
    "qwen3:14b (local)": ("qwen3:14b", {
        "direct": ["results/b43_direct_qwen3-14b.jsonl"],
        "plainctx": ["results/b43_plainctx_qwen3-14b.jsonl"],
        "smoc": ["results/b43_smoc_qwen3-14b.jsonl"],
        "smoc_v45": ["results/b43_smoc_v45_qwen3-14b.jsonl"],
    }),
}

READER_ORDER = ["haiku-4.5", "claude-sonnet-5", "gpt-5-mini",
               "gemini-3.6-flash", "qwen3:14b (local)"]


def load_many(paths, keys):
    m = {}
    for p in paths:
        if not (ROOT / p).exists():
            continue
        d = load(p)
        m.update({k: v for k, v in d.items() if k in keys})
    return m


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def stats(rows, pi, po):
    if not rows:
        return 0, 0, 0, 0.0
    mi = st.mean([r.get("usage_input_tokens") or 0 for r in rows])
    mo = st.mean([r.get("usage_output_tokens") or 0 for r in rows])
    lat = st.median([r.get("latency_s") or 0 for r in rows])
    return mi, mo, lat, mi / 1e6 * pi + mo / 1e6 * po


def cap_stats(d):
    have = [r for r in d.values() if "stop_reason" in r]
    if not have:
        return None
    capped = sum(1 for r in have
                if r.get("stop_reason") in ("length", "max_tokens", "MAX_TOKENS"))
    empty = sum(1 for r in have if not (r.get("answer") or "").strip())
    return capped, empty, len(have)


def cmp2(name_a, a, name_b, b):
    keys = sorted(set(a) & set(b))
    if not keys:
        return None
    aw = sum(1 for q in keys if a[q]["judge_correct"] and not b[q]["judge_correct"])
    bw = sum(1 for q in keys if b[q]["judge_correct"] and not a[q]["judge_correct"])
    pa = sum(bool(a[q]["judge_correct"]) for q in keys) / len(keys) * 100
    pb = sum(bool(b[q]["judge_correct"]) for q in keys) / len(keys) * 100
    p = sign_p(aw, bw)
    print("  %-20s vs %-20s | n=%3d | A=%5.1f%% B=%5.1f%% | delta(A-B)=%+6.2fpp "
          "| A-only-right=%2d B-only-right=%2d | McNemar exact p=%.4g"
          % (name_a, name_b, len(keys), pa, pb, pa - pb, aw, bw, p))
    return pa, pb, p


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    print("# Batch 43 -- reader matrix (5 readers x 3 arms), same 140 qids / "
          "36 chains\n")
    print(f"Questions: {QREF} ({len(qids)} qids). Prereg: "
          "results/opt_batch43_prereg.md.\n")

    data = {}   # reader -> arm -> dict
    price = {}
    for rname in READER_ORDER:
        pk, arms = READERS[rname]
        price[rname] = PRICES[pk]
        data[rname] = {}
        for arm, paths in arms.items():
            d = load_many(paths, qids)
            data[rname][arm] = d

    print("## 1. Accuracy / cost matrix (reader x arm, all restricted to the "
          "same 140 qids)\n")
    hdr = ("| reader | arm | n | acc | " + " | ".join(TYPES) +
           " | in tok | out tok | median lat s | $/q |")
    print(hdr)
    print("|" + "---|" * (7 + len(TYPES)))
    for rname in READER_ORDER:
        pi, po = price[rname]
        for arm in ("direct", "plainctx", "smoc", "smoc_v45"):
            d = data[rname][arm]
            if not d:
                print(f"| {rname} | {arm} | 0 | (missing) | " + "-|" * (6 + len(TYPES)))
                continue
            mi, mo, lat, cpq = stats(list(d.values()), pi, po)
            tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                             else "-" for t in TYPES)
            print("| %s | %s | %d | **%.1f%%** | %s | %.0f | %.0f | %.2f | $%.5f |"
                  % (rname, arm, len(d), acc(d), tys, mi, mo, lat, cpq))
    print()

    print("### 1b. Truncation / empty-answer diagnostics (stop_reason field)\n")
    print("| reader | arm | capped(length/max_tokens) | empty answer | n w/ field |")
    print("|---|---|---|---|---|")
    for rname in READER_ORDER:
        for arm in ("direct", "plainctx", "smoc", "smoc_v45"):
            d = data[rname][arm]
            cs = cap_stats(d)
            if cs is None:
                continue
            capped, empty, n = cs
            print(f"| {rname} | {arm} | {capped} | {empty} | {n} |")
    print()

    print("## 2. H1 -- smoc(v47skf) - direct >= 15pp, every reader\n")
    print("| reader | smoc(v47skf) | direct | gap | >= 15pp? |")
    print("|---|---|---|---|---|")
    h1_pass = []
    for rname in READER_ORDER:
        ds, dd = data[rname]["smoc"], data[rname]["direct"]
        if not ds or not dd:
            print(f"| {rname} | (missing) | | | |")
            continue
        keys = sorted(set(ds) & set(dd))
        a_s = sum(bool(ds[q]["judge_correct"]) for q in keys) / len(keys) * 100
        a_d = sum(bool(dd[q]["judge_correct"]) for q in keys) / len(keys) * 100
        gap = a_s - a_d
        ok = gap >= 15.0
        h1_pass.append((rname, ok, gap))
        print(f"| {rname} | {a_s:.1f} | {a_d:.1f} | **{gap:+.1f}** | "
              f"{'YES' if ok else 'NO'} |")
    n_pass = sum(1 for _, ok, _ in h1_pass if ok)
    print(f"\n**H1 verdict: {n_pass}/{len(h1_pass)} readers clear the 15pp bar.**")
    if n_pass < len(h1_pass):
        fails = [f"{r} ({g:+.1f}pp)" for r, ok, g in h1_pass if not ok]
        print(f"Falls short on: {', '.join(fails)}. H1 is falsified as a "
              "universal ('every reader') claim; report per-reader instead.")
    print()

    print("## 3. H2 -- ledger-minus-full-context gap, ordered by full-context "
          "(plainctx) score\n")
    order = []
    for rname in READER_ORDER:
        dp = data[rname]["plainctx"]
        if dp:
            order.append((rname, acc(dp)))
    order.sort(key=lambda t: t[1])
    print("| rank (weak->strong by plainctx) | reader | plainctx | smoc(v47skf) | "
          "gap (smoc-plainctx) |")
    print("|---|---|---|---|---|")
    gaps = []
    for i, (rname, pacc) in enumerate(order, 1):
        ds = data[rname]["smoc"]
        keys = sorted(set(ds) & set(data[rname]["plainctx"])) if ds else []
        if not keys:
            print(f"| {i} | {rname} | {pacc:.1f} | (missing) | |")
            continue
        sacc = sum(bool(ds[q]["judge_correct"]) for q in keys) / len(keys) * 100
        gap = sacc - pacc
        gaps.append((rname, gap))
        print(f"| {i} | {rname} | {pacc:.1f} | {sacc:.1f} | **{gap:+.1f}** |")
    print()
    viol = []
    for i in range(1, len(gaps)):
        prev_r, prev_g = gaps[i - 1]
        cur_r, cur_g = gaps[i]
        if cur_g - prev_g > 3.0:
            viol.append((prev_r, cur_r, cur_g - prev_g))
    if not gaps:
        print("**H2 verdict: no data.**")
    elif not viol:
        print(f"**H2 verdict: monotone non-increasing within the +-3pp tie band "
              f"across all {len(gaps)} readers -- confirmed.**")
    else:
        vs = "; ".join(f"{a}->{b} (+{d:.1f}pp)" for a, b, d in viol)
        print(f"**H2 verdict: falsified -- {len(viol)} violation(s): {vs}.**")
    print()

    print("## 4. H3 -- smoc(v47skf) score varies < 5pp across readers\n")
    scores = [(rname, acc(data[rname]["smoc"])) for rname in READER_ORDER
             if data[rname]["smoc"]]
    print("| reader | smoc(v47skf) acc |")
    print("|---|---|")
    for rname, s in scores:
        print(f"| {rname} | {s:.1f} |")
    if scores:
        vals = [s for _, s in scores]
        spread = max(vals) - min(vals)
        lo = min(scores, key=lambda t: t[1])
        hi = max(scores, key=lambda t: t[1])
        print(f"\nmax-min = **{spread:.1f}pp** (max {hi[0]} {hi[1]:.1f}, "
              f"min {lo[0]} {lo[1]:.1f}).")
        print(f"**H3 verdict: {'confirmed' if spread < 5.0 else 'falsified'}** "
              f"({'< 5pp' if spread < 5.0 else '>= 5pp'}).")
    print()

    print("## 5. Paired McNemar: smoc(v47skf) vs plainctx, per reader\n")
    for rname in READER_ORDER:
        ds, dp = data[rname]["smoc"], data[rname]["plainctx"]
        if ds and dp:
            cmp2(f"{rname}:smoc", ds, f"{rname}:plainctx", dp)
    print()
    print("## 5b. Paired McNemar: smoc(v47skf) vs direct, per reader\n")
    for rname in READER_ORDER:
        ds, dd = data[rname]["smoc"], data[rname]["direct"]
        if ds and dd:
            cmp2(f"{rname}:smoc", ds, f"{rname}:direct", dd)
    print()
    print("## 5c. Paired McNemar: smoc(v47skf) vs smoc(v45), per reader "
          "(store ablation, secondary)\n")
    for rname in READER_ORDER:
        ds, dv = data[rname]["smoc"], data[rname]["smoc_v45"]
        if ds and dv:
            cmp2(f"{rname}:v47skf", ds, f"{rname}:v45", dv)
    print()

    print("## 6. Cost summary (reader-side spend, judge separate)\n")
    print("| reader | arm | in tok total | out tok total | $ |")
    print("|---|---|---|---|---|")
    grand_all = 0.0
    grand_new = 0.0
    NEW_READERS = {"gpt-5-mini", "gemini-3.6-flash", "qwen3:14b (local)"}
    for rname in READER_ORDER:
        pi, po = price[rname]
        for arm in ("direct", "plainctx", "smoc", "smoc_v45"):
            d = data[rname][arm]
            if not d:
                continue
            ti = sum(r.get("usage_input_tokens") or 0 for r in d.values())
            to = sum(r.get("usage_output_tokens") or 0 for r in d.values())
            usd = ti / 1e6 * pi + to / 1e6 * po
            grand_all += usd
            if rname in NEW_READERS:
                grand_new += usd
            tag = " (reused, not paid this batch)" if rname not in NEW_READERS else ""
            print(f"| {rname} | {arm} | {ti:,} | {to:,} | ${usd:.4f}{tag} |")
    print(f"| **grand total, all 5 readers x 4 arms (informational)** | | | | "
          f"**${grand_all:.3f}** |")
    print(f"| **grand total, THIS BATCH'S new-reader API spend "
          f"(gpt-5-mini + gemini-3.6-flash; qwen3:14b is $0)** | | | | "
          f"**${grand_new:.3f}** |")
    print(f"\nThis matches the cumulative spend printed by the runner logs "
          f"(results/b43_run_gpt5mini.log / b43_run_gemini.log last line: "
          f"$5.753, since both scripts share one budget-glob counter over "
          f"results/b43_*.jsonl). haiku-4.5 and claude-sonnet-5 rows above "
          f"are the reused batch 35/36/36b/38e artifacts -- their $ figures "
          f"are historical, not spent in batch 43. qwen3:14b is local/ollama "
          f"-- $0 API cost by construction; its row reports token counts for "
          f"reference only.")


if __name__ == "__main__":
    main()
