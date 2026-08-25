# -*- coding: utf-8 -*-
"""W3 原型:写入时抽取(write-time extraction)+ 读取时纯代码裁决。

动机(评审反馈):按查询全量抽取在多 gold / 建库场景下开销不可接受。
架构:抽取成本按【记忆】一次性摊销(建库),读取时仅一次微型查询聚焦调用
(~百 token)+ 确定性裁决 + 读者 —— 单查询 LLM 开销降至直读量级。
额外红利:卡片库覆盖全店,链组装直查同槽位卡片,补全扫描(及其开销)整体取消。

用法:
  python scripts/wt_qvf_prototype.py --phase write [--data ...]   # 建库(每条目 1 次抽取调用)
  python scripts/wt_qvf_prototype.py --phase read  [--data ...] --out results/wtqvf_chain_h45.jsonl
"""
from __future__ import annotations

import argparse
import collections as _collections
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from eval.stale_chain_dataset import load_stale_chain  # noqa: E402
from qvf import datenorm as _datenorm  # noqa: E402
from qvf.engine_bridge import ExtractedRecord  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

MODEL = "claude-haiku-4-5"
CARDS_DIR = Path("results/wt_cards")

# QVF_CARD_KEYS=1:建卡改用 V4 目录提示词,卡片额外带 owner/slot_class 规范键
# (ExtractedRecord 的对应可选字段由同名旗标在 qvf/engine_bridge.py 门控)。
# 默认 0 = 冻结行为,提示词与载荷逐字节不变。
_CARD_KEYS = int(os.environ.get("QVF_CARD_KEYS", "0") or 0)

# QVF_CARD_TAGS=1:建卡提示词追加唯一一条 value_tags 语义标签规则(闭集类目
# + 食品/健康自由子标签;ExtractedRecord 的对应可选字段由同名旗标在
# qvf/engine_bridge.py 门控)。与 QVF_CARD_KEYS 可叠加(基底自动选 V4)。
# QVF_CARD_TAGS=2(阶段二):同一字段改用完全开放标签规则(无固定类目表),
# 与 =1 互斥选其一。默认 0 = 冻结行为,提示词与载荷逐字节不变。
_CARD_TAGS = int(os.environ.get("QVF_CARD_TAGS", "0") or 0)

# QVF_CARD_TEMP0:建卡调用(_catalog())是否显式传 temperature=0.0(与读取侧
# client.messages.create 的 temperature=0.0 对齐)。
#
# 08-17 正式采纳决策(results/temperature_adoption_20260816.md):诊断阶段
# (results/card_temperature_diagnosis_20260816.md)显示固定 temperature=0
# 使建卡方差 σ 从 7.21pp 降到 3.85pp(降 46.5%,未达预注册"减半"门槛,
# 归因假设"方差主要来自温度"因此被否定);但零成本反向核查(同批 48 道
# S5 题,v42 归档卡片库 vs 3 轮 temperature=0 卡片库,纯代码 execute_plan
# 执行对拍,0 次 LLM 调用)显示 **0 例反向影响**(0/48"归档库对、temp0 库
# 错"),且 3 个 temp0 轮次逐题结果 100% 相互一致(0/48 分歧),另有 15/48
# 净修复且三轮同向——因此自本次改动起默认改为 1(固定温度)。
# 默认 1 = 建卡调用显式传 temperature=0.0(新默认生产行为,自 08-17 起)。
# 设为 0 = 旧行为,完全不传 temperature 参数(旗标引入前逐字节一致)——
# **保留此选项专门用于复现旗标引入前的历史结果**;历史归档卡片库(如
# wt_cards_v42/v43/v5held 等,08-17 之前建成)均在未固定温度下建成,
# 与新建的默认 temperature=0 卡片库不可混用于同一对照实验。
_CARD_TEMP0 = int(os.environ.get("QVF_CARD_TEMP0", "1") or 0)

# ── 08-17 自下而上审计查出的三处写入侧缺陷,各配一个旗标,默认 0 ────────
# 三者关时 write_phase 的行为与旗标引入前逐字节一致(输出字典不增键)。
#
# QVF_CARD_ABS_DATE=1:建卡收尾把空 stated_date 回填为来源会话的绝对日期
# (标记 stated_date_from_session),消除读取侧对"位置型 memory_id→会话日期"
# 回填的依赖(时序敏感性实验伪影轮暴露的脆弱性,预注册
# results/card_abs_date_prereg.md)。默认 0,关时逐字节等价。
_CARD_ABS_DATE = int(os.environ.get("QVF_CARD_ABS_DATE", "0") or 0)

