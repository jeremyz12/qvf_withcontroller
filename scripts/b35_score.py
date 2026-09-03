# -*- coding: utf-8 -*-
"""批 35(部分跑,36/144 链分层抽样)记分器:v2.5 语料 x v46 店 x haiku-4.5 读者。

口径与 scripts/b33A_score.py 相同(直接 import 其 load/acc/sign_p):
- 去重:同一 question_id 保留**首次**出现;qid 集校验对 results/b35_questions_sample36.jsonl;
- 配对 McNemar(精确二项符号检验,同 b33A_score.sign_p);
- 链簇自助 CI:本批 36 链,N=4000,seed 35(协调员指定;33-A 为 N=10000/seed 20260902);
- 成本按 haiku $1.00/M in、$5.00/M out(另给 33-A 旧口径 $0.80/$4.00 换算列)。
对照 = 批 33-A 同臂产物(v2.4 语料 × v45/v45k 店)限制到同一 140 题(题面逐字相同,可配对)。

用法: PYTHONUTF8=1 python scripts/b35_score.py > results/b35_score_out.txt
"""
from __future__ import annotations

import hashlib
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p  # noqa: E402

N_BOOT = 4000            # 协调员指定(33-A 为 10000)
SEED = 35                # 协调员指定(33-A 为 20260902)
P_IN, P_OUT = 1.00, 5.00          # 协调员口径
P_IN33, P_OUT33 = 0.80, 4.00      # 33-A 旧口径(仅换算列)
QREF = "results/b35_questions_sample36.jsonl"
SAMPLE = "results/b35_sample_uids.txt"
ARMS = [
    ("direct",    "results/b35_direct.jsonl",    "results/b33A_direct.jsonl",    "—", "—"),
    ("compile_k", "results/b35_compile_k.jsonl", "results/b33A_compile_k.jsonl", "v46k", "v45k"),
    ("smoc",      "results/b35_smoc.jsonl",      "results/b33A_smoc_v45.jsonl",  "v46",  "v45"),
]
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def cost_row(rows, pi, po):
    mi = st.mean(r.get("usage_input_tokens") or 0 for r in rows)
    mo = st.mean(r.get("usage_output_tokens") or 0 for r in rows)
    lat = st.median(r.get("latency_s") or 0 for r in rows)
    return mi, mo, mi / 1e6 * pi + mo / 1e6 * po, lat


def compare(label, base, test, margins=(), boot=True):
    """与 b33A_score.compare 同估计量,自助参数改为 N_BOOT/SEED。"""
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
    print("### " + label)
    print("  n=%d ti / %d lian | delta=%+.2fpp  b/c=%d/%d  McNemar p=%.4g"
          % (len(keys), len(clusters), delta, b, c, sign_p(b, c)))
    print("  flips: base-right->test-wrong = %d | base-wrong->test-right = %d" % (b, c))
    if not boot:
        return delta
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
    print("  chain sign test %dW/%dL/%dT p=%.4g | cluster boot 95%% CI [%+.2f,%+.2f]pp "
          "(N=%d, seed=%d, %d chains)"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi, N_BOOT, SEED, len(clusters)))
    for m in margins:
        ok = (-m < l90) and (h90 < m)
        print("  TOST +-%.1fpp (90%% CI [%+.2f,%+.2f]): %s"
              % (m, l90, h90, "PASS equivalence" if ok else "FAIL not equivalent"))
    return delta


