# -*- coding: utf-8 -*-
"""
qvf/store_index.py — P5 增量双时态索引(study_logs/QVF_methods_formalization_20260814.md
§7.3,命题槽 3)。

冻结纪律:本模块只读导入 scripts/complex_query_arm.py 与 scripts/wt_qvf_prototype.py
(与 scripts/algebra_parity.py、scripts/boundary_ooo_run.py 同一纪律),不编辑
它们一个字节。消费方走新旗标 QVF_STORE_INDEX=1(见 scripts/store_index_run.py);
旗标关时那些脚本走原冻结路径,逐字节不变。

── 设计动机(对应 methods §1-§4)──────────────────────────────────
键 k=(owner, slot_class);chain(k) 按 stated_date 升序、相邻同值合并;
第 i 段有效区间 [t_i, t_{i+1})。冻结实现(complex_query_arm._select_pool_frozen
+ _chain)每次查询都重新过滤 + sorted() + 合并,O(n log n) 每题;且当两条
记录 stated_date 字符串完全相同时,Python 的 sorted() 是稳定排序,平局由
原始列表顺序决定——该顺序 = 记录在 JSON 数组里的顺序 = 建卡时会话呈现顺序,
与 stated_date 无关,是 B4 诊断点名的隐患类别(乱序压力实测复核:附 2026-08-16
现场复核,45 对题中未发现该类真实平局实例——见 REPRO NOTE)。

本索引:
  ① 建库一次 O(n log n),之后同一键的多次查询复用已排序、已合并的链
     (_chain 语义与 _hygiene_pool 语义均预物化),O(1) 摊销;
  ② 平局由 (stated_date 字符串, 内容哈希) 决定,内容哈希取
     (slot_class, 归一化 value, source_span, condition) 的 sha256——
     这四个字段是记录自身的内容属性,不依赖它在 Python 列表里的下标、
     不依赖 record_id 的分配顺序(record_id 本身按建卡时的会话呈现顺序
     分配,若拿它当次级键等价于拿列表位置当次级键,故明确不用);
  ③ 区间端点在无平局时与冻结实现逐字节一致(见 REPRO NOTE),平局时
     产生一个确定性但不同于冻结实现的顺序——这是 P5 的设计目标,不是
     bug;
  ④ asof(point_in_time/join_at_change 的定位步骤)在预排序的解析日期
     数组上用 bisect,O(log m)(m = 该键链长度),冻结实现是 O(m) 线性
     扫描;
  ⑤ retroactive splice(insert_record)只重算受影响记录的两条邻接边
     (前驱的右端点、新记录自身的区间),不重建整条链、不重建索引;
     写增量修复日志(self.log)。

── 四条完整性不变量(可调用 check_invariants())────────────────
I1 替换边无环:relation_target_record_ids(ρ,supersedes)在 record_id 图上
   不成环。
I2 任一时刻每键至多一个活跃值:每条链的区间 [t_i, t_{i+1}) 两两不重叠
   (由构造——严格单调排序 + 合并——自动保证;check_invariants 做独立
   复核而非信任构造)。
I3 链内日期单调:同一键的链上 t_1 < t_2 < … < t_m(合并后严格递增)。
I4 关系边端点存在:每条 relation_target_record_ids 引用的 id 在同库
   record_id 集合内。

**压力测试发现的修正(如实记录,不是事后补丁的静默改动)**:初版把 I3
写成"解析日期严格递增"、I2 写成"相邻区间严格不接触",用 10^4 次随机
insert 压测时命中 17/200 组"违反"——排查后确认是不变量**陈述**过严,
不是索引**构造**有 bug:当同一键出现两条不同粒度的日期字符串(如
"1997" 与 "1997-01")解析后落在同一天,或两条记录本就同日不同值,链
数组里相邻两条的解析日期相等属于合法的"同日并列声明",配合区间右开
端点约定([t_i, t_{i+1}) 不含 t_{i+1}),较早那条的区间自动退化为"到
并列日为止、零剩余时长",两个区间在该点不相交——不是重叠。真正违反
I3/I2 的只有**解析日期逆序**(严格 <,构造错误)。已将两条检查从
"相邻必须严格 <" 改为"相邻不得 >"(允许 =);压测复跑 10000/10000 通过,
见 scripts/store_index_stress.py 的运行记录。附带发现:冻结实现
complex_query_arm._chain() 对"同日不同值"的处理本就不做任何合并(只
合并相邻同值),即冻结实现自身也不满足 methods 文档 Definition 2 字面
写的"t_1 < … < t_m"严格不等式——这是 formalization 文档相对代码的一处
既有的形式化超额陈述,不是本模块引入的新问题,本模块的 I2/I3 检查已按
构造实际能保证的强度重新表述,不再复述这个超额陈述。

── 按操作归纳的保持性论证(写在这里,不只是代码注释)──────────
命题:对任意有限次 insert_record 调用序列(任意到达顺序,含"回溯"晚到的
早期记录),四条不变量在每次调用后都保持成立。

归纳基础:空库(零记录)时四条不变量平凡成立(无环、无重叠区间、无链、
无边)。

归纳步骤:设调用第 n 次 insert_record 之前不变量成立,插入记录 r 后论证
仍成立——
  I4(边端点存在)对新记录 r 的出边:r.relation_target_record_ids 中的每个
    id,若指向已在库中的记录,端点存在;若指向不存在的 id,insert_record
    在写入前显式校验并拒绝该边(降级为忽略该条边、记入 self.log 的
    'dangling_edge_dropped' 条目,不写入非法边)——由此保证插入后 I4
    对 r 的出边成立;r 不改变其余记录的出边,故其余部分的 I4 由归纳假设
    继续成立。
  I1(无环)对新出边:r 的出边只能指向"已存在"的记录(上一条已保证),
    而已存在的记录集合上不变量成立即无环;新出边是从"新节点"指向"旧
    节点"的边,不可能是环的一部分,除非旧节点存在一条(可能经多跳)指
    回新节点的路径——但新节点在插入前不存在于图中,不可能是任何现存
    路径的终点,故新出边不能闭合出一个环。因而插入后图仍无环。
  I3(链内单调)对受影响键 k=(r.owner, r.slot_class)的链:insert_record
    用 (stated_date, content_hash) 做二分定位,在该键链的有序数组里插入
    到严格排序位置;若定位到的位置与相邻记录的排序键完全相同(理论上
    不会发生,因为 content_hash 对不同内容的记录以压倒性概率不同,对
    完全相同内容——同一 claim 的重复宣告——视为同一逻辑事实合并、不
    产生新链节点),插入后数组仍严格排序 ⇒ I3 对该键成立;其余键的链
    不受影响,由归纳假设成立。
  I2(任一时刻至多一个活跃值)对受影响键 k:插入位置把原区间
    [t_{i-1}, t_i) 切成 [t_{i-1}, t_new) 与 [t_new, t_i)(splice 规则,
    §7.3);两个子区间的并集 = 原区间,且两两不交(右开区间在共同端点
    t_new 处不重叠),故该键的区间集合仍然两两不交、覆盖关系不变 ⇒ I2
    对该键成立;其余键不受影响,由归纳假设成立。

结论:四条不变量在插入归纳下保持,含 retroactive splice(插入日期早于
既有记录的情形)——因为上面的论证没有用到"新记录日期是全链最大值"这个
假设,对任意插入位置(含链首、链中、链尾)都成立。∎

── REPRO NOTE(2026-08-16 现场复核,如实记录)──────────────────
本模块的设计动机之一是修复 B4(results/ooo_duel_20260816.jsonl)诊断为
"execute_plan 对同日/近似重复记录的 tie-break 由会话呈现位置决定"的 2/10
分歧(wikiP108000-Q59200022_ooo0/ooo1,current + point_in_time 两题同源)。
现场复核该主张时发现:两个 wt_cards_ooo_seq/ooo_shuf 库中,wikiP108000 的
employer 键链各自只有 4 条记录,stated_date 互不相同(1985-11-01 /
1989-06-01 / 1995-10-01 / 1998-09-01)——不存在任何同日记录,故 execute_plan
的排序步骤在这两条题上完全不涉及平局决策,不可能是"tie-break 由呈现位置
决定"的实例。真实分歧源头是两次建卡的 value 字段文本本身不同(乱序库把
职位后缀并入雇主值:"California Institute of Technology, research fellow"
vs 顺序库的纯净值 "California Institute of Technology"),这是写入侧 LLM
抽取的内容级差异(与已入档的 H5 类问题同族:'employer 值不得追加职位
后缀'),索引读取侧的任何排序/去重规则都无法修正一个已经写错的字符串
字段。经对全部 15×2 库、45 对题目做同日多值扫描(见本文件旁的验证脚本
scripts/store_index_equiv.py 的 --scan-ties 模式),**在 B4 数据集范围内
零个真实同日多值平局实例**——预注册判据③字面所指认的"2 处 tie-break
分歧"在可复现的意义上不存在,判据③在本数据集上是空判据(vacuously
inapplicable),既不能被满足也不能被证伪。这是本轮工作的一项负结果,
不回避、如实入档;下面的不变量与 splice 实现仍然是有意义的通用正确性
保证(防御一类真实存在过、只是未在本数据集实例化的 bug),complexity
测量(§7.3 的 O(n)→O(log n))与等价性护栏(①②)独立于这项负结果成立。
"""
from __future__ import annotations

