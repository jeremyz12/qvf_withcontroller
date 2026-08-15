# -*- coding: utf-8 -*-
"""组合式时序代数(QVF_ALGEBRA=1 门控;默认关,平面路径逐字节不变)。

§7.2 P1 命题槽的构造性实现:6 原语 + 深度 ≤3 表达式树 + 递归解释器;
11 个现行算子(complex_query_arm.OPS)全部定义为宏(派生形式),证据包
渲染逐字节复用平面分支的字符串模板 —— 护栏 = 宏执行 vs 平面执行在
S5 全量 + S6 + S7 切片上证据包逐字节等价(scripts/algebra_parity.py,零 LLM)。

── 原语集 P(6 个;类型:Chain=有序去重状态链 / Rec=单记录 / Loc=链上
   定位 / Value=聚合值)────────────────────────────────────────────
  SELECT(slot, hygiene)   : () → Chain     键控选池(_select_pool)→
                                           [hygiene: _hygiene_pool] → _chain
  TAGSET(tag)             : () → Chain     跨键标签命中集,按日期排序
  WINDOW(of, before)      : Chain → Chain  严格早于 before 的子链
                                           (before 不可解析 → 空链)
  PICK(of, index|value)   : Chain → Rec?   序数取元(1-based;-1=链尾)或
                                           值锚(_norm 双向包含;
                                           exclude_last=True 时搜 chain[:-1],
                                           premise_check 的"过时值"语义)
  ASOF(of, date|at)       : Chain×Date → Loc  右开区间点查:gi = 最大 i
                                           使 t_i ≤ d;at=子表达式(Rec)时
                                           取其记录日期为 d(时序 join ——
                                           JOIN_T 由此被 ASOF 吸收,不独立
                                           设原语)
  AGG(of, fn)             : Chain → Value  fn ∈ {count_changes,
                                           distinct_ordered, argmax_dur,
                                           by_year}

── 宏定义表(构造性完备证明;C = SELECT(slot),Cʰ = SELECT(slot,H),
   G = TAGSET(tag);深度 = 树高)──────────────────────────────────
  current          = PICK(C, -1)                                   深度 2
  point_in_time(d) = ASOF(C, d)                                    深度 2
  trajectory       = C                                             深度 1
  premise_check(v̂) = ⟨PICK(C, -1), PICK(C, v̂, excl_last)⟩          深度 2
  count_changes    = AGG(Cʰ, count_changes)                        深度 2
  longest          = AGG(Cʰ, argmax_dur)                           深度 2
  count_before(d)  = AGG(WINDOW(Cʰ, d), distinct_ordered)          深度 3
  first_last       = ⟨PICK(Cʰ, 1), PICK(Cʰ, -1)⟩                   深度 2
  tag_filter(g)    = G                                             深度 1
  tag_trend(g)     = AGG(G, by_year)                               深度 2
  join_at_change   = ASOF(SELECT(slot2), at=PICK(C, v̂ | n))        深度 3
(⟨·,·⟩ 二元组宏实现为单树 + trace:第二分量沿共享子树 C 读出,不重算。)

新代码全部在本文件与 algebra_parity.py;complex_query_arm.py 仅在
QVF_ALGEBRA=1 时把 execute_plan / COMPILE_PROMPT / CompiledPlan 重绑到
本模块导出,旗标关时不导入本文件。
"""
from __future__ import annotations

import json
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from scripts.complex_query_arm import (EVIDENCE_CAP, _COUNT_OPS, _chain,
                                       _hygiene_pool, _label, _line,
                                       _ordinal_en, _pdate, _rec_date,
                                       _select_pool, _tagged)
from scripts.wt_qvf_prototype import _norm

_AGG_FNS = ("count_changes", "distinct_ordered", "argmax_dur", "by_year")


# ── AST(pydantic 显式嵌套,结构上深度 ≤3)──────────────────────
class LeafExpr(BaseModel):
    """深度 1:库上的选择原语(SELECT / TAGSET)。"""
    prim: Literal["SELECT", "TAGSET"]
    slot: Optional[str] = Field(default=None, description="SELECT: attribute")
    hygiene: bool = Field(default=False,
                          description="SELECT: apply count-op hygiene filter")
    tag: Optional[str] = Field(default=None, description="TAGSET: tag label")


