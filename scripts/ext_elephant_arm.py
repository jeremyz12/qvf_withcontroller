# -*- coding: utf-8 -*-
"""批 29-OB:ElephantBench 合成开卷三臂(prereg 见 results/opt_batch29_prereg.md)。

用法:
  python scripts/ext_elephant_arm.py --phase gen     # 伪文档底料(值逐字闸)
  python scripts/ext_elephant_arm.py --phase cards   # 写侧抽卡(报双值覆盖率)
  python scripts/ext_elephant_arm.py --phase run --arm closedbook|fullplain|qvf
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

N_ITEMS = 120
SEED = 26
DOCS_F = ROOT / "results/ext_elephant_docs.json"
CARDS_F = ROOT / "results/ext_elephant_cards.json"
SRC_NAMES = ("the Meridian Courier archive", "the Halcyon Reference Desk")

CLOSEDBOOK_SYS = (
    "You are answering a general-knowledge question using only your own "
    "training-time knowledge. You have no access to search, browsing, or any "
    "external tool, and no source documents have been given to you—rely "
    "solely on what you already know. If you recall that different reputable "
    "sources report different values for this fact, state all the values you "
    "recall and briefly note that sources disagree. If you only know one "
    "value, give only that value; if you genuinely do not know, say so rather "
    "than guessing. Keep the answer to at most three sentences.")
OPENBOOK_SYS = (
    "You are answering a question using the provided {what}. If different "
    "sources report different values for the fact in question, state all the "
    "values and briefly note that sources disagree. Keep the answer to at "
    "most three sentences.")
JUDGE_SYS = (
    "Evaluate factual recall using only the supplied question, candidate "
    "golds, and model answer. Judge semantic meaning, not exact wording. "
    "Steps: (1) identify the requested slot; (2) assess every gold: count "
    "direct statements and clear explanatory coverage, accepting paraphrase, "
    "rounding, and explanations connecting a gold to a source discrepancy; "
    "(3) record only material contradictions (a non-gold value clearly "
    "endorsed for the slot); (4) credit mechanically: any material "
    "contradiction or zero covered golds => no_credit; all golds covered => "
    "full_credit; otherwise partial_credit. Return JSON only: "
    '{"credit": "full_credit|partial_credit|no_credit", "reasoning": "..."}')


def haiku(system: str, user: str, max_tokens: int = 400) -> str:
    import anthropic
    cli = haiku._c = getattr(haiku, "_c", None) or anthropic.Anthropic()
    r = cli.messages.create(model="claude-haiku-4-5", max_tokens=max_tokens,
                            temperature=0.0, system=system,
                            messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in r.content if b.type == "text")


def judge(question: str, golds: list, answer: str) -> str:
    from openai import OpenAI
    cli = judge._c = getattr(judge, "_c", None) or OpenAI()
    u = (f"Question: {question}\nCandidate golds: "
         f"{json.dumps(golds, ensure_ascii=False)}\nModel answer: {answer}")
    for _ in range(3):
        r = cli.chat.completions.create(
            model="gpt-5-mini", max_completion_tokens=2000,
            messages=[{"role": "system", "content": JUDGE_SYS},
                      {"role": "user", "content": u}])
        m = re.search(r"(full_credit|partial_credit|no_credit)",
                      r.choices[0].message.content or "")
        if m:
            return m.group(1)
    return "no_credit"


def sample_items():
    rows = [json.loads(l) for l in
            open(ROOT / "data/external/elephantbench/elephantbench.jsonl",
                 encoding="utf-8")]
    by_group = {}
    for r in rows:
        g = by_group.setdefault(r["item_group_id"], [])
        g.append(r)
    groups = sorted(by_group)
    random.Random(SEED).shuffle(groups)
    items = []
    for g in groups[:N_ITEMS]:
        r = min(by_group[g], key=lambda x: x["benchmark_id"])
        items.append({"id": r["benchmark_id"], "group": g,
                      "question": r["eval"]["question"],
                      "golds": [a["value"] for a in r["eval"]["gold_answers"]]})
    return items


def phase_gen():
    docs = json.loads(DOCS_F.read_text(encoding="utf-8")) \
        if DOCS_F.exists() else {}
    items = sample_items()
    fallback = 0
    for it in items:
        if it["id"] in docs:
            continue
        pair = []
        for k, val in enumerate(it["golds"][:2]):
            name = SRC_NAMES[k]
            doc = ""
            for _ in range(2):
                doc = haiku(
                    "You write short archival snippets. Follow the "
                    "constraints exactly. Output only the snippet.",
                    f"Write 2-3 sentences in the style of a factual report "
                    f"from {name} that answers the following question with "
                    f"exactly this value: \"{val}\". The snippet MUST contain "
                    f"the exact string \"{val}\" verbatim and MUST NOT "
                    f"mention any other candidate value for this question.\n"
                    f"Question: {it['question']}")
                if val.lower() in doc.lower():
                    break
            if val.lower() not in doc.lower():
                doc = (f"According to {name}, regarding this question the "
                       f"reported value is {val}.")
                fallback += 1
            pair.append({"source": name, "text": doc.strip(), "gold": val})
        docs[it["id"]] = {"item": it, "docs": pair}
        DOCS_F.write_text(json.dumps(docs, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(f"[gen {len(docs)}/{len(items)}] {it['id'][:8]}", flush=True)
    print(f"GEN DONE n={len(docs)} 兜底模板 {fallback} 份")


def phase_cards():
    docs = json.loads(DOCS_F.read_text(encoding="utf-8"))
    cards = json.loads(CARDS_F.read_text(encoding="utf-8")) \
        if CARDS_F.exists() else {}
    covered = 0
    for bid, rec in docs.items():
        if bid not in cards:
            allc = []
            for d in rec["docs"]:
                raw = haiku(
                    "You extract state cards from source snippets. Output "
                    "only a JSON array.",
                    "Extract every reported factual value from this snippet "
                    "as state cards. Return a JSON array of objects "
                    '{"attribute": ..., "value": ..., "source": ..., '
                    '"span": <verbatim quote containing the value>}.\n'
                    f"Source name: {d['source']}\nSnippet: {d['text']}")
                m = re.search(r"\[.*\]", raw, re.S)
                try:
                    allc += json.loads(m.group(0)) if m else []
                except json.JSONDecodeError:
                    pass
            cards[bid] = allc
            CARDS_F.write_text(json.dumps(cards, ensure_ascii=False,
                                          indent=1), encoding="utf-8")
        blob = json.dumps(cards[bid], ensure_ascii=False).lower()
        if all(g.lower() in blob for g in rec["item"]["golds"][:2]):
            covered += 1
        print(f"[cards {bid[:8]}] {len(cards[bid])} cards", flush=True)
    print(f"CARDS DONE 双值覆盖 {covered}/{len(docs)} = "
          f"{covered / len(docs) * 100:.1f}%")


def phase_run(arm: str):
    docs = json.loads(DOCS_F.read_text(encoding="utf-8"))
    cards = json.loads(CARDS_F.read_text(encoding="utf-8")) \
        if arm == "qvf" else {}
    outp = ROOT / f"results/ext_elephant_{arm}.jsonl"
    done = {json.loads(l)["question_id"]
            for l in open(outp, encoding="utf-8")} if outp.exists() else set()
    fh = open(outp, "a", encoding="utf-8")
    tally = {"full_credit": 0, "partial_credit": 0, "no_credit": 0}
    n = 0
    for bid, rec in docs.items():
        it = rec["item"]
        if bid in done:
            continue
        t0 = time.time()
        if arm == "closedbook":
            ans = haiku(CLOSEDBOOK_SYS, it["question"])
        elif arm == "fullplain":
            src = "\n\n".join(f"[{d['source']}] {d['text']}"
                              for d in rec["docs"])
            ans = haiku(OPENBOOK_SYS.format(what="source excerpts"),
                        f"Sources:\n{src}\n\nQuestion: {it['question']}")
        else:
            led = "\n".join(
                f"- [{c.get('source', '?')}] {c.get('attribute', '?')}: "
                f"{c.get('value', '?')} | evidence: \"{c.get('span', '')}\""
                for c in cards.get(bid, []))
            ans = haiku(OPENBOOK_SYS.format(
                what="dated memory ledger distilled from sources"),
                f"Memory ledger:\n{led}\n\nQuestion: {it['question']}")
        credit = judge(it["question"], it["golds"], ans)
        tally[credit] += 1
        n += 1
        fh.write(json.dumps({
            "question_id": bid, "group": it["group"], "mode": f"eb_{arm}",
            "question": it["question"], "golds": it["golds"],
            "answer": ans.strip()[:1500], "credit": credit,
            "latency_s": round(time.time() - t0, 2)},
            ensure_ascii=False) + "\n")
        fh.flush()
        print(f"[{arm} {n}] {credit}", flush=True)
    tot = max(1, sum(tally.values()))
    c, p = tally["full_credit"] / tot * 100, tally["partial_credit"] / tot * 100
    print(f"EB ARM DONE {arm}: C={c:.1f} P={p:.1f} "
          f"F={tally['no_credit'] / tot * 100:.1f} K={c / max(c + p, 1e-9) * 100:.1f} (n={tot})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["gen", "cards", "run"], required=True)
    ap.add_argument("--arm", choices=["closedbook", "fullplain", "qvf"])
    a = ap.parse_args()
    if a.phase == "gen":
        phase_gen()
    elif a.phase == "cards":
        phase_cards()
    else:
        phase_run(a.arm)
