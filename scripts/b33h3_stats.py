# -*- coding: utf-8 -*-
"""33-H3 统计:Letta 式文件系统 agent(60 题标定场)acc / CI / 成本 / 延迟,
并与同 60 题上的既有臂做配对比较(McNemar 精确符号检验 + 簇自助 CI)。

价格口径(项目冻结):haiku-4-5 读者 $1.00/M in、$5.00/M out;
判官 claude-opus-5 $5.00/M in、$25.00/M out(本表按各考生惯例不计入 $/题)。
用法: python scripts/b33h3_stats.py
"""
from __future__ import annotations

import json
import random
import statistics as st
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
P_IN, P_OUT = 1.00, 5.00
SEED = 20260803
N_BOOT = 10000

MAIN = "results/wsc_s5_lettafs.jsonl"
PEERS = [
    ("QVF smoc(账目)", "results/wsc_s5_smoc.jsonl"),
    ("QVF filter-only", "results/wsc_s5_filter_only.jsonl"),
    ("稠密直读 top-10", "results/wsc_direct_s5_all_b1_union.jsonl"),
    ("timeline", "results/wsc_s5_timeline.jsonl"),
    ("lgstore", "results/wsc_s5_lgstore.jsonl"),
    ("txtai", "results/wsc_s5_txtai.jsonl"),
    ("cognee", "results/wsc_s5_cognee.jsonl"),
    ("A-MEM", "results/wsc_s5_amem.jsonl"),
    ("LangMem", "results/wsc_s5_langmem.jsonl"),
    ("Mem0", "results/wsc_s5_mem0.jsonl"),
    ("摘要 RAG", "results/wsc_s5_sumrag.jsonl"),
    ("obs-RAG", "results/wsc_s5_obsrag.jsonl"),
    ("BM25", "results/wsc_s5_bm25.jsonl"),
    ("盖章台账", "results/wsc_s5_mstrata.jsonl"),
]


def load(p):
    f = ROOT / p
    if not f.exists():
        return {}
    out = {}
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        qid = r.get("question_id") or r.get("qid")
        if qid:
            out[qid] = r
    return out


def uid_of(r, qid):
    return r.get("uid") or qid.rsplit("_", 1)[0]


def boot_ci(vals, rnd, cluster=None):
    """vals: list of 0/1. cluster: parallel list of cluster keys or None."""
    if cluster is None:
        n = len(vals)
        b = []
        for _ in range(N_BOOT):
            s = sum(vals[rnd.randrange(n)] for _ in range(n))
            b.append(100 * s / n)
    else:
        groups = defaultdict(list)
        for v, c in zip(vals, cluster):
            groups[c].append(v)
        keys = list(groups)
        b = []
        for _ in range(N_BOOT):
            s = []
            for _ in range(len(keys)):
                s += groups[keys[rnd.randrange(len(keys))]]
            b.append(100 * sum(s) / len(s))
    b.sort()
    return round(b[int(0.025 * N_BOOT)], 1), round(b[int(0.975 * N_BOOT)], 1)


def sign_test(a, b):
    """Exact two-sided sign test on discordant pairs (McNemar exact)."""
    n01 = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)
    n10 = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    n = n01 + n10
    if n == 0:
        return 1.0, n10, n01
    k = min(n01, n10)
    p = sum(comb(n, i) for i in range(k + 1)) / (2 ** n) * 2
    return min(1.0, p), n10, n01


def paired_boot(delta_pairs, clusters, rnd):
    groups = defaultdict(list)
    for d, c in zip(delta_pairs, clusters):
        groups[c].append(d)
    keys = list(groups)
    b = []
    for _ in range(N_BOOT):
        s = []
        for _ in range(len(keys)):
            s += groups[keys[rnd.randrange(len(keys))]]
        b.append(100 * sum(s) / len(s))
    b.sort()
    return round(b[int(0.025 * N_BOOT)], 1), round(b[int(0.975 * N_BOOT)], 1)