class MidExpr(BaseModel):
    """深度 2:单参组合原语,子式必为叶。"""
    prim: Literal["PICK", "ASOF", "WINDOW", "AGG"]
    of: LeafExpr
    index: Optional[int] = Field(default=None,
                                 description="PICK: 1-based ordinal, -1=last")
    value: Optional[str] = Field(default=None, description="PICK: value anchor")
    exclude_last: bool = Field(default=False,
                               description="PICK value: search chain[:-1]")
    date: Optional[str] = Field(default=None, description="ASOF: literal date")
    before: Optional[str] = Field(default=None, description="WINDOW: bound")
    fn: Optional[str] = Field(default=None, description="AGG: aggregate name")


class TopExpr(BaseModel):
    """深度 3:子式可为深度 2;仅 ASOF 可挂 at 子表达式(时序 join)。"""
    prim: Literal["PICK", "ASOF", "WINDOW", "AGG"]
    of: Union[MidExpr, LeafExpr]
    at: Optional[MidExpr] = Field(
        default=None, description="ASOF only: date taken from this Rec expr")
    index: Optional[int] = None
    value: Optional[str] = None
    exclude_last: bool = False
    date: Optional[str] = None
    before: Optional[str] = None
    fn: Optional[str] = None


Expr = Union[LeafExpr, MidExpr, TopExpr]


class AlgebraProgram(BaseModel):
    """编译器(旗标开)输出:一棵深度 ≤3 的原语表达式树。"""
    expr: Union[LeafExpr, MidExpr, TopExpr]


class IllFormed(ValueError):
    """类型检查拒绝的非良构树。"""


def expr_type(e) -> str:
    return {"SELECT": "Chain", "TAGSET": "Chain", "WINDOW": "Chain",
            "PICK": "Rec", "ASOF": "Loc", "AGG": "Value"}[e.prim]


def check_expr(e, depth: int = 1) -> str:
    """类型检查器:返回类型名,非良构抛 IllFormed。"""
    if depth > 3:
        raise IllFormed("depth > 3")
    p = e.prim
    if p == "TAGSET":
        if e.tag is None:
            raise IllFormed("TAGSET requires tag")
        return "Chain"
    if p == "SELECT":
        return "Chain"
    of = getattr(e, "of", None)
    if of is None:
        raise IllFormed(f"{p} requires 'of'")
    if check_expr(of, depth + 1) != "Chain":
        raise IllFormed(f"{p}.of must be Chain-typed")
    if p == "PICK":
        if (e.index is None) == (e.value is None):
            raise IllFormed("PICK: exactly one of index/value")
        return "Rec"
    if p == "WINDOW":
        if e.before is None:
            raise IllFormed("WINDOW requires before")
        return "Chain"
    if p == "AGG":
        if e.fn not in _AGG_FNS:
            raise IllFormed(f"AGG.fn must be one of {_AGG_FNS}")
        return "Value"
    # ASOF
    at = getattr(e, "at", None)
    if (e.date is None) == (at is None):
        raise IllFormed("ASOF: exactly one of date/at")
    if at is not None and check_expr(at, depth + 1) != "Rec":
        raise IllFormed("ASOF.at must be Rec-typed")
    return "Loc"


