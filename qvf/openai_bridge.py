"""OpenAI-backed reader and extractor for cross-provider comparison runs.

Interface-compatible with the Anthropic classes so the runner can swap
providers via --reader openai:<model> and QVF_ADAPTER_MODEL=openai:<model>.
The judge stays on claude-opus for protocol comparability across providers.

Note: gpt-5-family models do not accept a temperature parameter (reasoning
models); calls run at provider defaults. Record this as a protocol caveat.
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import OpenAI

from qvf import config
from qvf.engine_bridge import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT_SCOPED,
    ExtractedQueryFocus,
    ScopedQueryFocus,
    ScopedSlotExtraction,
    SlotExtraction,
)
from qvf.generator import GenerationResult
from qvf.prompts import BASELINE_GENERATOR_SYSTEM_PROMPT, format_baseline_generator_input
from qvf.retrieval import MemoryItem

_JSON_EXAMPLE = (
    '{"query_focus": {"entity": "user", "slot": "<slot name>", '
    '"needs_current": true, "query_temporal_scope": "current"}, '
    '"records": [{"record_id": "r1", "source_memory_id": "<memory_id>", '
    '"source_span": "<verbatim substring>", "entity": "user", '
    '"slot": "<slot name>", "value": "<value>", "claim": "<one sentence>", '
    '"slot_cardinality": "single", "temporal_relation": "unresolved", '
    '"relation_target_record_ids": []}]}'
)


class OpenAIGenerator:
    """Reader over OpenAI chat completions; mirrors BaselineGenerator."""

    def __init__(self, model: str, system_prompt: Optional[str] = None):
        self.model = f"openai:{model}"
        self._model = model
        self.system_prompt = system_prompt or BASELINE_GENERATOR_SYSTEM_PROMPT
        self._client = OpenAI()

    def generate(
        self,
        query: str,
        memories: List[MemoryItem],
        query_date: Optional[str] = None,
    ) -> GenerationResult:
        user_input = format_baseline_generator_input(query, memories, query_date)
        r = self._client.chat.completions.create(
            model=self._model,
            max_completion_tokens=config.GENERATOR_MAX_TOKENS,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_input},
            ],
        )
        return GenerationResult(
            answer=(r.choices[0].message.content or "").strip(),
            usage_input_tokens=r.usage.prompt_tokens,
            usage_output_tokens=r.usage.completion_tokens,
        )


class OpenAISlotExtractor:
    """Extraction via OpenAI chat completions, JSON-prompted like
    LocalSlotExtractor: one repair retry on invalid JSON, then an empty
    extraction (runner falls back to the full-context path)."""

    def __init__(self, model: str):
        self.model = f"openai:{model}"
        self._model = model
        self._client = OpenAI()

    def extract(
        self,
        query: str,
        memories: List[MemoryItem],
        query_date: Optional[str] = None,
        scoped: bool = False,
        contract: str = "v5",
    ) -> tuple[SlotExtraction, int, int]:
        if contract == "v7":
            raise NotImplementedError("v7 recall contract: Anthropic extractor only")
        schema_cls = ScopedSlotExtraction if scoped else SlotExtraction
        base_prompt = (EXTRACTION_SYSTEM_PROMPT_SCOPED if scoped
                       else EXTRACTION_SYSTEM_PROMPT)
        system = (
            base_prompt
            + "\n\nOutput format: return ONLY one JSON object, no prose and no "
            "markdown fences, shaped exactly like this example (field names "
            "and enum values must match):\n" + _JSON_EXAMPLE
            + ("\nquery_temporal_scope must be one of: current, "
               "past_or_change, unclear." if scoped else "")
        )
        mem_payload = [
            {"memory_id": m.memory_id, "text": m.content, "metadata": m.metadata}
            for m in memories
        ]
        user_input = (
            f"QUERY: {query}\n\nQUERY DATE: {query_date or 'UNKNOWN'}\n\n"
            f"RETRIEVED MEMORIES (JSON):\n"
            f"{json.dumps(mem_payload, ensure_ascii=False, indent=2)}"
        )
        tin = tout = 0
        attempt_input = user_input
        for _ in range(2):
            r = self._client.chat.completions.create(
                model=self._model,
                max_completion_tokens=config.ADAPTER_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": attempt_input},
                ],
            )
            tin += r.usage.prompt_tokens
            tout += r.usage.completion_tokens
            text = r.choices[0].message.content or ""
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return schema_cls.model_validate_json(text[start:end]), tin, tout
            except Exception as exc:  # noqa: BLE001 — retry once with the error
                attempt_input = (
                    user_input
                    + "\n\nYour previous output was not valid JSON for the "
                    f"required schema ({exc}). Return ONLY the corrected JSON "
                    "object."
                )
        if scoped:
            empty = ScopedSlotExtraction(
                query_focus=ScopedQueryFocus(
                    entity="user", slot="unknown", needs_current=True,
                    query_temporal_scope="unclear",
                ),
                records=[],
            )
        else:
            empty = SlotExtraction(
                query_focus=ExtractedQueryFocus(
                    entity="user", slot="unknown", needs_current=True
                ),
                records=[],
            )
        return empty, tin, tout
