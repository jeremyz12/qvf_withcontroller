"""Public memory-validity controller facade for QVF.

This module keeps the integration surface small: callers provide retrieved
memory records, optional update events, and query requests, then receive a
controller summary plus safe model-facing sidecar payloads.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .decisions import (
    assert_model_facing_payload_is_clean,
    model_facing_forbidden_key_paths,
)
from .pipeline import run_qvf_service_request
from .query_risk_router import LOW_RISK_ROUTE, route_query_risk

CONTROLLER_FACADE_VERSION = "qvf_memory_validity_controller_facade_v0.1"
SELECTIVE_CONTROLLER_FACADE_VERSION = "qvf_selective_memory_validity_controller_v0.1"
RETRIEVAL_REPAIR_LOOP_VERSION = "qvf_bounded_retrieval_repair_loop_v0.1"
SELECTIVE_RETRIEVAL_REPAIR_LOOP_VERSION = (
    "qvf_selective_bounded_retrieval_repair_loop_v0.1"
)
MAX_RETRIEVAL_REPAIR_ATTEMPTS = 3


def run_memory_validity_controller(
    request: dict[str, Any],
    *,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    """Run QVF as a read-time memory-validity controller.

    The returned object is safe for application integration: it includes
    controller decisions, safe model-facing sidecars, and a compact summary.
    It does not call a target LLM or judge model.
    """

    response = run_qvf_service_request(request)
    sidecars = _attach_raw_memory_fallback_contexts(
        response.get("model_facing_sidecar_payloads", []),
        request,
    )
    for sidecar in sidecars:
        assert_model_facing_payload_is_clean(sidecar)
    controller_decisions = extract_validity_controller_decisions(response)
    output = {
        "controller_facade_version": CONTROLLER_FACADE_VERSION,
        "request_id": response.get("request_id", request.get("request_id", "")),
        "decision": response.get("decision", ""),
        "api_calls_made": response.get("api_calls_made", 0),
        "controller_decisions": controller_decisions,
        "model_facing_sidecar_payloads": sidecars,
        "summary": {
            "query_count": len(controller_decisions),
            "next_action_counts": _next_action_counts(controller_decisions),
            "raw_memory_preservation": _raw_memory_preservation_summary(
                request,
                sidecars,
            ),
            "model_facing_payload_forbidden_key_count": sum(
                len(model_facing_forbidden_key_paths(sidecar)) for sidecar in sidecars
            ),
        },
    }
    if include_raw_response:
        output["raw_qvf_response"] = response
    return output


def run_selective_memory_validity_controller(
    request: dict[str, Any],
    *,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    """Route each post-retrieval query before deciding whether to run QVF."""

    query_rows = _controller_query_rows(request)
    if not query_rows:
        raise ValueError("request must contain at least one query request")
    retrieved_memories = _raw_memory_fallback_rows(request)
    routed_queries: list[dict[str, Any]] = []
    qvf_query_ids: set[str] = set()
    for field_name, query in query_rows:
        query_id = _controller_query_id(query)
        route = route_query_risk(
            _controller_question(query),
            query_metadata=query,
            retrieved_memories=retrieved_memories,
        )
        routed_queries.append(
            {
                "query_id": query_id,
                "query_field": field_name,
                "route": route,
                "query": query,
            }
        )
        if route["should_apply_qvf"]:
            qvf_query_ids.add(query_id)

    qvf_output: dict[str, Any] = {}
    if qvf_query_ids:
        qvf_request = _request_with_selected_queries(request, qvf_query_ids)
        qvf_output = run_memory_validity_controller(
            qvf_request,
            include_raw_response=include_raw_response,
        )

    qvf_decisions = {
        str(decision.get("query_id") or ""): decision
        for decision in qvf_output.get("controller_decisions", [])
        if isinstance(decision, dict)
    }
    direct_sidecars: list[dict[str, Any]] = []
    controller_decisions: list[dict[str, Any]] = []
    query_risk_routes: list[dict[str, Any]] = []
    for routed in routed_queries:
        query_id = routed["query_id"]
        query = routed["query"]
        route = routed["route"]
        query_risk_routes.append({"query_id": query_id, **route})
        if route["should_apply_qvf"]:
            if query_id in qvf_decisions:
                controller_decisions.append(qvf_decisions[query_id])
            continue
        direct_sidecar = _direct_preserve_sidecar(
            query_id=query_id,
            question=_controller_question(query),
            route=route,
            raw_rows=retrieved_memories,
        )
        assert_model_facing_payload_is_clean(direct_sidecar)
        direct_sidecars.append(direct_sidecar)
        controller_decisions.append(_direct_preserve_decision(query, route))

    qvf_sidecars = list(qvf_output.get("model_facing_sidecar_payloads", []))
    sidecars = [*direct_sidecars, *qvf_sidecars]
    for sidecar in sidecars:
        assert_model_facing_payload_is_clean(sidecar)
    direct_query_count = len(routed_queries) - len(qvf_query_ids)
    output = {
        "selective_controller_version": SELECTIVE_CONTROLLER_FACADE_VERSION,
        "request_id": str(request.get("request_id") or ""),
        "decision": (
            "GO_SELECTIVE_QVF_CONTROLLER_NO_API"
            if qvf_query_ids
            else "GO_SELECTIVE_DIRECT_BYPASS_NO_API"
        ),
        "api_calls_made": int(qvf_output.get("api_calls_made", 0) or 0),
        "qvf_controller_executed": bool(qvf_query_ids),
        "query_risk_routes": query_risk_routes,
        "controller_decisions": controller_decisions,
        "model_facing_sidecar_payloads": sidecars,
        "summary": {
            "query_count": len(routed_queries),
            "direct_query_count": direct_query_count,
            "qvf_query_count": len(qvf_query_ids),
            "qvf_call_rate": len(qvf_query_ids) / len(routed_queries),
            "next_action_counts": _next_action_counts(controller_decisions),
            "raw_memory_preservation": _raw_memory_preservation_summary(
                request,
                sidecars,
            ),
            "model_facing_payload_forbidden_key_count": sum(
                len(model_facing_forbidden_key_paths(sidecar)) for sidecar in sidecars
            ),
            "execution_boundary": (
                "route after initial retrieval; direct queries bypass QVF, while only "
                "validity-risk queries enter the QVF controller"
            ),
        },
    }
    if include_raw_response and qvf_output:
        output["qvf_controller_output"] = qvf_output
    return output


def run_memory_validity_controller_with_retrieval_repair(
    request: dict[str, Any],
    *,
    retriever: Callable[[dict[str, Any]], Any],
    max_repair_attempts: int = 1,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    """Run QVF and execute a bounded external retrieval repair when requested.

    The callback remains the retrieval system. QVF only emits the query rewrite
    and scope, admits newly returned rows into a temporary request copy, and
    reruns the read-time controller. No long-term memory write occurs here.
    """

    return _run_controller_with_retrieval_repair(
        request,
        retriever=retriever,
        controller_runner=run_memory_validity_controller,
        repair_loop_version=RETRIEVAL_REPAIR_LOOP_VERSION,
        max_repair_attempts=max_repair_attempts,
        include_raw_response=include_raw_response,
    )


def run_selective_memory_validity_controller_with_retrieval_repair(
    request: dict[str, Any],
    *,
    retriever: Callable[[dict[str, Any]], Any],
    max_repair_attempts: int = 1,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    """Run route-first QVF and execute its bounded retrieval repair requests."""

    return _run_controller_with_retrieval_repair(
        request,
        retriever=retriever,
        controller_runner=run_selective_memory_validity_controller,
        repair_loop_version=SELECTIVE_RETRIEVAL_REPAIR_LOOP_VERSION,
        max_repair_attempts=max_repair_attempts,
        include_raw_response=include_raw_response,
    )


def _run_controller_with_retrieval_repair(
    request: dict[str, Any],
    *,
    retriever: Callable[[dict[str, Any]], Any],
    controller_runner: Callable[..., dict[str, Any]],
    repair_loop_version: str,
    max_repair_attempts: int,
    include_raw_response: bool,
) -> dict[str, Any]:
    if not callable(retriever):
        raise TypeError("retriever must be callable")
    if isinstance(max_repair_attempts, bool) or not isinstance(max_repair_attempts, int):
        raise TypeError("max_repair_attempts must be an integer")
    if not 0 <= max_repair_attempts <= MAX_RETRIEVAL_REPAIR_ATTEMPTS:
        raise ValueError(
            "max_repair_attempts must be between 0 and "
            f"{MAX_RETRIEVAL_REPAIR_ATTEMPTS}"
        )

    working_request = deepcopy(request)
    result = controller_runner(
        working_request,
        include_raw_response=include_raw_response,
    )
    initial_decisions = deepcopy(result.get("controller_decisions", []))
    initial_repairs = _retrieval_repair_requests(initial_decisions)
    attempt_trace: list[dict[str, Any]] = []
    retriever_invocations = 0
    stop_reason = "not_needed" if not initial_repairs else "max_attempts_reached"

    for attempt_index in range(1, max_repair_attempts + 1):
        repair_requests = _retrieval_repair_requests(
            result.get("controller_decisions", [])
        )
        if not repair_requests:
            stop_reason = "resolved" if initial_repairs else "not_needed"
            break

        attempt_rows: list[dict[str, Any]] = []
        accepted_count = 0
        retriever_failed = False
        for repair_request in repair_requests:
            retriever_invocations += 1
            try:
                retriever_result = retriever(deepcopy(repair_request))
                additions = _normalize_retriever_result(retriever_result)
                merge = _merge_retrieval_additions(working_request, additions)
            except Exception as exc:  # fail closed and keep the initial validity boundary
                attempt_rows.append(
                    {
                        "query_id": repair_request["query_id"],
                        "next_action": repair_request["next_action"],
                        "status": "retriever_error",
                        "error_type": type(exc).__name__,
                    }
                )
                retriever_failed = True
                stop_reason = "retriever_error"
                break

            accepted_count += merge["accepted_count"]
            attempt_rows.append(
                {
                    "query_id": repair_request["query_id"],
                    "next_action": repair_request["next_action"],
                    "query_rewrite": repair_request["query_rewrite"],
                    "suggested_retrieval_scope": repair_request[
                        "suggested_retrieval_scope"
                    ],
                    "status": (
                        "new_evidence_accepted"
                        if merge["accepted_count"]
                        else "no_new_evidence"
                    ),
                    **merge,
                }
            )

        attempt_trace.append(
            {
                "attempt": attempt_index,
                "repair_request_count": len(repair_requests),
                "accepted_evidence_count": accepted_count,
                "queries": attempt_rows,
            }
        )
        if retriever_failed:
            break
        if accepted_count == 0:
            stop_reason = "no_new_evidence"
            break

        result = controller_runner(
            working_request,
            include_raw_response=include_raw_response,
        )
        if not _retrieval_repair_requests(result.get("controller_decisions", [])):
            stop_reason = "resolved"
            break

    final_decisions = result.get("controller_decisions", [])
    remaining_repairs = _retrieval_repair_requests(final_decisions)
    repair_loop = {
        "repair_loop_version": repair_loop_version,
        "boundary": (
            "QVF requests a bounded retry from an external retriever; it does not "
            "replace retrieval, write long-term memory, or treat feedback as evidence."
        ),
        "max_repair_attempts": max_repair_attempts,
        "attempts_executed": len(attempt_trace),
        "retriever_invocations": retriever_invocations,
        "external_call_accounting": "owned_by_retriever_callback",
        "initial_repair_request_count": len(initial_repairs),
        "remaining_repair_request_count": len(remaining_repairs),
        "resolved": not remaining_repairs,
        "stop_reason": stop_reason,
        "initial_controller_decisions": initial_decisions,
        "final_controller_decisions": deepcopy(final_decisions),
        "attempt_trace": attempt_trace,
    }
    output = dict(result)
    output["retrieval_repair_loop"] = repair_loop
    output["summary"] = {
        **dict(result.get("summary", {})),
        "retrieval_repair": {
            "attempts_executed": len(attempt_trace),
            "retriever_invocations": retriever_invocations,
            "resolved": not remaining_repairs,
            "stop_reason": stop_reason,
        },
    }
    return output


def _retrieval_repair_requests(decisions: Any) -> list[dict[str, Any]]:
    if not isinstance(decisions, list):
        return []
    requests: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        next_action = str(decision.get("next_action") or "")
        if not (
            next_action.startswith("retrieve_")
            or next_action == "query_rewrite_and_retrieve"
        ):
            continue
        query_id = str(decision.get("query_id") or "")
        query_rewrite = str(decision.get("query_rewrite") or "")
        key = (query_id, next_action, query_rewrite)
        if key in seen:
            continue
        seen.add(key)
        scope = decision.get("suggested_retrieval_scope", {})
        requests.append(
            {
                "query_id": query_id,
                "query": str(decision.get("query") or ""),
                "entity": str(decision.get("entity") or ""),
                "slot": str(decision.get("slot") or ""),
                "query_intent": str(decision.get("query_intent") or ""),
                "answerability_state": str(
                    decision.get("answerability_state") or ""
                ),
                "answerability_boundary": deepcopy(
                    decision.get("answerability_boundary", {})
                )
                if isinstance(decision.get("answerability_boundary"), dict)
                else {},
                "next_action": next_action,
                "query_rewrite": query_rewrite,
                "suggested_retrieval_scope": dict(scope)
                if isinstance(scope, dict)
                else {},
                "must_not_use_as_current_ids": list(
                    decision.get("blocked_as_current_ids", [])
                )
                if isinstance(decision.get("blocked_as_current_ids"), list)
                else [],
            }
        )
    return requests


def _controller_query_rows(
    request: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for field_name in ("query_requests", "queries"):
        value = request.get(field_name, [])
        if value in (None, []):
            continue
        if not isinstance(value, list):
            raise TypeError(f"request.{field_name} must be a list")
        for query in value:
            if not isinstance(query, dict):
                raise TypeError(f"request.{field_name} rows must be mappings")
            query_id = _controller_query_id(query)
            if not query_id:
                raise ValueError(f"request.{field_name} query id is required")
            if query_id in seen_ids:
                raise ValueError(f"duplicate query id: {query_id}")
            seen_ids.add(query_id)
            rows.append((field_name, query))
    return rows


def _controller_query_id(query: dict[str, Any]) -> str:
    return str(query.get("request_id") or query.get("query_id") or "").strip()


def _controller_question(query: dict[str, Any]) -> str:
    return str(
        query.get("question") or query.get("text") or query.get("query") or ""
    ).strip()


def _request_with_selected_queries(
    request: dict[str, Any],
    query_ids: set[str],
) -> dict[str, Any]:
    selected = deepcopy(request)
    for field_name in ("query_requests", "queries"):
        value = selected.get(field_name)
        if isinstance(value, list):
            selected[field_name] = [
                row
                for row in value
                if isinstance(row, dict) and _controller_query_id(row) in query_ids
            ]
    return selected


def _direct_preserve_sidecar(
    *,
    query_id: str,
    question: str,
    route: dict[str, Any],
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "context_type": LOW_RISK_ROUTE,
        "query_id": query_id,
        "latest_query": question,
        "query_risk_route": route,
        "raw_memory_context": deepcopy(raw_rows),
        "direct_preservation_policy": {
            "mode": "preserve_post_retrieval_raw_memory",
            "reason": (
                "The router found no validity, freshness, conflict, condition-scope, "
                "or evidence-sufficiency risk requiring QVF control."
            ),
        },
    }


def _direct_preserve_decision(
    query: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query_id": _controller_query_id(query),
        "query": _controller_question(query),
        "entity": str(query.get("entity") or ""),
        "slot": str(query.get("slot") or ""),
        "query_intent": str(query.get("query_intent") or "ordinary_recall"),
        "read_decision": "DIRECT_PRESERVE",
        "answer_policy": "answer_from_raw_memory",
        "route": LOW_RISK_ROUTE,
        "evidence_sufficiency": "validity_control_not_required",
        "next_action": "answer_from_raw_memory",
        "blocked_as_current_ids": [],
        "allowed_as_history_ids": [],
        "suggested_retrieval_scope": {},
        "query_rewrite": "",
        "reason": str(route.get("reason") or ""),
    }


def _normalize_retriever_result(value: Any) -> dict[str, list[dict[str, Any]]]:
    if value is None:
        return {"records": [], "events": []}
    if isinstance(value, list):
        records = value
        events: list[Any] = []
    elif isinstance(value, dict):
        if "records" in value or "events" in value:
            records = value.get("records", [])
            events = value.get("events", [])
        elif value.get("event_id"):
            records = []
            events = [value]
        elif value.get("memory_id"):
            records = [value]
            events = []
        else:
            raise ValueError("retriever result must contain records, events, or a memory row")
    else:
        raise TypeError("retriever result must be a mapping, list, or None")
    if not isinstance(records, list) or not isinstance(events, list):
        raise TypeError("retriever records and events must be lists")
    if not all(isinstance(row, dict) for row in [*records, *events]):
        raise TypeError("retriever rows must be mappings")
    return {
        "records": [deepcopy(row) for row in records],
        "events": [deepcopy(row) for row in events],
    }


def _merge_retrieval_additions(
    request: dict[str, Any],
    additions: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    accepted_ids: list[str] = []
    duplicate_ids: list[str] = []
    invalid_row_count = 0
    for field_name, identity_key in (("records", "memory_id"), ("events", "event_id")):
        existing = request.setdefault(field_name, [])
        if not isinstance(existing, list):
            raise TypeError(f"request.{field_name} must be a list")
        known_ids = {
            str(row.get(identity_key) or "").strip()
            for row in existing
            if isinstance(row, dict) and str(row.get(identity_key) or "").strip()
        }
        for row in additions.get(field_name, []):
            row_id = str(row.get(identity_key) or "").strip()
            if not row_id:
                invalid_row_count += 1
                continue
            if row_id in known_ids:
                duplicate_ids.append(row_id)
                continue
            existing.append(deepcopy(row))
            known_ids.add(row_id)
            accepted_ids.append(row_id)
    return {
        "accepted_count": len(accepted_ids),
        "accepted_ids": accepted_ids,
        "duplicate_ids": duplicate_ids,
        "invalid_row_count": invalid_row_count,
    }


def extract_validity_controller_decisions(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract compact controller decisions from a QVF service response."""

    query_results = (
        response.get("step_report", {})
        .get("query_report", {})
        .get("query_results", [])
    )
    decisions: list[dict[str, Any]] = []
    for result in query_results:
        if not isinstance(result, dict):
            continue
        packet = result.get("packet", {})
        query = packet.get("query", {}) if isinstance(packet, dict) else {}
        read_decision = result.get("read_decision", {})
        if not isinstance(read_decision, dict):
            read_decision = {}
        controller_decision = read_decision.get("validity_controller_decision", {})
        if not isinstance(controller_decision, dict):
            controller_decision = {}
        decisions.append(
            {
                "query_id": result.get("query_id", read_decision.get("query_id", "")),
                "query": query.get("text", query.get("query", "")),
                "entity": query.get("entity", ""),
                "slot": query.get("slot", ""),
                "query_intent": query.get("query_intent", ""),
                "read_decision": read_decision.get("decision", ""),
                "answer_policy": read_decision.get("answer_policy", ""),
                "route": read_decision.get("route", ""),
                "evidence_sufficiency": controller_decision.get(
                    "evidence_sufficiency",
                    "",
                ),
                "answerability_state": controller_decision.get(
                    "answerability_state",
                    "",
                ),
                "answerability_boundary": controller_decision.get(
                    "answerability_boundary",
                    {},
                ),
                "next_action": controller_decision.get("next_action", ""),
                "blocked_as_current_ids": controller_decision.get(
                    "blocked_as_current_ids",
                    [],
                ),
                "allowed_as_history_ids": controller_decision.get(
                    "allowed_as_history_ids",
                    [],
                ),
                "suggested_retrieval_scope": controller_decision.get(
                    "suggested_retrieval_scope",
                    {},
                ),
                "query_rewrite": controller_decision.get("query_rewrite", ""),
                "reason": controller_decision.get("reason", ""),
            }
        )
    return decisions


