# -*- coding: utf-8 -*-
"""批 46d 溯源块:pass1/pass2 建店窗 / 逐链建店成本 / 目录 sha256 / 读者臂成本。

目录 sha256 口径与 scripts/b33A_provenance.py / scripts/b38_provenance.py
逐字相同(排序后按文件名 + 文件内容拼接做一次 sha256)。

用法: PYTHONUTF8=1 python scripts/b46d_provenance.py > results/b46d_provenance.txt
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
SCRATCH = Path(r"C:/Users/25243/AppData/Local/Temp/claude/"
               r"D--ZZL-cluade/127d6855-ac31-4f09-a027-67dbfc5cf191/scratchpad")

CORPUS = "data/wikistate_full_ALL_v24.json"
QUESTIONS = "data/wsc_s5_v25.jsonl"
STORES = ["results/wt_cards_v45", "results/wt_cards_v48",
         "results/wt_cards_v48_pass2", "results/wt_cards_v48f"]

B_IN, B_OUT = 2.00, 10.00   # claude-sonnet-5 建卡价
PRICE = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5": (2.00, 10.00)}

RUNS = [
    ("run1", "results/b46d_smoc_v48f_haiku_run1.jsonl", "results/wt_cards_v48f",
     "claude-haiku-4-5"),
    ("run2", "results/b46d_smoc_v48f_haiku_run2.jsonl", "results/wt_cards_v48f",
     "claude-haiku-4-5"),
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
    print("## 溯源块(批 46d)\n")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--",
                            "scripts", "qvf"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    print(f"- git rev: `{git}`")
    print("- scripts//qvf 工作区改动:"
          + ("无" if not dirty else "\n```\n" + dirty + "\n```"))

    for rel in (CORPUS, QUESTIONS):
        p = ROOT / rel
        if p.exists():
            print(f"- 语料/题源 `{rel}`: sha256 `{sha256(p)}` "
                  f"({p.stat().st_size:,} B, mtime {ts(p.stat().st_mtime)})")

    print("\n### 建卡器(写入侧,冻结配置)\n")
    frozen = ROOT / "scripts/wt_qvf_prototype.py"
    b38 = ROOT / "scripts/wt_qvf_prototype_b38.py"
    print(f"- 冻结件 `scripts/wt_qvf_prototype.py` sha256 `{sha256(frozen)}` "
          "(全程只读,未改)")
    print(f"- 建卡器 `scripts/wt_qvf_prototype_b38.py`(批 38 冻结副本,本批"
          f"复用不新建)sha256 `{sha256(b38)}`")
    print("""
- **pass1 建店命令**(144 链全量):
  ```
  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \\
  QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_b38.py \\
    --phase write --data data/wikistate_full_ALL_v24.json \\
    --cards-dir results/wt_cards_v48 --uids <shard>   # 8 分片并行
  ```
- **pass2 建店命令**(gold-free 触发链子集,见 results/b46d_pass2_triggers.json):
  ```
  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \\
  QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_b38.py \\
    --phase write --data data/wikistate_full_ALL_v24.json \\
    --cards-dir results/wt_cards_v48_pass2 --uids <triggered subset>
  ```
""")

    print("### 建店窗 / 目录指纹\n")
    for s in STORES:
        d = ROOT / s
        fs = sorted(d.glob("*.json"))
        if not fs:
            print(f"- 店 `{s}`: **缺失/空**")
            continue
        mt = max(f.stat().st_mtime for f in fs)
        mn = min(f.stat().st_mtime for f in fs)
        cat = hashlib.sha256()
        nrec = 0
        for f in fs:
            cat.update(f.name.encode())
            b = f.read_bytes()
            cat.update(b)
            nrec += len(json.loads(b)["records"])
        print(f"- 店 `{s}`: {len(fs)} 文件 / {nrec:,} 记录 | 建店窗 "
              f"{ts(mn)} → {ts(mt)} | 目录 sha256(名+内容拼接) "
              f"`{cat.hexdigest()}`")

    print("\n### GOLD-FREE 第二遍触发统计\n")
    trig_f = ROOT / "results/b46d_pass2_triggers.json"
    if trig_f.exists():
        trig = json.loads(trig_f.read_text(encoding="utf-8"))
        cs = trig["counts_summary"]
        print(f"- 144 链 pass1 记录数:min={cs['min']} median={cs['median']} "
              f"q1(p25 linear)={cs['q1_p25_linear']:.2f} "
              f"60%median={cs['threshold_60pct_median']:.2f} max={cs['max']}")
        print(f"- 触发链数:{trig['n_triggered']}/{trig['n_chains']} "
              f"({trig['n_triggered']/trig['n_chains']*100:.1f}%)")
    else:
        print("- (results/b46d_pass2_triggers.json 缺失)")

    print("\n### 逐分片建店日志成本(claude-sonnet-5 $2.00/M in、$10.00/M out)\n")
    for phase, pattern in (("pass1", "build_v48_shard*.log"),
                           ("pass2", "build_v48_pass2*.log")):
        logs = sorted(glob.glob(str(SCRATCH / "b46d" / pattern)))
        if not logs:
            continue
        print(f"\n**{phase}**\n")
        print("| 日志 | 条目 | in tok | out tok | $ |")
        print("|---|---|---|---|---|")
        g_in = g_out = g_n = 0
        for lg in logs:
            txt = Path(lg).read_text(encoding="utf-8", errors="replace")
            items = re.findall(r"^\[(.*?)\] (\d+) cards \((\d+) batch\), "
                               r"in=(\d+) out=(\d+) \((\d+)s\)", txt, re.M)
            ti = sum(int(x[3]) for x in items)
            to = sum(int(x[4]) for x in items)
            g_in += ti; g_out += to; g_n += len(items)
            print(f"| `{Path(lg).name}` | {len(items)} | {ti:,} | {to:,} | "
                  f"${ti / 1e6 * B_IN + to / 1e6 * B_OUT:.3f} |")
        print(f"| **合计** | **{g_n}** | **{g_in:,}** | **{g_out:,}** | "
              f"**${g_in / 1e6 * B_IN + g_out / 1e6 * B_OUT:.3f}** |")

    print("\n### 读者臂运行时窗 / 成本\n")
    print("| 臂 | 产物 | 行数 | 店 | 读者 | 文件 mtime | in tok | out tok | "
          "$ | 累计延迟 h |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    tot = 0.0
    for name, rel, store, model in RUNS:
        p = ROOT / rel
        if not p.exists():
            print(f"| {name} | `{rel}` | **缺失** | {store} | {model} | — | — | "
                  "— | — | — |")
            continue
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
        to = sum(r.get("usage_output_tokens") or 0 for r in rows)
        lat = sum(r.get("latency_s") or 0 for r in rows)
        pi, po = PRICE[model]
        usd = ti / 1e6 * pi + to / 1e6 * po
        tot += usd
        print(f"| {name} | `{rel}` | {len(rows)} | {store} | {model} | "
              f"{ts(p.stat().st_mtime)} | {ti:,} | {to:,} | ${usd:.3f} | "
              f"{lat / 3600:.2f} |")
    print(f"\n**读者侧总花费(本批两跑合计)= ${tot:.3f}**")


if __name__ == "__main__":
    main()
