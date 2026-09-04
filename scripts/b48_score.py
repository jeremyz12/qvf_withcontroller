# -*- coding: utf-8 -*-
"""批 48 评分(零 API):v51f 两轮读者对 v48f 两轮(批 46d)与 v45(批 33-A)。
准确率、分题型、token、配对 McNemar(精确二项)、144 链簇自助 95% CI、TOST ±3pp。
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
QREF = ROOT / "data/wsc_s5_v25.jsonl"
qs = [json.loads(l) for l in open(QREF, encoding="utf-8") if l.strip()]
QT = {q["qid"]: q["qtype"] for q in qs}; QU = {q["qid"]: q["uid"] for q in qs}; QIDS = set(QT)


def load(path):
    d = {}; tok_in = []; tok_out = []; lat = []; capped = 0
    for l in open(ROOT / path, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l); qid = r.get("question_id") or r.get("qid")
        if qid not in QIDS:
            continue
        d[qid] = bool(r["judge_correct"]); tok_in.append(r.get("usage_input_tokens", 0)); tok_out.append(r.get("usage_output_tokens", 0))
        lat.append(r.get("latency_s", 0)); capped += r.get("stop_reason") == "max_tokens"
    return d, (st.mean(tok_in) if tok_in else 0), (st.mean(tok_out) if tok_out else 0), (st.median(lat) if lat else 0), capped


def acc(d, keys=None):
    keys = keys or list(d)
    return 100 * sum(d[k] for k in keys) / len(keys)


def mcnemar(a, b):
    keys = sorted(set(a) & set(b))
    ao = sum(1 for k in keys if a[k] and not b[k]); bo = sum(1 for k in keys if b[k] and not a[k])
    n = ao + bo
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(ao, bo) + 1)) / 2 ** n)
    return len(keys), ao, bo, p


def cluster_ci(a, b, n_boot=10000, seed=20260904):
    """144 链簇自助:按 uid 重抽,delta = mean(a) - mean(b)(pp)。"""
    keys = sorted(set(a) & set(b))
    by_uid = defaultdict(list)
    for k in keys:
        by_uid[QU[k]].append(k)
    uids = sorted(by_uid); rng = random.Random(seed); deltas = []
    for _ in range(n_boot):
        samp = [uids[rng.randrange(len(uids))] for _ in uids]
        ks = [k for u in samp for k in by_uid[u]]
        deltas.append(100 * (sum(a[k] for k in ks) - sum(b[k] for k in ks)) / len(ks))
    deltas.sort()
    return deltas[int(0.025 * n_boot)], deltas[int(0.975 * n_boot)], deltas[int(0.05 * n_boot)], deltas[int(0.95 * n_boot)]


def report(name, d, ti, to, lat, capped):
    per = " | ".join(f"{t} {acc(d, [k for k in d if QT[k] == t]):.1f}" for t in sorted(set(QT.values())))
    print(f"{name}: n={len(d)} acc={acc(d):.2f} | {per} | in/q {ti:.0f} out/q {to:.0f} $/q {ti/1e6*1+to/1e6*5:.5f} | median lat {lat:.2f}s | capped {capped}")


def main():
    runs = {
        "v51f run1": "results/b48_smoc_v51f_haiku_run1.jsonl",
        "v51f run2": "results/b48_smoc_v51f_haiku_run2.jsonl",
        "v48f run1 (46d)": "results/b46d_smoc_v48f_haiku_run1.jsonl",
        "v48f run2 (46d)": "results/b46d_smoc_v48f_haiku_run2.jsonl",
        "v45 (33-A)": "results/b33A_smoc_v45.jsonl",
        "direct (33-A)": "results/b33A_direct.jsonl",
    }
    D = {}
    for name, p in runs.items():
        try:
            d, ti, to, lat, capped = load(p)
        except FileNotFoundError:
            print(name, "absent:", p); continue
        D[name] = d; report(name, d, ti, to, lat, capped)
    if "v51f run1" in D and "v51f run2" in D:
        a, b = D["v51f run1"], D["v51f run2"]
        same = sum(1 for k in a if k in b and a[k] == b[k])
        print(f"v51f run1 vs run2: identical verdicts {same}/{len(a)}; mean acc {(acc(a)+acc(b))/2:.2f}")
    pairs = [("v51f run1", "v48f run1 (46d)"), ("v51f run2", "v48f run2 (46d)"), ("v51f run1", "v48f run2 (46d)"),
             ("v51f run1", "v45 (33-A)"), ("v51f run2", "v45 (33-A)"), ("v51f run1", "direct (33-A)")]
    for x, y in pairs:
        if x not in D or y not in D:
            continue
        n, ao, bo, p = mcnemar(D[x], D[y]); lo, hi, lo90, hi90 = cluster_ci(D[x], D[y])
        delta = 100 * (ao - bo) / n
        tost = "equivalent (±3pp)" if lo90 > -3 and hi90 < 3 else "not equivalent"
        print(f"{x} vs {y}: n={n} delta={delta:+.2f}pp A-only={ao} B-only={bo} McNemar p={p:.3g} | cluster 95% CI [{lo:+.2f},{hi:+.2f}] | 90% CI [{lo90:+.2f},{hi90:+.2f}] {tost}")


if __name__ == "__main__":
    main()
