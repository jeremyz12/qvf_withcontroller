# -*- coding: utf-8 -*-
"""批 33-J2:在 v2.4 头条语料上重生成 144 道 dim4(S2 point-in-time)探针。

金标规则**逐字取自** scripts/newdom_gen_probes.py 的 S2 分支(date utils 直接
import 原件,不复写):
  取一对相邻且日期不同的链项 (Da,Db),其中 Da 在链内唯一;查询日 d 在 floor/
  ceil 两种残缺日期约定下都严格居于 (Da,Db) 内(整日期要求间隔 >=3 天,残缺
  日期要求年差 >=2 且取严格中间年);gold = 最后一个 date <= d 的链项的值;
  dim4 不加 "(Today is ...)" 前缀。

题面用 newdom_gen_probes.BRIDGE["dim4_point_in_time"](= 老域 probing_queries
的 dim4 原生表面 "What {slot} did I have on {d}?"),slot 取条目的 slot 字段。

种子 = newdom_gen_probes.SEED,逐条目独立 Random(f"{SEED}-b33j-{uid}"),
故可重复生成。

用法:python scripts/b33j_gen_dim4_probes.py
输出:data/b33j_ws_dim4_probes.jsonl + 同名 .meta.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from newdom_gen_probes import (BRIDGE, SEED, is_partial, iso,  # noqa: E402
                               parse_parts, to_ord)

CORPUS = "data/wikistate_full_ALL_v24.json"
OUT = "data/b33j_ws_dim4_probes.jsonl"


def main() -> int:
    entries = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    tmpl = BRIDGE["dim4_point_in_time"]
    rows, skipped, agree, disagree = [], [], 0, 0
    for e in entries:
        uid, slotword, chain = e["uid"], e["slot"], e["chain"]
        dates = [c["date"] for c in chain]
        values = [c["value"] for c in chain]
        m = len(chain)
        pairs = []
        for i in range(m - 1):
            if dates[i] == dates[i + 1]:
                continue
            if dates.count(dates[i]) != 1:
                continue
            Da, Db = dates[i], dates[i + 1]
            if is_partial(Da) or is_partial(Db):
                ya, yb = parse_parts(Da)[0], parse_parts(Db)[0]
                if yb - ya >= 2:
                    pairs.append(("partial", i, Da, Db))
            else:
                if to_ord(Db, "floor") - to_ord(Da, "floor") >= 3:
                    pairs.append(("full", i, Da, Db))
        if not pairs:
            skipped.append(uid)
            continue
        rng = random.Random(f"{SEED}-b33j-{uid}")
        kind, i, Da, Db = rng.choice(pairs)
        if kind == "full":
            lo, hi = to_ord(Da, "floor") + 1, to_ord(Db, "floor") - 1
            d = iso(rng.randint(lo, hi))
        else:
            ya, yb = parse_parts(Da)[0], parse_parts(Db)[0]
            y = rng.randint(ya + 1, yb - 1)
            d = f"{y:04d}-{rng.randint(3, 10):02d}-{rng.randint(5, 25):02d}"
        gi = max(i2 for i2 in range(m)
                 if to_ord(dates[i2], "floor") <= to_ord(d, "floor"))
        gold = values[gi]
        # 交叉核对:语料自带的归档 dim4 探针(不同随机日,同一金标规则)
        arch = (e.get("probing_queries") or {}).get("dim4_point_in_time") or {}
        if arch.get("date"):
            ad = arch["date"]
            gj = max(i2 for i2 in range(m)
                     if to_ord(dates[i2], "floor") <= to_ord(ad, "floor"))
            if str(values[gj]) == str(arch.get("gold")):
                agree += 1
            else:
                disagree += 1
        rows.append({
            "uid": uid, "qid": f"{uid}_b33jdim4", "qtype": "chain-dim4_point_in_time",
            "question": tmpl.format(slot=slotword, d=d), "gold": gold,
            "date": d,
            "basis": f"d={d} strictly inside ({Da},{Db}) under floor and ceil "
                     "partial-date conventions; gold = value of last chain "
                     "item with date <= d"})
    (ROOT / OUT).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    meta = {"seed": SEED, "corpus": CORPUS, "n": len(rows),
            "skipped_uids": skipped,
            "archived_dim4_gold_rule_agreement": [agree, disagree],
            "template": tmpl,
            "rule_source": "scripts/newdom_gen_probes.py S2 dim4 branch"}
    (ROOT / OUT.replace(".jsonl", ".meta.json")).write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(rows)} dim4 probes -> {OUT}; skipped {len(skipped)}: "
          f"{skipped}")
    print(f"archived-dim4 gold-rule cross-check: agree={agree} "
          f"disagree={disagree}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
