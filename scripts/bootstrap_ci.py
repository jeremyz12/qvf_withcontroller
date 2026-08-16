"""Cluster-aware paired bootstrap CIs and cluster-robust significance for QVF
benchmark comparisons.

For each (test_arm vs base_arm) pair: resample CLUSTERS with replacement
(STALE item / LoCoMo conversation / MemConflict persona / LME question /
WikiState entity), recompute the paired accuracy delta on each resample,
report:
  - naive p: exact two-sided sign test on item-level win/loss pairs
    (treats each question as an independent trial -- ignores that WikiState
    entities contribute ~4 correlated questions each).
  - cluster p: exact two-sided sign test on CLUSTER-level win/loss (one vote
    per cluster, sign of mean(test)-mean(base) within that cluster) -- the
    clustering-robust analogue of the same test.
  - cluster bootstrap 95% CI on the paired accuracy delta (resampling whole
    clusters, not items).
  - n_clusters: effective number of independent units feeding the cluster
    stats (vs n items feeding the naive stat).

Two kinds of comparisons are supported:
  - COMPARISONS: test and base arm share one file, distinguished by `mode`.
  - TWO_FILE_COMPARISONS: test and base arm live in separate files (this is
    the case for every WikiState wt-v3-vs-direct pair -- each arm was run
    into its own results/*.jsonl), matched by `question_id`.

Usage: python scripts/bootstrap_ci.py [n_boot]
Rerun after new arms land; only rows/files present are used.
"""

import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

N_BOOT = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
SEED = 20260803

# (file, test_mode, base_mode, cluster_kind)
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

# WikiState family: test/base arms in separate files, matched by question_id.
# cluster_kind is always "wikistate"; use_uid=True reads the `uid` field
# directly (present in the S5 complex-query files), otherwise the entity id
# is recovered from question_id (format "wiki<PID>-Q<QID>_dimN_..." or
# "wiki<PID>-Q<QID>_s5x" -- split on "_dim" / rsplit is not needed since the
# S5 files carry `uid` explicitly).
# (label, test_file, test_mode, base_file, base_mode, use_uid)
TWO_FILE_COMPARISONS = [
    ("wsc_s5 (complex_arm vs wsc_direct) [flagship: S5 complex-query]",
     "wsc_s5_test_v42", "complex_arm", "wsc_direct_s5_all", "wsc_direct", True),
    ("wiki_P108_w2 (wt_qvf vs dense_direct)",
     "wiki_wtqvf3_P108_w2", "wt_qvf", "wiki_direct_P108_w2", "dense_direct", False),
    ("wiki_P108_ext (wt_qvf vs dense_direct) [flagship: 109-3 p=9e-29 in ledger]",
     "wiki_wtqvf3_P108_ext", "wt_qvf", "wiki_direct_P108_ext", "dense_direct", False),
    ("wiki_P39_ext (wt_qvf vs dense_direct)",
     "wiki_wtqvf3_P39_ext", "wt_qvf", "wiki_direct_P39_ext", "dense_direct", False),
    ("wiki_P54_w2 (wt_qvf vs dense_direct)",
     "wiki_wtqvf3_P54_w2", "wt_qvf", "wiki_direct_P54_w2", "dense_direct", False),
    ("wiki_P54_ext (wt_qvf vs dense_direct)",
     "wiki_wtqvf3_P54_ext", "wt_qvf", "wiki_direct_P54_ext", "dense_direct", False),
    ("wiki_P551 (wt_qvf vs dense_direct)",
     "wiki_wtqvf3_P551", "wt_qvf", "wiki_direct_P551", "dense_direct", False),
    ("newdom_P26 (wt_qvf vs dense_direct)",
     "newdom_wt_P26", "wt_qvf", "newdom_direct_P26", "dense_direct", False),
    ("newdom_P69 (wt_qvf vs dense_direct)",
     "newdom_wt_P69", "wt_qvf", "newdom_direct_P69", "dense_direct", False),
    ("newdom_P1303 (wt_qvf vs dense_direct)",
     "newdom_wt_P1303", "wt_qvf", "newdom_direct_P1303", "dense_direct", False),
]


def cluster_of(qid: str, kind: str, uid: str | None = None) -> str:
    if kind == "stale":
        return qid.split("_dim")[0]
    if kind == "locomo":
        return qid.rsplit("_q", 1)[0]
    if kind == "memconflict":
        return qid.split("_")[0]
    if kind == "wikistate":
        return uid if uid else qid.split("_dim")[0]
    return qid  # lme: question-level


def sign_test_p(w: int, l: int) -> float:
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def cluster_sign_counts(clusters: dict) -> tuple[int, int, int]:
    """One vote per cluster: win/loss/tie by sign of mean(test)-mean(base)."""
    cw = cl = ct = 0
    for items in clusters.values():
        d = sum(a - b for a, b in items) / len(items)
        if d > 0:
            cw += 1
        elif d < 0:
            cl += 1
        else:
            ct += 1
    return cw, cl, ct


