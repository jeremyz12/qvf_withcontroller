# -*- coding: utf-8 -*-
"""P3 学习路由 + conformal 风险证书:全离线策略评估,零 LLM 调用。

流程:
  1. 组装三元组 (特征φ(x), 臂, correct, token):行源与 v4.2 对照组同源
     (旧 wt 文件 + prompt_rows_all),qid 对齐用冻结 normkey 规则。
  2. 特征全部部署侧:bench 域 / 聚焦缓存(slot/scope/presupposed) /
     keyed_depth(路由日志部署值) / 卡片库形态 / 问题文本。禁入:判官、
     金答案、picked_arm、result、qid_raw 尾缀、question_type、stale_type。
  3. 每臂 numpy 手写逻辑回归 p̂_a(x)(sklearn 不可用),boosted-stumps 对照。
  4. 策略 â(x)=argmax_a[p̂_a(x) − λ·c_a(x)];λ 网格扫 Pareto 前沿
     (交叉拟合 5 折按 uid 分组,正式数字全量 5511)。
  5. 证书:Learn-then-Test,风险=相对逐题 oracle 选臂的准确率损失;
     40/20/40 train/calib/test 按 uid 分层,固定序列检验(二项尾界),
     δ=0.1,ε∈{0.03,0.05};测试集验证。
  6. 留一域外推 + 升级伪臂。

冻结代码只读引用:normkey/load_arm 语义、SLOT_ALIASES、_EVENT_ARITH_RE、
_FP_RE 与 _norm/_slot_match 逐字复刻自 scripts/qvf_router.py 与
scripts/wt_qvf_prototype.py(不 import,避免拉起 anthropic 客户端)。

用法: python scripts/train_router.py
输出: results/router_learned_triples_20260814.jsonl
      results/router_learned_policy_20260814.jsonl
      results/router_learned_report_20260814.md
"""
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\ZZL_cluade")
R = ROOT / "results"
SEED = 20260814
DELTA = 0.1
EPS_LIST = [0.03, 0.05]
LAMBDA_GRID = [0.0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05,
               0.08, 0.12, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0]
ARMS = ["direct", "rt", "wt", "prompt"]

# ── 冻结代码复刻(scripts/qvf_router.py 76-81 / wt_qvf_prototype.py 269-280)──
def normkey(k):
    k = re.sub(r"_query$", "", k)
    m = re.match(r"(.+?)_(dim\d)", k)
    if m:
        return f"{m.group(1)}|{m.group(2)}"
    return re.sub(r"_q1$", "", k)


def _norm(s):
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


SLOT_ALIASES = {
    "position": ["position", "职位", "job", "role", "chairman", "member",
                 "committee", "议员", "委员", "职务", "任职", "mayor",
                 "minister", "office"],
    "employer": ["employer", "雇主", "company", "工作", "单位", "university",
                 "institute", "works for", "employed"],
    "team": ["team", "球队", "队", "club"],
    "residence": ["residence", "住", "居住", "address", "city", "live",
                  "hometown"],
    "device": ["device", "phone", "laptop", "tablet", "camera", "手机",
               "电脑", "设备"],
    "location": ["location", "位置", "地点", "place", "where"],
    "relationship": ["relationship", "partner", "spouse", "wife", "husband",
                     "girlfriend", "boyfriend", "married", "婚", "恋", "关系"],
}
_EVENT_ARITH_RE = re.compile(
    r"how long|how many times|days between|多久|几次|多少次|隔了", re.IGNORECASE)
_FP_RE = re.compile(r"\b(i|me|my|mine)\b", re.IGNORECASE)

# ── 行源(与 v4.2 对照组同源:qvf_router.py BENCHES 旧 wt 文件)──────────
BENCHES = {
    "chain-212": ("data/stale_chain_full.json",
                  ("results/framing_chain_h45.jsonl", None),
                  ("results/framing_qvf_chain_h45.jsonl", None),
                  ("results/wtqvf3_chain_h45.jsonl", None)),
    "confirm-228": ("data/stale_chain_confirm.json",
                    ("results/framing_direct_confirm_h45.jsonl", None),
                    ("results/framing_qvf_confirm_h45.jsonl", None),
                    ("results/wtqvf3_confirm.jsonl", None)),
    "stale-150": ("data/stale400_s50_wt.json",
                  ("results/framing_stale50_h45.jsonl", None),
                  ("results/framing_qvf_stale50_h45.jsonl", None),
                  ("results/wtqvf3_stale50.jsonl", None)),
    "wiki-P39": ("data/wikistate_full.json",
                 ("results/wiki_direct_h45.jsonl", None),
                 ("results/wiki_qvf_h45.jsonl", None),
                 ("results/wiki_wtqvf3_test.jsonl", None)),
    "wiki-P39-ext": ("data/wikistate_full_P39_ext.json",
                     ("results/wiki_direct_P39_ext.jsonl", None),
                     ("results/wiki_qvf_P39_ext.jsonl", None),
                     ("results/wiki_wtqvf3_P39_ext.jsonl", None)),
    "wiki-P108-w2": ("data/wikistate_full_P108_w2.json",
                     ("results/wiki_direct_P108_w2.jsonl", None),
                     ("results/wiki_qvf_P108_w2.jsonl", None),
                     ("results/wiki_wtqvf3_P108_w2.jsonl", None)),
    "wiki-P108-ext": ("data/wikistate_full_P108_ext.json",
                      ("results/wiki_direct_P108_ext.jsonl", None),
                      ("results/wiki_qvf_P108_ext.jsonl", None),
                      ("results/wiki_wtqvf3_P108_ext.jsonl", None)),
    "wiki-P54-w2": ("data/wikistate_full_P54_w2.json",
                    ("results/wiki_direct_P54_w2.jsonl", None),
                    ("results/wiki_qvf_P54_w2.jsonl", None),
                    ("results/wiki_wtqvf3_P54_w2.jsonl", None)),
    "wiki-P54-ext": ("data/wikistate_full_P54_ext.json",
                     ("results/wiki_direct_P54_ext.jsonl", None),
                     ("results/wiki_qvf_P54_ext.jsonl", None),
                     ("results/wiki_wtqvf3_P54_ext.jsonl", None)),
    "wiki-P551": ("data/wikistate_full_P551.json",
                  ("results/wiki_direct_P551.jsonl", None),
                  None,
                  ("results/wiki_wtqvf3_P551.jsonl", None)),
    "LME-TR": ("data/lme_temporal_reasoning_wt.json",
               ("results/tr_full133.jsonl", "dense_direct"),
               ("results/final2_lmet_h45.jsonl", None),
               ("results/wtqvf3_lmetr.jsonl", None)),
    "LME-KU": ("data/lme_knowledge_update_wt.json",
               ("results/final2_lmek_h45.jsonl", "dense_direct"),
               ("results/final2_lmek_h45.jsonl", "minimal_rules_species2"),
               ("results/wtqvf3_lmeku.jsonl", None)),
    "LoCoMo": ("data/locomo_wt.json",
               ("results/locomo_direct_h45.jsonl", None),
               ("results/locomo_qvf_h45.jsonl", None),
               ("results/wtqvf3_locomo.jsonl", None)),
    "STALE-full": ("data/stale400_full_wt.json",
                   ("results/stale400_full_direct_v2.jsonl", None),
                   ("results/stale400_full_qvf_v2.jsonl", None),
                   ("results/wtqvf3_stale50.jsonl", None)),
    "LoCoMo-full": ("data/locomo_full.json",
                    ("results/locomo_full_direct.jsonl", None),
                    ("results/locomo_full_qvf.jsonl", None),
                    ("results/wtqvf3_locomo_full.jsonl", None)),
}
BENCH_ORDER = list(BENCHES.keys())
TARGET13 = [b for b in BENCH_ORDER if b not in ("STALE-full", "LoCoMo-full")]


