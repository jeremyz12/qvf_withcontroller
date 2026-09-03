# -*- coding: utf-8 -*-
"""批 35 溯源块采集(与 scripts/b33A_provenance.py 同结构):语料 sha256 / 店目录指纹 /
git rev / 建店窗与建店成本 / 各臂运行时窗与读者侧成本。

用法: PYTHONUTF8=1 python scripts/b35_provenance.py > results/b35_provenance.txt
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
P_IN, P_OUT = 1.00, 5.00       # 协调员口径
P_IN33, P_OUT33 = 0.80, 4.00   # 33-A 旧口径(换算列)

CORPUS = "data/wikistate_full_ALL_v25.json"
QUESTIONS = "results/b35_questions_sample36.jsonl"
SAMPLE = "results/b35_sample_uids.txt"
QUESTIONS_FULL = "data/wsc_s5_v25.jsonl"
STORES = ["results/wt_cards_v46", "results/wt_cards_v46k"]
BUILD_LOGS = "scratchpad/b35/build_v46_*.log"

ARMS = [
    ("direct",      "results/b35_direct.jsonl",      "—(不读店;QVF_EMBED_BACKEND=openai)"),
    ("smoc",        "results/b35_smoc.jsonl",        "wt_cards_v46"),
    ("compile_k",   "results/b35_compile_k.jsonl",   "wt_cards_v46k (derived)"),
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
    print("## 溯源块(批 35 **部分跑**:36/144 链分层抽样,v2.5 语料 × v46 店,3 臂)\n")
    sample = [l.strip() for l in open(ROOT / SAMPLE, encoding="utf-8") if l.strip()]
    qrows = [json.loads(l) for l in open(ROOT / QUESTIONS, encoding="utf-8") if l.strip()]
    print(f"- 抽样清单 `{SAMPLE}`: {len(sample)} 链(去重 {len(set(sample))}),分层 9 条/槽位")
    print(f"- 题集 `{QUESTIONS}`: {len(qrows)} 题(去重 qid {len({r['qid'] for r in qrows})};"
          f"覆盖 uid {len({r['uid'] for r in qrows})})")
    print("- 抽样 uid 全表: `" + "`, `".join(sorted(sample)) + "`")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "qvf"],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"- git rev: `{git}`")
    print(f"- scripts//qvf 工作区改动: {'无' if not dirty else chr(10) + '```' + chr(10) + dirty + chr(10) + '```'}")

    for rel in (CORPUS, QUESTIONS_FULL, QUESTIONS):
        p = ROOT / rel
        print(f"- 语料/题源 `{rel}`: sha256 `{sha256(p)}` ({p.stat().st_size:,} B, mtime {ts(p.stat().st_mtime)})")

    for s in STORES:
        d = ROOT / s
        fs = sorted(d.glob("*.json"))
        if not fs:
            print(f"- 店 `{s}`: **缺失**")
            continue
        mt = max(f.stat().st_mtime for f in fs)
        mn = min(f.stat().st_mtime for f in fs)
        cat = hashlib.sha256()
        n_rec = ti = to = 0          # 全目录 85 文件
        sn_rec = sti = sto = 0       # 仅抽样 36 链
        smn, smt = [], []
        sset = set(sample)
        for f in fs:
            cat.update(f.name.encode())
            b = f.read_bytes()
            cat.update(b)
            o = json.loads(b)
            nr = len(o.get("records", []))
            ui = o.get("usage_in", 0) or 0
            uo = o.get("usage_out", 0) or 0
            n_rec += nr
            ti += ui
            to += uo
            if f.stem in sset:
                sn_rec += nr
                sti += ui
                sto += uo
                smn.append(f.stat().st_mtime)
                smt.append(f.stat().st_mtime)
        derived = s.endswith("k")
        print(f"- 店 `{s}`{'(**派生店**,由 v46 机械补字段生成,非 builder 产物)' if derived else ''}: "
              f"{len(fs)} 文件(其中本批抽样链 {len(smn)}/{len(sample)} —— **只有这 36 个被批 35 读**;"
              f"其余 {len(fs) - len(smn)} 个为改期前的全量建店尝试所留,本批不用)")
        print(f"    - 记录数:全目录 {n_rec:,} | 抽样 36 链 {sn_rec:,}")
        print(f"    - 建店窗(全目录 mtime):{ts(mn)} → {ts(mt)};抽样 36 链:{ts(min(smn))} → {ts(max(smt))}")
        print(f"    - 目录 sha256(排序文件名+内容拼接,同 scripts/b33A_provenance.py 口径):`{cat.hexdigest()}`")
        if ti and not derived:
            print(f"    - 建店 haiku 用量:全目录 in {ti:,} / out {to:,} tok = "
                  f"${ti / 1e6 * P_IN + to / 1e6 * P_OUT:.2f}(旧口径 ${ti / 1e6 * P_IN33 + to / 1e6 * P_OUT33:.2f});"
                  f"**归属本批抽样 36 链** in {sti:,} / out {sto:,} tok = "
                  f"${sti / 1e6 * P_IN + sto / 1e6 * P_OUT:.2f}(旧口径 ${sti / 1e6 * P_IN33 + sto / 1e6 * P_OUT33:.2f})")
        elif derived:
            print(f"    - 建店成本:**$0**(纯本地拷贝+补 slot_class/owner;文件内的 usage_in/out 字段是从 v46 "
                  f"原样继承的,不代表新增 API 调用)")

    logs = sorted(glob.glob(str(ROOT / BUILD_LOGS)))
    if logs:
        st_file = ROOT / "scratchpad/b35/build_v46_start.txt"
        starts = [x.strip() for x in st_file.read_text().splitlines() if x.strip()] \
            if st_file.exists() else ["?"]
        full = [l for l in logs if "_sample_" not in Path(l).name]
        samp = [l for l in logs if "_sample_" in Path(l).name]
        print(f"- 建店命令:`QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype.py --phase write "
              f"--data {CORPUS} --cards-dir results/wt_cards_v46 --uids <shard>`,**4 个 uid 分片并行**"
              f"(builder 其余旗标全默认,与批 33-A 的 v45 同;model claude-haiku-4-5,temperature 0)")
        print(f"    - 第一轮(原计划全量 144 链)起跑 {starts[0]};范围改为 36 链抽样时中止,"
              f"故 `build_v46_{{0..3}}.log` 无 WRITE PHASE TOTAL(记为“未结束”属预期,不是失败)")
        if len(starts) > 1:
            print(f"    - 第二轮(补齐抽样链中尚缺的 uid)起跑 {starts[1]},4 分片,全部正常收尾")
        for lg in full + samp:
            txt = Path(lg).read_text(encoding="utf-8", errors="replace")
            n_items = len(re.findall(r"^\[.*?\] \d+ cards", txt, re.M))
            tot = re.search(r"WRITE PHASE TOTAL: (.*)", txt)
            print(f"  - `{Path(lg).name}`: {n_items} 条目 | "
                  f"{tot.group(1) if tot else '未结束(改范围时中止,见上)'}")
        for mf in sorted(glob.glob(str(ROOT / "scratchpad/b35/v46_missing_*.txt"))):
            uids = [u for u in Path(mf).read_text(encoding="utf-8").strip().split(",") if u]
            print(f"  - 补建清单 `{Path(mf).name}`: {len(uids)} uid")

    print("\n### 逐臂运行时窗 / 产物 / 读者侧成本\n")
    print("| 臂 | 产物 | 行数 | 唯一 qid | 店 | 文件 mtime | 读者 in tok | 读者 out tok | "
          "读者 $(1/5) | 读者 $(0.8/4) | 累计延迟 h |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    tot_in = tot_out = 0.0
    for name, rel, store in ARMS:
        p = ROOT / rel
        if not p.exists():
            print(f"| {name} | `{rel}` | **缺失** | — | {store} | — | — | — | — | — | — |")
            continue
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
        to = sum(r.get("usage_output_tokens") or 0 for r in rows)
        lat = sum(r.get("latency_s") or 0 for r in rows)
        tot_in += ti
        tot_out += to
        usd = ti / 1e6 * P_IN + to / 1e6 * P_OUT
        usd33 = ti / 1e6 * P_IN33 + to / 1e6 * P_OUT33
        nq = len({r.get("question_id") for r in rows})
        print(f"| {name} | `{rel}` | {len(rows)} | {nq} | {store} | {ts(p.stat().st_mtime)} | "
              f"{ti:,} | {to:,} | ${usd:.3f} | ${usd33:.3f} | {lat / 3600:.2f} |")
    print(f"\n读者侧合计:in {tot_in:,.0f} / out {tot_out:,.0f} tok = "
          f"**${tot_in / 1e6 * P_IN + tot_out / 1e6 * P_OUT:.3f}**(haiku $1.00/M in、$5.00/M out)"
          f" = ${tot_in / 1e6 * P_IN33 + tot_out / 1e6 * P_OUT33:.3f}(旧口径 $0.80/$4.00);"
          f"判官 claude-opus-5 另计(usage 不落盘,见 environment-limits)")

    print("\n### 跑臂命令行(scratchpad/b35/resilient.sh,单写者;lb_reader_arm.py 以 "
          "`open(out,'a')` 追加并跳过已有 question_id,故重跑=续跑)\n")
    print("```")
    print("direct    : PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python -u scripts/lb_reader_arm.py \\\n"
          "            --reader anthropic:claude-haiku-4-5 --arm direct \\\n"
          "            --data data/wikistate_full_ALL_v25.json \\\n"
          "            --questions results/b35_questions_sample36.jsonl --out results/b35_direct.jsonl")
    print("smoc      : PYTHONUTF8=1 python -u scripts/lb_reader_arm.py \\\n"
          "            --reader anthropic:claude-haiku-4-5 --arm smoc --cards-dir results/wt_cards_v46 \\\n"
          "            --data data/wikistate_full_ALL_v25.json \\\n"
          "            --questions results/b35_questions_sample36.jsonl --out results/b35_smoc.jsonl")
    print("compile_k : PYTHONUTF8=1 QVF_CARDS_KEYED=results/wt_cards_v46k QVF_EMPTY_EVIDENCE_DIRECT=1 "
          "QVF_TENURE_ASOF=1 \\\n            python -u scripts/complex_query_arm.py \\\n"
          "            --data data/wikistate_full_ALL_v25.json \\\n"
          "            --questions results/b35_questions_sample36.jsonl --out results/b35_compile_k.jsonl --resume")
    print("```")

    print("\n### 车道时间线(scratchpad/b35/lane_*.log)\n")
    for lane in ("direct", "compile_k", "smoc"):
        lg = ROOT / f"scratchpad/b35/lane_{lane}.log"
        if lg.exists():
            txt = [x for x in lg.read_text(encoding="utf-8", errors="replace").splitlines()
                   if x.strip() and not x.startswith("scratchpad/")]
            print(f"- **{lane}**: " + " / ".join(txt))

    print("\n### 对照(批 33-A,v2.4 语料 × v45/v45k 店)\n")
    for rel in ("results/b33A_direct.jsonl", "results/b33A_compile_k.jsonl",
                "results/b33A_smoc_v45.jsonl"):
        p = ROOT / rel
        if not p.exists():
            print(f"- `{rel}`: **缺失**")
            continue
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        qs = {json.loads(l)["qid"] for l in open(ROOT / QUESTIONS, encoding="utf-8") if l.strip()}
        cov = len(qs & {r.get("question_id") for r in rows})
        print(f"- `{rel}`: {len(rows)} 行,唯一 qid {len({r.get('question_id') for r in rows})},"
              f"mtime {ts(p.stat().st_mtime)},覆盖本批 140 题中的 {cov} 题")


if __name__ == "__main__":
    main()
