from __future__ import annotations

import argparse
import csv
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .answerability import (
    ARCHIVE_AWARE_QUERY_INTENTS,
    RELATION_GATED_QUERY_INTENTS,
    archive_answer_dimension_authorized,
    build_answerability_boundary,
    normalize_requested_response_dimensions,
    validate_answerability_boundary,
    validate_response_dimension_state,
)
from .semantic_relations import validate_semantic_relation_payload
from .temporal_validity import validate_strict_temporal_payload


ROOT = Path(__file__).resolve().parent
RECORDS_PATH = ROOT / "validity_admission_demo_records.jsonl"
QUERIES_PATH = ROOT / "validity_admission_demo_queries.jsonl"
STORE_OUT = ROOT / "validity_admission_demo_admitted_memory_store.jsonl"
PACKETS_OUT = ROOT / "validity_admission_demo_output_packets.json"
READ_DECISIONS_OUT = ROOT / "validity_admission_demo_read_decisions.json"
READER_RESPONSES_OUT = ROOT / "validity_admission_demo_reader_responses.json"
QUERY_RESULTS_OUT = ROOT / "validity_admission_demo_query_results.json"
STEP_REPORT_OUT = ROOT / "validity_admission_demo_step_report.json"
SERVICE_RESPONSE_OUT = ROOT / "validity_admission_demo_service_response.json"
WEAK_GATE_TASKS_OUT = ROOT / "validity_admission_demo_weak_gate_tasks.json"
WEAK_GATE_RESULTS_IN = ROOT / "validity_admission_demo_weak_gate_model_results.jsonl"
WEAK_GATE_ANALYSIS_OUT = ROOT / "validity_admission_demo_weak_gate_analysis.csv"
ADMISSION_LOG_OUT = ROOT / "validity_admission_demo_admission_log.csv"
SUMMARY_OUT = ROOT / "validity_admission_demo_summary.json"
ADMISSION_LOG_FIELDS = [
    "memory_id",
    "entity",
    "slot",
    "value",
    "observed_at",
    "source_confidence",
    "admission_status",
    "current_status",
    "evidence_role",
    "reason",
]
WEAK_GATE_ANALYSIS_FIELDS = [
    "task_id",
    "query_id",
    "expected_gate_decision",
    "predicted_decision",
    "decision_parseable",
    "decision_correct",
    "support",
    "blocker",
    "final_answer",
    "error",
]

POLICY_VERSION = "qvf_validity_admission_write_retrieve_v0.26_no_api"
ROUTER_VERSION = "qvf_read_time_router_v0.3_no_api"
VALIDITY_CONTROLLER_VERSION = "qvf_memory_validity_controller_v0.1_no_api"
READER_VERSION = "qvf_structured_reader_renderer_v0.2_no_api"
LOW_CONFIDENCE_THRESHOLD = 0.5
LINK_EDGE_TYPES = (
    "supersedes",
    "superseded_by",
    "contradicts",
    "supports",
    "invalidates",
    "invalidated_by",
)
RECIPROCAL_LINK_EDGE_TYPES = {
    "supersedes": "superseded_by",
    "superseded_by": "supersedes",
    "invalidates": "invalidated_by",
    "invalidated_by": "invalidates",
    "supports": "supports",
    "contradicts": "contradicts",
}
QUERY_REQUIRED_STRING_FIELDS = ("query_id", "query", "entity", "slot")
QUERY_NUMERIC_FIELDS = (
    "max_age_days",
    "freshness_window_days",
    "min_source_confidence",
    "required_source_confidence",
)
QUERY_COUNT_FIELDS = ("min_supporting_count", "required_supporting_count")
QUERY_PROFILE_FIELDS = ("risk_profile", "validity_profile")
QUERY_INTENTS = {
    "auto",
    "current_state",
    "historical_recall",
    "timeline_change",
    "conflict_audit",
    "validity_audit",
}
READER_PROFILES = {
    "default",
    "strong_graph_lite",
    "dim3_actionable",
    "weak_conservative",
}
SERVICE_CONFIG_FIELDS = (
    "low_confidence_threshold",
    "max_current",
    "max_supporting",
    "max_stale",
    "max_excluded",
    "max_packet_chars",
    "include_validity_edges",
    "include_weak_gate_card",
)
QUERY_STRING_OR_LIST_FIELDS = (
    "allowed_source_types",
    "required_source_types",
    "blocked_source_types",
    "excluded_source_types",
    "allowed_source_ids",
    "required_source_ids",
    "blocked_source_ids",
    "excluded_source_ids",
    "required_evidence_qualifiers",
)
QUERY_SLOT_LIST_FIELD = "coordinated_slots"
QUERY_SCOPE_RELATIONS = {"supported", "unsupported", "uncertain"}
MEMORY_EVENT_TIME_FIELDS = ("observed_at", "timestamp", "created_at")
MEMORY_EVENT_ACTION_ALIASES = {
    "invalidate": "invalidate",
    "invalidated": "invalidate",
    "memory_invalidated": "invalidate",
    "invalidate_current": "invalidate_current",
    "revoke": "revoke_current",
    "revoked": "revoke_current",
    "revoke_current": "revoke_current",
    "retraction": "invalidate_current",
    "delete": "invalidate_current",
    "forget": "invalidate_current",
}
MEMORY_EVENT_NON_ACTION_TYPES = {
    "",
    "memory_observation",
    "observation",
    "upsert",
    "write",
    "note",
    "profile_update",
    "tool_observation",
}
DEFAULT_EVENT_SOURCE_TYPE = "system_observation"
QUERY_REQUEST_TEXT_FIELDS = ("query", "text", "question", "user_query")
QUERY_REQUEST_ID_FIELDS = ("query_id", "request_id", "event_id")
MEMORY_REQUIRED_STRING_FIELDS = (
    "memory_id",
    "entity",
    "slot",
    "claim",
    "value",
    "observed_at",
)
VALIDITY_ACTIONS = {"revoke_current", "invalidate_current", "invalidate"}
ADMISSION_STATUSES = {
    "candidate",
    "admit_current",
    "admit_supporting_evidence",
    "admit_as_stale_contrast",
    "admit_validity_marker",
    "reject_duplicate_memory_id",
    "reject_low_confidence",
    "revoked_by_validity_marker",
    "admit_as_conflict_candidate",
    "admit_as_future_candidate",
}
CURRENT_STATUSES = {
    "candidate",
    "current",
    "supporting",
    "superseded",
    "revoked",
    "rejected",
    "validity_marker",
    "conflict",
    "future",
}
EVIDENCE_ROLES = {
    "current_support",
    "supporting_duplicate",
    "stale_contrast",
    "validity_marker",
    "excluded_duplicate_memory_id",
    "excluded_low_confidence",
    "conflict_candidate",
    "future_candidate",
}
EXPORTED_STATUS_TRIPLES = {
    "candidate": {("candidate", "current_support")},
    "admit_current": {("current", "current_support")},
    "admit_supporting_evidence": {("supporting", "supporting_duplicate")},
    "admit_as_stale_contrast": {("superseded", "stale_contrast")},
    "admit_validity_marker": {("validity_marker", "validity_marker")},
    "reject_duplicate_memory_id": {("rejected", "excluded_duplicate_memory_id")},
    "reject_low_confidence": {("rejected", "excluded_low_confidence")},
    "revoked_by_validity_marker": {("revoked", "stale_contrast")},
    "admit_as_conflict_candidate": {("conflict", "conflict_candidate")},
    "admit_as_future_candidate": {("future", "future_candidate")},
}
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
PACKET_REQUIRED_QUERY_FIELDS = ("query_id", "text", "entity", "slot")
PACKET_EVIDENCE_BUCKETS = (
    "current_evidence",
    "supporting_evidence",
    "stale_or_blocked_evidence",
    "excluded_memory_summary",
)
OPTIONAL_PACKET_EVIDENCE_BUCKETS = ("historical_evidence",)
WEAK_GATE_EVIDENCE_BUCKETS = (
    "current_candidate_evidence",
    "stale_or_blocked_evidence",
    "excluded_evidence",
)
RETRIEVAL_BUDGET_FIELDS = (
    "max_current",
    "max_supporting",
    "max_stale",
    "max_excluded",
)
RISK_PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "default": {
        "max_age_days": None,
        "min_source_confidence": None,
        "min_supporting_count": 0,
    },
    "current_sensitive": {
        "max_age_days": 30.0,
        "min_source_confidence": 0.65,
        "min_supporting_count": 0,
    },
    "high_stakes": {
        "max_age_days": 14.0,
        "min_source_confidence": 0.8,
        "min_supporting_count": 1,
    },
}


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def validate_step_id(step_id: Any) -> str | None:
    if step_id is None:
        return None
    if not isinstance(step_id, str) or not step_id.strip():
        raise ValueError("step_id must be a non-empty string when provided")
    return step_id.strip()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if text.startswith("["):
        loaded = json.loads(text)
        if not isinstance(loaded, list):
            raise ValueError("JSON input must be a list when using array format")
        return loaded
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("JSONL input rows must be objects")
            rows.append(value)
    return rows


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


def validate_lifecycle_step_request_payload(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("lifecycle step request must be an object")
    records = request.get("records", [])
    events = request.get("events", [])
    queries = request.get("queries", [])
    query_requests = request.get("query_requests", [])
    if not isinstance(records, list):
        raise ValueError("lifecycle step request.records must be a list")
    if not isinstance(events, list):
        raise ValueError("lifecycle step request.events must be a list")
    if not isinstance(queries, list):
        raise ValueError("lifecycle step request.queries must be a list")
    if not isinstance(query_requests, list):
        raise ValueError("lifecycle step request.query_requests must be a list")
    include_state = request.get("include_state", False)
    if not isinstance(include_state, bool):
        raise ValueError("lifecycle step request.include_state must be a boolean")
    weak_gate_outputs = validate_weak_gate_outputs_payload(
        request.get("weak_gate_outputs"),
        context="lifecycle step request.weak_gate_outputs",
        optional=True,
    )
    return {
        "step_id": validate_step_id(request.get("step_id")),
        "records": records,
        "events": events,
        "queries": queries,
        "query_requests": query_requests,
        "include_state": include_state,
        "weak_gate_outputs": weak_gate_outputs,
    }


def validate_lifecycle_step_requests_payload(requests: Any) -> list[dict[str, Any]]:
    if not isinstance(requests, list):
        raise ValueError("lifecycle step requests must be a list")
    validated_requests = [
        validate_lifecycle_step_request_payload(request)
        for request in requests
    ]
    seen_step_ids: set[str] = set()
    for request in validated_requests:
        step_id = request["step_id"]
        if step_id is None:
            continue
        if step_id in seen_step_ids:
            raise ValueError(f"Duplicate lifecycle step_id: {step_id}")
        seen_step_ids.add(step_id)
    return validated_requests


def load_lifecycle_step_request(path: Path) -> dict[str, Any]:
    return validate_lifecycle_step_request_payload(
        json.loads(path.read_text(encoding="utf-8-sig"))
    )


def load_lifecycle_step_requests(path: Path) -> list[dict[str, Any]]:
    return validate_lifecycle_step_requests_payload(load_json_or_jsonl(path))


def load_qvf_service_request(path: Path) -> dict[str, Any]:
    return validate_qvf_service_request_payload(
        json.loads(path.read_text(encoding="utf-8-sig"))
    )


def validate_qvf_service_request_payload(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("QVF service request must be an object")
    request_id = _optional_non_empty_string(
        request,
        "request_id",
        context="QVF service request",
    )
    step_id = _optional_non_empty_string(
        request,
        "step_id",
        context="QVF service request",
    ) or request_id
    state = request.get("state")
    if state is not None and not isinstance(state, dict):
        raise ValueError("QVF service request.state must be an object")
    memory_store = request.get("memory_store", [])
    if memory_store is None:
        memory_store = []
    if not isinstance(memory_store, list):
        raise ValueError("QVF service request.memory_store must be a list")
    if state is not None and memory_store:
        raise ValueError("QVF service request cannot include both state and memory_store")
    config = validate_qvf_service_config_payload(request.get("config", {}))
    if state is not None and config:
        raise ValueError("QVF service request.config cannot override embedded state")
    records = request.get("records", [])
    events = request.get("events", [])
    queries = request.get("queries", [])
    query_requests = request.get("query_requests", [])
    for field_name, value in [
        ("records", records),
        ("events", events),
        ("queries", queries),
        ("query_requests", query_requests),
    ]:
        if not isinstance(value, list):
            raise ValueError(f"QVF service request.{field_name} must be a list")
    include_state = request.get("include_state", False)
    if not isinstance(include_state, bool):
        raise ValueError("QVF service request.include_state must be a boolean")
    preview = request.get("preview", False)
    if not isinstance(preview, bool):
        raise ValueError("QVF service request.preview must be a boolean")
    weak_gate_outputs = validate_weak_gate_outputs_payload(
        request.get("weak_gate_outputs"),
        context="QVF service request.weak_gate_outputs",
        optional=True,
    )
    return {
        "request_id": request_id,
        "step_id": validate_step_id(step_id),
        "state": state,
        "memory_store": memory_store,
        "config": config,
        "records": records,
        "events": events,
        "queries": queries,
        "query_requests": query_requests,
        "weak_gate_outputs": weak_gate_outputs,
        "include_state": include_state,
        "preview": preview,
    }


def validate_qvf_service_config_payload(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError("QVF service request.config must be an object")
    unknown_fields = sorted(set(config) - set(SERVICE_CONFIG_FIELDS))
    if unknown_fields:
        raise ValueError(
            "Unknown QVF service request.config field(s): "
            + ", ".join(unknown_fields)
        )
    validated = deepcopy(config)
    if "low_confidence_threshold" in validated:
        validated["low_confidence_threshold"] = validate_low_confidence_threshold(
            validated["low_confidence_threshold"]
        )
    budget = validate_retrieval_budget(
        max_current=validated.get("max_current", 1),
        max_supporting=validated.get("max_supporting", 2),
        max_stale=validated.get("max_stale", 2),
        max_excluded=validated.get("max_excluded", 2),
    )
    for field_name, value in budget.items():
        if field_name in validated:
            validated[field_name] = value
    if "max_packet_chars" in validated:
        validated["max_packet_chars"] = validate_max_packet_chars(
            validated["max_packet_chars"]
        )
    for field_name in ["include_validity_edges", "include_weak_gate_card"]:
        if field_name in validated and not isinstance(validated[field_name], bool):
            raise ValueError(f"QVF service request.config.{field_name} must be a boolean")
    return validated


def _optional_non_empty_string(
    payload: dict[str, Any],
    field_name: str,
    *,
    context: str,
) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{field_name} must be a non-empty string")
    return value.strip()


def validate_memory_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("memory payload must be an object")
    validated = deepcopy(payload)
    memory_id = str(validated.get("memory_id", "<unknown>"))
    for field_name in MEMORY_REQUIRED_STRING_FIELDS:
        value = validated.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"memory.{field_name} must be a non-empty string")
    observed_at = _validate_iso_datetime_field(validated, "observed_at", memory_id=memory_id)
    valid_from = (
        _validate_iso_datetime_field(validated, "valid_from", memory_id=memory_id, optional=True)
        or observed_at
    )
    valid_until = _validate_iso_datetime_field(
        validated, "valid_until", memory_id=memory_id, optional=True
    )
    if valid_until is not None and valid_from > valid_until:
        raise ValueError(f"memory.valid_until must be >= valid_from for {memory_id}")

    source = validated.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"memory.source must be an object for {memory_id}")
    for field_name in ["source_id", "source_type"]:
        value = source.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"memory.source.{field_name} must be a non-empty string for {memory_id}")
    source_span = source.get("source_span")
    if source_span is not None and not isinstance(source_span, str):
        raise ValueError(f"memory.source.source_span must be a string for {memory_id}")

    source_confidence = validated.get("source_confidence")
    if isinstance(source_confidence, bool) or not isinstance(source_confidence, (int, float)):
        raise ValueError(f"memory.source_confidence must be a number in [0, 1] for {memory_id}")
    if not 0 <= float(source_confidence) <= 1:
        raise ValueError(f"memory.source_confidence must be in [0, 1] for {memory_id}")

    condition = validated.get("condition")
    if condition is not None and not isinstance(condition, str):
        raise ValueError(f"memory.condition must be a string for {memory_id}")

    _validate_memory_scope(validated, memory_id)
    _validate_validity_marker_fields(validated, memory_id)
    _validate_query_scope_evidence_fields(validated, memory_id)
    _validate_condition_activation_fields(validated, memory_id)
    validate_strict_temporal_payload(validated, memory_id=memory_id)
    validate_semantic_relation_payload(validated, memory_id=memory_id)
    return validated


