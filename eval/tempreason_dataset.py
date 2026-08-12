"""Loader for TempReason L2 (tan et al., ACL 2023; HF: tonytan48/TempReason).

L2 = time-of-event questions over Wikidata relation timelines: each record
asks for the value of a relation (employer / team / office / spouse ...) at a
named target time, e.g. "Which team did X play for in Jan, 2010?".

We use the pre-extracted ``fact_context``: a newline-separated list of dated
state statements ("X works for TeamA from Jan, 2008 to Jan, 2010."). Each
statement becomes one MemoryItem whose metadata session_date is the state's
START date — mirroring "memory creation time" in conversational benchmarks:
a state is written to memory when it begins. The states of 2-3 OTHER sampled
questions are mixed in as distractors, and the full memory list is shuffled
deterministically so target facts are not positionally identifiable.

File format (JSONL, one record per line; test_l2.json has 5397 records):
- question       str   names the target time in-question
- date           str   "January 11, 1948" — exact target date
- text_answers   dict  {"text": [answers]}
- id             str   "L2_Q457939_P108_0" (entity Qxxx, relation Pxxx, k-th)
- fact_context   str   dated state statements, newline-separated
- context        str   raw Wikipedia article text (used if use_fact_context=False)
- none_context   str   empty in the test split
- neg_answers    list  the OTHER states' values (stale/incorrect answers)
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.datasets import QAInstance
from qvf.retrieval import MemoryItem

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

# "from Jan, 1949" / "from January, 1949" — start date of a state statement.
_FROM_RE = re.compile(r"from\s+([A-Za-z]+),?\s+(\d{4})", re.IGNORECASE)
# fallback: any "Mon, 1949" mention
_ANY_DATE_RE = re.compile(r"([A-Za-z]+),\s+(\d{4})")
# record-level date field: "January 11, 1948"
_FULL_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})")


def _month_num(name: str) -> Optional[int]:
    return _MONTHS.get(name.strip().lower())


def _state_start_date(statement: str) -> str:
    """Start date ("memory creation time") of one fact_context statement.

    Returns "YYYY-MM-DD" (day pinned to 01) or "" if unparseable.
    """
    for regex in (_FROM_RE, _ANY_DATE_RE):
        for m in regex.finditer(statement):
            mon = _month_num(m.group(1))
            if mon is not None:
                return f"{int(m.group(2)):04d}-{mon:02d}-01"
    return ""


def _question_date(raw: str) -> str:
    """Normalize the record's `date` field to YYYY-MM-DD (kept raw on failure)."""
    m = _FULL_DATE_RE.search(raw or "")
    if m:
        mon = _month_num(m.group(1))
        if mon is not None:
            return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"
    return raw or ""


def _split_states(fact_context: str) -> List[str]:
    return [s.strip() for s in (fact_context or "").split("\n") if s.strip()]


def _entity_of(record_id: str) -> str:
    """"L2_Q457939_P108_0" -> "Q457939" (used to avoid same-entity distractors)."""
    parts = str(record_id).split("_")
    return parts[1] if len(parts) > 1 else str(record_id)


def _state_memories(rec: dict, tag: str) -> List[Tuple[str, str, str, str]]:
    """(local_id, source_record_id, content, session_date) per state."""
    rid = str(rec.get("id", ""))
    return [
        (f"{tag}{i}", rid, state, _state_start_date(state))
        for i, state in enumerate(_split_states(rec.get("fact_context", "")))
    ]


