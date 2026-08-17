# -*- coding: utf-8 -*-
"""复杂查询编译臂(S1-S7 独立跑批器;完全不触碰冻结路由 qvf_router)。

逐题四步:
  ① COMPILE:一次 haiku 调用(模型走 qvf.config,temperature 0)把问题编译
     为小计划 —— 严格 JSON:{"op", "slot", "slot2", "date", "tag",
     "presupposed", "anchor_index"}(slot2/anchor_index 可选,仅
     join_at_change 用;anchor_index 承接序数锚 "my second employer",
     1-based,与 presupposed 值锚二选一);
  ② EXECUTE:纯代码在键控(+标签)卡片库上执行计划。卡片解析与 qvf_router
     同口径:QVF_CARDS_KEYED 覆盖目录按 uid 先查,缺则回落 results/wt_cards;
     记录按 (owner, slot_class) 分组,聚焦槽位经 SLOT_ALIASES 归一,无键/无类
     命中回退 slot 词重叠;产出证据包(带日期条目行,上限 12 条)+ 计算结论;
  ③ READ:一次 haiku 调用,日常助手口吻(逐字节复用 framing_arm 修正框定
     基线提示词),用户内容 = 证据包条目行 + TODAY'S DATE + 问题,temperature 0;
  ④ JUDGE:qvf.judge.ClaudeJudge 与各臂同口径;gold 为 null(S7)时跳过判官,
     judge_correct=null(S7 另行按 judge_rubric 评审)。

gold 只进判官,绝不进两次 LLM 调用。

用法:
  python scripts/complex_query_arm.py --data data/wikistate_full.json [...] \
      --questions results/wsc_s5.jsonl --out results/complex_s5.jsonl --resume
  python scripts/complex_query_arm.py --data data/stale_chain_full.json \
      --out results/complex_probing.jsonl        # 缺省用条目自带 probing_queries
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from qvf import config  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from scripts.gen_wikistate_complex import parse_partial_date  # noqa: E402
from scripts.wt_qvf_prototype import _norm, _slot_match  # noqa: E402

# 两次 LLM 调用同款小模型;qvf.config 驱动(QVF_ADAPTER_MODEL,默认 haiku-4-5,
# 与 wt_qvf_prototype / qvf_router 的 MODEL 同值)。
MODEL = config.DEFAULT_ADAPTER_MODEL
CARDS = Path(r"results/wt_cards")
# 与 qvf_router 同名同义:键控卡片覆盖目录(按 uid 先查这里,缺则回落 CARDS)。
_CARDS_KEYED = os.environ.get("QVF_CARDS_KEYED", "")

# —— 修复机制旗标(默认全 0 = 冻结行为,输出逐字节不变)——
# QVF_OPEN_SLOT=1:_select_pool 的槽位→slot_class 匹配升级为开放规范化
#   (字符串归一+嵌入相似度;SLOT_ALIASES 词表降级为快路径缓存,未命中不再
#   决定失败;见 scripts/open_slot.py)。
# QVF_OPEN_KEYS=1:键控分组以 slot_class 字符串本身为键(other:* 一等公民),
#   字符串归一命中即可入组,不再要求命中闭集别名表(不含嵌入级)。
# QVF_FAIL_CLOSED=1:execute 后证据包为空时不再交读者猜 —— 跳过读者调用,
#   行记 fail_closed=true(answer 空、judge_correct=null),由跑批侧转直读臂
#   或弃答。
_OPEN_SLOT = int(os.environ.get("QVF_OPEN_SLOT", "0") or 0)
_OPEN_KEYS = int(os.environ.get("QVF_OPEN_KEYS", "0") or 0)
_FAIL_CLOSED = int(os.environ.get("QVF_FAIL_CLOSED", "0") or 0)
# QVF_TAG_LATTICE=1(阶段二):_tagged() 的闭集字符串相等改为格上闭包
# (scripts/tag_lattice.py:is-a 传递闭包 + has-property 一跳 + 格未命中时
# 嵌入软匹配)。默认 0 = 冻结行为,_tagged() 逐字节不变(纯字符串相等)。
# 只延迟 import tag_lattice(旗标关时零副作用、不读 results/tag_lattice.json)。
_TAG_LATTICE = int(os.environ.get("QVF_TAG_LATTICE", "0") or 0)
# QVF_COMPILE_SPEC=1(T4 去耦合):COMPILE_PROMPT 的 6 个 few-shot 与
# gen_wikistate_complex 出题模板逐字/同构(耦合审计 20260815 最高危项,
# n-gram containment 量化见 results/compile_spec_decoupling_20260816.md)。
# 旗标开:平面编译改走 COMPILE_PROMPT_SPEC —— few-shot 替换为 11 算子的
# 指称语义表(复用 study_logs/QVF_methods_formalization_20260814.md §4),
# 至多保留 2 个域外(非考场)示例。默认 0 = 冻结行为,COMPILE_PROMPT 逐
# 字节不变,compile_plan() 走原分支。只影响平面编译器;QVF_ALGEBRA=1 时
# 该旗标不生效(算子表达式编译器用独立的 ALGEBRA_COMPILE_PROMPT)。
_COMPILE_SPEC = int(os.environ.get("QVF_COMPILE_SPEC", "0") or 0)

# 与 scripts/qvf_router.py 的 SLOT_ALIASES 逐字一致(复制而非导入:qvf_router
# 模块级即创建 anthropic 客户端并读聚焦缓存,独立跑批器不背这些副作用)。
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

_FP_RE = re.compile(r"\b(i|me|my|mine)\b", re.IGNORECASE)
_TODAY_RE = re.compile(r"\(Today is ([0-9][0-9-]*)\.?\)")

EVIDENCE_CAP = 12    # 证据包条目行上限
_SPAN_CAP = 240      # 单条 source_span 引文长度上限(防超长行灌爆读者)

OPS = ("current", "point_in_time", "trajectory", "premise_check",
       "count_changes", "longest", "count_before", "first_last",
       "tag_filter", "tag_trend", "join_at_change")


# ── ① COMPILE:问题 → 严格 JSON 小计划 ────────────────────────
class CompiledPlan(BaseModel):
    op: Literal["current", "point_in_time", "trajectory", "premise_check",
                "count_changes", "longest", "count_before", "first_last",
                "tag_filter", "tag_trend", "join_at_change"] = Field(
        description="The single query operation this question compiles to.")
    slot: Optional[str] = Field(
        default=None,
        description="Concrete state attribute the question depends on "
        "(e.g. 'position', 'employer', 'residence city', 'phone model'); "
        "null for tag_filter/tag_trend. For join_at_change this is the "
        "ANCHOR attribute (the one whose change the question refers to).")
    slot2: Optional[str] = Field(
        default=None,
        description="join_at_change only: the OTHER concrete attribute whose "
        "value is asked at the anchor's change date; null otherwise.")
    date: Optional[str] = Field(
        default=None,
        description="The asked date (YYYY-MM-DD) for point_in_time / "
        "count_before; null otherwise.")
    tag: Optional[str] = Field(
        default=None,
        description="Tag label EXACTLY as the question names it (e.g. 饮食, "
        "高糖) for tag_filter/tag_trend; null otherwise.")
    presupposed: Optional[str] = Field(
        default=None,
        description="Value the question asserts/presupposes for the "
        "attribute (premise_check); null otherwise.")
    anchor_index: Optional[int] = Field(
        default=None,
        description="join_at_change only: when the question names the anchor "
        "by ORDINAL instead of by value ('my second employer' -> 2), the "
        "1-based ordinal position in the anchor attribute's dated history; "
        "null otherwise.")


COMPILE_PROMPT = """\
You compile a user's question about their own personal history into ONE
small query plan for a dated personal-state record store. Output STRICT
JSON only, exactly this object and nothing else:
{"op": "<one of: current | point_in_time | trajectory | premise_check |
count_changes | longest | count_before | first_last | tag_filter |
tag_trend | join_at_change>", "slot": <str|null>, "slot2": <str|null>,
"date": <str|null>, "tag": <str|null>, "presupposed": <str|null>,
"anchor_index": <int|null>}

