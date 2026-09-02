# -*- coding: utf-8 -*-
"""批 32-A:语料 C = v2.4 + 每链一处更正会话;派生 correction_date /
correction_count / scoped_count 三型 432 题(每型 144)。
产物 data/wikistate_v3C.json、data/wsc_v3_new.jsonl、data/v3_corrected_chains.json
"""
import json
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLOTN = {"employer": "employer", "position": "position",
         "residence": "place of residence", "team": "team"}


def pd(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, max(m, 1), max(d, 1))


def fd(dt):
    return dt.strftime("%Y-%m-%d")


def main():
    rng = random.Random(32)
    data = json.loads((ROOT / "data/wikistate_full_ALL_v24.json")
                      .read_text(encoding="utf-8"))
    qs, chains_out = [], {}
    for e in data:
        ch = [dict(c) for c in e["chain"]]
        n = len(ch)
        slot = SLOTN[e["slot"]]
        r = rng.randrange(1, n)
        old = pd(ch[r]["date"])
        prev = pd(ch[r - 1]["date"])
        nxt = pd(ch[r + 1]["date"]) if r + 1 < n else old + timedelta(days=3650)
        shift = timedelta(days=183)
        new = old + shift if old + shift < nxt else old - shift
        if new <= prev:
            new = old + timedelta(days=min(60, max(1, (nxt - old).days // 2)))
        ch[r]["date"] = fd(new)
        ch[r]["corrected_from"] = fd(old)
        ins = old + timedelta(days=45)
        if ins >= nxt:
            ins = old + timedelta(days=1)
        corr = {"chain_index": f"corr{r}", "date": fd(ins), "turns": [
            {"role": "user", "content":
                f"Quick correction on something I mentioned before - I actually "
                f"started at {ch[r]['value']} on {fd(new)}, not {fd(old)}. "
                f"I had the date mixed up."},
            {"role": "assistant", "content":
                f"Thanks for the correction - noted: {ch[r]['value']} "
                f"from {fd(new)}."}]}
        e["sessions"] = sorted(e["sessions"] + [corr], key=lambda s: s["date"])
        chains_out[e["uid"]] = ch
        today = fd(pd(ch[-1]["date"]) + timedelta(days=400))
        qs.append({"uid": e["uid"], "qid": f"{e['uid']}_v3cd",
                   "qtype": "correction_date",
                   "question": (f"(Today is {today}.) On what date did I start at "
                                f"{ch[r]['value']}? Answer with the exact date, "
                                f"taking into account any correction I made."),
                   "gold": fd(new)})
        lo, hi = sorted([old, new])
        boundary = fd(lo + (hi - lo) / 2)
        gold_cnt = sum(1 for c in ch if pd(c["date"]) < pd(boundary))
        qs.append({"uid": e["uid"], "qid": f"{e['uid']}_v3cc",
                   "qtype": "correction_count",
                   "question": (f"(Today is {today}.) How many different {slot} "
                                f"values had I held before {boundary}? Count only "
                                f"states that had already started by that date, "
                                f"using corrected dates where I corrected myself."),
                   "gold": str(gold_cnt)})
        i = rng.randrange(0, n - 2) if n > 3 else 0
        j = rng.randrange(i + 2, n)
        inclusive = rng.random() < 0.5
        bound = ("up to and INCLUDING when I started at" if inclusive
                 else "up to but NOT including when I started at")
        qs.append({"uid": e["uid"], "qid": f"{e['uid']}_v3sc",
                   "qtype": "scoped_count",
                   "question": (f"(Today is {today}.) Counting from when I started "
                                f"at {ch[i]['value']} {bound} {ch[j]['value']}, "
                                f"how many different {slot} values did I hold? "
                                f"Give a number."),
                   "gold": str(j - i + (1 if inclusive else 0))})
    (ROOT / "data/wikistate_v3C.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/v3_corrected_chains.json").write_text(
        json.dumps(chains_out, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(ROOT / "data/wsc_v3_new.jsonl", "w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"语料 C 写出;题 {len(qs)}:{Counter(q['qtype'] for q in qs)}")
    print("correction_count 金标分布:",
          Counter(q["gold"] for q in qs if q["qtype"] == "correction_count"))
    print("scoped_count 金标分布:",
          Counter(q["gold"] for q in qs if q["qtype"] == "scoped_count"))


if __name__ == "__main__":
    main()
