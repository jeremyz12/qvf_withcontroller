# -*- coding: utf-8 -*-
"""批 33-J 统一分析器($0,纯归档复算)。

对每个对照:题级配对 McNemar(精确符号检验)+ 链级符号检验 + 链簇自助 95% CI;
成本一律由行内 usage token 按 haiku-4.5 / gpt-5-mini 单价折算(与
scripts/cost_usd_recompute.py 同价表)。

用法:python scripts/b33j_analyze.py [j1|j2|j3|j4|all]
"""
from __future__ import annotations

import glob
import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_BOOT = 10000
SEED = 20260902

# $/M tok(scripts/cost_usd_recompute.py 同口径 + OpenAI 官方表)
PRICE = {"claude-haiku-4-5": (1.00, 5.00),
         "gpt-5-mini": (0.25, 2.00),
         "claude-opus-5": (5.00, 25.00),
         "text-embedding-3-small": (0.02, 0.0)}
# 判官侧实测单价(results/judge_cost_measured_20260816.md:5),仅用于
# **补丁之前**落盘、行内没有 judge usage 字段的批次(J4)。
JUDGE_ARCHIVE_RATE = 0.00308


def judge_cost(rows):
    """判官成本:优先按行内 usage token 实算;缺字段的行按归档实测单价补。"""
    ji = jo = 0
    n_meas = n_est = 0
    for r in rows.values():
        if r.get("judge_input_tokens") is not None:
            ji += r["judge_input_tokens"] or 0
            jo += r["judge_output_tokens"] or 0
            n_meas += 1
        else:
            n_est += 1
    pi, po = PRICE["claude-opus-5"]
    usd = ji / 1e6 * pi + jo / 1e6 * po + n_est * JUDGE_ARCHIVE_RATE
    return dict(usd=usd, in_tok=ji, out_tok=jo, n_measured=n_meas,
                n_archive_rate=n_est)


def load(*pats):
    d = {}
    for pat in pats:
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


def acc(rows, keys=None):
    ks = list(keys) if keys is not None else list(rows)
    if not ks:
        return 0.0, 0, 0
    ok = sum(1 for k in ks if rows[k]["judge_correct"])
    return 100 * ok / len(ks), ok, len(ks)


def compare(label, base, test, keys=None):
    ks = sorted(set(base) & set(test)) if keys is None else \
        sorted(set(keys) & set(base) & set(test))
    if not ks:
        print(f"{label}: no overlap")
        return None
    b = sum(1 for q in ks if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in ks if not base[q]["judge_correct"] and test[q]["judge_correct"])
    ab, _, _ = acc(base, ks)
    at, _, _ = acc(test, ks)
    delta = at - ab
    clusters = defaultdict(list)
    for q in ks:
        uid = test[q].get("uid") or base[q].get("uid") or q.split("_")[0]
        clusters[uid].append((int(bool(test[q]["judge_correct"])),
                              int(bool(base[q]["judge_correct"]))))
    cw = cl = ct = 0
    for items in clusters.values():
        d = sum(a - bb for a, bb in items) / len(items)
        cw += d > 0
        cl += d < 0
        ct += d == 0
    rng = random.Random(SEED)
    keysl = list(clusters)
    deltas = []
    for _ in range(N_BOOT):
        samp = [clusters[rng.choice(keysl)] for _ in keysl]
        num = sum(a - bb for items in samp for a, bb in items)
        den = sum(len(items) for items in samp)
        deltas.append(num / den * 100)
    deltas.sort()
    lo, hi = deltas[int(.025 * N_BOOT)], deltas[int(.975 * N_BOOT)]
    print(f"\n### {label}")
    print(f"  n_items={len(ks)}  n_chains={len(clusters)}  "
          f"base={ab:.2f}  test={at:.2f}")
    print(f"  item-level: D={delta:+.2f}pp  b={b}/c={c}  "
          f"McNemar p={sign_p(b, c):.4g}")
    print(f"  chain-level sign test: {cw}W/{cl}L/{ct}T  p={sign_p(cw, cl):.4g}")
    print(f"  chain cluster bootstrap 95% CI: [{lo:+.2f}, {hi:+.2f}]pp")
    return dict(n=len(ks), base=ab, test=at, delta=delta, b=b, c=c,
                p=sign_p(b, c), cw=cw, cl=cl, ct=ct,
                p_cluster=sign_p(cw, cl), ci=[lo, hi])


