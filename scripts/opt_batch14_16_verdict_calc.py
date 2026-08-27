# -*- coding: utf-8 -*-
"""批 14/16 判决计算(预注册 opt_batch14_prereg / opt_batch16_prereg)。
跑完三臂后一键出判决数字;判据逻辑照预注册写死,人不插手。
用法: python scripts/opt_batch14_16_verdict_calc.py
"""
import json
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")


def load(p):
    return [json.loads(l) for l in open(ROOT / p, encoding="utf-8")]


def mcnemar(pairs):
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if not x and y)
    n = b + c
    if n == 0:
        return b, c, 1.0
    p = sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n * 2
    return b, c, min(1.0, p)


def stats(rows):
    n = len(rows)
    acc = sum(1 for r in rows if r["judge_correct"]) / n * 100
    ti = sum(r["usage_input_tokens"] for r in rows) / n
    to = sum(r["usage_output_tokens"] for r in rows) / n
    lat = sorted(r["latency_s"] for r in rows)[n // 2]
    return acc, ti, to, lat


def by_type(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["question_type"]].append(r)
    return {t: sum(1 for r in v if r["judge_correct"]) / len(v) * 100
            for t, v in sorted(d.items())}


# ── 批 14:视图瘦身全量 ──────────────────────────────
ctrl = {r["question_id"]: r for r in load("results/wsc_v2_smoc.jsonl")}
print("=" * 62)
for arm, path in (("B slot", "results/wsc_v2_smoc_slot.jsonl"),
                  ("C slim", "results/wsc_v2_smoc_slim.jsonl")):
    if not (ROOT / path).exists():
        print(f"[批14 {arm}] 文件未就绪,跳过")
        continue
    rows = load(path)
    if len(rows) < 576:
        print(f"[批14 {arm}] {len(rows)}/576 未跑完,跳过")
        continue
    acc, ti, to, lat = stats(rows)
    m = {r["question_id"]: r for r in rows}
    pairs = [(bool(ctrl[q]["judge_correct"]), bool(m[q]["judge_correct"]))
             for q in ctrl]
    b, c, p = mcnemar(pairs)
    print(f"[批14 {arm}] acc {acc:.2f} (ctrl 82.64) | in/q {ti:.0f} "
          f"(ctrl 2539, {ti/2539*100:.0f}%) | out/q {to:.0f} | 中位延迟 {lat}s")
    print(f"    配对 McNemar ctrl对/臂错 b={b}, ctrl错/臂对 c={c}, p={p:.4f}")
    print(f"    分题型: {by_type(rows)}")
    if arm.startswith("B"):
        c1 = acc >= 80.64 and ti <= 1270
        print(f"    判据C1(acc>=80.64 且 tok<=1270): {'过' if c1 else '不过'}")
        tokB = ti
    else:
        c2 = acc >= 80.64 and ti <= 0.7 * tokB
        print(f"    判据C2(acc>=80.64 且 tok<=0.7x tokB={0.7*tokB:.0f}): "
              f"{'过' if c2 else '不过'}")

# ── 批 16:sonnet-5 读者头条 ─────────────────────────
print("=" * 62)
p16 = ROOT / "results/wsc_s5_smoc_sonnet5.jsonl"
if p16.exists():
    rows = load("results/wsc_s5_smoc_sonnet5.jsonl")
    if len(rows) >= 418:
        acc, ti, to, lat = stats(rows)
        trunc = sum(1 for r in rows if r["usage_output_tokens"] >= 1495)
        print(f"[批16] sonnet-5 smoc@418: acc {acc:.2f} | in/q {ti:.0f} "
              f"out/q {to:.0f} | 中位延迟 {lat}s")
        print(f"    截断自查: {trunc}/{len(rows)} = {trunc/len(rows)*100:.1f}% "
              f"(判废线 2%)")
        m = {r["question_id"]: r for r in rows}
        for tag, path in (("run1 87.80", "results/wsc_s5_smoc.jsonl"),
                          ("run2 89.00", "results/wsc_smoc418_rerun_20260826.jsonl")):
            base = {r["question_id"]: r for r in load(path)}
            common = sorted(set(base) & set(m))
            b, c, p = mcnemar([(bool(base[q]["judge_correct"]),
                                bool(m[q]["judge_correct"])) for q in common])
            print(f"    vs {tag} (n={len(common)}): b={b}, c={c}, p={p:.4f}")
        print(f"    分题型: {by_type(rows)}")
        verdict = ("采纳强读者可选配置" if acc >= 90.4 else
                   "中性入档" if acc >= 86.4 else "判负入档")
        print(f"    判据(>=90.4采纳 / 86.4-90.4中性 / <86.4判负): {verdict}"
              f"(p 条件另核)")
    else:
        print(f"[批16] {len(rows)}/418 未跑完,跳过")
else:
    print("[批16] 文件未就绪")
