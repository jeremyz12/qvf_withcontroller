# -*- coding: utf-8 -*-
"""新域三属性(P26/P69/P1303)路由驱动:只 import 冻结 qvf_router,零改动复用
其 focus_of / route_v2 / load_arm / normkey。

冻结契约:scripts/qvf_router.py 一行不改;本脚本仅是数据侧跑批器,把新域
S1-S4 题喂给冻结路由函数,并按冻结 main() v2 分支的同一挑臂/降级语义组合
臂行。v4.2 env 旗标组合由调用方设置,本脚本开头断言核对:
  QVF_ROUTER_KEYS=1  QVF_GATE_V2=1  (QVF_GATE_DEPTH 缺省=3)
  QVF_CARDS_KEYED=results/wt_cards_newdom  (新域卡片库;v4.2 原值为
  results/wt_cards_v42,该项为数据路径而非行为旗标,指向本轮新建卡库)

用法:
  python scripts/newdom_router.py --phase routes   # 聚焦+路由决策(写 routes jsonl)
  python scripts/newdom_router.py --phase combine  # 按臂行组合终榜(写 per-domain jsonl)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── v4.2 旗标断言(必须在 import 冻结模块之前设置,模块级读取)──
os.environ.setdefault("QVF_ROUTER_KEYS", "1")
os.environ.setdefault("QVF_GATE_V2", "1")
os.environ.setdefault("QVF_CARDS_KEYED", "results/wt_cards_newdom")
assert os.environ.get("QVF_ROUTER_KEYS") == "1"
assert os.environ.get("QVF_GATE_V2") == "1"
assert os.environ.get("QVF_GATE_DEPTH", "3") == "3"
assert os.environ.get("QVF_CARDS_KEYED") == "results/wt_cards_newdom"

from scripts import qvf_router as QR  # noqa: E402  冻结模块,只 import 不改

DOMAINS = [
    ("newdom-P26", "data/newdom_P26_full.json"),
    ("newdom-P69", "data/newdom_P69_full.json"),
    ("newdom-P1303", "data/newdom_P1303_full.json"),
]

ROUTES_F = "results/newdom_routes_{dom}.jsonl"
OUT_F = "results/newdom_router_{dom}.jsonl"

# 臂行文件(与旧域同名臂语义:direct=framing_arm dense_direct;
# rt=framing_qvf_arm minimal_rules_species2;wt=wt_qvf_prototype read;
# prompt=framing_tlcot_arm)
ARM_FILES = {
    "direct": "results/newdom_direct_{dom}.jsonl",
    "rt": "results/newdom_rt_{dom}.jsonl",
    "wt": "results/newdom_wt_{dom}.jsonl",
    "prompt": "results/newdom_prompt_{dom}.jsonl",
}


def _questions(data_f):
    items = json.loads(Path(data_f).read_text(encoding="utf-8"))
    qs = []
    for it in items:
        for dim, q in (it.get("probing_queries") or {}).items():
            rid = f"{it['uid']}_{dim}"
            qs.append((it["uid"], QR.normkey(rid), rid, dim, q["q"]))
    return qs


def phase_routes():
    from concurrent.futures import ThreadPoolExecutor
    for dom, data_f in DOMAINS:
        name = dom.split("-", 1)[1]
        qs = _questions(data_f)
        with ThreadPoolExecutor(max_workers=8) as ex:
            focuses = list(ex.map(
                lambda x: QR.focus_of(dom, x[1], x[4]), qs))
        QR.CACHE_F.write_text(json.dumps(QR.cache, ensure_ascii=False),
                              encoding="utf-8")
        dist = Counter()
        with open(ROUTES_F.format(dom=name), "w", encoding="utf-8") as f:
            for (uid, qid, rid, dim, q), fo in zip(qs, focuses):
                r, kd = QR.route_v2(uid, fo, q)
                dist[r] += 1
                f.write(json.dumps({
                    "bench": dom, "uid": uid, "qid": qid, "qid_raw": rid,
                    "dim": dim, "route": r, "keyed_depth": kd,
                    "focus_slot": fo["slot"], "focus_scope": fo["scope"],
                    "focus_presupposed": fo["presupposed"],
                }, ensure_ascii=False) + "\n")
        print(f"{dom}: n={len(qs)} routes={dict(dist)}")


def phase_combine():
    grand = Counter()
    grand_n = grand_c = 0
    for dom, data_f in DOMAINS:
        name = dom.split("-", 1)[1]
        arms = {a: QR.load_arm(ARM_FILES[a].format(dom=name))
                for a in ARM_FILES}
        routes = [json.loads(l) for l in
                  open(ROUTES_F.format(dom=name), encoding="utf-8")]
        dist = Counter()
        fallback = missing = correct = 0
        with open(OUT_F.format(dom=name), "w", encoding="utf-8") as f:
            for row in routes:
                qid, r = row["qid"], row["route"]
                dist[r] += 1
                pick, res = r, None
                # 与冻结 main() v2 分支同一语义:prompt 缺行记 None 不降级;
                # wt/rt 缺行按 rt→direct 降级;direct 直取 direct 行。
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
                f.write(json.dumps({**row, "picked_arm": pick,
                                    "result": res}, ensure_ascii=False) + "\n")
        n = len(routes)
        print(f"{dom}: n={n} ROUTER={correct / n * 100:.1f}% "
              f"分布 {dict(dist)} 降级{fallback} 缺行{missing}")
        grand_n += n
        grand_c += correct
        for k, v in dist.items():
            grand[k] += v
    print(f"TOTAL n={grand_n}: ROUTER {grand_c / grand_n * 100:.1f}% "
          f"分布 {dict(grand)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["routes", "combine"], required=True)
    a = ap.parse_args()
    if a.phase == "routes":
        phase_routes()
    else:
        phase_combine()


if __name__ == "__main__":
    main()
