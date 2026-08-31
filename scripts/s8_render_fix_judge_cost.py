# -*- coding: utf-8 -*-
"""渲染修复阶段(QVF_RENDER_ANCHORS)判官侧成本实测。

沿用 scripts/judge_cost_measure_20260816.py 的方法论:对已产出的答案行,
用同一份冻结判官代码(qvf.judge.ClaudeJudge,claude-opus-5)重新打分一遍,
读 judge.total_usage 得真实 token 数与 $5/$25 每百万 token 定价下的成本。

不覆盖任何已归档结果文件,只读输入 jsonl(--in,可传多个,通常是本轮
flat / algebra_off / algebra_on 三个跑批产物),按 question_id+source 写一份
新的核对文件(--out),并在末尾打印总成本。

用法:
  python -m scripts.s8_render_fix_judge_cost \
      --in results/s8_heldout_flat_p2.jsonl:flat \
           results/s8_heldout_algebra_off_p2.jsonl:algebra_off \
           results/s8_heldout_algebra_on_p2.jsonl:algebra_on \
      --out results/s8_render_fix_judge_recheck_p2.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qvf.judge import ClaudeJudge  # noqa: E402


def load_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        print(f"MISSING: {path}")
        return []
    with p.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True,
                     help="path:label pairs, colon-separated")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    judge = ClaudeJudge()  # frozen code, unmodified; DEFAULT_JUDGE_MODEL=claude-opus-5

    out_rows = []
    agree = 0
    disagree = 0
    n_by_label = {}
    for spec in a.inputs:
        path, _, label = spec.partition(":")
        label = label or path
        rows = load_rows(path)
        usable = [r for r in rows if r.get("gold_answer") is not None
                  and r.get("question") and "answer" in r]
        n_by_label[label] = len(usable)
        print(f"{label}: pool={len(rows)} usable={len(usable)}")
        for r in usable:
            question = r.get("question", "")
            gold = str(r.get("gold_answer"))
            answer = r.get("answer", "")
            qtype = r.get("question_type")
            qid = str(r.get("question_id", ""))

            v = judge.judge(question, gold, answer, qtype)
            old_correct = r.get("judge_correct")
            new_correct = v.correct
            agreed = old_correct == new_correct
            agree += int(agreed)
            disagree += int(not agreed)

            out_rows.append({
                "source": label, "question_id": qid, "question_type": qtype,
                "combo": r.get("combo"),
                "archived_judge_correct": old_correct,
                "rerun_judge_correct": new_correct,
                "agree": agreed,
                "rerun_judge_reason": v.reason,
                "usage_input_tokens": v.usage_input_tokens,
                "usage_output_tokens": v.usage_output_tokens,
            })

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fout:
        for row in out_rows:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")

    u = judge.total_usage
    calls = u["calls"] or 1
    cost = (u["input_tokens"] * 5 + u["output_tokens"] * 25) / 1_000_000
    print("\n=== REAL judge.total_usage (claude-opus-5, $5/$25 per Mtok in/out) ===")
    print(json.dumps(u, ensure_ascii=False))
    print(f"cost_usd: {cost:.4f}")
    print(f"avg_cost_per_call_usd: {cost / calls:.6f}")
    print(f"\nagreement vs archived (sanity, not the metric of interest): "
          f"{agree}/{agree + disagree} = {agree / max(1, agree + disagree):.4f}")
    print(f"n_by_label: {json.dumps(n_by_label, ensure_ascii=False)}")
    print(f"\nwrote {len(out_rows)} rows to {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
