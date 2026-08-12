# -*- coding: utf-8 -*-
"""修正框定版 QVF:流水线不动,三类读者的呈现框定统一改为对话誊录+日常助手,
裁决语义(预验证权威/不得拒答/矛盾取后并注明)逐条保留。"""
import argparse
import os
import sys

sys.path.insert(0, r"D:\ZZL_cluade")
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")

import qvf.engine_bridge as EB  # noqa: E402
import qvf.generator as G  # noqa: E402
import scripts.run_decisive_stale as rds  # noqa: E402

G.BASELINE_GENERATOR_SYSTEM_PROMPT = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)

EB.VALIDATED_CONTEXT_READER_PROMPT = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. These excerpts have "
    "been pre-validated by an upstream memory module: they reflect the "
    "user's CURRENT, up-to-date state relevant to this message (outdated "
    "information has already been removed), and any bracketed analysis notes "
    "among them are authoritative conclusions you should follow. Reply to "
    "the new message naturally and helpfully in 1-3 sentences. Treat the "
    "excerpts as reliable facts about the user; do not say you lack the "
    "information when an excerpt or note states it."
)

EB.CONFLICT_LATEST_KNOWN_READER_PROMPT = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (each dated), followed by "
    "the user's new message. The excerpts contain CONFLICTING claims about "
    "the state the message asks about, with no explicit update language. In "
    "personal-memory settings the later-dated claim usually reflects the "
    "current state: base your reply on the LATER claim, and add one brief "
    "clause noting it changed from the earlier state. Reply naturally in "
    "1-3 sentences; do not decline — the relevant facts are in front of you."
)


def _fmt(query, memories, query_date=None):
    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
    for m in memories:
        d = (m.metadata or {}).get("session_date") or "note"
        lines.append(f"[{d}] {m.content}")
    lines.append("")
    if query_date:
        lines.append(f"TODAY'S DATE: {query_date}")
        lines.append("")
    lines.append(f"USER'S NEW MESSAGE: {query}")
    return "\n".join(lines)


G.format_baseline_generator_input = _fmt

ap = argparse.ArgumentParser()
ap.add_argument("--benchmark", choices=["stale", "stale_chain"], required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--reader", default="claude-haiku-4-5")
ap.add_argument("--data", default=None)
ap.add_argument("--items", type=int, default=None)
ap.add_argument("--top-k", type=int, default=0, dest="top_k")
a = ap.parse_args()

if a.benchmark == "stale":
    argv = ["frq", "--data", a.data or r"D:\ZZL_cluade\data\stale_T1_T2_400_FULL.json",
            "--benchmark", "stale", "--items", str(a.items if a.items is not None else 50)]
else:
    argv = ["frq", "--data", a.data or r"D:\ZZL_cluade\data\stale_chain_full.json",
            "--benchmark", "stale_chain", "--items", "0"]
argv += ["--conditions", "minimal_rules_species2", "--out", a.out,
         "--reader", a.reader, "--resume"]
if a.top_k:
    argv += ["--top-k", str(a.top_k)]
sys.argv = argv
sys.exit(rds.main())
