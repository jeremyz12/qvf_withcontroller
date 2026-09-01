# -*- coding: utf-8 -*-
"""批 31-B:语料 v2.1 净化——从填充会话手术删除已确认的同槽位断言句。

输入: results/contamination_confirmed_20260901.json
       [{uid, quote, value, ...}](Fable 复审确认的 KEEP_A/KEEP_B + 新发现)
输出: data/wikistate_full_ALL_v21.json(v2.0 原档不动)
双闸: ①542 条链锚逐字仍在;②删除句逐条确认已移除;违闸即退出非零。
工艺: 定位包含引文的用户轮 → 仅删除该断言句(按句号边界扩展到完整句),
      保留该轮其余文本;若整轮只剩空白则删轮。全部编辑逐条留痕。
用法: python scripts/build_corpus_v21.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "results/contamination_confirmed_20260901.json"
SRC = ROOT / "data/wikistate_full_ALL.json"
DST = ROOT / "data/wikistate_full_ALL_v21.json"
LOG = ROOT / "results/corpus_v21_edits.jsonl"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def expand_sentence(text: str, start: int, end: int) -> tuple:
    """把 [start,end) 扩展到完整句边界(句号/问叹号/换行)。"""
    s = start
    while s > 0 and text[s - 1] not in ".!?\n":
        s -= 1
    e = end
    while e < len(text) and text[e] not in ".!?\n":
        e += 1
    if e < len(text):
        e += 1
    return s, e


def unwrap(t):
    """取出一轮的可编辑正文与回写器。

    本语料的 turn 有三种形态:dict、str({'role':..,'content':..}) 的字符串
    (批 28 格式伪影的根源)、裸字符串。必须按形态回写,否则动刀会切穿
    序列化边界毁掉语料。返回 (role, body, rebuild) ;body 为 None 表示跳过。
    """
    if isinstance(t, dict):
        return t.get("role", "user"), t.get("content"), \
            (lambda new, _t=t: {**_t, "content": new})
    s = str(t)
    # 本语料 45% 的 dict 型 turn 在 400 字符处被截断 → 非法字面量,
    # ast 解析必失败,故用正则拆壳(闭合与截断两种形态都要能回写)。
    m = re.match(r"^(\{'role':\s*'[a-z]+',\s*'content':\s*)([\"'])(.*)$",
                 s, re.S)
    if m:
        head, q, rest = m.group(1), m.group(2), m.group(3)
        closed = rest.endswith(q + "}")
        body = rest[:-2] if closed else rest
        role = re.search(r"'role':\s*'([a-z]+)'", head).group(1)
        tail = (q + "}") if closed else ""
        return role, body, (lambda new, h=head, _q=q, tl=tail:
                            f"{h}{_q}{new}{tl}")
    return "user", s, (lambda new: new)


def find_span(text: str, quote: str):
    """宽空白匹配:返回原文中引文的 (start,end),找不到返回 None。"""
    pat = re.escape(quote.strip())
    pat = re.sub(r"\\\s+", r"\\s+", pat).replace(r"\ ", r"\s+")
    m = re.search(pat, text, re.IGNORECASE)
    return (m.start(), m.end()) if m else None


def main() -> int:
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    data = json.loads(SRC.read_text(encoding="utf-8"))
    by_uid = {}
    for c in conf:
        by_uid.setdefault(c["uid"], []).append(c)
    log = open(LOG, "w", encoding="utf-8")
    n_edit = n_fail = 0
    for e in data:
        for c in by_uid.get(e["uid"], []):
            q = c["quote"]
            hit = False
            for s in e.get("sessions", []):
                turns = s.get("turns", [])
                for i, t in enumerate(turns):
                    role, body, rebuild = unwrap(t)
                    if role != "user" or not isinstance(body, str):
                        continue
                    span = find_span(body, q)
                    if not span:
                        continue
                    a, b = expand_sentence(body, *span)
                    removed = body[a:b]
                    newbody = re.sub(r"  +", " ",
                                     (body[:a] + body[b:]).strip())
                    if newbody:
                        turns[i] = rebuild(newbody)
                    else:
                        turns.pop(i)
                    log.write(json.dumps({
                        "uid": e["uid"], "session": s.get("date"),
                        "removed": removed, "quote": q},
                        ensure_ascii=False) + "\n")
                    n_edit += 1
                    hit = True
                    break
                if hit:
                    break
            if not hit:
                print(f"FAIL 未定位: {e['uid']} :: {q[:60]}", flush=True)
                n_fail += 1
    # 闸 1:全部链锚逐字仍在
    bad = 0
    for e in data:
        blob = norm(json.dumps(e.get("sessions", []), ensure_ascii=False))
        for c in e["chain"]:
            if norm(c["state_span"]) not in blob:
                print(f"闸1违例 锚丢失: {e['uid']} :: {c['state_span'][:50]}")
                bad += 1
    # 闸 2:确认句已全部移除
    for e in data:
        blob = norm(json.dumps(e.get("sessions", []), ensure_ascii=False))
        for c in by_uid.get(e["uid"], []):
            if norm(c["quote"])[:60] in blob:
                print(f"闸2违例 断言残留: {e['uid']} :: {c['quote'][:50]}")
                bad += 1
    if bad or n_fail:
        print(f"ABORT: 闸违例 {bad},未定位 {n_fail} — 不写出 v2.1")
        return 1
    DST.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"v2.1 写出 {DST} 编辑 {n_edit} 句,闸全过(锚 "
          f"{sum(len(e['chain']) for e in data)} 条完好)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