op semantics:
- current: the state now.
- point_in_time: the state at a specific past date (fill date, YYYY-MM-DD).
- trajectory: how the state changed over time (full ordered history).
- premise_check: a help request premised on some state value (fill
  presupposed with that value).
- count_changes: how many times the state changed.
- longest: which value of the state was held the longest.
- count_before: how many different values the state had before a date
  (fill date).
- first_last: the first value and the most recent value.
- tag_filter: list everything mentioned that matches a semantic tag
  (fill tag).
- tag_trend: what was mentioned under a tag category and whether it
  changed over time (fill tag).
- join_at_change: the value of a SECOND attribute at the moment the anchor
  attribute changed to a named value (slot = anchor attribute, presupposed
  = the anchor VALUE named in the question, slot2 = the attribute whose
  value is asked). If the question names the anchor by ORDINAL instead of
  by value ('my second employer', 'my third residence'), fill anchor_index
  with that 1-based ordinal (second = 2, third = 3, ...) and leave
  presupposed null.

Field rules: slot is a short concrete attribute noun phrase, never an
abstraction like 'history' or 'timeline'; slot2 (join_at_change only)
follows the same rules as slot; tag is copied verbatim from the question;
anchor_index (join_at_change only) is a 1-based integer used only for
ordinal anchors; unused fields are null.