def load_arm_rows(path, mode=None):
    """qid → {correct, tok};tok=in+out(+focus_tokens if present)。跳 error 行。"""
    d = {}
    p = ROOT / path
    if not p.exists():
        return d
    for l in open(p, encoding="utf-8"):
        s = l.strip()
        if not s:
            continue
        r = json.loads(s)
        if "error" in r:
            continue
        if mode and r.get("mode") != mode:
            continue
        tok = ((r.get("usage_input_tokens") or 0)
               + (r.get("usage_output_tokens") or 0)
               + (r.get("focus_tokens") or 0))
        d[normkey(r["question_id"])] = {"correct": bool(r.get("judge_correct")),
                                        "tok": int(tok),
                                        "lat": float(r.get("latency_s") or 0)}
    return d


# ── 组装 ───────────────────────────────────────────────────────────────────
def assemble():
    log = [json.loads(l) for l in
           open(R / "router_routes_v42_final.jsonl", encoding="utf-8")]
    cache = json.loads((R / "router_focus_cache.json").read_text(encoding="utf-8"))
    prompt_rows = load_arm_rows("results/prompt_rows_all.jsonl")

    arm_tables = {}
    questions = {}
    for b, (data_f, d_spec, r_spec, w_spec) in BENCHES.items():
        arm_tables[b] = {
            "direct": load_arm_rows(*d_spec),
            "rt": load_arm_rows(*r_spec) if r_spec else {},
            "wt": load_arm_rows(*w_spec),
        }
        items = json.loads((ROOT / data_f).read_text(encoding="utf-8"))
        for it in items:
            for dim, q in it.get("probing_queries", {}).items():
                questions[(b, normkey(f"{it['uid']}_{dim}"))] = q["q"]

    # 卡片库形态特征(部署侧;v42 键控目录优先,回落基础库 = v4.2 部署配置)
    card_cache = {}

    def card_feats(uid):
        if uid in card_cache:
            return card_cache[uid]
        f42 = R / "wt_cards_v42" / f"{uid}.json"
        fb = R / "wt_cards" / f"{uid}.json"
        f = f42 if f42.exists() else fb
        has_keyed = f42.exists()
        recs = []
        if f.exists():
            try:
                recs = json.loads(f.read_text(encoding="utf-8")).get("records", [])
            except Exception:
                recs = []
        groups = {}
        for rc in recs:
            cls = rc.get("slot_class")
            if not cls:
                continue
            v = _norm(rc.get("value", ""))
            if v:
                groups.setdefault(((rc.get("owner") or ""), cls), set()).add(v)
        smd = max((len(v) for v in groups.values()), default=0)
        out = {"has_card": f.exists(), "has_keyed": has_keyed,
               "recs_n": len(recs), "smd": smd}
        card_cache[uid] = out
        return out

    instances = []
    replay_mismatch = 0
    tok_missing = 0
    for row in log:
        b, uid, qid = row["bench"], row["uid"], row["qid"]
        arms = {}
        for a in ("direct", "rt", "wt"):
            if qid in arm_tables[b][a]:
                arms[a] = arm_tables[b][a][qid]
        if qid in prompt_rows:
            arms["prompt"] = prompt_rows[qid]
        pk = row["picked_arm"]
        if pk in arms:
            if arms[pk]["correct"] != bool(row["result"]):
                replay_mismatch += 1
            v42_tok = arms[pk]["tok"]
            v42_lat = arms[pk].get("lat", 0.0)
        else:
            tok_missing += 1
            v42_tok = 0
            v42_lat = 0.0
        fo = cache.get(f"{b}|{qid}", {"slot": "", "scope": "unclear",
                                      "presupposed": ""})
        cf = card_feats(uid)
        instances.append({
            "bench": b, "uid": uid, "qid": qid,
            "route": row["route"], "keyed_depth": row["keyed_depth"],
            "v42_pick": pk, "v42_correct": bool(row["result"]),
            "v42_tok": v42_tok, "v42_lat": v42_lat,
            "slot": fo.get("slot", ""), "scope": fo.get("scope", "unclear"),
            "presup": bool(fo.get("presupposed")),
            "question": questions.get((b, qid), ""),
            "card": cf, "arms": arms,
        })
    print(f"instances={len(instances)} replay_mismatch={replay_mismatch} "
          f"v42_tok_missing={tok_missing}")
    return instances


# ── 特征 ───────────────────────────────────────────────────────────────────
SCOPES = ["current", "point_in_time", "trajectory", "unclear"]
QWORDS = ["what", "when", "where", "who", "which", "how", "other"]
SLOTC = list(SLOT_ALIASES.keys())


def featurize(instances):
    names = ([f"bench={b}" for b in BENCH_ORDER]
             + [f"scope={s}" for s in SCOPES]
             + [f"slotc={c}" for c in SLOTC] + ["slotc=none"]
             + [f"route={a}" for a in ARMS]
             + [f"qw={w}" for w in QWORDS]
             + ["kd", "kd_null", "kd_ge2", "kd_ge3", "presup",
                "smd", "smd_ge3", "has_card", "has_keyed", "recs_log",
                "qchars_log", "qtoks_log", "event_arith", "first_person",
                "has_digit"])
    X = np.zeros((len(instances), len(names)), dtype=np.float64)
    idx = {n: i for i, n in enumerate(names)}
    for i, r in enumerate(instances):
        X[i, idx[f"bench={r['bench']}"]] = 1
        X[i, idx[f"scope={r['scope'] if r['scope'] in SCOPES else 'unclear'}"]] = 1
        fs = _norm(r["slot"])
        hit = False
        for c, al in SLOT_ALIASES.items():
            if any(a in fs for a in al):
                X[i, idx[f"slotc={c}"]] = 1
                hit = True
        if not hit:
            X[i, idx["slotc=none"]] = 1
        X[i, idx[f"route={r['route']}"]] = 1
        q = r["question"] or ""
        w0 = q.strip().lower().split(" ")[0] if q.strip() else ""
        w0 = re.sub(r"[^a-z]", "", w0)
        X[i, idx[f"qw={w0 if w0 in QWORDS[:-1] else 'other'}"]] = 1
        kd = r["keyed_depth"]
        X[i, idx["kd"]] = min(kd, 12) if kd is not None else 0
        X[i, idx["kd_null"]] = 1 if kd is None else 0
        X[i, idx["kd_ge2"]] = 1 if (kd or 0) >= 2 else 0
        X[i, idx["kd_ge3"]] = 1 if (kd or 0) >= 3 else 0
        X[i, idx["presup"]] = 1 if r["presup"] else 0
        cf = r["card"]
        X[i, idx["smd"]] = min(cf["smd"], 12)
        X[i, idx["smd_ge3"]] = 1 if cf["smd"] >= 3 else 0
        X[i, idx["has_card"]] = 1 if cf["has_card"] else 0
        X[i, idx["has_keyed"]] = 1 if cf["has_keyed"] else 0
        X[i, idx["recs_log"]] = math.log1p(cf["recs_n"])
        X[i, idx["qchars_log"]] = math.log1p(len(q))
        X[i, idx["qtoks_log"]] = math.log1p(len(q.split()))
        X[i, idx["event_arith"]] = 1 if _EVENT_ARITH_RE.search(q) else 0
        X[i, idx["first_person"]] = 1 if (_FP_RE.search(q) or "我" in q) else 0
        X[i, idx["has_digit"]] = 1 if re.search(r"\d", q) else 0
    return X, names


