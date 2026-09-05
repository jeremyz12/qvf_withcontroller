# -*- coding: utf-8 -*-
"""批 52-A:harness 基线一 —— 读时从整份记忆抽状态表,再用同一账目版式与协议作答。

即"把 QVF 的建卡在读时、按题重做一遍":每题两次调用 —
  (1) 抽取:读者模型读整份 transcript(与 fullplain / smw 臂逐字同一渲染),按题目槽位抽出
      全部"本人开始持有该槽位某值"的记录(value / stated_date / 逐字原句 / 会话日期);
  (2) 作答:把记录按日期渲染成与 render_card_ledger 相同的三列账目,套 SMW_PROMPT 协议作答。
判官 qvf.judge.ClaudeJudge(与 lb_reader_arm_b36b 同)。产物每行记两次调用的 usage。

用法:
  PYTHONUTF8=1 python scripts/b52_readtime_harness.py --model claude-haiku-4-5 \
      --questions results/b35_questions_sample36.jsonl --out results/b52_readtime_haiku.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

sys.path.insert(0, r"D:\ZZL_cluade"); sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")
import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import SMW_PROMPT, parse_answer, render_transcript  # noqa: E402

ROOT = Path(r"D:\ZZL_cluade")
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}


class Row(BaseModel):
    value: str = Field(description="The state value the user declares holding (e.g. the employer, position, team or residence).")
    stated_date: str = Field(default="", description="Date the state began, YYYY, YYYY-MM or YYYY-MM-DD, taken from the sentence if it states one, otherwise the session header date.")
    source_span: str = Field(description="VERBATIM contiguous substring of the transcript that declares this state. Copy exactly.")


class Extraction(BaseModel):
    rows: List[Row] = Field(description="Every declaration, in transcript order. Empty if none.")


EXTRACT_SYSTEM = """You are building a dated state table from one user's conversation transcript.
Slot of interest: {slot}. Extract EVERY turn in which the user declares that they themselves
now hold / have started / were appointed to / joined / moved to a value of this slot.
Rules:
1. source_span must be a VERBATIM contiguous substring of the transcript.
2. stated_date: use the date the sentence states if any; otherwise the session header date of that turn.
3. Skip plans, nominations, applications, offers not taken up, hypotheticals, one-off tasks,
   other people's states, and mere re-mentions of an unchanged state.
4. One row per declaration; do not merge or de-duplicate; do not invent facts."""


def cost(model, tin, tout):
    pi, po = PRICES.get(model, (2.0, 10.0))
    return tin / 1e6 * pi + tout / 1e6 * po


def render_rows(rows: List[dict], slot: str) -> str:
    rows = sorted(rows, key=lambda r: r.get("stated_date") or "9999")
    lines = []
    for n, r in enumerate(rows, 1):
        d = r.get("stated_date") or "undated"
        span = (r.get("source_span") or "")[:120]
        lines.append(f'[entry {n}] {d} | {slot}: {r.get("value", "?")} — "{span}"')
    return "\n".join(lines) if lines else "(no dated state rows were found for this slot)"


def run_one(cli, judge, model, q, entry, max_tokens):
    slot = (entry.get("slot") or "").lower()
    transcript = render_transcript(entry.get("sessions", []))
    kw = {}
    if model.startswith("claude-haiku"):
        kw["temperature"] = 0.0
    if model.startswith("claude-sonnet"):
        kw["thinking"] = {"type": "disabled"}
    t0 = time.time()
    r1 = cli.messages.parse(model=model, max_tokens=4000,
                            system=[{"type": "text", "text": EXTRACT_SYSTEM.format(slot=slot)}],
                            messages=[{"role": "user", "content": "TRANSCRIPT:\n" + transcript}],
                            output_format=Extraction, **kw)
    rows = [x.model_dump() for x in (r1.parsed_output.rows if r1.parsed_output else [])]
    led = render_rows(rows, slot)
    user = SMW_PROMPT.format(question=q["question"], transcript=led)
    kw2 = {}
    if model.startswith("claude-haiku"):
        kw2["temperature"] = 0.0
    if model.startswith("claude-sonnet"):
        kw2["thinking"] = {"type": "disabled"}
    r2 = cli.messages.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": user}], **kw2)
    raw = "".join(b.text for b in r2.content if b.type == "text")
    pred, dev = parse_answer(raw)
    v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
    return {"question_id": q["qid"], "uid": q["uid"], "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred, "raw": raw[-1500:], "protocol_deviation": dev,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "extract_rows": len(rows), "extract_in": r1.usage.input_tokens, "extract_out": r1.usage.output_tokens,
            "reader_in": r2.usage.input_tokens, "reader_out": r2.usage.output_tokens,
            "usage_input_tokens": r1.usage.input_tokens + r2.usage.input_tokens,
            "usage_output_tokens": r1.usage.output_tokens + r2.usage.output_tokens,
            "usd": cost(model, r1.usage.input_tokens + r2.usage.input_tokens, r1.usage.output_tokens + r2.usage.output_tokens),
            "latency_s": time.time() - t0, "stop_reason": r2.stop_reason, "reader_model": model, "arm": "readtime_extract"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--questions", default="results/b35_questions_sample36.jsonl")
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=800, dest="max_tokens")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    qs = [json.loads(l) for l in open(ROOT / a.questions, encoding="utf-8") if l.strip()]
    ents = {e["uid"]: e for e in json.load(open(ROOT / a.data, encoding="utf-8"))}
    out = ROOT / a.out
    done = set()
    if out.exists():
        done = {json.loads(l)["question_id"] for l in open(out, encoding="utf-8") if l.strip()}
    cli = anthropic.Anthropic(); judge = ClaudeJudge()
    todo = [q for q in qs if q["qid"] not in done]
    print(f"{len(todo)} questions to run ({len(done)} done)", flush=True)
    spent = 0.0; correct = 0; n = 0
    with ThreadPoolExecutor(a.workers) as ex, open(out, "a", encoding="utf-8") as f:
        for rec in ex.map(lambda q: run_one(cli, judge, a.model, q, ents[q["uid"]], a.max_tokens), todo):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            spent += rec["usd"]; correct += bool(rec["judge_correct"]); n += 1
            print(f"[{rec['question_id']}] {rec['judge_correct']} rows={rec['extract_rows']} in={rec['usage_input_tokens']} out={rec['usage_output_tokens']} ${spent:.2f}", flush=True)
    print(f"DONE {a.model} readtime_extract: {correct}/{n} = {100*correct/max(1,n):.1f}% | ${spent:.2f}", flush=True)


if __name__ == "__main__":
    main()
