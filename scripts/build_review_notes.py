# -*- coding: utf-8 -*-
"""生成人工核验对照笔记:按 author 题序列出机器筛查出的候选漏检。

输入:results/chain_audit_tiers.jsonl(A/B/C 分档)、
      data/labelstudio_chainproj_map.json(item→uid、对照题标记)、
      scratchpad/author_order.json(题序与已答)。
产物:results/review_notes_author.md

纪律:对照题(catch)只标记不剧透;C 档不进笔记正文(仅计数)。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade"
    r"\c0fc4c00-9fe5-4a6c-bad9-f42ba634a283\scratchpad")

tiers = defaultdict(list)
for line in open(ROOT / "results/chain_audit_tiers.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r["tier"] in ("A", "B"):
        tiers[r["uid"]].append(r)
cmap = json.loads((ROOT / "data/labelstudio_chainproj_map.json")
                  .read_text(encoding="utf-8"))
order = json.loads((SCRATCH / "author_order.json").read_text(encoding="utf-8"))
chains = {e["uid"]: e for e in json.loads(
    (ROOT / "data/wikistate_full_ALL.json").read_text(encoding="utf-8"))}

seq, answered = order["order"], set(order["answered"])
nA = sum(1 for v in tiers.values() for x in v if x["tier"] == "A")
nB = sum(1 for v in tiers.values() for x in v if x["tier"] == "B")
hit = [c for c in seq if tiers.get(cmap.get(c, {}).get("uid"))]
todo = [c for c in seq if c not in answered]

L = ["# 人工核验对照笔记(机器筛查,author 用)", "",
     "> **这一遍的核心任务已经明确**:机器审计发现填充语料(STALE 混音)往人设",
     "> 里注入了第一人称的同槽位状态,且多为年代错乱(1799 年的议员自称软件",
     "> 工程师)。若属实,**计数型题目的金标系统性偏低**——受污染链上 smoc",
     "> 63.8 vs 干净链 91.8,且判错里 76% 是\"多数了\"。你的判定决定主口径是",
     "> 82.64 还是 ~91.75(见 results/gold_contamination_erratum_20260901.md)。", "",
     f"> 覆盖 {len(seq)} 题;机器筛出 **A 档具名漏检 {nA} 条 / B 档无名转移"
     f" {nB} 条**,分布在 {len(hit)} 道题上。", ">",
     "> **A 档**=原文点名了该槽位的另一个值但链里没有(同时污染值型与计数型"
     "金标);**B 档**=原文有一次明确状态转移但没点名值(只污染计数型)。",
     "> C 档噪声已剔除不入本表。**每条都要你自己对着原文确认**——机器只负责"
     "把可疑处指出来,判定权在你。", ">",
     "> ⚠ 标记的是对照题(有意植入错误),我不剧透具体注入项;但用了本笔记后,"
     "你自己这一遍的\"抓错率\"不能再当注意力证据用(答案键本就在你库里)。", ""]

L += ["## 一、待办题里有问题的(按你的题序)", ""]
cnt = 0
for i, cid in enumerate(seq, 1):
    if cid in answered:
        continue
    uid = cmap.get(cid, {}).get("uid")
    rows = tiers.get(uid, [])
    if not rows:
        continue
    cnt += 1
    e = chains.get(uid, {})
    catch = " ⚠对照题" if cmap.get(cid, {}).get("catch") else ""
    L.append(f"### 第 {i} 题 · {cid} · {e.get('slot', '?')}{catch}")
    L.append(f"金标链 {len(e.get('chain', []))} 行:" + " / ".join(
        f"{c['date']} {c['value']}" for c in e.get("chain", [])))
    for r in sorted(rows, key=lambda x: x["tier"]):
        L.append(f"- **{r['tier']} 档**〔{r['date']}〕值:"
                 f"{r.get('value') or r.get('scanner_value')}")
        L.append(f"  > {r['quote'][:220]}")
        L.append(f"  判读:{r['why']}")
    L.append("")
if not cnt:
    L.append("(无)")

L += ["", "## 二、已答题的回溯提醒", ""]
back = [c for c in seq if c in answered and tiers.get(
    cmap.get(c, {}).get("uid"))]
if back:
    L.append("以下你已作答的题也被筛出候选,若当时判了\"通过\"可回看:")
    for cid in back:
        uid = cmap[cid]["uid"]
        ts = tiers[uid]
        L.append(f"- {cid}({chains.get(uid, {}).get('slot', '?')}):"
                 + ";".join(f"{r['tier']}档 {r['date']} "
                            f"{(r.get('value') or '')}" for r in ts))
else:
    L.append("(已答的 8 题机器未筛出候选)")

L += ["", "## 三、对照题清单(只标位置)", "",
      "、".join(f"第 {seq.index(c) + 1} 题 {c}"
                 for c in seq if cmap.get(c, {}).get("catch")), ""]

L += ["## 四、除漏检外还要顺手看的四类错", "",
      "1. **值错**:链里的值与锚句所述不一致;",
      "2. **日期错**:链行日期与该锚句所在会话日期对不上;",
      "3. **多余行**:链里有原文根本没出现的状态;",
      "4. **顺序/取代错**:两行值被调换,或应被取代的旧值仍标为现行。", ""]

out = ROOT / "results/review_notes_author.md"
out.write_text("\n".join(L), encoding="utf-8")
print(f"written {out}  待办有问题题数={cnt} A={nA} B={nB}")
