"""Domain-independent temporal validity semantics for QVF runtime records."""

from __future__ import annotations

from datetime import datetime
from typing import Any


STRICT_TEMPORAL_POLICY_VERSION = "qvf_strict_bitemporal_validity_v0.1"

SLOT_CARDINALITY_VALUES = {"single", "set", "unknown"}
TEMPORAL_RELATION_VALUES = {
    "equivalent",
    "additive",
    "replacement",
    "correction",
    "revocation",
    "unresolved",
}
TEMPORAL_STATUS_VALUES = {
    "effective",
    "observed",
    "planned",
    "future",
    "unknown",
}
DIRECTED_REPLACEMENT_RELATIONS = {"replacement", "correction"}


def normalized_temporal_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def is_strict_temporal_payload(payload: dict[str, Any]) -> bool:
    return (
        normalized_temporal_value(payload.get("validity_policy"))
        == normalized_temporal_value(STRICT_TEMPORAL_POLICY_VERSION)
    )


def strict_slot_cardinality(payload: dict[str, Any]) -> str:
    value = normalized_temporal_value(payload.get("slot_cardinality"))
    return value if value in SLOT_CARDINALITY_VALUES else "unknown"


def strict_temporal_relation(payload: dict[str, Any]) -> str:
    value = normalized_temporal_value(payload.get("temporal_relation"))
    return value if value in TEMPORAL_RELATION_VALUES else "unresolved"


def strict_temporal_status(payload: dict[str, Any]) -> str:
    value = normalized_temporal_value(payload.get("temporal_status"))
    return value if value in TEMPORAL_STATUS_VALUES else "unknown"


def strict_relation_target_ids(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("relation_target_memory_ids", [])
    if not isinstance(raw, list):
        return ()
    return tuple(str(value).strip() for value in raw if str(value).strip())


def validate_strict_temporal_payload(
    payload: dict[str, Any],
    *,
    memory_id: str,
) -> None:
    policy = payload.get("validity_policy")
    if policy is None:
        return
    if not is_strict_temporal_payload(payload):
        raise ValueError(
            f"memory.validity_policy is unknown for {memory_id}: {policy!r}"
        )

    cardinality = normalized_temporal_value(payload.get("slot_cardinality"))
    relation = normalized_temporal_value(payload.get("temporal_relation"))
    status = normalized_temporal_value(payload.get("temporal_status"))
    if cardinality not in SLOT_CARDINALITY_VALUES:
        known = ", ".join(sorted(SLOT_CARDINALITY_VALUES))
        raise ValueError(
            f"memory.slot_cardinality must be one of {known} for {memory_id}"
        )
    if relation not in TEMPORAL_RELATION_VALUES:
        known = ", ".join(sorted(TEMPORAL_RELATION_VALUES))
        raise ValueError(
            f"memory.temporal_relation must be one of {known} for {memory_id}"
        )
    if status not in TEMPORAL_STATUS_VALUES:
        known = ", ".join(sorted(TEMPORAL_STATUS_VALUES))
        raise ValueError(
            f"memory.temporal_status must be one of {known} for {memory_id}"
        )

    targets = payload.get("relation_target_memory_ids", [])
    if not isinstance(targets, list):
        raise ValueError(
            f"memory.relation_target_memory_ids must be a list for {memory_id}"
        )
    normalized_targets: list[str] = []
    for target in targets:
        if not isinstance(target, str) or not target.strip():
            raise ValueError(
                "memory.relation_target_memory_ids must contain non-empty strings "
                f"for {memory_id}"
            )
        normalized_targets.append(target.strip())
    if len(normalized_targets) != len(set(normalized_targets)):
        raise ValueError(
            f"memory.relation_target_memory_ids contains duplicates for {memory_id}"
        )
    if memory_id in normalized_targets:
        raise ValueError(
            f"memory.relation_target_memory_ids cannot target itself for {memory_id}"
        )
    if relation in DIRECTED_REPLACEMENT_RELATIONS | {"revocation"}:
        if not normalized_targets:
            raise ValueError(
                f"memory.temporal_relation={relation} requires relation targets for {memory_id}"
            )
    if relation in DIRECTED_REPLACEMENT_RELATIONS and cardinality != "single":
        raise ValueError(
            f"memory.temporal_relation={relation} requires slot_cardinality=single "
            f"for {memory_id}"
        )
    if relation == "additive" and cardinality != "set":
        raise ValueError(
            f"memory.temporal_relation=additive requires slot_cardinality=set for {memory_id}"
        )
    if status in {"planned", "future"} and not payload.get("effective_from"):
        raise ValueError(
            f"memory.temporal_status={status} requires effective_from for {memory_id}"
        )

    effective_from = _optional_datetime(payload.get("effective_from"), "effective_from", memory_id)
    effective_until = _optional_datetime(
        payload.get("effective_until"), "effective_until", memory_id
    )
    _optional_datetime(payload.get("source_time"), "source_time", memory_id)
    _optional_datetime(payload.get("event_time"), "event_time", memory_id)
    if (
        effective_from is not None
        and effective_until is not None
        and effective_from > effective_until
    ):
        raise ValueError(
            f"memory.effective_until must be >= effective_from for {memory_id}"
        )


def _optional_datetime(
    value: Any,
    field_name: str,
    memory_id: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"memory.{field_name} must be a non-empty ISO-8601 string for {memory_id}"
        )
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"memory.{field_name} must be ISO-8601 for {memory_id}"
        ) from exc


__all__ = [
    "DIRECTED_REPLACEMENT_RELATIONS",
    "SLOT_CARDINALITY_VALUES",
    "STRICT_TEMPORAL_POLICY_VERSION",
    "TEMPORAL_RELATION_VALUES",
    "TEMPORAL_STATUS_VALUES",
    "is_strict_temporal_payload",
    "normalized_temporal_value",
    "strict_relation_target_ids",
    "strict_slot_cardinality",
    "strict_temporal_relation",
    "strict_temporal_status",
    "validate_strict_temporal_payload",
]
