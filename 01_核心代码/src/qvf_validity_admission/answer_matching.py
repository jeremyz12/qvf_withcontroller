"""Strict offline answer-text matching for public evaluation audits."""

from __future__ import annotations

import re
from typing import Any

FORBIDDEN_ANSWER_KEYS = {"answers", "gold_answer", "expected_answers"}
AMBIGUOUS_TITLECASE_TOKENS = {
    "apple",
    "target",
    "may",
    "march",
    "orange",
    "rose",
    "shell",
}


def answer_text_paths(
    answers: list[str],
    payload: Any,
    *,
    prefix: str = "$",
) -> list[str]:
    """Return paths whose string payload contains an audited answer mention."""

    normalized_answers = _valid_answers(answers)
    if not normalized_answers:
        return []
    paths: list[str] = []
    if isinstance(payload, str):
        if any(answer_matches_text(answer, payload) for answer in normalized_answers):
            paths.append(prefix)
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in FORBIDDEN_ANSWER_KEYS:
                continue
            paths.extend(answer_text_paths(answers, value, prefix=f"{prefix}.{key}"))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            paths.extend(answer_text_paths(answers, value, prefix=f"{prefix}[{index}]"))
    return paths


def answer_mention_count(answers: list[str], payload: Any) -> int:
    """Count audited answer mentions in a payload."""

    normalized_answers = _valid_answers(answers)
    if not normalized_answers:
        return 0
    return _recursive_answer_mention_count(normalized_answers, payload)


def answer_mention_record_ids(answers: list[str], records: Any) -> list[str]:
    """Return record/evidence ids whose payload contains an audited answer mention."""

    normalized_answers = _valid_answers(answers)
    if not normalized_answers or not isinstance(records, list):
        return []
    ids: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if _recursive_answer_mention_count(normalized_answers, record) <= 0:
            continue
        ids.append(_record_identifier(record, index))
    return ids


def answer_matches_text(answer: str, text: str) -> bool:
    """Return true when answer appears as a defensible text mention.

    This intentionally avoids raw substring matching. Single-token answers use
    word boundaries; ambiguous titlecase tokens such as "Target" must match
    case-sensitively so generic phrases like "target audience" do not count.
    """

    cleaned_answer = " ".join(answer.split())
    if len(cleaned_answer) < 3:
        return False
    if not isinstance(text, str) or not text:
        return False
    if _is_single_token(cleaned_answer):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(cleaned_answer)}(?![A-Za-z0-9_])"
        flags = 0 if _requires_case_sensitive_match(cleaned_answer) else re.IGNORECASE
        return re.search(pattern, text, flags=flags) is not None
    pattern = r"\s+".join(re.escape(part) for part in cleaned_answer.split())
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _recursive_answer_mention_count(answers: list[str], payload: Any) -> int:
    if isinstance(payload, str):
        return sum(1 for answer in answers if answer_matches_text(answer, payload))
    if isinstance(payload, dict):
        return sum(
            _recursive_answer_mention_count(answers, value)
            for key, value in payload.items()
            if str(key).lower() not in FORBIDDEN_ANSWER_KEYS
        )
    if isinstance(payload, list):
        return sum(_recursive_answer_mention_count(answers, value) for value in payload)
    return 0


def _valid_answers(answers: list[str]) -> list[str]:
    return [
        " ".join(answer.split())
        for answer in answers
        if isinstance(answer, str) and len(answer.strip()) >= 3
    ]


def _is_single_token(answer: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_]+", answer) is not None


def _requires_case_sensitive_match(answer: str) -> bool:
    return answer.lower() in AMBIGUOUS_TITLECASE_TOKENS and any(
        char.isupper() for char in answer
    )


def _record_identifier(record: dict[str, Any], index: int) -> str:
    for field_name in ("memory_id", "evidence_id", "id"):
        value = record.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"record_{index:03d}"


__all__ = [
    "answer_matches_text",
    "answer_mention_count",
    "answer_mention_record_ids",
    "answer_text_paths",
]
