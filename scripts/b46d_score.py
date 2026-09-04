# -*- coding: utf-8 -*-
"""批 46d 记分器 —— 144 链全量冻结写入侧配置,全量 560 题 headline。

预注册:results/opt_batch46d_prereg.md(先于跑批提交,含 H1 基线修正)。

结构沿用 scripts/b38e_score.py / scripts/b41_score.py 的函数(去重取首次
出现;精确二项符号检验;compiled_answer/gold_equal 逐字复用),规模从 36 链
/140 题放大到 144 链/560 题;新增:
  - run1/run2/run-mean 三行 headline(两次独立读者跑);
  - run-mean 的"分数正确"(0/0.5/1)配对比较,用 compare_frac()(泛化
    scripts/b33A_score.py::compare() 支持非布尔值,N_BOOT/seed 同源);
  - 144 链簇自助 CI vs results/b33A_direct.jsonl / b33A_smw.jsonl /
    b33A_smwplain.jsonl(三个 33-A 文件先过滤到本批 560 个 question_id)。

用法: PYTHONUTF8=1 python scripts/b46d_score.py > results/b46d_score_out.txt
"""
from __future__ import annotations

import json
import random
import re
import statistics as st
import sys
import unicodedata
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import acc, load, sign_p  # noqa: E402
from b38e_score import compiled_answer, diag_uid, gold_equal  # noqa: E402

QREF = "data/wsc_s5_v25.jsonl"
CORPUS = "data/wikistate_full_ALL_v24.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
S5 = (2.00, 10.00)
H45 = (1.00, 5.00)
N_BOOT = 10000
SEED = 20260902

STORES = [
    ("v45", "results/wt_cards_v45", "claude-haiku-4-5"),
    ("v47s", "results/wt_cards_v47s", "claude-sonnet-5 (36-chain sample only)"),
    ("v48", "results/wt_cards_v48",
     "claude-sonnet-5, pass1, 144 chains (本批)"),
    ("v48f", "results/wt_cards_v48f",
     "claude-sonnet-5, pass1(+gold-free pass2 for triggered chains)"
     "+assertion-filter, 144 chains (本批)"),
]

RUNS = [
    ("run1", ["results/b46d_smoc_v48f_haiku_run1.jsonl",
              "results/b46d_smoc_v48f_haiku_run1_mt4000.jsonl"]),
    ("run2", ["results/b46d_smoc_v48f_haiku_run2.jsonl",
              "results/b46d_smoc_v48f_haiku_run2_mt4000.jsonl"]),
]

