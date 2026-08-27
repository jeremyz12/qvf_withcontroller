# -*- coding: utf-8 -*-
"""Convert MemConflict (arXiv:2605.20926) Step4_4.jsonl into QVF unified store format.

Source : data/external/memconflict/Step4_4.jsonl
         (github.com/TaoZhen1110/MemConflict, Data/Step4_4.jsonl — expanded release,
          30 instances / 1579 sessions / 3750 questions; the paper's table cites the
          smaller original release of 12 / ~628 / ~1492)
Output : data/external/memconflict_unified.json

Unified schema (one store per MemConflict instance):
  {"uid": "memconflict-<n>",                       # n = 0-based line index in Step4_4.jsonl
   "sessions": [{"date": "YYYY-MM-DD",             # real per-session timestamps (always present)
                 "turns": ["user: ...", "assistant: ...", ...]}],
   "questions": [{"qid", "question", "gold", "dim", "meta"}]}

dim  : conflict type — "dynamic" | "static" | "conditional"
meta : fields the arena's own LLM judge / analysis needs:
       conflict_type (full label), ability_target, difficulty,
       question_id (arena-local), session_id, session_date (when the query is posed),
       question_trigger_types.

Run:  python scripts/ext_convert_memconflict.py
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "external", "memconflict", "Step4_4.jsonl")
DST = os.path.join(ROOT, "data", "external", "memconflict_unified.json")

DIM_MAP = {
    "dynamic_conflict": "dynamic",
    "static_conflict": "static",
    "conditional_conflict": "conditional",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TURN_KEY_RE = re.compile(r"^dialogue_turn_(\d+)$")


ANOMALY_COUNTS = {"role_key_nested": 0, "role_key_flat": 0, "missing_content_skipped": 0}


def parse_message(msg):
    """Return (role, content) or None for a skippable malformed message.

    Handles LLM-generation noise present in the released file:
      {"role": r, "content": c[, "name": ...]}      -> normal (71k+ messages)
      {"assistant": {"content": c, ...}}            -> role-keyed nested dict (19x)
      {"assistant": "content", "content": c}        -> role-keyed flat (5x)
      {"role": "assistant"}                         -> no content, skip (2x)
    """
    if "role" in msg:
        role = msg["role"]
        assert role in ("user", "assistant"), f"unexpected role: {role!r}"
        if "content" in msg:
            return role, msg["content"]
        ANOMALY_COUNTS["missing_content_skipped"] += 1
        return None
    for role in ("user", "assistant"):
        if role in msg:
            val = msg[role]
            if isinstance(val, dict) and "content" in val:
                ANOMALY_COUNTS["role_key_nested"] += 1
                return role, val["content"]
            if "content" in msg:
                ANOMALY_COUNTS["role_key_flat"] += 1
                return role, msg["content"]
            if isinstance(val, str):
                ANOMALY_COUNTS["role_key_flat"] += 1
                return role, val
    raise AssertionError(f"unparseable message: {json.dumps(msg)[:200]}")


def flatten_dialogue(session_dialogue):
    """Session_Dialogue is {'dialogue_turn_N': [msg, ...]} (usually [user, assistant]).
    Sort by N numerically (lexicographic would put _10 before _2), then flatten."""
    turns = []
    keys = []
    for k in session_dialogue.keys():
        m = TURN_KEY_RE.match(k)
        assert m, f"unexpected dialogue key: {k!r}"
        keys.append((int(m.group(1)), k))
    keys.sort()
    for _, k in keys:
        for msg in session_dialogue[k]:
            parsed = parse_message(msg)
            if parsed is None:
                continue
            role, content = parsed
            content = str(content).replace("\r\n", "\n").strip()
            turns.append(f"{role}: {content}")
    return turns


def main():
    stores = []
    seen_qids = set()
    n_sessions = n_turns = n_questions = 0
    dims = {}
    with open(SRC, encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            rec = json.loads(line)
            uid = f"memconflict-{idx}"
            sessions = []
            questions = []
            chain = rec["Full_Session_Chain"]
            for s in chain:
                date = s.get("Date") or ""
                if date and not DATE_RE.match(date):
                    raise AssertionError(f"{uid}: bad date {date!r}")
                dlg = s.get("Session_Dialogue") or {}
                turns = flatten_dialogue(dlg)
                assert turns, f"{uid} session {s.get('Session_ID')}: empty dialogue"
                sessions.append({"date": date, "turns": turns})
                n_turns += len(turns)
                for q in s.get("Session_Questions") or []:
                    qid = f"{uid}-s{s['Session_ID']}-{q['question_id']}"
                    assert qid not in seen_qids, f"duplicate qid {qid}"
                    seen_qids.add(qid)
                    qtext = str(q["question"]).strip()
                    gold = str(q["answer"]).strip()
                    assert qtext, f"{qid}: empty question"
                    assert gold, f"{qid}: empty gold"
                    dim = DIM_MAP[q["conflict_type"]]
                    dims[dim] = dims.get(dim, 0) + 1
                    questions.append({
                        "qid": qid,
                        "question": qtext,
                        "gold": gold,
                        "dim": dim,
                        "meta": {
                            "conflict_type": q["conflict_type"],
                            "ability_target": q.get("ability_target"),
                            "difficulty": q.get("difficulty"),
                            "question_id": q["question_id"],
                            "session_id": s["Session_ID"],
                            "session_date": date,
                            "question_trigger_types": s.get("Question_Trigger_Types") or [],
                        },
                    })
            n_sessions += len(sessions)
            n_questions += len(questions)
            assert questions, f"{uid}: no questions"
            stores.append({"uid": uid, "sessions": sessions, "questions": questions})

    with open(DST, "w", encoding="utf-8") as fh:
        json.dump(stores, fh, ensure_ascii=False, separators=(",", ": "))

    # ---- verification report ----
    store_chars = [sum(len(t) for sess in st["sessions"] for t in sess["turns"]) for st in stores]
    store_json_chars = [len(json.dumps(st, ensure_ascii=False)) for st in stores]
    empty_dates = sum(1 for st in stores for sess in st["sessions"] if not sess["date"])
    print(f"stores            : {len(stores)}")
    print(f"sessions          : {n_sessions}")
    print(f"turns (messages)  : {n_turns}")
    print(f"questions         : {n_questions}  by dim: {dims}")
    print(f"sessions w/o date : {empty_dates}")
    print(f"anomalies healed  : {ANOMALY_COUNTS}")
    print(f"turn-chars/store  : mean={sum(store_chars)//len(store_chars)} "
          f"min={min(store_chars)} max={max(store_chars)}")
    print(f"json-chars/store  : mean={sum(store_json_chars)//len(store_json_chars)} "
          f"min={min(store_json_chars)} max={max(store_json_chars)}")
    print(f"output            : {DST}  ({os.path.getsize(DST)} bytes)")


if __name__ == "__main__":
    main()
