"""Query-risk router for selective QVF application.

The router is intentionally deterministic and conservative.  It does not
answer a query; it labels whether a retrieved-memory question should use a
direct preserve-first path or a validity-aware QVF routing path.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


QUERY_RISK_ROUTER_VERSION = "qvf_query_risk_router_v1.10"

LOW_RISK_ROUTE = "direct_preserve_first"
CURRENT_ROUTE = "qvf_current_archive_router"
EVIDENCE_CONFLICT_ROUTE = "qvf_evidence_conflict_router"
TRANSITION_ROUTE = "qvf_transition_router"
CONDITIONAL_ROUTE = "qvf_conditional_scope_router"
RETRIEVAL_SUFFICIENCY_ROUTE = "qvf_retrieval_sufficiency_router"


@dataclass(frozen=True)
class QueryRiskRoute:
    query_text: str
    query_type: str
    risk_level: str
    recommended_route: str
    should_apply_qvf: bool
    confidence: float
    cues: list[str]
    reason: str
    evidence_risk: dict[str, Any]
    confidence_semantics: str = "heuristic_priority_score_not_calibrated_probability"
    router_version: str = QUERY_RISK_ROUTER_VERSION


CURRENT_CUES = (
    "now",
    "current",
    "currently",
    "latest",
    "still",
    "anymore",
    "no longer",
    "today",
    "these days",
    "right now",
    "up to date",
)

CHANGE_CUES = (
    "change",
    "changed",
    "switch",
    "switched",
    "move",
    "moved",
    "became",
    "become",
    "transition",
    "used to",
    "stayed the same",
    "stay the same",
    "no longer",
)

TEMPORAL_CUES = (
    "before",
    "after",
    "when",
    "timeline",
    "earlier",
    "later",
    "previous",
    "previously",
    "next month",
    "since",
    "how long",
)

RECENT_SCOPE_PATTERNS = (
    ("recency_adverb", r"\b(?:recent|recently|lately)\b"),
    (
        "relative_calendar_window",
        r"\b(?:this|last|previous|past|next|earlier)\s+"
        r"(?:day|week|weekend|month|year|quarter|semester|season)\b",
    ),
    ("deictic_day_window", r"\b(?:today|yesterday|tomorrow|tonight)\b"),
    (
        "rolling_duration_window",
        r"\b(?:over\s+the\s+past|past|last)\s+"
        r"(?:few|several|\d+)?\s*"
        r"(?:days|weeks|months|years)\b",
    ),
)

CONDITIONAL_CUES = (
    "under what condition",
    "condition",
    "if ",
    "when does",
    "when do",
    "during",
    "while",
    "on days",
)

CONFLICT_CUES = (
    "conflict",
    "contradict",
    "which is true",
    "still true",
    "valid",
    "invalid",
    "outdated",
    "stale",
    "old memory",
    "new memory",
)

UNKNOWN_CUES = (
    "do we know",
    "can we tell",
    "is there evidence",
    "unknown",
    "not sure",
    "enough evidence",
)

MULTI_SESSION_CUES = (
    "across",
    "both",
    "all sessions",
    "sessions",
    "over time",
    "summarize",
    "compare",
    "relationship between",
)

TEMPORAL_COMPARISON_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "after",
    "be",
    "before",
    "between",
    "did",
    "do",
    "does",
    "earlier",
    "earliest",
    "first",
    "following",
    "for",
    "happen",
    "happened",
    "has",
    "had",
    "have",
    "i",
    "in",
    "is",
    "its",
    "last",
    "later",
    "latest",
    "least",
    "more",
    "most",
    "my",
    "new",
    "of",
    "or",
    "our",
    "preceding",
    "recent",
    "recently",
    "than",
    "the",
    "that",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "which",
    "who",
    "with",
}

COUNTED_SET_SCALAR_NOUNS = {
    "age",
    "ages",
    "day",
    "days",
    "dollar",
    "dollars",
    "duration",
    "durations",
    "hour",
    "hours",
    "kilometer",
    "kilometers",
    "meter",
    "meters",
    "metre",
    "metres",
    "mile",
    "miles",
    "minute",
    "minutes",
    "money",
    "month",
    "months",
    "mpg",
    "percent",
    "percentage",
    "percentages",
    "pound",
    "pounds",
    "second",
    "seconds",
    "time",
    "times",
    "week",
    "weeks",
    "year",
    "years",
}

COUNTED_SET_IRREGULAR_PLURALS = {
    "children",
    "men",
    "people",
    "women",
}


def route_query_risk(
    query_text: str,
    *,
    query_metadata: dict[str, Any] | None = None,
    retrieved_memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Route a query to direct or QVF based on validity-risk cues."""

    text = _normalize(query_text)
    query_metadata = query_metadata or {}
    retrieved_memories = retrieved_memories or []
    coordinated_slot_context = infer_query_coordinated_slots(
        query_text,
        retrieved_memories,
        entity=str(query_metadata.get("entity") or query_metadata.get("subject") or ""),
        primary_slot=str(
            query_metadata.get("slot") or query_metadata.get("attribute") or ""
        ),
    )
    if (
        coordinated_slot_context.get("applied")
        and not query_metadata.get("coordinated_slots")
    ):
        query_metadata = deepcopy(query_metadata)
        query_metadata["coordinated_slots"] = coordinated_slot_context[
            "coordinated_slots"
        ]
    retrieved_memories, cardinality_overlay = apply_query_conditioned_cardinality(
        query_text,
        retrieved_memories,
        query_metadata=query_metadata,
    )
    cues = _cue_matches(text)
    evidence_risk = _memory_validity_analysis(
        retrieved_memories,
        query_metadata=query_metadata,
        query_text=text,
    )
    evidence_risk["query_conditioned_cardinality"] = cardinality_overlay
    evidence_risk["coordinated_slot_context"] = coordinated_slot_context
    memory_cues = list(evidence_risk.get("cues", []))
    cues.extend(cue for cue in memory_cues if cue not in cues)

    metadata_needs_current = _metadata_flag(query_metadata.get("needs_current"))
    metadata_intent = str(query_metadata.get("query_intent") or query_metadata.get("risk_profile") or "")
    if metadata_needs_current:
        cues.append("metadata:needs_current")
    if _metadata_intent_has(metadata_intent, "conflict"):
        cues.append("metadata:conflict")
    if _metadata_intent_has(metadata_intent, "change", "timeline"):
        cues.append("metadata:timeline_change")

    cues = sorted(set(cues))

    query_type, route, risk_level, reason = _classify(
        text,
        cues,
        query_metadata,
        evidence_risk,
    )
    should_apply_qvf = route != LOW_RISK_ROUTE
    confidence = _confidence(query_type, cues, should_apply_qvf)
    return asdict(
        QueryRiskRoute(
            query_text=query_text,
            query_type=query_type,
            risk_level=risk_level,
            recommended_route=route,
            should_apply_qvf=should_apply_qvf,
            confidence=confidence,
            cues=cues,
            reason=reason,
            evidence_risk=evidence_risk,
        )
    )


