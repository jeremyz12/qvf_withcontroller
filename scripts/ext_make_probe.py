# -*- coding: utf-8 -*-
"""批 17 探针采样器(预注册 opt_batch17_prereg,seed=17 写死)。
产物:data/external/<arena>_probe.jsonl(题)+ <arena>_cardable.json
(采样店子集,含 load_stale_chain 需要的占位 chain/probing_queries)。
用法: python scripts/ext_make_probe.py
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
EXT = ROOT / "data/external"
rng = random.Random(17)


def last_date(store):
    for s in reversed(store.get("sessions", [])):
        if s.get("date"):
            return s["date"]
    return "2026-01-01"


def write_out(arena, stores, probe_rows):
    for st in stores:
        st["chain"] = [{"date": last_date(st), "value": ""}]
        st["probing_queries"] = {"_placeholder": {"q": "placeholder", "gold": ""}}
    (EXT / f"{arena}_cardable.json").write_text(
        json.dumps(stores, ensure_ascii=False), encoding="utf-8")
    with open(EXT / f"{arena}_probe.jsonl", "w", encoding="utf-8") as f:
        for r in probe_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    chars = sum(len(t) for st in stores for s in st["sessions"]
                for t in s["turns"])
    print(f"{arena}: {len(stores)} stores, {len(probe_rows)} questions, "
          f"card-build chars {chars:,}; dims "
          f"{dict(Counter(r['qtype'] for r in probe_rows))}", flush=True)


def row(q, cutoff=""):
    return {"uid": q["_uid"], "qid": q["qid"], "qtype": q["dim"],
            "question": q["question"], "gold": q["gold"],
            "cutoff": cutoff, "meta": q.get("meta", {})}


# ── MemConflict:10 店;dynamic 30 / static 15 / conditional 15 ──
mc = json.loads((EXT / "memconflict_unified.json").read_text(encoding="utf-8"))
uids = sorted(s["uid"] for s in mc)
pick = set(rng.sample(uids, 10))
stores = [s for s in mc if s["uid"] in pick]
pool = defaultdict(list)
for s in stores:
    for q in s["questions"]:
        q["_uid"] = s["uid"]
        pool[q["dim"]].append(q)
rows = []
for dim, quota in (("dynamic", 30), ("static", 15), ("conditional", 15)):
    got = rng.sample(pool[dim], min(quota, len(pool[dim])))
    for q in got:
        r = row(q, cutoff=q["meta"]["session_date"])
        # 官方增量协议:题在 session_date 当场提出。两臂同文注入日期,
        # 直读臂 _TODAY_RE 自动提取为 TODAY'S DATE。
        r["question"] = f"(Today is {r['cutoff']}.) " + r["question"]
        rows.append(r)
write_out("memconflict", stores, rows)
del mc

# ── STALE:20 店 × 3 维 ─────────────────────────────────
st = json.loads((EXT / "stale_unified.json").read_text(encoding="utf-8"))
uids = sorted(s["uid"] for s in st)
pick = set(rng.sample(uids, 20))
stores = [s for s in st if s["uid"] in pick]
rows = []
for s in stores:
    for q in s["questions"]:
        q["_uid"] = s["uid"]
        rows.append(row(q))
assert len(rows) == 60
write_out("stale", stores, rows)
# 全文参考臂子样:每维 7/7/6
by_dim = defaultdict(list)
for r in rows:
    by_dim[r["qtype"]].append(r)
sub = []
for dim, k in zip(sorted(by_dim), (7, 7, 6)):
    sub += rng.sample(by_dim[dim], k)
with open(EXT / "stale_fullctx_probe.jsonl", "w", encoding="utf-8") as f:
    for r in sub:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"stale-fullctx sub-probe: {len(sub)} questions", flush=True)
del st

# ── MemOps:5 操作类 × 4 店,每店 3 probe(longitudinal) ──
mo = json.loads((EXT / "memops_unified.json").read_text(encoding="utf-8"))
by_op = defaultdict(list)
for s in mo:
    qs = [q for q in s["questions"]
          if q["meta"].get("evaluation_setting") == "longitudinal_operation"]
    if not qs:
        continue
    op = Counter(q["dim"] for q in qs).most_common(1)[0][0]
    s["_lqs"] = qs
    by_op[op].append(s)
stores, rows = [], []
for op in sorted(by_op):
    for s in rng.sample(by_op[op], 4):
        stores.append(s)
        qs = s["_lqs"]
        cats = defaultdict(list)
        for q in qs:
            cats[q["meta"].get("evaluation_category", "?")].append(q)
        picked_cats = rng.sample(sorted(cats), min(3, len(cats)))
        for c in picked_cats:
            q = rng.choice(cats[c])
            q["_uid"] = s["uid"]
            rows.append(row(q))
for s in stores:
    s.pop("_lqs", None)
write_out("memops", stores, rows)
