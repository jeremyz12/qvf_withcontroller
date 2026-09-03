# -*- coding: utf-8 -*-
"""批 41 溯源块:第二次抽取(results/wt_cards_v47s_pass2)/ 联集+过滤新店
(results/wt_cards_v47skf2)/ 四只读店(v45、v47s、v47sk、v47skf)全程未被
本批触碰 / 读者臂成本与运行时窗。

目录 sha256 口径与 scripts/b38e_provenance.py 逐字相同(排序后按文件名 +
文件内容拼接做一次 sha256)。

用法: PYTHONUTF8=1 python scripts/b41_provenance.py > results/b41_provenance.txt
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")

CORPUS = "data/wikistate_full_ALL_v24.json"
QUESTIONS = "results/b35_questions_sample36.jsonl"
UIDS = "results/b35_sample_uids.txt"

# 批 38-E 建店后记录的指纹(results/b38e_provenance.txt)—— v45/v47s/v47sk/
# v47skf 四店本批全程只读,须与这四行逐字相同。
FROZEN_FP = {
    "results/wt_cards_v45": (144, 8288,
        "bcb31a114dc27479326d981bbce9c6d906d7689c00e18b9d4371aeecf55589d4"),
    "results/wt_cards_v47s": (36, 1743,
        "a80ea1f36554abff8964a1d536f911f613bac7e54200cfd9928b7fb946cdb3dd"),
    "results/wt_cards_v47sk": (36, 1639,
        "2b96697d10fd715712ba56499cfa83ff24011b229659548210e0963a06add131"),
    "results/wt_cards_v47skf": (36, 1436,
        "7a78f9b7ed16cc51809374339b3b59f73b44ed9be8aba2fa7848c78a86fade54"),
}

PRICE = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5": (2.00, 10.00)}

ARMS = [
    ("smoc_v47skf2@haiku-4-5 (mt800)",
     "results/b41_smoc_v47skf2_haiku-4-5.jsonl", "wt_cards_v47skf2",
     "claude-haiku-4-5"),
    ("smoc_v47skf2@sonnet-5 (mt4000)",
     "results/b41_smoc_v47skf2_sonnet-5.jsonl", "wt_cards_v47skf2",
     "claude-sonnet-5"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ts(x: float) -> str:
    return dt.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S")


def dir_fingerprint(rel: str):
    d = ROOT / rel
    fs = sorted(d.glob("*.json"))
    if not fs:
        return None
    cat = hashlib.sha256()
    nrec = 0
    for f in fs:
        cat.update(f.name.encode())
        cat.update(f.read_bytes())
        nrec += len(json.loads(f.read_text(encoding="utf-8"))["records"])
    mt = max(f.stat().st_mtime for f in fs)
    mn = min(f.stat().st_mtime for f in fs)
    return len(fs), nrec, cat.hexdigest(), mn, mt


def main() -> None:
    print("## 溯源块(批 41)\n")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--",
                            "scripts", "qvf"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    print(f"- git rev: `{git}`(本轨道全程未 git add / commit / push)")
    print("- scripts//qvf 工作区改动:"
          + ("无" if not dirty else "\n```\n" + dirty + "\n```"))

    for rel in (CORPUS, QUESTIONS, UIDS):
        p = ROOT / rel
        print(f"- 语料/题源 `{rel}`: sha256 `{sha256(p)}` "
              f"({p.stat().st_size:,} B, mtime {ts(p.stat().st_mtime)})")

    print("\n### 只读店核验(v45 / v47s / v47sk / v47skf 全程未被本批触碰)\n")
    for rel, (fn, fr, fh) in FROZEN_FP.items():
        fp = dir_fingerprint(rel)
        if fp is None:
            print(f"- `{rel}`: 目录不存在或为空!")
            continue
        n, r, h, _mn, _mt = fp
        same = (n, r, h) == (fn, fr, fh)
        print(f"- `{rel}`: {n} 文件 / {r:,} 记录 / sha256 `{h}` — "
              f"对照批 38-E 记录 ({fn} 文件 / {fr:,} 记录 / `{fh}`): "
              f"{'**逐字相同,未被触碰**' if same else '!!! 不同 !!!'}")

    print("\n### 建卡器(写入侧,第二次抽取,3 条链)\n")
    b38 = ROOT / "scripts/wt_qvf_prototype_b38.py"
    print(f"- `scripts/wt_qvf_prototype_b38.py` sha256 `{sha256(b38)}` "
          "(**全程只读,未改**,与建 v47s 用的是同一份文件,本批仅换 "
          "--cards-dir 与 --uids)")
    print("- **本批(v47s_pass2)建店命令**(3 条目标链,单进程串行):")
    print("  ```")
    print("  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 "
          "QVF_CARD_THINKING=off QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u "
          "scripts/wt_qvf_prototype_b38.py --phase write --data "
          "data/wikistate_full_ALL_v24.json --cards-dir "
          "results/wt_cards_v47s_pass2 --uids wikiP39037-Q3525068,"
          "wikiP39006-Q5220520,wikiP39017-Q24568849")
    print("  ```")
    print("  与建 `wt_cards_v47s`(批 38)的命令逐字相同,唯二差异:目标目录、"
          "--uids 收窄到 3 条链。")

    fp = dir_fingerprint("results/wt_cards_v47s_pass2")
    if fp:
        n, r, h, mn, mx = fp
        print(f"\n- 店 `results/wt_cards_v47s_pass2`: {n} 文件 / {r} 记录 | "
              f"建店窗 {ts(mn)} → {ts(mx)} | 目录 sha256 `{h}`")

    print("\n### 逐链建店成本(claude-sonnet-5 $2.00/M in、$10.00/M out,"
          "results/b41_build_pass2.log)\n")
    log = ROOT / "results/b41_build_pass2.log"
    print("| uid | in tok | out tok | $ |")
    print("|---|---|---|---|")
    import re
    tin = tout = 0
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\[(\S+)\] \d+ cards.*in=(\d+) out=(\d+)", line)
            if m:
                uid, i, o = m.group(1), int(m.group(2)), int(m.group(3))
                usd = i / 1e6 * 2.00 + o / 1e6 * 10.00
                tin += i; tout += o
                print(f"| {uid} | {i:,} | {o:,} | ${usd:.3f} |")
    usd_tot = tin / 1e6 * 2.00 + tout / 1e6 * 10.00
    print(f"| **合计** | **{tin:,}** | **{tout:,}** | **${usd_tot:.3f}** |")

    print("\n### 联集 + 过滤建店(results/wt_cards_v47skf2,离线,零 API)\n")
    b41 = ROOT / "scripts/b41_build_v47skf2.py"
    print(f"- `scripts/b41_build_v47skf2.py` sha256 `{sha256(b41)}`")
    fp2 = dir_fingerprint("results/wt_cards_v47skf2")
    if fp2:
        n, r, h, mn, mx = fp2
        print(f"- 店 `results/wt_cards_v47skf2`: {n} 文件 / {r} 记录 | "
              f"建店时刻 {ts(mx)} | 目录 sha256 `{h}`")
    flog = ROOT / "results/b41_filter_log.json"
    if flog.exists():
        d = json.loads(flog.read_text(encoding="utf-8"))
        print(f"- 硬约束(a)金标锚点索引翻转:vs v47sk = "
              f"{d['hard_constraint_gold_anchor_check_a_index']['lost_vs_v47sk']}/"
              f"{d['hard_constraint_gold_anchor_check_a_index']['gold_rows_total_36_chains']}"
              f"; vs v47skf = "
              f"{d['hard_constraint_gold_anchor_check_a_index']['lost_vs_v47skf']}/"
              f"{d['hard_constraint_gold_anchor_check_a_index']['gold_rows_total_36_chains']}")
        print(f"- 硬约束(b)span 文本二次核验被标记数:"
              f"{len(d['hard_constraint_gold_anchor_check_b_span_text']['flagged'])}")
        print(f"- 其余 33 条链字节级等同 v47skf: "
              f"{d['non_target_33_chains_byte_identical_to_v47skf']}")
        print(f"- 联集报告(每条目标链):")
        for uid, rep in d["union_report"].items():
            print(f"  - {uid}: v47sk {rep['v47sk_n']} 张 + pass2 新增 "
                  f"{rep['new_from_pass2']} 张(pass2 原 {rep['pass2_n']} "
                  f"张)= 联集 {rep['union_n']} 张(去重前)")

    print("\n### 读者臂运行时窗 / 成本\n")
    print("| 臂 | 产物 | 行数 | 店 | 读者 | 文件 mtime | in tok | out tok | "
          "$ |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, relpath, cardsdir, model in ARMS:
        p = ROOT / relpath
        if not p.exists():
            continue
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
        to = sum(r.get("usage_output_tokens") or 0 for r in rows)
        pin, pout = PRICE.get(model, (0, 0))
        usd = ti / 1e6 * pin + to / 1e6 * pout
        mt = ts(p.stat().st_mtime)
        print(f"| {name} | `{relpath}` | {len(rows)} | {cardsdir} | {model} "
              f"| {mt} | {ti:,} | {to:,} | ${usd:.3f} |")

    print("\n**本批总花费(建店 pass2 + 联集(离线,$0) + 读者,判官另计)"
          "见 results/b41_score_out.txt §6。**")


if __name__ == "__main__":
    main()
