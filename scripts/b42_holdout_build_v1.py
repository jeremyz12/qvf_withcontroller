# -*- coding: utf-8 -*-
"""批 42 冻结保留集 2·步骤2:标签解析 + 机械验证出题 + 参数可答过滤。

逐字沿用 scripts/holdout_build_v1.py(= scripts/wikistate_build.py 的链清洗
规则 + "无记忆参数对照"闸:haiku 裸答四问,ClaudeJudge 判对任一 → 弃)。
只改输入输出路径(holdout2_*)。

用法:python scripts/b42_holdout_build_v1.py P551 10
产物:data/holdout2_items_<PROP>.json
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
API = "https://www.wikidata.org/w/api.php"
MODEL = "claude-haiku-4-5"

PROP = sys.argv[1] if len(sys.argv) > 1 else "P39"
NOUN = {"P39": "position", "P54": "team", "P108": "employer",
        "P551": "residence"}[PROP]
KEEP_TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 0   # 0 = 不设上限
CAND_FILE = ROOT / f"data/holdout2_candidates_{PROP}.json"
OUT_FILE = ROOT / f"data/holdout2_items_{PROP}.json"


def resolve_labels(qids):
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        for _ in range(3):
            try:
                r = requests.get(API, params={
                    "action": "wbgetentities", "ids": "|".join(batch),
                    "props": "labels", "languages": "en", "format": "json"},
                    headers=UA, timeout=40)
                for qid, ent in r.json().get("entities", {}).items():
                    labels[qid] = ent.get("labels", {}).get(
                        "en", {}).get("value", qid)
                break
            except Exception as e:  # noqa: BLE001
                print(f"label retry: {type(e).__name__}", flush=True)
                time.sleep(3)
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


def main():
    cands = json.loads(CAND_FILE.read_text(encoding="utf-8"))
    pos_qids = {c["position"] for it in cands for c in it["chain"]}
    print(f"resolving {len(pos_qids)} value labels...", flush=True)
    labels = resolve_labels(pos_qids)

    items = []
    for it in cands:
        chain = nonoverlap(it["chain"])
        chain = [c for c in chain
                 if c["start"] and c["end"] and c["start"] < c["end"]]
        seen, dedup = set(), []
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
            "dim2": {"q": f"Since {name}'s current {NOUN} is {mid['label']}, "
                          f"what would typically be relevant to know about it?",
                     "gold": (f"The premise is outdated: as of {today} {name}'s "
                              f"current {NOUN} is {last['label']} (the "
                              f"{mid['label']} tenure ended {mid['end']}). A "
                              f"correct answer must correct the premise; it must "
                              f"not answer as if {mid['label']} were current."),
                     "presupposed": mid["label"]},
            "dim4": {"q": f"What {NOUN} did {name} have on {point_date}?",
                     "gold": pt["label"], "date": point_date},
            "dim5": {"q": f"How did {name}'s {NOUN} change over time — which "
                          f"values, in order?",
                     "gold": " -> ".join(c["label"] for c in dedup)},
        }
        items.append({"qid": it["qid"], "name": name,
                      "sitelinks": it["sitelinks"], "today": today,
                      "chain": dedup, "questions": qs})
    items.sort(key=lambda it: (len(it["chain"]), it["qid"]))
    print(f"validated items: {len(items)} "
          f"(len-sorted; lens={[len(it['chain']) for it in items][:20]})",
          flush=True)

    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    todo = items[:KEEP_TARGET * 3] if KEEP_TARGET else items

    def probe(it):
        for dim, q in it["questions"].items():
            ans = ""
            for _ in range(4):
                try:
                    r = client.messages.create(
                        model=MODEL, max_tokens=300, temperature=0.0,
                        messages=[{"role": "user", "content":
                                   f"(Assume today is {it['today']}.) {q['q']} "
                                   f"Answer in 1-2 sentences."}])
                    ans = "".join(b.text for b in r.content if b.type == "text")
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  retry {type(e).__name__}", flush=True)
                    time.sleep(6)
            v = judge.judge(q["q"], q["gold"], ans, f"wiki-{dim}")
            if v.correct:
                return True, dim
        return False, None

    kept = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {}
        it_iter = iter(list(enumerate(todo)))
        pending = []
        for _ in range(3):
            nxt = next(it_iter, None)
            if nxt:
                pending.append(nxt)
        results = {}
        for i, it in pending:
            futs[ex.submit(probe, it)] = (i, it)
        while futs:
            for fut in as_completed(list(futs)):
                i, it = futs.pop(fut)
                try:
                    leak, dim = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"[{i+1}] probe failed: {e}", flush=True)
                    leak, dim = True, "error"
                results[i] = (it, leak, dim)
                print(f"[{i+1}/{len(todo)}] {it['name']}: "
                      f"{'LEAK-DROP(' + str(dim) + ')' if leak else 'keep'}",
                      flush=True)
                n_keep = sum(1 for _, (_, lk, _) in results.items() if not lk)
                if not (KEEP_TARGET and n_keep >= KEEP_TARGET):
                    nxt = next(it_iter, None)
                    if nxt:
                        futs[ex.submit(probe, nxt[1])] = nxt
                break
    for i in sorted(results):
        it, leak, _ = results[i]
        if not leak and not (KEEP_TARGET and len(kept) >= KEEP_TARGET):
            kept.append(it)
    OUT_FILE.write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"FINAL: {len(kept)} kept / {len(results)} probed / {len(items)} validated -> {OUT_FILE}")
    print(f"judge usage: {judge.total_usage}")


if __name__ == "__main__":
    main()
