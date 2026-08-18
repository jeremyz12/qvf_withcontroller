# -*- coding: utf-8 -*-
"""armdom.audit — 一次跑完三件产物（支配矩阵 / 策略表 / 天花板）。"""
from __future__ import annotations

from typing import List, Optional, Sequence

from . import core
from . import features as F
from .ingest import arms_by_cost, load


def audit(path: str, seeds: int = 20, folds: int = 2, token_weight: float = 0.5,
          drop_arms: Sequence[str] = (), chain: Optional[str] = None) -> dict:
    """读日志 → 支配矩阵 + 同分母策略表 + 逐题 oracle 天花板。

    `drop_arms` 让你直接问"删掉这条臂会怎样"——这是本工具最常用的一个动作，
    因为被支配或严重低效的臂应当删除，而不是绕着它路由。
    """
    rows, stats = load(path)
    core.TOKEN_WEIGHT = token_weight
    order = arms_by_cost(rows)
    core.set_fallback_order(order)
    arms = tuple(a for a in order if a not in drop_arms)
    if not arms:
        raise ValueError("drop_arms 把所有臂都删光了")
    feats = F.build()
    has_text = stats["with_text"] == stats["rows"] and stats["rows"] > 0
    has_store = stats["stores"] > 1

    dom = core.dominance(rows, order)

    strategies: List[dict] = []
    for a in order:
        r = core.constant_strategy(rows, a)
        r["strategy"] = f"const:{a}"
        strategies.append(r)
    if has_text:
        ch = chain or F.DEFAULT_CHAIN
        r = core.lexical_router(rows, arms, ch, feats,
                                seeds=tuple(range(seeds)), folds=folds)
        r["strategy"] = f"lexical[{ch}]"
        strategies.append(r)
        if has_store:
            r = core.combined_router(rows, arms, feats, chain=ch,
                                     seeds=tuple(range(seeds)), folds=folds)
            r["strategy"] = f"combined[{ch}+store]"
            strategies.append(r)

    ceil = core.oracle(rows, arms)
    ceil["strategy"] = f"oracle[{'+'.join(arms)}]"

    baseline = None
    if stats["with_baseline"] == stats["rows"] and stats["rows"] > 0:
        n = len(rows)
        acc = sum(r["v42_correct"] for r in rows) / n
        tk = sum(r["v42_tok"] for r in rows) / n
        baseline = {"strategy": "your current system", "acc": acc, "tok": tk,
                    "score": core.score_of(acc, tk), "n": n, "fallback_rate": 0.0,
                    "acc_spread": 0.0, "score_spread": 0.0}

    allc = strategies + [ceil] + ([baseline] if baseline else [])
    best = max(strategies, key=lambda s: s["score"])
    return {"stats": stats, "arms_by_cost": order, "dominance": dom,
            "strategies": strategies, "ceiling": ceil, "baseline": baseline,
            "best": best, "frontier": core.mark_frontier(allc),
            "token_weight": token_weight}
