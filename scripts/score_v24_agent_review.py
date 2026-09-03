# -*- coding: utf-8 -*-
"""v2.4 全量评审(opus5-agent-v24 槽位)汇总:从 rate.db 导出(results/rater_answers_v24_*.json)
× 答案键 data/v24full_keymap.json → 判定分布、对照题召回、非对照题报错率(Wilson CI)、报错明细。
用法:先用 ssh 导出 answers 到 results/rater_answers_v24_20260903.json,再运行本脚本。
"""
import json, math, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
TOKENS = {"v24PjfPXLtZijW6R": "opus5-agent-v24", "v24BwLwRrXg9m78V": "reviewerA-v24",
          "v25kNtm27hkW2dcA": "opus5-agent-v25", "v25BTzCpYPPPYrqC": "reviewer-v25"}
KEYMAP = {"v24": "data/v24full_keymap.json", "v25": "data/v25full_keymap.json"}


def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main():
    src = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "results/rater_answers_v24_20260903.json")
    rows = json.load(open(src, encoding="utf-8"))
    out = []
    for tok, name in TOKENS.items():
        ans = {r["item"]: r for r in rows if r["rater"] == tok}
        if not ans: continue
        key = json.load(open(ROOT / KEYMAP[tok[:3]], encoding="utf-8"))
        vc = Counter(r["verdict"] for r in ans.values())
        catch = [i for i in ans if key.get(i, {}).get("catch")]
        crec = sum(1 for i in catch if ans[i]["verdict"] == "errors")
        non = [i for i in ans if not key.get(i, {}).get("catch")]
        flags = [i for i in non if ans[i]["verdict"] == "errors"]
        uns = [i for i in non if ans[i]["verdict"] == "unsure"]
        lo, hi = wilson(len(flags), len(non))
        ms = sorted(r["ms"] for r in ans.values() if r.get("ms"))
        med = ms[len(ms) // 2] / 1000 if ms else float("nan")
        out.append(f"## {name}(token …{tok[-4:]})\n\n"
                   f"- 已答 {len(ans)}/149;判定 {dict(vc)};中位 {med:.0f} 秒/题\n"
                   f"- 对照题召回 {crec}/{len(catch)}:" + ", ".join(f"{i}={ans[i]['verdict']}({key[i]['injection'].split(':')[0]})" for i in sorted(catch)) + "\n"
                   f"- 非对照题 {len(non)}:报错 {len(flags)}({len(flags)/max(1,len(non))*100:.1f}%,Wilson 95% [{lo*100:.1f}, {hi*100:.1f}]),不确定 {len(uns)}\n")
        if flags or uns:
            out.append("| 题 | uid | 判定 | 备注 |\n|---|---|---|---|")
            for i in flags + uns:
                out.append(f"| {i} | {key[i]['uid']} | {ans[i]['verdict']} | {(ans[i]['note'] or '')[:200]} |")
        out.append("")
    ver = "v2.5" if any(r["rater"].startswith("v25") for r in rows) else "v2.4"
    doc = f"# {ver} 全量评审汇总(2026-09-03)\n\n语料 {ver},149 题 = 144 链 + 5 植入对照题;数据源 rate.db 导出。\n\n" + "\n".join(out)
    (ROOT / (sys.argv[2] if len(sys.argv) > 2 else "results/v24_agent_review_20260903.md")).write_text(doc, encoding="utf-8")
    print(doc)


if __name__ == "__main__":
    main()
