"""Loaders that normalize LongMemEval, LoCoMo and MemConflict into the internal format.

Internal format per QA instance:
- question_id, question, gold_answer, question_date (optional), question_type
- a list of MemoryItem built from the conversation history, where each memory
  is one dialog round (user turn + following assistant turn) with metadata
  {session_id, session_date, round_index}.

Field names are read defensively (.get with fallbacks) because both datasets
have several released variants.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from qvf.retrieval import MemoryItem


@dataclass
class QAInstance:
    question_id: str
    question: str
    gold_answer: str
    memories: List[MemoryItem]
    question_date: Optional[str] = None
    question_type: Optional[str] = None
    is_abstention: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LongMemEval
# ---------------------------------------------------------------------------
# File format (longmemeval_s / longmemeval_m / longmemeval_oracle): a JSON list
# of instances with fields including question_id, question_type, question,
# answer, question_date, haystack_session_ids, haystack_dates,
# haystack_sessions (list of sessions; each session is a list of turns
# {role, content, [has_answer]}), answer_session_ids.
# Abstention questions have question_id ending with "_abs".


def _rounds_from_session(session_turns: List[dict]) -> List[str]:
    """Group a session's turns into user+assistant round strings."""
    rounds: List[str] = []
    current: List[str] = []
    for turn in session_turns:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        current.append(f"{role}: {content}")
        if role == "assistant":
            rounds.append("\n".join(current))
            current = []
    if current:
        rounds.append("\n".join(current))
    return rounds


def load_longmemeval(path: str | Path) -> List[QAInstance]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    instances: List[QAInstance] = []
    for item in data:
        qid = str(item.get("question_id"))
        sessions = item.get("haystack_sessions", [])
        session_ids = item.get("haystack_session_ids", [f"s{i}" for i in range(len(sessions))])
        session_dates = item.get("haystack_dates", [None] * len(sessions))

        memories: List[MemoryItem] = []
        for s_idx, session in enumerate(sessions):
            sid = session_ids[s_idx] if s_idx < len(session_ids) else f"s{s_idx}"
            sdate = session_dates[s_idx] if s_idx < len(session_dates) else None
            for r_idx, round_text in enumerate(_rounds_from_session(session)):
                memories.append(
                    MemoryItem(
                        memory_id=f"{sid}#r{r_idx}",
                        content=round_text,
                        metadata={
                            "session_id": sid,
                            "session_date": sdate,
                            "round_index": r_idx,
                        },
                    )
                )

        instances.append(
            QAInstance(
                question_id=qid,
                question=item.get("question", ""),
                gold_answer=str(item.get("answer", "")),
                memories=memories,
                question_date=item.get("question_date"),
                question_type=item.get("question_type"),
                is_abstention=qid.endswith("_abs"),
                extra={
                    "answer_session_ids": item.get("answer_session_ids"),
                },
            )
        )
    return instances


# ---------------------------------------------------------------------------
# LoCoMo
# ---------------------------------------------------------------------------
# locomo10.json: a JSON list of samples. Each sample has:
# - "conversation": {"speaker_a", "speaker_b", "session_1": [turns...],
#    "session_1_date_time": "...", "session_2": [...], ...}
#   where each turn is {"speaker", "text", "dia_id", ...}
# - "qa": [{"question", "answer", "evidence", "category"}, ...]
# Category taxonomy (per the paper): 1 multi-hop, 2 temporal, 3 open-domain,
# 4 single-hop, 5 adversarial (unanswerable).

LOCOMO_CATEGORY_NAMES = {
    1: "multi-hop",
    2: "temporal",
    3: "open-domain",
    4: "single-hop",
    5: "adversarial",
}


def _locomo_session_keys(conversation: dict) -> List[str]:
    keys = []
    for k in conversation:
        if k.startswith("session_") and not k.endswith("_date_time") and isinstance(
            conversation[k], list
        ):
            keys.append(k)
    # sort numerically: session_1, session_2, ...
    def session_num(k: str) -> int:
        try:
            return int(k.split("_")[1])
        except (IndexError, ValueError):
            return 0

    return sorted(keys, key=session_num)


