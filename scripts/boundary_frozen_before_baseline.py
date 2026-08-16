# -*- coding: utf-8 -*-
"""scripts/boundary_frozen_before_baseline.py — 阶段二步骤3:冻结路径 before 基线。

零 LLM。复用已存在的 results/wt_cards_ooo_seq / wt_cards_ooo_shuf(B4 原有产物,
旗标关的冻结 write_phase 对 data/_ooo_seq.json / _ooo_shuf.json 分别建卡),
统计 15 条链中卡片集"不同"的条数,作为阶段二步骤3的 before 基线。

比较口径:每条记录剥离 record_id(冻结路径的 record_id 是纯位置编号 "r1","r2"...
——同内容不同顺序必然编号不同,不能反映真实内容差异)与
relation_target_record_ids(其值本身就是位置编号的引用,同理剥离),保留其余
全部字段(source_span/entity/slot/value/claim/slot_cardinality/
temporal_relation/condition/implies_stale_slots/stated_date/owner/slot_class/
source_memory_id),整条记录序列化后按字典序排序(消除模型输出顺序差异),
两条链的记录多重集是否相等 = 是否等价。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
STRIP_KEYS = {"record_id", "relation_target_record_ids"}


def _canon_record(r: dict) -> str:
    d = {k: v for k, v in r.items() if k not in STRIP_KEYS}
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _canon_cardset(records: List[dict]) -> str:
    return json.dumps(sorted(_canon_record(r) for r in records), ensure_ascii=False)


def main():
    seq_dir = ROOT / "results" / "wt_cards_ooo_seq"
    shuf_dir = ROOT / "results" / "wt_cards_ooo_shuf"
    uids = sorted(p.stem for p in seq_dir.glob("*.json"))
    n_diff = 0
    n_same = 0
    rows = []
    for uid in uids:
        ps, pu = seq_dir / f"{uid}.json", shuf_dir / f"{uid}.json"
        if not ps.exists() or not pu.exists():
            print(f"[{uid}] MISSING (seq={ps.exists()} shuf={pu.exists()})")
            continue
        ds = json.loads(ps.read_text(encoding="utf-8"))
        du = json.loads(pu.read_text(encoding="utf-8"))
        cs = _canon_cardset(ds.get("records", []))
        cu = _canon_cardset(du.get("records", []))
        same = (cs == cu)
        n_same += int(same)
        n_diff += int(not same)
        rows.append({
            "uid": uid, "same": same,
            "n_records_seq": len(ds.get("records", [])),
            "n_records_shuf": len(du.get("records", [])),
        })
        print(f"[{uid}] {'SAME' if same else 'DIFF'} "
              f"(n_seq={len(ds.get('records', []))}, n_shuf={len(du.get('records', []))})")

    n = len(rows)
    print(f"\nFROZEN PATH before-baseline: {n_diff}/{n} chains differ "
          f"({n_diff/n*100:.1f}%), {n_same}/{n} identical (content-canonical, "
          f"record_id/relation_target_record_ids stripped)")

    out = ROOT / "results" / "p2_frozen_before_baseline.json"
    out.write_text(json.dumps({"rows": rows, "n_total": n, "n_diff": n_diff,
                                "n_same": n_same}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