Examples:
Q: (Today is 2007-01-22.) How many times did I change my position?
A: {"op": "count_changes", "slot": "position", "date": null, "tag": null, "presupposed": null}
Q: How many different employer values did I have before 2001-05-14?
A: {"op": "count_before", "slot": "employer", "date": "2001-05-14", "tag": null, "presupposed": null}
Q: Looking across everything I've told you, what have I mentioned in the 饮食 (diet/food) category, and has anything about my eating changed over time?
A: {"op": "tag_trend", "slot": null, "date": null, "tag": "饮食", "presupposed": null}
Q: Have I mentioned anything 高糖 (high-sugar)? List what and when.
A: {"op": "tag_filter", "slot": null, "date": null, "tag": "高糖", "presupposed": null}
Q: When I started at CERN, where was I living?
A: {"op": "join_at_change", "slot": "employer", "slot2": "residence", "date": null, "tag": null, "presupposed": "CERN", "anchor_index": null}
Q: When I started at my second employer, where was I living?
A: {"op": "join_at_change", "slot": "employer", "slot2": "residence", "date": null, "tag": null, "presupposed": null, "anchor_index": 2}
"""


# ── T4 去耦合(QVF_COMPILE_SPEC=1):规范文档版编译提示词 ──────────
# 与 COMPILE_PROMPT 的 JSON 输出契约、字段规则逐字一致;唯一区别是把
# "Examples:" 的 6 个与出题模板逐字/同构的 few-shot(n-gram containment
# 量化见 results/compile_spec_decoupling_20260816.md,#1-4 fwd=rev=1.000
# 逐字同构,#5-6 fwd=1.000)换成 11 算子的指称语义表(内容对应
# study_logs/QVF_methods_formalization_20260814.md §4 的 chain/区间定义,
# 译为编译模型可读的英文规范而非重抄该文件),外加至多 2 个域外
# (medication/dosage、园艺 gardening —— 均不出现在 SLOT_ALIASES /
# CLOSED_TAGS / SUB_TAGS / 任何出题模板)示例,仅作 JSON 格式演示。
COMPILE_PROMPT_SPEC = """\
You compile a user's question about their own personal history into ONE
small query plan for a dated personal-state record store. Output STRICT
JSON only, exactly this object and nothing else:
{"op": "<one of: current | point_in_time | trajectory | premise_check |
count_changes | longest | count_before | first_last | tag_filter |
tag_trend | join_at_change>", "slot": <str|null>, "slot2": <str|null>,
"date": <str|null>, "tag": <str|null>, "presupposed": <str|null>,
"anchor_index": <int|null>}

Denotational semantics. Every attribute the user has ever stated a value
for forms a dated CHAIN of states: chain(slot) = <(v_1, t_1), ..., (v_m,
t_m)>, t_1 < t_2 < ... < t_m, consecutive values distinct. Value v_i is
in force over the right-open interval [t_i, t_{i+1}) (the last value's
interval is open-ended: [t_m, +inf)). Tags are an orthogonal label on any
stated fact, independent of slot chains. Pick the op whose semantics
below matches the question, and fill only the fields that op needs;
leave the rest null.

- current -> v_m: the value in force now.
- point_in_time(date) -> v_i such that t_i <= date < t_{i+1}; a date
  before t_1 means "earlier than any known state". Fill date.
- trajectory -> the full ordered chain <(v_1,t_1), ..., (v_m,t_m)>.
- premise_check(presupposed) -> if presupposed equals some past v_i
  (i<m) and differs from v_m, the premise is STALE (report presupposed's
  valid interval and v_m); if presupposed equals v_m, the premise HOLDS.
  Fill presupposed with the value the question asserts.
- count_changes -> m-1, the number of transitions in the chain.
- count_before(date) -> the number of transitions at or before date
  (equivalently: the count of distinct values held strictly before
  date). Fill date.
- first_last -> (v_1, t_1) together with (v_m, t_m): the first-ever
  value and the most recent value.
- longest -> argmax_v of total closed-interval duration summed over all
  segments holding v (the open final segment is excluded).
- tag_filter(tag) -> every stated fact (any slot) whose tag set contains
  tag, each with its date. Fill tag verbatim as the question names it.
- tag_trend(tag) -> every stated fact tagged tag, bucketed by year, to
  characterize whether that topic changed over time. Fill tag verbatim.
- join_at_change(slot, slot2; anchor) -> resolve anchor time t* as the
  date the ANCHOR attribute's chain transitioned to a target value,
  named either by VALUE (fill presupposed with that value) or by
  ORDINAL position in the anchor chain (fill anchor_index, 1-based:
  "my second X" -> 2); then answer point_in_time(t*) on the OTHER
  attribute's chain (slot2). slot = the anchor attribute (the one whose
  change the question refers to); slot2 = the attribute being asked
  about at that moment.

Field rules: slot is a short concrete attribute noun phrase, never an
abstraction like 'history' or 'timeline'; slot2 (join_at_change only)
follows the same rules as slot; tag is copied verbatim from the question;
anchor_index (join_at_change only) is a 1-based integer used only for
ordinal anchors; unused fields are null.

