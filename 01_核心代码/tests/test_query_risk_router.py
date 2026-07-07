from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qvf_validity_admission.query_risk_router import (
    EVIDENCE_CONFLICT_ROUTE,
    TRANSITION_ROUTE,
    route_query_risk,
    write_query_risk_route,
)


class QueryRiskRouterTests(unittest.TestCase):
    def test_plain_recall_routes_to_direct_preserve_first(self) -> None:
        route = route_query_risk("What degree did I graduate with?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_state_without_evidence_risk_routes_to_direct(self) -> None:
        route = route_query_risk("Where does Maya live now?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_state_with_retrieved_slot_conflict_routes_to_qvf(self) -> None:
        route = route_query_risk(
            "Where does Maya live now?",
            retrieved_memories=[
                {
                    "memory_id": "old_location",
                    "entity": "Maya",
                    "slot": "location",
                    "value": "Rome",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_location",
                    "entity": "Maya",
                    "slot": "location",
                    "value": "Milan",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["query_type"], "current_state_or_update")
        self.assertEqual(route["recommended_route"], EVIDENCE_CONFLICT_ROUTE)
        self.assertTrue(route["should_apply_qvf"])

    def test_current_recommendation_query_fails_open_to_direct(self) -> None:
        route = route_query_risk(
            "Can you suggest some accessories that would complement my current photography setup?"
        )

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_recommendation_with_retrieved_slot_conflict_routes_to_qvf(self) -> None:
        route = route_query_risk(
            "Since the user has been based in Seattle for the last few years, "
            "can you recommend a few Seattle-specific neighborhood resources "
            "they should sign up for right now?",
            retrieved_memories=[
                {
                    "memory_id": "old_location",
                    "entity": "user",
                    "slot": "location",
                    "value": "I've been based in Seattle for the last few years.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_location",
                    "entity": "user",
                    "slot": "location",
                    "value": "I settled into my new place in Austin.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["query_type"], "current_state_or_update")
        self.assertEqual(route["recommended_route"], EVIDENCE_CONFLICT_ROUTE)
        self.assertTrue(route["should_apply_qvf"])
        self.assertEqual(route["evidence_risk"]["conflict_group_count"], 1)

    def test_action_query_with_implicit_retrieved_slot_conflict_routes_to_qvf(self) -> None:
        route = route_query_risk(
            "I just moved to the area and was wondering if you could recommend "
            "some good spots to relax on the weekends?",
            retrieved_memories=[
                {
                    "memory_id": "old_location",
                    "entity": "user",
                    "slot": "location",
                    "value": "I live in Seattle.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_location",
                    "entity": "user",
                    "slot": "location",
                    "value": "I moved to Austin.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["recommended_route"], EVIDENCE_CONFLICT_ROUTE)
        self.assertTrue(route["should_apply_qvf"])

    def test_example_like_services_with_slot_conflict_is_not_preference_recall(self) -> None:
        route = route_query_risk(
            "Since the user is residing in Chicago, can you recommend a few "
            "Chicago-specific local services (like utilities, internet providers, "
            "and nearby grocery options) they should set up this week?",
            retrieved_memories=[
                {
                    "memory_id": "old_location",
                    "entity": "user",
                    "slot": "location",
                    "value": "The user resides in Chicago.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_location",
                    "entity": "user",
                    "slot": "location",
                    "value": "The user moved to Portland.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["recommended_route"], EVIDENCE_CONFLICT_ROUTE)
        self.assertTrue(route["should_apply_qvf"])

    def test_current_recommendation_without_retrieved_conflict_stays_direct(self) -> None:
        route = route_query_risk(
            "Can you suggest some accessories that would complement my current photography setup?",
            retrieved_memories=[
                {
                    "memory_id": "camera",
                    "entity": "user",
                    "slot": "hobby",
                    "value": "The user enjoys street photography.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                }
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_generic_accessory_recommendation_with_slot_conflict_stays_direct(self) -> None:
        route = route_query_risk(
            "Can you suggest some useful accessories for my phone?",
            retrieved_memories=[
                {
                    "memory_id": "old_phone",
                    "entity": "user",
                    "slot": "phone",
                    "value": "The user has an iPhone 12.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_phone",
                    "entity": "user",
                    "slot": "phone",
                    "value": "The user bought a Pixel.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_preference_with_slot_conflict_stays_direct(self) -> None:
        route = route_query_risk(
            "What brand of BBQ sauce am I currently obsessed with?",
            retrieved_memories=[
                {
                    "memory_id": "old_sauce",
                    "entity": "user",
                    "slot": "bbq_sauce",
                    "value": "The user loves Brand A sauce.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_sauce",
                    "entity": "user",
                    "slot": "bbq_sauce",
                    "value": "The user has been buying Brand B sauce.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_recent_relocation_event_recall_with_metadata_current_stays_direct(self) -> None:
        route = route_query_risk(
            "Where did Rachel move to after her recent relocation?",
            query_metadata={"needs_current": True},
            retrieved_memories=[
                {
                    "memory_id": "old_location",
                    "entity": "rachel",
                    "slot": "location",
                    "value": "Rachel lived in Boston.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_location",
                    "entity": "rachel",
                    "slot": "location",
                    "value": "Rachel moved to Denver.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_historical_recall_with_retrieved_slot_conflict_stays_direct(self) -> None:
        route = route_query_risk(
            "Where did Maya live before she moved?",
            retrieved_memories=[
                {
                    "memory_id": "old_location",
                    "entity": "maya",
                    "slot": "location",
                    "value": "Maya lived in Darwin.",
                    "observed_at": "2023-06-01T00:00:00+00:00",
                },
                {
                    "memory_id": "new_location",
                    "entity": "maya",
                    "slot": "location",
                    "value": "Maya moved to Melbourne.",
                    "observed_at": "2025-03-01T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_preference_recall_fails_open_to_direct(self) -> None:
        route = route_query_risk("What brand of BBQ sauce am I currently obsessed with?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_recent_event_recall_fails_open_to_direct(self) -> None:
        route = route_query_risk("Where did Rachel move to after her recent relocation?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_inventory_question_without_evidence_risk_stays_direct(self) -> None:
        route = route_query_risk(
            "How many dozen eggs do we currently have stocked up in our refrigerator?"
        )

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_current_inventory_question_with_stale_status_routes_to_qvf(self) -> None:
        route = route_query_risk(
            "How many dozen eggs do we currently have stocked up in our refrigerator?",
            retrieved_memories=[
                {"memory_id": "old_count", "current_status": "stale"},
                {"memory_id": "new_count", "current_status": "current"},
            ],
        )

        self.assertEqual(route["query_type"], "current_state_or_update")
        self.assertEqual(route["recommended_route"], "qvf_current_archive_router")
        self.assertTrue(route["should_apply_qvf"])

    def test_past_vs_now_comparison_still_routes_to_qvf(self) -> None:
        route = route_query_risk(
            "How much more miles per gallon was my car getting a few months ago compared to now?"
        )

        self.assertEqual(route["query_type"], "current_state_or_update")
        self.assertEqual(route["recommended_route"], "qvf_current_archive_router")
        self.assertTrue(route["should_apply_qvf"])

    def test_plain_change_question_routes_to_direct_preserve_first(self) -> None:
        route = route_query_risk("How did the user's residence change?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_change_detail_with_update_evidence_routes_to_transition(self) -> None:
        route = route_query_risk(
            "How did the user's residence change?",
            retrieved_memories=[
                {
                    "memory_id": "old_residence",
                    "entity": "user",
                    "slot": "residence",
                    "value": "Darwin",
                    "claim": "User moved to Darwin.",
                    "observed_at": "2022-01-30T00:00:00+00:00",
                },
                {
                    "memory_id": "new_residence",
                    "entity": "user",
                    "slot": "residence_change",
                    "value": "moved to Melbourne",
                    "claim": "User moved to Melbourne.",
                    "observed_at": "2022-02-25T00:00:00+00:00",
                },
            ],
        )

        self.assertEqual(route["query_type"], "temporal_reasoning")
        self.assertEqual(route["recommended_route"], TRANSITION_ROUTE)
        self.assertTrue(route["should_apply_qvf"])

    def test_previous_only_history_recall_stays_direct(self) -> None:
        route = route_query_risk("What was my previous stance on spirituality?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_before_move_history_recall_stays_direct(self) -> None:
        route = route_query_risk("Where did Maya live before she moved?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_previous_vs_current_routes_to_qvf(self) -> None:
        route = route_query_risk("What changed between my previous stance and now?")

        self.assertEqual(route["query_type"], "current_state_or_update")
        self.assertEqual(route["recommended_route"], "qvf_current_archive_router")
        self.assertTrue(route["should_apply_qvf"])

    def test_recent_scoped_question_routes_to_qvf_with_medium_risk(self) -> None:
        route = route_query_risk("What type of tea blend did I try last weekend?")

        self.assertEqual(route["query_type"], "temporal_reasoning")
        self.assertEqual(route["recommended_route"], "qvf_hybrid_router")
        self.assertTrue(route["should_apply_qvf"])

    def test_plain_condition_question_routes_to_direct_preserve_first(self) -> None:
        route = route_query_risk("Under what condition does the user prefer audiobooks?")

        self.assertEqual(route["query_type"], "ordinary_recall")
        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_condition_preference_with_condition_evidence_routes_to_qvf(self) -> None:
        route = route_query_risk(
            "Under what condition does the user prefer audiobooks?",
            retrieved_memories=[
                {
                    "memory_id": "commute_audio",
                    "slot": "usage",
                    "claim": (
                        "User tends to use audiobooks for professional self-improvement "
                        "and technique study while commuting."
                    ),
                    "source": {
                        "source_span": (
                            "I commute daily and tend to use audiobooks for professional "
                            "self-improvement and technique study while commuting."
                        )
                    },
                }
            ],
        )

        self.assertEqual(route["query_type"], "conditional_scope")
        self.assertEqual(route["recommended_route"], "qvf_conditional_scope_router")
        self.assertTrue(route["should_apply_qvf"])
        self.assertEqual(route["evidence_risk"]["condition_bearing_record_count"], 1)

    def test_condition_preference_without_condition_evidence_stays_direct(self) -> None:
        route = route_query_risk(
            "When does the user prefer audiobooks?",
            retrieved_memories=[
                {
                    "memory_id": "audio",
                    "slot": "usage",
                    "claim": "User likes audiobooks.",
                }
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_previous_conversation_lookup_with_condition_words_stays_direct(self) -> None:
        route = route_query_risk(
            "I was looking back at our previous conversation about restaurants. "
            "What was the name of the place that serves great noodles?",
            retrieved_memories=[
                {
                    "memory_id": "restaurant",
                    "slot": "restaurant_name",
                    "claim": "The restaurant serves great noodles during lunch.",
                }
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_memory_status_mix_raises_validity_risk(self) -> None:
        route = route_query_risk(
            "Where should mail go?",
            retrieved_memories=[
                {"current_status": "current"},
                {"current_status": "stale"},
            ],
        )

        self.assertEqual(route["query_type"], "current_state_or_update")
        self.assertTrue(route["should_apply_qvf"])

    def test_archive_role_alone_does_not_force_qvf_for_plain_history(self) -> None:
        route = route_query_risk(
            "What was my previous stance on spirituality?",
            retrieved_memories=[
                {"retrieval_role": "archive"},
            ],
        )

        self.assertEqual(route["recommended_route"], "direct_preserve_first")
        self.assertFalse(route["should_apply_qvf"])

    def test_writer_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "route.json"
            route = write_query_risk_route(
                output,
                query_text="Has the user's employment status stayed the same?",
            )

            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(saved["query_type"], route["query_type"])
        self.assertEqual(saved["recommended_route"], "qvf_transition_router")


if __name__ == "__main__":
    unittest.main()
