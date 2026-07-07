from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ._pipeline_core import (
    ADMISSION_STATUSES,
    CURRENT_STATUSES,
    EVIDENCE_ROLES,
    LINK_EDGE_TYPES,
    LOW_CONFIDENCE_THRESHOLD,
    POLICY_VERSION,
    READER_PROFILES,
    RECIPROCAL_LINK_EDGE_TYPES,
    RISK_PROFILE_DEFAULTS,
    _validate_exported_link_targets,
    _validate_exported_status_field,
    _validate_exported_status_triple,
    apply_packet_char_budget,
    load_jsonl,
    norm,
    parse_dt,
    refresh_token_budget_proxy,
    validate_low_confidence_threshold,
    validate_max_packet_chars,
    validate_memory_batch,
    validate_memory_payload,
    validate_query_payload,
    validate_retrieval_budget,
)


@dataclass
class MemoryRecord:
    payload: dict[str, Any]
    admission_status: str = "candidate"
    current_status: str = "candidate"
    evidence_role: str = "current_support"
    links: dict[str, list[str]] = field(
        default_factory=lambda: {edge_type: [] for edge_type in LINK_EDGE_TYPES}
    )
    admission_reason: str = ""

    @classmethod
    def from_public_dict(cls, row: dict[str, Any]) -> "MemoryRecord":
        payload = deepcopy(row)
        memory_id = str(payload.get("memory_id", "<unknown>"))
        admission_status = _validate_exported_status_field(
            payload.pop("admission_status", "candidate"),
            field_name="admission_status",
            memory_id=memory_id,
            allowed_values=ADMISSION_STATUSES,
        )
        current_status = _validate_exported_status_field(
            payload.pop("current_status", "candidate"),
            field_name="current_status",
            memory_id=memory_id,
            allowed_values=CURRENT_STATUSES,
        )
        evidence_role = _validate_exported_status_field(
            payload.pop("evidence_role", "current_support"),
            field_name="evidence_role",
            memory_id=memory_id,
            allowed_values=EVIDENCE_ROLES,
        )
        _validate_exported_status_triple(
            admission_status=admission_status,
            current_status=current_status,
            evidence_role=evidence_role,
            memory_id=memory_id,
        )
        links = payload.pop("links", None)
        if links is None:
            links = {}
        if not isinstance(links, dict):
            raise ValueError(f"links must be an object for {memory_id}")
        unknown_edges = sorted(set(links) - set(LINK_EDGE_TYPES))
        if unknown_edges:
            raise ValueError(
                "Unknown link edge type in exported records for "
                f"{memory_id}: {', '.join(unknown_edges)}"
            )
        audit = payload.pop("audit", None) or {}
        payload = validate_memory_payload(payload)
        normalized_links: dict[str, list[str]] = {}
        for edge_type in LINK_EDGE_TYPES:
            normalized_links[edge_type] = _validate_exported_link_targets(
                links.get(edge_type, []),
                edge_type=edge_type,
                memory_id=memory_id,
            )
        return cls(
            payload=payload,
            admission_status=admission_status,
            current_status=current_status,
            evidence_role=evidence_role,
            links=normalized_links,
            admission_reason=str(audit.get("admission_reason", "")),
        )

    @property
    def memory_id(self) -> str:
        return self.payload["memory_id"]

    @property
    def entity(self) -> str:
        return self.payload["entity"]

    @property
    def slot(self) -> str:
        return self.payload["slot"]

    @property
    def value(self) -> str:
        return self.payload["value"]

    @property
    def observed_at(self) -> datetime:
        parsed = parse_dt(self.payload["observed_at"])
        if parsed is None:
            raise ValueError(f"Missing observed_at for {self.memory_id}")
        return parsed

    @property
    def valid_from(self) -> datetime:
        parsed = parse_dt(self.payload.get("valid_from") or self.payload["observed_at"])
        if parsed is None:
            raise ValueError(f"Missing valid_from/observed_at for {self.memory_id}")
        return parsed

    @property
    def valid_until(self) -> datetime | None:
        return parse_dt(self.payload.get("valid_until"))

    @property
    def source_confidence(self) -> float:
        return float(self.payload["source_confidence"])

    @property
    def source_id(self) -> str:
        return str(self.payload.get("source", {}).get("source_id", ""))

    @property
    def source_type(self) -> str:
        return str(self.payload.get("source", {}).get("source_type", ""))

    @property
    def scope(self) -> dict[str, str]:
        raw_scope = self.payload.get("scope", {}) or {}
        return {
            "namespace": str(raw_scope.get("namespace") or self.payload.get("namespace") or ""),
            "tenant_id": str(raw_scope.get("tenant_id") or self.payload.get("tenant_id") or ""),
            "user_id": str(raw_scope.get("user_id") or self.payload.get("user_id") or ""),
        }

    @property
    def key(self) -> tuple[str, str]:
        return norm(self.entity), norm(self.slot)

    @property
    def scoped_key(self) -> tuple[str, str, str, str, str]:
        scope = self.scope
        return (
            norm(scope["namespace"]),
            norm(scope["tenant_id"]),
            norm(scope["user_id"]),
            self.key[0],
            self.key[1],
        )

    def to_public_dict(self) -> dict[str, Any]:
        out = deepcopy(self.payload)
        out["admission_status"] = self.admission_status
        out["current_status"] = self.current_status
        out["evidence_role"] = self.evidence_role
        out["links"] = deepcopy(self.links)
        out["audit"] = {
            "policy_version": POLICY_VERSION,
            "admission_reason": self.admission_reason,
            "normalized_key": f"{self.key[0]}::{self.key[1]}",
            "normalized_scoped_key": "::".join(self.scoped_key),
        }
        return out


