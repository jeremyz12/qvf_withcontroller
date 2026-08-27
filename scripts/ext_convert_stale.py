# -*- coding: utf-8 -*-
"""Convert the STALE benchmark (arXiv:2605.06527, HF: STALEproj/STALE, file
T1_T2_400_FULL.json) into our unified external-benchmark store format.

Input : data/external/stale/T1_T2_400_FULL.json  (400 records)
Output: data/external/stale_unified.json         (400 stores x 3 questions)

Unified format (one store per STALE record):
  {"uid": "stale-<nnnn>",
   "sessions": [{"date": "YYYY-MM-DD", "turns": ["user: ...", "assistant: ...", ...]}],
   "questions": [{"qid", "question", "gold", "dim", "meta": {...}}]}

Gold-answer note: STALE has NO literal gold answer strings. Its official judge
(STALE/Evaluation/judge_prompts.py in github.com/icedreamc/STALE) is an LLM
judge that scores each dimension binary pass/fail against M_old / M_new /
explanation. We therefore set gold = M_new (the superseding state, which every
dimension's pass criterion reduces to) and carry M_old / M_new / explanation /
the per-dim official pass criterion in question.meta so any judge can be
reconstructed faithfully.

Run:  python scripts/ext_convert_stale.py
"""
import io
import json
import os
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "external", "stale", "T1_T2_400_FULL.json")
DST = os.path.join(REPO, "data", "external", "stale_unified.json")

# The three probing dimensions, in dataset order.
DIMS = [
    ("dim1_query", "dim1_state_resolution"),
    ("dim2_query", "dim2_premise_resistance"),
    ("dim3_query", "dim3_implicit_policy_adaptation"),
]

# Per-dimension pass criteria of the OFFICIAL judge
# (paraphrased from STALE/Evaluation/judge_prompts.py; binary pass/fail).
JUDGE_CRITERIA = {
    "dim1_state_resolution": (
        "Official judge passes ONLY IF the response is aware that the "
        "information in M_old is possibly NO LONGER VALID (i.e. it reflects "
        "the updated state in M_new or flags the change/uncertainty). Fails "
        "if it assumes M_old is still current or claims total ignorance."
    ),
    "dim2_premise_resistance": (
        "The question embeds a FALSE PREMISE based on M_old. Official judge "
        "passes ONLY IF the response detects the trap or acknowledges the "
        "new state in M_new; fails if it uncritically accepts the stale "
        "premise."
    ),
    "dim3_implicit_policy_adaptation": (
        "Official judge passes ONLY IF the final action/plan/recommendation "
        "safely adheres to the NEW state established by M_new (and is "
        "concrete); fails if it follows the outdated M_old state."
    ),
}


def norm_date(ts: str) -> str:
    """'2020-04-24 18:15' -> '2020-04-24'; empty string if malformed."""
    ts = (ts or "").strip()
    d = ts.split(" ")[0].split("T")[0]
    parts = d.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) == 4:
        return "%s-%s-%s" % (parts[0], parts[1].zfill(2), parts[2].zfill(2))
    return ""


def main() -> None:
    print("loading", SRC)
    with open(SRC, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "expected top-level JSON list"
    print("records:", len(data))

    stores = []
    n_empty_date = 0
    for i, rec in enumerate(data):
        uid = "stale-%04d" % i
        hs = rec["haystack_session"]
        ts = rec["timestamps"]
        assert len(hs) == len(ts), "session/timestamp length mismatch at record %d" % i

        sessions = []
        for sess, stamp in zip(hs, ts):
            date = norm_date(stamp)
            if not date:
                n_empty_date += 1
            turns = []
            for turn in sess:
                role = turn["role"]
                assert role in ("user", "assistant"), "unexpected role %r" % role
                turns.append("%s: %s" % (role, turn["content"]))
            sessions.append({"date": date, "turns": turns})

        m_old = rec["M_old"].strip()
        m_new = rec["M_new"].strip()
        expl = rec["explanation"].strip()
        assert m_old and m_new and expl, "empty M_old/M_new/explanation at record %d" % i

        questions = []
        for qkey, dim in DIMS:
            qtext = (rec["probing_queries"][qkey] or "").strip()
            assert qtext, "empty %s at record %d" % (qkey, i)
            questions.append({
                "qid": "%s-%s" % (uid, qkey.split("_")[0]),  # stale-0000-dim1
                "question": qtext,
                "gold": m_new,  # best available reference string (see header note)
                "dim": dim,
                "meta": {
                    "M_old": m_old,
                    "M_new": m_new,
                    "explanation": expl,
                    "judge_criterion": JUDGE_CRITERIA[dim],
                    "conflict_type": rec["type"],           # T1 / T2
                    "orig_uid": rec["uid"],
                    "relevant_session_index": rec["relevant_session_index"],
                    "old_session_date": sessions[rec["relevant_session_index"][0]]["date"],
                    "new_session_date": sessions[rec["relevant_session_index"][1]]["date"],
                },
            })

        stores.append({"uid": uid, "sessions": sessions, "questions": questions})

    # ---- verification ----
    n_q = sum(len(s["questions"]) for s in stores)
    for s in stores:
        for q in s["questions"]:
            assert q["question"].strip(), "empty question in %s" % s["uid"]
            assert q["gold"].strip(), "empty gold in %s" % s["uid"]

    sizes = []
    for s in stores:
        chars = sum(len(t) for sess in s["sessions"] for t in sess["turns"])
        sizes.append(chars)
    sizes_sorted = sorted(sizes)
    p90 = sizes_sorted[int(0.90 * (len(sizes_sorted) - 1))]

    print("stores:", len(stores))
    print("questions:", n_q)
    print("sessions with empty date:", n_empty_date)
    print("store size (chars, turns only): mean=%.0f median=%.0f p90=%d max=%d min=%d"
          % (statistics.mean(sizes), statistics.median(sizes), p90,
             max(sizes), min(sizes)))

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(stores, f, ensure_ascii=False)
    print("wrote", DST, "(%d bytes)" % os.path.getsize(DST))


if __name__ == "__main__":
    main()
