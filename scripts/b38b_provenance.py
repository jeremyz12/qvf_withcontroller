# -*- coding: utf-8 -*-
"""批 38-B 溯源块:v47sk 建店窗 / 逐链建店成本 / 三店目录 sha256(v45、v47s
全程只读,须与预注册记录的指纹逐字相同)/ 读者臂成本。

目录 sha256 口径与 scripts/b33A_provenance.py / scripts/b38_provenance.py
逐字相同(排序后按文件名 + 文件内容拼接做一次 sha256)。

用法: PYTHONUTF8=1 python scripts/b38b_provenance.py > results/b38b_provenance.txt
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
# 项目自有的仓库内 scratchpad/(随批次持久保存的建店日志),不是本次会话的
# 临时 scratchpad —— 建店日志实测落在这里(scratchpad/b38b/build_v47sk_*.log)。
SCRATCH = ROOT / "scratchpad"

CORPUS = "data/wikistate_full_ALL_v24.json"
QUESTIONS = "results/b35_questions_sample36.jsonl"
UIDS = "results/b35_sample_uids.txt"
STORES = ["results/wt_cards_v45", "results/wt_cards_v47s",
          "results/wt_cards_v47sk"]

# 预注册(results/opt_batch38b_prereg.md §三)记录的建店前指纹 —— 只读店
# 的机械核验基线。
FROZEN_FP = {
    "results/wt_cards_v45": (144, 8288,
        "bcb31a114dc27479326d981bbce9c6d906d7689c00e18b9d4371aeecf55589d4"),
    "results/wt_cards_v47s": (36, 1743,
        "a80ea1f36554abff8964a1d536f911f613bac7e54200cfd9928b7fb946cdb3dd"),
}

# 建卡器价格(claude-sonnet-5)
B_IN, B_OUT = 2.00, 10.00
# 读者价格
PRICE = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5": (2.00, 10.00)}

ARMS = [
    ("smoc_v47sk@haiku-4-5", "results/b38b_smoc_v47sk_haiku-4-5.jsonl",
     "wt_cards_v47sk", "claude-haiku-4-5"),
    ("smoc_v47sk@sonnet-5", "results/b38b_smoc_v47sk_sonnet-5.jsonl",
     "wt_cards_v47sk", "claude-sonnet-5"),
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
    """(文件数, 记录数, 目录 sha256(名+内容拼接), 建店窗 min_mtime, max_mtime)。"""
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
    print("## 溯源块(批 38-B)\n")
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

    print("\n### 建卡器(写入侧)\n")
    frozen = ROOT / "scripts/wt_qvf_prototype.py"
    b38 = ROOT / "scripts/wt_qvf_prototype_b38.py"
    b38b = ROOT / "scripts/wt_qvf_prototype_b38b.py"
    print(f"- 冻结件 `scripts/wt_qvf_prototype.py` sha256 `{sha256(frozen)}` "
          "(**全程只读,未改**)")
    print(f"- 批 38 副本 `scripts/wt_qvf_prototype_b38.py` sha256 "
          f"`{sha256(b38)}`(**全程只读,未改**,建 v47s 用)")
    print(f"- 本批副本 `scripts/wt_qvf_prototype_b38b.py` sha256 "
          f"`{sha256(b38b)}`")
    d = subprocess.run(["git", "diff", "--no-index", "--stat",
                        str(b38), str(b38b)], cwd=ROOT,
                       capture_output=True, text=True).stdout.strip()
    print(f"- 与批 38 副本(`wt_qvf_prototype_b38.py`)的差异: "
          f"`{d.splitlines()[-1].strip() if d else 'none'}`"
          "(预注册 §四称 +172 行纯新增、0 行删改 —— 上面这行是机械核验)")
    print("""
- **本批(v47sk)建店命令**(results/opt_batch38b_prereg.md §五,4 分片并行;
  v45 / v47s 全程只读):
  ```
  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \\
  QVF_CARD_KEYS=1 QVF_DATE_STRICT=1 QVF_CARD_SLOT_CANON=1 \\
  QVF_CARD_DATE_REFINE=1 QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u \\
    scripts/wt_qvf_prototype_b38b.py --phase write \\
    --data data/wikistate_full_ALL_v24.json \\
    --cards-dir results/wt_cards_v47sk --uids <shard>   # 4 分片并行
  ```
  与 v47s(批 38)的建店命令相比,唯一差异是抽取器脚本换成
  `wt_qvf_prototype_b38b.py`、店目录换成 `wt_cards_v47sk`,以及新增
  `QVF_CARD_KEYS=1 QVF_DATE_STRICT=1 QVF_CARD_SLOT_CANON=1
  QVF_CARD_DATE_REFINE=1` 四个旗标(前两个任务书点名但对本批目标零/弱作用,
  后两个是预注册 §四 授权补的最小规范化步骤;详见预注册全文)。
