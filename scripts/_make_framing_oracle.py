# -*- coding: utf-8 -*-
import ast

SRC = (r"C:/Users/25243/AppData/Local/Temp/claude/D--ZZL-cluade/"
       r"1dc74369-9e41-44da-94de-48910a3b4185/scratchpad/oracle_arm.py")
src = open(SRC, encoding="utf-8").read()
NL = chr(10)
patch = NL.join([
    "",
    "# ── 修正框定协议 v2 补丁(与 framing_arm 逐字一致)──",
    "import qvf.generator as G  # noqa: E402",
    "G.BASELINE_GENERATOR_SYSTEM_PROMPT = (",
    '    "You are the user\'s personal AI assistant. You will be shown excerpts "',
    '    "from your past conversations with this user (retrieved from memory, "',
    '    "each dated), followed by the user\'s new message. Reply to the new "',
    '    "message naturally and helpfully in 1-3 sentences, as you would in an "',
    '    "everyday chat."',
    ")",
    "",
    "def _fr_fmt(query, memories, query_date=None):",
    '    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]',
    "    for m in memories:",
    '        d = (m.metadata or {}).get("session_date") or "undated"',
    '        lines.append(f"[{d}] {m.content}")',
    '    lines.append("")',
    "    if query_date:",
    '        lines.append(f"TODAY\'S DATE: {query_date}")',
    '        lines.append("")',
    '    lines.append(f"USER\'S NEW MESSAGE: {query}")',
    "    return chr(10).join(lines)",
    "",
    "G.format_baseline_generator_input = _fr_fmt",
    "",
])
anchor = "import scripts.run_decisive_stale as rds  # noqa: E402"
assert anchor in src
src = src.replace(anchor, anchor + NL + patch)
open(r"scripts/framing_oracle_arm.py", "w", encoding="utf-8").write(src)
ast.parse(open(r"scripts/framing_oracle_arm.py", encoding="utf-8").read())
print("framing_oracle_arm written, syntax OK")
