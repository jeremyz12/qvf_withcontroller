"""Stateful QVF lifecycle orchestration.

This module owns the public write-store-retrieve-packet-read pipeline class.
The older ``_pipeline_core`` module remains as a compatibility/helper layer while
stage implementations are split into focused modules.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ._pipeline_core import (
    LOW_CONFIDENCE_THRESHOLD,
    POLICY_VERSION,
    build_count_delta,
    build_lifecycle_step_delta,
    build_memory_store_diff,
    build_read_time_summary,
    count_rows_by_field,
    inspect_memory_scope,
    inspect_memory_store_record,
    inspect_query_against_store,
    load_jsonl,
    summarize_memory_store,
    validate_lifecycle_step_request_payload,
    validate_lifecycle_step_requests_payload,
    validate_memory_batch,
    validate_query_batch,
    validate_step_id,
    write_jsonl,
)
from .admission import (
    DEFAULT_EVENT_SOURCE_TYPE,
    build_memory_event_adapter_summary,
    build_query_request_adapter_summary,
    normalize_memory_events,
    normalize_query_requests,
)
from .decisions import (
    READER_VERSION,
    ROUTER_VERSION,
    build_query_results,
    build_read_decisions,
    build_read_decisions_from_weak_gate_outputs,
    build_reader_responses,
    render_reader_response,
    route_read_time_packet,
    validate_weak_gate_outputs_payload,
)
from .memory import MemoryRecord, ValidityAwareMemoryStore
from .retrieval import (
    build_weak_gate_tasks,
    validate_max_packet_chars,
    validate_retrieval_budget,
)

class QVFMemoryPipeline:
    def __init__(
        self,
        store: ValidityAwareMemoryStore | None = None,
        *,
        max_current: int = 1,
        max_supporting: int = 2,
        max_stale: int = 2,
        max_excluded: int = 2,
        max_packet_chars: int | None = None,
        include_validity_edges: bool = True,
        include_weak_gate_card: bool = True,
    ) -> None:
        budget = validate_retrieval_budget(
            max_current=max_current,
            max_supporting=max_supporting,
            max_stale=max_stale,
            max_excluded=max_excluded,
        )
        self.store = store or ValidityAwareMemoryStore()
        self.max_current = budget["max_current"]
        self.max_supporting = budget["max_supporting"]
        self.max_stale = budget["max_stale"]
        self.max_excluded = budget["max_excluded"]
        self.max_packet_chars = validate_max_packet_chars(max_packet_chars)
        self.include_validity_edges = include_validity_edges
        self.include_weak_gate_card = include_weak_gate_card

    @classmethod
    def from_records(
        cls,
        records: list[dict[str, Any]],
        *,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        **kwargs: Any,
    ) -> "QVFMemoryPipeline":
        store = ValidityAwareMemoryStore(
            low_confidence_threshold=low_confidence_threshold
        )
        pipeline = cls(store=store, **kwargs)
        pipeline.admit_records(records)
        return pipeline

    @classmethod
    def from_exported_records(
        cls,
        rows: list[dict[str, Any]],
        *,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        **kwargs: Any,
    ) -> "QVFMemoryPipeline":
        store = ValidityAwareMemoryStore.from_exported_records(
            rows,
            low_confidence_threshold=low_confidence_threshold,
        )
        return cls(store=store, **kwargs)

    @classmethod
    def from_store_file(
        cls,
        path: Path,
        *,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        **kwargs: Any,
    ) -> "QVFMemoryPipeline":
        return cls.from_exported_records(
            load_jsonl(path),
            low_confidence_threshold=low_confidence_threshold,
            **kwargs,
        )

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "QVFMemoryPipeline":
        if not isinstance(state, dict):
            raise ValueError("pipeline state must be an object")
        config = state.get("config")
        if not isinstance(config, dict):
            raise ValueError("pipeline state.config must be an object")
        records = state.get("memory_store")
        if not isinstance(records, list):
            raise ValueError("pipeline state.memory_store must be a list")
        low_confidence_threshold = config.get(
            "low_confidence_threshold",
            LOW_CONFIDENCE_THRESHOLD,
        )
        pipeline = cls.from_exported_records(
            records,
            low_confidence_threshold=low_confidence_threshold,
            max_current=config.get("max_current", 1),
            max_supporting=config.get("max_supporting", 2),
            max_stale=config.get("max_stale", 2),
            max_excluded=config.get("max_excluded", 2),
            max_packet_chars=config.get("max_packet_chars"),
            include_validity_edges=config.get("include_validity_edges", True),
            include_weak_gate_card=config.get("include_weak_gate_card", True),
        )
        expected_integrity = state.get("store_integrity")
        if expected_integrity is not None and expected_integrity != pipeline.validate_integrity():
            raise ValueError("pipeline state.store_integrity does not match loaded memory_store")
        admission_log = state.get("admission_log", [])
        if not isinstance(admission_log, list):
            raise ValueError("pipeline state.admission_log must be a list")
        pipeline.store.admission_log = deepcopy(admission_log)
        return pipeline

    @classmethod
    def from_state_file(cls, path: Path) -> "QVFMemoryPipeline":
        return cls.from_state(json.loads(path.read_text(encoding="utf-8-sig")))

    def admit(self, record: dict[str, Any]) -> MemoryRecord:
        return self.store.admit(record)

    def admit_records(self, records: list[dict[str, Any]]) -> list[MemoryRecord]:
        return self.store.admit_records(records)

    def admit_records_with_report(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        log_start = len(self.store.admission_log)
        admitted_records = self.store.admit_records(records)
        admission_events = deepcopy(self.store.admission_log[log_start:])
        return {
            "decision": "GO_QVF_LIFECYCLE_WRITE_TIME_ADMISSION_READY_NO_API",
            "execution_mode": "pipeline_incremental_admission_report",
            "records_submitted": len(admitted_records),
            "input_memory_ids": [record.memory_id for record in admitted_records],
            "admission_event_count": len(admission_events),
            "admission_events": admission_events,
            "admission_status_counts": count_rows_by_field(
                admission_events,
                "admission_status",
            ),
            "current_status_counts": count_rows_by_field(
                admission_events,
                "current_status",
            ),
            "evidence_role_counts": count_rows_by_field(
                admission_events,
                "evidence_role",
            ),
            "store_integrity": self.validate_integrity(),
            "api_calls_made": 0,
        }

    def adapt_memory_events(
        self,
        events: list[dict[str, Any]],
        *,
        default_source_confidence: float | None = None,
        default_source_type: str = DEFAULT_EVENT_SOURCE_TYPE,
    ) -> dict[str, Any]:
        source_confidence = (
            self.store.low_confidence_threshold
            if default_source_confidence is None
            else default_source_confidence
        )
        records = normalize_memory_events(
            events,
            default_source_confidence=source_confidence,
            default_source_type=default_source_type,
        )
        return {
            "records": records,
            "summary": build_memory_event_adapter_summary(events, records),
        }

    def admit_memory_events_with_report(
        self,
        events: list[dict[str, Any]],
        *,
        default_source_confidence: float | None = None,
        default_source_type: str = DEFAULT_EVENT_SOURCE_TYPE,
    ) -> dict[str, Any]:
        adapted = self.adapt_memory_events(
            events,
            default_source_confidence=default_source_confidence,
            default_source_type=default_source_type,
        )
        admission_report = self.admit_records_with_report(adapted["records"])
        report = deepcopy(admission_report)
        report["execution_mode"] = "pipeline_memory_event_admission_report"
        report["event_adapter_summary"] = adapted["summary"]
        report["records_submitted_from_events"] = len(adapted["records"])
        report["claim_boundary"] = [
            "This is a no-API write-time memory-event adapter plus QVF admission run.",
            "It normalizes structured memory events before QVF admission; it is not model-accuracy evidence.",
        ]
        return report

    def preview_admission(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        validated_records = validate_memory_batch(records)
        store_integrity_before = self.validate_integrity()
        current_index_before = summarize_memory_store(self.store)["current_index"]
        preview_pipeline = QVFMemoryPipeline.from_state(self.export_state())
        admission_report = preview_pipeline.admit_records_with_report(validated_records)
        store_integrity_after = preview_pipeline.validate_integrity()
        store_diff = build_memory_store_diff(self.store, preview_pipeline.store)
        return {
            "decision": "GO_QVF_LIFECYCLE_ADMISSION_PREVIEW_READY_NO_API",
            "execution_mode": "pipeline_admission_preview",
            "records_submitted": admission_report["records_submitted"],
            "admission_event_count": admission_report["admission_event_count"],
            "state_delta": build_lifecycle_step_delta(
                admission_report,
                {"query_results": []},
            ),
            "admission_report": admission_report,
            "store_integrity_before": store_integrity_before,
            "store_integrity_after": store_integrity_after,
            "store_integrity_delta": build_count_delta(
                store_integrity_before,
                store_integrity_after,
            ),
            "changed_memory_ids": store_diff["changed_memory_ids"],
            "store_diff": store_diff,
            "current_index_before": current_index_before,
            "current_index_after": summarize_memory_store(preview_pipeline.store)[
                "current_index"
            ],
            "original_store_integrity": self.validate_integrity(),
            "api_calls_made": 0,
            "claim_boundary": [
                "This is a no-API admission preview, not model-accuracy evidence.",
                "It runs write-time admission on a cloned store and does not mutate the source pipeline.",
            ],
        }

    def build_packet(self, query: dict[str, Any]) -> dict[str, Any]:
        return self.store.build_packet(
            query,
            max_current=self.max_current,
            max_supporting=self.max_supporting,
            max_stale=self.max_stale,
            max_excluded=self.max_excluded,
            max_packet_chars=self.max_packet_chars,
            include_validity_edges=self.include_validity_edges,
            include_weak_gate_card=self.include_weak_gate_card,
        )

    def inspect_query(self, query: dict[str, Any]) -> dict[str, Any]:
        return inspect_query_against_store(
            self.store,
            query,
            max_current=self.max_current,
            max_supporting=self.max_supporting,
            max_stale=self.max_stale,
            max_excluded=self.max_excluded,
            max_packet_chars=self.max_packet_chars,
            include_validity_edges=self.include_validity_edges,
            include_weak_gate_card=self.include_weak_gate_card,
        )

    def build_packets(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.build_packet(query) for query in validate_query_batch(queries)]

    def build_weak_gate_task_pack(
        self, queries: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        packets = self.build_packets(queries)
        return {
            "packets": packets,
            "weak_gate_tasks": build_weak_gate_tasks(packets),
        }

    def adapt_query_requests(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        queries = normalize_query_requests(requests)
        return {
            "queries": queries,
            "summary": build_query_request_adapter_summary(requests, queries),
        }

    def query(self, query: dict[str, Any]) -> dict[str, Any]:
        packet = self.build_packet(query)
        decision = route_read_time_packet(packet)
        response = render_reader_response(packet, decision)
        return build_query_results([packet], [decision], [response])[0]

    def query_with_weak_gate_output(
        self,
        query: dict[str, Any],
        weak_gate_output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        packet = self.build_packet(query)
        weak_gate_tasks = build_weak_gate_tasks([packet])
        weak_gate_outputs: list[dict[str, Any]] = []
        if weak_gate_output is not None:
            if not isinstance(weak_gate_output, dict):
                raise ValueError("weak_gate_output must be an object or null")
            output = deepcopy(weak_gate_output)
            output.setdefault("query_id", packet["query"]["query_id"])
            weak_gate_outputs = validate_weak_gate_outputs_payload([output])
        read_decisions, adapter_summary = build_read_decisions_from_weak_gate_outputs(
            [packet],
            weak_gate_tasks,
            weak_gate_outputs,
        )
        response = render_reader_response(packet, read_decisions[0])
        result = build_query_results([packet], read_decisions, [response])[0]
        result["weak_gate_tasks"] = weak_gate_tasks
        result["weak_gate_adapter_summary"] = adapter_summary
        return result

    def run_queries_with_weak_gate_outputs(
        self,
        queries: list[dict[str, Any]],
        weak_gate_outputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        weak_gate_outputs = validate_weak_gate_outputs_payload(weak_gate_outputs)
        packets = self.build_packets(queries)
        weak_gate_tasks = build_weak_gate_tasks(packets)
        read_decisions, adapter_summary = build_read_decisions_from_weak_gate_outputs(
            packets,
            weak_gate_tasks,
            weak_gate_outputs,
        )
        reader_responses = build_reader_responses(packets, read_decisions)
        query_results = build_query_results(packets, read_decisions, reader_responses)
        summary = build_read_time_summary(
            packets,
            read_decisions,
            reader_responses,
            [],
        )
        summary.update(
            {
                "decision": "GO_QVF_LIFECYCLE_QUERY_BATCH_READY_NO_API",
                "execution_mode": "pipeline_query_batch_report_with_weak_gate_outputs",
                "query_count": len(packets),
                "store_integrity": self.validate_integrity(),
                "retrieval_budget": {
                    "max_current": self.max_current,
                    "max_supporting": self.max_supporting,
                    "max_stale": self.max_stale,
                    "max_excluded": self.max_excluded,
                    "max_packet_chars": self.max_packet_chars,
                    "include_validity_edges": self.include_validity_edges,
                    "include_weak_gate_card": self.include_weak_gate_card,
                },
                "weak_gate_adapter_summary": adapter_summary,
            }
        )
        return {
            "packets": packets,
            "weak_gate_tasks": weak_gate_tasks,
            "read_decisions": read_decisions,
            "reader_responses": reader_responses,
            "query_results": query_results,
            "weak_gate_adapter_summary": adapter_summary,
            "summary": summary,
        }

    def run_queries_with_report(self, queries: list[dict[str, Any]]) -> dict[str, Any]:
        packets = self.build_packets(queries)
        read_decisions = build_read_decisions(packets)
        reader_responses = build_reader_responses(packets, read_decisions)
        query_results = build_query_results(packets, read_decisions, reader_responses)
        summary = build_read_time_summary(
            packets,
            read_decisions,
            reader_responses,
            [],
        )
        summary.update(
            {
                "decision": "GO_QVF_LIFECYCLE_QUERY_BATCH_READY_NO_API",
                "execution_mode": "pipeline_query_batch_report",
                "query_count": len(packets),
                "store_integrity": self.validate_integrity(),
                "retrieval_budget": {
                    "max_current": self.max_current,
                    "max_supporting": self.max_supporting,
                    "max_stale": self.max_stale,
                    "max_excluded": self.max_excluded,
                    "max_packet_chars": self.max_packet_chars,
                    "include_validity_edges": self.include_validity_edges,
                    "include_weak_gate_card": self.include_weak_gate_card,
                },
            }
        )
        return {
            "packets": packets,
            "read_decisions": read_decisions,
            "reader_responses": reader_responses,
            "query_results": query_results,
            "summary": summary,
        }

    def run_query_requests_with_report(
        self, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        adapted = self.adapt_query_requests(requests)
        report = self.run_queries_with_report(adapted["queries"])
        report["query_request_adapter_summary"] = adapted["summary"]
        report["summary"]["query_request_adapter_summary"] = adapted["summary"]
        report["summary"]["execution_mode"] = "pipeline_query_request_batch_report"
        return report

    def run_validity_admission_step(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if records is not None and not isinstance(records, list):
            raise ValueError("records must be a list")
        if queries is not None and not isinstance(queries, list):
            raise ValueError("queries must be a list")
        weak_gate_outputs = validate_weak_gate_outputs_payload(
            weak_gate_outputs,
            optional=True,
        )
        validated_records = validate_memory_batch(records or [])
        validated_queries = validate_query_batch(queries or [])
        step_id = validate_step_id(step_id)
        store_integrity_before = self.validate_integrity()
        admission_report = self.admit_records_with_report(validated_records)
        if weak_gate_outputs is None:
            query_report = self.run_queries_with_report(validated_queries)
            query_mode = "deterministic_router"
        else:
            query_report = self.run_queries_with_weak_gate_outputs(
                validated_queries,
                weak_gate_outputs,
            )
            query_mode = "weak_gate_output_adapter"
        store_integrity_after = self.validate_integrity()
        step_report = {
            "decision": "GO_QVF_LIFECYCLE_STEP_READY_NO_API",
            "execution_mode": "pipeline_lifecycle_step",
            "step_id": step_id,
            "records_submitted": admission_report["records_submitted"],
            "admission_event_count": admission_report["admission_event_count"],
            "query_count": query_report["summary"]["query_count"],
            "query_mode": query_mode,
            "state_delta": build_lifecycle_step_delta(
                admission_report,
                query_report,
            ),
            "admission_report": admission_report,
            "query_report": query_report,
            "store_integrity_before": store_integrity_before,
            "store_integrity_after": store_integrity_after,
            "store_integrity_delta": build_count_delta(
                store_integrity_before,
                store_integrity_after,
            ),
            "store_integrity": store_integrity_after,
            "api_calls_made": 0,
        }
        if include_state:
            step_report["state"] = self.export_state()
        return step_report

    def run_validity_admission_event_step(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        records: list[dict[str, Any]] | None = None,
        query_requests: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if events is not None and not isinstance(events, list):
            raise ValueError("events must be a list")
        if records is not None and not isinstance(records, list):
            raise ValueError("records must be a list")
        if query_requests is not None and not isinstance(query_requests, list):
            raise ValueError("query_requests must be a list")
        explicit_records = validate_memory_batch(records or [])
        adapted = self.adapt_memory_events(events or [])
        combined_records = explicit_records + adapted["records"]
        explicit_queries = validate_query_batch(queries or [])
        adapted_queries = self.adapt_query_requests(query_requests or [])
        combined_queries = explicit_queries + adapted_queries["queries"]
        step_report = self.run_validity_admission_step(
            records=combined_records,
            queries=combined_queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state,
            step_id=step_id,
        )
        if events is not None:
            step_report["event_adapter_summary"] = adapted["summary"]
            step_report["records_submitted_from_events"] = len(adapted["records"])
            step_report["records_submitted_from_records"] = len(explicit_records)
            step_report["claim_boundary"] = [
                "This is a no-API lifecycle event step, not model-accuracy evidence.",
                "Structured memory events are normalized before write-time QVF admission and read-time routing.",
            ]
        if query_requests is not None:
            step_report["query_request_adapter_summary"] = adapted_queries["summary"]
            step_report["queries_submitted_from_requests"] = len(adapted_queries["queries"])
            step_report["queries_submitted_from_queries"] = len(explicit_queries)
        return step_report

    def preview_validity_admission_step(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        store_integrity_before = self.validate_integrity()
        preview_pipeline = QVFMemoryPipeline.from_state(self.export_state())
        step_report = preview_pipeline.run_validity_admission_step(
            records=records,
            queries=queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state,
            step_id=step_id,
        )
        store_diff = build_memory_store_diff(self.store, preview_pipeline.store)
        step_report["decision"] = "GO_QVF_LIFECYCLE_STEP_PREVIEW_READY_NO_API"
        step_report["execution_mode"] = "pipeline_lifecycle_step_preview"
        step_report["changed_memory_ids"] = store_diff["changed_memory_ids"]
        step_report["store_diff"] = store_diff
        step_report["preview_does_not_mutate_source"] = True
        step_report["original_store_integrity"] = self.validate_integrity()
        step_report["source_store_unchanged"] = (
            step_report["original_store_integrity"] == store_integrity_before
        )
        step_report["claim_boundary"] = [
            "This is a no-API lifecycle step preview, not model-accuracy evidence.",
            "It runs write-time admission and deterministic read-time QVF on a cloned store.",
            "The source pipeline is not mutated by the preview.",
        ]
        return step_report

    def preview_validity_admission_event_step(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        records: list[dict[str, Any]] | None = None,
        query_requests: list[dict[str, Any]] | None = None,
        queries: list[dict[str, Any]] | None = None,
        weak_gate_outputs: list[dict[str, Any]] | None = None,
        include_state: bool = False,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if events is not None and not isinstance(events, list):
            raise ValueError("events must be a list")
        if records is not None and not isinstance(records, list):
            raise ValueError("records must be a list")
        if query_requests is not None and not isinstance(query_requests, list):
            raise ValueError("query_requests must be a list")
        explicit_records = validate_memory_batch(records or [])
        adapted = self.adapt_memory_events(events or [])
        combined_records = explicit_records + adapted["records"]
        explicit_queries = validate_query_batch(queries or [])
        adapted_queries = self.adapt_query_requests(query_requests or [])
        combined_queries = explicit_queries + adapted_queries["queries"]
        step_report = self.preview_validity_admission_step(
            records=combined_records,
            queries=combined_queries,
            weak_gate_outputs=weak_gate_outputs,
            include_state=include_state,
            step_id=step_id,
        )
        if events is not None:
            step_report["event_adapter_summary"] = adapted["summary"]
            step_report["records_submitted_from_events"] = len(adapted["records"])
            step_report["records_submitted_from_records"] = len(explicit_records)
            step_report["claim_boundary"] = [
                "This is a no-API lifecycle event-step preview, not model-accuracy evidence.",
                "Structured memory events are normalized on a cloned store before QVF admission/read-time routing.",
                "The source pipeline is not mutated by the preview.",
            ]
        if query_requests is not None:
            step_report["query_request_adapter_summary"] = adapted_queries["summary"]
            step_report["queries_submitted_from_requests"] = len(adapted_queries["queries"])
            step_report["queries_submitted_from_queries"] = len(explicit_queries)
        return step_report

    def run_validity_admission_step_request(self, request: dict[str, Any]) -> dict[str, Any]:
        validated_request = validate_lifecycle_step_request_payload(request)
        return self.run_validity_admission_event_step(
            events=validated_request["events"] or None,
            records=validated_request["records"],
            query_requests=validated_request["query_requests"] or None,
            queries=validated_request["queries"],
            weak_gate_outputs=validated_request["weak_gate_outputs"],
            include_state=validated_request["include_state"],
            step_id=validated_request["step_id"],
        )

    def run_validity_admission_steps(
        self,
        requests: list[dict[str, Any]],
        *,
        include_final_state: bool = False,
        transactional: bool = True,
    ) -> dict[str, Any]:
        validated_requests = validate_lifecycle_step_requests_payload(requests)
        if not isinstance(include_final_state, bool):
            raise ValueError("include_final_state must be a boolean")
        if not isinstance(transactional, bool):
            raise ValueError("transactional must be a boolean")

        working_pipeline = (
            QVFMemoryPipeline.from_state(self.export_state())
            if transactional
            else self
        )
        store_integrity_before = self.validate_integrity()
        step_reports: list[dict[str, Any]] = []
        for index, request in enumerate(validated_requests):
            step_report = working_pipeline.run_validity_admission_event_step(
                events=request["events"] or None,
                records=request["records"],
                query_requests=request["query_requests"] or None,
                queries=request["queries"],
                weak_gate_outputs=request["weak_gate_outputs"],
                include_state=request["include_state"],
                step_id=request["step_id"],
            )
            step_report["batch_step_index"] = index
            step_reports.append(step_report)

        if transactional:
            self.store = working_pipeline.store

        store_integrity_after = self.validate_integrity()
        summary = {
            "decision": "GO_QVF_LIFECYCLE_MULTI_STEP_READY_NO_API",
            "execution_mode": "pipeline_lifecycle_multi_step",
            "transactional": transactional,
            "step_count": len(step_reports),
            "step_ids": [report["step_id"] for report in step_reports],
            "event_count": sum(
                report.get("event_adapter_summary", {}).get("event_count", 0)
                for report in step_reports
            ),
            "event_record_count": sum(
                report.get("event_adapter_summary", {}).get("normalized_record_count", 0)
                for report in step_reports
            ),
            "query_request_count": sum(
                report.get("query_request_adapter_summary", {}).get("request_count", 0)
                for report in step_reports
            ),
            "query_request_record_count": sum(
                report.get("query_request_adapter_summary", {}).get(
                    "normalized_query_count",
                    0,
                )
                for report in step_reports
            ),
            "records_submitted": sum(report["records_submitted"] for report in step_reports),
            "admission_event_count": sum(
                report["admission_event_count"] for report in step_reports
            ),
            "query_count": sum(report["query_count"] for report in step_reports),
            "query_mode_counts": count_rows_by_field(step_reports, "query_mode"),
            "store_integrity_before": store_integrity_before,
            "store_integrity_after": store_integrity_after,
            "store_integrity_delta": build_count_delta(
                store_integrity_before,
                store_integrity_after,
            ),
            "store_integrity": store_integrity_after,
            "api_calls_made": 0,
        }
        result = {
            "decision": summary["decision"],
            "execution_mode": summary["execution_mode"],
            "steps": step_reports,
            "summary": summary,
        }
        if include_final_state:
            result["state"] = self.export_state()
        return result

    # Backward-compatible aliases for historical local scripts and aggregate-result lineage.
    def run_lifecycle_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.run_validity_admission_step(**kwargs)

    def run_lifecycle_event_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.run_validity_admission_event_step(**kwargs)

    def preview_lifecycle_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.preview_validity_admission_step(**kwargs)

    def preview_lifecycle_event_step(self, **kwargs: Any) -> dict[str, Any]:
        return self.preview_validity_admission_event_step(**kwargs)

    def run_lifecycle_step_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.run_validity_admission_step_request(request)

    def run_lifecycle_steps(
        self,
        requests: list[dict[str, Any]],
        *,
        include_final_state: bool = False,
        transactional: bool = True,
    ) -> dict[str, Any]:
        return self.run_validity_admission_steps(
            requests,
            include_final_state=include_final_state,
            transactional=transactional,
        )

    def run_queries(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.run_queries_with_report(queries)["query_results"]

    def summarize_store(self) -> dict[str, Any]:
        return summarize_memory_store(self.store)

    def inspect_memory(self, memory_id: str) -> dict[str, Any]:
        return inspect_memory_store_record(self.store, memory_id)

    def inspect_scope(
        self,
        entity: str,
        slot: str,
        *,
        namespace: str = "",
        tenant_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        return inspect_memory_scope(
            self.store,
            entity,
            slot,
            namespace=namespace,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    def validate_integrity(self) -> dict[str, int]:
        return self.store.validate_integrity()

    def export_memory_store(self) -> list[dict[str, Any]]:
        return self.store.export_memory_store()

    def save_memory_store(self, path: Path) -> None:
        write_jsonl(path, self.export_memory_store())

    def export_state(self) -> dict[str, Any]:
        return {
            "state_version": "qvf_validity_admission_pipeline_state_v0.1_no_api",
            "policy_version": POLICY_VERSION,
            "router_version": ROUTER_VERSION,
            "reader_version": READER_VERSION,
            "config": {
                "low_confidence_threshold": self.store.low_confidence_threshold,
                "max_current": self.max_current,
                "max_supporting": self.max_supporting,
                "max_stale": self.max_stale,
                "max_excluded": self.max_excluded,
                "max_packet_chars": self.max_packet_chars,
                "include_validity_edges": self.include_validity_edges,
                "include_weak_gate_card": self.include_weak_gate_card,
            },
            "store_integrity": self.validate_integrity(),
            "memory_store": self.export_memory_store(),
            "admission_log": deepcopy(self.store.admission_log),
            "api_calls_made": 0,
            "claim_boundary": [
                "This state snapshot contains lifecycle QVF memory metadata, not model-run evidence.",
                "Raw prompts, target outputs, judge traces, and secrets are intentionally excluded.",
            ],
        }

    def save_state(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.export_state(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

__all__ = ["QVFMemoryPipeline"]
