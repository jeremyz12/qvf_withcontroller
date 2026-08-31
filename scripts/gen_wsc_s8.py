# -*- coding: utf-8 -*-
"""S8 组合题集生成器:未见组合泛化测试床(纯代码金答案,零 LLM)。

组合类型(6 种;combo 字段)与 split:
  SEEN(可作编译提示词示例与 dev 床,迭代 ≤3 轮):
    WINDOW∘COUNT        单链日期窗("d1 与 d2 之间换了几次")+
                        跨槽位值窗("住 X 期间换了几次工作")
    NTH∘CMP_DUR         序数取段 + 时长比较("第二份和第三份工作哪份更久")
  UNSEEN(一次性测,测前禁触):
    WINDOW∘AGG          截断聚合("截至 d,哪个值累计持有最久")
    WINDOW_2ANCHOR∘COUNT 两值锚开窗计数("从加入 X 到加入 Y 之间换了几次")
    NTH∘JOIN_T          第 n 次变更锚定跨槽位点查("第二次搬家时雇主是谁")
    JOIN_T∘WINDOW       区间横跨计数("哪份工作横跨了至少两次搬家")

金答案纯代码从链导出,零人工裁量;歧义一律跳过(边界重合/并列最长/
锚值链内重复/双读法分歧)。干扰筛沿 S5 口径(gen_wikistate_complex.
noise_interference;跨槽位条目双家族联筛,同 gen_s6)。

数据源:
  单链  data/wikistate_full_P108.json (employer) / _P54.json (team) /
        _P551.json (residence)
  跨槽位 data/wikistate_full_multi_big.json 与(偏差,见 meta)
        data/wikistate_full_multi_P108_P551.json —— multi_big 13 条中仅
        2 条过双家族干扰筛,P108_P551 同 uid 异噪声世界另有 2 条干净,
        合计 4 个跨槽位世界;NTH∘JOIN_T / JOIN_T∘WINDOW 题数受此硬顶,
        低于 24 题规格,如实入 meta.count_deviations。

用法:
  python scripts/gen_wsc_s8.py            # 落盘 data/wsc_s8.jsonl + meta
"""
from __future__ import annotations

import argparse
import json
import sys
import zlib
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gen_wikistate_complex import (_ORDINALS, _q_slot, _slot_family,
                                           noise_interference,
                                           parse_partial_date)

OUT = ROOT / "data" / "wsc_s8.jsonl"
META = ROOT / "data" / "wsc_s8.meta.json"

SINGLE_FILES = ["data/wikistate_full_P108.json", "data/wikistate_full_P54.json",
                "data/wikistate_full_P551.json"]
MULTI_FILES = ["data/wikistate_full_multi_big.json",
               "data/wikistate_full_multi_P108_P551.json"]

SPLIT = {"WINDOW∘COUNT": "seen", "NTH∘CMP_DUR": "seen",
         "WINDOW∘AGG": "unseen", "WINDOW_2ANCHOR∘COUNT": "unseen",
         "NTH∘JOIN_T": "unseen", "JOIN_T∘WINDOW": "unseen"}

CAPS = {"WINDOW∘COUNT": 28, "NTH∘CMP_DUR": 26, "WINDOW∘AGG": 28,
        "WINDOW_2ANCHOR∘COUNT": 28, "NTH∘JOIN_T": 30, "JOIN_T∘WINDOW": 30}
ZERO_SHARE_MAX = 0.35   # 计数类零金答案占比上限


# ── 家族措辞助手(题面手写句式的构件)──────────────────────────
def _fam(slot: str) -> str:
    return _slot_family(slot)


def live_clause(slot: str, v: str) -> str:
    return {"employer": f"I was working at {v}",
            "team": f"I was playing for {v}",
            "residence": f"I was living in {v}",
            "position": f"I was serving as {v}"}[_fam(slot)]


def join_past(slot: str, v: str) -> str:
    return {"employer": f"I started at {v}", "team": f"I joined {v}",
            "residence": f"I moved to {v}",
            "position": f"I became {v}"}[_fam(slot)]


def join_gerund(slot: str, v: str) -> str:
    return {"employer": f"starting at {v}", "team": f"joining {v}",
            "residence": f"moving to {v}",
            "position": f"becoming {v}"}[_fam(slot)]


def change_vp(slot: str) -> str:
    """不定式动词短语:change employers / move to a new home ..."""
    return {"employer": "change employers", "team": "switch teams",
            "residence": "move to a new home",
            "position": "change positions"}[_fam(slot)]


def change_vp_past(slot: str) -> str:
    return {"employer": "changed employers", "team": "switched teams",
            "residence": "moved to a new home",
            "position": "changed positions"}[_fam(slot)]


def change_noun(slot: str) -> str:
    """名词短语:employer change / move ..."""
    return {"employer": "employer change", "team": "team switch",
            "residence": "move", "position": "position change"}[_fam(slot)]


