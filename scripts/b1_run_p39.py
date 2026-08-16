# -*- coding: utf-8 -*-
"""B1 driver: run the (already-frozen) complex_query_arm and wsc_direct_arm
runners on the newly-unblocked P39 S5 question set, without editing either
frozen script. Also monkeypatches qvf.judge.ClaudeJudge.judge to accumulate
opus-side token usage (neither runner prints judge.total_usage itself), so
the run's actual judge-side cost can be reported per the standing "judge
token/cost must be read out and reported" discipline.

This file is new (not one of the four frozen scripts: qvf_router.py,
wt_qvf_prototype.py, complex_query_arm.py, qvf_algebra.py) so it is free to
import and drive them; it makes zero edits to their source.

IMPORTANT — run each arm as its own OS process (never both in one Python
process): complex_query_arm.py imports scripts.wt_qvf_prototype at module
level, and wt_qvf_prototype does `os.environ.setdefault("QVF_EMBED_BACKEND",
"openai")` on import (documented in wsc_direct_arm.py's own docstring as the
exact reason it copies rather than imports complex_query_arm's helpers).
Importing both arms in one process would silently flip wsc_direct_arm's
retrieval backend from its standalone default (ollama, local, $0) to openai
— a methodology drift from how `python scripts/wsc_direct_arm.py ...` runs
on its own. This script therefore only ever imports ONE arm module per
invocation, selected by the first CLI arg, and the caller (Bash) runs the
two arms as two separate `python scripts/b1_run_p39.py <arm> <mode>` calls.

Usage:
  python scripts/b1_run_p39.py complex smoke   # first 8 P39 questions, complex arm
  python scripts/b1_run_p39.py direct  smoke   # first 8 P39 questions, direct arm
  python scripts/b1_run_p39.py complex full    # full 104-question P39 batch
  python scripts/b1_run_p39.py direct  full
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same env the original v42 S5 run used: keyed card override only, all
# open-slot/fail-closed/algebra flags left at their default-off value so
# this run is code- and flag-identical to the archived 314-question run.
os.environ.setdefault("QVF_CARDS_KEYED", "results/wt_cards_v42")

import qvf.judge as qjudge  # noqa: E402

_GLOBAL_USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
_orig_judge_method = qjudge.ClaudeJudge.judge


def _tracked_judge(self, *a, **kw):
    before = dict(self.total_usage)
    result = _orig_judge_method(self, *a, **kw)
    for k in _GLOBAL_USAGE:
        _GLOBAL_USAGE[k] += self.total_usage[k] - before[k]
    return result


qjudge.ClaudeJudge.judge = _tracked_judge

DATA = ["data/wikistate_full_P39_ext.json"]
QUESTIONS_FULL = "results/wsc_s5_p39.jsonl"


def _smoke_questions_path() -> str:
    """First 8 rows of the full P39 question file, written once."""
    out = "results/wsc_s5_p39_smoke.jsonl"
    if not Path(out).exists():
        rows = [json.loads(l) for l in open(QUESTIONS_FULL, encoding="utf-8")]
        with open(out, "w", encoding="utf-8") as fh:
            for r in rows[:8]:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def _report_usage():
    print("\n=== judge (opus) usage this process ===")
    print(json.dumps(_GLOBAL_USAGE, ensure_ascii=False))
    # claude-opus-5 pricing per qvf/config.py DEFAULT_JUDGE_MODEL: $5/$25 per
    # Mtok (input/output), per claude-api skill's cached pricing table.
    cost = (_GLOBAL_USAGE["input_tokens"] * 5
            + _GLOBAL_USAGE["output_tokens"] * 25) / 1_000_000
    print(f"judge cost estimate (claude-opus-5 $5/$25 per Mtok): ${cost:.4f}")


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: b1_run_p39.py <complex|direct> <smoke|full>")
    arm, mode = sys.argv[1], sys.argv[2]
    if mode == "smoke":
        q = _smoke_questions_path()
        arm_out = "results/wsc_s5_p39_arm_smoke.jsonl"
        direct_out = "results/wsc_s5_p39_direct_smoke.jsonl"
    elif mode == "full":
        q = QUESTIONS_FULL
        arm_out = "results/wsc_s5_p39_arm.jsonl"
        direct_out = "results/wsc_s5_p39_direct.jsonl"
    else:
        raise SystemExit(f"unknown mode {mode!r}, use smoke|full")

    if arm == "complex":
        from scripts import complex_query_arm
        print(f"=== complex_query_arm ({mode}) QVF_CARDS_KEYED="
              f"{os.environ.get('QVF_CARDS_KEYED')} ===")
        complex_query_arm.run(DATA, q, arm_out, None, True)
    elif arm == "direct":
        from scripts import wsc_direct_arm
        print(f"=== wsc_direct_arm ({mode}) embed backend="
              f"{os.environ.get('QVF_EMBED_BACKEND', 'ollama (default)')} ===")
        wsc_direct_arm.run(DATA, q, direct_out, None, True)
    else:
        raise SystemExit(f"unknown arm {arm!r}, use complex|direct")

    _report_usage()


if __name__ == "__main__":
    main()
