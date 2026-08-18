# -*- coding: utf-8 -*-
"""armdom.ingest — 把通用日志读成内部行结构。

输入是 JSONL，每行一个 (question, arm) 结果；可选 ``baseline: true`` 行记录你的系统
当前实际选了什么。字段见 README。
"""
from __future__ import annotations

import collections
import json
from typing import Dict, List, Tuple


def load(path: str) -> Tuple[List[dict], Dict[str, float]]:
    """返回 (rows, baseline)。rows 每项一题，``arms`` 为 {arm: {correct, tok}}。"""
    per: Dict[str, dict] = {}
    base: Dict[str, dict] = {}
    dupes: List[str] = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        qid = d.get("qid")
        if qid is None:
            raise ValueError(f"缺 qid: {line[:120]}")
        if d.get("baseline"):
            base[qid] = {"correct": bool(d.get("correct")),
                         "tok": float(d.get("tokens", 0.0))}
            continue
        r = per.setdefault(qid, {"qid": qid, "uid": d.get("uid", qid),
                                 "bench": d.get("group", "all"),
                                 "q": d.get("question", ""), "arms": {}})
        if d.get("question") and not r["q"]:
            r["q"] = d["question"]
        arm = d.get("arm")
        if arm is None:
            raise ValueError(f"缺 arm: {line[:120]}")
        if arm in r["arms"]:
            dupes.append(qid)
        r["arms"][arm] = {"correct": bool(d.get("correct")),
                          "tok": float(d.get("tokens", 0.0))}
    rows = list(per.values())
    for r in rows:
        b = base.get(r["qid"])
        r["v42_correct"] = b["correct"] if b else None
        r["v42_tok"] = b["tok"] if b else None
    if dupes:
        raise ValueError(
            f"同一 (qid, arm) 出现多次，共 {len(dupes)} 次，样例 {dupes[:3]}。"
            "这会把不同的观测悄悄合并成一条，请让 qid 唯一后重试。")
    stats = {"rows": len(rows), "with_baseline": sum(1 for r in rows if r["v42_correct"] is not None),
             "with_text": sum(1 for r in rows if r["q"]),
             "stores": len({r["uid"] for r in rows}),
             "groups": len({r["bench"] for r in rows})}
    return rows, stats


def arms_by_cost(rows: List[dict]) -> List[str]:
    """按平均 token 从低到高排序的臂名——即缺省回落顺序。"""
    agg = collections.defaultdict(lambda: [0.0, 0])
    for r in rows:
        for a, v in r["arms"].items():
            agg[a][0] += v["tok"]
            agg[a][1] += 1
    return sorted(agg, key=lambda a: agg[a][0] / max(agg[a][1], 1))