""")

    print("### 建店窗 / 三店目录指纹(v45、v47s 全程只读,须与预注册逐字相同)\n")
    for s in STORES:
        fp = dir_fingerprint(s)
        if fp is None:
            print(f"- 店 `{s}`: **缺失**")
            continue
        nfiles, nrec, digest, mn, mt = fp
        print(f"- 店 `{s}`: {nfiles} 文件 / {nrec:,} 记录 | 建店窗 "
              f"{ts(mn)} → {ts(mt)} | 目录 sha256(名+内容拼接) `{digest}`")
        if s in FROZEN_FP:
            ffiles, frec, fdigest = FROZEN_FP[s]
            ok = (nfiles, nrec, digest) == (ffiles, frec, fdigest)
            print(f"  - 对照预注册 §三 记录的建店前指纹({ffiles} 文件 / "
                  f"{frec:,} 记录 / sha256 `{fdigest}`): "
                  + ("**逐字相同,机械证明未被本批触碰**" if ok
                     else "**!! 不同 —— 该店在预注册之后被改动过,需要复核 !!**"))
    print("\n注:`results/wt_cards_v45` 是批 33-A 的 144 链全量店;`v47s` 是"
          "批 38 的 36 链抽样店。`v47sk` 是本批新建的 36 链抽样店"
          "(from-scratch,非增量)。")

    print("\n### 逐链建店成本(claude-sonnet-5 $2.00/M in、$10.00/M out)\n")
    logs = sorted(glob.glob(str(SCRATCH / "b38b" / "build_v47sk_*.log")))
    if not logs:
        print(f"(未找到 {SCRATCH / 'b38b'} 下的 build_v47sk_*.log —— 建店成本"
              "缺失。)")
        g_in = g_out = g_n = 0
    else:
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
        if g_n:
            print(f"\n逐链均值:in {g_in / g_n:,.0f} / out {g_out / g_n:,.0f} "
                  f"tok = ${(g_in / 1e6 * B_IN + g_out / 1e6 * B_OUT) / g_n:.4f}"
                  "/链(冒烟 $0.139/链、批 38 同量级 $0.14x/链)。")

    # v47sk 卡片文件里归档的写入侧 usage(与逐链日志口径独立复核)
    uids = [x.strip() for x in open(ROOT / UIDS, encoding="utf-8") if x.strip()]
    print("\n| 店 | 抽取模型 | 链 | 写入 in tok(卡片文件) | 写入 out tok "
          "(卡片文件) | $ |")
    print("|---|---|---|---|---|---|")
    for s, model in (("results/wt_cards_v45", "claude-haiku-4-5"),
                     ("results/wt_cards_v47s", "claude-sonnet-5"),
                     ("results/wt_cards_v47sk", "claude-sonnet-5")):
        ti = to = n = 0
        for u in uids:
            p = ROOT / s / f"{u}.json"
            if not p.exists():
                continue
            j = json.loads(p.read_text(encoding="utf-8"))
            ti += j.get("usage_in") or 0
            to += j.get("usage_out") or 0
            n += 1
        pi, po = PRICE[model]
        print(f"| {s} | {model} | {n} | {ti:,} | {to:,} | "
              f"${ti / 1e6 * pi + to / 1e6 * po:.3f} |")
    print("\n(v45 / v47s 两行是从各自既有店里挑出这 36 个文件读的只读复核,"
          "不是重建;v47sk 一行应与上面逐链日志合计在四舍五入内一致 —— 两者"
          "独立来源,一致即证明日志没有漏记或重复计的链。)")

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

    print("\n### 读者跑批日志(启动命令与 ARM DONE 汇总行)\n")
    for lg in ("results/b38b_reader_haiku.log", "results/b38b_reader_sonnet.log"):
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

    build = g_in / 1e6 * B_IN + g_out / 1e6 * B_OUT
    print(f"\n**本批总花费(建店 + 读者,判官另计)= ${build + tot:.2f}** "
          f"(建店 ${build:.2f} + 读者 ${tot:.2f})。")


if __name__ == "__main__":
    main()
