# -*- coding: utf-8 -*-
"""批 33-C 保留集统计:点估 + 逐题型 + 配对 McNemar + 40 链簇自助 CI + 成本。

统计口径逐字沿用 scripts/cluster_units_b31_b32p.py(簇 = 链,自助 10,000 次,
分位数法 95% CI,配对 McNemar 用精确二项符号检验)。
"""
import glob
import json
import random
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_BOOT = 10000
random.seed(20260902)

P_IN, P_OUT = 0.80, 4.00        # haiku-4.5 $/M(本批口径)
J_IN, J_OUT = 5.00, 25.00       # claude-opus-5 判官 $/M

DEV = {  # 开发场参照(盘上实跑文件)
    "smoc": (90.45, {"change_count": 88.19, "count_before": 88.89,
                     "first_vs_last": 96.53, "longest_tenure": 88.19}),
    "direct": (48.26, {"change_count": 34.72, "count_before": 43.75,
                       "first_vs_last": 80.56, "longest_tenure": 34.03}),
    "fullplain": (52.26, {"change_count": 29.86, "count_before": 67.36,
                          "first_vs_last": 72.22, "longest_tenure": 39.58}),
}


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


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def arm_report(label, d):
    n = len(d)
    ok = sum(1 for r in d.values() if r["judge_correct"])
    bt = defaultdict(lambda: [0, 0])
    for r in d.values():
        t = r.get("question_type")
        bt[t][0] += 1
        bt[t][1] += bool(r["judge_correct"])
    ti = sum(r.get("usage_input_tokens") or 0 for r in d.values())
    to = sum(r.get("usage_output_tokens") or 0 for r in d.values())
    lat = [r.get("latency_s") or 0 for r in d.values()]
    cost = ti / 1e6 * P_IN + to / 1e6 * P_OUT
    # 簇自助(单臂准确率 CI)
    clusters = defaultdict(list)
    for q, r in d.items():
        clusters[r.get("uid") or q.rsplit("_", 1)[0]].append(int(r["judge_correct"]))
    keys = list(clusters)
    accs = []
    for _ in range(N_BOOT):
        samp = [clusters[random.choice(keys)] for _ in keys]
        num = sum(sum(x) for x in samp)
        den = sum(len(x) for x in samp)
        accs.append(num / den * 100)
    accs.sort()
    lo, hi = accs[int(.025 * N_BOOT)], accs[int(.975 * N_BOOT)]
    acc = ok / max(1, n) * 100
    dev_acc, dev_bt = DEV.get(label.split(":")[0], (None, {}))
    print(f"\n### {label}")
    print(f"  n={n} chains={len(clusters)} acc={acc:.2f} "
          f"簇 CI [{lo:.2f},{hi:.2f}]")
    if dev_acc is not None:
        print(f"  开发场 {dev_acc:.2f} → 保留集 {acc:.2f}  Δ={acc-dev_acc:+.2f}pp")
    for t, (a, b) in sorted(bt.items()):
        dv = dev_bt.get(t)
        extra = f"  (dev {dv:.2f}, Δ={b/a*100-dv:+.2f})" if dv else ""
        print(f"    {t:15s} {b}/{a} = {b/a*100:6.2f}{extra}")
    print(f"  tokens in={ti:,} out={to:,}  读者成本 ${cost:.4f}  "
          f"平均延迟 {sum(lat)/max(1,len(lat)):.2f}s")
    return {"label": label, "n": n, "acc": acc, "ci": [lo, hi],
            "by_type": {t: [b, a] for t, (a, b) in bt.items()},
            "tok_in": ti, "tok_out": to, "cost_usd": cost,
            "latency_mean": sum(lat) / max(1, len(lat))}


def contrast(label, base, test):
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
    for _ in range(N_BOOT):
        samp = [clusters[random.choice(keys)] for _ in keys]
        num = sum(a - bb for items in samp for a, bb in items)
        den = sum(len(items) for items in samp)
        deltas.append(num / den * 100)
    deltas.sort()
    lo, hi = deltas[int(.025 * N_BOOT)], deltas[int(.975 * N_BOOT)]
    print(f"\n### {label}")
    print(f"  n_items={len(ks)} n_chains={len(clusters)}")
    print(f"  Δ={delta:+.2f}pp  b={b}/c={c}  McNemar p={sign_p(b,c):.3g}")
    print(f"  链级符号检验 {cw}W/{cl}L/{ct}T  p={sign_p(cw,cl):.3g}")
    print(f"  40 链簇自助 95% CI [{lo:+.2f},{hi:+.2f}]pp")
    return {"label": label, "delta": delta, "b": b, "c": c,
            "p": sign_p(b, c), "ci": [lo, hi],
            "chain_sign": [cw, cl, ct], "chain_p": sign_p(cw, cl)}


def main():
    arms = {
        "smoc": load("results/holdout_smoc*.jsonl"),
        "direct": load("results/holdout_direct.jsonl"),
        "fullplain": load("results/holdout_fullplain.jsonl"),
    }
    rep = {"arms": [], "contrasts": []}
    for k, d in arms.items():
        if d:
            rep["arms"].append(arm_report(k, d))
    if arms["smoc"] and arms["direct"]:
        rep["contrasts"].append(contrast("smoc − direct(结构总价)",
                                         arms["direct"], arms["smoc"]))
    if arms["smoc"] and arms["fullplain"]:
        rep["contrasts"].append(contrast("smoc − fullplain(弱读者抬升)",
                                         arms["fullplain"], arms["smoc"]))
    if arms["direct"] and arms["fullplain"]:
        rep["contrasts"].append(contrast("fullplain − direct",
                                         arms["direct"], arms["fullplain"]))
    (ROOT / "results/holdout_stats_v1.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(a["cost_usd"] for a in rep["arms"])
    print(f"\n读者侧总成本(usage tokens):${tot:.4f}")


if __name__ == "__main__":
    main()
