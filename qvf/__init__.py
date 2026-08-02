"""QVF — Query-conditioned Validity Filter.

A post-retrieval, pre-generation module for memory-augmented LLM agents.
The Semantic Adapter converts (query, retrieved memories, metadata) into a
structured Query-Conditioned Validity Map that downstream answer generation
can condition on.
"""

__version__ = "0.1.0"

from qvf.schema import (
    ValidityMap,
    AtomicClaim,
    ClaimRelation,
    QueryAnalysis,
    ApplicabilityLabel,
    TemporalLabel,
    MemoryRole,
    RelationLabel,
    Sufficiency,
    RiskFlag,
)
from qvf.retrieval import MemoryItem, BM25Retriever
from qvf.adapter import SemanticAdapter
from qvf.pipeline import QVFPipeline, BaselinePipeline, FilterOnlyPipeline, PipelineResult
