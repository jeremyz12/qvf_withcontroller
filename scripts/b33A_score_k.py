# -*- coding: utf-8 -*-
"""批 33-A 附加记分:v45k(确定性 slot_class 回填派生店)键控制式阶梯。

与 b33A_score.py 同函数、同去重规则(首次出现优先)、同簇自助/TOST 口径。
用法: PYTHONUTF8=1 python scripts/b33A_score_k.py > results/b33A_score_k_out.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, compare, load  # noqa: E402

PAIRS = [
    ("filter",    "results/b33A_filter.jsonl",    "results/b33A_filter_k.jsonl",
     "results/wsc_v2_filter.jsonl"),
    ("usability", "results/b33A_usability.jsonl", "results/b33A_usability_k.jsonl",
     "results/wsc_v2_usability.jsonl"),
    ("compile",   "results/b33A_compile.jsonl",   "results/b33A_compile_k.jsonl",
     "results/wsc_v2_compile.jsonl"),
]


def main() -> None:
    raw = {n: load(p) for n, p, _, _ in PAIRS}
    k = {n: load(p) for n, _, p, _ in PAIRS}
    arch = {n: load(p) for n, _, _, p in PAIRS}
    direct = load("results/b33A_direct.jsonl")
    smoc = load("results/b33A_smoc_v45.jsonl")

    print("# 批 33-A v45k keyed-regime ladder (derived store)\n")

    print("## Dedupe ledger for the v45k runs\n")
    print("| arm | raw rows | deduped | dup rows | first/later agreement |")
    print("|---|---|---|---|---|")
    for n, _, p, _ in PAIRS:
        if p in DUP_STATS:
            t, u, dp, ag = DUP_STATS[p]
            print("| %s_k | %d | %d | %d | %s |"
                  % (n, t, u, dp, ("%.1f%%" % ag) if ag is not None else "-"))

    print("\n## Three regimes side by side\n")
    print("| arm | v2.0 archive (v2.0 corpus, v42) | b33A raw v45 (fallback) "
          "| b33A v45k (keyed backfill) |")
    print("|---|---|---|---|")
    for n, _, _, _ in PAIRS:
        if not k[n]:
            print("| %s | %.2f | %.2f | (missing) |" % (n, acc(arch[n]), acc(raw[n])))
            continue
        print("| %s | %.2f | %.2f | %.2f |"
              % (n, acc(arch[n]), acc(raw[n]), acc(k[n])))
    if smoc:
        print("| smoc(v45) | %.2f | %.2f | %.2f (same, store-independent) |"
              % (82.64, acc(smoc), acc(smoc)))

    print("\n## Per type (v45k)\n")
    types = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
    print("| arm | " + " | ".join(types) + " |")
    print("|---" * (len(types) + 1) + "|")
    for n, _, _, _ in PAIRS:
        if not k[n]:
            continue
        cells = []
        for t in types:
            rs = [r for r in k[n].values() if r.get("question_type") == t]
            cells.append("%.1f" % (sum(1 for r in rs if r["judge_correct"])
                                   / max(1, len(rs)) * 100) if rs else "-")
        print("| %s_k | " % n + " | ".join(cells) + " |")

    print("\n## Ladder in the keyed regime (A2 judged here)\n")
    rungs = [("select direct->filter_k", direct, k["filter"], 48.61, 62.67),
             ("certify filter_k->usability_k", k["filter"], k["usability"],
              62.67, 65.62),
             ("compute usability_k->compile_k", k["usability"], k["compile"],
              65.62, 75.87),
             ("ledger+protocol compile_k->smoc(v45)", k["compile"], smoc,
              75.87, 82.64)]
    for label, b, t, a0, a1 in rungs:
        if not b or not t:
            print("### " + label + ": missing\n")
            continue
        d = compare(label, b, t)
        same = "MATCH" if (d or 0) * (a1 - a0) > 0 else "MISMATCH"
        print("  v2.0 same rung: %.2f->%.2f = %+.2fpp | direction %s\n"
              % (a0, a1, a1 - a0, same))

    print("\n## Backfill effect: raw v45 -> v45k, same corpus same questions\n")
    for n, _, _, _ in PAIRS:
        if raw[n] and k[n]:
            compare("%s: raw v45 (fallback) -> v45k (keyed)" % n, raw[n], k[n],
                    margins=())
            print()

    print("\n## v45k vs v2.0 archive (corpus+builder effect, schema now aligned)\n")
    for n, _, _, _ in PAIRS:
        if k[n] and arch[n]:
            compare("%s: v2.0 archive -> b33A v45k" % n, arch[n], k[n], margins=())
            print()


if __name__ == "__main__":
    main()
