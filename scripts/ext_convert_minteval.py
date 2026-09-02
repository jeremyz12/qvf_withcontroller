# -*- coding: utf-8 -*-
"""Convert the MINTEval `multi_turn_dialogue` split (arXiv:2605.18565,
HF: dinobby/MINTEval, CC-BY-4.0) into our unified external-benchmark format.

Input : data/external/minteval/multi_turn_dialogue-00000-of-00001.parquet
Output: data/external/minteval_unified.json   (sampled users only, see below)
        data/external/minteval_cardable.json  (+ placeholder chain/probing_queries)

Why only the sampled users: one user's context is 0.5-2.8M characters, so the
full 100-user split is ~144M characters of JSON. `ext_smoc_arm` / `ext_direct_arm`
load the whole `--data` file into memory, so we materialize only the seeded
sample. The sample is drawn here (seed 33, pre-registered in
results/opt_batch33_prereg.md track 33-G) and written to
data/external/minteval_sampled_uids.txt so the choice is auditable.

Unified format (one store per MINTEval record = one simulated user):
  {"uid": "minteval-<nnn>",
   "sessions": [{"date": "YYYY-MM-DD", "turns": ["scenario: ...", "user: ...", ...]}],
   "questions": [{"qid", "question", "gold", "dim", "meta": {...}}]}

`contexts[i].content` is one dated dialogue session rendered as text: an optional
"[scenario] ..." header line followed by "user: ..." / "assistant: ..." turns whose
bodies may span multiple lines. We split it back into one turn per speaker line
(continuation lines are re-attached to their own turn) so that a memory item is a
single conversational turn -- byte-for-byte the same granularity STALE / MemOps /
MemConflict use, which keeps the dense-retrieval baseline comparable across arenas.

Gold answers ship with the dataset (short canonical strings, plus a `candidates`
list for most question types), so no gold is invented here.

Run:  PYTHONUTF8=1 python scripts/ext_convert_minteval.py [--n-users 40] [--seed 33]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "external", "minteval",
                   "multi_turn_dialogue-00000-of-00001.parquet")
DST = os.path.join(REPO, "data", "external", "minteval_unified.json")
DST_CARD = os.path.join(REPO, "data", "external", "minteval_cardable.json")
DST_UIDS = os.path.join(REPO, "data", "external", "minteval_sampled_uids.txt")

_SPEAKER = re.compile(r"^(user|assistant):\s?")


def split_turns(content: str) -> list:
    """One turn per speaker line; continuation lines re-attached to their turn.
    A leading '[scenario] ...' header becomes a 'scenario: ...' turn."""
    turns: list = []
    cur: list = []
    for line in content.split("\n"):
        if _SPEAKER.match(line):
            if cur:
                turns.append("\n".join(cur).rstrip())
            cur = [line]
        elif line.startswith("[scenario]"):
            if cur:
                turns.append("\n".join(cur).rstrip())
            cur = ["scenario: " + line[len("[scenario]"):].strip()]
        else:
            if not cur:          # stray leading text: start a turn for it
                cur = [line]
            else:
                cur.append(line)
    if cur:
        turns.append("\n".join(cur).rstrip())
    return [t for t in turns if t.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-users", type=int, default=40)
    ap.add_argument("--seed", type=int, default=33)
    a = ap.parse_args()

    import pyarrow.parquet as pq

    print("loading", SRC)
    rows = pq.read_table(SRC).to_pylist()
    print("records in split:", len(rows))
    rows.sort(key=lambda r: r["id"])          # deterministic order before sampling

    rng = random.Random(a.seed)
    idx = sorted(rng.sample(range(len(rows)), a.n_users))
    print("sampled %d users (seed %d)" % (len(idx), a.seed))

    stores = []
    for n, i in enumerate(idx):
        rec = rows[i]
        uid = "minteval-%03d" % n
        sessions = []
        for c in rec["contexts"]:
            date = (c["timestamp"] or "")[:10]
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date), \
                "bad timestamp %r in %s" % (c["timestamp"], rec["id"])
            turns = split_turns(c["content"])
            assert turns, "empty session in %s" % rec["id"]
            sessions.append({"date": date, "turns": turns})
        # sessions arrive in chronological order; assert it rather than resort
        ds = [s["date"] for s in sessions]
        assert ds == sorted(ds), "non-monotonic session dates in %s" % rec["id"]

        questions = []
        for qi, q in enumerate(rec["questions"]):
            qm = json.loads(q["metadata"]) if q["metadata"] else {}
            questions.append({
                "qid": "%s-q%03d" % (uid, qi),
                "question": q["question"],
                "gold": q["answer"],
                "dim": q["question_type"],
                "meta": {
                    "n_steps_back": qm.get("n_steps_back"),
                    "candidates": qm.get("candidates"),
                    "orig_id": rec["id"],
                    "orig_metadata": rec["metadata"],
                },
            })
        stores.append({"uid": uid, "orig_id": rec["id"],
                       "sessions": sessions, "questions": questions})

    # ---- verification ----
    sizes, nturn, nsess = [], [], []
    maxturn = 0
    for s in stores:
        sizes.append(sum(len(t) for ss in s["sessions"] for t in ss["turns"]))
        nturn.append(sum(len(ss["turns"]) for ss in s["sessions"]))
        nsess.append(len(s["sessions"]))
        maxturn = max(maxturn, max(len(t) for ss in s["sessions"]
                                   for t in ss["turns"]))
        for q in s["questions"]:
            assert q["question"].strip() and str(q["gold"]).strip()
    print("stores: %d   questions: %d" % (
        len(stores), sum(len(s["questions"]) for s in stores)))
    print("sessions/user: min %d med %d max %d" % (
        min(nsess), statistics.median(nsess), max(nsess)))
    print("turns/user:    min %d med %d max %d" % (
        min(nturn), statistics.median(nturn), max(nturn)))
    print("chars/user:    min %d med %d mean %.0f max %d  TOTAL %d" % (
        min(sizes), statistics.median(sizes), statistics.mean(sizes),
        max(sizes), sum(sizes)))
    print("longest single turn: %d chars (~%d tok)" % (maxturn, maxturn / 4))

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(stores, f, ensure_ascii=False)
    print("wrote", DST, "(%d bytes)" % os.path.getsize(DST))

    # cardable copy: load_stale_chain needs a chain + probing_queries placeholder
    for s in stores:
        last = next((ss["date"] for ss in reversed(s["sessions"]) if ss["date"]),
                    "2026-01-01")
        s["chain"] = [{"date": last, "value": ""}]
        s["probing_queries"] = {"_placeholder": {"q": "placeholder", "gold": ""}}
    with open(DST_CARD, "w", encoding="utf-8") as f:
        json.dump(stores, f, ensure_ascii=False)
    print("wrote", DST_CARD, "(%d bytes)" % os.path.getsize(DST_CARD))

    with open(DST_UIDS, "w", encoding="utf-8") as f:
        for s in stores:
            f.write("%s\t%s\t%d\n" % (s["uid"], s["orig_id"],
                                      sum(len(t) for ss in s["sessions"]
                                          for t in ss["turns"])))
    print("wrote", DST_UIDS)


if __name__ == "__main__":
    main()
