# -*- coding: utf-8 -*-
"""批 33-J3:从 v2.4 语料造"无填充"对照语料(只留链会话)。

设计(对应 narrative_gaps_grounded_20260902.md 的 E-K / G23):
  12pp 检索缺口至今是**观察性分箱**(有填充语料内部按检索命中与否分箱),
  从未有过"把填充整体拿掉"的操纵对照。本脚本机械地删除 chain_index is None
  的会话,其余字节(uid/type/slot/chain/probing_queries/attribution、保留
  会话的 date/turns/chain_index)逐字不动。

抽样:144 条链按 slot 比例分层,种子固定,取 30 条(=120 题,与 wsc_s5_v2
的四型题一一对应)。

用法:python scripts/b33j_build_nofiller.py
输出:data/b33j_nofiller_30.json、data/b33j_nofiller_30_q120.jsonl、
      data/b33j_nofiller_30.meta.json
"""
from __future__ import annotations

import collections
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = "b33j-nofiller-30"
N_PICK = 30
SRC = "data/wikistate_full_ALL_v24.json"
QSRC = "data/wsc_s5_v2.jsonl"


def main() -> int:
    entries = json.loads((ROOT / SRC).read_text(encoding="utf-8"))
    by_slot = collections.defaultdict(list)
    for e in entries:
        by_slot[e["slot"]].append(e["uid"])
    # 比例分层:按 slot 占比取整(最大余数法补齐到 N_PICK)
    tot = len(entries)
    quota, rema = {}, []
    for s, us in by_slot.items():
        exact = N_PICK * len(us) / tot
        quota[s] = int(exact)
        rema.append((exact - int(exact), s))
    for _, s in sorted(rema, reverse=True)[:N_PICK - sum(quota.values())]:
        quota[s] += 1
    picked = []
    for s in sorted(by_slot):
        rng = random.Random(f"{SEED}-{s}")
        picked += rng.sample(sorted(by_slot[s]), quota[s])
    picked = sorted(picked)
    assert len(picked) == N_PICK, (len(picked), quota)

    keep = set(picked)
    out, n_keep_sess, n_drop_sess, chars_keep, chars_drop = [], 0, 0, 0, 0
    for e in entries:
        if e["uid"] not in keep:
            continue
        e2 = dict(e)
        ss = []
        for s in e["sessions"]:
            ln = sum(len(str(t)) for t in s.get("turns", []))
            if s.get("chain_index") is not None:
                ss.append(s)
                n_keep_sess += 1
                chars_keep += ln
            else:
                n_drop_sess += 1
                chars_drop += ln
        e2["sessions"] = ss
        out.append(e2)
    (ROOT / "data/b33j_nofiller_30.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")

    qs = [json.loads(l) for l in
          (ROOT / QSRC).read_text(encoding="utf-8").splitlines() if l.strip()]
    q120 = [q for q in qs if q["uid"] in keep]
    (ROOT / "data/b33j_nofiller_30_q120.jsonl").write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in q120),
        encoding="utf-8")

    meta = {"seed": SEED, "src": SRC, "n_chains": len(out),
            "slot_quota": quota, "uids": picked, "n_questions": len(q120),
            "sessions_kept": n_keep_sess, "sessions_dropped": n_drop_sess,
            "chars_kept": chars_keep, "chars_dropped": chars_drop,
            "chain_text_share_pct": round(
                100 * chars_keep / max(1, chars_keep + chars_drop), 2),
            "qtype_counts": dict(collections.Counter(q["qtype"] for q in q120))}
    (ROOT / "data/b33j_nofiller_30.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1)[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
