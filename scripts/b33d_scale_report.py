# -*- coding: utf-8 -*-
"""批 33-D 规模轴 L2(30 店 / n=120)汇总:三臂 × 准确率 / 均输入 tok /
$/题 / 延迟,配对 McNemar,与同题小库(L0)对照,判据 D1-D3。

用法: PYTHONUTF8=1 python -u scripts/b33d_scale_report.py
"""
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
HAIKU_IN, HAIKU_OUT = 0.80 / 1e6, 4.00 / 1e6      # $/token
GPT5MINI_IN, GPT5MINI_OUT = 0.25 / 1e6, 2.00 / 1e6

STORES = json.loads((ROOT / "data/wikistate_long_L2_b33.json").read_text(
    encoding="utf-8"))
U30 = [e["uid"] for e in STORES]
U15_OLD = set(U30[:15])
U15_NEW = set(U30[15:])
U10 = set((ROOT / "data/b27_probe_uids.txt").read_text(
    encoding="utf-8").split())


def load(*paths):
    rows = {}
    for p in paths:
        f = ROOT / p
        if not f.exists():
            print(f"  [缺] {p}")
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["question_id"]] = r
    return rows


def stat(rows, uids=None, price=(HAIKU_IN, HAIKU_OUT)):
    rs = [r for r in rows.values() if uids is None or r["uid"] in uids]
    if not rs:
        return None
    n = len(rs)
    acc = 100 * sum(bool(r["judge_correct"]) for r in rs) / n
    mi = statistics.mean(r["usage_input_tokens"] for r in rs)
    mo = statistics.mean(r["usage_output_tokens"] for r in rs)
    lat = statistics.mean(r["latency_s"] for r in rs)
    cpq = mi * price[0] + mo * price[1]
    by = defaultdict(list)
    for r in rs:
        by[r["question_type"]].append(bool(r["judge_correct"]))
    qt = {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by.items())}
    return dict(n=n, acc=acc, mi=mi, mo=mo, lat=lat, cpq=cpq, qt=qt,
                tot=sum(r["usage_input_tokens"] * price[0]
                        + r["usage_output_tokens"] * price[1] for r in rs))


def mcnemar(a, b, uids=None):
    """a、b 为 qid->row;返回 (b_only, c_only, p 双侧精确)。"""
    ks = [k for k in a if k in b and (uids is None or a[k]["uid"] in uids)]
    bb = sum(1 for k in ks if a[k]["judge_correct"] and not b[k]["judge_correct"])
    cc = sum(1 for k in ks if not a[k]["judge_correct"] and b[k]["judge_correct"])
    n = bb + cc
    if n == 0:
        return bb, cc, 1.0, len(ks)
    p = sum(math.comb(n, i) for i in range(0, min(bb, cc) + 1)) / 2 ** n * 2
    return bb, cc, min(1.0, p), len(ks)


def line(tag, s):
    if s is None:
        return f"| {tag} | — | — | — | — | — |"
    return (f"| {tag} | {s['n']} | {s['acc']:.1f} | {s['mi']:,.0f} | "
            f"{s['cpq']:.4f} | {s['lat']:.2f} |")


ARMS = {
    "smoc(全账目)": load("results/b33d_smoc_L2_old10_repro.jsonl",
                          "results/b33d_smoc_L2_new20.jsonl"),
    "slot(槽位投影)": load("results/b33_smoc_L2probe_slot.jsonl",
                            "results/b33d_slot_L2_new20.jsonl"),
    "haiku 全文": load("results/b27_full_haiku_L2.jsonl",
                       "results/b33d_full_haiku_L2_new15.jsonl"),
}
GPT = load("results/b27_full_gpt_L2.jsonl")

print("\n## L2(≈104K tok/店)30 店 × 4 题 = 120\n")
print("| 臂 | n | 准确率 | 均输入 tok | $/题 | 延迟 s |")
print("|---|---|---|---|---|---|")
S = {}
for k, v in ARMS.items():
    S[k] = stat(v)
    print(line(k, S[k]))
S["gpt-5-mini 全文"] = stat(GPT, price=(GPT5MINI_IN, GPT5MINI_OUT))
print(line("gpt-5-mini 全文(仅原 15 店)", S["gpt-5-mini 全文"]))

print("\n### 逐题型")
for k in ARMS:
    if S[k]:
        print(f"- {k}: {S[k]['qt']}")

print("\n### 分层(原 15 店 / 新 15 店)")
print("| 臂 | 原15店 acc | 原15店 tok | 新15店 acc | 新15店 tok |")
print("|---|---|---|---|---|")
for k, v in ARMS.items():
    a, b = stat(v, U15_OLD), stat(v, U15_NEW)
    print(f"| {k} | {a['acc']:.1f} ({a['n']}) | {a['mi']:,.0f} | "
          f"{b['acc']:.1f} ({b['n']}) | {b['mi']:,.0f} |" if a and b else
          f"| {k} | — | — | — | — |")

print("\n### 与批 27/33 探针(原 10 店 40 题)复现核对")
for k, v in ARMS.items():
    s = stat(v, U10)
    if s:
        print(f"- {k} @10店(本轮): acc {s['acc']:.1f}, in {s['mi']:,.0f}")
