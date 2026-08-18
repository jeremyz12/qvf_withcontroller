# -*- coding: utf-8 -*-
"""armdom.core — 支配性审计与零 LLM 路由的核心算法。

术语与口径见 README。三条不可让步的口径约定，全部在本文件实现而非仅写在文档里：

1. **同分母**：所有策略在同一批行上评分；选中的臂在该行没跑过时按 ``FALLBACK_ORDER``
   回落，回落计入该策略的成绩。按各臂自己的可用子集报分会让低覆盖臂虚高。
2. **库级留出**：同一个 ``uid``（库）绝不跨折。跨折会让路由器记住某个具体库。
3. **前瞻 + bandit**：按库自适应只用该库此前已答题，且只观测**被选中**那条臂的结果。
"""
from __future__ import annotations

import collections
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

#: 回落顺序由调用方按"便宜优先"给出；缺省留空表示按 arms 顺序。
FALLBACK_ORDER: Tuple[str, ...] = ()

TOKEN_WEIGHT = 0.5


def set_fallback_order(order: Sequence[str]) -> None:
    """设定回落顺序（通常按平均 token 从低到高）。"""
    global FALLBACK_ORDER
    FALLBACK_ORDER = tuple(order)


def has(t: dict, a: str) -> bool:
    return a in t["arms"] and t["arms"][a].get("correct") is not None


def ok(t: dict, a: str) -> bool:
    return bool(t["arms"][a]["correct"])


def tok(t: dict, a: str) -> float:
    return float(t["arms"][a]["tok"])


def resolve(t: dict, a: Optional[str],
            arms: Sequence[str] = ()) -> Optional[str]:
    """把"想选的臂"落到"该行真能跑的臂"。回落顺序固定，便宜优先。"""
    if a is not None and has(t, a):
        return a
    for f in (FALLBACK_ORDER or arms):
        if has(t, f):
            return f
    return None


def score_of(acc: float, tk: float, weight: float = None) -> float:
    w = TOKEN_WEIGHT if weight is None else weight
    return acc * 100 - w * tk / 1000.0


def dominance(rows: List[dict], arms: Sequence[str],
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
                   features: Dict[str, Callable[[dict], str]],
                   seeds: Sequence[int] = tuple(range(5)), folds: int = 2,
                   min_sup: int = 10, slack: float = 0.01) -> dict:
    """uid 级 K 折留出的零 LLM 路由。**所有行都计入分母**，不可用臂按 resolve() 回落。

    `feat` 可以是单个特征名，也可以是用 `>` 连起来的**回落链**（如 `word3>word2>word1`）：
    测试时按链序找第一个支持度够的桶，全链落空才退到全局选臂。动机：细粒度桶命中率低
    （word3 单用时 52.6% 的题落不到桶里），层级回落让细桶只在它真有数据时才生效。
    """
    chain = feat.split(">")
    fns = [features[c] for c in chain]
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
                a = resolve(t, want, arms)
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
                     features: Dict[str, Callable[[dict], str]],
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
    fns = [features[l] for l in levels]
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
                a = resolve(t, want, arms)
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


def combined_router(rows: List[dict], arms: Sequence[str],
                    features: Dict[str, Callable[[dict], str]],
                    chain: str = "word3>word2>wh",
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
    fns = [features[c] for c in chain.split(">")]
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
                    a = resolve(t, want, arms)
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
        a = resolve(t, arm, (arm,))
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


def mark_frontier(cands: List[dict]) -> List[dict]:
    for c in cands:
        c["on_frontier"] = not any(
            o is not c and o["acc"] >= c["acc"] and o["tok"] <= c["tok"]
            and (o["acc"] > c["acc"] or o["tok"] < c["tok"]) for o in cands)
    return sorted(cands, key=lambda c: -c["score"])
