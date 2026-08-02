"""Cluster-aware paired bootstrap CIs for QVF benchmark comparisons.

For each (file, test_arm vs base_arm) pair: resample CLUSTERS with replacement
(STALE item / LoCoMo conversation / MemConflict persona / LME question),
recompute the paired accuracy delta on each resample, report the percentile
95% CI plus the exact two-sided sign-test p-value on win/loss pairs.

Usage: python scripts/bootstrap_ci.py [n_boot]
Rerun after new arms land; only rows present in the file are used.
"""

import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

N_BOOT = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
SEED = 20260803

COMPARISONS = [
    ("heldout_stale_ctx16k", "minimal_rules", "dense_direct", "stale"),
    ("heldout_stale_ctx16k", "qvf_v4", "dense_direct", "stale"),
    ("heldout_stale_ctx16k", "dense_recency", "dense_direct", "stale"),
    ("heldout2_stale_ctx16k", "minimal_rules_v5", "dense_direct", "stale"),
    ("heldout2_stale_ctx16k", "extraction_only", "dense_direct", "stale"),
    ("lme_tr_ctx16k", "minimal_rules", "dense_direct", "lme"),
    ("lme_tr_ctx16k", "minimal_rules_v5", "dense_direct", "lme"),
    ("lme_ku_ctx16k", "qvf_v4", "dense_direct", "lme"),
    ("lme_ku_ctx16k", "minimal_rules_v5", "dense_direct", "lme"),
    ("locomo_temporal_ctx16k", "minimal_rules", "dense_direct", "locomo"),
    ("locomo_temporal_ctx16k", "minimal_rules_v5", "dense_direct", "locomo"),
    ("memconflict_ctx16k", "minimal_rules", "dense_direct", "memconflict"),
    ("memconflict_ctx16k", "minimal_rules_v5", "dense_direct", "memconflict"),
]


def cluster_of(qid: str, kind: str) -> str:
    if kind == "stale":
        return qid.split("_dim")[0]
    if kind == "locomo":
        return qid.rsplit("_q", 1)[0]
    if kind == "memconflict":
        return qid.split("_")[0]
    return qid  # lme: question-level


def sign_test_p(w: int, l: int) -> float:
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main() -> int:
    rng = random.Random(SEED)
    base_dir = Path("results")
    print(f"{'file':26s} {'test vs base':38s} {'delta':>7s} {'95% CI':>18s} "
          f"{'W/L/T':>12s} {'p(sign)':>8s} {'clusters':>8s}")
    for fname, test, base, kind in COMPARISONS:
        path = base_dir / f"{fname}.jsonl"
        if not path.exists():
            continue
        by_q: dict = defaultdict(dict)
        for line in path.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in r:
                continue
            if r.get("mode") in (test, base):
                by_q[r["question_id"]][r["mode"]] = bool(r.get("judge_correct"))
        pairs = {q: d for q, d in by_q.items() if test in d and base in d}
        if not pairs:
            continue
        clusters: dict = defaultdict(list)
        for q, d in pairs.items():
            clusters[cluster_of(q, kind)].append((int(d[test]), int(d[base])))
        ckeys = list(clusters)
        w = sum(1 for d in pairs.values() if d[test] and not d[base])
        l = sum(1 for d in pairs.values() if d[base] and not d[test])
        t = len(pairs) - w - l
        obs = (sum(a for c in ckeys for a, _ in clusters[c])
               - sum(b for c in ckeys for _, b in clusters[c])) / len(pairs)
        deltas = []
        for _ in range(N_BOOT):
            sample = [clusters[rng.choice(ckeys)] for _ in ckeys]
            n = sum(len(c) for c in sample)
            if n == 0:
                continue
            deltas.append(
                (sum(a for c in sample for a, _ in c)
                 - sum(b for c in sample for _, b in c)) / n
            )
        deltas.sort()
        lo = deltas[int(0.025 * len(deltas))]
        hi = deltas[int(0.975 * len(deltas))]
        p = sign_test_p(w, l)
        print(f"{fname:26s} {test + ' vs ' + base:38s} {obs:+7.1%} "
              f"[{lo:+6.1%}, {hi:+6.1%}] {w:>4d}/{l}/{t} {p:>8.4f} {len(ckeys):>8d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
