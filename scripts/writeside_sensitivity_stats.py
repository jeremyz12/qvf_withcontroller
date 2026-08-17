# -*- coding: utf-8 -*-
"""T1 条件③:低质量轮(b6_rep3)端到端结果 vs 直读臂 vs 参照(v42)编译臂,
限定在同一 76 题子集上,复用 scripts/bootstrap_ci.py 的簇稳健检验(簇=uid)。
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import random  # noqa: E402
from scripts.bootstrap_ci import (  # noqa: E402
    load_two_file_pairs, build_clusters, report, print_row,
)

RES = Path("results")
rng = random.Random(20260816)
N_BOOT = 10000

# 限定 v42/直读两份 418 题全量文件到 b6_rep3 覆盖的同一 76 题子集,写临时
# 过滤文件,避免与全量 418 题比较混淆(v42-vs-direct 若不过滤会退化成整份
# 418 题的既有结论,不是本次要的"同 76 题"对照)。
import json  # noqa: E402
target_qids = set()
for l in open(RES / "writeside_sensitivity_b6rep3_arm.jsonl", encoding="utf-8"):
    target_qids.add(json.loads(l)["question_id"])

v42_sub = RES / "writeside_sensitivity_v42_subset76.jsonl"
direct_sub = RES / "writeside_sensitivity_direct_subset76.jsonl"
with open(v42_sub, "w", encoding="utf-8") as fo:
    for l in open(RES / "wsc_s5_test_v42b1_union.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r["question_id"] in target_qids:
            fo.write(l if l.endswith("\n") else l + "\n")
with open(direct_sub, "w", encoding="utf-8") as fo:
    for l in open(RES / "wsc_direct_s5_all_b1_union.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r["question_id"] in target_qids:
            fo.write(l if l.endswith("\n") else l + "\n")

pairs = [
    ("b6_rep3(64.0%,最低单轮) 编译臂 vs 直读臂,同 76 题",
     RES / "writeside_sensitivity_b6rep3_arm.jsonl", "complex_arm",
     RES / "wsc_direct_s5_all_b1_union.jsonl", "wsc_direct"),
    ("v42(76.88%,归档参照) 编译臂 vs 直读臂,同 76 题",
     v42_sub, "complex_arm",
     direct_sub, "wsc_direct"),
    ("b6_rep3 编译臂 vs v42 编译臂(纯质量效应,同库题集配对)",
     RES / "writeside_sensitivity_b6rep3_arm.jsonl", "complex_arm",
     v42_sub, "complex_arm"),
]

for name, tp, tm, bp, bm in pairs:
    items, uid_map = load_two_file_pairs(tp, bp, tm, bm, True)
    # 只保留 b6_rep3 覆盖的题(load_two_file_pairs 已按 base 文件里存在的
    # question_id 交集;因 v42/direct 文件题量大于 76,交集会被 test 文件
    # (76 题)天然限定,这里不需要额外过滤)
    clusters = build_clusters(items, "wikistate", uid_map)
    r = report(name, items, clusters, rng, N_BOOT)
    if r is None:
        print(f"[skip] {name}: no overlap")
        continue
    print_row(r)