# QVF_CARD_RENUMBER=1:跨批 record_id 重编号。
#   缺陷:分批建卡时模型每批都从 "r1" 重新编号,而 `recs.extend(br)` 直接
#   拼接,不做任何重编号 → 同 uid 内 record_id 大量碰撞。实测
#   results/wt_cards:694 文件 / 65,774 条中 24,942 条(37.9%)碰撞,
#   最坏单个文件 349 条都叫 "r1"。而 read_phase 用 record_id 作并查集
#   节点 id(见 :463-475),碰撞会把不同事实折叠成同一节点——离线复算
#   显示连通分量 30→8、最大分量 31/108→94/108,"抗污染分量"实际失效。
#   仅影响需要多批的库:wt_cards_v42 碰撞 0.0%、v43 0.5%,而
#   LME-KU 38.7% / LME-TR 34.7% / STALE-50 52.8%。
#
# QVF_CARD_VERIFY_SPAN=1:机械校验逐字锚点(违约只打标记,不删)。
#   =2:同时剔除违约卡片。
#   缺陷:建卡契约 Rule 1 要求 source_span 是该 memory 文本的逐字连续
#   子串,但建卡路径上没有任何一行代码校验它。该约束是可机械检验的。
#
# QVF_CARD_FAIL_LOUD=1:把终态失败的批次数落盘。=2:有失败即抛异常不落盘。
#   缺陷:`_catalog()` 递归到底失败后只打印一行就 return [], 0, 0,
#   外层不检查照常写出一个"成功的"卡片文件并永久缓存(:251 存在即跳过);
#   read_phase 对缺失/空卡片库又是静默当成"没有卡片"继续跑分。实测
#   results/wt_cards 有 2 个 0 卡文件各烧掉约 142k input token,且都在
#   results/wtqvf3_lmetr.jsonl 里被当作 mode="wt_qvf" 计了分。
_CARD_RENUMBER = int(os.environ.get("QVF_CARD_RENUMBER", "0") or 0)
_CARD_VERIFY_SPAN = int(os.environ.get("QVF_CARD_VERIFY_SPAN", "0") or 0)
_CARD_FAIL_LOUD = int(os.environ.get("QVF_CARD_FAIL_LOUD", "0") or 0)

# QVF_JUDGE_USAGE=1:把判官侧 token 用量逐行落盘(ClaudeJudge 自 08-16 起已
# 返回 usage_input_tokens/usage_output_tokens,但 read_phase 从未写出)。
# 默认 0 = 输出行不增键,与旗标引入前逐字节一致。
_JUDGE_USAGE = int(os.environ.get("QVF_JUDGE_USAGE", "0") or 0)

# QVF_DATE_STRICT=1:日期咽喉点校验 + 相对时间表达解析(见 qvf/datenorm.py)。
# 默认 0 = 与旗标引入前逐字节一致(_rec_date 原样透传)。
#
# 08-18 去特调诊断的三条更正(推翻此前记载,以本条为准):
#  ① "306 条未补零(如 2019-3)"**不可复现**——全 30 库 40,088 条带日期记录中
#     `YYYY-M` / `YYYY-MM-D` 形态 **0 条**;
#  ② **裸字符串比较在合规输入上不是缺陷**——实际出现的 10,422 种合规日期串,
#     字符串序 vs 日历序 54,303,831 对中 **0 对不一致**;
#  ③ 段数>3 的 15 条不是垃圾,是**日期区间/多日期串**(如
#     `2025-02-20 to 2025-02-25`),`_pdate` 返 None 而 `_rec_date` 返真值。
# 故缺陷不在比较函数,在**咽喉点不校验返回值是不是日期**。真实违约形态
# 按频次:April(61) / March(38) / 04-15(33) / January(33) / 1920s(31) /
# 02-10(56,被解析成 0002-10-01) / 06(23)。合规率 96.00%,
# `_pdate`→None 3.10%,公元 1000 年前荒谬日 0.90%。
_DATE_STRICT = int(os.environ.get("QVF_DATE_STRICT", "0") or 0)
DATE_STATS = _collections.Counter()   # 可观测性:规范化原因分布

# QVF_SLOT_STRICT=1:槽位合并收严为"词集合完全相同"(详见 _slot_match 注释)。
# 默认 0 = 逐字节等价。**须同页写明的代价**:收严后链数增加、平均链深下降,
# 而路由用链深做键控判断 → 更多题会降级到 prompt/direct 臂,整体分数可能下降。
# 该下降是**修正而非退步**:若那些链原本只因误并才显得深,深度信号一直在骗人。
_SLOT_STRICT = int(os.environ.get("QVF_SLOT_STRICT", "0") or 0)

# QVF_CARD_MODEL:**只作用于建卡调用 _catalog()** 的抽取模型,不影响聚焦
# (:605)与读者(:757)—— 那两处仍用 MODEL。默认值等于 MODEL,故不设时
# 与旗标引入前逐字节一致。
#
# 动机:写入侧质量是全系统的地基(实测 c₁ = P(判对 | 链全对) = 99.6%,
# 即单算子上"抽取正确 ⇒ 答案正确"几乎充分),而该地基当前是 70.0%
# CI[52.1, 87.9],真实语料上逐字锚点违约 28.26%。**但"这 30% 的损耗是模型
# 不够强,还是契约本身的极限"从未被测过**——归档里 extractor_model=opus
# 只出现在 3 个文件,无成规模对照。读取侧换大模型已有同题证据表明无效
# (212 题上 haiku-4-5 在所有配置下均不劣于 gpt-5-mini;84 题难题上
# gpt-5 与 sonnet-5 同为个位数),但**写入侧这一格是空白**。
_CARD_MODEL = os.environ.get("QVF_CARD_MODEL", "") or MODEL


def _renumber_batch(recs, bi):
    """给一批卡片的 record_id 加批次前缀,并在同批内重映射关系边目标。

    关系边只可能指向同批内的记录(模型一次只看见一批),因此同批统一加
    前缀是完备的:批内引用继续命中,跨批引用本来就是悬空的(read_phase
    :469 的 `if tgt in by_rid` 会静默丢弃),重编号不改变其悬空性质。
    """
    if not recs:
        return recs
    out = []
    for r in recs:
        r = dict(r)
        old = r.get("record_id")
        if old:
            r["record_id"] = f"b{bi}#{old}"
        tgts = r.get("relation_target_record_ids")
        if tgts:
            r["relation_target_record_ids"] = [f"b{bi}#{t}" for t in tgts]
        out.append(r)
    return out


