# -*- coding: utf-8 -*-
"""批 42 保留集 2 统计:新 40 链单臂(Wilson CI + 40 链簇自助 CI)+ 池化 80 链
(既有 40 链保留集 v1 + 批 42 新 40 链,仅 smoc/direct 两臂池化,理由见
`results/opt_batch42_prereg.md` §二"第三臂方法论声明")+ 逐题型 + 配对 McNemar
+ 成本(读者与判官,判官侧本批为实测)。H1/H2/H3 判据见 prereg §四。
"""
import glob
import json
import random
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_BOOT = 10000
SEED = 20260904
random.seed(SEED)

P_IN, P_OUT = 0.80, 4.00        # haiku-4.5 $/M(读者)
J_IN, J_OUT = 5.00, 25.00       # claude-opus-5 判官 $/M

MAIN_HEADLINE = {"smoc": 89.06, "direct": 47.57, "delta": 41.49}  # 任务书给定


def load(pat):
    d = {}
    for f in sorted(glob.glob(str(ROOT / pat))):
        for l in open(f, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            if "error" in r:
                continue
            d[r["question_id"]] = r
    return d


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    dd = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5
    return ((c - s) / dd * 100, (c + s) / dd * 100)


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def cluster_key(r, q):
    return r.get("uid") or q.rsplit("_", 1)[0]


def cluster_boot_acc(d, n_boot=N_BOOT):
    clusters = defaultdict(list)
    for q, r in d.items():
        clusters[cluster_key(r, q)].append(int(r["judge_correct"]))
    keys = list(clusters)
    accs = []
    for _ in range(n_boot):
        samp = [clusters[random.choice(keys)] for _ in keys]
        num = sum(sum(x) for x in samp)
        den = sum(len(x) for x in samp)
        accs.append(num / den * 100 if den else 0.0)
    accs.sort()
    return clusters, accs[int(.025 * n_boot)], accs[int(.975 * n_boot)]


def arm_report(label, d, judge_tokens_measured=True):
    n = len(d)
    ok = sum(1 for r in d.values() if r["judge_correct"])
    bt = defaultdict(lambda: [0, 0])
    for r in d.values():
        t = r.get("question_type")
        bt[t][0] += 1
        bt[t][1] += bool(r["judge_correct"])
    ti = sum(r.get("usage_input_tokens") or 0 for r in d.values())
    to = sum(r.get("usage_output_tokens") or 0 for r in d.values())
    jti = sum(r.get("judge_input_tokens") or 0 for r in d.values())
    jto = sum(r.get("judge_output_tokens") or 0 for r in d.values())
    lat = [r.get("latency_s") or 0 for r in d.values()]
    cost = ti / 1e6 * P_IN + to / 1e6 * P_OUT
    jcost = jti / 1e6 * J_IN + jto / 1e6 * J_OUT
    acc = ok / max(1, n) * 100
    wlo, whi = wilson(ok, n)
    clusters, clo, chi = cluster_boot_acc(d)
    print(f"\n### {label}")
    print(f"  n={n} chains={len(clusters)} acc={acc:.2f}  "
          f"Wilson 95% CI [{wlo:.2f},{whi:.2f}]  "
          f"{len(clusters)}链簇自助 95% CI [{clo:.2f},{chi:.2f}]")
    for t, (a, b) in sorted(bt.items()):
        print(f"    {t:15s} {b}/{a} = {b/a*100:6.2f}")
    print(f"  reader tokens in={ti:,} out={to:,}  cost ${cost:.4f}  "
          f"avg latency {sum(lat)/max(1,len(lat)):.2f}s")
    if jti or jto:
        tag = "实测" if judge_tokens_measured else "估算"
        print(f"  judge tokens in={jti:,} out={jto:,}  cost ${jcost:.4f} ({tag})")
    return {"label": label, "n": n, "acc": acc, "wilson_ci": [wlo, whi],
            "cluster_ci": [clo, chi], "n_clusters": len(clusters),
            "by_type": {t: [b, a] for t, (a, b) in bt.items()},
            "tok_in": ti, "tok_out": to, "cost_usd": cost,
            "judge_tok_in": jti, "judge_tok_out": jto, "judge_cost_usd": jcost,
            "latency_mean": sum(lat) / max(1, len(lat))}


def contrast(label, base, test, n_boot=N_BOOT):
    ks = sorted(set(base) & set(test))
    b = sum(1 for q in ks if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in ks if not base[q]["judge_correct"] and test[q]["judge_correct"])
    delta = (sum(test[q]["judge_correct"] for q in ks)
             - sum(base[q]["judge_correct"] for q in ks)) / len(ks) * 100
    clusters = defaultdict(list)
    for q in ks:
        uid = test[q].get("uid") or base[q].get("uid") or q.rsplit("_", 1)[0]
        clusters[uid].append((int(test[q]["judge_correct"]),
                              int(base[q]["judge_correct"])))
    cw = cl = ct = 0
    for items in clusters.values():
        dd = sum(a - bb for a, bb in items) / len(items)
        cw += dd > 0
        cl += dd < 0
        ct += dd == 0
    keys = list(clusters)
    deltas = []
    for _ in range(n_boot):
        samp = [clusters[random.choice(keys)] for _ in keys]
        num = sum(a - bb for items in samp for a, bb in items)
        den = sum(len(items) for items in samp)
        deltas.append(num / den * 100 if den else 0.0)
    deltas.sort()
    lo, hi = deltas[int(.025 * n_boot)], deltas[int(.975 * n_boot)]
    print(f"\n### {label}")
    print(f"  n_items={len(ks)} n_chains={len(clusters)}")
    print(f"  Δ={delta:+.2f}pp  b={b}/c={c}  McNemar p={sign_p(b,c):.3g}")
    print(f"  链级符号检验 {cw}W/{cl}L/{ct}T  p={sign_p(cw,cl):.3g}")
    print(f"  {len(clusters)}链簇自助 95% CI [{lo:+.2f},{hi:+.2f}]pp")
    return {"label": label, "delta": delta, "b": b, "c": c,
            "p": sign_p(b, c), "ci": [lo, hi], "n_items": len(ks),
            "n_clusters": len(clusters),
            "chain_sign": [cw, cl, ct], "chain_p": sign_p(cw, cl)}


def main():
    # 新 40 链(批 42)
    new = {
        "smoc": load("results/b42_smoc_holdout2*.jsonl"),
        "direct": load("results/b42_direct_holdout2*.jsonl"),
        "plainctx": load("results/b42_plainctx_holdout2*.jsonl"),
    }
    # 既有 40 链保留集 v1(批 33-C)
    old = {
        "smoc": load("results/holdout_smoc*.jsonl"),
        "direct": load("results/holdout_direct.jsonl"),
        "fullplain": load("results/holdout_fullplain.jsonl"),
    }

    rep = {"new40": {"arms": [], "contrasts": []},
           "pooled80": {"arms": [], "contrasts": []},
           "old40_reload": {}, "hypotheses": {}}

    print("=" * 70)
    print("新 40 链(批 42 保留集 2)单臂")
    print("=" * 70)
    for k, d in new.items():
        if d:
            rep["new40"]["arms"].append(arm_report(f"new40:{k}", d))
    if new["smoc"] and new["direct"]:
        rep["new40"]["contrasts"].append(
            contrast("new40 smoc − direct(结构总价,H1)", new["direct"], new["smoc"]))
    if new["smoc"] and new["plainctx"]:
        rep["new40"]["contrasts"].append(
            contrast("new40 smoc − plainctx", new["plainctx"], new["smoc"]))
    if new["plainctx"] and new["direct"]:
        rep["new40"]["contrasts"].append(
            contrast("new40 plainctx − direct", new["direct"], new["plainctx"]))

    print("\n" + "=" * 70)
    print("既有 40 链保留集 v1(批 33-C,复算供池化用)")
    print("=" * 70)
    for k, d in old.items():
        if d:
            rep["old40_reload"][k] = arm_report(f"old40:{k}", d,
                                                judge_tokens_measured=False)

    # 池化 80 链(仅 smoc / direct,理由见 prereg)
    print("\n" + "=" * 70)
    print("池化 80 链(既有 40 + 批 42 新 40;仅 smoc/direct,H2)")
    print("=" * 70)
    pooled = {}
    for arm in ("smoc", "direct"):
        merged = {}
        merged.update(old.get(arm, {}))
        merged.update(new.get(arm, {}))
        pooled[arm] = merged
        if merged:
            rep["pooled80"]["arms"].append(arm_report(f"pooled80:{arm}", merged))
    if pooled.get("smoc") and pooled.get("direct"):
        rep["pooled80"]["contrasts"].append(
            contrast("pooled80 smoc − direct(H2 头条)",
                     pooled["direct"], pooled["smoc"]))

    # ── 假设判读 ──────────────────────────────────────────────
    h1 = next((c for c in rep["new40"]["contrasts"]
               if "H1" in c["label"]), None)
    if h1:
        h1_pass = h1["delta"] >= 30 and h1["ci"][0] > 0
        rep["hypotheses"]["H1"] = {
            "criterion": "new40 smoc-direct delta>=+30pp AND cluster CI lower>0",
            "delta": h1["delta"], "ci": h1["ci"], "pass": h1_pass}
        print(f"\nH1(新 40 链 smoc−direct ≥+30pp 且簇 CI 下界>0): "
              f"Δ={h1['delta']:+.2f}pp CI={h1['ci']} -> "
              f"{'PASS' if h1_pass else 'FAIL'}")

    h2 = next((c for c in rep["pooled80"]["contrasts"]
               if "H2" in c["label"]), None)
    if h2:
        lo_ok = 41.49 - 5
        hi_ok = 41.49 + 5
        h2_pass = lo_ok <= h2["delta"] <= hi_ok
        rep["hypotheses"]["H2"] = {
            "criterion": f"pooled80 smoc-direct delta within +-5pp of {MAIN_HEADLINE['delta']}"
                         f" i.e. in [{lo_ok},{hi_ok}]",
            "delta": h2["delta"], "ci": h2["ci"],
            "main_field_delta": MAIN_HEADLINE["delta"], "pass": h2_pass}
        print(f"\nH2(池化 80 链头条与主场 {MAIN_HEADLINE['delta']}pp 相差≤5pp): "
              f"Δ={h2['delta']:+.2f}pp (簇CI={h2['ci']}) 目标区间=[{lo_ok},{hi_ok}] -> "
              f"{'PASS' if h2_pass else 'FAIL'}")

    plainctx_arm = next((a for a in rep["new40"]["arms"]
                         if a["label"] == "new40:plainctx"), None)
    smoc_arm = next((a for a in rep["new40"]["arms"]
                     if a["label"] == "new40:smoc"), None)
    direct_arm = next((a for a in rep["new40"]["arms"]
                       if a["label"] == "new40:direct"), None)
    if plainctx_arm and smoc_arm and direct_arm:
        between_point = direct_arm["acc"] <= plainctx_arm["acc"] <= smoc_arm["acc"]
        ci_overlap_direct = not (plainctx_arm["cluster_ci"][1] < direct_arm["cluster_ci"][0]
                                 or plainctx_arm["cluster_ci"][0] > direct_arm["cluster_ci"][1])
        ci_overlap_smoc = not (plainctx_arm["cluster_ci"][1] < smoc_arm["cluster_ci"][0]
                               or plainctx_arm["cluster_ci"][0] > smoc_arm["cluster_ci"][1])
        rep["hypotheses"]["H3"] = {
            "criterion": "new40 plainctx point estimate between direct and smoc",
            "direct_acc": direct_arm["acc"], "plainctx_acc": plainctx_arm["acc"],
            "smoc_acc": smoc_arm["acc"], "point_estimate_between": between_point,
            "plainctx_ci_overlaps_direct": ci_overlap_direct,
            "plainctx_ci_overlaps_smoc": ci_overlap_smoc}
        print(f"\nH3(新 40 链 plainctx 介于 direct/smoc 之间): "
              f"direct={direct_arm['acc']:.2f} plainctx={plainctx_arm['acc']:.2f} "
              f"smoc={smoc_arm['acc']:.2f} -> "
              f"点估{'PASS' if between_point else 'FAIL'}"
              f"(plainctx CI 与 direct CI 重叠={ci_overlap_direct}, "
              f"与 smoc CI 重叠={ci_overlap_smoc})")

    total_cost = (sum(a["cost_usd"] for a in rep["new40"]["arms"]) +
                 sum(a.get("cost_usd", 0) for a in rep["old40_reload"].values()
                     if False))  # old40 cost not counted against b42 budget
    b42_builder_reader_cost = sum(a["cost_usd"] for a in rep["new40"]["arms"])
    b42_judge_cost = sum(a["judge_cost_usd"] for a in rep["new40"]["arms"])
    print(f"\n批 42 读者侧总成本(建店成本另在 verdict 记账):"
          f" ${b42_builder_reader_cost:.4f}")
    print(f"批 42 判官侧总成本(实测): ${b42_judge_cost:.4f}")

    (ROOT / "results/b42_stats.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
