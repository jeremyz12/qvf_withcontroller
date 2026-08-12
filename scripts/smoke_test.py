"""End-to-end smoke test on a synthetic knowledge-update scenario.

The scenario is the canonical QVF motivating case: an older memory ("works at
Google") is superseded by a newer one ("moved to Anthropic") — but only for
*current-state* questions. A historical question must still be answered from
the older memory, which is exactly what query-conditioned validity means.

Runs in mock mode (QVF_MOCK=1, no API needed) to validate plumbing, or in real
mode when Anthropic API credentials are available.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.pipeline import BaselinePipeline, QVFPipeline
from qvf.retrieval import MemoryItem

MEMORIES = [
    MemoryItem(
        memory_id="m1",
        content="user: I just started a new job at Google as a software engineer!\n"
        "assistant: Congratulations on joining Google!",
        metadata={"session_id": "s1", "session_date": "2023-05-02"},
    ),
    MemoryItem(
        memory_id="m2",
        content="user: I usually bike to work, except when it rains — then I take the shuttle.\n"
        "assistant: That sounds like a nice routine.",
        metadata={"session_id": "s2", "session_date": "2023-08-15"},
    ),
    MemoryItem(
        memory_id="m3",
        content="user: Big news — I left Google and moved to Anthropic last week.\n"
        "assistant: Exciting move! How is the new role?",
        metadata={"session_id": "s3", "session_date": "2024-03-10"},
    ),
    MemoryItem(
        memory_id="m4",
        content="user: My sister works at a bakery downtown.\n"
        "assistant: Nice, does she bring home pastries?",
        metadata={"session_id": "s4", "session_date": "2024-01-20"},
    ),
]

QUESTIONS = [
    ("Where does the user work now?", "2024-06-01"),
    ("Where did the user work in June 2023?", "2024-06-01"),
    ("How does the user usually get to work?", "2024-06-01"),
]


def main() -> int:
    mock = os.environ.get("QVF_MOCK", "0") == "1"
    print(f"Running smoke test (mock={mock})\n")

    qvf_pipe = QVFPipeline(top_k=4)
    base_pipe = BaselinePipeline(top_k=4)

    for question, qdate in QUESTIONS:
        print("=" * 72)
        print(f"Q: {question}   (query date: {qdate})")

        base = base_pipe.answer(question, MEMORIES, qdate)
        print(f"[baseline] {base.answer}")

        result = qvf_pipe.answer(question, MEMORIES, qdate)
        print(f"[qvf     ] {result.answer}")

        vmap = result.validity_map
        if vmap is not None:
            print(f"  sufficiency: {vmap.sufficiency.value}  "
                  f"risks: {[r.value for r in vmap.risk_flags]}")
            for c in vmap.claims:
                print(
                    f"  claim {c.claim_id} [{c.memory_id}] "
                    f"{c.applicability.value}/{c.temporal_label.value} "
                    f"roles={[r.value for r in c.roles]} :: {c.normalized_claim[:70]}"
                )
            for r in vmap.relations:
                print(
                    f"  rel {r.source_claim_id} -{r.relation.value}-> "
                    f"{r.target_claim_id} :: {r.rationale[:70]}"
                )
        if result.adapter_warnings:
            print(f"  WARNINGS: {result.adapter_warnings}")
        print()

    print("Smoke test finished without exceptions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