def partition_query_evidence_qualifiers(
    query_text: str,
    qualifiers: Any,
    *,
    entity: str = "",
    slot: str = "",
) -> dict[str, Any]:
    """Separate answer-class projections from restrictive query qualifiers."""

    if isinstance(qualifiers, str):
        qualifiers = [qualifiers]
    if not isinstance(qualifiers, list):
        qualifiers = []
    normalized_qualifiers: list[str] = []
    for value in qualifiers:
        if not isinstance(value, str):
            continue
        normalized = _normalize_qualifier_phrase(value)
        if normalized and normalized not in normalized_qualifiers:
            normalized_qualifiers.append(normalized)

    normalized_query = _normalize_qualifier_phrase(query_text)
    target_match = re.search(
        r"\bhow\s+many\s+(?P<target>.+?)\s+"
        r"(?:do|does|did|am|is|are|was|were|have|has|had|can|could|"
        r"should|would|will)\b",
        normalized_query,
    )
    target_phrase = target_match.group("target") if target_match else ""
    scope_stems = {
        _light_value_stem(token)
        for token in re.findall(
            r"[a-z0-9]+",
            _normalize_qualifier_phrase(f"{entity} {slot}"),
        )
        if token not in {"a", "an", "of", "the", "to"}
    }
    nominal: list[str] = []
    restrictive: list[str] = []
    classifications: list[dict[str, Any]] = []
    for qualifier in normalized_qualifiers:
        qualifier_stems = {
            _light_value_stem(token)
            for token in re.findall(r"[a-z0-9]+", qualifier)
            if token not in {"a", "an", "of", "the", "to"}
        }
        target_bound = bool(
            target_phrase
            and re.search(
                rf"(?<![a-z0-9]){re.escape(qualifier)}(?![a-z0-9])",
                target_phrase,
            )
        )
        scope_covered = bool(qualifier_stems) and qualifier_stems <= scope_stems
        role = (
            "nominal_class_projection"
            if target_bound and scope_covered
            else "restrictive_scope"
        )
        if role == "nominal_class_projection":
            nominal.append(qualifier)
        else:
            restrictive.append(qualifier)
        classifications.append(
            {
                "qualifier": qualifier,
                "role": role,
                "target_bound": target_bound,
                "scope_covered": scope_covered,
                "qualifier_stems": sorted(qualifier_stems),
            }
        )
    return {
        "applied": bool(nominal),
        "target_phrase": target_phrase,
        "nominal_class_qualifiers": nominal,
        "restrictive_qualifiers": restrictive,
        "classifications": classifications,
        "reason": (
            "nominal_class_projection_removed_from_hard_requirements"
            if nominal
            else "all_qualifiers_remain_restrictive"
        ),
    }


def _normalize_qualifier_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def infer_query_coordinated_slots(
    query_text: str,
    memories: list[dict[str, Any]],
    *,
    entity: str,
    primary_slot: str,
    max_gap_tokens: int = 8,
) -> dict[str, Any]:
    """Infer query-bound coordinated slots from structural lexical evidence."""

    context: dict[str, Any] = {
        "applied": False,
        "entity": entity,
        "primary_slot": primary_slot,
        "coordinated_slots": [],
        "bound_slot_spans": [],
        "max_gap_tokens": max_gap_tokens,
        "reason": "insufficient_same_entity_candidate_slots",
    }
    normalized_entity = _normalize(entity)
    normalized_primary = _normalize(primary_slot)
    if not normalized_entity or not normalized_primary:
        context["reason"] = "missing_primary_entity_or_slot"
        return context

    candidate_slots: list[str] = []
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        memory_entity = _normalize(
            str(memory.get("entity") or memory.get("subject") or "")
        )
        slot = str(memory.get("slot") or memory.get("attribute") or "").strip()
        if memory_entity != normalized_entity or not slot:
            continue
        if all(_normalize(existing) != _normalize(slot) for existing in candidate_slots):
            candidate_slots.append(slot)
    primary_name = next(
        (
            slot
            for slot in candidate_slots
            if _normalize(slot) == normalized_primary
        ),
        "",
    )
    if not primary_name or len(candidate_slots) < 2:
        return context

    slot_tokens = {
        slot: {
            _light_value_stem(token)
            for token in re.findall(r"[a-z0-9]+", slot.lower().replace("_", " "))
            if token not in {"a", "an", "of", "the", "to"}
        }
        for slot in candidate_slots
    }
    shared_tokens = set.intersection(*slot_tokens.values()) if slot_tokens else set()
    query_tokens = [
        _light_value_stem(token)
        for token in re.findall(r"[a-z0-9]+", query_text.lower())
    ]
    spans: dict[str, tuple[int, int, list[str]]] = {}
    for slot, tokens in slot_tokens.items():
        distinctive = sorted(tokens - shared_tokens)
        if not distinctive:
            continue
        positions: list[int] = []
        for token in distinctive:
            try:
                positions.append(query_tokens.index(token))
            except ValueError:
                positions = []
                break
        if positions:
            spans[slot] = (min(positions), max(positions), distinctive)
    if primary_name not in spans or len(spans) < 2:
        context["reason"] = "fewer_than_two_query_bound_distinctive_slots"
        return context

    adjacency = {slot: set() for slot in spans}
    span_items = list(spans.items())
    for index, (left_slot, left_span) in enumerate(span_items):
        for right_slot, right_span in span_items[index + 1 :]:
            first_slot, first_span, second_slot, second_span = (
                (left_slot, left_span, right_slot, right_span)
                if left_span[0] <= right_span[0]
                else (right_slot, right_span, left_slot, left_span)
            )
            gap = second_span[0] - first_span[1] - 1
            if gap < 0 or gap > max_gap_tokens:
                continue
            between = query_tokens[first_span[1] + 1 : second_span[0]]
            coordinated = bool(
                set(between) & {"and", "or", "plus"}
                or all(token in between for token in ("as", "well"))
            )
            if coordinated:
                adjacency[first_slot].add(second_slot)
                adjacency[second_slot].add(first_slot)

    connected = {primary_name}
    stack = [primary_name]
    while stack:
        slot = stack.pop()
        for neighbor in adjacency.get(slot, set()):
            if neighbor not in connected:
                connected.add(neighbor)
                stack.append(neighbor)
    coordinated_slots = [
        slot
        for slot in candidate_slots
        if slot in connected and slot != primary_name
    ]
    if not coordinated_slots:
        context["reason"] = "no_nearby_coordination_edge_from_primary_slot"
        return context
    context.update(
        {
            "applied": True,
            "primary_slot": primary_name,
            "coordinated_slots": coordinated_slots,
            "bound_slot_spans": [
                {
                    "slot": slot,
                    "start_token": spans[slot][0],
                    "end_token": spans[slot][1],
                    "distinctive_tokens": spans[slot][2],
                }
                for slot in candidate_slots
                if slot in connected
            ],
            "reason": "query_bound_slots_connected_by_nearby_coordination",
        }
    )
    return context


