# -*- coding: utf-8 -*-
"""评审一致性汇总(2026-09-03):真人(rate.db 导出)× 机器复核各版本。
输入:results/rater_answers_20260903.json(rater/item/verdict)、
      results/machine_review_149.jsonl(单遍 haiku)、results/machine_review_149_opus5_s*.jsonl(单遍 opus5)、
      results/sim_senior1_reviews.json(多段 Opus 模拟 senior1,85 题)。
输出:每个机器版本的报错率、对照题召回、与 senior2 的三值一致率 / Cohen's κ(三值与二值)、混淆矩阵。
"""
import glob, json
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def kappa(pairs, labels):
    n = len(pairs)
    if not n: return float("nan"), float("nan")
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[l] / n * cb[l] / n for l in labels)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def binar(v):  # errors vs not-errors
    return "errors" if v == "errors" else "other"


def main():
    rows = json.load(open(ROOT / "results/rater_answers_20260903.json", encoding="utf-8"))
    human = {}
    for r in rows:
        human.setdefault(r["rater"], {})[r["item"]] = r["verdict"]
    cmap = json.loads((ROOT / "data/labelstudio_chainproj_map.json").read_text(encoding="utf-8"))
    catch = {k for k, v in cmap.items() if v.get("catch")}
    machines = {}
    machines["单遍 haiku-4.5"] = {json.loads(l)["item"]: json.loads(l) for l in open(ROOT / "results/machine_review_149.jsonl", encoding="utf-8")}
    op = {}
    for f in glob.glob(str(ROOT / "results/machine_review_149_opus5_s*.jsonl")):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l); op.setdefault(r["item"], r)
    if op: machines["单遍 opus-5"] = op
    so = {}
    for f in glob.glob(str(ROOT / "results/machine_review_149_sonnet5_s*.jsonl")):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l); so.setdefault(r["item"], r)
    if so: machines["单遍 sonnet-5"] = so
    sim = {r["item"]: r for r in json.load(open(ROOT / "results/sim_senior1_reviews.json", encoding="utf-8"))}
    machines["多段 Opus 模拟 senior1(85 题)"] = sim
    s2 = human.get("senior2", {})
    print(f"真人 senior2:n={len(s2)} {Counter(s2.values())} | author:n={len(human.get('author', {}))} {Counter(human.get('author', {}).values())}")
    print("| 机器版本 | n | 报错率 | 对照题召回 | 与 senior2 重叠 n | 三值一致 | κ(三值) | κ(errors 二值) | 混淆(机器行 × senior2 列:errors/other) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, m in machines.items():
        n = len(m); err = sum(1 for r in m.values() if r["verdict"] == "errors")
        cr = [it for it in catch if it in m]; crec = sum(1 for it in cr if m[it]["verdict"] == "errors")
        ov = [it for it in m if it in s2]
        pairs3 = [(m[it]["verdict"], s2[it]) for it in ov]
        po3, k3 = kappa(pairs3, ["correct", "errors", "unsure"])
        pairs2 = [(binar(a), binar(b)) for a, b in pairs3]
        _, k2 = kappa(pairs2, ["errors", "other"])
        cm = Counter(pairs2)
        conf = f"EE {cm[('errors','errors')]} / EO {cm[('errors','other')]} / OE {cm[('other','errors')]} / OO {cm[('other','other')]}"
        print(f"| {name} | {n} | {err/n*100:.1f}%({err}) | {crec}/{len(cr)} | {len(ov)} | {po3*100:.1f}% | {k3:.3f} | {k2:.3f} | {conf} |")
    # 机器之间:单遍 opus5 vs 多段模拟(85 题)
    if op:
        ov = [it for it in sim if it in op]
        po, k = kappa([(op[it]["verdict"], sim[it]["verdict"]) for it in ov], ["correct", "errors", "unsure"])
        print(f"\n单遍 opus-5 vs 多段模拟 senior1:n={len(ov)} 一致 {po*100:.1f}% κ={k:.3f}")
        # 对照题明细
        print("对照题(植入错误)opus-5 判定:", {it: op[it]["verdict"] for it in sorted(catch) if it in op})
        # senior2 判 errors 的 7 题,opus-5 怎么判
        print("senior2 判 errors 的题,opus-5 判定:", {it: op[it]["verdict"] for it, v in s2.items() if v == "errors" and it in op})


if __name__ == "__main__":
    main()
