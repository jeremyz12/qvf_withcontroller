from __future__ import annotations

from copy import deepcopy
from typing import Any

from .answerability import (
    ARCHIVE_AWARE_QUERY_INTENTS,
    RELATION_GATED_QUERY_INTENTS,
    attested_response_dimension_evidence,
    archive_answer_dimension_authorized,
    build_answerability_boundary,
    build_response_dimension_authorizations,
    normalize_requested_response_dimensions,
    validate_answerability_boundary,
)
from .retrieval import validate_packet_batch, validate_packet_payload

ROUTER_VERSION = "qvf_read_time_router_v0.3_no_api"
VALIDITY_CONTROLLER_VERSION = "qvf_memory_validity_controller_v0.1_no_api"
FACTORIZED_VALIDITY_CONTROLLER_VERSION = (
    "qvf_factorized_memory_validity_controller_v0.2_no_api"
)
READER_VERSION = "qvf_structured_reader_renderer_v0.2_no_api"
READ_DECISION_VALUES = {"ADMIT_CURRENT", "ADMIT_ARCHIVE", "REJECT_STALE_PREMISE", "UNKNOWN_CURRENT"}
READ_ROUTES = {
    "current_support_reader",
    "archive_aware_reader",
    "relation_evidence_insufficient",
    "unknown_current_router",
    "weak_conservative_gate",
}
ANSWER_POLICIES = {
    "answer_from_current",
    "answer_from_archive",
    "correct_then_answer_from_current",
    "correct_premise_only",
    "insufficient_current_state",
    "insufficient_relation_evidence",
}
READ_DECISION_ID_FIELDS = (
    "answer_evidence_ids",
    "blocking_evidence_ids",
    "stale_evidence_ids",
)


def _memory_ids(rows: list[dict[str, Any]]) -> list[str]:
    return [
        str(row.get("memory_id", "")).strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("memory_id", "")).strip()
    ]


def _controller_query_rewrite(
    query: dict[str, Any],
    *,
    temporal_focus: str,
) -> str:
    entity = str(query.get("entity") or "").strip()
    slots = [
        str(slot).strip()
        for slot in [query.get("slot"), *query.get("coordinated_slots", [])]
        if str(slot or "").strip()
    ]
    slot = ", ".join(dict.fromkeys(slots))
    if not entity and not slot:
        return ""
    target = " ".join(part for part in [entity, slot] if part)
    if temporal_focus == "current":
        return f"Retrieve current valid evidence for {target}."
    if temporal_focus == "timeline":
        return f"Retrieve timeline and source-history evidence for {target}."
    if temporal_focus == "historical_or_query_scoped":
        return f"Retrieve query-scoped archive evidence for {target}."
    return f"Retrieve evidence for {target}."


def _query_needs_source_history(query: dict[str, Any]) -> bool:
    query_intent = str(query.get("query_intent", "current_state"))
    if query_intent in {"timeline_change", "conflict_audit", "validity_audit"}:
        return True
    text = " ".join(
        str(query.get(field_name, "") or "")
        for field_name in ("query", "text")
    ).lower()
    padded = f" {text} "
    markers = (
        " when ",
        " what date ",
        " which date ",
        " before ",
        " after ",
        " recent ",
        " recently ",
        " latest ",
        " last ",
        " previous ",
        " first ",
        " earliest ",
        " moved ",
        " changed ",
        " started ",
        " ended ",
        " weekend ",
        " month ",
        " year ",
    )
    return any(marker in padded for marker in markers)