def load_locomo(path: str | Path) -> List[QAInstance]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    instances: List[QAInstance] = []
    for sample_idx, sample in enumerate(data):
        conversation = sample.get("conversation", {})
        sample_id = str(sample.get("sample_id", f"locomo{sample_idx}"))

        memories: List[MemoryItem] = []
        for skey in _locomo_session_keys(conversation):
            sdate = conversation.get(f"{skey}_date_time")
            turns = conversation[skey]
            # LoCoMo turns alternate speakers; group into consecutive pairs.
            for t_idx in range(0, len(turns), 2):
                chunk = turns[t_idx : t_idx + 2]
                text = "\n".join(
                    f"{t.get('speaker', '?')}: {t.get('text', '')}" for t in chunk
                )
                # Attach image captions where present (blip_caption fields).
                for t in chunk:
                    cap = t.get("blip_caption")
                    if cap:
                        text += f"\n[shared image: {cap}]"
                memories.append(
                    MemoryItem(
                        memory_id=f"{sample_id}/{skey}#r{t_idx // 2}",
                        content=text,
                        metadata={
                            "session_id": f"{sample_id}/{skey}",
                            "session_date": sdate,
                            "round_index": t_idx // 2,
                        },
                    )
                )

        for q_idx, qa in enumerate(sample.get("qa", [])):
            category = qa.get("category")
            try:
                category_int = int(category) if category is not None else None
            except (TypeError, ValueError):
                category_int = None
            qtype = LOCOMO_CATEGORY_NAMES.get(category_int, str(category))
            is_adversarial = category_int == 5
            if is_adversarial:
                # Category-5 questions are unanswerable; the released
                # `adversarial_answer` is the trap answer a fooled model gives.
                # The gold behavior is to decline.
                answer = "Not answerable from the conversation"
            else:
                answer = qa.get("answer", "")
            instances.append(
                QAInstance(
                    question_id=f"{sample_id}_q{q_idx}",
                    question=qa.get("question", ""),
                    gold_answer=str(answer),
                    memories=memories,
                    question_date=None,
                    question_type=qtype,
                    is_abstention=is_adversarial,
                    extra={
                        "evidence": qa.get("evidence"),
                        "category": category_int,
                        "adversarial_answer": qa.get("adversarial_answer"),
                    },
                )
            )
    return instances


# ---------------------------------------------------------------------------
# MemConflict (github.com/TaoZhen1110/MemConflict, step4 personas)
# ---------------------------------------------------------------------------
# No license published — evaluation-only use, must be flagged in any writeup.
# Each JSONL line is one persona. Full_Session_Chain holds ~53 sessions; each
# session has Session_Dialogue = {dialogue_turn_N: [{role, content}, ...]} and
# Session_Questions asked at that point in the chain. A question attached to
# session k concerns the state revealed up to and including session k, so its
# memory set is every dialogue round from sessions 0..k.
# conflict_type per question: dynamic_conflict (state changed over time),
# static_conflict (a wrong value must be recovered), conditional_conflict
# (preference bound to a condition). Stored as question_type.


def load_memconflict(
    path: str | Path,
    sample_per_type: Optional[Dict[str, int]] = None,
    seed: int = 20260802,
) -> List[QAInstance]:
    import random

    instances: List[QAInstance] = []
    with Path(path).open("r", encoding="utf-8") as fin:
        records = [json.loads(line) for line in fin if line.strip()]
    for rec in records:
        pid = str(rec.get("ID", ""))[:8]
        cum: List[MemoryItem] = []
        for s in rec.get("Full_Session_Chain", []):
            sid = s.get("Session_ID")
            sdate = s.get("Date")
            dialogue = s.get("Session_Dialogue") or {}

            def turn_num(key: str) -> int:
                try:
                    return int(key.rsplit("_", 1)[1])
                except (IndexError, ValueError):
                    return 0

            for tkey in sorted(dialogue.keys(), key=turn_num):
                turns = dialogue[tkey] or []
                text = "\n".join(
                    f"{t.get('role', '?')}: {t.get('content', '')}" for t in turns
                )
                if not text.strip():
                    continue
                cum.append(
                    MemoryItem(
                        memory_id=f"{pid}/s{sid}#r{turn_num(tkey)}",
                        content=text,
                        metadata={
                            "session_id": f"{pid}/s{sid}",
                            "session_date": sdate,
                            "round_index": turn_num(tkey),
                        },
                    )
                )
            snapshot = list(cum)
            for q in s.get("Session_Questions") or []:
                instances.append(
                    QAInstance(
                        question_id=f"{pid}_s{sid}_{q.get('question_id')}",
                        question=q.get("question", ""),
                        gold_answer=str(q.get("answer", "")),
                        memories=snapshot,
                        question_date=sdate,
                        question_type=q.get("conflict_type"),
                        is_abstention=False,
                        extra={
                            "ability_target": q.get("ability_target"),
                            "difficulty": q.get("difficulty"),
                            "persona": pid,
                            "session_id": sid,
                        },
                    )
                )
    if sample_per_type:
        rng = random.Random(seed)
        by_type: Dict[str, List[QAInstance]] = {}
        for inst in instances:
            by_type.setdefault(inst.question_type or "?", []).append(inst)
        chosen: List[QAInstance] = []
        for qtype, quota in sample_per_type.items():
            pool = by_type.get(qtype, [])
            rng.shuffle(pool)
            chosen.extend(pool[:quota])
        instances = chosen
    return instances
