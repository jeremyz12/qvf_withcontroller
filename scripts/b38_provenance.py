# -*- coding: utf-8 -*-
"""批 38 溯源块:v47s 建店窗 / 逐链建店成本 / 目录 sha256 / 读者臂成本。

目录 sha256 口径与 scripts/b33A_provenance.py 逐字相同(排序后按
文件名 + 文件内容拼接做一次 sha256)。

用法: PYTHONUTF8=1 python scripts/b38_provenance.py > results/b38_provenance.txt
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
QUESTIONS = "results/b35_questions_sample36.jsonl"
UIDS = "results/b35_sample_uids.txt"
STORES = ["results/wt_cards_v45", "results/wt_cards_v47s"]

# 建卡器价格(claude-sonnet-5)
B_IN, B_OUT = 2.00, 10.00
# 读者价格
PRICE = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5": (2.00, 10.00)}

ARMS = [
    ("smoc_v47s@haiku-4-5", "results/b38_smoc_v47s_haiku-4-5.jsonl",
     "wt_cards_v47s", "claude-haiku-4-5"),
    ("smoc_v47s@sonnet-5", "results/b38_smoc_v47s_sonnet-5.jsonl",
     "wt_cards_v47s", "claude-sonnet-5"),
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
    print("## 溯源块(批 38)\n")
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
    print(f"- 冻结件 `scripts/wt_qvf_prototype.py` sha256 `{sha256(frozen)}` "
          "(**全程只读,未改**)")
    print(f"- 本批副本 `scripts/wt_qvf_prototype_b38.py` sha256 "
          f"`{sha256(b38)}`")
    d = subprocess.run(["git", "diff", "--no-index", "--stat",
                        str(frozen), str(b38)], cwd=ROOT,
                       capture_output=True, text=True).stdout.strip()
    print(f"- 与冻结件差异: `{d.splitlines()[-1].strip() if d else 'none'}`")
    print("""
- **v45(批 33-A,对照店)建店命令**(自 results/opt_batch33_A_rebuild_verdict.md
  §九 与 scripts/b35_provenance.py:118 逐字复核):
  ```
  QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype.py \\
    --phase write --data data/wikistate_full_ALL_v24.json \\
    --cards-dir results/wt_cards_v45 --uids <shard>
  ```
  抽取模型 = 脚本内建常量 `MODEL = "claude-haiku-4-5"`(`QVF_CARD_MODEL` 未设,
  `_CARD_MODEL` 回落到 MODEL);`QVF_CARD_TEMP0` 默认 1 → 发 `temperature=0.0`;
  `max_tokens=16000`;其余建卡旗标全默认(KEYS/TAGS/V5/STRICT/ABS_DATE/
  RENUMBER/VERIFY_SPAN/FAIL_LOUD/INCR/BY_SESSION 全 0)。

- **v47s(本批)建店命令**:
  ```
  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \\
  QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_b38.py \\
    --phase write --data data/wikistate_full_ALL_v24.json \\
    --cards-dir results/wt_cards_v47s --uids <shard>   # 4 分片并行
  ```
  与 v45 的差异**只有三处**,逐条理由:
  1. `QVF_CARD_MODEL=claude-sonnet-5` —— 本批的自变量。
  2. **不发 `temperature`**。claude-sonnet-5 已移除采样参数,发送必 400
     (实测 `400 invalid_request_error: \\`temperature\\` is deprecated for this
     model.`)。闸写在 `_card_wants_temperature()`,**只对不接受该参数的模型
     生效**:传 claude-haiku-4-5 时仍发 `temperature=0.0`,与冻结件逐字节同。
     批 36-B 已在读者侧确认同一 API 行为。
  3. `QVF_CARD_THINKING=off` → 显式 `thinking={"type":"disabled"}`。
     **理由(必须照实读)**:sonnet-5 默认开自适应思考,而 `max_tokens` 同时
     封顶「思考 + 可见文本」。用默认设定实测(见 `build_v47s_smoke.log`):
     首次调用在 `max_tokens=16000` 上被截断 → `messages.parse` 解析失败 →
     `_catalog()` 对半分批,同一条链被拆成两次互不可见的抽取,与 v45 的
     「一链一次调用」**不同构**;且被截断那次的 token 白烧却不进 usage 统计。
     关掉思考后:一链一次调用、`stop_reason=end_turn`、`max_tokens` 保持
     16000 不变。这同时也让写入侧调用与 v45 **同构**——v45 的
     claude-haiku-4-5 不配 `budget_tokens` 本就零思考,故两店都是"零思考抽取,
     只有模型不同"。**代价照实记:本批没有测「sonnet-5 + 思考」的抽取上限**
     (预算 $10 封顶,默认设定实测约 $0.26/链 × 36 ≈ $9.4,加读者会超顶)。
