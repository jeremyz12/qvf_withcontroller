# -*- coding: utf-8 -*-
"""批 38-E 溯源块:derived 店 results/wt_cards_v47skf 的构建方式(离线过滤,
零 API 调用)/ 三只读店(v45、v47s、v47sk)全程未被本批触碰 / 读者臂成本与
运行时窗。

目录 sha256 口径与 scripts/b38b_provenance.py 逐字相同(排序后按文件名 +
文件内容拼接做一次 sha256)。

用法: PYTHONUTF8=1 python scripts/b38e_provenance.py > results/b38e_provenance.txt
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
STORES = ["results/wt_cards_v45", "results/wt_cards_v47s",
          "results/wt_cards_v47sk", "results/wt_cards_v47skf"]

# 批 38-B 建店后记录的指纹(results/b38b_provenance.txt)—— v45/v47s/v47sk
# 三店本批全程只读,须与这三行逐字相同。
FROZEN_FP = {
    "results/wt_cards_v45": (144, 8288,
        "bcb31a114dc27479326d981bbce9c6d906d7689c00e18b9d4371aeecf55589d4"),
    "results/wt_cards_v47s": (36, 1743,
        "a80ea1f36554abff8964a1d536f911f613bac7e54200cfd9928b7fb946cdb3dd"),
    "results/wt_cards_v47sk": (36, 1639,
        "2b96697d10fd715712ba56499cfa83ff24011b229659548210e0963a06add131"),
}

PRICE = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5": (2.00, 10.00)}

ARMS = [
    ("smoc_v47skf@haiku-4-5 (mt800)",
     "results/b38e_smoc_v47skf_haiku-4-5.jsonl", "wt_cards_v47skf",
     "claude-haiku-4-5"),
    ("smoc_v47skf@haiku-4-5 (mt4000 capped-row correction)",
     "results/b38e_smoc_v47skf_haiku-4-5_mt4000.jsonl", "wt_cards_v47skf",
     "claude-haiku-4-5"),
    ("smoc_v47skf@sonnet-5 (mt4000)",
     "results/b38e_smoc_v47skf_sonnet-5.jsonl", "wt_cards_v47skf",
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
    print("## 溯源块(批 38-E)\n")
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

    print("\n### 建店方式(离线,零 API 调用)\n")
    b = ROOT / "scripts/b38e_build_v47skf.py"
    print(f"- `scripts/b38e_build_v47skf.py` sha256 `{sha256(b)}` —— 对 "
          "results/wt_cards_v47sk 的 36 条链逐卡应用批 38-D 的 "
          "assertion_type() 规则(逐字复制自会话 scratchpad b38d_filter.py，"
          "见该文件顶部注释),丢弃 plan/task/other_person/restate 四类，"
          "保留 start+unknown；不调用任何模型 API。")
    print("- 命令: `PYTHONUTF8=1 python scripts/b38e_build_v47skf.py`")
    flog = ROOT / "results/b38e_filter_log.json"
    if flog.exists():
        j = json.loads(flog.read_text(encoding="utf-8"))
        print(f"- `results/b38e_filter_log.json`: dropped={j['dropped_total']} "
              f"kept={j['kept_total']} (census={j['census_all_records_36_chains']})")
        hc_a = j["hard_constraint_gold_anchor_check_a_index"]
        hc_b = j["hard_constraint_gold_anchor_check_b_span_text"]
        print(f"- 硬约束(a) 命中索引翻转检查: {hc_a['lost']} / "
              f"{hc_a['gold_rows_total_36_chains']} 金标行被误删")
        print(f"- 硬约束(b) span 文本二次核验: {len(hc_b['flagged'])} 条被标记")

    print("\n### 建店窗 / 四店目录指纹(v45、v47s、v47sk 全程只读,须与批 "
          "38-B 记录的指纹逐字相同)\n")
    for s in STORES:
        fp = dir_fingerprint(s)
        if fp is None:
            print(f"- 店 `{s}`: **缺失**")
            continue
        nfiles, nrec, digest, mn, mt = fp
        print(f"- 店 `{s}`: {nfiles} 文件 / {nrec:,} 记录 | 目录 mtime 窗 "
              f"{ts(mn)} → {ts(mt)} | 目录 sha256(名+内容拼接) `{digest}`")
        if s in FROZEN_FP:
            ffiles, frec, fdigest = FROZEN_FP[s]
            ok = (nfiles, nrec, digest) == (ffiles, frec, fdigest)
            print(f"  - 对照批 38-B 记录的指纹({ffiles} 文件 / {frec:,} 记录 "
                  f"/ sha256 `{fdigest}`): "
                  + ("**逐字相同,机械证明未被本批触碰**" if ok
                     else "**!! 不同 —— 该店在批 38-B 之后被改动过,需要复核 !!**"))
    print("\n注:`wt_cards_v47skf` 是本批新建的 derived 店(36 链,从 "
          "`wt_cards_v47sk` 离线过滤而来,非增量、非重新抽取)。")

    print("\n### 读者臂运行时窗 / 行数 / 成本\n")
    print("| 臂 | 产物 | 行数 | 去重后 qid 数 | 店 | 读者 | 文件 mtime | "
          "in tok | out tok | $ | 累计延迟 h |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    tot = 0.0
    for name, rel, store, model in ARMS:
        p = ROOT / rel
        if not p.exists():
            print(f"| {name} | `{rel}` | **缺失** | | {store} | {model} | "
                  "— | — | — | — | — |")
            continue
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        uniq = len({r.get("question_id") for r in rows})
        ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
        to = sum(r.get("usage_output_tokens") or 0 for r in rows)
        lat = sum(r.get("latency_s") or 0 for r in rows)
        pi, po = PRICE[model]
        usd = ti / 1e6 * pi + to / 1e6 * po
        tot += usd
        print(f"| {name} | `{rel}` | {len(rows)} | {uniq} | {store} | "
              f"{model} | {ts(p.stat().st_mtime)} | {ti:,} | {to:,} | "
              f"${usd:.3f} | {lat / 3600:.2f} |")
    print(f"\n**读者臂总花费(建店零花费,判官另计)= ${tot:.3f}**")

    print("\n### 读者跑批日志(启动命令与 ARM DONE 汇总行)\n")
    for lg in ("results/b38e_reader_haiku.log", "results/b38e_reader_sonnet.log",
              "results/b38e_reader_haiku_mt4000.log"):
        p = ROOT / lg
        if not p.exists():
            print(f"- `{lg}`: 缺失")
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        head = lines[0] if lines else ""
        done = [l for l in lines if l.startswith("B36B ARM DONE")]
        print(f"- `{lg}` (mtime {ts(p.stat().st_mtime)}): `{head}`")
        for l in done:
            print(f"  - `{l}`")

    print(f"\n**本批总花费(建店 $0.00 + 读者,判官另计)= ${tot:.2f}**")


if __name__ == "__main__":
    main()