class ValidityAwareMemoryStore:
    def __init__(
        self, low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD
    ) -> None:
        self.low_confidence_threshold = validate_low_confidence_threshold(
            low_confidence_threshold
        )
        self.records: dict[str, MemoryRecord] = {}
        self.current_by_key: dict[tuple[str, str, str, str, str], str] = {}
        self.admission_log: list[dict[str, Any]] = []

    @classmethod
    def from_exported_records(
        cls,
        rows: list[dict[str, Any]],
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    ) -> "ValidityAwareMemoryStore":
        store = cls(low_confidence_threshold=low_confidence_threshold)
        for row in rows:
            record = MemoryRecord.from_public_dict(row)
            if record.memory_id in store.records:
                raise ValueError(f"Duplicate memory_id in exported records: {record.memory_id}")
            store.records[record.memory_id] = record
        store._validate_link_targets()
        store._validate_reciprocal_links()

        for record in store.records.values():
            if record.current_status != "current":
                continue
            existing_id = store.current_by_key.get(record.scoped_key)
            if existing_id is None:
                store.current_by_key[record.scoped_key] = record.memory_id
                continue
            normalized_key = "::".join(record.scoped_key)
            raise ValueError(
                "Multiple current records for scoped key "
                f"{normalized_key}: {existing_id}, {record.memory_id}"
            )
        store.validate_integrity()
        return store

    def validate_integrity(self) -> dict[str, int]:
        self._validate_link_targets()
        self._validate_reciprocal_links()

        current_records_by_key: dict[tuple[str, str, str, str, str], str] = {}
        link_edge_count = 0
        for record in self.records.values():
            link_edge_count += sum(len(targets) for targets in record.links.values())
            if record.current_status != "current":
                continue
            existing_id = current_records_by_key.get(record.scoped_key)
            if existing_id is not None and existing_id != record.memory_id:
                normalized_key = "::".join(record.scoped_key)
                raise ValueError(
                    "Multiple current records for scoped key "
                    f"{normalized_key}: {existing_id}, {record.memory_id}"
                )
            current_records_by_key[record.scoped_key] = record.memory_id
            indexed_id = self.current_by_key.get(record.scoped_key)
            if indexed_id != record.memory_id:
                normalized_key = "::".join(record.scoped_key)
                raise ValueError(
                    "Current memory missing from current_by_key for scoped key "
                    f"{normalized_key}: expected {record.memory_id}, found {indexed_id}"
                )

        for scoped_key, memory_id in self.current_by_key.items():
            record = self.records.get(memory_id)
            normalized_key = "::".join(scoped_key)
            if record is None:
                raise ValueError(
                    "current_by_key points to missing memory for scoped key "
                    f"{normalized_key}: {memory_id}"
                )
            if record.scoped_key != scoped_key:
                raise ValueError(
                    "current_by_key scoped key mismatch for "
                    f"{memory_id}: indexed {normalized_key}, actual {'::'.join(record.scoped_key)}"
                )
            if record.current_status != "current":
                raise ValueError(
                    "current_by_key points to non-current memory "
                    f"{memory_id}: current_status={record.current_status}"
                )

        return {
            "records": len(self.records),
            "current_index_entries": len(self.current_by_key),
            "current_records": len(current_records_by_key),
            "link_edges": link_edge_count,
        }

    def _validate_link_targets(self) -> None:
        for record in self.records.values():
            for edge_type, targets in record.links.items():
                for target_id in targets:
                    if target_id not in self.records:
                        raise ValueError(
                            "Dangling link target in exported records: "
                            f"{record.memory_id}.{edge_type} -> {target_id}"
                        )

    def _validate_reciprocal_links(self) -> None:
        for record in self.records.values():
            for edge_type, reciprocal_type in RECIPROCAL_LINK_EDGE_TYPES.items():
                for target_id in record.links.get(edge_type, []):
                    target = self.records[target_id]
                    if record.memory_id not in target.links.get(reciprocal_type, []):
                        raise ValueError(
                            "Non-reciprocal link in exported records: "
                            f"{record.memory_id}.{edge_type} -> {target_id} "
                            f"requires {target_id}.{reciprocal_type} -> {record.memory_id}"
                        )

    def admit(self, candidate_payload: dict[str, Any]) -> MemoryRecord:
        record = MemoryRecord(payload=validate_memory_payload(candidate_payload))

        if record.memory_id in self.records:
            record.admission_status = "reject_duplicate_memory_id"
            record.current_status = "rejected"
            record.evidence_role = "excluded_duplicate_memory_id"
            record.admission_reason = (
                "memory_id already exists; duplicate write rejected without overwriting stored memory"
            )
            self._log(record)
            return record

        key = record.scoped_key

        if record.source_confidence < self.low_confidence_threshold:
            record.admission_status = "reject_low_confidence"
            record.current_status = "rejected"
            record.evidence_role = "excluded_low_confidence"
            record.admission_reason = (
                f"source_confidence {record.source_confidence:.2f} below "
                f"{self.low_confidence_threshold:.2f}"
            )
            self.records[record.memory_id] = record
            self._log(record)
            return record

        validity_action = norm(str(record.payload.get("validity_action", "")))
        if validity_action in {"revoke_current", "invalidate_current", "invalidate"}:
            return self._admit_validity_marker(record, key)

        previous_current_id = self.current_by_key.get(key)
        if previous_current_id is None:
            record.admission_status = "admit_current"
            record.current_status = "current"
            record.evidence_role = "current_support"
            record.admission_reason = "first admitted current evidence for entity-slot key"
            self.current_by_key[key] = record.memory_id
            self.records[record.memory_id] = record
            self._log(record)
            return record

        previous = self.records[previous_current_id]

        if norm(previous.value) == norm(record.value):
            record.admission_status = "admit_supporting_evidence"
            record.current_status = "supporting"
            record.evidence_role = "supporting_duplicate"
            record.links["supports"].append(previous.memory_id)
            previous.links["supports"].append(record.memory_id)
            record.admission_reason = "same value as existing current memory; stored as support"
            self.records[record.memory_id] = record
            self._log(record)
            return record

        if record.observed_at >= previous.observed_at:
            record.admission_status = "admit_current"
            record.current_status = "current"
            record.evidence_role = "current_support"
            record.links["supersedes"].append(previous.memory_id)
            record.links["contradicts"].append(previous.memory_id)
            record.admission_reason = "newer conflicting evidence supersedes previous current memory"

            previous.admission_status = "admit_as_stale_contrast"
            previous.current_status = "superseded"
            previous.evidence_role = "stale_contrast"
            previous.links["superseded_by"].append(record.memory_id)
            previous.links["contradicts"].append(record.memory_id)
            previous.admission_reason = (
                "superseded by newer conflicting evidence; retained as stale contrast"
            )

            self.current_by_key[key] = record.memory_id
            self.records[record.memory_id] = record
            self._log(record)
            self._log(previous)
            return record

        record.admission_status = "admit_as_stale_contrast"
        record.current_status = "superseded"
        record.evidence_role = "stale_contrast"
        record.links["superseded_by"].append(previous.memory_id)
        record.links["contradicts"].append(previous.memory_id)
        record.admission_reason = "older conflicting evidence retained as stale contrast"
        previous.links["supersedes"].append(record.memory_id)
        previous.links["contradicts"].append(record.memory_id)
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def admit_records(self, records: list[dict[str, Any]]) -> list[MemoryRecord]:
        validated_records = validate_memory_batch(records)
        return [self.admit(record) for record in validated_records]

    def _admit_validity_marker(
        self, record: MemoryRecord, key: tuple[str, str, str, str, str]
    ) -> MemoryRecord:
        requested_target_ids = [
            str(memory_id)
            for memory_id in record.payload.get("invalidates_memory_ids", [])
        ]
        explicit_targets: list[str] = []
        scope_mismatch_count = 0
        for memory_id in requested_target_ids:
            target = self.records.get(memory_id)
            if target is None:
                continue
            if target.scoped_key != record.scoped_key:
                scope_mismatch_count += 1
                continue
            explicit_targets.append(memory_id)
        if scope_mismatch_count:
            record.payload["invalidates_scope_mismatch_count"] = scope_mismatch_count
        current_id = self.current_by_key.get(key)
        if requested_target_ids:
            target_ids = explicit_targets
        else:
            target_ids = [current_id] if current_id else []

        record.admission_status = "admit_validity_marker"
        record.current_status = "validity_marker"
        record.evidence_role = "validity_marker"
        record.admission_reason = (
            "write-time validity marker; invalidates current evidence for entity-slot key"
        )

        for target_id in target_ids:
            if not target_id:
                continue
            target = self.records[target_id]
            target.admission_status = "revoked_by_validity_marker"
            target.current_status = "revoked"
            target.evidence_role = "stale_contrast"
            if record.memory_id not in target.links["invalidated_by"]:
                target.links["invalidated_by"].append(record.memory_id)
            if record.memory_id not in target.links["contradicts"]:
                target.links["contradicts"].append(record.memory_id)
            if target.memory_id not in record.links["invalidates"]:
                record.links["invalidates"].append(target.memory_id)
            if target.memory_id not in record.links["contradicts"]:
                record.links["contradicts"].append(target.memory_id)
            target.admission_reason = (
                "revoked by write-time validity marker; retained as stale contrast"
            )
            if self.current_by_key.get(target.scoped_key) == target.memory_id:
                del self.current_by_key[target.scoped_key]
            self._log(target)

        if not target_ids:
            if scope_mismatch_count:
                record.admission_reason = (
                    "write-time validity marker admitted but explicit invalidation targets "
                    "were outside the marker scope"
                )
            else:
                record.admission_reason = (
                    "write-time validity marker admitted but no matching current evidence was found"
                )
        elif scope_mismatch_count:
            record.admission_reason = (
                f"{record.admission_reason}; ignored {scope_mismatch_count} cross-scope target(s)"
            )

        self.records[record.memory_id] = record
        self._log(record)
        return record

    def build_packet(
        self,
        query: dict[str, Any],
        *,
        max_current: int = 1,
        max_supporting: int = 2,
        max_stale: int = 2,
        max_excluded: int = 2,
        max_packet_chars: int | None = None,
        include_validity_edges: bool = True,
        include_weak_gate_card: bool = True,
    ) -> dict[str, Any]:
        query = validate_query_payload(query)
        budget = validate_retrieval_budget(
            max_current=max_current,
            max_supporting=max_supporting,
            max_stale=max_stale,
            max_excluded=max_excluded,
        )
        max_current = budget["max_current"]
        max_supporting = budget["max_supporting"]
        max_stale = budget["max_stale"]
        max_excluded = budget["max_excluded"]
        max_packet_chars = validate_max_packet_chars(max_packet_chars)

        key = norm(query["entity"]), norm(query["slot"])
        as_of = parse_dt(query.get("as_of"))
        risk_profile = self._query_risk_profile(query)
        reader_profile = self._query_reader_profile(query)
        query_intent = self._query_intent(query)
        max_age_days = self._query_max_age_days(query, risk_profile)
        min_source_confidence = self._query_min_source_confidence(query, risk_profile)
        min_supporting_count = self._query_min_supporting_count(query, risk_profile)
        source_policy = self._query_source_policy(query)
        query_scope = self._query_scope(query)
        key_related = [record for record in self.records.values() if record.key == key]
        scope_mismatch_ids = {
            record.memory_id
            for record in key_related
            if not self._scope_matches_query(record, query_scope)
        }
        related = [
            record for record in key_related if record.memory_id not in scope_mismatch_ids
        ]
        not_yet_valid_ids = {
            record.memory_id
            for record in related
            if self._is_not_yet_valid_for_query(record, as_of)
        }
        expired_ids = {
            record.memory_id
            for record in related
            if self._is_expired_for_query(record, as_of)
        }
        revoked_ids = {
            record.memory_id
            for record in related
            if self._is_revoked_for_query(record, as_of)
        }
        stale_by_age_ids = {
            record.memory_id
            for record in related
            if self._is_stale_by_age_for_query(record, as_of, max_age_days)
        }
        below_query_confidence_ids = {
            record.memory_id
            for record in related
            if self._is_below_query_confidence(record, min_source_confidence)
        }
        source_policy_mismatch_ids = {
            record.memory_id
            for record in related
            if self._violates_source_policy(record, source_policy)
        }
        condition_mismatch_ids = {
            record.memory_id
            for record in related
            if not self._condition_matches_query(record, query)
        }
        base_blocked_ids = (
            not_yet_valid_ids
            | expired_ids
            | revoked_ids
            | stale_by_age_ids
            | below_query_confidence_ids
            | source_policy_mismatch_ids
            | condition_mismatch_ids
        )
        base_current_candidates = self._current_candidates_for_query(
            related=related,
            blocked_ids=base_blocked_ids,
            as_of=as_of,
        )
        insufficient_support_ids = {
            record.memory_id
            for record in base_current_candidates
            if self._support_count_for_record(record, related, base_blocked_ids)
            < min_supporting_count
        }
        blocked_ids = base_blocked_ids | insufficient_support_ids
        current_candidates = [
            record for record in base_current_candidates if record.memory_id not in blocked_ids
        ]
        current = self._select_records(
            current_candidates,
            max_current,
        )
        current_ids = {record.memory_id for record in current}
        dynamically_blocked = [
            record
            for record in related
            if record.memory_id in blocked_ids
            and record.current_status in {"current", "supporting", "superseded", "revoked"}
        ]
        stale = self._select_records(
            self._dedupe_records(
                [
                    record
                    for record in related
                    if record.evidence_role in {"stale_contrast", "validity_marker"}
                    and record.memory_id not in current_ids
                ]
                + dynamically_blocked
            ),
            max_stale,
        )
        supporting = self._select_records(
            [
                record
                for record in related
                if record.evidence_role == "supporting_duplicate"
                and record.memory_id not in blocked_ids
            ],
            max_supporting,
        )
        excluded = self._select_records(
            [
                record
                for record in related
                if record.evidence_role == "excluded_low_confidence"
            ],
            max_excluded,
        )
        historical = self._historical_evidence_for_query(query_intent, stale)

        selected_records = current + supporting + stale + excluded
        selected_ids = {record.memory_id for record in selected_records}
        edges = (
            self._validity_edges(selected_records, selected_ids)
            if include_validity_edges
            else []
        )
        retrieval_diagnostics = self._retrieval_diagnostics(
            related=related,
            current_candidates=current_candidates,
            current=current,
            supporting=supporting,
            stale=stale,
            excluded=excluded,
            not_yet_valid_ids=not_yet_valid_ids,
            expired_ids=expired_ids,
            revoked_ids=revoked_ids,
            stale_by_age_ids=stale_by_age_ids,
            below_query_confidence_ids=below_query_confidence_ids,
            insufficient_support_ids=insufficient_support_ids,
            source_policy_mismatch_ids=source_policy_mismatch_ids,
            scope_mismatch_ids=scope_mismatch_ids,
            condition_mismatch_ids=condition_mismatch_ids,
            blocked_ids=blocked_ids,
        )
        retrieval_diagnostics["selected_counts"]["historical_evidence"] = len(historical)
        context_policy = self._context_control_policy_for_intent(
            query_intent=query_intent,
            max_current=max_current,
            max_supporting=max_supporting,
            max_stale=max_stale,
            max_excluded=max_excluded,
            max_packet_chars=max_packet_chars,
            include_validity_edges=include_validity_edges,
            include_weak_gate_card=include_weak_gate_card,
            reader_profile=reader_profile,
        )

        packet = {
            "query": {
                "query_id": query["query_id"],
                "text": query["query"],
                "entity": query["entity"],
                "slot": query["slot"],
                "needs_current": bool(query.get("needs_current", True)),
                "query_intent": query_intent,
                "as_of": query.get("as_of"),
                "risk_profile": risk_profile,
                "reader_profile": reader_profile,
                "scope": query_scope,
                "max_age_days": max_age_days,
                "min_source_confidence": min_source_confidence,
                "min_supporting_count": min_supporting_count,
                "source_policy": {
                    name: sorted(values)
                    for name, values in source_policy.items()
                    if values
                },
                "condition": query.get("condition") or query.get("required_condition"),
            },
            "context_control_policy": context_policy,
            "compact_validity_packet": {
                "current_evidence": [
                    self._evidence_view(record, retrieval_role="current_support")
                    for record in current
                ],
                "supporting_evidence": [
                    self._evidence_view(record, retrieval_role="supporting_duplicate")
                    for record in supporting
                ],
                "historical_evidence": [
                    self._evidence_view(
                        record,
                        retrieval_role="historical_evidence",
                        retrieval_reason=(
                            "archive evidence admitted for historical/timeline/audit query; "
                            "not current-state support unless separately listed as current_evidence"
                        ),
                    )
                    for record in historical
                ],
                "stale_or_blocked_evidence": [
                    self._evidence_view(
                        record,
                        retrieval_role=self._blocked_retrieval_role(
                            record,
                            not_yet_valid_ids,
                            expired_ids,
                            revoked_ids,
                            stale_by_age_ids,
                            below_query_confidence_ids,
                            insufficient_support_ids,
                            source_policy_mismatch_ids,
                            condition_mismatch_ids,
                        ),
                        retrieval_reason=self._blocked_retrieval_reason(
                            record,
                            not_yet_valid_ids,
                            expired_ids,
                            revoked_ids,
                            stale_by_age_ids,
                            below_query_confidence_ids,
                            insufficient_support_ids,
                            source_policy_mismatch_ids,
                            condition_mismatch_ids,
                        ),
                    )
                    for record in stale
                ],
                "excluded_memory_summary": [self._evidence_view(record) for record in excluded],
                "validity_edges": edges,
            },
            "retrieval_diagnostics": retrieval_diagnostics,
            "expected_read_time_decision": self._expected_decision(current, excluded),
        }
        if include_weak_gate_card:
            packet["weak_conservative_gate_card"] = self._weak_gate_card(
                query=query,
                current=current,
                stale=stale,
                supporting=supporting,
                excluded=excluded,
            )
        return apply_packet_char_budget(packet, max_packet_chars)

    def _select_records(
        self, records: list[MemoryRecord], limit: int
    ) -> list[MemoryRecord]:
        if limit == 0:
            return []
        return sorted(
            records,
            key=lambda record: (
                record.observed_at,
                record.source_confidence,
                record.memory_id,
            ),
            reverse=True,
        )[:limit]

    def _dedupe_records(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        out: list[MemoryRecord] = []
        seen: set[str] = set()
        for record in records:
            if record.memory_id in seen:
                continue
            seen.add(record.memory_id)
            out.append(record)
        return out

    def _retrieval_diagnostics(
        self,
        *,
        related: list[MemoryRecord],
        current_candidates: list[MemoryRecord],
        current: list[MemoryRecord],
        supporting: list[MemoryRecord],
        stale: list[MemoryRecord],
        excluded: list[MemoryRecord],
        not_yet_valid_ids: set[str],
        expired_ids: set[str],
        revoked_ids: set[str],
        stale_by_age_ids: set[str],
        below_query_confidence_ids: set[str],
        insufficient_support_ids: set[str],
        source_policy_mismatch_ids: set[str],
        scope_mismatch_ids: set[str],
        condition_mismatch_ids: set[str],
        blocked_ids: set[str],
    ) -> dict[str, Any]:
        return {
            "related_records_total": len(related),
            "scope_mismatch_records_total": len(scope_mismatch_ids),
            "eligible_current_candidates_total": len(current_candidates),
            "selected_counts": {
                "current_evidence": len(current),
                "supporting_evidence": len(supporting),
                "stale_or_blocked_evidence": len(stale),
                "excluded_memory_summary": len(excluded),
            },
            "blocked_counts": {
                "future_evidence": len(not_yet_valid_ids),
                "expired_contrast": len(expired_ids),
                "revoked_contrast": len(revoked_ids),
                "stale_by_age": len(stale_by_age_ids),
                "below_query_confidence": len(below_query_confidence_ids),
                "insufficient_support": len(insufficient_support_ids),
                "source_policy_mismatch": len(source_policy_mismatch_ids),
                "scope_mismatch": len(scope_mismatch_ids),
                "condition_mismatch": len(condition_mismatch_ids),
                "blocked_total_unique": len(blocked_ids),
            },
            "related_current_status_counts": self._count_by(related, "current_status"),
            "related_evidence_role_counts": self._count_by(related, "evidence_role"),
            "validity_marker_records_total": sum(
                1 for record in related if record.evidence_role == "validity_marker"
            ),
            "revoked_records_total": sum(
                1 for record in related if record.current_status == "revoked"
            ),
        }

    def _count_by(self, records: list[MemoryRecord], attribute: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in records:
            value = str(getattr(record, attribute))
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def _current_candidates_for_query(
        self,
        *,
        related: list[MemoryRecord],
        blocked_ids: set[str],
        as_of: datetime | None,
    ) -> list[MemoryRecord]:
        return [
            record
            for record in related
            if record.memory_id not in blocked_ids
            and (
                record.current_status == "current"
                if as_of is None
                else record.evidence_role in {"current_support", "stale_contrast"}
            )
        ]

    def _is_expired_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        return as_of is not None and record.valid_until is not None and as_of > record.valid_until

    def _is_revoked_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        marker_ids = record.links.get("invalidated_by", [])
        if not marker_ids:
            return False
        if as_of is None:
            return record.current_status == "revoked"
        for marker_id in marker_ids:
            marker = self.records.get(marker_id)
            if marker is not None and marker.observed_at <= as_of:
                return True
        return False

    def _is_stale_by_age_for_query(
        self,
        record: MemoryRecord,
        as_of: datetime | None,
        max_age_days: float | None,
    ) -> bool:
        if as_of is None or max_age_days is None:
            return False
        return record.observed_at < as_of - timedelta(days=max_age_days)

    def _query_risk_profile(self, query: dict[str, Any]) -> str:
        risk_profile = norm(str(query.get("risk_profile") or query.get("validity_profile") or "default"))
        if risk_profile not in RISK_PROFILE_DEFAULTS:
            known = ", ".join(sorted(RISK_PROFILE_DEFAULTS))
            raise ValueError(f"Unknown risk_profile {risk_profile!r}; expected one of: {known}")
        return risk_profile

    def _query_reader_profile(self, query: dict[str, Any]) -> str:
        reader_profile = norm(str(query.get("reader_profile") or "default"))
        if reader_profile not in READER_PROFILES:
            known = ", ".join(sorted(READER_PROFILES))
            raise ValueError(
                f"Unknown reader_profile {reader_profile!r}; expected one of: {known}"
            )
        return reader_profile

    def _reader_profile_contract(self, reader_profile: str) -> str:
        if reader_profile == "dim3_actionable":
            return (
                "For actionable current-state questions, first reject any stale embedded "
                "premise, then answer from admitted current evidence when it exists."
            )
        if reader_profile == "weak_conservative":
            return (
                "Use a simpler premise gate for weaker models: compare the embedded "
                "premise value against current and stale evidence before answering."
            )
        if reader_profile == "strong_graph_lite":
            return (
                "Use compact packet plus validity graph edges for structured admission; "
                "preserve stale evidence only as contrast."
        )
        return "Use the default conservative QVF read-time admission policy."

    def _query_intent(self, query: dict[str, Any]) -> str:
        raw_intent = query.get("query_intent") or query.get("memory_query_intent")
        if raw_intent:
            return norm(str(raw_intent))
        if query.get("as_of"):
            return "current_state"

        text = norm(str(query.get("query", "")))
        timeline_cues = [
            "timeline",
            "change history",
            "history of",
            "changed",
            "evolved",
            "变化",
            "变更",
            "时间线",
            "历程",
        ]
        historical_cues = [
            "previous",
            "previously",
            "before",
            "earlier",
            "past",
            "used to",
            "used-to",
            "last year",
            "last month",
            "when did",
            "what was",
            "where was",
            "who was",
            "以前",
            "之前",
            "过去",
            "曾经",
            "什么时候",
            "当时",
        ]
        audit_cues = ["why did", "audit", "debug", "diagnose", "为什么", "审计", "诊断"]
        current_cues = [
            "current",
            "currently",
            "now",
            "latest",
            "still",
            "right now",
            "as of now",
            "现在",
            "当前",
            "目前",
            "还",
            "最新",
        ]
        if (
            any(cue in text for cue in ("did the", "has the"))
            and ("change" in text or "stayed the same" in text or "stay the same" in text)
        ):
            return "timeline_change"
        if any(cue in text for cue in timeline_cues):
            return "timeline_change"
        if any(cue in text for cue in audit_cues):
            return "validity_audit"
        if any(cue in text for cue in historical_cues):
            return "historical_recall"
        if any(cue in text for cue in current_cues):
            return "current_state"
        if query.get("needs_current") is False:
            return "historical_recall"
        return "current_state"

    def _historical_evidence_for_query(
        self, query_intent: str, stale: list[MemoryRecord]
    ) -> list[MemoryRecord]:
        if query_intent not in {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }:
            return []
        return [
            record
            for record in stale
            if record.evidence_role == "stale_contrast"
            or record.current_status in {"superseded", "revoked"}
        ]

    def _context_control_policy_for_intent(
        self,
        *,
        query_intent: str,
        max_current: int,
        max_supporting: int,
        max_stale: int,
        max_excluded: int,
        max_packet_chars: int | None,
        include_validity_edges: bool,
        include_weak_gate_card: bool,
        reader_profile: str,
    ) -> dict[str, Any]:
        retrieval_budget = {
            "max_current": max_current,
            "max_supporting": max_supporting,
            "max_stale": max_stale,
            "max_excluded": max_excluded,
            "max_packet_chars": max_packet_chars,
            "include_validity_edges": include_validity_edges,
            "include_weak_gate_card": include_weak_gate_card,
        }
        base_do_not_answer = [
            "expired_contrast",
            "revoked_contrast",
            "below_query_confidence",
            "insufficient_support",
            "source_policy_mismatch",
            "scope_mismatch",
            "condition_mismatch",
            "future_evidence",
            "excluded_low_confidence",
            "conflict_candidate",
        ]
        archive_intents = {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }
        if query_intent in archive_intents:
            return {
                "answer_from_roles": [
                    "current_support",
                    "historical_evidence",
                    "supporting_duplicate",
                ],
                "do_not_answer_from_roles": base_do_not_answer,
                "include_stale_evidence_as_contrast": True,
                "include_archive_evidence_as_answer_context": True,
                "archive_policy": (
                    "Historical/archive evidence may answer historical, timeline, "
                    "or audit queries. Do not reinterpret it as the current state unless "
                    "it is also listed as current_evidence."
                ),
                "retrieval_budget": retrieval_budget,
                "reader_contract": (
                    "Use current_evidence for present-state claims. For historical, "
                    "timeline, or audit queries, historical_evidence is admissible answer "
                    "context and should be labeled as historical or superseded when relevant."
                ),
                "reader_profile_contract": self._reader_profile_contract(reader_profile),
            }
        return {
            "answer_from_roles": ["current_support"],
            "do_not_answer_from_roles": [
                "stale_contrast",
                "stale_by_age",
            ]
            + base_do_not_answer,
            "include_stale_evidence_as_contrast": True,
            "include_archive_evidence_as_answer_context": False,
            "archive_policy": (
                "Archived stale evidence is visible for contrast and provenance, but "
                "must not answer current-state questions."
            ),
            "retrieval_budget": retrieval_budget,
            "reader_contract": (
                "Answer only from current_support if present. Use stale_contrast "
                "to reject stale premises, not as answer evidence. If no current "
                "support exists, return unknown_current_state."
            ),
            "reader_profile_contract": self._reader_profile_contract(reader_profile),
        }

    def _profile_default(self, risk_profile: str, field: str) -> Any:
        return RISK_PROFILE_DEFAULTS[risk_profile][field]

    def _query_max_age_days(
        self, query: dict[str, Any], risk_profile: str
    ) -> float | None:
        value = (
            query.get("max_age_days")
            if query.get("max_age_days") is not None
            else query.get("freshness_window_days")
        )
        if value is None:
            value = self._profile_default(risk_profile, "max_age_days")
        if value is None:
            return None
        max_age_days = float(value)
        if max_age_days < 0:
            raise ValueError("max_age_days/freshness_window_days must be >= 0")
        return max_age_days

    def _query_min_source_confidence(
        self, query: dict[str, Any], risk_profile: str
    ) -> float | None:
        value = (
            query.get("min_source_confidence")
            if query.get("min_source_confidence") is not None
            else query.get("required_source_confidence")
        )
        if value is None:
            value = self._profile_default(risk_profile, "min_source_confidence")
        if value is None:
            return None
        min_source_confidence = float(value)
        if not 0 <= min_source_confidence <= 1:
            raise ValueError("min_source_confidence/required_source_confidence must be in [0, 1]")
        return min_source_confidence

    def _query_min_supporting_count(
        self, query: dict[str, Any], risk_profile: str
    ) -> int:
        value = (
            query.get("min_supporting_count")
            if query.get("min_supporting_count") is not None
            else query.get("required_supporting_count")
        )
        if value is None:
            value = self._profile_default(risk_profile, "min_supporting_count")
        min_supporting_count = int(value)
        if min_supporting_count < 0:
            raise ValueError("min_supporting_count/required_supporting_count must be >= 0")
        return min_supporting_count

    def _query_source_policy(self, query: dict[str, Any]) -> dict[str, set[str]]:
        return {
            "allowed_source_types": self._normalized_query_set(
                query.get("allowed_source_types") or query.get("required_source_types")
            ),
            "blocked_source_types": self._normalized_query_set(
                query.get("blocked_source_types") or query.get("excluded_source_types")
            ),
            "allowed_source_ids": self._normalized_query_set(
                query.get("allowed_source_ids") or query.get("required_source_ids")
            ),
            "blocked_source_ids": self._normalized_query_set(
                query.get("blocked_source_ids") or query.get("excluded_source_ids")
            ),
        }

    def _query_scope(self, query: dict[str, Any]) -> dict[str, str]:
        raw_scope = query.get("scope", {}) or {}
        return {
            "namespace": norm(str(raw_scope.get("namespace") or query.get("namespace") or "")),
            "tenant_id": norm(str(raw_scope.get("tenant_id") or query.get("tenant_id") or "")),
            "user_id": norm(str(raw_scope.get("user_id") or query.get("user_id") or "")),
        }

    def _scope_matches_query(
        self, record: MemoryRecord, query_scope: dict[str, str]
    ) -> bool:
        record_scope = {
            name: norm(value) for name, value in record.scope.items()
        }
        for name in ["namespace", "tenant_id", "user_id"]:
            if record_scope[name] or query_scope[name]:
                if record_scope[name] != query_scope[name]:
                    return False
        return True

    def _normalized_query_set(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = [value]
        return {norm(str(item)) for item in values if str(item).strip()}

    def _violates_source_policy(
        self, record: MemoryRecord, source_policy: dict[str, set[str]]
    ) -> bool:
        source_type = norm(record.source_type)
        source_id = norm(record.source_id)
        allowed_types = source_policy["allowed_source_types"]
        blocked_types = source_policy["blocked_source_types"]
        allowed_ids = source_policy["allowed_source_ids"]
        blocked_ids = source_policy["blocked_source_ids"]
        return (
            (bool(allowed_types) and source_type not in allowed_types)
            or (bool(blocked_types) and source_type in blocked_types)
            or (bool(allowed_ids) and source_id not in allowed_ids)
            or (bool(blocked_ids) and source_id in blocked_ids)
        )

    def _support_count_for_record(
        self,
        record: MemoryRecord,
        related: list[MemoryRecord],
        blocked_ids: set[str],
    ) -> int:
        return sum(
            1
            for candidate in related
            if candidate.memory_id not in blocked_ids
            and candidate.evidence_role == "supporting_duplicate"
            and (
                record.memory_id in candidate.links.get("supports", [])
                or norm(candidate.value) == norm(record.value)
            )
        )

    def _is_below_query_confidence(
        self, record: MemoryRecord, min_source_confidence: float | None
    ) -> bool:
        return (
            min_source_confidence is not None
            and record.source_confidence < min_source_confidence
        )

    def _is_not_yet_valid_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        return as_of is not None and as_of < record.valid_from

    def _condition_matches_query(
        self, record: MemoryRecord, query: dict[str, Any]
    ) -> bool:
        condition = record.payload.get("condition")
        if not condition:
            return True
        normalized_condition = norm(str(condition))
        query_condition = query.get("condition") or query.get("required_condition")
        if query_condition:
            normalized_query_condition = norm(str(query_condition))
            return (
                normalized_condition == normalized_query_condition
                or normalized_condition in normalized_query_condition
                or normalized_query_condition in normalized_condition
            )
        return normalized_condition in norm(str(query.get("query", "")))

    def _blocked_retrieval_role(
        self,
        record: MemoryRecord,
        not_yet_valid_ids: set[str],
        expired_ids: set[str],
        revoked_ids: set[str],
        stale_by_age_ids: set[str],
        below_query_confidence_ids: set[str],
        insufficient_support_ids: set[str],
        source_policy_mismatch_ids: set[str],
        condition_mismatch_ids: set[str],
    ) -> str:
        if record.memory_id in not_yet_valid_ids:
            return "future_evidence"
        if record.memory_id in expired_ids:
            return "expired_contrast"
        if record.memory_id in revoked_ids:
            return "revoked_contrast"
        if record.memory_id in stale_by_age_ids:
            return "stale_by_age"
        if record.memory_id in below_query_confidence_ids:
            return "below_query_confidence"
        if record.memory_id in insufficient_support_ids:
            return "insufficient_support"
        if record.memory_id in source_policy_mismatch_ids:
            return "source_policy_mismatch"
        if record.evidence_role == "validity_marker":
            return "validity_marker"
        if record.memory_id in condition_mismatch_ids:
            return "condition_mismatch"
        return "stale_contrast"

    def _blocked_retrieval_reason(
        self,
        record: MemoryRecord,
        not_yet_valid_ids: set[str],
        expired_ids: set[str],
        revoked_ids: set[str],
        stale_by_age_ids: set[str],
        below_query_confidence_ids: set[str],
        insufficient_support_ids: set[str],
        source_policy_mismatch_ids: set[str],
        condition_mismatch_ids: set[str],
    ) -> str:
        if record.memory_id in not_yet_valid_ids:
            return "valid_from is after query as_of"
        if record.memory_id in expired_ids:
            return "valid_until is before query as_of"
        if record.memory_id in revoked_ids:
            return "revoked by write-time validity marker before query as_of"
        if record.memory_id in stale_by_age_ids:
            return "observed_at is older than query max_age_days"
        if record.memory_id in below_query_confidence_ids:
            return "source_confidence is below query min_source_confidence"
        if record.memory_id in insufficient_support_ids:
            return "supporting duplicate count is below query min_supporting_count"
        if record.memory_id in source_policy_mismatch_ids:
            return "source does not satisfy query source policy"
        if record.evidence_role == "validity_marker":
            return record.admission_reason
        if record.memory_id in condition_mismatch_ids:
            return "memory condition does not match query condition"
        return record.admission_reason

    def _validity_edges(
        self, selected_records: list[MemoryRecord], selected_ids: set[str]
    ) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        for record in selected_records:
            for edge_type in [
                "supersedes",
                "superseded_by",
                "contradicts",
                "supports",
                "invalidates",
                "invalidated_by",
            ]:
                for target in record.links.get(edge_type, []):
                    if target in selected_ids:
                        edges.append(
                            {
                                "source": record.memory_id,
                                "target": target,
                                "type": edge_type,
                            }
                        )
        return sorted(
            edges, key=lambda edge: (edge["source"], edge["target"], edge["type"])
        )

    def _expected_decision(
        self, current: list[MemoryRecord], excluded: list[MemoryRecord]
    ) -> str:
        if current:
            return "ADMIT_CURRENT"
        if excluded:
            return "UNKNOWN_CURRENT"
        return "UNKNOWN_CURRENT"

    def _weak_gate_card(
        self,
        *,
        query: dict[str, Any],
        current: list[MemoryRecord],
        stale: list[MemoryRecord],
        supporting: list[MemoryRecord],
        excluded: list[MemoryRecord],
    ) -> dict[str, Any]:
        premise_value = query.get("embedded_premise_value")
        reader_profile = str(query.get("reader_profile") or "default")
        current_values = {norm(record.value) for record in current}
        stale_values = {norm(record.value) for record in stale}

        if premise_value and current:
            normalized_premise = norm(str(premise_value))
            if normalized_premise in current_values:
                expected_gate_decision = "ADMIT_CURRENT"
            elif normalized_premise in stale_values:
                expected_gate_decision = "REJECT_STALE_PREMISE"
            else:
                expected_gate_decision = "UNKNOWN_CURRENT"
        elif current:
            expected_gate_decision = "ADMIT_CURRENT"
        elif premise_value and norm(str(premise_value)) in stale_values:
            expected_gate_decision = "REJECT_STALE_PREMISE"
        elif excluded:
            expected_gate_decision = "UNKNOWN_CURRENT"
        else:
            expected_gate_decision = "UNKNOWN_CURRENT"

        decision_rules = [
            "ADMIT_CURRENT only if current_candidate_evidence directly supports the premise.",
            "REJECT_STALE_PREMISE if stale_or_blocked_evidence supports the premise but current_candidate_evidence differs.",
            "UNKNOWN_CURRENT if evidence is missing, excluded, or ambiguous.",
            "When rejecting or unknown, correct the premise boundary instead of answering from stale evidence.",
        ]
        if reader_profile == "weak_conservative":
            decision_rules.insert(
                0,
                "For weak readers, compare embedded_premise_value to evidence values first; if current evidence differs from the premise, do not ADMIT_CURRENT.",
            )
        if reader_profile == "dim3_actionable":
            decision_rules.append(
                "For actionable questions, after rejecting a stale premise, use current_candidate_evidence to produce a current-state action if it exists."
            )

        return {
            "adapter": "weak_conservative_gate_v0.1",
            "purpose": (
                "Low-burden stale-premise gate for weaker readers; use before "
                "free-form answering when the query embeds a current/still/since premise."
            ),
            "query": {
                "query_id": query["query_id"],
                "text": query["query"],
                "entity": query["entity"],
                "slot": query["slot"],
                "needs_current": bool(query.get("needs_current", True)),
                "embedded_premise_value": premise_value,
                "reader_profile": reader_profile,
            },
            "decision_rules": decision_rules,
            "current_candidate_evidence": [
                self._gate_evidence_view(record) for record in current + supporting
            ],
            "stale_or_blocked_evidence": [
                self._gate_evidence_view(record) for record in stale
            ],
            "excluded_evidence": [
                self._gate_evidence_view(record) for record in excluded
            ],
            "expected_gate_decision": expected_gate_decision,
            "reader_output_schema": {
                "decision": "ADMIT_CURRENT | REJECT_STALE_PREMISE | UNKNOWN_CURRENT",
                "support": "memory_id or empty",
                "blocker": "memory_id or empty",
                "final_answer": "concise answer",
            },
        }

    def _evidence_view(
        self,
        record: MemoryRecord,
        *,
        retrieval_role: str | None = None,
        retrieval_reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "memory_id": record.memory_id,
            "claim": record.payload["claim"],
            "value": record.value,
            "observed_at": record.payload["observed_at"],
            "valid_until": record.payload.get("valid_until"),
            "condition": record.payload.get("condition"),
            "scope": record.scope,
            "source_id": record.source_id,
            "source_type": record.source_type,
            "source_span": record.payload.get("source", {}).get("source_span", ""),
            "source_turn_ids": record.payload.get("source", {}).get("source_turn_ids", []),
            "source_confidence": record.source_confidence,
            "admission_status": record.admission_status,
            "current_status": record.current_status,
            "evidence_role": record.evidence_role,
            "retrieval_role": retrieval_role or record.evidence_role,
            "retrieval_reason": retrieval_reason or record.admission_reason,
            "reason": record.admission_reason,
        }

    def _gate_evidence_view(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "memory_id": record.memory_id,
            "value": record.value,
            "claim": record.payload["claim"],
            "observed_at": record.payload["observed_at"],
            "valid_until": record.payload.get("valid_until"),
            "scope": record.scope,
            "source_id": record.source_id,
            "source_type": record.source_type,
            "evidence_role": record.evidence_role,
            "current_status": record.current_status,
        }

    def _log(self, record: MemoryRecord) -> None:
        self.admission_log.append(
            {
                "memory_id": record.memory_id,
                "entity": record.entity,
                "slot": record.slot,
                "value": record.value,
                "observed_at": record.payload["observed_at"],
                "source_confidence": f"{record.source_confidence:.2f}",
                "admission_status": record.admission_status,
                "current_status": record.current_status,
                "evidence_role": record.evidence_role,
                "reason": record.admission_reason,
            }
        )

    def export_memory_store(self) -> list[dict[str, Any]]:
        return [
            self.records[memory_id].to_public_dict()
            for memory_id in sorted(self.records)
        ]


def load_memory_store_jsonl(
    path: Path,
    *,
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> ValidityAwareMemoryStore:
    return ValidityAwareMemoryStore.from_exported_records(
        load_jsonl(path),
        low_confidence_threshold=low_confidence_threshold,
    )


__all__ = [
    "MemoryRecord",
    "ValidityAwareMemoryStore",
    "load_memory_store_jsonl",
    "validate_memory_batch",
    "validate_memory_payload",
]