# ── 递归解释器(纯代码,零 LLM)────────────────────────────────
def eval_expr(e, recs: List[dict], mem_dates: dict, question: str = "") -> dict:
    """求值一棵已通过 check_expr 的树;返回带 trace 的节点
    {"type", 值字段..., "of": 子节点, "at": 子节点},宏渲染沿 trace 读中间
    结果(共享子树不重算)。语义逐条复用平面执行的分支代码。"""
    p = e.prim
    if p == "SELECT":
        pool = _select_pool(recs, e.slot or "", mem_dates, question)
        if e.hygiene:
            pool = _hygiene_pool(pool)
        return {"type": "Chain", "chain": _chain(pool, mem_dates)}
    if p == "TAGSET":
        hits = sorted(_tagged(recs, e.tag or ""),
                      key=lambda r: _rec_date(r, mem_dates))
        return {"type": "Chain", "chain": hits}

    ofn = eval_expr(e.of, recs, mem_dates, question)
    chain = ofn["chain"]
    if p == "WINDOW":
        qd = _pdate(e.before or "")
        sub = [r for r in chain
               if qd is not None
               and _pdate(_rec_date(r, mem_dates)) is not None
               and _pdate(_rec_date(r, mem_dates)) < qd]
        return {"type": "Chain", "chain": sub, "qd": qd, "of": ofn}
    if p == "PICK":
        if e.value is not None:
            pv = _norm(e.value)
            hay = chain[:-1] if e.exclude_last else chain
            rec = next((r for r in hay
                        if pv and (pv in _norm(r.get("value", ""))
                                   or _norm(r.get("value", "")) in pv)), None)
            return {"type": "Rec", "rec": rec, "of": ofn}
        k = e.index
        rec = None
        if isinstance(k, int) and not isinstance(k, bool):
            if k == -1 and chain:
                rec = chain[-1]
            elif 1 <= k <= len(chain):
                rec = chain[k - 1]
        return {"type": "Rec", "rec": rec, "k": k, "of": ofn}
    if p == "AGG":
        dates = [_rec_date(r, mem_dates) for r in chain]
        values = [str(r.get("value", "")) for r in chain]
        if e.fn == "count_changes":
            data = len(chain) - 1
        elif e.fn == "distinct_ordered":
            data = sorted(set(values), key=values.index)
        elif e.fn == "argmax_dur":
            per_value: dict = {}
            parsed = [_pdate(d) for d in dates]
            for i in range(len(chain) - 1):
                if parsed[i] is not None and parsed[i + 1] is not None:
                    per_value[values[i]] = (per_value.get(values[i], 0)
                                            + (parsed[i + 1] - parsed[i]).days)
            data = per_value
        else:  # by_year
            by_year: dict = {}
            for r in chain:
                y = (_rec_date(r, mem_dates) or "undated")[:4]
                by_year.setdefault(y, []).append(str(r.get("value", "")))
            data = by_year
        return {"type": "Value", "fn": e.fn, "data": data, "of": ofn}
    # ASOF
    at = getattr(e, "at", None)
    atn = None
    if at is not None:
        atn = eval_expr(at, recs, mem_dates, question)
        rec = atn["rec"]
        t_raw = _rec_date(rec, mem_dates) if rec is not None else ""
        qd = _pdate(t_raw) if rec is not None else None
    else:
        t_raw = e.date or ""
        qd = _pdate(t_raw)
    gi = None
    for i, r in enumerate(chain):
        pd = _pdate(_rec_date(r, mem_dates))
        if pd is not None and qd is not None and pd <= qd:
            gi = i
    return {"type": "Loc", "gi": gi, "qd": qd, "date_raw": t_raw,
            "of": ofn, "at": atn}


def base_chain(node: dict) -> List[dict]:
    """沿 of 链下钻到叶,取其 Chain(宏渲染的证据基链)。"""
    while node.get("of") is not None:
        node = node["of"]
    return node["chain"]


# ── 宏定义表(plan dict → 表达式树)────────────────────────────
def _sel(slot, hygiene: bool = False) -> LeafExpr:
    return LeafExpr(prim="SELECT", slot=slot or "", hygiene=hygiene)


def _join_expr(plan: dict) -> TopExpr:
    ai = plan.get("anchor_index")
    if not isinstance(ai, int) or isinstance(ai, bool):
        ai = None
    if ai is not None:
        anchor = MidExpr(prim="PICK", of=_sel(plan.get("slot")), index=ai)
    else:
        anchor = MidExpr(prim="PICK", of=_sel(plan.get("slot")),
                         value=plan.get("presupposed") or "")
    return TopExpr(prim="ASOF", of=_sel(plan.get("slot2")), at=anchor)


MACROS = {
    "current": lambda p: MidExpr(prim="PICK", of=_sel(p.get("slot")),
                                 index=-1),
    "point_in_time": lambda p: MidExpr(prim="ASOF", of=_sel(p.get("slot")),
                                       date=p.get("date") or ""),
    "trajectory": lambda p: _sel(p.get("slot")),
    "premise_check": lambda p: MidExpr(prim="PICK", of=_sel(p.get("slot")),
                                       value=p.get("presupposed") or "",
                                       exclude_last=True),
    "count_changes": lambda p: MidExpr(prim="AGG", of=_sel(p.get("slot"), True),
                                       fn="count_changes"),
    "longest": lambda p: MidExpr(prim="AGG", of=_sel(p.get("slot"), True),
                                 fn="argmax_dur"),
    "count_before": lambda p: TopExpr(
        prim="AGG", fn="distinct_ordered",
        of=MidExpr(prim="WINDOW", of=_sel(p.get("slot"), True),
                   before=p.get("date") or "")),
    "first_last": lambda p: MidExpr(prim="PICK", of=_sel(p.get("slot"), True),
                                    index=1),
    "tag_filter": lambda p: LeafExpr(prim="TAGSET", tag=p.get("tag") or ""),
    "tag_trend": lambda p: MidExpr(prim="AGG",
                                   of=LeafExpr(prim="TAGSET",
                                               tag=p.get("tag") or ""),
                                   fn="by_year"),
    "join_at_change": _join_expr,
}


