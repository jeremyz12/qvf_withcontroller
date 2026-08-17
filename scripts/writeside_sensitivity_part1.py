# -*- coding: utf-8 -*-
"""T1 条件③ 第一步:零成本纯代码敏感性分析。

对同一批 S5 问题(已有编译计划,零 LLM),用不同质量的卡片库重跑
complex_query_arm.execute_plan(),比较:
  ① 证据包为空的比例
  ② 结论行(derived)的计算结果是否跨库一致
  ③ 若不一致,提取的关键数值/答案值是否翻转(相对 v42 参照库 与 相对 gold)

只读调用冻结文件 scripts/complex_query_arm.py 的 execute_plan / _mem_dates /
reader_content(不改动、不猴补);本脚本自己实现卡片加载(不经过冻结文件的
module-level CARDS/_CARDS_KEYED 全局态,以便逐库精确指定,不做非目标库回落)。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complex_query_arm import execute_plan, _mem_dates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
UNION = ROOT / "results/wsc_s5_test_v42b1_union.jsonl"

LIBRARIES = {
    "v42_archived_76.88": ROOT / "results/wt_cards_v42",
    "b6_rep1_78.0": ROOT / "results/wt_cards_b6_rep1",
    "b6_rep2_68.0": ROOT / "results/wt_cards_b6_rep2",
    "b6_rep3_64.0": ROOT / "results/wt_cards_b6_rep3",
    "p6_rep1_73.33": ROOT / "results/wt_cards_p6_rep1",
    "p6_rep2_80.00": ROOT / "results/wt_cards_p6_rep2",
    "p6_rep3_73.33": ROOT / "results/wt_cards_p6_rep3",
}

DATA_FILES = [ROOT / "data/wikistate_full_P108.json",
              ROOT / "data/wikistate_full_P54.json"]


def load_entries():
    by_uid = {}
    for f in DATA_FILES:
        for e in json.loads(f.read_text(encoding="utf-8")):
            by_uid.setdefault(e["uid"], e)
    return by_uid


def load_records(lib_dir: Path, uid: str):
    """不回落:库里没有就是没有(空证据包是这份库覆盖不到的真实后果)。"""
    p = lib_dir / f"{uid}.json"
    if not p.exists():
        return None  # None = 卡片文件本身缺失(非"有卡但抽取为0条")
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("records", [])
    except Exception:
        return []


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def extract_key_value(op: str, derived_line: str):
    """从结论行里摘取可比较的"关键计算值",按算子类型摘不同的东西。
    仅用于粗粒度一致性/翻转检测,不是完整语义解析。"""
    if not derived_line:
        return None
    if op == "count_changes":
        m = re.search(r"changed (\d+) time", derived_line)
        return int(m.group(1)) if m else None
    if op == "count_before":
        m = re.search(r"had (\d+) different", derived_line)
        return int(m.group(1)) if m else None
    if op == "longest":
        m = re.search(r"Held longest \(closed intervals only\): (.+?) \(",
                       derived_line)
        return m.group(1).strip() if m else (
            "SINGLE_STATE" if "no closed interval" in derived_line else None)
    if op == "first_last":
        m = re.search(r"First .+?: (.+?) \(from .+?\); most recent: (.+?) \(",
                       derived_line)
        return (m.group(1).strip(), m.group(2).strip()) if m else None
    if op in ("current", "premise_check"):
        m = re.search(r"current .+? is (.+?) \(since", derived_line)
        return m.group(1).strip() if m else None
    if op == "point_in_time":
        m = re.search(r"was (.+?) \(recorded", derived_line)
        if m:
            return m.group(1).strip()
        m = re.search(r"earliest known state is (.+?) from", derived_line)
        return m.group(1).strip() if m else None
    return None  # trajectory / tag_filter / tag_trend / join_at_change: 不摘取


def main():
    entries = load_entries()
    rows = [json.loads(l) for l in open(UNION, encoding="utf-8")]
    by_uid_rows = {}
    for r in rows:
        by_uid_rows.setdefault(r["uid"], []).append(r)

    lib_uid_sets = {name: set(p.stem for p in d.glob("*.json"))
                     for name, d in LIBRARIES.items()}
    b6_overlap = lib_uid_sets["b6_rep1_78.0"]
    p6_overlap = lib_uid_sets["p6_rep1_73.33"]

    for subset_name, subset_uids in (("B6 子集(50 uid,3 轮,含 v42 参照)",
                                       b6_overlap),
                                      ("P6 子集(30 uid,3 轮,含 v42 参照)",
                                       p6_overlap)):
        subset_libs = ([n for n in LIBRARIES if n.startswith("v42")] +
                        ([n for n in LIBRARIES if n.startswith("b6")]
                         if "B6" in subset_name else
                         [n for n in LIBRARIES if n.startswith("p6")]))
        qids = []
        for uid in sorted(subset_uids):
            for r in by_uid_rows.get(uid, []):
                qids.append(r["question_id"])
        print(f"\n=== {subset_name}: {len(subset_uids)} uid, "
              f"{len(qids)} 题 ===")

        per_lib_results = {}
        for lib in subset_libs:
            lib_dir = LIBRARIES[lib]
            empty_n = 0
            missing_file_n = 0
            key_vals = {}
            for uid in sorted(subset_uids & set(by_uid_rows)):
                mem_dates = _mem_dates(entries[uid])
                recs = load_records(lib_dir, uid)
                if recs is None:
                    missing_file_n += len(by_uid_rows.get(uid, []))
                    for r in by_uid_rows.get(uid, []):
                        key_vals[r["question_id"]] = ("NO_CARD_FILE", None)
                    continue
                for r in by_uid_rows.get(uid, []):
                    plan = r["plan"]
                    ev, derived = execute_plan(plan, recs, mem_dates,
                                                r["question"])
                    if not ev:
                        empty_n += 1
                    line = derived[0] if derived else ""
                    kv = extract_key_value(plan.get("op") or "", line)
                    key_vals[r["question_id"]] = (line, kv)
            per_lib_results[lib] = {
                "empty_ev": empty_n, "missing_file": missing_file_n,
                "n": len(qids), "key_vals": key_vals,
            }
            print(f"  {lib}: empty_evidence={empty_n}/{len(qids)} "
                  f"({empty_n/len(qids)*100:.1f}%), "
                  f"no_card_file={missing_file_n}/{len(qids)}")

        # 与 v42 参照逐题比对
        v42_name = [n for n in subset_libs if n.startswith("v42")][0]
        ref = per_lib_results[v42_name]["key_vals"]
        for lib in subset_libs:
            if lib == v42_name:
                continue
            cur = per_lib_results[lib]["key_vals"]
            same_line = diff_line = flip_kv = both_none = 0
            for qid in qids:
                rline, rkv = ref.get(qid, ("", None))
                cline, ckv = cur.get(qid, ("", None))
                if rline == cline:
                    same_line += 1
                else:
                    diff_line += 1
                if rkv is None and ckv is None:
                    both_none += 1
                elif rkv is not None and ckv is not None and rkv != ckv:
                    flip_kv += 1
            print(f"  [{lib} vs {v42_name}] 结论行逐字相同 "
                  f"{same_line}/{len(qids)}, 不同 {diff_line}/{len(qids)}; "
                  f"关键值不同(翻转候选) {flip_kv}/{len(qids)} "
                  f"(双方均无可摘取值 {both_none})")

        # gold 对照:code-only 关键值是否与 gold 匹配(粗粒度、非最终判分)
        gold_map = {r["question_id"]: r.get("gold_answer") for r in rows}
        for lib in subset_libs:
            kv = per_lib_results[lib]["key_vals"]
            checkable = matched = 0
            for qid in qids:
                _, v = kv.get(qid, ("", None))
                g = gold_map.get(qid)
                if v is None or g is None:
                    continue
                checkable += 1
                gs = str(g)
                vs = v if isinstance(v, str) else json.dumps(v)
                if isinstance(v, tuple):
                    ok = all(str(x).strip().lower() in gs.lower()
                             or gs.lower() in str(x).strip().lower()
                             for x in v)
                else:
                    ok = (vs.strip().lower() in gs.lower()
                          or gs.lower() in vs.strip().lower())
                matched += ok
            if checkable:
                print(f"  {lib}: code-only 关键值命中 gold(粗粒度子串匹配) "
                      f"{matched}/{checkable} = {matched/checkable*100:.1f}%")

    with open(ROOT / "results/writeside_sensitivity_part1_raw.json", "w",
              encoding="utf-8") as f:
        json.dump({"note": "see stdout capture for the table; this file "
                            "kept minimal on purpose"}, f)


if __name__ == "__main__":
    main()
