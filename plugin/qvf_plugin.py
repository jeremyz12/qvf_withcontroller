# -*- coding: utf-8 -*-
"""QVF — Query-conditioned Validity Filtering, as a plug-and-play memory layer.

Single-file, dependency-light (only `anthropic`). Packaged from the evaluated
mechanisms in the QVF research repo (write-side card contract, selection/chain,
membership filter with deterministic authorization, certification lines,
code-side aggregation operators, type routing with fallbacks). Numbers behind
each mechanism: see README.md.

Usage:
    from qvf_plugin import QVFMemory
    mem = QVFMemory()                      # uses ANTHROPIC_API_KEY env
    mem.ingest("Officially started at CERN today...", date="1989-06-01")
    out = mem.ask("Which employer did I hold the longest?", today="1998-09-01")
    print(out["answer"], out["route"])
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Optional

import anthropic

DEFAULT_MODEL = "claude-haiku-4-5"
EVIDENCE_CAP = 12

# ── 1. write side: session → dated state cards ─────────────────────────────

CARD_CONTRACT = """You extract STATE CARDS from one dated chat session.

A state card records the user declaring that some personal attribute (a SLOT)
took a NEW VALUE. Extract one card per declaration. Ignore questions, wishes,
third parties, and mere mentions that are not the user's own state change.

Return ONLY a JSON list; each card:
{"slot_class": "<canonical attribute, e.g. employer / home_city / car_model>",
 "value": "<the new value, verbatim where possible>",
 "stated_date": "<YYYY-MM-DD if the text states one, else null>",
 "source_span": "<EXACT verbatim substring of the session that declares it>",
 "slot_cardinality": "single" or "set",
 "replaces": "<previous value if the text says so, else null>"}

Rules: source_span must be copied character-for-character from the session.
slot_cardinality = "set" only for accumulative attributes (owned items,
hobbies collected), "single" for replace-on-change attributes (employer,
address, phone). Return [] if no declarations."""

COMPILE_PROMPT = """Compile the user's question into one memory-query plan.

QUESTION: {q}

Return ONLY JSON:
{{"op": one of ["current","point_in_time","change_count","count_before",
              "longest_tenure","first_vs_last","trajectory","other"],
  "slot": "<attribute asked about, canonical short name>",
  "date": "<YYYY-MM-DD if the question pins one, else null>"}}"""

READER_SYSTEM = (
    "You are the user's personal AI assistant. You will be shown EXCERPTS "
    "or memory notes from past conversations (each dated), followed by the "
    "user's new message. Reply naturally and helpfully in 1-3 sentences.")

MEMBER_PROMPT = """You are auditing a memory store. Target attribute (slot): {slot}

Some candidate cards below are TRUE STATE DECLARATIONS of this slot; others are
adjacent-topic attributes that merely share the theme. For EACH card decide:
is its value a state OF THE SLOT ITSELF? NEVER infer membership from topical
closeness. For every member=true copy the exact substring of the card's quote
that declares the state into `evidence`.

Cards:
{cards}

