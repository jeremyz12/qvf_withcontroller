# -*- coding: utf-8 -*-
"""批 22 结算:四店审计(卡数/重复度/杂卡率)+ 六臂配对判据。
预注册 opt_batch22_prereg。用法: python scripts/opt_batch22_verdict_calc.py
"""
import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from complex_query_arm import _mem_dates, _norm  # noqa: E402

ROOT = Path(r"D:\ZZL_cluade")
UIDS = [l.strip() for l in open(ROOT / "data/b22_uids.txt", encoding="utf-8")
        if l.strip()]
entries = {e["uid"]: e for e in json.loads(
    (ROOT / "data/wikistate_full_ALL.json").read_text(encoding="utf-8"))
    if e["uid"] in set(UIDS)}


def sim(a, b):
    a, b = _norm(str(a)), _norm(str(b))
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / max(1, min(len(sa), len(sb))) >= 0.7


def audit(cards_dir):
    """主槽卡:总数/唯一(值,日期)重复度/杂卡率(值不匹配任何金链值)。"""
    tot = stray = dup = allc = 0
    for uid in UIDS:
        p = Path(cards_dir) / f"{uid}.json"
        if not p.exists():
            continue
        recs = json.loads(p.read_text(encoding="utf-8")).get("records", [])
        allc += len(recs)
        e = entries[uid]
        md = _mem_dates(e)
        gvals = [str(r.get("value", "")) for r in e.get("chain", [])]
        slot = (e.get("slot") or "").lower()
        seen = set()
        for r in recs:
            sc = (r.get("slot_class") or "").lower()
            ss = (r.get("slot") or "").lower()
            if slot not in sc and slot not in ss:
                continue
            tot += 1
            key = (_norm(r.get("value", "")),
                   r.get("stated_date") or md.get(r.get("source_memory_id", ""), ""))
            if key in seen:
                dup += 1
            seen.add(key)
            if not any(sim(r.get("value", ""), g) for g in gvals):
                stray += 1
    return dict(cards=allc, main=tot, dup=dup, stray=stray)


def mcn(x, y, qs):
    b = sum(1 for q in qs if x[q]["judge_correct"] and not y[q]["judge_correct"])
    c = sum(1 for q in qs if not x[q]["judge_correct"] and y[q]["judge_correct"])
    n = b + c
    return b, c, (min(1.0, sum(comb(n, i) for i in range(min(b, c) + 1))
                      / 2 ** n * 2) if n else 1.0)


def load(p):
    return {r["question_id"]: r for r in
            (json.loads(l) for l in open(ROOT / p, encoding="utf-8"))}


print("== 店审计(15 店) ==")
AU = {}
for arm in ("a1", "t1", "t2", "s1"):
    a = audit(ROOT / f"results/wt_cards_b22_{arm}")
    AU[arm] = a
    print(f"{arm.upper()}: 全卡 {a['cards']} | 主槽 {a['main']} "
          f"(重复 {a['dup']}) | 杂卡 {a['stray']} "
          f"({a['stray']/max(1,a['main'])*100:.1f}%)")
a = audit(ROOT / "results/wt_cards_v42")
print(f"存档 v42: 全卡 {a['cards']} | 主槽 {a['main']} (重复 {a['dup']}) "
      f"| 杂卡 {a['stray']} ({a['stray']/max(1,a['main'])*100:.1f}%)")

print("\n== 六臂 60 题(A1 为配对基线) ==")
arms = {}
for arm in ("a1", "t1", "t2", "s1"):
    for path_ in ("smoc", "compile"):
        f = ROOT / f"results/b22_{arm}_{path_}.jsonl"
        if f.exists():
            arms[(arm, path_)] = load(f"results/b22_{arm}_{path_}.jsonl")
for path_ in ("smoc", "compile"):
    base = arms.get(("a1", path_))
    if not base:
        continue
    qs = sorted(base)
    a0 = sum(1 for q in qs if base[q]["judge_correct"]) / len(qs) * 100
    print(f"[{path_}] A1 = {a0:.2f} (n={len(qs)})")
    for arm in ("t1", "t2", "s1"):
        m = arms.get((arm, path_))
        if not m:
            print(f"    {arm.upper()}: 未就绪")
            continue
        common = sorted(set(base) & set(m))
        acc = sum(1 for q in common if m[q]["judge_correct"]) / len(common) * 100
        b, c, p = mcn(base, m, common)
        print(f"    {arm.upper()}: {acc:.2f} (Δ{acc-a0:+.2f}) | "
              f"b={b} c={c} p={p:.3f}")

print("\n== 判据速览 ==")
s_ok = AU["s1"]["stray"] <= 0.5 * AU["a1"]["stray"]
print(f"S1 杂卡减半({AU['s1']['stray']} vs 0.5x{AU['a1']['stray']}): "
      f"{'过' if s_ok else '不过'}(准确率护栏另见上表)")
print(f"T2 卡数 vs T1(去重生效?): {AU['t2']['main']} vs {AU['t1']['main']} "
      f"主槽;重复 {AU['t2']['dup']} vs {AU['t1']['dup']}")
