# -*- coding: utf-8 -*-
"""W1 框定修正臂:记忆=对话誊录 + 日常助手口吻 + 无弃答条款,单遍直读。

与冻结版直读唯一差异 = 呈现框定;检索、读者模型、判官逐位一致。
量化"JSON 板砖 + 弃答条款"两个框定嫌疑人的合计影响。"""
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

ap = argparse.ArgumentParser()
ap.add_argument("--benchmark", choices=["stale", "stale_chain"], required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--reader", default="claude-haiku-4-5")
ap.add_argument("--data", default=None)
ap.add_argument("--items", type=int, default=None)
a = ap.parse_args()

if a.benchmark == "stale":
    argv = ["fr", "--data", a.data or r"D:\ZZL_cluade\data\stale_T1_T2_400_FULL.json",
            "--benchmark", "stale", "--items", str(a.items if a.items is not None else 50)]
else:
    argv = ["fr", "--data", a.data or r"D:\ZZL_cluade\data\stale_chain_full.json",
            "--benchmark", "stale_chain", "--items", "0"]
argv += ["--conditions", "dense_direct", "--out", a.out,
         "--reader", a.reader, "--resume"]
sys.argv = argv
sys.exit(rds.main())
