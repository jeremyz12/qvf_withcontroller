# -*- coding: utf-8 -*-
"""批 32-A′:更正只动中间量、问题问合并结果。复用语料 C 与 v3C 店。
产物 data/wsc_v3_corrprime.jsonl(corr_longer 144 + corr_tenure ≤144)
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


def tenures(rows, today):
    """每行时长(天),末行到 today。"""
    out = []
    for i, r in enumerate(rows):
        end = pd(rows[i + 1]["date"]) if i + 1 < len(rows) else today
        out.append((end - pd(r["date"])).days)
    return out


def main():
    rng = random.Random(3232)
    ch = json.loads((ROOT / "data/v3_corrected_chains.json").read_text(encoding="utf-8"))
    data = {e["uid"]: e for e in json.loads(
        (ROOT / "data/wikistate_v3C.json").read_text(encoding="utf-8"))}
    qs = []
    flips = 0
    for uid, rows in ch.items():
        slot = SLOTN[data[uid]["slot"]]
        r = next(i for i, x in enumerate(rows) if "corrected_from" in x)
        today = pd(rows[-1]["date"]) + timedelta(days=400)
        # 更正后 / 更正前(把 r 行日期换回原值)两套时长
        new_t = tenures(rows, today)
        old_rows = [dict(x) for x in rows]
        old_rows[r]["date"] = old_rows[r]["corrected_from"]
        if "-00" in old_rows[r]["date"]:
            old_rows[r]["date"] = old_rows[r]["date"][:4] + "-01-01"
        old_t = tenures(old_rows, today)
        # corr_longer:选 Y 使答案翻转;否则选差异 ≥20% 的
        cands = [k for k in range(len(rows)) if k != r]
        flip_k = [k for k in cands if (new_t[r] > new_t[k]) != (old_t[r] > old_t[k])]
        sep_k = [k for k in cands if abs(new_t[r] - new_t[k]) >= 0.2 * max(new_t[r], new_t[k], 1)]
        pool = flip_k or sep_k or cands
        k = rng.choice(pool)
        gold = rows[r]["value"] if new_t[r] > new_t[k] else rows[k]["value"]
        qs.append({"uid": uid, "qid": f"{uid}_v3cl", "qtype": "corr_longer",
                   "flip": bool(flip_k), "old_gold": (rows[r]["value"] if old_t[r] > old_t[k] else rows[k]["value"]),
                   "question": (f"(Today is {fd(today)}.) Which did I hold for LONGER: my time at "
                                f"{rows[r]['value']} or my time at {rows[k]['value']}? Use the "
                                f"corrected dates where I corrected myself, and answer with the "
                                f"{slot} value that lasted longer."),
                   "gold": gold})
        flips += bool(flip_k)
        # corr_tenure:仅当整年四舍五入不落在 ±0.15 边界
        yrs = new_t[r] / 365.25
        if abs((yrs % 1) - 0.5) > 0.15:
            qs.append({"uid": uid, "qid": f"{uid}_v3ct", "qtype": "corr_tenure",
                       "old_gold": str(round(old_t[r] / 365.25)),
                       "question": (f"(Today is {fd(today)}.) For how many whole years (rounded to "
                                    f"the nearest year) was I at {rows[r]['value']}? Use the corrected "
                                    f"start date where I corrected myself. Answer with a number."),
                       "gold": str(round(yrs))})
    with open(ROOT / "data/wsc_v3_corrprime.jsonl", "w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"题 {len(qs)}:{Counter(q['qtype'] for q in qs)};corr_longer 翻转子集 {flips}/144")
    print("corr_tenure 金标分布:", Counter(q["gold"] for q in qs if q["qtype"] == "corr_tenure"))
    diff = sum(1 for q in qs if q["qtype"] == "corr_tenure" and q["gold"] != q["old_gold"])
    print(f"corr_tenure 中更正前后金标不同的:{diff}")


if __name__ == "__main__":
    main()
