# -*- coding: utf-8 -*-
"""Convert AMemGym (arXiv:2603.01966, ICLR 2026) v1.base to the QVF unified store format.

Source : data/external/amemgym/data.json
         (HuggingFace `AGI-Eval/AMemGym`, config `default`, split `v1.base`,
          file `v1.base/data.json`, license CC-BY-4.0; 20 personas)
Official harness: https://github.com/AGI-Eval-Official/amemgym (MIT), the copy of
         the scoring modules used to rebuild the metric here lives in
         data/external/amemgym/official/.
Output : data/external/amemgym_unified.json
         [{"uid": "amemgym-NN",
           "sessions": [{"date": "YYYY-MM-DD", "turns": ["user: ..."]}, ...],
           "questions": [{"qid", "question", "gold", "dim", "cutoff", "meta"}, ...]}]

WHAT THE OFFICIAL BENCHMARK DOES (src/amemgym/eval/overall.py, verbatim logic):
  For every persona, for every period pi (0..10) in order, the assistant first
  *interacts* with that period's sessions (user query -> assistant reply, the
  assistant's own memory machinery updating as it goes), then is asked all 10
  `qas`.  Each question is rendered as OVERALL_PROMPT = the query + the numbered
  answer_choices + "output {\"answer\": int}".  Scoring
  (eval/metric.py::state_similarity, metric "accuracy") is **exact match on the
  state tuple**: the chosen choice's `state` list must equal the golden state
  [period["state"][k] for k in qa["required_info"]] in full; partial credit is
  0.  A JSON parse failure falls back to a uniformly random choice.
  20 personas x 11 periods x 10 qas = 2,200 (question, period) pairs.

OFF-POLICY DISCLOSURE (the single deviation of this conversion):
  AMemGym is an *on-policy* environment: the assistant's own replies are part of
  the transcript it later reads.  A static file cannot carry those replies, so
  this converter keeps **only the user utterances** (`session["query"]`,
  prefixed with the official `[Current Time: ...]` header exactly as
  overall.py builds `query_with_time`) and drops the assistant side.  The
  resulting arena is therefore *off-policy / static*, and absolute numbers are
  NOT comparable to the paper's tables.
  This is sound for state tracking because the gold is carried entirely by the
  user side: the exposed-state audit below asserts that for all 2,200 pairs the
  most recent value of BOTH required state keys exposed in the user queries up
  to and including that period equals the period's gold state.

CUTOFF SEMANTICS:
  question["cutoff"] = period["period_end"].  Verified below: filtering the
  session stream by `date <= period_end` selects exactly the sessions of
  periods 0..pi -- no leakage forward, no loss backward.  Both arms already
  implement `cutoff` (ext_smoc_arm filters+renumbers ledger rows,
  ext_direct_arm filters the memory stream before retrieval), so the frozen
  arms need no change.

QUESTION RENDERING (one disclosed deviation from OVERALL_PROMPT):
  query + choice block are reproduced verbatim; the official
  "output in the following JSON format" tail is replaced by "Answer with the
  number of the single best option." because both frozen arms carry their own
  output protocol (smoc: "ANSWER: <value>"; direct: 1-3 sentence chat reply) and
  batch 29c showed that stacking a second output protocol on a haiku reader
  costs ~11pp of accuracy.  The "(Today is <period_end>.)" prefix is the batch
  17 external-arena convention (ext_direct_arm._TODAY_RE lifts it into TODAY'S
  DATE; the smoc reader sees it inline), and is identical for both arms.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "data" / "external" / "amemgym" / "data.json"
OUT = BASE / "data" / "external" / "amemgym_unified.json"

# Verbatim from src/amemgym/eval/overall.py::OVERALL_PROMPT (head), minus the
# JSON-format tail (see module docstring).
CHOICE_INSTRUCTION = (
    "Please select the most suitable answer for my current situation from the "
    "following options:\n(considering my current relevant preferences and "
    "state information)"
)
ANSWER_INSTRUCTION = "Answer with the number of the single best option."


def convert():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    stores = []
    for idx, item in enumerate(data):
        uid = f"amemgym-{idx:02d}"

        # ---- memory stream: user utterances only, globally date-sorted ----
        flat = []
        for pi, period in enumerate(item["periods"]):
            for sess in period["sessions"]:
                flat.append((sess["session_time"], pi, sess))
        flat.sort(key=lambda x: x[0])
        sessions = []
        for st, pi, sess in flat:
            # identical to overall.py's `query_with_time`
            turn = f"user: [Current Time: {st}]\n{sess['query']}"
            sessions.append({"date": st[:10], "turns": [turn]})

        # ---- questions: (period, qa) pairs ----
        questions = []
        for pi, period in enumerate(item["periods"]):
            cutoff = period["period_end"]
            for qi, qa in enumerate(item["qas"]):
                req = qa["required_info"]
                golden_state = [period["state"][k] for k in req]
                gold_idx = None
                for ci, ch in enumerate(qa["answer_choices"]):
                    if ch["state"] == golden_state:
                        gold_idx = ci
                        break
                assert gold_idx is not None, f"{uid} p{pi} q{qi}: no gold choice"
                choices_text = "\n".join(
                    "{}: {}".format(ci + 1, ch["answer"])
                    for ci, ch in enumerate(qa["answer_choices"]))
                question = (
                    f"(Today is {cutoff}.) {qa['query']}\n\n"
                    f"{CHOICE_INSTRUCTION}\n\n{choices_text}\n\n"
                    f"{ANSWER_INSTRUCTION}")
                gold = "{}: {}".format(
                    gold_idx + 1, qa["answer_choices"][gold_idx]["answer"])
                # how many times each required slot had already flipped by pi
                upd = period.get("update_cnts") or {}
                questions.append({
                    "qid": f"{uid}-p{pi:02d}q{qi}",
                    "question": question,
                    "gold": gold,
                    "dim": f"period{pi:02d}",
                    "cutoff": cutoff,
                    "meta": {
                        "persona_id": item["id"],
                        "period_index": pi,
                        "period_end": cutoff,
                        "qa_index": qi,
                        "required_info": req,
                        "golden_state": golden_state,
                        "gold_choice_1based": gold_idx + 1,
                        "n_choices": len(qa["answer_choices"]),
                        "choice_states": [c["state"] for c in qa["answer_choices"]],
                        "choice_types": [c.get("type") for c in qa["answer_choices"]],
                        "update_cnts_required": [int(upd.get(k, 0)) for k in req],
                        "updated_this_period": [
                            k in (period.get("updates") or {}) for k in req],
                    },
                })
        stores.append({"uid": uid, "sessions": sessions, "questions": questions})

    # ---------------- verification (all assertions, no silent pass) --------
    n_q = sum(len(s["questions"]) for s in stores)
    assert len(stores) == 20, len(stores)
    assert n_q == 2200, n_q
    qids = [q["qid"] for s in stores for q in s["questions"]]
    assert len(set(qids)) == len(qids), "duplicate qids"

    # (a) cutoff exactness: date<=period_end selects exactly periods 0..pi
    for store, item in zip(stores, data):
        flat = []
        for pi, period in enumerate(item["periods"]):
            for sess in period["sessions"]:
                flat.append((sess["session_time"][:10], pi))
        for pi, period in enumerate(item["periods"]):
            sel = {j for dt, j in flat if dt <= period["period_end"]}
            assert sel == set(range(pi + 1)), (store["uid"], pi, sorted(sel))

    # (b) off-policy soundness: gold recoverable from user utterances alone
    bad = 0
    for item in data:
        exposed_per_period = []
        for period in item["periods"]:
            dd = {}
            for sess in period["sessions"]:
                dd.update(sess.get("exposed_states") or {})
            exposed_per_period.append(dd)
        for pi, period in enumerate(item["periods"]):
            latest = {}
            for j in range(pi + 1):
                latest.update(exposed_per_period[j])
            for qa in item["qas"]:
                for k in qa["required_info"]:
                    if latest.get(k) != period["state"][k]:
                        bad += 1
    assert bad == 0, f"{bad} required state values not exposed by user side"

    n_sess = sum(len(s["sessions"]) for s in stores)
    chars = sum(len(t) for s in stores for ss in s["sessions"] for t in ss["turns"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(stores, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"amemgym: {len(stores)} stores, {n_sess} sessions, {n_q} questions, "
          f"{chars:,} store chars -> {OUT}")
    print("verified: cutoff exact for 220 (persona,period) cells; "
          "2200/2200 gold states recoverable from user utterances alone")
    return 0


if __name__ == "__main__":
    sys.exit(convert())
