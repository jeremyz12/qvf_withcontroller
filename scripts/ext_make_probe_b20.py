# -*- coding: utf-8 -*-
"""批 20 采样器:MemConflict 已建卡 10 店内的新鲜 conditional 题(seed=20,
排除批 17 探针已用 qid)。协议同批 17:cutoff=session_date,题面注入
"(Today is X.)"。产物:data/external/memconflict_probe_b20.jsonl(40 题)。
用法: python scripts/ext_make_probe_b20.py
"""
import json
import random
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
EXT = ROOT / "data/external"
rng = random.Random(20)

carded = {json.loads(l)["uid"] for l in
          open(EXT / "memconflict_probe.jsonl", encoding="utf-8") if l.strip()}
used_qids = {json.loads(l)["qid"] for l in
             open(EXT / "memconflict_probe.jsonl", encoding="utf-8") if l.strip()}
mc = json.loads((EXT / "memconflict_unified.json").read_text(encoding="utf-8"))
pool = []
for s in mc:
    if s["uid"] not in carded:
        continue
    for q in s["questions"]:
        if q["dim"] == "conditional" and q["qid"] not in used_qids:
            q["_uid"] = s["uid"]
            pool.append(q)
print(f"fresh conditional pool in 10 carded stores: {len(pool)}")
got = rng.sample(pool, 40)
with open(EXT / "memconflict_probe_b20.jsonl", "w", encoding="utf-8") as f:
    for q in got:
        cut = q["meta"]["session_date"]
        f.write(json.dumps({
            "uid": q["_uid"], "qid": q["qid"], "qtype": q["dim"],
            "question": f"(Today is {cut}.) " + q["question"],
            "gold": q["gold"], "cutoff": cut, "meta": q["meta"]},
            ensure_ascii=False) + "\n")
from collections import Counter
print("40 题分布(店):", dict(Counter(q["_uid"] for q in got)))
