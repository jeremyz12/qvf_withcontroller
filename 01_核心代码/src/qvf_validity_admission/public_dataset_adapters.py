"""Adapters for public long-memory benchmark records.

This module does not pretend that raw LongMemEval/LoCoMo conversations are
already QVF memories. It separates two paths:

* raw-history items become extraction work items for a later retriever/parser;
* rows that already contain structured candidate memories become QVF service
  requests that can run through validity admission immediately.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from .analysis_pipeline import normalize_candidate_memory_payloads
from .answer_matching import answer_text_paths
from .decisions import model_facing_forbidden_key_paths
from .service import run_qvf_service_request

PUBLIC_DATASET_ADAPTER_VERSION = "qvf_public_dataset_adapter_v0.1"
SUPPORTED_PUBLIC_DATASETS = ("auto", "longmemeval", "longmemeval-s", "locomo")
DEFAULT_PUBLIC_PILOT_LIMIT = 20
DEFAULT_MAX_HISTORY_TURNS = 80
DEFAULT_HISTORY_SELECTION = "query_bm25"
HISTORY_SELECTION_METHODS = (
    "head",
    "query_bm25",
    "query_bm25_window",
    "query_change_update_domain",
)
DEFAULT_QUERY_BM25_WINDOW_RADIUS = 1
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
MUTABLE_STATE_DOMAINS: tuple[dict[str, tuple[str, ...]], ...] = (
    {
        "triggers": ("career", "job", "work", "employment", "employed", "company", "income"),
        "terms": (
            "career",
            "job",
            "role",
            "position",
            "occupation",
            "profession",
            "employed",
            "employment",
            "work",
            "works",
            "working",
            "employer",
            "company",
            "income",
            "salary",
            "pay",
            "wage",
        ),
        "phrases": (
            "employed as",
            "works as",
            "working as",
            "started as",
            "started a role",
            "started a job",
            "new role",
            "new position",
            "new job",
            "joined",
            "hired as",
            "income",
            "salary",
            "pay",
        ),
    },
    {
        "triggers": ("relationship", "marital", "dating", "divorced", "married", "partner", "spouse"),
        "terms": (
            "relationship",
            "marital",
            "dating",
            "divorced",
            "married",
            "partner",
            "spouse",
            "engaged",
            "single",
        ),
        "phrases": (
            "started dating",
            "began dating",
            "got married",
            "married",
            "divorced",
            "separated",
            "broke up",
            "partner",
            "spouse",
            "engaged",
            "single",
        ),
    },
    {
        "triggers": ("live", "lives", "residence", "moved", "relocated", "location", "city", "address", "home"),
        "terms": (
            "live",
            "lives",
            "living",
            "moved",
            "relocated",
            "city",
            "home",
            "address",
            "residence",
            "location",
        ),
        "phrases": (
            "moved to",
            "relocated to",
            "living in",
            "live in",
            "lives in",
            "new address",
            "new home",
            "based in",
            "staying in",
        ),
    },
    {
        "triggers": ("change", "changed", "current", "currently", "now", "status", "update", "updated"),
        "terms": (
            "change",
            "changed",
            "current",
            "currently",
            "now",
            "new",
            "started",
            "became",
            "update",
            "updated",
            "status",
        ),
        "phrases": (
            "quick update",
            "i just started",
            "started a new",
            "i am now",
            "i m now",
            "became",
            "currently",
            "current",
            "as of",
            "no longer",
            "recently",
        ),
    },
)

QUESTION_FIELDS = (
    "question",
    "query",
    "question_text",
    "input",
    "prompt",
)
ANSWER_FIELDS = (
    "answer",
    "answers",
    "adversarial_answer",
    "gold_answer",
    "reference_answer",
    "target",
    "targets",
    "expected_answer",
)
ROW_ID_FIELDS = (
    "id",
    "case_id",
    "question_id",
    "sample_id",
    "conversation_id",
    "dialogue_id",
)
QA_LIST_FIELDS = (
    "qa",
    "qas",
    "qa_pairs",
    "questions",
    "question_answers",
)
HISTORY_FIELDS = (
    "haystack_sessions",
    "sessions",
    "conversation",
    "conversations",
    "messages",
    "chat_history",
    "history",
    "dialogue",
    "transcript",
    "long_context",
    "context",
)
CANDIDATE_MEMORY_FIELDS = (
    "qvf_candidates",
    "candidate_memories",
    "memory_candidates",
    "memories",
    "facts",
    "retrieved_memories",
    "evidence_memories",
)
TEXT_FIELDS = (
    "text",
    "content",
    "message",
    "utterance",
    "value",
)
TIMESTAMP_FIELDS = (
    "observed_at",
    "timestamp",
    "time",
    "date",
    "created_at",
)
SPEAKER_FIELDS = (
    "speaker",
    "role",
    "name",
    "from",
)
PUBLIC_ANSWER_KEY_NAMES = {field.lower() for field in ANSWER_FIELDS}


def load_public_dataset_rows(path: Path) -> list[dict[str, Any]]:
    """Load a JSON/JSONL public benchmark file into top-level rows."""

    return _coerce_public_rows(_load_json_object_array_or_jsonl(path), source_label=str(path))


def load_public_case_ids(path: Path) -> set[str]:
    """Load a JSON/JSONL list of public case ids for adapter filtering."""

    payload = _load_json_object_array_or_jsonl(path)
    if isinstance(payload, dict):
        for field_name in ("case_ids", "ids", "covered_full_history_answer_case_ids"):
            if isinstance(payload.get(field_name), list):
                payload = payload[field_name]
                break
    if not isinstance(payload, list):
        raise ValueError("case ids file must contain a JSON list or an object with case_ids")
    case_ids = {str(case_id).strip() for case_id in payload if str(case_id).strip()}
    if not case_ids:
        raise ValueError("case ids file did not contain any non-empty ids")
    return case_ids


def build_public_dataset_pilot(
    rows: list[dict[str, Any]],
    *,
    dataset: str = "auto",
    limit: int = DEFAULT_PUBLIC_PILOT_LIMIT,
    max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS,
    history_selection: str = DEFAULT_HISTORY_SELECTION,
    include_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build public-dataset pilot artifacts without model calls."""

    dataset_name = _validate_dataset(dataset)
    history_selection_method = _validate_history_selection(history_selection)
    _validate_positive_int(limit, "limit")
    _validate_positive_int(max_history_turns, "max_history_turns")
    rows = _coerce_public_rows(rows, source_label="rows")
    public_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    for source_index, row in enumerate(rows):
        for qa_index, qa_payload in enumerate(_iter_qa_payloads(row)):
            if len(public_items) >= limit:
                break
            try:
                item = adapt_public_dataset_item(
                    row,
                    qa_payload=qa_payload,
                    dataset=dataset_name,
                    source_index=source_index,
                    qa_index=qa_index,
                    max_history_turns=max_history_turns,
                    history_selection=history_selection_method,
                )
                if (
                    include_case_ids is not None
                    and item["case_id"] not in include_case_ids
                ):
                    continue
                public_items.append(item)
            except ValueError as exc:
                skipped_items.append(
                    {
                        "source_index": source_index,
                        "qa_index": qa_index,
                        "reason": str(exc),
                    }
                )
        if len(public_items) >= limit:
            break
    if not public_items:
        raise ValueError("public dataset pilot produced no usable items")
    summary = _public_pilot_summary(
        dataset=dataset_name,
        rows_received=len(rows),
        items=public_items,
        skipped_items=skipped_items,
    )
    summary["include_case_id_count"] = (
        len(include_case_ids) if include_case_ids is not None else None
    )
    return {
        "decision": "GO_QVF_PUBLIC_DATASET_ADAPTER_READY_NO_API",
        "execution_mode": "qvf_public_dataset_adapter_pilot",
        "adapter_version": PUBLIC_DATASET_ADAPTER_VERSION,
        "dataset": dataset_name,
        "limit": limit,
        "max_history_turns": max_history_turns,
        "history_selection": history_selection_method,
        "include_case_id_count": (
            len(include_case_ids) if include_case_ids is not None else None
        ),
        "items": public_items,
        "skipped_items": skipped_items,
        "summary": summary,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API public-dataset adapter and pilot-pack builder.",
            "Raw histories are queued for extraction; only structured candidate memories are run through QVF.",
            "This is engineering readiness for public benchmark evaluation, not broad model-accuracy evidence.",
        ],
    }


