"""Loader for STALE-Chain: multi-state evolution extension of STALE
(our CC BY 4.0 derivative; see scripts/gen_stale_chain.py).

Each item: one slot evolving through 3-5 dated states embedded among
distractor sessions; four probing dimensions —
  dim1_current        current state (gold = last state)
  dim2_premise_mid    question presupposes an INTERMEDIATE state (gold = last)
  dim4_point_in_time  state at a date between two updates (gold = intermediate)
  dim5_trajectory     how the state changed (gold = ordered chain)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.datasets import QAInstance
from qvf.retrieval import MemoryItem


def load_stale_chain(path: str | Path, limit_items: int = 0,
                     item_offset: int = 0) -> List[QAInstance]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if item_offset:
        data = data[item_offset:]
    if limit_items:
        data = data[:limit_items]

    instances: List[QAInstance] = []
    for item in data:
        uid = item["uid"]
        memories: List[MemoryItem] = []
        for si, sess in enumerate(item.get("sessions", [])):
            for ri, turn in enumerate(sess.get("turns", [])):
                memories.append(MemoryItem(
                    memory_id=f"{uid}/s{si}#r{ri}",
                    content=str(turn),
                    metadata={"session_id": f"s{si}",
                              "session_date": sess.get("date", "")},
                ))
        last_date = item["chain"][-1]["date"]
        # Query date: one month after the final update.
        y, m, d = (int(x) for x in last_date.split("-"))
        m += 1
        if m > 12:
            y, m = y + 1, 1
        qdate = f"{y}-{m:02d}-{d:02d}"
        for dim, q in item.get("probing_queries", {}).items():
            instances.append(QAInstance(
                question_id=f"{uid}_{dim}_query",
                question=q["q"],
                gold_answer=q["gold"],
                memories=memories,
                question_date=qdate,
                question_type=f"chain-{dim}",
                extra={
                    "slot": item.get("slot"),
                    "chain_values": [s["value"] for s in item["chain"]],
                    "chain_dates": [s["date"] for s in item["chain"]],
                    "presupposed": q.get("presupposed"),
                    "point_date": q.get("date"),
                },
            ))
    return instances
