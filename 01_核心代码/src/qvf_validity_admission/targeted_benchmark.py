"""Deterministic targeted benchmark cases for invalid memory admission.

The cases in this module are synthetic but systematic. They are designed to
exercise the QVF service contract around four invalid-admission families:
stale supersession, condition mismatch, entity/scope mismatch, and source-policy
mismatch. They intentionally avoid target-model calls; model-facing evaluation
packs can be built from the generated service requests in later stages.
"""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .decisions import model_facing_forbidden_key_paths
from .service import run_qvf_service_request

BENCHMARK_VERSION = "qvf_targeted_invalid_admission_v0.1"
DEFAULT_CASES_PER_FAMILY = 30
CASE_FAMILIES = (
    "stale_supersession",
    "conditional_mismatch",
    "entity_scope_mismatch",
    "source_policy_mismatch",
)


def build_targeted_benchmark_cases(
    *,
    cases_per_family: int = DEFAULT_CASES_PER_FAMILY,
) -> list[dict[str, Any]]:
    """Build systematic no-API invalid-admission benchmark cases."""

    if isinstance(cases_per_family, bool) or not isinstance(cases_per_family, int):
        raise ValueError("cases_per_family must be a positive integer")
    if cases_per_family <= 0:
        raise ValueError("cases_per_family must be a positive integer")
    cases: list[dict[str, Any]] = []
    for index in range(cases_per_family):
        cases.append(_stale_supersession_case(index))
        cases.append(_conditional_mismatch_case(index))
        cases.append(_entity_scope_mismatch_case(index))
        cases.append(_source_policy_mismatch_case(index))
    return cases


def validate_targeted_benchmark_case(case: dict[str, Any]) -> dict[str, Any]:
    """Validate the public targeted-benchmark case shape."""

    if not isinstance(case, dict):
        raise ValueError("targeted benchmark case must be an object")
    for field_name in ["case_id", "family", "capability", "service_request", "expected"]:
        if field_name not in case:
            raise ValueError(f"targeted benchmark case.{field_name} is required")
    case_id = case["case_id"]
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("targeted benchmark case.case_id must be a non-empty string")
    family = case["family"]
    if family not in CASE_FAMILIES:
        known = ", ".join(CASE_FAMILIES)
        raise ValueError(f"targeted benchmark case.family must be one of: {known}")
    if not isinstance(case["capability"], str) or not case["capability"].strip():
        raise ValueError("targeted benchmark case.capability must be a non-empty string")
    if not isinstance(case["service_request"], dict):
        raise ValueError("targeted benchmark case.service_request must be an object")
    expected = case["expected"]
    if not isinstance(expected, dict):
        raise ValueError("targeted benchmark case.expected must be an object")
    decision = expected.get("decision")
    if decision not in {"ADMIT_CURRENT", "REJECT_STALE_PREMISE", "UNKNOWN_CURRENT"}:
        raise ValueError("targeted benchmark case.expected.decision is invalid")
    return case


