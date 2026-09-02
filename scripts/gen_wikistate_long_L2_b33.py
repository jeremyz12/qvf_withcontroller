# -*- coding: utf-8 -*-
"""批 33-D:把 L2(≈440K 字符)店从 15 个扩到 30 个(确定性,零 LLM)。

背景:批 27 的 gen_wikistate_long.py 从 v2 语料抽 30 个 uid 建 L1(160K),
再从中抽 15 个建 L2(440K),再从中抽 10 个建卡(data/b27_probe_uids.txt)。
33-D 预注册要"30 店 / n=120",但 data/wikistate_long_L2.json 只有 15 店,
缺的 15 个 uid = L1 里未被抽进 L2 的那 15 个。本脚本用**逐字同一构造**
(同底料、同干扰池、同安全闸、同 440,000 字符目标)把它们补齐,
产出 data/wikistate_long_L2_b33.json = 15 条原样复制 + 15 条新建。

RNG:random.Random(3327)(批 27 用 27;新种子只影响新建 15 店的干扰会话抽样,
原 15 店逐字节复制,不重建)。

用法: PYTHONUTF8=1 python -u scripts/gen_wikistate_long_L2_b33.py
"""
import json
import random
import statistics
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
rng = random.Random(3327)
L2_CHARS = 440_000

src = json.loads((ROOT / "data/wikistate_full_ALL_fmtnorm.json").read_text(
    encoding="utf-8"))
by_uid = {e["uid"]: e for e in src}

all_spans = [r.get("state_span") or "" for e in src for r in e.get("chain", [])]
all_spans = [s for s in all_spans if s]

pool = []
for e in src:
    for s in e.get("sessions", []):
        if s.get("chain_index") is None:
            txt = "\n".join(str(t) for t in s.get("turns", []))
            if any(sp in txt for sp in all_spans):
                continue  # 安全闸:含任何店锚点句的会话不入池
            pool.append((e["uid"], s))
print(f"干扰池(安全闸后): {len(pool)}")

L1 = json.loads((ROOT / "data/wikistate_long_L1.json").read_text(
    encoding="utf-8"))
L2 = json.loads((ROOT / "data/wikistate_long_L2.json").read_text(
    encoding="utf-8"))
l1_uids = [e["uid"] for e in L1]
l2_uids = {e["uid"] for e in L2}
todo = sorted(u for u in l1_uids if u not in l2_uids)
print(f"L1 {len(l1_uids)} 店 / 已有 L2 {len(l2_uids)} 店 / 待建 {len(todo)} 店")
assert len(todo) == 15, todo


def store_chars(e):
    return sum(len(str(t)) for s in e["sessions"] for t in s["turns"])


def build(target_chars, uids):
    out = []
    for uid in uids:
        e = json.loads(json.dumps(by_uid[uid]))
        cur = store_chars(e)
        cand = [(ou, s) for ou, s in pool if ou != uid]
        rng.shuffle(cand)
        i = 0
        while cur < target_chars and i < len(cand):
            _, s = cand[i]
            i += 1
            sc = json.loads(json.dumps(s))
            e["sessions"].append(sc)
            cur += sum(len(str(t)) for t in sc["turns"])
        out.append(e)
    return out


NEW = build(L2_CHARS, todo)
ALL30 = L2 + NEW           # 前 15 = 原档逐字节;后 15 = 新建
out_p = ROOT / "data/wikistate_long_L2_b33.json"
out_p.write_text(json.dumps(ALL30, ensure_ascii=False), encoding="utf-8")

# ── 核验 ───────────────────────────────────────────────────────────────
cs_old = [store_chars(e) for e in L2]
cs_new = [store_chars(e) for e in NEW]
print(f"原 15 店字符 中位 {statistics.median(cs_old):,.0f} "
      f"(min {min(cs_old):,} max {max(cs_old):,})")
print(f"新 15 店字符 中位 {statistics.median(cs_new):,.0f} "
      f"(min {min(cs_new):,} max {max(cs_new):,})")
print(f"新 15 店会话数 中位 {statistics.median([len(e['sessions']) for e in NEW]):.0f}"
      f" / 原 {statistics.median([len(e['sessions']) for e in L2]):.0f}")

bad = 0            # 锚点完好闸
for e in NEW:
    alltxt = "\n".join(str(t) for s in e["sessions"] for t in s["turns"])
    for r in e.get("chain", []):
        sp = r.get("state_span") or ""
        if sp and sp not in alltxt:
            bad += 1
print(f"锚点完好闸(新 15 店): 违约 {bad}")

leak = 0           # 安全闸复核:填充会话不得含任何店的 state_span
for e in NEW:
    for s in e["sessions"]:
        if s.get("chain_index") is not None:
            continue
        txt = "\n".join(str(t) for t in s["turns"])
        if any(sp in txt for sp in all_spans):
            leak += 1
print(f"填充安全闸(新 15 店): 泄漏会话 {leak}")

assert len(ALL30) == 30 and len({e['uid'] for e in ALL30}) == 30
print(f"写出 {out_p} = {len(ALL30)} 店")
