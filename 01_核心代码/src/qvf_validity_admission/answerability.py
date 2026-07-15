"""Structured answer authorization for QVF controller decisions."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from .semantic_relations import normalized_semantic_value
from .temporal_validity import (
    STRICT_TEMPORAL_POLICY_VERSION,
    normalized_temporal_value,
)

ANSWERABILITY_CONTRACT_VERSION = "qvf_answerability_boundary_contract_v0.1"
FACTORIZED_ANSWERABILITY_CONTRACT_VERSION = (
    "qvf_factorized_answerability_boundary_contract_v0.2"
)
RESPONSE_DIMENSION_ATTESTATION_VERSION = (
    "qvf_response_dimension_query_attestation_v0.1"
)
DUAL_PROVIDER_ATTESTATION_VERSION = (
    "qvf_dual_response_dimension_provider_attestation_v0.1"
)
ANSWERABILITY_STATES = frozenset(
    {
        "answerable_current",
        "answerable_dimensions",
        "historical_only",
        "stale_premise_correctable",
        "retrieve_current",
        "retrieve_timeline",
        "clarify_ambiguity",
        "unresolved",
    }
)

RESPONSE_DIMENSIONS = frozenset(
    {
        "current_value",
        "historical_value",
        "change_existence",
        "transition_endpoints",
        "premise_validity",
        "conflict_presence",
        "condition_bound_value",
        "ambiguity_resolution",
    }
)

RESPONSE_DIMENSION_STATUSES = frozenset(
    {"authorized", "retrieve", "clarify", "unsupported"}
)

RESPONSE_DIMENSION_ATTESTED_ORIGINS = frozenset(
    {
        "caller_metadata",
        "dual_query_semantic_provider",
        "independent_annotation",
        "independent_control",
    }
)

_AMBIGUITY_SUFFICIENCY_STATES = frozenset(
    {
        "ambiguous_current_evidence",
        "ambiguous_latest_known",
        "concurrent_ambiguous_evidence",
        "condition_scope_ambiguity",
    }
)

ARCHIVE_AWARE_QUERY_INTENTS = frozenset(
    {
        "historical_recall",
        "timeline_change",
        "conflict_audit",
        "validity_audit",
    }
)

RELATION_GATED_QUERY_INTENTS = frozenset(
    {
        "timeline_change",
        "conflict_audit",
        "validity_audit",
    }
)

_TRANSITION_RELATIONS = frozenset({"replacement", "correction", "revocation"})

_CONFLICT_RELATIONS = frozenset({"contradiction"})

_SOURCE_BACKED_RELATION_ORIGINS = frozenset(
    {"independent_control", "retrieved_memory_metadata", "source_span_extraction"}
)


def normalize_requested_response_dimensions(value: Any) -> list[str]:
    """Validate an explicit response-dimension request without lexical inference."""

    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError("requested_response_dimensions must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                "requested_response_dimensions must contain non-empty strings"
            )
        dimension = raw.strip().lower()
        if dimension not in RESPONSE_DIMENSIONS:
            known = ", ".join(sorted(RESPONSE_DIMENSIONS))
            raise ValueError(
                f"unknown requested response dimension {dimension!r}; "
                f"expected one of: {known}"
            )
        if dimension in seen:
            raise ValueError(
                f"duplicate requested response dimension {dimension!r}"
            )
        seen.add(dimension)
        normalized.append(dimension)
    return sorted(normalized)


def build_response_dimension_attestation(
    *,
    query_text: Any,
    requested_response_dimensions: Any,
) -> dict[str, str]:
    """Bind an explicit dimension declaration to exact query bytes and dimensions."""

    if not isinstance(query_text, str) or not query_text.strip():
        raise ValueError("response-dimension attestation requires query text")
    dimensions = normalize_requested_response_dimensions(
        requested_response_dimensions
    )
    if not dimensions:
        raise ValueError(
            "response-dimension attestation requires at least one dimension"
        )
    dimensions_payload = json.dumps(
        dimensions,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": RESPONSE_DIMENSION_ATTESTATION_VERSION,
        "query_sha256": hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
        "dimensions_sha256": hashlib.sha256(dimensions_payload).hexdigest(),
    }


def build_dual_provider_attestation(
    *,
    query_text: Any,
    requested_response_dimensions: Any,
    providers: Any,
) -> dict[str, Any]:
    """Bind two independent semantic-provider outputs to a query declaration."""

    query_attestation = build_response_dimension_attestation(
        query_text=query_text,
        requested_response_dimensions=requested_response_dimensions,
    )
    normalized_providers = _normalize_dual_provider_records(providers)
    agreement_payload = {
        "query_sha256": query_attestation["query_sha256"],
        "dimensions_sha256": query_attestation["dimensions_sha256"],
        "providers": normalized_providers,
    }
    agreement_bytes = json.dumps(
        agreement_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "version": DUAL_PROVIDER_ATTESTATION_VERSION,
        "providers": normalized_providers,
        "agreement_sha256": hashlib.sha256(agreement_bytes).hexdigest(),
    }


def _normalize_dual_provider_records(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("dual provider attestation requires exactly two providers")
    normalized: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {
            "provider",
            "model",
            "output_sha256",
        }:
            raise ValueError(
                "dual provider records require provider, model, and output_sha256"
            )
        provider = str(raw.get("provider") or "").strip().lower()
        model = str(raw.get("model") or "").strip()
        digest = str(raw.get("output_sha256") or "").strip().lower()
        if not provider or not model:
            raise ValueError("dual provider identity fields must be non-empty")
        if len(digest) != 64:
            raise ValueError("dual provider output_sha256 is invalid")
        try:
            bytes.fromhex(digest)
        except ValueError as exc:
            raise ValueError("dual provider output_sha256 is invalid") from exc
        normalized.append(
            {"provider": provider, "model": model, "output_sha256": digest}
        )
    if len({row["provider"] for row in normalized}) != 2:
        raise ValueError("dual provider attestation requires distinct providers")
    return sorted(
        normalized,
        key=lambda row: (row["provider"], row["model"], row["output_sha256"]),
    )


def validate_response_dimension_state(
    value: Any,
    *,
    requested_response_dimensions: Any,
    query_text: Any = None,
) -> dict[str, Any]:
    """Validate the provenance attached to an explicit dimension request."""

    dimensions = normalize_requested_response_dimensions(
        requested_response_dimensions
    )
    if not dimensions and value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            "response_dimension_state must be an object when response dimensions "
            "are supplied"
        )
    status = str(value.get("status") or "").strip().lower()
    if status not in {"known", "unknown"}:
        raise ValueError("response_dimension_state.status must be known or unknown")
    origin = str(value.get("origin") or "").strip().lower()
    confidence = value.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("response_dimension_state.confidence must be numeric")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("response_dimension_state.confidence must be in [0, 1]")
    if dimensions:
        if status != "known":
            raise ValueError(
                "requested response dimensions require a known semantic state"
            )
        if origin not in RESPONSE_DIMENSION_ATTESTED_ORIGINS:
            known = ", ".join(sorted(RESPONSE_DIMENSION_ATTESTED_ORIGINS))
            raise ValueError(
                "unattested response-dimension origin; expected one of: " + known
            )
        expected_attestation = build_response_dimension_attestation(
            query_text=query_text,
            requested_response_dimensions=dimensions,
        )
        attestation = value.get("attestation")
        if not isinstance(attestation, dict):
            raise ValueError(
                "requested response dimensions require a query-bound attestation"
            )
        if set(attestation) != set(expected_attestation):
            raise ValueError(
                "response-dimension attestation fields are incomplete or unknown"
            )
        version = attestation.get("version")
        if version != RESPONSE_DIMENSION_ATTESTATION_VERSION:
            raise ValueError("response-dimension attestation version is unsupported")
        for field_name in ("query_sha256", "dimensions_sha256"):
            digest = attestation.get(field_name)
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(
                    f"response-dimension attestation {field_name} is invalid"
                )
            try:
                bytes.fromhex(digest)
            except ValueError as exc:
                raise ValueError(
                    f"response-dimension attestation {field_name} is invalid"
                ) from exc
            if not hmac.compare_digest(
                digest.lower(),
                expected_attestation[field_name],
            ):
                raise ValueError(
                    f"response-dimension attestation {field_name} mismatch"
                )
        provider_attestation = value.get("provider_attestation")
        if origin == "dual_query_semantic_provider":
            if not isinstance(provider_attestation, dict):
                raise ValueError(
                    "dual semantic provider origin requires provider_attestation"
                )
            if set(provider_attestation) != {
                "version",
                "providers",
                "agreement_sha256",
            }:
                raise ValueError("dual provider attestation fields are incomplete or unknown")
            if provider_attestation.get("version") != DUAL_PROVIDER_ATTESTATION_VERSION:
                raise ValueError("dual provider attestation version is unsupported")
            expected_provider_attestation = build_dual_provider_attestation(
                query_text=query_text,
                requested_response_dimensions=dimensions,
                providers=provider_attestation.get("providers"),
            )
            digest = provider_attestation.get("agreement_sha256")
            if not isinstance(digest, str) or not hmac.compare_digest(
                digest.lower(),
                expected_provider_attestation["agreement_sha256"],
            ):
                raise ValueError("dual provider agreement_sha256 mismatch")
            provider_attestation = expected_provider_attestation
        elif provider_attestation is not None:
            raise ValueError(
                "provider_attestation is only valid for dual_query_semantic_provider"
            )
    result = {
        "status": status,
        "origin": origin,
        "confidence": confidence,
    }
    if dimensions:
        result["attestation"] = expected_attestation
        if origin == "dual_query_semantic_provider":
            result["provider_attestation"] = provider_attestation
    return result


def build_response_dimension_authorizations(
    *,
    requested_response_dimensions: Any,
    next_action: str,
    visible_evidence_ids: Any,
    current_value_evidence_ids: Any = None,
    historical_value_evidence_ids: Any = None,
    change_relation_evidence_ids: Any = None,
    transition_endpoint_evidence_ids: Any = None,
    premise_correction_evidence_ids: Any = None,
    conflict_evidence_ids: Any = None,
    condition_bound_evidence_ids: Any = None,
    ambiguity_resolution_evidence_ids: Any = None,
) -> dict[str, Any]:
    """Authorize source-backed response dimensions independently."""

    dimensions = normalize_requested_response_dimensions(
        requested_response_dimensions
    )
    visible_ids = set(_normalized_ids(visible_evidence_ids))
    role_evidence = {
        "current_value": _normalized_ids(current_value_evidence_ids),
        "historical_value": _normalized_ids(historical_value_evidence_ids),
        "change_existence": _normalized_ids(change_relation_evidence_ids),
        "transition_endpoints": _normalized_ids(
            transition_endpoint_evidence_ids
        ),
        "premise_validity": _normalized_ids(
            premise_correction_evidence_ids
        ),
        "conflict_presence": _normalized_ids(conflict_evidence_ids),
        "condition_bound_value": _normalized_ids(
            condition_bound_evidence_ids
        ),
        "ambiguity_resolution": _normalized_ids(
            ambiguity_resolution_evidence_ids
        ),
    }
    escaped = sorted(
        {
            evidence_id
            for ids in role_evidence.values()
            for evidence_id in ids
            if evidence_id not in visible_ids
        }
    )
    if escaped:
        raise ValueError(
            "response-dimension evidence must remain within visible evidence: "
            + ", ".join(escaped)
        )

    fallback_status = "unsupported"
    if str(next_action or "") == "clarify_ambiguity":
        fallback_status = "clarify"
    elif str(next_action or "").startswith("retrieve_") or str(
        next_action or ""
    ) == "query_rewrite_and_retrieve":
        fallback_status = "retrieve"

    authorizations: dict[str, dict[str, Any]] = {}
    for dimension in dimensions:
        evidence_ids = role_evidence[dimension]
        sufficient = bool(evidence_ids)
        if dimension == "transition_endpoints":
            sufficient = len(evidence_ids) >= 2
        if sufficient:
            status = "authorized"
            reason_code = f"source_backed_{dimension}_evidence"
        else:
            status = fallback_status
            evidence_ids = []
            reason_code = f"missing_source_backed_{dimension}_evidence"
        authorizations[dimension] = {
            "status": status,
            "evidence_ids": evidence_ids,
            "reason_code": reason_code,
        }

    authorized = sorted(
        dimension
        for dimension, row in authorizations.items()
        if row["status"] == "authorized"
    )
    blocked = sorted(set(dimensions) - set(authorized))
    return {
        "requested_response_dimensions": dimensions,
        "dimension_authorizations": authorizations,
        "authorized_response_dimensions": authorized,
        "blocked_response_dimensions": blocked,
        "can_answer_any_requested_dimension": bool(authorized),
        "can_answer_all_requested_dimensions": bool(dimensions)
        and not blocked,
    }


def attested_response_dimension_evidence(
    *,
    current_evidence: Any,
    historical_evidence: Any,
    stale_or_blocked_evidence: Any,
    supporting_evidence: Any = None,
) -> dict[str, list[str]]:
    """Project validated packet roles into dimension-specific evidence sets."""

    current = _evidence_rows(current_evidence)
    historical = _evidence_rows(historical_evidence)
    stale = _evidence_rows(stale_or_blocked_evidence)
    supporting = _evidence_rows(supporting_evidence)
    visible = [*current, *historical, *stale, *supporting]
    visible_ids = _visible_ids(visible)
    current_ids = _visible_ids(current)
    historical_ids = _visible_ids(historical)
    stale_ids = _visible_ids(stale)

    change_ids: set[str] = set()
    endpoint_ids: set[str] = set()
    strict_policy = normalized_temporal_value(STRICT_TEMPORAL_POLICY_VERSION)
    for row in visible:
        memory_id = str(row.get("memory_id") or "").strip()
        relation = normalized_temporal_value(row.get("temporal_relation"))
        if (
            not memory_id
            or normalized_temporal_value(row.get("validity_policy"))
            != strict_policy
            or relation not in _TRANSITION_RELATIONS
        ):
            continue
        targets = {
            str(target).strip()
            for target in row.get("relation_target_memory_ids", [])
            if str(target).strip() in visible_ids
        }
        if not targets:
            continue
        change_ids.add(memory_id)
        if (
            relation in {"replacement", "correction"}
            and memory_id in current_ids
            and targets & (historical_ids | stale_ids)
        ):
            endpoint_ids.add(memory_id)
            endpoint_ids.update(targets)

    conflict_ids: set[str] = set()
    structural_conflicts = {
        str(row.get("memory_id") or "").strip()
        for row in visible
        if str(row.get("memory_id") or "").strip()
        and (
            normalized_temporal_value(row.get("current_status")) == "conflict"
            or normalized_temporal_value(row.get("retrieval_role"))
            == "conflict_candidate"
        )
    }
    if len(structural_conflicts) >= 2:
        conflict_ids.update(structural_conflicts)
    for row in visible:
        memory_id = str(row.get("memory_id") or "").strip()
        if not memory_id:
            continue
        relation = normalized_semantic_value(row.get("semantic_relation"))
        state = row.get("semantic_relation_state", {})
        if (
            relation != "contradiction"
            or not isinstance(state, dict)
            or normalized_semantic_value(state.get("status")) != "known"
            or normalized_semantic_value(state.get("origin"))
            not in _SOURCE_BACKED_RELATION_ORIGINS
        ):
            continue
        targets = {
            str(target).strip()
            for target in row.get("semantic_relation_target_memory_ids", [])
            if str(target).strip() in visible_ids
        }
        if targets:
            conflict_ids.add(memory_id)
            conflict_ids.update(targets)

    return {
        "visible_evidence_ids": sorted(visible_ids),
        "current_value_evidence_ids": sorted(current_ids),
        "historical_value_evidence_ids": sorted(historical_ids),
        "change_relation_evidence_ids": sorted(change_ids),
        "transition_endpoint_evidence_ids": sorted(endpoint_ids),
        "conflict_evidence_ids": sorted(conflict_ids),
    }


def build_answerability_boundary(
    *,
    answer_policy: str,
    evidence_sufficiency: str,
    next_action: str,
    answer_evidence_ids: Any = None,
    premise_correction_evidence_ids: Any = None,
    requested_response_dimensions: Any = None,
    visible_evidence_ids: Any = None,
    current_value_evidence_ids: Any = None,
    historical_value_evidence_ids: Any = None,
    change_relation_evidence_ids: Any = None,
    transition_endpoint_evidence_ids: Any = None,
    conflict_evidence_ids: Any = None,
    condition_bound_evidence_ids: Any = None,
    ambiguity_resolution_evidence_ids: Any = None,
) -> dict[str, Any]:
    """Factor safe response coverage from the controller's next action.

    The boundary does not infer facts or choose a domain-specific answer. It only
    makes explicit which already-source-backed response operations are authorized.
    """

    answer_policy = str(answer_policy or "").strip()
    evidence_sufficiency = str(evidence_sufficiency or "").strip()
    next_action = str(next_action or "").strip()
    answer_ids = _normalized_ids(answer_evidence_ids)
    correction_ids = _normalized_ids(premise_correction_evidence_ids)
    requested_dimensions = normalize_requested_response_dimensions(
        requested_response_dimensions
    )

    if answer_policy == "answer_from_authorized_dimensions":
        state = "answerable_dimensions"
    elif answer_policy == "answer_from_current":
        state = "answerable_current"
    elif answer_policy == "answer_from_archive":
        state = "historical_only"
    elif answer_policy in {
        "correct_then_answer_from_current",
        "correct_premise_only",
    }:
        state = "stale_premise_correctable"
    elif (
        next_action == "clarify_ambiguity"
        or evidence_sufficiency in _AMBIGUITY_SUFFICIENCY_STATES
    ):
        state = "clarify_ambiguity"
    elif next_action == "retrieve_entity_slot_timeline":
        state = "retrieve_timeline"
    elif next_action.startswith("retrieve_") or next_action == (
        "query_rewrite_and_retrieve"
    ):
        state = "retrieve_current"
    else:
        state = "unresolved"

    can_answer_requested_value = answer_policy in {
        "answer_from_current",
        "answer_from_archive",
        "correct_then_answer_from_current",
    }
    can_correct_stale_premise = state == "stale_premise_correctable"
    requires_external_retrieval = next_action.startswith("retrieve_") or (
        next_action == "query_rewrite_and_retrieve"
    )
    requires_clarification = state == "clarify_ambiguity"

    dimension_contract: dict[str, Any] = {}
    if requested_dimensions:
        dimension_contract = build_response_dimension_authorizations(
            requested_response_dimensions=requested_dimensions,
            next_action=next_action,
            visible_evidence_ids=visible_evidence_ids,
            current_value_evidence_ids=current_value_evidence_ids,
            historical_value_evidence_ids=historical_value_evidence_ids,
            change_relation_evidence_ids=change_relation_evidence_ids,
            transition_endpoint_evidence_ids=transition_endpoint_evidence_ids,
            premise_correction_evidence_ids=correction_ids,
            conflict_evidence_ids=conflict_evidence_ids,
            condition_bound_evidence_ids=condition_bound_evidence_ids,
            ambiguity_resolution_evidence_ids=(
                ambiguity_resolution_evidence_ids
            ),
        )
        all_authorized = dimension_contract[
            "can_answer_all_requested_dimensions"
        ]
        value_dimensions = set(requested_dimensions) & {
            "current_value",
            "historical_value",
            "condition_bound_value",
        }
        can_answer_requested_value = bool(value_dimensions) and all(
            dimension_contract["dimension_authorizations"][dimension][
                "status"
            ]
            == "authorized"
            for dimension in value_dimensions
        )
        can_correct_stale_premise = bool(
            dimension_contract["dimension_authorizations"].get(
                "premise_validity",
                {},
            ).get("status")
            == "authorized"
        )
        if all_authorized:
            state = "answerable_dimensions"
            requires_external_retrieval = False
            requires_clarification = False
            answer_ids = sorted(
                {
                    memory_id
                    for row in dimension_contract[
                        "dimension_authorizations"
                    ].values()
                    for memory_id in row["evidence_ids"]
                }
            )
        else:
            answer_ids = []
            if next_action == "clarify_ambiguity":
                state = "clarify_ambiguity"
            elif next_action == "retrieve_entity_slot_timeline":
                state = "retrieve_timeline"
            elif next_action.startswith("retrieve_") or next_action == (
                "query_rewrite_and_retrieve"
            ):
                state = "retrieve_current"
        if not can_correct_stale_premise:
            correction_ids = []

    if state == "answerable_dimensions":
        response_mode = "answer_authorized_dimensions_only"
    elif state == "answerable_current":
        response_mode = "full_current_answer"
    elif state == "historical_only":
        response_mode = "historical_answer_with_time_boundary"
    elif state == "stale_premise_correctable" and can_answer_requested_value:
        response_mode = "correct_premise_then_answer_supported_value"
    elif state == "stale_premise_correctable":
        response_mode = "bounded_correction_then_retrieve"
    elif state == "clarify_ambiguity":
        response_mode = "clarify_before_value_answer"
    elif state in {"retrieve_current", "retrieve_timeline"}:
        response_mode = "abstain_requested_value_then_retrieve"
    else:
        response_mode = "fail_closed"

    if not can_answer_requested_value and not dimension_contract.get(
        "can_answer_all_requested_dimensions",
        False,
    ):
        answer_ids = []
    if not can_correct_stale_premise:
        correction_ids = []

    result = {
        "contract_version": (
            FACTORIZED_ANSWERABILITY_CONTRACT_VERSION
            if requested_dimensions
            else ANSWERABILITY_CONTRACT_VERSION
        ),
        "answerability_state": state,
        "safe_response_mode": response_mode,
        "can_answer_requested_value": can_answer_requested_value,
        "can_correct_stale_premise": can_correct_stale_premise,
        "requires_external_retrieval": requires_external_retrieval,
        "requires_clarification": requires_clarification,
        "answer_evidence_ids": answer_ids,
        "premise_correction_evidence_ids": correction_ids,
        "authorization_rule": (
            "Answer only the response dimensions explicitly authorized here; "
            "retrieval need does not erase a source-backed premise correction, "
            "and premise correction does not authorize an unsupported current value."
        ),
    }
    if requested_dimensions:
        result.update(dimension_contract)
    return result


def validate_answerability_boundary(value: Any) -> dict[str, Any]:
    """Validate a boundary produced or transported by the runtime controller."""

    if not isinstance(value, dict):
        raise ValueError("answerability_boundary must be an object")
    state = str(value.get("answerability_state") or "")
    if state not in ANSWERABILITY_STATES:
        raise ValueError("answerability_boundary.answerability_state is invalid")
    for field_name in (
        "can_answer_requested_value",
        "can_correct_stale_premise",
        "requires_external_retrieval",
        "requires_clarification",
    ):
        if not isinstance(value.get(field_name), bool):
            raise ValueError(f"answerability_boundary.{field_name} must be boolean")
    answer_ids = _normalized_ids(value.get("answer_evidence_ids"))
    correction_ids = _normalized_ids(value.get("premise_correction_evidence_ids"))
    requested_dimensions = normalize_requested_response_dimensions(
        value.get("requested_response_dimensions")
    )
    dimension_authorizations: dict[str, dict[str, Any]] = {}
    all_requested_dimensions_authorized = False
    if requested_dimensions:
        raw_authorizations = value.get("dimension_authorizations")
        if not isinstance(raw_authorizations, dict):
            raise ValueError(
                "factorized answerability boundary requires dimension_authorizations"
            )
        if set(raw_authorizations) != set(requested_dimensions):
            raise ValueError(
                "dimension_authorizations must exactly match requested dimensions"
            )
        for dimension in requested_dimensions:
            row = raw_authorizations[dimension]
            if not isinstance(row, dict):
                raise ValueError(
                    f"dimension_authorizations.{dimension} must be an object"
                )
            status = str(row.get("status") or "")
            if status not in RESPONSE_DIMENSION_STATUSES:
                raise ValueError(
                    f"dimension_authorizations.{dimension}.status is invalid"
                )
            evidence_ids = _normalized_ids(row.get("evidence_ids"))
            if status == "authorized" and not evidence_ids:
                raise ValueError(
                    f"authorized response dimension {dimension} requires evidence"
                )
            if status != "authorized" and evidence_ids:
                raise ValueError(
                    f"blocked response dimension {dimension} cannot expose evidence"
                )
            dimension_authorizations[dimension] = {
                **row,
                "status": status,
                "evidence_ids": evidence_ids,
            }
        authorized_dimensions = sorted(
            dimension
            for dimension, row in dimension_authorizations.items()
            if row["status"] == "authorized"
        )
        blocked_dimensions = sorted(
            set(requested_dimensions) - set(authorized_dimensions)
        )
        all_requested_dimensions_authorized = not blocked_dimensions
        if value.get("authorized_response_dimensions") != authorized_dimensions:
            raise ValueError("authorized_response_dimensions is inconsistent")
        if value.get("blocked_response_dimensions") != blocked_dimensions:
            raise ValueError("blocked_response_dimensions is inconsistent")
        if value.get("can_answer_any_requested_dimension") is not bool(
            authorized_dimensions
        ):
            raise ValueError("can_answer_any_requested_dimension is inconsistent")
        if value.get("can_answer_all_requested_dimensions") is not bool(
            all_requested_dimensions_authorized
        ):
            raise ValueError("can_answer_all_requested_dimensions is inconsistent")
        expected_answer_ids = (
            sorted(
                {
                    memory_id
                    for row in dimension_authorizations.values()
                    for memory_id in row["evidence_ids"]
                }
            )
            if all_requested_dimensions_authorized
            else []
        )
        if answer_ids != expected_answer_ids:
            raise ValueError(
                "factorized answer evidence must equal the fully authorized "
                "dimension evidence closure"
            )
        if state == "answerable_dimensions" and not (
            all_requested_dimensions_authorized
        ):
            raise ValueError(
                "answerable_dimensions requires all requested dimensions"
            )
        if all_requested_dimensions_authorized and state != (
            "answerable_dimensions"
        ):
            raise ValueError(
                "fully authorized dimensions require answerable_dimensions"
            )
    if (
        not value["can_answer_requested_value"]
        and answer_ids
        and not all_requested_dimensions_authorized
    ):
        raise ValueError(
            "answerability_boundary cannot expose answer evidence when the requested "
            "value is not answerable"
        )
    if not value["can_correct_stale_premise"] and correction_ids:
        raise ValueError(
            "answerability_boundary cannot expose correction evidence when premise "
            "correction is not authorized"
        )
    if state == "stale_premise_correctable" and not correction_ids:
        raise ValueError(
            "stale_premise_correctable requires source-backed correction evidence"
        )
    if state in {"retrieve_current", "retrieve_timeline"} and not value[
        "requires_external_retrieval"
    ]:
        raise ValueError(f"{state} must require external retrieval")
    if state == "clarify_ambiguity" and not value["requires_clarification"]:
        raise ValueError("clarify_ambiguity must require clarification")
    result = {
        **value,
        "answer_evidence_ids": answer_ids,
        "premise_correction_evidence_ids": correction_ids,
    }
    if requested_dimensions:
        result["requested_response_dimensions"] = requested_dimensions
        result["dimension_authorizations"] = dimension_authorizations
    return result


def archive_answer_dimension_authorized(
    *,
    query_intent: str,
    query_slot: Any = None,
    embedded_premise: Any,
    current_evidence: Any,
    historical_evidence: Any,
) -> bool:
    """Return whether visible evidence supports an archive-aware answer dimension."""

    query_intent = str(query_intent or "current_state")
    current = _evidence_rows(current_evidence)
    historical = _evidence_rows(historical_evidence)
    visible = [*current, *historical]
    if query_intent == "historical_recall":
        return bool(visible)
    if query_intent == "validity_audit":
        return not str(embedded_premise or "").strip() and bool(visible)

    temporal_relations = _attested_temporal_relation_types(visible)
    semantic_relations = _attested_semantic_relation_types(visible)
    if query_intent == "conflict_audit":
        return bool(
            semantic_relations & _CONFLICT_RELATIONS
            or temporal_relations & _TRANSITION_RELATIONS
        )
    if query_intent == "timeline_change":
        return bool(temporal_relations & _TRANSITION_RELATIONS) or (
            _has_structural_prior_current_pair(
                current=current,
                historical=historical,
                query_slot=query_slot,
            )
            or _has_scalar_temporal_sequence(visible)
        )
    return False


def _normalized_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("answerability evidence ids must be a list-like collection")
    normalized = {str(item).strip() for item in value if str(item).strip()}
    return sorted(normalized)


def _evidence_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _visible_ids(visible: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("memory_id") or "").strip()
        for row in visible
        if str(row.get("memory_id") or "").strip()
    }


def _relation_targets_visible(row: dict[str, Any], visible_ids: set[str], field: str) -> bool:
    targets = row.get(field, [])
    return isinstance(targets, list) and bool(
        visible_ids & {str(target).strip() for target in targets if str(target).strip()}
    )


def _attested_temporal_relation_types(
    visible: list[dict[str, Any]],
) -> set[str]:
    visible_ids = _visible_ids(visible)
    strict_policy = normalized_temporal_value(STRICT_TEMPORAL_POLICY_VERSION)
    return {
        normalized_temporal_value(row.get("temporal_relation"))
        for row in visible
        if normalized_temporal_value(row.get("validity_policy")) == strict_policy
        and _relation_targets_visible(
            row,
            visible_ids,
            "relation_target_memory_ids",
        )
    }


def _attested_semantic_relation_types(
    visible: list[dict[str, Any]],
) -> set[str]:
    visible_ids = {
        str(row.get("memory_id") or "").strip()
        for row in visible
        if str(row.get("memory_id") or "").strip()
    }
    return {
        normalized_semantic_value(row.get("semantic_relation"))
        for row in visible
        if isinstance(row.get("semantic_relation_state"), dict)
        and normalized_semantic_value(row["semantic_relation_state"].get("status"))
        == "known"
        and normalized_semantic_value(row["semantic_relation_state"].get("origin"))
        in _SOURCE_BACKED_RELATION_ORIGINS
        and _relation_targets_visible(
            row,
            visible_ids,
            "semantic_relation_target_memory_ids",
        )
    }


def _has_scalar_temporal_sequence(visible: list[dict[str, Any]]) -> bool:
    if len(visible) < 2 or any(
        normalized_temporal_value(row.get("slot_cardinality")) != "single"
        for row in visible
    ):
        return False
    return _has_distinct_temporal_anchors(visible)


def _has_structural_prior_current_pair(
    *,
    current: list[dict[str, Any]],
    historical: list[dict[str, Any]],
    query_slot: Any,
) -> bool:
    query_base, _ = _temporal_role_slot(query_slot)
    return bool(current) and any(
        normalized_temporal_value(row.get("structural_temporal_role")) == "prior"
        and normalized_temporal_value(row.get("canonical_slot")) == query_base
        for row in historical
    )


def _temporal_role_slot(value: Any) -> tuple[str, str]:
    normalized = " ".join(
        "".join(character if character.isalnum() else " " for character in str(value or "").lower()).split()
    )
    for prefix in ("previous ", "prior ", "former "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip(), "prior"
    return normalized, "current"


def _has_distinct_temporal_anchors(visible: list[dict[str, Any]]) -> bool:
    anchors = {
        anchor
        for row in visible
        if (anchor := _temporal_anchor(row)) is not None
    }
    return len(anchors) >= 2


def _temporal_anchor(row: dict[str, Any]) -> float | None:
    for field_name in (
        "effective_from",
        "event_time",
        "observed_at",
        "source_time",
    ):
        raw = str(row.get(field_name) or "").strip()
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    return None


__all__ = [
    "ANSWERABILITY_CONTRACT_VERSION",
    "ANSWERABILITY_STATES",
    "ARCHIVE_AWARE_QUERY_INTENTS",
    "DUAL_PROVIDER_ATTESTATION_VERSION",
    "FACTORIZED_ANSWERABILITY_CONTRACT_VERSION",
    "RESPONSE_DIMENSION_ATTESTATION_VERSION",
    "RELATION_GATED_QUERY_INTENTS",
    "RESPONSE_DIMENSIONS",
    "RESPONSE_DIMENSION_ATTESTED_ORIGINS",
    "RESPONSE_DIMENSION_STATUSES",
    "attested_response_dimension_evidence",
    "archive_answer_dimension_authorized",
    "build_answerability_boundary",
    "build_dual_provider_attestation",
    "build_response_dimension_attestation",
    "build_response_dimension_authorizations",
    "normalize_requested_response_dimensions",
    "validate_answerability_boundary",
    "validate_response_dimension_state",
]
