from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from ._pipeline_core import (
    LOW_CONFIDENCE_THRESHOLD,
    READER_PROFILES,
    READ_DECISION_VALUES,
    norm,
    validate_query_batch,
)
from .memory import ValidityAwareMemoryStore

RETRIEVAL_BUDGET_FIELDS = (
    "max_current",
    "max_supporting",
    "max_stale",
    "max_excluded",
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

build_validity_admission_packets = build_lifecycle_packets

__all__ = [
    "apply_packet_char_budget",
    "build_lifecycle_packets",
    "build_packets_from_store",
    "build_validity_admission_packets",
    "build_weak_gate_tasks",
    "refresh_token_budget_proxy",
    "validate_max_packet_chars",
    "validate_packet_batch",
    "validate_packet_payload",
    "validate_retrieval_budget",
]
