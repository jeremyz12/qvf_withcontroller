"""Decisive experiment on STALE: direct vs prompted+engine vs oracle+engine.

Pre-registered decision rules (see docs/AGENT_BRIEFING.md §3):
- prompted+engine >> direct with rejection rate <30%  -> route viable
- prompted+engine ~= direct or coverage collapse      -> route falsified
- oracle+engine - prompted+engine = extraction headroom (reported either way)

Reader is claude-haiku-4-5 in all conditions (weak-reader deployment regime).

Usage:
    python scripts/run_decisive_stale.py --items 35 --out results/decisive_stale.jsonl [--resume]
    QVF_MOCK=1 python scripts/run_decisive_stale.py --items 1 --no-judge   # plumbing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm

from eval.stale_dataset import load_stale
from qvf import config
from qvf.engine_bridge import (
    LLMSlotExtractor,
    SidecarReader,
    build_engine_request,
    build_repair_query,
    needs_repair,
    oracle_pair_for_stale,
    run_engine,
)
from qvf.generator import BaselineGenerator
from qvf.judge import ClaudeJudge
from qvf.retrieval import BM25Retriever

READER_MODEL = "claude-haiku-4-5"
TOP_K = 10

# Cost knife (default 0 = off, frozen behavior unchanged): when >0, caps the
# number of EXTRA retrieval+extraction rounds (repair / sweep / escalation)
# per pipeline invocation. One budget unit is charged right before each extra
# extractor call; an exhausted budget skips that round entirely.
_SCAN_BUDGET = int(os.environ.get("QVF_SCAN_BUDGET", "0") or 0)


def _scan_taker():
    used = [0]

    def take():
        if _SCAN_BUDGET <= 0:
            return True
        if used[0] >= _SCAN_BUDGET:
            return False
        used[0] += 1
        return True

    return take


def _dense_retriever_cls():
    # QVF_EMBED_BACKEND=openai[:<model>] switches to the pure-API embedding
    # stack (no local Ollama). Default stays nomic-embed-text via Ollama —
    # the embedding model is part of the frozen retrieval protocol, so the
    # switch must only happen between campaigns, never mid-run.
    backend = os.environ.get("QVF_EMBED_BACKEND", "ollama")
    if backend.startswith("openai"):
        from functools import partial

        from qvf.retrieval import OpenAIDenseRetriever

        if ":" in backend:
            return partial(OpenAIDenseRetriever, model=backend.split(":", 1)[1])
        return OpenAIDenseRetriever
    from qvf.retrieval import OllamaDenseRetriever

    return OllamaDenseRetriever


def run_direct(instance, generator, retriever_cls=BM25Retriever,
               newest_first: bool = False) -> dict:
    retriever = retriever_cls(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    if newest_first:
        retrieved = sorted(
            retrieved,
            key=lambda m: str(m.metadata.get("session_date") or ""),
            reverse=True,
        )
    gen = generator.generate(instance.question, retrieved, instance.question_date)
    return {
        "answer": gen.answer,
        "usage_input_tokens": gen.usage_input_tokens,
        "usage_output_tokens": gen.usage_output_tokens,
        "retrieved_memory_ids": [m.memory_id for m in retrieved],
    }


_WARN_INSTRUCTION = (
    "\n\n[Instruction: some memories may be OUTDATED — a later message may "
    "have superseded an earlier state (moves, job changes, new preferences). "
    "Check the dates, use the state valid at the asked time for current-state "
    "questions, and keep superseded states available when the question asks "
    "about history or how something changed.]"
)


def run_warned_direct(instance, generator, retriever_cls=BM25Retriever) -> dict:
    """TRUE instruction-only control: identical dense direct read plus a
    staleness-awareness instruction appended to the question. (The `prompted`
    condition is NOT this — it is the legacy-engine sidecar-annotation arm;
    a referee pass caught the mislabel.)"""
    retriever = retriever_cls(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    gen = generator.generate(
        instance.question + _WARN_INSTRUCTION, retrieved,
        instance.question_date)
    return {
        "answer": gen.answer,
        "usage_input_tokens": gen.usage_input_tokens,
        "usage_output_tokens": gen.usage_output_tokens,
        "retrieved_memory_ids": [m.memory_id for m in retrieved],
    }


def run_full_context_direct(instance, generator) -> dict:
    """Iso-cost skeptic baseline: the ENTIRE haystack in the prompt, no
    retrieval — spends the same order of input budget as QVF's extraction."""
    gen = generator.generate(
        instance.question, list(instance.memories), instance.question_date)
    return {
        "answer": gen.answer,
        "usage_input_tokens": gen.usage_input_tokens,
        "usage_output_tokens": gen.usage_output_tokens,
        "retrieved_memory_ids": [m.memory_id for m in instance.memories],
    }


_USE_MMR = False


def _norm_val(v: str) -> str:
    return " ".join(str(v).lower().split())


def _slot_ok_top(s, qslot):
    s = _norm_val(s)
    return bool(s) and bool(qslot) and (s == qslot or s in qslot or qslot in s)


# Slot-mutability prior (ConflictBank-style): these attributes cannot change,
# so two values are ALWAYS a disagreement — recency ("latest wins") is never
# licensed, whatever the wording. ~30 deterministic lines, zero LLM calls.
_IMMUTABLE_SLOT_RE = re.compile(
    r"(birth\s*(date|day|place|year)|born|date\s*of\s*birth|"
    r"mother|father|parent|sibling|brother|sister|"
    r"gender|sex\b|blood\s*type|ethnicity|zodiac|"
    r"native\s*(language|place)|home\s*town|hometown|"
    r"maiden\s*name)", re.IGNORECASE)


def _immutable_slot(slot):
    return bool(_IMMUTABLE_SLOT_RE.search(str(slot or "")))


def _corroboration_note(records, qslot):
    """Count distinct source rounds asserting each value of the query slot.
    Truth-discovery lite: support count is explicit evidence the reader may
    weigh, instead of an uncontrolled frequency bias."""
    support = {}
    for r in records:
        if not _slot_ok_top(r.slot, qslot) or not r.value:
            continue
        v = _norm_val(r.value)
        support.setdefault(v, (r.value, set()))
        support[v][1].add(r.source_memory_id)
    multi = {k: v for k, v in support.items() if v[1]}
    if len(multi) < 2:
        return ""
    parts = "; ".join(
        f"'{v[0]}' asserted in {len(v[1])} separate round(s)"
        for v in sorted(multi.values(), key=lambda x: -len(x[1]))[:4])
    return (f"\n\n[Corroboration count from the record layer: {parts}. "
            f"Weigh independent support, not recency, for facts that "
            f"cannot change.]")


def _stated_date_key(r):
    """Fallback date for a record whose source round has no usable
    timestamp: the date stated IN the text (contract field stated_date).
    Returns (yyyy, mm, dd) or None."""
    sd = str(getattr(r, "stated_date", "") or "").strip()
    mm = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", sd)
    if not mm:
        return None
    return (int(mm.group(1)), int(mm.group(2) or 1), int(mm.group(3) or 1))


QUERY_GATE_SYSTEM = """\
You classify one user question for a long-term-memory assistant. Reply with
ONLY a JSON object {"invoke": true} or {"invoke": false}.

invoke=true  -> the question asks for the CURRENT state of something that may
                have been updated over time (address, job, plan, preference,
                device, subscription...), where an outdated memory could
                mislead the answer.
invoke=false -> the question asks about history or the past (when something
                happened, how long, what came first, how a value changed),
                asks for a count/total/aggregate over time, or is otherwise
                not about a possibly-updated current state.
"""

_GATE_CLIENT = None
_CONTRA_READER = None


def _contradiction_reader():
    return _CONTRA_READER


