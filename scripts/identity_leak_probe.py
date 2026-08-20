# -*- coding: utf-8 -*-
"""scripts/identity_leak_probe.py — 部分上下文身份泄漏探针(机械判分)。

预注册:results/identity_leak_probe_prereg.md(提交 9941c57,先于本文件运行)。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic

ROOT = Path(r"D:\ZZL_cluade")
S5 = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
      "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
S8 = ["data/wikistate_full_multi_P108_P551_v3.json", "data/wikistate_full_multi_P54_P108.json"]
CTRL = ["data/replchain_50.json"]
OUT = ROOT / "results/identity_leak_probe_20260820.jsonl"
MODEL = "claude-haiku-4-5"

PROMPT = """Here are the first two dated status updates about one attribute of a person:

[{d1}] {s1}
[{d2}] {s2}

Attribute: {slot}

Two tasks:
1. If you can identify who this specific real person might be, name them; otherwise say "unknown".
2. Based on your knowledge (NOT invention), list what this attribute changed to AFTER {d2},
   as a JSON list of values in order. If you do not know, return [].

Reply ONLY with JSON: {{"identity": "...", "subsequent_values": ["...", "..."]}}"""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def hit(pred: str, gold: str) -> bool:
    p, g = norm(pred), norm(gold)
    return bool(p and g) and (p in g or g in p)


def probe(client, corpus, tag, f):
    done = {json.loads(l)["uid"] for l in open(OUT, encoding="utf-8")} if OUT.exists() else set()
    for path in corpus:
        for e in json.loads((ROOT / path).read_text(encoding="utf-8")):
            uid = e["uid"]
            if uid in done:
                continue
            ch = e.get("chain") or []
            if len(ch) < 3:
                continue
            later = [str(c.get("value") or "") for c in ch[2:]]
            msg = PROMPT.format(
                d1=ch[0].get("date"), s1=ch[0].get("state_span") or ch[0].get("value"),
                d2=ch[1].get("date"), s2=ch[1].get("state_span") or ch[1].get("value"),
                slot=e.get("slot") or "")
            try:
                rr = client.messages.create(model=MODEL, max_tokens=500,
                                            temperature=0.0,
                                            messages=[{"role": "user", "content": msg}])
                txt = "".join(b.text for b in rr.content if b.type == "text")
                j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
                preds = [str(x) for x in (j.get("subsequent_values") or [])][:5]
            except Exception as err:  # noqa: BLE001
                f.write(json.dumps({"uid": uid, "corpus": tag,
                                    "error": str(err)[:150]}) + "\n")
                f.flush()
                continue
            hits = [g for g in later if any(hit(p, g) for p in preds)]
            f.write(json.dumps({
                "uid": uid, "corpus": tag, "slot": e.get("slot"),
                "identity_guess": str(j.get("identity", ""))[:80],
                "n_later": len(later), "preds": preds, "hits": hits,
                "leaked": bool(hits)}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{tag}] {uid[:30]} leaked={bool(hits)}", flush=True)


def main() -> int:
    client = anthropic.Anthropic()
    with OUT.open("a", encoding="utf-8") as f:
        probe(client, S5, "s5", f)
        probe(client, S8, "s8", f)
        probe(client, CTRL, "control", f)
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8") if '"error"' not in l]
    print("\n| 语料 | 实体 | 泄漏 | 率 |")
    for tag in ("s5", "s8", "control"):
        sub = [r for r in rows if r["corpus"] == tag]
        lk = sum(1 for r in sub if r["leaked"])
        if sub:
            print(f"| {tag} | {len(sub)} | {lk} | {lk/len(sub)*100:.1f}% |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