def run_targeted_benchmark_eval(
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the deterministic service against targeted benchmark cases."""

    case_pack = _case_pack_or_default(cases)
    case_results = [_run_case(validate_targeted_benchmark_case(case)) for case in case_pack]
    passed = sum(1 for result in case_results if result["passed"])
    total_checks = sum(len(result["checks"]) for result in case_results)
    passed_checks = sum(
        1 for result in case_results for check in result["checks"] if check["passed"]
    )
    family_rows = _family_summary(case_results)
    return {
        "decision": (
            "GO_QVF_TARGETED_BENCHMARK_PASS_NO_API"
            if passed == len(case_results)
            else "NO_GO_QVF_TARGETED_BENCHMARK_HAS_FAILURES"
        ),
        "execution_mode": "qvf_targeted_invalid_admission_benchmark",
        "benchmark_version": BENCHMARK_VERSION,
        "case_count": len(case_results),
        "passed_case_count": passed,
        "failed_case_count": len(case_results) - passed,
        "check_count": total_checks,
        "passed_check_count": passed_checks,
        "failed_check_count": total_checks - passed_checks,
        "family_summary": family_rows,
        "case_results": case_results,
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a deterministic no-API targeted integration benchmark.",
            "It validates QVF service behavior on synthetic invalid-admission cases, not target-model answer accuracy.",
        ],
    }


def write_targeted_benchmark_eval(
    output_dir: Path,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write targeted benchmark cases, results, summary, and CSV artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    case_pack = _case_pack_or_default(cases)
    result = run_targeted_benchmark_eval(case_pack)
    files = [
        output_dir / "targeted_benchmark_cases.json",
        output_dir / "targeted_benchmark_results.json",
        output_dir / "targeted_benchmark_summary.json",
        output_dir / "targeted_benchmark_cases.csv",
        output_dir / "targeted_benchmark_report_zh.md",
    ]
    _write_json(files[0], case_pack)
    _write_json(files[1], result)
    _write_json(
        files[2],
        {key: value for key, value in result.items() if key != "case_results"},
    )
    _write_case_csv(files[3], result["case_results"])
    _write_report(files[4], result)
    return {
        "decision": "GO_QVF_TARGETED_BENCHMARK_ARTIFACTS_READY_NO_API",
        "execution_mode": "qvf_targeted_invalid_admission_benchmark_writer",
        "files": [str(path) for path in files],
        "case_count": result["case_count"],
        "passed_case_count": result["passed_case_count"],
        "failed_case_count": result["failed_case_count"],
        "api_calls_made": 0,
    }


def _case_pack_or_default(cases: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    case_pack = deepcopy(
        build_targeted_benchmark_cases()
        if cases is None
        else cases
    )
    if not isinstance(case_pack, list) or not case_pack:
        raise ValueError("targeted benchmark cases must be a non-empty list")
    return case_pack


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    response = run_qvf_service_request(deepcopy(case["service_request"]))
    query_results = response["step_report"]["query_report"]["query_results"]
    if len(query_results) != 1:
        raise ValueError(f"{case['case_id']} must produce exactly one query result")
    result = query_results[0]
    checks = _evaluate_case(result, response, case["expected"])
    return {
        "case_id": case["case_id"],
        "family": case["family"],
        "capability": case["capability"],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "actual": _case_actual(result, response),
        "expected": case["expected"],
    }


def _evaluate_case(
    result: dict[str, Any],
    response: dict[str, Any],
    expected: dict[str, Any],
) -> list[dict[str, Any]]:
    actual = _case_actual(result, response)
    checks = [
        _check_equal("decision", actual["decision"], expected["decision"]),
    ]
    if "answer_policy" in expected:
        checks.append(
            _check_equal(
                "answer_policy",
                actual["answer_policy"],
                expected["answer_policy"],
            )
        )
    if "current_evidence_ids" in expected:
        checks.append(
            _check_equal(
                "current_evidence_ids",
                actual["current_evidence_ids"],
                expected["current_evidence_ids"],
            )
        )
    if "stale_or_blocked_roles" in expected:
        checks.append(
            _check_equal(
                "stale_or_blocked_roles",
                actual["stale_or_blocked_roles"],
                expected["stale_or_blocked_roles"],
            )
        )
    if "excluded_roles" in expected:
        checks.append(
            _check_equal(
                "excluded_roles",
                actual["excluded_roles"],
                expected["excluded_roles"],
            )
        )
    forbidden_paths = model_facing_forbidden_key_paths(
        response.get("model_facing_sidecar_payloads", [])
    )
    checks.append(_check_equal("model_facing_forbidden_paths", forbidden_paths, []))
    return checks


def _case_actual(result: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    packet = result["packet"]
    compact = packet["compact_validity_packet"]
    decision = result["read_decision"]
    return {
        "decision": decision["decision"],
        "answer_policy": decision["answer_policy"],
        "route": decision["route"],
        "current_evidence_ids": [
            row["memory_id"] for row in compact.get("current_evidence", [])
        ],
        "stale_or_blocked_roles": _role_counts(
            compact.get("stale_or_blocked_evidence", [])
        ),
        "excluded_roles": _role_counts(compact.get("excluded_memory_summary", [])),
        "model_facing_payload_count": len(response.get("model_facing_sidecar_payloads", [])),
    }


def _check_equal(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    return {
        "name": name,
        "passed": actual == expected,
        "actual": actual,
        "expected": expected,
    }


def _role_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = str(row.get("retrieval_role") or row.get("evidence_role") or "")
        if role:
            counts[role] = counts.get(role, 0) + 1
    return counts


def _family_summary(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in case_results:
        grouped.setdefault(result["family"], []).append(result)
    rows: list[dict[str, Any]] = []
    for family in CASE_FAMILIES:
        results = grouped.get(family, [])
        passed = sum(1 for result in results if result["passed"])
        rows.append(
            {
                "family": family,
                "case_count": len(results),
                "passed_case_count": passed,
                "failed_case_count": len(results) - passed,
                "pass_rate": passed / len(results) if results else 0.0,
            }
        )
    return rows


def _stale_supersession_case(index: int) -> dict[str, Any]:
    person = _name("Avery", index)
    old_city = _value("Seattle", index)
    new_city = _value("Portland", index)
    case_id = f"targeted_stale_supersession_{index:03d}"
    return {
        "case_id": case_id,
        "family": "stale_supersession",
        "capability": "newer conflicting evidence rejects an outdated premise",
        "service_request": {
            "request_id": f"svc_{case_id}",
            "step_id": f"step_{case_id}",
            "records": [
                _memory(
                    f"{case_id}::old",
                    person,
                    "home_city",
                    old_city,
                    "2024-01-01T00:00:00+00:00",
                    source_type="user_statement",
                )
            ],
            "events": [
                {
                    "event_id": f"{case_id}::new",
                    "text": f"{person} says their current home city is {new_city}.",
                    "entity": person,
                    "slot": "home_city",
                    "value": new_city,
                    "observed_at": "2025-01-01T00:00:00+00:00",
                    "source_type": "user_statement",
                    "source_confidence": 0.95,
                }
            ],
            "query_requests": [
                {
                    "request_id": f"q_{case_id}",
                    "question": f"Since {person} still lives in {old_city}, where should I send mail?",
                    "entity": person,
                    "slot": "home_city",
                    "premise_value": old_city,
                }
            ],
        },
        "expected": {
            "decision": "REJECT_STALE_PREMISE",
            "answer_policy": "correct_premise_only",
            "current_evidence_ids": [f"{case_id}::new"],
            "stale_or_blocked_roles": {"stale_contrast": 1},
        },
    }


def _conditional_mismatch_case(index: int) -> dict[str, Any]:
    person = _name("Blair", index)
    case_id = f"targeted_conditional_mismatch_{index:03d}"
    return {
        "case_id": case_id,
        "family": "conditional_mismatch",
        "capability": "condition-specific memory is blocked for a mismatched query condition",
        "service_request": {
            "request_id": f"svc_{case_id}",
            "step_id": f"step_{case_id}",
            "records": [
                _memory(
                    f"{case_id}::weekday",
                    person,
                    "transport_preference",
                    _value("subway", index),
                    "2025-02-01T00:00:00+00:00",
                    condition="weekday commute",
                    source_type="user_statement",
                )
            ],
            "queries": [
                {
                    "query_id": f"q_{case_id}",
                    "query": f"What transport should {person} use for a weekend trail trip?",
                    "entity": person,
                    "slot": "transport_preference",
                    "needs_current": True,
                    "condition": "weekend trail trip",
                }
            ],
        },
        "expected": {
            "decision": "UNKNOWN_CURRENT",
            "answer_policy": "insufficient_current_state",
            "current_evidence_ids": [],
            "stale_or_blocked_roles": {"condition_mismatch": 1},
        },
    }


def _entity_scope_mismatch_case(index: int) -> dict[str, Any]:
    person = _name("Casey", index)
    case_id = f"targeted_entity_scope_mismatch_{index:03d}"
    return {
        "case_id": case_id,
        "family": "entity_scope_mismatch",
        "capability": "memory for a different scoped user is excluded despite matching entity text",
        "service_request": {
            "request_id": f"svc_{case_id}",
            "step_id": f"step_{case_id}",
            "records": [
                _memory(
                    f"{case_id}::tenant_a",
                    person,
                    "access_status",
                    "active",
                    "2025-03-01T00:00:00+00:00",
                    source_type="access_review",
                    namespace="workspace",
                    tenant_id="tenant_a",
                    user_id="user_a",
                )
            ],
            "queries": [
                {
                    "query_id": f"q_{case_id}",
                    "query": f"Is {person} active for tenant_b user_b now?",
                    "entity": person,
                    "slot": "access_status",
                    "needs_current": True,
                    "scope": {
                        "namespace": "workspace",
                        "tenant_id": "tenant_b",
                        "user_id": "user_b",
                    },
                }
            ],
        },
        "expected": {
            "decision": "UNKNOWN_CURRENT",
            "answer_policy": "insufficient_current_state",
            "current_evidence_ids": [],
            "stale_or_blocked_roles": {},
            "excluded_roles": {},
        },
    }


def _source_policy_mismatch_case(index: int) -> dict[str, Any]:
    person = _name("Drew", index)
    case_id = f"targeted_source_policy_mismatch_{index:03d}"
    return {
        "case_id": case_id,
        "family": "source_policy_mismatch",
        "capability": "source policy blocks an otherwise current memory",
        "service_request": {
            "request_id": f"svc_{case_id}",
            "step_id": f"step_{case_id}",
            "records": [
                _memory(
                    f"{case_id}::imported",
                    person,
                    "medical_status",
                    _value("cleared_for_training", index),
                    "2025-04-01T00:00:00+00:00",
                    source_type="profile_import",
                )
            ],
            "queries": [
                {
                    "query_id": f"q_{case_id}",
                    "query": f"What is {person}'s current training status from clinician notes?",
                    "entity": person,
                    "slot": "medical_status",
                    "needs_current": True,
                    "allowed_source_types": ["clinician_note"],
                }
            ],
        },
        "expected": {
            "decision": "UNKNOWN_CURRENT",
            "answer_policy": "insufficient_current_state",
            "current_evidence_ids": [],
            "stale_or_blocked_roles": {"source_policy_mismatch": 1},
        },
    }


def _memory(
    memory_id: str,
    entity: str,
    slot: str,
    value: str,
    observed_at: str,
    *,
    source_confidence: float = 0.9,
    condition: str | None = None,
    source_type: str = "synthetic_targeted",
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
            "source_id": f"source_{memory_id}",
            "source_type": source_type,
        },
        "observed_at": observed_at,
        "valid_from": observed_at,
        "condition": condition,
        "scope": {
            "namespace": namespace,
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
        "source_confidence": source_confidence,
    }


def _name(prefix: str, index: int) -> str:
    return f"{prefix}_{index:03d}"


def _value(prefix: str, index: int) -> str:
    return f"{prefix}_{index:03d}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_case_csv(path: Path, case_results: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for result in case_results:
        rows.append(
            {
                "case_id": result["case_id"],
                "family": result["family"],
                "capability": result["capability"],
                "passed": result["passed"],
                "decision": result["actual"]["decision"],
                "answer_policy": result["actual"]["answer_policy"],
                "current_evidence_ids": json.dumps(
                    result["actual"]["current_evidence_ids"],
                    sort_keys=True,
                ),
                "stale_or_blocked_roles": json.dumps(
                    result["actual"]["stale_or_blocked_roles"],
                    sort_keys=True,
                ),
                "excluded_roles": json.dumps(
                    result["actual"]["excluded_roles"],
                    sort_keys=True,
                ),
                "failed_checks": json.dumps(
                    [
                        check["name"]
                        for check in result["checks"]
                        if not check["passed"]
                    ],
                    sort_keys=True,
                ),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_report(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# QVF targeted invalid-admission benchmark",
        "",
        "## 结果",
        "",
        f"- Benchmark version: `{result['benchmark_version']}`",
        f"- Cases: {result['passed_case_count']}/{result['case_count']} passed",
        f"- Checks: {result['passed_check_count']}/{result['check_count']} passed",
        "- API calls: 0",
        "",
        "## Family summary",
        "",
        "| Family | Cases | Passed | Pass rate |",
        "|---|---:|---:|---:|",
    ]
    for row in result["family_summary"]:
        lines.append(
            f"| {row['family']} | {row['case_count']} | "
            f"{row['passed_case_count']} | {row['pass_rate'] * 100:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is deterministic engineering evidence for the QVF service contract. "
            "It is not target-model answer accuracy and not broad benchmark evidence.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "BENCHMARK_VERSION",
    "CASE_FAMILIES",
    "DEFAULT_CASES_PER_FAMILY",
    "build_targeted_benchmark_cases",
    "run_targeted_benchmark_eval",
    "validate_targeted_benchmark_case",
    "write_targeted_benchmark_eval",
]
