from __future__ import annotations

import unittest

from qvf_validity_admission import run_raw_memory_validity_controller


class CoreSmokeTests(unittest.TestCase):
    def test_raw_controller_runs_without_api_and_blocks_old_current_value(self) -> None:
        old_claim = "The device had one active owner: team A."
        new_claim = (
            "The device has one active owner; this update replaces team A "
            "with team B effective 2 March 2026."
        )
        request = {
            "request_id": "smoke_owner_change",
            "query": {
                "query_id": "smoke_query",
                "text": "Which team currently owns the device?",
                "entity": "device",
                "slot": "active owner",
                "needs_current": True,
                "as_of": "2026-04-01T00:00:00+00:00",
            },
            "retrieved_memories": [
                {
                    "memory_id": "raw_old",
                    "text": old_claim,
                    "observed_at": "2025-03-02T00:00:00+00:00",
                    "source_confidence": 0.95,
                    "structured_records": [{
                        "memory_id": "owner_old",
                        "entity": "device",
                        "slot": "active owner",
                        "value": "team A",
                        "claim": old_claim,
                        "source_span": old_claim,
                        "slot_cardinality": "single",
                        "slot_cardinality_evidence": "one active owner",
                    }],
                },
                {
                    "memory_id": "raw_new",
                    "text": new_claim,
                    "observed_at": "2026-03-02T00:00:00+00:00",
                    "source_confidence": 0.97,
                    "structured_records": [{
                        "memory_id": "owner_new",
                        "entity": "device",
                        "slot": "active owner",
                        "value": "team B",
                        "claim": new_claim,
                        "source_span": new_claim,
                        "slot_cardinality": "single",
                        "slot_cardinality_evidence": "one active owner",
                        "temporal_relation": "replacement",
                        "temporal_relation_evidence": "replaces",
                        "relation_target_memory_ids": ["owner_old"],
                        "effective_from": "2026-03-02T00:00:00+00:00",
                        "effective_from_evidence": "2 March 2026",
                    }],
                },
            ],
        }

        output = run_raw_memory_validity_controller(request, selective=False)

        self.assertTrue(output["controller_executed"])
        self.assertEqual(output["api_calls_made"], 0)
        self.assertEqual(output["extraction_report"]["rejected_record_count"], 0)
        rendered = str(output["controller_decisions"])
        self.assertIn("owner_old", rendered)
        self.assertIn("owner_new", rendered)


if __name__ == "__main__":
    unittest.main()
