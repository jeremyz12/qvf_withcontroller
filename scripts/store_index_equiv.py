# -*- coding: utf-8 -*-
"""
scripts/store_index_equiv.py — P5 护栏①对拍:索引执行(qvf/store_index +
qvf/store_index_ops)vs 扫描执行(complex_query_arm.execute_plan,冻结,
只读导入),零 LLM。

用法(与 scripts/algebra_parity.py 同款调用面):
  QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/store_index_equiv.py \
      --rows results/wsc_s5_test_v42.jsonl \
      --data data/wikistate_full_P108.json data/wikistate_full_P54.json \
             data/wikistate_full_P551.json --name s5

--scan-ties:独立诊断模式,扫描给定卡片目录里是否存在"同键同日不同值"的
真实平局实例(REPRO NOTE 的可复现验证),不跑对拍。
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complex_query_arm import (_load_entries, _load_records,  # noqa: E402
                                       _mem_dates, _query_date, execute_plan,
                                       reader_content)
from scripts.wt_qvf_prototype import _norm  # noqa: E402
from qvf.store_index import StoreIndex, sort_key  # noqa: E402
from qvf.store_index_ops import execute_plan_indexed  # noqa: E402


def _rows(path: str, limit: int):
    out = []
    for i, l in enumerate(open(path, encoding="utf-8")):
        if limit and i >= limit:
            break
        s = l.strip()
        if s:
            out.append(json.loads(s))
    return out


def scan_ties(cards_glob: str):
    """对给定卡片目录里的每个 (owner, slot_class) 分组,报出任何两条记录
    stated_date 字符串完全相同但 value(归一化后)不同的实例——这正是
    execute_plan 的排序步骤需要平局裁决、原实现由列表位置决定胜负的
    唯一触发条件。零命中即证明 REPRO NOTE 的"该数据集范围内无真实平局
    实例"论断可复现。"""
    n_ties = 0
    hits = []
    for f in sorted(glob.glob(cards_glob)):
        recs = json.loads(Path(f).read_text(encoding="utf-8")).get("records", [])
        groups: dict = {}
        for r in recs:
            cls = r.get("slot_class")
            if not cls:
                continue
            groups.setdefault((r.get("owner") or "", cls), []).append(r)
        for key, g in groups.items():
            by_date: dict = {}
            for r in g:
                d = r.get("stated_date") or ""
                if d:
                    by_date.setdefault(d, []).append(r)
            for d, rs in by_date.items():
                vals = {_norm(r.get("value", "")) for r in rs}
                if len(vals) > 1:
                    n_ties += 1
                    hits.append({"file": f, "key": list(key), "date": d,
                                "record_ids": [r.get("record_id") for r in rs],
                                "values": [r.get("value") for r in rs]})
    print(f"SCAN_TIES: {cards_glob} -> {n_ties} true same-date multi-value "
          f"ties found across all keyed groups")
    for h in hits[:20]:
        print(" ", h)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows")
    ap.add_argument("--data", nargs="+")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--name", default="run")
    ap.add_argument("--out", default="results/store_index_equiv_20260816.jsonl")
    ap.add_argument("--scan-ties", default=None,
                    help="glob of card json files to scan for real ties, "
                         "e.g. 'results/wt_cards_v42/*.json'; skips the "
                         "parity run when given")
    a = ap.parse_args()

    if a.scan_ties:
        scan_ties(a.scan_ties)
        return

    entries = _load_entries(a.data)
    rows = _rows(a.rows, a.limit)
    md_cache = {}
    idx_cache = {}
    n = eq = 0
    diffs = []
    for r in rows:
        plan = r.get("plan")
        if not isinstance(plan, dict):
            continue
        uid = r["uid"]
        if uid not in md_cache:
            md_cache[uid] = _mem_dates(entries.get(uid, {}))
        md = md_cache[uid]
        recs = _load_records(uid)
        if uid not in idx_cache:
            idx_cache[uid] = StoreIndex().build(recs, md)
        index = idx_cache[uid]

        ev_s, de_s = execute_plan(plan, recs, md, r["question"])
        ev_i, de_i = execute_plan_indexed(plan, index, r["question"])
        qd = _query_date(entries.get(uid, {}), r["question"])
        rc_s = reader_content(ev_s, de_s, qd, r["question"])
        rc_i = reader_content(ev_i, de_i, qd, r["question"])
        n += 1
        if ev_s == ev_i and de_s == de_i and rc_s == rc_i:
            eq += 1
        else:
            diffs.append({"question_id": r.get("question_id") or r.get("qid"),
                          "op": plan.get("op"), "scan": rc_s, "indexed": rc_i})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({
            "slice": a.name, "rows_file": a.rows, "limit": a.limit or None,
            "n": n, "byte_equal": eq, "diff_n": len(diffs),
            "diffs": diffs[:10],
        }, ensure_ascii=False) + "\n")
    print(f"[{a.name}] n={n} byte_equal={eq} diff={len(diffs)}")
    for d in diffs[:5]:
        print("DIFF", d["question_id"], d["op"])
        print("  scan   :", d["scan"][:300].replace("\n", " | "))
        print("  indexed:", d["indexed"][:300].replace("\n", " | "))
    sys.exit(0 if not diffs else 1)


if __name__ == "__main__":
    main()
