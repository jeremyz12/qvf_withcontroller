# -*- coding: utf-8 -*-
"""Oracle upper-bound decomposition: 100% - policy_acc = routing_loss + arm_cap_gap.

Reads results/router_learned_triples_20260814.jsonl (produced by
scripts/train_router.py; frozen artifact, read-only) and, purely from the
per-question {arms: {correct, tok}, v42_pick/v42_correct, phat_cv} fields
already archived there, recomputes independently (zero LLM calls):

  - oracle_acc   = mean(any arm correct)                         [ceiling any
                    routing policy could ever reach on this arm set]
  - handwritten  = mean(v42_correct)                              [v4.2 hand-
                    written router, archived pick]
  - learned(lam) = mean(correct of argmax_a[phat_cv[a] - lam*(tok_a/T_ref)])
                    reproducing train_router.py's actual-cost policy exactly,
                    for every lambda in the same LAMBDA_GRID it swept.

Decomposition per policy:
  100% - policy_acc = (100% - oracle_acc)     "arm capability gap"
                      + (oracle_acc - policy_acc)  "routing loss"

T_ref is recomputed here (mean tok over all archived arm-rows) and cross-
checked against the 7445 figure printed in router_learned_report_20260814.md
section 1; a mismatch is flagged rather than silently trusted.

Usage: python scripts/redteam_oracle_decomp.py
Output: prints the decomposition table to stdout (results/
redteam_cluster_attribution_20260816.md embeds this table by hand from the
printed output, so numbers there are traceable to this script's run).
"""
import json
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
TRIPLES = ROOT / "results" / "router_learned_triples_20260814.jsonl"
ARMS = ["direct", "rt", "wt", "prompt"]
LAMBDA_GRID = [0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05,
               0.08, 0.12, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0]
REPORT_TREF = 7445.0  # from results/router_learned_report_20260814.md §1


def load():
    rows = []
    for line in TRIPLES.open(encoding="utf-8"):
        rows.append(json.loads(line))
    return rows


def policy_pick(arms, phat, lam, tref):
    best, bs = None, -1e18
    for a, meta in arms.items():
        c = meta["tok"] / tref
        s = phat[a] - lam * c
        if s > bs:
            bs, best = s, a
    return best


def main():
    rows = load()
    n = len(rows)

    all_toks = [m["tok"] for r in rows for m in r["arms"].values()]
    tref = sum(all_toks) / len(all_toks)
    print(f"n={n} triples={len(all_toks)} T_ref(recomputed)={tref:.1f} "
          f"T_ref(report)={REPORT_TREF} match={abs(tref - REPORT_TREF) < 1.0}")

    oracle_acc = sum(1 for r in rows if any(m["correct"] for m in r["arms"].values())) / n
    v42_acc = sum(1 for r in rows if r["v42_correct"]) / n
    print(f"oracle_acc={oracle_acc*100:.2f}% handwritten(v42)_acc={v42_acc*100:.2f}%")
    print(f"arm_capability_gap (100% - oracle) = {(1-oracle_acc)*100:.2f}pp  <- fixed, policy-independent")
    print()

    def row_for(label, acc):
        routing_loss = oracle_acc - acc
        arm_gap = 1 - oracle_acc
        total_gap = 1 - acc
        check = abs((routing_loss + arm_gap) - total_gap) < 1e-9
        return dict(label=label, acc=acc, routing_loss=routing_loss,
                    arm_gap=arm_gap, total_gap=total_gap, check=check)

    results = [row_for("handwritten(v4.2)", v42_acc)]
    for lam in LAMBDA_GRID:
        accs = []
        for r in rows:
            a = policy_pick(r["arms"], r["phat_cv"], lam, tref)
            accs.append(1 if r["arms"][a]["correct"] else 0)
        acc = sum(accs) / n
        results.append(row_for(f"learned(lam={lam})", acc))

    print(f"{'policy':28s} {'acc':>8s} {'100-acc':>9s} {'routing_loss':>13s} "
          f"{'arm_cap_gap':>12s} {'sum_check':>10s}")
    for r in results:
        print(f"{r['label']:28s} {r['acc']*100:7.2f}% {r['total_gap']*100:8.2f}pp "
              f"{r['routing_loss']*100:12.2f}pp {r['arm_gap']*100:11.2f}pp "
              f"{'OK' if r['check'] else 'MISMATCH':>10s}")


if __name__ == "__main__":
    main()
