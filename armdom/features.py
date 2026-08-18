# -*- coding: utf-8 -*-
"""armdom.features — 分桶特征。全部只读日志里已有的字段，可在部署时求值。

不得加入语料/基准身份类特征。参考反例：本工具的宿主系统曾把 ``bench`` 做成 one-hot
特征训练路由器，离线分数很好但单一混合流部署时不可知——那类特征在这里一律不收。
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List

_WORD = re.compile(r"[a-z0-9']+")
_ENT = re.compile(r"\b(?:[0-9]+|[A-Z][a-z]+)\b")

_WH = ("what", "when", "where", "who", "whom", "whose", "which", "how", "why")

#: 聚合/时序意图词：标记"要对状态做什么计算"，比表层首词更接近路由需要的信号。
_AGG = {
    "count": ("how many", "how many times", "number of", "count"),
    "dur": ("how long", "duration", "longest", "shortest"),
    "order": ("first", "last", "before", "after", "then", "previously", "originally"),
    "current": ("currently", "current", "now", "these days", "still", "at the moment"),
    "change": ("change", "changed", "switch", "switched", "move", "moved", "used to"),
}


def question_of(row: dict) -> str:
    """题面字段。内部行结构用 ``q``（core 的约定），原始日志用 ``question``——两者都收。"""
    return row.get("q") or row.get("question") or ""


def words(row: dict) -> List[str]:
    return _WORD.findall(question_of(row).lower())


def agg_key(row: dict) -> str:
    q = question_of(row).lower()
    hit = [k for k, ws in _AGG.items() if any(w in q for w in ws)]
    return "+".join(hit) if hit else "none"


def wh_key(row: dict) -> str:
    for w in words(row)[:4]:
        if w in _WH:
            return w
    return "other"


def skeleton(row: dict) -> str:
    """掩掉数字与专名，只留模板形状——同模板不同实体应共享路由决策。"""
    q = question_of(row)
    return " ".join(_ENT.sub("<e>", q).lower().split()[:6]) or "<empty>"


def build(extra: Dict[str, Callable[[dict], str]] = None
          ) -> Dict[str, Callable[[dict], str]]:
    f: Dict[str, Callable[[dict], str]] = {
        "const": lambda r: "<all>",
        "wh": wh_key,
        "agg": agg_key,
        "skel": skeleton,
        "len": lambda r: f"len{min(len(words(r)) // 4, 6)}",
        "w2agg": lambda r: " ".join(words(r)[:2]) + "|" + agg_key(r),
    }
    for n in (1, 2, 3, 4):
        f[f"word{n}"] = (lambda n_: lambda r: " ".join(words(r)[:n_]) or "<empty>")(n)
    if extra:
        f.update(extra)
    return f


#: 缺省回落链。细桶优先，支持不足时退到粗桶（实测优于任一单层：见 README）。
DEFAULT_CHAIN = "word3>word2>wh"
