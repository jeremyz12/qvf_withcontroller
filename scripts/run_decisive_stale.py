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


def _norm_val(v: str) -> str:
    return " ".join(str(v).lower().split())


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
                      repair_slotted: bool = False) -> dict:
    """Engine-ablation: identical retrieval/repair/extraction to qvf_v4, but
    adjudication is ~30 lines of plain Python instead of the symbolic engine.
    Measures the engine's net contribution.

    scope_gate=True (v5): the extractor additionally classifies the query's
    temporal scope; history-seeking queries (past state / change / duration /
    event order) bypass surgery entirely — their old states are evidence, not
    stale noise. Motivated by pre-registered risk, confirmed on LME
    temporal-reasoning losses where surgery removed rounds the reader needed."""
    retriever = _dense_retriever_cls()(instance.memories)
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
    triage = getattr(extraction, "memory_triage", None)
    if triage is not None:
        record["triage_counts"] = {
            k: sum(1 for t in triage if t.mentions_query_slot == k)
            for k in ("yes", "maybe", "no")
        }

    if scope_gate:
        scope = getattr(extraction.query_focus, "query_temporal_scope", "unclear")
        record["query_temporal_scope"] = scope
        if scope == "past_or_change":
            record.update(
                {
                    "extracted_record_count": len(extraction.records),
                    "filter_strategy": "scope_pass_history",
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
        if added:
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

    if contract == "species":
        # Species adjudication, in precedence order. Each branch is the
        # minimal deterministic policy for one validity species.
        cess = [r for r in rel if r.temporal_relation == "cessation"]
        contra = [r for r in rel if r.temporal_relation == "contradiction"]
        by_rid_all = {r.record_id: r for r in rel}
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
            # Conditional applicability: if exactly one record's condition
            # matches the query wording, prefer its rounds.
            conded = [r for r in rel if (r.condition or "").strip()]
            if conded:
                qn = _norm_val(instance.question)
                hits = [r for r in conded
                        if any(w in qn for w in _norm_val(r.condition).split()
                               if len(w) > 3)]
                if len({r.source_memory_id for r in hits}) >= 1 and hits:
                    keep = {r.source_memory_id for r in hits}
                    filtered = [m for m in retrieved if m.memory_id in keep]
                    record.update({
                        "extracted_record_count": len(rel),
                        "filter_strategy": "rules_conditional",
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
        if contra and not repl:
            # Factual disagreement: keep both sides, use the contradiction
            # prompt (recency is NOT evidence here).
            keep = {r.source_memory_id for r in contra}
            filtered = [m for m in retrieved if m.memory_id in keep]
            record.update({
                "extracted_record_count": len(rel),
                "filter_strategy": "rules_contradiction",
                "filtered_memory_ids": [m.memory_id for m in filtered],
                "retrieved_memory_ids": [m.memory_id for m in retrieved],
                "fallback_used": False,
            })
            gen = _contradiction_reader().generate(
                instance.question, filtered, instance.question_date
            )
            record["answer"] = gen.answer
            record["usage_input_tokens"] += gen.usage_input_tokens
            record["usage_output_tokens"] += gen.usage_output_tokens
            return record

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
            stale = {by_rid[t].source_memory_id for t in targets if t in by_rid}
            filtered = [m for m in retrieved if m.memory_id not in stale]
            strategy = ("rules_replacement_subtract" if stale
                        else "rules_replacement_noop")
        else:
            keep = {r.source_memory_id for r in repl}
            filtered = [m for m in retrieved if m.memory_id in keep]
            strategy = "rules_replacement"
    elif rel and len({_norm_val(r.value) for r in rel}) > 1:
        if subtractive:
            filtered = list(retrieved)  # keep all, flag the conflict
        else:
            keep = {r.source_memory_id for r in rel}
            filtered = [m for m in retrieved if m.memory_id in keep]
        reader = conflict_reader or validated_reader
        strategy = "rules_conflict_latest"
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
        if added:
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
    if engine.ok and engine.sidecar is not None:
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
        if added:
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
    if engine.ok and engine.sidecar is not None:
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
        "--benchmark", choices=["stale", "longmemeval", "locomo", "memconflict"],
        default="stale",
        help="longmemeval/locomo/memconflict load via eval.datasets "
        "(oracle condition unsupported there)",
    )
    parser.add_argument(
        "--qtype", default=None,
        help="longmemeval only: filter to one question_type "
        "(e.g. knowledge-update)",
    )
    parser.add_argument("--items", type=int, default=35)
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
    args = parser.parse_args()

    if args.benchmark in ("longmemeval", "locomo", "memconflict"):
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
                    seed=20260802,
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
                        "is_abstention": False,
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