REF_ARMS = [
    ("v45@haiku (smoc, 批33-A)", "results/b33A_smoc_v45.jsonl"),
    ("direct (批33-A)", "results/b33A_direct.jsonl"),
    ("smw (full text + F.1, 批33-A)", "results/b33A_smw.jsonl"),
    ("smwplain (full text plain, 批33-A)", "results/b33A_smwplain.jsonl"),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def load_many(paths, keys):
    m = {}
    for p in paths:
        if not (ROOT / p).exists():
            continue
        m.update(restrict(load(p), keys))
    return m


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def stats(rows, pi, po):
    mi = st.mean([r.get("usage_input_tokens") or 0 for r in rows])
    mo = st.mean([r.get("usage_output_tokens") or 0 for r in rows])
    lat = st.median([r.get("latency_s") or 0 for r in rows])
    ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
    to = sum(r.get("usage_output_tokens") or 0 for r in rows)
    return mi, mo, lat, mi / 1e6 * pi + mo / 1e6 * po, ti / 1e6 * pi + to / 1e6 * po


def cap_count(paths, keys):
    d = load_many(paths, keys)
    have = [r for r in d.values() if "stop_reason" in r]
    if not have:
        return None
    capped = sum(1 for r in have if r.get("stop_reason") == "max_tokens")
    return capped, len(have)


def cmp2(name_a, a, name_b, b):
    keys = sorted(set(a) & set(b))
    if not keys:
        print("  %s vs %s : no overlap" % (name_a, name_b))
        return
    aw = sum(1 for q in keys if a[q]["judge_correct"] and not b[q]["judge_correct"])
    bw = sum(1 for q in keys if b[q]["judge_correct"] and not a[q]["judge_correct"])
    pa = sum(bool(a[q]["judge_correct"]) for q in keys) / len(keys) * 100
    pb = sum(bool(b[q]["judge_correct"]) for q in keys) / len(keys) * 100
    print("  n=%3d | A=%-40s %5.1f%%  B=%-40s %5.1f%% | delta(A-B) %+6.2fpp | "
          "A-only-right=%2d B-only-right=%2d | McNemar exact p=%.4g"
          % (len(keys), name_a, pa, name_b, pb, pa - pb, aw, bw, sign_p(aw, bw)))


def compare_frac(label, base_val, test_val, base_uid, test_uid, margins=(3.0,)):
    """泛化 scripts/b33A_score.py::compare():base_val/test_val 是
    {qid: 0/1 或 0/0.5/1 的分数正确值}(支持 run-mean 的非布尔配对),
    base_uid/test_uid 是 {qid: uid} 用于链簇分组。N_BOOT/seed/margins 与
    b33A_score.compare() 同源,输出格式对齐但用"win/loss(按符号)"代替
    严格 McNemar 的 b/c 计数(非布尔值时 McNemar 本身不再是精确定义,
    这里退化为符号检验,与 scripts/cluster_units_b31_b32p.py 的链级符号
    检验同一方法,只是把它下放到题级)。"""
    keys = sorted(set(base_val) & set(test_val))
    if not keys:
        print("### " + label + ": no overlap")
        return None
    w = sum(1 for q in keys if test_val[q] > base_val[q])
    l = sum(1 for q in keys if test_val[q] < base_val[q])
    delta = (sum(test_val[q] for q in keys) - sum(base_val[q] for q in keys)) / len(keys) * 100
    clusters = defaultdict(list)
    for q in keys:
        uid = test_uid.get(q) or base_uid.get(q) or q.split("_")[0]
        clusters[uid].append((test_val[q], base_val[q]))
    random.seed(SEED)
    ks = list(clusters)
    ds = []
    for _ in range(N_BOOT):
        samp = [clusters[random.choice(ks)] for _ in ks]
        num = sum(x - y for it in samp for x, y in it)
        den = sum(len(it) for it in samp)
        ds.append(num / den * 100)
    ds.sort()
    lo, hi = ds[int(.025 * N_BOOT)], ds[int(.975 * N_BOOT)]
    l90, h90 = ds[int(.05 * N_BOOT)], ds[int(.95 * N_BOOT)]
    cw = sum(1 for it in clusters.values() if sum(x - y for x, y in it) > 0)
    cl = sum(1 for it in clusters.values() if sum(x - y for x, y in it) < 0)
    ct = len(clusters) - cw - cl
    print("### " + label)
    print("  n=%d items / %d chains | delta=%+.2fpp  item-win/loss=%d/%d  "
          "sign-test p=%.3g"
          % (len(keys), len(clusters), delta, w, l, sign_p(w, l)))
    print("  chain sign test %dW/%dL/%dT p=%.3g | cluster boot 95%% CI [%+.2f,%+.2f]pp"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi))
    for m in margins:
        ok = (-m < l90) and (h90 < m)
        print("  TOST +-%.1fpp (90%% CI [%+.2f,%+.2f]): %s"
              % (m, l90, h90, "PASS equivalence" if ok else "FAIL not equivalent"))
    return delta, (lo, hi)


