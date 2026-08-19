# -*- coding: utf-8 -*-
"""scripts/family_error_control.py — 全族统计检验的 Holm / BH-FDR 重算。

来源:持续优化循环 rank-3(2026-08-20)。输入:统计检验收集 workflow 的结构化输出
(每条含 检验名/文件行号/统计量原文/p 值原文/支撑主张/原文是否当显著)。

口径规则(写死,先于计算):
1. 族 = 所有以 p 值支撑主张的假设检验(McNemar/binomial/χ²/聚类稳健)。
   - 同一检验多处报告只入族一次(收集侧已去重);
   - 同时报朴素与聚类稳健 p 的,取聚类稳健(更保守且是正确口径);
   - "p<X" 形式取上界 X(对显著性主张方向保守);
   - 只有 CI 无 p 的、以及 LTT 证书(自带 δ 风险控制)不入 α 族,附录列出。
2. 校正:Holm(FWER)与 Benjamini-Hochberg(FDR),α=q=0.05,双口径同时报。
3. 判定只针对"原文当作显著"的条目:校正后仍显著 → 保留;失显 → 降级为方向性观察。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(r"C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade"
           r"\2b238d36-0e89-4591-ac1c-f5ffd6578795\tasks\w450kc47v.output")

P_NUM = re.compile(r"p\s*[=<]\s*([0-9.]+(?:e[+-]?\d+)?)", re.I)
P_CLUSTER = re.compile(r"聚类稳健\s*p\s*[=<]\s*([0-9.]+(?:e[+-]?\d+)?)", re.I)
CHI2 = re.compile(r"(?:χ²|chi2)\s*[=≈]\s*([0-9.]+)", re.I)


def chi2_sf_1df(x: float) -> float:
    import math
    return math.erfc(math.sqrt(x / 2.0))


def pick_p(txt: str, stat: str = ""):
    """按口径规则提取单一 p 值;返回 (p, 备注) 或 (None, 原因)。

    "p<X" 记为上界会在大族校正里对自己不公平:凡统计量原文带 χ²(McNemar 1df)
    的,恢复精确 p = sf(χ², 1);无统计量的仍取上界 X(保守)。
    """
    t = txt.replace("&gt;", ">").replace("&lt;", "<")
    if "LTT" in t or "拒绝" in t:      # LTT 固定序列检验自带控制,另列
        return None, "LTT(自带 δ 控制)"
    m = P_CLUSTER.search(t)
    if m:
        return float(m.group(1)), "聚类稳健"
    ms = P_NUM.findall(t)
    if ms:
        if "<" in t:
            c = CHI2.search((stat or "") + " " + t)
            if c:
                return chi2_sf_1df(float(c.group(1))), f"精确(χ²={c.group(1)},1df)"
            return float(ms[0]), "上界"
        return float(ms[0]), "点值"
    if "CI" in t or "无 p" in t:
        return None, "仅 CI"
    return None, "无法解析"


def holm(items):
    """items: [(idx, p)] → set(idx 通过)。"""
    order = sorted(items, key=lambda x: x[1])
    m = len(order)
    passed, stop = set(), False
    for i, (idx, p) in enumerate(order):
        if stop or p > 0.05 / (m - i):
            stop = True
            continue
        passed.add(idx)
    return passed


def bh(items, q=0.05):
    order = sorted(items, key=lambda x: x[1])
    m = len(order)
    k = 0
    for i, (_, p) in enumerate(order, 1):
        if p <= q * i / m:
            k = i
    return {idx for idx, _ in order[:k]}


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))["result"]
    tests = data["results_tests"] + data["logs_tests"]
    # 去重(收集器间可能重叠):按 (文件, 检验名前 30 字)
    seen, uniq = set(), []
    for t in tests:
        k = (t["file"].split(":")[0], t["name"][:30])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)

    family, aside = [], []
    for i, t in enumerate(uniq):
        p, note = pick_p(t.get("p_reported") or "", t.get("stat") or "")
        if p is not None:
            family.append((i, p, note, t))
        else:
            aside.append((note, t))

    idx_p = [(i, p) for i, p, _, _ in family]
    h_pass, b_pass = holm(idx_p), bh(idx_p)

    out = ["# 全族统计检验错误控制重算(2026-08-20,$0)", "",
           f"收集条目 {len(tests)},去重后 {len(uniq)};入 α 族 {len(family)}"
           f"(Holm/BH 双口径,α=q=0.05);LTT/仅CI 另列 {len(aside)}。",
           "口径规则见 scripts/family_error_control.py 文件头(先于计算写死)。", "",
           "## α 族总表(按 p 升序)", "",
           "| # | 检验 | p(口径) | 原文显著? | Holm | BH-FDR | 校正后判定 |",
           "|---|---|---|---|---|---|---|"]
    demoted, kept = [], []
    for rank, (i, p, note, t) in enumerate(sorted(family, key=lambda x: x[1]), 1):
        hp, bp = i in h_pass, i in b_pass
        claimed = t.get("sig_claimed")
        if claimed and not bp:
            verdict = "❌ 降级(FDR 失显)"
            demoted.append((t, p))
        elif claimed and not hp:
            verdict = "⚠️ FWER 失显,FDR 存活"
            kept.append((t, p, "fdr_only"))
        elif claimed:
            verdict = "✅ 双口径存活"
            kept.append((t, p, "both"))
        else:
            verdict = "(原文即不显著)"
        nm = t["name"][:46]
        out.append(f"| {rank} | {nm}({t['file'].split('/')[-1].split(':')[0][:28]}) "
                   f"| {p:.3g}({note}) | {'是' if claimed else '否'} "
                   f"| {'✅' if hp else '❌'} | {'✅' if bp else '❌'} | {verdict} |")

    out += ["", "## 判定汇总", "",
            f"- 原文当显著且**双口径存活**:{sum(1 for _, _, m in kept if m == 'both')} 条",
            f"- 原文当显著且 **Holm 失显、FDR 存活**:{sum(1 for _, _, m in kept if m == 'fdr_only')} 条"
            "(论文中引用须注明按 FDR 口径)",
            f"- 原文当显著但 **FDR 亦失显 → 降级为方向性观察**:{len(demoted)} 条", ""]
    if demoted:
        out += ["### 必须降级的条目", ""]
        for t, p in demoted:
            out.append(f"- **{t['name']}**(p={p:.3g},{t['file']})——主张:{t['claim'][:80]}")
        out.append("")
    out += ["## 附录:不入 α 族的条目(LTT 自带控制 / 仅 CI)", ""]
    for note, t in aside:
        out.append(f"- [{note}] {t['name']}({t['file']})")
    out.append("")

    dst = ROOT / "results/family_error_control_20260820.md"
    dst.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:12]))
    print(f"...\n入族 {len(family)},Holm 通过 {len(h_pass)},BH 通过 {len(b_pass)},"
          f"降级 {len(demoted)}。写入 {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
