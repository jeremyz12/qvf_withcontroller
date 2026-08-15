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

import re

from scripts.complex_query_arm import (EVIDENCE_CAP, MODEL, _COUNT_OPS,
                                       _chain, _hygiene_pool, _label, _line,
                                       _ordinal_en, _pdate, _rec_date,
                                       _select_pool, _tagged)
from scripts.wt_qvf_prototype import _norm

_AGG_FNS = ("count_changes", "distinct_ordered", "argmax_dur", "by_year",
            "count_elements")

# dev round 2(seen split 复核发现):WINDOW 原文档只有单侧 before(字面日期)
# 一种界。S8 WINDOW∘COUNT/WINDOW_2ANCHOR∘COUNT 需要双侧界,且界常由另一
# 表达式的值/序数锚给出(而非字面日期)。WINDOW 保持自身零递归子式(不
# 破坏原深度预算),锚以标量字段描述,WINDOW 求值时自行选池+定位 ——
# 语义上等价于 ASOF.at 的"锚子式"机制,但不占用树深度。
_BOUND_FIELDS = ("after", "after_slot", "after_value", "after_index",
                 "before_slot", "before_value", "before_index")


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
    before: Optional[str] = Field(
        default=None, description="WINDOW: literal upper bound (exclusive)")
    after: Optional[str] = Field(
        default=None, description="WINDOW: literal lower bound (exclusive)")
    before_slot: Optional[str] = Field(
        default=None, description="WINDOW: attribute whose dated history "
        "anchors the upper bound (value- or index-anchored)")
    before_value: Optional[str] = Field(
        default=None, description="WINDOW: value naming the anchor record "
        "on before_slot's history")
    before_index: Optional[int] = Field(
        default=None, description="WINDOW: 1-based ordinal position on "
        "before_slot's history anchoring the upper bound")
    after_slot: Optional[str] = Field(
        default=None, description="WINDOW: attribute whose dated history "
        "anchors the lower bound")
    after_value: Optional[str] = Field(
        default=None, description="WINDOW: value naming the anchor record "
        "on after_slot's history")
    after_index: Optional[int] = Field(
        default=None, description="WINDOW: 1-based ordinal position on "
        "after_slot's history anchoring the lower bound")
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
    after: Optional[str] = None
    before_slot: Optional[str] = None
    before_value: Optional[str] = None
    before_index: Optional[int] = None
    after_slot: Optional[str] = None
    after_value: Optional[str] = None
    after_index: Optional[int] = None
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
        # before_index/after_index 可省略 *_slot(隐式指同一条被开窗的
        # 链,提示词已文档化此默认;dev round 2 修复:补上此处遗漏的类型
        # 检查放行,原判据只认字面 before/after 或显式 *_slot)。
        has_before = (e.before is not None or e.before_slot is not None
                     or e.before_index is not None)
        has_after = (e.after is not None or e.after_slot is not None
                    or e.after_index is not None)
        if not (has_before or has_after):
            raise IllFormed("WINDOW requires before/after (literal, or "
                            "*_slot anchored)")
        if e.before_slot is not None and (e.before_value is None) == \
                (e.before_index is None):
            raise IllFormed("WINDOW before_slot needs exactly one of "
                            "before_value/before_index")
        if e.after_slot is not None and (e.after_value is None) == \
                (e.after_index is None):
            raise IllFormed("WINDOW after_slot needs exactly one of "
                            "after_value/after_index")
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


