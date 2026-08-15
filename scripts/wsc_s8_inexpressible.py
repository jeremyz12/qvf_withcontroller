# -*- coding: utf-8 -*-
"""S8 平面臂不可表达率:按 combo 类型机械判定(非逐行 LLM 判断)。

判据:平面臂 11 算子(scripts/complex_query_arm.OPS)各自的形式语义 —— 与
scripts/qvf_algebra.py 模块头 §7.2 记录的宏定义表(op = 原语表达式)逐一
对照 data/wsc_s8.meta.json 里各 combo 类型的机械金答案定义
(scripts/verify_wsc_s8.py 的独立重写口径),判断是否存在某个平面算子
(在某种参数填法下)与该 combo 类型的正确语义处处一致:

  WINDOW∘AGG        expressible   : gold 只認"闭区间"读法(reading B,
    要求 A/B 两读一致才收录,详见 verify_wsc_s8.check_row 的 window_agg
    分支);longest 宏 = AGG(SELECT(slot,hygiene), argmax_dur) 对
    WINDOW(before=cutoff) 之后的子链求值时,同样只累计闭区间(未闭合的
    末段被跳过,不做补偿)——这恰好就是 reading B 的定义,而 gold 已过滤
    掉 A≠B 的行,故 WINDOW(before=cutoff)+argmax_dur 在全部存活行上与
    gold 处处相等。structurally expressible。

  WINDOW_2ANCHOR∘COUNT  NOT expressible : 需要双锚窗(same_chain:两个序数
    位之间;cross:另一条链两个序数位对应的两个日期之间)计数元素/转移。
    11 算子里唯一沾边的 count_before(单一字面日期上界,只统计"不同值数")
    与 count_changes(整条链的转移数,零窗)都不具备"双侧界"或"以第二
    条链的序数锚定界"的能力——没有任何参数填法能重现这个语义。

  NTH∘JOIN_T        expressible   : gold = 另一条链 O 上,严格早于锚链 W
    第 n 个(0-based)转移日期 T 的最后一个转移的值(candidates 严格
    < T,取 max index)。join_at_change 宏 = ASOF(SELECT(slot2),
    at=PICK(SELECT(slot),index=anchor_index)) 的语义就是"锚记录生效日 T
    处,slot2 链上 t_i <= T 的最后一条"——ASOF 用 <=,verify 用 <,但
    wsc_s8.jsonl 生成时已显式剔除 T 与 O 转移重合的行(见
    verify_wsc_s8.check_row 的 NTH∘JOIN_T 分支:
    "if any(t == T for t in O['parsed']): return mismatch",即这类边界
    重合行本就不会出现在数据集里),故存活行上 <= 与 < 处处等价。
    anchor_index 用 1-based(n+1)可与 gold 的 0-based n 对齐。
    structurally expressible(前提:编译器需正确识别 slot/slot2/
    anchor_index,这是经验编译准确率问题,不影响此处的结构可表达性判定)。

  JOIN_T∘WINDOW     NOT expressible : gold 需要遍历锚链 W 的每一段窗口,
    统计另一条链 C 落在该段窗口内的转移数,再取"计数从属"意义下的赢家段
    (唯一 >=2 或唯一 argmax),报告赢家段自身的值——这是"逐段计数+跨段
    比较"复合操作,11 算子里没有任何单一算子在任何参数下能重现(longest
    比较的是"段自身时长",不是"段内另一条链的转移数";count_changes/
    count_before 都不做逐段分组比较)。

用法:
  python scripts/wsc_s8_inexpressible.py [--rows data/wsc_s8.jsonl] [--split unseen]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

EXPRESSIBLE_BY_COMBO = {
    "WINDOW∘COUNT": False,          # dev round 1 发现:平面臂无双侧界/值锚窗
    "NTH∘CMP_DUR": False,           # 平面臂 longest 只做全链 argmax,不做定序对比较
    "WINDOW∘AGG": True,             # reading B(闭区间)与 gold 处处一致,见上
    "WINDOW_2ANCHOR∘COUNT": False,  # 无双锚窗原语
    "NTH∘JOIN_T": True,             # join_at_change 的 ASOF+序数 PICK 语义处处一致
    "JOIN_T∘WINDOW": False,         # 无逐段计数比较原语
}

NOTES = {
    "WINDOW∘COUNT": "平面臂只有 count_before(单侧字面日期上界,统计不同值"
                    "数);combo 需要双侧界(常为值锚,如'since I moved to "
                    "X')统计转移数,任何参数填法都无法重现。",
    "NTH∘CMP_DUR": "平面臂 longest 是全链 argmax_dur;combo 需要比较两个"
                   "指定序数段的时长,当链上有第三段介入时全链 argmax 会"
                   "选中它而非二者之一。",
    "WINDOW∘AGG": "gold 收录条件已要求闭区间读法(reading B)与完整读法"
                  "(reading A)一致;count_before 的姊妹算子 longest 对"
                  "WINDOW(before=cutoff) 求值时天然只计闭区间,故与 gold "
                  "处处相等,虽然平面臂本身没有 WINDOW 原语可组合——这里"
                  "记为可表达是针对'代数臂的 WINDOW+longest 组合'与平面臂"
                  "自身单算子的对照,平面臂若强行只用 longest(不加窗)则"
                  "会把窗外数据也计入,故仍按其编译出的单算子实际语义判——"
                  "平面臂唯一能落的算子是 longest(无窗),与 gold 不等价"
                  "（除非 cutoff 恰好覆盖全链）。见 --strict 说明。",
    "WINDOW_2ANCHOR∘COUNT": "无双锚窗原语,同/跨链序数或值锚定界均无法表达。",
    "NTH∘JOIN_T": "join_at_change 的 anchor_index + ASOF 语义与 gold 处处"
                  "一致(数据集已剔除边界重合的歧义行)。",
    "JOIN_T∘WINDOW": "需要逐段计数比较,11 算子无一能重现。",
}

# --strict:平面臂实际能落的单算子(无组合能力)是否真能重现 gold,而不是
# "代数臂用 WINDOW 宏能重现"。WINDOW∘AGG 在平面臂自己的算子表里,唯一被
# 迫落的是 longest(无窗,对全链求 argmax_dur);cutoff 之后还有数据时,
# 全链 argmax 会把窗外更长的段也纳入比较,与仅窗内的 gold 不等价。因此
# "平面臂能否表达"这一问题的正确答案是 NOT expressible——WINDOW∘AGG 只在
# "代数臂有 WINDOW 原语可组合"的意义下才 expressible。上面的 True 标注
# 描述的是代数侧的宏语义等价,不是平面臂 11 算子表自身的表达力;跑批报表
# 一律使用 --strict(平面臂自身单算子口径),真正衡量"11 算子表能否表达"。
EXPRESSIBLE_STRICT = {
    "WINDOW∘COUNT": False,
    "NTH∘CMP_DUR": False,
    "WINDOW∘AGG": False,   # 平面臂只有 longest(全链、无窗),不等价 gold
    "WINDOW_2ANCHOR∘COUNT": False,
    "NTH∘JOIN_T": True,    # join_at_change 本身就是平面 11 算子之一,原样可用
    "JOIN_T∘WINDOW": False,
}


def classify(rows_path: str, split: str | None):
    rows = [json.loads(l) for l in open(rows_path, encoding="utf-8")
            if l.strip()]
    if split:
        rows = [r for r in rows if r.get("split") == split]
    by_combo = Counter(r["combo"] for r in rows)
    n = len(rows)
    n_inexpr = sum(c for combo, c in by_combo.items()
                   if not EXPRESSIBLE_STRICT.get(combo, False))
    return rows, by_combo, n, n_inexpr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="data/wsc_s8.jsonl")
    ap.add_argument("--split", default="unseen")
    a = ap.parse_args()
    rows, by_combo, n, n_inexpr = classify(a.rows, a.split)
    print(f"split={a.split or 'all'} n={n} inexpressible={n_inexpr} "
          f"({n_inexpr / n * 100:.1f}%)")
    for combo, c in sorted(by_combo.items()):
        expr = EXPRESSIBLE_STRICT.get(combo)
        print(f"  {combo:24s} n={c:3d}  flat_expressible={expr}")
        print(f"    -> {NOTES.get(combo, '')}")


if __name__ == "__main__":
    main()
