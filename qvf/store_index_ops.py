# -*- coding: utf-8 -*-
"""
qvf/store_index_ops.py — 11 算子的索引版求值器(execute_plan_indexed),
产出与 scripts/complex_query_arm.py::execute_plan 逐字节相同的证据包
(ev 行 + derived 行),数据来源换成 qvf/store_index.py 的物化索引而非
每题现场扫描+排序。冻结代码只读导入,不编辑。

对拍纪律:任何 derived 行文案改动都必须与 complex_query_arm.execute_plan
逐字比对——本文件的字符串模板是从该函数原样抄出的,改动需同步双方或
在 scripts/store_index_equiv.py 里报出不等价。
"""
from __future__ import annotations

import json
from typing import List

from qvf.store_index import StoreIndex, content_fingerprint, sort_key  # noqa: F401
from scripts.complex_query_arm import (  # noqa: E402
    EVIDENCE_CAP, _rec_date, _pdate, _label, _line, _ordinal_en, _COUNT_OPS,
    _norm,
)


def _exec_join_indexed(plan: dict, index: StoreIndex, question: str = ""):
    slot = plan.get("slot") or ""
    slot2 = plan.get("slot2") or ""
    pv = _norm(plan.get("presupposed") or "")
    ai = plan.get("anchor_index")
    if not isinstance(ai, int) or isinstance(ai, bool):
        ai = None
    ev: List[str] = []
    derived: List[str] = []
    md = index.mem_dates

    a_chain = index.select_chain(slot, question, hygiene=False)
    if ai is not None:
        if 1 <= ai <= len(a_chain):
            anchor = a_chain[ai - 1]
        else:
            ev = [_line(r, md) for r in a_chain]
            derived.append(
                f"Ordinal anchor out of range: the question refers to the "
                f"user's {_ordinal_en(ai)} "
                f"{slot or 'anchor-attribute'} value, but only "
                f"{len(a_chain)} dated state(s) are known in memory, so the "
                f"cross-attribute lookup cannot be resolved. Say so instead "
                f"of guessing.")
            return ev[:EVIDENCE_CAP], derived
    else:
        anchor = next(
            (r for r in a_chain
             if pv and (pv in _norm(r.get("value", ""))
                        or _norm(r.get("value", "")) in pv)), None)
        if anchor is None:
            ev = [_line(r, md) for r in a_chain]
            derived.append(
                f"Anchor not found: no dated {slot or 'anchor-attribute'} "
                f"record matching '{plan.get('presupposed') or ''}' exists "
                f"in memory, so the cross-attribute lookup cannot be "
                f"resolved. Say so instead of guessing.")
            return ev[:EVIDENCE_CAP], derived

    a_label = _label(anchor)
    a_value = anchor.get("value", "")
    t_raw = _rec_date(anchor, md)
    ev.append(_line(anchor, md))
    if ai is not None:
        derived.append(
            f"Ordinal anchor resolved: the user's {_ordinal_en(ai)} "
            f"{a_label} (1-based over the dated history) is {a_value}.")
    qd = _pdate(t_raw)
    if qd is None:
        derived.append(
            f"Anchor found (the user's {a_label} changed to {a_value}) but "
            f"its date '{t_raw}' is unparseable, so the cross-attribute "
            f"lookup cannot be resolved.")
        return ev[:EVIDENCE_CAP], derived

    b_chain = index.select_chain(slot2, question, hygiene=False)
    if not b_chain:
        derived.append(
            f"The user's {a_label} changed to {a_value} on {t_raw}, but no "
            f"dated record of {slot2 or 'the other asked attribute'} exists "
            f"in memory to look up at that date.")
        return ev[:EVIDENCE_CAP], derived
    b_dates = [_rec_date(r, md) for r in b_chain]
    b_values = [str(r.get("value", "")) for r in b_chain]
    b_label = _label(b_chain[-1])
    gi = index.asof(slot2, qd, question, hygiene=False)
    if gi is None:
        ev.append(_line(b_chain[0], md))
        derived.append(
            f"The user's {a_label} changed to {a_value} on {t_raw}, which "
            f"predates every known state of {b_label}; the earliest known "
            f"{b_label} is {b_values[0]} from {b_dates[0]}.")
        return ev[:EVIDENCE_CAP], derived
    ev += [_line(r, md) for r in b_chain[max(0, gi - 1):gi + 2]]
    until = (f", unchanged until {b_dates[gi + 1]}"
             if gi + 1 < len(b_chain) else "")
    derived.append(
        f"The user's {a_label} changed to {a_value} on {t_raw}; on that "
        f"date the user's {b_label} was {b_values[gi]} (recorded "
        f"{b_dates[gi]}{until}). This IS the answer.")
    return ev[:EVIDENCE_CAP], derived