def _build_validity_controller_decision(
    packet: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Return the controller action behind a read-time decision.

    The controller is intentionally action-oriented: it says whether the visible
    evidence is sufficient, whether raw archive rows remain usable as history,
    and what retrieval repair should happen when current evidence is missing.
    It does not add answer labels or benchmark-specific targets.
    """

    query = packet["query"]
    compact_packet = packet.get("compact_validity_packet", {})
    current = compact_packet.get("current_evidence", [])
    historical = compact_packet.get("historical_evidence", [])
    stale = compact_packet.get("stale_or_blocked_evidence", [])
    excluded = compact_packet.get("excluded_memory_summary", [])
    supporting = compact_packet.get("supporting_evidence", [])
    requested_dimensions = normalize_requested_response_dimensions(
        query.get("requested_response_dimensions")
    )
    dimension_evidence = attested_response_dimension_evidence(
        current_evidence=current,
        historical_evidence=historical,
        stale_or_blocked_evidence=stale,
        supporting_evidence=supporting,
    )

    answer_policy = decision.get("answer_policy", "")
    query_intent = str(query.get("query_intent", "current_state"))
    stale_ids = _memory_ids(stale)
    blocked_ids = list(decision.get("blocking_evidence_ids", []))
    answer_ids = list(decision.get("answer_evidence_ids", []))
    current_ids = _memory_ids(current)
    premise_blocker_ids: list[str] = []
    temporal_focus = "current"
    include_current = True
    include_archive = False
    include_source_history = False
    evidence_sufficiency = "insufficient_current_evidence"
    next_action = "retrieve_current_entity_slot"
    reason = "No admitted current answer evidence is available."
    allowed_as_history_ids: list[str] = []
    boundary_answer_policy = answer_policy

    if answer_policy == "answer_from_current":
        evidence_sufficiency = "sufficient_current_evidence"
        next_action = "answer_from_current"
        reason = "Admitted current evidence can answer the query."
        allowed_as_history_ids = stale_ids
    elif answer_policy == "answer_from_archive":
        evidence_sufficiency = "sufficient_archive_or_historical_evidence"
        next_action = "answer_from_archive"
        temporal_focus = "historical_or_query_scoped"
        include_archive = True
        include_source_history = _query_needs_source_history(query)
        reason = (
            "The query asks for historical, timeline, conflict, or validity context; "
            "archive evidence remains usable with an explicit time/status boundary."
        )
        allowed_as_history_ids = list(dict.fromkeys(answer_ids + stale_ids))
    elif answer_policy == "correct_then_answer_from_current":
        evidence_sufficiency = "stale_premise_with_current_evidence"
        next_action = "correct_premise_then_answer_from_current"
        reason = "A stale premise is blocked as current, but current evidence is available."
        allowed_as_history_ids = stale_ids
        premise_blocker_ids = blocked_ids
    elif answer_policy == "correct_premise_only":
        evidence_sufficiency = "stale_premise_without_answerable_current_evidence"
        next_action = "retrieve_current_entity_slot"
        reason = (
            "The visible evidence can reject the stale premise but cannot safely answer "
            "the requested current state without more current evidence."
        )
        allowed_as_history_ids = stale_ids
        premise_blocker_ids = blocked_ids
    elif query_intent in RELATION_GATED_QUERY_INTENTS:
        evidence_sufficiency = "insufficient_relation_evidence"
        next_action = "retrieve_entity_slot_timeline"
        temporal_focus = "timeline"
        include_archive = True
        include_source_history = True
        reason = (
            "The query asks for a historical or relational answer dimension, but "
            "the visible evidence does not establish the required timeline, conflict, "
            "or validity relation."
        )
        allowed_as_history_ids = list(
            dict.fromkeys(_memory_ids(historical) + stale_ids)
        )
    elif historical or stale:
        evidence_sufficiency = "archive_or_stale_only_for_current_query"
        next_action = "retrieve_current_entity_slot"
        reason = (
            "Only archive, stale, or blocked rows are visible for a current-state query; "
            "keep them as history but retrieve current entity-slot evidence before "
            "answering as current."
        )
        allowed_as_history_ids = list(dict.fromkeys(_memory_ids(historical) + stale_ids))
    elif excluded or supporting:
        evidence_sufficiency = "insufficient_relevant_current_evidence"
        next_action = "query_rewrite_and_retrieve"
        reason = (
            "Visible rows are excluded, uncertain, or supporting-only; rewrite the query "
            "around the entity-slot and retrieve again."
        )
    else:
        evidence_sufficiency = "no_visible_answer_evidence"
        next_action = "retrieve_entity_slot_timeline"
        temporal_focus = "timeline"
        include_archive = True
        include_source_history = True
        reason = "No visible answer evidence is available; retrieve a bounded timeline."

    premise_dimension_ids = list(dict.fromkeys([*blocked_ids, *stale_ids]))
    if requested_dimensions:
        dimension_preview = build_response_dimension_authorizations(
            requested_response_dimensions=requested_dimensions,
            next_action=next_action,
            visible_evidence_ids=dimension_evidence["visible_evidence_ids"],
            current_value_evidence_ids=(
                answer_ids
                if answer_policy
                in {"answer_from_current", "correct_then_answer_from_current"}
                else []
            ),
            historical_value_evidence_ids=(
                answer_ids
                if answer_policy == "answer_from_archive"
                else dimension_evidence["historical_value_evidence_ids"]
            ),
            change_relation_evidence_ids=dimension_evidence[
                "change_relation_evidence_ids"
            ],
            transition_endpoint_evidence_ids=dimension_evidence[
                "transition_endpoint_evidence_ids"
            ],
            premise_correction_evidence_ids=premise_dimension_ids,
            conflict_evidence_ids=dimension_evidence["conflict_evidence_ids"],
        )
        if dimension_preview["can_answer_all_requested_dimensions"]:
            boundary_answer_policy = "answer_from_authorized_dimensions"
            evidence_sufficiency = "sufficient_requested_response_dimensions"
            next_action = "answer_from_authorized_dimensions"
            reason = (
                "Every explicitly requested response dimension has visible, "
                "source-backed evidence; answer only those dimensions."
            )
            if set(requested_dimensions) & {
                "historical_value",
                "change_existence",
                "transition_endpoints",
                "premise_validity",
                "conflict_presence",
            }:
                temporal_focus = "historical_or_query_scoped"
                include_archive = True
                include_source_history = True
                allowed_as_history_ids = list(
                    dict.fromkeys(
                        _memory_ids(historical) + stale_ids
                    )
                )

    if next_action in {"retrieve_entity_slot_timeline", "query_rewrite_and_retrieve"}:
        temporal_focus = "timeline" if next_action == "retrieve_entity_slot_timeline" else temporal_focus
        include_archive = True
        include_source_history = True

    blocked_as_current_ids = blocked_ids
    if decision.get("decision") == "REJECT_STALE_PREMISE":
        current_id_set = set(current_ids)
        blocked_as_current_ids = [
            memory_id for memory_id in blocked_ids if memory_id not in current_id_set
        ]

    suggested_retrieval_scope = {
        "entity": str(query.get("entity", "")),
        "slot": str(query.get("slot", "")),
        "temporal_focus": temporal_focus,
        "include_current": include_current,
        "include_archive": include_archive,
        "include_source_history": include_source_history,
    }
    if query.get("coordinated_slots"):
        suggested_retrieval_scope["coordinated_slots"] = list(
            query["coordinated_slots"]
        )

    answerability_boundary = validate_answerability_boundary(
        build_answerability_boundary(
            answer_policy=boundary_answer_policy,
            evidence_sufficiency=evidence_sufficiency,
            next_action=next_action,
            answer_evidence_ids=answer_ids,
            premise_correction_evidence_ids=premise_dimension_ids,
            requested_response_dimensions=requested_dimensions,
            visible_evidence_ids=dimension_evidence["visible_evidence_ids"],
            current_value_evidence_ids=(
                answer_ids
                if answer_policy
                in {"answer_from_current", "correct_then_answer_from_current"}
                else []
            ),
            historical_value_evidence_ids=(
                answer_ids
                if answer_policy == "answer_from_archive"
                else dimension_evidence["historical_value_evidence_ids"]
            ),
            change_relation_evidence_ids=dimension_evidence[
                "change_relation_evidence_ids"
            ],
            transition_endpoint_evidence_ids=dimension_evidence[
                "transition_endpoint_evidence_ids"
            ],
            conflict_evidence_ids=dimension_evidence["conflict_evidence_ids"],
        )
    )

    return {
        "controller_version": (
            FACTORIZED_VALIDITY_CONTROLLER_VERSION
            if requested_dimensions
            else VALIDITY_CONTROLLER_VERSION
        ),
        "evidence_sufficiency": evidence_sufficiency,
        "answerability_state": answerability_boundary["answerability_state"],
        "answerability_boundary": answerability_boundary,
        "next_action": next_action,
        "reason": reason,
        "query_rewrite": _controller_query_rewrite(
            query,
            temporal_focus=temporal_focus,
        )
        if next_action.startswith("retrieve") or next_action == "query_rewrite_and_retrieve"
        else "",
        "suggested_retrieval_scope": suggested_retrieval_scope,
        "blocked_as_current_ids": list(dict.fromkeys(blocked_as_current_ids + stale_ids)),
        "allowed_as_history_ids": allowed_as_history_ids,
        "premise_blocker_ids": premise_blocker_ids,
        "diagnostic_evidence_ids": list(
            dict.fromkeys(
                answer_ids
                + blocked_ids
                + stale_ids
                + _memory_ids(excluded)
                + _memory_ids(supporting)
            )
        ),
    }


def _attach_validity_controller_decision(
    packet: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    out = dict(decision)
    out["validity_controller_decision"] = _build_validity_controller_decision(
        packet,
        out,
    )
    return out


def validate_weak_gate_outputs_payload(
    weak_gate_outputs: Any,
    *,
    context: str = "weak_gate_outputs",
    optional: bool = False,
) -> list[dict[str, Any]] | None:
    if weak_gate_outputs is None and optional:
        return None
    if not isinstance(weak_gate_outputs, list):
        raise ValueError(f"{context} must be a list")
    seen_task_ids: set[str] = set()
    seen_query_ids: set[str] = set()
    for index, output in enumerate(weak_gate_outputs):
        if not isinstance(output, dict):
            raise ValueError(f"{context}[{index}] must be an object")
        task_id = output.get("task_id")
        query_id = output.get("query_id")
        has_task_id = isinstance(task_id, str) and bool(task_id.strip())
        has_query_id = isinstance(query_id, str) and bool(query_id.strip())
        if not has_task_id and not has_query_id:
            raise ValueError(f"{context}[{index}] must include task_id or query_id")
        if has_task_id:
            normalized_task_id = task_id.strip()
            if normalized_task_id in seen_task_ids:
                raise ValueError(f"Duplicate weak gate output task_id: {normalized_task_id}")
            seen_task_ids.add(normalized_task_id)
        if has_query_id:
            normalized_query_id = query_id.strip()
            if normalized_query_id in seen_query_ids:
                raise ValueError(f"Duplicate weak gate output query_id: {normalized_query_id}")
            seen_query_ids.add(normalized_query_id)
    return weak_gate_outputs


def build_read_decisions(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packets = validate_packet_batch(packets)
    return [route_read_time_packet(packet) for packet in packets]


def build_weak_gate_tasks(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packets = validate_packet_batch(packets)
    tasks: list[dict[str, Any]] = []
    for packet in packets:
        card = packet.get("weak_conservative_gate_card")
        if card is None:
            continue
        if not card.get("query", {}).get("embedded_premise_value"):
            continue
        query_id = packet["query"]["query_id"]
        tasks.append(
            {
                "task_id": f"weak_gate::{query_id}",
                "query_id": query_id,
                "adapter": card["adapter"],
                "purpose": card["purpose"],
                "input": {
                    "query": card["query"],
                    "decision_rules": card["decision_rules"],
                    "current_candidate_evidence": card["current_candidate_evidence"],
                    "stale_or_blocked_evidence": card["stale_or_blocked_evidence"],
                    "excluded_evidence": card["excluded_evidence"],
                },
                "output_schema": card["reader_output_schema"],
                "expected_gate_decision": card["expected_gate_decision"],
                "packet_diagnostics": {
                    "retrieval_diagnostics": packet.get("retrieval_diagnostics", {}),
                    "token_budget_proxy": packet.get("token_budget_proxy", {}),
                },
            }
        )
    return tasks


def normalize_weak_gate_decision(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "ADMIT": "ADMIT_CURRENT",
        "CURRENT": "ADMIT_CURRENT",
        "ANSWER_CURRENT": "ADMIT_CURRENT",
        "REJECT": "REJECT_STALE_PREMISE",
        "REJECT_STALE": "REJECT_STALE_PREMISE",
        "STALE": "REJECT_STALE_PREMISE",
        "STALE_PREMISE": "REJECT_STALE_PREMISE",
        "UNKNOWN": "UNKNOWN_CURRENT",
        "UNSURE": "UNKNOWN_CURRENT",
        "ABSTAIN": "UNKNOWN_CURRENT",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in READ_DECISION_VALUES:
        return None
    return normalized


def score_weak_gate_outputs(
    weak_gate_tasks: list[dict[str, Any]],
    weak_gate_outputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(weak_gate_tasks, list):
        raise ValueError("weak_gate_tasks must be a list")
    weak_gate_outputs = validate_weak_gate_outputs_payload(weak_gate_outputs)
    outputs_by_task_id: dict[str, dict[str, Any]] = {}
    outputs_by_query_id: dict[str, dict[str, Any]] = {}
    for output in weak_gate_outputs:
        task_id = output.get("task_id")
        query_id = output.get("query_id")
        if isinstance(task_id, str) and task_id.strip():
            outputs_by_task_id[task_id.strip()] = output
        if isinstance(query_id, str) and query_id.strip():
            outputs_by_query_id[query_id.strip()] = output

    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_WEAK_GATE_ANALYSIS_READY_NO_API",
        "execution_mode": "weak_gate_analysis_only",
        "task_count": len(weak_gate_tasks),
        "output_count": len(weak_gate_outputs),
        "matched_output_count": 0,
        "missing_output_count": 0,
        "parseable_decision_count": 0,
        "unparseable_decision_count": 0,
        "decision_correct_count": 0,
        "decision_accuracy_on_matched": None,
        "decision_accuracy_on_parseable": None,
        "expected_gate_decision_counts": {},
        "predicted_decision_counts": {},
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API weak-gate result analyzer, not a model run.",
            "Accuracy reflects only the provided structured weak-model outputs against task-pack expected decisions.",
        ],
    }

    for task in weak_gate_tasks:
        if not isinstance(task, dict):
            raise ValueError("weak gate tasks must be objects")
        task_id = task.get("task_id")
        query_id = task.get("query_id")
        expected_decision = task.get("expected_gate_decision")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("weak gate task.task_id must be a non-empty string")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("weak gate task.query_id must be a non-empty string")
        if expected_decision not in READ_DECISION_VALUES:
            raise ValueError("weak gate task.expected_gate_decision is invalid")
        summary["expected_gate_decision_counts"][expected_decision] = (
            summary["expected_gate_decision_counts"].get(expected_decision, 0) + 1
        )

        output = outputs_by_task_id.get(task_id) or outputs_by_query_id.get(query_id)
        row = {
            "task_id": task_id,
            "query_id": query_id,
            "expected_gate_decision": expected_decision,
            "predicted_decision": "",
            "decision_parseable": "0",
            "decision_correct": "0",
            "support": "",
            "blocker": "",
            "final_answer": "",
            "error": "",
        }
        if output is None:
            row["error"] = "missing_output"
            summary["missing_output_count"] += 1
            rows.append(row)
            continue

        summary["matched_output_count"] += 1
        predicted_decision = normalize_weak_gate_decision(output.get("decision"))
        row["support"] = str(output.get("support", ""))
        row["blocker"] = str(output.get("blocker", ""))
        row["final_answer"] = str(output.get("final_answer", ""))
        if predicted_decision is None:
            row["error"] = "unparseable_decision"
            summary["unparseable_decision_count"] += 1
            rows.append(row)
            continue

        row["predicted_decision"] = predicted_decision
        row["decision_parseable"] = "1"
        summary["parseable_decision_count"] += 1
        summary["predicted_decision_counts"][predicted_decision] = (
            summary["predicted_decision_counts"].get(predicted_decision, 0) + 1
        )
        if predicted_decision == expected_decision:
            row["decision_correct"] = "1"
            summary["decision_correct_count"] += 1
        rows.append(row)

    if summary["matched_output_count"]:
        summary["decision_accuracy_on_matched"] = (
            summary["decision_correct_count"] / summary["matched_output_count"]
        )
    if summary["parseable_decision_count"]:
        summary["decision_accuracy_on_parseable"] = (
            summary["decision_correct_count"] / summary["parseable_decision_count"]
        )
    return rows, summary


def build_read_decisions_from_weak_gate_outputs(
    packets: list[dict[str, Any]],
    weak_gate_tasks: list[dict[str, Any]],
    weak_gate_outputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packets = validate_packet_batch(packets)
    _, weak_gate_analysis = score_weak_gate_outputs(weak_gate_tasks, weak_gate_outputs)
    tasks_by_query_id = _index_weak_gate_tasks_by_query_id(weak_gate_tasks)
    outputs_by_task_id, outputs_by_query_id = _index_weak_gate_outputs(weak_gate_outputs)

    decisions: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_WEAK_GATE_DECISION_ADAPTER_READY_NO_API",
        "execution_mode": "weak_gate_decision_adapter_only",
        "packet_count": len(packets),
        "weak_gate_task_count": len(weak_gate_tasks),
        "weak_gate_output_count": len(weak_gate_outputs),
        "adapted_from_weak_gate_output_count": 0,
        "fallback_no_task_count": 0,
        "fallback_missing_or_unparseable_output_count": 0,
        "read_decision_counts": {},
        "read_route_counts": {},
        "decision_source_counts": {},
        "weak_gate_analysis": weak_gate_analysis,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API weak-gate decision adapter, not a model run.",
            "It converts provided structured weak-gate outputs into QVF read decisions for downstream rendering.",
        ],
    }

    for packet in packets:
        query_id = packet["query"]["query_id"]
        task = tasks_by_query_id.get(query_id)
        if task is None:
            decision = route_read_time_packet(packet)
            decision["decision_source"] = "deterministic_router_fallback_no_weak_gate_task"
            summary["fallback_no_task_count"] += 1
        else:
            output = (
                outputs_by_task_id.get(task["task_id"])
                or outputs_by_query_id.get(query_id)
            )
            predicted_decision = (
                normalize_weak_gate_decision(output.get("decision"))
                if output is not None
                else None
            )
            if predicted_decision is None:
                decision = _weak_gate_failure_decision(
                    packet,
                    task,
                    reason="missing_or_unparseable_weak_gate_output",
                )
                summary["fallback_missing_or_unparseable_output_count"] += 1
            else:
                decision = _weak_gate_output_to_read_decision(
                    packet,
                    task,
                    output,
                    predicted_decision,
                )
                summary["adapted_from_weak_gate_output_count"] += 1
        decision = validate_read_decision_payload(decision, expected_query_id=query_id)
        decisions.append(decision)
        summary["read_decision_counts"][decision["decision"]] = (
            summary["read_decision_counts"].get(decision["decision"], 0) + 1
        )
        summary["read_route_counts"][decision["route"]] = (
            summary["read_route_counts"].get(decision["route"], 0) + 1
        )
        source = decision.get("decision_source", "unknown")
        summary["decision_source_counts"][source] = (
            summary["decision_source_counts"].get(source, 0) + 1
        )
    return decisions, summary


def _index_weak_gate_tasks_by_query_id(
    weak_gate_tasks: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    tasks_by_query_id: dict[str, dict[str, Any]] = {}
    for task in weak_gate_tasks:
        if not isinstance(task, dict):
            raise ValueError("weak gate tasks must be objects")
        query_id = task.get("query_id")
        task_id = task.get("task_id")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("weak gate task.query_id must be a non-empty string")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("weak gate task.task_id must be a non-empty string")
        if query_id in tasks_by_query_id:
            raise ValueError(f"Duplicate weak gate task query_id: {query_id}")
        tasks_by_query_id[query_id] = task
    return tasks_by_query_id


def _index_weak_gate_outputs(
    weak_gate_outputs: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    outputs_by_task_id: dict[str, dict[str, Any]] = {}
    outputs_by_query_id: dict[str, dict[str, Any]] = {}
    for output in weak_gate_outputs:
        if not isinstance(output, dict):
            raise ValueError("weak gate output rows must be objects")
        task_id = output.get("task_id")
        query_id = output.get("query_id")
        if isinstance(task_id, str) and task_id.strip():
            if task_id in outputs_by_task_id:
                raise ValueError(f"Duplicate weak gate output task_id: {task_id}")
            outputs_by_task_id[task_id] = output
        if isinstance(query_id, str) and query_id.strip():
            if query_id in outputs_by_query_id:
                raise ValueError(f"Duplicate weak gate output query_id: {query_id}")
            outputs_by_query_id[query_id] = output
    return outputs_by_task_id, outputs_by_query_id


def _weak_gate_output_to_read_decision(
    packet: dict[str, Any],
    task: dict[str, Any],
    output: dict[str, Any],
    predicted_decision: str,
) -> dict[str, Any]:
    query_id = packet["query"]["query_id"]
    reader_profile = packet["query"].get("reader_profile", "default")
    current_ids = _weak_gate_task_evidence_ids(task, "current_candidate_evidence")
    stale_ids = _weak_gate_task_evidence_ids(task, "stale_or_blocked_evidence")
    excluded_ids = _weak_gate_task_evidence_ids(task, "excluded_evidence")
    _validate_decision_ids_in_packet(packet, current_ids + stale_ids + excluded_ids)

    if predicted_decision == "ADMIT_CURRENT":
        answer_policy = "answer_from_current"
        answer_ids = current_ids
        blocking_ids: list[str] = []
        hint = "Use the weak gate admitted current candidate evidence."
    elif predicted_decision == "REJECT_STALE_PREMISE":
        if reader_profile == "dim3_actionable" and current_ids:
            answer_policy = "correct_then_answer_from_current"
            answer_ids = current_ids
        else:
            answer_policy = "correct_premise_only"
            answer_ids = []
        blocking_ids = current_ids
        hint = "Correct the stale embedded premise; do not answer from stale evidence."
    else:
        answer_policy = "insufficient_current_state"
        answer_ids = []
        blocking_ids = current_ids + excluded_ids
        hint = "Weak gate reported unknown current state; do not answer from stale evidence."

    return {
        "router_version": ROUTER_VERSION,
        "query_id": query_id,
        "route": "weak_conservative_gate",
        "decision": predicted_decision,
        "answer_policy": answer_policy,
        "answer_evidence_ids": answer_ids,
        "blocking_evidence_ids": blocking_ids,
        "stale_evidence_ids": stale_ids,
        "final_answer_hint": hint,
        "reader_contract": (
            "Decision adapted from structured weak gate output; evidence ids are selected "
            "from the validated weak gate task pack."
        ),
        "decision_source": "weak_gate_output",
        "weak_gate_output_decision": str(output.get("decision", "")),
        "weak_gate_output_support": str(output.get("support", "")),
        "weak_gate_output_blocker": str(output.get("blocker", "")),
    }


def _weak_gate_failure_decision(
    packet: dict[str, Any],
    task: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    current_ids = _weak_gate_task_evidence_ids(task, "current_candidate_evidence")
    stale_ids = _weak_gate_task_evidence_ids(task, "stale_or_blocked_evidence")
    excluded_ids = _weak_gate_task_evidence_ids(task, "excluded_evidence")
    _validate_decision_ids_in_packet(packet, current_ids + stale_ids + excluded_ids)
    return {
        "router_version": ROUTER_VERSION,
        "query_id": packet["query"]["query_id"],
        "route": "weak_conservative_gate",
        "decision": "UNKNOWN_CURRENT",
        "answer_policy": "insufficient_current_state",
        "answer_evidence_ids": [],
        "blocking_evidence_ids": current_ids + excluded_ids,
        "stale_evidence_ids": stale_ids,
        "final_answer_hint": "Weak gate output is unavailable or unparseable.",
        "reader_contract": "Do not answer from stale evidence when weak gate output fails.",
        "decision_source": reason,
    }


def _weak_gate_task_evidence_ids(task: dict[str, Any], bucket_name: str) -> list[str]:
    value = task.get("input", {}).get(bucket_name, [])
    if not isinstance(value, list):
        raise ValueError(f"weak gate task input.{bucket_name} must be a list")
    ids: list[str] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError(f"weak gate task input.{bucket_name} rows must be objects")
        memory_id = row.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError(f"weak gate task input.{bucket_name}.memory_id must be non-empty")
        ids.append(memory_id)
    return ids


def _validate_decision_ids_in_packet(packet: dict[str, Any], memory_ids: list[str]) -> None:
    evidence_by_id = _packet_evidence_by_id(packet)
    missing_ids = [memory_id for memory_id in memory_ids if memory_id not in evidence_by_id]
    if missing_ids:
        raise ValueError(
            f"weak gate adapted decision references ids not present in packet: "
            f"{', '.join(sorted(set(missing_ids)))}"
        )


def build_reader_responses(
    packets: list[dict[str, Any]], read_decisions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    packets = validate_packet_batch(packets)
    if not isinstance(read_decisions, list):
        raise ValueError("read_decisions must be a list")
    if len(packets) != len(read_decisions):
        raise ValueError("packets and read_decisions must have the same length")
    return [
        render_reader_response(packet, decision)
        for packet, decision in zip(packets, read_decisions)
    ]


def validate_read_decision_payload(
    decision: dict[str, Any], *, expected_query_id: str | None = None
) -> dict[str, Any]:
    if not isinstance(decision, dict):
        raise ValueError("read decision must be an object")
    validated = deepcopy(decision)
    for field_name in ["query_id", "route", "decision", "answer_policy"]:
        value = validated.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"read_decision.{field_name} must be a non-empty string")
    if expected_query_id is not None and validated["query_id"] != expected_query_id:
        raise ValueError(
            f"read_decision.query_id {validated['query_id']} does not match packet query_id "
            f"{expected_query_id}"
        )
    if validated["route"] not in READ_ROUTES:
        known = ", ".join(sorted(READ_ROUTES))
        raise ValueError(f"read_decision.route must be one of: {known}")
    if validated["decision"] not in READ_DECISION_VALUES:
        known = ", ".join(sorted(READ_DECISION_VALUES))
        raise ValueError(f"read_decision.decision must be one of: {known}")
    if validated["answer_policy"] not in ANSWER_POLICIES:
        known = ", ".join(sorted(ANSWER_POLICIES))
        raise ValueError(f"read_decision.answer_policy must be one of: {known}")
    for field_name in READ_DECISION_ID_FIELDS:
        validated[field_name] = _validate_read_decision_id_list(validated, field_name)
    reader_contract = validated.get("reader_contract")
    if reader_contract is not None and not isinstance(reader_contract, str):
        raise ValueError("read_decision.reader_contract must be a string")
    final_answer_hint = validated.get("final_answer_hint")
    if final_answer_hint is not None and not isinstance(final_answer_hint, str):
        raise ValueError("read_decision.final_answer_hint must be a string")
    return validated


def _validate_read_decision_id_list(
    decision: dict[str, Any], field_name: str
) -> list[str]:
    value = decision.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"read_decision.{field_name} must be a list")
    out: list[str] = []
    for memory_id in value:
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError(f"read_decision.{field_name} must contain non-empty string ids")
        out.append(memory_id)
    return out


def build_query_results(
    packets: list[dict[str, Any]],
    read_decisions: list[dict[str, Any]],
    reader_responses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    packets = validate_packet_batch(packets)
    if not isinstance(read_decisions, list):
        raise ValueError("read_decisions must be a list")
    if not isinstance(reader_responses, list):
        raise ValueError("reader_responses must be a list")
    if not (len(packets) == len(read_decisions) == len(reader_responses)):
        raise ValueError("packets, read_decisions, and reader_responses must have the same length")
    results: list[dict[str, Any]] = []
    for packet, decision, response in zip(packets, read_decisions, reader_responses):
        query_id = packet["query"]["query_id"]
        decision = validate_read_decision_payload(decision, expected_query_id=query_id)
        response = validate_reader_response_payload(
            response,
            expected_query_id=query_id,
            expected_decision=decision,
        )
        results.append(
            {
                "query_id": query_id,
                "packet": packet,
                "read_decision": decision,
                "reader_response": response,
            }
        )
    return results


def validate_reader_response_payload(
    response: dict[str, Any],
    *,
    expected_query_id: str | None = None,
    expected_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValueError("reader response must be an object")
    validated = deepcopy(response)
    for field_name in [
        "reader_version",
        "query_id",
        "decision",
        "answer_policy",
        "route",
        "final_answer",
    ]:
        value = validated.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"reader_response.{field_name} must be a non-empty string")
    if expected_query_id is not None and validated["query_id"] != expected_query_id:
        raise ValueError(
            f"reader_response.query_id {validated['query_id']} does not match packet query_id "
            f"{expected_query_id}"
        )
    if validated["decision"] not in READ_DECISION_VALUES:
        known = ", ".join(sorted(READ_DECISION_VALUES))
        raise ValueError(f"reader_response.decision must be one of: {known}")
    if validated["answer_policy"] not in ANSWER_POLICIES:
        known = ", ".join(sorted(ANSWER_POLICIES))
        raise ValueError(f"reader_response.answer_policy must be one of: {known}")
    if validated["route"] not in READ_ROUTES:
        known = ", ".join(sorted(READ_ROUTES))
        raise ValueError(f"reader_response.route must be one of: {known}")
    for field_name in READ_DECISION_ID_FIELDS:
        validated[field_name] = _validate_reader_response_id_list(validated, field_name)
    control = validated.get("control")
    if not isinstance(control, dict):
        raise ValueError("reader_response.control must be an object")
    for field_name in ["used_stale_as_answer_evidence", "requires_llm_freeform_completion"]:
        if not isinstance(control.get(field_name), bool):
            raise ValueError(f"reader_response.control.{field_name} must be a boolean")
    reader_contract = control.get("reader_contract")
    if not isinstance(reader_contract, str):
        raise ValueError("reader_response.control.reader_contract must be a string")
    if expected_decision is not None:
        _validate_reader_response_matches_decision(validated, expected_decision)
    return validated


def _validate_reader_response_id_list(
    response: dict[str, Any], field_name: str
) -> list[str]:
    value = response.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"reader_response.{field_name} must be a list")
    out: list[str] = []
    for memory_id in value:
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError(f"reader_response.{field_name} must contain non-empty string ids")
        out.append(memory_id)
    return out


def _validate_reader_response_matches_decision(
    response: dict[str, Any], decision: dict[str, Any]
) -> None:
    for field_name in ["decision", "answer_policy", "route"]:
        if response[field_name] != decision[field_name]:
            raise ValueError(
                f"reader_response.{field_name} does not match read_decision.{field_name}"
            )
    for field_name in READ_DECISION_ID_FIELDS:
        if response[field_name] != decision[field_name]:
            raise ValueError(
                f"reader_response.{field_name} does not match read_decision.{field_name}"
            )


def render_reader_response(packet: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    packet = validate_packet_payload(packet)
    query = packet["query"]
    decision = validate_read_decision_payload(decision, expected_query_id=query["query_id"])
    evidence_by_id = _packet_evidence_by_id(packet)
    answer_ids = list(decision.get("answer_evidence_ids", []))
    blocking_ids = list(decision.get("blocking_evidence_ids", []))
    stale_ids = list(decision.get("stale_evidence_ids", []))
    answer_evidence = _resolve_decision_evidence(
        evidence_by_id, answer_ids, field_name="answer_evidence_ids", query_id=query["query_id"]
    )
    blocking_evidence = _resolve_decision_evidence(
        evidence_by_id, blocking_ids, field_name="blocking_evidence_ids", query_id=query["query_id"]
    )
    stale_evidence = _resolve_decision_evidence(
        evidence_by_id, stale_ids, field_name="stale_evidence_ids", query_id=query["query_id"]
    )

    final_answer = _render_final_answer(
        query=query,
        decision=decision,
        answer_evidence=answer_evidence,
        blocking_evidence=blocking_evidence,
        stale_evidence=stale_evidence,
    )

    return {
        "reader_version": READER_VERSION,
        "query_id": query["query_id"],
        "decision": decision["decision"],
        "answer_policy": decision["answer_policy"],
        "route": decision["route"],
        "final_answer": final_answer,
        "answer_evidence_ids": answer_ids,
        "blocking_evidence_ids": blocking_ids,
        "stale_evidence_ids": stale_ids,
        "control": {
            "used_stale_as_answer_evidence": False,
            "used_archive_as_answer_evidence": decision["answer_policy"] == "answer_from_archive",
            "requires_llm_freeform_completion": False,
            "reader_contract": decision.get("reader_contract", ""),
        },
    }


def _packet_evidence_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    compact_packet = packet.get("compact_validity_packet", {})
    evidence: dict[str, dict[str, Any]] = {}
    for bucket in [
        "current_evidence",
        "supporting_evidence",
        "historical_evidence",
        "stale_or_blocked_evidence",
        "excluded_memory_summary",
    ]:
        for row in compact_packet.get(bucket, []):
            evidence[row["memory_id"]] = row
    return evidence


def _resolve_decision_evidence(
    evidence_by_id: dict[str, dict[str, Any]],
    memory_ids: list[str],
    *,
    field_name: str,
    query_id: str,
) -> list[dict[str, Any]]:
    missing_ids = [memory_id for memory_id in memory_ids if memory_id not in evidence_by_id]
    if missing_ids:
        raise ValueError(
            f"{field_name} for {query_id} references evidence ids not present in packet: "
            f"{', '.join(missing_ids)}"
        )
    return [evidence_by_id[memory_id] for memory_id in memory_ids]


def _render_final_answer(
    *,
    query: dict[str, Any],
    decision: dict[str, Any],
    answer_evidence: list[dict[str, Any]],
    blocking_evidence: list[dict[str, Any]],
    stale_evidence: list[dict[str, Any]],
) -> str:
    if decision["answer_policy"] == "answer_from_current" and answer_evidence:
        evidence = answer_evidence[0]
        return (
            f"Current admitted memory says {query['entity']} {query['slot']} is "
            f"{evidence['value']}."
        )
    if decision["answer_policy"] == "answer_from_archive" and answer_evidence:
        evidence = answer_evidence[0]
        return (
            f"Historical/archive memory says {query['entity']} {query['slot']} was "
            f"{evidence['value']} ({evidence['memory_id']})."
        )
    if decision["answer_policy"] == "correct_premise_only":
        if blocking_evidence:
            evidence = blocking_evidence[0]
            return (
                f"I should not use the embedded premise as current: current admitted "
                f"memory says {query['entity']} {query['slot']} is {evidence['value']}."
            )
        if stale_evidence:
            evidence = stale_evidence[0]
            return (
                f"I should not answer from that premise; it is only supported by stale "
                f"memory ({evidence['memory_id']})."
            )
        return "I should not answer from the embedded premise because current support is unavailable."
    if decision["answer_policy"] == "correct_then_answer_from_current":
        if answer_evidence:
            evidence = answer_evidence[0]
            return (
                f"I should not use the embedded premise as current. Current admitted "
                f"memory says {query['entity']} {query['slot']} is {evidence['value']}; "
                "answer should be based on that current state."
            )
        if blocking_evidence:
            evidence = blocking_evidence[0]
            return (
                f"I should not use the embedded premise as current. Current admitted "
                f"memory instead says {query['entity']} {query['slot']} is {evidence['value']}."
            )
        return "I should not use the embedded premise, and I do not have current evidence to continue."
    return "I do not have admitted current memory evidence to answer this."


def route_read_time_packet(packet: dict[str, Any]) -> dict[str, Any]:
    packet = validate_packet_payload(packet)
    query = packet["query"]
    compact_packet = packet.get("compact_validity_packet", {})
    weak_gate_card = packet.get("weak_conservative_gate_card")
    query_intent = query.get("query_intent", "current_state")
    archive_aware_intents = ARCHIVE_AWARE_QUERY_INTENTS
    embedded_premise = None
    if weak_gate_card:
        embedded_premise = weak_gate_card.get("query", {}).get("embedded_premise_value")

    current = compact_packet.get("current_evidence", [])
    historical = compact_packet.get("historical_evidence", [])
    archive_dimension_authorized = archive_answer_dimension_authorized(
        query_intent=query_intent,
        query_slot=query.get("slot"),
        embedded_premise=embedded_premise,
        current_evidence=current,
        historical_evidence=historical,
    )

    if weak_gate_card and embedded_premise and not archive_dimension_authorized:
        return _route_weak_gate(packet, weak_gate_card)

    excluded = compact_packet.get("excluded_memory_summary", [])
    if query_intent in archive_aware_intents and archive_dimension_authorized:
        answer_evidence = historical + current
        decision = {
            "router_version": ROUTER_VERSION,
            "query_id": query["query_id"],
            "route": "archive_aware_reader",
            "decision": "ADMIT_ARCHIVE",
            "answer_policy": "answer_from_archive",
            "answer_evidence_ids": [row["memory_id"] for row in answer_evidence],
            "blocking_evidence_ids": [],
            "stale_evidence_ids": [
                row["memory_id"] for row in compact_packet.get("stale_or_blocked_evidence", [])
            ],
            "final_answer_hint": _archive_answer_hint(query, answer_evidence),
            "reader_contract": (
                "Use historical_evidence for historical, timeline, or audit questions. "
                "Do not reinterpret historical evidence as the current state unless it "
                "also appears in current_evidence."
            ),
        }
        return _attach_validity_controller_decision(packet, decision)
    if query_intent in RELATION_GATED_QUERY_INTENTS:
        decision = {
            "router_version": ROUTER_VERSION,
            "query_id": query["query_id"],
            "route": "relation_evidence_insufficient",
            "decision": "UNKNOWN_CURRENT",
            "answer_policy": "insufficient_relation_evidence",
            "answer_evidence_ids": [],
            "blocking_evidence_ids": [],
            "stale_evidence_ids": [
                row["memory_id"]
                for row in compact_packet.get("stale_or_blocked_evidence", [])
            ],
            "final_answer_hint": "",
            "reader_contract": (
                "Do not infer a timeline, transition, conflict, or validity relation "
                "without source-backed relation evidence; retrieve a bounded timeline."
            ),
        }
        return _attach_validity_controller_decision(packet, decision)
    if current:
        decision = {
            "router_version": ROUTER_VERSION,
            "query_id": query["query_id"],
            "route": "current_support_reader",
            "decision": "ADMIT_CURRENT",
            "answer_policy": "answer_from_current",
            "answer_evidence_ids": [row["memory_id"] for row in current],
            "blocking_evidence_ids": [],
            "stale_evidence_ids": [
                row["memory_id"] for row in compact_packet.get("stale_or_blocked_evidence", [])
            ],
            "final_answer_hint": _current_answer_hint(query, current[0]),
            "reader_contract": "Use answer_evidence_ids as answer support; do not answer from stale_evidence_ids.",
        }
        return _attach_validity_controller_decision(packet, decision)

    decision = {
        "router_version": ROUTER_VERSION,
        "query_id": query["query_id"],
        "route": "unknown_current_router",
        "decision": "UNKNOWN_CURRENT",
        "answer_policy": "insufficient_current_state",
        "answer_evidence_ids": [],
        "blocking_evidence_ids": [row["memory_id"] for row in excluded],
        "stale_evidence_ids": [
            row["memory_id"] for row in compact_packet.get("stale_or_blocked_evidence", [])
        ],
        "final_answer_hint": "Current state is unknown from admitted memory evidence.",
        "reader_contract": "Ask for clarification or state that current evidence is unavailable.",
    }
    return _attach_validity_controller_decision(packet, decision)


def _route_weak_gate(packet: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    query = packet["query"]
    reader_profile = query.get("reader_profile", "default")
    decision = card.get("expected_gate_decision", "UNKNOWN_CURRENT")
    current = card.get("current_candidate_evidence", [])
    stale = card.get("stale_or_blocked_evidence", [])
    excluded = card.get("excluded_evidence", [])

    if decision == "ADMIT_CURRENT":
        answer_policy = "answer_from_current"
        answer_ids = [row["memory_id"] for row in current]
        blocker_ids: list[str] = []
        hint = _current_answer_hint(query, current[0]) if current else "Use current evidence."
    elif decision == "REJECT_STALE_PREMISE":
        if reader_profile == "dim3_actionable" and current:
            answer_policy = "correct_then_answer_from_current"
            answer_ids = [row["memory_id"] for row in current]
        else:
            answer_policy = "correct_premise_only"
            answer_ids = []
        blocker_ids = [row["memory_id"] for row in current]
        hint = _stale_premise_hint(query, current, stale, card)
    else:
        answer_policy = "insufficient_current_state"
        answer_ids = []
        blocker_ids = [row["memory_id"] for row in current + excluded]
        hint = "Do not answer from the embedded premise; current state is not established."

    routed = {
        "router_version": ROUTER_VERSION,
        "query_id": query["query_id"],
        "route": "weak_conservative_gate",
        "decision": decision,
        "answer_policy": answer_policy,
        "answer_evidence_ids": answer_ids,
        "blocking_evidence_ids": blocker_ids,
        "stale_evidence_ids": [row["memory_id"] for row in stale],
        "final_answer_hint": hint,
        "reader_contract": (
            "If decision is REJECT_STALE_PREMISE or UNKNOWN_CURRENT, do not answer "
            "the user's embedded request from stale evidence. If answer_policy is "
            "correct_then_answer_from_current, correct the stale premise first and "
            "then answer only from answer_evidence_ids."
        ),
    }
    return _attach_validity_controller_decision(packet, routed)


def _current_answer_hint(query: dict[str, Any], evidence: dict[str, Any]) -> str:
    return (
        f"Current admitted evidence for {query['entity']} {query['slot']} is "
        f"{evidence['value']} ({evidence['memory_id']})."
    )


def _archive_answer_hint(query: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "Use archive-aware context if historical evidence exists."
    values = ", ".join(row["value"] for row in evidence[:3])
    return (
        f"Archive-aware evidence for {query['entity']} {query['slot']} includes "
        f"{values}; label historical or superseded values explicitly."
    )


def _stale_premise_hint(
    query: dict[str, Any],
    current: list[dict[str, Any]],
    stale: list[dict[str, Any]],
    card: dict[str, Any],
) -> str:
    premise = card.get("query", {}).get("embedded_premise_value")
    if current:
        current_value = current[0]["value"]
        return (
            f"Reject the premise {premise!r}; current admitted evidence says "
            f"{query['entity']} {query['slot']} is {current_value}."
        )
    if stale:
        return f"The premise {premise!r} is only supported by stale evidence."
    return "Reject or withhold the embedded premise; no current support is available."



MODEL_FACING_FORBIDDEN_KEYS = {
    "expected_gate_decision",
    "expected_read_time_decision",
    "final_answer_hint",
    "packet_diagnostics",
    "qvf_rendered_answer_hint",
    "retrieval_diagnostics",
}


def sanitize_model_facing_payload(payload: Any) -> Any:
    """Return a copy without internal answer-hint, expected, or diagnostic keys."""
    if isinstance(payload, dict):
        return {
            key: sanitize_model_facing_payload(value)
            for key, value in payload.items()
            if key not in MODEL_FACING_FORBIDDEN_KEYS
        }
    if isinstance(payload, list):
        return [sanitize_model_facing_payload(value) for value in payload]
    return payload


def model_facing_forbidden_key_paths(payload: Any, *, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_path = f"{prefix}.{key}"
            if key in MODEL_FACING_FORBIDDEN_KEYS:
                paths.append(key_path)
            paths.extend(model_facing_forbidden_key_paths(value, prefix=key_path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            paths.extend(
                model_facing_forbidden_key_paths(value, prefix=f"{prefix}[{index}]")
            )
    return paths


def assert_model_facing_payload_is_clean(payload: Any) -> None:
    paths = model_facing_forbidden_key_paths(payload)
    if paths:
        raise ValueError(
            "model-facing QVF payload contains internal leakage keys: "
            + ", ".join(paths)
        )


def build_model_facing_sidecar_payload(query_result: dict[str, Any]) -> dict[str, Any]:
    """Build the safe packet+decision object to pass to a target LLM.

    The read-time decision is part of QVF's sidecar contract. Internal rendered
    answer hints and expected-decision labels are intentionally omitted.
    """
    packet = sanitize_model_facing_payload(query_result["packet"])
    decision = query_result["read_decision"]
    payload = {
        "latest_query": packet["query"]["text"],
        "qvf_validity_admission_packet": packet,
        "qvf_read_time_decision": {
            "decision": decision["decision"],
            "answer_policy": decision["answer_policy"],
            "route": decision["route"],
            "answer_evidence_ids": decision.get("answer_evidence_ids", []),
            "blocking_evidence_ids": decision.get("blocking_evidence_ids", []),
            "stale_evidence_ids": decision.get("stale_evidence_ids", []),
            "reader_contract": decision.get("reader_contract", ""),
            "validity_controller_decision": decision.get(
                "validity_controller_decision",
                {},
            ),
        },
    }
    assert_model_facing_payload_is_clean(payload)
    return payload


def build_model_facing_sidecar_payloads(
    query_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build safe model-facing QVF sidecar payloads for query results."""
    if not isinstance(query_results, list):
        raise ValueError("query_results must be a list")
    return [build_model_facing_sidecar_payload(result) for result in query_results]



__all__ = [
    "MODEL_FACING_FORBIDDEN_KEYS",
    "assert_model_facing_payload_is_clean",
    "build_model_facing_sidecar_payload",
    "build_model_facing_sidecar_payloads",
    "build_query_results",
    "build_read_decisions",
    "build_read_decisions_from_weak_gate_outputs",
    "build_reader_responses",
    "build_weak_gate_tasks",
    "model_facing_forbidden_key_paths",
    "normalize_weak_gate_decision",
    "render_reader_response",
    "route_read_time_packet",
    "sanitize_model_facing_payload",
    "score_weak_gate_outputs",
    "validate_read_decision_payload",
    "validate_reader_response_payload",
    "validate_weak_gate_outputs_payload",
]
