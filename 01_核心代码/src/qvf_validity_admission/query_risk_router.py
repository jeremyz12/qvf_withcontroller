"""Query-risk router for selective QVF application.

The router is intentionally deterministic and conservative.  It does not
answer a query; it labels whether a retrieved-memory question should use a
direct preserve-first path or a validity-aware QVF routing path.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


QUERY_RISK_ROUTER_VERSION = "qvf_query_risk_router_v0.9"

LOW_RISK_ROUTE = "direct_preserve_first"
CURRENT_ROUTE = "qvf_current_archive_router"
EVIDENCE_CONFLICT_ROUTE = "qvf_evidence_conflict_router"
TRANSITION_ROUTE = "qvf_transition_router"
CONDITIONAL_ROUTE = "qvf_conditional_scope_router"
UNKNOWN_ROUTE = "qvf_abstention_guard"
HYBRID_ROUTE = "qvf_hybrid_router"


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
    "before training",
    "after training",
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
    cues = _cue_matches(text)
    evidence_risk = _memory_validity_analysis(retrieved_memories)
    memory_cues = list(evidence_risk.get("cues", []))
    cues.extend(cue for cue in memory_cues if cue not in cues)

    metadata_needs_current = bool(query_metadata.get("needs_current"))
    metadata_intent = str(query_metadata.get("query_intent") or query_metadata.get("risk_profile") or "")
    if metadata_needs_current:
        cues.append("metadata:needs_current")
    if "conflict" in metadata_intent:
        cues.append("metadata:conflict")
    if "change" in metadata_intent or "timeline" in metadata_intent:
        cues.append("metadata:timeline_change")

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
            cues=sorted(set(cues)),
            reason=reason,
            evidence_risk=evidence_risk,
        )
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
    if _has_prefix(cues, "conflict:") or "metadata:conflict" in cues or _has_conflicting_memory_status(cues):
        return (
            "current_state_or_update",
            CURRENT_ROUTE,
            "high",
            "The query or retrieved memories indicate possible validity conflict.",
        )
    if _has_versioned_evidence_conflict(cues) and _low_risk_recall_should_override_evidence_conflict(text, cues):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Retrieved evidence has versioned values, but the query is preference, generic accessory, or recent-event recall rather than a validity decision.",
        )
    if _recommendation_or_advice_should_fail_open(text, cues):
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
    if _current_cue_should_fail_open(text, cues):
        return (
            "ordinary_recall",
            LOW_RISK_ROUTE,
            "low",
            "Current/recent wording appears in recommendation, preference, or event recall without explicit validity conflict.",
        )
    if _has_prefix(cues, "current:") or bool(query_metadata.get("needs_current")):
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
        if _recent_scope_should_fail_open(text, cues):
            return (
                "ordinary_recall",
                LOW_RISK_ROUTE,
                "low",
                "Recent scoped wording describes an event recall, not a current-validity decision.",
            )
        return (
            "temporal_reasoning",
            HYBRID_ROUTE,
            "medium",
            "The query contains a recent scoped window where selected-history or validity routing may help.",
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
    out.extend(f"current:{cue}" for cue in CURRENT_CUES if cue in text)
    out.extend(f"change:{cue}" for cue in CHANGE_CUES if cue in text)
    out.extend(_recent_scope_cue_matches(text))
    out.extend(f"temporal:{cue}" for cue in TEMPORAL_CUES if cue in text)
    out.extend(f"conditional:{cue}" for cue in CONDITIONAL_CUES if cue in text)
    out.extend(f"conflict:{cue}" for cue in CONFLICT_CUES if cue in text)
    out.extend(f"unknown:{cue}" for cue in UNKNOWN_CUES if cue in text)
    out.extend(f"multi_session:{cue}" for cue in MULTI_SESSION_CUES if cue in text)
    if re.search(r"\b(did|has|have)\b.+\b(change|changed|stay|stayed)\b", text):
        out.append("change:did_has_change_pattern")
    return out


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


def _memory_validity_cues(memories: list[dict[str, Any]]) -> list[str]:
    """Backward-compatible cue-only wrapper for callers/tests that inspect internals."""

    return list(_memory_validity_analysis(memories).get("cues", []))


def _memory_validity_analysis(memories: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = {
        _normalize(str(memory.get("current_status") or memory.get("validity_status") or ""))
        for memory in memories
        if isinstance(memory, dict)
    }
    roles = {
        _normalize(str(memory.get("retrieval_role") or _memory_source_type(memory) or ""))
        for memory in memories
        if isinstance(memory, dict)
    }
    out: list[str] = []
    if any(status in {"current", "active"} for status in statuses) and any(
        status in {"stale", "archive", "expired", "invalid"} for status in statuses
    ):
        out.append("memory:current_archive_mix")
    if any("stale" in role or "archive" in role for role in roles):
        out.append("memory:archive_or_stale_role")
    conflict_groups = _versioned_slot_conflict_groups(memories)
    if conflict_groups:
        out.append("memory:slot_value_conflict")
    if any(group.get("has_temporal_order") for group in conflict_groups):
        out.append("memory:temporal_versioned_conflict")
    if _has_memory_update_language(memories):
        out.append("memory:update_language")
    condition_bearing_record_count = _condition_bearing_record_count(memories)
    if condition_bearing_record_count:
        out.append("memory:condition_bearing_evidence")
    return {
        "memory_count": len([memory for memory in memories if isinstance(memory, dict)]),
        "cues": sorted(set(out)),
        "status_values": sorted(status for status in statuses if status),
        "role_values": sorted(role for role in roles if role),
        "conflict_group_count": len(conflict_groups),
        "conflict_groups": conflict_groups[:5],
        "condition_bearing_record_count": condition_bearing_record_count,
    }


def _versioned_slot_conflict_groups(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
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
            }
        )
    conflicts: list[dict[str, Any]] = []
    for (entity, slot), rows in grouped.items():
        distinct_values = sorted({row["value_signature"] for row in rows if row["value_signature"]})
        observed_times = sorted({row["observed_at"] for row in rows if row["observed_at"]})
        if len(distinct_values) < 2:
            continue
        conflicts.append(
            {
                "entity": entity,
                "slot": slot,
                "value_count": len(distinct_values),
                "memory_count": len(rows),
                "has_temporal_order": len(observed_times) >= 2,
                "memory_ids": [row["memory_id"] for row in rows if row["memory_id"]][:6],
            }
        )
    return conflicts


def _memory_value_signature(memory: dict[str, Any]) -> str:
    raw = str(
        memory.get("value")
        or memory.get("claim")
        or memory.get("source_span")
        or memory.get("text")
        or ""
    )
    signature = _normalize(raw)
    signature = re.sub(r"[^a-z0-9]+", " ", signature).strip()
    if len(signature) < 4:
        return ""
    return signature


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
        or re.search(r"\bon\s+(?:hot|cold|training|workout|weekend|school|heavy|rest)\b", text)
        or re.search(r"\bin\s+(?:summer|winter|spring|fall|autumn|the morning|the afternoon|the evening)\b", text)
    )


def _has_prefix(cues: list[str], prefix: str) -> bool:
    return any(cue.startswith(prefix) for cue in cues)


def _has_conflicting_memory_status(cues: list[str]) -> bool:
    return "memory:current_archive_mix" in cues


def _has_versioned_evidence_conflict(cues: list[str]) -> bool:
    return "memory:slot_value_conflict" in cues or "memory:temporal_versioned_conflict" in cues


def _low_risk_recall_should_override_evidence_conflict(text: str, cues: list[str]) -> bool:
    if _is_explicit_validity_change_query(text, cues):
        return False
    return (
        _recent_scope_should_fail_open(text, cues)
        or _is_preference_or_favorite_recall(text)
        or _is_generic_accessory_recommendation(text)
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
    if _recommendation_or_advice_should_fail_open(text, cues):
        return False
    if _recent_scope_should_fail_open(text, cues):
        return False
    if _is_explicit_historical_archive_recall(text):
        return False
    if _is_preference_or_favorite_recall(text):
        return False
    if _is_generic_accessory_recommendation(text):
        return False
    if bool(query_metadata.get("needs_current")):
        return True
    if _has_prefix(cues, "current:"):
        return True
    if _is_state_sensitive_action_query(text):
        return True
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
    if re.search(r"\b(still|anymore|no longer|latest|up to date|valid|invalid|outdated|stale)\b", text):
        return True
    if _is_state_sensitive_action_query(text):
        return True
    metadata_intent = _normalize(
        str(query_metadata.get("query_intent") or query_metadata.get("risk_profile") or "")
    )
    if "conflict" in metadata_intent or "validity" in metadata_intent:
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
    return bool(
        _has_current_window_reference(text)
        or re.search(
            r"\b("
            r"set up|sign up|notify|update my address|get established|"
            r"nearby|in the area|good spots|places to go|options nearby|"
            r"local sights|itinerary|just moved|settling into|settled into|"
            r"check in schedule|daily check in|adjustments should|good plan|"
            r"make sure|prepare before|will it be|will they be|safe to|"
            r"protect|prevent"
            r")\b",
            text,
        )
    )


def _recommendation_or_advice_should_fail_open(text: str, cues: list[str]) -> bool:
    if not _is_recommendation_or_advice_query(text):
        return False
    if _has_prefix(cues, "conflict:") or _is_explicit_validity_change_query(text, cues):
        return False
    if re.search(r"\b(valid|invalid|outdated|stale|still true|no longer true)\b", text):
        return False
    state_scoped_context = re.search(
        r"\b(since|given that|because)\b.{0,100}\b("
        r"live|lived|living|based|residing|moved|relocated|current|currently"
        r")\b",
        text,
    )
    state_scoped_action = re.search(
        r"\b(set up|sign up|nearby|in the area|local services|utilities|internet providers)\b",
        text,
    ) or _has_current_window_reference(text)
    if state_scoped_context and state_scoped_action:
        return False
    if re.search(r"\b(just moved|settling into|settled into)\b", text) and re.search(
        r"\b(recommend|nearby|in the area|good spots|places to go|local sights|itinerary)\b",
        text,
    ):
        return False
    return True


def _is_generic_accessory_recommendation(text: str) -> bool:
    if not _is_recommendation_or_advice_query(text):
        return False
    return bool(
        re.search(
            r"\b(accessory|accessories|complement(?: my| the)? .*setup|phone accessory|phone accessories)\b",
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
    if re.search(
        r"\b(where|what|who|when|which)\b.*\b(did|was|were)\b.*\b(after|during|from|at)\b",
        text,
    ) and _has_recent_scope_reference(text):
        return True
    if re.search(
        r"\b(where|what|who|when|which)\b.*\b(move|moved|relocation|relocated)\b.*\b(after|recent|recently)\b",
        text,
    ):
        return True
    return False


def _is_plain_profile_recall(text: str) -> bool:
    return bool(
        re.search(
            r"\b(what|where|who|which|name|degree|commute|favorite|favourite|prefer|like|work|live|graduated)\b",
            text,
        )
    )


def _confidence(query_type: str, cues: list[str], should_apply_qvf: bool) -> float:
    if not should_apply_qvf:
        return 0.74 if cues else 0.68
    if query_type in {"current_state_or_update", "conditional_scope", "temporal_reasoning"}:
        return min(0.95, 0.72 + 0.05 * len(cues))
    return min(0.86, 0.65 + 0.04 * len(cues))


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


__all__ = [
    "QUERY_RISK_ROUTER_VERSION",
    "EVIDENCE_CONFLICT_ROUTE",
    "TRANSITION_ROUTE",
    "route_query_risk",
    "write_query_risk_route",
]
