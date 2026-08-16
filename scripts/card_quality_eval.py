# -*- coding: utf-8 -*-
"""scripts/card_quality_eval.py — 写入侧抽取质量评测器（纯代码，零 LLM）。

比较卡片库（如 results/wt_cards_v42）在三大 Wikidata 属性域上的抽取值，
与 data/wikistate_full_P*.json 自带的真值链（gold chain）：
    P108 -> slot_class "employer"     （雇主）
    P54  -> slot_class "team"         （所属球队）
    P551 -> slot_class "residence"    （居住地）

设计说明（与冻结生产路径 scripts/qvf_router._keyed_depth /
scripts/complex_query_arm._select_pool_frozen 的区别）：
本评测器只做 "按 slot_class 过滤 + 按日期排序 + 相邻同值去重"，不做生产路径
里的 owner 分组、SLOT_ALIASES 归一、深度最大组挑选等键控选池逻辑 —— 这是
故意的简化：目的是直接测量"卡片抽取"这一步本身的忠实度，不与检索/路由算法
的行为耦合。日期推导口径与冻结路径一致（见下）。

日期推导（只读复现，不 import 冻结模块，避免其模块级副作用）：
  card 记录日期 = stated_date 优先，否则 source_memory_id -> 会话日期。
  逐字节对应 scripts/wt_qvf_prototype._rec_date / _mem_dates 与
  scripts/complex_query_arm._rec_date / _mem_dates（两处实现互相一致，均只读
  未改动；本文件的 _rec_date/_mem_dates 是对它们的独立重实现，行为相同）。

输出四项：
  a. 精确匹配率：卡片链 vs 源链值序列，逐 uid 全等。
  b. 值级 P/R/F1：卡片值集 vs 源值集，归一化（大小写/标点）+ 包含关系匹配。
  c. 失败模式计数（与精确匹配互斥、四类之和 = 失败总数）：
       zero_cards         完全失败零卡（过滤+日期解析后卡片链为空）
       missing_value      漏值（卡片链更短）
       extra_value        多出值（卡片链更长）
       wrong_value_or_order 等长错值或顺序（等长但不逐一相等）
  d. 逐 uid 明细 jsonl。

用法：
  python scripts/card_quality_eval.py --card-dir results/wt_cards_v42 --split dev \
      --out-detail results/card_quality_dev_v42.jsonl

  # 或完全自定义：
  python scripts/card_quality_eval.py --card-dir results/wt_cards_v42 \
      --source data/wikistate_full_P108.json data/wikistate_full_P108_ext.json \
      --out-detail results/card_quality_p108_v42.jsonl

held-out（P551）安全阀：--split heldout 只登记 uid 数量，不加载卡片、不算指标
（纪律：循环期间严禁建卡/测量/查看 P551）。要在验收阶段真正测量 P551，须显式
传 --allow-heldout（连同 --split heldout 或手动 --source ...P551.json）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

# ── 内置切分（与本任务纪律文档一致：dev=P108+P54 全部 uid，held-out=P551 全部 uid）
DEV_SOURCES = [
    "data/wikistate_full_P108.json",
    "data/wikistate_full_P108_ext.json",
    "data/wikistate_full_P54.json",
    "data/wikistate_full_P54_ext.json",
]
HELDOUT_SOURCES = [
    "data/wikistate_full_P551.json",
]
ALL_SOURCES = DEV_SOURCES + HELDOUT_SOURCES

SLOT_FOR_PREFIX = {
    "wikiP108": "employer",
    "wikiP54": "team",
    "wikiP551": "residence",
}


# ── 冻结口径的只读重实现（不 import 冻结/生产模块，避免副作用；见文件头注释）──
def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _norm_val(s: str) -> str:
    """值级匹配用归一化：在 _norm 基础上再去标点（逗号/句点等），供 P/R 用。"""
    return " ".join(_PUNCT_RE.sub(" ", _norm(s)).split())


def _mem_dates(entry: dict) -> Dict[str, str]:
    md: Dict[str, str] = {}
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, _ in enumerate(sess.get("turns", [])):
            md[f"{entry['uid']}/s{si}#r{ri}"] = sess.get("date", "")
    return md


def _rec_date(rec: dict, mem_dates: Dict[str, str]) -> str:
    return rec.get("stated_date") or mem_dates.get(rec.get("source_memory_id", ""), "")


# ── 数据加载 ──────────────────────────────────────────────────────────
def load_source_entries(source_paths: List[str]) -> Dict[str, dict]:
    """uid -> {uid, slot, chain:[{value,date,...}], sessions:[...]}。"""
    entries: Dict[str, dict] = {}
    for p in source_paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for e in data:
            entries[e["uid"]] = e
    return entries


def load_card(card_dir: Path, uid: str) -> Optional[dict]:
    f = card_dir / f"{uid}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


# ── 核心比较逻辑 ──────────────────────────────────────────────────────
def card_sequence(card: Optional[dict], target_slot: str,
                   mem_dates: Dict[str, str]) -> Tuple[List[str], int]:
    """返回 (按 slot_class 过滤+按日期排序+相邻同值去重后的值序列, 过滤后原始池大小)。

    池大小口径：仅 slot_class == target_slot 命中的记录数（去重/日期过滤前），
    用于区分"零卡"（该域压根没抽出记录）与"抽出了但日期解析不出"两种子情形，
    详情行里两者都记录，但失败模式分类统一按最终序列是否为空判定（见下）。
    """
    if not card:
        return [], 0
    pool = [r for r in card.get("records", []) if r.get("slot_class") == target_slot]
    dated = []
    for r in pool:
        d = _rec_date(r, mem_dates)
        v = _norm(r.get("value", ""))
        if d and v:
            dated.append((d, v))
    dated.sort(key=lambda t: t[0])
    seq: List[str] = []
    for _, v in dated:
        if seq and seq[-1] == v:
            continue
        seq.append(v)
    return seq, len(pool)


def source_sequence(entry: dict) -> List[str]:
    chain = sorted(entry.get("chain", []), key=lambda c: c.get("date", ""))
    seq: List[str] = []
    for c in chain:
        v = _norm(c.get("value", ""))
        if not v:
            continue
        if seq and seq[-1] == v:
            continue
        seq.append(v)
    return seq


def classify_failure(card_seq: List[str], source_seq: List[str]) -> str:
    if card_seq == source_seq:
        return "correct"
    if len(card_seq) == 0:
        return "zero_cards"
    if len(card_seq) == len(source_seq):
        return "wrong_value_or_order"
    if len(card_seq) > len(source_seq):
        return "extra_value"
    return "missing_value"


def match_values(card_vals: List[str], source_vals: List[str]
                  ) -> Tuple[List[Tuple[str, str]], List[str], List[str]]:
    """归一化（大小写/标点）+ 包含关系的贪心一对一匹配。

    输入先各自去重（保序）。source 值按长度降序优先匹配，避免短串抢占本该
    匹配长串的名额（例如源值 "University of Cambridge" 不应被卡片里的短值
    "Cambridge" 和 "University of Cambridge, Trinity College" 都算命中后，
    让后者的匹配名额被短串抢走）。
    返回 (命中对列表, 未匹配卡片值, 未匹配源值)。
    """
    card_set = list(dict.fromkeys(v for v in card_vals if v))
    source_set = list(dict.fromkeys(v for v in source_vals if v))
    used_card: set = set()
    tp: List[Tuple[str, str]] = []
    for sv in sorted(source_set, key=len, reverse=True):
        best = None
        for i, cv in enumerate(card_set):
            if i in used_card:
                continue
            if cv == sv or cv in sv or sv in cv:
                best = i
                break
        if best is not None:
            used_card.add(best)
            tp.append((card_set[best], sv))
    unmatched_card = [cv for i, cv in enumerate(card_set) if i not in used_card]
    matched_source = {sv for _, sv in tp}
    unmatched_source = [sv for sv in source_set if sv not in matched_source]
    return tp, unmatched_card, unmatched_source


# ── 主评测流程 ────────────────────────────────────────────────────────
def evaluate(card_dir: Path, source_paths: List[str],
             uid_subset: Optional[List[str]] = None) -> Tuple[dict, List[dict]]:
    entries = load_source_entries(source_paths)
    uids = uid_subset if uid_subset is not None else sorted(entries.keys())

    rows: List[dict] = []
    n_exact = 0
    fail_counts = {"zero_cards": 0, "missing_value": 0,
                   "extra_value": 0, "wrong_value_or_order": 0}
    micro_tp = micro_card = micro_src = 0
    macro_p_sum = macro_r_sum = macro_f1_sum = 0.0

    for uid in uids:
        entry = entries.get(uid)
        if entry is None:
            rows.append({"uid": uid, "error": "uid not in source"})
            continue
        prefix = next((p for p in SLOT_FOR_PREFIX if uid.startswith(p)), None)
        target_slot = SLOT_FOR_PREFIX.get(prefix, entry.get("slot", ""))
        mem_dates = _mem_dates(entry)
        card = load_card(card_dir, uid)
        c_seq, raw_pool = card_sequence(card, target_slot, mem_dates)
        s_seq = source_sequence(entry)

        exact = c_seq == s_seq
        label = classify_failure(c_seq, s_seq)
        if exact:
            n_exact += 1
        else:
            fail_counts[label] += 1

        # 值级 P/R/F1（值集，归一化+包含匹配；用 _norm_val 做标点无关比较）
        c_vals_pr = [_norm_val(v) for v in c_seq]
        s_vals_pr = [_norm_val(v) for v in s_seq]
        tp, unmatched_c, unmatched_s = match_values(c_vals_pr, s_vals_pr)
        tp_n = len(tp)
        card_n = len(set(c_vals_pr))
        src_n = len(set(s_vals_pr))
        precision = tp_n / card_n if card_n else (1.0 if src_n == 0 else 0.0)
        recall = tp_n / src_n if src_n else (1.0 if card_n == 0 else 0.0)
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)

        micro_tp += tp_n
        micro_card += card_n
        micro_src += src_n
        macro_p_sum += precision
        macro_r_sum += recall
        macro_f1_sum += f1

        rows.append({
            "uid": uid,
            "target_slot": target_slot,
            "card_present": card is not None,
            "raw_pool_size": raw_pool,
            "card_seq": c_seq,
            "source_seq": s_seq,
            "exact_match": exact,
            "failure_mode": None if exact else label,
            "value_tp": tp_n,
            "value_card_n": card_n,
            "value_src_n": src_n,
            "value_precision": round(precision, 4),
            "value_recall": round(recall, 4),
            "value_f1": round(f1, 4),
            "unmatched_card_values": unmatched_c,
            "unmatched_source_values": unmatched_s,
        })

    n = len(uids)
    n_scored = sum(1 for r in rows if "error" not in r)
    micro_p = micro_tp / micro_card if micro_card else None
    micro_r = micro_tp / micro_src if micro_src else None
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)
                if micro_p and micro_r and (micro_p + micro_r) else None)

    summary = {
        "n_uids": n,
        "n_scored": n_scored,
        "n_exact_match": n_exact,
        "exact_match_rate": round(n_exact / n_scored, 4) if n_scored else None,
        "failure_counts": fail_counts,
        "failure_counts_sum_check": sum(fail_counts.values()),
        "value_level_micro": {
            "precision": round(micro_p, 4) if micro_p is not None else None,
            "recall": round(micro_r, 4) if micro_r is not None else None,
            "f1": round(micro_f1, 4) if micro_f1 is not None else None,
            "tp": micro_tp, "card_n": micro_card, "src_n": micro_src,
        },
        "value_level_macro": {
            "precision": round(macro_p_sum / n_scored, 4) if n_scored else None,
            "recall": round(macro_r_sum / n_scored, 4) if n_scored else None,
            "f1": round(macro_f1_sum / n_scored, 4) if n_scored else None,
        },
    }
    return summary, rows


def _resolve_paths(paths: List[str]) -> List[str]:
    out = []
    for p in paths:
        pp = Path(p)
        out.append(str(pp if pp.is_absolute() else ROOT / pp))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--card-dir", required=True)
    ap.add_argument("--source", nargs="*", default=None,
                     help="源数据文件列表（wikistate_full_P*.json）；与 --split 二选一")
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default=None,
                     help="内置切分：dev=P108+P54 全部 uid，heldout=P551 全部 uid（安全阀锁定），"
                          "all=dev+heldout（需 --allow-heldout）")
    ap.add_argument("--uids", nargs="*", default=None,
                     help="限定 uid 子集（默认用源文件里的全部 uid）")
    ap.add_argument("--out-detail", required=True, help="逐 uid 明细 jsonl 输出路径")
    ap.add_argument("--allow-heldout", action="store_true",
                     help="显式确认要测量 held-out（P551）；--split heldout/all 默认不测量，只登记数量")
    args = ap.parse_args()

    card_dir = Path(args.card_dir)
    if not card_dir.is_absolute():
        card_dir = ROOT / card_dir

    if args.split:
        if args.split == "dev":
            source_paths = _resolve_paths(DEV_SOURCES)
        elif args.split == "heldout":
            source_paths = _resolve_paths(HELDOUT_SOURCES)
        else:
            source_paths = _resolve_paths(ALL_SOURCES)
    else:
        if not args.source:
            print("必须指定 --source 或 --split", file=sys.stderr)
            sys.exit(2)
        source_paths = _resolve_paths(args.source)

    touches_heldout = args.split in ("heldout", "all")
    if touches_heldout and not args.allow_heldout:
        entries = load_source_entries(_resolve_paths(HELDOUT_SOURCES))
        print(f"[安全阀] held-out (P551) 锁定中：循环期间严禁建卡/测量/查看。")
        print(f"[安全阀] 仅登记数量，不加载卡片、不计算任何指标。")
        print(f"held-out uid 数量 = {len(entries)}")
        if args.split == "heldout":
            Path(args.out_detail).write_text("", encoding="utf-8")
            return
        # split == all 且未 --allow-heldout：退化为只跑 dev 部分
        source_paths = _resolve_paths(DEV_SOURCES)
        print("[安全阀] --split all 未带 --allow-heldout，本次仅评测 dev 部分。")

    summary, rows = evaluate(card_dir, source_paths, args.uids)

    out_detail = Path(args.out_detail)
    out_detail.parent.mkdir(parents=True, exist_ok=True)
    with open(out_detail, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n逐 uid 明细已写: {out_detail}")


if __name__ == "__main__":
    main()
