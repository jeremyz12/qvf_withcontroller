# -*- coding: utf-8 -*-
"""armdom.fit — 把路由拟合成一份**可部署的表**,并在运行时按库在线自适应。

与 `armdom.audit` 的区别:audit 做的是留出评估(回答"这个策略值多少分"),
fit 做的是产出线上要用的东西(回答"线上每道题该走哪条臂")。故 fit **在全量数据
上拟合**——留出只是为了诚实估分,部署时没有理由丢掉一半数据。

产出的表是纯 JSON,不含任何模型权重,线上查表零 LLM 调用:

    {"chain": ["word3", "word2", "wh"],
     "arms": ["prompt", "direct", "wt"],
     "fallback_order": [...],          # 选中的臂不可用时按此顺序回落
     "global": "wt",                   # 全链未命中时的兜底
     "k_store": 10.0,                  # 按库在线自适应的收缩常数
     "levels": [{"feature": "word3", "table": {"<bucket>": {"arm": "wt",
                                                            "acc": .., "tok": ..}}}, ...],
     "prior": {"wt": {"acc": .., "tok": ..}, ...}}

`StoreRouter` 是配套的运行时:每个库一个实例,`pick(question)` 给臂,
`observe(arm, correct, tokens)` 回填结果。两条部署约束由结构强制而非文档约定:
`pick` 只读该库此前 `observe` 过的东西(前瞻性),而 `observe` 只接受**实际跑过的
那条臂**的结果(bandit)——没跑的臂在线上本就观测不到。
"""
from __future__ import annotations

import collections
import json
from typing import Dict, List, Optional, Sequence

from . import core
from . import features as F
from .ingest import arms_by_cost, load


def fit(rows: List[dict], arms: Sequence[str], features: Dict, chain: str,
        min_sup: int = 10, slack: float = 0.02, k_store: float = 10.0) -> dict:
    """在**全量** rows 上拟合分层查表。桶内选臂规则与评估时一致。"""
    fns = [(c, features[c]) for c in chain.split(">")]
    levels = []
    for name, fn in fns:
        st: Dict[str, Dict[str, List]] = collections.defaultdict(
            lambda: {a: [0, 0, 0.0] for a in arms})
        for t in rows:
            bk = fn(t)
            for a in arms:
                if core.has(t, a):
                    st[bk][a][0] += core.ok(t, a)
                    st[bk][a][1] += 1
                    st[bk][a][2] += core.tok(t, a)
        table = {}
        for bk, d in st.items():
            pick = core._pick(d, arms, min_sup, slack)
            if pick is None:
                continue
            table[bk] = {"arm": pick,
                         "acc": round(d[pick][0] / d[pick][1], 4),
                         "tok": round(d[pick][2] / d[pick][1], 1),
                         "n": d[pick][1]}
        levels.append({"feature": name, "table": table})

    g = {a: [0, 0, 0.0] for a in arms}
    for t in rows:
        for a in arms:
            if core.has(t, a):
                g[a][0] += core.ok(t, a)
                g[a][1] += 1
                g[a][2] += core.tok(t, a)
    prior = {a: {"acc": round(g[a][0] / g[a][1], 4) if g[a][1] else 0.0,
                 "tok": round(g[a][2] / g[a][1], 1) if g[a][1] else 0.0}
             for a in arms}
    return {"chain": [n for n, _ in fns], "arms": list(arms),
            "fallback_order": list(arms_by_cost(rows)),
            "global": core._pick(g, arms, 1, slack), "k_store": k_store,
            "slack": slack, "min_sup": min_sup, "levels": levels,
            "prior": prior, "n_fit": len(rows)}


class StoreRouter:
    """一个库一个实例的运行时路由器。零 LLM、零依赖。

    典型用法::

        table = json.load(open("armdom_table.json"))
        r = StoreRouter(table)                 # 每个 uid/库一个
        arm = r.pick("What phone am I using?")
        ...                                    # 跑这条臂
        r.observe(arm, correct=True, tokens=1830)

    `available` 传入本题**实际可跑**的臂;线上通常是全部臂,离线重放时用它
    表达"这条臂在这题上没有归档结果"。
    """

    __slots__ = ("t", "_fns", "_run")

    def __init__(self, table: dict, features: Optional[Dict] = None):
        self.t = table
        feats = features or F.build()
        self._fns = [feats[n] for n in table["chain"]]
        self._run = {a: [0, 0, 0.0] for a in table["arms"]}

    def _base(self, row: dict) -> Dict[str, Dict[str, float]]:
        base = dict(self.t["prior"])
        for lv, fn in zip(self.t["levels"], self._fns):
            e = lv["table"].get(fn(row))
            if e:
                base = {**base, e["arm"]: {"acc": e["acc"], "tok": e["tok"]}}
                break
        return base

    def pick(self, question: str, available: Optional[Sequence[str]] = None) -> str:
        arms = [a for a in self.t["arms"]
                if available is None or a in available]
        if not arms:
            raise ValueError("没有可用的臂")
        base = self._base({"q": question})
        slack = self.t.get("slack", 0.02)
        est = {}
        for a in arms:
            hit, cnt, tks = self._run[a]
            b = base.get(a) or self.t["prior"][a]
            w = cnt / (cnt + self.t["k_store"]) if cnt else 0.0
            est[a] = (w * (hit / cnt) + (1 - w) * b["acc"] if cnt else b["acc"],
                      w * (tks / cnt) + (1 - w) * b["tok"] if cnt else b["tok"])
        best = max(v[0] for v in est.values())
        want = min([a for a in arms if est[a][0] >= best - slack],
                   key=lambda a: est[a][1])
        if available is not None and want not in available:
            for f in self.t["fallback_order"]:
                if f in available:
                    return f
        return want

    def observe(self, arm: str, correct: bool,
                tokens: Optional[float] = None) -> None:
        """只回填**实际跑过的那条臂**——线上看不到没跑的臂,这里也不许看。

        `tokens=None` 表示调用方拿不到本次的实际 token(例如只记准确率的重放
        harness)。此时用表里的先验 tok 代替,使成本项退化为"不更新"而非崩溃或
        当成 0——当成 0 会让被选中的臂看起来越用越便宜,是个会自我强化的错误。
        """
        if arm not in self._run:
            return
        if tokens is None:
            tokens = self.t["prior"][arm]["tok"]
        self._run[arm][0] += bool(correct)
        self._run[arm][1] += 1
        self._run[arm][2] += float(tokens)


def fit_from_logs(path: str, drop_arms: Sequence[str] = (),
                  chain: Optional[str] = None, k_store: float = 10.0,
                  slack: float = 0.02, min_sup: int = 10) -> dict:
    rows, _ = load(path)
    order = arms_by_cost(rows)
    core.set_fallback_order(order)
    arms = tuple(a for a in order if a not in drop_arms)
    return fit(rows, arms, F.build(), chain or F.DEFAULT_CHAIN,
               min_sup=min_sup, slack=slack, k_store=k_store)