def execute_plan_indexed(plan: dict, index: StoreIndex, question: str = ""):
    """索引版 execute_plan;签名与语义对齐 complex_query_arm.execute_plan,
    唯一输入差异是第二参数换成已建好的 StoreIndex(而不是 recs 列表)。"""
    op = plan.get("op") or "current"
    slot = plan.get("slot") or ""
    md = index.mem_dates
    ev: List[str] = []
    derived: List[str] = []

    if op == "join_at_change":
        return _exec_join_indexed(plan, index, question)

    if op in ("tag_filter", "tag_trend"):
        tag = plan.get("tag") or ""
        hits = index.tag_index.get((tag or "").strip(), [])
        ev = [_line(r, md) for r in hits]
        if not hits:
            derived.append(f"No stored item carries the tag {tag}.")
        elif op == "tag_filter":
            derived.append(
                f"{len(hits)} stored item(s) carry the tag {tag}; every one "
                f"is listed above with its date. Mention ONLY these items, "
                f"each with its date; do not add or infer anything beyond "
                f"them.")
        else:
            by_year: dict = {}
            for r in hits:
                y = (_rec_date(r, md) or "undated")[:4]
                by_year.setdefault(y, []).append(str(r.get("value", "")))
            seq = "; ".join(f"{y}: " + ", ".join(vs)
                            for y, vs in sorted(by_year.items()))
            derived.append(
                f"Items tagged {tag} by year — {seq}. Describe what was "
                f"mentioned and how it evolved, citing ONLY these items "
                f"with their dates; state trends only when two or more "
                f"listed items directly show them, never by inference.")
        return ev[:EVIDENCE_CAP], derived

    hygiene = op in _COUNT_OPS
    chain = index.select_chain(slot, question, hygiene=hygiene)
    ev = [_line(r, md) for r in chain]
    if not chain:
        derived.append("No dated record found for "
                       f"{slot or 'the asked attribute'} in memory.")
        return ev[:EVIDENCE_CAP], derived
    label = _label(chain[-1])
    dates = [_rec_date(r, md) for r in chain]
    values = [str(r.get("value", "")) for r in chain]

    if op in ("current", "premise_check"):
        derived.append(f"The user's current {label} is {values[-1]} "
                       f"(since {dates[-1]}).")
        pv = _norm(plan.get("presupposed") or "")
        if op == "premise_check" and pv:
            stale = next(
                (r for r in chain[:-1]
                 if pv in _norm(r.get("value", ""))
                 or _norm(r.get("value", "")) in pv), None)
            if stale is not None:
                derived.append(
                    f"IMPORTANT: the message presupposes "
                    f"{stale.get('value', '')}, which is OUTDATED — the "
                    f"user's current {label} is {values[-1]}. Correct this "
                    f"premise before helping.")
    elif op == "point_in_time":
        qd = _pdate(plan.get("date") or "")
        gi = index.asof(slot, qd, question, hygiene=False)
        if qd is None or gi is None:
            derived.append(
                f"The asked date predates every known state of {label}; the "
                f"earliest known state is {values[0]} from {dates[0]}.")
        else:
            until = (f", unchanged until {dates[gi + 1]}"
                     if gi + 1 < len(chain) else "")
            derived.append(
                f"On {plan.get('date')}, the user's {label} was {values[gi]} "
                f"(recorded {dates[gi]}{until}). This IS the answer.")
    elif op == "trajectory":
        seq = " -> ".join(f"{v} (from {d})" for v, d in zip(values, dates))
        derived.append(f"Full evolution of the user's {label}: {seq}. "
                       f"Give the complete ordered history.")
    elif op == "count_changes":
        n = len(chain) - 1
        derived.append(
            f"The user's {label} changed {n} time(s) — {len(chain)} "
            f"successive states: " + " -> ".join(values) + ".")
    elif op == "longest":
        per_value: dict = {}
        parsed = [_pdate(d) for d in dates]
        for i in range(len(chain) - 1):
            if parsed[i] is not None and parsed[i + 1] is not None:
                per_value[values[i]] = (per_value.get(values[i], 0)
                                        + (parsed[i + 1] - parsed[i]).days)
        if per_value:
            best = max(per_value.values())
            winners = [v for v, d in per_value.items() if d == best]
            derived.append(
                f"Held longest (closed intervals only): {winners[0]} "
                f"({best} days). Closed days per value: "
                + json.dumps(per_value, ensure_ascii=False) + ".")
        else:
            derived.append(
                f"Only one dated state of {label} is known "
                f"({values[-1]} since {dates[-1]}); no closed interval to "
                f"compare.")
    elif op == "count_before":
        qd = _pdate(plan.get("date") or "")
        before = [v for v, d in zip(values, dates)
                  if qd is not None and _pdate(d) is not None
                  and _pdate(d) < qd]
        distinct = sorted(set(before), key=before.index)
        derived.append(
            f"Before {plan.get('date')}, the user had {len(distinct)} "
            f"different {label} value(s): " + (", ".join(distinct) or "none")
            + ".")
    elif op == "first_last":
        derived.append(
            f"First {label}: {values[0]} (from {dates[0]}); most recent: "
            f"{values[-1]} (since {dates[-1]}).")
    return ev[:EVIDENCE_CAP], derived
