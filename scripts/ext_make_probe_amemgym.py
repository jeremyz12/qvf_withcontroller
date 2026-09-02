# -*- coding: utf-8 -*-
"""AMemGym 探针采样器(批 33-G2 预注册,seed=33 写死)。

从 data/external/amemgym_unified.json 的 2,200 个 (question, period) 对里抽 600:
**按用户 x 周期双重分层**——20 个 persona 每人恰 30 题;每人 11 个周期先各 2 题,
再随机挑 8 个周期各 +1 题(20 x (11*2 + 8) = 600)。每个 (persona, period) 格内
在 10 道 qas 里无放回抽取。簇 = persona(20 簇),与判据 G 的簇自助 CI 对齐。

产物:
  data/external/amemgym_probe.jsonl     600 题(uid/qid/qtype/question/gold/cutoff/meta)
  data/external/amemgym_cardable.json   20 店(加 load_stale_chain 需要的
                                        chain / probing_queries 占位)
用法: python scripts/ext_make_probe_amemgym.py
"""
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"
SEED = 33
N_PER_USER = 30
BASE_PER_CELL = 2

rng = random.Random(SEED)


def last_date(store):
    for s in reversed(store.get("sessions", [])):
        if s.get("date"):
            return s["date"]
    raise AssertionError(f"{store['uid']}: no dated session")


def main():
    stores = json.loads((EXT / "amemgym_unified.json").read_text(encoding="utf-8"))
    rows = []
    for st in stores:
        by_period = {}
        for q in st["questions"]:
            by_period.setdefault(q["meta"]["period_index"], []).append(q)
        periods = sorted(by_period)
        n_extra = N_PER_USER - BASE_PER_CELL * len(periods)
        assert 0 <= n_extra <= len(periods), (st["uid"], n_extra)
        extra = set(rng.sample(periods, n_extra))
        for pi in periods:
            pool = sorted(by_period[pi], key=lambda q: q["qid"])
            k = BASE_PER_CELL + (1 if pi in extra else 0)
            for q in rng.sample(pool, k):
                rows.append({
                    "uid": st["uid"], "qid": q["qid"], "qtype": q["dim"],
                    "question": q["question"], "gold": q["gold"],
                    "cutoff": q["cutoff"], "meta": q["meta"],
                })

    rows.sort(key=lambda r: r["qid"])
    assert len(rows) == 600, len(rows)
    assert len({r["qid"] for r in rows}) == 600
    per_user = Counter(r["uid"] for r in rows)
    assert set(per_user.values()) == {N_PER_USER}, per_user

    # 建卡店:全部 20 店(题是分层子样,店不裁)
    for st in stores:
        st["chain"] = [{"date": last_date(st), "value": ""}]
        st["probing_queries"] = {"_placeholder": {"q": "placeholder", "gold": ""}}
    (EXT / "amemgym_cardable.json").write_text(
        json.dumps(stores, ensure_ascii=False), encoding="utf-8")
    with open(EXT / "amemgym_probe.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    chars = sum(len(t) for st in stores for s in st["sessions"] for t in s["turns"])
    per_period = Counter(r["meta"]["period_index"] for r in rows)
    print(f"amemgym: {len(stores)} stores, {len(rows)} questions, "
          f"card-build chars {chars:,}")
    print("per-user:", dict(sorted(per_user.items()))["amemgym-00"], "(all equal)")
    print("per-period:", dict(sorted(per_period.items())))
    print("choices/question:", dict(Counter(r["meta"]["n_choices"] for r in rows)))


if __name__ == "__main__":
    main()
