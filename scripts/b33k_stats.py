# -*- coding: utf-8 -*-
"""批 33-K 统计与成本($0,纯归档复算)。

配对精确符号检验(= 精确 McNemar)+ **链簇(uid)自助 95% CI** + 逐题美元。
价格口径:
  gemini-3.6-flash  in $0.75/M、out $3.75/M(2026-12-31 前 promo 价;
                    2027-01-01 起 $1.50/$7.50)——thoughts token 计入 out。
  haiku-4-5         in $1.00/M、out $5.00/M(对照行)
  判官 claude-opus-5 in $5.00/M、out $25.00/M(逐行无落盘时按实测均价
                    $0.003078/次,来源 results/judge_cost_measured_20260816.md)

用法:
  PYTHONUTF8=1 python scripts/b33k_stats.py
"""
from __future__ import annotations

import json
import random
import statistics as st
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
G_IN, G_OUT = 0.75, 3.75
JUDGE_USD_PER_CALL = 0.003078
SEED = 20260902
N_BOOT = 10000

ARMS = {
    "smoc": "results/b33k_gemini36f_smoc_v24.jsonl",
    "ledgerplain": "results/b33k_gemini36f_ledgerplain_v24.jsonl",
    "direct": "results/b33k_gemini36f_direct_v24.jsonl",
    "fullplain": "results/b33k_gemini36f_fullplain_v24_s2.jsonl",
    "closedbook": "results/b33k_gemini36f_closedbook_v24.jsonl",
    "L1_fullplain": "results/b33k_gemini36f_fullplain_L1.jsonl",
    "L2_fullplain": "results/b33k_gemini36f_fullplain_L2.jsonl",
}
HAIKU = {"smoc": 90.45, "ledgerplain": 75.35, "direct": 48.26,
         "fullplain": 52.26}


def load(p):
    fp = ROOT / p
    if not fp.exists():
        return []
    out = []
    for l in open(fp, encoding="utf-8"):
        if l.strip():
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                pass
    return out


def sign_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def cluster_boot(by_uid, n_boot=N_BOOT, seed=SEED):
    """按 uid(链)重采样的簇自助:Δ = acc_test − acc_base(pp)。"""
    rnd = random.Random(seed)
    uids = list(by_uid)
    n = len(uids)
    if n == 0:
        return (float("nan"), float("nan"))
    ds = []
    for _ in range(n_boot):
        a = b = tot = 0
        for _ in range(n):
            for x, y in by_uid[uids[rnd.randrange(n)]]:
                a += x
                b += y
                tot += 1
        ds.append(100.0 * (a - b) / max(tot, 1))
    ds.sort()
    return (ds[int(0.025 * n_boot)], ds[int(0.975 * n_boot)])


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = (z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return ((c - s) / d * 100, (c + s) / d * 100)


def summarize(tag, rows):
    if not rows:
        print(f"[{tag}] MISSING")
        return None
    n = len(rows)
    ok = sum(1 for r in rows if r.get("judge_correct"))
    ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
    to = sum(r.get("usage_output_tokens") or 0 for r in rows)
    th = sum((r.get("usage_meta") or {}).get("thoughts_token_count", 0)
             for r in rows)
    usd = ti / 1e6 * G_IN + to / 1e6 * G_OUT
    lat = st.mean(r.get("latency_s", 0) or 0 for r in rows)
    lo, hi = wilson(ok, n)
    dev = sum(1 for r in rows if r.get("protocol_deviation"))
    empt = sum(1 for r in rows if not str(r.get("answer", "")).strip())
    mx = sum(1 for r in rows if "MAX_TOKENS" in
             str((r.get("usage_meta") or {}).get("finish_reason", "")))
    print(f"[{tag}] n={n} acc={ok / n * 100:.2f} Wilson95=[{lo:.1f},{hi:.1f}] "
          f"in/q={ti / n:.0f} out/q={to / n:.0f} think/q={th / n:.0f} "
          f"read$/q={usd / n:.5f} judge$/q={JUDGE_USD_PER_CALL:.5f} "
          f"tot$/q={usd / n + JUDGE_USD_PER_CALL:.5f} lat={lat:.1f}s "
          f"read$={usd:.3f} judge$={n * JUDGE_USD_PER_CALL:.3f} "
          f"dev={dev} empty={empt} maxtok={mx}")
    return dict(n=n, acc=ok / n * 100, usd=usd,
                judge=n * JUDGE_USD_PER_CALL)


def compare(name, trows, brows):
    t = {r["question_id"]: bool(r.get("judge_correct")) for r in trows}
    b = {r["question_id"]: bool(r.get("judge_correct")) for r in brows}
    u = {r["question_id"]: r["uid"] for r in trows}
    ks = sorted(set(t) & set(b))
    if not ks:
        print(f"[{name}] NO OVERLAP")
        return
    by = defaultdict(list)
    for k in ks:
        by[u[k]].append((t[k], b[k]))
    w = sum(1 for k in ks if t[k] and not b[k])
    l = sum(1 for k in ks if b[k] and not t[k])
    at = 100.0 * sum(1 for k in ks if t[k]) / len(ks)
    ab = 100.0 * sum(1 for k in ks if b[k]) / len(ks)
    lo, hi = cluster_boot(by)
    print(f"[{name}] n={len(ks)} clusters={len(by)} test={at:.2f} "
          f"base={ab:.2f} delta={at - ab:+.2f}pp W/L/T={w}/{l}/"
          f"{len(ks) - w - l} sign_p={sign_p(w, l):.4g} "
          f"clusterboot95=[{lo:+.2f},{hi:+.2f}]")


def main():
    print("=== 逐臂(gemini-3.6-flash,temperature 0,thinking_level=low)===")
    tot_r = tot_j = 0.0
    data = {}
    for k, p in ARMS.items():
        rows = load(p)
        data[k] = rows
        s = summarize(k, rows)
        if s:
            tot_r += s["usd"]
            tot_j += s["judge"]
    print(f"\n读者侧合计 ${tot_r:.3f} + 判官侧(实测均价×行数)${tot_j:.3f} "
          f"= ${tot_r + tot_j:.3f}")
    print("\n=== 配对比较(簇=链 uid)===")
    for a, b in [("smoc", "ledgerplain"), ("smoc", "direct"),
                 ("smoc", "fullplain"), ("ledgerplain", "direct"),
                 ("fullplain", "direct"), ("smoc", "closedbook"),
                 ("direct", "closedbook"), ("fullplain", "closedbook")]:
        if data.get(a) and data.get(b):
            compare(f"{a} vs {b}", data[a], data[b])
    print("\n=== 与 haiku-4.5 行(v2.4,576)对照 ===")
    for k, hv in HAIKU.items():
        if data.get(k):
            n = len(data[k])
            acc = 100.0 * sum(1 for r in data[k]
                              if r.get("judge_correct")) / n
            print(f"  {k:12s} gemini {acc:6.2f} (n={n})  haiku {hv:6.2f}  "
                  f"Δ={acc - hv:+.2f}pp")
    print("\n=== 逐题型 ===")
    for k, rows in data.items():
        if not rows:
            continue
        by = defaultdict(lambda: [0, 0])
        for r in rows:
            c = by[r.get("question_type")]
            c[0] += bool(r.get("judge_correct"))
            c[1] += 1
        print(f"  {k:12s}", {t: f"{v[0]}/{v[1]}={v[0] / v[1] * 100:.1f}"
                             for t, v in sorted(by.items())})


if __name__ == "__main__":
    main()
