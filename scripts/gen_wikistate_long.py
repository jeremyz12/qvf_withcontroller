# -*- coding: utf-8 -*-
"""批 27:WikiState-Long 构造(确定性,零 LLM)。
底料=归一语料;垫他店纯干扰会话至目标字符量;安全闸=导入会话不含全库
任何 state_span。产出 data/wikistate_long_L{1,2}.json + 题集 + uid 清单。
用法: python scripts/gen_wikistate_long.py
"""
import json
import random
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
rng = random.Random(27)
L1_CHARS, L2_CHARS = 160_000, 440_000

src = json.loads((ROOT / "data/wikistate_full_ALL_fmtnorm.json").read_text(
    encoding="utf-8"))
by_uid = {e["uid"]: e for e in src}

# 全库 span 集(安全闸)
all_spans = [r.get("state_span") or "" for e in src for r in e.get("chain", [])]
all_spans = [s for s in all_spans if s]

# 干扰池:(origin_uid, session)
pool = []
for e in src:
    for s in e.get("sessions", []):
        if s.get("chain_index") is None:
            txt = "\n".join(str(t) for t in s.get("turns", []))
            if any(sp in txt for sp in all_spans):
                continue  # 安全闸:含任何店锚点句的会话不入池
            pool.append((e["uid"], s))
print(f"干扰池(安全闸后): {len(pool)}")

v2_uids = sorted({json.loads(l)["uid"] for l in
                  open(ROOT / "results/wsc_v2_smoc.jsonl", encoding="utf-8")})
pick = rng.sample(v2_uids, 30)
l2_pick = set(rng.sample(pick, 15))
probe_pick = set(rng.sample(sorted(l2_pick), 10))


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

L1 = build(L1_CHARS, pick)
L2 = build(L2_CHARS, sorted(l2_pick))
(ROOT / "data/wikistate_long_L1.json").write_text(
    json.dumps(L1, ensure_ascii=False), encoding="utf-8")
(ROOT / "data/wikistate_long_L2.json").write_text(
    json.dumps(L2, ensure_ascii=False), encoding="utf-8")

qs = [json.loads(l) for l in open(ROOT / "data/wsc_s5_v2.jsonl",
                                  encoding="utf-8")]
with open(ROOT / "data/wsc_long_L1_questions.jsonl", "w",
          encoding="utf-8") as f:
    for q in qs:
        if q["uid"] in set(pick):
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
with open(ROOT / "data/wsc_long_L2_questions.jsonl", "w",
          encoding="utf-8") as f:
    for q in qs:
        if q["uid"] in l2_pick:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
open(ROOT / "data/b27_probe_uids.txt", "w", encoding="utf-8").write(
    "\n".join(sorted(probe_pick)))

# 核验报告
import statistics
for tag, arr in (("L1", L1), ("L2", L2)):
    cs = [store_chars(e) for e in arr]
    ns = [len(e["sessions"]) for e in arr]
    print(f"{tag}: {len(arr)} 店 | 字符 中位 {statistics.median(cs):,.0f} "
          f"(min {min(cs):,} max {max(cs):,}) | 会话数 中位 {statistics.median(ns):.0f}")
# 锚点完好闸:每店金链 span 仍逐字在店内
bad = 0
for arr in (L1, L2):
    for e in arr:
        alltxt = "\n".join(str(t) for s in e["sessions"] for t in s["turns"])
        for r in e.get("chain", []):
            sp = r.get("state_span") or ""
            if sp and sp not in alltxt:
                bad += 1
print(f"锚点完好闸: 违约 {bad}(须为批28豁免例数量级)")