# ── 宏渲染(字符串模板逐字节同平面分支)─────────────────────────
def _render_tag(op: str, plan: dict, node: dict):
    tag = plan.get("tag") or ""
    hits = base_chain(node)
    ev = [_line(r, node["_md"]) for r in hits]
    derived: List[str] = []
    if not hits:
        derived.append(f"No stored item carries the tag {tag}.")
    elif op == "tag_filter":
        derived.append(
            f"{len(hits)} stored item(s) carry the tag {tag}; every one "
            f"is listed above with its date. Mention ONLY these items, "
            f"each with its date; do not add or infer anything beyond "
            f"them.")
    else:
        by_year = node["data"]
        seq = "; ".join(f"{y}: " + ", ".join(vs)
                        for y, vs in sorted(by_year.items()))
        derived.append(
            f"Items tagged {tag} by year — {seq}. Describe what was "
            f"mentioned and how it evolved, citing ONLY these items "
            f"with their dates; state trends only when two or more "
            f"listed items directly show them, never by inference.")
    return ev[:EVIDENCE_CAP], derived


def _render_join(plan: dict, node: dict, mem_dates: dict):
    slot = plan.get("slot") or ""
    slot2 = plan.get("slot2") or ""
    atn = node["at"]
    a_chain = atn["of"]["chain"]
    ai = atn.get("k")
    anchor = atn["rec"]
    ev: List[str] = []
    derived: List[str] = []
    if ai is not None:
        if not (1 <= ai <= len(a_chain)):
            ev = [_line(r, mem_dates) for r in a_chain]
            derived.append(
                f"Ordinal anchor out of range: the question refers to the "
                f"user's {_ordinal_en(ai)} "
                f"{slot or 'anchor-attribute'} value, but only "
                f"{len(a_chain)} dated state(s) are known in memory, so the "
                f"cross-attribute lookup cannot be resolved. Say so instead "
                f"of guessing.")
            return ev[:EVIDENCE_CAP], derived
    elif anchor is None:
        ev = [_line(r, mem_dates) for r in a_chain]
        derived.append(
            f"Anchor not found: no dated {slot or 'anchor-attribute'} "
            f"record matching '{plan.get('presupposed') or ''}' exists "
            f"in memory, so the cross-attribute lookup cannot be "
            f"resolved. Say so instead of guessing.")
        return ev[:EVIDENCE_CAP], derived

    a_label = _label(anchor)
    a_value = anchor.get("value", "")
    t_raw = node["date_raw"]
    ev.append(_line(anchor, mem_dates))
    if ai is not None:
        derived.append(
            f"Ordinal anchor resolved: the user's {_ordinal_en(ai)} "
            f"{a_label} (1-based over the dated history) is {a_value}.")
    if node["qd"] is None:
        derived.append(
            f"Anchor found (the user's {a_label} changed to {a_value}) but "
            f"its date '{t_raw}' is unparseable, so the cross-attribute "
            f"lookup cannot be resolved.")
        return ev[:EVIDENCE_CAP], derived

    b_chain = node["of"]["chain"]
    if not b_chain:
        derived.append(
            f"The user's {a_label} changed to {a_value} on {t_raw}, but no "
            f"dated record of {slot2 or 'the other asked attribute'} exists "
            f"in memory to look up at that date.")
        return ev[:EVIDENCE_CAP], derived
    b_dates = [_rec_date(r, mem_dates) for r in b_chain]
    b_values = [str(r.get("value", "")) for r in b_chain]
    b_label = _label(b_chain[-1])
    gi = node["gi"]
    if gi is None:
        ev.append(_line(b_chain[0], mem_dates))
        derived.append(
            f"The user's {a_label} changed to {a_value} on {t_raw}, which "
            f"predates every known state of {b_label}; the earliest known "
            f"{b_label} is {b_values[0]} from {b_dates[0]}.")
        return ev[:EVIDENCE_CAP], derived
    ev += [_line(r, mem_dates) for r in b_chain[max(0, gi - 1):gi + 2]]
    until = (f", unchanged until {b_dates[gi + 1]}"
             if gi + 1 < len(b_chain) else "")
    derived.append(
        f"The user's {a_label} changed to {a_value} on {t_raw}; on that "
        f"date the user's {b_label} was {b_values[gi]} (recorded "
        f"{b_dates[gi]}{until}). This IS the answer.")
    return ev[:EVIDENCE_CAP], derived


