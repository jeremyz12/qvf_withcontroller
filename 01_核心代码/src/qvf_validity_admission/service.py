"""Stateful no-API QVF validity-admission service interface."""

from typing import Any

from ._pipeline_core import (
    LOW_CONFIDENCE_THRESHOLD,
    load_qvf_service_request,
    validate_qvf_service_request_payload,
)
from .decisions import build_model_facing_sidecar_payloads
from .lifecycle import QVFMemoryPipeline


def build_model_facing_sidecar_payloads_from_response(
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract safe model-facing sidecar payloads from a QVF service response."""
    query_report = response.get("step_report", {}).get("query_report", {})
    query_results = query_report.get("query_results", [])
    return build_model_facing_sidecar_payloads(query_results)


def build_qvf_service_pipeline(request: dict[str, Any]) -> tuple[QVFMemoryPipeline, str]:
    """Build a configured QVF pipeline from a validated service request."""
    validated_request = validate_qvf_service_request_payload(request)
    config = validated_request["config"]
    pipeline_kwargs = {
        field_name: config[field_name]
        for field_name in [
            "max_current",
            "max_supporting",
            "max_stale",
            "max_excluded",
            "max_packet_chars",
            "include_validity_edges",
            "include_weak_gate_card",
        ]
        if field_name in config
    }
    if validated_request["state"] is not None:
        return QVFMemoryPipeline.from_state(validated_request["state"]), "service_state"
    if validated_request["memory_store"]:
        return (
            QVFMemoryPipeline.from_exported_records(
                validated_request["memory_store"],
                low_confidence_threshold=config.get(
                    "low_confidence_threshold",
                    LOW_CONFIDENCE_THRESHOLD,
                ),
                **pipeline_kwargs,
            ),
            "service_memory_store",
        )
    return (
        QVFMemoryPipeline.from_records(
            [],
            low_confidence_threshold=config.get(
                "low_confidence_threshold",
                LOW_CONFIDENCE_THRESHOLD,
            ),
            **pipeline_kwargs,
        ),
        "service_empty_store",
    )


def build_qvf_service_summary(
    request: dict[str, Any],
    step_report: dict[str, Any],
    *,
    input_mode: str,
    output_files: list[str],
) -> dict[str, Any]:
    """Build the deterministic no-API service summary."""
    query_summary = step_report.get("query_report", {}).get("summary", {})
    summary = {
        "decision": (
            "GO_QVF_SERVICE_PREVIEW_READY_NO_API"
            if request["preview"]
            else "GO_QVF_SERVICE_REQUEST_READY_NO_API"
        ),
        "execution_mode": "qvf_service_request_summary",
        "request_id": request["request_id"],
        "step_id": step_report["step_id"],
        "input_mode": input_mode,
        "preview": request["preview"],
        "records_submitted": step_report["records_submitted"],
        "admission_event_count": step_report["admission_event_count"],
        "query_count": step_report["query_count"],
        "query_mode": step_report["query_mode"],
        "read_decision_counts": query_summary.get("read_decision_counts", {}),
        "reader_answer_policy_counts": query_summary.get(
            "reader_answer_policy_counts",
            {},
        ),
        "store_integrity_before": step_report["store_integrity_before"],
        "store_integrity_after": step_report["store_integrity_after"],
        "store_integrity_delta": step_report["store_integrity_delta"],
        "state_returned": request["include_state"],
        "output_files": output_files,
        "api_calls_made": 0,
        "claim_boundary": [
            "This summary is for a no-API QVF service request run.",
            "It reports deterministic lifecycle/routing behavior, not target-model accuracy.",
        ],
    }
    for field_name in [
        "event_adapter_summary",
        "query_request_adapter_summary",
        "records_submitted_from_events",
        "records_submitted_from_records",
        "queries_submitted_from_requests",
        "queries_submitted_from_queries",
        "changed_memory_ids",
        "source_store_unchanged",
    ]:
        if field_name in step_report:
            summary[field_name] = step_report[field_name]
    return summary


def run_qvf_service_request(request: dict[str, Any]) -> dict[str, Any]:
    """Run a service request and attach safe model-facing sidecar payloads."""
    validated_request = validate_qvf_service_request_payload(request)
    pipeline, input_mode = build_qvf_service_pipeline(validated_request)
    step_runner = (
        pipeline.preview_validity_admission_event_step
        if validated_request["preview"]
        else pipeline.run_validity_admission_event_step
    )
    step_report = step_runner(
        events=validated_request["events"] or None,
        records=validated_request["records"],
        query_requests=validated_request["query_requests"] or None,
        queries=validated_request["queries"],
        weak_gate_outputs=validated_request["weak_gate_outputs"],
        include_state=validated_request["include_state"],
        step_id=validated_request["step_id"],
    )
    response = {
        "decision": (
            "GO_QVF_SERVICE_PREVIEW_READY_NO_API"
            if validated_request["preview"]
            else "GO_QVF_SERVICE_REQUEST_READY_NO_API"
        ),
        "execution_mode": "qvf_service_request",
        "request_id": validated_request["request_id"],
        "step_id": step_report["step_id"],
        "input_mode": input_mode,
        "preview": validated_request["preview"],
        "state_returned": validated_request["include_state"],
        "step_report": step_report,
        "summary": build_qvf_service_summary(
            validated_request,
            step_report,
            input_mode=input_mode,
            output_files=[],
        ),
        "api_calls_made": 0,
        "claim_boundary": [
            "This is a no-API service adapter around QVF validity-admission memory metadata.",
            "It consumes structured events/records/queries/read requests; it does not infer fields from raw text.",
            "It is an integration contract and engineering readiness evidence, not model-accuracy evidence.",
        ],
    }
    if validated_request["include_state"]:
        response["state"] = step_report.get("state") or pipeline.export_state()
    sidecar_payloads = build_model_facing_sidecar_payloads_from_response(response)
    response["model_facing_sidecar_payloads"] = sidecar_payloads
    response["summary"]["model_facing_payload_count"] = len(sidecar_payloads)
    return response

__all__ = [
    "QVFMemoryPipeline",
    "build_model_facing_sidecar_payloads_from_response",
    "build_qvf_service_pipeline",
    "build_qvf_service_summary",
    "load_qvf_service_request",
    "run_qvf_service_request",
    "validate_qvf_service_request_payload",
]
