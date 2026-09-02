# -*- coding: utf-8 -*-
"""批 33-G4 统计:MINTEval multi_turn_dialogue 外场 smoc vs direct。

口径与 scripts/bootstrap_ci.py 一致:
  - 逐题配对精确符号检验(= 精确 McNemar,b/c 为不一致对);
  - 簇=用户(一个用户 15 题强相关),簇级符号检验 + 簇自助 95% CI;
  - 剂量反应:acc × n_steps_back 深度桶,并做 correct ~ depth 的
    逻辑回归(簇自助给斜率 CI,不用 IID 标准误)。
成本一律由**落盘的 usage token**乘官方单价算出,不估算:
  读者 claude-haiku-4-5 $1/$5 per MTok;判官 claude-opus-5 $5/$25 per MTok;
  建卡 haiku 用量取自卡文件的 usage_in/usage_out;
  嵌入 text-embedding-3-small $0.02/MTok(direct 臂,按实际送检字符估算 token
  上界并明确标注为"估算项",其余全为实测)。

用法:
  PYTHONUTF8=1 python scripts/ext_minteval_analyze.py
"""
from __future__ import annotations

import glob
import io
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from math import comb

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = r"D:\ZZL_cluade"
SMOC = os.path.join(REPO, "results", "ext_minteval_smoc.jsonl")
DIRECT = os.path.join(REPO, "results", "ext_minteval_direct.jsonl")
PROBE = os.path.join(REPO, "data", "external", "minteval_probe.jsonl")
CARDS = os.path.join(REPO, "results", "ext_cards_minteval")
OUT = os.path.join(REPO, "results", "ext_minteval_summary.json")

SEED, N_BOOT = 33, 10000
PRICE = {"claude-haiku-4-5": (1.0, 5.0), "claude-opus-5": (5.0, 25.0)}
BINS = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25),
        (26, 30), (31, 35), (36, 40), (41, 45), (46, 10 ** 6)]


def bin_of(d):
    for i, (lo, hi) in enumerate(BINS):
        if lo <= d <= hi:
            return i
    raise ValueError(d)


def blab(i):
    lo, hi = BINS[i]
    return "%d-%d" % (lo, hi) if hi < 10 ** 6 else "%d+" % lo


def sign_test_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** .5
    return ((c - h) / d * 100, (c + h) / d * 100)


def load(path):
    rows = []
    for l in open(path, encoding="utf-8"):
        l = l.strip()
        if l:
            rows.append(json.loads(l))
    return rows


# ── 官方口径副指标:归一化 EM / token-F1(MINTEval _common.py 的度量族) ──
# normalize_answer 语义重建:逗号→空格、去冠词 a/an/the 与 and、去标点、
# 小写、压空白。官方 EM = 归一化后**整串相等**;我们的两臂都不按官方
# "\boxed{} + 候选清单" 协议作答,故额外报一个宽松的"含金串"命中率。
_PUNC = re.compile(r"[^a-z0-9_ ]+")
_ART = {"a", "an", "the", "and"}


def norm(s):
    t = str(s).replace(",", " ").lower()
    t = _PUNC.sub(" ", t)
    return " ".join(w for w in t.split() if w not in _ART)


def final_answer(row):
    """smoc 臂答案已由 parse_answer 取过 ANSWER: 行;direct 臂是自由文本。
    两臂统一再剥一次 'ANSWER:' 前缀,不做别的加工。"""
    a = str(row.get("answer") or "")
    m = re.search(r"ANSWER:\s*(.+)", a)
    return (m.group(1) if m else a).strip()


def em_f1(pred, gold):
    """-> (官方严格 EM, 宽松含金串, token-F1)"""
    p, g = norm(pred), norm(gold)
    em = int(p == g)
    cont = int(p == g or (" %s " % g) in (" %s " % p))
    pt, gt = p.split(), g.split()
    if not pt or not gt:
        return em, cont, 0.0
    common = Counter(pt) & Counter(gt)
    ns = sum(common.values())
    if ns == 0:
        return em, cont, 0.0
    prec, rec = ns / len(pt), ns / len(gt)
    return em, cont, 2 * prec * rec / (prec + rec)


