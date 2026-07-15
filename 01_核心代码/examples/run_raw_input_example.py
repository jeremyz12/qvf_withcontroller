from __future__ import annotations

import json

from qvf_validity_admission import run_raw_memory_validity_controller


def build_request() -> dict:
    old_claim = "The calibration plate had one active storage bay: bay 2."
    new_claim = (
        "The calibration plate has one active storage bay; this update "
        "replaces bay 2 with bay 7 effective 10 January 2026."
    )
    return {
        "request_id": "example_current_storage_bay",
        "query": {
            "query_id": "example_query",
            "text": "What is the current storage bay for the calibration plate?",
            "entity": "calibration plate",
            "slot": "storage bay",
            "needs_current": True,
            "as_of": "2026-02-01T00:00:00+00:00",
        },
        "retrieved_memories": [
            {
                "memory_id": "old_inventory_note",
                "text": old_claim,
                "source_type": "inventory_log",
                "observed_at": "2025-01-10T10:00:00+00:00",
                "source_confidence": 0.96,
                "retrieval_rank": 1,
                "structured_records": [
                    {
                        "memory_id": "old_storage_bay",
                        "entity": "calibration plate",
                        "slot": "storage bay",
                        "value": "bay 2",
                        "claim": old_claim,
                        "source_span": old_claim,
                        "slot_cardinality": "single",
                        "slot_cardinality_evidence": "one active storage bay",
                    }
                ],
            },
            {
                "memory_id": "new_inventory_note",
                "text": new_claim,
                "source_type": "inventory_log",
                "observed_at": "2026-01-10T10:00:00+00:00",
                "source_confidence": 0.97,
                "retrieval_rank": 2,
                "structured_records": [
                    {
                        "memory_id": "new_storage_bay",
                        "entity": "calibration plate",
                        "slot": "storage bay",
                        "value": "bay 7",
                        "claim": new_claim,
                        "source_span": new_claim,
                        "slot_cardinality": "single",
                        "slot_cardinality_evidence": "one active storage bay",
                        "temporal_relation": "replacement",
                        "temporal_relation_evidence": "replaces",
                        "relation_target_memory_ids": ["old_storage_bay"],
                        "effective_from": "2026-01-10T00:00:00+00:00",
                        "effective_from_evidence": "10 January 2026",
                    }
                ],
            },
        ],
    }


if __name__ == "__main__":
    output = run_raw_memory_validity_controller(build_request(), selective=False)
    print(json.dumps(output, ensure_ascii=False, indent=2))
