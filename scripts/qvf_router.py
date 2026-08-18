# -*- coding: utf-8 -*-
"""QVF-Router v1:调用门 + 读取时/写入时按题路由的整合系统评测。

路由决策逐题真算(mini 聚焦调用 + 卡片库链深查表,均为部署可用信号);
答案从既有三臂结果按题组合——路由为确定性函数,组合即整合系统输出。
路由规则(原则先行,不做数据调参):
  ① scope=unclear 且无预设值 → direct(调用门:非时序直通)
  ② 聚焦槽位在卡片库中的不同取值数 ≥3(深链) → wt(档案卡裁决)
  ③ 其余(浅更新/杂讯库) → rt(检索后现场抽取)
臂缺行时按 rt→direct 降级并计数。"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from scripts.wt_qvf_prototype import (FOCUS_PROMPT, QueryFocusMini, _norm,  # noqa: E402
                                      _slot_match)

CARDS = Path(r"results/wt_cards")
CACHE_F = Path(r"results/router_focus_cache.json")
MODEL = "claude-haiku-4-5"

# —— 环境旗标(默认全 0/空 = v1.2 冻结行为,输出逐字节不变)——
# QVF_ROUTER_KEYS=1:卡片带 slot_class 时,链深按 (owner, slot_class) 键控
#   计算,聚焦槽位经 SLOT_ALIASES 归一映射;无键卡片/无类命中回退词重叠逻辑。
# QVF_GATE_V2=1:门加宽 —— 时序薄链(键深 < QVF_GATE_DEPTH,默认 3)改走第
#   四路 "prompt"(裁决规则提示词臂);事件算术题(时长/次数)一律 direct。
# QVF_CARDS_KEYED=<dir>:键控卡片覆盖目录(按 uid 先查这里,缺则回落 CARDS)。
_ROUTER_KEYS = int(os.environ.get("QVF_ROUTER_KEYS", "0") or 0)
_GATE_V2 = int(os.environ.get("QVF_GATE_V2", "0") or 0)
_GATE_DEPTH = int(os.environ.get("QVF_GATE_DEPTH", "3") or 3)
_CARDS_KEYED = os.environ.get("QVF_CARDS_KEYED", "")
# QVF_OPEN_SLOT=1:_keyed_depth 的聚焦槽位→slot_class 匹配升级为开放规范化
#   (字符串归一+嵌入相似度;SLOT_ALIASES 降级为快路径缓存;scripts/open_slot)。
# QVF_OPEN_KEYS=1:键控分组以 slot_class 字符串本身为键(other:* 一等公民),
#   字符串归一命中即可入组(不含嵌入级)。两旗标默认 0 = 冻结行为不变。
_OPEN_SLOT = int(os.environ.get("QVF_OPEN_SLOT", "0") or 0)
_OPEN_KEYS = int(os.environ.get("QVF_OPEN_KEYS", "0") or 0)
# QVF_LLM_INTENT=1:事件算术判定从关键词正则升级为 LLM 意图分类(独立缓存,
#   不动 focus 缓存)。默认 0 = 走 _EVENT_ARITH_RE,冻结行为逐字节不变。
#   动因(去耦合原则1 + 08-16 实测):正则 _EVENT_ARITH_RE 在语义上确属事件
#   算术的 624 条盲写改写题上命中率仅 16.2%(longest / count_before 两类为
#   0%),"how often""on how many occasions""stayed the longest"等自然表述
#   全部漏检——关键词路由对改写脆弱,是审计标记的 high 风险项。
_LLM_INTENT = int(os.environ.get("QVF_LLM_INTENT", "0") or 0)
INTENT_CACHE_F = Path(r"results/router_intent_cache.json")

# 聚焦槽位文本 → 规范 slot_class 的别名表(小写子串命中;命中多类时取键深
# 最高者)。类目与 CATALOG_PROMPT_V4 的闭集一致。
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

_EVENT_ARITH_RE = re.compile(
    r"how long|how many times|days between|多久|几次|多少次|隔了",
    re.IGNORECASE)
_FP_RE = re.compile(r"\b(i|me|my|mine)\b", re.IGNORECASE)


def _card_file(uid):
    """键控卡片覆盖目录优先(QVF_CARDS_KEYED;默认空 = 只走 CARDS)。"""
    if _CARDS_KEYED:
        p = Path(_CARDS_KEYED) / f"{uid}.json"
        if p.exists():
            return p
    return CARDS / f"{uid}.json"


def normkey(k):
    k = re.sub(r"_query$", "", k)
    m = re.match(r"(.+?)_(dim\d)", k)
    if m:
        return f"{m.group(1)}|{m.group(2)}"
    return re.sub(r"_q1$", "", k)


def load_arm(path, mode=None):
    d = {}
    if not Path(path).exists():
        return d
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if not s:
            continue
        r = json.loads(s)
        if "error" in r:
            continue
        if mode and r.get("mode") != mode:
            continue
        d[normkey(r["question_id"])] = bool(r.get("judge_correct"))
    return d


BENCHES = [
    # name, data(chain-schema), direct, rt, wt   (None = 无该臂)
    ("chain-212", "data/stale_chain_full.json",
     ("results/framing_chain_h45.jsonl", None),
     ("results/framing_qvf_chain_h45.jsonl", None),
     ("results/wtqvf3_chain_h45.jsonl", None)),
    ("confirm-228", "data/stale_chain_confirm.json",
     ("results/framing_direct_confirm_h45.jsonl", None),
     ("results/framing_qvf_confirm_h45.jsonl", None),
     ("results/wtqvf3_confirm.jsonl", None)),
    ("stale-150", "data/stale400_s50_wt.json",
     ("results/framing_stale50_h45.jsonl", None),
     ("results/framing_qvf_stale50_h45.jsonl", None),
     ("results/wtqvf3_stale50.jsonl", None)),
    ("wiki-P39", "data/wikistate_full.json",
     ("results/wiki_direct_h45.jsonl", None),
     ("results/wiki_qvf_h45.jsonl", None),
     ("results/wiki_wtqvf3_test.jsonl", None)),
    ("wiki-P39-ext", "data/wikistate_full_P39_ext.json",
     ("results/wiki_direct_P39_ext.jsonl", None),
     ("results/wiki_qvf_P39_ext.jsonl", None),
     ("results/wiki_wtqvf3_P39_ext.jsonl", None)),
    ("wiki-P108-w2", "data/wikistate_full_P108_w2.json",
     ("results/wiki_direct_P108_w2.jsonl", None),
     ("results/wiki_qvf_P108_w2.jsonl", None),
     ("results/wiki_wtqvf3_P108_w2.jsonl", None)),
    ("wiki-P108-ext", "data/wikistate_full_P108_ext.json",
     ("results/wiki_direct_P108_ext.jsonl", None),
     ("results/wiki_qvf_P108_ext.jsonl", None),
     ("results/wiki_wtqvf3_P108_ext.jsonl", None)),
    ("wiki-P54-w2", "data/wikistate_full_P54_w2.json",
     ("results/wiki_direct_P54_w2.jsonl", None),
     ("results/wiki_qvf_P54_w2.jsonl", None),
     ("results/wiki_wtqvf3_P54_w2.jsonl", None)),
    ("wiki-P54-ext", "data/wikistate_full_P54_ext.json",
     ("results/wiki_direct_P54_ext.jsonl", None),
     ("results/wiki_qvf_P54_ext.jsonl", None),
     ("results/wiki_wtqvf3_P54_ext.jsonl", None)),
    ("wiki-P551", "data/wikistate_full_P551.json",
     ("results/wiki_direct_P551.jsonl", None), None,
     ("results/wiki_wtqvf3_P551.jsonl", None)),
    ("LME-TR", "data/lme_temporal_reasoning_wt.json",
     ("results/tr_full133.jsonl", "dense_direct"),
     ("results/final2_lmet_h45.jsonl", None),
     ("results/wtqvf3_lmetr.jsonl", None)),
    ("LME-KU", "data/lme_knowledge_update_wt.json",
     ("results/final2_lmek_h45.jsonl", "dense_direct"),
     ("results/final2_lmek_h45.jsonl", "minimal_rules_species2"),
     ("results/wtqvf3_lmeku.jsonl", None)),
    ("LoCoMo", "data/locomo_wt.json",
     ("results/locomo_direct_h45.jsonl", None),
     ("results/locomo_qvf_h45.jsonl", None),
     ("results/wtqvf3_locomo.jsonl", None)),
    # 全量原版考场(系统级整体测量;STALE 条目 50+ 无卡片库=冷库,深度0→rt)
    ("STALE-full", "data/stale400_full_wt.json",
     ("results/stale400_full_direct_v2.jsonl", None),
     ("results/stale400_full_qvf_v2.jsonl", None),
     ("results/wtqvf3_stale50.jsonl", None)),
    ("LoCoMo-full", "data/locomo_full.json",
     ("results/locomo_full_direct.jsonl", None),
     ("results/locomo_full_qvf.jsonl", None),
     ("results/wtqvf3_locomo_full.jsonl", None)),
]

cache = json.loads(CACHE_F.read_text(encoding="utf-8")) if CACHE_F.exists() else {}
client = anthropic.Anthropic()


def focus_of(bench, qid, question):
    key = f"{bench}|{qid}"
    if key in cache:
        return cache[key]
    out = {"slot": "", "scope": "unclear", "presupposed": ""}
    for _ in range(3):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=400, system=FOCUS_PROMPT,
                messages=[{"role": "user", "content": question}],
                output_format=QueryFocusMini)
            f = resp.parsed_output
            if f:
                out = {"slot": f.slot, "scope": f.scope,
                       "presupposed": f.presupposed_value}
                break
        except Exception:  # noqa: BLE001
            continue
    cache[key] = out
    return out


_INTENT_PROMPT = (
    "You classify a single user question about their own history.\n"
    "Answer YES if answering it requires ARITHMETIC OVER EVENTS — counting how "
    "many times something changed, how many distinct values there were, how "
    "long a state lasted, which value lasted longest, or the span between two "
    "events.\n"
    "Answer NO if it asks for a STATE VALUE — what something is now, what it "
    "was on a given date, the sequence of values, or whether a premise about a "
    "value still holds.\n"
    "Reply with exactly one word: YES or NO."
)

intent_cache = (json.loads(INTENT_CACHE_F.read_text(encoding="utf-8"))
                if INTENT_CACHE_F.exists() else {})


def intent_of(bench, qid, question):
    """QVF_LLM_INTENT=1 时的事件算术判定(独立缓存,不污染 focus 缓存)。

    返回 True = 事件算术题。调用失败保守返回 False(= 不直通,走常规路由),
    与正则未命中时的行为一致,故失败不改变分派方向。"""
    key = f"{bench}|{qid}"
    if key in intent_cache:
        return bool(intent_cache[key])
    val = False
    for _ in range(3):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4, system=_INTENT_PROMPT,
                messages=[{"role": "user", "content": question or ""}])
            txt = "".join(b.text for b in resp.content
                          if getattr(b, "type", "") == "text").strip().upper()
            if txt.startswith("YES") or txt.startswith("NO"):
                val = txt.startswith("YES")
                break
        except Exception:  # noqa: BLE001
            continue
    intent_cache[key] = val
    return val


def is_event_arith(question, bench="", qid=""):
    """事件算术判定的统一入口:旗标关=原正则(逐字节等价),开=LLM 意图。"""
    if _LLM_INTENT:
        return intent_of(bench, qid, question or "")
    return bool(_EVENT_ARITH_RE.search(question or ""))


def _keyed_depth(recs, slot, question=None):
    """QVF_ROUTER_KEYS=1:按 (owner, slot_class) 分组的键控链深。
    返回 None = 不可键控(卡片无 slot_class / 聚焦槽位无类命中),调用方
    回退原词重叠逻辑。一人称问题(本组基准默认;question=None 视同一人称)
    且卡片带 owner 时限定 owner∈{"", "user"},防多人库把不同人的同类状态
    并成一条深链;深度按组取最大,不跨 owner 汇总。"""
    keyed = [r for r in recs if r.get("slot_class")]
    if not keyed:
        return None
    fs = _norm(slot)
    matched = [c for c, al in SLOT_ALIASES.items() if any(a in fs for a in al)]
    if _OPEN_SLOT or _OPEN_KEYS:
        from scripts.open_slot import match_classes  # 旗标关闭时不加载
        om = match_classes(slot, {r.get("slot_class", "") for r in keyed},
                           use_embed=bool(_OPEN_SLOT))
        if om:
            matched = om  # 开放命中覆盖词表;未命中保持冻结回退链
    if not matched:
        return None
    first_person = (question is None or _FP_RE.search(question)
                    or "我" in question)
    if first_person and any(r.get("owner") for r in keyed):
        keyed = [r for r in keyed if (r.get("owner") or "") in ("", "user")]
    groups = {}
    for r in keyed:
        cls = r.get("slot_class", "")
        if cls not in matched:
            continue
        v = _norm(r.get("value", ""))
        if v:
            groups.setdefault(((r.get("owner") or ""), cls), set()).add(v)
    if not groups:
        return 0
    return max(len(vs) for vs in groups.values())


def chain_depth(uid, slot, presupposed="", question=None):
    """v3 同款分量深度:关系边+槽位模糊匹配并查集 → 含聚焦槽位的最佳分量的
    不同取值数(无槽位命中时按预设值锚定)。"""
    f = _card_file(uid)
    if not f.exists():
        return 0
    recs = json.loads(f.read_text(encoding="utf-8")).get("records", [])
    n = len(recs)
    if not n:
        return 0
    if _ROUTER_KEYS:
        kd = _keyed_depth(recs, slot, question)
        if kd is not None:
            return kd
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    id2idx = {r.get("record_id"): i for i, r in enumerate(recs) if r.get("record_id")}
    for i, r in enumerate(recs):
        for t in (r.get("relation_target_record_ids") or []):
            j = id2idx.get(t)
            if j is not None:
                union(i, j)
    for i in range(n):
        for j in range(i + 1, n):
            if _slot_match(recs[i].get("slot", ""), recs[j].get("slot", "")):
                union(i, j)
    comps = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    pv = _norm(presupposed)

    def hits(idx):
        h = sum(1 for i in idx if _slot_match(recs[i].get("slot", ""), slot))
        if not h and pv:
            h = sum(1 for i in idx if pv and pv in _norm(recs[i].get("value", "")))
        return h

    def dated_vals(idx):
        return {_norm(recs[i].get("value", "")) for i in idx
                if recs[i].get("stated_date") and _norm(recs[i].get("value", ""))}

    best, best_score = None, -1
    for idx in comps.values():
        h = hits(idx)
        if h == 0:
            continue
        rel = sum(len(recs[i].get("relation_target_record_ids") or []) for i in idx)
        score = 4 * h + min(rel, 3)
        if score > best_score:
            best_score, best = score, idx
    comp_depth = len(dated_vals(best)) if best else 0
    # v1.3:所有含槽位命中的分量的带日期取值并集(修槽位词汇分裂低估;
    # 带日期要求防杂讯膨胀)
    hit_union = []
    for idx in comps.values():
        if hits(idx):
            hit_union.extend(idx)
    direct_idx = [i for i in range(n)
                  if _slot_match(recs[i].get("slot", ""), slot)]
    return max(comp_depth, len(dated_vals(hit_union)), len(dated_vals(direct_idx)))


def route(uid, focus):
    if focus["scope"] == "unclear" and not focus["presupposed"]:
        return "direct"
    depth = chain_depth(uid, focus["slot"], focus.get("presupposed", ""))
    if focus["scope"] in ("trajectory", "point_in_time"):
        return "wt" if depth >= 2 else "rt"
    return "wt" if depth >= 3 else "rt"


# QVF_ROUTER_LEXICAL=<路由表.json>:改用零 LLM 词法路由 + 按库在线自适应,
# 并**跳过聚焦调用**(这正是省下的那次在线 LLM 调用 —— focus_of 的输出只喂
# route_v2,不喂任何一条臂,见本文件 :363-381)。表由 `armdom fit` 产出。
# 未设置(默认)时不加载任何东西,focuses 照常计算、route_v2 照常调用,
# 与本旗标引入前逐字节等价。
# 已知偏差(须同页写明):本 harness 不记录逐题 token,故按库自适应的成本项
# 用表里的先验 tok 代替运行均值。成本项只在 slack 内做同分裁决、不影响准确率
# 自适应,但这意味着此处决策与 armdom 离线评估可能在极少数并列桶上不同。
_LEXICAL_TABLE_PATH = os.environ.get("QVF_ROUTER_LEXICAL", "")
_LEX_TABLE = None
_LEX_ROUTERS = {}


def _lex_router(uid):
    """按库一个 StoreRouter 实例(前瞻 + bandit 由该类结构强制)。"""
    global _LEX_TABLE
    if _LEX_TABLE is None:
        import json as _json
        _LEX_TABLE = _json.loads(
            Path(_LEXICAL_TABLE_PATH).read_text(encoding="utf-8"))
    if uid not in _LEX_ROUTERS:
        from armdom.fit import StoreRouter
        _LEX_ROUTERS[uid] = StoreRouter(_LEX_TABLE)
    return _LEX_ROUTERS[uid]


def route_v2(uid, focus, question="", bench="", qid=""):
    """旗标路由(QVF_ROUTER_KEYS / QVF_GATE_V2 至少其一开启时使用):
    返回 (route, keyed_depth)。GATE_V2 关闭时决策规则与 route() 完全一致,
    仅链深计算可能走键控路径。事件算术判定见 is_event_arith()。"""
    if _GATE_V2 and is_event_arith(question, bench, qid):
        return "direct", None  # 事件算术(时长/计数):卡片裁决无增益,直读
    if focus["scope"] == "unclear" and not focus["presupposed"]:
        return "direct", None
    depth = chain_depth(uid, focus["slot"], focus.get("presupposed", ""),
                        question)
    if focus["scope"] in ("trajectory", "point_in_time"):
        r = "wt" if depth >= 2 else "rt"
    else:
        r = "wt" if depth >= 3 else "rt"
    if _GATE_V2 and r == "rt" and depth < _GATE_DEPTH \
            and _store_max_depth(uid) < _GATE_DEPTH:
        r = "prompt"  # 时序+薄链且整库皆浅:改走裁决规则提示词臂
    return r, depth


_STORE_DEPTH_CACHE = {}


def _store_max_depth(uid):
    """库形态信号:全库 (owner, slot_class) 分组的最大不同值数。
    库里存在深链(≥阈值)说明抽取路径在该库有用武之地,薄槽位问题仍走 rt;
    整库皆浅(STALE 二态/LME 事件流)才值得改派提示词臂。无键控卡时返回 0
    (视为浅,保持 GATE_V2 原行为)。"""
    if uid in _STORE_DEPTH_CACHE:
        return _STORE_DEPTH_CACHE[uid]
    d = 0
    f = _card_file(uid)
    if f.exists():
        try:
            recs = json.loads(f.read_text(encoding="utf-8")).get("records", [])
            groups = {}
            for r in recs:
                cls = r.get("slot_class")
                if not cls:
                    continue
                v = _norm(r.get("value", ""))
                if v:
                    groups.setdefault(((r.get("owner") or ""), cls),
                                      set()).add(v)
            if groups:
                d = max(len(vs) for vs in groups.values())
        except Exception:  # noqa: BLE001
            d = 0
    _STORE_DEPTH_CACHE[uid] = d
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-rows", nargs="+", default=None,
                    help="prompt 臂(裁决规则提示词)预算行 jsonl;缺文件/缺行"
                    "时记 result=None 并计入 missing_rows,不降级不崩溃")
    ap.add_argument("--direct-rows", nargs="+", default=None,
                    help="direct 路由决策的覆盖行 jsonl(可选;缺行回落各场"
                    "次自带 direct 臂)")
    ap.add_argument("--route-log", default=r"results/router_routes.jsonl",
                    help="逐题路由决策 jsonl(仅 QVF_ROUTER_KEYS/QVF_GATE_V2 "
                    "开启时写)")
    a = ap.parse_args()
    v2_active = bool(_ROUTER_KEYS or _GATE_V2)
    prompt_arm = None
    if a.prompt_rows:
        prompt_arm = {}
        for p in a.prompt_rows:
            prompt_arm.update(load_arm(p))
    direct_arm = None
    if a.direct_rows:
        direct_arm = {}
        for p in a.direct_rows:
            direct_arm.update(load_arm(p))
    route_f = open(a.route_log, "w", encoding="utf-8") if v2_active else None
    grand = Counter()
    grand_missing = 0
    grand_router = grand_direct = grand_n = 0
    print(f"{'bench':14s} {'n':>4s} {'direct':>7s} {'rt':>6s} {'wt':>6s} "
          f"{'ROUTER':>7s}  路由分布(direct/rt/wt) 降级")
    for name, data_f, d_spec, r_spec, w_spec in BENCHES:
        arms = {}
        arms["direct"] = load_arm(*d_spec)
        arms["rt"] = load_arm(*r_spec) if r_spec else {}
        arms["wt"] = load_arm(*w_spec) if w_spec else {}
        items = json.loads(Path(data_f).read_text(encoding="utf-8"))
        qs = []
        raw_ids = {}
        for it in items:
            for dim, q in it.get("probing_queries", {}).items():
                rid = f"{it['uid']}_{dim}"
                qid = normkey(rid)
                qs.append((it["uid"], qid, q["q"]))
                raw_ids[qid] = rid
        # 整体测量口径:只要求兜底臂(direct)在场;路由臂缺行走降级链
        # (wt 仅部分覆盖的场次=冷库语义;P39 原卷仍限 test-52 由 wt 行天然决定)
        qs = [x for x in qs if x[1] in arms["direct"]]
        # dev/test 隔离:切分由数据层 split 字段声明(见 data/*.json 的
        # it["split"]∈{"dev","test"});未标注 split 的卷全部参评。
        # 【去耦合记录 08-16】原实现为 `if name == "wiki-P39": qs = [x for x
        # in qs if x[1] in arms["wt"]]`,即用"哪些行恰好存在于 wt 结果文件里"
        # 反推测试集——切分本身正当(P39 dev-5/test-52),但以结果文件定义
        # 测试集形式上等同 cherry-picking。改为数据层显式声明,并由
        # scripts/verify_split_parity.py 证明两者产生的题集逐 qid 相同。
        _split = {it["uid"]: it.get("split", "test") for it in items}
        if any(v != "test" for v in _split.values()):
            qs = [x for x in qs if _split.get(x[0], "test") == "test"]
        if _LEXICAL_TABLE_PATH:
            focuses = [None] * len(qs)   # 词法路由不需要聚焦 —— 省下的就是这次调用
        else:
            with ThreadPoolExecutor(max_workers=8) as ex:
                focuses = list(ex.map(lambda x: focus_of(name, x[1], x[2]), qs))
        CACHE_F.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if _LLM_INTENT:
            INTENT_CACHE_F.write_text(json.dumps(intent_cache, ensure_ascii=False),
                                      encoding="utf-8")
        dist = Counter()
        fallback = 0
        missing = 0
        correct = 0
        for (uid, qid, _q), fo in zip(qs, focuses):
            if v2_active or _LEXICAL_TABLE_PATH:
                # 只换**路由决策的来源**;下游的臂解析/降级/计分一行不改,
                # 这样出问题时能确定是路由的锅而不是别处。
                if _LEXICAL_TABLE_PATH:
                    _sr = _lex_router(uid)
                    r, kd = _sr.pick(_q), None
                else:
                    r, kd = route_v2(uid, fo, _q, name, qid)
                dist[r] += 1
                pick, res = r, None
                if r == "prompt":
                    if prompt_arm and qid in prompt_arm:
                        res = prompt_arm[qid]
                    else:  # 行文件缺失/缺行:记 None 入 missing_rows,不降级
                        missing += 1
                        pick = None
                elif r == "direct" and direct_arm and qid in direct_arm:
                    res = direct_arm[qid]
                else:
                    if qid not in arms[pick]:
                        fallback += 1
                        pick = "rt" if "rt" != r and qid in arms["rt"] else "direct"
                        if qid not in arms[pick]:
                            pick = "direct"
                    res = arms[pick].get(qid, False)
                correct += bool(res)
                if _LEXICAL_TABLE_PATH and pick:
                    # bandit:只回填**实际跑过**的那条臂;没跑的臂线上观测不到。
                    _sr.observe(pick, bool(res), None)
                if route_f:
                    route_f.write(json.dumps(
                        {"bench": name, "uid": uid, "qid": qid,
                         "qid_raw": raw_ids.get(qid), "route": r,
                         "keyed_depth": kd, "picked_arm": pick,
                         "result": res}, ensure_ascii=False) + "\n")
                continue
            r = route(uid, fo)
            dist[r] += 1
            pick = r
            if qid not in arms[pick]:
                fallback += 1
                pick = "rt" if "rt" != r and qid in arms["rt"] else "direct"
                if qid not in arms[pick]:
                    pick = "direct"
            correct += bool(arms[pick].get(qid, False))
        n = len(qs)
        accs = {a: (sum(v for k, v in arms[a].items() if k in {q[1] for q in qs})
                    / n * 100 if arms[a] else float("nan")) for a in arms}
        racc = correct / n * 100 if n else 0
        extra = (f" prompt{dist['prompt']} 缺行{missing}" if v2_active else "")
        print(f"{name:14s} {n:4d} {accs['direct']:6.1f}% "
              f"{(accs['rt'] if arms['rt'] else float('nan')):5.1f}% "
              f"{accs['wt']:5.1f}% {racc:6.1f}%  "
              f"{dist['direct']}/{dist['rt']}/{dist['wt']} 降级{fallback}{extra}")
        grand_missing += missing
        grand_router += correct
        grand_direct += sum(v for k, v in arms["direct"].items() if k in {q[1] for q in qs})
        grand_n += n
        for k, v in dist.items():
            grand[k] += v
    print(f"\nTOTAL n={grand_n}: direct {grand_direct/grand_n*100:.1f}% → "
          f"ROUTER {grand_router/grand_n*100:.1f}%  路由分布 {dict(grand)}"
          + (f"  missing_rows={grand_missing}" if v2_active else ""))
    if route_f:
        route_f.close()
        print(f"route decisions -> {a.route_log}")


if __name__ == "__main__":
    main()