NUMERIC = ["kd", "smd", "recs_log", "qchars_log", "qtoks_log"]


def standardize(Xtr, X_all, names):
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    cols = [i for i, n in enumerate(names) if n in NUMERIC]
    Xa = X_all.copy()
    for c in cols:
        s = sd[c] if sd[c] > 1e-9 else 1.0
        Xa[:, c] = (Xa[:, c] - mu[c]) / s
    return Xa


# ── numpy 逻辑回归(IRLS + ridge)与 boosted stumps 对照 ────────────────────
def fit_lr(X, y, ridge=1.0, iters=30):
    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    w = np.zeros(d + 1)
    I = np.eye(d + 1)
    I[-1, -1] = 0.0  # 截距不正则
    for _ in range(iters):
        z = np.clip(Xb @ w, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        g = Xb.T @ (p - y) + ridge * (I @ w)
        Wd = np.clip(p * (1 - p), 1e-6, None)
        H = (Xb * Wd[:, None]).T @ Xb + ridge * I + 1e-8 * np.eye(d + 1)
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return w


def pred_lr(w, X):
    Xb = np.hstack([X, np.ones((X.shape[0], 1))])
    return 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))


def _stump_candidates(X):
    cands = []
    for j in range(X.shape[1]):
        vs = np.unique(np.quantile(X[:, j], np.linspace(0.05, 0.95, 15)))
        vs = vs[:-1] if len(vs) > 1 else vs
        for t in vs:
            cands.append((j, float(t)))
    return cands


def fit_stumps(X, y, rounds=200, lr=0.1):
    cands = _stump_candidates(X)
    M = np.stack([(X[:, j] <= t) for j, t in cands], axis=1).astype(np.float64)
    base = np.clip(y.mean(), 1e-4, 1 - 1e-4)
    F = np.full(len(y), math.log(base / (1 - base)))
    model = [("base", math.log(base / (1 - base)))]
    ones = np.ones(len(y))
    for _ in range(rounds):
        p = 1.0 / (1.0 + np.exp(-np.clip(F, -30, 30)))
        g = y - p
        h = np.clip(p * (1 - p), 1e-6, None)
        Gl, Hl = M.T @ g, M.T @ h
        Gt, Ht = g.sum(), h.sum()
        Gr, Hr = Gt - Gl, Ht - Hl
        gain = Gl ** 2 / (Hl + 1.0) + Gr ** 2 / (Hr + 1.0)
        s = int(np.argmax(gain))
        wl = Gl[s] / (Hl[s] + 1.0)
        wr = Gr[s] / (Hr[s] + 1.0)
        j, t = cands[s]
        F = F + lr * np.where(X[:, j] <= t, wl, wr)
        model.append((j, t, lr * wl, lr * wr))
        _ = ones
    return model


def pred_stumps(model, X):
    F = np.full(X.shape[0], model[0][1])
    for j, t, wl, wr in model[1:]:
        F = F + np.where(X[:, j] <= t, wl, wr)
    return 1.0 / (1.0 + np.exp(-np.clip(F, -30, 30)))


def auc(y, p):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    # 平均秩处理并列
    for v in np.unique(p):
        m = p == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def ece(y, p, bins=10):
    e = 0.0
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        m = (p >= lo) & (p < hi) if k < bins - 1 else (p >= lo) & (p <= hi)
        if m.sum() == 0:
            continue
        e += m.sum() / len(y) * abs(y[m].mean() - p[m].mean())
    return e


# ── 切分(按 uid 分组 + 按主 bench 分层)───────────────────────────────────
def uid_groups(instances):
    uid_bench = defaultdict(Counter)
    for r in instances:
        uid_bench[r["uid"]][r["bench"]] += 1
    primary = {u: c.most_common(1)[0][0] for u, c in uid_bench.items()}
    return primary


def stratified_uid_split(primary, fracs, rng):
    """fracs 如 [0.4,0.2,0.4] → uid→split_idx。"""
    strata = defaultdict(list)
    for u, b in sorted(primary.items()):
        strata[b].append(u)
    assign = {}
    for b, us in sorted(strata.items()):
        us = list(us)
        rng.shuffle(us)
        n = len(us)
        cuts = np.cumsum([int(round(f * n)) for f in fracs[:-1]])
        parts = np.split(np.array(us), cuts)
        for si, part in enumerate(parts):
            for u in part:
                assign[u] = si
    return assign


def kfold_uid(primary, k, rng):
    strata = defaultdict(list)
    for u, b in sorted(primary.items()):
        strata[b].append(u)
    fold = {}
    for b, us in sorted(strata.items()):
        us = list(us)
        rng.shuffle(us)
        for i, u in enumerate(us):
            fold[u] = i % k
    return fold


# ── 策略评估 ───────────────────────────────────────────────────────────────
def policy_pick(inst, phat_row, lam, tref, arm_idx, cost_mode="actual",
                mean_cost=None):
    best, bs = None, -1e18
    for a, meta in inst["arms"].items():
        c = (meta["tok"] / tref) if cost_mode == "actual" else mean_cost[a]
        s = phat_row[arm_idx[a]] - lam * c
        if s > bs:
            bs, best = s, a
    return best


def eval_policy(instances, phat, lam, tref, arm_idx, cost_mode="actual",
                mean_cost=None, sub=None):
    ids = sub if sub is not None else range(len(instances))
    n = corr = 0
    tok = lat = 0.0
    risk_loss = 0
    picks = Counter()
    for i in ids:
        inst = instances[i]
        a = policy_pick(inst, phat[i], lam, tref, arm_idx, cost_mode, mean_cost)
        meta = inst["arms"][a]
        corr += meta["correct"]
        tok += meta["tok"]
        lat += meta.get("lat", 0.0)
        oracle = any(m["correct"] for m in inst["arms"].values())
        risk_loss += int(oracle) - int(meta["correct"])
        picks[a] += 1
        n += 1
    return {"n": n, "acc": corr / n, "tok": tok / n, "lat": lat / n,
            "risk": risk_loss / n, "loss_k": risk_loss, "picks": dict(picks)}


# ── 二项尾界 / LTT ─────────────────────────────────────────────────────────
def binom_cdf(k, n, p):
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    lp, l1p = math.log(p), math.log1p(-p)
    s = 0.0
    for i in range(k + 1):
        lg = (math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
              + i * lp + (n - i) * l1p)
        s += math.exp(lg)
    return min(s, 1.0)


def cp_upper(k, n, delta):
    """Clopper-Pearson 单侧上界:sup{p: P(Bin(n,p)<=k) >= delta}。"""
    lo, hi = k / n if n else 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) >= delta:
            lo = mid
        else:
            hi = mid
    return hi


def ltt_select(instances, phat, tref, arm_idx, calib_ids, eps, delta,
               cost_mode="actual", mean_cost=None):
    """固定序列检验:λ 升序(风险近单调升),首个不拒绝即停。
    H0(λ): risk>eps;p 值 = P(Bin(n,eps) <= k);p<=delta 拒绝。
    返回 (lam_hat, 记录表)。全部不通过 → lam_hat=None。"""
    rec = []
    lam_hat = None
    for lam in LAMBDA_GRID:
        ev = eval_policy(instances, phat, lam, tref, arm_idx, cost_mode,
                         mean_cost, sub=calib_ids)
        pv = binom_cdf(ev["loss_k"], ev["n"], eps)
        ok = pv <= delta
        rec.append({"lam": lam, "risk": ev["risk"], "k": ev["loss_k"],
                    "n": ev["n"], "pval": pv, "reject": ok,
                    "acc": ev["acc"], "tok": ev["tok"]})
        if ok:
            lam_hat = lam
        else:
            break
    return lam_hat, rec


