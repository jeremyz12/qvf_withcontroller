# -*- coding: utf-8 -*-
"""批 33-A 记分器:单语料冻结重建(v2.4 语料 x v45/v45g 店 x haiku-4.5 读者)。

口径:
- 去重规则:同一 question_id 保留**首次**出现(并发重复写造成的多行);
- 配对 McNemar(精确二项符号检验,与 scripts/cluster_units_b31_b32p.py 同函数);
- 144 链簇自助 CI(N=10000,seed 20260902)+ TOST(90% CI 落 +-m 内判等价);
- 成本按 haiku $0.80/M in、$4.00/M out(读者侧 usage token;判官 opus-5 另计)。

用法: PYTHONUTF8=1 python scripts/b33A_score.py > results/b33A_score_out.txt
"""
from __future__ import annotations

import glob
import json
import random
import statistics as st
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
N_BOOT = 10000
P_IN, P_OUT = 0.80, 4.00

ARMS = [
    ("direct",     "results/b33A_direct.jsonl",     "results/wsc_v2_direct.jsonl"),
    ("filter",     "results/b33A_filter.jsonl",     "results/wsc_v2_filter.jsonl"),
    ("usability",  "results/b33A_usability.jsonl",  "results/wsc_v2_usability.jsonl"),
    ("compile",    "results/b33A_compile.jsonl",    "results/wsc_v2_compile.jsonl"),
    ("smw",        "results/b33A_smw.jsonl",        "results/wsc_v2_smw.jsonl"),
    ("smwplain",   "results/b33A_smwplain.jsonl",   "results/wsc_v2_smwplain.jsonl"),
    ("summary",    "results/b33A_summary.jsonl",    "results/wsc_v2_summary_arm.jsonl"),
    ("smoc_v45",   "results/b33A_smoc_v45.jsonl",   "results/wsc_v2_smoc.jsonl"),
    ("smoc_v45g",  "results/b33A_smoc_v45g.jsonl",  "results/wsc_v2_smoc.jsonl"),
]

SPLICED = {"smoc_v45": 90.45, "direct": 48.26}
DUP_STATS = {}


def load(pat):
    d, dup, agree, tot = {}, 0, 0, 0
    for f in sorted(glob.glob(str(ROOT / pat))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "error" in r:
                continue
            tot += 1
            q = r["question_id"]
            if q in d:
                dup += 1
                agree += int(bool(d[q].get("judge_correct"))
                             == bool(r.get("judge_correct")))
                continue
            d[q] = r
    DUP_STATS[pat] = (tot, len(d), dup, (agree / dup * 100) if dup else None)
    return d


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def acc(d):
    return sum(1 for r in d.values() if r.get("judge_correct")) / max(1, len(d)) * 100


def compare(label, base, test, margins=(3.0,)):
    keys = sorted(set(base) & set(test))
    if not keys:
        print("### " + label + ": no overlap")
        return None
    b = sum(1 for q in keys if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in keys if not base[q]["judge_correct"] and test[q]["judge_correct"])
    delta = (sum(bool(test[q]["judge_correct"]) for q in keys)
             - sum(bool(base[q]["judge_correct"]) for q in keys)) / len(keys) * 100
    clusters = defaultdict(list)
    for q in keys:
        uid = test[q].get("uid") or base[q].get("uid") or q.split("_")[0]
        clusters[uid].append((int(bool(test[q]["judge_correct"])),
                              int(bool(base[q]["judge_correct"]))))
    random.seed(20260902)
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
    print("  n=%d ti / %d lian | delta=%+.2fpp  b/c=%d/%d  McNemar p=%.3g"
          % (len(keys), len(clusters), delta, b, c, sign_p(b, c)))
    print("  chain sign test %dW/%dL/%dT p=%.3g | cluster boot 95%% CI [%+.2f,%+.2f]pp"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi))
    for m in margins:
        ok = (-m < l90) and (h90 < m)
        print("  TOST +-%.1fpp (90%% CI [%+.2f,%+.2f]): %s"
              % (m, l90, h90, "PASS equivalence" if ok else "FAIL not equivalent"))
    return delta