def main():
    sample = [l.strip() for l in open(ROOT / SAMPLE, encoding="utf-8") if l.strip()]
    qref = {json.loads(l)["qid"] for l in open(ROOT / QREF, encoding="utf-8") if l.strip()}
    data = {n: load(p) for n, p, _, _, _ in ARMS}
    full = {n: load(a) for n, _, a, _, _ in ARMS}
    prev = {n: restrict(full[n], qref) for n, _, _, _, _ in ARMS}

    print("# Batch 35 score — PARTIAL RUN (36/144 chains, stratified 9 per slot)")
    print("# corpus v2.5 (data/wikistate_full_ALL_v25.json) / store v46 (+derived v46k) "
          "/ reader claude-haiku-4-5 / ClaudeJudge (opus-5)\n")
    print("NOT a replacement for the batch 33-A full-576 headline: this is a 140-question "
          "subset on 36 of 144 chains.\n")
    print("Sample: %s (%d uids). Questions: %s (%d q, drawn from data/wsc_s5_v25.jsonl)."
          % (SAMPLE, len(sample), QREF, len(qref)))
    print("Paired reference: batch 33-A rows (corpus v2.4 / stores v45 + v45k) restricted "
          "to the same %d question_ids.\n" % len(qref))

    print("## 0. Dedupe ledger (concurrent duplicate writes -> keep FIRST)\n")
    print("| arm | file | raw rows | deduped | dup rows | first/later verdict agreement |")
    print("|---|---|---|---|---|---|")
    for n, p, a, _, _ in ARMS:
        for tag, pat in (("b35 " + n, p), ("b33A " + n, a)):
            if pat in DUP_STATS:
                t, u, dp, ag = DUP_STATS[pat]
                print("| %s | `%s` | %d | %d | %d | %s |"
                      % (tag, pat, t, u, dp, ("%.1f%%" % ag) if ag is not None else "-"))
    print("\nqid-set check vs %s (%d):" % (QREF, len(qref)))
    for n, _, _, _, _ in ARMS:
        d = data[n]
        if d:
            extra = set(d) - qref
            print("  b35 %-10s %d q, symdiff=%d -> %s"
                  % (n, len(d), len(set(d) ^ qref), "PASS" if set(d) == qref else "FAIL"))
            if extra:
                print("               (rows outside the sample: %d — excluded below)" % len(extra))
        else:
            print("  b35 %-10s MISSING" % n)
    for n, _, a, _, _ in ARMS:
        print("  b33A %-10s covers %d/%d of the sampled qids -> %s"
              % (n, len(prev[n]), len(qref), "PASS" if len(prev[n]) == len(qref) else "FAIL"))
    data = {n: restrict(d, qref) for n, d in data.items()}

    print("\n## 1. Headline table (same 36 chains / same 140 questions in both store columns)\n")
    print("| arm | n | b35 v2.5 x v46(k) | b33A v2.4 x v45(k), same 140 q | diff | "
          "b33A full 576 q (context only) |")
    print("|---|---|---|---|---|---|")
    for n, _, _, s5, s4 in ARMS:
        d = data[n]
        if not d:
            continue
        print("| %s | %d | %.2f (%s) | %.2f (%s) | %+.2f | %.2f |"
              % (n, len(d), acc(d), s5, acc(prev[n]), s4, acc(d) - acc(prev[n]), acc(full[n])))

    print("\n## 2. Cost / tokens / latency (reader-side usage; primary price $%.2f/M in, "
          "$%.2f/M out)\n" % (P_IN, P_OUT))
    print("| arm | n | mean in tok | mean out tok | $/q @1/5 | %dq $ @1/5 | $/q @0.8/4 (legacy) | "
          "median latency s |" % len(qref))
    print("|---|---|---|---|---|---|---|---|")
    grand = grand33 = 0.0
    for n, _, _, _, _ in ARMS:
        d = data[n]
        if not d:
            continue
        rows = list(d.values())
        mi, mo, pq, lat = cost_row(rows, P_IN, P_OUT)
        pq33 = mi / 1e6 * P_IN33 + mo / 1e6 * P_OUT33
        grand += pq * len(rows)
        grand33 += pq33 * len(rows)
        print("| %s | %d | %.0f | %.0f | $%.5f | $%.3f | $%.5f | %.2f |"
              % (n, len(rows), mi, mo, pq, pq * len(rows), pq33, lat))
    print("\nreader-side total over the 3 arms x %d q: $%.3f @1/5  |  $%.3f @0.8/4 "
          "(judge claude-opus-5 billed separately)" % (len(qref), grand, grand33))

    print("\n### 2b. Same table for the b33A (v2.4 x v45) reference rows, same 140 questions\n")
    print("| arm | n | mean in tok | mean out tok | $/q @1/5 | $/q @0.8/4 | median latency s |")
    print("|---|---|---|---|---|---|---|")
    for n, _, _, _, _ in ARMS:
        if not prev[n]:
            continue
        rows = list(prev[n].values())
        mi, mo, pq, lat = cost_row(rows, P_IN, P_OUT)
        pq33 = mi / 1e6 * P_IN33 + mo / 1e6 * P_OUT33
        print("| %s | %d | %.0f | %.0f | $%.5f | $%.5f | %.2f |" % (n, len(rows), mi, mo, pq, pq33, lat))

    print("\n## 3. Per question type (b35 v2.5 accuracy; in brackets b33A v2.4 on the same questions)\n")
    ct = {}
    for t in TYPES:
        ct[t] = sum(1 for r in data["direct"].values() if r.get("question_type") == t)
    print("| arm | " + " | ".join("%s (n=%d)" % (t, ct[t]) for t in TYPES) + " |")
    print("|---" * (len(TYPES) + 1) + "|")
    for n, _, _, _, _ in ARMS:
        d = data[n]
        if not d:
            continue
        cells = []
        for t in TYPES:
            a, b = by_type(d, t), by_type(prev[n], t)
            cells.append(("%.1f (%.1f)" % (a, b)) if a is not None else "-")
        print("| %s | " % n + " | ".join(cells) + " |")

    print("\n## 4. Structure total & ladder rungs inside b35 (v2.5 x v46)\n")
    print("(bootstrap: %d chain clusters, N=%d resamples, seed=%d)\n" % (36, N_BOOT, SEED))
    pairs = [("A1 structure total: direct -> smoc(v46)", "direct", "smoc", ()),
             ("rung 1: direct -> compile_k(v46k)", "direct", "compile_k", (3.0,)),
             ("rung 2: compile_k(v46k) -> smoc(v46) [ledger+protocol]", "compile_k", "smoc", (3.0,))]
    for label, b, t, m in pairs:
        if not data[b] or not data[t]:
            print("### " + label + ": missing\n")
            continue
        d = compare(label, data[b], data[t], margins=m)
        ab, at = acc(prev[b]), acc(prev[t])
        same = "MATCH" if (d or 0) * (at - ab) > 0 else "MISMATCH"
        print("  b33A same rung, same 140 questions: %.2f->%.2f = %+.2fpp | direction %s\n"
              % (ab, at, at - ab, same))

    print("\n## 5. Paired corpus-version comparison on the SAME 140 questions:")
    print("##    b33A (v2.4 corpus x v45/v45k store) -> b35 (v2.5 corpus x v46/v46k store)\n")
    print("| arm | v2.4-store acc | v2.5-store acc | diff pp | flips 2.4-right->2.5-wrong | "
          "flips 2.4-wrong->2.5-right | McNemar p |")
    print("|---|---|---|---|---|---|---|")
    for n, _, _, _, _ in ARMS:
        if not (data[n] and prev[n]):
            continue
        keys = sorted(set(prev[n]) & set(data[n]))
        b = sum(1 for q in keys if prev[n][q]["judge_correct"] and not data[n][q]["judge_correct"])
        c = sum(1 for q in keys if not prev[n][q]["judge_correct"] and data[n][q]["judge_correct"])
        print("| %s | %.2f | %.2f | %+.2f | %d | %d | %.4g |"
              % (n, acc(prev[n]), acc(data[n]), acc(data[n]) - acc(prev[n]), b, c, sign_p(b, c)))
    print()
    for n, _, _, _, _ in ARMS:
        if data[n] and prev[n]:
            compare("%s: v2.4 x v45(k) -> v2.5 x v46(k)" % n, prev[n], data[n], margins=(3.0,))
            print()

    print("\n## 6. 谁在动:把第 5 节按“该链的会话在 v2.4->v2.5 是否真的变了”拆开\n")
    print("语料清洗只动了一部分链。对**未变**的链,v2.4->v2.5 的差 = 重建店 + 读者非确定性的噪声底,")
    print("不是语料效应;只有**变了**的链上的差才可能含语料效应。\n")
    a24 = {e["uid"]: e for e in json.load(open(ROOT / "data/wikistate_full_ALL_v24.json", encoding="utf-8"))}
    a25 = {e["uid"]: e for e in json.load(open(ROOT / "data/wikistate_full_ALL_v25.json", encoding="utf-8"))}
    def h(o):
        return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    chg = {u for u in sample if h(a24[u]["sessions"]) != h(a25[u]["sessions"])}
    unch = set(sample) - chg
    print("链:会话变了 %d / 未变 %d(净删会话 %d 轮)"
          % (len(chg), len(unch), sum(len(a24[u]["sessions"]) - len(a25[u]["sessions"]) for u in chg)))
    print("变了的链: `" + "`, `".join(sorted(chg)) + "`\n")
    print("| arm | 子集 | 链 | 题 | v2.4 acc | v2.5 acc | diff pp | 翻错 | 翻对 | McNemar p |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for n, _, _, _, _ in ARMS:
        if not (data[n] and prev[n]):
            continue
        for tag, us in (("会话变了", chg), ("会话未变", unch)):
            keys = [q for q in sorted(set(prev[n]) & set(data[n]))
                    if (data[n][q].get("uid") or prev[n][q].get("uid")) in us]
            if not keys:
                continue
            p24 = sum(1 for q in keys if prev[n][q]["judge_correct"]) / len(keys) * 100
            p25 = sum(1 for q in keys if data[n][q]["judge_correct"]) / len(keys) * 100
            b = sum(1 for q in keys if prev[n][q]["judge_correct"] and not data[n][q]["judge_correct"])
            c = sum(1 for q in keys if not prev[n][q]["judge_correct"] and data[n][q]["judge_correct"])
            print("| %s | %s | %d | %d | %.2f | %.2f | %+.2f | %d | %d | %.4g |"
                  % (n, tag, len(us), len(keys), p24, p25, p25 - p24, b, c, sign_p(b, c)))
    print("\n注:未变子集上的非零差 = 噪声底(重建 v46 店 + haiku 读者非确定性),"
          "本机既有观测为 run 间抖动 3–4pp。第 5 节的合计差须对着这个底来读。")


if __name__ == "__main__":
    main()