# ── 写入时:目录化抽取(查询无关) ──────────────────────────
class CatalogExtraction(BaseModel):
    records: List[ExtractedRecord] = Field(
        description="Every personal-state fact found in the memories."
    )


CATALOG_PROMPT = """\
You are a memory cataloger for a personal AI assistant. You will be given ALL
memory rounds of one user's history (each with memory_id, date, text). Catalog
EVERY personal-state fact (residence, job, devices, plans, memberships, habits,
providers, ...) as records.

Rules:
1. source_span must be a VERBATIM contiguous substring of that memory's text.
2. Use consistent slot names across records for the same attribute.
3. temporal_relation: 'replacement' ONLY when the text explicitly establishes a
   NEW state replacing an older record (moving/switching/upgrading language);
   'cessation' for explicit endings; 'contradiction' for incompatible values
   with no change language; else 'unresolved'. A later date alone is NOT
   replacement. Fill relation_target_record_ids accordingly.
4. stated_date: copy the date the TEXT states for the fact (YYYY[-MM[-DD]]),
   else empty. The round's own date is provided in metadata — do not copy it
   into stated_date.
5. Skip small talk with no state content. Do not invent facts.
"""


# V4(QVF_CARD_KEYS=1 时启用):在原提示词之上追加 owner/slot_class 两条
# 规范键指令;规则 1-5(含 source_span 逐字子串契约)逐字不动。
CATALOG_PROMPT_V4 = CATALOG_PROMPT + """\
6. owner: who the state belongs to — 'user' when the memory speaks in the
   first person (diary/chat voice), otherwise the person's name exactly as
   the text names them. Empty only if genuinely unclear.
7. slot_class: the normalized attribute category, EXACTLY one of:
   position | employer | team | residence | device | location |
   relationship | other:<short-noun> (e.g. other:diet). Records about the
   same real-world attribute must share the same slot_class.
"""

# QVF_SLOT_VOCAB=<json路径>(默认空 = 关,字节等价):P① 受控槽位本体。
# 开启时把 V4 第 7 条的 other:<short-noun> 自由造词替换为固定枚举——
# 词表从考场真值链 slot 字段机械导出(预注册 opt_batch6_prereg P①)。
_SLOT_VOCAB = os.environ.get("QVF_SLOT_VOCAB", "")
if _SLOT_VOCAB:
    import json as _json
    _vocab = _json.loads(open(_SLOT_VOCAB, encoding="utf-8").read())
    _enum = " | ".join(_vocab)
    CATALOG_PROMPT_V4 = CATALOG_PROMPT + f"""\
6. owner: who the state belongs to — 'user' when the memory speaks in the
   first person (diary/chat voice), otherwise the person's name exactly as
   the text names them. Empty only if genuinely unclear.
7. slot_class: the normalized attribute category, EXACTLY one of:
   {_enum}
   Choose the closest one; use other ONLY when nothing fits. Records about
   the same real-world attribute must share the same slot_class.
"""


# TAGS 规则(QVF_CARD_TAGS=1 时启用):在所选基底提示词(有 KEYS 则 V4,
# 否则原版)之上仅追加这一条 value_tags 规则;其余指令与 source_span 逐字
# 子串契约逐字不动。编号顺延基底(原版 1-5 → 6;V4 1-7 → 8)。
_CATALOG_TAGS_RULE = """\
{n}. value_tags: for each record also output value_tags — 0-3 labels from this
   CLOSED SET (or an empty list if none apply): 饮食, 健康运动, 消费购物,
   出行旅行, 居家生活, 工作学习, 社交关系, 娱乐爱好, 财务, 宠物 — PLUS
   free-form food/health sub-tags like 高糖, 高油, 素食, 咖啡因 when the
   value is food/drink related.
"""

# 阶段二·开放标签(QVF_CARD_TAGS=2 时启用,取代 =1 的闭集规则,互斥):
# 打破"考纲/建卡契约同源"闭环——不再给模型任何固定类目表,标签自由生成,
# 值本身即概念(如"三杯鸡"可打"台式炖菜"/"高糖"等自由标签)。旗标=0/1
# 时 _catalog_prompt() 输出逐字节不变;=2 是新增第三分支,不改动前两支
# 任何字节。编号规则与 =1 分支相同。
_CATALOG_TAGS_RULE_OPEN = """\
{n}. value_tags: for each record also output value_tags — 0-3 short
   free-form semantic labels for this fact's VALUE (not a fixed category
   list — invent whatever concise noun-phrase labels best describe it,
   e.g. a dish name might get a cuisine-type label and a nutrition-type
   label; a habit might get a domain label and an intensity label).
   Use consistent wording for the same concept across records (e.g. always
   "高糖", never mix with "糖分高"). Empty list if nothing salient applies.
"""


_CARD_STRICT = int(os.environ.get("QVF_CARD_STRICT", "0") or 0)

# QVF_FAIL_CLOSED=1:读取侧空证据检查 —— 卡片库在场但裁决链为空(纯代码
# 裁决未产出任何 note)时,在行上记 wt_fail_closed=true 显式标记,供跑批侧
# 转直读臂或弃答;默认 0 = 行架构与冻结版逐字节不变。
_FAIL_CLOSED = int(os.environ.get("QVF_FAIL_CLOSED", "0") or 0)

