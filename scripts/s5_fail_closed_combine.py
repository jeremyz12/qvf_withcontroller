# -*- coding: utf-8 -*-
"""S5 编译臂 fail-closed 跑批侧组合器(新文件,不改任何冻结路径)。

QVF_FAIL_CLOSED=1 跑出的编译臂行里,空证据题带 fail_closed=true、
judge_correct=null。本脚本按预注册降级语义组合终榜:
  fail_closed 行 → 取同 qid 直读臂行(picked=direct);直读也缺行 → 弃答
  (picked=abstain,result=False);其余行原样(picked=arm)。
输出逐题组合行 + 汇总(总分与各题型 arm/direct/combined 对照)。

用法:
  python scripts/s5_fail_closed_combine.py \
      --arm results/newdom_s5_arm_P1303.jsonl \
      --direct results/newdom_s5_direct_P1303.jsonl \
      --out results/newdom_s5_combined_P1303.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict


def load(p):
    out = {}
    for l in open(p, encoding="utf-8"):
        s = l.strip()
        if s:
            r = json.loads(s)
            out[r["question_id"]] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--direct", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    arm, dire = load(a.arm), load(a.direct)
    by_t = defaultdict(lambda: [0, 0, 0, 0])  # arm, combined, direct, n
    n_fc = n_abstain = 0
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for qid, r in arm.items():
            t = r.get("question_type") or ""
            fc = bool(r.get("fail_closed"))
            if fc:
                n_fc += 1
                d = dire.get(qid)
                if d is not None:
                    pick, res = "direct", bool(d.get("judge_correct"))
                else:
                    pick, res = "abstain", False
                    n_abstain += 1
            else:
                pick, res = "arm", bool(r.get("judge_correct"))
            by_t[t][0] += (0 if fc else bool(r.get("judge_correct")))
            by_t[t][1] += res
            by_t[t][2] += bool((dire.get(qid) or {}).get("judge_correct"))
            by_t[t][3] += 1
            f.write(json.dumps({
                "question_id": qid, "question_type": t, "picked": pick,
                "fail_closed": fc, "result": res}, ensure_ascii=False) + "\n")
    ta = tc = td = tn = 0
    print(f"{'qtype':16s} {'arm':>6s} {'combined':>9s} {'direct':>7s}")
    for t, (x, c, d, n) in sorted(by_t.items()):
        print(f"{t:16s} {x:3d}/{n:<3d} {c:4d}/{n:<3d} {d:4d}/{n:<3d}")
        ta += x
        tc += c
        td += d
        tn += n
    print(f"{'TOTAL':16s} {ta:3d}/{tn:<3d} {tc:4d}/{tn:<3d} {td:4d}/{tn:<3d}"
          f"  ({ta / tn * 100:.1f}% -> {tc / tn * 100:.1f}%; direct "
          f"{td / tn * 100:.1f}%)  fail_closed={n_fc} abstain={n_abstain}")


if __name__ == "__main__":
    main()
