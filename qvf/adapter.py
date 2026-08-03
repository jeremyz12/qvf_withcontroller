"""The Semantic Adapter: (query, memories, metadata) -> ValidityMap.

Backed by the Claude API with structured outputs, so the ValidityMap schema is
enforced at the API layer (client.messages.parse validates against the Pydantic
model). A mock backend produces deterministic maps for pipeline tests without
API access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import anthropic

from qvf import config
from qvf.prompts import SEMANTIC_ADAPTER_SYSTEM_PROMPT, format_adapter_input
from qvf.retrieval import MemoryItem
from qvf.schema import (
    ApplicabilityLabel,
    AtomicClaim,
    MemoryRole,
    QueryAnalysis,
    RiskFlag,
    Sufficiency,
    TemporalLabel,
    TemporalScope,
    ValidityMap,
)

logger = logging.getLogger(__name__)


@dataclass
class AdapterResult:
    validity_map: ValidityMap
    warnings: List[str]
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0


class SemanticAdapter:
    """Runs the QVF Semantic Adapter over one (query, memories) pair."""

    def __init__(
        self,
        model: Optional[str] = None,
        client: Optional[anthropic.Anthropic] = None,
        mock: Optional[bool] = None,
    ):
        self.model = model or config.DEFAULT_ADAPTER_MODEL
        self.mock = config.mock_mode() if mock is None else mock
        self._client = client
        if not self.mock and self._client is None:
            self._client = anthropic.Anthropic()

    def analyze(
        self,
        query: str,
        memories: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> AdapterResult:
        if self.mock:
            vmap = _semantic_adapter_mock_map(query, memories)
            return AdapterResult(validity_map=vmap, warnings=[])

        user_input = format_adapter_input(query, memories, query_date)
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=config.ADAPTER_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SEMANTIC_ADAPTER_SYSTEM_PROMPT,
                    # The spec prompt is shared across every adapter call in an
                    # experiment run — cache it.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_input}],
            output_format=ValidityMap,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Semantic Adapter request was refused by the model")
        vmap: ValidityMap = response.parsed_output
        if vmap is None:
            raise RuntimeError("Structured output parsing returned no ValidityMap")

        warnings = vmap.validate_references([m.memory_id for m in memories])
        for w in warnings:
            logger.warning("ValidityMap reference warning: %s", w)
        return AdapterResult(
            validity_map=vmap,
            warnings=warnings,
            usage_input_tokens=response.usage.input_tokens,
            usage_output_tokens=response.usage.output_tokens,
        )

class FreeTextAnalyst:
    """Prompt-only ablation analyst: same call position as the Semantic
    Adapter, same concerns in the instructions, but unstructured free-text
    output — no schema, no closed vocabulary, no mechanical validation."""

    def __init__(
        self,
        model: Optional[str] = None,
        client: Optional[anthropic.Anthropic] = None,
        mock: Optional[bool] = None,
    ):
        from qvf.prompts import PROMPT_ONLY_ANALYST_SYSTEM_PROMPT

        self.system_prompt = PROMPT_ONLY_ANALYST_SYSTEM_PROMPT
        self.model = model or config.DEFAULT_ADAPTER_MODEL
        self.mock = config.mock_mode() if mock is None else mock
        self._client = client
        if not self.mock and self._client is None:
            self._client = anthropic.Anthropic()

    def analyze(
        self,
        query: str,
        memories: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> "FreeTextAnalysisResult":
        from qvf.prompts import format_prompt_only_analyst_input

        if self.mock:
            return FreeTextAnalysisResult(analysis="[mock analysis]")
        response = self._client.messages.create(
            model=self.model,
            max_tokens=config.ADAPTER_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": self.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": format_prompt_only_analyst_input(
                        query, memories, query_date
                    ),
                }
            ],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Free-text analyst request was refused")
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        return FreeTextAnalysisResult(
            analysis=text,
            usage_input_tokens=response.usage.input_tokens,
            usage_output_tokens=response.usage.output_tokens,
        )


@dataclass
class FreeTextAnalysisResult:
    analysis: str
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0


# ---------------------------------------------------------------------------
# Mock backend for SemanticAdapter: one trivially-applicable claim per memory.
# Lets the full pipeline (retrieval -> adapter -> generation -> eval IO) run
# without API access; it carries no analytical value.
# ---------------------------------------------------------------------------
def _semantic_adapter_mock_map(query: str, memories: List[MemoryItem]) -> ValidityMap:
    claims = []
    for i, m in enumerate(memories, start=1):
        span = m.content[:80]
        claims.append(
            AtomicClaim(
                claim_id=f"c{i}",
                memory_id=m.memory_id,
                supporting_span=span,
                normalized_claim=span,
                subject="UNKNOWN",
                attribute="UNKNOWN",
                value="UNKNOWN",
                condition=None,
                event_time=None,
                memory_creation_time=str(m.metadata.get("session_date"))
                if m.metadata.get("session_date")
                else None,
                is_inference=False,
                applicability=ApplicabilityLabel.UNKNOWN,
                temporal_label=TemporalLabel.UNKNOWN,
                roles=[MemoryRole.UNRESOLVED],
                confidence=0.0,
                rationale="mock backend output",
            )
        )
    return ValidityMap(
        query_analysis=QueryAnalysis(
            target_entities=[],
            target_attributes=[],
            temporal_scope=TemporalScope.UNKNOWN,
            specified_time=None,
            explicit_conditions=[],
            comparison_required=False,
        ),
        claims=claims,
        relations=[],
        sufficiency=Sufficiency.AMBIGUOUS,
        risk_flags=[RiskFlag.UNTRUSTED_OR_MISSING_METADATA],
        notes="Mock adapter output for plumbing tests only.",
    )
