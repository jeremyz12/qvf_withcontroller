# -*- coding: utf-8 -*-
"""批 33-I 统计与成本汇总($0,纯归档复算)。

配对精确符号检验(= 精确 McNemar)、簇自助 95% CI、逐题美元成本。
价格口径(与 scripts/cost_usd_recompute.py 同):haiku-4-5 in $1.00/M、out $5.00/M;
判官 claude-opus-5 in $5.00/M、out $25.00/M;OpenAI text-embedding-3-small $0.02/M。
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
P_IN, P_OUT = 1.00, 5.00
J_IN, J_OUT = 5.00, 25.00
SEED = 20260902
N_BOOT = 10000


def load(p):
    rows = []
    fp = ROOT / p
    if not fp.exists():
        return rows
    for l in open(fp, encoding="utf-8"):
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return rows


def key(qid: str) -> str:
    """账目臂 id 带 _<dim>_query 后缀,direct 臂用裸 question_id。"""
    for suf in ("_query",):
        if qid.endswith(suf):
            qid = qid[: -len(suf)]
            qid = qid.rsplit("_", 1)[0]
    return qid


def sign_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def boot_ci(pairs, n_boot=N_BOOT, seed=SEED):
    rnd = random.Random(seed)
    n = len(pairs)
    if n == 0:
        return (float("nan"), float("nan"))
    ds = []
    for _ in range(n_boot):
        s = [pairs[rnd.randrange(n)] for _ in range(n)]
        ds.append(100.0 * (sum(a for a, _ in s) - sum(b for _, b in s)) / n)
    ds.sort()
    return (ds[int(0.025 * n_boot)], ds[int(0.975 * n_boot)])


def usd_reader(rows):
    ti = sum(r.get("usage_input_tokens", 0) or 0 for r in rows)
    to = sum(r.get("usage_output_tokens", 0) or 0 for r in rows)
    return ti / 1e6 * P_IN + to / 1e6 * P_OUT, ti, to


def usd_judge(rows):
    ji = sum(r.get("judge_input_tokens", 0) or 0 for r in rows)
    jo = sum(r.get("judge_output_tokens", 0) or 0 for r in rows)
    return ji / 1e6 * J_IN + jo / 1e6 * J_OUT, ji, jo


def compare(name, test_rows, base_rows):
    """三种连接键各试一次,取匹配最多的那一种(MAB 两臂 id 同形,LME
    账目臂 id 带 _<dim>_query 后缀而 direct 臂用裸 question_id)。"""
    ident = lambda x: x  # noqa: E731
    best = None
    for kt, kb, tag in ((ident, ident, "raw"), (key, ident, "strip-test"),
                        (ident, key, "strip-base")):
        t = {kt(r["question_id"]): bool(r.get("judge_correct"))
             for r in test_rows}
        b = {kb(r["question_id"]): bool(r.get("judge_correct"))
             for r in base_rows}
        n = len(set(t) & set(b))
        if best is None or n > best[0]:
            best = (n, t, b, tag)
    _, t, b, tag = best
    ks = sorted(set(t) & set(b))
    name = f"{name} join={tag}"
    pairs = [(t[k], b[k]) for k in ks]
    w = sum(1 for x, y in pairs if x and not y)
    l = sum(1 for x, y in pairs if y and not x)
    ties = len(pairs) - w - l
    at = 100.0 * sum(1 for x, _ in pairs if x) / max(len(pairs), 1)
    ab = 100.0 * sum(1 for _, y in pairs if y) / max(len(pairs), 1)
    lo, hi = boot_ci(pairs)
    print(f"[{name}] n_paired={len(pairs)} test={at:.2f} base={ab:.2f} "
          f"delta={at-ab:+.2f}pp W/L/T={w}/{l}/{ties} "
          f"sign_p={sign_p(w, l):.4g} boot95=[{lo:+.2f},{hi:+.2f}]")
    return dict(n=len(pairs), acc_test=at, acc_base=ab, delta=at - ab,
                w=w, l=l, t=ties, p=sign_p(w, l), ci=(lo, hi))


def summarize(tag, rows, label=""):
    if not rows:
        print(f"[{tag}] MISSING")
        return
    n = len(rows)
    acc = 100.0 * sum(1 for r in rows if r.get("judge_correct")) / n
    ru, ti, to = usd_reader(rows)
    ju, ji, jo = usd_judge(rows)
    lat = st.mean(r.get("latency_s", 0) or 0 for r in rows)
    print(f"[{tag}] n={n} acc={acc:.2f} in/q={ti/n:.0f} out/q={to/n:.0f} "
          f"read$/q={ru/n:.5f} judge$/q={ju/n:.5f} lat={lat:.1f}s {label}")


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        parts = spec.split("::")
        if parts[0] == "sum":
            summarize(parts[1], load(parts[2]))
        elif parts[0] == "cmp":
            compare(parts[1], load(parts[2]), load(parts[3]))
