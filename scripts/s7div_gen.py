# -*- coding: utf-8 -*-
"""S7-div:发散查询题集生成器(反自考设计,纯代码、零 API)。

背景:S7 原题(gen_wikistate_complex.py --s7)与写入侧 _CATALOG_TAGS_RULE 共享
同一个 CLOSED_TAGS/SUB_TAGS 十标签词表 —— 出题、建卡、（若旗标开）读取侧
_tagged() 三处同源,构成自考闭环。S7-div 打破这一点:

  * 金答案的判据来自一份独立的种子属性词典(data/s7div_seed_ontology.json:
    食物/活动短语 -> 属性),该词典只在本文件(出题侧)被 import,建卡侧
    (wt_qvf_prototype.py)与读取侧(complex_query_arm.py/qvf_router.py/
    qvf_algebra.py)从不 import 它 —— 由 scripts/s7div_verify.py 的 grep
    断言③ 复核。
  * 问题里出现的属性词(如"高糖"/"caffeine")必须不在该 uid 名下任何卡片
    的 value / value_tags 字段中逐字出现(断言①,逐题 uid 内 scope,因为
    这是防止"字面命中"给出答案的漏题检查,而非全局禁词)。
  * 金答案 = 词典对该 uid 全部卡片 value 做机械子串匹配后的结果(断言②:
    独立复核器用另一套实现重新推导,与生成时存档的 gold 做全量比对)。

人口与 S7 原题一致:data/stale_chain_full.json (chain*) ∪
data/stale_chain_confirm.json (confirm*) 的 110 个 uid,对应
results/wt_cards/{uid}.json 已建好的卡片(QVF_CARD_TAGS 关闭时建的,故
value_tags 字段本就为空/缺失 —— 与"建卡侧从不接触种子词典"的纪律天然一致)。

dev/test 切分:按 uid 的 crc32 哈希取模,~73% dev / ~27% test,确定性、
与题目内容无关(冻结,不因产出票数调整)。test 全程封存,不用于本文件的
词典覆盖率调参 —— 词典覆盖率检查只看 dev 子集(见 --coverage-uids dev)。

用法:
  python scripts/s7div_gen.py --out data/wsc_s7div.jsonl
  python scripts/s7div_gen.py --coverage-uids dev   # 仅打印 dev 覆盖率,不写文件
"""
from __future__ import annotations

import argparse
import json
import re
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_FILES = [ROOT / "data" / "stale_chain_full.json",
              ROOT / "data" / "stale_chain_confirm.json"]
ONTOLOGY_PATH = ROOT / "data" / "s7div_seed_ontology.json"
CARDS_DIR = ROOT / "results" / "wt_cards"

MAX_ATTRS_PER_UID = 1
EVIDENCE_CAP = 12

RUBRIC_TMPL = (
    "gold is machine-derived from a seed food/activity ontology applied to "
    "the user's cards; answer must cite only items actually present in "
    "sessions, with dates; do not penalize wording, only factual coverage "
    "against gold.items")


# ── 数据装配(与 gen_wikistate_complex.py / complex_query_arm.py 同口径,
#    纯读取、不 import 冻结模块,避免拖入其重依赖) ────────────────────
def _load_entries() -> Dict[str, dict]:
    by_uid: Dict[str, dict] = {}
    for f in DATA_FILES:
        for e in json.loads(f.read_text(encoding="utf-8")):
            by_uid.setdefault(e["uid"], e)
    return by_uid


def _mem_dates(entry: dict) -> Dict[str, str]:
    """memory_id ('uid/sI#rJ') -> session date。逐字复刻
    complex_query_arm._mem_dates 的口径(独立实现,不 import 冻结模块)。"""
    md: Dict[str, str] = {}
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, _ in enumerate(sess.get("turns", [])):
            md[f"{entry['uid']}/s{si}#r{ri}"] = sess.get("date", "")
    return md


def _rec_date(rec: dict, mem_dates: Dict[str, str]) -> str:
    return rec.get("stated_date") or mem_dates.get(rec.get("source_memory_id", ""), "")


def _load_cards(uid: str) -> List[dict]:
    f = CARDS_DIR / f"{uid}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("records", [])


