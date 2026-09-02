# -*- coding: utf-8 -*-
"""批 33-A 溯源块采集:语料 sha256 / 店目录指纹 / git rev / 各臂运行时窗与成本。

用法: PYTHONUTF8=1 python scripts/b33A_provenance.py > results/b33A_provenance.txt
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
P_IN, P_OUT = 0.80, 4.00

CORPUS = "data/wikistate_full_ALL_v24.json"
QUESTIONS = "data/wsc_s5_v2.jsonl"
STORES = ["results/wt_cards_v45", "results/wt_cards_v45g",
          "results/wt_cards_v45k"]
SUMDIR = "results/wt_summaries_v24"

ARMS = [
    ("direct",     "results/b33A_direct.jsonl",     "—(不读店)"),
    ("filter",     "results/b33A_filter.jsonl",     "wt_cards_v45"),
    ("usability",  "results/b33A_usability.jsonl",  "wt_cards_v45"),
    ("compile",    "results/b33A_compile.jsonl",    "wt_cards_v45"),
    ("smw",        "results/b33A_smw.jsonl",        "—(读原文)"),
    ("smwplain",   "results/b33A_smwplain.jsonl",   "—(读原文)"),
    ("summary",    "results/b33A_summary.jsonl",    SUMDIR),
    ("smoc_v45",   "results/b33A_smoc_v45.jsonl",   "wt_cards_v45"),
    ("smoc_v45g",  "results/b33A_smoc_v45g.jsonl",  "wt_cards_v45g"),
    ("filter_k",   "results/b33A_filter_k.jsonl",   "wt_cards_v45k (derived)"),
    ("usability_k", "results/b33A_usability_k.jsonl", "wt_cards_v45k (derived)"),
    ("compile_k",  "results/b33A_compile_k.jsonl",  "wt_cards_v45k (derived)"),
    ("filter_v42probe", "results/b33A_filter_v42probe.jsonl", "wt_cards_v42 (144 fvl only)"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ts(x: float) -> str:
    return dt.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    print("## 溯源块(批 33-A)\n")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "qvf"],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"- git rev: `{git}`")
    print(f"- scripts//qvf 工作区改动: "
          f"{'无' if not dirty else chr(10) + '```' + chr(10) + dirty + chr(10) + '```'}")

    for rel in (CORPUS, QUESTIONS):
        p = ROOT / rel
        print(f"- 语料/题源 `{rel}`: sha256 `{sha256(p)}` "
              f"({p.stat().st_size:,} B, mtime {ts(p.stat().st_mtime)})")

    for s in STORES:
        d = ROOT / s
        fs = sorted(d.glob("*.json"))
        if not fs:
            print(f"- 店 `{s}`: **缺失**")
            continue
        mt = max(f.stat().st_mtime for f in fs)
        mn = min(f.stat().st_mtime for f in fs)
        cat = hashlib.sha256()
        for f in fs:
            cat.update(f.name.encode())
            cat.update(f.read_bytes())
        print(f"- 店 `{s}`: {len(fs)} 文件 | 建店窗 {ts(mn)} → {ts(mt)} | "
              f"目录 sha256(名+内容拼接) `{cat.hexdigest()}`")

    sd = ROOT / SUMDIR
    if sd.exists():
        fs = sorted(sd.glob("*.txt"))
        if fs:
            print(f"- 摘要目录 `{SUMDIR}`: {len(fs)} 文件 | "
                  f"{ts(min(f.stat().st_mtime for f in fs))} → "
                  f"{ts(max(f.stat().st_mtime for f in fs))}")

    print("\n### 逐臂运行时窗 / 产物 / 读者侧成本\n")
    print("| 臂 | 产物 | 行数 | 店 | 文件 mtime | 读者 in tok | 读者 out tok | "
          "读者 $(0.8/4) | 累计延迟 h |")
    print("|---|---|---|---|---|---|---|---|---|")
    tot_in = tot_out = 0.0
    for name, rel, store in ARMS:
        p = ROOT / rel
        if not p.exists():
            print(f"| {name} | `{rel}` | **缺失** | {store} | — | — | — | — | — |")
            continue
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
        to = sum(r.get("usage_output_tokens") or 0 for r in rows)
        lat = sum(r.get("latency_s") or 0 for r in rows)
        tot_in += ti
        tot_out += to
        usd = ti / 1e6 * P_IN + to / 1e6 * P_OUT
        print(f"| {name} | `{rel}` | {len(rows)} | {store} | "
              f"{ts(p.stat().st_mtime)} | {ti:,} | {to:,} | ${usd:.3f} | "
              f"{lat / 3600:.2f} |")
    print(f"\n读者侧合计:in {tot_in:,.0f} / out {tot_out:,.0f} tok = "
          f"**${tot_in / 1e6 * P_IN + tot_out / 1e6 * P_OUT:.2f}**"
          f"(haiku $0.80/M in、$4.00/M out;判官 claude-opus-5 另计)")


if __name__ == "__main__":
    main()
