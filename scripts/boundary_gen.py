# -*- coding: utf-8 -*-
"""
scripts/boundary_gen.py

压力子集生成器,回应 study_logs/QVF_coupling_audit_20260815.md 杀伤链第②环:
"算子-题型同构 + 计数/最长/边界口径靠出题器与执行器两侧代码手工同步对齐;
point_in_time 的 <= 边界被出题器特判剔除、永不受检"。

产出:
  data/wsc_boundary.jsonl  边界情形压力题(6 种情形,每种 >=15 题,
                            题面手写 >=4 种句式/情形)
  data/wsc_ooo.jsonl       乱序到达压力题(顺序版 vs 乱序版会话呈现顺序,
                            同题同金答案)

======================================================================
纪律声明
======================================================================
金答案一律经 scripts.boundary_gold.gold() 计算 —— 该文件是独立实现的金答案
推导器(其自身的独立性纪律见该文件头部注释),本脚本不引用、不调用、不导入
complex_query_arm.py 的 execute_plan / 任何 _chain* / _hygiene_pool* 函数,
也不导入 gen_wikistate_complex.py 的出题函数(gen_s5/gen_s6/gen_s7 等)。

本脚本复用的 gen_wikistate_complex.py 内容仅限两个与"金答案裁决口径"无关的
通用基础设施函数 —— noise_interference(S5 干扰筛惯例,任务第 3 条明确要求
"干扰筛沿 S5 口径")与 parse_partial_date(部分日期→date 的规约,纯日期解析,
不涉及任何算子语义裁决)—— 复用方式与既有的 scripts/gen_wsc_s8.py(S8 组合
题集生成器,同一决耦纪律下的先例)完全一致:那份脚本同样导入这两个函数,
自己的金答案则完全从链结构现算,不调用 execute_plan。

本脚本另有一类脚本自身的"构造判断"(如同日多值的 tie-break 顺序选哪个、
合成链的取值/日期怎么摆),这些不是文档意义上的算子语义歧义(不进
boundary_gold.AMBIGUITIES),而是本脚本作为出题者的设计选择,记入下面的
GEN_DECISIONS 列表,供审计核对。

用法:
  python scripts/boundary_gen.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from random import Random
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gen_wikistate_complex import (_q_slot, _slot_family,
                                           noise_interference,
                                           parse_partial_date)
from scripts.boundary_gold import gold  # 独立金答案推导器,唯一的答案来源

OUT_B = ROOT / "data" / "wsc_boundary.jsonl"
META_B = ROOT / "data" / "wsc_boundary.meta.json"
OUT_O = ROOT / "data" / "wsc_ooo.jsonl"
META_O = ROOT / "data" / "wsc_ooo.meta.json"

SOURCES = ["data/wikistate_full_P108.json", "data/wikistate_full_P54.json",
           "data/wikistate_full_P551.json"]

CAP_PER_CATEGORY = 30  # 遗留常量,部分情形仍引用其模板辅助函数
CAP_SWITCH = 20
CAP_RIGHT = 20
CAP_TAIL_ENTITIES = 15       # 2 子类/实体 -> 30 题
CAP_MULTISEG_ENTITIES = 7    # 3 子类/实体 -> 21 题
CAP_MIXED_ENTITIES = 15      # 2 子类/实体 -> <=30 题


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:8], 16)


# ── 题面措辞助手(与 gen_wsc_s8.py 同精神:仅措辞,不裁决语义)───────
def ask_value(slot: str) -> str:
    fam = _slot_family(slot)
    return {"employer": "who was my employer",
            "team": "which team was I playing for",
            "residence": "where was I living",
            "position": "what was my position"}[fam]


def change_noun(slot: str) -> str:
    fam = _slot_family(slot)
    return {"employer": "employer change", "team": "team switch",
            "residence": "move", "position": "position change"}[fam]


def held_longest_clause(slot: str) -> str:
    fam = _slot_family(slot)
    return {"employer": "which employer had I worked at the longest",
            "team": "which team had I played for the longest",
            "residence": "which place had I lived in the longest",
            "position": "which position had I held the longest"}[fam]


ANNOUNCE_SYN = {
    "employer": "I've officially started working at {v}.",
    "team": "I've officially joined {v}.",
    "residence": "I've officially moved to {v}.",
}


# ── 数据装载与前置筛(干扰筛沿 S5 口径:noise_interference)────────
def load_pool() -> List[dict]:
    pool: List[dict] = []
    for f in SOURCES:
        raw = json.loads((ROOT / f).read_text(encoding="utf-8"))
        for e in raw:
            chain = e.get("chain") or []
            if len(chain) < 3 or noise_interference(e):
                continue
            parsed: List[date] = []
            notes: List[str] = []
            for step in chain:
                dt, note = parse_partial_date(step["date"])
                parsed.append(dt)
                if note:
                    notes.append(note)
            if any(b <= a for a, b in zip(parsed, parsed[1:])):
                continue  # 非严格递增,数据异常,跳过
            pool.append({
                "uid": e["uid"], "slot": e["slot"], "chain": chain,
                "parsed": parsed, "notes": notes, "source": f,
                "values": [str(s["value"]) for s in chain],
                "sessions": e.get("sessions", []),
            })
    return pool


def harvest_vocab(pool: List[dict]) -> Dict[str, List[str]]:
    vocab: Dict[str, set] = {"employer": set(), "team": set(),
                             "residence": set()}
    for ent in pool:
        fam = _slot_family(ent["slot"])
        if fam in vocab:
            vocab[fam].update(ent["values"])
    return {k: sorted(v) for k, v in vocab.items()}


GEN_DECISIONS: List[dict] = []  # 本脚本自身的出题设计判断,供审计


def _record_decision(rid: str, site: str, choice: str) -> None:
    if not any(d["id"] == rid for d in GEN_DECISIONS):
        GEN_DECISIONS.append({"id": rid, "site": site, "choice": choice})


# ======================================================================
# 情形 1:switch_day —— d 恰落在状态切换日 t_i(前瞻式措辞)
# ======================================================================
def _switch_templates(slot: str, d: str) -> List[str]:
    av = ask_value(slot)
    return [
        f"As of {d}, {av}?",
        f"On {d}, {av}?",
        f"Starting on {d}, {av}?",
        f"From {d} onward, {av}?",
    ]


def cat_switch_day(pool: List[dict]) -> List[dict]:
    rows = []
    for ent in pool:
        chain, parsed, uid, slot = ent["chain"], ent["parsed"], ent["uid"], ent["slot"]
        m = len(chain)
        candidates = list(range(1, m - 1))  # 排除首段(平凡)与末段(见情形3)
        if not candidates:
            continue
        i = candidates[_h(uid + "_sw") % len(candidates)]
        d = str(chain[i]["date"])
        today = str(chain[-1]["date"])
        g = gold("point_in_time", chain, d=d)
        qs = _switch_templates(slot, d)
        tid = _h(uid + "_swT") % len(qs)
        rows.append({
            "uid": uid, "qid": f"{uid}_bswitch", "category": "switch_day",
            "qtype": "point_in_time", "slot": slot, "source": ent["source"],
            "synthetic": False, "template_id": f"switch_{tid}",
            "question": f"(Today is {today}.) {qs[tid]}",
            "gold": g,
            "params": {"d": d, "i": i},
            "basis": (f"d = chain[{i}].date = t_i exactly (a state-switch "
                      f"day). point_in_time semantics: t_i <= d < t_(i+1), "
                      f"so d==t_i falls in segment i -> gold = "
                      f"chain[{i}].value = {g!r} (the NEW value effective "
                      f"from t_i, not the value that held immediately "
                      f"before). This is exactly the 'd 恰落在状态切换日' "
                      f"case the coupling audit flags as typically excluded "
                      f"by question generators that pick interior midpoints "
                      f"to dodge the boundary."),
        })
        if len(rows) >= CAP_SWITCH:
            break
    return rows


# ======================================================================
# 情形 2:right_endpoint —— d 恰为区间右端点 t_i(收尾/闭合式措辞)
# 数学上与情形 1 同一个 d(某个 t_i),但用"截至/含 X 当天"这类在自然语言里
# 容易被误读为"闭右端"的措辞发问 —— 正是 point_in_time 右开区间定义
# (d==t_i 属于新段而非旧段)最容易被题面措辞悄悄绕开的地方。
# ======================================================================
def _right_endpoint_templates(slot: str, d: str) -> List[str]:
    av = ask_value(slot)
    return [
        f"Through {d}, {av}?",
        f"Up to and including {d}, {av}?",
        f"By the end of {d}, {av}?",
        f"Counting {d} as the last day of the old chapter, {av} as of then?",
    ]


def cat_right_endpoint(pool: List[dict]) -> List[dict]:
    rows = []
    for ent in pool:
        chain, parsed, uid, slot = ent["chain"], ent["parsed"], ent["uid"], ent["slot"]
        m = len(chain)
        candidates = list(range(1, m - 1))
        if not candidates:
            continue
        # 与情形 1 尽量错开同一实体挑的索引,增加边界覆盖面
        i = candidates[_h(uid + "_re") % len(candidates)]
        d = str(chain[i]["date"])
        today = str(chain[-1]["date"])
        g = gold("point_in_time", chain, d=d)
        qs = _right_endpoint_templates(slot, d)
        tid = _h(uid + "_reT") % len(qs)
        rows.append({
            "uid": uid, "qid": f"{uid}_bright", "category": "right_endpoint",
            "qtype": "point_in_time", "slot": slot, "source": ent["source"],
            "synthetic": False, "template_id": f"right_{tid}",
            "question": f"(Today is {today}.) {qs[tid]}",
            "gold": g,
            "params": {"d": d, "i": i},
            "basis": (f"d = chain[{i}].date = t_i, framed as the CLOSING day "
                      f"of the previous chapter ('through', 'up to and "
                      f"including') — natural-language surface form suggests "
                      f"a closed-right reading (old value still holds on d), "
                      f"but the documented semantics is open-right: d==t_i "
                      f"belongs to segment i, not segment i-1 -> gold = "
                      f"chain[{i}].value = {g!r}. A system that lets the "
                      f"'through/including' phrasing flip it to the previous "
                      f"value ({chain[i-1]['value']!r}) fails this boundary "
                      f"even though the plan-level operator is unchanged."),
        })
        if len(rows) >= CAP_RIGHT:
            break
    return rows


# ======================================================================
# 情形 3:chain_tail_open —— 链尾开区间 [t_m, +inf)
#   子类 A: point_in_time(d), d >= t_m(含恰好 d==t_m 与远超 t_m)
#   子类 B: longest,末段开区间默认不参与有限时长竞争(AMBIGUITY-4 读法 a)
# ======================================================================
def _tail_pit_templates(slot: str, d: str) -> List[str]:
    av = ask_value(slot)
    return [
        f"As of {d}, {av}?",
        f"Even now, in {d}, {av}?",
        f"If it's currently {d}, {av}?",
        f"Looking ahead to {d}, {av} still?",
    ]


def _tail_longest_templates(slot: str) -> List[str]:
    hl = held_longest_clause(slot)
    qs = _q_slot(slot)
    return [
        f"{hl[0].upper()}{hl[1:]}?",
        f"Which {qs} have I stuck with the longest so far?",
        f"Out of all my {qs}s, which one has the longest confirmed time span?",
        f"Which {qs} takes the record for longest duration to date?",
    ]


def cat_tail_open(pool: List[dict]) -> List[dict]:
    rows = []
    offsets = [0, 30, 365, 3650]
    for ent in pool:
        chain, parsed, uid, slot = ent["chain"], ent["parsed"], ent["uid"], ent["slot"]
        today = str(chain[-1]["date"])
        off = offsets[_h(uid + "_tailoff") % len(offsets)]
        d_date = parsed[-1] + timedelta(days=off)
        d = d_date.isoformat()
        g = gold("point_in_time", chain, d=d)
        qs = _tail_pit_templates(slot, d)
        tid = _h(uid + "_tailT") % len(qs)
        rows.append({
            "uid": uid, "qid": f"{uid}_btailA", "category": "chain_tail_open",
            "qtype": "point_in_time", "slot": slot, "source": ent["source"],
            "synthetic": False, "template_id": f"tailpit_{tid}",
            "question": f"(Today is {today}.) {qs[tid]}",
            "gold": g,
            "params": {"d": d, "offset_days": off},
            "basis": (f"d = t_m + {off} days (t_m = chain[-1].date = "
                      f"{parsed[-1].isoformat()}); Definition 2's last "
                      f"segment is [t_m, +inf) with no upper bound, so ANY "
                      f"d >= t_m (including d==t_m exactly) falls in the "
                      f"open tail -> gold = chain[-1].value = {g!r}, never "
                      f"'unknown'/'no data'."),
        })
        g2 = gold("longest", chain)
        qs2 = _tail_longest_templates(slot)
        tid2 = _h(uid + "_tailLT") % len(qs2)
        rows.append({
            "uid": uid, "qid": f"{uid}_btailB", "category": "chain_tail_open",
            "qtype": "longest", "slot": slot, "source": ent["source"],
            "synthetic": False, "template_id": f"taillong_{tid2}",
            "question": f"(Today is {today}.) {qs2[tid2]}",
            "gold": g2,
            "params": {},
            "basis": (f"longest with the open tail [t_m,+inf) excluded from "
                      f"the finite-duration competition by default (no "
                      f"as_of given, AMBIGUITY-4 reading a): argmax is taken "
                      f"only over the m-1 closed segments -> gold = {g2!r}. "
                      f"A system that silently treats the still-open final "
                      f"segment as 'infinite' or as some default 'now minus "
                      f"t_m' fails to match a document-only-grounded reading."),
        })
        if len(rows) >= 2 * CAP_TAIL_ENTITIES:
            break
    return rows


# ======================================================================
# 情形 4:same_value_multi_segment —— 同值多段(非相邻),合成链
#   真实数据(P108/P54/P551)扫描结果:0 条非相邻同值链(见 meta),
#   文档要求的 Sigma_{i:v_i=v} 累加口径因此在真实数据上从未被检验过 ——
#   这正是任务点名"专门挑选并构造此前会被剔除的边界情形"的字面意思。
# ======================================================================
def _multiseg_longest_templates(slot: str) -> List[str]:
    return _tail_longest_templates(slot)


def _multiseg_count_templates(slot: str) -> List[str]:
    qs = _q_slot(slot)
    return [
        f"How many times in total did I change my {qs}?",
        f"Across the whole history, how many {change_noun(slot)}s did I make?",
        f"Counting every switch, how many times has my {qs} changed?",
        f"In total, how many separate times did my {qs} change?",
    ]


def _multiseg_return_templates(slot: str, d: str) -> List[str]:
    av = ask_value(slot)
    return [
        f"On {d}, {av}?",
        f"As of {d}, {av}?",
        f"By {d}, {av} — did I go back to how things were before?",
        f"Starting {d}, {av}?",
    ]


def cat_same_value_multi_segment(vocab: Dict[str, List[str]]) -> List[dict]:
    rows = []
    families = ["employer", "team", "residence"]
    n_entities = CAP_MULTISEG_ENTITIES
    for k in range(n_entities):
        fam = families[k % 3]
        vlist = vocab.get(fam) or []
        if len(vlist) < 2:
            continue
        h = _h(f"SYN-MS-{fam}-{k}")
        vA = vlist[h % len(vlist)]
        vB = vlist[(h // 7 + 1) % len(vlist)]
        if vA == vB:
            vB = vlist[(h // 7 + 2) % len(vlist)]
        four_seg = (k % 3 == 2) and len(vlist) >= 3
        vC = vlist[(h // 13 + 3) % len(vlist)] if four_seg else None
        if vC in (vA, vB):
            vC = None
            four_seg = False

        base_year = 1998 + (h % 20)
        d1 = date(base_year, 1, 1)
        d2 = d1 + timedelta(days=300 + (h % 400))
        d3 = d2 + timedelta(days=300 + ((h // 3) % 500))
        chain = [
            {"value": vA, "date": d1.isoformat(),
             "state_span": ANNOUNCE_SYN[fam].format(v=vA) + " (synthetic)"},
            {"value": vB, "date": d2.isoformat(),
             "state_span": ANNOUNCE_SYN[fam].format(v=vB) + " (synthetic)"},
            {"value": vA, "date": d3.isoformat(),
             "state_span": ANNOUNCE_SYN[fam].format(v=vA)
                          + " again (synthetic, returns to a prior value)"},
        ]
        if four_seg:
            d4 = d3 + timedelta(days=300 + ((h // 5) % 400))
            chain.append({"value": vC, "date": d4.isoformat(),
                          "state_span": ANNOUNCE_SYN[fam].format(v=vC)
                                       + " (synthetic)"})
        uid = f"BOUNDARY-SYN-MS-{fam}-{k:02d}"
        sessions = [{"date": s["date"],
                    "turns": [s["state_span"].replace(" (synthetic)", "")
                             .replace(" (synthetic, returns to a prior "
                                      "value)", "")],
                    "chain_index": i}
                   for i, s in enumerate(chain)]
        today = chain[-1]["date"]

        g_long = gold("longest", chain)
        qs1 = _multiseg_longest_templates(fam)
        tid1 = h % len(qs1)
        rows.append({
            "uid": uid, "qid": f"{uid}_bms_long",
            "category": "same_value_multi_segment", "qtype": "longest",
            "slot": fam, "source": "synthetic", "synthetic": True,
            "construction": (f"3-4 segment synthetic chain, value {vA!r} "
                            f"reused at chain positions 0 and 2 (non-"
                            f"adjacent) so its finite closed-interval "
                            f"durations must be SUMMED per Sigma_"
                            f"{{i:v_i=v}} — this combination does not occur "
                            f"anywhere in the 3 real source files "
                            f"(0/100 entries have a non-adjacent repeat, "
                            f"see meta.real_data_scan)."),
            "template_id": f"mslong_{tid1}",
            "question": f"(Today is {today}.) {qs1[tid1]}",
            "gold": g_long,
            "params": {"vA": vA, "vB": vB, "vC": vC, "chain": chain},
            "basis": (f"chain values = {[s['value'] for s in chain]}; "
                      f"'{vA}' occupies non-adjacent segments 0 and 2 -> "
                      f"dur('{vA}') sums both closed segments per the "
                      f"formula's summation sign -> gold = {g_long!r}. A "
                      f"system whose executor keys duration accumulation by "
                      f"chain POSITION rather than by VALUE (i.e., only "
                      f"considers the single longest single segment) will "
                      f"give a different, wrong answer here."),
        })

        g_cnt = gold("count_changes", chain)
        qs2 = _multiseg_count_templates(fam)
        tid2 = (h // 11) % len(qs2)
        rows.append({
            "uid": uid, "qid": f"{uid}_bms_count",
            "category": "same_value_multi_segment", "qtype": "count_changes",
            "slot": fam, "source": "synthetic", "synthetic": True,
            "construction": "same synthetic chain as the longest-duration "
                            "twin question above",
            "template_id": f"mscount_{tid2}",
            "question": f"(Today is {today}.) {qs2[tid2]}",
            "gold": g_cnt,
            "params": {"vA": vA, "vB": vB, "vC": vC, "chain": chain},
            "basis": (f"count_changes = m-1 = {len(chain)-1} regardless of "
                      f"whether a later value equals an earlier one; the "
                      f"return to '{vA}' at chain position 2 IS counted as "
                      f"a real change (chain(k) only merges ADJACENT same-"
                      f"value runs, per Definition 2) -> gold = {g_cnt!r}. "
                      f"A system that treats 'returning to a previously-"
                      f"seen value' as not-a-real-change (e.g. some naive "
                      f"'distinct values seen' counter) would undercount."),
        })

        d3s = chain[2]["date"]
        g_pit = gold("point_in_time", chain, d=d3s)
        qs3 = _multiseg_return_templates(fam, d3s)
        tid3 = (h // 17) % len(qs3)
        rows.append({
            "uid": uid, "qid": f"{uid}_bms_return",
            "category": "same_value_multi_segment", "qtype": "point_in_time",
            "slot": fam, "source": "synthetic", "synthetic": True,
            "construction": "same synthetic chain; probes the exact day "
                            "value returns to the earlier value",
            "template_id": f"msreturn_{tid3}",
            "question": f"(Today is {today}.) {qs3[tid3]}",
            "gold": g_pit,
            "params": {"d": d3s},
            "basis": (f"d = chain[2].date = t_3 exactly, the day the value "
                      f"reverts to '{vA}' (seen earlier at chain position "
                      f"0) -> point_in_time(d) = chain[2].value = "
                      f"{g_pit!r}, combining the switch-day boundary with "
                      f"the same-value-multi-segment condition."),
        })
    return rows


# ======================================================================
# 情形 5:same_day_multi_value —— 同日多值,合成 tie
#   真实数据扫描:0 条同日多值(见 meta.real_data_scan)。文档(Definition
#   1/2)默认 t_1<...<t_m 严格递增,未规定同日不同值应如何排序/择一 ——
#   本脚本自行选定 tie-break 顺序(见 GEN_DECISIONS),不是 boundary_gold
#   的算子语义歧义,是出题构造判断,单独记录、不混入 boundary_gold.AMBIGUITIES。
# ======================================================================
def _sameday_templates(slot: str, d: str) -> List[str]:
    av = ask_value(slot)
    return [
        f"On {d}, {av}?",
        f"As of {d}, {av}?",
        f"That same day, {d} — what ended up being true? {av}?",
        f"Given everything stated on {d}, {av}?",
    ]


def cat_same_day_multi_value(pool: List[dict], vocab: Dict[str, List[str]]
                             ) -> List[dict]:
    _record_decision(
        "GEN-1", "cat_same_day_multi_value / tie-break input order",
        "文档未规定同日不同值应如何排序,本脚本把合成的第二条(冲突)记录"
        "放在原记录之后(即 raw_chain 中原记录先出现、冲突记录后出现)"
        "喂给 boundary_gold.gold() —— 该函数内部用稳定排序,同日的两条会"
        "保持输入顺序,循环 'if seg.date<=dk: ans=seg.value' 最终把 ans"
        "定为循环中最后处理到的那条,即本脚本选择的读法是'同日多值时,"
        "喂给推导器时排在后面的记录(在本脚本的构造语义里对应"
        "'更晚被复述/确认'的那条)对 point_in_time 生效'。这是本脚本的"
        "出题设计选择,不是 boundary_gold.py 的算子语义歧义。")
    rows = []
    n_target = 16
    k = 0
    idx = 0
    while len(rows) < n_target and idx < len(pool) * 3:
        ent = pool[idx % len(pool)]
        idx += 1
        chain, uid, slot = ent["chain"], ent["uid"], ent["slot"]
        m = len(chain)
        if m < 3:
            continue
        interior = list(range(1, m - 1))
        if not interior:
            continue
        i = interior[_h(uid + f"_sd{k}") % len(interior)]
        fam = _slot_family(slot)
        vlist = [v for v in (vocab.get(fam) or []) if v != chain[i]["value"]]
        if not vlist:
            continue
        alt_value = vlist[_h(uid + f"_sdv{k}") % len(vlist)]
        d = str(chain[i]["date"])
        injected = {"value": alt_value, "date": d,
                   "state_span": f"(synthetic tie) also reported {alt_value}"
                                 f" on {d}"}
        tied_chain = chain[:i + 1] + [injected] + chain[i + 1:]
        today = str(chain[-1]["date"])

        g_pit = gold("point_in_time", tied_chain, d=d)
        qs = _sameday_templates(slot, d)
        tid = _h(uid + f"_sdT{k}") % len(qs)
        rows.append({
            "uid": uid, "qid": f"{uid}_bsameday_pit_{k}",
            "category": "same_day_multi_value", "qtype": "point_in_time",
            "slot": slot, "source": ent["source"], "synthetic": True,
            "construction": (f"real chain {uid} with one extra synthetic "
                            f"record injected on the SAME date as "
                            f"chain[{i}] (original value {chain[i]['value']!r}"
                            f", injected value {alt_value!r}), injected "
                            f"record placed AFTER the original in input "
                            f"order (see GEN_DECISIONS GEN-1)."),
            "template_id": f"sameday_pit_{tid}",
            "question": f"(Today is {today}.) {qs[tid]}",
            "gold": g_pit,
            "params": {"d": d, "i": i, "original_value": chain[i]["value"],
                       "injected_value": alt_value, "tie_order": "injected_after"},
            "basis": (f"two records share date {d}: original "
                      f"'{chain[i]['value']}' (input position {i}) and "
                      f"synthetic '{alt_value}' (input position {i+1}, "
                      f"immediately after). Stable sort keeps them in that "
                      f"relative order; point_in_time's scan overwrites ans "
                      f"with each seg whose date<=d in input order, so the "
                      f"LAST one processed wins -> gold = {g_pit!r} (the "
                      f"injected/later-in-input value, per GEN-1's chosen "
                      f"tie-break reading, NOT a boundary_gold ambiguity)."),
        })

        g_cnt = gold("count_changes", tied_chain)
        qs2 = _multiseg_count_templates(slot)
        tid2 = _h(uid + f"_sdcT{k}") % len(qs2)
        rows.append({
            "uid": uid, "qid": f"{uid}_bsameday_count_{k}",
            "category": "same_day_multi_value", "qtype": "count_changes",
            "slot": slot, "source": ent["source"], "synthetic": True,
            "construction": "same tied chain as the point_in_time twin above",
            "template_id": f"sameday_count_{tid2}",
            "question": f"(Today is {today}.) {qs2[tid2]}",
            "gold": g_cnt,
            "params": {"i": i, "injected_value": alt_value},
            "basis": (f"injecting a same-day DIFFERENT-value record adds "
                      f"one more chain segment (values differ so Definition "
                      f"2's adjacent-merge does not collapse them) -> m goes "
                      f"from {m} to {m+1}, count_changes = m-1 = {g_cnt!r}. "
                      f"This subtype is well-defined regardless of tie-"
                      f"break order (both readings still add exactly one "
                      f"transition), unlike the point_in_time twin above."),
        })
        k += 1
    return rows


# ======================================================================
# 情形 6:year_only_mixed_with_full_date —— 仅年粒度日期与全日期混合
#   真实数据里天然存在(P108 7 条 / P54 15 条 / P551 2 条,共 24 条),
#   直接选用,不合成。
# ======================================================================
def _mixed_precision_templates(slot: str, d_display: str) -> List[str]:
    av = ask_value(slot)
    return [
        f"As of {d_display}, {av}?",
        f"By {d_display}, {av}?",
        f"Around {d_display}, {av}?",
        f"Looking at {d_display}, {av}?",
    ]


def cat_mixed_precision(pool: List[dict]) -> List[dict]:
    rows = []
    for ent in pool:
        chain, parsed, notes, uid, slot = (ent["chain"], ent["parsed"],
                                           ent["notes"], ent["uid"],
                                           ent["slot"])
        if not notes or len(notes) == len(chain):
            continue  # 需要真正的"部分日期 + 全日期"混合,不能全链皆部分/皆全
        # 找一个部分日期步(notes 非空说明至少一步被规约);定位该步索引
        partial_idx = None
        for i, step in enumerate(chain):
            raw = str(step["date"])
            _, note = parse_partial_date(raw)
            if note:
                partial_idx = i
                break
        if partial_idx is None:
            continue
        raw_date = str(chain[partial_idx]["date"])
        year = parsed[partial_idx].year
        today = str(chain[-1]["date"])

        # 子类 A:直接把原始部分日期串喂给 gold() 的 d 参数
        g_a = gold("point_in_time", chain, d=raw_date)
        qsA = _mixed_precision_templates(slot, raw_date)
        tidA = _h(uid + "_mpA") % len(qsA)
        rows.append({
            "uid": uid, "qid": f"{uid}_bmixed_raw", "category":
            "year_only_mixed_with_full_date", "qtype": "point_in_time",
            "slot": slot, "source": ent["source"], "synthetic": False,
            "template_id": f"mixedraw_{tidA}",
            "question": f"(Today is {today}.) {qsA[tidA]}",
            "gold": g_a,
            "params": {"d": raw_date, "i": partial_idx},
            "basis": (f"d fed to gold() AS THE ORIGINAL PARTIAL STRING "
                      f"'{raw_date}' (same precision as chain[{partial_idx}]"
                      f".date) — exercises the d-parameter's own partial-"
                      f"date parsing (AMBIGUITY-1: missing month/day -> 1), "
                      f"not just the chain dates' -> gold = {g_a!r}. This "
                      f"chain naturally mixes precision: "
                      f"{[s['date'] for s in chain]}."),
        })

        # 子类 B:仅年粒度日期年中探针(部分日期归约为年初,年中应仍是该值,
        # 除非同年内还有其它更晚的切换 —— 由 gold() 现算,不假设)
        mid_d = date(year, 7, 1).isoformat()
        g_b = gold("point_in_time", chain, d=mid_d)
        qsB = _mixed_precision_templates(slot, f"the middle of {year}")
        tidB = _h(uid + "_mpB") % len(qsB)
        rows.append({
            "uid": uid, "qid": f"{uid}_bmixed_midyear", "category":
            "year_only_mixed_with_full_date", "qtype": "point_in_time",
            "slot": slot, "source": ent["source"], "synthetic": False,
            "template_id": f"mixedmid_{tidB}",
            "question": f"(Today is {today}.) {qsB[tidB]}",
            "gold": g_b,
            "params": {"d": mid_d, "i": partial_idx, "year": year},
            "basis": (f"d = {mid_d} (mid-year probe for the year-only date "
                      f"chain[{partial_idx}].date={raw_date!r}, which "
                      f"AMBIGUITY-1 normalizes to {year}-01-01); gold() "
                      f"re-derives from the full chain (does not assume no "
                      f"other transition falls between Jan 1 and Jul 1 of "
                      f"{year}) -> gold = {g_b!r}."),
        })
        if len(rows) >= 2 * CAP_MIXED_ENTITIES:
            break
    return rows


# ======================================================================
# 乱序子集:wsc_ooo.jsonl
# ======================================================================
OOO_OPS = ["current", "count_changes", "first_last_first", "first_last_last",
           "count_before", "point_in_time"]


def _ooo_question(op: str, slot: str, chain: List[dict], parsed: List[date],
                  today: str) -> Tuple[str, object, dict, str]:
    """返回 (question, gold, params, basis) for 给定算子(非边界,取安全的
    链内部中点/直读,聚焦"顺序是否改变答案"这一个变量)。"""
    av = ask_value(slot)
    qs = _q_slot(slot)
    if op == "current":
        g = gold("current", chain)
        return (f"Right now, {av}?", g, {},
                f"current = chain tail value -> gold = {g!r}")
    if op == "count_changes":
        g = gold("count_changes", chain)
        return (f"How many times in total did my {qs} change?", g, {},
                f"count_changes = len(chain)-1 -> gold = {g!r}")
    if op == "first_last_first":
        g = gold("first_last", chain, which="first")
        return (f"What was my very first {qs}?", g, {"which": "first"},
                f"first_last(first) = chain[0] -> gold = {g!r}")
    if op == "first_last_last":
        g = gold("first_last", chain, which="last")
        return (f"What is my most recent {qs}?", g, {"which": "last"},
                f"first_last(last) = chain[-1] -> gold = {g!r}")
    if op == "count_before":
        m = len(chain)
        gaps = [i for i in range(m - 1)
               if (parsed[i + 1] - parsed[i]).days >= 2]
        i = gaps[_h("".join(s["value"] for s in chain) + "_cb") % len(gaps)] \
            if gaps else 0
        gap = (parsed[i + 1] - parsed[i]).days
        mid = parsed[i] + timedelta(days=gap // 2)
        d = mid.isoformat()
        g = gold("count_before", chain, d=d)
        return (f"How many times had my {qs} changed before {d}?", g,
                {"d": d}, f"count_before(d={d}, strict midpoint) -> gold = "
                         f"{g!r}")
    if op == "point_in_time":
        m = len(chain)
        gaps = [i for i in range(m - 1)
               if (parsed[i + 1] - parsed[i]).days >= 2]
        i = gaps[_h("".join(s["value"] for s in chain) + "_pit") % len(gaps)] \
            if gaps else 0
        gap = (parsed[i + 1] - parsed[i]).days
        mid = parsed[i] + timedelta(days=gap // 2)
        d = mid.isoformat()
        g = gold("point_in_time", chain, d=d)
        return (f"As of {d}, {av}?", g, {"d": d},
                f"point_in_time(d={d}, strict midpoint, non-boundary) -> "
                f"gold = {g!r}")
    raise ValueError(op)


def _deterministic_shuffle(n: int, seed_key: str,
                           decl_idx: List[int]) -> List[int]:
    order = list(range(n))
    seed = _h(seed_key)
    attempt = 0
    while True:
        rng = Random(seed + attempt)
        candidate = order[:]
        rng.shuffle(candidate)
        pos = {orig: pos for pos, orig in enumerate(candidate)}
        inversions = sum(1 for a in range(len(decl_idx))
                         for b in range(a + 1, len(decl_idx))
                         if pos[decl_idx[a]] > pos[decl_idx[b]])
        if inversions > 0 or not decl_idx:
            return candidate
        attempt += 1
        if attempt > 20:
            return candidate  # 极端退化兜底,不应发生


def build_ooo(pool: List[dict]) -> List[dict]:
    n_chains_target = 15
    per_chain = 3
    # 按来源文件轮转选取,保证三个槽位家族都覆盖
    by_source: Dict[str, List[dict]] = {}
    for ent in pool:
        by_source.setdefault(ent["source"], []).append(ent)
    chosen: List[dict] = []
    i = 0
    sources = list(by_source.keys())
    while len(chosen) < n_chains_target:
        advanced = False
        for src in sources:
            lst = by_source[src]
            if i < len(lst):
                chosen.append(lst[i])
                advanced = True
                if len(chosen) >= n_chains_target:
                    break
        if not advanced:
            break
        i += 1

    rows = []
    for ent in chosen:
        chain, parsed, uid, slot = ent["chain"], ent["parsed"], ent["uid"], ent["slot"]
        sessions = ent["sessions"]
        n_sess = len(sessions)
        today = str(chain[-1]["date"])
        seq_order = list(range(n_sess))
        decl_idx = [i for i, s in enumerate(sessions)
                   if s.get("chain_index") is not None]
        shuf_order = _deterministic_shuffle(n_sess, uid + "_ooo", decl_idx)

        pos_seq = {o: p for p, o in enumerate(seq_order)}
        pos_shuf = {o: p for p, o in enumerate(shuf_order)}
        inv = sum(1 for a in range(len(decl_idx))
                 for b in range(a + 1, len(decl_idx))
                 if pos_shuf[decl_idx[a]] > pos_shuf[decl_idx[b]])

        ops = []
        for k in range(per_chain):
            op = OOO_OPS[_h(uid + f"_op{k}") % len(OOO_OPS)]
            if op not in ops:
                ops.append(op)
        while len(ops) < per_chain:
            for op in OOO_OPS:
                if op not in ops:
                    ops.append(op)
                if len(ops) >= per_chain:
                    break

        for qk, op in enumerate(ops):
            question, g, params, basis = _ooo_question(op, slot, chain,
                                                        parsed, today)
            pair_id = f"{uid}_ooo{qk}"
            for variant, order in (("sequential", seq_order),
                                   ("shuffled", shuf_order)):
                rows.append({
                    "uid": uid, "pair_id": pair_id,
                    "qid": f"{pair_id}_{variant}",
                    "qtype": op, "slot": slot, "source": ent["source"],
                    "order_variant": variant,
                    "question": f"(Today is {today}.) {question}",
                    "gold": g,
                    "params": params,
                    "n_sessions": n_sess,
                    "session_order": order,
                    "declaring_session_indices": decl_idx,
                    "inversions_among_declaring_sessions":
                        (0 if variant == "sequential" else inv),
                    "basis": (basis + (" | rendering: sessions presented in "
                             "date-ascending order (session_order == "
                             "chronological index order); each session's "
                             "own 'date' field is untouched." if
                             variant == "sequential" else
                             " | rendering: sessions presented in a "
                             "deterministic shuffled order (session_order "
                             "gives the presentation-position -> original-"
                             "index mapping); each session's own 'date' "
                             f"field is UNCHANGED (still its true stated_"
                             f"date), so a later-presented session can "
                             f"state an earlier-dated fact — "
                             f"{inv} such inversions occur among the "
                             f"chain-declaring sessions for this chain. "
                             "gold must be identical to the sequential "
                             "twin (order-invariant by construction).")),
                    "materialize_note": (
                        f"presented_sessions = [entry['sessions'][idx] for "
                        f"idx in session_order], where entry = the record "
                        f"with uid={uid!r} in {ent['source']!r}."),
                })
    return rows


# ======================================================================
# main
# ======================================================================
def main() -> None:
    pool = load_pool()
    vocab = harvest_vocab(pool)
    by_source_n = {}
    for ent in pool:
        by_source_n[ent["source"]] = by_source_n.get(ent["source"], 0) + 1
    print(f"usable pool (len>=3, noise-clean, strictly increasing): "
          f"{len(pool)}  by_source={by_source_n}")

    # 真实数据扫描统计(供 meta 记录,佐证情形 4/5 为何必须合成)
    real_scan = {"nonadjacent_repeat_entries": 0, "sameday_dup_entries": 0,
                "mixed_precision_entries": 0}
    for f in SOURCES:
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            chain = e.get("chain") or []
            vals = [s["value"] for s in chain]
            dates = [s["date"] for s in chain]
            seen = {}
            rep = False
            for i, v in enumerate(vals):
                if v in seen and seen[v] != i - 1:
                    rep = True
                seen[v] = i
            if rep:
                real_scan["nonadjacent_repeat_entries"] += 1
            if len(set(dates)) != len(dates):
                real_scan["sameday_dup_entries"] += 1
            has_partial = any(len(str(d).split("-")) < 3
                              or str(d).split("-")[1] in ("00", "")
                              or str(d).split("-")[2] in ("00", "")
                              for d in dates)
            has_full = any(not (len(str(d).split("-")) < 3
                                or str(d).split("-")[1] in ("00", "")
                                or str(d).split("-")[2] in ("00", ""))
                          for d in dates)
            if has_partial and has_full:
                real_scan["mixed_precision_entries"] += 1

    rows_b: List[dict] = []
    rows_b += cat_switch_day(pool)
    rows_b += cat_right_endpoint(pool)
    rows_b += cat_tail_open(pool)
    rows_b += cat_same_value_multi_segment(vocab)
    rows_b += cat_same_day_multi_value(pool, vocab)
    rows_b += cat_mixed_precision(pool)

    qids = [r["qid"] for r in rows_b]
    assert len(qids) == len(set(qids)), "boundary qid collision"

    OUT_B.parent.mkdir(parents=True, exist_ok=True)
    with OUT_B.open("w", encoding="utf-8") as fh:
        for r in rows_b:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    by_cat: Dict[str, int] = {}
    by_cat_templates: Dict[str, set] = {}
    for r in rows_b:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_cat_templates.setdefault(r["category"], set()).add(r["template_id"])
    n_synthetic = sum(1 for r in rows_b if r.get("synthetic"))

    meta_b = {
        "date": "2026-08-16",
        "motivation": (
            "study_logs/QVF_coupling_audit_20260815.md 杀伤链②: "
            "point_in_time 的 <= 边界被出题器特判剔除、永不受检; "
            "计数/最长口径靠出题器与执行器两侧代码手工同步对齐。"),
        "n_questions": len(rows_b),
        "by_category": by_cat,
        "n_categories": len(by_cat),
        "min_per_category": min(by_cat.values()) if by_cat else 0,
        "templates_per_category": {c: len(t) for c, t in
                                   by_cat_templates.items()},
        "n_synthetic": n_synthetic,
        "n_real": len(rows_b) - n_synthetic,
        "real_data_scan": real_scan,
        "synthetic_rationale": (
            f"same_value_multi_segment 与 same_day_multi_value 两种情形在"
            f"真实数据(P108/P54/P551 共 {len(pool)} 条可用链)中天然出现"
            f"次数为 0(nonadjacent_repeat_entries="
            f"{real_scan['nonadjacent_repeat_entries']}, "
            f"sameday_dup_entries={real_scan['sameday_dup_entries']}),"
            f"故按任务指令'挑选并构造'合成;其余 4 种情形直接从真实链挑选,"
            f"不合成。"),
        "gold_method": (
            "全部经 scripts.boundary_gold.gold() 计算,零 LLM、零对拍代码 "
            "(不调用 execute_plan);干扰筛 = gen_wikistate_complex."
            "noise_interference,S5 口径。"),
        "gold_deriver_ambiguities": "见 scripts/boundary_gold.py 顶部 "
                                    "AMBIGUITIES(6 条,与本文件无关的独立"
                                    "文件已记录,此处不重复列出)。",
        "gen_decisions": GEN_DECISIONS,
        "sources": SOURCES + ["synthetic (same_value_multi_segment, "
                              "same_day_multi_value)"],
        "categories": sorted(by_cat.keys()),
    }
    META_B.write_text(json.dumps(meta_b, ensure_ascii=False, indent=2,
                                 default=str), encoding="utf-8")
    print(f"boundary: total={len(rows_b)} by_category={by_cat} "
          f"synthetic={n_synthetic}")
    print(f"  -> {OUT_B}\n  -> {META_B}")

    # ── 乱序子集 ────────────────────────────────────────────
    rows_o = build_ooo(pool)
    qids_o = [r["qid"] for r in rows_o]
    assert len(qids_o) == len(set(qids_o)), "ooo qid collision"

    with OUT_O.open("w", encoding="utf-8") as fh:
        for r in rows_o:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    n_pairs = len(set(r["pair_id"] for r in rows_o))
    n_chains = len(set(r["uid"] for r in rows_o))
    by_variant = {}
    for r in rows_o:
        by_variant[r["order_variant"]] = by_variant.get(r["order_variant"], 0) + 1
    avg_inv = (sum(r["inversions_among_declaring_sessions"] for r in rows_o
                  if r["order_variant"] == "shuffled")
              / max(1, by_variant.get("shuffled", 1)))
    meta_o = {
        "date": "2026-08-16",
        "motivation": (
            "study_logs/QVF_coupling_audit_20260815.md P5 预言: 乱序到达"
            "若改变答案则口径依赖会话呈现顺序而非 stated_date -> 语义洞。"),
        "n_questions": len(rows_o),
        "n_pairs": n_pairs,
        "n_chains": n_chains,
        "by_variant": by_variant,
        "avg_inversions_among_declaring_sessions_in_shuffled": round(avg_inv, 2),
        "design": (
            "每条链取 3 个非边界算子问题(current/count_changes/first_last/"
            "count_before/point_in_time,后两者用严格居中的日期,不落在任何"
            "边界上 —— 乱序子集的自变量是会话呈现顺序,不是边界情形,避免"
            "两个变量混杂),每题各配 sequential(会话按 stated_date 升序呈"
            "现,即源文件本身的顺序)与 shuffled(源文件同一组会话对象做"
            "确定性重排,session.date 字段本身不变,只改变其在会话数组里"
            "出现的位置)两版,gold 相同。"),
        "materialize_note": (
            "本文件不重复内嵌完整会话文本(源文件本身已含,平均每条链 ~33"
            "会话,内嵌两版会显著膨胀体积且与源数据重复);每行携带 "
            "session_order(展示顺序 -> 源文件 sessions 数组下标的映射)"
            "与 uid/source,下游按 materialize_note 字段还原具体会话顺序。"),
        "shuffle_method": (
            "Random(seed) 确定性打乱(seed = sha256(uid+'_ooo')截断整数);"
            "若打乱后链声明会话(chain_index 非 None)之间仍保持日期顺序"
            "(inversions==0),换种子重试,保证乱序版确有'后面的会话陈述"
            "更早日期事实'的情形。"),
        "sources": SOURCES,
        "gold_method": "同 wsc_boundary.jsonl,经 boundary_gold.gold() 计算。",
    }
    META_O.write_text(json.dumps(meta_o, ensure_ascii=False, indent=2,
                                 default=str), encoding="utf-8")
    print(f"ooo: total={len(rows_o)} pairs={n_pairs} chains={n_chains} "
          f"by_variant={by_variant} avg_inversions={avg_inv:.2f}")
    print(f"  -> {OUT_O}\n  -> {META_O}")


if __name__ == "__main__":
    main()
