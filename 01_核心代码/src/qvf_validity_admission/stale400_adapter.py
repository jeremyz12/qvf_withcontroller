"""Adapters from official STALE400 cases into the QVF validity-admission pipeline."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DIM_READER_PROFILES = {
    "dim1_query": "weak_conservative",
    "dim2_query": "weak_conservative",
    "dim3_query": "dim3_actionable",
}


def load_stale400_cases(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("STALE400 file must contain a list or an object with a data list")
    return [validate_stale400_case(row) for row in rows]


def validate_stale400_case(case: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError("STALE400 case must be an object")
    validated = dict(case)
    for field_name in ["uid", "M_old", "M_new", "probing_queries"]:
        if field_name == "probing_queries":
            if not isinstance(validated.get(field_name), dict):
                raise ValueError("STALE400 case.probing_queries must be an object")
            continue
        value = validated.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"STALE400 case.{field_name} must be a non-empty string")
    return validated


def stale400_case_to_validity_admission_request(
    case: dict[str, Any],
    *,
    case_type: str | None = None,
    reader_profile_by_dim: dict[str, str] | None = None,
) -> dict[str, Any]:
    case = validate_stale400_case(case)
    uid = case["uid"]
    case_type = case_type or str(case.get("type") or "STALE400")
    slot = infer_stale400_slot(case)
    old_at, new_at = infer_stale400_observed_times(case)
    dim_profiles = dict(DEFAULT_DIM_READER_PROFILES)
    if reader_profile_by_dim:
        dim_profiles.update(reader_profile_by_dim)

    records = [
        {
            "memory_id": f"{uid}::old",
            "entity": "user",
            "slot": slot,
            "claim": case["M_old"],
            "value": case["M_old"],
            "source": {
                "source_id": f"{uid}::old_source",
                "source_type": "stale400_memory",
            },
            "observed_at": old_at,
            "valid_from": old_at,
            "source_confidence": 0.9,
        },
        {
            "memory_id": f"{uid}::new",
            "entity": "user",
            "slot": slot,
            "claim": case["M_new"],
            "value": case["M_new"],
            "source": {
                "source_id": f"{uid}::new_source",
                "source_type": "stale400_memory",
            },
            "observed_at": new_at,
            "valid_from": new_at,
            "source_confidence": 0.95,
        },
    ]
    query_requests = []
    for dim_key, query_text in sorted(case["probing_queries"].items()):
        if not isinstance(query_text, str) or not query_text.strip():
            continue
        request = {
            "request_id": f"{uid}::{dim_key}",
            "question": query_text,
            "entity": "user",
            "slot": slot,
            "reader_profile": dim_profiles.get(dim_key, "strong_graph_lite"),
            "stale400": {
                "uid": uid,
                "case_type": case_type,
                "dim_key": dim_key,
            },
        }
        if dim_key in {"dim1_query", "dim2_query"}:
            request["premise_value"] = case["M_old"]
        query_requests.append(request)

    return {
        "request_id": f"stale400::{case_type}::{uid}",
        "records": records,
        "query_requests": query_requests,
        "metadata": {
            "source": "official_stale400",
            "uid": uid,
            "case_type": case_type,
            "slot": slot,
            "adapter": "qvf_validity_admission_stale400_adapter_v0.2",
        },
    }


def stale400_cases_to_validity_admission_requests(
    cases: list[dict[str, Any]],
    *,
    case_type: str | None = None,
    reader_profile_by_dim: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    return [
        stale400_case_to_validity_admission_request(
            case,
            case_type=case_type,
            reader_profile_by_dim=reader_profile_by_dim,
        )
        for case in cases
    ]


# Backward-compatible aliases for older local scripts and archived result lineage.
stale400_case_to_lifecycle_request = stale400_case_to_validity_admission_request
stale400_cases_to_lifecycle_requests = stale400_cases_to_validity_admission_requests


def infer_stale400_slot(case: dict[str, Any]) -> str:
    explanation = str(case.get("explanation") or "")
    match = re.search(r"([A-Za-z_]+(?:\.[A-Za-z_]+)*(?:\([^)]+\))?)\s+is\s+now\b", explanation)
    if match:
        return _slug(match.group(1))
    for query in (case.get("probing_queries") or {}).values():
        if not isinstance(query, str):
            continue
        lowered = query.lower()
        if " live " in lowered or " lives " in lowered or " based in " in lowered:
            return "location"
        if " identify " in lowered or " status " in lowered:
            return "status"
    return "stale400_current_fact"


def infer_stale400_observed_times(case: dict[str, Any]) -> tuple[str, str]:
    timestamps = case.get("timestamps")
    indices = case.get("relevant_session_index")
    if isinstance(timestamps, list) and isinstance(indices, list) and len(indices) >= 2:
        try:
            old_index = int(indices[0])
            new_index = int(indices[1])
            return _stale400_time_to_iso(timestamps[old_index]), _stale400_time_to_iso(
                timestamps[new_index]
            )
        except (IndexError, TypeError, ValueError):
            pass
    return "2024-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"


def _stale400_time_to_iso(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("STALE400 timestamp must be a non-empty string")
    dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(
        tzinfo=timezone.utc
    )
    return dt.isoformat()


def _slug(value: str) -> str:
    text = value.replace(".", "_")
    text = text.replace("(", "_").replace(")", "")
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    return text or "stale400_current_fact"
