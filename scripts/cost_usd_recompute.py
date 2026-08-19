# -*- coding: utf-8 -*-
"""scripts/cost_usd_recompute.py — 成本叙事的美元口径重算($0,纯归档复算)。

来源:持续优化循环 rank-5(首轮攻击面审计)。攻击:token 面值对比掩盖了
(a) 输出 token 5× 价差(建卡摊销含 772,858 输出 tok);
(b) 整库静态前缀可挂提示词缓存(读价 0.1×,写价 1.25×);
(c) 摊销依赖每库题数,只报了有利档位。

价格口径(项目既用,scripts/build_tag_lattice.py):haiku-4-5 输入 $1.00/M、
输出 $5.00/M;缓存写 1.25×、缓存读 0.10×(Anthropic 标准)。
建卡总量(study_logs/REVIEW_HANDOFF_20260819.md:165):in 2,279,776 / out 772,858,
S5 共 105 库 / 418 题。
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P_IN, P_OUT = 1.00, 5.00          # $/M tok
CACHE_W, CACHE_R = 1.25, 0.10     # 输入价倍率

ARMS = [
    ("稠密检索直读 top-10", "results/wsc_direct_s5_all_b1_union.jsonl"),
    ("+陈旧感知提示词",     "results/wsc_warned_s5_all_b1.jsonl"),
    ("更深检索 top-24",     "results/wsc_s5_direct_k24.jsonl"),
    ("更深检索 top-40",     "results/wsc_s5_direct_k40.jsonl"),
    ("整库上下文",          "results/wsc_s5_fullctx.jsonl"),
    ("QVF filter-only",     "results/wsc_s5_filter_only.jsonl"),
    ("QVF usability",       "results/wsc_s5_usability.jsonl"),
    ("QVF 编译臂",          "results/wsc_s5_test_v42b1_union.jsonl"),
]

BUILD_IN, BUILD_OUT = 2_279_776, 772_858
N_STORES, N_Q = 105, 418


def usd(i, o):
    return i / 1e6 * P_IN + o / 1e6 * P_OUT


def main() -> int:
    out = ["# 成本美元账本(2026-08-20,$0 归档复算)", "",
           f"价格:输入 ${P_IN}/M、输出 ${P_OUT}/M;缓存写 {CACHE_W}×、读 {CACHE_R}×(输入价)。",
           "", "## 读端逐题(418 题均值,输入/输出分列)", "",
           "| 臂 | in tok | out tok | 读端 $/题 |", "|---|---|---|---|"]
    stats = {}
    for name, p in ARMS:
        rows = [json.loads(l) for l in open(ROOT / p, encoding="utf-8")]
        mi = st.mean(r.get("usage_input_tokens", 0) for r in rows)
        mo = st.mean(r.get("usage_output_tokens", 0) for r in rows)
        stats[name] = (mi, mo)
        out.append(f"| {name} | {mi:,.0f} | {mo:,.0f} | ${usd(mi, mo):.5f} |")

    # QVF 全口径:读端 + 建卡摊销(美元)
    build_usd = usd(BUILD_IN, BUILD_OUT)
    qvf_in, qvf_out = stats["QVF 编译臂"]
    qvf_read = usd(qvf_in, qvf_out)
    out += ["", "## 写入侧(建卡,一次性)", "",
            f"- token:in {BUILD_IN:,} / out {BUILD_OUT:,}(共 {N_STORES} 库 / {N_Q} 题)",
            f"- **美元:${build_usd:.3f}**(其中输出占 ${BUILD_OUT/1e6*P_OUT:.3f},"
            f"= {BUILD_OUT/1e6*P_OUT/build_usd*100:.0f}%——token 面值口径掩盖的 5× 价差)",
            f"- 每库 ${build_usd/N_STORES:.4f};S5 实测密度(≈4 题/库)下摊销 ${build_usd/N_Q:.5f}/题",
            "", "## 摊销敏感性(QVF 全口径 $/题 = 读端 + 建卡/每库题数)", "",
            "| 每库题数 | 建卡摊销 $/题 | QVF 全口径 $/题 |", "|---|---|---|"]
    for q in (1, 4, 20):
        am = build_usd / N_STORES / q
        out.append(f"| {q} | ${am:.5f} | ${qvf_read + am:.5f} |")

    # 整库臂:无缓存 vs 缓存
    fc_in, fc_out = stats["整库上下文"]
    fc_plain = usd(fc_in, fc_out)
    out += ["", "## 整库臂的缓存修正(静态库前缀可挂 prompt cache)", "",
            "| 每库题数 | 有效输入倍率 (1.25+0.1(q−1))/q | 整库 $/题 |", "|---|---|---|"]
    fc_cached = {}
    for q in (1, 4, 20):
        mult = (CACHE_W + CACHE_R * (q - 1)) / q
        c = fc_in / 1e6 * P_IN * mult + fc_out / 1e6 * P_OUT
        fc_cached[q] = c
        out.append(f"| {q} | {mult:.3f} | ${c:.5f} |")
    out += ["", f"(无缓存整库:${fc_plain:.5f}/题;QVF 读端:${qvf_read:.5f}/题)", ""]

    # 判定
    q4_qvf = qvf_read + build_usd / N_STORES / 4
    out += ["## 判定(如实入档)", "",
            f"1. **token 面值口径的\"全成本 9,372 仍低于整库 14,780\"在美元口径下不成立需分档说**:",
            f"   4 题/库(S5 实测)QVF 全口径 ${q4_qvf:.5f}/题 vs 整库无缓存 ${fc_plain:.5f}/题 "
            f"—— QVF {'更便宜' if q4_qvf < fc_plain else '更贵'};"
            f"vs 整库缓存后 ${fc_cached[4]:.5f}/题 —— QVF "
            f"{'更便宜' if q4_qvf < fc_cached[4] else f'更贵({q4_qvf/fc_cached[4]:.1f}×)'}。",
            f"2. 1 题/库时 QVF 全口径 ${qvf_read + build_usd/N_STORES:.5f}/题,写入侧独占主导——低频库不划算,必须如实报。",
            f"3. 20 题/库时 QVF ${qvf_read + build_usd/N_STORES/20:.5f} vs 整库缓存 ${fc_cached[20]:.5f}:摊薄后差距缩小。",
            "4. 结论措辞:成本主张只能说 **\"同读端预算下准确率 +33pp\"** 与 **\"美元成本随库复用摊薄\"**;",
            "   \"全成本仍低于整库\"的 token 面值句撤回,改为本账本三档表述。",
            "   (准确率维度不受影响:整库无论缓存与否都是 50.5%,QVF 83.7%。)", ""]
    dst = ROOT / "results/cost_usd_ledger.md"
    dst.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
