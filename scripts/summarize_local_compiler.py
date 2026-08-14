# -*- coding: utf-8 -*-
"""汇总本地编译评测 jsonl → 总表 + 分算子表 + 判决(阶段 0 报告)。

用法:
  python scripts/summarize_local_compiler.py \
      results/local_compile_qwen3_4b_20260815.jsonl [more.jsonl ...] \
      --out results/local_compiler_stage0_20260815.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

GREEN_LINE = 0.90  # 绿灯线:计划一致率或执行等价率 ≥90%


def load(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    meta_p = Path(path).with_suffix(".meta.json")
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() \
        else {}
    return rows, meta


def pct(a, b):
    return f"{a}/{b} = {a / b * 100:.1f}%" if b else "n/a"


def summarize(rows, meta):
    n = len(rows)
    s = {
        "model": rows[0]["model"] if rows else "?", "n": n,
        "json_valid": sum(r["json_valid_first"] for r in rows),
        "compile_ok": sum(r["compile_ok"] for r in rows),
        "agree": sum(r["plan_agree"] for r in rows),
        "exec": sum(r["exec_equal"] for r in rows),
        "lat_med": statistics.median([r["latency_s"] for r in rows]) if rows
        else 0,
        "wall_s": meta.get("wall_s"),
        "vram_max": meta.get("vram_max_mib"),
        "vram_base": meta.get("vram_baseline_mib"),
        "ollama_ps": meta.get("ollama_ps", ""),
    }
    s["thr"] = (n / meta["wall_s"] * 60) if meta.get("wall_s") else None
    by_op = {}
    for r in rows:
        op = r["ref_plan"]["op"]
        d = by_op.setdefault(op, {"n": 0, "agree": 0, "exec": 0,
                                  "json": 0, "mis": {}})
        d["n"] += 1
        d["agree"] += r["plan_agree"]
        d["exec"] += r["exec_equal"]
        d["json"] += r["json_valid_first"]
        if not r["plan_agree"]:
            f = r.get("mismatch_field") or "?"
            d["mis"][f] = d["mis"].get(f, 0) + 1
    s["by_op"] = by_op
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonls", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sums = []
    for p in a.jsonls:
        rows, meta = load(p)
        rows = [r for r in rows if r.get("question_id") != "__META__"]
        sums.append((p, summarize(rows, meta)))

    L = []
    L.append("# 本地编译器评测 · 阶段 0(能力下限测量)\n")
    L.append("日期:2026-08-15;评测线:`scripts/eval_local_compiler.py`;"
             "参考集 369 题(qid 去重、判对且 compile_ok 的最新跑;"
             "S7 严格档 precision=1 & recall=1 & 零幻觉)。\n")
    L.append("提示词:与 haiku 线逐字节相同(import 冻结臂 COMPILE_PROMPT);"
             "temperature 0,num_predict 512,重试 ≤3,format=json + "
             "think=false 三档统一。零 API LLM 成本。\n")
    L.append("## 总表\n")
    L.append("| 模型 | n | 严格 JSON 合法率(首次) | 编译成功率(≤3 试) | "
             "计划一致率 | 执行等价率 | 每题延迟中位 | 吞吐 | "
             "模型驻留(ollama ps) | nvidia-smi 峰值(全卡) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for p, s in sums:
        thr = f"{s['thr']:.1f} 题/分" if s["thr"] else "n/a"
        m = re.search(r"(\d+(?:\.\d+)?\s*GB)\s+(\d+%[^\s]*(?:\s*GPU)?)",
                      s["ollama_ps"] or "")
        resident = f"{m.group(1)}, {m.group(2)}" if m else "?"
        L.append(
            f"| {s['model']} | {s['n']} | {pct(s['json_valid'], s['n'])} | "
            f"{pct(s['compile_ok'], s['n'])} | {pct(s['agree'], s['n'])} | "
            f"{pct(s['exec'], s['n'])} | {s['lat_med']:.2f}s | {thr} | "
            f"{resident} | {s['vram_max']} MiB(跑前基线 {s['vram_base']}) |")
    L.append("")
    L.append("显存注记:nvidia-smi 为全卡占用,评测期间桌面/其他应用共占"
             "(4b 跑时用户游戏在前台,基线 15.4GB;8b 跑时游戏中途退出);"
             "模型真实驻留以 ollama ps 列为准,三档均 100% GPU、未发生 CPU "
             "卸载。")
    L.append("")
    L.append("## 分算子(计划一致 / 执行等价)\n")
    ops = sorted({op for _, s in sums for op in s["by_op"]})
    head = "| 算子 | n |" + "".join(f" {s['model']} |" for _, s in sums)
    L.append(head)
    L.append("|---|---|" + "---|" * len(sums))
    n_by_op = {}
    for _, s in sums:
        for op, d in s["by_op"].items():
            n_by_op[op] = d["n"]
    for op in ops:
        cells = []
        for _, s in sums:
            d = s["by_op"].get(op)
            if d:
                cells.append(f" {d['agree']}/{d['n']} · exec {d['exec']}/{d['n']} |")
            else:
                cells.append(" - |")
        L.append(f"| {op} | {n_by_op[op]} |" + "".join(cells))
    L.append("")
    L.append("### 不一致主因(mismatch_field 计数)\n")
    for _, s in sums:
        mis_all = {}
        for op, d in s["by_op"].items():
            for f, c in d["mis"].items():
                mis_all[f"{op}.{f}"] = c
        top = sorted(mis_all.items(), key=lambda x: -x[1])[:8]
        L.append(f"- **{s['model']}**:" + ("、".join(
            f"{k} ×{v}" for k, v in top) if top else "无不一致"))
    L.append("")
    L.append("## 判决\n")
    for _, s in sums:
        ra = s["agree"] / s["n"] if s["n"] else 0
        re_ = s["exec"] / s["n"] if s["n"] else 0
        green = max(ra, re_) >= GREEN_LINE
        verdict = "绿灯(≥90%,可进阶段 1 蒸馏)" if green else "未过线"
        L.append(f"- **{s['model']}**:计划一致 {ra * 100:.1f}%,执行等价 "
                 f"{re_ * 100:.1f}% → {verdict}")
    out = Path(a.out)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
