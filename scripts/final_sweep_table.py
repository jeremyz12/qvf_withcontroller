# -*- coding: utf-8 -*-
"""冻结版(freeze-20260805)双模型总表:全部配对判决一键生成。"""
import glob
import json
import sys
from math import comb

R = r"D:\ZZL_cluade\results"


def load(pat, mode=None):
    d = {}
    for f in glob.glob(rf"{R}\{pat}"):
        if not f.endswith(".jsonl"):
            continue
        for l in open(f, encoding="utf-8", errors="ignore"):
            s = l.strip()
            if not s:
                continue
            try:
                r = json.loads(s)
            except Exception:
                continue
            if "error" in r:
                continue
            if mode and r.get("mode") != mode:
                continue
            d[r["question_id"]] = r
    return d


def verdict(base, arm, label):
    w = l = t = 0
    for qid, r in arm.items():
        x = base.get(qid)
        if not x:
            continue
        p1 = bool(x.get("judge_correct"))
        p2 = bool(r.get("judge_correct"))
        if p2 and not p1:
            w += 1
        elif p1 and not p2:
            l += 1
        else:
            t += 1
    n = w + l
    p_pos = sum(comb(n, k) for k in range(w, n + 1)) / 2**n if n else 1.0
    p_neg = sum(comb(n, k) for k in range(l, n + 1)) / 2**n if n else 1.0
    tot = w + l + t
    a_acc = sum(bool(r.get("judge_correct")) for r in arm.values()) / max(1, len(arm))
    b_acc = sum(bool(base.get(q, {}).get("judge_correct")) for q in arm if q in base) / max(1, tot)
    if p_pos < 0.05 and w > l:
        sig, p = "✅", p_pos
    elif p_neg < 0.05 and l > w:
        sig, p = "⚠️显著负", p_neg
    else:
        sig, p = "平", min(p_pos, p_neg)
    print(f"| {label} | {b_acc:.1%} → {a_acc:.1%} | QVF{'多' if w>=l else '少'}胜{abs(w-l)}题({w}胜{l}负, p={p:.2g}) | {sig} |")


print("| 基准×栈 | 直读 → +QVF | 配对判决(差值) | 显著 |")
print("|---|---|---|---|")
# STALE-400
verdict(load("full400_h45_*.jsonl", "dense_direct"), load("final_h45_*.jsonl"), "STALE-400 · haiku (1200)")
verdict(load("full400_gpt5m_*.jsonl", "dense_direct"), load("final_gpt_*.jsonl"), "STALE-400 · gpt (1200)")
# Chain
verdict(load("chainfull_s*.jsonl", "dense_direct"), load("final_chain_h45.jsonl"), "STALE-Chain · haiku (212)")
verdict(load("final_chain_gpt_direct.jsonl"), load("final_chain_gpt_species2.jsonl"), "STALE-Chain · gpt (212)")
# TempReason clean/raw
verdict(load("tempr_n200_direct.jsonl"), load("final_trc_h45.jsonl"), "TempReason干净 · haiku (200)")
verdict(load("final_trc_gpt_direct.jsonl"), load("final_trc_gpt_species2.jsonl"), "TempReason干净 · gpt (200)")
verdict(load("temprraw_n200_direct.jsonl"), load("final_trr_h45.jsonl"), "TempReason原文 · haiku (200)")
verdict(load("final_trr_gpt_direct.jsonl"), load("final_trr_gpt_species2.jsonl"), "TempReason原文 · gpt (200)")
# HoH
verdict(load("hoh_n200_direct.jsonl"), load("final_hoh_h45.jsonl"), "HoH · haiku (200)")
verdict(load("final_hoh_gpt_direct.jsonl"), load("final_hoh_gpt_species2.jsonl"), "HoH · gpt (200)")
# MC
verdict(load("mc_fresh_direct.jsonl", "dense_direct"), load("final_mc_h45.jsonl"), "MemConflict · haiku (150)")
verdict(load("final_mc_gpt_direct.jsonl"), load("final_mc_gpt_species2.jsonl"), "MemConflict · gpt (150)")
# LME (s_cleaned 完整版)
verdict(load("tr_full133.jsonl", "dense_direct"), load("final2_lmet_h45.jsonl"), "LME时间推理 · haiku (133)")
verdict(load("final2_lmet_gpt_direct.jsonl"), load("final2_lmet_gpt_species2.jsonl"), "LME时间推理 · gpt (133)")
verdict(load("final2_lmek_h45.jsonl", "dense_direct"), load("final2_lmek_h45.jsonl", "minimal_rules_species2"), "LME知识更新 · haiku (78)")
verdict(load("final2_lmek_gpt.jsonl", "dense_direct"), load("final2_lmek_gpt.jsonl", "minimal_rules_species2"), "LME知识更新 · gpt (78)")
# LoCoMo(注意:direct 臂必须来自与 final 相同的抽样池 — final_lc*_h45_direct)
verdict(load("final_lca_h45_direct.jsonl"), load("final_lca_h45.jsonl"), "LoCoMo对抗 · haiku (50)")
verdict(load("final_lca_gpt_direct.jsonl"), load("final_lca_gpt_abstain.jsonl"), "LoCoMo对抗 · gpt (50)")
verdict(load("final_lcs_h45_direct.jsonl"), load("final_lcs_h45.jsonl"), "LoCoMo单跳 · haiku (50)")
verdict(load("final_lcs_gpt_direct.jsonl"), load("final_lcs_gpt_abstain.jsonl"), "LoCoMo单跳 · gpt (50)")
