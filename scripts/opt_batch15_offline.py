# -*- coding: utf-8 -*-
"""批 15 离线组合:题型路由(R1,交叉拟合)与 change_count 一致性门控(R2)。
预注册 results/opt_batch15_prereg.md(先于本脚本运行提交)。零新增 API。
用法: python scripts/opt_batch15_offline.py
"""
import json
import hashlib
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")


def load(p):
    return [json.loads(l) for l in open(ROOT / p, encoding="utf-8")]


def mcnemar(pairs):
    """pairs: list of (a_correct, b_correct). Returns (b, c, p) 双侧精确."""
    b = sum(1 for x, y in pairs if x and not y)   # A 对 B 错
    c = sum(1 for x, y in pairs if not x and y)   # A 错 B 对
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(k + 1)) / 2 ** n * 2
    return b, c, min(1.0, p)


smoc = {r["question_id"]: r for r in load("results/wsc_v2_smoc.jsonl")}
compile_ = {r["question_id"]: r for r in load("results/wsc_v2_compile.jsonl")}
mf = {r["question_id"]: r for r in load("results/wsc_v2_countfam_mf.jsonl")}
rep = json.load(open(ROOT / "results/mf_v42_report.json", encoding="utf-8"))
removed = {row["uid"]: row["removed"] for row in rep["rows"]}

assert set(smoc) == set(compile_) and len(smoc) == 576
assert set(mf) <= set(compile_) and len(mf) == 288

# 修复编译臂拼装(批 12 口径):计数族行换过滤店产物
repaired = {qid: (mf[qid] if qid in mf else compile_[qid]) for qid in compile_}
n_smoc = sum(1 for r in smoc.values() if r["judge_correct"])
n_rep = sum(1 for r in repaired.values() if r["judge_correct"])
print(f"[断言核] smoc {n_smoc}/576 = {n_smoc/5.76:.2f} | repaired-compile "
      f"{n_rep}/576 = {n_rep/5.76:.2f}")
assert n_smoc == 476, f"smoc 存档总分变了: {n_smoc}"
assert n_rep == 454, f"修复编译拼装总分 != 454: {n_rep}"

qids = sorted(smoc)
qtype = {q: smoc[q]["question_type"] for q in qids}
uid_of = {q: smoc[q]["uid"] for q in qids}
uids = sorted({uid_of[q] for q in qids})

# ── R1 题型路由(交叉拟合) ─────────────────────────────
half = {u: int(hashlib.sha256(u.encode()).hexdigest(), 16) % 2 for u in uids}
print(f"\n[R1] uid 折分: half0={sum(1 for u in uids if half[u]==0)} 库, "
      f"half1={sum(1 for u in uids if half[u]==1)} 库")


def acc_by_type(rows_by_qid, qs):
    ok = defaultdict(int)
    n = defaultdict(int)
    for q in qs:
        t = qtype[q]
        n[t] += 1
        ok[t] += bool(rows_by_qid[q]["judge_correct"])
    return {t: ok[t] / n[t] for t in n}


rule = {}          # (train_half, qtype) -> 'smoc'|'repaired'
for h in (0, 1):
    train = [q for q in qids if half[uid_of[q]] == h]
    a_s = acc_by_type(smoc, train)
    a_r = acc_by_type(repaired, train)
    for t in a_s:
        rule[(h, t)] = "repaired" if a_r[t] > a_s[t] else "smoc"
print("[R1] 折内规则(应用到对折):")
for (h, t), arm in sorted(rule.items()):
    print(f"    train-half{h} {t}: {arm}")

routed = {}
route_arm = {}
for q in qids:
    h_apply = 1 - half[uid_of[q]]          # 规则来自对折
    arm = rule[(h_apply, qtype[q])]
    route_arm[q] = arm
    routed[q] = (smoc if arm == "smoc" else repaired)[q]

n_routed = sum(1 for q in qids if routed[q]["judge_correct"])
b, c, p = mcnemar([(bool(smoc[q]["judge_correct"]),
                    bool(routed[q]["judge_correct"])) for q in qids])
print(f"[R1] 交叉拟合路由: {n_routed}/576 = {n_routed/5.76:.2f} "
      f"(smoc 82.64) | McNemar smoc对/路由错 b={b}, smoc错/路由对 c={c}, p={p:.4f}")
print(f"[R1] 判据: acc>=84.14 且 p<0.05 -> "
      f"{'过' if n_routed/5.76 >= 84.14 and p < 0.05 else '不过'}")

# 参考:全集内定规则上界(不作判据)
a_s_full = acc_by_type(smoc, qids)
a_r_full = acc_by_type(repaired, qids)
ub = 0
for q in qids:
    arm = "repaired" if a_r_full[qtype[q]] > a_s_full[qtype[q]] else "smoc"
    ub += bool((smoc if arm == "smoc" else repaired)[q]["judge_correct"])
print(f"[R1·参考] 全集内定规则上界: {ub}/576 = {ub/5.76:.2f}")
print("[R1·附表] 分题型存档准确率 smoc vs repaired:")
for t in sorted(a_s_full):
    print(f"    {t}: {a_s_full[t]*100:.1f} vs {a_r_full[t]*100:.1f}")

# ── R2 change_count 一致性门控 ─────────────────────────
cc = [q for q in qids if qtype[q] == "change_count"]
assert len(cc) == 144
gated = {}
side = {}
for q in cc:
    dirty = removed.get(uid_of[q], 0) > 0
    side[q] = "smoc(剔过卡)" if dirty else "executor(净链)"
    gated[q] = smoc[q] if dirty else mf[q]
n_g = sum(1 for q in cc if gated[q]["judge_correct"])
n_s = sum(1 for q in cc if smoc[q]["judge_correct"])
n_e = sum(1 for q in cc if mf[q]["judge_correct"])
b2, c2, p2 = mcnemar([(bool(smoc[q]["judge_correct"]),
                       bool(gated[q]["judge_correct"])) for q in cc])
print(f"\n[R2] change_count 144 题: smoc {n_s} ({n_s/1.44:.1f}) | "
      f"executor(mf) {n_e} ({n_e/1.44:.1f}) | 门控 {n_g} ({n_g/1.44:.1f})")
print(f"[R2] McNemar vs smoc: b={b2}, c={c2}, p={p2:.4f}")
print(f"[R2] 判据: 门控 acc >= 78.4 -> {'过' if n_g/1.44 >= 78.4 else '不过'}")
clean = [q for q in cc if removed.get(uid_of[q], 0) == 0]
dirty = [q for q in cc if removed.get(uid_of[q], 0) > 0]
for name, grp in (("净链库", clean), ("剔过卡库", dirty)):
    es = sum(1 for q in grp if mf[q]["judge_correct"])
    ss = sum(1 for q in grp if smoc[q]["judge_correct"])
    print(f"[R2·机制] {name} n={len(grp)}: executor {es}/{len(grp)} "
          f"({es/max(1,len(grp))*100:.1f}) vs smoc {ss}/{len(grp)} "
          f"({ss/max(1,len(grp))*100:.1f})")
