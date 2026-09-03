# -*- coding: utf-8 -*-
"""v2.4 全量评审题目生成器(2026-09-03,用户令):从 v2.4 净化语料生成全部 144 条链
+ 5 道全新植入对照题 = 149 题;两位新评审(名字与前两轮区分),同一套题同一顺序 → 可算 κ。
产物 data/v24full_payload.json(灌入 rate.db)与 data/v24full_keymap.json(答案键,不上线)。
复用 build_round2_items 的渲染与植入函数,逐字同款界面。
"""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_round2_items import chain_table, raw_box, inject  # noqa: E402

RATER_NAMES = ("reviewerA-v24", "reviewerB-v24")


def main():
    data = {e["uid"]: e for e in json.loads(
        (ROOT / "data/wikistate_full_ALL_v24.json").read_text(encoding="utf-8"))}
    uids = sorted(data)
    rng = random.Random(2409)
    catch_pool = rng.sample(uids, 5)
    kinds = ["value_swap", "date_shift", "delete_row", "fabricate_anchor", "add_row"]
    items, keymap = [], {}
    for n, uid in enumerate(uids, 1):
        e = data[uid]
        iid = f"v24-{n:03d}"
        items.append({"id": iid, "slot": e["slot"],
                      "chain_html": chain_table(e["chain"]),
                      "raw_html": raw_box(e, e["chain"])})
        keymap[iid] = {"uid": uid, "catch": False, "injection": None, "group": "v24"}
    for k, (uid, kind) in enumerate(zip(catch_pool, kinds), 1):
        e = data[uid]
        rows, desc = inject(e["chain"], kind, rng)
        iid = f"v24-c{k:02d}"
        items.append({"id": iid, "slot": e["slot"],
                      "chain_html": chain_table(rows),
                      "raw_html": raw_box(e, e["chain"])})
        keymap[iid] = {"uid": uid, "catch": True, "injection": desc, "group": "catch"}
    order = [i["id"] for i in items]
    rng.shuffle(order)
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raters = [{"token": "v24" + "".join(rng.choice(alphabet) for _ in range(13)),
               "name": nm, "items": order} for nm in RATER_NAMES]
    (ROOT / "data/v24full_payload.json").write_text(json.dumps(
        {"items": items, "raters": raters}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/v24full_keymap.json").write_text(json.dumps(keymap, ensure_ascii=False,
                                                              indent=1), encoding="utf-8")
    print(f"题目 {len(items)}(v2.4 全部 {len(uids)} 链 + 植入 5)")
    for r in raters:
        print(f"  {r['name']}: /r/{r['token']}")


if __name__ == "__main__":
    main()
