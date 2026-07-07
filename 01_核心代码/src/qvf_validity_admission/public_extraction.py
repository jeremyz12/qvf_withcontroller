"""Candidate-memory extraction runner for public long-memory pilots.

The public dataset adapter produces extraction work items from raw history.
This module turns those work items into structured candidate memories, then
optionally runs the QVF service as a smoke check. API execution is opt-in; the
default path writes a preflight plan only.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .analysis_pipeline import normalize_candidate_memory_payloads
from .answer_model_eval import (
    DEFAULT_ANSWER_MODEL,
    GPT_4O_MINI_ESTIMATED_INPUT_USD_PER_1M,
    GPT_4O_MINI_ESTIMATED_OUTPUT_USD_PER_1M,
)
from .decisions import model_facing_forbidden_key_paths
from .public_dataset_adapters import load_public_dataset_rows
from .service import run_qvf_service_request

PUBLIC_EXTRACTION_VERSION = "qvf_public_memory_extraction_v0.4"
DEFAULT_EXTRACTOR_MODEL = DEFAULT_ANSWER_MODEL
DEFAULT_PUBLIC_EXTRACTION_LIMIT = 10
DEFAULT_EXTRACTOR_MAX_OUTPUT_TOKENS = 1200
DEFAULT_EXTRACTED_SOURCE_CONFIDENCE = 0.78
DEFAULT_OBSERVED_AT = "1970-01-01T00:00:00+00:00"
DEFAULT_QUERY_FOCUS_HINT_TURNS = 8
DEFAULT_SOURCE_NEIGHBOR_RADIUS = 3
DEFAULT_SOURCE_SPAN_MAX_CHARS = 1800
DEFAULT_SOURCE_TURN_MAX_CHARS = 650
QUERY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
PUBLIC_SESSION_DATETIME_PATTERN = re.compile(
    r"^\s*(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})"
    r"(?:\s+\([A-Za-z]{3}\))?"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?\s*$"
)
PUBLIC_NATURAL_SESSION_DATETIME_PATTERN = re.compile(
    r"^\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<ampm>am|pm)\s+on\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?P<month>[A-Za-z]+),?\s+"
    r"(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
QUERY_HINT_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "did",
    "do",
    "does",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "the",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}
CURRENT_SENSITIVE_QUERY_CUES = (
    "now",
    "currently",
    "current",
    "still",
    "today",
    "latest",
    "recent",
    "recently",
    "right now",
    "at the moment",
    "anymore",
    "no longer",
    "where should",
)
ELAPSED_DURATION_EXTRACTION_QUERY_PATTERN = re.compile(
    r"\bhow\s+many\s+(?:days?|weeks?|months?)\b|\bdays?\s+ago\b|\bhow\s+long\b",
    flags=re.I,
)
EVENT_TIME_MARKER_PATTERN = re.compile(
    r"\b(today|yesterday|last night|this morning|this afternoon|this evening)\b",
    flags=re.I,
)
EXPLICIT_SLASH_DATE_PATTERN = re.compile(
    r"\b(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})\b"
)
MAX_ELAPSED_EVENT_ANCHOR_REPAIRS = 4


def load_extraction_work_items(path: Path) -> list[dict[str, Any]]:
    """Load extraction work items from JSON/JSONL."""

    return validate_extraction_work_items(load_public_dataset_rows(path))


def _load_raw_extractor_outputs(path: Path) -> list[dict[str, Any]]:
    payload = load_public_dataset_rows(path)
    if not isinstance(payload, list):
        raise ValueError("raw extractor outputs must be a list or JSONL stream")
    return payload


def _parsed_raw_output(raw: dict[str, Any]) -> dict[str, Any]:
    parsed = raw.get("parsed")
    if isinstance(parsed, dict):
        return parse_extractor_output(json.dumps(parsed, ensure_ascii=False))
    content = raw.get("content")
    if isinstance(content, str):
        return parse_extractor_output(content)
    return {
        "parse_ok": False,
        "parse_error": "missing_raw_extractor_content",
        "candidate_memories": [],
        "query_focus": {},
    }


def validate_extraction_work_items(payload: Any) -> list[dict[str, Any]]:
    """Validate extraction work item shape."""

    if not isinstance(payload, list):
        raise ValueError("extraction work items must be a list")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"extraction work item {index} must be an object")
        case_id = _required_string(item, "case_id")
        question = _required_string(item, "question")
        history_turns = item.get("history_turns")
        if not isinstance(history_turns, list):
            raise ValueError(f"extraction work item {case_id} history_turns must be a list")
        for turn_index, turn in enumerate(history_turns):
            if not isinstance(turn, dict):
                raise ValueError(
                    f"extraction work item {case_id} history_turns[{turn_index}] must be an object"
                )
            _required_string(turn, "text")
        normalized = deepcopy(item)
        normalized["case_id"] = case_id
        normalized["question"] = question
        normalized["history_turns"] = history_turns
        items.append(normalized)
    return items


def run_public_extraction_eval(
    output_dir: Path,
    *,
    input_path: Path,
    extractor_model: str = DEFAULT_EXTRACTOR_MODEL,
    limit: int = DEFAULT_PUBLIC_EXTRACTION_LIMIT,
    run_api: bool = False,
    max_output_tokens: int = DEFAULT_EXTRACTOR_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Write preflight and optionally run API-backed candidate extraction."""

    _validate_positive_int(limit, "limit")
    _validate_positive_int(max_output_tokens, "max_output_tokens")
    if not isinstance(extractor_model, str) or not extractor_model.strip():
        raise ValueError("extractor_model must be a non-empty string")
    output_dir.mkdir(parents=True, exist_ok=True)
    work_items = validate_extraction_work_items(load_extraction_work_items(input_path))[:limit]
    if not work_items:
        raise ValueError("public extraction input contains no work items")

    messages_by_case = {
        item["case_id"]: build_extraction_messages(item)
        for item in work_items
    }
    preflight = _build_preflight(
        output_dir=output_dir,
        input_path=input_path,
        work_items=work_items,
        messages_by_case=messages_by_case,
        extractor_model=extractor_model,
        max_output_tokens=max_output_tokens,
    )
    _write_json(output_dir / "public_extraction_preflight.json", preflight)
    _write_preflight_report(output_dir / "public_extraction_preflight_zh.md", preflight)

    if not run_api:
        return {
            "decision": "NEEDS_RUN_API_FOR_PUBLIC_MEMORY_EXTRACTION",
            "execution_mode": "public_memory_extraction_preflight_only",
            "extraction_version": PUBLIC_EXTRACTION_VERSION,
            "work_item_count": len(work_items),
            "expected_call_count": preflight["expected_call_count"],
            "api_calls_made": 0,
            "preflight_files": [
                str(output_dir / "public_extraction_preflight.json"),
                str(output_dir / "public_extraction_preflight_zh.md"),
            ],
        }

    client = _OpenAIChatClient()
    raw_outputs: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    extracted_candidate_rows: list[dict[str, Any]] = []
    qvf_requests: list[dict[str, Any]] = []
    for item in work_items:
        timed = _call_with_timing(
            client,
            model=extractor_model,
            messages=messages_by_case[item["case_id"]],
            max_tokens=max_output_tokens,
        )
        content = _message_content(timed["response"])
        parsed = parse_extractor_output(content)
        raw_outputs.append(
            {
                "case_id": item["case_id"],
                "model": extractor_model,
                "latency_seconds": timed["latency_seconds"],
                "usage": timed["usage"],
                "content": content,
                "parsed": parsed,
                "raw_response": timed["response"],
            }
        )
        result = build_qvf_request_from_extraction(item, parsed)
        result_rows.append(_result_row(item, parsed, result, timed))
        extracted_candidate_rows.extend(result["normalized_candidates"])
        if result["qvf_service_request"] is not None:
            qvf_requests.append(result["qvf_service_request"])

    summary = _summarize_results(
        rows=result_rows,
        extractor_model=extractor_model,
    )
    result_payload = {
        "decision": "GO_QVF_PUBLIC_MEMORY_EXTRACTION_COMPLETE",
        "execution_mode": "public_memory_extraction_api_run",
        "extraction_version": PUBLIC_EXTRACTION_VERSION,
        "summary": summary,
        "case_results": result_rows,
        "api_calls_made": len(raw_outputs),
        "claim_boundary": [
            "This run extracts structured candidate memories from public-dataset raw history.",
            "It is evidence-gathering plumbing for QVF public pilots, not final answer-model accuracy.",
        ],
    }
    _write_jsonl(output_dir / "extractor_raw_outputs.jsonl", raw_outputs)
    _write_jsonl(output_dir / "extracted_candidate_memories.jsonl", extracted_candidate_rows)
    _write_jsonl(output_dir / "public_extraction_qvf_service_requests.jsonl", qvf_requests)
    _write_json(output_dir / "public_extraction_results.json", result_payload)
    _write_json(
        output_dir / "public_extraction_summary.json",
        {key: value for key, value in result_payload.items() if key != "case_results"},
    )
    _write_result_csv(output_dir / "public_extraction_cases.csv", result_rows)
    _write_result_report(output_dir / "public_extraction_report_zh.md", result_payload)
    return {
        "decision": result_payload["decision"],
        "execution_mode": result_payload["execution_mode"],
        "work_item_count": summary["work_item_count"],
        "qvf_ready_item_count": summary["qvf_ready_item_count"],
        "normalized_candidate_count": summary["normalized_candidate_count"],
        "api_calls_made": result_payload["api_calls_made"],
        "output_files": [
            str(output_dir / "public_extraction_preflight.json"),
            str(output_dir / "public_extraction_preflight_zh.md"),
            str(output_dir / "extractor_raw_outputs.jsonl"),
            str(output_dir / "extracted_candidate_memories.jsonl"),
            str(output_dir / "public_extraction_qvf_service_requests.jsonl"),
            str(output_dir / "public_extraction_results.json"),
            str(output_dir / "public_extraction_summary.json"),
            str(output_dir / "public_extraction_cases.csv"),
            str(output_dir / "public_extraction_report_zh.md"),
        ],
    }


