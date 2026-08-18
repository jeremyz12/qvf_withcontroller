# -*- coding: utf-8 -*-
"""armdom.cli — `armdom audit <logs.jsonl>`。"""
from __future__ import annotations

import argparse
import json
import sys

from .audit import audit
from .fit import fit_from_logs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="armdom")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="audit a multi-arm log")
    a.add_argument("logs")
    a.add_argument("--seeds", type=int, default=20)
    a.add_argument("--folds", type=int, default=2)
    a.add_argument("--token-weight", type=float, default=0.5,
                   help="score = acc_pp - w * tok/1000. A policy choice, not an estimate.")
    a.add_argument("--drop-arm", action="append", default=[],
                   help="ask 'what if I deleted this arm?'; repeatable")
    a.add_argument("--chain", default=None, help="e.g. word3>word2>wh")
    a.add_argument("--emit", default=None)
    a.add_argument("--metric", choices=["score", "acc", "tok"], default=None,
                   help="print one number only (for CI / iteration loops)")
    f = sub.add_parser("fit", help="拟合并导出可部署路由表(全量拟合,零 LLM)")
    f.add_argument("logs")
    f.add_argument("--out", required=True)
    f.add_argument("--drop-arm", action="append", default=[])
    f.add_argument("--chain", default=None)
    f.add_argument("--k-store", type=float, default=10.0)
    ns = ap.parse_args(argv)

    if ns.cmd == "fit":
        t = fit_from_logs(ns.logs, ns.drop_arm, ns.chain, ns.k_store)
        with open(ns.out, "w", encoding="utf-8") as fh:
            json.dump(t, fh, ensure_ascii=False, indent=1)
        n = sum(len(l["table"]) for l in t["levels"])
        print(f"fitted on {t['n_fit']} rows | arms {t['arms']} | "
              f"chain {'>'.join(t['chain'])} | {n} buckets | global={t['global']}")
        for l in t["levels"]:
            print(f"  {l['feature']:8s} {len(l['table']):5d} buckets")
        print(f"wrote {ns.out}")
        return 0

    r = audit(ns.logs, ns.seeds, ns.folds, ns.token_weight, ns.drop_arm, ns.chain)
    b = r["best"]
    if ns.metric:
        print({"score": f"{b['score']:.4f}", "acc": f"{b['acc'] * 100:.4f}",
               "tok": f"{b['tok']:.1f}"}[ns.metric])
        return 0

    s = r["stats"]
    print(f"{s['rows']} questions | {s['stores']} stores | {s['groups']} groups | "
          f"text {s['with_text']}/{s['rows']} | baseline {s['with_baseline']}/{s['rows']}")
    print(f"arms by cost (= fallback order): {', '.join(r['arms_by_cost'])}")

    print("\n== dominance ==")
    hits = [d for d in r["dominance"] if d["dominated_overall"]]
    if not hits:
        print("  no strictly dominated arm.")
    for d in hits:
        stable = d["benches_dominated"] == d["benches_total"] and d["benches_total"] > 1
        print(f"  {d['dominated_arm']} dominated by {d['by_arm']}  n={d['n']}  "
              f"acc {d['a_acc']}%->{d['b_acc']}%  tok {d['a_tok']}->{d['b_tok']}")
        print(f"    per-group {d['benches_dominated']}/{d['benches_total']} "
              f"{'STABLE' if stable else '-> UNSTABLE, report as a mix effect, not dominance'}")

    print(f"\n== strategies (same denominator, w={r['token_weight']}) ==")
    print(f"  {'':2s}{'strategy':34s} {'acc':>8s} {'tok':>8s} {'score':>8s} {'fallback':>9s}")
    for c in r["frontier"]:
        print(f"  {'*' if c.get('on_frontier') else ' ':2s}{c['strategy']:34s} "
              f"{c['acc'] * 100:7.2f}% {c['tok']:8.0f} {c['score']:8.3f} "
              f"{c.get('fallback_rate', 0) * 100:8.1f}%")
    if r["baseline"]:
        bl = r["baseline"]
        print(f"\n  best deployable vs your current system: "
              f"score {b['score'] - bl['score']:+.3f}  "
              f"acc {(b['acc'] - bl['acc']) * 100:+.2f}pp  "
              f"tok {(b['tok'] / bl['tok'] - 1) * 100:+.1f}%")
    print(f"  headroom to per-question oracle: {r['ceiling']['score'] - b['score']:+.3f}")

    if ns.emit:
        with open(ns.emit, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        print(f"\nwrote {ns.emit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
