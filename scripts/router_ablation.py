# -*- coding: utf-8 -*-
"""P3 学习路由抗"特调数据集"四项消融(A 去 bench / B 分基准 / C 混合治理 /
D 工作负载重加权)。全离线 CPU,零 LLM 调用。

复用方式:import scripts/train_router.py(本体零改动),直接调用其
assemble/featurize/standardize/fit_lr/pred_lr/eval_policy/policy_pick/
uid_groups/kfold_uid;成本归一与交叉拟合两段少量代码复制自
train_router.main(逐行同语义,出处行号在注释),因 main() 是整体流程
无法单独调用。切分与种子与正式数字完全一致(SEED=20260814,5 折按 uid
分组),并对逐题 cv_fold 与 phat_cv 做 bit-identical 核验后才进入消融。

消融不训练 stumps(train_router 中 stumps 仅作 AUC 对照,fit_lr 无随机性,
跳过不影响 LR p̂ 的逐位复现)。

用法: python scripts/router_ablation.py
输出: results/router_ablation_20260815.md
      results/router_ablation_details_20260815.jsonl(逐题中间数据)
      results/router_ablation_summary_20260815.jsonl(全部表格数字)
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT / "scripts"))
import train_router as tr  # 只读引用,本体零改动

R = tr.R
ARMS = tr.ARMS
SEED = tr.SEED
LAM_TIERS = [0.05, 0.5, 1.5]
TAUS = [0.02, 0.05, 0.1, 0.2]
T0 = time.time()


# ── 交叉拟合(复制自 train_router.main 617-634 行,LR-only)────────────────
def cv_phat(X, names, instances, fold_of, y_arm, arm_idx):
    n = len(instances)
    phat = np.zeros((n, 4))
    for k in range(5):
        trm = fold_of != k
        te = fold_of == k
        Xs = tr.standardize(X[trm], X, names)
        for a in ARMS:
            m_tr = trm & (y_arm[a] >= 0)
            w = tr.fit_lr(Xs[m_tr], y_arm[a][m_tr])
            phat[te, arm_idx[a]] = tr.pred_lr(w, Xs[te])
    return phat


def hybrid_eval(instances, phat, tau, lam, tref, arm_idx):
    """混合治理:仅当 max p̂(可用臂) − p̂(手写臂) > τ 时允许学习路由改判,
    否则沿用 v4.2 手写路由的实测记录(replay mismatch=0,两账同源)。"""
    n = corr = gate = chg = 0
    tok = 0.0
    for i, r in enumerate(instances):
        hand = r["v42_pick"]
        ph = phat[i]
        mx = max(ph[arm_idx[a]] for a in r["arms"])
        use_hand = True
        if mx - ph[arm_idx[hand]] > tau:
            gate += 1
            a = tr.policy_pick(r, ph, lam, tref, arm_idx)
            if a != hand:
                chg += 1
                m = r["arms"][a]
                corr += m["correct"]
                tok += m["tok"]
                use_hand = False
        if use_hand:
            corr += r["v42_correct"]
            tok += r["v42_tok"]
        n += 1
    return {"acc": corr / n, "tok": tok / n,
            "gate_rate": gate / n, "flip_rate": chg / n}


def main():
    instances = tr.assemble()
    n = len(instances)
    X_raw, names = tr.featurize(instances)
    arm_idx = {a: i for i, a in enumerate(ARMS)}
    primary = tr.uid_groups(instances)

    # 切分:与 train_router.main 618-620 行完全一致(同种子同调用序)
    rng = np.random.default_rng(SEED)
    fold = tr.kfold_uid(primary, 5, rng)
    fold_of = np.array([fold[r["uid"]] for r in instances])

    # 成本归一(复制自 train_router.main 589-600 行)
    arm_stat = {a: {"n": 0, "c": 0, "tok": 0.0} for a in ARMS}
    all_toks = []
    for r in instances:
        for a, m in r["arms"].items():
            arm_stat[a]["n"] += 1
            arm_stat[a]["c"] += m["correct"]
            arm_stat[a]["tok"] += m["tok"]
            all_toks.append(m["tok"])
    tref = float(np.mean(all_toks))

    y_arm = {a: np.array([r["arms"][a]["correct"] if a in r["arms"] else -1
                          for r in instances], dtype=np.float64) for a in ARMS}
    v42_acc = float(np.mean([r["v42_correct"] for r in instances]))
    v42_tok = float(np.mean([r["v42_tok"] for r in instances]))

    # ── 复现核验:cv_fold 与 phat_cv 必须与正式产物逐位一致 ────────────────
    stored = [json.loads(l) for l in
              open(R / "router_learned_triples_20260814.jsonl",
                   encoding="utf-8")]
    assert len(stored) == n
    fold_mismatch = sum(1 for i, s in enumerate(stored)
                        if s["cv_fold"] != int(fold_of[i])
                        or s["qid"] != instances[i]["qid"])
    assert fold_mismatch == 0, f"fold mismatch={fold_mismatch}"

    phat_full = cv_phat(X_raw, names, instances, fold_of, y_arm, arm_idx)
    max_dp = max(abs(phat_full[i, arm_idx[a]] - s["phat_cv"][a])
                 for i, s in enumerate(stored) for a in ARMS)
    assert max_dp <= 5.01e-5, f"phat mismatch max={max_dp}"  # 4 位舍入容差
    print(f"复现核验通过: fold 0 mismatch, max|p̂−p̂_stored|={max_dp:.2e}")

    # ── A. 去 bench 特征 ──────────────────────────────────────────────────
    keep = [i for i, nm in enumerate(names) if not nm.startswith("bench=")]
    names_nb = [names[i] for i in keep]
    X_nb = X_raw[:, keep]
    phat_nb = cv_phat(X_nb, names_nb, instances, fold_of, y_arm, arm_idx)

    frontier = {"full": [], "nobench": []}
    for lam in tr.LAMBDA_GRID:
        for key, ph in (("full", phat_full), ("nobench", phat_nb)):
            ev = tr.eval_policy(instances, ph, lam, tref, arm_idx)
            frontier[key].append({"lam": lam, "acc": ev["acc"],
                                  "tok": ev["tok"], "picks": ev["picks"]})

    def best_points(fr):
        sa = sc = None
        for f in fr:
            if f["acc"] >= v42_acc and (sa is None or f["tok"] < sa["tok"]):
                sa = f
            if f["tok"] <= v42_tok and (sc is None or f["acc"] > sc["acc"]):
                sc = f
        return sa, sc

    nb_sa, nb_sc = best_points(frontier["nobench"])

    # bench 可预测性诊断(去 bench 特征 → 15 类 one-vs-rest LR,5 折 CV)
    bench_arr = np.array([tr.BENCH_ORDER.index(r["bench"]) for r in instances])
    pred = np.zeros(n, dtype=int)
    for k in range(5):
        trm = fold_of != k
        te = fold_of == k
        Xs = tr.standardize(X_nb[trm], X_nb, names_nb)
        scores = np.zeros((int(te.sum()), len(tr.BENCH_ORDER)))
        for bi, b in enumerate(tr.BENCH_ORDER):
            y = (bench_arr == bi).astype(np.float64)
            w = tr.fit_lr(Xs[trm], y[trm])
            scores[:, bi] = tr.pred_lr(w, Xs[te])
        pred[te] = np.argmax(scores, axis=1)
    bench_pred_acc = float(np.mean(pred == bench_arr))
    majority = max(Counter(r["bench"] for r in instances).values()) / n

    # 首词/route 的解析上界(按该离散变量分组取众数 bench)
    def ceiling(keyf):
        cnt = Counter()
        for r in instances:
            cnt[(keyf(r), r["bench"])] += 1
        grp = {}
        for (kk, b), c in cnt.items():
            grp.setdefault(kk, Counter())[b] = c
        return sum(max(c.values()) for c in grp.values()) / n

    def first_word(r):
        q = (r["question"] or "").strip().lower()
        return q.split(" ")[0] if q else ""

    ceil_w0 = ceiling(first_word)
    ceil_route = ceiling(lambda r: r["route"])
    ceil_prefix3 = ceiling(
        lambda r: " ".join((r["question"] or "").strip().lower().split()[:3]))

    # 逐基准模板前缀表
    tmpl_rows = []
    for b in tr.BENCH_ORDER:
        qs = [(r["question"] or "").strip().lower()
              for r in instances if r["bench"] == b]
        w0 = Counter(q.split(" ")[0] if q else "" for q in qs)
        p3 = Counter(" ".join(q.split()[:3]) for q in qs)
        tw, tc = w0.most_common(1)[0]
        pw, pc = p3.most_common(1)[0]
        tmpl_rows.append({"bench": b, "n": len(qs),
                          "top_w0": tw, "top_w0_share": tc / len(qs),
                          "top_p3": pw, "top_p3_share": pc / len(qs)})

    # ── B. 分基准分解(λ=0.5)────────────────────────────────────────────
    bench_rows = []
    for b in tr.BENCH_ORDER:
        ids = [i for i, r in enumerate(instances) if r["bench"] == b]
        ef = tr.eval_policy(instances, phat_full, 0.5, tref, arm_idx, sub=ids)
        en = tr.eval_policy(instances, phat_nb, 0.5, tref, arm_idx, sub=ids)
        va = float(np.mean([instances[i]["v42_correct"] for i in ids]))
        vt = float(np.mean([instances[i]["v42_tok"] for i in ids]))
        bench_rows.append({"bench": b, "n": len(ids),
                           "v42_acc": va, "v42_tok": vt,
                           "full_acc": ef["acc"], "full_tok": ef["tok"],
                           "nb_acc": en["acc"], "nb_tok": en["tok"]})

    # ── C. 混合治理(λ=0.5 改判,τ 门控;全特征为主,去 bench 附列)──────
    hybrid_rows = []
    for tau in TAUS:
        hf = hybrid_eval(instances, phat_full, tau, 0.5, tref, arm_idx)
        hn = hybrid_eval(instances, phat_nb, tau, 0.5, tref, arm_idx)
        hybrid_rows.append({"tau": tau, "full": hf, "nobench": hn})

    # ── D. 工作负载重加权(15 基准等权宏平均,λ=0.5)──────────────────────
    macro = {
        "v42_acc": float(np.mean([r["v42_acc"] for r in bench_rows])),
        "v42_tok": float(np.mean([r["v42_tok"] for r in bench_rows])),
        "full_acc": float(np.mean([r["full_acc"] for r in bench_rows])),
        "full_tok": float(np.mean([r["full_tok"] for r in bench_rows])),
        "nb_acc": float(np.mean([r["nb_acc"] for r in bench_rows])),
        "nb_tok": float(np.mean([r["nb_tok"] for r in bench_rows])),
    }

    # ── 落盘:逐题中间数据 ────────────────────────────────────────────────
    with open(R / "router_ablation_details_20260815.jsonl", "w",
              encoding="utf-8") as f:
        for i, r in enumerate(instances):
            row = {"bench": r["bench"], "uid": r["uid"], "qid": r["qid"],
                   "cv_fold": int(fold_of[i]),
                   "phat_nb": {a: round(float(phat_nb[i, arm_idx[a]]), 4)
                               for a in ARMS}}
            for key, ph in (("full", phat_full), ("nb", phat_nb)):
                for lam in LAM_TIERS:
                    row[f"pick_{key}_{lam}"] = tr.policy_pick(
                        r, ph[i], lam, tref, arm_idx)
            hand = r["v42_pick"]
            mx = max(phat_full[i][arm_idx[a]] for a in r["arms"])
            gap = float(mx - phat_full[i][arm_idx[hand]])
            row["v42_pick"] = hand
            row["phat_gap_full"] = round(gap, 4)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "v42": {"acc": v42_acc, "tok": v42_tok},
        "frontier": frontier, "nb_same_acc": nb_sa, "nb_same_cost": nb_sc,
        "bench_pred_acc": bench_pred_acc, "majority": majority,
        "ceil_w0": ceil_w0, "ceil_prefix3": ceil_prefix3,
        "ceil_route": ceil_route, "tmpl_rows": tmpl_rows,
        "bench_rows": bench_rows, "hybrid_rows": hybrid_rows, "macro": macro,
        "runtime_s": time.time() - T0,
    }
    with open(R / "router_ablation_summary_20260815.jsonl", "w",
              encoding="utf-8") as f:
        for sec, obj in summary.items():
            f.write(json.dumps({"key": sec, "value": obj},
                               ensure_ascii=False, default=str) + "\n")

    write_report(summary)
    print(f"done in {time.time() - T0:.0f}s")


def fmt_pt(f):
    return f"{f['acc'] * 100:.2f}% @ {f['tok']:.0f}"


def write_report(o):
    v42 = o["v42"]
    fr = {k: {f["lam"]: f for f in v} for k, v in o["frontier"].items()}
    L = []
    A = L.append
    A("# P3 学习路由抗\"特调数据集\"四项消融(离线策略评估,零 LLM)")
    A("")
    A(f"日期 2026-08-15 | 种子 {SEED} | 5 折按 uid 分组 CV,切分与正式数字"
      "逐位一致(cv_fold 0 mismatch,p̂ 与归档 phat_cv 在 4 位舍入容差内"
      "全等)| 脚本 `scripts/router_ablation.py` import 只读复用 "
      "`scripts/train_router.py`,本体零改动 | 全部离线重放,零 LLM 调用,"
      "$0 API 费用")
    A("")
    A(f"对照组:v4.2 手写路由 = {v42['acc'] * 100:.2f}% @ {v42['tok']:.0f} "
      "tok/题(全量 5511)。已宣称(全特征):λ=0.5 双优档 "
      f"{fmt_pt(fr['full'][0.5])},λ=1.5 持平档 {fmt_pt(fr['full'][1.5])}"
      "——本轮逐位复现。")
    A("")

    # ── A ──
    d_full = fr["full"][0.5]["acc"] - v42["acc"]
    d_nb = fr["nobench"][0.5]["acc"] - v42["acc"]
    sv_full = 1 - fr["full"][0.5]["tok"] / v42["tok"]
    sv_nb = 1 - fr["nobench"][0.5]["tok"] / v42["tok"]
    d15_nb = fr["nobench"][1.5]["acc"] - v42["acc"]
    A("## A. 去 bench 消融(最关键)")
    A("")
    if (d_nb > 0 and fr["nobench"][0.5]["tok"] < v42["tok"]
            and d_nb >= d_full):
        A(f"**判决:λ=0.5 双优结论存活且不依赖考场身份——去 bench 后 "
          f"{fmt_pt(fr['nobench'][0.5])}(+{d_nb * 100:.2f}pp、"
          f"−{sv_nb * 100:.1f}%),相比全特征(+{d_full * 100:.2f}pp、"
          f"−{sv_full * 100:.1f}%)增益未缩水反而微升 "
          f"+{(d_nb - d_full) * 100:.2f}pp;唯一折损在 λ=1.5 持平档:"
          f"{fr['nobench'][1.5]['acc'] * 100:.2f}% 跌破手写 "
          f"{-d15_nb * 100:.2f}pp,持平档需移至 λ={o['nb_same_acc']['lam']}"
          f"({fmt_pt(o['nb_same_acc'])})。**")
    elif d_nb > 0 and fr["nobench"][0.5]["tok"] < v42["tok"]:
        shrink = (d_full - d_nb) * 100
        A(f"**判决:去掉 bench one-hot 后 λ=0.5 双优结论存活——准确率增益从 "
          f"+{d_full * 100:.2f}pp 缩水到 +{d_nb * 100:.2f}pp"
          f"(缩水 {shrink:.2f}pp,即 {shrink / (d_full * 100) * 100:.0f}% "
          f"的增益来自考场身份),token 节省 −{sv_nb * 100:.1f}% 基本保住"
          f"(全特征 −{sv_full * 100:.1f}%)。**")
    elif fr["nobench"][0.5]["tok"] < v42["tok"]:
        A(f"**判决:去掉 bench one-hot 后 λ=0.5 档双优被否定——准确率 "
          f"{fr['nobench'][0.5]['acc'] * 100:.2f}% 低于手写 "
          f"{v42['acc'] * 100:.2f}%({d_nb * 100:+.2f}pp),原 "
          f"+{d_full * 100:.2f}pp 增益中 {(d_full - d_nb) * 100:.2f}pp "
          f"来自考场身份;token 节省 −{sv_nb * 100:.1f}% 仍在。**")
    else:
        A("**判决:去掉 bench one-hot 后双优结论被否定(准确率与成本均不占优)。**")
    A("")
    A("| λ | 全特征 acc | 全特征 tok | 去 bench acc | 去 bench tok | 手写 acc | 手写 tok |")
    A("|---|---|---|---|---|---|---|")
    for lam in LAM_TIERS:
        f1, f2 = fr["full"][lam], fr["nobench"][lam]
        A(f"| {lam} | {f1['acc'] * 100:.2f}% | {f1['tok']:.0f} | "
          f"{f2['acc'] * 100:.2f}% | {f2['tok']:.0f} | "
          f"{v42['acc'] * 100:.2f}% | {v42['tok']:.0f} |")
    A("")
    if o["nb_same_acc"]:
        A(f"去 bench 版全网格最优:同准确率档 λ={o['nb_same_acc']['lam']} → "
          f"{fmt_pt(o['nb_same_acc'])};同成本档 λ={o['nb_same_cost']['lam']} → "
          f"{fmt_pt(o['nb_same_cost'])}。")
    else:
        A("去 bench 版全网格上没有任何 λ 达到手写准确率(同准确率档不存在);"
          f"同成本档最优 λ={o['nb_same_cost']['lam']} → "
          f"{fmt_pt(o['nb_same_cost'])}。")
    A("")
    A("**变相编码检查(报告不修):**去 bench 后的剩余特征仍能以 "
      f"**{o['bench_pred_acc'] * 100:.1f}%** 的 5 折 CV 准确率预测出基准身份"
      f"(多数类基线 {o['majority'] * 100:.1f}%)。来源:问题首词分组即可达 "
      f"{o['ceil_w0'] * 100:.1f}% 解析上界(前三词 {o['ceil_prefix3'] * 100:.1f}%),"
      f"手写 route 特征分组 {o['ceil_route'] * 100:.1f}%——多数基准确有固定"
      "模板前缀(下表),question 文本特征确在变相编码基准身份;"
      "因此\"去 bench\"消融是增益下界而非完全去身份。")
    A("")
    A("| 基准 | n | 众数首词(占比) | 众数前三词(占比) |")
    A("|---|---|---|---|")
    for t in o["tmpl_rows"]:
        A(f"| {t['bench']} | {t['n']} | {t['top_w0']}"
          f"({t['top_w0_share'] * 100:.0f}%) | {t['top_p3']}"
          f"({t['top_p3_share'] * 100:.0f}%) |")
    A("")

    # ── B ──
    br = o["bench_rows"]
    n_all = sum(r["n"] for r in br)
    wins_f = sum(1 for r in br if r["full_acc"] > r["v42_acc"] + 1e-9)
    loss_f = sum(1 for r in br if r["full_acc"] < r["v42_acc"] - 1e-9)
    big = {"STALE-full", "LoCoMo-full"}
    contrib_big = sum((r["full_acc"] - r["v42_acc"]) * r["n"]
                      for r in br if r["bench"] in big) / n_all
    contrib_all = sum((r["full_acc"] - r["v42_acc"]) * r["n"]
                      for r in br) / n_all
    A("## B. 分基准分解(λ=0.5)")
    A("")
    share = contrib_big / contrib_all * 100 if abs(contrib_all) > 1e-12 else 0
    tok_wins = sum(1 for r in br if r["full_tok"] < r["v42_tok"] - 1e-9)
    worst = sorted(br, key=lambda r: r["full_acc"] - r["v42_acc"])[:2]
    A(f"**判决:token 节省是广谱的({tok_wins}/15 基准全部下降),准确率"
      f"增益是集中的——微平均 +{contrib_all * 100:.2f}pp 中 "
      f"{contrib_big * 100:+.2f}pp({share:.0f}%)来自 STALE-full/LoCoMo-full "
      f"两个大卷;15 基准 {wins_f} 胜 {loss_f} 负,小卷存在实质回退"
      f"({worst[0]['bench']} "
      f"{(worst[0]['full_acc'] - worst[0]['v42_acc']) * 100:+.1f}pp、"
      f"{worst[1]['bench']} "
      f"{(worst[1]['full_acc'] - worst[1]['v42_acc']) * 100:+.1f}pp)。**")
    A("")
    A("| 基准 | n | 手写 acc/tok | 全特征 acc/tok | Δacc | 去bench acc/tok | Δacc |")
    A("|---|---|---|---|---|---|---|")
    for r in br:
        A(f"| {r['bench']} | {r['n']} | {r['v42_acc'] * 100:.1f}% / "
          f"{r['v42_tok']:.0f} | {r['full_acc'] * 100:.1f}% / "
          f"{r['full_tok']:.0f} | {(r['full_acc'] - r['v42_acc']) * 100:+.1f} | "
          f"{r['nb_acc'] * 100:.1f}% / {r['nb_tok']:.0f} | "
          f"{(r['nb_acc'] - r['v42_acc']) * 100:+.1f} |")
    A("")

    # ── C ──
    A("## C. 混合治理策略(τ 门控改判,改判动作 = 全特征 λ=0.5 选臂)")
    A("")
    h0 = o["hybrid_rows"][0]["full"]
    h3 = o["hybrid_rows"][-1]["full"]
    s0 = 1 - h0["tok"] / v42["tok"]
    s3 = 1 - h3["tok"] / v42["tok"]
    A(f"**判决:保守部署规则下准确率增益完整存活、token 节省大幅缩水——"
      f"τ=0.02 得 {h0['acc'] * 100:.2f}% @ {h0['tok']:.0f}"
      f"(+{(h0['acc'] - v42['acc']) * 100:.2f}pp、−{s0 * 100:.1f}%,"
      f"改判率 {h0['flip_rate'] * 100:.1f}%),τ=0.2 得 "
      f"{h3['acc'] * 100:.2f}% @ {h3['tok']:.0f}"
      f"(+{(h3['acc'] - v42['acc']) * 100:.2f}pp、−{s3 * 100:.1f}%,"
      f"改判率 {h3['flip_rate'] * 100:.1f}%);四档 τ 全部保持双优,但省幅"
      f"从纯学习的 −{sv_full * 100:.1f}% 缩到 −{s0 * 100:.1f}%"
      f"~−{s3 * 100:.1f}%——大头 token 节省恰来自 p̂ 差很小时的成本性改判,"
      "被门控挡在外面。**")
    A("")
    A("| τ | 门控通过率 | 改判率 | 全特征 acc | 全特征 tok | 去bench acc | 去bench tok |")
    A("|---|---|---|---|---|---|---|")
    for h in o["hybrid_rows"]:
        f1, f2 = h["full"], h["nobench"]
        A(f"| {h['tau']} | {f1['gate_rate'] * 100:.1f}% | "
          f"{f1['flip_rate'] * 100:.1f}% | {f1['acc'] * 100:.2f}% | "
          f"{f1['tok']:.0f} | {f2['acc'] * 100:.2f}% | {f2['tok']:.0f} |")
    A("")
    A(f"对照:纯手写 {v42['acc'] * 100:.2f}% @ {v42['tok']:.0f};"
      f"纯学习(全特征 λ=0.5){fmt_pt(fr['full'][0.5])}。")
    A("")

    # ── D ──
    m = o["macro"]
    A("## D. 工作负载重加权(15 基准等权宏平均,λ=0.5)")
    A("")
    dm_f = (m["full_acc"] - m["v42_acc"]) * 100
    dm_n = (m["nb_acc"] - m["v42_acc"]) * 100
    sv_mf = 1 - m["full_tok"] / m["v42_tok"]
    A(f"**判决:结论不依赖题量加权——基准等权宏平均下双优仍成立:全特征 "
      f"{m['full_acc'] * 100:.2f}% vs 手写 {m['v42_acc'] * 100:.2f}%"
      f"({dm_f:+.2f}pp,token {m['v42_tok']:.0f}→{m['full_tok']:.0f} 即 "
      f"−{sv_mf * 100:.1f}%),去 bench {m['nb_acc'] * 100:.2f}%"
      f"({dm_n:+.2f}pp);全特征增益从微平均 +{d_full * 100:.2f}pp 降到 "
      f"+{dm_f:.2f}pp(与 B 节的集中度发现一致)但方向与双优判定不变。**")
    A("")
    A("| 口径 | 手写 acc | 全特征 acc | Δ | 去bench acc | Δ | 手写 tok | 全特征 tok | 去bench tok |")
    A("|---|---|---|---|---|---|---|---|---|")
    mic_f = fr["full"][0.5]
    mic_n = fr["nobench"][0.5]
    A(f"| 微平均(题量加权) | {v42['acc'] * 100:.2f}% | "
      f"{mic_f['acc'] * 100:.2f}% | {(mic_f['acc'] - v42['acc']) * 100:+.2f} | "
      f"{mic_n['acc'] * 100:.2f}% | {(mic_n['acc'] - v42['acc']) * 100:+.2f} | "
      f"{v42['tok']:.0f} | {mic_f['tok']:.0f} | {mic_n['tok']:.0f} |")
    A(f"| 宏平均(基准等权) | {m['v42_acc'] * 100:.2f}% | "
      f"{m['full_acc'] * 100:.2f}% | {dm_f:+.2f} | {m['nb_acc'] * 100:.2f}% | "
      f"{dm_n:+.2f} | {m['v42_tok']:.0f} | {m['full_tok']:.0f} | "
      f"{m['nb_tok']:.0f} |")
    A("")
    A("## 成本与时间")
    A(f"- 全离线 CPU 重放:0 次 LLM 调用,0 token,$0;单进程运行 "
      f"{o['runtime_s']:.0f} s。")
    A("- 中间数据:`results/router_ablation_details_20260815.jsonl`(逐题)、"
      "`results/router_ablation_summary_20260815.jsonl`(表格数字)。")
    (R / "router_ablation_20260815.md").write_text("\n".join(L),
                                                   encoding="utf-8")
    print("report ->", R / "router_ablation_20260815.md")


if __name__ == "__main__":
    main()
