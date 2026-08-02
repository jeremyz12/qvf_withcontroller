from __future__ import annotations

import re
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
from .query_risk_router import (
    _memory_declares_set_cardinality,
    _memory_has_replacement_relation,
    _values_semantically_equivalent,
)
from .semantic_relations import (
    strict_semantic_relation,
    strict_semantic_relation_target_ids,
)
from .temporal_validity import (
    DIRECTED_REPLACEMENT_RELATIONS,
    is_strict_temporal_payload,
    strict_relation_target_ids,
    strict_slot_cardinality,
    strict_temporal_relation,
    strict_temporal_status,
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
        parsed = parse_dt(
            self.payload.get("effective_from")
            or self.payload.get("valid_from")
            or self.payload["observed_at"]
        )
        if parsed is None:
            raise ValueError(
                f"Missing effective_from/valid_from/observed_at for {self.memory_id}"
            )
        return parsed

    @property
    def valid_until(self) -> datetime | None:
        return parse_dt(
            self.payload.get("effective_until") or self.payload.get("valid_until")
        )

    @property
    def uses_strict_temporal_policy(self) -> bool:
        return is_strict_temporal_payload(self.payload)

    @property
    def strict_slot_cardinality(self) -> str:
        return strict_slot_cardinality(self.payload)

    @property
    def strict_temporal_relation(self) -> str:
        return strict_temporal_relation(self.payload)

    @property
    def strict_temporal_status(self) -> str:
        return strict_temporal_status(self.payload)

    @property
    def strict_relation_target_ids(self) -> tuple[str, ...]:
        return strict_relation_target_ids(self.payload)

    @property
    def strict_semantic_relation(self) -> str:
        return strict_semantic_relation(self.payload)

    @property
    def strict_semantic_relation_target_ids(self) -> tuple[str, ...]:
        return strict_semantic_relation_target_ids(self.payload)

    @property
    def is_future_at_observation(self) -> bool:
        if not self.uses_strict_temporal_policy:
            return False
        if self.strict_temporal_status in {"planned", "future"}:
            return True
        effective_from = parse_dt(self.payload.get("effective_from"))
        return effective_from is not None and effective_from > self.observed_at

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

    @property
    def is_additive_set_member(self) -> bool:
        if self.uses_strict_temporal_policy:
            return (
                self.strict_slot_cardinality == "set"
                and self.strict_semantic_relation == "additive_coexistence"
                and self.strict_temporal_relation
                not in DIRECTED_REPLACEMENT_RELATIONS | {"revocation"}
            )
        return _memory_declares_set_cardinality(
            self.payload
        ) and not _memory_has_replacement_relation(self.payload)

    @property
    def current_index_key(self) -> tuple[str, ...]:
        if self.is_additive_set_member:
            return self.scoped_key + (norm(self.value),)
        return self.scoped_key

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
        self.current_by_key: dict[tuple[str, ...], str] = {}
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
            index_key = record.current_index_key
            existing_id = store.current_by_key.get(index_key)
            if existing_id is None:
                store.current_by_key[index_key] = record.memory_id
                continue
            normalized_key = "::".join(index_key)
            raise ValueError(
                "Multiple current records for scoped key "
                f"{normalized_key}: {existing_id}, {record.memory_id}"
            )
        store.validate_integrity()
        return store

    def validate_integrity(self) -> dict[str, int]:
        self._validate_link_targets()
        self._validate_reciprocal_links()

        current_records_by_key: dict[tuple[str, ...], str] = {}
        current_records_by_scope: dict[
            tuple[str, str, str, str, str], list[MemoryRecord]
        ] = {}
        link_edge_count = 0
        for record in self.records.values():
            link_edge_count += sum(len(targets) for targets in record.links.values())
            if record.current_status != "current":
                continue
            index_key = record.current_index_key
            existing_id = current_records_by_key.get(index_key)
            if existing_id is not None and existing_id != record.memory_id:
                normalized_key = "::".join(index_key)
                raise ValueError(
                    "Multiple current records for scoped key "
                    f"{normalized_key}: {existing_id}, {record.memory_id}"
                )
            current_records_by_key[index_key] = record.memory_id
            current_records_by_scope.setdefault(record.scoped_key, []).append(record)
            indexed_id = self.current_by_key.get(index_key)
            if indexed_id != record.memory_id:
                normalized_key = "::".join(index_key)
                raise ValueError(
                    "Current memory missing from current_by_key for scoped key "
                    f"{normalized_key}: expected {record.memory_id}, found {indexed_id}"
                )

        for scoped_key, records in current_records_by_scope.items():
            if len(records) <= 1:
                continue
            normalized_key = "::".join(scoped_key)
            if not all(record.is_additive_set_member for record in records):
                raise ValueError(
                    "Multiple current records for scoped key require additive set cardinality "
                    f"{normalized_key}: {', '.join(record.memory_id for record in records)}"
                )
            for index, record in enumerate(records):
                if any(
                    _values_semantically_equivalent(record.value, other.value)
                    for other in records[index + 1 :]
                ):
                    raise ValueError(
                        "Semantically equivalent set members cannot both be current for scoped key "
                        f"{normalized_key}"
                    )

        for scoped_key, memory_id in self.current_by_key.items():
            record = self.records.get(memory_id)
            normalized_key = "::".join(scoped_key)
            if record is None:
                raise ValueError(
                    "current_by_key points to missing memory for scoped key "
                    f"{normalized_key}: {memory_id}"
                )
            if record.current_index_key != scoped_key:
                raise ValueError(
                    "current_by_key scoped key mismatch for "
                    f"{memory_id}: indexed {normalized_key}, actual {'::'.join(record.current_index_key)}"
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
            return self._admit_validity_marker(record)

        current_records = self._current_records_for_scope(record.scoped_key)
        if norm(str(record.payload.get("operation", ""))) == "activate_condition":
            return self._admit_condition_activation(record, current_records)
        strict_competitors = self._strict_competing_records_for_scope(
            record.scoped_key
        )
        if record.uses_strict_temporal_policy or any(
            candidate.uses_strict_temporal_policy
            for candidate in strict_competitors
        ):
            return self._admit_strict_temporal_record(record, strict_competitors)
        if record.is_additive_set_member and all(
            current.is_additive_set_member for current in current_records
        ):
            equivalent = next(
                (
                    current
                    for current in current_records
                    if _values_semantically_equivalent(current.value, record.value)
                ),
                None,
            )
            if equivalent is not None:
                return self._admit_supporting_record(
                    record,
                    equivalent,
                    reason=(
                        "semantically equivalent value for an additive set member; "
                        "stored as supporting evidence"
                    ),
                )
            return self._admit_current_record(
                record,
                reason=(
                    "additive set-valued evidence admitted as a coexisting current member"
                    if current_records
                    else "first admitted current evidence for additive set-valued entity-slot key"
                ),
            )

        return self._admit_single_value_record(
            record,
            self._legacy_competing_records_for_scope(record.scoped_key),
        )

    def _admit_condition_activation(
        self,
        record: MemoryRecord,
        current_records: list[MemoryRecord],
    ) -> MemoryRecord:
        """Promote an exact-source condition instance to effective current state."""

        activation = record.payload["condition_activation"]
        template_id = str(
            activation.get("condition_template_memory_id", "")
        ).strip()
        for current in current_records:
            same_value = norm(current.value) == norm(record.value)
            record.links["supersedes"].append(current.memory_id)
            current.admission_status = "admit_as_stale_contrast"
            current.current_status = "superseded"
            current.evidence_role = "stale_contrast"
            current.links["superseded_by"].append(record.memory_id)
            if not same_value:
                record.links["contradicts"].append(current.memory_id)
                current.links["contradicts"].append(record.memory_id)
            current.admission_reason = (
                "superseded by exact-source condition activation"
                if current.memory_id == template_id or same_value
                else "superseded by state change produced by exact-source condition activation"
            )
            self.current_by_key.pop(current.current_index_key, None)
        admitted = self._admit_current_record(
            record,
            reason="exact-source condition dependency activated at the trigger event time",
        )
        for current in current_records:
            self._log(current)
        return admitted

    def _current_records_for_scope(
        self, scoped_key: tuple[str, str, str, str, str]
    ) -> list[MemoryRecord]:
        return [
            record
            for record in self.records.values()
            if record.scoped_key == scoped_key and record.current_status == "current"
        ]

    def _strict_competing_records_for_scope(
        self, scoped_key: tuple[str, str, str, str, str]
    ) -> list[MemoryRecord]:
        return [
            record
            for record in self.records.values()
            if record.scoped_key == scoped_key
            and record.current_status in {"current", "conflict", "future"}
        ]

    def _legacy_competing_records_for_scope(
        self, scoped_key: tuple[str, str, str, str, str]
    ) -> list[MemoryRecord]:
        return [
            record
            for record in self.records.values()
            if record.scoped_key == scoped_key
            and record.current_status in {"current", "conflict"}
        ]

    def _admit_current_record(
        self,
        record: MemoryRecord,
        *,
        reason: str,
    ) -> MemoryRecord:
        record.admission_status = "admit_current"
        record.current_status = "current"
        record.evidence_role = "current_support"
        record.admission_reason = reason
        self.current_by_key[record.current_index_key] = record.memory_id
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def _admit_supporting_record(
        self,
        record: MemoryRecord,
        current: MemoryRecord,
        *,
        reason: str,
    ) -> MemoryRecord:
        record.admission_status = "admit_supporting_evidence"
        record.current_status = "supporting"
        record.evidence_role = "supporting_duplicate"
        record.links["supports"].append(current.memory_id)
        current.links["supports"].append(record.memory_id)
        record.admission_reason = reason
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def _admit_strict_temporal_record(
        self,
        record: MemoryRecord,
        competitors: list[MemoryRecord],
    ) -> MemoryRecord:
        """Admit explicit temporal relations without treating recency as replacement."""

        if record.strict_temporal_relation == "revocation":
            record.payload["validity_action"] = "revoke_current"
            record.payload["invalidates_memory_ids"] = list(
                record.strict_relation_target_ids
            )
            return self._admit_validity_marker(record)

        if record.strict_semantic_relation == "equivalent":
            return self._admit_strict_equivalent(record)

        if not competitors:
            if record.is_future_at_observation:
                return self._admit_future_record(
                    record,
                    reason=(
                        "planned/future evidence retained until its explicit effective time; "
                        "not admitted as write-time current"
                    ),
                )
            if (
                record.strict_temporal_relation
                in DIRECTED_REPLACEMENT_RELATIONS
                and record.strict_relation_target_ids
            ):
                return self._admit_strict_conflict(
                    record,
                    [],
                    reason=(
                        "directed temporal relation target is not yet present; "
                        "record retained as unresolved conflict candidate"
                    ),
                )
            return self._admit_current_record(
                record,
                reason=(
                    "only provenance-valid candidate for this scoped entity-slot; "
                    "no replacement inference was required"
                ),
            )

        exact_matches = [
            candidate
            for candidate in competitors
            if norm(candidate.value) == norm(record.value)
        ]
        exact_current = next(
            (
                candidate
                for candidate in exact_matches
                if candidate.current_status == "current"
            ),
            None,
        )
        if exact_current is not None:
            return self._admit_supporting_record(
                record,
                exact_current,
                reason=(
                    "exact normalized value matches current evidence; stored as support "
                    "without semantic-paraphrase inference"
                ),
            )

        if (
            record.is_additive_set_member
            and competitors
            and all(
                candidate.is_additive_set_member
                and candidate.current_status == "current"
                for candidate in competitors
            )
        ):
            return self._admit_current_record(
                record,
                reason=(
                    "explicit set cardinality admits a distinct coexisting current member"
                ),
            )

        incoming_targets = set(record.strict_relation_target_ids)
        incoming_directional = (
            record.strict_temporal_relation in DIRECTED_REPLACEMENT_RELATIONS
            and record.strict_slot_cardinality == "single"
        )
        reverse_replacers = [
            candidate
            for candidate in competitors
            if candidate.strict_temporal_relation
            in DIRECTED_REPLACEMENT_RELATIONS
            and candidate.strict_slot_cardinality == "single"
            and record.memory_id in candidate.strict_relation_target_ids
        ]
        if incoming_directional and reverse_replacers:
            return self._admit_strict_conflict(
                record,
                competitors,
                reason=(
                    "cyclic or bidirectional replacement evidence is unresolved"
                ),
            )
        if len(reverse_replacers) > 1:
            return self._admit_strict_conflict(
                record,
                competitors,
                reason="multiple records claim to replace the same predecessor",
            )

        non_equivalent_ids = {
            candidate.memory_id
            for candidate in competitors
            if norm(candidate.value) != norm(record.value)
        }
        if incoming_directional:
            if non_equivalent_ids and non_equivalent_ids <= incoming_targets:
                return self._admit_strict_replacement(record, competitors)
            return self._admit_strict_conflict(
                record,
                competitors,
                reason=(
                    "directed replacement does not cover every competing value in scope"
                ),
            )

        if reverse_replacers:
            replacer = reverse_replacers[0]
            unrelated = [
                candidate
                for candidate in competitors
                if candidate.memory_id != replacer.memory_id
                and norm(candidate.value) != norm(record.value)
            ]
            if unrelated:
                return self._admit_strict_conflict(
                    record,
                    competitors,
                    reason=(
                        "inverse replacement leaves additional competing values unresolved"
                    ),
                )
            return self._admit_strict_predecessor(record, replacer)

        if (
            not record.is_future_at_observation
            and competitors
            and all(candidate.current_status == "future" for candidate in competitors)
        ):
            return self._admit_current_record(
                record,
                reason=(
                    "effective evidence remains current while unresolved future candidates "
                    "wait for a query-time validity boundary"
                ),
            )
        if record.is_future_at_observation:
            return self._admit_future_record(
                record,
                reason=(
                    "future evidence has no proven replacement direction; retained as "
                    "a non-current candidate"
                ),
            )
        return self._admit_strict_conflict(
            record,
            competitors,
            reason=(
                "distinct values lack explicit equivalence, set coexistence, or a "
                "directed scalar replacement relation"
            ),
        )

    def _admit_strict_equivalent(self, record: MemoryRecord) -> MemoryRecord:
        """Attach one source-backed equivalent expression to its exact target."""

        target_ids = record.strict_semantic_relation_target_ids
        target = self.records.get(target_ids[0]) if len(target_ids) == 1 else None
        if target is None:
            return self._admit_strict_conflict(
                record,
                [],
                reason=(
                    "explicit semantic equivalence target is unavailable; "
                    "record retained as unresolved conflict candidate"
                ),
            )
        if target.scoped_key != record.scoped_key:
            return self._admit_strict_conflict(
                record,
                [],
                reason=(
                    "explicit semantic equivalence target has a different scoped "
                    "entity-slot"
                ),
            )
        return self._admit_supporting_record(
            record,
            target,
            reason=(
                "source-backed semantic equivalence references one exact scoped "
                "memory target; retained as supporting evidence without value rewriting"
            ),
        )

    def _admit_future_record(
        self,
        record: MemoryRecord,
        *,
        reason: str,
    ) -> MemoryRecord:
        record.admission_status = "admit_as_future_candidate"
        record.current_status = "future"
        record.evidence_role = "future_candidate"
        record.admission_reason = reason
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def _admit_strict_replacement(
        self,
        record: MemoryRecord,
        competitors: list[MemoryRecord],
    ) -> MemoryRecord:
        relation = record.strict_temporal_relation
        is_future = record.is_future_at_observation
        for previous in competitors:
            self._link_strict_replacement(record, previous)
            self._derive_predecessor_effective_until(previous, record)
            if is_future:
                previous.admission_reason = (
                    "current until the explicit replacement/correction effective boundary"
                )
            else:
                previous.admission_status = "admit_as_stale_contrast"
                previous.current_status = "superseded"
                previous.evidence_role = "stale_contrast"
                previous.admission_reason = (
                    f"explicit {relation} target retained as historical predecessor"
                )
                self.current_by_key.pop(previous.current_index_key, None)
            self._log(previous)

        if is_future:
            return self._admit_future_record(
                record,
                reason=(
                    f"explicit {relation} relation is planned for its effective time; "
                    "not admitted as write-time current"
                ),
            )
        return self._admit_current_record(
            record,
            reason=(
                f"explicit scalar {relation} relation targets every competing value"
            ),
        )

    def _admit_strict_predecessor(
        self,
        record: MemoryRecord,
        replacer: MemoryRecord,
    ) -> MemoryRecord:
        self._link_strict_replacement(replacer, record)
        self._derive_predecessor_effective_until(record, replacer)
        relation = replacer.strict_temporal_relation
        if replacer.current_status == "future":
            replacer.admission_reason = (
                f"explicit {relation} relation is planned for its effective time; "
                "not admitted as write-time current"
            )
            self._log(replacer)
            return self._admit_current_record(
                record,
                reason=(
                    "current until the explicit replacement/correction effective boundary"
                ),
            )
        if replacer.current_status == "conflict":
            replacer.admission_status = "admit_current"
            replacer.current_status = "current"
            replacer.evidence_role = "current_support"
            self.current_by_key[replacer.current_index_key] = replacer.memory_id
        replacer.admission_reason = (
            f"explicit scalar {relation} relation targets every competing value"
        )
        self._log(replacer)

        record.admission_status = "admit_as_stale_contrast"
        record.current_status = "superseded"
        record.evidence_role = "stale_contrast"
        record.admission_reason = (
            f"explicit {relation} target retained as historical predecessor"
        )
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def _admit_strict_conflict(
        self,
        record: MemoryRecord,
        competitors: list[MemoryRecord],
        *,
        reason: str,
    ) -> MemoryRecord:
        for candidate in competitors:
            if candidate.memory_id not in record.links["contradicts"]:
                record.links["contradicts"].append(candidate.memory_id)
            if record.memory_id not in candidate.links["contradicts"]:
                candidate.links["contradicts"].append(record.memory_id)
            if candidate.current_status == "current":
                self.current_by_key.pop(candidate.current_index_key, None)
            candidate.admission_status = "admit_as_conflict_candidate"
            candidate.current_status = "conflict"
            candidate.evidence_role = "conflict_candidate"
            candidate.admission_reason = reason
            self._log(candidate)
        record.admission_status = "admit_as_conflict_candidate"
        record.current_status = "conflict"
        record.evidence_role = "conflict_candidate"
        record.admission_reason = reason
        self.records[record.memory_id] = record
        self._log(record)
        return record

    def _link_strict_replacement(
        self,
        replacer: MemoryRecord,
        predecessor: MemoryRecord,
    ) -> None:
        for edge_type, source, target in (
            ("supersedes", replacer, predecessor),
            ("superseded_by", predecessor, replacer),
            ("contradicts", replacer, predecessor),
            ("contradicts", predecessor, replacer),
        ):
            if target.memory_id not in source.links[edge_type]:
                source.links[edge_type].append(target.memory_id)

    def _derive_predecessor_effective_until(
        self,
        predecessor: MemoryRecord,
        replacer: MemoryRecord,
    ) -> None:
        boundary = replacer.payload.get("effective_from")
        if not boundary or predecessor.payload.get("effective_until"):
            return
        predecessor.payload["effective_until"] = boundary
        states = predecessor.payload.setdefault("temporal_field_states", {})
        if isinstance(states, dict):
            states["effective_until"] = {
                "status": "derived",
                "value": boundary,
                "origin": "explicit_directed_relation",
                "relation_memory_id": replacer.memory_id,
            }
        derivations = predecessor.payload.setdefault("temporal_derivations", [])
        if isinstance(derivations, list):
            derivations.append(
                {
                    "field": "effective_until",
                    "value": boundary,
                    "origin": "explicit_directed_relation",
                    "relation_memory_id": replacer.memory_id,
                }
            )

    def _admit_single_value_record(
        self,
        record: MemoryRecord,
        competitors: list[MemoryRecord],
    ) -> MemoryRecord:
        if not competitors:
            return self._admit_current_record(
                record,
                reason="first admitted current evidence for entity-slot key",
            )

        equivalent = next(
            (
                candidate
                for candidate in competitors
                if norm(candidate.value) == norm(record.value)
            ),
            None,
        )
        if equivalent is not None:
            return self._admit_supporting_record(
                record,
                equivalent,
                reason="same value as existing scoped memory; stored as support",
            )

        previous = max(
            competitors,
            key=lambda current: (
                current.observed_at,
                current.source_confidence,
                current.memory_id,
            ),
        )
        if record.observed_at < previous.observed_at:
            return self._admit_stale_record(record, previous)

        structured_operation = norm(
            str(record.payload.get("operation") or record.payload.get("update_type") or "")
        )
        has_explicit_replacement_operation = structured_operation in {
            "remove",
            "removed",
            "delete",
            "deleted",
            "replace",
            "replaced",
            "revoke",
            "revoked",
        }
        if (
            record.observed_at == previous.observed_at
            and not has_explicit_replacement_operation
        ):
            return self._admit_strict_conflict(
                record,
                competitors,
                reason=(
                    "equal observed times do not establish a replacement direction; "
                    "distinct values retained as unresolved conflict candidates"
                ),
            )

        for current in competitors:
            record.links["supersedes"].append(current.memory_id)
            record.links["contradicts"].append(current.memory_id)
            current.admission_status = "admit_as_stale_contrast"
            current.current_status = "superseded"
            current.evidence_role = "stale_contrast"
            current.links["superseded_by"].append(record.memory_id)
            current.links["contradicts"].append(record.memory_id)
            current.admission_reason = (
                "superseded by newer conflicting evidence; retained as stale contrast"
            )
            self.current_by_key.pop(current.current_index_key, None)
        admitted = self._admit_current_record(
            record,
            reason=(
                "explicit structured replacement supersedes scoped competitors"
                if has_explicit_replacement_operation
                else "newer conflicting evidence supersedes previous current memory"
            ),
        )
        for current in competitors:
            self._log(current)
        return admitted

    def _admit_stale_record(
        self,
        record: MemoryRecord,
        previous: MemoryRecord,
    ) -> MemoryRecord:
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
        memory_ids = [str(record["memory_id"]) for record in validated_records]
        if len(memory_ids) != len(set(memory_ids)):
            return [self.admit(record) for record in validated_records]
        ordered_records = self._strict_dependency_order(validated_records)
        admitted_by_id = {
            str(record["memory_id"]): self.admit(record)
            for record in ordered_records
        }
        return [admitted_by_id[memory_id] for memory_id in memory_ids]

    def _strict_dependency_order(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Place explicit relation targets before dependants without using timestamps."""

        by_id = {str(record["memory_id"]): record for record in records}
        original_order = {
            str(record["memory_id"]): index for index, record in enumerate(records)
        }
        visiting: set[str] = set()
        visited: set[str] = set()
        ordered: list[dict[str, Any]] = []

        def visit(memory_id: str) -> None:
            if memory_id in visited:
                return
            if memory_id in visiting:
                return
            visiting.add(memory_id)
            record = by_id[memory_id]
            if is_strict_temporal_payload(record):
                targets = sorted(
                    {
                        target_id
                        for target_id in (
                            *strict_relation_target_ids(record),
                            *strict_semantic_relation_target_ids(record),
                        )
                        if target_id in by_id
                    },
                    key=lambda target_id: original_order[target_id],
                )
                for target_id in targets:
                    visit(target_id)
            visiting.remove(memory_id)
            visited.add(memory_id)
            ordered.append(record)

        for record in records:
            visit(str(record["memory_id"]))
        return ordered

    def _admit_validity_marker(
        self, record: MemoryRecord
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
        current_records = self._current_records_for_scope(record.scoped_key)
        current_id = self.current_by_key.get(record.scoped_key)
        if current_id is None and len(current_records) == 1:
            current_id = current_records[0].memory_id
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
        deferred_until_effective = (
            record.uses_strict_temporal_policy and record.is_future_at_observation
        )

        for target_id in target_ids:
            if not target_id:
                continue
            target = self.records[target_id]
            if record.memory_id not in target.links["invalidated_by"]:
                target.links["invalidated_by"].append(record.memory_id)
            if record.memory_id not in target.links["contradicts"]:
                target.links["contradicts"].append(record.memory_id)
            if target.memory_id not in record.links["invalidates"]:
                record.links["invalidates"].append(target.memory_id)
            if target.memory_id not in record.links["contradicts"]:
                record.links["contradicts"].append(target.memory_id)
            if deferred_until_effective:
                target.admission_reason = (
                    "current until the explicit revocation effective boundary"
                )
            else:
                target.admission_status = "revoked_by_validity_marker"
                target.current_status = "revoked"
                target.evidence_role = "stale_contrast"
                target.admission_reason = (
                    "revoked by write-time validity marker; retained as stale contrast"
                )
                if self.current_by_key.get(target.current_index_key) == target.memory_id:
                    del self.current_by_key[target.current_index_key]
            self._log(target)

        if deferred_until_effective and target_ids:
            record.admission_reason = (
                "strict revocation marker retained for its explicit effective boundary; "
                "current evidence is not revoked early"
            )

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

        query_entity = norm(query["entity"])
        query_slots = {
            norm(slot)
            for slot in [query["slot"], *query.get("coordinated_slots", [])]
            if str(slot).strip()
        }
        as_of = parse_dt(query.get("as_of"))
        risk_profile = self._query_risk_profile(query)
        reader_profile = self._query_reader_profile(query)
        query_intent = self._query_intent(query)
        max_age_days = self._query_max_age_days(query, risk_profile)
        min_source_confidence = self._query_min_source_confidence(query, risk_profile)
        min_supporting_count = self._query_min_supporting_count(query, risk_profile)
        source_policy = self._query_source_policy(query)
        query_scope = self._query_scope(query)
        required_evidence_qualifiers = self._normalized_query_set(
            query.get("required_evidence_qualifiers")
        )
        key_related = [
            record
            for record in self.records.values()
            if record.key[0] == query_entity
            and self._slot_matches_query(
                record.key[1],
                query_slots=query_slots,
                query_intent=query_intent,
            )
        ]
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
        evidence_qualifier_mismatch_ids = {
            record.memory_id
            for record in related
            if not self._evidence_qualifiers_match_query(
                record,
                required_evidence_qualifiers,
            )
        }
        pre_conflict_blocked_ids = (
            not_yet_valid_ids
            | expired_ids
            | revoked_ids
            | stale_by_age_ids
            | below_query_confidence_ids
            | source_policy_mismatch_ids
            | condition_mismatch_ids
            | evidence_qualifier_mismatch_ids
        )
        stored_conflict_candidate_ids = {
            record.memory_id
            for record in related
            if record.evidence_role == "conflict_candidate"
            or record.current_status == "conflict"
        }
        temporal_conflict_candidate_ids = (
            self._strict_unresolved_conflict_ids_for_query(
                related=related,
                blocked_ids=pre_conflict_blocked_ids,
            )
        )
        conflict_candidate_ids = (
            stored_conflict_candidate_ids | temporal_conflict_candidate_ids
        )
        base_blocked_ids = pre_conflict_blocked_ids | conflict_candidate_ids
        base_current_candidates = self._current_candidates_for_query(
            related=related,
            blocked_ids=base_blocked_ids,
            as_of=as_of,
        )
        if query_intent in {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }:
            base_current_candidates = [
                record
                for record in base_current_candidates
                if self._slot_temporal_role(record.key[1])[1] != "prior"
            ]
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
            and record.current_status
            in {"current", "supporting", "superseded", "revoked", "conflict", "future"}
        ]
        stale = self._select_records(
            self._dedupe_records(
                [
                    record
                    for record in related
                    if record.evidence_role
                    in {
                        "stale_contrast",
                        "validity_marker",
                        "conflict_candidate",
                        "future_candidate",
                    }
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
        if query_intent in {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }:
            structural_prior = [
                record
                for record in related
                if self._slot_temporal_role(record.key[1])[1] == "prior"
                and record.memory_id not in current_ids
            ]
            historical = self._select_records(
                self._dedupe_records([*historical, *structural_prior]),
                max_stale,
            )

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
            evidence_qualifier_mismatch_ids=evidence_qualifier_mismatch_ids,
            conflict_candidate_ids=conflict_candidate_ids,
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
                "coordinated_slots": list(query.get("coordinated_slots", [])),
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
                "required_evidence_qualifiers": sorted(required_evidence_qualifiers),
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
                            evidence_qualifier_mismatch_ids,
                            conflict_candidate_ids,
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
                            evidence_qualifier_mismatch_ids,
                            conflict_candidate_ids,
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
        if query.get("requested_response_dimensions"):
            packet["query"]["requested_response_dimensions"] = list(
                query["requested_response_dimensions"]
            )
            packet["query"]["response_dimension_state"] = deepcopy(
                query["response_dimension_state"]
            )
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
        evidence_qualifier_mismatch_ids: set[str],
        conflict_candidate_ids: set[str],
        blocked_ids: set[str],
    ) -> dict[str, Any]:
        diagnostics = {
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
                "evidence_qualifier_mismatch": len(
                    evidence_qualifier_mismatch_ids
                ),
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
        if conflict_candidate_ids or any(
            record.uses_strict_temporal_policy for record in related
        ):
            diagnostics["blocked_counts"]["conflict_candidate"] = len(
                conflict_candidate_ids
            )
            diagnostics["conflict_candidate_records_total"] = len(
                conflict_candidate_ids
            )
        return diagnostics

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
                else record.evidence_role
                in {"current_support", "stale_contrast", "future_candidate"}
            )
        ]

    def _is_expired_for_query(
        self, record: MemoryRecord, as_of: datetime | None
    ) -> bool:
        if as_of is None or record.valid_until is None:
            return False
        if record.uses_strict_temporal_policy:
            return as_of >= record.valid_until
        return as_of > record.valid_until

    def _strict_unresolved_conflict_ids_for_query(
        self,
        *,
        related: list[MemoryRecord],
        blocked_ids: set[str],
    ) -> set[str]:
        groups: dict[tuple[str, str, str, str, str], list[MemoryRecord]] = {}
        for record in related:
            if record.memory_id in blocked_ids:
                continue
            if not record.uses_strict_temporal_policy:
                continue
            if record.current_status not in {"current", "future", "conflict"}:
                continue
            groups.setdefault(record.scoped_key, []).append(record)

        conflict_ids: set[str] = set()
        for records in groups.values():
            distinct_values = {norm(record.value) for record in records}
            if len(distinct_values) < 2:
                continue
            if all(record.is_additive_set_member for record in records):
                continue
            resolved_by_direction = False
            record_ids = {record.memory_id for record in records}
            for record in records:
                if (
                    record.strict_temporal_relation
                    in DIRECTED_REPLACEMENT_RELATIONS
                    and record.strict_slot_cardinality == "single"
                    and record_ids - {record.memory_id}
                    <= set(record.strict_relation_target_ids)
                ):
                    resolved_by_direction = True
                    break
            if not resolved_by_direction:
                conflict_ids.update(record_ids)
        return conflict_ids

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
            if marker is None:
                continue
            marker_boundary = (
                marker.valid_from
                if marker.uses_strict_temporal_policy
                else marker.observed_at
            )
            if marker_boundary <= as_of:
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
        if query.get("needs_current") is False:
            return "historical_recall"

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
        return "current_state"

    @staticmethod
    def _slot_temporal_role(value: Any) -> tuple[str, str]:
        normalized = re.sub(
            r"\s+",
            " ",
            re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()),
        ).strip()
        for prefix in ("previous ", "prior ", "former "):
            if normalized.startswith(prefix):
                return normalized[len(prefix) :].strip(), "prior"
        return normalized, "current"

    def _slot_matches_query(
        self,
        record_slot: Any,
        *,
        query_slots: set[str],
        query_intent: str,
    ) -> bool:
        if norm(str(record_slot)) in query_slots:
            return True
        if query_intent not in {
            "historical_recall",
            "timeline_change",
            "conflict_audit",
            "validity_audit",
        }:
            return False
        record_base, record_role = self._slot_temporal_role(record_slot)
        if record_role != "prior":
            return False
        query_bases = {self._slot_temporal_role(slot)[0] for slot in query_slots}
        return bool(record_base and record_base in query_bases)

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
            or bool(record.links.get("invalidated_by"))
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
        if as_of is not None:
            return as_of < record.valid_from
        return (
            record.uses_strict_temporal_policy
            and record.is_future_at_observation
        )

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

    def _evidence_qualifiers_match_query(
        self,
        record: MemoryRecord,
        required_qualifiers: set[str],
    ) -> bool:
        if not required_qualifiers:
            return True
        relation = norm(str(record.payload.get("query_scope_relation") or ""))
        supported = self._normalized_query_set(
            record.payload.get("supported_query_qualifiers")
        )
        return relation == "supported" and required_qualifiers <= supported

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
        evidence_qualifier_mismatch_ids: set[str],
        conflict_candidate_ids: set[str],
    ) -> str:
        if record.memory_id in conflict_candidate_ids:
            return "conflict_candidate"
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
        if record.memory_id in evidence_qualifier_mismatch_ids:
            return "evidence_qualifier_mismatch"
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
        evidence_qualifier_mismatch_ids: set[str],
        conflict_candidate_ids: set[str],
    ) -> str:
        if record.memory_id in conflict_candidate_ids:
            return (
                "distinct values remain unresolved because equivalence, set coexistence, "
                "or a directed scalar replacement relation is not proven"
            )
        if record.memory_id in not_yet_valid_ids:
            return "effective_from/valid_from is after query as_of, or evidence is still planned"
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
        if record.memory_id in evidence_qualifier_mismatch_ids:
            return (
                "memory does not explicitly support every required query evidence qualifier"
            )
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
                "coordinated_slots": list(query.get("coordinated_slots", [])),
                "needs_current": bool(query.get("needs_current", True)),
                "embedded_premise_value": premise_value,
                "reader_profile": reader_profile,
                "required_evidence_qualifiers": sorted(
                    self._normalized_query_set(
                        query.get("required_evidence_qualifiers")
                    )
                ),
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
        out = {
            "memory_id": record.memory_id,
            "claim": record.payload["claim"],
            "value": record.value,
            "observed_at": record.payload["observed_at"],
            "valid_until": record.payload.get("valid_until"),
            "condition": record.payload.get("condition"),
            "query_scope_relation": record.payload.get("query_scope_relation"),
            "supported_query_qualifiers": record.payload.get(
                "supported_query_qualifiers", []
            ),
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
        if "slot_cardinality" in record.payload:
            out["slot_cardinality"] = record.payload.get("slot_cardinality")
        canonical_slot, temporal_role = self._slot_temporal_role(record.slot)
        if temporal_role == "prior":
            out["structural_temporal_role"] = "prior"
            out["canonical_slot"] = canonical_slot
        if record.uses_strict_temporal_policy:
            out.update(
                {
                    "source_time": record.payload.get("source_time"),
                    "event_time": record.payload.get("event_time"),
                    "effective_from": record.payload.get("effective_from"),
                    "effective_until": record.payload.get("effective_until"),
                    "temporal_status": record.payload.get("temporal_status"),
                    "slot_cardinality": record.payload.get("slot_cardinality"),
                    "temporal_relation": record.payload.get("temporal_relation"),
                    "relation_target_memory_ids": list(
                        record.payload.get("relation_target_memory_ids") or []
                    ),
                    "validity_policy": record.payload.get("validity_policy"),
                    "temporal_field_states": deepcopy(
                        record.payload.get("temporal_field_states", {})
                    ),
                    "temporal_semantic_states": deepcopy(
                        record.payload.get("temporal_semantic_states", {})
                    ),
                    "temporal_derivations": deepcopy(
                        record.payload.get("temporal_derivations", [])
                    ),
                }
            )
            if record.strict_semantic_relation != "unresolved":
                out.update(
                    {
                        "semantic_relation": record.strict_semantic_relation,
                        "semantic_relation_target_memory_ids": list(
                            record.strict_semantic_relation_target_ids
                        ),
                        "semantic_relation_state": deepcopy(
                            record.payload.get("semantic_relation_state", {})
                        ),
                    }
                )
        return out

    def _gate_evidence_view(self, record: MemoryRecord) -> dict[str, Any]:
        out = {
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
        if "slot_cardinality" in record.payload:
            out["slot_cardinality"] = record.payload.get("slot_cardinality")
        canonical_slot, temporal_role = self._slot_temporal_role(record.slot)
        if temporal_role == "prior":
            out["structural_temporal_role"] = "prior"
            out["canonical_slot"] = canonical_slot
        if record.uses_strict_temporal_policy:
            out.update(
                {
                    "effective_from": record.payload.get("effective_from"),
                    "effective_until": record.payload.get("effective_until"),
                    "temporal_status": record.payload.get("temporal_status"),
                    "slot_cardinality": record.payload.get("slot_cardinality"),
                    "temporal_relation": record.payload.get("temporal_relation"),
                }
            )
            if record.strict_semantic_relation != "unresolved":
                out.update(
                    {
                        "semantic_relation": record.strict_semantic_relation,
                        "semantic_relation_target_memory_ids": list(
                            record.strict_semantic_relation_target_ids
                        ),
                    }
                )
        return out

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
