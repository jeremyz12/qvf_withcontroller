"""Schema of the Query-Conditioned Validity Map.

These Pydantic models define the structured output contract of the Semantic
Adapter (see qvf/prompts.py, sections 2-8 of the system prompt). They are also
passed to the Claude API as the structured-output schema, so the adapter's JSON
is validated at the API layer.

Design notes:
- Enums mirror the label vocabularies in the adapter spec exactly.
- Confidence values are diagnostic estimates in [0, 1]; numeric range
  constraints are validated client-side (the API strips them).
- Every claim/relation must cite supplied memory IDs; this is enforced softly
  by `ValidityMap.validate_references` (the adapter may cite IDs we did not
  supply if the backend model hallucinates -- we surface that as a warning
  rather than dropping data).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Label vocabularies (spec sections 4-7)
# ---------------------------------------------------------------------------

class TemporalScope(str, Enum):
    """What temporal scope the *query* asks about (spec section 2)."""

    CURRENT_STATE = "CURRENT_STATE"
    HISTORICAL_STATE = "HISTORICAL_STATE"
    STATE_AT_SPECIFIED_TIME = "STATE_AT_SPECIFIED_TIME"
    CHANGE_OVER_TIME = "CHANGE_OVER_TIME"
    TIME_INSENSITIVE = "TIME_INSENSITIVE"
    UNKNOWN = "UNKNOWN"


class RelationLabel(str, Enum):
    """Semantic relation between two atomic claims (spec section 4)."""

    EQUIVALENT = "EQUIVALENT"
    SUPPORTS = "SUPPORTS"
    COMPLEMENTS = "COMPLEMENTS"
    COEXISTS = "COEXISTS"
    CONDITIONALLY_COMPATIBLE = "CONDITIONALLY_COMPATIBLE"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    UNRELATED = "UNRELATED"
    UNKNOWN = "UNKNOWN"


class ApplicabilityLabel(str, Enum):
    """Query-conditioned applicability of a claim (spec section 5)."""

    APPLICABLE = "APPLICABLE"
    PARTIALLY_APPLICABLE = "PARTIALLY_APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class TemporalLabel(str, Enum):
    """Query-conditioned temporal status of a claim (spec section 5)."""

    CURRENT_FOR_QUERY = "CURRENT_FOR_QUERY"
    HISTORICAL_FOR_QUERY = "HISTORICAL_FOR_QUERY"
    SUPERSEDED_FOR_QUERY = "SUPERSEDED_FOR_QUERY"
    FUTURE_OR_NOT_YET_VALID = "FUTURE_OR_NOT_YET_VALID"
    TIME_INSENSITIVE = "TIME_INSENSITIVE"
    UNKNOWN = "UNKNOWN"


class MemoryRole(str, Enum):
    """Query-conditioned role of a claim/memory (spec section 6)."""

    DIRECT_SUPPORT = "DIRECT_SUPPORT"
    CORROBORATION = "CORROBORATION"
    UPDATE = "UPDATE"
    CONTRAST = "CONTRAST"
    QUALIFIER = "QUALIFIER"
    BACKGROUND = "BACKGROUND"
    DISTRACTOR = "DISTRACTOR"
    UNRESOLVED = "UNRESOLVED"


class Sufficiency(str, Enum):
    """Sufficiency of the retrieved evidence set for the query (spec section 7)."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    AMBIGUOUS = "AMBIGUOUS"


class RiskFlag(str, Enum):
    """Risk flags over the retrieved set (spec section 7)."""

    TEMPORAL_AMBIGUITY = "TEMPORAL_AMBIGUITY"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    ENTITY_ATTACHMENT_UNCERTAINTY = "ENTITY_ATTACHMENT_UNCERTAINTY"
    CONDITION_LOSS_RISK = "CONDITION_LOSS_RISK"
    MISSING_CURRENT_STATE = "MISSING_CURRENT_STATE"
    MISSING_HISTORICAL_STATE = "MISSING_HISTORICAL_STATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNTRUSTED_OR_MISSING_METADATA = "UNTRUSTED_OR_MISSING_METADATA"
    POSSIBLE_PROMPT_INJECTION = "POSSIBLE_PROMPT_INJECTION"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# Structural models
# ---------------------------------------------------------------------------

class QueryAnalysis(BaseModel):
    """Grounding of what evidence the query actually requires (spec section 2)."""

    target_entities: List[str] = Field(
        description="Entities the query is about (people, places, objects, events)."
    )
    target_attributes: List[str] = Field(
        description="Attributes or events of those entities the query asks for."
    )
    temporal_scope: TemporalScope = Field(
        description="Which temporal scope the query requests."
    )
    specified_time: Optional[str] = Field(
        default=None,
        description=(
            "The explicit time referenced by the query, if any, as stated or "
            "normalized (e.g. '2023-05', 'last May'). Null if none."
        ),
    )
    explicit_conditions: List[str] = Field(
        default_factory=list,
        description="Explicit conditions or qualifiers the query imposes.",
    )
    comparison_required: bool = Field(
        description="Whether the query requires comparing multiple facts or states."
    )