def apply_query_conditioned_cardinality(
    query_text: str,
    memories: list[dict[str, Any]],
    *,
    query_metadata: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Annotate query-scoped counted sets without mutating extracted records."""

    annotated = [deepcopy(memory) for memory in memories if isinstance(memory, dict)]
    counted_noun = _counted_set_query_noun(query_text)
    context: dict[str, Any] = {
        "applied": False,
        "counted_noun": counted_noun,
        "reason": "query_does_not_request_a_counted_set",
        "group_count": 0,
        "groups": [],
    }
    if not counted_noun:
        return annotated, context

    query_scope = _normalized_query_scope(query_metadata or {})
    scoped_indices = [
        index
        for index, memory in enumerate(annotated)
        if _memory_matches_query_scope(memory, query_scope)
    ]
    grouped: dict[tuple[str, str], list[int]] = {}
    for index in scoped_indices:
        memory = annotated[index]
        entity = _normalize(str(memory.get("entity") or memory.get("subject") or "user"))
        slot = _normalize(str(memory.get("slot") or memory.get("attribute") or ""))
        if not slot:
            continue
        grouped.setdefault((entity, slot), []).append(index)

    promoted_groups: list[dict[str, Any]] = []
    for (entity, slot), indices in sorted(grouped.items()):
        rows = [annotated[index] for index in indices]
        if not _counted_noun_matches_slot(counted_noun, slot):
            continue
        if any(_memory_value_is_scalar_count(row) for row in rows):
            continue
        values = sorted(
            {
                signature
                for row in rows
                if (signature := _memory_value_signature(row))
            }
        )
        semantic_values = _semantic_value_representatives(values)
        if len(semantic_values) < 2:
            continue
        statuses = {
            _normalize(str(row.get("current_status") or row.get("validity_status") or ""))
            for row in rows
        }
        status_replacement = bool(
            statuses & {"current", "active"}
            and statuses & {"stale", "archive", "expired", "invalid", "revoked"}
        )
        if status_replacement or any(_memory_has_replacement_relation(row) for row in rows):
            continue
        memory_ids: list[str] = []
        for index in indices:
            row = annotated[index]
            row["query_slot_cardinality"] = "set"
            row["query_cardinality_evidence"] = {
                "mode": "counted_plural_query",
                "counted_noun": counted_noun,
                "query_scope_entity": entity,
                "query_scope_slot": slot,
                "semantic_value_count": len(semantic_values),
            }
            memory_id = str(row.get("memory_id") or row.get("id") or "")
            if memory_id:
                memory_ids.append(memory_id)
        promoted_groups.append(
            {
                "entity": entity,
                "slot": slot,
                "counted_noun": counted_noun,
                "semantic_value_count": len(semantic_values),
                "memory_ids": memory_ids,
                "reason": "query_requests_count_over_distinct_nonreplacement_values",
            }
        )

    context.update(
        {
            "applied": bool(promoted_groups),
            "reason": (
                "query_scoped_counted_set_groups_promoted"
                if promoted_groups
                else "no_multi_value_nonreplacement_query_scope_group"
            ),
            "group_count": len(promoted_groups),
            "groups": promoted_groups,
        }
    )
    return annotated, context


def _counted_set_query_noun(query_text: str) -> str:
    match = re.search(r"\bhow\s+many\s+(?P<noun>[a-z][a-z-]*)\b", _normalize(query_text))
    if not match:
        return ""
    noun = match.group("noun")
    if noun in COUNTED_SET_SCALAR_NOUNS:
        return ""
    if noun in COUNTED_SET_IRREGULAR_PLURALS:
        return noun
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun
    return ""


def _memory_matches_query_scope(
    memory: dict[str, Any],
    query_scope: dict[str, Any],
) -> bool:
    if not query_scope.get("applied"):
        return True
    target_entity = str(query_scope.get("entity") or "")
    target_slots = {
        str(slot)
        for slot in query_scope.get("slots", [])
        if str(slot)
    }
    entity = _normalize(str(memory.get("entity") or memory.get("subject") or "user"))
    slot = _normalize(str(memory.get("slot") or memory.get("attribute") or ""))
    if target_slots and slot not in target_slots:
        return False
    if target_entity and entity and entity != target_entity:
        return False
    return True


def _counted_noun_matches_slot(counted_noun: str, slot: str) -> bool:
    noun_stem = _light_value_stem(counted_noun)
    slot_stems = {
        _light_value_stem(token)
        for token in re.findall(r"[a-z0-9]+", slot.lower().replace("_", " "))
    }
    return bool(noun_stem and noun_stem in slot_stems)


def _memory_value_is_scalar_count(memory: dict[str, Any]) -> bool:
    value = _normalize(str(memory.get("value") or ""))
    if not value:
        return True
    if value in {"n/a", "none", "not specified", "unknown", "unspecified"}:
        return True
    number_words = {
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    }
    tokens = re.findall(r"[a-z0-9]+", value)
    if not tokens:
        return True
    scalar_modifiers = {
        "about",
        "approximately",
        "around",
        "exactly",
        "nearly",
        "roughly",
    }
    substantive = [token for token in tokens if token not in scalar_modifiers]
    return bool(substantive) and all(
        token.isdigit() or token in number_words for token in substantive
    )


def write_query_risk_route(
    output_path: Path,
    *,
    query_text: str,
    query_metadata: dict[str, Any] | None = None,
    retrieved_memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write a single query-risk route JSON artifact."""

    route = route_query_risk(
        query_text,
        query_metadata=query_metadata,
        retrieved_memories=retrieved_memories,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(route, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return route


def _classify(
    text: str,
    cues: list[str],
    query_metadata: dict[str, Any],
    evidence_risk: dict[str, Any],
) -> tuple[str, str, str, str]:
    explicit_conflict = _has_prefix(cues, "conflict:") or "metadata:conflict" in cues
    status_mix_requires_control = (
        _has_conflicting_memory_status(cues)
        and not _is_explicit_historical_archive_recall(text)
    )
    if explicit_conflict or status_mix_requires_control:
        return (
            "current_state_or_update",
            CURRENT_ROUTE,
            "high",
            "The query or retrieved memories indicate possible validity conflict.",
        )
    if _temporal_comparison_should_apply(cues, evidence_risk):
        return (
            "temporal_reasoning",
            TRANSITION_ROUTE,
            "high",
            "The query requires ordering multiple candidates and retrieved evidence provides candidate-bound temporal support.",
        )
    if _explicit_replacement_should_apply(text, evidence_risk):
        return (
            "current_state_or_update",
            EVIDENCE_CONFLICT_ROUTE,
            "high",
            "Retrieved evidence explicitly removes, revokes, or replaces a competing value; this structural validity signal overrides generic preference/advice preservation.",
        )
    if _has_versioned_evidence_conflict(cues) and _low_risk_recall_should_override_evidence_conflict(
        text, cues
    ):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Retrieved evidence has versioned values, but the query is preference, generic accessory, or recent-event recall rather than a validity decision.",
        )
    if _recommendation_or_advice_should_fail_open(text, cues, evidence_risk):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Advice or recommendation requests preserve direct context unless they contain an explicit stale/current premise or validity decision.",
        )
    if _evidence_conflict_should_apply(text, cues, query_metadata, evidence_risk):
        return (
            "current_state_or_update",
            EVIDENCE_CONFLICT_ROUTE,
            "high",
            "Retrieved evidence contains versioned same-slot value conflict for a state-sensitive query.",
        )
    if _change_scope_gap_should_route_to_sufficiency(
        text,
        cues,
        evidence_risk,
    ):
        return (
            "retrieval_sufficiency",
            RETRIEVAL_SUFFICIENCY_ROUTE,
            "medium",
            "The query asks for a state change, but the retrieved set contains no query-scoped evidence; run the validity controller so it can request bounded retrieval repair instead of answering from unrelated rows.",
        )
    if _current_cue_should_fail_open(text, cues):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Current/recent wording appears in recommendation, preference, or event recall without explicit validity conflict.",
        )
    if _has_prefix(cues, "current:") or _metadata_flag(query_metadata.get("needs_current")):
        if _current_or_metadata_should_apply(text, cues, query_metadata, evidence_risk):
            return (
                "current_state_or_update",
                CURRENT_ROUTE,
                "high",
                "The query asks for a validity-sensitive current or latest state.",
            )
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Current wording alone is not enough to activate QVF without conflict, validity, or state-sensitive evidence risk.",
        )
    if _change_detail_evidence_should_apply(text, cues, evidence_risk):
        return (
            "temporal_reasoning",
            TRANSITION_ROUTE,
            "high",
            "The query asks for a concrete change detail and retrieved evidence indicates an update or version transition.",
        )
    if _has_prefix(cues, "unknown:"):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Uncertainty wording alone is not a validity-admission risk without current or conflict cues.",
        )
    if _condition_preference_scope_should_apply(text, evidence_risk):
        return (
            "conditional_scope",
            CONDITIONAL_ROUTE,
            "medium",
            "The query asks for a condition-bound preference and retrieved evidence contains condition-bearing answer candidates.",
        )
    if _has_prefix(cues, "conditional:"):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Condition-scope recall should preserve direct context unless current/conflict evidence is explicit.",
        )
    if _has_prefix(cues, "change:") or "metadata:timeline_change" in cues:
        if not _is_explicit_validity_change_query(text, cues):
            return (
                "ordinary_recall",
                LOW_RISK_ROUTE,
                "low",
                "The query has change/history wording but no explicit current-state or validity comparison.",
            )
        return (
            "temporal_reasoning",
            TRANSITION_ROUTE,
            "high",
            "The query asks for an explicit old-to-current, validity, or stayed-same comparison.",
        )
    if _has_prefix(cues, "temporal_recent:"):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "A recent window alone is retrieval scope, not a memory-validity decision.",
        )
    if _has_prefix(cues, "temporal:"):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Historical scope wording alone should preserve direct memory context.",
        )
    if _has_prefix(cues, "multi_session:"):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Multi-session recall is not a validity-admission risk without current/change/conflict cues.",
        )
    if _is_plain_profile_recall(text):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "The query is a plain recall request with no validity-risk cue.",
        )
    return (
        "ordinary_recall",
        LOW_RISK_ROUTE,
        "low",
        "No clear stale/current/conditional/temporal risk cue was detected.",
    )