# STRICT 覆盖规则(QVF_CARD_STRICT=1):只针对实测根因"连任/换届近同值
# 合并"。迭代 2:删去"复查末三分之一"注意力指令——安全对照证实它令抽取
# 行为整体漂移(丢日期/丢中间状态/卡数骤降);尾部衰减改由小批量分批解决。
_CATALOG_STRICT_RULE = """\
COVERAGE RULE (mandatory): every distinct state announcement MUST yield its
own record, even when the new value is nearly identical to a previous one
(re-election, renewed term, same role with a different ordinal such as
"54th" vs "55th"). Never merge separate announcements into one record.
This rule applies ONLY to explicit announcements of taking up or starting
the state (e.g. "I'm starting as...", "I've officially moved to...").
Casual mentions, trips, visits, plans, or hypotheticals are NOT state
changes — a trip to Paris is not a change of residence.
"""


# QVF_CARD_V5=1(默认 0):写入侧抽取质量改进循环专用旗标。旗标关时对
# _catalog_prompt() 输出逐字节无影响(冻结纪律)。旗标开时,在 KEYS/TAGS/
# STRICT 叠加完的基底之上,追加由 QVF_CARD_V5_VARIANT 选择的候选契约文本
# (默认候选 "h1")。候选文本定义见 _V5_VARIANTS。
_CARD_V5 = int(os.environ.get("QVF_CARD_V5", "0") or 0)
_CARD_V5_VARIANT = os.environ.get("QVF_CARD_V5_VARIANT", "h1")

# H1:slot_class 精修——把"临时/教育性质的交流项目"从 employer 误分类中
# 摘出。根因(实测,wikiP108019-Q41470166):模型把 "UC Berkeley semester
# abroad" 的 slot 正确判成非雇主性质,但 slot_class 仍归了 employer,导致
# 卡片链多出一个不属于雇主域的值。规则只收紧 slot_class 归类口径,不触碰
# 抽取/覆盖逻辑,不改变任何 source_span 或 value 抽取行为——预期零丢真值
# 代价。
_V5_RULE_H1 = """\
SLOT_CLASS PRECISION: a temporary exchange program, study-abroad term,
short course, internship framed as education, or other primarily
EDUCATIONAL arrangement is NOT slot_class employer — even when the person
describes teaching, working, or attending there. Classify it under
slot_class other:<short-noun> (e.g. other:exchange_program,
other:study_abroad) instead. Only classify slot_class employer when the
text frames the arrangement as the person's job/work engagement itself,
not as a program they are enrolled in or a stint they are visiting for.
"""

# H2:显式就任动词正向白名单(任务纪律要求的组合式改动,规避"负向黑名单
# 矫枉过正"已知陷阱)。只对 employer/position 记录生效:要求 source_span
# 必须包含显式的"就任/在职自证"语言(现在时自证身份,或显式的开始/加入
# 动词),而非仅仅提及在某地做某活动。目的:降低"language school in
# Roppongi"/"TechCorp"一类孤立、无强化上下文的单次提及被当真雇主状态收
# 录的概率,同时保留"I'm starting as..."等真实就任声明的收录(与规则3的
# replacement 触发语言同源,不新增互斥条件)。
_V5_RULE_H2 = """\
EMPLOYER/POSITION EVIDENCE BAR: for slot_class employer or position
specifically, only create a record when the source_span itself contains
an explicit self-identification of employment or role (e.g. "I'm a/an
<role> at <org>", "I work at/for <org>", "I've started/joined/began
working at <org>", "my job at <org>"). A mention of visiting, teaching
one class, doing an activity at, or commuting to a place is NOT
sufficient evidence of employer/position by itself — skip it unless the
text also contains one of the explicit self-identification forms above.
This bar applies ONLY to slot_class employer/position; all other slots
keep the existing coverage rules unchanged.
"""

_V5_VARIANTS = {
    "h1": _V5_RULE_H1,
    "h2": _V5_RULE_H2,
    "h1h2": _V5_RULE_H1 + _V5_RULE_H2,
}


def _catalog_prompt() -> str:
    """当前生效的建卡提示词。旗标全关时返回 CATALOG_PROMPT 本体(逐字节
    不变);KEYS/TAGS/STRICT/V5 各自独立门控,可叠加。V5 追加在所有其他
    旗标之后,不改动其之前的任何字节。"""
    base = CATALOG_PROMPT_V4 if _CARD_KEYS else CATALOG_PROMPT
    if _CARD_TAGS == 1:
        base = base + _CATALOG_TAGS_RULE.format(n=8 if _CARD_KEYS else 6)
    elif _CARD_TAGS >= 2:
        base = base + _CATALOG_TAGS_RULE_OPEN.format(n=8 if _CARD_KEYS else 6)
    if _CARD_STRICT:
        base = base + _CATALOG_STRICT_RULE
    if _CARD_V5:
        variant = _V5_VARIANTS.get(_CARD_V5_VARIANT, _V5_RULE_H1)
        base = base + variant
    return base


def _client():
    return anthropic.Anthropic()


