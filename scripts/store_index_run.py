# -*- coding: utf-8 -*-
"""
scripts/store_index_run.py — 消费方旗标分支(QVF_STORE_INDEX=1)。

旗标关(默认):execute_plan_dispatch 就是 complex_query_arm.execute_plan
本身(逐字节引用,不包一层新代码路径),行为逐字节不变。
旗标开:走 qvf/store_index(_ops).py 的索引路径。

冻结代码(complex_query_arm.py 等)不被本文件编辑,只读导入——满足
"消费方走旗标分支,不碰冻结文件"的纪律。

用法(替代 scripts/boundary_ooo_run.py 里对 execute_plan 的直接调用,
跑 B4 45 对题,验证①旗标关时输出与原 boundary_ooo_run.py 逐字节相同、
②旗标开时是否引入新的 seq/shuf 分歧):

  python scripts/store_index_run.py --mode ooo_duel \
      --cards-seq results/wt_cards_ooo_seq --cards-shuf results/wt_cards_ooo_shuf \
      --out results/store_index_ooo_duel_flag0.jsonl          # 旗标关对拍
  QVF_STORE_INDEX=1 python scripts/store_index_run.py --mode ooo_duel \
      --cards-seq results/wt_cards_ooo_seq --cards-shuf results/wt_cards_ooo_shuf \
      --out results/store_index_ooo_duel_flag1.jsonl          # 旗标开重跑
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_STORE_INDEX = int(os.environ.get("QVF_STORE_INDEX", "0") or 0)

from scripts.complex_query_arm import execute_plan as _execute_plan_frozen  # noqa: E402
from scripts.complex_query_arm import _mem_dates as _cqa_mem_dates  # noqa: E402
from scripts.boundary_gold import BEFORE_EARLIEST, EMPTY_CHAIN  # noqa: E402
from scripts.boundary_run import (_norm_val, _RE_PIT_ANSWER,  # noqa: E402
                                  _RE_PIT_BEFORE, _RE_PIT_NOCHAIN, _RE_CC)
from scripts.boundary_ooo_run import (OOO_IN, build_plan, extract_answer,  # noqa: E402
                                      answers_agree, _load_entries)

if _STORE_INDEX:
    from qvf.store_index import StoreIndex  # noqa: E402
    from qvf.store_index_ops import execute_plan_indexed  # noqa: E402

    def execute_plan_dispatch(plan, recs, mem_dates, question=""):
        index = StoreIndex().build(recs, mem_dates)
        return execute_plan_indexed(plan, index, question)
else:
    # 旗标关:直接绑定冻结函数本身,零包装,逐字节不变。
    execute_plan_dispatch = _execute_plan_frozen


def run_ooo_duel(cards_seq: str, cards_shuf: str, data_seq: str, data_shuf: str,
                 out_path: str, uids: Optional[List[str]] = None):
    rows = [json.loads(l) for l in open(OOO_IN, encoding="utf-8") if l.strip()]
    if uids:
        keep = set(uids)
        rows = [r for r in rows if r["uid"] in keep]
    pairs: Dict[str, dict] = {}
    for r in rows:
        pairs.setdefault(r["pair_id"], {})[r["order_variant"]] = r
    pair_ids = sorted(k for k, v in pairs.items()
                      if "sequential" in v and "shuffled" in v)

    entries_seq = _load_entries(ROOT / data_seq)
    entries_shuf = _load_entries(ROOT / data_shuf)
    cards_seq_dir = ROOT / cards_seq
    cards_shuf_dir = ROOT / cards_shuf

    def load_recs(uid, cards_dir):
        p = cards_dir / f"{uid}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8")).get("records", [])

    out_rows = []
    n_missing = 0
    for pid in pair_ids:
        rowset = pairs[pid]
        row = rowset["sequential"]
        uid = row["uid"]
        plan = build_plan(row)
        recs_seq = load_recs(uid, cards_seq_dir)
        recs_shuf = load_recs(uid, cards_shuf_dir)
        if recs_seq is None or recs_shuf is None:
            n_missing += 1
            continue
        md_seq = _cqa_mem_dates(entries_seq[uid])
        md_shuf = _cqa_mem_dates(entries_shuf[uid])
        _, der_seq = execute_plan_dispatch(plan, recs_seq, md_seq, row["question"])
        _, der_shuf = execute_plan_dispatch(plan, recs_shuf, md_shuf,
                                            rowset["shuffled"]["question"])
        ans_seq, txt_seq = extract_answer(row["qtype"], der_seq)
        ans_shuf, txt_shuf = extract_answer(row["qtype"], der_shuf)
        gold = row["gold"]
        out_rows.append({
            "pair_id": pid, "uid": uid, "qtype": row["qtype"], "slot": row["slot"],
            "question": row["question"], "gold": gold,
            "seq_answer": ans_seq, "shuf_answer": ans_shuf,
            "seq_eq_shuf": answers_agree(ans_seq, ans_shuf),
            "seq_agree_gold": answers_agree(ans_seq, gold),
            "shuf_agree_gold": answers_agree(ans_shuf, gold),
            "seq_derived": txt_seq, "shuf_derived": txt_shuf,
        })

    outp = ROOT / out_path
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    n = len(out_rows)
    n_eq = sum(1 for r in out_rows if r["seq_eq_shuf"])
    print(f"QVF_STORE_INDEX={_STORE_INDEX}  TOTAL pairs={n} "
         f"(missing_card={n_missing})")
    print(f"  seq==shuf: {n_eq}/{n} = {n_eq/n*100:.1f}%")
    print(f"-> {outp}")
    return out_rows


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ooo_duel"], default="ooo_duel")
    ap.add_argument("--cards-seq", required=True)
    ap.add_argument("--cards-shuf", required=True)
    ap.add_argument("--data-seq", default="data/_ooo_seq.json")
    ap.add_argument("--data-shuf", default="data/_ooo_shuf.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--uids", default=None)
    a = ap.parse_args()
    uid_list = a.uids.split(",") if a.uids else None
    run_ooo_duel(a.cards_seq, a.cards_shuf, a.data_seq, a.data_shuf, a.out,
                uid_list)


if __name__ == "__main__":
    main()
