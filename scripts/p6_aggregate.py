# -*- coding: utf-8 -*-
"""P6: 聚合 n=3 轮 card_quality_eval 输出 -> 均值/标准差/t区间/bootstrap(与
results/b6_aggregate_output_20260816.txt 同一方法,便于并排对比)。
"""
import json
import math
import random
import sys
from pathlib import Path

T_CRIT_DF2 = 4.303  # 95% two-sided, df=2


def load_eval(path):
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def per_rep_metrics(rows):
    n = len(rows)
    n_exact = sum(1 for r in rows if r.get("exact_match"))
    micro_tp = sum(r["value_tp"] for r in rows)
    micro_card = sum(r["value_card_n"] for r in rows)
    micro_src = sum(r["value_src_n"] for r in rows)
    micro_p = micro_tp / micro_card if micro_card else 0.0
    micro_r = micro_tp / micro_src if micro_src else 0.0
    macro_p = sum(r["value_precision"] for r in rows) / n
    macro_r = sum(r["value_recall"] for r in rows) / n
    return {
        "n": n, "n_exact": n_exact, "exact_rate": n_exact / n,
        "micro_p": micro_p, "micro_r": micro_r,
        "macro_p": macro_p, "macro_r": macro_r,
    }


def t_interval(vals):
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    sd = math.sqrt(var)
    half = T_CRIT_DF2 * sd / math.sqrt(n)
    return mean, sd, (mean - half, mean + half), half * 100


def main():
    paths = sys.argv[1:]
    assert len(paths) == 3, "need exactly 3 eval jsonl paths"
    reps = [load_eval(p) for p in paths]
    metrics = [per_rep_metrics(r) for r in reps]

    print("=== per-rep summary ===")
    for p, m in zip(paths, metrics):
        print(f"{p}: n={m['n']} exact={m['n_exact']}/{m['n']}={m['exact_rate']:.4f} "
              f"micro_P={m['micro_p']:.4f} micro_R={m['micro_r']:.4f} "
              f"macro_P={m['macro_p']:.4f} macro_R={m['macro_r']:.4f}")

    print("\n=== t-interval (n=3 reps, df=2) ===")
    for key, label in [("exact_rate", "exact_match_rate"),
                        ("micro_p", "value_micro_precision"),
                        ("micro_r", "value_micro_recall"),
                        ("macro_p", "value_macro_precision"),
                        ("macro_r", "value_macro_recall")]:
        vals = [m[key] for m in metrics]
        mean, sd, ci, half_pp = t_interval(vals)
        print(f"{label}: vals={[f'{v:.4f}' for v in vals]} mean={mean:.4f} sd={sd:.4f} "
              f"95%CI=({ci[0]:.4f},{ci[1]:.4f})  half_width_pp={half_pp:.2f}")

    # uid-level bootstrap on exact-match (common uids across reps)
    uid_sets = [set(r["uid"] for r in rep) for rep in reps]
    common = set.intersection(*uid_sets)
    common = sorted(common)
    exact_by_rep = []
    for rep in reps:
        d = {r["uid"]: r["exact_match"] for r in rep}
        exact_by_rep.append(d)

    random.seed(20260817)
    B = 5000
    boot_means = []
    for _ in range(B):
        sample = [random.choice(common) for _ in common]
        rep_rates = []
        for d in exact_by_rep:
            rep_rates.append(sum(1 for u in sample if d[u]) / len(sample))
        boot_means.append(sum(rep_rates) / len(rep_rates))
    boot_means.sort()
    boot_mean = sum(boot_means) / len(boot_means)
    lo = boot_means[int(0.025 * B)]
    hi = boot_means[int(0.975 * B) - 1]
    print(f"\n=== uid-level bootstrap (B={B}, resample uids within each rep, average across reps) ===")
    print(f"n_common_uids={len(common)} boot_mean={boot_mean:.4f} 95%CI=({lo:.4f},{hi:.4f})")


if __name__ == "__main__":
    main()
