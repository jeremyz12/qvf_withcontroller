# -*- coding: utf-8 -*-
"""开放槽位规范化(QVF_OPEN_SLOT / QVF_OPEN_KEYS 的共享工具)。

把问题侧槽位短语(聚焦 slot / 编译 plan.slot)规范到卡片库内实际存在的
slot_class 字符串集合(other:* 一等公民)。三级瀑布,前级命中即返回:
  ① 快路径缓存:SLOT_ALIASES 词表命中(与冻结路径同一子串规则)时,返回
     命中类 ∩ 库内在场类并【终止瀑布】(alias 否决:闭集词表已理解该短语,
     类在库内缺席是真阴性——问题问的东西库里没有,应交 fail-closed 显式
     降级,而不是嵌入到别的类上硬凑;dev 实测 'employer'→'other:habit'
     余弦 0.499 的荒谬救援即由此规则挡下);
  ② 字符串归一:小写、_/- 归空格、去 "other:" 前缀,做等值/双向包含/
     词重叠(与 _slot_match 同阈)匹配,other:* 一等公民;
  ③ 嵌入相似度(仅 QVF_OPEN_SLOT=1 时启用;候选仅限 other:* 开放类——
     闭集类归词表管辖):与 QVF_EMBED_BACKEND=openai 管线同款嵌入(默认
     text-embedding-3-small),取余弦 ≥ QVF_OPEN_SLOT_TAU(默认 0.55)的
     最高类,并携带相差 ≤ QVF_OPEN_SLOT_MARGIN(默认 0.03)的同伴类;
     向量落盘缓存(results/open_slot_embed_cache.json),重放确定且零增量
     成本;后端不可用时静默退化为 ①② 纯字符串行为。
全未命中返回 [] —— 调用方回退各自的冻结逻辑(词表未命中不再决定失败,
空证据由 QVF_FAIL_CLOSED 显式降级兜底)。

本模块只被旗标分支延迟 import;旗标全关时冻结路径不加载、不产生任何副作用。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List

# 与 scripts/qvf_router.py / complex_query_arm.py 的 SLOT_ALIASES 逐字一致
# (快路径缓存语义;复制而非导入,避免背上那两个模块的副作用)。
SLOT_ALIASES = {
    "position": ["position", "职位", "job", "role", "chairman", "member",
                 "committee", "议员", "委员", "职务", "任职", "mayor",
                 "minister", "office"],
    "employer": ["employer", "雇主", "company", "工作", "单位", "university",
                 "institute", "works for", "employed"],
    "team": ["team", "球队", "队", "club"],
    "residence": ["residence", "住", "居住", "address", "city", "live",
                  "hometown"],
    "device": ["device", "phone", "laptop", "tablet", "camera", "手机",
               "电脑", "设备"],
    "location": ["location", "位置", "地点", "place", "where"],
    "relationship": ["relationship", "partner", "spouse", "wife", "husband",
                     "girlfriend", "boyfriend", "married", "婚", "恋", "关系"],
}

_TAU = float(os.environ.get("QVF_OPEN_SLOT_TAU", "0.55"))
_MARGIN = float(os.environ.get("QVF_OPEN_SLOT_MARGIN", "0.03"))
_EMBED_MODEL = os.environ.get("QVF_OPEN_SLOT_EMBED_MODEL",
                              "text-embedding-3-small")
_CACHE_F = Path(r"results/open_slot_embed_cache.json")

_vec_cache: dict = {}
_cache_loaded = False
_cache_dirty = False
_client = None
_backend_dead = False


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


def _hum(cls: str) -> str:
    """slot_class 字符串 → 可比对文本("other:musical_instrument" →
    "musical instrument";闭集类原样归一)。"""
    return _norm(str(cls).split(":", 1)[-1])


def _str_match(a: str, b: str) -> bool:
    """与 wt_qvf_prototype._slot_match 同阈的字符串归一匹配(输入已归一)。"""
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    aw, bw = set(a.split()), set(b.split())
    return len(aw & bw) >= max(1, min(len(aw), len(bw)) - 1) and bool(aw & bw)


def _load_cache():
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    if _CACHE_F.exists():
        try:
            _vec_cache.update(json.loads(_CACHE_F.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass


def _save_cache():
    global _cache_dirty
    if not _cache_dirty:
        return
    try:
        _CACHE_F.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_F.write_text(json.dumps(_vec_cache), encoding="utf-8")
        _cache_dirty = False
    except Exception:  # noqa: BLE001
        pass


def _embed(texts: List[str]):
    """批量嵌入(缓存优先);后端失败返回 None(调用方退化为纯字符串)。"""
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
    import math
    out = []
    for t in texts:
        v = _vec_cache[f"{_EMBED_MODEL}|{t}"]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def match_classes(slot_phrase: str, classes_present: Iterable[str],
                  use_embed: bool = True) -> List[str]:
    """槽位短语 → 库内在场 slot_class 字符串列表(见模块 docstring)。
    返回 [] = 三级全未命中,调用方走冻结回退。"""
    present = sorted({c for c in classes_present if c})
    if not present:
        return []
    fs = _norm(slot_phrase or "")
    if not fs:
        return []
    # ① 词表快路径(冻结同规则):命中即终止(alias 否决,见 docstring)
    alias = [c for c, al in SLOT_ALIASES.items() if any(a in fs for a in al)]
    if alias:
        return [c for c in present if c in alias]
    # ② 字符串归一匹配(other:* 一等公民)
    hit = [c for c in present if _str_match(fs, _hum(c))]
    if hit:
        return hit
    # ③ 嵌入相似度(仅 other:* 开放类):top-1 + margin 同伴
    if not use_embed:
        return []
    cand = [c for c in present if c.startswith("other:")]
    if not cand:
        return []
    vecs = _embed([fs] + [_hum(c) for c in cand])
    if vecs is None:
        return []
    q = vecs[0]
    sims = [sum(a * b for a, b in zip(q, v)) for v in vecs[1:]]
    ranked = sorted(zip(cand, sims), key=lambda x: -x[1])
    best_c, best_s = ranked[0]
    if best_s < _TAU:
        return []
    return [c for c, s in ranked if s >= _TAU and best_s - s <= _MARGIN]
