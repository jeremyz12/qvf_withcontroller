# -*- coding: utf-8 -*-
"""护栏对拍:宏执行(qvf_algebra)vs 平面执行(execute_plan),零 LLM。

预注册判据:S5 全量 314 + S6 30 + S7 切片 50 上,逐题证据包(ev 行 +
derived 行 + reader_content 全文)逐字节等价;任一不等价即弃(修不平报
blocked)。--synthetic 附加合成计划对拍(current / point_in_time /
trajectory / premise_check —— 既有三切片未覆盖的 4 个算子;判据之外的
加强项,单独汇报)。

env(QVF_CARDS_KEYED 等)由调用方设置,须与原始跑批一致;QVF_ALGEBRA
保持关(本对拍显式 import 代数模块,不经旗标)。

用法:
  QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/algebra_parity.py \
      --rows results/wsc_s5_test_v42.jsonl --data data/wikistate_full_P108.json \
      data/wikistate_full_P54.json data/wikistate_full_P551.json --name s5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complex_query_arm import (_load_entries, _load_records,  # noqa: E402
                                       _mem_dates, _query_date, _select_pool,
                                       _chain, execute_plan, reader_content)
from scripts.qvf_algebra import execute_plan_algebra  # noqa: E402


def _rows(path: str, limit: int):
    out = []
    for i, l in enumerate(open(path, encoding="utf-8")):
        if limit and i >= limit:
            break
        s = l.strip()
        if s:
            out.append(json.loads(s))
    return out


def _synth_plans(rows, entries, md_cache):
    """合成计划:每个 (uid, slot) 一组 current/trajectory/point_in_time/
    premise_check(presupposed=链首值,过时值语义;date=链中段日期)。"""
    seen = set()
    out = []
    for r in rows:
        slot = (r.get("plan") or {}).get("slot")
        uid = r["uid"]
        if not slot or (uid, slot) in seen:
            continue
        seen.add((uid, slot))
        recs = _load_records(uid)
        ch = _chain(_select_pool(recs, slot, md_cache[uid], r["question"]),
                    md_cache[uid])
        first_v = str(ch[0].get("value", "")) if ch else "unknown-value"
        mid_d = (ch[len(ch) // 2].get("stated_date")
                 or "2005-06-15") if ch else "2005-06-15"
        q = r["question"]
        for op, extra in (("current", {}), ("trajectory", {}),
                          ("point_in_time", {"date": str(mid_d)}),
                          ("premise_check", {"presupposed": first_v})):
            plan = {"op": op, "slot": slot, "slot2": None, "date": None,
                    "tag": None, "presupposed": None, "anchor_index": None}
            plan.update(extra)
            out.append({"uid": uid, "question_id": f"syn_{uid}_{slot}_{op}",
                        "question": q, "plan": plan})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--name", required=True)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", default="results/algebra_parity_20260815.jsonl")
    a = ap.parse_args()
    entries = _load_entries(a.data)
    rows = _rows(a.rows, a.limit)
    md_cache = {}
    for r in rows:
        if r["uid"] not in md_cache:
            md_cache[r["uid"]] = _mem_dates(entries.get(r["uid"], {}))
    if a.synthetic:
        rows = _synth_plans(rows, entries, md_cache)
    n = eq = 0
    diffs = []
    for r in rows:
        plan = r.get("plan")
        if not isinstance(plan, dict):
            continue
        uid = r["uid"]
        recs = _load_records(uid)
        md = md_cache[uid]
        ev_f, de_f = execute_plan(plan, recs, md, r["question"])
        ev_a, de_a = execute_plan_algebra(plan, recs, md, r["question"])
        qd = _query_date(entries.get(uid, {}), r["question"])
        rc_f = reader_content(ev_f, de_f, qd, r["question"])
        rc_a = reader_content(ev_a, de_a, qd, r["question"])
        n += 1
        if ev_f == ev_a and de_f == de_a and rc_f == rc_a:
            eq += 1
        else:
            diffs.append({"question_id": r.get("question_id"),
                          "op": plan.get("op"), "flat": rc_f, "algebra": rc_a})
    with open(a.out, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "slice": a.name, "rows_file": a.rows, "limit": a.limit or None,
            "synthetic": a.synthetic, "n": n, "byte_equal": eq,
            "diff_n": len(diffs), "diffs": diffs[:10],
        }, ensure_ascii=False) + "\n")
    print(f"[{a.name}] n={n} byte_equal={eq} diff={len(diffs)}")
    for d in diffs[:3]:
        print("DIFF", d["question_id"], d["op"])
        print("  flat   :", d["flat"][:300].replace("\n", " | "))
        print("  algebra:", d["algebra"][:300].replace("\n", " | "))
    sys.exit(0 if not diffs else 1)


if __name__ == "__main__":
    main()