Return ONLY JSON: {{"decisions":[{{"i":0,"member":true,"evidence":"..."}}]}}"""


def _pdate(s) -> Optional[date]:
    if not s:
        return None
    m = re.match(r"(\d{4})-?(\d{0,2})-?(\d{0,2})", str(s))
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 1) or 1, int(m.group(3) or 1) or 1
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _json_block(text: str):
    try:
        i, j = text.index("["), text.rindex("]") + 1
        return json.loads(text[i:j])
    except Exception:
        try:
            i, j = text.index("{"), text.rindex("}") + 1
            return json.loads(text[i:j])
        except Exception:
            return None


_WORD = re.compile(r"[a-z0-9]+")


def _words(s: str) -> set:
    return {w for w in _WORD.findall(str(s).lower()) if len(w) > 2}


@dataclass
class Card:
    slot_class: str
    value: str
    stated_date: Optional[str]
    source_span: str
    session_date: str
    slot_cardinality: str = "single"
    replaces: Optional[str] = None
    member_checked: bool = False

    @property
    def eff_date(self) -> Optional[date]:
        return _pdate(self.stated_date) or _pdate(self.session_date)


@dataclass
class QVFMemory:
    """Plug-and-play QVF memory. ingest() builds cards; ask() routes & answers."""
    api_key: Optional[str] = None
    model: str = DEFAULT_MODEL
    membership_filter: bool = True       # semantic-role filter + deterministic auth
    cards: list = field(default_factory=list)
    sessions: list = field(default_factory=list)   # [(date, text)] for fallback
    _client: object = field(default=None, repr=False)

    def __post_init__(self):
        self._client = anthropic.Anthropic(
            api_key=self.api_key or os.environ.get("ANTHROPIC_API_KEY"))

    # ── LLM helper ──
    def _llm(self, prompt: str, system: Optional[str] = None, max_tokens=1200) -> str:
        kw = dict(model=self.model, max_tokens=max_tokens, temperature=0.0,
                  messages=[{"role": "user", "content": prompt}])
        if system:
            kw["system"] = system
        r = self._client.messages.create(**kw)
        return "".join(b.text for b in r.content if b.type == "text")

    # ── write side (Algorithm 1) ──
    def ingest(self, session_text: str, date: str) -> int:
        """Extract dated state cards from one session. Returns #cards kept."""
        self.sessions.append((str(date), session_text))
        raw = _json_block(self._llm(
            f"{CARD_CONTRACT}\n\nSESSION DATE: {date}\nSESSION:\n{session_text}"))
        kept = 0
        for c in raw or []:
            span = str(c.get("source_span") or "")
            if not span or span not in session_text:      # anchor must be verbatim
                continue                                   # fail-closed drop
            self.cards.append(Card(
                slot_class=str(c.get("slot_class") or "").strip().lower(),
                value=str(c.get("value") or "").strip(),
                stated_date=c.get("stated_date"),
                source_span=span, session_date=str(date),
                slot_cardinality=str(c.get("slot_cardinality") or "single"),
                replaces=c.get("replaces")))
            kept += 1
        return kept

    # ── selection (Algorithm 2) ──
    def _select(self, slot: str):
        sw = _words(slot)
        pool = [c for c in self.cards
                if c.slot_class == slot
                or (sw and sw & _words(c.slot_class))]
        pool = [c for c in pool if c.eff_date]
        pool.sort(key=lambda c: c.eff_date)
        chain, prev = [], None
        for c in pool:                                     # merge adjacent dups
            if prev is None or c.value.lower() != prev.value.lower():
                chain.append(c)
            prev = c
        return chain[:EVIDENCE_CAP]

    # ── membership filter (Algorithm 3) ──
    def _filter(self, chain, slot: str):
        todo = [c for c in chain if not c.member_checked]
        if not todo:
            return [c for c in chain if c.member_checked]
        cards_txt = "\n".join(
            f'- i={i} value="{c.value}" date="{c.eff_date}" quote="{c.source_span}"'
            for i, c in enumerate(chain))
        out = _json_block(self._llm(MEMBER_PROMPT.format(slot=slot, cards=cards_txt)))
        blob = "\n".join(t for _, t in self.sessions)
        keep = []
        decs = out if isinstance(out, list) else (out or {}).get("decisions", [])
        dec = {d.get("i"): d for d in decs if isinstance(d, dict)}
        for i, c in enumerate(chain):                      # deterministic authorization
            d = dec.get(i)
            ev = str((d or {}).get("evidence") or "").strip()
            ok = bool(d and d.get("member")) and bool(ev)
            if ok and ev not in c.source_span:
                w = _words(ev)
                ok = bool(w) and len(w & _words(c.source_span)) / len(w) >= 0.8
            ok = ok and c.source_span in blob
            if ok:                                         # model proposes, code authorizes
                c.member_checked = True
                keep.append(c)
        return keep

    # ── certification lines (Algorithm 4; no aggregates → leak-safe) ──
    @staticmethod
    def _certify(chain, t_q: date):
        lines = []
        for i, c in enumerate(chain):
            start = c.eff_date
            end = chain[i + 1].eff_date if i + 1 < len(chain) else None
            if start > t_q:
                role = "not yet active on that date"
            elif end is None or end > t_q:
                role = "current as of that date"
            else:
                role = f"superseded on {end} by \"{chain[i + 1].value}\""
            lines.append(f"[{start}] {c.slot_class}: {c.value} — {role} "
                         f"— \"{c.source_span}\"")
        return lines

    # ── operators (Algorithm 5) ──
    @staticmethod
    def _compute(op: str, chain, t_q: date, pin: Optional[date], card_set: bool):
        vals = [c.value for c in chain]
        if card_set:                                       # set-semantics branch
            if op == "current":
                return "Values held (accumulative attribute): " + ", ".join(vals)
            if op in ("change_count", "count_before"):
                sub = [c for c in chain if not pin or c.eff_date < pin]
                return f"Distinct values{' before ' + str(pin) if pin else ''}: " \
                       f"{len({c.value.lower() for c in sub})}"
        if op == "change_count":
            return f"The value changed {max(len(chain) - 1, 0)} times."
        if op == "count_before" and pin:
            sub = [c for c in chain if c.eff_date < pin]
            return f"Distinct values before {pin}: {len({c.value.lower() for c in sub})}"
        if op == "point_in_time" and pin:
            cur = None
            for c in chain:
                if c.eff_date <= pin:
                    cur = c
            return f"On {pin} the value was: {cur.value}" if cur else None
        if op == "longest_tenure":
            per = {}
            for i, c in enumerate(chain[:-1]):
                per[c.value] = per.get(c.value, 0) + \
                    (chain[i + 1].eff_date - c.eff_date).days
            if not per:
                return None
            best = max(per.values())
            win = [v for v, d in per.items() if d == best]
            return (f"Held longest (closed intervals): {win[0]} ({best} days)"
                    if len(win) == 1 else None)
        if op == "first_vs_last":
            return f"First: {vals[0]}; most recent: {vals[-1]}"
        if op == "trajectory":
            return "Order of values: " + " -> ".join(vals)
        return None

    # ── fallback: lexical top-k direct read ──
    def _direct(self, question: str, today: Optional[str], k: int = 10):
        qw = _words(question)
        scored = sorted(self.sessions,
                        key=lambda s: -len(qw & _words(s[1])))[:k]
        scored.sort(key=lambda s: s[0])
        ev = [f"[{d}] {t[:600]}" for d, t in scored]
        return self._read(ev, [], question, today), ev

    def _read(self, ev, derived, question, today):
        body = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
        body += ev or ["(no matching records found in memory)"]
        body += [f"[memory summary] {d}" for d in derived]
        if today:
            body += ["", f"TODAY'S DATE: {today}"]
        body += ["", f"USER'S NEW MESSAGE: {question}"]
        return self._llm("\n".join(body), system=READER_SYSTEM, max_tokens=400)

    # ── ask (Algorithms 2-6 wired; Algorithm 6 = routing) ──
    def ask(self, question: str, today: Optional[str] = None) -> dict:
        plan = _json_block(self._llm(COMPILE_PROMPT.format(q=question))) or {}
        op = str(plan.get("op") or "other")
        slot = str(plan.get("slot") or "").strip().lower()
        pin = _pdate(plan.get("date"))
        t_q = _pdate(today) or pin or date.today()

        if op in ("current", "other") and not slot:
            ans, ev = self._direct(question, today)
            return {"answer": ans, "route": "direct(no-slot)", "plan": plan,
                    "evidence": ev}
        if op == "current":                                # type routing
            chain = self._select(slot)
            card_set = sum(c.slot_cardinality == "set" for c in chain) \
                > len(chain) / 2 if chain else False
            if not card_set:                               # single-valued → direct
                ans, ev = self._direct(question, today)
                return {"answer": ans, "route": "direct(current)", "plan": plan,
                        "evidence": ev}

        chain = self._select(slot)
        if self.membership_filter and chain:
            chain = self._filter(chain, slot)
        if not chain:                                      # empty evidence → direct
            ans, ev = self._direct(question, today)
            return {"answer": ans, "route": "direct(empty-evidence)",
                    "plan": plan, "evidence": ev}
        card_set = sum(c.slot_cardinality == "set" for c in chain) > len(chain) / 2
        ev = self._certify(chain, t_q)
        derived = []
        d = self._compute(op, chain, t_q, pin, card_set)
        if d:
            derived.append(d + " This IS the derived result; state it.")
        ans = self._read(ev, derived, question, today)
        return {"answer": ans, "route": f"qvf({op})", "plan": plan,
                "evidence": ev, "derived": derived}

    # ── persistence ──
    def save(self, path: str):
        json.dump({"cards": [asdict(c) for c in self.cards],
                   "sessions": self.sessions},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def load(self, path: str):
        d = json.load(open(path, encoding="utf-8"))
        self.cards = [Card(**c) for c in d["cards"]]
        self.sessions = [tuple(s) for s in d["sessions"]]
        return self
