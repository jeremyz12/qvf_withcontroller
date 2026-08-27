# -*- coding: utf-8 -*-
"""批 18 诊断(零 API):净链库 change_count 执行器错题的逐链对齐归因。
重建冻结执行器链(_select_pool_frozen + _chain on wt_cards_v42_mf),与金链
(entry['chain'])对齐,把多数/少数的转移分类:
  rewrite   同值异写:执行器链中相邻两值,金链视为同一状态(规范化后相似)
  stray     杂卡残留:执行器链值在金链值集中不存在
  reorder   A,B,A 型:金链无此回returns形态(插值劈开同状态)
  window    末段越界:执行器链含金链末日期之后的行
  other     未归类
用法: python scripts/opt_batch18_diagnose.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from complex_query_arm import _chain, _mem_dates, _select_pool_frozen, _norm  # noqa: E402
from repro_batch2 import VOLS, ROOT  # noqa: E402

entries = {}
for v in VOLS:
    for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
        entries.setdefault(e["uid"], e)

smoc = {r["question_id"]: r for r in
        (json.loads(l) for l in open(ROOT / "results/wsc_v2_smoc.jsonl",
                                     encoding="utf-8"))}
mf = {r["question_id"]: r for r in
      (json.loads(l) for l in open(ROOT / "results/wsc_v2_countfam_mf.jsonl",
                                   encoding="utf-8"))}
rep = json.load(open(ROOT / "results/mf_v42_report.json", encoding="utf-8"))
removed = {row["uid"]: row["removed"] for row in rep["rows"]}
CARDS = ROOT / "results/wt_cards_v42_mf"


def num(s):
    m = re.search(r"-?\d+", str(s))
    return int(m.group()) if m else None


def sim(a, b):
    """粗相似:一方是另一方子串,或去空格后字符重叠率>0.7。"""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    sa, sb = set(a.split()), set(b.split())
    inter = len(sa & sb)
    return inter / max(1, min(len(sa), len(sb))) >= 0.7


cases = []
for qid, r in mf.items():
    if r["question_type"] != "change_count" or r["judge_correct"]:
        continue
    uid = r["uid"]
    if removed.get(uid, 0) > 0:
        continue
    entry = entries[uid]
    recs = json.loads((CARDS / f"{uid}.json").read_text(
        encoding="utf-8")).get("records", [])
    md = _mem_dates(entry)
    pool = _select_pool_frozen(recs, entry.get("slot", ""), md, r["question"])
    ch = _chain(pool, md)
    exec_n = len(ch) - 1
    gold_n = num(r["gold_answer"])
    ans_n = num(r["answer"])
    gold_chain = entry.get("chain", [])
    gvals = [_norm(str(s.get("value", ""))) for s in gold_chain]
    gdates = [str(s.get("date", "")) for s in gold_chain]
    evals = [_norm(c.get("value", "")) for c in ch]
    # 分类
    tags = []
    for i in range(1, len(ch)):
        a, b = evals[i - 1], evals[i]
        if sim(a, b) and a != b:
            tags.append("rewrite")
    for v in evals:
        if not any(sim(v, g) for g in gvals):
            tags.append("stray")
    for i in range(2, len(evals)):
        if evals[i] == evals[i - 2] and evals[i] != evals[i - 1]:
            # A,B,A:金链同位置无此形态才算
            gseq = "|".join(gvals)
            if f"{evals[i]}|{evals[i-1]}|{evals[i]}" not in gseq:
                tags.append("reorder")
    from complex_query_arm import _rec_date
    if gdates and any((_rec_date(c, md) or "") > max(gdates) for c in ch):
        tags.append("window")
    tag = tags[0] if tags else "other"
    cases.append(dict(uid=uid, gold=gold_n, exec_len=exec_n, answered=ans_n,
                      tag=tag, all_tags=sorted(set(tags)),
                      exec_vals=evals[:8], gold_vals=gvals[:8]))

print(f"净链库 change_count 执行器错题: {len(cases)} 例")
print("主分类:", dict(Counter(c["tag"] for c in cases)))
print("全标签分布:", dict(Counter(t for c in cases for t in c["all_tags"])))
print("执行器链长-1 vs 答案数字一致:",
      sum(1 for c in cases if c["exec_len"] == c["answered"]), "/", len(cases))
print()
for c in cases[:14]:
    print(f"[{c['uid']}] gold={c['gold']} exec={c['exec_len']} "
          f"ans={c['answered']} tag={c['tag']} {c['all_tags']}")
    print(f"    exec: {c['exec_vals']}")
    print(f"    gold: {c['gold_vals']}")