def adapt_public_dataset_item(
    row: dict[str, Any],
    *,
    qa_payload: dict[str, Any] | None = None,
    dataset: str = "auto",
    source_index: int = 0,
    qa_index: int = 0,
    max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS,
    history_selection: str = DEFAULT_HISTORY_SELECTION,
) -> dict[str, Any]:
    """Adapt one public benchmark question into a QVF-ready or extraction item."""

    dataset_name = _validate_dataset(dataset)
    history_selection_method = _validate_history_selection(history_selection)
    _validate_positive_int(max_history_turns, "max_history_turns")
    if not isinstance(row, dict):
        raise ValueError("public dataset row must be an object")
    if qa_payload is not None and not isinstance(qa_payload, dict):
        raise ValueError("public dataset qa payload must be an object")
    qa = qa_payload or row
    question = _first_string(qa, QUESTION_FIELDS) or _first_string(row, QUESTION_FIELDS)
    if question is None:
        raise ValueError("public dataset item has no question/query text")
    answers = _extract_answers(qa) or _extract_answers(row)
    source_row_id = _source_row_id(row, source_index)
    case_id = _public_case_id(dataset_name, source_row_id, qa, qa_index)
    all_history_turns = _extract_all_history_turns(row)
    history_turns = _select_history_turns(
        question,
        all_history_turns,
        max_history_turns=max_history_turns,
        history_selection=history_selection_method,
    )
    candidates = _extract_candidate_memory_payloads(row, qa)
    item: dict[str, Any] = {
        "case_id": case_id,
        "dataset": dataset_name,
        "source_row_id": source_row_id,
        "qa_index": qa_index,
        "question": question,
        "answers": answers,
        "total_history_turn_count": len(all_history_turns),
        "selected_history_turn_count": len(history_turns),
        "raw_history_turn_count": len(history_turns),
        "history_selection": history_selection_method,
        "candidate_memory_count": len(candidates),
        "qvf_ready": False,
        "warnings": [],
        "api_calls_made": 0,
    }
    if len(all_history_turns) > max_history_turns:
        if history_selection_method == "head":
            item["warnings"].append("history_truncated_to_max_history_turns")
        else:
            item["warnings"].append(
                f"history_selected_by_{history_selection_method}"
            )
    extraction_work_item = _build_extraction_work_item(
        case_id=case_id,
        dataset=dataset_name,
        source_row_id=source_row_id,
        question=question,
        history_turns=history_turns,
        total_history_turn_count=len(all_history_turns),
        history_selection=history_selection_method,
    )
    item["extraction_work_item"] = extraction_work_item
    if not candidates:
        item["warnings"].append("raw_history_requires_candidate_memory_extraction")
        item["leakage_report"] = _leakage_report(
            answers=answers,
            extraction_work_item=extraction_work_item,
            qvf_request=None,
            sidecar_payloads=[],
        )
        return item

    normalized_candidates = normalize_candidate_memory_payloads(candidates)
    qvf_request = _build_qvf_service_request(
        case_id=case_id,
        question=question,
        candidate_records=normalized_candidates,
    )
    response = run_qvf_service_request(deepcopy(qvf_request))
    item.update(
        {
            "qvf_ready": True,
            "qvf_service_request": qvf_request,
            "qvf_summary": response["summary"],
            "qvf_read_decisions": [
                result["read_decision"]
                for result in response["step_report"]["query_report"]["query_results"]
            ],
        }
    )
    item["leakage_report"] = _leakage_report(
        answers=answers,
        extraction_work_item=extraction_work_item,
        qvf_request=qvf_request,
        sidecar_payloads=response.get("model_facing_sidecar_payloads", []),
    )
    return item


