# -*- coding: utf-8 -*-
"""scripts/verify_persession_determinism.py — 判据④装配层确定性验证(零 LLM)。

预注册判据④:同一批未连边记录,打乱输入顺序 >= 1000 次,scripts.
write_persession.assemble() 的输出经 canonical_json() 稳定序列化后逐字节
相同(纯代码,零 LLM)。本脚本只 import assemble/canonical_json,不发起任何
API 调用。

构造一份有意刁难装配层的合成未连边记录集(单个 fixture,覆盖):
  - 2 个 owner × 3 个 slot_class(其中一个 slot_class 标为 set 基数)
  - 组内同一属性的 slot 原文大小写/下划线/空格写法不一致(考验槽位名归一
    的 tie-break 是否真的与顺序无关)
  - 日期部分缺失(仅 YYYY / YYYY-MM)与完全缺失(空字符串,靠会话日期回退)
    混合,且存在同日期并列(考验 record_id 决胜)
  - temporal_relation 覆盖 replacement / cessation / contradiction /
    unresolved / additive 五种取值
  - 两条内容完全相同的重复记录(不同列表位置)——装配应去重为一条

用法:
  python scripts/verify_persession_determinism.py [--trials 1000]
"""
from __future__ import annotations

import argparse
import copy
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.write_persession import assemble, canonical_json  # noqa: E402


def _fixture():
    recs = []

    def add(owner, slot_class, slot, value, date, temporal, cardinality="single",
             span_suffix=""):
        recs.append({
            "entity": "user" if owner == "user" else owner,
            "slot": slot,
            "value": value,
            "claim": f"{owner} {slot} is {value}",
            "slot_cardinality": cardinality,
            "temporal_relation": temporal,
            "condition": "",
            "implies_stale_slots": [],
            "stated_date": date,
            "source_span": f"{slot} {value} span{span_suffix}",
            "owner": owner,
            "slot_class": slot_class,
            "source_memory_id": f"m/{owner}-{slot_class}-{value}",
            "_session_date": date or "2020-01-01",
        })

    # owner=user, slot_class=residence (single) — 3 条链式替换,槽位文本写法故意不一致
    add("user", "residence", "home city", "Seattle", "2018", "unresolved")
    add("user", "residence", "Home_City", "Portland", "2020-05", "replacement")
    add("user", "residence", "HOME CITY", "Austin", "2022-05-01", "replacement")

    # owner=user, slot_class=employer (single) — 含 cessation + contradiction,含空日期(回退会话日期)
    add("user", "employer", "employer", "Acme Corp", "2019", "unresolved")
    add("user", "employer", "employer", "", "2021", "cessation")
    add("user", "employer", "Employer", "Beta LLC", "", "contradiction")

    # owner=user, slot_class=other:hobby (set) — 并存,不应连边
    add("user", "other:hobby", "hobby", "chess", "2017", "additive", cardinality="set")
    add("user", "other:hobby", "Hobby", "climbing", "2019", "additive", cardinality="set")
    add("user", "other:hobby", "HOBBY", "pottery", "2019", "additive", cardinality="set")

    # owner=Alex, slot_class=team (single) — 同日期并列(考验 record_id 决胜)
    add("Alex", "team", "team", "Red Sox", "2021-06-01", "unresolved")
    add("Alex", "team", "team", "Yankees", "2021-06-01", "replacement")

    # 精确重复记录(不同位置)——应去重为一条
    dup = copy.deepcopy(recs[0])
    recs.append(dup)

    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=1000)
    args = ap.parse_args()

    base = _fixture()
    print(f"fixture: {len(base)} raw records (incl. 1 exact duplicate)")

    ref_cards = assemble(copy.deepcopy(base))
    ref_json = canonical_json(ref_cards)
    print(f"reference assemble(): {len(ref_cards)} cards "
          f"(expect {len(base)-1} after dedup)")

    rng = random.Random(20260817)
    mismatches = 0
    distinct = {ref_json}
    t0 = time.time()
    for trial in range(args.trials):
        shuffled = copy.deepcopy(base)
        rng.shuffle(shuffled)
        cards = assemble(shuffled)
        j = canonical_json(cards)
        distinct.add(j)
        if j != ref_json:
            mismatches += 1
            if mismatches <= 3:
                print(f"  MISMATCH at trial {trial}")
    dt = time.time() - t0

    print(f"trials={args.trials} mismatches={mismatches} "
          f"distinct_outputs={len(distinct)} ({dt:.2f}s)")
    if mismatches == 0 and len(distinct) == 1:
        print("PASS: assembly output is byte-identical across "
              f"{args.trials} input-order shuffles.")
        sys.exit(0)
    else:
        print("FAIL: assembly output depends on input order.")
        sys.exit(1)


if __name__ == "__main__":
    main()
