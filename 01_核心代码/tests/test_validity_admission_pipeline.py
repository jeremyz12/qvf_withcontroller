from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from qvf_validity_admission._pipeline_core import (
    build_method_lock_comparison_summary,
    build_method_lock_summary,
    build_weak_gate_pack_summary,
    enforce_method_lock_match,
    load_jsonl,
    main,
)
from qvf_validity_admission.admission import (
    build_memory_event_adapter_summary,
    build_query_request_adapter_summary,
    normalize_memory_event_payload,
    normalize_query_request_payload,
)
from qvf_validity_admission.decisions import (
    build_query_results,
    build_read_decisions,
    build_read_decisions_from_weak_gate_outputs,
    build_reader_responses,
    route_read_time_packet,
    score_weak_gate_outputs,
)
from qvf_validity_admission.lifecycle import (
    QVFMemoryPipeline,
)
from qvf_validity_admission.memory import (
    ValidityAwareMemoryStore,
)
from qvf_validity_admission.pipeline import (
    run_qvf_service_request,
)
from qvf_validity_admission.retrieval import (
    build_lifecycle_packets,
    build_packets_from_store,
    build_weak_gate_tasks,
)
from qvf_validity_admission import (
    QVFMemoryPipeline as ModularQVFMemoryPipeline,
    build_model_eval_plan,
    run_heldout_integration_eval,
    run_qvf_service_request as modular_run_qvf_service_request,
    stale400_case_to_validity_admission_request,
    write_heldout_integration_eval,
    write_model_eval_plan,
)

stale400_case_to_lifecycle_request = stale400_case_to_validity_admission_request


