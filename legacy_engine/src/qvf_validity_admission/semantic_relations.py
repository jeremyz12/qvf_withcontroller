"""Auditable semantic-relation contract for strict QVF runtime records.

The active runtime consumes only source-backed relation metadata. Learned or
model-produced assessments remain unresolved until a separately verified
attestation registry is implemented and promoted.
"""

from __future__ import annotations

from typing import Any


SEMANTIC_RELATION_CONTRACT_VERSION = "qvf_semantic_relation_contract_v0.1"

SEMANTIC_RELATION_VALUES = {
    "equivalent",
    "additive_coexistence",
    "contradiction",
    "condition_bound",
    "unrelated",
    "unresolved",
}

TARGETED_SEMANTIC_RELATIONS = {
    "equivalent",
    "contradiction",
    "condition_bound",
    "unrelated",
}

_LEGACY_RELATION_MAP = {
    "equivalent": "equivalent",
    "additive": "additive_coexistence",
}

_SOURCE_BACKED_ORIGINS = {
    "independent_control",
    "retrieved_memory_metadata",
    "source_span_extraction",
}


def normalized_semantic_value(value: Any) -> str:
    if value is None:
        return ""
    return "_".join(
        str(value).strip().lower().replace("-", " ").replace("_", " ").split()
    )


def strict_semantic_relation(payload: dict[str, Any]) -> str:
    explicit = normalized_semantic_value(payload.get("semantic_relation"))
    if explicit:
        return explicit if explicit in SEMANTIC_RELATION_VALUES else "unresolved"
    legacy = normalized_semantic_value(payload.get("temporal_relation"))
    return _LEGACY_RELATION_MAP.get(legacy, "unresolved")


def strict_semantic_relation_target_ids(
    payload: dict[str, Any],
) -> tuple[str, ...]:
    raw = payload.get("semantic_relation_target_memory_ids")
    if raw is None and normalized_semantic_value(
        payload.get("temporal_relation")
    ) in _LEGACY_RELATION_MAP:
        raw = payload.get("relation_target_memory_ids", [])
    if not isinstance(raw, list):
        return ()
    return tuple(str(value).strip() for value in raw if str(value).strip())


def validate_semantic_relation_payload(
    payload: dict[str, Any],
    *,
    memory_id: str,
) -> None:
    explicit_raw = payload.get("semantic_relation")
    legacy_raw = normalized_semantic_value(payload.get("temporal_relation"))
    legacy_relation = _LEGACY_RELATION_MAP.get(legacy_raw)
    if explicit_raw is None and legacy_relation is None:
        return

    explicit = normalized_semantic_value(explicit_raw)
    if explicit_raw is not None and explicit not in SEMANTIC_RELATION_VALUES:
        known = ", ".join(sorted(SEMANTIC_RELATION_VALUES))
        raise ValueError(
            f"memory.semantic_relation must be one of {known} for {memory_id}"
        )
    relation = explicit or legacy_relation or "unresolved"
    if explicit and legacy_relation and explicit != legacy_relation:
        raise ValueError(
            "memory.semantic_relation conflicts with legacy temporal_relation "
            f"for {memory_id}"
        )

    raw_targets = payload.get("semantic_relation_target_memory_ids")
    if raw_targets is None and legacy_relation is not None:
        raw_targets = payload.get("relation_target_memory_ids", [])
    if raw_targets is None:
        raw_targets = []
    if not isinstance(raw_targets, list):
        raise ValueError(
            f"memory.semantic_relation_target_memory_ids must be a list for {memory_id}"
        )
    targets: list[str] = []
    for target in raw_targets:
        if not isinstance(target, str) or not target.strip():
            raise ValueError(
                "memory.semantic_relation_target_memory_ids must contain non-empty "
                f"strings for {memory_id}"
            )
        targets.append(target.strip())
    if len(targets) != len(set(targets)):
        raise ValueError(
            f"memory.semantic_relation_target_memory_ids contains duplicates for {memory_id}"
        )
    if memory_id in targets:
        raise ValueError(
            f"memory.semantic_relation_target_memory_ids cannot target itself for {memory_id}"
        )
    if relation == "equivalent" and len(targets) != 1:
        raise ValueError(
            "memory.semantic_relation=equivalent requires exactly one relation target "
            f"for {memory_id}"
        )
    if relation in TARGETED_SEMANTIC_RELATIONS and not targets:
        raise ValueError(
            f"memory.semantic_relation={relation} requires relation targets for {memory_id}"
        )
    if relation == "additive_coexistence":
        cardinality = normalized_semantic_value(payload.get("slot_cardinality"))
        if cardinality != "set":
            raise ValueError(
                "memory.semantic_relation=additive_coexistence requires "
                f"slot_cardinality=set for {memory_id}"
            )

    if explicit_raw is None:
        return
    state = payload.get("semantic_relation_state")
    if not isinstance(state, dict):
        raise ValueError(
            f"memory.semantic_relation_state is required for {memory_id}"
        )
    status = normalized_semantic_value(state.get("status"))
    origin = normalized_semantic_value(state.get("origin"))
    if relation == "unresolved":
        if status not in {"unknown", "abstained"}:
            raise ValueError(
                "memory.semantic_relation=unresolved requires an unknown or abstained "
                f"state for {memory_id}"
            )
        return
    if status != "known":
        raise ValueError(
            f"memory.semantic_relation={relation} requires state.status=known for {memory_id}"
        )
    if origin not in _SOURCE_BACKED_ORIGINS:
        raise ValueError(
            "memory semantic provider inference is not attested for active runtime: "
            f"{memory_id} origin={state.get('origin')!r}"
        )


__all__ = [
    "SEMANTIC_RELATION_CONTRACT_VERSION",
    "SEMANTIC_RELATION_VALUES",
    "TARGETED_SEMANTIC_RELATIONS",
    "normalized_semantic_value",
    "strict_semantic_relation",
    "strict_semantic_relation_target_ids",
    "validate_semantic_relation_payload",
]
