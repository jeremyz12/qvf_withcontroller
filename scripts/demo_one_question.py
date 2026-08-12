# -*- coding: utf-8 -*-
"""教学演示:把一道题在 QVF(写入时路径)里的全过程逐步打印出来。

用法:
  python scripts/demo_one_question.py                # 默认:问"现在"
  python scripts/demo_one_question.py dim4           # 问"那一天"
  python scripts/demo_one_question.py dim5           # 问"怎么变的"
  python scripts/demo_one_question.py dim2           # 陷阱题(预设过时状态)
可加第二个参数选条目序号(默认 7)。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic
from scripts.wt_qvf_prototype import (FOCUS_PROMPT, QueryFocusMini,
                                      READER_SYSTEM, _norm, _slot_match)

DIM = sys.argv[1] if len(sys.argv) > 1 else "dim1"
IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 7

items = json.load(open(r"data/wikistate_full.json", encoding="utf-8"))
it = items[IDX]
uid = it["uid"]
dim_key = next(k for k in it["probing_queries"] if k.startswith(DIM))
q = it["probing_queries"][dim_key]
client = anthropic.Anthropic()

print("=" * 72)
print(f"条目: {uid}   问题类型: {dim_key}")
print(f"问题: {q['q']}")
print("=" * 72)

# ── 第 1 步:mini 聚焦(一次小 LLM 调用)──
resp = client.messages.parse(model="claude-haiku-4-5", max_tokens=400,
                             system=FOCUS_PROMPT,
                             messages=[{"role": "user", "content": q["q"]}],
                             output_format=QueryFocusMini)
f = resp.parsed_output
print("\n【第1步 · 聚焦】LLM 把问题读成了这样:")
print(f"  关注的属性(slot) = {f.slot}")
print(f"  时间语义(scope)  = {f.scope}")
print(f"  问的日期          = {f.point_date or '(无)'}")
print(f"  题面预设的值      = {f.presupposed_value or '(无)'}")

# ── 第 2 步:打开卡片库,串链(纯代码,零 token)──
recs = json.loads((Path(r"results/wt_cards") / f"{uid}.json").read_text(encoding="utf-8"))["records"]
print(f"\n【第2步 · 卡片库】这个条目入库时抽了 {len(recs)} 张卡(闲聊也会混进一些)")
hits = [r for r in recs if _slot_match(r.get("slot", ""), f.slot)]
hits = sorted(hits, key=lambda r: r.get("stated_date") or "")
seen = set()
chain = []
for r in hits:
    v = _norm(r.get("value", ""))
    if v and v not in seen:
        seen.add(v)
        chain.append(r)
print(f"  与「{f.slot}」匹配并串成链的有 {len(chain)} 张:")
for r in chain:
    print(f"    {r.get('stated_date','????-??-??')}  {r.get('value','')[:60]}")

# ── 第 3 步:代码裁决(看清楚:就是 if/else 和一个循环)──
print("\n【第3步 · 裁决】代码按时间语义做决定:")
note = ""
if f.scope == "point_in_time" and f.point_date:
    valid = [r for r in chain if (r.get("stated_date") or "") <= f.point_date]
    pick = valid[-1] if valid else None
    print(f"  规则=区间算术: 找「日期 ≤ {f.point_date}」的最后一张卡")
    if pick:
        note = (f"[记忆模块核验: 于 {f.point_date}, 用户的 {f.slot} 为 "
                f"{pick['value']} (自 {pick.get('stated_date')} 起生效). 这就是答案.]")
elif f.scope == "trajectory":
    print("  规则=全链按序, 一张不删")
    seqs = " -> ".join(f"{r.get('value','')}({r.get('stated_date','')})" for r in chain)
    note = f"[记忆模块核验: 完整演化历史: {seqs}]"
else:
    pick = chain[-1] if chain else None
    print("  规则=问现在 → 取链尾为现任, 其余标记过时")
    if pick:
        note = (f"[记忆模块核验: 用户当前 {f.slot} = {pick['value']} "
                f"(自 {pick.get('stated_date')} 起). 此前状态均已卸任.]")
    if f.presupposed_value:
        note += (f" [注意: 题目预设的「{f.presupposed_value}」已过时, "
                 f"请先纠正这一前提再回答.]")
print(f"  生成的注记 = {note[:160]}")

# ── 第 4 步:拼最终输入, 读者作答 ──
today = it["chain"][-1]["date"]
excerpts = []
for r in chain[-3:]:
    excerpts.append(f"[{r.get('stated_date','')}] {r.get('source_span','')[:150]}")
final_input = ("EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:\n"
               + "\n".join(excerpts) + f"\n{note}\n\nTODAY'S DATE: {today}\n\n"
               + f"USER'S NEW MESSAGE: {q['q']}")
print("\n【第4步 · 投喂】读者实际看到的全文:")
print("-" * 60)
print(final_input[:900])
print("-" * 60)
r2 = client.messages.create(model="claude-haiku-4-5", max_tokens=300,
                            temperature=0.0, system=READER_SYSTEM,
                            messages=[{"role": "user", "content": final_input}])
ans = "".join(b.text for b in r2.content if b.type == "text")
print(f"\n【第5步 · 回答】{ans}")
print(f"\n【对照 · 金答案】{str(q['gold'])[:200]}")
print("\n(注: 教学版为可读性做了简化——正式版的链来自并查集连通分量、"
      "会做检回摘录的删除、含四物种分支; 逻辑骨架与此一致)")
