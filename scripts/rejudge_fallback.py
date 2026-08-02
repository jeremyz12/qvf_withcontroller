"""Re-judge rows whose judge degraded to the containment heuristic.

During the 2026-08-02 credit outage, ClaudeJudge fell back to its string
containment heuristic for some rows (judge_reason starts with 'FALLBACK
containment'). Those verdicts use a different protocol than the rest of the
file. This script re-runs the real judge on exactly those rows and rewrites
each file in place (pre-patch originals live in results/backup_pre_patch/).

is_abstention is recomputed from the question_id (the runner stores a
hardcoded False): LongMemEval abstention questions end with '_abs'.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.judge import ClaudeJudge  # noqa: E402

FILES = [
    "heldout_stale_ctx16k",
    "lme_ku_ctx16k",
    "lme_tr_ctx16k",
    "locomo_temporal_ctx16k",
    "memconflict_ctx16k",
]


def main() -> int:
    judge = ClaudeJudge()
    total = 0
    for name in FILES:
        path = Path("results") / f"{name}.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.open(encoding="utf-8")]
        n = 0
        for r in rows:
            if not str(r.get("judge_reason", "")).startswith("FALLBACK containment"):
                continue
            is_abs = str(r.get("question_id", "")).endswith("_abs")
            try:
                v = judge.judge(
                    r.get("question", ""),
                    r.get("gold_answer", ""),
                    r.get("answer", ""),
                    r.get("question_type"),
                    is_abs,
                )
            except Exception as exc:  # noqa: BLE001 — keep fallback verdict
                print(f"{name}: rejudge failed for {r.get('question_id')}: {exc}")
                continue
            if str(v.reason or "").startswith("FALLBACK containment"):
                # Judge degraded again — leave the row flagged for a later pass.
                continue
            r["judge_correct"] = v.correct
            r["judge_reason"] = v.reason
            r["rejudged"] = True
            n += 1
        with path.open("w", encoding="utf-8") as fout:
            for r in rows:
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
        total += n
        print(f"{name}: rejudged {n}")
    print(f"total rejudged: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