def validate_memory_batch(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    return [validate_memory_payload(record) for record in records]


def load_memory_events(path: Path) -> list[dict[str, Any]]:
    return validate_memory_events_payload(load_json_or_jsonl(path))


def validate_memory_events_payload(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        raise ValueError("memory events must be a list")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"memory events[{index}] must be an object")
    return events


def normalize_memory_events(
    events: list[dict[str, Any]],
    *,
    default_source_confidence: float = LOW_CONFIDENCE_THRESHOLD,
    default_source_type: str = DEFAULT_EVENT_SOURCE_TYPE,
) -> list[dict[str, Any]]:
    return [
        normalize_memory_event_payload(
            event,
            default_source_confidence=default_source_confidence,
            default_source_type=default_source_type,
        )
        for event in validate_memory_events_payload(events)
    ]


def normalize_memory_event_payload(
    event: dict[str, Any],
    *,
    default_source_confidence: float = LOW_CONFIDENCE_THRESHOLD,
    default_source_type: str = DEFAULT_EVENT_SOURCE_TYPE,
) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("memory event must be an object")
    default_source_confidence = validate_low_confidence_threshold(
        default_source_confidence
    )
    if not isinstance(default_source_type, str) or not default_source_type.strip():
        raise ValueError("default_source_type must be a non-empty string")

    memory_id = _event_string(event, ("memory_id", "event_id"))
    if memory_id is None:
        memory_id = f"mem_event_{_stable_event_digest(event)}"

    observed_at = _event_string(event, MEMORY_EVENT_TIME_FIELDS)
    if observed_at is None:
        raise ValueError(f"memory event observed_at/timestamp/created_at is required for {memory_id}")

    record: dict[str, Any] = {
        "memory_id": memory_id,
        "entity": _required_event_string(event, "entity", memory_id),
        "slot": _required_event_string(event, "slot", memory_id),
        "value": _required_event_string(event, "value", memory_id),
        "observed_at": observed_at,
        "valid_from": _event_string(event, ("valid_from",)) or observed_at,
        "valid_until": _event_string(event, ("valid_until",)),
        "condition": _event_string(event, ("condition", "validity_condition")),
        "source": _event_source(event, memory_id, default_source_type),
        "source_confidence": _event_source_confidence(
            event,
            default_source_confidence,
        ),
    }
    record["claim"] = (
        _event_string(event, ("claim", "text", "content"))
        or f"{record['entity']} {record['slot']} is {record['value']}."
    )
    scope = _event_scope(event)
    if scope:
        record["scope"] = scope

    explicit_action = _event_string(event, ("validity_action",))
    if explicit_action is not None:
        record["validity_action"] = explicit_action
    else:
        mapped_action = _map_memory_event_action(
            _event_string(event, ("event_type", "action", "type"))
        )
        if mapped_action is not None:
            record["validity_action"] = mapped_action

    invalidates = _event_invalidates_memory_ids(event)
    if invalidates is not None:
        record["invalidates_memory_ids"] = invalidates

    return validate_memory_payload(record)


def build_memory_event_adapter_summary(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_memory_events_payload(events)
    validate_memory_batch(records)
    generated_ids = [
        record["memory_id"]
        for event, record in zip(events, records)
        if _event_string(event, ("memory_id", "event_id")) is None
    ]
    action_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    for record in records:
        action = str(record.get("validity_action") or "memory_observation")
        action_counts[action] = action_counts.get(action, 0) + 1
        source_type = str(record.get("source", {}).get("source_type", ""))
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        scope = record.get("scope", {}) or {}
        scope_key = "::".join(
            [
                norm(str(scope.get("namespace", ""))),
                norm(str(scope.get("tenant_id", ""))),
                norm(str(scope.get("user_id", ""))),
            ]
        )
        scope_counts[scope_key] = scope_counts.get(scope_key, 0) + 1
    return {
        "decision": "GO_QVF_MEMORY_EVENT_ADAPTER_READY_NO_API",
        "execution_mode": "memory_event_adapter",
        "event_count": len(events),
        "normalized_record_count": len(records),
        "input_event_ids": [
            _event_string(event, ("event_id", "memory_id")) for event in events
        ],
        "output_memory_ids": [record["memory_id"] for record in records],
        "generated_memory_id_count": len(generated_ids),
        "generated_memory_ids": generated_ids,
        "validity_action_counts": dict(sorted(action_counts.items())),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "api_calls_made": 0,
        "claim_boundary": [
            "This adapter normalizes already-structured memory events; it does not extract facts from raw text.",
            "It is write-time integration plumbing for QVF validity-admission admission, not model-accuracy evidence.",
        ],
    }


def attach_event_adapter_summary(
    summary: dict[str, Any],
    event_adapter_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    if event_adapter_summary is not None:
        summary["event_adapter_summary"] = event_adapter_summary
    return summary


def load_query_requests(path: Path) -> list[dict[str, Any]]:
    return validate_query_requests_payload(load_json_or_jsonl(path))


def validate_query_requests_payload(requests: Any) -> list[dict[str, Any]]:
    if not isinstance(requests, list):
        raise ValueError("query requests must be a list")
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            raise ValueError(f"query requests[{index}] must be an object")
    return requests


def normalize_query_requests(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        normalize_query_request_payload(request)
        for request in validate_query_requests_payload(requests)
    ]


def normalize_query_request_payload(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("query request must be an object")
    query_id = _query_request_string(request, QUERY_REQUEST_ID_FIELDS)
    if query_id is None:
        query_id = f"q_request_{_stable_event_digest(request)}"
    query_text = _query_request_string(request, QUERY_REQUEST_TEXT_FIELDS)
    if query_text is None:
        raise ValueError(f"query request text/query/question is required for {query_id}")
    query = {
        "query_id": query_id,
        "query": query_text,
        "entity": _required_query_request_string(request, "entity", query_id),
        "slot": _required_query_request_string(request, "slot", query_id),
        "needs_current": _query_request_bool(request, "needs_current", True),
    }
    for source_field, target_field in [
        ("as_of", "as_of"),
        ("timestamp", "as_of"),
        ("condition", "condition"),
        ("required_condition", "required_condition"),
        ("query_intent", "query_intent"),
        ("memory_query_intent", "query_intent"),
        ("embedded_premise_value", "embedded_premise_value"),
        ("premise_value", "embedded_premise_value"),
        ("risk_profile", "risk_profile"),
        ("validity_profile", "validity_profile"),
        ("reader_profile", "reader_profile"),
    ]:
        value = _query_request_string(request, (source_field,))
        if value is not None and target_field not in query:
            query[target_field] = value
    _copy_optional_query_number(request, query, "max_age_days")
    _copy_optional_query_number(request, query, "freshness_window_days")
    _copy_optional_query_number(request, query, "min_source_confidence")
    _copy_optional_query_number(request, query, "required_source_confidence")
    _copy_optional_query_int(request, query, "min_supporting_count")
    _copy_optional_query_int(request, query, "required_supporting_count")
    for field_name in QUERY_STRING_OR_LIST_FIELDS:
        if field_name in request:
            query[field_name] = _query_request_string_or_list(request, field_name)
    if QUERY_SLOT_LIST_FIELD in request:
        coordinated_slots = _query_request_string_or_list(
            request,
            QUERY_SLOT_LIST_FIELD,
        )
        query[QUERY_SLOT_LIST_FIELD] = (
            [coordinated_slots]
            if isinstance(coordinated_slots, str)
            else coordinated_slots
        )
    scope = _query_request_scope(request)
    if scope:
        query["scope"] = scope
    return validate_query_payload(query)


def build_query_request_adapter_summary(
    requests: list[dict[str, Any]],
    queries: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_query_requests_payload(requests)
    validate_query_batch(queries)
    generated_ids = [
        query["query_id"]
        for request, query in zip(requests, queries)
        if _query_request_string(request, QUERY_REQUEST_ID_FIELDS) is None
    ]
    risk_profile_counts: dict[str, int] = {}
    premise_count = 0
    source_policy_request_count = 0
    evidence_qualifier_request_count = 0
    for query in queries:
        profile = str(query.get("risk_profile") or query.get("validity_profile") or "default")
        risk_profile_counts[profile] = risk_profile_counts.get(profile, 0) + 1
        if query.get("embedded_premise_value"):
            premise_count += 1
        if any(
            query.get(field_name) is not None
            for field_name in QUERY_STRING_OR_LIST_FIELDS
            if field_name != "required_evidence_qualifiers"
        ):
            source_policy_request_count += 1
        if query.get("required_evidence_qualifiers"):
            evidence_qualifier_request_count += 1
    return {
        "decision": "GO_QVF_QUERY_REQUEST_ADAPTER_READY_NO_API",
        "execution_mode": "query_request_adapter",
        "request_count": len(requests),
        "normalized_query_count": len(queries),
        "input_request_ids": [
            _query_request_string(request, QUERY_REQUEST_ID_FIELDS)
            for request in requests
        ],
        "output_query_ids": [query["query_id"] for query in queries],
        "generated_query_id_count": len(generated_ids),
        "generated_query_ids": generated_ids,
        "embedded_premise_request_count": premise_count,
        "source_policy_request_count": source_policy_request_count,
        "evidence_qualifier_request_count": evidence_qualifier_request_count,
        "risk_profile_counts": dict(sorted(risk_profile_counts.items())),
        "api_calls_made": 0,
        "claim_boundary": [
            "This adapter normalizes already-structured read requests; it does not infer entity/slot from raw text.",
            "It is read-time integration plumbing for QVF packet/routing, not model-accuracy evidence.",
        ],
    }


def attach_query_request_adapter_summary(
    summary: dict[str, Any],
    query_request_adapter_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    if query_request_adapter_summary is not None:
        summary["query_request_adapter_summary"] = query_request_adapter_summary
    return summary


def load_cli_queries(
    query_path: Path,
    query_request_queries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if query_request_queries and query_path == QUERIES_PATH:
        return []
    return load_jsonl(query_path)


def _query_request_string(
    request: dict[str, Any], field_names: tuple[str, ...]
) -> str | None:
    for field_name in field_names:
        value = request.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"query request.{field_name} must be a string")
        if value.strip():
            return value.strip()
    return None


def _required_query_request_string(
    request: dict[str, Any], field_name: str, query_id: str
) -> str:
    value = _query_request_string(request, (field_name,))
    if value is None:
        raise ValueError(f"query request.{field_name} is required for {query_id}")
    return value


def _copy_optional_query_number(
    request: dict[str, Any],
    query: dict[str, Any],
    field_name: str,
) -> None:
    if field_name not in request or request[field_name] is None:
        return
    value = request[field_name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"query request.{field_name} must be a non-negative number")
    query[field_name] = value


def _query_request_bool(
    request: dict[str, Any],
    field_name: str,
    default: bool,
) -> bool:
    if field_name not in request or request[field_name] is None:
        return default
    value = request[field_name]
    if not isinstance(value, bool):
        raise ValueError(f"query request.{field_name} must be a boolean")
    return value


def _copy_optional_query_int(
    request: dict[str, Any],
    query: dict[str, Any],
    field_name: str,
) -> None:
    if field_name not in request or request[field_name] is None:
        return
    value = request[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"query request.{field_name} must be a non-negative integer")
    query[field_name] = value


def _query_request_string_or_list(
    request: dict[str, Any], field_name: str
) -> str | list[str]:
    value = request[field_name]
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"query request.{field_name} must be non-empty")
        return value
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"query request.{field_name} must contain non-empty strings")
        return value
    raise ValueError(f"query request.{field_name} must be a string or list of strings")


def _query_request_scope(request: dict[str, Any]) -> dict[str, str]:
    raw_scope = request.get("scope", {}) or {}
    if not isinstance(raw_scope, dict):
        raise ValueError("query request.scope must be an object")
    scope = {
        "namespace": str(raw_scope.get("namespace") or request.get("namespace") or ""),
        "tenant_id": str(raw_scope.get("tenant_id") or request.get("tenant_id") or ""),
        "user_id": str(raw_scope.get("user_id") or request.get("user_id") or ""),
    }
    return {key: value for key, value in scope.items() if value}


def _stable_event_digest(event: dict[str, Any]) -> str:
    blob = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _event_string(event: dict[str, Any], field_names: tuple[str, ...]) -> str | None:
    for field_name in field_names:
        value = event.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"memory event.{field_name} must be a string")
        if value.strip():
            return value.strip()
    return None


def _required_event_string(event: dict[str, Any], field_name: str, memory_id: str) -> str:
    value = _event_string(event, (field_name,))
    if value is None:
        raise ValueError(f"memory event.{field_name} is required for {memory_id}")
    return value


def _event_source(
    event: dict[str, Any],
    memory_id: str,
    default_source_type: str,
) -> dict[str, str]:
    raw_source = event.get("source", {}) or {}
    if not isinstance(raw_source, dict):
        raise ValueError(f"memory event.source must be an object for {memory_id}")
    source_id = (
        _event_string(raw_source, ("source_id",))
        or _event_string(event, ("source_id", "event_id"))
        or memory_id
    )
    source_type = (
        _event_string(raw_source, ("source_type",))
        or _event_string(event, ("source_type",))
        or default_source_type.strip()
    )
    source: dict[str, str] = {
        "source_id": source_id,
        "source_type": source_type,
    }
    source_span = (
        _event_string(raw_source, ("source_span",))
        or _event_string(event, ("source_span", "text", "content"))
    )
    if source_span is not None:
        source["source_span"] = source_span
    return source


def _event_source_confidence(
    event: dict[str, Any],
    default_source_confidence: float,
) -> float:
    value = event.get("source_confidence")
    if value is None:
        value = event.get("confidence")
    if value is None:
        return float(default_source_confidence)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("memory event.source_confidence/confidence must be a number in [0, 1]")
    confidence = float(value)
    if not 0 <= confidence <= 1:
        raise ValueError("memory event.source_confidence/confidence must be in [0, 1]")
    return confidence


def _event_scope(event: dict[str, Any]) -> dict[str, str]:
    raw_scope = event.get("scope", {}) or {}
    if not isinstance(raw_scope, dict):
        raise ValueError("memory event.scope must be an object")
    scope = {
        "namespace": str(raw_scope.get("namespace") or event.get("namespace") or ""),
        "tenant_id": str(raw_scope.get("tenant_id") or event.get("tenant_id") or ""),
        "user_id": str(raw_scope.get("user_id") or event.get("user_id") or ""),
    }
    return {key: value for key, value in scope.items() if value}


def _map_memory_event_action(raw_action: str | None) -> str | None:
    if raw_action is None:
        return None
    normalized = norm(raw_action)
    if normalized in MEMORY_EVENT_NON_ACTION_TYPES:
        return None
    return MEMORY_EVENT_ACTION_ALIASES.get(normalized)


def _event_invalidates_memory_ids(event: dict[str, Any]) -> list[str] | None:
    if "invalidates_memory_ids" in event:
        value = event["invalidates_memory_ids"]
    elif "invalidates" in event:
        value = event["invalidates"]
    elif "target_memory_ids" in event:
        value = event["target_memory_ids"]
    elif "target_memory_id" in event:
        value = event["target_memory_id"]
    else:
        return None
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ValueError("memory event invalidation targets must be a string or list")
    return value


def validate_low_confidence_threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("low_confidence_threshold must be a number in [0, 1]")
    threshold = float(value)
    if not 0 <= threshold <= 1:
        raise ValueError("low_confidence_threshold must be in [0, 1]")
    return threshold


def _validate_iso_datetime_field(
    payload: dict[str, Any],
    field_name: str,
    *,
    memory_id: str,
    optional: bool = False,
) -> datetime | None:
    value = payload.get(field_name)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"memory.{field_name} must be an ISO date-time string for {memory_id}")
    try:
        parsed = parse_dt(value)
    except ValueError as exc:
        raise ValueError(f"memory.{field_name} must be an ISO date-time string for {memory_id}") from exc
    if parsed is None:
        raise ValueError(f"memory.{field_name} must be an ISO date-time string for {memory_id}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"memory.{field_name} must include a timezone for {memory_id}")
    return parsed


def _validate_memory_scope(payload: dict[str, Any], memory_id: str) -> None:
    scope = payload.get("scope")
    if scope is not None and not isinstance(scope, dict):
        raise ValueError(f"memory.scope must be an object for {memory_id}")
    if isinstance(scope, dict):
        for field_name in ["namespace", "tenant_id", "user_id"]:
            value = scope.get(field_name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"memory.scope.{field_name} must be a string for {memory_id}")
    for field_name in ["namespace", "tenant_id", "user_id"]:
        value = payload.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"memory.{field_name} must be a string for {memory_id}")


def _validate_validity_marker_fields(payload: dict[str, Any], memory_id: str) -> None:
    validity_action = payload.get("validity_action")
    if validity_action is not None:
        if not isinstance(validity_action, str) or not validity_action.strip():
            raise ValueError(f"memory.validity_action must be a non-empty string for {memory_id}")
        if norm(validity_action) not in VALIDITY_ACTIONS:
            known = ", ".join(sorted(VALIDITY_ACTIONS))
            raise ValueError(f"memory.validity_action must be one of: {known}")
    target_ids = payload.get("invalidates_memory_ids")
    if target_ids is not None:
        if not isinstance(target_ids, list):
            raise ValueError(f"memory.invalidates_memory_ids must be a list for {memory_id}")
        normalized_target_ids: list[str] = []
        seen_target_ids: set[str] = set()
        for target_id in target_ids:
            if not isinstance(target_id, str) or not target_id.strip():
                raise ValueError(
                    f"memory.invalidates_memory_ids must contain non-empty strings for {memory_id}"
                )
            normalized_target_id = target_id.strip()
            if normalized_target_id == memory_id.strip():
                raise ValueError(
                    f"memory.invalidates_memory_ids must not contain self-reference for {memory_id}"
                )
            if normalized_target_id in seen_target_ids:
                raise ValueError(
                    "memory.invalidates_memory_ids contains duplicate target "
                    f"{normalized_target_id} for {memory_id}"
                )
            seen_target_ids.add(normalized_target_id)
            normalized_target_ids.append(normalized_target_id)
        payload["invalidates_memory_ids"] = normalized_target_ids
    mismatch_count = payload.get("invalidates_scope_mismatch_count")
    if mismatch_count is not None:
        if isinstance(mismatch_count, bool) or not isinstance(mismatch_count, int):
            raise ValueError(f"memory.invalidates_scope_mismatch_count must be an integer for {memory_id}")
        if mismatch_count < 0:
            raise ValueError(f"memory.invalidates_scope_mismatch_count must be >= 0 for {memory_id}")


def _validate_query_scope_evidence_fields(
    payload: dict[str, Any], memory_id: str
) -> None:
    relation = payload.get("query_scope_relation")
    if relation is not None:
        if not isinstance(relation, str) or not relation.strip():
            raise ValueError(
                f"memory.query_scope_relation must be a non-empty string for {memory_id}"
            )
        normalized_relation = norm(relation)
        if normalized_relation not in QUERY_SCOPE_RELATIONS:
            known = ", ".join(sorted(QUERY_SCOPE_RELATIONS))
            raise ValueError(
                f"memory.query_scope_relation must be one of: {known} for {memory_id}"
            )
        payload["query_scope_relation"] = normalized_relation

    qualifiers = payload.get("supported_query_qualifiers")
    if qualifiers is None:
        return
    if not isinstance(qualifiers, list):
        raise ValueError(
            f"memory.supported_query_qualifiers must be a list for {memory_id}"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for qualifier in qualifiers:
        if not isinstance(qualifier, str) or not qualifier.strip():
            raise ValueError(
                "memory.supported_query_qualifiers must contain non-empty strings "
                f"for {memory_id}"
            )
        cleaned = norm(qualifier)
        if cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    payload["supported_query_qualifiers"] = normalized


def _validate_condition_activation_fields(
    payload: dict[str, Any], memory_id: str
) -> None:
    activation = payload.get("condition_activation")
    operation = norm(str(payload.get("operation", "")))
    if activation is None:
        if operation == "activate_condition":
            raise ValueError(
                f"memory.condition_activation is required for activate_condition operation: {memory_id}"
            )
        return
    if operation != "activate_condition":
        raise ValueError(
            f"memory.operation must be activate_condition when condition_activation is present: {memory_id}"
        )
    if not isinstance(activation, dict):
        raise ValueError(f"memory.condition_activation must be an object for {memory_id}")
    for field_name in ["trigger_slot", "dependent_slot"]:
        value = activation.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"memory.condition_activation.{field_name} must be a non-empty string for {memory_id}"
            )
    depth = activation.get("activation_depth")
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError(
            f"memory.condition_activation.activation_depth must be an integer >= 1 for {memory_id}"
        )
    for field_name in [
        "rule_source_turn_ids",
        "root_trigger_source_turn_ids",
        "parent_trigger_source_turn_ids",
        "activation_path",
    ]:
        values = activation.get(field_name)
        if not isinstance(values, list) or not values:
            raise ValueError(
                f"memory.condition_activation.{field_name} must be a non-empty list for {memory_id}"
            )
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(
                f"memory.condition_activation.{field_name} must contain non-empty strings for {memory_id}"
            )
    template_id = activation.get("condition_template_memory_id")
    if template_id is not None and (
        not isinstance(template_id, str) or not template_id.strip()
    ):
        raise ValueError(
            "memory.condition_activation.condition_template_memory_id must be a "
            f"non-empty string when present for {memory_id}"
        )


def _validate_exported_link_targets(
    raw_targets: Any, *, edge_type: str, memory_id: str
) -> list[str]:
    if not isinstance(raw_targets, list):
        raise ValueError(f"links.{edge_type} must be a list for {memory_id}")
    normalized_targets: list[str] = []
    seen_targets: set[str] = set()
    for target_id in raw_targets:
        if not isinstance(target_id, str) or not target_id.strip():
            raise ValueError(
                f"links.{edge_type} must contain non-empty string memory ids "
                f"for {memory_id}"
            )
        normalized_target_id = target_id.strip()
        if normalized_target_id == memory_id.strip():
            raise ValueError(
                f"links.{edge_type} must not contain self-links for {memory_id}"
            )
        if normalized_target_id in seen_targets:
            raise ValueError(
                f"links.{edge_type} contains duplicate target "
                f"{normalized_target_id} for {memory_id}"
            )
        seen_targets.add(normalized_target_id)
        normalized_targets.append(normalized_target_id)
    return normalized_targets


def validate_query_payload(query: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(query, dict):
        raise ValueError("query must be an object")
    validated = deepcopy(query)
    for field_name in QUERY_REQUIRED_STRING_FIELDS:
        value = validated.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"query.{field_name} must be a non-empty string")
    if validated.get("as_of") is not None:
        try:
            as_of = parse_dt(str(validated["as_of"]))
        except ValueError as exc:
            raise ValueError("query.as_of must be an ISO date-time string") from exc
        if as_of is None or as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("query.as_of must include a timezone")
    for field_name in QUERY_NUMERIC_FIELDS:
        _validate_query_non_negative_number(validated, field_name)
    for field_name in ["min_source_confidence", "required_source_confidence"]:
        value = validated.get(field_name)
        if value is not None and not 0 <= float(value) <= 1:
            raise ValueError(f"query.{field_name} must be in [0, 1]")
    for field_name in QUERY_COUNT_FIELDS:
        _validate_query_non_negative_int(validated, field_name)
    scope = validated.get("scope")
    if scope is not None and not isinstance(scope, dict):
        raise ValueError("query.scope must be an object")
    if isinstance(scope, dict):
        for field_name in ["namespace", "tenant_id", "user_id"]:
            value = scope.get(field_name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"query.scope.{field_name} must be a string")
    for field_name in ["namespace", "tenant_id", "user_id"]:
        value = validated.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"query.{field_name} must be a string")
    for field_name in QUERY_STRING_OR_LIST_FIELDS:
        _validate_query_string_or_list(validated, field_name)
    _validate_query_coordinated_slots(validated)
    for field_name in ["condition", "required_condition", "embedded_premise_value"]:
        value = validated.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"query.{field_name} must be a string")
    _validate_query_intent(validated)
    requested_dimensions = normalize_requested_response_dimensions(
        validated.get("requested_response_dimensions")
    )
    response_dimension_state = validate_response_dimension_state(
        validated.get("response_dimension_state"),
        requested_response_dimensions=requested_dimensions,
        query_text=validated.get("query"),
    )
    if requested_dimensions:
        validated["requested_response_dimensions"] = requested_dimensions
        validated["response_dimension_state"] = response_dimension_state
    _validate_query_profile_fields(validated)
    _validate_query_reader_profile(validated)
    return validated


def _validate_query_intent(query: dict[str, Any]) -> None:
    value = query.get("query_intent") or query.get("memory_query_intent")
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError("query.query_intent must be a non-empty string")
    normalized_intent = norm(value)
    aliases = {
        "historical": "historical_recall",
        "history": "historical_recall",
        "past": "historical_recall",
        "archive": "historical_recall",
        "archival": "historical_recall",
        "timeline": "timeline_change",
        "change": "timeline_change",
        "changes": "timeline_change",
        "current": "current_state",
        "now": "current_state",
        "latest": "current_state",
        "conflict": "conflict_audit",
        "audit": "validity_audit",
        "validity": "validity_audit",
    }
    normalized_intent = aliases.get(normalized_intent, normalized_intent)
    if normalized_intent not in QUERY_INTENTS:
        known = ", ".join(sorted(QUERY_INTENTS))
        raise ValueError(
            f"Unknown query.query_intent {normalized_intent!r}; expected one of: {known}"
        )
    query["query_intent"] = normalized_intent


def _validate_query_profile_fields(query: dict[str, Any]) -> None:
    normalized_profiles: dict[str, str] = {}
    for field_name in QUERY_PROFILE_FIELDS:
        value = query.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"query.{field_name} must be a non-empty string")
        normalized_profile = norm(value)
        if normalized_profile not in RISK_PROFILE_DEFAULTS:
            known = ", ".join(sorted(RISK_PROFILE_DEFAULTS))
            raise ValueError(
                f"Unknown query.{field_name} {normalized_profile!r}; expected one of: {known}"
            )
        query[field_name] = normalized_profile
        normalized_profiles[field_name] = normalized_profile
    if (
        normalized_profiles.get("risk_profile") is not None
        and normalized_profiles.get("validity_profile") is not None
        and normalized_profiles["risk_profile"] != normalized_profiles["validity_profile"]
    ):
        raise ValueError("query.risk_profile and query.validity_profile must match when both are set")


def _validate_query_reader_profile(query: dict[str, Any]) -> None:
    value = query.get("reader_profile")
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError("query.reader_profile must be a non-empty string")
    normalized_profile = norm(value)
    aliases = {
        "graph_lite": "strong_graph_lite",
        "strong": "strong_graph_lite",
        "dim3": "dim3_actionable",
        "dim3-actionable": "dim3_actionable",
        "actionable": "dim3_actionable",
        "weak": "weak_conservative",
        "weak-model": "weak_conservative",
        "weak_model": "weak_conservative",
    }
    normalized_profile = aliases.get(normalized_profile, normalized_profile)
    if normalized_profile not in READER_PROFILES:
        known = ", ".join(sorted(READER_PROFILES))
        raise ValueError(
            f"Unknown query.reader_profile {normalized_profile!r}; expected one of: {known}"
        )
    query["reader_profile"] = normalized_profile


def validate_query_batch(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(queries, list):
        raise ValueError("queries must be a list")
    validated_queries = [validate_query_payload(query) for query in queries]
    seen_query_ids: set[str] = set()
    duplicate_query_ids: set[str] = set()
    for query in validated_queries:
        query_id = query["query_id"]
        if query_id in seen_query_ids:
            duplicate_query_ids.add(query_id)
        seen_query_ids.add(query_id)
    if duplicate_query_ids:
        duplicates = ", ".join(sorted(duplicate_query_ids))
        raise ValueError(f"Duplicate query_id in query batch: {duplicates}")
    return validated_queries


def _validate_query_non_negative_number(
    query: dict[str, Any], field_name: str
) -> None:
    value = query.get(field_name)
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"query.{field_name} must be a non-negative number")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"query.{field_name} must be a non-negative number") from exc
    if numeric_value < 0:
        raise ValueError(f"query.{field_name} must be >= 0")


def _validate_query_non_negative_int(query: dict[str, Any], field_name: str) -> None:
    value = query.get(field_name)
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"query.{field_name} must be a non-negative integer")
    try:
        numeric_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"query.{field_name} must be a non-negative integer") from exc
    if float(value) != numeric_value:
        raise ValueError(f"query.{field_name} must be a non-negative integer")
    if numeric_value < 0:
        raise ValueError(f"query.{field_name} must be >= 0")


def _validate_query_string_or_list(query: dict[str, Any], field_name: str) -> None:
    value = query.get(field_name)
    if value is None:
        return
    values = value if isinstance(value, list) else [value]
    if not isinstance(values, list):
        raise ValueError(f"query.{field_name} must be a string or list of strings")
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"query.{field_name} must contain non-empty strings")


def _validate_query_coordinated_slots(query: dict[str, Any]) -> None:
    value = query.get(QUERY_SLOT_LIST_FIELD)
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError(f"query.{QUERY_SLOT_LIST_FIELD} must be a list of strings")
    primary_slot = norm(str(query.get("slot") or ""))
    normalized: list[str] = []
    seen: set[str] = {primary_slot}
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"query.{QUERY_SLOT_LIST_FIELD} must contain non-empty strings"
            )
        stripped = item.strip()
        normalized_item = norm(stripped)
        if normalized_item in seen:
            continue
        seen.add(normalized_item)
        normalized.append(stripped)
    query[QUERY_SLOT_LIST_FIELD] = normalized


def _validate_exported_status_field(
    value: Any, *, field_name: str, memory_id: str, allowed_values: set[str]
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"exported memory.{field_name} must be a non-empty string for {memory_id}"
        )
    normalized_value = value.strip()
    if normalized_value not in allowed_values:
        known = ", ".join(sorted(allowed_values))
        raise ValueError(
            f"exported memory.{field_name} must be one of: {known} for {memory_id}"
        )
    return normalized_value


def _validate_exported_status_triple(
    *,
    admission_status: str,
    current_status: str,
    evidence_role: str,
    memory_id: str,
) -> None:
    allowed_pairs = EXPORTED_STATUS_TRIPLES[admission_status]
    if (current_status, evidence_role) not in allowed_pairs:
        readable_pairs = ", ".join(
            f"{current}/{role}" for current, role in sorted(allowed_pairs)
        )
        raise ValueError(
            "exported memory status fields are inconsistent for "
            f"{memory_id}: admission_status={admission_status} requires "
            f"current_status/evidence_role in {readable_pairs}"
        )


@dataclass
class MemoryRecord:
    payload: dict[str, Any]
    admission_status: str = "candidate"
    current_status: str = "candidate"
    evidence_role: str = "current_support"
    links: dict[str, list[str]] = field(
        default_factory=lambda: {edge_type: [] for edge_type in LINK_EDGE_TYPES}
    )
    admission_reason: str = ""

    @classmethod
    def from_public_dict(cls, row: dict[str, Any]) -> "MemoryRecord":
        payload = deepcopy(row)
        memory_id = str(payload.get("memory_id", "<unknown>"))
        admission_status = _validate_exported_status_field(
            payload.pop("admission_status", "candidate"),
            field_name="admission_status",
            memory_id=memory_id,
            allowed_values=ADMISSION_STATUSES,
        )
        current_status = _validate_exported_status_field(
            payload.pop("current_status", "candidate"),
            field_name="current_status",
            memory_id=memory_id,
            allowed_values=CURRENT_STATUSES,
        )
        evidence_role = _validate_exported_status_field(
            payload.pop("evidence_role", "current_support"),
            field_name="evidence_role",
            memory_id=memory_id,
            allowed_values=EVIDENCE_ROLES,
        )
        _validate_exported_status_triple(
            admission_status=admission_status,
            current_status=current_status,
            evidence_role=evidence_role,
            memory_id=memory_id,
        )
        links = payload.pop("links", None)
        if links is None:
            links = {}
        if not isinstance(links, dict):
            raise ValueError(f"links must be an object for {memory_id}")
        unknown_edges = sorted(set(links) - set(LINK_EDGE_TYPES))
        if unknown_edges:
            raise ValueError(
                "Unknown link edge type in exported records for "
                f"{memory_id}: {', '.join(unknown_edges)}"
            )
        audit = payload.pop("audit", None) or {}
        payload = validate_memory_payload(payload)
        normalized_links: dict[str, list[str]] = {}
        for edge_type in LINK_EDGE_TYPES:
            normalized_links[edge_type] = _validate_exported_link_targets(
                links.get(edge_type, []),
                edge_type=edge_type,
                memory_id=memory_id,
            )
        return cls(
            payload=payload,
            admission_status=admission_status,
            current_status=current_status,
            evidence_role=evidence_role,
            links=normalized_links,
            admission_reason=str(audit.get("admission_reason", "")),
        )

    @property
    def memory_id(self) -> str:
        return self.payload["memory_id"]

    @property
    def entity(self) -> str:
        return self.payload["entity"]

    @property
    def slot(self) -> str:
        return self.payload["slot"]

    @property
    def value(self) -> str:
        return self.payload["value"]

    @property
    def observed_at(self) -> datetime:
        parsed = parse_dt(self.payload["observed_at"])
        if parsed is None:
            raise ValueError(f"Missing observed_at for {self.memory_id}")
        return parsed

    @property
    def valid_from(self) -> datetime:
        parsed = parse_dt(self.payload.get("valid_from") or self.payload["observed_at"])
        if parsed is None:
            raise ValueError(f"Missing valid_from/observed_at for {self.memory_id}")
        return parsed

    @property
    def valid_until(self) -> datetime | None:
        return parse_dt(self.payload.get("valid_until"))

    @property
    def source_confidence(self) -> float:
        return float(self.payload["source_confidence"])

    @property
    def source_id(self) -> str:
        return str(self.payload.get("source", {}).get("source_id", ""))

    @property
    def source_type(self) -> str:
        return str(self.payload.get("source", {}).get("source_type", ""))

    @property
    def scope(self) -> dict[str, str]:
        raw_scope = self.payload.get("scope", {}) or {}
        return {
            "namespace": str(raw_scope.get("namespace") or self.payload.get("namespace") or ""),
            "tenant_id": str(raw_scope.get("tenant_id") or self.payload.get("tenant_id") or ""),
            "user_id": str(raw_scope.get("user_id") or self.payload.get("user_id") or ""),
        }

    @property
    def key(self) -> tuple[str, str]:
        return norm(self.entity), norm(self.slot)

    @property
    def scoped_key(self) -> tuple[str, str, str, str, str]:
        scope = self.scope
        return (
            norm(scope["namespace"]),
            norm(scope["tenant_id"]),
            norm(scope["user_id"]),
            self.key[0],
            self.key[1],
        )

    def to_public_dict(self) -> dict[str, Any]:
        out = deepcopy(self.payload)
        out["admission_status"] = self.admission_status
        out["current_status"] = self.current_status
        out["evidence_role"] = self.evidence_role
        out["links"] = deepcopy(self.links)
        out["audit"] = {
            "policy_version": POLICY_VERSION,
            "admission_reason": self.admission_reason,
            "normalized_key": f"{self.key[0]}::{self.key[1]}",
            "normalized_scoped_key": "::".join(self.scoped_key),
        }
        return out


