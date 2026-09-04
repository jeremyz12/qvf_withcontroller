# -*- coding: utf-8 -*-
"""批 46b 记分器 —— 104K 规模上 render-only / render-raw(复刻批 44)vs
归档的槽位投影(61.7)/全账目(54.2)/dense_top100(38.3)/haiku 全文(7.5)。

预注册:results/opt_batch46b_prereg.md。方法论:
- 去重/acc/McNemar 逐字复用 scripts/b33A_score.py;
- Wilson 95% CI 逐字复用 scripts/b39_score.py;
- 30 店级簇自助 CI:N=10000, seed=20260904(prereg §6)。

用法: PYTHONUTF8=1 python scripts/b46b_score.py > results/b46b_score_out.txt
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p  # noqa: E402

N_BOOT, SEED = 10000, 20260904
P_IN, P_OUT = 1.00, 5.00          # haiku 读者口径(与批 39/44 一致)
J_IN, J_OUT = 5.00, 25.00         # claude-opus-5 判官官方 list price
QREF_PATH = "data/wsc_long_L1_questions.jsonl"
DATA_PATH = "data/wikistate_long_L2_b33.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]

NEW_ARMS = [
    ("render-only", "results/b46b_renderonly_L2.jsonl"),
    ("render-raw",  "results/b46b_renderraw_L2.jsonl"),
]

# 归档参照臂(批 39/33-D 头条口径,不重跑,直接复用)
REFS = [
    ("projection (archived, 61.7)", ["results/b33d_slot_L2_new20.jsonl",
                                     "results/b33_smoc_L2probe_slot.jsonl"]),
    ("ledger (archived, 54.2)", ["results/b33d_smoc_L2_new20.jsonl",
                                 "results/b33d_smoc_L2_old10_repro.jsonl"]),
    ("dense_top100 (archived, 38.3)", ["results/b39_dense_top100_L2.jsonl"]),
    ("haiku fulltext (archived, 7.5)", ["results/b33d_full_haiku_L2_new15.jsonl",
                                        "results/b27_full_haiku_L2.jsonl"]),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def load_many(paths):
    out = {}
    for p in paths:
        for q, r in load(p).items():
            out.setdefault(q, r)
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, (c - h) * 100), min(1.0, c + h) * 100)


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def compare(label, base, test, boot=True):
    """base = 参照/前者,test = 被比较臂;delta = test - base。"""
    keys = sorted(set(base) & set(test))
    if not keys:
        print("### " + label + ": no overlap")
        return None
    b = sum(1 for q in keys if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in keys if not base[q]["judge_correct"] and test[q]["judge_correct"])
    delta = (sum(bool(test[q]["judge_correct"]) for q in keys)
             - sum(bool(base[q]["judge_correct"]) for q in keys)) / len(keys) * 100
    clusters = defaultdict(list)
    for q in keys:
        uid = test[q].get("uid") or base[q].get("uid") or q.split("_")[0]
        clusters[uid].append((int(bool(test[q]["judge_correct"])),
                              int(bool(base[q]["judge_correct"]))))
    print("### " + label)
    print("  n=%d q / %d stores | delta=%+.2fpp  b/c=%d/%d  McNemar p=%.4g"
          % (len(keys), len(clusters), delta, b, c, sign_p(b, c)))
    if not boot:
        return delta
    random.seed(SEED)
    ks = list(clusters)
    ds = []
    for _ in range(N_BOOT):
        samp = [clusters[random.choice(ks)] for _ in ks]
        num = sum(x - y for it in samp for x, y in it)
        den = sum(len(it) for it in samp)
        ds.append(num / den * 100)
    ds.sort()
    lo, hi = ds[int(.025 * N_BOOT)], ds[int(.975 * N_BOOT)]
    cw = sum(1 for it in clusters.values() if sum(x - y for x, y in it) > 0)
    cl = sum(1 for it in clusters.values() if sum(x - y for x, y in it) < 0)
    ct = len(clusters) - cw - cl
    print("  store sign test %dW/%dL/%dT p=%.4g | cluster boot 95%% CI "
          "[%+.2f,%+.2f]pp (N=%d, seed=%d)"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi, N_BOOT, SEED))
    return delta


def cost_row(d):
    rows = list(d.values())
    mi = st.mean(r.get("usage_input_tokens") or 0 for r in rows)
    mo = st.mean(r.get("usage_output_tokens") or 0 for r in rows)
    dpq = mi / 1e6 * P_IN + mo / 1e6 * P_OUT
    mji = st.mean(r.get("judge_input_tokens") or 0 for r in rows)
    mjo = st.mean(r.get("judge_output_tokens") or 0 for r in rows)
    jpq = mji / 1e6 * J_IN + mjo / 1e6 * J_OUT
    return mi, mo, dpq, mji, mjo, jpq


def main() -> int:
    qs = [json.loads(l) for l in open(ROOT / QREF_PATH, encoding="utf-8") if l.strip()]
    qref = {q["qid"] for q in qs}
    entries = {e["uid"]: e for e in
               json.loads((ROOT / DATA_PATH).read_text(encoding="utf-8"))}

    refs = {name: restrict(load_many(paths), qref) for name, paths in REFS}
    data = {}
    for name, path in NEW_ARMS:
        p = ROOT / path
        data[name] = restrict(load(path), qref) if p.exists() else {}

    print("# Batch 46b score -- write-time cards at 104K scale "
          "(render-only / render-raw vs archived projection/ledger/RAG/fulltext)")
    print("# corpus %s | questions %s (30 stores x 4 qtypes = 120 q)"
          % (DATA_PATH, QREF_PATH))
    print("# reader claude-haiku-4-5 (max_tokens 800, temperature 0) | "
          "judge qvf.judge.ClaudeJudge (claude-opus-5, frozen)")
    print("# cards: results/wt_cards_b33_L2 (20 stores) + "
          "results/wt_cards_b27_L2 (10 stores), read-only, same store as "
          "batch 33-D/39/40")
    print("# archived reference arms: results/opt_batch39_verdict.md headline "
          "table (not rerun)\n")

    print("## 0. Row ledger\n")
    print("| arm | rows loaded | qid symdiff vs the 120 | status |")
    print("|---|---|---|---|")
    for name, _ in REFS:
        d = refs[name]
        print("| %s | %d | %d | %s |"
              % (name, len(d), len(set(d) ^ qref),
                 "PASS(subset)" if set(d) <= qref else "MISMATCH"))
    for name, _ in NEW_ARMS:
        d = data[name]
        print("| %s | %d | %d | %s |"
              % (name, len(d), len(set(d) ^ qref),
                 "PASS(exact 120)" if set(d) == qref else "MISMATCH"))

    print("\n## 1. Headline accuracy (Wilson 95% CI) + cost/tokens/rendered rows\n")
    print("| arm | n | acc % | Wilson 95% | mean rendered_rows | mean in tok | "
          "mean out tok | reader $/q | judge $/q | median latency s |")
    print("|---|---|---|---|---|---|---|---|---|---|")

    def line(name, d):
        n = len(d)
        k = sum(1 for r in d.values() if r.get("judge_correct"))
        lo, hi = wilson(k, n)
        rows = list(d.values())
        rr = [r.get("rendered_rows") for r in rows if r.get("rendered_rows") is not None]
        mr = ("%.2f" % st.mean(rr)) if rr else "n/a"
        mi, mo, dpq, mji, mjo, jpq = cost_row(d)
        lat = st.median([r.get("latency_s") or 0 for r in rows])
        print("| %s | %d | %.2f | [%.1f, %.1f] | %s | %.0f | %.0f | $%.4f | "
              "$%.4f | %.2f |"
              % (name, n, k / max(1, n) * 100, lo, hi, mr, mi, mo, dpq, jpq, lat))

    for name, _ in REFS:
        line(name, refs[name])
    for name, _ in NEW_ARMS:
        line(name, data[name])

    print("\n## 2. Accuracy by question type (%% correct; n=30 each)\n")
    print("| arm | " + " | ".join(TYPES) + " |")
    print("|---|" + "---|" * len(TYPES))
    for name, d in [(n, refs[n]) for n, _ in REFS] + \
            [(n, data[n]) for n, _ in NEW_ARMS]:
        cells = ["-" if by_type(d, t) is None else "%.1f" % by_type(d, t)
                 for t in TYPES]
        print("| %s | %s |" % (name, " | ".join(cells)))

    print("\n## 3. Selection-tier / capping breakdown (render-only / render-raw)\n")
    for name, _ in NEW_ARMS:
        d = data[name]
        if not d:
            continue
        tiers = defaultdict(lambda: [0, 0])
        for r in d.values():
            t = r.get("selection_tier", "?")
            tiers[t][0] += 1
            tiers[t][1] += bool(r.get("judge_correct"))
        print("### " + name)
        for t, (cnt, ok) in sorted(tiers.items()):
            print("  %-24s n=%-4d acc=%.1f%%" % (t, cnt, ok / max(1, cnt) * 100))
        if name == "render-raw":
            dropped = [r.get("renderraw_rows_dropped", 0) for r in d.values()]
            capped_n = sum(1 for x in dropped if x > 0)
            print("  rows dropped for budget cap: %d/%d questions capped, "
                  "total rows dropped=%d" % (capped_n, len(d), sum(dropped)))
        print()

    print("\n## 4. Paired comparisons (render-only / render-raw vs each other "
          "+ vs archived arms), 30-store cluster bootstrap\n")
    ro, rr = data["render-only"], data["render-raw"]
    pairs = [
        ("render-only vs render-raw", rr, ro),
        ("render-only vs projection 61.7", refs["projection (archived, 61.7)"], ro),
        ("render-only vs ledger 54.2", refs["ledger (archived, 54.2)"], ro),
        ("render-raw vs projection 61.7", refs["projection (archived, 61.7)"], rr),
        ("render-raw vs ledger 54.2", refs["ledger (archived, 54.2)"], rr),
        ("render-only vs dense_top100 38.3", refs["dense_top100 (archived, 38.3)"], ro),
        ("render-raw vs dense_top100 38.3", refs["dense_top100 (archived, 38.3)"], rr),
        ("render-only vs haiku fulltext 7.5", refs["haiku fulltext (archived, 7.5)"], ro),
        ("render-raw vs haiku fulltext 7.5", refs["haiku fulltext (archived, 7.5)"], rr),
    ]
    deltas = {}
    for label, base, test in pairs:
        if not base or not test:
            print("### " + label + ": missing\n")
            continue
        deltas[label] = compare(label, base, test)
        print()

    print("\n## 5. Cost ledger (measured tokens, this batch's two new arms only)\n")
    print("| arm | reader in | reader out | reader $ ($1/$5) | judge in | "
          "judge out | judge $ (opus-5 $5/$25) |")
    print("|---|---|---|---|---|---|---|")
    tot = [0] * 4
    for name, _ in NEW_ARMS:
        d = data[name].values()
        ti = sum(r.get("usage_input_tokens") or 0 for r in d)
        to = sum(r.get("usage_output_tokens") or 0 for r in d)
        ji = sum(r.get("judge_input_tokens") or 0 for r in d)
        jo = sum(r.get("judge_output_tokens") or 0 for r in d)
        for i, x in enumerate((ti, to, ji, jo)):
            tot[i] += x
        print("| %s | %d | %d | $%.3f | %d | %d | $%.3f |"
              % (name, ti, to, ti / 1e6 * P_IN + to / 1e6 * P_OUT, ji, jo,
                 ji / 1e6 * J_IN + jo / 1e6 * J_OUT))
    print("| **TOTAL** | %d | %d | $%.3f | %d | %d | $%.3f |"
          % (tot[0], tot[1], tot[0] / 1e6 * P_IN + tot[1] / 1e6 * P_OUT,
             tot[2], tot[3], tot[2] / 1e6 * J_IN + tot[3] / 1e6 * J_OUT))
    print("\nReader spend cap was $6 (judge separate); actual reader spend "
          "= $%.3f (%.1f%% of cap)."
          % (tot[0] / 1e6 * P_IN + tot[1] / 1e6 * P_OUT,
             (tot[0] / 1e6 * P_IN + tot[1] / 1e6 * P_OUT) / 6.0 * 100))

    print("\n## 6. Hypothesis verdicts (thresholds fixed in prereg, not "
          "adjusted post hoc)\n")
    a_ro, a_rr = acc(ro), acc(rr)
    a_proj, a_ledger = 61.67, 54.17
    print("acc(render-only)=%.2f  acc(render-raw)=%.2f  "
          "[archived] projection=%.2f  ledger=%.2f\n" % (a_ro, a_rr, a_proj, a_ledger))

    h1_gap = a_proj - a_rr
    print("H1 (render-raw collapses at 104K): projection(%.2f) - "
          "acc(render-raw)(%.2f) = %+.2fpp vs threshold >=+15pp -> %s"
          % (a_proj, a_rr, h1_gap, "CONFIRMED" if h1_gap >= 15.0 else "REJECTED"))

    mi_ro, mo_ro, _, _, _, _ = cost_row(ro)
    mi_rr, mo_rr, _, _, _, _ = cost_row(rr)
    rows_ro = [r.get("rendered_rows") or 0 for r in ro.values()]
    rows_rr = [r.get("rendered_rows") or 0 for r in rr.values()]
    mean_rows_ro = st.mean(rows_ro)
    mean_rows_rr = st.mean(rows_rr)
    tok_ratio = mi_rr / 8800.0
    rows_ratio_vs_ro = mean_rows_rr / max(1e-9, mean_rows_ro)
    h2_tok = mi_rr >= 2 * 8800.0
    h2_rows = mean_rows_rr >= 2 * mean_rows_ro
    print("\nH2 (render-raw rows+tokens blow up):")
    print("  token sub-test: mean(render-raw in tok)=%.0f vs 2x8800=17600 "
          "-> ratio=%.2fx -> %s"
          % (mi_rr, tok_ratio, "CONFIRMED" if h2_tok else "REJECTED"))
    print("  rows sub-test:  mean(render-raw rows)=%.2f vs 2x mean(render-only "
          "rows)=%.2f (=%.2f) -> ratio=%.2fx -> %s"
          % (mean_rows_rr, mean_rows_ro, 2 * mean_rows_ro, rows_ratio_vs_ro,
             "CONFIRMED" if h2_rows else "REJECTED"))
    print("  H2 overall (both sub-tests must hold): %s"
          % ("CONFIRMED" if (h2_tok and h2_rows) else "REJECTED"))

    h3_gap = abs(a_ro - a_ledger)
    print("\nH3 (render-only stays within 5pp of full ledger at scale): "
          "|acc(render-only)(%.2f) - ledger(%.2f)| = %.2fpp vs threshold <=5pp "
          "-> %s"
          % (a_ro, a_ledger, h3_gap, "CONFIRMED" if h3_gap <= 5.0 else "REJECTED"))
    print("  [context] render-only vs projection(%.2f): %+.2fpp (not the H3 "
          "comparator, reported per prereg note on the L2 ranking reversal)"
          % (a_proj, a_ro - a_proj))

    print("\n## 7. Per-store correct-count distribution (of 4 questions each)\n")
    print("| arm | 0 | 1 | 2 | 3 | 4 |")
    print("|---|---|---|---|---|---|")
    for name, d in [(n, refs[n]) for n, _ in REFS] + \
            [(n, data[n]) for n, _ in NEW_ARMS]:
        cnt = defaultdict(int)
        per = defaultdict(int)
        for r in d.values():
            per[r["uid"]] += int(bool(r.get("judge_correct")))
        for u in per:
            cnt[per[u]] += 1
        print("| %s | %d | %d | %d | %d | %d |"
              % (name, cnt[0], cnt[1], cnt[2], cnt[3], cnt[4]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