def _cue_matches(text: str) -> list[str]:
    out: list[str] = []
    out.extend(f"current:{cue}" for cue in CURRENT_CUES if _phrase_cue_present(text, cue))
    out.extend(f"change:{cue}" for cue in CHANGE_CUES if _phrase_cue_present(text, cue))
    out.extend(_recent_scope_cue_matches(text))
    out.extend(f"temporal:{cue}" for cue in TEMPORAL_CUES if _phrase_cue_present(text, cue))
    out.extend(f"conditional:{cue}" for cue in CONDITIONAL_CUES if _phrase_cue_present(text, cue))
    out.extend(f"conflict:{cue}" for cue in CONFLICT_CUES if _phrase_cue_present(text, cue))
    out.extend(f"unknown:{cue}" for cue in UNKNOWN_CUES if _phrase_cue_present(text, cue))
    out.extend(f"multi_session:{cue}" for cue in MULTI_SESSION_CUES if _phrase_cue_present(text, cue))
    if re.search(r"\b(did|has|have)\b.+\b(change|changed|stay|stayed)\b", text):
        out.append("change:did_has_change_pattern")
    if _is_temporal_comparison_query(text):
        out.append("temporal_comparison:relational_order")
    return out


def _phrase_cue_present(text: str, cue: str) -> bool:
    """Match a lexical cue as a token sequence rather than an arbitrary substring."""

    normalized_cue = _normalize(cue)
    if not normalized_cue:
        return False
    pattern = re.escape(normalized_cue).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text))


def _recent_scope_cue_matches(text: str) -> list[str]:
    return [
        f"temporal_recent:{label}"
        for label, pattern in RECENT_SCOPE_PATTERNS
        if re.search(pattern, text)
    ]


def _has_recent_scope_reference(text: str) -> bool:
    return bool(_recent_scope_cue_matches(text))


def _has_current_window_reference(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:right\s+now|today|tonight|these\s+days|"
            r"this\s+(?:day|week|weekend|month|year|quarter|semester|season)|"
            r"upcoming\s+(?:day|week|weekend|month|year|quarter|semester|season)|"
            r"next\s+(?:day|week|weekend|month|year|quarter|semester|season))\b",
            text,
        )
    )


def _is_temporal_comparison_query(text: str) -> bool:
    """Return whether the query asks for a relation between candidate times."""

    ordinal = r"(?:first|last|earliest|latest)"
    relation = r"(?:before|after|following|preceding)"
    return bool(
        re.search(r"\bmore\s+recent(?:ly)?\b", text)
        or re.search(r"\b(?:earlier|later|newer|older)\s+than\b", text)
        or re.search(
            r"\b(?:which|what|who)\b.{0,120}\b(?:came|happened|occurred|started|ended|was|were)\s+"
            r"(?:first|last|earlier|later)\b",
            text,
        )
        or re.search(rf"\b{ordinal}\b.{{0,160}}\b{relation}\b", text)
        or re.search(rf"\b{relation}\b.{{0,160}}\b{ordinal}\b", text)
    )


def is_temporal_comparison_query(text: str) -> bool:
    """Public structural predicate shared by Router and answer-context policy."""

    return _is_temporal_comparison_query(_normalize(str(text or "")))


def _memory_validity_cues(memories: list[dict[str, Any]]) -> list[str]:
    """Backward-compatible cue-only wrapper for callers/tests that inspect internals."""

    return list(_memory_validity_analysis(memories).get("cues", []))


def _memory_validity_analysis(
    memories: list[dict[str, Any]],
    *,
    query_metadata: dict[str, Any] | None = None,
    query_text: str = "",
) -> dict[str, Any]:
    valid_memories = [memory for memory in memories if isinstance(memory, dict)]
    query_scope = _normalized_query_scope(query_metadata or {})
    scoped_memories = _query_scoped_memories(valid_memories, query_scope)
    analyzed_memories = scoped_memories if query_scope["applied"] else valid_memories
    statuses = {
        _normalize(str(memory.get("current_status") or memory.get("validity_status") or ""))
        for memory in analyzed_memories
    }
    roles = {
        _normalize(str(memory.get("retrieval_role") or _memory_source_type(memory) or ""))
        for memory in analyzed_memories
    }
    out: list[str] = []
    if any(status in {"current", "active"} for status in statuses) and any(
        status in {"stale", "archive", "expired", "invalid"} for status in statuses
    ):
        out.append("memory:current_archive_mix")
    if any("stale" in role or "archive" in role for role in roles):
        out.append("memory:archive_or_stale_role")
    all_slot_analysis = _slot_value_group_analysis(valid_memories)
    slot_analysis = _slot_value_group_analysis(analyzed_memories)
    all_conflict_groups = all_slot_analysis["conflict_groups"]
    conflict_groups = slot_analysis["conflict_groups"]
    if conflict_groups:
        out.append("memory:slot_value_conflict")
    if any(group.get("has_temporal_order") for group in conflict_groups):
        out.append("memory:temporal_versioned_conflict")
    if _has_memory_update_language(analyzed_memories):
        out.append("memory:update_language")
    condition_bearing_record_count = _condition_bearing_record_count(analyzed_memories)
    if condition_bearing_record_count:
        out.append("memory:condition_bearing_evidence")
    temporal_comparison = _temporal_comparison_evidence_analysis(
        query_text,
        valid_memories,
        query_scope,
    )
    if temporal_comparison["eligible"]:
        out.append("memory:temporal_comparison_evidence")
    return {
        "memory_count": len(valid_memories),
        "analyzed_memory_count": len(analyzed_memories),
        "query_scope": query_scope,
        "cues": sorted(set(out)),
        "status_values": sorted(status for status in statuses if status),
        "role_values": sorted(role for role in roles if role),
        "conflict_group_count": len(conflict_groups),
        "conflict_groups": conflict_groups[:5],
        "unscoped_conflict_group_count": len(all_conflict_groups),
        "semantic_equivalent_group_count": slot_analysis[
            "semantic_equivalent_group_count"
        ],
        "semantic_equivalent_value_collapse_count": slot_analysis[
            "semantic_equivalent_value_collapse_count"
        ],
        "coexisting_set_group_count": slot_analysis["coexisting_set_group_count"],
        "coexisting_set_groups": slot_analysis["coexisting_set_groups"][:5],
        "replacement_reactivated_group_count": slot_analysis[
            "replacement_reactivated_group_count"
        ],
        "condition_bearing_record_count": condition_bearing_record_count,
        "temporal_comparison": temporal_comparison,
    }


