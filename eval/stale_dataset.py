"""Loader for the STALE benchmark (arXiv 2605.06527, HF: STALEproj/STALE).

Each of the 400 items carries:
- M_old / M_new: the exact old/new memory statement pair (in-data oracle pairing)
- explanation: the changed slot in structured form, e.g.
  "Spatiotemporal_Context.location(city) is now Austin."
- probing_queries: three dimensions —
    dim1: direct state resolution ("does the user still live in Seattle?")
    dim2: stale premise embedded in the question
    dim3: implicit/actionable (must silently use the updated state)
- haystack_session: ~50 sessions of {role, content} turns
- timestamps: per-session datetimes; relevant_session_index: [old_idx, new_idx]

We map each (item, dim) to one QAInstance. The gold answer encodes the updated
state; the judge should count a response correct iff it reflects the NEW state
and does not treat the OLD state as current. The in-data M_old/M_new pair also
lets an oracle-extraction condition be built without any hand-written adapter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.datasets import QAInstance
from qvf.retrieval import MemoryItem

DIMS = ("dim1_query", "dim2_query", "dim3_query")


def _rounds_from_session(session_turns: List[dict]) -> List[str]:
    rounds: List[str] = []
    current: List[str] = []
    for turn in session_turns:
        role = turn.get("role", "user")
        current.append(f"{role}: {turn.get('content', '')}")
        if role == "assistant":
            rounds.append("\n".join(current))
            current = []
    if current:
        rounds.append("\n".join(current))
    return rounds


def load_stale(
    path: str | Path,
    dims: Optional[List[str]] = None,
    limit_items: int = 0,
    item_offset: int = 0,
) -> List[QAInstance]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if item_offset:
        data = data[item_offset:]
    if limit_items:
        data = data[:limit_items]
    use_dims = dims or list(DIMS)

    instances: List[QAInstance] = []
    for item in data:
        uid = item["uid"]
        sessions = item.get("haystack_session", [])
        timestamps = item.get("timestamps", [])
        old_idx, new_idx = (item.get("relevant_session_index") or [None, None])[:2]

        memories: List[MemoryItem] = []
        for s_idx, session in enumerate(sessions):
            sdate = timestamps[s_idx] if s_idx < len(timestamps) else None
            for r_idx, round_text in enumerate(_rounds_from_session(session)):
                memories.append(
                    MemoryItem(
                        memory_id=f"{uid[:8]}/s{s_idx}#r{r_idx}",
                        content=round_text,
                        metadata={
                            "session_id": f"s{s_idx}",
                            "session_date": sdate,
                            "round_index": r_idx,
                        },
                    )
                )

        # Query time = after the last session, so the updated state is current.
        query_date = timestamps[-1] if timestamps else None
        gold = (
            f"The user's state has been UPDATED: {item.get('explanation', '')} "
            f"A correct response must reflect the new state "
            f"(new memory: \"{item.get('M_new', '')}\") and must NOT present the "
            f"old state (\"{item.get('M_old', '')}\") as current."
        )

        for dim in use_dims:
            query = (item.get("probing_queries") or {}).get(dim)
            if not query:
                continue
            instances.append(
                QAInstance(
                    question_id=f"{uid}_{dim}",
                    question=query,
                    gold_answer=gold,
                    memories=memories,
                    question_date=str(query_date) if query_date else None,
                    question_type=f"stale-{dim.replace('_query', '')}",
                    is_abstention=False,
                    extra={
                        "M_old": item.get("M_old"),
                        "M_new": item.get("M_new"),
                        "explanation": item.get("explanation"),
                        "old_session_index": old_idx,
                        "new_session_index": new_idx,
                        "stale_type": item.get("type"),
                    },
                )
            )
    return instances


if __name__ == "__main__":
    instances = load_stale("data/stale_T1_T2_400_FULL.json", limit_items=3)
    print(f"loaded {len(instances)} instances from 3 items")
    inst = instances[0]
    print("qid:", inst.question_id)
    print("type:", inst.question_type)
    print("memories:", len(inst.memories))
    print("query:", inst.question[:100])
    print("gold:", inst.gold_answer[:160])