def main():
    probe = {r["qid"]: r for r in load(PROBE)}
    arms = {}
    for name, path in (("smoc", SMOC), ("direct", DIRECT)):
        if not os.path.exists(path):
            print("MISSING", path)
            continue
        rows = {r["question_id"]: r for r in load(path)}
        arms[name] = rows
        print("%-7s rows=%d" % (name, len(rows)))
    if len(arms) < 2:
        print("need both arms")
        return 1

    qids = sorted(set(arms["smoc"]) & set(arms["direct"]) & set(probe))
    print("paired questions: %d" % len(qids))
    depth = {q: int(probe[q]["meta"]["n_steps_back"]) for q in qids}
    uid = {q: probe[q]["uid"] for q in qids}
    corr = {a: {q: bool(arms[a][q].get("judge_correct")) for q in qids}
            for a in arms}
    emf = {a: {q: em_f1(final_answer(arms[a][q]), probe[q]["gold"]) for q in qids}
           for a in arms}

    summ = {"n_questions": len(qids), "n_users": len(set(uid.values())),
            "arms": {}, "depth": {}, "cost": {}}

    # ── 总体 acc ──
    print("\n== 总体(ClaudeJudge 主指标 / 官方口径 EM,F1 副指标) ==")
    for a in ("smoc", "direct"):
        k = sum(corr[a].values())
        lo, hi = wilson(k, len(qids))
        em = sum(emf[a][q][0] for q in qids) / len(qids) * 100
        ct_ = sum(emf[a][q][1] for q in qids) / len(qids) * 100
        f1 = sum(emf[a][q][2] for q in qids) / len(qids) * 100
        print("%-7s judge %3d/%d = %5.1f%%  [Wilson %.1f, %.1f]   "
              "官方严格EM %4.1f%%  含金串 %4.1f%%  F1 %4.1f"
              % (a, k, len(qids), k / len(qids) * 100, lo, hi, em, ct_, f1))
        summ["arms"][a] = {"n": len(qids), "judge_correct": k,
                           "acc": k / len(qids) * 100, "wilson": [lo, hi],
                           "em_strict": em, "em_contains": ct_, "f1": f1}

    # ── 失败形态:弃答率 / 协议偏差(输出预算截断) ──
    _ABST = re.compile(
        r"unable to determine|i don'?t have|i do not have|no record|"
        r"not (?:available|recorded|present|found)|cannot determine|"
        r"insufficient (?:data|information)|isn'?t (?:part of|available)",
        re.I)
    print("\n== 失败形态 ==")
    for a in ("smoc", "direct"):
        ab = sum(1 for q in qids if _ABST.search(str(arms[a][q].get("answer") or "")))
        dv = sum(1 for q in qids if arms[a][q].get("protocol_deviation"))
        print("%-7s 弃答 %3d/%d = %4.1f%%   协议偏差(无 ANSWER 行)%3d = %4.1f%%"
              % (a, ab, len(qids), ab / len(qids) * 100, dv, dv / len(qids) * 100))
        summ["arms"][a]["abstain_rate"] = ab / len(qids) * 100
        summ["arms"][a]["protocol_deviation_rate"] = dv / len(qids) * 100

    # ── 写侧话题覆盖:账目里有没有该属性的料 ──
    # 题面形如 "... value for 'prioritization required' in their \"Actionability
    # Format\" preference N ... ago"。取单引号里的属性词 + 双引号里的偏好族,
    # 数账目里 slot/claim 命中任一内容词的行数——区分"店里根本没有"与
    # "店里有但读者没答出来"。
    _ATTR = re.compile(r"'([^']+)'")
    _FAM = re.compile(r'"([^"]+)"')
    cov = []
    ledger_cache = {}
    try:
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        sys.path.insert(0, REPO)
        from repro_batch3 import render_card_ledger  # noqa: E402
        ents = {e["uid"]: e for e in json.load(
            open(os.path.join(REPO, "data", "external",
                              "minteval_cardable.json"), encoding="utf-8"))}
        for q in qids:
            u = uid[q]
            if u not in ledger_cache:
                ledger_cache[u] = render_card_ledger(
                    u, ents[u], cards_dir=CARDS).lower()
            led = ledger_cache[u]
            qt = probe[q]["question"].split("\n")[0]
            words = set()
            for m in list(_ATTR.findall(qt)) + list(_FAM.findall(qt)):
                words |= {w for w in re.split(r"[^a-z]+", m.lower())
                          if len(w) > 3}
            hit = sum(1 for line in led.splitlines()
                      if any(w in line for w in words))
            cov.append(hit)
        cov.sort()
        print("账目话题命中行数(每题):0 命中 %d/%d = %.1f%%,中位 %d,p90 %d"
              % (sum(1 for x in cov if x == 0), len(cov),
                 sum(1 for x in cov if x == 0) / len(cov) * 100,
                 cov[len(cov) // 2], cov[int(.9 * len(cov))]))
        summ["ledger_topic_hits"] = {
            "zero_hit_pct": sum(1 for x in cov if x == 0) / len(cov) * 100,
            "median": cov[len(cov) // 2], "p90": cov[int(.9 * len(cov))]}
    except Exception as e:  # noqa: BLE001
        print("话题覆盖统计跳过:%s: %s" % (type(e).__name__, e))

    # ── 配对检验 ──
    b = sum(1 for q in qids if corr["smoc"][q] and not corr["direct"][q])
    c = sum(1 for q in qids if corr["direct"][q] and not corr["smoc"][q])
    p_item = sign_test_p(b, c)
    byu = defaultdict(list)
    for q in qids:
        byu[uid[q]].append((int(corr["smoc"][q]), int(corr["direct"][q])))
    cw = sum(1 for v in byu.values()
             if sum(x - y for x, y in v) > 0)
    cl = sum(1 for v in byu.values() if sum(x - y for x, y in v) < 0)
    ct = len(byu) - cw - cl
    p_clu = sign_test_p(cw, cl)
    delta = (sum(corr["smoc"].values()) - sum(corr["direct"].values())) / len(qids) * 100
    rng = random.Random(SEED)
    users = sorted(byu)
    boots = []
    for _ in range(N_BOOT):
        samp = [byu[users[rng.randrange(len(users))]] for _ in users]
        n = sum(len(v) for v in samp)
        d = sum(x - y for v in samp for x, y in v)
        boots.append(d / n * 100)
    boots.sort()
    ci = (boots[int(.025 * N_BOOT)], boots[int(.975 * N_BOOT)])
    print("\n== smoc − direct 配对 ==")
    print("delta = %+.2f pp   McNemar 精确(b=%d 只 smoc 对 / c=%d 只 direct 对)p=%.4g"
          % (delta, b, c, p_item))
    print("簇级(用户)符号检验 %d 胜 / %d 负 / %d 平  p=%.4g" % (cw, cl, ct, p_clu))
    print("簇自助 95%% CI = [%+.2f, %+.2f] pp  (n_clusters=%d, B=%d)"
          % (ci[0], ci[1], len(users), N_BOOT))
    summ["paired"] = {"delta_pp": delta, "mcnemar_b": b, "mcnemar_c": c,
                      "p_item": p_item, "cluster_w": cw, "cluster_l": cl,
                      "cluster_t": ct, "p_cluster": p_clu,
                      "cluster_ci95": list(ci), "n_clusters": len(users)}

    # 单臂簇自助 CI
    for a in ("smoc", "direct"):
        bs = []
        for _ in range(N_BOOT):
            samp = [byu[users[rng.randrange(len(users))]] for _ in users]
            n = sum(len(v) for v in samp)
            k = sum((x if a == "smoc" else y) for v in samp for x, y in v)
            bs.append(k / n * 100)
        bs.sort()
        summ["arms"][a]["cluster_ci95"] = [bs[int(.025 * N_BOOT)],
                                           bs[int(.975 * N_BOOT)]]
        print("%-7s 簇自助 95%% CI = [%.1f, %.1f]" % (a, *summ["arms"][a]["cluster_ci95"]))

    # ── 剂量反应 ──
    print("\n== acc × n_steps_back(剂量反应) ==")
    print("%-8s %5s %6s %6s %6s" % ("bin", "n", "users", "smoc", "direct"))
    for i in range(len(BINS)):
        qs = [q for q in qids if bin_of(depth[q]) == i]
        if not qs:
            continue
        s = sum(corr["smoc"][q] for q in qs) / len(qs) * 100
        d = sum(corr["direct"][q] for q in qs) / len(qs) * 100
        nu = len({uid[q] for q in qs})
        print("%-8s %5d %6d %6.1f %6.1f" % (blab(i), len(qs), nu, s, d))
        summ["depth"][blab(i)] = {"n": len(qs), "n_users": nu,
                                  "smoc": s, "direct": d}

    # 逻辑回归 correct ~ depth(簇自助 CI)
    def logit_slope(idx_users, arm):
        X, Y = [], []
        for u in idx_users:
            for q in sorted(q for q in qids if uid[q] == u):
                X.append(depth[q])
                Y.append(1.0 if corr[arm][q] else 0.0)
        X = np.asarray(X, float)
        Y = np.asarray(Y, float)
        if Y.min() == Y.max():
            return float("nan")
        w = np.zeros(2)
        A = np.column_stack([np.ones_like(X), X])
        for _ in range(200):
            p = 1 / (1 + np.exp(-A @ w))
            g = A.T @ (Y - p)
            W = p * (1 - p) + 1e-9
            H = A.T @ (A * W[:, None]) + 1e-6 * np.eye(2)
            step = np.linalg.solve(H, g)
            w += step
            if np.max(np.abs(step)) < 1e-9:
                break
        return float(w[1])

    print("\n== correct ~ n_steps_back 逻辑回归斜率(每 +1 步) ==")
    for a in ("smoc", "direct"):
        s0 = logit_slope(users, a)
        bs = []
        for _ in range(1000):
            su = [users[rng.randrange(len(users))] for _ in users]
            v = logit_slope(su, a)
            if v == v:
                bs.append(v)
        bs.sort()
        if s0 != s0 or len(bs) < 20:
            print("%-7s 该臂全对或全错(或自助样本过少),斜率不可估" % a)
            summ["depth"].setdefault("_slope", {})[a] = None
            continue
        lo, hi = bs[int(.025 * len(bs))], bs[int(.975 * len(bs))]
        print("%-7s beta=%+.4f  簇自助 95%% CI [%+.4f, %+.4f]  OR/步=%.3f"
              % (a, s0, lo, hi, float(np.exp(s0))))
        summ["depth"].setdefault("_slope", {})[a] = {
            "beta": s0, "ci95": [lo, hi], "odds_ratio_per_step": float(np.exp(s0))}

    # ── 成本(全部由 usage token 计) ──
    print("\n== 成本(实测 usage token × 官方单价) ==")
    hi_, ho_ = PRICE["claude-haiku-4-5"]
    build_in = build_out = 0
    ncards = []
    for f in glob.glob(os.path.join(CARDS, "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        build_in += d.get("usage_in", 0)
        build_out += d.get("usage_out", 0)
        ncards.append(len(d.get("records", [])))
    build_usd = build_in / 1e6 * hi_ + build_out / 1e6 * ho_
    print("建卡:%d 店  卡数 min/med/max %d/%d/%d  in=%d out=%d  = $%.2f  ($%.3f/店)"
          % (len(ncards), min(ncards), sorted(ncards)[len(ncards) // 2], max(ncards),
             build_in, build_out, build_usd, build_usd / max(1, len(ncards))))
    summ["cost"]["build"] = {"n_stores": len(ncards), "in": build_in,
                             "out": build_out, "usd": build_usd,
                             "cards_median": sorted(ncards)[len(ncards) // 2]}
    for a in ("smoc", "direct"):
        ti = sum(arms[a][q].get("usage_input_tokens", 0) or 0 for q in qids)
        to = sum(arms[a][q].get("usage_output_tokens", 0) or 0 for q in qids)
        usd = ti / 1e6 * hi_ + to / 1e6 * ho_
        lat = [arms[a][q].get("latency_s", 0) or 0 for q in qids]
        print("%-7s 读者 in=%d out=%d  = $%.2f  = $%.4f/题  (in %.0f tok/题, "
              "中位延迟 %.1fs)" % (a, ti, to, usd, usd / len(qids),
                                   ti / len(qids), sorted(lat)[len(lat) // 2]))
        summ["cost"][a] = {"reader_in": ti, "reader_out": to,
                           "reader_usd": usd, "usd_per_q": usd / len(qids),
                           "in_tok_per_q": ti / len(qids),
                           "latency_median_s": sorted(lat)[len(lat) // 2]}
    # 判官成本:优先用 *.judgeusage.json 的实测累计(ext_minteval_run 记的),
    # 缺失时回落到逐行 judge_input_tokens 字段。
    oi, oo = PRICE["claude-opus-5"]
    ji = jo = jc = 0
    for f in glob.glob(os.path.join(REPO, "results",
                                    "ext_minteval_*.judgeusage.json")):
        d = json.load(open(f, encoding="utf-8"))
        ji += d.get("input_tokens", 0)
        jo += d.get("output_tokens", 0)
        jc += d.get("calls", 0)
    if not jc:
        for a in ("smoc", "direct"):
            for q in qids:
                ji += arms[a][q].get("judge_input_tokens") or 0
                jo += arms[a][q].get("judge_output_tokens") or 0
                jc += 1
    if jc:
        jusd = ji / 1e6 * oi + jo / 1e6 * oo
        print("判官 claude-opus-5:calls=%d in=%d out=%d = $%.2f ($%.4f/题·臂)"
              % (jc, ji, jo, jusd, jusd / max(1, jc)))
        summ["cost"]["judge"] = {"calls": jc, "input_tokens": ji,
                                 "output_tokens": jo, "usd": jusd}
        tot = build_usd + jusd + sum(summ["cost"][a]["reader_usd"]
                                     for a in ("smoc", "direct"))
        print("合计(建卡+两臂读者+判官)= $%.2f" % tot)
        summ["cost"]["total_usd"] = tot
    json.dump(summ, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
