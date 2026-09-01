# -*- coding: utf-8 -*-
"""机器复核器:用评审界面显示的链 + 原始会话日志,按人类同一判据裁决 149 题。

判据与界面问题逐字对应:"该状态链是否正确且完整地代表了人设在该槽位的历史?"
五类错误全查:漏检状态 / 值错 / 日期错 / 多余行 / 顺序-取代错。
产物: results/machine_review_149.jsonl(verdict + note + 依据)

注意:链取自 rate.db 的界面版本(含 5 道对照题的植入错误),日志取 v2.0 语料
——与人类评审看到的完全一致。本产物是机器审计,不写入任何人类评审身份。
"""
import json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
import anthropic
from build_corpus_v21 import unwrap

SCRATCH = Path(r"C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade"
               r"\c0fc4c00-9fe5-4a6c-bad9-f42ba634a283\scratchpad")
SYS = ("You are verifying a benchmark's gold 'state chain' against the raw "
       "conversation log it was derived from. Be rigorous and concrete. "
       "Output JSON only.")
TMPL = """QUESTION (same wording the human reviewers see):
Does the state chain below correctly and COMPLETELY represent the persona's \
'{slot}' history as stated in the raw session log?

STATE CHAIN AS DISPLAYED:
{chain}

RAW SESSION LOG (user and assistant turns, with session dates):
{log}

Check all five error classes:
1. MISSING: the log states a {slot} state for the persona themselves that no \
chain row covers (this includes states asserted inside filler/small-talk \
sessions, and states echoed by the assistant).
2. WRONG VALUE: a row's value contradicts its anchor sentence or the log.
3. WRONG DATE: a row's date does not match the session where its anchor appears.
4. EXTRA ROW: a row whose anchor sentence does not appear in the log at all.
5. ORDER/SUPERSESSION: rows swapped, or an outdated value presented as current.

Ignore: statements about other people, questions, plans, wishes, in-progress \
degrees, and restatements of a value already in the chain.

Return JSON: {{"verdict": "correct|errors|unsure", "classes": ["MISSING", ...], \
"note": "<one concrete sentence naming date + value, like a reviewer's note>", \
"evidence_quote": "<verbatim sentence from the log if you claim MISSING or \
EXTRA ROW, else empty>"}}"""


def log_of(entry):
    out = []
    for s in entry.get("sessions", []):
        msgs = []
        for t in s.get("turns", []):
            role, body, _ = unwrap(t)
            if isinstance(body, str) and body.strip():
                msgs.append(f"{role}: {body}")
        if msgs:
            out.append(f"### Session {s.get('date','?')}\n" + "\n".join(msgs))
    return "\n\n".join(out)


def main():
    items = json.loads((SCRATCH / "app_chains.json").read_text(encoding="utf-8"))
    cmap = json.loads((ROOT / "data/labelstudio_chainproj_map.json").read_text(encoding="utf-8"))
    data = {e["uid"]: e for e in json.loads((ROOT / "data/wikistate_full_ALL.json").read_text(encoding="utf-8"))}
    out = ROOT / "results/machine_review_149.jsonl"
    done = {json.loads(l)["item"] for l in open(out, encoding="utf-8")} if out.exists() else set()
    fh = open(out, "a", encoding="utf-8")
    cli = anthropic.Anthropic()
    n = 0
    for item, info in sorted(items.items()):
        if item in done: continue
        uid = cmap.get(item, {}).get("uid")
        if uid not in data: continue
        chain = "\n".join(" | ".join(r) for r in info["rows"])
        prompt = TMPL.format(slot=info["slot"], chain=chain, log=log_of(data[uid]))
        res = {"verdict": "unsure", "classes": [], "note": "", "evidence_quote": ""}
        for attempt in range(3):
            try:
                r = cli.messages.create(model="claude-haiku-4-5", max_tokens=1200,
                                        temperature=0.0, system=SYS,
                                        messages=[{"role": "user", "content": prompt}])
                txt = "".join(b.text for b in r.content if b.type == "text")
                m = re.search(r"\{.*\}", txt, re.S)
                if m: res = json.loads(m.group(0)); break
            except Exception as ex:
                print(f"retry {attempt}: {str(ex)[:60]}", flush=True); time.sleep(4)
        # 机核:声称 MISSING/EXTRA 必须给出原文中存在的引文
        q = re.sub(r"\s+", " ", str(res.get("evidence_quote", ""))).strip().lower()
        blob = re.sub(r"\s+", " ", log_of(data[uid])).lower()
        res["quote_verified"] = bool(q) and q in blob
        fh.write(json.dumps({"item": item, "uid": uid, "slot": info["slot"],
                             "catch": bool(cmap.get(item, {}).get("catch")),
                             **res}, ensure_ascii=False) + "\n")
        fh.flush(); n += 1
        print(f"[{n}] {item} {res['verdict']} {res.get('classes')}", flush=True)
    print(f"MACHINE REVIEW DONE n={n}")


if __name__ == "__main__":
    main()