def _normalized_query_scope(query_metadata: dict[str, Any]) -> dict[str, Any]:
    entity = _normalize(
        str(query_metadata.get("entity") or query_metadata.get("subject") or "")
    )
    slot = _normalize(
        str(query_metadata.get("slot") or query_metadata.get("attribute") or "")
    )
    raw_coordinated = query_metadata.get("coordinated_slots", [])
    if isinstance(raw_coordinated, str):
        raw_coordinated = [raw_coordinated]
    coordinated_slots = [
        normalized
        for value in raw_coordinated
        if isinstance(value, str) and (normalized := _normalize(value)) and normalized != slot
    ] if isinstance(raw_coordinated, list) else []
    slots = list(dict.fromkeys([value for value in [slot, *coordinated_slots] if value]))
    return {
        "entity": entity,
        "slot": slot,
        "slots": slots,
        "coordinated_slots": coordinated_slots,
        "applied": bool(entity or slot),
    }


def _query_scoped_memories(
    memories: list[dict[str, Any]],
    query_scope: dict[str, Any],
) -> list[dict[str, Any]]:
    if not query_scope.get("applied"):
        return memories
    target_entity = str(query_scope.get("entity") or "")
    target_slots = {
        str(slot)
        for slot in query_scope.get("slots", [])
        if str(slot)
    }
    scoped: list[dict[str, Any]] = []
    for memory in memories:
        memory_entity = _normalize(
            str(memory.get("entity") or memory.get("subject") or "user")
        )
        memory_slot = _normalize(
            str(memory.get("slot") or memory.get("attribute") or "")
        )
        if target_slots and memory_slot not in target_slots:
            continue
        if target_entity and memory_entity and memory_entity != target_entity:
            continue
        scoped.append(memory)
    return scoped


def _temporal_comparison_evidence_analysis(
    query_text: str,
    memories: list[dict[str, Any]],
    query_scope: dict[str, Any],
) -> dict[str, Any]:
    intent_detected = _is_temporal_comparison_query(query_text)
    result: dict[str, Any] = {
        "intent_detected": intent_detected,
        "eligible": False,
        "entity_scoped_memory_count": 0,
        "temporal_record_count": 0,
        "bound_record_count": 0,
        "bound_candidate_count": 0,
        "bound_memory_ids": [],
        "candidate_terms": [],
        "temporal_memory_ids": [],
    }
    if not intent_detected:
        return result

    target_entity = str(query_scope.get("entity") or "")
    entity_scoped: list[dict[str, Any]] = []
    for memory in memories:
        memory_entity = _normalize(
            str(memory.get("entity") or memory.get("subject") or "")
        )
        if target_entity and memory_entity != target_entity:
            continue
        entity_scoped.append(memory)
    result["entity_scoped_memory_count"] = len(entity_scoped)

    temporal_rows = [
        memory for memory in entity_scoped if _memory_has_temporal_evidence(memory)
    ]
    result["temporal_record_count"] = len(temporal_rows)
    result["temporal_memory_ids"] = [
        str(memory.get("memory_id") or memory.get("id") or "")
        for memory in temporal_rows
        if memory.get("memory_id") or memory.get("id")
    ][:8]
    if len(temporal_rows) < 2:
        return result

    query_tokens = {
        _light_temporal_binding_stem(token)
        for token in re.findall(r"[a-z0-9]+", query_text)
        if token not in TEMPORAL_COMPARISON_STOPWORDS
    }
    row_overlaps: list[set[str]] = []
    token_row_counts: dict[str, int] = {}
    for memory in temporal_rows:
        memory_tokens = {
            _light_temporal_binding_stem(token)
            for token in re.findall(r"[a-z0-9]+", _memory_binding_text(memory))
            if token not in TEMPORAL_COMPARISON_STOPWORDS
        }
        overlap = query_tokens & memory_tokens
        row_overlaps.append(overlap)
        for token in overlap:
            token_row_counts[token] = token_row_counts.get(token, 0) + 1

    candidate_terms = {
        token
        for token, row_count in token_row_counts.items()
        if row_count < len(temporal_rows)
    }
    bound_rows = [overlap & candidate_terms for overlap in row_overlaps]
    bound_memory_ids = [
        str(memory.get("memory_id") or memory.get("id") or "")
        for memory, binding in zip(temporal_rows, bound_rows)
        if binding and (memory.get("memory_id") or memory.get("id"))
    ]
    bound_rows = [binding for binding in bound_rows if binding]
    result["candidate_terms"] = sorted(candidate_terms)
    result["bound_record_count"] = len(bound_rows)
    result["bound_memory_ids"] = bound_memory_ids[:8]
    result["bound_candidate_count"] = len(
        {token for binding in bound_rows for token in binding}
    )
    result["eligible"] = (
        result["bound_record_count"] >= 2
        and result["bound_candidate_count"] >= 2
    )
    return result


def _light_temporal_binding_stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        stem = token[:-3]
        if len(stem) >= 3 and stem[-1] == stem[-2]:
            stem = stem[:-1]
        return stem
    if len(token) > 4 and token.endswith("ied"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ced"):
        return token[:-1]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ly"):
        return token[:-2]
    return token


def _memory_binding_text(memory: dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            str(part)
            for part in (
                memory.get("claim", ""),
                memory.get("value", ""),
                memory.get("candidate", ""),
                memory.get("name", ""),
            )
            if part
        )
    )


def _memory_has_temporal_evidence(memory: dict[str, Any]) -> bool:
    if any(
        memory.get(key) not in (None, "")
        for key in (
            "date",
            "effective_at",
            "effective_date",
            "end_date",
            "event_at",
            "event_date",
            "event_time",
            "start_date",
        )
    ):
        return True
    text = _normalize(
        " ".join(
            str(part)
            for part in (
                memory.get("claim", ""),
                memory.get("value", ""),
            )
            if part
        )
    )
    number = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    unit = r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|quarters?|semesters?|seasons?|years?)"
    return bool(
        re.search(r"\b(?:19|20)\d{2}(?:-\d{1,2}-\d{1,2})?\b", text)
        or re.search(
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
            text,
        )
        or re.search(
            rf"\b(?:last|next|previous|this|past)\s+{unit}\b",
            text,
        )
        or re.search(rf"\b(?:for\s+)?{number}\s+{unit}(?:\s+ago)?\b", text)
        or re.search(r"\b(?:today|yesterday|tomorrow|tonight)\b", text)
    )


