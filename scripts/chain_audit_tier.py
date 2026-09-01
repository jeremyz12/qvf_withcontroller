# -*- coding: utf-8 -*-
"""链完整性候选分档复判(第二段):把高召回扫描的候选分成 A/B/C 三档。

档位定义(写死):
  A 硬漏 = 原文明确断言用户自身的该槽位【具名值】,且金标链无此值
           → 同时污染值型与计数型金标;
  B 软漏 = 明确断言一次状态转移但值未具名("started my new job"/"got
           promoted"/"moved into a new place"),链中无对应转移
           → 只污染计数型金标;
  C 噪声 = 仅隐含在职/居住,无转移无具名值;或指他人/假设/愿望;或与
           链中已有行同指。

复判材料:候选引文 + 其所在会话全文(上下文)+ 完整金标链。
用法: python scripts/chain_audit_tier.py
产物: results/chain_audit_tiers.jsonl
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

IN = ROOT / "results/chain_completeness_audit.jsonl"
OUT = ROOT / "results/chain_audit_tiers.jsonl"
SYS = ("You adjudicate whether a flagged sentence is a genuine missing state "
       "in a benchmark's gold chain. Be strict: the default is C (noise). "
       "Output JSON only.")
TMPL = """SLOT: {slot}

GOLD CHAIN (date | value | anchor):
{chain}

FLAGGED SENTENCE (from session {date}):
"{quote}"

FULL SESSION CONTAINING IT (for context):
{session}

Assign exactly one tier:
A = the sentence asserts, as fact, a state of slot "{slot}" for the user \
themselves that is IDENTIFIABLE and is not covered by any chain row. \
Identifiable does NOT require a proper name: "a data analyst at a mid-sized \
company in New York City", "my role as Senior Software Engineer", "the \
language school in Roppongi" all qualify, because they pin down a concrete \
job/place/team distinguishable from the chain rows.
B = the sentence asserts a real state TRANSITION for slot "{slot}" for the \
user (started a new job, got promoted into a new post, moved somewhere new, \
joined a new team) with no identifiable description at all, and no chain row \
covers that transition.
C = anything else: mere implication of being employed/living somewhere with \
no transition and no description; about another person; a question, plan, \
hypothetical or wish; a restatement of a value already in the chain; a value \
belonging to a different slot; OR — important — a statement that could \
plausibly describe the user's SAME job/place/team as a chain row whose dates \
cover this session (e.g. a job title held at a chain employer).

Judge A vs C by this test: reading the log, would a careful annotator say \
"the persona also had this {slot} state, and the chain is missing it"? \
If yes -> A. If it is just another way of talking about a state already in \
the chain, or too vague to place -> C.

Return: {{"tier": "A|B|C", "value": "<named value, or null>", \
"why": "<one sentence>"}}"""


def sessions_of(entry: dict) -> list:
    out = []
    for s in entry.get("sessions", []):
        msgs = []
        for t in s.get("turns", []):
            if isinstance(t, dict):
                if t.get("role") == "user":
                    msgs.append(str(t.get("content", "")))
            else:
                msgs.append(str(t))
        out.append((s.get("date", "?"), "\n".join(msgs)))
    return out


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def main() -> int:
    from openai import OpenAI
    cli = OpenAI()
    data = {e["uid"]: e for e in json.loads(
        (ROOT / "data/wikistate_full_ALL.json").read_text(encoding="utf-8"))}
    done = set()
    if OUT.exists():
        for l in open(OUT, encoding="utf-8"):
            r = json.loads(l)
            done.add((r["uid"], norm(r["quote"])))
    fh = open(OUT, "a", encoding="utf-8")
    tally = {"A": 0, "B": 0, "C": 0}
    for line in open(IN, encoding="utf-8"):
        rec = json.loads(line)
        uid = rec["uid"]
        e = data.get(uid)
        if not e:
            continue
        chain = "\n".join(f"#{i} | {c['date']} | {c['value']} | "
                          f"\"{c['state_span']}\""
                          for i, c in enumerate(e["chain"], 1))
        sess = sessions_of(e)
        for cand in rec["candidates"]:
            q = str(cand.get("quote", ""))
            if (uid, norm(q)) in done:
                continue
            ctx = ""
            for d, body in sess:
                if norm(q) in norm(body):
                    ctx = f"[{d}]\n{body}"
                    break
            prompt = TMPL.format(slot=rec["slot"], chain=chain,
                                 date=cand.get("date", "?"), quote=q,
                                 session=ctx[:6000])
            tier, val, why = "C", None, ""
            for attempt in range(3):
                try:
                    r = cli.chat.completions.create(
                        model="gpt-5-mini", max_completion_tokens=1500,
                        messages=[{"role": "system", "content": SYS},
                                  {"role": "user", "content": prompt}])
                    txt = r.choices[0].message.content or ""
                    m = re.search(r"\{.*\}", txt, re.S)
                    if m:
                        o = json.loads(m.group(0))
                        tier = str(o.get("tier", "C")).strip().upper()[:1]
                        val, why = o.get("value"), str(o.get("why", ""))[:300]
                        break
                except Exception as ex:  # noqa: BLE001
                    print(f"retry {attempt}: {str(ex)[:60]}", flush=True)
                    time.sleep(4)
            tier = tier if tier in ("A", "B", "C") else "C"
            tally[tier] += 1
            fh.write(json.dumps({
                "uid": uid, "slot": rec["slot"], "date": cand.get("date"),
                "quote": q, "scanner_value": cand.get("implied_value"),
                "tier": tier, "value": val, "why": why},
                ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{uid}] {tier}: {q[:60]}", flush=True)
    print(f"TIER DONE A={tally['A']} B={tally['B']} C={tally['C']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
