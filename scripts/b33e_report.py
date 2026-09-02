# -*- coding: utf-8 -*-
"""批 33-E 汇总:逐臂准确率 / 逐题型 / 对参照 direct 的配对 McNemar /
token·$·延迟(全部由 usage 字段实测,不估算)。

参照 direct = results/b33_direct_v24oai_shard*.jsonl(同语料 v2.4、同嵌入器
text-embedding-3-small、同读者 haiku-4-5、同判官)。

用法:
  PYTHONUTF8=1 python scripts/b33e_report.py --arm 名称=通配 [--arm ...] [--dev]
"""
from __future__ import annotations

import argparse
import glob
import json
import random
from collections import defaultdict
from math import comb

REF = "results/b33_direct_v24oai_shard*.jsonl"
# 价格($/M):haiku-4-5 读者 1/5;opus-5 判官 5/25;text-embedding-3-small 0.02
P_IN, P_OUT, J_IN, J_OUT = 1.0, 5.0, 5.0, 25.0


def load(spec):
    """spec 可为逗号分隔的多个通配(同一臂分散在多份 jsonl 时用)。"""
    rows = {}
    files = []
    for part in spec.split(","):
        if part.strip():
            files.extend(glob.glob(part.strip()))
    for f in sorted(files):
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                rows[r["question_id"]] = r
    return rows


def mcnemar(b, c):
    """精确二项双尾 p(b,c 为不一致对);b = 参照对而本臂错。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2.0 ** n) * 2
    return min(1.0, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", default=[],
                    help="名称=文件通配(按最后一个 = 切分)")
    ap.add_argument("--ref", default=REF)
    a = ap.parse_args()
    ref = load(a.ref)
    print(f"REF direct n={len(ref)} acc="
          f"{sum(bool(r['judge_correct']) for r in ref.values()) / len(ref) * 100:.2f}")
    print()
    hdr = (f"{'arm':34s} {'n':>4s} {'acc%':>7s} {'Δdirect':>8s} "
           f"{'b/c':>9s} {'p':>9s} {'in tok':>8s} {'out':>6s} "
           f"{'$/题':>8s} {'lat s':>6s} {'reuse':>5s}")
    print(hdr)
    print("-" * len(hdr))
    for spec in a.arm:
        name, pat = spec.rsplit("=", 1)
        rows = load(pat)
        ids = [q for q in rows if q in ref]
        n = len(ids)
        ok = sum(bool(rows[q]["judge_correct"]) for q in ids)
        rok = sum(bool(ref[q]["judge_correct"]) for q in ids)
        b = sum(1 for q in ids if ref[q]["judge_correct"]
                and not rows[q]["judge_correct"])
        c = sum(1 for q in ids if not ref[q]["judge_correct"]
                and rows[q]["judge_correct"])
        ti = sum(rows[q]["usage_input_tokens"] for q in ids)
        to = sum(rows[q]["usage_output_tokens"] for q in ids)
        ji = sum(rows[q].get("judge_input_tokens", 0) or 0 for q in ids)
        jo = sum(rows[q].get("judge_output_tokens", 0) or 0 for q in ids)
        lat = sum(rows[q].get("latency_s", 0) or 0 for q in ids)
        cost = (ti * P_IN + to * P_OUT + ji * J_IN + jo * J_OUT) / 1e6
        reuse = sum(1 for q in ids if rows[q].get("reused_from"))
        # 144 链簇自助 CI(按 uid 重抽,house 协议)
        byu = defaultdict(list)
        for q in ids:
            byu[rows[q]["uid"]].append(
                bool(rows[q]["judge_correct"]) - bool(ref[q]["judge_correct"]))
        uids = list(byu)
        rng = random.Random(20260902)
        boot = []
        for _ in range(2000):
            pick = [byu[rng.choice(uids)] for _ in uids]
            flat = [x for g in pick for x in g]
            boot.append(sum(flat) / len(flat) * 100)
        boot.sort()
        ci = (boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))])
        print(f"{name:34s} {n:4d} {ok / n * 100:7.2f} "
              f"{(ok - rok) / n * 100:+8.2f} {b:4d}/{c:<4d} "
              f"{mcnemar(b, c):9.2e} {ti / n:8.0f} {to / n:6.0f} "
              f"{cost / n:8.5f} {lat / n:6.2f} {reuse:5d}")
        # 逐题型
        byt = defaultdict(lambda: [0, 0, 0])
        for q in ids:
            t = rows[q].get("question_type") or "?"
            byt[t][0] += 1
            byt[t][1] += bool(rows[q]["judge_correct"])
            byt[t][2] += bool(ref[q]["judge_correct"])
        seg = "   ".join(
            f"{t}={v[1] / v[0] * 100:.1f}(ref {v[2] / v[0] * 100:.1f})"
            for t, v in sorted(byt.items()))
        print(f"{'':34s} {seg}")
        # 判官侧成本单列
        print(f"{'':34s} 簇自助 95%CI(Δdirect) = "
              f"[{ci[0]:+.2f}, {ci[1]:+.2f}] pp (144 链簇, 2000 次)")
        print(f"{'':34s} judge {ji / n:.0f}+{jo / n:.0f} tok/题 "
              f"= ${(ji * J_IN + jo * J_OUT) / 1e6 / n:.5f}/题; "
              f"reader ${(ti * P_IN + to * P_OUT) / 1e6 / n:.5f}/题; "
              f"臂总 ${cost:.3f}")


if __name__ == "__main__":
    main()