def _versioned_slot_conflict_groups(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _slot_value_group_analysis(memories)["conflict_groups"]


def _slot_value_group_analysis(memories: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        slot = _normalize(str(memory.get("slot") or memory.get("attribute") or ""))
        if not slot:
            continue
        entity = _normalize(str(memory.get("entity") or memory.get("subject") or "user"))
        signature = _memory_value_signature(memory)
        if not signature:
            continue
        grouped.setdefault((entity, slot), []).append(
            {
                "memory_id": str(memory.get("memory_id") or memory.get("id") or ""),
                "value_signature": signature,
                "observed_at": str(memory.get("observed_at") or memory.get("timestamp") or ""),
                "current_status": _normalize(
                    str(memory.get("current_status") or memory.get("validity_status") or "")
                ),
                "declares_set_cardinality": _memory_declares_set_cardinality(memory),
                "has_additive_relation": _memory_has_additive_relation(memory),
                "has_replacement_relation": _memory_has_replacement_relation(memory),
            }
        )
    conflicts: list[dict[str, Any]] = []
    coexisting_set_groups: list[dict[str, Any]] = []
    semantic_equivalent_group_count = 0
    semantic_equivalent_value_collapse_count = 0
    replacement_reactivated_group_count = 0
    for (entity, slot), rows in grouped.items():
        distinct_values = sorted(
            {row["value_signature"] for row in rows if row["value_signature"]}
        )
        semantic_values = _semantic_value_representatives(distinct_values)
        collapse_count = len(distinct_values) - len(semantic_values)
        if collapse_count:
            semantic_equivalent_group_count += 1
            semantic_equivalent_value_collapse_count += collapse_count
        observed_times = sorted({row["observed_at"] for row in rows if row["observed_at"]})
        if len(semantic_values) < 2:
            continue
        set_valued = any(
            row["declares_set_cardinality"] or row["has_additive_relation"]
            for row in rows
        )
        statuses = {row["current_status"] for row in rows if row["current_status"]}
        status_replacement = bool(
            statuses & {"current", "active"}
            and statuses & {"stale", "archive", "expired", "invalid", "revoked"}
        )
        replacement_evidence = status_replacement or any(
            row["has_replacement_relation"] for row in rows
        )
        if set_valued and not replacement_evidence:
            coexisting_set_groups.append(
                {
                    "entity": entity,
                    "slot": slot,
                    "raw_value_count": len(distinct_values),
                    "semantic_value_count": len(semantic_values),
                    "memory_count": len(rows),
                    "memory_ids": [
                        row["memory_id"] for row in rows if row["memory_id"]
                    ][:6],
                }
            )
            continue
        if set_valued and replacement_evidence:
            replacement_reactivated_group_count += 1
        conflicts.append(
            {
                "entity": entity,
                "slot": slot,
                "value_count": len(semantic_values),
                "raw_value_count": len(distinct_values),
                "semantic_value_count": len(semantic_values),
                "memory_count": len(rows),
                "has_temporal_order": len(observed_times) >= 2,
                "set_valued": set_valued,
                "replacement_evidence": replacement_evidence,
                "memory_ids": [row["memory_id"] for row in rows if row["memory_id"]][:6],
            }
        )
    return {
        "conflict_groups": conflicts,
        "coexisting_set_groups": coexisting_set_groups,
        "semantic_equivalent_group_count": semantic_equivalent_group_count,
        "semantic_equivalent_value_collapse_count": (
            semantic_equivalent_value_collapse_count
        ),
        "coexisting_set_group_count": len(coexisting_set_groups),
        "replacement_reactivated_group_count": replacement_reactivated_group_count,
    }


def _memory_value_signature(memory: dict[str, Any]) -> str:
    explicit_value = memory.get("value")
    if explicit_value not in (None, ""):
        if isinstance(explicit_value, (list, tuple, set)):
            values = sorted(
                {
                    re.sub(r"[^a-z0-9]+", " ", _normalize(str(value))).strip()
                    for value in explicit_value
                    if str(value).strip()
                }
            )
            return " || ".join(value for value in values if value)
        signature = _normalize(str(explicit_value))
        return re.sub(r"[^a-z0-9]+", " ", signature).strip()

    raw = str(
        memory.get("claim")
        or memory.get("source_span")
        or memory.get("text")
        or ""
    )
    signature = _normalize(raw)
    signature = re.sub(r"[^a-z0-9]+", " ", signature).strip()
    if len(signature) < 4:
        return ""
    return signature


def _semantic_value_representatives(values: list[str]) -> list[str]:
    representatives: list[str] = []
    for value in values:
        if any(_values_semantically_equivalent(value, other) for other in representatives):
            continue
        representatives.append(value)
    return representatives


def _values_semantically_equivalent(left: str, right: str) -> bool:
    left_normalized = re.sub(r"[^a-z0-9]+", " ", _normalize(left)).strip()
    right_normalized = re.sub(r"[^a-z0-9]+", " ", _normalize(right)).strip()
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    left_tokens = _semantic_value_tokens(left_normalized)
    right_tokens = _semantic_value_tokens(right_normalized)
    if left_tokens and right_tokens and set(left_tokens) == set(right_tokens):
        return True
    if len(left_tokens) == 1 and len(right_tokens) >= 2:
        return left_tokens[0] == _value_acronym(right_tokens)
    if len(right_tokens) == 1 and len(left_tokens) >= 2:
        return right_tokens[0] == _value_acronym(left_tokens)
    return False


def _semantic_value_tokens(value: str) -> list[str]:
    stopwords = {"a", "an", "the", "is", "am", "are", "was", "were", "of", "to"}
    return [
        _light_value_stem(token)
        for token in value.split()
        if token and token not in stopwords
    ]


def _light_value_stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        stem = token[:-3]
        if len(stem) >= 3 and stem[-1] == stem[-2]:
            stem = stem[:-1]
        return stem
    if len(token) > 4 and token.endswith("ied"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ly"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _value_acronym(tokens: list[str]) -> str:
    number_prefix = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }
    return "".join(number_prefix.get(token, token[0]) for token in tokens if token)


def _memory_declares_set_cardinality(memory: dict[str, Any]) -> bool:
    if isinstance(memory.get("value"), (list, tuple, set)):
        return True
    metadata = memory.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    cardinality = _normalize(
        str(
            memory.get("query_slot_cardinality")
            or memory.get("slot_cardinality")
            or memory.get("value_cardinality")
            or memory.get("cardinality")
            or metadata.get("slot_cardinality")
            or metadata.get("value_cardinality")
            or ""
        )
    )
    if cardinality in {"set", "multi", "many", "list", "collection", "multi valued"}:
        return True
    return _metadata_flag(
        memory.get("is_set_valued", metadata.get("is_set_valued"))
    )


def _memory_relation_text(memory: dict[str, Any]) -> str:
    # Cardinality relations must bind to the extracted claim. Broad source
    # spans often concatenate neighboring facts whose additive words do not
    # govern this entity/slot value.
    return _normalize(
        " ".join(
            str(part)
            for part in (
                memory.get("claim", ""),
                memory.get("text", ""),
            )
            if part
        )
    )


def _memory_has_additive_relation(memory: dict[str, Any]) -> bool:
    operation = _normalize(str(memory.get("operation") or memory.get("update_type") or ""))
    if operation in {"add", "added", "append", "appended", "include", "included"}:
        return True
    text = _memory_relation_text(memory)
    return bool(
        re.search(
            r"\b(?:also|as well|in addition|additionally|another|alongside)\b",
            text,
        )
    )


def _memory_has_replacement_relation(memory: dict[str, Any]) -> bool:
    operation = _normalize(str(memory.get("operation") or memory.get("update_type") or ""))
    if operation in {
        "remove",
        "removed",
        "delete",
        "deleted",
        "replace",
        "replaced",
        "revoke",
        "revoked",
    }:
        return True
    text = _memory_relation_text(memory)
    if "not only" in text:
        text = text.replace("not only", "")
    return bool(
        re.search(
            r"\b(?:instead|replaced?|replacement|no longer|removed?|deleted?|"
            r"dropped?|stopped|revoked?|superseded?|only)\b",
            text,
        )
        or re.search(r"\bswitch(?:ed|ing)?\s+from\b", text)
    )


def _memory_source_type(memory: dict[str, Any]) -> str:
    source = memory.get("source")
    if isinstance(source, dict):
        return str(source.get("source_type") or "")
    return str(memory.get("source_type") or "")


def _has_memory_update_language(memories: list[dict[str, Any]]) -> bool:
    update_pattern = re.compile(
        r"\b(now|current|currently|new|updated|changed|moved|relocated|settled|no longer|used to|previously|old)\b"
    )
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        source = memory.get("source")
        source_span = source.get("source_span", "") if isinstance(source, dict) else ""
        text = _normalize(
            " ".join(
                str(part)
                for part in (
                    memory.get("claim", ""),
                    memory.get("value", ""),
                    memory.get("source_span", ""),
                    source_span,
                )
                if part
            )
        )
        if update_pattern.search(text):
            return True
    return False


def _condition_bearing_record_count(memories: list[dict[str, Any]]) -> int:
    count = 0
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        source = memory.get("source")
        source_span = source.get("source_span", "") if isinstance(source, dict) else ""
        text = _normalize(
            " ".join(
                str(part)
                for part in (
                    memory.get("claim", ""),
                    memory.get("value", ""),
                    memory.get("source_span", ""),
                    source_span,
                )
                if part
            )
        )
        if _has_condition_bearing_language(text):
            count += 1
    return count


def _has_condition_bearing_language(text: str) -> bool:
    return bool(
        re.search(r"\b(when|while|during|before|after|if|whenever|unless)\b", text)
        or re.search(
            r"\bon\s+(?:[a-z0-9'-]+\s+){0,3}"
            r"(?:days?|nights?|weekends?|weekdays?|shifts?|sessions?|occasions?)\b",
            text,
        )
        or re.search(
            r"\bin\s+(?:the\s+)?(?:morning|afternoon|evening|night|"
            r"spring|summer|autumn|fall|winter)\b",
            text,
        )
    )


def _has_prefix(cues: list[str], prefix: str) -> bool:
    return any(cue.startswith(prefix) for cue in cues)


def _temporal_comparison_should_apply(
    cues: list[str],
    evidence_risk: dict[str, Any],
) -> bool:
    comparison = evidence_risk.get("temporal_comparison")
    return bool(
        _has_prefix(cues, "temporal_comparison:")
        and isinstance(comparison, dict)
        and comparison.get("eligible")
    )


def _has_conflicting_memory_status(cues: list[str]) -> bool:
    return "memory:current_archive_mix" in cues


def _has_versioned_evidence_conflict(cues: list[str]) -> bool:
    return "memory:slot_value_conflict" in cues or "memory:temporal_versioned_conflict" in cues


def _explicit_replacement_should_apply(
    text: str,
    evidence_risk: dict[str, Any],
) -> bool:
    if _is_explicit_historical_archive_recall(text):
        return False
    if _is_change_detail_query(text):
        return False
    return bool(
        int(evidence_risk.get("conflict_group_count", 0) or 0) > 0
        and int(evidence_risk.get("replacement_reactivated_group_count", 0) or 0) > 0
    )


def _low_risk_recall_should_override_evidence_conflict(text: str, cues: list[str]) -> bool:
    if _is_explicit_validity_change_query(text, cues):
        return False
    return (
        _recent_scope_should_fail_open(text, cues)
        or _is_preference_or_favorite_recall(text)
    )


def _evidence_conflict_should_apply(
    text: str,
    cues: list[str],
    query_metadata: dict[str, Any],
    evidence_risk: dict[str, Any],
) -> bool:
    if int(evidence_risk.get("conflict_group_count", 0) or 0) <= 0:
        return False
    if _is_explicit_validity_change_query(text, cues):
        return True
    if _recommendation_or_advice_should_fail_open(text, cues, evidence_risk):
        return False
    if _recent_scope_should_fail_open(text, cues):
        return False
    if _is_explicit_historical_archive_recall(text):
        return False
    if _is_preference_or_favorite_recall(text):
        return False
    if _metadata_flag(query_metadata.get("needs_current")):
        return True
    if _has_prefix(cues, "current:"):
        return True
    if _is_state_sensitive_action_query(text):
        return _has_ordered_or_status_conflict(evidence_risk)
    if _is_explicit_historical_archive_recall(text):
        return False
    if _has_prefix(cues, "conditional:") and not _has_prefix(cues, "conflict:"):
        return False
    return False


def _change_detail_evidence_should_apply(
    text: str,
    cues: list[str],
    evidence_risk: dict[str, Any],
) -> bool:
    if not _is_change_detail_query(text):
        return False
    if _is_explicit_historical_archive_recall(text):
        return False
    return (
        "memory:update_language" in cues
        or "memory:temporal_versioned_conflict" in cues
        or int(evidence_risk.get("conflict_group_count", 0) or 0) > 0
    )


def _is_change_detail_query(text: str) -> bool:
    return bool(
        re.search(r"\bhow did\b.+\bchange(?:d)?\b", text)
        or re.search(r"\bwhat changed about\b", text)
        or re.search(r"\bwhat change occurred\b", text)
        or re.search(r"\b(did|has|have)\b.+\bchange(?:d)?\b", text)
    )


def _is_explicit_validity_change_query(text: str, cues: list[str]) -> bool:
    if any(
        cue in cues
        for cue in (
            "change:stayed the same",
            "change:stay the same",
            "change:no longer",
        )
    ):
        return True
    if re.search(
        r"\b(previous|previously|before|old|used to)\b.*\b(now|current|currently|latest|new)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(now|current|currently|latest|new)\b.*\b(previous|previously|before|old|used to)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(ago|earlier|before|previously|used to)\b.*\b(compared to|than|versus|vs\.?)\b.*\b(now|current|currently)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(compared to|than|versus|vs\.?)\b.*\b(now|current|currently)\b",
        text,
    ) and re.search(r"\b(ago|earlier|before|previously|used to)\b", text):
        return True
    return False


def _current_cue_should_fail_open(text: str, cues: list[str]) -> bool:
    if not (_has_prefix(cues, "current:") or _has_prefix(cues, "temporal_recent:")):
        return False
    if _is_explicit_validity_change_query(text, cues):
        return False
    if _has_prefix(cues, "conflict:") or _has_conflicting_memory_status(cues) or _has_versioned_evidence_conflict(cues):
        return False
    if _is_recommendation_or_advice_query(text):
        return True
    if _is_preference_or_favorite_recall(text):
        return True
    if _recent_scope_should_fail_open(text, cues):
        return True
    return False


def _current_or_metadata_should_apply(
    text: str,
    cues: list[str],
    query_metadata: dict[str, Any],
    evidence_risk: dict[str, Any],
) -> bool:
    if _is_explicit_validity_change_query(text, cues):
        return True
    if _has_prefix(cues, "conflict:") or _has_conflicting_memory_status(cues):
        return True
    if _has_versioned_evidence_conflict(cues):
        return True
    if int(evidence_risk.get("conflict_group_count", 0) or 0) > 0:
        return True
    if re.search(r"\b(still|anymore|no longer|up to date|valid|invalid|outdated|stale)\b", text):
        return True
    if _is_state_sensitive_action_query(text):
        return True
    metadata_intent = _normalize(
        str(query_metadata.get("query_intent") or query_metadata.get("risk_profile") or "")
    )
    if _metadata_intent_has(metadata_intent, "conflict", "validity"):
        return True
    return False


def _condition_preference_scope_should_apply(
    text: str,
    evidence_risk: dict[str, Any],
) -> bool:
    if not _is_condition_preference_scope_query(text):
        return False
    if _is_explicit_historical_archive_recall(text):
        return False
    return int(evidence_risk.get("condition_bearing_record_count", 0) or 0) > 0


def _is_condition_preference_scope_query(text: str) -> bool:
    preference_action = (
        r"prefer|like|love|use|wear|eat|drink|watch|read|listen(?: to)?|choose|"
        r"pick(?: up)?|have|crave|go for"
    )
    return bool(
        re.search(
            rf"\bunder what conditions?\b.+\b(?:user|i|we|you)\b.+\b(?:{preference_action})\b",
            text,
        )
        or re.search(
            rf"\bwhen (?:does|do|did)\b.+\b(?:user|i|we|you)\b.+\b(?:{preference_action})\b",
            text,
        )
    )


def _is_recommendation_or_advice_query(text: str) -> bool:
    return bool(
        re.search(
            r"\b(suggest|recommend|recommendation|advice|tips|ideas|what should i|what should we|should i|should we|complement)\b",
            text,
        )
    )


def _is_state_sensitive_action_query(text: str) -> bool:
    if _has_current_window_reference(text) or _is_recommendation_or_advice_query(text):
        return True
    if re.search(r"\b(?:remind|recall|remember)\b", text):
        return False
    if re.search(r"\bhow\s+(?:many|much|long|often)\b", text):
        return False
    actor = r"(?:i|we|you|they|he|she|the user)"
    return bool(
        re.search(rf"\b(?:what|which|how)\s+(?:should|could|can)\s+{actor}\b", text)
        or re.search(rf"\b(?:should|could|can|must)\s+{actor}\b", text)
        or re.search(
            rf"\b{actor}\s+(?:should|could|can|must|need to|have to|"
            rf"plan to|planning to|going to|want to)\b",
            text,
        )
        or re.search(
            rf"\b(?:would|will)\s+{actor}\s+be\s+"
            r"(?:safe|valid|allowed|appropriate|ready)\b",
            text,
        )
        or re.search(r"\b(?:please|help me)\b", text)
    )


def _recommendation_or_advice_should_fail_open(
    text: str,
    cues: list[str],
    evidence_risk: dict[str, Any],
) -> bool:
    if not _is_recommendation_or_advice_query(text):
        return False
    if (
        _has_versioned_evidence_conflict(cues)
        and _advice_depends_on_state(text, cues)
        and _has_ordered_or_status_conflict(evidence_risk)
    ):
        return False
    if _has_prefix(cues, "conflict:") or _is_explicit_validity_change_query(text, cues):
        return False
    if re.search(r"\b(valid|invalid|outdated|stale|still true|no longer true)\b", text):
        return False
    return True


def _has_ordered_or_status_conflict(evidence_risk: dict[str, Any]) -> bool:
    statuses = set(evidence_risk.get("status_values", []))
    if statuses & {"current", "active"} and statuses & {
        "stale",
        "archive",
        "expired",
        "invalid",
    }:
        return True
    groups = evidence_risk.get("conflict_groups", [])
    return bool(
        isinstance(groups, list)
        and any(
            isinstance(group, dict) and group.get("has_temporal_order")
            for group in groups
        )
    )


def _advice_depends_on_state(text: str, cues: list[str]) -> bool:
    return bool(
        _has_prefix(cues, "current:")
        or _has_prefix(cues, "change:")
        or _has_prefix(cues, "temporal_recent:")
        or _has_current_window_reference(text)
        or re.search(
            r"\b(?:since|given(?:\s+that)?|because|now that|considering that)\b"
            r".{3,160}\b(?:can|could|would|should|will|recommend|suggest|advise|help)\b",
            text,
        )
        or re.search(
            r"\b(?:just|recently)\s+(?:[a-z]+ed|became|got|started|stopped|left|joined)\b",
            text,
        )
    )


def _is_explicit_historical_archive_recall(text: str) -> bool:
    if re.search(r"\b(now|current|currently|latest|right now|today|still)\b", text):
        return False
    return bool(
        re.search(
            r"\b(previous|previously|before|used to|in the past|earlier|old|former)\b",
            text,
        )
        or re.search(r"\b(where|what|who|when|which)\b.*\b(did|was|were)\b", text)
    )


def _is_preference_or_favorite_recall(text: str) -> bool:
    if re.search(r"\b(still|anymore|no longer|changed|valid|outdated|stale)\b", text):
        return False
    return bool(
        re.search(
            r"\b(favorite|favourite|prefer|preference|love|loving|obsessed|brand of)\b",
            text,
        )
    )


def _recent_scope_should_fail_open(text: str, cues: list[str]) -> bool:
    if _is_explicit_validity_change_query(text, cues):
        return False
    if _has_recent_scope_reference(text) and re.search(
        r"\b(where|what|who|when|which)\b.*\b(did|was|were)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(where|what|who|when|which)\b.*\b(did|was|were)\b.*\b(after|during|from|at)\b",
        text,
    ) and _has_recent_scope_reference(text):
        return True
    return False


def _is_plain_profile_recall(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:what|where|who|which|when|name)\b",
            text,
        )
    )


