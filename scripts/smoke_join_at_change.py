# -*- coding: utf-8 -*-
"""join_at_change 离线冒烟:零 API、零网络(scripts/complex_query_arm.py)。

断言清单:
  A schema/prompt:OPS 前 10 项与改动前逐项一致且新增 join_at_change;
    CompiledPlan Literal 接受 join_at_change、拒绝未知 op;slot2 与
    anchor_index 均可选(旧形状计划 JSON —— 无该键 —— 仍可构造,缺省
    None);COMPILE_PROMPT 含 CERN few-shot(presupposed 携锚值,
    slot2=residence)与序数 few-shot(anchor_index=2,presupposed=null);
  B join 正例:employer+residence fixture 店 → 锚 = 雇主变更为 CERN 的
    记录(生效日 T),返回副链上覆盖 T 的居住地;证据包 = 锚记录 +
    覆盖记录 ± 邻居;结论行同时陈述两侧(手核逐字节);
  C 模糊匹配:presupposed 大小写/包含变体命中同一锚(承 premise_check
    的 _norm 双向包含口径);
  D 降级:锚未命中 → 'Anchor not found' 结论行(不猜);slot2 缺省 →
    明示无从点查;T 早于副链首个已知状态 → 明示 predates + 最早已知值;
  E 回归(字节冻结):既有 10 算子的冻结 fixture 计划集 + join fixture
    计划(值锚)在改动后逐字节复现改动前捕获的输出
    (FROZEN_EXPECTED_JSON / FROZEN_JOIN_EXPECTED_JSON 均由改动前原件
    生成);同一计划带/不带 slot2=None / anchor_index=None 键输出一致;
  F 序数锚正例:anchor_index=2 → 锚组有序带日期链第 2 元 = CERN,副链
    覆盖区间 Geneva;结论行 = 序数映射行 + 与值锚逐字节相同的 join
    结论行;证据包与值锚逐字节一致;
  G 序数越界:anchor_index=9 / 0 → 'Ordinal anchor out of range' 明示
    结论行(不猜),证据包 = 锚组全链;
  H 生成器隐式孪生(gen_wikistate_complex.gen_s6):合成双链条目上每道
    显式题配一道 s6_cross_slot_implicit 孪生(同转移 i 同 gold,qid
    _s6ia{i}/_s6ib{i},问句用序数短语不含锚值 needle,basis 写明序数
    映射);锚值在链内重复时显式与孪生同跳。

用法:  python scripts/smoke_join_at_change.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.complex_query_arm as C  # noqa: E402
import scripts.gen_wikistate_complex as G  # noqa: E402

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

# F/G:序数锚计划(anchor_index=2 → 锚组有序带日期链第 2 元 = CERN)
ORD_Q = "When I started at my second employer, where was I living?"
ORD_PLAN = {"op": "join_at_change", "slot": "employer", "slot2": "residence",
            "date": None, "tag": None, "presupposed": None, "anchor_index": 2}
ORD_MAPPING = ("Ordinal anchor resolved: the user's 2nd employer (1-based "
               "over the dated history) is CERN.")

# E:join fixture 计划(值锚)在序数锚落地前由原件 execute_plan 捕获;
# json.dumps(out, ensure_ascii=False, sort_keys=True) 的逐字节输出。
FROZEN_JOIN_EXPECTED_JSON = r'''{"join_happy": {"derived": ["The user's employer changed to CERN on 2003-05-01; on that date the user's residence was Geneva (recorded 2002-11-03, unchanged until 2007-12-20). This IS the answer."], "ev": ["[2003-05-01] employer: CERN — \"I officially started working at CERN today.\"", "[2000-01-15] residence: Oslo — \"I officially moved to Oslo today.\"", "[2002-11-03] residence: Geneva — \"I officially moved to Geneva today.\"", "[2007-12-20] residence: Munich — \"I officially moved to Munich today.\""]}}'''


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
    assert d["anchor_index"] is None, "值锚计划 anchor_index 应缺省 None"
    po = C.CompiledPlan(op="join_at_change", slot="employer",
                        slot2="residence", anchor_index=2)
    do = po.model_dump()
    assert do["anchor_index"] == 2 and do["presupposed"] is None
    # 旧形状计划(无 slot2 / anchor_index 键)仍可构造,缺省 None
    old = C.CompiledPlan.model_validate(
        {"op": "current", "slot": "employer", "date": None, "tag": None,
         "presupposed": None})
    assert old.slot2 is None and old.anchor_index is None
    old_join = C.CompiledPlan.model_validate(
        {"op": "join_at_change", "slot": "employer", "slot2": "residence",
         "date": None, "tag": None, "presupposed": "CERN"})
    assert old_join.anchor_index is None
    try:
        C.CompiledPlan(op="bogus_op")
        raise AssertionError("Literal 未拒绝未知 op")
    except Exception:  # noqa: BLE001 —— pydantic ValidationError
        pass

    assert "Q: When I started at CERN, where was I living?" in C.COMPILE_PROMPT
    join_lines = [l for l in C.COMPILE_PROMPT.splitlines()
                  if '"op": "join_at_change"' in l]
    assert len(join_lines) == 2, "join few-shot 应恰为值锚 + 序数锚两例"
    ans = join_lines[0]
    assert '"presupposed": "CERN"' in ans, "few-shot presupposed 未携锚值"
    assert '"slot2": "residence"' in ans and '"slot": "employer"' in ans
    assert '"anchor_index": null' in ans, "值锚 few-shot 应示范 anchor_index=null"
    assert f"Q: {ORD_Q}" in C.COMPILE_PROMPT, "序数 few-shot 问句缺失"
    ord_ans = join_lines[1]
    assert '"anchor_index": 2' in ord_ans, "序数 few-shot 未携 anchor_index=2"
    assert '"presupposed": null' in ord_ans, "序数 few-shot presupposed 应为 null"
    assert '"slot": "employer"' in ord_ans and '"slot2": "residence"' in ord_ans
    sem = C.COMPILE_PROMPT.split("op semantics:")[1]
    assert "join_at_change" in sem and "anchor_index" in sem
    print("A. OPS/Literal/slot2+anchor_index 可选/CERN+序数 few-shot 全部"
          "就位;旧形状计划兼容")


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


def check_ordinal_happy():
    ev, derived = _join(ORD_PLAN, q=ORD_Q)
    assert derived == [ORD_MAPPING, JOIN_DERIVED], derived
    # 证据包与值锚正例逐字节一致(锚同为 CERN 记录,后续路径完全共享)
    ev_v, _ = _join(JOIN_PLAN)
    assert ev == ev_v and len(ev) == 4, ev
    assert ev[0] == ('[2003-05-01] employer: CERN — '
                     '"I officially started working at CERN today."'), ev[0]
    print("F. 序数锚正例:anchor_index=2 → 锚链第 2 元 CERN;序数映射行 + "
          "与值锚逐字节相同的 join 结论行;证据包一致")


def check_ordinal_range():
    for bad in (9, 0):
        ev, derived = _join({**ORD_PLAN, "anchor_index": bad}, q=ORD_Q)
        assert len(derived) == 1 and derived[0].startswith(
            "Ordinal anchor out of range"), (bad, derived)
        assert "only 3 dated state(s)" in derived[0] and \
            "instead of guessing" in derived[0], derived
        assert len(ev) == 3 and all("employer" in l for l in ev), ev
    assert "9th" in _join({**ORD_PLAN, "anchor_index": 9}, q=ORD_Q)[1][0]
    print("G. 序数越界:anchor_index=9 / 0 → 'Ordinal anchor out of range' "
          "明示结论行(不猜),证据包 = 锚组全链")


# ── H:生成器隐式孪生(gen_wikistate_complex.gen_s6)────────────
GEN_ENTRY = {
    "uid": "genfix", "slot": "employer",
    "chain": [
        {"date": "2001-09-01", "value": "University of Oslo"},
        {"date": "2003-05-01", "value": "CERN"},
        {"date": "2008-02-01", "value": "Max Planck Institute"},
    ],
    "chain2": {
        "slot": "residence",
        "chain": [
            {"date": "2000-01-15", "value": "Oslo"},
            {"date": "2002-11-03", "value": "Geneva"},
            {"date": "2007-12-20", "value": "Munich"},
        ],
    },
    "sessions": [],
}


def check_gen_s6_implicit():
    rows = G.gen_s6(json.loads(json.dumps(GEN_ENTRY)))
    exp = [r for r in rows if r["qtype"] == "s6_cross_slot"]
    imp = [r for r in rows if r["qtype"] == "s6_cross_slot_implicit"]
    assert len(rows) == 8 and len(exp) == 4 and len(imp) == 4, \
        [r["qid"] for r in rows]
    by_qid = {r["qid"]: r for r in rows}
    # 每道显式题配一道孪生:qid _s6a{i} ↔ _s6ia{i},gold/槽位逐一相同
    for r in exp:
        twin = by_qid.get(r["qid"].replace("_s6", "_s6i"))
        assert twin is not None, r["qid"]
        assert twin["gold"] == r["gold"] and twin["slot"] == r["slot"]
        assert twin["anchor_slot"] == r["anchor_slot"]
        # 孪生问句不含锚值 needle(显式问句点名的锚值不出现)
        anchor_v = None
        for step in (GEN_ENTRY["chain"] + GEN_ENTRY["chain2"]["chain"]):
            if step["value"] in r["question"]:
                anchor_v = step["value"]
        assert anchor_v is not None and anchor_v not in twin["question"], \
            (r["qid"], twin["question"])
    q1 = by_qid["genfix_s6ia1"]
    assert q1["question"] == ("(Today is 2008-02-01.) When I started at my "
                              "second employer, where was I living at that "
                              "time?"), q1["question"]
    assert q1["gold"] == "Geneva" and q1["anchor_ordinal"] == 2
    assert "ordinal mapping" in q1["basis"] and \
        "position 2 (1-based) = CERN" in q1["basis"], q1["basis"]
    q2 = by_qid["genfix_s6ib2"]
    assert "moved to my third residence" in q2["question"] and \
        "what was my employer at that time?" in q2["question"]
    assert q2["gold"] == "CERN"
    # 锚值在链内重复 → 显式与孪生同跳(repeat 筛同条件)
    dup = json.loads(json.dumps(GEN_ENTRY))
    dup["chain"][2]["value"] = "University of Oslo"
    qids = {r["qid"] for r in G.gen_s6(dup)}
    assert "genfix_s6a2" not in qids and "genfix_s6ia2" not in qids, qids
    assert "genfix_s6a1" in qids and "genfix_s6ia1" in qids, qids
    print("H. 生成器隐式孪生:4 显式 × 4 孪生(同 i 同 gold,序数短语无 "
          "needle,basis 带序数映射);锚值重复时显式+孪生同跳")


def check_frozen_byte_identical():
    expected = FROZEN_EXPECTED_JSON
    got = json.dumps(_run_frozen(FROZEN_PLANS), ensure_ascii=False,
                     sort_keys=True)
    assert got == expected, "既有算子输出与改动前捕获不再逐字节一致!"
    # 同一计划显式带 slot2=None 键 → 输出不变(新键对既有算子零影响)
    plans2 = [[n, q, {**p, "slot2": None}] for n, q, p in FROZEN_PLANS]
    got2 = json.dumps(_run_frozen(plans2), ensure_ascii=False, sort_keys=True)
    assert got2 == expected, "slot2=None 键改变了既有算子输出!"
    # anchor_index=None 键同样零影响(序数锚落地后旧计划字节不变)
    plans3 = [[n, q, {**p, "anchor_index": None}] for n, q, p in FROZEN_PLANS]
    got3 = json.dumps(_run_frozen(plans3), ensure_ascii=False, sort_keys=True)
    assert got3 == expected, "anchor_index=None 键改变了既有算子输出!"
    # join fixture 计划(值锚)与序数锚落地前捕获逐字节一致
    ev, derived = _join(JOIN_PLAN)
    got_j = json.dumps({"join_happy": {"ev": ev, "derived": derived}},
                       ensure_ascii=False, sort_keys=True)
    assert got_j == FROZEN_JOIN_EXPECTED_JSON, \
        "值锚 join 输出与序数锚落地前捕获不再逐字节一致!"
    ev4, derived4 = _join({**JOIN_PLAN, "anchor_index": None})
    got_j4 = json.dumps({"join_happy": {"ev": ev4, "derived": derived4}},
                        ensure_ascii=False, sort_keys=True)
    assert got_j4 == FROZEN_JOIN_EXPECTED_JSON, \
        "anchor_index=None 键改变了值锚 join 输出!"
    print(f"E. 冻结回归:{len(FROZEN_PLANS)}+join 计划(覆盖既有 10 算子 + "
          "值锚 join)输出与改动前捕获逐字节一致;slot2=None / "
          "anchor_index=None 键零影响")


def main() -> int:
    check_schema_prompt()
    check_join_happy()
    check_fuzzy_anchor()
    check_degrade()
    check_ordinal_happy()
    check_ordinal_range()
    check_gen_s6_implicit()
    check_frozen_byte_identical()
    print("SMOKE OK: join_at_change 编译 schema/few-shot/执行器/降级 + "
          "序数锚(anchor_index)正例/越界 + 生成器隐式孪生 + 既有算子与"
          "值锚 join 字节冻结回归,全部离线断言通过(零 API 调用)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
