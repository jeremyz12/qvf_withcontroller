# -*- coding: utf-8 -*-
"""批 46c 记分器:六臂 run1(既有)+ run2(本批新跑)双轮抖动实测。

预注册:results/opt_batch46c_prereg.md(§零已把"再跑两轮"减档为"只补
run2",记录了 $12 预算硬顶 vs $22.36 字面需求的核算与理由)。

本脚本零 API 调用,纯离线记分:
  - 逐臂 run1/run2 准确率、mean、sd(n=2,= |Δ|/√2)、逐题两轮一致率;
  - run-averaged correctness(每题两轮 judge_correct 均值,0/0.5/1)做配对
    符号检验(与仓库既有 sign_p 同源,scripts/b45_score.py 抄一份);
  - H1(逐臂抖动)、H2(haiku 排序,两轮分别判)、H3(sonnet-5 plainctx vs
    ledger,n=2 概要 CI + 140 题 run-averaged 配对符号检验双报);
  - 成本(读者 + 判官,run1 用产物里的 usage token 现算,不查历史文档数字)。

用法: PYTHONUTF8=1 python scripts/b46c_score.py > results/b46c_score_out.txt
"""
from __future__ import annotations

import json
import math
from math import comb
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent.parent

R_PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}
J_PRICES = {"claude-opus-5": (5.0, 25.0)}
J_DEFAULT = (5.0, 25.0)


def r_cost(model, ti, to):
    p = R_PRICES.get(model, (3.0, 15.0))
    return (ti or 0) / 1e6 * p[0] + (to or 0) / 1e6 * p[1]