def _render_chain_op(op: str, plan: dict, node: dict, mem_dates: dict):
    slot = plan.get("slot") or ""
    chain = base_chain(node)
    ev = [_line(r, mem_dates) for r in chain]
    derived: List[str] = []
    if not chain:
        derived.append("No dated record found for "
                       f"{slot or 'the asked attribute'} in memory.")
        return ev[:EVIDENCE_CAP], derived
    label = _label(chain[-1])
    dates = [_rec_date(r, mem_dates) for r in chain]
    values = [str(r.get("value", "")) for r in chain]

    if op in ("current", "premise_check"):
        derived.append(f"The user's current {label} is {values[-1]} "
                       f"(since {dates[-1]}).")
        pv = _norm(plan.get("presupposed") or "")
        if op == "premise_check" and pv:
            stale = node["rec"]
            if stale is not None:
                derived.append(
                    f"IMPORTANT: the message presupposes "
                    f"{stale.get('value', '')}, which is OUTDATED — the "
                    f"user's current {label} is {values[-1]}. Correct this "
                    f"premise before helping.")
    elif op == "point_in_time":
        gi = node["gi"]
        if node["qd"] is None or gi is None:
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
        n = node["data"]
        derived.append(
            f"The user's {label} changed {n} time(s) — {len(chain)} "
            f"successive states: " + " -> ".join(values) + ".")
    elif op == "longest":
        per_value = node["data"]
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
        distinct = node["data"]
        derived.append(
            f"Before {plan.get('date')}, the user had {len(distinct)} "
            f"different {label} value(s): " + (", ".join(distinct) or "none")
            + ".")
    elif op == "first_last":
        derived.append(
            f"First {label}: {values[0]} (from {dates[0]}); most recent: "
            f"{values[-1]} (since {dates[-1]}).")
    return ev[:EVIDENCE_CAP], derived


# ── 直接表达式路径(旗标开、编译产出 AST 时;未见组合用)────────
def _render_direct(node: dict, mem_dates: dict):
    """通用渲染:证据 = 基链行(ASOF 时序 join 另加锚行与命中窗),结论 =
    对求值结果的中性陈述。仅新组合走此路;11 算子宏不经过这里。"""
    ev: List[str] = []
    derived: List[str] = []
    t = node["type"]
    if t == "Chain":
        ev = [_line(r, mem_dates) for r in node["chain"]]
        seq = " -> ".join(
            f"{str(r.get('value', ''))} (from {_rec_date(r, mem_dates)})"
            for r in node["chain"])
        derived.append(f"Matching dated records, in order: {seq or 'none'}.")
    elif t == "Rec":
        ev = [_line(r, mem_dates) for r in base_chain(node)]
        rec = node["rec"]
        if rec is None:
            derived.append("The requested element does not exist in the "
                           "dated history above; say so instead of guessing.")
        else:
            derived.append(
                f"The selected record: the user's {_label(rec)} was "
                f"{rec.get('value', '')} (recorded "
                f"{_rec_date(rec, mem_dates)}). This IS the answer.")
    elif t == "Loc":
        if node.get("at") is not None:
            arec = node["at"]["rec"]
            if arec is not None:
                ev.append(_line(arec, mem_dates))
        chain = node["of"]["chain"]
        gi = node["gi"]
        if node["qd"] is None:
            derived.append("The reference date could not be resolved from "
                           "memory, so the lookup cannot be answered.")
            return ev[:EVIDENCE_CAP], derived
        if not chain or gi is None:
            ev += [_line(r, mem_dates) for r in chain[:1]]
            derived.append(
                f"The date {node['date_raw']} predates every known state of "
                f"the asked attribute; no value can be resolved at it.")
            return ev[:EVIDENCE_CAP], derived
        ev += [_line(r, mem_dates) for r in chain[max(0, gi - 1):gi + 2]]
        rec = chain[gi]
        derived.append(
            f"As of {node['date_raw']}, the user's {_label(rec)} was "
            f"{rec.get('value', '')} (recorded "
            f"{_rec_date(rec, mem_dates)}). This IS the answer.")
    else:  # Value
        ev = [_line(r, mem_dates) for r in base_chain(node)]
        derived.append(
            f"Computed {node['fn']} over the dated records above: "
            + json.dumps(node["data"], ensure_ascii=False)
            + ". This computed result IS the answer; do not recount.")
    return ev[:EVIDENCE_CAP], derived