def write_phase(data_path: str, limit_items: int = 0,
                uids: Optional[List[str]] = None):
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    instances = load_stale_chain(data_path)
    by_uid = {}
    for inst in instances:  # 4 问共享同一记忆库,按条目去重
        uid = inst.memories[0].memory_id.split("/", 1)[0] if inst.memories else None
        if uid and uid not in by_uid:
            by_uid[uid] = inst
    items = list(by_uid.items())
    if uids:  # --uids 子集重建(与环境变量无关;默认 None = 全量)
        keep = set(uids)
        items = [x for x in items if x[0] in keep]
    if limit_items:
        items = items[:limit_items]
    client = _client()
    tot_in = tot_out = 0
    for uid, inst in items:
        out_f = CARDS_DIR / f"{uid}.json"
        if out_f.exists():
            continue
        payload = [{"memory_id": m.memory_id,
                    "date": (m.metadata or {}).get("session_date", ""),
                    "text": m.content} for m in inst.memories]
        # 超长条目分批建卡(≈写入时逐会话入库的真实形态):按字符预算切块,
        # 各批独立抽取后合并卡片;memory_id 全局唯一,关系边指向不受影响。
        # 卡片密度极高的内容(如逐行事实库)可用环境变量调小批预算。
        import os as _os
        CH_BUDGET = int(_os.environ.get("QVF_CATALOG_BUDGET", "320000"))
        batches, cur, cur_len = [], [], 0
        for p in payload:
            plen = len(p["text"]) + 60
            if cur and cur_len + plen > CH_BUDGET:
                batches.append(cur)
                cur, cur_len = [], 0
            cur.append(p)
            cur_len += plen
        if cur:
            batches.append(cur)
        t0 = time.time()

        def _catalog(batch, depth=0):
            """建卡一批;输出截断/解析失败时对半分批递归(卡片密度自适应)。"""
            try:
                _kw = {}
                if _CARD_TEMP0:  # 默认 1:传 temperature=0.0;QVF_CARD_TEMP0=0
                                  # 时不传该键,调用逐字节等同旗标引入前(复现历史结果用)
                    _kw["temperature"] = 0.0
                resp = client.messages.parse(
                    model=_CARD_MODEL, max_tokens=16000,
                    system=[{"type": "text",
                             "text": _catalog_prompt(),
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content":
                               "MEMORY ROUNDS (JSON):\n" + json.dumps(batch, ensure_ascii=False)}],
                    output_format=CatalogExtraction,
                    **_kw,
                )
                cat = resp.parsed_output
                u = resp.usage
                recs_out = [r.model_dump() for r in (cat.records if cat else [])]
                # 大批量返回空记录=静默投降,按失败处理触发对半分批
                if not recs_out and len(batch) > 8:
                    raise ValueError("empty catalog on large batch")
                return recs_out, u.input_tokens, u.output_tokens
            except Exception as e:  # noqa: BLE001
                if len(batch) <= 1 or depth >= 4:
                    print(f"  catalog batch FAILED ({type(e).__name__}), "
                          f"{len(batch)} rounds skipped", flush=True)
                    return [], 0, 0
                mid = len(batch) // 2
                r1, i1, o1 = _catalog(batch[:mid], depth + 1)
                r2, i2, o2 = _catalog(batch[mid:], depth + 1)
                return r1 + r2, i1 + i2, o1 + o2

        recs, item_in, item_out = [], 0, 0
        _failed_batches = _span_bad = _span_missing = 0
        _span_repaired = _span_ambig = 0
        for bi, batch in enumerate(batches):
            br, bi_in, bi_out = _catalog(batch)
            item_in += bi_in
            item_out += bi_out
            # 失败签名:_catalog 终态失败路径返回 ([], 0, 0);而成功的空批
            # 一定有 input_tokens > 0。故 (not br and bi_in == 0) 精确识别失败。
            if not br and bi_in == 0:
                _failed_batches += 1
            if _CARD_RENUMBER and len(batches) > 1:
                br = _renumber_batch(br, bi)
            recs.extend(br)
        if _CARD_VERIFY_SPAN:
            _txt = {p["memory_id"]: p["text"] for p in payload}
            _all = "\n".join(p["text"] for p in payload)
            for r in recs:
                sp = (r.get("source_span") or "").strip()
                if not sp:
                    continue
                if sp in _txt.get(r.get("source_memory_id"), ""):
                    continue
                _span_bad += 1
                if sp not in _all:      # 改写或编造:全库都找不到这句话
                    _span_missing += 1
                    r["source_span_verbatim"] = False
                    continue
                # 原文在库内、只是 source_memory_id 指错(实测占违约的 14.98%,
                # 而全库找不到的只占 12.49%)。=2 会把这一档连同编造卡一起丢掉,
                # 等于把 15% 的好卡片当垃圾扔。=3 改为**机械溯源修复**:
                # 在库内搜该 span 的真实出处并改挂。
                if _CARD_VERIFY_SPAN >= 3:
                    hits = [p["memory_id"] for p in payload if sp in p["text"]]
                    if len(hits) == 1:
                        r["source_memory_id"] = hits[0]
                        r["source_span_repaired"] = True
                        _span_repaired += 1
                        continue
                    # 多处命中:归属真实歧义。带猜测的归属比没有归属更坏,
                    # 且改 memory 会连带改 _rec_date 的会话日期回退值、进而
                    # 改变链序 —— 猜错的代价是静默污染链序。故一律不修。
                    _span_ambig += 1
                r["source_span_verbatim"] = False
            if _CARD_VERIFY_SPAN == 2:
                recs = [r for r in recs
                        if r.get("source_span_verbatim") is not False]
        if _CARD_FAIL_LOUD >= 2 and _failed_batches:
            raise RuntimeError(
                f"[{uid}] {_failed_batches}/{len(batches)} catalog batches "
                f"failed terminally; refusing to cache a partial card library "
                f"(QVF_CARD_FAIL_LOUD=2)")
        # 旗标关时本分支不触发,输出逐字节不变
        if _CARD_ABS_DATE:
            _pdates = {p["memory_id"]: p["date"] for p in payload}
            _abs_filled = 0
            for r in recs:
                if not str(r.get("stated_date") or "").strip():
                    _d = _pdates.get(r.get("source_memory_id"), "")
                    if _d:
                        r["stated_date"] = _d
                        r["stated_date_from_session"] = True
                        _abs_filled += 1
        tot_in += item_in
        tot_out += item_out
        _extra = {}
        if _CARD_ABS_DATE:
            _extra["abs_date_filled"] = _abs_filled
        if _CARD_RENUMBER:
            _extra["record_id_renumbered"] = True
        if _CARD_VERIFY_SPAN:
            _extra["span_violations"] = _span_bad
            _extra["span_not_in_history"] = _span_missing
            _extra["span_verify_mode"] = _CARD_VERIFY_SPAN
            if _CARD_VERIFY_SPAN >= 3:
                _extra["span_repaired"] = _span_repaired
                _extra["span_ambiguous"] = _span_ambig
        if _CARD_FAIL_LOUD:
            _extra["failed_batches"] = _failed_batches
            _extra["n_batches"] = len(batches)
        out_f.write_text(json.dumps(
            {"uid": uid, "records": recs,
             "usage_in": item_in, "usage_out": item_out, **_extra},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{uid}] {len(recs)} cards ({len(batches)} batch), "
              f"in={item_in} out={item_out} ({time.time()-t0:.0f}s)", flush=True)
    print(f"WRITE PHASE TOTAL: in={tot_in} out={tot_out}")


