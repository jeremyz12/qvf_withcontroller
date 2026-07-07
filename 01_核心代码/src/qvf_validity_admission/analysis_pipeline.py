"""Parser/analyzer adapter for QVF validity-aware memory context packing."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from ._pipeline_core import norm, validate_memory_payload, validate_query_payload
from .admission import normalize_memory_event_payload, normalize_query_request_payload
from .decisions import model_facing_forbidden_key_paths
from .service import run_qvf_service_request
from .targeted_benchmark import build_targeted_benchmark_cases

ANALYZER_VERSION = "qvf_parser_analyzer_v0.1"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_QUERY_TEXT_FIELDS = ("query", "text", "question", "user_query")
_QUERY_ID_FIELDS = ("query_id", "request_id", "event_id")


def run_qvf_parser_analyzer_request(request: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic query parsing, validity analysis, and context packing."""

    if not isinstance(request, dict):
        raise ValueError("parser/analyzer request must be an object")
    request_id = _string_field(request, ("request_id",)) or "qvf_parser_analyzer_request"
    step_id = _string_field(request, ("step_id",)) or f"{request_id}_step"
    raw_candidates = _raw_candidate_payloads(request)
    normalized_candidates = normalize_candidate_memory_payloads(raw_candidates)
    raw_queries = _raw_query_payloads(request)
    parsed_queries = [
        parse_query_request_payload(raw_query, normalized_candidates)
        for raw_query in raw_queries
    ]
    service_request = {
        "request_id": request_id,
        "step_id": step_id,
        "records": normalized_candidates,
        "queries": parsed_queries,
        "config": deepcopy(request.get("config", {})),
    }
    response = run_qvf_service_request(service_request)
    query_results = response["step_report"]["query_report"]["query_results"]
    sidecars = response.get("model_facing_sidecar_payloads", [])
    query_analyses = [
        _build_query_analysis(
            query=parsed_queries[index],
            query_result=query_results[index],
            sidecar=sidecars[index],
            candidates=normalized_candidates,
        )
        for index in range(len(parsed_queries))
    ]
    label_counts = _label_counts(query_analyses)
    return {
        "decision": "GO_QVF_PARSER_ANALYZER_READY_NO_API",
        "execution_mode": "qvf_parser_analyzer_pipeline",
        "analyzer_version": ANALYZER_VERSION,
        "request_id": request_id,
        "step_id": step_id,
        "candidate_count": len(normalized_candidates),
        "parsed_query_count": len(parsed_queries),
        "query_parser_summary": _query_parser_summary(raw_queries, parsed_queries),
        "candidate_normalizer_summary": _candidate_normalizer_summary(
            raw_candidates,
            normalized_candidates,
        ),
        "validity_analyzer_summary": {
            "query_count": len(query_analyses),
            "admission_label_counts": label_counts,
            "model_facing_forbidden_path_count": sum(
                len(analysis["model_facing_forbidden_paths"])
                for analysis in query_analyses
            ),
        },
        "query_analyses": query_analyses,
        "service_summary": response["summary"],
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a deterministic parser/analyzer adapter over structured or lightly parsed memory metadata.",
            "It does not call target models and does not claim natural-language extraction quality.",
            "It prepares validity-aware context and safe sidecar payloads before answer generation.",
        ],
    }