Examples (format demonstration only -- match the semantics above, not
the surface wording of these two questions):
Q: Have I ever mentioned anything about 园艺 (gardening)? Tell me what
and when.
A: {"op": "tag_filter", "slot": null, "date": null, "tag": "园艺", "presupposed": null}
Q: When I switched to my third medication, what was my dosage at that
time?
A: {"op": "join_at_change", "slot": "medication", "slot2": "dosage", "date": null, "tag": null, "presupposed": null, "anchor_index": 3}
"""


# ── ③ READ:日常助手读者(逐字节复用 framing_arm 修正框定基线) ──
READER_SYSTEM = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)


def _client():
    return anthropic.Anthropic()


def compile_plan(client, question: str):
    """一次 haiku 编译调用(重试 3 次);返回 (plan_dict, in_tok, out_tok, ok)。
    全部失败时回落 op=current 的空计划(ok=False),流程不中断。
    QVF_COMPILE_SPEC=1:system 换 COMPILE_PROMPT_SPEC(规范文档版,见旗标
    注释);默认 0 时 _prompt is COMPILE_PROMPT,本函数其余逻辑逐字节
    不变。"""
    _prompt = COMPILE_PROMPT_SPEC if _COMPILE_SPEC else COMPILE_PROMPT
    tin = tout = 0
    for _ in range(3):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=400, temperature=0.0,
                system=[{"type": "text", "text": _prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": question}],
                output_format=CompiledPlan,
            )
            tin += resp.usage.input_tokens
            tout += resp.usage.output_tokens
            p = resp.parsed_output
            if p:
                return p.model_dump(), tin, tout, True
        except Exception:  # noqa: BLE001
            continue
    return ({"op": "current", "slot": None, "date": None, "tag": None,
             "presupposed": None}, tin, tout, False)


# ── ② EXECUTE:纯代码执行计划 ────────────────────────────────
def _card_file(uid: str) -> Path:
    """与 qvf_router._card_file 同口径:覆盖目录优先,回落 CARDS。"""
    if _CARDS_KEYED:
        p = Path(_CARDS_KEYED) / f"{uid}.json"
        if p.exists():
            return p
    return CARDS / f"{uid}.json"


def _load_records(uid: str) -> List[dict]:
    f = _card_file(uid)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("records", [])
    except Exception:  # noqa: BLE001
        return []


def _rec_date(rec: dict, mem_dates: dict) -> str:
    return rec.get("stated_date") or mem_dates.get(
        rec.get("source_memory_id", ""), "")


def _pdate(s: str):
    """部分日期解析(与 S5 gold 生成器同一规约函数);失败返回 None。"""
    try:
        return parse_partial_date(str(s))[0]
    except Exception:  # noqa: BLE001
        return None


def _select_pool_frozen(recs: List[dict], slot: str, mem_dates: dict,
                        question: str = "") -> List[dict]:
    """槽位记录池(冻结路径,一字不改):键控优先((owner, slot_class) 分组
    + SLOT_ALIASES 归一,取带日期不同值数最多的组 —— 与路由键控链深同精神);
    无键卡片/无类命中回退 slot 词重叠(_slot_match)。一人称问题且卡片带
    owner 时限定 owner∈{"", "user"}(与 qvf_router._keyed_depth 同规则)。"""
    fs = _norm(slot or "")
    matched = [c for c, al in SLOT_ALIASES.items() if any(a in fs for a in al)]
    keyed = [r for r in recs if r.get("slot_class")]
    first_person = (not question or _FP_RE.search(question)
                    or "我" in question)
    if keyed and matched:
        kp = keyed
        if first_person and any(r.get("owner") for r in keyed):
            kp = [r for r in keyed if (r.get("owner") or "") in ("", "user")]
        groups: dict = {}
        for r in kp:
            cls = r.get("slot_class", "")
            if cls in matched and _norm(r.get("value", "")):
                groups.setdefault(((r.get("owner") or ""), cls), []).append(r)
        if groups:
            def depth(g):
                return len({_norm(r.get("value", "")) for r in g
                            if _rec_date(r, mem_dates)})
            pool = max(groups.values(), key=depth)
            return sorted(pool, key=lambda r: _rec_date(r, mem_dates))
    pool = [r for r in recs if _slot_match(r.get("slot", ""), slot or "")]
    return sorted(pool, key=lambda r: _rec_date(r, mem_dates))


def _select_pool(recs: List[dict], slot: str, mem_dates: dict,
                 question: str = "") -> List[dict]:
    """冻结路径优先;QVF_OPEN_SLOT/QVF_OPEN_KEYS 仅做【空池救援】:冻结
    选池非空时原样返回(证据逐字节不变),空池时才用开放槽位规范化
    (scripts/open_slot;词表 alias 否决 + 字符串归一 + other:* 嵌入)重找
    记录组。救援也未命中时仍返回空池,交 QVF_FAIL_CLOSED 显式降级。
    dev 迭代 2:救援式取代迭代 1 的覆盖式 —— 覆盖式在 dev 床把 16 道原本
    判对的题的选池换成了更深的错类组(嵌入弱匹配),净负;空池救援保证
    非空池行为零漂移。"""
    pool = _select_pool_frozen(recs, slot, mem_dates, question)
    if pool or not (_OPEN_SLOT or _OPEN_KEYS):
        return pool
    keyed = [r for r in recs if r.get("slot_class")]
    if not keyed:
        return pool
    from scripts.open_slot import match_classes  # 旗标关闭时不加载
    om = match_classes(slot or "", {r.get("slot_class", "") for r in keyed},
                       use_embed=bool(_OPEN_SLOT))
    if not om:
        return pool
    first_person = (not question or _FP_RE.search(question)
                    or "我" in question)
    kp = keyed
    if first_person and any(r.get("owner") for r in keyed):
        kp = [r for r in keyed if (r.get("owner") or "") in ("", "user")]
    groups: dict = {}
    for r in kp:
        cls = r.get("slot_class", "")
        if cls in om and _norm(r.get("value", "")):
            groups.setdefault(((r.get("owner") or ""), cls), []).append(r)
    if not groups:
        return pool

    def depth(g):
        return len({_norm(r.get("value", "")) for r in g
                    if _rec_date(r, mem_dates)})
    rescued = max(groups.values(), key=depth)
    return sorted(rescued, key=lambda r: _rec_date(r, mem_dates))


def _chain(pool: List[dict], mem_dates: dict) -> List[dict]:
    """带日期、相邻去重的有序状态链(相邻同值 = 同一状态延续,合并;
    非相邻重现视为再次变更 —— 与 S5 gold 的逐转移计数口径一致)。"""
    out: List[dict] = []
    for r in pool:
        d = _rec_date(r, mem_dates)
        v = _norm(r.get("value", ""))
        if not d or not v:
            continue
        if out and _norm(out[-1].get("value", "")) == v:
            continue
        out.append(r)
    return out


def _label(rec: dict) -> str:
    return rec.get("slot_class") or rec.get("slot", "") or "state"


def _line(rec: dict, mem_dates: dict) -> str:
    span = str(rec.get("source_span", ""))
    if len(span) > _SPAN_CAP:
        span = span[:_SPAN_CAP] + " ...[truncated]"
    return (f"[{_rec_date(rec, mem_dates) or 'undated'}] "
            f"{_label(rec)}: {rec.get('value', '')} — \"{span}\"")


def _tagged(recs: List[dict], tag: str) -> List[dict]:
    t = (tag or "").strip()
    if _TAG_LATTICE:
        from scripts.tag_lattice import tag_matches  # noqa: E402  (延迟 import)
        return [r for r in recs
                if any(tag_matches((x or "").strip(), t)
                       for x in (r.get("value_tags") or []))]
    return [r for r in recs
            if any((x or "").strip() == t for x in (r.get("value_tags") or []))]


_COUNT_OPS = {"count_changes", "count_before", "first_last", "longest"}
_DATEPHRASE_RE = re.compile(
    r"\b\d+\s+(months?|weeks?|years?|days?)\b|\b(before|after|ago)\b",
    re.IGNORECASE)


def _hygiene_pool(pool: List[dict]) -> List[dict]:
    """计数类算子的池清洗(dev 迭代 1):
    ①值为日期短语的碎卡剔除(如 '6 months before 1980-02-12'——同一宣告句
    被拆出的时间描述,不是状态值);②同一来源会话只保留一张卡(一句话至多
    宣告一个状态;优先带日期、其次值更长的那张)。点查/轨迹算子不经此路,
    保持原语义。"""
    kept = [r for r in pool
            if not _DATEPHRASE_RE.search(str(r.get("value", "")))]
    by_mem: dict = {}
    order: List[str] = []
    for r in kept:
        m = str(r.get("source_memory_id", "")) or f"_r{id(r)}"
        if m not in by_mem:
            by_mem[m] = r
            order.append(m)
        else:
            cur = by_mem[m]
            better = ((bool(r.get("stated_date")), len(str(r.get("value", ""))))
                      > (bool(cur.get("stated_date")),
                         len(str(cur.get("value", "")))))
            if better:
                by_mem[m] = r
    return [by_mem[m] for m in order]


def _ordinal_en(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th'(降级结论行用)。"""
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _exec_join(plan: dict, recs: List[dict], mem_dates: dict,
               question: str = ""):
    """join_at_change:跨槽位 join(零 LLM)。
    ① 锚:计划带 anchor_index(1-based,序数锚 "my Nth <slot>")时直接取
       锚组有序带日期链的第 anchor_index 个元素,越界降级为明示结论行;
       否则(presupposed 路径,原样保持)在 slot 组(同 _select_pool 口径)
       内找 value 与 presupposed 模糊匹配的记录(承 premise_check 的 _norm
       双向包含口径);取锚记录生效日 T;
    ② 在 slot2(经 SLOT_ALIASES 归一,与 slot 同一 _select_pool 路径)组内
       对 T 做 point_in_time 点查;
    证据包 = 锚记录 + 覆盖记录 ± 相邻记录;结论行同时陈述两侧(序数锚另加
    一行序数映射,供读者把 "my Nth ..." 对上具体值)。
    锚未命中/序数越界/锚日期不可解析/副槽位无带日期记录,均降级为明示
    结论行。"""
    slot = plan.get("slot") or ""
    slot2 = plan.get("slot2") or ""
    pv = _norm(plan.get("presupposed") or "")
    ai = plan.get("anchor_index")
    if not isinstance(ai, int) or isinstance(ai, bool):
        ai = None
    ev: List[str] = []
    derived: List[str] = []

    a_chain = _chain(_select_pool(recs, slot, mem_dates, question), mem_dates)
    if ai is not None:
        if 1 <= ai <= len(a_chain):
            anchor = a_chain[ai - 1]
        else:
            ev = [_line(r, mem_dates) for r in a_chain]
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
            ev = [_line(r, mem_dates) for r in a_chain]
            derived.append(
                f"Anchor not found: no dated {slot or 'anchor-attribute'} "
                f"record matching '{plan.get('presupposed') or ''}' exists "
                f"in memory, so the cross-attribute lookup cannot be "
                f"resolved. Say so instead of guessing.")
            return ev[:EVIDENCE_CAP], derived

    a_label = _label(anchor)
    a_value = anchor.get("value", "")
    t_raw = _rec_date(anchor, mem_dates)
    ev.append(_line(anchor, mem_dates))
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

    b_chain = _chain(_select_pool(recs, slot2, mem_dates, question),
                     mem_dates)
    if not b_chain:
        derived.append(
            f"The user's {a_label} changed to {a_value} on {t_raw}, but no "
            f"dated record of {slot2 or 'the other asked attribute'} exists "
            f"in memory to look up at that date.")
        return ev[:EVIDENCE_CAP], derived
    b_dates = [_rec_date(r, mem_dates) for r in b_chain]
    b_values = [str(r.get("value", "")) for r in b_chain]
    b_label = _label(b_chain[-1])
    parsed = [_pdate(d) for d in b_dates]
    gi = None
    for i, pd in enumerate(parsed):
        if pd is not None and pd <= qd:
            gi = i
    if gi is None:
        ev.append(_line(b_chain[0], mem_dates))
        derived.append(
            f"The user's {a_label} changed to {a_value} on {t_raw}, which "
            f"predates every known state of {b_label}; the earliest known "
            f"{b_label} is {b_values[0]} from {b_dates[0]}.")
        return ev[:EVIDENCE_CAP], derived
    ev += [_line(r, mem_dates)
           for r in b_chain[max(0, gi - 1):gi + 2]]
    until = (f", unchanged until {b_dates[gi + 1]}"
             if gi + 1 < len(b_chain) else "")
    derived.append(
        f"The user's {a_label} changed to {a_value} on {t_raw}; on that "
        f"date the user's {b_label} was {b_values[gi]} (recorded "
        f"{b_dates[gi]}{until}). This IS the answer.")
    return ev[:EVIDENCE_CAP], derived