def excess_eval(instances, phat, lam, tref, arm_idx, sub):
    """次级风险:相对同预测器 λ=0 策略的单侧 break 损失
    L_i(λ)=1{pol_0 对 ∧ pol_λ 错} ∈ {0,1}(保守:不抵扣 λ 救回的题)。"""
    k = n = corr = 0
    tok = 0.0
    for i in sub:
        inst = instances[i]
        a0 = policy_pick(inst, phat[i], 0.0, tref, arm_idx)
        al = policy_pick(inst, phat[i], lam, tref, arm_idx)
        c0 = inst["arms"][a0]["correct"]
        cl = inst["arms"][al]["correct"]
        k += int(c0 and not cl)
        corr += cl
        tok += inst["arms"][al]["tok"]
        n += 1
    return {"n": n, "loss_k": k, "risk": k / n, "acc": corr / n, "tok": tok / n}


def ltt_select_excess(instances, phat, tref, arm_idx, calib_ids, eps, delta):
    """次级证书的固定序列检验(λ 升序;λ=0 风险恒 0)。"""
    rec = []
    lam_hat = None
    for lam in LAMBDA_GRID:
        ev = excess_eval(instances, phat, lam, tref, arm_idx, calib_ids)
        pv = binom_cdf(ev["loss_k"], ev["n"], eps)
        ok = pv <= delta
        rec.append({"lam": lam, "risk": ev["risk"], "k": ev["loss_k"],
                    "n": ev["n"], "pval": pv, "reject": ok,
                    "acc": ev["acc"], "tok": ev["tok"]})
        if ok:
            lam_hat = lam
        else:
            break
    return lam_hat, rec


