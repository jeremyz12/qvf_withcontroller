"""Provenance-preserving raw post-retrieval input contract for QVF.

This module is deliberately independent of benchmark adapters.  It converts a
query plus raw retrieved memories into the structured QVF service contract only
when every admitted record can be traced back to an exact source span.  Missing
semantic fields remain missing and block execution; the contract never inserts
placeholder timestamps or confidence values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any

from .admission import normalize_query_request_payload
from .controller import (
    run_memory_validity_controller,
    run_selective_memory_validity_controller,
)
from .decisions import assert_model_facing_payload_is_clean
from .memory import validate_memory_payload
from .semantic_relations import (
    SEMANTIC_RELATION_CONTRACT_VERSION,
    TARGETED_SEMANTIC_RELATIONS,
    strict_semantic_relation,
    strict_semantic_relation_target_ids,
)
from .temporal_validity import (
    STRICT_TEMPORAL_POLICY_VERSION,
    is_strict_temporal_payload,
    strict_relation_target_ids,
    strict_temporal_relation,
)

RAW_INPUT_CONTRACT_VERSION = "qvf_raw_retrieved_memory_input_v0.1"
RAW_INPUT_PROVENANCE_VERSION = "qvf_exact_source_span_provenance_v0.1"

RAW_INPUT_FORBIDDEN_KEYS = {
    "answer",
    "answers",
    "benchmark",
    "case_id",
    "category",
    "dataset",
    "expected_answer",
    "gold",
    "gold_answer",
    "gold_labels",
    "gold_valid_memory_ids",
    "judge",
    "judge_metadata",
    "reference_answer",
}

_QUERY_OPTIONAL_FIELDS = (
    "as_of",
    "condition",
    "required_condition",
    "embedded_premise_value",
    "risk_profile",
    "validity_profile",
    "reader_profile",
    "max_age_days",
    "freshness_window_days",
    "min_source_confidence",
    "required_source_confidence",
    "min_supporting_count",
    "required_supporting_count",
    "required_source_types",
    "allowed_source_types",
    "required_evidence_qualifiers",
    "coordinated_slots",
    "scope",
    "requested_response_dimensions",
    "response_dimension_state",
)


class RawInputContractError(ValueError):
    """Raised when the caller-supplied raw contract is unsafe or malformed."""


def prepare_raw_memory_controller_request(
    raw_request: dict[str, Any],
    *,
    extractor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Prepare a structured QVF request from raw post-retrieval input.

    ``extractor`` is an application-provided semantic extraction boundary.  It
    receives only the query and safe raw-memory fields, and returns ``query``
    (entity/slot focus) plus ``records`` or ``candidate_memories``.  Already
    structured records embedded in raw rows use the same provenance validator.
    """

    if not isinstance(raw_request, dict):
        raise RawInputContractError("raw request must be an object")
    original_request = deepcopy(raw_request)
    forbidden_paths = raw_input_forbidden_key_paths(raw_request)
    if forbidden_paths:
        raise RawInputContractError(
            "raw request contains evaluation-only or benchmark metadata: "
            + ", ".join(forbidden_paths)
        )
    if extractor is not None and not callable(extractor):
        raise TypeError("extractor must be callable")
    if not isinstance(allow_partial, bool):
        raise TypeError("allow_partial must be a boolean")

    request_id = _request_id(raw_request)
    query = _normalize_raw_query(raw_request.get("query"), request_id=request_id)
    raw_memories, generated_memory_ids = _normalize_raw_memories(
        raw_request.get("retrieved_memories")
    )
    raw_context = [_model_facing_raw_memory(row) for row in raw_memories]
    extractor_input = {
        "query": deepcopy(query),
        "retrieved_memories": deepcopy(raw_context),
    }

    embedded_candidates = _embedded_structured_candidates(raw_memories)
    extraction_error = ""
    extraction_output: dict[str, Any] = {}
    if extractor is not None:
        if embedded_candidates:
            raise RawInputContractError(
                "provide either extractor output or embedded structured_records, not both"
            )
        try:
            extracted = extractor(deepcopy(extractor_input))
        except Exception as exc:  # keep raw evidence, but do not guess structured facts
            extraction_error = f"extractor_error:{type(exc).__name__}"
        else:
            if not isinstance(extracted, dict):
                extraction_error = "extractor_output_not_object"
            else:
                output_forbidden = raw_input_forbidden_key_paths(extracted)
                if output_forbidden:
                    raise RawInputContractError(
                        "extractor output contains evaluation-only metadata: "
                        + ", ".join(output_forbidden)
                    )
                extraction_output = deepcopy(extracted)

    candidate_rows = embedded_candidates
    if extractor is not None and not extraction_error:
        candidate_rows = extraction_output.get(
            "records",
            extraction_output.get("candidate_memories", []),
        )
        if not isinstance(candidate_rows, list):
            extraction_error = "extractor_records_not_list"
            candidate_rows = []

    caller_query_focus = _query_focus_from_request(raw_request, query)
    extractor_query_focus = extraction_output.get(
        "query",
        extraction_output.get("query_focus", {}),
    )
    if not isinstance(extractor_query_focus, dict):
        extraction_error = extraction_error or "extractor_query_focus_not_object"
        extractor_query_focus = {}
    query_focus, query_focus_error = _merge_query_focus(
        caller_query_focus,
        extractor_query_focus,
    )

    raw_by_id = {row["memory_id"]: row for row in raw_memories}
    accepted_records: list[dict[str, Any]] = []
    rejected_records: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidate_rows):
        if not isinstance(candidate, dict):
            rejected_records.append(
                {
                    "candidate_index": index,
                    "reason": "candidate_not_object",
                    "missing_fields": [],
                }
            )
            continue
        try:
            accepted_records.append(
                _provenance_validated_record(candidate, index=index, raw_by_id=raw_by_id)
            )
        except RawInputContractError as exc:
            rejected_records.append(
                {
                    "candidate_index": index,
                    "memory_id": str(candidate.get("memory_id") or ""),
                    "reason": str(exc),
                    "missing_fields": _candidate_missing_fields(candidate, raw_by_id),
                }
            )

    duplicate_ids = _duplicate_values(
        [record["memory_id"] for record in accepted_records]
    )
    if duplicate_ids:
        rejected_records.extend(
            {
                "candidate_index": -1,
                "memory_id": memory_id,
                "reason": "duplicate_structured_memory_id",
                "missing_fields": [],
            }
            for memory_id in duplicate_ids
        )
    if not duplicate_ids:
        accepted_records, temporal_reference_rejections = (
            _validate_strict_temporal_references(accepted_records)
        )
        rejected_records.extend(temporal_reference_rejections)

    query_request: dict[str, Any] | None = None
    if not query_focus_error and query_focus:
        query_request = _build_query_request(query, query_focus)
        try:
            normalize_query_request_payload(query_request)
        except ValueError as exc:
            query_focus_error = f"invalid_query_focus:{exc}"
            query_request = None

    blocking_reasons: list[str] = []
    if extractor is None and not embedded_candidates:
        blocking_reasons.append("extractor_or_structured_records_required")
    if extraction_error:
        blocking_reasons.append(extraction_error)
    if query_focus_error:
        blocking_reasons.append(query_focus_error)
    if query_request is None:
        blocking_reasons.append("query_entity_slot_focus_required")
    if not accepted_records:
        blocking_reasons.append("no_provenance_validated_records")
    if rejected_records and not allow_partial:
        blocking_reasons.append("partial_extraction_blocked_by_default")
    if duplicate_ids:
        blocking_reasons.append("duplicate_structured_memory_ids")

    qvf_ready = not blocking_reasons
    qvf_request = None
    if qvf_ready and query_request is not None:
        qvf_request = {
            "request_id": request_id,
            "records": accepted_records,
            "events": [],
            "query_requests": [query_request],
            "queries": [],
            "config": deepcopy(raw_request.get("config", {})),
        }

    provenance_rows = [
        {
            "memory_id": record["memory_id"],
            "source_memory_id": record["source"]["source_id"],
            "source_span_start": record["source"]["source_span_start"],
            "source_span_end": record["source"]["source_span_end"],
            "observed_at_origin": record["provenance"]["observed_at_origin"],
            "source_confidence_origin": record["provenance"][
                "source_confidence_origin"
            ],
            "temporal_field_states": deepcopy(record["temporal_field_states"]),
        }
        for record in accepted_records
    ]
    temporal_missing_field_count = sum(
        1
        for record in accepted_records
        for state in record["temporal_field_states"].values()
        if state["status"] == "unknown"
    )
    return {
        "raw_input_contract_version": RAW_INPUT_CONTRACT_VERSION,
        "decision": (
            "GO_RAW_INPUT_QVF_REQUEST_READY_NO_API"
            if qvf_ready
            else "NO_GO_RAW_INPUT_INSUFFICIENT_PROVENANCE"
        ),
        "request_id": request_id,
        "qvf_ready": qvf_ready,
        "qvf_service_request": qvf_request,
        "raw_retrieved_memory_context": raw_context,
        "extraction_report": {
            "extractor_used": extractor is not None,
            "structured_fast_path_used": bool(embedded_candidates),
            "input_raw_memory_count": len(raw_memories),
            "generated_raw_memory_ids": generated_memory_ids,
            "candidate_count": len(candidate_rows),
            "accepted_record_count": len(accepted_records),
            "rejected_record_count": len(rejected_records),
            "rejected_records": rejected_records,
            "blocking_reasons": _stable_unique(blocking_reasons),
            "provenance_rows": provenance_rows,
            "temporal_missing_field_count": temporal_missing_field_count,
            "missingness_preserved": True,
            "placeholder_timestamp_count": 0,
            "placeholder_confidence_count": 0,
            "extractor_input_sha256": _canonical_sha256(extractor_input),
            "raw_context_sha256": _canonical_sha256(raw_context),
            "input_unchanged": raw_request == original_request,
        },
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API provenance and integration contract, not answer-accuracy evidence.",
            "The extractor remains pluggable; QVF validates provenance before validity control.",
            "Rejected or missing fields are not replaced with semantic defaults.",
        ],
    }


