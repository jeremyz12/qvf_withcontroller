"""STALE-Chain generator: multi-state evolution items extending STALE
(CC BY 4.0 derivative; haystack distractor sessions remixed from the original
with attribution). Each item: one slot evolving through 3-5 dated states,
embedded among distractor sessions; four probing queries (current / mid-state
premise trap / point-in-time / trajectory).

Generation model: claude-opus-5 (generator != reader; judge is blind to
generation). Deterministic validators: verbatim span presence, strictly
increasing dates, pairwise-distinct values.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

TOPICS = [
    "residence city", "job title", "phone model", "gym membership",
    "car model", "primary bank", "favorite coffee shop", "diet plan",
    "commute mode", "streaming subscription", "doctor/clinic",
    "programming language at work", "apartment furniture", "pet",
    "weekend hobby", "project codename", "team assignment",
    "insurance provider", "hair style", "travel plan",
]


class ChainState(BaseModel):
    value: str = Field(description="The slot value at this stage, short.")
    date: str = Field(description="Session date YYYY-MM-DD; strictly later than the previous state.")
    session_turns: list[str] = Field(
        description="3-5 casual first-person user messages forming this session. "
        "EXACTLY ONE turn must state the new value naturally (moving/changing/"
        "switching language for later states). No other state values mentioned."
    )
    state_span: str = Field(
        description="VERBATIM contiguous substring of one session turn that "
        "states this value (will be checked mechanically)."
    )


class ChainItem(BaseModel):
    slot: str
    chain: list[ChainState] = Field(description="3 to 5 states, chronological.")
    q_current: str = Field(description="Natural question asking the CURRENT state.")
    q_premise_mid: str = Field(
        description="Question that PRESUPPOSES one intermediate (not first, not "
        "last) state as still true, asking for related help."
    )
    premise_mid_index: int = Field(description="Index into chain of the presupposed state.")
    q_point_in_time: str = Field(
        description="Question asking the state AT a specific past date that falls "
        "strictly between two updates (name the date explicitly)."
    )
    point_date: str = Field(description="That date, YYYY-MM-DD.")
    point_gold_index: int = Field(description="Index into chain of the state valid at point_date.")
    q_trajectory: str = Field(description="Question asking how the state changed over time.")


GEN_PROMPT = """You create ONE benchmark item for a long-term-memory assistant
evaluation. A single user attribute (slot) evolves through {n_states} states
over time. Write natural, varied, casual user messages — no meta language.
Constraints:
- Values pairwise distinct and unambiguous.
- Dates strictly increasing, spread over 6-18 months, all in 2025.
- Later states use natural change language sometimes explicit ("we moved"),
  sometimes oblique ("signing the lease next to the river tomorrow").
- point_in_time date must fall strictly BETWEEN two consecutive state dates.
- The premise question presupposes an intermediate state (index given).
Topic/slot: {topic}
Variation key: {vkey} — make this item clearly distinct from any other item on
the same topic (different names, places, brands, values, writing style).
"""


def validate(item: ChainItem) -> list[str]:
    errs = []
    ch = item.chain
    if not (3 <= len(ch) <= 5):
        errs.append("chain length")
    if len({s.value.strip().lower() for s in ch}) != len(ch):
        errs.append("values not distinct")
    dates = [s.date for s in ch]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        errs.append("dates not strictly increasing")
    for i, s in enumerate(ch):
        if not any(s.state_span in t for t in s.session_turns):
            errs.append(f"span missing in state {i}")
        if s.value.lower() not in s.state_span.lower():
            errs.append(f"value not inside span {i}")
    if not (0 < item.premise_mid_index < len(ch) - 1):
        errs.append("premise index not intermediate")
    if not (0 <= item.point_gold_index < len(ch)):
        errs.append("point gold index range")
    else:
        pd = item.point_date
        gi = item.point_gold_index
        if not (ch[gi].date <= pd and (gi + 1 >= len(ch) or pd < ch[gi + 1].date)):
            errs.append("point date/gold mismatch")
        if pd in dates:
            errs.append("point date equals an update date")
    return errs


def build_haystack(rng, stale_items, chain_states, n_distractors=30):
    """Distractor sessions remixed from original STALE haystacks (CC BY),
    merged chronologically with the chain sessions."""
    pool = []
    for it in rng.sample(stale_items, 12):
        for sess in (it.get("haystack_session") or [])[:6]:
            turns = sess if isinstance(sess, list) else [str(sess)]
            pool.append([str(t)[:400] for t in turns[:5]])
    rng.shuffle(pool)
    distractors = pool[:n_distractors]
    sessions = []
    for i, st in enumerate(chain_states):
        sessions.append({"date": st.date, "turns": st.session_turns, "chain_index": i})
    for j, turns in enumerate(distractors):
        y, m = 2025, 1 + (j % 12)
        d = 1 + (j * 7) % 27
        sessions.append({"date": f"{y}-{m:02d}-{d:02d}", "turns": turns, "chain_index": None})
    sessions.sort(key=lambda s: s["date"])
    return sessions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--out", default="data/stale_chain_pilot.json")
    ap.add_argument("--model", default="claude-opus-5")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    stale_items = json.load(open("data/stale_T1_T2_400_FULL.json", encoding="utf-8"))
    client = anthropic.Anthropic()
    out = []
    topics = [TOPICS[i % len(TOPICS)] for i in range(args.n)]
    rng.shuffle(topics)
    for i, topic in enumerate(topics):
        n_states = rng.choice([3, 3, 4, 4, 5])
        for attempt in range(3):
            resp = client.messages.parse(
                model=args.model,
                max_tokens=16000,
                messages=[{"role": "user", "content": GEN_PROMPT.format(
                    n_states=n_states, topic=topic,
                    vkey=f"{args.seed}-{i}")}],
                output_format=ChainItem,
            )
            item = resp.parsed_output
            if item is None:
                continue
            errs = validate(item)
            if not errs:
                break
            print(f"[{topic}] attempt {attempt}: {errs}", file=sys.stderr)
        else:
            print(f"[{topic}] FAILED validation 3x, skipped", file=sys.stderr)
            continue
        sessions = build_haystack(rng, stale_items, item.chain)
        uid = f"chain{i:03d}-{rng.randrange(16**8):08x}"
        last = item.chain[-1]
        mid = item.chain[item.premise_mid_index]
        point = item.chain[item.point_gold_index]
        out.append({
            "uid": uid,
            "type": "CHAIN",
            "slot": item.slot,
            "chain": [s.model_dump() for s in item.chain],
            "sessions": sessions,
            "probing_queries": {
                "dim1_current": {"q": item.q_current, "gold": last.value},
                "dim2_premise_mid": {"q": item.q_premise_mid, "gold": last.value,
                                     "presupposed": mid.value},
                "dim4_point_in_time": {"q": item.q_point_in_time, "gold": point.value,
                                       "date": item.point_date},
                "dim5_trajectory": {"q": item.q_trajectory,
                                    "gold": " -> ".join(s.value for s in item.chain)},
            },
            "attribution": "Derivative of STALE (arXiv 2605.06527, CC BY 4.0): "
                           "distractor sessions remixed from the original haystacks.",
        })
        print(f"[{topic}] ok: {len(item.chain)} states, "
              f"{len(sessions)} sessions", file=sys.stderr)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"wrote {len(out)} items -> {args.out}")


if __name__ == "__main__":
    main()