def main():
    main_rows = load(MAIN)
    qids = sorted(main_rows)
    print(f"# 33-H3 Letta 式文件系统 agent — n={len(qids)}\n")

    ys = [1 if main_rows[q].get("judge_correct") else 0 for q in qids]
    uids = [uid_of(main_rows[q], q) for q in qids]
    acc = 100 * sum(ys) / len(ys)
    rnd = random.Random(SEED)
    ci_item = boot_ci(ys, random.Random(SEED))
    ci_clu = boot_ci(ys, random.Random(SEED), cluster=uids)
    print(f"acc = {acc:.2f}  ({sum(ys)}/{len(ys)})")
    print(f"  题级 bootstrap 95% CI = {ci_item}   (与 sys16 表同法)")
    print(f"  簇级(15 uid)bootstrap 95% CI = {ci_clu}   (prereg 判据 H)")

    # per type
    agg = defaultdict(lambda: [0, 0])
    for q in qids:
        r = main_rows[q]
        a = agg[r["question_type"]]
        a[0] += 1
        a[1] += 1 if r.get("judge_correct") else 0
    print("\n## 逐题型")
    for k in sorted(agg):
        n, c = agg[k]
        print(f"  {k:16s} n={n} acc={100*c/n:5.1f}")

    # cost / latency
    ti = [main_rows[q]["usage_input_tokens"] for q in qids]
    to = [main_rows[q]["usage_output_tokens"] for q in qids]
    lat = [main_rows[q]["latency_s"] for q in qids]
    rounds = [main_rows[q]["agent_rounds"] for q in qids]
    grep = [main_rows[q]["tool_grep"] for q in qids]
    read = [main_rows[q]["tool_read"] for q in qids]
    ingest = {uid_of(main_rows[q], q): main_rows[q]["ingest_seconds"]
              for q in qids}
    usd_q = (st.mean(ti) / 1e6 * P_IN + st.mean(to) / 1e6 * P_OUT)
    print("\n## 成本 / 延迟(读者侧 haiku-4-5,判官另计)")
    print(f"  in-tok 均 {st.mean(ti):.0f}  中位 {st.median(ti):.0f}  "
          f"max {max(ti)}")
    print(f"  out-tok 均 {st.mean(to):.0f}")
    print(f"  总 token in={sum(ti)} out={sum(to)}  "
          f"总额 ${sum(ti)/1e6*P_IN + sum(to)/1e6*P_OUT:.3f}")
    print(f"  $/题 = ${usd_q:.5f}")
    print(f"  延迟中位 {st.median(lat):.2f}s  均 {st.mean(lat):.2f}s")
    print(f"  agent 轮次 均 {st.mean(rounds):.2f}  "
          f"grep 次 均 {st.mean(grep):.2f}  read 次 均 {st.mean(read):.2f}")
    print(f"  建库(落盘,零 LLM/零嵌入)= {sum(ingest.values()):.3f}s / "
          f"{len(ingest)} 库 = {st.mean(list(ingest.values()))*1000:.1f} ms/库")

    print("\n## 同 60 题配对比较(McNemar 精确 + 簇自助 CI on Δ)")
    print("| 对手 | 对手 acc | Δ(lettafs − 对手) | 精确 p | 赢/输 | 簇 CI |")
    print("|---|---|---|---|---|---|")
    for label, path in PEERS:
        rows = load(path)
        common = [q for q in qids if q in rows]
        if len(common) < len(qids):
            note = f" [仅 {len(common)}/60 可配对]"
        else:
            note = ""
        if not common:
            print(f"| {label} | 缺文件 | — | — | — | — |")
            continue
        a = [1 if main_rows[q].get("judge_correct") else 0 for q in common]
        b = [1 if (rows[q].get("judge_correct") or rows[q].get("correct"))
             else 0 for q in common]
        cl = [uid_of(main_rows[q], q) for q in common]
        p, win, lose = sign_test(a, b)
        d = [x - y for x, y in zip(a, b)]
        ci = paired_boot(d, cl, random.Random(SEED))
        print(f"| {label}{note} | {100*sum(b)/len(b):.2f} | "
              f"{100*sum(d)/len(d):+.2f} | {p:.4f} | {win}/{lose} | "
              f"[{ci[0]:+.1f}, {ci[1]:+.1f}] |")


if __name__ == "__main__":
    main()
