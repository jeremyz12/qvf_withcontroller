# -*- coding: utf-8 -*-
"""批 32-B:语料 D = v2.4 + 每链 6 个第三人称同槽位干扰会话(金标不变)。
干扰值取自同槽位其他人设的真实链值;固定模板,永远第三人称。
产物 data/wikistate_v3D.json、results/v3D_distractor_log.jsonl
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["Dana", "Priya", "Marcus", "Elena", "Tomas", "Yuki", "Sofia", "Liam",
         "Aisha", "Noah", "Mei", "Jonas", "Fatima", "Owen", "Ines", "Kofi",
         "Hana", "Diego", "Zara", "Felix"]
REL = ["cousin", "sister", "brother", "old roommate", "neighbor", "coworker",
       "friend from college", "former classmate"]
T = {
    "employer": [
        "My {rel} {n} just started at {v} - {n} seems really excited about it.",
        "Ran into {n}, a {rel} of mine; {n} works at {v} now.",
        "{n} (my {rel}) got an offer from {v} and accepted it last week."],
    "position": [
        "My {rel} {n} was just appointed {v}.",
        "{n}, a {rel} of mine, now holds the position of {v}.",
        "Heard that {n} (my {rel}) became {v} this year."],
    "residence": [
        "My {rel} {n} moved to {v} last month.",
        "{n}, a {rel} of mine, is now living in {v}.",
        "My {rel} {n} finally settled in {v} after a long search."],
    "team": [
        "My {rel} {n} signed with {v} this season.",
        "{n}, a {rel} of mine, is now riding for {v}.",
        "Heard my {rel} {n} joined {v} - {n} is thrilled."],
}
ASSIST = ["That is great news for {n}! Anything you would like to plan around it?",
          "Nice - sounds like a big step for {n}. Let me know if you want gift ideas.",
          "Good for {n}! Want help drafting a congratulations message?"]


def pd(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, max(m, 1), max(d, 1))


def main():
    rng = random.Random(322)
    data = json.loads((ROOT / "data/wikistate_full_ALL_v24.json")
                      .read_text(encoding="utf-8"))
    by_slot = {}
    for e in data:
        by_slot.setdefault(e["slot"], []).append(e)
    log = open(ROOT / "results/v3D_distractor_log.jsonl", "w", encoding="utf-8")
    added = 0
    for e in data:
        own = {c["value"] for c in e["chain"]}
        pool = [c["value"] for o in by_slot[e["slot"]] if o["uid"] != e["uid"]
                for c in o["chain"] if c["value"] not in own]
        vals = rng.sample(pool, min(6, len(pool)))
        d0, d1 = pd(e["sessions"][0]["date"]), pd(e["sessions"][-1]["date"])
        taken = {s["date"] for s in e["sessions"]}
        new = []
        for v in vals:
            dt = None
            for _ in range(20):
                cand = (d0 + timedelta(days=rng.randrange(max(1, (d1 - d0).days)))
                        ).strftime("%Y-%m-%d")
                if cand not in taken:
                    dt = cand
                    break
            if dt is None:
                continue
            taken.add(dt)
            n, rel = rng.choice(NAMES), rng.choice(REL)
            u = rng.choice(T[e["slot"]]).format(rel=rel, n=n, v=v)
            new.append({"chain_index": None, "date": dt, "turns": [
                {"role": "user", "content": u},
                {"role": "assistant", "content": rng.choice(ASSIST).format(n=n)}]})
            log.write(json.dumps({"uid": e["uid"], "date": dt, "value": v,
                                  "text": u}, ensure_ascii=False) + "\n")
            added += 1
        e["sessions"] = sorted(e["sessions"] + new, key=lambda s: s["date"])
    (ROOT / "data/wikistate_v3D.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"语料 D 写出:{len(data)} 链,共加 {added} 个第三人称干扰会话")


if __name__ == "__main__":
    main()