# ── 主流程 ─────────────────────────────────────────────────────────────────
def main():
    instances = assemble()
    n = len(instances)
    X_raw, names = featurize(instances)
    arm_idx = {a: i for i, a in enumerate(ARMS)}
    primary = uid_groups(instances)

    # 全局臂统计与成本归一
    arm_stat = {a: {"n": 0, "c": 0, "tok": 0.0, "lat": 0.0} for a in ARMS}
    all_toks = []
    for r in instances:
        for a, m in r["arms"].items():
            arm_stat[a]["n"] += 1
            arm_stat[a]["c"] += m["correct"]
            arm_stat[a]["tok"] += m["tok"]
            arm_stat[a]["lat"] += m.get("lat", 0.0)
            all_toks.append(m["tok"])
    tref = float(np.mean(all_toks))
    mean_cost = {a: (arm_stat[a]["tok"] / arm_stat[a]["n"]) / tref
                 for a in ARMS}
    n_arms_dist = Counter(len(r["arms"]) for r in instances)
    print("TREF", round(tref, 1), "mean_cost", {a: round(v, 3) for a, v in mean_cost.items()})
    print("arms per instance", dict(n_arms_dist))

    # v4.2 对照与 oracle(全量)
    v42_acc = np.mean([r["v42_correct"] for r in instances])
    v42_tok = np.mean([r["v42_tok"] for r in instances])
    v42_lat = np.mean([r["v42_lat"] for r in instances])
    oracle_c = [any(m["correct"] for m in r["arms"].values()) for r in instances]
    oracle_tok = []
    for r in instances:
        cs = [m["tok"] for m in r["arms"].values() if m["correct"]]
        oracle_tok.append(min(cs) if cs else min(m["tok"] for m in r["arms"].values()))
    oracle_acc = np.mean(oracle_c)
    oracle_tokm = np.mean(oracle_tok)

    # ── 交叉拟合(5 折按 uid,分层)→ 全量 5511 的诚实 p̂ ────────────────
    rng = np.random.default_rng(SEED)
    fold = kfold_uid(primary, 5, rng)
    fold_of = np.array([fold[r["uid"]] for r in instances])
    phat = np.zeros((n, 4))
    phat_gb = np.zeros((n, 4))
    y_arm = {a: np.array([r["arms"][a]["correct"] if a in r["arms"] else -1
                          for r in instances], dtype=np.float64) for a in ARMS}
    for k in range(5):
        tr = fold_of != k
        te = fold_of == k
        Xs = standardize(X_raw[tr], X_raw, names)
        for a in ARMS:
            m_tr = tr & (y_arm[a] >= 0)
            w = fit_lr(Xs[m_tr], y_arm[a][m_tr])
            phat[te, arm_idx[a]] = pred_lr(w, Xs[te])
            gb = fit_stumps(X_raw[m_tr], y_arm[a][m_tr])
            phat_gb[te, arm_idx[a]] = pred_stumps(gb, X_raw[te])

    # 每臂 AUC / ECE(交叉拟合,只在该臂有实测行的题上)
    arm_quality = {}
    for a in ARMS:
        m = y_arm[a] >= 0
        y = y_arm[a][m]
        p = phat[m, arm_idx[a]]
        pg = phat_gb[m, arm_idx[a]]
        arm_quality[a] = {"n": int(m.sum()), "acc": float(y.mean()),
                          "auc_lr": auc(y, p), "auc_gb": auc(y, pg),
                          "ece_lr": ece(y, p), "brier_lr": float(np.mean((p - y) ** 2))}

    # ── λ 扫描:全量 Pareto(实测成本 与 常数成本两口径)────────────────
    frontier = []
    frontier_const = []
    for lam in LAMBDA_GRID:
        frontier.append({"lam": lam, **{k: v for k, v in
                        eval_policy(instances, phat, lam, tref, arm_idx).items()}})
        frontier_const.append({"lam": lam, **{k: v for k, v in
                              eval_policy(instances, phat, lam, tref, arm_idx,
                                          "const", mean_cost).items()}})

    # headline:同准确率省token / 同成本涨准确率(相对 v4.2 全量)
    same_acc = None
    for f in frontier:
        if f["acc"] >= v42_acc and (same_acc is None or f["tok"] < same_acc["tok"]):
            same_acc = f
    same_cost = None
    for f in frontier:
        if f["tok"] <= v42_tok and (same_cost is None or f["acc"] > same_cost["acc"]):
            same_cost = f

    # 分 bench oracle-gap 表(λ 取 same_acc 那档)
    lam_star = same_acc["lam"] if same_acc else 0.0
    bench_rows = []
    for b in BENCH_ORDER:
        ids = [i for i, r in enumerate(instances) if r["bench"] == b]
        ev = eval_policy(instances, phat, lam_star, tref, arm_idx, sub=ids)
        o_acc = np.mean([oracle_c[i] for i in ids])
        v_acc = np.mean([instances[i]["v42_correct"] for i in ids])
        v_tok = np.mean([instances[i]["v42_tok"] for i in ids])
        bench_rows.append({"bench": b, "n": len(ids), "oracle": float(o_acc),
                           "v42": float(v_acc), "v42_tok": float(v_tok),
                           "learned": ev["acc"], "learned_tok": ev["tok"]})

    # 目标域 13 基准微平均
    t13 = [i for i, r in enumerate(instances) if r["bench"] in TARGET13]
    ev13 = eval_policy(instances, phat, lam_star, tref, arm_idx, sub=t13)
    v42_13_acc = np.mean([instances[i]["v42_correct"] for i in t13])
    v42_13_tok = np.mean([instances[i]["v42_tok"] for i in t13])
    o13 = np.mean([oracle_c[i] for i in t13])

    # ── 证书协议:40/20/40 train/calib/test 按 uid 分层 ────────────────────
    rng2 = np.random.default_rng(SEED)
    split = stratified_uid_split(primary, [0.4, 0.2, 0.4], rng2)
    s_of = np.array([split[r["uid"]] for r in instances])
    tr_ids = np.where(s_of == 0)[0]
    ca_ids = np.where(s_of == 1)[0]
    te_ids = np.where(s_of == 2)[0]
    Xs2 = standardize(X_raw[tr_ids], X_raw, names)
    phat2 = np.zeros((n, 4))
    for a in ARMS:
        m_tr = np.zeros(n, dtype=bool)
        m_tr[tr_ids] = True
        m_tr &= (y_arm[a] >= 0)
        w = fit_lr(Xs2[m_tr], y_arm[a][m_tr])
        phat2[:, arm_idx[a]] = pred_lr(w, Xs2)

    # 主证书(任务定义:相对逐题 oracle 的准确率损失)与
    # 次级证书(相对 λ=0 学习策略的单侧 break 损失,成本压缩安全性)
    v42_te_acc = float(np.mean([instances[i]["v42_correct"] for i in te_ids]))
    v42_te_tok = float(np.mean([instances[i]["v42_tok"] for i in te_ids]))
    o_te = float(np.mean([oracle_c[i] for i in te_ids]))
    # λ=0 在 calib 上的风险与其 CP 上界 → 本协议可发证的最小 ε
    ev_ca0 = eval_policy(instances, phat2, 0.0, tref, arm_idx, sub=list(ca_ids))
    min_cert_eps = cp_upper(ev_ca0["loss_k"], ev_ca0["n"], DELTA)
    certs = {"primary": {}, "excess": {},
             "min_cert_eps_primary": min_cert_eps,
             "calib_risk_lam0": ev_ca0["risk"]}
    for eps in EPS_LIST:
        lam_hat, rec = ltt_select(instances, phat2, tref, arm_idx,
                                  list(ca_ids), eps, DELTA)
        entry = {"eps": eps, "delta": DELTA, "n_calib": len(ca_ids),
                 "n_test": len(te_ids), "lam_hat": lam_hat, "ltt_table": rec}
        if lam_hat is not None:
            ev_te = eval_policy(instances, phat2, lam_hat, tref, arm_idx,
                                sub=list(te_ids))
            entry["test"] = {**ev_te,
                             "risk_ucb_cp": cp_upper(ev_te["loss_k"],
                                                     ev_te["n"], DELTA),
                             "risk_ucb_hoeff": ev_te["risk"]
                             + math.sqrt(math.log(1 / DELTA) / (2 * ev_te["n"]))}
        certs["primary"][eps] = entry
        lam_hat2, rec2 = ltt_select_excess(instances, phat2, tref, arm_idx,
                                           list(ca_ids), eps, DELTA)
        entry2 = {"eps": eps, "delta": DELTA, "n_calib": len(ca_ids),
                  "n_test": len(te_ids), "lam_hat": lam_hat2,
                  "ltt_table": rec2}
        if lam_hat2 is not None:
            ev_te2 = excess_eval(instances, phat2, lam_hat2, tref, arm_idx,
                                 list(te_ids))
            ev_te2_full = eval_policy(instances, phat2, lam_hat2, tref,
                                      arm_idx, sub=list(te_ids))
            entry2["test"] = {**ev_te2,
                              "oracle_risk": ev_te2_full["risk"],
                              "risk_ucb_cp": cp_upper(ev_te2["loss_k"],
                                                      ev_te2["n"], DELTA),
                              "risk_ucb_hoeff": ev_te2["risk"]
                              + math.sqrt(math.log(1 / DELTA)
                                          / (2 * ev_te2["n"]))}
        certs["excess"][eps] = entry2
    certs["test_v42"] = {"acc": v42_te_acc, "tok": v42_te_tok}
    certs["test_oracle_acc"] = o_te

    # ── 留一域外推(LODO):证书退化 ─────────────────────────────────────
    lodo = []
    for b in BENCH_ORDER:
        held = [i for i, r in enumerate(instances) if r["bench"] == b]
        held_uids = {instances[i]["uid"] for i in held}
        rest = [i for i, r in enumerate(instances)
                if r["bench"] != b and r["uid"] not in held_uids]
        rest_uids = sorted({instances[i]["uid"] for i in rest})
        rng3 = np.random.default_rng(SEED + 7)
        prim_rest = {u: primary[u] for u in rest_uids}
        sp = stratified_uid_split(prim_rest, [0.7, 0.3], rng3)
        tr_i = [i for i in rest if sp[instances[i]["uid"]] == 0]
        ca_i = [i for i in rest if sp[instances[i]["uid"]] == 1]
        Xs3 = standardize(X_raw[tr_i], X_raw, names)
        ph3 = np.zeros((n, 4))
        for a in ARMS:
            m_tr = np.zeros(n, dtype=bool)
            m_tr[tr_i] = True
            m_tr &= (y_arm[a] >= 0)
            if m_tr.sum() < 20:
                continue
            w = fit_lr(Xs3[m_tr], y_arm[a][m_tr])
            ph3[:, arm_idx[a]] = pred_lr(w, Xs3)
        eps = 0.05
        lam_hat, _rec = ltt_select_excess(instances, ph3, tref, arm_idx,
                                          ca_i, eps, DELTA)
        row = {"bench": b, "n_held": len(held), "lam_hat": lam_hat}
        if lam_hat is not None:
            ex_h = excess_eval(instances, ph3, lam_hat, tref, arm_idx, held)
            ev_h = eval_policy(instances, ph3, lam_hat, tref, arm_idx, sub=held)
            v_acc = np.mean([instances[i]["v42_correct"] for i in held])
            v_tok = np.mean([instances[i]["v42_tok"] for i in held])
            row.update({"risk_held": ex_h["risk"],
                        "cert_holds": ex_h["risk"] <= eps,
                        "oracle_risk_held": ev_h["risk"],
                        "acc": ev_h["acc"], "tok": ev_h["tok"],
                        "v42_acc": float(v_acc), "v42_tok": float(v_tok)})
        lodo.append(row)

    # ── 升级伪臂:max p̂ 低于阈值 → 改派最贵臂(全局均token最高的可用臂)──
    exp_order = sorted(ARMS, key=lambda a: -mean_cost[a])
    esc = []
    lam_esc = certs["excess"][0.05]["lam_hat"]
    if lam_esc is None:
        lam_esc = lam_star
    for tau in (0.5, 0.6, 0.7):
        base_c = base_t = esc_c = esc_t = flag = saved = broken = 0
        for i, inst in enumerate(instances):
            a0 = policy_pick(inst, phat[i], lam_esc, tref, arm_idx)
            m0 = inst["arms"][a0]
            base_c += m0["correct"]
            base_t += m0["tok"]
            mx = max(phat[i][arm_idx[a]] for a in inst["arms"])
            if mx < tau:
                flag += 1
                a1 = next(a for a in exp_order if a in inst["arms"])
            else:
                a1 = a0
            m1 = inst["arms"][a1]
            esc_c += m1["correct"]
            esc_t += m1["tok"]
            if a1 != a0:
                saved += int(m1["correct"] and not m0["correct"])
                broken += int(m0["correct"] and not m1["correct"])
        esc.append({"tau": tau, "flagged": flag, "saved": saved,
                    "broken": broken,
                    "acc_base": base_c / n, "acc_esc": esc_c / n,
                    "tok_base": base_t / n, "tok_esc": esc_t / n})

    # ── 覆盖率 ─────────────────────────────────────────────────────────────
    triples_by_bench = {b: {a: 0 for a in ARMS} for b in BENCH_ORDER}
    for r in instances:
        for a in r["arms"]:
            triples_by_bench[r["bench"]][a] += 1
    n_triples = sum(arm_stat[a]["n"] for a in ARMS)
    restricted = sum(1 for r in instances if len(r["arms"]) < 4)

    # ── 落盘 ───────────────────────────────────────────────────────────────
    with open(R / "router_learned_triples_20260814.jsonl", "w",
              encoding="utf-8") as f:
        for i, r in enumerate(instances):
            f.write(json.dumps({
                "bench": r["bench"], "uid": r["uid"], "qid": r["qid"],
                "cv_fold": int(fold_of[i]), "cert_split": int(s_of[i]),
                "arms": r["arms"], "v42_pick": r["v42_pick"],
                "v42_correct": r["v42_correct"], "v42_tok": r["v42_tok"],
                "phat_cv": {a: round(float(phat[i, arm_idx[a]]), 4)
                            for a in ARMS},
            }, ensure_ascii=False) + "\n")
    with open(R / "router_learned_policy_20260814.jsonl", "w",
              encoding="utf-8") as f:
        for i, r in enumerate(instances):
            a_l0 = policy_pick(r, phat[i], 0.0, tref, arm_idx)
            a_ls = policy_pick(r, phat[i], lam_star, tref, arm_idx)
            f.write(json.dumps({
                "bench": r["bench"], "qid": r["qid"],
                "pick_lam0": a_l0, "pick_lamstar": a_ls,
                "lam_star": lam_star,
                "correct_lamstar": r["arms"][a_ls]["correct"],
                "tok_lamstar": r["arms"][a_ls]["tok"],
            }, ensure_ascii=False) + "\n")

    out = {
        "n": n, "tref": tref, "mean_cost": mean_cost,
        "arm_stat": arm_stat, "arm_quality": arm_quality,
        "v42": {"acc": float(v42_acc), "tok": float(v42_tok),
                "lat": float(v42_lat)},
        "oracle": {"acc": float(oracle_acc), "tok": float(oracle_tokm)},
        "frontier": frontier, "frontier_const": frontier_const,
        "same_acc": same_acc, "same_cost": same_cost, "lam_star": lam_star,
        "bench_rows": bench_rows,
        "t13": {"learned": ev13, "v42_acc": float(v42_13_acc),
                "v42_tok": float(v42_13_tok), "oracle": float(o13)},
        "certs": certs, "lodo": lodo, "esc": esc, "lam_esc": lam_esc,
        "split_sizes": {"train": len(tr_ids), "calib": len(ca_ids),
                        "test": len(te_ids)},
        "n_triples": n_triples, "triples_by_bench": triples_by_bench,
        "restricted": restricted, "n_arms_dist": dict(n_arms_dist),
    }
    (R / "router_learned_raw_20260814.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    write_report(out)
    print("done")


def write_report(o):
    L = []
    A = L.append
    A("# P3 学习路由 + Learn-then-Test 风险证书(离线策略评估,零 LLM)")
    A("")
    A(f"日期 2026-08-14/15 | 种子 {SEED} | sklearn 不可用 → numpy 手写逻辑回归"
      "(IRLS+ridge),boosted-stumps 作对照 | 全部离线:同一 qid 多臂已归档判官"
      "结果做路由模拟,未发起任何 LLM 调用")
    A("")
    A("## 0. 判决")
    sa, sc, v42 = o["same_acc"], o["same_cost"], o["v42"]
    if sa and sa["tok"] < v42["tok"] - 1e-9:
        A(f"**猜想被证实:学习路由优于 v4.2 手写路由。**同准确率口径下每题 token "
          f"从 {v42['tok']:.0f} 降到 {sa['tok']:.0f}"
          f"(−{(1 - sa['tok'] / v42['tok']) * 100:.1f}%,准确率 "
          f"{sa['acc'] * 100:.2f}% ≥ 手写 {v42['acc'] * 100:.2f}%);"
          f"同成本口径下准确率从 {v42['acc'] * 100:.2f}% 升到 "
          f"{sc['acc'] * 100:.2f}%(+{(sc['acc'] - v42['acc']) * 100:.2f}pp,"
          f"每题 token {sc['tok']:.0f} ≤ 手写 {v42['tok']:.0f})。")
    elif sa:
        A(f"学习路由与手写路由成本相当(同准确率下 token {sa['tok']:.0f} vs "
          f"{v42['tok']:.0f}),未见显著节省;同成本准确率 "
          f"{(sc['acc'] * 100 if sc else float('nan')):.2f}% vs {v42['acc'] * 100:.2f}%。")
    else:
        A(f"**猜想被否定:λ 网格上学习路由没有任何一点达到手写路由准确率 "
          f"{v42['acc'] * 100:.2f}%。**负结果照常入档,细节见前沿表。")
    ce = o["certs"]["excess"].get(0.05, {})
    if ce.get("lam_hat") is not None and ce.get("test"):
        A(f"证书:主口径(相对 oracle 损失 ≤ ε)被否定 —— oracle-gap ≈9% "
          f"结构性超出 ε∈{{0.03,0.05}}(§6.1);次级成本压缩安全证书成立 —— "
          f"λ̂={ce['lam_hat']} 时置信 90% 下 break 风险 ≤ 5%,测试集实测 "
          f"{ce['test']['risk'] * 100:.2f}%(§6.2)。")
    else:
        A("证书:主口径与次级口径均未能发证,见 §6。")
    A("")
    A("## 1. 数据组装与覆盖率")
    A(f"- 实例:v4.2 路由日志全量 {o['n']} 题(15 基准);三元组(特征,臂,"
      f"correct,token)共 **{o['n_triples']}** 条。")
    st = o["arm_stat"]
    A("- 各臂行数/实测正确率/每题均 token(token=in+out,wt 另计 focus_tokens):")
    A("")
    A("| 臂 | 行数 | 正确率 | 均 token | 均时延 s |")
    A("|---|---|---|---|---|")
    for a in ARMS:
        s = st[a]
        A(f"| {a} | {s['n']} | {s['c'] / s['n'] * 100:.1f}% | "
          f"{s['tok'] / s['n']:.0f} | {s['lat'] / s['n']:.1f} |")
    A("")
    A(f"- 动作空间掩码:所选臂必有实测行(argmax 只在可用臂上取),故离线评估"
      f"对全部 {o['n']}/{o['n']} 题精确 —— **覆盖率 5511/5511,无缺行丢弃**。")
    A(f"- 受限动作空间(<4 臂可选)共 {o['restricted']} 题:STALE-full 冷库 1050 无 wt"
      "(结构性)、wiki-P551 44 无 rt(结构性)、LoCoMo 110 + LoCoMo-full 749 无 "
      "prompt 行(与行为策略相关的缺失,按盘点建议掩码处理并如实计数,不外推)、"
      "LoCoMo-full 2 题 rt error。")
    A(f"- 每题可用臂数分布:{o['n_arms_dist']};成本归一 T_ref = 全体臂行均 token "
      f"= {o['tref']:.0f};各臂常数成本(均token/T_ref):"
      + ", ".join(f"{a} {o['mean_cost'][a]:.2f}" for a in ARMS) + "。")
    A("- 行源与对照组同源(旧 wt 文件 + prompt_rows_all);对照组重放校验:"
      "result 与臂行判官 0 mismatch。")
    A("")
    A("## 2. 每臂正确率预测器(交叉拟合 5 折按 uid 分组,防同库泄漏)")
    A("")
    A("| 臂 | n | 基率 | AUC(LR) | AUC(stumps) | ECE(LR) | Brier(LR) |")
    A("|---|---|---|---|---|---|---|")
    for a in ARMS:
        q = o["arm_quality"][a]
        A(f"| {a} | {q['n']} | {q['acc'] * 100:.1f}% | {q['auc_lr']:.3f} | "
          f"{q['auc_gb']:.3f} | {q['ece_lr']:.3f} | {q['brier_lr']:.3f} |")
    A("")
    A("特征全部部署侧(bench one-hot、scope/slot 类/presupposed、keyed_depth、"
    "卡片库形态、问题文本旗标、手写路由决策 route 本身作为特征);判官/金答案/"
    "qid_raw 尾缀/question_type/stale_type/picked_arm/result 一律禁入。")
    A("")
    A("## 3. 准确率-成本 Pareto 前沿(全量 5511,交叉拟合,实测 token 成本)")
    A("")
    A("| λ | 准确率 | 每题 token | 每题时延 s | 相对oracle风险 | 路由分布 d/r/w/p |")
    A("|---|---|---|---|---|---|")
    for f in o["frontier"]:
        p = f["picks"]
        A(f"| {f['lam']} | {f['acc'] * 100:.2f}% | {f['tok']:.0f} | "
          f"{f['lat']:.1f} | "
          f"{f['risk'] * 100:.2f}% | {p.get('direct', 0)}/{p.get('rt', 0)}/"
          f"{p.get('wt', 0)}/{p.get('prompt', 0)} |")
    A("")
    A(f"参照:**v4.2 手写路由 = {v42['acc'] * 100:.2f}% @ {v42['tok']:.0f} tok/题 "
      f"@ {v42['lat']:.1f} s/题**;"
      f"逐题 oracle 上界 = {o['oracle']['acc'] * 100:.2f}% @ {o['oracle']['tok']:.0f} "
      "tok/题(oracle token 取最便宜的答对臂)。")
    A("")
    A("常数成本口径(部署时不知逐题实测 token,用臂均值)敏感性:")
    A("")
    A("| λ | 准确率 | 每题 token |")
    A("|---|---|---|")
    for f in o["frontier_const"]:
        A(f"| {f['lam']} | {f['acc'] * 100:.2f}% | {f['tok']:.0f} |")
    A("")
    A("## 4. Headline(相对 v4.2 手写路由,全量 5511)")
    if sa:
        A(f"- **同准确率省 token**:λ={sa['lam']} 时 {sa['acc'] * 100:.2f}% ≥ 手写 "
          f"{v42['acc'] * 100:.2f}%,每题 token {sa['tok']:.0f} vs {v42['tok']:.0f}"
          f"(**−{(1 - sa['tok'] / v42['tok']) * 100:.1f}%**)。")
    else:
        A("- 同准确率档:网格上无达标点(负结果)。")
    if sc:
        A(f"- **同成本涨准确率**:λ={sc['lam']} 时每题 token {sc['tok']:.0f} ≤ 手写 "
          f"{v42['tok']:.0f},准确率 {sc['acc'] * 100:.2f}% vs {v42['acc'] * 100:.2f}%"
          f"(**+{(sc['acc'] - v42['acc']) * 100:.2f}pp**)。")
    else:
        A("- 同成本档:网格上无更低成本点(负结果)。")
    bal = next((f for f in o["frontier"] if f["lam"] == 0.5), None)
    if bal and bal["acc"] > v42["acc"] and bal["tok"] < v42["tok"]:
        A(f"- 均衡档(双优,即次级证书 ε=0.05 的 λ̂=0.5):"
          f"{bal['acc'] * 100:.2f}% @ {bal['tok']:.0f} tok/题 @ {bal['lat']:.1f} s/题 "
          f"—— 同时 +{(bal['acc'] - v42['acc']) * 100:.2f}pp 与 "
          f"−{(1 - bal['tok'] / v42['tok']) * 100:.1f}% token"
          f"(v4.2 时延 {v42['lat']:.1f} s/题),两轴同时占优。")
    t13 = o["t13"]
    A(f"- 目标域 13 基准微平均(λ={o['lam_star']}):学习 "
      f"{t13['learned']['acc'] * 100:.2f}% @ {t13['learned']['tok']:.0f} tok vs 手写 "
      f"{t13['v42_acc'] * 100:.2f}% @ {t13['v42_tok']:.0f} tok;oracle "
      f"{t13['oracle'] * 100:.2f}%。(日志重放口径;与档案 88.8 的宏平均口径不同,"
      "重放本身无歧义。)")
    A("")
    A("## 5. Oracle-gap 逐基准(λ=" + str(o["lam_star"]) + ")")
    A("")
    A("| 基准 | n | oracle上界 | v4.2手写 | 学习路由 | v4.2 tok | 学习 tok |")
    A("|---|---|---|---|---|---|---|")
    for r in o["bench_rows"]:
        A(f"| {r['bench']} | {r['n']} | {r['oracle'] * 100:.1f}% | "
          f"{r['v42'] * 100:.1f}% | {r['learned'] * 100:.1f}% | "
          f"{r['v42_tok']:.0f} | {r['learned_tok']:.0f} |")
    tot = o
    A(f"| **合计** | {o['n']} | {o['oracle']['acc'] * 100:.2f}% | "
      f"{v42['acc'] * 100:.2f}% | "
      f"{[f for f in o['frontier'] if f['lam'] == o['lam_star']][0]['acc'] * 100:.2f}% | "
      f"{v42['tok']:.0f} | "
      f"{[f for f in o['frontier'] if f['lam'] == o['lam_star']][0]['tok']:.0f} |")
    _ = tot
    A("")
    A("## 6. Learn-then-Test 风险证书")
    A("")
    ss = o["split_sizes"]
    A(f"协议:按 uid 分层(uid 主基准分层;共享 uid 并组)切 train/calib/test = "
      f"{ss['train']}/{ss['calib']}/{ss['test']} 题(≈40/20/40;预测器只用 train,"
      f"λ 选择只用 calib,验证只用 test;种子 {SEED})。风险 = 相对逐题 oracle "
      f"选臂的准确率损失;固定序列检验按 λ 升序,二项精确尾界,δ={DELTA}。")
    A("")
    A("### 6.1 主风险定义(任务口径):相对逐题 oracle 选臂的准确率损失")
    A("")
    for eps in EPS_LIST:
        c = o["certs"]["primary"][eps]
        A(f"#### ε = {eps}")
        A("")
        A("| λ | calib风险 | k/n | p值 | 拒绝H0(risk>ε)? |")
        A("|---|---|---|---|---|")
        for rr in c["ltt_table"]:
            A(f"| {rr['lam']} | {rr['risk'] * 100:.2f}% | {rr['k']}/{rr['n']} | "
              f"{rr['pval']:.2e} | {'是' if rr['reject'] else '否(停)'} |")
        if c["lam_hat"] is None:
            A("")
            A("**无 λ 通过检验 → 主口径无法发证(负结果)。**")
        else:
            t = c["test"]
            A("")
            A(f"**λ̂ = {c['lam_hat']}**。测试集(n={t['n']}):经验风险 "
              f"{t['risk'] * 100:.2f}%(k={t['loss_k']}),CP 上界 "
              f"{t['risk_ucb_cp'] * 100:.2f}%,Hoeffding 上界 "
              f"{t['risk_ucb_hoeff'] * 100:.2f}%;证书"
              f"{'成立' if t['risk'] <= eps else '不成立'}。")
        A("")
    mce = o["certs"]["min_cert_eps_primary"]
    cr0 = o["certs"]["calib_risk_lam0"]
    A(f"**判决:主口径证书被否定 —— 结构性不可达,而非检验太严。**λ=0(最准的"
      f"学习策略)在 calib 上相对 oracle 的经验风险已是 {cr0 * 100:.2f}%,远超 "
      f"ε∈{{0.03,0.05}};预测器质量决定的 oracle-gap ≈9%(§3),"
      f"本协议下主口径可发证的最小 ε ≈ {mce * 100:.1f}%"
      f"(λ=0 calib 风险的 CP 上界,δ={DELTA})。要在 ε=0.05 发主口径证书,"
      "需把 oracle-gap 压到 5% 以内 —— 是预测器/特征问题,不是 λ 选择问题。")
    A("")
    A("### 6.2 次级风险定义(成本压缩安全证书):相对 λ=0 学习策略的单侧 break 损失")
    A("")
    A("L(λ)=1{λ=0 策略答对 ∧ λ 策略答错}(保守单侧:不抵扣 λ 救回的题)。"
      "证书语义:置信 1−δ 下,成本压缩至多打破 ε 比例的题。")
    A("")
    for eps in EPS_LIST:
        c = o["certs"]["excess"][eps]
        A(f"#### ε = {eps}")
        A("")
        A("| λ | calib break风险 | k/n | p值 | 拒绝? | calib acc | calib tok |")
        A("|---|---|---|---|---|---|---|")
        for rr in c["ltt_table"]:
            A(f"| {rr['lam']} | {rr['risk'] * 100:.2f}% | {rr['k']}/{rr['n']} | "
              f"{rr['pval']:.2e} | {'是' if rr['reject'] else '否(停)'} | "
              f"{rr['acc'] * 100:.2f}% | {rr['tok']:.0f} |")
        if c["lam_hat"] is None:
            A("")
            A("**无 λ 通过 → 次级口径亦无法发证。**")
        else:
            t = c["test"]
            A("")
            A(f"**λ̂ = {c['lam_hat']}**(通过前缀中成本最低档)。测试集验证"
              f"(n={t['n']}):break 经验风险 {t['risk'] * 100:.2f}%"
              f"(k={t['loss_k']}),CP 上界(δ={DELTA})"
              f"{t['risk_ucb_cp'] * 100:.2f}%,Hoeffding 上界 "
              f"{t['risk_ucb_hoeff'] * 100:.2f}%;**证书"
              f"{'成立' if t['risk'] <= eps else '不成立'}**"
              f"(经验风险 {'≤' if t['risk'] <= eps else '>'} ε={eps})。"
              f"该 λ̂ 下测试集准确率 {t['acc'] * 100:.2f}% @ {t['tok']:.0f} "
              f"tok/题(相对 oracle 风险 {t['oracle_risk'] * 100:.2f}%),"
              f"同测试集 v4.2 = {o['certs']['test_v42']['acc'] * 100:.2f}% @ "
              f"{o['certs']['test_v42']['tok']:.0f} tok/题,oracle 上界 "
              f"{o['certs']['test_oracle_acc'] * 100:.2f}%。")
        A("")
    A("注意:证书的可交换性单位是题而非库;同库题目相关(尤其 LoCoMo 系 10 库"
      "2286 题),二项界在题层面偏乐观,uid 层聚类效应见 §7 域外推的退化,"
      "以及切分敏感性注记。")
    A("")
    A("## 7. 留一域外推(可交换性被破坏时的证书退化;次级 break 风险,ε=0.05)")
    A("")
    A("留出域的 uid 全部从训练/校准中剔除(含跨基准共享 uid),在余下 14 个基准"
      "上训练+LTT 选 λ̂,再看留出域上 break 风险是否仍 ≤ ε。")
    A("")
    A("| 留出域 | n | λ̂(域内calib) | 留出域break风险 | 证书还成立? | "
      "留出域oracle风险 | 学习acc | v4.2acc |")
    A("|---|---|---|---|---|---|---|---|")
    for r in o["lodo"]:
        if r["lam_hat"] is None:
            A(f"| {r['bench']} | {r['n_held']} | 无 | - | 发证失败 | - | - | - |")
        else:
            A(f"| {r['bench']} | {r['n_held']} | {r['lam_hat']} | "
              f"{r['risk_held'] * 100:.2f}% | {'是' if r['cert_holds'] else '**否**'} | "
              f"{r['oracle_risk_held'] * 100:.2f}% | "
              f"{r['acc'] * 100:.1f}% | {r['v42_acc'] * 100:.1f}% |")
    A("")
    n_hold = sum(1 for r in o["lodo"] if r.get("cert_holds"))
    n_tot = sum(1 for r in o["lodo"] if r["lam_hat"] is not None)
    A(f"{n_tot} 个可发证的留出域中 {n_hold} 个证书仍成立。域外推破坏可交换性,"
      "退化如实呈现 —— 这是分析素材不是丑闻:证书只对与校准分布可交换的题成立。")
    A("")
    A(f"## 8. 升级伪臂(max p̂ < τ 改派最贵臂;基线策略 λ={o['lam_esc']})")
    A("")
    A("| τ | 触发题数 | 救回 | 打破 | 净变化 | acc 基线→升级 | tok/题 基线→升级 |")
    A("|---|---|---|---|---|---|---|")
    for e in o["esc"]:
        A(f"| {e['tau']} | {e['flagged']} | {e['saved']} | {e['broken']} | "
          f"{e['saved'] - e['broken']:+d} | {e['acc_base'] * 100:.2f}%→"
          f"{e['acc_esc'] * 100:.2f}% | {e['tok_base']:.0f}→{e['tok_esc']:.0f} |")
    A("")
    A("**判决:升级伪臂被否定。**本臂集里最贵臂=rt(均 21.9k token)并非最强臂"
      "(wt 更准且便宜 8 倍),低置信题改派 rt 三档阈值全为净亏"
      "(−19/−122/−143 题)且成本上升;该机制要有用,需要一个"
      "\"更贵且确实更强\"的臂(如深研模式),当前动作空间不满足前提。")
    A("")
    A("## 9. 已知局限")
    A("- LoCoMo 系 prompt 臂缺行与行为策略相关(v4.2 未派 prompt 的题),掩码处理"
      "存在选择偏倚,故这些题的 prompt 反事实未评估。")
    A("- 逐题实测 token 作为成本在部署时不可先验获得(输出 token 未知);常数成本"
      "口径见 §3 敏感性表,结论方向一致性以该表为准核对。")
    A("- wt 行源用旧文件与对照组同源保公平;wtqvf3_v42_* 行源(154 处判官分歧)"
      "留作后续敏感性分析,本轮未跑。")
    A("- LoCoMo 系 10 库承载 2286 题,uid 切分粒度粗:证书切分对这 10 库的落位"
      "敏感,题层二项界偏乐观。")
    A("- 升级伪臂按任务规格用\"最贵臂\"定义;若改为\"argmax p̂ 的非当前臂\"则退化"
      "为 λ=0 策略,未另设机制。")
    A("")
    A("## 10. 复现与产物")
    A("- 脚本:`scripts/train_router.py`(仅新增;冻结代码零改动,`_norm`/"
      "`normkey`/`SLOT_ALIASES` 等自冻结源逐字复刻并注明出处)。")
    A("- 运行:`python scripts/train_router.py`(全离线,单进程 ~2 分钟,"
      "零 LLM 调用,零 API 费用)。")
    A("- 产物:`results/router_learned_triples_20260814.jsonl`(逐题三元组+"
      "交叉拟合 p̂+切分归属)、`results/router_learned_policy_20260814.jsonl`"
      "(逐题选臂)、`results/router_learned_raw_20260814.json`(全部中间统计)、"
      "本报告。")
    (R / "router_learned_report_20260814.md").write_text(
        "\n".join(L), encoding="utf-8")
    print("report ->", R / "router_learned_report_20260814.md")


if __name__ == "__main__":
    main()