def load_single_file_pairs(path: Path, test: str, base: str) -> dict:
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
    return {q: (int(d[test]), int(d[base])) for q, d in by_q.items() if test in d and base in d}


def load_two_file_pairs(test_path: Path, base_path: Path, test_mode: str,
                         base_mode: str, use_uid: bool) -> tuple[dict, dict]:
    test_correct: dict = {}
    test_uid: dict = {}
    for line in test_path.open(encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or r.get("mode") != test_mode:
            continue
        q = r["question_id"]
        test_correct[q] = bool(r.get("judge_correct"))
        if use_uid:
            test_uid[q] = r.get("uid")
    items: dict = {}
    uid_map: dict = {}
    for line in base_path.open(encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or r.get("mode") != base_mode:
            continue
        q = r["question_id"]
        if q not in test_correct:
            continue
        items[q] = (int(test_correct[q]), int(bool(r.get("judge_correct"))))
        if use_uid:
            uid_map[q] = r.get("uid") or test_uid.get(q)
    return items, uid_map


def build_clusters(items: dict, kind: str, uid_map: dict | None = None) -> dict:
    clusters: dict = defaultdict(list)
    for q, pair in items.items():
        uid = uid_map.get(q) if uid_map else None
        clusters[cluster_of(q, kind, uid)].append(pair)
    return clusters


def report(name: str, items: dict, clusters: dict, rng: random.Random, n_boot: int) -> dict | None:
    n = len(items)
    if n == 0:
        return None
    w = sum(1 for a, b in items.values() if a and not b)
    l = sum(1 for a, b in items.values() if b and not a)
    t = n - w - l
    naive_p = sign_test_p(w, l)

    ckeys = list(clusters)
    n_clusters = len(ckeys)
    cw, cl, ct = cluster_sign_counts(clusters)
    cluster_p = sign_test_p(cw, cl)

    obs = (sum(a for c in ckeys for a, _ in clusters[c])
           - sum(b for c in ckeys for _, b in clusters[c])) / n
    deltas = []
    for _ in range(n_boot):
        sample = [clusters[rng.choice(ckeys)] for _ in ckeys]
        m = sum(len(c) for c in sample)
        if m == 0:
            continue
        deltas.append(
            (sum(a for c in sample for a, _ in c)
             - sum(b for c in sample for _, b in c)) / m
        )
    deltas.sort()
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[int(0.975 * len(deltas))]

    return dict(name=name, n=n, n_clusters=n_clusters, delta=obs,
                w=w, l=l, t=t, naive_p=naive_p,
                cw=cw, cl=cl, ct=ct, cluster_p=cluster_p,
                ci_lo=lo, ci_hi=hi)


def print_row(r: dict) -> None:
    print(f"{r['name']:60s} n={r['n']:>5d} clusters={r['n_clusters']:>4d} "
          f"delta={r['delta']:+6.1%} clusterCI=[{r['ci_lo']:+6.1%}, {r['ci_hi']:+6.1%}] "
          f"item W/L/T={r['w']}/{r['l']}/{r['t']} naive_p={r['naive_p']:.3g} "
          f"cluster W/L/T={r['cw']}/{r['cl']}/{r['ct']} cluster_p={r['cluster_p']:.3g}")


def main() -> int:
    rng = random.Random(SEED)
    base_dir = Path("results")
    results = []

    print("=== single-file comparisons (STALE / LME / LoCoMo / MemConflict) ===")
    for fname, test, base, kind in COMPARISONS:
        path = base_dir / f"{fname}.jsonl"
        if not path.exists():
            continue
        items = load_single_file_pairs(path, test, base)
        if not items:
            continue
        clusters = build_clusters(items, kind)
        r = report(f"{fname}: {test} vs {base}", items, clusters, rng, N_BOOT)
        if r is None:
            continue
        results.append(r)
        print_row(r)

    print("\n=== WikiState family (two-file comparisons, entity clusters) ===")
    for label, test_file, test_mode, base_file, base_mode, use_uid in TWO_FILE_COMPARISONS:
        test_path = base_dir / f"{test_file}.jsonl"
        base_path = base_dir / f"{base_file}.jsonl"
        if not test_path.exists() or not base_path.exists():
            print(f"[skip] missing file for {label}: {test_path} / {base_path}")
            continue
        items, uid_map = load_two_file_pairs(test_path, base_path, test_mode, base_mode, use_uid)
        if not items:
            print(f"[skip] no overlapping question_ids for {label}")
            continue
        clusters = build_clusters(items, "wikistate", uid_map)
        r = report(label, items, clusters, rng, N_BOOT)
        if r is None:
            continue
        results.append(r)
        print_row(r)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
