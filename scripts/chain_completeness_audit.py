# -*- coding: utf-8 -*-
"""链完整性机器审计:找"原文里声明了该槽位状态、但未进金标链"的漏检。

动因:人工核验 item 8 发现填充会话(STALE 混音)引入了同槽位状态却未入链——
若普遍存在,计数型题目(change_count/count_before)的金标系统性偏低。

三段式(杀幻觉):
  1) 扫描:haiku 读完整用户侧会话日志 + 金标链,高召回列出候选漏检;
  2) 机械核验:候选引文必须在原文中逐字存在(归一空白),否则丢弃;
  3) 复判留给 workflow 对抗代理(本脚本只出候选)。

用法: python scripts/chain_completeness_audit.py [--limit N]
产物: results/chain_completeness_audit.jsonl(逐链一行)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import anthropic  # noqa: E402

OUT = ROOT / "results/chain_completeness_audit.jsonl"
SLOT_DESC = {
    "employer": "the user's own employer / the organization they work for",
    "position": "the user's own job title or official position",
    "residence": "the city or place the user lives in",
    "member_of": "a group, party, or organization the user belongs to",
    "educated_at": "a school or university the user attends/attended",
}
SYS = ("You audit a benchmark's gold 'state chain' for COMPLETENESS. You are "
       "shown a user's full message log (assistant replies omitted) and a "
       "gold chain of state rows for one slot. Your job is to find user "
       "statements that assert a value for that slot but are MISSING from "
       "the chain. Be precise and quote verbatim. Output JSON only.")
USER = """SLOT: {slot} — {desc}

GOLD CHAIN (each row: date | value | anchor sentence):
{chain}

FULL USER MESSAGE LOG (session dates given; only user messages shown):
{log}

TASK: list every user statement in the log that asserts or clearly implies a \
value of the slot "{slot}" FOR THE USER THEMSELVES, and that is NOT already \
represented by one of the gold chain rows above.

Count as a MISS only if the statement asserts the user's own state for this \
slot as a fact (e.g. starting, working at, living in, joining). Do NOT report:
- statements about other people, companies discussed in the abstract, or media;
- questions, hypotheticals, plans, wishes, or things they are considering;
- rephrasings or later mentions of a value that already appears in the chain;
- values for a DIFFERENT slot than "{slot}".

Return a JSON array (possibly empty). Each element:
{{"date": "<session date>", "quote": "<VERBATIM sentence copied exactly from \
the log>", "implied_value": "<the slot value it asserts>", "reason": "<why it \
is a distinct state not in the chain>"}}

The quote MUST be copied character-for-character from the log so it can be \
verified mechanically."""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def user_log(entry: dict) -> str:
    out = []
    for s in entry.get("sessions", []):
        msgs = []
        for t in s.get("turns", []):
            if isinstance(t, dict):
                if t.get("role") == "user":
                    msgs.append(str(t.get("content", "")))
            else:
                msgs.append(str(t))
        if msgs:
            out.append(f"### Session {s.get('date', '?')}\n" + "\n".join(msgs))
    return "\n\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    data = json.loads((ROOT / "data/wikistate_full_ALL.json")
                      .read_text(encoding="utf-8"))
    done = {json.loads(l)["uid"] for l in open(OUT, encoding="utf-8")} \
        if OUT.exists() else set()
    fh = open(OUT, "a", encoding="utf-8")
    cli = anthropic.Anthropic()
    n = flagged = 0
    for e in data:
        uid = e["uid"]
        if uid in done:
            continue
        if a.limit and n >= a.limit:
            break
        log = user_log(e)
        chain = "\n".join(
            f"#{i} | {c['date']} | {c['value']} | \"{c['state_span']}\""
            for i, c in enumerate(e["chain"], 1))
        prompt = USER.format(slot=e["slot"],
                             desc=SLOT_DESC.get(e["slot"], e["slot"]),
                             chain=chain, log=log)
        raw = ""
        for attempt in range(3):
            try:
                r = cli.messages.create(
                    model="claude-haiku-4-5", max_tokens=2000,
                    temperature=0.0, system=SYS,
                    messages=[{"role": "user", "content": prompt}])
                raw = "".join(b.text for b in r.content if b.type == "text")
                break
            except Exception as ex:  # noqa: BLE001
                print(f"retry {attempt}: {str(ex)[:70]}", flush=True)
                time.sleep(5)
        i, j = raw.find("["), raw.rfind("]")
        try:
            cands = json.loads(raw[i:j + 1]) if i >= 0 and j > i else []
        except json.JSONDecodeError:
            cands = []
        nlog = norm(log)
        nchain = norm(chain)
        kept, rejected = [], []
        for c in cands if isinstance(cands, list) else []:
            q = norm(str(c.get("quote", "")))
            if not q or len(q) < 15:
                rejected.append({**c, "drop": "quote too short"})
            elif q not in nlog:
                rejected.append({**c, "drop": "quote not verbatim in log"})
            elif q in nchain:
                rejected.append({**c, "drop": "quote is an existing anchor"})
            else:
                kept.append(c)
        fh.write(json.dumps({
            "uid": uid, "slot": e["slot"], "chain_rows": len(e["chain"]),
            "candidates": kept, "rejected": rejected,
            "n_candidates": len(kept)}, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        flagged += bool(kept)
        print(f"[{n}] {uid} {e['slot']}: {len(kept)} 候选"
              f"(机核丢弃 {len(rejected)})", flush=True)
    print(f"AUDIT DONE: 扫 {n} 链,{flagged} 条有候选漏检")
    return 0


if __name__ == "__main__":
    sys.exit(main())