def write_public_dataset_adapter_pilot(
    output_dir: Path,
    *,
    rows: list[dict[str, Any]] | None = None,
    input_path: Path | None = None,
    dataset: str = "auto",
    limit: int = DEFAULT_PUBLIC_PILOT_LIMIT,
    max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS,
    history_selection: str = DEFAULT_HISTORY_SELECTION,
    include_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Write public dataset adapter artifacts."""

    if rows is None:
        if input_path is None:
            raise ValueError("rows or input_path is required")
        rows = load_public_dataset_rows(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    pilot = build_public_dataset_pilot(
        rows,
        dataset=dataset,
        limit=limit,
        max_history_turns=max_history_turns,
        history_selection=history_selection,
        include_case_ids=include_case_ids,
    )
    if input_path is not None:
        pilot["input_file_name"] = input_path.name
        pilot["summary"]["input_file_name"] = input_path.name
    extraction_items = [
        item["extraction_work_item"]
        for item in pilot["items"]
        if item.get("extraction_work_item") is not None
    ]
    qvf_requests = [
        item["qvf_service_request"]
        for item in pilot["items"]
        if item.get("qvf_service_request") is not None
    ]
    files = {
        "items": output_dir / "public_dataset_items.json",
        "summary": output_dir / "public_dataset_summary.json",
        "extraction_work_items": output_dir / "public_dataset_extraction_work_items.jsonl",
        "qvf_service_requests": output_dir / "public_dataset_qvf_service_requests.jsonl",
        "cases_csv": output_dir / "public_dataset_cases.csv",
        "report_zh": output_dir / "public_dataset_report_zh.md",
    }
    _write_json(files["items"], pilot)
    _write_json(files["summary"], pilot["summary"])
    _write_jsonl(files["extraction_work_items"], extraction_items)
    _write_jsonl(files["qvf_service_requests"], qvf_requests)
    _write_cases_csv(files["cases_csv"], pilot["items"])
    _write_report_zh(files["report_zh"], pilot)
    return {
        "decision": "GO_QVF_PUBLIC_DATASET_ADAPTER_ARTIFACTS_READY_NO_API",
        "execution_mode": "qvf_public_dataset_adapter_writer",
        "adapter_version": PUBLIC_DATASET_ADAPTER_VERSION,
        "dataset": pilot["dataset"],
        "history_selection": pilot["history_selection"],
        "include_case_id_count": pilot["include_case_id_count"],
        "files": {key: str(path) for key, path in files.items()},
        "item_count": pilot["summary"]["item_count"],
        "qvf_ready_item_count": pilot["summary"]["qvf_ready_item_count"],
        "extraction_required_item_count": pilot["summary"][
            "extraction_required_item_count"
        ],
        "api_calls_made": 0,
    }


def _coerce_public_rows(payload: Any, *, source_label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if (
            len(payload) == 1
            and isinstance(payload[0], dict)
            and any(isinstance(payload[0].get(field_name), list) for field_name in ("data", "examples", "records", "rows", "items"))
        ):
            return _coerce_public_rows(payload[0], source_label=source_label)
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for field_name in ("data", "examples", "records", "rows", "items"):
            if isinstance(payload.get(field_name), list):
                rows = payload[field_name]
                break
        if rows is None:
            rows = [payload]
    else:
        raise ValueError(f"{source_label} must be a JSON object or list")
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{source_label}[{index}] must be an object")
        normalized_rows.append(row)
    return normalized_rows


def _load_json_object_array_or_jsonl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        # JSON strings may contain Unicode line separators such as U+2028.
        # Treat only physical LF as JSONL row boundaries.
        for line in text.split("\n"):
            line = line.strip()
            if line:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("JSONL public dataset rows must be objects")
                rows.append(value)
        return rows


def _iter_qa_payloads(row: dict[str, Any]) -> list[dict[str, Any] | None]:
    for field_name in QA_LIST_FIELDS:
        value = row.get(field_name)
        if not isinstance(value, list) or not value:
            continue
        qa_payloads: list[dict[str, Any] | None] = []
        for question_index, item in enumerate(value):
            if isinstance(item, dict):
                if _first_string(item, QUESTION_FIELDS):
                    qa_payloads.append(item)
            elif isinstance(item, str) and item.strip():
                qa_payloads.append(
                    {
                        "question_id": f"{field_name}_{question_index}",
                        "question": item.strip(),
                    }
                )
        if qa_payloads:
            return qa_payloads
    return [None]


def _extract_all_history_turns(row: dict[str, Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    handled_history_fields: set[str] = set()
    if _walk_parallel_session_history(row, turns, path="$"):
        handled_history_fields.add("haystack_sessions")
    for field_name in HISTORY_FIELDS:
        if field_name in handled_history_fields:
            continue
        if field_name in row:
            _walk_history(row[field_name], turns, path=f"$.{field_name}")
    if not turns and any(field in row for field in TEXT_FIELDS):
        _walk_history(row, turns, path="$")
    for index, turn in enumerate(turns):
        turn.setdefault("history_index", index)
    return turns


def _walk_parallel_session_history(
    row: dict[str, Any],
    turns: list[dict[str, Any]],
    *,
    path: str,
) -> bool:
    """Walk LongMemEval-style parallel session/date/id arrays."""

    sessions = row.get("haystack_sessions")
    if not isinstance(sessions, list) or not sessions:
        return False
    dates = row.get("haystack_dates")
    session_ids = row.get("haystack_session_ids")
    has_parallel_metadata = isinstance(dates, list) or isinstance(session_ids, list)
    if not has_parallel_metadata:
        return False
    for session_index, session in enumerate(sessions):
        timestamp = _parallel_string_at(dates, session_index)
        session_id = _parallel_string_at(session_ids, session_index)
        session_turns = session if isinstance(session, list) else [session]
        for turn_index, item in enumerate(session_turns):
            turn_path = f"{path}.haystack_sessions[{session_index}][{turn_index}]"
            if isinstance(item, dict):
                enriched = deepcopy(item)
                if timestamp:
                    enriched.setdefault("timestamp", timestamp)
                if session_id:
                    enriched.setdefault("session_id", session_id)
            else:
                enriched = {"text": item}
                if timestamp:
                    enriched["timestamp"] = timestamp
                if session_id:
                    enriched["session_id"] = session_id
            _walk_history(enriched, turns, path=turn_path)
    return True


def _parallel_string_at(value: Any, index: int) -> str | None:
    if not isinstance(value, list) or index >= len(value):
        return None
    item = value[index]
    if isinstance(item, str) and item.strip():
        return item.strip()
    return None


def _select_history_turns(
    question: str,
    turns: list[dict[str, Any]],
    *,
    max_history_turns: int,
    history_selection: str,
) -> list[dict[str, Any]]:
    if len(turns) <= max_history_turns:
        return deepcopy(turns)
    if history_selection == "head":
        selected = deepcopy(turns[:max_history_turns])
        for rank, turn in enumerate(selected, start=1):
            turn["selection_rank"] = rank
            turn["selection_score"] = 0.0
        return selected
    if history_selection == "query_bm25_window":
        return _select_query_bm25_window(
            question,
            turns,
            max_history_turns=max_history_turns,
            window_radius=DEFAULT_QUERY_BM25_WINDOW_RADIUS,
        )
    if history_selection == "query_change_update_domain":
        return _select_query_change_update_domain(
            question,
            turns,
            max_history_turns=max_history_turns,
        )
    scored_turns = _score_turns_by_query_bm25(question, turns)
    if not scored_turns or scored_turns[0]["selection_score"] <= 0:
        selected = deepcopy(turns[:max_history_turns])
        for rank, turn in enumerate(selected, start=1):
            turn["selection_rank"] = rank
            turn["selection_score"] = 0.0
        return selected
    top_scored = scored_turns[:max_history_turns]
    ranked_by_index = {
        turn["history_index"]: rank
        for rank, turn in enumerate(top_scored, start=1)
    }
    selected_by_index = {turn["history_index"]: turn for turn in top_scored}
    selected: list[dict[str, Any]] = []
    for turn in turns:
        history_index = turn.get("history_index")
        if history_index not in selected_by_index:
            continue
        selected_turn = deepcopy(selected_by_index[history_index])
        selected_turn["selection_rank"] = ranked_by_index[history_index]
        selected.append(selected_turn)
    return selected


def _select_query_change_update_domain(
    question: str,
    turns: list[dict[str, Any]],
    *,
    max_history_turns: int,
) -> list[dict[str, Any]]:
    scored_turns = _score_turns_by_query_change_update_domain(question, turns)
    if not scored_turns or scored_turns[0]["selection_score"] <= 0:
        selected = deepcopy(turns[:max_history_turns])
        for rank, turn in enumerate(selected, start=1):
            turn["selection_rank"] = rank
            turn["selection_score"] = 0.0
        return selected
    top_scored = scored_turns[:max_history_turns]
    ranked_by_index = {
        turn["history_index"]: rank
        for rank, turn in enumerate(top_scored, start=1)
    }
    selected_by_index = {turn["history_index"]: turn for turn in top_scored}
    selected: list[dict[str, Any]] = []
    for turn in turns:
        history_index = turn.get("history_index")
        if history_index not in selected_by_index:
            continue
        selected_turn = deepcopy(selected_by_index[history_index])
        selected_turn["selection_rank"] = ranked_by_index[history_index]
        selected.append(selected_turn)
    return selected


def _select_query_bm25_window(
    question: str,
    turns: list[dict[str, Any]],
    *,
    max_history_turns: int,
    window_radius: int,
) -> list[dict[str, Any]]:
    scored_turns = _score_turns_by_query_bm25(question, turns)
    if not scored_turns or scored_turns[0]["selection_score"] <= 0:
        selected = deepcopy(turns[:max_history_turns])
        for rank, turn in enumerate(selected, start=1):
            turn["selection_rank"] = rank
            turn["selection_score"] = 0.0
            turn["selection_anchor_index"] = None
            turn["selection_window_offset"] = 0
        return selected
    score_by_index = {
        int(turn.get("history_index", index)): float(turn.get("selection_score", 0.0))
        for index, turn in enumerate(scored_turns)
    }
    rank_by_index = {
        int(turn.get("history_index", 0)): rank
        for rank, turn in enumerate(scored_turns, start=1)
    }
    selected_indices: dict[int, tuple[int, int]] = {}
    for anchor in scored_turns:
        anchor_index = int(anchor.get("history_index", 0))
        if float(anchor.get("selection_score", 0.0)) <= 0 and selected_indices:
            continue
        offsets = [0]
        for radius in range(1, window_radius + 1):
            offsets.extend([radius, -radius])
        for offset in offsets:
            candidate_index = anchor_index + offset
            if candidate_index < 0 or candidate_index >= len(turns):
                continue
            selected_indices.setdefault(candidate_index, (anchor_index, offset))
            if len(selected_indices) >= max_history_turns:
                break
        if len(selected_indices) >= max_history_turns:
            break
    if len(selected_indices) < max_history_turns:
        for turn in scored_turns:
            candidate_index = int(turn.get("history_index", 0))
            selected_indices.setdefault(candidate_index, (candidate_index, 0))
            if len(selected_indices) >= max_history_turns:
                break
    selected: list[dict[str, Any]] = []
    for turn in turns:
        history_index = int(turn.get("history_index", len(selected)))
        if history_index not in selected_indices:
            continue
        anchor_index, offset = selected_indices[history_index]
        selected_turn = deepcopy(turn)
        selected_turn["selection_rank"] = rank_by_index.get(
            history_index,
            rank_by_index.get(anchor_index, len(scored_turns) + 1),
        )
        selected_turn["selection_score"] = round(score_by_index.get(history_index, 0.0), 6)
        selected_turn["selection_anchor_index"] = anchor_index
        selected_turn["selection_window_offset"] = offset
        selected.append(selected_turn)
    return selected


def _score_turns_by_query_bm25(
    question: str,
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query_tokens = set(_tokenize_for_selection(question))
    if not query_tokens:
        return []
    tokenized_turns = [_tokenize_for_selection(_turn_text(turn)) for turn in turns]
    doc_count = max(len(tokenized_turns), 1)
    document_frequencies: Counter[str] = Counter()
    for tokens in tokenized_turns:
        document_frequencies.update(set(tokens))
    scored_turns: list[dict[str, Any]] = []
    for index, (turn, tokens) in enumerate(zip(turns, tokenized_turns, strict=True)):
        term_counts = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = term_counts[token]
            if frequency <= 0:
                continue
            idf = math.log((doc_count + 1) / (document_frequencies[token] + 0.5)) + 1.0
            score += idf * ((frequency * 2.2) / (frequency + 1.2))
        scored_turn = deepcopy(turn)
        scored_turn["selection_score"] = round(score, 6)
        scored_turn["history_index"] = int(scored_turn.get("history_index", index))
        scored_turns.append(scored_turn)
    scored_turns.sort(
        key=lambda turn: (
            -float(turn.get("selection_score", 0.0)),
            int(turn.get("history_index", 0)),
        )
    )
    return scored_turns


def _score_turns_by_query_change_update_domain(
    question: str,
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query_tokens = set(_tokenize_for_selection(question))
    expanded_terms = _expanded_change_update_terms(question)
    if not query_tokens and not expanded_terms:
        return []
    tokenized_turns = [_tokenize_for_selection(_turn_text(turn)) for turn in turns]
    doc_count = max(len(tokenized_turns), 1)
    document_frequencies: Counter[str] = Counter()
    for tokens in tokenized_turns:
        document_frequencies.update(set(tokens))
    scored_turns: list[dict[str, Any]] = []
    for index, (turn, tokens) in enumerate(zip(turns, tokenized_turns, strict=True)):
        term_counts = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = term_counts[token]
            if frequency <= 0:
                continue
            idf = math.log((doc_count + 1) / (document_frequencies[token] + 0.5)) + 1.0
            score += idf * ((frequency * 2.2) / (frequency + 1.2))
        token_set = set(tokens)
        score += len(expanded_terms & token_set) * 0.85
        score += _change_update_phrase_score(question, _normalized_selection_text(_turn_text(turn))) * 1.35
        if str(turn.get("speaker", "")).lower() == "user":
            score += 0.25
        scored_turn = deepcopy(turn)
        scored_turn["selection_score"] = round(score, 6)
        scored_turn["history_index"] = int(scored_turn.get("history_index", index))
        scored_turns.append(scored_turn)
    scored_turns.sort(
        key=lambda turn: (
            -float(turn.get("selection_score", 0.0)),
            int(turn.get("history_index", 0)),
        )
    )
    return scored_turns


def _expanded_change_update_terms(question: str) -> set[str]:
    normalized = _normalized_selection_text(question)
    question_tokens = set(normalized.split())
    terms: set[str] = set()
    for domain in MUTABLE_STATE_DOMAINS:
        if question_tokens & set(domain["triggers"]):
            terms.update(domain["terms"])
    return terms


def _change_update_phrase_score(question: str, normalized_text: str) -> float:
    normalized_question = _normalized_selection_text(question)
    question_tokens = set(normalized_question.split())
    score = 0.0
    for domain in MUTABLE_STATE_DOMAINS:
        if question_tokens & set(domain["triggers"]):
            score += float(sum(1 for cue in domain["phrases"] if cue in normalized_text))
    return score


def _normalized_selection_text(text: str) -> str:
    return " ".join(token for token in _tokenize_for_selection(str(text)) if token)


def _tokenize_for_selection(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _turn_text(turn: dict[str, Any]) -> str:
    pieces = [
        str(turn.get("speaker", "")),
        str(turn.get("timestamp", "")),
        str(turn.get("text", "")),
    ]
    return " ".join(piece for piece in pieces if piece.strip())


def _walk_history(value: Any, turns: list[dict[str, Any]], *, path: str) -> None:
    if isinstance(value, str):
        for chunk_index, chunk in enumerate(_text_chunks(value)):
            turns.append(
                {
                    "turn_id": f"{path}[chunk_{chunk_index}]",
                    "text": chunk,
                    "source_path": path,
                }
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_history(item, turns, path=f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return
    if _walk_locomo_session_dict(value, turns, path=path):
        return
    text = _first_string(value, TEXT_FIELDS)
    if text:
        turn = {
            "turn_id": _first_string(value, ("turn_id", "message_id", "id")) or path,
            "text": text,
            "source_path": path,
        }
        speaker = _first_string(value, SPEAKER_FIELDS)
        if speaker:
            turn["speaker"] = speaker
        timestamp = _first_string(value, TIMESTAMP_FIELDS)
        if timestamp:
            turn["timestamp"] = timestamp
        session_id = _first_string(value, ("session_id", "session", "episode_id"))
        if session_id:
            turn["session_id"] = session_id
        turns.append(turn)
        return
    for field_name in HISTORY_FIELDS:
        if field_name in value:
            _walk_history(value[field_name], turns, path=f"{path}.{field_name}")


def _walk_locomo_session_dict(value: dict[str, Any], turns: list[dict[str, Any]], *, path: str) -> bool:
    """Walk raw LoCoMo conversation dicts with session_N/session_N_date_time keys."""

    session_keys = sorted(
        key
        for key, session_value in value.items()
        if re.fullmatch(r"session_\d+", str(key)) and isinstance(session_value, list)
    )
    if not session_keys:
        return False
    for session_key in session_keys:
        session_turns = value.get(session_key)
        if not isinstance(session_turns, list):
            continue
        timestamp = _first_string(value, (f"{session_key}_date_time", f"{session_key}_date"))
        for index, item in enumerate(session_turns):
            if not isinstance(item, dict):
                _walk_history(item, turns, path=f"{path}.{session_key}[{index}]")
                continue
            enriched = deepcopy(item)
            enriched.setdefault("session_id", session_key)
            if timestamp:
                enriched.setdefault("timestamp", timestamp)
            if "turn_id" not in enriched and isinstance(enriched.get("dia_id"), str):
                enriched["turn_id"] = str(enriched["dia_id"])
            _walk_history(enriched, turns, path=f"{path}.{session_key}[{index}]")
    return True


def _text_chunks(text: str, *, max_chars: int = 1600) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    chunks: list[str] = []
    for start in range(0, len(cleaned), max_chars):
        chunks.append(cleaned[start : start + max_chars])
    return chunks


def _extract_candidate_memory_payloads(
    row: dict[str, Any],
    qa_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    containers = [row]
    if qa_payload is not row:
        containers.append(qa_payload)
    for container in containers:
        for field_name in CANDIDATE_MEMORY_FIELDS:
            value = container.get(field_name)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and _looks_like_candidate_memory(item):
                    candidates.append(deepcopy(item))
    return candidates


def _looks_like_candidate_memory(item: dict[str, Any]) -> bool:
    if "memory_id" in item:
        return True
    if "event_id" in item:
        return True
    return all(field in item for field in ("entity", "slot", "value")) and any(
        field in item for field in ("observed_at", "timestamp", "created_at")
    )


def _build_extraction_work_item(
    *,
    case_id: str,
    dataset: str,
    source_row_id: str,
    question: str,
    history_turns: list[dict[str, Any]],
    total_history_turn_count: int,
    history_selection: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "dataset": dataset,
        "source_row_id": source_row_id,
        "question": question,
        "history_turns": deepcopy(history_turns),
        "history_turn_count": len(history_turns),
        "selected_history_turn_count": len(history_turns),
        "total_history_turn_count": total_history_turn_count,
        "history_selection": history_selection,
        "task": "extract_structured_candidate_memories_for_qvf_validity_admission",
        "api_calls_made": 0,
    }


def _build_qvf_service_request(
    *,
    case_id: str,
    question: str,
    candidate_records: list[dict[str, Any]],
) -> dict[str, Any]:
    entity, slot = _query_entity_slot_from_candidates(candidate_records)
    query_request = {
        "request_id": f"q_{case_id}",
        "question": question,
        "entity": entity,
        "slot": slot,
        "needs_current": True,
        "risk_profile": "current_sensitive",
    }
    premise_value = _premise_value_from_question(question, candidate_records)
    if premise_value:
        query_request["premise_value"] = premise_value
    return {
        "request_id": f"public_dataset_{case_id}",
        "step_id": f"public_dataset_step_{case_id}",
        "records": candidate_records,
        "query_requests": [query_request],
    }


def _query_entity_slot_from_candidates(candidates: list[dict[str, Any]]) -> tuple[str, str]:
    counts: Counter[tuple[str, str]] = Counter()
    for candidate in candidates:
        entity = str(candidate.get("entity", "")).strip()
        slot = str(candidate.get("slot", "")).strip()
        if entity and slot:
            counts[(entity, slot)] += 1
    if not counts:
        raise ValueError("structured candidate memories must include entity and slot")
    return counts.most_common(1)[0][0]


def _premise_value_from_question(
    question: str,
    candidates: list[dict[str, Any]],
) -> str | None:
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


def _leakage_report(
    *,
    answers: list[str],
    extraction_work_item: dict[str, Any],
    qvf_request: dict[str, Any] | None,
    sidecar_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    qvf_payload = qvf_request or {}
    answer_key_paths = _answer_key_paths(qvf_payload)
    extraction_answer_key_paths = _answer_key_paths(extraction_work_item)
    answer_text_question_paths = answer_text_paths(
        answers,
        qvf_payload.get("query_requests", []),
    )
    natural_history_answer_mentions = answer_text_paths(
        answers,
        extraction_work_item.get("history_turns", []),
    )
    model_facing_paths = model_facing_forbidden_key_paths(sidecar_payloads)
    return {
        "decision": (
            "GO_PUBLIC_DATASET_ADAPTER_NO_ANSWER_KEY_LEAKAGE"
            if not answer_key_paths
            and not extraction_answer_key_paths
            and not model_facing_paths
            else "NO_GO_PUBLIC_DATASET_ADAPTER_LEAKAGE_KEYS_FOUND"
        ),
        "answer_key_paths_in_qvf_request": answer_key_paths,
        "answer_key_paths_in_extraction_work_item": extraction_answer_key_paths,
        "internal_forbidden_key_paths_in_model_facing_payload": model_facing_paths,
        "answer_text_paths_in_query_request": answer_text_question_paths,
        "natural_history_answer_mention_count": len(natural_history_answer_mentions),
        "natural_history_answer_paths": natural_history_answer_mentions[:20],
        "note": (
            "Answer text inside source history can be legitimate evidence; "
            "answer/gold-answer keys are not copied into QVF or extraction payloads."
        ),
    }


def _answer_key_paths(payload: Any, *, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_path = f"{prefix}.{key}"
            if key.lower() in PUBLIC_ANSWER_KEY_NAMES:
                paths.append(key_path)
            paths.extend(_answer_key_paths(value, prefix=key_path))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            paths.extend(_answer_key_paths(item, prefix=f"{prefix}[{index}]"))
    return paths


def _public_pilot_summary(
    *,
    dataset: str,
    rows_received: int,
    items: list[dict[str, Any]],
    skipped_items: list[dict[str, Any]],
) -> dict[str, Any]:
    qvf_ready_count = sum(1 for item in items if item["qvf_ready"])
    leakage_decision_counts = Counter(
        item.get("leakage_report", {}).get("decision", "unknown")
        for item in items
    )
    warning_counts: Counter[str] = Counter()
    for item in items:
        warning_counts.update(item.get("warnings", []))
    history_selection_counts = Counter(
        item.get("history_selection", "unknown") for item in items
    )
    return {
        "decision": "GO_QVF_PUBLIC_DATASET_ADAPTER_SUMMARY_READY_NO_API",
        "adapter_version": PUBLIC_DATASET_ADAPTER_VERSION,
        "dataset": dataset,
        "rows_received": rows_received,
        "item_count": len(items),
        "qvf_ready_item_count": qvf_ready_count,
        "extraction_required_item_count": len(items) - qvf_ready_count,
        "skipped_item_count": len(skipped_items),
        "total_history_turn_count": sum(
            item.get("total_history_turn_count", item["raw_history_turn_count"])
            for item in items
        ),
        "selected_history_turn_count": sum(
            item.get("selected_history_turn_count", item["raw_history_turn_count"])
            for item in items
        ),
        "raw_history_turn_count": sum(item["raw_history_turn_count"] for item in items),
        "history_selection_counts": dict(sorted(history_selection_counts.items())),
        "candidate_memory_count": sum(item["candidate_memory_count"] for item in items),
        "leakage_decision_counts": dict(sorted(leakage_decision_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "api_calls_made": 0,
    }


def _extract_answers(payload: dict[str, Any]) -> list[str]:
    answers: list[str] = []
    for field_name in ANSWER_FIELDS:
        if field_name not in payload:
            continue
        answers.extend(_coerce_answer_strings(payload[field_name]))
    return _dedupe_preserve_order(answers)


def _coerce_answer_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, list):
        answers: list[str] = []
        for item in value:
            answers.extend(_coerce_answer_strings(item))
        return answers
    if isinstance(value, dict):
        answers: list[str] = []
        for field_name in ("text", "answer", "value", "label"):
            if field_name in value:
                answers.extend(_coerce_answer_strings(value[field_name]))
        return answers
    return []


def _first_string(payload: dict[str, Any], field_names: tuple[str, ...]) -> str | None:
    for field_name in field_names:
        value = payload.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_row_id(row: dict[str, Any], source_index: int) -> str:
    return _first_string(row, ROW_ID_FIELDS) or f"row_{source_index:05d}"


def _public_case_id(
    dataset: str,
    source_row_id: str,
    qa_payload: dict[str, Any],
    qa_index: int,
) -> str:
    question_id = _first_string(qa_payload, ROW_ID_FIELDS)
    suffix = question_id or f"qa_{qa_index:03d}_{_stable_digest(qa_payload)}"
    return _slug(f"{dataset}_{source_row_id}_{suffix}")


def _stable_digest(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]


def _slug(value: str) -> str:
    chars = [
        char.lower() if char.isalnum() else "_"
        for char in value.strip()
    ]
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "public_dataset_case"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _validate_dataset(dataset: str) -> str:
    if not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("dataset must be a non-empty string")
    normalized = dataset.strip().lower()
    if normalized not in SUPPORTED_PUBLIC_DATASETS:
        supported = ", ".join(SUPPORTED_PUBLIC_DATASETS)
        raise ValueError(f"dataset must be one of: {supported}")
    return normalized


def _validate_history_selection(history_selection: str) -> str:
    if not isinstance(history_selection, str) or not history_selection.strip():
        raise ValueError("history_selection must be a non-empty string")
    normalized = history_selection.strip().lower()
    if normalized not in HISTORY_SELECTION_METHODS:
        supported = ", ".join(HISTORY_SELECTION_METHODS)
        raise ValueError(f"history_selection must be one of: {supported}")
    return normalized


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
    text = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def _write_cases_csv(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "dataset",
        "source_row_id",
        "qa_index",
        "qvf_ready",
        "history_selection",
        "total_history_turn_count",
        "selected_history_turn_count",
        "raw_history_turn_count",
        "candidate_memory_count",
        "leakage_decision",
        "warnings",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "case_id": item["case_id"],
                    "dataset": item["dataset"],
                    "source_row_id": item["source_row_id"],
                    "qa_index": item["qa_index"],
                    "qvf_ready": item["qvf_ready"],
                    "history_selection": item.get("history_selection", ""),
                    "total_history_turn_count": item.get("total_history_turn_count", ""),
                    "selected_history_turn_count": item.get(
                        "selected_history_turn_count",
                        item["raw_history_turn_count"],
                    ),
                    "raw_history_turn_count": item["raw_history_turn_count"],
                    "candidate_memory_count": item["candidate_memory_count"],
                    "leakage_decision": item["leakage_report"]["decision"],
                    "warnings": json.dumps(item["warnings"], ensure_ascii=False),
                }
            )


def _write_report_zh(path: Path, pilot: dict[str, Any]) -> None:
    summary = pilot["summary"]
    lines = [
        "# QVF 公开数据集 adapter pilot",
        "",
        "## 结果",
        "",
        f"- Dataset: `{summary['dataset']}`",
        f"- Input file: `{summary.get('input_file_name', '')}`",
        f"- Items: {summary['item_count']}",
        f"- QVF-ready items: {summary['qvf_ready_item_count']}",
        f"- Extraction-required items: {summary['extraction_required_item_count']}",
        f"- Skipped items: {summary['skipped_item_count']}",
        f"- History selection: `{summary['history_selection_counts']}`",
        f"- Selected/total history turns: {summary['selected_history_turn_count']} / {summary['total_history_turn_count']}",
        f"- API calls: {summary['api_calls_made']}",
        "",
        "## 解释",
        "",
        "这个 adapter 不把原始长对话直接当作 QVF 结构化记忆。",
        "如果公开数据行已经包含 entity/slot/value/timestamp 形式的候选记忆，",
        "它会生成 QVF service request 并做无 API lifecycle smoke run；",
        "如果只有 raw conversation/history，则生成 extraction work item，供下一步检索/抽取模块使用。",
        "",
        "## Leakage check",
        "",
        f"- Leakage decisions: `{summary['leakage_decision_counts']}`",
        "- Gold answer keys 只保留在 adapter metadata 中，不会复制进 extraction/QVF payload。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DEFAULT_HISTORY_SELECTION",
    "DEFAULT_MAX_HISTORY_TURNS",
    "DEFAULT_PUBLIC_PILOT_LIMIT",
    "HISTORY_SELECTION_METHODS",
    "PUBLIC_DATASET_ADAPTER_VERSION",
    "SUPPORTED_PUBLIC_DATASETS",
    "adapt_public_dataset_item",
    "build_public_dataset_pilot",
    "load_public_case_ids",
    "load_public_dataset_rows",
    "write_public_dataset_adapter_pilot",
]