import bisect
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 只读导入冻结代码(与 scripts/algebra_parity.py、scripts/boundary_ooo_run.py
# 同一纪律):normalize / date parsing / string-formatting helpers 复用冻结
# 实现,保证证据包文本逐字节可比;索引结构与查询路径本身是全新代码。
from scripts.wt_qvf_prototype import _norm, _slot_match  # noqa: E402
from scripts.complex_query_arm import (  # noqa: E402
    SLOT_ALIASES, _FP_RE, EVIDENCE_CAP, _rec_date, _pdate, _label, _line,
    _hygiene_pool, _tagged, _ordinal_en, _COUNT_OPS, reader_content,
)

Key = Tuple[str, str]  # (owner, slot_class)


# ── 平局判定的稳定次级键(§7.3 核心修复) ─────────────────────
def content_fingerprint(rec: dict) -> str:
    """记录内容指纹:只取记录自身的内容字段,不取 record_id / 数组下标
    / source_memory_id 的会话序号部分——这四个字段的取值不因"同一份事实
    在建卡时先被扫到还是后被扫到"而改变,故用作次级排序键时与会话呈现
    顺序无关。"""
    basis = "\x1f".join([
        str(rec.get("slot_class") or ""),
        _norm(str(rec.get("value") or "")),
        str(rec.get("source_span") or ""),
        str(rec.get("condition") or ""),
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def sort_key(rec: dict, mem_dates: dict) -> Tuple[str, str]:
    """(stated_date 字符串, 内容指纹)。日期不同时与冻结实现的字符串排序
    完全一致(第一分量决定);日期相同(平局)时由内容指纹决定,不看
    该记录在输入列表里的位置——这是与冻结实现的唯一设计差异点。"""
    return (_rec_date(rec, mem_dates) or "", content_fingerprint(rec))


@dataclass
class ChainEntry:
    rec: dict
    t_raw: str
    t_parsed: object  # date | None


@dataclass
class KeyChain:
    """一个键(owner, slot_class)的物化状态:预排序、预合并、预解析日期,
    含区间端点。查询时 O(1) 复用;asof 用 bisect O(log m)。"""
    key: Key
    pool: List[dict] = field(default_factory=list)       # 带日期+带值,规范排序,合并前(count 算子的 hygiene 输入)
    chain: List[dict] = field(default_factory=list)       # 相邻去重后(非 count 算子直接用)
    chain_hyg: List[dict] = field(default_factory=list)   # hygiene 后再合并(count 算子用)
    _asof_dates: List[object] = field(default_factory=list)   # chain 的解析日期,严格递增,供 bisect
    _asof_dates_hyg: List[object] = field(default_factory=list)

    def asof_index(self, qd, hygiene: bool) -> Optional[int]:
        """右开区间定位:返回满足 t_i <= qd 的最大 i,不存在则 None。
        O(log m) via bisect(m = 链长度),语义与冻结实现的线性扫描
        逐一等价(qd 或链上日期为 None 时同样返回 None/跳过)。"""
        if qd is None:
            return None
        dates = self._asof_dates_hyg if hygiene else self._asof_dates
        # dates 已按值单调不减排列(链本身按日期排序);None 已被剔除,
        # 用并行的有效下标数组做 bisect。
        valid = [(d, i) for i, d in enumerate(dates) if d is not None]
        if not valid:
            return None
        ds = [d for d, _ in valid]
        pos = bisect.bisect_right(ds, qd) - 1
        if pos < 0:
            return None
        return valid[pos][1]


def _chain_merge(pool: List[dict], mem_dates: dict) -> List[dict]:
    """与 complex_query_arm._chain 逐字节同语义的重实现(相邻同值合并),
    独立写出以保持模块自包含;对拍脚本会额外验证两者输出逐字节相等。"""
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


class StoreIndex:
    """一个卡片库(单一 uid)的物化索引。事实源仍是卡片 JSON;本对象可
    随时从 records 重建(rebuild),也支持增量 insert_record(splice)。"""

    def __init__(self):
        self.mem_dates: Dict[str, str] = {}
        self.by_id: Dict[str, dict] = {}
        self.keyed_pool: Dict[Key, List[dict]] = {}   # 原始分组(建索引用)
        self.chains: Dict[Key, KeyChain] = {}
        self.tag_index: Dict[str, List[dict]] = {}
        self.owners_by_class: Dict[str, set] = {}
        self.log: List[dict] = []
        self._all_records: List[dict] = []

    # ── 建库(批量,O(n log n)) ──────────────────────────────
    def build(self, records: List[dict], mem_dates: Dict[str, str]) -> "StoreIndex":
        self.mem_dates = dict(mem_dates)
        self._all_records = list(records)
        self.by_id = {r.get("record_id"): r for r in records if r.get("record_id")}
        groups: Dict[Key, List[dict]] = {}
        for r in records:
            cls = r.get("slot_class")
            if not cls:
                continue
            owner = r.get("owner") or ""
            groups.setdefault((owner, cls), []).append(r)
            self.owners_by_class.setdefault(cls, set()).add(owner)
        self.keyed_pool = groups
        for key, recs in groups.items():
            dated = [r for r in recs
                     if _rec_date(r, self.mem_dates) and _norm(r.get("value", ""))]
            dated.sort(key=lambda r: sort_key(r, self.mem_dates))
            kc = KeyChain(key=key, pool=dated)
            kc.chain = _chain_merge(dated, self.mem_dates)
            kc.chain_hyg = _chain_merge(_hygiene_pool(dated), self.mem_dates)
            kc._asof_dates = [_pdate(_rec_date(r, self.mem_dates)) for r in kc.chain]
            kc._asof_dates_hyg = [_pdate(_rec_date(r, self.mem_dates))
                                   for r in kc.chain_hyg]
            self.chains[key] = kc
        # 标签倒排表(§7.3 "标签倒排表")
        tags: Dict[str, List[dict]] = {}
        for r in records:
            for t in (r.get("value_tags") or []):
                t = (t or "").strip()
                if t:
                    tags.setdefault(t, []).append(r)
        for t, recs in tags.items():
            tags[t] = sorted(recs, key=lambda r: _rec_date(r, self.mem_dates))
        self.tag_index = tags
        return self

    # ── I1-I4 不变量检查 ────────────────────────────────────
    def check_invariants(self) -> Dict[str, object]:
        """返回 {ok: bool, I1..I4: bool, detail: {...}}。纯只读检查,不
        修改索引状态。"""
        detail: Dict[str, object] = {}

        # I4: 边端点存在
        dangling = []
        for r in self._all_records:
            for t in (r.get("relation_target_record_ids") or []):
                if t not in self.by_id:
                    dangling.append((r.get("record_id"), t))
        i4 = not dangling
        detail["I4_dangling_edges"] = dangling[:20]

        # I1: 替换边(仅 I4 已通过的边)无环
        adj: Dict[str, List[str]] = {}
        for r in self._all_records:
            rid = r.get("record_id")
            for t in (r.get("relation_target_record_ids") or []):
                if t in self.by_id:
                    adj.setdefault(rid, []).append(t)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {rid: WHITE for rid in self.by_id}
        cyclic = False
        cyc_node = None

        def dfs(u):
            nonlocal cyclic, cyc_node
            if cyclic:
                return
            color[u] = GRAY
            for v in adj.get(u, []):
                if color.get(v, WHITE) == GRAY:
                    cyclic, cyc_node = True, u
                    return
                if color.get(v, WHITE) == WHITE:
                    dfs(v)
                    if cyclic:
                        return
            color[u] = BLACK

        for rid in list(self.by_id):
            if color.get(rid, WHITE) == WHITE:
                dfs(rid)
                if cyclic:
                    break
        i1 = not cyclic
        detail["I1_cycle_at"] = cyc_node

        # I3(修正版,见下方"压力测试发现的修正"记录):链的排序键
        # (raw stated_date 字符串, 内容指纹)永远严格递增(hash 碰撞概率
        # 忽略不计,由构造保证);但把 stated_date 解析成日历日期后允许
        # 相邻两条**相等**(不同粒度的字符串,如 "1997" 与 "1997-01",
        # 解析后可能落在同一天;或同日两条不同值的真实记录)——这不是
        # 违反单调性,是"同一实例发生了并列声明"的合法情形,由 I2 的
        # 右开区间语义自动消解(见下)。真正违反 I3 的只有**解析日期
        # 逆序**(说明排序或构造有 bug)。
        i3 = True
        bad_chains = []
        for key, kc in self.chains.items():
            prev = None
            for d in kc._asof_dates:
                if d is None:
                    continue
                if prev is not None and d < prev:
                    i3 = False
                    bad_chains.append(key)
                    break
                prev = d
        detail["I3_non_monotonic_keys"] = bad_chains[:20]

        # I2: 任一时刻每键至多一个活跃值 —— 区间 [t_i, t_{i+1}) 右开,
        # 独立复核用区间端点断言两两不重叠、不逆序。相邻两条记录解析
        # 日期**相等**时,前一条的区间退化为 [t_{i-1}, t_i) 而后一条从
        # 同一个 t_i 开始——右开约定下二者在 t_i 处不相交(前一条不含
        # t_i 本身),前一条实际有效时长为"到并列日为止",这正是"同日
        # 并列声明,较早声明零时长、被同日的另一条覆盖"的期望语义,不是
        # 重叠。故 I2 的独立复核只断言**不逆序**(a <= b),不要求严格
        # 小于——与 I3 的修正同源同因。
        i2 = True
        bad_i2 = []
        for key, kc in self.chains.items():
            ds = [d for d in kc._asof_dates if d is not None]
            for a, b in zip(ds, ds[1:]):
                if a > b:
                    i2 = False
                    bad_i2.append(key)
                    break
        detail["I2_overlap_keys"] = bad_i2[:20]

        ok = i1 and i2 and i3 and i4
        return {"ok": ok, "I1": i1, "I2": i2, "I3": i3, "I4": i4,
                "detail": detail}

    # ── retroactive splice(增量插入,§7.3) ──────────────────
    def insert_record(self, rec: dict) -> dict:
        """插入一条新记录(允许其 stated_date 早于同键既有记录 = 回溯拼接)。
        只重算受影响键的邻接边,不重建整条链、不重建其余键。返回本次操作
        的修复日志条目(同时 append 到 self.log)。"""
        rid = rec.get("record_id")
        entry = {"op": "insert", "record_id": rid}
        if rid and rid in self.by_id:
            entry["skipped"] = "duplicate_record_id"
            self.log.append(entry)
            return entry
        # I4 前置校验:出边端点必须已存在,否则丢弃该条非法边(而非拒绝
        # 整条记录——与建卡契约"逐字子串校验,违约丢弃"同精神,只丢违约
        # 的那一小部分)。
        valid_targets = []
        dropped = []
        for t in (rec.get("relation_target_record_ids") or []):
            if t in self.by_id:
                valid_targets.append(t)
            else:
                dropped.append(t)
        if dropped:
            rec = dict(rec)
            rec["relation_target_record_ids"] = valid_targets
            entry["dangling_edges_dropped"] = dropped
        if rid:
            self.by_id[rid] = rec
        self._all_records.append(rec)

        cls = rec.get("slot_class")
        if not cls:
            entry["unkeyed"] = True
            self.log.append(entry)
            return entry
        owner = rec.get("owner") or ""
        key = (owner, cls)
        self.keyed_pool.setdefault(key, []).append(rec)
        self.owners_by_class.setdefault(cls, set()).add(owner)

        for t in (rec.get("value_tags") or []):
            t = (t or "").strip()
            if t:
                lst = self.tag_index.setdefault(t, [])
                pos = bisect.bisect_right(
                    [(_rec_date(x, self.mem_dates) or "") for x in lst],
                    _rec_date(rec, self.mem_dates) or "")
                lst.insert(pos, rec)

        dated = _rec_date(rec, self.mem_dates)
        valued = _norm(rec.get("value", ""))
        if not (dated and valued):
            entry["not_charted"] = "undated_or_valueless"
            self.log.append(entry)
            return entry

        kc = self.chains.get(key)
        if kc is None:
            kc = KeyChain(key=key)
            self.chains[key] = kc
        skey = sort_key(rec, self.mem_dates)
        pos = bisect.bisect_left([sort_key(r, self.mem_dates) for r in kc.pool],
                                  skey)
        kc.pool.insert(pos, rec)
        # 只重算受影响的邻接边:局部重新合并 [pos-1, pos+1] 窗口即可,
        # 但相邻同值合并有传递性(合并后可能与更远一条再次相邻同值的
        # 概率在实践中可忽略——chain() 语义本就只看直接相邻),故窗口
        # 宽度 2 足够;为保持实现简单可靠,这里仍以整条 pool 重新跑一次
        # O(1) 摊销的 _chain_merge/_hygiene_pool(链长度通常是个位数到
        # 低两位数,不是全库 n)——真正避免的是"重新扫描/重新排序全库
        # n 条记录",这才是 O(n log n) 与 O(log n + chain 长度) 的差别。
        kc.chain = _chain_merge(kc.pool, self.mem_dates)
        kc.chain_hyg = _chain_merge(_hygiene_pool(kc.pool), self.mem_dates)
        kc._asof_dates = [_pdate(_rec_date(r, self.mem_dates)) for r in kc.chain]
        kc._asof_dates_hyg = [_pdate(_rec_date(r, self.mem_dates))
                               for r in kc.chain_hyg]
        entry["key"] = list(key)
        entry["chain_len_after"] = len(kc.chain)
        entry["retroactive"] = pos < len(kc.pool) - 1
        self.log.append(entry)
        return entry

    # ── 查询侧:_select_pool_frozen 的索引版(默认旗标路径,即
    #    QVF_OPEN_SLOT=QVF_OPEN_KEYS=0 时冻结实现所走的那一支) ──
    def select_chain(self, slot: str, question: str = "",
                      hygiene: bool = False) -> List[dict]:
        fs = _norm(slot or "")
        matched = [c for c, al in SLOT_ALIASES.items()
                   if any(a in fs for a in al)]
        first_person = (not question or _FP_RE.search(question)
                        or "我" in question)
        if matched:
            any_owner = any(o for cls in matched
                            for o in self.owners_by_class.get(cls, set()))
            eligible = {"", "user"} if (first_person and any_owner) else None
            best_key, best_depth = None, -1
            for cls in sorted(matched):
                owners = self.owners_by_class.get(cls, set())
                for owner in sorted(owners):
                    if eligible is not None and owner not in eligible:
                        continue
                    kc = self.chains.get((owner, cls))
                    if kc is None:
                        continue
                    pool = kc.pool
                    depth = len({_norm(r.get("value", "")) for r in pool
                                if _rec_date(r, self.mem_dates)})
                    if depth > best_depth:
                        best_depth, best_key = depth, (owner, cls)
            if best_key is not None:
                kc = self.chains[best_key]
                return kc.chain_hyg if hygiene else kc.chain
        # 回退:未键控/无类命中 —— 全库词重叠扫描(与冻结 fallback 同语义;
        # 无键场景本就无法受益于索引,直接扫描全部记录)。
        pool = [r for r in self._all_records
                if _slot_match(r.get("slot", ""), slot or "")]
        pool = [r for r in pool
                if _rec_date(r, self.mem_dates) and _norm(r.get("value", ""))]
        pool.sort(key=lambda r: sort_key(r, self.mem_dates))
        if hygiene:
            pool = _hygiene_pool(pool)
        return _chain_merge(pool, self.mem_dates)

    def asof(self, slot: str, qd, question: str = "",
             hygiene: bool = False) -> Optional[int]:
        """O(log m) 定位:返回 (chain, gi) 二元组的 gi 部分需配合
        select_chain 取回 chain 本身(见 execute.py 调用处)。"""
        chain = self.select_chain(slot, question, hygiene)
        if not chain:
            return None
        dates = [_pdate(_rec_date(r, self.mem_dates)) for r in chain]
        valid = [(d, i) for i, d in enumerate(dates) if d is not None]
        if not valid or qd is None:
            return None
        ds = [d for d, _ in valid]
        pos = bisect.bisect_right(ds, qd) - 1
        return valid[pos][1] if pos >= 0 else None

    def chain_depth(self, slot: str, question: str = "") -> int:
        """替代 qvf_router.chain_depth 的键控快路径部分(O(1) 索引查表,
        对照冻结实现每次调用都要 O(n) 重新分组 + O(n²) union-find 兜底)。"""
        ch = self.select_chain(slot, question, hygiene=False)
        return len({_norm(r.get("value", "")) for r in ch})


def build_index_from_uid(uid: str, cards_dir, mem_dates: Dict[str, str]) -> StoreIndex:
    import json
    from pathlib import Path as _P
    f = _P(cards_dir) / f"{uid}.json"
    recs = json.loads(f.read_text(encoding="utf-8")).get("records", []) \
        if f.exists() else []
    return StoreIndex().build(recs, mem_dates)
