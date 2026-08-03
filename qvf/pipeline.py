"""End-to-end pipelines: retrieve -> (QVF) -> generate.

Two conditions share retrieval and generation settings; the only difference is
whether the Semantic Adapter runs and whether the generator is conditioned on
its ValidityMap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from qvf.adapter import FreeTextAnalyst, SemanticAdapter
from qvf.generator import BaselineGenerator, PromptOnlyGenerator, QVFGenerator
from qvf.retrieval import BM25Retriever, MemoryItem
from qvf.schema import ValidityMap


@dataclass
class PipelineResult:
    answer: str
    retrieved_memory_ids: List[str]
    validity_map: Optional[ValidityMap] = None
    analysis_text: Optional[str] = None
    adapter_warnings: List[str] = field(default_factory=list)
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0


class QVFPipeline:
    """retrieve -> Semantic Adapter -> validity-conditioned generation."""

    def __init__(
        self,
        top_k: int = 10,
        adapter: Optional[SemanticAdapter] = None,
        generator: Optional[QVFGenerator] = None,
        mock: Optional[bool] = None,
    ):
        self.top_k = top_k
        self.adapter = adapter or SemanticAdapter(mock=mock)
        self.generator = generator or QVFGenerator(mock=mock)

    def answer(
        self,
        query: str,
        memory_store: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> PipelineResult:
        retriever = BM25Retriever(memory_store)
        retrieved = retriever.retrieve(query, top_k=self.top_k)
        adapter_result = self.adapter.analyze(query, retrieved, query_date)
        gen = self.generator.generate(
            query, retrieved, adapter_result.validity_map, query_date
        )
        return PipelineResult(
            answer=gen.answer,
            retrieved_memory_ids=[m.memory_id for m in retrieved],
            validity_map=adapter_result.validity_map,
            adapter_warnings=adapter_result.warnings,
            usage_input_tokens=adapter_result.usage_input_tokens
            + gen.usage_input_tokens,
            usage_output_tokens=adapter_result.usage_output_tokens
            + gen.usage_output_tokens,
        )


class FilterOnlyPipeline:
    """Ablation: retrieve -> Semantic Adapter -> drop NOT_APPLICABLE memories ->
    vanilla generation.

    The validity map is used only to filter the memory set; the generator never
    sees the map itself. Comparing this against the full QVF condition isolates
    the value of structured explanation over pure filtering.
    """

    def __init__(
        self,
        top_k: int = 10,
        adapter: Optional[SemanticAdapter] = None,
        generator: Optional[BaselineGenerator] = None,
        mock: Optional[bool] = None,
    ):
        self.top_k = top_k
        self.adapter = adapter or SemanticAdapter(mock=mock)
        self.generator = generator or BaselineGenerator(mock=mock)

    def answer(
        self,
        query: str,
        memory_store: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> PipelineResult:
        retriever = BM25Retriever(memory_store)
        retrieved = retriever.retrieve(query, top_k=self.top_k)
        adapter_result = self.adapter.analyze(query, retrieved, query_date)
        keep_ids = set(adapter_result.validity_map.applicable_memory_ids())
        # An empty applicable set is passed through as-is: the generator then
        # sees no evidence and should abstain, which is the honest behavior.
        filtered = [m for m in retrieved if m.memory_id in keep_ids]
        gen = self.generator.generate(query, filtered, query_date)
        return PipelineResult(
            answer=gen.answer,
            retrieved_memory_ids=[m.memory_id for m in filtered],
            validity_map=adapter_result.validity_map,
            adapter_warnings=adapter_result.warnings,
            usage_input_tokens=adapter_result.usage_input_tokens
            + gen.usage_input_tokens,
            usage_output_tokens=adapter_result.usage_output_tokens
            + gen.usage_output_tokens,
        )


class PromptOnlyPipeline:
    """Prompt-only ablation: retrieve -> free-text analyst -> generation.

    Same two-call architecture and model as QVFPipeline; the only difference
    is that the intermediate representation is unstructured prose instead of
    the schema-enforced ValidityMap. If full QVF does not beat this condition,
    the structured schema is not what's doing the work.
    """

    def __init__(
        self,
        top_k: int = 10,
        analyst: Optional[FreeTextAnalyst] = None,
        generator: Optional[PromptOnlyGenerator] = None,
        mock: Optional[bool] = None,
    ):
        self.top_k = top_k
        self.analyst = analyst or FreeTextAnalyst(mock=mock)
        self.generator = generator or PromptOnlyGenerator(mock=mock)

    def answer(
        self,
        query: str,
        memory_store: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> PipelineResult:
        retriever = BM25Retriever(memory_store)
        retrieved = retriever.retrieve(query, top_k=self.top_k)
        analysis = self.analyst.analyze(query, retrieved, query_date)
        gen = self.generator.generate(query, retrieved, analysis.analysis, query_date)
        return PipelineResult(
            answer=gen.answer,
            retrieved_memory_ids=[m.memory_id for m in retrieved],
            analysis_text=analysis.analysis,
            usage_input_tokens=analysis.usage_input_tokens + gen.usage_input_tokens,
            usage_output_tokens=analysis.usage_output_tokens + gen.usage_output_tokens,
        )


class BaselinePipeline:
    """retrieve -> vanilla generation (no QVF)."""

    def __init__(
        self,
        top_k: int = 10,
        generator: Optional[BaselineGenerator] = None,
        mock: Optional[bool] = None,
    ):
        self.top_k = top_k
        self.generator = generator or BaselineGenerator(mock=mock)

    def answer(
        self,
        query: str,
        memory_store: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> PipelineResult:
        retriever = BM25Retriever(memory_store)
        retrieved = retriever.retrieve(query, top_k=self.top_k)
        gen = self.generator.generate(query, retrieved, query_date)
        return PipelineResult(
            answer=gen.answer,
            retrieved_memory_ids=[m.memory_id for m in retrieved],
            usage_input_tokens=gen.usage_input_tokens,
            usage_output_tokens=gen.usage_output_tokens,
        )
