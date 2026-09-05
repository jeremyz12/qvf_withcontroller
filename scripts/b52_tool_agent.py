# -*- coding: utf-8 -*-
"""批 52-B:harness 基线二 —— 带工具的 agent 循环直接在原始记忆上作答。

工具(全部纯代码,零 LLM):
  list_sessions()               会话索引:s{i} 日期 + 首句
  search_memory(query)          大小写不敏感子串搜索,返回命中轮次(会话日期 + 全文,最多 12 条)
  read_session(index)           某会话全部轮次
  days_between(d1, d2)          两个日期(YYYY[-MM[-DD]])的天数差
模型最多 max_steps 轮工具调用,最后一行须为 "ANSWER: ...";判官与其他臂同(qvf.judge.ClaudeJudge)。

用法:
  PYTHONUTF8=1 python scripts/b52_tool_agent.py --model claude-haiku-4-5 \
      --questions results/b35_questions_sample36.jsonl --out results/b52_toolagent_haiku.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade"); sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")
import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import parse_answer  # noqa: E402

ROOT = Path(r"D:\ZZL_cluade")
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}

TOOLS = [
    {"name": "list_sessions", "description": "List all sessions of the user's memory with their dates and the first words of each.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_memory", "description": "Case-insensitive substring search over every turn of the memory. Returns up to 12 matching turns with session index and date.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "read_session", "description": "Return all turns of one session by its index (from list_sessions).", "input_schema": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}},
    {"name": "days_between", "description": "Number of days between two dates given as YYYY, YYYY-MM or YYYY-MM-DD (missing parts default to 01).", "input_schema": {"type": "object", "properties": {"d1": {"type": "string"}, "d2": {"type": "string"}}, "required": ["d1", "d2"]}},
]

SYSTEM = """You answer questions about ONE user's long conversation memory. You cannot see the memory directly;
use the tools to find the evidence. Typical questions ask how many times a state changed, how many distinct
values existed before a date, which value lasted longest, or the first and most recent values.
Plan: list the sessions, search for the slot's key words and their synonyms, read the sessions that matter,
build a dated list of the user's OWN declarations of that state (ignore plans, nominations, other people's
states and mere re-mentions), then compute the answer. Use days_between for tenure comparisons.
When done, write the dated list you relied on, then finish with one final line: ANSWER: <answer>"""


def parse_date(s):
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(s or ""))
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


class Memory:
    def __init__(self, entry):
        self.sessions = entry.get("sessions", [])

    def list_sessions(self):
        return "\n".join(f"s{i} {s.get('date','')}: {(s['turns'][0] if s.get('turns') else '')[:90]}" for i, s in enumerate(self.sessions))

    def search_memory(self, query):
        q = (query or "").lower(); hits = []
        for i, s in enumerate(self.sessions):
            for t in s.get("turns", []):
                if q and q in t.lower():
                    hits.append(f"[s{i} {s.get('date','')}] {t[:700]}")
                    if len(hits) >= 12:
                        return "\n".join(hits)
        return "\n".join(hits) if hits else "(no match)"

    def read_session(self, index):
        try:
            s = self.sessions[int(index)]
        except (IndexError, ValueError, TypeError):
            return "(no such session)"
        return f"session s{index} date {s.get('date','')}\n" + "\n".join(t[:1200] for t in s.get("turns", []))

    def days_between(self, d1, d2):
        a, b = parse_date(d1), parse_date(d2)
        return str(abs((b - a).days)) if a and b else "(unparseable date)"


def cost(model, tin, tout):
    pi, po = PRICES.get(model, (2.0, 10.0))
    return tin / 1e6 * pi + tout / 1e6 * po


def run_one(cli, judge, model, q, entry, max_steps, max_tokens):
    mem = Memory(entry); t0 = time.time()
    msgs = [{"role": "user", "content": q["question"]}]
    tin = tout = 0; steps = 0; raw = ""; stop = ""
    kw = {"temperature": 0.0} if model.startswith("claude-haiku") else {"thinking": {"type": "disabled"}}
    while steps <= max_steps:
        r = cli.messages.create(model=model, max_tokens=max_tokens, system=SYSTEM, tools=TOOLS, messages=msgs, **kw)
        tin += r.usage.input_tokens; tout += r.usage.output_tokens; stop = r.stop_reason
        text = "".join(b.text for b in r.content if b.type == "text")
        uses = [b for b in r.content if b.type == "tool_use"]
        if not uses or steps == max_steps:
            raw = text; break
        msgs.append({"role": "assistant", "content": r.content})
        results = []
        for u in uses:
            fn = getattr(mem, u.name, None)
            try:
                out = fn(**(u.input or {})) if fn else "(unknown tool)"
            except Exception as e:  # noqa: BLE001
                out = f"(tool error: {type(e).__name__})"
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": str(out)[:6000]})
        msgs.append({"role": "user", "content": results})
        steps += 1
    if steps > max_steps and not raw:
        # 强制收尾:不再给工具,要求直接作答
        r = cli.messages.create(model=model, max_tokens=max_tokens, system=SYSTEM + "\nNo more tools are available. Answer now.", messages=msgs + [{"role": "user", "content": "Give your final answer now, ending with ANSWER: ..."}], **kw)
        tin += r.usage.input_tokens; tout += r.usage.output_tokens; raw = "".join(b.text for b in r.content if b.type == "text"); stop = r.stop_reason
    pred, dev = parse_answer(raw)
    v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
    return {"question_id": q["qid"], "uid": q["uid"], "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred, "raw": raw[-1500:], "protocol_deviation": dev,
            "judge_correct": v.correct, "judge_reason": v.reason, "tool_steps": steps,
            "usage_input_tokens": tin, "usage_output_tokens": tout, "usd": cost(model, tin, tout),
            "latency_s": time.time() - t0, "stop_reason": stop, "reader_model": model, "arm": "tool_agent"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--questions", default="results/b35_questions_sample36.jsonl")
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-steps", type=int, default=10, dest="max_steps")
    ap.add_argument("--max-tokens", type=int, default=1500, dest="max_tokens")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    qs = [json.loads(l) for l in open(ROOT / a.questions, encoding="utf-8") if l.strip()]
    ents = {e["uid"]: e for e in json.load(open(ROOT / a.data, encoding="utf-8"))}
    out = ROOT / a.out
    done = {json.loads(l)["question_id"] for l in open(out, encoding="utf-8") if l.strip()} if out.exists() else set()
    cli = anthropic.Anthropic(); judge = ClaudeJudge()
    todo = [q for q in qs if q["qid"] not in done]
    print(f"{len(todo)} questions to run ({len(done)} done)", flush=True)
    spent = 0.0; correct = 0; n = 0
    with ThreadPoolExecutor(a.workers) as ex, open(out, "a", encoding="utf-8") as f:
        for rec in ex.map(lambda q: run_one(cli, judge, a.model, q, ents[q["uid"]], a.max_steps, a.max_tokens), todo):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            spent += rec["usd"]; correct += bool(rec["judge_correct"]); n += 1
            print(f"[{rec['question_id']}] {rec['judge_correct']} steps={rec['tool_steps']} in={rec['usage_input_tokens']} out={rec['usage_output_tokens']} ${spent:.2f}", flush=True)
    print(f"DONE {a.model} tool_agent: {correct}/{n} = {100*correct/max(1,n):.1f}% | ${spent:.2f}", flush=True)


if __name__ == "__main__":
    main()
