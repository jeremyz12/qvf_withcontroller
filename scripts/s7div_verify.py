# -*- coding: utf-8 -*-
"""S7-div 独立校验器 —— 三项断言的生成后复核,与 scripts/s7div_gen.py 的
生成逻辑刻意用不同实现路径(手写边界检查取代正则、独立重算 gold),避免
"生成器与校验器抄同一个 bug"。

断言①  查询词零逐字命中:对 data/wsc_s7div.jsonl 每一行,该 uid 的全部
        卡片 value / source_span / value_tags 都不得逐字(大小写不敏感)
        包含该题的属性中文 key、gloss、或问题里出现的 en_question 短语。
断言②  gold 可由词典 + 卡片机械重推:独立扫描器对每题重算 gold,与存档
        gold 做全量比对(record_id 集合 / onset 记录 + 日期)。
断言③  种子词典未被冻结代码引用:grep data/s7div_seed_ontology.json 的
        文件名/模块名,在 qvf_router.py / wt_qvf_prototype.py /
        complex_query_arm.py / qvf_algebra.py 四个冻结文件中必须零命中。

用法:
  python scripts/s7div_verify.py --questions data/wsc_s7div.jsonl
退出码非 0 = 有断言失败。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "results" / "wt_cards"
ONTOLOGY_PATH = ROOT / "data" / "s7div_seed_ontology.json"
DATA_FILES = [ROOT / "data" / "stale_chain_full.json",
              ROOT / "data" / "stale_chain_confirm.json"]
FROZEN_FILES = [ROOT / "scripts" / "qvf_router.py",
                 ROOT / "scripts" / "wt_qvf_prototype.py",
                 ROOT / "scripts" / "complex_query_arm.py",
                 ROOT / "scripts" / "qvf_algebra.py"]


def _load_rows(path: Path) -> List[dict]:
    rows = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _load_cards(uid: str) -> List[dict]:
    f = CARDS_DIR / f"{uid}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("records", [])


def _contains_phrase(haystack: str, phrase: str) -> bool:
    """手写边界检查版本的子串匹配(独立于生成器的 re.search 实现):在
    haystack(已小写)中找 phrase(已小写),命中位置左右字符若存在必须
    是非字母数字,否则不算整词/整短语命中。与生成器的 \\b 正则语义等价,
    但代码路径完全独立。"""
    start = 0
    n = len(phrase)
    while True:
        idx = haystack.find(phrase, start)
        if idx == -1:
            return False
        left_ok = (idx == 0) or (not haystack[idx - 1].isalnum())
        right = idx + n
        right_ok = (right == len(haystack)) or (not haystack[right].isalnum())
        if left_ok and right_ok:
            return True
        start = idx + 1


def _mem_dates(entry: dict) -> Dict[str, str]:
    md: Dict[str, str] = {}
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, _ in enumerate(sess.get("turns", [])):
            md[f"{entry['uid']}/s{si}#r{ri}"] = sess.get("date", "")
    return md


def _rec_date(rec: dict, mem_dates: Dict[str, str]) -> str:
    return rec.get("stated_date") or mem_dates.get(rec.get("source_memory_id", ""), "")


# ── 断言① ────────────────────────────────────────────────────
def assert1_no_leak(rows: List[dict], attrs_doc: dict) -> List[str]:
    failures = []
    card_cache: Dict[str, List[dict]] = {}
    for row in rows:
        uid = row["uid"]
        if uid not in card_cache:
            card_cache[uid] = _load_cards(uid)
        records = card_cache[uid]
        a = row["attribute"]
        needles = {a.lower(), attrs_doc[a]["gloss"].lower(),
                   attrs_doc[a]["en_question"].lower()}
        for rec in records:
            hay = " ".join([
                str(rec.get("value", "")).lower(),
                str(rec.get("source_span", "")).lower(),
                " ".join(str(t).lower() for t in (rec.get("value_tags") or [])),
            ])
            if any(_contains_phrase(hay, needle) for needle in needles):
                failures.append(
                    f"{row['qid']}: uid {uid} card {rec.get('record_id')} "
                    f"leaks attribute {a!r}")
                break
    return failures


# ── 断言② ────────────────────────────────────────────────────
def _is_user_record(rec: dict) -> bool:
    """entity 过滤的独立复核版本(与 s7div_gen._record_is_user 语义相同、
    实现独立):entity 缺失按约定视为用户本人。"""
    ent = rec.get("entity", "user")
    return not ent or ent == "user"


def _independent_match(records: List[dict], items: List[dict]) -> Dict[str, List[str]]:
    """与生成器 match_attrs() 语义相同、实现独立(手写边界检查 + 逐记录
    逐词条双循环,不用正则预编译)的重算。返回 attr -> record_id 列表。
    v2:附加 entity 过滤(仅用户本人)与 neg_context(命中即剔除该条)/
    require_any(非空时必须至少命中一条才算数)—— 字段名与 v2 词典
    (data/s7div_seed_ontology_v2.json)一致,取值均已 lower() 好的
    substring 列表;v1 词典没有这两个字段,.get(...,[]) 取到空列表,
    语义与断言②的 v1 行为逐字节一致。"""
    out: Dict[str, List[str]] = {}
    for rec in records:
        if not _is_user_record(rec):
            continue
        val_l = str(rec.get("value", "")).lower()
        if not val_l:
            continue
        for it in items:
            if not _contains_phrase(val_l, it["phrase"].lower()):
                continue
            neg_context = [s.lower() for s in it.get("neg_context", [])]
            if any(n in val_l for n in neg_context):
                continue
            require_any = [s.lower() for s in it.get("require_any", [])]
            if require_any and not any(n in val_l for n in require_any):
                continue
            for a in it["attrs"]:
                out.setdefault(a, [])
                rid = str(rec.get("record_id", ""))
                if rid not in out[a]:
                    out[a].append(rid)
    return out


def assert2_gold_reproducible(rows: List[dict], items: List[dict],
                                entries: Dict[str, dict]) -> List[str]:
    failures = []
    card_cache: Dict[str, List[dict]] = {}
    recomputed_cache: Dict[str, Dict[str, List[str]]] = {}
    for row in rows:
        uid = row["uid"]
        if uid not in card_cache:
            card_cache[uid] = _load_cards(uid)
            recomputed_cache[uid] = _independent_match(card_cache[uid], items)
        recomputed = recomputed_cache[uid]
        a = row["attribute"]
        # 有序去重列表(record 遍历顺序,与生成器的 dict-insertion-order 语义
        # 一致) —— onset 的并列同日期打破平局依赖这个顺序,不能转 set。
        recomputed_ordered = recomputed.get(a, [])
        recomputed_ids = set(recomputed_ordered)

        if row["qtype"] == "s7div_filter":
            stored_ids = set(row["gold"]["record_ids"])
            if stored_ids != recomputed_ids:
                failures.append(
                    f"{row['qid']}: filter gold mismatch stored={sorted(stored_ids)} "
                    f"recomputed={sorted(recomputed_ids)}")
        elif row["qtype"] == "s7div_onset":
            entry = entries.get(uid, {})
            mem_dates = _mem_dates(entry)
            recs_by_id = {str(r.get("record_id", "")): r for r in card_cache[uid]}
            dated = sorted(
                [rid for rid in recomputed_ordered
                 if _rec_date(recs_by_id.get(rid, {}), mem_dates)],
                key=lambda rid: _rec_date(recs_by_id[rid], mem_dates))
            if not dated:
                failures.append(f"{row['qid']}: onset recompute has no dated hits")
                continue
            recomputed_first = dated[0]
            recomputed_date = _rec_date(recs_by_id[recomputed_first], mem_dates)
            if (row["gold"]["record_id"] != recomputed_first
                    or row["gold"]["date"] != recomputed_date):
                failures.append(
                    f"{row['qid']}: onset gold mismatch stored="
                    f"{row['gold']['record_id']}/{row['gold']['date']} "
                    f"recomputed={recomputed_first}/{recomputed_date}")
    return failures


# ── 断言③ ────────────────────────────────────────────────────
def assert3_not_referenced_by_frozen() -> List[str]:
    failures = []
    needles = ["s7div_seed_ontology", "s7div_gen"]
    for f in FROZEN_FILES:
        if not f.exists():
            failures.append(f"frozen file missing: {f}")
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for n in needles:
            if n in text:
                failures.append(f"{f.name} references {n!r}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", default=str(ROOT / "data" / "wsc_s7div.jsonl"))
    ap.add_argument("--ontology", default=str(ONTOLOGY_PATH),
                     help="种子词典路径,须与生成 --questions 时用的词典一致"
                          "(v1 题集配 v1 词典,v2 题集配 "
                          "data/s7div_seed_ontology_v2.json)。")
    args = ap.parse_args()

    rows = _load_rows(Path(args.questions))
    doc = json.loads(Path(args.ontology).read_text(encoding="utf-8"))
    attrs_doc, items = doc["attributes"], doc["items"]
    entries: Dict[str, dict] = {}
    for f in DATA_FILES:
        for e in json.loads(f.read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)

    print(f"rows: {len(rows)}")

    f1 = assert1_no_leak(rows, attrs_doc)
    print(f"[assert1 verbatim-leak] failures: {len(f1)}")
    for x in f1[:10]:
        print("  ", x)

    f2 = assert2_gold_reproducible(rows, items, entries)
    print(f"[assert2 gold-reproducible] failures: {len(f2)} / {len(rows)}")
    for x in f2[:10]:
        print("  ", x)

    f3 = assert3_not_referenced_by_frozen()
    print(f"[assert3 frozen-code-isolation] failures: {len(f3)}")
    for x in f3:
        print("  ", x)

    total_fail = len(f1) + len(f2) + len(f3)
    if total_fail:
        print(f"\nFAILED: {total_fail} total failures")
        sys.exit(1)
    print("\nALL ASSERTIONS PASS")


if __name__ == "__main__":
    main()