def execute_plan(plan: dict, recs: List[dict], mem_dates: dict,
                 question: str = ""):
    """执行小计划;返回 (证据行 ≤EVIDENCE_CAP, 计算结论行)。零 LLM。"""
    op = plan.get("op") or "current"
    slot = plan.get("slot") or ""
    ev: List[str] = []
    derived: List[str] = []

    if op == "join_at_change":
        return _exec_join(plan, recs, mem_dates, question)

    if op in ("tag_filter", "tag_trend"):
        tag = plan.get("tag") or ""
        hits = sorted(_tagged(recs, tag),
                      key=lambda r: _rec_date(r, mem_dates))
        ev = [_line(r, mem_dates) for r in hits]
        if not hits:
            derived.append(f"No stored item carries the tag {tag}.")
        elif op == "tag_filter":
            derived.append(
                f"{len(hits)} stored item(s) carry the tag {tag}; every one "
                f"is listed above with its date. Mention ONLY these items, "
                f"each with its date; do not add or infer anything beyond "
                f"them.")
        else:  # tag_trend:按年分组的演变
            by_year: dict = {}
            for r in hits:
                y = (_rec_date(r, mem_dates) or "undated")[:4]
                by_year.setdefault(y, []).append(str(r.get("value", "")))
            seq = "; ".join(f"{y}: " + ", ".join(vs)
                            for y, vs in sorted(by_year.items()))
            derived.append(
                f"Items tagged {tag} by year — {seq}. Describe what was "
                f"mentioned and how it evolved, citing ONLY these items "
                f"with their dates; state trends only when two or more "
                f"listed items directly show them, never by inference.")
        return ev[:EVIDENCE_CAP], derived

    pool = _select_pool(recs, slot, mem_dates, question)
    if op in _COUNT_OPS:
        pool = _hygiene_pool(pool)
    chain = _chain(pool, mem_dates)
    ev = [_line(r, mem_dates) for r in chain]
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
        parsed = [_pdate(d) for d in dates]
        gi = None
        for i, pd in enumerate(parsed):
            if pd is not None and qd is not None and pd <= qd:
                gi = i
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
        # 与 gen_wikistate_complex S5a 同口径:仅闭区间,同值多段按值累加。
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


