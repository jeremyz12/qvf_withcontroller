# -*- coding: utf-8 -*-
"""批 33-J 成本总账($0):一律由行内 usage token 折算,建卡侧读 write_phase 日志。

用法:python scripts/b33j_cost_ledger.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = {"haiku": (1.00, 5.00), "mini": (0.25, 2.00), "opus": (5.00, 25.00)}
JUDGE_ARCHIVE_RATE = 0.00308   # results/judge_cost_measured_20260816.md:5


def rows(pat):
    out = []
    for f in sorted(glob.glob(str(ROOT / pat))):
        for l in open(f, encoding="utf-8"):
            if l.strip():
                out.append(json.loads(l))
    return out


def block(label, pat, reader_key):
    rs = rows(pat)
    if not rs:
        return label, 0, 0.0, 0.0, 0.0
    pi, po = P[reader_key]
    ri = sum(r.get("usage_input_tokens", 0) for r in rs)
    ro = sum(r.get("usage_output_tokens", 0) for r in rs)
    read_usd = ri / 1e6 * pi + ro / 1e6 * po
    # rtl 建卡侧(去重按检索集)
    ci = co = 0
    seen = set()
    for r in rs:
        if "rtl_catalog_input_tokens" not in r:
            continue
        k = tuple(r.get("retrieved_memory_ids") or [r["question_id"]])
        if k in seen:
            continue
        seen.add(k)
        ci += r["rtl_catalog_input_tokens"]
        co += r["rtl_catalog_output_tokens"]
    build_usd = ci / 1e6 * P["haiku"][0] + co / 1e6 * P["haiku"][1]
    ji = jo = 0
    n_est = 0
    for r in rs:
        if r.get("judge_input_tokens") is not None:
            ji += r["judge_input_tokens"] or 0
            jo += r["judge_output_tokens"] or 0
        else:
            n_est += 1
    judge_usd = ji / 1e6 * P["opus"][0] + jo / 1e6 * P["opus"][1] + \
        n_est * JUDGE_ARCHIVE_RATE
    return label, len(rs), read_usd, build_usd, judge_usd


def main():
    items = [
        block("J4 gpt-5-mini smoc 补丁", "results/b33j/j4_smoc_patched_s*.jsonl", "mini"),
        block("J4 gpt-5-mini smoc 不补丁", "results/b33j/j4_smoc_plain_s*.jsonl", "mini"),
        block("J2 dim1 smoc", "results/b33j/j2_dim1_smoc_s*.jsonl", "haiku"),
        block("J2 dim1 direct", "results/b33j/j2_dim1_direct_s*.jsonl", "haiku"),
        block("J2 dim4 smoc", "results/b33j/j2_dim4_smoc_s*.jsonl", "haiku"),
        block("J2 dim4 direct", "results/b33j/j2_dim4_direct_s*.jsonl", "haiku"),
        block("J3 nofiller smoc", "results/b33j/j3_smoc_nofiller_s*.jsonl", "haiku"),
        block("J3 nofiller direct", "results/b33j/j3_direct_nofiller_s*.jsonl", "haiku"),
        block("J3 nofiller fullplain", "results/b33j/j3_fullplain_nofiller_s*.jsonl", "haiku"),
        block("J1 rtl(读时账目)", "results/b33j/j1_rtl_s*.jsonl", "haiku"),
    ]
    # J3 建店(write_phase 日志)
    bl = ROOT / "results/b33j/log_j3_build.txt"
    build30 = 0.0
    if bl.exists():
        m = re.search(r"WRITE PHASE TOTAL: in=(\d+) out=(\d+)",
                      bl.read_text(encoding="utf-8"))
        if m:
            build30 = int(m.group(1)) / 1e6 * P["haiku"][0] + \
                int(m.group(2)) / 1e6 * P["haiku"][1]
    print(f"{'条目':<28}{'n':>6}{'读者$':>9}{'建卡$':>9}{'判官$':>9}{'合计$':>9}")
    tot = 0.0
    for lab, n, r, b, j in items:
        s = r + b + j
        tot += s
        print(f"{lab:<28}{n:>6}{r:>9.3f}{b:>9.3f}{j:>9.3f}{s:>9.3f}")
    print(f"{'J3 无填充建店(30 店)':<28}{30:>6}{0:>9.3f}{build30:>9.3f}"
          f"{0:>9.3f}{build30:>9.3f}")
    tot += build30
    print(f"{'—— 总计 ——':<28}{'':>6}{'':>9}{'':>9}{'':>9}{tot:>9.3f}")
    print("\n注:嵌入侧(text-embedding-3-small,$0.02/M)未落 usage 字段,"
          "按语料 token 量级估 <$0.15,未计入上表。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
