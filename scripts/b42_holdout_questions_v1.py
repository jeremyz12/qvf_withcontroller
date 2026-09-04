# -*- coding: utf-8 -*-
"""批 42 冻结保留集 2·步骤4:出题(逐字复用 scripts/gen_wsc_v2.py 的四型公式)。

四型:change_count / count_before / longest_tenure / first_vs_last;题面口径、
锚点候选、贪心平衡、末段计入至今、1/4 库"链尾可反超"锚,全部与开发场
及保留集 v1 同源(scripts/holdout_questions_v1.py 逐字)。
唯一差别:语料换成 data/wikistate_holdout2_v1.json,产物换成
data/wsc_holdout2_v1.jsonl(+ data/wsc_holdout2_v1.keymap.json 答案键)。
"""
from __future__ import annotations

import collections
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/wikistate_holdout2_v1.json"
OUT = ROOT / "data/wsc_holdout2_v1.jsonl"
KEY = ROOT / "data/wsc_holdout2_v1.keymap.json"

SLOT_WORD = {"employer": "employer", "position": "position",
             "team": "team", "residence": "residence"}
CC_NOTE = (" (Count only transitions between different values; the initial "
           "value does not count as a change.)")
LT_NOTE = (" (The segment you currently hold counts up to today.)")


def d(s):
    y, m, dd = (s[:10] + "-01-01")[:10].split("-")[:3]
    m = "01" if m == "00" else m
    dd = "01" if dd == "00" else dd
    return date(int(y), int(m), int(dd))


def load_chains():
    out = []
    for e in json.loads(SRC.read_text(encoding="utf-8")):
        ch = e.get("chain") or []
        if len(ch) >= 3 and all(c.get("date") for c in ch):
            out.append((e["uid"], e.get("slot", "attribute"), ch))
    return sorted(out)


def anchors(ch):
    cand = []
    for i in range(1, len(ch)):
        a, b = d(ch[i - 1]["date"]), d(ch[i]["date"])
        if (b - a).days >= 2:
            cand.append((a + (b - a) / 2, i))
    tail = d(ch[-1]["date"])
    cand.append((tail + timedelta(days=180), len(ch)))
    cand.append((tail + timedelta(days=540), len(ch)))
    return cand


def tenure_gold(ch, today):
    per = collections.Counter()
    for i, c in enumerate(ch):
        start = d(c["date"])
        if start > today:
            break
        end = d(ch[i + 1]["date"]) if i + 1 < len(ch) else today
        end = min(end, today)
        if end > start:
            per[c["value"]] += (end - start).days
    if not per:
        return None, False
    top = per.most_common(2)
    uniq = len(top) == 1 or top[0][1] > top[1][1]
    return top[0][0], uniq


def main():
    chains = load_chains()
    print(f"chains: {len(chains)}")
    hist_cc, hist_cb = collections.Counter(), collections.Counter()
    lt_tail_hits = lt_n = 0
    rows, keymap = [], {}
    for uid, slot, ch in chains:
        w = SLOT_WORD.get(slot, slot)
        cand = anchors(ch)
        best = None
        for today, k in cand:
            g = k - 1
            if g < 1:
                continue
            key = (hist_cc[g], g)
            if best is None or key < best[0]:
                best = (key, today, g)
        if best:
            _, today, g = best
            hist_cc[g] += 1
            rows.append({"uid": uid, "qid": f"{uid}_v2cc",
                         "qtype": "change_count",
                         "question": f"(Today is {today.isoformat()}.) How many"
                                     f" times did I change my {w}?" + CC_NOTE,
                         "gold": g})
        best = None
        for today, k in cand:
            vals = {ch[i]["value"] for i in range(min(k, len(ch)))}
            g = len(vals)
            key = (hist_cb[g], g)
            if best is None or key < best[0]:
                best = (key, today, g)
        if best:
            _, today, g = best
            hist_cb[g] += 1
            rows.append({"uid": uid, "qid": f"{uid}_v2cb",
                         "qtype": "count_before",
                         "question": f"How many different {w} values did I "
                                     f"have before {today.isoformat()}? "
                                     f"(strictly before that date)",
                         "gold": g})
        pick = None
        lt_cand = list(cand)
        if int(hashlib.sha256(uid.encode()).hexdigest(), 16) % 4 == 0:
            tail_start = d(ch[-1]["date"])
            per = collections.Counter()
            for i, c in enumerate(ch[:-1]):
                per[c["value"]] += (d(ch[i + 1]["date"]) - d(c["date"])).days
            prior_tail = per.get(ch[-1]["value"], 0)
            best_other = max((v for k2, v in per.items()
                              if k2 != ch[-1]["value"]), default=0)
            need = best_other - prior_tail + 30
            if 0 < need < 366 * 40:
                lt_cand.append((tail_start + timedelta(days=need), len(ch)))
        for today, k in sorted(lt_cand, key=lambda t: -t[0].toordinal()):
            gv, uniq = tenure_gold(ch, today)
            if gv is None or not uniq:
                continue
            if pick is None:
                pick = (today, gv)
            if gv == ch[-1]["value"]:
                pick = (today, gv)
                break
        if pick:
            today, gv = pick
            lt_n += 1
            lt_tail_hits += (gv == ch[-1]["value"])
            rows.append({"uid": uid, "qid": f"{uid}_v2lt",
                         "qtype": "longest_tenure",
                         "question": f"(Today is {today.isoformat()}.) Which "
                                     f"{w} did I hold the longest?" + LT_NOTE,
                         "gold": gv})
        rows.append({"uid": uid, "qid": f"{uid}_v2fl",
                     "qtype": "first_vs_last",
                     "question": f"(Today is {(d(ch[-1]['date']) + timedelta(days=180)).isoformat()}.)"
                                 f" What was my first {w}, and what is my most"
                                 f" recent one?",
                     "gold": f"first: {ch[0]['value']}; most recent: "
                             f"{ch[-1]['value']}"})
        keymap[uid] = {
            "slot": slot,
            "qid_wikidata": uid.split("-", 1)[1],
            "chain_values": [c["value"] for c in ch],
            "chain_dates": [c["date"] for c in ch],
            "state_spans": [c["state_span"] for c in ch],
        }
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def top_share(h):
        tot = sum(h.values())
        return max(h.values()) / tot * 100 if tot else 0
    rep = {
        "n_chains": len(chains),
        "n_questions": len(rows),
        "qtype_counts": dict(collections.Counter(r["qtype"] for r in rows)),
        "slot_counts": dict(collections.Counter(s for _, s, _ in chains)),
        "change_count_gold_hist": dict(sorted(hist_cc.items())),
        "change_count_mode_share": round(top_share(hist_cc), 1),
        "count_before_gold_hist": dict(sorted(hist_cb.items())),
        "count_before_mode_share": round(top_share(hist_cb), 1),
        "longest_tenure_tail_share": round(lt_tail_hits / max(1, lt_n) * 100, 1),
        "criteria": {
            "mode_share_le_35": top_share(hist_cc) <= 35 and top_share(hist_cb) <= 35,
            "tail_share_gt_10": lt_tail_hits / max(1, lt_n) * 100 > 10,
        },
    }
    KEY.write_text(json.dumps({"meta": rep, "chains": keymap},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
