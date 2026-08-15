# -*- coding: utf-8 -*-
"""
scripts/boundary_ooo_materialize.py

乱序对决:第②步前置——把 data/wsc_ooo.jsonl 里每条链的 session_order(展示
顺序 -> 源文件 sessions 数组下标的映射)物化成两份可喂给
scripts/wt_qvf_prototype.py --phase write 的临时数据文件:
  data/_ooo_seq.json   sessions 保持源文件原顺序(顺序版)
  data/_ooo_shuf.json  sessions 按 session_order 重排(乱序版;每个 session
                        自己的 date 字段不变,只改它在数组里出现的位置)

纪律:只读三份源 data/wikistate_full_P*.json + data/wsc_ooo.jsonl,不改动、
不导入 gen_wikistate_complex 的出题逻辑,不导入 complex_query_arm。纯数据
搬运脚本,新文件走 scripts/boundary_* 命名。

load_stale_chain(eval/stale_chain_dataset.py)要求条目带非空 probing_queries
才会产出 QAInstance(write_phase 只用 instances 取 memories,不关心具体问题
内容)—— 补一个占位 dummy 问题触发实例化,不影响建卡本身。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OOO_IN = ROOT / "data" / "wsc_ooo.jsonl"
SOURCES = ["data/wikistate_full_P108.json", "data/wikistate_full_P54.json",
           "data/wikistate_full_P551.json"]

OUT_SEQ = ROOT / "data" / "_ooo_seq.json"
OUT_SHUF = ROOT / "data" / "_ooo_shuf.json"

_DUMMY_PQ = {"dummy": {"q": "placeholder, unused by write_phase", "gold": "x"}}


def main() -> None:
    rows = [json.loads(l) for l in open(OOO_IN, encoding="utf-8") if l.strip()]
    by_uid: Dict[str, dict] = {}
    for r in rows:
        by_uid.setdefault(r["uid"], {"source": r["source"]})
        if r["order_variant"] == "shuffled":
            by_uid[r["uid"]]["session_order"] = r["session_order"]
    uids = sorted(by_uid.keys())
    print(f"uids needed: {len(uids)}")

    entries_by_source: Dict[str, Dict[str, dict]] = {}
    for f in SOURCES:
        by = {}
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            by[e["uid"]] = e
        entries_by_source[f] = by

    seq_out: List[dict] = []
    shuf_out: List[dict] = []
    for uid in uids:
        info = by_uid[uid]
        entry = entries_by_source[info["source"]].get(uid)
        assert entry is not None, f"uid not found in {info['source']}: {uid}"
        sessions = entry.get("sessions", [])
        order = info["session_order"]
        assert len(order) == len(sessions), (
            f"{uid}: session_order len {len(order)} != sessions len "
            f"{len(sessions)}")

        seq_entry = dict(entry)
        seq_entry["sessions"] = sessions  # 原顺序,原样引用
        seq_entry["probing_queries"] = _DUMMY_PQ
        seq_out.append(seq_entry)

        shuf_entry = dict(entry)
        shuf_entry["sessions"] = [sessions[i] for i in order]
        shuf_entry["probing_queries"] = _DUMMY_PQ
        shuf_out.append(shuf_entry)

    OUT_SEQ.write_text(json.dumps(seq_out, ensure_ascii=False, default=str),
                       encoding="utf-8")
    OUT_SHUF.write_text(json.dumps(shuf_out, ensure_ascii=False, default=str),
                        encoding="utf-8")
    print(f"-> {OUT_SEQ} ({len(seq_out)} entries)")
    print(f"-> {OUT_SHUF} ({len(shuf_out)} entries)")


if __name__ == "__main__":
    main()