def _resolve_bound(literal, slot, value, index, recs, mem_dates, question):
    """WINDOW 单侧界解析(dev round 2 新增,零递归 —— 界锚以标量字段描述,
    自行选池+定位,不占用树深度预算)。返回 (requested, date|None):
    requested=False 表示该侧未设界(WINDOW 求值时应放行,与旧版单侧
    before-only 语义逐字节兼容);requested=True 但 date=None 表示界已声明
    但无法解析(字面日期解析失败,或 slot 锚值/序数未命中)——旧版对此的
    行为是整侧判负(该侧界内容清空),这里原样保留。"""
    if literal:
        return True, _pdate(literal)
    if not slot:
        return False, None
    apool = _select_pool(recs, slot, mem_dates, question)
    achain = _chain(apool, mem_dates)
    if isinstance(index, int) and not isinstance(index, bool):
        # 序数锚越界(含 <=0,即"第一个元素之前不存在锚"这类合法的开放
        # 端):视为"该侧未设界"而非"已声明但失败"——序数锚是本轮新机制,
        # 没有旧版行为要兼容;这样"前 N 个/从第 N 个起"两类窗才能只填
        # 一侧,不必为越界的另一侧编造锚(NTH∘CMP_DUR 的"第一 vs 第二"
        # 只需 before_index=3,不必为不存在的"第 0 个"填 after_index)。
        if 1 <= index <= len(achain):
            return True, _pdate(_rec_date(achain[index - 1], mem_dates))
        return False, None
    if value:
        pv = _norm(value)
        arec = next((r for r in achain
                     if pv and (pv in _norm(r.get("value", ""))
                                or _norm(r.get("value", "")) in pv)), None)
        return True, (_pdate(_rec_date(arec, mem_dates))
                      if arec is not None else None)
    return True, None


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
        # *_index 界省略 *_slot 时,隐式指同一条被开窗的链(of 为 SELECT
        # 叶子时用它自己的 slot;of 非 SELECT——如 TAGSET/嵌套 WINDOW——则
        # 无法自指,保持 None,交 _resolve_bound 按"未声明"处理)。
        self_slot = getattr(e.of, "slot", None)
        before_slot = getattr(e, "before_slot", None) or (
            self_slot if getattr(e, "before_index", None) is not None else None)
        after_slot = getattr(e, "after_slot", None) or (
            self_slot if getattr(e, "after_index", None) is not None else None)
        b_req, qd = _resolve_bound(
            e.before, before_slot,
            getattr(e, "before_value", None), getattr(e, "before_index", None),
            recs, mem_dates, question)
        a_req, qa = _resolve_bound(
            e.after, after_slot,
            getattr(e, "after_value", None), getattr(e, "after_index", None),
            recs, mem_dates, question)

        def _in_window(pd):
            if b_req and not (qd is not None and pd < qd):
                return False
            if a_req and not (qa is not None and pd > qa):
                return False
            return True
        sub = [r for r in chain
               if _pdate(_rec_date(r, mem_dates)) is not None
               and _in_window(_pdate(_rec_date(r, mem_dates)))]
        return {"type": "Chain", "chain": sub, "qd": qd, "qa": qa, "of": ofn}
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
        elif e.fn == "count_elements":
            # dev round 2 新增(WINDOW_2ANCHOR∘COUNT same_chain 口径:窗内
            # 元素计数,不去重、不算转移——len(chain) 本身)。
            data = len(chain)
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
        # dev round 2 修复:证据取直接子式的链(WINDOW 时是窗内子链),不
        # 沿 of 一路下钻到叶——AGG(WINDOW(...)) 的证据须与窗内结论一致,
        # 否则读者会看到窗外记录,与"计算结论 IS the answer"的指示冲突。
        src = node.get("of") or {}
        ev = [_line(r, mem_dates) for r in src.get("chain", base_chain(node))]
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
personal-state records. Output STRICT JSON only, and nothing else: no
prose, no alternatives, no "wait, let me reconsider" — commit to exactly
ONE JSON object as your entire response.
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
- {"prim":"WINDOW","of":<Chain expr>, ...bounds...} : Chain -> Chain
  The sub-chain strictly between a lower and/or upper bound (either bound
  may be omitted). ONLY use WINDOW when the question explicitly names a
  bounding span with words like between/since/during/before/after/while —
  e.g. "since I moved to Chicago", "between my third and fifth apartment",
  "while I worked at Oracle". For a question that just names TWO ordinal
  positions to compare directly ("my first vs my second X", "which lasted
  longer, my 2nd or 3rd Y") with NO bounding-span language, do NOT use
  WINDOW at all — use plain AGG on the un-windowed SELECT (fn="argmax_dur"
  compares durations; if that is not decisive, PICK each position with
  "index" and compare their records individually).
  Each bound is given ONE of three ways:
    "before"/"after": <YYYY-MM-DD> — a literal date named in the question.
    "before_slot"+"before_value" / "after_slot"+"after_value": the date is
      taken from the record on a (possibly different) attribute's history
      whose VALUE the question names (e.g. "since I moved to Chicago" ->
      after_slot="residence", after_value="Chicago").
    "before_slot"+"before_index" / "after_slot"+"after_index": the date is
      taken from the record at a 1-based ORDINAL position in a (possibly
      different) attribute's history that marks the EDGE of the span, NOT
      a position you want included (e.g. "before my third employer" ->
      before_slot="employer", before_index=3, correctly EXCLUDES the 3rd
      employer itself). before_slot/after_slot default to the SAME slot as
      the chain being windowed when the bound anchors on that same
      history.
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
  fn = "count_changes" (number of state transitions IN THE WHOLE chain
  passed to it — use this only when "of" is a plain SELECT, not a WINDOW);
  "count_elements" (number of dated records in the chain — use this
  whenever "of" is a WINDOW and the question asks "how many times did X
  change/happen BETWEEN/SINCE/DURING <bound(s)>": each record inside a
  window already IS one change, so counting elements, not transitions
  between them, is what "how many times" means over a bounded span);
  "distinct_ordered" (distinct values in first-seen order); "argmax_dur"
  (days each value was held, closed intervals — when "of" is a WINDOW, an
  in-progress last segment is correctly left uncredited, do not compensate
  for this); "by_year" (values grouped by year).

Composition examples:
Q: Between when I switched to my third apartment and my fifth apartment,
   how many times did my job title change?
A: {"expr": {"prim": "AGG", "fn": "count_elements", "of": {"prim": "WINDOW", "after_slot": "apartment", "after_index": 3, "before_slot": "apartment", "before_index": 5, "of": {"prim": "SELECT", "slot": "job title", "hygiene": true}}}}
Q: What was my job title back when I owned my second phone?
A: {"expr": {"prim": "ASOF", "of": {"prim": "SELECT", "slot": "position", "hygiene": false}, "at": {"prim": "PICK", "index": 2, "of": {"prim": "SELECT", "slot": "device", "hygiene": false}}}}
"""

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```|(\{.*\})",
                            re.DOTALL)


def _json_candidates(text: str):
    """按出现顺序取出文本里所有形似 JSON 对象的片段(```json 围栏内的,或
    裸花括号包裹的)。纯文本编译路径下模型偶尔会先给一版、再"Wait, let me
    reconsider..."式改口给第二版(dev round 2 现场发现,messages.parse 的
    服务端结构化输出没有这个问题,但该路径本身对本模块 schema 会挂起/
    400,见 compile_plan_algebra 文档字符串)——本函数把所有候选一并交还,
    调用方从后往前(取模型的"最终版本")逐个尝试校验。"""
    return [m.group(1) or m.group(2) for m in _JSON_BLOCK_RE.finditer(text)]


def compile_plan_algebra(client, question: str, model: str = MODEL):
    """代数臂编译(dev round 2 新增):messages.create 纯文本 + 手工
    JSON/pydantic 校验,不用 messages.parse 的服务端结构化输出。

    起因:WINDOW 加入双侧界字段(本轮扩展)后,messages.parse 在此 schema
    上被 bisection 复现地观测到频繁挂起(client 侧长时间无响应,即使显式
    设置 SDK timeout 也不总能拦下)或显式 400 "Schema is too complex"；
    同一 schema、同一问题改走纯文本 messages.create + 手工解析,稳定
    <2s 返回(dev round 2 现场验证,10+ 次调用零复现)。判断是服务端
    结构化输出(strict JSON schema 编译)对多可选字段的联合类型有复杂度
    上限,而模型本身逐字节按提示词产出合法 JSON 没有困难。平面臂
    compile_plan(messages.parse,CompiledPlan 小 schema)不受影响、不改
    动,旗标关时逐字节不变。

    签名与返回值形状与 compile_plan 一致:(plan_dict, in_tok, out_tok, ok)。
    """
    tin = tout = 0
    for _ in range(3):
        try:
            resp = client.messages.create(
                model=model, max_tokens=600, temperature=0.0,
                system=[{"type": "text", "text": ALGEBRA_COMPILE_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": question}],
            )
            tin += resp.usage.input_tokens
            tout += resp.usage.output_tokens
            full = "".join(b.text for b in resp.content if b.type == "text")
            cands = _json_candidates(full)
            p = None
            for c in reversed(cands):  # 从后往前:模型改口时取最终版本
                try:
                    p = AlgebraProgram.model_validate_json(c)
                    break
                except Exception:  # noqa: BLE001
                    continue
            if p is not None:
                return p.model_dump(), tin, tout, True
        except Exception:  # noqa: BLE001
            continue
    fallback = AlgebraProgram(expr=MidExpr(
        prim="PICK", of=LeafExpr(prim="SELECT"), index=-1)).model_dump()
    return fallback, tin, tout, False