def compiled_ceiling(store, uids, qs_by_uid, ents):
    """§H1: compiled_answer()/gold_equal() 离线上限,question-level,
    (逐字复用 scripts/b38e_score.py 的方法)。"""
    n_eq = n_tot = 0
    by_t = Counter(); by_t_tot = Counter()
    for u in uids:
        try:
            _e, _d0, _m, _x, lane_slots, _nrec, rows = diag_uid(u, ents[u], store)
        except FileNotFoundError:
            continue
        lane_set = set(lane_slots)
        lane_rows = [(dd, r) for dd, r in rows if (r.get("slot") or "?") in lane_set]
        for q in qs_by_uid.get(u, []):
            comp = compiled_answer(q["qtype"], q["question"], lane_rows)
            eq = gold_equal(q["qtype"], q["gold"], comp)
            n_tot += 1; by_t_tot[q["qtype"]] += 1
            if eq:
                n_eq += 1; by_t[q["qtype"]] += 1
    return n_eq, n_tot, by_t, by_t_tot


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})
    qtype = {q["qid"]: q["qtype"] for q in qref}
    quid = {q["qid"]: q["uid"] for q in qref}
    qs_by_uid = {}
    for q in qref:
        qs_by_uid.setdefault(q["uid"], []).append(q)

    print("# Batch 46d — 144-chain frozen write-side config, full-set headline\n")
    print("Pre-registration: results/opt_batch46d_prereg.md (H1 baseline "
          "corrected there \u00a70 from the task-quoted 91.7% — a 36-chain/"
          "133-row historical figure — to a freshly-measured full-scale "
          "v45 baseline; see \u00a71 below for both numbers side by side).\n")
    print(f"Questions: {QREF} ({len(qids)} qids / {len(uids)} chains); "
          f"corpus {CORPUS}.\n")

    corpus = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}

    # ---------------------------------------------------------------- \u00a71
    print("## 1. Write-side diagnostic: compiled ledger vs gold chain "
          "(all stores, 144 chains)\n")
    agg = {}
    diag_full = {}
    for tag, store, extr in STORES:
        if not (ROOT / store).exists():
            print(f"| {tag} | (store missing: {store}) |")
            continue
        tot = Counter()
        per = {}
        chains_here = uids if tag != "v47s" else [
            u for u in uids if (ROOT / store / f"{u}.json").exists()]
        for u in chains_here:
            e, d0, m, x, lane, nrec, rows = diag_uid(u, ents[u], store)
            diag_full[(tag, u)] = (e, d0, m, x, lane, nrec, rows)
            per[u] = (e, d0, m, x, lane, nrec)
            tot["exact"] += e; tot["date_off"] += d0
            tot["missing"] += m; tot["extra"] += x
            tot["gold"] += len(ents[u].get("chain") or [])
            tot["records"] += nrec
        agg[tag] = (tot, per, chains_here)
    print("| store | extractor | n chains | gold rows | exact | date-off | "
          "missing | extra | total cards | perfect chains |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for tag, store, extr in STORES:
        if tag not in agg:
            continue
        tot, per, chains_here = agg[tag]
        perfect = sum(1 for u in chains_here
                      if per[u][2] == 0 and per[u][1] == 0
                      and per[u][0] == len(ents[u].get("chain") or []))
        print("| %s | %s | %d | %d | **%d** (%.1f%%) | %d | **%d** | %d | %d | "
              "%d/%d |"
              % (tag, extr, len(chains_here), tot["gold"], tot["exact"],
                 tot["exact"] / max(1, tot["gold"]) * 100,
                 tot["date_off"], tot["missing"], tot["extra"],
                 tot["records"], perfect, len(chains_here)))

    print("\n## 2. H1 — compiled-answer ceiling (offline, zero API), all "
          "560 questions, threshold >= 98%\n")
    print("Task-quoted baseline \"v45 was 91.7% of rows\" is the 36-chain/"
          "133-gold-row figure from results/opt_batch38_verdict.md \u00a76 "
          "(row-level, not question-level, and not full-scale) — see "
          "prereg \u00a70 for the full correction. Both a freshly-measured "
          "full-scale row-level number and the question-level ceiling "
          "(the H1 judging metric) are reported below.\n")
    h1_results = {}
    for tag, store, extr in STORES:
        if tag not in agg or store not in ("results/wt_cards_v45",
                                            "results/wt_cards_v48f"):
            continue
        n_eq, n_tot, by_t, by_t_tot = compiled_ceiling(store, uids, qs_by_uid, ents)
        h1_results[tag] = (n_eq, n_tot)
    print("| store | gold-equal (question-level, H1 metric) | " +
          " | ".join(TYPES) + " |")
    print("|---|---|---|---|---|---|")
    for tag, store, extr in STORES:
        if tag not in h1_results:
            continue
        n_eq, n_tot = h1_results[tag]
        _e2, _t2, by_t, by_t_tot = compiled_ceiling(store, uids, qs_by_uid, ents)
        print("| %s | **%d/%d = %.1f%%** | %s |"
              % (tag, n_eq, n_tot, n_eq / max(1, n_tot) * 100,
                 " | ".join(f"{by_t[t]}/{by_t_tot[t]}" for t in TYPES)))
    if "v45" in h1_results and "v48f" in h1_results:
        e45, t45 = h1_results["v45"]
        ef, tf = h1_results["v48f"]
        p45, pf = e45 / t45 * 100, ef / tf * 100
        verdict = "CONFIRMED" if pf >= 98.0 else "REJECTED"
        print(f"\n**H1 verdict**: v48f = {pf:.1f}% ({'>= 98%' if pf>=98 else '< 98%'}) "
              f"-> **{verdict}**. (v45 full-scale for context: {p45:.1f}%, "
              f"delta {pf-p45:+.1f}pp.)")

    # ---------------------------------------------------------------- \u00a73 reader runs
    print("\n## 3. H2/H3 — real reader (claude-haiku-4-5, smoc, "
          "results/wt_cards_v48f), two independent runs\n")
    hdr = ("| run | n | acc | " + " | ".join(TYPES) +
           " | in tok | out tok | median lat s | $/q | $ total |")
    print(hdr)
    print("|" + "---|" * (9 + len(TYPES)))
    run_data = {}
    for name, paths in RUNS:
        d = load_many(paths, qids)
        if not d:
            print(f"| {name} | 0 | (missing: {paths}) |" + "|" * len(TYPES))
            continue
        run_data[name] = d
        mi, mo, lat, cpq, total = stats(list(d.values()), *H45)
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| %s | %d | **%.2f%%** | %s | %.0f | %.0f | %.2f | $%.5f | "
              "$%.3f |"
              % (name, len(d), acc(d), tys, mi, mo, lat, cpq, total))

    # run-mean row (only over qids present in BOTH runs)
    mean_row = None
    if "run1" in run_data and "run2" in run_data:
        keys = sorted(set(run_data["run1"]) & set(run_data["run2"]))
        mean_correct = {q: (int(bool(run_data["run1"][q]["judge_correct"])) +
                            int(bool(run_data["run2"][q]["judge_correct"]))) / 2
                        for q in keys}
        mean_acc = sum(mean_correct.values()) / len(keys) * 100
        mi = st.mean([(run_data["run1"][q].get("usage_input_tokens") or 0) +
                      (run_data["run2"][q].get("usage_input_tokens") or 0)
                      for q in keys]) / 2
        mo = st.mean([(run_data["run1"][q].get("usage_output_tokens") or 0) +
                      (run_data["run2"][q].get("usage_output_tokens") or 0)
                      for q in keys]) / 2
        cpq = mi / 1e6 * H45[0] + mo / 1e6 * H45[1]
        by_t_mean = {}
        for t in TYPES:
            tk = [q for q in keys if qtype.get(q) == t]
            by_t_mean[t] = (sum(mean_correct[q] for q in tk) / len(tk) * 100
                            if tk else None)
        tys = " | ".join(("%.1f" % by_t_mean[t]) if by_t_mean[t] is not None
                         else "-" for t in TYPES)
        print("| **run-mean** | %d | **%.2f%%** | %s | %.0f | %.0f | - | "
              "$%.5f | $%.3f |"
              % (len(keys), mean_acc, tys, mi, mo, cpq, cpq * len(keys)))
        mean_row = mean_correct

    print("\n### max_tokens cap hits (stop_reason==\"max_tokens\")\n")
    print("| run | capped rows | rows w/ stop_reason |")
    print("|---|---|---|")
    for name, paths in RUNS:
        cc = cap_count(paths, qids)
        if cc is None:
            print(f"| {name} | (no stop_reason field) | - |")
        else:
            capped, tot = cc
            print(f"| {name} | {capped} | {tot} |")

    if "run1" in run_data:
        acc1 = acc(run_data["run1"])
        v_h2 = "CONFIRMED" if acc1 >= 92.0 else "REJECTED (run1)"
        print(f"\n**H2 verdict (run1)**: {acc1:.2f}% vs threshold >=92% "
              f"(v45=89.29%) -> {v_h2}")
        if mean_row is not None:
            mean_acc2 = sum(mean_row.values()) / len(mean_row) * 100
            v_h2b = "CONFIRMED" if mean_acc2 >= 92.0 else "REJECTED (run-mean)"
            print(f"**H2 verdict (run-mean)**: {mean_acc2:.2f}% -> {v_h2b}")
        mi1 = st.mean([r.get("usage_input_tokens") or 0
                       for r in run_data["run1"].values()])
        v_h3 = "CONFIRMED" if mi1 <= 2937 else "REJECTED (run1)"
        print(f"**H3 verdict (run1)**: mean in-tok {mi1:.0f} vs threshold "
              f"<=2937 (v45) -> {v_h3}")

    # ---------------------------------------------------------------- \u00a74 McNemar vs v45
    print("\n## 4. Paired McNemar (exact binomial sign test) vs v45 "
          "(results/b33A_smoc_v45.jsonl, filtered to the 560 qids)\n")
    v45 = load_many(["results/b33A_smoc_v45.jsonl"], qids)
    if "run1" in run_data and v45:
        cmp2("v48f@haiku run1", run_data["run1"], "v45@haiku (batch 33-A)", v45)
    if mean_row is not None and v45:
        v45_val = {q: int(bool(v45[q]["judge_correct"])) for q in v45}
        v45_uid = {q: v45[q].get("uid") for q in v45}
        test_uid = {q: quid.get(q) for q in mean_row}
        compare_frac("v48f@haiku run-mean vs v45@haiku (McNemar generalized "
                     "to fractional run-mean values, see compare_frac() "
                     "docstring)", v45_val, mean_row, v45_uid, test_uid)

    # ---------------------------------------------------------------- \u00a75 chain-cluster CI
    print("\n## 5. 144-chain-cluster bootstrap CI (N=%d, seed=%d, reused "
          "from scripts/b33A_score.py::compare()) vs direct / full-text arms\n"
          % (N_BOOT, SEED))
    for label, path in REF_ARMS:
        if "v45@haiku" in label:
            continue
        ref = load_many([path], qids)
        if not ref or "run1" not in run_data:
            print(f"### v48f@haiku run1 vs {label}: missing data")
            continue
        run1_val = {q: int(bool(run_data["run1"][q]["judge_correct"]))
                    for q in run_data["run1"]}
        run1_uid = {q: quid.get(q) for q in run1_val}
        ref_val = {q: int(bool(ref[q]["judge_correct"])) for q in ref}
        ref_uid = {q: ref[q].get("uid") or quid.get(q) for q in ref}
        compare_frac(f"v48f@haiku run1 vs {label}", ref_val, run1_val,
                    ref_uid, run1_uid)
        if mean_row is not None:
            mean_uid = {q: quid.get(q) for q in mean_row}
            compare_frac(f"v48f@haiku run-mean vs {label}", ref_val, mean_row,
                        ref_uid, mean_uid)

    # ---------------------------------------------------------------- \u00a76 per-question-type headline
    print("\n## 6. Headline accuracy comparison table (560 qids, all arms "
          "restricted to the same set)\n")
    print("| arm | n | acc | " + " | ".join(TYPES) + " |")
    print("|---|---|---|---|---|---|---|")
    for label, path in REF_ARMS:
        d = load_many([path], qids)
        if not d:
            continue
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| %s | %d | %.2f%% | %s |" % (label, len(d), acc(d), tys))
    for name, d in run_data.items():
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| v48f@haiku %s | %d | %.2f%% | %s |" % (name, len(d), acc(d), tys))

    # ---------------------------------------------------------------- \u00a77 cost
    print("\n## 7. Reader-arm cost summary (this batch's two runs; judge "
          "billed separately)\n")
    print("| run | in tok total | out tok total | $ |")
    print("|---|---|---|---|")
    reader_total = 0.0
    for name, paths in RUNS:
        d = load_many(paths, qids)
        ti = sum(r.get("usage_input_tokens") or 0 for r in d.values())
        to = sum(r.get("usage_output_tokens") or 0 for r in d.values())
        usd = ti / 1e6 * H45[0] + to / 1e6 * H45[1]
        reader_total += usd
        print(f"| {name} | {ti:,} | {to:,} | ${usd:.3f} |")
    print(f"| **reader total** | | | **${reader_total:.3f}** |")

    print("\nSee results/b46d_provenance.txt for build windows, per-chain "
          "cost, and store directory sha256.")


if __name__ == "__main__":
    main()