def cost(rows, model, extra_in_key=None, extra_out_key=None,
         extra_model="claude-haiku-4-5"):
    pi, po = PRICE[model]
    ti = sum(r.get("usage_input_tokens", 0) for r in rows.values())
    to = sum(r.get("usage_output_tokens", 0) for r in rows.values())
    usd = ti / 1e6 * pi + to / 1e6 * po
    ei = eo = 0.0
    if extra_in_key:
        # rtl 建卡:同一 (uid,检索集) 只算一次(cached 行不重复计费)
        seen = set()
        for k, r in rows.items():
            ck = tuple(r.get("retrieved_memory_ids") or [k])
            if ck in seen:
                continue
            seen.add(ck)
            ei += r.get(extra_in_key, 0)
            eo += r.get(extra_out_key, 0)
        epi, epo = PRICE[extra_model]
        usd += ei / 1e6 * epi + eo / 1e6 * epo
    n = len(rows)
    return dict(n=n, in_tok=ti, out_tok=to, extra_in=ei, extra_out=eo,
                usd=usd, usd_per_q=usd / max(1, n),
                mean_in=ti / max(1, n), mean_out=to / max(1, n))


def j4():
    print("\n" + "=" * 70 + "\nJ4  强读者日期粗化 E1(gpt-5-mini smoc,v43 账目)\n" + "=" * 70)
    plain = load("results/b33j/j4_smoc_plain_s*.jsonl")
    patch = load("results/b33j/j4_smoc_patched_s*.jsonl")
    print(f"unpatched n={len(plain)}  patched n={len(patch)}")
    coarse = {k for k, r in patch.items() if r.get("ledger_dates_patched", 0) > 0}
    print(f"实际被改写日期的链所属题数(粗化子层)= {len(coarse)}")
    compare("全 56 题降级层:补丁 vs 不补丁", plain, patch)
    compare("粗化子层(日期真被改写的 10 链/40 题)", plain, patch, coarse)
    arch = load("results/wsc_v2_smoc_v43_gpt5mini.jsonl")
    ks = set(plain)
    print(f"\n  [口径核对] 归档 smoc(F.1)gpt-5-mini 在同 56 题上 "
          f"{acc(arch, ks & set(arch))[0]:.2f};本轮 unpatched "
          f"{acc(plain)[0]:.2f}")
    for lab, rows in (("unpatched", plain), ("patched", patch)):
        c = cost(rows, "gpt-5-mini")
        jc = judge_cost(rows)
        print(f"  cost[{lab}] n={c['n']} in={c['in_tok']:,} out={c['out_tok']:,} "
              f"读者${c['usd']:.3f} + 判官${jc['usd']:.3f}"
              f"(实测{jc['n_measured']}/归档价{jc['n_archive_rate']}) "
              f"= ${c['usd']+jc['usd']:.3f}")


def j2():
    print("\n" + "=" * 70 + "\nJ2  S1/S2 有效性探针(haiku 读者,v44clean 账目)\n" + "=" * 70)
    for tag, name, pred in (("dim1", "S1 dim1_current(当前值)", "预注册:打平 ±5pp"),
                            ("dim4", "S2 dim4_point_in_time(时点值)", "预注册:>= +30pp")):
        s = load(f"results/b33j/j2_{tag}_smoc_s*.jsonl")
        d = load(f"results/b33j/j2_{tag}_direct_s*.jsonl")
        if not s or not d:
            print(f"  [{tag}] 缺文件 smoc={len(s)} direct={len(d)}")
            continue
        print(f"\n-- {name}  ({pred}) --")
        compare(f"{tag}: smoc vs direct", d, s)
        for lab, rows in (("smoc", s), ("direct", d)):
            c = cost(rows, "claude-haiku-4-5")
            jc = judge_cost(rows)
            print(f"  cost[{tag}/{lab}] n={c['n']} mean_in={c['mean_in']:.0f} "
                  f"mean_out={c['mean_out']:.0f} 读者${c['usd']:.3f} + "
                  f"判官${jc['usd']:.3f} = ${c['usd']+jc['usd']:.3f}")