# ── 组合式时序代数門控(QVF_ALGEBRA=1;默认关 = 上面平面路径逐字节
#    不变,本块不导入任何新模块)。旗标开:execute_plan 重绑为宏/表达式
#    解释执行(scripts/qvf_algebra),编译提示词与输出模式换原语文档版
#    (AlgebraProgram 表达式树)。──────────────────────────────
_ALGEBRA = int(os.environ.get("QVF_ALGEBRA", "0") or 0)
if _ALGEBRA:
    from scripts.qvf_algebra import (ALGEBRA_COMPILE_PROMPT,  # noqa: E402
                                     AlgebraProgram, compile_plan_algebra,
                                     execute_plan_algebra)
    COMPILE_PROMPT = ALGEBRA_COMPILE_PROMPT  # noqa: F811
    CompiledPlan = AlgebraProgram  # noqa: F811
    _execute_plan_flat = execute_plan
    _compile_plan_flat = compile_plan

    def execute_plan(plan, recs, mem_dates, question=""):  # noqa: F811
        return execute_plan_algebra(plan, recs, mem_dates, question)

    def compile_plan(client, question: str):  # noqa: F811
        # dev round 2:代数臂改走 messages.create 纯文本编译(见
        # qvf_algebra.compile_plan_algebra 文档字符串——messages.parse 结构
        # 化输出在本模块扩展后的 schema 上被观测到挂起/400)。平面臂路径
        # (旗标关)从不进入本分支,compile_plan 原实现逐字节不变。
        return compile_plan_algebra(client, question, MODEL)