def load_tempreason(
    path: str | Path,
    limit: int = 0,
    seed: int = 0,
    use_fact_context: bool = True,
) -> List[QAInstance]:
    """Load TempReason L2 test questions as QAInstance list.

    For each sampled question, the memory store contains the question's own
    fact_context states (one MemoryItem per state, session_date = state start
    date) plus the states of 2-3 other sampled questions as distractors,
    preferring distractors about a different entity. Deterministic given seed.

    With use_fact_context=False the raw Wikipedia `context` article is used
    as a single (undated) memory per record instead of the state statements.
    """
    records: List[dict] = []
    with Path(path).open("r", encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                records.append(json.loads(line))

    rng = random.Random(seed)
    if limit and limit < len(records):
        idx = sorted(rng.sample(range(len(records)), limit))
        records = [records[i] for i in idx]

    instances: List[QAInstance] = []
    n = len(records)
    for pos, rec in enumerate(records):
        rid = str(rec.get("id", f"L2_{pos}"))
        entity = _entity_of(rid)

        # --- distractors: 2-3 OTHER sampled questions, different entity if possible
        n_distractors = rng.randint(2, 3) if n > 1 else 0
        others = [i for i in range(n) if i != pos]
        rng.shuffle(others)
        other_entity = [i for i in others if _entity_of(records[i].get("id", "")) != entity]
        pool = other_entity if len(other_entity) >= n_distractors else others
        distractor_pos = pool[:n_distractors]

        memories: List[MemoryItem] = []
        if use_fact_context:
            triples = _state_memories(rec, "fact")
            for j, dpos in enumerate(distractor_pos):
                triples.extend(_state_memories(records[dpos], f"dx{j}s"))
            rng.shuffle(triples)  # deterministic: rng is seed-driven
            seen: set = set()
            for local_id, src_rid, content, sdate in triples:
                if content in seen:  # same-entity distractor duplicate states
                    continue
                seen.add(content)
                memories.append(MemoryItem(
                    memory_id=f"{rid}/{local_id}",
                    content=content,
                    metadata={"session_id": src_rid,
                              "session_date": sdate},
                ))
        else:
            # Raw-article mode: chunk each article into paragraph-level
            # memories (granularity matched to conversational rounds so the
            # pipeline's retrieval/sweeps work as designed). Paragraphs carry
            # no timestamp — date arithmetic relies on the extraction
            # contract's stated_date field (dates stated in the prose).
            docs = [(rid, rec)] + [
                (str(records[d].get("id", f"L2_{d}")), records[d])
                for d in distractor_pos
            ]
            for src_id, src in docs:
                text = (src.get("context") or "").strip()
                if not text:
                    continue
                # Articles are single-line; split into sentences and pack
                # to ~450-char chunks.
                sentences = re.split(r"(?<=[.!?])\s+", text)
                chunks: List[str] = []
                buf = ""
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if len(buf) + len(sent) < 450:
                        buf = f"{buf} {sent}".strip()
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = sent
                if buf:
                    chunks.append(buf)
                for ci, chunk in enumerate(chunks):
                    memories.append(MemoryItem(
                        memory_id=f"{rid}/doc:{src_id}:p{ci}",
                        content=chunk,
                        metadata={"session_id": src_id, "session_date": ""},
                    ))

        answers = (rec.get("text_answers") or {}).get("text") or []
        instances.append(QAInstance(
            question_id=rid,
            question=rec.get("question", ""),
            gold_answer=" OR ".join(str(a) for a in answers),
            memories=memories,
            question_date=_question_date(rec.get("date", "")),
            question_type="tempreason_l2",
            extra={
                "neg_answers": rec.get("neg_answers") or [],
                "raw_date": rec.get("date", ""),
                "entity": entity,
                "n_gold_states": len(_split_states(rec.get("fact_context", ""))),
                "distractor_ids": [str(records[d].get("id", "")) for d in distractor_pos],
            },
        ))
    return instances


if __name__ == "__main__":
    data_path = Path(__file__).resolve().parent.parent / "data" / "tempreason" / "test_l2.json"
    insts = load_tempreason(data_path, limit=5, seed=0)
    for inst in insts:
        print("=" * 78)
        print(f"[{inst.question_id}] {inst.question}")
        print(f"  question_date: {inst.question_date}   gold: {inst.gold_answer}")
        print(f"  neg_answers:   {inst.extra['neg_answers']}")
        print(f"  memories ({len(inst.memories)}):")
        for m in inst.memories:
            print(f"    ({m.metadata['session_date'] or '????-??-??'}) "
                  f"[{m.metadata['session_id']}] {m.content}")