def replay_public_extraction_outputs(
    output_dir: Path,
    *,
    input_path: Path,
    raw_outputs_path: Path,
    limit: int = DEFAULT_PUBLIC_EXTRACTION_LIMIT,
) -> dict[str, Any]:
    """Replay saved extractor JSON through current deterministic normalization."""

    _validate_positive_int(limit, "limit")
    output_dir.mkdir(parents=True, exist_ok=True)
    work_items = validate_extraction_work_items(load_extraction_work_items(input_path))[:limit]
    if not work_items:
        raise ValueError("public extraction replay input contains no work items")
    raw_by_case = {
        str(row.get("case_id", "")): row
        for row in _load_raw_extractor_outputs(raw_outputs_path)
        if isinstance(row, dict) and row.get("case_id")
    }
    result_rows: list[dict[str, Any]] = []
    extracted_candidate_rows: list[dict[str, Any]] = []
    qvf_requests: list[dict[str, Any]] = []
    missing_case_ids: list[str] = []
    for item in work_items:
        raw = raw_by_case.get(item["case_id"])
        if raw is None:
            missing_case_ids.append(item["case_id"])
            continue
        parsed = _parsed_raw_output(raw)
        result = build_qvf_request_from_extraction(item, parsed)
        result_rows.append(
            _result_row(
                item,
                parsed,
                result,
                {
                    "latency_seconds": 0.0,
                    "usage": raw.get("usage", {}),
                },
            )
        )
        extracted_candidate_rows.extend(result["normalized_candidates"])
        if result["qvf_service_request"] is not None:
            qvf_requests.append(result["qvf_service_request"])

    if not result_rows:
        raise ValueError("public extraction replay found no matching raw outputs")
    summary = _summarize_results(
        rows=result_rows,
        extractor_model="replay_saved_extractor_outputs",
        api_calls_made=0,
    )
    result_payload = {
        "decision": "GO_QVF_PUBLIC_MEMORY_EXTRACTION_REPLAY_COMPLETE",
        "execution_mode": "public_memory_extraction_replay_no_api",
        "extraction_version": PUBLIC_EXTRACTION_VERSION,
        "summary": summary,
        "case_results": result_rows,
        "missing_case_ids": missing_case_ids,
        "api_calls_made": 0,
        "claim_boundary": [
            "This replay reuses saved extractor JSON and makes no API calls.",
            "It measures current deterministic normalization, source-span repair, and QVF request construction.",
        ],
    }
    _write_jsonl(output_dir / "extracted_candidate_memories.jsonl", extracted_candidate_rows)
    _write_jsonl(output_dir / "public_extraction_qvf_service_requests.jsonl", qvf_requests)
    _write_json(output_dir / "public_extraction_results.json", result_payload)
    _write_json(
        output_dir / "public_extraction_summary.json",
        {key: value for key, value in result_payload.items() if key != "case_results"},
    )
    _write_result_csv(output_dir / "public_extraction_cases.csv", result_rows)
    _write_result_report(output_dir / "public_extraction_report_zh.md", result_payload)
    return {
        "decision": result_payload["decision"],
        "execution_mode": result_payload["execution_mode"],
        "work_item_count": summary["work_item_count"],
        "qvf_ready_item_count": summary["qvf_ready_item_count"],
        "normalized_candidate_count": summary["normalized_candidate_count"],
        "missing_case_count": len(missing_case_ids),
        "api_calls_made": 0,
        "output_files": [
            str(output_dir / "extracted_candidate_memories.jsonl"),
            str(output_dir / "public_extraction_qvf_service_requests.jsonl"),
            str(output_dir / "public_extraction_results.json"),
            str(output_dir / "public_extraction_summary.json"),
            str(output_dir / "public_extraction_cases.csv"),
            str(output_dir / "public_extraction_report_zh.md"),
        ],
    }