def ask_value(slot: str) -> str:
    return {"employer": "who was my employer",
            "team": "which team was I playing for",
            "residence": "where was I living",
            "position": "what was my position"}[_fam(slot)]


def held_longest_clause(slot: str) -> str:
    return {"employer": "which employer had I worked at for the longest "
                        "total time",
            "team": "which team had I played for the longest total time",
            "residence": "which place had I lived in for the longest "
                         "total time",
            "position": "which position had I held for the longest "
                        "total time"}[_fam(slot)]


# ── 条目装载与前置筛 ─────────────────────────────────────────
def _parse_chain(chain) -> Tuple[List[date], List[str]]:
    parsed, notes = [], []
    for step in chain:
        dt, note = parse_partial_date(step["date"])
        parsed.append(dt)
        if note:
            notes.append(note)
    return parsed, notes


def load_single() -> List[dict]:
    """单链可用条目:len>=3、严格递增、过 S5 干扰筛;三文件轮转交错。"""
    per_file: List[List[dict]] = []
    for f in SINGLE_FILES:
        rows = []
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            chain = e.get("chain") or []
            if len(chain) < 3 or noise_interference(e):
                continue
            parsed, notes = _parse_chain(chain)
            if any(b <= a for a, b in zip(parsed, parsed[1:])):
                continue
            rows.append({"uid": e["uid"], "slot": e["slot"], "chain": chain,
                         "parsed": parsed, "notes": notes, "source": f,
                         "values": [str(s["value"]) for s in chain]})
        per_file.append(rows)
    out, i = [], 0
    while any(per_file):
        for rows in per_file:
            if i < len(rows):
                out.append(rows[i])
        if all(i >= len(rows) for rows in per_file):
            break
        i += 1
    return out


def load_cross(multi_files: Optional[List[str]] = None) -> List[dict]:
    """跨槽位可用世界:双链严格递增 + 双家族干扰筛;同 uid 优先取
    multi_big(orchestrator 列名文件),其世界不干净时回落 P108_P551。

    multi_files: 覆盖 MULTI_FILES 的来源列表(v2 用来追加渲染补齐后的新
    文件,不传时行为与 v1 逐字节一致)。"""
    files = multi_files if multi_files is not None else MULTI_FILES
    picked: Dict[str, dict] = {}
    for f in files:
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            if e["uid"] in picked:
                continue
            c2 = e.get("chain2") or {}
            ca, cb = e.get("chain") or [], c2.get("chain") or []
            if not ca or not cb:
                continue
            probe = list(ca) + list(cb)
            if any(noise_interference({"slot": fs, "chain": probe,
                                       "sessions": e.get("sessions", [])})
                   for fs in (e["slot"], c2["slot"])):
                continue
            pa, na = _parse_chain(ca)
            pb, nb = _parse_chain(cb)
            if any(y <= x for x, y in zip(pa, pa[1:])) or \
                    any(y <= x for x, y in zip(pb, pb[1:])):
                continue
            picked[e["uid"]] = {
                "uid": e["uid"], "source": f,
                "a": {"slot": e["slot"], "chain": ca, "parsed": pa,
                      "values": [str(s["value"]) for s in ca]},
                "b": {"slot": c2["slot"], "chain": cb, "parsed": pb,
                      "values": [str(s["value"]) for s in cb]},
                "notes": na + nb,
            }
    return list(picked.values())


def _date_basis(notes: List[str]) -> str:
    return ("partial dates normalized to period start: " + ", ".join(notes)
            ) if notes else "all chain dates complete"


def _today_single(ent) -> str:
    return str(ent["chain"][-1]["date"])


def _today_cross(w) -> str:
    return (str(w["a"]["chain"][-1]["date"])
            if w["a"]["parsed"][-1] >= w["b"]["parsed"][-1]
            else str(w["b"]["chain"][-1]["date"]))