def query_gate(question: str) -> tuple[bool, int, int]:
    """Cheap query-only risk gate (~300 tokens, temp 0). Fail-open: any
    parse/API failure returns invoke=True so the guard never silently
    disables itself."""
    global _GATE_CLIENT
    import anthropic

    if _GATE_CLIENT is None:
        _GATE_CLIENT = anthropic.Anthropic()
    try:
        resp = _GATE_CLIENT.messages.create(
            model="claude-haiku-4-5",
            max_tokens=64,
            temperature=0.0,
            system=QUERY_GATE_SYSTEM,
            messages=[{"role": "user", "content": question}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        invoke = json.loads(text[text.index("{"):text.rindex("}") + 1])["invoke"]
        return bool(invoke), resp.usage.input_tokens, resp.usage.output_tokens
    except Exception:  # noqa: BLE001
        return True, 0, 0


def _expand_siblings(retrieved, memories, radius: int = 2):
    """Attach same-session neighbor rounds to each retrieved round (the
    forensics found 22/26 retrieval misses had the answer in a sibling round
    already adjacent to a retrieved one)."""
    pos = {m.memory_id: i for i, m in enumerate(memories)}
    keep = set()
    for m in retrieved:
        i = pos.get(m.memory_id)
        if i is None:
            continue
        sess = m.memory_id.split("#")[0]
        for j in range(max(0, i - radius), min(len(memories), i + radius + 1)):
            if memories[j].memory_id.split("#")[0] == sess:
                keep.add(j)
    return [memories[j] for j in sorted(keep)]


_ESCALATE_ROUTES = ("rules_conflict_latest", "rules_admit", "rules_no_records",
                    "rules_admit_noop")


def run_minimal_rules_escalated(instance, extractor, strong_extractor,
                                validated_reader, conflict_reader,
                                fallback_generator,
                                subtractive: bool = False,
                                premise_note: bool = False) -> dict:
    """Targeted escalation: run v5 with the cheap extractor; if the case lands
    on a measured dead route (conflict/admit/no_records), redo it with a
    stronger extractor. Pays the big-model price only on hard cases."""
    rec = run_minimal_rules(
        instance, extractor, validated_reader, conflict_reader,
        fallback_generator, scope_gate=True,
        subtractive=subtractive, premise_note=premise_note,
    )
    if rec.get("filter_strategy") in _ESCALATE_ROUTES:
        rec2 = run_minimal_rules(
            instance, strong_extractor, validated_reader, conflict_reader,
            fallback_generator, scope_gate=True,
            subtractive=subtractive, premise_note=premise_note,
        )
        rec2["escalated"] = True
        rec2["usage_input_tokens"] += rec.get("usage_input_tokens", 0)
        rec2["usage_output_tokens"] += rec.get("usage_output_tokens", 0)
        rec2["pre_escalation_strategy"] = rec.get("filter_strategy")
        return rec2
    rec["escalated"] = False
    return rec


def run_ledger_v8(instance, ledger_store, validated_reader,
                  fallback_generator) -> dict:
    """v8 write-time ledger: sessions were indexed at write time (query-blind,
    LLM-extracted, disk-cached); query time is a slot lookup + date-ordered
    adjudication + the usual physical delivery. No query-time extraction."""
    import anthropic as _anthropic

    uid = instance.question_id.rsplit("_", 2)[0]
    ledger = ledger_store.index_item(uid, instance.memories)
    lin, lout = ledger_store.last_index_tokens
    record = {
        "usage_input_tokens": lin,
        "usage_output_tokens": lout,
        "ledger_records": len(ledger),
        "ledger_index_cached": lin == 0,
        "repair_triggered": False,
        "repair_added_ids": [],
        "retrieved_memory_ids": [],
    }
    slots = sorted({r["slot"] for r in ledger})
    from qvf.engine_bridge import LEDGER_SLOT_PICK_PROMPT
    global _GATE_CLIENT
    if _GATE_CLIENT is None:
        _GATE_CLIENT = _anthropic.Anthropic()
    picked, scope = [], "current"
    try:
        resp = _GATE_CLIENT.messages.create(
            model="claude-haiku-4-5", max_tokens=200, temperature=0.0,
            system=LEDGER_SLOT_PICK_PROMPT,
            messages=[{"role": "user", "content":
                       f"QUESTION: {instance.question}\n\nAVAILABLE SLOTS: {json.dumps(slots)}"}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        picked = [s for s in obj.get("slots", []) if s in slots]
        scope = obj.get("scope", "current")
        record["usage_input_tokens"] += resp.usage.input_tokens
        record["usage_output_tokens"] += resp.usage.output_tokens
    except Exception:  # noqa: BLE001
        pass
    record["ledger_slots_picked"] = picked
    record["query_temporal_scope"] = scope

    by_id = {m.memory_id: m for m in instance.memories}

    def _deliver(mem_ids, strategy):
        mems = [by_id[i] for i in sorted(mem_ids, key=lambda x: list(by_id).index(x))
                if i in by_id]
        record["filter_strategy"] = strategy
        record["filtered_memory_ids"] = [m.memory_id for m in mems]
        gen = validated_reader.generate(
            instance.question, mems, instance.question_date
        )
        record["answer"] = gen.answer
        record["usage_input_tokens"] += gen.usage_input_tokens
        record["usage_output_tokens"] += gen.usage_output_tokens
        record["fallback_used"] = False
        return record

    def _fallback(strategy):
        retriever = _dense_retriever_cls()(instance.memories)
        retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
        record["retrieved_memory_ids"] = [m.memory_id for m in retrieved]
        record["filter_strategy"] = strategy
        record["filtered_memory_ids"] = [m.memory_id for m in retrieved]
        gen = fallback_generator.generate(
            instance.question, retrieved, instance.question_date
        )
        record["answer"] = gen.answer
        record["usage_input_tokens"] += gen.usage_input_tokens
        record["usage_output_tokens"] += gen.usage_output_tokens
        record["fallback_used"] = True
        return record

    matching = [r for r in ledger if r["slot"] in picked]
    if scope == "past_or_change":
        if matching:
            return _deliver({r["source_memory_id"] for r in matching},
                            "ledger_pass_history")
        return _fallback("ledger_pass_history_fallback")
    if not matching:
        return _fallback("ledger_no_slot")

    def _datekey(r):
        m = re.search(r"(\d{4})[^\d](\d{1,2})[^\d](\d{1,2})", r.get("date") or "")
        return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)

    values = {_norm_val(r["value"]) for r in matching}
    if len(values) == 1:
        return _deliver({r["source_memory_id"] for r in matching},
                        "ledger_single_value")
    latest = max(_datekey(r) for r in matching)
    keep = {r["source_memory_id"] for r in matching if _datekey(r) == latest}
    return _deliver(keep, "ledger_surgery")


def run_qvf_final(instance, extractor, strong_extractor, validated_reader,
                  conflict_reader, fallback_generator) -> dict:
    """Release config: risk gate -> base pipeline with subtractive delivery
    (generalization-safe) -> dead-route cases escalate to the strong extractor
    with selective delivery (trap-sharp). Composition follows the measured
    interaction: subtractive helps the base branch, hurts the escalated one."""
    invoke, gin, gout = query_gate(instance.question)
    if not invoke:
        rec = run_direct(
            instance, fallback_generator, retriever_cls=_dense_retriever_cls()
        )
        rec["filter_strategy"] = "gate_direct"
        rec["fallback_used"] = False
        rec["gate_invoked"] = False
    else:
        rec = run_minimal_rules(
            instance, extractor, validated_reader, conflict_reader,
            fallback_generator, scope_gate=True, subtractive=True,
        )
        rec["gate_invoked"] = True
        if rec.get("filter_strategy") in _ESCALATE_ROUTES:
            rec2 = run_minimal_rules(
                instance, strong_extractor, validated_reader, conflict_reader,
                fallback_generator, scope_gate=True, subtractive=False,
            )
            rec2["gate_invoked"] = True
            rec2["escalated"] = True
            rec2["usage_input_tokens"] += rec.get("usage_input_tokens", 0)
            rec2["usage_output_tokens"] += rec.get("usage_output_tokens", 0)
            rec2["pre_escalation_strategy"] = rec.get("filter_strategy")
            rec = rec2
        else:
            rec["escalated"] = False
    rec["usage_input_tokens"] = rec.get("usage_input_tokens", 0) + gin
    rec["usage_output_tokens"] = rec.get("usage_output_tokens", 0) + gout
    return rec


def run_qvf_final_routed(instance, extractor, strong_extractor,
                         validated_reader, conflict_reader,
                         fallback_generator, reasoning_conflict_reader) -> dict:
    """Release config + residual routing, each choice backed by measured
    route accuracies: post-escalation conflict residues (53% w/ haiku) go to a
    reasoning reader (exploits conflict annotations); post-escalation admit
    residues (11% selective) fall back to full pass-through (~direct level)."""
    rec = run_qvf_final(
        instance, extractor, strong_extractor, validated_reader,
        conflict_reader, fallback_generator,
    )
    if not rec.get("escalated"):
        return rec
    strategy = rec.get("filter_strategy")
    by_id = {m.memory_id: m for m in instance.memories}
    if strategy == "rules_conflict_latest":
        mems = [by_id[i] for i in rec.get("filtered_memory_ids", []) if i in by_id]
        gen = reasoning_conflict_reader.generate(
            instance.question, mems, instance.question_date
        )
        rec["answer"] = gen.answer
        rec["usage_input_tokens"] += gen.usage_input_tokens
        rec["usage_output_tokens"] += gen.usage_output_tokens
        rec["residual_route"] = "conflict->reasoning_reader"
    elif strategy in ("rules_admit", "rules_no_records"):
        mems = [by_id[i] for i in rec.get("retrieved_memory_ids", []) if i in by_id]
        if mems:
            gen = fallback_generator.generate(
                instance.question, mems, instance.question_date
            )
            rec["answer"] = gen.answer
            rec["usage_input_tokens"] += gen.usage_input_tokens
            rec["usage_output_tokens"] += gen.usage_output_tokens
            rec["residual_route"] = "admit->pass_through"
    return rec


def run_conditional_v5(instance, extractor, validated_reader, conflict_reader,
                       fallback_generator) -> dict:
    """Conditional invocation: a query-only gate decides per query whether to
    run the full v5 pipeline (current-state risk) or answer directly from the
    dense context (history/aggregate/other). Turns the always-on x2.5-3 cost
    multiplier into a marginal cost on risky queries only."""
    invoke, gin, gout = query_gate(instance.question)
    if invoke:
        rec = run_minimal_rules(
            instance, extractor, validated_reader, conflict_reader,
            fallback_generator, scope_gate=True,
        )
    else:
        rec = run_direct(
            instance, fallback_generator, retriever_cls=_dense_retriever_cls()
        )
        rec["filter_strategy"] = "gate_direct"
        rec["fallback_used"] = False
    rec["gate_invoked"] = invoke
    rec["usage_input_tokens"] = rec.get("usage_input_tokens", 0) + gin
    rec["usage_output_tokens"] = rec.get("usage_output_tokens", 0) + gout
    return rec


def run_extraction_only(instance, extractor, fallback_generator) -> dict:
    """Confound control (motivated by Presentation-Not-Mechanism's render
    confound): identical retrieval and the SAME scoped extractor call as
    minimal_rules_v5, but NO gate, NO adjudication, NO surgery — the reader
    sees the full retrieved context plus the extracted records rendered
    neutrally (entity/slot/value/date, no relation labels, no admit/block).
    If this arm reproduces the QVF gain, the gain is extraction+annotation;
    if it stays at baseline, selection/surgery is the active ingredient."""
    retriever = _dense_retriever_cls()(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    extraction, ein, eout = extractor.extract(
        instance.question, retrieved, instance.question_date, scoped=True
    )
    lines = []
    for r in extraction.records:
        src = next(
            (m for m in retrieved if m.memory_id == r.source_memory_id), None
        )
        date = str((src.metadata or {}).get("session_date") or "") if src else ""
        lines.append(f"- [{date}] {r.entity} / {r.slot} = {r.value} "
                     f"(from {r.source_memory_id})")
    notes = "\n".join(lines) if lines else "(no records extracted)"
    question = (
        f"{instance.question}\n\n"
        "Structured notes extracted from the memories above "
        f"(neutral, for reference):\n{notes}"
    )
    gen = fallback_generator.generate(question, retrieved, instance.question_date)
    return {
        "usage_input_tokens": ein + gen.usage_input_tokens,
        "usage_output_tokens": eout + gen.usage_output_tokens,
        "extracted_record_count": len(extraction.records),
        "query_temporal_scope": getattr(
            extraction.query_focus, "query_temporal_scope", None
        ),
        "filter_strategy": "extraction_only_neutral",
        "retrieved_memory_ids": [m.memory_id for m in retrieved],
        "fallback_used": False,
        "answer": gen.answer,
    }


def run_minimal_rules(instance, extractor, validated_reader, conflict_reader,
                      fallback_generator, scope_gate: bool = False,
                      contract: str = "v5", agg_guard: bool = False,
                      sibling_expand: bool = False,
                      subtractive: bool = False,
                      premise_note: bool = False,
                      repair_slotted: bool = False,
                      abstain_guard: bool = False,
                      strong_extractor=None) -> dict:
    """Engine-ablation: identical retrieval/repair/extraction to qvf_v4, but
    adjudication is ~30 lines of plain Python instead of the symbolic engine.
    Measures the engine's net contribution.

    scope_gate=True (v5): the extractor additionally classifies the query's
    temporal scope; history-seeking queries (past state / change / duration /
    event order) bypass surgery entirely — their old states are evidence, not
    stale noise. Motivated by pre-registered risk, confirmed on LME
    temporal-reasoning losses where surgery removed rounds the reader needed."""
    retriever = _dense_retriever_cls()(instance.memories)
    if _USE_MMR and hasattr(retriever, "retrieve_mmr"):
        retrieved = retriever.retrieve_mmr(instance.question, top_k=TOP_K)
    else:
        retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    if sibling_expand:
        retrieved = _expand_siblings(retrieved, instance.memories)
    if agg_guard and _AGG_QUERY_RE.search(instance.question):
        # Aggregation questions (how many/total/since) are history
        # aggregations: pass through BEFORE paying for extraction.
        gen = fallback_generator.generate(
            instance.question, retrieved, instance.question_date
        )
        return {
            "usage_input_tokens": gen.usage_input_tokens,
            "usage_output_tokens": gen.usage_output_tokens,
            "repair_triggered": False,
            "repair_added_ids": [],
            "extracted_record_count": 0,
            "filter_strategy": "scope_pass_aggregation",
            "filtered_memory_ids": [m.memory_id for m in retrieved],
            "retrieved_memory_ids": [m.memory_id for m in retrieved],
            "fallback_used": False,
            "answer": gen.answer,
        }
    extraction, ein, eout = extractor.extract(
        instance.question, retrieved, instance.question_date,
        scoped=scope_gate, contract=contract,
    )
    record = {
        "usage_input_tokens": ein,
        "usage_output_tokens": eout,
        "repair_triggered": False,
        "repair_added_ids": [],
    }
    _scan_ok = _scan_taker()
    triage = getattr(extraction, "memory_triage", None)
    if triage is not None:
        record["triage_counts"] = {
            k: sum(1 for t in triage if t.mentions_query_slot == k)
            for k in ("yes", "maybe", "no")
        }

    if abstain_guard and contract == "species2":
        # No-valid-record abstention guard: when NOT ONE extracted record
        # matches the query slot, the question may presuppose something the
        # history never stated (LoCoMo category-5 style trap). Soft guard:
        # the reader keeps every retrieved round and may still answer if the
        # fact is there — the note only licenses declining over guessing.
        _q_norm = _norm_val(extraction.query_focus.slot)

        def _s_ok(s):
            s = _norm_val(s)
            return bool(s) and bool(_q_norm) and (
                s == _q_norm or s in _q_norm or _q_norm in s)

        if not any(_s_ok(r.slot) and r.value for r in extraction.records):
            gen = fallback_generator.generate(
                f"{instance.question}\n\n[Validity check: none of the "
                f"retrieved memory records states a value for "
                f"'{extraction.query_focus.slot}' of "
                f"'{extraction.query_focus.entity}'. If the conversation "
                f"history truly does not mention this, say the information "
                f"is not available rather than guessing.]",
                retrieved, instance.question_date,
            )
            record.update({
                "extracted_record_count": len(extraction.records),
                "filter_strategy": "no_valid_record_note",
                "filtered_memory_ids": [m.memory_id for m in retrieved],
                "retrieved_memory_ids": [m.memory_id for m in retrieved],
                "fallback_used": False,
                "answer": gen.answer,
            })
            record["usage_input_tokens"] += gen.usage_input_tokens
            record["usage_output_tokens"] += gen.usage_output_tokens
            return record

    if scope_gate:
        scope = getattr(extraction.query_focus, "query_temporal_scope", "unclear")
        record["query_temporal_scope"] = scope
        if contract == "species2" and scope != "past_or_change":
            # Explicit-date override: a question naming a specific past
            # date/month ("in May, 1986", "on 2025-04-10") is point-in-time
            # seeking, whatever the extractor classified. Deterministic
            # signal beats LLM scope judgment; replacement surgery on such
            # a question deletes exactly the evidence it needs.
            _dm = (re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b",
                             instance.question)
                   or re.search(
                       r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov"
                       r"|Dec)[a-z]*\.?,?\s+\d{4}\b", instance.question))
            if _dm:
                scope = "past_or_change"
                record["scope_overridden_by_date"] = True
        if scope == "past_or_change":
            question = instance.question
            strategy = "scope_pass_history"
            if contract == "species2":
                # Trajectory/point-in-time routes with chain-completion
                # retrieval: the earliest state is usually ranked out of
                # top-10 by change-question wording (pilot forensics: 5/6
                # trajectory failures were incomplete chains in the note).
                qslot = _norm_val(extraction.query_focus.slot)

                def _slot_ok(s):
                    s = _norm_val(s)
                    return bool(s) and (s == qslot or s in qslot or qslot in s)

                def _chain_of(extr, mems_by_id):
                    def dk(r):
                        src = mems_by_id.get(r.source_memory_id)
                        raw = str((src.metadata or {}).get("session_date") or "") if src else ""
                        mm = re.search(r"(\d{4})[^\d](\d{1,2})[^\d](\d{1,2})", raw)
                        if mm:
                            return (tuple(int(g) for g in mm.groups()), raw)
                        sd = _stated_date_key(r)
                        if sd:
                            return (sd, getattr(r, "stated_date", ""))
                        return ((0, 0, 0), raw)
                    ch = [r for r in extr.records
                          if _slot_ok(r.slot) and r.value]
                    ch.sort(key=lambda r: dk(r)[0])
                    return ch, dk

                by_mem = {m.memory_id: m for m in retrieved}
                chain, _dk = _chain_of(extraction, by_mem)

                def _mdate(m):
                    raw = str((m.metadata or {}).get("session_date") or "")
                    mm = re.search(r"(\d{4})[^\d](\d{1,2})[^\d](\d{1,2})", raw)
                    return tuple(int(g) for g in mm.groups()) if mm else None

                def _dk_over(mems_by_id):
                    def dk(r):
                        src = mems_by_id.get(r.source_memory_id)
                        raw = str((src.metadata or {}).get("session_date") or "") if src else ""
                        mm = re.search(r"(\d{4})[^\d](\d{1,2})[^\d](\d{1,2})", raw)
                        if mm:
                            return (tuple(int(g) for g in mm.groups()), raw)
                        sd = _stated_date_key(r)
                        if sd:
                            return (sd, getattr(r, "stated_date", ""))
                        return ((0, 0, 0), raw)
                    return dk

                # Sweep extraction calls must NOT re-derive the query slot:
                # on distractor-heavy windows the extractor drifts (e.g.
                # 'programming language at work' -> 'work_language_style',
                # then extracts writing style). Pin the already-known focus.
                focus_q = (
                    f"{instance.question}\n[Extraction focus: the query slot "
                    f"is '{extraction.query_focus.slot}' of "
                    f"'{extraction.query_focus.entity}'. Extract EVERY "
                    f"message stating a value this slot held at some time, "
                    f"with its date. Match the slot by MEANING, not wording "
                    f"— the text may use a synonymous term (mayor = head of "
                    f"a city, chairman = chair, club = team, works at = "
                    f"employer). Use this exact slot name in the records.]"
                )

                def _merge_reextract(fresh, tag):
                    """Merge new rounds and re-extract. If the fresh chain is
                    at least as long, replace (re-extraction with more context
                    often consolidates spurious records); otherwise union the
                    unseen records in — never lose a state already found."""
                    nonlocal chain, _dk, retrieved
                    if not fresh:
                        return
                    if not _scan_ok():
                        return
                    merged = retrieved + fresh
                    extraction2, ein3, eout3 = extractor.extract(
                        focus_q, merged, instance.question_date,
                        contract="species2",
                    )
                    record["usage_input_tokens"] += ein3
                    record["usage_output_tokens"] += eout3
                    mmap = {m.memory_id: m for m in merged}
                    chain2, dk2 = _chain_of(extraction2, mmap)
                    if len(chain2) >= len(chain):
                        chain, _dk = chain2, dk2
                        retrieved = merged
                        record[tag] = len(fresh)
                        return
                    seen = {(r.source_memory_id, _norm_val(r.value))
                            for r in chain}
                    extra = [r for r in chain2
                             if (r.source_memory_id, _norm_val(r.value))
                             not in seen]
                    if extra:
                        dku = _dk_over(mmap)
                        grown = sorted(chain + extra, key=lambda r: dku(r)[0])
                        chain, _dk = grown, dku
                        retrieved = merged
                        record[tag] = len(fresh)

                def _resweep(query, tag, before=None, upto=None):
                    """Dense sweep: top-30 for `query`, merge <=6 new rounds.
                    `upto` hard-filters to session_date <= upto; `before`
                    soft-prefers rounds predating the earliest known state
                    (the diagnosed recall hole)."""
                    cands = retriever.retrieve(query, top_k=30)
                    have = {m.memory_id for m in retrieved}
                    fresh = [m for m in cands if m.memory_id not in have]
                    if upto is not None:
                        fresh = [m for m in fresh
                                 if (_mdate(m) or (9999,)) <= upto]
                    elif before is not None and before > (0, 0, 0):
                        fresh.sort(
                            key=lambda m: (_mdate(m) or (9999,)) >= before)
                    _merge_reextract(fresh[:6], tag)

                def _sibling_sweep(tag):
                    """Deterministic completion: the state statement often
                    lives in ANOTHER round of a session the chain already
                    touches (extractor caught a diet-adjacent remark but the
                    actual change statement is the neighbouring round). Zero
                    retrieval involved."""
                    def _sess_key(mid):
                        # round ids "uid/s3#r0" -> "uid/s3"; document chunk
                        # ids "rid/doc:X:p4" -> "rid/doc:X".
                        return re.sub(r":p\d+$", "", mid.split("#")[0])

                    have = {m.memory_id for m in retrieved}
                    sess = {_sess_key(r.source_memory_id) for r in chain}
                    sibs = [m for m in instance.memories
                            if _sess_key(m.memory_id) in sess
                            and m.memory_id not in have]
                    _merge_reextract(sibs[:10], tag)

                def _extract_sweep(tag, upto=None, before=None):
                    """LLM-recognition sweep. Embeddings miss state values the
                    query cannot name (a round saying 'started doing keto'
                    ranks outside top-30 for 'user diet'), so: date-filter the
                    FULL haystack in code, cap by dense rank, and let the
                    extractor recognize slot states in the window. Rounds it
                    grounds records in get merged; no re-extraction needed."""
                    nonlocal chain, _dk, retrieved
                    have = {m.memory_id for m in retrieved}
                    window = []
                    for m in instance.memories:
                        if m.memory_id in have:
                            continue
                        d = _mdate(m)
                        # Unknown date PASSES the filters: the date filter is
                        # an optimization, not a correctness gate — undated
                        # document chunks must stay reachable.
                        if d is not None:
                            if upto is not None and d > upto:
                                continue
                            if before is not None and d >= before:
                                continue
                        window.append(m)
                    if not window:
                        return
                    if not _scan_ok():
                        return
                    if len(window) > 36:
                        ranked = {m.memory_id: i for i, m in enumerate(
                            retriever.retrieve(
                                f"{extraction.query_focus.entity} "
                                f"{extraction.query_focus.slot}",
                                top_k=len(instance.memories)))}
                        window.sort(key=lambda m: ranked.get(m.memory_id, 10**6))
                        window = window[:36]
                    ex3, ein3, eout3 = extractor.extract(
                        focus_q, window, instance.question_date,
                        contract="species2",
                    )
                    record["usage_input_tokens"] += ein3
                    record["usage_output_tokens"] += eout3
                    wmap = {m.memory_id: m for m in window}
                    hits = [r for r in ex3.records
                            if _slot_ok(r.slot) and r.value
                            and r.source_memory_id in wmap]
                    record.setdefault("recog_debug", []).append({
                        "tag": tag, "n_window": len(window),
                        "win": [m.memory_id.split("/")[-1] for m in window],
                        "raw_recs": [(r.slot, r.value,
                                      str(r.source_memory_id).split("/")[-1])
                                     for r in ex3.records],
                    })
                    if not hits:
                        return
                    add_ids = list(dict.fromkeys(
                        r.source_memory_id for r in hits))[:6]
                    merged = retrieved + [wmap[i] for i in add_ids]
                    combined = {m.memory_id: m for m in merged}

                    dk3 = _dk_over(combined)

                    seen_pairs = {(c.source_memory_id, _norm_val(c.value))
                                  for c in chain}
                    grown = chain + [
                        r for r in hits
                        if (r.source_memory_id, _norm_val(r.value))
                        not in seen_pairs and r.source_memory_id in combined]
                    grown.sort(key=lambda r: dk3(r)[0])
                    chain, _dk = grown, dk3
                    retrieved = merged
                    record[tag] = len(add_ids)

                if chain:
                    sweep_q = (f"{extraction.query_focus.entity} "
                               f"{extraction.query_focus.slot} earlier previous "
                               f"before: " + "; ".join(r.value for r in chain[:3]))
                    _resweep(sweep_q, "chain_sweep_added",
                             before=_dk(chain[0])[0])
                    _sibling_sweep("sib_sweep_added")
                # Recognition pass over the whole undelivered haystack
                # (capped by dense rank): catches missing chain HEADS and
                # missing MIDDLE states alike — and when the main extraction
                # found NOTHING (chain empty), this is the only mechanism
                # that can build the chain at all.
                _extract_sweep("recog_sweep_added")
                if (not chain and strong_extractor is not None
                        and _scan_ok()):
                    # Dead-route escalation: cheap extractor found no state
                    # of the query slot anywhere. Re-extract with the strong
                    # extractor over a WIDENED pool (delivered + top-36
                    # undelivered by dense rank) — the failing layer can be
                    # perception OR retrieval, so widen both at once.
                    have = {m.memory_id for m in retrieved}
                    wide = [m for m in instance.memories
                            if m.memory_id not in have]
                    if len(wide) > 36:
                        ranked = {m.memory_id: i for i, m in enumerate(
                            retriever.retrieve(
                                f"{extraction.query_focus.entity} "
                                f"{extraction.query_focus.slot}",
                                top_k=len(instance.memories)))}
                        wide.sort(key=lambda m: ranked.get(m.memory_id, 10**6))
                        wide = wide[:36]
                    pool = retrieved + wide
                    ex4, ein4, eout4 = strong_extractor.extract(
                        focus_q, pool, instance.question_date,
                        contract="species2",
                    )
                    record["usage_input_tokens"] += ein4
                    record["usage_output_tokens"] += eout4
                    record["escalated_extraction"] = True
                    pmap = {m.memory_id: m for m in pool}
                    chain, _dk = _chain_of(ex4, pmap)
                    if chain:
                        add = [pmap[i] for i in dict.fromkeys(
                            r.source_memory_id for r in chain)
                            if i in pmap and i not in have][:8]
                        retrieved = retrieved + add

                vals = {_norm_val(r.value) for r in chain}
                pm = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", instance.question)
                if pm:
                    pdate = tuple(int(g) for g in pm.groups())
                    pstr = pm.group(0)
                else:
                    # Month-name form ("in Jan, 1948" / "in March 2010"):
                    # resolve to end-of-month so a state starting that month
                    # still counts as valid at the asked time.
                    mn = re.search(
                        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                        r"[a-z]*\.?,?\s+(\d{4})\b", instance.question)
                    if mn:
                        month = ("jan feb mar apr may jun jul aug sep oct "
                                 "nov dec").split().index(
                                     mn.group(1).lower()[:3]) + 1
                        pdate = (int(mn.group(2)), month, 31)
                        pstr = mn.group(0)
                    else:
                        pdate, pstr = None, None
                record["chain_len"] = len(chain)
                record["chain_qslot"] = extraction.query_focus.slot
                record["chain_vals"] = [
                    (r.value, _dk(r)[1] or "undated") for r in chain]
                record["pm_matched"] = pdate is not None
                if pdate and vals:
                    # Deterministic point-in-time slice: interval arithmetic
                    # is code's job, not the reader's.
                    # Falsified alternative (2026-08-04): splitting dated vs
                    # undated records and hedging the note when undated ones
                    # exist LOST net 4 questions on TempReason-raw (38% vs
                    # 44%) — the hard note's reader compliance outweighs the
                    # incomplete-date risk. Keep the simple selection.
                    valid = None
                    for r in chain:
                        if _dk(r)[0] <= pdate:
                            valid = r
                    if valid is None:
                        # Every extracted state postdates the asked date:
                        # the chain head is missing. Recognition sweep over
                        # rounds dated on/before the asked date.
                        _extract_sweep("time_sweep_added", upto=pdate)
                        record["chain_len"] = len(chain)
                        for r in chain:
                            if _dk(r)[0] <= pdate:
                                valid = r
                    if valid is not None:
                        nxt = None
                        for r in chain:
                            if _dk(r)[0] > pdate:
                                nxt = r
                                break
                        until = (f", and it stayed so until {_dk(nxt)[1]} "
                                 f"(next change: {nxt.value})" if nxt else "")
                        question = (
                            f"{instance.question}\n\n[Deterministic validity "
                            f"resolution from dated memory records: on "
                            f"{pstr}, {extraction.query_focus.slot} "
                            f"was {valid.value} — it was recorded on "
                            f"{_dk(valid)[1]}{until}. This IS the answer to "
                            f"the question; do not reply that information "
                            f"for that date is unavailable.]"
                        )
                        strategy = "scope_pass_point_in_time"
                    else:
                        question = (
                            f"{instance.question}\n\n[Validity note: the "
                            f"extracted records of "
                            f"{extraction.query_focus.slot} all postdate "
                            f"{pstr}; earliest known is "
                            f"{chain[0].value} ({_dk(chain[0])[1] or 'undated'}). "
                            f"The answer is likely an EARLIER state — check "
                            f"the raw conversation history for one.]"
                        )
                        strategy = "scope_pass_point_predates"
                elif len(vals) >= 2:
                    # Containment dedup: 'vegan' / 'vegan diet' or a value
                    # plus its elaborated variant are one state, not two.
                    dedup = []
                    for r in chain:
                        nv = _norm_val(r.value)
                        if any(nv == d or nv in d or d in nv
                               for d, _ in dedup):
                            continue
                        dedup.append((nv, r))
                    if len(dedup) >= 2:
                        steps = " -> ".join(
                            f"{r.value} ({_dk(r)[1] or 'undated'})"
                            for _, r in dedup
                        )
                        question = (
                            f"{instance.question}\n\n[Memory chain for "
                            f"{extraction.query_focus.slot}: {steps}. When "
                            f"asked how something changed, list every "
                            f"recorded state in order with dates.]"
                        )
                        strategy = "scope_pass_trajectory"
            record.update(
                {
                    "extracted_record_count": len(extraction.records),
                    "filter_strategy": strategy,
                    "filtered_memory_ids": [m.memory_id for m in retrieved],
                    "retrieved_memory_ids": [m.memory_id for m in retrieved],
                    "fallback_used": False,
                }
            )
            gen = fallback_generator.generate(
                question, retrieved, instance.question_date
            )
            record["answer"] = gen.answer
            record["usage_input_tokens"] += gen.usage_input_tokens
            record["usage_output_tokens"] += gen.usage_output_tokens
            return record

    def has_repl(extr):
        return any(
            r.temporal_relation in ("replacement", "correction") for r in extr.records
        )

    if extraction.query_focus.needs_current and not has_repl(extraction):
        record["repair_triggered"] = True
        from qvf.engine_bridge import build_repair_query_dense

        if repair_slotted:
            # Slot-aware repair query: anchor on the entity/slot and contrast
            # against the already-known (possibly stale) values. The generic
            # template yielded decisive retrievals in only 7/202 firings.
            known = "; ".join(sorted({
                _norm_val(r.value) for r in extraction.records if r.value
            }))[:200]
            rq = (f"{extraction.query_focus.entity} "
                  f"{extraction.query_focus.slot} updated changed new current "
                  f"value, different from: {known or 'the old state'}")
        else:
            rq = build_repair_query_dense(extraction.query_focus)
        second = retriever.retrieve(rq, top_k=TOP_K)
        have = {m.memory_id for m in retrieved}
        added = [m for m in second if m.memory_id not in have][:5]
        record["repair_added_ids"] = [m.memory_id for m in added]
        if added and _scan_ok():
            merged = retrieved + added
            # scoped/contract must match the first extraction: switching
            # prompt/schema mid-pipeline was an uncontrolled confound
            # (fixed 2026-08-02).
            extraction, ein2, eout2 = extractor.extract(
                instance.question, merged, instance.question_date,
                scoped=scope_gate, contract=contract,
            )
            record["usage_input_tokens"] += ein2
            record["usage_output_tokens"] += eout2
            retrieved = merged

    rel = extraction.records
    repl = [r for r in rel if r.temporal_relation in ("replacement", "correction")]
    reader = validated_reader

    # Falsified (2026-08-05): a needs-current recognition sweep (re-extract
    # over a widened window when no replacement pair was found) merged ZERO
    # rounds across 105 dev questions — the admit_noop bucket's root cause
    # is not un-delivered old rounds; re-extraction still labels no
    # replacement. Removed to save one extraction call per dead route.

    if contract in ("species", "species2"):
        # Species adjudication, in precedence order. Each branch is the
        # minimal deterministic policy for one validity species.
        cess = [r for r in rel if r.temporal_relation == "cessation"]
        contra = [r for r in rel if r.temporal_relation == "contradiction"]
        by_rid_all = {r.record_id: r for r in rel}
        _qslot_top = _norm_val(extraction.query_focus.slot)
        if (contract == "species2" and rel
                and _immutable_slot(extraction.query_focus.slot)
                and len({_norm_val(r.value) for r in rel
                         if _slot_ok_top(r.slot, _qslot_top) and r.value}) > 1):
            # Immutable-slot disagreement: birthdate/siblings/etc. cannot be
            # "updated" — divergent values are misinformation-vs-truth, and
            # recency is never evidence. Deliver everything + corroboration
            # counts to the contradiction reader.
            note = _corroboration_note(rel, _qslot_top)
            record.update({
                "extracted_record_count": len(rel),
                "filter_strategy": "rules_immutable_disagreement",
                "filtered_memory_ids": [m.memory_id for m in retrieved],
                "retrieved_memory_ids": [m.memory_id for m in retrieved],
                "fallback_used": False,
            })
            gen = _contradiction_reader().generate(
                instance.question + note, retrieved, instance.question_date
            )
            record["answer"] = gen.answer
            record["usage_input_tokens"] += gen.usage_input_tokens
            record["usage_output_tokens"] += gen.usage_output_tokens
            return record
        if cess and not repl:
            # State ended: remove the ended state's rounds, keep the
            # cessation statement (it IS the current answer: "no longer X").
            stale = {
                by_rid_all[t].source_memory_id
                for r in cess for t in r.relation_target_record_ids
                if t in by_rid_all
            }
            filtered = [m for m in retrieved if m.memory_id not in stale]
            record.update({
                "extracted_record_count": len(rel),
                "filter_strategy": "rules_cessation",
                "filtered_memory_ids": [m.memory_id for m in filtered],
                "retrieved_memory_ids": [m.memory_id for m in retrieved],
                "fallback_used": False,
            })
            gen = validated_reader.generate(
                instance.question, filtered, instance.question_date
            )
            record["answer"] = gen.answer
            record["usage_input_tokens"] += gen.usage_input_tokens
            record["usage_output_tokens"] += gen.usage_output_tokens
            return record
        if not repl and rel and extraction.query_focus.needs_current:
            # Conditional applicability: if a record's condition matches the
            # query wording, ANNOTATE it — subtractive-delivery principle:
            # deliver everything (MemConflict forensics: keep-only-flagged
            # dropped 13-14/15 rounds and the reader answered "no info").
            conded = [r for r in rel if (r.condition or "").strip()]
            # Coexistence requires >=2 DISTINCT conditions on the slot; a
            # single conditioned record is not a conditional conflict
            # (STALE-400 forensics: loose trigger fired on 68 T1 questions
            # at 33.8% accuracy, rerouting genuine updates).
            if len({_norm_val(r.condition) for r in conded}) >= 2:
                qn = _norm_val(instance.question)
                hits = [r for r in conded
                        if any(w in qn for w in _norm_val(r.condition).split()
                               if len(w) > 3)]
                if len({r.source_memory_id for r in hits}) >= 1 and hits:
                    note = "; ".join(
                        f"'{r.value}' when {r.condition}" for r in conded[:4])
                    q2 = (f"{instance.question}\n\n[Condition-bound states "
                          f"on record: {note}. These COEXIST — answer for "
                          f"the condition the question asks about.]")
                    record.update({
                        "extracted_record_count": len(rel),
                        "filter_strategy": "rules_conditional",
                        "filtered_memory_ids": [m.memory_id for m in retrieved],
                        "retrieved_memory_ids": [m.memory_id for m in retrieved],
                        "fallback_used": False,
                    })
                    gen = validated_reader.generate(
                        q2, retrieved, instance.question_date
                    )
                    record["answer"] = gen.answer
                    record["usage_input_tokens"] += gen.usage_input_tokens
                    record["usage_output_tokens"] += gen.usage_output_tokens
                    return record
        if contra and not repl:
            # Factual disagreement: deliver EVERYTHING (subtractive
            # principle — the pair rounds alone starve the reader of
            # context), use the contradiction prompt (recency is NOT
            # evidence here).
            record.update({
                "extracted_record_count": len(rel),
                "filter_strategy": "rules_contradiction",
                "filtered_memory_ids": [m.memory_id for m in retrieved],
                "retrieved_memory_ids": [m.memory_id for m in retrieved],
                "fallback_used": False,
            })
            gen = _contradiction_reader().generate(
                instance.question, retrieved, instance.question_date
            )
            record["answer"] = gen.answer
            record["usage_input_tokens"] += gen.usage_input_tokens
            record["usage_output_tokens"] += gen.usage_output_tokens
            return record

    premise_note_text = ""
    if repl:
        targets = set()
        for r in repl:
            targets.update(r.relation_target_record_ids)
        if subtractive:
            # v5.1 subtractive delivery: remove ONLY the superseded rounds,
            # keep everything else. If the old state was never retrieved
            # (benign update), nothing is removed and delivery == direct —
            # structurally incapable of harming already-solved cases.
            by_rid = {r.record_id: r for r in rel}
            by_mid = {m.memory_id: m for m in retrieved}

            def _round_date(mid):
                m = by_mid.get(mid)
                raw = str((m.metadata or {}).get("session_date") or "") if m else ""
                mm = re.search(r"(\d{4})[^\d](\d{1,2})[^\d](\d{1,2})", raw)
                return tuple(int(g) for g in mm.groups()) if mm else None

            # Temporal sanity check on deletion: a round may be subtracted
            # only if it is STRICTLY OLDER than the round replacing it.
            # On near-identical texts (wiki-diff versions) the extractor
            # can invert the replacement direction and would otherwise
            # delete the current state along with the stale one.
            stale = set()
            for r in repl:
                rd = _round_date(r.source_memory_id)
                for t in r.relation_target_record_ids:
                    if t not in by_rid:
                        continue
                    tid = by_rid[t].source_memory_id
                    if tid == r.source_memory_id:
                        continue
                    td = _round_date(tid)
                    if rd is not None and td is not None and td >= rd:
                        continue
                    stale.add(tid)
            filtered = [m for m in retrieved if m.memory_id not in stale]
            strategy = ("rules_replacement_subtract" if stale
                        else "rules_replacement_noop")
            if contract == "species2":
                # Premise-refutation note. Error anatomy (chain held-out):
                # 88% of premise-trap failures ECHO the value the question
                # presupposes — memory surgery cannot reach a stale value
                # sitting in the QUESTION TEXT. When a superseded value
                # appears verbatim in the question, say so. (The earlier
                # premise_note attempt was falsified for lack of a trigger:
                # the old record was not extracted; the replacement pair now
                # supplies it.)
                qn = _norm_val(instance.question)
                for r in repl:
                    for t in r.relation_target_record_ids:
                        if t not in by_rid:
                            continue
                        ov = _norm_val(by_rid[t].value)
                        if ov and len(ov) > 3 and ov in qn \
                                and ov != _norm_val(r.value):
                            premise_note_text = (
                                f"\n\n[Premise check: the question assumes "
                                f"'{by_rid[t].value}', which is OUTDATED — "
                                f"it was later superseded by '{r.value}'. "
                                f"Answer from the CURRENT state, and note "
                                f"the premise is stale.]")
                            record["premise_flagged"] = True
                            break
                    if record.get("premise_flagged"):
                        break
        else:
            keep = {r.source_memory_id for r in repl}
            filtered = [m for m in retrieved if m.memory_id in keep]
            strategy = "rules_replacement"
    elif rel and len({_norm_val(r.value) for r in rel
                      if getattr(r, "slot_cardinality", "unknown")
                      != "set"}) > 1:
        # Distinct values among SINGLE-valued records = genuine conflict.
        # SET-valued slots (interests, hobbies) are excluded from the
        # trigger: their values COEXIST, and latest-wins adjudication
        # there is a category error (manufactured a confident wrong answer
        # on unanswerable LoCoMo traps).
        # Change-language check: latest-wins is only licensed when at
        # least one span actually SAYS something changed. Bare divergent
        # re-assertions (misinformation vs truth about an immutable fact,
        # e.g. two different birthdates) are a disagreement — recency is
        # not evidence there; route to the contradiction reader instead.
        _CHANGE_RE = re.compile(
            r"\b(moved|moving|switch\w*|chang\w*|no longer|anymore|"
            r"renamed|replac\w*|updat\w*|became|becomes|start\w*|"
            r"from now|instead)\b", re.IGNORECASE)
        has_change = any(
            _CHANGE_RE.search(str(getattr(r, "source_span", "") or ""))
            for r in rel)
        if subtractive:
            filtered = list(retrieved)  # keep all, flag the conflict
        else:
            keep = {r.source_memory_id for r in rel}
            filtered = [m for m in retrieved if m.memory_id in keep]
        if has_change:
            reader = conflict_reader or validated_reader
            strategy = "rules_conflict_latest"
        else:
            reader = _contradiction_reader()
            strategy = "rules_contradiction_bare"
    elif rel:
        if subtractive:
            filtered = list(retrieved)  # nothing superseded -> touch nothing
            strategy = "rules_admit_noop"
        else:
            keep = {r.source_memory_id for r in rel}
            filtered = [m for m in retrieved if m.memory_id in keep]
            strategy = "rules_admit"
    else:
        filtered = []
        strategy = "rules_no_records"

    record.update(
        {
            "extracted_record_count": len(rel),
            "filter_strategy": strategy,
            "filtered_memory_ids": [m.memory_id for m in filtered],
            "retrieved_memory_ids": [m.memory_id for m in retrieved],
        }
    )
    if filtered:
        gen = reader.generate(
            instance.question + premise_note_text, filtered,
            instance.question_date)
        record["fallback_used"] = False
    else:
        gen = fallback_generator.generate(
            instance.question + premise_note_text, retrieved,
            instance.question_date
        )
        record["fallback_used"] = True
    record["answer"] = gen.answer
    record["usage_input_tokens"] += gen.usage_input_tokens
    record["usage_output_tokens"] += gen.usage_output_tokens
    return record


_AGG_QUERY_RE = re.compile(
    r"\bhow (?:many|much|often|long)\b|\bin total\b|\bso far\b",
    re.IGNORECASE,
)


def _mem_date_key(mem):
    """Sortable (y, m, d) from a memory's session_date; None if unparseable."""
    raw = str((mem.metadata or {}).get("session_date") or "")
    m = re.search(r"(\d{4})[^\d](\d{1,2})[^\d](\d{1,2})", raw)
    return tuple(int(g) for g in m.groups()) if m else None


def run_minimal_rules_v6(instance, extractor, validated_reader, conflict_reader,
                         fallback_generator) -> dict:
    """v6 = v5 + three route fixes, each aimed at a measured dead route:
    (1) aggregation guard: how-many/total/since questions are history
        aggregations -> pass-through (a KU pilot loss came from surgering one);
    (2) conflict-route surgery: extraction-confirmed same-slot competition ->
        keep only the latest-dated record's rounds instead of keep-both+prompt
        (conflict route measured 33% vs surgery route 74-76%);
    (3) admit suspicion: a single-valued record set on a needs-current query
        means the competitor was likely missed by extraction -> full
        pass-through instead of keeping possibly-stale record rounds
        (admit route measured 0% across all slices).
    v5 is left untouched for protocol comparability."""
    retriever = _dense_retriever_cls()(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    extraction, ein, eout = extractor.extract(
        instance.question, retrieved, instance.question_date, scoped=True
    )
    record = {
        "usage_input_tokens": ein,
        "usage_output_tokens": eout,
        "repair_triggered": False,
        "repair_added_ids": [],
    }
    _scan_ok = _scan_taker()

    def _pass_through(strategy):
        record.update(
            {
                "extracted_record_count": len(extraction.records),
                "filter_strategy": strategy,
                "filtered_memory_ids": [m.memory_id for m in retrieved],
                "retrieved_memory_ids": [m.memory_id for m in retrieved],
                "fallback_used": False,
            }
        )
        gen = fallback_generator.generate(
            instance.question, retrieved, instance.question_date
        )
        record["answer"] = gen.answer
        record["usage_input_tokens"] += gen.usage_input_tokens
        record["usage_output_tokens"] += gen.usage_output_tokens
        return record

    scope = getattr(extraction.query_focus, "query_temporal_scope", "unclear")
    record["query_temporal_scope"] = scope
    if _AGG_QUERY_RE.search(instance.question):
        return _pass_through("scope_pass_aggregation")
    if scope == "past_or_change":
        return _pass_through("scope_pass_history")

    def has_repl(extr):
        return any(
            r.temporal_relation in ("replacement", "correction") for r in extr.records
        )

    if extraction.query_focus.needs_current and not has_repl(extraction):
        record["repair_triggered"] = True
        from qvf.engine_bridge import build_repair_query_dense

        second = retriever.retrieve(
            build_repair_query_dense(extraction.query_focus), top_k=TOP_K
        )
        have = {m.memory_id for m in retrieved}
        added = [m for m in second if m.memory_id not in have][:5]
        record["repair_added_ids"] = [m.memory_id for m in added]
        if added and _scan_ok():
            merged = retrieved + added
            extraction, ein2, eout2 = extractor.extract(
                instance.question, merged, instance.question_date, scoped=True
            )
            record["usage_input_tokens"] += ein2
            record["usage_output_tokens"] += eout2
            retrieved = merged

    rel = extraction.records
    repl = [r for r in rel if r.temporal_relation in ("replacement", "correction")]
    by_id = {m.memory_id: m for m in retrieved}
    reader = validated_reader
    if repl:
        keep = {r.source_memory_id for r in repl}
        filtered = [m for m in retrieved if m.memory_id in keep]
        strategy = "rules_replacement"
    elif rel and len({_norm_val(r.value) for r in rel}) > 1:
        # v6 fix (2): execute latest-wins instead of annotating it.
        dated = [
            (key, r) for r in rel
            if (key := _mem_date_key(by_id.get(r.source_memory_id))) is not None
        ] if rel else []
        if len(dated) >= 2:
            latest = max(k for k, _ in dated)
            keep = {r.source_memory_id for k, r in dated if k == latest}
            filtered = [m for m in retrieved if m.memory_id in keep]
            strategy = "rules_conflict_surgery"
        else:
            keep = {r.source_memory_id for r in rel}
            filtered = [m for m in retrieved if m.memory_id in keep]
            reader = conflict_reader or validated_reader
            strategy = "rules_conflict_latest"
    elif rel:
        if extraction.query_focus.needs_current:
            # v6 fix (3): single value + needs-current = suspect recall miss.
            return _pass_through("rules_admit_suspicious_pass")
        keep = {r.source_memory_id for r in rel}
        filtered = [m for m in retrieved if m.memory_id in keep]
        strategy = "rules_admit"
    else:
        filtered = []
        strategy = "rules_no_records"

    record.update(
        {
            "extracted_record_count": len(rel),
            "filter_strategy": strategy,
            "filtered_memory_ids": [m.memory_id for m in filtered],
            "retrieved_memory_ids": [m.memory_id for m in retrieved],
        }
    )
    question = instance.question
    if premise_note and repl:
        # dim2 fix: when the question itself presupposes a superseded value,
        # say so explicitly — readers of every tier fail to contradict a
        # question's premise unprompted (3-5/55 across haiku/sonnet/gpt-5).
        by_rid = {r.record_id: r for r in rel}
        old_vals = [
            by_rid[t].value
            for r in repl for t in r.relation_target_record_ids
            if t in by_rid and by_rid[t].value
        ]
        q_norm = _norm_val(question)
        if any(len(str(v)) > 2 and _norm_val(v) in q_norm for v in old_vals):
            latest = repl[0]
            question = (
                f"{question}\n\n[Validity note: this question may presuppose "
                f"an outdated state. According to the memories, the current "
                f"{latest.slot} is: {latest.value}.]"
            )
            record["premise_note_fired"] = True

    if filtered:
        gen = reader.generate(question, filtered, instance.question_date)
        record["fallback_used"] = False
    else:
        gen = fallback_generator.generate(
            question, retrieved, instance.question_date
        )
        record["fallback_used"] = True
    record["answer"] = gen.answer
    record["usage_input_tokens"] += gen.usage_input_tokens
    record["usage_output_tokens"] += gen.usage_output_tokens
    return record


def run_prompted(instance, extractor, reader, fallback_generator) -> dict:
    retriever = BM25Retriever(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    extraction, ein, eout = extractor.extract(
        instance.question, retrieved, instance.question_date
    )
    request = build_engine_request(
        request_id=instance.question_id,
        query_text=instance.question,
        focus=extraction.query_focus,
        memories=retrieved,
        extracted=extraction.records,
        as_of=instance.question_date,
    )
    engine = run_engine(request)
    record = {
        "extracted_record_count": len(extraction.records),
        "query_focus": extraction.query_focus.model_dump(),
        "engine_ok": engine.ok,
        "engine_accepted": engine.accepted_records,
        "engine_rejected": engine.rejected_records,
        "engine_rejection_reasons": engine.rejection_reasons,
        "engine_blocking_reasons": engine.blocking_reasons,
        "engine_error": engine.error,
        "usage_input_tokens": ein,
        "usage_output_tokens": eout,
        "retrieved_memory_ids": [m.memory_id for m in retrieved],
    }
    if engine.decision:
        record["engine_decision"] = {
            k: engine.decision.get(k)
            for k in (
                "read_decision",
                "answer_policy",
                "next_action",
                "blocked_as_current_ids",
                "allowed_as_history_ids",
            )
        }
    if engine.ok and engine.sidecar is not None and reader is not None:
        answer, rin, rout = reader.answer(instance.question, engine.sidecar)
        record["fallback_used"] = False
    else:
        # Deployment-realistic fallback: engine blocked -> plain direct read.
        gen = fallback_generator.generate(
            instance.question, retrieved, instance.question_date
        )
        answer, rin, rout = gen.answer, gen.usage_input_tokens, gen.usage_output_tokens
        record["fallback_used"] = True
    record["answer"] = answer
    record["usage_input_tokens"] += rin
    record["usage_output_tokens"] += rout
    return record


def run_filtered(instance, extractor, direct_reader, fallback_generator) -> dict:
    """Condition A (context surgery): same extraction + engine as `prompted`,
    but instead of handing the reader an annotated sidecar packet, physically
    REMOVE non-admitted evidence and give the weak reader only the small set of
    admitted-current raw memories via the plain baseline prompt.

    Tests the hypothesis from the decisive run's decomposition: weak readers
    comply with small clean contexts but ignore annotation packets.
    """
    retriever = BM25Retriever(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    extraction, ein, eout = extractor.extract(
        instance.question, retrieved, instance.question_date
    )
    request = build_engine_request(
        request_id=instance.question_id + "_flt",
        query_text=instance.question,
        focus=extraction.query_focus,
        memories=retrieved,
        extracted=extraction.records,
        as_of=instance.question_date,
    )
    engine = run_engine(request)
    rec2mem = {r.record_id: r.source_memory_id for r in extraction.records}

    record = {
        "extracted_record_count": len(extraction.records),
        "engine_ok": engine.ok,
        "engine_accepted": engine.accepted_records,
        "engine_rejected": engine.rejected_records,
        "engine_rejection_reasons": engine.rejection_reasons,
        "usage_input_tokens": ein,
        "usage_output_tokens": eout,
        "retrieved_memory_ids": [m.memory_id for m in retrieved],
    }
    decision = engine.decision or {}
    boundary = decision.get("answerability_boundary") or {}
    answer_ids = boundary.get("answer_evidence_ids") or []
    blocked_ids = decision.get("blocked_as_current_ids") or []
    record["engine_decision"] = {
        k: decision.get(k)
        for k in ("read_decision", "answer_policy", "next_action",
                  "blocked_as_current_ids", "allowed_as_history_ids")
    }

    keep = {rec2mem[rid] for rid in answer_ids if rid in rec2mem}
    if keep:
        filtered = [m for m in retrieved if m.memory_id in keep]
        strategy = "keep_admitted_only"
    else:
        drop = {rec2mem[rid] for rid in blocked_ids if rid in rec2mem}
        filtered = [m for m in retrieved if m.memory_id not in drop]
        strategy = "drop_blocked" if drop else "no_surgery"
    record["filter_strategy"] = strategy
    record["filtered_memory_ids"] = [m.memory_id for m in filtered]

    if engine.ok and filtered:
        gen = direct_reader.generate(instance.question, filtered, instance.question_date)
        record["fallback_used"] = False
    else:
        gen = fallback_generator.generate(
            instance.question, retrieved, instance.question_date
        )
        record["fallback_used"] = True
    record["answer"] = gen.answer
    record["usage_input_tokens"] += gen.usage_input_tokens
    record["usage_output_tokens"] += gen.usage_output_tokens
    return record


def _surgery_and_read(instance, retrieved, extraction, engine, direct_reader,
                      fallback_generator, record: dict,
                      conflict_reader=None) -> dict:
    """Shared tail: context surgery on the engine decision, then weak read.

    v4 addition: when the engine reports an UNRESOLVED conflict
    (UNKNOWN_CURRENT with blocked competitors), do NOT discard the evidence —
    keep exactly the conflicting rounds and read them with the
    latest-known-with-hedge policy (calibrated recency: time is used as a
    tie-breaker only AFTER the symbolic layer verified a same-slot conflict).
    """
    rec2mem = {r.record_id: r.source_memory_id for r in extraction.records}
    decision = engine.decision or {}
    boundary = decision.get("answerability_boundary") or {}
    answer_ids = boundary.get("answer_evidence_ids") or []
    blocked_ids = decision.get("blocked_as_current_ids") or []
    record["engine_decision"] = {
        k: decision.get(k)
        for k in ("read_decision", "answer_policy", "next_action",
                  "blocked_as_current_ids", "allowed_as_history_ids")
    }
    reader = direct_reader
    unresolved_conflict = (
        decision.get("read_decision") == "UNKNOWN_CURRENT"
        and blocked_ids
        and conflict_reader is not None
    )
    keep = {rec2mem[rid] for rid in answer_ids if rid in rec2mem}
    if unresolved_conflict:
        conflict_mem = {rec2mem[rid] for rid in blocked_ids if rid in rec2mem}
        filtered = [m for m in retrieved if m.memory_id in conflict_mem]
        strategy = "conflict_latest_known"
        reader = conflict_reader
        if not filtered:
            filtered = retrieved
            strategy = "conflict_fallback_full"
    elif keep:
        filtered = [m for m in retrieved if m.memory_id in keep]
        strategy = "keep_admitted_only"
    else:
        drop = {rec2mem[rid] for rid in blocked_ids if rid in rec2mem}
        filtered = [m for m in retrieved if m.memory_id not in drop]
        strategy = "drop_blocked" if drop else "no_surgery"
    record["filter_strategy"] = strategy
    record["filtered_memory_ids"] = [m.memory_id for m in filtered]

    if engine.ok and filtered:
        gen = reader.generate(instance.question, filtered, instance.question_date)
        record["fallback_used"] = False
    else:
        gen = fallback_generator.generate(
            instance.question, retrieved, instance.question_date
        )
        record["fallback_used"] = True
    record["answer"] = gen.answer
    record["usage_input_tokens"] += gen.usage_input_tokens
    record["usage_output_tokens"] += gen.usage_output_tokens
    return record


def run_repaired(instance, extractor, direct_reader, fallback_generator,
                 retriever_cls=BM25Retriever, dense: bool = False,
                 conflict_reader=None) -> dict:
    """Full system condition: retrieval -> extract -> adjudicate ->
    validity-triggered targeted re-retrieval -> re-extract -> re-adjudicate ->
    context surgery -> weak read."""
    retriever = retriever_cls(instance.memories)
    retrieved = retriever.retrieve(instance.question, top_k=TOP_K)
    extraction, ein, eout = extractor.extract(
        instance.question, retrieved, instance.question_date
    )
    request = build_engine_request(
        request_id=instance.question_id + "_rep1",
        query_text=instance.question,
        focus=extraction.query_focus,
        memories=retrieved,
        extracted=extraction.records,
        as_of=instance.question_date,
    )
    engine = run_engine(request)
    record = {
        "usage_input_tokens": ein,
        "usage_output_tokens": eout,
        "repair_triggered": False,
        "repair_added_ids": [],
    }
    _scan_ok = _scan_taker()

    if needs_repair(engine, extraction):
        record["repair_triggered"] = True
        if dense:
            from qvf.engine_bridge import build_repair_query_dense

            repair_q = build_repair_query_dense(extraction.query_focus)
        else:
            repair_q = build_repair_query(extraction.query_focus)
        record["repair_query"] = repair_q
        second = retriever.retrieve(repair_q, top_k=TOP_K)
        have = {m.memory_id for m in retrieved}
        added = [m for m in second if m.memory_id not in have][:5]
        record["repair_added_ids"] = [m.memory_id for m in added]
        if added and _scan_ok():
            merged = retrieved + added
            extraction, ein2, eout2 = extractor.extract(
                instance.question, merged, instance.question_date
            )
            record["usage_input_tokens"] += ein2
            record["usage_output_tokens"] += eout2
            request = build_engine_request(
                request_id=instance.question_id + "_rep2",
                query_text=instance.question,
                focus=extraction.query_focus,
                memories=merged,
                extracted=extraction.records,
                as_of=instance.question_date,
            )
            engine = run_engine(request)
            retrieved = merged

    record.update(
        {
            "extracted_record_count": len(extraction.records),
            "engine_ok": engine.ok,
            "engine_accepted": engine.accepted_records,
            "engine_rejected": engine.rejected_records,
            "engine_rejection_reasons": engine.rejection_reasons,
            "retrieved_memory_ids": [m.memory_id for m in retrieved],
        }
    )
    return _surgery_and_read(
        instance, retrieved, extraction, engine, direct_reader,
        fallback_generator, record, conflict_reader=conflict_reader,
    )


def run_oracle(instance, reader, fallback_generator) -> dict:
    extra = instance.extra
    old_idx = extra.get("old_session_index")
    new_idx = extra.get("new_session_index")
    # session_date metadata for the two oracle memories from the item timestamps
    dates = {}
    for m in instance.memories:
        sid = m.metadata.get("session_id")
        if sid is not None and sid not in dates:
            dates[sid] = m.metadata.get("session_date")
    ts_old = dates.get(f"s{old_idx}")
    ts_new = dates.get(f"s{new_idx}")

    memories, focus, records = oracle_pair_for_stale(extra, ts_old, ts_new)
    request = build_engine_request(
        request_id=instance.question_id + "_oracle",
        query_text=instance.question,
        focus=focus,
        memories=memories,
        extracted=records,
        as_of=instance.question_date,
    )
    engine = run_engine(request)
    record = {
        "engine_ok": engine.ok,
        "engine_accepted": engine.accepted_records,
        "engine_rejected": engine.rejected_records,
        "engine_rejection_reasons": engine.rejection_reasons,
        "engine_blocking_reasons": engine.blocking_reasons,
        "engine_error": engine.error,
        "usage_input_tokens": 0,
        "usage_output_tokens": 0,
    }
    if engine.decision:
        record["engine_decision"] = {
            k: engine.decision.get(k)
            for k in ("read_decision", "answer_policy", "next_action",
                      "blocked_as_current_ids", "allowed_as_history_ids")
        }
    if engine.ok and engine.sidecar is not None and reader is not None:
        answer, rin, rout = reader.answer(instance.question, engine.sidecar)
        record["fallback_used"] = False
    else:
        gen = fallback_generator.generate(
            instance.question, memories, instance.question_date
        )
        answer, rin, rout = gen.answer, gen.usage_input_tokens, gen.usage_output_tokens
        record["fallback_used"] = True
    record["answer"] = answer
    record["usage_input_tokens"] += rin
    record["usage_output_tokens"] += rout
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/stale_T1_T2_400_FULL.json")
    parser.add_argument(
        "--benchmark",
        choices=["stale", "longmemeval", "locomo", "memconflict",
                 "stale_chain", "tempreason", "hoh"],
        default="stale",
        help="longmemeval/locomo/memconflict load via eval.datasets "
        "(oracle condition unsupported there)",
    )
    parser.add_argument(
        "--qtype", default=None,
        help="longmemeval only: filter to one question_type "
        "(e.g. knowledge-update)",
    )
    parser.add_argument("--items", type=int, default=0,
                        help="Limit item count; 0 = no limit. (Default was "
                        "35 for legacy STALE dev runs — that silently "
                        "truncated other benchmarks twice; now explicit.)")
    parser.add_argument(
        "--item-offset", type=int, default=0,
        help="Skip the first N STALE items (held-out evaluation: dev used 0-34)",
    )
    parser.add_argument(
        "--conditions", default="direct,prompted,oracle",
        help="Comma-separated subset of {direct,prompted,oracle,filtered}",
    )
    parser.add_argument("--out", default="results/decisive_stale.jsonl")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--redo-empty", action="store_true",
        help="With --resume: re-run only (question,mode) pairs whose stored "
        "answer is empty (reader budget-exhaustion casualties); every other "
        "row is kept verbatim and no new pairs are added.",
    )
    parser.add_argument(
        "--reader",
        default="claude-haiku-4-5",
        help="Reader model: an Anthropic model id, or 'local:<ollama-model>' "
        "(e.g. local:qwen3:4b) for a free local weak reader",
    )
    parser.add_argument(
        "--sample-n", type=int, default=0,
        help="Randomly sample N queries from the loaded pool (pilot mode). "
        "Applied after all other filters; deterministic given --sample-seed.",
    )
    parser.add_argument(
        "--sample-items", type=int, default=0,
        help="STALE: randomly sample N ITEMS (keeping all their query "
        "variants) from the loaded pool — preserves the case structure, "
        "unlike --sample-n. Deterministic given --sample-seed.",
    )
    parser.add_argument("--sample-seed", type=int, default=20260802)
    parser.add_argument("--tempreason-raw", action="store_true",
                        help="TempReason: raw Wikipedia article context "
                        "instead of pre-extracted fact_context")
    parser.add_argument("--top-k", type=int, default=0,
                        help="Override primary retrieval TOP_K (0 = keep "
                        "default). Set >= haystack size for full-context "
                        "delivery into the QVF pipeline.")
    parser.add_argument("--mmr", action="store_true",
                        help="Primary retrieval uses MMR diversity "
                        "reranking (Carbonell & Goldstein 1998) instead of "
                        "plain top-K")
    parser.add_argument("--qid-file", default=None,
                        help="Path to a text file of question_ids (one per "
                        "line); restricts the run to exactly these questions")
    parser.add_argument("--mc-seed", type=int, default=20260802,
                        help="MemConflict: stratified-sample seed "
                        "(20260802 = dev slice; use a new seed for fresh "
                        "confirmation)")
    parser.add_argument("--hoh-min-versions", type=int, default=1,
                        help="HoH: keep rows with >= N outdated versions")
    parser.add_argument("--hoh-distractors", type=int, default=8,
                        help="HoH: distractor passages per instance")
    args = parser.parse_args()
    global _USE_MMR, TOP_K
    _USE_MMR = bool(args.mmr)
    if args.top_k:
        TOP_K = args.top_k

    if args.benchmark == "stale_chain":
        from eval.stale_chain_dataset import load_stale_chain

        instances = load_stale_chain(
            args.data, limit_items=args.items, item_offset=args.item_offset
        )
        print(f"Loaded {len(instances)} stale_chain queries")
    elif args.benchmark == "tempreason":
        from eval.tempreason_dataset import load_tempreason

        instances = load_tempreason(
            args.data, limit=args.items, seed=args.sample_seed,
            use_fact_context=not args.tempreason_raw,
        )
        print(f"Loaded {len(instances)} tempreason L2 queries "
              f"(raw_context={args.tempreason_raw})")
    elif args.benchmark == "hoh":
        from eval.hoh_dataset import load_hoh

        instances = load_hoh(
            args.data, limit=args.items, seed=args.sample_seed,
            n_distractors=args.hoh_distractors,
            min_versions=args.hoh_min_versions,
        )
        print(f"Loaded {len(instances)} HoH queries "
              f"(min_versions={args.hoh_min_versions}, "
              f"distractors={args.hoh_distractors})")
    elif args.benchmark in ("longmemeval", "locomo", "memconflict"):
        if args.benchmark == "longmemeval":
            from eval.datasets import load_longmemeval as loader
        elif args.benchmark == "memconflict":
            from eval.datasets import load_memconflict

            # Pre-registered stratified sample (seed fixed before any run):
            # 90 dynamic / 30 static / 30 conditional.
            def loader(path):
                return load_memconflict(
                    path,
                    sample_per_type={
                        "dynamic_conflict": 90,
                        "static_conflict": 30,
                        "conditional_conflict": 30,
                    },
                    seed=args.mc_seed,
                )
        else:
            from eval.datasets import load_locomo as loader

        instances = loader(args.data)
        if args.qtype:
            instances = [i for i in instances if i.question_type == args.qtype]
        if args.item_offset:
            instances = instances[args.item_offset:]
        if args.items:
            instances = instances[: args.items * 3]  # keep --items semantics loose
        print(
            f"Loaded {len(instances)} {args.benchmark} queries (qtype={args.qtype})"
        )
    else:
        instances = load_stale(
            args.data, limit_items=args.items, item_offset=args.item_offset
        )
        print(
            f"Loaded {len(instances)} queries from {args.items} STALE items "
            f"(offset {args.item_offset})"
        )
    if args.qid_file:
        keep_ids = {l.strip() for l in open(args.qid_file, encoding="utf-8")
                    if l.strip()}
        instances = [i for i in instances if i.question_id in keep_ids]
        print(f"qid-file filter: {len(instances)} questions kept")
    if args.sample_items:
        import random as _random

        def _item_uid(inst):
            return inst.question_id.rsplit("_", 2)[0]

        uids = []
        for inst in instances:
            u = _item_uid(inst)
            if u not in uids:
                uids.append(u)
        if len(uids) > args.sample_items:
            keep = set(_random.Random(args.sample_seed).sample(
                uids, args.sample_items
            ))
            instances = [i for i in instances if _item_uid(i) in keep]
        print(
            f"Randomly sampled {args.sample_items} items -> "
            f"{len(instances)} queries (seed {args.sample_seed})"
        )
    if args.sample_n and len(instances) > args.sample_n:
        import random as _random

        instances = _random.Random(args.sample_seed).sample(
            instances, args.sample_n
        )
        print(
            f"Randomly sampled {len(instances)} queries "
            f"(seed {args.sample_seed})"
        )
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    # Extractor: QVF_LOCAL_EXTRACTOR=<ollama-model> selects the fully-local
    # zero-API extractor; otherwise the Anthropic extractor with
    # QVF_ADAPTER_MODEL (default opus).
    _local_ext = os.environ.get("QVF_LOCAL_EXTRACTOR")
    _adapter = os.environ.get("QVF_ADAPTER_MODEL", "")
    if _local_ext:
        from qvf.engine_bridge import LocalSlotExtractor

        extractor = LocalSlotExtractor(_local_ext)
    elif _adapter.startswith("openai:"):
        from qvf.openai_bridge import OpenAISlotExtractor

        extractor = OpenAISlotExtractor(_adapter.split(":", 1)[1])
    else:
        extractor = LLMSlotExtractor()
    if args.reader.startswith("local:"):
        from qvf.engine_bridge import (
            VALIDATED_CONTEXT_READER_PROMPT,
            LocalChatModel,
            LocalDirectGenerator,
            LocalSidecarReader,
        )

        local = LocalChatModel(model=args.reader.split(":", 1)[1])
        reader = LocalSidecarReader(local)
        direct_gen = LocalDirectGenerator(local)
        validated_gen = LocalDirectGenerator(
            local, system_prompt=VALIDATED_CONTEXT_READER_PROMPT
        )
        from qvf.engine_bridge import (
            CONFLICT_LATEST_KNOWN_READER_PROMPT,
            RECENCY_READER_PROMPT,
        )

        conflict_gen = LocalDirectGenerator(
            local, system_prompt=CONFLICT_LATEST_KNOWN_READER_PROMPT
        )
        recency_gen = LocalDirectGenerator(
            local, system_prompt=RECENCY_READER_PROMPT
        )
    elif args.reader.startswith("openai:"):
        from qvf.engine_bridge import (
            CONFLICT_LATEST_KNOWN_READER_PROMPT,
            VALIDATED_CONTEXT_READER_PROMPT,
        )
        from qvf.openai_bridge import OpenAIGenerator

        _om = args.reader.split(":", 1)[1]
        reader = None  # SidecarReader paths (prompted/oracle/qvf_v4) unsupported
        direct_gen = OpenAIGenerator(_om)
        validated_gen = OpenAIGenerator(
            _om, system_prompt=VALIDATED_CONTEXT_READER_PROMPT
        )
        conflict_gen = OpenAIGenerator(
            _om, system_prompt=CONFLICT_LATEST_KNOWN_READER_PROMPT
        )
        recency_gen = direct_gen
    else:
        reader = SidecarReader(model=args.reader)
        direct_gen = BaselineGenerator(model=args.reader)
        # API readers get the same specialized system prompts as the local
        # path, so the QVF arm is not handicapped relative to the qwen runs.
        from qvf.engine_bridge import (
            CONFLICT_LATEST_KNOWN_READER_PROMPT,
            VALIDATED_CONTEXT_READER_PROMPT,
        )

        validated_gen = BaselineGenerator(model=args.reader)
        validated_gen.system_prompt = VALIDATED_CONTEXT_READER_PROMPT
        conflict_gen = BaselineGenerator(model=args.reader)
        conflict_gen.system_prompt = CONFLICT_LATEST_KNOWN_READER_PROMPT
        recency_gen = direct_gen
        if "haiku" in args.reader:
            # Deterministic reads on models that accept temperature —
            # aligns the API protocol with the local temp-0 runs.
            for _g in (direct_gen, validated_gen, conflict_gen):
                _g.temperature = 0.0
    haiku_gen = BaselineGenerator(model="claude-haiku-4-5")

    _lazy = {}

    def _strong_extractor():
        if "strong" not in _lazy:
            _lazy["strong"] = LLMSlotExtractor(model="claude-sonnet-5")
        return _lazy["strong"]

    def _ledger_store():
        if "ledger" not in _lazy:
            from qvf.engine_bridge import WriteTimeLedger

            _lazy["ledger"] = WriteTimeLedger(model="claude-haiku-4-5")
        return _lazy["ledger"]

    def _reasoning_conflict_reader():
        if "rcr" not in _lazy:
            from qvf.engine_bridge import CONFLICT_LATEST_KNOWN_READER_PROMPT
            from qvf.openai_bridge import OpenAIGenerator

            _lazy["rcr"] = OpenAIGenerator(
                "gpt-5-mini",
                system_prompt=CONFLICT_LATEST_KNOWN_READER_PROMPT,
            )
        return _lazy["rcr"]

    # Contradiction reader mirrors the arm's reader family.
    global _CONTRA_READER
    from qvf.engine_bridge import CONTRADICTION_READER_PROMPT as _CRP

    if args.reader.startswith("local:"):
        from qvf.engine_bridge import LocalChatModel as _LCM
        from qvf.engine_bridge import LocalDirectGenerator as _LDG

        _CONTRA_READER = _LDG(
            _LCM(model=args.reader.split(":", 1)[1]), system_prompt=_CRP
        )
    elif args.reader.startswith("openai:"):
        from qvf.openai_bridge import OpenAIGenerator as _OG

        _CONTRA_READER = _OG(args.reader.split(":", 1)[1], system_prompt=_CRP)
    else:
        _CONTRA_READER = BaselineGenerator(model=args.reader)
        _CONTRA_READER.system_prompt = _CRP
        if "haiku" in args.reader:
            _CONTRA_READER.temperature = 0.0

    print(f"Reader: {args.reader}")
    judge = None if args.no_judge else ClaudeJudge()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    records = []
    redo_pairs = set()
    if args.resume and out_path.exists():
        rows = []
        with out_path.open("r", encoding="utf-8") as fin:
            for line in fin:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if args.redo_empty:
            keep = [r for r in rows if (r.get("answer") or "").strip()]
            all_pairs = {(r.get("question_id"), r.get("mode")) for r in rows}
            done = {(r.get("question_id"), r.get("mode")) for r in keep}
            redo_pairs = all_pairs - done
            with out_path.open("w", encoding="utf-8") as fout0:
                for r in keep:
                    fout0.write(json.dumps(r, ensure_ascii=False) + "\n")
            records = keep
            print(
                f"Redo-empty: re-running {len(redo_pairs)} empty-answer pairs, "
                f"keeping {len(keep)} rows"
            )
        else:
            for r in rows:
                done.add((r.get("question_id"), r.get("mode")))
                records.append(r)
            print(f"Resuming: {len(done)} pairs already done")

    runners = {
        "direct": lambda inst: run_direct(inst, direct_gen),
        "prompted": lambda inst: run_prompted(inst, extractor, reader, direct_gen),
        "oracle": lambda inst: run_oracle(inst, reader, direct_gen),
        "filtered": lambda inst: run_filtered(inst, extractor, direct_gen, direct_gen),
        "repaired": lambda inst: run_repaired(inst, extractor, validated_gen, direct_gen),
        "repaired_dense": lambda inst: run_repaired(
            inst, extractor, validated_gen, direct_gen,
            retriever_cls=_dense_retriever_cls(), dense=True,
        ),
        "qvf_v4": lambda inst: run_repaired(
            inst, extractor, validated_gen, direct_gen,
            retriever_cls=_dense_retriever_cls(), dense=True,
            conflict_reader=conflict_gen,
        ),
        "dense_direct": lambda inst: run_direct(
            inst, direct_gen, retriever_cls=_dense_retriever_cls()
        ),
        "warned_direct": lambda inst: run_warned_direct(
            inst, direct_gen, retriever_cls=_dense_retriever_cls()
        ),
        "full_context_direct": lambda inst: run_full_context_direct(
            inst, direct_gen
        ),
        "dense_recency": lambda inst: run_direct(
            inst, recency_gen, retriever_cls=_dense_retriever_cls(),
            newest_first=True,
        ),
        "haiku_dense_direct": lambda inst: run_direct(
            inst, haiku_gen, retriever_cls=_dense_retriever_cls()
        ),
        "minimal_rules": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen
        ),
        "minimal_rules_v5": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True,
        ),
        "minimal_rules_v6": lambda inst: run_minimal_rules_v6(
            inst, extractor, validated_gen, conflict_gen, direct_gen
        ),
        "minimal_rules_v7": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, contract="v7",
        ),
        "minimal_rules_v5agg": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, agg_guard=True,
        ),
        "conditional_v5": lambda inst: run_conditional_v5(
            inst, extractor, validated_gen, conflict_gen, direct_gen
        ),
        "minimal_rules_v5sib": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, sibling_expand=True,
        ),
        "minimal_rules_v5esc": lambda inst: run_minimal_rules_escalated(
            inst, extractor, _strong_extractor(), validated_gen, conflict_gen,
            direct_gen,
        ),
        "ledger_v8": lambda inst: run_ledger_v8(
            inst, _ledger_store(), validated_gen, direct_gen
        ),
        "minimal_rules_v51": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, subtractive=True,
        ),
        "minimal_rules_pnote": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, premise_note=True,
        ),
        "minimal_rules_srepair": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, repair_slotted=True,
        ),
        "minimal_rules_esc_sub": lambda inst: run_minimal_rules_escalated(
            inst, extractor, _strong_extractor(), validated_gen, conflict_gen,
            direct_gen, subtractive=True,
        ),
        "qvf_final": lambda inst: run_qvf_final(
            inst, extractor, _strong_extractor(), validated_gen, conflict_gen,
            direct_gen
        ),
        "qvf_final_routed": lambda inst: run_qvf_final_routed(
            inst, extractor, _strong_extractor(), validated_gen, conflict_gen,
            direct_gen, _reasoning_conflict_reader()
        ),
        "minimal_rules_species": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, contract="species", subtractive=True,
        ),
        "minimal_rules_species2": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, contract="species2", subtractive=True,
        ),
        "minimal_rules_species2_abstain": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, contract="species2", subtractive=True,
            abstain_guard=True,
        ),
        "minimal_rules_species2_esc": lambda inst: run_minimal_rules(
            inst, extractor, validated_gen, conflict_gen, direct_gen,
            scope_gate=True, contract="species2", subtractive=True,
            strong_extractor=_strong_extractor(),
        ),
        "extraction_only": lambda inst: run_extraction_only(
            inst, extractor, direct_gen
        ),
    }

    open_mode = "a" if (args.resume and out_path.exists()) else "w"
    with out_path.open(open_mode, encoding="utf-8") as fout:
        for instance in tqdm(instances, desc="queries"):
            for mode in conditions:
                if (instance.question_id, mode) in done:
                    continue
                if args.redo_empty and (instance.question_id, mode) not in redo_pairs:
                    continue
                t0 = time.time()
                try:
                    record = runners[mode](instance)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    record = {"error": traceback.format_exc(limit=3)}
                record.update(
                    {
                        "question_id": instance.question_id,
                        "mode": mode,
                        "question_type": instance.question_type,
                        "question": instance.question,
                        "gold_answer": instance.gold_answer,
                        "is_abstention": instance.is_abstention,
                        "stale_type": instance.extra.get("stale_type"),
                        "latency_s": round(time.time() - t0, 2),
                        "extractor_model": getattr(extractor, "model", None),
                        "reader_model": args.reader,
                    }
                )
                if judge is not None and "error" not in record:
                    try:
                        verdict = judge.judge(
                            instance.question,
                            instance.gold_answer,
                            record["answer"],
                            instance.question_type,
                            instance.is_abstention,
                        )
                        record["judge_correct"] = verdict.correct
                        record["judge_reason"] = verdict.reason
                    except Exception:  # noqa: BLE001
                        record["judge_correct"] = None
                        record["judge_error"] = traceback.format_exc(limit=2)
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                fout.flush()
                records.append(record)

    # Aggregates
    from collections import defaultdict

    agg = defaultdict(lambda: {"n": 0, "correct": 0, "fallback": 0, "rej": 0, "acc_rec": 0})
    for r in records:
        if "error" in r:
            continue
        a = agg[(r["mode"], r["question_type"])]
        a["n"] += 1
        a["correct"] += 1 if r.get("judge_correct") else 0
        a["fallback"] += 1 if r.get("fallback_used") else 0
        a["rej"] += r.get("engine_rejected", 0)
        a["acc_rec"] += r.get("engine_accepted", 0)
    print()
    for key in sorted(agg):
        a = agg[key]
        print(
            f"{key[0]:9s} {key[1]:12s} n={a['n']:>3} acc={a['correct']/max(a['n'],1):.3f} "
            f"fallback={a['fallback']} accepted_rec={a['acc_rec']} rejected_rec={a['rej']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
