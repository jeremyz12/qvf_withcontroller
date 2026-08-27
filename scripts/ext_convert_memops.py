# -*- coding: utf-8 -*-
"""Convert MemOps (arXiv:2607.12893) distractor-injected instances to the QVF unified store format.

Input : data/external/memops/generated_result/4-inject_evidence_with_distractors/*.json
        (403 self-contained instances; each = 50 conversation segments + ~8-12 probes)
Output: data/external/memops_unified.json
        [{"uid": "memops-<file-stem>",
          "sessions": [{"date": "", "turns": ["user: ...", "assistant: ...", ...]}, ...],
          "questions": [{"qid", "question", "gold", "dim", "meta": {...}}, ...]}]

Notes:
- MemOps carries NO timestamps anywhere (verified by key scan over raw JSON), so every
  session date is the empty string.
- Turn rendering mirrors the official harness (5-test_operation_metrics.py::dialogue_to_text):
  roles restricted to user/assistant, content stripped, prefixed "role: ".
- qid mirrors the official question_id: "<file-stem>_q<1-based-index-over-answer-list>".
- dim = instance-level operation_type (Remember/Update/Forget/Reflect/TrajectoryOps).
- meta keeps every field the official LLM judge (5.5-evaluate_operation_metrics.py)
  consumes: judge_rubric, gold_memory_state, diagnostic_checks, evaluation_setting,
  evaluation_type, evaluation_category, difficulty, question_pair_id, and the optional
  candidate_options / distractor_rationale / gold_reasoning_chain / gold_provenance /
  probe-type / trajectory fields when present.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC_DIR = BASE / "data" / "external" / "memops" / "generated_result" / "4-inject_evidence_with_distractors"
OUT_PATH = BASE / "data" / "external" / "memops_unified.json"

OPTIONAL_META_FIELDS = (
    "state_transition_probe_type",
    "application_probe_type",
    "candidate_options",
    "distractor_rationale",
    "gold_reasoning_chain",
    "trajectory_granularity",
    "gold_provenance",
)


def dialogue_to_turns(dialogue):
    """Mirror the official dialogue_to_text filtering, but keep turns as a list."""
    turns = []
    for message in dialogue:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            turns.append(f"{role}: {content.strip()}")
    return turns


def convert_instance(path):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    stem = path.stem
    sessions = []
    for conv in payload["conversations"]:
        turns = dialogue_to_turns(conv["dialogue"])
        assert turns, f"{stem}: empty session after filtering"
        sessions.append({"date": "", "turns": turns})  # MemOps has no timestamps at all

    questions = []
    for idx, spec in enumerate(payload["answer"], start=1):
        question = spec["question"].strip()
        gold = spec["expected_answer"].strip()
        assert question, f"{stem} q{idx}: empty question"
        assert gold, f"{stem} q{idx}: empty gold"
        meta = {
            "question_pair_id": spec.get("question_pair_id", ""),
            "evaluation_setting": spec.get("evaluation_setting", ""),
            "evaluation_type": spec.get("evaluation_type", ""),
            "evaluation_category": spec.get("evaluation_category", ""),
            "difficulty": spec.get("difficulty", ""),
            "gold_memory_state": spec.get("gold_memory_state", ""),
            "judge_rubric": spec.get("judge_rubric", {}),
            "diagnostic_checks": spec.get("diagnostic_checks", {}),
            "target_fact": payload.get("target_fact", ""),
        }
        for field in OPTIONAL_META_FIELDS:
            if field in spec:
                meta[field] = spec[field]
        questions.append(
            {
                "qid": f"{stem}_q{idx}",  # identical to official question_id
                "question": question,
                "gold": gold,
                "dim": payload["operation_type"],
                "meta": meta,
            }
        )

    return {"uid": f"memops-{stem}", "sessions": sessions, "questions": questions}


def main():
    files = sorted(SRC_DIR.glob("*.json"))
    if not files:
        print(f"ERROR: no source files under {SRC_DIR}", file=sys.stderr)
        return 1

    stores = [convert_instance(p) for p in files]

    # ---- verification ----
    n_q = sum(len(s["questions"]) for s in stores)
    uids = {s["uid"] for s in stores}
    assert len(uids) == len(stores), "duplicate uids"
    qids = [q["qid"] for s in stores for q in s["questions"]]
    assert len(set(qids)) == len(qids), "duplicate qids"
    per_store_chars = [sum(len(t) for sess in s["sessions"] for t in sess["turns"]) for s in stores]
    mean_chars = sum(per_store_chars) / len(stores)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(stores, f, ensure_ascii=False, indent=1)

    print(f"stores: {len(stores)}")
    print(f"questions: {n_q}")
    print(f"sessions/store: min={min(len(s['sessions']) for s in stores)} max={max(len(s['sessions']) for s in stores)}")
    print(f"turn-chars/store: min={min(per_store_chars)} mean={mean_chars:.0f} max={max(per_store_chars)}")
    dims = {}
    settings = {}
    for s in stores:
        for q in s["questions"]:
            dims[q["dim"]] = dims.get(q["dim"], 0) + 1
            settings[q["meta"]["evaluation_setting"]] = settings.get(q["meta"]["evaluation_setting"], 0) + 1
    print(f"dim counts: {dims}")
    print(f"evaluation_setting counts: {settings}")
    print(f"output: {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
