"""T2 (终裁条件⑥): 判官侧 token 成本实测.

Re-runs the SAME frozen judge code (qvf.judge.ClaudeJudge, claude-opus-5)
against a stratified sample of already-archived, already-judged rows drawn
from several distinct experiment lines (WikiState v4.2 domains, LME-TR/KU,
LoCoMo, S5 complex-query compiled arm, S8 completeness suite). This is
PURELY a cost/consistency measurement:

- It does NOT overwrite any archived result file or archived verdict.
- It writes fresh verdicts + real per-call usage to a NEW file
  (results/judge_cost_measured_sample_20260816.jsonl).
- It also reports the agreement rate between the fresh verdict and the
  archived verdict, as a free byproduct (judge stability signal).

Sampling is deterministic (fixed seed) and stratified by question_type
within each source file so the sample spans different question types and
(via random draw, not filtered) different answer lengths.
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.judge import ClaudeJudge  # noqa: E402

SEED = 20260816

# (source file, category label, target sample size)
SOURCES = [
    ("results/wtqvf3_v42_P39.jsonl", "wikistate_P39_v42", 15),
    ("results/wtqvf3_v42_P54w2.jsonl", "wikistate_P54w2_v42", 15),
    ("results/wtqvf3_v42_confirm.jsonl", "confirm_v42", 15),
    ("results/wtqvf3_v42_chain.jsonl", "chain_v42", 15),
    ("results/final_lme_tr.jsonl", "lme_tr", 15),
    ("results/final_lme_ku.jsonl", "lme_ku", 15),
    ("results/final_locomo.jsonl", "locomo", 15),
    ("results/wsc_s5_p39_arm.jsonl", "s5_p39_complex_arm", 20),  # fills b1's known judge-usage gap
    ("results/wsc_s5_test_v42.jsonl", "s5_314_complex", 15),
    ("results/wsc_s8_direct_test.jsonl", "s8_direct", 5),
    ("results/wsc_s8_algebra_test.jsonl", "s8_algebra", 5),
    ("results/wsc_s8_flat_test.jsonl", "s8_flat", 5),
]

OUT_PATH = Path("results/judge_cost_measured_sample_20260816.jsonl")


def load_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        print(f"MISSING: {path}")
        return []
    with p.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def stratified_sample(rows: list[dict], n: int, rng: random.Random) -> list[dict]:
    usable = [r for r in rows if r.get("gold_answer") is not None and r.get("question") and "answer" in r]
    if len(usable) <= n:
        return usable
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in usable:
        by_type[str(r.get("question_type"))].append(r)
    types = sorted(by_type)
    per_type = max(1, n // len(types))
    picked: list[dict] = []
    for t in types:
        bucket = by_type[t]
        rng.shuffle(bucket)
        picked.extend(bucket[:per_type])
    if len(picked) < n:
        remaining = [r for r in usable if r not in picked]
        rng.shuffle(remaining)
        picked.extend(remaining[: n - len(picked)])
    rng.shuffle(picked)
    return picked[:n]


def main() -> int:
    rng = random.Random(SEED)
    judge = ClaudeJudge()  # frozen code, unmodified; DEFAULT_JUDGE_MODEL=claude-opus-5

    sample: list[tuple[str, dict]] = []
    for path, label, n in SOURCES:
        rows = load_rows(path)
        picked = stratified_sample(rows, n, rng)
        print(f"{label}: pool={len(rows)} usable_pool={sum(1 for r in rows if r.get('gold_answer') is not None)} picked={len(picked)}")
        for r in picked:
            sample.append((label, r))

    print(f"\nTOTAL sampled rows: {len(sample)}\n")

    out_rows = []
    agree = 0
    disagree = 0
    for i, (label, r) in enumerate(sample):
        question = r.get("question", "")
        gold = str(r.get("gold_answer"))
        answer = r.get("answer", "")
        qtype = r.get("question_type")
        qid = str(r.get("question_id", ""))
        is_abs = bool(r.get("is_abstention", False)) or qid.endswith("_abs")

        v = judge.judge(question, gold, answer, qtype, is_abs)
        old_correct = r.get("judge_correct")
        new_correct = v.correct
        agreed = old_correct == new_correct
        agree += int(agreed)
        disagree += int(not agreed)

        out_rows.append(
            {
                "source": label,
                "question_id": qid,
                "question_type": qtype,
                "is_abstention": is_abs,
                "answer_chars": len(str(answer)),
                "gold_chars": len(gold),
                "archived_judge_correct": old_correct,
                "rerun_judge_correct": new_correct,
                "agree": agreed,
                "rerun_judge_reason": v.reason,
                "archived_judge_reason": r.get("judge_reason"),
                "usage_input_tokens": v.usage_input_tokens,
                "usage_output_tokens": v.usage_output_tokens,
            }
        )
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(sample)} done, running usage={judge.total_usage}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as fout:
        for row in out_rows:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")

    u = judge.total_usage
    calls = u["calls"] or 1
    cost = (u["input_tokens"] * 5 + u["output_tokens"] * 25) / 1_000_000
    print("\n=== REAL judge.total_usage (claude-opus-5, $5/$25 per Mtok input/output) ===")
    print(json.dumps(u, ensure_ascii=False))
    print(f"cost_usd: {cost:.4f}")
    print(f"avg_input_tokens_per_call: {u['input_tokens'] / calls:.2f}")
    print(f"avg_output_tokens_per_call: {u['output_tokens'] / calls:.2f}")
    print(f"avg_cost_per_call_usd: {cost / calls:.6f}")
    print(f"\nagreement: {agree}/{agree + disagree} = {agree / (agree + disagree):.4f}")
    print(f"disagreements: {disagree}")
    print(f"\nwrote {len(out_rows)} rows to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
