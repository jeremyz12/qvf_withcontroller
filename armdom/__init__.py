# -*- coding: utf-8 -*-
"""armdom — 多臂记忆 / RAG 系统的臂支配性审计与零 LLM 路由。

    import armdom
    report = armdom.audit("logs.jsonl", drop_arms=["expensive_arm"])

命令行：``armdom audit logs.jsonl``。输入格式与口径约定见 README.md。
"""
from .audit import audit
from .core import (combined_router, constant_strategy, dominance, lexical_router,
                   mark_frontier, oracle, score_of, set_fallback_order,
                   shrinkage_router)
from .features import DEFAULT_CHAIN
from .features import build as build_features
from .ingest import arms_by_cost, load

__version__ = "0.1.0"
__all__ = ["audit", "load", "arms_by_cost", "build_features", "DEFAULT_CHAIN",
           "dominance", "lexical_router", "shrinkage_router", "combined_router",
           "constant_strategy", "oracle", "mark_frontier", "score_of",
           "set_fallback_order"]