def j_cost(ti, to):
    p = J_PRICES.get("claude-opus-5", J_DEFAULT)
    return (ti or 0) / 1e6 * p[0] + (to or 0) / 1e6 * p[1]


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def load(path, override=None, keep=None):
    """按 question_id 建索引;override 文件(mt4000 校正)逐题覆盖同 id 行。
    keep: 若给定 qid 集合,只保留该子集(direct 臂 576 行裁到 140 题)。"""
    rows = {}
    for line in open(ROOT / path, encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        if keep is not None and d["question_id"] not in keep:
            continue
        rows[d["question_id"]] = d
    if override:
        for line in open(ROOT / override, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            if keep is not None and d["question_id"] not in keep:
                continue
            rows[d["question_id"]] = d
    return rows


def main():
    qs = [json.loads(l) for l in
          open(ROOT / "results/b35_questions_sample36.jsonl", encoding="utf-8")
          if l.strip()]
    qids = [q["qid"] for q in qs]
    qidset = set(qids)
    qtype = {q["qid"]: q["qtype"] for q in qs}
    print("=" * 78)
    print("批 46c 记分:六臂 run1(既有)+ run2(本批,预算减档 n=2 非 n=3)")
    print("=" * 78)
    print(f"样本:{len(qids)} 题 / {len(set(q['uid'] for q in qs))} 店 "
          f"(results/b35_questions_sample36.jsonl)")

    ARMS = [
        # key, reader, run1(base, override), run2(base, override)
        ("smoc_v47skf2@haiku", "claude-haiku-4-5",
         "results/b41_smoc_v47skf2_haiku-4-5.jsonl", None,
         "results/b46c_smoc_v47skf2_haiku-4-5_run2.jsonl", None),
        ("smoc_v47skf@haiku", "claude-haiku-4-5",
         "results/b38e_smoc_v47skf_haiku-4-5.jsonl", None,
         "results/b46c_smoc_v47skf_haiku-4-5_run2.jsonl", None),
        ("plainctx@haiku", "claude-haiku-4-5",
         "results/b36_plainctx_haiku-4-5.jsonl",
         "results/b36_plainctx_haiku-4-5_mt4000.jsonl",
         "results/b46c_plainctx_haiku-4-5_run2.jsonl",
         "results/b46c_plainctx_haiku-4-5_run2_mt4000.jsonl"),
        ("direct@haiku", "claude-haiku-4-5",
         "results/b33A_direct.jsonl", None,
         "results/b46c_direct_haiku-4-5_run2.jsonl", None),
        ("smoc_v47skf2@sonnet5", "claude-sonnet-5",
         "results/b41_smoc_v47skf2_sonnet-5.jsonl", None,
         "results/b46c_smoc_v47skf2_sonnet-5_run2.jsonl", None),
        ("plainctx@sonnet5", "claude-sonnet-5",
         "results/b36_plainctx_sonnet-5.jsonl",
         "results/b36_plainctx_sonnet-5_mt4000.jsonl",
         "results/b46c_plainctx_sonnet-5_run2.jsonl", None),
    ]

    data = {}  # key -> {"run1": {qid: row}, "run2": {qid: row}}
    cost_rows = {}  # key -> {"run1": (reader$, judge$), "run2": (...)}
    for key, reader, r1b, r1o, r2b, r2o in ARMS:
        keep = qidset if key == "direct@haiku" else None
        run1 = load(r1b, r1o, keep=keep)
        run2 = load(r2b, r2o, keep=keep)
        missing1 = qidset - set(run1)
        missing2 = qidset - set(run2)
        if missing1 or missing2:
            print(f"[WARN] {key}: run1 missing {len(missing1)}, "
                  f"run2 missing {len(missing2)} of {len(qidset)}")
        data[key] = {"run1": run1, "run2": run2}

        def rc(rows):
            rd = jd = 0.0
            for qid, d in rows.items():
                if qid not in qidset:
                    continue
                rd += r_cost(d.get("reader_model", reader),
                             d.get("usage_input_tokens", 0),
                             d.get("usage_output_tokens", 0))
                jd += j_cost(d.get("judge_input_tokens", 0),
                             d.get("judge_output_tokens", 0))
            return rd, jd

        cost_rows[key] = {"run1": rc(run1), "run2": rc(run2)}

    # ── §一 逐臂 mean/sd(n=2)/agreement ──────────────────────────
    print("\n" + "-" * 78)
    print("§一 逐臂:run1 vs run2 准确率、mean±sd(n=2)、两轮一致率")
    print("-" * 78)
    print(f"{'arm':24s} {'run1':>8s} {'run2':>8s} {'mean':>8s} "
          f"{'sd(n=2)':>9s} {'range':>8s} {'agree':>8s}")
    summary = {}
    for key, *_ in ARMS:
        run1, run2 = data[key]["run1"], data[key]["run2"]
        c1 = {q: bool(run1[q]["judge_correct"]) for q in qids}
        c2 = {q: bool(run2[q]["judge_correct"]) for q in qids}
        a1 = 100 * sum(c1.values()) / len(qids)
        a2 = 100 * sum(c2.values()) / len(qids)
        mn = (a1 + a2) / 2
        sd = abs(a1 - a2) / math.sqrt(2)  # sample sd, n=2
        rng = abs(a1 - a2)
        agree = 100 * sum(c1[q] == c2[q] for q in qids) / len(qids)
        summary[key] = dict(a1=a1, a2=a2, mean=mn, sd=sd, range=rng,
                            agree=agree, c1=c1, c2=c2)
        print(f"{key:24s} {a1:7.1f}% {a2:7.1f}% {mn:7.1f}% "
              f"{sd:8.2f}p {rng:7.2f}p {agree:7.1f}%")

    # ── §二 H1 判决 ──────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("§二 H1(逐臂 run-to-run sd,n=2,阈值 ≤2pp / 2-4pp / >4pp)")
    print("-" * 78)
    for key, *_ in ARMS:
        s = summary[key]
        if s["sd"] <= 2.0:
            verdict = "证实(sd<=2pp,比既往'3-4pp'记录的抖动更小)"
        elif s["sd"] <= 4.0:
            verdict = "证实(与既往'3-4pp'经验一致)"
        else:
            verdict = "被否定(实测抖动超过既往'3-4pp'上限)"
        print(f"{key:24s} sd={s['sd']:5.2f}pp (run1={s['a1']:.1f}%, "
              f"run2={s['a2']:.1f}%) -> {verdict}")

    # ── §三 H2 haiku 排序(逐轮分别判) ────────────────────────────
    print("\n" + "-" * 78)
    print("§三 H2 haiku 排序:smoc(ledger) > plainctx > direct,逐轮分别判")
    print("-" * 78)
    for ledger_key in ("smoc_v47skf2@haiku", "smoc_v47skf@haiku"):
        for run in ("run1", "run2"):
            acc = "a1" if run == "run1" else "a2"
            L = summary[ledger_key][acc]
            P = summary["plainctx@haiku"][acc]
            D = summary["direct@haiku"][acc]
            ok = L > P > D
            print(f"ledger={ledger_key:20s} {run}: L={L:.1f}% P={P:.1f}% "
                  f"D={D:.1f}% | order-holds={ok}")
    both_hold_v2 = all(
        summary["smoc_v47skf2@haiku"][acc] > summary["plainctx@haiku"][acc] >
        summary["direct@haiku"][acc] for acc in ("a1", "a2"))
    print(f"\nH2 判决(主口径 ledger=v47skf2,两轮都成立才算证实):"
          f" {'证实' if both_hold_v2 else '被否定'}")

    # ── §四 H3 sonnet-5 plainctx vs smoc_v47skf2 ────────────────
    print("\n" + "-" * 78)
    print("§四 H3 sonnet-5:plainctx - smoc_v47skf2,两条证据线")
    print("-" * 78)
    Ls = summary["smoc_v47skf2@sonnet5"]
    Ps = summary["plainctx@sonnet5"]
    d1 = Ps["a1"] - Ls["a1"]
    d2 = Ps["a2"] - Ls["a2"]
    dmean = (d1 + d2) / 2
    dsd = abs(d1 - d2) / math.sqrt(2)
    # n=2 t 分布 95% CI(df=1, t_(.975,1)=12.706)—如实标注极宽、仅形式意义
    t_975_df1 = 12.706
    se = dsd / math.sqrt(2)
    ci_lo, ci_hi = dmean - t_975_df1 * se, dmean + t_975_df1 * se
    print(f"run1 Δ(plainctx-ledger) = {d1:+.2f}pp | run2 Δ = {d2:+.2f}pp | "
          f"mean Δ = {dmean:+.2f}pp")
    print(f"n=2 概要 CI(df=1 t 分布,形式计算,区间极宽,仅供参考,不做强判决):"
          f" [{ci_lo:+.2f}, {ci_hi:+.2f}]pp | 含 0: {ci_lo <= 0 <= ci_hi}")

    # 更有功效的第二条证据线:140 题 run-averaged correctness 配对符号检验
    ra_L = {q: (Ls["c1"][q] + Ls["c2"][q]) / 2 for q in qids}
    ra_P = {q: (Ps["c1"][q] + Ps["c2"][q]) / 2 for q in qids}
    win_p = sum(1 for q in qids if ra_P[q] > ra_L[q])
    win_l = sum(1 for q in qids if ra_L[q] > ra_P[q])
    tie = len(qids) - win_p - win_l
    p_sign = sign_p(win_p, win_l)
    print(f"\n配对符号检验(140 题,run-averaged correctness,plainctx 赢/ledger 赢/平):"
          f" {win_p}/{win_l}/{tie} | 精确二项 p={p_sign:.4f}")
    h3_verdict = ("证实预判(CI 含 0 / 符号检验不显著,即'追平')"
                  if (ci_lo <= 0 <= ci_hi) and p_sign >= 0.05
                  else "证据不一致,标注但不升级为强判决(n=2 功效有限)")
    print(f"H3 判决:{h3_verdict}")

    # ── §五 逐题两轮一致率细分(按题型) ──────────────────────────
    print("\n" + "-" * 78)
    print("§五 逐题两轮一致率(按题型细分)")
    print("-" * 78)
    qtypes = sorted(set(qtype.values()))
    print(f"{'arm':24s} " + " ".join(f"{t:>15s}" for t in qtypes))
    for key, *_ in ARMS:
        s = summary[key]
        row = []
        for t in qtypes:
            sub = [q for q in qids if qtype[q] == t]
            a = 100 * sum(s["c1"][q] == s["c2"][q] for q in sub) / len(sub)
            row.append(f"{a:14.1f}%")
        print(f"{key:24s} " + " ".join(row))

    # ── §六 成本 ────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("§六 成本(读者:本批 $12 硬顶适用于 run2 新增部分;判官另计)")
    print("-" * 78)
    grand_r2_reader = 0.0
    grand_r2_judge = 0.0
    grand_r1_reader = 0.0
    grand_r1_judge = 0.0
    print(f"{'arm':24s} {'run1 $reader':>13s} {'run1 $judge':>12s} "
          f"{'run2 $reader':>13s} {'run2 $judge':>12s}")
    for key, *_ in ARMS:
        r1r, r1j = cost_rows[key]["run1"]
        r2r, r2j = cost_rows[key]["run2"]
        grand_r1_reader += r1r
        grand_r1_judge += r1j
        grand_r2_reader += r2r
        grand_r2_judge += r2j
        print(f"{key:24s} {r1r:12.3f}$ {r1j:11.3f}$ "
              f"{r2r:12.3f}$ {r2j:11.3f}$")
    print(f"{'TOTAL':24s} {grand_r1_reader:12.3f}$ {grand_r1_judge:11.3f}$ "
          f"{grand_r2_reader:12.3f}$ {grand_r2_judge:11.3f}$")
    print(f"\nrun2(本批新增)读者花费合计: ${grand_r2_reader:.3f} "
          f"(硬顶 $12,剩余 ${12 - grand_r2_reader:.3f})")
    print(f"run2(本批新增)判官花费合计: ${grand_r2_judge:.3f}(另计,不计入硬顶)")
    print(f"run1+run2 读者花费合计(含历史已花): ${grand_r1_reader + grand_r2_reader:.3f}")

    # ── §七 数据质量脚注 ────────────────────────────────────────
    print("\n" + "-" * 78)
    print("§七 数据质量脚注(逐臂 stop_reason==max_tokens 计数,run2)")
    print("-" * 78)
    for key, *_ in ARMS:
        run2 = data[key]["run2"]
        capped = [q for q in qids if run2[q].get("stop_reason") == "max_tokens"]
        print(f"{key:24s} capped={len(capped)}/{len(qids)} {capped if capped else ''}")


if __name__ == "__main__":
    main()
