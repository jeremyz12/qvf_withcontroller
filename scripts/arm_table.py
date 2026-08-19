# -*- coding: utf-8 -*-
"""scripts/arm_table.py — 直读 / 提示词 / QVF 的准确率·token·延迟三项对照表。

零 LLM、零成本:只读归档的逐题多臂产物(每条臂带 correct / tok / lat)。

**同分母纪律**:每卷只在"三条臂都跑过"的题上比较(交集口径),并单独报出该卷
三臂各自的原始覆盖数。按各臂自己的可用子集报分会让覆盖率低的臂占便宜——
本仓库实测过一次:某常数臂按自己子集读 72.56%,计入回落后实为 67.88%。

**QVF 一列是整合系统(四臂路由)的实际分派结果**,不是"最好的那条臂"。
理由见项目纪律:报成绩必须绑定臂名,默认报生产分派下的加权值。
`wt` 臂另列为消融,不参与主对照。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = "results/router_learned_triples_20260814.jsonl"


def has(t: dict, a: str) -> bool:
    return a in t["arms"] and t["arms"][a].get("correct") is not None


def agg(rows: List[dict], a: str) -> Dict[str, float]:
    if not rows:
        return {"n": 0, "acc": float("nan"), "tok": float("nan"), "lat": float("nan")}
    n = len(rows)
    return {"n": n,
            "acc": sum(bool(t["arms"][a]["correct"]) for t in rows) / n * 100,
            "tok": sum(float(t["arms"][a]["tok"]) for t in rows) / n,
            "lat": sum(float(t["arms"][a].get("lat") or 0) for t in rows) / n}


def qvf(rows: List[dict]) -> Dict[str, float]:
    """整合系统:准确率/成本取路由归档值,延迟取被选中那条臂的实测延迟。"""
    n = len(rows)
    lat = 0.0
    for t in rows:
        p = t.get("v42_pick")
        lat += float((t["arms"].get(p) or {}).get("lat") or 0) if p else 0.0
    return {"n": n,
            "acc": sum(bool(t["v42_correct"]) for t in rows) / n * 100,
            "tok": sum(float(t["v42_tok"]) for t in rows) / n,
            "lat": lat / n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triples", default=DEFAULT)
    ap.add_argument("--emit", default=None)
    a = ap.parse_args()
    tri = [json.loads(l) for l in open(ROOT / a.triples, encoding="utf-8") if l.strip()]
    benches = sorted({t["bench"] for t in tri})

    out = []
    print(f"{'卷':16s} {'n(交集)':>8s} | {'直读':^22s} | {'提示词':^22s} | "
          f"{'QVF(整合路由)':^22s} | 覆盖")
    print(f"{'':16s} {'':>8s} | {'acc':>6s} {'tok':>7s} {'lat':>6s} | "
          f"{'acc':>6s} {'tok':>7s} {'lat':>6s} | {'acc':>6s} {'tok':>7s} {'lat':>6s} |")
    print("-" * 116)
    for b in benches:
        s = [t for t in tri if t["bench"] == b]
        inter = [t for t in s if all(has(t, x) for x in ("direct", "prompt", "wt"))]
        cov = {x: sum(1 for t in s if has(t, x)) for x in ("direct", "prompt", "wt")}
        d, p, q = agg(inter, "direct"), agg(inter, "prompt"), qvf(inter) if inter else None
        w = agg(inter, "wt")
        note = "" if len(inter) == len(s) else f"缺 {len(s) - len(inter)}"
        if not inter:
            print(f"  {b:16s} {'0':>8s} | 三臂无交集,该卷无法比较 "
                  f"(direct {cov['direct']} / prompt {cov['prompt']} / wt {cov['wt']} / 全 {len(s)})")
            out.append({"bench": b, "n_inter": 0, "n_all": len(s), "cov": cov})
            continue
        print(f"  {b:16s} {len(inter):8d} | {d['acc']:5.1f}% {d['tok']:7.0f} {d['lat']:5.1f}s | "
              f"{p['acc']:5.1f}% {p['tok']:7.0f} {p['lat']:5.1f}s | "
              f"{q['acc']:5.1f}% {q['tok']:7.0f} {q['lat']:5.1f}s | {note}")
        out.append({"bench": b, "n_inter": len(inter), "n_all": len(s), "cov": cov,
                    "direct": d, "prompt": p, "wt": w, "qvf": q})

    inter_all = [t for t in tri if all(has(t, x) for x in ("direct", "prompt", "wt"))]
    d, p, q, w = (agg(inter_all, "direct"), agg(inter_all, "prompt"),
                  qvf(inter_all), agg(inter_all, "wt"))
    print("-" * 116)
    print(f"  {'合计(三臂交集)':14s} {len(inter_all):8d} | "
          f"{d['acc']:5.1f}% {d['tok']:7.0f} {d['lat']:5.1f}s | "
          f"{p['acc']:5.1f}% {p['tok']:7.0f} {p['lat']:5.1f}s | "
          f"{q['acc']:5.1f}% {q['tok']:7.0f} {q['lat']:5.1f}s |")
    print(f"\n  消融(不入主表):wt 臂在同一交集上 "
          f"acc {w['acc']:.1f}%  tok {w['tok']:.0f}  lat {w['lat']:.1f}s")
    print(f"  相对直读:QVF acc {q['acc'] - d['acc']:+.2f}pp / "
          f"token {q['tok'] / d['tok']:.2f}x / 延迟 {q['lat'] / d['lat']:.2f}x")
    print(f"  相对提示词:QVF acc {q['acc'] - p['acc']:+.2f}pp / "
          f"token {q['tok'] / p['tok']:.2f}x / 延迟 {q['lat'] / p['lat']:.2f}x")
    print(f"\n  ⚠️ 全量 {len(tri)} 行里只有 {len(inter_all)} 行三臂齐全;"
          f"被排除的 {len(tri) - len(inter_all)} 行集中在 LoCoMo/LoCoMo-full(缺提示词)"
          f"与 STALE-full(缺 wt),**合计行不代表全卷**。")
    if a.emit:
        (ROOT / a.emit).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"  产物 -> {a.emit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
