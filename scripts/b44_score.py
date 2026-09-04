# -*- coding: utf-8 -*-
"""批 44 记分器 —— render-matched 控制臂 vs smoc/smw/smwplain 拆分。

预注册:results/opt_batch44_prereg.md。方法论逐字复用
scripts/b33A_score.py 的 McNemar + 144 链簇自助 CI(N=10000, seed=20260902)。
比较范围限定在 data/wsc_s5_v25.jsonl 的 560 个 question_id(33-A 的
576 题源里这 560 个是真子集,比较前把 33-A 的四个臂过滤到这 560 个 id)。

用法: PYTHONUTF8=1 python scripts/b44_score.py > results/b44_score_out.txt
"""
from __future__ import annotations

import json
import random
import statistics as st
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
N_BOOT = 10000
SEED = 20260902

QREF = {json.loads(l)["qid"] for l in
        open(ROOT / "data/wsc_s5_v25.jsonl", encoding="utf-8") if l.strip()}

ARMS = [
    ("smoc",       "results/b33A_smoc_v45.jsonl",   True),
    ("smw",        "results/b33A_smw.jsonl",        True),
    ("smwplain",   "results/b33A_smwplain.jsonl",   True),
    ("direct",     "results/b33A_direct.jsonl",     True),
    ("renderonly", "results/b44_renderonly.jsonl",  False),
    ("renderraw",  "results/b44_renderraw.jsonl",   False),
]


def load(path, restrict560):
    d = {}
    p = ROOT / path
    if not p.exists():
        return d
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "error" in r:
            continue
        q = r["question_id"]
        if restrict560 and q not in QREF:
            continue
        if q in d:  # keep first (concurrent-write dedupe, same rule as 33-A)
            continue
        d[q] = r
    return d


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def acc(d, keys=None):
    rows = [d[k] for k in (keys if keys is not None else d)]
    return sum(1 for r in rows if r.get("judge_correct")) / max(1, len(rows)) * 100


def compare(label, base, test):
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
    print("### " + label)
    print("  n=%d ti / %d lian | delta=%+.2fpp  b/c=%d/%d  McNemar p=%.3g"
          % (len(keys), len(clusters), delta, b, c, sign_p(b, c)))
    print("  chain sign test %dW/%dL/%dT p=%.3g | cluster boot 95%% CI [%+.2f,%+.2f]pp"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi))
    return delta