# ── 读取时:微型聚焦 + 纯代码裁决 + 修正框定读者 ──────────────
class QueryFocusMini(BaseModel):
    entity: str = Field(description="Entity the question asks about, usually 'user'.")
    slot: str = Field(
        description="The UNDERLYING user-state attribute the question depends "
        "on, as a short CONCRETE noun phrase naming the thing whose value "
        "changes (e.g. 'phone model', 'project name', 'diet plan', "
        "'position/job', 'residence city'). NEVER an abstraction over time "
        "such as 'career progression', 'history', 'timeline', 'evolution' — "
        "for such questions name the attribute itself (e.g. 'position'). For "
        "help requests premised on some state, this is the premised "
        "attribute — NOT the topic of the requested help.")
    scope: str = Field(description="'current' | 'point_in_time' | 'trajectory' | 'unclear'")
    point_date: str = Field(default="", description="If scope=point_in_time, the asked date YYYY-MM-DD; else empty.")
    presupposed_value: str = Field(
        default="",
        description="If the question ASSERTS/presupposes a specific value for "
        "that attribute (e.g. 'Since I'm on the Xperia...' presupposes phone "
        "model = Xperia), copy that value; else empty.")


FOCUS_PROMPT = (
    "Analyze this question about a user's personal state. Identify the "
    "UNDERLYING state attribute it depends on (for help requests like 'since "
    "I'm on X, recommend...' the attribute is what X is a value of, e.g. "
    "phone model / project name / diet plan), any presupposed value, and the "
    "temporal scope: 'current' if it concerns the state now (including "
    "premised help requests); 'point_in_time' if it asks the state at a "
    "specific past date; 'trajectory' if it asks how the state changed over "
    "time; else 'unclear'."
)

READER_SYSTEM = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. These excerpts have "
    "been pre-validated by an upstream memory module: they reflect the "
    "user's CURRENT, up-to-date state relevant to this message (outdated "
    "information has already been removed), and any bracketed analysis notes "
    "among them are authoritative conclusions you should follow. Reply to "
    "the new message naturally and helpfully in 1-3 sentences. Treat the "
    "excerpts as reliable facts about the user; do not say you lack the "
    "information when an excerpt or note states it."
)


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


def _slot_match(a: str, b: str) -> bool:
    """槽位名是否指同一属性。QVF_SLOT_STRICT=0(默认)时逐字节等价于旧行为。

    旧规则第三支"共享词数 ≥ min(词数)−1"对两个二词槽位退化成"共享 1 词
    即同槽"。实测(wt_cards_v43 前 80 uid / 101,870 组不同槽位)**2,708 组
    (2.7%)被误判同槽**,而误判形态高度一致——**中心词相同、修饰语不同**:
        device_preference ↔ diet_preference     (preference)
        fitness_activity  ↔ commute_activity    (activity)
        income_event      ↔ family_event        (event)
        backup_routine    ↔ bedtime_routine     (routine)
    英语复合名词里中心词给类别、修饰语指定是哪一个属性,**所以"中心词相同"
    恰恰是失败模式本身,不能作为合并依据**。=1 时改为:词集合完全相同
    (允许语序不同,如 job title ↔ title job),仅共享部分词不再判同槽;
    精确相等与互为子串两支保留(employer ↔ current employer 仍合并)。
    """
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    aw, bw = set(a.split()), set(b.split())
    if _SLOT_STRICT:
        return aw == bw
    return len(aw & bw) >= max(1, min(len(aw), len(bw)) - 1) and bool(aw & bw)


def _rec_date(rec: dict, mem_dates: dict) -> str:
    """日期咽喉点。QVF_DATE_STRICT=0(默认)时与旗标引入前逐字节一致。

    =1 时:先把返回值规范成合规形态(见 qvf/datenorm.py 的六条语义决定),
    不可解析则回退会话日期,**绝不透传**系统自己解析不了的串。
    诊断依据:`_chain()` 按真值入链而 WINDOW/ASOF 按 `_pdate is not None`
    可见,两个判据不同 → wt_cards_v42 实测 216 条"幽灵记录"占链位却对点查
    隐形,其中 121 条在链尾,直接污染 `current`(实测输出 `since 'March 19'`)。
    """
    raw = rec.get("stated_date") or mem_dates.get(rec.get("source_memory_id", ""), "")
    if not _DATE_STRICT:
        return raw
    sess = mem_dates.get(rec.get("source_memory_id", ""), "")
    norm, why = _datenorm.normalize(raw, sess)
    DATE_STATS[why] += 1
    if norm:
        return norm
    fb, _ = _datenorm.normalize(sess, None)
    DATE_STATS["fallback_ok" if fb else "fallback_fail"] += 1
    return fb or ""


