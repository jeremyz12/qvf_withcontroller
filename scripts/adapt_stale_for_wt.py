# -*- coding: utf-8 -*-
"""STALE-400 → chain-schema 适配器(供 wt-QVF 流水线直接使用)。

金答案逐字克隆 eval/stale_dataset.py 的构造式,保证与既有直读/读取时 QVF
修正协议臂同判官同口径;会话保留全部轮次(user/assistant 前缀文本)。"""
import json
import sys
from pathlib import Path

SRC = Path(r"data/stale_T1_T2_400_FULL.json")
OUT = Path(r"data/stale400_s50_wt.json")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50

data = json.loads(SRC.read_text(encoding="utf-8"))[:N]
out = []
for item in data:
    uid = item["uid"]
    timestamps = item.get("timestamps", [])
    sessions = []
    for i, sess in enumerate(item.get("haystack_session", [])):
        date = (timestamps[i][:10] if i < len(timestamps) else "undated")
        turns = [f"{t.get('role', '?')}: {t.get('content', '')}" for t in sess]
        sessions.append({"date": date, "turns": turns, "chain_index": None})
    gold = (
        f"The user's state has been UPDATED: {item.get('explanation', '')} "
        f"A correct response must reflect the new state "
        f"(new memory: \"{item.get('M_new', '')}\") and must NOT present the "
        f"old state (\"{item.get('M_old', '')}\") as current."
    )
    pq = item.get("probing_queries") or {}
    queries = {}
    for src_key, new_key in [("dim1_query", "dim1_still"),
                             ("dim2_query", "dim2_premise"),
                             ("dim3_query", "dim3_natural")]:
        if pq.get(src_key):
            queries[new_key] = {"q": pq[src_key], "gold": gold}
    old_idx, new_idx = (item.get("relevant_session_index") or [0, 0])[:2]
    chain = [
        {"value": item.get("M_old", ""), "date": timestamps[old_idx][:10],
         "state_span": item.get("M_old", "")},
        {"value": item.get("M_new", ""), "date": timestamps[new_idx][:10],
         "state_span": item.get("M_new", "")},
    ]
    out.append({"uid": uid, "type": "STALE400", "slot": "user state",
                "chain": chain, "sessions": sessions, "probing_queries": queries})
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"adapted {len(out)} items -> {OUT}")
