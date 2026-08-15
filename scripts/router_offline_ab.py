# -*- coding: utf-8 -*-
"""路由离线 A/B(零 LLM;dev 工具,新文件,不改任何冻结路径)。

从既有 routes jsonl 读逐题聚焦结果(focus_slot/scope/presupposed),在当前
env 旗标下重算 route_v2,并按 newdom_router.phase_combine 同一挑臂/降级语义
用既有臂行组合出终榜。用于:
  ① 旗标关:与既有 routes 决策逐题对拍(冻结等价证明);
  ② 旗标开:dev A/B(路由分布 + 组合准确率前后对比)。

用法(env 由调用方设置;import 前生效):
  QVF_ROUTER_KEYS=1 QVF_GATE_V2=1 QVF_CARDS_KEYED=results/wt_cards_newdom \
  python scripts/router_offline_ab.py --routes results/newdom_routes_P1303.jsonl \
      --arm-dir results/newdom_{arm}_P1303.jsonl --out <decisions.jsonl>
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", required=True,
                    help="既有 routes jsonl(带 focus_slot/scope/presupposed)")
    ap.add_argument("--arms", required=True,
                    help="臂行文件模板,含 {arm} 占位,如 "
                    "results/newdom_{arm}_P1303.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", nargs="+", default=None,
                    help="chain 架构数据 json:按 qid_raw 还原问题原文"
                    "(route_v2 的事件算术正则/一人称检查需要)")
    a = ap.parse_args()
    assert "P69" not in a.routes and "P69" not in a.arms, \
        "P69 是测试床,离线 A/B 拒绝触碰"

    from scripts import qvf_router as QR  # env 已生效后 import

    qtext = {}
    for df in (a.data or []):
        assert "P69" not in df
        for it in json.loads(Path(df).read_text(encoding="utf-8")):
            for dim, q in (it.get("probing_queries") or {}).items():
                qtext[f"{it['uid']}_{dim}"] = q["q"]

    arms = {arm: QR.load_arm(a.arms.format(arm=arm))
            for arm in ("direct", "rt", "wt", "prompt")}
    routes = [json.loads(l) for l in open(a.routes, encoding="utf-8")]
    dist = Counter()
    changed = fallback = missing = correct = 0
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for row in routes:
            fo = {"slot": row.get("focus_slot", ""),
                  "scope": row.get("focus_scope", "unclear"),
                  "presupposed": row.get("focus_presupposed", "")}
            q = qtext.get(row.get("qid_raw", ""), row.get("question", ""))
            r, kd = QR.route_v2(row["uid"], fo, q)
            if r != row.get("route"):
                changed += 1
            dist[r] += 1
            qid = row["qid"]
            pick, res = r, None
            if r == "prompt":
                if qid in arms["prompt"]:
                    res = arms["prompt"][qid]
                else:
                    missing += 1
                    pick = None
            elif r == "direct":
                if qid in arms["direct"]:
                    res = arms["direct"][qid]
                else:
                    missing += 1
                    pick = None
            else:
                if qid not in arms[pick]:
                    fallback += 1
                    pick = "rt" if "rt" != r and qid in arms["rt"] else "direct"
                    if qid not in arms[pick]:
                        pick = "direct"
                res = arms[pick].get(qid, False)
            correct += bool(res)
            f.write(json.dumps({**row, "route_new": r, "keyed_depth_new": kd,
                                "picked_arm": pick, "result": res},
                               ensure_ascii=False) + "\n")
    n = len(routes)
    print(f"n={n} ROUTER={correct / n * 100:.1f}% 分布 {dict(dist)} "
          f"决策变更 {changed} 降级{fallback} 缺行{missing}")


if __name__ == "__main__":
    main()
