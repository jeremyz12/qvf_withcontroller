# -*- coding: utf-8 -*-
"""
scripts/store_index_bench_ops.py — P5 阶段二护栏④补充:11 算子(不只
chain_depth/asof)在索引路径 execute_plan_indexed 下的 p50/p99 延迟,
与冻结扫描路径 execute_plan 对照(小规模,O(n^2)/O(n log n) 扫描在大
n 下不现实,同 store_index_bench.py 的外推纪律)。

11 算子:current / premise_check / point_in_time / trajectory /
count_changes / longest / count_before / first_last / tag_filter /
tag_trend / join_at_change。

用法: python scripts/store_index_bench_ops.py
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.store_index import StoreIndex  # noqa: E402
from qvf.store_index_ops import execute_plan_indexed  # noqa: E402
from scripts.complex_query_arm import execute_plan  # noqa: E402

OWNERS = ["", "user"]
SLOT_CLASSES = ["employer", "position", "residence", "team", "device",
                "relationship"]
TAGS = ["tagA", "tagB", "tagC"]

OPS_PLANS = [
    ("current", {"op": "current", "slot": "employer", "slot2": None,
                "date": None, "tag": None, "presupposed": None,
                "anchor_index": None}),
    ("premise_check", {"op": "premise_check", "slot": "employer",
                       "slot2": None, "date": None, "tag": None,
                       "presupposed": "val_3", "anchor_index": None}),
    ("point_in_time", {"op": "point_in_time", "slot": "employer",
                       "slot2": None, "date": "2010-06-15", "tag": None,
                       "presupposed": None, "anchor_index": None}),
    ("trajectory", {"op": "trajectory", "slot": "employer", "slot2": None,
                    "date": None, "tag": None, "presupposed": None,
                    "anchor_index": None}),
    ("count_changes", {"op": "count_changes", "slot": "employer",
                       "slot2": None, "date": None, "tag": None,
                       "presupposed": None, "anchor_index": None}),
    ("longest", {"op": "longest", "slot": "employer", "slot2": None,
                "date": None, "tag": None, "presupposed": None,
                "anchor_index": None}),
    ("count_before", {"op": "count_before", "slot": "employer",
                      "slot2": None, "date": "2015-01-01", "tag": None,
                      "presupposed": None, "anchor_index": None}),
    ("first_last", {"op": "first_last", "slot": "employer", "slot2": None,
                    "date": None, "tag": None, "presupposed": None,
                    "anchor_index": None}),
    ("tag_filter", {"op": "tag_filter", "slot": "employer", "slot2": None,
                    "date": None, "tag": "tagA", "presupposed": None,
                    "anchor_index": None}),
    ("tag_trend", {"op": "tag_trend", "slot": "employer", "slot2": None,
                  "date": None, "tag": "tagB", "presupposed": None,
                  "anchor_index": None}),
    ("join_at_change", {"op": "join_at_change", "slot": "employer",
                        "slot2": "residence", "date": None, "tag": None,
                        "presupposed": "val_3", "anchor_index": None}),
]


def synth_records(n: int, rng: random.Random) -> list:
    recs = []
    for i in range(n):
        owner = rng.choice(OWNERS)
        cls = rng.choice(SLOT_CLASSES)
        y = rng.randint(1990, 2025)
        m = rng.randint(1, 12)
        d = rng.randint(1, 28)
        recs.append({
            "record_id": f"r{i}",
            "source_memory_id": f"benchops/s{i}#r0",
            "source_span": f"span-{i}",
            "entity": "user",
            "slot": cls,
            "value": f"val_{i % 37}",
            "slot_cardinality": "single",
            "temporal_relation": ("replacement" if i > 0 and rng.random() < 0.3
                                  else "equivalent"),
            "relation_target_record_ids": ([f"r{i-1}"] if i > 0
                                           and rng.random() < 0.3 else []),
            "condition": "", "implies_stale_slots": [],
            "stated_date": f"{y}-{m:02d}-{d:02d}",
            "owner": owner, "slot_class": cls,
            "value_tags": rng.sample(TAGS, k=rng.randint(0, 2)),
        })
    return recs


def _percentiles(times):
    times = sorted(times)
    return times[len(times) // 2] * 1000, times[-1] * 1000


def bench_indexed(sizes, n_queries=200, seed=20260817):
    rng = random.Random(seed)
    print("=== StoreIndex (execute_plan_indexed) — 11 ops, measured ===")
    rows = []
    for n in sizes:
        recs = synth_records(n, rng)
        idx = StoreIndex().build(recs, {})
        row = {"n": n}
        for op_name, plan in OPS_PLANS:
            times = []
            for _ in range(n_queries):
                t0 = time.perf_counter()
                execute_plan_indexed(plan, idx, "")
                times.append(time.perf_counter() - t0)
            p50, p99 = _percentiles(times)
            row[op_name] = {"p50_ms": p50, "p99_ms": p99}
            print(f"  n={n:>7}  {op_name:<16} p50={p50:8.4f}ms p99={p99:8.4f}ms")
        rows.append(row)
    return rows


def bench_scan(sizes, n_queries=20, seed=20260817):
    rng = random.Random(seed)
    print("\n=== Frozen scan (execute_plan) — 11 ops, small n only "
          "(O(n) linear scan for select_pool + O(n log n) sort per call; "
          "no union-find here since these plans don't hit chain_depth) ===")
    rows = []
    for n in sizes:
        recs = synth_records(n, rng)
        row = {"n": n}
        for op_name, plan in OPS_PLANS:
            times = []
            for _ in range(n_queries):
                t0 = time.perf_counter()
                execute_plan(plan, recs, {}, "")
                times.append(time.perf_counter() - t0)
            p50, p99 = _percentiles(times)
            row[op_name] = {"p50_ms": p50, "p99_ms": p99}
            print(f"  n={n:>7}  {op_name:<16} p50={p50:8.4f}ms p99={p99:8.4f}ms")
        rows.append(row)
    return rows


def main():
    scan_sizes = [200, 400, 800, 1600, 3200]
    scan_rows = bench_scan(scan_sizes)
    index_sizes = [1_000, 10_000, 100_000]
    index_rows = bench_indexed(index_sizes)

    import json
    out = {"scan": scan_rows, "indexed": index_rows}
    Path("results/p5_index_bench_ops_stage2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nDONE. Written results/p5_index_bench_ops_stage2.json")


if __name__ == "__main__":
    main()
