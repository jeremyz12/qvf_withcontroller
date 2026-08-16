# -*- coding: utf-8 -*-
"""
scripts/store_index_bench.py — P5 护栏④:复杂度实测。

对照:qvf_router.chain_depth(现有 O(n²) union-find,冻结代码只读调用)
      vs StoreIndex(索引 build 一次 + O(1) chain_depth 查表 + O(log m) asof)

O(n²) 参照实现在 n=10^4/10^5 上跑到完成不现实(见下方估算),故：
  - O(n²) 参照:实测 n in {200,400,800,1600,3200}(拟合确认二次标度后,
    对 10^4/10^5 做外推标注,不冒充实测);
  - 索引实现:n in {1000,10000,100000} 全部真实跑,p50/p99 latency。

合成库生成:每 uid 一个"库",n 条记录随机分布到 ~12 个 (owner,slot_class)
键上(不是全放一个键——现实卡片库的键控深度远小于总记录数,union-find
的 O(n²) 慢是"整库扫描定位一个键"造成的,不是"单键很深"造成的),便于
两种实现在同一份数据上做对照。

用法: python scripts/store_index_bench.py
"""
from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.store_index import StoreIndex  # noqa: E402

OWNERS = ["", "user"]
SLOT_CLASSES = ["employer", "position", "residence", "team", "device",
                "relationship"]


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
            "source_memory_id": f"bench/s{i}#r0",
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
        })
    return recs


# ── O(n²) 参照实现:与 qvf_router.chain_depth 的 union-find 主体逐字
#    移植(不 import qvf_router 本身,因为它模块级会创建 anthropic 客户端
#    等副作用,不适合在合成库压测里反复触发;算法逻辑保持一致,供公平
#    对照)。──────────────────────────────────────────────────
def slow_chain_depth(recs: list, slot: str) -> int:
    from scripts.wt_qvf_prototype import _slot_match, _norm
    n = len(recs)
    if not n:
        return 0
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    id2idx = {r.get("record_id"): i for i, r in enumerate(recs)
              if r.get("record_id")}
    for i, r in enumerate(recs):
        for t in (r.get("relation_target_record_ids") or []):
            j = id2idx.get(t)
            if j is not None:
                union(i, j)
    for i in range(n):
        for j in range(i + 1, n):
            if _slot_match(recs[i].get("slot", ""), recs[j].get("slot", "")):
                union(i, j)
    comps = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)

    def hits(idx):
        return sum(1 for i in idx if _slot_match(recs[i].get("slot", ""), slot))

    def dated_vals(idx):
        return {_norm(recs[i].get("value", "")) for i in idx
                if recs[i].get("stated_date") and _norm(recs[i].get("value", ""))}

    best, best_score = None, -1
    for idx in comps.values():
        h = hits(idx)
        if h == 0:
            continue
        rel = sum(len(recs[i].get("relation_target_record_ids") or [])
                  for i in idx)
        score = 4 * h + min(rel, 3)
        if score > best_score:
            best_score, best = score, idx
    comp_depth = len(dated_vals(best)) if best else 0
    hit_union = []
    for idx in comps.values():
        if hits(idx):
            hit_union.extend(idx)
    direct_idx = [i for i in range(n)
                  if _slot_match(recs[i].get("slot", ""), slot)]
    return max(comp_depth, len(dated_vals(hit_union)), len(dated_vals(direct_idx)))


def bench_slow(sizes, reps=5, seed=20260816):
    rng = random.Random(seed)
    rows = []
    for n in sizes:
        recs = synth_records(n, rng)
        times = []
        for _ in range(reps):
            t0 = time.perf_counter()
            slow_chain_depth(recs, "employer")
            times.append(time.perf_counter() - t0)
        times.sort()
        rows.append({"n": n, "p50_s": times[len(times) // 2], "p99_s": times[-1],
                     "reps": reps})
        print(f"  O(n^2) reference  n={n:>7}  p50={rows[-1]['p50_s']*1000:9.2f}ms "
              f"p99={rows[-1]['p99_s']*1000:9.2f}ms")
    return rows


def bench_index(sizes, n_queries=200, seed=20260816):
    rng = random.Random(seed)
    rows = []
    for n in sizes:
        recs = synth_records(n, rng)
        t_build0 = time.perf_counter()
        idx = StoreIndex().build(recs, {})
        build_s = time.perf_counter() - t_build0

        depth_times = []
        asof_times = []
        for _ in range(n_queries):
            slot = rng.choice(SLOT_CLASSES)
            t0 = time.perf_counter()
            idx.chain_depth(slot)
            depth_times.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            from scripts.complex_query_arm import _pdate
            qd = _pdate(f"{rng.randint(1990,2025)}-{rng.randint(1,12):02d}-01")
            idx.asof(slot, qd)
            asof_times.append(time.perf_counter() - t0)
        depth_times.sort()
        asof_times.sort()
        row = {
            "n": n, "build_s": build_s,
            "chain_depth_p50_ms": depth_times[len(depth_times) // 2] * 1000,
            "chain_depth_p99_ms": depth_times[-1] * 1000,
            "asof_p50_ms": asof_times[len(asof_times) // 2] * 1000,
            "asof_p99_ms": asof_times[-1] * 1000,
        }
        rows.append(row)
        print(f"  index  n={n:>7}  build={build_s*1000:9.2f}ms  "
              f"chain_depth p50={row['chain_depth_p50_ms']:.4f}ms "
              f"p99={row['chain_depth_p99_ms']:.4f}ms  "
              f"asof p50={row['asof_p50_ms']:.4f}ms p99={row['asof_p99_ms']:.4f}ms")
    return rows


def main():
    print("=== O(n^2) reference implementation (qvf_router.chain_depth "
          "union-find, ported read-only for benchmarking) ===")
    slow_sizes = [200, 400, 800, 1600, 3200]
    slow_rows = bench_slow(slow_sizes)

    # 二次标度检验:n 翻倍,耗时应约 x4
    print("\n  quadratic-scaling check (time ratio should be ~4x per size "
          "doubling if O(n^2)):")
    for a, b in zip(slow_rows, slow_rows[1:]):
        ratio = b["p50_s"] / a["p50_s"] if a["p50_s"] > 0 else float("nan")
        print(f"    n {a['n']:>5} -> {b['n']:>5}: time ratio = {ratio:.2f}x")

    # 外推(不是实测):用最大两点的经验斜率做二次外推到 1e4/1e5,明确
    # 标注为估算。
    import math
    last, prev = slow_rows[-1], slow_rows[-2]
    k = last["p50_s"] / (last["n"] ** 2)
    print(f"\n  EXTRAPOLATED (not executed — would take too long; quadratic "
          f"fit k=t/n^2={k:.3e}s from n={last['n']}):")
    for n in (10_000, 100_000):
        est = k * n * n
        unit = "s" if est < 120 else "min"
        val = est if est < 120 else est / 60
        print(f"    n={n:>7}: estimated p50 ≈ {val:.1f}{unit} "
              f"(EXTRAPOLATED, not measured)")

    print("\n=== StoreIndex (this module) — measured at 10^3/10^4/10^5 ===")
    index_sizes = [1_000, 10_000, 100_000]
    bench_index(index_sizes)

    print("\nDONE.")


if __name__ == "__main__":
    main()