def execute_plan_algebra(plan: dict, recs: List[dict], mem_dates: dict,
                         question: str = ""):
    """代数执行入口,签名同 execute_plan。plan 带 "op" → 宏路径(11 算子,
    渲染逐字节同平面);plan 带 "expr"(AlgebraProgram.model_dump)→ 直接
    表达式路径。非良构树 → IllFormed 上抛(调用方按编译失败处理)。"""
    if isinstance(plan, dict) and "expr" in plan and not plan.get("op"):
        e = AlgebraProgram.model_validate(plan).expr
        check_expr(e)
        node = eval_expr(e, recs, mem_dates, question)
        return _render_direct(node, mem_dates)

    op = plan.get("op") or "current"
    make = MACROS.get(op)
    expr = make(plan) if make else _sel(plan.get("slot"))
    check_expr(expr)
    node = eval_expr(expr, recs, mem_dates, question)
    if op == "join_at_change":
        return _render_join(plan, node, mem_dates)
    if op in ("tag_filter", "tag_trend"):
        node["_md"] = mem_dates
        return _render_tag(op, plan, node)
    return _render_chain_op(op, plan, node, mem_dates)


# ── 旗标开时的编译提示词(原语形式语义文档 + 2 个组合示例)───────
# 示例句式为新造,不取自 gen_wikistate_complex 出题模板(去耦合原则 3)。
ALGEBRA_COMPILE_PROMPT = """\
You compile a user's question about their own personal history into ONE
expression over a small temporal algebra, evaluated on a store of dated
personal-state records. Output STRICT JSON only:
{"expr": <expression>}

An expression is a tree of at most depth 3 built from six primitives.
Types: Chain = the dated, deduplicated history of one attribute (or one
tag), oldest first; Rec = one record; Loc = a position in a chain;
Value = an aggregate.

Primitives (formal semantics; chain(k) = <(v_1,t_1),...,(v_m,t_m)>):
- {"prim":"SELECT","slot":<str>,"hygiene":<bool>} : () -> Chain
  The dated history of one concrete attribute (slot is a short noun
  phrase like 'employer', 'residence city' — never an abstraction like
  'history'). Set "hygiene": true when the result feeds counting or
  duration aggregation (it drops fragment records so counts are exact).
- {"prim":"TAGSET","tag":<str>} : () -> Chain
  All records carrying a semantic tag, dated, oldest first; tag is
  copied verbatim from the question.
- {"prim":"WINDOW","of":<Chain expr>,"before":<YYYY-MM-DD>} : Chain -> Chain
  The sub-chain strictly earlier than the bound.
- {"prim":"PICK","of":<Chain expr>,"index":<int>} or
  {"prim":"PICK","of":<Chain expr>,"value":<str>} : Chain -> Rec
  One element: index is 1-based (-1 = latest); value matches the record
  whose value the question names.
- {"prim":"ASOF","of":<Chain expr>,"date":<YYYY-MM-DD>} or
  {"prim":"ASOF","of":<Chain expr>,"at":<Rec expr>} : Chain -> Loc
  The state in force at a date: the last (v_i,t_i) with t_i <= d. With
  "at", the date is taken from another expression's record — this is the
  temporal join: resolve WHEN something happened, then read a different
  attribute as of that moment.
- {"prim":"AGG","of":<Chain expr>,"fn":<name>} : Chain -> Value
  fn = "count_changes" (number of state transitions), "distinct_ordered"
  (distinct values in first-seen order), "argmax_dur" (days each value
  was held, closed intervals), "by_year" (values grouped by year).

Composition examples:
Q: Out of all the gadgets I told you about before 2019-06-01, how many
   distinct ones were there?
A: {"expr": {"prim": "AGG", "fn": "distinct_ordered", "of": {"prim": "WINDOW", "before": "2019-06-01", "of": {"prim": "SELECT", "slot": "device", "hygiene": true}}}}
Q: What was my job title back when I owned my second phone?
A: {"expr": {"prim": "ASOF", "of": {"prim": "SELECT", "slot": "position", "hygiene": false}, "at": {"prim": "PICK", "index": 2, "of": {"prim": "SELECT", "slot": "device", "hygiene": false}}}}
"""
