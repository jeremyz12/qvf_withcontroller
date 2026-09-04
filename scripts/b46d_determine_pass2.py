# -*- coding: utf-8 -*-
"""批 46d 步骤 A:GOLD-FREE 第二遍抽取触发判据。

只读 results/wt_cards_v48(144 链 pass1)的逐链 len(records),不读语料
chain 字段、不看金标行数、不做任何金标锚点核验——与批 41(gold-anchor
触发,只挑 3 条金标缺口链)方法论互斥,本脚本严格执行任务书指定的
gold-free 版本。

触发判据(OR):
  (a) 记录数 <= Q1(numpy.percentile(counts, 25, method='linear'))
  (b) 记录数 <  0.6 * median(counts)

用法: PYTHONUTF8=1 python scripts/b46d_determine_pass2.py
输出: results/b46d_pass2_triggers.json
      results/b46d_pass2_uids.txt (逗号分隔,供 --uids 直接消费)
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import numpy as np

ROOT = Path(r"D:/ZZL_cluade")
SRC = ROOT / "results/wt_cards_v48"
UIDS_FILE = ROOT / "results/b46d_all144_uids.txt"
OUT_JSON = ROOT / "results/b46d_pass2_triggers.json"
OUT_UIDS = ROOT / "results/b46d_pass2_uids.txt"


def main():
    uids = [x.strip() for x in UIDS_FILE.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert len(uids) == 144, f"expected 144 uids, got {len(uids)}"

    counts = {}
    missing = []
    for u in uids:
        p = SRC / f"{u}.json"
        if not p.exists():
            missing.append(u)
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        counts[u] = len(obj.get("records") or [])
    if missing:
        raise SystemExit(f"missing pass1 files for {len(missing)} uids: {missing}")

    vals = list(counts.values())
    q1 = float(np.percentile(vals, 25, method="linear"))
    median = float(st.median(vals))
    thr60 = 0.6 * median

    triggered = []
    for u in uids:
        c = counts[u]
        reasons = []
        if c <= q1:
            reasons.append("le_q1")
        if c < thr60:
            reasons.append("lt_60pct_median")
        if reasons:
            triggered.append({"uid": u, "count": c, "reasons": reasons})

    triggered.sort(key=lambda d: d["count"])

    report = {
        "n_chains": len(uids),
        "counts_summary": {
            "min": min(vals), "max": max(vals),
            "mean": round(sum(vals) / len(vals), 2),
            "median": median, "q1_p25_linear": q1,
            "threshold_60pct_median": thr60,
        },
        "n_triggered": len(triggered),
        "triggered": triggered,
        "counts_by_uid": counts,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    OUT_UIDS.write_text(",".join(d["uid"] for d in triggered), encoding="utf-8")

    print(f"n_chains={len(uids)} min={min(vals)} q1={q1:.2f} median={median} "
          f"60%median={thr60:.2f} max={max(vals)}")
    print(f"n_triggered={len(triggered)} / {len(uids)} "
          f"({len(triggered)/len(uids)*100:.1f}%)")
    for d in triggered:
        print(f"  {d['uid']}: count={d['count']} reasons={d['reasons']}")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_UIDS} ({len(triggered)} uids, comma-separated)")


if __name__ == "__main__":
    main()
