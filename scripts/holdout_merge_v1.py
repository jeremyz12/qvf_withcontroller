# -*- coding: utf-8 -*-
"""批 33-C:合并四个分槽位渲染分片 → data/wikistate_holdout_v1.json,并复核双闸。

闸1 锚点:每条链的 state_span 必须逐字出现在该链会话里(542 锚口径同法)。
闸2 污染:pool_verdicts / v23_residual 里任一 CONFIRMED 逐字引文都不得出现在
        填充会话里(批 31 构造规范第 4 条"复扫后残余为零")。
另报:与既有 144 链 / L1 / L2 的 uid 与 QID 交集(须为零)、链长直方图、槽位分布。
"""
import collections
import glob
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/wikistate_holdout_v1.json"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def main():
    parts = sorted(glob.glob(str(ROOT / "data/holdout_part_*.json")))
    out, seen = [], set()
    for p in parts:
        for e in json.loads(Path(p).read_text(encoding="utf-8")):
            if e["uid"] in seen:
                continue
            seen.add(e["uid"])
            out.append(e)
    out.sort(key=lambda e: e["uid"])
    print(f"merged {len(out)} chains from {len(parts)} parts")

    verdicts = json.loads((ROOT / "results/pool_verdicts.json")
                          .read_text(encoding="utf-8"))
    quotes = [x["quote"] for x in verdicts
              if x["verdict"] == "CONFIRMED" and x.get("quote")]
    quotes += [x["quote_head"] for x in
               json.loads((ROOT / "results/v23_residual_verdicts.json")
                          .read_text(encoding="utf-8"))
               if x["verdict"] == "CONFIRMED"]

    bad_anchor = bad_quote = 0
    for e in out:
        blob = norm(json.dumps(e["sessions"], ensure_ascii=False))
        for c in e["chain"]:
            if norm(c["state_span"]) not in blob:
                print(f"闸1违例 锚丢失: {e['uid']}")
                bad_anchor += 1
        fill = norm(json.dumps([s for s in e["sessions"]
                                if s["chain_index"] is None],
                               ensure_ascii=False))
        for q in quotes:
            qq = norm(q)[:60]
            if len(qq) >= 20 and qq in fill:
                print(f"闸2违例 污染残留: {e['uid']} :: {q[:60]}")
                bad_quote += 1

    # 零交集核验
    old = set()
    for pat in ["data/wikistate_full*.json", "data/wikistate_long_*.json"]:
        for p in glob.glob(str(ROOT / pat)):
            try:
                d = json.loads(Path(p).read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d, list):
                for e in d:
                    if isinstance(e, dict) and isinstance(e.get("uid"), str):
                        old.update(re.findall(r"Q\d+", e["uid"]))
    newq = {e["uid"].split("-", 1)[1] for e in out}
    inter = newq & old
    n_anchor = sum(len(e["chain"]) for e in out)
    hist = collections.Counter(len(e["chain"]) for e in out)
    slots = collections.Counter(e["slot"] for e in out)
    sess = collections.Counter(len(e["sessions"]) for e in out)
    print(f"闸1 锚点 {n_anchor - bad_anchor}/{n_anchor} 逐字完好;闸2 污染残留 {bad_quote}")
    print(f"与既有语料 QID 交集: {len(inter)} {sorted(inter)[:5]}")
    print(f"槽位: {dict(slots)}")
    print(f"链长直方图: {dict(sorted(hist.items()))}")
    print(f"会话数分布: {dict(sorted(sess.items()))}")
    if bad_anchor or bad_quote or inter or len(out) != 40:
        print("ABORT — 未写出")
        return
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"WROTE {OUT} ({len(out)} chains)\nsha256={sha}")


if __name__ == "__main__":
    main()