def build_extraction_messages(work_item: dict[str, Any]) -> list[dict[str, str]]:
    """Build extractor-model messages without gold-answer fields."""

    safe_item = {
        "case_id": work_item["case_id"],
        "dataset": work_item.get("dataset", ""),
        "source_row_id": work_item.get("source_row_id", ""),
        "question": work_item["question"],
        "history_turns": [
            _safe_history_turn(turn)
            for turn in work_item.get("history_turns", [])
        ],
        "query_focus_hints": _build_query_focus_hints(work_item),
    }
    return [
        {
            "role": "system",
            "content": (
                "Extract candidate long-term memories from dialogue history. Return JSON only. "
                "Do not answer the question. Do not invent facts not supported by history. "
                "Prioritize exact names, titles, dates, places, numbers, and organizations "
                "that are relevant to the question."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "extract_structured_candidate_memories_for_qvf_validity_admission",
                    "instructions": [
                        "Use query_focus_hints as retrieval hints only; all candidate memories must be supported by history_turns.",
                        "If a focus turn contains a concrete value that answers who/what/where/when/how-many, preserve that value as a candidate memory value.",
                        "Prefer small atomic memories over broad summaries; include source_turn_ids for every candidate.",
                        "For stale/current questions, include both older and newer conflicting values when present.",
                    ],
                    "required_json_schema": {
                        "candidate_memories": [
                            {
                                "entity": "string",
                                "slot": "string",
                                "value": "string",
                                "claim": "string",
                                "observed_at": "ISO-8601 string if available",
                                "source_turn_ids": ["string"],
                                "source_confidence": "number 0..1",
                            }
                        ],
                        "query_focus": {
                            "entity": "string if inferable",
                            "slot": "string if inferable",
                            "premise_value": "string if the question embeds a stale/current premise",
                            "needs_current": "boolean only if the question asks for current/latest/still-valid state",
                        },
                    },
                    "work_item": safe_item,
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def _safe_history_turn(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        key: turn[key]
        for key in ["turn_id", "speaker", "timestamp", "session_id", "text"]
        if key in turn
    }


def _build_query_focus_hints(
    work_item: dict[str, Any],
    *,
    top_k: int = DEFAULT_QUERY_FOCUS_HINT_TURNS,
) -> dict[str, Any]:
    question = str(work_item.get("question", ""))
    query_terms = _content_query_tokens(question)
    scored_turns = _score_history_turns_for_question(
        question,
        work_item.get("history_turns", []),
    )
    return {
        "query_terms": query_terms,
        "top_history_turns": [
            {
                **_safe_history_turn(turn),
                "query_overlap_terms": overlap_terms,
                "focus_score": score,
            }
            for score, overlap_terms, turn in scored_turns[:top_k]
            if score > 0
        ],
        "note": (
            "Hints are computed from question/history text only. They are not gold answers."
        ),
    }


def _score_history_turns_for_question(
    question: str,
    turns: Any,
) -> list[tuple[float, list[str], dict[str, Any]]]:
    if not isinstance(turns, list):
        return []
    query_terms = set(_content_query_tokens(question))
    if not query_terms:
        return []
    scored: list[tuple[float, list[str], dict[str, Any]]] = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            continue
        turn_tokens = set(_content_query_tokens(_turn_text(turn)))
        overlap_terms = sorted(query_terms & turn_tokens)
        score = float(len(overlap_terms))
        if score <= 0:
            continue
        score += _focus_specificity_bonus(turn)
        scored.append((round(score, 3), overlap_terms, turn))
    scored.sort(key=lambda item: (-item[0], _history_index(item[2])))
    return scored


def parse_extractor_output(content: str) -> dict[str, Any]:
    """Parse extractor JSON content into a normalized envelope."""

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {
            "parse_ok": False,
            "parse_error": "json_decode_error",
            "candidate_memories": [],
            "query_focus": {},
        }
    if not isinstance(parsed, dict):
        return {
            "parse_ok": False,
            "parse_error": "json_not_object",
            "candidate_memories": [],
            "query_focus": {},
        }
    candidates = parsed.get("candidate_memories", [])
    if not isinstance(candidates, list):
        candidates = []
    query_focus = parsed.get("query_focus", {})
    if not isinstance(query_focus, dict):
        query_focus = {}
    return {
        "parse_ok": True,
        "parse_error": "",
        "candidate_memories": [
            candidate for candidate in candidates if isinstance(candidate, dict)
        ],
        "query_focus": query_focus,
    }


def build_qvf_request_from_extraction(
    work_item: dict[str, Any],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Normalize extracted candidates and build a QVF request if possible."""

    normalized_candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    query_focus = extraction.get("query_focus", {})
    if not isinstance(query_focus, dict):
        query_focus = {}
    for index, candidate in enumerate(extraction.get("candidate_memories", [])):
        try:
            normalized_candidates.append(
                normalize_extracted_candidate(work_item, candidate, index)
            )
        except ValueError as exc:
            rejected_candidates.append(
                {
                    "candidate_index": index,
                    "reason": str(exc),
                }
            )
    normalized_candidates = _dedupe_candidates(normalized_candidates)
    normalized_candidates = _dedupe_candidates(
        normalized_candidates
        + _source_span_repair_candidates(work_item, normalized_candidates)
        + _source_backed_elapsed_event_anchor_candidates(
            work_item,
            normalized_candidates,
        )
    )
    qvf_request = None
    qvf_summary = None
    qvf_forbidden_paths: list[str] = []
    qvf_decisions: list[dict[str, Any]] = []
    if normalized_candidates:
        qvf_request = _build_service_request(
            work_item,
            normalized_candidates,
            query_focus=query_focus,
        )
        qvf_response = run_qvf_service_request(deepcopy(qvf_request))
        qvf_summary = qvf_response["summary"]
        qvf_decisions = [
            result["read_decision"]
            for result in qvf_response["step_report"]["query_report"]["query_results"]
        ]
        qvf_forbidden_paths = model_facing_forbidden_key_paths(
            qvf_response.get("model_facing_sidecar_payloads", [])
        )
    return {
        "case_id": work_item["case_id"],
        "parse_ok": bool(extraction.get("parse_ok")),
        "parse_error": str(extraction.get("parse_error", "")),
        "raw_candidate_count": len(extraction.get("candidate_memories", [])),
        "normalized_candidate_count": len(normalized_candidates),
        "rejected_candidate_count": len(rejected_candidates),
        "rejected_candidates": rejected_candidates,
        "normalized_candidates": normalized_candidates,
        "qvf_ready": qvf_request is not None,
        "qvf_service_request": qvf_request,
        "qvf_summary": qvf_summary,
        "qvf_read_decisions": qvf_decisions,
        "model_facing_forbidden_paths": qvf_forbidden_paths,
    }


def normalize_extracted_candidate(
    work_item: dict[str, Any],
    candidate: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """Convert one extractor candidate into QVF memory schema."""

    entity = _required_string(candidate, "entity")
    slot = _required_string(candidate, "slot")
    value = _required_string(candidate, "value")
    memory_id = str(candidate.get("memory_id") or "").strip()
    if not memory_id:
        memory_id = f"{work_item['case_id']}::extracted_{index:03d}_{_stable_digest(candidate)}"
    source_turn_ids = _string_list(candidate.get("source_turn_ids"))
    observed_at = _source_turn_timestamp(
        work_item,
        {"source_turn_ids": source_turn_ids},
    )
    if not observed_at:
        observed_at = _first_string(candidate, ("observed_at", "timestamp", "date"))
    if observed_at is None:
        observed_at = _observed_at_from_source_turns(work_item, candidate)
    observed_at = _timezone_normalized_observed_at(observed_at)
    source = {
        "source_id": f"{work_item['case_id']}::extractor::{index:03d}",
        "source_type": "public_history_extraction",
        "source_span": _source_span(work_item, source_turn_ids),
        "source_turn_ids": source_turn_ids,
    }
    confidence = candidate.get("source_confidence", candidate.get("confidence"))
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        confidence = DEFAULT_EXTRACTED_SOURCE_CONFIDENCE
    confidence = max(0.0, min(1.0, float(confidence)))
    record = {
        "memory_id": memory_id,
        "entity": entity,
        "slot": slot,
        "value": value,
        "claim": str(candidate.get("claim") or f"{entity} {slot} is {value}."),
        "observed_at": observed_at,
        "valid_from": observed_at,
        "source": source,
        "source_confidence": confidence,
    }
    return normalize_candidate_memory_payloads([record])[0]


def _timezone_normalized_observed_at(value: str) -> str:
    """Normalize extractor datetimes while preserving strict core schema."""

    cleaned = str(value or "").strip()
    if not cleaned:
        return DEFAULT_OBSERVED_AT
    normalized = cleaned.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        public_session_datetime = _normalize_public_session_datetime(cleaned)
        if public_session_datetime:
            return public_session_datetime
        return cleaned
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if "T" not in normalized:
            return f"{normalized}T00:00:00+00:00"
        return f"{normalized}+00:00"
    return normalized


def _normalize_public_session_datetime(value: str) -> str | None:
    match = PUBLIC_SESSION_DATETIME_PATTERN.match(str(value or ""))
    if match is not None:
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        hour = int(match.group("hour") or 0)
        minute = int(match.group("minute") or 0)
        try:
            parsed = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        return parsed.isoformat(timespec="seconds") + "+00:00"
    match = PUBLIC_NATURAL_SESSION_DATETIME_PATTERN.match(str(value or ""))
    if match is None:
        return None
    month_name = match.group("month").lower()
    month = MONTH_NAME_TO_NUMBER.get(month_name)
    if month is None:
        return None
    year = int(match.group("year"))
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = match.group("ampm").lower()
    if hour < 1 or hour > 12:
        return None
    if ampm == "am":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    try:
        parsed = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    return parsed.isoformat(timespec="seconds") + "+00:00"


def _source_span_repair_candidates(
    work_item: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    question = str(work_item.get("question", ""))
    existing_values = {
        _normalize_repair_value(str(candidate.get("value", "")))
        for candidate in candidates
        if str(candidate.get("value", "")).strip()
    }
    generated_signatures: set[tuple[str, str, str]] = set()
    repairs: list[dict[str, Any]] = []
    for candidate in candidates:
        source = candidate.get("source", {})
        if not isinstance(source, dict):
            continue
        source_span = str(source.get("source_span", "")).strip()
        if not source_span:
            continue
        span_values = _source_span_values_for_question(question, source_span)
        if not _source_span_repair_base_candidate(
            question,
            candidate,
        ) and not _has_numeric_range_repair(span_values):
            continue
        for value, repair_kind in span_values:
            normalized_value = _normalize_repair_value(value)
            if not normalized_value or normalized_value in existing_values:
                continue
            if normalized_value in _normalize_repair_value(question):
                continue
            entity, slot = _source_span_repair_entity_slot(
                question,
                candidate,
                repair_kind,
            )
            signature = (entity.lower(), slot.lower(), normalized_value)
            if signature in generated_signatures:
                continue
            generated_signatures.add(signature)
            repairs.append(
                _build_source_span_repair_candidate(
                    work_item,
                    candidate,
                    value,
                    repair_kind,
                    index=len(repairs),
                )
            )
            existing_values.add(normalized_value)
    return repairs


def _source_backed_elapsed_event_anchor_candidates(
    work_item: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    question = str(work_item.get("question", ""))
    if not _elapsed_duration_extraction_question(question):
        return []
    question_tokens = set(_content_query_tokens(question))
    if len(question_tokens) < 3:
        return []
    covered_turn_ids = _candidate_source_turn_ids(candidates)
    existing_signatures = {
        (
            str(candidate.get("slot", "")).lower(),
            _normalize_repair_value(str(candidate.get("value", ""))),
            tuple(_string_list((candidate.get("source") or {}).get("source_turn_ids"))),
        )
        for candidate in candidates
        if isinstance(candidate.get("source"), dict)
    }
    scored_repairs: list[tuple[float, int, dict[str, Any]]] = []
    for index, turn in enumerate(work_item.get("history_turns", [])):
        if not isinstance(turn, dict):
            continue
        turn_id = str(turn.get("turn_id", "")).strip()
        if not turn_id or turn_id in covered_turn_ids:
            continue
        if str(turn.get("speaker", "")).strip().lower() not in {"user", "human"}:
            continue
        turn_text = str(turn.get("text", "")).strip()
        if not turn_text:
            continue
        marker = _event_time_marker(turn_text)
        timestamp = _first_string(turn, ("timestamp", "observed_at", "date"))
        if not marker or not timestamp:
            continue
        normalized_timestamp = _timezone_normalized_observed_at(timestamp)
        event_date = _event_date_from_marker(marker, normalized_timestamp, turn_text)
        if not event_date:
            continue
        turn_tokens = set(_content_query_tokens(turn_text))
        overlap = {
            token
            for token in question_tokens & turn_tokens
            if not _generic_elapsed_anchor_token(token)
        }
        if len(overlap) < 3:
            continue
        entity = _elapsed_event_anchor_entity(question, turn_text, overlap)
        if not entity:
            continue
        signature = ("event_date", _normalize_repair_value(event_date), (turn_id,))
        if signature in existing_signatures:
            continue
        repair = _build_elapsed_event_anchor_candidate(
            work_item,
            turn,
            entity=entity,
            event_date=event_date,
            observed_at=normalized_timestamp,
            marker=marker,
            overlap=sorted(overlap),
            index=len(scored_repairs),
        )
        score = float(len(overlap)) + _elapsed_event_marker_bonus(marker)
        scored_repairs.append((score, _history_index(turn), repair))
    scored_repairs.sort(key=lambda item: (-item[0], item[1]))
    return [
        repair
        for _, _, repair in scored_repairs[:MAX_ELAPSED_EVENT_ANCHOR_REPAIRS]
    ]


def _elapsed_duration_extraction_question(question: str) -> bool:
    return bool(ELAPSED_DURATION_EXTRACTION_QUERY_PATTERN.search(str(question or "")))


def _candidate_source_turn_ids(candidates: list[dict[str, Any]]) -> set[str]:
    turn_ids: set[str] = set()
    for candidate in candidates:
        source = candidate.get("source", {})
        if not isinstance(source, dict):
            continue
        turn_ids.update(_string_list(source.get("source_turn_ids")))
    return turn_ids


def _event_time_marker(text: str) -> str:
    match = EVENT_TIME_MARKER_PATTERN.search(str(text or ""))
    if match:
        return match.group(1).lower()
    explicit = EXPLICIT_SLASH_DATE_PATTERN.search(str(text or ""))
    if explicit:
        return explicit.group(0)
    return ""


def _event_date_from_marker(marker: str, observed_at: str, text: str) -> str:
    explicit = EXPLICIT_SLASH_DATE_PATTERN.search(marker) or EXPLICIT_SLASH_DATE_PATTERN.search(
        str(text or "")
    )
    if explicit:
        try:
            return datetime(
                int(explicit.group("year")),
                int(explicit.group("month")),
                int(explicit.group("day")),
            ).date().isoformat()
        except ValueError:
            return ""
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
    except ValueError:
        return ""
    normalized_marker = marker.lower()
    if normalized_marker == "yesterday" or normalized_marker == "last night":
        return (observed - timedelta(days=1)).date().isoformat()
    if normalized_marker in {"today", "this morning", "this afternoon", "this evening"}:
        return observed.date().isoformat()
    return ""


def _elapsed_event_marker_bonus(marker: str) -> float:
    normalized = marker.lower()
    if normalized in {"today", "yesterday", "last night"}:
        return 1.5
    if EXPLICIT_SLASH_DATE_PATTERN.search(marker):
        return 1.0
    return 0.5


def _elapsed_event_anchor_entity(
    question: str,
    turn_text: str,
    overlap: set[str],
) -> str:
    question_terms = [
        token
        for token in _content_query_tokens(question)
        if token in overlap and not _generic_elapsed_anchor_token(token)
    ]
    if len(question_terms) >= 2:
        return " ".join(question_terms[:5])
    turn_terms = [
        token
        for token in _content_query_tokens(turn_text)
        if token in overlap and not _generic_elapsed_anchor_token(token)
    ]
    if len(turn_terms) >= 2:
        return " ".join(turn_terms[:5])
    return ""


def _generic_elapsed_anchor_token(token: str) -> bool:
    return token in {
        "after",
        "ago",
        "before",
        "been",
        "between",
        "day",
        "days",
        "did",
        "does",
        "done",
        "had",
        "has",
        "have",
        "how",
        "long",
        "many",
        "month",
        "months",
        "much",
        "own",
        "week",
        "weeks",
        "what",
        "where",
        "many",
        "much",
        "when",
        "which",
        "who",
        "today",
        "yesterday",
        "last",
        "this",
    }


def _build_elapsed_event_anchor_candidate(
    work_item: dict[str, Any],
    turn: dict[str, Any],
    *,
    entity: str,
    event_date: str,
    observed_at: str,
    marker: str,
    overlap: list[str],
    index: int,
) -> dict[str, Any]:
    turn_id = str(turn.get("turn_id", "")).strip()
    text = str(turn.get("text", "")).strip()
    payload = {
        "memory_id": (
            f"{work_item['case_id']}::elapsed_event_anchor_{index:03d}_"
            f"{_stable_digest({'turn_id': turn_id, 'event_date': event_date, 'entity': entity})}"
        ),
        "entity": entity,
        "slot": "event_date",
        "value": event_date,
        "claim": f"Source-backed event anchor for {entity} resolves to {event_date}.",
        "observed_at": observed_at,
        "valid_from": observed_at,
        "source": {
            "source_id": f"{work_item['case_id']}::elapsed_event_anchor::{index:03d}",
            "source_type": "public_history_elapsed_event_anchor_repair",
            "source_span": _turn_text_excerpt(turn),
            "source_turn_ids": [turn_id],
            "repair_kind": "elapsed_event_anchor",
            "temporal_marker": marker,
            "query_overlap_tokens": overlap[:8],
        },
        "source_confidence": 0.82,
    }
    return normalize_candidate_memory_payloads([payload])[0]


def _has_numeric_range_repair(values: list[tuple[str, str]]) -> bool:
    return any(
        repair_kind in {"income_range", "savings_range", "numeric_range"}
        for _, repair_kind in values
    )


def _source_span_values_for_question(
    question: str,
    source_span: str,
) -> list[tuple[str, str]]:
    normalized_question = " ".join(question.lower().split())
    numeric_ranges = _extract_numeric_range_values(question, source_span)
    if normalized_question.startswith("where") or " where " in f" {normalized_question} ":
        return numeric_ranges + [
            (value, "where_location")
            for value in _extract_location_like_values(question, source_span)
        ]
    if normalized_question.startswith("what") and "play" in normalized_question:
        return numeric_ranges + [
            (value, "work_title")
            for value in _extract_play_title_values(source_span)
        ]
    return numeric_ranges


def _source_span_repair_base_candidate(question: str, candidate: dict[str, Any]) -> bool:
    text = " ".join(
        str(candidate.get(field, ""))
        for field in ("entity", "slot", "value", "claim")
    )
    if _question_type_candidate_bonus(question, text):
        return True
    question_tokens = set(_query_tokens(question))
    candidate_tokens = set(_query_tokens(text))
    return bool(question_tokens & candidate_tokens)


def _extract_location_like_values(question: str, source_span: str) -> list[str]:
    values: list[str] = []
    for sentence in _candidate_sentences(source_span):
        if not _location_repair_sentence_allowed(question, sentence):
            continue
        values.extend(_extract_location_values_from_sentence(sentence))
    return _dedupe_repair_values(values)


def _extract_location_values_from_sentence(sentence: str) -> list[str]:
    patterns = (
        r"\bshop(?:ped|ping)?\s+at\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,3})",
        r"\b(?:retailers?|stores?|shops?|venues?|restaurants?|theaters?|theatres?|studios?),?\s+like\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,3})",
        r"\bat\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,3})",
        r"\bfrom\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,3})",
    )
    return [
        _clean_repair_value(match.group("value"))
        for pattern in patterns
        for match in re.finditer(pattern, sentence)
    ]


def _location_repair_sentence_allowed(question: str, sentence: str) -> bool:
    normalized_question = question.lower()
    normalized_sentence = sentence.lower()
    location_cues = (
        "address",
        "retailer",
        "retailers",
        "shop",
        "shopping",
        "store",
        "stores",
        "venue",
        "restaurant",
        "theater",
        "theatre",
        "studio",
    )
    if not _contains_any(normalized_sentence, location_cues):
        return False
    if any(term in normalized_question for term in ("redeem", "redeemed", "coupon")):
        return _contains_any(
            normalized_sentence,
            (
                "redeem",
                "redeemed",
                "redeeming",
                "retailer",
                "retailers",
                "shop",
                "shopping",
                "store",
                "stores",
            ),
        )
    question_tokens = set(_query_tokens(question))
    sentence_tokens = set(_query_tokens(sentence))
    return bool(question_tokens & sentence_tokens)


def _candidate_sentences(text: str) -> list[str]:
    rough_sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [sentence.strip() for sentence in rough_sentences if sentence.strip()]


def _extract_play_title_values(source_span: str) -> list[str]:
    patterns = (
        r"(?P<value>(?:[A-Z][A-Za-z0-9'’:-]*|The|A|An)(?:\s+(?:[A-Z][A-Za-z0-9'’:-]*|of|the|and|A|An|The)){0,5})\s+is\s+(?:a|an|the)\s+(?:classic\s+)?play\b",
        r"\bplay\s+(?:called|titled|named)\s+[\"'“”]?(?P<value>[A-Z][^\"'“”.,;:!?]{2,80})",
    )
    return _dedupe_repair_values(
        _clean_repair_value(match.group("value"))
        for pattern in patterns
        for match in re.finditer(pattern, source_span)
    )


def _extract_numeric_range_values(
    question: str,
    source_span: str,
) -> list[tuple[str, str]]:
    if not _numeric_range_repair_allowed(question, source_span):
        return []
    repairs: list[tuple[str, str]] = []
    for sentence in _candidate_sentences(source_span):
        sentence_lower = sentence.lower()
        if not _numeric_range_sentence_allowed(question, sentence):
            continue
        for value, start, end in _numeric_range_matches_from_sentence(sentence):
            repair_kind = _numeric_range_repair_kind(sentence_lower, start, end)
            repairs.append((value, repair_kind))
    return _dedupe_repair_pairs(repairs)


def _numeric_range_repair_allowed(question: str, source_span: str) -> bool:
    text = f"{question} {source_span}".lower()
    cues = (
        "budget",
        "career",
        "change",
        "changed",
        "details",
        "employed",
        "employment",
        "finance",
        "financial",
        "income",
        "job",
        "monthly",
        "pay",
        "salary",
        "savings",
        "update",
        "updated",
    )
    return any(cue in text for cue in cues)


def _numeric_range_sentence_allowed(question: str, sentence: str) -> bool:
    text = f"{question} {sentence}".lower()
    allowed_cues = (
        "budget",
        "finance",
        "financial",
        "income",
        "monthly",
        "pay",
        "salary",
        "savings",
    )
    return any(cue in text for cue in allowed_cues)


def _numeric_range_repair_kind(
    sentence_lower: str,
    start: int | None = None,
    end: int | None = None,
) -> str:
    if start is not None and end is not None:
        income_distance = _closest_numeric_range_cue_distance(
            sentence_lower,
            start,
            end,
            ("income", "salary", "pay", "compensation"),
        )
        savings_distance = _closest_numeric_range_cue_distance(
            sentence_lower,
            start,
            end,
            ("savings", "saved", "balance"),
        )
        if savings_distance < income_distance:
            return "savings_range"
        if income_distance < savings_distance:
            return "income_range"

    if any(cue in sentence_lower for cue in ("income", "salary", "pay", "compensation")):
        return "income_range"
    if any(cue in sentence_lower for cue in ("savings", "saved", "balance")):
        return "savings_range"
    return "numeric_range"


def _closest_numeric_range_cue_distance(
    sentence_lower: str,
    start: int,
    end: int,
    cues: tuple[str, ...],
) -> int:
    best = 10_000
    for cue in cues:
        before = sentence_lower.rfind(cue, 0, start)
        if before >= 0:
            best = min(best, start - (before + len(cue)))
        after = sentence_lower.find(cue, end)
        if after >= 0:
            best = min(best, after - end)
    return best


def _numeric_range_matches_from_sentence(sentence: str) -> list[tuple[str, int, int]]:
    pattern = (
        r"\b(?P<left>\d{1,3}(?:,\d{3})+)"
        r"\s*(?:-|\u2013|\u2014|to|through)\s*"
        r"(?P<right>\d{1,3}(?:,\d{3})+)\b"
    )
    values: list[tuple[str, int, int]] = []
    for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
        left = match.group("left")
        right = match.group("right")
        values.append((f"{left}-{right}", match.start(), match.end()))
    return values


def _numeric_ranges_from_sentence(sentence: str) -> list[str]:
    return [value for value, _, _ in _numeric_range_matches_from_sentence(sentence)]


def _legacy_numeric_ranges_from_sentence(sentence: str) -> list[str]:
    pattern = (
        r"\b(?P<left>\d{1,3}(?:,\d{3})+)"
        r"\s*(?:-|–|—|to|through)\s*"
        r"(?P<right>\d{1,3}(?:,\d{3})+)\b"
    )
    values: list[str] = []
    for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
        left = match.group("left")
        right = match.group("right")
        values.append(f"{left}-{right}")
    return values


def _dedupe_repair_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for value, repair_kind in values:
        normalized = _normalize_repair_value(value)
        key = (normalized, repair_kind)
        if not normalized or key in seen:
            continue
        seen.add(key)
        out.append((value, repair_kind))
    return out


def _build_source_span_repair_candidate(
    work_item: dict[str, Any],
    base_candidate: dict[str, Any],
    value: str,
    repair_kind: str,
    *,
    index: int,
) -> dict[str, Any]:
    entity, slot = _source_span_repair_entity_slot(
        str(work_item.get("question", "")),
        base_candidate,
        repair_kind,
    )
    observed_at = str(base_candidate.get("observed_at") or DEFAULT_OBSERVED_AT)
    source = base_candidate.get("source", {})
    if not isinstance(source, dict):
        source = {}
    source_span = str(source.get("source_span", "")).strip()
    source_turn_ids = _string_list(source.get("source_turn_ids"))
    repair_payload = {
        "memory_id": (
            f"{work_item['case_id']}::source_span_repair_{index:03d}_"
            f"{_stable_digest({'value': value, 'kind': repair_kind, 'source': source_span})}"
        ),
        "entity": entity,
        "slot": slot,
        "value": value,
        "claim": f"{entity} {slot} is {value}.",
        "observed_at": observed_at,
        "valid_from": observed_at,
        "source": {
            "source_id": f"{work_item['case_id']}::source_span_repair::{index:03d}",
            "source_type": "public_history_source_span_repair",
            "source_span": source_span,
            "source_turn_ids": source_turn_ids,
            "repair_kind": repair_kind,
            "base_memory_id": str(base_candidate.get("memory_id", "")),
        },
        "source_confidence": _source_span_repair_confidence(base_candidate),
    }
    return normalize_candidate_memory_payloads([repair_payload])[0]


def _source_span_repair_entity_slot(
    question: str,
    base_candidate: dict[str, Any],
    repair_kind: str,
) -> tuple[str, str]:
    entity = str(base_candidate.get("entity") or "user").strip() or "user"
    if repair_kind == "where_location":
        slot = "location"
        normalized_question = question.lower()
        if any(term in normalized_question for term in ("coupon", "redeem", "redeemed")):
            entity = "coupon"
            slot = "redemption_location"
        return entity, slot
    if repair_kind == "work_title":
        base_slot = str(base_candidate.get("slot") or "").strip()
        if entity.lower() == "play" and base_slot:
            return "play", base_slot
        return "play", "title"
    if repair_kind in {"income_range", "savings_range"}:
        return "user", repair_kind
    if repair_kind == "numeric_range":
        base_slot = str(base_candidate.get("slot") or "").strip()
        if "range" in base_slot.lower():
            return entity, base_slot
        return entity, "numeric_range"
    return entity, str(base_candidate.get("slot") or "value").strip() or "value"


def _source_span_repair_confidence(base_candidate: dict[str, Any]) -> float:
    value = base_candidate.get("source_confidence", DEFAULT_EXTRACTED_SOURCE_CONFIDENCE)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        value = DEFAULT_EXTRACTED_SOURCE_CONFIDENCE
    return min(max(float(value), DEFAULT_EXTRACTED_SOURCE_CONFIDENCE), 0.82)


def _dedupe_repair_values(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = _normalize_repair_value(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(value)
    return out


def _clean_repair_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t\r\n\"'“”.,;:!?()[]{}")
    cleaned = re.sub(r"\b(?:send|exclusive|coupons|offers|promotions)\b.*$", "", cleaned).strip()
    if len(cleaned) < 3 or len(cleaned) > 80:
        return ""
    if not any(char.isupper() for char in cleaned):
        return ""
    if cleaned.split()[0] in {"Many", "Some", "Here", "This", "That", "There"}:
        return ""
    return cleaned


def _normalize_repair_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _build_service_request(
    work_item: dict[str, Any],
    candidate_records: list[dict[str, Any]],
    *,
    query_focus: dict[str, Any],
) -> dict[str, Any]:
    entity, slot = _query_entity_slot(
        candidate_records,
        query_focus,
        question=work_item["question"],
    )
    risk_config = _infer_public_query_risk(work_item["question"], query_focus)
    query_request = {
        "request_id": f"q_{work_item['case_id']}",
        "question": work_item["question"],
        "entity": entity,
        "slot": slot,
        "needs_current": risk_config["needs_current"],
        "risk_profile": risk_config["risk_profile"],
        "risk_inference": risk_config["reason"],
    }
    if risk_config["needs_current"]:
        premise_value = _first_string(
            query_focus,
            ("premise_value", "embedded_premise_value"),
        )
        if premise_value is None:
            premise_value = _premise_value_from_question(
                work_item["question"],
                candidate_records,
            )
        if premise_value:
            query_request["premise_value"] = premise_value
    return {
        "request_id": f"public_extraction_{work_item['case_id']}",
        "step_id": f"public_extraction_step_{work_item['case_id']}",
        "records": candidate_records,
        "query_requests": [query_request],
    }


def _query_entity_slot(
    candidates: list[dict[str, Any]],
    query_focus: dict[str, Any],
    *,
    question: str,
) -> tuple[str, str]:
    entity = _first_string(query_focus, ("entity",))
    slot = _first_string(query_focus, ("slot",))
    candidate_keys = {
        (
            str(candidate.get("entity", "")).strip().lower(),
            str(candidate.get("slot", "")).strip().lower(),
        )
        for candidate in candidates
    }
    focus_key = (
        (entity, slot)
        if entity and slot and (entity.lower(), slot.lower()) in candidate_keys
        else None
    )
    scored_key, scored_value = _question_relevant_candidate_key(candidates, question)
    if focus_key is not None:
        focus_value = _candidate_key_alignment_score(candidates, focus_key, question)
        entity_override_key, _ = _question_entity_override_candidate_key(
            candidates,
            question,
            focus_key,
        )
        if entity_override_key is not None:
            return entity_override_key
        override_key, override_value = _question_type_override_candidate_key(
            candidates,
            question,
            focus_key,
        )
        if override_key is not None and override_value >= focus_value - 1.5:
            return override_key
        if (
            scored_key is not None
            and _focus_slot_alignment_protects_query(
                question,
                focus_key,
                scored_key,
            )
        ):
            return focus_key
        if (
            scored_key is not None
            and scored_value >= focus_value + 1.0
            and not _focus_entity_better_matches_question(
                question,
                focus_key,
                scored_key,
            )
        ):
            return scored_key
        return focus_key
    if scored_key is not None:
        return scored_key
    counts: Counter[tuple[str, str]] = Counter()
    for candidate in candidates:
        candidate_entity = str(candidate.get("entity", "")).strip()
        candidate_slot = str(candidate.get("slot", "")).strip()
        if candidate_entity and candidate_slot:
            counts[(candidate_entity, candidate_slot)] += 1
    if not counts:
        raise ValueError("extracted candidates must include entity and slot")
    return counts.most_common(1)[0][0]


def _question_relevant_candidate_key(
    candidates: list[dict[str, Any]],
    question: str,
) -> tuple[tuple[str, str] | None, float]:
    question_tokens = set(_query_tokens(question))
    if not question_tokens:
        return None, 0.0
    scored: Counter[tuple[str, str]] = Counter()
    first_index: dict[tuple[str, str], int] = {}
    for index, candidate in enumerate(candidates):
        entity = str(candidate.get("entity", "")).strip()
        slot = str(candidate.get("slot", "")).strip()
        if not entity or not slot:
            continue
        key = (entity, slot)
        first_index.setdefault(key, index)
        text = " ".join(
            str(candidate.get(field, ""))
            for field in ("entity", "slot", "value", "claim")
        )
        overlap = question_tokens & set(_query_tokens(text))
        if overlap:
            scored[key] += len(overlap)
        semantic_bonus = _question_type_candidate_bonus(question, text)
        if semantic_bonus:
            scored[key] += semantic_bonus
    if not scored:
        return None, 0.0
    best_key = min(scored, key=lambda key: (-scored[key], first_index[key]))
    return best_key, float(scored[best_key])


def _candidate_key_alignment_score(
    candidates: list[dict[str, Any]],
    key: tuple[str, str],
    question: str,
) -> float:
    score = 0.0
    question_tokens = set(_query_tokens(question))
    for candidate in candidates:
        candidate_key = (
            str(candidate.get("entity", "")).strip(),
            str(candidate.get("slot", "")).strip(),
        )
        if candidate_key != key:
            continue
        text = " ".join(
            str(candidate.get(field, ""))
            for field in ("entity", "slot", "value", "claim")
        )
        score = max(
            score,
            float(len(question_tokens & set(_query_tokens(text))))
            + _question_type_candidate_bonus(question, text),
        )
    return score


def _question_entity_override_candidate_key(
    candidates: list[dict[str, Any]],
    question: str,
    focus_key: tuple[str, str],
) -> tuple[tuple[str, str] | None, float]:
    question_tokens = set(_content_query_tokens(question))
    focus_entity_tokens = set(_content_query_tokens(focus_key[0]))
    focus_entity_overlap = len(question_tokens & focus_entity_tokens)
    focus_slot = focus_key[1].lower()
    best_key: tuple[str, str] | None = None
    best_overlap = focus_entity_overlap
    best_value = 0.0
    first_index: dict[tuple[str, str], int] = {}
    for index, candidate in enumerate(candidates):
        entity = str(candidate.get("entity", "")).strip()
        slot = str(candidate.get("slot", "")).strip()
        if not entity or not slot:
            continue
        key = (entity, slot)
        first_index.setdefault(key, index)
        if key == focus_key or slot.lower() != focus_slot:
            continue
        entity_overlap = len(question_tokens & set(_content_query_tokens(entity)))
        if entity_overlap <= focus_entity_overlap:
            continue
        value = _candidate_key_alignment_score(candidates, key, question)
        if value < 1.0:
            continue
        if (
            best_key is None
            or entity_overlap > best_overlap
            or (
                entity_overlap == best_overlap
                and (
                    value > best_value
                    or (
                        value == best_value
                        and first_index[key] < first_index[best_key]
                    )
                )
            )
        ):
            best_key = key
            best_overlap = entity_overlap
            best_value = value
    return best_key, best_value


def _question_type_override_candidate_key(
    candidates: list[dict[str, Any]],
    question: str,
    focus_key: tuple[str, str],
) -> tuple[tuple[str, str] | None, float]:
    normalized_question = question.lower()
    if not (
        normalized_question.startswith("where")
        or " where " in f" {normalized_question} "
    ):
        return None, 0.0
    if _slot_has_location_semantics(focus_key[1]):
        return None, 0.0
    keys = {
        (
            str(candidate.get("entity", "")).strip(),
            str(candidate.get("slot", "")).strip(),
        )
        for candidate in candidates
        if str(candidate.get("entity", "")).strip()
        and _slot_has_location_semantics(str(candidate.get("slot", "")).strip())
    }
    if not keys:
        return None, 0.0
    scored = {
        key: _candidate_key_alignment_score(candidates, key, question)
        for key in keys
    }
    best_key = max(scored, key=lambda key: scored[key])
    return best_key, float(scored[best_key])


def _focus_entity_better_matches_question(
    question: str,
    focus_key: tuple[str, str],
    scored_key: tuple[str, str],
) -> bool:
    if focus_key == scored_key:
        return False
    question_tokens = set(_content_query_tokens(question))
    focus_overlap = len(question_tokens & set(_content_query_tokens(focus_key[0])))
    scored_overlap = len(question_tokens & set(_content_query_tokens(scored_key[0])))
    return focus_overlap >= scored_overlap + 1


def _focus_slot_alignment_protects_query(
    question: str,
    focus_key: tuple[str, str],
    scored_key: tuple[str, str],
) -> bool:
    if focus_key == scored_key:
        return False
    focus_score = _slot_question_alignment_score(focus_key[1], question)
    if focus_score <= 0:
        return False
    scored_score = _slot_question_alignment_score(scored_key[1], question)
    return focus_score > scored_score


def _slot_question_alignment_score(slot: str, question: str) -> float:
    normalized_slot = str(slot).lower().replace("_", " ")
    normalized_question = " ".join(str(question).lower().split())
    question_tokens = set(_content_query_tokens(normalized_question))
    slot_tokens = set(_content_query_tokens(normalized_slot))
    score = float(len(question_tokens & slot_tokens))
    if _slot_has_residence_semantics(normalized_slot) and any(
        cue in normalized_question
        for cue in (
            "address",
            "city",
            "home",
            "live",
            "lived",
            "location",
            "move",
            "moved",
            "relocated",
            "residence",
        )
    ):
        score += 3.0
    if _slot_has_income_semantics(normalized_slot) and any(
        cue in normalized_question
        for cue in ("income", "monthly", "pay", "salary")
    ):
        score += 3.0
    if "commute" in normalized_slot and "commute" in normalized_question:
        score += 3.0
    if "saving" in normalized_slot and "saving" in normalized_question:
        score += 3.0
    return score


def _question_type_candidate_bonus(question: str, candidate_text: str) -> float:
    normalized_question = question.lower()
    normalized_candidate = candidate_text.lower()
    if normalized_question.startswith("where") or " where " in f" {normalized_question} ":
        return _contains_any(
            normalized_candidate,
            (
                "address",
                "city",
                "location",
                "place",
                "restaurant",
                "school",
                "shop",
                "store",
                "studio",
                "venue",
            ),
        ) * 4.0
    if normalized_question.startswith("when") or " when " in f" {normalized_question} ":
        return _contains_any(
            normalized_candidate,
            (
                "anniversary",
                "birthday",
                "date",
                "day",
                "month",
                "time",
                "year",
            ),
        ) * 3.0
    if normalized_question.startswith("who") or " who " in f" {normalized_question} ":
        return _contains_any(
            normalized_candidate,
            (
                "doctor",
                "friend",
                "manager",
                "name",
                "partner",
                "person",
                "teacher",
            ),
        ) * 2.0
    if normalized_question.startswith("what") and " play" in normalized_question:
        return _contains_any(normalized_candidate, ("name", "play", "title")) * 2.0
    return 0.0


def _slot_has_location_semantics(slot: str) -> bool:
    normalized_slot = slot.lower()
    if _slot_has_residence_semantics(normalized_slot):
        return True
    return any(
        cue in normalized_slot
        for cue in (
            "address",
            "location",
            "place",
            "redemption",
            "restaurant",
            "store",
            "venue",
        )
    )


def _slot_has_residence_semantics(slot: str) -> bool:
    normalized_slot = slot.lower()
    return any(
        cue in normalized_slot
        for cue in (
            "address",
            "city",
            "home",
            "location",
            "residence",
        )
    )


def _slot_has_income_semantics(slot: str) -> bool:
    normalized_slot = slot.lower()
    return any(
        cue in normalized_slot
        for cue in (
            "compensation",
            "income",
            "pay",
            "salary",
        )
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> int:
    return int(any(needle in text for needle in needles))


def _infer_public_query_risk(
    question: str,
    query_focus: dict[str, Any],
) -> dict[str, Any]:
    explicit_needs_current = query_focus.get("needs_current")
    if isinstance(explicit_needs_current, bool):
        normalized_question = " ".join(question.lower().split())
        has_current_cue = any(
            cue in normalized_question for cue in CURRENT_SENSITIVE_QUERY_CUES
        )
        if explicit_needs_current and not has_current_cue:
            return {
                "needs_current": False,
                "risk_profile": "default",
                "reason": "extractor_current_flag_ignored_without_question_cue",
            }
        return {
            "needs_current": explicit_needs_current,
            "risk_profile": "current_sensitive" if explicit_needs_current else "default",
            "reason": "extractor_query_focus_needs_current",
        }
    normalized_question = " ".join(question.lower().split())
    has_current_cue = any(
        cue in normalized_question for cue in CURRENT_SENSITIVE_QUERY_CUES
    )
    if has_current_cue:
        return {
            "needs_current": True,
            "risk_profile": "current_sensitive",
            "reason": "question_contains_current_sensitive_cue",
        }
    return {
        "needs_current": False,
        "risk_profile": "default",
        "reason": "public_question_without_current_sensitive_cue",
    }


def _query_tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in QUERY_TOKEN_PATTERN.finditer(text)]


def _content_query_tokens(text: str) -> list[str]:
    return [
        token
        for token in _query_tokens(text)
        if token not in QUERY_HINT_STOPWORDS and len(token) >= 2
    ]


def _turn_text(turn: dict[str, Any]) -> str:
    return " ".join(
        str(turn.get(field, ""))
        for field in ("speaker", "timestamp", "session_id", "text")
        if str(turn.get(field, "")).strip()
    )


def _history_index(turn: dict[str, Any]) -> int:
    value = turn.get("history_index")
    if isinstance(value, int):
        return value
    return 0


def _focus_specificity_bonus(turn: dict[str, Any]) -> float:
    text = str(turn.get("text", ""))
    bonus = 0.0
    if re.search(r"\b\d{1,4}\b", text):
        bonus += 0.2
    if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text):
        bonus += 0.2
    if any(marker in text for marker in ('"', "'", "“", "”")):
        bonus += 0.1
    return bonus


def _build_preflight(
    *,
    output_dir: Path,
    input_path: Path,
    work_items: list[dict[str, Any]],
    messages_by_case: dict[str, list[dict[str, str]]],
    extractor_model: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    estimated_input_tokens = sum(
        _rough_message_tokens(messages_by_case[item["case_id"]])
        for item in work_items
    )
    estimated_output_tokens = len(work_items) * max_output_tokens
    return {
        "decision": "GO_QVF_PUBLIC_MEMORY_EXTRACTION_PREFLIGHT_READY",
        "execution_mode": "public_memory_extraction_preflight",
        "extraction_version": PUBLIC_EXTRACTION_VERSION,
        "hypothesis": (
            "A fixed extractor model can convert public long-memory raw history into "
            "candidate memories that QVF can then validate and pack before answer generation."
        ),
        "dataset_slice": "public extraction work items generated by qvf-va public-adapter",
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "work_item_count": len(work_items),
        "extractor_model": extractor_model,
        "max_output_tokens": max_output_tokens,
        "expected_call_count": {
            "extractor_calls": len(work_items),
            "total_calls": len(work_items),
        },
        "estimated_token_range": {
            "input_tokens": [
                max(0, int(estimated_input_tokens * 0.75)),
                int(estimated_input_tokens * 1.35),
            ],
            "output_tokens": [
                max_output_tokens,
                estimated_output_tokens,
            ],
        },
        "estimated_cost_usd": [
            round(_estimated_cost_usd(int(estimated_input_tokens * 0.75), max_output_tokens), 6),
            round(_estimated_cost_usd(int(estimated_input_tokens * 1.35), estimated_output_tokens), 6),
        ],
        "health_gates": [
            "preflight file written before API calls",
            "no answer/gold-answer keys are included in extractor messages",
            "extractor responses are parseable JSON or logged as parse failures",
            "normalized candidates pass QVF memory schema validation before service execution",
            "raw outputs remain under ignored local runs directories",
        ],
        "acceptance_criteria": [
            "at least one candidate memory is normalized for non-empty history items",
            "QVF service smoke run succeeds for every item with normalized candidates",
            "model-facing sidecar payloads have no internal forbidden keys",
        ],
        "api_calls_made": 0,
    }


def _result_row(
    work_item: dict[str, Any],
    extraction: dict[str, Any],
    result: dict[str, Any],
    timed_response: dict[str, Any],
) -> dict[str, Any]:
    usage = timed_response.get("usage", {})
    return {
        "case_id": work_item["case_id"],
        "dataset": work_item.get("dataset", ""),
        "parse_ok": bool(extraction.get("parse_ok")),
        "parse_error": str(extraction.get("parse_error", "")),
        "raw_candidate_count": result["raw_candidate_count"],
        "normalized_candidate_count": result["normalized_candidate_count"],
        "rejected_candidate_count": result["rejected_candidate_count"],
        "qvf_ready": result["qvf_ready"],
        "qvf_decisions": result["qvf_read_decisions"],
        "model_facing_forbidden_path_count": len(result["model_facing_forbidden_paths"]),
        "latency_seconds": timed_response["latency_seconds"],
        "input_tokens": int(usage.get("prompt_tokens", 0)),
        "output_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }


def _summarize_results(
    *,
    rows: list[dict[str, Any]],
    extractor_model: str,
    api_calls_made: int | None = None,
) -> dict[str, Any]:
    input_tokens = sum(row["input_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    actual_api_calls = len(rows) if api_calls_made is None else api_calls_made
    return {
        "decision": "GO_QVF_PUBLIC_MEMORY_EXTRACTION_SUMMARY_READY",
        "extraction_version": PUBLIC_EXTRACTION_VERSION,
        "extractor_model": extractor_model,
        "work_item_count": len(rows),
        "parse_ok_count": sum(1 for row in rows if row["parse_ok"]),
        "qvf_ready_item_count": sum(1 for row in rows if row["qvf_ready"]),
        "raw_candidate_count": sum(row["raw_candidate_count"] for row in rows),
        "normalized_candidate_count": sum(row["normalized_candidate_count"] for row in rows),
        "rejected_candidate_count": sum(row["rejected_candidate_count"] for row in rows),
        "model_facing_forbidden_path_count": sum(
            row["model_facing_forbidden_path_count"] for row in rows
        ),
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "estimated_usd": _estimated_cost_usd(input_tokens, output_tokens),
        "mean_latency_seconds": _mean([row["latency_seconds"] for row in rows]),
        "api_calls_made": actual_api_calls,
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        memory_id = candidate["memory_id"]
        if memory_id in seen:
            continue
        seen.add(memory_id)
        out.append(candidate)
    return out


def _observed_at_from_source_turns(work_item: dict[str, Any], candidate: dict[str, Any]) -> str:
    timestamp = _source_turn_timestamp(work_item, candidate)
    if timestamp:
        return timestamp
    return DEFAULT_OBSERVED_AT


def _source_turn_timestamp(work_item: dict[str, Any], candidate: dict[str, Any]) -> str:
    source_turn_ids = set(_string_list(candidate.get("source_turn_ids")))
    for turn in work_item.get("history_turns", []):
        turn_id = str(turn.get("turn_id", ""))
        if source_turn_ids and turn_id not in source_turn_ids:
            continue
        timestamp = _first_string(turn, ("timestamp",))
        if timestamp:
            return timestamp
    return ""


def _source_span(work_item: dict[str, Any], source_turn_ids: list[str]) -> str:
    if not source_turn_ids:
        return ""
    turn_texts = [
        _turn_text_excerpt(turn)
        for turn in _rank_source_span_turns(
            work_item,
            source_turn_ids,
            _source_neighborhood_turns(
                work_item,
                source_turn_ids,
                radius=DEFAULT_SOURCE_NEIGHBOR_RADIUS,
            ),
        )
        if _turn_text_excerpt(turn)
    ]
    return " ".join(turn_texts)[:DEFAULT_SOURCE_SPAN_MAX_CHARS]


def _rank_source_span_turns(
    work_item: dict[str, Any],
    source_turn_ids: list[str],
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    wanted = set(source_turn_ids)
    exact = [
        turn
        for turn in turns
        if str(turn.get("turn_id", "")) in wanted
    ]
    exact_ids = {id(turn) for turn in exact}
    neighbors = [turn for turn in turns if id(turn) not in exact_ids]
    scored_neighbors = [
        turn
        for score, _overlap, turn in _score_history_turns_for_question(
            str(work_item.get("question", "")),
            neighbors,
        )
        if score > 0
    ]
    if not scored_neighbors:
        scored_neighbors = neighbors[:3]
    return exact + scored_neighbors[:3]


def _turn_text_excerpt(turn: dict[str, Any]) -> str:
    text = str(turn.get("text", "")).strip()
    if len(text) <= DEFAULT_SOURCE_TURN_MAX_CHARS:
        return text
    return text[:DEFAULT_SOURCE_TURN_MAX_CHARS].rstrip()


def _source_neighborhood_turns(
    work_item: dict[str, Any],
    source_turn_ids: list[str],
    *,
    radius: int,
) -> list[dict[str, Any]]:
    turns = [
        turn
        for turn in work_item.get("history_turns", [])
        if isinstance(turn, dict)
    ]
    if not turns:
        return []
    wanted = set(source_turn_ids)
    source_indexes = [
        index
        for index, turn in enumerate(turns)
        if str(turn.get("turn_id", "")) in wanted
    ]
    if not source_indexes:
        return []
    selected_indexes: set[int] = set(source_indexes)
    for source_index in source_indexes:
        source_turn = turns[source_index]
        source_history_index = _optional_int(source_turn.get("history_index"))
        source_session = _turn_session_key(source_turn)
        for index, candidate in enumerate(turns):
            if index in selected_indexes:
                continue
            if _turn_session_key(candidate) != source_session:
                continue
            candidate_history_index = _optional_int(candidate.get("history_index"))
            if source_history_index is not None and candidate_history_index is not None:
                if abs(candidate_history_index - source_history_index) <= radius:
                    selected_indexes.add(index)
            elif abs(index - source_index) <= radius:
                selected_indexes.add(index)
    return [turns[index] for index in sorted(selected_indexes)]


def _turn_session_key(turn: dict[str, Any]) -> str:
    session_id = str(turn.get("session_id", "")).strip()
    if session_id:
        return session_id
    turn_id = str(turn.get("turn_id", ""))
    match = re.match(r"^(.*)\[\d+\]$", turn_id)
    return match.group(1) if match else ""


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _premise_value_from_question(question: str, candidates: list[dict[str, Any]]) -> str | None:
    normalized_question = question.lower()
    matched_values = [
        str(candidate.get("value", "")).strip()
        for candidate in candidates
        if str(candidate.get("value", "")).strip()
        and str(candidate.get("value", "")).strip().lower() in normalized_question
    ]
    if not matched_values:
        return None
    return max(matched_values, key=len)


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _first_string(payload: dict[str, Any], field_names: tuple[str, ...]) -> str | None:
    for field_name in field_names:
        value = payload.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _stable_digest(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    import hashlib

    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]


def _call_with_timing(
    client: "_OpenAIChatClient",
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.chat(model=model, messages=messages, max_tokens=max_tokens)
    return {
        "response": response,
        "latency_seconds": time.perf_counter() - started,
        "usage": response.get("usage", {}),
    }


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content", ""))


class _OpenAIChatClient:
    def __init__(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for --run-api")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base_url}/chat/completions"
        self.api_key = api_key

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc


def _rough_message_tokens(messages: list[dict[str, str]]) -> int:
    return max(1, len(json.dumps(messages, ensure_ascii=False)) // 4)


def _estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * GPT_4O_MINI_ESTIMATED_INPUT_USD_PER_1M
        + output_tokens / 1_000_000 * GPT_4O_MINI_ESTIMATED_OUTPUT_USD_PER_1M
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_preflight_report(path: Path, preflight: dict[str, Any]) -> None:
    lines = [
        "# QVF 公开数据记忆抽取 preflight",
        "",
        f"- Hypothesis: {preflight['hypothesis']}",
        f"- Dataset slice: {preflight['dataset_slice']}",
        f"- Work items: {preflight['work_item_count']}",
        f"- Extractor model: `{preflight['extractor_model']}`",
        f"- Expected calls: {preflight['expected_call_count']['total_calls']}",
        f"- Estimated cost USD: {preflight['estimated_cost_usd']}",
        "",
        "## Acceptance Criteria",
        "",
    ]
    lines.extend(f"- {item}" for item in preflight["acceptance_criteria"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_result_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "dataset",
        "parse_ok",
        "parse_error",
        "raw_candidate_count",
        "normalized_candidate_count",
        "rejected_candidate_count",
        "qvf_ready",
        "model_facing_forbidden_path_count",
        "latency_seconds",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def _write_result_report(path: Path, result: dict[str, Any]) -> None:
    summary = result["summary"]
    lines = [
        "# QVF 公开数据记忆抽取运行",
        "",
        f"- Extractor model: `{summary['extractor_model']}`",
        f"- Work items: {summary['work_item_count']}",
        f"- Parse OK: {summary['parse_ok_count']}",
        f"- QVF-ready items: {summary['qvf_ready_item_count']}",
        f"- Normalized candidates: {summary['normalized_candidate_count']}",
        f"- API calls: {result['api_calls_made']}",
        f"- Estimated USD: {summary['estimated_usd']:.6f}",
        "",
        "这是公开 benchmark pilot 的抽取/证据构建通路，不是 final answer-model accuracy。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DEFAULT_EXTRACTOR_MAX_OUTPUT_TOKENS",
    "DEFAULT_EXTRACTOR_MODEL",
    "DEFAULT_PUBLIC_EXTRACTION_LIMIT",
    "PUBLIC_EXTRACTION_VERSION",
    "build_extraction_messages",
    "build_qvf_request_from_extraction",
    "load_extraction_work_items",
    "normalize_extracted_candidate",
    "parse_extractor_output",
    "replay_public_extraction_outputs",
    "run_public_extraction_eval",
    "validate_extraction_work_items",
]
