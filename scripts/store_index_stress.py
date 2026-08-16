# -*- coding: utf-8 -*-
"""
scripts/store_index_stress.py — P5 护栏②:I1-I4 不变量的随机压力测试。

≥10^4 次随机 insert/splice 序列(含乱序到达:新记录日期可早于已插入记录),
每次插入后独立复核 check_invariants();另附一个"顺序不变性"断言(同一组
记录以不同随机顺序逐条插入,最终物化的链应彼此相同——回溯拼接的正确性
定义)。零 LLM,纯代码。

用法: python scripts/store_index_stress.py [--trials N] [--inserts-per-trial M]
"""
from __future__ import annotations

import argparse
import random
import string
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.store_index import StoreIndex  # noqa: E402

OWNERS = ["", "user", "friend_a", "friend_b"]
SLOT_CLASSES = ["employer", "position", "residence", "team", "device",
                "relationship", "other:hobby", "other:travel"]
VALUES = [f"value_{c}" for c in string.ascii_uppercase[:10]]


def _rand_date(rng: random.Random) -> str:
    y = rng.randint(1990, 2025)
    fmt = rng.choice(["Y", "YM", "YMD"])
    if fmt == "Y":
        return f"{y}"
    m = rng.randint(1, 12)
    if fmt == "YM":
        return f"{y}-{m:02d}"
    d = rng.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


def _rand_record(rng: random.Random, i: int, dangling_edge_prob: float) -> dict:
    owner = rng.choice(OWNERS)
    cls = rng.choice(SLOT_CLASSES)
    val = rng.choice(VALUES)
    date = _rand_date(rng) if rng.random() > 0.15 else ""  # 15% 无日期
    rec = {
        "record_id": f"r{i}",
        "source_memory_id": f"stress/s{i}#r0",
        "source_span": f"span-{i}-{val}",
        "entity": "user",
        "slot": cls,
        "value": val,
        "slot_cardinality": "single",
        "temporal_relation": "equivalent",
        "relation_target_record_ids": [],
        "condition": "",
        "implies_stale_slots": [],
        "stated_date": date,
        "owner": owner,
        "slot_class": cls,
        "value_tags": rng.sample(["tagA", "tagB", "tagC"], k=rng.randint(0, 2)),
    }
    if rng.random() < dangling_edge_prob:
        # 故意造一个指向不存在 id 的边,验证 I4 前置校验会丢弃它而不是
        # 让不变量被破坏。
        rec["relation_target_record_ids"] = [f"r_nonexistent_{i}"]
    return rec


def run_trial(rng: random.Random, n_inserts: int, check_every_insert: bool
              ) -> dict:
    idx = StoreIndex().build([], {})
    n_checks = 0
    n_dangling_dropped = 0
    prev_id = None
    for i in range(n_inserts):
        rec = _rand_record(rng, i, dangling_edge_prob=0.1)
        # 20% 概率给一条合法的替换边(指向已存在的上一条记录),测试 I1
        if prev_id and rng.random() < 0.2:
            rec["relation_target_record_ids"] = [prev_id]
            rec["temporal_relation"] = "replacement"
        entry = idx.insert_record(rec)
        if entry.get("dangling_edges_dropped"):
            n_dangling_dropped += 1
        prev_id = rec["record_id"]
        if check_every_insert:
            v = idx.check_invariants()
            n_checks += 1
            if not v["ok"]:
                return {"ok": False, "fail_at_insert": i, "verdict": v,
                       "n_checks": n_checks}
    v = idx.check_invariants()
    return {"ok": v["ok"], "verdict": v, "n_checks": n_checks + 1,
           "n_dangling_dropped": n_dangling_dropped, "final_records": n_inserts}


def order_independence_trial(rng: random.Random, n_records: int) -> dict:
    """同一组随机记录(互不构成替换边,避免 I4 依赖插入顺序的边),用两种
    不同的随机插入顺序分别建索引,断言两次得到的每条链(dated, canonical
    order)完全相同 —— 这是"retroactive splice 与到达顺序无关"的核心
    正确性断言,而不仅仅是"不变量不被破坏"。"""
    recs = [_rand_record(rng, i, dangling_edge_prob=0.0) for i in range(n_records)]
    order1 = recs[:]
    order2 = recs[:]
    rng.shuffle(order2)
    idx1 = StoreIndex().build([], {})
    for r in order1:
        idx1.insert_record(r)
    idx2 = StoreIndex().build([], {})
    for r in order2:
        idx2.insert_record(r)
    keys = set(idx1.chains) | set(idx2.chains)
    for k in keys:
        c1 = [r["record_id"] for r in idx1.chains.get(k, type("x", (), {"chain": []})).chain] \
            if k in idx1.chains else []
        c2 = [r["record_id"] for r in idx2.chains.get(k, type("x", (), {"chain": []})).chain] \
            if k in idx2.chains else []
        if c1 != c2:
            return {"ok": False, "key": list(k), "order1_chain": c1,
                   "order2_chain": c2}
    return {"ok": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--inserts-per-trial", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260816)
    ap.add_argument("--order-trials", type=int, default=300)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    t0 = time.time()
    total_inserts = 0
    total_dangling = 0
    fails = []
    for t in range(a.trials):
        res = run_trial(rng, a.inserts_per_trial, check_every_insert=True)
        total_inserts += a.inserts_per_trial
        if not res["ok"]:
            fails.append({"trial": t, **res})
        else:
            total_dangling += res.get("n_dangling_dropped", 0)
    dt = time.time() - t0

    oi_fails = []
    for t in range(a.order_trials):
        n = rng.randint(5, 40)
        res = order_independence_trial(rng, n)
        if not res["ok"]:
            oi_fails.append({"trial": t, **res})

    print(f"INVARIANT STRESS: {a.trials} trials x {a.inserts_per_trial} "
          f"inserts = {total_inserts} total insert-then-check operations "
          f"in {dt:.2f}s")
    print(f"  invariant failures: {len(fails)}/{a.trials} trials")
    print(f"  dangling edges correctly dropped (I4 pre-check exercised): "
          f"{total_dangling} times")
    print(f"ORDER-INDEPENDENCE (retroactive splice correctness): "
          f"{a.order_trials} trials, failures={len(oi_fails)}")
    for f in fails[:5]:
        print("  INVARIANT FAIL:", f)
    for f in oi_fails[:5]:
        print("  ORDER FAIL:", f)
    ok = not fails and not oi_fails
    print(f"VERDICT: {'ALL PASS' if ok else 'FAILURES FOUND — see above'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
