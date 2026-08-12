# -*- coding: utf-8 -*-
"""WikiState 试点·步骤2:标签解析 + 机械验证出题 + 参数可答过滤。

产物:data/wikistate_items.json —— 每条目含非重叠任职链(英文标签)、
四问及机械金答案;经"无记忆参数对照"过滤(haiku 裸答对任一问即弃)。"""
import json
import time
from pathlib import Path

import requests
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
API = "https://www.wikidata.org/w/api.php"
MODEL = "claude-haiku-4-5"


def resolve_labels(qids):
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        r = requests.get(API, params={
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "labels", "languages": "en", "format": "json"},
            headers=UA, timeout=30)
        for qid, ent in r.json().get("entities", {}).items():
            labels[qid] = ent.get("labels", {}).get("en", {}).get("value", qid)
        time.sleep(0.2)
    return labels


def nonoverlap(chain):
    out = []
    for c in chain:
        if not out or c["start"] >= out[-1]["end"]:
            out.append(c)
    return out


def midpoint(a, b):
    from datetime import date
    def p(s):
        y, m, d = (s + "-01-01")[:10].split("-")
        return date(int(y), max(1, int(m)), max(1, int(d)))
    da, db = p(a), p(b)
    return (da + (db - da) / 2).isoformat()


import sys as _sys

PROP = _sys.argv[1] if len(_sys.argv) > 1 else "P39"
NOUN = {"P39": "position", "P54": "team", "P108": "employer",
        "P551": "residence"}[PROP]
CAND_FILE = (r"data/wikistate_candidates.json" if PROP == "P39"
             else rf"data/wikistate_candidates_{PROP}.json")
OUT_FILE = (r"data/wikistate_items.json" if PROP == "P39"
            else rf"data/wikistate_items_{PROP}.json")
if len(_sys.argv) > 2:
    CAND_FILE = _sys.argv[2]
if len(_sys.argv) > 3:
    OUT_FILE = _sys.argv[3]


def main():
    cands = json.load(open(CAND_FILE, encoding="utf-8"))
    pos_qids = {c["position"] for it in cands for c in it["chain"]}
    print(f"resolving {len(pos_qids)} position labels...")
    labels = resolve_labels(pos_qids)

    items = []
    for it in cands:
        chain = nonoverlap(it["chain"])
        chain = [c for c in chain if c["start"] and c["end"] and c["start"] < c["end"]]
        seen = set()
        dedup = []
        for c in chain:
            lb = labels.get(c["position"], c["position"])
            if lb not in seen and not lb.startswith("Q"):
                seen.add(lb)
                dedup.append({**c, "label": lb})
        if len(dedup) < 3:
            continue
        last, mid = dedup[-1], dedup[len(dedup) // 2]
        pt = dedup[0] if dedup[0] is not mid else dedup[1]
        today = last["start"][:10]
        point_date = midpoint(pt["start"], pt["end"])
        name = it["label"]
        qs = {
            "dim1": {"q": f"What {NOUN} does {name} have these days?",
                     "gold": last["label"]},
            "dim2": {"q": f"Since {name}'s current {NOUN} is {mid['label']}, what would "
                          f"typically be relevant to know about it?",
                     "gold": (f"The premise is outdated: as of {today} {name}'s "
                              f"current {NOUN} is {last['label']} (the "
                              f"{mid['label']} tenure ended {mid['end']}). A "
                              f"correct answer must correct the premise; it must "
                              f"not answer as if {mid['label']} were current."),
                     "presupposed": mid["label"]},
            "dim4": {"q": f"What {NOUN} did {name} have on {point_date}?",
                     "gold": pt["label"], "date": point_date},
            "dim5": {"q": f"How did {name}'s {NOUN} change over time — which values, in order?",
                     "gold": " -> ".join(c["label"] for c in dedup)},
        }
        items.append({"qid": it["qid"], "name": name, "sitelinks": it["sitelinks"],
                      "today": today, "chain": dedup, "questions": qs})
    print(f"validated items: {len(items)}")

    # 参数可答过滤:无记忆裸答,任一问判对 → 弃条目
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    kept = []
    for i, it in enumerate(items):
        leak = False
        for dim, q in it["questions"].items():
            r = client.messages.create(
                model=MODEL, max_tokens=300, temperature=0.0,
                messages=[{"role": "user", "content":
                           f"(Assume today is {it['today']}.) {q['q']} "
                           f"Answer in 1-2 sentences."}])
            ans = "".join(b.text for b in r.content if b.type == "text")
            v = judge.judge(q["q"], q["gold"], ans, f"wiki-{dim}")
            if v.correct:
                leak = True
                break
        tag = "LEAK-DROP" if leak else "keep"
        print(f"[{i+1}/{len(items)}] {it['name']}: {tag}", flush=True)
        if not leak:
            kept.append(it)
    Path(OUT_FILE).write_text(
        json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"FINAL: {len(kept)} items -> data/wikistate_items.json")


if __name__ == "__main__":
    main()