def _next_action_counts(controller_decisions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in controller_decisions:
        action = str(decision.get("next_action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def _attach_raw_memory_fallback_contexts(
    sidecars: Any,
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(sidecars, list):
        return []
    raw_rows = _raw_memory_fallback_rows(request)
    out: list[dict[str, Any]] = []
    for sidecar in sidecars:
        if not isinstance(sidecar, dict):
            continue
        enriched = dict(sidecar)
        enriched["raw_memory_fallback_context"] = raw_rows
        enriched["raw_memory_fallback_policy"] = {
            "mode": "preserve_all_request_records",
            "current_state": (
                "Use QVF current/stale labels for current-state answers; do not use "
                "raw fallback rows as current facts when blocked_as_current_ids marks them unsafe."
            ),
            "historical_recall": (
                "Raw fallback rows remain usable for ordinary history, archive, "
                "prior-state, and exact-detail recall when directly relevant."
            ),
        }
        out.append(enriched)
    return out


def _raw_memory_fallback_rows(request: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        source = record.get("source", {})
        if not isinstance(source, dict):
            source = {}
        row = {
            "memory_id": record.get("memory_id", ""),
            "entity": record.get("entity", ""),
            "slot": record.get("slot", ""),
            "claim": record.get("claim", ""),
            "value": record.get("value", ""),
            "observed_at": record.get("observed_at", ""),
            "valid_until": record.get("valid_until"),
            "condition": record.get("condition"),
            "source_type": source.get("source_type", ""),
            "source_span": source.get("source_span", ""),
        }
        rows.append({key: value for key, value in row.items() if value not in (None, "")})
    for event in request.get("events", []):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id", "")).strip()
        row = {
            "memory_id": event.get("memory_id", event_id),
            "entity": event.get("entity", ""),
            "slot": event.get("slot", ""),
            "claim": event.get("claim", event.get("text", "")),
            "value": event.get("value", ""),
            "observed_at": event.get("observed_at", ""),
            "valid_until": event.get("valid_until"),
            "condition": event.get("condition"),
            "source_type": event.get("source_type", "memory_event"),
            "source_span": event.get("source_span", event.get("text", "")),
        }
        rows.append({key: value for key, value in row.items() if value not in (None, "")})
    return rows


def _raw_memory_preservation_summary(
    request: dict[str, Any],
    sidecars: list[dict[str, Any]],
) -> dict[str, Any]:
    input_ids = {
        str(record.get("memory_id", "")).strip()
        for record in request.get("records", [])
        if isinstance(record, dict) and str(record.get("memory_id", "")).strip()
    }
    input_ids.update(
        str(event.get("memory_id", event.get("event_id", ""))).strip()
        for event in request.get("events", [])
        if isinstance(event, dict)
        and str(event.get("memory_id", event.get("event_id", ""))).strip()
    )
    visible_ids: set[str] = set()
    for sidecar in sidecars:
        visible_ids.update(_collect_memory_ids(sidecar))
    preserved_ids = sorted(input_ids & visible_ids)
    missing_ids = sorted(input_ids - visible_ids)
    return {
        "input_record_count": len(input_ids),
        "preserved_record_count": len(preserved_ids),
        "missing_record_count": len(missing_ids),
        "preservation_rate": (
            len(preserved_ids) / len(input_ids) if input_ids else 1.0
        ),
        "missing_memory_ids": missing_ids,
    }


def _collect_memory_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        memory_id = value.get("memory_id")
        if isinstance(memory_id, str) and memory_id.strip():
            ids.add(memory_id.strip())
        for child in value.values():
            ids.update(_collect_memory_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(_collect_memory_ids(child))
    return ids


__all__ = [
    "CONTROLLER_FACADE_VERSION",
    "MAX_RETRIEVAL_REPAIR_ATTEMPTS",
    "RETRIEVAL_REPAIR_LOOP_VERSION",
    "SELECTIVE_RETRIEVAL_REPAIR_LOOP_VERSION",
    "SELECTIVE_CONTROLLER_FACADE_VERSION",
    "extract_validity_controller_decisions",
    "run_memory_validity_controller",
    "run_memory_validity_controller_with_retrieval_repair",
    "run_selective_memory_validity_controller",
    "run_selective_memory_validity_controller_with_retrieval_repair",
]
