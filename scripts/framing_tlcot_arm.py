# -*- coding: utf-8 -*-
"""修正框定 + 政策提示臂:对话誊录渲染 × timeline-CoT 指令。

与 framing_arm 同一修正框定,叠加政策指令 —— 量出修正协议下提示的真实净值。"""
import argparse
import os
import sys

sys.path.insert(0, r"D:\ZZL_cluade")
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")

import qvf.generator as G  # noqa: E402
import scripts.run_decisive_stale as rds  # noqa: E402

G.BASELINE_GENERATOR_SYSTEM_PROMPT = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)


def _fmt(query, memories, query_date=None):
    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
    for m in memories:
        d = (m.metadata or {}).get("session_date") or "undated"
        lines.append(f"[{d}] {m.content}")
    lines.append("")
    if query_date:
        lines.append(f"TODAY'S DATE: {query_date}")
        lines.append("")
    lines.append(f"USER'S NEW MESSAGE: {query}")
    return "\n".join(lines)


G.format_baseline_generator_input = _fmt

rds._WARN_INSTRUCTION = (
    "\n\n[Instruction: Before answering, reconstruct (silently) a dated "
    "timeline of every attribute the question touches: list each state with "
    "its start date in chronological order, and note which states have been "
    "superseded by later ones. Then answer STRICTLY from that timeline: for "
    "current-state questions use the latest state; for questions about a "
    "specific past date use the state that was valid on that date; for "
    "history/trajectory questions give the full ordered evolution. If the "
    "question presupposes a state your timeline shows as superseded, correct "
    "the premise before helping.]"
)

ap = argparse.ArgumentParser()
ap.add_argument("--benchmark", choices=["stale", "stale_chain"], required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--reader", default="claude-haiku-4-5")
ap.add_argument("--data", default=None)
ap.add_argument("--qid-file", default=None, dest="qid_file",
                help="限定题号文件(逐行 question_id;透传 run_decisive_stale"
                " --qid-file,用于只为路由到 prompt 臂的题产行)")
a = ap.parse_args()

if a.benchmark == "stale":
    argv = ["frt", "--data", a.data or r"D:\ZZL_cluade\data\stale_T1_T2_400_FULL.json",
            "--benchmark", "stale", "--items", "50"]
else:
    argv = ["frt", "--data", a.data or r"D:\ZZL_cluade\data\stale_chain_full.json",
            "--benchmark", "stale_chain", "--items", "0"]
argv += ["--conditions", "warned_direct", "--out", a.out,
         "--reader", a.reader, "--resume"]
if a.qid_file:
    argv += ["--qid-file", a.qid_file]
sys.argv = argv
sys.exit(rds.main())
