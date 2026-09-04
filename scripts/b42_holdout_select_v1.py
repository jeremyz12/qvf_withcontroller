# -*- coding: utf-8 -*-
"""批 42 冻结保留集 2·步骤2.5:合并条目池 + 按开发场链长直方图定选。

与 scripts/holdout_select_v1.py 逐字同逻辑(链长匹配变量、目标直方图算法、
最大余数法),两处改动:
  (1) 槽位配额改为 **10/10/10/10**(批 42 预注册目标:每槽位类型 10 条,
      而非按开发场比例缩放的 14/12/11/3——批 42 探索性抓取显示四个属性在
      双重排除集下均有充足候选供给,故采用均衡配额而非比例配额);
  (2) 输入输出路径改为 holdout2_*。
链长目标直方图仍按开发场 144 链比例缩放到 40(与 holdout v1 相同的匹配变量,
保持"只改选哪 40 条,不改任何过滤规则"的构造纪律)。

产物:data/holdout2_itempool_<PROP>.json、data/holdout2_selection_v1.json
"""
from __future__ import annotations

import collections
import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLOTS = {"P108": 10, "P39": 10, "P54": 10, "P551": 10}
DEV_HIST = {3: 86, 4: 33, 5: 9, 6: 8, 7: 5, 8: 3}   # 开发场 144 链(同 v1)
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
    for p in [ROOT / f"data/holdout2_items_{prop}.json"]:
        if not p.exists():
            continue
        for e in json.loads(p.read_text(encoding="utf-8")):
            seen.setdefault(e["qid"], e)
    items = sorted(seen.values(), key=lambda e: (len(e["chain"]), e["qid"]))
    (ROOT / f"data/holdout2_itempool_{prop}.json").write_text(
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
    lengths = sorted(tgt, reverse=True)
    alloc = {p: {} for p in slots}

    def rec(li, used):
        if li == len(lengths) - 1:
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
    (ROOT / "data/holdout2_selection_v1.json").write_text(json.dumps({
        "quota": SLOTS, "dev_hist": DEV_HIST, "target_hist": tgt,
        "achieved_hist": dict(sorted(got.items())),
        "feasible_exact_match": bool(ok), "selection": sel},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("-> data/holdout2_selection_v1.json")


if __name__ == "__main__":
    main()