def _change_scope_gap_should_route_to_sufficiency(
    text: str,
    cues: list[str],
    evidence_risk: dict[str, Any],
) -> bool:
    if not (
        _has_prefix(cues, "change:") or "metadata:timeline_change" in cues
    ):
        return False
    if _is_explicit_historical_archive_recall(text):
        return False
    query_scope = evidence_risk.get("query_scope", {})
    if not isinstance(query_scope, dict) or not query_scope.get("applied"):
        return False
    return int(evidence_risk.get("analyzed_memory_count", 0) or 0) == 0


def _confidence(query_type: str, cues: list[str], should_apply_qvf: bool) -> float:
    if not should_apply_qvf:
        return 0.74 if cues else 0.68
    if query_type in {
        "current_state_or_update",
        "conditional_scope",
        "retrieval_sufficiency",
        "temporal_reasoning",
    }:
        return min(0.95, 0.72 + 0.05 * len(cues))
    return min(0.86, 0.65 + 0.04 * len(cues))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _metadata_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False


def _metadata_intent_has(value: str, *terms: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", _normalize(value))
    for term in terms:
        normalized_term = _normalize(term)
        if re.search(
            rf"\b(?:no|non|without)\s+{re.escape(normalized_term)}\b",
            normalized,
        ):
            continue
        if re.search(rf"\b{re.escape(normalized_term)}\b", normalized):
            return True
    return False


__all__ = [
    "QUERY_RISK_ROUTER_VERSION",
    "EVIDENCE_CONFLICT_ROUTE",
    "RETRIEVAL_SUFFICIENCY_ROUTE",
    "TRANSITION_ROUTE",
    "apply_query_conditioned_cardinality",
    "infer_query_coordinated_slots",
    "is_temporal_comparison_query",
    "partition_query_evidence_qualifiers",
    "route_query_risk",
    "write_query_risk_route",
]