def memory(
    memory_id: str,
    entity: str,
    slot: str,
    value: str,
    observed_at: str,
    source_confidence: float = 0.9,
    valid_until: str | None = None,
    condition: str | None = None,
    source_type: str = "synthetic_demo",
    source_id: str | None = None,
    namespace: str = "",
    tenant_id: str = "",
    user_id: str = "",
) -> dict:
    return {
        "memory_id": memory_id,
        "entity": entity,
        "slot": slot,
        "claim": f"{entity} {slot} is {value}.",
        "value": value,
        "source": {
            "source_id": source_id or f"source_{memory_id}",
            "source_type": source_type,
        },
        "observed_at": observed_at,
        "valid_from": observed_at,
        "valid_until": valid_until,
        "condition": condition,
        "scope": {
            "namespace": namespace,
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
        "source_confidence": source_confidence,
    }


class LifecycleContextControllerTests(unittest.TestCase):
    def test_modular_public_imports_expose_core_pipeline_surfaces(self) -> None:
        pipeline = ModularQVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_modular_alice",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_modular_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
            }
        )

        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])

    def test_modular_service_import_runs_service_request(self) -> None:
        request = {
            "request_id": "svc_modular_import",
            "records": [
                memory(
                    "mem_modular_service_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            "events": [
                {
                    "event_id": "evt_modular_service_alice_new",
                    "text": "Alice says her office is now in Berlin.",
                    "entity": "Alice",
                    "slot": "office_city",
                    "value": "Berlin",
                    "observed_at": "2025-01-01T00:00:00+00:00",
                    "source_type": "user_statement",
                    "source_confidence": 0.95,
                }
            ],
            "query_requests": [
                {
                    "request_id": "req_modular_service_alice",
                    "question": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "premise_value": "Paris",
                }
            ],
        }

        response = modular_run_qvf_service_request(request)
        result = response["step_report"]["query_report"]["query_results"][0]

        self.assertEqual(response["decision"], "GO_QVF_SERVICE_REQUEST_READY_NO_API")
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])

    def test_stale400_adapter_builds_lifecycle_service_request(self) -> None:
        case = {
            "uid": "case_bridge_1",
            "type": "T1",
            "M_old": "I've been based in Seattle for the last few years.",
            "M_new": "I just finished updating my address after settling into my new place in Austin.",
            "explanation": "Spatiotemporal_Context.location(city) is now Austin.",
            "timestamps": ["2021-06-15 10:30", "2025-06-15 10:30"],
            "relevant_session_index": [0, 1],
            "probing_queries": {
                "dim1_query": "Based on the conversation history, does the user still live in Seattle?",
                "dim2_query": "Since the user has been based in Seattle, what should they sign up for right now?",
                "dim3_query": "I just moved to the area; what local setup steps should I take?",
            },
        }

        request = stale400_case_to_lifecycle_request(case)

        self.assertEqual(request["metadata"]["slot"], "spatiotemporal_context_location_city")
        self.assertEqual(len(request["records"]), 2)
        self.assertEqual(len(request["query_requests"]), 3)
        self.assertEqual(request["query_requests"][0]["reader_profile"], "weak_conservative")
        self.assertEqual(request["query_requests"][1]["reader_profile"], "weak_conservative")
        self.assertEqual(request["query_requests"][2]["reader_profile"], "dim3_actionable")
        self.assertEqual(request["query_requests"][0]["premise_value"], case["M_old"])

    def test_stale400_adapter_runs_through_lifecycle_service(self) -> None:
        case = {
            "uid": "case_bridge_2",
            "type": "T1",
            "M_old": "I've been based in Seattle for the last few years.",
            "M_new": "I just finished updating my address after settling into my new place in Austin.",
            "explanation": "Spatiotemporal_Context.location(city) is now Austin.",
            "timestamps": ["2021-06-15 10:30", "2025-06-15 10:30"],
            "relevant_session_index": [0, 1],
            "probing_queries": {
                "dim2_query": "Since the user has been based in Seattle, what should they sign up for right now?",
                "dim3_query": "I just moved to the area; what local setup steps should I take?",
            },
        }

        response = modular_run_qvf_service_request(
            stale400_case_to_lifecycle_request(case)
        )
        results = {
            result["query_id"]: result
            for result in response["step_report"]["query_report"]["query_results"]
        }
        dim2 = results["case_bridge_2::dim2_query"]
        dim3 = results["case_bridge_2::dim3_query"]

        self.assertEqual(response["decision"], "GO_QVF_SERVICE_REQUEST_READY_NO_API")
        self.assertEqual(dim2["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(dim2["read_decision"]["answer_policy"], "correct_premise_only")
        self.assertIn("Austin", dim2["reader_response"]["final_answer"])
        self.assertEqual(dim3["packet"]["query"]["reader_profile"], "dim3_actionable")
        self.assertEqual(dim3["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertIn("Austin", dim3["reader_response"]["final_answer"])

    def test_heldout_integration_eval_passes_all_no_api_cases(self) -> None:
        result = run_heldout_integration_eval()

        self.assertEqual(
            result["decision"],
            "GO_QVF_HELDOUT_INTEGRATION_EVAL_PASS_NO_API",
        )
        self.assertEqual(result["case_count"], 7)
        self.assertEqual(result["passed_case_count"], 7)
        self.assertEqual(result["failed_check_count"], 0)
        self.assertEqual(result["api_calls_made"], 0)

    def test_heldout_integration_eval_writes_safe_pack_and_model_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            heldout = write_heldout_integration_eval(out_dir / "heldout")
            model_plan = write_model_eval_plan(out_dir / "model_eval")

            for file_name in heldout["files"] + model_plan["files"]:
                self.assertTrue(Path(file_name).exists(), file_name)

            summary = json.loads(
                (out_dir / "heldout" / "heldout_integration_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            plan = json.loads(
                (out_dir / "model_eval" / "model_eval_plan.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(summary["passed_case_count"], 7)
        self.assertEqual(model_plan["decision"], "NEEDS_EXPLICIT_GO_BEFORE_API_RUN")
        self.assertEqual(plan["expected_call_count"]["target_calls_total"], 35)
        self.assertEqual(plan["expected_call_count"]["max_calls_with_llm_judge"], 70)
        self.assertEqual(plan["api_calls_made"], 0)

    def test_model_eval_plan_requires_explicit_go_before_api_calls(self) -> None:
        plan = build_model_eval_plan()

        self.assertEqual(plan["decision"], "NEEDS_EXPLICIT_GO_BEFORE_API_RUN")
        self.assertEqual(plan["go_no_go"], "NO_GO_API_UNTIL_USER_APPROVES_MODEL_RUN")
        self.assertEqual(plan["dataset_slice"]["case_count"], 7)
        self.assertEqual(plan["expected_call_count"]["target_calls_total"], 35)

    def test_newer_conflict_supersedes_old_memory(self) -> None:
        store = ValidityAwareMemoryStore()
        old = store.admit(
            memory(
                "mem_alice_old",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        )
        new = store.admit(
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        )

        self.assertEqual(new.admission_status, "admit_current")
        self.assertEqual(old.admission_status, "admit_as_stale_contrast")
        self.assertEqual(old.current_status, "superseded")
        self.assertEqual(new.links["supersedes"], ["mem_alice_old"])

    def test_older_conflict_exports_reciprocal_supersede_links(self) -> None:
        store = ValidityAwareMemoryStore()
        current = store.admit(
            memory(
                "mem_alice_current",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        )
        stale = store.admit(
            memory(
                "mem_alice_stale",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        )
        exported = {
            record["memory_id"]: record for record in store.export_memory_store()
        }

        self.assertEqual(current.admission_status, "admit_current")
        self.assertEqual(stale.admission_status, "admit_as_stale_contrast")
        self.assertEqual(stale.links["superseded_by"], ["mem_alice_current"])
        self.assertEqual(current.links["supersedes"], ["mem_alice_stale"])
        self.assertEqual(
            exported["mem_alice_current"]["links"]["supersedes"],
            ["mem_alice_stale"],
        )
        self.assertEqual(
            exported["mem_alice_stale"]["links"]["superseded_by"],
            ["mem_alice_current"],
        )
        self.assertEqual(store.validate_integrity()["link_edges"], 4)
        self.assertEqual(
            ValidityAwareMemoryStore.from_exported_records(
                store.export_memory_store()
            ).validate_integrity(),
            store.validate_integrity(),
        )

    def test_duplicate_memory_id_is_rejected_without_overwriting_store(self) -> None:
        store = ValidityAwareMemoryStore()
        original = store.admit(
            memory(
                "mem_duplicate",
                "Dana",
                "office_city",
                "Paris",
                "2025-01-01T00:00:00+00:00",
            )
        )
        duplicate = store.admit(
            memory(
                "mem_duplicate",
                "Dana",
                "office_city",
                "Berlin",
                "2025-02-01T00:00:00+00:00",
            )
        )

        self.assertEqual(original.admission_status, "admit_current")
        self.assertEqual(duplicate.admission_status, "reject_duplicate_memory_id")
        self.assertEqual(duplicate.current_status, "rejected")
        self.assertEqual(
            duplicate.evidence_role,
            "excluded_duplicate_memory_id",
        )
        self.assertEqual(store.records["mem_duplicate"].value, "Paris")
        self.assertEqual(
            store.current_by_key[("", "", "", "dana", "office_city")],
            "mem_duplicate",
        )
        self.assertEqual(len(store.export_memory_store()), 1)
        self.assertEqual(
            store.admission_log[-1]["admission_status"],
            "reject_duplicate_memory_id",
        )

    def test_store_admit_records_rejects_bad_record_batch_before_partial_admission(self) -> None:
        store = ValidityAwareMemoryStore()
        valid_record = memory(
            "mem_alice_valid",
            "Alice",
            "office_city",
            "Paris",
            "2024-01-01T00:00:00+00:00",
        )
        invalid_record = memory(
            "mem_alice_invalid",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        invalid_record["source_confidence"] = "high"

        with self.assertRaisesRegex(ValueError, "memory.source_confidence"):
            store.admit_records([valid_record, invalid_record])

        self.assertEqual(store.records, {})
        self.assertEqual(store.current_by_key, {})
        self.assertEqual(store.admission_log, [])

    def test_store_validate_integrity_accepts_live_and_reloaded_store(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_alice_old",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        )
        store.admit(
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        )

        summary = store.validate_integrity()
        reloaded = ValidityAwareMemoryStore.from_exported_records(
            store.export_memory_store()
        )

        self.assertEqual(summary["records"], 2)
        self.assertEqual(summary["current_records"], 1)
        self.assertEqual(summary["current_index_entries"], 1)
        self.assertEqual(summary["link_edges"], 4)
        self.assertEqual(reloaded.validate_integrity(), summary)
        self.assertEqual(QVFMemoryPipeline(store).validate_integrity(), summary)

    def test_store_validate_integrity_rejects_corrupt_current_index(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_alice_old",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        )
        store.admit(
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        )
        key = ("", "", "", "alice", "office_city")
        del store.current_by_key[key]

        with self.assertRaisesRegex(ValueError, "missing from current_by_key"):
            store.validate_integrity()

    def test_admit_rejects_invalid_memory_payload_shapes(self) -> None:
        store = ValidityAwareMemoryStore()
        cases = [
            ({"entity": ""}, "memory.entity"),
            ({"observed_at": "not-a-date"}, "memory.observed_at"),
            ({"observed_at": "2025-01-01T00:00:00"}, "timezone"),
            ({"valid_until": "2025-02-01T00:00:00"}, "timezone"),
            (
                {
                    "valid_from": "2025-03-01T00:00:00+00:00",
                    "valid_until": "2025-02-01T00:00:00+00:00",
                },
                "valid_until",
            ),
            ({"source": "chat"}, "memory.source"),
            ({"source": {"source_id": "", "source_type": "synthetic_demo"}}, "source_id"),
            ({"source_confidence": "0.9"}, "source_confidence"),
            ({"source_confidence": 1.5}, "source_confidence"),
            ({"condition": 42}, "memory.condition"),
            ({"scope": "tenant-a"}, "memory.scope"),
            ({"scope": {"tenant_id": 42}}, "memory.scope.tenant_id"),
            ({"validity_action": "archive_current"}, "memory.validity_action"),
            ({"invalidates_memory_ids": "mem_a"}, "invalidates_memory_ids"),
            ({"invalidates_memory_ids": [""]}, "invalidates_memory_ids"),
            (
                {"invalidates_memory_ids": ["mem_target", " mem_target "]},
                "duplicate target mem_target",
            ),
            (
                {"invalidates_memory_ids": ["mem_bad_payload"]},
                "self-reference",
            ),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                row = memory(
                    "mem_bad_payload",
                    "Dana",
                    "office_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                )
                row.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    store.admit(row)

    def test_load_jsonl_accepts_utf8_bom_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.jsonl"
            path.write_text('{"value": 1}\n', encoding="utf-8-sig")

            rows = load_jsonl(path)

        self.assertEqual(rows, [{"value": 1}])

    def test_reloading_duplicate_memory_ids_raises(self) -> None:
        rows = [
            memory(
                "mem_duplicate_reload",
                "Dana",
                "office_city",
                "Paris",
                "2025-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_duplicate_reload",
                "Dana",
                "office_city",
                "Berlin",
                "2025-02-01T00:00:00+00:00",
            ),
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate memory_id"):
            ValidityAwareMemoryStore.from_exported_records(rows)

    def test_reloading_invalid_memory_payload_raises(self) -> None:
        row = memory(
            "mem_bad_reload_payload",
            "Dana",
            "office_city",
            "Paris",
            "2025-01-01T00:00:00+00:00",
        )
        row["source_confidence"] = True

        with self.assertRaisesRegex(ValueError, "source_confidence"):
            ValidityAwareMemoryStore.from_exported_records([row])

    def test_reloading_invalid_exported_status_fields_raises(self) -> None:
        cases = [
            ({"admission_status": "uploaded"}, "admission_status"),
            ({"current_status": "active"}, "current_status"),
            ({"evidence_role": "answer_source"}, "evidence_role"),
            ({"current_status": 42}, "current_status"),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                row = memory(
                    "mem_bad_status",
                    "Dana",
                    "office_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                )
                row.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    ValidityAwareMemoryStore.from_exported_records([row])

    def test_reloading_inconsistent_exported_status_triples_raises(self) -> None:
        cases = [
            (
                {
                    "admission_status": "admit_current",
                    "current_status": "rejected",
                    "evidence_role": "current_support",
                },
                "admit_current requires",
            ),
            (
                {
                    "admission_status": "reject_low_confidence",
                    "current_status": "rejected",
                    "evidence_role": "current_support",
                },
                "reject_low_confidence requires",
            ),
            (
                {
                    "admission_status": "revoked_by_validity_marker",
                    "current_status": "superseded",
                    "evidence_role": "stale_contrast",
                },
                "revoked_by_validity_marker requires",
            ),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                row = memory(
                    "mem_bad_status_combo",
                    "Dana",
                    "office_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                )
                row.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    ValidityAwareMemoryStore.from_exported_records([row])

    def test_reloading_multiple_current_for_scoped_key_raises(self) -> None:
        rows = [
            memory(
                "mem_conflict_current_a",
                "Dana",
                "office_city",
                "Paris",
                "2025-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_conflict_current_b",
                "Dana",
                "office_city",
                "Berlin",
                "2025-02-01T00:00:00+00:00",
            ),
        ]
        for row in rows:
            row["admission_status"] = "admit_current"
            row["current_status"] = "current"
            row["evidence_role"] = "current_support"

        with self.assertRaisesRegex(ValueError, "Multiple current records"):
            ValidityAwareMemoryStore.from_exported_records(rows)

    def test_reloading_dangling_link_target_raises(self) -> None:
        row = memory(
            "mem_with_bad_link",
            "Dana",
            "office_city",
            "Paris",
            "2025-01-01T00:00:00+00:00",
        )
        row["links"] = {
            "supersedes": ["missing_memory"],
            "superseded_by": [],
            "contradicts": [],
            "supports": [],
            "invalidates": [],
            "invalidated_by": [],
        }

        with self.assertRaisesRegex(ValueError, "Dangling link target"):
            ValidityAwareMemoryStore.from_exported_records([row])

    def test_reloading_non_reciprocal_link_raises(self) -> None:
        newer = memory(
            "mem_newer",
            "Dana",
            "office_city",
            "Berlin",
            "2025-02-01T00:00:00+00:00",
        )
        older = memory(
            "mem_older",
            "Dana",
            "office_city",
            "Paris",
            "2025-01-01T00:00:00+00:00",
        )
        newer["links"] = {
            "supersedes": ["mem_older"],
            "superseded_by": [],
            "contradicts": [],
            "supports": [],
            "invalidates": [],
            "invalidated_by": [],
        }
        older["links"] = {
            "supersedes": [],
            "superseded_by": [],
            "contradicts": [],
            "supports": [],
            "invalidates": [],
            "invalidated_by": [],
        }

        with self.assertRaisesRegex(ValueError, "Non-reciprocal link"):
            ValidityAwareMemoryStore.from_exported_records([newer, older])

    def test_reloading_invalid_link_shape_raises(self) -> None:
        cases = [
            (
                {"supersedes": "mem_other"},
                "links.supersedes must be a list",
            ),
            (
                {"future_edge": []},
                "Unknown link edge type",
            ),
            (
                {"supports": [""]},
                "non-empty string memory ids",
            ),
            (
                {"contradicts": [123]},
                "non-empty string memory ids",
            ),
        ]

        for links, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                row = memory(
                    "mem_bad_link_shape",
                    "Dana",
                    "office_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                )
                row["links"] = links

                with self.assertRaisesRegex(ValueError, expected_error):
                    ValidityAwareMemoryStore.from_exported_records([row])

    def test_reloading_duplicate_or_self_link_targets_raises(self) -> None:
        cases = [
            (
                {"supports": ["mem_bad_link"]},
                "self-links",
            ),
            (
                {"supports": ["mem_other", "mem_other"]},
                "duplicate target mem_other",
            ),
            (
                {"supports": [" mem_other ", "mem_other"]},
                "duplicate target mem_other",
            ),
        ]

        for links, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                row = memory(
                    "mem_bad_link",
                    "Dana",
                    "office_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                )
                row["links"] = links

                with self.assertRaisesRegex(ValueError, expected_error):
                    ValidityAwareMemoryStore.from_exported_records([row])

    def test_export_memory_store_contains_validity_metadata(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_alice_old",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        )
        store.admit(
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        )

        exported = {
            row["memory_id"]: row for row in store.export_memory_store()
        }

        self.assertEqual(exported["mem_alice_new"]["current_status"], "current")
        self.assertEqual(exported["mem_alice_old"]["current_status"], "superseded")
        self.assertEqual(
            exported["mem_alice_new"]["links"]["supersedes"],
            ["mem_alice_old"],
        )
        self.assertEqual(
            exported["mem_alice_old"]["links"]["superseded_by"],
            ["mem_alice_new"],
        )
        self.assertIn("policy_version", exported["mem_alice_new"]["audit"])
        self.assertEqual(
            exported["mem_alice_new"]["audit"]["normalized_key"],
            "alice::office_city",
        )

    def test_validity_marker_revokes_current_memory(self) -> None:
        store = ValidityAwareMemoryStore()
        current = store.admit(
            memory(
                "mem_juno_active",
                "Juno",
                "badge_status",
                "active",
                "2025-01-01T00:00:00+00:00",
            )
        )
        revoke_marker = memory(
            "mem_juno_revoke",
            "Juno",
            "badge_status",
            "revoked",
            "2025-03-01T00:00:00+00:00",
        )
        revoke_marker["validity_action"] = "revoke_current"
        revoke_marker["invalidates_memory_ids"] = [" mem_juno_active "]
        marker = store.admit(revoke_marker)

        self.assertEqual(marker.admission_status, "admit_validity_marker")
        self.assertEqual(marker.payload["invalidates_memory_ids"], ["mem_juno_active"])
        self.assertNotIn(("", "", "", "juno", "badge_status"), store.current_by_key)
        self.assertEqual(current.admission_status, "revoked_by_validity_marker")
        self.assertEqual(current.current_status, "revoked")
        self.assertEqual(current.evidence_role, "stale_contrast")
        self.assertEqual(marker.links["invalidates"], ["mem_juno_active"])
        self.assertEqual(current.links["invalidated_by"], ["mem_juno_revoke"])

        packets = build_packets_from_store(
            store,
            [
                {
                    "query_id": "q_juno",
                    "query": "Since Juno's badge is still active, should they enter?",
                    "entity": "Juno",
                    "slot": "badge_status",
                    "needs_current": True,
                    "embedded_premise_value": "active",
                }
            ],
        )
        packet = packets[0]["compact_validity_packet"]
        diagnostics = packets[0]["retrieval_diagnostics"]
        roles_by_id = {
            row["memory_id"]: row["retrieval_role"]
            for row in packet["stale_or_blocked_evidence"]
        }
        decision = build_read_decisions(packets)[0]

        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(roles_by_id["mem_juno_active"], "revoked_contrast")
        self.assertEqual(roles_by_id["mem_juno_revoke"], "validity_marker")
        self.assertEqual(diagnostics["validity_marker_records_total"], 1)
        self.assertEqual(diagnostics["revoked_records_total"], 1)
        self.assertEqual(diagnostics["blocked_counts"]["revoked_contrast"], 1)
        self.assertEqual(
            diagnostics["selected_counts"]["stale_or_blocked_evidence"],
            2,
        )
        self.assertEqual(decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decision["answer_policy"], "correct_premise_only")

    def test_as_of_after_revocation_does_not_restore_revoked_memory(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_kai_active",
                "Kai",
                "access_status",
                "active",
                "2025-01-01T00:00:00+00:00",
            )
        )
        revoke_marker = memory(
            "mem_kai_revoke",
            "Kai",
            "access_status",
            "revoked",
            "2025-03-01T00:00:00+00:00",
        )
        revoke_marker["validity_action"] = "revoke_current"
        store.admit(revoke_marker)

        before_revoke = build_packets_from_store(
            store,
            [
                {
                    "query_id": "q_kai_before",
                    "query": "Was Kai's access active before March?",
                    "entity": "Kai",
                    "slot": "access_status",
                    "needs_current": True,
                    "as_of": "2025-02-01T00:00:00+00:00",
                }
            ],
        )[0]
        after_revoke = build_packets_from_store(
            store,
            [
                {
                    "query_id": "q_kai_after",
                    "query": "Is Kai's access active after March?",
                    "entity": "Kai",
                    "slot": "access_status",
                    "needs_current": True,
                    "as_of": "2025-04-01T00:00:00+00:00",
                }
            ],
        )[0]

        before_packet = before_revoke["compact_validity_packet"]
        after_packet = after_revoke["compact_validity_packet"]
        self.assertEqual(before_packet["current_evidence"][0]["memory_id"], "mem_kai_active")
        self.assertEqual(
            before_packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "future_evidence",
        )
        self.assertEqual(after_packet["current_evidence"], [])
        self.assertEqual(
            after_packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "validity_marker",
        )
        self.assertEqual(
            after_packet["stale_or_blocked_evidence"][1]["retrieval_role"],
            "revoked_contrast",
        )
        self.assertEqual(
            after_revoke["retrieval_diagnostics"]["blocked_counts"]["revoked_contrast"],
            1,
        )

    def test_reloaded_memory_store_preserves_read_time_routing(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_alice_old",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        )
        store.admit(
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        )
        reloaded = ValidityAwareMemoryStore.from_exported_records(
            store.export_memory_store()
        )
        queries = [
            {
                "query_id": "q_alice",
                "query": "Since Alice is still in Paris, where should I send mail?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
                "embedded_premise_value": "Paris",
            }
        ]

        packets = build_packets_from_store(reloaded, queries)
        decision = build_read_decisions(packets)[0]

        self.assertEqual(
            reloaded.current_by_key[("", "", "", "alice", "office_city")],
            "mem_alice_new",
        )
        self.assertEqual(decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decision["blocking_evidence_ids"], ["mem_alice_new"])
        self.assertEqual(decision["stale_evidence_ids"], ["mem_alice_old"])
        controller = decision["validity_controller_decision"]
        self.assertEqual(controller["premise_blocker_ids"], ["mem_alice_new"])
        self.assertEqual(controller["blocked_as_current_ids"], ["mem_alice_old"])

    def test_scoped_current_memories_do_not_supersede_across_users(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_alex_u1",
                "Alex",
                "office_city",
                "Paris",
                "2025-01-01T00:00:00+00:00",
                namespace="work",
                tenant_id="team_a",
                user_id="user_1",
            )
        )
        store.admit(
            memory(
                "mem_alex_u2",
                "Alex",
                "office_city",
                "Berlin",
                "2025-02-01T00:00:00+00:00",
                namespace="work",
                tenant_id="team_a",
                user_id="user_2",
            )
        )

        self.assertEqual(
            store.current_by_key[("work", "team_a", "user_1", "alex", "office_city")],
            "mem_alex_u1",
        )
        self.assertEqual(
            store.current_by_key[("work", "team_a", "user_2", "alex", "office_city")],
            "mem_alex_u2",
        )
        self.assertEqual(store.records["mem_alex_u1"].current_status, "current")
        self.assertEqual(store.records["mem_alex_u2"].current_status, "current")

        result = QVFMemoryPipeline(store).query(
            {
                "query_id": "q_alex_u1",
                "query": "Where is Alex's office now?",
                "entity": "Alex",
                "slot": "office_city",
                "needs_current": True,
                "scope": {
                    "namespace": "work",
                    "tenant_id": "team_a",
                    "user_id": "user_1",
                },
            }
        )

        packet = result["packet"]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_alex_u1"],
        )
        self.assertEqual(packet["compact_validity_packet"]["current_evidence"][0]["value"], "Paris")
        self.assertEqual(packet["retrieval_diagnostics"]["blocked_counts"]["scope_mismatch"], 1)

    def test_validity_marker_cannot_revoke_cross_scope_target(self) -> None:
        store = ValidityAwareMemoryStore()
        store.admit(
            memory(
                "mem_casey_u1",
                "Casey",
                "access_status",
                "active",
                "2025-01-01T00:00:00+00:00",
                namespace="work",
                tenant_id="team_a",
                user_id="user_1",
            )
        )
        cross_scope_target = store.admit(
            memory(
                "mem_casey_u2",
                "Casey",
                "access_status",
                "active",
                "2025-01-01T00:00:00+00:00",
                namespace="work",
                tenant_id="team_a",
                user_id="user_2",
            )
        )
        revoke_marker = memory(
            "mem_casey_u1_bad_revoke",
            "Casey",
            "access_status",
            "revoked",
            "2025-03-01T00:00:00+00:00",
            namespace="work",
            tenant_id="team_a",
            user_id="user_1",
        )
        revoke_marker["validity_action"] = "revoke_current"
        revoke_marker["invalidates_memory_ids"] = ["mem_casey_u2"]
        marker = store.admit(revoke_marker)

        self.assertEqual(marker.admission_status, "admit_validity_marker")
        self.assertEqual(marker.links["invalidates"], [])
        self.assertEqual(marker.payload["invalidates_scope_mismatch_count"], 1)
        self.assertIn("outside the marker scope", marker.admission_reason)
        self.assertEqual(cross_scope_target.current_status, "current")
        self.assertEqual(
            store.current_by_key[("work", "team_a", "user_1", "casey", "access_status")],
            "mem_casey_u1",
        )
        self.assertEqual(
            store.current_by_key[("work", "team_a", "user_2", "casey", "access_status")],
            "mem_casey_u2",
        )

        result = QVFMemoryPipeline(store).query(
            {
                "query_id": "q_casey_u2",
                "query": "Is Casey active?",
                "entity": "Casey",
                "slot": "access_status",
                "needs_current": True,
                "scope": {
                    "namespace": "work",
                    "tenant_id": "team_a",
                    "user_id": "user_2",
                },
            }
        )

        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_casey_u2"],
        )

    def test_unscoped_query_does_not_expose_scoped_memories(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_blair_private",
                    "Blair",
                    "home_city",
                    "Oslo",
                    "2025-01-01T00:00:00+00:00",
                    namespace="personal",
                    tenant_id="tenant_1",
                    user_id="user_1",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_blair_unscoped",
                "query": "Where does Blair live now?",
                "entity": "Blair",
                "slot": "home_city",
                "needs_current": True,
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(packet["stale_or_blocked_evidence"], [])
        self.assertEqual(diagnostics["blocked_counts"]["scope_mismatch"], 1)
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_memory_event_adapter_normalizes_external_event_payload(self) -> None:
        event = {
            "event_id": "evt_alice_office_update",
            "text": "Alice told the assistant that her office is now in Berlin.",
            "entity": "Alice",
            "slot": "office_city",
            "value": "Berlin",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "source_type": "user_statement",
            "confidence": 0.91,
            "namespace": "work",
            "tenant_id": "team_a",
            "user_id": "user_1",
        }

        record = normalize_memory_event_payload(event)
        summary = build_memory_event_adapter_summary([event], [record])

        self.assertEqual(record["memory_id"], "evt_alice_office_update")
        self.assertEqual(record["claim"], event["text"])
        self.assertEqual(record["source"]["source_id"], "evt_alice_office_update")
        self.assertEqual(record["source"]["source_type"], "user_statement")
        self.assertEqual(record["source_confidence"], 0.91)
        self.assertEqual(record["scope"]["namespace"], "work")
        self.assertEqual(summary["event_count"], 1)
        self.assertEqual(summary["output_memory_ids"], ["evt_alice_office_update"])
        self.assertEqual(summary["source_type_counts"], {"user_statement": 1})
        self.assertEqual(summary["api_calls_made"], 0)

    def test_memory_event_adapter_generates_stable_id_without_event_id(self) -> None:
        event = {
            "entity": "Alice",
            "slot": "office_city",
            "value": "Berlin",
            "observed_at": "2025-01-01T00:00:00+00:00",
            "source": {
                "source_id": "chat_42",
                "source_type": "user_statement",
            },
            "source_confidence": 0.9,
        }

        first = normalize_memory_event_payload(event)
        second = normalize_memory_event_payload(deepcopy(event))
        summary = build_memory_event_adapter_summary([event], [first])

        self.assertEqual(first["memory_id"], second["memory_id"])
        self.assertTrue(first["memory_id"].startswith("mem_event_"))
        self.assertEqual(summary["generated_memory_id_count"], 1)
        self.assertEqual(summary["generated_memory_ids"], [first["memory_id"]])

    def test_query_request_adapter_normalizes_external_read_request(self) -> None:
        request = {
            "request_id": "req_alice_current_mail",
            "question": "Since Alice is still in Paris, where should I send mail?",
            "entity": "Alice",
            "slot": "office_city",
            "premise_value": "Paris",
            "risk_profile": "current_sensitive",
            "min_source_confidence": 0.8,
            "allowed_source_types": ["user_statement"],
            "scope": {"namespace": "work", "tenant_id": "team_a"},
            "user_id": "user_1",
        }

        query = normalize_query_request_payload(request)
        summary = build_query_request_adapter_summary([request], [query])

        self.assertEqual(query["query_id"], "req_alice_current_mail")
        self.assertEqual(query["query"], request["question"])
        self.assertEqual(query["entity"], "Alice")
        self.assertEqual(query["slot"], "office_city")
        self.assertEqual(query["embedded_premise_value"], "Paris")
        self.assertEqual(query["risk_profile"], "current_sensitive")
        self.assertEqual(query["min_source_confidence"], 0.8)
        self.assertEqual(query["allowed_source_types"], ["user_statement"])
        self.assertEqual(
            query["scope"],
            {"namespace": "work", "tenant_id": "team_a", "user_id": "user_1"},
        )
        self.assertEqual(summary["request_count"], 1)
        self.assertEqual(summary["normalized_query_count"], 1)
        self.assertEqual(summary["output_query_ids"], ["req_alice_current_mail"])
        self.assertEqual(summary["embedded_premise_request_count"], 1)
        self.assertEqual(summary["source_policy_request_count"], 1)
        self.assertEqual(summary["risk_profile_counts"], {"current_sensitive": 1})
        self.assertEqual(summary["api_calls_made"], 0)

    def test_query_request_adapter_rejects_bad_request_shapes(self) -> None:
        bad_cases = [
            ("bad_request", "query request must be an object"),
            ({"entity": "Alice", "slot": "office_city"}, "text/query/question"),
            (
                {"question": "Where is Alice?", "slot": "office_city"},
                "query request.entity",
            ),
            (
                {"question": "Where is Alice?", "entity": "Alice"},
                "query request.slot",
            ),
            (
                {
                    "question": "Where is Alice?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": "false",
                },
                "needs_current",
            ),
            (
                {
                    "question": "Where is Alice?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "allowed_source_types": [""],
                },
                "allowed_source_types",
            ),
            (
                {
                    "question": "Where is Alice?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "min_source_confidence": 1.2,
                },
                "min_source_confidence",
            ),
        ]

        for request, expected_error in bad_cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    normalize_query_request_payload(request)  # type: ignore[arg-type]

    def test_pipeline_query_requests_report_drives_read_time_stale_rejection(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                    source_type="user_statement",
                ),
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                    source_type="user_statement",
                ),
            ]
        )
        request = {
            "request_id": "req_alice_current_mail",
            "question": "Since Alice is still in Paris, where should I send mail?",
            "entity": "Alice",
            "slot": "office_city",
            "premise_value": "Paris",
            "allowed_source_types": ["user_statement"],
        }

        report = pipeline.run_query_requests_with_report([request])
        result = report["query_results"][0]

        self.assertEqual(
            report["summary"]["execution_mode"],
            "pipeline_query_request_batch_report",
        )
        self.assertEqual(
            report["query_request_adapter_summary"]["output_query_ids"],
            ["req_alice_current_mail"],
        )
        self.assertEqual(result["query_id"], "req_alice_current_mail")
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        self.assertEqual(report["summary"]["api_calls_made"], 0)

    def test_pipeline_lifecycle_event_step_supersedes_old_memory_and_queries_current(
        self,
    ) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            max_stale=1,
        )
        event = {
            "event_id": "evt_alice_new",
            "text": "Alice says her office is now in Berlin.",
            "entity": "Alice",
            "slot": "office_city",
            "value": "Berlin",
            "observed_at": "2025-01-01T00:00:00+00:00",
            "source_type": "user_statement",
            "source_confidence": 0.95,
        }

        step = pipeline.run_validity_admission_event_step(
            events=[event],
            queries=[
                {
                    "query_id": "q_alice",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                }
            ],
            step_id="event-step-001",
        )

        self.assertEqual(step["decision"], "GO_QVF_LIFECYCLE_STEP_READY_NO_API")
        self.assertEqual(step["records_submitted_from_events"], 1)
        self.assertEqual(step["records_submitted_from_records"], 0)
        self.assertEqual(
            step["event_adapter_summary"]["output_memory_ids"],
            ["evt_alice_new"],
        )
        self.assertEqual(step["state_delta"]["current_memory_ids"], ["evt_alice_new"])
        self.assertEqual(step["state_delta"]["superseded_memory_ids"], ["mem_alice_old"])
        self.assertEqual(
            step["state_delta"]["read_decisions_by_query_id"],
            {"q_alice": "REJECT_STALE_PREMISE"},
        )
        self.assertEqual(
            pipeline.store.records["mem_alice_old"].current_status,
            "superseded",
        )
        self.assertEqual(
            pipeline.store.current_by_key[("", "", "", "alice", "office_city")],
            "evt_alice_new",
        )
        self.assertIn(
            "Berlin",
            step["query_report"]["query_results"][0]["reader_response"]["final_answer"],
        )

    def test_pipeline_lifecycle_event_step_accepts_query_requests(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                    source_type="user_statement",
                )
            ],
            max_stale=1,
        )
        event = {
            "event_id": "evt_alice_new",
            "text": "Alice says her office is now in Berlin.",
            "entity": "Alice",
            "slot": "office_city",
            "value": "Berlin",
            "observed_at": "2025-01-01T00:00:00+00:00",
            "source_type": "user_statement",
            "source_confidence": 0.95,
        }
        request = {
            "request_id": "req_alice_current_mail",
            "question": "Since Alice is still in Paris, where should I send mail?",
            "entity": "Alice",
            "slot": "office_city",
            "premise_value": "Paris",
            "allowed_source_types": ["user_statement"],
        }

        step = pipeline.run_validity_admission_event_step(
            events=[event],
            query_requests=[request],
            step_id="event-request-step-001",
        )
        result = step["query_report"]["query_results"][0]

        self.assertEqual(step["query_count"], 1)
        self.assertEqual(step["queries_submitted_from_requests"], 1)
        self.assertEqual(step["queries_submitted_from_queries"], 0)
        self.assertEqual(
            step["query_request_adapter_summary"]["output_query_ids"],
            ["req_alice_current_mail"],
        )
        self.assertEqual(
            step["state_delta"]["read_decisions_by_query_id"],
            {"req_alice_current_mail": "REJECT_STALE_PREMISE"},
        )
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        self.assertEqual(
            pipeline.store.current_by_key[("", "", "", "alice", "office_city")],
            "evt_alice_new",
        )

    def test_qvf_service_request_runs_stateful_write_read_step(self) -> None:
        base_pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            max_stale=1,
        )
        service_request = {
            "request_id": "svc_alice_mail",
            "memory_store": base_pipeline.export_memory_store(),
            "events": [
                {
                    "event_id": "evt_alice_new",
                    "text": "Alice says her office is now in Berlin.",
                    "entity": "Alice",
                    "slot": "office_city",
                    "value": "Berlin",
                    "observed_at": "2025-01-01T00:00:00+00:00",
                    "source_type": "user_statement",
                    "source_confidence": 0.95,
                }
            ],
            "query_requests": [
                {
                    "request_id": "req_alice_current_mail",
                    "question": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "premise_value": "Paris",
                }
            ],
            "include_state": True,
        }

        response = run_qvf_service_request(service_request)
        result = response["step_report"]["query_report"]["query_results"][0]
        returned_state = response["state"]

        self.assertEqual(response["decision"], "GO_QVF_SERVICE_REQUEST_READY_NO_API")
        self.assertEqual(response["execution_mode"], "qvf_service_request")
        self.assertEqual(response["request_id"], "svc_alice_mail")
        self.assertEqual(response["input_mode"], "service_memory_store")
        self.assertTrue(response["state_returned"])
        self.assertEqual(response["summary"]["query_count"], 1)
        self.assertEqual(
            response["summary"]["query_request_adapter_summary"]["output_query_ids"],
            ["req_alice_current_mail"],
        )
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        current_rows = [
            row
            for row in returned_state["memory_store"]
            if row["current_status"] == "current"
        ]
        self.assertEqual([row["memory_id"] for row in current_rows], ["evt_alice_new"])
        self.assertEqual(response["api_calls_made"], 0)

    def test_qvf_service_request_rejects_ambiguous_or_bad_shapes(self) -> None:
        base_state = QVFMemoryPipeline.from_records([]).export_state()
        bad_cases = [
            ("bad_request", "QVF service request must be an object"),
            (
                {"state": base_state, "memory_store": [{"memory_id": "mem_x"}]},
                "both state and memory_store",
            ),
            (
                {"state": base_state, "config": {"max_current": 2}},
                "config cannot override embedded state",
            ),
            ({"config": {"unknown": 1}}, "Unknown QVF service request.config"),
            (
                {"config": {"include_validity_edges": "yes"}},
                "include_validity_edges",
            ),
            ({"records": {}}, "records must be a list"),
            ({"include_state": "true"}, "include_state must be a boolean"),
            ({"preview": "false"}, "preview must be a boolean"),
        ]

        for request, expected_error in bad_cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    run_qvf_service_request(request)  # type: ignore[arg-type]

    def test_pipeline_memory_event_invalidation_marker_revokes_current(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_casey_active",
                    "Casey",
                    "access_status",
                    "active",
                    "2025-01-01T00:00:00+00:00",
                )
            ]
        )
        event = {
            "event_id": "evt_casey_revoke",
            "event_type": "invalidate_current",
            "entity": "Casey",
            "slot": "access_status",
            "value": "revoked",
            "observed_at": "2025-03-01T00:00:00+00:00",
            "source": {
                "source_id": "iam_audit_7",
                "source_type": "tool_result",
            },
            "source_confidence": 0.98,
            "invalidates_memory_ids": ["mem_casey_active"],
        }

        report = pipeline.admit_memory_events_with_report([event])
        result = pipeline.query(
            {
                "query_id": "q_casey",
                "query": "Is Casey active now?",
                "entity": "Casey",
                "slot": "access_status",
                "needs_current": True,
            }
        )

        self.assertEqual(report["execution_mode"], "pipeline_memory_event_admission_report")
        self.assertEqual(report["records_submitted_from_events"], 1)
        self.assertEqual(
            report["event_adapter_summary"]["validity_action_counts"],
            {"invalidate_current": 1},
        )
        self.assertEqual(
            pipeline.store.records["mem_casey_active"].current_status,
            "revoked",
        )
        self.assertEqual(
            pipeline.store.records["evt_casey_revoke"].links["invalidates"],
            ["mem_casey_active"],
        )
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")
        self.assertEqual(
            result["packet"]["compact_validity_packet"]["current_evidence"],
            [],
        )

    def test_memory_event_adapter_rejects_bad_event_shapes(self) -> None:
        bad_cases = [
            ("bad_event", "memory event must be an object"),
            ({"entity": "Alice"}, "memory event observed_at/timestamp/created_at"),
            (
                {
                    "entity": "Alice",
                    "slot": "office_city",
                    "value": "Paris",
                    "observed_at": "2025-01-01T00:00:00+00:00",
                    "confidence": "high",
                },
                "source_confidence/confidence",
            ),
            (
                {
                    "entity": "Alice",
                    "slot": "office_city",
                    "value": "Paris",
                    "observed_at": "2025-01-01T00:00:00+00:00",
                    "scope": "work",
                },
                "memory event.scope",
            ),
        ]

        for event, expected_error in bad_cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    normalize_memory_event_payload(event)  # type: ignore[arg-type]

    def test_pipeline_query_returns_packet_decision_and_response(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_alice",
                "query": "Since Alice is still in Paris, where should I send mail?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
                "embedded_premise_value": "Paris",
            }
        )

        self.assertIn("packet", result)
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        self.assertEqual(
            result["reader_response"]["blocking_evidence_ids"],
            ["mem_alice_new"],
        )

    def test_pipeline_admit_records_with_report_captures_state_transitions(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )

        report = pipeline.admit_records_with_report(
            [
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ]
        )

        self.assertEqual(
            report["decision"],
            "GO_QVF_LIFECYCLE_WRITE_TIME_ADMISSION_READY_NO_API",
        )
        self.assertEqual(
            report["execution_mode"],
            "pipeline_incremental_admission_report",
        )
        self.assertEqual(report["records_submitted"], 1)
        self.assertEqual(report["input_memory_ids"], ["mem_alice_new"])
        self.assertEqual(report["admission_event_count"], 2)
        self.assertEqual(report["api_calls_made"], 0)
        self.assertEqual(
            report["admission_status_counts"],
            {"admit_current": 1, "admit_as_stale_contrast": 1},
        )
        self.assertEqual(
            report["current_status_counts"],
            {"current": 1, "superseded": 1},
        )
        self.assertEqual(
            [event["memory_id"] for event in report["admission_events"]],
            ["mem_alice_new", "mem_alice_old"],
        )
        self.assertEqual(report["store_integrity"], pipeline.validate_integrity())

        result = pipeline.query(
            {
                "query_id": "q_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        )
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_alice_new"])

    def test_pipeline_preview_admission_reports_delta_without_mutating_store(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        before_store = pipeline.export_memory_store()
        before_integrity = pipeline.validate_integrity()

        preview = pipeline.preview_admission(
            [
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ]
        )

        self.assertEqual(
            preview["decision"],
            "GO_QVF_LIFECYCLE_ADMISSION_PREVIEW_READY_NO_API",
        )
        self.assertEqual(preview["execution_mode"], "pipeline_admission_preview")
        self.assertEqual(preview["records_submitted"], 1)
        self.assertEqual(preview["admission_event_count"], 2)
        self.assertEqual(preview["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(
            preview["state_delta"]["superseded_memory_ids"],
            ["mem_alice_old"],
        )
        self.assertEqual(preview["store_integrity_before"], before_integrity)
        self.assertEqual(preview["store_integrity_after"]["records"], 2)
        self.assertEqual(preview["store_integrity_delta"]["records"], 1)
        self.assertEqual(
            preview["current_index_before"][0]["memory_id"],
            "mem_alice_old",
        )
        self.assertEqual(
            preview["current_index_after"][0]["memory_id"],
            "mem_alice_new",
        )
        self.assertEqual(
            preview["changed_memory_ids"],
            ["mem_alice_new", "mem_alice_old"],
        )
        self.assertEqual(preview["store_diff"]["added_memory_ids"], ["mem_alice_new"])
        self.assertEqual(preview["store_diff"]["updated_memory_ids"], ["mem_alice_old"])
        self.assertEqual(
            preview["store_diff"]["current_index_changes"][0]["before_memory_id"],
            "mem_alice_old",
        )
        self.assertEqual(
            preview["store_diff"]["current_index_changes"][0]["after_memory_id"],
            "mem_alice_new",
        )
        old_change = next(
            change
            for change in preview["store_diff"]["record_changes"]
            if change["memory_id"] == "mem_alice_old"
        )
        self.assertEqual(old_change["change_type"], "updated")
        self.assertIn("current_status", old_change["changed_fields"])
        self.assertEqual(pipeline.export_memory_store(), before_store)
        self.assertEqual(pipeline.validate_integrity(), before_integrity)
        result = pipeline.query(
            {
                "query_id": "q_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        )
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_alice_old"])

    def test_pipeline_admit_records_with_report_rejects_non_list_input(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])

        with self.assertRaisesRegex(ValueError, "records must be a list"):
            pipeline.admit_records_with_report({"memory_id": "not_a_list"})  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "records must be a list"):
            pipeline.preview_admission({"memory_id": "not_a_list"})  # type: ignore[arg-type]

    def test_pipeline_admit_records_rejects_bad_record_batch_before_partial_admission(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        valid_record = memory(
            "mem_alice_valid",
            "Alice",
            "office_city",
            "Paris",
            "2024-01-01T00:00:00+00:00",
        )
        invalid_record = memory(
            "mem_alice_invalid",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        invalid_record["source_confidence"] = "high"

        with self.assertRaisesRegex(ValueError, "memory.source_confidence"):
            pipeline.admit_records([valid_record, invalid_record])

        self.assertEqual(pipeline.validate_integrity()["records"], 0)
        self.assertEqual(pipeline.export_memory_store(), [])
        self.assertEqual(pipeline.store.admission_log, [])

    def test_pipeline_admit_records_with_report_rejects_bad_record_batch_before_partial_admission(
        self,
    ) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        valid_record = memory(
            "mem_alice_valid",
            "Alice",
            "office_city",
            "Paris",
            "2024-01-01T00:00:00+00:00",
        )
        invalid_record = memory(
            "mem_alice_invalid",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        invalid_record["source_confidence"] = "high"

        with self.assertRaisesRegex(ValueError, "memory.source_confidence"):
            pipeline.admit_records_with_report([valid_record, invalid_record])

        self.assertEqual(pipeline.validate_integrity()["records"], 0)
        self.assertEqual(pipeline.export_memory_store(), [])
        self.assertEqual(pipeline.store.admission_log, [])

    def test_pipeline_query_with_weak_gate_output_uses_external_gate_decision(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query_with_weak_gate_output(
            {
                "query_id": "q_alice",
                "query": "Since Alice is still in Paris, where should I send mail?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
                "embedded_premise_value": "Paris",
            },
            {
                "decision": "reject stale premise",
                "support": "",
                "blocker": "mem_alice_new",
                "final_answer": "Alice is no longer supported as being in Paris.",
            },
        )

        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(result["read_decision"]["decision_source"], "weak_gate_output")
        self.assertEqual(result["read_decision"]["blocking_evidence_ids"], ["mem_alice_new"])
        self.assertEqual(result["weak_gate_tasks"][0]["query_id"], "q_alice")
        self.assertEqual(
            result["weak_gate_adapter_summary"]["adapted_from_weak_gate_output_count"],
            1,
        )
        self.assertIn("Berlin", result["reader_response"]["final_answer"])

    def test_pipeline_query_with_weak_gate_output_rejects_bad_gate_shape(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])

        with self.assertRaisesRegex(ValueError, "weak_gate_output must be an object or null"):
            pipeline.query_with_weak_gate_output(
                {
                    "query_id": "q_alice",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                },
                "bad_row",  # type: ignore[arg-type]
            )

    def test_pipeline_batch_weak_gate_outputs_fallback_for_non_gate_queries(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        batch = pipeline.run_queries_with_weak_gate_outputs(
            [
                {
                    "query_id": "q_alice",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                },
                {
                    "query_id": "q_ben",
                    "query": "Where does Ben live now?",
                    "entity": "Ben",
                    "slot": "home_city",
                    "needs_current": True,
                },
            ],
            [
                {
                    "query_id": "q_alice",
                    "decision": "REJECT_STALE_PREMISE",
                    "support": "",
                    "blocker": "mem_alice_new",
                    "final_answer": "Alice is no longer supported as being in Paris.",
                }
            ],
        )

        self.assertEqual(len(batch["query_results"]), 2)
        self.assertEqual(batch["weak_gate_adapter_summary"]["adapted_from_weak_gate_output_count"], 1)
        self.assertEqual(batch["weak_gate_adapter_summary"]["fallback_no_task_count"], 1)
        self.assertEqual(
            batch["summary"]["execution_mode"],
            "pipeline_query_batch_report_with_weak_gate_outputs",
        )
        self.assertEqual(
            batch["summary"]["weak_gate_adapter_summary"][
                "adapted_from_weak_gate_output_count"
            ],
            1,
        )
        self.assertEqual(batch["read_decisions"][0]["decision_source"], "weak_gate_output")
        self.assertEqual(
            batch["read_decisions"][1]["decision_source"],
            "deterministic_router_fallback_no_weak_gate_task",
        )
        self.assertEqual(batch["query_results"][1]["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertIn("Milan", batch["query_results"][1]["reader_response"]["final_answer"])

    def test_pipeline_batch_weak_gate_outputs_rejects_bad_gate_shapes(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        queries = [
            {
                "query_id": "q_alice",
                "query": "Since Alice is still in Paris, where should I send mail?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
                "embedded_premise_value": "Paris",
            }
        ]

        bad_output_cases = [
            ({"query_id": "q_alice"}, "weak_gate_outputs must be a list"),
            (["bad_row"], r"weak_gate_outputs\[0\] must be an object"),
            ([{"decision": "REJECT_STALE_PREMISE"}], r"weak_gate_outputs\[0\] must include task_id or query_id"),
        ]

        for weak_gate_outputs, expected_error in bad_output_cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    pipeline.run_queries_with_weak_gate_outputs(
                        queries,
                        weak_gate_outputs,  # type: ignore[arg-type]
                    )

    def test_pipeline_run_queries_with_report_returns_batch_artifacts_and_summary(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ],
            max_packet_chars=4500,
        )
        batch = pipeline.run_queries_with_report(
            [
                {
                    "query_id": "q_alice",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                },
                {
                    "query_id": "q_ben",
                    "query": "Where does Ben live now?",
                    "entity": "Ben",
                    "slot": "home_city",
                    "needs_current": True,
                },
            ]
        )

        self.assertEqual(len(batch["packets"]), 2)
        self.assertEqual(len(batch["read_decisions"]), 2)
        self.assertEqual(len(batch["reader_responses"]), 2)
        self.assertEqual(len(batch["query_results"]), 2)
        self.assertEqual(
            [result["query_id"] for result in batch["query_results"]],
            ["q_alice", "q_ben"],
        )
        self.assertEqual(batch["read_decisions"][0]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(batch["read_decisions"][1]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            batch["summary"]["decision"],
            "GO_QVF_LIFECYCLE_QUERY_BATCH_READY_NO_API",
        )
        self.assertEqual(batch["summary"]["execution_mode"], "pipeline_query_batch_report")
        self.assertEqual(batch["summary"]["query_count"], 2)
        self.assertEqual(
            batch["summary"]["read_decision_counts"],
            {"REJECT_STALE_PREMISE": 1, "ADMIT_CURRENT": 1},
        )
        self.assertEqual(
            batch["summary"]["read_route_counts"],
            {"weak_conservative_gate": 1, "current_support_reader": 1},
        )
        self.assertEqual(
            batch["summary"]["reader_answer_policy_counts"],
            {"correct_premise_only": 1, "answer_from_current": 1},
        )
        self.assertEqual(batch["summary"]["retrieval_budget"]["max_packet_chars"], 4500)
        self.assertEqual(batch["summary"]["store_integrity"], pipeline.validate_integrity())
        self.assertEqual(batch["summary"]["api_calls_made"], 0)

    def test_pipeline_lifecycle_step_admits_then_queries_updated_store(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            max_current=1,
            max_stale=1,
        )

        step = pipeline.run_validity_admission_step(
            records=[
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ],
            queries=[
                {
                    "query_id": "q_alice_now",
                    "query": "Where is Alice's office now?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                }
            ],
            include_state=True,
            step_id="svc-step-001",
        )

        self.assertEqual(step["decision"], "GO_QVF_LIFECYCLE_STEP_READY_NO_API")
        self.assertEqual(step["execution_mode"], "pipeline_lifecycle_step")
        self.assertEqual(step["step_id"], "svc-step-001")
        self.assertEqual(step["records_submitted"], 1)
        self.assertEqual(step["admission_event_count"], 2)
        self.assertEqual(step["query_count"], 1)
        self.assertEqual(step["api_calls_made"], 0)
        self.assertEqual(step["store_integrity_before"]["records"], 1)
        self.assertEqual(step["store_integrity_after"], pipeline.validate_integrity())
        self.assertEqual(step["store_integrity"], step["store_integrity_after"])
        self.assertEqual(
            step["store_integrity_delta"],
            {
                "current_index_entries": 0,
                "current_records": 0,
                "link_edges": 4,
                "records": 1,
            },
        )
        self.assertEqual(step["state_delta"]["input_memory_ids"], ["mem_alice_new"])
        self.assertEqual(
            step["state_delta"]["admission_event_memory_ids"],
            ["mem_alice_new", "mem_alice_old"],
        )
        self.assertEqual(step["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(step["state_delta"]["superseded_memory_ids"], ["mem_alice_old"])
        self.assertEqual(step["state_delta"]["rejected_memory_ids"], [])
        self.assertEqual(step["state_delta"]["query_ids"], ["q_alice_now"])
        self.assertEqual(
            step["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_now": "ADMIT_CURRENT"},
        )
        self.assertEqual(
            step["admission_report"]["admission_status_counts"],
            {"admit_current": 1, "admit_as_stale_contrast": 1},
        )
        result = step["query_report"]["query_results"][0]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_alice_new"])
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        self.assertEqual(step["store_integrity"], pipeline.validate_integrity())
        self.assertEqual(step["state"]["store_integrity"], pipeline.validate_integrity())
        self.assertEqual(step["state"]["config"]["max_stale"], 1)

    def test_pipeline_preview_validity_admission_step_reports_query_without_mutating_store(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            max_current=1,
            max_stale=1,
        )
        before_store = pipeline.export_memory_store()
        before_integrity = pipeline.validate_integrity()

        preview = pipeline.preview_validity_admission_step(
            records=[
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ],
            queries=[
                {
                    "query_id": "q_alice_now",
                    "query": "Where is Alice's office now?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                }
            ],
            step_id="preview-step-001",
        )

        self.assertEqual(
            preview["decision"],
            "GO_QVF_LIFECYCLE_STEP_PREVIEW_READY_NO_API",
        )
        self.assertEqual(preview["execution_mode"], "pipeline_lifecycle_step_preview")
        self.assertTrue(preview["preview_does_not_mutate_source"])
        self.assertTrue(preview["source_store_unchanged"])
        self.assertEqual(preview["step_id"], "preview-step-001")
        self.assertEqual(preview["records_submitted"], 1)
        self.assertEqual(preview["query_count"], 1)
        self.assertEqual(preview["store_integrity_before"], before_integrity)
        self.assertEqual(preview["store_integrity_after"]["records"], 2)
        self.assertEqual(preview["store_integrity_delta"]["records"], 1)
        self.assertEqual(preview["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(preview["state_delta"]["superseded_memory_ids"], ["mem_alice_old"])
        self.assertEqual(
            preview["changed_memory_ids"],
            ["mem_alice_new", "mem_alice_old"],
        )
        self.assertEqual(preview["store_diff"]["added_memory_ids"], ["mem_alice_new"])
        self.assertEqual(preview["store_diff"]["updated_memory_ids"], ["mem_alice_old"])
        self.assertEqual(
            preview["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_now": "ADMIT_CURRENT"},
        )
        result = preview["query_report"]["query_results"][0]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_alice_new"])
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        self.assertEqual(preview["original_store_integrity"], before_integrity)
        self.assertEqual(pipeline.export_memory_store(), before_store)
        self.assertEqual(pipeline.validate_integrity(), before_integrity)
        current_result = pipeline.query(
            {
                "query_id": "q_alice_current",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        )
        self.assertEqual(
            current_result["reader_response"]["answer_evidence_ids"],
            ["mem_alice_old"],
        )

    def test_pipeline_lifecycle_step_accepts_empty_inputs_and_rejects_bad_shapes(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])

        step = pipeline.run_validity_admission_step()
        self.assertEqual(step["records_submitted"], 0)
        self.assertEqual(step["query_count"], 0)
        self.assertEqual(step["admission_report"]["admission_event_count"], 0)
        self.assertEqual(step["query_report"]["query_results"], [])
        self.assertEqual(
            step["store_integrity_delta"],
            {
                "current_index_entries": 0,
                "current_records": 0,
                "link_edges": 0,
                "records": 0,
            },
        )
        self.assertEqual(step["state_delta"]["input_memory_ids"], [])
        self.assertEqual(step["state_delta"]["query_ids"], [])

        with self.assertRaisesRegex(ValueError, "records must be a list"):
            pipeline.run_validity_admission_step(records={"memory_id": "not_a_list"})  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "queries must be a list"):
            pipeline.run_validity_admission_step(queries={"query_id": "not_a_list"})  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "weak_gate_outputs must be a list"):
            pipeline.run_validity_admission_step(weak_gate_outputs={"query_id": "not_a_list"})  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, r"weak_gate_outputs\[0\] must be an object"):
            pipeline.run_validity_admission_step(weak_gate_outputs=["not_an_object"])  # type: ignore[list-item]
        with self.assertRaisesRegex(ValueError, "step_id must be a non-empty string"):
            pipeline.run_validity_admission_step(step_id=" ")

    def test_pipeline_lifecycle_step_rejects_bad_weak_gate_rows_before_admission(self) -> None:
        bad_output_cases = [
            (["bad_row"], r"weak_gate_outputs\[0\] must be an object"),
            ([{"decision": "REJECT_STALE_PREMISE"}], r"weak_gate_outputs\[0\] must include task_id or query_id"),
            (
                [
                    {"query_id": "q_alice_stale_premise", "decision": "REJECT_STALE_PREMISE"},
                    {"query_id": "q_alice_stale_premise", "decision": "UNKNOWN_CURRENT"},
                ],
                "Duplicate weak gate output query_id: q_alice_stale_premise",
            ),
        ]

        for weak_gate_outputs, expected_error in bad_output_cases:
            with self.subTest(expected_error=expected_error):
                pipeline = QVFMemoryPipeline.from_records(
                    [
                        memory(
                            "mem_alice_old",
                            "Alice",
                            "office_city",
                            "Paris",
                            "2024-01-01T00:00:00+00:00",
                        )
                    ]
                )
                before_integrity = pipeline.validate_integrity()

                with self.assertRaisesRegex(ValueError, expected_error):
                    pipeline.run_validity_admission_step(
                        records=[
                            memory(
                                "mem_alice_new",
                                "Alice",
                                "office_city",
                                "Berlin",
                                "2025-01-01T00:00:00+00:00",
                            )
                        ],
                        queries=[
                            {
                                "query_id": "q_alice_stale_premise",
                                "query": "Since Alice is still in Paris, where should I send mail?",
                                "entity": "Alice",
                                "slot": "office_city",
                                "needs_current": True,
                                "embedded_premise_value": "Paris",
                            }
                        ],
                        weak_gate_outputs=weak_gate_outputs,  # type: ignore[arg-type]
                    )

                self.assertEqual(pipeline.validate_integrity(), before_integrity)
                self.assertEqual(
                    [row["memory_id"] for row in pipeline.export_memory_store()],
                    ["mem_alice_old"],
                )

    def test_pipeline_lifecycle_step_allows_unparseable_weak_gate_decisions(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        step = pipeline.run_validity_admission_step(
            records=[
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ],
            queries=[
                {
                    "query_id": "q_alice_stale_premise",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                }
            ],
            weak_gate_outputs=[
                {
                    "query_id": "q_alice_stale_premise",
                    "decision": "not_a_known_decision",
                }
            ],
        )

        self.assertEqual(step["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(
            step["query_report"]["summary"]["weak_gate_adapter_summary"][
                "fallback_missing_or_unparseable_output_count"
            ],
            1,
        )
        self.assertEqual(
            step["query_report"]["read_decisions"][0]["decision_source"],
            "missing_or_unparseable_weak_gate_output",
        )

    def test_pipeline_lifecycle_step_rejects_bad_queries_before_admission(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        before_integrity = pipeline.validate_integrity()

        with self.assertRaisesRegex(ValueError, "query.entity"):
            pipeline.run_validity_admission_step(
                records=[
                    memory(
                        "mem_alice_new",
                        "Alice",
                        "office_city",
                        "Berlin",
                        "2025-01-01T00:00:00+00:00",
                    )
                ],
                queries=[
                    {
                        "query_id": "q_missing_entity",
                        "query": "Where should I send mail now?",
                        "slot": "office_city",
                        "needs_current": True,
                    }
                ],
            )

        self.assertEqual(pipeline.validate_integrity(), before_integrity)
        self.assertEqual(
            [row["memory_id"] for row in pipeline.export_memory_store()],
            ["mem_alice_old"],
        )

    def test_pipeline_lifecycle_step_rejects_bad_record_batch_before_partial_admission(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        valid_record = memory(
            "mem_alice_valid",
            "Alice",
            "office_city",
            "Paris",
            "2024-01-01T00:00:00+00:00",
        )
        invalid_record = memory(
            "mem_alice_invalid",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        invalid_record["source_confidence"] = "high"

        with self.assertRaisesRegex(ValueError, "memory.source_confidence"):
            pipeline.run_validity_admission_step(records=[valid_record, invalid_record])

        self.assertEqual(pipeline.validate_integrity()["records"], 0)
        self.assertEqual(pipeline.export_memory_store(), [])

    def test_pipeline_lifecycle_step_request_runs_from_object(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        step = pipeline.run_validity_admission_step_request(
            {
                "step_id": "api-request-step-001",
                "records": [
                    memory(
                        "mem_alice_new",
                        "Alice",
                        "office_city",
                        "Berlin",
                        "2025-01-01T00:00:00+00:00",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_alice_now",
                        "query": "Where is Alice's office now?",
                        "entity": "Alice",
                        "slot": "office_city",
                        "needs_current": True,
                    }
                ],
                "include_state": True,
            }
        )

        self.assertEqual(step["step_id"], "api-request-step-001")
        self.assertEqual(step["records_submitted"], 1)
        self.assertEqual(step["query_count"], 1)
        self.assertEqual(step["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(
            step["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_now": "ADMIT_CURRENT"},
        )
        self.assertEqual(step["state"]["store_integrity"], pipeline.validate_integrity())

    def test_pipeline_lifecycle_step_request_can_use_weak_gate_outputs(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        step = pipeline.run_validity_admission_step_request(
            {
                "step_id": "weak-gate-request-step-001",
                "records": [
                    memory(
                        "mem_alice_new",
                        "Alice",
                        "office_city",
                        "Berlin",
                        "2025-01-01T00:00:00+00:00",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_alice_stale_premise",
                        "query": "Since Alice is still in Paris, where should I send mail?",
                        "entity": "Alice",
                        "slot": "office_city",
                        "needs_current": True,
                        "embedded_premise_value": "Paris",
                    }
                ],
                "weak_gate_outputs": [
                    {
                        "query_id": "q_alice_stale_premise",
                        "decision": "REJECT_STALE_PREMISE",
                        "support": "",
                        "blocker": "mem_alice_new",
                        "final_answer": "Alice is no longer supported as being in Paris.",
                    }
                ],
            }
        )

        read_decision = step["query_report"]["read_decisions"][0]
        self.assertEqual(step["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(read_decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(read_decision["decision_source"], "weak_gate_output")
        self.assertEqual(read_decision["blocking_evidence_ids"], ["mem_alice_new"])
        self.assertEqual(
            step["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_stale_premise": "REJECT_STALE_PREMISE"},
        )
        self.assertEqual(
            step["query_report"]["summary"]["execution_mode"],
            "pipeline_query_batch_report_with_weak_gate_outputs",
        )
        self.assertEqual(
            step["query_report"]["summary"]["weak_gate_adapter_summary"][
                "adapted_from_weak_gate_output_count"
            ],
            1,
        )
        self.assertIn(
            "Berlin",
            step["query_report"]["reader_responses"][0]["final_answer"],
        )

    def test_pipeline_lifecycle_step_request_rejects_bad_shapes(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        cases = [
            ([], "request must be an object"),
            ({"records": {"memory_id": "bad"}}, "request.records must be a list"),
            ({"queries": {"query_id": "bad"}}, "request.queries must be a list"),
            ({"include_state": "yes"}, "request.include_state must be a boolean"),
            ({"weak_gate_outputs": {"query_id": "bad"}}, "request.weak_gate_outputs must be a list"),
            (
                {"weak_gate_outputs": ["bad"]},
                r"request.weak_gate_outputs\[0\] must be an object",
            ),
            ({"step_id": " "}, "step_id must be a non-empty string"),
        ]

        for request, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    pipeline.run_validity_admission_step_request(request)  # type: ignore[arg-type]

    def test_pipeline_lifecycle_steps_runs_transactional_sequence(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        result = pipeline.run_validity_admission_steps(
            [
                {
                    "step_id": "step-old",
                    "records": [
                        memory(
                            "mem_alice_old",
                            "Alice",
                            "office_city",
                            "Paris",
                            "2024-01-01T00:00:00+00:00",
                        )
                    ],
                    "queries": [
                        {
                            "query_id": "q_alice_old",
                            "query": "Where is Alice's office now?",
                            "entity": "Alice",
                            "slot": "office_city",
                            "needs_current": True,
                        }
                    ],
                },
                {
                    "step_id": "step-new",
                    "records": [
                        memory(
                            "mem_alice_new",
                            "Alice",
                            "office_city",
                            "Berlin",
                            "2025-01-01T00:00:00+00:00",
                        )
                    ],
                    "queries": [
                        {
                            "query_id": "q_alice_new",
                            "query": "Since Alice is still in Paris, where should I send mail?",
                            "entity": "Alice",
                            "slot": "office_city",
                            "needs_current": True,
                            "embedded_premise_value": "Paris",
                        }
                    ],
                },
            ],
            include_final_state=True,
        )

        self.assertEqual(
            result["decision"],
            "GO_QVF_LIFECYCLE_MULTI_STEP_READY_NO_API",
        )
        self.assertEqual(result["summary"]["step_count"], 2)
        self.assertEqual(result["summary"]["step_ids"], ["step-old", "step-new"])
        self.assertEqual(result["summary"]["records_submitted"], 2)
        self.assertEqual(result["summary"]["admission_event_count"], 3)
        self.assertEqual(result["summary"]["query_count"], 2)
        self.assertEqual(
            result["summary"]["query_mode_counts"],
            {"deterministic_router": 2},
        )
        self.assertEqual(result["steps"][0]["batch_step_index"], 0)
        self.assertEqual(result["steps"][1]["batch_step_index"], 1)
        self.assertEqual(
            result["steps"][0]["query_report"]["query_results"][0]["read_decision"]["decision"],
            "ADMIT_CURRENT",
        )
        self.assertEqual(
            result["steps"][1]["query_report"]["query_results"][0]["read_decision"]["decision"],
            "REJECT_STALE_PREMISE",
        )
        self.assertEqual(
            pipeline.store.current_by_key[("", "", "", "alice", "office_city")],
            "mem_alice_new",
        )
        self.assertEqual(pipeline.store.records["mem_alice_old"].current_status, "superseded")
        self.assertEqual(result["state"]["store_integrity"], pipeline.validate_integrity())
        self.assertEqual(result["summary"]["api_calls_made"], 0)

    def test_pipeline_lifecycle_steps_default_transaction_rolls_back_on_later_bad_step(
        self,
    ) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        requests = [
            {
                "step_id": "valid-step",
                "records": [
                    memory(
                        "mem_alice_valid",
                        "Alice",
                        "office_city",
                        "Paris",
                        "2024-01-01T00:00:00+00:00",
                    )
                ],
            },
            {
                "step_id": "bad-step",
                "records": [
                    {
                        "memory_id": "mem_bad_missing_fields",
                        "entity": "Alice",
                    }
                ],
            },
        ]

        with self.assertRaisesRegex(ValueError, "memory.slot"):
            pipeline.run_validity_admission_steps(requests)

        self.assertEqual(pipeline.validate_integrity()["records"], 0)
        self.assertEqual(pipeline.export_memory_store(), [])

    def test_pipeline_lifecycle_steps_rejects_bad_batch_controls(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        with self.assertRaisesRegex(ValueError, "step requests must be a list"):
            pipeline.run_validity_admission_steps({"records": []})  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "Duplicate lifecycle step_id"):
            pipeline.run_validity_admission_steps(
                [
                    {"step_id": "duplicate-step"},
                    {"step_id": "duplicate-step"},
                ]
            )
        with self.assertRaisesRegex(ValueError, "include_final_state must be a boolean"):
            pipeline.run_validity_admission_steps([], include_final_state="yes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "transactional must be a boolean"):
            pipeline.run_validity_admission_steps([], transactional="yes")  # type: ignore[arg-type]

    def test_pipeline_query_requires_non_empty_identity_fields(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        query = {
            "query_id": "q_missing_entity",
            "query": "Where is Dana now?",
            "slot": "office_city",
            "needs_current": True,
        }

        with self.assertRaisesRegex(ValueError, "query.entity"):
            pipeline.query(query)

    def test_pipeline_query_rejects_invalid_gate_values(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        cases = [
            ({"max_age_days": -1}, "query.max_age_days"),
            ({"min_source_confidence": 1.2}, "query.min_source_confidence"),
            ({"min_supporting_count": 1.5}, "query.min_supporting_count"),
            ({"as_of": "not-a-date"}, "query.as_of"),
            ({"as_of": "2025-03-01T00:00:00"}, "timezone"),
            ({"risk_profile": True}, "query.risk_profile"),
            ({"risk_profile": ""}, "query.risk_profile"),
            ({"risk_profile": "experimental"}, "Unknown query.risk_profile"),
            (
                {"risk_profile": "default", "validity_profile": "high_stakes"},
                "risk_profile and query.validity_profile",
            ),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                query = {
                    "query_id": "q_bad_gate",
                    "query": "Where is Dana now?",
                    "entity": "Dana",
                    "slot": "office_city",
                    "needs_current": True,
                }
                query.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    pipeline.query(query)

    def test_pipeline_query_rejects_invalid_scope_and_policy_shapes(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        cases = [
            ({"scope": "tenant-a"}, "query.scope"),
            ({"scope": {"tenant_id": 42}}, "query.scope.tenant_id"),
            ({"allowed_source_types": {"source_type": "hr"}}, "allowed_source_types"),
            ({"blocked_source_ids": [""]}, "blocked_source_ids"),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                query = {
                    "query_id": "q_bad_shape",
                    "query": "Where is Dana now?",
                    "entity": "Dana",
                    "slot": "office_city",
                    "needs_current": True,
                }
                query.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    pipeline.query(query)

    def test_run_queries_rejects_duplicate_query_ids(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        queries = [
            {
                "query_id": "q_duplicate",
                "query": "Where is Dana now?",
                "entity": "Dana",
                "slot": "office_city",
                "needs_current": True,
            },
            {
                "query_id": "q_duplicate",
                "query": "Where does Dana work now?",
                "entity": "Dana",
                "slot": "office_city",
                "needs_current": True,
            },
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate query_id"):
            pipeline.run_queries(queries)

    def test_build_packets_from_store_rejects_invalid_query_batch_shape(self) -> None:
        store = ValidityAwareMemoryStore()

        with self.assertRaisesRegex(ValueError, "queries must be a list"):
            build_packets_from_store(store, {"query_id": "q_not_a_list"})  # type: ignore[arg-type]

    def test_pipeline_reloads_from_exported_records(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        reloaded = QVFMemoryPipeline.from_exported_records(
            pipeline.export_memory_store()
        )
        result = reloaded.query(
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            }
        )

        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_ben_new"])
        self.assertIn("Milan", result["reader_response"]["final_answer"])

    def test_pipeline_state_snapshot_round_trips_configuration_and_store(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_low",
                    "Ben",
                    "home_city",
                    "Oslo",
                    "2026-01-01T00:00:00+00:00",
                    source_confidence=0.3,
                ),
            ],
            low_confidence_threshold=0.6,
            max_current=1,
            max_supporting=1,
            max_stale=1,
            max_excluded=1,
            max_packet_chars=4500,
            include_validity_edges=False,
            include_weak_gate_card=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "pipeline_state.json"
            pipeline.save_state(state_path)
            saved_state = json.loads(state_path.read_text(encoding="utf-8"))
            reloaded = QVFMemoryPipeline.from_state_file(state_path)

        self.assertEqual(saved_state["state_version"], "qvf_validity_admission_pipeline_state_v0.1_no_api")
        self.assertEqual(saved_state["api_calls_made"], 0)
        self.assertEqual(saved_state["config"]["low_confidence_threshold"], 0.6)
        self.assertEqual(saved_state["config"]["max_packet_chars"], 4500)
        self.assertFalse(saved_state["config"]["include_validity_edges"])
        self.assertEqual(saved_state["store_integrity"], pipeline.validate_integrity())
        self.assertGreaterEqual(len(saved_state["admission_log"]), 3)
        self.assertEqual(reloaded.max_packet_chars, 4500)
        self.assertFalse(reloaded.include_validity_edges)
        self.assertEqual(reloaded.validate_integrity(), pipeline.validate_integrity())
        self.assertEqual(
            len(reloaded.export_state()["admission_log"]),
            len(saved_state["admission_log"]),
        )
        result = reloaded.query(
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            }
        )
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_ben_new"])

    def test_pipeline_summarize_store_reports_validity_metadata(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_low",
                    "Ben",
                    "home_city",
                    "Oslo",
                    "2026-01-01T00:00:00+00:00",
                    source_confidence=0.3,
                ),
            ],
            low_confidence_threshold=0.6,
        )

        summary = pipeline.summarize_store()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_STORE_SUMMARY_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "store_summary_only")
        self.assertEqual(summary["memory_store_records"], 3)
        self.assertEqual(summary["store_integrity"]["records"], 3)
        self.assertEqual(summary["store_integrity"]["current_records"], 1)
        self.assertEqual(summary["admission_status_counts"]["admit_current"], 1)
        self.assertEqual(summary["admission_status_counts"]["admit_as_stale_contrast"], 1)
        self.assertEqual(summary["admission_status_counts"]["reject_low_confidence"], 1)
        self.assertEqual(summary["current_status_counts"]["current"], 1)
        self.assertEqual(summary["current_status_counts"]["superseded"], 1)
        self.assertEqual(summary["current_status_counts"]["rejected"], 1)
        self.assertEqual(summary["evidence_role_counts"]["current_support"], 1)
        self.assertEqual(summary["evidence_role_counts"]["stale_contrast"], 1)
        self.assertEqual(summary["evidence_role_counts"]["excluded_low_confidence"], 1)
        self.assertEqual(
            summary["memory_ids_by_admission_status"],
            {
                "admit_as_stale_contrast": ["mem_ben_old"],
                "admit_current": ["mem_ben_new"],
                "reject_low_confidence": ["mem_ben_low"],
            },
        )
        self.assertEqual(
            summary["memory_ids_by_current_status"],
            {
                "current": ["mem_ben_new"],
                "rejected": ["mem_ben_low"],
                "superseded": ["mem_ben_old"],
            },
        )
        self.assertEqual(
            summary["memory_ids_by_evidence_role"],
            {
                "current_support": ["mem_ben_new"],
                "excluded_low_confidence": ["mem_ben_low"],
                "stale_contrast": ["mem_ben_old"],
            },
        )
        self.assertEqual(summary["source_type_counts"], {"synthetic_demo": 3})
        self.assertEqual(summary["scope_counts"], {"::::": 3})
        self.assertEqual(summary["entity_slot_counts"], {"ben::home_city": 3})
        self.assertEqual(
            summary["current_index"],
            [
                {
                    "namespace": "",
                    "tenant_id": "",
                    "user_id": "",
                    "entity": "ben",
                    "slot": "home_city",
                    "memory_id": "mem_ben_new",
                }
            ],
        )

    def test_pipeline_inspect_memory_reports_links_and_current_index(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )

        inspection = pipeline.inspect_memory(" mem_ben_old ")

        self.assertEqual(
            inspection["decision"],
            "GO_QVF_LIFECYCLE_MEMORY_INSPECTION_READY_NO_API",
        )
        self.assertEqual(inspection["execution_mode"], "memory_inspection_only")
        self.assertEqual(inspection["memory_id"], "mem_ben_old")
        self.assertEqual(inspection["record"]["current_status"], "superseded")
        self.assertEqual(inspection["record"]["evidence_role"], "stale_contrast")
        self.assertEqual(inspection["current_index_memory_id"], "mem_ben_new")
        self.assertFalse(inspection["is_current_index_target"])
        self.assertEqual(
            inspection["same_scoped_key_memory_ids"],
            ["mem_ben_new", "mem_ben_old"],
        )
        self.assertEqual(
            inspection["outbound_links"],
            [
                {
                    "source": "mem_ben_old",
                    "target": "mem_ben_new",
                    "type": "contradicts",
                },
                {
                    "source": "mem_ben_old",
                    "target": "mem_ben_new",
                    "type": "superseded_by",
                },
            ],
        )
        self.assertEqual(
            inspection["inbound_links"],
            [
                {
                    "source": "mem_ben_new",
                    "target": "mem_ben_old",
                    "type": "contradicts",
                },
                {
                    "source": "mem_ben_new",
                    "target": "mem_ben_old",
                    "type": "supersedes",
                },
            ],
        )
        self.assertEqual(inspection["store_integrity"]["records"], 2)
        with self.assertRaisesRegex(ValueError, "Unknown memory_id"):
            pipeline.inspect_memory("missing_memory")

    def test_pipeline_inspect_scope_reports_scoped_history(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                    namespace="app",
                    tenant_id="tenant_1",
                    user_id="user_1",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                    namespace="app",
                    tenant_id="tenant_1",
                    user_id="user_1",
                ),
                memory(
                    "mem_ben_other_user",
                    "Ben",
                    "home_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                    namespace="app",
                    tenant_id="tenant_1",
                    user_id="user_2",
                ),
            ]
        )

        inspection = pipeline.inspect_scope(
            " BEN ",
            " Home_City ",
            namespace=" APP ",
            tenant_id=" TENANT_1 ",
            user_id=" USER_1 ",
        )
        empty_inspection = pipeline.inspect_scope(
            "Ben",
            "home_city",
            namespace="app",
            tenant_id="tenant_1",
            user_id="missing_user",
        )

        self.assertEqual(
            inspection["decision"],
            "GO_QVF_LIFECYCLE_SCOPE_INSPECTION_READY_NO_API",
        )
        self.assertEqual(inspection["execution_mode"], "scope_inspection_only")
        self.assertEqual(
            inspection["normalized_scoped_key"],
            "app::tenant_1::user_1::ben::home_city",
        )
        self.assertEqual(inspection["record_count"], 2)
        self.assertEqual(
            inspection["history_memory_ids"],
            ["mem_ben_old", "mem_ben_new"],
        )
        self.assertEqual(inspection["current_index_memory_id"], "mem_ben_new")
        self.assertEqual(inspection["current_record"]["value"], "Milan")
        self.assertEqual(
            [row["current_status"] for row in inspection["history"]],
            ["superseded", "current"],
        )
        self.assertEqual(
            inspection["admission_status_counts"],
            {"admit_as_stale_contrast": 1, "admit_current": 1},
        )
        self.assertEqual(len(inspection["in_scope_edges"]), 4)
        self.assertEqual(empty_inspection["record_count"], 0)
        self.assertIsNone(empty_inspection["current_index_memory_id"])
        self.assertIsNone(empty_inspection["current_record"])

    def test_pipeline_inspect_query_reports_packet_and_reader_decision(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        query = {
            "query_id": "q_ben",
            "query": "Where does Ben live now?",
            "entity": "Ben",
            "slot": "home_city",
            "needs_current": True,
        }

        inspection = pipeline.inspect_query(query)

        self.assertEqual(
            inspection["decision"],
            "GO_QVF_LIFECYCLE_QUERY_INSPECTION_READY_NO_API",
        )
        self.assertEqual(inspection["execution_mode"], "query_inspection_only")
        self.assertEqual(inspection["query_id"], "q_ben")
        self.assertEqual(inspection["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(inspection["reader_response"]["answer_policy"], "answer_from_current")
        self.assertEqual(
            inspection["selected_memory_ids_by_bucket"]["current_evidence"],
            ["mem_ben_new"],
        )
        self.assertEqual(
            inspection["selected_memory_ids_by_bucket"]["stale_or_blocked_evidence"],
            ["mem_ben_old"],
        )
        self.assertEqual(
            inspection["packet"]["compact_validity_packet"]["current_evidence"][0]["value"],
            "Milan",
        )
        self.assertEqual(inspection["validity_edge_count"], 4)
        self.assertTrue(inspection["weak_gate_card_present"])
        self.assertEqual(inspection["store_integrity"]["records"], 2)

    def test_pipeline_state_rejects_integrity_mismatch(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                )
            ]
        )
        state = pipeline.export_state()
        state["store_integrity"]["records"] = 999

        with self.assertRaisesRegex(ValueError, "store_integrity"):
            QVFMemoryPipeline.from_state(state)

    def test_method_lock_summary_fingerprints_config_and_source(self) -> None:
        summary = build_method_lock_summary(
            ["method_lock.json"],
            low_confidence_threshold=0.42,
            max_current=1,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )
        changed_config_summary = build_method_lock_summary(
            ["method_lock.json"],
            low_confidence_threshold=0.42,
            max_current=2,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )

        self.assertEqual(
            summary["decision"],
            "GO_QVF_LIFECYCLE_METHOD_LOCK_READY_NO_API",
        )
        self.assertEqual(summary["execution_mode"], "method_lock_export_only")
        self.assertEqual(summary["method_config"]["low_confidence_threshold"], 0.42)
        self.assertEqual(summary["method_config"]["max_packet_chars"], 2048)
        self.assertTrue(summary["method_config"]["include_validity_edges"])
        self.assertFalse(summary["method_config"]["include_weak_gate_card"])
        self.assertEqual(
            summary["source_fingerprint"]["file_name"],
            "_pipeline_core.py",
        )
        self.assertEqual(len(summary["source_fingerprint"]["sha256"]), 64)
        self.assertEqual(len(summary["method_signature_sha256"]), 64)
        self.assertNotEqual(
            summary["method_signature_sha256"],
            changed_config_summary["method_signature_sha256"],
        )
        self.assertEqual(summary["api_calls_made"], 0)

    def test_method_lock_comparison_reports_match_and_config_mismatch(self) -> None:
        expected_lock = build_method_lock_summary(
            ["method_lock.json"],
            low_confidence_threshold=0.42,
            max_current=1,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )

        match = build_method_lock_comparison_summary(
            expected_lock,
            ["method_lock_compare.json"],
            low_confidence_threshold=0.42,
            max_current=1,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )
        mismatch = build_method_lock_comparison_summary(
            expected_lock,
            ["method_lock_compare.json"],
            low_confidence_threshold=0.42,
            max_current=2,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )

        self.assertEqual(
            match["decision"],
            "GO_QVF_LIFECYCLE_METHOD_LOCK_MATCH_NO_API",
        )
        self.assertTrue(match["lock_matches"])
        self.assertTrue(match["signature_matches"])
        self.assertTrue(match["config_matches"])
        self.assertTrue(match["source_fingerprint_matches"])
        self.assertEqual(match["config_differences"], [])
        self.assertEqual(
            mismatch["decision"],
            "NO_GO_QVF_LIFECYCLE_METHOD_LOCK_MISMATCH_NO_API",
        )
        self.assertFalse(mismatch["lock_matches"])
        self.assertFalse(mismatch["signature_matches"])
        self.assertFalse(mismatch["config_matches"])
        self.assertTrue(mismatch["source_fingerprint_matches"])
        self.assertEqual(mismatch["config_differences"][0]["field"], "max_current")
        self.assertEqual(mismatch["config_differences"][0]["expected"], 1)
        self.assertEqual(mismatch["config_differences"][0]["current"], 2)
        self.assertEqual(mismatch["api_calls_made"], 0)

    def test_enforce_method_lock_match_raises_on_config_mismatch(self) -> None:
        expected_lock = build_method_lock_summary(
            ["method_lock.json"],
            low_confidence_threshold=0.42,
            max_current=1,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )

        comparison = enforce_method_lock_match(
            expected_lock,
            low_confidence_threshold=0.42,
            max_current=1,
            max_supporting=2,
            max_stale=3,
            max_excluded=4,
            max_packet_chars=2048,
            include_validity_edges=True,
            include_weak_gate_card=False,
        )
        with self.assertRaisesRegex(ValueError, "method lock mismatch"):
            enforce_method_lock_match(
                expected_lock,
                low_confidence_threshold=0.42,
                max_current=2,
                max_supporting=2,
                max_stale=3,
                max_excluded=4,
                max_packet_chars=2048,
                include_validity_edges=True,
                include_weak_gate_card=False,
            )

        self.assertTrue(comparison["lock_matches"])

    def test_cli_export_method_lock_only_does_not_read_dataset_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "records_should_not_be_read.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            store_out = root / "store_should_not_exist.jsonl"
            packets_out = root / "packets_should_not_exist.json"
            summary_out = root / "method_lock.json"

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--summary-out",
                str(summary_out),
                "--max-current",
                "3",
                "--max-packet-chars",
                "1234",
                "--no-validity-edges",
                "--no-weak-gate-card",
                "--export-method-lock-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(
            summary["decision"],
            "GO_QVF_LIFECYCLE_METHOD_LOCK_READY_NO_API",
        )
        self.assertEqual(summary["method_config"]["max_current"], 3)
        self.assertEqual(summary["method_config"]["max_packet_chars"], 1234)
        self.assertFalse(summary["method_config"]["include_validity_edges"])
        self.assertFalse(summary["method_config"]["include_weak_gate_card"])
        self.assertIn(summary_out.name, summary["output_files"])
        self.assertFalse(store_out.exists())
        self.assertFalse(packets_out.exists())

    def test_cli_compare_method_lock_only_does_not_read_dataset_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "records_should_not_be_read.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            lock_in = root / "method_lock.json"
            summary_out = root / "method_lock_compare.json"
            packets_out = root / "packets_should_not_exist.json"
            expected_lock = build_method_lock_summary(
                ["method_lock.json"],
                low_confidence_threshold=0.5,
                max_current=2,
                max_supporting=2,
                max_stale=2,
                max_excluded=2,
                max_packet_chars=None,
                include_validity_edges=True,
                include_weak_gate_card=True,
            )
            lock_in.write_text(
                json.dumps(expected_lock, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--packets-out",
                str(packets_out),
                "--method-lock-in",
                str(lock_in),
                "--summary-out",
                str(summary_out),
                "--max-current",
                "2",
                "--compare-method-lock-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(
            summary["decision"],
            "GO_QVF_LIFECYCLE_METHOD_LOCK_MATCH_NO_API",
        )
        self.assertTrue(summary["lock_matches"])
        self.assertTrue(summary["config_matches"])
        self.assertIn(summary_out.name, summary["output_files"])
        self.assertFalse(packets_out.exists())

    def test_cli_enforce_method_lock_blocks_mismatch_before_dataset_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lock_in = root / "method_lock.json"
            missing_records = root / "records_should_not_be_read.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            expected_lock = build_method_lock_summary(
                ["method_lock.json"],
                low_confidence_threshold=0.5,
                max_current=1,
                max_supporting=2,
                max_stale=2,
                max_excluded=2,
                max_packet_chars=None,
                include_validity_edges=True,
                include_weak_gate_card=True,
            )
            lock_in.write_text(
                json.dumps(expected_lock, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--method-lock-in",
                str(lock_in),
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--max-current",
                "2",
                "--enforce-method-lock",
            ]
            with patch("sys.argv", argv):
                with self.assertRaisesRegex(ValueError, "method lock mismatch"):
                    main()

    def test_cli_admit_only_writes_and_validates_pipeline_state(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records_in = root / "records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            store_out = root / "store.jsonl"
            state_out = root / "state.json"
            admission_log_out = root / "admission_log.csv"
            admit_summary_out = root / "admit_summary.json"
            validate_summary_out = root / "validate_summary.json"

            records_in.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n",
                encoding="utf-8",
            )

            admit_argv = [
                "qvf-va",
                "--records",
                str(records_in),
                "--queries",
                str(missing_queries),
                "--store-out",
                str(store_out),
                "--state-out",
                str(state_out),
                "--admission-log-out",
                str(admission_log_out),
                "--summary-out",
                str(admit_summary_out),
                "--admit-only",
            ]
            with patch("sys.argv", admit_argv):
                with redirect_stdout(io.StringIO()):
                    main()

            state = json.loads(state_out.read_text(encoding="utf-8"))
            admit_summary = json.loads(admit_summary_out.read_text(encoding="utf-8"))

            validate_argv = [
                "qvf-va",
                "--load-state",
                str(state_out),
                "--records",
                str(root / "records_should_not_be_read.jsonl"),
                "--queries",
                str(root / "queries_should_not_be_read.jsonl"),
                "--summary-out",
                str(validate_summary_out),
                "--validate-state-only",
            ]
            with patch("sys.argv", validate_argv):
                with redirect_stdout(io.StringIO()):
                    main()

            validate_summary = json.loads(validate_summary_out.read_text(encoding="utf-8"))

        self.assertEqual(state["state_version"], "qvf_validity_admission_pipeline_state_v0.1_no_api")
        self.assertEqual(len(state["memory_store"]), 2)
        self.assertEqual(state["store_integrity"]["current_records"], 1)
        self.assertIn(state_out.name, admit_summary["output_files"])
        self.assertEqual(
            validate_summary["decision"],
            "GO_QVF_LIFECYCLE_PIPELINE_STATE_READY_NO_API",
        )
        self.assertEqual(validate_summary["execution_mode"], "pipeline_state_validation_only")
        self.assertEqual(
            validate_summary["input_mode"],
            "load_pipeline_state_validate_state_only",
        )
        self.assertEqual(validate_summary["memory_store_records"], 2)
        self.assertGreaterEqual(validate_summary["admission_log_rows"], 2)
        self.assertEqual(validate_summary["store_integrity"], state["store_integrity"])

    def test_cli_summarize_store_only_does_not_require_queries_or_packets(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            summary_out = root / "store_summary.json"
            packets_out = root / "packets_should_not_exist.json"
            query_results_out = root / "results_should_not_exist.json"

            pipeline.save_memory_store(store_in)

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(missing_queries),
                "--summary-out",
                str(summary_out),
                "--packets-out",
                str(packets_out),
                "--query-results-out",
                str(query_results_out),
                "--summarize-store-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            packets_written = packets_out.exists()
            results_written = query_results_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_STORE_SUMMARY_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "store_summary_only")
        self.assertEqual(summary["input_mode"], "load_exported_store_summarize_store_only")
        self.assertEqual(summary["records_loaded"], 2)
        self.assertEqual(summary["memory_store_records"], 2)
        self.assertEqual(summary["store_integrity"]["current_records"], 1)
        self.assertEqual(summary["current_index"][0]["memory_id"], "mem_ben_new")
        self.assertEqual(
            summary["memory_ids_by_current_status"]["current"],
            ["mem_ben_new"],
        )
        self.assertEqual(
            summary["memory_ids_by_current_status"]["superseded"],
            ["mem_ben_old"],
        )
        self.assertIn(summary_out.name, summary["output_files"])
        self.assertFalse(packets_written)
        self.assertFalse(results_written)

    def test_cli_inspect_memory_only_does_not_require_queries_or_packets(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            inspect_out = root / "memory_inspection.json"
            packets_out = root / "packets_should_not_exist.json"
            query_results_out = root / "results_should_not_exist.json"

            pipeline.save_memory_store(store_in)

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(missing_queries),
                "--summary-out",
                str(inspect_out),
                "--packets-out",
                str(packets_out),
                "--query-results-out",
                str(query_results_out),
                "--memory-id",
                "mem_ben_old",
                "--inspect-memory-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            inspection = json.loads(inspect_out.read_text(encoding="utf-8"))
            packets_written = packets_out.exists()
            results_written = query_results_out.exists()

        self.assertEqual(
            inspection["decision"],
            "GO_QVF_LIFECYCLE_MEMORY_INSPECTION_READY_NO_API",
        )
        self.assertEqual(inspection["execution_mode"], "memory_inspection_only")
        self.assertEqual(inspection["input_mode"], "load_exported_store_inspect_memory_only")
        self.assertEqual(inspection["records_loaded"], 2)
        self.assertEqual(inspection["memory_id"], "mem_ben_old")
        self.assertEqual(inspection["current_index_memory_id"], "mem_ben_new")
        self.assertFalse(inspection["is_current_index_target"])
        self.assertIn(inspect_out.name, inspection["output_files"])
        self.assertFalse(packets_written)
        self.assertFalse(results_written)

    def test_cli_inspect_scope_only_does_not_require_queries_or_packets(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                    user_id="user_1",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                    user_id="user_1",
                ),
                memory(
                    "mem_ben_other_user",
                    "Ben",
                    "home_city",
                    "Paris",
                    "2025-01-01T00:00:00+00:00",
                    user_id="user_2",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            inspect_out = root / "scope_inspection.json"
            packets_out = root / "packets_should_not_exist.json"
            query_results_out = root / "results_should_not_exist.json"

            pipeline.save_memory_store(store_in)

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(missing_queries),
                "--summary-out",
                str(inspect_out),
                "--packets-out",
                str(packets_out),
                "--query-results-out",
                str(query_results_out),
                "--scope-entity",
                "Ben",
                "--scope-slot",
                "home_city",
                "--scope-user-id",
                "user_1",
                "--inspect-scope-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            inspection = json.loads(inspect_out.read_text(encoding="utf-8"))
            packets_written = packets_out.exists()
            results_written = query_results_out.exists()

        self.assertEqual(
            inspection["decision"],
            "GO_QVF_LIFECYCLE_SCOPE_INSPECTION_READY_NO_API",
        )
        self.assertEqual(inspection["execution_mode"], "scope_inspection_only")
        self.assertEqual(inspection["input_mode"], "load_exported_store_inspect_scope_only")
        self.assertEqual(inspection["records_loaded"], 3)
        self.assertEqual(inspection["record_count"], 2)
        self.assertEqual(inspection["history_memory_ids"], ["mem_ben_old", "mem_ben_new"])
        self.assertEqual(inspection["current_index_memory_id"], "mem_ben_new")
        self.assertIn(inspect_out.name, inspection["output_files"])
        self.assertFalse(packets_written)
        self.assertFalse(results_written)

    def test_cli_inspect_query_only_writes_single_query_summary(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        queries = [
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            },
            {
                "query_id": "q_other",
                "query": "Where does Ada live now?",
                "entity": "Ada",
                "slot": "home_city",
                "needs_current": True,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store.jsonl"
            queries_in = root / "queries.jsonl"
            inspect_out = root / "query_inspection.json"
            packets_out = root / "packets_should_not_exist.json"
            decisions_out = root / "decisions_should_not_exist.json"
            responses_out = root / "responses_should_not_exist.json"
            query_results_out = root / "results_should_not_exist.json"

            pipeline.save_memory_store(store_in)
            queries_in.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in queries) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(queries_in),
                "--summary-out",
                str(inspect_out),
                "--packets-out",
                str(packets_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(query_results_out),
                "--query-id",
                "q_ben",
                "--inspect-query-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            inspection = json.loads(inspect_out.read_text(encoding="utf-8"))
            packets_written = packets_out.exists()
            decisions_written = decisions_out.exists()
            responses_written = responses_out.exists()
            results_written = query_results_out.exists()

        self.assertEqual(
            inspection["decision"],
            "GO_QVF_LIFECYCLE_QUERY_INSPECTION_READY_NO_API",
        )
        self.assertEqual(inspection["execution_mode"], "query_inspection_only")
        self.assertEqual(inspection["input_mode"], "load_exported_store_inspect_query_only")
        self.assertEqual(inspection["queries_loaded"], 2)
        self.assertEqual(inspection["query_id"], "q_ben")
        self.assertEqual(inspection["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            inspection["selected_memory_ids_by_bucket"]["current_evidence"],
            ["mem_ben_new"],
        )
        self.assertIn(inspect_out.name, inspection["output_files"])
        self.assertFalse(packets_written)
        self.assertFalse(decisions_written)
        self.assertFalse(responses_written)
        self.assertFalse(results_written)

    def test_cli_lifecycle_step_only_loads_state_appends_and_writes_step_report(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            max_stale=1,
        )
        append_record = memory(
            "mem_alice_new",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        query = {
            "query_id": "q_alice_now",
            "query": "Where is Alice's office now?",
            "entity": "Alice",
            "slot": "office_city",
            "needs_current": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            append_in = root / "append.jsonl"
            queries_in = root / "queries.jsonl"
            step_report_out = root / "step_report.json"
            updated_state_out = root / "updated_state.json"
            summary_out = root / "summary.json"
            store_out = root / "store_should_not_exist.jsonl"
            packets_out = root / "packets_should_not_exist.json"
            results_out = root / "results_should_not_exist.json"

            pipeline.save_state(state_in)
            append_in.write_text(json.dumps(append_record) + "\n", encoding="utf-8")
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--append-records",
                str(append_in),
                "--queries",
                str(queries_in),
                "--step-report-out",
                str(step_report_out),
                "--state-out",
                str(updated_state_out),
                "--summary-out",
                str(summary_out),
                "--step-id",
                "cli-step-001",
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--query-results-out",
                str(results_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            updated_state = json.loads(updated_state_out.read_text(encoding="utf-8"))
            store_written = store_out.exists()
            packets_written = packets_out.exists()
            results_written = results_out.exists()

        self.assertEqual(step_report["decision"], "GO_QVF_LIFECYCLE_STEP_READY_NO_API")
        self.assertEqual(step_report["execution_mode"], "pipeline_lifecycle_step")
        self.assertEqual(step_report["step_id"], "cli-step-001")
        self.assertEqual(step_report["input_mode"], "load_pipeline_state_lifecycle_step_only")
        self.assertEqual(step_report["append_records_loaded"], 1)
        self.assertEqual(step_report["records_submitted"], 1)
        self.assertEqual(step_report["query_count"], 1)
        self.assertEqual(step_report["admission_event_count"], 2)
        self.assertEqual(step_report["store_integrity_before"]["records"], 1)
        self.assertEqual(step_report["store_integrity_after"]["records"], 2)
        self.assertEqual(step_report["store_integrity_delta"]["records"], 1)
        self.assertEqual(step_report["store_integrity_delta"]["link_edges"], 4)
        self.assertEqual(step_report["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(step_report["state_delta"]["superseded_memory_ids"], ["mem_alice_old"])
        self.assertEqual(
            step_report["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_now": "ADMIT_CURRENT"},
        )
        self.assertIn(step_report_out.name, step_report["output_files"])
        self.assertIn(updated_state_out.name, step_report["output_files"])
        self.assertEqual(
            step_report["query_report"]["query_results"][0]["read_decision"]["decision"],
            "ADMIT_CURRENT",
        )
        self.assertEqual(
            step_report["query_report"]["query_results"][0]["reader_response"][
                "answer_evidence_ids"
            ],
            ["mem_alice_new"],
        )
        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_STEP_READY_NO_API")
        self.assertEqual(summary["step_id"], "cli-step-001")
        self.assertEqual(summary["records_loaded"], 1)
        self.assertEqual(summary["append_records_loaded"], 1)
        self.assertEqual(summary["state_delta"], step_report["state_delta"])
        self.assertEqual(
            summary["store_integrity_before"],
            step_report["store_integrity_before"],
        )
        self.assertEqual(
            summary["store_integrity_after"],
            step_report["store_integrity_after"],
        )
        self.assertEqual(
            summary["store_integrity_delta"],
            step_report["store_integrity_delta"],
        )
        self.assertEqual(summary["read_decision_counts"], {"ADMIT_CURRENT": 1})
        self.assertEqual(updated_state["store_integrity"]["records"], 2)
        current_rows = [
            row for row in updated_state["memory_store"] if row["current_status"] == "current"
        ]
        self.assertEqual([row["memory_id"] for row in current_rows], ["mem_alice_new"])
        self.assertFalse(store_written)
        self.assertFalse(packets_written)
        self.assertFalse(results_written)

    def test_cli_lifecycle_step_only_accepts_memory_events_file(self) -> None:
        query = {
            "query_id": "q_alice_now",
            "query": "Where is Alice's office now?",
            "entity": "Alice",
            "slot": "office_city",
            "needs_current": True,
        }
        event = {
            "event_id": "evt_alice_berlin",
            "text": "Alice reports that her office is now in Berlin.",
            "entity": "Alice",
            "slot": "office_city",
            "value": "Berlin",
            "observed_at": "2025-01-01T00:00:00+00:00",
            "source_type": "user_statement",
            "source_confidence": 0.93,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records_in = root / "records.jsonl"
            events_in = root / "events.jsonl"
            queries_in = root / "queries.jsonl"
            step_report_out = root / "step_report.json"
            state_out = root / "state.json"
            summary_out = root / "summary.json"

            records_in.write_text(
                json.dumps(
                    memory(
                        "mem_alice_old",
                        "Alice",
                        "office_city",
                        "Paris",
                        "2024-01-01T00:00:00+00:00",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            events_in.write_text(json.dumps(event) + "\n", encoding="utf-8")
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")

            argv = [
                "qvf-va",
                "--records",
                str(records_in),
                "--events-in",
                str(events_in),
                "--queries",
                str(queries_in),
                "--step-report-out",
                str(step_report_out),
                "--state-out",
                str(state_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            state = json.loads(state_out.read_text(encoding="utf-8"))

        self.assertEqual(step_report["decision"], "GO_QVF_LIFECYCLE_STEP_READY_NO_API")
        self.assertEqual(step_report["records_submitted_from_events"], 1)
        self.assertEqual(step_report["records_submitted_from_records"], 0)
        self.assertEqual(
            step_report["event_adapter_summary"]["output_memory_ids"],
            ["evt_alice_berlin"],
        )
        self.assertEqual(
            step_report["query_report"]["query_results"][0]["read_decision"]["decision"],
            "ADMIT_CURRENT",
        )
        self.assertIn(
            "Berlin",
            step_report["query_report"]["query_results"][0]["reader_response"]["final_answer"],
        )
        self.assertEqual(
            summary["event_adapter_summary"]["source_type_counts"],
            {"user_statement": 1},
        )
        current_rows = [
            row for row in state["memory_store"] if row["current_status"] == "current"
        ]
        self.assertEqual([row["memory_id"] for row in current_rows], ["evt_alice_berlin"])

    def test_cli_lifecycle_step_only_accepts_query_requests_file(self) -> None:
        event = {
            "event_id": "evt_alice_berlin",
            "text": "Alice reports that her office is now in Berlin.",
            "entity": "Alice",
            "slot": "office_city",
            "value": "Berlin",
            "observed_at": "2025-01-01T00:00:00+00:00",
            "source_type": "user_statement",
            "source_confidence": 0.93,
        }
        query_request = {
            "request_id": "req_alice_current_mail",
            "question": "Since Alice is still in Paris, where should I send mail?",
            "entity": "Alice",
            "slot": "office_city",
            "premise_value": "Paris",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records_in = root / "records.jsonl"
            events_in = root / "events.jsonl"
            query_requests_in = root / "query_requests.jsonl"
            step_report_out = root / "step_report.json"
            state_out = root / "state.json"
            summary_out = root / "summary.json"

            records_in.write_text(
                json.dumps(
                    memory(
                        "mem_alice_old",
                        "Alice",
                        "office_city",
                        "Paris",
                        "2024-01-01T00:00:00+00:00",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            events_in.write_text(json.dumps(event) + "\n", encoding="utf-8")
            query_requests_in.write_text(
                json.dumps(query_request) + "\n", encoding="utf-8"
            )

            argv = [
                "qvf-va",
                "--records",
                str(records_in),
                "--events-in",
                str(events_in),
                "--query-requests-in",
                str(query_requests_in),
                "--step-report-out",
                str(step_report_out),
                "--state-out",
                str(state_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        result = step_report["query_report"]["query_results"][0]
        self.assertEqual(step_report["query_count"], 1)
        self.assertEqual(step_report["queries_submitted_from_requests"], 1)
        self.assertEqual(step_report["queries_submitted_from_queries"], 0)
        self.assertEqual(
            step_report["query_request_adapter_summary"]["output_query_ids"],
            ["req_alice_current_mail"],
        )
        self.assertEqual(result["query_id"], "req_alice_current_mail")
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Berlin", result["reader_response"]["final_answer"])
        self.assertEqual(summary["query_count"], 1)
        self.assertEqual(
            summary["query_request_adapter_summary"]["normalized_query_count"],
            1,
        )

    def test_cli_preview_validity_admission_step_only_writes_summary_without_mutating_outputs(
        self,
    ) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ],
            max_stale=1,
        )
        append_record = memory(
            "mem_alice_new",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        query = {
            "query_id": "q_alice_now",
            "query": "Where is Alice's office now?",
            "entity": "Alice",
            "slot": "office_city",
            "needs_current": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            append_in = root / "append.jsonl"
            queries_in = root / "queries.jsonl"
            step_report_out = root / "step_report_should_not_exist.json"
            updated_state_out = root / "updated_state_should_not_exist.json"
            summary_out = root / "summary.json"
            store_out = root / "store_should_not_exist.jsonl"
            packets_out = root / "packets_should_not_exist.json"
            results_out = root / "results_should_not_exist.json"

            pipeline.save_state(state_in)
            append_in.write_text(json.dumps(append_record) + "\n", encoding="utf-8")
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--append-records",
                str(append_in),
                "--queries",
                str(queries_in),
                "--step-report-out",
                str(step_report_out),
                "--state-out",
                str(updated_state_out),
                "--summary-out",
                str(summary_out),
                "--step-id",
                "preview-cli-step-001",
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--query-results-out",
                str(results_out),
                "--preview-validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            saved_state = json.loads(state_in.read_text(encoding="utf-8"))
            step_report_written = step_report_out.exists()
            updated_state_written = updated_state_out.exists()
            store_written = store_out.exists()
            packets_written = packets_out.exists()
            results_written = results_out.exists()

        self.assertEqual(
            summary["decision"],
            "GO_QVF_LIFECYCLE_STEP_PREVIEW_READY_NO_API",
        )
        self.assertEqual(summary["execution_mode"], "pipeline_lifecycle_step_preview")
        self.assertTrue(summary["preview_does_not_mutate_source"])
        self.assertTrue(summary["source_store_unchanged"])
        self.assertEqual(summary["step_id"], "preview-cli-step-001")
        self.assertEqual(summary["input_mode"], "load_pipeline_state_lifecycle_step_preview")
        self.assertEqual(summary["records_loaded"], 1)
        self.assertEqual(summary["append_records_loaded"], 1)
        self.assertEqual(summary["records_submitted"], 1)
        self.assertEqual(summary["query_count"], 1)
        self.assertEqual(summary["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(summary["state_delta"]["superseded_memory_ids"], ["mem_alice_old"])
        self.assertEqual(
            summary["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_now": "ADMIT_CURRENT"},
        )
        self.assertEqual(summary["store_integrity_before"]["records"], 1)
        self.assertEqual(summary["store_integrity_after"]["records"], 2)
        self.assertEqual(summary["store_integrity_delta"]["records"], 1)
        self.assertEqual(
            summary["changed_memory_ids"],
            ["mem_alice_new", "mem_alice_old"],
        )
        self.assertEqual(summary["store_diff"]["added_memory_ids"], ["mem_alice_new"])
        self.assertEqual(
            summary["store_diff"]["current_index_changes"][0]["after_memory_id"],
            "mem_alice_new",
        )
        self.assertEqual(summary["read_decision_counts"], {"ADMIT_CURRENT": 1})
        self.assertEqual(saved_state["store_integrity"]["records"], 1)
        self.assertIn(summary_out.name, summary["output_files"])
        self.assertFalse(step_report_written)
        self.assertFalse(updated_state_written)
        self.assertFalse(store_written)
        self.assertFalse(packets_written)
        self.assertFalse(results_written)

    def test_cli_lifecycle_step_only_can_load_weak_gate_results_file(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        append_record = memory(
            "mem_alice_new",
            "Alice",
            "office_city",
            "Berlin",
            "2025-01-01T00:00:00+00:00",
        )
        query = {
            "query_id": "q_alice_stale_premise",
            "query": "Since Alice is still in Paris, where should I send mail?",
            "entity": "Alice",
            "slot": "office_city",
            "needs_current": True,
            "embedded_premise_value": "Paris",
        }
        weak_gate_output = {
            "query_id": "q_alice_stale_premise",
            "decision": "REJECT_STALE_PREMISE",
            "support": "",
            "blocker": "mem_alice_new",
            "final_answer": "Alice is no longer supported as being in Paris.",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            append_in = root / "append.jsonl"
            queries_in = root / "queries.jsonl"
            weak_gate_results_in = root / "weak_gate_results.jsonl"
            step_report_out = root / "step_report.json"
            summary_out = root / "summary.json"

            pipeline.save_state(state_in)
            append_in.write_text(json.dumps(append_record) + "\n", encoding="utf-8")
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")
            weak_gate_results_in.write_text(
                json.dumps(weak_gate_output) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--append-records",
                str(append_in),
                "--queries",
                str(queries_in),
                "--weak-gate-results-in",
                str(weak_gate_results_in),
                "--step-report-out",
                str(step_report_out),
                "--summary-out",
                str(summary_out),
                "--step-id",
                "weak-gate-file-step-001",
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        read_decision = step_report["query_report"]["read_decisions"][0]
        self.assertEqual(step_report["step_id"], "weak-gate-file-step-001")
        self.assertEqual(step_report["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(read_decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(read_decision["decision_source"], "weak_gate_output")
        self.assertEqual(
            step_report["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_stale_premise": "REJECT_STALE_PREMISE"},
        )
        self.assertEqual(summary["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(
            summary["weak_gate_adapter_summary"]["adapted_from_weak_gate_output_count"],
            1,
        )

    def test_cli_lifecycle_step_request_runs_from_single_json_object(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        request = {
            "step_id": "request-step-001",
            "records": [
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ],
            "queries": [
                {
                    "query_id": "q_alice_now",
                    "query": "Where is Alice's office now?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                }
            ],
            "include_state": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            request_in = root / "step_request.json"
            step_report_out = root / "step_report.json"
            summary_out = root / "summary.json"

            pipeline.save_state(state_in)
            request_in.write_text(
                json.dumps(request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--step-request-in",
                str(request_in),
                "--step-report-out",
                str(step_report_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(step_report["step_id"], "request-step-001")
        self.assertEqual(step_report["input_mode"], "load_pipeline_state_lifecycle_step_request")
        self.assertEqual(step_report["append_records_loaded"], 1)
        self.assertEqual(step_report["state_delta"]["current_memory_ids"], ["mem_alice_new"])
        self.assertEqual(step_report["state"]["store_integrity"]["records"], 2)
        current_rows = [
            row for row in step_report["state"]["memory_store"] if row["current_status"] == "current"
        ]
        self.assertEqual([row["memory_id"] for row in current_rows], ["mem_alice_new"])
        self.assertEqual(summary["step_id"], "request-step-001")
        self.assertEqual(summary["input_mode"], "load_pipeline_state_lifecycle_step_request")
        self.assertEqual(summary["state_delta"], step_report["state_delta"])

    def test_cli_lifecycle_step_request_can_load_external_weak_gate_results(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        request = {
            "step_id": "request-weak-file-step-001",
            "records": [
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ],
            "queries": [
                {
                    "query_id": "q_alice_stale_premise",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                }
            ],
        }
        weak_gate_output = {
            "query_id": "q_alice_stale_premise",
            "decision": "REJECT_STALE_PREMISE",
            "support": "",
            "blocker": "mem_alice_new",
            "final_answer": "Alice is no longer supported as being in Paris.",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            request_in = root / "step_request.json"
            weak_gate_results_in = root / "weak_gate_results.jsonl"
            step_report_out = root / "step_report.json"
            summary_out = root / "summary.json"

            pipeline.save_state(state_in)
            request_in.write_text(
                json.dumps(request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            weak_gate_results_in.write_text(
                json.dumps(weak_gate_output) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--step-request-in",
                str(request_in),
                "--weak-gate-results-in",
                str(weak_gate_results_in),
                "--step-report-out",
                str(step_report_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        read_decision = step_report["query_report"]["read_decisions"][0]
        self.assertEqual(step_report["step_id"], "request-weak-file-step-001")
        self.assertEqual(step_report["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(read_decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(read_decision["decision_source"], "weak_gate_output")
        self.assertEqual(summary["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(
            summary["weak_gate_adapter_summary"]["adapted_from_weak_gate_output_count"],
            1,
        )

    def test_cli_lifecycle_step_request_rejects_duplicate_weak_gate_sources(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        weak_gate_output = {
            "query_id": "q_alice_stale_premise",
            "decision": "REJECT_STALE_PREMISE",
            "support": "",
            "blocker": "mem_alice_new",
        }
        request = {
            "queries": [],
            "weak_gate_outputs": [weak_gate_output],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            request_in = root / "step_request.json"
            weak_gate_results_in = root / "weak_gate_results.jsonl"
            step_report_out = root / "step_report.json"

            pipeline.save_state(state_in)
            request_in.write_text(
                json.dumps(request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            weak_gate_results_in.write_text(
                json.dumps(weak_gate_output) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--step-request-in",
                str(request_in),
                "--weak-gate-results-in",
                str(weak_gate_results_in),
                "--step-report-out",
                str(step_report_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with self.assertRaisesRegex(
                    ValueError,
                    "weak_gate_outputs and --weak-gate-results-in are mutually exclusive",
                ):
                    main()

    def test_cli_lifecycle_step_request_can_use_weak_gate_outputs(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_old",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        request = {
            "step_id": "weak-gate-cli-step-001",
            "records": [
                memory(
                    "mem_alice_new",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                )
            ],
            "queries": [
                {
                    "query_id": "q_alice_stale_premise",
                    "query": "Since Alice is still in Paris, where should I send mail?",
                    "entity": "Alice",
                    "slot": "office_city",
                    "needs_current": True,
                    "embedded_premise_value": "Paris",
                }
            ],
            "weak_gate_outputs": [
                {
                    "query_id": "q_alice_stale_premise",
                    "decision": "REJECT_STALE_PREMISE",
                    "support": "",
                    "blocker": "mem_alice_new",
                    "final_answer": "Alice is no longer supported as being in Paris.",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            request_in = root / "step_request.json"
            step_report_out = root / "step_report.json"
            summary_out = root / "summary.json"

            pipeline.save_state(state_in)
            request_in.write_text(
                json.dumps(request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--step-request-in",
                str(request_in),
                "--step-report-out",
                str(step_report_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-step-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            step_report = json.loads(step_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        read_decision = step_report["query_report"]["read_decisions"][0]
        self.assertEqual(step_report["step_id"], "weak-gate-cli-step-001")
        self.assertEqual(step_report["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(read_decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(read_decision["decision_source"], "weak_gate_output")
        self.assertEqual(
            step_report["state_delta"]["read_decisions_by_query_id"],
            {"q_alice_stale_premise": "REJECT_STALE_PREMISE"},
        )
        self.assertEqual(summary["query_mode"], "weak_gate_output_adapter")
        self.assertEqual(summary["read_decision_counts"], {"REJECT_STALE_PREMISE": 1})
        self.assertEqual(
            summary["weak_gate_adapter_summary"]["adapted_from_weak_gate_output_count"],
            1,
        )

    def test_cli_lifecycle_steps_request_runs_transactional_sequence(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        step_requests = [
            {
                "step_id": "cli-batch-old",
                "records": [
                    memory(
                        "mem_alice_old",
                        "Alice",
                        "office_city",
                        "Paris",
                        "2024-01-01T00:00:00+00:00",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_alice_old",
                        "query": "Where is Alice's office now?",
                        "entity": "Alice",
                        "slot": "office_city",
                        "needs_current": True,
                    }
                ],
            },
            {
                "step_id": "cli-batch-new",
                "records": [
                    memory(
                        "mem_alice_new",
                        "Alice",
                        "office_city",
                        "Berlin",
                        "2025-01-01T00:00:00+00:00",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_alice_new",
                        "query": "Since Alice is still in Paris, where should I send mail?",
                        "entity": "Alice",
                        "slot": "office_city",
                        "needs_current": True,
                        "embedded_premise_value": "Paris",
                    }
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            steps_in = root / "steps.json"
            batch_report_out = root / "batch_report.json"
            updated_state_out = root / "updated_state.json"
            summary_out = root / "summary.json"

            pipeline.save_state(state_in)
            steps_in.write_text(
                json.dumps(step_requests, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--steps-request-in",
                str(steps_in),
                "--step-report-out",
                str(batch_report_out),
                "--state-out",
                str(updated_state_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-steps-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            batch_report = json.loads(batch_report_out.read_text(encoding="utf-8"))
            updated_state = json.loads(updated_state_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(
            batch_report["decision"],
            "GO_QVF_LIFECYCLE_MULTI_STEP_READY_NO_API",
        )
        self.assertEqual(batch_report["execution_mode"], "pipeline_lifecycle_multi_step")
        self.assertEqual(
            batch_report["input_mode"],
            "load_pipeline_state_lifecycle_steps_request",
        )
        self.assertEqual(batch_report["summary"]["step_count"], 2)
        self.assertEqual(batch_report["summary"]["step_ids"], ["cli-batch-old", "cli-batch-new"])
        self.assertEqual(batch_report["steps"][0]["batch_step_index"], 0)
        self.assertEqual(batch_report["steps"][1]["batch_step_index"], 1)
        self.assertEqual(
            batch_report["steps"][1]["query_report"]["query_results"][0]["read_decision"]["decision"],
            "REJECT_STALE_PREMISE",
        )
        self.assertEqual(updated_state["store_integrity"]["records"], 2)
        current_rows = [
            row for row in updated_state["memory_store"] if row["current_status"] == "current"
        ]
        self.assertEqual([row["memory_id"] for row in current_rows], ["mem_alice_new"])
        self.assertEqual(
            summary["decision"],
            "GO_QVF_LIFECYCLE_MULTI_STEP_READY_NO_API",
        )
        self.assertEqual(summary["step_count"], 2)
        self.assertEqual(summary["records_submitted"], 2)
        self.assertEqual(summary["admission_event_count"], 3)
        self.assertEqual(summary["query_count"], 2)
        self.assertEqual(summary["query_mode_counts"], {"deterministic_router": 2})
        self.assertEqual(summary["store_integrity"], updated_state["store_integrity"])
        self.assertEqual(summary["api_calls_made"], 0)
        self.assertIn(batch_report_out.name, summary["output_files"])
        self.assertIn(updated_state_out.name, summary["output_files"])

    def test_cli_lifecycle_steps_request_rolls_back_on_later_bad_step(self) -> None:
        pipeline = QVFMemoryPipeline.from_records([])
        step_requests = [
            {
                "step_id": "valid-first-step",
                "records": [
                    memory(
                        "mem_alice_valid",
                        "Alice",
                        "office_city",
                        "Paris",
                        "2024-01-01T00:00:00+00:00",
                    )
                ],
            },
            {
                "step_id": "bad-second-step",
                "records": [{"memory_id": "mem_bad", "entity": "Alice"}],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_in = root / "state_in.json"
            steps_in = root / "steps.json"
            batch_report_out = root / "batch_report.json"
            updated_state_out = root / "updated_state.json"
            summary_out = root / "summary.json"

            pipeline.save_state(state_in)
            steps_in.write_text(
                json.dumps(step_requests, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            argv = [
                "qvf-va",
                "--load-state",
                str(state_in),
                "--steps-request-in",
                str(steps_in),
                "--step-report-out",
                str(batch_report_out),
                "--state-out",
                str(updated_state_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-steps-only",
            ]
            with patch("sys.argv", argv):
                with self.assertRaisesRegex(ValueError, "memory.slot"):
                    main()

            input_state = json.loads(state_in.read_text(encoding="utf-8"))
            batch_written = batch_report_out.exists()
            state_written = updated_state_out.exists()
            summary_written = summary_out.exists()

        self.assertEqual(input_state["store_integrity"]["records"], 0)
        self.assertFalse(batch_written)
        self.assertFalse(state_written)
        self.assertFalse(summary_written)

    def test_cli_lifecycle_steps_request_accepts_jsonl_input(self) -> None:
        step_requests = [
            {
                "step_id": "jsonl-step-old",
                "records": [
                    memory(
                        "mem_dana_old",
                        "Dana",
                        "office_city",
                        "Rome",
                        "2024-01-01T00:00:00+00:00",
                    )
                ],
            },
            {
                "step_id": "jsonl-step-new",
                "records": [
                    memory(
                        "mem_dana_new",
                        "Dana",
                        "office_city",
                        "Madrid",
                        "2025-01-01T00:00:00+00:00",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_dana_now",
                        "query": "Where is Dana's office now?",
                        "entity": "Dana",
                        "slot": "office_city",
                        "needs_current": True,
                    }
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            steps_in = root / "steps.jsonl"
            batch_report_out = root / "batch_report.json"
            summary_out = root / "summary.json"
            steps_in.write_text(
                "\n".join(json.dumps(step, ensure_ascii=False) for step in step_requests)
                + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(root / "empty_records.jsonl"),
                "--steps-request-in",
                str(steps_in),
                "--step-report-out",
                str(batch_report_out),
                "--summary-out",
                str(summary_out),
                "--validity-admission-steps-only",
            ]
            (root / "empty_records.jsonl").write_text("", encoding="utf-8")
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            batch_report = json.loads(batch_report_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(batch_report["summary"]["step_ids"], ["jsonl-step-old", "jsonl-step-new"])
        self.assertEqual(batch_report["summary"]["records_submitted"], 2)
        self.assertEqual(
            batch_report["steps"][1]["query_report"]["query_results"][0]["read_decision"]["decision"],
            "ADMIT_CURRENT",
        )
        self.assertEqual(summary["step_count"], 2)
        self.assertEqual(summary["query_count"], 1)

    def test_cli_load_store_appends_records_before_querying(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        append_record = memory(
            "mem_ben_latest",
            "Ben",
            "home_city",
            "Venice",
            "2026-01-01T00:00:00+00:00",
        )
        query = {
            "query_id": "q_ben",
            "query": "Where does Ben live now?",
            "entity": "Ben",
            "slot": "home_city",
            "needs_current": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store_in.jsonl"
            append_in = root / "append.jsonl"
            queries_in = root / "queries.jsonl"
            store_out = root / "store_out.jsonl"
            packets_out = root / "packets.json"
            decisions_out = root / "decisions.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            admission_log_out = root / "admission_log.csv"
            summary_out = root / "summary.json"

            pipeline.save_memory_store(store_in)
            append_in.write_text(json.dumps(append_record) + "\n", encoding="utf-8")
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--append-records",
                str(append_in),
                "--queries",
                str(queries_in),
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--admission-log-out",
                str(admission_log_out),
                "--summary-out",
                str(summary_out),
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            results = json.loads(results_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            exported = [
                json.loads(line)
                for line in store_out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(results[0]["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            results[0]["reader_response"]["answer_evidence_ids"],
            ["mem_ben_latest"],
        )
        self.assertIn("Venice", results[0]["reader_response"]["final_answer"])
        self.assertEqual(summary["input_mode"], "load_exported_store_plus_append_records")
        self.assertEqual(summary["records_loaded"], 2)
        self.assertEqual(summary["append_records_loaded"], 1)
        self.assertEqual(summary["store_records_loaded"], 3)
        self.assertEqual(
            summary["store_integrity"],
            {
                "records": 3,
                "current_index_entries": 1,
                "current_records": 1,
                "link_edges": 8,
            },
        )
        self.assertEqual(
            {row["memory_id"]: row["current_status"] for row in exported}["mem_ben_latest"],
            "current",
        )

    def test_cli_full_run_accepts_query_requests_without_default_queries(self) -> None:
        query_request = {
            "request_id": "req_ben_courier",
            "question": "Since Ben still lives in Rome, where should the courier go?",
            "entity": "Ben",
            "slot": "home_city",
            "premise_value": "Rome",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records_in = root / "records.jsonl"
            query_requests_in = root / "query_requests.jsonl"
            store_out = root / "store_out.jsonl"
            packets_out = root / "packets.json"
            decisions_out = root / "decisions.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            admission_log_out = root / "admission_log.csv"
            summary_out = root / "summary.json"

            records_in.write_text(
                "\n".join(
                    [
                        json.dumps(
                            memory(
                                "mem_ben_old",
                                "Ben",
                                "home_city",
                                "Rome",
                                "2024-01-01T00:00:00+00:00",
                            )
                        ),
                        json.dumps(
                            memory(
                                "mem_ben_new",
                                "Ben",
                                "home_city",
                                "Milan",
                                "2025-01-01T00:00:00+00:00",
                            )
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            query_requests_in.write_text(
                json.dumps(query_request) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(records_in),
                "--query-requests-in",
                str(query_requests_in),
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--admission-log-out",
                str(admission_log_out),
                "--summary-out",
                str(summary_out),
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            results = json.loads(results_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            packets = json.loads(packets_out.read_text(encoding="utf-8"))

        self.assertEqual(summary["queries_loaded"], 1)
        self.assertEqual(
            summary["query_request_adapter_summary"]["output_query_ids"],
            ["req_ben_courier"],
        )
        self.assertEqual(packets[0]["query"]["query_id"], "req_ben_courier")
        self.assertEqual(results[0]["query_id"], "req_ben_courier")
        self.assertEqual(results[0]["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Milan", results[0]["reader_response"]["final_answer"])
        self.assertEqual(summary["api_calls_made"], 0)

    def test_cli_service_request_runs_without_demo_records_or_queries(self) -> None:
        service_request = {
            "request_id": "svc_ben_courier",
            "config": {"max_stale": 1, "include_weak_gate_card": True},
            "records": [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ],
            "query_requests": [
                {
                    "request_id": "req_ben_courier",
                    "question": "Since Ben still lives in Rome, where should the courier go?",
                    "entity": "Ben",
                    "slot": "home_city",
                    "premise_value": "Rome",
                }
            ],
            "include_state": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            service_request_in = root / "service_request.json"
            service_response_out = root / "service_response.json"
            summary_out = root / "summary.json"

            service_request_in.write_text(
                json.dumps(service_request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--service-request-in",
                str(service_request_in),
                "--service-response-out",
                str(service_response_out),
                "--summary-out",
                str(summary_out),
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            response = json.loads(service_response_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        result = response["step_report"]["query_report"]["query_results"][0]
        current_rows = [
            row for row in response["state"]["memory_store"] if row["current_status"] == "current"
        ]
        self.assertEqual(response["decision"], "GO_QVF_SERVICE_REQUEST_READY_NO_API")
        self.assertEqual(response["input_mode"], "service_empty_store")
        self.assertEqual(response["output_files"], [service_response_out.name, summary_out.name])
        self.assertEqual(result["query_id"], "req_ben_courier")
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertIn("Milan", result["reader_response"]["final_answer"])
        self.assertEqual([row["memory_id"] for row in current_rows], ["mem_ben_new"])
        self.assertEqual(summary["decision"], response["summary"]["decision"])
        self.assertEqual(summary["query_count"], 1)
        self.assertEqual(
            summary["query_request_adapter_summary"]["output_query_ids"],
            ["req_ben_courier"],
        )
        self.assertEqual(summary["output_files"], [service_response_out.name, summary_out.name])
        self.assertEqual(summary["api_calls_made"], 0)

    def test_cli_preview_admission_only_does_not_write_store_outputs(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                )
            ]
        )
        append_record = memory(
            "mem_ben_new",
            "Ben",
            "home_city",
            "Milan",
            "2025-01-01T00:00:00+00:00",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store_in.jsonl"
            append_in = root / "append.jsonl"
            missing_queries = root / "queries_should_not_be_read.jsonl"
            store_out = root / "store_should_not_exist.jsonl"
            packets_out = root / "packets_should_not_exist.json"
            results_out = root / "results_should_not_exist.json"
            admission_log_out = root / "admission_log_should_not_exist.csv"
            summary_out = root / "preview_summary.json"

            pipeline.save_memory_store(store_in)
            append_in.write_text(json.dumps(append_record) + "\n", encoding="utf-8")

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--append-records",
                str(append_in),
                "--queries",
                str(missing_queries),
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--query-results-out",
                str(results_out),
                "--admission-log-out",
                str(admission_log_out),
                "--summary-out",
                str(summary_out),
                "--preview-admission-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            store_written = store_out.exists()
            packets_written = packets_out.exists()
            results_written = results_out.exists()
            admission_log_written = admission_log_out.exists()

        self.assertEqual(
            summary["decision"],
            "GO_QVF_LIFECYCLE_ADMISSION_PREVIEW_READY_NO_API",
        )
        self.assertEqual(summary["execution_mode"], "pipeline_admission_preview")
        self.assertEqual(summary["input_mode"], "load_exported_store_preview_admission_only")
        self.assertEqual(summary["records_loaded"], 1)
        self.assertEqual(summary["append_records_loaded"], 1)
        self.assertEqual(summary["state_delta"]["current_memory_ids"], ["mem_ben_new"])
        self.assertEqual(summary["state_delta"]["superseded_memory_ids"], ["mem_ben_old"])
        self.assertEqual(summary["store_integrity_before"]["records"], 1)
        self.assertEqual(summary["store_integrity_after"]["records"], 2)
        self.assertEqual(summary["current_index_before"][0]["memory_id"], "mem_ben_old")
        self.assertEqual(summary["current_index_after"][0]["memory_id"], "mem_ben_new")
        self.assertEqual(
            summary["changed_memory_ids"],
            ["mem_ben_new", "mem_ben_old"],
        )
        self.assertEqual(summary["store_diff"]["added_memory_ids"], ["mem_ben_new"])
        self.assertEqual(summary["store_diff"]["updated_memory_ids"], ["mem_ben_old"])
        self.assertIn(summary_out.name, summary["output_files"])
        self.assertFalse(store_written)
        self.assertFalse(packets_written)
        self.assertFalse(results_written)
        self.assertFalse(admission_log_written)

    def test_cli_load_store_without_append_writes_empty_admission_log(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        query = {
            "query_id": "q_ben",
            "query": "Where does Ben live now?",
            "entity": "Ben",
            "slot": "home_city",
            "needs_current": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store_in.jsonl"
            queries_in = root / "queries.jsonl"
            store_out = root / "store_out.jsonl"
            packets_out = root / "packets.json"
            decisions_out = root / "decisions.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            admission_log_out = root / "admission_log.csv"
            summary_out = root / "summary.json"

            pipeline.save_memory_store(store_in)
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(queries_in),
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--admission-log-out",
                str(admission_log_out),
                "--summary-out",
                str(summary_out),
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            admission_log_lines = admission_log_out.read_text(encoding="utf-8").splitlines()

        self.assertEqual(summary["input_mode"], "load_exported_store")
        self.assertEqual(summary["append_records_loaded"], 0)
        self.assertEqual(
            summary["store_integrity"],
            {
                "records": 2,
                "current_index_entries": 1,
                "current_records": 1,
                "link_edges": 4,
            },
        )
        self.assertEqual(len(admission_log_lines), 1)
        self.assertEqual(
            admission_log_lines[0],
            "memory_id,entity,slot,value,observed_at,source_confidence,"
            "admission_status,current_status,evidence_role,reason",
        )

    def test_cli_validate_store_only_does_not_require_queries(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store_in.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            summary_out = root / "summary.json"
            packets_out = root / "packets.json"

            pipeline.save_memory_store(store_in)

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(missing_queries),
                "--packets-out",
                str(packets_out),
                "--summary-out",
                str(summary_out),
                "--validate-store-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            packets_written = packets_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_STORE_INTEGRITY_READY_NO_API")
        self.assertEqual(summary["validation_mode"], "store_integrity_only")
        self.assertNotIn("queries_loaded", summary)
        self.assertEqual(summary["store_integrity"]["records"], 2)
        self.assertEqual(summary["store_integrity"]["link_edges"], 4)
        self.assertEqual(summary["output_files"], ["summary.json"])
        self.assertFalse(packets_written)

    def test_cli_admit_only_writes_store_without_queries(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records_in = root / "records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            store_out = root / "store_out.jsonl"
            packets_out = root / "packets.json"
            admission_log_out = root / "admission_log.csv"
            summary_out = root / "summary.json"

            records_in.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(records_in),
                "--queries",
                str(missing_queries),
                "--store-out",
                str(store_out),
                "--packets-out",
                str(packets_out),
                "--admission-log-out",
                str(admission_log_out),
                "--summary-out",
                str(summary_out),
                "--admit-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            exported = [
                json.loads(line)
                for line in store_out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            admission_log_lines = admission_log_out.read_text(encoding="utf-8").splitlines()
            packets_written = packets_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_WRITE_TIME_ADMISSION_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "write_time_admission_only")
        self.assertNotIn("queries_loaded", summary)
        self.assertEqual(summary["input_mode"], "replay_raw_records_admit_only")
        self.assertEqual(summary["records_loaded"], 2)
        self.assertEqual(summary["store_records_loaded"], 2)
        self.assertEqual(summary["store_integrity"]["link_edges"], 4)
        self.assertEqual(summary["admission_status_counts"]["admit_current"], 1)
        self.assertEqual(summary["admission_status_counts"]["admit_as_stale_contrast"], 1)
        self.assertEqual(
            {row["memory_id"]: row["current_status"] for row in exported},
            {
                "mem_ben_old": "superseded",
                "mem_ben_new": "current",
            },
        )
        self.assertEqual(len(admission_log_lines), 4)
        self.assertFalse(packets_written)

    def test_cli_packets_only_writes_packets_without_reader_outputs(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_old",
                    "Ben",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_new",
                    "Ben",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        query = {
            "query_id": "q_ben",
            "query": "Where does Ben live now?",
            "entity": "Ben",
            "slot": "home_city",
            "needs_current": True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store_in = root / "store_in.jsonl"
            queries_in = root / "queries.jsonl"
            lock_in = root / "method_lock.json"
            packets_out = root / "packets.json"
            decisions_out = root / "decisions.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            summary_out = root / "summary.json"

            pipeline.save_memory_store(store_in)
            queries_in.write_text(json.dumps(query) + "\n", encoding="utf-8")
            lock_in.write_text(
                json.dumps(
                    build_method_lock_summary(
                        ["method_lock.json"],
                        low_confidence_threshold=0.5,
                        max_current=1,
                        max_supporting=2,
                        max_stale=2,
                        max_excluded=2,
                        max_packet_chars=None,
                        include_validity_edges=True,
                        include_weak_gate_card=True,
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--load-store",
                str(store_in),
                "--queries",
                str(queries_in),
                "--method-lock-in",
                str(lock_in),
                "--packets-out",
                str(packets_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--summary-out",
                str(summary_out),
                "--enforce-method-lock",
                "--packets-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            packets = json.loads(packets_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            decisions_written = decisions_out.exists()
            responses_written = responses_out.exists()
            results_written = results_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_PACKET_BUILD_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "retrieval_time_packet_build_only")
        self.assertEqual(summary["input_mode"], "load_exported_store_packets_only")
        self.assertEqual(summary["queries_loaded"], 1)
        self.assertEqual(summary["packet_count"], 1)
        self.assertEqual(summary["packet_budget_satisfied_count"], 1)
        self.assertEqual(summary["packet_budget_unsatisfied_count"], 0)
        self.assertEqual(summary["weak_gate_card_count"], 1)
        self.assertEqual(summary["validity_edge_count"], 4)
        self.assertEqual(packets[0]["query"]["query_id"], "q_ben")
        self.assertEqual(
            packets[0]["compact_validity_packet"]["current_evidence"][0]["value"],
            "Milan",
        )
        self.assertFalse(decisions_written)
        self.assertFalse(responses_written)
        self.assertFalse(results_written)

    def test_build_weak_gate_tasks_exports_compact_gate_inputs(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)

        tasks = build_weak_gate_tasks(packets)

        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual(task["task_id"], "weak_gate::q_ben")
        self.assertEqual(task["query_id"], "q_ben")
        self.assertEqual(task["adapter"], "weak_conservative_gate_v0.1")
        self.assertEqual(task["expected_gate_decision"], "REJECT_STALE_PREMISE")
        self.assertIn("decision_rules", task["input"])
        self.assertEqual(
            task["input"]["current_candidate_evidence"][0]["memory_id"],
            "mem_ben_new",
        )
        self.assertEqual(
            task["input"]["stale_or_blocked_evidence"][0]["memory_id"],
            "mem_ben_old",
        )
        self.assertEqual(
            task["output_schema"]["decision"],
            "ADMIT_CURRENT | REJECT_STALE_PREMISE | UNKNOWN_CURRENT",
        )
        self.assertIn("token_budget_proxy", task["packet_diagnostics"])

    def test_build_weak_gate_tasks_skips_queries_without_embedded_premise(self) -> None:
        records = [
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)

        tasks = build_weak_gate_tasks(packets)

        self.assertEqual(tasks, [])

    def test_build_weak_gate_pack_summary_reports_task_coverage(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben_stale",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            },
            {
                "query_id": "q_ben_plain",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            },
        ]
        _, packets = build_lifecycle_packets(records, queries)
        tasks = build_weak_gate_tasks(packets)

        summary = build_weak_gate_pack_summary(packets, tasks, ["weak_gate_tasks.json"])

        self.assertEqual(summary["packet_count"], 2)
        self.assertEqual(summary["weak_gate_task_count"], 1)
        self.assertEqual(summary["estimated_model_call_count"], 1)
        self.assertEqual(summary["task_coverage"]["packet_query_count"], 2)
        self.assertEqual(summary["task_coverage"]["covered_packet_count"], 1)
        self.assertEqual(summary["task_coverage"]["skipped_packet_count"], 1)
        self.assertEqual(summary["task_coverage"]["coverage_ratio"], 0.5)
        self.assertEqual(summary["task_coverage"]["covered_query_ids"], ["q_ben_stale"])
        self.assertEqual(summary["task_coverage"]["skipped_query_ids"], ["q_ben_plain"])
        self.assertEqual(summary["task_size_proxy"]["task_count"], 1)
        self.assertGreater(summary["task_size_proxy"]["input_json_chars_total"], 0)
        self.assertGreater(
            summary["task_size_proxy"]["task_json_chars_total"],
            summary["task_size_proxy"]["input_json_chars_total"],
        )
        self.assertEqual(
            summary["task_size_proxy"]["max_task_json_chars"],
            summary["task_size_proxy"]["largest_tasks"][0]["task_json_chars"],
        )
        self.assertEqual(
            summary["task_size_proxy"]["largest_tasks"][0]["task_id"],
            "weak_gate::q_ben_stale",
        )

    def test_cli_weak_gate_pack_only_exports_tasks_without_reader_outputs(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "missing_records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            packets_in = root / "packets_in.json"
            tasks_out = root / "weak_gate_tasks.json"
            decisions_out = root / "decisions_should_not_exist.json"
            responses_out = root / "responses_should_not_exist.json"
            results_out = root / "results_should_not_exist.json"
            summary_out = root / "summary.json"

            packets_in.write_text(
                json.dumps(packets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--packets-in",
                str(packets_in),
                "--weak-gate-tasks-out",
                str(tasks_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--summary-out",
                str(summary_out),
                "--weak-gate-pack-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            tasks = json.loads(tasks_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            decisions_written = decisions_out.exists()
            responses_written = responses_out.exists()
            results_written = results_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_WEAK_GATE_PACK_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "weak_gate_pack_only")
        self.assertEqual(summary["packet_count"], 1)
        self.assertEqual(summary["weak_gate_task_count"], 1)
        self.assertEqual(summary["estimated_model_call_count"], 1)
        self.assertEqual(summary["task_coverage"]["coverage_ratio"], 1.0)
        self.assertEqual(summary["task_coverage"]["skipped_query_ids"], [])
        self.assertEqual(summary["task_size_proxy"]["task_count"], 1)
        self.assertGreater(summary["task_size_proxy"]["task_json_chars_total"], 0)
        self.assertEqual(
            summary["task_size_proxy"]["largest_tasks"][0]["query_id"],
            "q_ben",
        )
        self.assertEqual(summary["expected_gate_decision_counts"]["REJECT_STALE_PREMISE"], 1)
        self.assertEqual(tasks[0]["expected_gate_decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(tasks[0]["input"]["query"]["embedded_premise_value"], "Rome")
        self.assertFalse(decisions_written)
        self.assertFalse(responses_written)
        self.assertFalse(results_written)

    def test_score_weak_gate_outputs_counts_parseable_correct_and_missing(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)
        tasks = build_weak_gate_tasks(packets)
        tasks.append(
            {
                **deepcopy(tasks[0]),
                "task_id": "weak_gate::q_missing",
                "query_id": "q_missing",
            }
        )
        outputs = [
            {
                "task_id": "weak_gate::q_ben",
                "decision": "reject stale premise",
                "support": "",
                "blocker": "mem_ben_old",
                "final_answer": "Ben no longer has Rome as current evidence.",
            }
        ]

        rows, summary = score_weak_gate_outputs(tasks, outputs)

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_WEAK_GATE_ANALYSIS_READY_NO_API")
        self.assertEqual(summary["task_count"], 2)
        self.assertEqual(summary["output_count"], 1)
        self.assertEqual(summary["matched_output_count"], 1)
        self.assertEqual(summary["missing_output_count"], 1)
        self.assertEqual(summary["parseable_decision_count"], 1)
        self.assertEqual(summary["decision_correct_count"], 1)
        self.assertEqual(summary["decision_accuracy_on_matched"], 1.0)
        self.assertEqual(summary["decision_accuracy_on_parseable"], 1.0)
        self.assertEqual(rows[0]["predicted_decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(rows[0]["decision_correct"], "1")
        self.assertEqual(rows[1]["error"], "missing_output")

    def test_cli_analyze_weak_gate_results_only_writes_csv_summary(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)
        tasks = build_weak_gate_tasks(packets)
        outputs = [
            {
                "query_id": "q_ben",
                "decision": "REJECT_STALE_PREMISE",
                "support": "",
                "blocker": "mem_ben_old",
                "final_answer": "Use Milan as the current location.",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "missing_records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            tasks_in = root / "weak_gate_tasks.json"
            results_in = root / "weak_gate_results.jsonl"
            analysis_out = root / "weak_gate_analysis.csv"
            summary_out = root / "summary.json"

            tasks_in.write_text(
                json.dumps(tasks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results_in.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in outputs) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--weak-gate-tasks-in",
                str(tasks_in),
                "--weak-gate-results-in",
                str(results_in),
                "--weak-gate-analysis-out",
                str(analysis_out),
                "--summary-out",
                str(summary_out),
                "--analyze-weak-gate-results-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            with analysis_out.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_WEAK_GATE_ANALYSIS_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "weak_gate_analysis_only")
        self.assertEqual(summary["task_count"], 1)
        self.assertEqual(summary["matched_output_count"], 1)
        self.assertEqual(summary["parseable_decision_count"], 1)
        self.assertEqual(summary["decision_correct_count"], 1)
        self.assertEqual(rows[0]["query_id"], "q_ben")
        self.assertEqual(rows[0]["predicted_decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(rows[0]["decision_correct"], "1")

    def test_adapt_weak_gate_outputs_to_read_decisions_can_drive_renderer(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)
        tasks = build_weak_gate_tasks(packets)
        outputs = [
            {
                "task_id": "weak_gate::q_ben",
                "decision": "reject stale premise",
                "support": "",
                "blocker": "mem_ben_new",
                "final_answer": "Ben's current city is not Rome.",
            }
        ]

        decisions, summary = build_read_decisions_from_weak_gate_outputs(
            packets,
            tasks,
            outputs,
        )
        responses = build_reader_responses(packets, decisions)

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_WEAK_GATE_DECISION_ADAPTER_READY_NO_API")
        self.assertEqual(summary["adapted_from_weak_gate_output_count"], 1)
        self.assertEqual(summary["decision_source_counts"]["weak_gate_output"], 1)
        self.assertEqual(decisions[0]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decisions[0]["route"], "weak_conservative_gate")
        self.assertEqual(decisions[0]["blocking_evidence_ids"], ["mem_ben_new"])
        self.assertEqual(decisions[0]["stale_evidence_ids"], ["mem_ben_old"])
        self.assertEqual(responses[0]["answer_policy"], "correct_premise_only")
        self.assertIn("current admitted memory says Ben home_city is Milan", responses[0]["final_answer"])

    def test_cli_adapt_weak_gate_results_only_writes_decisions_for_renderer(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Since Ben still lives in Rome, where should the courier go?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Rome",
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)
        tasks = build_weak_gate_tasks(packets)
        outputs = [
            {
                "query_id": "q_ben",
                "decision": "REJECT_STALE_PREMISE",
                "support": "",
                "blocker": "mem_ben_new",
                "final_answer": "Ben's current city is not Rome.",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "missing_records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            packets_in = root / "packets.json"
            tasks_in = root / "weak_gate_tasks.json"
            results_in = root / "weak_gate_results.jsonl"
            decisions_out = root / "read_decisions.json"
            summary_out = root / "summary.json"

            packets_in.write_text(
                json.dumps(packets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tasks_in.write_text(
                json.dumps(tasks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results_in.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in outputs) + "\n",
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--packets-in",
                str(packets_in),
                "--weak-gate-tasks-in",
                str(tasks_in),
                "--weak-gate-results-in",
                str(results_in),
                "--read-decisions-out",
                str(decisions_out),
                "--summary-out",
                str(summary_out),
                "--adapt-weak-gate-results-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            decisions = json.loads(decisions_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_WEAK_GATE_DECISION_ADAPTER_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "weak_gate_decision_adapter_only")
        self.assertEqual(summary["adapted_from_weak_gate_output_count"], 1)
        self.assertEqual(summary["read_decision_counts"]["REJECT_STALE_PREMISE"], 1)
        self.assertEqual(decisions[0]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decisions[0]["decision_source"], "weak_gate_output")

    def test_cli_read_packets_only_writes_reader_outputs_without_store(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "missing_records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            packets_in = root / "packets_in.json"
            store_out = root / "store_out.jsonl"
            decisions_out = root / "decisions.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            summary_out = root / "summary.json"

            packets_in.write_text(
                json.dumps(packets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--packets-in",
                str(packets_in),
                "--store-out",
                str(store_out),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--summary-out",
                str(summary_out),
                "--read-packets-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            decisions = json.loads(decisions_out.read_text(encoding="utf-8"))
            responses = json.loads(responses_out.read_text(encoding="utf-8"))
            results = json.loads(results_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            store_written = store_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_READ_TIME_READER_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "read_time_reader_only")
        self.assertEqual(summary["packet_count"], 1)
        self.assertEqual(summary["read_decision_counts"]["ADMIT_CURRENT"], 1)
        self.assertEqual(summary["read_route_counts"]["current_support_reader"], 1)
        self.assertEqual(summary["reader_answer_policy_counts"]["answer_from_current"], 1)
        self.assertEqual(decisions[0]["decision"], "ADMIT_CURRENT")
        self.assertEqual(responses[0]["answer_evidence_ids"], ["mem_ben_new"])
        self.assertEqual(results[0]["packet"]["query"]["query_id"], "q_ben")
        self.assertFalse(store_written)

    def test_cli_route_packets_only_writes_decisions_without_reader_outputs(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "missing_records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            packets_in = root / "packets_in.json"
            decisions_out = root / "decisions.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            summary_out = root / "summary.json"

            packets_in.write_text(
                json.dumps(packets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--packets-in",
                str(packets_in),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--summary-out",
                str(summary_out),
                "--route-packets-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            decisions = json.loads(decisions_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            responses_written = responses_out.exists()
            results_written = results_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_READ_TIME_ROUTER_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "read_time_router_only")
        self.assertEqual(summary["packet_count"], 1)
        self.assertEqual(summary["read_decision_counts"]["ADMIT_CURRENT"], 1)
        self.assertEqual(summary["read_route_counts"]["current_support_reader"], 1)
        self.assertEqual(decisions[0]["decision"], "ADMIT_CURRENT")
        self.assertEqual(decisions[0]["answer_evidence_ids"], ["mem_ben_new"])
        self.assertFalse(responses_written)
        self.assertFalse(results_written)

    def test_cli_render_decisions_only_writes_reader_outputs_without_routing(self) -> None:
        records = [
            memory(
                "mem_ben_old",
                "Ben",
                "home_city",
                "Rome",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ben_new",
                "Ben",
                "home_city",
                "Milan",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ben",
                "query": "Where does Ben live now?",
                "entity": "Ben",
                "slot": "home_city",
                "needs_current": True,
            }
        ]
        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_records = root / "missing_records.jsonl"
            missing_queries = root / "missing_queries.jsonl"
            packets_in = root / "packets_in.json"
            decisions_in = root / "decisions_in.json"
            decisions_out = root / "decisions_should_not_exist.json"
            responses_out = root / "responses.json"
            results_out = root / "results.json"
            summary_out = root / "summary.json"
            store_out = root / "store_out.jsonl"

            packets_in.write_text(
                json.dumps(packets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            decisions_in.write_text(
                json.dumps(decisions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            argv = [
                "qvf-va",
                "--records",
                str(missing_records),
                "--queries",
                str(missing_queries),
                "--packets-in",
                str(packets_in),
                "--read-decisions-in",
                str(decisions_in),
                "--read-decisions-out",
                str(decisions_out),
                "--reader-responses-out",
                str(responses_out),
                "--query-results-out",
                str(results_out),
                "--summary-out",
                str(summary_out),
                "--store-out",
                str(store_out),
                "--render-decisions-only",
            ]
            with patch("sys.argv", argv):
                with redirect_stdout(io.StringIO()):
                    main()

            responses = json.loads(responses_out.read_text(encoding="utf-8"))
            results = json.loads(results_out.read_text(encoding="utf-8"))
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
            decisions_written = decisions_out.exists()
            store_written = store_out.exists()

        self.assertEqual(summary["decision"], "GO_QVF_LIFECYCLE_READER_RENDERER_READY_NO_API")
        self.assertEqual(summary["execution_mode"], "reader_renderer_only")
        self.assertEqual(summary["packet_count"], 1)
        self.assertEqual(summary["read_decision_count"], 1)
        self.assertEqual(summary["reader_response_count"], 1)
        self.assertEqual(summary["query_result_count"], 1)
        self.assertEqual(summary["reader_answer_policy_counts"]["answer_from_current"], 1)
        self.assertEqual(responses[0]["answer_evidence_ids"], ["mem_ben_new"])
        self.assertEqual(results[0]["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertFalse(decisions_written)
        self.assertFalse(store_written)

    def test_cli_component_mode_argument_validation(self) -> None:
        cases = [
            (
                ["--validate-store-only", "--admit-only"],
                "mutually exclusive",
            ),
            (
                ["--validate-store-only", "--summarize-store-only"],
                "mutually exclusive",
            ),
            (
                ["--summarize-store-only", "--inspect-memory-only", "--memory-id", "mem_a"],
                "mutually exclusive",
            ),
            (
                [
                    "--summarize-store-only",
                    "--inspect-scope-only",
                    "--scope-entity",
                    "Ben",
                    "--scope-slot",
                    "home_city",
                ],
                "mutually exclusive",
            ),
            (
                ["--packets-only", "--inspect-query-only", "--query-id", "q_ben"],
                "mutually exclusive",
            ),
            (
                ["--admit-only", "--preview-admission-only", "--append-records", "new.jsonl"],
                "mutually exclusive",
            ),
            (
                ["--validity-admission-step-only", "--preview-validity-admission-step-only"],
                "mutually exclusive",
            ),
            (
                ["--validate-store-only", "--validate-state-only"],
                "mutually exclusive",
            ),
            (
                ["--admit-only", "--packets-only"],
                "mutually exclusive",
            ),
            (
                ["--packets-only", "--read-packets-only"],
                "mutually exclusive",
            ),
            (
                ["--read-packets-only", "--route-packets-only"],
                "mutually exclusive",
            ),
            (
                ["--route-packets-only", "--render-decisions-only"],
                "mutually exclusive",
            ),
            (
                ["--render-decisions-only", "--weak-gate-pack-only"],
                "mutually exclusive",
            ),
            (
                ["--weak-gate-pack-only", "--analyze-weak-gate-results-only"],
                "mutually exclusive",
            ),
            (
                ["--analyze-weak-gate-results-only", "--adapt-weak-gate-results-only"],
                "mutually exclusive",
            ),
            (
                ["--read-packets-only"],
                "requires --packets-in",
            ),
            (
                ["--validate-state-only"],
                "requires --load-state",
            ),
            (
                ["--load-store", "store.jsonl", "--load-state", "state.json"],
                "mutually exclusive",
            ),
            (
                ["--step-id", "orphan-step"],
                "requires --validity-admission-step-only",
            ),
            (
                ["--memory-id", "mem_a"],
                "requires --inspect-memory-only",
            ),
            (
                ["--inspect-memory-only"],
                "requires --memory-id",
            ),
            (
                ["--query-id", "q_ben"],
                "requires --inspect-query-only",
            ),
            (
                ["--inspect-query-only"],
                "requires --query-id",
            ),
            (
                ["--preview-admission-only"],
                "requires --append-records",
            ),
            (
                ["--scope-entity", "Ben", "--scope-slot", "home_city"],
                "require --inspect-scope-only",
            ),
            (
                ["--scope-namespace", "app"],
                "require --inspect-scope-only",
            ),
            (
                ["--inspect-scope-only", "--scope-entity", "Ben"],
                "requires --scope-entity and --scope-slot",
            ),
            (
                ["--step-request-in", "step_request.json"],
                "requires --validity-admission-step-only",
            ),
            (
                [
                    "--validity-admission-step-only",
                    "--step-request-in",
                    "step_request.json",
                    "--append-records",
                    "append.jsonl",
                ],
                "mutually exclusive",
            ),
            (
                [
                    "--validity-admission-step-only",
                    "--step-request-in",
                    "step_request.json",
                    "--step-id",
                    "duplicate-source",
                ],
                "mutually exclusive",
            ),
            (
                ["--route-packets-only"],
                "requires --packets-in",
            ),
            (
                ["--render-decisions-only"],
                "requires --packets-in",
            ),
            (
                ["--weak-gate-pack-only"],
                "requires --packets-in",
            ),
            (
                ["--analyze-weak-gate-results-only"],
                "requires --weak-gate-tasks-in",
            ),
            (
                ["--adapt-weak-gate-results-only"],
                "requires --packets-in",
            ),
            (
                ["--adapt-weak-gate-results-only", "--packets-in", "packets.json"],
                "requires --weak-gate-tasks-in",
            ),
            (
                ["--render-decisions-only", "--packets-in", "packets.json"],
                "requires --read-decisions-in",
            ),
        ]

        for extra_args, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                argv = ["qvf-va", *extra_args]
                with patch("sys.argv", argv):
                    with self.assertRaisesRegex(ValueError, expected_error):
                        main()

    def test_expired_current_memory_is_blocked_at_read_time(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_trial",
                    "Casey",
                    "subscription_status",
                    "active trial",
                    "2025-01-01T00:00:00+00:00",
                    valid_until="2025-02-01T00:00:00+00:00",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_casey",
                "query": "Since Casey still has an active trial, what should they use?",
                "entity": "Casey",
                "slot": "subscription_status",
                "needs_current": True,
                "embedded_premise_value": "active trial",
                "as_of": "2025-03-01T00:00:00+00:00",
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "expired_contrast",
        )
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(result["reader_response"]["answer_policy"], "correct_premise_only")
        self.assertIn("only supported by stale", result["reader_response"]["final_answer"])

    def test_valid_until_memory_is_current_before_expiration(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_trial",
                    "Casey",
                    "subscription_status",
                    "active trial",
                    "2025-01-01T00:00:00+00:00",
                    valid_until="2025-02-01T00:00:00+00:00",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_casey",
                "query": "Does Casey have an active trial?",
                "entity": "Casey",
                "slot": "subscription_status",
                "needs_current": True,
                "as_of": "2025-01-15T00:00:00+00:00",
            }
        )

        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["reader_response"]["answer_evidence_ids"], ["mem_trial"])

    def test_max_age_days_blocks_old_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_lina_status",
                    "Lina",
                    "assignment_status",
                    "on project alpha",
                    "2025-01-01T00:00:00+00:00",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_lina_stale_by_age",
                "query": "Since Lina is still on project alpha, who should review it?",
                "entity": "Lina",
                "slot": "assignment_status",
                "needs_current": True,
                "embedded_premise_value": "on project alpha",
                "as_of": "2025-04-15T00:00:00+00:00",
                "max_age_days": 30,
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "stale_by_age",
        )
        self.assertEqual(diagnostics["blocked_counts"]["stale_by_age"], 1)
        self.assertEqual(result["read_decision"]["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(result["reader_response"]["answer_policy"], "correct_premise_only")

    def test_max_age_days_allows_recent_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_mira_status",
                    "Mira",
                    "assignment_status",
                    "on project beta",
                    "2025-04-01T00:00:00+00:00",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_mira_recent",
                "query": "Is Mira currently on project beta?",
                "entity": "Mira",
                "slot": "assignment_status",
                "needs_current": True,
                "as_of": "2025-04-15T00:00:00+00:00",
                "max_age_days": 30,
            }
        )

        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_mira_status"],
        )
        self.assertEqual(diagnostics["blocked_counts"]["stale_by_age"], 0)

    def test_query_min_source_confidence_blocks_weak_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_noah_status",
                    "Noah",
                    "travel_clearance",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                    source_confidence=0.65,
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_noah_high_risk",
                "query": "Can Noah travel now?",
                "entity": "Noah",
                "slot": "travel_clearance",
                "needs_current": True,
                "min_source_confidence": 0.8,
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "below_query_confidence",
        )
        self.assertEqual(diagnostics["blocked_counts"]["below_query_confidence"], 1)
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_query_min_source_confidence_allows_strong_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_olivia_status",
                    "Olivia",
                    "travel_clearance",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                    source_confidence=0.95,
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_olivia_high_risk",
                "query": "Can Olivia travel now?",
                "entity": "Olivia",
                "slot": "travel_clearance",
                "needs_current": True,
                "min_source_confidence": 0.8,
            }
        )

        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_olivia_status"],
        )
        self.assertEqual(diagnostics["blocked_counts"]["below_query_confidence"], 0)

    def test_min_supporting_count_blocks_singleton_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_priya_status",
                    "Priya",
                    "access_status",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_priya_quorum",
                "query": "Is Priya approved for access now?",
                "entity": "Priya",
                "slot": "access_status",
                "needs_current": True,
                "min_supporting_count": 1,
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "insufficient_support",
        )
        self.assertEqual(diagnostics["blocked_counts"]["insufficient_support"], 1)
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_min_supporting_count_allows_supported_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_quentin_status_primary",
                    "Quentin",
                    "access_status",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                ),
                memory(
                    "mem_quentin_status_support",
                    "Quentin",
                    "access_status",
                    "approved",
                    "2025-04-02T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_quentin_quorum",
                "query": "Is Quentin approved for access now?",
                "entity": "Quentin",
                "slot": "access_status",
                "needs_current": True,
                "min_supporting_count": 1,
            }
        )

        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_quentin_status_primary"],
        )
        self.assertEqual(diagnostics["blocked_counts"]["insufficient_support"], 0)
        self.assertEqual(diagnostics["selected_counts"]["supporting_evidence"], 1)

    def test_source_policy_blocks_disallowed_source_type(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_rhea_status",
                    "Rhea",
                    "employment_status",
                    "contractor",
                    "2025-04-01T00:00:00+00:00",
                    source_type="chat_observation",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_rhea_verified_only",
                "query": "Is Rhea a contractor now?",
                "entity": "Rhea",
                "slot": "employment_status",
                "needs_current": True,
                "allowed_source_types": ["hr_system"],
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "source_policy_mismatch",
        )
        self.assertEqual(diagnostics["blocked_counts"]["source_policy_mismatch"], 1)
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_source_policy_allows_required_source_type(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_sam_status",
                    "Sam",
                    "employment_status",
                    "contractor",
                    "2025-04-01T00:00:00+00:00",
                    source_type="hr_system",
                    source_id="hr_42",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_sam_verified_only",
                "query": "Is Sam a contractor now?",
                "entity": "Sam",
                "slot": "employment_status",
                "needs_current": True,
                "allowed_source_types": ["hr_system"],
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_sam_status"],
        )
        self.assertEqual(packet["current_evidence"][0]["source_type"], "hr_system")
        self.assertEqual(packet["current_evidence"][0]["source_id"], "hr_42")
        self.assertEqual(diagnostics["blocked_counts"]["source_policy_mismatch"], 0)

    def test_high_stakes_risk_profile_applies_default_retrieval_gates(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_tara_status",
                    "Tara",
                    "travel_clearance",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                    source_confidence=0.95,
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_tara_high_stakes",
                "query": "Can Tara travel now?",
                "entity": "Tara",
                "slot": "travel_clearance",
                "needs_current": True,
                "as_of": "2025-04-10T00:00:00+00:00",
                "risk_profile": "high_stakes",
            }
        )

        packet = result["packet"]
        diagnostics = packet["retrieval_diagnostics"]
        self.assertEqual(packet["query"]["risk_profile"], "high_stakes")
        self.assertEqual(packet["query"]["max_age_days"], 14.0)
        self.assertEqual(packet["query"]["min_source_confidence"], 0.8)
        self.assertEqual(packet["query"]["min_supporting_count"], 1)
        self.assertEqual(packet["compact_validity_packet"]["current_evidence"], [])
        self.assertEqual(diagnostics["blocked_counts"]["below_query_confidence"], 0)
        self.assertEqual(diagnostics["blocked_counts"]["insufficient_support"], 1)
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_validity_profile_alias_applies_risk_profile_defaults(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_tara_status",
                    "Tara",
                    "travel_clearance",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                    source_confidence=0.95,
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_tara_validity_profile",
                "query": "Can Tara travel now?",
                "entity": "Tara",
                "slot": "travel_clearance",
                "needs_current": True,
                "as_of": "2025-04-10T00:00:00+00:00",
                "validity_profile": "high_stakes",
            }
        )

        packet = result["packet"]
        self.assertEqual(packet["query"]["risk_profile"], "high_stakes")
        self.assertEqual(packet["query"]["max_age_days"], 14.0)
        self.assertEqual(packet["query"]["min_source_confidence"], 0.8)
        self.assertEqual(packet["query"]["min_supporting_count"], 1)
        self.assertEqual(result["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_explicit_query_gates_override_risk_profile_defaults(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_uri_status",
                    "Uri",
                    "travel_clearance",
                    "approved",
                    "2025-04-01T00:00:00+00:00",
                    source_confidence=0.75,
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_uri_high_stakes_override",
                "query": "Can Uri travel now?",
                "entity": "Uri",
                "slot": "travel_clearance",
                "needs_current": True,
                "as_of": "2025-04-10T00:00:00+00:00",
                "risk_profile": "high_stakes",
                "max_age_days": 30,
                "min_source_confidence": 0.5,
                "min_supporting_count": 0,
            }
        )

        packet = result["packet"]
        diagnostics = packet["retrieval_diagnostics"]
        self.assertEqual(packet["query"]["risk_profile"], "high_stakes")
        self.assertEqual(packet["query"]["max_age_days"], 30.0)
        self.assertEqual(packet["query"]["min_source_confidence"], 0.5)
        self.assertEqual(packet["query"]["min_supporting_count"], 0)
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_uri_status"],
        )
        self.assertEqual(diagnostics["blocked_counts"]["below_query_confidence"], 0)
        self.assertEqual(diagnostics["blocked_counts"]["insufficient_support"], 0)

    def test_as_of_query_reconstructs_historical_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_alice_2024",
                    "Alice",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_alice_2025",
                    "Alice",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_alice_2024",
                "query": "Where was Alice's office in June 2024?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
                "as_of": "2024-06-01T00:00:00+00:00",
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        diagnostics = result["packet"]["retrieval_diagnostics"]
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_alice_2024"],
        )
        self.assertEqual(packet["current_evidence"][0]["value"], "Paris")
        self.assertEqual(diagnostics["blocked_counts"]["future_evidence"], 1)
        self.assertEqual(diagnostics["selected_counts"]["current_evidence"], 1)
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "future_evidence",
        )
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["memory_id"],
            "mem_alice_2025",
        )

    def test_query_without_as_of_uses_latest_current_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_ben_2024",
                    "Ben",
                    "office_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_ben_2025",
                    "Ben",
                    "office_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_ben_latest",
                "query": "Where is Ben's office now?",
                "entity": "Ben",
                "slot": "office_city",
                "needs_current": True,
            }
        )

        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_ben_2025"],
        )
        self.assertEqual(
            result["packet"]["compact_validity_packet"]["historical_evidence"],
            [],
        )

    def test_historical_query_can_answer_from_archive_without_hiding_current(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_cara_2024",
                    "Cara",
                    "office_city",
                    "Paris",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_cara_2025",
                    "Cara",
                    "office_city",
                    "Berlin",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_cara_previous",
                "query": "Where was Cara's office before the move?",
                "entity": "Cara",
                "slot": "office_city",
                "needs_current": False,
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        policy = result["packet"]["context_control_policy"]

        self.assertEqual(result["packet"]["query"]["query_intent"], "historical_recall")
        self.assertEqual(result["read_decision"]["route"], "archive_aware_reader")
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_ARCHIVE")
        self.assertEqual(result["read_decision"]["answer_policy"], "answer_from_archive")
        self.assertEqual(
            result["read_decision"]["validity_controller_decision"]["next_action"],
            "answer_from_archive",
        )
        self.assertTrue(
            result["read_decision"]["validity_controller_decision"][
                "suggested_retrieval_scope"
            ]["include_source_history"]
        )
        self.assertIn(
            "mem_cara_2024",
            result["read_decision"]["validity_controller_decision"][
                "allowed_as_history_ids"
            ],
        )
        self.assertEqual(packet["current_evidence"][0]["memory_id"], "mem_cara_2025")
        self.assertEqual(packet["historical_evidence"][0]["memory_id"], "mem_cara_2024")
        self.assertEqual(packet["historical_evidence"][0]["retrieval_role"], "historical_evidence")
        self.assertIn("historical_evidence", policy["answer_from_roles"])
        self.assertTrue(policy["include_archive_evidence_as_answer_context"])
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_cara_2024", "mem_cara_2025"],
        )
        self.assertTrue(
            result["reader_response"]["control"]["used_archive_as_answer_evidence"]
        )

    def test_explicit_current_query_keeps_archive_as_non_answer_contrast(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_dina_2024",
                    "Dina",
                    "home_city",
                    "Rome",
                    "2024-01-01T00:00:00+00:00",
                ),
                memory(
                    "mem_dina_2025",
                    "Dina",
                    "home_city",
                    "Milan",
                    "2025-01-01T00:00:00+00:00",
                ),
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_dina_current",
                "query": "Where does Dina live now?",
                "entity": "Dina",
                "slot": "home_city",
                "needs_current": True,
            }
        )

        packet = result["packet"]["compact_validity_packet"]
        policy = result["packet"]["context_control_policy"]

        self.assertEqual(result["packet"]["query"]["query_intent"], "current_state")
        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(result["read_decision"]["answer_policy"], "answer_from_current")
        self.assertEqual(
            result["read_decision"]["validity_controller_decision"]["next_action"],
            "answer_from_current",
        )
        self.assertIn(
            "mem_dina_2024",
            result["read_decision"]["validity_controller_decision"][
                "blocked_as_current_ids"
            ],
        )
        self.assertEqual(packet["current_evidence"][0]["memory_id"], "mem_dina_2025")
        self.assertEqual(packet["historical_evidence"], [])
        self.assertEqual(packet["stale_or_blocked_evidence"][0]["memory_id"], "mem_dina_2024")
        self.assertFalse(policy["include_archive_evidence_as_answer_context"])

    def test_conditional_memory_requires_matching_query_condition(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_refund_standard",
                    "Acme Support",
                    "refund_channel",
                    "self_service_portal",
                    "2026-01-01T00:00:00+00:00",
                    condition="standard refunds",
                )
            ]
        )

        matched = pipeline.query(
            {
                "query_id": "q_refund_standard",
                "query": "How should standard refunds be requested now?",
                "entity": "Acme Support",
                "slot": "refund_channel",
                "needs_current": True,
            }
        )
        self.assertEqual(matched["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            matched["reader_response"]["answer_evidence_ids"],
            ["mem_refund_standard"],
        )

        mismatched = pipeline.query(
            {
                "query_id": "q_refund_unspecified",
                "query": "How should refunds be requested now?",
                "entity": "Acme Support",
                "slot": "refund_channel",
                "needs_current": True,
            }
        )
        packet = mismatched["packet"]["compact_validity_packet"]
        self.assertEqual(packet["current_evidence"], [])
        self.assertEqual(
            packet["stale_or_blocked_evidence"][0]["retrieval_role"],
            "condition_mismatch",
        )
        self.assertEqual(mismatched["read_decision"]["decision"], "UNKNOWN_CURRENT")

    def test_explicit_query_condition_admits_conditional_memory(self) -> None:
        pipeline = QVFMemoryPipeline.from_records(
            [
                memory(
                    "mem_refund_premium",
                    "Acme Support",
                    "refund_channel",
                    "concierge_support",
                    "2026-01-01T00:00:00+00:00",
                    condition="premium plan refunds",
                )
            ]
        )
        result = pipeline.query(
            {
                "query_id": "q_refund_premium",
                "query": "How should refunds be requested now?",
                "entity": "Acme Support",
                "slot": "refund_channel",
                "needs_current": True,
                "condition": "premium plan refunds",
            }
        )

        self.assertEqual(result["read_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            result["reader_response"]["answer_evidence_ids"],
            ["mem_refund_premium"],
        )

    def test_packet_budget_controls_stale_context_and_edges(self) -> None:
        records = [
            memory(
                "mem_alice_old",
                "Alice",
                "office_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets_without_stale = build_lifecycle_packets(
            records,
            queries,
            max_stale=0,
        )
        packet = packets_without_stale[0]["compact_validity_packet"]
        self.assertEqual(len(packet["current_evidence"]), 1)
        self.assertEqual(len(packet["stale_or_blocked_evidence"]), 0)
        self.assertEqual(packet["validity_edges"], [])

        _, packets_with_stale = build_lifecycle_packets(
            records,
            queries,
            max_stale=1,
        )
        packet = packets_with_stale[0]["compact_validity_packet"]
        self.assertEqual(len(packet["current_evidence"]), 1)
        self.assertEqual(len(packet["stale_or_blocked_evidence"]), 1)
        self.assertTrue(
            any(edge["type"] == "supersedes" for edge in packet["validity_edges"])
        )

    def test_packet_char_budget_prunes_noncritical_context(self) -> None:
        long_old_value = "Paris " + ("historic stale detail " * 40)
        records = [
            memory(
                "mem_alice_old_1",
                "Alice",
                "office_city",
                long_old_value,
                "2023-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_alice_old_2",
                "Alice",
                "office_city",
                "Rome " + ("older contrast " * 40),
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_alice_low_conf",
                "Alice",
                "office_city",
                "Madrid",
                "2026-01-01T00:00:00+00:00",
                source_confidence=0.2,
            ),
        ]
        queries = [
            {
                "query_id": "q_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, full_packets = build_lifecycle_packets(
            records,
            queries,
            max_stale=2,
            max_excluded=1,
        )
        full_size = full_packets[0]["token_budget_proxy"]["json_chars"]
        _, minimal_packets = build_lifecycle_packets(
            records,
            queries,
            max_stale=0,
            max_excluded=0,
            include_validity_edges=False,
            include_weak_gate_card=False,
        )
        minimal_size = minimal_packets[0]["token_budget_proxy"]["json_chars"]
        self.assertLess(minimal_size + 500, full_size)
        max_packet_chars = minimal_size + 500

        _, budgeted_packets = build_lifecycle_packets(
            records,
            queries,
            max_stale=2,
            max_excluded=1,
            max_packet_chars=max_packet_chars,
        )
        packet = budgeted_packets[0]
        proxy = packet["token_budget_proxy"]

        self.assertTrue(proxy["budget_satisfied"])
        self.assertLessEqual(proxy["json_chars"], max_packet_chars)
        self.assertEqual(proxy["max_packet_chars"], max_packet_chars)
        self.assertIn("drop_weak_conservative_gate_card", proxy["pruning_steps"])
        self.assertNotIn("weak_conservative_gate_card", packet)
        self.assertEqual(
            packet["compact_validity_packet"]["current_evidence"][0]["memory_id"],
            "mem_alice_new",
        )
        self.assertEqual(build_read_decisions(budgeted_packets)[0]["decision"], "ADMIT_CURRENT")

        _, tiny_budget_packets = build_lifecycle_packets(
            records,
            queries,
            max_stale=2,
            max_excluded=1,
            max_packet_chars=1,
        )
        tiny_packet = tiny_budget_packets[0]
        self.assertFalse(tiny_packet["token_budget_proxy"]["budget_satisfied"])
        self.assertTrue(tiny_packet["retrieval_diagnostics"]["packet_budget_pruned"])
        for bucket_name in [
            "current_evidence",
            "supporting_evidence",
            "stale_or_blocked_evidence",
            "excluded_memory_summary",
        ]:
            with self.subTest(bucket_name=bucket_name):
                self.assertEqual(
                    tiny_packet["retrieval_diagnostics"]["selected_counts"][bucket_name],
                    len(tiny_packet["compact_validity_packet"][bucket_name]),
                )

    def test_packet_char_budget_preserves_embedded_premise_gate(self) -> None:
        records = [
            memory(
                "mem_finn_old",
                "Finn",
                "borrowed_tool",
                "still has saw",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_finn_new",
                "Finn",
                "borrowed_tool",
                "returned saw",
                "2025-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_finn_low_conf",
                "Finn",
                "borrowed_tool",
                "lost saw " + ("low confidence distractor " * 50),
                "2026-01-01T00:00:00+00:00",
                source_confidence=0.2,
            ),
        ]
        queries = [
            {
                "query_id": "q_finn",
                "query": "Since Finn still has the saw, how should he return it?",
                "entity": "Finn",
                "slot": "borrowed_tool",
                "needs_current": True,
                "embedded_premise_value": "still has saw",
            }
        ]

        _, full_packets = build_lifecycle_packets(
            records,
            queries,
            max_excluded=1,
        )
        tight_budget = full_packets[0]["token_budget_proxy"]["json_chars"] - 100
        _, budgeted_packets = build_lifecycle_packets(
            records,
            queries,
            max_excluded=1,
            max_packet_chars=tight_budget,
        )
        packet = budgeted_packets[0]
        decision = build_read_decisions(budgeted_packets)[0]
        response = build_reader_responses(budgeted_packets, [decision])[0]

        self.assertIn("weak_conservative_gate_card", packet)
        self.assertTrue(packet["token_budget_proxy"]["pruning_steps"])
        self.assertNotIn(
            "drop_weak_conservative_gate_card",
            packet["token_budget_proxy"]["pruning_steps"],
        )
        self.assertEqual(decision["route"], "weak_conservative_gate")
        self.assertEqual(decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decision["blocking_evidence_ids"], ["mem_finn_new"])
        self.assertIn("returned saw", response["final_answer"])

    def test_packet_char_budget_marks_unsatisfied_when_minimum_packet_is_too_large(self) -> None:
        records = [
            memory(
                "mem_alice_new",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries, max_packet_chars=1)
        packet = packets[0]

        self.assertFalse(packet["token_budget_proxy"]["budget_satisfied"])
        self.assertEqual(packet["token_budget_proxy"]["max_packet_chars"], 1)
        self.assertEqual(
            packet["compact_validity_packet"]["current_evidence"][0]["memory_id"],
            "mem_alice_new",
        )
        self.assertEqual(build_read_decisions(packets)[0]["decision"], "ADMIT_CURRENT")

    def test_retrieval_budget_rejects_invalid_values(self) -> None:
        records = [
            memory(
                "mem_alice",
                "Alice",
                "office_city",
                "Berlin",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_alice",
                "query": "Where is Alice's office now?",
                "entity": "Alice",
                "slot": "office_city",
                "needs_current": True,
            }
        ]
        cases = [
            ({"max_current": -1}, "max_current"),
            ({"max_supporting": 1.5}, "max_supporting"),
            ({"max_stale": True}, "max_stale"),
            ({"max_excluded": "2"}, "max_excluded"),
        ]

        for kwargs, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    build_lifecycle_packets(records, queries, **kwargs)

        with self.assertRaisesRegex(ValueError, "max_stale"):
            build_packets_from_store(ValidityAwareMemoryStore(), [], max_stale=-1)

        with self.assertRaisesRegex(ValueError, "max_current"):
            QVFMemoryPipeline(max_current=False)

        with self.assertRaisesRegex(ValueError, "max_packet_chars"):
            build_lifecycle_packets(records, queries, max_packet_chars=0)

        with self.assertRaisesRegex(ValueError, "max_packet_chars"):
            build_packets_from_store(
                ValidityAwareMemoryStore(),
                [],
                max_packet_chars="100",
            )

        with self.assertRaisesRegex(ValueError, "max_packet_chars"):
            QVFMemoryPipeline(max_packet_chars=True)

    def test_low_confidence_threshold_is_configurable(self) -> None:
        borderline = memory(
            "mem_carol",
            "Carol",
            "travel_city",
            "Oslo",
            "2026-01-01T00:00:00+00:00",
            source_confidence=0.6,
        )

        strict_store = ValidityAwareMemoryStore(low_confidence_threshold=0.7)
        strict_record = strict_store.admit(borderline)
        self.assertEqual(strict_record.admission_status, "reject_low_confidence")

        permissive_store = ValidityAwareMemoryStore(low_confidence_threshold=0.5)
        permissive_record = permissive_store.admit(borderline)
        self.assertEqual(permissive_record.admission_status, "admit_current")

    def test_low_confidence_threshold_rejects_invalid_values(self) -> None:
        cases = [
            (True, "number in \\[0, 1\\]"),
            ("0.5", "number in \\[0, 1\\]"),
            (-0.1, "in \\[0, 1\\]"),
            (1.1, "in \\[0, 1\\]"),
        ]

        for value, expected_error in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, expected_error):
                    ValidityAwareMemoryStore(low_confidence_threshold=value)

        with self.assertRaisesRegex(ValueError, "low_confidence_threshold"):
            QVFMemoryPipeline.from_records([], low_confidence_threshold=False)

    def test_graph_edges_can_be_disabled(self) -> None:
        records = [
            memory(
                "mem_bob_old",
                "Bob",
                "meeting_day",
                "Monday",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_bob_new",
                "Bob",
                "meeting_day",
                "Tuesday",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_bob",
                "query": "What day is Bob's meeting now?",
                "entity": "Bob",
                "slot": "meeting_day",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(
            records,
            queries,
            include_validity_edges=False,
        )
        self.assertEqual(packets[0]["compact_validity_packet"]["validity_edges"], [])

    def test_weak_gate_card_rejects_embedded_stale_premise(self) -> None:
        records = [
            memory(
                "mem_dana_old",
                "Dana",
                "home_city",
                "Seattle",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_dana_new",
                "Dana",
                "home_city",
                "Portland",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_dana",
                "query": "Since Dana still lives in Seattle, what errands are nearby?",
                "entity": "Dana",
                "slot": "home_city",
                "needs_current": True,
                "embedded_premise_value": "Seattle",
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        card = packets[0]["weak_conservative_gate_card"]

        self.assertEqual(card["expected_gate_decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(card["query"]["embedded_premise_value"], "Seattle")
        self.assertEqual(card["current_candidate_evidence"][0]["value"], "Portland")
        self.assertEqual(card["stale_or_blocked_evidence"][0]["value"], "Seattle")

    def test_weak_gate_card_can_be_disabled(self) -> None:
        records = [
            memory(
                "mem_erin",
                "Erin",
                "office_city",
                "Madrid",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_erin",
                "query": "Where is Erin's office now?",
                "entity": "Erin",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(
            records,
            queries,
            include_weak_gate_card=False,
        )
        self.assertNotIn("weak_conservative_gate_card", packets[0])

    def test_read_router_rejects_stale_embedded_premise(self) -> None:
        records = [
            memory(
                "mem_finn_old",
                "Finn",
                "borrowed_tool",
                "still has saw",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_finn_new",
                "Finn",
                "borrowed_tool",
                "returned saw",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_finn",
                "query": "Since Finn still has the saw, how should he return it?",
                "entity": "Finn",
                "slot": "borrowed_tool",
                "needs_current": True,
                "embedded_premise_value": "still has saw",
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decision = build_read_decisions(packets)[0]

        self.assertEqual(decision["route"], "weak_conservative_gate")
        self.assertEqual(decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decision["answer_policy"], "correct_premise_only")
        self.assertEqual(decision["blocking_evidence_ids"], ["mem_finn_new"])
        self.assertEqual(decision["stale_evidence_ids"], ["mem_finn_old"])
        self.assertIn("returned saw", decision["final_answer_hint"])

    def test_dim3_actionable_profile_corrects_then_answers_from_current(self) -> None:
        records = [
            memory(
                "mem_nora_old",
                "Nora",
                "commute_mode",
                "cycling",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_nora_new",
                "Nora",
                "commute_mode",
                "train",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_nora_action",
                "query": "Since Nora still cycles to work, what should she do to plan her commute?",
                "entity": "Nora",
                "slot": "commute_mode",
                "needs_current": True,
                "embedded_premise_value": "cycling",
                "reader_profile": "dim3_actionable",
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decision = build_read_decisions(packets)[0]
        response = build_reader_responses(packets, [decision])[0]

        self.assertEqual(packets[0]["query"]["reader_profile"], "dim3_actionable")
        self.assertEqual(decision["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(decision["answer_policy"], "correct_then_answer_from_current")
        self.assertEqual(decision["answer_evidence_ids"], ["mem_nora_new"])
        self.assertEqual(decision["blocking_evidence_ids"], ["mem_nora_new"])
        self.assertEqual(response["answer_policy"], "correct_then_answer_from_current")
        self.assertIn("should not use the embedded premise", response["final_answer"])
        self.assertIn("train", response["final_answer"])
        self.assertFalse(response["control"]["used_stale_as_answer_evidence"])

    def test_weak_conservative_profile_adds_hard_gate_rule_to_task(self) -> None:
        records = [
            memory(
                "mem_omar_old",
                "Omar",
                "home_city",
                "Seattle",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_omar_new",
                "Omar",
                "home_city",
                "Portland",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_omar_weak",
                "query": "Since Omar still lives in Seattle, what nearby errands should he do?",
                "entity": "Omar",
                "slot": "home_city",
                "embedded_premise_value": "Seattle",
                "reader_profile": "weak_conservative",
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        tasks = build_weak_gate_tasks(packets)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["input"]["query"]["reader_profile"], "weak_conservative")
        self.assertEqual(tasks[0]["expected_gate_decision"], "REJECT_STALE_PREMISE")
        self.assertIn(
            "For weak readers, compare embedded_premise_value",
            tasks[0]["input"]["decision_rules"][0],
        )

    def test_query_reader_profile_aliases_and_invalid_values_are_validated(self) -> None:
        records = [
            memory(
                "mem_pia_new",
                "Pia",
                "office_city",
                "Rome",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        _, packets = build_lifecycle_packets(
            records,
            [
                {
                    "query_id": "q_pia",
                    "query": "Where is Pia now?",
                    "entity": "Pia",
                    "slot": "office_city",
                    "reader_profile": "dim3",
                }
            ],
        )

        self.assertEqual(packets[0]["query"]["reader_profile"], "dim3_actionable")

        with self.assertRaisesRegex(ValueError, "reader_profile"):
            build_lifecycle_packets(
                records,
                [
                    {
                        "query_id": "q_pia_bad",
                        "query": "Where is Pia now?",
                        "entity": "Pia",
                        "slot": "office_city",
                        "reader_profile": "mystery_profile",
                    }
                ],
            )

    def test_read_router_admits_current_support_without_embedded_premise(self) -> None:
        records = [
            memory(
                "mem_gia",
                "Gia",
                "office_city",
                "Lisbon",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_gia",
                "query": "Where is Gia's office now?",
                "entity": "Gia",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decision = build_read_decisions(packets)[0]

        self.assertEqual(decision["route"], "current_support_reader")
        self.assertEqual(decision["decision"], "ADMIT_CURRENT")
        self.assertEqual(decision["answer_policy"], "answer_from_current")
        self.assertEqual(decision["answer_evidence_ids"], ["mem_gia"])
        self.assertEqual(
            decision["validity_controller_decision"]["evidence_sufficiency"],
            "sufficient_current_evidence",
        )

    def test_validity_controller_requests_current_retrieval_for_stale_only_packet(self) -> None:
        records = [
            memory(
                "mem_zara_old",
                "Zara",
                "home_city",
                "Paris",
                "2024-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_zara_current",
                "query": "Where does Zara live now?",
                "entity": "Zara",
                "slot": "home_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        packet = deepcopy(packets[0])
        stale_row = dict(packet["compact_validity_packet"]["current_evidence"][0])
        stale_row["retrieval_role"] = "stale_or_blocked"
        packet["compact_validity_packet"]["current_evidence"] = []
        packet["compact_validity_packet"]["stale_or_blocked_evidence"] = [stale_row]
        decision = route_read_time_packet(packet)
        controller = decision["validity_controller_decision"]

        self.assertEqual(decision["decision"], "UNKNOWN_CURRENT")
        self.assertEqual(controller["next_action"], "retrieve_current_entity_slot")
        self.assertEqual(
            controller["evidence_sufficiency"],
            "archive_or_stale_only_for_current_query",
        )
        self.assertEqual(controller["blocked_as_current_ids"], ["mem_zara_old"])
        self.assertEqual(controller["allowed_as_history_ids"], ["mem_zara_old"])
        self.assertIn("Zara home_city", controller["query_rewrite"])

    def test_reader_renderer_corrects_rejected_stale_premise(self) -> None:
        records = [
            memory(
                "mem_hugo_old",
                "Hugo",
                "borrowed_item",
                "still has camera",
                "2024-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_hugo_new",
                "Hugo",
                "borrowed_item",
                "returned camera",
                "2025-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_hugo",
                "query": "Since Hugo still has the camera, how should he return it?",
                "entity": "Hugo",
                "slot": "borrowed_item",
                "needs_current": True,
                "embedded_premise_value": "still has camera",
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)
        response = build_reader_responses(packets, decisions)[0]

        self.assertEqual(response["decision"], "REJECT_STALE_PREMISE")
        self.assertEqual(response["answer_policy"], "correct_premise_only")
        self.assertEqual(response["blocking_evidence_ids"], ["mem_hugo_new"])
        self.assertIn("returned camera", response["final_answer"])
        self.assertFalse(response["control"]["used_stale_as_answer_evidence"])

    def test_reader_renderer_answers_from_current_support(self) -> None:
        records = [
            memory(
                "mem_ivy",
                "Ivy",
                "home_city",
                "Dublin",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_ivy",
                "query": "Where does Ivy live now?",
                "entity": "Ivy",
                "slot": "home_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)
        response = build_reader_responses(packets, decisions)[0]

        self.assertEqual(response["decision"], "ADMIT_CURRENT")
        self.assertEqual(response["answer_policy"], "answer_from_current")
        self.assertEqual(response["answer_evidence_ids"], ["mem_ivy"])
        self.assertIn("Dublin", response["final_answer"])

    def test_reader_renderer_rejects_missing_decision_evidence_ids(self) -> None:
        records = [
            memory(
                "mem_ivy",
                "Ivy",
                "home_city",
                "Dublin",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_ivy",
                "query": "Where does Ivy live now?",
                "entity": "Ivy",
                "slot": "home_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decision = build_read_decisions(packets)[0]

        for field_name in [
            "answer_evidence_ids",
            "blocking_evidence_ids",
            "stale_evidence_ids",
        ]:
            with self.subTest(field_name=field_name):
                bad_decision = dict(decision)
                bad_decision[field_name] = ["missing_memory"]

                with self.assertRaisesRegex(ValueError, field_name):
                    build_reader_responses(packets, [bad_decision])

    def test_reader_renderer_rejects_invalid_decision_shape(self) -> None:
        records = [
            memory(
                "mem_ivy",
                "Ivy",
                "home_city",
                "Dublin",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_ivy",
                "query": "Where does Ivy live now?",
                "entity": "Ivy",
                "slot": "home_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decision = build_read_decisions(packets)[0]
        cases = [
            ({"answer_evidence_ids": "mem_ivy"}, "answer_evidence_ids"),
            ({"blocking_evidence_ids": [123]}, "blocking_evidence_ids"),
            ({"stale_evidence_ids": [""]}, "stale_evidence_ids"),
            ({"route": "freeform_reader"}, "read_decision.route"),
            ({"decision": "MAYBE_CURRENT"}, "read_decision.decision"),
            ({"answer_policy": "answer_from_stale"}, "read_decision.answer_policy"),
            ({"query_id": "wrong_query"}, "does not match"),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                bad_decision = dict(decision)
                bad_decision.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    build_reader_responses(packets, [bad_decision])

    def test_read_time_pipeline_rejects_invalid_packet_shape(self) -> None:
        records = [
            memory(
                "mem_ivy",
                "Ivy",
                "home_city",
                "Dublin",
                "2025-01-01T00:00:00+00:00",
            ),
            memory(
                "mem_ivy_old",
                "Ivy",
                "home_city",
                "Galway",
                "2024-01-01T00:00:00+00:00",
            ),
        ]
        queries = [
            {
                "query_id": "q_ivy",
                "query": "Where does Ivy live now?",
                "entity": "Ivy",
                "slot": "home_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        cases = []

        bad_bucket = deepcopy(packets[0])
        bad_bucket["compact_validity_packet"]["current_evidence"] = "not-a-list"
        cases.append((bad_bucket, "current_evidence"))

        missing_value = deepcopy(packets[0])
        del missing_value["compact_validity_packet"]["current_evidence"][0]["value"]
        cases.append((missing_value, "current_evidence\\[0\\].value"))

        duplicate_id = deepcopy(packets[0])
        duplicate_row = dict(duplicate_id["compact_validity_packet"]["current_evidence"][0])
        duplicate_id["compact_validity_packet"]["stale_or_blocked_evidence"].append(
            duplicate_row
        )
        cases.append((duplicate_id, "Duplicate evidence memory_id"))

        bad_edge = deepcopy(packets[0])
        bad_edge["compact_validity_packet"]["validity_edges"] = [
            {"source": "mem_ivy", "target": "", "type": "supports"}
        ]
        cases.append((bad_edge, "validity_edges\\[0\\].target"))

        bad_gate_decision = deepcopy(packets[0])
        bad_gate_decision["weak_conservative_gate_card"][
            "expected_gate_decision"
        ] = "MAYBE_CURRENT"
        cases.append((bad_gate_decision, "expected_gate_decision"))

        for bad_packet, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    build_read_decisions([bad_packet])

        bad_reader_packet = deepcopy(packets[0])
        del bad_reader_packet["query"]["entity"]
        decision = build_read_decisions(packets)[0]

        with self.assertRaisesRegex(ValueError, "packet.query.entity"):
            build_reader_responses([bad_reader_packet], [decision])

    def test_read_time_batch_helpers_reject_invalid_batch_shapes(self) -> None:
        records = [
            memory(
                "mem_ivy",
                "Ivy",
                "home_city",
                "Dublin",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_ivy",
                "query": "Where does Ivy live now?",
                "entity": "Ivy",
                "slot": "home_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)
        responses = build_reader_responses(packets, decisions)

        with self.assertRaisesRegex(ValueError, "packets must be a list"):
            build_read_decisions({"not": "a list"})

        with self.assertRaisesRegex(ValueError, "read_decisions must be a list"):
            build_reader_responses(packets, {"not": "a list"})

        with self.assertRaisesRegex(ValueError, "reader_responses must be a list"):
            build_query_results(packets, decisions, {"not": "a list"})

        duplicate_packets = [deepcopy(packets[0]), deepcopy(packets[0])]
        with self.assertRaisesRegex(ValueError, "Duplicate packet query_id"):
            build_read_decisions(duplicate_packets)

        with self.assertRaisesRegex(ValueError, "Duplicate packet query_id"):
            build_query_results(duplicate_packets, decisions + decisions, responses + responses)

    def test_build_query_results_bundles_packet_decision_and_response(self) -> None:
        records = [
            memory(
                "mem_jules",
                "Jules",
                "office_city",
                "Prague",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_jules",
                "query": "Where is Jules's office now?",
                "entity": "Jules",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)
        responses = build_reader_responses(packets, decisions)
        results = build_query_results(packets, decisions, responses)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query_id"], "q_jules")
        self.assertEqual(results[0]["packet"], packets[0])
        self.assertEqual(results[0]["read_decision"], decisions[0])
        self.assertEqual(results[0]["reader_response"], responses[0])

        bad_response = dict(responses[0])
        bad_response["query_id"] = "wrong_query"
        with self.assertRaises(ValueError):
            build_query_results(packets, decisions, [bad_response])

    def test_build_query_results_rejects_invalid_reader_response_shape(self) -> None:
        records = [
            memory(
                "mem_jules",
                "Jules",
                "office_city",
                "Prague",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_jules",
                "query": "Where is Jules's office now?",
                "entity": "Jules",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)
        response = build_reader_responses(packets, decisions)[0]
        cases = [
            ({"answer_evidence_ids": "mem_jules"}, "reader_response.answer_evidence_ids"),
            ({"blocking_evidence_ids": [123]}, "reader_response.blocking_evidence_ids"),
            ({"control": None}, "reader_response.control"),
            (
                {
                    "control": {
                        "used_stale_as_answer_evidence": "false",
                        "requires_llm_freeform_completion": False,
                        "reader_contract": "",
                    }
                },
                "used_stale_as_answer_evidence",
            ),
            ({"answer_policy": "answer_from_stale"}, "reader_response.answer_policy"),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                bad_response = dict(response)
                bad_response.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    build_query_results(packets, decisions, [bad_response])

    def test_build_query_results_rejects_reader_response_decision_mismatch(self) -> None:
        records = [
            memory(
                "mem_jules",
                "Jules",
                "office_city",
                "Prague",
                "2025-01-01T00:00:00+00:00",
            )
        ]
        queries = [
            {
                "query_id": "q_jules",
                "query": "Where is Jules's office now?",
                "entity": "Jules",
                "slot": "office_city",
                "needs_current": True,
            }
        ]

        _, packets = build_lifecycle_packets(records, queries)
        decisions = build_read_decisions(packets)
        response = build_reader_responses(packets, decisions)[0]
        cases = [
            ({"decision": "UNKNOWN_CURRENT"}, "reader_response.decision"),
            ({"route": "unknown_current_router"}, "reader_response.route"),
            ({"answer_evidence_ids": []}, "reader_response.answer_evidence_ids"),
        ]

        for patch, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                bad_response = dict(response)
                bad_response.update(patch)

                with self.assertRaisesRegex(ValueError, expected_error):
                    build_query_results(packets, decisions, [bad_response])


if __name__ == "__main__":
    unittest.main()
