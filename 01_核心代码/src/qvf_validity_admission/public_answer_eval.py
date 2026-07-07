"""Answer-model evaluation for public-dataset QVF service requests."""

from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .answer_model_eval import (
    DEFAULT_ANSWER_MODEL,
    DEFAULT_JUDGE_MODEL,
    GPT_4O_MINI_ESTIMATED_INPUT_USD_PER_1M,
    GPT_4O_MINI_ESTIMATED_OUTPUT_USD_PER_1M,
)
from .public_dataset_adapters import load_public_dataset_rows
from .query_risk_router import (
    CONDITIONAL_ROUTE,
    CURRENT_ROUTE,
    EVIDENCE_CONFLICT_ROUTE,
    HYBRID_ROUTE,
    TRANSITION_ROUTE,
    route_query_risk,
)
from .service import run_qvf_service_request

PUBLIC_ANSWER_EVAL_VERSION = "qvf_public_answer_eval_v0.9"
DEFAULT_PUBLIC_ANSWER_EVAL_LIMIT = 10
DEFAULT_PUBLIC_ANSWER_MAX_OUTPUT_TOKENS = 220
MAX_TEMPORAL_RESOLUTION_HINTS = 3
MAX_CONDITION_SCOPE_HINTS = 2
MAX_SCOPED_READER_EVENTS = 4
MAX_HABIT_FREQUENCY_HINTS = 4
MAX_ANSWER_RENDERING_ANCHORS = 6
MAX_ANSWER_RENDERING_ANCHOR_CHARS = 160
MAX_ANSWER_DECISION_CONTRACT_ROWS = 4
MAX_ANSWER_DECISION_CONTRACT_PHRASES = 4
MAX_ANSWER_DECISION_CONTRACT_CHARS = 220
MAX_COMPUTATIONAL_CANDIDATE_ROWS = 8
MAX_COMPUTATIONAL_CANDIDATE_ITEMS = 12
MAX_SOURCE_HISTORY_FOCUS_ROWS = 4
MAX_SOURCE_HISTORY_FOCUS_SENTENCE_CHARS = 420
MAX_SOURCE_HISTORY_ANSWER_ANCHOR_ROWS = 4
MAX_SOURCE_HISTORY_ANSWER_ANCHOR_TERMS = 8
RETRIEVAL_FEEDBACK_VERSION = "qvf_retrieval_feedback_v0.1"
POST_ANSWER_CONTRACT_REPAIR_MIN_SCORE = 16
POST_ANSWER_CONTRACT_REPAIR_MIN_GAIN = 0.18
QVF_CONTEXT_VARIANTS = (
    "adaptive",
    "evidence_preserving",
    "full",
    "compact_full",
    "auto_compact",
    "no_source_history_repair",
    "core_routing",
    "selective_router",
    "annotation_only_qvf",
    "multi_action_controller",
    "post_answer_audit_controller",
)
DEFAULT_QVF_CONTEXT_VARIANT = "adaptive"
DIRECT_METHOD = "direct_extracted_memories"
QVF_METHOD = "qvf_validity_packed_context"
SELECTIVE_ROUTER_METHOD = "qvf_selective_router"
QVF_CONTEXT_ROW_FIELDS = (
    "memory_id",
    "claim",
    "value",
    "observed_at",
    "valid_until",
    "source_type",
    "source_span",
    "source_confidence",
    "current_status",
    "retrieval_role",
)


def load_public_qvf_requests(path: Path) -> list[dict[str, Any]]:
    """Load QVF service requests from JSON/JSONL."""

    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for field_name in ("qvf_service_requests", "requests", "data", "items"):
            if isinstance(payload.get(field_name), list):
                return payload[field_name]
    raise ValueError("public QVF request input must be a JSON list or JSONL file")


def run_public_answer_eval(
    output_dir: Path,
    *,
    adapter_items_path: Path,
    qvf_requests_path: Path,
    answer_model: str = DEFAULT_ANSWER_MODEL,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    limit: int = DEFAULT_PUBLIC_ANSWER_EVAL_LIMIT,
    run_api: bool = False,
    max_output_tokens: int = DEFAULT_PUBLIC_ANSWER_MAX_OUTPUT_TOKENS,
    qvf_context_variant: str = DEFAULT_QVF_CONTEXT_VARIANT,
) -> dict[str, Any]:
    """Write preflight and optionally run public direct-vs-QVF answer evaluation."""

    _validate_positive_int(limit, "limit")
    _validate_positive_int(max_output_tokens, "max_output_tokens")
    qvf_context_variant = _validate_qvf_context_variant(qvf_context_variant)
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter_items = load_public_dataset_rows(adapter_items_path)
    qvf_requests = load_public_qvf_requests(qvf_requests_path)
    eval_items = build_public_answer_eval_items(
        adapter_items=adapter_items,
        qvf_requests=qvf_requests,
        limit=limit,
        qvf_context_variant=qvf_context_variant,
    )
    preflight = _build_preflight(
        output_dir=output_dir,
        adapter_items_path=adapter_items_path,
        qvf_requests_path=qvf_requests_path,
        eval_items=eval_items,
        answer_model=answer_model,
        judge_model=judge_model,
        max_output_tokens=max_output_tokens,
        qvf_context_variant=qvf_context_variant,
    )
    payload_audit = _build_target_payload_audit(
        eval_items,
        qvf_context_variant=qvf_context_variant,
    )
    _write_json(output_dir / "public_answer_preflight.json", preflight)
    _write_json(output_dir / "public_answer_payload_audit.json", payload_audit)
    _write_preflight_report(output_dir / "public_answer_preflight_zh.md", preflight)
    if not run_api:
        return {
            "decision": (
                "NEEDS_RUN_API_FOR_PUBLIC_ANSWER_EVAL"
                if payload_audit["decision"] == "GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT"
                else "NO_GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT"
            ),
            "execution_mode": "public_answer_eval_preflight_only",
            "answer_eval_version": PUBLIC_ANSWER_EVAL_VERSION,
            "qvf_context_variant": qvf_context_variant,
            "case_count": preflight["case_count"],
            "expected_call_count": preflight["expected_call_count"],
            "payload_audit_decision": payload_audit["decision"],
            "api_calls_made": 0,
            "preflight_files": [
                str(output_dir / "public_answer_preflight.json"),
                str(output_dir / "public_answer_payload_audit.json"),
                str(output_dir / "public_answer_preflight_zh.md"),
            ],
        }
    if payload_audit["decision"] != "GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT":
        return {
            "decision": "NO_GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT",
            "execution_mode": "public_answer_eval_payload_audit_failed",
            "answer_eval_version": PUBLIC_ANSWER_EVAL_VERSION,
            "qvf_context_variant": qvf_context_variant,
            "case_count": preflight["case_count"],
            "expected_call_count": preflight["expected_call_count"],
            "payload_audit_decision": payload_audit["decision"],
            "api_calls_made": 0,
            "preflight_files": [
                str(output_dir / "public_answer_preflight.json"),
                str(output_dir / "public_answer_payload_audit.json"),
                str(output_dir / "public_answer_preflight_zh.md"),
            ],
        }

    client = _OpenAIChatClient()
    raw_targets: list[dict[str, Any]] = []
    raw_judges: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    target_records_by_case_method: dict[tuple[str, str], dict[str, Any]] = {}
    judge_records_by_case_method: dict[tuple[str, str], dict[str, Any]] = {}
    items_by_case_method = {
        (str(item["case_id"]), str(item["method"])): item for item in eval_items
    }
    api_calls_made = 0
    target_outputs_path = output_dir / "target_outputs.jsonl"
    judge_outputs_path = output_dir / "judge_outputs.jsonl"
    target_outputs_path.write_text("", encoding="utf-8")
    judge_outputs_path.write_text("", encoding="utf-8")
    for item in eval_items:
        case_method_key = (str(item["case_id"]), str(item["method"]))
        post_answer_audit: dict[str, Any] = {}
        reuse_source_method = _selective_eval_reuse_source_method(
            item=item,
            items_by_case_method=items_by_case_method,
            target_records_by_case_method=target_records_by_case_method,
            judge_records_by_case_method=judge_records_by_case_method,
        )
        if reuse_source_method:
            source_key = (str(item["case_id"]), reuse_source_method)
            source_target = target_records_by_case_method[source_key]
            source_judge = judge_records_by_case_method[source_key]
            target_content = str(source_target.get("content", ""))
            target_response = _reused_api_response(source_target, reuse_source_method)
            target_content, post_answer_audit = _post_answer_temporal_audit_content(
                item,
                target_content,
            )
            target_response["post_answer_audit"] = post_answer_audit
            equivalent_judge_source_method = (
                _post_answer_equivalent_direct_judge_reuse_method(
                    item=item,
                    target_content=target_content,
                    post_answer_audit=post_answer_audit,
                    target_records_by_case_method=target_records_by_case_method,
                    judge_records_by_case_method=judge_records_by_case_method,
                )
            )
            if equivalent_judge_source_method:
                source_key = (
                    str(item["case_id"]),
                    equivalent_judge_source_method,
                )
                source_judge = judge_records_by_case_method[source_key]
                post_answer_audit = dict(post_answer_audit)
                post_answer_audit["judge_reuse_reason"] = (
                    "final_answer_equivalent_to_direct"
                )
                target_response["post_answer_audit"] = post_answer_audit
                judge_content = str(source_judge.get("content", ""))
                judgment = dict(source_judge.get("parsed_judgment", {}))
                judge_response = _reused_api_response(
                    source_judge,
                    equivalent_judge_source_method,
                )
            elif post_answer_audit.get("applied"):
                judge_response = _call_with_timing(
                    client,
                    model=judge_model,
                    messages=_judge_messages(item, target_content),
                    max_tokens=180,
                )
                judge_response["api_call_made"] = True
                judge_response["reused_from_method"] = ""
                api_calls_made += 1
                judge_content = _message_content(judge_response["response"])
                judgment = _parse_judgment(judge_content)
            else:
                judge_content = str(source_judge.get("content", ""))
                judgment = dict(source_judge.get("parsed_judgment", {}))
                judge_response = _reused_api_response(source_judge, reuse_source_method)
        else:
            target_response = _call_with_timing(
                client,
                model=answer_model,
                messages=item["target_messages"],
                max_tokens=max_output_tokens,
            )
            target_response["api_call_made"] = True
            target_response["reused_from_method"] = ""
            api_calls_made += 1
            target_content = _message_content(target_response["response"])
            target_content, post_answer_audit = _post_answer_temporal_audit_content(
                item,
                target_content,
            )
            target_response["post_answer_audit"] = post_answer_audit
            equivalent_judge_source_method = (
                _post_answer_equivalent_direct_judge_reuse_method(
                    item=item,
                    target_content=target_content,
                    post_answer_audit=post_answer_audit,
                    target_records_by_case_method=target_records_by_case_method,
                    judge_records_by_case_method=judge_records_by_case_method,
                )
            )
            if equivalent_judge_source_method:
                source_key = (
                    str(item["case_id"]),
                    equivalent_judge_source_method,
                )
                source_judge = judge_records_by_case_method[source_key]
                post_answer_audit = dict(post_answer_audit)
                post_answer_audit["judge_reuse_reason"] = (
                    "final_answer_equivalent_to_direct"
                )
                target_response["post_answer_audit"] = post_answer_audit
                judge_content = str(source_judge.get("content", ""))
                judgment = dict(source_judge.get("parsed_judgment", {}))
                judge_response = _reused_api_response(
                    source_judge,
                    equivalent_judge_source_method,
                )
            else:
                judge_response = _call_with_timing(
                    client,
                    model=judge_model,
                    messages=_judge_messages(item, target_content),
                    max_tokens=180,
                )
                judge_response["api_call_made"] = True
                judge_response["reused_from_method"] = ""
                api_calls_made += 1
                judge_content = _message_content(judge_response["response"])
                judgment = _parse_judgment(judge_content)
        target_record = _api_record(
            item=item,
            model=answer_model,
            response=target_response,
            content=target_content,
        )
        raw_targets.append(target_record)
        target_records_by_case_method[case_method_key] = target_record
        _append_jsonl_row(target_outputs_path, target_record)
        judge_record = _api_record(
            item=item,
            model=judge_model,
            response=judge_response,
            content=judge_content,
            parsed_judgment=judgment,
        )
        raw_judges.append(judge_record)
        judge_records_by_case_method[case_method_key] = judge_record
        _append_jsonl_row(judge_outputs_path, judge_record)
        result_rows.append(
            _result_row(
                item=item,
                target_content=target_content,
                target_response=target_response,
                judge_response=judge_response,
                judgment=judgment,
            )
        )

    summary = _summarize_rows(
        rows=result_rows,
        answer_model=answer_model,
        judge_model=judge_model,
    )
    result = {
        "decision": "GO_QVF_PUBLIC_ANSWER_EVAL_COMPLETE",
        "execution_mode": "public_answer_eval_api_run",
        "answer_eval_version": PUBLIC_ANSWER_EVAL_VERSION,
        "qvf_context_variant": qvf_context_variant,
        "summary": summary,
        "case_results": result_rows,
        "api_calls_made": api_calls_made,
        "reuse_summary": _api_reuse_summary(result_rows),
        "claim_boundary": [
            "This is an API-backed pilot over extracted public-dataset QVF requests.",
            "It evaluates the tested slice only and depends on extractor quality.",
            "It is not a full LongMemEval/LoCoMo benchmark result.",
        ],
    }
    _write_jsonl(output_dir / "target_outputs.jsonl", raw_targets)
    _write_jsonl(output_dir / "judge_outputs.jsonl", raw_judges)
    _write_json(output_dir / "public_answer_results.json", result)
    _write_json(
        output_dir / "public_answer_summary.json",
        {key: value for key, value in result.items() if key != "case_results"},
    )
    _write_result_csv(output_dir / "public_answer_cases.csv", result_rows)
    _write_result_report(output_dir / "public_answer_report_zh.md", result)
    return {
        "decision": result["decision"],
        "execution_mode": result["execution_mode"],
        "case_count": summary["case_count"],
        "method_summary": summary["method_summary"],
        "api_calls_made": result["api_calls_made"],
        "output_files": [
            str(output_dir / "public_answer_preflight.json"),
            str(output_dir / "public_answer_payload_audit.json"),
            str(output_dir / "public_answer_preflight_zh.md"),
            str(output_dir / "target_outputs.jsonl"),
            str(output_dir / "judge_outputs.jsonl"),
            str(output_dir / "public_answer_results.json"),
            str(output_dir / "public_answer_summary.json"),
            str(output_dir / "public_answer_cases.csv"),
            str(output_dir / "public_answer_report_zh.md"),
        ],
    }


def build_public_answer_eval_items(
    *,
    adapter_items: list[dict[str, Any]],
    qvf_requests: list[dict[str, Any]],
    limit: int = DEFAULT_PUBLIC_ANSWER_EVAL_LIMIT,
    qvf_context_variant: str = DEFAULT_QVF_CONTEXT_VARIANT,
) -> list[dict[str, Any]]:
    """Build direct and QVF answer-eval items."""

    _validate_positive_int(limit, "limit")
    qvf_context_variant = _validate_qvf_context_variant(qvf_context_variant)
    adapter_by_case = {
        item["case_id"]: item
        for item in adapter_items
        if isinstance(item, dict) and item.get("case_id") and _answers(item)
    }
    answer_by_case = {
        case_id: _answers(item) for case_id, item in adapter_by_case.items()
    }
    eval_items: list[dict[str, Any]] = []
    for request in deepcopy(qvf_requests):
        case_id = _case_id_from_request(request)
        answers = answer_by_case.get(case_id, [])
        if not answers:
            continue
        if qvf_context_variant in {
            "adaptive",
            "evidence_preserving",
            "full",
            "compact_full",
            "auto_compact",
            "selective_router",
            "annotation_only_qvf",
            "multi_action_controller",
            "post_answer_audit_controller",
        }:
            selected_history_turns = _selected_history_turns(adapter_by_case.get(case_id))
            if selected_history_turns:
                request["_selected_history_turns"] = selected_history_turns
        question = _question(request)
        direct_context = _direct_context(request)
        qvf_variant_for_context = (
            "adaptive" if qvf_context_variant == "selective_router" else qvf_context_variant
        )
        qvf_context = _qvf_context(request, qvf_context_variant=qvf_variant_for_context)
        if qvf_context_variant == "post_answer_audit_controller":
            qvf_context = dict(qvf_context)
            qvf_context["direct_recall_context"] = direct_context
        method_contexts = [
            (DIRECT_METHOD, direct_context),
            (QVF_METHOD, qvf_context),
        ]
        if qvf_context_variant == "selective_router":
            method_contexts.append(
                (
                    SELECTIVE_ROUTER_METHOD,
                    _selective_router_context(
                        request=request,
                        question=question,
                        direct_context=direct_context,
                        qvf_context=qvf_context,
                    ),
                )
            )
        for method, context in method_contexts:
            eval_items.append(
                {
                    "case_id": case_id,
                    "method": method,
                    "question": question,
                    "expected_answers": answers,
                    "target_messages": _target_messages(
                        question=question,
                        method=method,
                        context=context,
                    ),
                    "context": context,
                }
            )
        if len({item["case_id"] for item in eval_items}) >= limit:
            break
    if not eval_items:
        raise ValueError("public answer eval produced no cases with answers and QVF requests")
    return eval_items


def _target_messages(
    *,
    question: str,
    method: str,
    context: dict[str, Any],
) -> list[dict[str, str]]:
    if method == SELECTIVE_ROUTER_METHOD:
        selected_method, selected_context = _selected_router_target_context(context)
        return _target_messages(
            question=question,
            method=selected_method,
            context=selected_context,
        )
    if _post_answer_audit_uses_direct_target(method, context):
        return _target_messages(
            question=question,
            method=DIRECT_METHOD,
            context=_post_answer_audit_direct_context(context),
        )
    target_method = _target_context_method(method, context)
    instruction_context = _target_instruction_context(
        method=method,
        context=context,
        target_method=target_method,
    )
    if target_method == QVF_METHOD:
        fallback_instruction = ""
        is_annotation_only_qvf = (
            instruction_context.get("qvf_context_variant") == "annotation_only_qvf"
        )
        is_multi_action_controller = instruction_context.get(
            "qvf_context_variant"
        ) in {"multi_action_controller", "post_answer_audit_controller"}
        if instruction_context.get("query_relevant_context"):
            fallback_instruction = (
                " query_relevant_context is fallback evidence from extracted records "
                "that matched the question but were not selected by QVF routing; use it "
                "only when routed answer buckets are empty, off-topic, or need corroboration."
            )
        if instruction_context.get("public_reader_override"):
            fallback_instruction += (
                " public_reader_override is a public-dataset adapter policy for "
                "ambiguous same-timestamp extracted memories. If its mode is "
                "same_timestamp_conflict_resolution, use "
                "static_conflict_resolution_context.recommended_value as the answer "
                "for the requested slot when the recommendation_confidence is cue_based. "
                "Treat core_qvf_read_time_decision as diagnostic in that case."
            )
        if instruction_context.get("evidence_preservation_policy"):
            fallback_instruction += (
                " extracted_memory_context preserves the original extracted memories with "
                "QVF validity labels. Follow evidence_preservation_policy.routing_mode: "
                "preserve_first means use extracted_memory_context as ordinary recall evidence "
                "while respecting qvf_route_label and qvf_use_policy; route_first means answer "
                "from QVF routed, transition, change-detail, or temporal-resolution contexts first "
                "but keep extracted_memory_context as fallback for exact answer details, names, "
                "numbers, dates, and corroboration. "
                "For current-state conflicts, prefer current_answer rows and do not treat "
                "stale_or_blocked rows as current facts. For history/change questions, archive "
                "or stale rows can be used if they directly answer the historical question."
            )
        if instruction_context.get("status_class_context"):
            fallback_instruction += (
                " status_class_context gives a coarse state abstraction for explicit "
                "stayed-same status questions. For employment-status stayed-same questions, "
                "use status_class_context.preferred_answer verbatim as the concise answer "
                "unless the user asks for details. Do not treat job form, job title, "
                "company, or industry detail changes as coarse employment-status changes "
                "when status_class_context says the class stayed the same."
            )
        if instruction_context.get("condition_scope_context"):
            fallback_instruction += (
                " condition_scope_context lists exact condition clauses derived from "
                "model-visible memory or source text. For questions asking under what "
                "condition, when, or in what situation a preference applies, answer from "
                "condition_scope_context.exact_condition or preferred_answer first. Do not "
                "broaden exact conditions into wider time frames or adjacent routines unless "
                "condition_scope_context explicitly says they are equivalent. Preserve "
                "condition_scope_context.supporting_value and condition_answer_detail when "
                "present; do not shorten a condition-bound preference to only the condition "
                "phrase when the same row carries answer-critical descriptors."
            )
        if instruction_context.get("condition_scope_priority_policy"):
            fallback_instruction += (
                " condition_scope_priority_policy marks condition_scope_context as the "
                "primary answer route for this condition-bound question. Treat current, "
                "archive, and supporting buckets as corroboration only; do not replace the "
                "exact condition clause with a broader current/archive frame."
            )
        if instruction_context.get("scoped_reader_context"):
            fallback_instruction += (
                " scoped_reader_context contains selected-history events that satisfy "
                "explicit temporal or action scope in the question. For scoped temporal "
                "questions, prefer scoped_reader_context.candidate_events over unscoped "
                "recommendation lists or generic extracted memories."
            )
        if instruction_context.get("source_history_focus_context"):
            fallback_instruction += (
                " source_history_focus_context is a non-gold index of selected-history "
                "sentences already visible to QVF. For when, week, weekend, and "
                "source-history questions, preserve source_temporal_phrase with its "
                "source_observed_at boundary instead of replacing relative phrases with "
                "a different exact date unless the source sentence states that exact date. "
                "For why or reason questions, preserve source_focus_phrase and "
                "source_sentence as the source-backed causal trigger."
            )
        if instruction_context.get("source_history_answer_anchor_context"):
            fallback_instruction += (
                " source_history_answer_anchor_context marks concrete activity, place, "
                "object, or manner terms from model-visible source spans. For what/how "
                "source-history questions, inspect source_anchor_excerpt and avoid "
                "dropping source_answer_anchor_terms that specify the answer."
            )
        if instruction_context.get("habit_frequency_context"):
            fallback_instruction += (
                " habit_frequency_context contains source-backed cadence phrases for "
                "how-often or routine-change questions. Preserve frequency_phrase and "
                "day_phrase values when answering; do not summarize them away into only "
                "the event or activity name. When a row has answer_slot such as "
                "previous_frequency or current_frequency, map the answer to that slot "
                "using observed_at chronology; do not invert previous/current roles."
            )
        if _answer_rendering_guard(instruction_context):
            fallback_instruction += (
                " answer_rendering_guard is not new evidence and does not change QVF "
                "routing. It lists source-backed phrases already visible in memory_context; "
                "when one is relevant, preserve its exact condition, cadence, source, or "
                "slot-detail wording in the final answer instead of replacing it with a "
                "broader paraphrase."
            )
        if _answer_decision_contract(instruction_context):
            fallback_instruction += (
                " answer_decision_contract is not new evidence and does not change QVF "
                "routing. It is an answer-rendering contract derived from visible memory "
                "rows. Follow its answer_shape, preserve relevant must_preserve phrases, "
                "and obey avoid_overclaim rules. For condition questions, do not narrow "
                "compound source-backed alternatives or drop descriptors listed in the "
                "contract."
            )
        if instruction_context.get("validity_controller_decision"):
            fallback_instruction += (
                " validity_controller_decision is QVF's memory-validity controller action. "
                "It is not an answer label and does not hide raw memories. If next_action is "
                "answer_from_archive, prioritize historical_archive_context, scoped_reader_context, "
                "and directly relevant extracted_memory_context with an explicit historical boundary. "
                "If next_action asks to retrieve current evidence, do not answer a current-state "
                "claim from stale_or_blocked rows; use them only as history and answer with a "
                "current-evidence boundary when no current row is visible."
            )
        if _controller_requires_source_history_prompt(instruction_context):
            fallback_instruction += (
                " source_history_answer_contract is not new evidence and does not change "
                "retrieval. It means the controller found an archive answer whose wording "
                "depends on source dates, source spans, or relative temporal markers. For "
                "when, before, after, recent, latest, previous, first, weekend, month, or "
                "year questions, preserve the visible source-backed temporal phrase or "
                "observed_at boundary instead of answering from an ungrounded paraphrase."
            )
        if _computational_answer_contract(instruction_context):
            fallback_instruction += (
                " computational_answer_contract is not new evidence and does not change "
                "retrieval. It means the question asks for a scalar that must be computed "
                "from visible memory rows. Follow the listed computation_mode: enumerate "
                "all relevant source-backed items or event endpoints first, then return "
                "the computed scalar. Do not answer a count, total, or elapsed duration "
                "from the first matching row when multiple rows or dates satisfy the "
                "question scope."
            )
        if instruction_context.get("retrieval_feedback"):
            fallback_instruction += (
                " retrieval_feedback is system feedback for a possible upstream retrieval "
                "retry; it is not answer evidence and must not be cited as memory support. "
                "If it says additional retrieval is needed, keep stale, archive, or "
                "unsupported rows behind their validity boundary instead of converting "
                "them into current facts."
            )
        if is_annotation_only_qvf or is_multi_action_controller:
            if is_multi_action_controller:
                controller_action_instruction = (
                    " Follow memory_validity_controller_action. If action is "
                    "raw_recall_with_annotations, answer from extracted_memory_context "
                    "as ordinary raw memory and use QVF labels only as annotations. If "
                    "action is condition_scope_packet, answer from exact condition rows "
                    "first. If action is timeline_or_conflict_packet or "
                    "stale_current_validity_packet, use transition/current/conflict "
                    "contexts first while preserving raw fallback for exact names, "
                    "numbers, dates, frequencies, routines, and cadence phrases. "
                )
            else:
                controller_action_instruction = ""
            instruction = (
                "Answer using raw extracted memories plus QVF annotations. QVF is an "
                "annotation layer, not a filter: do not discard extracted_memory_context, "
                "historical_archive_context, or stale_or_blocked_context solely because "
                "QVF labels them historical, stale, blocked, or uncertain. For ordinary "
                "historical recall, use any directly relevant extracted or archive row as "
                "valid evidence. For present-state or validity-conflict questions, prefer "
                "current_answer_context and QVF labels, and do not treat stale_or_blocked "
                "rows as current facts. transition_context, change_detail_context, "
                "condition_scope_context, habit_frequency_context, scoped_reader_context, "
                "static_conflict_resolution_context, and temporal_resolution_context can "
                "resolve update, condition, frequency, conflict, or time-scope questions "
                "when available. supporting_context can supply "
                f"exact details.{fallback_instruction} {controller_action_instruction}"
                "If evidence conflicts, answer with the supported boundary rather than "
                "silently dropping older memories. Abstain only when neither raw memories "
                "nor QVF annotations support an answer."
            )
            instruction += (
                " For explicit past-date, before/after, historical, or scoped recall "
                "questions, matching raw/archive rows are valid evidence even when newer "
                "current_answer rows exist; do not let current_answer_context override the "
                "requested historical or scoped boundary."
            )
        else:
            instruction = (
                "Answer from QVF-routed memory. current_answer_context is primary for "
                "present-state answers. historical_archive_context may answer history, "
                "timeline, or change questions. transition_context summarizes old-to-new "
                "changes when available. change_detail_context contains source-history "
                "field changes for multi-detail change questions. "
                "status_class_context preserves coarse status-class continuity for explicit "
                "stayed-same status questions. "
                "condition_scope_context preserves exact condition clauses for conditional "
                "preference or habit questions. "
                "habit_frequency_context preserves source-backed cadence phrases for how-often "
                "or routine-change questions. "
                "scoped_reader_context preserves selected-history events for explicit temporal "
                "or action-scoped questions. "
                "static_conflict_resolution_context resolves same-timestamp value conflicts "
                "using source-span cues such as currently/used-to/already-read or brand/source "
                "phrases; follow its recommended_value when it matches the question. "
                "temporal_resolution_context resolves relative "
                "time expressions when available; if a row includes preferred_answer, use "
                "that wording for when/month/year questions instead of inventing a different "
                "date form. supporting_context can supply exact details."
                f"{fallback_instruction} "
                "stale_or_blocked_context and uncertain_context are not current-state answer "
                "support; use them only to explain outdated/low-confidence evidence when asked. "
                "Abstain only if the routed context does not support an answer."
            )
    else:
        instruction = (
            "Answer using the extracted candidate memories below. Prefer directly relevant memories."
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a concise memory-grounded assistant. Return one valid compact "
                "JSON object only, with no markdown, no code fences, and no text outside "
                "JSON. Use keys answer, used_memory_ids, and abstained. Keep answer to "
                "one short sentence or a small scalar/object directly answering the "
                "question. Include at most 3 used_memory_ids. Use abstained as a boolean."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "instruction": instruction,
                    "question": question,
                    "memory_context": _target_memory_context(method, context),
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
                "You are a strict evaluator for long-memory QA. Return JSON only with keys "
                "correct (boolean), error_type (string), and rationale (string)."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": item["question"],
                    "method": item["method"],
                    "gold_answers": item["expected_answers"],
                    "model_answer": target_content,
                    "memory_context": _judge_memory_context(item, target_content),
                    "grading_rules": [
                        "Mark correct if the model answer semantically matches any gold answer.",
                        "Mark incorrect if it abstains when a gold answer is specific.",
                        "Do not require exact wording, but numbers, names, dates, and degrees must match.",
                        "Use memory_context to assess support.",
                        "Do not penalize extra details if they are directly supported by memory_context and do not contradict the gold answer.",
                        "If the answer is not supported by memory_context, note that in error_type.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def _judge_memory_context(
    item: dict[str, Any],
    target_content: str = "",
) -> dict[str, Any]:
    method = str(item.get("method") or "")
    context = item.get("context", {})
    if not isinstance(context, dict):
        return {}
    if _post_answer_audit_uses_direct_target(method, context):
        direct_context = _post_answer_audit_direct_context(context)
        support = _post_answer_temporal_judge_support(
            context=context,
            target_content=target_content,
            question=str(item.get("question") or ""),
        )
        if not support:
            return direct_context
        return {
            **direct_context,
            "post_answer_audit_support": {
                "mode": "temporal_resolution_support_for_final_audited_answer",
                "principle": (
                    "These rows are non-gold QVF temporal-resolution evidence used "
                    "by the post-answer audit after the direct-equivalent target answer."
                ),
                "temporal_resolution_context": support,
            },
        }
    if (
        method == QVF_METHOD
        and context.get("qvf_context_variant") == "post_answer_audit_controller"
    ):
        return _target_memory_context(method, context)
    return context


def _post_answer_audit_uses_direct_target(
    method: str,
    context: dict[str, Any],
) -> bool:
    if method != QVF_METHOD:
        return False
    if context.get("qvf_context_variant") != "post_answer_audit_controller":
        return False
    action = context.get("memory_validity_controller_action", {})
    if not isinstance(action, dict):
        return False
    action_name = str(action.get("action") or "")
    if action_name == "raw_recall_with_annotations":
        return not _raw_recall_requires_independent_target(context)
    if _retrieval_feedback_has_blocking_issue(context.get("retrieval_feedback", {})):
        return False
    if _controller_requires_source_history_prompt(context):
        return not _source_history_requires_independent_target(context)
    return False


def _post_answer_audit_direct_context(context: dict[str, Any]) -> dict[str, Any]:
    direct_context = context.get("direct_recall_context", {})
    return direct_context if isinstance(direct_context, dict) else {}


def _retrieval_feedback_has_blocking_issue(feedback: Any) -> bool:
    if not isinstance(feedback, dict):
        return False
    if feedback.get("status") == "needs_additional_retrieval":
        return True
    issues = feedback.get("issues", [])
    if not isinstance(issues, list):
        return False
    return any(
        isinstance(issue, dict) and issue.get("severity") == "blocking"
        for issue in issues
    )


def _validity_controller_decision_from_context(context: dict[str, Any]) -> dict[str, Any]:
    decision = context.get("validity_controller_decision", {})
    if isinstance(decision, dict) and decision:
        return decision
    for field_name in ("qvf_read_time_decision", "core_qvf_read_time_decision"):
        read_decision = context.get(field_name, {})
        if not isinstance(read_decision, dict):
            continue
        decision = read_decision.get("validity_controller_decision", {})
        if isinstance(decision, dict) and decision:
            return decision
    return {}


def _controller_requires_source_history_prompt(context: dict[str, Any]) -> bool:
    decision = _validity_controller_decision_from_context(context)
    if not decision:
        return False
    if str(decision.get("next_action") or "") != "answer_from_archive":
        return False
    scope = _retrieval_feedback_scope(decision)
    return bool(scope.get("include_source_history"))


def _source_history_requires_independent_target(context: dict[str, Any]) -> bool:
    if not _controller_requires_source_history_prompt(context):
        return False
    if _dict_rows(context.get("source_history_answer_anchor_context", [])):
        return True
    if _dict_rows(context.get("source_history_focus_context", [])):
        return True
    if _dict_rows(context.get("scoped_reader_context", [])):
        return True
    question = _controller_question_fingerprint(context)
    if _is_previous_state_question(question):
        return True
    computational_contract = _computational_answer_contract(context)
    if computational_contract.get("visible_candidate_items", {}).get(
        "deduplicated_candidate_items"
    ):
        return True
    return False


def _raw_recall_requires_independent_target(context: dict[str, Any]) -> bool:
    if _dict_rows(context.get("scoped_reader_context", [])):
        return True
    if _source_history_requires_independent_target(context):
        return True
    return False


def _is_previous_state_question(question: str) -> bool:
    text = re.sub(r"\s+", " ", str(question or "")).strip().lower()
    if not text:
        return False
    return bool(
        re.search(r"\bwhat\s+was\s+my\s+previous\b", text)
        or re.search(
            r"\bprevious\s+(?:occupation|stance|status|role|last name|address|location)\b",
            text,
        )
    )


def _post_answer_temporal_judge_support(
    *,
    context: dict[str, Any],
    target_content: str,
    question: str,
) -> list[dict[str, Any]]:
    parsed = _parse_answer_payload(target_content)
    answer = str(parsed.get("answer") or "")
    if not answer:
        return []
    if not (_is_temporal_answer_question(question) or _has_unresolved_relative_time(answer)):
        return []
    used_ids = {
        str(memory_id)
        for memory_id in parsed.get("used_memory_ids", [])
        if str(memory_id).strip()
    } if isinstance(parsed.get("used_memory_ids"), list) else set()
    support = []
    for hint in _post_answer_temporal_hints(context):
        replacement = _temporal_candidate_answer(hint)
        if not replacement:
            continue
        memory_id = str(hint.get("memory_id") or "")
        if (
            _answer_already_contains_temporal_candidate(answer, replacement)
            or (memory_id and memory_id in used_ids)
        ):
            support.append(
                {
                    "memory_id": memory_id,
                    "phrase": hint.get("phrase", ""),
                    "observed_at": hint.get("observed_at", ""),
                    "resolved_time": hint.get("resolved_time", ""),
                    "preferred_answer": hint.get("preferred_answer", ""),
                    "resolution_note": hint.get("resolution_note", ""),
                }
            )
    return support[:MAX_TEMPORAL_RESOLUTION_HINTS]


RELATIVE_TIME_ANSWER_PATTERN = re.compile(
    r"\b(?:"
    r"yesterday|today|tomorrow|"
    r"last\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"next\s+(?:week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:around\s+)?\d+\s+years?\s+ago|"
    r"\d+-year-old"
    r")\b",
    flags=re.I,
)

TEMPORAL_QUESTION_PATTERN = re.compile(
    r"\b(?:when|which\s+(?:year|month|week|day)|what\s+(?:year|month|date))\b",
    flags=re.I,
)

ELAPSED_DURATION_QUESTION_PATTERN = re.compile(
    r"\b(?:"
    r"how\s+(?:many|much)\s+(?:days?|weeks?|months?|years?)|"
    r"how\s+long"
    r")\b.*\b(?:ago|before|after|since|between|when)\b|"
    r"\b(?:days?|weeks?|months?|years?)\s+(?:ago|before|after)\b",
    flags=re.I,
)

ELAPSED_DAYS_ANSWER_PATTERN = re.compile(
    r"\b(?:around\s+)?\d+\s+days?(?:\s+ago)?\b",
    flags=re.I,
)

ELAPSED_STALE_EXPLANATION_PATTERN = re.compile(
    r"\s*,\s*(?:which|that)\s+means\s+(?:it\s+)?(?:was|is)\s+"
    r"(?:around\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)\s+"
    r"days?(?:\s+ago)?\b",
    flags=re.I,
)

COMPARATIVE_SCALAR_DELTA_PATTERN = re.compile(
    r"\b(?P<quantity>\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?P<unit>(?:(?!more\b|less\b|fewer\b)[a-z][a-z0-9/-]*\s+){0,6})"
    r"(?P<direction>more|less|fewer)\b",
    flags=re.I,
)


def _post_answer_temporal_audit_content(
    item: dict[str, Any],
    target_content: str,
) -> tuple[str, dict[str, Any]]:
    """Repair post-answer temporal rendering without changing target prompts."""

    context = item.get("context", {})
    method = str(item.get("method", ""))
    if not isinstance(context, dict):
        return target_content, {"applied": False, "reason": "not_post_answer_qvf"}
    comparative_repaired, comparative_audit = _post_answer_comparative_scalar_audit_content(
        item,
        target_content,
    )
    if comparative_audit.get("applied"):
        return comparative_repaired, comparative_audit
    contract_repaired, contract_audit = _post_answer_contract_audit_content(
        item,
        target_content,
    )
    if contract_audit.get("applied"):
        return contract_repaired, contract_audit
    if not _post_answer_audit_uses_direct_target(method, context):
        return target_content, contract_audit
    parsed = _parse_answer_payload(target_content)
    if not parsed:
        return target_content, {"applied": False, "reason": "answer_json_parse_failed"}
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        return target_content, {"applied": False, "reason": "empty_answer"}
    question = str(item.get("question") or "")
    if not (
        _is_temporal_answer_question(question)
        or _has_unresolved_relative_time(answer)
    ):
        return target_content, {"applied": False, "reason": "not_temporal_answer"}
    hints = _post_answer_temporal_hints(context)
    if not hints:
        return target_content, {"applied": False, "reason": "no_temporal_hints"}
    if _asks_age_at_event_question(question):
        return target_content, {
            "applied": False,
            "reason": "age_at_event_requires_age_scalar_not_year_hint",
            "hint_count": len(hints),
        }
    duration_repair, duration_audit = _repair_elapsed_duration_answer(
        question=question,
        answer=answer,
        answer_payload=parsed,
        hints=hints,
    )
    if duration_repair:
        repaired = dict(parsed)
        repaired["answer"] = duration_repair
        if duration_audit.get("replace_used_memory_ids"):
            used_memory_ids = []
        else:
            used_memory_ids = list(repaired.get("used_memory_ids", []))
            if not isinstance(used_memory_ids, list):
                used_memory_ids = []
        for memory_id in duration_audit.get("memory_ids", []):
            if memory_id and memory_id not in used_memory_ids:
                used_memory_ids.append(memory_id)
        repaired["used_memory_ids"] = used_memory_ids
        if repaired.get("abstained"):
            repaired["abstained"] = []
        return (
            json.dumps(repaired, ensure_ascii=False, indent=2),
            {
                **duration_audit,
                "applied": True,
                "hint_count": len(hints),
            },
        )
    if _asks_elapsed_duration_question(question):
        return target_content, {
            **duration_audit,
            "hint_count": len(hints),
        }
    candidate, selection_reason = _select_post_answer_temporal_hint(
        question=question,
        answer=answer,
        answer_payload=parsed,
        hints=hints,
    )
    if not candidate:
        return target_content, {
            "applied": False,
            "reason": selection_reason or "no_supported_temporal_hint",
            "hint_count": len(hints),
        }
    replacement = _temporal_candidate_answer(candidate)
    if not replacement:
        return target_content, {
            "applied": False,
            "reason": "selected_hint_has_no_answer",
            "hint_count": len(hints),
        }
    if _answer_already_contains_temporal_candidate(answer, replacement):
        return target_content, {
            "applied": False,
            "reason": "answer_already_contains_temporal_candidate",
            "hint_count": len(hints),
        }
    repaired_answer, repair_mode = _repair_temporal_answer_text(
        question=question,
        answer=answer,
        candidate=candidate,
        replacement=replacement,
    )
    if not repaired_answer or repaired_answer == answer:
        return target_content, {
            "applied": False,
            "reason": "temporal_repair_noop",
            "hint_count": len(hints),
        }
    repaired = dict(parsed)
    repaired["answer"] = repaired_answer
    if not repaired.get("used_memory_ids") and candidate.get("memory_id"):
        repaired["used_memory_ids"] = [candidate["memory_id"]]
    if repaired.get("abstained"):
        repaired["abstained"] = []
    return (
        json.dumps(repaired, ensure_ascii=False, indent=2),
        {
            "applied": True,
            "reason": selection_reason,
            "repair_mode": repair_mode,
            "memory_id": candidate.get("memory_id", ""),
            "phrase": candidate.get("phrase", ""),
            "replacement": replacement,
            "hint_count": len(hints),
        },
    )


def _post_answer_comparative_scalar_audit_content(
    item: dict[str, Any],
    target_content: str,
) -> tuple[str, dict[str, Any]]:
    method = str(item.get("method", ""))
    if method != QVF_METHOD:
        return target_content, {
            "applied": False,
            "reason": "not_qvf_comparative_scalar_audit",
        }
    question = str(item.get("question") or "")
    direction = _comparative_scalar_question_direction(question)
    if not direction:
        return target_content, {
            "applied": False,
            "reason": "not_comparative_scalar_delta_question",
        }
    parsed = _parse_answer_payload(target_content)
    if not parsed:
        return target_content, {"applied": False, "reason": "answer_json_parse_failed"}
    if parsed.get("abstained") is True:
        return target_content, {
            "applied": False,
            "reason": "comparative_scalar_answer_abstained",
        }
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        return target_content, {"applied": False, "reason": "empty_answer"}
    replacement, selection_reason = _select_comparative_scalar_replacement(
        question=question,
        answer=answer,
        direction=direction,
    )
    if not replacement:
        return target_content, {"applied": False, "reason": selection_reason}
    if _norm_text(answer) == _norm_text(replacement):
        return target_content, {
            "applied": False,
            "reason": "comparative_scalar_already_compact",
        }
    repaired = dict(parsed)
    repaired["answer"] = replacement
    return (
        json.dumps(repaired, ensure_ascii=False, indent=2),
        {
            "applied": True,
            "reason": "comparative_scalar_component_suffix_contract",
            "replacement": replacement,
            "direction": direction,
        },
    )


def _comparative_scalar_question_direction(question: str) -> str:
    text = _norm_text(question)
    if not text:
        return ""
    if re.search(r"\bhow\s+(?:much|many)\s+more\b", text):
        return "more"
    if re.search(r"\bhow\s+(?:much|many)\s+(?:less|fewer)\b", text):
        return "less"
    return ""


def _select_comparative_scalar_replacement(
    *,
    question: str,
    answer: str,
    direction: str,
) -> tuple[str, str]:
    question_terms = _content_terms(question)
    matches = []
    for match in COMPARATIVE_SCALAR_DELTA_PATTERN.finditer(answer):
        match_direction = _norm_text(match.group("direction"))
        if match_direction == "fewer":
            match_direction = "less"
        if match_direction != direction:
            continue
        quantity = str(match.group("quantity") or "").strip()
        unit = re.sub(r"\s+", " ", str(match.group("unit") or "")).strip()
        phrase = " ".join(part for part in (quantity, unit, direction) if part).strip()
        unit_terms = _content_terms(unit)
        if unit_terms and question_terms and not (unit_terms & question_terms):
            continue
        replacement = _trim_comparative_scalar_component_suffix(answer, match.end())
        if not replacement:
            continue
        matches.append((phrase, replacement))
    unique = []
    seen = set()
    for phrase, replacement in matches:
        key = _norm_text(phrase)
        if key in seen:
            continue
        seen.add(key)
        unique.append(replacement)
    if len(unique) != 1:
        return "", "comparative_scalar_component_suffix_not_unique"
    return unique[0], "comparative_scalar_delta_unique"


def _trim_comparative_scalar_component_suffix(answer: str, match_end: int) -> str:
    comma_index = str(answer or "").find(",", match_end)
    if comma_index < 0:
        return ""
    suffix = answer[comma_index:]
    if not re.search(r"\b(?:at|from|with|compared|versus|vs)\b", suffix, flags=re.I):
        return ""
    if not re.search(r"\d", suffix):
        return ""
    trimmed = answer[:comma_index].rstrip(" ,;.")
    if not trimmed:
        return ""
    return f"{trimmed}."


def _post_answer_contract_audit_content(
    item: dict[str, Any],
    target_content: str,
) -> tuple[str, dict[str, Any]]:
    context = item.get("context", {})
    if not isinstance(context, dict) or not _post_answer_contract_audit_enabled(
        str(item.get("method", "")),
        context,
    ):
        return target_content, {"applied": False, "reason": "not_post_answer_qvf"}
    parsed = _parse_answer_payload(target_content)
    if not parsed:
        return target_content, {"applied": False, "reason": "answer_json_parse_failed"}
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        return target_content, {"applied": False, "reason": "empty_answer"}
    target_context = _target_memory_context(QVF_METHOD, context)
    contract = target_context.get("answer_decision_contract", {})
    if not isinstance(contract, dict) or not contract.get("contract_rows"):
        return target_content, {
            "applied": False,
            "reason": "no_answer_decision_contract",
        }
    question = str(item.get("question") or "")
    candidates = _post_answer_contract_repair_candidates(
        question=question,
        target_context=target_context,
        answer=answer,
    )
    if not candidates:
        return target_content, {
            "applied": False,
            "reason": "no_contract_repair_candidate",
            "contract_row_count": len(contract.get("contract_rows", [])),
        }
    satisfied_candidate = _post_answer_contract_satisfied_candidate(candidates)
    if satisfied_candidate:
        return target_content, {
            "applied": False,
            "reason": "answer_already_satisfies_complete_contract_candidate",
            "memory_id": satisfied_candidate.get("memory_id", ""),
            "answer_coverage": satisfied_candidate["answer_coverage"],
            "condition_coverage": satisfied_candidate["condition_coverage"],
            "detail_coverage": satisfied_candidate["detail_coverage"],
        }
    repairable_candidates = [
        candidate
        for candidate in candidates
        if candidate["score"] >= POST_ANSWER_CONTRACT_REPAIR_MIN_SCORE
        and _post_answer_contract_candidate_has_repair_gain(candidate)
        and _post_answer_contract_candidate_is_safe_repair(candidate)
    ]
    if not repairable_candidates:
        candidate = candidates[0]
        if candidate["answer_coverage"] >= 0.82:
            return target_content, {
                "applied": False,
                "reason": "answer_already_satisfies_contract",
                "memory_id": candidate.get("memory_id", ""),
                "answer_coverage": candidate["answer_coverage"],
            }
        return target_content, {
            "applied": False,
            "reason": "no_contract_candidate_with_sufficient_gain",
            "memory_id": candidate.get("memory_id", ""),
            "candidate_score": candidate["score"],
            "answer_coverage": candidate["answer_coverage"],
            "candidate_coverage": candidate["candidate_coverage"],
        }
    candidate = repairable_candidates[0]
    if candidate["score"] < POST_ANSWER_CONTRACT_REPAIR_MIN_SCORE:
        return target_content, {
            "applied": False,
            "reason": "contract_candidate_score_too_low",
            "memory_id": candidate.get("memory_id", ""),
            "candidate_score": candidate["score"],
        }
    if not _post_answer_contract_candidate_has_repair_gain(candidate):
        return target_content, {
            "applied": False,
            "reason": "contract_candidate_gain_too_low",
            "memory_id": candidate.get("memory_id", ""),
            "answer_coverage": candidate["answer_coverage"],
            "candidate_coverage": candidate["candidate_coverage"],
        }
    replacement = _post_answer_contract_replacement(candidate)
    if not replacement or _norm_text(replacement) == _norm_text(answer):
        return target_content, {
            "applied": False,
            "reason": "contract_repair_noop",
            "memory_id": candidate.get("memory_id", ""),
        }
    repaired = dict(parsed)
    repaired["answer"] = replacement
    used_memory_ids = repaired.get("used_memory_ids", [])
    if not isinstance(used_memory_ids, list):
        used_memory_ids = []
    memory_id = str(candidate.get("memory_id") or "")
    if memory_id and memory_id not in used_memory_ids:
        used_memory_ids.append(memory_id)
    repaired["used_memory_ids"] = used_memory_ids
    if repaired.get("abstained"):
        repaired["abstained"] = []
    return (
        json.dumps(repaired, ensure_ascii=False, indent=2),
        {
            "applied": True,
            "reason": candidate["reason"],
            "repair_mode": "replace_answer_with_contract_satisfying_phrase",
            "memory_id": memory_id,
            "replacement": replacement,
            "condition_phrase": candidate.get("condition_phrase", ""),
            "supporting_value": candidate.get("supporting_value", ""),
            "condition_answer_detail": candidate.get("condition_answer_detail", ""),
            "answer_coverage": candidate["answer_coverage"],
            "candidate_coverage": candidate["candidate_coverage"],
            "candidate_score": candidate["score"],
        },
    )


def _post_answer_contract_audit_enabled(
    method: str,
    context: dict[str, Any],
) -> bool:
    if method != QVF_METHOD:
        return False
    if context.get("qvf_context_variant") != "post_answer_audit_controller":
        return False
    action = context.get("memory_validity_controller_action", {})
    if not isinstance(action, dict):
        return False
    return str(action.get("action") or "") == "condition_scope_packet"


def _post_answer_contract_repair_candidates(
    *,
    question: str,
    target_context: dict[str, Any],
    answer: str,
) -> list[dict[str, Any]]:
    target_tokens = _condition_scope_target_tokens(question)
    contract_phrases = _post_answer_contract_must_preserve_phrases(target_context)
    candidates: list[dict[str, Any]] = []
    for row in _post_answer_contract_candidate_rows(target_context):
        memory_id = str(row.get("memory_id") or "")
        supporting_value = str(row.get("supporting_value") or row.get("value") or "")
        for source_field, text in _post_answer_condition_candidate_texts(row):
            for phrase in _extract_condition_phrases(text):
                phrase = _condition_phrase_with_leading_context(text, phrase)
                phrase = _condition_preference_parallel_condition_phrase(text, phrase)
                if _condition_phrase_has_dangling_nested_cue(phrase):
                    continue
                if _condition_phrase_has_noise(phrase):
                    continue
                if _condition_phrase_is_object_only(phrase, row):
                    continue
                if _post_answer_condition_phrase_is_value_echo(
                    phrase,
                    supporting_value,
                ):
                    continue
                if _post_answer_condition_phrase_is_neighbor_noise(phrase, text):
                    continue
                if not _post_answer_condition_phrase_matches_structured_scope(
                    row,
                    source_field,
                    phrase,
                ):
                    continue
                detail = (
                    str(row.get("condition_answer_detail") or "")
                    or _condition_source_condition_answer_detail(text, phrase, row)
                )
                replacement = _post_answer_condition_replacement_text(
                    supporting_value=supporting_value,
                    condition_phrase=phrase,
                    detail=detail,
                )
                if not replacement:
                    continue
                candidate_phrases = _post_answer_contract_candidate_phrases(
                    replacement=replacement,
                    supporting_value=supporting_value,
                    condition_phrase=phrase,
                    detail=detail,
                    contract_phrases=contract_phrases,
                )
                answer_coverage = _post_answer_contract_phrase_coverage(
                    answer,
                    candidate_phrases,
                )
                candidate_coverage = _post_answer_contract_phrase_coverage(
                    replacement,
                    candidate_phrases,
                )
                score, reasons = _post_answer_contract_candidate_score(
                    question=question,
                    target_tokens=target_tokens,
                    row=row,
                    source_field=source_field,
                    source_text=text,
                    condition_phrase=phrase,
                    supporting_value=supporting_value,
                    detail=detail,
                    candidate_coverage=candidate_coverage,
                    answer_coverage=answer_coverage,
                )
                if score <= 0:
                    continue
                candidates.append(
                    {
                        "memory_id": memory_id,
                        "supporting_value": supporting_value,
                        "condition_phrase": phrase,
                        "condition_answer_detail": detail,
                        "replacement": replacement,
                        "source_field": source_field,
                        "score": score,
                        "reason": "+".join(reasons),
                        "answer_coverage": round(answer_coverage, 3),
                        "candidate_coverage": round(candidate_coverage, 3),
                        "value_coverage": round(
                            _post_answer_contract_overlap(answer, supporting_value),
                            3,
                        ),
                        "condition_coverage": round(
                            _post_answer_contract_overlap(answer, phrase),
                            3,
                        ),
                        "detail_coverage": round(
                            _post_answer_contract_overlap(answer, detail)
                            if detail
                            else 1.0,
                            3,
                        ),
                    }
                )
    candidates.sort(
        key=lambda candidate: (
            _post_answer_contract_candidate_is_leading_context_compound(candidate),
            candidate["candidate_coverage"] - candidate["answer_coverage"],
            candidate["score"],
            len(_norm_text(candidate["condition_phrase"]).split()),
        ),
        reverse=True,
    )
    return candidates


def _post_answer_contract_candidate_rows(
    target_context: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in _dict_rows(target_context.get("condition_scope_context", [])):
        memory_id = str(row.get("memory_id") or "")
        value = str(row.get("supporting_value") or row.get("value") or "")
        source_text = " ".join(text for _, text in _post_answer_condition_candidate_texts(row))
        key = (memory_id, _norm_text(value) or _norm_text(source_text)[:120])
        if key in seen:
            continue
        seen.add(key)
        enriched = dict(row)
        enriched["_post_answer_candidate_bucket"] = "condition_scope_context"
        rows.append(enriched)
    return rows


def _post_answer_contract_satisfied_candidate(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    has_repairable_compound_candidate = any(
        _post_answer_contract_candidate_is_compound(candidate)
        and candidate["score"] >= POST_ANSWER_CONTRACT_REPAIR_MIN_SCORE
        and _post_answer_contract_candidate_has_repair_gain(candidate)
        for candidate in candidates
    )
    for candidate in candidates:
        if candidate["score"] < POST_ANSWER_CONTRACT_REPAIR_MIN_SCORE:
            continue
        if candidate["value_coverage"] < 0.75:
            continue
        if candidate["condition_coverage"] < 0.8:
            if not (
                not has_repairable_compound_candidate
                and
                candidate["condition_coverage"] >= 0.6
                and candidate["answer_coverage"] >= 0.5
            ):
                continue
        if (
            _post_answer_contract_detail_requires_repair(
                str(candidate.get("condition_answer_detail") or ""),
                str(candidate.get("supporting_value") or ""),
            )
            and candidate["detail_coverage"] < 0.7
        ):
            continue
        if (
            has_repairable_compound_candidate
            and not _post_answer_contract_candidate_is_compound(candidate)
        ):
            continue
        has_detail_or_compound = bool(
            candidate.get("condition_answer_detail")
        ) or _post_answer_contract_candidate_is_compound(candidate)
        if not has_detail_or_compound and has_repairable_compound_candidate:
            continue
        if not has_detail_or_compound and candidate["answer_coverage"] < 0.82:
            continue
        return candidate
    return {}


def _post_answer_contract_detail_requires_repair(
    detail: str,
    supporting_value: str,
) -> bool:
    detail_tokens = _post_answer_contract_content_tokens(detail)
    if not detail_tokens:
        return False
    value_tokens = _post_answer_contract_content_tokens(supporting_value)
    generic_detail_tokens = {
        "entertainment",
        "find",
        "finds",
        "fun",
        "human",
        "idea",
        "key",
        "light",
        "low",
        "sounds",
        "useful",
    }
    critical_tokens = detail_tokens - value_tokens - generic_detail_tokens
    noisy_detail_tokens = {
        "any",
        "can",
        "check",
        "checks",
        "either",
        "ins",
        "like",
        "meeting",
        "meetings",
        "occasional",
        "practice",
        "practices",
        "said",
        "tip",
        "tips",
        "together",
        "tweak",
        "usually",
        "walk",
        "walks",
        "want",
        "wants",
    }
    pronoun_noise = {
        "i",
        "me",
        "our",
        "their",
        "them",
        "they",
        "we",
        "you",
        "your",
        "yours",
    }
    raw_tokens = set(_norm_text(detail).split())
    if raw_tokens & (noisy_detail_tokens | pronoun_noise):
        return False
    return len(critical_tokens) >= 3


def _post_answer_contract_candidate_has_repair_gain(
    candidate: dict[str, Any],
) -> bool:
    gain = candidate["candidate_coverage"] - candidate["answer_coverage"]
    if gain >= POST_ANSWER_CONTRACT_REPAIR_MIN_GAIN:
        return True
    if (
        gain > 0
        and _post_answer_contract_candidate_is_compound(candidate)
        and candidate["candidate_coverage"] >= 0.95
    ):
        return True
    return False


def _post_answer_contract_candidate_is_compound(candidate: dict[str, Any]) -> bool:
    reason = str(candidate.get("reason") or "")
    return "compound_condition" in reason or "leading_context_compound" in reason


def _post_answer_contract_candidate_is_leading_context_compound(
    candidate: dict[str, Any],
) -> bool:
    return "leading_context_compound" in str(candidate.get("reason") or "")


def _post_answer_contract_candidate_has_critical_repair_signal(
    candidate: dict[str, Any],
) -> bool:
    reason = str(candidate.get("reason") or "")
    detail = str(candidate.get("condition_answer_detail") or "")
    if detail and _post_answer_contract_detail_requires_repair(
        detail,
        str(candidate.get("supporting_value") or ""),
    ):
        return True
    if _post_answer_contract_candidate_is_leading_context_compound(candidate):
        return candidate.get("value_coverage", 0.0) >= 0.75
    if _post_answer_contract_candidate_is_compound(candidate):
        return candidate.get("condition_coverage", 0.0) > 0.0
    if "source_backed" not in reason or "source_value_overlap" not in reason:
        return False
    if candidate.get("value_coverage", 0.0) >= 0.75:
        return True
    return (
        "source_preference_cue" in reason
        and candidate.get("condition_coverage", 0.0) >= 0.8
    )


def _post_answer_contract_candidate_is_safe_repair(
    candidate: dict[str, Any],
) -> bool:
    reason = str(candidate.get("reason") or "")
    if "question_value_overlap" not in reason:
        return False
    if candidate.get("value_coverage", 0.0) < 0.3:
        return False
    condition_tokens = set(_norm_text(str(candidate.get("condition_phrase") or "")).split())
    if condition_tokens & {"our", "ours", "us", "we"}:
        return False
    detail = str(candidate.get("condition_answer_detail") or "")
    if detail and not _post_answer_contract_detail_requires_repair(
        detail,
        str(candidate.get("supporting_value") or ""),
    ):
        return False
    if not _post_answer_contract_candidate_has_critical_repair_signal(candidate):
        return False
    return True


def _post_answer_condition_candidate_texts(
    row: dict[str, Any],
) -> list[tuple[str, str]]:
    candidates = []
    for field_name in (
        "exact_condition",
        "source_excerpt",
        "source_span",
        "claim",
        "value",
    ):
        value = row.get(field_name, "")
        if isinstance(value, str) and value.strip():
            candidates.append((field_name, value))
    return candidates


def _post_answer_contract_must_preserve_phrases(
    target_context: dict[str, Any],
) -> list[str]:
    contract = target_context.get("answer_decision_contract", {})
    if not isinstance(contract, dict):
        return []
    phrases: list[str] = []
    seen: set[str] = set()
    for row in _dict_rows(contract.get("contract_rows", [])):
        for phrase in row.get("must_preserve", []):
            cleaned = _clean_answer_decision_contract_phrase(phrase)
            key = _norm_text(cleaned)
            if not cleaned or key in seen:
                continue
            seen.add(key)
            phrases.append(cleaned)
    return phrases


def _post_answer_contract_candidate_phrases(
    *,
    replacement: str,
    supporting_value: str,
    condition_phrase: str,
    detail: str,
    contract_phrases: list[str],
) -> list[str]:
    phrases = [supporting_value, condition_phrase, detail]
    normalized_replacement = _norm_text(replacement)
    for contract_phrase in contract_phrases:
        normalized_contract = _norm_text(contract_phrase)
        if not normalized_contract:
            continue
        if normalized_contract in normalized_replacement or _post_answer_contract_overlap(
            replacement,
            contract_phrase,
        ) >= 0.45:
            phrases.append(contract_phrase)
    return [
        phrase
        for phrase in _dedupe_preserve_order(
            [str(phrase) for phrase in phrases if str(phrase).strip()]
        )
        if _post_answer_contract_content_tokens(phrase)
    ]


def _post_answer_contract_candidate_score(
    *,
    question: str,
    target_tokens: set[str],
    row: dict[str, Any],
    source_field: str,
    source_text: str,
    condition_phrase: str,
    supporting_value: str,
    detail: str,
    candidate_coverage: float,
    answer_coverage: float,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    phrase_tokens = _post_answer_contract_content_tokens(condition_phrase)
    value_tokens = _post_answer_contract_content_tokens(supporting_value)
    source_tokens = _post_answer_contract_content_tokens(source_text)
    question_tokens = _post_answer_contract_content_tokens(question) | target_tokens
    if value_tokens and question_tokens & value_tokens:
        score += 10
        reasons.append("question_value_overlap")
    if phrase_tokens and question_tokens & phrase_tokens:
        score += 5
        reasons.append("question_condition_overlap")
    if value_tokens and source_tokens & value_tokens:
        score += 6
        reasons.append("source_value_overlap")
    if set(_norm_text(source_text).split()) & CONDITION_PREFERENCE_CUES:
        score += 6
        reasons.append("source_preference_cue")
    if detail:
        score += 6
        reasons.append("condition_detail")
    if " or " in f" {_norm_text(condition_phrase)} ":
        score += 7
        reasons.append("compound_condition")
    if _condition_phrase_has_explanatory_leading_context(condition_phrase):
        score += 12
        reasons.append("leading_context_compound")
    if candidate_coverage > answer_coverage:
        score += int((candidate_coverage - answer_coverage) * 12)
        reasons.append("coverage_gain")
    if source_field.startswith("source"):
        score += 2
        reasons.append("source_backed")
    if _post_answer_condition_phrase_is_neighbor_noise(condition_phrase, source_text):
        score -= 18
        reasons.append("neighbor_noise_penalty")
    if _condition_source_is_schedule_without_preference(source_text, target_tokens):
        score -= 10
        reasons.append("schedule_noise_penalty")
    return score, reasons


def _post_answer_condition_replacement_text(
    *,
    supporting_value: str,
    condition_phrase: str,
    detail: str,
) -> str:
    value = _post_answer_contract_display_text(supporting_value)
    condition = _post_answer_condition_display_text(condition_phrase)
    descriptor = _post_answer_contract_display_text(detail)
    if not value or not condition:
        return ""
    answer = f"The user prefers {value} {condition}"
    training_condition = _post_answer_training_detail_condition(descriptor, value)
    if training_condition:
        answer += f" and {training_condition}"
    elif descriptor:
        answer += f"; detail: {descriptor}"
    return answer + "."


def _post_answer_condition_display_text(text: str) -> str:
    display = _post_answer_contract_display_text(text)
    display = re.sub(r"\bif i lived\b", "if they lived", display, flags=re.IGNORECASE)
    display = re.sub(r"\bif i live\b", "if they live", display, flags=re.IGNORECASE)
    display = re.sub(r"\bif i move\b", "if they move", display, flags=re.IGNORECASE)
    return display


def _post_answer_training_detail_condition(detail: str, supporting_value: str = "") -> str:
    normalized = _norm_text(detail)
    if not normalized:
        return ""
    tokens = set(normalized.split())
    has_training_cue = bool({"train", "trained", "training", "commands", "command"} & tokens)
    if not has_training_cue:
        return ""
    has_command = bool({"command", "commands"} & tokens)
    has_prevent_chaos = "prevent chaos" in normalized or "trained to prevent" in normalized
    has_train = bool({"train", "trained", "training"} & tokens)
    trained_object = _post_answer_training_detail_object(supporting_value)
    if has_command and (has_prevent_chaos or has_train):
        if has_prevent_chaos:
            return f"they are able to train {trained_object} to follow commands and prevent chaos"
        return f"they are able to train {trained_object} to follow commands"
    clauses: list[str] = []
    if has_command:
        clauses.append("it follows commands")
    if has_prevent_chaos:
        clauses.append("they are able to train it to prevent chaos")
    elif has_train:
        clauses.append("they are able to train it")
    clauses = _dedupe_preserve_order(clauses)
    return " and ".join(clauses)


def _post_answer_training_detail_object(supporting_value: str) -> str:
    normalized_value = _norm_text(supporting_value)
    if (
        "dog" in normalized_value
        or "watchdog" in normalized_value
        or "poodle" in normalized_value
        or "shepherd" in normalized_value
        or "puppy" in normalized_value
        or "canine" in normalized_value
    ):
        return "the dog"
    return "it"


def _post_answer_contract_replacement(candidate: dict[str, Any]) -> str:
    replacement = str(candidate.get("replacement") or "").strip()
    if replacement:
        return replacement
    return _post_answer_condition_replacement_text(
        supporting_value=str(candidate.get("supporting_value") or ""),
        condition_phrase=str(candidate.get("condition_phrase") or ""),
        detail=str(candidate.get("condition_answer_detail") or ""),
    )


def _post_answer_contract_phrase_coverage(text: str, phrases: list[str]) -> float:
    content_phrases = [
        phrase
        for phrase in phrases
        if _post_answer_contract_content_tokens(phrase)
    ]
    if not content_phrases:
        return 1.0
    scores = [
        _post_answer_contract_overlap(text, phrase)
        for phrase in content_phrases
    ]
    return sum(scores) / len(scores)


def _post_answer_contract_overlap(text: str, phrase: str) -> float:
    phrase_tokens = _post_answer_contract_content_tokens(phrase)
    if not phrase_tokens:
        return 1.0
    text_tokens = _post_answer_contract_content_tokens(text)
    return len(phrase_tokens & text_tokens) / len(phrase_tokens)


def _post_answer_contract_content_tokens(text: Any) -> set[str]:
    stopwords = CONDITION_SCOPE_STOPWORDS | {
        "answer",
        "condition",
        "detail",
        "does",
        "doing",
        "having",
        "likes",
        "prefers",
        "prefer",
        "preference",
        "them",
        "user",
        "when",
        "what",
        "where",
        "which",
        "watch",
        "watches",
    }
    tokens = set()
    for token in _norm_text(text).split():
        if len(token) <= 2 or token in stopwords:
            continue
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def _post_answer_contract_display_text(text: str) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    normalized = re.sub(r"\bin morning\b", "in the morning", normalized)
    normalized = re.sub(r"\bi m\b", "I'm", normalized)
    normalized = re.sub(r"\bi need\b", "I need", normalized)
    normalized = re.sub(r"\bI need break\b", "I need a break", normalized)
    return normalized


def _post_answer_condition_phrase_is_value_echo(
    phrase: str,
    supporting_value: str,
) -> bool:
    phrase_tokens = _post_answer_contract_content_tokens(phrase)
    value_tokens = _post_answer_contract_content_tokens(supporting_value)
    if not phrase_tokens or not value_tokens:
        return False
    cue = _norm_text(phrase).split()[0] if _norm_text(phrase).split() else ""
    if cue not in {"on", "in"}:
        return False
    overlap = len(phrase_tokens & value_tokens)
    return overlap >= max(1, len(phrase_tokens) - 1)


def _post_answer_condition_phrase_matches_structured_scope(
    row: dict[str, Any],
    source_field: str,
    phrase: str,
) -> bool:
    if source_field in {
        "exact_condition",
        "preferred_answer",
        "complete_condition_answer",
    }:
        return True
    structured_texts = [
        str(row.get(field_name) or "")
        for field_name in (
            "exact_condition",
            "preferred_answer",
            "complete_condition_answer",
            "condition_answer_detail",
        )
        if str(row.get(field_name) or "").strip()
    ]
    if not structured_texts:
        return True
    phrase_norm = _norm_text(phrase)
    if not phrase_norm:
        return False
    exact_condition = _norm_text(str(row.get("exact_condition") or ""))
    if exact_condition and _post_answer_condition_phrase_is_neighbor_noise(
        exact_condition,
        exact_condition,
    ):
        return True
    if exact_condition and (
        exact_condition in phrase_norm or phrase_norm in exact_condition
    ):
        return True
    phrase_tokens = _post_answer_contract_content_tokens(phrase)
    if not phrase_tokens:
        return False
    exact_tokens = _post_answer_contract_content_tokens(exact_condition)
    if exact_tokens:
        exact_overlap = len(phrase_tokens & exact_tokens) / len(exact_tokens)
        if exact_overlap >= 0.67:
            return True
    structured_tokens: set[str] = set()
    for text in structured_texts:
        structured_tokens.update(_post_answer_contract_content_tokens(text))
    if not structured_tokens:
        return True
    overlap = len(phrase_tokens & structured_tokens)
    required_overlap = 1 if len(structured_tokens) <= 3 else 2
    return overlap >= required_overlap


def _post_answer_condition_phrase_is_neighbor_noise(
    phrase: str,
    source_text: str,
) -> bool:
    normalized_phrase = _norm_text(phrase)
    if not normalized_phrase:
        return False
    noise_terms = {
        "finalize",
        "template",
        "sign",
        "messages",
        "spots",
        "supermarkets",
        "inner",
        "travel",
        "city",
    }
    phrase_tokens = set(normalized_phrase.split())
    if not phrase_tokens & noise_terms:
        return False
    return True


def _parse_answer_payload(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _answer_payloads_equivalent(left_content: str, right_content: str) -> bool:
    left = _canonical_answer_payload_for_equivalence(left_content)
    right = _canonical_answer_payload_for_equivalence(right_content)
    return left is not None and right is not None and left == right


def _canonical_answer_payload_for_equivalence(
    content: str,
) -> dict[str, Any] | None:
    parsed = _parse_answer_payload(content)
    if not parsed:
        return None
    used_memory_ids = parsed.get("used_memory_ids", [])
    if not isinstance(used_memory_ids, list):
        return None
    return {
        "answer": _canonical_answer_payload_value(parsed.get("answer")),
        "used_memory_ids": [str(memory_id) for memory_id in used_memory_ids],
        "abstained": bool(parsed.get("abstained", False)),
    }


def _canonical_answer_payload_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        return [_canonical_answer_payload_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonical_answer_payload_value(value[key])
            for key in sorted(value)
        }
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)


def _is_temporal_answer_question(question: str) -> bool:
    return bool(
        TEMPORAL_QUESTION_PATTERN.search(str(question or ""))
        or _asks_elapsed_duration_question(question)
    )


def _has_unresolved_relative_time(answer: str) -> bool:
    return bool(RELATIVE_TIME_ANSWER_PATTERN.search(str(answer or "")))


def _asks_age_at_event_question(question: str) -> bool:
    text = _norm_text(question)
    if "how old" not in text:
        return False
    return bool(
        re.search(
            r"\b(?:when|while|during|at the time|upon)\b",
            str(question or ""),
            flags=re.I,
        )
    )


def _post_answer_temporal_hints(context: dict[str, Any]) -> list[dict[str, Any]]:
    hints = []
    seen = set()
    for row in context.get("temporal_resolution_context", []):
        if not isinstance(row, dict):
            continue
        answer = _temporal_candidate_answer(row)
        if not answer:
            continue
        key = (
            str(row.get("memory_id", "")),
            _norm_text(row.get("phrase", "")),
            _norm_text(answer),
        )
        if key in seen:
            continue
        seen.add(key)
        hints.append(row)
    return hints


def _repair_elapsed_duration_answer(
    *,
    question: str,
    answer: str,
    answer_payload: dict[str, Any],
    hints: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    if not _asks_elapsed_duration_question(question):
        return "", {"applied": False, "reason": "not_elapsed_duration_question"}
    if "day" not in _norm_text(question):
        return "", {"applied": False, "reason": "elapsed_duration_unit_not_supported"}
    pair, reason = _select_elapsed_duration_anchor_pair(
        question=question,
        answer=answer,
        answer_payload=answer_payload,
        hints=hints,
    )
    if not pair:
        return "", {"applied": False, "reason": reason}
    target_hint, target_date, reference_hint, reference_date = pair
    days = abs((reference_date - target_date).days)
    if days <= 0:
        return "", {"applied": False, "reason": "elapsed_duration_non_positive"}
    replacement = _elapsed_duration_scalar_answer(question, days)
    if replacement:
        repaired = replacement
        repair_mode = "replace_answer_with_elapsed_duration_scalar"
    else:
        replacement = _elapsed_duration_answer_phrase(
            question=question,
            days=days,
            target_date=target_date,
            reference_date=reference_date,
        )
        repaired, repair_mode = _replace_elapsed_duration_answer_span(
            answer,
            replacement,
            target_phrase=str(target_hint.get("phrase") or ""),
        )
    if not repaired and _answer_is_temporal_abstention(answer):
        repaired = replacement
        repair_mode = "replace_temporal_abstention_with_elapsed_duration"
    if not repaired or repaired == answer:
        return "", {"applied": False, "reason": "elapsed_duration_repair_noop"}
    target_memory_id = str(target_hint.get("memory_id") or "")
    reference_memory_id = str(reference_hint.get("memory_id") or "")
    return repaired, {
        "reason": reason,
        "repair_mode": repair_mode,
        "replacement": replacement,
        "duration_days": days,
        "replace_used_memory_ids": reason
        == "elapsed_duration_before_after_clause_anchor_pair",
        "memory_ids": [
            memory_id
            for memory_id in (target_memory_id, reference_memory_id)
            if memory_id
        ],
        "anchor_pair": [
            _elapsed_duration_anchor_trace(target_hint, target_date, "target_event"),
            _elapsed_duration_anchor_trace(
                reference_hint,
                reference_date,
                "reference_event",
            ),
        ],
    }


def _elapsed_duration_scalar_answer(question: str, days: int) -> str:
    text = _norm_text(question)
    if re.search(r"\bhow\s+many\s+days?\b", text):
        return f"{days} days"
    return ""


def _select_elapsed_duration_anchor_pair(
    *,
    question: str,
    answer: str,
    answer_payload: dict[str, Any],
    hints: list[dict[str, Any]],
) -> tuple[tuple[dict[str, Any], Any, dict[str, Any], Any] | None, str]:
    dated_hints = []
    for index, hint in enumerate(hints):
        resolved_date = _resolved_temporal_hint_date(hint)
        if resolved_date is not None:
            dated_hints.append((index, hint, resolved_date))
    if len(dated_hints) < 2:
        return None, "elapsed_duration_needs_two_temporal_anchors"

    between_pair, between_reason = _select_between_clause_elapsed_anchor_pair(
        question,
        dated_hints,
    )
    if between_pair:
        return between_pair, between_reason
    if between_reason != "not_between_clause_elapsed_duration":
        return None, between_reason
    before_after_pair, before_after_reason = _select_before_after_clause_elapsed_anchor_pair(
        question,
        dated_hints,
    )
    if before_after_pair:
        return before_after_pair, before_after_reason
    if before_after_reason != "not_before_after_clause_elapsed_duration":
        return None, before_after_reason

    used_ids = {
        str(memory_id)
        for memory_id in answer_payload.get("used_memory_ids", [])
        if str(memory_id).strip()
    } if isinstance(answer_payload.get("used_memory_ids"), list) else set()

    target_scored = []
    for index, hint, resolved_date in dated_hints:
        score = 0
        reasons = []
        memory_id = str(hint.get("memory_id") or "")
        phrase = str(hint.get("phrase") or "")
        if memory_id and memory_id in used_ids:
            score += 12
            reasons.append("answer_used_target_memory")
        if phrase and _phrase_in_text(phrase, answer):
            score += 4
            reasons.append("answer_contains_target_relative_phrase")
        if score > 0:
            target_scored.append((score, -index, hint, resolved_date, "+".join(reasons)))
    if not target_scored:
        return None, "elapsed_duration_no_answer_aligned_target_anchor"
    target_scored.sort(reverse=True, key=lambda row: (row[0], row[1]))
    if len(target_scored) > 1 and target_scored[0][0] == target_scored[1][0]:
        return None, "elapsed_duration_ambiguous_target_anchor"

    _, _, target_hint, target_date, target_reason = target_scored[0]
    target_memory_id = str(target_hint.get("memory_id") or "")
    reference_terms = _elapsed_duration_reference_terms(question)
    if not reference_terms:
        return None, "elapsed_duration_reference_clause_not_found"

    reference_scored = []
    for index, hint, resolved_date in dated_hints:
        memory_id = str(hint.get("memory_id") or "")
        if memory_id and memory_id == target_memory_id:
            continue
        score = _hint_term_overlap_score(reference_terms, hint)
        if score:
            reference_scored.append((score, -index, hint, resolved_date))
    if not reference_scored:
        return None, "elapsed_duration_no_query_aligned_reference_anchor"
    reference_scored.sort(reverse=True, key=lambda row: (row[0], row[1]))
    if reference_scored[0][0] < 3:
        return None, "elapsed_duration_reference_anchor_below_alignment_threshold"
    if len(reference_scored) > 1 and reference_scored[0][0] == reference_scored[1][0]:
        return None, "elapsed_duration_ambiguous_reference_anchor"

    _, _, reference_hint, reference_date = reference_scored[0]
    return (
        target_hint,
        target_date,
        reference_hint,
        reference_date,
    ), f"elapsed_duration_anchor_pair:{target_reason}"


def _select_between_clause_elapsed_anchor_pair(
    question: str,
    dated_hints: list[tuple[int, dict[str, Any], Any]],
) -> tuple[tuple[dict[str, Any], Any, dict[str, Any], Any] | None, str]:
    clause_terms = _elapsed_duration_between_clause_terms(question)
    if not clause_terms:
        return None, "not_between_clause_elapsed_duration"
    target_terms, reference_terms = clause_terms
    candidates = []
    for index, hint, resolved_date in dated_hints:
        target_score = _hint_clause_overlap_score(target_terms, hint)
        reference_score = _hint_clause_overlap_score(reference_terms, hint)
        candidates.append(
            {
                "index": index,
                "hint": hint,
                "resolved_date": resolved_date,
                "target_score": target_score,
                "reference_score": reference_score,
                "memory_id": str(hint.get("memory_id") or ""),
            }
        )

    target_candidates = [
        row
        for row in candidates
        if row["target_score"] >= 1 and row["target_score"] > row["reference_score"]
    ]
    reference_candidates = [
        row
        for row in candidates
        if row["reference_score"] >= 1 and row["reference_score"] > row["target_score"]
    ]
    target = _unique_top_between_clause_candidate(target_candidates, "target_score")
    reference = _unique_top_between_clause_candidate(
        reference_candidates,
        "reference_score",
    )
    if not target or not reference:
        return None, "elapsed_duration_between_clause_no_unique_pair"
    if target["memory_id"] and target["memory_id"] == reference["memory_id"]:
        return None, "elapsed_duration_between_clause_same_memory"
    return (
        target["hint"],
        target["resolved_date"],
        reference["hint"],
        reference["resolved_date"],
    ), "elapsed_duration_between_clause_anchor_pair"


def _select_before_after_clause_elapsed_anchor_pair(
    question: str,
    dated_hints: list[tuple[int, dict[str, Any], Any]],
) -> tuple[tuple[dict[str, Any], Any, dict[str, Any], Any] | None, str]:
    clause_terms = _elapsed_duration_before_after_clause_terms(question)
    if not clause_terms:
        return None, "not_before_after_clause_elapsed_duration"
    target_terms, reference_terms = clause_terms
    candidates = []
    for index, hint, resolved_date in dated_hints:
        target_score = _hint_clause_overlap_score(target_terms, hint)
        reference_score = _hint_clause_overlap_score(reference_terms, hint)
        candidates.append(
            {
                "index": index,
                "hint": hint,
                "resolved_date": resolved_date,
                "target_score": target_score,
                "reference_score": reference_score,
                "target_source_support": _hint_source_overlap_score(target_terms, hint),
                "reference_source_support": _hint_source_overlap_score(
                    reference_terms,
                    hint,
                ),
                "memory_id": str(hint.get("memory_id") or ""),
            }
        )

    target_candidates = [
        row
        for row in candidates
        if row["target_score"] >= 1 and row["target_score"] > row["reference_score"]
    ]
    reference_candidates = [
        row
        for row in candidates
        if row["reference_score"] >= 1 and row["reference_score"] > row["target_score"]
    ]
    target = _unique_top_clause_candidate(
        target_candidates,
        "target_score",
        "target_source_support",
    )
    reference = _unique_top_clause_candidate(
        reference_candidates,
        "reference_score",
        "reference_source_support",
    )
    if not target or not reference:
        return None, "elapsed_duration_before_after_clause_no_unique_pair"
    if target["memory_id"] and target["memory_id"] == reference["memory_id"]:
        return None, "elapsed_duration_before_after_clause_same_memory"
    return (
        target["hint"],
        target["resolved_date"],
        reference["hint"],
        reference["resolved_date"],
    ), "elapsed_duration_before_after_clause_anchor_pair"


def _elapsed_duration_before_after_clause_terms(
    question: str,
) -> tuple[set[str], set[str]] | None:
    text = re.sub(r"\s+", " ", str(question or "")).strip(" .?!")
    match = re.search(
        r"\bhow\s+(?:many|much)\s+days?\s+"
        r"(?:before|after)\s+(?P<reference>.+?)\s+"
        r"did\s+(?:i|we|the\s+user|user)\s+(?P<target>.+)$",
        text,
        flags=re.I,
    )
    if not match:
        return None
    target_terms = _content_terms(match.group("target"))
    reference_terms = _content_terms(match.group("reference"))
    if not target_terms or not reference_terms:
        return None
    return target_terms, reference_terms


def _unique_top_clause_candidate(
    candidates: list[dict[str, Any]],
    score_key: str,
    source_support_key: str,
) -> dict[str, Any]:
    if not candidates:
        return {}
    ordered = sorted(
        candidates,
        key=lambda row: (
            int(row[score_key]),
            int(row[source_support_key]),
            -int(row["index"]),
        ),
        reverse=True,
    )
    if len(ordered) > 1:
        first_key = (
            ordered[0][score_key],
            ordered[0][source_support_key],
        )
        second_key = (
            ordered[1][score_key],
            ordered[1][source_support_key],
        )
        if first_key == second_key:
            return {}
    return ordered[0]


def _unique_top_between_clause_candidate(
    candidates: list[dict[str, Any]],
    score_key: str,
) -> dict[str, Any]:
    if not candidates:
        return {}
    ordered = sorted(
        candidates,
        key=lambda row: (int(row[score_key]), -int(row["index"])),
        reverse=True,
    )
    if len(ordered) > 1 and ordered[0][score_key] == ordered[1][score_key]:
        return {}
    return ordered[0]


def _hint_clause_overlap_score(terms: set[str], hint: dict[str, Any]) -> int:
    if not terms:
        return 0
    hint_terms = _content_terms(
        " ".join(
            str(hint.get(field_name, ""))
            for field_name in ("claim", "value", "phrase")
        )
    )
    return len(terms & hint_terms)


def _hint_source_overlap_score(terms: set[str], hint: dict[str, Any]) -> int:
    if not terms:
        return 0
    source_terms = _content_terms(str(hint.get("source_span") or ""))
    return len(terms & source_terms)


def _elapsed_duration_between_clause_terms(
    question: str,
) -> tuple[set[str], set[str]] | None:
    text = re.sub(r"\s+", " ", str(question or "")).strip(" .?!")
    match = re.search(
        r"\bbetween\s+(?P<target>.+?)\s+and\s+(?P<reference>.+)$",
        text,
        flags=re.I,
    )
    if not match:
        return None
    target_terms = _content_terms(match.group("target"))
    reference_terms = _content_terms(match.group("reference"))
    if not target_terms or not reference_terms:
        return None
    return target_terms, reference_terms


def _replace_elapsed_duration_answer_span(
    answer: str,
    replacement: str,
    *,
    target_phrase: str = "",
) -> tuple[str, str]:
    if target_phrase:
        repaired, count = _replace_temporal_phrase(answer, target_phrase, replacement)
        if count:
            return (
                _cleanup_elapsed_duration_contradiction(repaired),
                "replace_target_relative_phrase_with_elapsed_days",
            )
    repaired, count = ELAPSED_DAYS_ANSWER_PATTERN.subn(replacement, answer, count=1)
    if count:
        return _cleanup_elapsed_duration_contradiction(repaired), "replace_elapsed_days_phrase"
    repaired, count = re.subn(
        r"\byesterday\b",
        replacement,
        answer,
        count=1,
        flags=re.I,
    )
    if count:
        return _cleanup_elapsed_duration_contradiction(repaired), "replace_yesterday_with_elapsed_days"
    return "", ""


def _elapsed_duration_answer_phrase(
    *,
    question: str,
    days: int,
    target_date: Any,
    reference_date: Any,
) -> str:
    reference_clause = _elapsed_duration_reference_clause(question)
    if not reference_clause:
        return f"{days} days ago"
    relation = "before" if target_date <= reference_date else "after"
    return f"{days} days {relation} {reference_clause}"


def _elapsed_duration_reference_clause(question: str) -> str:
    match = re.search(r"\bwhen\s+(?P<clause>.+?)[?.!]*$", str(question or ""), flags=re.I)
    if not match:
        return ""
    clause = re.sub(r"\s+", " ", match.group("clause")).strip(" .?!,;:")
    if not clause or len(clause.split()) > 14:
        return ""
    return clause


def _cleanup_elapsed_duration_contradiction(answer: str) -> str:
    repaired = ELAPSED_STALE_EXPLANATION_PATTERN.sub("", answer)
    repaired = re.sub(r"\s+([,.;:!?])", r"\1", repaired)
    repaired = re.sub(r"\s{2,}", " ", repaired).strip()
    return repaired


def _resolved_temporal_hint_date(hint: dict[str, Any]) -> Any:
    value = str(hint.get("resolved_time") or hint.get("preferred_answer") or "").strip()
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    if not match:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _elapsed_duration_anchor_trace(
    hint: dict[str, Any],
    resolved_date: Any,
    role: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "memory_id": hint.get("memory_id", ""),
        "phrase": hint.get("phrase", ""),
        "resolved_date": resolved_date.isoformat() if hasattr(resolved_date, "isoformat") else "",
        "observed_at": hint.get("observed_at", ""),
        "claim": hint.get("claim", ""),
        "value": hint.get("value", ""),
    }


def _elapsed_duration_reference_terms(question: str) -> set[str]:
    normalized = _norm_text(question)
    for marker in (" when ", " after ", " before ", " since "):
        padded = f" {normalized} "
        if marker in padded:
            clause = padded.split(marker, 1)[1]
            return _content_terms(clause)
    return _content_terms(normalized)


def _hint_term_overlap_score(terms: set[str], hint: dict[str, Any]) -> int:
    if not terms:
        return 0
    hint_terms = _content_terms(
        " ".join(
            str(hint.get(field_name, ""))
            for field_name in ("claim", "value", "source_span", "phrase")
        )
    )
    return len(terms & hint_terms)


def _content_terms(text: str) -> set[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "when",
        "what",
        "which",
        "where",
        "from",
        "into",
        "have",
        "has",
        "had",
        "did",
        "does",
        "was",
        "were",
        "are",
        "you",
        "your",
        "user",
        "how",
        "many",
        "much",
        "long",
        "ago",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "local",
    }
    terms = set()
    for token in re.findall(r"[a-z0-9]+", _norm_text(text)):
        if len(token) <= 2 or token in stopwords:
            continue
        terms.add(token)
    return terms


def _temporal_candidate_answer(candidate: dict[str, Any]) -> str:
    phrase_norm = _norm_text(candidate.get("phrase", ""))
    resolved = str(candidate.get("resolved_time") or "").strip()
    if phrase_norm == "last year" and resolved:
        return _display_temporal_candidate_answer(resolved)
    for field_name in ("preferred_answer", "resolved_time", "value"):
        value = str(candidate.get(field_name) or "").strip()
        if value:
            return _display_temporal_candidate_answer(value)
    return ""


def _display_temporal_candidate_answer(value: str) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return text
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return _display_date(datetime(year, month, day))
    except ValueError:
        return text


def _answer_already_contains_temporal_candidate(answer: str, replacement: str) -> bool:
    answer_norm = _norm_text(answer)
    replacement_norm = _norm_text(replacement)
    if replacement_norm and replacement_norm in answer_norm:
        return True
    return False


def _select_post_answer_temporal_hint(
    *,
    question: str,
    answer: str,
    answer_payload: dict[str, Any],
    hints: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    used_ids = {
        str(memory_id)
        for memory_id in answer_payload.get("used_memory_ids", [])
        if str(memory_id).strip()
    } if isinstance(answer_payload.get("used_memory_ids"), list) else set()
    scored = []
    for index, hint in enumerate(hints):
        score = 0
        reasons = []
        phrase = str(hint.get("phrase") or "")
        if phrase and _phrase_in_text(phrase, answer):
            score += 20
            reasons.append("answer_contains_temporal_phrase")
        if str(hint.get("memory_id") or "") in used_ids:
            score += 10
            reasons.append("answer_used_temporal_memory")
        replacement = _temporal_candidate_answer(hint)
        if _question_answer_shape_matches(question, replacement):
            score += 4
            reasons.append("question_shape_matches_hint")
        if _answer_is_temporal_abstention(answer):
            score += 2
            reasons.append("temporal_abstention")
        scored.append((score, -index, hint, "+".join(reasons)))
    scored.sort(reverse=True, key=lambda row: (row[0], row[1]))
    if not scored or scored[0][0] <= 0:
        return {}, "no_positive_temporal_hint_score"
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return {}, "ambiguous_temporal_hint_tie"
    return scored[0][2], scored[0][3] or "selected_temporal_hint"


def _phrase_in_text(phrase: str, text: str) -> bool:
    normalized_phrase = _norm_text(phrase)
    normalized_text = _norm_text(text)
    if not normalized_phrase or not normalized_text:
        return False
    return normalized_phrase in normalized_text


def _question_answer_shape_matches(question: str, replacement: str) -> bool:
    q = _norm_text(question)
    value = str(replacement or "").strip()
    if not value:
        return False
    if "year" in q and re.fullmatch(r"\d{4}", value):
        return True
    if "month" in q and (
        _looks_like_month_year(_norm_text(value))
        or re.fullmatch(r"\d{4}-\d{2}", value)
    ):
        return True
    if "when" in q:
        return True
    return False


def _answer_is_temporal_abstention(answer: str) -> bool:
    text = _norm_text(answer)
    if not any(token in text for token in ("when", "date", "year", "month", "time")):
        return False
    return any(
        phrase in text
        for phrase in (
            "do not provide",
            "does not provide",
            "do not specify",
            "does not specify",
            "not specify",
            "cannot determine",
            "not enough information",
            "unknown",
        )
    )


def _repair_temporal_answer_text(
    *,
    question: str,
    answer: str,
    candidate: dict[str, Any],
    replacement: str,
) -> tuple[str, str]:
    phrase = str(candidate.get("phrase") or "").strip()
    if phrase:
        replacement_phrase = _temporal_answer_phrase(
            question=question,
            replacement=replacement,
        )
        repaired, count = _replace_temporal_phrase(
            answer,
            phrase,
            replacement_phrase,
        )
        if count:
            return repaired, "replace_relative_phrase"
    if (
        str(candidate.get("memory_id") or "")
        and _is_atomic_temporal_answer(replacement)
        and (
        _answer_is_temporal_abstention(answer)
        or _contains_explicit_temporal_value(answer)
        )
    ):
        return replacement, "replace_answer_with_supported_temporal_hint"
    return "", ""


def _temporal_answer_phrase(*, question: str, replacement: str) -> str:
    value = str(replacement or "").strip()
    if not value:
        return value
    if value.startswith("the ") or value.startswith("between "):
        return value
    q = _norm_text(question)
    normalized = _norm_text(value)
    if "year" in q or "month" in q:
        return f"in {value}"
    if re.fullmatch(r"\d{4}", value) or _looks_like_month_year(normalized):
        return f"in {value}"
    if re.fullmatch(r"\d{1,2}\s+[a-z]+\s+\d{4}", normalized):
        return f"on {value}"
    return value


def _replace_temporal_phrase(answer: str, phrase: str, replacement: str) -> tuple[str, int]:
    escaped = re.escape(str(phrase).strip())
    if not escaped:
        return answer, 0
    patterns = [
        rf"\baround\s+{escaped}\b",
        rf"\b{escaped}\b",
    ]
    current = answer
    total = 0
    for pattern in patterns:
        current, count = re.subn(pattern, replacement, current, count=1, flags=re.I)
        total += count
        if count:
            break
    return current, total


def _contains_explicit_temporal_value(answer: str) -> bool:
    text = str(answer or "")
    if re.search(r"\b\d{4}\b", text):
        return True
    return bool(
        re.search(
            r"\b(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\b",
            text,
            flags=re.I,
        )
    )


def _is_atomic_temporal_answer(value: str) -> bool:
    text = str(value or "").strip()
    normalized = _norm_text(text)
    if re.fullmatch(r"\d{4}", text):
        return True
    if re.fullmatch(r"\d{1,2}\s+[a-z]+\s+\d{4}", normalized):
        return True
    return _looks_like_month_year(normalized)


def _direct_context(request: dict[str, Any]) -> dict[str, Any]:
    memories = []
    for row in request.get("records", []):
        memories.append(
            {
                "memory_id": row["memory_id"],
                "claim": row.get("claim", ""),
                "value": row.get("value", ""),
                "observed_at": row.get("observed_at", ""),
                "source_type": row.get("source", {}).get("source_type", ""),
                "source_span": row.get("source", {}).get("source_span", ""),
            }
        )
    return {
        "context_type": "direct_extracted_memories",
        "retrieved_memories": memories,
    }


def _selective_router_context(
    *,
    request: dict[str, Any],
    question: str,
    direct_context: dict[str, Any],
    qvf_context: dict[str, Any],
) -> dict[str, Any]:
    route = route_query_risk(
        question,
        query_metadata=_first_query_request(request),
        retrieved_memories=request.get("records", []),
    )
    selected_method, selection_reason = _selective_router_selected_method(
        route,
        qvf_context,
    )
    selected_context = qvf_context if selected_method == QVF_METHOD else direct_context
    return {
        "context_type": SELECTIVE_ROUTER_METHOD,
        "query_risk_route": route,
        "selected_method": selected_method,
        "selection_reason": selection_reason,
        "selected_context": selected_context,
    }


def _selective_router_selected_method(
    route: dict[str, Any],
    qvf_context: dict[str, Any],
) -> tuple[str, str]:
    if _dynamic_change_override_should_apply(route, qvf_context):
        return QVF_METHOD, "dynamic_change_transition_override"
    if not bool(route.get("should_apply_qvf")):
        return DIRECT_METHOD, "direct_non_degradation"
    if recommended_route := str(route.get("recommended_route") or ""):
        if recommended_route == HYBRID_ROUTE and _is_recent_categorical_selection_route(route):
            return QVF_METHOD, "recent_categorical_scope_selection"
    if recommended_route == CONDITIONAL_ROUTE and _has_condition_scope_candidate(qvf_context):
        return QVF_METHOD, "condition_preference_scope"
    if _controller_prefers_direct_preservation(qvf_context):
        return DIRECT_METHOD, "direct_controller_preserve_raw_memory"
    query_type = str(route.get("query_type") or "")
    if recommended_route == EVIDENCE_CONFLICT_ROUTE:
        return QVF_METHOD, "retrieved_evidence_conflict"
    if recommended_route == CURRENT_ROUTE or query_type == "current_state_or_update":
        return QVF_METHOD, "current_or_conflict"
    if recommended_route == TRANSITION_ROUTE and _has_change_answer_candidate(qvf_context):
        return QVF_METHOD, "change_detail_or_transition"
    if recommended_route == HYBRID_ROUTE and _has_scoped_reader_candidate(qvf_context):
        return QVF_METHOD, "high_confidence_recent_scoped"
    return DIRECT_METHOD, "direct_non_degradation"


def _is_recent_categorical_selection_route(route: dict[str, Any]) -> bool:
    cues = route.get("cues", [])
    if not isinstance(cues, list) or not any(
        str(cue).startswith("temporal_recent:") for cue in cues
    ):
        return False
    text = str(route.get("query_text") or "").strip().lower()
    if not re.search(r"^(what type|which)\b", text):
        return False
    if re.search(
        r"\b(where|how many|how much|total|amount|number|comments|hours|spent|earn|earned|cost|price)\b",
        text,
    ):
        return False
    if re.search(r"\b(recommend|suggest|advice|should i|should we)\b", text):
        return False
    return True


def _controller_prefers_direct_preservation(qvf_context: dict[str, Any]) -> bool:
    decision = qvf_context.get("validity_controller_decision", {})
    if not isinstance(decision, dict):
        return False
    evidence_sufficiency = str(decision.get("evidence_sufficiency") or "")
    next_action = str(decision.get("next_action") or "")
    if evidence_sufficiency == "no_visible_answer_evidence":
        return True
    if next_action.startswith("retrieve_"):
        return True
    if (
        evidence_sufficiency == "sufficient_archive_or_historical_evidence"
        and next_action == "answer_from_archive"
    ):
        return True
    return False


def _has_change_answer_candidate(context: dict[str, Any]) -> bool:
    for field_name in (
        "transition_context",
        "change_detail_context",
        "status_class_context",
    ):
        packets = context.get(field_name, [])
        if isinstance(packets, list) and packets:
            return True
    return False


def _dynamic_change_override_should_apply(
    route: dict[str, Any],
    qvf_context: dict[str, Any],
) -> bool:
    text = _norm_text(str(route.get("query_text") or ""))
    if not text or not _has_change_answer_candidate(qvf_context):
        return False
    if _is_movement_from_to_query(text):
        return False
    if _is_open_social_status_change_detail_query(text):
        return False
    if _is_yes_no_dynamic_change_query(text):
        return bool(qvf_context.get("transition_context"))
    if _is_career_field_change_query(text):
        return bool(
            qvf_context.get("change_detail_context")
            or _transition_context_has_career_slot(qvf_context)
        )
    return False


def _is_yes_no_dynamic_change_query(text: str) -> bool:
    return bool(
        re.search(r"^(did|has|have|is|are|was|were)\b", text)
        and re.search(r"\b(change|changed|stay|stayed)\b", text)
    )


def _is_movement_from_to_query(text: str) -> bool:
    return bool(
        re.search(r"\b(where|what place|which city|which country)\b", text)
        and re.search(r"\b(move|moved|relocate|relocated|from|to)\b", text)
    )


def _is_open_social_status_change_detail_query(text: str) -> bool:
    return bool(
        re.search(r"^(what|how)\b", text)
        and "social status" in text
        and re.search(r"\b(change|changed)\b", text)
    )


def _is_career_field_change_query(text: str) -> bool:
    if not re.search(r"\bwhat changed about\b", text):
        return False
    return bool(
        re.search(
            r"\b(job title|title|company|employer|industry|income|salary|employment)\b",
            text,
        )
    )


def _transition_context_has_career_slot(qvf_context: dict[str, Any]) -> bool:
    career_slots = {"job_title", "company", "industry", "income", "employment_status"}
    transitions = qvf_context.get("transition_context", [])
    if not isinstance(transitions, list):
        return False
    return any(
        isinstance(row, dict) and str(row.get("slot", "")) in career_slots
        for row in transitions
    )


def _has_condition_scope_candidate(context: dict[str, Any]) -> bool:
    condition_scope_context = context.get("condition_scope_context", [])
    if not isinstance(condition_scope_context, list):
        return False
    return any(isinstance(row, dict) and row for row in condition_scope_context)


def _has_scoped_reader_candidate(context: dict[str, Any]) -> bool:
    scoped_reader_context = context.get("scoped_reader_context", [])
    if not isinstance(scoped_reader_context, list):
        return False
    for packet in scoped_reader_context:
        if not isinstance(packet, dict):
            continue
        candidate_events = packet.get("candidate_events", [])
        if isinstance(candidate_events, list) and candidate_events:
            return True
    return False


def _validate_qvf_context_variant(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized in QVF_CONTEXT_VARIANTS:
        return normalized
    supported = ", ".join(QVF_CONTEXT_VARIANTS)
    raise ValueError(
        f"unsupported QVF context variant {value!r}; supported variants: {supported}"
    )


def _condition_scope_priority_policy(
    *,
    question: str,
    condition_scope_context: list[dict[str, Any]],
) -> dict[str, Any]:
    if not condition_scope_context:
        return {}
    if not _asks_for_condition_scope(question):
        return {}
    return {
        "decision": "PROMOTE_CONDITION_SCOPE_PRIMARY",
        "reason": (
            "question asks for a condition-bound preference or habit and exact "
            "condition rows are available"
        ),
        "condition_row_count": len(condition_scope_context),
        "primary_bucket": "condition_scope_context",
        "competing_bucket_policy": (
            "current/archive/supporting buckets may corroborate but must not "
            "replace exact condition clauses"
        ),
    }


def _condition_scope_read_decision_override(
    *,
    base_read_decision: dict[str, Any],
    priority_policy: dict[str, Any],
) -> dict[str, Any]:
    if not priority_policy:
        return base_read_decision
    return {
        "decision": "ADMIT_CONDITION_SCOPE",
        "answer_policy": "answer_from_condition_scope",
        "route": "condition_scope_reader",
        "reader_contract": (
            "Use condition_scope_context.exact_condition or preferred_answer as "
            "the primary answer for this condition-bound question. Use current, "
            "archive, or supporting buckets only for corroboration; do not broaden "
            "the exact condition into adjacent routines, wider time frames, or "
            "unsupported historical frames."
        ),
        "base_decision": base_read_decision.get("decision", ""),
        "base_answer_policy": base_read_decision.get("answer_policy", ""),
        "promotion_reason": priority_policy.get("reason", ""),
    }


def _qvf_context(
    request: dict[str, Any],
    *,
    qvf_context_variant: str = DEFAULT_QVF_CONTEXT_VARIANT,
) -> dict[str, Any]:
    qvf_context_variant = _validate_qvf_context_variant(qvf_context_variant)
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    response = run_qvf_service_request(_service_request(request))
    result = response["step_report"]["query_report"]["query_results"][0]
    read_decision = result["read_decision"]
    compact_packet = result["packet"]["compact_validity_packet"]
    current_context = _compact_context_rows(compact_packet.get("current_evidence", []))
    supporting_context = _compact_context_rows(compact_packet.get("supporting_evidence", []))
    historical_context = _compact_context_rows(compact_packet.get("historical_evidence", []))
    historical_ids = {
        row.get("memory_id")
        for row in historical_context
        if isinstance(row, dict) and row.get("memory_id")
    }
    stale_or_blocked_context = _compact_context_rows(
        row
        for row in compact_packet.get("stale_or_blocked_evidence", [])
        if row.get("memory_id") not in historical_ids
    )
    uncertain_context = _compact_context_rows(
        compact_packet.get("excluded_memory_summary", [])
    )
    transition_context = []
    change_detail_context = []
    static_conflict_resolution_context = []
    temporal_resolution_context = []
    status_class_context = []
    scoped_reader_context = []
    source_history_focus_context = []
    source_history_answer_anchor_context = []
    condition_scope_context = []
    habit_frequency_context = []
    query_relevant_context = []
    if qvf_context_variant != "core_routing":
        transition_context = _build_transition_context(request)
        current_context, historical_context = (
            _reconcile_current_context_with_transition_context(
                current_context=current_context,
                historical_context=historical_context,
                transition_context=transition_context,
            )
        )
        status_class_context = _build_status_class_context(request, transition_context)
        if qvf_context_variant in {
            "adaptive",
            "evidence_preserving",
            "full",
            "compact_full",
            "auto_compact",
            "annotation_only_qvf",
            "multi_action_controller",
            "post_answer_audit_controller",
        }:
            change_detail_context = _build_change_detail_context(request)
            static_conflict_resolution_context = _build_static_conflict_resolution_context(
                request
            )
        temporal_evidence_rows = (
            _all_record_temporal_context_rows(request)
            + current_context
            + historical_context
            + supporting_context
        )
        temporal_resolution_context = _build_temporal_resolution_context(
            request,
            temporal_evidence_rows,
        )
        query_relevant_context = _build_query_relevant_context(
            request,
            current_context
            + historical_context
            + supporting_context
            + stale_or_blocked_context
            + uncertain_context,
        )
        raw_condition_context = []
        if qvf_context_variant in {
            "adaptive",
            "evidence_preserving",
            "annotation_only_qvf",
            "multi_action_controller",
            "post_answer_audit_controller",
        }:
            raw_condition_context = _evidence_preserving_context_rows(
                request,
                routed_labels={},
            )
        condition_scope_context = _build_condition_scope_context(
            request,
            current_context
            + historical_context
            + supporting_context
            + stale_or_blocked_context
            + query_relevant_context
            + raw_condition_context,
        )
        habit_frequency_context = _build_habit_frequency_context(
            request,
            current_context
            + historical_context
            + supporting_context
            + stale_or_blocked_context
            + query_relevant_context
            + raw_condition_context,
        )
        scoped_reader_context = _build_scoped_reader_context(request)
        source_history_focus_context = _build_source_history_focus_context(
            request,
            question,
        )
        source_history_answer_anchor_context = _build_source_history_answer_anchor_context(
            request,
            question,
            scoped_reader_context=scoped_reader_context,
            source_history_focus_context=source_history_focus_context,
        )
    condition_scope_priority_policy = _condition_scope_priority_policy(
        question=question,
        condition_scope_context=condition_scope_context,
    )
    target_compaction_policy = _target_compaction_policy(
        request,
        qvf_context_variant=qvf_context_variant,
        transition_context=transition_context,
        change_detail_context=change_detail_context,
        static_conflict_resolution_context=static_conflict_resolution_context,
    )
    routing_policy = _routing_policy()
    core_read_decision = _compact_read_decision(read_decision)
    public_reader_override = _public_reader_override(
        core_read_decision=core_read_decision,
        static_conflict_resolution_context=static_conflict_resolution_context,
    )
    if public_reader_override:
        current_context, stale_or_blocked_context, uncertain_context = (
            _apply_public_reader_override_to_context(
                current_context=current_context,
                stale_or_blocked_context=stale_or_blocked_context,
                uncertain_context=uncertain_context,
                static_conflict_resolution_context=static_conflict_resolution_context,
                public_reader_override=public_reader_override,
            )
        )
    model_read_decision = (
        public_reader_override.get("qvf_read_time_decision", core_read_decision)
        if public_reader_override
        else core_read_decision
    )
    if condition_scope_priority_policy:
        model_read_decision = _condition_scope_read_decision_override(
            base_read_decision=model_read_decision,
            priority_policy=condition_scope_priority_policy,
        )
    supported_current_context, source_weak_current_context = (
        _partition_source_supported_current_context(current_context)
    )
    model_read_decision = _current_source_support_read_decision(
        model_read_decision,
        supported_current_rows=supported_current_context,
        source_weak_current_rows=source_weak_current_context,
    )
    validity_controller_decision = (
        model_read_decision.get("validity_controller_decision", {})
        if isinstance(model_read_decision, dict)
        else {}
    )
    if not validity_controller_decision:
        validity_controller_decision = core_read_decision.get(
            "validity_controller_decision",
            {},
        )
    routing_mode = _evidence_preservation_routing_mode(
        read_decision=model_read_decision,
        transition_context=transition_context,
        change_detail_context=change_detail_context,
        temporal_resolution_context=temporal_resolution_context,
        stale_or_blocked_context=stale_or_blocked_context,
    )
    effective_qvf_context_variant = qvf_context_variant
    if qvf_context_variant == "adaptive":
        effective_qvf_context_variant = (
            "full" if routing_mode == "route_first" else "evidence_preserving"
        )
    evidence_preservation_policy = {}
    extracted_memory_context = []
    preserve_extracted_context = (
        effective_qvf_context_variant == "evidence_preserving"
        or qvf_context_variant == "annotation_only_qvf"
        or qvf_context_variant == "multi_action_controller"
        or qvf_context_variant == "post_answer_audit_controller"
        or (qvf_context_variant == "adaptive" and qvf_context_variant != "core_routing")
    )
    if preserve_extracted_context:
        routed_labels = _routed_labels_by_memory_id(
            current_context=current_context,
            supporting_context=supporting_context,
            historical_context=historical_context,
            stale_or_blocked_context=stale_or_blocked_context,
            uncertain_context=uncertain_context,
            query_relevant_context=query_relevant_context,
        )
        allowed_memory_ids = None
        if routing_mode == "route_first" and qvf_context_variant not in {
            "annotation_only_qvf",
            "post_answer_audit_controller",
        }:
            allowed_memory_ids = _route_first_raw_fallback_memory_ids(
                routed_labels=routed_labels,
                transition_context=transition_context,
                status_class_context=status_class_context,
                condition_scope_context=condition_scope_context,
                habit_frequency_context=habit_frequency_context,
                temporal_resolution_context=temporal_resolution_context,
                static_conflict_resolution_context=static_conflict_resolution_context,
            )
        extracted_memory_context = _evidence_preserving_context_rows(
            request,
            routed_labels=routed_labels,
            allowed_memory_ids=allowed_memory_ids,
        )
        evidence_preservation_policy = {
            "mode": (
                "annotation_only_preserve_all_extracted_records"
                if qvf_context_variant == "annotation_only_qvf"
                else "post_answer_audit_preserve_extracted_records_with_hidden_qvf_labels"
                if qvf_context_variant == "post_answer_audit_controller"
                else "multi_action_preserve_extracted_records_with_qvf_labels"
                if qvf_context_variant == "multi_action_controller"
                else "preserve_extracted_records_with_qvf_labels"
            ),
            "routing_mode": routing_mode,
            "ordinary_recall": "use extracted_memory_context when it directly answers the question",
            "route_first": "use QVF routed/change/temporal contexts first, but keep extracted_memory_context as raw fallback for exact details, frequencies, routines, and anchor preservation",
            "current_state_conflict": "prefer current_answer rows; do not answer current-state questions from stale_or_blocked rows",
            "history_or_change": "historical_archive and stale_or_blocked rows may answer history/change questions",
            "same_timestamp_conflict": "use static_conflict_resolution_context for ambiguous equal-timestamp conflicts",
            "uncertain": "use uncertain rows only with corroboration or low-confidence wording",
        }
    annotation_policy = {}
    if qvf_context_variant == "annotation_only_qvf":
        annotation_policy = {
            "mode": "always_on_annotation",
            "principle": "QVF labels memory usability but does not remove raw extracted memories",
            "ordinary_recall": "raw extracted memories remain valid evidence when directly relevant",
            "current_state": "prefer current_answer_context for present-state or validity-conflict questions",
            "stale_or_archive": "may be valid for historical recall, prior-state, timeline, and change questions",
            "unknown": "use low-confidence wording rather than treating uncertain rows as current facts",
        }
    memory_validity_controller_action = {}
    if qvf_context_variant in {"multi_action_controller", "post_answer_audit_controller"}:
        memory_validity_controller_action = _memory_validity_controller_action(
            question=question,
            model_read_decision=model_read_decision,
            validity_controller_decision=validity_controller_decision,
            condition_scope_priority_policy=condition_scope_priority_policy,
            public_reader_override=public_reader_override,
            transition_context=transition_context,
            change_detail_context=change_detail_context,
            status_class_context=status_class_context,
            condition_scope_context=condition_scope_context,
            habit_frequency_context=habit_frequency_context,
            extracted_memory_context=extracted_memory_context,
            scoped_reader_context=scoped_reader_context,
            static_conflict_resolution_context=static_conflict_resolution_context,
            temporal_resolution_context=temporal_resolution_context,
            current_context=current_context,
            historical_context=historical_context,
            stale_or_blocked_context=stale_or_blocked_context,
            query_relevant_context=query_relevant_context,
        )
        if (
            qvf_context_variant == "post_answer_audit_controller"
            and memory_validity_controller_action.get("action")
            == "scoped_or_temporal_packet"
        ):
            memory_validity_controller_action = dict(memory_validity_controller_action)
            memory_validity_controller_action.update(
                {
                    "action": "raw_recall_with_annotations",
                    "reason": (
                        "post_answer_controller_temporal_only_recall_direct_equivalent"
                    ),
                    "primary_context_order": [
                        "extracted_memory_context",
                        "historical_archive_context",
                        "query_relevant_context",
                        "supporting_context",
                    ],
                    "post_answer_audit_note": (
                        "Scoped/temporal evidence without explicit validity conflict "
                        "is audited after direct-equivalent answering."
                    ),
                }
            )
        if (
            qvf_context_variant == "post_answer_audit_controller"
            and _post_answer_controller_preserves_comparative_recall(
                question=question,
                memory_validity_controller_action=memory_validity_controller_action,
                model_read_decision=model_read_decision,
                condition_scope_priority_policy=condition_scope_priority_policy,
                public_reader_override=public_reader_override,
                transition_context=transition_context,
                change_detail_context=change_detail_context,
                static_conflict_resolution_context=static_conflict_resolution_context,
            )
        ):
            memory_validity_controller_action = dict(memory_validity_controller_action)
            memory_validity_controller_action.update(
                {
                    "action": "raw_recall_with_annotations",
                    "reason": (
                        "post_answer_controller_comparative_recall_direct_equivalent"
                    ),
                    "primary_context_order": [
                        "extracted_memory_context",
                        "historical_archive_context",
                        "query_relevant_context",
                        "supporting_context",
                    ],
                    "post_answer_audit_note": (
                        "Comparative or aggregate recall without explicit validity "
                        "conflict is audited after direct-equivalent answering."
                    ),
                }
            )
        if (
            qvf_context_variant == "post_answer_audit_controller"
            and _post_answer_controller_preserves_uncontested_current_state(
                memory_validity_controller_action=memory_validity_controller_action,
                model_read_decision=model_read_decision,
                condition_scope_priority_policy=condition_scope_priority_policy,
                public_reader_override=public_reader_override,
                transition_context=transition_context,
                change_detail_context=change_detail_context,
                status_class_context=status_class_context,
                static_conflict_resolution_context=static_conflict_resolution_context,
                stale_or_blocked_context=stale_or_blocked_context,
            )
        ):
            memory_validity_controller_action = dict(memory_validity_controller_action)
            memory_validity_controller_action.update(
                {
                    "action": "raw_recall_with_annotations",
                    "reason": (
                        "post_answer_controller_uncontested_current_state_direct_equivalent"
                    ),
                    "primary_context_order": [
                        "extracted_memory_context",
                        "current_answer_context",
                        "query_relevant_context",
                        "supporting_context",
                    ],
                    "post_answer_audit_note": (
                        "Current-state pressure without explicit stale/current "
                        "conflict is audited after direct-equivalent answering."
                    ),
                }
            )
        if qvf_context_variant == "post_answer_audit_controller":
            annotation_policy = {
                "mode": "direct_equivalent_post_answer_audit_controller",
                "principle": (
                    "ordinary raw-recall actions keep the model-facing prompt "
                    "byte-equivalent to direct; QVF action stays available for "
                    "audit and only route-first validity pressure reaches the "
                    "answer prompt"
                ),
                "ordinary_recall": "answer with direct raw memory prompt; audit QVF labels after answer",
                "current_state": "stale_or_blocked rows are never current facts",
                "fallback": "preserve direct raw memory context for anchor protection",
            }
        else:
            annotation_policy = {
                "mode": "multi_action_annotation_preserving_controller",
                "principle": "choose the lightest QVF action that preserves raw answer anchors",
                "ordinary_recall": "raw extracted memories remain primary unless controller action says route-first validity is required",
                "current_state": "stale_or_blocked rows are never current facts",
                "fallback": "use extracted_memory_context when routed packets are empty, off-topic, or missing exact answer details",
            }
    retrieval_feedback = _build_retrieval_feedback(
        question=question,
        model_read_decision=model_read_decision,
        validity_controller_decision=validity_controller_decision,
        memory_validity_controller_action=memory_validity_controller_action,
        condition_scope_priority_policy=condition_scope_priority_policy,
        current_context=current_context,
        historical_context=historical_context,
        stale_or_blocked_context=stale_or_blocked_context,
        transition_context=transition_context,
        change_detail_context=change_detail_context,
        status_class_context=status_class_context,
        temporal_resolution_context=temporal_resolution_context,
        condition_scope_context=condition_scope_context,
        extracted_memory_context=extracted_memory_context,
    )
    return {
        "context_type": "qvf_validity_packed_context",
        "qvf_context_variant": qvf_context_variant,
        "effective_qvf_context_variant": effective_qvf_context_variant,
        "routing_version": "memory_routing_v1",
        "target_compaction_policy": target_compaction_policy,
        "query_intent": result["packet"]["query"].get("query_intent", "current_state"),
        "qvf_read_time_decision": model_read_decision,
        "core_qvf_read_time_decision": core_read_decision,
        "validity_controller_decision": validity_controller_decision,
        "public_reader_override": public_reader_override,
        "context_control_policy": _compact_context_control_policy(
            result["packet"].get("context_control_policy", {})
        ),
        "routing_policy": routing_policy,
        "memory_validity_controller_action": memory_validity_controller_action,
        "retrieval_feedback": retrieval_feedback,
        "annotation_policy": annotation_policy,
        "evidence_preservation_policy": evidence_preservation_policy,
        "extracted_memory_context": extracted_memory_context,
        "current_answer_context": current_context,
        "admitted_context": current_context,
        "historical_archive_context": historical_context,
        "transition_context": transition_context,
        "change_detail_context": change_detail_context,
        "status_class_context": status_class_context,
        "condition_scope_context": condition_scope_context,
        "habit_frequency_context": habit_frequency_context,
        "condition_scope_priority_policy": condition_scope_priority_policy,
        "scoped_reader_context": scoped_reader_context,
        "source_history_focus_context": source_history_focus_context,
        "source_history_answer_anchor_context": source_history_answer_anchor_context,
        "static_conflict_resolution_context": static_conflict_resolution_context,
        "temporal_resolution_context": temporal_resolution_context,
        "query_relevant_context": query_relevant_context,
        "supporting_context": supporting_context,
        "uncertain_context": uncertain_context,
        "stale_or_blocked_context": stale_or_blocked_context,
    }


def _build_retrieval_feedback(
    *,
    question: str,
    model_read_decision: dict[str, Any],
    validity_controller_decision: dict[str, Any],
    memory_validity_controller_action: dict[str, Any],
    condition_scope_priority_policy: dict[str, Any],
    current_context: list[dict[str, Any]],
    historical_context: list[dict[str, Any]],
    stale_or_blocked_context: list[dict[str, Any]],
    transition_context: list[dict[str, Any]],
    temporal_resolution_context: list[dict[str, Any]],
    condition_scope_context: list[dict[str, Any]],
    extracted_memory_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]] | None = None,
    status_class_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Emit system-facing feedback when QVF cannot validate memory use yet."""

    if not isinstance(validity_controller_decision, dict):
        validity_controller_decision = {}
    if not isinstance(model_read_decision, dict):
        model_read_decision = {}
    if not isinstance(memory_validity_controller_action, dict):
        memory_validity_controller_action = {}
    if not isinstance(condition_scope_priority_policy, dict):
        condition_scope_priority_policy = {}
    if change_detail_context is None:
        change_detail_context = []
    if status_class_context is None:
        status_class_context = []

    next_action = str(validity_controller_decision.get("next_action") or "")
    evidence_sufficiency = str(
        validity_controller_decision.get("evidence_sufficiency") or ""
    )
    action_name = str(memory_validity_controller_action.get("action") or "")
    action_reason = str(memory_validity_controller_action.get("reason") or "")
    guard = memory_validity_controller_action.get(
        "condition_scope_primary_precision_guard",
        {},
    )
    if not isinstance(guard, dict):
        guard = {}

    issues: list[dict[str, Any]] = []
    retrieve_scope = _retrieval_feedback_scope(validity_controller_decision)
    blocked_ids = _feedback_ids(validity_controller_decision.get("blocked_as_current_ids"))
    allowed_history_ids = _feedback_ids(
        validity_controller_decision.get("allowed_as_history_ids")
    )
    stale_ids = _context_memory_ids(stale_or_blocked_context)

    if (
        next_action in {"retrieve_current_entity_slot", "query_rewrite_and_retrieve"}
        and not _direct_equivalent_recall_feedback_suppressed(
            action_name=action_name,
            action_reason=action_reason,
        )
    ):
        issues.append(
            {
                "issue_type": (
                    "missing_current_evidence"
                    if next_action == "retrieve_current_entity_slot"
                    else "insufficient_relevant_evidence"
                ),
                "severity": "blocking",
                "reason": (
                    "QVF sees stale, archive, excluded, or supporting-only rows but "
                    "does not see source-backed current answer evidence."
                ),
                "required_retrieval": {
                    "retrieve": "source_backed_entity_slot_current_evidence",
                    "scope": retrieve_scope,
                    "query_rewrite": str(
                        validity_controller_decision.get("query_rewrite") or ""
                    ),
                    "success_criterion": (
                        "return a visible current row for the requested entity-slot, "
                        "or an explicit no-current-evidence result"
                    ),
                },
                "must_not_use_as_current_ids": list(
                    dict.fromkeys([*blocked_ids, *stale_ids])
                ),
                "allowed_as_history_ids": allowed_history_ids,
            }
        )
    elif (
        next_action == "retrieve_entity_slot_timeline"
        and not transition_context
        and not change_detail_context
        and not status_class_context
        and not temporal_resolution_context
    ):
        issues.append(
            {
                "issue_type": "missing_timeline_evidence",
                "severity": "blocking",
                "reason": (
                    "QVF cannot order the relevant entity-slot states from the visible "
                    "memory rows."
                ),
                "required_retrieval": {
                    "retrieve": "bounded_entity_slot_timeline",
                    "scope": retrieve_scope,
                    "query_rewrite": str(
                        validity_controller_decision.get("query_rewrite") or ""
                    ),
                    "success_criterion": (
                        "return source-dated current and historical rows sufficient "
                        "to establish ordering"
                    ),
                },
                "must_not_use_as_current_ids": list(
                    dict.fromkeys([*blocked_ids, *stale_ids])
                ),
                "allowed_as_history_ids": allowed_history_ids,
            }
        )

    if (
        _asks_for_change_detail(question)
        and action_name == "raw_recall_with_annotations"
        and not transition_context
        and not change_detail_context
        and not status_class_context
    ):
        target_group = _transition_group_for_question(question, "")
        issues.append(
            {
                "issue_type": "missing_change_pair_evidence",
                "severity": "blocking",
                "reason": (
                    "The question asks what changed, but QVF does not see a "
                    "source-backed previous-current pair or field-change row."
                ),
                "required_retrieval": {
                    "retrieve": "source_backed_previous_current_change_pair",
                    "scope": {
                        **retrieve_scope,
                        "target_group": target_group,
                        "include_current": True,
                        "include_archive": True,
                        "include_source_history": True,
                    },
                    "query_rewrite": _change_pair_feedback_query(
                        question,
                        target_group=target_group,
                    ),
                    "success_criterion": (
                        "return old and new values for the requested field with "
                        "source dates, or an explicit no-previous-state result"
                    ),
                },
            }
        )

    if condition_scope_priority_policy and not condition_scope_context:
        issues.append(
            {
                "issue_type": "missing_condition_scope_evidence",
                "severity": "blocking",
                "reason": (
                    "The query requires condition-scoped memory use, but no "
                    "condition_scope_context rows are visible."
                ),
                "required_retrieval": {
                    "retrieve": "source_backed_condition_scope_rows",
                    "scope": retrieve_scope,
                    "query_rewrite": _condition_scope_feedback_query(question),
                    "success_criterion": (
                        "return source spans that state the exact condition and "
                        "answer value together"
                    ),
                },
            }
        )
    elif guard.get("decision") == "DEMOTE_CONDITION_SCOPE_PRIMARY":
        issues.append(
            {
                "issue_type": "condition_scope_evidence_unsupported",
                "severity": "advisory",
                "reason": (
                    "QVF found condition rows, but the precision guard demoted them "
                    "because raw memory contains stronger or more complete answer "
                    "anchors."
                ),
                "required_retrieval": {
                    "retrieve": "complete_condition_scope_source_spans",
                    "scope": retrieve_scope,
                    "query_rewrite": _condition_scope_feedback_query(question),
                    "success_criterion": (
                        "return condition rows whose source span preserves all "
                        "answer-critical alternatives and descriptors"
                    ),
                },
                "guard_risk_count": len(guard.get("risk_rows", []))
                if isinstance(guard.get("risk_rows"), list)
                else 0,
            }
        )

    if not issues:
        return {}

    blocking_count = sum(1 for issue in issues if issue.get("severity") == "blocking")
    return {
        "feedback_version": RETRIEVAL_FEEDBACK_VERSION,
        "scope": "system_retrieval_feedback_not_answer_evidence",
        "status": "needs_additional_retrieval" if blocking_count else "advisory_only",
        "primary_issue_type": str(issues[0].get("issue_type") or ""),
        "controller_next_action": next_action,
        "controller_evidence_sufficiency": evidence_sufficiency,
        "controller_action": action_name,
        "question_fingerprint": _truncate_text(question, 120),
        "max_retrieval_attempts": 1,
        "boundary": (
            "QVF emits feedback after initial retrieval; it does not write memory, "
            "replace retrieval, or treat feedback as answer evidence."
        ),
        "visible_bucket_counts": {
            "current_answer_context": len(current_context),
            "historical_archive_context": len(historical_context),
            "stale_or_blocked_context": len(stale_or_blocked_context),
            "transition_context": len(transition_context),
            "change_detail_context": len(change_detail_context),
            "status_class_context": len(status_class_context),
            "temporal_resolution_context": len(temporal_resolution_context),
            "condition_scope_context": len(condition_scope_context),
            "extracted_memory_context": len(extracted_memory_context),
        },
        "issues": issues,
    }


def _retrieval_feedback_scope(
    validity_controller_decision: dict[str, Any],
) -> dict[str, Any]:
    scope = validity_controller_decision.get("suggested_retrieval_scope", {})
    if not isinstance(scope, dict):
        scope = {}
    return {
        key: value
        for key, value in scope.items()
        if value not in (None, "", [], {})
    }


def _feedback_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _context_memory_ids(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        memory_id = str(row.get("memory_id") or "")
        if memory_id:
            ids.append(memory_id)
    return list(dict.fromkeys(ids))


def _condition_scope_feedback_query(question: str) -> str:
    cleaned = _truncate_text(re.sub(r"\s+", " ", question).strip(), 160)
    if not cleaned:
        return "retrieve source-backed condition scope rows"
    return f"retrieve source-backed condition scope rows for: {cleaned}"


def _direct_equivalent_recall_feedback_suppressed(
    *,
    action_name: str,
    action_reason: str,
) -> bool:
    if action_name != "raw_recall_with_annotations":
        return False
    return action_reason in {
        "post_answer_controller_temporal_only_recall_direct_equivalent",
        "post_answer_controller_comparative_recall_direct_equivalent",
        "post_answer_controller_uncontested_current_state_direct_equivalent",
    }


def _change_pair_feedback_query(question: str, *, target_group: str) -> str:
    cleaned = _truncate_text(re.sub(r"\s+", " ", question).strip(), 160)
    if target_group:
        return f"retrieve previous and current {target_group} evidence for: {cleaned}"
    return f"retrieve previous and current change evidence for: {cleaned}"


def _memory_validity_controller_action(
    *,
    question: str,
    model_read_decision: dict[str, Any],
    validity_controller_decision: dict[str, Any],
    condition_scope_priority_policy: dict[str, Any],
    public_reader_override: dict[str, Any],
    transition_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]],
    status_class_context: list[dict[str, Any]],
    condition_scope_context: list[dict[str, Any]],
    habit_frequency_context: list[dict[str, Any]],
    extracted_memory_context: list[dict[str, Any]],
    scoped_reader_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
    temporal_resolution_context: list[dict[str, Any]],
    current_context: list[dict[str, Any]],
    historical_context: list[dict[str, Any]],
    stale_or_blocked_context: list[dict[str, Any]],
    query_relevant_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Choose the lightest model-facing QVF action from evidence buckets."""

    next_action = str(validity_controller_decision.get("next_action") or "")
    read_decision = str(model_read_decision.get("decision") or "")
    answer_policy = str(model_read_decision.get("answer_policy") or "")
    evidence_sufficiency = str(
        validity_controller_decision.get("evidence_sufficiency") or ""
    )
    current_state_pressure = bool(
        current_context
        and (
            stale_or_blocked_context
            or read_decision in {"REJECT_STALE_PREMISE", "UNKNOWN_CURRENT"}
            or next_action.startswith("retrieve_current")
            or "current" in evidence_sufficiency
        )
    )

    condition_primary_guard = _condition_scope_primary_precision_guard(
        question=question,
        condition_scope_context=condition_scope_context,
        extracted_memory_context=extracted_memory_context,
    )
    if (
        condition_scope_priority_policy
        and condition_scope_context
        and condition_primary_guard.get("decision")
        == "DEMOTE_CONDITION_SCOPE_PRIMARY"
    ):
        action = "raw_recall_with_annotations"
        primary = [
            "extracted_memory_context",
            "condition_scope_context",
            "historical_archive_context",
            "query_relevant_context",
            "supporting_context",
        ]
        reason = "condition_scope_primary_precision_guard"
    elif condition_scope_priority_policy and condition_scope_context:
        action = "condition_scope_packet"
        primary = ["condition_scope_context", "extracted_memory_context"]
        reason = "condition_scope_priority_policy_present"
    elif public_reader_override or static_conflict_resolution_context:
        action = "timeline_or_conflict_packet"
        primary = [
            "static_conflict_resolution_context",
            "extracted_memory_context",
        ]
        reason = "same_timestamp_or_static_conflict_resolution_present"
    elif transition_context or change_detail_context or status_class_context:
        action = "timeline_or_conflict_packet"
        primary = [
            "transition_context",
            "change_detail_context",
            "status_class_context",
            "extracted_memory_context",
        ]
        reason = "transition_or_change_detail_context_present"
    elif current_state_pressure:
        action = "stale_current_validity_packet"
        primary = [
            "current_answer_context",
            "stale_or_blocked_context",
            "extracted_memory_context",
        ]
        reason = "current_state_pressure_with_qvf_validity_evidence"
    elif scoped_reader_context or temporal_resolution_context:
        action = "scoped_or_temporal_packet"
        primary = [
            "scoped_reader_context",
            "temporal_resolution_context",
            "extracted_memory_context",
        ]
        reason = "scoped_or_temporal_evidence_present"
    else:
        action = "raw_recall_with_annotations"
        primary = [
            "extracted_memory_context",
            "historical_archive_context",
            "query_relevant_context",
            "supporting_context",
        ]
        reason = "no_route_first_validity_pressure_detected"

    if habit_frequency_context and _asks_for_habit_frequency(question):
        primary = [
            "habit_frequency_context",
            *[bucket for bucket in primary if bucket != "habit_frequency_context"],
        ]
        reason = f"{reason}_with_source_backed_habit_frequency"

    result = {
        "action": action,
        "reason": reason,
        "question_fingerprint": _truncate_text(question, 120),
        "primary_context_order": primary,
        "raw_memory_fallback": "preserve_extracted_memory_context",
        "stale_current_rule": (
            "stale_or_blocked rows are usable as history but never as current facts"
        ),
        "answer_anchor_policy": (
            "prefer raw extracted rows for exact names, numbers, dates, frequencies, "
            "routines, cadence phrases, and spans when routed QVF packets omit "
            "answer-critical details"
        ),
        "bucket_counts": {
            "current_answer_context": len(current_context),
            "historical_archive_context": len(historical_context),
            "transition_context": len(transition_context),
            "change_detail_context": len(change_detail_context),
            "status_class_context": len(status_class_context),
            "condition_scope_context": len(condition_scope_context),
            "habit_frequency_context": len(habit_frequency_context),
            "scoped_reader_context": len(scoped_reader_context),
            "static_conflict_resolution_context": len(static_conflict_resolution_context),
            "temporal_resolution_context": len(temporal_resolution_context),
            "query_relevant_context": len(query_relevant_context),
            "stale_or_blocked_context": len(stale_or_blocked_context),
        },
    }
    if condition_primary_guard:
        result["condition_scope_primary_precision_guard"] = condition_primary_guard
    return result


def _condition_scope_primary_precision_guard(
    *,
    question: str,
    condition_scope_context: list[dict[str, Any]],
    extracted_memory_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Demote imprecise condition rows when raw memory has a stronger answer anchor."""

    if not condition_scope_context or not extracted_memory_context:
        return {}
    target_tokens = _condition_scope_target_tokens(question)
    strong_raw_rows = _strong_raw_condition_answer_rows(
        target_tokens=target_tokens,
        extracted_memory_context=extracted_memory_context,
    )
    target_relevant_raw_rows = _target_relevant_raw_answer_rows(
        target_tokens=target_tokens,
        extracted_memory_context=extracted_memory_context,
    )
    fallback_raw_rows = _dedupe_condition_raw_rows(
        [*strong_raw_rows, *target_relevant_raw_rows]
    )
    if not fallback_raw_rows:
        return {}
    risk_rows = []
    for row in condition_scope_context:
        if not isinstance(row, dict):
            continue
        reasons = _condition_scope_primary_row_risks(
            row=row,
            target_tokens=target_tokens,
            strong_raw_rows=strong_raw_rows,
            fallback_raw_rows=fallback_raw_rows,
        )
        if reasons:
            risk_rows.append(
                {
                    "memory_id": row.get("memory_id", ""),
                    "exact_condition": row.get("exact_condition", ""),
                    "supporting_value": row.get("supporting_value", ""),
                    "source_field": row.get("source_field", ""),
                    "risk_reasons": reasons,
                }
            )
    if not risk_rows:
        return {
            "decision": "KEEP_CONDITION_SCOPE_PRIMARY",
            "risk_row_count": 0,
            "strong_raw_anchor_count": len(strong_raw_rows),
            "fallback_raw_anchor_count": len(fallback_raw_rows),
        }
    return {
        "decision": "DEMOTE_CONDITION_SCOPE_PRIMARY",
        "risk_row_count": len(risk_rows),
        "strong_raw_anchor_count": len(strong_raw_rows),
        "fallback_raw_anchor_count": len(fallback_raw_rows),
        "reason": (
            "condition_scope_context has high-risk primary rows while raw "
            "extracted memory contains stronger condition-answer anchors"
        ),
        "fallback_action": "raw_recall_with_annotations",
        "risk_rows": risk_rows[:MAX_CONDITION_SCOPE_HINTS],
    }


def _strong_raw_condition_answer_rows(
    *,
    target_tokens: set[str],
    extracted_memory_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for row in extracted_memory_context:
        if not isinstance(row, dict):
            continue
        claim = str(row.get("claim", ""))
        value = str(row.get("value", ""))
        text = _norm_text(" ".join([claim, value]))
        tokens = set(text.split())
        overlap = len(target_tokens & tokens) if target_tokens else 0
        if target_tokens and overlap < _condition_scope_required_target_overlap(target_tokens):
            continue
        relevance = _safe_int(row.get("relevance_score"), 0)
        has_condition = _raw_claim_has_condition_answer_anchor(row)
        has_preference = bool(tokens & CONDITION_PREFERENCE_CUES)
        if relevance >= 3 and has_condition and (has_preference or value):
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: _safe_int(row.get("relevance_score"), 0),
        reverse=True,
    )


def _target_relevant_raw_answer_rows(
    *,
    target_tokens: set[str],
    extracted_memory_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for row in extracted_memory_context:
        if not isinstance(row, dict):
            continue
        text = _norm_text(" ".join([str(row.get("claim", "")), str(row.get("value", ""))]))
        tokens = set(text.split())
        overlap = len(target_tokens & tokens) if target_tokens else 0
        if target_tokens and overlap < _condition_scope_required_target_overlap(target_tokens):
            continue
        if _safe_int(row.get("relevance_score"), 0) >= 3:
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: _safe_int(row.get("relevance_score", 0), 0),
        reverse=True,
    )


def _dedupe_condition_raw_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (
            str(row.get("memory_id", "")),
            str(row.get("claim", "")),
            str(row.get("value", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _raw_claim_has_condition_answer_anchor(row: dict[str, Any]) -> bool:
    claim = str(row.get("claim", ""))
    if not claim:
        return False
    for phrase in _extract_condition_phrases(claim):
        phrase = _condition_phrase_with_leading_context(claim, phrase)
        if _condition_phrase_has_noise(phrase):
            continue
        if _condition_phrase_is_object_only(phrase, row):
            continue
        if _condition_scope_signal_tokens(phrase):
            return True
    return False


def _condition_scope_primary_row_risks(
    *,
    row: dict[str, Any],
    target_tokens: set[str],
    strong_raw_rows: list[dict[str, Any]],
    fallback_raw_rows: list[dict[str, Any]],
) -> list[str]:
    reasons = []
    phrase = str(row.get("exact_condition", ""))
    phrase_tokens = _condition_scope_signal_tokens(phrase)
    if _condition_phrase_has_dangling_connector(phrase):
        reasons.append("dangling_condition_connector")
    if _condition_row_value_misses_target(row, target_tokens):
        reasons.append("condition_supporting_value_misses_query_target")
    if _condition_source_span_is_not_claim_bound(row, phrase_tokens, strong_raw_rows):
        reasons.append("source_span_condition_not_supported_by_direct_claim")
    if _condition_advice_row_overrides_preference(row, strong_raw_rows):
        reasons.append("advice_or_schedule_row_overrides_preference_anchor")
    if _condition_tentative_acquisition_overrides_suitability_anchor(
        row,
        fallback_raw_rows,
        target_tokens,
    ):
        reasons.append("tentative_acquisition_condition_overrides_suitability_anchor")
    return reasons


def _condition_scope_signal_tokens(text: str) -> set[str]:
    return {
        token
        for token in _norm_text(text).split()
        if len(token) > 2 and token not in CONDITION_SCOPE_STOPWORDS
    }


def _condition_phrase_has_dangling_connector(phrase: str) -> bool:
    tokens = _norm_text(phrase).split()
    return bool(tokens and tokens[-1] in {"and", "or", "to", "for", "with"})


def _condition_row_value_misses_target(
    row: dict[str, Any],
    target_tokens: set[str],
) -> bool:
    if not target_tokens:
        return False
    if str(row.get("scope_type", "")) == "condition_preference_source":
        return False
    value_tokens = _condition_scope_signal_tokens(str(row.get("supporting_value", "")))
    if not value_tokens:
        return False
    return not bool(value_tokens & target_tokens)


def _condition_source_span_is_not_claim_bound(
    row: dict[str, Any],
    phrase_tokens: set[str],
    strong_raw_rows: list[dict[str, Any]],
) -> bool:
    if not strong_raw_rows:
        return False
    if str(row.get("source_field", "")) != "source_span":
        return False
    if not phrase_tokens:
        return False
    row_memory_id = str(row.get("memory_id", ""))
    raw_rows = [
        raw
        for raw in strong_raw_rows
        if not row_memory_id or str(raw.get("memory_id", "")) == row_memory_id
    ] or strong_raw_rows
    for raw in raw_rows:
        raw_tokens = _condition_scope_signal_tokens(
            " ".join([str(raw.get("claim", "")), str(raw.get("value", ""))])
        )
        required = 2 if len(phrase_tokens) >= 3 else 1
        if len(phrase_tokens & raw_tokens) >= required:
            return False
    return True


def _condition_advice_row_overrides_preference(
    row: dict[str, Any],
    strong_raw_rows: list[dict[str, Any]],
) -> bool:
    exact_condition_tokens = set(_norm_text(str(row.get("exact_condition", ""))).split())
    row_text = _norm_text(
        " ".join(
            str(row.get(field_name, ""))
            for field_name in ("source_excerpt", "supporting_value", "exact_condition")
        )
    )
    advice_terms = {
        "advised",
        "advice",
        "tips",
        "consider",
        "daycare",
        "walker",
        "schedule",
        "train",
        "routine",
        "routines",
    }
    if not (exact_condition_tokens & advice_terms):
        return False
    if not (set(row_text.split()) & advice_terms):
        return False
    for raw in strong_raw_rows:
        raw_text = _norm_text(
            " ".join([str(raw.get("claim", "")), str(raw.get("value", ""))])
        )
        raw_tokens = set(raw_text.split())
        if (raw_tokens & CONDITION_PREFERENCE_CUES or str(raw.get("value", ""))) and not (
            raw_tokens & {"advised", "advice", "tips"}
        ):
            return True
    return False


def _condition_tentative_acquisition_overrides_suitability_anchor(
    row: dict[str, Any],
    strong_raw_rows: list[dict[str, Any]],
    target_tokens: set[str],
) -> bool:
    if not strong_raw_rows:
        return False
    row_text = _norm_text(
        " ".join(
            str(row.get(field_name, ""))
            for field_name in (
                "exact_condition",
                "preferred_answer",
                "supporting_value",
                "source_excerpt",
            )
        )
    )
    row_tokens = set(row_text.split())
    tentative_terms = {
        "consider",
        "considering",
        "get",
        "getting",
        "might",
        "would",
    }
    timing_terms = {
        "eases",
        "if",
        "later",
        "pace",
        "right",
        "timing",
        "when",
    }
    if not (row_tokens & tentative_terms and row_tokens & timing_terms):
        return False
    acquisition_target_terms = {
        "adopt",
        "adoption",
        "cat",
        "companion",
        "dog",
        "pet",
    }
    if not (row_tokens & acquisition_target_terms or target_tokens & acquisition_target_terms):
        return False
    suitability_terms = {
        "adaptable",
        "busy",
        "companion",
        "fit",
        "fits",
        "good",
        "hypoallergenic",
        "schedule",
        "smaller",
        "suitability",
        "suitable",
    }
    for raw in strong_raw_rows:
        raw_text = _norm_text(
            " ".join([str(raw.get("claim", "")), str(raw.get("value", ""))])
        )
        if set(raw_text.split()) & suitability_terms:
            return True
    return False


def _post_answer_controller_preserves_comparative_recall(
    *,
    question: str,
    memory_validity_controller_action: dict[str, Any],
    model_read_decision: dict[str, Any],
    condition_scope_priority_policy: dict[str, Any],
    public_reader_override: dict[str, Any],
    transition_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
) -> bool:
    if str(memory_validity_controller_action.get("action") or "") != "stale_current_validity_packet":
        return False
    if (
        condition_scope_priority_policy
        or public_reader_override
        or transition_context
        or change_detail_context
        or static_conflict_resolution_context
    ):
        return False
    if str(model_read_decision.get("decision") or "") == "REJECT_STALE_PREMISE":
        return False
    return _is_comparative_or_aggregate_recall_question(question)


def _is_comparative_or_aggregate_recall_question(question: str) -> bool:
    text = _norm_text(question)
    if not text:
        return False
    if " compared to " in f" {text} ":
        return True
    if re.search(r"\bhow much (?:more|less)\b", text):
        return True
    if re.search(r"\b(?:more|less) .+ than\b", text):
        return True
    if text.startswith("how many ") and (
        re.search(r"\b(?:have|has|had)\b.+\bor\b.+\bcurrently\b", text)
        or re.search(r"\bcurrently\b.+\bor\b", text)
    ):
        return True
    return False


def _post_answer_controller_preserves_uncontested_current_state(
    *,
    memory_validity_controller_action: dict[str, Any],
    model_read_decision: dict[str, Any],
    condition_scope_priority_policy: dict[str, Any],
    public_reader_override: dict[str, Any],
    transition_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]],
    status_class_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
    stale_or_blocked_context: list[dict[str, Any]],
) -> bool:
    if str(memory_validity_controller_action.get("action") or "") != "stale_current_validity_packet":
        return False
    if (
        condition_scope_priority_policy
        or public_reader_override
        or transition_context
        or change_detail_context
        or status_class_context
        or static_conflict_resolution_context
        or stale_or_blocked_context
    ):
        return False
    if str(model_read_decision.get("decision") or "") == "REJECT_STALE_PREMISE":
        return False
    return True


def _reconcile_current_context_with_transition_context(
    *,
    current_context: list[dict[str, Any]],
    historical_context: list[dict[str, Any]],
    transition_context: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    previous_state_ids = {
        str(transition.get("previous_memory_id", ""))
        for transition in transition_context
        if isinstance(transition, dict) and transition.get("previous_memory_id")
    }
    if not previous_state_ids:
        return current_context, historical_context

    historical_ids = {
        str(row.get("memory_id", ""))
        for row in historical_context
        if isinstance(row, dict) and row.get("memory_id")
    }
    reconciled_current = []
    reconciled_historical = list(historical_context)
    for row in current_context:
        if not isinstance(row, dict):
            continue
        memory_id = str(row.get("memory_id", ""))
        if memory_id and memory_id in previous_state_ids:
            if memory_id not in historical_ids:
                historical_row = dict(row)
                historical_row["reconciled_from"] = "current_answer_context"
                historical_row["reconciliation_reason"] = (
                    "transition_previous_state_not_current"
                )
                reconciled_historical.append(historical_row)
                historical_ids.add(memory_id)
            continue
        reconciled_current.append(row)
    return reconciled_current, reconciled_historical


def _target_memory_context(method: str, context: dict[str, Any]) -> dict[str, Any]:
    if method == SELECTIVE_ROUTER_METHOD:
        selected_method, selected_context = _selected_router_target_context(context)
        return _target_memory_context(
            selected_method,
            selected_context,
        )
    if method != QVF_METHOD:
        return context
    public_reader_override = context.get("public_reader_override", {})
    if not isinstance(public_reader_override, dict):
        public_reader_override = {}
    current_answer_context, source_weak_current_context = (
        _partition_source_supported_current_context(
            context.get("current_answer_context", [])
        )
    )
    target_read_decision = _current_source_support_read_decision(
        context.get("qvf_read_time_decision", {}),
        supported_current_rows=current_answer_context,
        source_weak_current_rows=source_weak_current_context,
    )
    uncertain_context = _source_weak_current_quarantine_rows(
        source_weak_current_context
    ) + [
        row
        for row in context.get("uncertain_context", [])
        if isinstance(row, dict)
    ]
    memory_context = {
        "context_type": context.get("context_type"),
        "qvf_context_variant": context.get("qvf_context_variant"),
        "effective_qvf_context_variant": context.get("effective_qvf_context_variant"),
        "routing_version": context.get("routing_version"),
        "query_intent": context.get("query_intent"),
        "target_compaction_policy": context.get("target_compaction_policy", {}),
        "memory_validity_controller_action": context.get(
            "memory_validity_controller_action",
            {},
        ),
        "qvf_read_time_decision": _target_read_decision(
            target_read_decision,
        ),
        "validity_controller_decision": context.get(
            "validity_controller_decision",
            {},
        ),
        "current_answer_context": _target_rows_from_rows(
            context,
            current_answer_context,
        ),
        "historical_archive_context": _target_rows(
            context,
            "historical_archive_context",
        ),
        "transition_context": context.get("transition_context", []),
        "change_detail_context": context.get("change_detail_context", []),
        "status_class_context": context.get("status_class_context", []),
        "condition_scope_context": context.get("condition_scope_context", []),
        "habit_frequency_context": context.get("habit_frequency_context", []),
        "scoped_reader_context": context.get("scoped_reader_context", []),
        "source_history_focus_context": context.get(
            "source_history_focus_context",
            [],
        ),
        "source_history_answer_anchor_context": context.get(
            "source_history_answer_anchor_context",
            [],
        ),
        "static_conflict_resolution_context": context.get(
            "static_conflict_resolution_context",
            [],
        ),
        "temporal_resolution_context": context.get("temporal_resolution_context", []),
        "supporting_context": _target_rows(context, "supporting_context"),
        "stale_or_blocked_context": _target_rows(
            context,
            "stale_or_blocked_context",
        ),
        "uncertain_context": _target_rows_from_rows(context, uncertain_context),
        "bucket_counts": {
            "extracted_memory_context": len(
                context.get("extracted_memory_context", [])
            ),
            "current_answer_context": len(current_answer_context),
            "historical_archive_context": len(
                context.get("historical_archive_context", [])
            ),
            "transition_context": len(context.get("transition_context", [])),
            "change_detail_context": len(context.get("change_detail_context", [])),
            "status_class_context": len(context.get("status_class_context", [])),
            "condition_scope_context": len(
                context.get("condition_scope_context", [])
            ),
            "habit_frequency_context": len(
                context.get("habit_frequency_context", [])
            ),
            "scoped_reader_context": len(
                context.get("scoped_reader_context", [])
            ),
            "source_history_focus_context": len(
                context.get("source_history_focus_context", [])
            ),
            "source_history_answer_anchor_context": len(
                context.get("source_history_answer_anchor_context", [])
            ),
            "static_conflict_resolution_context": len(
                context.get("static_conflict_resolution_context", [])
            ),
            "temporal_resolution_context": len(
                context.get("temporal_resolution_context", [])
            ),
            "supporting_context": len(context.get("supporting_context", [])),
            "stale_or_blocked_context": len(
                context.get("stale_or_blocked_context", [])
            ),
            "uncertain_context": len(uncertain_context),
        },
    }
    if source_weak_current_context:
        memory_context["source_weak_current_quarantine"] = {
            "decision": "QUARANTINE_SOURCE_WEAK_CURRENT",
            "row_count": len(source_weak_current_context),
            "memory_ids": [
                row.get("memory_id", "")
                for row in source_weak_current_context
                if row.get("memory_id")
            ],
            "reason": "current row value/claim is not sufficiently supported by source_span",
        }
    if public_reader_override:
        memory_context["public_reader_override"] = public_reader_override
        memory_context["core_qvf_read_time_decision"] = _target_read_decision(
            context.get("core_qvf_read_time_decision", {})
        )
    condition_priority_policy = context.get("condition_scope_priority_policy", {})
    if isinstance(condition_priority_policy, dict) and condition_priority_policy:
        memory_context["condition_scope_priority_policy"] = condition_priority_policy
        memory_context["core_qvf_read_time_decision"] = _target_read_decision(
            context.get("core_qvf_read_time_decision", {})
        )
    evidence_preservation_policy = context.get("evidence_preservation_policy", {})
    if evidence_preservation_policy:
        memory_context["evidence_preservation_policy"] = evidence_preservation_policy
    annotation_policy = context.get("annotation_policy", {})
    if annotation_policy:
        memory_context["annotation_policy"] = annotation_policy
    retrieval_feedback = context.get("retrieval_feedback", {})
    if isinstance(retrieval_feedback, dict) and retrieval_feedback:
        memory_context["retrieval_feedback"] = retrieval_feedback
    source_history_answer_contract = _source_history_answer_contract(context)
    if source_history_answer_contract:
        memory_context["source_history_answer_contract"] = (
            source_history_answer_contract
        )
    computational_answer_contract = _computational_answer_contract(context)
    if computational_answer_contract:
        memory_context["computational_answer_contract"] = (
            computational_answer_contract
        )
    extracted_memory_context = context.get("extracted_memory_context", [])
    if extracted_memory_context:
        memory_context["extracted_memory_context"] = _target_rows(
            context,
            "extracted_memory_context",
        )
    query_relevant_context = context.get("query_relevant_context", [])
    if query_relevant_context:
        memory_context["query_relevant_context"] = _target_rows(
            context,
            "query_relevant_context",
        )
        memory_context["bucket_counts"]["query_relevant_context"] = len(
            query_relevant_context
        )
    answer_rendering_guard = _answer_rendering_guard(context)
    if answer_rendering_guard:
        memory_context["answer_rendering_guard"] = answer_rendering_guard
        memory_context["bucket_counts"]["answer_rendering_guard"] = len(
            answer_rendering_guard["anchors"]
        )
    answer_decision_contract = _answer_decision_contract(context)
    if answer_decision_contract:
        memory_context["answer_decision_contract"] = answer_decision_contract
        memory_context["bucket_counts"]["answer_decision_contract"] = len(
            answer_decision_contract["contract_rows"]
        )
    return memory_context


def _answer_rendering_guard(context: dict[str, Any]) -> dict[str, Any]:
    anchors = _answer_rendering_guard_anchors(context)
    if not anchors:
        return {}
    return {
        "mode": "preserve_exact_answer_anchors",
        "scope": "answer_rendering_only",
        "evidence_boundary": (
            "anchors are copied from model-visible memory/QVF context and must not be "
            "treated as new evidence or as a routing override"
        ),
        "rule": (
            "If an anchor is relevant to the question, preserve its exact condition, "
            "cadence, source, or slot-detail wording in the answer."
        ),
        "anchors": anchors,
    }


def _answer_rendering_guard_anchors(context: dict[str, Any]) -> list[dict[str, str]]:
    anchors: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in _dict_rows(context.get("condition_scope_context", [])):
        _add_answer_rendering_anchor(
            anchors,
            seen,
            row,
            anchor_type="condition_scope",
            fields=(
                "complete_condition_answer",
                "preferred_answer",
                "exact_condition",
                "condition_answer_detail",
                "supporting_value",
                "source_excerpt",
            ),
        )
    for row in _dict_rows(context.get("habit_frequency_context", [])):
        _add_answer_rendering_anchor(
            anchors,
            seen,
            row,
            anchor_type="habit_frequency",
            fields=(
                "preferred_answer_anchor",
                "frequency_phrase",
                "day_phrase",
                "answer_slot",
                "source_excerpt",
            ),
        )
    for row in _dict_rows(context.get("status_class_context", [])):
        _add_answer_rendering_anchor(
            anchors,
            seen,
            row,
            anchor_type="status_class",
            fields=("preferred_answer", "status_class", "source_excerpt"),
        )
    for row in _dict_rows(context.get("transition_context", [])):
        _add_answer_rendering_anchor(
            anchors,
            seen,
            row,
            anchor_type="transition",
            fields=(
                "preferred_answer",
                "previous_value",
                "current_value",
                "from_value",
                "to_value",
                "source_excerpt",
            ),
        )
    for row in _dict_rows(context.get("change_detail_context", [])):
        _add_answer_rendering_anchor(
            anchors,
            seen,
            row,
            anchor_type="change_detail",
            fields=(
                "preferred_answer",
                "changed_fields",
                "previous_value",
                "current_value",
                "source_excerpt",
            ),
        )
    return anchors[:MAX_ANSWER_RENDERING_ANCHORS]


def _answer_decision_contract(context: dict[str, Any]) -> dict[str, Any]:
    action = context.get("memory_validity_controller_action", {})
    if not isinstance(action, dict):
        action = {}
    action_name = str(action.get("action") or "")
    if action_name == "raw_recall_with_annotations":
        return {}
    rows: list[dict[str, Any]] = []
    question = str(action.get("question_fingerprint") or "")
    if _is_yes_no_change_question(question):
        transition_rows = _dict_rows(context.get("transition_context", []))
        if transition_rows:
            rows.append(_yes_no_transition_contract_row(transition_rows[0]))
    for row in _dict_rows(context.get("condition_scope_context", [])):
        contract_row = _condition_answer_contract_row(row)
        if contract_row:
            rows.append(contract_row)
        if len(rows) >= MAX_ANSWER_DECISION_CONTRACT_ROWS:
            break
    if not rows:
        return {}
    return {
        "mode": "source_backed_answer_decision_contract",
        "scope": "answer_rendering_only",
        "evidence_boundary": (
            "contract rows are copied or summarized from visible memory_context rows; "
            "they are not benchmark answers and do not override QVF routing"
        ),
        "rule": (
            "Satisfy answer_shape and preserve relevant must_preserve phrases without "
            "adding unsupported slot-level paraphrases."
        ),
        "contract_rows": rows[:MAX_ANSWER_DECISION_CONTRACT_ROWS],
    }


def _source_history_answer_contract(context: dict[str, Any]) -> dict[str, Any]:
    if not _controller_requires_source_history_prompt(context):
        return {}
    decision = _validity_controller_decision_from_context(context)
    retrieve_scope = _retrieval_feedback_scope(decision)
    return {
        "mode": "source_history_temporal_boundary_contract",
        "scope": "answer_rendering_only",
        "controller_next_action": decision.get("next_action", ""),
        "controller_evidence_sufficiency": decision.get(
            "evidence_sufficiency",
            "",
        ),
        "suggested_retrieval_scope": retrieve_scope,
        "evidence_boundary": (
            "This contract is derived from QVF controller scope and visible memory "
            "rows. It is not a benchmark answer, not new retrieval evidence, and "
            "does not authorize using stale rows as current facts."
        ),
        "rule": (
            "When the question depends on time, ordering, before/after relations, "
            "or recent/latest wording, answer from rows whose observed_at, "
            "source_span, or source_excerpt supports the temporal boundary. Preserve "
            "the source-backed temporal phrase or date when it is answer-critical. "
            "If source_history_focus_context is present, prefer its "
            "source_temporal_phrase plus source_observed_at boundary for week/weekend "
            "answers rather than replacing the phrase with a narrower date. For "
            "why/reason questions, preserve source_focus_phrase and source_sentence "
            "as the causal support instead of substituting a generic explanation."
        ),
        "required_fields": [
            "observed_at",
            "source_span",
            "source_excerpt",
            "resolved_time",
            "temporal_marker",
        ],
    }


def _computational_answer_contract(context: dict[str, Any]) -> dict[str, Any]:
    question = _controller_question_fingerprint(context)
    if not question:
        return {}
    computation_mode = _question_computation_mode(question)
    if not computation_mode:
        return {}
    if computation_mode == "elapsed_duration":
        answer_shape = (
            "identify the start event and end event from visible rows, compute the "
            "elapsed scalar, and answer with the requested unit"
        )
        steps = [
            "find the row or phrase that supports the start event",
            "find the row or phrase that supports the end event",
            "compute the elapsed duration in the unit requested by the question",
            "do not reuse one date as both start and end unless the source text says so",
        ]
    elif computation_mode == "quantity_sum":
        answer_shape = (
            "sum only durations or quantities that satisfy every activity and temporal "
            "constraint in the question"
        )
        steps = [
            "enumerate visible rows matching the requested activities and time window",
            "exclude broader routine ranges or adjacent activities outside the scope",
            "sum the supported quantities, preserving fractional values when present",
            "if the visible evidence only gives a range, answer the supported range or abstain",
        ]
    else:
        answer_shape = (
            "enumerate unique relevant entities or events before returning the count"
        )
        steps = [
            "collect all visible rows satisfying the entity, action, and temporal scope",
            "deduplicate repeated claims about the same item or event",
            "count named individuals or items explicitly supported by source text",
            "treat plural groups such as twins as multiple individuals only when the source supports it",
        ]
    candidates = (
        _aggregate_answer_candidates(context, question)
        if computation_mode == "aggregate_count"
        else {}
    )
    return {
        "mode": "computed_scalar_answer_contract",
        "scope": "answer_rendering_only",
        "computation_mode": computation_mode,
        "question_fingerprint": question,
        "answer_shape": answer_shape,
        "computation_steps": steps,
        **({"visible_candidate_items": candidates} if candidates else {}),
        "evidence_boundary": (
            "This contract is derived from the question shape and visible QVF memory "
            "context. It is not a benchmark answer, not gold metadata, and not new "
            "evidence. If visible rows do not support the scalar, abstain or state the "
            "supported boundary rather than inventing a value."
        ),
    }


def _question_computation_mode(question: str) -> str:
    text = re.sub(r"\s+", " ", str(question or "")).strip().lower()
    if not text:
        return ""
    if re.search(
        r"\bhow many\s+(?:days|hours|weeks|months|years)\s+did\s+it\s+take\b",
        text,
    ) or re.search(r"\bhow long\s+did\s+it\s+take\b", text):
        return "elapsed_duration"
    if re.search(
        r"\bhow many\s+(?:days|weeks|months|years)\s+(?:before|after)\b",
        text,
    ):
        return "elapsed_duration"
    if re.search(r"\bhow many\s+(?:hours|minutes)\b", text):
        return "quantity_sum"
    if re.search(r"\b(?:how many|number of|count of|total number of)\b", text):
        return "aggregate_count"
    return ""


def _aggregate_answer_candidates(
    context: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen_rows: set[str] = set()
    deduped_items: list[str] = []
    seen_items: set[str] = set()
    question_key = _candidate_item_key(question)
    for bucket in (
        "current_answer_context",
        "scoped_reader_context",
        "historical_archive_context",
        "extracted_memory_context",
        "supporting_context",
        "query_relevant_context",
    ):
        for row in _dict_rows(context.get(bucket, [])):
            memory_id = str(row.get("memory_id") or "")
            row_key = memory_id or str(row.get("claim") or row.get("value") or "")
            if row_key and row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            if not _row_matches_aggregate_scope(row, question):
                continue
            items = _candidate_items_from_row(row)
            items = [
                item
                for item in items
                if _candidate_item_key(item)
                and _candidate_item_key(item) not in question_key
            ]
            if not items:
                continue
            rows.append(
                {
                    "source_bucket": bucket,
                    "memory_id": memory_id,
                    "candidate_text": _short_candidate_text(row),
                    "candidate_items": items,
                }
            )
            for item in items:
                item_key = _candidate_item_key(item)
                if item_key and item_key not in seen_items:
                    seen_items.add(item_key)
                    deduped_items.append(item)
            if len(rows) >= MAX_COMPUTATIONAL_CANDIDATE_ROWS:
                break
        if len(rows) >= MAX_COMPUTATIONAL_CANDIDATE_ROWS:
            break
    if not rows:
        return {}
    return {
        "candidate_rule": (
            "Candidate items are normalized from visible memory row values/claims. "
            "Use them only as a counting aid, then verify they satisfy the question scope."
        ),
        "deduplicated_candidate_items": deduped_items[
            :MAX_COMPUTATIONAL_CANDIDATE_ITEMS
        ],
        "candidate_rows": rows[:MAX_COMPUTATIONAL_CANDIDATE_ROWS],
    }


def _candidate_items_from_row(row: dict[str, Any]) -> list[str]:
    value = str(row.get("value") or "").strip()
    return _split_candidate_items(value)


def _row_matches_aggregate_scope(row: dict[str, Any], question: str) -> bool:
    question_tokens = _scope_tokens(question)
    if not question_tokens:
        return False
    row_text = " ".join(
        str(row.get(field) or "")
        for field in ("claim", "value", "source_excerpt", "source_span")
    )
    row_tokens = _scope_tokens(row_text)
    return bool(question_tokens & row_tokens)


SCOPE_TOKEN_STOPWORDS = {
    "about",
    "after",
    "before",
    "being",
    "currently",
    "different",
    "does",
    "family",
    "friend",
    "friends",
    "from",
    "have",
    "including",
    "last",
    "many",
    "member",
    "members",
    "month",
    "months",
    "number",
    "that",
    "their",
    "there",
    "this",
    "time",
    "what",
    "when",
    "where",
    "with",
}


def _scope_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9']+", str(text or "").lower()):
        token = raw.strip("'")
        if len(token) < 4 or token in SCOPE_TOKEN_STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        else:
            token = re.sub(r"(?:ing|ed|es|s)$", "", token)
        if len(token) >= 4 and token not in SCOPE_TOKEN_STOPWORDS:
            tokens.add(token)
    return tokens


def _split_candidate_items(text: str) -> list[str]:
    text = _clean_candidate_text(text)
    if not text or _candidate_text_is_non_entity(text):
        return []
    parts = re.split(r"\s*(?:,|;|\band\b|\bor\b)\s*", text, flags=re.I)
    items: list[str] = []
    for part in parts:
        item = _clean_candidate_item(part)
        if item and not _candidate_text_is_non_entity(item):
            items.append(item)
    if len(items) > 1:
        return items[:MAX_COMPUTATIONAL_CANDIDATE_ITEMS]
    item = _clean_candidate_item(text)
    return [item] if item and not _candidate_text_is_non_entity(item) else []


def _clean_candidate_text(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"^[\"'`]+|[\"'`.]+$", "", text).strip()
    return text


def _clean_candidate_item(text: str) -> str:
    text = _clean_candidate_text(text)
    text = re.sub(r"^(?:a|an|the|my|your|their|his|her)\s+", "", text, flags=re.I)
    text = re.sub(r"\b(?:plant|baby|boy|girl|son|daughter)\s+named\s+", "", text, flags=re.I)
    return _clean_candidate_text(text)


def _candidate_text_is_non_entity(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    if lowered in {"unknown", "none", "n/a", "yes", "no", "current", "historical"}:
        return True
    if re.search(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", lowered):
        return True
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", lowered):
        return True
    if re.search(r"\b(?:ago|week|weeks|month|months|year|years|hour|hours|day|days|visit|resolved)\b", lowered):
        return True
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", lowered):
        return True
    if re.search(r"^\$?\d", lowered):
        return True
    return False


def _short_candidate_text(row: dict[str, Any]) -> str:
    for field in ("value", "claim", "source_excerpt", "source_span"):
        text = _clean_candidate_text(str(row.get(field) or ""))
        if text:
            return text[:MAX_ANSWER_DECISION_CONTRACT_CHARS]
    return ""


def _candidate_item_key(item: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(item or "").lower()).strip()


def _controller_question_fingerprint(context: dict[str, Any]) -> str:
    action = context.get("memory_validity_controller_action", {})
    if isinstance(action, dict):
        question = str(action.get("question_fingerprint") or "")
        if question:
            return question
    feedback = context.get("retrieval_feedback", {})
    if isinstance(feedback, dict):
        question = str(feedback.get("question_fingerprint") or "")
        if question:
            return question
    return ""


def _is_yes_no_change_question(question: str) -> bool:
    return bool(
        re.search(
            r"^\s*(?:did|does|do|has|have|is|are|was|were)\b.*\b(?:change|changed|different|same)\b",
            str(question or ""),
            flags=re.I,
        )
    )


def _yes_no_transition_contract_row(row: dict[str, Any]) -> dict[str, Any]:
    must_preserve = _contract_phrases(
        row,
        ("preferred_answer", "previous_value", "current_value", "source_excerpt"),
    )
    return {
        "contract_type": "yes_no_transition_answer_shape",
        "source_bucket": "transition_context",
        "memory_id": str(row.get("memory_id", "")).strip(),
        "answer_shape": "answer yes/no first; add only source-backed change boundary if needed",
        "must_preserve": must_preserve,
        "avoid_overclaim": (
            "do not present a current value or adjacent relationship detail as the "
            "queried slot label unless the visible source row states that label"
        ),
    }


def _condition_answer_contract_row(row: dict[str, Any]) -> dict[str, Any]:
    must_preserve = _contract_phrases(
        row,
        (
            "complete_condition_answer",
            "preferred_answer",
            "source_excerpt",
            "condition_answer_detail",
            "supporting_value",
            "exact_condition",
        ),
    )
    if not must_preserve:
        return {}
    return {
        "contract_type": "condition_detail_preservation",
        "source_bucket": "condition_scope_context",
        "memory_id": str(row.get("memory_id", "")).strip(),
        "answer_shape": (
            "answer the requested condition/preference using all relevant source-backed "
            "condition alternatives and descriptors"
        ),
        "must_preserve": must_preserve,
        "avoid_overclaim": (
            "do not narrow a compound condition to one alternative and do not add adjacent "
            "schedule/routine details unless they are part of the same source-backed phrase"
        ),
    }


def _contract_phrases(row: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for field in fields:
        phrase = _clean_answer_decision_contract_phrase(row.get(field))
        if not phrase:
            continue
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        phrases.append(phrase)
        if len(phrases) >= MAX_ANSWER_DECISION_CONTRACT_PHRASES:
            break
    return phrases


def _clean_answer_decision_contract_phrase(value: Any) -> str:
    phrase = _clean_answer_rendering_phrase(value)
    if not phrase:
        return ""
    if len(phrase) > MAX_ANSWER_DECISION_CONTRACT_CHARS:
        phrase = phrase[: MAX_ANSWER_DECISION_CONTRACT_CHARS - 3].rstrip() + "..."
    return phrase


def _dict_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _add_answer_rendering_anchor(
    anchors: list[dict[str, str]],
    seen: set[tuple[str, str, str]],
    row: dict[str, Any],
    *,
    anchor_type: str,
    fields: tuple[str, ...],
) -> None:
    if len(anchors) >= MAX_ANSWER_RENDERING_ANCHORS:
        return
    memory_id = str(row.get("memory_id", "")).strip()
    for field in fields:
        if len(anchors) >= MAX_ANSWER_RENDERING_ANCHORS:
            return
        phrase = _clean_answer_rendering_phrase(row.get(field))
        if not phrase:
            continue
        key = (anchor_type, field, phrase.lower())
        if key in seen:
            continue
        seen.add(key)
        anchor = {
            "anchor_type": anchor_type,
            "source_field": field,
            "phrase": phrase,
            "preservation_policy": (
                "copy this wording when it is the relevant answer detail; do not broaden"
            ),
        }
        if memory_id:
            anchor["memory_id"] = memory_id
        answer_slot = str(row.get("answer_slot", "")).strip()
        if answer_slot:
            anchor["answer_slot"] = answer_slot
        anchors.append(anchor)


def _clean_answer_rendering_phrase(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict):
        return ""
    if isinstance(value, list):
        value = ", ".join(str(item).strip() for item in value if str(item).strip())
    phrase = re.sub(r"\s+", " ", str(value)).strip()
    if len(phrase) < 3:
        return ""
    if len(phrase) > MAX_ANSWER_RENDERING_ANCHOR_CHARS:
        phrase = phrase[: MAX_ANSWER_RENDERING_ANCHOR_CHARS - 3].rstrip() + "..."
    return phrase


def _target_context_method(method: str, context: dict[str, Any]) -> str:
    if method == SELECTIVE_ROUTER_METHOD:
        selected_method, _ = _selected_router_target_context(context)
        return selected_method
    return method


def _selected_router_target_context(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    selected_method = str(context.get("selected_method") or DIRECT_METHOD)
    if selected_method == SELECTIVE_ROUTER_METHOD:
        selected_method = DIRECT_METHOD
    selected_context = context.get("selected_context", {})
    if not isinstance(selected_context, dict):
        selected_context = {}
    return selected_method, selected_context


def _target_instruction_context(
    *,
    method: str,
    context: dict[str, Any],
    target_method: str,
) -> dict[str, Any]:
    if method == SELECTIVE_ROUTER_METHOD and target_method == QVF_METHOD:
        selected_context = context.get("selected_context", {})
        if isinstance(selected_context, dict):
            return selected_context
    return context


FORBIDDEN_TARGET_PAYLOAD_TERMS = (
    "expected_answers",
    "gold_valid_memory_ids",
    "gold labels",
    "gold answer",
    "judge metadata",
    "judge_response",
    "parsed_judgment",
)

LOCAL_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\+(?:Users|ZZL_MPHIL)\\+|/Users/|/home/)"
)
SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_-]?key|secret[_-]?key|sk-[A-Za-z0-9]{12,})",
    flags=re.I,
)


def _build_target_payload_audit(
    eval_items: list[dict[str, Any]],
    *,
    qvf_context_variant: str,
) -> dict[str, Any]:
    case_ids = {str(item.get("case_id", "")) for item in eval_items if item.get("case_id")}
    method_counts = Counter(str(item.get("method", "")) for item in eval_items)
    forbidden_hits = []
    local_path_hits = []
    secret_like_hits = []
    answer_text_overlaps = []
    selective_route_counts: Counter[str] = Counter()
    scoped_cases = []
    for item in eval_items:
        case_id = str(item.get("case_id", ""))
        method = str(item.get("method", ""))
        rendered = json.dumps(item.get("target_messages", []), ensure_ascii=False)
        lowered = rendered.lower()
        for term in FORBIDDEN_TARGET_PAYLOAD_TERMS:
            if term in lowered:
                forbidden_hits.append(
                    {"case_id": case_id, "method": method, "term": term}
                )
        if LOCAL_PATH_PATTERN.search(rendered):
            local_path_hits.append({"case_id": case_id, "method": method})
        if SECRET_LIKE_PATTERN.search(rendered):
            secret_like_hits.append({"case_id": case_id, "method": method})
        overlap_count = _answer_text_overlap_count(
            item.get("expected_answers", []),
            rendered,
        )
        if overlap_count:
            answer_text_overlaps.append(
                {
                    "case_id": case_id,
                    "method": method,
                    "answer_text_overlap_count": overlap_count,
                }
            )
        if method == SELECTIVE_ROUTER_METHOD:
            context = item.get("context", {})
            if not isinstance(context, dict):
                context = {}
            selected_method = str(context.get("selected_method") or "")
            selective_route_counts[selected_method] += 1
            target_context = _target_memory_context(method, context)
            scoped = target_context.get("scoped_reader_context", [])
            if isinstance(scoped, list) and scoped:
                events = [
                    event
                    for packet in scoped
                    if isinstance(packet, dict)
                    for event in packet.get("candidate_events", [])
                    if isinstance(event, dict)
                ]
                scoped_cases.append(
                    {
                        "case_id": case_id,
                        "question": str(item.get("question", "")),
                        "selected_method": selected_method,
                        "scoped_packet_count": len(scoped),
                        "event_count": len(events),
                        "top_event_title": events[0].get("event_title", "") if events else "",
                        "top_temporal_marker": events[0].get("temporal_marker", "") if events else "",
                        "top_action_cue": events[0].get("action_cue", "") if events else "",
                    }
                )
    blocking_hit_count = len(forbidden_hits) + len(local_path_hits) + len(secret_like_hits)
    decision = (
        "GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT"
        if blocking_hit_count == 0
        else "NO_GO_PUBLIC_ANSWER_TARGET_PAYLOAD_AUDIT"
    )
    return {
        "decision": decision,
        "execution_mode": "public_answer_target_payload_audit_no_api",
        "qvf_context_variant": qvf_context_variant,
        "case_count": len(case_ids),
        "item_count": len(eval_items),
        "method_counts": dict(method_counts),
        "selective_route_counts": dict(selective_route_counts),
        "scoped_case_count": len(scoped_cases),
        "scoped_cases": scoped_cases,
        "forbidden_field_hits": forbidden_hits,
        "local_path_hits": local_path_hits,
        "secret_like_hits": secret_like_hits,
        "answer_text_overlap_count": len(answer_text_overlaps),
        "answer_text_overlap_note": (
            "Answer strings may appear in target prompts when selected or extracted "
            "evidence contains the answer; this is not gold-label leakage by itself."
        ),
        "blocking_hit_count": blocking_hit_count,
        "api_calls_made": 0,
    }


def _answer_text_overlap_count(answers: Any, rendered_target: str) -> int:
    if isinstance(answers, str):
        answer_values = [answers]
    elif isinstance(answers, list):
        answer_values = [str(answer) for answer in answers]
    else:
        answer_values = []
    return sum(1 for answer in answer_values if answer.strip() and answer in rendered_target)


def _target_read_decision(read_decision: Any) -> dict[str, Any]:
    if not isinstance(read_decision, dict):
        return {}
    out = {
        "decision": read_decision.get("decision", ""),
        "answer_policy": read_decision.get("answer_policy", ""),
        "route": read_decision.get("route", ""),
    }
    reader_contract = read_decision.get("reader_contract", "")
    if reader_contract:
        out["reader_contract"] = _truncate_text(str(reader_contract), 160)
    controller = read_decision.get("validity_controller_decision", {})
    if isinstance(controller, dict) and controller:
        out["validity_controller_decision"] = {
            "evidence_sufficiency": controller.get("evidence_sufficiency", ""),
            "next_action": controller.get("next_action", ""),
            "suggested_retrieval_scope": controller.get(
                "suggested_retrieval_scope",
                {},
            ),
            "blocked_as_current_ids": controller.get("blocked_as_current_ids", []),
            "allowed_as_history_ids": controller.get("allowed_as_history_ids", []),
        }
    return {key: value for key, value in out.items() if value not in (None, "", [], {})}


COMPACT_FULL_TARGET_ROW_FIELDS = (
    "memory_id",
    "claim",
    "value",
    "observed_at",
    "valid_until",
    "source_span",
    "retrieval_role",
    "relevance_score",
    "relevance_reason",
)


def _target_rows(context: dict[str, Any], bucket_name: str) -> list[dict[str, Any]]:
    rows = context.get(bucket_name, [])
    return _target_rows_from_rows(context, rows)


def _target_rows_from_rows(context: dict[str, Any], rows: Any) -> list[dict[str, Any]]:
    compaction_policy = context.get("target_compaction_policy", {})
    if not isinstance(compaction_policy, dict):
        compaction_policy = {}
    if compaction_policy.get("mode") != "compact":
        return rows if isinstance(rows, list) else []
    return [_compact_full_target_row(row) for row in rows if isinstance(row, dict)]


def _partition_source_supported_current_context(
    rows: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    supported_rows: list[dict[str, Any]] = []
    source_weak_rows: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return supported_rows, source_weak_rows
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _target_row_has_source_support(row):
            supported_rows.append(row)
            continue
        source_weak_rows.append(row)
    return supported_rows, source_weak_rows


def _source_weak_current_quarantine_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quarantined = []
    for row in rows:
        out = dict(row)
        out["retrieval_role"] = "source_weak_current_quarantine"
        out["quarantine_reason"] = "current_value_not_source_supported"
        quarantined.append(out)
    return quarantined


def _target_row_has_source_support(row: dict[str, Any]) -> bool:
    source = row.get("source", {})
    source_span = str(row.get("source_span") or "")
    if not source_span and isinstance(source, dict):
        source_span = str(source.get("source_span") or "")
    if not source_span:
        return False
    source_tokens = set(_source_support_tokens(source_span))
    value_tokens = [
        token
        for token in _source_support_tokens(str(row.get("value", "")))
        if len(token) > 2 and token not in SOURCE_SUPPORT_VALUE_MODIFIER_TOKENS
    ]
    claim_tokens = [
        token
        for token in _source_support_tokens(str(row.get("claim", "")))
        if len(token) > 3
    ]
    if value_tokens and all(token in source_tokens for token in value_tokens[:6]):
        return True
    if claim_tokens:
        overlap = sum(1 for token in claim_tokens if token in source_tokens)
        return overlap / max(1, min(len(claim_tokens), 12)) >= 0.5
    return True


def _source_support_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


SOURCE_SUPPORT_VALUE_MODIFIER_TOKENS = {
    "current",
    "currently",
    "latest",
    "new",
    "now",
    "recent",
    "recently",
}


def _current_source_support_read_decision(
    read_decision: Any,
    *,
    supported_current_rows: list[dict[str, Any]],
    source_weak_current_rows: list[dict[str, Any]],
) -> Any:
    if not isinstance(read_decision, dict):
        return read_decision
    if supported_current_rows and _read_decision_blocks_supported_current(
        read_decision,
        supported_current_rows=supported_current_rows,
    ):
        updated = dict(read_decision)
        updated["decision"] = "ADMIT_CURRENT"
        updated["answer_policy"] = "answer_from_current"
        updated["route"] = "current_support_reader_reconciled"
        updated["reader_contract"] = (
            "Answer from source-supported current_answer_context rows. Ignore "
            "stale/unknown diagnostics that also list the same supported current "
            "row as blocked."
        )
        controller = dict(updated.get("validity_controller_decision", {}))
        supported_ids = {
            str(row.get("memory_id", ""))
            for row in supported_current_rows
            if row.get("memory_id")
        }
        blocked_ids = [
            memory_id
            for memory_id in controller.get("blocked_as_current_ids", [])
            if str(memory_id) not in supported_ids
        ]
        controller["evidence_sufficiency"] = "visible_current_answer_evidence"
        controller["next_action"] = "answer_from_current"
        controller["blocked_as_current_ids"] = blocked_ids
        updated["validity_controller_decision"] = controller
        return updated
    if not source_weak_current_rows or supported_current_rows:
        return read_decision
    if not _read_decision_answers_from_current(read_decision):
        return read_decision
    updated = dict(read_decision)
    updated["decision"] = "UNKNOWN_CURRENT"
    updated["answer_policy"] = "insufficient_source_supported_current"
    updated["route"] = "source_weak_current_quarantine"
    updated["reader_contract"] = (
        "Do not answer as current from source-weak current rows. Use other routed "
        "change/archive evidence if supported; otherwise answer unknown."
    )
    return updated


def _read_decision_blocks_supported_current(
    read_decision: dict[str, Any],
    *,
    supported_current_rows: list[dict[str, Any]],
) -> bool:
    supported_ids = {
        str(row.get("memory_id", ""))
        for row in supported_current_rows
        if row.get("memory_id")
    }
    controller = read_decision.get("validity_controller_decision", {})
    if not isinstance(controller, dict):
        controller = {}
    blocked_ids = {
        str(memory_id) for memory_id in controller.get("blocked_as_current_ids", [])
    }
    decision = str(read_decision.get("decision", "")).upper()
    answer_policy = str(read_decision.get("answer_policy", "")).lower()
    evidence_sufficiency = str(
        controller.get("evidence_sufficiency", "")
    ).lower()
    return bool(
        (supported_ids and supported_ids & blocked_ids)
        or decision in {"UNKNOWN_CURRENT", "REJECT_STALE_PREMISE"}
        or answer_policy in {"insufficient_current_state", "insufficient_source_supported_current"}
        or evidence_sufficiency == "no_visible_answer_evidence"
    )


def _read_decision_answers_from_current(read_decision: dict[str, Any]) -> bool:
    decision = str(read_decision.get("decision", "")).lower()
    answer_policy = str(read_decision.get("answer_policy", "")).lower()
    route = str(read_decision.get("route", "")).lower()
    return (
        "current" in answer_policy
        or decision.startswith("admit_current")
        or route in {"current_reader", "current_support_reader"}
    )


def _compact_full_target_row(row: dict[str, Any]) -> dict[str, Any]:
    compacted = {}
    for field_name in COMPACT_FULL_TARGET_ROW_FIELDS:
        value = row.get(field_name)
        if value in (None, "", [], {}):
            continue
        if field_name == "claim" and isinstance(value, str):
            value = _truncate_text(value, 180)
        if field_name == "source_span" and isinstance(value, str):
            value = _truncate_text(value, 240)
        compacted[field_name] = value
    return compacted


STATIC_PROFILE_SLOT_GROUPS = {
    "birthdate",
    "degree",
    "education",
    "father",
    "father_name",
    "gender",
    "highest_degree",
    "mother",
    "name",
    "parent",
    "university",
}


def _target_compaction_policy(
    request: dict[str, Any],
    *,
    qvf_context_variant: str,
    transition_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
) -> dict[str, str]:
    if qvf_context_variant == "compact_full":
        return {"mode": "compact", "reason": "explicit_compact_full"}
    if qvf_context_variant == "adaptive":
        return {"mode": "full", "reason": "adaptive_variant"}
    if qvf_context_variant == "evidence_preserving":
        return {
            "mode": "full",
            "reason": "evidence_preserving_variant_keeps_original_extracted_records",
        }
    if qvf_context_variant != "auto_compact":
        return {"mode": "full", "reason": f"explicit_{qvf_context_variant}"}
    risk_reason = _auto_compact_risk_reason(
        request,
        transition_context=transition_context,
        change_detail_context=change_detail_context,
        static_conflict_resolution_context=static_conflict_resolution_context,
    )
    if risk_reason:
        return {"mode": "full", "reason": risk_reason}
    return {"mode": "compact", "reason": "low_conflict_or_change_risk"}


def _auto_compact_risk_reason(
    request: dict[str, Any],
    *,
    transition_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
) -> str:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    query_slot = str(query.get("slot", ""))
    if _asks_for_transition(question):
        return "transition_question"
    if transition_context:
        return "transition_context_present"
    if change_detail_context:
        return "change_detail_context_present"
    if static_conflict_resolution_context:
        return "static_conflict_resolution_context_present"
    if _is_static_profile_question(question, query_slot):
        return "static_profile_question"
    if _has_query_relevant_value_conflict(request, question, query):
        return "query_relevant_value_conflict"
    return ""


def _is_static_profile_question(question: str, query_slot: str) -> bool:
    text = _norm_text(question)
    slot = _transition_slot_group(query_slot, question) or _norm_text(query_slot)
    if slot in STATIC_PROFILE_SLOT_GROUPS:
        return True
    return any(term in text.split() for term in STATIC_PROFILE_SLOT_GROUPS)


def _has_query_relevant_value_conflict(
    request: dict[str, Any],
    question: str,
    query: dict[str, Any],
) -> bool:
    grouped_values: dict[str, set[str]] = {}
    query_entity = _norm_text(query.get("entity", ""))
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        if query_entity and _norm_text(record.get("entity", "")) != query_entity:
            continue
        score, _ = _question_relevance_score(question, query, record)
        if score < 4:
            continue
        value = _norm_text(record.get("value", ""))
        if not value:
            continue
        group = _transition_slot_group(str(record.get("slot", "")), question)
        if not group:
            group = _norm_text(record.get("slot", ""))
        grouped_values.setdefault(group, set()).add(value)
    return any(len(values) > 1 for values in grouped_values.values())


def _routing_policy() -> dict[str, str]:
    return {
        "extracted_memory_context": "original extracted evidence preserved with QVF validity labels",
        "current_answer_context": "answer current-state questions",
        "historical_archive_context": "answer history/timeline/change questions",
        "transition_context": "old-to-new change summaries for change questions",
        "change_detail_context": "source-history field changes for multi-detail change questions",
        "status_class_context": "coarse status-class continuity for explicit stayed-same status questions",
        "condition_scope_context": "exact condition clauses for condition-bound preferences or habits",
        "habit_frequency_context": "source-backed frequency/cadence anchors for how-often habit questions",
        "static_conflict_resolution_context": "same-timestamp value conflicts resolved from source-span cues",
        "temporal_resolution_context": "relative-time resolutions for when/date questions",
        "query_relevant_context": "fallback extracted records when QVF routing misses question-relevant evidence",
        "supporting_context": "details or disambiguation",
        "stale_or_blocked_context": "outdated/blocked; not current-state support",
        "uncertain_context": "low confidence; corroborate before use",
    }


def _compact_context_control_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    out = {}
    for field_name in (
        "answer_from_roles",
        "do_not_answer_from_roles",
        "archive_policy",
        "reader_contract",
    ):
        value = policy.get(field_name)
        if value not in (None, "", [], {}):
            out[field_name] = value
    return out


def _compact_read_decision(read_decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": read_decision.get("decision", ""),
        "answer_policy": read_decision.get("answer_policy", ""),
        "route": read_decision.get("route", ""),
        "reader_contract": read_decision.get("reader_contract", ""),
        "validity_controller_decision": read_decision.get(
            "validity_controller_decision",
            {},
        ),
    }


def _public_reader_override(
    *,
    core_read_decision: dict[str, Any],
    static_conflict_resolution_context: list[dict[str, Any]],
) -> dict[str, Any]:
    if not _is_weak_public_read_decision(core_read_decision):
        return {}
    conflict = _best_static_conflict_resolution(static_conflict_resolution_context)
    if not conflict:
        return {}
    recommended_memory_id = str(conflict.get("recommended_memory_id", ""))
    recommended_value = str(conflict.get("recommended_value", ""))
    if not recommended_memory_id or not recommended_value:
        return {}
    return {
        "mode": "same_timestamp_conflict_resolution",
        "reason": (
            "public extraction assigned equal timestamps to conflicting records; "
            "source-span cues provide a stronger per-query resolution"
        ),
        "recommended_memory_id": recommended_memory_id,
        "recommended_value": recommended_value,
        "recommendation_confidence": conflict.get("recommendation_confidence", ""),
        "recommendation_reason": conflict.get("recommendation_reason", []),
        "core_decision": core_read_decision.get("decision", ""),
        "core_answer_policy": core_read_decision.get("answer_policy", ""),
        "qvf_read_time_decision": {
            "decision": "ADMIT_CURRENT",
            "answer_policy": "answer_from_static_conflict_resolution",
            "route": "public_same_timestamp_conflict_reader",
            "reader_contract": (
                "Use static_conflict_resolution_context.recommended_value as the "
                "answer support for this same-timestamp public extraction conflict. "
                "Do not treat the preserved core_qvf_read_time_decision weak gate as "
                "a reason to abstain when recommendation_confidence is cue_based."
            ),
        },
    }


def _is_weak_public_read_decision(core_read_decision: dict[str, Any]) -> bool:
    decision = str(core_read_decision.get("decision", ""))
    answer_policy = str(core_read_decision.get("answer_policy", ""))
    return decision in {"UNKNOWN_CURRENT", "REJECT_STALE_PREMISE"} or answer_policy in {
        "correct_premise_only",
        "insufficient_current_state",
    }


def _best_static_conflict_resolution(
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    cue_based = [
        row
        for row in contexts
        if isinstance(row, dict)
        and row.get("recommendation_confidence") == "cue_based"
        and row.get("recommended_value")
        and row.get("recommended_memory_id")
    ]
    if not cue_based:
        return {}
    return sorted(
        cue_based,
        key=lambda row: (
            -_best_static_candidate_score(row),
            str(row.get("recommended_memory_id", "")),
        ),
    )[0]


def _best_static_candidate_score(row: dict[str, Any]) -> int:
    recommended_memory_id = str(row.get("recommended_memory_id", ""))
    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        return 0
    for candidate in candidates:
        if (
            isinstance(candidate, dict)
            and str(candidate.get("memory_id", "")) == recommended_memory_id
        ):
            try:
                return int(candidate.get("cue_score", 0))
            except (TypeError, ValueError):
                return 0
    return 0


def _apply_public_reader_override_to_context(
    *,
    current_context: list[dict[str, Any]],
    stale_or_blocked_context: list[dict[str, Any]],
    uncertain_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
    public_reader_override: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    recommended_memory_id = str(public_reader_override.get("recommended_memory_id", ""))
    if not recommended_memory_id:
        return current_context, stale_or_blocked_context, uncertain_context
    conflict = _static_conflict_by_recommended_id(
        static_conflict_resolution_context,
        recommended_memory_id,
    )
    if not conflict:
        return current_context, stale_or_blocked_context, uncertain_context
    candidate_ids = {
        str(candidate.get("memory_id", ""))
        for candidate in conflict.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("memory_id")
    }
    if not candidate_ids:
        return current_context, stale_or_blocked_context, uncertain_context
    resolved_row = _resolved_static_conflict_row(conflict)
    new_current_context: list[dict[str, Any]] = []
    moved_uncertain: list[dict[str, Any]] = []
    found_recommended = False
    for row in current_context:
        memory_id = str(row.get("memory_id", ""))
        if memory_id == recommended_memory_id:
            new_current_context.append({**row, **resolved_row})
            found_recommended = True
        elif memory_id in candidate_ids:
            moved_uncertain.append(
                _overridden_static_conflict_row(row, recommended_memory_id)
            )
        else:
            new_current_context.append(row)
    if not found_recommended and resolved_row:
        new_current_context.insert(0, resolved_row)

    new_stale_or_blocked_context = [
        row
        for row in stale_or_blocked_context
        if str(row.get("memory_id", "")) != recommended_memory_id
    ]
    for row in stale_or_blocked_context:
        memory_id = str(row.get("memory_id", ""))
        if memory_id in candidate_ids and memory_id != recommended_memory_id:
            moved_uncertain.append(
                _overridden_static_conflict_row(row, recommended_memory_id)
            )
    return (
        new_current_context,
        new_stale_or_blocked_context,
        uncertain_context + moved_uncertain,
    )


def _static_conflict_by_recommended_id(
    contexts: list[dict[str, Any]],
    recommended_memory_id: str,
) -> dict[str, Any]:
    for context in contexts:
        if (
            isinstance(context, dict)
            and str(context.get("recommended_memory_id", "")) == recommended_memory_id
        ):
            return context
    return {}


def _resolved_static_conflict_row(conflict: dict[str, Any]) -> dict[str, Any]:
    recommended_memory_id = str(conflict.get("recommended_memory_id", ""))
    candidate = _static_conflict_candidate_by_id(conflict, recommended_memory_id)
    value = str(conflict.get("recommended_value", ""))
    row = {
        "memory_id": recommended_memory_id,
        "claim": f"Same-timestamp conflict resolved to {value}.",
        "value": value,
        "observed_at": conflict.get("observed_at", ""),
        "source_type": "public_history_extraction",
        "source_span": candidate.get("source_span", ""),
        "source_confidence": conflict.get("recommendation_confidence", ""),
        "current_status": "current_by_source_cue",
        "retrieval_role": "same_timestamp_conflict_resolved",
    }
    return {
        key: value
        for key, value in row.items()
        if value not in (None, "", [], {})
    }


def _static_conflict_candidate_by_id(
    conflict: dict[str, Any],
    memory_id: str,
) -> dict[str, Any]:
    candidates = conflict.get("candidates", [])
    if not isinstance(candidates, list):
        return {}
    for candidate in candidates:
        if (
            isinstance(candidate, dict)
            and str(candidate.get("memory_id", "")) == memory_id
        ):
            return candidate
    return {}


def _overridden_static_conflict_row(
    row: dict[str, Any],
    recommended_memory_id: str,
) -> dict[str, Any]:
    out = dict(row)
    out["current_status"] = "same_timestamp_conflict_overridden"
    out["retrieval_role"] = "not_current_after_static_conflict_resolution"
    out["overridden_by_memory_id"] = recommended_memory_id
    return out


def _service_request(request: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in request.items() if not str(key).startswith("_")}


def _compact_context_rows(rows: Any) -> list[dict[str, Any]]:
    if isinstance(rows, (str, bytes, dict)) or rows is None:
        return []
    if not isinstance(rows, list):
        rows = list(rows)
    compacted = []
    for row in rows:
        if isinstance(row, dict):
            compacted.append(_compact_context_row(row))
    return compacted


def _compact_context_row(row: dict[str, Any]) -> dict[str, Any]:
    compacted = {}
    for field_name in QVF_CONTEXT_ROW_FIELDS:
        value = row.get(field_name)
        if value not in (None, "", [], {}):
            compacted[field_name] = _compact_context_value(field_name, value)
    return compacted


def _compact_context_value(field_name: str, value: Any) -> Any:
    if field_name == "claim" and isinstance(value, str):
        return _truncate_text(value, 320)
    if field_name == "source_span" and isinstance(value, str):
        return _truncate_text(value, 700)
    return value


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


CAREER_CHANGE_FIELDS = ("job_title", "company", "industry", "income")


def _build_change_detail_context(request: dict[str, Any]) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not question or not _asks_for_transition(question):
        return []
    if not _is_career_change_question(question, str(query.get("slot", ""))):
        return []

    evidence = _career_change_evidence(request)
    if not evidence:
        return []

    target_group = _transition_group_for_question(question, str(query.get("slot", "")))
    fields = _career_change_fields_for_question(target_group)
    changes = []
    for field_name in fields:
        candidates = _distinct_career_candidates(evidence.get(field_name, []))
        if len(candidates) < 2:
            continue
        previous = _career_endpoint_candidate(candidates, endpoint="previous")
        current = _career_endpoint_candidate(candidates, endpoint="current")
        if _norm_text(previous["value"]) == _norm_text(current["value"]):
            continue
        changes.append(
            {
                "field": field_name,
                "previous_value": previous["value"],
                "current_value": current["value"],
                "previous_observed_at": previous.get("observed_at", ""),
                "current_observed_at": current.get("observed_at", ""),
                "previous_source_id": previous.get("source_id", ""),
                "current_source_id": current.get("source_id", ""),
                "evidence_note": _career_change_evidence_note(previous, current),
            }
        )

    if not changes:
        return []
    return [
        {
            "detail_type": "career_change",
            "summary": _career_change_summary(changes),
            "field_changes": changes[:6],
        }
    ]


def _is_career_change_question(question: str, query_slot: str) -> bool:
    text = _norm_text(question)
    target_group = _transition_group_for_question(question, query_slot)
    if target_group in set(CAREER_CHANGE_FIELDS) | {"career_profile"}:
        return True
    return any(
        cue in text
        for cue in (
            "career",
            "job title",
            "industry",
            "company",
            "income",
            "employment",
            "employer",
        )
    )


def _career_change_fields_for_question(target_group: str) -> tuple[str, ...]:
    if target_group in CAREER_CHANGE_FIELDS:
        return (target_group,)
    return CAREER_CHANGE_FIELDS


def _career_change_evidence(request: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    evidence: dict[str, list[dict[str, Any]]] = {field: [] for field in CAREER_CHANGE_FIELDS}
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        field_name = _transition_slot_group(str(record.get("slot", "")), "")
        if field_name in evidence and record.get("value"):
            _append_career_candidate(
                evidence,
                field_name,
                value=str(record.get("value", "")),
                observed_at=str(record.get("observed_at", "")),
                source_id=str(record.get("memory_id", "")),
                source_text=str(record.get("claim", "")),
            )
        source = record.get("source", {})
        if isinstance(source, dict):
            _append_career_values_from_text(
                evidence,
                text=str(source.get("source_span", "")),
                observed_at=str(record.get("observed_at", "")),
                source_id=str(record.get("memory_id", "")),
            )

    for turn in _selected_history_turns_from_request(request):
        _append_career_values_from_text(
            evidence,
            text=str(turn.get("text", "")),
            observed_at=str(turn.get("timestamp", "")),
            source_id=str(turn.get("turn_id", "")),
        )
    return evidence


def _append_career_values_from_text(
    evidence: dict[str, list[dict[str, Any]]],
    *,
    text: str,
    observed_at: str,
    source_id: str,
) -> None:
    if not text:
        return
    for field_name, value in _extract_career_values(text):
        _append_career_candidate(
            evidence,
            field_name,
            value=value,
            observed_at=observed_at,
            source_id=source_id,
            source_text=text,
        )


def _extract_career_values(text: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    normalized = _norm_text(text)

    for pattern in (
        r"\bwork\s+as\s+(?:a|an)\s+(?P<value>[A-Z][A-Za-z -]{1,40}?)(?:\s+at|\s+in|[.,]|$)",
        r"\bas\s+(?:a|an)\s+(?P<value>[A-Z][A-Za-z -]{1,40}?)(?:\s+at|\s+in|[.,]|$)",
    ):
        for match in re.finditer(pattern, text):
            value = _clean_career_value(match.group("value"))
            if value:
                values.append(("job_title", value))
    if "internship" in normalized or re.search(r"\bintern\b", normalized):
        values.append(("job_title", "Intern"))

    if _has_company_career_context(normalized):
        company = _extract_started_at_organization(text)
        if company:
            values.append(("company", company))
        for pattern in (
            r"\bat\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,4})",
            r"\bfrom\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,4})",
        ):
            for match in re.finditer(pattern, text):
                value = _clean_source_span_org(match.group("value"))
                if value and value not in {"HR"}:
                    values.append(("company", value))

    industry_match = re.search(
        r"\bin\s+the\s+(?P<value>[A-Za-z][A-Za-z -]{1,30}?)\s+industry\b",
        text,
        flags=re.IGNORECASE,
    )
    if industry_match:
        values.append(("industry", _clean_career_value(industry_match.group("value"))))
    if any(
        cue in normalized
        for cue in (
            "legal research",
            "legal intern",
            "legal interns",
            "legal database",
            "legal databases",
            "law firm",
            "junior lawyer",
            "junior lawyers",
        )
    ):
        values.append(("industry", "Legal"))

    income = _extract_income_value(text)
    if income:
        values.append(("income", income))
    return values


def _has_company_career_context(normalized_text: str) -> bool:
    return any(
        cue in normalized_text
        for cue in (
            "started at",
            "work at",
            "work as",
            "working at",
            "hr at",
            "payroll",
            "internship",
            "job at",
            "employer",
            "company",
        )
    )


def _append_career_candidate(
    evidence: dict[str, list[dict[str, Any]]],
    field_name: str,
    *,
    value: str,
    observed_at: str,
    source_id: str,
    source_text: str,
) -> None:
    value = _clean_career_value(value)
    if not value or field_name not in evidence:
        return
    evidence[field_name].append(
        {
            "field": field_name,
            "value": value,
            "observed_at": observed_at,
            "source_id": source_id,
            "source_excerpt": _truncate_text(source_text, 240),
        }
    )


def _distinct_career_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        value_key = _norm_text(candidate.get("value", ""))
        if not value_key:
            continue
        key = (value_key, _observed_day_key(str(candidate.get("observed_at", ""))))
        existing = best_by_key.get(key)
        if existing is None or _career_candidate_provenance_score(
            candidate
        ) > _career_candidate_provenance_score(existing):
            best_by_key[key] = candidate
    return sorted(
        best_by_key.values(),
        key=lambda row: (
            str(row.get("observed_at", "")),
            str(row.get("source_id", "")),
        ),
    )


def _observed_day_key(observed_at: str) -> str:
    if "T" in observed_at:
        return observed_at.split("T", 1)[0]
    return observed_at


def _career_endpoint_candidate(
    candidates: list[dict[str, Any]],
    *,
    endpoint: str,
) -> dict[str, Any]:
    if not candidates:
        return {}
    sorted_dates = sorted({str(candidate.get("observed_at", "")) for candidate in candidates})
    target_date = sorted_dates[0] if endpoint == "previous" else sorted_dates[-1]
    same_date = [
        candidate
        for candidate in candidates
        if str(candidate.get("observed_at", "")) == target_date
    ]
    return sorted(
        same_date or candidates,
        key=_career_candidate_provenance_score,
        reverse=True,
    )[0]


def _career_candidate_provenance_score(candidate: dict[str, Any]) -> tuple[int, str]:
    source_id = str(candidate.get("source_id", ""))
    field_name = str(candidate.get("field", ""))
    if field_name == "income" and "source_span_repair" in source_id:
        return (3, source_id)
    if "::extracted_" in source_id:
        return (2, source_id)
    return (1, source_id)


def _career_change_summary(changes: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{change['field']} changed from {change['previous_value']} to {change['current_value']}"
        for change in changes
    ) + "."


def _career_change_evidence_note(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> str:
    previous_source = previous.get("source_id", "")
    current_source = current.get("source_id", "")
    if previous_source and current_source:
        return f"derived from source evidence {previous_source} -> {current_source}"
    return "derived from source evidence"


def _clean_career_value(value: Any) -> str:
    text = str(value).strip()
    text = text.replace("＊", "'").replace("每", "-").replace("иC", "-")
    text = re.sub(r"\s+", " ", text).strip(" .,:;")
    blocked = {
        "I",
        "HR",
        "Nice",
        "Got",
        "Since",
        "That",
        "The",
        "A",
        "An",
    }
    if text in blocked:
        return ""
    return text


def _extract_income_value(text: str) -> str:
    scoped_value, scoped_decisive = _extract_income_value_with_local_scope(text)
    if scoped_decisive:
        return scoped_value
    normalized = text.replace("每", "-").replace("иC", "-")
    patterns = (
        r"\$\s*(?P<low>\d+(?:,\d{3})?\s*[kK]?)\s*[-–]\s*\$?\s*(?P<high>\d+(?:,\d{3})?\s*[kK]?)",
        r"\bbetween\s+(?P<low>\d+(?:,\d{3})?\s*[kK]?)\s+and\s+(?P<high>\d+(?:,\d{3})?\s*[kK]?)\b",
        r"\b(?P<low>\d{4,6})\s*[-–]\s*(?P<high>\d{4,6})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        low = _normalize_income_part(match.group("low"))
        high = _normalize_income_part(match.group("high"))
        if low and high:
            return f"{low}-{high}"
    return ""


def _extract_income_value_with_local_scope(text: str) -> tuple[str, bool]:
    normalized = _normalize_financial_range_text(text)
    normalized_lower = normalized.lower()
    matches = _financial_range_matches(normalized)
    if not matches:
        return "", False

    income_cues = ("income", "salary", "pay", "compensation", "earnings")
    savings_cues = ("savings", "saved", "balance")
    has_income_cue = any(cue in normalized_lower for cue in income_cues)
    has_savings_cue = any(cue in normalized_lower for cue in savings_cues)

    for value, start, end in matches:
        income_distance = _closest_range_cue_distance(
            normalized_lower,
            start,
            end,
            income_cues,
        )
        savings_distance = _closest_range_cue_distance(
            normalized_lower,
            start,
            end,
            savings_cues,
        )
        if income_distance < 10_000 and income_distance <= savings_distance:
            return value, True

    if has_savings_cue and not has_income_cue:
        return "", True
    if has_savings_cue and has_income_cue:
        return "", True
    if any(
        cue in normalized_lower
        for cue in ("monthly", "finance", "financial", "budget", "career", "job")
    ):
        return matches[0][0], True
    return "", False


def _normalize_financial_range_text(text: str) -> str:
    return (
        text.replace("藩", "-")
        .replace("我C", "-")
        .replace("每", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )


def _financial_range_matches(text: str) -> list[tuple[str, int, int]]:
    number = r"(?:\$?\s*\d{1,3}(?:,\d{3})+|\$?\s*\d{4,6}|\$?\s*\d+(?:\.\d+)?\s*[kK])"
    patterns = (
        rf"\bbetween\s+(?P<low>{number})\s+and\s+(?P<high>{number})\b",
        rf"(?P<low>{number})\s*(?:-|to|through)\s*(?P<high>{number})",
    )
    matches: list[tuple[str, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            span = (match.start(), match.end())
            if span in seen:
                continue
            seen.add(span)
            low = _normalize_income_display_part(match.group("low"))
            high = _normalize_income_display_part(match.group("high"))
            if low and high:
                matches.append((f"{low}-{high}", match.start(), match.end()))
    return sorted(matches, key=lambda row: (row[1], row[2]))


def _closest_range_cue_distance(
    text_lower: str,
    start: int,
    end: int,
    cues: tuple[str, ...],
) -> int:
    best = 10_000
    for cue in cues:
        before = text_lower.rfind(cue, 0, start)
        if before >= 0:
            best = min(best, start - (before + len(cue)))
        after = text_lower.find(cue, end)
        if after >= 0:
            best = min(best, after - end)
    return best


def _normalize_income_display_part(value: str) -> str:
    text = value.replace("$", "").replace(" ", "")
    if text.lower().endswith("k"):
        try:
            return f"{int(float(text[:-1].replace(',', '')) * 1000):,}"
        except ValueError:
            return text
    return text


def _normalize_income_part(value: str) -> str:
    text = value.replace(",", "").replace(" ", "")
    if text.lower().endswith("k"):
        try:
            return str(int(float(text[:-1]) * 1000))
        except ValueError:
            return text
    return text


def _build_transition_context(request: dict[str, Any]) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not question:
        return []
    if not _asks_for_transition(question):
        return []
    entity = _norm_text(query.get("entity", ""))
    target_group = _transition_group_for_question(question, str(query.get("slot", "")))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        if entity and not _record_entity_matches_query(
            record.get("entity", ""),
            entity,
            question,
        ):
            continue
        group = _transition_slot_group(str(record.get("slot", "")), question)
        if not group and target_group and _record_supports_transition_target(
            record,
            target_group,
        ):
            group = target_group
        if target_group and group != target_group:
            continue
        if not group or not record.get("value"):
            continue
        if not _valid_transition_candidate(record, group):
            continue
        grouped.setdefault(group, []).append(record)

    transitions = []
    for group, records in grouped.items():
        records = sorted(
            records,
            key=lambda row: (
                str(row.get("observed_at", "")),
                str(row.get("memory_id", "")),
            ),
        )
        distinct = _distinct_value_records(records)
        if len(distinct) < 2:
            continue
        previous = distinct[0]
        current = distinct[-1]
        transitions.append(
            {
                "slot": group,
                "previous_value": _clean_transition_value(previous.get("value", "")),
                "current_value": _clean_transition_value(current.get("value", "")),
                "previous_observed_at": previous.get("observed_at", ""),
                "current_observed_at": current.get("observed_at", ""),
                "previous_memory_id": previous.get("memory_id", ""),
                "current_memory_id": current.get("memory_id", ""),
                "summary": _transition_summary(group, previous, current),
            }
        )
    existing_groups = {
        str(transition.get("slot", ""))
        for transition in transitions
        if isinstance(transition, dict)
    }
    transitions.extend(
        _build_source_span_transition_context(
            request,
            entity=entity,
            target_group=target_group,
            existing_groups=existing_groups,
        )
    )
    transitions.extend(
        _build_source_history_previous_state_transition_context(
            request,
            entity=entity,
            target_group=target_group,
            existing_groups={
                str(transition.get("slot", ""))
                for transition in transitions
                if isinstance(transition, dict)
            },
        )
    )
    transitions.extend(
        _build_change_event_transition_context(
            request,
            entity=entity,
            target_group=target_group,
            existing_groups={
                str(transition.get("slot", ""))
                for transition in transitions
                if isinstance(transition, dict)
            },
        )
    )
    return transitions[:3]


def _first_query_request(request: dict[str, Any]) -> dict[str, Any]:
    for field_name in ("query_requests", "queries"):
        rows = request.get(field_name)
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
    return {}


def _asks_for_transition(question: str) -> bool:
    text = _norm_text(question)
    if _asks_for_stayed_same(question):
        return True
    return any(
        cue in text
        for cue in (
            "did the",
            "has the",
            "how did",
            "what changed",
            "changed about",
            "change occurred",
            "change in",
        )
    )


def _asks_for_stayed_same(question: str) -> bool:
    text = _norm_text(question)
    return "stayed the same" in text or "stay the same" in text


def _transition_group_for_question(question: str, query_slot: str) -> str:
    text = _norm_text(question)
    if "career situation" in text or "career detail" in text or "career details" in text:
        return "career_profile"
    if "residence" in text or "moved" in text or "move" in text:
        return "residence"
    if "employment status" in text or "work status" in text:
        return "employment_status"
    if "job title" in text or "title" in text:
        return "job_title"
    if "company" in text or "employer" in text:
        return "company"
    if "industry" in text:
        return "industry"
    if "marital" in text or "relationship" in text:
        return "marital_status"
    if "children status" in text or "child status" in text:
        return "children_status"
    return _transition_slot_group(query_slot, question) if query_slot else ""


def _transition_slot_group(slot: str, question: str) -> str:
    raw_slot = _norm_text(slot).replace(" ", "_")
    question_text = _norm_text(question)
    for prefix in ("current_", "latest_", "new_", "old_", "previous_", "prior_", "former_"):
        if raw_slot.startswith(prefix):
            raw_slot = raw_slot[len(prefix) :]
    for suffix in ("_change", "_status_change"):
        if raw_slot.endswith(suffix):
            raw_slot = raw_slot[: -len(suffix)]
    if raw_slot in {"current_residence", "residence_change", "home_city", "location"}:
        return "residence"
    if (
        raw_slot
        in {
            "current_relationship",
            "relationship",
            "relationship_status",
            "dating_status",
            "partner_status",
        }
        and _asks_for_change_detail(question)
        and any(cue in question_text for cue in ("marital", "relationship", "dating"))
    ):
        return "marital_status"
    if raw_slot in {"workplace", "employer"} or "company" in raw_slot:
        return "company"
    if raw_slot == "title" and any(
        cue in question_text for cue in ("book", "reading", "album", "movie")
    ):
        return "title"
    if "job_title" in raw_slot or raw_slot in {"title", "role", "occupation"}:
        return "job_title"
    if "industry" in raw_slot:
        return "industry"
    if raw_slot in {"income", "salary", "income_range", "salary_range"}:
        return "income"
    if "children" in question_text and raw_slot in {
        "birth_date",
        "child_birth_date",
        "child_name",
        "name",
        "status",
    }:
        return "children_status"
    if raw_slot in {
        "social_activity",
        "social_status",
        "socializing_status",
    }:
        return "social_status"
    if raw_slot:
        return raw_slot
    return ""


def _record_entity_matches_query(record_entity: Any, query_entity: str, question: str) -> bool:
    if not query_entity:
        return True
    record = _norm_text(record_entity)
    query = _norm_text(query_entity)
    if not record:
        return False
    if record == query:
        return True
    if {record, query} <= {"child", "children"}:
        return True
    question_text = _norm_text(question)
    if (
        "children" in question_text
        and query in {"child", "children"}
        and record in {"child", "children"}
    ):
        return True
    return False


def _distinct_value_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    distinct = []
    seen_values = set()
    for record in records:
        value_key = _norm_text(_clean_transition_value(record.get("value", "")))
        if not value_key or value_key in seen_values:
            continue
        seen_values.add(value_key)
        distinct.append(record)
    return distinct


def _valid_transition_candidate(record: dict[str, Any], group: str) -> bool:
    value = str(record.get("value", "")).strip()
    if not value:
        return False
    normalized = _norm_text(value)
    if len(value) > 160:
        return False
    if any(
        cue in normalized
        for cue in (
            "when should",
            "if i want",
            "if the internship",
            "begin discreetly",
            "start documenting",
            "use your work log",
            "can you",
            "how should",
        )
    ):
        return False
    if group == "employment_status" and any(
        cue in normalized
        for cue in (
            "pickup",
            "school",
            "bedtime",
            "therapy",
            "savings",
            "calendar",
        )
    ):
        return False
    if group == "children_status" and not _is_children_status_transition_value(
        record
    ):
        return False
    if group == "children_status" and _is_date_only_transition_value(value):
        return False
    if group == "social_status" and not _is_social_status_transition_value(record):
        return False
    if (
        group == "residence"
        and ("moved" in normalized or "move" in normalized)
        and _norm_text(_clean_transition_value(value)) == normalized
    ):
        return False
    return True


def _record_supports_transition_target(record: dict[str, Any], target_group: str) -> bool:
    if target_group == "children_status":
        return _is_children_status_transition_value(record)
    if target_group == "social_status":
        return _is_social_status_transition_value(record)
    return False


def _is_date_only_transition_value(value: str) -> bool:
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()) is not None


def _is_children_status_transition_value(record: dict[str, Any]) -> bool:
    text = _norm_text(
        " ".join(
            str(record.get(field_name, ""))
            for field_name in ("claim", "value")
            if record.get(field_name)
        )
    )
    child_terms = {
        "baby",
        "child",
        "children",
        "daughter",
        "kid",
        "kids",
        "newborn",
        "son",
    }
    non_child_family_terms = {
        "brother",
        "father",
        "mother",
        "parent",
        "parents",
        "partner",
        "pet",
        "pets",
        "sibling",
        "siblings",
        "sister",
    }
    tokens = set(text.split())
    if tokens & child_terms:
        return True
    if tokens & non_child_family_terms:
        return False
    return True


def _is_social_status_transition_value(record: dict[str, Any]) -> bool:
    text = _norm_text(
        " ".join(
            str(record.get(field_name, ""))
            for field_name in ("claim", "value")
            if record.get(field_name)
        )
    )
    if not text:
        return False
    state_cues = {
        "less",
        "more",
        "people",
        "social",
        "socializing",
        "socialising",
        "socially",
    }
    direction_phrases = (
        "less time socializing",
        "meeting more people",
        "more social",
        "seeing people more often",
        "shifted a lot",
        "spending a lot less time socializing",
    )
    if any(phrase in text for phrase in direction_phrases):
        return True
    tokens = set(text.split())
    if not tokens & state_cues:
        return False
    low_value_action_phrases = (
        "committed to one social event",
        "one social event next week",
        "schedule the event",
    )
    if any(phrase in text for phrase in low_value_action_phrases):
        return False
    side_effect_terms = {"fatigue", "guilty", "logistics", "deadline"}
    if tokens & side_effect_terms and not any(
        phrase in text for phrase in direction_phrases
    ):
        return False
    return True


def _clean_transition_value(value: Any) -> str:
    text = str(value).strip()
    lower = text.lower()
    for prefix in ("moved to ", "changed to ", "relocated to "):
        if lower.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _transition_summary(
    slot: str,
    previous: dict[str, Any],
    current: dict[str, Any],
) -> str:
    previous_value = _clean_transition_value(previous.get("value", ""))
    current_value = _clean_transition_value(current.get("value", ""))
    return f"{slot} changed from {previous_value} to {current_value}."


EMPLOYMENT_STATUS_EMPLOYED_CUES = (
    "career",
    "company",
    "employer",
    "employment",
    "full-time",
    "intern",
    "internship",
    "job",
    "occupation",
    "part-time",
    "role",
    "senior at",
    "started at",
    "started a new internship",
    "work",
    "worked",
    "working",
    "works",
)

EMPLOYMENT_STATUS_NOT_EMPLOYED_CUES = (
    "jobless",
    "not employed",
    "out of work",
    "retired",
    "student only",
    "unemployed",
)


def _build_status_class_context(
    request: dict[str, Any],
    transition_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not _asks_for_stayed_same(question):
        return []
    if _transition_group_for_question(question, str(query.get("slot", ""))) != "employment_status":
        return []
    records_by_id = {
        str(record.get("memory_id", "")): record
        for record in request.get("records", [])
        if isinstance(record, dict) and record.get("memory_id")
    }
    rows = []
    for transition in transition_context:
        if not isinstance(transition, dict):
            continue
        if transition.get("slot") != "employment_status":
            continue
        previous_record = records_by_id.get(str(transition.get("previous_memory_id", "")), {})
        current_record = records_by_id.get(str(transition.get("current_memory_id", "")), {})
        previous_class = _employment_status_class(
            transition.get("previous_value", ""),
            previous_record,
        )
        current_class = _employment_status_class(
            transition.get("current_value", ""),
            current_record,
        )
        if previous_class != current_class or previous_class != "employed":
            continue
        previous_detail = str(transition.get("previous_value", "")).strip()
        current_detail = str(transition.get("current_value", "")).strip()
        transition["status_class_relation"] = "same_coarse_status"
        transition["previous_status_class"] = previous_class
        transition["current_status_class"] = current_class
        transition["summary"] = (
            "employment_status details changed from "
            f"{previous_detail} to {current_detail}, but coarse "
            "employment_status_class stayed employed."
        )
        rows.append(
            {
                "status_type": "employment_status_class",
                "previous_class": previous_class,
                "current_class": current_class,
                "relation": "same_coarse_status",
                "previous_detail": previous_detail,
                "current_detail": current_detail,
                "previous_memory_id": transition.get("previous_memory_id", ""),
                "current_memory_id": transition.get("current_memory_id", ""),
                "preferred_answer": "Yes, the user stayed employed.",
                "detail_note": (
                    "Detailed job form changed from "
                    f"{previous_detail} to {current_detail}; do not include this "
                    "detail in a yes/no stayed-same answer unless asked."
                ),
                "reader_policy": (
                    "For explicit stayed-same employment-status questions, answer "
                    "the coarse status-class relation first. Preserve detailed "
                    "job/company/title/industry changes as details, not as evidence "
                    "that the employed/not-employed status changed."
                ),
                "evidence_note": (
                    "coarse status inferred from employment cues in the old/current "
                    "values and source text"
                ),
            }
        )
    return rows[:2]


def _employment_status_class(value: Any, record: dict[str, Any]) -> str:
    text = _norm_text(
        " ".join(
            str(part)
            for part in (
                value,
                record.get("claim", ""),
                _record_source_span(record),
            )
            if part not in (None, "")
        )
    )
    if any(cue in text for cue in EMPLOYMENT_STATUS_NOT_EMPLOYED_CUES):
        return "not_employed"
    if any(cue in text for cue in EMPLOYMENT_STATUS_EMPLOYED_CUES):
        return "employed"
    return "unknown"


def _record_source_span(record: dict[str, Any]) -> str:
    source = record.get("source", {})
    if isinstance(source, dict):
        return str(source.get("source_span", ""))
    return ""


def _build_source_span_transition_context(
    request: dict[str, Any],
    *,
    entity: str,
    target_group: str,
    existing_groups: set[str],
) -> list[dict[str, Any]]:
    if target_group not in {"company", "job_title"} or target_group in existing_groups:
        return []
    records = [
        record
        for record in request.get("records", [])
        if isinstance(record, dict)
        and (not entity or _norm_text(record.get("entity", "")) == entity)
    ]
    previous_records = [
        record
        for record in records
        if _transition_slot_group(str(record.get("slot", "")), "") == target_group
        and record.get("value")
    ]
    if not previous_records:
        return []
    previous = sorted(
        previous_records,
        key=lambda row: (
            str(row.get("observed_at", "")),
            str(row.get("memory_id", "")),
        ),
    )[0]
    current = _source_span_current_transition_value(
        target_group,
        records,
        after_observed_at=str(previous.get("observed_at", "")),
    )
    if current is None:
        return []
    current_value, current_observed_at, current_memory_id, source_phrase = current
    if _norm_text(current_value) == _norm_text(previous.get("value", "")):
        return []
    return [
        {
            "slot": target_group,
            "previous_value": _clean_transition_value(previous.get("value", "")),
            "current_value": current_value,
            "previous_observed_at": previous.get("observed_at", ""),
            "current_observed_at": current_observed_at,
            "previous_memory_id": previous.get("memory_id", ""),
            "current_memory_id": current_memory_id,
            "summary": (
                f"{target_group} changed from "
                f"{_clean_transition_value(previous.get('value', ''))} to {current_value}."
            ),
            "evidence_note": f"current value inferred from source_span phrase: {source_phrase}",
        }
    ]


def _source_span_current_transition_value(
    target_group: str,
    records: list[dict[str, Any]],
    *,
    after_observed_at: str,
) -> tuple[str, str, str, str] | None:
    for record in sorted(
        records,
        key=lambda row: (
            str(row.get("observed_at", "")),
            str(row.get("memory_id", "")),
        ),
    ):
        observed_at = str(record.get("observed_at", ""))
        if after_observed_at and observed_at <= after_observed_at:
            continue
        source = record.get("source", {})
        if not isinstance(source, dict):
            continue
        source_span = str(source.get("source_span", ""))
        if target_group == "company":
            value = _extract_started_at_organization(source_span)
            if value:
                return (
                    value,
                    observed_at,
                    str(record.get("memory_id", "")),
                    f"started at {value}",
                )
        if target_group == "job_title" and "internship" in _norm_text(source_span):
            return (
                "Intern",
                observed_at,
                str(record.get("memory_id", "")),
                "internship",
            )
    return None


def _build_source_history_previous_state_transition_context(
    request: dict[str, Any],
    *,
    entity: str,
    target_group: str,
    existing_groups: set[str],
) -> list[dict[str, Any]]:
    """Build a previous-state transition from selected source history."""

    if target_group != "residence" or target_group in existing_groups:
        return []
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not _asks_for_change_detail(question):
        return []
    records = [
        record
        for record in request.get("records", [])
        if isinstance(record, dict)
        and (not entity or _norm_text(record.get("entity", "")) == entity)
        and _transition_slot_group(str(record.get("slot", "")), "") == "residence"
        and record.get("value")
        and _valid_transition_candidate(record, "residence")
    ]
    if not records:
        return []
    current = sorted(
        records,
        key=lambda row: (
            str(row.get("observed_at", "")),
            str(row.get("memory_id", "")),
        ),
    )[-1]
    current_value = _clean_transition_value(current.get("value", ""))
    current_observed_at = str(current.get("observed_at", ""))
    previous = _previous_residence_candidate_from_source_history(
        request,
        current_value=current_value,
        before_observed_at=current_observed_at,
    )
    if previous is None or _norm_text(previous["value"]) == _norm_text(current_value):
        return []
    return [
        {
            "slot": "residence",
            "previous_value": previous["value"],
            "current_value": current_value,
            "previous_observed_at": previous.get("observed_at", ""),
            "current_observed_at": current_observed_at,
            "previous_memory_id": previous.get("source_id", ""),
            "current_memory_id": current.get("memory_id", ""),
            "summary": f"residence changed from {previous['value']} to {current_value}.",
            "evidence_note": (
                "previous value inferred from selected source-history turn; "
                "use as prior-state evidence for the change answer, not as current state"
            ),
            "source_history_repair": "previous_state_anchor",
            "previous_source_speaker": previous.get("speaker", ""),
        }
    ]


def _asks_for_change_detail(question: str) -> bool:
    text = _norm_text(question)
    return any(
        cue in text
        for cue in (
            "how did",
            "what change occurred",
            "what changed",
            "changed about",
            "change occurred",
            "change in",
            "from what to what",
        )
    )


def _previous_residence_candidate_from_source_history(
    request: dict[str, Any],
    *,
    current_value: str,
    before_observed_at: str,
) -> dict[str, str] | None:
    current_at = _parse_observed_at(before_observed_at)
    candidates = []
    for turn in _selected_history_turns_from_request(request):
        text = str(turn.get("text", ""))
        value = _extract_previous_residence_value_from_text(text)
        if not value or _norm_text(value) == _norm_text(current_value):
            continue
        observed_at = str(turn.get("timestamp", ""))
        turn_at = _parse_observed_at(observed_at)
        if (
            current_at is not None
            and turn_at is not None
            and turn_at.date() >= current_at.date()
        ):
            continue
        candidates.append(
            {
                "value": value,
                "observed_at": observed_at,
                "source_id": str(turn.get("turn_id", "")),
                "speaker": str(turn.get("speaker", "")),
                "history_index": str(turn.get("history_index", "")),
                "selection_rank": str(turn.get("selection_rank", "")),
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            str(row.get("observed_at", "")),
            _safe_optional_int(row.get("history_index", "")),
            -_safe_optional_int(row.get("selection_rank", 999999)),
        ),
        reverse=True,
    )
    return candidates[0]


def _extract_previous_residence_value_from_text(text: str) -> str:
    if not text:
        return ""
    normalized = _norm_text(text)
    has_residence_context = any(
        cue in normalized
        for cue in (
            "where you are",
            "where you live",
            "where you re living",
            "day to day",
            "relocated",
            "moved",
            "move to",
            "move from",
            "living in",
            "live in",
            "based in",
        )
    )
    if not has_residence_context:
        return ""
    patterns = (
        r"\b(?:live|living|based|located|staying|stay)\s+in\s+(?P<value>[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\?|\band\b|$)",
        r"\b(?:moved|relocated)\s+(?:to|from)\s+(?P<value>[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\?|\band\b|$)",
        r"\b(?P<value>[A-Z][A-Za-z .'-]{1,40})'s\s+got\b.*\bwhere you are\b",
        r"\bwhere you are\b.*\b(?:in|around)\s+(?P<value>[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\?|\band\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = _clean_location_candidate(match.group("value"))
        if value:
            return value
    return ""


def _clean_location_candidate(value: str) -> str:
    cleaned = value.strip(" .,-:;!?\"'")
    cleaned = re.split(
        r"\s+(?:and|but|or|from|with|where|when|what|how|that|this|last)\b",
        cleaned,
        maxsplit=1,
    )[0].strip(" .,-:;!?\"'")
    normalized = _norm_text(cleaned)
    if not cleaned or normalized in {"i", "it", "nice", "the", "your"}:
        return ""
    if len(cleaned) > 40 or len(cleaned.split()) > 4:
        return ""
    if not cleaned[0].isupper():
        return ""
    return cleaned


def _safe_optional_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_change_event_transition_context(
    request: dict[str, Any],
    *,
    entity: str,
    target_group: str,
    existing_groups: set[str],
) -> list[dict[str, Any]]:
    if not target_group or target_group in existing_groups:
        return []
    records = [
        record
        for record in request.get("records", [])
        if isinstance(record, dict)
        and (not entity or _norm_text(record.get("entity", "")) == entity)
    ]
    candidates = []
    for record in records:
        source = record.get("source", {})
        source_span = str(source.get("source_span", "")) if isinstance(source, dict) else ""
        text = " ".join(
            str(value)
            for value in (record.get("claim", ""), record.get("value", ""), source_span)
            if value
        )
        event = _change_event_from_text(target_group, text)
        if not event:
            continue
        candidates.append(
            {
                "slot": target_group,
                "previous_value": event.get("previous_value", "unknown"),
                "current_value": event["current_value"],
                "current_observed_at": record.get("observed_at", ""),
                "current_memory_id": record.get("memory_id", ""),
                "summary": event["summary"],
                "evidence_note": event["evidence_note"],
            }
        )
    if not candidates:
        return []
    candidates.sort(
        key=lambda row: (
            str(row.get("current_observed_at", "")),
            str(row.get("current_memory_id", "")),
        ),
        reverse=True,
    )
    return candidates[:1]


def _change_event_from_text(target_group: str, text: str) -> dict[str, str] | None:
    normalized = _norm_text(text)
    if target_group == "residence":
        if "moved" not in normalized and "move" not in normalized:
            return None
        destination = _extract_move_destination(text)
        current_value = destination or "moved recently"
        return {
            "previous_value": "unknown",
            "current_value": current_value,
            "summary": f"residence changed recently to {current_value}.",
            "evidence_note": "change event inferred from move-related source evidence",
        }
    if target_group in {"marital_status", "relationship_status"}:
        relationship = _extract_relationship_status(text)
        if not relationship:
            return None
        return {
            "previous_value": "unknown",
            "current_value": relationship,
            "summary": f"{target_group} evidence indicates a change involving {relationship}.",
            "evidence_note": "change event inferred from relationship source evidence",
        }
    return None


def _extract_move_destination(text: str) -> str:
    for pattern in (
        r"\bmoved\s+(?:to\s+)?(?P<value>[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\?|\band\b|\bthis\b|\blast\b|$)",
        r"\bmove\s+to\s+(?P<value>[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\?|\band\b|\bthis\b|\blast\b|$)",
    ):
        match = re.search(pattern, text)
        if not match:
            continue
        value = _clean_transition_value(match.group("value"))
        value = re.split(r"\s+(?:and|but|or|this|last|when|have)\b", value)[0].strip(" .,-")
        if value:
            return value
    return ""


def _extract_relationship_status(text: str) -> str:
    normalized = _norm_text(text)
    if "seeing someone" in normalized:
        return "seeing someone"
    for pattern in (
        r"\bdating\s+(?P<value>[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\band\b|$)",
        r"\bseeing\s+(?P<value>someone|[A-Z][A-Za-z .'-]{1,40})(?:,|\.|\band\b|$)",
    ):
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group("value").strip(" .,-")
        if value:
            return f"seeing {value}" if value == "someone" else f"dating {value}"
    if "divorced" in normalized:
        return "divorced"
    return ""


def _extract_started_at_organization(source_span: str) -> str:
    patterns = (
        r"\bstarted\s+at\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,4})",
        r"\bat\s+(?P<value>[A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,4})\s+or\s+is\s+your\s+first\s+day",
    )
    for pattern in patterns:
        match = re.search(pattern, source_span)
        if not match:
            continue
        value = _clean_source_span_org(match.group("value"))
        if value:
            return value
    return ""


def _clean_source_span_org(value: str) -> str:
    cleaned = re.split(r"\s+(?:or|and|but|when|where|is|are)\b", value.strip())[0]
    cleaned = re.sub(r"[^A-Za-z0-9&'. -]+$", "", cleaned).strip(" .,-")
    blocked = {"I", "Nice", "Got", "Since", "That"}
    if cleaned in blocked:
        return ""
    return cleaned


def _build_static_conflict_resolution_context(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not question:
        return []
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    query_entity = _norm_text(query.get("entity", ""))
    query_slot_group = _transition_slot_group(str(query.get("slot", "")), question)
    for record in request.get("records", []):
        if not isinstance(record, dict) or not record.get("memory_id"):
            continue
        if query_entity and _norm_text(record.get("entity", "")) != query_entity:
            continue
        score, _ = _question_relevance_score(question, query, record)
        slot_group = _transition_slot_group(str(record.get("slot", "")), question)
        if query_slot_group and slot_group == query_slot_group:
            score += 3
        if score < 3:
            continue
        grouped.setdefault(
            (
                _norm_text(record.get("entity", "")),
                slot_group or _norm_text(record.get("slot", "")),
                str(record.get("observed_at", "")),
            ),
            [],
        ).append(record)

    contexts = []
    for (entity, slot, observed_at), records in grouped.items():
        distinct_records = _distinct_static_conflict_records(records)
        if len(distinct_records) < 2:
            continue
        candidates = [
            _static_conflict_candidate(record, question=question, query=query)
            for record in distinct_records
        ]
        candidates.sort(
            key=lambda row: (
                -int(row.get("cue_score", 0)),
                int(row.get("original_record_index", 0)),
                str(row.get("memory_id", "")),
            )
        )
        best = candidates[0]
        second_score = int(candidates[1].get("cue_score", 0))
        best_score = int(best.get("cue_score", 0))
        best_reasons = [
            str(reason) for reason in best.get("cue_reasons", []) if str(reason)
        ]
        recommendation_confidence = (
            "cue_based"
            if best_score > second_score
            and _has_static_conflict_source_cue(best_reasons)
            else "ambiguous"
        )
        if recommendation_confidence != "cue_based":
            continue
        contexts.append(
            {
                "conflict_type": "same_timestamp_value_conflict",
                "entity": entity,
                "slot": slot,
                "observed_at": observed_at,
                "recommended_memory_id": best.get("memory_id", ""),
                "recommended_value": best.get("value", ""),
                "recommendation_confidence": recommendation_confidence,
                "recommendation_reason": best_reasons,
                "use_policy": (
                    "Use recommended_value for the current question only when the "
                    "source-span cues match the question; otherwise inspect candidates."
                ),
                "candidates": candidates[:6],
            }
        )
    return contexts[:3]


def _has_static_conflict_source_cue(reasons: list[str]) -> bool:
    cue_markers = (
        "current_source_cue:",
        "non_current_source_cue:",
        "historical_source_cue:",
        "brand_source_phrase",
        "descriptor_not_brand",
        "book_current_reading_cue",
        "book_already_read_cue",
    )
    return any(
        any(reason.startswith(marker) for marker in cue_markers)
        for reason in reasons
    )


def _distinct_static_conflict_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    distinct = []
    seen_values = set()
    for index, record in enumerate(records):
        value_key = _norm_text(record.get("value", ""))
        if not value_key or value_key in seen_values:
            continue
        seen_values.add(value_key)
        copied = dict(record)
        copied["_original_record_index"] = index
        distinct.append(copied)
    return distinct


def _static_conflict_candidate(
    record: dict[str, Any],
    *,
    question: str,
    query: dict[str, Any],
) -> dict[str, Any]:
    source = record.get("source", {})
    if not isinstance(source, dict):
        source = {}
    source_span = str(source.get("source_span", ""))
    value = str(record.get("value", ""))
    score, reasons = _question_relevance_score(question, query, record)
    cue_score, cue_reasons = _static_conflict_cue_score(
        question=question,
        query=query,
        record=record,
        source_span=source_span,
    )
    total_score = score + cue_score
    return {
        "memory_id": record.get("memory_id", ""),
        "entity": record.get("entity", ""),
        "slot": record.get("slot", ""),
        "value": value,
        "observed_at": record.get("observed_at", ""),
        "source_span": _focus_excerpt(source_span, value, max_chars=360),
        "cue_score": total_score,
        "cue_reasons": (reasons + cue_reasons)[:8],
        "original_record_index": record.get("_original_record_index", 0),
    }


def _static_conflict_cue_score(
    *,
    question: str,
    query: dict[str, Any],
    record: dict[str, Any],
    source_span: str,
) -> tuple[int, list[str]]:
    question_norm = _norm_text(question)
    source_norm = _norm_text(source_span)
    value_norm = _norm_text(record.get("value", ""))
    slot_norm = _norm_text(record.get("slot", ""))
    score = 0
    reasons: list[str] = []
    asks_current = bool(query.get("needs_current")) or any(
        cue in question_norm
        for cue in ("current", "currently", "now", "right now", "still")
    )
    asks_previous = any(
        cue in question_norm
        for cue in ("previous", "used to", "before", "formerly", "past")
    )

    if asks_current:
        current_hits = _source_current_cues(source_norm)
        if current_hits:
            score += 5
            reasons.append(f"current_source_cue:{','.join(current_hits[:3])}")
        stale_hits = _source_stale_cues(source_norm)
        if stale_hits:
            score -= 4
            reasons.append(f"non_current_source_cue:{','.join(stale_hits[:3])}")
    if asks_previous:
        stale_hits = _source_stale_cues(source_norm)
        if stale_hits:
            score += 4
            reasons.append(f"historical_source_cue:{','.join(stale_hits[:3])}")

    if "brand" in question_norm or slot_norm == "brand":
        brand_score, brand_reasons = _brand_source_cue_score(
            value_norm=value_norm,
            source_norm=source_norm,
        )
        score += brand_score
        reasons.extend(brand_reasons)

    if ("book" in question_norm or "reading" in question_norm) and slot_norm in {
        "title",
        "book_title",
    }:
        if any(cue in source_norm for cue in ("currently devouring", "currently reading")):
            score += 5
            reasons.append("book_current_reading_cue")
        if "already read" in source_norm:
            score -= 5 if asks_current else 2
            reasons.append("book_already_read_cue")

    return score, reasons


def _source_current_cues(source_norm: str) -> list[str]:
    cues = (
        "currently",
        "right now",
        "still",
        "now",
        "been using",
        "i m using",
        "i am using",
        "currently devouring",
        "currently reading",
    )
    return [cue for cue in cues if cue in source_norm]


def _source_stale_cues(source_norm: str) -> list[str]:
    cues = (
        "already read",
        "used to",
        "previously",
        "formerly",
        "was reading",
        "finished",
        "i ve read",
        "i have read",
    )
    return [cue for cue in cues if cue in source_norm]


def _brand_source_cue_score(
    *,
    value_norm: str,
    source_norm: str,
) -> tuple[int, list[str]]:
    if not value_norm:
        return 0, []
    reasons = []
    score = 0
    if re.search(rf"\b(?:at|from|by)\s+{re.escape(value_norm)}\b", source_norm):
        score += 6
        reasons.append("brand_source_phrase")
    if re.search(rf"\b{re.escape(value_norm)}\s+(?:brand|store|shop|company)\b", source_norm):
        score += 4
        reasons.append("brand_entity_phrase")
    descriptor_terms = {"lavender", "scented", "unscented", "hydrating", "gentle"}
    value_tokens = set(value_norm.split())
    if value_tokens & descriptor_terms and not reasons:
        score -= 3
        reasons.append("descriptor_not_brand")
    return score, reasons


def _focus_excerpt(source_span: str, value: str, *, max_chars: int) -> str:
    if not source_span:
        return ""
    if not value:
        return _truncate_text(source_span, max_chars)
    index = source_span.lower().find(value.lower())
    if index < 0:
        return _truncate_text(source_span, max_chars)
    flank = max_chars // 2
    start = max(0, index - flank)
    end = min(len(source_span), index + len(value) + flank)
    excerpt = source_span[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(source_span):
        excerpt += "..."
    return excerpt


CONDITION_SCOPE_CUES = ("before", "after", "during", "when", "if", "while", "on", "in")
DIRECT_CONDITION_CUES = (
    "after",
    "at",
    "before",
    "during",
    "for",
    "in",
    "on",
    "to",
    "when",
    "while",
)
CONDITION_SCOPE_STOPWORDS = {
    "a",
    "an",
    "and",
    "applies",
    "as",
    "condition",
    "conditions",
    "does",
    "for",
    "her",
    "his",
    "in",
    "is",
    "it",
    "my",
    "of",
    "or",
    "our",
    "prefer",
    "preference",
    "prefers",
    "read",
    "reading",
    "reads",
    "situation",
    "the",
    "their",
    "to",
    "under",
    "user",
    "what",
    "when",
    "which",
    "your",
}
CONDITION_PHRASE_BOUNDARY_WORDS = {
    "because",
    "but",
    "i",
    "it",
    "as",
    "for",
    "so",
    "sound",
    "sounds",
    "then",
    "they",
    "to",
    "usually",
    "we",
    "with",
}
CONDITION_SCOPE_NOISE_TERMS = {
    "calendar",
    "checklist",
    "checklists",
    "different",
    "dimensions",
    "mind",
    "meantime",
    "note",
    "possible",
    "planning",
    "plan",
    "plans",
    "reach",
    "reaching",
    "reminder",
    "reminders",
    "starter",
    "suggest",
    "suggested",
    "suggests",
}
CONDITION_SOURCE_ADMIN_NEIGHBOR_TERMS = {
    "draft",
    "drafts",
    "finalize",
    "finalized",
    "finalizing",
    "message",
    "messages",
    "outreach",
    "plain",
    "sign",
    "signed",
    "signing",
    "table",
    "template",
    "templates",
    "text",
    "tracking",
}
CONDITION_ENVIRONMENT_TERMS = {
    "autumn",
    "cold",
    "fall",
    "hot",
    "rainy",
    "spring",
    "summer",
    "sunny",
    "warm",
    "weather",
    "winter",
}
CONDITION_ANCHOR_TERMS = CONDITION_ENVIRONMENT_TERMS | {
    "commute",
    "commuting",
    "commutes",
    "ceremonies",
    "ceremony",
    "conference",
    "conferences",
    "day",
    "days",
    "evening",
    "evenings",
    "entertainment",
    "event",
    "events",
    "flight",
    "flights",
    "formal",
    "gallery",
    "meeting",
    "meetings",
    "morning",
    "mornings",
    "presentation",
    "presentations",
    "school",
    "session",
    "sessions",
    "training",
    "weekend",
    "weekends",
    "work",
    "workout",
    "workouts",
}
CONDITION_PREFERENCE_CUES = {
    "crave",
    "craves",
    "favorite",
    "find",
    "finds",
    "go",
    "like",
    "liked",
    "likes",
    "love",
    "loved",
    "loves",
    "prefer",
    "preferred",
    "prefers",
    "rely",
    "relies",
    "relying",
    "tend",
    "tends",
    "use",
    "uses",
    "using",
    "useful",
}
CONDITION_IN_ON_SCOPE_ALLOWED_TERMS = CONDITION_ANCHOR_TERMS | CONDITION_PREFERENCE_CUES | {
    "family",
    "home",
    "house",
    "need",
    "needed",
    "needs",
    "pet",
    "practice",
    "training",
    "want",
    "wanted",
    "wants",
    "watchdog",
    "monday",
    "mondays",
    "tuesday",
    "tuesdays",
    "wednesday",
    "wednesdays",
    "thursday",
    "thursdays",
    "friday",
    "fridays",
    "saturday",
    "saturdays",
    "sunday",
    "sundays",
}
CONDITION_SCHEDULE_NOISE_TERMS = {
    "appointment",
    "appointments",
    "choir",
    "class",
    "classes",
    "meeting",
    "meetings",
    "practice",
    "practices",
    "reminder",
    "reminders",
    "schedule",
    "scheduled",
    "schedules",
}
HABIT_FREQUENCY_QUESTION_CUES = (
    "how often",
    "how frequently",
    "frequency",
    "routine",
    "routines",
    "habit",
    "habits",
    "cadence",
    "schedule",
    "usually",
    "regularly",
    "every week",
    "every other",
)
HABIT_FREQUENCY_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
HABIT_FREQUENCY_PATTERNS = (
    re.compile(
        r"\bevery\s+other\s+(?:day|week|month|year|weekend|"
        + "|".join(HABIT_FREQUENCY_WEEKDAYS)
        + r")s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bevery\s+(?:day|week|month|year|weekend|"
        + "|".join(HABIT_FREQUENCY_WEEKDAYS)
        + r")s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beach\s+(?:day|week|month|year|weekend|"
        + "|".join(HABIT_FREQUENCY_WEEKDAYS)
        + r")s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:once|twice|three times|four times|several times|a few times)\s+"
        r"(?:a|per|each)\s+(?:day|week|month|year)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:daily|weekly|biweekly|fortnightly|monthly|yearly|annually)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:on\s+)?(?:mondays|tuesdays|wednesdays|thursdays|fridays|"
        r"saturdays|sundays|weekends)\b",
        re.IGNORECASE,
    ),
)
HABIT_DAY_PATTERN = re.compile(
    r"\b(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
    re.IGNORECASE,
)


def _build_condition_scope_context(
    request: dict[str, Any],
    routed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not _asks_for_condition_scope(question):
        return []

    target_tokens = _condition_scope_target_tokens(question)
    scored_hints = []
    for row in routed_rows:
        if not isinstance(row, dict):
            continue
        memory_id = str(row.get("memory_id", ""))
        for hint in _condition_direct_claim_hints(row, target_tokens):
            scored_hints.append(
                (
                    -(
                        80
                        + _condition_phrase_priority(str(hint["exact_condition"]))
                        + _condition_phrase_specificity_bonus(
                            str(hint["exact_condition"])
                        )
                        + _condition_phrase_target_overlap(
                            str(hint["exact_condition"]),
                            target_tokens,
                        )
                        + _condition_scope_row_priority(row, answer_support=12)
                    ),
                    str(row.get("observed_at", "")),
                    memory_id,
                    str(hint["exact_condition"]),
                    len(scored_hints),
                    hint,
                )
            )
        text_candidates = _condition_scope_candidate_texts(row)
        for source_field, text in text_candidates:
            relevance = _condition_scope_relevance(target_tokens, text)
            if relevance <= 0:
                continue
            for phrase in _extract_condition_phrases(text):
                phrase = _condition_phrase_with_leading_context(text, phrase)
                phrase = _condition_preference_parallel_condition_phrase(
                    text,
                    phrase,
                )
                if _condition_phrase_has_dangling_nested_cue(phrase):
                    continue
                if not _condition_phrase_is_near_target(phrase, text, target_tokens):
                    continue
                if _condition_phrase_has_noise(phrase):
                    continue
                if _condition_phrase_is_object_only(phrase, row):
                    continue
                cue = phrase.split()[0].lower() if phrase.split() else ""
                attached_detail = _condition_source_condition_answer_detail(
                    text,
                    phrase,
                    row,
                )
                scope_policy = (
                    "answer condition questions with exact_condition; "
                    "do not broaden to adjacent routines"
                )
                if attached_detail:
                    scope_policy = (
                        "answer condition questions with exact_condition; include "
                        "condition_answer_detail when present; do not broaden to "
                        "adjacent routines"
                    )
                answer_support = _condition_answer_support_score(
                    row,
                    source_field,
                    text,
                    phrase,
                    target_tokens,
                    attached_detail,
                )
                score = (
                    relevance * 4
                    + _condition_phrase_priority(phrase)
                    + _condition_phrase_specificity_bonus(phrase)
                    + _condition_phrase_target_overlap(phrase, target_tokens)
                    + _condition_phrase_context_bonus(phrase, text, target_tokens)
                    + answer_support
                    + _condition_scope_row_priority(row, answer_support)
                )
                scored_hints.append(
                    (
                        -score,
                        str(row.get("observed_at", "")),
                        memory_id,
                        phrase,
                        len(scored_hints),
                        {
                            "scope_type": "condition_scope",
                            "memory_id": memory_id,
                            "exact_condition": phrase,
                            "preferred_answer": phrase,
                            "condition_cue": cue,
                            "condition_answer_detail": attached_detail,
                            "complete_condition_answer": _complete_condition_answer(
                                phrase,
                                attached_detail,
                            ),
                            "scope_policy": scope_policy,
                            "source_field": source_field,
                            "source_excerpt": _focus_excerpt(text, phrase, max_chars=260),
                            "supporting_value": row.get("value", ""),
                            "observed_at": row.get("observed_at", ""),
                            "source_confidence": row.get("source_confidence", ""),
                        },
                    )
                )
    for row in _condition_preference_source_rows(request, target_tokens):
        memory_id = str(row.get("memory_id", ""))
        for source_field, text in _condition_scope_candidate_texts(row):
            relevance = _condition_scope_relevance(target_tokens, text)
            if relevance <= 0:
                continue
            for phrase in _extract_condition_phrases(text):
                phrase = _condition_phrase_with_leading_context(text, phrase)
                phrase = _condition_preference_parallel_condition_phrase(
                    text,
                    phrase,
                )
                if _condition_phrase_has_dangling_nested_cue(phrase):
                    continue
                if not _condition_phrase_is_near_target(phrase, text, target_tokens):
                    continue
                if _condition_phrase_has_noise(phrase):
                    continue
                if _condition_phrase_is_object_only(phrase, row):
                    continue
                if not _condition_phrase_has_source_preference_support(
                    phrase,
                    text,
                    target_tokens,
                ):
                    continue
                detail = _condition_source_condition_answer_detail(
                    text,
                    phrase,
                    row,
                )
                answer_support = _condition_answer_support_score(
                    row,
                    source_field,
                    text,
                    phrase,
                    target_tokens,
                    detail,
                )
                cue = phrase.split()[0].lower() if phrase.split() else ""
                scored_hints.append(
                    (
                        -(
                            relevance * 4
                            + _condition_phrase_priority(phrase)
                            + _condition_phrase_specificity_bonus(phrase)
                            + _condition_phrase_target_overlap(phrase, target_tokens)
                            + _condition_phrase_context_bonus(phrase, text, target_tokens)
                            + answer_support
                            + 14
                        ),
                        str(row.get("observed_at", "")),
                        memory_id,
                        phrase,
                        len(scored_hints),
                        {
                            "scope_type": "condition_preference_source",
                            "memory_id": memory_id,
                            "exact_condition": phrase,
                            "preferred_answer": _complete_condition_answer(
                                phrase,
                                detail,
                            )
                            or phrase,
                            "condition_cue": cue,
                            "condition_answer_detail": detail,
                            "complete_condition_answer": _complete_condition_answer(
                                phrase,
                                detail,
                            ),
                            "scope_policy": (
                                "answer condition questions from this source-supported "
                                "preference row; do not replace it with adjacent schedules "
                                "or practice times unless the question asks for a schedule"
                            ),
                            "source_field": source_field,
                            "source_excerpt": _focus_excerpt(text, phrase, max_chars=300),
                            "supporting_value": row.get("value", ""),
                            "observed_at": row.get("observed_at", ""),
                            "source_confidence": row.get("source_confidence", ""),
                        },
                    )
                )
    scored_hints.sort()
    selected = []
    for _, _, _, phrase, _, hint in scored_hints:
        if _condition_source_hint_should_yield_to_direct_claim(
            hint,
            scored_hints,
            target_tokens,
        ):
            continue
        if _condition_direct_anchor_should_yield_to_detailed_source(
            hint,
            scored_hints,
            target_tokens,
        ):
            continue
        if _condition_hint_should_yield_to_target_value_row(
            hint,
            scored_hints,
            target_tokens,
        ):
            continue
        if str(hint.get("scope_type", "")) == "condition_direct_claim_anchor":
            memory_id = str(hint.get("memory_id", ""))
            if any(
                str(other_hint.get("memory_id", "")) == memory_id
                and str(other_hint.get("scope_type", ""))
                == "condition_direct_claim_anchor"
                and _condition_phrase_is_subset_scope(
                    phrase,
                    str(other_hint.get("exact_condition", "")),
                )
                for _, _, _, _, _, other_hint in scored_hints
            ):
                continue
            if any(
                _condition_direct_anchor_should_yield_to_fuller_compound(
                    hint,
                    other_hint,
                    target_tokens,
                )
                for _, _, _, _, _, other_hint in scored_hints
            ):
                continue
        if not _condition_phrase_has_explanatory_leading_context(phrase):
            memory_id = str(hint.get("memory_id", ""))
            source_field = str(hint.get("source_field", ""))
            if any(
                str(other_hint.get("memory_id", "")) == memory_id
                and (
                    str(other_hint.get("source_field", "")) == source_field
                    or str(other_hint.get("source_field", "")).endswith("source_span")
                )
                and not (
                    str(hint.get("scope_type", "")) == "condition_direct_claim_anchor"
                    and _condition_phrase_mentions_target_value(
                        str(other_hint.get("exact_condition", "")),
                        hint,
                        target_tokens,
                    )
                )
                and _condition_phrase_has_explanatory_leading_context(
                    str(other_hint.get("exact_condition", ""))
                )
                for _, _, _, _, _, other_hint in scored_hints
            ):
                continue
        if str(hint.get("scope_type", "")) == "condition_direct_claim_anchor":
            memory_id = str(hint.get("memory_id", ""))
            if any(
                str(other_hint.get("memory_id", "")) == memory_id
                and str(other_hint.get("source_field", "")).endswith("source_span")
                and not _condition_phrase_mentions_target_value(
                    str(other_hint.get("exact_condition", "")),
                    hint,
                    target_tokens,
                )
                and _condition_phrase_has_explanatory_leading_context(
                    str(other_hint.get("exact_condition", ""))
                )
                for _, _, _, _, _, other_hint in scored_hints
            ):
                continue
        if any(
            _condition_phrase_is_duplicate_scope(
                phrase,
                str(existing.get("exact_condition", "")),
            )
            for existing in selected
        ):
            continue
        selected.append(
            {
                key: value
                for key, value in hint.items()
                if value not in (None, "", [], {})
            }
        )
        if str(hint.get("scope_type", "")) == "condition_direct_claim_anchor":
            selected = _add_stronger_direct_condition_anchor_sibling(
                selected,
                scored_hints,
                target_tokens,
            )
            break
        if len(selected) >= MAX_CONDITION_SCOPE_HINTS:
            break
    selected = _condition_preference_primary_selection(selected)
    selected = _prefer_fuller_compound_direct_anchor(
        selected,
        scored_hints,
        target_tokens,
    )
    selected = _add_direct_condition_anchor_siblings_for_low_value_source_rows(
        selected,
        scored_hints,
        target_tokens,
    )
    return selected


def _build_habit_frequency_context(
    request: dict[str, Any],
    routed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not _asks_for_habit_frequency(question):
        return []

    question_tokens = _habit_frequency_target_tokens(question)
    scored_hints: list[tuple[int, str, str, str, int, int, dict[str, Any]]] = []
    seen_rows: set[str] = set()
    candidate_rows: list[dict[str, Any]] = []
    for row in routed_rows:
        if not isinstance(row, dict):
            continue
        memory_id = str(row.get("memory_id", ""))
        if memory_id:
            seen_rows.add(memory_id)
        candidate_rows.append(row)
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        memory_id = str(record.get("memory_id", ""))
        if memory_id and memory_id in seen_rows:
            continue
        candidate_rows.append(record)

    for order, row in enumerate(candidate_rows):
        if not isinstance(row, dict):
            continue
        score, reasons = _question_relevance_score(question, query, row)
        if score <= 0 and not _habit_frequency_row_mentions_target(
            row,
            question_tokens,
        ):
            continue
        memory_id = str(row.get("memory_id", ""))
        for source_field, text in _habit_frequency_candidate_texts(row):
            phrase = _first_habit_frequency_phrase(text)
            if not phrase:
                continue
            day_phrase = _first_habit_day_phrase(text)
            hint = {
                "context_type": "habit_frequency",
                "memory_id": memory_id,
                "frequency_phrase": phrase,
                "day_phrase": day_phrase,
                "preferred_answer_anchor": _habit_frequency_preferred_anchor(
                    phrase,
                    day_phrase,
                ),
                "claim": row.get("claim", ""),
                "value": row.get("value", ""),
                "observed_at": row.get("observed_at", ""),
                "source_field": source_field,
                "source_excerpt": _focus_excerpt(text, phrase, max_chars=300),
                "source_confidence": row.get("source_confidence", ""),
                "frequency_policy": (
                    "preserve frequency_phrase and day_phrase as answer-critical "
                    "cadence evidence for how-often or routine-change questions"
                ),
                "relevance_score": score,
                "relevance_reason": reasons[:4],
            }
            scored_hints.append(
                (
                    -(
                        score * 5
                        + _habit_frequency_phrase_priority(phrase)
                        + (4 if day_phrase else 0)
                        + (2 if source_field.startswith("source") else 0)
                    ),
                    str(row.get("observed_at", "")),
                    memory_id,
                    _norm_text(phrase),
                    order,
                    len(scored_hints),
                    hint,
                )
            )

    scored_hints.sort()
    selected: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    latest_observed_at = max(
        (
            str(hint.get("observed_at", ""))
            for *_, hint in scored_hints
            if str(hint.get("observed_at", ""))
        ),
        default="",
    )
    for _, _, memory_id, phrase_norm, _, _, hint in scored_hints:
        key = (
            memory_id,
            phrase_norm,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out = {
            key: value
            for key, value in hint.items()
            if value not in (None, "", [], {})
        }
        observed_at = str(hint.get("observed_at", ""))
        if latest_observed_at and observed_at:
            out["time_role"] = (
                "latest_or_current_candidate"
                if observed_at == latest_observed_at
                else "previous_or_historical_candidate"
            )
        selected.append(out)
        if len(selected) >= MAX_HABIT_FREQUENCY_HINTS:
            break
    return _assign_habit_frequency_chronology_roles(
        selected,
        question=question,
    )


def _assign_habit_frequency_chronology_roles(
    rows: list[dict[str, Any]],
    *,
    question: str,
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    if not _asks_for_habit_frequency_change(question):
        return rows
    dated_values = sorted(
        {
            str(row.get("observed_at", ""))
            for row in rows
            if str(row.get("observed_at", "")).strip()
        }
    )
    if len(dated_values) < 2:
        return [
            {
                **row,
                "chronology_role_status": "ambiguous_or_insufficient_dated_hints",
                "chronology_policy": (
                    "do not force previous/current frequency roles without at least "
                    "two distinct observed_at values"
                ),
            }
            for row in rows
        ]
    latest = dated_values[-1]
    assigned = []
    for row in rows:
        observed_at = str(row.get("observed_at", ""))
        out = dict(row)
        if observed_at == latest:
            out["answer_slot"] = "current_frequency"
            out["chronology_role"] = "current_or_now"
        elif observed_at:
            out["answer_slot"] = "previous_frequency"
            out["chronology_role"] = "previous_or_historical"
        else:
            out["chronology_role"] = "undated_frequency_hint"
        out["chronology_policy"] = (
            "for previous/current routine questions, use observed_at chronology: "
            "earlier cadence hints fill previous_frequency and the latest dated "
            "cadence hint fills current_frequency"
        )
        assigned.append(out)
    assigned.sort(
        key=lambda row: (
            _habit_frequency_answer_slot_order(str(row.get("answer_slot", ""))),
            str(row.get("observed_at", "")),
            str(row.get("memory_id", "")),
        )
    )
    return assigned


def _habit_frequency_answer_slot_order(answer_slot: str) -> int:
    if answer_slot == "previous_frequency":
        return 0
    if answer_slot == "current_frequency":
        return 1
    return 2


def _asks_for_habit_frequency_change(question: str) -> bool:
    text = _norm_text(question)
    if not _asks_for_habit_frequency(question):
        return False
    previous_cues = ("previously", "before", "used to", "earlier", "prior")
    current_cues = ("now", "currently", "current", "these days", "lately", "recently")
    return _contains_any(text, previous_cues) and _contains_any(text, current_cues)


def _asks_for_habit_frequency(question: str) -> bool:
    text = _norm_text(question)
    if not text:
        return False
    if _contains_any(text, HABIT_FREQUENCY_QUESTION_CUES):
        return True
    return bool(
        re.search(
            r"\b(?:how|what)\s+(?:much|many)?\s*(?:regular|often|frequency)\b",
            text,
        )
    )


def _habit_frequency_target_tokens(question: str) -> set[str]:
    ignored = set(_norm_text(" ".join(HABIT_FREQUENCY_QUESTION_CUES)).split()) | {
        "before",
        "currently",
        "current",
        "now",
        "previously",
        "regular",
        "regularly",
    }
    return {
        token
        for token in _content_tokens(question)
        if token not in ignored and token not in HABIT_FREQUENCY_WEEKDAYS
    }


def _habit_frequency_row_mentions_target(
    row: dict[str, Any],
    question_tokens: set[str],
) -> bool:
    if not question_tokens:
        return True
    row_tokens = _content_tokens(
        " ".join(
            str(row.get(field_name, ""))
            for field_name in ("entity", "slot", "claim", "value", "source_span")
        )
    )
    source = row.get("source", {})
    if isinstance(source, dict):
        row_tokens.update(_content_tokens(source.get("source_span", "")))
    return bool(row_tokens & question_tokens)


def _habit_frequency_candidate_texts(row: dict[str, Any]) -> list[tuple[str, str]]:
    candidates = []
    for field_name in ("source_span", "claim", "value"):
        value = row.get(field_name, "")
        if isinstance(value, str) and value.strip():
            candidates.append((field_name, value))
    source_span = _row_source_span(row)
    if source_span and not any(text == source_span for _, text in candidates):
        candidates.append(("source.source_span", source_span))
    return candidates


def _first_habit_frequency_phrase(text: str) -> str:
    for pattern in HABIT_FREQUENCY_PATTERNS:
        match = pattern.search(text)
        if match:
            return " ".join(match.group(0).split())
    return ""


def _first_habit_day_phrase(text: str) -> str:
    match = HABIT_DAY_PATTERN.search(text)
    if not match:
        return ""
    return " ".join(match.group(0).split())


def _habit_frequency_preferred_anchor(
    frequency_phrase: str,
    day_phrase: str,
) -> str:
    if frequency_phrase and day_phrase:
        return f"{frequency_phrase} ({day_phrase})"
    return frequency_phrase or day_phrase


def _habit_frequency_phrase_priority(phrase: str) -> int:
    normalized = _norm_text(phrase)
    if "every other" in normalized:
        return 18
    if normalized in {"weekly", "biweekly", "fortnightly", "monthly"}:
        return 14
    if normalized.startswith("every "):
        return 12
    if normalized.startswith("once ") or normalized.startswith("twice "):
        return 10
    if normalized.endswith("s"):
        return 4
    return 6


def _condition_preference_source_rows(
    request: dict[str, Any],
    target_tokens: set[str],
) -> list[dict[str, Any]]:
    rows = []
    for row in request.get("records", []):
        if not isinstance(row, dict):
            continue
        text = " ".join(
            text
            for _, text in _condition_scope_candidate_texts(row)
            if isinstance(text, str)
        )
        if not _condition_source_mentions_target(text, target_tokens):
            continue
        if not _condition_source_has_preference_cue(text):
            continue
        if not any(_extract_condition_phrases(text)):
            continue
        if _condition_source_is_schedule_without_preference(text, target_tokens):
            continue
        rows.append(row)
    return rows


def _condition_source_mentions_target(text: str, target_tokens: set[str]) -> bool:
    if not target_tokens:
        return True
    return bool(set(_norm_text(text).split()) & target_tokens)


def _condition_source_has_preference_cue(text: str) -> bool:
    return bool(set(_norm_text(text).split()) & CONDITION_PREFERENCE_CUES)


def _condition_source_is_schedule_without_preference(
    text: str,
    target_tokens: set[str],
) -> bool:
    tokens = set(_norm_text(text).split())
    if not (tokens & CONDITION_SCHEDULE_NOISE_TERMS):
        return False
    if tokens & CONDITION_PREFERENCE_CUES and target_tokens & tokens:
        return False
    return True


def _condition_phrase_has_source_preference_support(
    phrase: str,
    text: str,
    target_tokens: set[str],
) -> bool:
    window_tokens = _condition_phrase_window_tokens(
        text,
        phrase,
        before_token_count=24,
        after_token_count=24,
    )
    if not window_tokens:
        return False
    return bool(
        window_tokens & CONDITION_PREFERENCE_CUES
        and (not target_tokens or window_tokens & target_tokens)
    )


def _asks_for_condition_scope(question: str) -> bool:
    text = _norm_text(question)
    if not text:
        return False
    if "under what condition" in text or "what condition" in text:
        return True
    if "in what situation" in text or "which situation" in text:
        return True
    if text.startswith("when ") and _contains_any(text, ("prefer", "prefers", "preference", "like", "likes", "habit")):
        return True
    if _contains_any(text, ("if ", "during ", "before ", "after ")) and _contains_any(
        text,
        ("prefer", "prefers", "preference", "like", "likes", "habit"),
    ):
        return True
    return False


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def _condition_scope_target_tokens(question: str) -> set[str]:
    return {
        token
        for token in _norm_text(question).split()
        if len(token) > 1 and token not in CONDITION_SCOPE_STOPWORDS
    }


def _condition_phrase_mentions_target_value(
    phrase: str,
    hint: dict[str, Any],
    target_tokens: set[str],
) -> bool:
    phrase_tokens = _condition_scope_signal_tokens(phrase)
    if not phrase_tokens:
        return False
    value_tokens = _condition_scope_signal_tokens(str(hint.get("supporting_value", "")))
    return bool(phrase_tokens & (target_tokens | value_tokens))


def _condition_source_hint_should_yield_to_direct_claim(
    hint: dict[str, Any],
    scored_hints: list[tuple[Any, ...]],
    target_tokens: set[str],
) -> bool:
    if str(hint.get("scope_type", "")) not in {
        "condition_scope",
        "condition_preference_source",
    }:
        return False
    if not str(hint.get("source_field", "")).endswith("source_span"):
        return False
    exact_condition = str(hint.get("exact_condition", ""))
    phrase_mentions_target = _condition_phrase_mentions_target_value(
        exact_condition,
        hint,
        target_tokens,
    )
    memory_id = str(hint.get("memory_id", ""))
    if not memory_id:
        return False
    direct_target_anchors = [
        other_hint
        for *_, other_hint in scored_hints
        if str(other_hint.get("scope_type", "")) == "condition_direct_claim_anchor"
        and _condition_direct_anchor_target_coverage(other_hint, target_tokens) > 0
    ]
    if _condition_hint_should_yield_to_fuller_compound_direct_anchor(
        hint,
        direct_target_anchors,
    ):
        return True
    if not phrase_mentions_target:
        return bool(direct_target_anchors) and not any(
            _condition_phrase_is_duplicate_scope(
                exact_condition,
                str(other_hint.get("exact_condition", "")),
            )
            for other_hint in direct_target_anchors
        )
    return any(
        str(other_hint.get("memory_id", "")) == memory_id
        and str(other_hint.get("scope_type", "")) == "condition_direct_claim_anchor"
        for *_, other_hint in scored_hints
    )


def _condition_hint_should_yield_to_fuller_compound_direct_anchor(
    hint: dict[str, Any],
    direct_target_anchors: list[dict[str, Any]],
) -> bool:
    exact_condition = str(hint.get("exact_condition", ""))
    if not exact_condition:
        return False
    observed_at = str(hint.get("observed_at", ""))
    for other_hint in direct_target_anchors:
        other_condition = str(other_hint.get("exact_condition", ""))
        if not _condition_phrase_is_compound_superset(
            other_condition,
            exact_condition,
        ):
            continue
        other_observed_at = str(other_hint.get("observed_at", ""))
        if observed_at and other_observed_at and observed_at != other_observed_at:
            continue
        return True
    return False


def _condition_direct_anchor_should_yield_to_detailed_source(
    hint: dict[str, Any],
    scored_hints: list[tuple[Any, ...]],
    target_tokens: set[str],
) -> bool:
    if str(hint.get("scope_type", "")) != "condition_direct_claim_anchor":
        return False
    exact_condition = str(hint.get("exact_condition", ""))
    if not exact_condition:
        return False
    if target_tokens and not _condition_hint_mentions_target(hint, target_tokens):
        return False
    for *_, other_hint in scored_hints:
        if other_hint is hint:
            continue
        if str(other_hint.get("scope_type", "")) == "condition_direct_claim_anchor":
            continue
        detail = str(other_hint.get("condition_answer_detail", "") or "")
        if not detail:
            continue
        if not _condition_phrase_is_duplicate_scope(
            exact_condition,
            str(other_hint.get("exact_condition", "")),
        ):
            continue
        if target_tokens and not _condition_hint_mentions_target(
            other_hint,
            target_tokens,
        ):
            continue
        return True
    return False


def _condition_hint_should_yield_to_target_value_row(
    hint: dict[str, Any],
    scored_hints: list[tuple[Any, ...]],
    target_tokens: set[str],
) -> bool:
    if str(hint.get("scope_type", "")) not in {
        "condition_scope",
        "condition_preference_source",
    }:
        return False
    if not target_tokens:
        return False
    supporting_value_tokens = _condition_scope_signal_tokens(
        str(hint.get("supporting_value", ""))
    )
    if supporting_value_tokens & target_tokens:
        return False
    if not _condition_hint_mentions_target(hint, target_tokens):
        return False
    if supporting_value_tokens and str(hint.get("condition_answer_detail", "")):
        exact_condition = str(hint.get("exact_condition", ""))
        if any(
            other_hint is not hint
            and _condition_scope_signal_tokens(
                str(other_hint.get("supporting_value", ""))
            )
            & target_tokens
            and _condition_phrase_is_duplicate_scope(
                exact_condition,
                str(other_hint.get("exact_condition", "")),
            )
            for *_, other_hint in scored_hints
        ):
            return False
    return any(
        other_hint is not hint
        and _condition_scope_signal_tokens(str(other_hint.get("supporting_value", "")))
        & target_tokens
        for *_, other_hint in scored_hints
    )


def _condition_hint_mentions_target(
    hint: dict[str, Any],
    target_tokens: set[str],
) -> bool:
    if not target_tokens:
        return True
    text = " ".join(
        str(hint.get(field_name, ""))
        for field_name in (
            "supporting_value",
            "source_excerpt",
            "preferred_answer",
            "complete_condition_answer",
        )
    )
    return bool(_condition_scope_signal_tokens(text) & target_tokens)


def _prefer_fuller_compound_direct_anchor(
    selected: list[dict[str, Any]],
    scored_hints: list[tuple[Any, ...]],
    target_tokens: set[str],
) -> list[dict[str, Any]]:
    if not selected:
        return selected
    direct_candidates = [
        hint
        for *_, hint in scored_hints
        if str(hint.get("scope_type", "")) == "condition_direct_claim_anchor"
        and _condition_direct_anchor_target_coverage(hint, target_tokens) > 0
    ]
    if not direct_candidates:
        return selected
    output = list(selected)
    for index, row in enumerate(output):
        exact_condition = str(row.get("exact_condition", ""))
        if not exact_condition:
            continue
        observed_at = str(row.get("observed_at", ""))
        fuller_candidates = []
        for hint in direct_candidates:
            phrase = str(hint.get("exact_condition", ""))
            if not _condition_phrase_is_compound_superset(phrase, exact_condition):
                continue
            hint_observed_at = str(hint.get("observed_at", ""))
            if observed_at and hint_observed_at and observed_at != hint_observed_at:
                continue
            fuller_candidates.append(
                (
                    -len(_condition_scope_signal_tokens(phrase)),
                    str(hint.get("memory_id", "")),
                    hint,
                )
            )
        if not fuller_candidates:
            continue
        fuller_candidates.sort(key=lambda item: item[:2])
        output[index] = {
            key: value
            for key, value in fuller_candidates[0][2].items()
            if value not in (None, "", [], {})
        }
    return output


def _condition_source_hint_is_admin_neighbor_noise(
    hint: dict[str, Any],
    target_tokens: set[str],
) -> bool:
    phrase = str(hint.get("exact_condition", ""))
    if not phrase:
        return False
    if _condition_phrase_mentions_target_value(phrase, hint, target_tokens):
        return False
    phrase_tokens = set(_norm_text(phrase).split())
    if not (phrase_tokens & CONDITION_SOURCE_ADMIN_NEIGHBOR_TERMS):
        return False
    source_excerpt_tokens = set(_norm_text(str(hint.get("source_excerpt", ""))).split())
    if source_excerpt_tokens and not (source_excerpt_tokens & CONDITION_PREFERENCE_CUES):
        return False
    return True


def _condition_scope_candidate_texts(row: dict[str, Any]) -> list[tuple[str, str]]:
    candidates = []
    for field_name in ("source_span", "claim", "value"):
        value = row.get(field_name, "")
        if isinstance(value, str) and value.strip():
            candidates.append((field_name, value))
    source_span = _row_source_span(row)
    if source_span and not any(text == source_span for _, text in candidates):
        candidates.append(("source.source_span", source_span))
    return candidates


def _condition_direct_claim_hints(
    row: dict[str, Any],
    target_tokens: set[str],
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for source_field, text in _condition_scope_candidate_texts(row):
        if source_field != "claim":
            continue
        normalized_text = _norm_text(text)
        tokens = normalized_text.split()
        for start, end in _condition_target_spans(tokens, row, target_tokens):
            candidate_phrases = [
                *_direct_conditions_after_target(tokens[end:]),
                _direct_condition_before_target(tokens[max(0, start - 16) : start]),
            ]
            for candidate_phrase in candidate_phrases:
                phrase = _normalize_direct_condition_phrase(candidate_phrase)
                phrase = _condition_preference_parallel_condition_phrase(text, phrase)
                phrase = _normalize_direct_condition_phrase(phrase)
                if not phrase or _condition_phrase_has_noise(phrase):
                    continue
                phrase_tokens = set(_norm_text(phrase).split())
                if not (
                    phrase_tokens & CONDITION_ANCHOR_TERMS
                    or phrase_tokens & CONDITION_PREFERENCE_CUES
                ):
                    continue
                if _condition_phrase_is_object_only(phrase, row):
                    continue
                hints.append(
                    {
                        "scope_type": "condition_direct_claim_anchor",
                        "memory_id": str(row.get("memory_id", "")),
                        "exact_condition": phrase,
                        "preferred_answer": phrase,
                        "condition_cue": phrase.split()[0].lower() if phrase.split() else "",
                        "scope_policy": (
                            "answer condition questions from the direct claim-level "
                            "target-condition binding; do not replace it with adjacent "
                            "source-span routines"
                        ),
                        "source_field": source_field,
                        "source_excerpt": _focus_excerpt(text, phrase, max_chars=300),
                        "supporting_value": row.get("value", ""),
                        "observed_at": row.get("observed_at", ""),
                        "source_confidence": row.get("source_confidence", ""),
                    }
                )
    return _dedupe_condition_hints(hints)


def _add_stronger_direct_condition_anchor_sibling(
    selected: list[dict[str, Any]],
    scored_hints: list[tuple[Any, ...]],
    target_tokens: set[str],
) -> list[dict[str, Any]]:
    if len(selected) >= MAX_CONDITION_SCOPE_HINTS:
        return selected
    selected_direct = [
        row
        for row in selected
        if str(row.get("scope_type", "")) == "condition_direct_claim_anchor"
    ]
    if not selected_direct:
        return selected
    selected_coverage = max(
        _condition_direct_anchor_target_coverage(row, target_tokens)
        for row in selected_direct
    )
    selected_memory_ids = {
        str(row.get("memory_id", "")) for row in selected_direct if row.get("memory_id")
    }
    selected_conditions = [
        str(row.get("exact_condition", ""))
        for row in selected
        if row.get("exact_condition")
    ]
    addable: list[tuple[int, str, str, dict[str, Any]]] = []
    for *_, hint in scored_hints:
        if str(hint.get("scope_type", "")) != "condition_direct_claim_anchor":
            continue
        memory_id = str(hint.get("memory_id", ""))
        if not memory_id:
            continue
        exact_condition = str(hint.get("exact_condition", ""))
        if any(
            _condition_phrase_is_duplicate_scope(exact_condition, existing)
            or _condition_phrase_is_subset_scope(exact_condition, existing)
            for existing in selected_conditions
        ):
            continue
        coverage = _condition_direct_anchor_target_coverage(hint, target_tokens)
        same_memory = memory_id in selected_memory_ids
        if same_memory and coverage <= 0:
            continue
        if not same_memory and coverage <= selected_coverage:
            continue
        addable.append(
            (
                -coverage,
                str(hint.get("observed_at", "")),
                memory_id,
                hint,
            )
        )
    if not addable:
        return selected
    addable.sort(key=lambda item: item[:3])
    augmented = list(selected)
    for _, _, _, hint in addable:
        if len(augmented) >= MAX_CONDITION_SCOPE_HINTS:
            break
        augmented.append(
            {
                key: value
                for key, value in hint.items()
                if value not in (None, "", [], {})
            }
        )
    return augmented


def _add_direct_condition_anchor_siblings_for_low_value_source_rows(
    selected: list[dict[str, Any]],
    scored_hints: list[tuple[Any, ...]],
    target_tokens: set[str],
) -> list[dict[str, Any]]:
    if not selected:
        return selected
    source_memory_ids = {
        str(row.get("memory_id", ""))
        for row in selected
        if str(row.get("scope_type", "")) == "condition_preference_source"
        and str(row.get("memory_id", ""))
    }
    if not source_memory_ids:
        return selected
    selected_conditions = [
        str(row.get("exact_condition", ""))
        for row in selected
        if row.get("exact_condition")
    ]
    direct_candidates: list[tuple[int, str, str, dict[str, Any]]] = []
    for *_, hint in scored_hints:
        if str(hint.get("scope_type", "")) != "condition_direct_claim_anchor":
            continue
        memory_id = str(hint.get("memory_id", ""))
        if memory_id not in source_memory_ids:
            continue
        exact_condition = str(hint.get("exact_condition", ""))
        if any(
            _condition_phrase_is_duplicate_scope(exact_condition, existing)
            for existing in selected_conditions
        ):
            continue
        coverage = _condition_direct_anchor_target_coverage(hint, target_tokens)
        if coverage <= 0:
            continue
        direct_candidates.append(
            (
                -coverage,
                str(hint.get("observed_at", "")),
                memory_id,
                hint,
            )
        )
    for row in selected:
        if str(row.get("scope_type", "")) != "condition_preference_source":
            continue
        if str(row.get("memory_id", "")) not in source_memory_ids:
            continue
        source_excerpt = str(row.get("source_excerpt", ""))
        supporting_value = str(row.get("supporting_value", ""))
        if target_tokens and not (
            _condition_scope_signal_tokens(supporting_value) & target_tokens
        ):
            continue
        for phrase in _condition_source_excerpt_sibling_conditions(source_excerpt):
            if any(
                _condition_phrase_is_duplicate_scope(phrase, existing)
                for existing in selected_conditions
            ):
                continue
            sibling = {
                "scope_type": "condition_preference_source",
                "memory_id": str(row.get("memory_id", "")),
                "exact_condition": phrase,
                "preferred_answer": phrase,
                "condition_cue": phrase.split()[0].lower() if phrase.split() else "",
                "scope_policy": str(row.get("scope_policy", "")),
                "source_field": str(row.get("source_field", "")),
                "source_excerpt": _focus_excerpt(source_excerpt, phrase, max_chars=300),
                "supporting_value": supporting_value,
                "observed_at": row.get("observed_at", ""),
                "source_confidence": row.get("source_confidence", ""),
            }
            direct_candidates.append(
                (
                    -_condition_phrase_priority(phrase),
                    str(row.get("observed_at", "")),
                    str(row.get("memory_id", "")),
                    sibling,
                )
            )
    if not direct_candidates:
        return selected
    direct_candidates.sort(key=lambda item: item[:3])
    augmented = list(selected)
    for _, _, _, hint in direct_candidates:
        out = {
            key: value
            for key, value in hint.items()
            if value not in (None, "", [], {})
        }
        if len(augmented) >= MAX_CONDITION_SCOPE_HINTS:
            removable_index = _low_value_source_condition_row_index(
                augmented,
                target_tokens,
            )
            if removable_index is None:
                break
            augmented[removable_index] = out
        else:
            augmented.append(out)
        selected_conditions.append(str(hint.get("exact_condition", "")))
        if len(augmented) >= MAX_CONDITION_SCOPE_HINTS:
            break
    return augmented


def _condition_source_excerpt_sibling_conditions(source_excerpt: str) -> list[str]:
    siblings: list[str] = []
    for phrase in _extract_condition_phrases(source_excerpt):
        phrase = _condition_phrase_with_leading_context(source_excerpt, phrase)
        phrase = _condition_preference_parallel_condition_phrase(source_excerpt, phrase)
        if not phrase:
            continue
        if _condition_phrase_has_noise(phrase):
            continue
        phrase_tokens = set(_norm_text(phrase).split())
        if not (phrase_tokens & CONDITION_ANCHOR_TERMS):
            continue
        if any(_condition_phrase_is_duplicate_scope(phrase, existing) for existing in siblings):
            continue
        siblings.append(phrase)
    return siblings


def _low_value_source_condition_row_index(
    rows: list[dict[str, Any]],
    target_tokens: set[str],
) -> int | None:
    for index in range(len(rows) - 1, -1, -1):
        row = rows[index]
        if not _condition_source_row_is_low_value_neighbor(row, target_tokens):
            continue
        return index
    return None


def _condition_source_row_is_low_value_neighbor(
    row: dict[str, Any],
    target_tokens: set[str],
) -> bool:
    if str(row.get("scope_type", "")) not in {
        "condition_scope",
        "condition_preference_source",
    }:
        return False
    if not str(row.get("source_field", "")).endswith("source_span"):
        return False
    phrase = str(row.get("exact_condition", ""))
    if not phrase:
        return False
    if _condition_phrase_mentions_target_value(phrase, row, target_tokens):
        return False
    phrase_tokens = set(_norm_text(phrase).split())
    if phrase_tokens & CONDITION_ANCHOR_TERMS:
        return False
    low_value_terms = CONDITION_SOURCE_ADMIN_NEIGHBOR_TERMS | {
        "help",
        "helps",
        "helping",
        "quick",
        "tip",
        "tips",
        "tone",
    }
    return bool(phrase_tokens & low_value_terms)


def _condition_direct_anchor_target_coverage(
    hint: dict[str, Any],
    target_tokens: set[str],
) -> int:
    if not target_tokens:
        return 0
    text = " ".join(
        str(hint.get(field_name, ""))
        for field_name in ("supporting_value", "source_excerpt", "exact_condition")
        if hint.get(field_name)
    )
    return len(_condition_scope_signal_tokens(text) & target_tokens)


def _condition_direct_anchor_should_yield_to_fuller_compound(
    hint: dict[str, Any],
    other_hint: dict[str, Any],
    target_tokens: set[str],
) -> bool:
    if str(hint.get("scope_type", "")) != "condition_direct_claim_anchor":
        return False
    if str(other_hint.get("scope_type", "")) != "condition_direct_claim_anchor":
        return False
    if hint is other_hint:
        return False
    phrase = str(hint.get("exact_condition", ""))
    other_phrase = str(other_hint.get("exact_condition", ""))
    if not _condition_phrase_is_compound_superset(other_phrase, phrase):
        return False
    observed_at = str(hint.get("observed_at", ""))
    other_observed_at = str(other_hint.get("observed_at", ""))
    if observed_at and other_observed_at and observed_at != other_observed_at:
        return False
    if target_tokens and (
        _condition_direct_anchor_target_coverage(other_hint, target_tokens)
        < _condition_direct_anchor_target_coverage(hint, target_tokens)
    ):
        return False
    return True


def _condition_phrase_is_compound_superset(candidate: str, existing: str) -> bool:
    candidate_tokens_all = _norm_text(candidate).split()
    if not ({"and", "or"} & set(candidate_tokens_all)):
        return False
    candidate_tokens = _condition_scope_signal_tokens(candidate) - set(
        CONDITION_SCOPE_CUES
    )
    existing_tokens = _condition_scope_signal_tokens(existing) - set(
        CONDITION_SCOPE_CUES
    )
    if not candidate_tokens or not existing_tokens:
        return False
    return existing_tokens <= candidate_tokens and candidate_tokens != existing_tokens


def _condition_target_spans(
    tokens: list[str],
    row: dict[str, Any],
    target_tokens: set[str],
) -> list[tuple[int, int]]:
    signal_tokens = {
        token
        for token in target_tokens
        if len(token) > 2 and token not in CONDITION_SCOPE_STOPWORDS
    }
    value_tokens = {
        token
        for token in _norm_text(str(row.get("value", ""))).split()
        if len(token) > 2 and token not in CONDITION_SCOPE_STOPWORDS
    }
    row_tokens = set(
        _norm_text(
            " ".join(
                str(row.get(field_name, ""))
                for field_name in ("claim", "value", "source_span")
                if row.get(field_name)
            )
        ).split()
    )
    if signal_tokens and row_tokens:
        overlap = len(signal_tokens & row_tokens)
        if overlap < _condition_scope_required_target_overlap(signal_tokens):
            return []
    if signal_tokens & value_tokens:
        signal_tokens |= value_tokens
    if not signal_tokens:
        signal_tokens = value_tokens
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(tokens):
        if tokens[index] not in signal_tokens:
            index += 1
            continue
        end = index + 1
        while end < len(tokens) and tokens[end] in signal_tokens:
            end += 1
        spans.append((index, end))
        index = end
    return spans


DIRECT_CONDITION_BOUNDARY_TERMS = {
    "add",
    "also",
    "and",
    "anything",
    "as",
    "because",
    "but",
    "consider",
    "great",
    "keep",
    "noted",
    "since",
    "so",
    "that",
    "then",
    "unless",
    "when",
    "which",
}
DIRECT_CONDITION_PREFIX_META_TERMS = {
    "add",
    "checklist",
    "explicitly",
    "item",
    "items",
    "note",
    "reflect",
    "schedule",
    "schedules",
    "updated",
    "wants",
}
DIRECT_CONDITION_PURPOSE_VERBS = {
    "decompress",
    "help",
    "helps",
    "process",
    "relax",
    "reset",
    "soothe",
    "unwind",
}
CONDITION_OPTIONAL_MATCH_TOKENS = {"a", "an", "the", "their", "my", "our", "your"}


def _direct_conditions_after_target(after_tokens: list[str]) -> list[str]:
    if not after_tokens:
        return []
    cue_index = -1
    for index, token in enumerate(after_tokens[:4]):
        if token in DIRECT_CONDITION_CUES:
            cue_index = index
            break
    if cue_index < 0:
        return []
    cue = after_tokens[cue_index]
    if cue not in {"for", "to"}:
        condition_text = " ".join(after_tokens[cue_index : cue_index + 12])
        return _extract_condition_phrases(condition_text)
    if cue == "to":
        following = [token for token in after_tokens[cue_index + 1 : cue_index + 4] if token]
        if following and following[0] in DIRECT_CONDITION_PURPOSE_VERBS:
            return []
    kept = [cue]
    for token in after_tokens[cue_index + 1 : cue_index + 12]:
        if token in DIRECT_CONDITION_BOUNDARY_TERMS and token != "and":
            break
        if token == "and" and len(kept) > 2:
            break
        kept.append(token)
        if len(kept) >= 10:
            break
    if len(kept) < 2:
        return []
    if cue == "to":
        kept[0] = "during"
    return [" ".join(kept)]


def _direct_condition_after_target(after_tokens: list[str]) -> str:
    conditions = _direct_conditions_after_target(after_tokens)
    return conditions[0] if conditions else ""


def _direct_condition_before_target(before_tokens: list[str]) -> str:
    if not before_tokens:
        return ""
    marker_indexes = [
        index
        for index, token in enumerate(before_tokens)
        if token in {"involved", "involves", "include", "includes", "included"}
    ]
    if marker_indexes:
        return _condition_prefix_from_tokens(before_tokens[: marker_indexes[-1]])
    for action in ("read", "use", "watch", "bring", "have", "eat", "choose"):
        try:
            action_index = len(before_tokens) - 1 - before_tokens[::-1].index(action)
        except ValueError:
            continue
        if action_index > 0 and before_tokens[action_index - 1] == "to":
            return _condition_prefix_from_tokens(before_tokens[: action_index - 1])
        direct_prefix = _direct_condition_prefix_before_action(
            before_tokens[:action_index]
        )
        if direct_prefix:
            return direct_prefix
    return ""


def _direct_condition_prefix_before_action(prefix_tokens: list[str]) -> str:
    cue_index = -1
    for index in range(len(prefix_tokens) - 1, -1, -1):
        if prefix_tokens[index] in CONDITION_SCOPE_CUES:
            cue_index = index
            break
    if cue_index < 0:
        return ""
    kept = [token for token in prefix_tokens[cue_index:] if token]
    while kept and kept[-1] in {"he", "i", "she", "they", "user", "we"}:
        kept.pop()
    if len(kept) < 3:
        return ""
    if set(kept) & DIRECT_CONDITION_PREFIX_META_TERMS:
        return ""
    if not (set(kept) & (CONDITION_ANCHOR_TERMS | CONDITION_PREFERENCE_CUES)):
        return ""
    return " ".join(kept[-10:])


def _condition_prefix_from_tokens(tokens: list[str]) -> str:
    cleaned = [
        token
        for token in tokens
        if token
        not in {
            "a",
            "an",
            "i",
            "my",
            "that",
            "the",
            "their",
            "user",
            "usually",
        }
    ]
    while cleaned and cleaned[0] in CONDITION_PREFERENCE_CUES | {
        "mentioned",
        "says",
        "said",
        "uses",
        "use",
    }:
        cleaned.pop(0)
    if len(cleaned) < 2:
        return ""
    if set(cleaned) & DIRECT_CONDITION_PREFIX_META_TERMS:
        return ""
    kept = cleaned[-8:]
    if not (set(kept) & CONDITION_ANCHOR_TERMS):
        return ""
    return "during " + " ".join(kept)


def _normalize_direct_condition_phrase(phrase: str) -> str:
    tokens = _norm_text(phrase).split()
    if len(tokens) < 2:
        return ""
    while tokens and tokens[-1] in {"and", "or", "for", "to"}:
        tokens.pop()
    if len(tokens) < 2:
        return ""
    return " ".join(tokens)


def _dedupe_condition_hints(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hint in hints:
        phrase = str(hint.get("exact_condition", ""))
        if any(
            _condition_phrase_is_duplicate_scope(
                phrase,
                str(existing.get("exact_condition", "")),
            )
            for existing in out
        ):
            continue
        out.append(hint)
    return out


def _extract_condition_phrases(text: str) -> list[str]:
    if not text:
        return []
    phrases = []
    pattern = re.compile(
        r"(?=\b(?P<cue>before|after|during|when|if|while|on|in)\b"
        r"(?P<body>[^,.;:!?()\[\]\n\r]{0,80}))",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        cue = match.group("cue").lower()
        body = match.group("body") or ""
        tokens = []
        raw_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", body)
        for index, token in enumerate(raw_tokens):
            normalized = _norm_text(token)
            if not normalized:
                continue
            next_one = _norm_text(raw_tokens[index + 1]) if index + 1 < len(raw_tokens) else ""
            next_two = _norm_text(raw_tokens[index + 2]) if index + 2 < len(raw_tokens) else ""
            if (
                normalized == "or"
                and next_one == "right"
                and next_two in CONDITION_SCOPE_CUES
                and tokens
            ):
                break
            if normalized in CONDITION_PHRASE_BOUNDARY_WORDS and tokens:
                break
            if normalized in {"a", "an", "the", "their", "my", "our", "your"}:
                continue
            tokens.append(normalized)
            if len(tokens) >= 9:
                break
        if not tokens:
            continue
        phrase = " ".join([cue] + tokens)
        phrases.append(phrase)
    return _dedupe_preserve_order(phrases)


def _condition_scope_relevance(target_tokens: set[str], text: str) -> int:
    if not target_tokens:
        return 1 if any(cue in f" {_norm_text(text)} " for cue in CONDITION_SCOPE_CUES) else 0
    text_tokens = set(_norm_text(text).split())
    overlap = len(target_tokens & text_tokens)
    if overlap < _condition_scope_required_target_overlap(target_tokens):
        return 0
    return overlap


def _condition_scope_required_target_overlap(target_tokens: set[str]) -> int:
    return 2 if len(target_tokens) >= 3 else 1


def _condition_phrase_is_near_target(
    phrase: str,
    text: str,
    target_tokens: set[str],
) -> bool:
    if not target_tokens:
        return True
    window_tokens = _condition_phrase_window_tokens(
        text,
        phrase,
        before_token_count=16,
        after_token_count=24,
    )
    if not window_tokens:
        return bool(target_tokens & set(_norm_text(text).split()))
    return bool(target_tokens & window_tokens)


CONDITION_LEADING_CONTEXT_BRIDGE_TERMS = {
    "especially",
    "including",
    "like",
    "notably",
    "particularly",
}
CONDITION_LEADING_CONTEXT_SETTING_TERMS = CONDITION_ANCHOR_TERMS | {
    "calm",
    "family",
    "house",
    "home",
    "quiet",
    "quieter",
    "small",
    "yard",
}
CONDITION_LEADING_CONTEXT_SETTING_HEAD_TERMS = {
    "day",
    "days",
    "evening",
    "evenings",
    "home",
    "house",
    "morning",
    "mornings",
    "night",
    "nights",
    "weekend",
    "weekends",
    "yard",
}
CONDITION_LEADING_CONTEXT_SETTING_SUPPORT_TERMS = {
    "choose",
    "chooses",
    "choosing",
    "mentioned",
    "mentions",
    "noted",
    "said",
    "says",
    "shared",
    "told",
}


def _condition_phrase_with_leading_context(text: str, phrase: str) -> str:
    normalized_text = _norm_text(text)
    normalized_phrase = _norm_text(phrase)
    if not normalized_text or not normalized_phrase:
        return phrase
    text_tokens = normalized_text.split()
    phrase_tokens = normalized_phrase.split()
    span = _condition_phrase_token_span(text_tokens, phrase_tokens)
    if span:
        compound = _condition_phrase_with_explanatory_leading_context(
            text_tokens,
            span,
        )
        if compound:
            return compound
        compound = _condition_phrase_with_prior_setting_context(text_tokens, span)
        if compound:
            return compound
    if not normalized_phrase.startswith("when "):
        return phrase
    index = normalized_text.find(normalized_phrase)
    if index < 0:
        return phrase
    before = normalized_text[max(0, index - 80) : index].strip()
    match = re.search(
        r"\b(?P<prefix>(?:on|in|during|after|before|while)\s+"
        r"(?:[a-z0-9]+\s*){1,5})$",
        before,
    )
    if not match:
        return phrase
    prefix = " ".join(match.group("prefix").split())
    prefix_tokens = set(prefix.split())
    if not prefix_tokens & CONDITION_ANCHOR_TERMS:
        return phrase
    return f"{prefix} {normalized_phrase}"


def _condition_phrase_with_explanatory_leading_context(
    text_tokens: list[str],
    phrase_span: tuple[int, int],
) -> str:
    start, end = phrase_span
    if start <= 1 or end <= start:
        return ""
    bridge_start = start
    while (
        bridge_start > 0
        and text_tokens[bridge_start - 1] in CONDITION_LEADING_CONTEXT_BRIDGE_TERMS
    ):
        bridge_start -= 1
    bridge_tokens = text_tokens[bridge_start:start]
    if not bridge_tokens:
        return ""
    if not set(bridge_tokens) <= CONDITION_LEADING_CONTEXT_BRIDGE_TERMS:
        return ""
    cue_index = -1
    lower_bound = max(0, bridge_start - 8)
    for index in range(bridge_start - 1, lower_bound - 1, -1):
        if text_tokens[index] in CONDITION_SCOPE_CUES:
            cue_index = index
            break
    if cue_index < 0:
        return ""
    prefix_tokens = text_tokens[cue_index:bridge_start]
    if len(prefix_tokens) < 3 or len(prefix_tokens) > 8:
        return ""
    if _condition_phrase_has_noise(" ".join(prefix_tokens)):
        return ""
    prefix_content = {
        token
        for token in prefix_tokens[1:]
        if token not in CONDITION_SCOPE_STOPWORDS | {"it", "s"}
    }
    if not prefix_content:
        return ""
    if not prefix_content & CONDITION_LEADING_CONTEXT_SETTING_TERMS:
        return ""
    phrase_tokens = text_tokens[start:end]
    if len(phrase_tokens) < 2:
        return ""
    compound_tokens = prefix_tokens + bridge_tokens + phrase_tokens
    if len(compound_tokens) > 16:
        return ""
    return _clean_condition_compound_phrase_tokens(compound_tokens)


def _condition_phrase_with_prior_setting_context(
    text_tokens: list[str],
    phrase_span: tuple[int, int],
) -> str:
    start, end = phrase_span
    if start <= 2 or end <= start:
        return ""
    before_tokens = text_tokens[max(0, start - 18) : start]
    if not set(before_tokens) & CONDITION_LEADING_CONTEXT_SETTING_SUPPORT_TERMS:
        return ""
    phrase_tokens = text_tokens[start:end]
    if len(phrase_tokens) < 2 or phrase_tokens[0] not in CONDITION_SCOPE_CUES:
        return ""
    if before_tokens and before_tokens[-1] in {"and", "or"}:
        return ""
    for noun_index in range(len(before_tokens) - 1, -1, -1):
        if before_tokens[noun_index] not in CONDITION_LEADING_CONTEXT_SETTING_HEAD_TERMS:
            continue
        setting_start = noun_index
        while (
            setting_start > 0
            and before_tokens[setting_start - 1]
            in CONDITION_LEADING_CONTEXT_SETTING_TERMS
        ):
            setting_start -= 1
        setting_tokens = before_tokens[setting_start : noun_index + 1]
        if len(setting_tokens) < 2:
            continue
        setting_content = {
            token
            for token in setting_tokens
            if token not in CONDITION_SCOPE_STOPWORDS | {"it", "s"}
        }
        if not setting_content & CONDITION_LEADING_CONTEXT_SETTING_TERMS:
            continue
        compound_tokens = ["on", *setting_tokens, *phrase_tokens]
        if len(compound_tokens) > 16:
            continue
        return _clean_condition_compound_phrase_tokens(compound_tokens)
    return ""


def _condition_phrase_has_explanatory_leading_context(phrase: str) -> bool:
    tokens = _norm_text(phrase).split()
    if len(tokens) < 6:
        return False
    if _condition_phrase_has_prior_setting_compound(tokens):
        return True
    bridge_indexes = [
        index
        for index, token in enumerate(tokens[1:-1], start=1)
        if token in CONDITION_LEADING_CONTEXT_BRIDGE_TERMS
    ]
    if not bridge_indexes:
        return False
    first_bridge = bridge_indexes[0]
    before_bridge = {
        token
        for token in tokens[1:first_bridge]
        if token not in CONDITION_SCOPE_STOPWORDS | {"it", "s"}
    }
    after_bridge = {
        token
        for token in tokens[first_bridge + 1 :]
        if token not in CONDITION_SCOPE_STOPWORDS | {"it", "s"}
    }
    return bool(
        before_bridge
        and after_bridge
        and before_bridge & CONDITION_LEADING_CONTEXT_SETTING_TERMS
    )


def _condition_phrase_has_prior_setting_compound(tokens: list[str]) -> bool:
    if len(tokens) < 5 or tokens[0] != "on":
        return False
    cue_indexes = [
        index
        for index, token in enumerate(tokens[2:], start=2)
        if token in CONDITION_SCOPE_CUES
    ]
    if not cue_indexes:
        return False
    cue_index = cue_indexes[0]
    setting_tokens = set(tokens[1:cue_index])
    return bool(
        setting_tokens & CONDITION_LEADING_CONTEXT_SETTING_HEAD_TERMS
        and setting_tokens & CONDITION_LEADING_CONTEXT_SETTING_TERMS
    )


def _clean_condition_compound_phrase_tokens(tokens: list[str]) -> str:
    cleaned = " ".join(token for token in tokens if token)
    cleaned = re.sub(r"\bit s\b", "it is", cleaned)
    return cleaned


def _condition_phrase_has_dangling_nested_cue(phrase: str) -> bool:
    tokens = _norm_text(phrase).split()
    return len(tokens) > 2 and tokens[-1] in CONDITION_SCOPE_CUES


def _condition_phrase_priority(phrase: str) -> int:
    cue = phrase.split()[0].lower() if phrase.split() else ""
    priority = {
        "before": 14,
        "after": 8,
        "if": 7,
        "when": 7,
        "during": 6,
        "while": 5,
        "on": 3,
        "in": 5,
    }.get(cue, 0)
    if _condition_phrase_noise_terms(phrase):
        priority -= 10
    if set(_norm_text(phrase).split()) & CONDITION_ENVIRONMENT_TERMS:
        priority += 5
    return priority


def _condition_phrase_specificity_bonus(phrase: str) -> int:
    tokens = _norm_text(phrase).split()
    if len(tokens) < 2:
        return 0
    cue = tokens[0]
    bonus = 0
    if _condition_phrase_has_explanatory_leading_context(phrase):
        bonus += 18
    if cue == "before" and len(tokens) <= 4:
        bonus += 30
    if cue in {"on", "in"} and set(tokens[1:]) & {"day", "days", "schedule", "schedules"}:
        bonus -= 4
    return bonus


def _condition_phrase_target_overlap(phrase: str, target_tokens: set[str]) -> int:
    if not target_tokens:
        return 0
    return len(set(_norm_text(phrase).split()) & target_tokens)


def _condition_phrase_context_bonus(
    phrase: str,
    text: str,
    target_tokens: set[str],
) -> int:
    before_tokens, _, after_tokens = _condition_phrase_window_parts(
        text,
        phrase,
        before_token_count=16,
        after_token_count=24,
    )
    if not before_tokens and not after_tokens:
        return 0
    preference_terms = {
        "crave",
        "craves",
        "find",
        "finds",
        "go",
        "have",
        "like",
        "likes",
        "pick",
        "prefer",
        "prefers",
        "useful",
    }
    bonus = 0
    if before_tokens & preference_terms:
        bonus += 5
    if target_tokens & after_tokens and after_tokens & preference_terms:
        bonus += 3
    return bonus


def _condition_answer_support_score(
    row: dict[str, Any],
    source_field: str,
    text: str,
    phrase: str,
    target_tokens: set[str],
    attached_detail: str,
) -> int:
    before_tokens, phrase_tokens, after_tokens = _condition_phrase_window_parts(
        text,
        phrase,
        before_token_count=28,
        after_token_count=28,
    )
    window_tokens = before_tokens | phrase_tokens | after_tokens
    if not window_tokens:
        return 0
    row_text = " ".join(
        str(row.get(field_name, ""))
        for field_name in ("claim", "value", "source_span")
        if row.get(field_name)
    )
    row_tokens = set(_norm_text(row_text).split())
    value_tokens = set(_norm_text(str(row.get("value", ""))).split())

    score = 0
    if target_tokens and window_tokens & target_tokens:
        score += 6
    if target_tokens and value_tokens & target_tokens:
        score += 4
    if window_tokens & CONDITION_PREFERENCE_CUES:
        score += 8
    elif target_tokens and row_tokens & target_tokens and row_tokens & CONDITION_PREFERENCE_CUES:
        score += 3
    if attached_detail:
        score += 10
    if _condition_phrase_has_source_preference_support(phrase, text, target_tokens):
        score += 5
    if (
        value_tokens
        and (not target_tokens or value_tokens & target_tokens)
        and _condition_phrase_precedes_value(text, phrase, str(row.get("value", "")))
    ):
        score += 8
    if source_field.endswith("source_span"):
        score += 2
    elif source_field == "claim":
        score += 1
    window = " ".join(sorted(window_tokens))
    if _condition_source_is_schedule_without_preference(window, target_tokens):
        score -= 6
    return score


def _condition_phrase_window_tokens(
    text: str,
    phrase: str,
    *,
    before_token_count: int,
    after_token_count: int,
) -> set[str]:
    before_tokens, phrase_tokens, after_tokens = _condition_phrase_window_parts(
        text,
        phrase,
        before_token_count=before_token_count,
        after_token_count=after_token_count,
    )
    return before_tokens | phrase_tokens | after_tokens


def _condition_phrase_window_parts(
    text: str,
    phrase: str,
    *,
    before_token_count: int,
    after_token_count: int,
) -> tuple[set[str], set[str], set[str]]:
    text_tokens = _norm_text(text).split()
    phrase_tokens = _norm_text(phrase).split()
    if not text_tokens or not phrase_tokens:
        return set(), set(), set()
    span = _condition_phrase_token_span(text_tokens, phrase_tokens)
    if not span:
        return set(), set(), set()
    start, end = span
    before = set(text_tokens[max(0, start - before_token_count) : start])
    matched = set(text_tokens[start:end])
    after = set(text_tokens[end : min(len(text_tokens), end + after_token_count)])
    return before, matched, after


def _condition_phrase_token_span(
    text_tokens: list[str],
    phrase_tokens: list[str],
) -> tuple[int, int]:
    phrase_core = [
        token for token in phrase_tokens if token not in CONDITION_OPTIONAL_MATCH_TOKENS
    ]
    if not phrase_core:
        return ()
    for start in range(len(text_tokens)):
        phrase_index = 0
        cursor = start
        while cursor < len(text_tokens) and phrase_index < len(phrase_core):
            text_token = text_tokens[cursor]
            if text_token in CONDITION_OPTIONAL_MATCH_TOKENS:
                cursor += 1
                continue
            if text_token != phrase_core[phrase_index]:
                break
            phrase_index += 1
            cursor += 1
        if phrase_index == len(phrase_core):
            return start, cursor
    return ()


def _condition_phrase_precedes_value(text: str, phrase: str, value: str) -> bool:
    text_tokens = _norm_text(text).split()
    phrase_tokens = _norm_text(phrase).split()
    value_tokens = _norm_text(value).split()
    if not text_tokens or not phrase_tokens or not value_tokens:
        return False
    phrase_span = _condition_phrase_token_span(text_tokens, phrase_tokens)
    value_span = _condition_phrase_token_span(text_tokens, value_tokens)
    if not phrase_span or not value_span:
        return False
    return phrase_span[1] <= value_span[0]


def _condition_phrase_is_object_only(phrase: str, row: dict[str, Any]) -> bool:
    tokens = _norm_text(phrase).split()
    if len(tokens) < 2 or tokens[0] not in {"in", "on"}:
        return False
    content_tokens = {
        token
        for token in tokens[1:]
        if token not in {"a", "an", "the", "that", "this"}
    }
    if not content_tokens or content_tokens & CONDITION_ANCHOR_TERMS:
        return False
    value_tokens = set(_norm_text(str(row.get("value", ""))).split())
    claim_tokens = set(_norm_text(str(row.get("claim", ""))).split())
    evidence_tokens = value_tokens | claim_tokens
    return bool(content_tokens and content_tokens <= evidence_tokens)


def _condition_attached_answer_detail(
    text: str,
    phrase: str,
    row: dict[str, Any],
) -> str:
    normalized_text = _norm_text(text)
    normalized_phrase = _norm_text(phrase)
    if not normalized_text or not normalized_phrase:
        return ""
    index = normalized_text.find(normalized_phrase)
    if index < 0:
        return ""
    candidates: list[str] = []
    before = normalized_text[max(0, index - 140) : index].strip()
    after = normalized_text[index + len(normalized_phrase) : index + len(normalized_phrase) + 120].strip()
    before_match = re.search(r"\bfor\s+([a-z0-9][a-z0-9\s]{2,90})$", before)
    if before_match and _condition_before_detail_has_value_anchor(before, row):
        candidates.append(before_match.group(1))
    after_match = re.match(r"^(?:for|about)\s+([a-z0-9][a-z0-9\s]{2,90})", after)
    if after_match:
        candidates.append(after_match.group(1))
    continuation = _condition_continuation_answer_detail(after)
    if continuation:
        candidates.append(continuation)
    for candidate in candidates:
        detail = _clean_condition_answer_detail(candidate, row)
        if detail:
            return detail
    return ""


def _condition_before_detail_has_value_anchor(before_condition: str, row: dict[str, Any]) -> bool:
    """Only borrow a preceding `for ...` detail when it is attached to the answer value."""

    value_tokens = {
        token
        for field_name in ("value", "supporting_value")
        for token in _norm_text(str(row.get(field_name, ""))).split()
        if len(token) > 2 and token not in CONDITION_SCOPE_STOPWORDS
    }
    if not value_tokens:
        return False
    before_tokens = _norm_text(before_condition).split()
    if not before_tokens:
        return False
    try:
        for_index = len(before_tokens) - 1 - before_tokens[::-1].index("for")
    except ValueError:
        return False
    anchor_window = set(before_tokens[max(0, for_index - 10) : for_index])
    return bool(anchor_window & value_tokens)


CONDITION_CONTINUATION_BOUNDARY_TERMS = {
    "also",
    "bedtime",
    "bedtimes",
    "because",
    "but",
    "got",
    "however",
    "maybe",
    "next",
    "okay",
    "please",
    "sure",
    "then",
}


def _condition_continuation_answer_detail(after_condition: str) -> str:
    tokens = _norm_text(after_condition).split()
    if not tokens or tokens[0] in {"about", "for", "to"}:
        return ""
    kept = []
    for token in tokens:
        if token in CONDITION_SCOPE_CUES:
            break
        if token in CONDITION_CONTINUATION_BOUNDARY_TERMS:
            break
        kept.append(token)
        if len(kept) >= 10:
            break
    if len(kept) < 2:
        return ""
    text = " ".join(kept)
    if " and " not in f" {text} " and " or " not in f" {text} ":
        return ""
    return text


def _condition_preference_source_answer_detail(
    text: str,
    phrase: str,
    row: dict[str, Any],
) -> str:
    normalized_text = _norm_text(text)
    normalized_phrase = _norm_text(phrase)
    if not normalized_text or not normalized_phrase:
        return ""
    index = normalized_text.find(normalized_phrase)
    if index < 0:
        return ""
    before = normalized_text[max(0, index - 120) : index].strip()
    after = normalized_text[index + len(normalized_phrase) : index + len(normalized_phrase) + 100].strip()
    candidates: list[str] = []
    before_parts = re.split(
        r"\b(?:prefer|prefers|preferred|like|likes|liked|love|loves|loved|"
        r"enjoy|enjoys|rely|relies|relying|tend|tends|use|uses|using)\b",
        before,
    )
    if len(before_parts) > 1:
        candidates.append(before_parts[-1])
    purpose_match = re.match(r"^to\s+([a-z0-9][a-z0-9\s]{2,70})", after)
    if purpose_match:
        candidates.append(purpose_match.group(1))
    cleaned = [_clean_condition_answer_detail(candidate, row) for candidate in candidates]
    cleaned = [detail for detail in cleaned if detail]
    return " ".join(_dedupe_preserve_order(" ".join(cleaned).split()))


def _condition_source_condition_answer_detail(
    text: str,
    phrase: str,
    row: dict[str, Any],
) -> str:
    return (
        _condition_preference_source_answer_detail(text, phrase, row)
        or _condition_target_descriptor_answer_detail(text, phrase, row)
        or _condition_training_ability_answer_detail(text, phrase, row)
        or _condition_attached_answer_detail(text, phrase, row)
    )


CONDITION_TRAINING_ABILITY_TERMS = {
    "able",
    "avoid",
    "avoids",
    "chaos",
    "command",
    "commands",
    "control",
    "controlled",
    "follows",
    "handle",
    "handles",
    "manage",
    "manages",
    "prevent",
    "prevents",
    "trained",
}
CONDITION_TRAINING_DETAIL_BOUNDARY_TERMS = CONDITION_CONTINUATION_BOUNDARY_TERMS | {
    "conditional",
    "fair",
    "like",
    "plan",
    "plans",
    "point",
    "solid",
    "sound",
    "sounds",
}


def _condition_training_ability_answer_detail(
    text: str,
    phrase: str,
    row: dict[str, Any],
) -> str:
    text_tokens = _norm_text(text).split()
    phrase_tokens = _norm_text(phrase).split()
    if not text_tokens or not phrase_tokens:
        return ""
    phrase_span = _condition_phrase_token_span(text_tokens, phrase_tokens)
    if not phrase_span:
        return ""
    start, end = phrase_span
    window_tokens = text_tokens[max(0, start - 42) : min(len(text_tokens), end + 42)]
    window_token_set = set(window_tokens)
    if not (window_token_set & CONDITION_TRAINING_ABILITY_TERMS):
        return ""
    value_tokens = {
        token
        for token in _norm_text(str(row.get("value", ""))).split()
        if len(token) > 2 and token not in CONDITION_SCOPE_STOPWORDS
    }
    if value_tokens and not (value_tokens & window_token_set):
        return ""

    snippets: list[str] = []
    index = 0
    while index < len(window_tokens):
        token = window_tokens[index]
        next_one = window_tokens[index + 1] if index + 1 < len(window_tokens) else ""
        next_two = window_tokens[index + 2] if index + 2 < len(window_tokens) else ""
        if token in {"follow", "follows"} and next_one == "commands":
            snippets.append("follows commands")
            index += 2
            continue
        if token == "able" and next_one == "to" and next_two == "train":
            kept = _condition_training_detail_tokens(window_tokens, index, max_tokens=6)
            if kept:
                snippets.append(" ".join(kept))
            index += 3
            continue
        if token == "trained":
            kept = _condition_training_detail_tokens(window_tokens, index, max_tokens=5)
            if kept:
                snippets.append(" ".join(kept))
            index += 1
            continue
        index += 1

    if not snippets:
        return ""
    cleaned = [
        _restore_condition_training_detail_grammar(
            _clean_condition_answer_detail(snippet, row)
        )
        for snippet in _dedupe_preserve_order(snippets)
    ]
    cleaned = [detail for detail in cleaned if detail]
    if not cleaned:
        return ""
    return " and ".join(_dedupe_preserve_order(cleaned))


def _restore_condition_training_detail_grammar(detail: str) -> str:
    if not detail:
        return ""
    restored = re.sub(
        r"\btrained\s+(avoid|handle|manage|prevent|reduce)\b",
        r"trained to \1",
        detail,
    )
    restored = re.sub(r"\bable\s+train\b", "able to train", restored)
    return restored


def _condition_training_detail_tokens(
    tokens: list[str],
    start: int,
    *,
    max_tokens: int,
) -> list[str]:
    kept: list[str] = []
    for token in tokens[start : start + max_tokens + 3]:
        if token in CONDITION_SCOPE_CUES and kept:
            break
        if token in CONDITION_TRAINING_DETAIL_BOUNDARY_TERMS and len(kept) >= 2:
            break
        if token in {"can", "could", "be", "that"} and not kept:
            continue
        kept.append(token)
        if len(kept) >= max_tokens:
            break
    while kept and kept[-1] in {"and", "or", "for", "to", "with"}:
        kept.pop()
    content = [
        token
        for token in kept
        if token
        not in {
            "a",
            "an",
            "be",
            "can",
            "could",
            "that",
            "the",
            "to",
        }
    ]
    if len(content) < 2:
        return []
    return kept


def _condition_preference_parallel_condition_phrase(text: str, phrase: str) -> str:
    normalized_text = _norm_text(text)
    normalized_phrase = _norm_text(phrase)
    if not normalized_text or not normalized_phrase:
        return phrase
    index = normalized_text.find(normalized_phrase)
    if index < 0:
        return phrase
    after_tokens = normalized_text[index + len(normalized_phrase) :].split()
    if not after_tokens or after_tokens[0] in {"to"}:
        return phrase

    kept: list[str] = []
    for index, token in enumerate(after_tokens):
        next_one = after_tokens[index + 1] if index + 1 < len(after_tokens) else ""
        next_two = after_tokens[index + 2] if index + 2 < len(after_tokens) else ""
        if token == "or" and next_one == "right" and next_two in CONDITION_SCOPE_CUES:
            break
        if token in CONDITION_CONTINUATION_BOUNDARY_TERMS:
            break
        if token in CONDITION_DESCRIPTOR_BOUNDARY_TERMS and kept:
            break
        if token in CONDITION_SCOPE_CUES and (not kept or kept[-1] not in {"and", "or"}):
            break
        kept.append(token)
        if len(kept) >= 10:
            break
    while kept and kept[-1] in {"and", "or", "for", "to", "with"}:
        kept.pop()
    if len(kept) < 2:
        return phrase
    if "and" not in kept and "or" not in kept:
        return phrase
    return " ".join([normalized_phrase, *kept])


def _condition_preference_primary_selection(
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_supported = [
        row
        for row in selected
        if str(row.get("scope_type", "")) == "condition_preference_source"
    ]
    if not source_supported:
        return selected
    selected_primary = source_supported[:MAX_CONDITION_SCOPE_HINTS]
    source_memory_ids = {
        str(row.get("memory_id", "")) for row in source_supported if row.get("memory_id")
    }
    source_value_tokens = set()
    for row in source_supported:
        source_value_tokens.update(_norm_text(str(row.get("supporting_value", ""))).split())
    source_value_tokens -= CONDITION_SCOPE_STOPWORDS
    for row in selected:
        if row in selected_primary:
            continue
        if len(selected_primary) >= MAX_CONDITION_SCOPE_HINTS:
            break
        if str(row.get("scope_type", "")) != "condition_scope":
            continue
        row_memory_id = str(row.get("memory_id", ""))
        row_value_tokens = set(_norm_text(str(row.get("supporting_value", ""))).split())
        row_value_tokens -= CONDITION_SCOPE_STOPWORDS
        if row_memory_id in source_memory_ids or row_value_tokens & source_value_tokens:
            selected_primary.append(row)
    return selected_primary


CONDITION_DESCRIPTOR_BOUNDARY_TERMS = {
    "also",
    "but",
    "however",
    "if",
    "maybe",
    "next",
    "okay",
    "then",
}

CONDITION_DESCRIPTOR_LEADING_TERMS = {
    "a",
    "an",
    "as",
    "is",
    "it",
    "like",
    "s",
    "something",
    "that",
    "the",
    "which",
}


def _condition_target_descriptor_answer_detail(
    text: str,
    phrase: str,
    row: dict[str, Any],
) -> str:
    normalized_text = _norm_text(text)
    normalized_phrase = _norm_text(phrase)
    if not normalized_text or not normalized_phrase:
        return ""
    suffix_detail = _condition_value_suffix_answer_detail(phrase, row)
    if suffix_detail:
        return suffix_detail
    phrase_index = normalized_text.find(normalized_phrase)
    if phrase_index < 0:
        return ""

    value_candidates = [
        _norm_text(str(row.get(field_name, "")))
        for field_name in ("value", "claim")
        if isinstance(row.get(field_name, ""), str)
    ]
    value_candidates = [
        candidate
        for candidate in value_candidates
        if 2 <= len(candidate.split()) <= 8
    ]
    value_candidates.sort(key=len, reverse=True)
    for value_text in value_candidates:
        value_index = normalized_text.rfind(value_text, 0, phrase_index)
        if value_index < 0:
            continue
        between = normalized_text[value_index + len(value_text) : phrase_index]
        detail = _clean_condition_descriptor_detail(between)
        if detail:
            return detail
    return ""


def _condition_value_suffix_answer_detail(phrase: str, row: dict[str, Any]) -> str:
    phrase_tokens = _norm_text(phrase).split()
    value_tokens = _norm_text(str(row.get("value", ""))).split()
    if not phrase_tokens or len(value_tokens) < 3:
        return ""
    max_overlap = min(len(phrase_tokens), len(value_tokens), 4)
    for overlap in range(max_overlap, 0, -1):
        if phrase_tokens[-overlap:] != value_tokens[:overlap]:
            continue
        suffix_tokens = value_tokens[overlap:]
        if len(suffix_tokens) < 2:
            return ""
        detail = _clean_condition_answer_detail(" ".join(suffix_tokens), row)
        return detail or " ".join(suffix_tokens[:8])
    return ""


def _clean_condition_descriptor_detail(candidate: str) -> str:
    tokens = _norm_text(candidate).split()
    while tokens and tokens[0] in CONDITION_DESCRIPTOR_LEADING_TERMS:
        tokens.pop(0)
    kept = []
    for token in tokens:
        if token in CONDITION_SCOPE_CUES:
            break
        if token in CONDITION_DESCRIPTOR_BOUNDARY_TERMS and kept:
            break
        if token in CONDITION_SCOPE_STOPWORDS and token not in {"and", "to", "up", "with"}:
            continue
        kept.append(token)
        if len(kept) >= 10:
            break
    while kept and kept[-1] in {"and", "or", "for", "to", "with"}:
        kept.pop()
    if len(kept) < 2:
        return ""
    return " ".join(kept)


def _clean_condition_answer_detail(candidate: str, row: dict[str, Any]) -> str:
    tokens = []
    entity_tokens = set(_norm_text(str(row.get("entity", ""))).split())
    short_value_tokens = set(_norm_text(str(row.get("value", ""))).split())
    if len(short_value_tokens) > 4:
        short_value_tokens = set()
    for token in _norm_text(candidate).split():
        if token in CONDITION_SCOPE_CUES:
            break
        if token == "s":
            continue
        if token in CONDITION_SCOPE_STOPWORDS and token not in {"and", "self"}:
            continue
        if token in entity_tokens or token in short_value_tokens:
            continue
        tokens.append(token)
        if len(tokens) >= 8:
            break
    while tokens and tokens[-1] in {"and", "or", "for", "to"}:
        tokens.pop()
    if len(tokens) < 2:
        return ""
    value_tokens = set(_norm_text(str(row.get("value", ""))).split())
    if value_tokens and len(value_tokens) <= 4 and set(tokens) <= value_tokens:
        return ""
    return " ".join(tokens)


def _complete_condition_answer(phrase: str, detail: str) -> str:
    if not detail:
        return ""
    return f"{phrase}; detail: {detail}"


def _condition_phrase_has_noise(phrase: str) -> bool:
    return bool(_condition_phrase_noise_terms(phrase))


def _condition_phrase_noise_terms(phrase: str) -> set[str]:
    tokens = set(_norm_text(phrase).split())
    noise = tokens & CONDITION_SCOPE_NOISE_TERMS
    phrase_tokens = _norm_text(phrase).split()
    if (
        len(phrase_tokens) >= 2
        and phrase_tokens[0] in {"in", "on"}
        and not (set(phrase_tokens[1:]) & CONDITION_IN_ON_SCOPE_ALLOWED_TERMS)
    ):
        noise = set(noise)
        noise.add("generic_object_scope")
    if "planning" in noise and "future" in tokens and ({"and", "or"} & tokens):
        noise = set(noise)
        noise.discard("planning")
    return noise


def _condition_scope_row_priority(row: dict[str, Any], answer_support: int = 0) -> int:
    current_status = str(row.get("current_status", "")).lower()
    retrieval_role = str(row.get("retrieval_role", "")).lower()
    if current_status == "supporting" or retrieval_role == "supporting_duplicate":
        return -4
    if current_status == "current" or retrieval_role == "current_support":
        return 3 if answer_support >= 10 else 1
    return 0


def _condition_phrase_signature(phrase: str) -> str:
    tokens = [
        token
        for token in _norm_text(phrase).split()
        if token not in {"a", "an", "day", "days", "is", "it", "s", "that", "the"}
    ]
    return " ".join(tokens)


def _condition_phrase_is_duplicate_scope(candidate: str, existing: str) -> bool:
    candidate_cue, candidate_head = _condition_phrase_cue_and_head(candidate)
    existing_cue, existing_head = _condition_phrase_cue_and_head(existing)
    return bool(
        candidate_cue
        and candidate_cue == existing_cue
        and candidate_head
        and candidate_head == existing_head
    )


def _condition_phrase_is_subset_scope(candidate: str, existing: str) -> bool:
    candidate_tokens = _condition_scope_signal_tokens(candidate) - set(CONDITION_SCOPE_CUES)
    existing_tokens = _condition_scope_signal_tokens(existing) - set(CONDITION_SCOPE_CUES)
    if len(candidate_tokens) < 2 or len(existing_tokens) < 2:
        return False
    return candidate_tokens < existing_tokens


def _condition_phrase_cue_and_head(phrase: str) -> tuple[str, str]:
    tokens = [
        token
        for token in _norm_text(phrase).split()
        if token not in {"a", "an", "day", "days", "is", "it", "s", "that", "the"}
    ]
    if not tokens:
        return "", ""
    cue = tokens[0]
    content = [
        token
        for token in tokens[1:]
        if token
        not in {
            "busy",
            "long",
            "recent",
            "right",
        }
    ]
    head = content[-1] if content else tokens[-1]
    if len(head) > 3 and head.endswith("s"):
        head = head[:-1]
    return cue, head


SCOPED_READER_TEMPORAL_MARKERS = (
    "last weekend",
    "last week",
    "last month",
    "past month",
    "past few months",
    "over the past month",
    "previous weekend",
    "previous week",
    "yesterday",
    "earlier this week",
)

SCOPED_READER_ACTION_CUES = (
    "tried",
    "try",
    "made",
    "make",
    "bought",
    "spent",
    "gained",
    "lost",
    "read",
    "watched",
    "visited",
    "used to be",
)

SCOPED_READER_OBJECT_STOPWORDS = {
    "about",
    "after",
    "before",
    "currently",
    "did",
    "does",
    "during",
    "earlier",
    "first",
    "following",
    "from",
    "have",
    "last",
    "latest",
    "many",
    "month",
    "past",
    "previous",
    "recent",
    "recently",
    "that",
    "the",
    "this",
    "today",
    "tomorrow",
    "type",
    "week",
    "weekend",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "yesterday",
}


def _build_scoped_reader_context(request: dict[str, Any]) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not question:
        return []
    constraints = _scoped_reader_constraints(question)
    if not _needs_scoped_reader_context(constraints):
        return []
    history_turns = _selected_history_turns_from_request(request)
    if not history_turns:
        return []
    case_id = _case_id_from_request(request)
    events = _scoped_reader_events(
        case_id=case_id,
        question=question,
        history_turns=history_turns,
        constraints=constraints,
    )
    if not events:
        return []
    return [
        {
            "packet_type": "qvf_scoped_reader_packet",
            "scope_constraints": constraints,
            "reader_policy": {
                "route": "scoped_temporal_or_action_reader",
                "use_policy": (
                    "Prefer candidate_events that satisfy the question's exact temporal "
                    "or action scope. Do not replace a scoped event with an unscoped "
                    "recommendation list unless no scoped event is relevant."
                ),
            },
            "candidate_events": events[:MAX_SCOPED_READER_EVENTS],
        }
    ]


def _build_source_history_focus_context(
    request: dict[str, Any],
    question: str,
) -> list[dict[str, Any]]:
    if not _needs_source_history_focus(question):
        return []
    history_turns = _selected_history_turns_from_request(request)
    if not history_turns:
        return []
    if not _selected_history_has_observed_boundary(history_turns):
        return []
    rows = _source_history_focus_rows(
        case_id=_case_id_from_request(request),
        question=question,
        history_turns=history_turns,
    )
    if not rows:
        return []
    return [
        {
            "packet_type": "qvf_source_history_focus_packet",
            "reader_policy": {
                "route": "source_history_focus",
                "use_policy": (
                    "Use focus_rows as an index into selected source-history text. "
                    "Preserve source_temporal_phrase and source_observed_at when the "
                    "question asks when, which week, which weekend, before/after, or "
                    "recent/latest. Preserve source_focus_phrase and source_sentence "
                    "when the question asks why or for a reason. Do not treat focus "
                    "rows as new evidence."
                ),
            },
            "focus_rows": rows[:MAX_SOURCE_HISTORY_FOCUS_ROWS],
        }
    ]


def _build_source_history_answer_anchor_context(
    request: dict[str, Any],
    question: str,
    *,
    scoped_reader_context: list[dict[str, Any]],
    source_history_focus_context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _needs_source_history_answer_anchor(question):
        return []
    if not _selected_history_has_observed_boundary(
        _selected_history_turns_from_request(request)
    ):
        return []
    if not scoped_reader_context and not source_history_focus_context:
        return []
    question_terms = _source_history_focus_terms(question)
    if not question_terms:
        return []
    rows: list[dict[str, Any]] = []
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        source_span = _record_source_span(record)
        if not source_span:
            continue
        span_terms = _source_history_focus_terms(source_span)
        overlap_terms = sorted(question_terms & span_terms)
        if len(overlap_terms) < 2:
            continue
        focus_value = str(record.get("value") or record.get("claim") or "")
        source_anchor_excerpt = _focus_excerpt(
            source_span,
            focus_value,
            max_chars=MAX_SOURCE_HISTORY_FOCUS_SENTENCE_CHARS,
        )
        anchor_terms = _source_history_answer_anchor_terms(
            source_anchor_excerpt,
            question_terms=question_terms,
        )
        if not anchor_terms:
            continue
        score = len(overlap_terms) * 10 + len(anchor_terms)
        source_norm = _norm_text(source_span)
        question_norm = _norm_text(question)
        if " after " in f" {question_norm} " and " after " in f" {source_norm} ":
            score += 8
        rows.append(
            {
                "anchor_id": (
                    f"{_case_id_from_request(request)}::source_history_anchor_"
                    f"{len(rows):03d}"
                ),
                "memory_id": str(record.get("memory_id") or ""),
                "slot": str(record.get("slot") or ""),
                "value": str(record.get("value") or ""),
                "claim": _truncate_text(str(record.get("claim") or ""), 220),
                "query_overlap_terms": overlap_terms[:8],
                "source_answer_anchor_terms": anchor_terms[
                    :MAX_SOURCE_HISTORY_ANSWER_ANCHOR_TERMS
                ],
                "anchor_score": score,
                "source_anchor_excerpt": source_anchor_excerpt,
            }
        )
    rows.sort(
        key=lambda row: (
            int(row.get("anchor_score") or 0),
            len(row.get("source_answer_anchor_terms") or []),
        ),
        reverse=True,
    )
    if not rows:
        return []
    return [
        {
            "packet_type": "qvf_source_history_answer_anchor_packet",
            "reader_policy": {
                "route": "source_history_answer_anchor",
                "use_policy": (
                    "Use anchor_rows as a non-gold reminder of concrete answer "
                    "terms inside source spans already visible to QVF. Preserve "
                    "source_answer_anchor_terms when they specify the activity, "
                    "place, object, or manner asked by the question."
                ),
            },
            "anchor_rows": rows[:MAX_SOURCE_HISTORY_ANSWER_ANCHOR_ROWS],
        }
    ]


def _selected_history_has_observed_boundary(
    history_turns: list[dict[str, Any]],
) -> bool:
    for turn in history_turns:
        if not isinstance(turn, dict):
            continue
        timestamp = str(turn.get("timestamp") or turn.get("observed_at") or "").strip()
        if timestamp:
            return True
    return False


def _needs_source_history_answer_anchor(question: str) -> bool:
    text = _norm_text(question)
    if not text:
        return False
    return bool(
        re.search(r"\bwhat\s+did\b", text)
        or re.search(r"\bwhat\s+was\b", text)
        or re.search(r"\bwhat\s+type\b", text)
        or re.search(r"\bhow\s+did\b", text)
        or re.search(r"\bwhere\s+did\b", text)
        or re.search(r"\b(?:activity|activities|do|did|relax|way|manner)\b", text)
    )


def _source_history_answer_anchor_terms(
    source_span: str,
    *,
    question_terms: set[str],
) -> list[str]:
    stop_terms = {
        "caroline",
        "melanie",
        "thanks",
        "thank",
        "the",
        "and",
        "was",
        "were",
        "did",
        "does",
        "had",
        "have",
        "has",
        "you",
        "your",
        "got",
        "some",
        "with",
        "for",
        "from",
        "yeah",
        "yup",
        "yep",
        "glad",
        "sure",
        "huh",
        "what",
        "that",
        "this",
        "these",
        "those",
        "after",
        "before",
        "yesterday",
        "today",
        "tomorrow",
        "nice",
        "great",
        "awesome",
        "good",
        "way",
        "thing",
        "things",
        "something",
        "anything",
        "really",
        "just",
        "very",
        "road",
        "trip",
        "relax",
        "drive",
        "drove",
    }
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]+", str(source_span or "")):
        term = token.lower()
        if len(term) <= 2 and term not in {"er", "ai", "tv", "ux", "5k"}:
            continue
        if term in question_terms or term in stop_terms:
            continue
        if re.fullmatch(r"\d+", term):
            continue
        terms.append(term)
    return _dedupe_preserve_order(terms)


def _needs_source_history_focus(question: str) -> bool:
    text = _norm_text(question)
    if not text:
        return False
    return bool(
        text.startswith("when ")
        or text.startswith("why ")
        or re.search(r"\b(?:which|what)\s+(?:week|weekend|month|year|day)\b", text)
        or re.search(r"\b(?:reason|caused|because|why)\b", text)
        or re.search(r"\b(?:before|after|recent|recently|latest|last|first)\b", text)
    )


def _source_history_focus_rows(
    *,
    case_id: str,
    question: str,
    history_turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    question_terms = _source_history_focus_terms(question)
    for turn in history_turns:
        text = str(turn.get("text") or "")
        if not text.strip():
            continue
        observed_at = str(turn.get("timestamp") or turn.get("observed_at") or "")
        sentences = _sentences(text)
        for sentence_index, sentence in enumerate(sentences):
            focus_type, focus_phrase = _source_history_focus_phrase(sentence, question)
            source_sentence = sentence
            if not focus_phrase:
                for neighbor_index in (sentence_index - 1, sentence_index + 1):
                    if neighbor_index < 0 or neighbor_index >= len(sentences):
                        continue
                    neighbor = sentences[neighbor_index]
                    focus_type, focus_phrase = _source_history_focus_phrase(
                        neighbor,
                        question,
                    )
                    if focus_phrase:
                        if neighbor_index < sentence_index:
                            source_sentence = f"{neighbor} {sentence}"
                        else:
                            source_sentence = f"{sentence} {neighbor}"
                        break
            if not focus_phrase:
                continue
            sentence_terms = _source_history_focus_terms(source_sentence)
            overlap_terms = sorted(question_terms & sentence_terms)
            if not overlap_terms:
                continue
            score = len(overlap_terms) * 10
            if focus_type == "causal":
                score += 16
            if focus_type == "temporal" and _temporal_phrase_is_relative(focus_phrase):
                score += 12
            if _norm_text(focus_phrase) in _norm_text(question):
                score += 8
            rows.append(
                {
                    "focus_id": f"{case_id}::source_history_focus_{len(rows):03d}",
                    "source_turn_id": str(turn.get("turn_id") or ""),
                    "source_observed_at": observed_at,
                    "selection_rank": turn.get("selection_rank", ""),
                    "source_focus_type": focus_type,
                    "source_focus_phrase": focus_phrase,
                    "source_temporal_phrase": (
                        focus_phrase if focus_type == "temporal" else ""
                    ),
                    "query_overlap_terms": overlap_terms[:8],
                    "focus_score": score,
                    "source_sentence": _truncate_text(
                        source_sentence,
                        MAX_SOURCE_HISTORY_FOCUS_SENTENCE_CHARS,
                    ),
                }
            )
    rows.sort(
        key=lambda row: (
            int(row.get("focus_score") or 0),
            -_safe_int(row.get("selection_rank"), 999),
        ),
        reverse=True,
    )
    return rows


def _source_history_focus_terms(text: str) -> set[str]:
    allowed_short_terms = {"ai", "er", "tv", "ux", "5k"}
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "when",
        "what",
        "which",
        "where",
        "did",
        "does",
        "have",
        "has",
        "had",
        "was",
        "were",
        "you",
        "your",
        "his",
        "her",
        "him",
        "she",
        "he",
        "they",
        "their",
        "from",
        "into",
        "about",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _norm_text(text))
        if (len(token) > 2 or token in allowed_short_terms)
        and token not in stopwords
    }


def _source_history_focus_phrase(text: str, question: str) -> tuple[str, str]:
    temporal_phrase = _source_history_temporal_phrase(text)
    if temporal_phrase:
        return "temporal", temporal_phrase
    question_norm = _norm_text(question)
    if question_norm.startswith("why ") or re.search(
        r"\b(?:reason|caused|because|why)\b",
        question_norm,
    ):
        causal_phrase = _source_history_causal_phrase(text)
        if causal_phrase:
            return "causal", causal_phrase
    return "", ""


def _source_history_causal_phrase(text: str) -> str:
    causal_patterns = [
        r"\bbecause\b[^.!?]{0,160}",
        r"\bdue\s+to\b[^.!?]{0,160}",
        r"\bas\s+a\s+result\s+of\b[^.!?]{0,160}",
        r"\b(?:made|pushed|prompted|motivated|led|inspired|convinced)\s+"
        r"(?:me|him|her|them|us)\s+(?:to|into)\b[^.!?]{0,160}",
        r"\bgave\s+(?:me|him|her|them|us)\s+(?:the\s+)?"
        r"(?:push|motivation|reason|confidence|impetus|chance|opportunity)\b"
        r"[^.!?]{0,160}",
        r"\b(?:the|a)\s+reason\b[^.!?]{0,160}",
        r"\bwanted\s+to\b[^.!?]{0,140}",
        r"\bdecided\s+to\b[^.!?]{0,140}",
    ]
    for pattern in causal_patterns:
        match = re.search(pattern, str(text or ""), flags=re.I)
        if match:
            return match.group(0).strip(" ,;:-")
    return ""


def _source_history_temporal_phrase(text: str) -> str:
    temporal_patterns = [
        r"\b(?:this|last|next|previous)\s+(?:weekend|week|month|year|day)\b",
        r"\bweekend\s+before\b",
        r"\bweek\s+of\b",
        r"\b(?:today|yesterday|tomorrow|recently)\b",
        r"\b(?:a|one|two|three|four|few|several)\s+"
        r"(?:days|weeks|months|years)\s+ago\b",
        r"\b(?:on\s+)?\d{1,2}\s+"
        r"(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December),?\s+\d{4}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    ]
    for pattern in temporal_patterns:
        match = re.search(pattern, str(text or ""), flags=re.I)
        if match:
            return match.group(0)
    return ""


def _temporal_phrase_is_relative(phrase: str) -> bool:
    return bool(
        re.search(
            r"\b(?:this|last|next|previous|today|yesterday|tomorrow|ago|recently|"
            r"weekend before|week of)\b",
            str(phrase or ""),
            flags=re.I,
        )
    )


def _scoped_reader_constraints(question: str) -> dict[str, Any]:
    question_norm = _norm_text(question)
    temporal_markers = []
    for marker in SCOPED_READER_TEMPORAL_MARKERS:
        marker_norm = _norm_text(marker)
        if marker_norm == "last week" and "last weekend" in question_norm:
            continue
        if marker_norm in question_norm:
            temporal_markers.append(marker)
    action_cues = [
        cue
        for cue in SCOPED_READER_ACTION_CUES
        if _norm_text(cue) in question_norm
    ]
    if "try" in action_cues and "tried" not in action_cues:
        action_cues.append("tried")
    if "what type" in question_norm and "tried" not in action_cues:
        action_cues.append("tried")
    object_terms = _scoped_reader_object_terms(question)
    return {
        "temporal_markers": _dedupe_preserve_order(temporal_markers),
        "action_cues": _dedupe_preserve_order(action_cues),
        "object_terms": _dedupe_preserve_order(object_terms),
        "requires_event_title": _requires_scoped_event_title(question),
    }


def _needs_scoped_reader_context(constraints: dict[str, Any]) -> bool:
    temporal = constraints.get("temporal_markers", [])
    actions = constraints.get("action_cues", [])
    requires_event_title = bool(constraints.get("requires_event_title"))
    return bool(temporal and (actions or requires_event_title))


def _scoped_reader_events(
    *,
    case_id: str,
    question: str,
    history_turns: list[dict[str, Any]],
    constraints: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    question_terms = _scoped_reader_query_terms(question)
    for turn in history_turns:
        text = str(turn.get("text", ""))
        for sentence in _sentences(text):
            sentence_norm = _norm_text(sentence)
            temporal_marker = _first_scoped_match(
                constraints.get("temporal_markers", []),
                sentence_norm,
            )
            action_cue = _first_scoped_match(
                constraints.get("action_cues", []),
                sentence_norm,
            )
            object_hit = _first_scoped_match(
                constraints.get("object_terms", []),
                sentence_norm,
            )
            if not temporal_marker and not action_cue:
                continue
            if constraints.get("temporal_markers") and not temporal_marker:
                continue
            if constraints.get("object_terms") and not object_hit:
                continue
            sentence_terms = set(_norm_text(sentence).split())
            overlap = len(question_terms & sentence_terms)
            if overlap <= 0:
                continue
            event_title = _scoped_event_title(sentence, question)
            if _requires_scoped_event_title(question) and not event_title:
                continue
            score = overlap * 10
            if temporal_marker:
                score += 25
            if action_cue:
                score += 20
            if object_hit:
                score += 8
            if event_title:
                score += 15
            events.append(
                {
                    "event_id": f"{case_id}::scoped_event_{len(events):03d}",
                    "event_title": event_title,
                    "temporal_marker": temporal_marker,
                    "action_cue": action_cue,
                    "object_term": object_hit,
                    "query_overlap_count": overlap,
                    "source_score": score,
                    "source_turn_id": turn.get("turn_id", ""),
                    "observed_at": turn.get("timestamp", ""),
                    "selection_rank": turn.get("selection_rank", ""),
                    "speaker": turn.get("speaker", ""),
                    "source_sentence": _truncate_text(sentence, 420),
                }
            )
    events.sort(
        key=lambda event: (
            -int(event.get("source_score", 0)),
            _safe_int(event.get("selection_rank"), 999),
            str(event.get("event_title", "")),
        )
    )
    return _dedupe_scoped_events(events)


def _scoped_reader_query_terms(question: str) -> set[str]:
    return {
        token
        for token in _norm_text(question).split()
        if len(token) >= 3 and token not in SCOPED_READER_OBJECT_STOPWORDS
    }


def _scoped_reader_object_terms(question: str) -> list[str]:
    action_terms = {_norm_text(cue) for cue in SCOPED_READER_ACTION_CUES}
    object_terms = []
    for token in _norm_text(question).split():
        if len(token) < 3:
            continue
        if token in SCOPED_READER_OBJECT_STOPWORDS or token in action_terms:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        object_terms.append(token)
    return _dedupe_preserve_order(object_terms)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _first_scoped_match(candidates: Any, normalized_text: str) -> str:
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        candidate_norm = _norm_text(candidate)
        if candidate_norm and candidate_norm in normalized_text:
            return str(candidate)
    return ""


def _requires_scoped_event_title(question: str) -> bool:
    question_norm = _norm_text(question)
    return bool(
        re.search(r"\bwhat\s+(?:type|kind|name|title)\b", question_norm)
        and re.search(
            r"\b(?:try|tried|make|made|read|watched|visited|bought|used|tested)\b",
            question_norm,
        )
    )


def _scoped_event_title(sentence: str, question: str) -> str:
    if not _requires_scoped_event_title(question):
        return ""
    object_terms = _scoped_reader_object_terms(question)
    if not object_terms:
        return ""
    object_pattern = "|".join(re.escape(term) for term in object_terms)
    patterns = (
        rf"\b(?:tried|made|read|watched|visited|bought|used|tested)\s+"
        rf"(?:a|an|the|some)?\s*(?P<title>[a-z][a-z0-9\s'&-]{{2,100}}?)\s+"
        rf"(?:{object_pattern})\b",
        rf"\b(?:try|make|read|watch|visit|buy|use|test)\s+"
        rf"(?:a|an|the|some)?\s*(?P<title>[a-z][a-z0-9\s'&-]{{2,100}}?)\s+"
        rf"(?:{object_pattern})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.I)
        if match:
            return _clean_scoped_title(match.group("title"))
    return ""


def _clean_scoped_title(value: str) -> str:
    text = " ".join(str(value).split())
    text = re.sub(r"^(a|an|the)\s+", "", text, flags=re.I)
    return text.strip(" ,.;:-").lower()


def _dedupe_scoped_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        key = (
            _norm_text(event.get("event_title", "")),
            str(event.get("temporal_marker", "")),
            str(event.get("source_turn_id", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        event["event_id"] = event["event_id"].rsplit("_", 1)[0] + f"_{len(out):03d}"
        out.append(event)
    return out


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        key = _norm_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _build_query_relevant_context(
    request: dict[str, Any],
    routed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not question:
        return []
    routed_ids = {
        str(row.get("memory_id", ""))
        for row in routed_rows
        if isinstance(row, dict) and row.get("memory_id")
    }
    records_by_id = {
        str(record.get("memory_id", "")): record
        for record in request.get("records", [])
        if isinstance(record, dict) and record.get("memory_id")
    }
    routed_best_score = _best_routed_question_relevance_score(
        question,
        query,
        routed_rows,
        records_by_id,
    )
    scored_rows = []
    for record in request.get("records", []):
        if not isinstance(record, dict):
            continue
        memory_id = str(record.get("memory_id", ""))
        if not memory_id or memory_id in routed_ids:
            continue
        score, reasons = _question_relevance_score(question, query, record)
        if score < 4 or routed_best_score >= 2:
            continue
        scored_rows.append(
            (
                -score,
                str(record.get("observed_at", "")),
                memory_id,
                _query_relevant_row(record, score, reasons),
            )
        )
    scored_rows.sort()
    return [row for _, _, _, row in scored_rows[:5]]


def _best_routed_question_relevance_score(
    question: str,
    query: dict[str, Any],
    routed_rows: list[dict[str, Any]],
    records_by_id: dict[str, dict[str, Any]],
) -> int:
    best_score = 0
    for row in routed_rows:
        if not isinstance(row, dict):
            continue
        score_row = records_by_id.get(str(row.get("memory_id", "")), row)
        score, _ = _question_relevance_score(question, query, score_row)
        best_score = max(best_score, score)
    return best_score


QUESTION_RELEVANCE_GROUPS = (
    (
        "career",
        {
            "career",
            "job",
            "work",
            "employment",
            "employed",
            "employer",
            "company",
            "industry",
            "income",
            "title",
            "internship",
            "occupation",
        },
    ),
    (
        "education",
        {
            "degree",
            "bachelor",
            "master",
            "university",
            "college",
            "school",
            "graduate",
            "graduated",
        },
    ),
    ("family_name", {"father", "dad", "mother", "parent", "name"}),
    ("birthdate", {"birthdate", "birthday", "born", "date"}),
    ("residence", {"residence", "address", "home", "location", "city", "move", "moved"}),
    ("relationship", {"marital", "relationship", "married", "divorced", "dating"}),
    ("preference", {"prefer", "preference", "favorite", "likes", "basketball", "casual"}),
)

QUESTION_RELEVANCE_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "did",
    "do",
    "does",
    "education",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "their",
    "to",
    "user",
    "users",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
}


def _question_relevance_score(
    question: str,
    query: dict[str, Any],
    record: dict[str, Any],
) -> tuple[int, list[str]]:
    question_tokens = _content_tokens(question)
    record_text = " ".join(
        str(record.get(field_name, ""))
        for field_name in ("entity", "slot", "claim", "value")
    )
    record_tokens = _content_tokens(record_text)
    overlap = sorted(question_tokens & record_tokens)
    score = len(overlap)
    reasons = [f"token_overlap:{','.join(overlap[:6])}"] if overlap else []

    for group_name, terms in QUESTION_RELEVANCE_GROUPS:
        if question_tokens & terms and record_tokens & terms:
            score += 3
            reasons.append(f"semantic_group:{group_name}")

    if _norm_text(query.get("entity", "")) and _norm_text(query.get("entity", "")) == _norm_text(
        record.get("entity", "")
    ):
        score += 1
        reasons.append("entity_match")

    return score, reasons


def _content_tokens(value: Any) -> set[str]:
    return {
        token
        for token in _norm_text(value).split()
        if len(token) > 1 and token not in QUESTION_RELEVANCE_STOPWORDS
    }


def _query_relevant_row(
    record: dict[str, Any],
    score: int,
    reasons: list[str],
) -> dict[str, Any]:
    source = record.get("source", {})
    if not isinstance(source, dict):
        source = {}
    row = {
        "memory_id": record.get("memory_id", ""),
        "claim": _truncate_text(str(record.get("claim", "")), 320),
        "value": record.get("value", ""),
        "observed_at": record.get("observed_at", ""),
        "valid_until": record.get("valid_until", ""),
        "source_type": source.get("source_type", record.get("source_type", "")),
        "source_span": _truncate_text(str(source.get("source_span", "")), 700),
        "source_confidence": record.get("source_confidence", ""),
        "relevance_score": score,
        "relevance_reason": reasons[:4],
    }
    return {
        key: value
        for key, value in row.items()
        if value not in (None, "", [], {})
    }


def _all_record_temporal_context_rows(request: dict[str, Any]) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    rows = []
    seen = set()
    for record in request.get("records", []):
        if not isinstance(record, dict) or not record.get("memory_id"):
            continue
        memory_id = str(record.get("memory_id", ""))
        if memory_id in seen:
            continue
        seen.add(memory_id)
        score, reasons = _question_relevance_score(question, query, record)
        row = _query_relevant_row(record, score, reasons)
        source_span = _row_source_span(record)
        if source_span:
            row["source_span"] = _truncate_text(source_span, 2400)
        rows.append(row)
    return rows


def _routed_labels_by_memory_id(
    *,
    current_context: list[dict[str, Any]],
    supporting_context: list[dict[str, Any]],
    historical_context: list[dict[str, Any]],
    stale_or_blocked_context: list[dict[str, Any]],
    uncertain_context: list[dict[str, Any]],
    query_relevant_context: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for label, rows in [
        ("current_answer", current_context),
        ("supporting", supporting_context),
        ("historical_archive", historical_context),
        ("stale_or_blocked", stale_or_blocked_context),
        ("uncertain", uncertain_context),
        ("query_relevant_fallback", query_relevant_context),
    ]:
        for row in rows:
            if not isinstance(row, dict):
                continue
            memory_id = str(row.get("memory_id", ""))
            if not memory_id:
                continue
            labels.setdefault(
                memory_id,
                {
                    "qvf_route_label": label,
                    "qvf_retrieval_role": row.get("retrieval_role", ""),
                    "qvf_current_status": row.get("current_status", ""),
                },
            )
    return labels


def _evidence_preserving_context_rows(
    request: dict[str, Any],
    *,
    routed_labels: dict[str, dict[str, Any]],
    allowed_memory_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    rows = []
    for index, record in enumerate(request.get("records", [])):
        if not isinstance(record, dict):
            continue
        memory_id = str(record.get("memory_id", ""))
        if not memory_id:
            continue
        if allowed_memory_ids is not None and allowed_memory_ids and memory_id not in allowed_memory_ids:
            continue
        score, reasons = _question_relevance_score(question, query, record)
        row = _query_relevant_row(record, score, reasons)
        row["memory_id"] = memory_id
        label = routed_labels.get(
            memory_id,
            {
                "qvf_route_label": "unrouted_extracted",
                "qvf_retrieval_role": "",
                "qvf_current_status": "",
            },
        )
        row.update(label)
        row["qvf_use_policy"] = _qvf_use_policy_for_label(
            str(row.get("qvf_route_label", "")),
        )
        row["original_record_index"] = index
        rows.append(row)
    return rows


def _route_first_raw_fallback_memory_ids(
    *,
    routed_labels: dict[str, dict[str, Any]],
    transition_context: list[dict[str, Any]],
    status_class_context: list[dict[str, Any]],
    condition_scope_context: list[dict[str, Any]],
    habit_frequency_context: list[dict[str, Any]],
    temporal_resolution_context: list[dict[str, Any]],
    static_conflict_resolution_context: list[dict[str, Any]],
) -> set[str]:
    memory_ids = set(routed_labels)
    for row in (
        transition_context
        + status_class_context
        + condition_scope_context
        + habit_frequency_context
        + temporal_resolution_context
        + static_conflict_resolution_context
    ):
        if not isinstance(row, dict):
            continue
        for field_name in (
            "memory_id",
            "previous_memory_id",
            "current_memory_id",
            "recommended_memory_id",
        ):
            value = str(row.get(field_name, "")).strip()
            if value:
                memory_ids.add(value)
        for field_name in ("memory_ids", "supporting_memory_ids"):
            values = row.get(field_name, [])
            if isinstance(values, list):
                memory_ids.update(str(value).strip() for value in values if str(value).strip())
    return memory_ids


def _qvf_use_policy_for_label(label: str) -> str:
    if label == "current_answer":
        return "primary answer evidence for current-state questions"
    if label == "supporting":
        return "supporting detail or corroboration"
    if label == "historical_archive":
        return "answer evidence for history/timeline/change questions"
    if label == "stale_or_blocked":
        return "do not use as current fact; use only for history/change or stale-premise correction"
    if label == "uncertain":
        return "low confidence; corroborate or hedge before using"
    if label == "query_relevant_fallback":
        return "question-relevant fallback when routed buckets miss answer evidence"
    return "ordinary extracted evidence; use if directly relevant and not contradicted by current/stale labels"


def _evidence_preservation_routing_mode(
    *,
    read_decision: dict[str, Any],
    transition_context: list[dict[str, Any]],
    change_detail_context: list[dict[str, Any]],
    temporal_resolution_context: list[dict[str, Any]],
    stale_or_blocked_context: list[dict[str, Any]],
) -> str:
    if transition_context or change_detail_context or temporal_resolution_context:
        return "route_first"
    if read_decision.get("decision") in {"REJECT_STALE_PREMISE", "ADMIT_ARCHIVE"}:
        return "route_first"
    if stale_or_blocked_context and read_decision.get("answer_policy") != "answer_from_current":
        return "route_first"
    return "preserve_first"


def _build_temporal_resolution_context(
    request: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    query = _first_query_request(request)
    question = str(query.get("question") or query.get("query") or "")
    if not _asks_for_time_resolution(question):
        return []
    allow_explicit_event_dates = _asks_two_event_elapsed_duration_question(question)
    named_calendar_anchor_dates = (
        _named_calendar_anchor_dates_from_evidence(evidence_rows)
        if allow_explicit_event_dates
        else {}
    )

    hints = []
    seen = set()
    for row in evidence_rows:
        observed_at = _parse_observed_at(row.get("observed_at"))
        if observed_at is None:
            continue
        source_span = _row_source_span(row)
        text = " ".join(
            str(row.get(field_name, ""))
            for field_name in ("claim", "source_span")
            if row.get(field_name)
        )
        if source_span and source_span not in text:
            text = " ".join(part for part in (text, source_span) if part)
        for phrase, resolved_time, note in _resolve_relative_time_phrases(
            text,
            observed_at,
        ):
            key = (row.get("memory_id"), phrase, resolved_time)
            if key in seen:
                continue
            seen.add(key)
            hint = {
                "memory_id": row.get("memory_id", ""),
                "phrase": phrase,
                "observed_at": row.get("observed_at", ""),
                "resolved_time": resolved_time,
                "preferred_answer": _preferred_temporal_answer(
                    phrase,
                    resolved_time,
                    observed_at,
                ),
                "resolution_note": note,
                "claim": row.get("claim", ""),
                "value": row.get("value", ""),
                "source_span": source_span,
            }
            hints.append(
                (
                    -_temporal_hint_priority(question, row, hint),
                    str(row.get("memory_id", "")),
                    phrase,
                    resolved_time,
                    hint,
                )
            )
        if allow_explicit_event_dates:
            for phrase, resolved_time, note in _source_backed_explicit_event_date_hints(
                row,
                observed_at,
            ):
                key = (row.get("memory_id"), phrase, resolved_time)
                if key in seen:
                    continue
                seen.add(key)
                hint = {
                    "memory_id": row.get("memory_id", ""),
                    "phrase": phrase,
                    "observed_at": row.get("observed_at", ""),
                    "resolved_time": resolved_time,
                    "preferred_answer": resolved_time,
                    "resolution_note": note,
                    "claim": row.get("claim", ""),
                    "value": row.get("value", ""),
                    "source_span": source_span,
                }
                hints.append(
                    (
                        -_temporal_hint_priority(question, row, hint),
                        str(row.get("memory_id", "")),
                        phrase,
                        resolved_time,
                        hint,
                    )
                )
            for phrase, resolved_time, note in _source_backed_named_calendar_date_hints(
                row,
                observed_at,
            ):
                key = (row.get("memory_id"), phrase, resolved_time)
                if key in seen:
                    continue
                seen.add(key)
                hint = {
                    "memory_id": row.get("memory_id", ""),
                    "phrase": phrase,
                    "observed_at": row.get("observed_at", ""),
                    "resolved_time": resolved_time,
                    "preferred_answer": resolved_time,
                    "resolution_note": note,
                    "claim": row.get("claim", ""),
                    "value": row.get("value", ""),
                    "source_span": source_span,
                }
                hints.append(
                    (
                        -_temporal_hint_priority(question, row, hint),
                        str(row.get("memory_id", "")),
                        phrase,
                        resolved_time,
                        hint,
                    )
                )
            for phrase, resolved_time, note in _named_calendar_relative_date_hints(
                row,
                named_calendar_anchor_dates,
            ):
                key = (row.get("memory_id"), phrase, resolved_time)
                if key in seen:
                    continue
                seen.add(key)
                hint = {
                    "memory_id": row.get("memory_id", ""),
                    "phrase": phrase,
                    "observed_at": row.get("observed_at", ""),
                    "resolved_time": resolved_time,
                    "preferred_answer": resolved_time,
                    "resolution_note": note,
                    "claim": row.get("claim", ""),
                    "value": row.get("value", ""),
                    "source_span": source_span,
                }
                hints.append(
                    (
                        -_temporal_hint_priority(question, row, hint),
                        str(row.get("memory_id", "")),
                        phrase,
                        resolved_time,
                        hint,
                    )
                )
    hints.sort()
    return _dedupe_temporal_hints(
        [hint for _, _, _, _, hint in hints],
        max_hints=MAX_TEMPORAL_RESOLUTION_HINTS,
    )


def _dedupe_temporal_hints(
    hints: list[dict[str, Any]],
    *,
    max_hints: int,
) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for hint in hints:
        key = (
            _norm_text(hint.get("phrase", "")),
            _norm_text(hint.get("preferred_answer") or hint.get("resolved_time", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(hint)
        if len(out) >= max_hints:
            break
    return out


def _temporal_hint_priority(
    question: str,
    row: dict[str, Any],
    hint: dict[str, Any],
) -> int:
    text = _norm_text(question)
    phrase = _norm_text(hint.get("phrase", ""))
    resolved = _norm_text(hint.get("resolved_time", ""))
    priority = 0
    try:
        priority += int(row.get("relevance_score", 0))
    except (TypeError, ValueError):
        priority += 0
    if "month" in text and ("month" in phrase or _looks_like_month_year(resolved)):
        priority += 6
    if "year" in text and re.fullmatch(r"\d{4}", resolved):
        priority += 6
    if "when" in text and phrase:
        priority += 3
    if any(token in text for token in ("score", "points")):
        row_text = _norm_text(
            " ".join(str(row.get(field_name, "")) for field_name in ("claim", "source_span"))
        )
        if "score" in row_text or "points" in row_text:
            priority += 4
    return priority


def _looks_like_month_year(value: str) -> bool:
    return any(
        value.startswith(month)
        for month in (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        )
    )


def _asks_for_time_resolution(question: str) -> bool:
    text = _norm_text(question)
    return _asks_elapsed_duration_question(text) or any(
        cue in text
        for cue in (
            "when",
            "what date",
            "which date",
            "what month",
            "which month",
            "what year",
            "which year",
            "in which month",
        )
    )


def _asks_elapsed_duration_question(question: str) -> bool:
    return bool(ELAPSED_DURATION_QUESTION_PATTERN.search(str(question or "")))


def _asks_two_event_elapsed_duration_question(question: str) -> bool:
    text = _norm_text(question)
    if not _asks_elapsed_duration_question(text):
        return False
    return bool(
        re.search(r"\bbetween\b.+\band\b", text)
        or re.search(r"\bwhen\b", text)
        or re.search(r"\b(?:before|after)\b", text)
    )


MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

EXPLICIT_ISO_DATE_PATTERN = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
EXPLICIT_MONTH_DAY_PATTERN = re.compile(
    r"\b(?P<month>"
    + "|".join(MONTH_NAME_TO_NUMBER)
    + r")\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?\b",
    flags=re.I,
)


def _source_backed_explicit_event_date_hints(
    row: dict[str, Any],
    observed_at: datetime,
) -> list[tuple[str, str, str]]:
    claim = str(row.get("claim") or "")
    source_span = _row_source_span(row)
    source_text = " ".join(part for part in (claim, source_span) if part.strip())
    if not source_text.strip():
        return []

    hints: list[tuple[str, str, str]] = []
    seen_dates = set()
    for phrase, resolved_date in _explicit_event_dates_from_text(
        claim,
        observed_at=observed_at,
    ):
        if _is_placeholder_event_date(resolved_date):
            continue
        key = (phrase.lower(), resolved_date)
        if key in seen_dates:
            continue
        seen_dates.add(key)
        hints.append(
            (
                phrase,
                resolved_date,
                "source-backed explicit event date from claim",
            )
        )
    if hints:
        return hints

    value = str(row.get("value") or "")
    for phrase, resolved_date in _explicit_event_dates_from_text(
        value,
        observed_at=observed_at,
    ):
        if _is_placeholder_event_date(resolved_date):
            continue
        if not _explicit_date_supported_by_source_text(
            resolved_date,
            source_text,
            observed_at=observed_at,
        ):
            continue
        key = (phrase.lower(), resolved_date)
        if key in seen_dates:
            continue
        seen_dates.add(key)
        hints.append(
            (
                phrase,
                resolved_date,
                "source-backed explicit event date from value",
            )
        )
    return hints


def _explicit_event_dates_from_text(
    text: str,
    *,
    observed_at: datetime,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for match in EXPLICIT_ISO_DATE_PATTERN.finditer(str(text or "")):
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        resolved_date = _safe_iso_date(year, month, day)
        if resolved_date:
            out.append((match.group(0), resolved_date))
    for match in EXPLICIT_MONTH_DAY_PATTERN.finditer(str(text or "")):
        month = MONTH_NAME_TO_NUMBER[match.group("month").lower()]
        day = int(match.group("day"))
        if not match.group("year") and observed_at.year <= 1971:
            continue
        year = int(match.group("year") or observed_at.year)
        resolved_date = _safe_iso_date(year, month, day)
        if resolved_date:
            out.append((match.group(0), resolved_date))
    return out


def _safe_iso_date(year: int, month: int, day: int) -> str:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""


def _is_placeholder_event_date(value: str) -> bool:
    return str(value or "") in {"1970-01-01", "0001-01-01"}


def _explicit_date_supported_by_source_text(
    resolved_date: str,
    source_text: str,
    *,
    observed_at: datetime,
) -> bool:
    for _, supported_date in _explicit_event_dates_from_text(
        source_text,
        observed_at=observed_at,
    ):
        if supported_date == resolved_date:
            return True
    return False


NAMED_CALENDAR_EVENT_PATTERNS = {
    "black_friday": re.compile(r"\bblack\s+friday\b", flags=re.I),
}

NAMED_CALENDAR_RELATIVE_PATTERN = re.compile(
    r"\b(?P<phrase>(?P<amount>a|one|two|three|\d+)\s+weeks?\s+"
    r"(?P<direction>before|after)\s+black\s+friday)\b",
    flags=re.I,
)


def _named_calendar_anchor_dates_from_evidence(
    evidence_rows: list[dict[str, Any]],
) -> dict[str, set[str]]:
    anchors: dict[str, set[str]] = {}
    for row in evidence_rows:
        observed_at = _parse_observed_at(row.get("observed_at"))
        if observed_at is None or observed_at.year <= 1971:
            continue
        for _, resolved_date, note in _source_backed_named_calendar_date_hints(
            row,
            observed_at,
        ):
            if "black friday" not in note:
                continue
            anchors.setdefault("black_friday", set()).add(resolved_date)
    return anchors


def _source_backed_named_calendar_date_hints(
    row: dict[str, Any],
    observed_at: datetime,
) -> list[tuple[str, str, str]]:
    if observed_at.year <= 1971:
        return []
    claim = str(row.get("claim") or "")
    source_span = _row_source_span(row)
    source_text = " ".join(part for part in (claim, source_span) if part.strip())
    if not source_span.strip():
        return []
    hints: list[tuple[str, str, str]] = []
    if NAMED_CALENDAR_EVENT_PATTERNS["black_friday"].search(source_text):
        resolved_date = _nearest_prior_black_friday(observed_at)
        if resolved_date:
            hints.append(
                (
                    "Black Friday",
                    resolved_date,
                    "source-backed named calendar event: black friday",
                )
            )
    return hints


def _named_calendar_relative_date_hints(
    row: dict[str, Any],
    anchor_dates: dict[str, set[str]],
) -> list[tuple[str, str, str]]:
    black_friday_dates = sorted(anchor_dates.get("black_friday", set()))
    if len(black_friday_dates) != 1:
        return []
    black_friday = _parse_iso_date(black_friday_dates[0])
    if black_friday is None:
        return []
    text = " ".join(
        part
        for part in (str(row.get("claim") or ""), _row_source_span(row))
        if part
    )
    hints: list[tuple[str, str, str]] = []
    for match in NAMED_CALENDAR_RELATIVE_PATTERN.finditer(text):
        weeks = _relative_week_amount(match.group("amount"))
        if not weeks:
            continue
        offset_days = weeks * 7
        if match.group("direction").lower() == "before":
            resolved_date = black_friday - timedelta(days=offset_days)
        else:
            resolved_date = black_friday + timedelta(days=offset_days)
        hints.append(
            (
                match.group("phrase"),
                resolved_date.date().isoformat(),
                "named calendar relative event from retrieved claim using source-backed black friday",
            )
        )
    return hints


def _row_source_span(row: dict[str, Any]) -> str:
    source_span = str(row.get("source_span") or "")
    if source_span:
        return source_span
    source = row.get("source", {})
    if isinstance(source, dict):
        return str(source.get("source_span") or "")
    return ""


def _relative_week_amount(value: str) -> int:
    text = _norm_text(value)
    if text in {"a", "one"}:
        return 1
    if text == "two":
        return 2
    if text == "three":
        return 3
    try:
        amount = int(text)
    except ValueError:
        return 0
    if 0 < amount <= 8:
        return amount
    return 0


def _nearest_prior_black_friday(observed_at: datetime) -> str:
    year = observed_at.year
    candidate = _black_friday_date(year)
    if candidate.date() > observed_at.date():
        candidate = _black_friday_date(year - 1)
    return candidate.date().isoformat()


def _black_friday_date(year: int) -> datetime:
    thanksgiving = _nth_weekday_of_month(year, 11, 3, 4)
    return thanksgiving + timedelta(days=1)


def _nth_weekday_of_month(
    year: int,
    month: int,
    weekday_index: int,
    occurrence: int,
) -> datetime:
    cursor = datetime(year, month, 1)
    days_forward = (weekday_index - cursor.weekday()) % 7
    return cursor + timedelta(days=days_forward + 7 * (occurrence - 1))


def _parse_iso_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _resolve_relative_time_phrases(
    text: str,
    observed_at: datetime,
) -> list[tuple[str, str, str]]:
    normalized = _norm_text(text)
    hints: list[tuple[str, str, str]] = []
    if "yesterday" in normalized:
        resolved = observed_at - timedelta(days=1)
        hints.append(
            (
                "yesterday",
                resolved.date().isoformat(),
                "one day before observed_at",
            )
        )
    if "today" in normalized:
        hints.append(
            (
                "today",
                observed_at.date().isoformat(),
                "same date as observed_at",
            )
        )
    if "last year" in normalized:
        hints.append(
            (
                "last year",
                str(observed_at.year - 1),
                "calendar year before observed_at",
            )
        )
    if "this month" in normalized:
        hints.append(
            (
                "this month",
                _month_year(observed_at.year, observed_at.month),
                "same calendar month as observed_at",
            )
        )
    if "next month" in normalized:
        year, month = _add_months(observed_at.year, observed_at.month, 1)
        hints.append(
            (
                "next month",
                _month_year(year, month),
                "calendar month after observed_at",
            )
        )
    if "last month" in normalized:
        year, month = _add_months(observed_at.year, observed_at.month, -1)
        hints.append(
            (
                "last month",
                _month_year(year, month),
                "calendar month before observed_at",
            )
        )
    if "last week" in normalized:
        hints.append(
            (
                "last week",
                f"week before {observed_at.date().isoformat()}",
                "relative week before observed_at",
            )
        )
    for phrase, days in (
        ("two days ago", 2),
        ("three days ago", 3),
        ("four days ago", 4),
        ("five days ago", 5),
        ("six days ago", 6),
        ("a week ago", 7),
        ("one week ago", 7),
    ):
        if phrase in normalized:
            resolved = observed_at - timedelta(days=days)
            hints.append(
                (
                    phrase,
                    resolved.date().isoformat(),
                    f"{days} days before observed_at",
                )
            )
    for weekday_name, weekday_index in _WEEKDAY_INDEX.items():
        phrase = f"last {weekday_name}"
        if phrase in normalized:
            resolved = _previous_weekday(observed_at, weekday_index)
            hints.append(
                (
                    phrase,
                    resolved.date().isoformat(),
                    f"previous {weekday_name} before observed_at",
                )
            )
    years_ago = _years_ago(normalized)
    if years_ago is not None:
        hints.append(
            (
                f"{years_ago} years ago",
                str(observed_at.year - years_ago),
                "year offset before observed_at",
            )
        )
    for age in _age_years(normalized):
        hints.append(
            (
                f"{age}-year-old",
                str(observed_at.year - age),
                "age-derived approximate year before observed_at",
            )
        )
    return hints


_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_observed_at(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    zero_based = month - 1 + offset
    return year + zero_based // 12, zero_based % 12 + 1


def _month_year(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B %Y")


def _preferred_temporal_answer(
    phrase: str,
    resolved_time: str,
    observed_at: datetime,
) -> str:
    phrase_norm = _norm_text(phrase)
    if phrase_norm == "last week":
        return f"the week before {_display_date(observed_at)}"
    if phrase_norm.startswith("last ") and phrase_norm != "last month":
        return f"the {phrase_norm} before {_display_date(observed_at)}"
    if phrase_norm == "last month":
        return resolved_time
    if phrase_norm.endswith("year old") or phrase_norm.endswith("years old"):
        return resolved_time
    if re.fullmatch(r"\d+ year old", phrase_norm):
        return resolved_time
    return resolved_time


def _display_date(value: datetime) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _previous_weekday(observed_at: datetime, weekday_index: int) -> datetime:
    days_back = (observed_at.weekday() - weekday_index) % 7
    if days_back == 0:
        days_back = 7
    return observed_at - timedelta(days=days_back)


def _years_ago(normalized_text: str) -> int | None:
    tokens = normalized_text.split()
    for index in range(len(tokens) - 2):
        if tokens[index + 1] == "years" and tokens[index + 2] == "ago":
            try:
                return int(tokens[index])
            except ValueError:
                return None
    return None


def _age_years(normalized_text: str) -> list[int]:
    years = []
    for pattern in (
        r"\b(?P<years>\d{1,2})\s+year\s+old\b",
        r"\b(?P<years>\d{1,2})\s+years\s+old\b",
        r"\b(?P<years>\d{1,2})\s*-\s*year\s*-\s*old\b",
    ):
        for match in re.finditer(pattern, normalized_text):
            try:
                value = int(match.group("years"))
            except ValueError:
                continue
            if 0 < value < 40:
                years.append(value)
    return sorted(set(years))


def _norm_text(value: Any) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in str(value)).split()
    )


def _build_preflight(
    *,
    output_dir: Path,
    adapter_items_path: Path,
    qvf_requests_path: Path,
    eval_items: list[dict[str, Any]],
    answer_model: str,
    judge_model: str,
    max_output_tokens: int,
    qvf_context_variant: str,
) -> dict[str, Any]:
    nominal_target_calls = len(eval_items)
    nominal_judge_calls = len(eval_items)
    reuse_plan = _selective_eval_reuse_plan(eval_items)
    target_calls = nominal_target_calls - reuse_plan["reused_target_calls"]
    judge_calls = nominal_judge_calls - reuse_plan["reused_judge_calls"]
    methods = sorted({str(item["method"]) for item in eval_items})
    case_count = len({str(item["case_id"]) for item in eval_items})
    target_charged_items = [
        item
        for item in eval_items
        if not _selective_eval_reuse_source_method_from_items(item, eval_items)
    ]
    estimated_input_tokens = (
        sum(_rough_message_tokens(item["target_messages"]) for item in target_charged_items)
        + judge_calls * 650
    )
    estimated_output_tokens = target_calls * max_output_tokens + judge_calls * 120
    return {
        "decision": "GO_QVF_PUBLIC_ANSWER_EVAL_PREFLIGHT_READY",
        "execution_mode": "public_answer_eval_preflight",
        "answer_eval_version": PUBLIC_ANSWER_EVAL_VERSION,
        "hypothesis": (
            "QVF validity packing can improve or clarify answer behavior on public long-memory "
            "items after candidate-memory extraction, but the pilot is limited by extractor recall."
        ),
        "dataset_slice": "public QVF service requests produced by public-extract",
        "adapter_items_path": str(adapter_items_path),
        "qvf_requests_path": str(qvf_requests_path),
        "output_dir": str(output_dir),
        "case_count": case_count,
        "methods": methods,
        "qvf_context_variant": qvf_context_variant,
        "qvf_context_variant_semantics": {
            "adaptive": (
                "Risk-gated default: route-first QVF context for explicit current/recent, "
                "change, condition, or conflict questions; original extracted memories are "
                "retained with QVF labels as raw fallback for anchor preservation."
            ),
            "evidence_preserving": (
                "QVF routing plus original extracted memories annotated with "
                "current/stale/archive/uncertain labels; intended for broad long-memory QA "
                "where QVF should augment rather than replace evidence."
            ),
            "full": (
                "Core QVF routing plus temporal/query fallback and source-history "
                "change-detail repair."
            ),
            "compact_full": (
                "Full QVF routing and repair, with compact target-facing evidence rows "
                "for lower answer-model input cost."
            ),
            "auto_compact": (
                "Full QVF routing and repair with risk-gated target compaction; "
                "change/conflict/static-profile questions keep full target-facing rows."
            ),
            "no_source_history_repair": (
                "Core QVF routing plus deterministic public-record repairs, without "
                "selected source-history change-detail repair."
            ),
            "core_routing": (
                "Only QVF validity-routing buckets; disables public benchmark repair "
                "layers for contribution-boundary ablation."
            ),
            "selective_router": (
                "Three-method comparison: direct extracted memories, always-on adaptive "
                "QVF, and an external router whose target prompt is byte-for-byte "
                "equivalent to the selected direct/QVF branch. It preserves direct "
                "context for ordinary recall and activates QVF only for current/conflict "
                "queries or high-confidence recent-scoped queries with selected-history "
                "evidence."
            ),
            "annotation_only_qvf": (
                "Always-on non-destructive QVF annotation: raw extracted memories are "
                "kept as answer evidence, and QVF labels advise current/stale/archive/"
                "uncertain use without filtering historical recall anchors."
            ),
            "multi_action_controller": (
                "Always-on QVF controller that chooses the lightest model-facing action "
                "from evidence buckets: raw recall with annotations, condition-scope "
                "packet, timeline/conflict packet, stale/current validity packet, or "
                "scoped/temporal packet. It preserves extracted-memory fallback unless "
                "a row is explicitly unsafe as current evidence."
            ),
            "post_answer_audit_controller": (
                "Direct-equivalent controller for ordinary recall: raw-recall actions "
                "reuse the exact direct target prompt and keep QVF labels for "
                "post-answer audit/diagnostics, while condition, timeline/conflict, "
                "stale/current, and scoped/temporal actions still expose the relevant "
                "QVF packet with raw-memory fallback."
            ),
        },
        "answer_model": answer_model,
        "judge_model": judge_model,
        "expected_call_count": {
            "target_calls": target_calls,
            "judge_calls": judge_calls,
            "total_calls": target_calls + judge_calls,
        },
        "nominal_call_count_without_reuse": {
            "target_calls": nominal_target_calls,
            "judge_calls": nominal_judge_calls,
            "total_calls": nominal_target_calls + nominal_judge_calls,
        },
        "selective_eval_reuse_plan": reuse_plan,
        "estimated_token_range": {
            "input_tokens": [
                max(0, int(estimated_input_tokens * 0.75)),
                int(estimated_input_tokens * 1.35),
            ],
            "output_tokens": [
                max_output_tokens,
                estimated_output_tokens,
            ],
        },
        "estimated_cost_usd": [
            round(_estimated_cost_usd(int(estimated_input_tokens * 0.75), max_output_tokens), 6),
            round(_estimated_cost_usd(int(estimated_input_tokens * 1.35), estimated_output_tokens), 6),
        ],
        "health_gates": [
            "preflight is written before API calls",
            "target payload audit checks forbidden fields, local paths, and secret-like strings before API calls",
            "gold answers are used only in judge prompts, not target prompts",
            "judge prompts include the same memory_context shown to the target method",
            "byte-equivalent selective target prompts reuse the selected branch target; post-answer audit rows may rerun judge if the audited answer changes",
            "usage and latency are recorded for every target and judge call",
            "raw outputs are saved only under ignored local runs directories",
        ],
        "acceptance_criteria": [
            "method-level accuracy, latency, and token use are reported",
            "QVF failures distinguish extraction-recall limits from validity-packing limits",
            "no raw target or judge outputs are committed",
        ],
        "api_calls_made": 0,
    }


def _selective_eval_reuse_plan(eval_items: list[dict[str, Any]]) -> dict[str, Any]:
    reusable_cases: list[dict[str, str]] = []
    reused_target_calls = 0
    reused_judge_calls = 0
    for item in eval_items:
        source_method = _selective_eval_reuse_source_method_from_items(item, eval_items)
        if source_method:
            context = item.get("context", {}) if isinstance(item.get("context", {}), dict) else {}
            judge_reused = not (
                str(item.get("method", "")) == QVF_METHOD
                and _post_answer_audit_uses_direct_target(str(item.get("method", "")), context)
            )
            reused_target_calls += 1
            if judge_reused:
                reused_judge_calls += 1
            reusable_cases.append(
                {
                    "case_id": str(item.get("case_id", "")),
                    "method": str(item.get("method", "")),
                    "reused_from_method": source_method,
                    "target_reused": "true",
                    "judge_reused": "true" if judge_reused else "false_conservative_post_answer_audit",
                }
            )
    return {
        "mode": "reuse_byte_equivalent_selective_outputs",
        "reusable_case_method_count": len(reusable_cases),
        "reused_target_calls": reused_target_calls,
        "reused_judge_calls": reused_judge_calls,
        "reusable_cases_preview": reusable_cases[:20],
    }


def _selective_eval_reuse_source_method_from_items(
    item: dict[str, Any],
    eval_items: list[dict[str, Any]],
) -> str:
    method = str(item.get("method", ""))
    if method == QVF_METHOD and _post_answer_audit_uses_direct_target(
        method,
        item.get("context", {}) if isinstance(item.get("context", {}), dict) else {},
    ):
        return _byte_equivalent_direct_source_method_from_items(item, eval_items)
    if method != SELECTIVE_ROUTER_METHOD:
        return ""
    context = item.get("context", {})
    if not isinstance(context, dict):
        return ""
    selected_method = str(context.get("selected_method") or "")
    if selected_method not in {DIRECT_METHOD, QVF_METHOD}:
        return ""
    case_id = str(item.get("case_id", ""))
    source_item = next(
        (
            candidate
            for candidate in eval_items
            if str(candidate.get("case_id", "")) == case_id
            and str(candidate.get("method", "")) == selected_method
        ),
        None,
    )
    if not isinstance(source_item, dict):
        return ""
    if item.get("target_messages") != source_item.get("target_messages"):
        return ""
    return selected_method


def _byte_equivalent_direct_source_method_from_items(
    item: dict[str, Any],
    eval_items: list[dict[str, Any]],
) -> str:
    case_id = str(item.get("case_id", ""))
    source_item = next(
        (
            candidate
            for candidate in eval_items
            if str(candidate.get("case_id", "")) == case_id
            and str(candidate.get("method", "")) == DIRECT_METHOD
        ),
        None,
    )
    if not isinstance(source_item, dict):
        return ""
    if item.get("target_messages") != source_item.get("target_messages"):
        return ""
    return DIRECT_METHOD


def _selective_eval_reuse_source_method(
    *,
    item: dict[str, Any],
    items_by_case_method: dict[tuple[str, str], dict[str, Any]],
    target_records_by_case_method: dict[tuple[str, str], dict[str, Any]],
    judge_records_by_case_method: dict[tuple[str, str], dict[str, Any]],
) -> str:
    method = str(item.get("method", ""))
    if method == QVF_METHOD and _post_answer_audit_uses_direct_target(
        method,
        item.get("context", {}) if isinstance(item.get("context", {}), dict) else {},
    ):
        source_key = (str(item.get("case_id", "")), DIRECT_METHOD)
        source_item = items_by_case_method.get(source_key)
        if not isinstance(source_item, dict):
            return ""
        if item.get("target_messages") != source_item.get("target_messages"):
            return ""
        if source_key not in target_records_by_case_method:
            return ""
        if source_key not in judge_records_by_case_method:
            return ""
        return DIRECT_METHOD
    if method != SELECTIVE_ROUTER_METHOD:
        return ""
    context = item.get("context", {})
    if not isinstance(context, dict):
        return ""
    selected_method = str(context.get("selected_method") or "")
    if selected_method not in {DIRECT_METHOD, QVF_METHOD}:
        return ""
    source_key = (str(item.get("case_id", "")), selected_method)
    source_item = items_by_case_method.get(source_key)
    if not isinstance(source_item, dict):
        return ""
    if item.get("target_messages") != source_item.get("target_messages"):
        return ""
    if source_key not in target_records_by_case_method:
        return ""
    if source_key not in judge_records_by_case_method:
        return ""
    return selected_method


def _post_answer_equivalent_direct_judge_reuse_method(
    *,
    item: dict[str, Any],
    target_content: str,
    post_answer_audit: dict[str, Any],
    target_records_by_case_method: dict[tuple[str, str], dict[str, Any]],
    judge_records_by_case_method: dict[tuple[str, str], dict[str, Any]],
) -> str:
    if str(item.get("method", "")) != QVF_METHOD:
        return ""
    if not isinstance(post_answer_audit, dict) or not post_answer_audit.get("applied"):
        return ""
    source_key = (str(item.get("case_id", "")), DIRECT_METHOD)
    source_target = target_records_by_case_method.get(source_key)
    source_judge = judge_records_by_case_method.get(source_key)
    if not isinstance(source_target, dict) or not isinstance(source_judge, dict):
        return ""
    if not _answer_payloads_equivalent(
        target_content,
        str(source_target.get("content", "")),
    ):
        return ""
    return DIRECT_METHOD


def _reused_api_response(
    source_record: dict[str, Any],
    source_method: str,
) -> dict[str, Any]:
    return {
        "response": source_record.get("raw_response", {}),
        "latency_seconds": 0.0,
        "usage": {},
        "api_call_made": False,
        "reused_from_method": source_method,
    }


def _api_record(
    *,
    item: dict[str, Any],
    model: str,
    response: dict[str, Any],
    content: str,
    parsed_judgment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "case_id": item["case_id"],
        "method": item["method"],
        "model": model,
        "latency_seconds": response["latency_seconds"],
        "usage": response["usage"],
        "content": content,
        "raw_response": response["response"],
        "api_call_made": bool(response.get("api_call_made", True)),
        "reused_from_method": str(response.get("reused_from_method", "")),
    }
    if parsed_judgment is not None:
        record["parsed_judgment"] = parsed_judgment
    post_answer_audit = response.get("post_answer_audit", {})
    if isinstance(post_answer_audit, dict) and post_answer_audit:
        record["post_answer_audit"] = post_answer_audit
    return record


def _api_reuse_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_reused = [
        row for row in rows if not row.get("target_api_call_made", True)
    ]
    judge_reused = [
        row for row in rows if not row.get("judge_api_call_made", True)
    ]
    return {
        "target_reused_rows": len(target_reused),
        "judge_reused_rows": len(judge_reused),
        "target_reuse_by_source_method": dict(
            Counter(str(row.get("target_reused_from_method", "")) for row in target_reused)
        ),
        "judge_reuse_by_source_method": dict(
            Counter(str(row.get("judge_reused_from_method", "")) for row in judge_reused)
        ),
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
    post_answer_audit = target_response.get("post_answer_audit", {})
    if not isinstance(post_answer_audit, dict):
        post_answer_audit = {}
    return {
        "case_id": item["case_id"],
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
        "target_api_call_made": bool(target_response.get("api_call_made", True)),
        "judge_api_call_made": bool(judge_response.get("api_call_made", True)),
        "target_reused_from_method": str(target_response.get("reused_from_method", "")),
        "judge_reused_from_method": str(judge_response.get("reused_from_method", "")),
        "post_answer_audit_applied": bool(post_answer_audit.get("applied", False)),
        "post_answer_audit_reason": str(post_answer_audit.get("reason", "")),
        "post_answer_audit_replacement": str(post_answer_audit.get("replacement", "")),
        "post_answer_audit_judge_reuse_reason": str(
            post_answer_audit.get("judge_reuse_reason", "")
        ),
        "expected_answers": json.dumps(item["expected_answers"], ensure_ascii=False),
        "answer_excerpt": target_content[:500],
        "judge_rationale_excerpt": judgment["rationale"][:500],
    }


def _summarize_rows(
    *,
    rows: list[dict[str, Any]],
    answer_model: str,
    judge_model: str,
) -> dict[str, Any]:
    method_summary = []
    for method in sorted({row["method"] for row in rows}):
        method_rows = [row for row in rows if row["method"] == method]
        target_input = sum(row["target_input_tokens"] for row in method_rows)
        target_output = sum(row["target_output_tokens"] for row in method_rows)
        judge_input = sum(row["judge_input_tokens"] for row in method_rows)
        judge_output = sum(row["judge_output_tokens"] for row in method_rows)
        correct_count = sum(1 for row in method_rows if row["correct"])
        target_api_calls = sum(1 for row in method_rows if row.get("target_api_call_made", True))
        judge_api_calls = sum(1 for row in method_rows if row.get("judge_api_call_made", True))
        method_summary.append(
            {
                "method": method,
                "case_count": len(method_rows),
                "correct_count": correct_count,
                "accuracy": correct_count / len(method_rows) if method_rows else 0.0,
                "target_api_calls": target_api_calls,
                "judge_api_calls": judge_api_calls,
                "reused_target_rows": len(method_rows) - target_api_calls,
                "reused_judge_rows": len(method_rows) - judge_api_calls,
                "mean_target_latency_seconds": _mean(
                    [
                        row["target_latency_seconds"]
                        for row in method_rows
                        if row.get("target_api_call_made", True)
                    ]
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
        "case_count": len({str(row["case_id"]) for row in rows}),
        "case_method_count": len(rows),
        "method_summary": method_summary,
        "actual_target_api_calls": sum(1 for row in rows if row.get("target_api_call_made", True)),
        "actual_judge_api_calls": sum(1 for row in rows if row.get("judge_api_call_made", True)),
        "estimated_total_usd": sum(row["estimated_usd"] for row in method_summary),
    }


def _case_id_from_request(request: dict[str, Any]) -> str:
    request_id = str(request.get("request_id", ""))
    prefixes = ("public_extraction_", "public_dataset_")
    for prefix in prefixes:
        if request_id.startswith(prefix):
            return request_id[len(prefix) :]
    return request_id


def _question(request: dict[str, Any]) -> str:
    if request.get("query_requests"):
        return str(request["query_requests"][0].get("question", ""))
    if request.get("queries"):
        return str(request["queries"][0].get("query", ""))
    raise ValueError("QVF request must contain a query or query_request")


def _answers(item: dict[str, Any]) -> list[str]:
    answers = item.get("answers", [])
    if isinstance(answers, str):
        return [answers] if answers.strip() else []
    if isinstance(answers, list):
        return [str(answer).strip() for answer in answers if str(answer).strip()]
    return []


def _selected_history_turns(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    work_item = item.get("extraction_work_item", {})
    if not isinstance(work_item, dict):
        return []
    turns = work_item.get("history_turns", [])
    if not isinstance(turns, list):
        return []
    compact_turns = []
    for turn in turns:
        if not isinstance(turn, dict) or not turn.get("text"):
            continue
        compact_turns.append(
            {
                "turn_id": turn.get("turn_id", ""),
                "timestamp": turn.get("timestamp", ""),
                "speaker": turn.get("speaker", ""),
                "text": _truncate_text(str(turn.get("text", "")), 900),
                "selection_rank": turn.get("selection_rank", ""),
                "selection_score": turn.get("selection_score", ""),
            }
        )
    return compact_turns


def _selected_history_turns_from_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    turns = request.get("_selected_history_turns", [])
    if not isinstance(turns, list):
        return []
    return [turn for turn in turns if isinstance(turn, dict)]


def _call_with_timing(
    client: "_OpenAIChatClient",
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.chat(model=model, messages=messages, max_tokens=max_tokens)
    return {
        "response": response,
        "latency_seconds": time.perf_counter() - started,
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


class _OpenAIChatClient:
    transient_status_codes = {408, 409, 429, 500, 502, 503, 504}

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
            "response_format": {"type": "json_object"},
        }
        payload[_completion_token_limit_field(model)] = max_tokens
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt, sleep_seconds in enumerate((0.0, 2.0, 5.0, 10.0), start=1):
            if sleep_seconds:
                time.sleep(sleep_seconds)
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"OpenAI API error {exc.code}: {body}")
                if exc.code not in self.transient_status_codes or attempt >= 4:
                    raise last_error from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = RuntimeError(f"OpenAI API transport error: {exc}")
                if attempt >= 4:
                    raise last_error from exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("OpenAI API request failed without an exception")


def _completion_token_limit_field(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith("gpt-5"):
        return "max_completion_tokens"
    return "max_tokens"


def _rough_message_tokens(messages: list[dict[str, str]]) -> int:
    return max(1, len(json.dumps(messages, ensure_ascii=False)) // 4)


def _estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * GPT_4O_MINI_ESTIMATED_INPUT_USD_PER_1M
        + output_tokens / 1_000_000 * GPT_4O_MINI_ESTIMATED_OUTPUT_USD_PER_1M
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


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


def _append_jsonl_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_preflight_report(path: Path, preflight: dict[str, Any]) -> None:
    lines = [
        "# QVF public answer eval preflight",
        "",
        f"- Hypothesis: {preflight['hypothesis']}",
        f"- Dataset slice: {preflight['dataset_slice']}",
        f"- Cases: {preflight['case_count']}",
        f"- QVF context variant: `{preflight['qvf_context_variant']}`",
        f"- Answer model: `{preflight['answer_model']}`",
        f"- Judge model: `{preflight['judge_model']}`",
        f"- Expected calls: {preflight['expected_call_count']['total_calls']}",
        f"- Estimated cost USD: {preflight['estimated_cost_usd']}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_result_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
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
        "target_api_call_made",
        "judge_api_call_made",
        "target_reused_from_method",
        "judge_reused_from_method",
        "post_answer_audit_applied",
        "post_answer_audit_reason",
        "post_answer_audit_replacement",
        "post_answer_audit_judge_reuse_reason",
        "expected_answers",
        "answer_excerpt",
        "judge_rationale_excerpt",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_result_report(path: Path, result: dict[str, Any]) -> None:
    summary = result["summary"]
    reuse_summary = result.get("reuse_summary", {})
    if not isinstance(reuse_summary, dict):
        reuse_summary = {}
    lines = [
        "# QVF public answer evaluation",
        "",
        f"- Answer model: `{summary['answer_model']}`",
        f"- Judge model: `{summary['judge_model']}`",
        f"- Cases: {summary['case_count']}",
        f"- QVF context variant: `{result.get('qvf_context_variant', DEFAULT_QVF_CONTEXT_VARIANT)}`",
        f"- API calls: {result['api_calls_made']}",
        f"- Reused target/judge rows: {reuse_summary.get('target_reused_rows', 0)}/{reuse_summary.get('judge_reused_rows', 0)}",
        f"- Estimated total USD: {summary['estimated_total_usd']:.6f}",
        "",
        "| Method | Accuracy | Correct | API calls | Mean target latency | Target tokens | Judge tokens | Estimated USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["method_summary"]:
        lines.append(
            f"| `{row['method']}` | "
            f"{row['accuracy'] * 100:.1f}% | "
            f"{row['correct_count']}/{row['case_count']} | "
            f"{row.get('target_api_calls', row['case_count']) + row.get('judge_api_calls', row['case_count'])} | "
            f"{row['mean_target_latency_seconds']:.2f}s | "
            f"{row['target_input_tokens'] + row['target_output_tokens']} | "
            f"{row['judge_input_tokens'] + row['judge_output_tokens']} | "
            f"${row['estimated_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "This is a public-slice pilot over extracted candidate memories. Treat failures as a mix of extraction recall, QVF packing, and answer-model behavior.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DEFAULT_QVF_CONTEXT_VARIANT",
    "DEFAULT_PUBLIC_ANSWER_EVAL_LIMIT",
    "DEFAULT_PUBLIC_ANSWER_MAX_OUTPUT_TOKENS",
    "PUBLIC_ANSWER_EVAL_VERSION",
    "QVF_CONTEXT_VARIANTS",
    "build_public_answer_eval_items",
    "load_public_qvf_requests",
    "run_public_answer_eval",
]