def run_raw_memory_validity_controller(
    raw_request: dict[str, Any],
    *,
    extractor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    selective: bool = True,
    allow_partial: bool = False,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    """Validate raw input provenance, then run the existing QVF controller."""

    if not isinstance(selective, bool):
        raise TypeError("selective must be a boolean")
    prepared = prepare_raw_memory_controller_request(
        raw_request,
        extractor=extractor,
        allow_partial=allow_partial,
    )
    base_output = {
        "raw_input_contract_version": RAW_INPUT_CONTRACT_VERSION,
        "request_id": prepared["request_id"],
        "decision": prepared["decision"],
        "controller_executed": False,
        "api_calls_made": 0,
        "controller_decisions": [],
        "model_facing_sidecar_payloads": [],
        "raw_retrieved_memory_context": deepcopy(
            prepared["raw_retrieved_memory_context"]
        ),
        "extraction_report": deepcopy(prepared["extraction_report"]),
        "summary": {
            "qvf_ready": prepared["qvf_ready"],
            "raw_memory_preservation_rate": 1.0,
            "raw_context_sha256": prepared["extraction_report"][
                "raw_context_sha256"
            ],
            "api_calls_made": 0,
        },
        "claim_boundary": deepcopy(prepared["claim_boundary"]),
    }
    if not prepared["qvf_ready"]:
        return base_output

    runner = (
        run_selective_memory_validity_controller
        if selective
        else run_memory_validity_controller
    )
    controller_output = runner(
        deepcopy(prepared["qvf_service_request"]),
        include_raw_response=include_raw_response,
    )
    raw_context = deepcopy(prepared["raw_retrieved_memory_context"])
    sidecars: list[dict[str, Any]] = []
    for sidecar in controller_output.get("model_facing_sidecar_payloads", []):
        if not isinstance(sidecar, dict):
            continue
        enriched = deepcopy(sidecar)
        enriched["raw_retrieved_memory_context"] = deepcopy(raw_context)
        enriched["raw_retrieved_memory_policy"] = {
            "provenance": "Each structured record points to an exact span in this raw context.",
            "current_state": "Honor QVF blocked/current roles for current-state answers.",
            "historical_recall": (
                "Preserve exact raw wording for relevant historical detail recall."
            ),
        }
        assert_model_facing_payload_is_clean(enriched)
        sidecars.append(enriched)

    base_output.update(
        {
            "decision": "GO_RAW_INPUT_QVF_CONTROLLER_READY_NO_API",
            "controller_executed": True,
            "api_calls_made": int(controller_output.get("api_calls_made", 0) or 0),
            "controller_decisions": deepcopy(
                controller_output.get("controller_decisions", [])
            ),
            "model_facing_sidecar_payloads": sidecars,
            "query_risk_routes": deepcopy(
                controller_output.get("query_risk_routes", [])
            ),
            "summary": {
                **base_output["summary"],
                "controller_mode": "selective" if selective else "always_on",
                "controller_decision_count": len(
                    controller_output.get("controller_decisions", [])
                ),
                "model_facing_payload_count": len(sidecars),
            },
        }
    )
    if include_raw_response:
        base_output["controller_output"] = controller_output
    return base_output


def raw_input_forbidden_key_paths(value: Any, *, prefix: str = "$") -> list[str]:
    """Return paths containing evaluation-only fields forbidden at runtime."""

    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_path = f"{prefix}.{key_text}"
            normalized_key = key_text.strip().lower().replace("-", "_")
            if (
                normalized_key in RAW_INPUT_FORBIDDEN_KEYS
                or normalized_key.startswith("gold_")
                or normalized_key.startswith("judge_")
            ):
                paths.append(key_path)
            paths.extend(raw_input_forbidden_key_paths(child, prefix=key_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(
                raw_input_forbidden_key_paths(child, prefix=f"{prefix}[{index}]")
            )
    return paths


def _request_id(raw_request: dict[str, Any]) -> str:
    value = raw_request.get("request_id")
    if value is not None:
        if not isinstance(value, str) or not value.strip():
            raise RawInputContractError("request_id must be a non-empty string")
        return value.strip()
    return f"raw_request_{_canonical_sha256(raw_request)[:16]}"


def _normalize_raw_query(value: Any, *, request_id: str) -> dict[str, Any]:
    if isinstance(value, str):
        text = value
        query_id = request_id
    elif isinstance(value, dict):
        text = value.get("text", value.get("question", value.get("query")))
        query_id = value.get("query_id", value.get("request_id", request_id))
    else:
        raise RawInputContractError("query must be a string or object")
    if not isinstance(text, str) or not text.strip():
        raise RawInputContractError("query text must be a non-empty string")
    if not isinstance(query_id, str) or not query_id.strip():
        raise RawInputContractError("query_id must be a non-empty string")
    return {"query_id": query_id.strip(), "text": text}


def _normalize_raw_memories(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list):
        raise RawInputContractError("retrieved_memories must be a list")
    rows: list[dict[str, Any]] = []
    generated_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, raw_row in enumerate(value):
        if isinstance(raw_row, str):
            row: dict[str, Any] = {"text": raw_row}
        elif isinstance(raw_row, dict):
            row = deepcopy(raw_row)
        else:
            raise RawInputContractError(
                f"retrieved_memories[{index}] must be a string or object"
            )
        text = row.get("text", row.get("content", row.get("memory")))
        if not isinstance(text, str) or not text:
            raise RawInputContractError(
                f"retrieved_memories[{index}].text must be a non-empty string"
            )
        memory_id = row.get("memory_id", row.get("id"))
        if memory_id is None:
            memory_id = f"raw_{index:04d}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"
            generated_ids.append(memory_id)
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise RawInputContractError(
                f"retrieved_memories[{index}].memory_id must be a non-empty string"
            )
        memory_id = memory_id.strip()
        if memory_id in seen_ids:
            raise RawInputContractError(f"duplicate raw memory_id: {memory_id}")
        seen_ids.add(memory_id)
        normalized = {
            "memory_id": memory_id,
            "text": text,
            "source_type": _optional_string(row.get("source_type"))
            or "raw_retrieved_memory",
            "observed_at": _optional_string(row.get("observed_at")),
            "source_time": _optional_string(row.get("source_time")),
            "event_time": _optional_string(row.get("event_time")),
            "effective_from": _optional_string(row.get("effective_from")),
            "effective_until": _optional_string(row.get("effective_until")),
            "temporal_status": _optional_string(row.get("temporal_status")),
            "source_confidence": row.get("source_confidence"),
            "retrieval_rank": row.get("retrieval_rank"),
            "retrieval_score": row.get("retrieval_score"),
            "structured_records": deepcopy(row.get("structured_records", [])),
        }
        if not isinstance(normalized["structured_records"], list):
            raise RawInputContractError(
                f"retrieved_memories[{index}].structured_records must be a list"
            )
        rows.append(normalized)
    return rows, generated_ids


def _model_facing_raw_memory(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "memory_id": row["memory_id"],
        "text": row["text"],
        "source_type": row["source_type"],
        "text_sha256": hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
    }
    for field_name in (
        "observed_at",
        "source_time",
        "event_time",
        "effective_from",
        "effective_until",
        "temporal_status",
        "source_confidence",
        "retrieval_rank",
        "retrieval_score",
    ):
        value = row.get(field_name)
        if value is not None:
            out[field_name] = value
    return out


def _embedded_structured_candidates(raw_memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw_memories:
        for record in row["structured_records"]:
            if isinstance(record, dict):
                candidate = deepcopy(record)
                candidate.setdefault("source_memory_id", row["memory_id"])
                out.append(candidate)
            else:
                out.append(record)
    return out


def _query_focus_from_request(
    raw_request: dict[str, Any],
    normalized_query: dict[str, Any],
) -> dict[str, Any]:
    focus = raw_request.get("query_focus", {})
    if focus is None:
        focus = {}
    if not isinstance(focus, dict):
        raise RawInputContractError("query_focus must be an object")
    query_value = raw_request.get("query")
    if isinstance(query_value, dict):
        query_options = {
            key: query_value[key]
            for key in _QUERY_OPTIONAL_FIELDS
            if key in query_value
        }
        focus = {**query_options, **focus}
        for field_name in ("entity", "slot", "needs_current"):
            if field_name in query_value and field_name not in focus:
                focus[field_name] = query_value[field_name]
    focus["query_id"] = normalized_query["query_id"]
    return focus


def _merge_query_focus(
    caller: dict[str, Any],
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    merged = deepcopy(caller)
    for key, value in extracted.items():
        if key in {"text", "question", "query", "query_id", "request_id"}:
            continue
        if key in merged and merged[key] != value:
            return {}, f"query_focus_conflict:{key}"
        merged[key] = deepcopy(value)
    entity = merged.get("entity")
    slot = merged.get("slot")
    if not isinstance(entity, str) or not entity.strip():
        return {}, "query_focus_missing_entity"
    if not isinstance(slot, str) or not slot.strip():
        return {}, "query_focus_missing_slot"
    merged["entity"] = entity.strip()
    merged["slot"] = slot.strip()
    return merged, ""


def _build_query_request(
    query: dict[str, Any],
    query_focus: dict[str, Any],
) -> dict[str, Any]:
    out = {
        "request_id": query["query_id"],
        "question": query["text"],
        "entity": query_focus["entity"],
        "slot": query_focus["slot"],
        "needs_current": query_focus.get("needs_current", True),
    }
    for field_name in _QUERY_OPTIONAL_FIELDS:
        if field_name in query_focus:
            out[field_name] = deepcopy(query_focus[field_name])
    return out


def _provenance_validated_record(
    candidate: dict[str, Any],
    *,
    index: int,
    raw_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source = candidate.get("source", {})
    if source is None:
        source = {}
    if not isinstance(source, dict):
        raise RawInputContractError("candidate.source must be an object")
    source_memory_id = candidate.get(
        "source_memory_id",
        source.get("source_memory_id", source.get("source_id")),
    )
    if not isinstance(source_memory_id, str) or not source_memory_id.strip():
        raise RawInputContractError("missing_source_memory_id")
    source_memory_id = source_memory_id.strip()
    raw = raw_by_id.get(source_memory_id)
    if raw is None:
        raise RawInputContractError("source_memory_id_not_in_retrieved_memories")

    source_span = candidate.get("source_span", source.get("source_span"))
    if not isinstance(source_span, str) or not source_span:
        raise RawInputContractError("missing_exact_source_span")
    span_start = candidate.get("source_span_start", source.get("source_span_start"))
    span_start, span_end = _exact_span_offsets(raw["text"], source_span, span_start)

    required_values: dict[str, str] = {}
    for field_name in ("entity", "slot", "value", "claim"):
        value = candidate.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise RawInputContractError(f"missing_required_semantic_field:{field_name}")
        required_values[field_name] = value.strip()

    observed_at, observed_origin = _provenance_observed_at(
        candidate,
        raw,
        source_span,
    )
    source_confidence, confidence_origin = _provenance_source_confidence(
        candidate,
        raw,
    )
    temporal_values, temporal_field_states = _temporal_field_provenance(
        candidate,
        raw,
        source_span,
        observed_at=observed_at,
        observed_origin=observed_origin,
    )
    memory_id = candidate.get("memory_id")
    if memory_id is None:
        digest_payload = {
            "source_memory_id": source_memory_id,
            "span_start": span_start,
            **required_values,
        }
        memory_id = f"extracted_{index:04d}_{_canonical_sha256(digest_payload)[:12]}"
    if not isinstance(memory_id, str) or not memory_id.strip():
        raise RawInputContractError("memory_id must be a non-empty string")

    record: dict[str, Any] = {
        "memory_id": memory_id.strip(),
        **required_values,
        "observed_at": observed_at,
        "source": {
            "source_id": source_memory_id,
            "source_type": raw["source_type"],
            "source_span": source_span,
            "source_span_start": span_start,
            "source_span_end": span_end,
            "raw_text_sha256": hashlib.sha256(
                raw["text"].encode("utf-8")
            ).hexdigest(),
        },
        "source_confidence": source_confidence,
        **temporal_values,
        "temporal_field_states": temporal_field_states,
        "provenance": {
            "version": RAW_INPUT_PROVENANCE_VERSION,
            "derivation": "extracted_from_raw_retrieved_memory",
            "source_memory_id": source_memory_id,
            "observed_at_origin": observed_origin,
            "source_confidence_origin": confidence_origin,
        },
    }
    _copy_evidence_bound_optional_fields(candidate, record, source_span, raw)
    try:
        return validate_memory_payload(record)
    except ValueError as exc:
        raise RawInputContractError(f"invalid_qvf_memory_record:{exc}") from exc


def _provenance_observed_at(
    candidate: dict[str, Any],
    raw: dict[str, Any],
    source_span: str,
) -> tuple[str, str]:
    candidate_time = _optional_string(candidate.get("observed_at"))
    raw_time = _optional_string(raw.get("observed_at"))
    if candidate_time is None and raw_time is not None:
        return raw_time, "retrieved_memory_metadata"
    if candidate_time is None:
        raise RawInputContractError("missing_observed_at_without_source_evidence")
    if raw_time is not None and candidate_time == raw_time:
        return candidate_time, "retrieved_memory_metadata"
    evidence = candidate.get("observed_at_evidence")
    _require_exact_evidence(evidence, source_span, "observed_at_evidence")
    return candidate_time, "source_span_normalization"


def _provenance_source_confidence(
    candidate: dict[str, Any],
    raw: dict[str, Any],
) -> tuple[float, str]:
    value = candidate.get("source_confidence")
    origin = "extractor_output"
    if value is None:
        value = raw.get("source_confidence")
        origin = "retrieved_memory_metadata"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RawInputContractError("missing_source_confidence")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise RawInputContractError("source_confidence_out_of_range")
    return confidence, origin


def _temporal_field_provenance(
    candidate: dict[str, Any],
    raw: dict[str, Any],
    source_span: str,
    *,
    observed_at: str,
    observed_origin: str,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    values: dict[str, str] = {}
    states: dict[str, dict[str, str]] = {
        "observed_at": {
            "status": "known",
            "value": observed_at,
            "origin": observed_origin,
        }
    }
    for field_name in (
        "source_time",
        "event_time",
        "effective_from",
        "effective_until",
    ):
        candidate_value = _optional_string(candidate.get(field_name))
        raw_value = _optional_string(raw.get(field_name))
        if candidate_value is None and raw_value is None:
            states[field_name] = {"status": "unknown"}
            continue
        if candidate_value is None:
            value = raw_value
            origin = "retrieved_memory_metadata"
        elif raw_value is not None and candidate_value == raw_value:
            value = candidate_value
            origin = "retrieved_memory_metadata"
        else:
            _require_exact_evidence(
                candidate.get(f"{field_name}_evidence"),
                source_span,
                f"{field_name}_evidence",
            )
            value = candidate_value
            origin = "source_span_normalization"
        assert value is not None
        _validate_iso_datetime_text(value, field_name)
        values[field_name] = value
        states[field_name] = {
            "status": "known",
            "value": value,
            "origin": origin,
        }
    return values, states


def _copy_evidence_bound_optional_fields(
    candidate: dict[str, Any],
    record: dict[str, Any],
    source_span: str,
    raw: dict[str, Any],
) -> None:
    for field_name in ("condition", "valid_from", "valid_until", "validity_action"):
        value = candidate.get(field_name)
        if value is None:
            continue
        _require_exact_evidence(
            candidate.get(f"{field_name}_evidence"),
            source_span,
            f"{field_name}_evidence",
        )
        record[field_name] = deepcopy(value)
    record["validity_policy"] = STRICT_TEMPORAL_POLICY_VERSION
    semantic_states: dict[str, dict[str, str]] = {}
    if "slot_cardinality" in candidate:
        _require_exact_evidence(
            candidate.get("slot_cardinality_evidence"),
            source_span,
            "slot_cardinality_evidence",
        )
        record["slot_cardinality"] = deepcopy(candidate["slot_cardinality"])
        record["slot_cardinality_evidence"] = candidate[
            "slot_cardinality_evidence"
        ]
        semantic_states["slot_cardinality"] = {
            "status": "known",
            "origin": "source_span_extraction",
        }
    else:
        record["slot_cardinality"] = "unknown"
        semantic_states["slot_cardinality"] = {"status": "unknown"}

    if "temporal_relation" in candidate:
        _require_exact_evidence(
            candidate.get("temporal_relation_evidence"),
            source_span,
            "temporal_relation_evidence",
        )
        record["temporal_relation"] = deepcopy(candidate["temporal_relation"])
        record["temporal_relation_evidence"] = candidate[
            "temporal_relation_evidence"
        ]
        record["relation_target_memory_ids"] = deepcopy(
            candidate.get("relation_target_memory_ids", [])
        )
        semantic_states["temporal_relation"] = {
            "status": "known",
            "origin": "source_span_extraction",
        }
    else:
        record["temporal_relation"] = "unresolved"
        record["relation_target_memory_ids"] = []
        semantic_states["temporal_relation"] = {"status": "unknown"}

    explicit_semantic_relation = _optional_string(
        candidate.get("semantic_relation")
    )
    legacy_semantic_relation = {
        "equivalent": "equivalent",
        "additive": "additive_coexistence",
    }.get(str(record["temporal_relation"]).strip().lower())
    if explicit_semantic_relation is not None:
        _require_exact_evidence(
            candidate.get("semantic_relation_evidence"),
            source_span,
            "semantic_relation_evidence",
        )
        record["semantic_relation"] = explicit_semantic_relation
        record["semantic_relation_evidence"] = candidate[
            "semantic_relation_evidence"
        ]
        record["semantic_relation_target_memory_ids"] = deepcopy(
            candidate.get("semantic_relation_target_memory_ids", [])
        )
        record["semantic_relation_state"] = {
            "status": (
                "unknown"
                if explicit_semantic_relation.strip().lower() == "unresolved"
                else "known"
            ),
            "origin": "source_span_extraction",
            "contract_version": SEMANTIC_RELATION_CONTRACT_VERSION,
        }
    elif legacy_semantic_relation is not None:
        record["semantic_relation"] = legacy_semantic_relation
        record["semantic_relation_target_memory_ids"] = deepcopy(
            record["relation_target_memory_ids"]
        )
        record["semantic_relation_state"] = {
            "status": "known",
            "origin": "source_span_extraction",
            "contract_version": SEMANTIC_RELATION_CONTRACT_VERSION,
            "legacy_field": "temporal_relation",
        }
    else:
        record["semantic_relation"] = "unresolved"
        record["semantic_relation_target_memory_ids"] = []
        record["semantic_relation_state"] = {
            "status": "unknown",
            "contract_version": SEMANTIC_RELATION_CONTRACT_VERSION,
        }

    candidate_status = _optional_string(candidate.get("temporal_status"))
    raw_status = _optional_string(raw.get("temporal_status"))
    if candidate_status is None and raw_status is None:
        record["temporal_status"] = "unknown"
        semantic_states["temporal_status"] = {"status": "unknown"}
    elif candidate_status is None or candidate_status == raw_status:
        record["temporal_status"] = raw_status
        semantic_states["temporal_status"] = {
            "status": "known",
            "origin": "retrieved_memory_metadata",
        }
    else:
        _require_exact_evidence(
            candidate.get("temporal_status_evidence"),
            source_span,
            "temporal_status_evidence",
        )
        record["temporal_status"] = candidate_status
        record["temporal_status_evidence"] = candidate[
            "temporal_status_evidence"
        ]
        semantic_states["temporal_status"] = {
            "status": "known",
            "origin": "source_span_extraction",
        }
    record["temporal_semantic_states"] = semantic_states

    if record["temporal_relation"] == "revocation":
        record["validity_action"] = "revoke_current"
        record["invalidates_memory_ids"] = deepcopy(
            record["relation_target_memory_ids"]
        )


def _validate_strict_temporal_references(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject dangling or cross-scope directed relations before QVF execution."""

    active = list(records)
    rejected: list[dict[str, Any]] = []
    while True:
        by_id = {record["memory_id"]: record for record in active}
        invalid: dict[str, str] = {}
        for record in active:
            if not is_strict_temporal_payload(record):
                continue
            relation = strict_temporal_relation(record)
            target_groups: list[tuple[str, tuple[str, ...]]] = []
            if relation in {"replacement", "correction", "revocation"}:
                target_groups.append(
                    ("strict_temporal_relation", strict_relation_target_ids(record))
                )
            semantic_relation = strict_semantic_relation(record)
            if semantic_relation in TARGETED_SEMANTIC_RELATIONS:
                target_groups.append(
                    (
                        "strict_semantic_relation",
                        strict_semantic_relation_target_ids(record),
                    )
                )
            for prefix, target_ids in target_groups:
                for target_id in target_ids:
                    target = by_id.get(target_id)
                    if target is None:
                        invalid[record["memory_id"]] = (
                            f"{prefix}_target_not_in_batch:{target_id}"
                        )
                        break
                    if _record_scope_signature(record) != _record_scope_signature(
                        target
                    ):
                        invalid[record["memory_id"]] = (
                            f"{prefix}_target_scope_mismatch:{target_id}"
                        )
                        break
                if record["memory_id"] in invalid:
                    break
        if not invalid:
            break
        next_active: list[dict[str, Any]] = []
        for record in active:
            reason = invalid.get(record["memory_id"])
            if reason is None:
                next_active.append(record)
                continue
            rejected.append(
                {
                    "candidate_index": -1,
                    "memory_id": record["memory_id"],
                    "reason": reason,
                    "missing_fields": [],
                }
            )
        active = next_active
    return active, rejected


def _record_scope_signature(record: dict[str, Any]) -> tuple[str, ...]:
    scope = record.get("scope", {}) or {}
    if not isinstance(scope, dict):
        scope = {}
    return (
        str(scope.get("namespace") or record.get("namespace") or "").casefold(),
        str(scope.get("tenant_id") or record.get("tenant_id") or "").casefold(),
        str(scope.get("user_id") or record.get("user_id") or "").casefold(),
        str(record.get("entity") or "").strip().casefold(),
        str(record.get("slot") or "").strip().casefold(),
    )


def _require_exact_evidence(value: Any, source_span: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise RawInputContractError(f"missing_{field_name}")
    if value not in source_span:
        raise RawInputContractError(f"{field_name}_not_in_source_span")


def _exact_span_offsets(
    raw_text: str,
    source_span: str,
    supplied_start: Any,
) -> tuple[int, int]:
    if supplied_start is not None:
        if isinstance(supplied_start, bool) or not isinstance(supplied_start, int):
            raise RawInputContractError("source_span_start_must_be_integer")
        visible_span = raw_text[supplied_start : supplied_start + len(source_span)]
        if supplied_start < 0 or visible_span != source_span:
            raise RawInputContractError("source_span_start_does_not_match_raw_text")
        return supplied_start, supplied_start + len(source_span)
    first = raw_text.find(source_span)
    if first < 0:
        raise RawInputContractError("source_span_not_in_raw_memory")
    if raw_text.find(source_span, first + 1) >= 0:
        raise RawInputContractError("ambiguous_source_span_requires_start_offset")
    return first, first + len(source_span)


def _candidate_missing_fields(
    candidate: dict[str, Any],
    raw_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    missing = [
        field_name
        for field_name in ("entity", "slot", "value", "claim")
        if not isinstance(candidate.get(field_name), str)
        or not str(candidate.get(field_name)).strip()
    ]
    source = candidate.get("source", {})
    if not isinstance(source, dict):
        source = {}
    source_id = candidate.get(
        "source_memory_id",
        source.get("source_memory_id", source.get("source_id")),
    )
    if not isinstance(source_id, str) or source_id not in raw_by_id:
        missing.append("source_memory_id")
        raw = {}
    else:
        raw = raw_by_id[source_id]
    span = candidate.get("source_span", source.get("source_span"))
    if not isinstance(span, str) or not span:
        missing.append("source_span")
    if candidate.get("observed_at") is None and raw.get("observed_at") is None:
        missing.append("observed_at")
    if candidate.get("source_confidence") is None and raw.get("source_confidence") is None:
        missing.append("source_confidence")
    return _stable_unique(missing)


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RawInputContractError("optional provenance text fields must be strings")
    return value.strip() or None


def _validate_iso_datetime_text(value: str, field_name: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RawInputContractError(
            f"{field_name}_must_be_iso_8601_datetime"
        ) from exc


def _canonical_sha256(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = [
    "RAW_INPUT_CONTRACT_VERSION",
    "RAW_INPUT_FORBIDDEN_KEYS",
    "RAW_INPUT_PROVENANCE_VERSION",
    "RawInputContractError",
    "prepare_raw_memory_controller_request",
    "raw_input_forbidden_key_paths",
    "run_raw_memory_validity_controller",
]
