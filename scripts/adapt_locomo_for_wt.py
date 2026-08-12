# -*- coding: utf-8 -*-
"""LoCoMo → chain-schema 适配器(wt 无害性对照用)。

每段对话一个条目;问题取类别 4(单跳)与 5(对抗/不可答),每类每对话
最多 15 问,镜像既有读取时 QVF 的 LoCoMo-adv / single 两格。对抗题
gold 标注为不可答,判官要求答案不得编造。"""
import json
from pathlib import Path

SRC = Path(r"data/locomo10.json")
OUT = Path(r"data/locomo_wt.json")
PER_CAT = 15

data = json.loads(SRC.read_text(encoding="utf-8"))
out = []
for conv_i, it in enumerate(data):
    conv = it["conversation"]
    sessions = []
    si = 1
    while f"session_{si}" in conv:
        raw_date = conv.get(f"session_{si}_date_time", "") or ""
        date = raw_date.split(" ")[-1] if raw_date else "undated"
        try:
            from datetime import datetime
            date = datetime.strptime(raw_date, "%I:%M %p on %d %B, %Y").strftime("%Y-%m-%d")
        except Exception:
            pass
        turns = [f"{t.get('speaker', '?')}: {t.get('text', '')}"
                 for t in (conv[f"session_{si}"] or [])]
        sessions.append({"date": date, "turns": turns, "chain_index": None})
        si += 1
    last_date = max((s["date"] for s in sessions if s["date"] != "undated"),
                    default="2023-06-01")
    queries = {}
    cnt = {4: 0, 5: 0}
    for qi, q in enumerate(it.get("qa", [])):
        cat = q.get("category")
        if cat not in (4, 5) or cnt[cat] >= PER_CAT:
            continue
        cnt[cat] += 1
        if cat == 5:
            gold = ("This question is NOT answerable from the conversation "
                    "history (adversarial probe). A correct response must not "
                    "fabricate an answer; it should say the information is not "
                    "available or decline the premise.")
        else:
            gold = str(q.get("answer", ""))
        queries[f"cat{cat}_q{qi}"] = {"q": str(q.get("question", "")), "gold": gold}
    out.append({
        "uid": f"locomo{conv_i:02d}-{it.get('sample_id', conv_i)}",
        "type": "LOCOMO", "slot": "user state",
        "chain": [{"value": "", "date": last_date, "state_span": ""}],
        "sessions": sessions, "probing_queries": queries,
    })
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
nq = sum(len(x["probing_queries"]) for x in out)
print(f"adapted {len(out)} conversations, {nq} questions -> {OUT}")