def parse_query_request_payload(
    request: dict[str, Any],
    candidate_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a raw query request into the QVF query schema."""

    if not isinstance(request, dict):
        raise ValueError("query request must be an object")
    candidates = candidate_records or []
    enriched = deepcopy(request)
    query_text = _query_text_from_request(enriched)
    if not query_text:
        raise ValueError("query request text/query/question is required")
    inferred = _infer_query_entity_slot(query_text, candidates)
    if not _string_field(enriched, ("entity",)) and inferred.get("entity"):
        enriched["entity"] = inferred["entity"]
    if not _string_field(enriched, ("slot",)) and inferred.get("slot"):
        enriched["slot"] = inferred["slot"]
    if (
        not _string_field(enriched, ("embedded_premise_value", "premise_value"))
        and _infer_premise_value(query_text)
    ):
        enriched["embedded_premise_value"] = _infer_premise_value(query_text)
    parsed = normalize_query_request_payload(enriched)
    parsed["parser_trace"] = {
        "parser_version": ANALYZER_VERSION,
        "entity_source": "explicit" if _string_field(request, ("entity",)) else "candidate_overlap",
        "slot_source": "explicit" if _string_field(request, ("slot",)) else "candidate_overlap",
        "premise_source": (
            "explicit"
            if _string_field(request, ("embedded_premise_value", "premise_value"))
            else (
                "text_pattern"
                if parsed.get("embedded_premise_value")
                else "absent"
            )
        ),
    }
    return validate_query_payload(parsed)


def normalize_candidate_memory_payloads(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize records/events into QVF memory records."""

    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidate memories must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        normalized_candidate = normalize_candidate_memory_payload(candidate)
        memory_id = normalized_candidate["memory_id"]
        if memory_id in seen_ids:
            raise ValueError(f"duplicate candidate memory_id: {memory_id}")
        seen_ids.add(memory_id)
        normalized_candidate["normalizer_trace"] = {
            "normalizer_version": ANALYZER_VERSION,
            "input_index": index,
            "input_kind": (
                "event" if "event_id" in candidate and "memory_id" not in candidate else "record"
            ),
        }
        normalized.append(normalized_candidate)
    return normalized


def normalize_candidate_memory_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Normalize one candidate memory record/event."""

    if not isinstance(candidate, dict):
        raise ValueError("candidate memory must be an object")
    if "memory_id" in candidate:
        return validate_memory_payload(deepcopy(candidate))
    if "event_id" in candidate:
        return normalize_memory_event_payload(candidate)
    raise ValueError("candidate memory requires memory_id or event_id")


def write_parser_analyzer_eval(
    output_dir: Path,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run parser/analyzer over targeted cases and write artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    case_pack = deepcopy(build_targeted_benchmark_cases() if cases is None else cases)
    if not isinstance(case_pack, list) or not case_pack:
        raise ValueError("parser/analyzer eval cases must be a non-empty list")
    analyses = [
        _analyze_targeted_case(case)
        for case in case_pack
    ]
    passed = sum(1 for row in analyses if row["passed"])
    result = {
        "decision": (
            "GO_QVF_PARSER_ANALYZER_EVAL_PASS_NO_API"
            if passed == len(analyses)
            else "NO_GO_QVF_PARSER_ANALYZER_EVAL_HAS_FAILURES"
        ),
        "execution_mode": "qvf_parser_analyzer_targeted_eval",
        "analyzer_version": ANALYZER_VERSION,
        "case_count": len(analyses),
        "passed_case_count": passed,
        "failed_case_count": len(analyses) - passed,
        "case_results": analyses,
        "api_calls_made": 0,
    }
    files = [
        output_dir / "parser_analyzer_results.json",
        output_dir / "parser_analyzer_summary.json",
        output_dir / "parser_analyzer_cases.csv",
    ]
    _write_json(files[0], result)
    _write_json(files[1], {key: value for key, value in result.items() if key != "case_results"})
    _write_case_csv(files[2], analyses)
    return {
        "decision": "GO_QVF_PARSER_ANALYZER_ARTIFACTS_READY_NO_API",
        "execution_mode": "qvf_parser_analyzer_writer",
        "files": [str(path) for path in files],
        "case_count": result["case_count"],
        "passed_case_count": result["passed_case_count"],
        "failed_case_count": result["failed_case_count"],
        "api_calls_made": 0,
    }


def _analyze_targeted_case(case: dict[str, Any]) -> dict[str, Any]:
    result = run_qvf_parser_analyzer_request(case["service_request"])
    analysis = result["query_analyses"][0]
    expected_current = list(case["expected"].get("current_evidence_ids", []))
    label_by_id = {
        row["memory_id"]: row
        for row in analysis["admission_labels"]
    }
    current_ok = all(
        label_by_id.get(memory_id, {}).get("admission_label") == "ADMIT_CURRENT"
        for memory_id in expected_current
    )
    no_forbidden = not analysis["model_facing_forbidden_paths"]
    decision_ok = (
        analysis["read_decision"]["decision"] == case["expected"]["decision"]
    )
    expected_empty_current = not expected_current
    if expected_empty_current:
        current_ok = not any(
            row["admission_label"] == "ADMIT_CURRENT"
            for row in analysis["admission_labels"]
        )
    return {
        "case_id": case["case_id"],
        "family": case["family"],
        "passed": current_ok and no_forbidden and decision_ok,
        "decision_ok": decision_ok,
        "current_label_ok": current_ok,
        "model_facing_clean": no_forbidden,
        "read_decision": analysis["read_decision"]["decision"],
        "label_counts": dict(Counter(row["admission_label"] for row in analysis["admission_labels"])),
    }


def _build_query_analysis(
    *,
    query: dict[str, Any],
    query_result: dict[str, Any],
    sidecar: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    compact = query_result["packet"]["compact_validity_packet"]
    labels = _admission_labels(compact, query, candidates)
    packed_context = {
        "query_id": query["query_id"],
        "context_evidence": [
            _context_row(row)
            for row in compact.get("current_evidence", [])
        ],
        "suppressed_evidence_count": sum(
            1 for row in labels if row["context_action"] != "include"
        ),
    }
    forbidden_paths = model_facing_forbidden_key_paths(sidecar)
    return {
        "query_id": query["query_id"],
        "parsed_query": query,
        "read_decision": query_result["read_decision"],
        "admission_labels": labels,
        "packed_context": packed_context,
        "model_facing_sidecar_payload": sidecar,
        "model_facing_forbidden_paths": forbidden_paths,
    }


def _admission_labels(
    compact_packet: dict[str, Any],
    query: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in compact_packet.get("current_evidence", []):
        seen_ids.add(row["memory_id"])
        rows.append(_label_row(row, "ADMIT_CURRENT", "include"))
    for row in compact_packet.get("supporting_evidence", []):
        seen_ids.add(row["memory_id"])
        rows.append(_label_row(row, "ADMIT_SUPPORT", "include"))
    for row in compact_packet.get("stale_or_blocked_evidence", []):
        seen_ids.add(row["memory_id"])
        rows.append(
            _label_row(
                row,
                _blocked_label(str(row.get("retrieval_role") or "")),
                "suppress",
            )
        )
    for row in compact_packet.get("excluded_memory_summary", []):
        seen_ids.add(row["memory_id"])
        rows.append(
            _label_row(
                row,
                _blocked_label(str(row.get("retrieval_role") or row.get("evidence_role") or "")),
                "exclude",
            )
        )
    query_scope = _query_scope(query)
    for candidate in candidates:
        if candidate["memory_id"] in seen_ids:
            continue
        label = (
            "EXCLUDE_SCOPE_MISMATCH"
            if query_scope and not _scope_matches(candidate.get("scope", {}), query_scope)
            else "NOT_RETRIEVED"
        )
        rows.append(
            {
                "memory_id": candidate["memory_id"],
                "value": candidate["value"],
                "admission_label": label,
                "context_action": "exclude",
                "retrieval_role": label.lower(),
                "reason": "candidate did not enter QVF packet for this query",
                "model_facing_allowed": False,
            }
        )
    return sorted(rows, key=lambda row: row["memory_id"])


def _label_row(row: dict[str, Any], label: str, action: str) -> dict[str, Any]:
    return {
        "memory_id": row["memory_id"],
        "value": row.get("value", ""),
        "admission_label": label,
        "context_action": action,
        "retrieval_role": row.get("retrieval_role") or row.get("evidence_role") or "",
        "reason": row.get("retrieval_reason") or row.get("reason") or "",
        "model_facing_allowed": action == "include",
    }


def _blocked_label(role: str) -> str:
    normalized = norm(role)
    mapping = {
        "stale_contrast": "REJECT_STALE",
        "condition_mismatch": "REJECT_CONDITION_MISMATCH",
        "source_policy_mismatch": "REJECT_SOURCE_POLICY",
        "scope_mismatch": "EXCLUDE_SCOPE_MISMATCH",
        "expired_contrast": "REJECT_EXPIRED",
        "revoked_contrast": "REJECT_REVOKED",
        "future_evidence": "REJECT_FUTURE",
        "below_query_confidence": "REJECT_LOW_CONFIDENCE",
        "insufficient_support": "REJECT_INSUFFICIENT_SUPPORT",
    }
    return mapping.get(normalized, "REJECT_INVALID")


def _context_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": row["memory_id"],
        "claim": row.get("claim", ""),
        "value": row.get("value", ""),
        "observed_at": row.get("observed_at", ""),
        "source_type": row.get("source_type", ""),
    }


def _raw_candidate_payloads(request: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    candidates.extend(deepcopy(request.get("candidates", [])))
    candidates.extend(deepcopy(request.get("records", [])))
    candidates.extend(deepcopy(request.get("events", [])))
    if not candidates:
        raise ValueError("parser/analyzer request requires candidates, records, or events")
    return candidates


def _raw_query_payloads(request: dict[str, Any]) -> list[dict[str, Any]]:
    query_payloads = []
    query_payloads.extend(deepcopy(request.get("queries", [])))
    query_payloads.extend(deepcopy(request.get("query_requests", [])))
    if "query" in request or "question" in request or "text" in request:
        query_payloads.append(deepcopy(request))
    if not query_payloads:
        raise ValueError("parser/analyzer request requires queries or query_requests")
    return query_payloads


def _query_parser_summary(
    raw_queries: list[dict[str, Any]],
    parsed_queries: list[dict[str, Any]],
) -> dict[str, Any]:
    trace_counts: Counter[str] = Counter()
    for query in parsed_queries:
        trace = query.get("parser_trace", {})
        for key in ["entity_source", "slot_source", "premise_source"]:
            trace_counts[f"{key}:{trace.get(key, 'unknown')}"] += 1
    return {
        "raw_query_count": len(raw_queries),
        "parsed_query_count": len(parsed_queries),
        "trace_counts": dict(sorted(trace_counts.items())),
    }


def _candidate_normalizer_summary(
    raw_candidates: list[dict[str, Any]],
    normalized_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    kind_counts: Counter[str] = Counter(
        candidate.get("normalizer_trace", {}).get("input_kind", "unknown")
        for candidate in normalized_candidates
    )
    return {
        "raw_candidate_count": len(raw_candidates),
        "normalized_candidate_count": len(normalized_candidates),
        "input_kind_counts": dict(sorted(kind_counts.items())),
    }


def _label_counts(query_analyses: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for analysis in query_analyses:
        for label in analysis["admission_labels"]:
            counts[label["admission_label"]] += 1
    return dict(sorted(counts.items()))


def _infer_query_entity_slot(
    query_text: str,
    candidates: list[dict[str, Any]],
) -> dict[str, str]:
    if not candidates:
        return {}
    query_tokens = set(_tokens(query_text))
    best_score = -1
    best_candidate: dict[str, Any] | None = None
    for candidate in candidates:
        entity = str(candidate.get("entity", ""))
        slot = str(candidate.get("slot", ""))
        candidate_tokens = set(
            _tokens(" ".join([entity, slot, candidate.get("claim", ""), candidate.get("value", "")]))
        )
        score = len(query_tokens & candidate_tokens)
        if norm(entity) in norm(query_text):
            score += 5
        slot_tokens = set(_tokens(slot.replace("_", " ")))
        if query_tokens & slot_tokens:
            score += 3
        if score > best_score:
            best_score = score
            best_candidate = candidate
    if best_candidate is None:
        return {}
    return {
        "entity": str(best_candidate.get("entity", "")),
        "slot": str(best_candidate.get("slot", "")),
    }


def _infer_premise_value(query_text: str) -> str | None:
    patterns = [
        r"\bstill\s+(?:lives|live|works|work|located|based)\s+in\s+([A-Za-z0-9_\-]+)",
        r"\bstill\s+in\s+([A-Za-z0-9_\-]+)",
        r"\bis\s+still\s+in\s+([A-Za-z0-9_\-]+)",
        r"\bis\s+still\s+([A-Za-z0-9_\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,;:?!")
    return None


def _query_text_from_request(request: dict[str, Any]) -> str | None:
    return _string_field(request, _QUERY_TEXT_FIELDS)


def _string_field(request: dict[str, Any], field_names: tuple[str, ...]) -> str | None:
    for field_name in field_names:
        value = request.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text)]


def _query_scope(query: dict[str, Any]) -> dict[str, str]:
    raw_scope = query.get("scope", {}) or {}
    if not isinstance(raw_scope, dict):
        return {}
    return {
        key: norm(str(raw_scope.get(key) or query.get(key) or ""))
        for key in ["namespace", "tenant_id", "user_id"]
    }


def _scope_matches(candidate_scope: Any, query_scope: dict[str, str]) -> bool:
    if not isinstance(candidate_scope, dict):
        candidate_scope = {}
    for key in ["namespace", "tenant_id", "user_id"]:
        candidate_value = norm(str(candidate_scope.get(key) or ""))
        query_value = query_scope.get(key, "")
        if candidate_value or query_value:
            if candidate_value != query_value:
                return False
    return True


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_case_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "family",
        "passed",
        "decision_ok",
        "current_label_ok",
        "model_facing_clean",
        "read_decision",
        "label_counts",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["label_counts"] = json.dumps(
                csv_row["label_counts"],
                ensure_ascii=False,
                sort_keys=True,
            )
            writer.writerow(csv_row)


__all__ = [
    "ANALYZER_VERSION",
    "normalize_candidate_memory_payload",
    "normalize_candidate_memory_payloads",
    "parse_query_request_payload",
    "run_qvf_parser_analyzer_request",
    "write_parser_analyzer_eval",
]
