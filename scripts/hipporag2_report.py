# -*- coding: utf-8 -*-
"""批 33-H1 汇总:HippoRAG 2 × 60 题标定场,出榜单同格式一行 + 自助 CI + 成本。

用法: python scripts/hipporag2_report.py [results/wsc_s5_hipporag2.jsonl ...]
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
SEED = 20260902
N_BOOT = 10000

# USD / 1M tokens
PRICE = {
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
}


def boot_ci(vals, n_boot=N_BOOT, seed=SEED):
    rng = random.Random(seed)
    n = len(vals)
    xs = []
    for _ in range(n_boot):
        xs.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    xs.sort()
    return xs[int(0.025 * n_boot)] * 100, xs[int(0.975 * n_boot)] * 100


def boot_ci_cluster(by_cluster, n_boot=N_BOOT, seed=SEED):
    rng = random.Random(seed)
    keys = list(by_cluster)
    k = len(keys)
    xs = []
    for _ in range(n_boot):
        pool = []
        for _ in range(k):
            pool.extend(by_cluster[keys[rng.randrange(k)]])
        xs.append(sum(pool) / len(pool))
    xs.sort()
    return xs[int(0.025 * n_boot)] * 100, xs[int(0.975 * n_boot)] * 100


def report(path: Path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    n = len(rows)
    correct = [1 if r.get("judge_correct") else 0 for r in rows]
    acc = sum(correct) / n * 100
    lo, hi = boot_ci(correct)
    by_uid = defaultdict(list)
    for r, c in zip(rows, correct):
        by_uid[r["uid"]].append(c)
    clo, chi = boot_ci_cluster(by_uid)

    in_tok = statistics.mean(r.get("usage_input_tokens", 0) for r in rows)
    out_tok = statistics.mean(r.get("usage_output_tokens", 0) for r in rows)
    lat_med = statistics.median(r.get("latency_s", 0) for r in rows)
    retr_med = statistics.median(r.get("retrieve_s", 0) for r in rows)

    # 建库:每条目一次,取条目级均值(与榜单"建库 s/题"口径:总建库秒 / 题数)
    ing_by_uid = {r["uid"]: r.get("ingest_seconds", 0) for r in rows}
    ingest_total = sum(ing_by_uid.values())
    ingest_per_q = ingest_total / n
    ingest_per_item = ingest_total / max(len(ing_by_uid), 1)

    # 成本
    hr_ing_in = sum({r["uid"]: r.get("hr_ingest_llm_in", 0) for r in rows}.values())
    hr_ing_out = sum({r["uid"]: r.get("hr_ingest_llm_out", 0) for r in rows}.values())
    hr_ing_emb = sum({r["uid"]: r.get("hr_ingest_emb_tok", 0) for r in rows}.values())
    hr_q_in = sum(r.get("hr_query_llm_in", 0) for r in rows)
    hr_q_out = sum(r.get("hr_query_llm_out", 0) for r in rows)
    hr_q_emb = sum(r.get("hr_query_emb_tok", 0) for r in rows)
    rd_in = sum(r.get("usage_input_tokens", 0) for r in rows)
    rd_out = sum(r.get("usage_output_tokens", 0) for r in rows)

    pi, po = PRICE["gpt-4o-mini"]
    pe = PRICE["text-embedding-3-small"][0]
    ph_i, ph_o = PRICE["claude-haiku-4-5"]
    usd_index = (hr_ing_in * pi + hr_ing_out * po + hr_ing_emb * pe) / 1e6
    usd_query_hr = (hr_q_in * pi + hr_q_out * po + hr_q_emb * pe) / 1e6
    usd_reader = (rd_in * ph_i + rd_out * ph_o) / 1e6

    print(f"\n=== {path.name} ===")
    print(f"n={n}  acc={acc:.2f}  item-boot 95% CI [{lo:.1f}, {hi:.1f}]  "
          f"cluster(uid, k={len(by_uid)})-boot 95% CI [{clo:.1f}, {chi:.1f}]")
    print(f"reader in-tok={in_tok:.0f} out-tok={out_tok:.0f}  "
          f"latency median={lat_med:.2f}s (retrieve median={retr_med:.2f}s)")
    print(f"ingest: {ingest_per_item:.1f}s/item  {ingest_per_q:.1f}s/question  "
          f"(total {ingest_total:.0f}s over {len(ing_by_uid)} items)")
    print(f"HippoRAG index tokens: llm {hr_ing_in}/{hr_ing_out}, emb {hr_ing_emb}"
          f"   -> ${usd_index:.4f}")
    print(f"HippoRAG query tokens: llm {hr_q_in}/{hr_q_out}, emb {hr_q_emb}"
          f"   -> ${usd_query_hr:.4f}")
    print(f"reader tokens: {rd_in}/{rd_out}  -> ${usd_reader:.4f}")
    print(f"$/question total (index+query+reader) = "
          f"${(usd_index + usd_query_hr + usd_reader) / n:.4f}")
    print(f"$/question excl. index = ${(usd_query_hr + usd_reader) / n:.4f}")

    bt = defaultdict(lambda: [0, 0])
    for r, c in zip(rows, correct):
        bt[r["question_type"]][0] += 1
        bt[r["question_type"]][1] += c
    for qt in sorted(bt):
        m, k = bt[qt]
        print(f"   {qt:18s} n={m:>3} acc={k / m * 100:.1f}")
    return {"n": n, "acc": acc, "ci": (lo, hi), "cci": (clo, chi),
            "in": in_tok, "out": out_tok, "lat": lat_med,
            "ingest_q": ingest_per_q,
            "usd_q": (usd_index + usd_query_hr + usd_reader) / n}


def _acc_map(path: Path, qids=None):
    m = {}
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        qid = r.get("question_id")
        if qids is not None and qid not in qids:
            continue
        m[qid] = 1 if r.get("judge_correct") else 0
    return m


def paired(test_path: Path, base_path: Path, label: str):
    """配对比较:McNemar 精确检验 + 簇(uid)自助 CI on delta。"""
    from math import comb

    a = _acc_map(test_path)
    b = _acc_map(base_path, set(a))
    common = sorted(set(a) & set(b))
    if not common:
        print(f"  [{label}] no overlap")
        return
    n01 = sum(1 for q in common if a[q] == 0 and b[q] == 1)   # base 赢
    n10 = sum(1 for q in common if a[q] == 1 and b[q] == 0)   # test 赢
    n = n01 + n10
    p = 1.0
    if n:
        k = min(n01, n10)
        p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n))
    delta = (sum(a[q] for q in common) - sum(b[q] for q in common)) / len(common) * 100
    by_c = defaultdict(list)
    for q in common:
        by_c[q.rsplit("_", 1)[0]].append(a[q] - b[q])
    rng = random.Random(SEED)
    keys = list(by_c)
    xs = []
    for _ in range(N_BOOT):
        pool = []
        for _ in range(len(keys)):
            pool.extend(by_c[keys[rng.randrange(len(keys))]])
        xs.append(sum(pool) / len(pool) * 100)
    xs.sort()
    print(f"  [{label}] n={len(common)} delta={delta:+.2f}pp  "
          f"cluster-boot 95% CI [{xs[int(.025 * N_BOOT)]:+.1f}, "
          f"{xs[int(.975 * N_BOOT)]:+.1f}]  McNemar exact p={p:.4g} "
          f"(win {n10} / lose {n01})")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or [ROOT / "results/wsc_s5_hipporag2.jsonl"]
    outs = [report(p) for p in paths]
    main_p = paths[0]
    print("\n配对比较(同 60 题,question_id 对齐;簇=15 个 WikiState 实体):")
    for lbl, bp in [
        ("vs 直读 top-10", ROOT / "results/wsc_direct_s5_all_b1_union.jsonl"),
        ("vs QVF smoc", ROOT / "results/wsc_smoc418_rerun_20260826.jsonl"),
        ("vs txtai", ROOT / "results/wsc_s5_txtai.jsonl"),
        ("vs timeline", ROOT / "results/wsc_s5_timeline.jsonl"),
        ("vs lgstore", ROOT / "results/wsc_s5_lgstore.jsonl"),
        ("vs Mem0", ROOT / "results/wsc_s5_mem0.jsonl"),
        ("vs cognee", ROOT / "results/wsc_s5_cognee.jsonl"),
        ("vs A-MEM", ROOT / "results/wsc_s5_amem.jsonl"),
    ]:
        if bp.exists():
            paired(main_p, bp, lbl)
    print("\n榜单格式行(| 系统/臂 | n | acc | in-tok | out-tok | 延迟中位 | 建库 | 注 |):")
    for p, o in zip(paths, outs):
        print(f"| HippoRAG 2 | {o['n']} | **{o['acc']:.2f}** | {o['in']:.0f} | "
              f"{o['out']:.0f} | {o['lat']:.2f}s | {o['ingest_q']:.1f}s/题 | "
              f"CI [{o['ci'][0]:.1f}, {o['ci'][1]:.1f}]; ${o['usd_q']:.4f}/题 |")
