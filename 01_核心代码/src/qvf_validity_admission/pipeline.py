"""End-to-end QVF validity-admission pipeline facade.

This module is the preferred import point for applications that want to plug QVF
between memory retrieval and answer generation.
"""

from .lifecycle import QVFMemoryPipeline
from .service import (
    build_model_facing_sidecar_payloads_from_response,
    build_qvf_service_pipeline,
    build_qvf_service_summary,
    load_qvf_service_request,
    run_qvf_service_request,
    validate_qvf_service_request_payload,
)

__all__ = [
    "QVFMemoryPipeline",
    "build_model_facing_sidecar_payloads_from_response",
    "build_qvf_service_pipeline",
    "build_qvf_service_summary",
    "load_qvf_service_request",
    "run_qvf_service_request",
    "validate_qvf_service_request_payload",
]
