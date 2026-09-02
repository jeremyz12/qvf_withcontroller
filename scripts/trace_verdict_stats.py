# -*- coding: utf-8 -*-
"""批 33-H2:TRACE 考生结果统计($0,纯离线复算)。

输出:acc、簇(uid)自助 95% CI、题级自助 95% CI、$/题、延迟中位、
与同场对照臂的配对符号检验(题级 + 簇级)。

价格口径(项目既用):
  claude-haiku-4-5 读者 $1.00/M in, $5.00/M out
  claude-opus-5 判官   $5.00/M in, $25.00/M out(results/judge_cost_measured_20260816.md)
  gpt-4o-mini(TRACE 自带 LLM) $0.15/M in, $0.60/M out

用法: python scripts/trace_verdict_stats.py <file.jsonl> [--vs other.jsonl ...]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260902
N_BOOT = 10000

P_READ_IN, P_READ_OUT = 1.00, 5.00
P_JUDGE_IN, P_JUDGE_OUT = 5.00, 25.00
P_MINI_IN, P_MINI_OUT = 0.15, 0.60
JUDGE_IN_MEAN, JUDGE_OUT_MEAN = 198.28, 83.45   # 实测均值,判官不落盘 usage


def load(path):
    p = ROOT / path if not Path(path).is_absolute() else Path(path)
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def uid_of(r):
    if r.get("uid"):
        return r["uid"]
    qid = r.get("question_id", "")
    return qid.rsplit("_", 1)[0]


def boot_ci(values, n_boot=N_BOOT, seed=SEED):
    rng = random.Random(seed)
    n = len(values)
    xs = sorted(sum(rng.choices(values, k=n)) / n for _ in range(n_boot))
    return xs[int(0.025 * n_boot)] * 100, xs[int(0.975 * n_boot)] * 100


def cluster_boot_ci(rows, n_boot=N_BOOT, seed=SEED):
    by = defaultdict(list)
    for r in rows:
        by[uid_of(r)].append(1 if r.get("judge_correct") else 0)
    clusters = list(by.values())
    rng = random.Random(seed)
    xs = []
    for _ in range(n_boot):
        pick = rng.choices(clusters, k=len(clusters))
        flat = [v for c in pick for v in c]
        xs.append(sum(flat) / len(flat))
    xs.sort()
    return xs[int(0.025 * n_boot)] * 100, xs[int(0.975 * n_boot)] * 100


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def cost_of(rows):
    """$/题:读者(逐行实测)+ 判官(实测均值)+ TRACE 自带 gpt-4o-mini。
    建库(ingest)成本按库摊到该库的题上,单列。"""
    n = len(rows)
    r_in = sum(r.get("usage_input_tokens") or 0 for r in rows)
    r_out = sum(r.get("usage_output_tokens") or 0 for r in rows)
    read_usd = r_in / 1e6 * P_READ_IN + r_out / 1e6 * P_READ_OUT
    judge_usd = n * (JUDGE_IN_MEAN / 1e6 * P_JUDGE_IN
                     + JUDGE_OUT_MEAN / 1e6 * P_JUDGE_OUT)
    q_in = sum(r.get("trace_query_input_tokens") or 0 for r in rows)
    q_out = sum(r.get("trace_query_output_tokens") or 0 for r in rows)
    query_usd = q_in / 1e6 * P_MINI_IN + q_out / 1e6 * P_MINI_OUT
    # 建库:同一 uid 的行携带同一份 ingest 计数,去重后累加
    seen, ing_in, ing_out, ing_calls, ing_s = set(), 0, 0, 0, []
    for r in rows:
        u = uid_of(r)
        if u in seen:
            continue
        seen.add(u)
        ing_in += r.get("trace_ingest_input_tokens") or 0
        ing_out += r.get("trace_ingest_output_tokens") or 0
        ing_calls += r.get("trace_ingest_llm_calls") or 0
        if r.get("ingest_seconds"):
            ing_s.append(r["ingest_seconds"])
    build_usd = ing_in / 1e6 * P_MINI_IN + ing_out / 1e6 * P_MINI_OUT
    return {
        "n": n, "n_stores": len(seen),
        "read_in": r_in / n, "read_out": r_out / n,
        "usd_read_per_q": read_usd / n,
        "usd_judge_per_q": judge_usd / n,
        "usd_query_per_q": query_usd / n,
        "usd_answer_per_q": (read_usd + judge_usd + query_usd) / n,
        "usd_build_total": build_usd,
        "usd_build_per_q": build_usd / n,
        "usd_all_per_q": (read_usd + judge_usd + query_usd + build_usd) / n,
        "build_in": ing_in, "build_out": ing_out, "build_calls": ing_calls,
        "build_s_per_store": st.median(ing_s) if ing_s else None,
    }


def describe(label, rows):
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    ci_i = boot_ci([1 if r.get("judge_correct") else 0 for r in rows])
    ci_c = cluster_boot_ci(rows)
    lat = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    tlat = [r["trace_retrieval_latency_s"] for r in rows
            if r.get("trace_retrieval_latency_s") is not None]
    c = cost_of(rows)
    print(f"\n== {label} ==")
    print(f"n={len(rows)}  stores={c['n_stores']}  acc={acc:.2f}")
    print(f"  题级 bootstrap 95% CI [{ci_i[0]:.1f}, {ci_i[1]:.1f}]")
    print(f"  簇级(uid) bootstrap 95% CI [{ci_c[0]:.1f}, {ci_c[1]:.1f}]")
    if lat:
        print(f"  延迟中位 {st.median(lat):.2f}s (答题端到端)"
              + (f";其中检索 {st.median(tlat):.2f}s" if tlat else ""))
    print(f"  读者 in/out 均值 {c['read_in']:.0f}/{c['read_out']:.0f} tok")
    print(f"  $/题(答题:读者+判官+对手查询LLM) ${c['usd_answer_per_q']:.5f}")
    print(f"  建库总额 ${c['usd_build_total']:.4f}"
          f"(gpt-4o-mini in {c['build_in']:,} / out {c['build_out']:,}"
          f" / {c['build_calls']:,} 次调用);摊到每题 ${c['usd_build_per_q']:.5f}")
    print(f"  $/题(含建库摊销) ${c['usd_all_per_q']:.5f}")
    if c["build_s_per_store"]:
        print(f"  建库耗时中位 {c['build_s_per_store']:.1f}s/库"
              f" = {c['build_s_per_store']/(len(rows)/max(1,c['n_stores'])):.1f}s/题")
    by_t = defaultdict(list)
    for r in rows:
        by_t[r.get("question_type")].append(1 if r.get("judge_correct") else 0)
    print("  按题型:" + " | ".join(
        f"{k} {sum(v)/len(v)*100:.1f}({len(v)})" for k, v in sorted(by_t.items())))
    return acc


def paired(label_a, rows_a, label_b, rows_b):
    a = {r["question_id"]: bool(r.get("judge_correct")) for r in rows_a}
    b = {r["question_id"]: bool(r.get("judge_correct")) for r in rows_b}
    common = sorted(set(a) & set(b))
    if not common:
        print(f"\n-- {label_a} vs {label_b}: 无共同题,跳过")
        return
    w = sum(1 for q in common if a[q] and not b[q])
    l = sum(1 for q in common if b[q] and not a[q])
    da = sum(a[q] for q in common) / len(common) * 100
    db = sum(b[q] for q in common) / len(common) * 100
    # 簇级符号检验
    cw = cl = 0
    by = defaultdict(lambda: [0, 0, 0])
    for q in common:
        u = q.rsplit("_", 1)[0]
        by[u][0] += a[q]
        by[u][1] += b[q]
        by[u][2] += 1
    for u, (sa, sb, n) in by.items():
        if sa > sb:
            cw += 1
        elif sb > sa:
            cl += 1
    # 簇自助配对 CI
    rng = random.Random(SEED)
    keys = list(by)
    xs = []
    for _ in range(N_BOOT):
        pick = rng.choices(keys, k=len(keys))
        na = sum(by[u][0] for u in pick)
        nb = sum(by[u][1] for u in pick)
        nt = sum(by[u][2] for u in pick)
        xs.append((na - nb) / nt * 100)
    xs.sort()
    print(f"\n-- {label_a} ({da:.2f}) vs {label_b} ({db:.2f})  n={len(common)}")
    print(f"   Δ={da-db:+.2f}pp  题级 w/l={w}/{l} p={sign_p(w,l):.4g}")
    print(f"   簇级 w/l={cw}/{cl} p={sign_p(cw,cl):.4g}  "
          f"簇自助 95% CI [{xs[int(0.025*N_BOOT)]:+.1f}, {xs[int(0.975*N_BOOT)]:+.1f}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="主文件(可多个,同 label 合并)")
    ap.add_argument("--label", default="")
    ap.add_argument("--vs", action="append", default=[],
                    help="对照 label=path;可重复")
    ap.add_argument("--restrict-to-main", action="store_true",
                    help="对照臂只取与主文件同题的子集")
    a = ap.parse_args()
    rows = []
    for f in a.files:
        rows += load(f)
    main_ids = {r["question_id"] for r in rows}
    describe(a.label or a.files[0], rows)
    for spec in a.vs:
        lab, _, path = spec.partition("=")
        other = load(path)
        if a.restrict_to_main:
            other = [r for r in other if r["question_id"] in main_ids]
        describe(lab, other)
        paired(a.label or "TRACE", rows, lab, other)
    return 0


if __name__ == "__main__":
    sys.exit(main())
