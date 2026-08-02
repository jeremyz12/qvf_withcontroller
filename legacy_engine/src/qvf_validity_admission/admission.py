from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ._pipeline_core import (
    LOW_CONFIDENCE_THRESHOLD,
    load_json_or_jsonl,
    load_jsonl,
    norm,
    validate_low_confidence_threshold,
    validate_memory_batch,
    validate_memory_payload,
    validate_query_batch,
    validate_query_payload,
)

ROOT = Path(__file__).resolve().parent
QUERIES_PATH = ROOT / "validity_admission_demo_queries.jsonl"
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
    if "requested_response_dimensions" in request:
        query["requested_response_dimensions"] = deepcopy(
            request["requested_response_dimensions"]
        )
    if "response_dimension_state" in request:
        query["response_dimension_state"] = deepcopy(
            request["response_dimension_state"]
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
    coordinated_slot_request_count = 0
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
        if query.get(QUERY_SLOT_LIST_FIELD):
            coordinated_slot_request_count += 1
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
        "coordinated_slot_request_count": coordinated_slot_request_count,
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


__all__ = [
    "build_memory_event_adapter_summary",
    "build_query_request_adapter_summary",
    "load_memory_events",
    "load_query_requests",
    "normalize_memory_event_payload",
    "normalize_memory_events",
    "normalize_query_request_payload",
    "normalize_query_requests",
    "validate_memory_events_payload",
    "validate_query_requests_payload",
]
