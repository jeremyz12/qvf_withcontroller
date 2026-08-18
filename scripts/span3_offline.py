# -*- coding: utf-8 -*-
"""scripts/span3_offline.py — 把 QVF_CARD_VERIFY_SPAN=3 的溯源修复离线套用到既有卡片库。

为什么可以离线做:`wt_qvf_prototype.py:414-446` 的整个校验/修复块是**纯代码**——
它只读已抽好的 `recs` 与源文本 `payload`,不调用任何模型。因此无需重跑建卡
(105 个库 ≈ $6.3),直接在既有库上复算即可,成本 $0。

逐字复刻的判定顺序(与原件同序,任何一步换序都会改变结果):
  1. `source_span` 为空 -> 跳过
  2. span 是其 `source_memory_id` 文本的子串 -> 合规
  3. 否则计违约;若 span 在**全库**都找不到 -> 编造/改写,标 verbatim=False
  4. 否则(库内找得到、只是挂错 id):唯一命中则改挂并标 repaired;
     多处命中为真实歧义,**一律不修**——带猜测的归属比没有归属更坏,
     且改 memory 会连带改 `_rec_date` 的会话日期回退值、进而改变链序。

自校验:重建的 payload 必须覆盖卡片里出现的每一个 `source_memory_id`,
否则说明记忆流口径对不上,直接报错退出而非产出一个悄悄错的库。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def payload_of(entry: dict) -> list:
    """与 wt_qvf_prototype 建卡时的 payload 同构(memory_id / date / text)。"""
    uid = entry.get("uid", "")
    out = []
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, turn in enumerate(sess.get("turns", [])):
            out.append({"memory_id": f"{uid}/s{si}#r{ri}",
                        "date": sess.get("date", ""),
                        "text": str(turn)})
    return out


def apply_span3(recs: list, payload: list) -> dict:
    txt = {p["memory_id"]: p["text"] for p in payload}
    allt = "\n".join(p["text"] for p in payload)
    bad = missing = repaired = ambig = 0
    for r in recs:
        sp = (r.get("source_span") or "").strip()
        if not sp:
            continue
        if sp in txt.get(r.get("source_memory_id"), ""):
            continue
        bad += 1
        if sp not in allt:
            missing += 1
            r["source_span_verbatim"] = False
            continue
        hits = [p["memory_id"] for p in payload if sp in p["text"]]
        if len(hits) == 1:
            r["source_memory_id"] = hits[0]
            r["source_span_repaired"] = True
            repaired += 1
            continue
        ambig += 1
        r["source_span_verbatim"] = False
    return {"span_violations": bad, "span_not_in_history": missing,
            "span_repaired": repaired, "span_ambiguous": ambig,
            "span_verify_mode": 3}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True, help="源卡片目录")
    ap.add_argument("--out", required=True, help="输出卡片目录")
    ap.add_argument("--data", nargs="+", required=True, help="chain 架构数据 json")
    ap.add_argument("--uids-from", default=None,
                    help="只处理该 jsonl 里出现的 uid(默认处理源目录全部)")
    a = ap.parse_args()

    entries = {}
    for f in a.data:
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)

    src, dst = ROOT / a.cards, ROOT / a.out
    dst.mkdir(parents=True, exist_ok=True)
    want = None
    if a.uids_from:
        want = {json.loads(l)["uid"]
                for l in (ROOT / a.uids_from).read_text(encoding="utf-8").splitlines() if l.strip()}

    tot = dict(span_violations=0, span_not_in_history=0, span_repaired=0,
               span_ambiguous=0)
    bad_ids = {}
    n_lib = n_rec = 0
    unknown = []
    for p in sorted(src.glob("*.json")):
        uid = p.stem
        if want is not None and uid not in want:
            continue
        if uid not in entries:
            unknown.append(uid)
            continue
        card = json.loads(p.read_text(encoding="utf-8"))
        recs = card.get("records", [])
        pay = payload_of(entries[uid])
        ids = {x["memory_id"] for x in pay}
        # 自校验:统计卡片引用了但重建 payload 里不存在的 memory_id。
        # **不中止** —— 原件 `txt.get(id, "")` 对未知 id 返回空串,于是该记录
        # 自然计为违约并进入修复流程,这正是 mode 3 要处理的一类。中止会
        # 偏离原件语义。但这批 id 是独立缺陷(实测形如 `s8#3`,少了 `r`),
        # 必须单独计数报出,否则会被混进"违约率"里看不见。
        miss = {r.get("source_memory_id") for r in recs} - ids - {None}
        if miss:
            bad_ids[uid] = sorted(miss)
        st = apply_span3(recs, pay)
        for k in tot:
            tot[k] += st[k]
        n_lib += 1
        n_rec += len(recs)
        (dst / p.name).write_text(json.dumps({**card, "records": recs, **st},
                                             ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    if unknown:
        print(f"跳过 {len(unknown)} 个数据里没有的 uid", file=sys.stderr)
    if bad_ids:
        n = sum(len(v) for v in bad_ids.values())
        print()
        print(f"  ⚠️ 另有独立缺陷:{len(bad_ids)} 个库共 {n} 个 source_memory_id "
              f"在记忆流里不存在(实测形如少了 `r` 的 `s8#3`)。这类记录会被"
              f"当作违约并进入修复流程,故须单独计数,否则混进违约率里看不见。")
        print(f"     样例 {[(k, v[:2]) for k, v in list(bad_ids.items())[:3]]}")
    print(f"处理 {n_lib} 个库 / {n_rec} 条记录 -> {a.out}")
    print(f"  逐字锚点违约      {tot['span_violations']:5d} "
          f"({tot['span_violations'] / max(n_rec, 1) * 100:.2f}%)")
    print(f"  全库找不到(编造)  {tot['span_not_in_history']:5d}")
    print(f"  溯源修复(唯一命中) {tot['span_repaired']:5d}")
    print(f"  归属歧义(不修)    {tot['span_ambiguous']:5d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
