"""Bridge between LLM extraction and the legacy deterministic validity engine.

Implements the three conditions of the decisive experiment:
- prompted: Claude extracts slot-level records (span-grounded) from retrieved
  rounds -> engine adjudicates -> sidecar -> small reader answers.
- oracle: records built programmatically from STALE's M_old/M_new/explanation
  fields (faithful to the historical "adapter provided exact pairs" setup;
  bypasses retrieval, serving as the mechanism ceiling).
- (direct condition lives in qvf.pipeline.BaselinePipeline.)

Design notes:
- Evidence fields are set to the full source_span (legal per the engine's
  substring rule). The LLM's task is getting the span itself right; span
  verbatimness is enforced by the engine, and rejections are counted via
  extraction_report -> this is the coverage metric.
- allow_partial=True so imperfect extraction degrades record-by-record instead
  of killing the whole request.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from qvf import config
from qvf.retrieval import MemoryItem

# Make the legacy engine importable. The upstream repo moved the engine from
# 01_核心代码/src to legacy_engine/src (2026-08-02 restructure); try both.
_ENGINE_BASE = Path(__file__).resolve().parent.parent / "external" / "qvf_withcontroller"
for _cand in (_ENGINE_BASE / "legacy_engine" / "src",
              _ENGINE_BASE / "01_核心代码" / "src"):
    if _cand.exists():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

from qvf_validity_admission import run_raw_memory_validity_controller  # noqa: E402


# ---------------------------------------------------------------------------
# Extraction contract (LLM-facing schema)
# ---------------------------------------------------------------------------

class ExtractedQueryFocus(BaseModel):
    entity: str = Field(description="The entity the query asks about, e.g. 'user'.")
    slot: str = Field(
        description="The attribute/slot the query asks about, e.g. 'residence city'. "
        "Must EXACTLY match the slot string used in the relevant records."
    )
    needs_current: bool = Field(
        description="True if the query asks about the current state."
    )


class ExtractedRecord(BaseModel):
    record_id: str = Field(description="Unique id for this record, e.g. 'r1'.")
    source_memory_id: str = Field(
        description="memory_id of the retrieved memory this record comes from."
    )
    source_span: str = Field(
        description="VERBATIM contiguous substring of that memory's text stating the fact. "
        "Copy exactly — any paraphrase invalidates the record."
    )
    entity: str = Field(description="Entity of the fact, e.g. 'user'.")
    slot: str = Field(description="Slot name; use the same string as query_focus.slot for relevant records.")
    value: str = Field(description="The slot value stated by this span.")
    claim: str = Field(description="One-sentence normalized statement of the fact.")
    slot_cardinality: Literal["single", "set", "unknown"] = Field(
        description="'single' if the slot can hold one value at a time (e.g. home city); "
        "'set' if multiple values coexist (e.g. hobbies); 'unknown' if unclear."
    )
    temporal_relation: Literal[
        "replacement", "correction", "equivalent", "additive", "unresolved",
        "contradiction", "cessation"
    ] = Field(
        description="Relation of this record to OTHER extracted records for the same "
        "entity+slot: 'replacement' only if this memory explicitly establishes a NEW "
        "state replacing an older record's state; 'cessation' if it explicitly ENDS "
        "the state without a new value (quit, canceled, no longer, stopped); "
        "'contradiction' if two records assert incompatible values with NO change "
        "language and no clear temporal ordering (a factual disagreement, not an "
        "update); 'unresolved' when in doubt. A later timestamp alone is NOT "
        "replacement."
    )
    relation_target_record_ids: List[str] = Field(
        default_factory=list,
        description="record_ids of the records this replaces/corrects/ends/"
        "contradicts (required for replacement/correction/cessation/"
        "contradiction; must cover every competing record).",
    )
    condition: str = Field(
        default="",
        description="If this value applies only under an explicit condition or "
        "context (at work, on weekends, when traveling ...), state it briefly; "
        "empty string otherwise.",
    )
    implies_stale_slots: List[str] = Field(
        default_factory=list,
        description="Slot names of OTHER attributes this update makes stale via "
        "a common-sense dependency (e.g. registering car+license in a new state "
        "implies 'residence_state' changed). Empty if none.",
    )


class SlotExtraction(BaseModel):
    query_focus: ExtractedQueryFocus
    records: List[ExtractedRecord] = Field(
        description="Records RELEVANT to the query focus only. Skip unrelated memories."
    )


class ScopedQueryFocus(ExtractedQueryFocus):
    """v5: adds the query's temporal scope so the controller can leave
    history-seeking queries untouched (old states are their evidence)."""

    query_temporal_scope: Literal["current", "past_or_change", "unclear"] = Field(
        description="'current' if the query asks what the state IS now; "
        "'past_or_change' if it asks about a past state, when something "
        "happened, a duration or date computation, which of two events came "
        "first, or how a value changed over time (trajectory); "
        "'unclear' otherwise."
    )


class ScopedSlotExtraction(SlotExtraction):
    query_focus: ScopedQueryFocus


class MemoryTriage(BaseModel):
    memory_id: str
    mentions_query_slot: Literal["yes", "maybe", "no"] = Field(
        description="'yes' = this memory states a value for the query's "
        "entity+slot; 'maybe' = it implies one obliquely; 'no' = unrelated."
    )


class TriagedScopedSlotExtraction(ScopedSlotExtraction):
    """v7 recall contract: a forced per-memory triage decision precedes record
    extraction, so a competing value cannot be silently skipped (the measured
    admit-route failure mode: extraction found only one of two values in
    25/54 fresh-slice failures)."""

    memory_triage: List[MemoryTriage] = Field(
        description="EXACTLY one entry per retrieved memory, in input order."
    )
    records: List[ExtractedRecord] = Field(
        description="One record for EVERY memory triaged 'yes' or 'maybe'. "
        "Do not skip oblique phrasings - map them onto the query slot."
    )


EXTRACTION_SYSTEM_PROMPT = """\
You extract slot-level structured records from retrieved conversation memories,
for consumption by a downstream deterministic validity engine.

