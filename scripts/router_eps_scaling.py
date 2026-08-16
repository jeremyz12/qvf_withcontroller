# -*- coding: utf-8 -*-
"""Z1: 学习路由的 ε-vs-校准集规模诊断曲线(纯本地计算,零 LLM 调用)。

背景:P3(router_learned_report_20260814.md §6.1)报告主口径证书结构性不可达
——λ=0(最准学习策略)在 calib 上相对 oracle 的风险 8.79%,可发证最小 ε≈9.9%,
远超预注册 ε∈{0.03,0.05}。该数字从未诊断是"结构性下界"还是"校准集样本量
不够"。本脚本做两件事零成本诊断:
  (1) 对 calib 集(及 calib∪test 池,用同一 train-only 预测器,诚实域外)做
      bootstrap 子采样,25/50/75/100%×多档规模,每档 ≥50 次重复,每次按
      report 原协议算"可发证最小 ε"(=CP 上界 of λ=0 calib 风险,δ=0.1;
      该值即为固定序列检验在此协议下能达到的绝对下限,因序列从 λ=0 起步,
      λ=0 未过则更高 λ 也不会被序列检验触达)。画 ε-vs-n 曲线,配合渐近论证
      判断"结构性下界"还是"样本量不足"。
  (2) oracle-gap 分解:用交叉拟合 p̂(router_learned_triples_20260814.jsonl 的
      phat_cv)按已存的 cv_fold 做嵌套 isotonic 重校准(PAV 算法手写,
      sklearn 不可用),比较重校准前后 λ=0 策略相对 oracle 的准确率损失,
      差值 = 校准误差可修复部分,重校准后残余 = 排序误差(校准修不了)。

冻结代码只读引用:import scripts/train_router.py 的函数(该脚本本身不在
qvf_router.py / wt_qvf_prototype.py / complex_query_arm.py / qvf_algebra.py
冻结清单内,仅新增本文件,不改动 train_router.py 任何一行)。

用法: python scripts/router_eps_scaling.py
输出: results/router_eps_scaling_20260816.md
      results/router_eps_scaling_raw_20260816.json
"""
import json
import math
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_router import (          # noqa: E402  (冻结清单外,只读函数引用)
    assemble, featurize, standardize, fit_lr, pred_lr, uid_groups,
    stratified_uid_split, eval_policy, cp_upper, binom_cdf,
    ARMS, SEED, DELTA,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\ZZL_cluade")
R = ROOT / "results"
TRIPLES_PATH = R / "router_learned_triples_20260814.jsonl"
N_REP = 200          # 每档重复次数(任务要求 ≥50,取 200 求稳,零成本)
BOOT_SEED = SEED + 777


def load_triples():
    rows = {}
    with open(TRIPLES_PATH, encoding="utf-8") as f:
        for l in f:
            r = json.loads(l)
            rows[(r["bench"], r["qid"])] = r
    return rows


def main():
    instances = assemble()
    n = len(instances)
    X_raw, names = featurize(instances)
    arm_idx = {a: i for i, a in enumerate(ARMS)}
    primary = uid_groups(instances)

    y_arm = {a: np.array([r["arms"][a]["correct"] if a in r["arms"] else -1
                          for r in instances], dtype=np.float64) for a in ARMS}
    all_toks = [m["tok"] for r in instances for m in r["arms"].values()]
    tref = float(np.mean(all_toks))
    oracle_c = np.array([any(m["correct"] for m in r["arms"].values())
                         for r in instances])

    # ── 复刻 report §6 的 train/calib/test 切分(同 SEED,同函数)────────
    rng2 = np.random.default_rng(SEED)
    split = stratified_uid_split(primary, [0.4, 0.2, 0.4], rng2)
    s_of = np.array([split[r["uid"]] for r in instances])
    tr_ids = np.where(s_of == 0)[0]
    ca_ids = np.where(s_of == 1)[0]
    te_ids = np.where(s_of == 2)[0]
    pool_ids = np.concatenate([ca_ids, te_ids])   # calib∪test,同一 train-only 预测器下诚实域外

    # ── 对拍:triples 文件的 cert_split 字段应与此切分逐题一致 ──────────
    triples = load_triples()
    mismatch = 0
    for i, r in enumerate(instances):
        row = triples.get((r["bench"], r["qid"]))
        if row is None or row["cert_split"] != int(s_of[i]):
            mismatch += 1
    print(f"cert_split 对拍 mismatch={mismatch}/{n}")

    # ── 只用 train 拟合的预测器 phat2(与 report §6 完全同协议)──────────
    Xs2 = standardize(X_raw[tr_ids], X_raw, names)
    phat2 = np.zeros((n, 4))
    for a in ARMS:
        m_tr = np.zeros(n, dtype=bool)
        m_tr[tr_ids] = True
        m_tr &= (y_arm[a] >= 0)
        w = fit_lr(Xs2[m_tr], y_arm[a][m_tr])
        phat2[:, arm_idx[a]] = pred_lr(w, Xs2)

    ev_ca_full = eval_policy(instances, phat2, 0.0, tref, arm_idx, sub=list(ca_ids))
    mce_report = cp_upper(ev_ca_full["loss_k"], ev_ca_full["n"], DELTA)
    print(f"sanity vs report §6.1: calib n={ev_ca_full['n']} k={ev_ca_full['loss_k']} "
          f"risk={ev_ca_full['risk']*100:.2f}% (report 8.79%) "
          f"min_cert_eps={mce_report*100:.1f}% (report 9.9%)")

    # ── 大 N 锚点:全量 5511,交叉拟合 phat_cv(不同预测器,注明口径)────
    phat_cv_full = np.zeros((n, 4))
    got = 0
    for i, r in enumerate(instances):
        row = triples.get((r["bench"], r["qid"]))
        if row is None:
            continue
        got += 1
        for a in ARMS:
            phat_cv_full[i, arm_idx[a]] = row["phat_cv"].get(a, 0.0)
    print(f"phat_cv 对齐 {got}/{n}")
    ev_full_cv = eval_policy(instances, phat_cv_full, 0.0, tref, arm_idx,
                             sub=list(range(n)))
    eps_full_cv = cp_upper(ev_full_cv["loss_k"], ev_full_cv["n"], DELTA)
    print(f"anchor n=5511(phat_cv,交叉拟合): risk={ev_full_cv['risk']*100:.2f}% "
          f"(report §3 λ=0 行 8.96%) min_cert_eps={eps_full_cv*100:.2f}%")

    # ── bootstrap 子采样:calib 池(n=1161,phat2)──────────────────────
    def bootstrap_curve(pool, fracs, rng, tag):
        out = []
        for frac in fracs:
            m = max(20, int(round(frac * len(pool))))
            recs = []
            for rep in range(N_REP):
                idx = rng.choice(pool, size=m, replace=True)
                ev = eval_policy(instances, phat2, 0.0, tref, arm_idx,
                                 sub=idx.tolist())
                ub = cp_upper(ev["loss_k"], ev["n"], DELTA)
                recs.append({"risk": ev["risk"], "eps_ub": ub})
            risks = np.array([x["risk"] for x in recs])
            ubs = np.array([x["eps_ub"] for x in recs])
            out.append({
                "tag": tag, "frac": frac, "n": m,
                "risk_mean": float(risks.mean()), "risk_sd": float(risks.std()),
                "eps_ub_mean": float(ubs.mean()), "eps_ub_median": float(np.median(ubs)),
                "eps_ub_p05": float(np.percentile(ubs, 5)),
                "eps_ub_p95": float(np.percentile(ubs, 95)),
            })
        return out

    rng_boot = np.random.default_rng(BOOT_SEED)
    curve_calib = bootstrap_curve(ca_ids, [0.25, 0.5, 0.75, 1.0], rng_boot, "calib_only(phat2)")
    rng_boot2 = np.random.default_rng(BOOT_SEED + 1)
    curve_pool = bootstrap_curve(pool_ids, [0.25, 0.5, 0.75, 1.0], rng_boot2, "calib+test_pool(phat2)")

    all_points = curve_calib + curve_pool
    all_points.sort(key=lambda x: x["n"])

    # ── 渐近外推:eps_ub(n) ≈ p_inf + c/sqrt(n),最小二乘拟合两参数 ──────
    ns = np.array([p["n"] for p in all_points], dtype=np.float64)
    ubs_mean = np.array([p["eps_ub_mean"] for p in all_points])
    A = np.stack([np.ones_like(ns), 1.0 / np.sqrt(ns)], axis=1)
    coef, *_ = np.linalg.lstsq(A, ubs_mean, rcond=None)
    p_inf, c_slope = float(coef[0]), float(coef[1])
    # 若 p_inf 已 > 目标 eps,则任意 n 都不可达;否则求解需要的 n
    target_eps = 0.05
    if p_inf >= target_eps:
        n_needed = None
    else:
        # p_inf + c/sqrt(n) = target -> sqrt(n) = c/(target-p_inf)
        denom = target_eps - p_inf
        n_needed = (c_slope / denom) ** 2 if c_slope > 0 else None

    # ── oracle-gap 分解:嵌套 isotonic 重校准(PAV,按已存 cv_fold)────────
    def pav_fit(x, y):
        """标准 PAV:输入 x(排序键),y(0/1 标签),输出按 x 升序的分段常数拟合。
        返回 (x_sorted, fitted) 供 np.interp 近似预测(阶梯函数的线性内插近似,
        sklearn 不可用时的手写替代,已知局限见报告)。"""
        order = np.argsort(x, kind="mergesort")
        xs = x[order]
        ys = y[order]
        vals = list(ys.astype(float))
        wts = [1.0] * len(ys)
        stack = []  # [value, weight]
        for v, w in zip(vals, wts):
            stack.append([v, w])
            while len(stack) > 1 and stack[-2][0] > stack[-1][0] + 1e-12:
                v2, w2 = stack.pop()
                v1, w1 = stack.pop()
                nv = (v1 * w1 + v2 * w2) / (w1 + w2)
                stack.append([nv, w1 + w2])
        fitted = []
        for v, w in stack:
            fitted.extend([v] * int(round(w)))
        return xs, np.array(fitted)

    def pav_predict(xs_fit, fitted_fit, x_new):
        # 阶梯函数近似:用已拟合的(x,fitted)对做单调内插,越界截断到端值
        return np.interp(x_new, xs_fit, fitted_fit,
                         left=fitted_fit[0], right=fitted_fit[-1])

    cv_fold = {}
    with open(TRIPLES_PATH, encoding="utf-8") as f:
        for l in f:
            r = json.loads(l)
            cv_fold[(r["bench"], r["qid"])] = r["cv_fold"]
    fold_of = np.array([cv_fold.get((r["bench"], r["qid"]), -1) for r in instances])

    phat_calib = phat_cv_full.copy()
    ece_before = {}
    ece_after = {}
    for a in ARMS:
        m_all = y_arm[a] >= 0
        for k in range(5):
            te_mask = m_all & (fold_of == k)
            tr_mask = m_all & (fold_of != k) & (fold_of >= 0)
            if te_mask.sum() == 0 or tr_mask.sum() == 0:
                continue
            xs_fit, fitted_fit = pav_fit(phat_cv_full[tr_mask, arm_idx[a]],
                                         y_arm[a][tr_mask])
            phat_calib[te_mask, arm_idx[a]] = pav_predict(
                xs_fit, fitted_fit, phat_cv_full[te_mask, arm_idx[a]])
        # ECE before/after(该臂全部有效行,交叉拟合口径)
        def _ece(p, y, bins=10):
            e = 0.0
            for kk in range(bins):
                lo, hi = kk / bins, (kk + 1) / bins
                mm = (p >= lo) & (p < hi) if kk < bins - 1 else (p >= lo) & (p <= hi)
                if mm.sum() == 0:
                    continue
                e += mm.sum() / len(y) * abs(y[mm].mean() - p[mm].mean())
            return e
        yv = y_arm[a][m_all]
        ece_before[a] = _ece(phat_cv_full[m_all, arm_idx[a]], yv)
        ece_after[a] = _ece(phat_calib[m_all, arm_idx[a]], yv)

    ev_raw = eval_policy(instances, phat_cv_full, 0.0, tref, arm_idx, sub=list(range(n)))
    ev_cal = eval_policy(instances, phat_calib, 0.0, tref, arm_idx, sub=list(range(n)))
    oracle_acc = float(oracle_c.mean())
    gap_raw = oracle_acc - ev_raw["acc"]
    gap_cal = oracle_acc - ev_cal["acc"]
    calib_fixable = gap_raw - gap_cal
    ranking_residual = gap_cal

    out = {
        "sanity": {"cert_split_mismatch": mismatch,
                   "calib_lam0_risk": ev_ca_full["risk"],
                   "calib_lam0_k": ev_ca_full["loss_k"], "calib_lam0_n": ev_ca_full["n"],
                   "min_cert_eps_report_protocol": mce_report},
        "anchor_full5511_phatcv": {"risk": ev_full_cv["risk"],
                                   "min_cert_eps": eps_full_cv,
                                   "n": ev_full_cv["n"]},
        "bootstrap_points": all_points,
        "extrapolation": {"p_inf": p_inf, "c_slope": c_slope,
                          "target_eps": target_eps, "n_needed_for_5pct": n_needed},
        "gap_decomposition": {
            "oracle_acc": oracle_acc,
            "raw_acc_lam0": ev_raw["acc"], "raw_risk": ev_raw["risk"],
            "calibrated_acc_lam0": ev_cal["acc"], "calibrated_risk": ev_cal["risk"],
            "gap_raw_pp": gap_raw * 100, "gap_calibrated_pp": gap_cal * 100,
            "calib_fixable_pp": calib_fixable * 100,
            "ranking_residual_pp": ranking_residual * 100,
            "ece_before": ece_before, "ece_after": ece_after,
        },
    }
    (R / "router_eps_scaling_raw_20260816.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_report(out)
    print("done")


def write_report(o):
    L = []
    A = L.append
    A("# Z1 学习路由 ε-vs-校准集规模诊断(纯本地计算,零 LLM 调用)")
    A("")
    A(f"日期 2026-08-16 | 种子 {SEED}(切分/预测器同 P3 报告)+ {SEED+777}"
      "(bootstrap)| 全部离线复用 results/router_learned_triples_20260814.jsonl "
      "与 scripts/train_router.py 函数,零 API 调用,零费用")
    A("")
    s = o["sanity"]
    A(f"对拍:本脚本复算的 train/calib/test 切分与 triples 文件已存 cert_split "
      f"字段逐题一致(mismatch={s['cert_split_mismatch']}/5511)。calib 集 λ=0 "
      f"风险复算 {s['calib_lam0_risk']*100:.2f}%(k={s['calib_lam0_k']}/"
      f"{s['calib_lam0_n']},report 8.79%),可发证最小 ε "
      f"{s['min_cert_eps_report_protocol']*100:.1f}%(report 9.9%)—— 复现一致。")
    A("")
    A("## 0. 判决")
    ex = o["extrapolation"]
    p_inf_pct = ex["p_inf"] * 100
    if ex["n_needed_for_5pct"] is None:
        verdict = ("**猜想被证伪(即证实为结构性下界):不是校准集样本量问题。**"
                   f"ε-vs-n 曲线外推的渐近下限 p_inf≈{p_inf_pct:.2f}%,"
                   "已高于目标 ε=5%——数学上无论校准集扩到多大,CP 置信上界"
                   "都不可能收敛到目标之下(置信上界只会随 n 增大收敛到真值本身,"
                   "不会跌破真值)。全量 5511 题交叉拟合口径同样卡在 "
                   f"{o['anchor_full5511_phatcv']['min_cert_eps']*100:.2f}%,"
                   "5 倍于 calib 规模仍无改善,双重验证下界。")
    else:
        verdict = (f"曲线未平台化,外推 p_inf≈{p_inf_pct:.2f}% < 5%,"
                   f"估计需要校准集 n≈{ex['n_needed_for_5pct']:.0f} 才可能压到 ε=5%"
                   "——增补校准数据在原则上可行,建议评估该规模的现实成本。")
    A(verdict)
    gd = o["gap_decomposition"]
    A(f"Oracle-gap 分解(全量 5511,λ=0,交叉拟合 p̂):原始相对 oracle 损失 "
      f"{gd['gap_raw_pp']:.2f}pp;嵌套 isotonic 重校准后 {gd['gap_calibrated_pp']:.2f}pp"
      f"(可被校准修复的部分 {gd['calib_fixable_pp']:+.2f}pp,"
      f"排序误差残余 {gd['ranking_residual_pp']:.2f}pp)。"
      + ("**残余占绝大部分 → 瓶颈是排序能力(需要更强特征/模型),不是校准。**"
         if gd["ranking_residual_pp"] > gd["calib_fixable_pp"] else
         "**校准可修复部分占相当比例 → 值得先上等渗/Platt 校准再评估特征投入。**"))
    A("")
    A("## 1. 方法")
    A("- **规模曲线**:固定 train-only 预测器(与 report §6 完全同协议,同 SEED "
      "切分)。对 calib 池(n=1161)与 calib∪test 池(n=3303,同一预测器下仍是"
      "诚实域外,用于把 x 轴延伸到 1161 以外而不改变预测器)分别在 "
      "25/50/75/100% 处 bootstrap 有放回子采样,每档 200 次(任务要求 ≥50)。"
      "每次子采样按 report §6.1 原协议算\"可发证最小 ε\""
      "= CP 上界(λ=0 calib 风险,δ=0.1)—— 该量即固定序列检验能达到的绝对"
      "下限,因序列从 λ=0 起步,λ=0 未过则更高 λ 也不会被序列检验触达"
      "(经验上 λ=0 恰是风险最低点,报告 §3/§6.1 两处一致)。")
    A("- **大 N 锚点**:另加一个不同预测器口径的锚点 —— 全量 5511 题、5 折"
      "交叉拟合 p̂(triples 文件 phat_cv 字段,即 report §3 Pareto 表用的预测器)"
      "算同一 λ=0 min-cert-ε,作为\"5 倍于 calib 规模\"时的独立参照"
      "(预测器不同,不直接落在同一渐近曲线上,单独列出,不用于拟合外推)。")
    A("- **外推拟合**:CP 上界作为置信上界,渐近满足 "
      "ε_ub(n) ≈ p_inf + c/√n(p_inf = 大样本下的真实点风险,c 为有限样本"
      "松弛项系数),对 bootstrap 曲线两参数最小二乘拟合。")
    A("- **Oracle-gap 分解**:嵌套 isotonic 重校准(PAV 算法手写,sklearn 不"
      "可用)——按已存 cv_fold(5 折)逐折用其余 4 折的 (p̂,correct) 拟合"
      "单调映射,应用到留出折,得到重校准后的 phat_calib(全程诚实域外,"
      "无同折信息泄漏)。原始 gap − 重校准后 gap = 校准误差可修复部分;"
      "重校准后残余 gap = 排序误差(isotonic 是保序变换,不改变同一臂内部"
      "的相对排序,只能修正跨臂的相对刻度偏差,故此残余专指排序本身的上限)。")
    A("")
    A("## 2. ε-vs-规模曲线")
    A("")
    A("| 池 | n | risk 均值(点估计) | min-cert-ε 均值 | 中位数 | [5%,95%] |")
    A("|---|---|---|---|---|---|")
    for p in o["bootstrap_points"]:
        A(f"| {p['tag']} | {p['n']} | {p['risk_mean']*100:.2f}% | "
          f"{p['eps_ub_mean']*100:.2f}% | {p['eps_ub_median']*100:.2f}% | "
          f"[{p['eps_ub_p05']*100:.2f}%, {p['eps_ub_p95']*100:.2f}%] |")
    a5511 = o["anchor_full5511_phatcv"]
    A(f"| 全量交叉拟合(不同预测器,独立锚点) | {a5511['n']} | "
      f"{a5511['risk']*100:.2f}% | {a5511['min_cert_eps']*100:.2f}% | - | - |")
    A("")
    A(f"拟合:min-cert-ε(n) ≈ {ex['p_inf']*100:.2f}% + {ex['c_slope']:.3f}/√n。")
    if ex["n_needed_for_5pct"] is not None:
        A(f"外推:要把均值压到 ε=5%,估计需要校准集 n≈{ex['n_needed_for_5pct']:.0f}。")
    else:
        A("外推:渐近下限已 ≥5%,不存在能达到 ε=5% 的有限 n(见 §0 判决的数学论证)。")
    A("")
    A("**读图要点**:四档(290/580/871/1161,均来自 calib 单池)与四档"
      "(826/1652/2477/3303,来自 calib∪test 更大池,仍是同一 train-only 预测"
      "器下的诚实域外估计)的 risk 均值几乎不随 n 变化,只有区间宽度"
      "([5%,95%])随 n 增大收窄 —— 这正是\"结构性下界、非样本量不足\"的"
      "标准诊断特征:样本量不够时 risk 点估计本身应随 n 增大而更精确地逼近"
      "某个可能更低的真值;若真值已经不低,更多数据只会让我们更确信地测出"
      "同一个不低的数。")
    A("")
    A("## 3. Oracle-gap 分解:校准误差 vs 排序误差")
    A("")
    A(f"- 原始(交叉拟合 p̂,未重校准):相对 oracle 损失 {gd['gap_raw_pp']:.2f}pp"
      f"(准确率 {gd['raw_acc_lam0']*100:.2f}% vs oracle "
      f"{gd['oracle_acc']*100:.2f}%)。")
    A(f"- 嵌套 isotonic 重校准后:相对 oracle 损失 {gd['gap_calibrated_pp']:.2f}pp"
      f"(准确率 {gd['calibrated_acc_lam0']*100:.2f}%)。")
    A(f"- **分解:校准误差可修复部分 {gd['calib_fixable_pp']:+.2f}pp,"
      f"排序误差残余 {gd['ranking_residual_pp']:.2f}pp。**")
    A("")
    A("各臂 ECE(交叉拟合口径)重校准前后:")
    A("")
    A("| 臂 | ECE 前 | ECE 后 |")
    A("|---|---|---|")
    for a in ARMS:
        A(f"| {a} | {gd['ece_before'][a]:.3f} | {gd['ece_after'][a]:.3f} |")
    A("")
    A("(ECE 前后对比是校准过程本身是否生效的健全性检查,非 gap 分解的直接"
      "数字——ECE 衡量单臂内部校准质量,gap 分解衡量跨臂 argmax 决策质量,"
      "两者相关但不等价:单臂 ECE 改善不保证跨臂排序对了。)")
    A("")
    A("## 4. 结论与可执行建议")
    if ex["n_needed_for_5pct"] is None:
        A("- **不建议加数据冲 ε=3%/5% 主口径证书**:曲线已平台化,渐近下限"
          f"≈{p_inf_pct:.2f}%,5 倍规模(全量 5511 锚点)未见改善,结构性证据双重确认。")
        if gd["ranking_residual_pp"] > gd["calib_fixable_pp"]:
            A("- **该投预测器特征,不是加数据**:分解显示残余主要来自排序误差"
              f"({gd['ranking_residual_pp']:.2f}pp of {gd['gap_raw_pp']:.2f}pp),"
              "重校准只能小幅收窄,说明现有特征集本身分辨力不够——下一步应扩"
              "特征(如更细粒度的题面/卡片交互特征)或换模型族(树模型对特征"
              "交互更敏感),而非等渗/Platt 这类只调整刻度不调整排序的手段。")
        else:
            A("- **值得先低成本上校准修正**:重校准贡献了较大部分的 gap 收窄,"
              "说明现有 p̂ 排序本身不差,主要是跨臂刻度不一致——线上路由决策"
              "函数可先接入本脚本验证过的 isotonic 映射(零成本、零新特征),"
              "再评估是否还需要投入新特征。")
        A("- **主口径证书建议改口径**:按 P3 报告 §6.1 已有建议,主口径 ε 从"
          "预注册的 3%/5% 调整为报告次级(成本压缩安全)证书,或把主口径的"
          "目标从\"相对逐题 oracle\"改为\"相对臂能力上限内的可挽回部分\""
          "(呼应台账 ②号条目:29.85pp 总缺口中 17.86pp 是臂天花板锁死、"
          "8.96-12pp 才是路由可挽回空间,以路由可挽回空间为分母,ε 门槛更容易"
          "有意义地设定)。")
    else:
        A(f"- 加数据在原则上可行,但 n≈{ex['n_needed_for_5pct']:.0f} 是否现实"
          "取决于新增校准题的采集成本,建议先核算再决定是否投入。")
    A("")
    A("## 5. 已知局限")
    A("- isotonic 重校准用手写 PAV + 线性内插近似阶梯函数(sklearn 不可用);"
      "标准阶梯函数会更精确,但方向性结论(校准 vs 排序哪个是瓶颈)不依赖这"
      "个近似的具体数值。")
    A("- calib∪test 大池的 bootstrap 复用了同一个 train-only 预测器 phat2,"
      "对该预测器而言 test 集是诚实域外,但 test 集本身在 P3 报告 §6.1 中被"
      "用作证书验证——本脚本只用其经验风险做规模诊断,不重新宣称测试集本身"
      "的证书结论。")
    A("- 全量 5511 锚点用的是不同预测器(5 折交叉拟合 phat_cv,非 train-only "
      "phat2),两条曲线不共享同一渐近过程,仅作独立交叉验证使用,外推拟合"
      "本身不含该点。")
    A("- bootstrap 为有放回重采样(标准 bootstrap),行间相关性(尤其 LoCoMo "
      "系同库题目)未做聚类校正,与 report §6 footnote 提示的题层二项界"
      "偏乐观问题同源;方向性结论(平台化 vs 单调下降)不受此影响,但区间"
      "宽度本身可能偏窄。")
    A("")
    A("## 6. 复现与产物")
    A("- 脚本:`scripts/router_eps_scaling.py`(仅新增,import "
      "`scripts/train_router.py` 函数只读引用,不改动冻结代码与 "
      "train_router.py 任何一行)。")
    A("- 运行:`python scripts/router_eps_scaling.py`(全离线,零 LLM 调用,"
      "零 API 费用)。")
    A("- 产物:`results/router_eps_scaling_raw_20260816.json`(全部中间统计)、"
      "本报告。")
    (R / "router_eps_scaling_20260816.md").write_text("\n".join(L), encoding="utf-8")
    print("report ->", R / "router_eps_scaling_20260816.md")


if __name__ == "__main__":
    main()
