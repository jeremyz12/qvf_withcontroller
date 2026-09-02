# -*- coding: utf-8 -*-
"""33-H3b:"Letta 式文件系统 agent"平凡强基线(docs/related_work.md:448 的欠账)。

设计(Letta 博客 "Is a Filesystem All You Need?" 的复刻,非其代码):
  * 写侧零 LLM、零嵌入:把每条目的会话按时间顺序落成真实文件
    results/letta_fs_corpus/<uid>/s000__<date>.md,内容 = 与 repro_batch4
    `sess_text` 逐字相同的会话渲染((session date: X) + 前 6 轮 × 400 字)。
    ——与 60 题标定场其余 16 个考生同一语料切法,保证同台可比。
  * 读侧:claude-haiku-4-5(与全场读者同款,temperature 0)带三个文件系统
    工具自主检索:list_files / grep_files / read_file,最多 MAX_ROUNDS 轮
    工具调用,末轮强制作答。
  * 判官:qvf.judge.ClaudeJudge(全场同一冻结判官)。

题源与库源:与 repro_batch2.sample_stores() 完全一致(15 库 × 4 题 = 60 题)。

用法:
  python scripts/letta_fs_agent_baseline.py --out results/wsc_s5_lettafs.jsonl
  python scripts/letta_fs_agent_baseline.py --limit-stores 1 --out results/smoke.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import anthropic  # noqa: E402

from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch2 import VOLS, READER_MODEL, sample_stores  # noqa: E402

CORPUS_ROOT = ROOT / "results" / "letta_fs_corpus"
MAX_ROUNDS = 12
MAX_GREP_HITS = 60

AGENT_SYS = (
    "You are the user's personal AI assistant. Your long-term memory of this "
    "user is stored as a FILESYSTEM: one file per past chat session, named "
    "s<NNN>__<session date>.md and listed in chronological order. You have no "
    "other memory — you must use the tools to look things up before you "
    "answer.\n\n"
    "Tools: list_files() shows every session file; grep_files(pattern) runs a "
    "case-insensitive regular-expression search across all files and returns "
    "matching lines with their file names; read_file(name) returns one whole "
    "session file.\n\n"
    "Work by searching and reading until you have the evidence you need, then "
    "answer the user's message directly in 1-3 sentences. Pay attention to "
    "session dates when the question is about ordering, counting or timing."
)

TOOLS = [
    {
        "name": "list_files",
        "description": "List every session file in the user's memory "
                       "filesystem, oldest first, with its byte size.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "grep_files",
        "description": "Case-insensitive regular-expression search across all "
                       "session files. Returns up to 60 matching lines as "
                       "'<file>:<line no>: <line>'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string",
                            "description": "Python regular expression."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": "Read one whole session file by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "File name as shown by list_files."},
            },
            "required": ["name"],
        },
    },
]


# ── 语料落盘(写侧:零 LLM、零嵌入)────────────────────────────
def sess_text(s: dict) -> str:
    """与 scripts/repro_batch4.sess_text 逐字相同。"""
    turns = s.get("turns", [])[:6]
    return f"(session date: {s.get('date','undated')})\n" + \
        "\n".join(str(t)[:400] for t in turns)


def materialize(uid: str, sessions: list) -> Path:
    d = CORPUS_ROOT / uid
    d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(sessions):
        date = str(s.get("date", "undated"))
        p = d / f"s{i:03d}__{date}.md"
        p.write_text(sess_text(s), encoding="utf-8")
    return d


# ── 文件系统工具 ────────────────────────────────────────────
class FsTools:
    def __init__(self, d: Path):
        self.dir = d
        self.files = sorted(p.name for p in d.glob("*.md"))
        self.reads = 0
        self.greps = 0
        self.lists = 0

    def list_files(self) -> str:
        self.lists += 1
        return "\n".join(
            f"{n}  ({(self.dir / n).stat().st_size} bytes)" for n in self.files
        )

    def grep_files(self, pattern: str) -> str:
        self.greps += 1
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"invalid regular expression: {e}"
        hits = []
        for n in self.files:
            for ln, line in enumerate(
                    (self.dir / n).read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{n}:{ln}: {line.strip()[:300]}")
                    if len(hits) >= MAX_GREP_HITS:
                        return "\n".join(hits) + \
                            f"\n[truncated at {MAX_GREP_HITS} hits]"
        return "\n".join(hits) if hits else "(no matches)"

    def read_file(self, name: str) -> str:
        self.reads += 1
        p = self.dir / Path(name).name
        if not p.exists():
            return f"no such file: {name}. Use list_files() to see the names."
        return p.read_text(encoding="utf-8")

    def call(self, tool: str, args: dict) -> str:
        if tool == "list_files":
            return self.list_files()
        if tool == "grep_files":
            return self.grep_files(str(args.get("pattern", "")))
        if tool == "read_file":
            return self.read_file(str(args.get("name", "")))
        return f"unknown tool {tool}"


# ── agent 回合 ─────────────────────────────────────────────
def run_agent(client, tools: FsTools, question: str) -> dict:
    msgs = [{"role": "user", "content": question}]
    tin = tout = 0
    rounds = 0
    answer = ""
    for rounds in range(1, MAX_ROUNDS + 1):
        last = rounds == MAX_ROUNDS
        kw = dict(model=READER_MODEL, max_tokens=700, temperature=0.0,
                  system=AGENT_SYS, messages=msgs)
        if not last:
            kw["tools"] = TOOLS
        r = None
        for attempt in range(4):
            try:
                r = client.messages.create(**kw)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  api retry {attempt}: {type(e).__name__}: "
                      f"{str(e)[:100]}", flush=True)
                time.sleep(3 * (attempt + 1))
        if r is None:
            break
        tin += r.usage.input_tokens
        tout += r.usage.output_tokens
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        if text:
            answer = text
        if r.stop_reason != "tool_use":
            break
        msgs.append({"role": "assistant", "content": [b.model_dump()
                                                      for b in r.content]})
        results = []
        for b in r.content:
            if b.type == "tool_use":
                out = tools.call(b.name, b.input or {})
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": out[:20000]})
        msgs.append({"role": "user", "content": results})
    return {"answer": answer, "usage_input_tokens": tin,
            "usage_output_tokens": tout, "agent_rounds": rounds,
            "tool_list": tools.lists, "tool_grep": tools.greps,
            "tool_read": tools.reads}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/wsc_s5_lettafs.jsonl")
    ap.add_argument("--limit-stores", type=int, default=0)
    a = ap.parse_args()

    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    if a.limit_stores:
        picked = picked[:a.limit_stores]

    out_p = ROOT / a.out
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"]
                for l in open(out_p, encoding="utf-8") if l.strip()}
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    fh = open(out_p, "a", encoding="utf-8")
    for uid in picked:
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            continue
        t0 = time.time()
        sessions = sorted(entries[uid].get("sessions", []),
                          key=lambda s: s.get("date", ""))
        d = materialize(uid, sessions)
        ingest_s = time.time() - t0
        for q in qs:
            t1 = time.time()
            tools = FsTools(d)
            res = run_agent(client, tools, q["question"])
            v = judge.judge(q["question"], str(q["gold"]), res["answer"],
                            q["qtype"])
            row = {"question_id": q["qid"], "mode": "lettafs", "uid": uid,
                   "question_type": q["qtype"], "question": q["question"],
                   "gold_answer": q["gold"], "answer": res["answer"],
                   "memories_n": len(tools.files),
                   "judge_correct": v.correct, "judge_reason": v.reason,
                   "ingest_seconds": round(ingest_s, 3),
                   "latency_s": round(time.time() - t1, 2)}
            row.update({k: res[k] for k in
                        ("usage_input_tokens", "usage_output_tokens",
                         "agent_rounds", "tool_list", "tool_grep",
                         "tool_read")})
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{q['qid']}] {'OK ' if v.correct else 'ERR'} "
                  f"rounds={res['agent_rounds']} "
                  f"tok={res['usage_input_tokens']}/"
                  f"{res['usage_output_tokens']} "
                  f"{time.time() - t1:.1f}s", flush=True)
    fh.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