ARC = {"smoc(存档 b27 探针)": load("results/b27_smoc_L2probe.jsonl"),
       "slot(存档 b33 探针)": load("results/b33_smoc_L2probe_slot.jsonl"),
       "haiku 全文(存档 b27)": load("results/b27_full_haiku_L2.jsonl")}
for k, v in ARC.items():
    s = stat(v, U10)
    if s:
        print(f"- {k} @10店: acc {s['acc']:.1f}, in {s['mi']:,.0f}")
b, c, p, n = mcnemar(ARC["smoc(存档 b27 探针)"], ARMS["smoc(全账目)"], U10)
print(f"- smoc 存档 vs 本轮重跑(同 10 店 40 题): b/c={b}/{c}, p={p:.3g}")

print("\n### 配对 McNemar(120 题)")
for x, y in (("smoc(全账目)", "slot(槽位投影)"),
             ("smoc(全账目)", "haiku 全文"),
             ("slot(槽位投影)", "haiku 全文")):
    b, c, p, n = mcnemar(ARMS[x], ARMS[y])
    print(f"- {x} vs {y}: b/c={b}/{c}, p={p:.3g} (n={n})")

# ── 小库(L0)同题对照 ────────────────────────────────────────────────
print("\n### 同题小库(L0,v43 店)对照")
L0 = {"smoc(全账目)": load("results/wsc_v2_smoc_v43.jsonl"),
      "slot(槽位投影)": load("results/wsc_v2_smoc_v43_slot.jsonl")}
print("| 臂 | L0 30店 acc | L0 tok | L0 $/题 | L2 acc | L2 tok | Δacc | tok 倍数 |")
print("|---|---|---|---|---|---|---|---|")
for k in L0:
    a = stat(L0[k], set(U30))
    b = S[k]
    if a and b:
        print(f"| {k} | {a['acc']:.1f} | {a['mi']:,.0f} | {a['cpq']:.4f} | "
              f"{b['acc']:.1f} | {b['mi']:,.0f} | {b['acc'] - a['acc']:+.1f} | "
              f"{b['mi'] / a['mi']:.2f}× |")
        print(f"|   └ 10 店口径 | {stat(L0[k], U10)['acc']:.1f} | "
              f"{stat(L0[k], U10)['mi']:,.0f} | — | — | — | — | — |")

# ── 判据 ────────────────────────────────────────────────────────────
print("\n### 判据 D1-D3")
sm, sl, fp = S["smoc(全账目)"], S["slot(槽位投影)"], S["haiku 全文"]
l0 = stat(L0["smoc(全账目)"], set(U30))
if sm and l0:
    print(f"- D1 账目 acc ≥ 小库同题 −20pp:L2 {sm['acc']:.1f} vs L0 "
          f"{l0['acc']:.1f} → Δ {sm['acc'] - l0['acc']:+.1f}pp,"
          f"{'通过' if sm['acc'] >= l0['acc'] - 20 else '不通过'}")
if sm:
    print(f"- D2 账目读取 ≤ 25K tok:{sm['mi']:,.0f} → "
          f"{'通过' if sm['mi'] <= 25000 else '不通过'}")
if sm and fp:
    print(f"- D3 $/题 vs haiku 全文 ≥ 3×:{fp['cpq'] / sm['cpq']:.2f}× → "
          f"{'通过' if fp['cpq'] / sm['cpq'] >= 3 else '不通过'}"
          f"(投影 {fp['cpq'] / sl['cpq']:.2f}×)")
g = S["gpt-5-mini 全文"]
if g and sm:
    print(f"- vs gpt-5-mini 全文(无阈值,仅原 15 店口径):"
          f"$/题 {g['cpq']:.4f} vs 账目 {sm['cpq']:.4f} = "
          f"{g['cpq'] / sm['cpq']:.2f}×;acc {g['acc']:.1f} vs {sm['acc']:.1f}")

# ── 成本 ────────────────────────────────────────────────────────────
print("\n### 本轮实付(usage token 口径)")
tot = 0.0
RUN = {"smoc 全账目(120,含 10 店重跑)":
       load("results/b33d_smoc_L2_old10_repro.jsonl",
            "results/b33d_smoc_L2_new20.jsonl"),
       "slot 槽位投影(80 新)": load("results/b33d_slot_L2_new20.jsonl"),
       "haiku 全文(60 新)": load("results/b33d_full_haiku_L2_new15.jsonl")}
for k, v in RUN.items():
    s = stat(v)
    if s:
        print(f"- {k}:{s['n']} 题,in {s['n'] * s['mi']:,.0f} / "
              f"out {s['n'] * s['mo']:,.0f} tok = ${s['tot']:.2f}")
        tot += s["tot"]
bi = bo = 0
for u in sorted(set(U30) - U10):
    f = ROOT / "results/wt_cards_b33_L2" / f"{u}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        bi += d.get("usage_in", 0)
        bo += d.get("usage_out", 0)
bc = bi * HAIKU_IN + bo * HAIKU_OUT
print(f"- 建店 20 个:in {bi:,} / out {bo:,} tok = ${bc:.2f} "
      f"(${bc / 20:.4f}/店)")
print(f"- 读者侧合计 ${tot:.2f};读者+建店 ${tot + bc:.2f}(判官另计)")