# ── ③ READ:证据包 → 日常口吻回答 ────────────────────────────
def reader_content(ev: List[str], derived: List[str], qdate: str,
                   question: str) -> str:
    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
    lines += ev or ["(no matching records found in memory)"]
    for d in derived:
        lines.append(f"[memory summary] {d}")
    lines.append("")
    if qdate:
        lines.append(f"TODAY'S DATE: {qdate}")
        lines.append("")
    lines.append(f"USER'S NEW MESSAGE: {question}")
    return "\n".join(lines)


# ── 题目装配 ─────────────────────────────────────────────────
def _load_entries(paths: List[str]) -> dict:
    """合并多份 chain 架构数据,按 uid 去重(同 gen_wikistate_complex)。"""
    by_uid: dict = {}
    for f in paths:
        for e in json.loads(Path(f).read_text(encoding="utf-8")):
            by_uid.setdefault(e["uid"], e)
    return by_uid


def _mem_dates(entry: dict) -> dict:
    md = {}
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, _ in enumerate(sess.get("turns", [])):
            md[f"{entry['uid']}/s{si}#r{ri}"] = sess.get("date", "")
    return md


def _query_date(entry: dict, question: str) -> str:
    """TODAY'S DATE:问题自带 (Today is X.) 前缀则用 X(S5/wiki 卷);否则
    末链日期 +1 月(与 eval.stale_chain_dataset.load_stale_chain 同算式)。"""
    m = _TODAY_RE.search(question or "")
    if m:
        return m.group(1)
    try:
        last = str(entry["chain"][-1]["date"])
        y, mo, d = (int(x) for x in last.split("-"))
        mo += 1
        if mo > 12:
            y, mo = y + 1, 1
        return f"{y}-{mo:02d}-{d:02d}"
    except Exception:  # noqa: BLE001
        return ""


def _questions_from_jsonl(path: str) -> List[dict]:
    """gen_wikistate_complex 输出行:uid/qid/qtype/question/gold
    (S7 额外带 judge_rubric,gold=null)。"""
    out = []
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if s:
            out.append(json.loads(s))
    return out


def _questions_from_probing(entries: dict) -> List[dict]:
    """缺省题源:条目自带 probing_queries(dim1/2/4/5 四维混合)。"""
    out = []
    for uid, e in entries.items():
        for dim, q in (e.get("probing_queries") or {}).items():
            out.append({"uid": uid, "qid": f"{uid}_{dim}",
                        "qtype": f"chain-{dim}", "question": q["q"],
                        "gold": q.get("gold")})
    return out


