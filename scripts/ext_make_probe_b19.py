# -*- coding: utf-8 -*-
"""批 19 新鲜扩样采样器(seed=19,排除批 17 已采店)。
STALE +40 店×3 维 =120 题;MemOps +40 店(5 操作类×8)×3 probe =120 题。
产物:data/external/<arena>_probe_b19.jsonl + <arena>_cardable_b19.json。
用法: python scripts/ext_make_probe_b19.py
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
EXT = ROOT / "data/external"
rng = random.Random(19)


def used_uids(probe):
    return {json.loads(l)["uid"] for l in open(EXT / probe, encoding="utf-8")
            if l.strip()}


def last_date(store):
    for s in reversed(store.get("sessions", [])):
        if s.get("date"):
            return s["date"]
    return "2026-01-01"


def write_out(arena, stores, probe_rows):
    for st in stores:
        st["chain"] = [{"date": last_date(st), "value": ""}]
        st["probing_queries"] = {"_placeholder": {"q": "placeholder", "gold": ""}}
    (EXT / f"{arena}_cardable_b19.json").write_text(
        json.dumps(stores, ensure_ascii=False), encoding="utf-8")
    with open(EXT / f"{arena}_probe_b19.jsonl", "w", encoding="utf-8") as f:
        for r in probe_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    chars = sum(len(t) for st in stores for s in st["sessions"]
                for t in s["turns"])
    print(f"{arena}: +{len(stores)} stores, {len(probe_rows)} questions, "
          f"chars {chars:,}; dims "
          f"{dict(Counter(r['qtype'] for r in probe_rows))}", flush=True)


def row(q, uid):
    return {"uid": uid, "qid": q["qid"], "qtype": q["dim"],
            "question": q["question"], "gold": q["gold"],
            "cutoff": "", "meta": q.get("meta", {})}


# ── STALE:+40 店 ────────────────────────────────────
st = json.loads((EXT / "stale_unified.json").read_text(encoding="utf-8"))
old = used_uids("stale_probe.jsonl")
cand = sorted(s["uid"] for s in st if s["uid"] not in old)
pick = set(rng.sample(cand, 40))
stores = [s for s in st if s["uid"] in pick]
rows = [row(q, s["uid"]) for s in stores for q in s["questions"]]
assert len(rows) == 120
write_out("stale", stores, rows)
del st

# ── MemOps:5 操作类 × 8 店 ──────────────────────────
mo = json.loads((EXT / "memops_unified.json").read_text(encoding="utf-8"))
old = used_uids("memops_probe.jsonl")
by_op = defaultdict(list)
for s in mo:
    if s["uid"] in old:
        continue
    qs = [q for q in s["questions"]
          if q["meta"].get("evaluation_setting") == "longitudinal_operation"]
    if not qs:
        continue
    op = Counter(q["dim"] for q in qs).most_common(1)[0][0]
    s["_lqs"] = qs
    by_op[op].append(s)
stores, rows = [], []
for op in sorted(by_op):
    for s in rng.sample(by_op[op], 8):
        stores.append(s)
        cats = defaultdict(list)
        for q in s["_lqs"]:
            cats[q["meta"].get("evaluation_category", "?")].append(q)
        for c in rng.sample(sorted(cats), min(3, len(cats))):
            rows.append(row(rng.choice(cats[c]), s["uid"]))
for s in stores:
    s.pop("_lqs", None)
write_out("memops", stores, rows)
