# -*- coding: utf-8 -*-
"""批 33-E 检索侧诊断($0,零 API):金证据召回。

金证据 = 每条链的 chain[i].state_span 所在的那一条记忆(state_span 作为子串
出现在 str(turn) 里)。四种题型都要求把**整条链**的转移点数出来,所以
"top-10 里装进了几个 state_span"直接决定直读臂的天花板。

对每份检索计划报:
  recall@10(全链)  = 命中的 state_span 数 / 该题可用的 state_span 数
  full@10          = 整条链全部装进 top-10 的题目比例
  cutoff 版         = 只算 date ≤ 问题里的 (Today is X.) 的链节

用法:
  PYTHONUTF8=1 python scripts/b33e_recall.py --plan 名称=计划jsonl [--plan ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ext_direct_arm import _memories, _query_date  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--questions", default="data/wsc_s5_v2.jsonl")
    ap.add_argument("--plan", action="append", default=[],
                    help="名称=计划jsonl(按最后一个 = 切分)")
    a = ap.parse_args()
    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = {json.loads(l)["qid"]: json.loads(l)
          for l in open(a.questions, encoding="utf-8") if l.strip()}
    # uid -> [(chain_date, memory_id or None)]
    gold = {}
    for uid, e in entries.items():
        M = _memories(e)
        rows = []
        for link in e.get("chain", []):
            span = (link.get("state_span") or "").strip()
            mid = None
            if span:
                for m in M:
                    if span in m.content:
                        mid = m.memory_id
                        break
            rows.append((str(link.get("date", "")), mid, span))
        gold[uid] = rows
    miss = sum(1 for u in gold for d, m, s in gold[u] if s and m is None)
    tot = sum(1 for u in gold for d, m, s in gold[u] if s)
    print(f"gold state_span 定位:{tot - miss}/{tot} 条可锚定到记忆条")
    print()
    print(f"{'plan':30s} {'n':>4s} {'recall@10':>10s} {'full@10%':>9s} "
          f"{'recall(cut)':>12s} {'full(cut)%':>11s}")
    for spec in a.plan:
        name, path = spec.rsplit("=", 1)
        num = den = numc = denc = 0
        nfull = nfullc = n = 0
        for l in open(path, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            q = qs[r["qid"]]
            sel = set(r["memory_ids"])
            qd = _query_date(entries[r["uid"]], q["question"])
            hits = [(d, m) for d, m, s in gold[r["uid"]] if m]
            if not hits:
                continue
            n += 1
            h = sum(1 for d, m in hits if m in sel)
            num += h
            den += len(hits)
            nfull += (h == len(hits))
            cut = [(d, m) for d, m in hits if not qd or d <= qd]
            if cut:
                hc = sum(1 for d, m in cut if m in sel)
                numc += hc
                denc += len(cut)
                nfullc += (hc == len(cut))
        print(f"{name:30s} {n:4d} {num / den:10.3f} {nfull / n * 100:9.1f} "
              f"{numc / max(1, denc):12.3f} {nfullc / n * 100:11.1f}")


if __name__ == "__main__":
    main()