def _mid(a: date, b: date) -> Optional[date]:
    gap = (b - a).days
    if gap < 2:
        return None
    m = a + timedelta(days=gap // 2)
    return m if a < m < b else None


def _h(s: str) -> int:
    return zlib.crc32(s.encode("utf-8"))


# ── 类型 1:WINDOW∘COUNT(seen)────────────────────────────────
def cand_wc_single(ent) -> List[dict]:
    """两日期窗计数:d1/d2 取两不同 gap 的严格中点,金答案 = g2-g1。"""
    p, uid = ent["parsed"], ent["uid"]
    m = len(p)
    mids = {g: _mid(p[g], p[g + 1]) for g in range(m - 1)}
    pairs = [(g1, g2) for g1 in range(m - 1) for g2 in range(g1 + 1, m - 1)
             if mids[g1] and mids[g2]]
    if not pairs:
        return []
    g1, g2 = pairs[_h(uid + "_wc") % len(pairs)]
    d1, d2 = mids[g1], mids[g2]
    gold = g2 - g1
    tset = [p[i].isoformat() for i in range(g1 + 1, g2 + 1)]
    q = {
        0: f"Between {d1.isoformat()} and {d2.isoformat()}, how many times "
           f"did I {change_vp(ent['slot'])}?",
        1: f"How many times did I {change_vp(ent['slot'])} between "
           f"{d1.isoformat()} and {d2.isoformat()}?",
        2: f"In the period from {d1.isoformat()} to {d2.isoformat()}, how "
           f"many times did my {_q_slot(ent['slot'])} change?",
        3: f"Count the number of times my {_q_slot(ent['slot'])} changed "
           f"between {d1.isoformat()} and {d2.isoformat()}.",
    }
    tid = _h(uid + "_wcT") % 4
    return [{
        "uid": uid, "qid": f"{uid}_s8wc", "combo": "WINDOW∘COUNT",
        "qtype": "s8_window_count", "world": "single",
        "slot": ent["slot"], "anchor_slot": None, "source": ent["source"],
        "template_id": f"wc_single_{tid}",
        "question": f"(Today is {_today_single(ent)}.) {q[tid]}",
        "gold": gold,
        "params": {"kind": "date_window", "g1": g1, "g2": g2,
                   "d1": d1.isoformat(), "d2": d2.isoformat()},
        "basis": (f"d1 = midpoint of chain[{g1}].start..chain[{g1 + 1}].start"
                  f" = {d1.isoformat()}, d2 = midpoint of chain[{g2}].start.."
                  f"chain[{g2 + 1}].start = {d2.isoformat()}; both strictly "
                  f"inside their gaps, so inclusive/exclusive endpoint "
                  f"readings agree; transitions strictly inside (d1, d2): "
                  f"{tset} -> gold = {gold}; " + _date_basis(ent["notes"])),
    }]


def cand_wc_cross(w) -> List[dict]:
    """值窗计数:住/在 X 期间,另一槽位换了几次;窗值链内唯一,
    被数转移落在窗边界上则该窗歧义跳过。"""
    out = []
    for wk, ck in (("a", "b"), ("b", "a")):
        W, C = w[wk], w[ck]
        c_tr = C["parsed"][1:]
        for i, wv in enumerate(W["values"]):
            if W["values"].count(wv) > 1:
                continue
            s = W["parsed"][i]
            e = W["parsed"][i + 1] if i + 1 < len(W["parsed"]) else None
            if any(t == s or (e is not None and t == e) for t in c_tr):
                continue
            inside = [t for t in c_tr if t > s and (e is None or t < e)]
            gold = len(inside)
            open_w = e is None
            qid = f"{w['uid']}_s8wc{wk}{i}"
            if open_w:
                q = {
                    0: f"Since {join_past(W['slot'], wv)}, how many times "
                       f"have I {change_vp_past(C['slot'])}?",
                    1: f"In all the time since {join_gerund(W['slot'], wv)}, "
                       f"how many times did I {change_vp(C['slot'])}?",
                }
                tid = _h(qid + "T") % 2
                tname = f"wc_cross_open_{tid}"
                qq = q[tid]
            else:
                q = {
                    0: f"While {live_clause(W['slot'], wv)}, how many times "
                       f"did I {change_vp(C['slot'])}?",
                    1: f"During the period when "
                       f"{live_clause(W['slot'], wv)}, how many times did my "
                       f"{_q_slot(C['slot'])} change?",
                    2: f"Back when {live_clause(W['slot'], wv)}, how many "
                       f"separate times did I {change_vp(C['slot'])}?",
                    3: f"Over the whole stretch that "
                       f"{live_clause(W['slot'], wv)}, count the times I "
                       f"{change_vp_past(C['slot'])}.",
                }
                tid = _h(qid + "T") % 4
                tname = f"wc_cross_{tid}"
                qq = q[tid]
            out.append({
                "uid": w["uid"], "qid": qid, "combo": "WINDOW∘COUNT",
                "qtype": "s8_window_count", "world": "cross",
                "slot": C["slot"], "anchor_slot": W["slot"],
                "source": w["source"], "template_id": tname,
                "question": f"(Today is {_today_cross(w)}.) {qq}",
                "gold": gold,
                "params": {"kind": "value_window", "w_side": wk,
                           "w_index": i, "w_value": wv},
                "basis": (f"window = {W['slot']} value '{wv}' "
                          f"[{s.isoformat()}, "
                          f"{e.isoformat() if e else 'open'}); {C['slot']} "
                          f"transitions strictly inside: "
                          f"{[t.isoformat() for t in inside]} -> gold = "
                          f"{gold}; windows whose edge coincides with a "
                          f"counted transition are skipped as ambiguous; "
                          + _date_basis(w["notes"])),
            })
    return out


# ── 类型 2:NTH∘CMP_DUR(seen)────────────────────────────────
def cand_cd(ent) -> List[dict]:
    """第 i 份 vs 第 j 份哪个更久:双闭区间、值链内唯一、时长严格不等。"""
    p, vals, uid = ent["parsed"], ent["values"], ent["uid"]
    m = len(p)
    pairs = []
    for i in range(0, m - 1):
        for j in range(i + 1, m - 1):
            vi, vj = vals[i], vals[j]
            if vi == vj or vals.count(vi) > 1 or vals.count(vj) > 1:
                continue
            di = (p[i + 1] - p[i]).days
            dj = (p[j + 1] - p[j]).days
            if di == dj or i >= len(_ORDINALS) or j >= len(_ORDINALS):
                continue
            pairs.append((i, j, di, dj))
    if not pairs:
        return []
    i, j, di, dj = pairs[_h(uid + "_cd") % len(pairs)]
    wi, wj = _ORDINALS[i], _ORDINALS[j]
    noun = _q_slot(ent["slot"])
    gold = vals[i] if di > dj else vals[j]
    q = {
        0: f"Which did I keep longer: my {wi} {noun} or my {wj} {noun}?",
        1: f"Compare my {wi} and my {wj} {noun}: which one lasted longer?",
        2: f"Did I spend more time with my {wi} {noun} or with my {wj} "
           f"{noun}?",
        3: f"Of my {wi} and {wj} {noun}s, which one did I stay with for "
           f"more time before moving on?",
    }
    tid = _h(uid + "_cdT") % 4
    return [{
        "uid": uid, "qid": f"{uid}_s8cd", "combo": "NTH∘CMP_DUR",
        "qtype": "s8_nth_cmp_dur", "world": "single",
        "slot": ent["slot"], "anchor_slot": None, "source": ent["source"],
        "template_id": f"cd_{tid}",
        "question": f"(Today is {_today_single(ent)}.) {q[tid]}",
        "gold": gold,
        "params": {"i": i, "j": j},
        "basis": (f"ordinal = 1-based chain position (both values unique in "
                  f"chain): {wi} = chain[{i}] = {vals[i]} held "
                  f"[{p[i].isoformat()}, {p[i + 1].isoformat()}) = {di} "
                  f"days; {wj} = chain[{j}] = {vals[j]} held "
                  f"[{p[j].isoformat()}, {p[j + 1].isoformat()}) = {dj} "
                  f"days; both intervals closed; {di} != {dj} -> gold = "
                  f"{gold}; " + _date_basis(ent["notes"])),
    }]


# ── 类型 3:WINDOW∘AGG(unseen)───────────────────────────────
def cand_wa(ent) -> List[dict]:
    """截至 d 持有最久:d 取 gap 严格中点;要求"含进行中部分段"与
    "仅闭区间"两种读法赢家一致且唯一,否则换切点/跳过。"""
    p, vals, uid = ent["parsed"], ent["values"], ent["uid"]
    m = len(p)
    cands = []
    for g in range(1, m - 1):
        d = _mid(p[g], p[g + 1])
        if d is None:
            continue
        # 读法 a:闭段 [t_i, t_{i+1}) for i<g + 进行中部分段 [t_g, d)
        dur_a: Dict[str, int] = {}
        for i in range(g):
            dur_a[vals[i]] = dur_a.get(vals[i], 0) + (p[i + 1] - p[i]).days
        dur_a[vals[g]] = dur_a.get(vals[g], 0) + (d - p[g]).days
        # 读法 b:仅闭区间
        dur_b: Dict[str, int] = {}
        for i in range(g):
            dur_b[vals[i]] = dur_b.get(vals[i], 0) + (p[i + 1] - p[i]).days
        wa_ = sorted(dur_a.items(), key=lambda kv: -kv[1])
        wb_ = sorted(dur_b.items(), key=lambda kv: -kv[1])
        if len(wa_) < 2 or (len(wb_) > 1 and wb_[0][1] == wb_[1][1]) or \
                (wa_[0][1] == wa_[1][1]):
            continue
        if wa_[0][0] != wb_[0][0]:
            continue
        winner = wa_[0][0]
        # 判别力:切点赢家 != 全链(闭区间口径)最长赢家 更有价值
        full: Dict[str, int] = {}
        for i in range(m - 1):
            full[vals[i]] = full.get(vals[i], 0) + (p[i + 1] - p[i]).days
        fw = sorted(full.items(), key=lambda kv: -kv[1])
        discriminative = fw and fw[0][0] != winner
        cands.append((1 if discriminative else 0, g, d, winner,
                      dur_a, dur_b))
    if not cands:
        return []
    cands.sort(key=lambda c: (-c[0], -c[1]))
    _, g, d, winner, dur_a, dur_b = cands[0]
    clause = held_longest_clause(ent["slot"])
    q = {
        0: f"As of {d.isoformat()}, {clause}?",
        1: f"Looking only at the time before {d.isoformat()}, {clause}?",
        2: f"If we stop the clock at {d.isoformat()}, {clause}?",
        3: f"Up to {d.isoformat()} — {clause}?",
    }
    tid = _h(uid + "_waT") % 4
    return [{
        "uid": uid, "qid": f"{uid}_s8wa", "combo": "WINDOW∘AGG",
        "qtype": "s8_window_agg", "world": "single",
        "slot": ent["slot"], "anchor_slot": None, "source": ent["source"],
        "template_id": f"wa_{tid}",
        "question": f"(Today is {_today_single(ent)}.) {q[tid]}",
        "gold": winner,
        "params": {"g": g, "d": d.isoformat()},
        "basis": (f"cutoff d = {d.isoformat()} = midpoint of chain[{g}].."
                  f"chain[{g + 1}] starts (strictly inside the gap); reading "
                  f"A (closed segments before d + ongoing segment clipped to "
                  f"d): {json.dumps(dur_a, ensure_ascii=False)}; reading B "
                  f"(closed segments only): "
                  f"{json.dumps(dur_b, ensure_ascii=False)}; both readings "
                  f"give the unique winner '{winner}' -> gold; ties or "
                  f"reading disagreement are skipped; "
                  + _date_basis(ent["notes"])),
    }]


# ── 类型 4:WINDOW_2ANCHOR∘COUNT(unseen)─────────────────────
def cand_w2_single(ent) -> List[dict]:
    """同链两值锚:从加入 X 到加入 Y 之间(不含两端)另外换了几次。"""
    p, vals, uid = ent["parsed"], ent["values"], ent["uid"]
    m = len(p)
    pairs = []
    for i in range(1, m - 1):
        for j in range(i + 1, m):
            vi, vj = vals[i], vals[j]
            if vi == vj or vals.count(vi) > 1 or vals.count(vj) > 1:
                continue
            pairs.append((i, j, j - i - 1))
    if not pairs:
        return []
    nz = [x for x in pairs if x[2] > 0]
    pick = nz or pairs
    i, j, gold = pick[_h(uid + "_w2") % len(pick)]
    vi, vj = vals[i], vals[j]
    slot = ent["slot"]
    q = {
        0: f"Between the day {join_past(slot, vi)} and the day "
           f"{join_past(slot, vj)}, how many times did I "
           f"{change_vp(slot)} in between — not counting those two changes "
           f"themselves?",
        1: f"After {join_gerund(slot, vi)} but before "
           f"{join_gerund(slot, vj)}, how many other times did my "
           f"{_q_slot(slot)} change?",
        2: f"Think about the stretch between {join_gerund(slot, vi)} and "
           f"{join_gerund(slot, vj)}: how many separate "
           f"{change_noun(slot)}s did I make strictly in between (excluding "
           f"those two)?",
        3: f"From when {join_past(slot, vi)} until {join_past(slot, vj)}, "
           f"how many times did I {change_vp(slot)}, leaving out those two "
           f"changes themselves?",
    }
    tid = _h(uid + "_w2T") % 4
    return [{
        "uid": uid, "qid": f"{uid}_s8w2", "combo": "WINDOW_2ANCHOR∘COUNT",
        "qtype": "s8_window2_count", "world": "single",
        "slot": slot, "anchor_slot": slot, "source": ent["source"],
        "template_id": f"w2_single_{tid}",
        "question": f"(Today is {_today_single(ent)}.) {q[tid]}",
        "gold": gold,
        "params": {"kind": "same_chain", "i": i, "j": j,
                   "vi": vi, "vj": vj},
        "basis": (f"anchors (both values unique in chain): arrival at "
                  f"'{vi}' = chain[{i}].start = {p[i].isoformat()}, arrival "
                  f"at '{vj}' = chain[{j}].start = {p[j].isoformat()}; "
                  f"transitions strictly between = chain positions "
                  f"{list(range(i + 1, j))} -> gold = {gold} (endpoints "
                  f"excluded explicitly in the question); "
                  + _date_basis(ent["notes"])),
    }]


def cand_w2_cross(w) -> List[dict]:
    """跨槽位两值锚:两锚取自锚链转移,窗内数另一槽位的转移。"""
    out = []
    for wk, ck in (("a", "b"), ("b", "a")):
        W, C = w[wk], w[ck]
        c_tr = C["parsed"][1:]
        n = len(W["parsed"])
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                vi, vj = W["values"][i], W["values"][j]
                if vi == vj or W["values"].count(vi) > 1 \
                        or W["values"].count(vj) > 1:
                    continue
                ti, tj = W["parsed"][i], W["parsed"][j]
                if any(t == ti or t == tj for t in c_tr):
                    continue
                inside = [t for t in c_tr if ti < t < tj]
                gold = len(inside)
                qid = f"{w['uid']}_s8w2{wk}{i}_{j}"
                q = {
                    0: f"Between {join_gerund(W['slot'], vi)} and "
                       f"{join_gerund(W['slot'], vj)}, how many times did I "
                       f"{change_vp(C['slot'])}?",
                    1: f"In the stretch after {join_gerund(W['slot'], vi)} "
                       f"and before {join_gerund(W['slot'], vj)}, how many "
                       f"times did my {_q_slot(C['slot'])} change?",
                    2: f"From when {join_past(W['slot'], vi)} until "
                       f"{join_past(W['slot'], vj)}, how many "
                       f"{change_noun(C['slot'])}s did I go through?",
                    3: f"Count my {change_noun(C['slot'])}s in the period "
                       f"between {join_gerund(W['slot'], vi)} and "
                       f"{join_gerund(W['slot'], vj)}.",
                }
                tid = _h(qid + "T") % 4
                out.append({
                    "uid": w["uid"], "qid": qid,
                    "combo": "WINDOW_2ANCHOR∘COUNT",
                    "qtype": "s8_window2_count", "world": "cross",
                    "slot": C["slot"], "anchor_slot": W["slot"],
                    "source": w["source"],
                    "template_id": f"w2_cross_{tid}",
                    "question": f"(Today is {_today_cross(w)}.) {q[tid]}",
                    "gold": gold,
                    "params": {"kind": "cross", "w_side": wk, "i": i,
                               "j": j, "vi": vi, "vj": vj},
                    "basis": (f"anchors on {W['slot']} chain (values unique):"
                              f" '{vi}' at {ti.isoformat()}, '{vj}' at "
                              f"{tj.isoformat()}; {C['slot']} transitions "
                              f"strictly inside ({ti.isoformat()}, "
                              f"{tj.isoformat()}): "
                              f"{[t.isoformat() for t in inside]} -> gold = "
                              f"{gold}; anchor dates coinciding with a "
                              f"counted transition are skipped as ambiguous;"
                              f" " + _date_basis(w["notes"])),
                })
    return out


# ── 类型 5:NTH∘JOIN_T(unseen)───────────────────────────────
def nth_change_clause(slot: str, word: str) -> str:
    return {"employer": f"I changed employers for the {word} time",
            "team": f"I switched teams for the {word} time",
            "residence": f"I moved for the {word} time",
            "position": f"I changed positions for the {word} time"
            }[_fam(slot)]


def nth_change_noun(slot: str, word: str) -> str:
    return {"employer": f"my {word} employer change",
            "team": f"my {word} team switch",
            "residence": f"my {word} move",
            "position": f"my {word} position change"}[_fam(slot)]


def cand_nj(w) -> List[dict]:
    """第 n 次变更(变更计数,非链位置)锚定,另一槽位当日点查。"""
    out = []
    for wk, ck in (("a", "b"), ("b", "a")):
        W, O = w[wk], w[ck]
        for n in range(1, len(W["parsed"])):
            if n > len(_ORDINALS):
                continue
            T = W["parsed"][n]
            if T < O["parsed"][0] or any(T == t for t in O["parsed"]):
                continue
            j = max(k for k, t in enumerate(O["parsed"]) if t < T)
            hi = (O["parsed"][j + 1].isoformat()
                  if j + 1 < len(O["parsed"]) else "open")
            word = _ORDINALS[n - 1]
            gold = O["values"][j]
            qid = f"{w['uid']}_s8nj{wk}{n}"
            q = {
                0: f"When {nth_change_clause(W['slot'], word)}, "
                   f"{ask_value(O['slot'])} at that moment?",
                1: f"Think back to {nth_change_noun(W['slot'], word)} — "
                   f"{ask_value(O['slot'])} then?",
                2: f"At the time of {nth_change_noun(W['slot'], word)}, "
                   f"{ask_value(O['slot'])}?",
                3: f"{ask_value(O['slot'])[0].upper()}"
                   f"{ask_value(O['slot'])[1:]} back when "
                   f"{nth_change_clause(W['slot'], word)}?",
            }
            tid = _h(qid + "T") % 4
            out.append({
                "uid": w["uid"], "qid": qid, "combo": "NTH∘JOIN_T",
                "qtype": "s8_nth_join", "world": "cross",
                "slot": O["slot"], "anchor_slot": W["slot"],
                "source": w["source"], "template_id": f"nj_{tid}",
                "question": f"(Today is {_today_cross(w)}.) {q[tid]}",
                "gold": gold,
                "params": {"w_side": wk, "n": n},
                "basis": (f"anchor = {n}-th CHANGE of {W['slot']} (change "
                          f"count, not chain position) = arrival at "
                          f"'{W['values'][n]}' = chain[{n}].start = "
                          f"{T.isoformat()}; {O['slot']} interval "
                          f"[{O['parsed'][j].isoformat()}, {hi}) covers T ->"
                          f" gold = {gold}; T before first {O['slot']} "
                          f"start or exactly on an {O['slot']} boundary is "
                          f"skipped as ambiguous; " + _date_basis(w["notes"])),
            })
    return out


# ── 类型 6:JOIN_T∘WINDOW(unseen)────────────────────────────
def cand_jw(w) -> List[dict]:
    """哪个区间横跨了(至少两次 / 最多次)另一槽位的变更。"""
    out = []
    for wk, ck in (("a", "b"), ("b", "a")):
        W, C = w[wk], w[ck]
        if len(set(W["values"])) != len(W["values"]):
            continue
        c_tr = C["parsed"][1:]
        if any(t in W["parsed"] for t in c_tr):
            continue  # 任一被数转移撞上锚链任何日期,整方向歧义
        counts = []
        for i in range(len(W["parsed"])):
            s = W["parsed"][i]
            e = (W["parsed"][i + 1] if i + 1 < len(W["parsed"]) else None)
            counts.append(len([t for t in c_tr
                               if t > s and (e is None or t < e)]))
        ge2 = [i for i, c in enumerate(counts) if c >= 2]
        if len(ge2) == 1:
            mode = "unique_ge2"
        else:
            mx = max(counts) if counts else 0
            if mx < 2 or counts.count(mx) != 1:
                continue
            ge2 = [counts.index(mx)]
            mode = "unique_argmax"
        i = ge2[0]
        gold = W["values"][i]
        wnoun = _q_slot(W["slot"])
        cnoun = change_noun(C["slot"])
        qid = f"{w['uid']}_s8jw{wk}"
        q = {
            0: f"Which {wnoun} did I keep through at least two of my "
               f"{cnoun}s?",
            1: f"There is one {wnoun} I held while my "
               f"{_q_slot(C['slot'])} changed more than once — which one?",
            2: f"During which single {wnoun} did the largest number of my "
               f"{cnoun}s happen?",
            3: f"Which {wnoun} was I with while I went through the most "
               f"{cnoun}s?",
        }
        tid = _h(qid + "T") % (2 if mode == "unique_ge2" else 4)
        if mode == "unique_argmax":
            tid = 2 + _h(qid + "T") % 2
        out.append({
            "uid": w["uid"], "qid": qid, "combo": "JOIN_T∘WINDOW",
            "qtype": "s8_join_window", "world": "cross",
            "slot": W["slot"], "anchor_slot": C["slot"],
            "source": w["source"], "template_id": f"jw_{tid}",
            "question": f"(Today is {_today_cross(w)}.) {q[tid]}",
            "gold": gold,
            "params": {"w_side": wk, "mode": mode, "win_index": i},
            "basis": (f"{C['slot']} transitions counted per {W['slot']} "
                      f"interval (strict containment; any date coincidence "
                      f"between counted transitions and anchor-chain dates "
                      f"skips the direction): counts per interval = "
                      f"{counts}; mode = {mode}; unique winner interval "
                      f"chain[{i}] -> gold = {gold}; "
                      + _date_basis(w["notes"])),
        })
    return out


# ── 选择:round-robin + 零金答案占比控制 ─────────────────────
def select(cands: List[dict], cap: int, count_type: bool) -> List[dict]:
    by_uid: Dict[str, List[dict]] = {}
    order: List[str] = []
    for c in cands:
        if c["uid"] not in by_uid:
            order.append(c["uid"])
        by_uid.setdefault(c["uid"], []).append(c)
    # 每 uid 内非零金答案优先
    if count_type:
        for u in order:
            by_uid[u].sort(key=lambda c: (c["gold"] == 0,
                                          _h(c["qid"])))
    picked: List[dict] = []
    i = 0
    while len(picked) < cap:
        advanced = False
        for u in order:
            if i < len(by_uid[u]) and len(picked) < cap:
                c = by_uid[u][i]
                if count_type and c["gold"] == 0:
                    zeros = sum(1 for x in picked if x["gold"] == 0)
                    if (zeros + 1) / (len(picked) + 1) > ZERO_SHARE_MAX \
                            and len(picked) >= 3:
                        continue
                picked.append(c)
                advanced = True
        if not advanced:
            break
        i += 1
    return picked


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extra-multi", nargs="*", default=[],
                    help="追加到 MULTI_FILES 的跨槽位来源文件(不传时 v1 "
                         "行为逐字节不变);传入时与 MULTI_FILES 拼接,"
                         "顺序在后 —— 同 uid 仍以先出现者(MULTI_FILES 原顺"
                         "序)优先,追加文件只补 MULTI_FILES 里没有的 uid。")
    ap.add_argument("--out", default=str(OUT), help="输出 jsonl 路径")
    ap.add_argument("--meta", default=str(META), help="输出 meta json 路径")
    args = ap.parse_args(argv)
    out_path = Path(args.out)
    meta_path = Path(args.meta)
    multi_files = MULTI_FILES + list(args.extra_multi)

    singles = load_single()
    crosses = load_cross(multi_files)
    print(f"usable single entries: {len(singles)}  "
          f"cross worlds: {len(crosses)} "
          f"({[w['uid'] for w in crosses]})")

    # 单链类型按错峰起点扫 uid,避免同一批 uid 承担全部题型
    def staggered(cand_fn, offset: int, need: int) -> List[dict]:
        got: List[dict] = []
        n = len(singles)
        for k in range(n):
            ent = singles[(offset + k) % n]
            got.extend(cand_fn(ent))
            if len(got) >= need:
                break
        return got

    pools: Dict[str, List[dict]] = {}
    pools["WINDOW∘COUNT"] = (cand_wc_cross_all(crosses)
                             + staggered(cand_wc_single, 0, 18))
    pools["NTH∘CMP_DUR"] = staggered(cand_cd, 20, CAPS["NTH∘CMP_DUR"])
    pools["WINDOW∘AGG"] = staggered(cand_wa, 40, CAPS["WINDOW∘AGG"])
    pools["WINDOW_2ANCHOR∘COUNT"] = (
        [c for w in crosses for c in cand_w2_cross(w)]
        + staggered(cand_w2_single, 60, 20))
    pools["NTH∘JOIN_T"] = [c for w in crosses for c in cand_nj(w)]
    pools["JOIN_T∘WINDOW"] = [c for w in crosses for c in cand_jw(w)]

    rows: List[dict] = []
    for combo, cap in CAPS.items():
        count_type = combo in ("WINDOW∘COUNT", "WINDOW_2ANCHOR∘COUNT")
        sel = select(pools[combo], cap, count_type)
        for r in sel:
            r["split"] = SPLIT[combo]
        rows.extend(sel)
        golds = [r["gold"] for r in sel]
        zshare = (sum(1 for g in golds if g == 0) / len(sel)) if sel else 0
        print(f"{combo:24s} pool={len(pools[combo]):3d} picked={len(sel):3d}"
              f" zero_share={zshare:.2f}"
              f" templates={len(set(r['template_id'] for r in sel))}")

    qids = [r["qid"] for r in rows]
    assert len(qids) == len(set(qids)), "qid collision"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_combo: Dict[str, int] = {}
    for r in rows:
        by_combo[r["combo"]] = by_combo.get(r["combo"], 0) + 1
    templates = {combo: sorted(set(r["template_id"] for r in rows
                                   if r["combo"] == combo))
                 for combo in CAPS}
    deviations = {c: n for c, n in by_combo.items() if n < 24}
    meta = {
        "date": "2026-08-15",
        "n_questions": len(rows),
        "by_combo": by_combo,
        "split": SPLIT,
        "n_seen": sum(1 for r in rows if r["split"] == "seen"),
        "n_unseen": sum(1 for r in rows if r["split"] == "unseen"),
        "sources": SINGLE_FILES + multi_files,
        "cross_worlds_used": [w["uid"] for w in crosses],
        "n_cross_worlds": len(crosses),
        "source_deviation": (
            "wikistate_full_multi_P108_P551.json added beyond the task's "
            "listed files: only 2/13 multi_big entries pass the S5-protocol "
            "dual-family noise screen; the P108_P551 renders of the same "
            "uids contribute 2 more clean worlds (4 cross worlds total) in "
            "v1. v2 additionally renders the 9 previously-unrendered "
            "P108_P551 candidates plus re-renders all 22 with a fixed "
            "distractor pipeline (STALE noise pre-screened for family/"
            "transition leak terms before mixing, in "
            "wikistate_full_multi_P108_P551_v2.json) -> more clean worlds, "
            "see n_cross_worlds/cross_worlds_used above." if multi_files
            != MULTI_FILES else
            "wikistate_full_multi_P108_P551.json added beyond the task's "
            "listed files: only 2/13 multi_big entries pass the S5-protocol "
            "dual-family noise screen; the P108_P551 renders of the same "
            "uids contribute 2 more clean worlds (4 cross worlds total)."),
        "count_deviations": deviations,
        "count_deviation_note": (
            "NTH∘JOIN_T and JOIN_T∘WINDOW are cross-slot-only combos; yield "
            "is hard-capped by the number of clean dual-chain worlds "
            "(dual-family noise screen) times the per-world ambiguity "
            "rules (boundary coincidence / before-first-start / repeated "
            "anchor values / unique-winner-segment requirement). Reported "
            "as-is; no rule was relaxed to inflate counts."),
        "gold_method": (
            "pure code from chain structure; ambiguous cases skipped "
            "(boundary coincidence, ties, repeated anchor values, "
            "dual-reading disagreement for WINDOW∘AGG); noise screen = "
            "gen_wikistate_complex.noise_interference, S5 protocol, "
            "dual-family for cross-slot worlds"),
        "question_templates": templates,
        "template_note": (
            "compile-prompt examples must NOT reuse these surface patterns "
            "(decoupling principle: examples may not come from gen "
            "templates)"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"total={len(rows)} -> {out_path}")
    print(f"meta -> {meta_path}")


def cand_wc_cross_all(crosses: List[dict]) -> List[dict]:
    return [c for w in crosses for c in cand_wc_cross(w)]


if __name__ == "__main__":
    main()
