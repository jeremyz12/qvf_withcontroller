# -*- coding: utf-8 -*-
"""
scripts/boundary_run.py

边界对决:第①步(零判官、纯代码机械对照)。

对 data/wsc_boundary.jsonl 的每一题,直接构造 plan={op,slot,date}(op/slot/date
均已由 boundary_gen.py 写入题行,跳过 LLM 编译步——本实验测的是 EXECUTE 语义,
不是 COMPILE 准确率),用冻结的 scripts.complex_query_arm.execute_plan 计算出
系统的 derived 结论行,与 scripts.boundary_gold.gold() 算出的独立金答案逐题
比对。

纪律:complex_query_arm.py 只读只调用(import + call execute_plan),零编辑;
本文件走 scripts/boundary_* 命名,新文件。

卡片来源三类(按 category 分派):
  A. switch_day / right_endpoint / chain_tail_open / year_only_mixed_with_full_date
     真实 uid,卡片直接读 results/wt_cards_v43(缺则回落 results/wt_cards)——
     这批卡片由与本次边界实验完全独立的既有建卡流水线产出,是"系统真实会
     看到什么"的诚实输入。
  B. same_value_multi_segment:合成 uid(BOUNDARY-SYN-MS-*),真实卡片库中不
     存在——按 params.chain(题行自带的 value/date/state_span 三元组,
     boundary_gen.py 生成)直接构造卡片记录(零 LLM、零字符串猜测,一段
     一条记录,字段值=chain 里的原值),不经写入时抽取的 LLM 步骤,因为
     这些"记忆原文"本身就是本实验合成的确定性模板句,抽取应得的结果无
     歧义。
  C. same_day_multi_value:真实 uid 的既有卡片("原始记录") + 一条注入记录
     (value=alt_value, stated_date=d,直接构造,不经 LLM),注入记录追加在
     该 uid 卡片记录列表的末尾(晚于原始记录的列表位置)—— 与
     boundary_gold 的 GEN-1 tie-break 选择("注入记录在输入顺序中排在原记
     录之后")同一约定,让"同日多值时谁在系统的稳定排序里排在后面"这个
     变量在两侧保持一致,不引入额外的自由裁量。每题独立构造一份 recs 列
     表(内存里的列表拷贝,不写回磁盘、不跨题共享可变对象),故同一 uid
     被其它类别复用时不会被污染。

用法:
  python scripts/boundary_run.py --out results/boundary_duel_20260816.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# v4.2 旗标组合(见 study_logs/VERSION_LEDGER.md "开放槽位修复" 08-16 条目:
# 救援式 OPEN_SLOT/OPEN_KEYS 已过预注册裁决,FAIL_CLOSED 亦已裁决"降级不
# 作恶"成立;三者仅在冻结路径选池为空时才生效,本次边界题绝大多数走单
# 属性键控命中的非空池,故这组旗标对多数题应为惰性开关,开启是为了对齐
# "系统当前推荐配置"而非制造额外变量——旗标状态逐题记录在输出行里,供
# 复核这条假设)。
os.environ.setdefault("QVF_OPEN_SLOT", "1")
os.environ.setdefault("QVF_OPEN_KEYS", "1")
os.environ.setdefault("QVF_FAIL_CLOSED", "1")
os.environ.setdefault("QVF_ALGEBRA", "0")  # 平面路径,非代数臂

from scripts.complex_query_arm import execute_plan  # noqa: E402
from scripts.complex_query_arm import _mem_dates as _cqa_mem_dates  # noqa: E402
from scripts.boundary_gold import (BEFORE_EARLIEST, EMPTY_CHAIN,  # noqa: E402
                                   gold)

CARDS_V43 = ROOT / "results" / "wt_cards_v43"
CARDS_V42 = ROOT / "results" / "wt_cards"
BOUNDARY_IN = ROOT / "data" / "wsc_boundary.jsonl"

_DATA_CACHE: Dict[str, dict] = {}
_CARD_CACHE: Dict[str, Optional[dict]] = {}


def _load_data_file(path: str) -> dict:
    if path not in _DATA_CACHE:
        by_uid = {}
        for e in json.loads((ROOT / path).read_text(encoding="utf-8")):
            by_uid[e["uid"]] = e
        _DATA_CACHE[path] = by_uid
    return _DATA_CACHE[path]


def _load_card(uid: str) -> Tuple[Optional[dict], str]:
    """返回 (card_dict_or_None, which_dir)。"""
    key = uid
    if key in _CARD_CACHE:
        return _CARD_CACHE[key], _CARD_CACHE.get(key + "__src", "")
    for d, tag in ((CARDS_V43, "v43"), (CARDS_V42, "wt_cards")):
        p = d / f"{uid}.json"
        if p.exists():
            c = json.loads(p.read_text(encoding="utf-8"))
            _CARD_CACHE[key] = c
            _CARD_CACHE[key + "__src"] = tag
            return c, tag
    _CARD_CACHE[key] = None
    _CARD_CACHE[key + "__src"] = ""
    return None, ""


# ── 卡片构造:三类分派 ──────────────────────────────────────────
def _build_recs_real(row: dict) -> Tuple[Optional[List[dict]], dict, str]:
    """A/C 类(真实 uid):从既有卡片库读 records,mem_dates 从源 data 文件
    的 sessions 现算(与 complex_query_arm._mem_dates 同函数)。"""
    uid = row["uid"]
    card, card_src = _load_card(uid)
    if card is None:
        return None, {}, ""
    entry = _load_data_file(row["source"]).get(uid, {})
    mem_dates = _cqa_mem_dates(entry)
    recs = list(card.get("records", []))  # 拷贝,不改原卡片对象
    return recs, mem_dates, card_src


_MS_CHAIN_CACHE: Dict[str, list] = {}


def _build_recs_synthetic_ms(row: dict) -> Tuple[List[dict], dict, str]:
    """B 类(same_value_multi_segment,合成 uid):按 params.chain 逐段构造
    一条记录,不经 LLM。三道题(bms_long/bms_count/bms_return)共享同一条
    合成链;boundary_gen.py 只在 bms_long/bms_count 两行的 params 里内嵌了
    完整 chain,bms_return 行的 params 只有 {"d": ...}(见该函数注释"same
    synthetic chain as the longest-duration twin question above")——按 uid
    缓存首次见到的 chain,供同 uid 的后续行复用,不是另一处口径判断。"""
    uid = row["uid"]
    slot = row["slot"]
    chain = row["params"].get("chain")
    if chain is not None:
        _MS_CHAIN_CACHE[uid] = chain
    else:
        chain = _MS_CHAIN_CACHE[uid]
    recs = []
    for i, seg in enumerate(chain):
        span = str(seg.get("state_span", ""))
        recs.append({
            "record_id": f"r{i+1}",
            "source_memory_id": f"{uid}/s{i}#r0",
            "source_span": span,
            "entity": "user",
            "slot": slot,
            "value": seg["value"],
            "claim": span,
            "stated_date": str(seg["date"]),
            "owner": "user",
            "slot_class": slot,
        })
    return recs, {}, "synthetic-direct"


_SAMEDAY_D_CACHE: Dict[str, dict] = {}


def _build_recs_sameday(row: dict) -> Tuple[Optional[List[dict]], dict, str]:
    """C 类(same_day_multi_value):真实卡片 + 追加一条注入记录(同日,列表
    位置晚于全部原始记录,呼应 GEN-1 的 tie-break 读法)。pit 题行的 params
    带 d/injected_value;其 count_changes 孪生题行(同 uid,紧随其后生成)
    只带 i/injected_value,不重复带 d —— 按 uid 缓存 pit 行的 d 供孪生行
    复用(与 boundary_gen.py 单次循环内先 append pit 后 append count 的生
    成顺序一致,非另一处口径判断)。"""
    recs, mem_dates, card_src = _build_recs_real(row)
    if recs is None:
        return None, {}, ""
    p = dict(row["params"])
    if "d" in p:
        _SAMEDAY_D_CACHE[row["uid"]] = p
    else:
        cached = _SAMEDAY_D_CACHE[row["uid"]]
        p["d"] = cached["d"]
        p.setdefault("original_value", cached.get("original_value"))
    # owner 字段必须跟随该 uid 卡片里同 slot_class 记录的实际 owner 取值
    # (v43 卡片经验上常见 owner==''而非'user'),否则注入记录会被
    # _select_pool_frozen 的 (owner, slot_class) 键控分组隔到另一个组,
    # 永远进不了真实记录所在的组——这是测试夹具的构造缺陷,不是系统语义
    # 分歧,必须按真实卡片的 owner 取值注入,不能硬编码。
    same_class = [r for r in recs if r.get("slot_class") == row["slot"]]
    owner = same_class[0].get("owner", "") if same_class else "user"
    injected = {
        "record_id": "r_injected",
        "source_memory_id": f"{row['uid']}/SYN_SAMEDAY",
        "source_span": f"(synthetic tie) also reported {p['injected_value']} "
                        f"on {p['d']}",
        "entity": "user",
        "slot": row["slot"],
        "value": p["injected_value"],
        "claim": f"synthetic same-day tie injection at {p['d']}",
        "stated_date": p["d"],
        "owner": owner,
        "slot_class": row["slot"],
    }
    recs = recs + [injected]  # 追加在末尾 = 列表顺序晚于全部原始记录
    return recs, mem_dates, card_src + "+injected"


def build_recs(row: dict) -> Tuple[Optional[List[dict]], dict, str]:
    cat = row["category"]
    if cat == "same_value_multi_segment":
        return _build_recs_synthetic_ms(row)
    if cat == "same_day_multi_value":
        return _build_recs_sameday(row)
    return _build_recs_real(row)


# ── plan 构造(op/slot/date 均已在题行里,不经 LLM 编译) ────────
def build_plan(row: dict) -> dict:
    op = row["qtype"]
    plan = {"op": op, "slot": row["slot"], "slot2": None, "date": None,
            "tag": None, "presupposed": None, "anchor_index": None}
    if op == "point_in_time":
        plan["date"] = row["params"]["d"]
    return plan


# ── derived 结论行 → 系统计算值(纯正则,模板取自 complex_query_arm.py
#    execute_plan 的 f-string 原文,逐字节对应,不做任何语义裁决)────────
_RE_PIT_ANSWER = re.compile(r"the user's [^ ]+.*? was (.+?) \(recorded ")
_RE_PIT_BEFORE = re.compile(r"^The asked date predates every known state")
_RE_PIT_NOCHAIN = re.compile(r"^No dated record found")
_RE_CC = re.compile(r"changed (\d+) time\(s\)")
_RE_LONGEST_WIN = re.compile(
    r"^Held longest \(closed intervals only\): (.+?) \((\d+) days\)\.")
_RE_LONGEST_UNBOUND = re.compile(
    r"^Only one dated state of .+? is known \((.+?) since")


def extract_system_answer(op: str, derived: List[str]):
    text = derived[0] if derived else ""
    if not derived:
        return ("NO_DERIVED", text)
    if op == "point_in_time":
        if _RE_PIT_NOCHAIN.search(text):
            return (EMPTY_CHAIN, text)
        if _RE_PIT_BEFORE.search(text):
            return (BEFORE_EARLIEST, text)
        m = _RE_PIT_ANSWER.search(text)
        if m:
            return (m.group(1), text)
        return ("UNPARSED", text)
    if op == "count_changes":
        m = _RE_CC.search(text)
        if m:
            return (int(m.group(1)), text)
        return ("UNPARSED", text)
    if op == "longest":
        m = _RE_LONGEST_WIN.search(text)
        if m:
            return ((m.group(1), int(m.group(2))), text)
        m2 = _RE_LONGEST_UNBOUND.search(text)
        if m2:
            return ((m2.group(1), "UNBOUNDED"), text)
        return ("UNPARSED", text)
    return ("UNKNOWN_OP", text)


def _norm_val(v: str) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().casefold()


def values_agree(op: str, sys_ans, gold_ans) -> bool:
    if op == "count_changes":
        return sys_ans == gold_ans
    if op == "longest":
        if not (isinstance(sys_ans, tuple) and isinstance(gold_ans, tuple)):
            return sys_ans == gold_ans
        v_ok = _norm_val(sys_ans[0]) == _norm_val(gold_ans[0])
        d_ok = sys_ans[1] == gold_ans[1]
        return v_ok and d_ok
    # point_in_time
    if sys_ans in (EMPTY_CHAIN, BEFORE_EARLIEST) or gold_ans in (
            EMPTY_CHAIN, BEFORE_EARLIEST):
        return sys_ans == gold_ans
    return _norm_val(sys_ans) == _norm_val(gold_ans)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/boundary_duel_20260816.jsonl")
    ap.add_argument("--in", dest="inp", default=str(BOUNDARY_IN))
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.inp, encoding="utf-8") if l.strip()]
    out_rows = []
    n_missing_cards = 0
    for row in rows:
        recs, mem_dates, card_src = build_recs(row)
        plan = build_plan(row)
        if recs is None:
            out_rows.append({**{k: row[k] for k in
                                ("qid", "uid", "category", "qtype", "slot")},
                             "gold": row["gold"], "sys_answer": "MISSING_CARD",
                             "agree": False, "card_src": "",
                             "derived_text": "", "plan": plan})
            n_missing_cards += 1
            continue
        ev, derived = execute_plan(plan, recs, mem_dates, row["question"])
        sys_ans, text = extract_system_answer(row["qtype"], derived)
        gold_ans = row["gold"]
        if isinstance(gold_ans, list):  # json 往返 tuple->list,还原比较
            gold_ans = tuple(gold_ans)
        agree = values_agree(row["qtype"], sys_ans, gold_ans)
        out_rows.append({
            "qid": row["qid"], "uid": row["uid"], "category": row["category"],
            "qtype": row["qtype"], "slot": row["slot"],
            "question": row["question"],
            "gold": row["gold"], "sys_answer": sys_ans, "agree": agree,
            "card_src": card_src, "derived_text": text,
            "n_evidence": len(ev), "plan": plan,
            "flags": {"QVF_OPEN_SLOT": os.environ.get("QVF_OPEN_SLOT"),
                     "QVF_OPEN_KEYS": os.environ.get("QVF_OPEN_KEYS"),
                     "QVF_FAIL_CLOSED": os.environ.get("QVF_FAIL_CLOSED")},
        })

    outp = ROOT / a.out
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    n = len(out_rows)
    n_agree = sum(1 for r in out_rows if r["agree"])
    by_cat: Dict[str, List[int]] = {}
    for r in out_rows:
        b = by_cat.setdefault(r["category"], [0, 0])
        b[0] += 1
        b[1] += int(r["agree"])
    print(f"TOTAL: {n_agree}/{n} = {n_agree/n*100:.1f}% agree "
          f"(missing_card={n_missing_cards})")
    for c, (tot, ok) in sorted(by_cat.items()):
        print(f"  {c}: {ok}/{tot} = {ok/tot*100:.1f}%")
    print(f"-> {outp}")


if __name__ == "__main__":
    main()