""")

    print("### 建店窗 / 目录指纹\n")
    for s in STORES:
        d = ROOT / s
        fs = sorted(d.glob("*.json"))
        if not fs:
            print(f"- 店 `{s}`: **缺失**")
            continue
        mt = max(f.stat().st_mtime for f in fs)
        mn = min(f.stat().st_mtime for f in fs)
        cat = hashlib.sha256()
        nrec = 0
        for f in fs:
            cat.update(f.name.encode())
            cat.update(f.read_bytes())
            nrec += len(json.loads(f.read_text(encoding="utf-8"))["records"])
        print(f"- 店 `{s}`: {len(fs)} 文件 / {nrec:,} 记录 | 建店窗 "
              f"{ts(mn)} → {ts(mt)} | 目录 sha256(名+内容拼接) "
              f"`{cat.hexdigest()}`")
    print("\n注:`results/wt_cards_v45` 是批 33-A 的 144 链全量店,本批**全程只读**"
          "(上面的 144 文件指纹应与 results/b33A_provenance.txt 逐字相同 —— "
          "这就是「未触碰 v45」的机械证明)。v47s 只建 36 链抽样。")

    print("\n### 逐链建店成本(claude-sonnet-5 $2.00/M in、$10.00/M out)\n")
    logs = sorted(glob.glob(str(SCRATCH / "b38" / "build_v47s_*.log")))
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
        print(f"\n逐链均值:in {g_in / g_n:,.0f} / out {g_out / g_n:,.0f} tok = "
              f"${(g_in / 1e6 * B_IN + g_out / 1e6 * B_OUT) / g_n:.4f}/链。")
    print("\n对照:v45 同 36 条链的 haiku 建店成本无逐链归档"
          "(批 33-A 只留 144 链的分片日志),故不做逐链对照;"
          "两店的 `usage_in`/`usage_out` 字段落在各自卡片文件里,见下表。")

    # 两店同 36 链的写入侧 usage(从卡片文件里读,口径一致)
    uids = [x.strip() for x in open(ROOT / UIDS, encoding="utf-8") if x.strip()]
    print("\n| 店 | 抽取模型 | 链 | 写入 in tok | 写入 out tok | $ |")
    print("|---|---|---|---|---|---|")
    for s, model in (("results/wt_cards_v45", "claude-haiku-4-5"),
                     ("results/wt_cards_v47s", "claude-sonnet-5")):
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
    print("\n(v45 的 36 链 usage 是从 144 链店里挑出这 36 个文件读的,"
          "不是重建;两行价格表不同,故金额不可直接相减比模型贵贱。)")

    print("\n### 读者臂运行时窗 / 成本\n")
    print("| 臂 | 产物 | 行数 | 店 | 读者 | 文件 mtime | in tok | out tok | "
          "$ | 累计延迟 h |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    tot = 0.0
    for name, rel, store, model in ARMS:
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
    build = g_in / 1e6 * B_IN + g_out / 1e6 * B_OUT
    print(f"\n**本批总花费(建店 + 读者,判官另计)= ${build + tot:.2f}** "
          f"(建店 ${build:.2f} + 读者 ${tot:.2f};另有一次被截断的默认设定"
          "冒烟 ≈ $0.35 白烧,见上文第 3 条理由)。")


if __name__ == "__main__":
    main()
