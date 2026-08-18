# -*- coding: utf-8 -*-
"""scripts/armdom.py — 臂支配性审计 + 零 LLM 词法路由 + acc/token 帕累托前沿。

纯代码、零 LLM、零 API 成本。只读归档的逐题多臂产物，不调用任何模型。

同分母纪律（本文件最重要的口径约定）
------------------------------------
所有策略一律在**同一批行**上评估。某策略选中的臂在该行不可用时，按 `FALLBACK_ORDER`
顺序回落到可用臂，回落本身计入该策略的 acc 与 tok，并单独报出回落率。
理由：早期版本按"各臂自己的可用子集"报分，导致覆盖率低的臂（wt 只在 77% 的行上可用）
凭更容易的子集拿到虚高分数，跨策略不可比。

三件产物
--------
1. **支配矩阵**：在同题上，臂 A 是否被臂 B 双向支配（acc 更低 *且* token 更高）。
   分卷复核是判据的一部分——合计支配而分卷不稳的，不得声称"该臂应删"。
2. **零 LLM 路由表**：以 `FEATURES` 里的某个特征函数为桶键，桶内按"准确率在最优 slack
   内取最便宜"选臂；uid 级 K 折留出（同 uid 绝不跨折），多种子，同页报种子极差。
3. **帕累托前沿 + 合成分数** `score = acc_pp - 0.5 * tok/1000`。

为什么桶键只用题面文本
----------------------
`scripts/train_router.py:266,278` 把 `bench={b}` 做成 one-hot 特征，故其 `phat` 编码
基准身份，单一混合流部署时不可知。本文件的所有特征只读 `question` 文本，可部署。

用法
----
    python scripts/armdom.py                        # 全量三件产物
    python scripts/armdom.py --metric score         # 只打一个数（autoresearch Verify）
    python scripts/armdom.py --feature word2        # 指定单个特征
    python scripts/armdom.py --emit results/armdom.json
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TRIPLES = "results/router_learned_triples_20260814.jsonl"
DEFAULT_QTEXT = "results/prompt_rows_all.jsonl"
ARMS = ("direct", "rt", "wt", "prompt")
NO_RT = ("direct", "wt", "prompt")
# 回落顺序：便宜优先。任何策略选不出可用臂时按此顺序取第一个可用的。
FALLBACK_ORDER = ("prompt", "direct", "wt", "rt")

TOKEN_WEIGHT = 0.5  # score = acc_pp - TOKEN_WEIGHT * tok/1000

_WORD = re.compile(r"[a-z0-9']+")


# ── 载入与联结 ────────────────────────────────────────────────────────
def _norm_pr(qid: str) -> str:
    return qid[:-6] if qid.endswith("_query") else qid


def load_rows(triples: str, qtext: Optional[str]) -> Tuple[List[dict], dict]:
    rows = [json.loads(l) for l in open(ROOT / triples, encoding="utf-8") if l.strip()]
    stats = {"triples": len(rows), "exact": 0, "prefix": 0, "ambiguous": 0, "no_text": 0}
    if not qtext:
        return rows, stats

    by: Dict[str, List[dict]] = collections.defaultdict(list)
    for r in (json.loads(l) for l in open(ROOT / qtext, encoding="utf-8") if l.strip()):
        by[_norm_pr(r.get("question_id", ""))].append(r)
    keys = sorted(by)

    out = []
    for t in rows:
        k = t["qid"].replace("|", "_")
        if k in by:
            cand = by[k]
            stats["exact"] += 1
        else:
            cand = [r for kk in keys if kk.startswith(k + "_") for r in by[kk]]
            if not cand:
                stats["no_text"] += 1
                continue
            if len({_norm_pr(r["question_id"]) for r in cand}) > 1:
                stats["ambiguous"] += 1
                continue
            stats["prefix"] += 1
        q = cand[0].get("question", "")
        if not q:
            stats["no_text"] += 1
            continue
        out.append({**t, "q": q})
    stats["joined"] = len(out)
    return out, stats


def has(t: dict, a: str) -> bool:
    return a in t["arms"] and t["arms"][a].get("correct") is not None


def ok(t: dict, a: str) -> bool:
    return bool(t["arms"][a]["correct"])


def tok(t: dict, a: str) -> float:
    return float(t["arms"][a]["tok"])


def resolve(t: dict, a: Optional[str]) -> Optional[str]:
    """把"想选的臂"落到"该行真能跑的臂"。回落顺序固定，便宜优先。"""
    if a is not None and has(t, a):
        return a
    for f in FALLBACK_ORDER:
        if has(t, f):
            return f
    return None


def score_of(acc: float, tk: float) -> float:
    return acc * 100 - TOKEN_WEIGHT * tk / 1000.0


# ── 特征注册表：迭代时在这里加新特征，不改其余代码 ─────────────────────
def _words(t: dict) -> List[str]:
    return _WORD.findall(t["q"].lower())


DEFAULT_CHAINS = [
    "word2", "word3>word2>word1",
    "wh", "agg", "len",
    "word3>word2>agg", "word3>word2>wh", "word3>word2>word1>agg",
    "w2agg>word2>word1", "skel>word2>word1",
]

_WH = ("what", "when", "where", "who", "whom", "whose", "which", "how", "why")
# 聚合/时序意图词：这些词标记的是"要对状态链做什么"，而非"问哪个实体"，
# 因此比表层首词更接近路由真正需要的信号（哪条臂能做这种计算）。
_AGG = {
    "count": ("how many", "how many times", "number of", "count"),
    "dur": ("how long", "duration", "longest", "shortest"),
    "order": ("first", "last", "before", "after", "then", "previously", "originally"),
    "current": ("currently", "current", "now", "these days", "still", "at the moment"),
    "change": ("change", "changed", "switch", "switched", "move", "moved", "used to"),
}
_ENT = re.compile(r"(?:[0-9]+|[A-Z][a-z]+)")


def _agg_key(t: dict) -> str:
    q = t["q"].lower()
    hit = [k for k, ws in _AGG.items() if any(w in q for w in ws)]
    return "+".join(hit) if hit else "none"


def _wh_key(t: dict) -> str:
    for w in _words(t)[:4]:
        if w in _WH:
            return w
    return "other"


def _skel(t: dict) -> str:
    """题面骨架：掩掉数字与专名，只留模板形状。同一模板的不同实体应共享路由决策。"""
    return " ".join(_ENT.sub("<e>", t["q"]).lower().split()[:6]) or "<empty>"


FEATURES: Dict[str, Callable[[dict], str]] = {
    "word1": lambda t: " ".join(_words(t)[:1]) or "<empty>",
    "word2": lambda t: " ".join(_words(t)[:2]) or "<empty>",
    "word3": lambda t: " ".join(_words(t)[:3]) or "<empty>",
    "word4": lambda t: " ".join(_words(t)[:4]) or "<empty>",
    "wh": _wh_key,
    "agg": _agg_key,
    "len": lambda t: f"len{min(len(_words(t)) // 4, 6)}",
    "skel": _skel,
    "w2agg": lambda t: " ".join(_words(t)[:2]) + "|" + _agg_key(t),
    "const": lambda t: "<all>",
}


# ── 1. 支配矩阵 ──────────────────────────────────────────────────────
def dominance(rows: List[dict], arms: Sequence[str] = ARMS,
              min_n: int = 30, min_bench_n: int = 20) -> List[dict]:
    out = []
    for a in arms:
        for b in arms:
            if a == b:
                continue
            sub = [t for t in rows if has(t, a) and has(t, b)]
            if len(sub) < min_n:
                continue
            a_acc = sum(ok(t, a) for t in sub) / len(sub)
            b_acc = sum(ok(t, b) for t in sub) / len(sub)
            a_tok = sum(tok(t, a) for t in sub) / len(sub)
            b_tok = sum(tok(t, b) for t in sub) / len(sub)
            per_bench, n_ok, n_tot = [], 0, 0
            for bench in sorted({t["bench"] for t in sub}):
                s2 = [t for t in sub if t["bench"] == bench]
                if len(s2) < min_bench_n:
                    continue
                n_tot += 1
                aa = sum(ok(t, a) for t in s2) / len(s2)
                bb = sum(ok(t, b) for t in s2) / len(s2)
                at = sum(tok(t, a) for t in s2) / len(s2)
                bt = sum(tok(t, b) for t in s2) / len(s2)
                d2 = (bb > aa) and (bt < at)
                n_ok += d2
                per_bench.append({"bench": bench, "n": len(s2), "dominated": d2,
                                  "d_acc_pp": round((bb - aa) * 100, 2),
                                  "tok_ratio": round(at / bt, 2) if bt else None})
            out.append({
                "dominated_arm": a, "by_arm": b, "n": len(sub),
                "a_acc": round(a_acc * 100, 2), "b_acc": round(b_acc * 100, 2),
                "a_tok": round(a_tok), "b_tok": round(b_tok),
                "dominated_overall": (b_acc > a_acc) and (b_tok < a_tok),
                "benches_dominated": n_ok, "benches_total": n_tot,
                "per_bench": per_bench,
            })
    return out


# ── 2. 零 LLM 路由（同分母评估）──────────────────────────────────────
def _pick(d: Dict[str, List], arms: Sequence[str], min_sup: int,
          slack: float) -> Optional[str]:
    cand = [a for a in arms if d[a][1] >= min_sup]
    if not cand:
        return None
    acc = {a: d[a][0] / d[a][1] for a in cand}
    cost = {a: d[a][2] / d[a][1] for a in cand}
    best = max(acc.values())
    return min([a for a in cand if acc[a] >= best - slack], key=lambda a: cost[a])


def lexical_router(rows: List[dict], arms: Sequence[str], feat: str,
                   seeds: Sequence[int] = tuple(range(5)), folds: int = 2,
                   min_sup: int = 10, slack: float = 0.01) -> dict:
    """uid 级 K 折留出的零 LLM 路由。**所有行都计入分母**，不可用臂按 resolve() 回落。

    `feat` 可以是单个特征名，也可以是用 `>` 连起来的**回落链**（如 `word3>word2>word1`）：
    测试时按链序找第一个支持度够的桶，全链落空才退到全局选臂。动机：细粒度桶命中率低
    （word3 单用时 52.6% 的题落不到桶里），层级回落让细桶只在它真有数据时才生效。
    """
    chain = feat.split(">")
    fns = [FEATURES[c] for c in chain]
    n = len(rows)
    accs, toks, fbs = [], [], []
    uids = sorted({t["uid"] for t in rows})
    for s in seeds:
        rnd = random.Random(s)
        u = uids[:]
        rnd.shuffle(u)
        assign = {x: i % folds for i, x in enumerate(u)}
        c = tt = 0.0
        fb = 0
        for f in range(folds):
            tr = [t for t in rows if assign[t["uid"]] != f]
            te = [t for t in rows if assign[t["uid"]] == f]
            sts: List[Dict[str, Dict[str, List]]] = [
                collections.defaultdict(lambda: {a: [0, 0, 0.0] for a in arms})
                for _ in fns]
            gd = {a: [0, 0, 0.0] for a in arms}
            for t in tr:
                for lv, fn in enumerate(fns):
                    bk = fn(t)
                    for a in arms:
                        if has(t, a):
                            sts[lv][bk][a][0] += ok(t, a)
                            sts[lv][bk][a][1] += 1
                            sts[lv][bk][a][2] += tok(t, a)
                for a in arms:
                    if has(t, a):
                        gd[a][0] += ok(t, a)
                        gd[a][1] += 1
                        gd[a][2] += tok(t, a)
            tables = [{bk: p for bk, d in st.items()
                       if (p := _pick(d, arms, min_sup, slack))} for st in sts]
            glob = _pick(gd, arms, 1, slack)
            for t in te:
                want = None
                for lv, fn in enumerate(fns):
                    want = tables[lv].get(fn(t))
                    if want is not None:
                        break
                if want is None:
                    fb += 1
                    want = glob
                a = resolve(t, want)
                if a is None:
                    continue
                c += ok(t, a)
                tt += tok(t, a)
        accs.append(c / n)
        toks.append(tt / n)
        fbs.append(fb / n)
    mean = lambda x: sum(x) / len(x)
    acc, tk = mean(accs), mean(toks)
    per_seed = [score_of(a, t) for a, t in zip(accs, toks)]
    return {"feature": feat, "arms": list(arms), "n": n, "acc": acc, "tok": tk,
            "score": score_of(acc, tk), "acc_spread": max(accs) - min(accs),
            "score_spread": max(per_seed) - min(per_seed),
            "score_by_seed": [round(x, 4) for x in per_seed],
            "fallback_rate": mean(fbs),
            "acc_by_seed": [round(x * 100, 2) for x in accs]}


def shrinkage_router(rows: List[dict], arms: Sequence[str], levels: Sequence[str],
                     k: float = 20.0, seeds: Sequence[int] = tuple(range(20)),
                     folds: int = 2, slack: float = 0.01) -> dict:
    """层级收缩路由（经验贝叶斯式）。

    动机（实测，见 results/armdom_iterations.tsv 迭代 7）：细分桶 **in-sample** 上界很高
    （skel 2,820 桶达 77.59 分，逐题 oracle 78.80），但留出只有 71.65——瓶颈是每桶样本
    太少（2,820 桶摊 4,633 行），硬回落只能把支持不足的桶整个丢掉，信息随之丢掉。

    收缩不丢桶：从最粗层到最细层逐层把子桶估计向父桶估计拉，权重按支持度
        p_shrunk = (n_b * p_b + k * p_parent) / (n_b + k)
    支持度大的细桶几乎保留自身估计，支持度小的细桶退化成父桶——是 `min_sup` 硬阈值的
    连续版本。k 越大越保守。准确率与成本各自独立收缩，选臂规则不变（准确率在 slack 内
    取最便宜）。
    """
    fns = [FEATURES[l] for l in levels]
    n = len(rows)
    accs, toks = [], []
    uids = sorted({t["uid"] for t in rows})
    for s in seeds:
        rnd = random.Random(s)
        u = uids[:]
        rnd.shuffle(u)
        assign = {x: i % folds for i, x in enumerate(u)}
        c = tt = 0.0
        for f in range(folds):
            tr = [t for t in rows if assign[t["uid"]] != f]
            te = [t for t in rows if assign[t["uid"]] == f]
            # 每层每桶每臂的 (命中数, 计数, token 和)
            lv_stat: List[Dict[str, Dict[str, List]]] = []
            for fn in fns:
                st: Dict[str, Dict[str, List]] = collections.defaultdict(
                    lambda: {a: [0, 0, 0.0] for a in arms})
                for t in tr:
                    bk = fn(t)
                    for a in arms:
                        if has(t, a):
                            st[bk][a][0] += ok(t, a)
                            st[bk][a][1] += 1
                            st[bk][a][2] += tok(t, a)
                lv_stat.append(st)
            # 全局先验
            root = {a: [0, 0, 0.0] for a in arms}
            for t in tr:
                for a in arms:
                    if has(t, a):
                        root[a][0] += ok(t, a)
                        root[a][1] += 1
                        root[a][2] += tok(t, a)
            prior = {a: ((root[a][0] / root[a][1]) if root[a][1] else 0.0,
                         (root[a][2] / root[a][1]) if root[a][1] else 0.0)
                     for a in arms}

            def shrunk(t: dict) -> Dict[str, Tuple[float, float]]:
                cur = dict(prior)
                for lv, fn in enumerate(fns):
                    d = lv_stat[lv].get(fn(t))
                    if not d:
                        continue
                    nxt = {}
                    for a in arms:
                        hit, cnt, tks = d[a]
                        pa, ca = cur[a]
                        if cnt <= 0:
                            nxt[a] = (pa, ca)
                        else:
                            w = cnt / (cnt + k)
                            nxt[a] = (w * (hit / cnt) + (1 - w) * pa,
                                      w * (tks / cnt) + (1 - w) * ca)
                    cur = nxt
                return cur

            for t in te:
                est = shrunk(t)
                best = max(v[0] for v in est.values())
                want = min([a for a in arms if est[a][0] >= best - slack],
                           key=lambda a: est[a][1])
                a = resolve(t, want)
                if a is None:
                    continue
                c += ok(t, a)
                tt += tok(t, a)
        accs.append(c / n)
        toks.append(tt / n)
    mean = lambda x: sum(x) / len(x)
    acc, tk = mean(accs), mean(toks)
    per_seed = [score_of(a, t) for a, t in zip(accs, toks)]
    return {"feature": f"shrink[{'>'.join(levels)}]k={k}", "arms": list(arms), "n": n,
            "acc": acc, "tok": tk, "score": score_of(acc, tk),
            "acc_spread": max(accs) - min(accs),
            "score_spread": max(per_seed) - min(per_seed),
            "score_by_seed": [round(x, 4) for x in per_seed],
            "fallback_rate": 0.0, "acc_by_seed": [round(x * 100, 2) for x in accs]}


def combined_router(rows: List[dict], arms: Sequence[str], chain: str = "word3>word2>wh",
                    k_store: float = 10.0, slack: float = 0.02, min_sup: int = 10,
                    seeds: Sequence[int] = tuple(range(20)), folds: int = 2) -> dict:
    """题面回落链 + **按库(uid)在线自适应**。当前最佳可部署策略。

    为什么加按库自适应（实测，迭代 9/10-12）：记忆系统服务的是**持久的库**，同一个库会
    被反复提问；而已有的轻量路由工作（arXiv 2604.03455 / 2606.02581 / 2604.09019）全部
    是无状态的逐查询路由。按库累积"哪条臂在这个库上有效"，在题面路由之上再拿 +0.39 分
    （20 种子配对 t=6.74，19/20 一致）。**纯库信号单独用是负的**——它是补充，不是替代。

    两条部署诚实性约束，都已写进实现：
      1. **前瞻性（prequential）**：每题只用该 uid 此前已答题的结果，不使用任何未来信息。
      2. **bandit 约束**：只观测**被选中那条臂**的结果——部署时看不到没跑的臂会怎样。
    """
    fns = [FEATURES[c] for c in chain.split(">")]
    n = len(rows)
    accs, toks = [], []
    uids = sorted({t["uid"] for t in rows})
    for s in seeds:
        rnd = random.Random(s)
        u = uids[:]
        rnd.shuffle(u)
        assign = {x: i % folds for i, x in enumerate(u)}
        c = tt = 0.0
        for f in range(folds):
            tr = [t for t in rows if assign[t["uid"]] != f]
            te = [t for t in rows if assign[t["uid"]] == f]
            glob = {a: [0, 0, 0.0] for a in arms}
            sts = [collections.defaultdict(lambda: {a: [0, 0, 0.0] for a in arms})
                   for _ in fns]
            for t in tr:
                for lv, fn in enumerate(fns):
                    bk = fn(t)
                    for a in arms:
                        if has(t, a):
                            sts[lv][bk][a][0] += ok(t, a)
                            sts[lv][bk][a][1] += 1
                            sts[lv][bk][a][2] += tok(t, a)
                for a in arms:
                    if has(t, a):
                        glob[a][0] += ok(t, a)
                        glob[a][1] += 1
                        glob[a][2] += tok(t, a)
            prior = {a: ((glob[a][0] / glob[a][1]) if glob[a][1] else 0.0,
                         (glob[a][2] / glob[a][1]) if glob[a][1] else 0.0) for a in arms}
            by_uid: Dict[str, List[dict]] = collections.defaultdict(list)
            for t in te:
                by_uid[t["uid"]].append(t)
            for _uid, qs in by_uid.items():
                run = {a: [0, 0, 0.0] for a in arms}   # 该库的在线累积（只含已选中的臂）
                for t in qs:
                    base = dict(prior)
                    for lv, fn in enumerate(fns):
                        d = sts[lv].get(fn(t))
                        if d:
                            cand = {a: (d[a][0] / d[a][1], d[a][2] / d[a][1])
                                    for a in arms if d[a][1] >= min_sup}
                            if cand:
                                base = {**base, **cand}
                                break
                    est = {}
                    for a in arms:
                        hit, cnt, tks = run[a]
                        pa, ca = base[a]
                        w = cnt / (cnt + k_store) if cnt else 0.0
                        est[a] = ((w * (hit / cnt) + (1 - w) * pa) if cnt else pa,
                                  (w * (tks / cnt) + (1 - w) * ca) if cnt else ca)
                    best = max(v[0] for v in est.values())
                    want = min([a for a in arms if est[a][0] >= best - slack],
                               key=lambda a: est[a][1])
                    a = resolve(t, want)
                    if a is None:
                        continue
                    c += ok(t, a)
                    tt += tok(t, a)
                    run[a][0] += ok(t, a)      # bandit：只更新被选中的臂
                    run[a][1] += 1
                    run[a][2] += tok(t, a)
        accs.append(c / n)
        toks.append(tt / n)
    mean = lambda x: sum(x) / len(x)
    acc, tk = mean(accs), mean(toks)
    per_seed = [score_of(a, t) for a, t in zip(accs, toks)]
    return {"feature": f"{chain}+store(k={k_store})", "arms": list(arms), "n": n,
            "acc": acc, "tok": tk, "score": score_of(acc, tk),
            "acc_spread": max(accs) - min(accs),
            "score_spread": max(per_seed) - min(per_seed),
            "score_by_seed": [round(x, 4) for x in per_seed],
            "fallback_rate": 0.0, "acc_by_seed": [round(x * 100, 2) for x in accs]}


def constant_strategy(rows: List[dict], arm: str) -> dict:
    """常数臂，**同分母**：该臂不可用的行按 resolve() 回落，回落计入分数。"""
    n = len(rows)
    c = tt = 0.0
    fb = 0
    for t in rows:
        a = resolve(t, arm)
        if a is None:
            continue
        fb += (a != arm)
        c += ok(t, a)
        tt += tok(t, a)
    acc, tk = c / n, tt / n
    return {"feature": f"const:{arm}", "arms": [arm], "n": n, "acc": acc, "tok": tk,
            "score": score_of(acc, tk), "acc_spread": 0.0, "score_spread": 0.0,
            "fallback_rate": fb / n, "acc_by_seed": []}


def oracle(rows: List[dict], arms: Sequence[str]) -> dict:
    """逐题 oracle（同等对错取最便宜）——不可部署，只作天花板。"""
    n = len(rows)
    c = tt = 0.0
    for t in rows:
        av = [a for a in arms if has(t, a)]
        if not av:
            continue
        good = [a for a in av if ok(t, a)]
        a = min(good or av, key=lambda x: tok(t, x))
        c += ok(t, a)
        tt += tok(t, a)
    acc, tk = c / n, tt / n
    return {"feature": f"oracle:{'+'.join(arms)}", "arms": list(arms), "n": n,
            "acc": acc, "tok": tk, "score": score_of(acc, tk),
            "acc_spread": 0.0, "score_spread": 0.0, "fallback_rate": 0.0,
            "acc_by_seed": []}


# ── 3. 前沿 ──────────────────────────────────────────────────────────
def mark_frontier(cands: List[dict]) -> List[dict]:
    for c in cands:
        c["on_frontier"] = not any(
            o is not c and o["acc"] >= c["acc"] and o["tok"] <= c["tok"]
            and (o["acc"] > c["acc"] or o["tok"] < c["tok"]) for o in cands)
    return sorted(cands, key=lambda c: -c["score"])


# ── 主流程 ──────────────────────────────────────────────────────────
def run(triples: str, qtext: Optional[str], seeds: int, folds: int,
        only_feature: Optional[str] = None) -> dict:
    rows, jstats = load_rows(triples, qtext)
    n = len(rows)
    v_acc = sum(t["v42_correct"] for t in rows) / n
    v_tok = sum(t["v42_tok"] for t in rows) / n
    baseline = {"strategy": "出厂 v4.2 四臂路由(含在线 LLM 聚焦)", "acc": v_acc,
                "tok": v_tok, "score": score_of(v_acc, v_tok), "zero_llm": False,
                "n": n, "fallback_rate": 0.0, "acc_spread": 0.0}

    feats = [only_feature] if only_feature else DEFAULT_CHAINS
    strategies: List[dict] = []
    if qtext:
        for arms in (ARMS, NO_RT):
            for f in feats:
                r = lexical_router(rows, arms, f, tuple(range(seeds)), folds)
                r["strategy"] = f"{f}·{'含rt' if 'rt' in arms else '无rt'}"
                r["zero_llm"] = True
                strategies.append(r)
    if qtext:
        r = combined_router(rows, NO_RT, seeds=tuple(range(max(seeds, 20))))
        r["strategy"] = "★最终: word3>word2>wh + 按库自适应"
        r["zero_llm"] = True
        strategies.append(r)
    for a in ARMS:
        r = constant_strategy(rows, a)
        r["strategy"] = f"常数 {a}"
        r["zero_llm"] = True
        strategies.append(r)

    ceilings = [oracle(rows, ARMS), oracle(rows, NO_RT)]
    for c in ceilings:
        c["strategy"] = c["feature"]
        c["zero_llm"] = True

    best = max((s for s in strategies if s["zero_llm"]), key=lambda s: s["score"])
    return {"join_stats": jstats, "n_rows": n, "baseline": baseline,
            "dominance": dominance(rows), "strategies": strategies,
            "ceilings": ceilings, "best": best,
            "frontier": mark_frontier(strategies + [baseline] + ceilings)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triples", default=DEFAULT_TRIPLES)
    ap.add_argument("--qtext", default=DEFAULT_QTEXT)
    ap.add_argument("--no-qtext", action="store_true")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--folds", type=int, default=2)
    ap.add_argument("--feature", default=None,
                    help="特征名，或用 > 连接的回落链，如 word3>word2>word1")
    ap.add_argument("--emit", default=None)
    ap.add_argument("--metric", choices=["score", "tok", "acc", "none"], default="none")
    a = ap.parse_args()

    res = run(a.triples, None if a.no_qtext else a.qtext, a.seeds, a.folds, a.feature)
    b = res["best"]

    if a.metric != "none":
        print({"score": f"{b['score']:.4f}", "tok": f"{b['tok']:.1f}",
               "acc": f"{b['acc'] * 100:.4f}"}[a.metric])
        return 0

    j = res["join_stats"]
    print(f"三元组 {j['triples']} 行", end="")
    if "joined" in j:
        print(f" | 联结: 精确 {j['exact']} / 前缀 {j['prefix']} / "
              f"多义丢弃 {j['ambiguous']} / 无题面 {j['no_text']} -> 可用 {j['joined']}")
    else:
        print()
    bl = res["baseline"]
    print(f"参与计算 {res['n_rows']} 行(所有策略同分母)")
    print(f"\n【基线】{bl['strategy']}\n  acc={bl['acc'] * 100:.2f}%  tok={bl['tok']:.0f}  "
          f"score={bl['score']:.3f}")

    print(f"\n{'=' * 92}\n1. 支配矩阵(同题;A 被 B 支配 = acc 更低且 tok 更高)\n{'=' * 92}")
    hits = [d for d in res["dominance"] if d["dominated_overall"]]
    if not hits:
        print("  未发现任何双向支配对。")
    for d in hits:
        print(f"  ⚠️ {d['dominated_arm']} 被 {d['by_arm']} 支配  n={d['n']}  "
              f"acc {d['a_acc']}%→{d['b_acc']}% ({d['b_acc'] - d['a_acc']:+.2f}pp)  "
              f"tok {d['a_tok']}→{d['b_tok']} ({d['a_tok'] / max(d['b_tok'], 1):.1f}x)")
        print(f"     分卷复核 {d['benches_dominated']}/{d['benches_total']} 卷成立")

    print(f"\n{'=' * 92}\n2. 策略表(同分母;uid 级 {a.folds} 折 × {a.seeds} 种子)\n{'=' * 92}")
    print(f"  {'':2s}{'策略':22s} {'acc':>8s} {'tok':>8s} {'score':>8s} {'Δscore':>8s} "
          f"{'种子极差':>8s} {'回落率':>7s}")
    for s in res["frontier"]:
        print(f"  {'★' if s.get('on_frontier') else ' ':2s}{s['strategy']:22s} "
              f"{s['acc'] * 100:7.2f}% {s['tok']:8.0f} {s['score']:8.3f} "
              f"{s['score'] - bl['score']:+8.3f} {s.get('score_spread', 0) :7.3f} "
              f"{s.get('fallback_rate', 0) * 100:6.1f}%")

    print(f"\n【当前最佳可部署(零 LLM)】{b['strategy']}  "
          f"acc={b['acc'] * 100:.2f}%  tok={b['tok']:.0f}  score={b['score']:.3f}")

    if a.emit:
        p = ROOT / a.emit
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"产物已写入 {a.emit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