class AtomicClaim(BaseModel):
    """A minimal atomic claim extracted from one retrieved memory (spec section 3)."""

    claim_id: str = Field(description="Unique claim identifier, e.g. 'c1', 'c2'.")
    memory_id: str = Field(
        description="ID of the supplied memory this claim was extracted from."
    )
    supporting_span: str = Field(
        description="Short exact span copied from the memory content that supports the claim."
    )
    normalized_claim: str = Field(
        description="The claim normalized into a clear declarative sentence, preserving conditional qualifiers."
    )
    subject: str = Field(description="Subject entity of the claim.")
    attribute: str = Field(description="Attribute, relation, or event type.")
    value: str = Field(description="Value or object of the attribute/relation.")
    condition: Optional[str] = Field(
        default=None,
        description="Conditional qualifier (only when / except / if / usually ...), null if unconditional.",
    )
    event_time: Optional[str] = Field(
        default=None,
        description="Time the described event/state holds, ONLY if explicitly available. Null otherwise.",
    )
    memory_creation_time: Optional[str] = Field(
        default=None,
        description="Creation/recording time of the source memory from its metadata, if available.",
    )
    is_inference: bool = Field(
        description="False if the claim is explicitly stated; true if it is a semantic inference from the memory."
    )
    applicability: ApplicabilityLabel = Field(
        description="Query-conditioned applicability of this claim."
    )
    temporal_label: TemporalLabel = Field(
        description="Query-conditioned temporal status of this claim."
    )
    roles: List[MemoryRole] = Field(
        description="One or more query-conditioned roles of this claim."
    )
    confidence: float = Field(
        description="Diagnostic confidence in [0,1] for the extraction and labeling of this claim."
    )
    rationale: Optional[str] = Field(
        default=None,
        description="One short sentence explaining the applicability/temporal labeling, if non-obvious.",
    )


class ClaimRelation(BaseModel):
    """Semantic relation between two extracted claims (spec section 4)."""

    source_claim_id: str = Field(description="claim_id of the source claim.")
    target_claim_id: str = Field(description="claim_id of the target claim.")
    relation: RelationLabel = Field(description="Relation label from the closed vocabulary.")
    rationale: str = Field(
        description="One short sentence justifying the relation, citing conditions/times when relevant."
    )
    confidence: float = Field(
        description="Diagnostic confidence in [0,1] for this relation."
    )


class ValidityMap(BaseModel):
    """The full Query-Conditioned Validity Map (spec section 9 output contract)."""

    query_analysis: QueryAnalysis
    claims: List[AtomicClaim] = Field(
        description="Atomic claims extracted from the supplied memories only."
    )
    relations: List[ClaimRelation] = Field(
        description="Pairwise semantic relations between claims that matter for the query. Omit UNRELATED pairs unless informative."
    )
    sufficiency: Sufficiency = Field(
        description="Whether the retrieved set suffices to answer the query."
    )
    risk_flags: List[RiskFlag] = Field(
        description="Zero or more risk flags; use ['NONE'] when no risk applies."
    )
    notes: Optional[str] = Field(
        default=None,
        description="At most two sentences of diagnostic notes. Never an answer to the query.",
    )

    # ------------------------------------------------------------------
    # Soft validation helpers (not enforced by the API schema)
    # ------------------------------------------------------------------

    def validate_references(self, memory_ids: List[str]) -> List[str]:
        """Return a list of warning strings for citation violations.

        Checks the closed-evidence-boundary rule: every claim must cite a
        supplied memory ID, and every relation must reference extracted claims.
        """
        warnings: List[str] = []
        known_mem = set(memory_ids)
        known_claims = {c.claim_id for c in self.claims}
        for c in self.claims:
            if c.memory_id not in known_mem:
                warnings.append(
                    f"claim {c.claim_id} cites unknown memory_id {c.memory_id!r}"
                )
        for r in self.relations:
            if r.source_claim_id not in known_claims:
                warnings.append(
                    f"relation cites unknown source claim {r.source_claim_id!r}"
                )
            if r.target_claim_id not in known_claims:
                warnings.append(
                    f"relation cites unknown target claim {r.target_claim_id!r}"
                )
        return warnings

    def applicable_claims(self) -> List[AtomicClaim]:
        """Claims directly usable for the query."""
        return [
            c
            for c in self.claims
            if c.applicability
            in (ApplicabilityLabel.APPLICABLE, ApplicabilityLabel.PARTIALLY_APPLICABLE)
        ]

    def applicable_memory_ids(self) -> List[str]:
        """Deduplicated memory IDs backing applicable claims, in claim order."""
        seen: List[str] = []
        for c in self.applicable_claims():
            if c.memory_id not in seen:
                seen.append(c.memory_id)
        return seen
