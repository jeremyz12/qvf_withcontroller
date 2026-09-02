# -*- coding: utf-8 -*-
"""批 33-K 汇总器:逐臂 acc / token / $每题 / 延迟,以及与 haiku 行的对照。

只读 results/b33k_*.jsonl,不写任何归档文件。

单价(2026-09-02 官方价,promo 期):
  gemini-3.6-flash  $0.75 /M 输入,$3.75 /M 输出(2026-12-31 前;2027-01-01 起 $1.50/$7.50)
  claude-opus-5(判官)$5 /M 输入,$25 /M 输出(项目冻结口径)

用法:
  PYTHONUTF8=1 python scripts/b33k_summarize.py results/b33k_*.jsonl
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

PRICE = {"in": 0.75 / 1e6, "out": 3.75 / 1e6}


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - s) / d * 100, (c + s) / d * 100)


def load(p: Path):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main() -> int:
    rows = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"MISSING {p}")
            continue
        d = load(p)
        if not d:
            print(f"EMPTY {p}")
            continue
        n = len(d)
        ok = sum(1 for r in d if r.get("judge_correct"))
        ti = sum(r.get("usage_input_tokens") or 0 for r in d)
        to = sum(r.get("usage_output_tokens") or 0 for r in d)
        th = sum((r.get("usage_meta") or {}).get("thoughts_token_count", 0)
                 for r in d)
        lat = sum(r.get("latency_s") or 0.0 for r in d)
        dev = sum(1 for r in d if r.get("protocol_deviation"))
        empt = sum(1 for r in d if not str(r.get("answer", "")).strip())
        mx = sum(1 for r in d
                 if "MAX_TOKENS" in str((r.get("usage_meta") or {})
                                        .get("finish_reason", "")))
        cost = ti * PRICE["in"] + to * PRICE["out"]
        lo, hi = wilson(ok, n)
        rows.append(dict(file=p.name, mode=d[0].get("mode"), n=n, ok=ok,
                         acc=ok / n * 100, lo=lo, hi=hi,
                         ti=ti / n, to=to / n, th=th / n,
                         lat=lat / n, cost_q=cost / n, cost=cost,
                         dev=dev, empty=empt, maxtok=mx))
        by = defaultdict(lambda: [0, 0])
        for r in d:
            b = by[r.get("question_type")]
            b[0] += bool(r.get("judge_correct"))
            b[1] += 1
        rows[-1]["byqtype"] = {k: (v[0], v[1]) for k, v in sorted(by.items())}
    print(f"{'file':52s} {'n':>4s} {'acc%':>7s} {'95%CI':>16s} "
          f"{'in/q':>8s} {'out/q':>7s} {'think/q':>8s} {'lat_s':>6s} "
          f"{'$/q':>8s} {'$tot':>7s} {'dev':>4s} {'empty':>5s} {'maxtok':>6s}")
    for r in rows:
        print(f"{r['file']:52s} {r['n']:4d} {r['acc']:7.2f} "
              f"[{r['lo']:5.1f},{r['hi']:5.1f}] {r['ti']:8.0f} {r['to']:7.0f} "
              f"{r['th']:8.0f} {r['lat']:6.1f} {r['cost_q']:8.5f} "
              f"{r['cost']:7.3f} {r['dev']:4d} {r['empty']:5d} {r['maxtok']:6d}")
    print("\n-- 逐题型 --")
    for r in rows:
        print(r["file"], {k: f"{v[0]}/{v[1]}" for k, v in
                          r["byqtype"].items()})
    print(f"\nGEMINI READER COST TOTAL = ${sum(r['cost'] for r in rows):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
