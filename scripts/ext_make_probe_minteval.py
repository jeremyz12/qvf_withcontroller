# -*- coding: utf-8 -*-
"""批 33-G4 探针采样器:MINTEval multi_turn_dialogue,按 n_steps_back 分层。

为什么必须分层:MINTEval 里只有 `history` 型题带 n_steps_back(深度),而
**深度按用户聚簇**——例如 o3__user_113 的 30 道 history 题深度全在 3-7,
sonnet-4.5__user_0 则跨 2-51。若在题池里随机抽,深度桶与用户身份完全共线,
"acc 随深度下降"就无法与"某些用户天生更难"区分。故:
  ① 只从 history 题抽(其余四型 simple/counting/ordering/multi-hop 无深度标注);
  ② 每个用户配额相同(--per-user);
  ③ 用户内按**全局深度桶**轮转取题(bin 宽 5,46+ 并作一桶),
     每桶内 seed=33 随机取,轮转起点按用户序号错开。
这样每个用户在自己覆盖到的深度范围内被摊平,聚合后深度桶与用户身份解耦。

产物:data/external/minteval_probe.jsonl(uid/qid/qtype/question/gold/cutoff/meta)

用法:
  PYTHONUTF8=1 python scripts/ext_make_probe_minteval.py \
      --uids-file scratchpad/b33g_built_uids.txt --per-user 15
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "external", "minteval_unified.json")
DST = os.path.join(REPO, "data", "external", "minteval_probe.jsonl")

BINS = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25),
        (26, 30), (31, 35), (36, 40), (41, 45), (46, 10 ** 6)]


def bin_of(d: int) -> int:
    for i, (lo, hi) in enumerate(BINS):
        if lo <= d <= hi:
            return i
    raise ValueError("depth %r out of range" % d)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uids-file", required=True,
                    help="每行一个 uid(实际建好卡的店),只对这些用户出题")
    ap.add_argument("--per-user", type=int, default=15)
    ap.add_argument("--seed", type=int, default=33)
    ap.add_argument("--out", default=DST)
    ap.add_argument("--no-candidates", action="store_true",
                    help="不注入候选清单(默认注入,见下方说明)")
    a = ap.parse_args()

    keep = [l.strip().split("\t")[0] for l in open(a.uids_file, encoding="utf-8")
            if l.strip()]
    stores = {s["uid"]: s for s in
              json.loads(open(SRC, encoding="utf-8").read())}
    rng = random.Random(a.seed)

    rows = []
    for ui, uid in enumerate(keep):
        s = stores[uid]
        by_bin = defaultdict(list)
        for q in s["questions"]:
            d = (q.get("meta") or {}).get("n_steps_back")
            if q["dim"] != "history" or d is None:
                continue
            by_bin[bin_of(int(d))].append(q)
        for b in by_bin:
            by_bin[b].sort(key=lambda q: q["qid"])
            rng.shuffle(by_bin[b])
        order = sorted(by_bin)
        if not order:
            print("WARN %s: no history questions, skipped" % uid)
            continue
        start = ui % len(order)
        order = order[start:] + order[:start]
        picked, i = [], 0
        while len(picked) < a.per_user and any(by_bin[b] for b in order):
            b = order[i % len(order)]
            if by_bin[b]:
                picked.append(by_bin[b].pop())
            i += 1
        if len(picked) < a.per_user:
            print("WARN %s: only %d/%d history questions available"
                  % (uid, len(picked), a.per_user))
        for q in sorted(picked, key=lambda q: q["qid"]):
            # 候选清单注入(默认开):MINTEval 官方 _common.py 的题面本身就带
            # "Pick the answer from this candidate list ..." + 候选项列表,
            # 金标是该清单里的规范化标签(如 deadline_driven),对话原文里
            # 从不逐字出现。不给清单则两臂只会说"我没有偏好变更日志"——
            # 预跑 6 题 direct 臂 0/6 全弃答,考场直接触底、无法区分两臂。
            # 故按官方题面协议注入,**两臂同一字节的题面**(与批 17
            # MemConflict 注入 "(Today is X.)" 同一先例)。
            qtext = q["question"]
            cands = (q.get("meta") or {}).get("candidates") or []
            if cands and not a.no_candidates:
                qtext += ("\n\nPick the answer from this candidate list "
                          "(reply with exactly one value from the list, "
                          "verbatim):\n"
                          + "\n".join("- %s" % c for c in cands))
            rows.append({
                "uid": uid, "qid": q["qid"], "qtype": q["dim"],
                "question": qtext, "gold": q["gold"],
                "cutoff": "",          # 题在流末提出,无增量协议截断
                "meta": q["meta"],
            })

    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    depths = [int(r["meta"]["n_steps_back"]) for r in rows]
    bc = Counter(bin_of(d) for d in depths)
    print("users %d  questions %d  (per-user target %d)"
          % (len(keep), len(rows), a.per_user))
    print("depth: min %d med %d max %d" % (min(depths),
                                           sorted(depths)[len(depths) // 2],
                                           max(depths)))
    for i, (lo, hi) in enumerate(BINS):
        lab = "%d-%d" % (lo, hi) if hi < 10 ** 6 else "%d+" % lo
        nu = len({r["uid"] for r in rows
                  if bin_of(int(r["meta"]["n_steps_back"])) == i})
        print("  bin %-6s n=%-4d users=%d" % (lab, bc.get(i, 0), nu))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
