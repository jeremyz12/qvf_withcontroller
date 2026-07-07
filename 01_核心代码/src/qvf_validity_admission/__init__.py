"""Minimal public import surface for the QVF controller progress package.

This desktop package keeps the controller-version core files and the small set
of compatibility modules needed to inspect and run the included tests. The full
research repository contains many additional experiment, reporting, and
historical-ablation modules that are intentionally omitted from this package.
"""

__version__ = "0.2.0-controller-progress"

from .admission import (
    build_memory_event_adapter_summary,
    build_query_request_adapter_summary,
    load_memory_events,
    load_query_requests,
    normalize_memory_event_payload,
    normalize_memory_events,
    normalize_query_request_payload,
    normalize_query_requests,
    validate_memory_events_payload,
    validate_query_requests_payload,
)
from .analysis_pipeline import (
    ANALYZER_VERSION,
    normalize_candidate_memory_payload,
    normalize_candidate_memory_payloads,
    parse_query_request_payload,
    run_qvf_parser_analyzer_request,
    write_parser_analyzer_eval,
)
from .answer_model_eval import (
    ANSWER_EVAL_VERSION,
    DEFAULT_ANSWER_MODEL,
    DEFAULT_CASES_PER_FAMILY,
    DEFAULT_JUDGE_MODEL,
    build_answer_eval_items,
    run_answer_model_eval,
)
from .decisions import (
    MODEL_FACING_FORBIDDEN_KEYS,
    assert_model_facing_payload_is_clean,
    build_model_facing_sidecar_payload,
    build_model_facing_sidecar_payloads,
    build_query_results,
    build_read_decisions,
    build_read_decisions_from_weak_gate_outputs,
    build_reader_responses,
    model_facing_forbidden_key_paths,
    normalize_weak_gate_decision,
    render_reader_response,
    route_read_time_packet,
    sanitize_model_facing_payload,
    score_weak_gate_outputs,
    validate_read_decision_payload,
    validate_reader_response_payload,
    validate_weak_gate_outputs_payload,
)
from .integration_eval import (
    build_heldout_integration_requests,
    build_model_eval_plan,
    run_heldout_integration_eval,
    write_heldout_integration_eval,
    write_model_eval_plan,
)
from .lifecycle import QVFMemoryPipeline
from .memory import MemoryRecord, ValidityAwareMemoryStore, load_memory_store_jsonl
from .pipeline import run_qvf_service_request
from .query_risk_router import QueryRiskRoute, route_query_risk, write_query_risk_route
from .retrieval import (
    build_lifecycle_packets,
    build_packets_from_store,
    build_validity_admission_packets,
    build_weak_gate_tasks,
    validate_packet_batch,
    validate_packet_payload,
)
from .service import (
    build_model_facing_sidecar_payloads_from_response,
    build_qvf_service_pipeline,
    build_qvf_service_summary,
)
from .stale400_adapter import stale400_case_to_validity_admission_request

__all__ = [
    "ANALYZER_VERSION",
    "ANSWER_EVAL_VERSION",
    "DEFAULT_ANSWER_MODEL",
    "DEFAULT_CASES_PER_FAMILY",
    "DEFAULT_JUDGE_MODEL",
    "MODEL_FACING_FORBIDDEN_KEYS",
    "MemoryRecord",
    "QVFMemoryPipeline",
    "QueryRiskRoute",
    "ValidityAwareMemoryStore",
    "__version__",
    "assert_model_facing_payload_is_clean",
    "build_answer_eval_items",
    "build_heldout_integration_requests",
    "build_lifecycle_packets",
    "build_memory_event_adapter_summary",
    "build_model_eval_plan",
    "build_model_facing_sidecar_payload",
    "build_model_facing_sidecar_payloads",
    "build_model_facing_sidecar_payloads_from_response",
    "build_packets_from_store",
    "build_query_request_adapter_summary",
    "build_query_results",
    "build_qvf_service_pipeline",
    "build_qvf_service_summary",
    "build_read_decisions",
    "build_read_decisions_from_weak_gate_outputs",
    "build_reader_responses",
    "build_validity_admission_packets",
    "build_weak_gate_tasks",
    "load_memory_events",
    "load_memory_store_jsonl",
    "load_query_requests",
    "model_facing_forbidden_key_paths",
    "normalize_candidate_memory_payload",
    "normalize_candidate_memory_payloads",
    "normalize_memory_event_payload",
    "normalize_memory_events",
    "normalize_query_request_payload",
    "normalize_query_requests",
    "normalize_weak_gate_decision",
    "parse_query_request_payload",
    "render_reader_response",
    "route_query_risk",
    "route_read_time_packet",
    "run_answer_model_eval",
    "run_heldout_integration_eval",
    "run_qvf_parser_analyzer_request",
    "run_qvf_service_request",
    "sanitize_model_facing_payload",
    "score_weak_gate_outputs",
    "stale400_case_to_validity_admission_request",
    "validate_memory_events_payload",
    "validate_packet_batch",
    "validate_packet_payload",
    "validate_query_requests_payload",
    "validate_read_decision_payload",
    "validate_reader_response_payload",
    "validate_weak_gate_outputs_payload",
    "write_heldout_integration_eval",
    "write_model_eval_plan",
    "write_parser_analyzer_eval",
    "write_query_risk_route",
]
