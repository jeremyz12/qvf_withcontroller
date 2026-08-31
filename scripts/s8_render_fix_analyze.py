# -*- coding: utf-8 -*-
"""渲染修复(QVF_RENDER_ANCHORS)持出集结果分析:总表 + 分 combo + 拒答率。

只读三份跑批产物(flat / algebra_off / algebra_on),不改动任何数据,输出
markdown 表格片段到 stdout,供 results/algebra_render_fix_20260816.md 直接
粘贴。

拒答/空依据关键词表是本脚本内的启发式判据(不进入生产读者/判官提示词,
只用于本报告的机制分析),可能漏检措辞更委婉的拒答,已在报告里如实标注
这一局限。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REJECT_PHRASES = [
    "don't have", "do not have", "don't recall", "do not recall",
    "no record", "no information", "not sure", "can't find", "cannot find",
    "no memory of", "i don't know", "not have any record",
    "no details about", "don't have details", "unable to",
]


def load(p: str) -> list[dict]:
    if not Path(p).exists():
        print(f"MISSING: {p}", file=sys.stderr)
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def attach_combo(rows: list[dict], combo_by_qid: dict) -> list[dict]:
    """跑批产物行本身不带 combo 字段(complex_query_arm.run() 的行结构里
    没有这一列);从原始持出集(qid -> combo)反查补上,纯本地 join,不
    改变任何已产出结果文件。"""
    out = []
    for r in rows:
        r = dict(r)
        r["combo"] = combo_by_qid.get(r.get("question_id"), "?")
        out.append(r)
    return out


def is_reject(answer: str) -> bool:
    a = (answer or "").lower()
    return any(ph in a for ph in REJECT_PHRASES)


def summarize(rows: list[dict], label: str):
    by_combo = defaultdict(lambda: {"n": 0, "correct": 0, "reject": 0})
    for r in rows:
        combo = r.get("combo") or "?"
        d = by_combo[combo]
        d["n"] += 1
        d["correct"] += int(bool(r.get("judge_correct")))
        d["reject"] += int(is_reject(r.get("answer", "")))
    tot = {"n": 0, "correct": 0, "reject": 0}
    for d in by_combo.values():
        for k in tot:
            tot[k] += d[k]
    print(f"\n### {label}")
    print("| combo | n | correct | acc | reject-phrasing |")
    print("|---|---|---|---|---|")
    for combo, d in sorted(by_combo.items()):
        acc = d["correct"] / d["n"] * 100 if d["n"] else 0
        rj = d["reject"] / d["n"] * 100 if d["n"] else 0
        print(f"| {combo} | {d['n']} | {d['correct']} | {acc:.1f}% | {rj:.1f}% |")
    acc = tot["correct"] / tot["n"] * 100 if tot["n"] else 0
    rj = tot["reject"] / tot["n"] * 100 if tot["n"] else 0
    print(f"| **TOTAL** | {tot['n']} | {tot['correct']} | **{acc:.1f}%** | {rj:.1f}% |")
    return by_combo, tot


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--flat", required=True)
    ap.add_argument("--algebra-off", required=True)
    ap.add_argument("--algebra-on", required=True)
    ap.add_argument("--questions", default="data/wsc_s8_heldout_p2.jsonl")
    a = ap.parse_args()

    combo_by_qid = {r["qid"]: r["combo"] for r in load(a.questions)}
    flat = attach_combo(load(a.flat), combo_by_qid)
    off = attach_combo(load(a.algebra_off), combo_by_qid)
    on = attach_combo(load(a.algebra_on), combo_by_qid)

    _, tot_flat = summarize(flat, "Flat arm (11-op macros, QVF_ALGEBRA=0)")
    by_combo_off, tot_off = summarize(off, "Algebra arm, render fix OFF (QVF_ALGEBRA=1 QVF_RENDER_ANCHORS=0)")
    by_combo_on, tot_on = summarize(on, "Algebra arm, render fix ON (QVF_ALGEBRA=1 QVF_RENDER_ANCHORS=1)")

    print("\n### Predicate check")
    d1 = tot_on["correct"] / tot_on["n"] * 100 - tot_flat["correct"] / tot_flat["n"] * 100 \
        if tot_on["n"] and tot_flat["n"] else float("nan")
    print(f"Predicate 1 (main): algebra-on vs flat, delta = {d1:+.1f}pp "
          f"({'PASS (>=0)' if d1 >= 0 else 'FAIL (<0)'})")
    rj_off = tot_off["reject"] / tot_off["n"] * 100 if tot_off["n"] else float("nan")
    rj_on = tot_on["reject"] / tot_on["n"] * 100 if tot_on["n"] else float("nan")
    print(f"Predicate 2 (mechanism, overall): reject-phrasing rate off={rj_off:.1f}% -> on={rj_on:.1f}%")

    target = "WINDOW_2ANCHOR∘COUNT"
    off_c = by_combo_off.get(target)
    on_c = by_combo_on.get(target)
    if off_c and on_c:
        rj_off_c = off_c["reject"] / off_c["n"] * 100
        rj_on_c = on_c["reject"] / on_c["n"] * 100
        acc_off_c = off_c["correct"] / off_c["n"] * 100
        acc_on_c = on_c["correct"] / on_c["n"] * 100
        print(f"Predicate 2 (mechanism, {target} only, n={off_c['n']}): "
              f"reject-phrasing off={rj_off_c:.1f}% -> on={rj_on_c:.1f}%, "
              f"acc off={acc_off_c:.1f}% -> on={acc_on_c:.1f}%")


if __name__ == "__main__":
    main()
