# -*- coding: utf-8 -*-
"""批 33-C 冻结保留集·步骤2.5:合并条目池 + 按开发场链长直方图定选。

为什么要这一步:开发场 144 链的链长分布是 3:86 / 4:33 / 5:9 / 6:8 / 7:5 / 8:3
(均值 3.76);新切片若按发现序或纯最短序取,链长会系统性偏离,C2("任何臂
开发场→保留集下降 ≤5pp")就会被难度差混淆。这里把链长当作**匹配变量**:
按开发场比例最大余数法缩放到 40 链 → 目标 3:24 / 4:9 / 5:3 / 6:2 / 7:1 / 8:1,
在四个槽位的配额(P108 14 / P39 12 / P54 11 / P551 3)下求一个可行分配。
只改"选哪 40 条",不改任何过滤规则,选中名单落盘可审。

产物:data/holdout_itempool_<PROP>.json(合并去重后的候选池)
      data/holdout_selection_v1.json(选中名单 + 达成直方图)
"""
from __future__ import annotations

import collections
import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLOTS = {"P108": 14, "P39": 12, "P54": 11, "P551": 3}
DEV_HIST = {3: 86, 4: 33, 5: 9, 6: 8, 7: 5, 8: 3}   # 开发场 144 链
N = 40


def target_hist():
    tot = sum(DEV_HIST.values())
    raw = {L: n * N / tot for L, n in DEV_HIST.items()}
    base = {L: int(v) for L, v in raw.items()}
    rem = N - sum(base.values())
    for L, _ in sorted(raw.items(), key=lambda kv: -(kv[1] - int(kv[1]))):
        if rem <= 0:
            break
        base[L] += 1
        rem -= 1
    return {L: n for L, n in base.items() if n}


def load_pool(prop):
    seen = {}
    for p in [ROOT / f"data/holdout_items_{prop}.json",
              ROOT / f"scratchpad/holdout_items_{prop}_discovery_order.json"]:
        if not p.exists():
            continue
        for e in json.loads(p.read_text(encoding="utf-8")):
            seen.setdefault(e["qid"], e)
    items = sorted(seen.values(), key=lambda e: (len(e["chain"]), e["qid"]))
    (ROOT / f"data/holdout_itempool_{prop}.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def main():
    tgt = target_hist()
    pools = {p: load_pool(p) for p in SLOTS}
    avail = {p: collections.Counter(min(8, len(e["chain"])) for e in pools[p])
             for p in SLOTS}
    print("目标链长直方图:", tgt)
    for p in SLOTS:
        print(f"  {p} 可用 {len(pools[p])}: {dict(sorted(avail[p].items()))}")

    slots = list(SLOTS)
    lengths = sorted(tgt, reverse=True)      # 稀有的先分配
    alloc = {p: {} for p in slots}

    def rec(li, used):
        if li == len(lengths) - 1:           # 最短那档由剩余配额强制确定
            L = lengths[li]
            need = tgt[L]
            take = {p: SLOTS[p] - used[p] for p in slots}
            if sum(take.values()) != need:
                return False
            if any(take[p] > avail[p].get(L, 0) or take[p] < 0 for p in slots):
                return False
            for p in slots:
                alloc[p][L] = take[p]
            return True
        L = lengths[li]
        caps = [min(avail[p].get(L, 0), SLOTS[p] - used[p]) for p in slots]
        for combo in product(*[range(c + 1) for c in caps]):
            if sum(combo) != tgt[L]:
                continue
            for p, k in zip(slots, combo):
                alloc[p][L] = k
                used[p] += k
            if rec(li + 1, used):
                return True
            for p, k in zip(slots, combo):
                used[p] -= k
                alloc[p].pop(L, None)
        return False

    ok = rec(0, {p: 0 for p in slots})
    if not ok:
        print("!! 目标直方图在当前池下不可行;退回槽位内最短优先")
        sel = {p: [e["qid"] for e in pools[p][:SLOTS[p]]] for p in slots}
    else:
        sel = {}
        for p in slots:
            by_len = collections.defaultdict(list)
            for e in pools[p]:
                by_len[min(8, len(e["chain"]))].append(e["qid"])
            picked = []
            for L in sorted(alloc[p]):
                picked += by_len[L][:alloc[p][L]]
            sel[p] = picked
    got = collections.Counter()
    for p in slots:
        by_qid = {e["qid"]: e for e in pools[p]}
        for q in sel[p]:
            got[min(8, len(by_qid[q]["chain"]))] += 1
        print(f"  {p}: 选中 {len(sel[p])}/{SLOTS[p]} "
              f"{dict(sorted(collections.Counter(min(8, len(by_qid[q]['chain'])) for q in sel[p]).items()))}")
    print("达成链长直方图:", dict(sorted(got.items())),
          "  目标:", dict(sorted(tgt.items())),
          "  匹配:", dict(sorted(got.items())) == dict(sorted(tgt.items())))
    (ROOT / "data/holdout_selection_v1.json").write_text(json.dumps({
        "quota": SLOTS, "dev_hist": DEV_HIST, "target_hist": tgt,
        "achieved_hist": dict(sorted(got.items())),
        "feasible_exact_match": bool(ok), "selection": sel},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> data/holdout_selection_v1.json")


if __name__ == "__main__":
    main()
