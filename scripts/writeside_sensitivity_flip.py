# -*- coding: utf-8 -*-
"""T1 条件③ 补充:b6_rep3(最低轮) vs v42(参照)在同 76 题上,code-only 关键值
相对 gold 的"翻转"精确计数(赢/输/两边都对/两边都错/不可判)。"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complex_query_arm import execute_plan, _mem_dates  # noqa: E402
from scripts.writeside_sensitivity_part1 import (  # noqa: E402
    load_entries, load_records, extract_key_value, LIBRARIES, UNION,
)

entries = load_entries()
rows = [json.loads(l) for l in open(UNION, encoding="utf-8")]
by_uid_rows = {}
for r in rows:
    by_uid_rows.setdefault(r["uid"], []).append(r)

b6_uids = set(p.stem for p in LIBRARIES["b6_rep1_78.0"].glob("*.json"))
target_uids = b6_uids & set(by_uid_rows)
gold_map = {r["question_id"]: r.get("gold_answer") for r in rows}


def code_correct(v, g):
    if v is None or g is None:
        return None
    gs = str(g)
    vs = v if isinstance(v, str) else json.dumps(v)
    if isinstance(v, tuple):
        return all(str(x).strip().lower() in gs.lower()
                   or gs.lower() in str(x).strip().lower() for x in v)
    return vs.strip().lower() in gs.lower() or gs.lower() in vs.strip().lower()


results = {}
for lib_name in ("v42_archived_76.88", "b6_rep3_64.0"):
    lib_dir = LIBRARIES[lib_name]
    kv = {}
    for uid in sorted(target_uids):
        mem_dates = _mem_dates(entries[uid])
        recs = load_records(lib_dir, uid) or []
        for r in by_uid_rows[uid]:
            plan = r["plan"]
            ev, derived = execute_plan(plan, recs, mem_dates, r["question"])
            line = derived[0] if derived else ""
            kv[r["question_id"]] = extract_key_value(plan.get("op") or "",
                                                       line)
    results[lib_name] = kv

v42kv = results["v42_archived_76.88"]
b6kv = results["b6_rep3_64.0"]

gained = lost = stay_ok = stay_bad = uncheckable = 0
detail_lost = []
detail_gained = []
for qid, g in gold_map.items():
    if qid not in v42kv:
        continue
    c_v42 = code_correct(v42kv[qid], g)
    c_b6 = code_correct(b6kv[qid], g)
    if c_v42 is None or c_b6 is None:
        uncheckable += 1
        continue
    if c_v42 and not c_b6:
        lost += 1
        detail_lost.append(qid)
    elif c_b6 and not c_v42:
        gained += 1
        detail_gained.append(qid)
    elif c_v42 and c_b6:
        stay_ok += 1
    else:
        stay_bad += 1

n = gained + lost + stay_ok + stay_bad
print(f"checkable questions: {n} (uncheckable/regex-miss: {uncheckable})")
print(f"v42 code-correct -> b6_rep3 code-WRONG (LOST): {lost}  {detail_lost}")
print(f"v42 code-WRONG -> b6_rep3 code-correct (GAINED): {gained}  "
      f"{detail_gained}")
print(f"both code-correct: {stay_ok}")
print(f"both code-wrong: {stay_bad}")
print(f"net flip: {gained - lost:+d} (positive = b6_rep3 code-layer better)")