class ValidityAwareMemoryStore:
    def __init__(
        self, low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD
    ) -> None:
        self.low_confidence_threshold = validate_low_confidence_threshold(
            low_confidence_threshold
        )
        self.records: dict[str, MemoryRecord] = {}
        self.current_by_key: dict[tuple[str, str, str, str, str], str] = {}
        self.admission_log: list[dict[str, Any]] = []

    @classmethod
    def from_exported_records(
        cls,
        rows: list[dict[str, Any]],
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    ) -> "ValidityAwareMemoryStore":
        store = cls(low_confidence_threshold=low_confidence_threshold)
        for row in rows:
            record = MemoryRecord.from_public_dict(row)
            if record.memory_id in store.records:
                raise ValueError(f"Duplicate memory_id in exported records: {record.memory_id}")
            store.records[record.memory_id] = record
        store._validate_link_targets()
        store._validate_reciprocal_links()

        for record in store.records.values():
            if record.current_status != "current":
                continue
            existing_id = store.current_by_key.get(record.scoped_key)
            if existing_id is None:
                store.current_by_key[record.scoped_key] = record.memory_id
                continue
            normalized_key = "::".join(record.scoped_key)
            raise ValueError(
                "Multiple current records for scoped key "
                f"{normalized_key}: {existing_id}, {record.memory_id}"
            )
        store.validate_integrity()
        return store

    def validate_integrity(self) -> dict[str, int]:
        self._validate_link_targets()
        self._validate_reciprocal_links()

        current_records_by_key: dict[tuple[str, str, str, str, str], str] = {}
        link_edge_count = 0
        for record in self.records.values():
            link_edge_count += sum(len(targets) for targets in record.links.values())
            if record.current_status != "current":
                continue
            existing_id = current_records_by_key.get(record.scoped_key)
            if existing_id is not None and existing_id != record.memory_id:
                normalized_key = "::".join(record.scoped_key)
                raise ValueError(
                    "Multiple current records for scoped key "
                    f"{normalized_key}: {existing_id}, {record.memory_id}"
                )
            current_records_by_key[record.scoped_key] = record.memory_id
            indexed_id = self.current_by_key.get(record.scoped_key)
            if indexed_id != record.memory_id:
                normalized_key = "::".join(record.scoped_key)
                raise ValueError(
                    "Current memory missing from current_by_key for scoped key "
                    f"{normalized_key}: expected {record.memory_id}, found {indexed_id}"
                )

        for scoped_key, memory_id in self.current_by_key.items():
            record = self.records.get(memory_id)
            normalized_key = "::".join(scoped_key)
            if record is None:
                raise ValueError(
                    "current_by_key points to missing memory for scoped key "
                    f"{normalized_key}: {memory_id}"
                )
            if record.scoped_key != scoped_key:
                raise ValueError(
                    "current_by_key scoped key mismatch for "
                    f"{memory_id}: indexed {normalized_key}, actual {'::'.join(record.scoped_key)}"
                )
            if record.current_status != "current":
                raise ValueError(
                    "current_by_key points to non-current memory "
                    f"{memory_id}: current_status={record.current_status}"
                )

        return {
            "records": len(self.records),
            "current_index_entries": len(self.current_by_key),
            "current_records": len(current_records_by_key),
            "link_edges": link_edge_count,
        }

    def _validate_link_targets(self) -> None:
        for record in self.records.values():
            for edge_type, targets in record.links.items():
                for target_id in targets:
                    if target_id not in self.records:
                        raise ValueError(
                            "Dangling link target in exported records: "
                            f"{record.memory_id}.{edge_type} -> {target_id}"
                        )

    def _validate_reciprocal_links(self) -> None:
        for record in self.records.values():
            for edge_type, reciprocal_type in RECIPROCAL_LINK_EDGE_TYPES.items():
                for target_id in record.links.get(edge_type, []):
                    target = self.records[target_id]
                    if record.memory_id not in target.links.get(reciprocal_type, []):
                        raise ValueError(
                            "Non-reciprocal link in exported records: "
                            f"{record.memory_id}.{edge_type} -> {target_id} "
                            f"requires {target_id}.{reciprocal_type} -> {record.memory_id}"
                        )

    def admit(self, candidate_payload: dict[str, Any]) -> MemoryRecord:
        record = MemoryRecord(payload=validate_memory_payload(candidate_payload))

        if record.memory_id in self.records:
            record.admission_status = "reject_duplicate_memory_id"
            record.current_status = "rejected"
            record.evidence_role = "excluded_duplicate_memory_id"
            record.admission_reason = (
                "memory_id already exists; duplicate write rejected without overwriting stored memory"
            )
            self._log(record)
            return record

        key = record.scoped_key

        if record.source_confidence < self.low_confidence_threshold:
            record.admission_status = "reject_low_confidence"
            record.current_status = "rejected"
            record.evidence_role = "excluded_low_confidence"
            record.admission_reason = (
                f"source_confidence {record.source_confidence:.2f} below "
                f"{self.low_confidence_threshold:.2f}"
            )
            self.records[record.memory_id] = record
            self._log(record)
            return record

        validity_action = norm(str(record.payload.get("validity_action", "")))
        if validity_action in {"revoke_current", "invalidate_current", "invalidate"}:
            return self._admit_validity_marker(record, key)

        previous_current_id = self.current_by_key.get(key)
        if previous_current_id is None:
            record.admission_status = "admit_current"
            record.current_status = "current"
            record.evidence_role = "current_support"
            record.admission_reason = "first admitted current evidence for entity-slot key"
            self.current_by_key[key] = record.memory_id
            self.records[record.memory_id] = record
            self._log(record)
            return record

        previous = self.records[previous_current_id]

        if norm(previous.value) == norm(record.value):
            record.admission_status = "admit_supporting_evidence"
            record.current_status = "supporting"
            record.evidence_role = "supporting_duplicate"
            record.links["supports"].append(previous.memory_id)
            previous.links["supports"].append(record.memory_id)
            record.admission_reason = "same value as existing current memory; stored as support"
            self.records[record.memory_id] = record
            self._log(record)
            return record

        if record.observed_at >= previous.observed_at:
            record.admission_status = "admit_current"
            record.current_status = "current"
            record.evidence_role = "current_support"
            record.links["supersedes"].append(previous.memory_id)
            record.links["contradicts"].append(previous.memory_id)
            record.admission_reason = "newer conflicting evidence supersedes previous current memory"

            previous.admission_status = "admit_as_stale_contrast"
            previous.current_status = "superseded"
            previous.evidence_role = "stale_contrast"
            previous.links["superseded_by"].append(record.memory_id)
            previous.links["contradicts"].append(record.memory_id)
            previous.admission_reason = (
                "superseded by newer conflicting evidence; retained as stale contrast"
            )

            self.current_by_key[key] = record.memory_id
            self.records[record.memory_id] = record
            self._log(record)
            self._log(previous)
            return record

        record.admission_status = "admit_as_stale_contrast"
        record.current_status = "superseded"
        record.evidence_role = "stale_contrast"
        record.links["superseded_by"].append(previous.memory_id)
        record.links["contradicts"].append(previous.memory_id)
        record.admission_reason = "older conflicting evidence retained as stale contrast"
        previous.links["supersedes"].append(record.memory_id)
        previous.links["contradicts"].append(record.memory_id)
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def admit_records(self, records: list[dict[str, Any]]) -> list[MemoryRecord]:
        validated_records = validate_memory_batch(records)
        return [self.admit(record) for record in validated_records]

    def _admit_validity_marker(
        self, record: MemoryRecord, key: tuple[str, str, str, str, str]
    ) -> MemoryRecord:
        requested_target_ids = [
            str(memory_id)
            for memory_id in record.payload.get("invalidates_memory_ids", [])
        ]
        explicit_targets: list[str] = []
        scope_mismatch_count = 0
        for memory_id in requested_target_ids:
            target = self.records.get(memory_id)
            if target is None:
                continue
            if target.scoped_key != record.scoped_key:
                scope_mismatch_count += 1
                continue
            explicit_targets.append(memory_id)
        if scope_mismatch_count:
            record.payload["invalidates_scope_mismatch_count"] = scope_mismatch_count
        current_id = self.current_by_key.get(key)
        if requested_target_ids:
            target_ids = explicit_targets
        else:
            target_ids = [current_id] if current_id else []

        record.admission_status = "admit_validity_marker"
        record.current_status = "validity_marker"
        record.evidence_role = "validity_marker"
        record.admission_reason = (
            "write-time validity marker; invalidates current evidence for entity-slot key"
        )

        for target_id in target_ids:
            if not target_id:
                continue
            target = self.records[target_id]
            target.admission_status = "revoked_by_validity_marker"
            target.current_status = "revoked"
            target.evidence_role = "stale_contrast"
            if record.memory_id not in target.links["invalidated_by"]:
                target.links["invalidated_by"].append(record.memory_id)
            if record.memory_id not in target.links["contradicts"]:
                target.links["contradicts"].append(record.memory_id)
            if target.memory_id not in record.links["invalidates"]:
                record.links["invalidates"].append(target.memory_id)
            if target.memory_id not in record.links["contradicts"]:
                record.links["contradicts"].append(target.memory_id)
            target.admission_reason = (
                "revoked by write-time validity marker; retained as stale contrast"
            )
            if self.current_by_key.get(target.scoped_key) == target.memory_id:
                del self.current_by_key[target.scoped_key]
            self._log(target)

        if not target_ids:
            if scope_mismatch_count:
                record.admission_reason = (
                    "write-time validity marker admitted but explicit invalidation targets "
                    "were outside the marker scope"
                )
            else:
                record.admission_reason = (
                    "write-time validity marker admitted but no matching current evidence was found"
                )
        elif scope_mismatch_count:
            record.admission_reason = (
                f"{record.admission_reason}; ignored {scope_mismatch_count} cross-scope target(s)"
            )

        self.records[record.memory_id] = record
        self._log(record)
        return record

    def build_packet(
        self,
        query: dict[str, Any],
        *,
        max_current: int = 1,
        max_supporting: int = 2,
        max_stale: int = 2,
        max_excluded: int = 2,
        max_packet_chars: int | None = None,
        include_validity_edges: bool = True,
        include_weak_gate_card: bool = True,
    ) -> dict[str, Any]:
        query = validate_query_payload(query)
        budget = validate_retrieval_budget(
            max_current=max_current,
            max_supporting=max_supporting,
            max_stale=max_stale,
            max_excluded=max_excluded,
        )
        max_current = budget["max_current"]
        max_supporting = budget["max_supporting"]
        max_stale = budget["max_stale"]
        max_excluded = budget["max_excluded"]
        max_packet_chars = validate_max_packet_chars(max_packet_chars)

        key = norm(query["entity"]), norm(query["slot"])
        as_of = parse_dt(query.get("as_of"))
        risk_profile = self._query_risk_profile(query)
        reader_profile = self._query_reader_profile(query)
        query_intent = self._query_intent(query)
        max_age_days = self._query_max_age_days(query, risk_profile)
        min_source_confidence = self._query_min_source_confidence(query, risk_profile)
        min_supporting_count = self._query_min_supporting_count(query, risk_profile)
        source_policy = self._query_source_policy(query)
        query_scope = self._query_scope(query)
        key_related = [record for record in self.records.values() if record.key == key]
        scope_mismatch_ids = {
            record.memory_id
            for record in key_related
            if not self._scope_matches_query(record, query_scope)
        }
        related = [
            record for record in key_related if record.memory_id not in scope_mismatch_ids
        ]
        not_yet_valid_ids = {
            record.memory_id
            for record in related
            if self._is_not_yet_valid_for_query(record, as_of)
        }
        expired_ids = {
            record.memory_id
            for record in related
            if self._is_expired_for_query(record, as_of)
        }
        revoked_ids = {
            record.memory_id
            for record in related
            if self._is_revoked_for_query(record, as_of)
        }
        stale_by_age_ids = {
            record.memory_id
            for record in related
            if self._is_stale_by_age_for_query(record, as_of, max_age_days)
        }
        below_query_confidence_ids = {
            record.memory_id
            for record in related
            if self._is_below_query_confidence(record, min_source_confidence)
        }
        source_policy_mismatch_ids = {
            record.memory_id
            for record in related
            if self._violates_source_policy(record, source_policy)
        }
        condition_mismatch_ids = {
            record.memory_id
            for record in related
            if not self._condition_matches_query(record, query)
        }
        base_blocked_ids = (
            not_yet_valid_ids
            | expired_ids
            | revoked_ids
            | stale_by_age_ids
            | below_query_confidence_ids
            | source_policy_mismatch_ids
            | condition_mismatch_ids
        )
        base_current_candidates = self._current_candidates_for_query(
            related=related,
            blocked_ids=base_blocked_ids,
            as_of=as_of,
        )
        insufficient_support_ids = {
            record.memory_id
            for record in base_current_candidates
            if self._support_count_for_record(record, related, base_blocked_ids)
            < min_supporting_count
        }
        blocked_ids = base_blocked_ids | insufficient_support_ids
        current_candidates = [
            record for record in base_current_candidates if record.memory_id not in blocked_ids
        ]
        current = self._select_records(
            current_candidates,
            max_current,
        )
        current_ids = {record.memory_id for record in current}
        dynamically_blocked = [
            record
            for record in related
            if record.memory_id in blocked_ids
            and record.current_status in {"current", "supporting", "superseded", "revoked"}
        ]
        stale = self._select_records(
            self._dedupe_records(
                [
                    record
                    for record in related
                    if record.evidence_role in {"stale_contrast", "validity_marker"}
                    and record.memory_id not in current_ids
                ]
                + dynamically_blocked
            ),
            max_stale,
        )
        supporting = self._select_records(
            [
                record
                for record in related
                if record.evidence_role == "supporting_duplicate"
                and record.memory_id not in blocked_ids
            ],
            max_supporting,
        )
        excluded = self._select_records(
            [
                record
                for record in related
                if record.evidence_role == "excluded_low_confidence"
            ],
            max_excluded,
        )
        historical = self._historical_evidence_for_query(query_intent, stale)

        selected_records = current + supporting + stale + excluded
        selected_ids = {record.memory_id for record in selected_records}
        edges = (
            self._validity_edges(selected_records, selected_ids)
            if include_validity_edges
            else []
        )
        retrieval_diagnostics = self._retrieval_diagnostics(
            related=related,
            current_candidates=current_candidates,
            current=current,
            supporting=supporting,
            stale=stale,
            excluded=excluded,
            not_yet_valid_ids=not_yet_valid_ids,
            expired_ids=expired_ids,
            revoked_ids=revoked_ids,
            stale_by_age_ids=stale_by_age_ids,
            below_query_confidence_ids=below_query_confidence_ids,
            insufficient_support_ids=insufficient_support_ids,
            source_policy_mismatch_ids=source_policy_mismatch_ids,
            scope_mismatch_ids=scope_mismatch_ids,
            condition_mismatch_ids=condition_mismatch_ids,
            blocked_ids=blocked_ids,
        )
        retrieval_diagnostics["selected_counts"]["historical_evidence"] = len(historical)
        context_policy = self._context_control_policy_for_intent(
            query_intent=query_intent,
            max_current=max_current,
            max_supporting=max_supporting,
            max_stale=max_stale,
            max_excluded=max_excluded,
            max_packet_chars=max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
            reader_profile=reader_profile,
        )

        packet = {
            "query": {
                "query_id": query["query_id"],
                "text": query["query"],
                "entity": query["entity"],
                "slot": query["slot"],
                "needs_current": bool(query.get("needs_current", True)),
                "query_intent": query_intent,
                "as_of": query.get("as_of"),
                "risk_profile": risk_profile,
                "reader_profile": reader_profile,
                "scope": query_scope,
                "max_age_days": max_age_days,
                "min_source_confidence": min_source_confidence,
                "min_supporting_count": min_supporting_count,
                "source_policy": {
                    name: sorted(values)
                    for name, values in source_policy.items()
                    if values
                },
                "condition": query.get("condition") or query.get("required_condition"),
            },
            "context_control_policy": context_policy,
            "compact_validity_packet": {
                "current_evidence": [
                    self._evidence_view(record, retrieval_role="current_support")
                    for record in current
                ],
                "supporting_evidence": [
                    self._evidence_view(record, retrieval_role="supporting_duplicate")
                    for record in supporting
                ],
                "historical_evidence": [
                    self._evidence_view(
                        record,
                        retrieval_role="historical_evidence",
                        retrieval_reason=(
                            "archive evidence admitted for historical/timeline/audit query; "
                            "not current-state support unless separately listed as current_evidence"
                        ),
                    )
                    for record in historical
                ],
                "stale_or_blocked_evidence": [
                    self._evidence_view(
                        record,
                        retrieval_role=self._blocked_retrieval_role(
                            record,
                            not_yet_valid_ids,
                            expired_ids,
                            revoked_ids,
                            stale_by_age_ids,
                            below_query_confidence_ids,
                            insufficient_support_ids,
                            source_policy_mismatch_ids,
                            condition_mismatch_ids,
                        ),
                        retrieval_reason=self._blocked_retrieval_reason(
                            record,
                            not_yet_valid_ids,
                            expired_ids,
                            revoked_ids,
                            stale_by_age_ids,
                            below_query_confidence_ids,
                            insufficient_support_ids,
                            source_policy_mismatch_ids,
                            condition_mismatch_ids,
                        ),
                    )
                    for record in stale
                ],
                "excluded_memory_summary": [self._evidence_view(record) for record in excluded],
                "validity_edges": edges,
            },
            "retrieval_diagnostics": retrieval_diagnostics,
            "expected_read_time_decision": self._expected_decision(current, excluded),
        }
        if include_weak_gate_card:
            packet["weak_conservative_gate_card"] = self._weak_gate_card(
                query=query,
                current=current,
                stale=stale,
                supporting=supporting,
                excluded=excluded,
            )
        return apply_packet_char_budget(packet, max_packet_chars)

    def _select_records(
        self, records: list[MemoryRecord], limit: int
    ) -> list[MemoryRecord]:
        if limit == 0:
            return []
        return sorted(
            records,
            key=lambda record: (
                record.observed_at,
                record.source_confidence,
                record.memory_id,
            ),
            reverse=True,
        )[:limit]

    def _dedupe_records(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        seen: set[str] = set()
        for record in records:
            if record.memory_id in seen:
                continue
            seen.add(record.memory_id)
            out.append(record)
        return out

    def _retrieval_diagnostics(
        self,
        *,
        related: list[MemoryRecord],
        current_candidates: list[MemoryRecord],
        current: list[MemoryRecord],
        supporting: list[MemoryRecord],
        stale: list[MemoryRecord],
        excluded: list[MemoryRecord],
        not_yet_valid_ids: set[str],
        expired_ids: set[str],
        revoked_ids: set[str],
        stale_by_age_ids: set[str],
        below_query_confidence_ids: set[str],
        insufficient_support_ids: set[str],
        source_policy_mismatch_ids: set[str],
        scope_mismatch_ids: set[str],
        condition_mismatch_ids: set[str],
        blocked_ids: set[str],
    ) -> dict[str, Any]:
        return {
            "related_records_total": len(related),
            "scope_mismatch_records_total": len(scope_mismatch_ids),
            "eligible_current_candidates_total": len(current_candidates),
            "selected_counts": {
                "current_evidence": len(current),
                "supporting_evidence": len(supporting),
                "stale_or_blocked_evidence": len(stale),
                "excluded_memory_summary": len(excluded),
            },
            "blocked_counts": {
                "future_evidence": len(not_yet_valid_ids),
                "expired_contrast": len(expired_ids),
                "revoked_contrast": len(revoked_ids),
                "stale_by_age": len(stale_by_age_ids),
                "below_query_confidence": len(below_query_confidence_ids),
                "insufficient_support": len(insufficient_support_ids),
                "source_policy_mismatch": len(source_policy_mismatch_ids),
                "scope_mismatch": len(scope_mismatch_ids),
                "condition_mismatch": len(condition_mismatch_ids),
                "blocked_total_unique": len(blocked_ids),
            },
            "related_current_status_counts": self._count_by(related, "current_status"),
            "related_evidence_role_counts": self._count_by(related, "evidence_role"),
            "validity_marker_records_total": sum(
                1 for record in related if record.evidence_role == "validity_marker"
            ),
            "revoked_records_total": sum(
                1 for record in related if record.current_status == "revoked"
            ),
        }

    def _count_by(self, records: list[MemoryRecord], attribute: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in records:
            value = str(getattr(record, attribute))
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def _current_candidates_for_query(
        self,
        *,
        related: list[MemoryRecord],
        blocked_ids: set[str],
        as_of: datetime | None,
    ) -> list[MemoryRecord]:
        return [
            record
            for record in related
            if record.memory_id not in blocked_ids
            and (
                record.current_status == "current"
                if as_of is None
                else record.evidence_role in {"current_support", "stale_contrast"}
            )
        ]

    def _is_expired_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        return as_of is not None and record.valid_until is not None and as_of > record.valid_until

    def _is_revoked_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        marker_ids = record.links.get("invalidated_by", [])
        if not marker_ids:
            return False
        if as_of is None:
            return record.current_status == "revoked"
        for marker_id in marker_ids:
            marker = self.records.get(marker_id)
            if marker is not None and marker.observed_at <= as_of:
                return True
        return False

    def _is_stale_by_age_for_query(
        self,
        record: MemoryRecord,
        as_of: datetime | None,
        max_age_days: float | None,
    ) -> bool:
        if as_of is None or max_age_days is None:
            return False
        return record.observed_at < as_of - timedelta(days=max_age_days)

    def _query_risk_profile(self, query: dict[str, Any]) -> str:
        risk_profile = norm(str(query.get("risk_profile") or query.get("validity_profile") or "default"))
        if risk_profile not in RISK_PROFILE_DEFAULTS:
            known = ", ".join(sorted(RISK_PROFILE_DEFAULTS))
            raise ValueError(f"Unknown risk_profile {risk_profile!r}; expected one of: {known}")
        return risk_profile

    def _query_reader_profile(self, query: dict[str, Any]) -> str:
        reader_profile = norm(str(query.get("reader_profile") or "default"))
        if reader_profile not in READER_PROFILES:
            known = ", ".join(sorted(READER_PROFILES))
            raise ValueError(
                f"Unknown reader_profile {reader_profile!r}; expected one of: {known}"
            )
        return reader_profile

    def _reader_profile_contract(self, reader_profile: str) -> str:
        if reader_profile == "dim3_actionable":
            return (
                "For actionable current-state questions, first reject any stale embedded "
                "premise, then answer from admitted current evidence when it exists."
            )
        if reader_profile == "weak_conservative":
            return (
                "Use a simpler premise gate for weaker models: compare the embedded "
                "premise value against current and stale evidence before answering."
            )
        if reader_profile == "strong_graph_lite":
            return (
                "Use compact packet plus validity graph edges for structured admission; "
                "preserve stale evidence only as contrast."
            )
        return "Use the default conservative QVF read-time admission policy."

    def _query_intent(self, query: dict[str, Any]) -> str:
        raw_intent = query.get("query_intent") or query.get("memory_query_intent")
        if raw_intent:
            return norm(str(raw_intent))
        if query.get("as_of"):
            return "current_state"
        if query.get("needs_current") is False:
            return "historical_recall"

        text = norm(str(query.get("query", "")))
        timeline_cues = [
            "timeline",
            "change history",
            "history of",
            "changed",
            "evolved",
            "变化",
            "变更",
            "时间线",
            "历程",
        ]
        historical_cues = [
            "previous",
            "previously",
            "before",
            "earlier",
            "past",
            "used to",
            "used-to",
            "last year",
            "last month",
            "when did",
            "what was",
            "where was",
            "who was",
            "以前",
            "之前",
            "过去",
            "曾经",
            "什么时候",
            "当时",
        ]
        audit_cues = ["why did", "audit", "debug", "diagnose", "为什么", "审计", "诊断"]
        current_cues = [
            "current",
            "currently",
            "now",
            "latest",
            "still",
            "right now",
            "as of now",
            "现在",
            "当前",
            "目前",
            "还",
            "最新",
        ]
        if (
            any(cue in text for cue in ("did the", "has the"))
            and ("change" in text or "stayed the same" in text or "stay the same" in text)
        ):
            return "timeline_change"
        if any(cue in text for cue in timeline_cues):
            return "timeline_change"
        if any(cue in text for cue in audit_cues):
            return "validity_audit"
        if any(cue in text for cue in historical_cues):
            return "historical_recall"
        if any(cue in text for cue in current_cues):
            return "current_state"
        return "current_state"

    def _historical_evidence_for_query(
        self, query_intent: str, stale: list[MemoryRecord]
    ) -> list[MemoryRecord]:
        if query_intent not in {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }:
            return []
        return [
            record
            for record in stale
            if record.evidence_role == "stale_contrast"
            or record.current_status in {"superseded", "revoked"}
        ]

    def _context_control_policy_for_intent(
        self,
        *,
        query_intent: str,
        max_current: int,
        max_supporting: int,
        max_stale: int,
        max_excluded: int,
        max_packet_chars: int | None,
        include_validity_edges: bool,
        include_weak_gate_card: bool,
        reader_profile: str,
    ) -> dict[str, Any]:
        retrieval_budget = {
            "max_current": max_current,
            "max_supporting": max_supporting,
            "max_stale": max_stale,
            "max_excluded": max_excluded,
            "max_packet_chars": max_packet_chars,
            "include_validity_edges": include_validity_edges,
            "include_weak_gate_card": include_weak_gate_card,
        }
        base_do_not_answer = [
            "expired_contrast",
            "revoked_contrast",
            "below_query_confidence",
            "insufficient_support",
            "source_policy_mismatch",
            "scope_mismatch",
            "condition_mismatch",
            "future_evidence",
            "excluded_low_confidence",
            "conflict_candidate",
        ]
        archive_intents = {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }
        if query_intent in archive_intents:
            return {
                "answer_from_roles": [
                    "current_support",
                    "historical_evidence",
                    "supporting_duplicate",
                ],
                "do_not_answer_from_roles": base_do_not_answer,
                "include_stale_evidence_as_contrast": True,
                "include_archive_evidence_as_answer_context": True,
                "archive_policy": (
                    "Historical/archive evidence may answer historical, timeline, "
                    "or audit queries. Do not reinterpret it as the current state unless "
                    "it is also listed as current_evidence."
                ),
                "retrieval_budget": retrieval_budget,
                "reader_contract": (
                    "Use current_evidence for present-state claims. For historical, "
                    "timeline, or audit queries, historical_evidence is admissible answer "
                    "context and should be labeled as historical or superseded when relevant."
                ),
                "reader_profile_contract": self._reader_profile_contract(reader_profile),
            }
        return {
            "answer_from_roles": ["current_support"],
            "do_not_answer_from_roles": [
                "stale_contrast",
                "stale_by_age",
            ]
            + base_do_not_answer,
            "include_stale_evidence_as_contrast": True,
            "include_archive_evidence_as_answer_context": False,
            "archive_policy": (
                "Archived stale evidence is visible for contrast and provenance, but "
                "must not answer current-state questions."
            ),
            "retrieval_budget": retrieval_budget,
            "reader_contract": (
                "Answer only from current_support if present. Use stale_contrast "
                "to reject stale premises, not as answer evidence. If no current "
                "support exists, return unknown_current_state."
            ),
            "reader_profile_contract": self._reader_profile_contract(reader_profile),
        }

    def _profile_default(self, risk_profile: str, field: str) -> Any:
        return RISK_PROFILE_DEFAULTS[risk_profile][field]

    def _query_max_age_days(
        self, query: dict[str, Any], risk_profile: str
    ) -> float | None:
        value = (
            query.get("max_age_days")
            if query.get("max_age_days") is not None
            else query.get("freshness_window_days")
        )
        if value is None:
            value = self._profile_default(risk_profile, "max_age_days")
        if value is None:
            return None
        max_age_days = float(value)
        if max_age_days < 0:
            raise ValueError("max_age_days/freshness_window_days must be >= 0")
        return max_age_days

    def _query_min_source_confidence(
        self, query: dict[str, Any], risk_profile: str
    ) -> float | None:
        value = (
            query.get("min_source_confidence")
            if query.get("min_source_confidence") is not None
            else query.get("required_source_confidence")
        )
        if value is None:
            value = self._profile_default(risk_profile, "min_source_confidence")
        if value is None:
            return None
        min_source_confidence = float(value)
        if not 0 <= min_source_confidence <= 1:
            raise ValueError("min_source_confidence/required_source_confidence must be in [0, 1]")
        return min_source_confidence

    def _query_min_supporting_count(
        self, query: dict[str, Any], risk_profile: str
    ) -> int:
        value = (
            query.get("min_supporting_count")
            if query.get("min_supporting_count") is not None
            else query.get("required_supporting_count")
        )
        if value is None:
            value = self._profile_default(risk_profile, "min_supporting_count")
        min_supporting_count = int(value)
        if min_supporting_count < 0:
            raise ValueError("min_supporting_count/required_supporting_count must be >= 0")
        return min_supporting_count

    def _query_source_policy(self, query: dict[str, Any]) -> dict[str, set[str]]:
        return {
            "allowed_source_types": self._normalized_query_set(
                query.get("allowed_source_types") or query.get("required_source_types")
            ),
            "blocked_source_types": self._normalized_query_set(
                query.get("blocked_source_types") or query.get("excluded_source_types")
            ),
            "allowed_source_ids": self._normalized_query_set(
                query.get("allowed_source_ids") or query.get("required_source_ids")
            ),
            "blocked_source_ids": self._normalized_query_set(
                query.get("blocked_source_ids") or query.get("excluded_source_ids")
            ),
        }

    def _query_scope(self, query: dict[str, Any]) -> dict[str, str]:
        raw_scope = query.get("scope", {}) or {}
        return {
            "namespace": norm(str(raw_scope.get("namespace") or query.get("namespace") or "")),
            "tenant_id": norm(str(raw_scope.get("tenant_id") or query.get("tenant_id") or "")),
            "user_id": norm(str(raw_scope.get("user_id") or query.get("user_id") or "")),
        }

    def _scope_matches_query(
        self, record: MemoryRecord, query_scope: dict[str, str]
    ) -> bool:
        record_scope = {
            name: norm(value) for name, value in record.scope.items()
        }
        for name in ["namespace", "tenant_id", "user_id"]:
            if record_scope[name] or query_scope[name]:
                if record_scope[name] != query_scope[name]:
                    return False
        return True

    def _normalized_query_set(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = [value]
        return {norm(str(item)) for item in values if str(item).strip()}

    def _violates_source_policy(
        self, record: MemoryRecord, source_policy: dict[str, set[str]]
    ) -> bool:
        source_type = norm(record.source_type)
        source_id = norm(record.source_id)
        allowed_types = source_policy["allowed_source_types"]
        blocked_types = source_policy["blocked_source_types"]
        allowed_ids = source_policy["allowed_source_ids"]
        blocked_ids = source_policy["blocked_source_ids"]
        return (
            (bool(allowed_types) and source_type not in allowed_types)
            or (bool(blocked_types) and source_type in blocked_types)
            or (bool(allowed_ids) and source_id not in allowed_ids)
            or (bool(blocked_ids) and source_id in blocked_ids)
        )

    def _support_count_for_record(
        self,
        record: MemoryRecord,
        related: list[MemoryRecord],
        blocked_ids: set[str],
    ) -> int:
        return sum(
            1
            for candidate in related
            if candidate.memory_id not in blocked_ids
            and candidate.evidence_role == "supporting_duplicate"
            and (
                record.memory_id in candidate.links.get("supports", [])
                or norm(candidate.value) == norm(record.value)
            )
        )

    def _is_below_query_confidence(
        self, record: MemoryRecord, min_source_confidence: float | None
    ) -> bool:
        return (
            min_source_confidence is not None
            and record.source_confidence < min_source_confidence
        )

    def _is_not_yet_valid_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        return as_of is not None and as_of < record.valid_from

    def _condition_matches_query(
        self, record: MemoryRecord, query: dict[str, Any]
    ) -> bool:
        condition = record.payload.get("condition")
        if not condition:
            return True
        normalized_condition = norm(str(condition))
        query_condition = query.get("condition") or query.get("required_condition")
        if query_condition:
            normalized_query_condition = norm(str(query_condition))
            return (
                normalized_condition == normalized_query_condition
                or normalized_condition in normalized_query_condition
                or normalized_query_condition in normalized_condition
            )
        return normalized_condition in norm(str(query.get("query", "")))

    def _blocked_retrieval_role(
        self,
        record: MemoryRecord,
        not_yet_valid_ids: set[str],
        expired_ids: set[str],
        revoked_ids: set[str],
        stale_by_age_ids: set[str],
        below_query_confidence_ids: set[str],
        insufficient_support_ids: set[str],
        source_policy_mismatch_ids: set[str],
        condition_mismatch_ids: set[str],
    ) -> str:
        if record.memory_id in not_yet_valid_ids:
            return "future_evidence"
        if record.memory_id in expired_ids:
            return "expired_contrast"
        if record.memory_id in revoked_ids:
            return "revoked_contrast"
        if record.memory_id in stale_by_age_ids:
            return "stale_by_age"
        if record.memory_id in below_query_confidence_ids:
            return "below_query_confidence"
        if record.memory_id in insufficient_support_ids:
            return "insufficient_support"
        if record.memory_id in source_policy_mismatch_ids:
            return "source_policy_mismatch"
        if record.evidence_role == "validity_marker":
            return "validity_marker"
        if record.memory_id in condition_mismatch_ids:
            return "condition_mismatch"
        return "stale_contrast"

    def _blocked_retrieval_reason(
        self,
        record: MemoryRecord,
        not_yet_valid_ids: set[str],
        expired_ids: set[str],
        revoked_ids: set[str],
        stale_by_age_ids: set[str],
        below_query_confidence_ids: set[str],
        insufficient_support_ids: set[str],
        source_policy_mismatch_ids: set[str],
        condition_mismatch_ids: set[str],
    ) -> str:
        if record.memory_id in not_yet_valid_ids:
            return "valid_from is after query as_of"
        if record.memory_id in expired_ids:
            return "valid_until is before query as_of"
        if record.memory_id in revoked_ids:
            return "revoked by write-time validity marker before query as_of"
        if record.memory_id in stale_by_age_ids:
            return "observed_at is older than query max_age_days"
        if record.memory_id in below_query_confidence_ids:
            return "source_confidence is below query min_source_confidence"
        if record.memory_id in insufficient_support_ids:
            return "supporting duplicate count is below query min_supporting_count"
        if record.memory_id in source_policy_mismatch_ids:
            return "source does not satisfy query source policy"
        if record.evidence_role == "validity_marker":
            return record.admission_reason
        if record.memory_id in condition_mismatch_ids:
            return "memory condition does not match query condition"
        return record.admission_reason

    def _validity_edges(
        self, selected_records: list[MemoryRecord], selected_ids: set[str]
    ) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        for record in selected_records:
            for edge_type in [
                "supersedes",
                "superseded_by",
                "contradicts",
                "supports",
                "invalidates",
                "invalidated_by",
            ]:
                for target in record.links.get(edge_type, []):
                    if target in selected_ids:
                        edges.append(
                            {
                                "source": record.memory_id,
                                "target": target,
                                "type": edge_type,
                            }
                        )
        return sorted(
            edges, key=lambda edge: (edge["source"], edge["target"], edge["type"])
        )

    def _expected_decision(
        self, current: list[MemoryRecord], excluded: list[MemoryRecord]
    ) -> str:
        if current:
            return "ADMIT_CURRENT"
        if excluded:
            return "UNKNOWN_CURRENT"
        return "UNKNOWN_CURRENT"

    def _weak_gate_card(
        self,
        *,
        query: dict[str, Any],
        current: list[MemoryRecord],
        stale: list[MemoryRecord],
        supporting: list[MemoryRecord],
        excluded: list[MemoryRecord],
    ) -> dict[str, Any]:
        premise_value = query.get("embedded_premise_value")
        reader_profile = str(query.get("reader_profile") or "default")
        current_values = {norm(record.value) for record in current}
        stale_values = {norm(record.value) for record in stale}

        if premise_value and current:
            normalized_premise = norm(str(premise_value))
            if normalized_premise in current_values:
                expected_gate_decision = "ADMIT_CURRENT"
            elif normalized_premise in stale_values:
                expected_gate_decision = "REJECT_STALE_PREMISE"
            else:
                expected_gate_decision = "UNKNOWN_CURRENT"
        elif current:
            expected_gate_decision = "ADMIT_CURRENT"
        elif premise_value and norm(str(premise_value)) in stale_values:
            expected_gate_decision = "REJECT_STALE_PREMISE"
        elif excluded:
            expected_gate_decision = "UNKNOWN_CURRENT"
        else:
            expected_gate_decision = "UNKNOWN_CURRENT"

        decision_rules = [
            "ADMIT_CURRENT only if current_candidate_evidence directly supports the premise.",
            "REJECT_STALE_PREMISE if stale_or_blocked_evidence supports the premise but current_candidate_evidence differs.",
            "UNKNOWN_CURRENT if evidence is missing, excluded, or ambiguous.",
            "When rejecting or unknown, correct the premise boundary instead of answering from stale evidence.",
        ]
        if reader_profile == "weak_conservative":
            decision_rules.insert(
                0,
                "For weak readers, compare embedded_premise_value to evidence values first; if current evidence differs from the premise, do not ADMIT_CURRENT.",
            )
        if reader_profile == "dim3_actionable":
            decision_rules.append(
                "For actionable questions, after rejecting a stale premise, use current_candidate_evidence to produce a current-state action if it exists."
            )

        return {
            "adapter": "weak_conservative_gate_v0.1",
            "purpose": (
                "Low-burden stale-premise gate for weaker readers; use before "
                "free-form answering when the query embeds a current/still/since premise."
            ),
            "query": {
                "query_id": query["query_id"],
                "text": query["query"],
                "entity": query["entity"],
                "slot": query["slot"],
                "needs_current": bool(query.get("needs_current", True)),
                "embedded_premise_value": premise_value,
                "reader_profile": reader_profile,
            },
            "decision_rules": decision_rules,
            "current_candidate_evidence": [
                self._gate_evidence_view(record) for record in current + supporting
            ],
            "stale_or_blocked_evidence": [
                self._gate_evidence_view(record) for record in stale
            ],
            "excluded_evidence": [
                self._gate_evidence_view(record) for record in excluded
            ],
            "expected_gate_decision": expected_gate_decision,
            "reader_output_schema": {
                "decision": "ADMIT_CURRENT | REJECT_STALE_PREMISE | UNKNOWN_CURRENT",
                "support": "memory_id or empty",
                "blocker": "memory_id or empty",
                "final_answer": "concise answer",
            },
        }

    def _evidence_view(
        self,
        record: MemoryRecord,
        *,
        retrieval_role: str | None = None,
        retrieval_reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "memory_id": record.memory_id,
            "claim": record.payload["claim"],
            "value": record.value,
            "observed_at": record.payload["observed_at"],
            "valid_until": record.payload.get("valid_until"),
            "condition": record.payload.get("condition"),
            "scope": record.scope,
            "source_id": record.source_id,
            "source_type": record.source_type,
            "source_span": record.payload.get("source", {}).get("source_span", ""),
            "source_turn_ids": record.payload.get("source", {}).get("source_turn_ids", []),
            "source_confidence": record.source_confidence,
            "admission_status": record.admission_status,
            "current_status": record.current_status,
            "evidence_role": record.evidence_role,
            "retrieval_role": retrieval_role or record.evidence_role,
            "retrieval_reason": retrieval_reason or record.admission_reason,
            "reason": record.admission_reason,
        }

    def _gate_evidence_view(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "memory_id": record.memory_id,
            "value": record.value,
            "claim": record.payload["claim"],
            "observed_at": record.payload["observed_at"],
            "valid_until": record.payload.get("valid_until"),
            "scope": record.scope,
            "source_id": record.source_id,
            "source_type": record.source_type,
            "evidence_role": record.evidence_role,
            "current_status": record.current_status,
        }

    def _log(self, record: MemoryRecord) -> None:
        self.admission_log.append(
            {
                "memory_id": record.memory_id,
                "entity": record.entity,
                "slot": record.slot,
                "value": record.value,
                "observed_at": record.payload["observed_at"],
                "source_confidence": f"{record.source_confidence:.2f}",
                "admission_status": record.admission_status,
                "current_status": record.current_status,
                "evidence_role": record.evidence_role,
                "reason": record.admission_reason,
            }
        )

    def export_memory_store(self) -> list[dict[str, Any]]:
        return [
            self.records[memory_id].to_public_dict()
            for memory_id in sorted(self.records)
        ]


def write_csv(
    path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None
) -> None:
    if not rows and fieldnames is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def count_rows_by_field(rows: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field_name, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_count_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = sorted(set(before) | set(after))
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys}


def scoped_key_to_public_dict(scoped_key: tuple[str, str, str, str, str]) -> dict[str, str]:
    return {
        "namespace": scoped_key[0],
        "tenant_id": scoped_key[1],
        "user_id": scoped_key[2],
        "entity": scoped_key[3],
        "slot": scoped_key[4],
    }


def build_memory_record_change(
    memory_id: str,
    before_row: dict[str, Any] | None,
    after_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if before_row is None:
        change_type = "added"
        changed_fields = sorted(after_row.keys()) if after_row is not None else []
    elif after_row is None:
        change_type = "removed"
        changed_fields = sorted(before_row.keys())
    else:
        change_type = "updated"
        changed_fields = sorted(
            field_name
            for field_name in set(before_row) | set(after_row)
            if before_row.get(field_name) != after_row.get(field_name)
        )
    return {
        "memory_id": memory_id,
        "change_type": change_type,
        "changed_fields": changed_fields,
        "before": before_row,
        "after": after_row,
    }


def build_memory_store_diff(
    before_store: ValidityAwareMemoryStore,
    after_store: ValidityAwareMemoryStore,
) -> dict[str, Any]:
    before_rows = {
        memory_id: record.to_public_dict()
        for memory_id, record in before_store.records.items()
    }
    after_rows = {
        memory_id: record.to_public_dict()
        for memory_id, record in after_store.records.items()
    }
    before_ids = set(before_rows)
    after_ids = set(after_rows)
    added_memory_ids = sorted(after_ids - before_ids)
    removed_memory_ids = sorted(before_ids - after_ids)
    updated_memory_ids = sorted(
        memory_id
        for memory_id in before_ids & after_ids
        if before_rows[memory_id] != after_rows[memory_id]
    )
    record_changes = [
        build_memory_record_change(
            memory_id,
            before_rows.get(memory_id),
            after_rows.get(memory_id),
        )
        for memory_id in [*added_memory_ids, *updated_memory_ids, *removed_memory_ids]
    ]
    current_index_changes = [
        {
            "scoped_key": scoped_key_to_public_dict(scoped_key),
            "normalized_scoped_key": "::".join(scoped_key),
            "before_memory_id": before_store.current_by_key.get(scoped_key),
            "after_memory_id": after_store.current_by_key.get(scoped_key),
        }
        for scoped_key in sorted(
            set(before_store.current_by_key) | set(after_store.current_by_key)
        )
        if before_store.current_by_key.get(scoped_key)
        != after_store.current_by_key.get(scoped_key)
    ]
    return {
        "added_memory_ids": added_memory_ids,
        "removed_memory_ids": removed_memory_ids,
        "updated_memory_ids": updated_memory_ids,
        "changed_memory_ids": sorted(
            set(added_memory_ids) | set(updated_memory_ids) | set(removed_memory_ids)
        ),
        "record_changes": record_changes,
        "current_index_changes": current_index_changes,
    }


def build_lifecycle_step_delta(
    admission_report: dict[str, Any],
    query_report: dict[str, Any],
) -> dict[str, Any]:
    admission_events = admission_report.get("admission_events", [])
    query_results = query_report.get("query_results", [])
    return {
        "input_memory_ids": list(admission_report.get("input_memory_ids", [])),
        "admission_event_memory_ids": [
            event["memory_id"] for event in admission_events
        ],
        "current_memory_ids": [
            event["memory_id"]
            for event in admission_events
            if event.get("current_status") == "current"
        ],
        "superseded_memory_ids": [
            event["memory_id"]
            for event in admission_events
            if event.get("current_status") == "superseded"
        ],
        "rejected_memory_ids": [
            event["memory_id"]
            for event in admission_events
            if str(event.get("admission_status", "")).startswith("reject_")
            or event.get("current_status") == "rejected"
        ],
        "query_ids": [result["query_id"] for result in query_results],
        "read_decisions_by_query_id": {
            result["query_id"]: result["read_decision"]["decision"]
            for result in query_results
        },
    }


def load_memory_store_jsonl(
    path: Path,
    *,
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> ValidityAwareMemoryStore:
    return ValidityAwareMemoryStore.from_exported_records(
        load_jsonl(path),
        low_confidence_threshold=low_confidence_threshold,
    )


def validate_retrieval_budget(
    *,
    max_current: Any = 1,
    max_supporting: Any = 2,
    max_stale: Any = 2,
    max_excluded: Any = 2,
) -> dict[str, int]:
    raw_budget = {
        "max_current": max_current,
        "max_supporting": max_supporting,
        "max_stale": max_stale,
        "max_excluded": max_excluded,
    }
    validated: dict[str, int] = {}
    for field_name in RETRIEVAL_BUDGET_FIELDS:
        value = raw_budget[field_name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{field_name} must be a non-negative integer")
        if value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
        validated[field_name] = value
    return validated


def validate_max_packet_chars(max_packet_chars: Any) -> int | None:
    if max_packet_chars is None:
        return None
    if isinstance(max_packet_chars, bool) or not isinstance(max_packet_chars, int):
        raise ValueError("max_packet_chars must be a positive integer when set")
    if max_packet_chars <= 0:
        raise ValueError("max_packet_chars must be a positive integer when set")
    return max_packet_chars


def apply_packet_char_budget(
    packet: dict[str, Any], max_packet_chars: int | None
) -> dict[str, Any]:
    max_packet_chars = validate_max_packet_chars(max_packet_chars)
    if max_packet_chars is None:
        return refresh_token_budget_proxy(packet, max_packet_chars=None)

    pruned_packet = deepcopy(packet)
    pruning_steps: list[str] = []
    if _packet_fits_char_budget(pruned_packet, max_packet_chars, pruning_steps):
        return refresh_token_budget_proxy(
            pruned_packet,
            max_packet_chars=max_packet_chars,
            pruning_steps=pruning_steps,
        )

    preserve_weak_gate = _weak_gate_has_embedded_premise(pruned_packet)
    if not preserve_weak_gate and pruned_packet.pop("weak_conservative_gate_card", None) is not None:
        pruning_steps.append("drop_weak_conservative_gate_card")
    compact_packet = pruned_packet.get("compact_validity_packet", {})
    if compact_packet.get("validity_edges"):
        compact_packet["validity_edges"] = []
        pruning_steps.append("drop_validity_edges")

    if (
        preserve_weak_gate
        and not _packet_fits_char_budget(pruned_packet, max_packet_chars, pruning_steps)
        and _compact_weak_gate_card(pruned_packet)
    ):
        pruning_steps.append("compact_weak_conservative_gate_card")

    for bucket_name in [
        "excluded_memory_summary",
        "supporting_evidence",
        "historical_evidence",
        "stale_or_blocked_evidence",
    ]:
        removed = _trim_packet_bucket_to_budget(
            compact_packet,
            bucket_name,
            pruned_packet,
            max_packet_chars,
            pruning_steps,
        )
        if removed:
            pruning_steps.append(f"trim_{bucket_name}:{removed}")
            _sync_weak_gate_card_to_compact_packet(pruned_packet, pruning_steps)

    current_evidence = compact_packet.get("current_evidence", [])
    removed_current = 0
    while (
        isinstance(current_evidence, list)
        and len(current_evidence) > 1
        and not _packet_fits_char_budget(pruned_packet, max_packet_chars, pruning_steps)
    ):
        current_evidence.pop()
        removed_current += 1
    if removed_current:
        pruning_steps.append(f"trim_current_evidence:{removed_current}")
        _sync_weak_gate_card_to_compact_packet(pruned_packet, pruning_steps)

    if not _packet_fits_char_budget(pruned_packet, max_packet_chars, pruning_steps):
        diagnostics = pruned_packet.get("retrieval_diagnostics")
        if isinstance(diagnostics, dict):
            pruned_packet["retrieval_diagnostics"] = {
                "related_records_total": diagnostics.get("related_records_total", 0),
                "selected_counts": diagnostics.get("selected_counts", {}),
                "blocked_counts": diagnostics.get("blocked_counts", {}),
                "diagnostics_compacted_for_packet_budget": True,
            }
            pruning_steps.append("compact_retrieval_diagnostics")

    _refresh_selected_counts_after_packet_pruning(pruned_packet, pruning_steps)
    return refresh_token_budget_proxy(
        pruned_packet,
        max_packet_chars=max_packet_chars,
        pruning_steps=pruning_steps,
    )


def _weak_gate_has_embedded_premise(packet: dict[str, Any]) -> bool:
    card = packet.get("weak_conservative_gate_card")
    if not isinstance(card, dict):
        return False
    query = card.get("query")
    if not isinstance(query, dict):
        return False
    premise = query.get("embedded_premise_value")
    return isinstance(premise, str) and bool(premise.strip())


def _compact_weak_gate_card(packet: dict[str, Any]) -> bool:
    card = packet.get("weak_conservative_gate_card")
    if not isinstance(card, dict):
        return False
    removed_any = False
    for field_name in ["purpose", "decision_rules", "reader_output_schema"]:
        if field_name in card:
            card.pop(field_name)
            removed_any = True
    return removed_any


def _sync_weak_gate_card_to_compact_packet(
    packet: dict[str, Any], pruning_steps: list[str]
) -> None:
    card = packet.get("weak_conservative_gate_card")
    compact_packet = packet.get("compact_validity_packet")
    if not isinstance(card, dict) or not isinstance(compact_packet, dict):
        return
    retained_ids: set[str] = set()
    for bucket_name in PACKET_EVIDENCE_BUCKETS + OPTIONAL_PACKET_EVIDENCE_BUCKETS:
        rows = compact_packet.get(bucket_name, [])
        if not isinstance(rows, list):
            continue
        retained_ids.update(
            row["memory_id"]
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("memory_id"), str)
            and row["memory_id"].strip()
        )
    for bucket_name in WEAK_GATE_EVIDENCE_BUCKETS:
        rows = card.get(bucket_name, [])
        if not isinstance(rows, list):
            continue
        filtered_rows = [
            row
            for row in rows
            if isinstance(row, dict) and row.get("memory_id") in retained_ids
        ]
        removed = len(rows) - len(filtered_rows)
        if removed:
            card[bucket_name] = filtered_rows
            pruning_steps.append(f"sync_weak_gate_{bucket_name}:{removed}")


def _refresh_selected_counts_after_packet_pruning(
    packet: dict[str, Any], pruning_steps: list[str]
) -> None:
    diagnostics = packet.get("retrieval_diagnostics")
    compact_packet = packet.get("compact_validity_packet")
    if not isinstance(diagnostics, dict) or not isinstance(compact_packet, dict):
        return
    diagnostics["selected_counts"] = {
        bucket_name: len(compact_packet.get(bucket_name, []))
        if isinstance(compact_packet.get(bucket_name, []), list)
        else 0
        for bucket_name in PACKET_EVIDENCE_BUCKETS + OPTIONAL_PACKET_EVIDENCE_BUCKETS
    }
    if pruning_steps:
        diagnostics["packet_budget_pruned"] = True


def _trim_packet_bucket_to_budget(
    compact_packet: dict[str, Any],
    bucket_name: str,
    packet: dict[str, Any],
    max_packet_chars: int,
    pruning_steps: list[str],
) -> int:
    bucket = compact_packet.get(bucket_name, [])
    if not isinstance(bucket, list):
        return 0
    removed = 0
    while bucket and not _packet_fits_char_budget(packet, max_packet_chars, pruning_steps):
        bucket.pop()
        removed += 1
    return removed


def _packet_fits_char_budget(
    packet: dict[str, Any], max_packet_chars: int, pruning_steps: list[str]
) -> bool:
    probe = deepcopy(packet)
    refresh_token_budget_proxy(
        probe,
        max_packet_chars=max_packet_chars,
        pruning_steps=pruning_steps,
    )
    return probe["token_budget_proxy"]["json_chars"] <= max_packet_chars


def refresh_token_budget_proxy(
    packet: dict[str, Any],
    *,
    max_packet_chars: int | None,
    pruning_steps: list[str] | None = None,
) -> dict[str, Any]:
    packet.pop("token_budget_proxy", None)
    proxy: dict[str, Any] = {
        "json_chars": 0,
        "word_like_tokens": 0,
    }
    if max_packet_chars is not None:
        proxy["max_packet_chars"] = max_packet_chars
        proxy["budget_satisfied"] = False
        proxy["pruning_steps"] = list(pruning_steps or [])
    packet["token_budget_proxy"] = proxy
    for _ in range(4):
        json_blob = json.dumps(packet, ensure_ascii=False)
        proxy["json_chars"] = len(json_blob)
        proxy["word_like_tokens"] = len(json_blob.split())
        if max_packet_chars is not None:
            proxy["budget_satisfied"] = proxy["json_chars"] <= max_packet_chars
    return packet


def validate_packet_payload(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("packet must be an object")
    validated = deepcopy(packet)
    query = validated.get("query")
    if not isinstance(query, dict):
        raise ValueError("packet.query must be an object")
    for field_name in PACKET_REQUIRED_QUERY_FIELDS:
        value = query.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"packet.query.{field_name} must be a non-empty string")
    reader_profile = query.get("reader_profile")
    if reader_profile is not None:
        if not isinstance(reader_profile, str) or not reader_profile.strip():
            raise ValueError("packet.query.reader_profile must be a non-empty string")
        normalized_profile = norm(reader_profile)
        if normalized_profile not in READER_PROFILES:
            known = ", ".join(sorted(READER_PROFILES))
            raise ValueError(
                f"packet.query.reader_profile must be one of: {known}"
            )
        query["reader_profile"] = normalized_profile

    compact_packet = validated.get("compact_validity_packet")
    if not isinstance(compact_packet, dict):
        raise ValueError("packet.compact_validity_packet must be an object")
    seen_ids: set[str] = set()
    for bucket_name in PACKET_EVIDENCE_BUCKETS:
        value = compact_packet.get(bucket_name)
        if not isinstance(value, list):
            raise ValueError(f"packet.compact_validity_packet.{bucket_name} must be a list")
        compact_packet[bucket_name] = [
            _validate_packet_evidence_row(
                row,
                field_path=f"packet.compact_validity_packet.{bucket_name}[{index}]",
                seen_ids=seen_ids,
            )
            for index, row in enumerate(value)
        ]
    for bucket_name in OPTIONAL_PACKET_EVIDENCE_BUCKETS:
        value = compact_packet.get(bucket_name, [])
        if not isinstance(value, list):
            raise ValueError(f"packet.compact_validity_packet.{bucket_name} must be a list")
        compact_packet[bucket_name] = [
            _validate_packet_evidence_row(
                row,
                field_path=f"packet.compact_validity_packet.{bucket_name}[{index}]",
            )
            for index, row in enumerate(value)
        ]
    compact_packet["validity_edges"] = _validate_packet_validity_edges(
        compact_packet.get("validity_edges", [])
    )

    weak_gate_card = validated.get("weak_conservative_gate_card")
    if weak_gate_card is not None:
        validated["weak_conservative_gate_card"] = _validate_weak_gate_card_payload(
            weak_gate_card
        )
    return validated


def validate_packet_batch(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(packets, list):
        raise ValueError("packets must be a list")
    validated_packets = [validate_packet_payload(packet) for packet in packets]
    seen_query_ids: set[str] = set()
    duplicate_query_ids: set[str] = set()
    for packet in validated_packets:
        query_id = packet["query"]["query_id"]
        if query_id in seen_query_ids:
            duplicate_query_ids.add(query_id)
        seen_query_ids.add(query_id)
    if duplicate_query_ids:
        duplicates = ", ".join(sorted(duplicate_query_ids))
        raise ValueError(f"Duplicate packet query_id in packet batch: {duplicates}")
    return validated_packets


def _validate_packet_evidence_row(
    row: dict[str, Any], *, field_path: str, seen_ids: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"{field_path} must be an object")
    validated = deepcopy(row)
    for field_name in ["memory_id", "value"]:
        value = validated.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_path}.{field_name} must be a non-empty string")
    if seen_ids is not None:
        memory_id = validated["memory_id"]
        if memory_id in seen_ids:
            raise ValueError(f"Duplicate evidence memory_id in packet: {memory_id}")
        seen_ids.add(memory_id)
    return validated


def _validate_packet_validity_edges(edges: Any) -> list[dict[str, Any]]:
    if not isinstance(edges, list):
        raise ValueError("packet.compact_validity_packet.validity_edges must be a list")
    validated_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(edges):
        field_path = f"packet.compact_validity_packet.validity_edges[{index}]"
        if not isinstance(edge, dict):
            raise ValueError(f"{field_path} must be an object")
        validated = deepcopy(edge)
        for field_name in ["source", "target", "type"]:
            value = validated.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_path}.{field_name} must be a non-empty string")
        validated_edges.append(validated)
    return validated_edges


def _validate_weak_gate_card_payload(card: Any) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError("packet.weak_conservative_gate_card must be an object")
    validated = deepcopy(card)
    query = validated.get("query")
    if not isinstance(query, dict):
        raise ValueError("packet.weak_conservative_gate_card.query must be an object")
    for field_name in PACKET_REQUIRED_QUERY_FIELDS:
        value = query.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"packet.weak_conservative_gate_card.query.{field_name} "
                "must be a non-empty string"
            )
    premise = query.get("embedded_premise_value")
    if premise is not None and not isinstance(premise, str):
        raise ValueError(
            "packet.weak_conservative_gate_card.query.embedded_premise_value "
            "must be a string when present"
        )
    reader_profile = query.get("reader_profile")
    if reader_profile is not None:
        if not isinstance(reader_profile, str) or not reader_profile.strip():
            raise ValueError(
                "packet.weak_conservative_gate_card.query.reader_profile "
                "must be a non-empty string"
            )
        normalized_profile = norm(reader_profile)
        if normalized_profile not in READER_PROFILES:
            known = ", ".join(sorted(READER_PROFILES))
            raise ValueError(
                "packet.weak_conservative_gate_card.query.reader_profile "
                f"must be one of: {known}"
            )
        query["reader_profile"] = normalized_profile
    expected_decision = validated.get("expected_gate_decision")
    if expected_decision not in READ_DECISION_VALUES:
        known = ", ".join(sorted(READ_DECISION_VALUES))
        raise ValueError(
            "packet.weak_conservative_gate_card.expected_gate_decision "
            f"must be one of: {known}"
        )
    seen_ids: set[str] = set()
    for bucket_name in WEAK_GATE_EVIDENCE_BUCKETS:
        value = validated.get(bucket_name)
        if not isinstance(value, list):
            raise ValueError(f"packet.weak_conservative_gate_card.{bucket_name} must be a list")
        validated[bucket_name] = [
            _validate_packet_evidence_row(
                row,
                field_path=f"packet.weak_conservative_gate_card.{bucket_name}[{index}]",
                seen_ids=seen_ids,
            )
            for index, row in enumerate(value)
        ]
    return validated


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
    slot = str(query.get("slot") or "").strip()
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
    """Return an action-oriented memory-validity controller decision."""

    query = packet["query"]
    compact_packet = packet.get("compact_validity_packet", {})
    current = compact_packet.get("current_evidence", [])
    historical = compact_packet.get("historical_evidence", [])
    stale = compact_packet.get("stale_or_blocked_evidence", [])
    excluded = compact_packet.get("excluded_memory_summary", [])
    supporting = compact_packet.get("supporting_evidence", [])

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

    answerability_boundary = validate_answerability_boundary(
        build_answerability_boundary(
            answer_policy=answer_policy,
            evidence_sufficiency=evidence_sufficiency,
            next_action=next_action,
            answer_evidence_ids=answer_ids,
            premise_correction_evidence_ids=[*blocked_ids, *stale_ids],
        )
    )

    return {
        "controller_version": VALIDITY_CONTROLLER_VERSION,
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
        "suggested_retrieval_scope": {
            "entity": str(query.get("entity", "")),
            "slot": str(query.get("slot", "")),
            "temporal_focus": temporal_focus,
            "include_current": include_current,
            "include_archive": include_archive,
            "include_source_history": include_source_history,
        },
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


def build_lifecycle_packets(
    records: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    *,
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    max_current: int = 1,
    max_supporting: int = 2,
    max_stale: int = 2,
    max_excluded: int = 2,
    max_packet_chars: int | None = None,
    include_validity_edges: bool = True,
    include_weak_gate_card: bool = True,
) -> tuple[ValidityAwareMemoryStore, list[dict[str, Any]]]:
    store = ValidityAwareMemoryStore(
        low_confidence_threshold=low_confidence_threshold
    )

    for record in records:
        store.admit(record)

    packets = build_packets_from_store(
        store,
        queries,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    return store, packets


def build_packets_from_store(
    store: ValidityAwareMemoryStore,
    queries: list[dict[str, Any]],
    *,
    max_current: int = 1,
    max_supporting: int = 2,
    max_stale: int = 2,
    max_excluded: int = 2,
    max_packet_chars: int | None = None,
    include_validity_edges: bool = True,
    include_weak_gate_card: bool = True,
) -> list[dict[str, Any]]:
    queries = validate_query_batch(queries)
    budget = validate_retrieval_budget(
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
    )
    max_packet_chars = validate_max_packet_chars(max_packet_chars)
    return [
        store.build_packet(
            query,
            max_current=budget["max_current"],
            max_supporting=budget["max_supporting"],
            max_stale=budget["max_stale"],
            max_excluded=budget["max_excluded"],
            max_packet_chars=max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        for query in queries
    ]


class QVFMemoryPipeline:
    def __init__(
        self,
        store: ValidityAwareMemoryStore | None = None,
        *,
        max_current: int = 1,
        max_supporting: int = 2,
        max_stale: int = 2,
        max_excluded: int = 2,
        max_packet_chars: int | None = None,
        include_validity_edges: bool = True,
        include_weak_gate_card: bool = True,
    ) -> None:
        budget = validate_retrieval_budget(
            max_current=max_current,
            max_supporting=max_supporting,
            max_stale=max_stale,
            max_excluded=max_excluded,
        )
        self.store = store or ValidityAwareMemoryStore()
        self.max_current = budget["max_current"]
        self.max_supporting = budget["max_supporting"]
        self.max_stale = budget["max_stale"]
        self.max_excluded = budget["max_excluded"]
        self.max_packet_chars = validate_max_packet_chars(max_packet_chars)
        self.include_validity_edges = include_validity_edges
        self.include_weak_gate_card = include_weak_gate_card

    @classmethod
    def from_records(
        cls,
        records: list[dict[str, Any]],
        *,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        **kwargs: Any,
    ) -> "QVFMemoryPipeline":
        store = ValidityAwareMemoryStore(
            low_confidence_threshold=low_confidence_threshold
        )
        pipeline = cls(store=store, **kwargs)
        pipeline.admit_records(records)
        return pipeline

    @classmethod
    def from_exported_records(
        cls,
        rows: list[dict[str, Any]],
        *,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        **kwargs: Any,
    ) -> "QVFMemoryPipeline":
        store = ValidityAwareMemoryStore.from_exported_records(
            rows,
            low_confidence_threshold=low_confidence_threshold,
        )
        return cls(store=store, **kwargs)

    @classmethod
    def from_store_file(
        cls,
        path: Path,
        *,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        **kwargs: Any,
    ) -> "QVFMemoryPipeline":
        return cls.from_exported_records(
            load_jsonl(path),
            low_confidence_threshold=low_confidence_threshold,
            **kwargs,
        )

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "QVFMemoryPipeline":
        if not isinstance(state, dict):
            raise ValueError("pipeline state must be an object")
        config = state.get("config")
        if not isinstance(config, dict):
            raise ValueError("pipeline state.config must be an object")
        records = state.get("memory_store")
        if not isinstance(records, list):
            raise ValueError("pipeline state.memory_store must be a list")
        low_confidence_threshold = config.get(
            "low_confidence_threshold",
            LOW_CONFIDENCE_THRESHOLD,
        )
        pipeline = cls.from_exported_records(
            records,
            low_confidence_threshold=low_confidence_threshold,
            max_current=config.get("max_current", 1),
            max_supporting=config.get("max_supporting", 2),
            max_stale=config.get("max_stale", 2),
            max_excluded=config.get("max_excluded", 2),
            max_packet_chars=config.get("max_packet_chars"),
            include_validity_edges=config.get("include_validity_edges", True),
            include_weak_gate_card=config.get("include_weak_gate_card", True),
        )
        expected_integrity = state.get("store_integrity")
        if expected_integrity is not None and expected_integrity != pipeline.validate_integrity():
            raise ValueError("pipeline state.store_integrity does not match loaded memory_store")
        admission_log = state.get("admission_log", [])
        if not isinstance(admission_log, list):
            raise ValueError("pipeline state.admission_log must be a list")
        pipeline.store.admission_log = deepcopy(admission_log)
        return pipeline

    @classmethod
    def from_state_file(cls, path: Path) -> "QVFMemoryPipeline":
        return cls.from_state(json.loads(path.read_text(encoding="utf-8-sig")))

    def admit(self, record: dict[str, Any]) -> MemoryRecord:
        return self.store.admit(record)

    def admit_records(self, records: list[dict[str, Any]]) -> list[MemoryRecord]:
        return self.store.admit_records(records)

    def admit_records_with_report(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        log_start = len(self.store.admission_log)
        admitted_records = self.store.admit_records(records)
        admission_events = deepcopy(self.store.admission_log[log_start:])
        return {
            "decision": "GO_QVF_LIFECYCLE_WRITE_TIME_ADMISSION_READY_NO_API",
            "execution_mode": "pipeline_incremental_admission_report",
            "records_submitted": len(admitted_records),
            "input_memory_ids": [record.memory_id for record in admitted_records],
            "admission_event_count": len(admission_events),
            "admission_events": admission_events,
            "admission_status_counts": count_rows_by_field(
                admission_events,
                "admission_status",
            ),
            "current_status_counts": count_rows_by_field(
                admission_events,
                "current_status",
            ),
            "evidence_role_counts": count_rows_by_field(
                admission_events,
                "evidence_role",
            ),
            "store_integrity": self.validate_integrity(),
            "api_calls_made": 0,
        }

    def adapt_memory_events(
        self,
        events: list[dict[str, Any]],
        *,
        default_source_confidence: float | None = None,
        default_source_type: str = DEFAULT_EVENT_SOURCE_TYPE,
    ) -> dict[str, Any]:
        source_confidence = (
            self.store.low_confidence_threshold
            if default_source_confidence is None
            else default_source_confidence
        )
        records = normalize_memory_events(
            events,
            default_source_confidence=source_confidence,
            default_source_type=default_source_type,
        )
        return {
            "records": records,
            "summary": build_memory_event_adapter_summary(events, records),
        }

    def admit_memory_events_with_report(
        self,
        events: list[dict[str, Any]],
        *,
        default_source_confidence: float | None = None,
        default_source_type: str = DEFAULT_EVENT_SOURCE_TYPE,
    ) -> dict[str, Any]:
        adapted = self.adapt_memory_events(
            events,
            default_source_confidence=default_source_confidence,
            default_source_type=default_source_type,
        )
        admission_report = self.admit_records_with_report(adapted["records"])
        report = deepcopy(admission_report)
        report["execution_mode"] = "pipeline_memory_event_admission_report"
        report["event_adapter_summary"] = adapted["summary"]
        report["records_submitted_from_events"] = len(adapted["records"])
        report["claim_boundary"] = [
            "This is a no-API write-time memory-event adapter plus QVF admission run.",
            "It normalizes structured memory events before QVF admission; it is not model-accuracy evidence.",
        ]
        return report

    def preview_admission(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        validated_records = validate_memory_batch(records)
        store_integrity_before = self.validate_integrity()
        current_index_before = summarize_memory_store(self.store)["current_index"]
        preview_pipeline = QVFMemoryPipeline.from_state(self.export_state())
        admission_report = preview_pipeline.admit_records_with_report(validated_records)
        store_integrity_after = preview_pipeline.validate_integrity()
        store_diff = build_memory_store_diff(self.store, preview_pipeline.store)
        return {
            "decision": "GO_QVF_LIFECYCLE_ADMISSION_PREVIEW_READY_NO_API",
            "execution_mode": "pipeline_admission_preview",
            "records_submitted": admission_report["records_submitted"],
            "admission_event_count": admission_report["admission_event_count"],
            "state_delta": build_lifecycle_step_delta(
                admission_report,
                {"query_results": []},
            ),
            "admission_report": admission_report,
            "store_integrity_before": store_integrity_before,
            "store_integrity_after": store_integrity_after,
            "store_integrity_delta": build_count_delta(
                store_integrity_before,
                store_integrity_after,
            ),
            "changed_memory_ids": store_diff["changed_memory_ids"],
            "store_diff": store_diff,
            "current_index_before": current_index_before,
            "current_index_after": summarize_memory_store(preview_pipeline.store)[
                "current_index"
            ],
            "original_store_integrity": self.validate_integrity(),
            "api_calls_made": 0,
            "claim_boundary": [
                "This is a no-API admission preview, not model-accuracy evidence.",
                "It runs write-time admission on a cloned store and does not mutate the source pipeline.",
            ],
        }

    def build_packet(self, query: dict[str, Any]) -> dict[str, Any]:
        return self.store.build_packet(
            query,
            max_current=self.max_current,
            max_supporting=self.max_supporting,
            max_stale=self.max_stale,
            max_excluded=self.max_excluded,
            max_packet_chars=self.max_packet_chars,
            include_validity_edges=self.include_validity_edges,
            include_weak_gate_card=self.include_weak_gate_card,
        )

    def inspect_query(self, query: dict[str, Any]) -> dict[str, Any]:
        return inspect_query_against_store(
            self.store,
            query,
            max_current=self.max_current,
            max_supporting=self.max_supporting,
            max_stale=self.max_stale,
            max_excluded=self.max_excluded,
            max_packet_chars=self.max_packet_chars,
            include_validity_edges=self.include_validity_edges,
            include_weak_gate_card=self.include_weak_gate_card,
        )

    def build_packets(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.build_packet(query) for query in validate_query_batch(queries)]

    def build_weak_gate_task_pack(
        self, queries: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        packets = self.build_packets(queries)
        return {
            "packets": packets,
            "weak_gate_tasks": build_weak_gate_tasks(packets),
        }

    def adapt_query_requests(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        queries = normalize_query_requests(requests)
        return {
            "queries": queries,
            "summary": build_query_request_adapter_summary(requests, queries),
        }

    def query(self, query: dict[str, Any]) -> dict[str, Any]:
        packet = self.build_packet(query)
        decision = route_read_time_packet(packet)
        response = render_reader_response(packet, decision)
        return build_query_results([packet], [decision], [response])[0]

    def query_with_weak_gate_output(
        self,
        query: dict[str, Any],
        weak_gate_output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        packet = self.build_packet(query)
        weak_gate_tasks = build_weak_gate_tasks([packet])
        weak_gate_outputs: list[dict[str, Any]] = []
        if weak_gate_output is not None:
            if not isinstance(weak_gate_output, dict):
                raise ValueError("weak_gate_output must be an object or null")
            output = deepcopy(weak_gate_output)
            output.setdefault("query_id", packet["query"]["query_id"])
            weak_gate_outputs = validate_weak_gate_outputs_payload([output])
        read_decisions, adapter_summary = build_read_decisions_from_weak_gate_outputs(
            [packet],
            weak_gate_tasks,
            weak_gate_outputs,
        )
        response = render_reader_response(packet, read_decisions[0])
        result = build_query_results([packet], read_decisions, [response])[0]
        result["weak_gate_tasks"] = weak_gate_tasks
        result["weak_gate_adapter_summary"] = adapter_summary
        return result

    def run_queries_with_weak_gate_outputs(
        self,
        queries: list[dict[str, Any]],
        weak_gate_outputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        weak_gate_outputs = validate_weak_gate_outputs_payload(weak_gate_outputs)
        packets = self.build_packets(queries)
        weak_gate_tasks = build_weak_gate_tasks(packets)
        read_decisions, adapter_summary = build_read_decisions_from_weak_gate_outputs(
            packets,
            weak_gate_tasks,
            weak_gate_outputs,
        )
        reader_responses = build_reader_responses(packets, read_decisions)
        query_results = build_query_results(packets, read_decisions, reader_responses)
        summary = build_read_time_summary(
            packets,
            read_decisions,
            reader_responses,
            [],
        )
        summary.update(
            {
                "decision": "GO_QVF_LIFECYCLE_QUERY_BATCH_READY_NO_API",
                "execution_mode": "pipeline_query_batch_report_with_weak_gate_outputs",
                "query_count": len(packets),
                "store_integrity": self.validate_integrity(),
                "retrieval_budget": {
                    "max_current": self.max_current,
                    "max_supporting": self.max_supporting,
                    "max_stale": self.max_stale,
                    "max_excluded": self.max_excluded,
                    "max_packet_chars": self.max_packet_chars,
                    "include_validity_edges": self.include_validity_edges,
                    "include_weak_gate_card": self.include_weak_gate_card,
                },
                "weak_gate_adapter_summary": adapter_summary,
            }
        )
        return {
            "packets": packets,
            "weak_gate_tasks": weak_gate_tasks,
            "read_decisions": read_decisions,
            "reader_responses": reader_responses,
            "query_results": query_results,
            "weak_gate_adapter_summary": adapter_summary,
            "summary": summary,
        }

    def run_queries_with_report(self, queries: list[dict[str, Any]]) -> dict[str, Any]:
        packets = self.build_packets(queries)
        read_decisions = build_read_decisions(packets)
        reader_responses = build_reader_responses(packets, read_decisions)
        query_results = build_query_results(packets, read_decisions, reader_responses)
        summary = build_read_time_summary(
            packets,
            read_decisions,
            reader_responses,
            [],
        )
        summary.update(
            {
                "decision": "GO_QVF_LIFECYCLE_QUERY_BATCH_READY_NO_API",
                "execution_mode": "pipeline_query_batch_report",
                "query_count": len(packets),
                "store_integrity": self.validate_integrity(),
                "retrieval_budget": {
                    "max_current": self.max_current,
                    "max_supporting": self.max_supporting,
                    "max_stale": self.max_stale,
                    "max_excluded": self.max_excluded,
                    "max_packet_chars": self.max_packet_chars,
                    "include_validity_edges": self.include_validity_edges,
                    "include_weak_gate_card": self.include_weak_gate_card,
                },
            }
        )
        return {
            "packets": packets,
            "read_decisions": read_decisions,
            "reader_responses": reader_responses,
            "query_results": query_results,
            "summary": summary,
        }

    def run_query_requests_with_report(
        self, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        adapted = self.adapt_query_requests(requests)
        report = self.run_queries_with_report(adapted["queries"])
        report["query_request_adapter_summary"] = adapted["summary"]
        report["summary"]["query_request_adapter_summary"] = adapted["summary"]
        report["summary"]["execution_mode"] = "pipeline_query_request_batch_report"
        return report

    def run_validity_admission_step(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if records is not None and not isinstance(records, list):
            raise ValueError("records must be a list")
        if queries is not None and not isinstance(queries, list):
            raise ValueError("queries must be a list")
        weak_gate_outputs = validate_weak_gate_outputs_payload(
            weak_gate_outputs,
            optional=True,
        )
        validated_records = validate_memory_batch(records or [])
        validated_queries = validate_query_batch(queries or [])
        step_id = validate_step_id(step_id)
        store_integrity_before = self.validate_integrity()
        admission_report = self.admit_records_with_report(validated_records)
        if weak_gate_outputs is None:
            query_report = self.run_queries_with_report(validated_queries)
            query_mode = "deterministic_router"
        else:
            query_report = self.run_queries_with_weak_gate_outputs(
                validated_queries,
                weak_gate_outputs,
            )
            query_mode = "weak_gate_output_adapter"
        store_integrity_after = self.validate_integrity()
        step_report = {
            "decision": "GO_QVF_LIFECYCLE_STEP_READY_NO_API",
            "execution_mode": "pipeline_lifecycle_step",
            "step_id": step_id,
            "records_submitted": admission_report["records_submitted"],
            "admission_event_count": admission_report["admission_event_count"],
            "query_count": query_report["summary"]["query_count"],
            "query_mode": query_mode,
            "state_delta": build_lifecycle_step_delta(
                admission_report,
                query_report,
            ),
            "admission_report": admission_report,
            "query_report": query_report,
            "store_integrity_before": store_integrity_before,
            "store_integrity_after": store_integrity_after,
            "store_integrity_delta": build_count_delta(
                store_integrity_before,
                store_integrity_after,
            ),
            "store_integrity": store_integrity_after,
            "api_calls_made": 0,
        }
        if include_state:
            step_report["state"] = self.export_state()
        return step_report

    def run_validity_admission_event_step(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        records: list[dict[str, Any]] | None = None,
        query_requests: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if events is not None and not isinstance(events, list):
            raise ValueError("events must be a list")
        if records is not None and not isinstance(records, list):
            raise ValueError("records must be a list")
        if query_requests is not None and not isinstance(query_requests, list):
            raise ValueError("query_requests must be a list")
        explicit_records = validate_memory_batch(records or [])
        adapted = self.adapt_memory_events(events or [])
        combined_records = explicit_records + adapted["records"]
        explicit_queries = validate_query_batch(queries or [])
        adapted_queries = self.adapt_query_requests(query_requests or [])
        combined_queries = explicit_queries + adapted_queries["queries"]
        step_report = self.run_validity_admission_step(
            records=combined_records,
            queries=combined_queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state,
            step_id=step_id,
        )
        if events is not None:
            step_report["event_adapter_summary"] = adapted["summary"]
            step_report["records_submitted_from_events"] = len(adapted["records"])
            step_report["records_submitted_from_records"] = len(explicit_records)
            step_report["claim_boundary"] = [
                "This is a no-API lifecycle event step, not model-accuracy evidence.",
                "Structured memory events are normalized before write-time QVF admission and read-time routing.",
            ]
        if query_requests is not None:
            step_report["query_request_adapter_summary"] = adapted_queries["summary"]
            step_report["queries_submitted_from_requests"] = len(adapted_queries["queries"])
            step_report["queries_submitted_from_queries"] = len(explicit_queries)
        return step_report

    def preview_validity_admission_step(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        store_integrity_before = self.validate_integrity()
        preview_pipeline = QVFMemoryPipeline.from_state(self.export_state())
        step_report = preview_pipeline.run_validity_admission_step(
            records=records,
            queries=queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state,
            step_id=step_id,
        )
        store_diff = build_memory_store_diff(self.store, preview_pipeline.store)
        step_report["decision"] = "GO_QVF_LIFECYCLE_STEP_PREVIEW_READY_NO_API"
        step_report["execution_mode"] = "pipeline_lifecycle_step_preview"
        step_report["changed_memory_ids"] = store_diff["changed_memory_ids"]
        step_report["store_diff"] = store_diff
        step_report["preview_does_not_mutate_source"] = True
        step_report["original_store_integrity"] = self.validate_integrity()
        step_report["source_store_unchanged"] = (
            step_report["original_store_integrity"] == store_integrity_before
        )
        step_report["claim_boundary"] = [
            "This is a no-API lifecycle step preview, not model-accuracy evidence.",
            "It runs write-time admission and deterministic read-time QVF on a cloned store.",
            "The source pipeline is not mutated by the preview.",
        ]
        return step_report

    def preview_validity_admission_event_step(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        records: list[dict[str, Any]] | None = None,
        query_requests: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if events is not None and not isinstance(events, list):
            raise ValueError("events must be a list")
        if records is not None and not isinstance(records, list):
            raise ValueError("records must be a list")
        if query_requests is not None and not isinstance(query_requests, list):
            raise ValueError("query_requests must be a list")
        explicit_records = validate_memory_batch(records or [])
        adapted = self.adapt_memory_events(events or [])
        combined_records = explicit_records + adapted["records"]
        explicit_queries = validate_query_batch(queries or [])
        adapted_queries = self.adapt_query_requests(query_requests or [])
        combined_queries = explicit_queries + adapted_queries["queries"]
        step_report = self.preview_validity_admission_step(
            records=combined_records,
            queries=combined_queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state,
            step_id=step_id,
        )
        if events is not None:
            step_report["event_adapter_summary"] = adapted["summary"]
            step_report["records_submitted_from_events"] = len(adapted["records"])
            step_report["records_submitted_from_records"] = len(explicit_records)
            step_report["claim_boundary"] = [
                "This is a no-API lifecycle event-step preview, not model-accuracy evidence.",
                "Structured memory events are normalized on a cloned store before QVF admission/read-time routing.",
                "The source pipeline is not mutated by the preview.",
            ]
        if query_requests is not None:
            step_report["query_request_adapter_summary"] = adapted_queries["summary"]
            step_report["queries_submitted_from_requests"] = len(adapted_queries["queries"])
            step_report["queries_submitted_from_queries"] = len(explicit_queries)
        return step_report

    def run_validity_admission_step_request(self, request: dict[str, Any]) -> dict[str, Any]:
        validated_request = validate_lifecycle_step_request_payload(request)
        return self.run_validity_admission_event_step(
            events=validated_request["events"] or None,
            records=validated_request["records"],
            query_requests=validated_request["query_requests"] or None,
            queries=validated_request["queries"],
            weak_gate_outputs=validated_request["weak_gate_outputs"],
            include_state=validated_request["include_state"],
            step_id=validated_request["step_id"],
        )

    def run_validity_admission_steps(
        self,
        requests: list[dict[str, Any]],
        *,
        include_final_state: bool = False,
        transactional: bool = True,
    ) -> dict[str, Any]:
        validated_requests = validate_lifecycle_step_requests_payload(requests)
        if not isinstance(include_final_state, bool):
            raise ValueError("include_final_state must be a boolean")
        if not isinstance(transactional, bool):
            raise ValueError("transactional must be a boolean")

        working_pipeline = (
            QVFMemoryPipeline.from_state(self.export_state())
            if transactional
            else self
        )
        store_integrity_before = self.validate_integrity()
        step_reports: list[dict[str, Any]] = []
        for index, request in enumerate(validated_requests):
            step_report = working_pipeline.run_validity_admission_event_step(
                events=request["events"] or None,
                records=request["records"],
                query_requests=request["query_requests"] or None,
                queries=request["queries"],
                weak_gate_outputs=request["weak_gate_outputs"],
                include_state=request["include_state"],
                step_id=request["step_id"],
            )
            step_report["batch_step_index"] = index
            step_reports.append(step_report)

        if transactional:
            self.store = working_pipeline.store

        store_integrity_after = self.validate_integrity()
        summary = {
            "decision": "GO_QVF_LIFECYCLE_MULTI_STEP_READY_NO_API",
            "execution_mode": "pipeline_lifecycle_multi_step",
            "transactional": transactional,
            "step_count": len(step_reports),
            "step_ids": [report["step_id"] for report in step_reports],
            "event_count": sum(
                report.get("event_adapter_summary", {}).get("event_count", 0)
                for report in step_reports
            ),
            "event_record_count": sum(
                report.get("event_adapter_summary", {}).get("normalized_record_count", 0)
                for report in step_reports
            ),
            "query_request_count": sum(
                report.get("query_request_adapter_summary", {}).get("request_count", 0)
                for report in step_reports
            ),
            "query_request_record_count": sum(
                report.get("query_request_adapter_summary", {}).get(
                    "normalized_query_count",
                    0,
                )
                for report in step_reports
            ),
            "records_submitted": sum(report["records_submitted"] for report in step_reports),
            "admission_event_count": sum(
                report["admission_event_count"] for report in step_reports
            ),
            "query_count": sum(report["query_count"] for report in step_reports),
            "query_mode_counts": count_rows_by_field(step_reports, "query_mode"),
            "store_integrity_before": store_integrity_before,
            "store_integrity_after": store_integrity_after,
            "store_integrity_delta": build_count_delta(
                store_integrity_before,
                store_integrity_after,
            ),
            "store_integrity": store_integrity_after,
            "api_calls_made": 0,
        }
        result = {
            "decision": summary["decision"],
            "execution_mode": summary["execution_mode"],
            "steps": step_reports,
            "summary": summary,
        }
        if include_final_state:
            result["state"] = self.export_state()
        return result

    # Backward-compatible aliases for historical local scripts and aggregate-result lineage.
    def run_lifecycle_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.run_validity_admission_step(**kwargs)

    def run_lifecycle_event_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.run_validity_admission_event_step(**kwargs)

    def preview_lifecycle_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.preview_validity_admission_step(**kwargs)

    def preview_lifecycle_event_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.preview_validity_admission_event_step(**kwargs)

    def run_lifecycle_step_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.run_validity_admission_step_request(request)

    def run_lifecycle_steps(
        self,
        requests: list[dict[str, Any]],
        *,
        include_final_state: bool = False,
        transactional: bool = True,
    ) -> dict[str, Any]:
        return self.run_validity_admission_steps(
            requests,
            include_final_state=include_final_state,
            transactional=transactional,
        )

    def run_queries(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.run_queries_with_report(queries)["query_results"]

    def summarize_store(self) -> dict[str, Any]:
        return summarize_memory_store(self.store)

    def inspect_memory(self, memory_id: str) -> dict[str, Any]:
        return inspect_memory_store_record(self.store, memory_id)

    def inspect_scope(
        self,
        entity: str,
        slot: str,
        *,
        namespace: str = "",
        tenant_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        return inspect_memory_scope(
            self.store,
            entity,
            slot,
            namespace=namespace,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    def validate_integrity(self) -> dict[str, int]:
        return self.store.validate_integrity()

    def export_memory_store(self) -> list[dict[str, Any]]:
        return self.store.export_memory_store()

    def save_memory_store(self, path: Path) -> None:
        write_jsonl(path, self.export_memory_store())

    def export_state(self) -> dict[str, Any]:
        return {
            "state_version": "qvf_validity_admission_pipeline_state_v0.1_no_api",
            "policy_version": POLICY_VERSION,
            "router_version": ROUTER_VERSION,
            "reader_version": READER_VERSION,
            "config": {
                "low_confidence_threshold": self.store.low_confidence_threshold,
                "max_current": self.max_current,
                "max_supporting": self.max_supporting,
                "max_stale": self.max_stale,
                "max_excluded": self.max_excluded,
                "max_packet_chars": self.max_packet_chars,
                "include_validity_edges": self.include_validity_edges,
                "include_weak_gate_card": self.include_weak_gate_card,
            },
            "store_integrity": self.validate_integrity(),
            "memory_store": self.export_memory_store(),
            "admission_log": deepcopy(self.store.admission_log),
            "api_calls_made": 0,
            "claim_boundary": [
                "This state snapshot contains lifecycle QVF memory metadata, not model-run evidence.",
                "Raw prompts, target outputs, judge traces, and secrets are intentionally excluded.",
            ],
        }

    def save_state(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.export_state(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_qvf_service_pipeline(request: dict[str, Any]) -> tuple[QVFMemoryPipeline, str]:
    validated_request = validate_qvf_service_request_payload(request)
    config = validated_request["config"]
    pipeline_kwargs = {
        field_name: config[field_name]
        for field_name in [
            "max_current",
            "max_supporting",
            "max_stale",
            "max_excluded",
            "max_packet_chars",
            "include_validity_edges",
            "include_weak_gate_card",
        ]
        if field_name in config
    }
    if validated_request["state"] is not None:
        return QVFMemoryPipeline.from_state(validated_request["state"]), "service_state"
    if validated_request["memory_store"]:
        return (
            QVFMemoryPipeline.from_exported_records(
                validated_request["memory_store"],
                low_confidence_threshold=config.get(
                    "low_confidence_threshold",
                    LOW_CONFIDENCE_THRESHOLD,
                ),
                **pipeline_kwargs,
            ),
            "service_memory_store",
        )
    return (
        QVFMemoryPipeline.from_records(
            [],
            low_confidence_threshold=config.get(
                "low_confidence_threshold",
                LOW_CONFIDENCE_THRESHOLD,
            ),
            **pipeline_kwargs,
        ),
        "service_empty_store",
    )


def run_qvf_service_request(request: dict[str, Any]) -> dict[str, Any]:
    validated_request = validate_qvf_service_request_payload(request)
    pipeline, input_mode = build_qvf_service_pipeline(validated_request)
    step_runner = (
        pipeline.preview_validity_admission_event_step
        if validated_request["preview"]
        else pipeline.run_validity_admission_event_step
    )
    step_report = step_runner(
        events=validated_request["events"] or None,
        records=validated_request["records"],
        query_requests=validated_request["query_requests"] or None,
        queries=validated_request["queries"],
        weak_gate_outputs=validated_request["weak_gate_outputs"],
        include_state=validated_request["include_state"],
        step_id=validated_request["step_id"],
    )
    response = {
        "decision": (
            "GO_QVF_SERVICE_PREVIEW_READY_NO_API"
            if validated_request["preview"]
            else "GO_QVF_SERVICE_REQUEST_READY_NO_API"
        ),
        "execution_mode": "qvf_service_request",
        "request_id": validated_request["request_id"],
        "step_id": step_report["step_id"],
        "input_mode": input_mode,
        "preview": validated_request["preview"],
        "state_returned": validated_request["include_state"],
        "step_report": step_report,
        "summary": build_qvf_service_summary(
            validated_request,
            step_report,
            input_mode=input_mode,
            output_files=[],
        ),
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API service adapter around QVF validity-admission memory metadata.",
            "It consumes structured events/records/queries/read requests; it does not infer fields from raw text.",
            "It is an integration contract and engineering readiness evidence, not model-accuracy evidence.",
        ],
    }
    if validated_request["include_state"]:
        response["state"] = step_report.get("state") or pipeline.export_state()
    return response


def build_qvf_service_summary(
    request: dict[str, Any],
    step_report: dict[str, Any],
    *,
    input_mode: str,
    output_files: list[str],
) -> dict[str, Any]:
    query_summary = step_report.get("query_report", {}).get("summary", {})
    summary = {
        "decision": (
            "GO_QVF_SERVICE_PREVIEW_READY_NO_API"
            if request["preview"]
            else "GO_QVF_SERVICE_REQUEST_READY_NO_API"
        ),
        "execution_mode": "qvf_service_request_summary",
        "request_id": request["request_id"],
        "step_id": step_report["step_id"],
        "input_mode": input_mode,
        "preview": request["preview"],
        "records_submitted": step_report["records_submitted"],
        "admission_event_count": step_report["admission_event_count"],
        "query_count": step_report["query_count"],
        "query_mode": step_report["query_mode"],
        "read_decision_counts": query_summary.get("read_decision_counts", {}),
        "reader_answer_policy_counts": query_summary.get(
            "reader_answer_policy_counts",
            {},
        ),
        "store_integrity_before": step_report["store_integrity_before"],
        "store_integrity_after": step_report["store_integrity_after"],
        "store_integrity_delta": step_report["store_integrity_delta"],
        "state_returned": request["include_state"],
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This summary is for a no-API QVF service request run.",
            "It reports deterministic lifecycle/routing behavior, not target-model accuracy.",
        ],
    }
    for field_name in [
        "event_adapter_summary",
        "query_request_adapter_summary",
        "records_submitted_from_events",
        "records_submitted_from_records",
        "queries_submitted_from_requests",
        "queries_submitted_from_queries",
        "changed_memory_ids",
        "source_store_unchanged",
    ]:
        if field_name in step_report:
            summary[field_name] = step_report[field_name]
    return summary


def build_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    read_decisions: list[dict[str, Any]],
    reader_responses: list[dict[str, Any]],
    output_files: list[str],
    *,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_MEMORY_ADMISSION_PROTOTYPE_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "input_mode": input_mode,
        "records_loaded": len(records),
        "append_records_loaded": append_records_loaded,
        "store_records_loaded": len(store.records),
        "store_integrity": store.validate_integrity(),
        "queries_loaded": len(queries),
        "low_confidence_threshold": store.low_confidence_threshold,
        "retrieval_budget": {
            "max_current": max_current,
            "max_supporting": max_supporting,
            "max_stale": max_stale,
            "max_excluded": max_excluded,
            "max_packet_chars": max_packet_chars,
            "include_validity_edges": include_validity_edges,
            "include_weak_gate_card": include_weak_gate_card,
        },
        "admission_status_counts": {},
        "current_status_counts": {},
        "evidence_role_counts": {},
        "read_decision_counts": {},
        "read_route_counts": {},
        "reader_answer_policy_counts": {},
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API architecture readiness check, not new model-accuracy evidence.",
            "Write-time lifecycle scaffolding is outside the promoted post-retrieval QVF controller claim.",
            "Weak-gate cards are routing/gating scaffolds for weaker readers, not standalone full-answer readers.",
            "Benchmark accuracy evidence must come from separate frozen evaluation artifacts.",
        ],
    }

    for record in store.records.values():
        summary["admission_status_counts"][record.admission_status] = (
            summary["admission_status_counts"].get(record.admission_status, 0) + 1
        )
        summary["current_status_counts"][record.current_status] = (
            summary["current_status_counts"].get(record.current_status, 0) + 1
        )
        summary["evidence_role_counts"][record.evidence_role] = (
            summary["evidence_role_counts"].get(record.evidence_role, 0) + 1
        )
    for decision in read_decisions:
        summary["read_decision_counts"][decision["decision"]] = (
            summary["read_decision_counts"].get(decision["decision"], 0) + 1
        )
        summary["read_route_counts"][decision["route"]] = (
            summary["read_route_counts"].get(decision["route"], 0) + 1
        )
    for response in reader_responses:
        summary["reader_answer_policy_counts"][response["answer_policy"]] = (
            summary["reader_answer_policy_counts"].get(response["answer_policy"], 0) + 1
        )
    return summary


def summarize_memory_store(store: ValidityAwareMemoryStore) -> dict[str, Any]:
    exported = store.export_memory_store()
    current_index = [
        {
            "namespace": scoped_key[0],
            "tenant_id": scoped_key[1],
            "user_id": scoped_key[2],
            "entity": scoped_key[3],
            "slot": scoped_key[4],
            "memory_id": memory_id,
        }
        for scoped_key, memory_id in sorted(store.current_by_key.items())
    ]
    source_type_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    entity_slot_counts: dict[str, int] = {}
    for row in exported:
        source_type = str(row.get("source", {}).get("source_type", ""))
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        scope = row.get("scope", {}) or {}
        scope_key = "::".join(
            [
                norm(str(scope.get("namespace", ""))),
                norm(str(scope.get("tenant_id", ""))),
                norm(str(scope.get("user_id", ""))),
            ]
        )
        scope_counts[scope_key] = scope_counts.get(scope_key, 0) + 1
        entity_slot_key = "::".join([norm(str(row["entity"])), norm(str(row["slot"]))])
        entity_slot_counts[entity_slot_key] = entity_slot_counts.get(entity_slot_key, 0) + 1
    return {
        "decision": "GO_QVF_LIFECYCLE_STORE_SUMMARY_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "execution_mode": "store_summary_only",
        "store_integrity": store.validate_integrity(),
        "memory_store_records": len(exported),
        "current_index": current_index,
        "admission_status_counts": count_rows_by_field(exported, "admission_status"),
        "current_status_counts": count_rows_by_field(exported, "current_status"),
        "evidence_role_counts": count_rows_by_field(exported, "evidence_role"),
        "memory_ids_by_admission_status": group_memory_ids_by_field(
            exported,
            "admission_status",
        ),
        "memory_ids_by_current_status": group_memory_ids_by_field(
            exported,
            "current_status",
        ),
        "memory_ids_by_evidence_role": group_memory_ids_by_field(
            exported,
            "evidence_role",
        ),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "entity_slot_counts": dict(sorted(entity_slot_counts.items())),
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API lifecycle store summary, not model-accuracy evidence.",
            "It reports persisted validity metadata and current-index state for integration checks.",
        ],
    }


def group_memory_ids_by_field(
    rows: list[dict[str, Any]],
    field_name: str,
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        key = str(row.get(field_name, ""))
        grouped.setdefault(key, []).append(str(row["memory_id"]))
    return {
        key: sorted(memory_ids)
        for key, memory_ids in sorted(grouped.items())
    }


def build_scoped_key(
    entity: str,
    slot: str,
    *,
    namespace: str = "",
    tenant_id: str = "",
    user_id: str = "",
) -> tuple[str, str, str, str, str]:
    if not isinstance(entity, str) or not entity.strip():
        raise ValueError("scope inspection entity must be a non-empty string")
    if not isinstance(slot, str) or not slot.strip():
        raise ValueError("scope inspection slot must be a non-empty string")
    for field_name, value in {
        "namespace": namespace,
        "tenant_id": tenant_id,
        "user_id": user_id,
    }.items():
        if not isinstance(value, str):
            raise ValueError(f"scope inspection {field_name} must be a string")
    return (
        norm(namespace),
        norm(tenant_id),
        norm(user_id),
        norm(entity),
        norm(slot),
    )


def inspect_memory_scope(
    store: ValidityAwareMemoryStore,
    entity: str,
    slot: str,
    *,
    namespace: str = "",
    tenant_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    scoped_key = build_scoped_key(
        entity,
        slot,
        namespace=namespace,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    records = sorted(
        [
            record
            for record in store.records.values()
            if record.scoped_key == scoped_key
        ],
        key=lambda record: (record.observed_at.isoformat(), record.memory_id),
    )
    scoped_ids = {record.memory_id for record in records}
    current_index_memory_id = store.current_by_key.get(scoped_key)
    current_record = (
        store.records[current_index_memory_id].to_public_dict()
        if current_index_memory_id is not None
        else None
    )
    in_scope_edges = [
        {
            "source": record.memory_id,
            "target": target_id,
            "type": edge_type,
        }
        for record in records
        for edge_type, targets in record.links.items()
        for target_id in targets
        if target_id in scoped_ids
    ]
    history = [
        {
            "memory_id": record.memory_id,
            "value": record.value,
            "observed_at": record.observed_at.isoformat(),
            "admission_status": record.admission_status,
            "current_status": record.current_status,
            "evidence_role": record.evidence_role,
            "source_id": record.source_id,
            "source_type": record.source_type,
            "source_confidence": record.source_confidence,
            "validity_action": record.payload.get("validity_action"),
            "links": deepcopy(record.links),
        }
        for record in records
    ]
    return {
        "decision": "GO_QVF_LIFECYCLE_SCOPE_INSPECTION_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "execution_mode": "scope_inspection_only",
        "scoped_key": {
            "namespace": scoped_key[0],
            "tenant_id": scoped_key[1],
            "user_id": scoped_key[2],
            "entity": scoped_key[3],
            "slot": scoped_key[4],
        },
        "normalized_scoped_key": "::".join(scoped_key),
        "record_count": len(records),
        "history_memory_ids": [record.memory_id for record in records],
        "current_index_memory_id": current_index_memory_id,
        "current_record": current_record,
        "history": history,
        "in_scope_edges": sorted(
            in_scope_edges,
            key=lambda edge: (edge["source"], edge["type"], edge["target"]),
        ),
        "admission_status_counts": count_rows_by_field(
            [record.to_public_dict() for record in records],
            "admission_status",
        ),
        "current_status_counts": count_rows_by_field(
            [record.to_public_dict() for record in records],
            "current_status",
        ),
        "evidence_role_counts": count_rows_by_field(
            [record.to_public_dict() for record in records],
            "evidence_role",
        ),
        "store_integrity": store.validate_integrity(),
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API lifecycle scope inspection, not model-accuracy evidence.",
            "It reports persisted validity history for one normalized entity-slot scope.",
        ],
    }


def inspect_memory_store_record(
    store: ValidityAwareMemoryStore,
    memory_id: str,
) -> dict[str, Any]:
    if not isinstance(memory_id, str) or not memory_id.strip():
        raise ValueError("memory_id must be a non-empty string")
    normalized_memory_id = memory_id.strip()
    record = store.records.get(normalized_memory_id)
    if record is None:
        raise ValueError(f"Unknown memory_id: {normalized_memory_id}")

    outbound_links = [
        {
            "source": record.memory_id,
            "target": target_id,
            "type": edge_type,
        }
        for edge_type, targets in record.links.items()
        for target_id in targets
    ]
    inbound_links = [
        {
            "source": source.memory_id,
            "target": record.memory_id,
            "type": edge_type,
        }
        for source in store.records.values()
        for edge_type, targets in source.links.items()
        if record.memory_id in targets
    ]
    current_index_memory_id = store.current_by_key.get(record.scoped_key)
    same_scoped_key_memory_ids = sorted(
        candidate.memory_id
        for candidate in store.records.values()
        if candidate.scoped_key == record.scoped_key
    )
    return {
        "decision": "GO_QVF_LIFECYCLE_MEMORY_INSPECTION_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "execution_mode": "memory_inspection_only",
        "memory_id": record.memory_id,
        "record": record.to_public_dict(),
        "current_index_memory_id": current_index_memory_id,
        "is_current_index_target": current_index_memory_id == record.memory_id,
        "same_scoped_key_memory_ids": same_scoped_key_memory_ids,
        "outbound_links": sorted(
            outbound_links,
            key=lambda edge: (edge["type"], edge["target"]),
        ),
        "inbound_links": sorted(
            inbound_links,
            key=lambda edge: (edge["type"], edge["source"]),
        ),
        "store_integrity": store.validate_integrity(),
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API lifecycle memory inspection, not model-accuracy evidence.",
            "It reports persisted validity metadata and link/index state for one memory record.",
        ],
    }


def build_memory_inspection_cli_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    memory_id: str,
    output_files: list[str],
    *,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    summary = inspect_memory_store_record(store, memory_id)
    summary.update(
        {
            "input_mode": input_mode,
            "records_loaded": len(records),
            "append_records_loaded": append_records_loaded,
            "output_files": output_files,
        }
    )
    return summary


def build_scope_inspection_cli_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    entity: str,
    slot: str,
    namespace: str = "",
    tenant_id: str = "",
    user_id: str = "",
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    summary = inspect_memory_scope(
        store,
        entity,
        slot,
        namespace=namespace,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    summary.update(
        {
            "input_mode": input_mode,
            "records_loaded": len(records),
            "append_records_loaded": append_records_loaded,
            "output_files": output_files,
        }
    )
    return summary


def selected_packet_memory_ids(packet: dict[str, Any]) -> dict[str, list[str]]:
    compact_packet = packet.get("compact_validity_packet", {})
    if not isinstance(compact_packet, dict):
        return {bucket_name: [] for bucket_name in PACKET_EVIDENCE_BUCKETS}
    selected: dict[str, list[str]] = {}
    for bucket_name in PACKET_EVIDENCE_BUCKETS:
        rows = compact_packet.get(bucket_name, [])
        if not isinstance(rows, list):
            selected[bucket_name] = []
            continue
        selected[bucket_name] = [
            str(row["memory_id"])
            for row in rows
            if isinstance(row, dict) and "memory_id" in row
        ]
    return selected


def inspect_query_against_store(
    store: ValidityAwareMemoryStore,
    query: dict[str, Any],
    *,
    max_current: int = 1,
    max_supporting: int = 2,
    max_stale: int = 2,
    max_excluded: int = 2,
    max_packet_chars: int | None = None,
    include_validity_edges: bool = True,
    include_weak_gate_card: bool = True,
) -> dict[str, Any]:
    packet = store.build_packet(
        query,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    read_decision = route_read_time_packet(packet)
    reader_response = render_reader_response(packet, read_decision)
    compact_packet = packet.get("compact_validity_packet", {})
    validity_edges = (
        compact_packet.get("validity_edges", [])
        if isinstance(compact_packet, dict)
        else []
    )
    return {
        "decision": "GO_QVF_LIFECYCLE_QUERY_INSPECTION_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "router_version": ROUTER_VERSION,
        "reader_version": READER_VERSION,
        "execution_mode": "query_inspection_only",
        "query_id": packet["query"]["query_id"],
        "query": packet["query"],
        "expected_read_time_decision": packet.get("expected_read_time_decision"),
        "read_decision": read_decision,
        "reader_response": reader_response,
        "selected_memory_ids_by_bucket": selected_packet_memory_ids(packet),
        "retrieval_diagnostics": packet.get("retrieval_diagnostics", {}),
        "validity_edge_count": len(validity_edges) if isinstance(validity_edges, list) else 0,
        "weak_gate_card_present": "weak_conservative_gate_card" in packet,
        "token_budget_proxy": packet.get("token_budget_proxy", {}),
        "packet": packet,
        "store_integrity": store.validate_integrity(),
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API query inspection, not model-accuracy evidence.",
            "It reuses the deterministic QVF packet, router, and renderer path for one query.",
        ],
    }


def select_query_by_id(queries: list[dict[str, Any]], query_id: str) -> dict[str, Any]:
    if not isinstance(query_id, str) or not query_id.strip():
        raise ValueError("query_id must be a non-empty string")
    normalized_query_id = query_id.strip()
    validated_queries = validate_query_batch(queries)
    for query in validated_queries:
        if query["query_id"] == normalized_query_id:
            return query
    raise ValueError(f"Unknown query_id: {normalized_query_id}")


def build_query_inspection_cli_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    query_id: str,
    output_files: list[str],
    *,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    query = select_query_by_id(queries, query_id)
    summary = inspect_query_against_store(
        store,
        query,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    summary.update(
        {
            "input_mode": input_mode,
            "records_loaded": len(records),
            "append_records_loaded": append_records_loaded,
            "queries_loaded": len(queries),
            "output_files": output_files,
        }
    )
    return summary


def build_store_summary_cli_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    summary = summarize_memory_store(store)
    summary.update(
        {
            "input_mode": input_mode,
            "records_loaded": len(records),
            "append_records_loaded": append_records_loaded,
            "output_files": output_files,
        }
    )
    return summary


def maybe_write_pipeline_state(
    state_out: Path | None,
    store: ValidityAwareMemoryStore,
    *,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
) -> list[str]:
    if state_out is None:
        return []
    pipeline = QVFMemoryPipeline(
        store=store,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    pipeline.save_state(state_out)
    return [state_out.name]


def build_store_validation_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    return {
        "decision": "GO_QVF_LIFECYCLE_STORE_INTEGRITY_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "input_mode": input_mode,
        "validation_mode": "store_integrity_only",
        "records_loaded": len(records),
        "append_records_loaded": append_records_loaded,
        "store_records_loaded": len(store.records),
        "store_integrity": store.validate_integrity(),
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API store integrity check, not model-accuracy evidence.",
            "It validates lifecycle memory-store invariants before read-time packet construction.",
        ],
    }


def build_state_validation_summary(
    pipeline: QVFMemoryPipeline,
    output_files: list[str],
    *,
    input_mode: str,
) -> dict[str, Any]:
    state = pipeline.export_state()
    return {
        "decision": "GO_QVF_LIFECYCLE_PIPELINE_STATE_READY_NO_API",
        "execution_mode": "pipeline_state_validation_only",
        "input_mode": input_mode,
        "state_version": state["state_version"],
        "policy_version": POLICY_VERSION,
        "store_integrity": state["store_integrity"],
        "config": state["config"],
        "memory_store_records": len(state["memory_store"]),
        "admission_log_rows": len(state["admission_log"]),
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API pipeline-state validation, not model-accuracy evidence.",
            "It validates saved lifecycle QVF memory metadata and configuration only.",
        ],
    }


def build_method_lock_summary(
    output_files: list[str],
    *,
    low_confidence_threshold: float,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
) -> dict[str, Any]:
    source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    method_config = {
        "low_confidence_threshold": low_confidence_threshold,
        "max_current": max_current,
        "max_supporting": max_supporting,
        "max_stale": max_stale,
        "max_excluded": max_excluded,
        "max_packet_chars": max_packet_chars,
        "include_validity_edges": include_validity_edges,
        "include_weak_gate_card": include_weak_gate_card,
    }
    method_signature_payload = {
        "policy_version": POLICY_VERSION,
        "router_version": ROUTER_VERSION,
        "reader_version": READER_VERSION,
        "method_config": method_config,
        "source_file_sha256": source_sha256,
    }
    signature_blob = json.dumps(
        method_signature_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "decision": "GO_QVF_LIFECYCLE_METHOD_LOCK_READY_NO_API",
        "execution_mode": "method_lock_export_only",
        "policy_version": POLICY_VERSION,
        "router_version": ROUTER_VERSION,
        "reader_version": READER_VERSION,
        "method_config": method_config,
        "source_fingerprint": {
            "file_name": Path(__file__).name,
            "sha256": source_sha256,
        },
        "method_signature_sha256": hashlib.sha256(
            signature_blob.encode("utf-8")
        ).hexdigest(),
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API method lock, not model-accuracy evidence.",
            "Use it before held-out or external runs to freeze code and runtime configuration.",
            "If source_fingerprint or method_config changes, do not compare results as the same locked method.",
        ],
    }


def build_method_lock_comparison_summary(
    expected_lock: dict[str, Any],
    output_files: list[str],
    *,
    low_confidence_threshold: float,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
) -> dict[str, Any]:
    if not isinstance(expected_lock, dict):
        raise ValueError("method lock must be a JSON object")
    current_lock = build_method_lock_summary(
        [],
        low_confidence_threshold=low_confidence_threshold,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    expected_config = expected_lock.get("method_config")
    current_config = current_lock["method_config"]
    config_differences = [
        {
            "field": field_name,
            "expected": expected_config.get(field_name)
            if isinstance(expected_config, dict)
            else None,
            "current": current_config.get(field_name),
        }
        for field_name in sorted(
            set(current_config)
            | (set(expected_config) if isinstance(expected_config, dict) else set())
        )
        if not isinstance(expected_config, dict)
        or expected_config.get(field_name) != current_config.get(field_name)
    ]
    expected_signature = expected_lock.get("method_signature_sha256")
    current_signature = current_lock["method_signature_sha256"]
    expected_source_sha = (
        expected_lock.get("source_fingerprint", {}).get("sha256")
        if isinstance(expected_lock.get("source_fingerprint"), dict)
        else None
    )
    current_source_sha = current_lock["source_fingerprint"]["sha256"]
    signature_matches = expected_signature == current_signature
    config_matches = not config_differences
    source_matches = expected_source_sha == current_source_sha
    return {
        "decision": (
            "GO_QVF_LIFECYCLE_METHOD_LOCK_MATCH_NO_API"
            if signature_matches
            else "NO_GO_QVF_LIFECYCLE_METHOD_LOCK_MISMATCH_NO_API"
        ),
        "execution_mode": "method_lock_compare_only",
        "lock_matches": signature_matches,
        "signature_matches": signature_matches,
        "config_matches": config_matches,
        "source_fingerprint_matches": source_matches,
        "expected_method_signature_sha256": expected_signature,
        "current_method_signature_sha256": current_signature,
        "expected_source_sha256": expected_source_sha,
        "current_source_sha256": current_source_sha,
        "config_differences": config_differences,
        "current_lock": current_lock,
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API method-lock comparison, not model-accuracy evidence.",
            "NO_GO means the current code/config should not be compared as the locked method.",
        ],
    }


def enforce_method_lock_match(
    expected_lock: dict[str, Any],
    *,
    low_confidence_threshold: float,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
) -> dict[str, Any]:
    comparison = build_method_lock_comparison_summary(
        expected_lock,
        [],
        low_confidence_threshold=low_confidence_threshold,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    if comparison["lock_matches"]:
        return comparison
    config_fields = ", ".join(
        difference["field"] for difference in comparison["config_differences"]
    )
    if not config_fields:
        config_fields = "none"
    raise ValueError(
        "method lock mismatch; "
        f"signature_matches={comparison['signature_matches']}; "
        f"config_matches={comparison['config_matches']}; "
        f"source_fingerprint_matches={comparison['source_fingerprint_matches']}; "
        f"config_differences={config_fields}"
    )


def build_admission_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_WRITE_TIME_ADMISSION_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "input_mode": input_mode,
        "execution_mode": "write_time_admission_only",
        "records_loaded": len(records),
        "append_records_loaded": append_records_loaded,
        "store_records_loaded": len(store.records),
        "store_integrity": store.validate_integrity(),
        "admission_status_counts": {},
        "current_status_counts": {},
        "evidence_role_counts": {},
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API write-time admission run, not model-accuracy evidence.",
            "It emits an admitted lifecycle memory store for later retrieval-time QVF packet construction.",
        ],
    }
    for record in store.records.values():
        summary["admission_status_counts"][record.admission_status] = (
            summary["admission_status_counts"].get(record.admission_status, 0) + 1
        )
        summary["current_status_counts"][record.current_status] = (
            summary["current_status_counts"].get(record.current_status, 0) + 1
        )
        summary["evidence_role_counts"][record.evidence_role] = (
            summary["evidence_role_counts"].get(record.evidence_role, 0) + 1
        )
    return summary


def build_admission_preview_cli_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    preview_records: list[dict[str, Any]],
    output_files: list[str],
    *,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
    input_mode: str,
) -> dict[str, Any]:
    pipeline = QVFMemoryPipeline(
        store=store,
        max_current=max_current,
        max_supporting=max_supporting,
        max_stale=max_stale,
        max_excluded=max_excluded,
        max_packet_chars=max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    summary = pipeline.preview_admission(preview_records)
    summary.update(
        {
            "input_mode": input_mode,
            "records_loaded": len(records),
            "append_records_loaded": len(preview_records),
            "output_files": output_files,
        }
    )
    return summary


def build_packet_summary(
    store: ValidityAwareMemoryStore,
    records: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    output_files: list[str],
    *,
    max_current: int,
    max_supporting: int,
    max_stale: int,
    max_excluded: int,
    max_packet_chars: int | None,
    include_validity_edges: bool,
    include_weak_gate_card: bool,
    input_mode: str,
    append_records_loaded: int = 0,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_PACKET_BUILD_READY_NO_API",
        "policy_version": POLICY_VERSION,
        "input_mode": input_mode,
        "execution_mode": "retrieval_time_packet_build_only",
        "records_loaded": len(records),
        "append_records_loaded": append_records_loaded,
        "store_records_loaded": len(store.records),
        "store_integrity": store.validate_integrity(),
        "queries_loaded": len(queries),
        "packet_count": len(packets),
        "packet_budget_satisfied_count": 0,
        "packet_budget_unsatisfied_count": 0,
        "weak_gate_card_count": 0,
        "validity_edge_count": 0,
        "retrieval_budget": {
            "max_current": max_current,
            "max_supporting": max_supporting,
            "max_stale": max_stale,
            "max_excluded": max_excluded,
            "max_packet_chars": max_packet_chars,
            "include_validity_edges": include_validity_edges,
            "include_weak_gate_card": include_weak_gate_card,
        },
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API retrieval-time packet build, not model-accuracy evidence.",
            "It emits compact validity packets for downstream QVF reading or external readers.",
        ],
    }
    for packet in packets:
        proxy = packet.get("token_budget_proxy", {})
        if proxy.get("budget_satisfied") is False:
            summary["packet_budget_unsatisfied_count"] += 1
        else:
            summary["packet_budget_satisfied_count"] += 1
        if "weak_conservative_gate_card" in packet:
            summary["weak_gate_card_count"] += 1
        compact_packet = packet.get("compact_validity_packet", {})
        if isinstance(compact_packet, dict):
            edges = compact_packet.get("validity_edges", [])
            if isinstance(edges, list):
                summary["validity_edge_count"] += len(edges)
    return summary


def build_read_time_summary(
    packets: list[dict[str, Any]],
    read_decisions: list[dict[str, Any]],
    reader_responses: list[dict[str, Any]],
    output_files: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_READ_TIME_READER_READY_NO_API",
        "router_version": ROUTER_VERSION,
        "reader_version": READER_VERSION,
        "execution_mode": "read_time_reader_only",
        "packet_count": len(packets),
        "read_decision_counts": {},
        "read_route_counts": {},
        "reader_answer_policy_counts": {},
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API structured read-time reader run, not model-accuracy evidence.",
            "It consumes prebuilt compact validity packets and emits decisions, responses, and query-result bundles.",
        ],
    }
    for decision in read_decisions:
        summary["read_decision_counts"][decision["decision"]] = (
            summary["read_decision_counts"].get(decision["decision"], 0) + 1
        )
        summary["read_route_counts"][decision["route"]] = (
            summary["read_route_counts"].get(decision["route"], 0) + 1
        )
    for response in reader_responses:
        summary["reader_answer_policy_counts"][response["answer_policy"]] = (
            summary["reader_answer_policy_counts"].get(response["answer_policy"], 0) + 1
        )
    return summary


def build_route_summary(
    packets: list[dict[str, Any]],
    read_decisions: list[dict[str, Any]],
    output_files: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_READ_TIME_ROUTER_READY_NO_API",
        "router_version": ROUTER_VERSION,
        "execution_mode": "read_time_router_only",
        "packet_count": len(packets),
        "read_decision_counts": {},
        "read_route_counts": {},
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API structured read-time router run, not model-accuracy evidence.",
            "It consumes prebuilt compact validity packets and emits read-time admission decisions.",
        ],
    }
    for decision in read_decisions:
        summary["read_decision_counts"][decision["decision"]] = (
            summary["read_decision_counts"].get(decision["decision"], 0) + 1
        )
        summary["read_route_counts"][decision["route"]] = (
            summary["read_route_counts"].get(decision["route"], 0) + 1
        )
    return summary


def build_renderer_summary(
    packets: list[dict[str, Any]],
    read_decisions: list[dict[str, Any]],
    reader_responses: list[dict[str, Any]],
    query_results: list[dict[str, Any]],
    output_files: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_READER_RENDERER_READY_NO_API",
        "reader_version": READER_VERSION,
        "execution_mode": "reader_renderer_only",
        "packet_count": len(packets),
        "read_decision_count": len(read_decisions),
        "reader_response_count": len(reader_responses),
        "query_result_count": len(query_results),
        "reader_answer_policy_counts": {},
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API reader renderer run, not model-accuracy evidence.",
            "It consumes prebuilt compact validity packets plus read decisions and emits responses/query-result bundles.",
        ],
    }
    for response in reader_responses:
        summary["reader_answer_policy_counts"][response["answer_policy"]] = (
            summary["reader_answer_policy_counts"].get(response["answer_policy"], 0) + 1
        )
    return summary


def build_weak_gate_pack_summary(
    packets: list[dict[str, Any]],
    weak_gate_tasks: list[dict[str, Any]],
    output_files: list[str],
) -> dict[str, Any]:
    packet_query_ids = [
        packet["query"]["query_id"]
        for packet in packets
        if isinstance(packet.get("query"), dict)
        and isinstance(packet["query"].get("query_id"), str)
    ]
    task_query_ids = [
        task["query_id"]
        for task in weak_gate_tasks
        if isinstance(task, dict) and isinstance(task.get("query_id"), str)
    ]
    task_query_id_set = set(task_query_ids)
    covered_query_ids = [
        query_id for query_id in packet_query_ids if query_id in task_query_id_set
    ]
    skipped_query_ids = [
        query_id for query_id in packet_query_ids if query_id not in task_query_id_set
    ]
    task_size_rows: list[dict[str, Any]] = []
    for task in weak_gate_tasks:
        task_input = task.get("input", {}) if isinstance(task, dict) else {}
        input_blob = json.dumps(task_input, ensure_ascii=False, sort_keys=True)
        task_blob = json.dumps(task, ensure_ascii=False, sort_keys=True)
        task_size_rows.append(
            {
                "task_id": task.get("task_id", "") if isinstance(task, dict) else "",
                "query_id": task.get("query_id", "") if isinstance(task, dict) else "",
                "input_json_chars": len(input_blob),
                "task_json_chars": len(task_blob),
                "input_word_like_tokens": len(input_blob.split()),
                "task_word_like_tokens": len(task_blob.split()),
            }
        )
    largest_tasks = sorted(
        task_size_rows,
        key=lambda row: (row["task_json_chars"], row["task_id"]),
        reverse=True,
    )[:5]
    summary: dict[str, Any] = {
        "decision": "GO_QVF_LIFECYCLE_WEAK_GATE_PACK_READY_NO_API",
        "execution_mode": "weak_gate_pack_only",
        "packet_count": len(packets),
        "weak_gate_task_count": len(weak_gate_tasks),
        "estimated_model_call_count": len(weak_gate_tasks),
        "task_coverage": {
            "packet_query_count": len(packet_query_ids),
            "covered_packet_count": len(covered_query_ids),
            "skipped_packet_count": len(skipped_query_ids),
            "coverage_ratio": (
                len(covered_query_ids) / len(packet_query_ids)
                if packet_query_ids
                else None
            ),
            "covered_query_ids": covered_query_ids,
            "skipped_query_ids": skipped_query_ids,
        },
        "task_size_proxy": {
            "task_count": len(task_size_rows),
            "input_json_chars_total": sum(
                row["input_json_chars"] for row in task_size_rows
            ),
            "task_json_chars_total": sum(row["task_json_chars"] for row in task_size_rows),
            "input_word_like_tokens_total": sum(
                row["input_word_like_tokens"] for row in task_size_rows
            ),
            "task_word_like_tokens_total": sum(
                row["task_word_like_tokens"] for row in task_size_rows
            ),
            "max_input_json_chars": max(
                [row["input_json_chars"] for row in task_size_rows],
                default=0,
            ),
            "max_task_json_chars": max(
                [row["task_json_chars"] for row in task_size_rows],
                default=0,
            ),
            "largest_tasks": largest_tasks,
        },
        "expected_gate_decision_counts": {},
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API weak-reader task pack, not weak-model accuracy evidence.",
            "It exports compact gate inputs for later approved weak-model runs.",
        ],
    }
    for task in weak_gate_tasks:
        expected_decision = task["expected_gate_decision"]
        summary["expected_gate_decision_counts"][expected_decision] = (
            summary["expected_gate_decision_counts"].get(expected_decision, 0) + 1
        )
    return summary


def build_lifecycle_step_cli_summary(
    step_report: dict[str, Any],
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    input_mode: str,
    append_records_loaded: int,
) -> dict[str, Any]:
    query_summary = step_report["query_report"]["summary"]
    summary = {
        "decision": step_report["decision"],
        "execution_mode": step_report["execution_mode"],
        "step_id": step_report.get("step_id"),
        "input_mode": input_mode,
        "query_mode": step_report["query_mode"],
        "records_loaded": len(records),
        "append_records_loaded": append_records_loaded,
        "records_submitted": step_report["records_submitted"],
        "admission_event_count": step_report["admission_event_count"],
        "query_count": step_report["query_count"],
        "state_delta": step_report["state_delta"],
        "store_integrity_before": step_report["store_integrity_before"],
        "store_integrity_after": step_report["store_integrity_after"],
        "store_integrity_delta": step_report["store_integrity_delta"],
        "store_integrity": step_report["store_integrity"],
        "read_decision_counts": query_summary["read_decision_counts"],
        "read_route_counts": query_summary["read_route_counts"],
        "reader_answer_policy_counts": query_summary["reader_answer_policy_counts"],
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API lifecycle step run, not model-accuracy evidence.",
            "It executes write-time admission followed by retrieval/read-time QVF over the updated store.",
        ],
    }
    if "weak_gate_adapter_summary" in query_summary:
        summary["weak_gate_adapter_summary"] = query_summary["weak_gate_adapter_summary"]
    if "event_adapter_summary" in step_report:
        summary["event_adapter_summary"] = step_report["event_adapter_summary"]
        summary["records_submitted_from_events"] = step_report[
            "records_submitted_from_events"
        ]
        summary["records_submitted_from_records"] = step_report[
            "records_submitted_from_records"
        ]
    if "query_request_adapter_summary" in step_report:
        summary["query_request_adapter_summary"] = step_report[
            "query_request_adapter_summary"
        ]
        summary["queries_submitted_from_requests"] = step_report[
            "queries_submitted_from_requests"
        ]
        summary["queries_submitted_from_queries"] = step_report[
            "queries_submitted_from_queries"
        ]
    return summary


def build_lifecycle_step_preview_cli_summary(
    step_report: dict[str, Any],
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    input_mode: str,
    append_records_loaded: int,
) -> dict[str, Any]:
    query_summary = step_report["query_report"]["summary"]
    summary = {
        "decision": step_report["decision"],
        "execution_mode": step_report["execution_mode"],
        "preview_does_not_mutate_source": step_report["preview_does_not_mutate_source"],
        "source_store_unchanged": step_report["source_store_unchanged"],
        "step_id": step_report.get("step_id"),
        "input_mode": input_mode,
        "query_mode": step_report["query_mode"],
        "records_loaded": len(records),
        "append_records_loaded": append_records_loaded,
        "records_submitted": step_report["records_submitted"],
        "admission_event_count": step_report["admission_event_count"],
        "query_count": step_report["query_count"],
        "state_delta": step_report["state_delta"],
        "store_integrity_before": step_report["store_integrity_before"],
        "store_integrity_after": step_report["store_integrity_after"],
        "store_integrity_delta": step_report["store_integrity_delta"],
        "store_integrity": step_report["store_integrity"],
        "original_store_integrity": step_report["original_store_integrity"],
        "changed_memory_ids": step_report["changed_memory_ids"],
        "store_diff": step_report["store_diff"],
        "read_decision_counts": query_summary["read_decision_counts"],
        "read_route_counts": query_summary["read_route_counts"],
        "reader_answer_policy_counts": query_summary["reader_answer_policy_counts"],
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API lifecycle step preview, not model-accuracy evidence.",
            "It previews write-time admission plus retrieval/read-time QVF on a cloned store.",
            "The source store is intentionally not written or mutated.",
        ],
    }
    if "weak_gate_adapter_summary" in query_summary:
        summary["weak_gate_adapter_summary"] = query_summary["weak_gate_adapter_summary"]
    if "event_adapter_summary" in step_report:
        summary["event_adapter_summary"] = step_report["event_adapter_summary"]
        summary["records_submitted_from_events"] = step_report[
            "records_submitted_from_events"
        ]
        summary["records_submitted_from_records"] = step_report[
            "records_submitted_from_records"
        ]
    if "query_request_adapter_summary" in step_report:
        summary["query_request_adapter_summary"] = step_report[
            "query_request_adapter_summary"
        ]
        summary["queries_submitted_from_requests"] = step_report[
            "queries_submitted_from_requests"
        ]
        summary["queries_submitted_from_queries"] = step_report[
            "queries_submitted_from_queries"
        ]
    return summary


def build_lifecycle_steps_cli_summary(
    batch_report: dict[str, Any],
    records: list[dict[str, Any]],
    output_files: list[str],
    *,
    input_mode: str,
) -> dict[str, Any]:
    batch_summary = batch_report["summary"]
    return {
        "decision": batch_report["decision"],
        "execution_mode": batch_report["execution_mode"],
        "input_mode": input_mode,
        "records_loaded": len(records),
        "step_count": batch_summary["step_count"],
        "step_ids": batch_summary["step_ids"],
        "event_count": batch_summary["event_count"],
        "event_record_count": batch_summary["event_record_count"],
        "query_request_count": batch_summary["query_request_count"],
        "query_request_record_count": batch_summary["query_request_record_count"],
        "records_submitted": batch_summary["records_submitted"],
        "admission_event_count": batch_summary["admission_event_count"],
        "query_count": batch_summary["query_count"],
        "query_mode_counts": batch_summary["query_mode_counts"],
        "store_integrity_before": batch_summary["store_integrity_before"],
        "store_integrity_after": batch_summary["store_integrity_after"],
        "store_integrity_delta": batch_summary["store_integrity_delta"],
        "store_integrity": batch_summary["store_integrity"],
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API lifecycle multi-step run, not model-accuracy evidence.",
            "It executes ordered write/read steps transactionally by default over QVF validity-admission memory metadata.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=RECORDS_PATH)
    parser.add_argument("--queries", type=Path, default=QUERIES_PATH)
    parser.add_argument(
        "--load-store",
        type=Path,
        default=None,
        help="Load a previously exported admitted memory store JSONL instead of replaying raw records.",
    )
    parser.add_argument(
        "--load-state",
        type=Path,
        default=None,
        help="Load a saved validity-admission pipeline state JSON instead of replaying raw records.",
    )
    parser.add_argument(
        "--method-lock-in",
        type=Path,
        default=None,
        help="Load a method lock JSON for --compare-method-lock-only.",
    )
    parser.add_argument(
        "--append-records",
        type=Path,
        default=None,
        help="After loading or replaying the base store, admit additional raw memory records before querying.",
    )
    parser.add_argument(
        "--events-in",
        type=Path,
        default=None,
        help="Load structured external memory events as JSON/JSONL and normalize them into QVF records before admission.",
    )
    parser.add_argument(
        "--query-requests-in",
        type=Path,
        default=None,
        help="Load structured external read requests as JSON/JSONL and normalize them into QVF queries before packet building.",
    )
    parser.add_argument("--store-out", type=Path, default=STORE_OUT)
    parser.add_argument(
        "--state-out",
        type=Path,
        default=None,
        help="Optionally write a validity-admission pipeline state JSON snapshot for store-bearing runs.",
    )
    parser.add_argument(
        "--packets-in",
        type=Path,
        default=None,
        help="Load prebuilt compact validity packets JSON for read-time-only execution.",
    )
    parser.add_argument(
        "--read-decisions-in",
        type=Path,
        default=None,
        help="Load prebuilt read-time admission decisions JSON for renderer-only execution.",
    )
    parser.add_argument("--packets-out", type=Path, default=PACKETS_OUT)
    parser.add_argument("--read-decisions-out", type=Path, default=READ_DECISIONS_OUT)
    parser.add_argument("--reader-responses-out", type=Path, default=READER_RESPONSES_OUT)
    parser.add_argument("--query-results-out", type=Path, default=QUERY_RESULTS_OUT)
    parser.add_argument("--step-report-out", type=Path, default=STEP_REPORT_OUT)
    parser.add_argument(
        "--service-request-in",
        type=Path,
        default=None,
        help="Run a single structured QVF service request JSON without reading demo records or queries.",
    )
    parser.add_argument(
        "--service-response-out",
        type=Path,
        default=SERVICE_RESPONSE_OUT,
        help="Write the structured QVF service response JSON for --service-request-in.",
    )
    parser.add_argument(
        "--step-request-in",
        type=Path,
        default=None,
        help="Load a lifecycle step request JSON object with records, queries, and optional step_id.",
    )
    parser.add_argument(
        "--steps-request-in",
        type=Path,
        default=None,
        help="Load lifecycle multi-step requests as a JSON array or JSONL. Each item has the same shape as --step-request-in.",
    )
    parser.add_argument(
        "--step-id",
        type=str,
        default=None,
        help="Optional caller-supplied id for lifecycle step tracing.",
    )
    parser.add_argument(
        "--memory-id",
        type=str,
        default=None,
        help="Memory id to inspect with --inspect-memory-only.",
    )
    parser.add_argument(
        "--query-id",
        type=str,
        default=None,
        help="Query id to inspect with --inspect-query-only.",
    )
    parser.add_argument(
        "--scope-entity",
        type=str,
        default=None,
        help="Entity to inspect with --inspect-scope-only.",
    )
    parser.add_argument(
        "--scope-slot",
        type=str,
        default=None,
        help="Slot to inspect with --inspect-scope-only.",
    )
    parser.add_argument(
        "--scope-namespace",
        type=str,
        default="",
        help="Optional namespace for --inspect-scope-only.",
    )
    parser.add_argument(
        "--scope-tenant-id",
        type=str,
        default="",
        help="Optional tenant id for --inspect-scope-only.",
    )
    parser.add_argument(
        "--scope-user-id",
        type=str,
        default="",
        help="Optional user id for --inspect-scope-only.",
    )
    parser.add_argument(
        "--weak-gate-tasks-in",
        type=Path,
        default=None,
        help="Load weak gate task pack JSON for weak-gate result analysis.",
    )
    parser.add_argument(
        "--weak-gate-results-in",
        type=Path,
        default=None,
        help="Load structured weak-model gate outputs as JSON array or JSONL.",
    )
    parser.add_argument("--weak-gate-tasks-out", type=Path, default=WEAK_GATE_TASKS_OUT)
    parser.add_argument("--weak-gate-analysis-out", type=Path, default=WEAK_GATE_ANALYSIS_OUT)
    parser.add_argument("--admission-log-out", type=Path, default=ADMISSION_LOG_OUT)
    parser.add_argument("--summary-out", type=Path, default=SUMMARY_OUT)
    parser.add_argument(
        "--low-confidence-threshold",
        type=float,
        default=LOW_CONFIDENCE_THRESHOLD,
    )
    parser.add_argument("--max-current", type=int, default=1)
    parser.add_argument("--max-supporting", type=int, default=2)
    parser.add_argument("--max-stale", type=int, default=2)
    parser.add_argument("--max-excluded", type=int, default=2)
    parser.add_argument(
        "--max-packet-chars",
        type=int,
        default=None,
        help="Prune non-critical packet context until emitted packets fit this JSON char budget when possible.",
    )
    parser.add_argument(
        "--no-validity-edges",
        action="store_true",
        help="Omit graph-lite validity edges from emitted packets.",
    )
    parser.add_argument(
        "--no-weak-gate-card",
        action="store_true",
        help="Omit weak-model conservative gate cards from emitted packets.",
    )
    parser.add_argument(
        "--validate-store-only",
        action="store_true",
        help="Validate the admitted memory store and write only the summary output.",
    )
    parser.add_argument(
        "--export-method-lock-only",
        action="store_true",
        help="Export a no-data method fingerprint/config lock before held-out evaluation.",
    )
    parser.add_argument(
        "--compare-method-lock-only",
        action="store_true",
        help="Compare current code/config against --method-lock-in without loading datasets.",
    )
    parser.add_argument(
        "--enforce-method-lock",
        action="store_true",
        help="Require --method-lock-in to match current code/config before data-bearing runs.",
    )
    parser.add_argument(
        "--summarize-store-only",
        action="store_true",
        help="Summarize admitted memory validity metadata without packet building or read-time routing.",
    )
    parser.add_argument(
        "--inspect-memory-only",
        action="store_true",
        help="Inspect one admitted memory record and its validity links without packet building or read-time routing.",
    )
    parser.add_argument(
        "--inspect-scope-only",
        action="store_true",
        help="Inspect one normalized entity-slot scope history without packet building or read-time routing.",
    )
    parser.add_argument(
        "--inspect-query-only",
        action="store_true",
        help="Inspect one query's packet, read decision, and retrieval diagnostics without batch outputs.",
    )
    parser.add_argument(
        "--validate-state-only",
        action="store_true",
        help="Validate a saved pipeline state loaded with --load-state and write only the summary output.",
    )
    parser.add_argument(
        "--admit-only",
        action="store_true",
        help="Run write-time admission and write store/admission-log/summary without read-time querying.",
    )
    parser.add_argument(
        "--preview-admission-only",
        action="store_true",
        help="Preview append-record admission on a cloned store and write only the summary output.",
    )
    parser.add_argument(
        "--packets-only",
        action="store_true",
        help="Build compact validity packets and summary without read-time routing or reader responses.",
    )
    parser.add_argument(
        "--read-packets-only",
        action="store_true",
        help="Run structured read-time routing/response generation from prebuilt packets only.",
    )
    parser.add_argument(
        "--route-packets-only",
        action="store_true",
        help="Run structured read-time routing from prebuilt packets without reader responses.",
    )
    parser.add_argument(
        "--render-decisions-only",
        action="store_true",
        help="Render reader responses/results from prebuilt packets and read decisions.",
    )
    parser.add_argument(
        "--weak-gate-pack-only",
        action="store_true",
        help="Export weak-reader gate task inputs from prebuilt packets without model calls.",
    )
    parser.add_argument(
        "--analyze-weak-gate-results-only",
        action="store_true",
        help="Score structured weak-reader gate outputs against a weak gate task pack.",
    )
    parser.add_argument(
        "--adapt-weak-gate-results-only",
        action="store_true",
        help="Convert structured weak-reader gate outputs into QVF read decisions.",
    )
    parser.add_argument(
        "--validity-admission-step-only",
        "--lifecycle-step-only",
        dest="validity_admission_step_only",
        action="store_true",
        help="Run one write/read validity-admission step and emit a nested step report without model calls.",
    )
    parser.add_argument(
        "--preview-validity-admission-step-only",
        "--preview-lifecycle-step-only",
        dest="preview_validity_admission_step_only",
        action="store_true",
        help="Preview one write/read validity-admission step on a cloned store and write only the summary output.",
    )
    parser.add_argument(
        "--validity-admission-steps-only",
        "--lifecycle-steps-only",
        dest="validity_admission_steps_only",
        action="store_true",
        help="Run an ordered transactional sequence of validity-admission step requests without model calls.",
    )
    return parser.parse_args()


def validate_component_mode_args(args: argparse.Namespace) -> None:
    component_modes = [
        ("validate_store_only", "--validate-store-only"),
        ("export_method_lock_only", "--export-method-lock-only"),
        ("compare_method_lock_only", "--compare-method-lock-only"),
        ("summarize_store_only", "--summarize-store-only"),
        ("inspect_memory_only", "--inspect-memory-only"),
        ("inspect_scope_only", "--inspect-scope-only"),
        ("inspect_query_only", "--inspect-query-only"),
        ("validate_state_only", "--validate-state-only"),
        ("admit_only", "--admit-only"),
        ("preview_admission_only", "--preview-admission-only"),
        ("packets_only", "--packets-only"),
        ("read_packets_only", "--read-packets-only"),
        ("route_packets_only", "--route-packets-only"),
        ("render_decisions_only", "--render-decisions-only"),
        ("weak_gate_pack_only", "--weak-gate-pack-only"),
        ("analyze_weak_gate_results_only", "--analyze-weak-gate-results-only"),
        ("adapt_weak_gate_results_only", "--adapt-weak-gate-results-only"),
        ("validity_admission_step_only", "--validity-admission-step-only"),
        ("preview_validity_admission_step_only", "--preview-validity-admission-step-only"),
        ("validity_admission_steps_only", "--validity-admission-steps-only"),
    ]
    selected_modes = [
        flag_name for attribute_name, flag_name in component_modes if getattr(args, attribute_name)
    ]
    if len(selected_modes) > 1:
        raise ValueError(
            "Component modes are mutually exclusive: "
            + ", ".join(selected_modes)
        )
    if args.service_request_in is not None:
        if selected_modes:
            raise ValueError(
                "--service-request-in is mutually exclusive with component modes: "
                + ", ".join(selected_modes)
            )
        service_external_inputs = [
            ("--load-store", args.load_store is not None),
            ("--load-state", args.load_state is not None),
            ("--method-lock-in", args.method_lock_in is not None),
            ("--append-records", args.append_records is not None),
            ("--events-in", args.events_in is not None),
            ("--query-requests-in", args.query_requests_in is not None),
            ("--packets-in", args.packets_in is not None),
            ("--read-decisions-in", args.read_decisions_in is not None),
            ("--step-request-in", args.step_request_in is not None),
            ("--steps-request-in", args.steps_request_in is not None),
            ("--weak-gate-tasks-in", args.weak_gate_tasks_in is not None),
            ("--weak-gate-results-in", args.weak_gate_results_in is not None),
            ("--enforce-method-lock", args.enforce_method_lock),
        ]
        conflicting_inputs = [
            flag_name for flag_name, is_present in service_external_inputs if is_present
        ]
        if conflicting_inputs:
            raise ValueError(
                "--service-request-in expects all QVF inputs inside the request JSON; "
                "remove "
                + ", ".join(conflicting_inputs)
            )
        if args.records != RECORDS_PATH or args.queries != QUERIES_PATH:
            raise ValueError("--service-request-in ignores --records/--queries; put them inside the request JSON")
        return
    if args.service_response_out != SERVICE_RESPONSE_OUT:
        raise ValueError("--service-response-out requires --service-request-in")
    if args.step_id is not None and not (
        args.validity_admission_step_only or args.preview_validity_admission_step_only
    ):
        raise ValueError("--step-id requires --validity-admission-step-only or --preview-validity-admission-step-only")
    if args.memory_id is not None and not args.inspect_memory_only:
        raise ValueError("--memory-id requires --inspect-memory-only")
    if args.inspect_memory_only and args.memory_id is None:
        raise ValueError("--inspect-memory-only requires --memory-id")
    if args.query_id is not None and not args.inspect_query_only:
        raise ValueError("--query-id requires --inspect-query-only")
    if args.inspect_query_only and args.query_id is None:
        raise ValueError("--inspect-query-only requires --query-id")
    scope_args_provided = any(
        [
            args.scope_entity is not None,
            args.scope_slot is not None,
            bool(args.scope_namespace),
            bool(args.scope_tenant_id),
            bool(args.scope_user_id),
        ]
    )
    if scope_args_provided and not args.inspect_scope_only:
        raise ValueError(
            "--scope-entity/--scope-slot/--scope-* require --inspect-scope-only"
        )
    if args.inspect_scope_only and (
        args.scope_entity is None or args.scope_slot is None
    ):
        raise ValueError("--inspect-scope-only requires --scope-entity and --scope-slot")
    if args.step_request_in is not None and not (
        args.validity_admission_step_only or args.preview_validity_admission_step_only
    ):
        raise ValueError(
            "--step-request-in requires --validity-admission-step-only or --preview-validity-admission-step-only"
        )
    if args.steps_request_in is not None and not args.validity_admission_steps_only:
        raise ValueError("--steps-request-in requires --validity-admission-steps-only")
    if args.validity_admission_steps_only and args.steps_request_in is None:
        raise ValueError("--validity-admission-steps-only requires --steps-request-in")
    if args.validity_admission_steps_only and args.step_id is not None:
        raise ValueError("--step-id requires --validity-admission-step-only")
    if args.validity_admission_steps_only and args.step_request_in is not None:
        raise ValueError("--step-request-in and --steps-request-in are mutually exclusive")
    if args.validity_admission_steps_only and args.append_records is not None:
        raise ValueError("--append-records is not supported with --validity-admission-steps-only")
    if args.validity_admission_steps_only and args.events_in is not None:
        raise ValueError("--events-in is not supported with --validity-admission-steps-only; put events inside each step request")
    if args.validity_admission_steps_only and args.query_requests_in is not None:
        raise ValueError("--query-requests-in is not supported with --validity-admission-steps-only; put query_requests inside each step request")
    if args.preview_admission_only and args.append_records is None and args.events_in is None:
        raise ValueError("--preview-admission-only requires --append-records or --events-in")
    if args.validity_admission_steps_only and args.weak_gate_results_in is not None:
        raise ValueError(
            "--weak-gate-results-in is not supported with --validity-admission-steps-only; "
            "put weak_gate_outputs inside each step request"
        )
    if args.step_request_in is not None and args.append_records is not None:
        raise ValueError("--step-request-in and --append-records are mutually exclusive")
    if args.step_request_in is not None and args.events_in is not None:
        raise ValueError("--step-request-in and --events-in are mutually exclusive")
    if args.step_request_in is not None and args.query_requests_in is not None:
        raise ValueError("--step-request-in and --query-requests-in are mutually exclusive")
    if args.step_request_in is not None and args.step_id is not None:
        raise ValueError("--step-request-in and --step-id are mutually exclusive")
    if args.load_store is not None and args.load_state is not None:
        raise ValueError("--load-store and --load-state are mutually exclusive")
    if args.events_in is not None and (
        args.export_method_lock_only
        or args.compare_method_lock_only
        or args.read_packets_only
        or args.route_packets_only
        or args.render_decisions_only
        or args.weak_gate_pack_only
        or args.analyze_weak_gate_results_only
        or args.adapt_weak_gate_results_only
    ):
        raise ValueError("--events-in requires a store-bearing admission/query mode")
    if args.query_requests_in is not None and (
        args.export_method_lock_only
        or args.compare_method_lock_only
        or args.read_packets_only
        or args.route_packets_only
        or args.render_decisions_only
        or args.weak_gate_pack_only
        or args.analyze_weak_gate_results_only
        or args.adapt_weak_gate_results_only
        or args.validate_store_only
        or args.summarize_store_only
        or args.inspect_memory_only
        or args.inspect_scope_only
        or args.validate_state_only
        or args.admit_only
        or args.preview_admission_only
    ):
        raise ValueError("--query-requests-in requires a query-bearing store mode")
    if args.method_lock_in is not None and not (
        args.compare_method_lock_only or args.enforce_method_lock
    ):
        raise ValueError(
            "--method-lock-in requires --compare-method-lock-only or --enforce-method-lock"
        )
    if args.compare_method_lock_only and args.method_lock_in is None:
        raise ValueError("--compare-method-lock-only requires --method-lock-in")
    if args.enforce_method_lock and args.method_lock_in is None:
        raise ValueError("--enforce-method-lock requires --method-lock-in")
    if args.enforce_method_lock and (
        args.export_method_lock_only or args.compare_method_lock_only
    ):
        raise ValueError(
            "--enforce-method-lock is for data-bearing runs, not method-lock export/compare modes"
        )
    if args.validate_state_only and args.load_state is None:
        raise ValueError("--validate-state-only requires --load-state")
    if (
        args.read_packets_only
        or args.route_packets_only
        or args.render_decisions_only
        or args.weak_gate_pack_only
        or args.adapt_weak_gate_results_only
    ) and args.packets_in is None:
        raise ValueError(
            "--read-packets-only/--route-packets-only/--render-decisions-only/"
            "--weak-gate-pack-only/--adapt-weak-gate-results-only "
            "requires --packets-in"
        )
    if args.render_decisions_only and args.read_decisions_in is None:
        raise ValueError("--render-decisions-only requires --read-decisions-in")
    if args.analyze_weak_gate_results_only and args.weak_gate_tasks_in is None:
        raise ValueError("--analyze-weak-gate-results-only requires --weak-gate-tasks-in")
    if args.analyze_weak_gate_results_only and args.weak_gate_results_in is None:
        raise ValueError("--analyze-weak-gate-results-only requires --weak-gate-results-in")
    if args.adapt_weak_gate_results_only and args.weak_gate_tasks_in is None:
        raise ValueError("--adapt-weak-gate-results-only requires --weak-gate-tasks-in")
    if args.adapt_weak_gate_results_only and args.weak_gate_results_in is None:
        raise ValueError("--adapt-weak-gate-results-only requires --weak-gate-results-in")


def main() -> None:
    args = parse_args()
    validate_component_mode_args(args)
    if args.export_method_lock_only:
        include_validity_edges = not args.no_validity_edges
        include_weak_gate_card = not args.no_weak_gate_card
        summary = build_method_lock_summary(
            [args.summary_out.name],
            low_confidence_threshold=args.low_confidence_threshold,
            max_current=args.max_current,
            max_supporting=args.max_supporting,
            max_stale=args.max_stale,
            max_excluded=args.max_excluded,
            max_packet_chars=args.max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.compare_method_lock_only:
        include_validity_edges = not args.no_validity_edges
        include_weak_gate_card = not args.no_weak_gate_card
        expected_lock = json.loads(args.method_lock_in.read_text(encoding="utf-8"))
        summary = build_method_lock_comparison_summary(
            expected_lock,
            [args.summary_out.name],
            low_confidence_threshold=args.low_confidence_threshold,
            max_current=args.max_current,
            max_supporting=args.max_supporting,
            max_stale=args.max_stale,
            max_excluded=args.max_excluded,
            max_packet_chars=args.max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.service_request_in is not None:
        service_request = load_qvf_service_request(args.service_request_in)
        service_response = run_qvf_service_request(service_request)
        output_files = [args.service_response_out.name, args.summary_out.name]
        service_response["output_files"] = output_files
        service_response["summary"]["output_files"] = output_files
        args.service_response_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.service_response_out.write_text(
            json.dumps(service_response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        args.summary_out.write_text(
            json.dumps(service_response["summary"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(service_response["summary"], ensure_ascii=False, indent=2))
        return

    if args.enforce_method_lock:
        include_validity_edges = not args.no_validity_edges
        include_weak_gate_card = not args.no_weak_gate_card
        expected_lock = json.loads(args.method_lock_in.read_text(encoding="utf-8"))
        enforce_method_lock_match(
            expected_lock,
            low_confidence_threshold=args.low_confidence_threshold,
            max_current=args.max_current,
            max_supporting=args.max_supporting,
            max_stale=args.max_stale,
            max_excluded=args.max_excluded,
            max_packet_chars=args.max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )

    if args.read_packets_only:
        packets = validate_packet_batch(
            json.loads(args.packets_in.read_text(encoding="utf-8"))
        )
        read_decisions = build_read_decisions(packets)
        reader_responses = build_reader_responses(packets, read_decisions)
        query_results = build_query_results(packets, read_decisions, reader_responses)
        args.read_decisions_out.parent.mkdir(parents=True, exist_ok=True)
        args.reader_responses_out.parent.mkdir(parents=True, exist_ok=True)
        args.query_results_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.read_decisions_out.write_text(
            json.dumps(read_decisions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        args.reader_responses_out.write_text(
            json.dumps(reader_responses, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        args.query_results_out.write_text(
            json.dumps(query_results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = build_read_time_summary(
            packets,
            read_decisions,
            reader_responses,
            [
                args.read_decisions_out.name,
                args.reader_responses_out.name,
                args.query_results_out.name,
                args.summary_out.name,
            ],
        )
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.route_packets_only:
        packets = validate_packet_batch(
            json.loads(args.packets_in.read_text(encoding="utf-8"))
        )
        read_decisions = build_read_decisions(packets)
        args.read_decisions_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.read_decisions_out.write_text(
            json.dumps(read_decisions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = build_route_summary(
            packets,
            read_decisions,
            [
                args.read_decisions_out.name,
                args.summary_out.name,
            ],
        )
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.render_decisions_only:
        packets = validate_packet_batch(
            json.loads(args.packets_in.read_text(encoding="utf-8"))
        )
        read_decisions = json.loads(args.read_decisions_in.read_text(encoding="utf-8"))
        reader_responses = build_reader_responses(packets, read_decisions)
        query_results = build_query_results(packets, read_decisions, reader_responses)
        args.reader_responses_out.parent.mkdir(parents=True, exist_ok=True)
        args.query_results_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.reader_responses_out.write_text(
            json.dumps(reader_responses, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        args.query_results_out.write_text(
            json.dumps(query_results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = build_renderer_summary(
            packets,
            read_decisions,
            reader_responses,
            query_results,
            [
                args.reader_responses_out.name,
                args.query_results_out.name,
                args.summary_out.name,
            ],
        )
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.weak_gate_pack_only:
        packets = validate_packet_batch(
            json.loads(args.packets_in.read_text(encoding="utf-8"))
        )
        weak_gate_tasks = build_weak_gate_tasks(packets)
        args.weak_gate_tasks_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.weak_gate_tasks_out.write_text(
            json.dumps(weak_gate_tasks, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = build_weak_gate_pack_summary(
            packets,
            weak_gate_tasks,
            [
                args.weak_gate_tasks_out.name,
                args.summary_out.name,
            ],
        )
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.analyze_weak_gate_results_only:
        weak_gate_tasks = load_json_or_jsonl(args.weak_gate_tasks_in)
        weak_gate_outputs = load_json_or_jsonl(args.weak_gate_results_in)
        analysis_rows, summary = score_weak_gate_outputs(
            weak_gate_tasks,
            weak_gate_outputs,
        )
        summary["output_files"] = [
            args.weak_gate_analysis_out.name,
            args.summary_out.name,
        ]
        args.weak_gate_analysis_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        write_csv(
            args.weak_gate_analysis_out,
            analysis_rows,
            fieldnames=WEAK_GATE_ANALYSIS_FIELDS,
        )
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.adapt_weak_gate_results_only:
        packets = validate_packet_batch(
            json.loads(args.packets_in.read_text(encoding="utf-8"))
        )
        weak_gate_tasks = load_json_or_jsonl(args.weak_gate_tasks_in)
        weak_gate_outputs = load_json_or_jsonl(args.weak_gate_results_in)
        read_decisions, summary = build_read_decisions_from_weak_gate_outputs(
            packets,
            weak_gate_tasks,
            weak_gate_outputs,
        )
        summary["output_files"] = [
            args.read_decisions_out.name,
            args.summary_out.name,
        ]
        args.read_decisions_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.read_decisions_out.write_text(
            json.dumps(read_decisions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    runtime_max_current = args.max_current
    runtime_max_supporting = args.max_supporting
    runtime_max_stale = args.max_stale
    runtime_max_excluded = args.max_excluded
    runtime_max_packet_chars = args.max_packet_chars
    include_validity_edges = not args.no_validity_edges
    include_weak_gate_card = not args.no_weak_gate_card
    append_records: list[dict[str, Any]] = []
    memory_events: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    event_adapter_summary: dict[str, Any] | None = None
    query_requests: list[dict[str, Any]] = []
    query_request_queries: list[dict[str, Any]] = []
    query_request_adapter_summary: dict[str, Any] | None = None

    if args.load_state is not None:
        loaded_pipeline = QVFMemoryPipeline.from_state_file(args.load_state)
        store = loaded_pipeline.store
        records = store.export_memory_store()
        runtime_max_current = loaded_pipeline.max_current
        runtime_max_supporting = loaded_pipeline.max_supporting
        runtime_max_stale = loaded_pipeline.max_stale
        runtime_max_excluded = loaded_pipeline.max_excluded
        runtime_max_packet_chars = loaded_pipeline.max_packet_chars
        include_validity_edges = loaded_pipeline.include_validity_edges
        include_weak_gate_card = loaded_pipeline.include_weak_gate_card
        input_mode = "load_pipeline_state"
    elif args.load_store is not None:
        store = load_memory_store_jsonl(
            args.load_store,
            low_confidence_threshold=args.low_confidence_threshold,
        )
        records = store.export_memory_store()
        input_mode = "load_exported_store"
    else:
        records = load_jsonl(args.records)
        store = ValidityAwareMemoryStore(
            low_confidence_threshold=args.low_confidence_threshold,
        )
        store.admit_records(records)
        input_mode = "replay_raw_records"

    if args.events_in is not None:
        memory_events = load_memory_events(args.events_in)
        event_records = normalize_memory_events(
            memory_events,
            default_source_confidence=store.low_confidence_threshold,
        )
        event_adapter_summary = build_memory_event_adapter_summary(
            memory_events,
            event_records,
        )
    if args.query_requests_in is not None:
        query_requests = load_query_requests(args.query_requests_in)
        query_request_queries = normalize_query_requests(query_requests)
        query_request_adapter_summary = build_query_request_adapter_summary(
            query_requests,
            query_request_queries,
        )
    if args.validity_admission_steps_only:
        step_requests = load_lifecycle_step_requests(args.steps_request_in)
        step_input_mode = f"{input_mode}_lifecycle_steps_request"
        pipeline = QVFMemoryPipeline(
            store=store,
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        batch_report = pipeline.run_validity_admission_steps(step_requests)
        state_outputs = maybe_write_pipeline_state(
            args.state_out,
            pipeline.store,
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        output_files = [
            args.step_report_out.name,
            *state_outputs,
            args.summary_out.name,
        ]
        batch_report["input_mode"] = step_input_mode
        batch_report["output_files"] = output_files
        args.step_report_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.step_report_out.write_text(
            json.dumps(batch_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary = build_lifecycle_steps_cli_summary(
            batch_report,
            records,
            output_files,
            input_mode=step_input_mode,
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.preview_validity_admission_step_only:
        if args.step_request_in is not None:
            step_request = load_lifecycle_step_request(args.step_request_in)
            step_records = step_request["records"]
            step_events = step_request["events"] or None
            step_query_requests = step_request["query_requests"] or None
            queries = step_request["queries"]
            step_id = step_request["step_id"]
            weak_gate_outputs = step_request["weak_gate_outputs"]
            step_input_mode = f"{input_mode}_lifecycle_step_preview_request"
        else:
            step_records = (
                load_jsonl(args.append_records)
                if args.append_records is not None
                else []
            )
            step_events = memory_events or None
            step_query_requests = query_requests or None
            queries = load_cli_queries(args.queries, query_request_queries)
            step_id = args.step_id
            weak_gate_outputs = None
            step_input_mode = f"{input_mode}_lifecycle_step_preview"
        if args.weak_gate_results_in is not None and weak_gate_outputs is None:
            weak_gate_outputs = load_json_or_jsonl(args.weak_gate_results_in)
        pipeline = QVFMemoryPipeline(
            store=store,
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        step_report = pipeline.preview_validity_admission_event_step(
            events=step_events,
            records=step_records,
            query_requests=step_query_requests,
            queries=queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=False,
            step_id=step_id,
        )
        output_files = [args.summary_out.name]
        step_report["input_mode"] = step_input_mode
        step_report["append_records_loaded"] = len(step_records)
        step_report["output_files"] = output_files
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_lifecycle_step_preview_cli_summary(
            step_report,
            records,
            output_files,
            input_mode=step_input_mode,
            append_records_loaded=len(step_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.validity_admission_step_only:
        if args.step_request_in is not None:
            step_request = load_lifecycle_step_request(args.step_request_in)
            step_records = step_request["records"]
            step_events = step_request["events"] or None
            step_query_requests = step_request["query_requests"] or None
            queries = step_request["queries"]
            step_id = step_request["step_id"]
            include_state_in_report = step_request["include_state"]
            weak_gate_outputs = step_request["weak_gate_outputs"]
            if weak_gate_outputs is not None and args.weak_gate_results_in is not None:
                raise ValueError(
                    "lifecycle step request.weak_gate_outputs and "
                    "--weak-gate-results-in are mutually exclusive"
                )
            if weak_gate_outputs is None and args.weak_gate_results_in is not None:
                weak_gate_outputs = load_json_or_jsonl(args.weak_gate_results_in)
            step_input_mode = f"{input_mode}_lifecycle_step_request"
        else:
            step_records = (
                load_jsonl(args.append_records)
                if args.append_records is not None
                else []
            )
            step_events = memory_events or None
            step_query_requests = query_requests or None
            queries = load_cli_queries(args.queries, query_request_queries)
            step_id = args.step_id
            include_state_in_report = False
            weak_gate_outputs = (
                load_json_or_jsonl(args.weak_gate_results_in)
                if args.weak_gate_results_in is not None
                else None
            )
            step_input_mode = f"{input_mode}_lifecycle_step_only"
        pipeline = QVFMemoryPipeline(
            store=store,
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        step_report = pipeline.run_validity_admission_event_step(
            events=step_events,
            records=step_records,
            query_requests=step_query_requests,
            queries=queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state_in_report,
            step_id=step_id,
        )
        state_outputs = maybe_write_pipeline_state(
            args.state_out,
            pipeline.store,
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
        )
        output_files = [
            args.step_report_out.name,
            *state_outputs,
            args.summary_out.name,
        ]
        step_report["input_mode"] = step_input_mode
        step_report["append_records_loaded"] = len(step_records)
        step_report["output_files"] = output_files
        args.step_report_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.step_report_out.write_text(
            json.dumps(step_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary = build_lifecycle_step_cli_summary(
            step_report,
            records,
            output_files,
            input_mode=step_input_mode,
            append_records_loaded=len(step_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.preview_admission_only:
        preview_records = (
            load_jsonl(args.append_records)
            if args.append_records is not None
            else []
        ) + event_records
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_admission_preview_cli_summary(
            store,
            records,
            preview_records,
            [args.summary_out.name],
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
            input_mode=f"{input_mode}_preview_admission_only",
        )
        if event_adapter_summary is not None:
            attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.append_records is not None or event_records:
        if args.append_records is not None:
            append_records = load_jsonl(args.append_records)
        append_records = append_records + event_records
        store.admit_records(append_records)
        if args.append_records is not None:
            input_mode = f"{input_mode}_plus_append_records"
        if event_records:
            input_mode = f"{input_mode}_plus_memory_events"

    state_outputs = maybe_write_pipeline_state(
        args.state_out,
        store,
        max_current=runtime_max_current,
        max_supporting=runtime_max_supporting,
        max_stale=runtime_max_stale,
        max_excluded=runtime_max_excluded,
        max_packet_chars=runtime_max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )

    if args.validate_state_only:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_state_validation_summary(
            QVFMemoryPipeline(
                store=store,
                max_current=runtime_max_current,
                max_supporting=runtime_max_supporting,
                max_stale=runtime_max_stale,
                max_excluded=runtime_max_excluded,
                max_packet_chars=runtime_max_packet_chars,
                include_validity_edges=include_validity_edges,
                include_weak_gate_card=include_weak_gate_card,
            ),
            state_outputs + [args.summary_out.name],
            input_mode=f"{input_mode}_validate_state_only",
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.validate_store_only:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_store_validation_summary(
            store,
            records,
            state_outputs + [args.summary_out.name],
            input_mode=f"{input_mode}_validate_store_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.summarize_store_only:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_store_summary_cli_summary(
            store,
            records,
            state_outputs + [args.summary_out.name],
            input_mode=f"{input_mode}_summarize_store_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.inspect_memory_only:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_memory_inspection_cli_summary(
            store,
            records,
            args.memory_id,
            state_outputs + [args.summary_out.name],
            input_mode=f"{input_mode}_inspect_memory_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.inspect_scope_only:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_scope_inspection_cli_summary(
            store,
            records,
            state_outputs + [args.summary_out.name],
            entity=args.scope_entity,
            slot=args.scope_slot,
            namespace=args.scope_namespace,
            tenant_id=args.scope_tenant_id,
            user_id=args.scope_user_id,
            input_mode=f"{input_mode}_inspect_scope_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.admit_only:
        admitted_store = store.export_memory_store()
        args.store_out.parent.mkdir(parents=True, exist_ok=True)
        args.admission_log_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.store_out, admitted_store)
        write_csv(args.admission_log_out, store.admission_log, fieldnames=ADMISSION_LOG_FIELDS)
        summary = build_admission_summary(
            store,
            records,
            [
                args.store_out.name,
                args.admission_log_out.name,
                *state_outputs,
                args.summary_out.name,
            ],
            input_mode=f"{input_mode}_admit_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    queries = validate_query_batch(
        load_cli_queries(args.queries, query_request_queries) + query_request_queries
    )
    if args.inspect_query_only:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary = build_query_inspection_cli_summary(
            store,
            records,
            queries,
            args.query_id,
            state_outputs + [args.summary_out.name],
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
            input_mode=f"{input_mode}_inspect_query_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    packets = build_packets_from_store(
        store,
        queries,
        max_current=runtime_max_current,
        max_supporting=runtime_max_supporting,
        max_stale=runtime_max_stale,
        max_excluded=runtime_max_excluded,
        max_packet_chars=runtime_max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
    )
    if args.packets_only:
        args.packets_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.packets_out.write_text(
            json.dumps(packets, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = build_packet_summary(
            store,
            records,
            queries,
            packets,
            [
                args.packets_out.name,
                *state_outputs,
                args.summary_out.name,
            ],
            max_current=runtime_max_current,
            max_supporting=runtime_max_supporting,
            max_stale=runtime_max_stale,
            max_excluded=runtime_max_excluded,
            max_packet_chars=runtime_max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
            input_mode=f"{input_mode}_packets_only",
            append_records_loaded=len(append_records),
        )
        attach_event_adapter_summary(summary, event_adapter_summary)
        attach_query_request_adapter_summary(summary, query_request_adapter_summary)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    read_decisions = build_read_decisions(packets)
    reader_responses = build_reader_responses(packets, read_decisions)
    query_results = build_query_results(packets, read_decisions, reader_responses)
    admitted_store = store.export_memory_store()

    args.store_out.parent.mkdir(parents=True, exist_ok=True)
    args.packets_out.parent.mkdir(parents=True, exist_ok=True)
    args.read_decisions_out.parent.mkdir(parents=True, exist_ok=True)
    args.reader_responses_out.parent.mkdir(parents=True, exist_ok=True)
    args.query_results_out.parent.mkdir(parents=True, exist_ok=True)
    args.admission_log_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)

    write_jsonl(args.store_out, admitted_store)
    args.packets_out.write_text(
        json.dumps(packets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.read_decisions_out.write_text(
        json.dumps(read_decisions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.reader_responses_out.write_text(
        json.dumps(reader_responses, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.query_results_out.write_text(
        json.dumps(query_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(args.admission_log_out, store.admission_log, fieldnames=ADMISSION_LOG_FIELDS)

    summary = build_summary(
        store,
        records,
        queries,
        read_decisions,
        reader_responses,
        [
            args.store_out.name,
            args.packets_out.name,
            args.read_decisions_out.name,
            args.reader_responses_out.name,
            args.query_results_out.name,
            args.admission_log_out.name,
            *state_outputs,
            args.summary_out.name,
        ],
        max_current=runtime_max_current,
        max_supporting=runtime_max_supporting,
        max_stale=runtime_max_stale,
        max_excluded=runtime_max_excluded,
        max_packet_chars=runtime_max_packet_chars,
        include_validity_edges=include_validity_edges,
        include_weak_gate_card=include_weak_gate_card,
        input_mode=input_mode,
        append_records_loaded=len(append_records),
    )
    attach_event_adapter_summary(summary, event_adapter_summary)
    attach_query_request_adapter_summary(summary, query_request_adapter_summary)

    args.summary_out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
