# -*- coding: utf-8 -*-
"""Chain-clustered re-analysis of batch31 (cleaning) and batch32' (owner gate).
Item-level McNemar (as reported) vs chain-level sign test + chain cluster bootstrap CI + TOST."""
import glob, json, random, sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
N_BOOT = 10000
random.seed(20260902)

def load(pat):
    d = {}
    for f in sorted(glob.glob(str(ROOT / pat))):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if "error" in r: continue
            d[r["question_id"]] = r
    return d

def sign_p(w, l):
    n = w + l
    if n == 0: return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)

def analyze(label, base, test):
    ks = sorted(set(base) & set(test))
    if not ks:
        print(f"{label}: no overlap"); return
    b = sum(1 for q in ks if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in ks if not base[q]["judge_correct"] and test[q]["judge_correct"])
    delta = (sum(test[q]["judge_correct"] for q in ks) - sum(base[q]["judge_correct"] for q in ks)) / len(ks) * 100
    clusters = defaultdict(list)
    for q in ks:
        uid = test[q].get("uid") or base[q].get("uid") or q.split("_")[0]
        clusters[uid].append((int(test[q]["judge_correct"]), int(base[q]["judge_correct"])))
    cw = cl = ct = 0
    for items in clusters.values():
        d = sum(a - bb for a, bb in items) / len(items)
        cw += d > 0; cl += d < 0; ct += d == 0
    csign = sign_p(cw, cl)
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
    print(f"  n_items={len(ks)}  n_chains={len(clusters)}")
    print(f"  item-level: Δ={delta:+.2f}pp  b={b}/c={c}  McNemar p={sign_p(b,c):.3g}")
    print(f"  chain-level sign test: {cw}W/{cl}L/{ct}T  p={csign:.3g}")
    print(f"  chain cluster bootstrap 95% CI: [{lo:+.2f}, {hi:+.2f}]pp")
    for m in (2.0, 3.0, 5.0):
        # TOST: equivalence within +-m  => 90% CI inside (-m, m)
        l90, h90 = deltas[int(.05 * N_BOOT)], deltas[int(.95 * N_BOOT)]
        ok = (-m < l90) and (h90 < m)
        print(f"  TOST margin ±{m}pp (90% CI [{l90:+.2f},{h90:+.2f}]): {'PASS equivalence' if ok else 'FAIL (not equivalent)'}")

v20 = load("results/wsc_v2_smoc.jsonl")
v22 = load("results/b31_smoc_v22_full.jsonl")
v24 = {**load("results/b31_smoc_v22_full.jsonl"), **load("results/b31_smoc_v23.jsonl"), **load("results/b31_smoc_v24.jsonl")}
D   = load("results/b32_smoc_D.jsonl")
gate= load("results/b32p_smoc_Dgate_shard*.jsonl")
rd  = load("results/b32p_smoc_Dread_shard*.jsonl")
direct20 = load("results/wsc_v2_direct.jsonl")

analyze("B31 cleaning: v2.0 smoc -> v2.2 smoc (576)", v20, v22)
analyze("B31 cleaning: v2.0 smoc -> v2.4 smoc (576)", v20, v24)
analyze("B32' gate: v2.4 -> D gate store (B'3 non-inferiority)", v24, gate)
analyze("B32' no-gate: v2.4 -> D raw store", v24, D)
analyze("B32' read-side: v2.4 -> D read-only-self", v24, rd)
analyze("B32' gate vs no-gate (recovery)", D, gate)