Rules:
1. First identify the query focus: entity + slot + whether it needs the current
   state. Use a short stable slot name and reuse it verbatim in the records.
2. Extract ONLY records relevant to the query focus. For each record copy an
   EXACT verbatim contiguous span from the memory text (the engine mechanically
   verifies the span; paraphrasing gets the record rejected).
3. Mark temporal_relation='replacement' ONLY when the text explicitly
   establishes a new state for the same entity+slot (moved, changed, updated,
   no longer, now ...). A later timestamp alone is NOT evidence of replacement.
   When you mark replacement/correction, relation_target_record_ids must list
   every competing record.
4. Prefer 'unresolved' over guessing. Missing evidence must stay missing —
   never invent values, spans, or relations.
5. When two records give DIFFERENT values for the same entity+slot, you must
   surface the competition: mark the later one 'replacement'/'correction' with
   targets if its text has state-change language, otherwise extract BOTH with
   'unresolved' so the downstream engine sees the conflict. Never extract only
   one of two competing values.
6. You are not answering the question. Do not include an answer anywhere.
"""


EXTRACTION_SYSTEM_PROMPT_SCOPED = EXTRACTION_SYSTEM_PROMPT + """
7. Classify the query's temporal scope (query_focus.query_temporal_scope):
   'current' = the query asks what the state IS now.
   'past_or_change' = the query asks about a past state, when something
   happened, how long between two events, which of two events came first, or
   how a value changed over time. For such queries OLD states are the evidence
   the reader needs — they must not be treated as stale noise.
   'unclear' = anything else.
