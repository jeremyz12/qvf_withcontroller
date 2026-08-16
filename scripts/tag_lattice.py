# -*- coding: utf-8 -*-
"""标签格(tag lattice)加载 + 闭包匹配(QVF_TAG_LATTICE 的共享工具)。

动机(导师原话场景):"很多年之前的一个三杯鸡,怎么发散到糖分高的饮食" ——
complex_query_arm._tagged() 冻结实现是精确字符串相等,"三杯鸡"只有恰好被
打过字面"高糖"标签才可能被查到。本模块把闭集字符串相等换成格上闭包:

  ① is-a 边(概念层级,可传递):三杯鸡 --is_a--> 台式炖菜 --is_a--> 肉类主菜。
     查询标签命中任一祖先节点即算命中(概念泛化)。
  ② has-property 边(限一跳,不传递):三杯鸡 --has_property--> 高糖。
     防止"跳两跳"把无关属性级联到无关概念上(如 A has_property 高糖,
     高糖 happens to is_a 某节点,不应把该节点的其他 has_property 都
     级联给 A)。
  ③ 格未命中(卡片标签或查询标签压根不在格里):回退嵌入余弦软匹配,
     阈值 QVF_TAG_LATTICE_TAU 在 dev 上校准(build_tag_lattice.py 的
     calibrate 子命令报 P-R 曲线,选精确率 >=95% 的最大召回工作点)。

lattice JSON 格式(results/tag_lattice.json,由 scripts/build_tag_lattice.py
产出):
{
  "nodes": {"<node_id>": {"label": str, "type": "concept"|"property",
                           "aliases": [str, ...]}},
  "is_a": [[child_id, parent_id], ...],
  "has_property": [[concept_id, property_id], ...]
}

本模块只被旗标分支延迟 import(complex_query_arm.py 的 QVF_TAG_LATTICE=1
分支);旗标关时冻结路径不加载、不产生任何副作用、不读文件。
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

_LATTICE_F = Path(os.environ.get("QVF_TAG_LATTICE_FILE", "") or
                  "results/tag_lattice.json")
_TAU = float(os.environ.get("QVF_TAG_LATTICE_TAU", "0.60"))
_EMBED_MODEL = os.environ.get("QVF_TAG_LATTICE_EMBED_MODEL",
                              "text-embedding-3-small")
_EMBED_CACHE_F = Path(r"results/tag_lattice_embed_cache.json")


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


class TagLattice:
    """一次加载,供 _tagged() 反复查询。空/缺失文件时退化为空格(调用方
    应回退纯字符串相等,与冻结行为一致)。"""

    def __init__(self, path: Optional[Path] = None):
        self.nodes: Dict[str, dict] = {}
        self.is_a: List[Tuple[str, str]] = []       # (child, parent)
        self.has_property: List[Tuple[str, str]] = []  # (concept, property)
        self._label_to_node: Dict[str, str] = {}     # normalized alias -> node_id
        self._parents: Dict[str, List[str]] = {}
        self._props: Dict[str, List[str]] = {}
        self._ok = False
        p = path or _LATTICE_F
        if not p.exists():
            return
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        self.nodes = d.get("nodes") or {}
        self.is_a = [tuple(e) for e in (d.get("is_a") or [])]
        self.has_property = [tuple(e) for e in (d.get("has_property") or [])]
        for nid, meta in self.nodes.items():
            labels = [meta.get("label", "")] + list(meta.get("aliases") or [])
            for lab in labels:
                nl = _norm(lab)
                if nl and nl not in self._label_to_node:
                    self._label_to_node[nl] = nid
        for child, parent in self.is_a:
            self._parents.setdefault(child, []).append(parent)
        for concept, prop in self.has_property:
            self._props.setdefault(concept, []).append(prop)
        self._ok = True

    def __bool__(self) -> bool:
        return self._ok

    def node_for(self, label: str) -> Optional[str]:
        return self._label_to_node.get(_norm(label))

    def ancestors(self, node_id: str) -> Set[str]:
        """is-a 闭包(传递;含自身),环路安全。"""
        seen: Set[str] = set()
        stack = [node_id]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self._parents.get(n, []))
        return seen

    def properties_one_hop(self, node_id: str) -> Set[str]:
        """has-property 边(限一跳,不传递)。"""
        return set(self._props.get(node_id, []))

    def satisfies(self, card_tag: str, query_tag: str) -> bool:
        """card_tag(卡片 value_tags 里的一条原始标签)是否在格闭包意义下
        满足 query_tag(编译计划里的 plan.tag)。精确字符串相等作为格内
        特例天然覆盖(同节点)。格未命中任一方时返回 False(调用方回退
        嵌入软匹配)。"""
        if _norm(card_tag) == _norm(query_tag) and card_tag:
            return True
        cn = self.node_for(card_tag)
        qn = self.node_for(query_tag)
        if not cn or not qn:
            return False
        if cn == qn:
            return True
        if qn in self.ancestors(cn):        # ① is-a 传递闭包
            return True
        if qn in self.properties_one_hop(cn):  # ② has-property 一跳
            return True
        return False


# ── 嵌入软匹配(格未命中时的回退;②/③ 都未命中才用) ──────────────
_vec_cache: dict = {}
_cache_loaded = False
_cache_dirty = False
_client = None
_backend_dead = False


def _load_cache():
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    if _EMBED_CACHE_F.exists():
        try:
            _vec_cache.update(
                json.loads(_EMBED_CACHE_F.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass


def _save_cache():
    global _cache_dirty
    if not _cache_dirty:
        return
    try:
        _EMBED_CACHE_F.parent.mkdir(parents=True, exist_ok=True)
        _EMBED_CACHE_F.write_text(json.dumps(_vec_cache), encoding="utf-8")
        _cache_dirty = False
    except Exception:  # noqa: BLE001
        pass


def _embed(texts: List[str]):
    global _client, _backend_dead, _cache_dirty
    if _backend_dead:
        return None
    _load_cache()
    missing = [t for t in texts if f"{_EMBED_MODEL}|{t}" not in _vec_cache]
    if missing:
        try:
            if _client is None:
                from openai import OpenAI
                _client = OpenAI()
            for i in range(0, len(missing), 256):
                batch = [t if t.strip() else " " for t in missing[i:i + 256]]
                r = _client.embeddings.create(model=_EMBED_MODEL, input=batch)
                for t, d in zip(missing[i:i + 256], r.data):
                    _vec_cache[f"{_EMBED_MODEL}|{t}"] = d.embedding
            _cache_dirty = True
            _save_cache()
        except Exception:  # noqa: BLE001
            _backend_dead = True
            return None
    out = []
    for t in texts:
        v = _vec_cache[f"{_EMBED_MODEL}|{t}"]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def embed_similar(card_tag: str, query_tag: str, tau: Optional[float] = None) -> bool:
    """格闭包未命中时的最后回退:原始标签字符串直接嵌入比对,
    余弦 >= tau(默认 QVF_TAG_LATTICE_TAU)。后端不可用时返回 False
    (纯代码回退,不中断跑批)。"""
    if not card_tag or not query_tag:
        return False
    vecs = _embed([_norm(card_tag), _norm(query_tag)])
    if vecs is None:
        return False
    a, b = vecs
    sim = sum(x * y for x, y in zip(a, b))
    return sim >= (tau if tau is not None else _TAU)


_lattice_singleton: Optional[TagLattice] = None


def get_lattice() -> TagLattice:
    global _lattice_singleton
    if _lattice_singleton is None:
        _lattice_singleton = TagLattice()
    return _lattice_singleton


def tag_matches(card_tag: str, query_tag: str, use_embed_fallback: bool = True) -> bool:
    """对外唯一入口:格闭包优先,未命中且 use_embed_fallback 时退嵌入软匹配。"""
    lat = get_lattice()
    if lat.satisfies(card_tag, query_tag):
        return True
    if not use_embed_fallback:
        return False
    return embed_similar(card_tag, query_tag)