def j3():
    print("\n" + "=" * 70 + "\nJ3  无填充对照梯(30 链 / 120 题)\n" + "=" * 70)
    q120 = {json.loads(l)["qid"] for l in
            (ROOT / "data/b33j_nofiller_30_q120.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()}
    withf = {
        "smoc": load("results/b31_smoc_v22_full.jsonl",
                     "results/b31_smoc_v23.jsonl", "results/b31_smoc_v24.jsonl"),
        "direct": load("results/b33_direct_v24oai_shard*.jsonl"),
        # 有填充的 fullplain 无 v2.4 归档;按任务书用**归档行**,
        # 但须同页标注:该归档跑在 fmtnorm(v2.0 系)语料上,不是 v2.4。
        "fullplain": load("results/b28_fullplain_haiku_fmt.jsonl"),
    }
    nof = {a: load(f"results/b33j/j3_{a}_nofiller_s*.jsonl")
           for a in ("smoc", "direct", "fullplain")}
    print(f"{'arm':<12} {'有填充':>10} {'无填充':>10} {'Δ':>9}   n")
    for a in ("smoc", "direct", "fullplain"):
        w = withf[a]
        nf = nof[a]
        ks = q120 & set(w) & set(nf)
        if not ks:
            print(f"{a:<12} 缺文件 with={len(w)} nofiller={len(nf)}")
            continue
        aw = acc(w, ks)[0]
        an = acc(nf, ks)[0]
        print(f"{a:<12} {aw:10.2f} {an:10.2f} {an - aw:+9.2f}   {len(ks)}")
    for a in ("smoc", "direct", "fullplain"):
        if withf[a] and nof[a]:
            compare(f"{a}: 无填充 vs 有填充(同 120 题)", withf[a], nof[a], q120)
    if nof["smoc"] and nof["direct"]:
        compare("无填充语料内:smoc vs direct", nof["direct"], nof["smoc"], q120)
    if nof["fullplain"] and nof["direct"]:
        compare("无填充语料内:fullplain vs direct", nof["direct"],
                nof["fullplain"], q120)
    for a in ("smoc", "direct", "fullplain"):
        if nof[a]:
            c = cost(nof[a], "claude-haiku-4-5")
            jc = judge_cost(nof[a])
            print(f"  cost[nofiller/{a}] n={c['n']} mean_in={c['mean_in']:.0f} "
                  f"mean_out={c['mean_out']:.0f} 读者${c['usd']:.3f} + "
                  f"判官${jc['usd']:.3f} = ${c['usd']+jc['usd']:.3f}")


def j1():
    print("\n" + "=" * 70 + "\nJ1  读时建账目臂 rtl(576 题,v2.4)\n" + "=" * 70)
    rtl = load("results/b33j/j1_rtl_s*.jsonl")
    smoc = load("results/b31_smoc_v22_full.jsonl", "results/b31_smoc_v23.jsonl",
                "results/b31_smoc_v24.jsonl")
    direct = load("results/b33_direct_v24oai_shard*.jsonl")
    print(f"rtl n={len(rtl)}  smoc n={len(smoc)}  direct n={len(direct)}")
    if not rtl:
        return
    a, ok, n = acc(rtl)
    print(f"rtl acc = {ok}/{n} = {a:.2f}")
    compare("rtl vs direct(读时账目 vs 裸检索)", direct, rtl)
    compare("rtl vs smoc(读时建 vs 写时建)", smoc, rtl)
    byt = defaultdict(lambda: [0, 0, 0, 0])
    for k, r in rtl.items():
        t = r.get("question_type")
        byt[t][0] += bool(r["judge_correct"])
        byt[t][1] += bool(smoc[k]["judge_correct"]) if k in smoc else 0
        byt[t][2] += bool(direct[k]["judge_correct"]) if k in direct else 0
        byt[t][3] += 1
    print(f"\n  {'qtype':<16} {'rtl':>7} {'smoc':>7} {'direct':>7}   n")
    for t, (x, y, z, m) in sorted(byt.items()):
        print(f"  {t:<16} {100*x/m:7.2f} {100*y/m:7.2f} {100*z/m:7.2f}   {m}")
    nrec = [r.get("rtl_n_records", 0) for r in rtl.values()]
    cached = sum(1 for r in rtl.values() if r.get("rtl_catalog_cached"))
    print(f"\n  读时建卡:每题卡片数 mean={sum(nrec)/len(nrec):.1f} "
          f"min={min(nrec)} max={max(nrec)};检索集重复命中缓存 {cached}/{len(rtl)}")
    c = cost(rtl, "claude-haiku-4-5", "rtl_catalog_input_tokens",
             "rtl_catalog_output_tokens")
    print(f"  cost[rtl] 读者 in={c['in_tok']:,} out={c['out_tok']:,};"
          f"建卡 in={c['extra_in']:,.0f} out={c['extra_out']:,.0f};"
          f"合计 ${c['usd']:.3f} (${c['usd_per_q']:.5f}/题)")
    jc = judge_cost(rtl)
    print(f"  cost[rtl 判官] ${jc['usd']:.3f} "
          f"(实测{jc['n_measured']}/归档价{jc['n_archive_rate']});"
          f"rtl 全口径 ${c['usd']+jc['usd']:.3f}")
    cs = cost(smoc, "claude-haiku-4-5")
    cd = cost(direct, "claude-haiku-4-5")
    print(f"  cost[smoc 读端] ${cs['usd']:.3f} (${cs['usd_per_q']:.5f}/题, "
          f"mean_in={cs['mean_in']:.0f});cost[direct] ${cd['usd']:.3f} "
          f"(${cd['usd_per_q']:.5f}/题, mean_in={cd['mean_in']:.0f})")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for f, name in ((j1, "j1"), (j2, "j2"), (j3, "j3"), (j4, "j4")):
        if which in ("all", name):
            try:
                f()
            except Exception as e:  # noqa: BLE001
                print(f"[{name}] SKIP: {type(e).__name__}: {e}")
