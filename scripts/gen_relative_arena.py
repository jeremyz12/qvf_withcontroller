# -*- coding: utf-8 -*-
"""批 21 变换生成器:WikiState 相对日期叙述变体(确定性,零 LLM)。

对采样店的每条链宣告:宣告会话日期后移 Δ,锚点句改写为
"{RelPhrase}, {原句去当日词}"——短语集全部**精确可逆**(解析器按同一
日历算术还原原日期);金链(chain.date)不动。产物:
data/wikistate_rel30.json + 变换报告(锚点逐字核验)。
用法: python scripts/gen_relative_arena.py
"""
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade\scripts")
sys.path.insert(0, r"D:\ZZL_cluade")
from repro_batch2 import VOLS, ROOT  # noqa: E402

rng = random.Random(21)


def pd(s):
    try:
        y, m, d = (int(x) for x in str(s).split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None  # 部分日期(如 00 月)不可整历,该宣告跳过不变换


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, 28 if m == 2 else 30 if m in (4, 6, 9, 11)
                          else 31))


# 短语 -> 会话日期前移函数(解析器用同表还原:D = shift(D'))
PHRASES = [
    ("Two months ago", lambda d: add_months(d, 2)),      # D' = D + 2mo
    ("Three weeks ago", lambda d: d.fromordinal(d.toordinal() + 21)),
    ("Last month", lambda d: add_months(d, 1)),
    ("A year ago", lambda d: add_months(d, 12)),
]
STRIP = [" this morning", " this afternoon", " this evening", " today",
         "this morning ", "today "]

entries = {}
for v in VOLS:
    for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
        entries.setdefault(e["uid"], e)

uids = sorted({json.loads(l)["uid"] for l in
               open(ROOT / "results/wsc_v2_smoc.jsonl", encoding="utf-8")})
pick = rng.sample(uids, 30)

out, report = [], {"stores": 0, "decls": 0, "rewritten": 0,
                   "anchor_ok": 0, "skipped": []}
for uid in pick:
    e = json.loads(json.dumps(entries[uid]))  # deep copy
    report["stores"] += 1
    for k, row in enumerate(e.get("chain", [])):
        span = row.get("state_span") or ""
        if not span:
            continue
        report["decls"] += 1
        # 找宣告会话:chain_index==k 且含锚点句
        sess = next((s for s in e["sessions"]
                     if s.get("chain_index") == k
                     and any(span in str(t) for t in s.get("turns", []))),
                    None)
        if sess is None:
            report["skipped"].append(f"{uid}#k{k}:no-session")
            continue
        phrase, fwd = PHRASES[k % len(PHRASES)]
        d0 = pd(row["date"])
        if d0 is None:
            report["skipped"].append(f"{uid}#k{k}:partial-date")
            continue
        d_new = fwd(d0)
        new_span = span
        for st in STRIP:
            if st in new_span:
                new_span = new_span.replace(st, "", 1)
                break
        new_span = f"{phrase}, {new_span[0].lower()}{new_span[1:]}"
        sess["turns"] = [
            (str(t).replace(span, new_span) if span in str(t) else t)
            for t in sess["turns"]]
        sess["date"] = d_new.isoformat()
        row["state_span"] = new_span   # 锚点句同步(逐字纪律对变换后语料)
        report["rewritten"] += 1
        if any(new_span in str(t) for t in sess["turns"]):
            report["anchor_ok"] += 1
    out.append(e)

(ROOT / "data/wikistate_rel30.json").write_text(
    json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "skipped"},
                 ensure_ascii=False))
print("skipped:", len(report["skipped"]), report["skipped"][:5])
assert report["rewritten"] == report["anchor_ok"], "锚点逐字核验未全过"
with open(ROOT / "data/wikistate_rel30_uids.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(pick))
print(f"stores -> data/wikistate_rel30.json ({len(out)}); uids 清单已存")