"""


EXTRACTION_SYSTEM_PROMPT_SPECIES = EXTRACTION_SYSTEM_PROMPT_SCOPED + """
8. VALIDITY SPECIES (beyond temporal replacement):
   - 'cessation': the text explicitly ENDS a state with no new value ("I quit
     the gym", "canceled that subscription", "no longer ..."). Target the
     ended state's record(s).
   - 'contradiction': two records give incompatible values for the same
     entity+slot with NO change language and NO clear temporal ordering — a
     factual disagreement, not an update. Label BOTH records 'contradiction'
     and cross-target each other. Never resolve it yourself.
   - condition field: when a value explicitly holds only in a context ("my
     work address", "on weekends I stay at ..."), record that context.
   - implies_stale_slots: when an update to THIS slot makes ANOTHER slot's
     older values stale through common sense (car registration + license
     moved to a new state -> residence state changed), list those slot names.
9. Precedence when labeling: replacement/correction/cessation (explicit
   language) > contradiction (incompatible, unordered) > unresolved.
"""


EXTRACTION_SYSTEM_PROMPT_SPECIES2 = EXTRACTION_SYSTEM_PROMPT_SPECIES + """
10. CONFLICT-PAIR SCAN: whenever you extract ANY record for the query's slot,
    actively re-scan EVERY other memory for competing or earlier values of
    that same slot and extract them too — a chain or conflict can only be
    seen downstream if BOTH sides are extracted. For change/trajectory
    questions ("how did X change?") extracting the full dated chain of
    values is the deliverable.
"""


CONTRADICTION_READER_PROMPT = """\
You are a question answering assistant. The memories provided contain
FACTUALLY INCOMPATIBLE claims about the thing the question asks about. The
upstream validity controller verified they conflict without any update
language and without a clear temporal order — this is a disagreement between
sources, NOT an update.

Rules:
1. Do NOT resolve the conflict by recency — no evidence supports that here.
2. Prefer the claim with more specific, first-hand, or repeated support in
   the memories; say briefly that the records disagree if it matters.
3. If the disagreement cannot be resolved from the memories, answer with the
   better-supported value and note the uncertainty in one clause.
Answer concisely and directly.
"""


WRITE_TIME_EXTRACTION_PROMPT = """\
You are indexing ONE conversation session into a long-term memory ledger,
at the moment the session is written to storage. You see only this session —
no question, no other sessions.

Extract user-state records: every stated or implied fact about the user's
situation (location, job, device, plan, subscription, preference, project,
health, relationship, possessions ...).

Rules:
1. slot: a short stable snake_case attribute name (location_city, phone_model,
   job_title, backup_service ...). Use the most conventional name so the same
   attribute gets the same slot across sessions.
2. Copy an EXACT verbatim contiguous span from the session text as
   source_span (mechanically verified; paraphrase gets rejected).
3. Include obliquely implied states ("signed a lease in Austin" ->
   location_city = Austin).
4. Skip chitchat, questions, hypotheticals, plans that did not happen.
5. temporal_relation is always 'unresolved' here (cross-session ordering is
   resolved later by the ledger, not by you).
6. No records is a valid answer for a session with no user-state facts.
"""


class LedgerExtraction(BaseModel):
    records: List[ExtractedRecord] = Field(
        description="User-state records found in THIS session only."
    )


class WriteTimeLedger:
    """v8: extraction moves from query time to write time. Each session is
    indexed once (small focused context — no 10-round attention dilution),
    records accumulate in a per-item slot ledger, and query time becomes a
    deterministic slot lookup (no embedding-similarity dependence). Disk-cached
    so the indexing cost is paid once per item and amortized across queries."""

    def __init__(self, model: str = "claude-haiku-4-5",
                 cache_dir: str = "results/ledger_cache"):
        self.model = model
        self.cache_dir = Path(cache_dir) / model.replace(":", "_")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = anthropic.Anthropic()
        self.last_index_tokens = (0, 0)

    def _index_session(self, item_uid: str, sess_key: str,
                       rounds: List[MemoryItem]) -> tuple[list, int, int]:
        cache_file = self.cache_dir / f"{item_uid}_{sess_key.replace('/', '_')}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8")), 0, 0
        payload = [
            {"memory_id": m.memory_id, "text": m.content, "metadata": m.metadata}
            for m in rounds
        ]
        extra = {"temperature": 0.0} if "haiku" in self.model else {}
        resp = self._client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=[{"type": "text", "text": WRITE_TIME_EXTRACTION_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content":
                       f"SESSION (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}"}],
            output_format=LedgerExtraction,
            **extra,
        )
        recs = []
        if resp.stop_reason != "refusal" and resp.parsed_output is not None:
            date = str((rounds[0].metadata or {}).get("session_date") or "")
            recs = [
                {"slot": r.slot, "value": r.value, "entity": r.entity,
                 "source_memory_id": r.source_memory_id, "date": date}
                for r in resp.parsed_output.records
            ]
        cache_file.write_text(json.dumps(recs, ensure_ascii=False),
                              encoding="utf-8")
        return recs, resp.usage.input_tokens, resp.usage.output_tokens

    def index_item(self, item_uid: str, memories: List[MemoryItem]) -> list:
        """Index every session of an item's memory pool; returns the ledger."""
        sessions: dict = {}
        for m in memories:
            sess = m.memory_id.split("#")[0]
            sessions.setdefault(sess, []).append(m)
        ledger, tin, tout = [], 0, 0
        for sess_key, rounds in sessions.items():
            recs, i, o = self._index_session(item_uid, sess_key, rounds)
            ledger.extend(recs)
            tin += i
            tout += o
        self.last_index_tokens = (tin, tout)
        return ledger


LEDGER_SLOT_PICK_PROMPT = """\
You route one user question against a memory ledger. Reply with ONLY a JSON
object {"slots": [...], "scope": "current"|"past_or_change"}.

- slots: which of the AVAILABLE SLOTS (given below) the question is about —
  usually one, possibly several, empty list if none match.
- scope: 'current' if the question asks what the state IS now;
  'past_or_change' if it asks about a past state, when something happened,
  a duration, ordering of events, or how a value changed over time.
"""


EXTRACTION_SYSTEM_PROMPT_V7 = EXTRACTION_SYSTEM_PROMPT_SCOPED + """
8. RECALL CONTRACT: fill memory_triage with EXACTLY one entry per retrieved
   memory, in input order — does the memory state or imply a value for the
   query's entity+slot? 'yes' = states one; 'maybe' = implies one obliquely
   (e.g. "signed a lease in Austin" implies location = Austin); 'no' =
   unrelated.
9. Every memory triaged 'yes' or 'maybe' MUST yield a record carrying its
   value, even when the phrasing is oblique. The caution in rules 3-5 governs
   only the temporal_relation LABEL (prefer 'unresolved' when explicit change
   language is absent); it never justifies omitting a record. Omitting one of
   two competing values is the worst possible failure.
"""


RECENCY_READER_PROMPT = """\
You are a question answering assistant with access to retrieved memories from
past conversations with the user. The memories are listed NEWEST FIRST.

When memories conflict about the same fact, prefer the most recent one — the
user's situation may have changed over time. Answer the question using only
the retrieved memories. If the memories do not contain the needed information,
say you don't have that information.

Answer concisely and directly.
"""


CONFLICT_LATEST_KNOWN_READER_PROMPT = """\
You are a question answering assistant. The memories provided contain
CONFLICTING claims about the state the question asks about: an earlier claim
and a later claim (their dates are in the metadata). The upstream validity
controller verified they compete for the same attribute but found no explicit
update language to order them.

Rules:
1. In personal-memory settings, the later-dated claim usually reflects the
   current state. Base your answer on the LATER claim.
2. Briefly note that this changed from the earlier state (one clause, e.g.
   "— previously X").
3. Do not decline to answer; the relevant facts are in front of you.
Answer concisely and directly.
"""


VALIDATED_CONTEXT_READER_PROMPT = """\
You are a question answering assistant. The memories provided to you have been
pre-validated by an upstream validity controller: they represent the user's
CURRENT, up-to-date state relevant to this question (stale or superseded
information has already been removed).

Rules:
1. Treat the provided memories as authoritative current facts and base your
   answer on them.
2. Do NOT decline for lack of information when a provided memory states the
   relevant fact — connect it to the question even if the memory is brief or
   from a different conversation topic.
3. Only say you don't have the information if the memories genuinely contain
   nothing relevant.
Answer concisely and directly.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(ts: Optional[str]) -> Optional[str]:
    """Normalize timestamps to ISO-8601 with UTC.

    Handles 'YYYY-MM-DD HH:MM' (STALE) and 'YYYY/MM/DD (Www) HH:MM'
    (LongMemEval) styles.
    """
    if not ts:
        return None
    t = str(ts).strip()
    # LongMemEval style: 2023/05/20 (Mon) 02:21
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})\s*(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})", t)
    if m:
        y, mo, d, h, mi = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}T{int(h):02d}:{mi}:00+00:00"
    t = t.replace(" ", "T")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        t += "T00:00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", t):
        t += ":00"
    if not re.search(r"[+-]\d{2}:\d{2}$|Z$", t):
        t += "+00:00"
    return t


def _engine_memory_row(
    m: MemoryItem, rank: int, records: List[dict]
) -> dict:
    row = {
        "memory_id": m.memory_id,
        "text": m.content,
        "source_type": "conversation_round",
        "source_confidence": 0.9,
        "retrieval_rank": rank,
    }
    observed = _iso(m.metadata.get("session_date"))
    if observed:
        row["observed_at"] = observed
    if records:
        row["structured_records"] = records
    return row


def _record_to_engine(rec: ExtractedRecord, observed_at: Optional[str]) -> dict:
    span = rec.source_span
    out = {
        "memory_id": rec.record_id,
        "entity": rec.entity,
        "slot": rec.slot,
        "value": rec.value,
        "claim": rec.claim,
        "source_span": span,
        "slot_cardinality": rec.slot_cardinality,
        "slot_cardinality_evidence": span,
    }
    if rec.temporal_relation in ("replacement", "correction"):
        out["temporal_relation"] = rec.temporal_relation
        out["temporal_relation_evidence"] = span
        out["relation_target_memory_ids"] = list(rec.relation_target_record_ids)
        if observed_at:
            out["effective_from"] = observed_at
            out["effective_from_evidence"] = span
    elif rec.temporal_relation in ("equivalent", "additive"):
        out["temporal_relation"] = rec.temporal_relation
        out["temporal_relation_evidence"] = span
        if rec.relation_target_record_ids:
            out["relation_target_memory_ids"] = list(rec.relation_target_record_ids)
    return out


def build_engine_request(
    request_id: str,
    query_text: str,
    focus: ExtractedQueryFocus,
    memories: List[MemoryItem],
    extracted: List[ExtractedRecord],
    as_of: Optional[str] = None,
) -> dict:
    by_memory: dict = {}
    for rec in extracted:
        by_memory.setdefault(rec.source_memory_id, []).append(rec)
    rows = []
    for i, m in enumerate(memories):
        recs = [
            _record_to_engine(r, _iso(m.metadata.get("session_date")))
            for r in by_memory.get(m.memory_id, [])
        ]
        rows.append(_engine_memory_row(m, i + 1, recs))
    query = {
        "query_id": f"{request_id}_q",
        "text": query_text,
        "entity": focus.entity,
        "slot": focus.slot,
        "needs_current": bool(focus.needs_current),
    }
    as_of_iso = _iso(as_of)
    if as_of_iso:
        query["as_of"] = as_of_iso
    return {
        "request_id": request_id,
        "query": query,
        "retrieved_memories": rows,
    }


@dataclass
class EngineRunResult:
    ok: bool
    sidecar: Optional[dict] = None
    decision: Optional[dict] = None
    accepted_records: int = 0
    rejected_records: int = 0
    rejection_reasons: List[str] = field(default_factory=list)
    blocking_reasons: List[str] = field(default_factory=list)
    error: Optional[str] = None


def run_engine(request: dict) -> EngineRunResult:
    try:
        output = run_raw_memory_validity_controller(
            request, selective=False, allow_partial=True
        )
    except Exception as e:  # noqa: BLE001 — contract errors are data, not crashes
        return EngineRunResult(ok=False, error=f"{type(e).__name__}: {e}")
    report = output.get("extraction_report", {})
    rejected = report.get("rejected_records", []) or []
    result = EngineRunResult(
        ok=bool(output.get("controller_executed")),
        accepted_records=report.get("accepted_record_count", 0),
        rejected_records=report.get("rejected_record_count", 0),
        rejection_reasons=[str(r.get("reason", r)) for r in rejected][:20],
        blocking_reasons=[str(b) for b in (report.get("blocking_reasons") or [])],
    )
    sidecars = output.get("model_facing_sidecar_payloads") or []
    decisions = output.get("controller_decisions") or []
    if sidecars:
        result.sidecar = sidecars[0]
    if decisions:
        result.decision = decisions[0]
    return result


# ---------------------------------------------------------------------------
# LLM extractor (prompted condition)
# ---------------------------------------------------------------------------

class LLMSlotExtractor:
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

    def extract(
        self,
        query: str,
        memories: List[MemoryItem],
        query_date: Optional[str] = None,
        scoped: bool = False,
        contract: str = "v5",
    ) -> tuple[SlotExtraction, int, int]:
        """Returns (extraction, input_tokens, output_tokens).

        scoped=True uses the v5 schema/prompt that additionally classifies the
        query's temporal scope. contract="v7" selects the recall-contract
        variant; contract="species" adds the extended validity vocabulary
        (contradiction/cessation/condition/dependency). Defaults keep the
        pre-v5 contract byte-identical (existing arms are unaffected).
        """
        if contract in ("v7", "species", "species2"):
            scoped = True
        if self.mock:
            if contract == "v7":
                return (
                    TriagedScopedSlotExtraction(
                        query_focus=ScopedQueryFocus(
                            entity="user", slot="unknown", needs_current=True,
                            query_temporal_scope="current",
                        ),
                        records=[],
                        memory_triage=[],
                    ),
                    0,
                    0,
                )
            if scoped:
                return (
                    ScopedSlotExtraction(
                        query_focus=ScopedQueryFocus(
                            entity="user", slot="unknown", needs_current=True,
                            query_temporal_scope="current",
                        ),
                        records=[],
                    ),
                    0,
                    0,
                )
            return (
                SlotExtraction(
                    query_focus=ExtractedQueryFocus(
                        entity="user", slot="unknown", needs_current=True
                    ),
                    records=[],
                ),
                0,
                0,
            )
        mem_payload = [
            {"memory_id": m.memory_id, "text": m.content, "metadata": m.metadata}
            for m in memories
        ]
        user_input = (
            f"QUERY: {query}\n\nQUERY DATE: {query_date or 'UNKNOWN'}\n\n"
            f"RETRIEVED MEMORIES (JSON):\n{json.dumps(mem_payload, ensure_ascii=False, indent=2)}"
        )
        # Deterministic extraction on models that still accept temperature
        # (haiku-4-5); Opus 4.7+ rejects the param, so gate on model id.
        extra = {"temperature": 0.0} if "haiku" in self.model else {}
        if contract == "species2":
            sys_prompt = EXTRACTION_SYSTEM_PROMPT_SPECIES2
            out_schema = ScopedSlotExtraction
        elif contract == "species":
            sys_prompt = EXTRACTION_SYSTEM_PROMPT_SPECIES
            out_schema = ScopedSlotExtraction
        elif contract == "v7":
            sys_prompt = EXTRACTION_SYSTEM_PROMPT_V7
            out_schema = TriagedScopedSlotExtraction
        elif scoped:
            sys_prompt = EXTRACTION_SYSTEM_PROMPT_SCOPED
            out_schema = ScopedSlotExtraction
        else:
            sys_prompt = EXTRACTION_SYSTEM_PROMPT
            out_schema = SlotExtraction
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=config.ADAPTER_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": sys_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_input}],
            output_format=out_schema,
            **extra,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError("extraction failed or refused")
        return (
            response.parsed_output,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )


class LocalSlotExtractor:
    """Fully-local extraction via an Ollama chat model (zero API cost).

    Prompts the model to emit the SlotExtraction JSON directly. Invalid JSON
    gets one repair retry with the validation error appended; a second failure
    falls back to an empty extraction (runner then takes the direct-fallback
    path). Interface-compatible with LLMSlotExtractor.
    """

    _EXAMPLE = (
        '{"query_focus": {"entity": "user", "slot": "<slot name>", '
        '"needs_current": true, "query_temporal_scope": "current"}, '
        '"records": [{"record_id": "r1", "source_memory_id": "<memory_id>", '
        '"source_span": "<verbatim substring>", "entity": "user", '
        '"slot": "<slot name>", "value": "<value>", "claim": "<one sentence>", '
        '"slot_cardinality": "single", "temporal_relation": "unresolved", '
        '"relation_target_record_ids": []}]}'
    )

    def __init__(self, model: str = "qwen3:4b"):
        self.model = f"local:{model}"
        self._chat = LocalChatModel(model=model)

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
            "and enum values must match):\n" + self._EXAMPLE
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
        attempt_input = user_input
        for _ in range(2):
            text = self._chat.chat(system, attempt_input, max_tokens=4096)
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return schema_cls.model_validate_json(text[start:end]), 0, 0
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
        return empty, 0, 0


# ---------------------------------------------------------------------------
# Oracle extraction from STALE fields (mechanism ceiling)
# ---------------------------------------------------------------------------

def oracle_pair_for_stale(item_extra: dict, timestamps_old: Optional[str], timestamps_new: Optional[str]):
    """Build (memories, focus, records) from M_old/M_new/explanation.

    Mirrors the historical setup where the hand-written adapter supplied exact
    old/new pairs directly (no retrieval).
    """
    m_old = str(item_extra.get("M_old") or "")
    m_new = str(item_extra.get("M_new") or "")
    explanation = str(item_extra.get("explanation") or "")
    # "Spatiotemporal_Context.location(city) is now Austin." -> slot / new value
    slot, new_value = explanation, m_new
    m = re.match(r"^(.*?)\s+is now\s+(.*?)\.?$", explanation)
    if m:
        slot = m.group(1).strip()
        new_value = m.group(2).strip()

    memories = [
        MemoryItem(
            memory_id="mem_old",
            content=m_old,
            metadata={"session_date": timestamps_old, "session_id": "oracle_old"},
        ),
        MemoryItem(
            memory_id="mem_new",
            content=m_new,
            metadata={"session_date": timestamps_new, "session_id": "oracle_new"},
        ),
    ]
    focus = ExtractedQueryFocus(entity="user", slot=slot, needs_current=True)
    records = [
        ExtractedRecord(
            record_id="oracle_old",
            source_memory_id="mem_old",
            source_span=m_old,
            entity="user",
            slot=slot,
            value=f"OLD: {m_old}",
            claim=m_old,
            slot_cardinality="single",
            temporal_relation="unresolved",
        ),
        ExtractedRecord(
            record_id="oracle_new",
            source_memory_id="mem_new",
            source_span=m_new,
            entity="user",
            slot=slot,
            value=new_value,
            claim=m_new,
            slot_cardinality="single",
            temporal_relation="replacement",
            relation_target_record_ids=["oracle_old"],
        ),
    ]
    return memories, focus, records


# ---------------------------------------------------------------------------
# Validity-triggered retrieval repair
# ---------------------------------------------------------------------------
# Why: a current-state query usually mentions the OLD value ("does the user
# still live in Seattle?"), so lexical retrieval returns old-state rounds; the
# NEW state ("Austin") shares no surface overlap and gets missed. Worse, with
# only the old state in context the engine sees no competitor and admits the
# stale state as current. The repair pass drops the old value and searches by
# slot terms + state-change language instead.

UPDATE_EXPANSION_TERMS = (
    "moved changed switched updated update new now recently no longer anymore "
    "replaced started stopped quit joined bought sold current latest just"
)


def build_repair_query(focus: ExtractedQueryFocus) -> str:
    slot_tokens = re.sub(r"[_.()\[\]]+", " ", focus.slot)
    return f"{focus.entity} {slot_tokens} {UPDATE_EXPANSION_TERMS}"


def build_repair_query_dense(focus: ExtractedQueryFocus) -> str:
    """Natural-sentence phrasing embeds better than keyword soup."""
    slot_tokens = re.sub(r"[_.()\[\]]+", " ", focus.slot).strip()
    return (
        f"The user's {slot_tokens} recently changed: they moved, switched, "
        f"updated, quit, started, or got something new. "
        f"What is the user's current {slot_tokens} now?"
    )


def has_state_change_record(extraction: SlotExtraction) -> bool:
    return any(
        r.temporal_relation in ("replacement", "correction")
        for r in extraction.records
    )


def needs_repair(engine: EngineRunResult, extraction: SlotExtraction) -> bool:
    """Trigger the repair pass when validity analysis suggests the current
    state may be missing from the retrieved set."""
    if not engine.ok:
        return True
    decision = engine.decision or {}
    action = str(decision.get("next_action") or "")
    if action.startswith("retrieve") or action.startswith("query_rewrite"):
        return True
    if decision.get("read_decision") == "UNKNOWN_CURRENT":
        return True
    if extraction.query_focus.needs_current and not has_state_change_record(extraction):
        # Current-state query but no evidence of any state change extracted:
        # the update round may simply not have been retrieved.
        return True
    return False


# ---------------------------------------------------------------------------
# Sidecar reader (small answer model consuming the engine's packet)
# ---------------------------------------------------------------------------

class LocalChatModel:
    """Minimal client for a local Ollama server's OpenAI-compatible endpoint.

    Used for weak-reader conditions: the reader must be strictly weaker than
    API models, runs free on the local GPU, and adds cross-family evidence.
    Qwen3 thinking is disabled (weak-reader regime measures direct compliance),
    and any leaked <think> blocks are stripped defensively.
    """

    def __init__(self, model: str = "qwen3:4b", base_url: str = "http://localhost:11434",
                 num_ctx: int = 16384):
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Explicit context window. Ollama's runtime default (~2048) silently
        # truncates long prompts — discovered 2026-08-01 via prompt_eval_count;
        # all local-reader results before this fix ran under truncation.
        self.num_ctx = num_ctx
        self.last_prompt_eval: int | None = None

    def _chat_once(self, system: str, user: str, max_tokens: int,
                   num_ctx: int) -> str:
        import requests

        # Default (thinking-enabled) mode: Ollama separates reasoning into
        # message.thinking and puts the clean answer in message.content.
        # (Passing think=false inverts this and dumps reasoning into content.)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.0,
                "num_ctx": num_ctx,
            },
        }
        r = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=600)
        r.raise_for_status()
        data = r.json()
        self.last_prompt_eval = data.get("prompt_eval_count")
        text = (data.get("message") or {}).get("content", "")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return text.strip()

    def chat(self, system: str, user: str, max_tokens: int = 4096) -> str:
        # Empty-answer retry ladder. num_predict counts thinking tokens, so a
        # long chain of thought (e.g. date arithmetic) can exhaust the budget
        # before any answer text is emitted, returning empty content. Applied
        # identically on every call path so no experimental arm is favored:
        #   1. normal call;
        #   2. retry with a 4x generation budget and a wider context window;
        #   3. retry with Qwen3's /no_think soft switch (no thinking, direct
        #      answer) — think=false via the API is NOT equivalent (it dumps
        #      reasoning prose into content).
        self.last_empty_retries = 0
        text = self._chat_once(system, user, max_tokens, self.num_ctx)
        if text:
            return text
        self.last_empty_retries = 1
        text = self._chat_once(system, user, max_tokens * 4,
                               max(self.num_ctx, 24576))
        if text:
            return text
        self.last_empty_retries = 2
        return self._chat_once(system, user + "\n/no_think", max_tokens,
                               max(self.num_ctx, 24576))


SIDECAR_READER_SYSTEM_PROMPT = """\
You answer a user's question using a validity-controlled memory packet produced
by an upstream controller.

The packet tells you which evidence is admitted as CURRENT, which is allowed
only as HISTORY, and which is blocked as stale for current-state use. Rules:
1. Follow the packet's context_control_policy and reader contract strictly:
   answer current-state questions only from current-admitted evidence.
2. Blocked/stale items may be mentioned only as past history, never as the
   current state. If the question's premise relies on a stale state, correct it.
3. If the packet indicates the evidence is insufficient, say you don't have
   that information rather than guessing.
Answer concisely and directly.
"""


class SidecarReader:
    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        client: Optional[anthropic.Anthropic] = None,
        mock: Optional[bool] = None,
    ):
        self.model = model
        self.mock = config.mock_mode() if mock is None else mock
        self._client = client
        if not self.mock and self._client is None:
            self._client = anthropic.Anthropic()

    def answer(self, question: str, sidecar: dict) -> tuple[str, int, int]:
        if self.mock:
            return "[mock answer]", 0, 0
        user_input = (
            f"VALIDITY PACKET (JSON):\n{json.dumps(sidecar, ensure_ascii=False, indent=1)}\n\n"
            f"QUESTION: {question}"
        )
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SIDECAR_READER_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_input}],
        )
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        return text, response.usage.input_tokens, response.usage.output_tokens


class LocalSidecarReader:
    """SidecarReader backed by a local Ollama model (free, weak-reader regime)."""

    def __init__(self, local: LocalChatModel):
        self.local = local
        self.model = f"local:{local.model}"

    def answer(self, question: str, sidecar: dict) -> tuple[str, int, int]:
        user_input = (
            f"VALIDITY PACKET (JSON):\n{json.dumps(sidecar, ensure_ascii=False, indent=1)}\n\n"
            f"QUESTION: {question}"
        )
        return self.local.chat(SIDECAR_READER_SYSTEM_PROMPT, user_input), 0, 0


class LocalDirectGenerator:
    """Baseline (direct) generation backed by a local Ollama model.

    Pass system_prompt=VALIDATED_CONTEXT_READER_PROMPT for the post-surgery
    read, where memories are pre-validated and abstention-by-default backfires.
    """

    def __init__(self, local: LocalChatModel, system_prompt: Optional[str] = None):
        from qvf.prompts import BASELINE_GENERATOR_SYSTEM_PROMPT

        self.local = local
        self.model = f"local:{local.model}"
        self.system_prompt = system_prompt or BASELINE_GENERATOR_SYSTEM_PROMPT

    def generate(self, query: str, memories: List[MemoryItem], query_date: Optional[str] = None):
        from qvf.generator import GenerationResult
        from qvf.prompts import format_baseline_generator_input

        text = self.local.chat(
            self.system_prompt,
            format_baseline_generator_input(query, memories, query_date),
        )
        return GenerationResult(answer=text)
