"""Answer generation, with and without QVF conditioning.

Two generators sharing one Claude backend:
- BaselineGenerator: query + raw retrieved memories -> answer (vanilla RAG).
- QVFGenerator: query + memories + ValidityMap -> answer conditioned on
  query-conditioned applicability/temporal labels and sufficiency.

The generator model and prompts are held constant across conditions except for
the presence of the validity map, isolating QVF's contribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import anthropic

from qvf import config
from qvf.prompts import (
    BASELINE_GENERATOR_SYSTEM_PROMPT,
    PROMPT_ONLY_GENERATOR_SYSTEM_PROMPT,
    QVF_GENERATOR_SYSTEM_PROMPT,
    format_baseline_generator_input,
    format_prompt_only_generator_input,
    format_qvf_generator_input,
)
from qvf.retrieval import MemoryItem
from qvf.schema import ValidityMap


@dataclass
class GenerationResult:
    answer: str
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0


def _extract_text(response) -> str:
    parts = [b.text for b in response.content if b.type == "text"]
    return "\n".join(parts).strip()


class _ClaudeGenerator:
    def __init__(
        self,
        system_prompt: str,
        model: Optional[str] = None,
        client: Optional[anthropic.Anthropic] = None,
        mock: Optional[bool] = None,
    ):
        self.system_prompt = system_prompt
        self.model = model or config.DEFAULT_GENERATOR_MODEL
        self.mock = config.mock_mode() if mock is None else mock
        self._client = client
        if not self.mock and self._client is None:
            self._client = anthropic.Anthropic()

    def _call(self, user_input: str) -> GenerationResult:
        if self.mock:
            return GenerationResult(answer="[mock answer]")
        response = self._client.messages.create(
            model=self.model,
            max_tokens=config.GENERATOR_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": self.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_input}],
        )
        if response.stop_reason == "refusal":
            return GenerationResult(answer="[refused]")
        return GenerationResult(
            answer=_extract_text(response),
            usage_input_tokens=response.usage.input_tokens,
            usage_output_tokens=response.usage.output_tokens,
        )


class BaselineGenerator(_ClaudeGenerator):
    """Vanilla RAG generation: no validity map."""

    def __init__(self, **kwargs):
        super().__init__(system_prompt=BASELINE_GENERATOR_SYSTEM_PROMPT, **kwargs)

    def generate(
        self,
        query: str,
        memories: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> GenerationResult:
        return self._call(format_baseline_generator_input(query, memories, query_date))


class PromptOnlyGenerator(_ClaudeGenerator):
    """Generation conditioned on free-text analyst notes (prompt-only ablation)."""

    def __init__(self, **kwargs):
        super().__init__(system_prompt=PROMPT_ONLY_GENERATOR_SYSTEM_PROMPT, **kwargs)

    def generate(
        self,
        query: str,
        memories: List[MemoryItem],
        analysis_text: str,
        query_date: Optional[str] = None,
    ) -> GenerationResult:
        return self._call(
            format_prompt_only_generator_input(query, memories, analysis_text, query_date)
        )


class QVFGenerator(_ClaudeGenerator):
    """Generation conditioned on the Query-Conditioned Validity Map."""

    def __init__(self, **kwargs):
        super().__init__(system_prompt=QVF_GENERATOR_SYSTEM_PROMPT, **kwargs)

    def generate(
        self,
        query: str,
        memories: List[MemoryItem],
        validity_map: ValidityMap,
        query_date: Optional[str] = None,
    ) -> GenerationResult:
        vmap_json = validity_map.model_dump_json(indent=2)
        return self._call(
            format_qvf_generator_input(query, memories, vmap_json, query_date)
        )
