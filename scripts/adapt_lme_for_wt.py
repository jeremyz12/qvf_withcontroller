# -*- coding: utf-8 -*-
"""LongMemEval → chain-schema 适配器(wt-QVF 流水线用)。

默认取 temporal-reasoning 133 问;官方短金答案原样保留(ClaudeJudge 按
LME 官方协议判分)。chain 末日期设为 question_date 减一个月,使加载器
推出的查询日期与官方 question_date 对齐。"""
import json
import sys
from pathlib import Path

SRC = Path(r"data/longmemeval_s_cleaned.json")
QTYPE = sys.argv[1] if len(sys.argv) > 1 else "temporal-reasoning"
OUT = Path(rf"data/lme_{QTYPE.replace('-', '_')}_wt.json")


def norm_date(s: str) -> str:
    s = (s or "").split(" ")[0].replace("/", "-")
    parts = s.split("-")
    if len(parts) == 3:
        y, m, d = parts
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return "2023-01-01"


def minus_one_month(s: str) -> str:
    y, m, d = (int(x) for x in s.split("-"))
    m -= 1
    if m < 1:
        y, m = y - 1, 12
    return f"{y}-{m:02d}-{min(d, 28):02d}"


data = json.loads(SRC.read_text(encoding="utf-8"))
items = [x for x in data if x.get("question_type") == QTYPE]
out = []
for it in items:
    qd = norm_date(it.get("question_date", ""))
    sessions = []
    dates = it.get("haystack_dates", [])
    for i, sess in enumerate(it.get("haystack_sessions", [])):
        turns = [f"{t.get('role', '?')}: {t.get('content', '')}"[:3500] for t in sess]
        sessions.append({"date": norm_date(dates[i]) if i < len(dates) else "undated",
                         "turns": turns, "chain_index": None})
    out.append({
        "uid": it["question_id"], "type": f"LME-{QTYPE}", "slot": "user state",
        "chain": [{"value": "", "date": minus_one_month(qd), "state_span": ""}],
        "sessions": sessions,
        "probing_queries": {"q1": {"q": it["question"], "gold": str(it.get("answer", ""))}},
    })
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"adapted {len(out)} {QTYPE} questions -> {OUT}")