def _split(uid: str) -> str:
    h = zlib.crc32(uid.encode("utf-8"))
    return "test" if (h % 10) < 3 else "dev"


# ── 词典装载与编译 ───────────────────────────────────────────────
def load_ontology() -> Tuple[dict, List[Tuple[str, re.Pattern, List[str]]]]:
    doc = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    attrs = doc["attributes"]
    compiled = []
    for it in doc["items"]:
        phrase = it["phrase"]
        pat = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        compiled.append((phrase, pat, it["attrs"]))
    return attrs, compiled


def match_attrs(records: List[dict],
                 compiled: List[Tuple[str, re.Pattern, List[str]]]
                 ) -> Dict[str, List[dict]]:
    """对一个 uid 的全部卡片记录,机械推导 attr -> 命中记录列表(去重按
    record_id)。零人工裁量:纯正则子串匹配 + 词典查表。"""
    hits: Dict[str, Dict[str, dict]] = {}
    for rec in records:
        val_l = str(rec.get("value", "")).lower()
        if not val_l:
            continue
        for phrase, pat, attr_list in compiled:
            if pat.search(val_l):
                for a in attr_list:
                    hits.setdefault(a, {})[rec.get("record_id", id(rec))] = rec
    return {a: list(d.values()) for a, d in hits.items()}


def literal_leak(records: List[dict], attr_key: str, attrs_doc: dict) -> bool:
    """断言①的生成时前置版本:该 uid 的任一卡片 value/value_tags 是否逐字
    (大小写不敏感)包含该属性的查询词(中文 key 本身,或问题里出现的英文
    gloss/en_question 短语)。命中即该 uid 不得被问及此属性 —— 避免字面
    检索就能答对,失去"格闭包/语义推断"的测试意义。"""
    gloss = attrs_doc[attr_key]["gloss"].lower()
    en_q = attrs_doc[attr_key]["en_question"].lower()
    needles = {attr_key.lower(), gloss, en_q}
    for rec in records:
        val_l = str(rec.get("value", "")).lower()
        span_l = str(rec.get("source_span", "")).lower()
        tags = [str(t).lower() for t in (rec.get("value_tags") or [])]
        hay = " ".join([val_l, span_l] + tags)
        if any(n in hay for n in needles):
            return True
    return False


# ── 题目组装 ─────────────────────────────────────────────────────
def _line(rec: dict, mem_dates: Dict[str, str]) -> str:
    d = _rec_date(rec, mem_dates) or "undated"
    return f"[{d}] {rec.get('slot', 'state')}: {rec.get('value', '')}"


def gen_for_uid(uid: str, entry: dict, attrs_doc: dict,
                 compiled: List[Tuple[str, re.Pattern, List[str]]]
                 ) -> Tuple[List[dict], dict]:
    """返回 (该 uid 产出的题目列表, 诊断计数字典)。"""
    records = _load_cards(uid)
    diag = {"n_records": len(records), "n_candidate_attrs": 0,
            "n_leak_excluded": 0, "n_emitted": 0}
    if not records:
        return [], diag

    mem_dates = _mem_dates(entry)
    hits = match_attrs(records, compiled)
    split = _split(uid)

    candidates = []
    for attr_key, recs in hits.items():
        if not recs:
            continue
        if literal_leak(records, attr_key, attrs_doc):
            diag["n_leak_excluded"] += 1
            continue
        candidates.append((attr_key, recs))
    diag["n_candidate_attrs"] = len(candidates)

    # 确定性排序:命中数降序,平手按属性 key 字典序 —— 与出题量无关的
    # 内容无关排序,不针对具体条目调参。
    candidates.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    candidates = candidates[:MAX_ATTRS_PER_UID]

    rows = []
    for i, (attr_key, recs) in enumerate(candidates):
        gloss = attrs_doc[attr_key]["gloss"]
        en_q = attrs_doc[attr_key]["en_question"]
        category = attrs_doc[attr_key]["category"]
        cat_word = "eating/diet" if category == "diet" else "activity/exercise"
        dated = sorted(
            [r for r in recs if _rec_date(r, mem_dates)],
            key=lambda r: _rec_date(r, mem_dates))
        gold_items = [{"record_id": r.get("record_id", ""),
                        "value": r.get("value", ""),
                        "slot": r.get("slot", ""),
                        "date": _rec_date(r, mem_dates)}
                       for r in recs]

        qid = f"{uid}_s7div{i}"
        descr = en_q if en_q == gloss else f"{en_q} ({gloss})"
        question = (f"Looking across everything I've told you, which of my "
                    f"{cat_word} records are {descr}? List what and when.")
        rows.append({
            "uid": uid, "qid": qid, "qtype": "s7div_filter",
            "attribute": attr_key, "attribute_gloss": gloss,
            "category": category,
            "question": question,
            "gold": {"record_ids": sorted(str(r.get("record_id", ""))
                                           for r in recs),
                      "items": gold_items},
            "judge_rubric": RUBRIC_TMPL,
            "split": split,
        })

        if len(dated) >= 2:
            first = dated[0]
            qid2 = f"{uid}_s7divO{i}"
            act_word = "eating" if category == "diet" else "activity"
            q2 = (f"When did I first start showing a pattern of "
                  f"{descr} {act_word}?")
            rows.append({
                "uid": uid, "qid": qid2, "qtype": "s7div_onset",
                "attribute": attr_key, "attribute_gloss": gloss,
                "category": category,
                "question": q2,
                "gold": {"record_id": str(first.get("record_id", "")),
                          "value": first.get("value", ""),
                          "date": _rec_date(first, mem_dates)},
                "judge_rubric": RUBRIC_TMPL,
                "split": split,
            })
    diag["n_emitted"] = len(rows)
    return rows, diag