def main():
    data = {n: load(p) for n, p, _ in ARMS}
    v20 = {n: load(a) for n, _, a in ARMS}

    print("# Batch 33-A score (corpus v2.4 / stores v45+v45g / haiku-4.5 / ClaudeJudge)\n")

    print("## 0. Dedupe ledger (concurrent duplicate writes -> keep FIRST)\n")
    print("| arm | raw rows | deduped | dup rows | first/later verdict agreement |")
    print("|---|---|---|---|---|")
    for n, p, _ in ARMS:
        if p in DUP_STATS:
            t, u, dp, ag = DUP_STATS[p]
            print("| %s | %d | %d | %d | %s |"
                  % (n, t, u, dp, ("%.1f%%" % ag) if ag is not None else "-"))
    qref = {json.loads(l)["qid"] for l in
            open(ROOT / "data/wsc_s5_v2.jsonl", encoding="utf-8") if l.strip()}
    print("\nqid-set check vs data/wsc_s5_v2.jsonl (576):")
    for n, _, _ in ARMS:
        d = data[n]
        if d:
            print("  %-11s %d q, symdiff=%d -> %s"
                  % (n, len(d), len(set(d) ^ qref),
                     "PASS" if set(d) == qref else "FAIL"))

    print("\n## 1. Headline table\n")
    print("| arm | n | v2.4 x v45 | v2.0 archive | diff | spliced v2.4 |")
    print("|---|---|---|---|---|---|")
    for n, _, arch in ARMS:
        d = data[n]
        if not d:
            continue
        a, aa = acc(d), acc(v20[n])
        sp = SPLICED.get(n)
        print("| %s | %d | %.2f | %.2f | %+.2f | %s |"
              % (n, len(d), a, aa, a - aa, sp if sp is not None else "-"))

    print("\n## 2. Cost / tokens / latency (reader usage; $0.80/M in, $4/M out)\n")
    print("| arm | mean in | mean out | $/q | 576q $ | median latency s |")
    print("|---|---|---|---|---|---|")
    grand = 0.0
    for n, _, _ in ARMS:
        d = data[n]
        if not d:
            continue
        rows = list(d.values())
        mi = st.mean(r.get("usage_input_tokens") or 0 for r in rows)
        mo = st.mean(r.get("usage_output_tokens") or 0 for r in rows)
        lat = st.median(r.get("latency_s") or 0 for r in rows)
        pq = mi / 1e6 * P_IN + mo / 1e6 * P_OUT
        grand += pq * len(rows)
        print("| %s | %,.0f | %,.0f | $%.5f | $%.2f | %.2f |".replace("%,", "%")
              % (n, mi, mo, pq, pq * len(rows), lat))
    print("\nreader-side total (deduped rows only): $%.2f" % grand)

    print("\n## 3. Per question type\n")
    types = sorted({r.get("question_type") for d in data.values()
                    for r in d.values() if r.get("question_type")})
    print("| arm | " + " | ".join(types) + " |")
    print("|---" * (len(types) + 1) + "|")
    for n, _, _ in ARMS:
        d = data[n]
        if not d:
            continue
        cells = []
        for t in types:
            rs = [r for r in d.values() if r.get("question_type") == t]
            cells.append("%.1f" % (sum(1 for r in rs if r["judge_correct"])
                                   / max(1, len(rs)) * 100) if rs else "-")
        print("| %s | " % n + " | ".join(cells) + " |")

    print("\n## 4. Ladder rungs (A2: direction must match v2.0)\n")
    rungs = [("select direct->filter", "direct", "filter"),
             ("certify filter->usability", "filter", "usability"),
             ("compute usability->compile", "usability", "compile"),
             ("ledger+protocol compile->smoc(v45)", "compile", "smoc_v45"),
             ("[aside] compile->smw", "compile", "smw"),
             ("[aside] smw->smoc(v45)", "smw", "smoc_v45"),
             ("[aside] smwplain->smw (protocol price)", "smwplain", "smw"),
             ("[aside] summary->smoc(v45)", "summary", "smoc_v45")]
    for label, b, t in rungs:
        if not data[b] or not data[t]:
            print("### " + label + ": missing\n")
            continue
        d = compare(label, data[b], data[t])
        ab, at = acc(v20[b]), acc(v20[t])
        same = "MATCH" if (d or 0) * (at - ab) > 0 else "MISMATCH"
        print("  v2.0 same rung: %.2f->%.2f = %+.2fpp | direction %s\n"
              % (ab, at, at - ab, same))

    print("\n## 5. A1 structure total & A3 owner-gate equivalence\n")
    if data["smoc_v45"] and data["direct"]:
        compare("A1 direct->smoc(v45)", data["direct"], data["smoc_v45"], margins=())
        print()
    if data["smoc_v45"] and data["smoc_v45g"]:
        compare("A3 smoc(v45)->smoc(v45g) owner gate", data["smoc_v45"],
                data["smoc_v45g"], margins=(2.0, 3.0, 5.0))
        print()

    print("\n## 6. Each arm vs its v2.0 archive (cleaning tax, confounded by store)\n")
    for n, _, _ in ARMS:
        if data[n] and v20[n]:
            compare("%s: v2.0 archive -> b33A v2.4 x v45" % n, v20[n], data[n],
                    margins=())
            print()

    print("\n## 7. Schema-regime isolation probe (first_vs_last only)\n")
    probe = load("results/b33A_filter_v42probe.jsonl")
    if probe:
        fv = lambda d: {k: v for k, v in d.items()
                        if v.get("question_type") == "first_vs_last"}
        a_arch = acc(fv(v20["filter"]))
        a_v45 = acc(fv(data["filter"]))
        a_pr = acc(probe)
        print("| cell | corpus | store | fvl acc |")
        print("|---|---|---|---|")
        print("| v2.0 archive | v2.0 | v42 (has slot_class) | %.2f |" % a_arch)
        print("| b33A probe   | v2.4 | v42 (has slot_class) | %.2f |" % a_pr)
        print("| b33A run     | v2.4 | v45 (no slot_class)  | %.2f |" % a_v45)
        print("\ncorpus effect (archive->probe): %+.2fpp" % (a_pr - a_arch))
        print("store/schema effect (probe->run): %+.2fpp" % (a_v45 - a_pr))
        ev = lambda d: st.mean(int(r.get("evidence_n") or 0) for r in d.values())
        print("mean evidence_n: archive %.2f | probe %.2f | run %.2f"
              % (ev(fv(v20["filter"])), ev(probe), ev(fv(data["filter"]))))
        compare("probe(v42 store) -> run(v45 store), fvl 144",
                probe, fv(data["filter"]), margins=())
    else:
        print("(probe not available)")


if __name__ == "__main__":
    main()
