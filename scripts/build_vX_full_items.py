# -*- coding: utf-8 -*-
"""全量评审题目生成器(通用版,2026-09-03):任意语料版本 → 全部链 + 5 道植入对照题,N 位评审同题同序。
相对 build_v24_full_items 修了两处对照题泄漏:
  (1) raw 框按**植入后的链**高亮锚句(伪造锚句不会被高亮、删行后高亮数不多于行数);
  (2) 对照题 id 与普通题同形(接在 001…144 之后,如 145…149),顺序打乱后不可凭 id 识别。
用法:python scripts/build_vX_full_items.py --data data/wikistate_full_ALL_v25.json --tag v25 --names reviewer-v25,opus5-agent-v25 --seed 2509
产物:data/<tag>full_payload.json(灌入 rate.db)与 data/<tag>full_keymap.json(答案键,不上线)。
"""
import argparse, json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_round2_items import chain_table, raw_box, inject  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--names", required=True, help="comma-separated rater names")
    ap.add_argument("--seed", type=int, default=2509)
    a = ap.parse_args()
    data = {e["uid"]: e for e in json.loads((ROOT / a.data).read_text(encoding="utf-8"))}
    uids = sorted(data)
    rng = random.Random(a.seed)
    catch_pool = rng.sample(uids, 5)
    kinds = ["value_swap", "date_shift", "delete_row", "fabricate_anchor", "add_row"]
    items, keymap = [], {}
    for n, uid in enumerate(uids, 1):
        e = data[uid]
        iid = f"{a.tag}-{n:03d}"
        items.append({"id": iid, "slot": e["slot"], "chain_html": chain_table(e["chain"]),
                      "raw_html": raw_box(e, e["chain"])})
        keymap[iid] = {"uid": uid, "catch": False, "injection": None, "group": a.tag}
    for k, (uid, kind) in enumerate(zip(catch_pool, kinds), 1):
        e = data[uid]
        rows, desc = inject(e["chain"], kind, rng)
        iid = f"{a.tag}-{len(uids) + k:03d}"  # 同形 id
        items.append({"id": iid, "slot": e["slot"], "chain_html": chain_table(rows),
                      "raw_html": raw_box(e, rows)})  # 按植入后的链高亮
        keymap[iid] = {"uid": uid, "catch": True, "injection": desc, "group": "catch"}
    order = [i["id"] for i in items]
    rng.shuffle(order)
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raters = [{"token": a.tag + "".join(rng.choice(alphabet) for _ in range(13)), "name": nm.strip(), "items": order}
              for nm in a.names.split(",")]
    (ROOT / f"data/{a.tag}full_payload.json").write_text(json.dumps({"items": items, "raters": raters}, ensure_ascii=False), encoding="utf-8")
    (ROOT / f"data/{a.tag}full_keymap.json").write_text(json.dumps(keymap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"题目 {len(items)}({a.tag} 全部 {len(uids)} 链 + 植入 5;对照题 id 同形)")
    for r in raters:
        print(f"  {r['name']}: /r/{r['token']}")


if __name__ == "__main__":
    main()
