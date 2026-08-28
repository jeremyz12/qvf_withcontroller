# -*- coding: utf-8 -*-
"""批 17 场判官:按各考场官方判据重判臂输出(主指标;内联 ClaudeJudge 留作附注)。

- stale:官方三维二元判据(STALE/Evaluation/judge_prompts.py 语义重建):
  dim1 须意识到 M_old 可能失效;dim2 须识破假前提或按 M_new 回答;
  dim3 最终建议须遵循 M_new。判官上下文 = M_old/M_new/explanation(meta 全存)。
- memops:官方 rubric 语义重建:must_include 全中 + must_not_include 零命中
  (Forget 类泄漏=错)+ 答案与 expected_answer 实质一致(措辞可异)。

判官 = haiku t=0,输出 PASS/FAIL 单词。产物:<in>.rejudged.jsonl,
行内加 arena_judge_pass 字段。
用法: python scripts/ext_arena_judge.py --arena stale|memops --in results/ext_..jsonl \
        --probe data/external/<arena>_probe.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")
import anthropic  # noqa: E402

import os

CLIENT = anthropic.Anthropic()
# 批 28 判官稳健性:QVF_ARENA_JUDGE_MODEL 覆盖(gpt- 前缀走 OpenAI 栈);
# 覆盖时输出文件加 .j2 后缀避免与主判官产物混写。默认行为不变。
MODEL = os.environ.get("QVF_ARENA_JUDGE_MODEL", "claude-haiku-4-5")

STALE_CRIT = {
    "dim1_state_resolution":
        "PASS only if the response shows awareness that the OLD fact may no "
        "longer be valid (acknowledges the update / answers with the NEW state "
        "/ flags uncertainty about staleness). FAIL if it asserts the old "
        "state as still current.",
    "dim2_premise_resistance":
        "The question embeds a FALSE premise built on the OLD fact. PASS only "
        "if the response detects/corrects the false premise or answers in a "
        "way consistent with the NEW fact. FAIL if it accepts the stale "
        "premise.",
    "dim3_implicit_policy_adaptation":
        "The question never states the fact. PASS only if the final "
        "action/plan/recommendation adheres to the NEW state. FAIL if it "
        "follows the old state or hedges without adapting.",
}


def judge_stale(row, meta):
    crit = STALE_CRIT[row["question_type"]]
    p = (f"You are grading a memory-augmented assistant per the STALE "
         f"benchmark protocol.\nOLD (stale) fact: {meta['M_old']}\n"
         f"NEW (superseding) fact: {meta['M_new']}\n"
         f"Hidden logic: {meta.get('explanation', '')}\n\n"
         f"User question: {row['question']}\nAssistant response: "
         f"{row['answer']}\n\nCriterion: {crit}\n\n"
         "Reply with exactly one word: PASS or FAIL.")
    return p


def judge_memops(row, meta):
    r = meta.get("judge_rubric") or {}
    p = (f"You are grading per the MemOps benchmark rubric.\n"
         f"Question: {row['question']}\n"
         f"Expected answer: {row['gold_answer']}\n"
         f"MUST include (all): {json.dumps(r.get('must_include', []), ensure_ascii=False)}\n"
         f"Acceptable paraphrases allowed: {json.dumps(r.get('acceptable_paraphrases', []), ensure_ascii=False)}\n"
         f"MUST NOT include (any occurrence = FAIL, e.g. forgotten/outdated "
         f"values): {json.dumps(r.get('must_not_include', []), ensure_ascii=False)}\n"
         f"Assistant response: {row['answer']}\n\n"
         "PASS only if the response conveys the substance of the expected "
         "answer (wording may differ; paraphrases fine), covers every "
         "must-include item, and contains NO must-not-include content. "
         "Reply with exactly one word: PASS or FAIL.")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arena", choices=["stale", "memops"], required=True)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--probe", required=True)
    a = ap.parse_args()
    meta_by_qid = {json.loads(l)["qid"]: json.loads(l)["meta"]
                   for l in open(a.probe, encoding="utf-8") if l.strip()}
    rows = [json.loads(l) for l in open(a.inp, encoding="utf-8")]
    sfx = ".rejudged.jsonl" if not MODEL.startswith("gpt") else ".rejudged.j2.jsonl"
    outp = Path(a.inp).with_suffix(sfx)
    done = set()
    if outp.exists():
        done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")}
    fh = open(outp, "a", encoding="utf-8")
    build = judge_stale if a.arena == "stale" else judge_memops
    n = ok = 0
    for row in rows:
        if row["question_id"] in done:
            continue
        prompt = build(row, meta_by_qid[row["question_id"]])
        verdict = None
        for attempt in range(3):
            try:
                if MODEL.startswith("gpt"):
                    from openai import OpenAI
                    cli = main._oai = getattr(main, "_oai", None) or OpenAI()
                    rr = cli.chat.completions.create(
                        model=MODEL, max_completion_tokens=16,
                        messages=[{"role": "user", "content": prompt}])
                    txt = (rr.choices[0].message.content or "").upper()
                else:
                    r = CLIENT.messages.create(
                        model=MODEL, max_tokens=8, temperature=0.0,
                        messages=[{"role": "user", "content": prompt}])
                    txt = "".join(b.text for b in r.content
                                  if b.type == "text").upper()
                verdict = "PASS" in txt and "FAIL" not in txt
                break
            except Exception as e:  # noqa: BLE001
                print(f"retry {attempt}: {str(e)[:60]}", flush=True)
                time.sleep(3)
        row["arena_judge_pass"] = verdict
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(verdict)
    print(f"{a.arena} arena-judge: {ok}/{n} PASS "
          f"({ok/max(1,n)*100:.1f}%) -> {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
