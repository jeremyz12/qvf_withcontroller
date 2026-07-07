"""No-API held-out integration evaluation for the QVF validity-admission service.

The cases here are intentionally small, synthetic lifecycle scenarios rather
than STALE400 prompt variants. They exercise the plug-in surface an external
memory system would call: write records/events, retrieve a compact validity
packet, route a read-time decision, and render a structured response.
"""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .service import run_qvf_service_request


def _memory(
    memory_id: str,
    entity: str,
    slot: str,
    value: str,
    observed_at: str,
    *,
    source_confidence: float = 0.9,
    valid_until: str | None = None,
    condition: str | None = None,
    source_type: str = "synthetic_heldout",
    source_id: str | None = None,
    namespace: str = "",
    tenant_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "entity": entity,
        "slot": slot,
        "claim": f"{entity} {slot} is {value}.",
        "value": value,
        "source": {
            "source_id": source_id or f"source_{memory_id}",
            "source_type": source_type,
        },
        "observed_at": observed_at,
        "valid_from": observed_at,
        "valid_until": valid_until,
        "condition": condition,
        "scope": {
            "namespace": namespace,
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
        "source_confidence": source_confidence,
    }


def build_heldout_integration_requests() -> list[dict[str, Any]]:
    """Build deterministic no-API service requests and expected outcomes."""

    return [
        {
            "case_id": "heldout_supersede_stale_premise",
            "capability": "newer conflicting event supersedes stale premise",
            "service_request": {
                "request_id": "svc_heldout_supersede_stale_premise",
                "step_id": "step_heldout_supersede_stale_premise",
                "records": [
                    _memory(
                        "mem_alice_office_2024",
                        "Alice",
                        "office_city",
                        "Paris",
                        "2024-01-01T00:00:00+00:00",
                        source_type="user_statement",
                    )
                ],
                "events": [
                    {
                        "event_id": "evt_alice_office_2025",
                        "text": "Alice says her office is now in Berlin.",
                        "entity": "Alice",
                        "slot": "office_city",
                        "value": "Berlin",
                        "observed_at": "2025-01-01T00:00:00+00:00",
                        "source_type": "user_statement",
                        "source_confidence": 0.95,
                    }
                ],
                "query_requests": [
                    {
                        "request_id": "req_alice_mail",
                        "question": "Since Alice is still in Paris, where should I send mail?",
                        "entity": "Alice",
                        "slot": "office_city",
                        "premise_value": "Paris",
                    }
                ],
            },
            "expected": {
                "decision": "REJECT_STALE_PREMISE",
                "current_evidence_ids": ["evt_alice_office_2025"],
                "answer_contains": ["Berlin"],
                "stale_or_blocked_roles": {"stale_contrast": 1},
            },
        },
        {
            "case_id": "heldout_validity_marker_revoke",
            "capability": "write-time validity marker revokes current evidence",
            "service_request": {
                "request_id": "svc_heldout_validity_marker_revoke",
                "step_id": "step_heldout_validity_marker_revoke",
                "records": [
                    _memory(
                        "mem_casey_access_active",
                        "Casey",
                        "access_status",
                        "active",
                        "2025-01-01T00:00:00+00:00",
                        source_type="access_review",
                    )
                ],
                "events": [
                    {
                        "event_id": "evt_casey_access_revoked",
                        "event_type": "invalidate_current",
                        "entity": "Casey",
                        "slot": "access_status",
                        "value": "revoked",
                        "observed_at": "2025-03-01T00:00:00+00:00",
                        "source_type": "tool_result",
                        "source_confidence": 0.98,
                        "invalidates_memory_ids": ["mem_casey_access_active"],
                    }
                ],
                "queries": [
                    {
                        "query_id": "q_casey_access",
                        "query": "Is Casey active now?",
                        "entity": "Casey",
                        "slot": "access_status",
                        "needs_current": True,
                    }
                ],
            },
            "expected": {
                "decision": "UNKNOWN_CURRENT",
                "answer_contains": ["do not have admitted current"],
                "blocked_counts": {"revoked_contrast": 1},
                "stale_or_blocked_roles": {"validity_marker": 1, "revoked_contrast": 1},
            },
        },
        {
            "case_id": "heldout_source_policy_blocks_untrusted_current",
            "capability": "retrieval-time source policy blocks otherwise current memory",
            "service_request": {
                "request_id": "svc_heldout_source_policy",
                "step_id": "step_heldout_source_policy",
                "records": [
                    _memory(
                        "mem_drew_location_imported",
                        "Drew",
                        "travel_city",
                        "Tokyo",
                        "2025-02-01T00:00:00+00:00",
                        source_type="profile_import",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_drew_travel_city",
                        "query": "Where is Drew traveling now according to user statements?",
                        "entity": "Drew",
                        "slot": "travel_city",
                        "needs_current": True,
                        "allowed_source_types": ["user_statement"],
                    }
                ],
            },
            "expected": {
                "decision": "UNKNOWN_CURRENT",
                "blocked_counts": {"source_policy_mismatch": 1},
                "stale_or_blocked_roles": {"source_policy_mismatch": 1},
            },
        },
        {
            "case_id": "heldout_scope_isolation_blocks_cross_user_memory",
            "capability": "retrieval scope prevents cross-user leakage",
            "service_request": {
                "request_id": "svc_heldout_scope_isolation",
                "step_id": "step_heldout_scope_isolation",
                "records": [
                    _memory(
                        "mem_erin_plan_user_a",
                        "Erin",
                        "recovery_plan",
                        "alpha",
                        "2025-01-15T00:00:00+00:00",
                        namespace="care",
                        tenant_id="clinic_1",
                        user_id="user_a",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_erin_plan_user_b",
                        "query": "What is Erin's current recovery plan for user B?",
                        "entity": "Erin",
                        "slot": "recovery_plan",
                        "scope": {
                            "namespace": "care",
                            "tenant_id": "clinic_1",
                            "user_id": "user_b",
                        },
                    }
                ],
            },
            "expected": {
                "decision": "UNKNOWN_CURRENT",
                "blocked_counts": {"scope_mismatch": 1},
                "scope_mismatch_records_total": 1,
            },
        },
        {
            "case_id": "heldout_condition_mismatch_blocks_contextual_memory",
            "capability": "conditioned memory is blocked when query condition differs",
            "service_request": {
                "request_id": "svc_heldout_condition_mismatch",
                "step_id": "step_heldout_condition_mismatch",
                "records": [
                    _memory(
                        "mem_finn_contact_travel",
                        "Finn",
                        "contact_channel",
                        "satellite_phone",
                        "2025-01-10T00:00:00+00:00",
                        condition="when traveling",
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_finn_contact_home",
                        "query": "How should I contact Finn at home?",
                        "entity": "Finn",
                        "slot": "contact_channel",
                        "condition": "when at home",
                    }
                ],
            },
            "expected": {
                "decision": "UNKNOWN_CURRENT",
                "blocked_counts": {"condition_mismatch": 1},
                "stale_or_blocked_roles": {"condition_mismatch": 1},
            },
        },
        {
            "case_id": "heldout_as_of_recovers_historical_current",
            "capability": "as-of query can admit a historical value while newer evidence is future evidence",
            "service_request": {
                "request_id": "svc_heldout_as_of_historical",
                "step_id": "step_heldout_as_of_historical",
                "records": [
                    _memory(
                        "mem_quinn_plan_2024",
                        "Quinn",
                        "subscription_plan",
                        "analog",
                        "2024-01-01T00:00:00+00:00",
                    ),
                    _memory(
                        "mem_quinn_plan_2025",
                        "Quinn",
                        "subscription_plan",
                        "digital",
                        "2025-01-01T00:00:00+00:00",
                    ),
                ],
                "queries": [
                    {
                        "query_id": "q_quinn_plan_2024_06",
                        "query": "What was Quinn's subscription plan in June 2024?",
                        "entity": "Quinn",
                        "slot": "subscription_plan",
                        "as_of": "2024-06-01T00:00:00+00:00",
                    }
                ],
            },
            "expected": {
                "decision": "ADMIT_CURRENT",
                "current_evidence_ids": ["mem_quinn_plan_2024"],
                "answer_contains": ["analog"],
                "blocked_counts": {"future_evidence": 1},
            },
        },
        {
            "case_id": "heldout_low_confidence_rejected_at_write_time",
            "capability": "low-confidence memory is stored as excluded evidence and not admitted",
            "service_request": {
                "request_id": "svc_heldout_low_confidence",
                "step_id": "step_heldout_low_confidence",
                "records": [
                    _memory(
                        "mem_gray_channel_low_conf",
                        "Gray",
                        "preferred_channel",
                        "sms",
                        "2025-01-01T00:00:00+00:00",
                        source_confidence=0.4,
                    )
                ],
                "queries": [
                    {
                        "query_id": "q_gray_channel",
                        "query": "What is Gray's current preferred channel?",
                        "entity": "Gray",
                        "slot": "preferred_channel",
                    }
                ],
            },
            "expected": {
                "decision": "UNKNOWN_CURRENT",
                "excluded_memory_ids": ["mem_gray_channel_low_conf"],
                "blocking_evidence_ids": ["mem_gray_channel_low_conf"],
            },
        },
    ]


def run_heldout_integration_eval(
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the deterministic held-out lifecycle integration checks."""

    cases = deepcopy(cases or build_heldout_integration_requests())
    case_results = [_run_case(case) for case in cases]
    passed_cases = sum(1 for case in case_results if case["passed"])
    total_checks = sum(len(case["checks"]) for case in case_results)
    passed_checks = sum(
        1 for case in case_results for check in case["checks"] if check["passed"]
    )
    return {
        "decision": (
            "GO_QVF_HELDOUT_INTEGRATION_EVAL_PASS_NO_API"
            if passed_cases == len(case_results)
            else "NO_GO_QVF_HELDOUT_INTEGRATION_EVAL_FAIL_NO_API"
        ),
        "execution_mode": "qvf_validity_admission_heldout_integration_eval",
        "case_count": len(case_results),
        "passed_case_count": passed_cases,
        "failed_case_count": len(case_results) - passed_cases,
        "check_count": total_checks,
        "passed_check_count": passed_checks,
        "failed_check_count": total_checks - passed_checks,
        "api_calls_made": 0,
        "case_results": case_results,
        "claim_boundary": [
            "This is deterministic no-API integration evidence for the lifecycle service.",
            "It is not target-model accuracy evidence and does not estimate STALE400 performance.",
        ],
    }


def write_heldout_integration_eval(
    output_dir: str | Path,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write held-out service requests, results, summary JSON, and a case CSV."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    case_pack = deepcopy(cases or build_heldout_integration_requests())
    result = run_heldout_integration_eval(case_pack)

    _write_json(output_path / "heldout_service_requests.json", case_pack)
    _write_json(output_path / "heldout_integration_results.json", result)
    _write_json(
        output_path / "heldout_integration_summary.json",
        {
            key: value
            for key, value in result.items()
            if key not in {"case_results", "claim_boundary"}
        },
    )
    _write_case_csv(output_path / "heldout_integration_cases.csv", result["case_results"])
    return {
        "decision": result["decision"],
        "execution_mode": "qvf_validity_admission_heldout_integration_eval_writer",
        "output_dir": str(output_path),
        "files": [
            str(output_path / "heldout_service_requests.json"),
            str(output_path / "heldout_integration_results.json"),
            str(output_path / "heldout_integration_summary.json"),
            str(output_path / "heldout_integration_cases.csv"),
        ],
        "case_count": result["case_count"],
        "passed_case_count": result["passed_case_count"],
        "failed_case_count": result["failed_case_count"],
        "api_calls_made": 0,
    }


def build_model_eval_plan(
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare the low/mainstream model evaluation plan without making calls."""

    case_pack = deepcopy(cases or build_heldout_integration_requests())
    weak_methods = [
        "direct_service_context",
        "weak_conservative_gate",
    ]
    mainstream_methods = [
        "direct_service_context",
        "slim_validity_packet",
        "graph_lite_validity_packet",
    ]
    weak_target_calls = len(case_pack) * len(weak_methods)
    mainstream_target_calls = len(case_pack) * len(mainstream_methods)
    target_calls = weak_target_calls + mainstream_target_calls
    return {
        "decision": "NEEDS_EXPLICIT_GO_BEFORE_API_RUN",
        "execution_mode": "qvf_validity_admission_model_eval_plan_no_api",
        "api_calls_made": 0,
        "hypotheses": [
            {
                "model_group": "low_capability",
                "hypothesis": (
                    "A weak model will benefit most from the conservative gate because "
                    "it makes stale-premise rejection explicit before free-form answering."
                ),
            },
            {
                "model_group": "mainstream",
                "hypothesis": (
                    "A mainstream model should preserve current-evidence admission while "
                    "rejecting stale/invalid premises from compact packets or graph-lite packets."
                ),
            },
        ],
        "dataset_slice": {
            "name": "qvf_validity_admission_heldout_integration_cases",
            "case_count": len(case_pack),
            "case_ids": [case["case_id"] for case in case_pack],
            "evidence_boundary": (
                "This slice evaluates integration behavior and stale/invalid-memory pressure; "
                "it is not an official benchmark claim."
            ),
        },
        "methods": [
            {
                "model_group": "low_capability",
                "method": method,
                "case_count": len(case_pack),
            }
            for method in weak_methods
        ]
        + [
            {
                "model_group": "mainstream",
                "method": method,
                "case_count": len(case_pack),
            }
            for method in mainstream_methods
        ],
        "expected_call_count": {
            "low_capability_target_calls": weak_target_calls,
            "mainstream_target_calls": mainstream_target_calls,
            "target_calls_total": target_calls,
            "judge_calls_if_llm_judged": target_calls,
            "max_calls_with_llm_judge": target_calls * 2,
        },
        "health_gates": {
            "final_answer_parseable_rate_min": 0.95,
            "structured_schema_ok_rate_min": 0.95,
            "max_token_truncation_rate_max": 0.02,
            "missing_output_count_max": 0,
        },
        "acceptance_criteria": [
            (
                "Low-capability QVF/gate method improves stale/invalid rejection over "
                "direct_service_context by at least 20 percentage points on applicable cases."
            ),
            (
                "Mainstream compact/graph-lite methods match or exceed direct_service_context "
                "overall and introduce no more than one current-admission regression."
            ),
            "All compared methods pass health gates before any accuracy claim is used.",
        ],
        "cost_estimate_status": (
            "Provider pricing must be checked at execution time before GO; no API calls "
            "were made while preparing this plan."
        ),
        "go_no_go": "NO_GO_API_UNTIL_USER_APPROVES_MODEL_RUN",
    }


def write_model_eval_plan(
    output_dir: str | Path,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write safe model-eval planning files without target or judge calls."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    case_pack = deepcopy(cases or build_heldout_integration_requests())
    plan = build_model_eval_plan(case_pack)
    _write_json(output_path / "model_eval_plan.json", plan)
    _write_json(output_path / "model_eval_cases.json", case_pack)
    _write_methods_csv(output_path / "model_eval_methods.csv", plan["methods"])
    return {
        "decision": plan["decision"],
        "execution_mode": "qvf_validity_admission_model_eval_plan_writer_no_api",
        "output_dir": str(output_path),
        "files": [
            str(output_path / "model_eval_plan.json"),
            str(output_path / "model_eval_cases.json"),
            str(output_path / "model_eval_methods.csv"),
        ],
        "case_count": len(case_pack),
        "api_calls_made": 0,
        "go_no_go": plan["go_no_go"],
    }


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    response = run_qvf_service_request(deepcopy(case["service_request"]))
    query_results = response["step_report"]["query_report"]["query_results"]
    if len(query_results) != 1:
        raise ValueError(f"{case['case_id']} must produce exactly one query result")
    result = query_results[0]
    checks = _evaluate_expectations(result, case["expected"])
    return {
        "case_id": case["case_id"],
        "capability": case["capability"],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "actual": _case_actual(result),
        "service_decision": response["decision"],
        "api_calls_made": response["api_calls_made"],
    }


def _case_actual(result: dict[str, Any]) -> dict[str, Any]:
    packet = result["packet"]
    compact = packet["compact_validity_packet"]
    return {
        "query_id": result["query_id"],
        "decision": result["read_decision"]["decision"],
        "answer_policy": result["read_decision"]["answer_policy"],
        "current_evidence_ids": [
            row["memory_id"] for row in compact["current_evidence"]
        ],
        "stale_or_blocked_roles": _count_roles(compact["stale_or_blocked_evidence"]),
        "excluded_memory_ids": [
            row["memory_id"] for row in compact["excluded_memory_summary"]
        ],
        "blocking_evidence_ids": result["read_decision"]["blocking_evidence_ids"],
        "blocked_counts": packet["retrieval_diagnostics"]["blocked_counts"],
        "scope_mismatch_records_total": packet["retrieval_diagnostics"][
            "scope_mismatch_records_total"
        ],
        "final_answer": result["reader_response"]["final_answer"],
    }


def _evaluate_expectations(
    result: dict[str, Any],
    expected: dict[str, Any],
) -> list[dict[str, Any]]:
    actual = _case_actual(result)
    checks: list[dict[str, Any]] = []
    _add_check(checks, "decision", expected.get("decision"), actual["decision"])
    for field_name in [
        "current_evidence_ids",
        "excluded_memory_ids",
        "blocking_evidence_ids",
        "scope_mismatch_records_total",
    ]:
        if field_name in expected:
            _add_check(checks, field_name, expected[field_name], actual[field_name])
    if "blocked_counts" in expected:
        for name, value in expected["blocked_counts"].items():
            _add_check(
                checks,
                f"blocked_counts.{name}",
                value,
                actual["blocked_counts"].get(name, 0),
            )
    if "stale_or_blocked_roles" in expected:
        for name, value in expected["stale_or_blocked_roles"].items():
            _add_check(
                checks,
                f"stale_or_blocked_roles.{name}",
                value,
                actual["stale_or_blocked_roles"].get(name, 0),
            )
    for snippet in expected.get("answer_contains", []):
        _add_check(
            checks,
            f"answer_contains.{snippet}",
            True,
            snippet in actual["final_answer"],
        )
    return checks


def _add_check(
    checks: list[dict[str, Any]],
    name: str,
    expected: Any,
    actual: Any,
) -> None:
    checks.append(
        {
            "name": name,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        }
    )


def _count_roles(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = str(row["retrieval_role"])
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_case_csv(path: Path, case_results: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "capability",
                "passed",
                "decision",
                "current_evidence_ids",
                "stale_or_blocked_roles",
                "excluded_memory_ids",
                "blocking_evidence_ids",
                "api_calls_made",
            ],
        )
        writer.writeheader()
        for result in case_results:
            actual = result["actual"]
            writer.writerow(
                {
                    "case_id": result["case_id"],
                    "capability": result["capability"],
                    "passed": result["passed"],
                    "decision": actual["decision"],
                    "current_evidence_ids": "|".join(actual["current_evidence_ids"]),
                    "stale_or_blocked_roles": json.dumps(
                        actual["stale_or_blocked_roles"],
                        sort_keys=True,
                    ),
                    "excluded_memory_ids": "|".join(actual["excluded_memory_ids"]),
                    "blocking_evidence_ids": "|".join(actual["blocking_evidence_ids"]),
                    "api_calls_made": result["api_calls_made"],
                }
            )


def _write_methods_csv(path: Path, methods: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["model_group", "method", "case_count"],
        )
        writer.writeheader()
        writer.writerows(methods)