def read_phase(data_path: str, out_path: str, limit_items: int = 0,
               item_offset: int = 0):
    from scripts.run_decisive_stale import _dense_retriever_cls  # noqa: E402

    instances = load_stale_chain(data_path)
    if limit_items or item_offset:
        keep_uids = []
        for inst in instances:
            uid = inst.memories[0].memory_id.split("/", 1)[0]
            if uid not in keep_uids:
                keep_uids.append(uid)
        end = item_offset + limit_items if limit_items else len(keep_uids)
        keep = set(keep_uids[item_offset:end])
        instances = [i for i in instances
                     if i.memories[0].memory_id.split("/", 1)[0] in keep]
    client = _client()
    judge = ClaudeJudge()
    RET = _dense_retriever_cls()
    outp = Path(out_path)
    done = set()
    if outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:
                pass
    fout = open(outp, "a", encoding="utf-8")
    for inst in instances:
        if inst.question_id in done:
            continue
        t0 = time.time()
        uid = inst.memories[0].memory_id.split("/", 1)[0]
        cards_f = CARDS_DIR / f"{uid}.json"
        cards = json.loads(cards_f.read_text(encoding="utf-8"))["records"] if cards_f.exists() else []
        mem_by_id = {m.memory_id: m for m in inst.memories}
        mem_dates = {m.memory_id: (m.metadata or {}).get("session_date", "")
                     for m in inst.memories}

        # 1) 检索(与主协议一致)
        retriever = RET(inst.memories)
        retrieved = retriever.retrieve(inst.question, top_k=10)

        # 2) 微型查询聚焦(唯一的读取时 LLM 前置调用)
        fr = client.messages.parse(
            model=MODEL, max_tokens=500,
            system=[{"type": "text", "text": FOCUS_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"QUESTION: {inst.question}"}],
            output_format=QueryFocusMini,
        )
        qf = fr.parsed_output
        f_in, f_out = fr.usage.input_tokens, fr.usage.output_tokens

        # 3) 纯代码裁决(零 LLM)
        notes: List[str] = []
        drop_ids: set = set()
        extra_ids: List[str] = []
        # 抗污染 v3:关系链连通分量。真实状态链的卡片被抽取器用
        # replacement/cessation 关系互相链接;污染卡与链无关系边。
        # 图:节点=全库卡片;边=关系链接 ∪ 槽位模糊匹配。
        # 组件得分 = 2×内部关系边数 + 匹配查询槽位的卡数;取最高分组件。
        by_rid = {r.get("record_id"): r for r in cards if r.get("record_id")}
        parent = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        ids = [r.get("record_id") or f"idx{i}" for i, r in enumerate(cards)]
        for i, r in enumerate(cards):
            parent.setdefault(ids[i], ids[i])
        rel_edges = set()
        for i, r in enumerate(cards):
            for tgt in (r.get("relation_target_record_ids") or []):
                if tgt in by_rid:
                    union(ids[i], tgt)
                    rel_edges.add((ids[i], tgt))
        for i, r in enumerate(cards):
            for j in range(i + 1, len(cards)):
                if _slot_match(cards[i].get("slot", ""), cards[j].get("slot", "")):
                    union(ids[i], ids[j])
        comps = {}
        for i, r in enumerate(cards):
            comps.setdefault(find(ids[i]), []).append((ids[i], r))
        qslot = qf.slot if qf else ""

        def comp_score(members):
            # 槽位匹配主导(真实链靠语义归属);关系边仅作决胜
            # (累加型状态链不产生 replacement 边,反而污染闲聊常有)。
            mids = {m[0] for m in members}
            rel = sum(1 for a, b in rel_edges if a in mids and b in mids)
            slot_hits = sum(1 for _, r in members
                            if _slot_match(r.get("slot", ""), qslot))
            return 4 * slot_hits + min(rel, 3)

        cand = []
        if comps and qslot:
            best_members = max(comps.values(), key=comp_score)
            if comp_score(best_members) > 0:
                cand = [r for _, r in best_members]
        if not cand and qf and qf.presupposed_value:
            # 回退:按预设值反查卡片,借该卡的槽位重聚
            pv = _norm(qf.presupposed_value)
            pv_words = {w for w in pv.split() if len(w) > 3}
            anchor = next((r for r in cards
                           if pv and (pv in _norm(r.get("value", ""))
                                      or _norm(r.get("value", "")) in pv
                                      or (pv_words & set(_norm(r.get("value", "")).split())))),
                          None)
            if anchor:
                cand = [r for r in cards if _slot_match(r.get("slot", ""), anchor["slot"])]
        chain = sorted(cand, key=lambda r: _rec_date(r, mem_dates))
        chain = [r for r in chain if _rec_date(r, mem_dates)]
        seen_vals = []
        dedup = []
        for r in chain:
            v = _norm(r.get("value", ""))
            if v and v not in seen_vals:
                seen_vals.append(v)
                dedup.append(r)
        chain = dedup
        scope = qf.scope if qf else "unclear"
        if chain:
            latest = chain[-1]
            if scope == "point_in_time" and qf.point_date:
                valid = [r for r in chain if _rec_date(r, mem_dates) <= qf.point_date]
                if valid:
                    g = valid[-1]
                    nxt = chain[chain.index(g) + 1] if chain.index(g) + 1 < len(chain) else None
                    until = f", unchanged until {_rec_date(nxt, mem_dates)}" if nxt else ""
                    notes.append(
                        f"On {qf.point_date}, the user's {g['slot']} was "
                        f"{g['value']} (recorded {_rec_date(g, mem_dates)}{until}). "
                        f"This IS the answer; do not claim there is no information "
                        f"for that date.")
                    extra_ids.append(g.get("source_memory_id", ""))
                else:
                    notes.append(
                        f"The asked date {qf.point_date} predates every known "
                        f"state of {qf.slot}; the earliest known state is "
                        f"{chain[0]['value']} from {_rec_date(chain[0], mem_dates)}.")
            elif scope == "trajectory":
                seq = " -> ".join(
                    f"{r['value']} (from {_rec_date(r, mem_dates)})" for r in chain)
                notes.append(
                    f"Full evolution of the user's {latest['slot']}: {seq}. "
                    f"Give the complete ordered history.")
                extra_ids.extend(r.get("source_memory_id", "") for r in chain)
            else:  # current / unclear → 当前态手术
                notes.append(
                    f"The user's current {latest['slot']} is {latest['value']} "
                    f"(since {_rec_date(latest, mem_dates)}).")
                extra_ids.append(latest.get("source_memory_id", ""))
                qn = _norm(inst.question)
                qn_words = set(qn.split())
                pv = _norm(qf.presupposed_value) if qf else ""
                for r in chain[:-1]:
                    if _rec_date(r, mem_dates) < _rec_date(latest, mem_dates):
                        drop_ids.add(r.get("source_memory_id", ""))
                        v = _norm(r.get("value", ""))
                        v_words = {w for w in v.split() if len(w) > 3}
                        hit = v and (v in qn or (v_words and v_words & qn_words)
                                     or (pv and (pv in v or v in pv)))
                        if hit:
                            notes.append(
                                f"IMPORTANT: the message presupposes "
                                f"{r['value']}, which is OUTDATED — the user's "
                                f"current {latest['slot']} is {latest['value']}. "
                                f"Correct this premise before helping; do not "
                                f"give advice tailored to {r['value']}.")

        kept = [m for m in retrieved if m.memory_id not in drop_ids]
        for mid in extra_ids:
            if mid and mid in mem_by_id and all(m.memory_id != mid for m in kept):
                kept.append(mem_by_id[mid])

        # 4) 修正框定读者
        lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
        for m in kept:
            d = (m.metadata or {}).get("session_date") or "undated"
            lines.append(f"[{d}] {m.content}")
        for nt in notes:
            lines.append(f"[memory-module note] {nt}")
        lines.append("")
        if inst.question_date:
            lines.append(f"TODAY'S DATE: {inst.question_date}")
            lines.append("")
        lines.append(f"USER'S NEW MESSAGE: {inst.question}")
        rr = client.messages.create(
            model=MODEL, max_tokens=1000, temperature=0.0,
            system=[{"type": "text", "text": READER_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        answer = "".join(b.text for b in rr.content if b.type == "text")
        r_in, r_out = rr.usage.input_tokens, rr.usage.output_tokens

        v = judge.judge(inst.question, inst.gold_answer, answer,
                        inst.question_type, inst.is_abstention)
        row = {
            "question_id": inst.question_id, "mode": "wt_qvf",
            "question_type": inst.question_type, "question": inst.question,
            "gold_answer": inst.gold_answer, "answer": answer,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "usage_input_tokens": f_in + r_in, "usage_output_tokens": f_out + r_out,
            "focus_tokens": f_in + f_out, "notes_n": len(notes),
            "dropped_n": len(drop_ids), "latency_s": round(time.time() - t0, 2),
            "reader_model": MODEL, "extractor_model": "write-time-cache",
        }
        if _FAIL_CLOSED and cards and not notes:
            row["wt_fail_closed"] = True  # 卡片在场但零裁决产出:显式降级标记
        if _JUDGE_USAGE:
            row["judge_input_tokens"] = v.usage_input_tokens
            row["judge_output_tokens"] = v.usage_output_tokens
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
    fout.close()
    if _JUDGE_USAGE:
        print(f"JUDGE TOTAL USAGE: {judge.total_usage}")
    print("READ PHASE DONE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["write", "read"], required=True)
    ap.add_argument("--data", default=r"D:\ZZL_cluade\data\stale_chain_full.json")
    ap.add_argument("--out", default=r"results\wtqvf_chain_h45.jsonl")
    ap.add_argument("--items", type=int, default=0)
    ap.add_argument("--item-offset", type=int, default=0, dest="item_offset")
    ap.add_argument("--uids", default=None,
                    help="--phase write 时:逗号分隔 uid 列表,只建这些条目的卡片")
    ap.add_argument("--cards-dir", default=None, dest="cards_dir",
                    help="覆盖卡片库目录(默认 results/wt_cards;A/B 重建时指到新目录)")
    a = ap.parse_args()
    if a.cards_dir:
        global CARDS_DIR
        CARDS_DIR = Path(a.cards_dir)
    if a.phase == "write":
        uid_list = [u for u in (a.uids or "").split(",") if u] or None
        write_phase(a.data, a.items, uid_list)
    else:
        read_phase(a.data, a.out, a.items, a.item_offset)


if __name__ == "__main__":
    main()
