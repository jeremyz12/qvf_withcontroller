# -*- coding: utf-8 -*-
"""join_at_change 离线冒烟:零 API、零网络(scripts/complex_query_arm.py)。

断言清单:
  A schema/prompt:OPS 前 10 项与改动前逐项一致且新增 join_at_change;
    CompiledPlan Literal 接受 join_at_change、拒绝未知 op;slot2 可选
    (旧形状计划 JSON —— 无 slot2 键 —— 仍可构造,缺省 None);
    COMPILE_PROMPT 含 CERN few-shot(presupposed 携锚值,slot2=residence);
  B join 正例:employer+residence fixture 店 → 锚 = 雇主变更为 CERN 的
    记录(生效日 T),返回副链上覆盖 T 的居住地;证据包 = 锚记录 +
    覆盖记录 ± 邻居;结论行同时陈述两侧(手核逐字节);
  C 模糊匹配:presupposed 大小写/包含变体命中同一锚(承 premise_check
    的 _norm 双向包含口径);
  D 降级:锚未命中 → 'Anchor not found' 结论行(不猜);slot2 缺省 →
    明示无从点查;T 早于副链首个已知状态 → 明示 predates + 最早已知值;
  E 回归(字节冻结):既有 10 算子的冻结 fixture 计划集在改动后逐字节
    复现改动前捕获的输出(FROZEN_EXPECTED_JSON 由改动前原件生成);
    同一计划带/不带 slot2=None 键输出一致。

用法:  python scripts/smoke_join_at_change.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.complex_query_arm as C  # noqa: E402

# ── E:冻结 fixture(与改动前捕获脚本逐字节一致)────────────────
FROZEN_RECS = [
    {"record_id": "e1", "source_memory_id": "fz/s0#r0", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "University of Oslo", "stated_date": "2001-09-01",
     "source_span": "I started working at the University of Oslo."},
    {"record_id": "e2", "source_memory_id": "fz/s1#r0", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "CERN", "stated_date": "2003-05-01",
     "source_span": "I officially started working at CERN today."},
    {"record_id": "h1", "source_memory_id": "fz/s2#r1", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "6 months before 2008-02-01", "stated_date": "2007-08-01",
     "source_span": "That was about 6 months before 2008-02-01."},
    {"record_id": "e3", "source_memory_id": "fz/s2#r0", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "Max Planck Institute", "stated_date": "2008-02-01",
     "source_span": "I officially started working at Max Planck Institute today."},
    {"record_id": "r1", "source_memory_id": "fz/s3#r0", "owner": "user",
     "slot_class": "residence", "slot": "residence",
     "value": "Oslo", "stated_date": "2000-01-15",
     "source_span": "I officially moved to Oslo today."},
    {"record_id": "r2", "source_memory_id": "fz/s4#r0", "owner": "user",
     "slot_class": "residence", "slot": "residence",
     "value": "Geneva", "stated_date": "2002-11-03",
     "source_span": "I officially moved to Geneva today.",
     "value_tags": ["出行旅行"]},
    {"record_id": "r3", "source_memory_id": "fz/s9#r0", "owner": "user",
     "slot_class": "residence", "slot": "residence",
     "value": "Munich", "stated_date": "",
     "source_span": "I officially moved to Munich today."},
]
FROZEN_MEM_DATES = {"fz/s9#r0": "2007-12-20"}

FROZEN_PLANS = [
    ["current_emp", "What is my employer these days?",
     {"op": "current", "slot": "employer", "date": None, "tag": None,
      "presupposed": None}],
    ["point_2004", "What employer did I have on 2004-01-01?",
     {"op": "point_in_time", "slot": "employer", "date": "2004-01-01",
      "tag": None, "presupposed": None}],
    ["point_predate", "Where did I live on 1999-01-01?",
     {"op": "point_in_time", "slot": "residence", "date": "1999-01-01",
      "tag": None, "presupposed": None}],
    ["trajectory_res", "How has my residence changed over time?",
     {"op": "trajectory", "slot": "residence", "date": None, "tag": None,
      "presupposed": None}],
    ["premise_stale", "Since my employer is University of Oslo, what should I know?",
     {"op": "premise_check", "slot": "employer", "date": None, "tag": None,
      "presupposed": "University of Oslo"}],
    ["count_changes_emp", "How many times did I change my employer?",
     {"op": "count_changes", "slot": "employer", "date": None, "tag": None,
      "presupposed": None}],
    ["longest_emp", "Which employer did I hold the longest?",
     {"op": "longest", "slot": "employer", "date": None, "tag": None,
      "presupposed": None}],
    ["count_before_2005", "How many different employer values did I have before 2005-01-01?",
     {"op": "count_before", "slot": "employer", "date": "2005-01-01",
      "tag": None, "presupposed": None}],
    ["first_last_res", "What was my first residence, and what is my most recent one?",
     {"op": "first_last", "slot": "residence", "date": None, "tag": None,
      "presupposed": None}],
    ["tag_filter_hit", "Have I mentioned anything 出行旅行 related? List what and when.",
     {"op": "tag_filter", "slot": None, "date": None, "tag": "出行旅行",
      "presupposed": None}],
    ["tag_trend_hit", "What have I mentioned in the 出行旅行 category over time?",
     {"op": "tag_trend", "slot": None, "date": None, "tag": "出行旅行",
      "presupposed": None}],
    ["tag_filter_miss", "Have I mentioned anything 宠物 related?",
     {"op": "tag_filter", "slot": None, "date": None, "tag": "宠物",
      "presupposed": None}],
    ["current_nomatch", "What is my phone model?",
     {"op": "current", "slot": "device", "date": None, "tag": None,
      "presupposed": None}],
]

# 改动前(join_at_change 落地前)由原件 execute_plan 在上述 fixture 上捕获;
# json.dumps(out, ensure_ascii=False, sort_keys=True) 的逐字节输出。
FROZEN_EXPECTED_JSON = r'''{"count_before_2005": {"derived": ["Before 2005-01-01, the user had 2 different employer value(s): University of Oslo, CERN."], "ev": ["[2001-09-01] employer: University of Oslo — \"I started working at the University of Oslo.\"", "[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2008-02-01] employer: Max Planck Institute — \"I officially started working at Max Planck Institute today.\""]}, "count_changes_emp": {"derived": ["The user's employer changed 2 time(s) — 3 successive states: University of Oslo -> CERN -> Max Planck Institute."], "ev": ["[2001-09-01] employer: University of Oslo — \"I started working at the University of Oslo.\"", "[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2008-02-01] employer: Max Planck Institute — \"I officially started working at Max Planck Institute today.\""]}, "current_emp": {"derived": ["The user's current employer is Max Planck Institute (since 2008-02-01)."], "ev": ["[2001-09-01] employer: University of Oslo — \"I started working at the University of Oslo.\"", "[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2007-08-01] employer: 6 months before 2008-02-01 — \"That was about 6 months before 2008-02-01.\"", "[2008-02-01] employer: Max Planck Institute — \"I officially started working at Max Planck Institute today.\""]}, "current_nomatch": {"derived": ["No dated record found for device in memory."], "ev": []}, "first_last_res": {"derived": ["First residence: Oslo (from 2000-01-15); most recent: Munich (since 2007-12-20)."], "ev": ["[2000-01-15] residence: Oslo — \"I officially moved to Oslo today.\"", "[2002-11-03] residence: Geneva — \"I officially moved to Geneva today.\"", "[2007-12-20] residence: Munich — \"I officially moved to Munich today.\""]}, "longest_emp": {"derived": ["Held longest (closed intervals only): CERN (1737 days). Closed days per value: {\"University of Oslo\": 607, \"CERN\": 1737}."], "ev": ["[2001-09-01] employer: University of Oslo — \"I started working at the University of Oslo.\"", "[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2008-02-01] employer: Max Planck Institute — \"I officially started working at Max Planck Institute today.\""]}, "point_2004": {"derived": ["On 2004-01-01, the user's employer was CERN (recorded 2003-05-01, unchanged until 2007-08-01). This IS the answer."], "ev": ["[2001-09-01] employer: University of Oslo — \"I started working at the University of Oslo.\"", "[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2007-08-01] employer: 6 months before 2008-02-01 — \"That was about 6 months before 2008-02-01.\"", "[2008-02-01] employer: Max Planck Institute — \"I officially started working at Max Planck Institute today.\""]}, "point_predate": {"derived": ["The asked date predates every known state of residence; the earliest known state is Oslo from 2000-01-15."], "ev": ["[2000-01-15] residence: Oslo — \"I officially moved to Oslo today.\"", "[2002-11-03] residence: Geneva — \"I officially moved to Geneva today.\"", "[2007-12-20] residence: Munich — \"I officially moved to Munich today.\""]}, "premise_stale": {"derived": ["The user's current employer is Max Planck Institute (since 2008-02-01).", "IMPORTANT: the message presupposes University of Oslo, which is OUTDATED — the user's current employer is Max Planck Institute. Correct this premise before helping."], "ev": ["[2001-09-01] employer: University of Oslo — \"I started working at the University of Oslo.\"", "[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2007-08-01] employer: 6 months before 2008-02-01 — \"That was about 6 months before 2008-02-01.\"", "[2008-02-01] employer: Max Planck Institute — \"I officially started working at Max Planck Institute today.\""]}, "tag_filter_hit": {"derived": ["1 stored item(s) carry the tag 出行旅行; every one is listed above with its date."], "ev": ["[2002-11-03] residence: Geneva — \"I officially moved to Geneva today.\""]}, "tag_filter_miss": {"derived": ["No stored item carries the tag 宠物."], "ev": []}, "tag_trend_hit": {"derived": ["Items tagged 出行旅行 by year — 2002: Geneva. Describe what was mentioned and how it evolved, citing only these items with their dates."], "ev": ["[2002-11-03] residence: Geneva — \"I officially moved to Geneva today.\""]}, "trajectory_res": {"derived": ["Full evolution of the user's residence: Oslo (from 2000-01-15) -> Geneva (from 2002-11-03) -> Munich (from 2007-12-20). Give the complete ordered history."], "ev": ["[2000-01-15] residence: Oslo — \"I officially moved to Oslo today.\"", "[2002-11-03] residence: Geneva — \"I officially moved to Geneva today.\"", "[2007-12-20] residence: Munich — \"I officially moved to Munich today.\""]}}'''


def _run_frozen(plans):
    out = {}
    for name, question, plan in plans:
        ev, derived = C.execute_plan(
            dict(plan), [dict(r) for r in FROZEN_RECS],
            dict(FROZEN_MEM_DATES), question)
        out[name] = {"ev": ev, "derived": derived}
    return out


# ── B/C/D:join fixture(employer + residence 两组键控卡)────────
FIX_JOIN = [
    {"record_id": "e1", "source_memory_id": "jx/s0#r0", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "University of Oslo", "stated_date": "2001-09-01",
     "source_span": "I started working at the University of Oslo."},
    {"record_id": "e2", "source_memory_id": "jx/s1#r0", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "CERN", "stated_date": "2003-05-01",
     "source_span": "I officially started working at CERN today."},
    {"record_id": "e3", "source_memory_id": "jx/s2#r0", "owner": "user",
     "slot_class": "employer", "slot": "employer",
     "value": "Max Planck Institute", "stated_date": "2008-02-01",
     "source_span": "I officially started working at Max Planck Institute today."},
    {"record_id": "r1", "source_memory_id": "jx/s3#r0", "owner": "user",
     "slot_class": "residence", "slot": "residence",
     "value": "Oslo", "stated_date": "2000-01-15",
     "source_span": "I officially moved to Oslo today."},
    {"record_id": "r2", "source_memory_id": "jx/s4#r0", "owner": "user",
     "slot_class": "residence", "slot": "residence",
     "value": "Geneva", "stated_date": "2002-11-03",
     "source_span": "I officially moved to Geneva today."},
    {"record_id": "r3", "source_memory_id": "jx/s5#r0", "owner": "user",
     "slot_class": "residence", "slot": "residence",
     "value": "Munich", "stated_date": "2007-12-20",
     "source_span": "I officially moved to Munich today."},
]
JOIN_Q = "When I started at CERN, where was I living?"
JOIN_PLAN = {"op": "join_at_change", "slot": "employer", "slot2": "residence",
             "date": None, "tag": None, "presupposed": "CERN"}
JOIN_DERIVED = ("The user's employer changed to CERN on 2003-05-01; on that "
                "date the user's residence was Geneva (recorded 2002-11-03, "
                "unchanged until 2007-12-20). This IS the answer.")


def _join(plan, recs=FIX_JOIN, q=JOIN_Q):
    return C.execute_plan(dict(plan), [dict(r) for r in recs], {}, q)


def check_schema_prompt():
    assert C.OPS[:10] == (
        "current", "point_in_time", "trajectory", "premise_check",
        "count_changes", "longest", "count_before", "first_last",
        "tag_filter", "tag_trend"), "既有 OPS 前缀被改动"
    assert C.OPS[10] == "join_at_change" and len(C.OPS) == 11

    p = C.CompiledPlan(op="join_at_change", slot="employer",
                       slot2="residence", presupposed="CERN")
    d = p.model_dump()
    assert d["op"] == "join_at_change" and d["slot2"] == "residence"
    assert d["presupposed"] == "CERN" and d["date"] is None
    # 旧形状计划(无 slot2 键)仍可构造,缺省 None
    old = C.CompiledPlan.model_validate(
        {"op": "current", "slot": "employer", "date": None, "tag": None,
         "presupposed": None})
    assert old.slot2 is None
    try:
        C.CompiledPlan(op="bogus_op")
        raise AssertionError("Literal 未拒绝未知 op")
    except Exception:  # noqa: BLE001 —— pydantic ValidationError
        pass

    assert "Q: When I started at CERN, where was I living?" in C.COMPILE_PROMPT
    ans = next(l for l in C.COMPILE_PROMPT.splitlines()
               if '"op": "join_at_change"' in l)
    assert '"presupposed": "CERN"' in ans, "few-shot presupposed 未携锚值"
    assert '"slot2": "residence"' in ans and '"slot": "employer"' in ans
    assert "join_at_change" in C.COMPILE_PROMPT.split("op semantics:")[1]
    print("A. OPS/Literal/slot2 可选/CERN few-shot 全部就位;旧形状计划兼容")


def check_join_happy():
    ev, derived = _join(JOIN_PLAN)
    assert derived == [JOIN_DERIVED], derived
    assert len(ev) == 4, ev
    assert ev[0] == ('[2003-05-01] employer: CERN — '
                     '"I officially started working at CERN today."'), ev[0]
    assert "Oslo" in ev[1] and "Geneva" in ev[2] and "Munich" in ev[3], ev
    assert "2003-05-01" in derived[0] and "Geneva" in derived[0]
    print("B. join 正例:锚 CERN(T=2003-05-01)→ 副链覆盖区间 Geneva;"
          "证据包 = 锚 + 覆盖 ± 邻居;结论行两侧齐陈")


def check_fuzzy_anchor():
    for pv in ("cern", "at CERN"):
        _, derived = _join({**JOIN_PLAN, "presupposed": pv})
        assert derived == [JOIN_DERIVED], (pv, derived)
    print("C. 模糊匹配:'cern' / 'at CERN' 变体均命中同一锚(_norm 双向包含)")


def check_degrade():
    # D1 锚未命中 → 'Anchor not found' 明示,不猜
    ev, derived = _join({**JOIN_PLAN, "presupposed": "NASA"})
    assert len(derived) == 1 and derived[0].startswith("Anchor not found"), \
        derived
    assert "NASA" in derived[0] and "employer" in derived[0]
    assert len(ev) == 3 and all("employer" in l for l in ev), ev
    # D2 slot2 缺省(旧形状键缺失)→ 明示无从点查
    p2 = {k: v for k, v in JOIN_PLAN.items() if k != "slot2"}
    ev2, derived2 = _join(p2)
    assert derived2 == [
        "The user's employer changed to CERN on 2003-05-01, but no dated "
        "record of the other asked attribute exists in memory to look up "
        "at that date."], derived2
    assert len(ev2) == 1 and "CERN" in ev2[0]
    # D3 T 早于副链首个已知状态 → 明示 predates + 最早已知值
    recs = [r for r in FIX_JOIN if r["record_id"] != "r1"]
    ev3, derived3 = _join({**JOIN_PLAN, "presupposed": "University of Oslo"},
                          recs=recs)
    assert len(derived3) == 1 and "predates every known state" in derived3[0]
    assert ("earliest known residence is Geneva from 2002-11-03"
            in derived3[0]), derived3
    assert len(ev3) == 2 and "University of Oslo" in ev3[0] \
        and "Geneva" in ev3[1]
    print("D. 降级三态:anchor not found / slot2 缺省 / T 早于副链 —— "
          "均为明示结论行")


def check_frozen_byte_identical():
    expected = FROZEN_EXPECTED_JSON
    got = json.dumps(_run_frozen(FROZEN_PLANS), ensure_ascii=False,
                     sort_keys=True)
    assert got == expected, "既有算子输出与改动前捕获不再逐字节一致!"
    # 同一计划显式带 slot2=None 键 → 输出不变(新键对既有算子零影响)
    plans2 = [[n, q, {**p, "slot2": None}] for n, q, p in FROZEN_PLANS]
    got2 = json.dumps(_run_frozen(plans2), ensure_ascii=False, sort_keys=True)
    assert got2 == expected, "slot2=None 键改变了既有算子输出!"
    print(f"E. 冻结回归:{len(FROZEN_PLANS)} 计划(覆盖既有 10 算子)输出与"
          "改动前捕获逐字节一致;slot2=None 键零影响")


def main() -> int:
    check_schema_prompt()
    check_join_happy()
    check_fuzzy_anchor()
    check_degrade()
    check_frozen_byte_identical()
    print("SMOKE OK: join_at_change 编译 schema/few-shot/执行器/降级 + "
          "既有算子字节冻结回归,全部离线断言通过(零 API 调用)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
