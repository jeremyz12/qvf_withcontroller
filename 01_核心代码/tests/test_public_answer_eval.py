from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qvf_validity_admission.public_answer_eval import (
    _build_target_payload_audit,
    _build_condition_scope_context,
    _build_retrieval_feedback,
    _build_source_history_answer_anchor_context,
    _build_source_history_focus_context,
    _build_habit_frequency_context,
    _build_temporal_resolution_context,
    _build_transition_context,
    _completion_token_limit_field,
    _condition_attached_answer_detail,
    _condition_phrase_is_object_only,
    _condition_scope_primary_precision_guard,
    _answer_payloads_equivalent,
    _extract_condition_phrases,
    _extract_income_value,
    _qvf_context,
    _reconcile_current_context_with_transition_context,
    _target_memory_context,
    _target_messages,
    _judge_messages,
    _post_answer_temporal_audit_content,
    _result_row,
    build_public_answer_eval_items,
    load_public_qvf_requests,
    run_public_answer_eval,
    _selective_router_selected_method,
)


class PublicAnswerEvalTests(unittest.TestCase):
    def test_public_answer_eval_items_do_not_put_gold_in_target_prompt(self) -> None:
        items = build_public_answer_eval_items(
            adapter_items=[_adapter_item()],
            qvf_requests=[_qvf_request()],
            limit=1,
        )

        self.assertEqual(len(items), 2)
        rendered_targets = json.dumps(
            [item["target_messages"] for item in items],
            ensure_ascii=False,
        )
        self.assertIn("where should mail go now?", rendered_targets)
        self.assertIn("source_span", rendered_targets)
        self.assertNotIn("SECRET_GOLD_ANSWER", rendered_targets)
        self.assertEqual(items[0]["expected_answers"], ["SECRET_GOLD_ANSWER"])

    def test_public_answer_judge_prompt_gets_memory_context(self) -> None:
        items = build_public_answer_eval_items(
            adapter_items=[_adapter_item()],
            qvf_requests=[_qvf_request()],
            limit=1,
        )
        judge_messages = _judge_messages(
            items[0],
            '{"answer":"Milan","used_memory_ids":["maya_new"],"abstained":false}',
        )
        rendered_judge = json.dumps(judge_messages, ensure_ascii=False)

        self.assertIn("memory_context", rendered_judge)
        self.assertIn("Maya moved to Milan.", rendered_judge)
        self.assertIn("SECRET_GOLD_ANSWER", rendered_judge)

    def test_target_prompt_uses_compact_json_contract(self) -> None:
        messages = _target_messages(
            question="Where should Maya's mail go now?",
            method="direct_extracted_memories",
            context={"extracted_memories": []},
        )
        system_content = messages[0]["content"]

        self.assertIn("one valid compact JSON object", system_content)
        self.assertIn("no markdown", system_content)
        self.assertIn("at most 3 used_memory_ids", system_content)
        self.assertIn("abstained as a boolean", system_content)

    def test_qvf_answer_context_exposes_archive_for_historical_queries(self) -> None:
        items = build_public_answer_eval_items(
            adapter_items=[_historical_adapter_item()],
            qvf_requests=[_historical_qvf_request()],
            limit=1,
        )
        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        context = qvf_item["context"]
        rendered_target = json.dumps(qvf_item["target_messages"], ensure_ascii=False)

        self.assertEqual(context["query_intent"], "historical_recall")
        self.assertEqual(
            context["qvf_read_time_decision"]["answer_policy"],
            "answer_from_archive",
        )
        self.assertEqual(
            context["historical_archive_context"][0]["memory_id"],
            "maya_old",
        )
        self.assertNotIn(
            "maya_old",
            [row["memory_id"] for row in context["stale_or_blocked_context"]],
        )
        self.assertIn("historical_archive_context", rendered_target)
        self.assertNotIn("SECRET_HISTORICAL_ANSWER", rendered_target)

    def test_qvf_answer_context_routes_non_current_memory_roles(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            context = _qvf_context({"request_id": "demo"})

        rendered_target = json.dumps(
            _target_messages(
                question="Where should Maya's mail go now?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(context["routing_version"], "memory_routing_v1")
        self.assertEqual(
            context["current_answer_context"][0]["memory_id"],
            "maya_current",
        )
        self.assertEqual(context["admitted_context"], context["current_answer_context"])
        self.assertEqual(
            context["supporting_context"][0]["memory_id"],
            "maya_supporting",
        )
        self.assertEqual(
            context["uncertain_context"][0]["memory_id"],
            "maya_uncertain",
        )
        self.assertEqual(
            context["stale_or_blocked_context"][0]["memory_id"],
            "maya_stale",
        )
        self.assertNotIn("source_id", context["current_answer_context"][0])
        self.assertIn("supporting_context", rendered_target)
        self.assertIn("uncertain_context", rendered_target)
        self.assertIn("Abstain only if the routed context", rendered_target)

    def test_target_memory_context_omits_repeated_reader_diagnostics_without_override(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            context = _qvf_context(_qvf_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertIn("routing_policy", context)
        self.assertIn("context_control_policy", context)
        self.assertNotIn("routing_policy", target_context)
        self.assertNotIn("context_control_policy", target_context)
        self.assertNotIn("core_qvf_read_time_decision", target_context)
        self.assertNotIn("public_reader_override", target_context)

    def test_qvf_condition_scope_context_preserves_exact_condition(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_condition_scope_qvf_response(),
        ):
            context = _qvf_context(_condition_scope_qvf_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        condition_rows = target_context["condition_scope_context"]
        rendered_target = json.dumps(
            _target_messages(
                question="Under what condition does the user prefer fresh orange juice?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertTrue(condition_rows)
        self.assertEqual(condition_rows[0]["exact_condition"], "before training")
        self.assertIn("condition_scope_context", rendered_target)
        self.assertIn("Do not broaden exact conditions", rendered_target)
        self.assertIn("before training", rendered_target)
        self.assertNotIn("SECRET_CONDITION_ANSWER", rendered_target)

    def test_qvf_answer_rendering_guard_preserves_visible_anchors(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_condition_scope_qvf_response(),
        ):
            context = _qvf_context(_condition_scope_qvf_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question="Under what condition does the user prefer fresh orange juice?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertIn("answer_rendering_guard", target_context)
        rendered_guard = json.dumps(
            target_context["answer_rendering_guard"],
            ensure_ascii=False,
        )
        self.assertIn("answer_rendering_only", rendered_guard)
        self.assertIn("before training", rendered_guard)
        self.assertIn("fresh orange juice", rendered_guard)
        self.assertIn("answer_rendering_guard is not new evidence", rendered_target)
        self.assertNotIn("SECRET_CONDITION_ANSWER", rendered_target)

    def test_qvf_answer_decision_contract_preserves_compound_condition_detail(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "condition_scope_packet",
                "question_fingerprint": "When does the user prefer green vegetable juice?",
            },
            "condition_scope_context": [
                {
                    "memory_id": "green_juice",
                    "exact_condition": "after workouts",
                    "supporting_value": "green vegetable juice",
                    "source_excerpt": (
                        "User likes having a green vegetable juice in the morning "
                        "or after workouts."
                    ),
                }
            ],
        }

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question="When does the user prefer green vegetable juice?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        contract = target_context["answer_decision_contract"]
        rendered_contract = json.dumps(contract, ensure_ascii=False)
        self.assertEqual(contract["contract_rows"][0]["contract_type"], "condition_detail_preservation")
        self.assertIn("in the morning or after workouts", rendered_contract)
        self.assertIn("do not narrow", rendered_contract)
        self.assertIn("answer_decision_contract is not new evidence", rendered_target)

    def test_condition_scope_prefers_direct_claim_value_binding_over_neighbor_span(
        self,
    ) -> None:
        case_id = "condition_direct_priority"
        direct_memory_id = f"{case_id}::direct"
        noisy_memory_id = f"{case_id}::noisy"
        qvf_request = {
            "request_id": f"public_extraction_{case_id}",
            "step_id": f"public_extraction_step_{case_id}",
            "records": [
                {
                    "memory_id": direct_memory_id,
                    "entity": "movie",
                    "slot": "preference",
                    "claim": (
                        "When I need a break and crave high-stakes excitement, "
                        "I watch 'Disaster Masterpiece'."
                    ),
                    "value": "Disaster Masterpiece",
                    "observed_at": "2022-01-17T00:00:00+00:00",
                    "valid_from": "2022-01-17T00:00:00+00:00",
                    "source": {
                        "source_id": "direct",
                        "source_type": "public_history_extraction",
                        "source_span": (
                            "When I need a break and crave high-stakes excitement, "
                            "I watch 'Disaster Masterpiece'."
                        ),
                    },
                    "source_confidence": 1.0,
                },
                {
                    "memory_id": noisy_memory_id,
                    "entity": "movie",
                    "slot": "personal_touch",
                    "claim": (
                        "Fun fact: when I need an adrenaline break I watch "
                        "Disaster Masterpiece."
                    ),
                    "value": "Disaster Masterpiece",
                    "observed_at": "2022-01-17T00:00:00+00:00",
                    "valid_from": "2022-01-17T00:00:00+00:00",
                    "source": {
                        "source_id": "noisy",
                        "source_type": "public_history_extraction",
                        "source_span": (
                            "Fun fact: when I need an adrenaline break I watch "
                            "Disaster Masterpiece in one template to keep it human. "
                            "Anything else to include before I finalize?"
                        ),
                    },
                    "source_confidence": 1.0,
                },
            ],
            "query_requests": [
                {
                    "request_id": f"q_{case_id}",
                    "question": (
                        'When does the user prefer the movie "Disaster Masterpiece"?'
                    ),
                    "entity": "movie",
                    "slot": "preference",
                    "needs_current": False,
                }
            ],
        }
        items = build_public_answer_eval_items(
            adapter_items=[
                {
                    "case_id": case_id,
                    "question": (
                        'When does the user prefer the movie "Disaster Masterpiece"?'
                    ),
                    "answers": ["SECRET_CONDITION_GOLD"],
                }
            ],
            qvf_requests=[qvf_request],
            limit=1,
            qvf_context_variant="post_answer_audit_controller",
        )
        qvf_item = next(
            item for item in items if item["method"] == "qvf_validity_packed_context"
        )
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            qvf_item["context"],
        )

        condition_rows = target_context["condition_scope_context"]
        self.assertEqual(condition_rows[0]["memory_id"], direct_memory_id)
        self.assertIn(
            "when i need a break and crave high stakes excitement",
            condition_rows[0]["exact_condition"],
        )
        rendered_condition_rows = json.dumps(condition_rows, ensure_ascii=False)
        self.assertNotIn("before i finalize", rendered_condition_rows)
        self.assertNotIn("in one template", rendered_condition_rows)

        content = json.dumps(
            {
                "answer": (
                    "The user prefers the movie 'Disaster Masterpiece' "
                    "before finalizing."
                ),
                "used_memory_ids": [noisy_memory_id],
                "abstained": False,
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertIn("need a break", payload["answer"])
        self.assertIn("high stakes excitement", payload["answer"])
        self.assertNotIn("finalize", payload["answer"].lower())
        self.assertNotIn("template", payload["answer"].lower())

    def test_qvf_answer_decision_contract_adds_yes_no_transition_shape(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "timeline_or_conflict_packet",
                "question_fingerprint": "Did the user's marital status change?",
            },
            "transition_context": [
                {
                    "memory_id": "relationship_update",
                    "previous_value": "divorced",
                    "current_value": "seeing someone",
                    "source_excerpt": "The user is divorced and is currently seeing someone.",
                }
            ],
        }

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        contract = target_context["answer_decision_contract"]
        self.assertEqual(
            contract["contract_rows"][0]["contract_type"],
            "yes_no_transition_answer_shape",
        )
        self.assertIn("answer yes/no first", contract["contract_rows"][0]["answer_shape"])
        self.assertIn("avoid_overclaim", contract["contract_rows"][0])

    def test_qvf_computational_contract_adds_aggregate_count_shape(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
                "question_fingerprint": (
                    "How many babies were born to friends and family members "
                    "in the last few months?"
                ),
            },
            "validity_controller_decision": {
                "next_action": "answer_from_archive",
                "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                "suggested_retrieval_scope": {
                    "include_source_history": True,
                    "include_archive": True,
                    "temporal_focus": "historical_or_query_scoped",
                },
            },
            "extracted_memory_context": [
                {
                    "memory_id": "births_0",
                    "claim": "David had a baby boy named Jasper.",
                    "value": "Jasper",
                },
                {
                    "memory_id": "births_1",
                    "claim": "Rachel's son Max was born in March.",
                    "value": "Max",
                },
                {
                    "memory_id": "births_2",
                    "claim": "Mike and Emma welcomed a baby named Charlotte.",
                    "value": "Charlotte",
                },
                {
                    "memory_id": "births_3",
                    "claim": "Aunt's twins, Ava and Lily, were born in April.",
                    "value": "Ava and Lily",
                }
            ],
        }

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question=(
                    "How many babies were born to friends and family members "
                    "in the last few months?"
                ),
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )
        direct_rendered = json.dumps(
            _target_messages(
                question=(
                    "How many babies were born to friends and family members "
                    "in the last few months?"
                ),
                method="direct_extracted_memories",
                context=context,
            ),
            ensure_ascii=False,
        )

        contract = target_context["computational_answer_contract"]
        self.assertEqual(contract["computation_mode"], "aggregate_count")
        self.assertIn("enumerate unique relevant entities", contract["answer_shape"])
        self.assertEqual(
            contract["visible_candidate_items"]["deduplicated_candidate_items"],
            ["Jasper", "Max", "Charlotte", "Ava", "Lily"],
        )
        self.assertIn("computational_answer_contract is not new evidence", rendered_target)
        self.assertNotIn("computational_answer_contract", direct_rendered)

    def test_qvf_computational_contract_adds_elapsed_duration_shape(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
                "question_fingerprint": (
                    "How many days did it take for me to receive the new remote "
                    "shutter release after I ordered it?"
                ),
            },
            "temporal_resolution_context": [
                {
                    "memory_id": "remote_order",
                    "source_excerpt": "I ordered it on February 5 and received it on February 10.",
                }
            ],
        }

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question=(
                    "How many days did it take for me to receive the new remote "
                    "shutter release after I ordered it?"
                ),
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        contract = target_context["computational_answer_contract"]
        self.assertEqual(contract["computation_mode"], "elapsed_duration")
        self.assertIn("start event and end event", contract["answer_shape"])
        self.assertNotIn("compute the elapsed duration", rendered_target)

    def test_direct_target_prompt_has_no_answer_rendering_guard(self) -> None:
        messages = _target_messages(
            question="Under what condition does the user prefer fresh orange juice?",
            method="direct_extracted_memories",
            context={
                "extracted_memories": _condition_scope_qvf_request()["records"],
                "condition_scope_context": [
                    {
                        "memory_id": "orange_exact",
                        "exact_condition": "before training",
                        "preferred_answer": "before training",
                    }
                ],
            },
        )
        rendered_target = json.dumps(messages, ensure_ascii=False)

        self.assertNotIn("answer_rendering_guard", rendered_target)
        self.assertNotIn("answer_decision_contract", rendered_target)

    def test_condition_scope_priority_policy_overrides_competing_archive_route(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_condition_scope_qvf_response(),
        ):
            context = _qvf_context(_condition_scope_qvf_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question="Under what condition does the user prefer fresh orange juice?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(
            target_context["qvf_read_time_decision"]["answer_policy"],
            "answer_from_condition_scope",
        )
        self.assertEqual(
            target_context["qvf_read_time_decision"]["route"],
            "condition_scope_reader",
        )
        self.assertEqual(
            target_context["condition_scope_priority_policy"]["primary_bucket"],
            "condition_scope_context",
        )
        self.assertEqual(
            target_context["core_qvf_read_time_decision"]["answer_policy"],
            "answer_from_current",
        )
        self.assertIn("primary answer route", rendered_target)
        self.assertNotIn("SECRET_CONDITION_ANSWER", rendered_target)

    def test_condition_scope_priority_policy_is_gated_by_question_shape(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_condition_scope_qvf_response(),
        ):
            context = _qvf_context(
                {
                    **_condition_scope_qvf_request(),
                    "query_requests": [
                        {
                            "request_id": "q_recall",
                            "question": "What juice does the user prefer?",
                            "entity": "user",
                            "slot": "juice_preference",
                            "needs_current": False,
                        }
                    ],
                }
            )

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertNotIn("condition_scope_priority_policy", target_context)
        self.assertEqual(
            target_context["qvf_read_time_decision"]["answer_policy"],
            "answer_from_current",
        )

    def test_target_context_quarantines_source_weak_current_rows(self) -> None:
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            {
                "context_type": "qvf_validity_packed_context",
                "qvf_context_variant": "auto_compact",
                "target_compaction_policy": {"mode": "compact"},
                "query_intent": "current_state",
                "qvf_read_time_decision": {
                    "decision": "ADMIT_CURRENT",
                    "answer_policy": "answer_from_current",
                    "route": "current_support_reader",
                },
                "current_answer_context": [
                    {
                        "memory_id": "m_weak_current",
                        "claim": "User's marital status changed recently.",
                        "value": "recently married",
                        "source_span": "I just moved yesterday.",
                    }
                ],
                "uncertain_context": [],
            },
        )

        self.assertEqual(target_context["current_answer_context"], [])
        self.assertEqual(
            target_context["qvf_read_time_decision"]["answer_policy"],
            "insufficient_source_supported_current",
        )
        self.assertEqual(
            target_context["uncertain_context"][0]["retrieval_role"],
            "source_weak_current_quarantine",
        )
        self.assertEqual(
            target_context["source_weak_current_quarantine"]["memory_ids"],
            ["m_weak_current"],
        )

    def test_target_context_keeps_source_supported_current_rows(self) -> None:
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            {
                "context_type": "qvf_validity_packed_context",
                "qvf_context_variant": "auto_compact",
                "target_compaction_policy": {"mode": "compact"},
                "query_intent": "current_state",
                "qvf_read_time_decision": {
                    "decision": "ADMIT_CURRENT",
                    "answer_policy": "answer_from_current",
                    "route": "current_support_reader",
                },
                "current_answer_context": [
                    {
                        "memory_id": "m_supported_current",
                        "value": "just got married",
                        "source_span": "I just got married yesterday.",
                    }
                ],
                "uncertain_context": [],
            },
        )

        self.assertEqual(
            target_context["current_answer_context"][0]["memory_id"],
            "m_supported_current",
        )
        self.assertEqual(
            target_context["qvf_read_time_decision"]["answer_policy"],
            "answer_from_current",
        )
        self.assertNotIn("source_weak_current_quarantine", target_context)

    def test_target_context_reconciles_unknown_when_supported_current_row_is_visible(self) -> None:
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            {
                "context_type": "qvf_validity_packed_context",
                "qvf_context_variant": "post_answer_audit_controller",
                "target_compaction_policy": {"mode": "full"},
                "query_intent": "current_state",
                "qvf_read_time_decision": {
                    "decision": "UNKNOWN_CURRENT",
                    "answer_policy": "insufficient_current_state",
                    "route": "weak_conservative_gate",
                    "validity_controller_decision": {
                        "evidence_sufficiency": "no_visible_answer_evidence",
                        "next_action": "retrieve_entity_slot_timeline",
                        "blocked_as_current_ids": ["m_supported_current"],
                    },
                },
                "current_answer_context": [
                    {
                        "memory_id": "m_supported_current",
                        "claim": "Rachel is currently working at TechCorp.",
                        "value": "TechCorp",
                        "source_span": "Rachel, an old colleague, is currently at TechCorp.",
                    }
                ],
                "uncertain_context": [],
            },
        )

        self.assertEqual(
            target_context["qvf_read_time_decision"]["decision"],
            "ADMIT_CURRENT",
        )
        self.assertEqual(
            target_context["qvf_read_time_decision"]["answer_policy"],
            "answer_from_current",
        )
        self.assertEqual(
            target_context["qvf_read_time_decision"]["validity_controller_decision"][
                "next_action"
            ],
            "answer_from_current",
        )
        self.assertEqual(
            target_context["qvf_read_time_decision"]["validity_controller_decision"].get(
                "blocked_as_current_ids",
                [],
            ),
            [],
        )

    def test_qvf_condition_scope_context_extracts_in_summer_scope(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_summer_condition_scope_qvf_response(),
        ):
            context = _qvf_context(_summer_condition_scope_qvf_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertTrue(target_context["condition_scope_context"])
        self.assertEqual(
            target_context["condition_scope_context"][0]["exact_condition"],
            "in summer",
        )

    def test_condition_preference_source_promotes_retrieved_preference_record(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_practice_schedule_only_qvf_response(),
        ):
            context = _qvf_context(_preference_source_promotion_qvf_request())

        rows = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )["condition_scope_context"]

        self.assertTrue(rows)
        self.assertEqual(rows[0]["scope_type"], "condition_preference_source")
        self.assertEqual(rows[0]["memory_id"], "basketball_preference")
        self.assertEqual(rows[0]["exact_condition"], "in summer")
        self.assertIn("casual pickup games", rows[0]["condition_answer_detail"])
        self.assertIn("keep cardio fun", rows[0]["condition_answer_detail"])

    def test_condition_preference_source_does_not_promote_schedule_only_record(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_practice_schedule_only_qvf_response(),
        ):
            context = _qvf_context(_schedule_only_condition_qvf_request())

        rows = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )["condition_scope_context"]

        self.assertFalse(
            [
                row
                for row in rows
                if row.get("scope_type") == "condition_preference_source"
            ]
        )

    def test_condition_preference_source_extends_parallel_condition_list(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "When does the user prefer reading a business guide?",
                    }
                ],
                "records": [
                    {
                        "memory_id": "business_guide_preference",
                        "entity": "user",
                        "slot": "reading_preference",
                        "claim": (
                            "User finds business guides useful when learning about "
                            "finances, contracts, and planning for the future."
                        ),
                        "value": "business guide",
                        "source_span": (
                            "I often pick up a business guide; I find them useful "
                            "when I'm learning about finances, contracts, and "
                            "planning for the future."
                        ),
                    }
                ],
            },
            [],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["scope_type"], "condition_preference_source")
        self.assertIn("finances", rows[0]["preferred_answer"])
        self.assertIn("contracts", rows[0]["preferred_answer"])
        self.assertIn("planning", rows[0]["preferred_answer"])
        self.assertNotIn("s useful", rows[0].get("condition_answer_detail", ""))

    def test_condition_preference_source_preserves_training_condition_detail(self) -> None:
        records = [
            {
                "memory_id": "german_shepherd_preference",
                "entity": "user",
                "slot": "pet_preference",
                "claim": (
                    "The user half-joked that if they lived in a family "
                    "home and wanted a watchdog, they'd consider a "
                    "protective German Shepherd."
                ),
                "value": "protective German Shepherd",
                "source_span": (
                    "I half-joked that if I lived in a family home and "
                    "wanted a watchdog, I'd consider a protective German "
                    "Shepherd - something that actually follows commands. "
                    "Fair point about wanting a dog that can be trained "
                    "to prevent chaos - sounds like a solid conditional "
                    "plan if you move into a family house and want a "
                    "proper watchdog."
                ),
            },
            {
                "memory_id": "current_apartment",
                "entity": "user",
                "slot": "current_living_situation",
                "claim": (
                    "The user mentioned they live in an apartment right now, "
                    "so getting a big dog isn't really practical."
                ),
                "value": "apartment",
                "source_span": (
                    "I half-joked that if I lived in a family home and "
                    "wanted a watchdog, I'd consider a protective German "
                    "Shepherd - something that actually follows commands. "
                    "Fair point about wanting a dog that can be trained "
                    "to prevent chaos - sounds like a solid conditional "
                    "plan if you move into a family house and want a "
                    "proper watchdog. I do live in an apartment right now, "
                    "so getting a big dog isn't really practical."
                ),
            },
        ]
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "Under what condition would the user prefer a "
                            "protective German Shepherd as a pet?"
                        ),
                    }
                ],
                "records": records,
            },
            records,
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["supporting_value"], "protective German Shepherd")
        rendered_details = " ".join(
            str(row.get("condition_answer_detail", "")) for row in rows
        )
        self.assertIn("trained", rendered_details)
        self.assertIn("prevent chaos", rendered_details)

    def test_condition_preference_source_filters_adjacent_generic_scope(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "When does the user prefer basketball?",
                    }
                ],
                "records": [
                    {
                        "memory_id": "basketball_preference",
                        "entity": "Jackson Andrews",
                        "slot": "interest",
                        "claim": (
                            "Jackson really likes basketball; he loves casual "
                            "pickup games in summer to keep cardio fun."
                        ),
                        "value": "basketball",
                        "source_span": (
                            "Jackson really likes basketball; he loves casual "
                            "pickup games in summer to keep cardio fun."
                        ),
                    }
                ],
            },
            [
                {
                    "memory_id": "nba_group_hint",
                    "entity": "Jackson Andrews",
                    "slot": "recommendation_context",
                    "claim": (
                        "Basketball fans can find NBA meetups in Brisbane or "
                        "sports fan groups."
                    ),
                    "value": "NBA meetups",
                    "source_span": (
                        "For basketball and NBA meetups, try looking in Brisbane "
                        "or sports fan groups."
                    ),
                }
            ],
        )

        self.assertTrue(rows)
        self.assertEqual([row["memory_id"] for row in rows], ["basketball_preference"])
        self.assertEqual(rows[0]["exact_condition"], "in summer")
        rendered = json.dumps(rows, sort_keys=True)
        self.assertNotIn("brisbane", rendered.lower())
        self.assertNotIn("sports fan groups", rendered.lower())

    def test_condition_source_admin_neighbor_yields_to_direct_claim_anchor(self) -> None:
        records = [
            {
                "memory_id": "disaster_direct_preference",
                "claim": (
                    "When I need a break and crave high-stakes excitement, "
                    "I watch Disaster Masterpiece."
                ),
                "value": "Disaster Masterpiece",
                "source": {
                    "source_span": (
                        "When I need a break and crave high-stakes excitement, "
                        "I watch Disaster Masterpiece."
                    )
                },
            },
            {
                "memory_id": "disaster_template_neighbor",
                "claim": (
                    "Fun fact: when I need an adrenaline break I watch "
                    "Disaster Masterpiece."
                ),
                "value": "Disaster Masterpiece",
                "source": {
                    "source_span": (
                        "Yes, I will add a single light sentence like 'Fun fact: "
                        "when I need an adrenaline break I watch Disaster "
                        "Masterpiece' in one template to keep it human. Anything "
                        "else to include before I finalize?"
                    )
                },
            },
        ]
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "When does the user prefer the movie "
                            '"Disaster Masterpiece"?'
                        ),
                    }
                ],
                "records": records,
            },
            records,
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "disaster_direct_preference")
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")
        self.assertEqual(
            rows[0]["exact_condition"],
            "when i need a break and crave high stakes excitement",
        )
        self.assertNotIn(
            "before i finalize",
            [row["exact_condition"] for row in rows],
        )

    def test_condition_scope_phrase_keeps_or_condition(self) -> None:
        phrases = _extract_condition_phrases(
            "I usually unwind by playing story-driven games in the evenings "
            "after grading or on weekends, and I want that protected."
        )

        self.assertIn("in evenings after grading or on weekends", phrases)
        self.assertNotIn("in evenings after grading", phrases)

    def test_condition_scope_uses_nested_source_span_over_purpose_claim(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "When does the user prefer slow reflective dramas?",
                    }
                ]
            },
            [
                {
                    "memory_id": "slow_drama",
                    "claim": (
                        "User prefers slow reflective dramas to help process "
                        "the day without overstimulation."
                    ),
                    "value": "slow reflective dramas",
                    "source": {
                        "source_span": (
                            "When it is quiet, like after the children are "
                            "asleep, I prefer slow reflective dramas - they "
                            "help me process the day without overstimulating me."
                        )
                    },
                    "observed_at": "2022-01-27T00:00:00+00:00",
                    "source_confidence": 0.9,
                }
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(
            rows[0]["exact_condition"],
            "when it is quiet like after the children are asleep",
        )
        self.assertEqual(rows[0]["source_field"], "source.source_span")
        rendered = json.dumps(rows, sort_keys=True)
        self.assertNotIn("during help process", rendered)

    def test_condition_scope_composes_prior_setting_with_condition_qualifier(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "When does the user prefer slow reflective dramas?",
                    }
                ]
            },
            [
                {
                    "memory_id": "slow_drama",
                    "claim": "User prefers slow reflective dramas.",
                    "value": "slow reflective dramas",
                    "source": {
                        "source_span": (
                            "Since you mentioned quiet evenings, choosing a slow "
                            "reflective drama when the children are asleep sounds "
                            "like a good fit."
                        )
                    },
                    "observed_at": "2022-01-27T00:00:00+00:00",
                    "source_confidence": 0.9,
                }
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(
            rows[0]["exact_condition"],
            "on quiet evenings when the children are asleep",
        )
        self.assertEqual(rows[0]["source_field"], "source.source_span")

    def test_condition_scope_guard_does_not_treat_purpose_detail_as_raw_condition(self) -> None:
        guard = _condition_scope_primary_precision_guard(
            question="When does the user prefer slow reflective dramas?",
            condition_scope_context=[
                {
                    "memory_id": "slow_drama",
                    "exact_condition": "on quiet evenings when the children are asleep",
                    "supporting_value": "slow reflective dramas",
                    "source_field": "source_span",
                    "source_excerpt": (
                        "Since you mentioned quiet evenings, choosing a slow "
                        "reflective drama when the children are asleep sounds "
                        "like a good fit."
                    ),
                }
            ],
            extracted_memory_context=[
                {
                    "memory_id": "slow_drama",
                    "claim": (
                        "User prefers slow reflective dramas to help process "
                        "the day without overstimulation."
                    ),
                    "value": "slow reflective dramas",
                    "relevance_score": 4,
                }
            ],
        )

        self.assertEqual(guard["decision"], "KEEP_CONDITION_SCOPE_PRIMARY")
        self.assertEqual(guard["strong_raw_anchor_count"], 0)

    def test_condition_scope_filters_object_only_on_phrase(self) -> None:
        self.assertTrue(
            _condition_phrase_is_object_only(
                "on audiobooks",
                {
                    "claim": "User relies on audiobooks for study.",
                    "value": "rely on audiobooks for study",
                },
            )
        )
        self.assertFalse(
            _condition_phrase_is_object_only(
                "on hot summer days",
                {
                    "claim": "User prefers cold noodles on hot summer days.",
                    "value": "cold noodles",
                },
            )
        )

    def test_condition_scope_attaches_purpose_detail_from_same_source(self) -> None:
        detail = _condition_attached_answer_detail(
            (
                "I commute daily and tend to use audiobooks for professional "
                "self-improvement and technique study while commuting."
            ),
            "while commuting",
            {
                "claim": "User uses audiobooks while commuting.",
                "value": "audiobooks",
            },
        )

        self.assertEqual(
            detail,
            "professional self improvement and technique study",
        )

    def test_condition_scope_ranks_answer_span_over_adjacent_current_routine(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "When does the user prefer city building games?",
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "city_building_routine",
                    "claim": (
                        "User worries that city building game sessions run late "
                        "after a measurable win."
                    ),
                    "value": "game sessions",
                    "source_span": (
                        "The user worries that city building game sessions run "
                        "late after a measurable win."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2025-05-02T00:00:00+00:00",
                },
                {
                    "memory_id": "city_building_preference",
                    "claim": (
                        "User prefers city building games after school for "
                        "focused play."
                    ),
                    "value": "city building games",
                    "source_span": (
                        "After school I prefer city building games for focused "
                        "play."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                    "observed_at": "2025-04-01T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "city_building_preference")
        self.assertEqual(rows[0]["exact_condition"], "after school")

    def test_condition_scope_promotes_direct_claim_to_meetings_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "Under what condition does the user prefer Hot Pu-erh tea?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "puerh_meetings",
                    "claim": "User prefers to bring Hot Pu-erh tea to meetings.",
                    "value": "Hot Pu-erh tea",
                    "source_span": (
                        "Story-driven games work well for me after grading, "
                        "and I tend to bring hot Pu-erh tea to meetings."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["exact_condition"], "during meetings")
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")

    def test_condition_scope_direct_anchor_survives_target_leaking_source_span(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "Under what condition does the user prefer Hot Pu-erh tea?"}
                ],
                "records": [
                    {
                        "memory_id": "puerh_meetings",
                        "claim": "User prefers to bring Hot Pu-erh tea to meetings.",
                        "value": "Hot Pu-erh tea",
                        "source": {
                            "source_span": (
                                "Like I said, story-driven games work well for me "
                                "on weekends or evenings after grading, and I tend "
                                "to bring hot Pu-erh tea to meetings."
                            )
                        },
                        "source_confidence": 0.9,
                    }
                ],
            },
            [
                {
                    "memory_id": "puerh_meetings",
                    "claim": "User prefers to bring Hot Pu-erh tea to meetings.",
                    "value": "Hot Pu-erh tea",
                    "source_span": (
                        "Like I said, story-driven games work well for me on "
                        "weekends or evenings after grading, and I tend to bring "
                        "hot Pu-erh tea to meetings."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["exact_condition"], "during meetings")
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")

    def test_condition_scope_direct_claim_accepts_formal_event_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "When does the user prefer an elegant evening dress?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "gallery_dress",
                    "claim": (
                        "User has an elegant evening dress they keep for special "
                        "gallery events."
                    ),
                    "value": "elegant evening dress",
                    "source_span": (
                        "I have an elegant evening dress I keep for special "
                        "gallery events."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                }
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["exact_condition"], "for special gallery events")
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")

    def test_condition_scope_preserves_stronger_direct_anchor_sibling(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "When does the user prefer an elegant evening dress?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "gallery_dress",
                    "claim": (
                        "User has an elegant evening dress they keep for special "
                        "gallery events."
                    ),
                    "value": "elegant evening dress",
                    "source_span": (
                        "I have an elegant evening dress I keep for special "
                        "gallery events."
                    ),
                    "current_status": "superseded",
                    "retrieval_role": "historical_evidence",
                },
                {
                    "memory_id": "presentation_dress",
                    "claim": "User has an elegant dress ready for a formal presentation.",
                    "value": "elegant dress ready",
                    "source_span": (
                        "The idea of a formal presentation is tempting, which is "
                        "why I have that elegant dress ready."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
            ],
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {
                "for special gallery events",
                "for a formal presentation",
            },
            {row["exact_condition"] for row in rows},
        )
        self.assertTrue(
            all(row["scope_type"] == "condition_direct_claim_anchor" for row in rows)
        )

    def test_condition_scope_direct_anchor_suppresses_weaker_secondary_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "Under what condition does the user prefer Hot Pu-erh tea?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "puerh_meetings",
                    "claim": "User prefers to bring Hot Pu-erh tea to meetings.",
                    "value": "Hot Pu-erh tea",
                    "source_span": "I bring hot Pu-erh tea to meetings.",
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                },
                {
                    "memory_id": "puerh_tasting",
                    "claim": "User considers Pu-erh for a tea-tasting evening.",
                    "value": "Pu-erh",
                    "source_span": "Maybe use Pu-erh for a tea tasting evening.",
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                },
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["memory_id"], "puerh_meetings")
        self.assertEqual(rows[0]["exact_condition"], "during meetings")

    def test_condition_scope_rejects_meta_checklist_anchor_over_exact_condition(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "Under what condition does the user prefer fresh "
                            "orange juice?"
                        )
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "orange_before_training",
                    "claim": (
                        "User usually has fresh orange juice as a quick morning "
                        "boost before training."
                    ),
                    "value": "fresh",
                    "source_span": (
                        "Before training I usually have fresh orange juice as a "
                        "quick morning boost."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
                {
                    "memory_id": "orange_schedule_meta",
                    "claim": (
                        "User wants the morning item to explicitly reflect their "
                        "training schedule and include the orange juice boost on "
                        "training days."
                    ),
                    "value": "fresh",
                    "source_span": (
                        "I would like the morning item to explicitly reflect my "
                        "training schedule and include the orange juice boost on "
                        "training days."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "orange_before_training")
        self.assertEqual(rows[0]["exact_condition"], "before training")
        self.assertNotIn(
            "during morning item to explicitly reflect training schedule",
            [row["exact_condition"] for row in rows],
        )

    def test_condition_scope_prefers_exact_event_boundary_over_broad_schedule(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "Under what condition does the user prefer fresh "
                            "orange juice?"
                        )
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "orange_training_days",
                    "claim": (
                        "User prefers to have fresh orange juice as a boost on "
                        "training days."
                    ),
                    "value": "fresh",
                    "source_span": (
                        "I train mornings and use fresh orange juice as a boost "
                        "on training days."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
                {
                    "memory_id": "orange_before_training",
                    "claim": (
                        "User usually has fresh orange juice as a quick morning "
                        "boost before training."
                    ),
                    "value": "fresh",
                    "source_span": (
                        "Before training I usually have fresh orange juice as a "
                        "quick morning boost."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "orange_before_training")
        self.assertEqual(rows[0]["exact_condition"], "before training")

    def test_condition_scope_promotes_direct_claim_after_target_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "When does the user prefer a waterproof raincoat?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "raincoat_commute",
                    "claim": (
                        "User relies on a waterproof raincoat while commuting "
                        "in rainy weather."
                    ),
                    "value": "waterproof raincoat",
                    "source_span": (
                        "My days are routine: commute into the city for work, "
                        "desk job most of the day. When it's raining I usually "
                        "rely on a waterproof raincoat while commuting in rainy "
                        "weather so I don't get soaked."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                }
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")
        self.assertEqual(rows[0]["exact_condition"], "while commuting in rainy weather")
        self.assertNotIn(
            "work desk job",
            " ".join(str(row.get("condition_answer_detail", "")) for row in rows),
        )

    def test_condition_scope_promotes_direct_claim_compound_condition(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "Under what condition does the user prefer cold noodles?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "cold_noodles_shoots",
                    "claim": (
                        "User tends to crave cold noodles after long outdoor "
                        "shoots and on hot summer days."
                    ),
                    "value": "cold noodles",
                    "source_span": (
                        "After long outdoor shoots I tend to crave cold noodles "
                        "- they're my go-to on hot summer days or right after a "
                        "busy shoot."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
                {
                    "memory_id": "cold_noodles_warm_day",
                    "claim": "User likes the idea of having cold noodles if it's warm.",
                    "value": "cold noodles",
                    "source_span": (
                        "I could also do cold noodles if it's warm that day - "
                        "sounds quirky and sweet."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")
        self.assertEqual(
            rows[0]["exact_condition"],
            "after long outdoor shoots and on hot summer days",
        )

    def test_condition_scope_completes_suffix_alternative_in_direct_claim(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "When does the user prefer a breathable gym tank?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "gym_tank",
                    "claim": (
                        "User prefers a breathable gym tank when going for a "
                        "morning run or on a hot summer day."
                    ),
                    "value": "breathable gym tank",
                    "source_span": (
                        "I prefer a breathable gym tank when I go for a morning "
                        "run or on a hot summer day."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2022-03-16T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["scope_type"], "condition_direct_claim_anchor")
        self.assertEqual(
            rows[0]["exact_condition"],
            "when going for a morning run or on a hot summer day",
        )

    def test_condition_scope_prefers_same_date_fuller_compound_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "When does the user prefer story-driven games?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "story_games_full",
                    "claim": (
                        "User usually unwinds by playing story-driven games in "
                        "the evenings after grading or on weekends."
                    ),
                    "value": "story-driven games",
                    "source_span": (
                        "I usually unwind by playing story-driven games in the "
                        "evenings after grading or on weekends."
                    ),
                    "current_status": "superseded",
                    "retrieval_role": "historical_evidence",
                    "observed_at": "2023-05-25T00:00:00+00:00",
                },
                {
                    "memory_id": "story_games_weekend",
                    "claim": (
                        "User and Carol both enjoy story-driven things on weekends."
                    ),
                    "value": "cooperative story-driven games",
                    "source_span": (
                        "Carol and I both enjoy story-driven things on weekends."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2023-05-25T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "story_games_full")
        self.assertEqual(
            rows[0]["exact_condition"],
            "in evenings after grading or on weekends",
        )

    def test_condition_scope_promotes_activity_condition_over_side_task(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            'When does the user prefer an "Evening Walk" as '
                            "their sport preference?"
                        )
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "evening_walk_preference",
                    "claim": (
                        "The user started taking an evening walk after work to "
                        "decompress and plan the next day."
                    ),
                    "value": "Evening Walk",
                    "source_span": (
                        "I usually do my evening walk after work to decompress "
                        "and plan the next day."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
                {
                    "memory_id": "call_mum_timing",
                    "claim": (
                        "The user prefers to call their mum after their evening "
                        "walk around 7:30 PM."
                    ),
                    "value": "7:30 PM",
                    "source_span": (
                        "For timing: I usually do my evening walk after work "
                        "to decompress, so calling my mum after that around "
                        "7:30pm works for me."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "evening_walk_preference")
        self.assertEqual(
            rows[0]["exact_condition"],
            "after work",
        )

    def test_condition_scope_promotes_condition_before_target_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": "When does the user prefer cold noodles?"}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "cold_noodles_sessions",
                    "claim": (
                        "User mentioned that late-night study sessions at Lee "
                        "University usually involved a bowl of cold noodles."
                    ),
                    "value": "cold noodles",
                    "source_span": (
                        "I want to celebrate after the first week with cold noodles, "
                        "like old times from my Lee University study days."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(
            rows[0]["exact_condition"],
            "during late night study sessions at lee university",
        )

    def test_condition_scope_promotes_to_read_target_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {"question": 'When does the user prefer reading "Academic Journal"?'}
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "academic_journal_commutes",
                    "claim": (
                        "User uses long commutes or weekends to read academic "
                        "journals to stay updated on industry trends."
                    ),
                    "value": "Academic Journal",
                    "source_span": (
                        "I have been shifting reading to hotel evenings while "
                        "hopping between cities."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["exact_condition"], "during long commutes or weekends")

    def test_condition_scope_preserves_direct_for_or_on_compound_anchor(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "Under what condition does the user prefer "
                            "Action/Superhero movies?"
                        )
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "action_superhero",
                    "claim": (
                        "User prefers Action / Superhero movies for high-energy "
                        "entertainment or on long flights."
                    ),
                    "value": "Action / Superhero",
                    "source_span": (
                        "If I want entertainment later tonight, I tend to go for "
                        "Action / Superhero movies when I want high-energy "
                        "entertainment or on long flights."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(
            rows[0]["exact_condition"],
            "for high energy entertainment or on long flights",
        )

    def test_condition_scope_keeps_leading_environment_for_when_clause(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "When does the user prefer short philosophy texts?"
                        ),
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "philosophy_preference",
                    "claim": (
                        "User prefers short philosophy texts on quiet mornings "
                        "when doing professional development."
                    ),
                    "value": "short philosophy texts",
                    "source_span": (
                        "I prefer short philosophy texts on quiet mornings when "
                        "I'm doing professional development."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2025-05-01T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(
            rows[0]["exact_condition"],
            "on quiet mornings when i m doing professional development",
        )

    def test_condition_scope_requires_specific_target_overlap_for_multiword_target(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "When does the user prefer slow reflective dramas?"
                        ),
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "generic_drama_preference",
                    "claim": (
                        "User prefers family and historical dramas after dinner."
                    ),
                    "value": "family and historical dramas",
                    "source_span": (
                        "The user prefers family and historical dramas after "
                        "dinner."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2025-05-02T00:00:00+00:00",
                },
                {
                    "memory_id": "slow_reflective_preference",
                    "claim": (
                        "User prefers slow reflective dramas when it is quiet."
                    ),
                    "value": "slow reflective dramas",
                    "source_span": (
                        "I prefer slow reflective dramas when it's quiet, like "
                        "after the children are asleep."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                    "observed_at": "2025-04-01T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "slow_reflective_preference")
        self.assertEqual(
            rows[0]["exact_condition"],
            "when it is quiet like after the children are asleep",
        )
        self.assertNotIn(
            "generic_drama_preference",
            [row["memory_id"] for row in rows],
        )

    def test_condition_scope_does_not_merge_recovery_preference_with_adjacent_routine(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "When does the user prefer fruit salad?",
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "fruit_outreach_routine",
                    "claim": (
                        "User plans to prepare fruit salad before reaching out "
                        "to others."
                    ),
                    "value": "fruit salad",
                    "source_span": (
                        "I can make fruit salad before reaching out to others "
                        "later."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2025-05-02T00:00:00+00:00",
                },
                {
                    "memory_id": "fruit_recovery_preference",
                    "claim": (
                        "User prefers fruit salad after workouts because it is "
                        "light and refreshing."
                    ),
                    "value": "fruit salad",
                    "source_span": (
                        "After workouts I prefer fruit salad because it is light "
                        "and refreshing."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                    "observed_at": "2025-04-01T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "fruit_recovery_preference")
        self.assertEqual(rows[0]["exact_condition"], "after workouts")

    def test_condition_scope_duplicate_phrase_prefers_answer_detail_span(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": "Under what condition does the user prefer audiobooks?",
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "audiobook_low_detail",
                    "claim": "User keeps using audiobooks while commuting.",
                    "value": "audiobooks",
                    "source_span": "I keep using audiobooks while commuting.",
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2025-05-02T00:00:00+00:00",
                },
                {
                    "memory_id": "audiobook_answer_detail",
                    "claim": (
                        "User tends to use audiobooks for professional "
                        "self-improvement and technique study while commuting."
                    ),
                    "value": (
                        "for professional self-improvement and technique study "
                        "while commuting"
                    ),
                    "source_span": (
                        "I commute daily and tend to use audiobooks for "
                        "professional self-improvement and technique study while "
                        "commuting."
                    ),
                    "current_status": "historical",
                    "retrieval_role": "historical_support",
                    "observed_at": "2025-04-01T00:00:00+00:00",
                },
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "audiobook_answer_detail")
        self.assertEqual(rows[0]["exact_condition"], "while commuting")
        self.assertIn("professional self improvement", rows[0]["condition_answer_detail"])

    def test_condition_scope_attaches_same_clause_continuation_detail(self) -> None:
        detail = _condition_attached_answer_detail(
            (
                "I often pick up a business guide; I find them useful when "
                "I'm learning about finances, contracts, and planning for "
                "the future. Maybe a hike after that."
            ),
            "when i m learning about finances",
            {
                "claim": (
                    "User finds business guides useful when learning about "
                    "finances, contracts, and planning for the future."
                ),
                "value": "business guide",
            },
        )

        self.assertEqual(detail, "contracts and planning future")

    def test_condition_scope_continuation_ignores_to_purpose_tail(self) -> None:
        detail = _condition_attached_answer_detail(
            (
                "Jackson really likes basketball; he loves casual pickup "
                "games in summer to keep cardio fun, and Maya likes art."
            ),
            "in summer",
            {
                "claim": "Jackson likes basketball in summer.",
                "value": "basketball",
            },
        )

        self.assertEqual(detail, "")

    def test_condition_scope_preserves_target_adjacent_descriptor_detail(self) -> None:
        rows = _build_condition_scope_context(
            {
                "query_requests": [
                    {
                        "question": (
                            "Under what condition does the user prefer a "
                            '"Cuddly Ragdoll Cat" as a pet?'
                        ),
                    }
                ],
                "records": [],
            },
            [
                {
                    "memory_id": "ragdoll_companion",
                    "entity": "user",
                    "slot": "pet_preference",
                    "claim": (
                        "User is thinking about getting a cuddly Ragdoll cat, "
                        "something calm and indoor to curl up with during "
                        "reading and writing."
                    ),
                    "value": "Cuddly Ragdoll Cat",
                    "source_span": (
                        "Small comforts help - I've been thinking a lot "
                        "about getting a cuddly Ragdoll cat, something "
                        "calm and indoor to curl up with during reading "
                        "and writing."
                    ),
                    "current_status": "current",
                    "retrieval_role": "current_support",
                    "observed_at": "2023-08-12T00:00:00+00:00",
                    "source_confidence": 0.9,
                }
            ],
        )

        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], "ragdoll_companion")
        self.assertEqual(rows[0]["exact_condition"], "during reading and writing")
        self.assertIn("calm and indoor", rows[0]["condition_answer_detail"])
        self.assertIn("curl up", rows[0]["condition_answer_detail"])

    def test_qvf_answer_prompt_preserves_condition_value_and_detail(self) -> None:
        rendered_target = json.dumps(
            _target_messages(
                question="When does the user prefer watching esports?",
                method="qvf_validity_packed_context",
                context={
                    "context_type": "qvf_validity_packed_context",
                    "qvf_context_variant": "annotation_only_qvf",
                    "condition_scope_context": [
                        {
                            "memory_id": "esports_background",
                            "exact_condition": "when decompressing",
                            "supporting_value": "esports streams as background",
                            "condition_answer_detail": "relaxed background activity",
                        }
                    ],
                    "evidence_preservation_policy": {
                        "routing_mode": "preserve_first",
                    },
                    "annotation_policy": {
                        "mode": "always_on_annotation",
                    },
                },
            ),
            ensure_ascii=False,
        )

        self.assertIn("Preserve", rendered_target)
        self.assertIn("condition_scope_context.supporting_value", rendered_target)
        self.assertIn("condition_answer_detail", rendered_target)
        self.assertIn("answer-critical descriptors", rendered_target)

    def test_qvf_habit_frequency_context_preserves_source_cadence(self) -> None:
        request = _tennis_frequency_qvf_request()
        rows = _build_habit_frequency_context(
            request,
            list(request["records"]),
        )
        rendered_rows = json.dumps(rows, ensure_ascii=False)

        self.assertIn("weekly", rendered_rows)
        self.assertIn("every other week", rendered_rows)
        self.assertIn("Sunday", rendered_rows)
        self.assertTrue(
            all(row["context_type"] == "habit_frequency" for row in rows)
        )
        by_phrase = {row["frequency_phrase"]: row for row in rows}
        self.assertEqual(by_phrase["weekly"]["answer_slot"], "previous_frequency")
        self.assertEqual(
            by_phrase["every other week"]["answer_slot"],
            "current_frequency",
        )

        rendered_target = json.dumps(
            _target_messages(
                question=str(request["query_requests"][0]["question"]),
                method="qvf_validity_packed_context",
                context={
                    "context_type": "qvf_validity_packed_context",
                    "qvf_context_variant": "post_answer_audit_controller",
                    "habit_frequency_context": rows,
                    "evidence_preservation_policy": {
                        "routing_mode": "route_first",
                    },
                    "memory_validity_controller_action": {
                        "action": "timeline_or_conflict_packet",
                        "primary_context_order": [
                            "habit_frequency_context",
                            "extracted_memory_context",
                        ],
                    },
                },
            ),
            ensure_ascii=False,
        )

        self.assertIn("habit_frequency_context", rendered_target)
        self.assertIn("Preserve frequency_phrase", rendered_target)
        self.assertIn("answer_slot", rendered_target)
        self.assertIn("do not invert previous/current roles", rendered_target)
        self.assertIn("every other week", rendered_target)

    def test_qvf_habit_frequency_context_does_not_trigger_for_transport_recency(self) -> None:
        request = _transport_recency_qvf_request()
        rows = _build_habit_frequency_context(
            request,
            list(request["records"]),
        )

        self.assertEqual(rows, [])

    def test_qvf_habit_frequency_context_does_not_force_roles_for_plain_frequency(self) -> None:
        request = _tennis_frequency_qvf_request()
        request["query_requests"][0]["question"] = (
            "How often does the user play tennis with friends?"
        )
        rows = _build_habit_frequency_context(
            request,
            list(request["records"]),
        )

        self.assertTrue(rows)
        self.assertNotIn("answer_slot", json.dumps(rows, ensure_ascii=False))

    def test_qvf_condition_scope_context_deprioritizes_reminder_noise(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_cold_noodles_condition_scope_qvf_response(),
        ):
            context = _qvf_context(_cold_noodles_condition_scope_qvf_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        conditions = [
            row["exact_condition"]
            for row in target_context["condition_scope_context"]
        ]

        self.assertIn("after long outdoor shoots", conditions)
        self.assertIn("on hot summer days", conditions)
        self.assertNotIn("after busy shoot", conditions)
        self.assertNotIn("before planning reminder", conditions)

    def test_qvf_condition_scope_uses_raw_extracted_direct_anchor(self) -> None:
        request = {
            "request_id": "public_extraction_raw_condition_anchor",
            "records": [
                {
                    "memory_id": "cold_noodles_sessions",
                    "entity": "user",
                    "slot": "meal_preference",
                    "claim": (
                        "User mentioned that late-night study sessions at Lee "
                        "University usually involved a bowl of cold noodles."
                    ),
                    "value": "cold noodles",
                    "observed_at": "2022-05-06T00:00:00+00:00",
                    "source": {
                        "source_type": "public_history_extraction",
                        "source_span": (
                            "Late-night study sessions at Lee University usually "
                            "involved a bowl of cold noodles."
                        ),
                    },
                    "source_confidence": 0.9,
                },
                {
                    "memory_id": "cold_noodles_first_week",
                    "entity": "user",
                    "slot": "meal_preference",
                    "claim": (
                        "User plans to celebrate after the first week with cold "
                        "noodles like old times."
                    ),
                    "value": "cold noodles",
                    "observed_at": "2025-05-01T00:00:00+00:00",
                    "source": {
                        "source_type": "public_history_extraction",
                        "source_span": (
                            "I want to celebrate after the first week with cold "
                            "noodles, like old times."
                        ),
                    },
                    "source_confidence": 0.9,
                },
            ],
            "query_requests": [
                {
                    "request_id": "q_raw_condition_anchor",
                    "question": "When does the user prefer cold noodles?",
                    "entity": "user",
                    "slot": "meal_preference",
                    "needs_current": False,
                }
            ],
        }
        response = _routed_qvf_response(query_intent="historical_recall")
        packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
        packet["compact_validity_packet"]["current_evidence"] = [
            _evidence_row(
                "cold_noodles_first_week",
                "User plans to celebrate after the first week with cold noodles like old times.",
                "cold noodles",
                "I want to celebrate after the first week with cold noodles, like old times.",
                "current_support",
                observed_at="2025-05-01T00:00:00+00:00",
            )
        ]
        packet["compact_validity_packet"]["supporting_evidence"] = []
        packet["compact_validity_packet"]["historical_evidence"] = []
        packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
        packet["compact_validity_packet"]["excluded_memory_summary"] = []

        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=response,
        ):
            context = _qvf_context(
                request,
                qvf_context_variant="annotation_only_qvf",
            )

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        condition_rows = target_context["condition_scope_context"]

        self.assertTrue(condition_rows)
        self.assertEqual(
            condition_rows[0]["memory_id"],
            "cold_noodles_sessions",
        )
        self.assertEqual(
            condition_rows[0]["exact_condition"],
            "during late night study sessions at lee university",
        )
        self.assertEqual(
            condition_rows[0]["scope_type"],
            "condition_direct_claim_anchor",
        )

    def test_qvf_answer_context_evidence_preserving_keeps_original_records_with_labels(self) -> None:
        context = _qvf_context(
            _qvf_request(),
            qvf_context_variant="evidence_preserving",
        )
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rows_by_id = {
            row["memory_id"]: row
            for row in target_context["extracted_memory_context"]
        }
        rendered_target = json.dumps(
            _target_messages(
                question="Since Maya still lives in Rome, where should mail go now?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(context["qvf_context_variant"], "evidence_preserving")
        self.assertEqual(
            context["evidence_preservation_policy"]["mode"],
            "preserve_extracted_records_with_qvf_labels",
        )
        self.assertEqual(
            context["evidence_preservation_policy"]["routing_mode"],
            "preserve_first",
        )
        self.assertEqual(rows_by_id["maya_new"]["qvf_route_label"], "current_answer")
        self.assertEqual(rows_by_id["maya_old"]["qvf_route_label"], "stale_or_blocked")
        self.assertIn("Maya moved to Milan.", rows_by_id["maya_new"]["source_span"])
        self.assertIn("do not use as current fact", rows_by_id["maya_old"]["qvf_use_policy"])
        self.assertIn("extracted_memory_context", rendered_target)
        self.assertIn("qvf_route_label", rendered_target)

    def test_qvf_answer_context_annotation_only_keeps_raw_records_as_non_filtering_annotations(self) -> None:
        context = _qvf_context(
            _qvf_request(),
            qvf_context_variant="annotation_only_qvf",
        )
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rows_by_id = {
            row["memory_id"]: row
            for row in target_context["extracted_memory_context"]
        }
        rendered_target = json.dumps(
            _target_messages(
                question="Since Maya still lives in Rome, where should mail go now?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(context["qvf_context_variant"], "annotation_only_qvf")
        self.assertEqual(
            context["evidence_preservation_policy"]["mode"],
            "annotation_only_preserve_all_extracted_records",
        )
        self.assertEqual(
            target_context["annotation_policy"]["mode"],
            "always_on_annotation",
        )
        self.assertIn(
            target_context["validity_controller_decision"]["next_action"],
            {
                "answer_from_current",
                "correct_premise_then_answer_from_current",
                "retrieve_current_entity_slot",
            },
        )
        self.assertIn("maya_new", rows_by_id)
        self.assertIn("maya_old", rows_by_id)
        self.assertEqual(rows_by_id["maya_new"]["qvf_route_label"], "current_answer")
        self.assertEqual(rows_by_id["maya_old"]["qvf_route_label"], "stale_or_blocked")
        self.assertIn("annotation layer, not a filter", rendered_target)
        self.assertIn("do not discard extracted_memory_context", rendered_target)
        self.assertIn("validity_controller_decision", rendered_target)
        self.assertIn("do not let current_answer_context override", rendered_target)
        self.assertNotIn("Answer from QVF-routed memory", rendered_target)
        self.assertNotIn("SECRET_GOLD_ANSWER", rendered_target)

    def test_multi_action_controller_uses_raw_recall_action_for_plain_recall(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            context = _qvf_context(
                _plain_recall_qvf_request(),
                qvf_context_variant="multi_action_controller",
            )

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question="What activity is Melanie planning?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(context["qvf_context_variant"], "multi_action_controller")
        self.assertEqual(
            target_context["memory_validity_controller_action"]["action"],
            "raw_recall_with_annotations",
        )
        self.assertEqual(
            context["evidence_preservation_policy"]["mode"],
            "multi_action_preserve_extracted_records_with_qvf_labels",
        )
        self.assertTrue(target_context["extracted_memory_context"])
        self.assertIn("memory_validity_controller_action", rendered_target)
        self.assertIn("action is raw_recall_with_annotations", rendered_target)
        self.assertIn("annotation layer, not a filter", rendered_target)

    def test_multi_action_controller_uses_condition_packet_for_condition_scope(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_condition_scope_qvf_response(),
        ):
            context = _qvf_context(
                _condition_scope_qvf_request(),
                qvf_context_variant="multi_action_controller",
            )

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertEqual(
            target_context["memory_validity_controller_action"]["action"],
            "condition_scope_packet",
        )
        self.assertIn(
            "condition_scope_context",
            target_context["memory_validity_controller_action"]["primary_context_order"],
        )
        self.assertTrue(target_context["condition_scope_context"])
        self.assertTrue(target_context["extracted_memory_context"])

    def test_multi_action_controller_uses_stale_current_packet_for_current_conflict(self) -> None:
        context = _qvf_context(
            _qvf_request(),
            qvf_context_variant="multi_action_controller",
        )
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rows_by_id = {
            row["memory_id"]: row
            for row in target_context["extracted_memory_context"]
        }

        self.assertEqual(
            target_context["memory_validity_controller_action"]["action"],
            "stale_current_validity_packet",
        )
        self.assertIn(
            "stale_or_blocked rows are usable as history but never as current facts",
            target_context["memory_validity_controller_action"]["stale_current_rule"],
        )
        self.assertEqual(rows_by_id["maya_new"]["qvf_route_label"], "current_answer")
        self.assertEqual(rows_by_id["maya_old"]["qvf_route_label"], "stale_or_blocked")
        self.assertIn("do not use as current fact", rows_by_id["maya_old"]["qvf_use_policy"])

    def test_retrieval_feedback_requests_current_evidence_when_controller_retrieves(self) -> None:
        feedback = _build_retrieval_feedback(
            question="Since Maya still lives in Rome, where should mail go now?",
            model_read_decision={
                "decision": "UNKNOWN_CURRENT",
                "answer_policy": "correct_premise_only",
            },
            validity_controller_decision={
                "evidence_sufficiency": (
                    "stale_premise_without_answerable_current_evidence"
                ),
                "next_action": "retrieve_current_entity_slot",
                "query_rewrite": "Maya home_city current",
                "suggested_retrieval_scope": {
                    "entity": "Maya",
                    "slot": "home_city",
                    "temporal_focus": "current",
                    "include_current": True,
                },
                "blocked_as_current_ids": ["maya_old"],
                "allowed_as_history_ids": ["maya_old"],
            },
            memory_validity_controller_action={
                "action": "stale_current_validity_packet",
            },
            condition_scope_priority_policy={},
            current_context=[],
            historical_context=[],
            stale_or_blocked_context=[{"memory_id": "maya_old"}],
            transition_context=[],
            temporal_resolution_context=[],
            condition_scope_context=[],
            extracted_memory_context=[{"memory_id": "maya_old"}],
        )

        self.assertEqual(feedback["status"], "needs_additional_retrieval")
        self.assertEqual(feedback["primary_issue_type"], "missing_current_evidence")
        self.assertEqual(
            feedback["issues"][0]["required_retrieval"]["retrieve"],
            "source_backed_entity_slot_current_evidence",
        )
        self.assertIn("maya_old", feedback["issues"][0]["must_not_use_as_current_ids"])

    def test_retrieval_feedback_marks_condition_guard_as_advisory(self) -> None:
        feedback = _build_retrieval_feedback(
            question="When does the user prefer a mango milkshake?",
            model_read_decision={},
            validity_controller_decision={
                "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                "next_action": "answer_from_archive",
                "suggested_retrieval_scope": {
                    "entity": "user",
                    "slot": "drink_preference",
                    "temporal_focus": "historical_or_query_scoped",
                },
            },
            memory_validity_controller_action={
                "action": "raw_recall_with_annotations",
                "condition_scope_primary_precision_guard": {
                    "decision": "DEMOTE_CONDITION_SCOPE_PRIMARY",
                    "risk_rows": [{"memory_id": "m1"}],
                },
            },
            condition_scope_priority_policy={
                "decision": "PROMOTE_CONDITION_SCOPE_PRIMARY",
            },
            current_context=[],
            historical_context=[],
            stale_or_blocked_context=[],
            transition_context=[],
            temporal_resolution_context=[],
            condition_scope_context=[{"memory_id": "m1"}],
            extracted_memory_context=[{"memory_id": "m1"}],
        )

        self.assertEqual(feedback["status"], "advisory_only")
        self.assertEqual(
            feedback["primary_issue_type"],
            "condition_scope_evidence_unsupported",
        )
        self.assertEqual(feedback["issues"][0]["guard_risk_count"], 1)

    def test_retrieval_feedback_requests_change_pair_for_unpaired_change_query(self) -> None:
        feedback = _build_retrieval_feedback(
            question="What changed about the user's job title?",
            model_read_decision={
                "decision": "ADMIT_CURRENT",
                "answer_policy": "answer_from_current",
            },
            validity_controller_decision={
                "evidence_sufficiency": "sufficient_current_evidence",
                "next_action": "answer_from_current",
            },
            memory_validity_controller_action={
                "action": "raw_recall_with_annotations",
            },
            condition_scope_priority_policy={},
            current_context=[{"memory_id": "job_new"}],
            historical_context=[],
            stale_or_blocked_context=[],
            transition_context=[],
            temporal_resolution_context=[],
            condition_scope_context=[],
            extracted_memory_context=[{"memory_id": "job_new"}],
        )

        self.assertEqual(feedback["status"], "needs_additional_retrieval")
        self.assertEqual(
            feedback["primary_issue_type"],
            "missing_change_pair_evidence",
        )
        self.assertEqual(
            feedback["issues"][0]["required_retrieval"]["retrieve"],
            "source_backed_previous_current_change_pair",
        )
        self.assertEqual(
            feedback["issues"][0]["required_retrieval"]["scope"]["target_group"],
            "job_title",
        )

    def test_retrieval_feedback_is_not_emitted_when_current_evidence_is_sufficient(self) -> None:
        feedback = _build_retrieval_feedback(
            question="Where does Maya currently live?",
            model_read_decision={
                "decision": "ADMIT_CURRENT",
                "answer_policy": "answer_from_current",
            },
            validity_controller_decision={
                "evidence_sufficiency": "sufficient_current_evidence",
                "next_action": "answer_from_current",
            },
            memory_validity_controller_action={
                "action": "stale_current_validity_packet",
            },
            condition_scope_priority_policy={},
            current_context=[{"memory_id": "maya_new"}],
            historical_context=[],
            stale_or_blocked_context=[{"memory_id": "maya_old"}],
            transition_context=[],
            temporal_resolution_context=[],
            condition_scope_context=[],
            extracted_memory_context=[
                {"memory_id": "maya_new"},
                {"memory_id": "maya_old"},
            ],
        )

        self.assertEqual(feedback, {})

    def test_retrieval_feedback_is_model_visible_but_not_answer_evidence(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "target_compaction_policy": {"mode": "full"},
            "query_intent": "current_state",
            "qvf_read_time_decision": {
                "decision": "UNKNOWN_CURRENT",
                "answer_policy": "insufficient_current_state",
            },
            "memory_validity_controller_action": {
                "action": "stale_current_validity_packet",
            },
            "retrieval_feedback": {
                "feedback_version": "qvf_retrieval_feedback_v0.1",
                "scope": "system_retrieval_feedback_not_answer_evidence",
                "status": "needs_additional_retrieval",
                "primary_issue_type": "missing_current_evidence",
                "issues": [],
            },
            "current_answer_context": [],
            "historical_archive_context": [],
            "stale_or_blocked_context": [{"memory_id": "maya_old"}],
            "uncertain_context": [],
        }
        rendered_target = json.dumps(
            _target_messages(
                question="Where should mail go now?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertIn("retrieval_feedback", rendered_target)
        self.assertIn("not answer evidence", rendered_target)

    def test_blocking_retrieval_feedback_is_advisory_for_raw_recall_reuse(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "target_compaction_policy": {"mode": "full"},
            "query_intent": "current_state",
            "direct_recall_context": {
                "retrieved_memories": [
                    {
                        "memory_id": "rachel_suburbs",
                        "claim": "Rachel recently moved back to the suburbs.",
                    }
                ]
            },
            "qvf_read_time_decision": {
                "decision": "UNKNOWN_CURRENT",
                "answer_policy": "insufficient_source_supported_current",
            },
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
            },
            "retrieval_feedback": {
                "feedback_version": "qvf_retrieval_feedback_v0.1",
                "scope": "system_retrieval_feedback_not_answer_evidence",
                "status": "needs_additional_retrieval",
                "primary_issue_type": "missing_timeline_evidence",
                "issues": [
                    {
                        "issue_type": "missing_timeline_evidence",
                        "severity": "blocking",
                    }
                ],
            },
            "current_answer_context": [],
            "historical_archive_context": [],
            "transition_context": [],
            "change_detail_context": [],
            "status_class_context": [],
            "condition_scope_context": [],
            "habit_frequency_context": [],
            "scoped_reader_context": [],
            "static_conflict_resolution_context": [],
            "temporal_resolution_context": [],
            "supporting_context": [],
            "stale_or_blocked_context": [],
            "uncertain_context": [{"memory_id": "rachel_suburbs"}],
        }
        rendered_payload = json.loads(
            _target_messages(
                question="Where did Rachel move to after her recent relocation?",
                method="qvf_validity_packed_context",
                context=context,
            )[1]["content"]
        )

        self.assertIn("retrieved_memories", rendered_payload["memory_context"])
        self.assertNotIn("retrieval_feedback", rendered_payload["memory_context"])

    def test_route_evidence_keeps_independent_target_despite_blocking_feedback(self) -> None:
        context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "target_compaction_policy": {"mode": "full"},
            "query_intent": "timeline_change",
            "direct_recall_context": {
                "retrieved_memories": [
                    {"memory_id": "job_new", "claim": "User became an intern."}
                ]
            },
            "qvf_read_time_decision": {
                "decision": "ADMIT_CURRENT",
                "answer_policy": "answer_from_current",
            },
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
            },
            "retrieval_feedback": {
                "feedback_version": "qvf_retrieval_feedback_v0.1",
                "scope": "system_retrieval_feedback_not_answer_evidence",
                "status": "needs_additional_retrieval",
                "primary_issue_type": "missing_change_pair_evidence",
                "issues": [
                    {
                        "issue_type": "missing_change_pair_evidence",
                        "severity": "blocking",
                    }
                ],
            },
            "current_answer_context": [{"memory_id": "job_new"}],
            "historical_archive_context": [],
            "transition_context": [],
            "change_detail_context": [],
            "status_class_context": [],
            "condition_scope_context": [],
            "habit_frequency_context": [],
            "scoped_reader_context": [
                {
                    "scope_type": "temporal_action",
                    "candidate_events": [
                        {
                            "memory_id": "melanie_camping",
                            "event_title": "camping plan",
                            "temporal_marker": "next month",
                            "action_cue": "going camping",
                        }
                    ],
                }
            ],
            "static_conflict_resolution_context": [],
            "temporal_resolution_context": [],
            "supporting_context": [],
            "stale_or_blocked_context": [],
            "uncertain_context": [],
        }
        rendered_payload = json.loads(
            _target_messages(
                question="What changed about the user's job title?",
                method="qvf_validity_packed_context",
                context=context,
            )[1]["content"]
        )

        self.assertIn("retrieval_feedback", rendered_payload["memory_context"])
        self.assertNotIn("retrieved_memories", rendered_payload["memory_context"])

    def test_post_answer_audit_controller_keeps_plain_recall_target_equivalent_to_direct(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_plain_recall_adapter_item()],
                qvf_requests=[_plain_recall_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        direct_item = [item for item in items if item["method"] == "direct_extracted_memories"][0]
        qvf_item = [item for item in items if item["method"] == "qvf_validity_packed_context"][0]
        qvf_context = qvf_item["context"]
        direct_judge_payload = json.loads(
            _judge_messages(direct_item, '{"answer":"camping","used_memory_ids":[],"abstained":false}')[1][
                "content"
            ]
        )
        qvf_judge_payload = json.loads(
            _judge_messages(qvf_item, '{"answer":"camping","used_memory_ids":[],"abstained":false}')[1][
                "content"
            ]
        )

        self.assertEqual(
            qvf_context["memory_validity_controller_action"]["action"],
            "raw_recall_with_annotations",
        )
        self.assertEqual(qvf_context["direct_recall_context"], direct_item["context"])
        self.assertEqual(qvf_item["target_messages"], direct_item["target_messages"])
        self.assertEqual(
            qvf_judge_payload["memory_context"],
            direct_judge_payload["memory_context"],
        )
        self.assertEqual(
            qvf_context["evidence_preservation_policy"]["mode"],
            "post_answer_audit_preserve_extracted_records_with_hidden_qvf_labels",
        )

    def test_post_answer_audit_source_history_scope_reaches_target_prompt(self) -> None:
        direct_context = {
            "context_type": "direct_extracted_memories",
            "extracted_memories": [
                {
                    "memory_id": "melanie_camping",
                    "claim": "Melanie planned camping for next month.",
                    "value": "next month",
                    "observed_at": "2023-05-25T13:14:00+00:00",
                    "source_span": (
                        "We talked about school pickup, groceries, and a few unrelated "
                        "weekend errands before the plan came up. "
                        + "filler " * 80
                        + "We're thinking about going camping next month."
                    ),
                }
            ],
        }
        qvf_context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
                "reason": "no_route_first_validity_pressure_detected",
                "question_fingerprint": "When is Melanie planning on going camping?",
            },
            "direct_recall_context": direct_context,
            "validity_controller_decision": {
                "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                "next_action": "answer_from_archive",
                "suggested_retrieval_scope": {
                    "include_archive": True,
                    "include_source_history": True,
                    "target_group": "camping_plan",
                },
            },
            "qvf_read_time_decision": {
                "decision": "ADMIT_ARCHIVE",
                "answer_policy": "answer_from_archive",
                "route": "archive_history_reader",
            },
            "target_compaction_policy": {"mode": "full"},
            "historical_archive_context": direct_context["extracted_memories"],
            "extracted_memory_context": direct_context["extracted_memories"],
            "current_answer_context": [],
            "transition_context": [],
            "change_detail_context": [],
            "status_class_context": [],
            "condition_scope_context": [],
            "habit_frequency_context": [],
            "scoped_reader_context": [
                {
                    "scope_type": "temporal_action",
                    "candidate_events": [
                        {
                            "memory_id": "melanie_camping",
                            "event_title": "camping plan",
                            "temporal_marker": "next month",
                            "action_cue": "going camping",
                        }
                    ],
                }
            ],
            "static_conflict_resolution_context": [],
            "temporal_resolution_context": [],
            "supporting_context": [],
            "stale_or_blocked_context": [],
            "uncertain_context": [],
        }

        direct_messages = _target_messages(
            question="When is Melanie planning on going camping?",
            method="direct_extracted_memories",
            context=direct_context,
        )
        qvf_messages = _target_messages(
            question="When is Melanie planning on going camping?",
            method="qvf_validity_packed_context",
            context=qvf_context,
        )
        qvf_payload = json.loads(qvf_messages[1]["content"])

        self.assertNotEqual(qvf_messages, direct_messages)
        self.assertIn(
            "source_history_answer_contract",
            qvf_payload["memory_context"],
        )
        self.assertIn("extracted_memory_context", qvf_payload["memory_context"])
        self.assertIn("include_source_history", json.dumps(qvf_payload, ensure_ascii=False))
        self.assertIn("source_history_answer_contract", qvf_payload["instruction"])
        self.assertNotIn("SECRET", json.dumps(qvf_messages, ensure_ascii=False))

    def test_source_history_focus_context_preserves_relative_temporal_phrase(self) -> None:
        request = {
            "request_id": "source_history_focus_request",
            "query_requests": [
                {
                    "question": "When did Caroline apply to adoption agencies?",
                }
            ],
            "_selected_history_turns": [
                {
                    "turn_id": "turn_2023_08_23",
                    "timestamp": "3:31 pm on 23 August, 2023",
                    "selection_rank": 1,
                    "speaker": "user",
                    "text": (
                        "Hi Melanie! Guess what I did this week? I took the first "
                        "step towards becoming a mom - I applied to adoption agencies!"
                    ),
                }
            ],
        }

        focus_context = _build_source_history_focus_context(
            request,
            "When did Caroline apply to adoption agencies?",
        )

        self.assertEqual(len(focus_context), 1)
        focus_rows = focus_context[0]["focus_rows"]
        self.assertEqual(focus_rows[0]["source_temporal_phrase"], "this week")
        self.assertEqual(
            focus_rows[0]["source_observed_at"],
            "3:31 pm on 23 August, 2023",
        )
        self.assertIn("adoption", focus_rows[0]["query_overlap_terms"])

    def test_source_history_focus_context_keeps_short_domain_terms(self) -> None:
        request = {
            "request_id": "source_history_focus_er_request",
            "query_requests": [{"question": "When was Sam in the ER?"}],
            "_selected_history_turns": [
                {
                    "turn_id": "turn_2023_10_17",
                    "timestamp": "1:50 pm on 17 October, 2023",
                    "selection_rank": 1,
                    "speaker": "user",
                    "text": (
                        "I had quite the health scare last weekend - ended up "
                        "in the ER with a severe stomachache."
                    ),
                }
            ],
        }

        focus_context = _build_source_history_focus_context(
            request,
            "When was Sam in the ER?",
        )

        focus_rows = focus_context[0]["focus_rows"]
        self.assertEqual(focus_rows[0]["source_temporal_phrase"], "last weekend")
        self.assertIn("er", focus_rows[0]["query_overlap_terms"])

    def test_source_history_focus_context_preserves_causal_trigger(self) -> None:
        request = {
            "request_id": "source_history_focus_causal_request",
            "query_requests": [
                {"question": "Why did Jon decide to start his dance studio?"}
            ],
            "_selected_history_turns": [
                {
                    "turn_id": "turn_jon_dance_studio",
                    "timestamp": "9:15 am on 12 April, 2023",
                    "selection_rank": 1,
                    "speaker": "user",
                    "text": (
                        "Thanks! A major life change gave me the motivation to finally start "
                        "my dream business: my own dance studio."
                    ),
                }
            ],
        }

        focus_context = _build_source_history_focus_context(
            request,
            "Why did Jon decide to start his dance studio?",
        )

        focus_rows = focus_context[0]["focus_rows"]
        self.assertEqual(focus_rows[0]["source_focus_type"], "causal")
        self.assertIn("gave me the motivation", focus_rows[0]["source_focus_phrase"])
        self.assertIn("dance", focus_rows[0]["query_overlap_terms"])
        self.assertIn("studio", focus_rows[0]["query_overlap_terms"])

    def test_source_history_answer_anchor_context_preserves_source_span_terms(
        self,
    ) -> None:
        request = {
            "request_id": "source_history_anchor_request",
            "query_requests": [
                {"question": "What did Melanie do after the road trip to relax?"}
            ],
            "_selected_history_turns": [
                {
                    "turn_id": "turn_road_trip_relax",
                    "timestamp": "6:55 pm on 20 October, 2023",
                    "text": (
                        "The kids loved it and it was a nice way to relax after "
                        "the road trip."
                    ),
                }
            ],
            "records": [
                {
                    "memory_id": "relax_after_road_trip",
                    "slot": "activity_after_road_trip",
                    "value": "relax",
                    "claim": (
                        "The kids loved it and it was a nice way to relax after "
                        "the road trip."
                    ),
                    "source": {
                        "source_span": (
                            "Thanks, Caroline! Yup, we just did it yesterday! "
                            "The kids loved it and it was a nice way to relax "
                            "after the road trip. Glad you got some R&R after "
                            "the drive. Nature sure seems to refresh us, huh?"
                        )
                    },
                }
            ],
        }

        anchor_context = _build_source_history_answer_anchor_context(
            request,
            "What did Melanie do after the road trip to relax?",
            scoped_reader_context=[{"candidate_events": [{"event_id": "road_trip"}]}],
            source_history_focus_context=[],
        )

        anchor_rows = anchor_context[0]["anchor_rows"]
        self.assertIn("nature", anchor_rows[0]["source_answer_anchor_terms"])
        self.assertIn("refresh", anchor_rows[0]["source_answer_anchor_terms"])
        self.assertIn("source_anchor_excerpt", anchor_rows[0])

    def test_source_history_focus_context_requires_source_timestamp(self) -> None:
        request = {
            "request_id": "source_history_focus_no_timestamp_request",
            "query_requests": [{"question": "When was Sam in the ER?"}],
            "_selected_history_turns": [
                {
                    "turn_id": "turn_without_timestamp",
                    "selection_rank": 1,
                    "speaker": "user",
                    "text": "I had a health scare last weekend and ended up in the ER.",
                }
            ],
        }

        focus_context = _build_source_history_focus_context(
            request,
            "When was Sam in the ER?",
        )

        self.assertEqual(focus_context, [])

    def test_source_history_focus_context_reaches_qvf_target_prompt(self) -> None:
        qvf_context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
                "question_fingerprint": "When was Sam in the ER?",
            },
            "validity_controller_decision": {
                "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                "next_action": "answer_from_archive",
                "suggested_retrieval_scope": {
                    "include_archive": True,
                    "include_source_history": True,
                },
            },
            "qvf_read_time_decision": {
                "decision": "ADMIT_ARCHIVE",
                "answer_policy": "answer_from_archive",
            },
            "target_compaction_policy": {"mode": "full"},
            "source_history_focus_context": [
                {
                    "packet_type": "qvf_source_history_temporal_focus_packet",
                    "focus_rows": [
                        {
                            "focus_id": "sam_er_focus",
                            "source_observed_at": "1:50 pm on 17 October, 2023",
                            "source_temporal_phrase": "last weekend",
                            "query_overlap_terms": ["sam"],
                            "source_sentence": (
                                "I had a health scare last weekend - ended up in "
                                "the ER with a severe stomachache."
                            ),
                        }
                    ],
                }
            ],
            "source_history_answer_anchor_context": [
                {
                    "packet_type": "qvf_source_history_answer_anchor_packet",
                    "anchor_rows": [
                        {
                            "anchor_id": "melanie_relax_anchor",
                            "memory_id": "relax_after_road_trip",
                            "source_answer_anchor_terms": ["kids", "nature"],
                            "source_anchor_excerpt": (
                                "The kids loved it and it was a nice way to relax "
                                "after the road trip. Nature sure seems to refresh us."
                            ),
                        }
                    ],
                }
            ],
            "historical_archive_context": [],
            "extracted_memory_context": [],
            "current_answer_context": [],
            "transition_context": [],
            "change_detail_context": [],
            "status_class_context": [],
            "condition_scope_context": [],
            "habit_frequency_context": [],
            "scoped_reader_context": [],
            "static_conflict_resolution_context": [],
            "temporal_resolution_context": [],
            "supporting_context": [],
            "stale_or_blocked_context": [],
            "uncertain_context": [],
        }

        qvf_payload = json.loads(
            _target_messages(
                question="When was Sam in the ER?",
                method="qvf_validity_packed_context",
                context=qvf_context,
            )[1]["content"]
        )

        self.assertIn(
            "source_history_focus_context",
            qvf_payload["memory_context"],
        )
        self.assertIn("last weekend", json.dumps(qvf_payload, ensure_ascii=False))
        self.assertIn("source_history_focus_context", qvf_payload["instruction"])
        self.assertIn(
            "source_history_answer_anchor_context",
            qvf_payload["memory_context"],
        )
        self.assertIn("nature", json.dumps(qvf_payload, ensure_ascii=False))
        self.assertIn(
            "source_history_answer_anchor_context",
            qvf_payload["instruction"],
        )

    def test_post_answer_audit_generic_source_history_reuses_direct_target(self) -> None:
        direct_context = {
            "context_type": "direct_extracted_memories",
            "extracted_memories": [
                {
                    "memory_id": "shirt",
                    "claim": "Andy wore an untidy stained white shirt.",
                    "value": "untidy stained white shirt",
                }
            ],
        }
        qvf_context = {
            "context_type": "qvf_validity_packed_context",
            "qvf_context_variant": "post_answer_audit_controller",
            "memory_validity_controller_action": {
                "action": "raw_recall_with_annotations",
                "reason": "no_route_first_validity_pressure_detected",
                "question_fingerprint": (
                    "I was going through our previous chat; what was Andy wearing?"
                ),
            },
            "direct_recall_context": direct_context,
            "validity_controller_decision": {
                "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                "next_action": "answer_from_archive",
                "suggested_retrieval_scope": {
                    "include_archive": True,
                    "include_source_history": True,
                },
            },
            "qvf_read_time_decision": {
                "decision": "ADMIT_ARCHIVE",
                "answer_policy": "answer_from_archive",
            },
            "historical_archive_context": direct_context["extracted_memories"],
            "extracted_memory_context": direct_context["extracted_memories"],
            "current_answer_context": [],
            "scoped_reader_context": [],
        }

        direct_messages = _target_messages(
            question="I was going through our previous chat; what was Andy wearing?",
            method="direct_extracted_memories",
            context=direct_context,
        )
        qvf_messages = _target_messages(
            question="I was going through our previous chat; what was Andy wearing?",
            method="qvf_validity_packed_context",
            context=qvf_context,
        )

        self.assertEqual(qvf_messages, direct_messages)

    def test_post_answer_audit_controller_keeps_stale_current_packet_model_facing(self) -> None:
        items = build_public_answer_eval_items(
            adapter_items=[_adapter_item()],
            qvf_requests=[_qvf_request()],
            limit=1,
            qvf_context_variant="post_answer_audit_controller",
        )
        direct_item = [item for item in items if item["method"] == "direct_extracted_memories"][0]
        qvf_item = [item for item in items if item["method"] == "qvf_validity_packed_context"][0]
        qvf_target_payload = json.loads(qvf_item["target_messages"][1]["content"])
        qvf_memory_context = qvf_target_payload["memory_context"]
        qvf_judge_payload = json.loads(
            _judge_messages(qvf_item, '{"answer":"Milan","used_memory_ids":[],"abstained":false}')[1][
                "content"
            ]
        )

        self.assertNotEqual(qvf_item["target_messages"], direct_item["target_messages"])
        self.assertEqual(
            qvf_memory_context["memory_validity_controller_action"]["action"],
            "stale_current_validity_packet",
        )
        self.assertIn("current_answer_context", qvf_memory_context)
        self.assertIn("stale_or_blocked_context", qvf_memory_context)
        self.assertNotIn("direct_recall_context", qvf_memory_context)
        self.assertIn("stale_current_validity_packet", json.dumps(qvf_item["target_messages"]))
        self.assertEqual(qvf_judge_payload["memory_context"], qvf_memory_context)

    def test_post_answer_audit_controller_keeps_uncontested_current_state_direct_equivalent(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_current_only_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_current_only_adapter_item()],
                qvf_requests=[_current_only_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        direct_item = [item for item in items if item["method"] == "direct_extracted_memories"][0]
        qvf_item = [item for item in items if item["method"] == "qvf_validity_packed_context"][0]

        self.assertEqual(
            qvf_item["context"]["memory_validity_controller_action"]["action"],
            "raw_recall_with_annotations",
        )
        self.assertEqual(
            qvf_item["context"]["memory_validity_controller_action"]["reason"],
            "post_answer_controller_uncontested_current_state_direct_equivalent",
        )
        self.assertEqual(qvf_item["target_messages"], direct_item["target_messages"])

    def test_post_answer_audit_controller_keeps_comparative_recall_direct_equivalent(self) -> None:
        request = {
            "request_id": "public_extraction_comparative_recall",
            "step_id": "public_extraction_step_comparative_recall",
            "query_requests": [
                {
                    "request_id": "q_comparative_recall",
                    "question": (
                        "How much more miles per gallon was my car getting a few "
                        "months ago compared to now?"
                    ),
                    "entity": "car",
                    "slot": "fuel_efficiency",
                    "premise_value": "30 miles per gallon",
                    "needs_current": True,
                }
            ],
            "records": [
                {
                    "memory_id": "car_old_mpg",
                    "entity": "car",
                    "slot": "fuel_efficiency",
                    "value": "30 miles per gallon",
                    "claim": "User's car was getting 30 miles per gallon a few months ago.",
                    "observed_at": "2023-05-20T01:33:00+00:00",
                    "source": {
                        "source_id": "turn_car_old",
                        "source_type": "public_history_extraction",
                    },
                    "source_confidence": 0.9,
                },
                {
                    "memory_id": "car_current_mpg",
                    "entity": "car",
                    "slot": "current_fuel_efficiency",
                    "value": "28 miles per gallon",
                    "claim": "User has been getting around 28 miles per gallon lately.",
                    "observed_at": "2023-05-24T23:28:00+00:00",
                    "source": {
                        "source_id": "turn_car_current",
                        "source_type": "public_history_extraction",
                    },
                    "source_confidence": 0.9,
                },
            ],
        }
        adapter_item = {
            "case_id": "comparative_recall",
            "question": request["query_requests"][0]["question"],
            "answers": ["SECRET_COMPARATIVE_ANSWER"],
        }

        items = build_public_answer_eval_items(
            adapter_items=[adapter_item],
            qvf_requests=[request],
            limit=1,
            qvf_context_variant="post_answer_audit_controller",
        )

        direct_item = [item for item in items if item["method"] == "direct_extracted_memories"][0]
        qvf_item = [item for item in items if item["method"] == "qvf_validity_packed_context"][0]

        self.assertEqual(
            qvf_item["context"]["memory_validity_controller_action"]["action"],
            "raw_recall_with_annotations",
        )
        self.assertEqual(
            qvf_item["context"]["memory_validity_controller_action"]["reason"],
            "post_answer_controller_comparative_recall_direct_equivalent",
        )
        self.assertEqual(qvf_item["target_messages"], direct_item["target_messages"])

    def test_post_answer_comparative_scalar_audit_compacts_unique_delta(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                "How much more miles per gallon was my car getting a few "
                "months ago compared to now?"
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "timeline_or_conflict_packet",
                },
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "Your car was getting 2 miles per gallon more a few months "
                    "ago, at 30 mpg compared to 28 mpg now."
                ),
                "used_memory_ids": ["car_old_mpg", "car_current_mpg"],
                "abstained": False,
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(
            audit["reason"],
            "comparative_scalar_component_suffix_contract",
        )
        self.assertEqual(
            audit["replacement"],
            "Your car was getting 2 miles per gallon more a few months ago.",
        )
        self.assertEqual(
            payload["answer"],
            "Your car was getting 2 miles per gallon more a few months ago.",
        )
        self.assertEqual(
            payload["used_memory_ids"],
            ["car_old_mpg", "car_current_mpg"],
        )

    def test_post_answer_comparative_scalar_audit_rejects_multiple_deltas(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "How much more did my old commute cost compared to now?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "timeline_or_conflict_packet",
                },
            },
        }
        content = json.dumps(
            {
                "answer": "It was 2 dollars more on weekdays and 5 dollars more on weekends.",
                "used_memory_ids": ["commute_old", "commute_current"],
                "abstained": False,
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(audit["reason"], "not_post_answer_qvf")
        self.assertEqual(repaired, content)

    def test_answer_payload_equivalence_requires_final_payload_match(self) -> None:
        direct = json.dumps(
            {
                "answer": "Your car was getting 2 miles per gallon more a few months ago.",
                "used_memory_ids": ["old_mpg", "new_mpg"],
                "abstained": False,
            }
        )
        qvf = json.dumps(
            {
                "answer": " Your car was getting 2 miles per gallon more a few months ago. ",
                "used_memory_ids": ["old_mpg", "new_mpg"],
                "abstained": False,
            }
        )
        different_sources = json.dumps(
            {
                "answer": "Your car was getting 2 miles per gallon more a few months ago.",
                "used_memory_ids": ["new_mpg", "old_mpg"],
                "abstained": False,
            }
        )
        different_answer = json.dumps(
            {
                "answer": "2 miles per gallon more",
                "used_memory_ids": ["old_mpg", "new_mpg"],
                "abstained": False,
            }
        )

        self.assertTrue(_answer_payloads_equivalent(direct, qvf))
        self.assertFalse(_answer_payloads_equivalent(direct, different_sources))
        self.assertFalse(_answer_payloads_equivalent(direct, different_answer))

    def test_post_answer_audit_controller_keeps_current_or_aggregate_recall_direct_equivalent(self) -> None:
        request = {
            "request_id": "public_extraction_aggregate_recall",
            "step_id": "public_extraction_step_aggregate_recall",
            "query_requests": [
                {
                    "request_id": "q_aggregate_recall",
                    "question": "How many projects have I led or am currently leading?",
                    "entity": "user",
                    "slot": "projects_led",
                    "premise_value": "projects led or currently leading",
                    "needs_current": True,
                }
            ],
            "records": [
                {
                    "memory_id": "project_old",
                    "entity": "user",
                    "slot": "projects_led",
                    "value": "data analysis team",
                    "claim": "User led the data analysis team for a market analysis.",
                    "observed_at": "2023-05-21T19:38:00+00:00",
                    "source": {
                        "source_id": "turn_project_old",
                        "source_type": "public_history_extraction",
                    },
                    "source_confidence": 0.9,
                },
                {
                    "memory_id": "project_current",
                    "entity": "user",
                    "slot": "projects_led",
                    "value": "high-priority project",
                    "claim": "User completed a high-priority project two months early.",
                    "observed_at": "2023-05-28T03:42:00+00:00",
                    "source": {
                        "source_id": "turn_project_current",
                        "source_type": "public_history_extraction",
                    },
                    "source_confidence": 0.9,
                },
            ],
        }
        adapter_item = {
            "case_id": "aggregate_recall",
            "question": request["query_requests"][0]["question"],
            "answers": ["SECRET_AGGREGATE_ANSWER"],
        }

        items = build_public_answer_eval_items(
            adapter_items=[adapter_item],
            qvf_requests=[request],
            limit=1,
            qvf_context_variant="post_answer_audit_controller",
        )

        direct_item = [item for item in items if item["method"] == "direct_extracted_memories"][0]
        qvf_item = [item for item in items if item["method"] == "qvf_validity_packed_context"][0]

        self.assertEqual(
            qvf_item["context"]["memory_validity_controller_action"]["action"],
            "raw_recall_with_annotations",
        )
        self.assertEqual(qvf_item["target_messages"], direct_item["target_messages"])

    def test_post_answer_audit_controller_maps_temporal_only_packet_to_direct_equivalent(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            multi_action_context = _qvf_context(
                _temporal_qvf_request(),
                qvf_context_variant="multi_action_controller",
            )
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            post_answer_items = build_public_answer_eval_items(
                adapter_items=[_plain_recall_adapter_item()],
                qvf_requests=[_temporal_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        direct_item = [
            item for item in post_answer_items if item["method"] == "direct_extracted_memories"
        ][0]
        qvf_item = [
            item for item in post_answer_items if item["method"] == "qvf_validity_packed_context"
        ][0]

        self.assertEqual(
            multi_action_context["memory_validity_controller_action"]["action"],
            "scoped_or_temporal_packet",
        )
        self.assertEqual(
            qvf_item["context"]["memory_validity_controller_action"]["action"],
            "raw_recall_with_annotations",
        )
        self.assertEqual(qvf_item["target_messages"], direct_item["target_messages"])

    def test_post_answer_temporal_audit_repairs_relative_time_answer(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_temporal_adapter_item()],
                qvf_requests=[_temporal_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        content = json.dumps(
            {
                "answer": "Melanie is planning on going camping next month.",
                "used_memory_ids": ["melanie_camping"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(audit["replacement"], "June 2023")
        self.assertEqual(
            payload["answer"],
            "Melanie is planning on going camping in June 2023.",
        )

    def test_post_answer_contract_audit_repairs_compound_condition_drop(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer green vegetable juice?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        "When does the user prefer green vegetable juice?"
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "green_juice",
                        "exact_condition": "after workouts",
                        "supporting_value": "green vegetable juice",
                        "source_excerpt": (
                            "User likes having a green vegetable juice in the "
                            "morning or after workouts."
                        ),
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "The user prefers green vegetable juice after workouts.",
                "used_memory_ids": ["green_juice"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(
            payload["answer"],
            "The user prefers green vegetable juice in the morning or after workouts.",
        )

    def test_post_answer_contract_audit_repairs_missing_critical_detail(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                'Under what condition does the user prefer a "Cuddly Ragdoll Cat"?'
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        'Under what condition does the user prefer a "Cuddly Ragdoll Cat"?'
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "quiet_pet",
                        "scope_type": "condition_preference_source",
                        "exact_condition": "during reading and writing",
                        "preferred_answer": (
                            "during reading and writing; detail: calm indoor "
                            "companion to curl up"
                        ),
                        "condition_answer_detail": "calm indoor companion to curl up",
                        "source_excerpt": (
                            "User prefers a Cuddly Ragdoll Cat, something calm "
                            "and indoor to curl up with during reading and writing."
                        ),
                        "supporting_value": "Cuddly Ragdoll Cat",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    'The user prefers a "Cuddly Ragdoll Cat" during reading '
                    "and writing."
                ),
                "used_memory_ids": ["quiet_pet"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertIn("calm indoor companion", payload["answer"])
        self.assertIn("during reading and writing", payload["answer"])

    def test_post_answer_contract_audit_renders_training_detail_as_condition(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                "Under what condition would the user prefer a protective "
                "German Shepherd as a pet?"
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        "Under what condition would the user prefer a protective "
                        "German Shepherd as a pet?"
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "german_shepherd_preference",
                        "scope_type": "condition_preference_source",
                        "exact_condition": (
                            "if i lived in family home and wanted watchdog"
                        ),
                        "preferred_answer": (
                            "if i lived in family home and wanted watchdog; "
                            "detail: follows commands and trained to prevent chaos"
                        ),
                        "condition_answer_detail": (
                            "follows commands and trained to prevent chaos"
                        ),
                        "source_excerpt": (
                            "If I lived in a family home and wanted a watchdog, "
                            "I'd consider a protective German Shepherd, something "
                            "that follows commands and can be trained to prevent chaos."
                        ),
                        "supporting_value": "protective German Shepherd",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "The user would prefer a protective German Shepherd if they "
                    "lived in a family home and wanted a watchdog."
                ),
                "used_memory_ids": ["german_shepherd_preference"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertIn("able to train", payload["answer"])
        self.assertIn("train the dog to follow commands", payload["answer"])
        self.assertIn("prevent chaos", payload["answer"])
        self.assertNotIn("detail:", payload["answer"])
        self.assertNotIn("if i lived", payload["answer"].lower())

    def test_post_answer_contract_audit_repairs_leading_context_drop(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer slow reflective dramas?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        "When does the user prefer slow reflective dramas?"
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "slow_drama",
                        "scope_type": "condition_preference_source",
                        "exact_condition": (
                            "when it is quiet like after the children are asleep"
                        ),
                        "preferred_answer": (
                            "when it is quiet like after the children are asleep"
                        ),
                        "source_excerpt": (
                            "When it is quiet, like after the children are "
                            "asleep, I prefer slow reflective dramas."
                        ),
                        "supporting_value": "slow reflective dramas",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "The user prefers slow reflective dramas after the children "
                    "are asleep."
                ),
                "used_memory_ids": ["slow_drama"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertIn("quiet", payload["answer"])
        self.assertIn("children are asleep", payload["answer"])

    def test_post_answer_contract_audit_treats_doing_as_coverage_stopword(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer short philosophy texts?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                },
                "condition_scope_context": [
                    {
                        "memory_id": "philosophy_text",
                        "scope_type": "condition_preference_source",
                        "exact_condition": (
                            "on quiet mornings when i m doing professional development"
                        ),
                        "preferred_answer": (
                            "on quiet mornings when i m doing professional development"
                        ),
                        "source_excerpt": (
                            "I prefer short philosophy texts on quiet mornings "
                            "when I'm doing professional development."
                        ),
                        "supporting_value": "short philosophy texts",
                        "source_field": "source_span",
                    }
                ],
                "answer_decision_contract": {
                    "contract_rows": [
                        {
                            "memory_id": "philosophy_text",
                            "must_preserve": [
                                "short philosophy texts",
                                "on quiet mornings when i m doing professional development",
                            ],
                        }
                    ]
                },
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "The user prefers short philosophy texts on quiet mornings "
                    "during professional development."
                ),
                "used_memory_ids": ["philosophy_text"],
                "abstained": False,
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertNotIn("when I'm doing", repaired)

    def test_post_answer_contract_audit_skips_joint_subject_condition_repair(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer story-driven games?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                },
                "condition_scope_context": [
                    {
                        "memory_id": "story_games",
                        "scope_type": "condition_preference_source",
                        "exact_condition": "on quiet evenings when we re both free",
                        "preferred_answer": "on quiet evenings when we re both free",
                        "source_excerpt": (
                            "I prefer story-driven games on quiet evenings when "
                            "we're both free."
                        ),
                        "supporting_value": "story-driven games",
                        "source_field": "source_span",
                    }
                ],
                "answer_decision_contract": {
                    "contract_rows": [
                        {
                            "memory_id": "story_games",
                            "must_preserve": [
                                "story-driven games",
                                "on quiet evenings when we re both free",
                            ],
                        }
                    ]
                },
            },
        }
        content = json.dumps(
            {
                "answer": "User prefers story-driven games during quiet evenings.",
                "used_memory_ids": ["story_games"],
                "abstained": False,
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertNotIn("both free", repaired)

    def test_post_answer_contract_audit_skips_source_neighbor_condition_drift(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "Under what condition does the user prefer fresh orange juice?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        "Under what condition does the user prefer fresh orange juice?"
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "orange_training_days",
                        "scope_type": "condition_preference_source",
                        "exact_condition": "on training days",
                        "preferred_answer": "on training days; detail: have as boost",
                        "condition_answer_detail": "have as boost",
                        "source_excerpt": (
                            "User prefers to have fresh orange juice as a boost "
                            "on training days."
                        ),
                        "supporting_value": "fresh orange juice",
                    },
                    {
                        "memory_id": "orange_before_training",
                        "scope_type": "condition_scope",
                        "exact_condition": "before training",
                        "preferred_answer": "before training",
                        "source_excerpt": (
                            "Before training I usually have fresh orange juice as "
                            "a quick morning boost. The sessions help, but on "
                            "heavy workdays the afternoon crash still hits."
                        ),
                        "supporting_value": "fresh orange juice",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "User prefers fresh orange juice before training and as a "
                    "boost on training days."
                ),
                "used_memory_ids": [
                    "orange_training_days",
                    "orange_before_training",
                ],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertIn("answer_already_satisfies", audit["reason"])
        self.assertEqual(json.loads(repaired)["answer"], json.loads(content)["answer"])

    def test_post_answer_contract_audit_skips_low_value_alternate_condition(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "Under what condition would the user prefer a Miniature Poodle?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                },
                "condition_scope_context": [
                    {
                        "memory_id": "poodle_later",
                        "scope_type": "condition_scope",
                        "exact_condition": "if startup pace eases bit later",
                        "preferred_answer": "if startup pace eases bit later",
                        "source_excerpt": (
                            "If the startup pace eases a bit later, I might "
                            "actually get that Miniature Poodle."
                        ),
                        "supporting_value": "might actually get that Miniature Poodle",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "User prefers a Miniature Poodle if it is hypoallergenic "
                    "and fits a busy lifestyle."
                ),
                "used_memory_ids": ["poodle_primary"],
                "abstained": False,
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertNotIn("startup pace", json.loads(repaired)["answer"])

    def test_condition_scope_context_replaces_low_value_source_neighbor_with_sibling(self) -> None:
        row = {
            "memory_id": "feel_good_movie",
            "claim": (
                "User prefers feel-good comedies after work to unwind or on "
                "weekend evenings."
            ),
            "value": "feel-good comedy",
            "source": {
                "source_span": (
                    "We both like feel-good comedies after work to unwind or "
                    "on weekend evenings, if that helps tone."
                )
            },
        }
        request = {
            "query_requests": [
                {
                    "question": (
                        "When does the user prefer 'Feel-good Comedy' as a "
                        "movie choice?"
                    )
                }
            ],
            "records": [row],
        }

        conditions = _build_condition_scope_context(request, [row])

        exact_conditions = [row["exact_condition"] for row in conditions]
        self.assertEqual(exact_conditions, ["after work", "on weekend evenings"])
        self.assertNotIn("if that helps tone", exact_conditions)

    def test_condition_scope_context_preserves_value_suffix_descriptor(self) -> None:
        row = {
            "memory_id": "poodle_primary",
            "claim": (
                "User is considering getting a Miniature Poodle as a pet due "
                "to its hypoallergenic nature and suitability for a busy "
                "lifestyle."
            ),
            "value": "hypoallergenic, smaller companion that fits a busy schedule",
            "source": {
                "source_span": (
                    "I was leaning toward a Miniature Poodle if I need a "
                    "hypoallergenic, smaller companion that fits a busy "
                    "schedule. Any quick tips on that while running a startup?"
                )
            },
        }
        request = {
            "query_requests": [
                {
                    "question": (
                        "Under what condition would the user prefer a "
                        "Miniature Poodle as a pet?"
                    )
                }
            ],
            "records": [row],
        }

        conditions = _build_condition_scope_context(request, [row])

        self.assertTrue(conditions)
        self.assertEqual(conditions[0]["exact_condition"], "if i need hypoallergenic")
        self.assertIn(
            "smaller companion",
            conditions[0]["condition_answer_detail"],
        )
        self.assertIn(
            "busy schedule",
            conditions[0]["complete_condition_answer"],
        )

    def test_post_answer_contract_audit_skips_compound_condition_without_anchor_overlap(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer an elegant evening dress?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                },
                "condition_scope_context": [
                    {
                        "memory_id": "gallery_dress",
                        "scope_type": "condition_preference_source",
                        "exact_condition": "when small show or opening might come up",
                        "preferred_answer": "when small show or opening might come up",
                        "source_excerpt": (
                            "I have an elegant evening dress I keep for special "
                            "gallery events. Keeping that dress ready is practical; "
                            "you never know when a small show or opening might "
                            "come up."
                        ),
                        "supporting_value": "elegant evening dress",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "User prefers an elegant evening dress for special gallery "
                    "events and formal presentations."
                ),
                "used_memory_ids": ["gallery_dress"],
                "abstained": False,
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertIn("formal presentations", json.loads(repaired)["answer"])

    def test_post_answer_contract_audit_skips_neighbor_noise_condition(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer Disaster Masterpiece?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        "When does the user prefer Disaster Masterpiece?"
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "disaster_movie",
                        "exact_condition": "before i finalize",
                        "supporting_value": "Disaster Masterpiece",
                        "source_excerpt": (
                            "Fun fact: when I need an adrenaline break I watch "
                            "Disaster Masterpiece in one template to keep it "
                            "human. Anything else to include before I finalize?"
                        ),
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "The user prefers Disaster Masterpiece before finalizing tasks."
                ),
                "used_memory_ids": ["disaster_movie"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertIn("I need adrenaline break", payload["answer"])
        self.assertNotIn("finalize", payload["answer"].lower())
        self.assertNotIn("template", payload["answer"].lower())

    def test_post_answer_contract_audit_skips_value_echo_condition(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When does the user prefer watching esports?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "memory_validity_controller_action": {
                    "action": "condition_scope_packet",
                    "question_fingerprint": (
                        "When does the user prefer watching esports?"
                    ),
                },
                "condition_scope_context": [
                    {
                        "memory_id": "esports_background",
                        "exact_condition": "when i m decompressing",
                        "supporting_value": "esports streams as background",
                        "source_excerpt": (
                            "I tend to put on esports streams as background "
                            "when I'm decompressing."
                        ),
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "The user prefers watching esports when they're decompressing."
                ),
                "used_memory_ids": ["esports_background"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertIn("esports streams as background", payload["answer"])
        self.assertIn("decompressing", payload["answer"])
        self.assertNotIn("on esports streams", payload["answer"])

    def test_post_answer_temporal_audit_judge_gets_temporal_support(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_temporal_adapter_item()],
                qvf_requests=[_temporal_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        direct_item = [
            item for item in items if item["method"] == "direct_extracted_memories"
        ][0]
        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        content = json.dumps(
            {
                "answer": "Melanie is planning on going camping next month.",
                "used_memory_ids": ["melanie_camping"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        direct_judge_payload = json.loads(_judge_messages(direct_item, repaired)[1]["content"])
        qvf_judge_payload = json.loads(_judge_messages(qvf_item, repaired)[1]["content"])

        self.assertTrue(audit["applied"])
        self.assertEqual(qvf_item["target_messages"], direct_item["target_messages"])
        self.assertNotIn("post_answer_audit_support", direct_judge_payload["memory_context"])
        self.assertIn("post_answer_audit_support", qvf_judge_payload["memory_context"])
        support = qvf_judge_payload["memory_context"]["post_answer_audit_support"]
        self.assertEqual(
            support["temporal_resolution_context"][0]["preferred_answer"],
            "June 2023",
        )

    def test_post_answer_temporal_audit_replaces_wrong_temporal_value_when_memory_used(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_month_age_temporal_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_month_age_temporal_adapter_item()],
                qvf_requests=[_month_age_temporal_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        content = json.dumps(
            {
                "answer": "Audrey adopted the first three dogs in 2021.",
                "used_memory_ids": ["audrey_dogs"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(payload["answer"], "2020")

    def test_post_answer_temporal_audit_does_not_replace_age_at_event_with_year(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "How old were you when you moved to the United States?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "age_now",
                        "phrase": "32-year-old",
                        "observed_at": "2023-01-01T00:00:00+00:00",
                        "resolved_time": "1991",
                        "preferred_answer": "1991",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "The memories do not state the exact age directly, but the "
                    "user is currently 32 and has lived in the U.S. for five "
                    "years, so they moved at age 27."
                ),
                "used_memory_ids": ["age_now", "visa_duration"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(
            audit["reason"],
            "age_at_event_requires_age_scalar_not_year_hint",
        )
        self.assertEqual(json.loads(repaired)["answer"], json.loads(content)["answer"])

    def test_post_answer_temporal_audit_repairs_elapsed_duration_from_anchor_pair(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                "How many days ago did I attend a baking class at a local "
                "culinary school when I made my friend's birthday cake?"
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m_baking",
                        "phrase": "yesterday",
                        "observed_at": "2022-03-21T15:54:00+00:00",
                        "resolved_time": "2022-03-20",
                        "preferred_answer": "2022-03-20",
                        "claim": "User attended a baking class at a local culinary school yesterday.",
                        "value": "yesterday",
                    },
                    {
                        "memory_id": "m_cake",
                        "phrase": "today",
                        "observed_at": "2022-04-10T14:14:00+00:00",
                        "resolved_time": "2022-04-10",
                        "preferred_answer": "2022-04-10",
                        "claim": "User made a chocolate cake for a friend's birthday party today.",
                        "value": "chocolate cake",
                    },
                    {
                        "memory_id": "m_noisy_party",
                        "phrase": "three weeks ago",
                        "observed_at": "2022-03-27T18:27:00+00:00",
                        "resolved_time": "2022-03-06",
                        "preferred_answer": "2022-03-06",
                        "claim": "User attended a birthday party for a friend three weeks ago.",
                        "value": "birthday party",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "I attended the baking class yesterday, which means it was 1 day ago.",
                "used_memory_ids": ["m_baking"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(audit["duration_days"], 21)
        self.assertEqual(audit["replacement"], "21 days")
        self.assertEqual(payload["answer"], "21 days")
        self.assertEqual(payload["used_memory_ids"], ["m_baking", "m_cake"])

    def test_post_answer_temporal_audit_elapsed_duration_requires_two_anchors(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "How many days ago did I attend a baking class when I made the cake?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m_baking",
                        "phrase": "yesterday",
                        "observed_at": "2022-03-21T15:54:00+00:00",
                        "resolved_time": "2022-03-20",
                        "preferred_answer": "2022-03-20",
                        "claim": "User attended a baking class yesterday.",
                    }
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "I attended the baking class yesterday.",
                "used_memory_ids": ["m_baking"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(audit["reason"], "elapsed_duration_needs_two_temporal_anchors")
        self.assertEqual(repaired, content)

    def test_post_answer_temporal_audit_elapsed_duration_rejects_weak_reference_anchor(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                "How many days ago did I attend a baking class at a local "
                "culinary school when I made my friend's birthday cake?"
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m_baking",
                        "phrase": "yesterday",
                        "observed_at": "2022-03-21T15:54:00+00:00",
                        "resolved_time": "2022-03-20",
                        "preferred_answer": "2022-03-20",
                        "claim": "User attended a baking class at a local culinary school yesterday.",
                    },
                    {
                        "memory_id": "m_noisy_party",
                        "phrase": "three weeks ago",
                        "observed_at": "2022-03-27T18:27:00+00:00",
                        "resolved_time": "2022-03-06",
                        "preferred_answer": "2022-03-06",
                        "claim": "User attended a birthday party for a friend three weeks ago.",
                        "value": "birthday party",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "I attended the baking class yesterday.",
                "used_memory_ids": ["m_baking"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(
            audit["reason"],
            "elapsed_duration_reference_anchor_below_alignment_threshold",
        )
        self.assertEqual(repaired, content)

    def test_post_answer_temporal_audit_explicit_before_clause_rejects_loose_fallback(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                "How many days before my best friend's birthday party did I "
                "order her gift?"
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m_party",
                        "phrase": "April 22nd",
                        "observed_at": "2023-04-22T00:00:00+00:00",
                        "resolved_time": "2023-04-22",
                        "preferred_answer": "2023-04-22",
                        "claim": "User celebrated their best friend's birthday party on April 22nd.",
                        "value": "best friend's birthday party",
                    },
                    {
                        "memory_id": "m_engagement",
                        "phrase": "May 15th",
                        "observed_at": "2023-05-15T00:00:00+00:00",
                        "resolved_time": "2023-05-15",
                        "preferred_answer": "2023-05-15",
                        "claim": "User's close friend Rachel got engaged on May 15th.",
                        "source_span": (
                            "My close friend Rachel got engaged and I am "
                            "planning a party and gift."
                        ),
                        "value": "Rachel's engagement",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "7 days",
                "used_memory_ids": ["m_party"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(
            audit["reason"],
            "elapsed_duration_before_after_clause_no_unique_pair",
        )
        self.assertEqual(json.loads(repaired)["answer"], "7 days")

    def test_post_answer_temporal_audit_repairs_source_backed_explicit_date_pair(self) -> None:
        question = (
            "How many days had passed between the Hindu festival of Holi and "
            "the Sunday mass at St. Mary's Church?"
        )
        rows = [
            {
                "memory_id": "m_holi",
                "claim": "The user attended the Holi celebration at their local temple on February 26th.",
                "value": "February 26th",
                "observed_at": "2023-03-26T12:48:00+00:00",
                "source_span": "I just attended the Holi celebration at my local temple on February 26th.",
            },
            {
                "memory_id": "m_mass",
                "claim": "The user attended Sunday mass at St. Mary's Church on March 19th.",
                "value": "March 19th",
                "observed_at": "2023-03-26T01:51:00+00:00",
                "source_span": "I just got back from Sunday mass at St. Mary's Church on March 19th.",
            },
        ]
        temporal_context = _build_temporal_resolution_context(
            {"query_requests": [{"question": question}]},
            rows,
        )
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": question,
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": temporal_context,
            },
        }
        content = json.dumps(
            {
                "answer": "It was around 0 days.",
                "used_memory_ids": ["m_holi"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(audit["duration_days"], 21)
        self.assertEqual(payload["answer"], "21 days")
        self.assertEqual(set(payload["used_memory_ids"]), {"m_holi", "m_mass"})
        self.assertEqual(
            {row["resolution_note"] for row in temporal_context},
            {"source-backed explicit event date from claim"},
        )

    def test_post_answer_temporal_audit_between_clause_pair_breaks_used_memory_tie(self) -> None:
        question = (
            "How many days had passed between the Hindu festival of Holi and "
            "the Sunday mass at St. Mary's Church?"
        )
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": question,
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m_mass",
                        "phrase": "March 19th",
                        "observed_at": "2023-03-26T01:51:00+00:00",
                        "resolved_time": "2023-03-19",
                        "preferred_answer": "2023-03-19",
                        "claim": "The user attended Sunday mass at St. Mary's Church on March 19th.",
                    },
                    {
                        "memory_id": "m_holi",
                        "phrase": "February 26th",
                        "observed_at": "2023-03-26T12:48:00+00:00",
                        "resolved_time": "2023-02-26",
                        "preferred_answer": "2023-02-26",
                        "claim": "The user attended the Holi celebration at their local temple on February 26th.",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "0 days",
                "used_memory_ids": ["m_holi", "m_mass"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(audit["reason"], "elapsed_duration_between_clause_anchor_pair")
        self.assertEqual(audit["duration_days"], 21)
        self.assertEqual(payload["answer"], "21 days")
        self.assertEqual(set(payload["used_memory_ids"]), {"m_holi", "m_mass"})

    def test_post_answer_temporal_audit_between_clause_rejects_irrelevant_pair(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": (
                "How many days passed between the Holiday Market and the day "
                "I bought the iPhone 13 Pro?"
            ),
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m_iphone",
                        "phrase": "March 16, 2023",
                        "observed_at": "2023-12-10T13:33:00+00:00",
                        "resolved_time": "2023-03-16",
                        "preferred_answer": "2023-03-16",
                        "claim": "User bought the iPhone 13 Pro on March 16, 2023.",
                    },
                    {
                        "memory_id": "m_departure",
                        "phrase": "March 21, 2023",
                        "observed_at": "2023-12-10T13:33:00+00:00",
                        "resolved_time": "2023-03-21",
                        "preferred_answer": "2023-03-21",
                        "claim": "User will depart Tokyo on March 21, 2023.",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "5 days",
                "used_memory_ids": ["m_iphone", "m_departure"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(
            audit["reason"],
            "elapsed_duration_between_clause_no_unique_pair",
        )
        self.assertEqual(repaired, content)

    def test_temporal_context_rejects_extractor_only_date_with_empty_source_span(self) -> None:
        question = (
            "How many days before I bought the iPhone 13 Pro did I attend "
            "the Holiday Market?"
        )
        rows = [
            {
                "memory_id": "m_iphone",
                "claim": "User bought the iPhone 13 Pro on March 16, 2023.",
                "value": "2023-03-16",
                "observed_at": "2023-12-10T13:33:00+00:00",
                "source_span": "The trip starts on 3/16/2023.",
            },
            {
                "memory_id": "m_market",
                "claim": "User attended the annual Holiday Market a week before Black Friday.",
                "value": "2022-11-18",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source_span": "",
            },
        ]
        temporal_context = _build_temporal_resolution_context(
            {"query_requests": [{"question": question}]},
            rows,
        )

        self.assertTrue(
            any(row["memory_id"] == "m_iphone" for row in temporal_context)
        )
        self.assertFalse(
            any(row["memory_id"] == "m_market" for row in temporal_context)
        )

    def test_temporal_context_resolves_named_calendar_relative_anchor_pair(self) -> None:
        question = (
            "How many days before I bought the iPhone 13 Pro did I attend "
            "the Holiday Market?"
        )
        rows = [
            {
                "memory_id": "m_wrong_travel_date",
                "claim": "User bought the iPhone 13 Pro on March 16, 2023.",
                "value": "2023-03-16",
                "observed_at": "2023-12-10T13:33:00+00:00",
                "source_span": (
                    "My wife and I are going to fly to Tokyo and land in Narita "
                    "airport at 14:30 3/16/2023."
                ),
            },
            {
                "memory_id": "m_best_buy_black_friday",
                "claim": (
                    "User bought the iPhone 13 Pro at a discounted price of $800 "
                    "from Best Buy."
                ),
                "value": "$800",
                "observed_at": "2023-12-10T14:52:00+00:00",
                "source_span": (
                    "I got my iPhone 13 Pro at a discounted price of $800 from "
                    "Best Buy on Black Friday."
                ),
            },
            {
                "memory_id": "m_market",
                "claim": "User attended the annual Holiday Market a week before Black Friday.",
                "value": "2022-11-18",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source_span": "",
            },
        ]

        temporal_context = _build_temporal_resolution_context(
            {"query_requests": [{"question": question}]},
            rows,
        )

        by_memory = {
            (row["memory_id"], row["resolved_time"], row["resolution_note"])
            for row in temporal_context
        }
        self.assertIn(
            (
                "m_best_buy_black_friday",
                "2023-11-24",
                "source-backed named calendar event: black friday",
            ),
            by_memory,
        )
        self.assertIn(
            (
                "m_market",
                "2023-11-17",
                (
                    "named calendar relative event from retrieved claim using "
                    "source-backed black friday"
                ),
            ),
            by_memory,
        )
        self.assertFalse(
            any(
                row["memory_id"] == "m_market" and row["resolved_time"] == "2022-11-18"
                for row in temporal_context
            )
        )

    def test_temporal_context_uses_nested_long_source_span_for_named_calendar_anchor(self) -> None:
        question = (
            "How many days before I bought the iPhone 13 Pro did I attend "
            "the Holiday Market?"
        )
        long_prefix = "case recommendation. " * 55
        rows = [
            {
                "memory_id": "m_best_buy_black_friday",
                "claim": (
                    "User bought the iPhone 13 Pro at a discounted price of $800 "
                    "from Best Buy."
                ),
                "value": "$800",
                "observed_at": "2023-12-10T14:52:00+00:00",
                "source": {
                    "source_span": (
                        long_prefix
                        + "I got my iPhone 13 Pro at a discounted price of $800 "
                        "from Best Buy on Black Friday."
                    )
                },
            },
            {
                "memory_id": "m_market",
                "claim": "User attended the annual Holiday Market a week before Black Friday.",
                "value": "2022-11-18",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source_span": "",
            },
        ]

        temporal_context = _build_temporal_resolution_context(
            {"query_requests": [{"question": question}]},
            rows,
        )

        self.assertTrue(
            any(
                row["memory_id"] == "m_best_buy_black_friday"
                and row["resolved_time"] == "2023-11-24"
                for row in temporal_context
            )
        )
        self.assertTrue(
            any(
                row["memory_id"] == "m_market"
                and row["resolved_time"] == "2023-11-17"
                for row in temporal_context
            )
        )

    def test_post_answer_temporal_audit_before_after_uses_source_supported_named_anchor(self) -> None:
        question = (
            "How many days before I bought the iPhone 13 Pro did I attend "
            "the Holiday Market?"
        )
        temporal_context = [
            {
                "memory_id": "m_wrong_travel_date",
                "phrase": "March 16, 2023",
                "observed_at": "2023-12-10T13:33:00+00:00",
                "resolved_time": "2023-03-16",
                "preferred_answer": "2023-03-16",
                "claim": "User bought the iPhone 13 Pro on March 16, 2023.",
                "source_span": (
                    "My wife and I are going to fly to Tokyo and land in Narita "
                    "airport at 14:30 3/16/2023."
                ),
            },
            {
                "memory_id": "m_best_buy_black_friday",
                "phrase": "Black Friday",
                "observed_at": "2023-12-10T14:52:00+00:00",
                "resolved_time": "2023-11-24",
                "preferred_answer": "2023-11-24",
                "resolution_note": "source-backed named calendar event: black friday",
                "claim": (
                    "User bought the iPhone 13 Pro at a discounted price of $800 "
                    "from Best Buy."
                ),
                "source_span": (
                    "I got my iPhone 13 Pro at a discounted price of $800 from "
                    "Best Buy on Black Friday."
                ),
            },
            {
                "memory_id": "m_market",
                "phrase": "a week before Black Friday",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "resolved_time": "2023-11-17",
                "preferred_answer": "2023-11-17",
                "resolution_note": (
                    "named calendar relative event from retrieved claim using "
                    "source-backed black friday"
                ),
                "claim": "User attended the annual Holiday Market a week before Black Friday.",
                "source_span": "",
            },
        ]
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": question,
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": temporal_context,
            },
        }
        content = json.dumps(
            {
                "answer": (
                    "User attended the Holiday Market on November 18, 2022, "
                    "and bought the iPhone 13 Pro on March 16, 2023. Therefore, "
                    "the number of days between these two events is 118 days."
                ),
                "used_memory_ids": ["m_wrong_travel_date", "m_market"],
                "abstained": [],
            }
        )

        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)
        payload = json.loads(repaired)

        self.assertTrue(audit["applied"])
        self.assertEqual(
            audit["reason"],
            "elapsed_duration_before_after_clause_anchor_pair",
        )
        self.assertEqual(audit["duration_days"], 7)
        self.assertEqual(payload["answer"], "7 days")
        self.assertEqual(
            set(payload["used_memory_ids"]),
            {"m_market", "m_best_buy_black_friday"},
        )

    def test_temporal_context_does_not_add_explicit_dates_for_single_anchor_recall(self) -> None:
        question = "What kitchen appliance did I buy 10 days ago?"
        rows = [
            {
                "memory_id": "m_blender",
                "claim": "User bought a blender on February 10th.",
                "value": "February 10th",
                "observed_at": "2023-02-20T00:00:00+00:00",
                "source_span": "I bought a blender on February 10th.",
            },
        ]

        temporal_context = _build_temporal_resolution_context(
            {"query_requests": [{"question": question}]},
            rows,
        )

        self.assertEqual(temporal_context, [])

    def test_post_answer_temporal_audit_leaves_ambiguous_abstention_unchanged(self) -> None:
        qvf_item = {
            "method": "qvf_validity_packed_context",
            "question": "When did the user attend the event?",
            "context": {
                "qvf_context_variant": "post_answer_audit_controller",
                "direct_recall_context": {"retrieved_memories": []},
                "memory_validity_controller_action": {
                    "action": "raw_recall_with_annotations",
                },
                "temporal_resolution_context": [
                    {
                        "memory_id": "m1",
                        "phrase": "last week",
                        "resolved_time": "week before 2023-07-16",
                        "preferred_answer": "the week before 16 July 2023",
                    },
                    {
                        "memory_id": "m2",
                        "phrase": "last month",
                        "resolved_time": "June 2023",
                        "preferred_answer": "June 2023",
                    },
                ],
            },
        }
        content = json.dumps(
            {
                "answer": "The memories do not specify the date.",
                "used_memory_ids": [],
                "abstained": ["insufficient_evidence"],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(qvf_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(json.loads(repaired)["answer"], "The memories do not specify the date.")

    def test_post_answer_temporal_audit_leaves_direct_item_unchanged(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_temporal_adapter_item()],
                qvf_requests=[_temporal_qvf_request()],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        direct_item = [
            item for item in items if item["method"] == "direct_extracted_memories"
        ][0]
        content = json.dumps(
            {
                "answer": "Melanie is planning on going camping next month.",
                "used_memory_ids": ["melanie_camping"],
                "abstained": [],
            }
        )
        repaired, audit = _post_answer_temporal_audit_content(direct_item, content)

        self.assertFalse(audit["applied"])
        self.assertEqual(repaired, content)

    def test_qvf_answer_context_adaptive_uses_evidence_preserving_for_plain_recall(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            context = _qvf_context(_plain_recall_qvf_request())

        self.assertEqual(context["qvf_context_variant"], "adaptive")
        self.assertEqual(
            context["effective_qvf_context_variant"],
            "evidence_preserving",
        )
        self.assertTrue(context["extracted_memory_context"])
        self.assertEqual(
            context["evidence_preservation_policy"]["routing_mode"],
            "preserve_first",
        )

    def test_selective_router_adds_third_method_and_routes_current_queries_to_qvf(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_adapter_item()],
                qvf_requests=[_qvf_request()],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective = by_method["qvf_selective_router"]
        target_payload = json.loads(selective["target_messages"][1]["content"])

        self.assertEqual(len(items), 3)
        self.assertEqual(selective["context"]["selected_method"], "qvf_validity_packed_context")
        self.assertTrue(selective["context"]["query_risk_route"]["should_apply_qvf"])
        self.assertEqual(selective["target_messages"], by_method["qvf_validity_packed_context"]["target_messages"])
        self.assertNotIn("selective_router_policy", json.dumps(target_payload, ensure_ascii=False))
        self.assertNotIn("query-risk router selected", json.dumps(target_payload, ensure_ascii=False))
        self.assertIn("evidence_preservation_policy", target_payload["memory_context"])
        self.assertIn("extracted_memory_context", target_payload["memory_context"])
        self.assertIn("current_answer_context", json.dumps(target_payload, ensure_ascii=False))
        self.assertNotIn("SECRET_GOLD_ANSWER", json.dumps(target_payload, ensure_ascii=False))

    def test_selective_router_routes_implicit_recommendation_conflict_to_qvf(self) -> None:
        request = _qvf_request()
        request["request_id"] = "public_extraction_public_case_implicit_conflict"
        request["step_id"] = "public_extraction_step_public_case_implicit_conflict"
        request["query_requests"] = [
            {
                "request_id": "q_public_case_implicit_conflict",
                "question": (
                    "Since Maya has lived in Rome for years, can you recommend "
                    "Rome-specific neighborhood resources she should sign up for right now?"
                ),
                "entity": "Maya",
                "slot": "home_city",
                "premise_value": "Rome",
            }
        ]
        adapter_item = {
            "case_id": "public_case_implicit_conflict",
            "question": request["query_requests"][0]["question"],
            "answers": ["SECRET_IMPLICIT_CONFLICT_ANSWER"],
        }

        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[adapter_item],
                qvf_requests=[request],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective = by_method["qvf_selective_router"]
        route = selective["context"]["query_risk_route"]

        self.assertEqual(selective["context"]["selected_method"], "qvf_validity_packed_context")
        self.assertEqual(selective["context"]["selection_reason"], "retrieved_evidence_conflict")
        self.assertEqual(route["recommended_route"], "qvf_evidence_conflict_router")
        self.assertEqual(route["evidence_risk"]["conflict_group_count"], 1)
        self.assertEqual(selective["target_messages"], by_method["qvf_validity_packed_context"]["target_messages"])
        self.assertNotIn(
            "SECRET_IMPLICIT_CONFLICT_ANSWER",
            json.dumps(selective["target_messages"], ensure_ascii=False),
        )

    def test_selective_router_keeps_plain_recall_on_direct_preserve_first(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_plain_recall_adapter_item()],
                qvf_requests=[_plain_recall_qvf_request()],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective = by_method["qvf_selective_router"]
        target_payload = json.loads(selective["target_messages"][1]["content"])

        self.assertEqual(selective["context"]["selected_method"], "direct_extracted_memories")
        self.assertFalse(selective["context"]["query_risk_route"]["should_apply_qvf"])
        self.assertEqual(selective["target_messages"], by_method["direct_extracted_memories"]["target_messages"])
        self.assertEqual(
            target_payload["memory_context"]["context_type"],
            "direct_extracted_memories",
        )
        self.assertNotIn("selective_router_policy", json.dumps(target_payload, ensure_ascii=False))
        self.assertNotIn("query-risk router selected", json.dumps(target_payload, ensure_ascii=False))
        self.assertNotIn("qvf_read_time_decision", json.dumps(target_payload, ensure_ascii=False))

    def test_selective_router_keeps_before_move_history_on_direct_preserve_first(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_historical_adapter_item()],
                qvf_requests=[_historical_qvf_request()],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective = by_method["qvf_selective_router"]
        target_payload = json.loads(selective["target_messages"][1]["content"])

        self.assertEqual(selective["context"]["selected_method"], "direct_extracted_memories")
        self.assertFalse(selective["context"]["query_risk_route"]["should_apply_qvf"])
        self.assertEqual(selective["target_messages"], by_method["direct_extracted_memories"]["target_messages"])
        self.assertNotIn("selective_router_policy", json.dumps(target_payload, ensure_ascii=False))
        self.assertNotIn("query-risk router selected", json.dumps(target_payload, ensure_ascii=False))
        self.assertNotIn("qvf_read_time_decision", json.dumps(target_payload, ensure_ascii=False))

    def test_selective_router_routes_change_detail_when_transition_context_exists(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[
                    {
                        "case_id": "change_demo",
                        "question": "How did the user's residence change?",
                        "answers": ["SECRET_CHANGE_ANSWER"],
                    }
                ],
                qvf_requests=[_transition_qvf_request()],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective = by_method["qvf_selective_router"]
        route = selective["context"]["query_risk_route"]

        self.assertEqual(selective["context"]["selected_method"], "qvf_validity_packed_context")
        self.assertEqual(selective["context"]["selection_reason"], "change_detail_or_transition")
        self.assertEqual(route["recommended_route"], "qvf_transition_router")
        self.assertEqual(selective["target_messages"], by_method["qvf_validity_packed_context"]["target_messages"])
        self.assertNotIn(
            "SECRET_CHANGE_ANSWER",
            json.dumps(selective["target_messages"], ensure_ascii=False),
        )

    def test_selective_router_overrides_direct_for_yes_no_dynamic_change(self) -> None:
        selected_method, reason = _selective_router_selected_method(
            {
                "query_text": "Did the user's marital status change recently?",
                "recommended_route": "direct_preserve_first",
                "should_apply_qvf": False,
                "query_type": "ordinary_recall",
            },
            {
                "transition_context": [
                    {
                        "slot": "marital_status",
                        "previous_value": "unknown",
                        "current_value": "dating Michelle Williams",
                    }
                ],
                "validity_controller_decision": {
                    "evidence_sufficiency": "no_visible_answer_evidence",
                    "next_action": "retrieve_entity_slot_timeline",
                },
            },
        )

        self.assertEqual(selected_method, "qvf_validity_packed_context")
        self.assertEqual(reason, "dynamic_change_transition_override")

    def test_selective_router_overrides_direct_for_career_field_change(self) -> None:
        selected_method, reason = _selective_router_selected_method(
            {
                "query_text": "What changed about their job title?",
                "recommended_route": "qvf_transition_router",
                "should_apply_qvf": True,
                "query_type": "temporal_reasoning",
            },
            {
                "change_detail_context": [
                    {
                        "detail_type": "career_change",
                        "summary": "job_title changed from Senior to Junior.",
                    }
                ],
                "validity_controller_decision": {
                    "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                    "next_action": "answer_from_archive",
                },
            },
        )

        self.assertEqual(selected_method, "qvf_validity_packed_context")
        self.assertEqual(reason, "dynamic_change_transition_override")

    def test_selective_router_keeps_movement_from_to_direct(self) -> None:
        selected_method, reason = _selective_router_selected_method(
            {
                "query_text": "Where did the user move from and to?",
                "recommended_route": "direct_preserve_first",
                "should_apply_qvf": False,
                "query_type": "ordinary_recall",
            },
            {
                "transition_context": [
                    {
                        "slot": "residence",
                        "previous_value": "Singapore",
                        "current_value": "Frankfurt, Germany",
                    }
                ],
            },
        )

        self.assertEqual(selected_method, "direct_extracted_memories")
        self.assertEqual(reason, "direct_non_degradation")

    def test_selective_router_keeps_open_social_status_change_direct(self) -> None:
        selected_method, reason = _selective_router_selected_method(
            {
                "query_text": "How did the user's social status change?",
                "recommended_route": "qvf_transition_router",
                "should_apply_qvf": True,
                "query_type": "temporal_reasoning",
            },
            {
                "transition_context": [
                    {
                        "slot": "social_energy",
                        "previous_value": "a bit overwhelmed",
                        "current_value": "exciting",
                    }
                ],
                "validity_controller_decision": {
                    "evidence_sufficiency": "sufficient_archive_or_historical_evidence",
                    "next_action": "answer_from_archive",
                },
            },
        )

        self.assertEqual(selected_method, "direct_extracted_memories")
        self.assertEqual(reason, "direct_controller_preserve_raw_memory")

    def test_selective_router_routes_condition_preference_when_scope_context_exists(self) -> None:
        request = _condition_scope_qvf_request()
        adapter_item = {
            "case_id": "condition_scope",
            "question": request["query_requests"][0]["question"],
            "answers": ["SECRET_CONDITION_ANSWER"],
        }

        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_condition_scope_qvf_response(),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[adapter_item],
                qvf_requests=[request],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective = by_method["qvf_selective_router"]
        route = selective["context"]["query_risk_route"]

        self.assertEqual(selective["context"]["selected_method"], "qvf_validity_packed_context")
        self.assertEqual(selective["context"]["selection_reason"], "condition_preference_scope")
        self.assertEqual(route["recommended_route"], "qvf_conditional_scope_router")
        self.assertEqual(selective["target_messages"], by_method["qvf_validity_packed_context"]["target_messages"])
        self.assertNotIn(
            "SECRET_CONDITION_ANSWER",
            json.dumps(selective["target_messages"], ensure_ascii=False),
        )

    def test_qvf_answer_context_adaptive_uses_route_first_for_temporal_questions(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            request = _temporal_qvf_request()
            request["records"] = _plain_recall_qvf_request()["records"]
            context = _qvf_context(request)

        self.assertEqual(context["qvf_context_variant"], "adaptive")
        self.assertEqual(context["effective_qvf_context_variant"], "full")
        self.assertTrue(context["extracted_memory_context"])
        self.assertEqual(
            context["evidence_preservation_policy"]["routing_mode"],
            "route_first",
        )
        self.assertTrue(context["temporal_resolution_context"])

    def test_qvf_answer_context_evidence_preserving_uses_preserve_first_for_plain_recall(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            context = _qvf_context(
                _plain_recall_qvf_request(),
                qvf_context_variant="evidence_preserving",
            )

        self.assertEqual(
            context["evidence_preservation_policy"]["routing_mode"],
            "preserve_first",
        )

    def test_qvf_answer_context_evidence_preserving_uses_route_first_for_temporal_questions(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            context = _qvf_context(
                _temporal_qvf_request(),
                qvf_context_variant="evidence_preserving",
            )

        self.assertEqual(
            context["evidence_preservation_policy"]["routing_mode"],
            "route_first",
        )
        self.assertTrue(context["temporal_resolution_context"])

    def test_qvf_answer_context_builds_transition_context_for_change_questions(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            context = _qvf_context(_transition_qvf_request())

        rendered_target = json.dumps(
            _target_messages(
                question="How did the user's residence change?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(context["transition_context"][0]["slot"], "residence")
        self.assertEqual(context["transition_context"][0]["previous_value"], "Darwin")
        self.assertEqual(context["transition_context"][0]["current_value"], "Melbourne")
        self.assertIn("residence changed from Darwin to Melbourne", rendered_target)

    def test_transition_context_filters_children_status_sibling_distractor(self) -> None:
        transitions = _build_transition_context(
            {
                "query_requests": [
                    {
                        "question": "How has the user's children status changed?",
                        "entity": "user",
                        "slot": "children_status",
                    }
                ],
                "records": [
                    {
                        "memory_id": "baby_update",
                        "entity": "user",
                        "slot": "children_status",
                        "claim": (
                            "The user recently had a baby, Christopher Moore, "
                            "born 2022-05-01."
                        ),
                        "value": (
                            "has a child named Christopher Moore born on "
                            "2022-05-01"
                        ),
                        "observed_at": "2022-05-01T00:00:00+00:00",
                    },
                    {
                        "memory_id": "no_children_before",
                        "entity": "user",
                        "slot": "children_status",
                        "claim": "User mentioned they don't have children.",
                        "value": "does not have children",
                        "observed_at": "2022-01-07T00:00:00+00:00",
                    },
                    {
                        "memory_id": "sibling_distractor",
                        "entity": "user",
                        "slot": "children_status",
                        "claim": (
                            "User has siblings, including a brother who travels "
                            "to London."
                        ),
                        "value": "has a brother who travels to London",
                        "observed_at": "2022-05-01T00:00:00+00:00",
                    },
                ],
            }
        )

        self.assertTrue(transitions)
        self.assertEqual(transitions[0]["slot"], "children_status")
        self.assertEqual(transitions[0]["previous_value"], "does not have children")
        self.assertIn("Christopher Moore", transitions[0]["current_value"])
        self.assertEqual(transitions[0]["current_memory_id"], "baby_update")

    def test_transition_context_maps_children_entity_status_query(self) -> None:
        transitions = _build_transition_context(
            {
                "query_requests": [
                    {
                        "question": "Has the user's children status changed recently?",
                        "entity": "children",
                        "slot": "status",
                    }
                ],
                "records": [
                    {
                        "memory_id": "child_name",
                        "entity": "child",
                        "slot": "name",
                        "claim": (
                            "User recently had a baby, Christopher Moore, born "
                            "2022-05-01."
                        ),
                        "value": "Christopher Moore",
                        "observed_at": "2022-05-01T00:00:00+00:00",
                    },
                    {
                        "memory_id": "child_birth_date",
                        "entity": "child",
                        "slot": "birth_date",
                        "claim": (
                            "User recently had a baby, Christopher Moore, born "
                            "2022-05-01."
                        ),
                        "value": "2022-05-01",
                        "observed_at": "2022-05-01T00:00:00+00:00",
                    },
                    {
                        "memory_id": "no_children",
                        "entity": "children",
                        "slot": "status",
                        "claim": "User mentioned they don't have children.",
                        "value": "does not have children",
                        "observed_at": "2022-01-07T00:00:00+00:00",
                    },
                    {
                        "memory_id": "brother",
                        "entity": "children",
                        "slot": "brother",
                        "claim": "User has a brother who travels to London.",
                        "value": "has a brother who travels to London",
                        "observed_at": "2022-05-01T00:00:00+00:00",
                    },
                ],
            }
        )

        self.assertTrue(transitions)
        self.assertEqual(transitions[0]["slot"], "children_status")
        self.assertEqual(transitions[0]["previous_memory_id"], "no_children")
        self.assertEqual(transitions[0]["current_memory_id"], "child_name")

    def test_transition_previous_state_is_not_labeled_current(self) -> None:
        current_context, historical_context = (
            _reconcile_current_context_with_transition_context(
                current_context=[
                    {
                        "memory_id": "no_children",
                        "claim": "User mentioned they do not have children.",
                        "value": "does not have children",
                    },
                    {
                        "memory_id": "other_current",
                        "claim": "User has a current preference.",
                        "value": "current preference",
                    },
                ],
                historical_context=[],
                transition_context=[
                    {
                        "slot": "children_status",
                        "previous_memory_id": "no_children",
                        "current_memory_id": "child_name",
                    }
                ],
            )
        )

        self.assertEqual([row["memory_id"] for row in current_context], ["other_current"])
        self.assertEqual([row["memory_id"] for row in historical_context], ["no_children"])
        self.assertEqual(
            historical_context[0]["reconciliation_reason"],
            "transition_previous_state_not_current",
        )

    def test_transition_context_filters_social_status_action_plan_distractors(self) -> None:
        transitions = _build_transition_context(
            {
                "query_requests": [
                    {
                        "question": "What changed in the user's social status?",
                        "entity": "user",
                        "slot": "social_status",
                    }
                ],
                "records": [
                    {
                        "memory_id": "less_social_before",
                        "entity": "user",
                        "slot": "social_status",
                        "claim": "User was spending less time socializing.",
                        "value": "spending less time socializing",
                        "observed_at": "2022-01-07T00:00:00+00:00",
                    },
                    {
                        "memory_id": "more_social_now",
                        "entity": "user",
                        "slot": "social_status",
                        "claim": (
                            "User has become more social due to remote work "
                            "flexibility and spontaneous invites."
                        ),
                        "value": "more social due to spontaneous invites",
                        "observed_at": "2022-07-10T00:00:00+00:00",
                    },
                    {
                        "memory_id": "fatigue_side_effect",
                        "entity": "user",
                        "slot": "social_status",
                        "claim": "User experiences social fatigue after two events.",
                        "value": "experiencing social fatigue after two events",
                        "observed_at": "2022-07-10T00:00:00+00:00",
                    },
                    {
                        "memory_id": "event_plan",
                        "entity": "user",
                        "slot": "social_status",
                        "claim": "User committed to one social event next week.",
                        "value": "committed to one social event next week",
                        "observed_at": "2022-07-10T00:00:00+00:00",
                    },
                ],
            }
        )

        self.assertTrue(transitions)
        self.assertEqual(transitions[0]["slot"], "social_status")
        self.assertEqual(transitions[0]["previous_memory_id"], "less_social_before")
        self.assertEqual(transitions[0]["current_memory_id"], "more_social_now")
        self.assertIn("more social", transitions[0]["current_value"])

    def test_transition_context_maps_social_activity_query_to_social_status(self) -> None:
        transitions = _build_transition_context(
            {
                "query_requests": [
                    {
                        "question": "Did the user's social status change recently?",
                        "entity": "user",
                        "slot": "social_activity",
                    }
                ],
                "records": [
                    {
                        "memory_id": "less_social",
                        "entity": "user",
                        "slot": "social_status",
                        "claim": (
                            "Since the move, the user has been spending a lot "
                            "less time socializing."
                        ),
                        "value": "spending a lot less time socializing",
                        "observed_at": "2022-02-19T00:00:00+00:00",
                    },
                    {
                        "memory_id": "meeting_more",
                        "entity": "user",
                        "slot": "social_activity",
                        "claim": (
                            "The user's social life has shifted a lot lately, "
                            "and they are meeting more people than they used to."
                        ),
                        "value": "meeting more people than I used to",
                        "observed_at": "2022-04-25T00:00:00+00:00",
                    },
                    {
                        "memory_id": "frequency_detail",
                        "entity": "user",
                        "slot": "social_activity_frequency",
                        "claim": (
                            "The user is going out several times a week for "
                            "social activities."
                        ),
                        "value": "several times a week",
                        "observed_at": "2022-04-25T00:00:00+00:00",
                    },
                ],
            }
        )

        self.assertTrue(transitions)
        self.assertEqual(transitions[0]["slot"], "social_status")
        self.assertEqual(transitions[0]["previous_memory_id"], "less_social")
        self.assertEqual(transitions[0]["current_memory_id"], "meeting_more")

    def test_qvf_answer_context_builds_transition_for_yes_no_residence_change(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="current_state"),
        ):
            context = _qvf_context(_yes_no_residence_change_qvf_request())

        transition = context["transition_context"][0]

        self.assertEqual(transition["slot"], "residence")
        self.assertEqual(transition["previous_value"], "unknown")
        self.assertEqual(transition["current_value"], "Melbourne")
        self.assertIn("change event inferred", transition["evidence_note"])

    def test_qvf_answer_context_repairs_residence_previous_state_from_selected_history(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_selected_history_residence_adapter_item()],
                qvf_requests=[_selected_history_residence_qvf_request()],
                limit=1,
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        transition = qvf_item["context"]["transition_context"][0]
        rendered_target = json.dumps(qvf_item["target_messages"], ensure_ascii=False)

        self.assertEqual(transition["slot"], "residence")
        self.assertEqual(transition["previous_value"], "Darwin")
        self.assertEqual(transition["current_value"], "Melbourne")
        self.assertEqual(transition["previous_memory_id"], "prior-location-turn")
        self.assertEqual(transition["source_history_repair"], "previous_state_anchor")
        self.assertIn("prior-state evidence", transition["evidence_note"])
        self.assertIn("residence changed from Darwin to Melbourne", rendered_target)

    def test_qvf_answer_context_groups_relationship_alias_for_marital_change(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            context = _qvf_context(_relationship_alias_transition_qvf_request())

        transition = context["transition_context"][0]
        rendered_target = json.dumps(
            _target_messages(
                question="What change occurred in the user's marital status?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(transition["slot"], "marital_status")
        self.assertEqual(transition["previous_value"], "divorced")
        self.assertEqual(transition["current_value"], "dating Helen Wilson")
        self.assertIn(
            "marital_status changed from divorced to dating Helen Wilson",
            rendered_target,
        )
        self.assertNotIn("unknown to dating Helen Wilson", rendered_target)

    def test_qvf_answer_context_groups_previous_relationship_alias_for_marital_change(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            context = _qvf_context(_previous_relationship_alias_transition_qvf_request())

        transition = context["transition_context"][0]
        rendered_target = json.dumps(
            _target_messages(
                question="How did the user's marital status change?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(transition["slot"], "marital_status")
        self.assertEqual(transition["previous_value"], "single")
        self.assertEqual(transition["current_value"], "dating Michelle Williams")
        self.assertEqual(transition["previous_memory_id"], "prior_relationship_status")
        self.assertIn(
            "marital_status changed from single to dating Michelle Williams",
            rendered_target,
        )
        self.assertNotIn("unknown to dating Michelle Williams", rendered_target)

    def test_relationship_alias_transition_does_not_fire_for_yes_no_change(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            context = _qvf_context(_relationship_alias_yes_no_qvf_request())

        rendered_transition = json.dumps(
            context["transition_context"],
            ensure_ascii=False,
        )

        self.assertNotIn("divorced to dating Helen Wilson", rendered_transition)

    def test_qvf_answer_context_builds_transition_for_stayed_same_employment_question(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="historical_recall"),
        ):
            context = _qvf_context(_employment_stayed_same_qvf_request())

        transition = context["transition_context"][0]
        rendered_target = json.dumps(
            _target_messages(
                question="Has the user's employment status stayed the same?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(transition["slot"], "employment_status")
        self.assertEqual(transition["previous_value"], "part-time from home")
        self.assertEqual(transition["current_value"], "internship")
        self.assertEqual(transition["status_class_relation"], "same_coarse_status")
        self.assertEqual(context["status_class_context"][0]["previous_class"], "employed")
        self.assertEqual(context["status_class_context"][0]["current_class"], "employed")
        self.assertEqual(
            context["status_class_context"][0]["preferred_answer"],
            "Yes, the user stayed employed.",
        )
        self.assertIn("status_class_context", rendered_target)
        self.assertIn("the user stayed employed", rendered_target)
        self.assertIn("do not include this detail in a yes/no stayed-same answer", rendered_target)
        self.assertNotIn("employment_status changed from part-time from home to internship", rendered_target)
        self.assertNotIn("begin discreetly exploring opportunities", rendered_target)

    def test_qvf_answer_context_repairs_company_transition_from_source_span(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            context = _source_span_company_transition_qvf_request()
            context = _qvf_context(context)

        transition = context["transition_context"][0]

        self.assertEqual(transition["slot"], "company")
        self.assertEqual(transition["previous_value"], "Future Intelligence")
        self.assertEqual(transition["current_value"], "Northern Logistics")
        self.assertIn("source_span phrase", transition["evidence_note"])
        self.assertEqual(context["status_class_context"], [])

    def test_qvf_answer_context_repairs_job_title_change_from_selected_history(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_selected_history_job_title_adapter_item()],
                qvf_requests=[_selected_history_job_title_qvf_request()],
                limit=1,
            )

        direct_item = [
            item for item in items if item["method"] == "direct_extracted_memories"
        ][0]
        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        rendered_direct = json.dumps(direct_item["target_messages"], ensure_ascii=False)
        rendered_qvf = json.dumps(qvf_item["target_messages"], ensure_ascii=False)

        self.assertNotIn("SECRET_JOB_TITLE_GOLD", rendered_qvf)
        self.assertNotIn("Intern", rendered_direct)
        self.assertEqual(
            qvf_item["context"]["change_detail_context"][0]["field_changes"][0][
                "field"
            ],
            "job_title",
        )
        self.assertIn("job_title changed from Senior to Intern", rendered_qvf)

    def test_qvf_feedback_reconciles_source_supported_current_before_blocking(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_source_supported_current_blocked_qvf_response(),
        ):
            context = _qvf_context(
                _source_supported_current_blocked_qvf_request(),
                qvf_context_variant="post_answer_audit_controller",
            )

        decision = context["qvf_read_time_decision"]
        controller = context["validity_controller_decision"]

        self.assertEqual(decision["decision"], "ADMIT_CURRENT")
        self.assertEqual(decision["answer_policy"], "answer_from_current")
        self.assertEqual(decision["route"], "current_support_reader_reconciled")
        self.assertEqual(
            controller["evidence_sufficiency"],
            "visible_current_answer_evidence",
        )
        self.assertEqual(controller["next_action"], "answer_from_current")
        self.assertNotIn("married_current", controller.get("blocked_as_current_ids", []))
        self.assertEqual(context["retrieval_feedback"], {})

    def test_income_extractor_prefers_income_range_over_savings_range(self) -> None:
        text = (
            "My monthly income falls in the 10,000-25,000 range and "
            "I have savings between 10,000-50,000."
        )

        self.assertEqual(_extract_income_value(text), "10,000-25,000")

    def test_income_extractor_rejects_savings_only_range(self) -> None:
        text = "I have savings between 10,000-50,000."

        self.assertEqual(_extract_income_value(text), "")

    def test_qvf_answer_context_adds_scoped_reader_packet_from_selected_history(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="temporal_reasoning"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_scoped_tea_blend_adapter_item()],
                qvf_requests=[_scoped_tea_blend_qvf_request()],
                limit=1,
                qvf_context_variant="selective_router",
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        selective_item = [
            item for item in items if item["method"] == "qvf_selective_router"
        ][0]
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            qvf_item["context"],
        )
        rendered_qvf = json.dumps(qvf_item["target_messages"], ensure_ascii=False)
        rendered_selective = json.dumps(
            selective_item["target_messages"],
            ensure_ascii=False,
        )

        scoped_packet = qvf_item["context"]["scoped_reader_context"][0]
        top_event = scoped_packet["candidate_events"][0]
        self.assertEqual(top_event["event_title"], "citrus oolong")
        self.assertEqual(top_event["temporal_marker"], "last weekend")
        self.assertEqual(top_event["action_cue"], "tried")
        self.assertEqual(
            target_context["bucket_counts"]["scoped_reader_context"],
            1,
        )
        self.assertEqual(
            selective_item["context"]["selected_method"],
            "qvf_validity_packed_context",
        )
        self.assertEqual(selective_item["target_messages"], qvf_item["target_messages"])
        self.assertIn("scoped_reader_context", rendered_qvf)
        self.assertIn("citrus oolong", rendered_qvf)
        self.assertIn("last weekend", rendered_selective)
        self.assertIn("extracted_memory_context preserves", rendered_selective)
        self.assertNotIn("SECRET_TEA_BLEND_GOLD", rendered_qvf)
        self.assertNotIn("SECRET_TEA_BLEND_GOLD", rendered_selective)

    def test_selective_router_recent_categorical_scope_can_route_to_qvf(self) -> None:
        adapter_item = _scoped_tea_blend_adapter_item()
        adapter_item.pop("extraction_work_item", None)
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="temporal_reasoning"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[adapter_item],
                qvf_requests=[_scoped_tea_blend_qvf_request()],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective_item = by_method["qvf_selective_router"]

        self.assertEqual(
            selective_item["context"]["query_risk_route"]["recommended_route"],
            "qvf_hybrid_router",
        )
        self.assertEqual(
            selective_item["context"]["selected_method"],
            "qvf_validity_packed_context",
        )
        self.assertEqual(
            selective_item["context"]["selection_reason"],
            "recent_categorical_scope_selection",
        )
        self.assertEqual(
            selective_item["target_messages"],
            by_method["qvf_validity_packed_context"]["target_messages"],
        )

    def test_selective_router_recent_numeric_scope_without_selected_history_stays_direct(self) -> None:
        adapter_item = _scoped_tea_blend_adapter_item()
        adapter_item.pop("extraction_work_item", None)
        adapter_item["question"] = "How many tea blends did I try last weekend?"
        request = _scoped_tea_blend_qvf_request()
        request["query_requests"][0]["question"] = adapter_item["question"]
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="temporal_reasoning"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[adapter_item],
                qvf_requests=[request],
                limit=1,
                qvf_context_variant="selective_router",
            )

        by_method = {item["method"]: item for item in items}
        selective_item = by_method["qvf_selective_router"]

        self.assertEqual(
            selective_item["context"]["query_risk_route"]["recommended_route"],
            "qvf_hybrid_router",
        )
        self.assertEqual(
            selective_item["context"]["selected_method"],
            "direct_extracted_memories",
        )
        self.assertEqual(
            selective_item["target_messages"],
            by_method["direct_extracted_memories"]["target_messages"],
        )

    def test_scoped_reader_does_not_promote_plain_temporal_object_recall(self) -> None:
        adapter_item = {
            "case_id": "plain_temporal_object_recall",
            "question": "What certification did I complete last month?",
            "answers": ["SECRET_CERTIFICATION_GOLD"],
            "extraction_work_item": {
                "history_turns": [
                    {
                        "turn_id": "certification-turn",
                        "timestamp": "2024-05-13",
                        "speaker": "user",
                        "text": (
                            "I completed a Data Science certification last month "
                            "and updated my profile."
                        ),
                        "selection_rank": 1,
                        "selection_score": 11.0,
                    }
                ]
            },
        }
        qvf_request = {
            "request_id": "public_extraction_plain_temporal_object_recall",
            "records": [
                {
                    "memory_id": "certification_memory",
                    "entity": "user",
                    "slot": "certification",
                    "claim": "User completed a Data Science certification last month.",
                    "value": "Data Science",
                    "observed_at": "2024-05-13T00:00:00+00:00",
                    "source": {
                        "source_type": "public_history_extraction",
                        "source_span": (
                            "I completed a Data Science certification last month "
                            "and updated my profile."
                        ),
                    },
                }
            ],
            "query_requests": [
                {
                    "request_id": "q_plain_temporal_object_recall",
                    "question": "What certification did I complete last month?",
                    "entity": "user",
                    "slot": "certification",
                    "needs_current": False,
                }
            ],
        }
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="temporal_reasoning"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[adapter_item],
                qvf_requests=[qvf_request],
                limit=1,
                qvf_context_variant="post_answer_audit_controller",
            )

        by_method = {item["method"]: item for item in items}
        qvf_item = by_method["qvf_validity_packed_context"]

        self.assertFalse(qvf_item["context"]["scoped_reader_context"])

    def test_qvf_answer_context_variant_disables_source_history_repair(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_selected_history_job_title_adapter_item()],
                qvf_requests=[_selected_history_job_title_qvf_request()],
                limit=1,
                qvf_context_variant="no_source_history_repair",
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        rendered_qvf = json.dumps(qvf_item["target_messages"], ensure_ascii=False)

        self.assertEqual(
            qvf_item["context"]["qvf_context_variant"],
            "no_source_history_repair",
        )
        self.assertEqual(qvf_item["context"]["change_detail_context"], [])
        self.assertNotIn("job_title changed from Senior to Intern", rendered_qvf)

    def test_qvf_answer_context_compact_full_keeps_source_history_repair(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_selected_history_job_title_adapter_item()],
                qvf_requests=[_selected_history_job_title_qvf_request()],
                limit=1,
                qvf_context_variant="compact_full",
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]
        rendered_qvf = json.dumps(qvf_item["target_messages"], ensure_ascii=False)

        self.assertEqual(qvf_item["context"]["qvf_context_variant"], "compact_full")
        self.assertEqual(
            qvf_item["context"]["change_detail_context"][0]["field_changes"][0][
                "field"
            ],
            "job_title",
        )
        self.assertIn("job_title changed from Senior to Intern", rendered_qvf)

    def test_qvf_answer_context_core_routing_disables_repair_buckets(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            context = _qvf_context(
                _transition_qvf_request(),
                qvf_context_variant="core_routing",
            )

        self.assertEqual(context["qvf_context_variant"], "core_routing")
        self.assertEqual(context["transition_context"], [])
        self.assertEqual(context["change_detail_context"], [])
        self.assertEqual(context["temporal_resolution_context"], [])
        self.assertEqual(context["query_relevant_context"], [])

    def test_qvf_answer_context_compact_full_keeps_hints_but_compacts_target_rows(self) -> None:
        long_response = _temporal_qvf_response()
        packet = long_response["step_report"]["query_report"]["query_results"][0][
            "packet"
        ]
        packet["compact_validity_packet"]["current_evidence"][0]["source_span"] += (
            " " + "extra detail " * 80
        )
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=long_response,
        ):
            context = _qvf_context(
                _temporal_qvf_request(),
                qvf_context_variant="compact_full",
            )

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertEqual(context["qvf_context_variant"], "compact_full")
        self.assertGreater(len(context["current_answer_context"][0]["source_span"]), 500)
        self.assertLess(
            len(target_context["current_answer_context"][0]["source_span"]),
            260,
        )
        self.assertIn("temporal_resolution_context", target_context)
        self.assertEqual(
            target_context["temporal_resolution_context"][0]["resolved_time"],
            "June 2023",
        )

    def test_qvf_answer_context_auto_compact_compacts_low_risk_temporal_rows(self) -> None:
        long_response = _temporal_qvf_response()
        packet = long_response["step_report"]["query_report"]["query_results"][0][
            "packet"
        ]
        packet["compact_validity_packet"]["current_evidence"][0]["source_span"] += (
            " " + "extra detail " * 80
        )
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=long_response,
        ):
            context = _qvf_context(
                _temporal_qvf_request(),
                qvf_context_variant="auto_compact",
            )

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertEqual(context["target_compaction_policy"]["mode"], "compact")
        self.assertLess(
            len(target_context["current_answer_context"][0]["source_span"]),
            260,
        )

    def test_qvf_answer_context_auto_compact_keeps_full_rows_for_change_questions(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="timeline_change"),
        ):
            items = build_public_answer_eval_items(
                adapter_items=[_selected_history_job_title_adapter_item()],
                qvf_requests=[_selected_history_job_title_qvf_request()],
                limit=1,
                qvf_context_variant="auto_compact",
            )

        qvf_item = [
            item for item in items if item["method"] == "qvf_validity_packed_context"
        ][0]

        self.assertEqual(
            qvf_item["context"]["target_compaction_policy"]["mode"],
            "full",
        )
        self.assertEqual(
            qvf_item["context"]["target_compaction_policy"]["reason"],
            "transition_question",
        )
        self.assertEqual(
            qvf_item["context"]["change_detail_context"][0]["field_changes"][0][
                "field"
            ],
            "job_title",
        )

    def test_qvf_answer_context_auto_compact_keeps_full_rows_for_static_profile_questions(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(query_intent="historical_recall"),
        ):
            context = _qvf_context(
                _degree_route_miss_qvf_request(),
                qvf_context_variant="auto_compact",
            )

        self.assertEqual(context["target_compaction_policy"]["mode"], "full")
        self.assertEqual(
            context["target_compaction_policy"]["reason"],
            "static_profile_question",
        )

    def test_qvf_answer_context_rejects_unknown_variant(self) -> None:
        with self.assertRaises(ValueError):
            _qvf_context(_qvf_request(), qvf_context_variant="dataset_magic")

    def test_qvf_answer_context_resolves_relative_time_for_when_questions(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_temporal_qvf_response(),
        ):
            context = _qvf_context(_temporal_qvf_request())

        rendered_target = json.dumps(
            _target_messages(
                question="When is Melanie planning on going camping?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )
        resolutions = {
            row["phrase"]: row["resolved_time"]
            for row in context["temporal_resolution_context"]
        }

        self.assertEqual(resolutions["next month"], "June 2023")
        self.assertEqual(resolutions["last saturday"], "2023-05-20")
        preferred = {
            row["phrase"]: row["preferred_answer"]
            for row in context["temporal_resolution_context"]
        }
        self.assertEqual(preferred["last saturday"], "the last saturday before 25 May 2023")
        self.assertIn("temporal_resolution_context", rendered_target)

    def test_qvf_answer_context_resolves_month_and_age_year_temporal_hints(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_month_age_temporal_qvf_response(),
        ):
            context = _qvf_context(_month_age_temporal_qvf_request())

        hints = {
            row["phrase"]: row
            for row in context["temporal_resolution_context"]
        }

        self.assertLessEqual(len(context["temporal_resolution_context"]), 3)
        self.assertEqual(hints["last month"]["resolved_time"], "June 2023")
        self.assertEqual(hints["last month"]["preferred_answer"], "June 2023")
        self.assertEqual(hints["3-year-old"]["resolved_time"], "2020")
        self.assertEqual(hints["3-year-old"]["preferred_answer"], "2020")

    def test_qvf_answer_context_adds_query_relevant_fallback_records(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_company_qvf_response(),
        ):
            context = _qvf_context(_degree_route_miss_qvf_request())

        rendered_target = json.dumps(
            _target_messages(
                question="What is the user's highest degree in their education background?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )
        fallback_ids = [
            row["memory_id"] for row in context["query_relevant_context"]
        ]

        self.assertEqual(context["current_answer_context"][0]["memory_id"], "company")
        self.assertIn("degree", fallback_ids)
        self.assertNotIn("company", fallback_ids)
        self.assertIn("Bachelor degree", rendered_target)
        self.assertIn("query_relevant_context", rendered_target)

    def test_qvf_answer_context_resolves_same_timestamp_current_book_conflict(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            context = _qvf_context(_same_timestamp_book_conflict_request())

        conflict = context["static_conflict_resolution_context"][0]
        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question="What book am I currently reading?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(conflict["recommended_value"], "The Seven Husbands of Evelyn Hugo")
        self.assertEqual(conflict["slot"], "title")
        self.assertEqual(conflict["recommendation_confidence"], "cue_based")
        self.assertIn("book_current_reading_cue", conflict["recommendation_reason"])
        self.assertIn("book_already_read_cue", json.dumps(conflict, ensure_ascii=False))
        self.assertEqual(context["public_reader_override"], {})
        self.assertEqual(
            target_context["bucket_counts"]["static_conflict_resolution_context"],
            1,
        )
        self.assertIn("static_conflict_resolution_context", rendered_target)

    def test_qvf_answer_context_overrides_weak_same_timestamp_public_decision(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_weak_gate_qvf_response(),
        ):
            context = _qvf_context(_same_timestamp_book_conflict_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )
        rendered_target = json.dumps(
            _target_messages(
                question="What book am I currently reading?",
                method="qvf_validity_packed_context",
                context=context,
            ),
            ensure_ascii=False,
        )

        self.assertEqual(
            context["core_qvf_read_time_decision"]["decision"],
            "UNKNOWN_CURRENT",
        )
        self.assertEqual(context["qvf_read_time_decision"]["decision"], "ADMIT_CURRENT")
        self.assertEqual(
            context["qvf_read_time_decision"]["answer_policy"],
            "answer_from_static_conflict_resolution",
        )
        self.assertEqual(
            context["public_reader_override"]["mode"],
            "same_timestamp_conflict_resolution",
        )
        self.assertEqual(
            context["public_reader_override"]["recommended_value"],
            "The Seven Husbands of Evelyn Hugo",
        )
        self.assertEqual(context["current_answer_context"][0]["memory_id"], "book_current")
        self.assertEqual(
            context["current_answer_context"][0]["retrieval_role"],
            "same_timestamp_conflict_resolved",
        )
        self.assertNotIn(
            "book_current",
            [row["memory_id"] for row in context["stale_or_blocked_context"]],
        )
        self.assertIn(
            "book_completed",
            [row["memory_id"] for row in context["uncertain_context"]],
        )
        overridden = [
            row
            for row in context["uncertain_context"]
            if row["memory_id"] == "book_completed"
        ][0]
        self.assertEqual(
            overridden["current_status"],
            "same_timestamp_conflict_overridden",
        )
        self.assertEqual(
            target_context["public_reader_override"]["recommended_memory_id"],
            "book_current",
        )
        self.assertIn("core_qvf_read_time_decision", target_context)
        self.assertIn("same_timestamp_conflict_resolution", rendered_target)

    def test_qvf_answer_context_resolves_same_timestamp_brand_descriptor_conflict(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            context = _qvf_context(
                _same_timestamp_brand_conflict_request(),
                qvf_context_variant="auto_compact",
            )

        conflict = context["static_conflict_resolution_context"][0]

        self.assertEqual(conflict["recommended_value"], "Trader Joe's")
        self.assertIn("brand_source_phrase", conflict["recommendation_reason"])
        self.assertIn("descriptor_not_brand", json.dumps(conflict, ensure_ascii=False))
        self.assertEqual(
            context["target_compaction_policy"]["reason"],
            "static_conflict_resolution_context_present",
        )

    def test_qvf_answer_context_suppresses_ambiguous_same_timestamp_conflict(self) -> None:
        with patch(
            "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
            return_value=_routed_qvf_response(),
        ):
            context = _qvf_context(_ambiguous_amount_conflict_request())

        target_context = _target_memory_context(
            "qvf_validity_packed_context",
            context,
        )

        self.assertEqual(context["static_conflict_resolution_context"], [])
        self.assertEqual(
            target_context["bucket_counts"]["static_conflict_resolution_context"],
            0,
        )

    def test_public_answer_result_row_keeps_judge_rationale_excerpt(self) -> None:
        items = build_public_answer_eval_items(
            adapter_items=[_adapter_item()],
            qvf_requests=[_qvf_request()],
            limit=1,
        )
        row = _result_row(
            item=items[0],
            target_content='{"answer":"Milan"}',
            target_response={
                "latency_seconds": 1.2,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                },
            },
            judge_response={
                "latency_seconds": 0.8,
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                },
            },
            judgment={
                "correct": False,
                "error_type": "unsupported",
                "rationale": "The answer is not supported by the provided memory.",
            },
        )

        self.assertEqual(row["error_type"], "unsupported")
        self.assertEqual(
            row["judge_rationale_excerpt"],
            "The answer is not supported by the provided memory.",
        )

    def test_public_answer_eval_preflight_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            adapter_path = tmp_path / "items.json"
            requests_path = tmp_path / "requests.jsonl"
            output_dir = tmp_path / "answer_eval"
            adapter_path.write_text(
                json.dumps({"items": [_adapter_item()]}),
                encoding="utf-8",
            )
            requests_path.write_text(
                json.dumps(_qvf_request(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            loaded = load_public_qvf_requests(requests_path)
            report = run_public_answer_eval(
                output_dir,
                adapter_items_path=adapter_path,
                qvf_requests_path=requests_path,
                limit=1,
                qvf_context_variant="core_routing",
            )
            preflight = json.loads(
                (output_dir / "public_answer_preflight.json").read_text(
                    encoding="utf-8"
                )
            )
            payload_audit = json.loads(
                (output_dir / "public_answer_payload_audit.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(len(loaded), 1)
        self.assertEqual(report["decision"], "NEEDS_RUN_API_FOR_PUBLIC_ANSWER_EVAL")
        self.assertEqual(report["payload_audit_decision"], "GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT")
        self.assertEqual(report["api_calls_made"], 0)
        self.assertEqual(report["qvf_context_variant"], "core_routing")
        self.assertIn("public_answer_payload_audit.json", report["preflight_files"][1])
        self.assertEqual(preflight["case_count"], 1)
        self.assertEqual(preflight["qvf_context_variant"], "core_routing")
        self.assertEqual(preflight["expected_call_count"]["total_calls"], 4)
        self.assertIn(
            "target payload audit checks forbidden fields, local paths, and secret-like strings before API calls",
            preflight["health_gates"],
        )
        self.assertEqual(payload_audit["decision"], "GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT")
        self.assertEqual(payload_audit["blocking_hit_count"], 0)
        self.assertIn(
            "judge prompts include the same memory_context shown to the target method",
            preflight["health_gates"],
        )

    def test_api_eval_reuses_selective_qvf_byte_equivalent_outputs(self) -> None:
        fake_client = _FakeOpenAIChatClient(
            judge_correct_by_method={
                "direct_extracted_memories": False,
                "qvf_validity_packed_context": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            adapter_path = tmp_path / "items.json"
            requests_path = tmp_path / "requests.jsonl"
            output_dir = tmp_path / "answer_eval"
            adapter_path.write_text(
                json.dumps({"items": [_adapter_item()]}),
                encoding="utf-8",
            )
            requests_path.write_text(
                json.dumps(_qvf_request(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with patch(
                "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
                return_value=_routed_qvf_response(),
            ), patch(
                "qvf_validity_admission.public_answer_eval._OpenAIChatClient",
                return_value=fake_client,
            ):
                report = run_public_answer_eval(
                    output_dir,
                    adapter_items_path=adapter_path,
                    qvf_requests_path=requests_path,
                    limit=1,
                    qvf_context_variant="selective_router",
                    run_api=True,
                    max_output_tokens=128,
                )
            results = json.loads(
                (output_dir / "public_answer_results.json").read_text(
                    encoding="utf-8"
                )
            )
            target_rows = [
                json.loads(line)
                for line in (output_dir / "target_outputs.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]

        self.assertEqual(report["api_calls_made"], 4)
        self.assertEqual(len(fake_client.calls), 4)
        self.assertEqual(results["reuse_summary"]["target_reused_rows"], 1)
        self.assertEqual(results["reuse_summary"]["judge_reused_rows"], 1)
        selective_case = [
            row
            for row in results["case_results"]
            if row["method"] == "qvf_selective_router"
        ][0]
        qvf_case = [
            row
            for row in results["case_results"]
            if row["method"] == "qvf_validity_packed_context"
        ][0]
        self.assertTrue(qvf_case["correct"])
        self.assertTrue(selective_case["correct"])
        self.assertFalse(selective_case["target_api_call_made"])
        self.assertEqual(
            selective_case["target_reused_from_method"],
            "qvf_validity_packed_context",
        )
        self.assertEqual(
            [
                row
                for row in target_rows
                if row["method"] == "qvf_selective_router"
            ][0]["content"],
            [
                row
                for row in target_rows
                if row["method"] == "qvf_validity_packed_context"
            ][0]["content"],
        )

    def test_api_eval_reuses_selective_direct_byte_equivalent_outputs(self) -> None:
        fake_client = _FakeOpenAIChatClient(
            judge_correct_by_method={
                "direct_extracted_memories": True,
                "qvf_validity_packed_context": False,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            adapter_path = tmp_path / "items.json"
            requests_path = tmp_path / "requests.jsonl"
            output_dir = tmp_path / "answer_eval"
            adapter_path.write_text(
                json.dumps({"items": [_plain_recall_adapter_item()]}),
                encoding="utf-8",
            )
            requests_path.write_text(
                json.dumps(_plain_recall_qvf_request(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with patch(
                "qvf_validity_admission.public_answer_eval.run_qvf_service_request",
                return_value=_temporal_qvf_response(),
            ), patch(
                "qvf_validity_admission.public_answer_eval._OpenAIChatClient",
                return_value=fake_client,
            ):
                report = run_public_answer_eval(
                    output_dir,
                    adapter_items_path=adapter_path,
                    qvf_requests_path=requests_path,
                    limit=1,
                    qvf_context_variant="selective_router",
                    run_api=True,
                    max_output_tokens=128,
                )
            results = json.loads(
                (output_dir / "public_answer_results.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(report["api_calls_made"], 4)
        self.assertEqual(len(fake_client.calls), 4)
        selective_case = [
            row
            for row in results["case_results"]
            if row["method"] == "qvf_selective_router"
        ][0]
        direct_case = [
            row
            for row in results["case_results"]
            if row["method"] == "direct_extracted_memories"
        ][0]
        self.assertTrue(direct_case["correct"])
        self.assertTrue(selective_case["correct"])
        self.assertFalse(selective_case["judge_api_call_made"])
        self.assertEqual(
            selective_case["judge_reused_from_method"],
            "direct_extracted_memories",
        )

    def test_public_answer_target_payload_audit_blocks_forbidden_payload(self) -> None:
        audit = _build_target_payload_audit(
            [
                {
                    "case_id": "bad_case",
                    "method": "direct_extracted_memories",
                    "question": "Where is the file?",
                    "expected_answers": ["SECRET_EXPECTED"],
                    "target_messages": [
                        {
                            "role": "user",
                            "content": (
                                "expected_answers should not be here; "
                                "path C:\\Users\\25243\\secret.txt; "
                                "api_key=abc123"
                            ),
                        }
                    ],
                    "context": {},
                }
            ],
            qvf_context_variant="core_routing",
        )

        self.assertEqual(
            audit["decision"],
            "NO_GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT",
        )
        self.assertEqual(audit["blocking_hit_count"], 3)
        self.assertEqual(audit["forbidden_field_hits"][0]["term"], "expected_answers")
        self.assertEqual(audit["local_path_hits"][0]["case_id"], "bad_case")
        self.assertEqual(audit["secret_like_hits"][0]["case_id"], "bad_case")

    def test_gpt5_models_use_max_completion_tokens(self) -> None:
        self.assertEqual(
            _completion_token_limit_field("gpt-5.4"),
            "max_completion_tokens",
        )
        self.assertEqual(_completion_token_limit_field("gpt-4o-mini"), "max_tokens")


class _FakeOpenAIChatClient:
    def __init__(self, *, judge_correct_by_method: dict[str, bool]) -> None:
        self.judge_correct_by_method = judge_correct_by_method
        self.calls: list[dict[str, object]] = []
        self.target_call_count = 0

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
            }
        )
        if max_tokens == 180:
            payload = json.loads(messages[1]["content"])
            method = str(payload.get("method", ""))
            content = json.dumps(
                {
                    "correct": self.judge_correct_by_method.get(method, False),
                    "error_type": "",
                    "rationale": f"fake judge for {method}",
                }
            )
            return _fake_chat_response(content, prompt_tokens=17, completion_tokens=7)
        self.target_call_count += 1
        content = json.dumps(
            {
                "answer": f"fake target answer {self.target_call_count}",
                "used_memory_ids": [f"fake_{self.target_call_count}"],
                "abstained": False,
            }
        )
        return _fake_chat_response(content, prompt_tokens=23, completion_tokens=11)


def _fake_chat_response(
    content: str,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _adapter_item() -> dict[str, object]:
    return {
        "case_id": "public_case_001",
        "question": "Since Maya still lives in Rome, where should mail go now?",
        "answers": ["SECRET_GOLD_ANSWER"],
    }


def _historical_adapter_item() -> dict[str, object]:
    return {
        "case_id": "public_case_history",
        "question": "Where did Maya live before she moved?",
        "answers": ["SECRET_HISTORICAL_ANSWER"],
    }


def _plain_recall_adapter_item() -> dict[str, object]:
    return {
        "case_id": "temporal_demo",
        "question": "What activity is Melanie planning?",
        "answers": ["SECRET_ACTIVITY_GOLD"],
    }


def _current_only_adapter_item() -> dict[str, object]:
    return {
        "case_id": "current_only_case",
        "question": "Where does Maya currently live?",
        "answers": ["SECRET_CURRENT_ONLY_GOLD"],
    }


def _temporal_adapter_item() -> dict[str, object]:
    return {
        "case_id": "temporal_demo",
        "question": "When is Melanie planning on going camping?",
        "answers": ["SECRET_TEMPORAL_GOLD"],
    }


def _month_age_temporal_adapter_item() -> dict[str, object]:
    return {
        "case_id": "month_age_temporal_demo",
        "question": "In which month's game did John achieve a career-high score in points?",
        "answers": ["SECRET_MONTH_GOLD"],
    }


def _qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_public_case_001",
        "step_id": "public_extraction_step_public_case_001",
        "records": [
            {
                "memory_id": "maya_old",
                "entity": "Maya",
                "slot": "home_city",
                "claim": "Maya home_city is Rome.",
                "value": "Rome",
                "observed_at": "2024-01-01T00:00:00+00:00",
                "valid_from": "2024-01-01T00:00:00+00:00",
                "source": {"source_id": "old", "source_type": "public_history_extraction"},
                "source_confidence": 0.9,
            },
            {
                "memory_id": "maya_new",
                "entity": "Maya",
                "slot": "home_city",
                "claim": "Maya home_city is Milan.",
                "value": "Milan",
                "observed_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2025-01-01T00:00:00+00:00",
                "source": {
                    "source_id": "new",
                    "source_type": "public_history_extraction",
                    "source_span": "Maya moved to Milan.",
                },
                "source_confidence": 0.95,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_public_case_001",
                "question": "Since Maya still lives in Rome, where should mail go now?",
                "entity": "Maya",
                "slot": "home_city",
                "premise_value": "Rome",
                "needs_current": True,
            }
        ],
    }


def _historical_qvf_request() -> dict[str, object]:
    request = _qvf_request()
    request["request_id"] = "public_extraction_public_case_history"
    request["step_id"] = "public_extraction_step_public_case_history"
    request["query_requests"] = [
        {
            "request_id": "q_public_case_history",
            "question": "Where did Maya live before she moved?",
            "entity": "Maya",
            "slot": "home_city",
            "needs_current": False,
        }
    ]
    return request


def _current_only_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_current_only_case",
        "step_id": "public_extraction_step_current_only_case",
        "records": [
            {
                "memory_id": "maya_current",
                "entity": "Maya",
                "slot": "home_city",
                "claim": "Maya currently lives in Milan.",
                "value": "Milan",
                "observed_at": "2025-01-01T00:00:00+00:00",
                "valid_from": "2025-01-01T00:00:00+00:00",
                "source": {
                    "source_id": "current",
                    "source_type": "public_history_extraction",
                    "source_span": "Maya currently lives in Milan.",
                },
                "source_confidence": 0.95,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_current_only_case",
                "question": "Where does Maya currently live?",
                "entity": "Maya",
                "slot": "home_city",
                "needs_current": True,
            }
        ],
    }


def _source_supported_current_blocked_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_source_supported_current_blocked_case",
        "step_id": "public_extraction_step_source_supported_current_blocked_case",
        "records": [
            {
                "memory_id": "married_current",
                "entity": "user",
                "slot": "marital_status_change",
                "claim": "User's marital status changed recently.",
                "value": "recently married",
                "observed_at": "2022-05-11T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I just got married. I married Michelle Williams.",
                },
                "source_confidence": 0.95,
            },
            {
                "memory_id": "single_archive",
                "entity": "user",
                "slot": "marital_status",
                "claim": "User used to be single.",
                "value": "single",
                "observed_at": "2022-01-11T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I am single for now.",
                },
                "source_confidence": 0.9,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_source_supported_current_blocked_case",
                "question": "Did the user's marital status change recently?",
                "entity": "user",
                "slot": "marital_status_change",
                "needs_current": True,
            }
        ],
    }


def _tennis_frequency_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_tennis_frequency_case",
        "records": [
            {
                "memory_id": "tennis_recent_cadence",
                "entity": "user",
                "slot": "tennis_routine",
                "claim": "User plans tennis with friends every other week.",
                "value": "tennis every other week",
                "observed_at": "2023-07-30T00:00:00+00:00",
                "source": {
                    "source_id": "tennis_recent",
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I'm planning to play tennis with my friends this Sunday, "
                        "like we do every other week."
                    ),
                },
                "source_confidence": 0.95,
            },
            {
                "memory_id": "tennis_previous_cadence",
                "entity": "user",
                "slot": "tennis_routine",
                "claim": "User has weekly tennis sessions with friends.",
                "value": "weekly tennis sessions",
                "observed_at": "2023-03-11T00:00:00+00:00",
                "source": {
                    "source_id": "tennis_previous",
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I was at the local park last Sunday for our weekly tennis "
                        "sessions with friends."
                    ),
                },
                "source_confidence": 0.91,
            },
            {
                "memory_id": "tennis_event_only",
                "entity": "user",
                "slot": "tennis_activity",
                "claim": "User played tennis with friends on Sunday.",
                "value": "tennis with friends",
                "observed_at": "2023-03-11T00:00:00+00:00",
                "source": {
                    "source_id": "tennis_event",
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I played tennis with friends at the local park last Sunday."
                    ),
                },
                "source_confidence": 0.9,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_tennis_frequency_case",
                "question": (
                    "How often did the user play tennis with friends before and now?"
                ),
                "entity": "user",
                "slot": "tennis_routine",
                "needs_current": False,
            }
        ],
    }


def _transport_recency_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_transport_recency_case",
        "records": [
            {
                "memory_id": "transport_bus_old",
                "entity": "user",
                "slot": "transport",
                "claim": "User has recently started taking the bus to work.",
                "value": "bus",
                "observed_at": "2023-01-31T00:00:00+00:00",
                "source": {
                    "source_id": "transport_bus_old",
                    "source_type": "public_history_extraction",
                    "source_span": "I started taking the bus to work recently.",
                },
                "source_confidence": 0.9,
            },
            {
                "memory_id": "transport_train_latest",
                "entity": "user",
                "slot": "transport",
                "claim": (
                    "User has been taking a lot of trains lately for shorter distances."
                ),
                "value": "train",
                "observed_at": "2023-03-03T00:00:00+00:00",
                "source": {
                    "source_id": "transport_train_latest",
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I've been taking a lot of trains lately for shorter distances."
                    ),
                },
                "source_confidence": 0.93,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_transport_recency_case",
                "question": (
                    "Which mode of transport has the user taken most recently?"
                ),
                "entity": "user",
                "slot": "transport",
                "needs_current": True,
            }
        ],
    }


def _routed_qvf_response(query_intent: str = "current_state") -> dict[str, object]:
    return {
        "step_report": {
            "query_report": {
                "query_results": [
                    {
                        "read_decision": {
                            "decision": "ADMIT_CURRENT",
                            "answer_policy": "answer_from_current",
                            "route": "current_support_reader",
                            "reader_contract": "Use current evidence as answer support.",
                        },
                        "packet": {
                            "query": {"query_intent": query_intent},
                            "context_control_policy": {
                                "answer_from_roles": ["current_evidence"],
                            },
                            "compact_validity_packet": {
                                "current_evidence": [
                                    _evidence_row(
                                        "maya_current",
                                        "Maya home_city is Milan.",
                                        "Milan",
                                        "Maya moved to Milan.",
                                        "current_support",
                                    )
                                ],
                                "supporting_evidence": [
                                    _evidence_row(
                                        "maya_supporting",
                                        "Maya receives mail near Milan.",
                                        "Milan mailroom",
                                        "Maya asked for mail near Milan.",
                                        "supporting_duplicate",
                                    )
                                ],
                                "historical_evidence": [],
                                "stale_or_blocked_evidence": [
                                    _evidence_row(
                                        "maya_stale",
                                        "Maya home_city was Rome.",
                                        "Rome",
                                        "Maya used to live in Rome.",
                                        "expired",
                                    )
                                ],
                                "excluded_memory_summary": [
                                    _evidence_row(
                                        "maya_uncertain",
                                        "Maya may work in Turin.",
                                        "Turin",
                                        "A low-confidence note mentions Turin.",
                                        "below_query_confidence",
                                    )
                                ],
                            },
                        },
                    }
                ]
            }
        }
    }


def _current_only_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="current_state")
    result = response["step_report"]["query_report"]["query_results"][0]
    result["read_decision"]["validity_controller_decision"] = {
        "evidence_sufficiency": "sufficient_current_evidence",
        "next_action": "answer_from_current",
    }
    packet = result["packet"]["compact_validity_packet"]
    packet["current_evidence"] = [
        _evidence_row(
            "maya_current",
            "Maya currently lives in Milan.",
            "Milan",
            "Maya currently lives in Milan.",
            "current_support",
        )
    ]
    packet["supporting_evidence"] = []
    packet["historical_evidence"] = []
    packet["stale_or_blocked_evidence"] = []
    packet["excluded_memory_summary"] = []
    return response


def _weak_gate_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="current_state")
    result = response["step_report"]["query_report"]["query_results"][0]
    result["read_decision"] = {
        "decision": "UNKNOWN_CURRENT",
        "answer_policy": "insufficient_current_state",
        "route": "weak_conservative_gate",
        "reader_contract": "Core QVF lacks enough timestamp evidence for current state.",
    }
    packet = result["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "book_completed",
            "User's book club is discussing The Last House Guest.",
            "The Last House Guest",
            "We are going to discuss The Last House Guest, which I've already read.",
            "current_support",
            observed_at="1970-01-01T00:00:00+00:00",
        )
    ]
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = [
        _evidence_row(
            "book_current",
            "User is reading The Seven Husbands of Evelyn Hugo.",
            "The Seven Husbands of Evelyn Hugo",
            "I'm currently devouring The Seven Husbands of Evelyn Hugo.",
            "expired",
            observed_at="1970-01-01T00:00:00+00:00",
        )
    ]
    return response


def _source_supported_current_blocked_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="current_state")
    result = response["step_report"]["query_report"]["query_results"][0]
    result["read_decision"] = {
        "decision": "UNKNOWN_CURRENT",
        "answer_policy": "insufficient_current_state",
        "route": "stale_current_conflict_gate",
        "reader_contract": "Retrieve a current marital status row before answering.",
        "validity_controller_decision": {
            "evidence_sufficiency": "no_visible_answer_evidence",
            "next_action": "retrieve_current_entity_slot",
            "query_rewrite": "user marital_status current",
            "blocked_as_current_ids": ["married_current", "single_archive"],
            "allowed_as_history_ids": ["single_archive"],
            "suggested_retrieval_scope": {
                "entity": "user",
                "slot": "marital_status",
                "temporal_focus": "current",
                "include_current": True,
            },
        },
    }
    packet = result["packet"]["compact_validity_packet"]
    packet["current_evidence"] = [
        _evidence_row(
            "married_current",
            "User's marital status changed recently.",
            "recently married",
            "I just got married. I married Michelle Williams.",
            "current_support",
            observed_at="2022-05-11T00:00:00+00:00",
        )
    ]
    packet["supporting_evidence"] = []
    packet["historical_evidence"] = []
    packet["stale_or_blocked_evidence"] = [
        _evidence_row(
            "single_archive",
            "User used to be single.",
            "single",
            "I am single for now.",
            "expired",
            observed_at="2022-01-11T00:00:00+00:00",
        )
    ]
    packet["excluded_memory_summary"] = []
    return response


def _transition_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_change_demo",
        "records": [
            {
                "memory_id": "residence_old",
                "entity": "user",
                "slot": "residence",
                "claim": "User moved to Darwin.",
                "value": "Darwin",
                "observed_at": "2022-01-30T00:00:00+00:00",
            },
            {
                "memory_id": "residence_new",
                "entity": "user",
                "slot": "residence_change",
                "claim": "User moved to Melbourne.",
                "value": "moved to Melbourne",
                "observed_at": "2022-02-25T00:00:00+00:00",
            },
        ],
        "query_requests": [
            {
                "request_id": "q_change_demo",
                "question": "How did the user's residence change?",
                "entity": "user",
                "slot": "residence",
                "needs_current": False,
            }
        ],
    }


def _yes_no_residence_change_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_yes_no_residence_change_demo",
        "records": [
            {
                "memory_id": "move_event",
                "entity": "user",
                "slot": "residence_change",
                "claim": "User moved last week.",
                "value": "moved last week",
                "observed_at": "2022-01-30T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I moved last week. When did you move to Melbourne?",
                },
            },
            {
                "memory_id": "current_city",
                "entity": "user",
                "slot": "current_residence",
                "claim": "User moved to Melbourne.",
                "value": "Melbourne",
                "observed_at": "2022-01-30T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "When did you move to Melbourne? I moved last week.",
                },
            },
        ],
        "query_requests": [
            {
                "request_id": "q_yes_no_residence_change_demo",
                "question": "Did the user's residence change recently?",
                "entity": "user",
                "slot": "residence_change",
                "needs_current": True,
            }
        ],
    }


def _employment_stayed_same_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_employment_stayed_same_demo",
        "records": [
            {
                "memory_id": "old_employment",
                "entity": "user",
                "slot": "employment_status",
                "claim": "User works part-time from home.",
                "value": "part-time from home",
                "observed_at": "2022-01-03T00:00:00+00:00",
            },
            {
                "memory_id": "advice_not_status",
                "entity": "user",
                "slot": "employment_status",
                "claim": "Assistant gave career planning advice.",
                "value": "If the internship has a timeline, begin discreetly exploring opportunities about 6-8 weeks before the end.",
                "observed_at": "2022-02-25T00:00:00+00:00",
            },
            {
                "memory_id": "new_employment",
                "entity": "user",
                "slot": "employment_status",
                "claim": "User is currently in an internship.",
                "value": "internship",
                "observed_at": "2022-02-25T00:00:00+00:00",
            },
        ],
        "query_requests": [
            {
                "request_id": "q_employment_stayed_same_demo",
                "question": "Has the user's employment status stayed the same?",
                "entity": "user",
                "slot": "employment_status",
                "needs_current": False,
            }
        ],
    }


def _source_span_company_transition_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_company_change_demo",
        "records": [
            {
                "memory_id": "old_company",
                "entity": "user",
                "slot": "company",
                "claim": "User works as a Senior at Future Intelligence.",
                "value": "Future Intelligence",
                "observed_at": "2022-01-07T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I work at Future Intelligence.",
                },
            },
            {
                "memory_id": "new_commute",
                "entity": "user",
                "slot": "commute",
                "claim": "User's commute is about 30 minutes.",
                "value": "30 minutes",
                "observed_at": "2022-02-25T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Have you already started at Northern Logistics or is "
                        "your first day coming up?"
                    ),
                },
            },
        ],
        "query_requests": [
            {
                "request_id": "q_company_change_demo",
                "question": "What changed about the user's company?",
                "entity": "user",
                "slot": "commute",
                "needs_current": False,
            }
        ],
    }


def _selected_history_job_title_adapter_item() -> dict[str, object]:
    return {
        "case_id": "selected_history_job_title_case",
        "question": "What changed about the user's job title?",
        "answers": ["SECRET_JOB_TITLE_GOLD"],
        "extraction_work_item": {
            "history_turns": [
                {
                    "turn_id": "old-role-turn",
                    "timestamp": "2022-01-07",
                    "speaker": "user",
                    "text": "I work as a Senior at Future Intelligence in the media industry.",
                    "selection_rank": 1,
                    "selection_score": 10.0,
                },
                {
                    "turn_id": "new-role-turn",
                    "timestamp": "2022-02-25",
                    "speaker": "assistant",
                    "text": "Given you're early in the internship, keep a private work log.",
                    "selection_rank": 2,
                    "selection_score": 9.0,
                },
            ]
        },
    }


def _selected_history_job_title_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_selected_history_job_title_case",
        "records": [
            {
                "memory_id": "old_role",
                "entity": "user",
                "slot": "job_title",
                "claim": "User works as a Senior at Future Intelligence.",
                "value": "Senior",
                "observed_at": "2022-01-07T00:00:00+00:00",
            },
            {
                "memory_id": "current_commute",
                "entity": "user",
                "slot": "commute_time",
                "claim": "User has a 30 minute commute.",
                "value": "30 minutes",
                "observed_at": "2022-02-25T00:00:00+00:00",
            },
        ],
        "query_requests": [
            {
                "request_id": "q_selected_history_job_title_case",
                "question": "What changed about the user's job title?",
                "entity": "user",
                "slot": "commute_time",
                "needs_current": False,
            }
        ],
    }


def _selected_history_residence_adapter_item() -> dict[str, object]:
    return {
        "case_id": "selected_history_residence_case",
        "question": "How did the user's residence change?",
        "answers": ["SECRET_RESIDENCE_GOLD"],
        "extraction_work_item": {
            "history_turns": [
                {
                    "turn_id": "prior-location-turn",
                    "timestamp": "2022-01-30",
                    "speaker": "assistant",
                    "text": (
                        "Nice! Darwin's got a totally different vibe from the "
                        "southern cities. How are you finding it so far--what's "
                        "day-to-day like where you are?"
                    ),
                    "selection_rank": 1,
                    "selection_score": 9.0,
                },
                {
                    "turn_id": "current-location-turn",
                    "timestamp": "2022-02-25",
                    "speaker": "user",
                    "text": "Hey -- quick update: I just relocated to Melbourne.",
                    "selection_rank": 2,
                    "selection_score": 8.5,
                },
            ]
        },
    }


def _selected_history_residence_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_selected_history_residence_case",
        "records": [
            {
                "memory_id": "current_residence",
                "entity": "user",
                "slot": "residence",
                "claim": "User relocated to Melbourne.",
                "value": "Melbourne",
                "observed_at": "2022-02-25T00:00:00+00:00",
            }
        ],
        "query_requests": [
            {
                "request_id": "q_selected_history_residence_case",
                "question": "How did the user's residence change?",
                "entity": "user",
                "slot": "residence",
                "needs_current": False,
            }
        ],
    }


def _relationship_alias_transition_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_relationship_alias_case",
        "records": [
            {
                "memory_id": "prior_marital_status",
                "entity": "user",
                "slot": "marital_status",
                "claim": "User mentioned they are divorced.",
                "value": "divorced",
                "observed_at": "2022-01-27T00:00:00+00:00",
            },
            {
                "memory_id": "current_relationship",
                "entity": "user",
                "slot": "current_relationship",
                "claim": "User is now dating Helen Wilson.",
                "value": "dating Helen Wilson",
                "observed_at": "2022-03-09T00:00:00+00:00",
            },
        ],
        "query_requests": [
            {
                "request_id": "q_relationship_alias_case",
                "question": "What change occurred in the user's marital status?",
                "entity": "user",
                "slot": "marital_status",
                "needs_current": False,
            }
        ],
    }


def _previous_relationship_alias_transition_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_previous_relationship_alias_case",
        "records": [
            {
                "memory_id": "prior_relationship_status",
                "entity": "user",
                "slot": "previous_relationship_status",
                "claim": "User was previously single before dating Michelle.",
                "value": "single",
                "observed_at": "2022-01-23T00:00:00+00:00",
            },
            {
                "memory_id": "current_relationship",
                "entity": "user",
                "slot": "current_relationship",
                "claim": "User is now dating Michelle Williams.",
                "value": "dating Michelle Williams",
                "observed_at": "2022-01-27T00:00:00+00:00",
            },
        ],
        "query_requests": [
            {
                "request_id": "q_previous_relationship_alias_case",
                "question": "How did the user's marital status change?",
                "entity": "user",
                "slot": "marital_status",
                "needs_current": False,
            }
        ],
    }


def _relationship_alias_yes_no_qvf_request() -> dict[str, object]:
    request = _relationship_alias_transition_qvf_request()
    request["request_id"] = "public_extraction_relationship_alias_yes_no_case"
    request["query_requests"][0]["request_id"] = "q_relationship_alias_yes_no_case"
    request["query_requests"][0]["question"] = "Did the user's marital status change?"
    return request


def _scoped_tea_blend_adapter_item() -> dict[str, object]:
    return {
        "case_id": "scoped_tea_blend_case",
        "question": "What type of tea blend did I try last weekend?",
        "answers": ["SECRET_TEA_BLEND_GOLD"],
        "extraction_work_item": {
            "history_turns": [
                {
                    "turn_id": "tea-blend-turn",
                    "timestamp": "2024-05-13",
                    "speaker": "user",
                    "text": (
                        "Speaking of which, I tried a citrus oolong tea blend "
                        "last weekend and liked the bright finish."
                    ),
                    "selection_rank": 1,
                    "selection_score": 11.0,
                },
                {
                    "turn_id": "generic-rec-turn",
                    "timestamp": "2024-05-10",
                    "speaker": "assistant",
                    "text": "You might like roasted barley tea if you want a deeper evening drink.",
                    "selection_rank": 2,
                    "selection_score": 7.0,
                },
            ]
        },
    }


def _scoped_tea_blend_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_scoped_tea_blend_case",
        "records": [
            {
                "memory_id": "tea_generic_recommendation",
                "entity": "user",
                "slot": "tea_blend_interest",
                "claim": "User may like roasted barley tea.",
                "value": "roasted barley tea",
                "observed_at": "2024-05-10T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "You might like roasted barley tea if you want a deeper evening drink.",
                },
            }
        ],
        "query_requests": [
            {
                "request_id": "q_scoped_tea_blend_case",
                "question": "What type of tea blend did I try last weekend?",
                "entity": "user",
                "slot": "tea_blend",
                "needs_current": False,
            }
        ],
    }


def _temporal_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_temporal_demo",
        "query_requests": [
            {
                "request_id": "q_temporal_demo",
                "question": "When is Melanie planning on going camping?",
                "entity": "Melanie",
                "slot": "camping_plan",
                "needs_current": False,
            }
        ],
    }


def _plain_recall_qvf_request() -> dict[str, object]:
    request = _temporal_qvf_request()
    request["records"] = [
        {
            "memory_id": "melanie_camping",
            "entity": "Melanie",
            "slot": "camping_plan",
            "claim": "Melanie is thinking about going camping next month.",
            "value": "camping next month",
            "observed_at": "2023-05-25T13:14:00+00:00",
            "source": {
                "source_type": "public_history_extraction",
                "source_span": "We're thinking about going camping next month.",
            },
            "source_confidence": 0.9,
        }
    ]
    request["query_requests"] = [
        {
            "request_id": "q_plain_recall_demo",
            "question": "What activity is Melanie planning?",
            "entity": "Melanie",
            "slot": "camping_plan",
            "needs_current": False,
        }
    ]
    return request


def _temporal_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "melanie_camping",
            "Melanie is thinking about going camping next month.",
            "camping next month",
            "We're thinking about going camping next month.",
            "current_support",
            observed_at="2023-05-25T13:14:00+00:00",
        ),
        _evidence_row(
            "melanie_race",
            "Melanie ran a charity race for mental health last Saturday.",
            "last Saturday",
            "I ran a charity race for mental health last Saturday.",
            "current_support",
            observed_at="2023-05-25T13:14:00+00:00",
        ),
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = []
    packet["compact_validity_packet"]["historical_evidence"] = []
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _month_age_temporal_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_month_age_temporal_demo",
        "query_requests": [
            {
                "request_id": "q_month_age_temporal_demo",
                "question": "Which year did Audrey adopt the first three dogs?",
                "entity": "Audrey",
                "slot": "dogs_age",
                "needs_current": False,
            }
        ],
    }


def _month_age_temporal_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "john_score",
            "John scored 40 points last month.",
            "40 points",
            "So much happened in the last month. Last week I scored 40 points.",
            "current_support",
            observed_at="2023-07-16T16:21:00+00:00",
        ),
        _evidence_row(
            "audrey_dogs",
            "Audrey's dogs are 3-year-old.",
            "3-year-old",
            "They're all 3-year-old and they are a great pack.",
            "current_support",
            observed_at="2023-07-03T20:32:00+00:00",
        ),
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = []
    packet["compact_validity_packet"]["historical_evidence"] = []
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _degree_route_miss_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_degree_route_miss",
        "records": [
            {
                "memory_id": "company",
                "entity": "user",
                "slot": "current_company",
                "claim": "User works at Huaxin Consulting.",
                "value": "Huaxin Consulting",
                "observed_at": "2022-05-17T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "User started a new job at Huaxin Consulting.",
                },
                "source_confidence": 0.9,
            },
            {
                "memory_id": "degree",
                "entity": "user",
                "slot": "highest_degree",
                "claim": "User has a Bachelor degree.",
                "value": "Bachelor degree",
                "observed_at": "2022-06-07T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I have a Bachelor degree, so I might want alumni records updated too.",
                },
                "source_confidence": 0.9,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_degree_route_miss",
                "question": "What is the user's highest degree in their education background?",
                "entity": "user",
                "slot": "current_company",
                "needs_current": False,
            }
        ],
    }


def _routed_company_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "company",
            "User works at Huaxin Consulting.",
            "Huaxin Consulting",
            "User started a new job at Huaxin Consulting.",
            "current_support",
        )
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = []
    packet["compact_validity_packet"]["historical_evidence"] = []
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _condition_scope_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_condition_scope",
        "records": [
            {
                "memory_id": "orange_current",
                "entity": "user",
                "slot": "juice_preference",
                "claim": "User prefers fresh orange juice as a boost on training days.",
                "value": "fresh orange juice",
                "observed_at": "2025-02-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Morning: if training, have fresh orange juice as a boost; "
                        "otherwise keep breakfast simple."
                    ),
                },
                "source_confidence": 0.9,
            },
            {
                "memory_id": "orange_exact",
                "entity": "user",
                "slot": "juice_preference",
                "claim": "User prefers fresh orange juice before training.",
                "value": "fresh orange juice",
                "observed_at": "2025-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Before training I usually have fresh orange juice as a "
                        "quick morning boost."
                    ),
                },
                "source_confidence": 0.9,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_condition_scope",
                "question": "Under what condition does the user prefer fresh orange juice?",
                "entity": "user",
                "slot": "juice_preference",
                "needs_current": False,
            }
        ],
        "expected_answers": ["SECRET_CONDITION_ANSWER"],
    }


def _condition_scope_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "orange_current",
            "User prefers fresh orange juice as a boost on training days.",
            "fresh orange juice",
            (
                "Morning: if training, have fresh orange juice as a boost; "
                "otherwise keep breakfast simple."
            ),
            "current_support",
            observed_at="2025-02-01T00:00:00+00:00",
        )
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = []
    packet["compact_validity_packet"]["historical_evidence"] = [
        _evidence_row(
            "orange_training_days",
            "User uses fresh orange juice as a boost on training days.",
            "fresh orange juice",
            "I train mornings and use fresh orange juice as a boost on training days.",
            "historical_support",
            observed_at="2025-01-15T00:00:00+00:00",
        ),
        _evidence_row(
            "orange_exact",
            "User prefers fresh orange juice before training.",
            "fresh orange juice",
            "Before training I usually have fresh orange juice as a quick morning boost.",
            "historical_support",
            observed_at="2025-01-01T00:00:00+00:00",
        ),
    ]
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _summer_condition_scope_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_summer_condition_scope",
        "records": [
            {
                "memory_id": "basketball_summer",
                "entity": "Jackson Andrews",
                "slot": "interest",
                "claim": "Jackson likes basketball in summer.",
                "value": "basketball",
                "observed_at": "2025-03-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Jackson really likes basketball; he loves casual pickup "
                        "games in summer to keep cardio fun."
                    ),
                },
                "source_confidence": 0.9,
            }
        ],
        "query_requests": [
            {
                "request_id": "q_summer_condition_scope",
                "question": "When does the user prefer basketball?",
                "entity": "Jackson Andrews",
                "slot": "interest",
                "needs_current": False,
            }
        ],
    }


def _summer_condition_scope_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "basketball_summer",
            "Jackson really likes basketball in summer.",
            "basketball",
            (
                "Jackson really likes basketball; he loves casual pickup games "
                "in summer to keep cardio fun."
            ),
            "current_support",
            observed_at="2025-03-01T00:00:00+00:00",
        )
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = []
    packet["compact_validity_packet"]["historical_evidence"] = []
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _preference_source_promotion_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_preference_source_promotion",
        "records": [
            {
                "memory_id": "basketball_preference",
                "entity": "Jackson Andrews",
                "slot": "interest",
                "claim": (
                    "Jackson really likes basketball; he loves casual pickup "
                    "games in summer to keep cardio fun."
                ),
                "value": "basketball",
                "observed_at": "2025-03-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Jackson really likes basketball; he loves casual pickup "
                        "games in summer to keep cardio fun."
                    ),
                },
                "source_confidence": 0.9,
            },
            {
                "memory_id": "basketball_practice",
                "entity": "Jackson Andrews",
                "slot": "practice_schedule",
                "claim": "Jackson has basketball practice Tuesdays and Thursdays from 4:00-5:00.",
                "value": "Tuesdays and Thursdays from 4:00-5:00",
                "observed_at": "2025-03-02T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Jackson has basketball practice Tuesdays and Thursdays "
                        "from 4:00-5:00. Maya has choir on Wednesdays 4:00."
                    ),
                },
                "source_confidence": 0.9,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_preference_source_promotion",
                "question": "When does the user prefer basketball?",
                "entity": "Jackson Andrews",
                "slot": "interest",
                "needs_current": False,
            }
        ],
    }


def _schedule_only_condition_qvf_request() -> dict[str, object]:
    request = _preference_source_promotion_qvf_request()
    request["records"] = [request["records"][1]]
    return request


def _practice_schedule_only_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "basketball_practice",
            "Jackson has basketball practice Tuesdays and Thursdays from 4:00-5:00.",
            "Tuesdays and Thursdays from 4:00-5:00",
            (
                "Jackson has basketball practice Tuesdays and Thursdays "
                "from 4:00-5:00. Maya has choir on Wednesdays 4:00."
            ),
            "current_support",
            observed_at="2025-03-02T00:00:00+00:00",
        )
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = []
    packet["compact_validity_packet"]["historical_evidence"] = []
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _cold_noodles_condition_scope_qvf_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_cold_noodles_condition_scope",
        "records": [
            {
                "memory_id": "cold_noodles_shoots",
                "entity": "user",
                "slot": "meal_preference",
                "claim": "User prefers cold noodles after long outdoor shoots.",
                "value": "cold noodles",
                "observed_at": "2025-04-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "After long outdoor shoots I tend to crave cold noodles; "
                        "they're my go-to on hot summer days or right after a busy shoot."
                    ),
                },
                "source_confidence": 0.9,
            },
            {
                "memory_id": "cold_noodles_warm",
                "entity": "user",
                "slot": "meal_preference",
                "claim": "User may have cold noodles if it is warm that day.",
                "value": "cold noodles",
                "observed_at": "2025-04-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I could also do cold noodles if it's warm that day. "
                        "Set a week-before planning reminder and add make cold noodles to the note."
                    ),
                },
                "source_confidence": 0.9,
            },
        ],
        "query_requests": [
            {
                "request_id": "q_cold_noodles_condition_scope",
                "question": "Under what condition does the user prefer cold noodles?",
                "entity": "user",
                "slot": "meal_preference",
                "needs_current": False,
            }
        ],
    }


def _cold_noodles_condition_scope_qvf_response() -> dict[str, object]:
    response = _routed_qvf_response(query_intent="historical_recall")
    packet = response["step_report"]["query_report"]["query_results"][0]["packet"]
    packet["compact_validity_packet"]["current_evidence"] = [
        _evidence_row(
            "cold_noodles_shoots",
            "User prefers cold noodles after long outdoor shoots.",
            "cold noodles",
            (
                "After long outdoor shoots I tend to crave cold noodles; "
                "they're my go-to on hot summer days or right after a busy shoot."
            ),
            "current_support",
            observed_at="2025-04-01T00:00:00+00:00",
        ),
    ]
    packet["compact_validity_packet"]["supporting_evidence"] = [
        _evidence_row(
            "cold_noodles_warm",
            "User may have cold noodles if it is warm that day.",
            "cold noodles",
            (
                "I could also do cold noodles if it's warm that day. "
                "Set a week-before planning reminder and add make cold noodles to the note."
            ),
            "supporting_duplicate",
            observed_at="2025-04-01T00:00:00+00:00",
        ),
    ]
    packet["compact_validity_packet"]["historical_evidence"] = []
    packet["compact_validity_packet"]["stale_or_blocked_evidence"] = []
    packet["compact_validity_packet"]["excluded_memory_summary"] = []
    return response


def _same_timestamp_book_conflict_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_book_conflict",
        "records": [
            {
                "memory_id": "book_current",
                "entity": "book",
                "slot": "title",
                "claim": "User is reading The Seven Husbands of Evelyn Hugo.",
                "value": "The Seven Husbands of Evelyn Hugo",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "By the way, I'm currently devouring "
                        "\"The Seven Husbands of Evelyn Hugo\" and it is hard to put down."
                    ),
                },
            },
            {
                "memory_id": "book_completed",
                "entity": "book",
                "slot": "title",
                "claim": "User read The Last House Guest.",
                "value": "The Last House Guest",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "Our book club will discuss \"The Last House Guest\", "
                        "which I've already read and enjoyed."
                    ),
                },
            },
        ],
        "query_requests": [
            {
                "request_id": "q_book_conflict",
                "question": "What book am I currently reading?",
                "entity": "book",
                "slot": "title",
                "needs_current": True,
            }
        ],
    }


def _same_timestamp_brand_conflict_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_brand_conflict",
        "records": [
            {
                "memory_id": "brand_store",
                "entity": "shampoo",
                "slot": "brand",
                "claim": "User uses Trader Joe's shampoo.",
                "value": "Trader Joe's",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I've been using a lavender scented shampoo that I picked "
                        "up on a whim at Trader Joe's."
                    ),
                },
            },
            {
                "memory_id": "brand_descriptor",
                "entity": "shampoo",
                "slot": "brand",
                "claim": "User uses lavender scented shampoo.",
                "value": "lavender scented",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": (
                        "I've been using a lavender scented shampoo that I picked "
                        "up on a whim at Trader Joe's."
                    ),
                },
            },
        ],
        "query_requests": [
            {
                "request_id": "q_brand_conflict",
                "question": "What brand of shampoo do I currently use?",
                "entity": "shampoo",
                "slot": "brand",
                "needs_current": True,
            }
        ],
    }


def _ambiguous_amount_conflict_request() -> dict[str, object]:
    return {
        "request_id": "public_extraction_ambiguous_amount_conflict",
        "records": [
            {
                "memory_id": "thrive_amount",
                "entity": "grocery store",
                "slot": "most money spent",
                "claim": "User spent around $150 on groceries.",
                "value": "$150",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I placed an online order and spent around $150.",
                },
            },
            {
                "memory_id": "walmart_amount",
                "entity": "grocery store",
                "slot": "most money spent",
                "claim": "User spent around $120 on groceries.",
                "value": "$120",
                "observed_at": "1970-01-01T00:00:00+00:00",
                "source": {
                    "source_type": "public_history_extraction",
                    "source_span": "I went grocery shopping and spent around $120.",
                },
            },
        ],
        "query_requests": [
            {
                "request_id": "q_ambiguous_amount_conflict",
                "question": "Which grocery store did I spend the most money at?",
                "entity": "grocery store",
                "slot": "most money spent",
                "needs_current": False,
            }
        ],
    }


def _evidence_row(
    memory_id: str,
    claim: str,
    value: str,
    source_span: str,
    retrieval_role: str,
    observed_at: str = "2025-01-01T00:00:00+00:00",
) -> dict[str, object]:
    return {
        "memory_id": memory_id,
        "claim": claim,
        "value": value,
        "observed_at": observed_at,
        "source_id": "internal-source-id-should-be-omitted",
        "source_type": "public_history_extraction",
        "source_span": source_span,
        "source_turn_ids": ["turn-1"],
        "source_confidence": 0.7,
        "admission_status": "admit_current",
        "current_status": "current",
        "evidence_role": retrieval_role,
        "retrieval_role": retrieval_role,
        "retrieval_reason": "test reason",
        "reason": "test reason",
    }


if __name__ == "__main__":
    unittest.main()
