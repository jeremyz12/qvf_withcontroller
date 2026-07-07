"""API-backed answer-model evaluation for QVF packed memory context."""

from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

from .analysis_pipeline import run_qvf_parser_analyzer_request
from .targeted_benchmark import build_targeted_benchmark_cases

ANSWER_EVAL_VERSION = "qvf_answer_model_eval_v0.1"
DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
DEFAULT_CASES_PER_FAMILY = 2
DEFAULT_MAX_OUTPUT_TOKENS = 220
GPT_4O_MINI_ESTIMATED_INPUT_USD_PER_1M = 0.15
GPT_4O_MINI_ESTIMATED_OUTPUT_USD_PER_1M = 0.60


def run_answer_model_eval(
    output_dir: Path,
    *,
    cases_per_family: int = DEFAULT_CASES_PER_FAMILY,
    answer_model: str = DEFAULT_ANSWER_MODEL,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    run_api: bool = False,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Write preflight and optionally run direct-vs-QVF answer-model evaluation."""

    if isinstance(cases_per_family, bool) or cases_per_family <= 0:
        raise ValueError("cases_per_family must be a positive integer")
    if isinstance(max_output_tokens, bool) or max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be a positive integer")
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = build_targeted_benchmark_cases(cases_per_family=cases_per_family)
    eval_items = build_answer_eval_items(cases)
    preflight = _build_preflight(
        output_dir=output_dir,
        eval_items=eval_items,
        answer_model=answer_model,
        judge_model=judge_model,
        max_output_tokens=max_output_tokens,
    )
    _write_json(output_dir / "answer_model_preflight.json", preflight)
    _write_preflight_report(output_dir / "answer_model_preflight_zh.md", preflight)

    if not run_api:
        return {
            "decision": "NEEDS_RUN_API_FOR_ANSWER_MODEL_EVAL",
            "execution_mode": "answer_model_eval_preflight_only",
            "answer_eval_version": ANSWER_EVAL_VERSION,
            "case_count": len(cases),
            "target_call_count": preflight["expected_call_count"]["target_calls"],
            "judge_call_count": preflight["expected_call_count"]["judge_calls"],
            "api_calls_made": 0,
            "preflight_files": [
                str(output_dir / "answer_model_preflight.json"),
                str(output_dir / "answer_model_preflight_zh.md"),
            ],
        }

    client = _OpenAIChatClient()
    raw_targets: list[dict[str, Any]] = []
    raw_judges: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    for item in eval_items:
        target_response = _call_with_timing(
            client,
            model=answer_model,
            messages=item["target_messages"],
            max_tokens=max_output_tokens,
        )
        target_content = _message_content(target_response["response"])
        raw_targets.append(
            {
                "case_id": item["case_id"],
                "family": item["family"],
                "method": item["method"],
                "model": answer_model,
                "latency_seconds": target_response["latency_seconds"],
                "usage": target_response["usage"],
                "content": target_content,
                "raw_response": target_response["response"],
            }
        )
        judge_messages = _judge_messages(item, target_content)
        judge_response = _call_with_timing(
            client,
            model=judge_model,
            messages=judge_messages,
            max_tokens=180,
        )
        judge_content = _message_content(judge_response["response"])
        judgment = _parse_judgment(judge_content)
        raw_judges.append(
            {
                "case_id": item["case_id"],
                "family": item["family"],
                "method": item["method"],
                "model": judge_model,
                "latency_seconds": judge_response["latency_seconds"],
                "usage": judge_response["usage"],
                "content": judge_content,
                "parsed_judgment": judgment,
                "raw_response": judge_response["response"],
            }
        )
        result_rows.append(
            _result_row(
                item=item,
                target_content=target_content,
                target_response=target_response,
                judge_response=judge_response,
                judgment=judgment,
            )
        )

    summary = _summarize_answer_eval(
        rows=result_rows,
        answer_model=answer_model,
        judge_model=judge_model,
    )
    result = {
        "decision": "GO_QVF_ANSWER_MODEL_EVAL_COMPLETE",
        "execution_mode": "answer_model_eval_api_run",
        "answer_eval_version": ANSWER_EVAL_VERSION,
        "summary": summary,
        "case_results": result_rows,
        "api_calls_made": len(raw_targets) + len(raw_judges),
        "claim_boundary": [
            "This is a small API-backed pilot on targeted synthetic cases.",
            "It measures answer-model behavior under direct retrieved context versus QVF packed context.",
            "It is not a broad public-benchmark generalization result.",
        ],
    }
    _write_jsonl(output_dir / "target_outputs.jsonl", raw_targets)
    _write_jsonl(output_dir / "judge_outputs.jsonl", raw_judges)
    _write_json(output_dir / "answer_model_results.json", result)
    _write_json(
        output_dir / "answer_model_summary.json",
        {key: value for key, value in result.items() if key != "case_results"},
    )
    _write_result_csv(output_dir / "answer_model_cases.csv", result_rows)
    _write_result_report(output_dir / "answer_model_report_zh.md", result)
    return {
        "decision": result["decision"],
        "execution_mode": result["execution_mode"],
        "case_count": summary["case_count"],
        "method_summary": summary["method_summary"],
        "api_calls_made": result["api_calls_made"],
        "output_files": [
            str(output_dir / "answer_model_preflight.json"),
            str(output_dir / "answer_model_preflight_zh.md"),
            str(output_dir / "target_outputs.jsonl"),
            str(output_dir / "judge_outputs.jsonl"),
            str(output_dir / "answer_model_results.json"),
            str(output_dir / "answer_model_summary.json"),
            str(output_dir / "answer_model_cases.csv"),
            str(output_dir / "answer_model_report_zh.md"),
        ],
    }


def build_answer_eval_items(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build direct and QVF prompt items from targeted benchmark cases."""

    items: list[dict[str, Any]] = []
    for case in deepcopy(cases):
        expected = _expected_for_case(case)
        direct_context = _direct_context(case["service_request"])
        qvf_context = _qvf_context(case["service_request"])
        for method, context in [
            ("direct_retrieved_context", direct_context),
            ("qvf_packed_context", qvf_context),
        ]:
            items.append(
                {
                    "case_id": case["case_id"],
                    "family": case["family"],
                    "method": method,
                    "question": _question(case["service_request"]),
                    "target_messages": _target_messages(
                        question=_question(case["service_request"]),
                        method=method,
                        context=context,
                    ),
                    "judge_expected": expected,
                    "context": context,
                }
            )
    return items


def _target_messages(*, question: str, method: str, context: dict[str, Any]) -> list[dict[str, str]]:
    if method == "qvf_packed_context":
        instruction = (
            "Answer using only the admitted QVF context and follow response_contract exactly. "
            "If QVF says the premise is stale, explicitly reject that premise before giving "
            "any current-state answer. Do not use suppressed memories."
        )
    else:
        instruction = (
            "Answer using the retrieved memories below. Prefer current information if it is clear."
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a concise memory-grounded assistant. Return JSON only with keys "
                "answer, used_memory_ids, and abstained."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "instruction": instruction,
                    "question": question,
                    "memory_context": context,
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def _judge_messages(item: dict[str, Any], target_content: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a strict evaluator. Return JSON only with keys correct "
                "(boolean), error_type (string), and rationale (string)."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": item["question"],
                    "method": item["method"],
                    "expected": item["judge_expected"],
                    "model_answer": target_content,
                    "grading_rules": [
                        "If expected.decision is REJECT_STALE_PREMISE and expected.current_values is non-empty, mark correct only when the answer explicitly rejects the stale premise and answers the user's practical request using a current value.",
                        "For REJECT_STALE_PREMISE, do not require exact wording; 'stale', 'outdated', 'invalid premise', or equivalent wording is enough.",
                        "If expected.current_values is non-empty for any other decision, the answer is correct only if it uses the current value and does not affirm stale or blocked values.",
                        "If expected.answer_policy is insufficient_current_state, the answer is correct only if it refuses/abstains due to missing valid current evidence and does not answer from blocked memory.",
                        "Ignore minor wording differences.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def _expected_for_case(case: dict[str, Any]) -> dict[str, Any]:
    service_request = case["service_request"]
    id_to_value = {
        row["memory_id"]: row.get("value", "")
        for row in service_request.get("records", [])
    }
    id_to_value.update(
        {
            row["event_id"]: row.get("value", "")
            for row in service_request.get("events", [])
        }
    )
    expected_ids = list(case["expected"].get("current_evidence_ids", []))
    all_values = [
        str(row.get("value", ""))
        for row in service_request.get("records", [])
    ] + [
        str(row.get("value", ""))
        for row in service_request.get("events", [])
    ]
    current_values = [id_to_value[memory_id] for memory_id in expected_ids if memory_id in id_to_value]
    return {
        "decision": case["expected"]["decision"],
        "answer_policy": case["expected"].get("answer_policy", ""),
        "current_memory_ids": expected_ids,
        "current_values": current_values,
        "blocked_values": [
            value for value in all_values if value and value not in set(current_values)
        ],
    }


def _direct_context(service_request: dict[str, Any]) -> dict[str, Any]:
    memories = []
    for row in service_request.get("records", []):
        memories.append(_memory_context_row(row["memory_id"], row))
    for row in service_request.get("events", []):
        memories.append(_memory_context_row(row["event_id"], row))
    return {
        "context_type": "direct_retrieved_memories",
        "retrieved_memories": memories,
    }


def _qvf_context(service_request: dict[str, Any]) -> dict[str, Any]:
    analysis = run_qvf_parser_analyzer_request(service_request)["query_analyses"][0]
    read_decision = analysis["read_decision"]
    return {
        "context_type": "qvf_packed_context",
        "qvf_read_time_decision": {
            "decision": read_decision["decision"],
            "answer_policy": read_decision["answer_policy"],
            "route": read_decision["route"],
        },
        "response_contract": _qvf_response_contract(read_decision),
        "admitted_context": analysis["packed_context"],
    }


def _qvf_response_contract(read_decision: dict[str, Any]) -> str:
    decision = read_decision.get("decision")
    if decision == "REJECT_STALE_PREMISE":
        return (
            "Explicitly state that the premise in the user question is stale or invalid. "
            "Then, if admitted context evidence is present, answer the user's practical request "
            "using the current value from that evidence. "
            "Do not answer as though the stale premise is true."
        )
    if decision == "UNKNOWN_CURRENT":
        return (
            "State that valid current evidence is unavailable for this query. "
            "Do not infer an answer from suppressed, mismatched, or absent memories."
        )
    if decision == "ADMIT_CURRENT":
        return "Answer directly from admitted current evidence only."
    return "Follow the QVF read-time decision and admitted context only."


def _memory_context_row(memory_id: str, row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source", {})
    return {
        "memory_id": memory_id,
        "claim": row.get("claim") or row.get("text", ""),
        "value": row.get("value", ""),
        "observed_at": row.get("observed_at", ""),
        "condition": row.get("condition"),
        "scope": row.get("scope", {}),
        "source_type": row.get("source_type") or source.get("source_type", ""),
    }


def _question(service_request: dict[str, Any]) -> str:
    queries = service_request.get("queries", [])
    if queries:
        return str(queries[0]["query"])
    query_requests = service_request.get("query_requests", [])
    if query_requests:
        return str(query_requests[0]["question"])
    raise ValueError("service request must contain one query")


def _call_with_timing(
    client: "_OpenAIChatClient",
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    elapsed = time.perf_counter() - started
    return {
        "response": response,
        "latency_seconds": elapsed,
        "usage": response.get("usage", {}),
    }


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content", ""))


def _parse_judgment(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {
            "correct": False,
            "error_type": "judge_parse_error",
            "rationale": content[:500],
        }
    return {
        "correct": bool(parsed.get("correct", False)),
        "error_type": str(parsed.get("error_type", "")),
        "rationale": str(parsed.get("rationale", "")),
    }


def _result_row(
    *,
    item: dict[str, Any],
    target_content: str,
    target_response: dict[str, Any],
    judge_response: dict[str, Any],
    judgment: dict[str, Any],
) -> dict[str, Any]:
    target_usage = target_response["usage"]
    judge_usage = judge_response["usage"]
    return {
        "case_id": item["case_id"],
        "family": item["family"],
        "method": item["method"],
        "correct": judgment["correct"],
        "error_type": judgment["error_type"],
        "target_latency_seconds": target_response["latency_seconds"],
        "judge_latency_seconds": judge_response["latency_seconds"],
        "target_input_tokens": int(target_usage.get("prompt_tokens", 0)),
        "target_output_tokens": int(target_usage.get("completion_tokens", 0)),
        "target_total_tokens": int(target_usage.get("total_tokens", 0)),
        "judge_input_tokens": int(judge_usage.get("prompt_tokens", 0)),
        "judge_output_tokens": int(judge_usage.get("completion_tokens", 0)),
        "judge_total_tokens": int(judge_usage.get("total_tokens", 0)),
        "answer_excerpt": target_content[:500],
    }


def _summarize_answer_eval(
    *,
    rows: list[dict[str, Any]],
    answer_model: str,
    judge_model: str,
) -> dict[str, Any]:
    method_summary = []
    methods = sorted({row["method"] for row in rows})
    for method in methods:
        method_rows = [row for row in rows if row["method"] == method]
        correct_count = sum(1 for row in method_rows if row["correct"])
        target_input = sum(row["target_input_tokens"] for row in method_rows)
        target_output = sum(row["target_output_tokens"] for row in method_rows)
        judge_input = sum(row["judge_input_tokens"] for row in method_rows)
        judge_output = sum(row["judge_output_tokens"] for row in method_rows)
        method_summary.append(
            {
                "method": method,
                "case_count": len(method_rows),
                "correct_count": correct_count,
                "accuracy": correct_count / len(method_rows) if method_rows else 0.0,
                "mean_target_latency_seconds": _mean(
                    [row["target_latency_seconds"] for row in method_rows]
                ),
                "target_input_tokens": target_input,
                "target_output_tokens": target_output,
                "judge_input_tokens": judge_input,
                "judge_output_tokens": judge_output,
                "estimated_usd": _estimated_cost_usd(
                    target_input + judge_input,
                    target_output + judge_output,
                ),
            }
        )
    return {
        "answer_model": answer_model,
        "judge_model": judge_model,
        "case_count": len(rows) // 2,
        "case_method_count": len(rows),
        "method_summary": method_summary,
        "total_target_input_tokens": sum(row["target_input_tokens"] for row in rows),
        "total_target_output_tokens": sum(row["target_output_tokens"] for row in rows),
        "total_judge_input_tokens": sum(row["judge_input_tokens"] for row in rows),
        "total_judge_output_tokens": sum(row["judge_output_tokens"] for row in rows),
        "estimated_total_usd": sum(row["estimated_usd"] for row in method_summary),
    }


def _build_preflight(
    *,
    output_dir: Path,
    eval_items: list[dict[str, Any]],
    answer_model: str,
    judge_model: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    target_calls = len(eval_items)
    judge_calls = len(eval_items)
    estimated_input_tokens = sum(
        _rough_message_tokens(item["target_messages"]) + 700
        for item in eval_items
    )
    estimated_output_tokens = target_calls * max_output_tokens + judge_calls * 120
    return {
        "decision": "GO_QVF_ANSWER_MODEL_EVAL_PREFLIGHT_READY",
        "execution_mode": "answer_model_eval_preflight",
        "answer_eval_version": ANSWER_EVAL_VERSION,
        "hypothesis": (
            "QVF packed context improves answer-model accuracy by suppressing stale, "
            "condition-mismatched, scope-mismatched, and source-policy-mismatched memories."
        ),
        "dataset_slice": "targeted invalid-admission benchmark pilot",
        "case_count": target_calls // 2,
        "methods": ["direct_retrieved_context", "qvf_packed_context"],
        "answer_model": answer_model,
        "judge_model": judge_model,
        "expected_call_count": {
            "target_calls": target_calls,
            "judge_calls": judge_calls,
            "total_calls": target_calls + judge_calls,
        },
        "estimated_token_range": {
            "input_tokens": [max(0, int(estimated_input_tokens * 0.75)), int(estimated_input_tokens * 1.35)],
            "output_tokens": [max_output_tokens, estimated_output_tokens],
        },
        "estimated_cost_usd": [
            round(_estimated_cost_usd(int(estimated_input_tokens * 0.75), max_output_tokens), 6),
            round(_estimated_cost_usd(int(estimated_input_tokens * 1.35), estimated_output_tokens), 6),
        ],
        "pricing_note": (
            "Estimate uses OpenAI published GPT-4o mini launch pricing: "
            "$0.15/1M input tokens and $0.60/1M output tokens; actual billing may differ."
        ),
        "health_gates": [
            "preflight file written before any API call",
            "target and judge calls both return parseable responses",
            "usage and latency are recorded for every call",
            "raw target and judge outputs are saved only under the local ignored runs directory",
        ],
        "acceptance_criteria": [
            "qvf_packed_context accuracy is higher than direct_retrieved_context on the pilot",
            "qvf_packed_context has lower invalid-memory usage according to the judge",
            "all result files are written and no raw outputs are committed",
        ],
        "output_dir": str(output_dir),
    }


def _rough_message_tokens(messages: list[dict[str, str]]) -> int:
    text = json.dumps(messages, ensure_ascii=False)
    return max(1, len(text) // 4)


def _estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * GPT_4O_MINI_ESTIMATED_INPUT_USD_PER_1M
        + output_tokens / 1_000_000 * GPT_4O_MINI_ESTIMATED_OUTPUT_USD_PER_1M
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class _OpenAIChatClient:
    def __init__(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for --run-api")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base_url}/chat/completions"
        self.api_key = api_key

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_result_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "family",
        "method",
        "correct",
        "error_type",
        "target_latency_seconds",
        "judge_latency_seconds",
        "target_input_tokens",
        "target_output_tokens",
        "target_total_tokens",
        "judge_input_tokens",
        "judge_output_tokens",
        "judge_total_tokens",
        "answer_excerpt",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_preflight_report(path: Path, preflight: dict[str, Any]) -> None:
    lines = [
        "# QVF answer-model eval preflight",
        "",
        f"- Hypothesis: {preflight['hypothesis']}",
        f"- Dataset slice: {preflight['dataset_slice']}",
        f"- Cases: {preflight['case_count']}",
        f"- Target model: `{preflight['answer_model']}`",
        f"- Judge model: `{preflight['judge_model']}`",
        f"- Expected calls: {preflight['expected_call_count']['total_calls']}",
        f"- Estimated cost USD: {preflight['estimated_cost_usd']}",
        "",
        "## Acceptance Criteria",
        "",
    ]
    lines.extend(f"- {item}" for item in preflight["acceptance_criteria"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_result_report(path: Path, result: dict[str, Any]) -> None:
    summary = result["summary"]
    lines = [
        "# QVF answer-model evaluation",
        "",
        f"- Answer model: `{summary['answer_model']}`",
        f"- Judge model: `{summary['judge_model']}`",
        f"- Cases: {summary['case_count']}",
        f"- API calls: {result['api_calls_made']}",
        f"- Estimated total USD: {summary['estimated_total_usd']:.6f}",
        "",
        "| Method | Accuracy | Correct | Mean target latency | Target tokens | Judge tokens | Estimated USD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["method_summary"]:
        lines.append(
            f"| `{row['method']}` | "
            f"{row['accuracy'] * 100:.1f}% | "
            f"{row['correct_count']}/{row['case_count']} | "
            f"{row['mean_target_latency_seconds']:.2f}s | "
            f"{row['target_input_tokens'] + row['target_output_tokens']} | "
            f"{row['judge_input_tokens'] + row['judge_output_tokens']} | "
            f"${row['estimated_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "This is a small API-backed pilot. Treat it as model-accuracy evidence for the tested slice only, not broad benchmark generalization.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "ANSWER_EVAL_VERSION",
    "DEFAULT_ANSWER_MODEL",
    "DEFAULT_CASES_PER_FAMILY",
    "DEFAULT_JUDGE_MODEL",
    "build_answer_eval_items",
    "run_answer_model_eval",
]