def assert_no_verbatim_query_leak(rows: List[dict], attrs_doc: dict) -> None:
    """断言①(生成后复核,独立于生成时的逐条前置过滤):对每道题,重新加载
    该 uid 的卡片,确认属性词/gloss 没有逐字出现在 value/value_tags 里。"""
    bad = []
    for row in rows:
        uid = row["uid"]
        records = _load_cards(uid)
        if literal_leak(records, row["attribute"], attrs_doc):
            bad.append(row["qid"])
    assert not bad, f"query-term verbatim leak on {len(bad)} rows: {bad[:10]}"
    print(f"[assert1] OK: 0/{len(rows)} rows leak the query term into "
          f"their own uid's cards")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data" / "wsc_s7div.jsonl"))
    ap.add_argument("--coverage-uids", choices=["all", "dev", "test"],
                     default="all",
                     help="all=正常生成写文件;dev/test=只打印覆盖率诊断,不写文件"
                          "(--coverage-uids dev 用于生成阶段的词典调参,"
                          "test 不得在生成阶段使用)")
    args = ap.parse_args()

    entries = _load_entries()
    attrs_doc, compiled = load_ontology()

    uids = sorted(entries.keys() & {p.stem for p in CARDS_DIR.glob("*.json")})
    print(f"population uids: {len(uids)}")

    if args.coverage_uids != "all":
        target = args.coverage_uids
        sub = [u for u in uids if _split(u) == target]
        n_with_hits = 0
        tot_candidates = 0
        for u in sub:
            _, diag = gen_for_uid(u, entries[u], attrs_doc, compiled)
            if diag["n_candidate_attrs"] > 0:
                n_with_hits += 1
            tot_candidates += diag["n_candidate_attrs"]
        print(f"[{target}] uids={len(sub)} uids_with_hits={n_with_hits} "
              f"avg_candidate_attrs={tot_candidates/max(1,len(sub)):.2f}")
        return

    all_rows: List[dict] = []
    n_leak_excluded = 0
    split_counts = {"dev": 0, "test": 0}
    for u in uids:
        rows, diag = gen_for_uid(u, entries[u], attrs_doc, compiled)
        n_leak_excluded += diag["n_leak_excluded"]
        all_rows.extend(rows)
        for r in rows:
            split_counts[r["split"]] += 1

    print(f"total questions: {len(all_rows)}  split={split_counts}  "
          f"leak_excluded_attr_instances={n_leak_excluded}")

    assert_no_verbatim_query_leak(all_rows, attrs_doc)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"written: {out} ({len(all_rows)} rows)")


if __name__ == "__main__":
    main()
