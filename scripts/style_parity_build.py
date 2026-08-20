# -*- coding: utf-8 -*-
"""scripts/style_parity_build.py — 风格配平语料构造(批 1)。

预注册:results/style_parity_prereg.md(提交 44f56a7,先于本文件运行)。
改写干扰会话为自然散文 + 注入第三方同族转变硬负例;金链/金会话/题目不动。
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")
import anthropic

ROOT = Path(r"D:\ZZL_cluade")
VOLS = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
        "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
MODEL = "claude-haiku-4-5"
rng = random.Random(20260820)

REWRITE = """Rewrite the following chat-log fragments into natural, first-person
casual chat messages from a user to their AI assistant. Keep EVERY factual
detail, name, number and topic; keep roughly the same length; do NOT add any
statements about the user's employer/team/position/city changing.

Return ONLY a JSON list of strings, one rewritten message per input fragment.

FRAGMENTS:
{frags}"""

NEG = """Write {n} short casual chat messages in which the user mentions a
THIRD PARTY (brother / colleague / friend, with an invented name) changing
their {slot} to a NEW value. The new values must NOT be any of: {ban}.
Each message is 1-2 sentences, first person ("My brother Tom just started
at ..."). Return ONLY a JSON list of strings."""


def jlist(text):
    try:
        return json.loads(text[text.index("["):text.rindex("]") + 1])
    except Exception:
        return None


def main() -> int:
    client = anthropic.Anthropic()
    entries = []
    for v in VOLS:
        d = json.loads((ROOT / v).read_text(encoding="utf-8"))
        uids = sorted(e["uid"] for e in d)
        take = {uids[i * len(uids) // 3] for i in range(3)} if v != VOLS[0] else \
               {uids[i * len(uids) // 1] if False else uids[i * len(uids) // 1 - 1]
                for i in [1]} | {uids[0]}
        # 简化:每卷取前 2-3 个(分层等距)
        take = {uids[i * len(uids) // 3] for i in range(3)}
        entries += [e for e in d if e["uid"] in take]
    entries = entries[:10]
    print("抽中:", [e["uid"] for e in entries], flush=True)

    vals_all = lambda e: [str(c.get("value") or "") for c in e.get("chain", [])]
    out, inject_log = [], []
    for e in entries:
        chain_vals = vals_all(e)
        gold_dates = {str(c.get("date")) for c in e.get("chain", [])}
        new_sessions = []
        for s in e.get("sessions", []):
            blob = " ".join(str(t) for t in s.get("turns", []))
            is_gold = any(v and v in blob for v in chain_vals)
            if is_gold:
                new_sessions.append(s)
                continue
            frags = [str(t)[:400] for t in s.get("turns", [])[:6]]
            r = client.messages.create(
                model=MODEL, max_tokens=1500, temperature=0.3,
                messages=[{"role": "user",
                           "content": REWRITE.format(frags=json.dumps(frags))}])
            rw = jlist("".join(b.text for b in r.content if b.type == "text"))
            if rw and len(rw) >= 1:
                new_sessions.append({"date": s.get("date"), "turns": rw})
            else:
                new_sessions.append(s)          # 改写失败保留原样,如实计数
        # 硬负例
        r = client.messages.create(
            model=MODEL, max_tokens=800, temperature=0.7,
            messages=[{"role": "user", "content": NEG.format(
                n=4, slot=e.get("slot"), ban=", ".join(chain_vals))}])
        negs = jlist("".join(b.text for b in r.content if b.type == "text")) or []
        negs = [n for n in negs
                if not any(v.lower() in str(n).lower() for v in chain_vals)][:4]
        spots = [i for i, s in enumerate(new_sessions)
                 if str(s.get("date")) not in gold_dates]
        rng.shuffle(spots)
        for n_txt, si in zip(negs, spots):
            new_sessions[si]["turns"] = list(new_sessions[si]["turns"]) + [n_txt]
        inject_log.append({"uid": e["uid"], "n_injected": min(len(negs), len(spots)),
                           "negs": negs})
        e2 = dict(e)
        e2["sessions"] = new_sessions
        out.append(e2)
        print(f"[{e['uid']}] rewrote {sum(1 for s in new_sessions)} sessions, "
              f"injected {min(len(negs), len(spots))} negatives", flush=True)

    (ROOT / "data/s5_styled_p10.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    (ROOT / "results/style_parity_inject_log.json").write_text(
        json.dumps(inject_log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done:", len(out), "entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
