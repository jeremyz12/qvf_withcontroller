# -*- coding: utf-8 -*-
"""
scripts/boundary_ooo_run.py

乱序对决:第②步(同题跑顺序版/乱序版两套库,比同答率)。

对 data/wsc_ooo.jsonl 每条(pair_id, qtype)题对,分别用顺序库
(--cards-seq)与乱序库(--cards-shuf)构造 recs,调 execute_plan 算出两版
系统答案,与 gold 三方比对:
  seq_agree_gold / shuf_agree_gold:各自是否与独立金答案一致;
  seq_eq_shuf:两版系统答案彼此是否一致(乱序鲁棒性的核心指标——
  execute_plan 按记录的 stated_date 排序建链,理论上应与会话呈现顺序无关;
  若卡片库本身(写入时抽取)受呈现顺序影响,才会在这里现出差异)。

纪律:complex_query_arm.py 只读只调用;新文件走 scripts/boundary_* 命名。

用法:
  python scripts/boundary_ooo_run.py \
      --cards-seq results/wt_cards_ooo_seq --cards-shuf results/wt_cards_ooo_shuf \
      --data-seq data/_ooo_seq.json --data-shuf data/_ooo_shuf.json \
      --out results/ooo_duel_20260816.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QVF_OPEN_SLOT", "1")
os.environ.setdefault("QVF_OPEN_KEYS", "1")
os.environ.setdefault("QVF_FAIL_CLOSED", "1")
os.environ.setdefault("QVF_ALGEBRA", "0")

from scripts.complex_query_arm import execute_plan  # noqa: E402
from scripts.complex_query_arm import _mem_dates as _cqa_mem_dates  # noqa: E402
from scripts.boundary_gold import BEFORE_EARLIEST, EMPTY_CHAIN  # noqa: E402
from scripts.boundary_run import (_norm_val, _RE_PIT_ANSWER,  # noqa: E402
                                  _RE_PIT_BEFORE, _RE_PIT_NOCHAIN, _RE_CC)

OOO_IN = ROOT / "data" / "wsc_ooo.jsonl"

_RE_CURRENT = re.compile(r"current .+? is (.+?) \(since ")
_RE_FL_FIRST = re.compile(r"^First .+?: (.+?) \(from ")
_RE_FL_LAST = re.compile(r"most recent: (.+?) \(since ")
_RE_COUNT_BEFORE = re.compile(r"had (\d+) different")


def _load_entries(path: Path) -> Dict[str, dict]:
    by = {}
    for e in json.loads(path.read_text(encoding="utf-8")):
        by[e["uid"]] = e
    return by


def build_plan(row: dict) -> dict:
    op = row["qtype"]
    sys_op = "first_last" if op in ("first_last_first", "first_last_last") \
        else op
    plan = {"op": sys_op, "slot": row["slot"], "slot2": None, "date": None,
            "tag": None, "presupposed": None, "anchor_index": None}
    if op in ("point_in_time", "count_before"):
        plan["date"] = row["params"]["d"]
    return plan


def extract_answer(op: str, derived: List[str]):
    text = derived[0] if derived else ""
    if not derived:
        return ("NO_DERIVED", text)
    if op == "current":
        m = _RE_CURRENT.search(text)
        return (m.group(1), text) if m else ("UNPARSED", text)
    if op == "count_changes":
        m = _RE_CC.search(text)
        return (int(m.group(1)), text) if m else ("UNPARSED", text)
    if op == "first_last_first":
        m = _RE_FL_FIRST.search(text)
        return (m.group(1), text) if m else ("UNPARSED", text)
    if op == "first_last_last":
        m = _RE_FL_LAST.search(text)
        return (m.group(1), text) if m else ("UNPARSED", text)
    if op == "count_before":
        m = _RE_COUNT_BEFORE.search(text)
        return (int(m.group(1)), text) if m else ("UNPARSED", text)
    if op == "point_in_time":
        if _RE_PIT_NOCHAIN.search(text):
            return (EMPTY_CHAIN, text)
        if _RE_PIT_BEFORE.search(text):
            return (BEFORE_EARLIEST, text)
        m = _RE_PIT_ANSWER.search(text)
        return (m.group(1), text) if m else ("UNPARSED", text)
    return ("UNKNOWN_OP", text)


def answers_agree(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str) and a not in (
            EMPTY_CHAIN, BEFORE_EARLIEST) and b not in (
            EMPTY_CHAIN, BEFORE_EARLIEST):
        return _norm_val(a) == _norm_val(b)
    return a == b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-seq", required=True)
    ap.add_argument("--cards-shuf", required=True)
    ap.add_argument("--data-seq", default="data/_ooo_seq.json")
    ap.add_argument("--data-shuf", default="data/_ooo_shuf.json")
    ap.add_argument("--out", default="results/ooo_duel_20260816.jsonl")
    ap.add_argument("--uids", default=None,
                    help="逗号分隔 uid 子集(冒烟用);默认全量")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(OOO_IN, encoding="utf-8") if l.strip()]
    if a.uids:
        keep = set(a.uids.split(","))
        rows = [r for r in rows if r["uid"] in keep]
    # 按 pair_id 分组:每组含 sequential/shuffled 两行,qtype/gold 相同
    pairs: Dict[str, dict] = {}
    for r in rows:
        pairs.setdefault(r["pair_id"], {})[r["order_variant"]] = r
    pair_ids = sorted(k for k, v in pairs.items()
                      if "sequential" in v and "shuffled" in v)
    if a.uids:
        print(f"pairs in subset: {len(pair_ids)}")

    entries_seq = _load_entries(ROOT / a.data_seq)
    entries_shuf = _load_entries(ROOT / a.data_shuf)
    cards_seq_dir = ROOT / a.cards_seq
    cards_shuf_dir = ROOT / a.cards_shuf

    def load_recs(uid: str, cards_dir: Path) -> Optional[List[dict]]:
        p = cards_dir / f"{uid}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8")).get("records", [])

    out_rows = []
    n_missing = 0
    for pid in pair_ids:
        rowset = pairs[pid]
        row = rowset["sequential"]  # qtype/slot/gold/uid 与 shuffled 孪生行相同
        uid = row["uid"]
        plan = build_plan(row)

        recs_seq = load_recs(uid, cards_seq_dir)
        recs_shuf = load_recs(uid, cards_shuf_dir)
        if recs_seq is None or recs_shuf is None:
            n_missing += 1
            continue
        md_seq = _cqa_mem_dates(entries_seq[uid])
        md_shuf = _cqa_mem_dates(entries_shuf[uid])

        _, der_seq = execute_plan(plan, recs_seq, md_seq, row["question"])
        _, der_shuf = execute_plan(plan, recs_shuf, md_shuf,
                                   rowset["shuffled"]["question"])
        ans_seq, txt_seq = extract_answer(row["qtype"], der_seq)
        ans_shuf, txt_shuf = extract_answer(row["qtype"], der_shuf)
        gold = row["gold"]

        out_rows.append({
            "pair_id": pid, "uid": uid, "qtype": row["qtype"],
            "slot": row["slot"], "question": row["question"], "gold": gold,
            "seq_answer": ans_seq, "shuf_answer": ans_shuf,
            "seq_eq_shuf": answers_agree(ans_seq, ans_shuf),
            "seq_agree_gold": answers_agree(ans_seq, gold),
            "shuf_agree_gold": answers_agree(ans_shuf, gold),
            "seq_derived": txt_seq, "shuf_derived": txt_shuf,
            "inversions": row.get("inversions_among_declaring_sessions", 0),
            "shuf_inversions":
                rowset["shuffled"].get(
                    "inversions_among_declaring_sessions", 0),
        })

    outp = ROOT / a.out
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    n = len(out_rows)
    if n == 0:
        print(f"NO PAIRS RUN (missing_card={n_missing})")
        return
    n_eq = sum(1 for r in out_rows if r["seq_eq_shuf"])
    n_seq_gold = sum(1 for r in out_rows if r["seq_agree_gold"])
    n_shuf_gold = sum(1 for r in out_rows if r["shuf_agree_gold"])
    print(f"TOTAL pairs={n} (missing_card={n_missing})")
    print(f"  seq==shuf (乱序鲁棒性): {n_eq}/{n} = {n_eq/n*100:.1f}%")
    print(f"  seq vs gold: {n_seq_gold}/{n} = {n_seq_gold/n*100:.1f}%")
    print(f"  shuf vs gold: {n_shuf_gold}/{n} = {n_shuf_gold/n*100:.1f}%")
    by_op: Dict[str, List[int]] = {}
    for r in out_rows:
        b = by_op.setdefault(r["qtype"], [0, 0, 0, 0])
        b[0] += 1
        b[1] += int(r["seq_eq_shuf"])
        b[2] += int(r["seq_agree_gold"])
        b[3] += int(r["shuf_agree_gold"])
    for op, (tot, eq, sg, shg) in sorted(by_op.items()):
        print(f"  {op}: n={tot} seq==shuf={eq}/{tot}({eq/tot*100:.0f}%) "
              f"seq==gold={sg}/{tot} shuf==gold={shg}/{tot}")
    print(f"-> {outp}")


if __name__ == "__main__":
    main()