def main():
    data = {n: load(p, restrict) for n, p, restrict in ARMS}

    print("# Batch 44 score — render-matched control vs smoc/smw/smwplain "
          "(reader claude-haiku-4-5 / judge = 33-A)\n")

    print("## 0. Row counts + qid-set check vs data/wsc_s5_v25.jsonl (560)\n")
    print("| arm | rows loaded | symdiff vs 560 | status |")
    print("|---|---|---|---|")
    for n, _, _ in ARMS:
        d = data[n]
        sd = len(set(d) ^ QREF) if n in ("renderonly", "renderraw") else "n/a(supset)"
        status = "PASS" if (n in ("renderonly", "renderraw") and set(d) == QREF) \
            else ("PASS(subset)" if n not in ("renderonly", "renderraw")
                  and set(d) <= QREF else "-")
        print("| %s | %d | %s | %s |" % (n, len(d), sd, status))

    print("\n## 1. Headline accuracy (560 q)\n")
    print("| arm | n | accuracy |")
    print("|---|---|---|")
    for n, _, _ in ARMS:
        d = data[n]
        if d:
            print("| %s | %d | %.2f |" % (n, len(d), acc(d)))

    print("\n## 2. Cost / tokens / rendered rows\n")
    print("| arm | mean in tok | mean out tok | mean rendered_rows | median latency s |")
    print("|---|---|---|---|---|")
    for n, _, _ in ARMS:
        d = data[n]
        if not d:
            continue
        rows = list(d.values())
        mi = st.mean(r.get("usage_input_tokens") or 0 for r in rows)
        mo = st.mean(r.get("usage_output_tokens") or 0 for r in rows)
        rr = [r.get("rendered_rows") for r in rows if r.get("rendered_rows") is not None]
        mr = ("%.2f" % st.mean(rr)) if rr else "n/a"
        lat = st.median(r.get("latency_s") or 0 for r in rows)
        print("| %s | %.0f | %.0f | %s | %.2f |" % (n, mi, mo, mr, lat))

    print("\n## 3. Per question type\n")
    types = sorted({r.get("question_type") for d in data.values()
                    for r in d.values() if r.get("question_type")})
    print("| arm | " + " | ".join(types) + " |")
    print("|---" * (len(types) + 1) + "|")
    for n, _, _ in ARMS:
        d = data[n]
        if not d:
            continue
        cells = []
        for t in types:
            rs = [r for r in d.values() if r.get("question_type") == t]
            cells.append("%.1f" % (sum(1 for r in rs if r["judge_correct"])
                                   / max(1, len(rs)) * 100) if rs else "-")
        print("| %s | " % n + " | ".join(cells) + " |")

    print("\n## 4. Selection-tier breakdown (renderonly / renderraw)\n")
    for n in ("renderonly", "renderraw"):
        d = data[n]
        if not d:
            continue
        tiers = defaultdict(lambda: [0, 0])
        for r in d.values():
            t = r.get("selection_tier", "?")
            tiers[t][0] += 1
            tiers[t][1] += bool(r.get("judge_correct"))
        print("### " + n)
        for t, (cnt, ok) in sorted(tiers.items()):
            print("  %-16s n=%-4d acc=%.1f%%" % (t, cnt, ok / max(1, cnt) * 100))
        print()

    print("\n## 5. Paired comparisons (task-specified four pairs + auxiliary)\n")
    pairs = [
        ("smoc vs render-only", "smoc", "renderonly"),
        ("render-only vs smwplain", "smwplain", "renderonly"),
        ("render-only vs smw", "smw", "renderonly"),
        ("render-raw vs smwplain", "smwplain", "renderraw"),
        ("[aux] smoc vs render-raw", "smoc", "renderraw"),
        ("[aux] render-only vs render-raw", "renderonly", "renderraw"),
        ("[aux] smoc vs smwplain (total gap)", "smwplain", "smoc"),
    ]
    deltas = {}
    for label, b, t in pairs:
        if not data[b] or not data[t]:
            print("### " + label + ": missing\n")
            continue
        deltas[(b, t)] = compare(label, data[b], data[t])
        print()

    print("\n## 6. Decomposition: layout share vs mechanism share\n")
    print("overall (560 q):")
    a_smoc, a_ro, a_swp, a_smw, a_rr = (acc(data["smoc"]), acc(data["renderonly"]),
                                        acc(data["smwplain"]), acc(data["smw"]),
                                        acc(data["renderraw"]))
    layout = a_ro - a_swp
    mech = a_smoc - a_ro
    total = a_smoc - a_swp
    print("  acc(smwplain)=%.2f  acc(render-only)=%.2f  acc(smoc)=%.2f"
          % (a_swp, a_ro, a_smoc))
    print("  layout share (render-only - smwplain)   = %+.2fpp" % layout)
    print("  mechanism share (smoc - render-only)     = %+.2fpp" % mech)
    print("  total (smoc - smwplain)                  = %+.2fpp "
          "(check: layout+mech = %+.2fpp)" % (total, layout + mech))
    print("  [context] acc(render-raw)=%.2f  acc(smw)=%.2f" % (a_rr, a_smw))

    print("\nper question type:")
    print("| qtype | smwplain | render-raw | render-only | smoc | layout(ro-swp) "
          "| mechanism(smoc-ro) | total(smoc-swp) |")
    print("|---|---|---|---|---|---|---|---|")
    per_type_gap = {}
    for t in types:
        def acc_t(d):
            rs = [r for r in d.values() if r.get("question_type") == t]
            return (sum(1 for r in rs if r["judge_correct"]) / max(1, len(rs)) * 100,
                    len(rs))
        a_swp_t, _ = acc_t(data["smwplain"])
        a_rr_t, _ = acc_t(data["renderraw"])
        a_ro_t, _ = acc_t(data["renderonly"])
        a_smoc_t, _ = acc_t(data["smoc"])
        lay_t = a_ro_t - a_swp_t
        mech_t = a_smoc_t - a_ro_t
        tot_t = a_smoc_t - a_swp_t
        per_type_gap[t] = mech_t
        print("| %s | %.1f | %.1f | %.1f | %.1f | %+.1f | %+.1f | %+.1f |"
              % (t, a_swp_t, a_rr_t, a_ro_t, a_smoc_t, lay_t, mech_t, tot_t))

    print("\n## 7. Hypothesis verdicts (thresholds fixed in prereg, not adjusted post hoc)\n")
    h1_delta = deltas.get(("smoc", "renderonly")) if False else (a_smoc - a_ro)
    print("H1 (mechanism share exists): acc(smoc)-acc(render-only) = %+.2fpp "
          "vs threshold >=+5pp -> %s"
          % (h1_delta, "CONFIRMED" if h1_delta >= 5.0 else "REJECTED"))
    h2_delta = a_ro - a_swp
    print("H2 (layout share exists): acc(render-only)-acc(smwplain) = %+.2fpp "
          "vs threshold >=+10pp -> %s"
          % (h2_delta, "CONFIRMED" if h2_delta >= 10.0 else "REJECTED"))
    cc_ratio = per_type_gap.get("change_count", 0.0)
    cb_ratio = per_type_gap.get("count_before", 0.0)
    fvl_ratio = per_type_gap.get("first_vs_last", 0.0)
    lt_ratio = per_type_gap.get("longest_tenure", 0.0)
    count_mean = st.mean([v for k, v in [("cc", cc_ratio), ("cb", cb_ratio)]])
    other_mean = st.mean([v for k, v in [("fvl", fvl_ratio), ("lt", lt_ratio)]])
    h3 = (count_mean - other_mean) >= 5.0
    print("H3 (mechanism gap concentrated in change_count/count_before): "
          "mean(change_count,count_before)=%+.2fpp vs mean(first_vs_last,"
          "longest_tenure)=%+.2fpp, diff=%+.2fpp vs threshold >=+5pp -> %s"
          % (count_mean, other_mean, count_mean - other_mean,
             "CONFIRMED" if h3 else "REJECTED"))


if __name__ == "__main__":
    main()
