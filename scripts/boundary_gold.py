# -*- coding: utf-8 -*-
"""
scripts/boundary_gold.py

独立金答案推导器(边界情形)。

======================================================================
纪律声明(务必先读)
======================================================================
本文件的全部算子语义依据仅为:
    study_logs/QVF_methods_formalization_20260814.md 的 §1 / §2 / §4
    (记号与库定义、核心命题、11 算子指称语义表)。

实现者在写这份文件的全过程中,没有打开、没有读取:
  - complex_query_arm.py 的 execute_plan / _chain / _hygiene_pool(及任何其他函数);
  - gen_wikistate_complex.py 的出题逻辑。
也没有打开 wt_qvf_prototype.py / qvf_router.py / qvf_algebra.py。

这意味着:本文件的行为如果与 complex_query_arm.py 的执行器口径一致,是"口径经得起
独立复现"的证据;如果不一致,是"口径确为双侧手工同步产物"的证据——两种结果都是本实验
要暴露的东西,不是实现 bug,严禁为了对齐而回头看代码。

文档在若干边界情形下没有把行为写到唯一确定的程度。这些地方逐条记入本文件末尾的
AMBIGUITIES 列表:情形 + 两种可能读法 + 本实现选了哪个(按"最自然读法"),不做代码验证。

输入格式:与 data/wikistate_full_*.json 的 "chain" 字段同构,即
    [{"value": <str>, "date": "YYYY[-MM[-DD]]", "state_span": <str, 本推导器忽略>}, ...]
纯代码实现,零 LLM 调用。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# 哨兵值(不是 chain 上任何一个 v_i,专门标记算子表里点名的"特殊情形")
# ---------------------------------------------------------------------------

BEFORE_EARLIEST = "<BEFORE_EARLIEST_KNOWN_STATE>"   # point_in_time(d), d < t_1 的文档特判输出
EMPTY_CHAIN = "<EMPTY_CHAIN>"                        # chain(k) 为空(库中无该键记录),文档未覆盖，视为退化输入


# ---------------------------------------------------------------------------
# §1 记号与库定义 —— Definition 1/2:记录、键、链
# ---------------------------------------------------------------------------

def _parse_date(date_str: Union[str, _dt.date]) -> _dt.date:
    """
    把 stated_date(定义 1 中的 t)解析为可比较、可做天数运算的 datetime.date。

    [AMBIGUITY-1] 文档定义 1 只说"t 为陈述日期,允许部分日期 YYYY / YYYY-MM"，
    没有规定部分日期该如何折算为可比较的具体日期，也完全没有讨论 data 文件里实际出现
    的 "YYYY-00-00" / "YYYY-MM-00" 记法(月/日用 00 占位表示"未知/未细化到该精度")。
    两种可能读法：
      (a) 缺失分量按该区间"最早可能取值"折算(00 或缺失 -> 1)——本实现采用；
      (b) 缺失分量视为不可比较，需要单独的偏序/精度感知比较逻辑（更复杂，文档未提供）。
    选 (a)：最简单、单调、且与"允许部分日期"这句话最自然地衔接——日期越不精确，
    就当作已知信息范围内最早的一天，不引入文档没有定义的额外机制。
    """
    if isinstance(date_str, _dt.date):
        return date_str
    s = str(date_str).strip()
    parts = s.split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 and parts[1] not in ("", "00") else 1
    day = int(parts[2]) if len(parts) > 2 and parts[2] not in ("", "00") else 1
    month = month or 1
    day = day or 1
    return _dt.date(year, month, day)


@dataclass
class Segment:
    value: Any
    date_raw: str
    date: _dt.date


def build_chain(raw_chain: List[dict]) -> List[Segment]:
    """
    Definition 2(键与链):S|_k 按 t 升序排序，合并相邻同值，得
        chain(k) = <(v_1,t_1), ..., (v_m,t_m)>,  t_1 < ... < t_m,  v_i != v_{i+1}

    raw_chain: [{"value":..., "date":...}, ...]
               —— data/wikistate_full_*.json 的 "chain" 字段格式；state_span 字段
               与金答案推导无关，忽略。

    [AMBIGUITY-2] 文档只说"合并相邻同值"，没有规定合并后的段该取 run 中的哪个 t。
    两种可能读法：
      (a) 取 run 中最早的 t（该状态"开始生效"的日期）——本实现采用；
      (b) 取 run 中最晚的 t（最近一次被重新陈述的日期）。
    选 (a)：链的语义是"状态在何时开始成立"，一个状态被多次重复陈述不改变它的起始时刻，
    这是对"合并"最朴素的理解；(b) 需要额外假设"更晚的复述覆盖更早的起始"，文档没有
    这层意思。

    这一步同时回答了任务里点名的两处边界：
      - count_changes 的"同值相邻段是否计入"：不计入，因为 chain(k) 定义本身已合并，
        m 是在合并之后数的；
      - trajectory 的"同值相邻是否去重"：去重，同理，trajectory 输出的就是 chain(k)。
      这两条不是本算子另加的规则，是 Definition 2 的直接推论。
    """
    if not raw_chain:
        return []

    parsed = [Segment(r["value"], r["date"], _parse_date(r["date"])) for r in raw_chain]
    parsed.sort(key=lambda s: s.date)  # 稳定排序，升序

    merged: List[Segment] = []
    for seg in parsed:
        if merged and merged[-1].value == seg.value:
            continue  # 相邻同值：丢弃后来的重复记录，保留 run 中最早的 t（见 AMBIGUITY-2）
        merged.append(seg)
    return merged


# ---------------------------------------------------------------------------
# §4.1 算子条件化卫生过滤 H —— 本推导器的适用范围声明
# ---------------------------------------------------------------------------
#
# [AMBIGUITY-3] 文档 §4.1：H(pool, op) 对 COUNT_OPS = {count_changes, count_before,
# first_last, longest} 做 dedup_session(drop_datephrase(pool))。这个定义依赖两项
# 信息：(i) 记录所属的会话 id（用于 dedup_session），(ii) 记录是否为"纯日期提及"
# （用于 drop_datephrase）。任务指定的输入格式是 data/wikistate_full_*.json 的
# "chain" 字段（value/date/state_span 三元组），不携带会话 id，也不携带
# datephrase 分类标签。
# 两种可能读法：
#   (a) 既然本推导器拿不到 H 所需的会话粒度/分类信息，H 在本推导器的输入范围内
#       视为恒等（不做额外过滤），只依赖 Definition 2 的相邻同值合并去处理"碎卡"
#       问题的一阶效应——本实现采用；
#   (b) 越权推测"chain 字段在生成时已经是 hygiene 之后的产物"，从而假装 H 已经
#       满足，等价于 (a) 的效果但叙述方式不同。
# 选 (a) 并明确声明：本文件对 COUNT_OPS 不做 §4.1 描述的会话级/日期短语级过滤，
# 因为运行时收到的输入本身不含这些信息；这是"文档要求的操作在给定输入下不可执行"
# 的记录，不是对文档的偏离。


# ---------------------------------------------------------------------------
# §4 算子指称语义 —— 与本次审计相关的 7 个算子(在边界情形下的行为)
# ---------------------------------------------------------------------------

def op_current(chain: List[Segment]):
    """current: v_m（链尾值）。"""
    if not chain:
        return EMPTY_CHAIN
    return chain[-1].value


def op_point_in_time(chain: List[Segment], d: Union[str, _dt.date]):
    """
    point_in_time(d): v_i s.t. t_i <= d < t_{i+1}；d < t_1 时为"早于已知最早状态"。
    右开区间（文档原话）。

    边界核对（均为文档字面推论，非另加规则）：
      - d 恰等于某个 t_i（i<m）：落入 [t_i, t_{i+1})，答 v_i。
      - d 恰等于 t_{i+1}：落入 [t_{i+1}, t_{i+2})，答 v_{i+1}，不是 v_i——
        这正是"右开区间"这句话的意义所在。
      - d < t_1：文档给出的特判输出，不是链上任何值，本实现返回 BEFORE_EARLIEST。
      - d 晚于 t_m（含 d == t_m）：Definition 2 明文"最后一段为 [t_m, +infty)"，
        d >= t_m 一律落在这个无上界区间里，答 v_m。这不是一条需要另外决定的边界
        规则，是把 Definition 2 的最后一段定义代入之后的直接结果。
    """
    if not chain:
        return EMPTY_CHAIN
    dk = _parse_date(d)
    if dk < chain[0].date:
        return BEFORE_EARLIEST
    ans = chain[0].value
    for seg in chain:
        if seg.date <= dk:
            ans = seg.value
        else:
            break
    return ans


def op_trajectory(chain: List[Segment]) -> List[Tuple[Any, str]]:
    """
    trajectory: 全链 <(v_i,t_i)>，逐条带日期输出。
    chain(k) 已经是 Definition 2 合并相邻同值之后的结果，不存在需要本算子
    另行去重的相邻同值项。
    """
    return [(seg.value, seg.date_raw) for seg in chain]


def op_count_changes(chain: List[Segment]) -> int:
    """
    count_changes: m - 1（状态变更次数）。
    m 取自 chain(k)（已合并相邻同值），"同值相邻段"因 Definition 2 从不计入 m。
    """
    return max(len(chain) - 1, 0)


def op_count_before(chain: List[Segment], d: Union[str, _dt.date]) -> int:
    """
    count_before(d): |{ i>=2 : t_i <= d }|（d 前的变更次数）。
    公式字面用的是 <=，不是 <——"d 恰等于某 t_i 是否计入"不是自由裁量项，文档已经
    用符号写死了：计入。
    """
    if not chain:
        return 0
    dk = _parse_date(d)
    return sum(1 for seg in chain[1:] if seg.date <= dk)


def op_first_last(chain: List[Segment], which: str) -> Union[Tuple[Any, str], str]:
    """first_last: (v_1,t_1) / (v_m,t_m)，按问句取首（which='first'）或末（which='last'）。"""
    if not chain:
        return EMPTY_CHAIN
    seg = chain[0] if which == "first" else chain[-1]
    return (seg.value, seg.date_raw)


def op_longest(
    chain: List[Segment], as_of: Optional[Union[str, _dt.date]] = None
) -> Union[Tuple[Any, Union[int, str]], str]:
    """
    longest: argmax_v dur(v), dur(v) = sum_{i: v_i=v} days([t_i, t_{i+1}))。

    [AMBIGUITY-4] 最后一段区间是 [t_m, +infty)（Definition 2）。文档在 §1/§2/§4
    的任何地方都没有给出用来把这个无穷区间闭合成有限天数的参照"现在"日期——它既不是
    库的记号之一，也不是 longest 在 §4 表里的显式参数（表中 longest 一栏不带参数，
    不像 point_in_time(d) / count_before(d) 那样显式接收 d）。
    两种可能读法：
      (a) 没有外部参照时，最后一段不参与"最长"的有限时长竞争（argmax 只在
          i=1..m-1 的有限段上取；若 m=1，没有任何有限段，退化返回该唯一值并标注
          "UNBOUNDED"）——本实现的默认行为；
      (b) 隐式借用某个未写明的"当前时间"把最后一段闭合成有限值再参与比较——
          需要文档之外的信息源，本推导器提供 as_of 可选参数支持这种读法，但不作为
          默认值，因为默认必须只用文档给出的信息就能确定。
    选 (a) 为默认：只依赖文档已写明的量。

    [AMBIGUITY-5] "同值多段累加"：公式 Σ_{i: v_i=v} 明确要求对链上所有取值为 v 的段
    （不论是否相邻）求和——这一条文档已经用求和符号写死，不是待选项，本实现直接照办。

    [AMBIGUITY-6] "并列最长怎么办"：argmax 在多个值并列取到最大 dur 时，数学上是一个
    集合，文档没有规定取哪一个作为单一答案。
    两种可能读法：
      (a) 取"按值在链上首次出现的顺序，最早达到该最大值的那个 v"——本实现采用；
      (b) 返回并列的全部值组成的集合/列表。
    选 (a)：金答案推导器的每个算子调用被期待产出单个可比对的值（供①边界一致率判据
    使用），(b) 会让"一致率"本身的定义复杂化，且文档通篇给的都是单值语义（如
    current/first_last），(a) 与之风格一致。
    """
    if not chain:
        return EMPTY_CHAIN

    m = len(chain)
    durations: dict = {}
    order: List[Any] = []  # 值首次出现顺序，用于打破并列（AMBIGUITY-6）

    for i in range(m - 1):  # 有限段：0-indexed i=0..m-2，对应文档 1-indexed i=1..m-1
        v = chain[i].value
        dur = (chain[i + 1].date - chain[i].date).days
        if v not in durations:
            durations[v] = 0
            order.append(v)
        durations[v] += dur

    if as_of is not None:
        ak = _parse_date(as_of)
        v_last = chain[-1].value
        dur_last = max((ak - chain[-1].date).days, 0)
        if v_last not in durations:
            durations[v_last] = 0
            order.append(v_last)
        durations[v_last] += dur_last

    if not durations:
        # m == 1 且未提供 as_of：唯一一段是开区间，没有可比较的有限时长（AMBIGUITY-4）
        return (chain[0].value, "UNBOUNDED")

    best_dur = max(durations.values())
    for v in order:
        if durations[v] == best_dur:
            return (v, best_dur)
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# 顶层入口:算子名 -> 函数,统一签名 gold(op, raw_chain, **kwargs)
# ---------------------------------------------------------------------------

def gold(op: str, raw_chain: List[dict], **kwargs):
    """
    独立金答案推导入口。

    op in {"current","point_in_time","trajectory","count_changes",
           "count_before","first_last","longest"}
    raw_chain: data/wikistate_full_*.json 的 chain 字段格式
    kwargs: 传给具体算子的参数(如 point_in_time 的 d、first_last 的 which、
            longest 的可选 as_of)
    """
    chain = build_chain(raw_chain)
    if op == "current":
        return op_current(chain)
    if op == "point_in_time":
        return op_point_in_time(chain, kwargs["d"])
    if op == "trajectory":
        return op_trajectory(chain)
    if op == "count_changes":
        return op_count_changes(chain)
    if op == "count_before":
        return op_count_before(chain, kwargs["d"])
    if op == "first_last":
        return op_first_last(chain, kwargs["which"])
    if op == "longest":
        return op_longest(chain, kwargs.get("as_of"))
    raise ValueError(f"boundary_gold 只实现了边界相关的 7 个算子，未知/未覆盖: {op!r}")


# ---------------------------------------------------------------------------
# 歧义清单(AMBIGUITIES) —— 机器可读版本，供上层脚本直接引用/计数
# ---------------------------------------------------------------------------

AMBIGUITIES = [
    {
        "id": "AMBIGUITY-1",
        "site": "_parse_date / Definition 1 的部分日期 (YYYY / YYYY-MM / YYYY-MM-00)",
        "issue": "文档未规定部分日期折算为可比较具体日期的规则",
        "reading_a": "缺失月/日分量按区间最早可能取值折算 (00 或缺失 -> 1)",
        "reading_b": "缺失分量不可比较，需要精度感知的偏序逻辑",
        "chosen": "a",
    },
    {
        "id": "AMBIGUITY-2",
        "site": "build_chain / Definition 2 的“合并相邻同值”",
        "issue": "合并后的段应取 run 中最早还是最晚的 t",
        "reading_a": "取 run 中最早的 t（状态开始生效的日期）",
        "reading_b": "取 run 中最晚的 t（最近一次复述的日期）",
        "chosen": "a",
    },
    {
        "id": "AMBIGUITY-3",
        "site": "§4.1 算子条件化卫生过滤 H，对 COUNT_OPS 的 dedup_session/drop_datephrase",
        "issue": "H 需要会话 id 与 datephrase 分类，任务指定的 chain 字段输入不携带这两项信息",
        "reading_a": "H 在本推导器的输入范围内恒等（不做额外过滤），只靠 Definition 2 的相邻同值合并处理碎卡的一阶效应",
        "reading_b": "假设 chain 字段在生成时已经是 hygiene 之后的产物",
        "chosen": "a",
    },
    {
        "id": "AMBIGUITY-4",
        "site": "longest / 最后一段开区间 [t_m, +infty) 的时长",
        "issue": "文档未给出闭合无穷区间所需的参照“现在”日期，longest 在 §4 表中也不带显式日期参数",
        "reading_a": "无外部参照时最后一段不参与有限时长竞争（argmax 只在有限段上取；m=1 时退化为 UNBOUNDED）",
        "reading_b": "隐式借用未写明的“当前时间”把最后一段闭合为有限值参与比较（本实现以可选 as_of 形式支持，但非默认）",
        "chosen": "a",
    },
    {
        "id": "AMBIGUITY-5",
        "site": "longest / 同值多段是否累加",
        "issue": "非相邻的同值段是否应合并计入 dur(v)",
        "reading_a": "累加（Σ_{i: v_i=v} 已用求和符号写死）",
        "reading_b": "只计最长的单一段，不跨段累加",
        "chosen": "a（文档公式本身已消解此歧义，非自由裁量，仍列出以便审计核对）",
    },
    {
        "id": "AMBIGUITY-6",
        "site": "longest / 并列最长 (argmax 平局)",
        "issue": "多个值取到相同最大 dur(v) 时，argmax 数学上是集合，文档未规定取哪一个作单一金答案",
        "reading_a": "取按值首次出现顺序最早达到最大值的那个 v",
        "reading_b": "返回并列的全部值组成的集合/列表",
        "chosen": "a",
    },
]


# ---------------------------------------------------------------------------
# 自测:20+ 手工小样例
# ---------------------------------------------------------------------------

def _run_self_tests() -> None:
    passed = 0
    failed = []

    def check(name, got, expect):
        nonlocal passed
        ok = got == expect
        if ok:
            passed += 1
        else:
            failed.append((name, got, expect))

    # ---- 基础链(无相邻重复) ----
    chain_a = [
        {"value": "A", "date": "2000-01-01"},
        {"value": "B", "date": "2001-06-15"},
        {"value": "C", "date": "2003-03-10"},
    ]

    # 1. current 基础
    check("1 current basic", gold("current", chain_a), "C")

    # 2. current 在含相邻重复的原始记录上,应先合并再取尾
    chain_a_dup_tail = chain_a + [{"value": "C", "date": "2003-05-01"}]
    check("2 current with adjacent dup tail", gold("current", chain_a_dup_tail), "C")

    # 3. point_in_time: d 落在区间内部
    check("3 pit interior", gold("point_in_time", chain_a, d="2001-08-01"), "B")

    # 4. point_in_time: d 恰等于某 t_i(i<m) -> v_i
    check("4 pit d==t_i", gold("point_in_time", chain_a, d="2001-06-15"), "B")

    # 5. point_in_time: d 恰等于 t_{i+1} -> v_{i+1}, 不是 v_i(右开区间核心)
    check("5 pit d==t_{i+1} boundary", gold("point_in_time", chain_a, d="2003-03-10"), "C")

    # 6. point_in_time: d 早于 t_1 -> BEFORE_EARLIEST
    check("6 pit d<t1", gold("point_in_time", chain_a, d="1999-01-01"), BEFORE_EARLIEST)

    # 7. point_in_time: d 晚于 t_m -> v_m(最后一段 [t_m,+inf))
    check("7 pit d>tm", gold("point_in_time", chain_a, d="2099-01-01"), "C")

    # 8. point_in_time: d == t_m 恰好 -> v_m
    check("8 pit d==tm", gold("point_in_time", chain_a, d="2003-03-10"), "C")

    # 9. count_changes: 基础 m-1
    check("9 count_changes basic", gold("count_changes", chain_a), 2)

    # 10. count_changes: 单段链 -> 0
    chain_single = [{"value": "X", "date": "2010-01-01"}]
    check("10 count_changes single", gold("count_changes", chain_single), 0)

    # 11. count_changes: 原始记录含相邻同值重复卡,不应虚增计数
    chain_noisy = [
        {"value": "A", "date": "2000-01-01"},
        {"value": "A", "date": "2000-02-01"},  # 碎卡:同值重复
        {"value": "B", "date": "2001-01-01"},
        {"value": "B", "date": "2001-03-01"},  # 碎卡:同值重复
        {"value": "C", "date": "2002-01-01"},
    ]
    check("11 count_changes dedup noisy", gold("count_changes", chain_noisy), 2)

    # 12. count_before: d 恰等于某 t_i(i>=2) -> 按 <= 计入(不是 <)
    check("12 count_before d==t_i inclusive", gold("count_before", chain_a, d="2001-06-15"), 1)

    # 13. count_before: d 早于全部变更(甚至早于 t_1)-> 0
    check("13 count_before before all", gold("count_before", chain_a, d="1990-01-01"), 0)

    # 14. count_before: d 晚于全部 -> m-1
    check("14 count_before after all", gold("count_before", chain_a, d="2099-01-01"), 2)

    # 15. count_before: d 恰等于 t_m -> 计入最后一次变更
    check("15 count_before d==tm inclusive", gold("count_before", chain_a, d="2003-03-10"), 2)

    # 16. first_last: first
    check("16 first_last first", gold("first_last", chain_a, which="first"), ("A", "2000-01-01"))

    # 17. first_last: last
    check("17 first_last last", gold("first_last", chain_a, which="last"), ("C", "2003-03-10"))

    # 18. trajectory: 基础,逐条带日期,且原始相邻重复被去重
    check(
        "18 trajectory dedup",
        gold("trajectory", chain_noisy),
        [("A", "2000-01-01"), ("B", "2001-01-01"), ("C", "2002-01-01")],
    )

    # ---- longest 系列 ----
    chain_long = [
        {"value": "A", "date": "2000-01-01"},  # A: 2000-01-01 -> 2000-04-01 = 91 天(闰年2000)
        {"value": "B", "date": "2000-04-01"},  # B: 2000-04-01 -> 2000-04-11 = 10 天
        {"value": "A", "date": "2000-04-11"},  # A: 2000-04-11 -> 2001-01-01(开区间,默认不参与)
    ]

    # 19. longest: 默认(无 as_of)排除最后开区间段,A 的有限段(91天) > B(10天) -> A
    check("19 longest default excludes open tail", gold("longest", chain_long), ("A", 91))

    # 20. longest: 提供 as_of 把最后一段闭合后可能反超
    #     A 累计 = 91(第一段) + (2002-01-01 - 2000-04-11).days(第三段,as_of 之前)
    got20 = gold("longest", chain_long, as_of="2002-01-01")
    expect20_A_total = 91 + (_dt.date(2002, 1, 1) - _dt.date(2000, 4, 11)).days
    check("20 longest with as_of reopens tail", got20, ("A", expect20_A_total))

    # 21. longest: 同值多段(非相邻)累加验证——A 的两段之和 > 单看第一段
    check("21 longest same-value multi-segment sums", got20[1] > 91, True)

    # 22. longest: 单段链(m=1),无 as_of -> UNBOUNDED 退化
    check("22 longest single segment unbounded", gold("longest", chain_single), ("X", "UNBOUNDED"))

    # 23. longest: 并列最长,取首次出现顺序中最早的值
    chain_tie = [
        {"value": "A", "date": "2000-01-01"},  # A: 10天
        {"value": "B", "date": "2000-01-11"},  # B: 10天
        {"value": "C", "date": "2000-01-21"},  # 尾段开区间,默认不参与
    ]
    check("23 longest tie-break earliest-first", gold("longest", chain_tie), ("A", 10))

    # 24. point_in_time: 空链 -> EMPTY_CHAIN
    check("24 pit empty chain", gold("point_in_time", [], d="2000-01-01"), EMPTY_CHAIN)

    # 25. current: 空链 -> EMPTY_CHAIN
    check("25 current empty chain", gold("current", []), EMPTY_CHAIN)

    # 26. 部分日期解析:YYYY-00-00 折算为该年 1月1日,用于排序与比较(AMBIGUITY-1)
    chain_partial = [
        {"value": "P", "date": "1993-00-00"},
        {"value": "Q", "date": "1995-10-04"},
    ]
    check("26 partial date pit", gold("point_in_time", chain_partial, d="1994-01-01"), "P")
    check("27 partial date current", gold("current", chain_partial), "Q")

    # ---- 汇总 ----
    total = passed + len(failed)
    print(f"[boundary_gold self-test] {passed}/{total} passed")
    if failed:
        for name, got, expect in failed:
            print(f"  FAIL {name}: got={got!r} expect={expect!r}")
        raise SystemExit(1)
    else:
        print("[boundary_gold self-test] ALL PASS")
        print(f"[boundary_gold] AMBIGUITIES 记录数: {len(AMBIGUITIES)}")


if __name__ == "__main__":
    _run_self_tests()