# ── 主流程 ───────────────────────────────────────────────────
def run(data_paths: List[str], questions_path: Optional[str], out_path: str,
        uids: Optional[List[str]], resume: bool):
    entries = _load_entries(data_paths)
    qs = (_questions_from_jsonl(questions_path) if questions_path
          else _questions_from_probing(entries))
    if uids:
        keep = set(uids)
        qs = [q for q in qs if q["uid"] in keep]
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if resume and outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:  # noqa: BLE001
                pass
    fout = open(outp, "a" if resume else "w", encoding="utf-8")
    client = _client()
    judge = ClaudeJudge()
    md_cache: dict = {}
    n_run = n_ok = n_null = n_fc = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done:
            continue
        t0 = time.time()
        entry = entries.get(uid, {})
        if uid not in md_cache:
            md_cache[uid] = _mem_dates(entry)
        mem_dates = md_cache[uid]

        # ① 编译(只见问题)
        plan, c_in, c_out, ok = compile_plan(client, q["question"])
        # ② 纯代码执行(代数臂:类型检查拒绝按 qvf_algebra 文档契约由调用方
        # 接住,记 wellformed=False 并降级为空证据包,不中断跑批;平面臂
        # execute_plan 从不抛出此类异常,故本 try/except 对旗标关时的输出
        # 零影响)
        wellformed = True
        try:
            ev, derived = execute_plan(plan, _load_records(uid), mem_dates,
                                       q["question"])
        except Exception as e:  # noqa: BLE001
            wellformed = False
            ev, derived = [], [
                f"[compile rejected: {type(e).__name__}: {e}] The compiled "
                f"query plan could not be executed; say the requested "
                f"lookup could not be resolved."]
        # ②' fail-closed:空证据包不交读者猜,显式降级标记(跑批侧转直读臂
        #    或弃答;judge_correct=null 不计入本臂判分)
        if _FAIL_CLOSED and not ev:
            row = {
                "question_id": qid, "mode": "complex_arm", "uid": uid,
                "question_type": q.get("qtype"), "question": q["question"],
                "gold_answer": q.get("gold"), "answer": "",
                "plan": plan, "compile_ok": ok, "evidence_n": 0,
                "usage_input_tokens": c_in, "usage_output_tokens": c_out,
                "judge_correct": None,
                "judge_reason": "fail_closed: empty evidence pack; "
                                "batch side must fall back to the direct "
                                "arm or abstain",
                "fail_closed": True,
                "reader_model": MODEL,
                "latency_s": round(time.time() - t0, 2),
            }
            if q.get("judge_rubric"):
                row["judge_rubric"] = q["judge_rubric"]
            if _ALGEBRA:  # 新增字段仅代数臂路径出现,旗标关时行架构逐字节不变
                row["compile_wellformed"] = wellformed
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            n_run += 1
            n_fc += 1
            print(f"[{qid}] op={plan.get('op')} ev=0 FAIL_CLOSED "
                  f"({time.time() - t0:.1f}s)", flush=True)
            continue
        # ③ 读者(只见证据包 + 日期 + 问题)
        qdate = _query_date(entry, q["question"])
        rr = client.messages.create(
            model=MODEL, max_tokens=1000, temperature=0.0,
            system=[{"type": "text", "text": READER_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": reader_content(ev, derived, qdate,
                                                 q["question"])}],
        )
        answer = "".join(b.text for b in rr.content if b.type == "text")

        # ④ 判官(gold 仅在此出现;S7 gold=null 跳过,另行评审)
        gold = q.get("gold")
        if gold is None:
            jc, jr = None, "gold=null (S7): judged separately via rubric"
            n_null += 1
        else:
            v = judge.judge(q["question"], str(gold), answer, q.get("qtype"))
            jc, jr = v.correct, v.reason
            n_ok += bool(jc)

        row = {
            "question_id": qid, "mode": "complex_arm", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": gold, "answer": answer,
            "plan": plan, "compile_ok": ok, "evidence_n": len(ev),
            "usage_input_tokens": c_in + rr.usage.input_tokens,
            "usage_output_tokens": c_out + rr.usage.output_tokens,
            "judge_correct": jc, "judge_reason": jr,
            "reader_model": MODEL, "latency_s": round(time.time() - t0, 2),
        }
        if q.get("judge_rubric"):
            row["judge_rubric"] = q["judge_rubric"]
        if _ALGEBRA:  # 新增字段仅代数臂路径出现,旗标关时行架构逐字节不变
            row["compile_wellformed"] = wellformed
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
        n_run += 1
        print(f"[{qid}] op={plan.get('op')} ev={len(ev)} "
              f"judge={jc} ({time.time() - t0:.1f}s)", flush=True)
    fout.close()
    n_judged = n_run - n_null - n_fc
    acc = f"{n_ok}/{n_judged} = {n_ok / n_judged * 100:.1f}%" if n_judged \
        else "n/a"
    print(f"COMPLEX ARM DONE: ran {n_run} (skipped {len(done)} done); "
          f"judged {n_judged}, correct {acc}; gold=null {n_null}"
          + (f"; fail_closed {n_fc}" if _FAIL_CLOSED else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True,
                    help="一个或多个 chain 架构数据 json(供会话日期/缺省题源)")
    ap.add_argument("--questions", default=None,
                    help="gen_wikistate_complex 输出 jsonl;缺省用条目自带 "
                    "probing_queries")
    ap.add_argument("--out", required=True, help="输出 jsonl 路径")
    ap.add_argument("--uids", default=None,
                    help="逗号分隔 uid 列表,只跑这些条目(默认全量)")
    ap.add_argument("--resume", action="store_true",
                    help="跳过输出文件里已有 question_id 的题,追加写")
    a = ap.parse_args()
    uid_list = [u for u in (a.uids or "").split(",") if u] or None
    run(a.data, a.questions, a.out, uid_list, a.resume)


if __name__ == "__main__":
    main()
