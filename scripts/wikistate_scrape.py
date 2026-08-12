# -*- coding: utf-8 -*-
"""WikiState 试点·步骤1:拉取候选实体(任职链≥3段且带起止日期、低知名度)。

路线:Wikidata 搜索 API(haswbstatement:P39)分页 → 逐实体 EntityData →
本地过滤(≥3 条带 P580+P582 的 P39;sitelinks ≤ 5)→ 存候选池。
公共 SPARQL 端点重查询超时,此路线全部为轻量请求。"""
import json
import time
from pathlib import Path

import requests

import sys as _sys

UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
SEARCH = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

PROP = _sys.argv[1] if len(_sys.argv) > 1 else "P39"   # P39 任职 / P54 队籍 / P108 雇主 / P551 居住地
TARGET = int(_sys.argv[2]) if len(_sys.argv) > 2 else 80
OUT = Path(rf"D:\ZZL_cluade\data\wikistate_candidates_{PROP}.json")

MAX_SITELINKS = 5
MIN_CHAIN = 3


def dated_p39(claims):
    out = []
    for st in claims.get(PROP, []):
        try:
            q = st.get("qualifiers", {})
            start = q["P580"][0]["datavalue"]["value"]["time"]
            end = q["P582"][0]["datavalue"]["value"]["time"]
            val = st["mainsnak"]["datavalue"]["value"]["id"]
            out.append({"position": val, "start": start[1:11], "end": end[1:11]})
        except Exception:
            continue
    return sorted(out, key=lambda x: x["start"])


def main():
    candidates = []
    seen = set()
    offset = 0
    scanned = 0
    while len(candidates) < TARGET and offset < 5000:
        r = requests.get(SEARCH, params={
            "action": "query", "list": "search", "format": "json",
            "srsearch": f"haswbstatement:{PROP}", "srnamespace": 0,
            "srlimit": 50, "sroffset": offset}, headers=UA, timeout=30)
        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            break
        offset += 50
        for h in hits:
            qid = h["title"]
            if qid in seen or not qid.startswith("Q"):
                continue
            seen.add(qid)
            scanned += 1
            try:
                er = requests.get(ENTITY.format(qid=qid), headers=UA, timeout=30)
                ent = er.json()["entities"][qid]
            except Exception:
                continue
            sl = len(ent.get("sitelinks", {}))
            if sl > MAX_SITELINKS:
                continue
            chain = dated_p39(ent.get("claims", {}))
            # 链内值去重后仍需 ≥ MIN_CHAIN,且日期严格可排序
            vals = []
            dedup = []
            for c in chain:
                if c["position"] not in vals:
                    vals.append(c["position"])
                    dedup.append(c)
            if len(dedup) < MIN_CHAIN:
                continue
            label = ent.get("labels", {}).get("en", {}).get("value", qid)
            candidates.append({"qid": qid, "label": label, "sitelinks": sl,
                               "chain": dedup})
            print(f"[{len(candidates):3d}] {qid} {label} sl={sl} chain={len(dedup)}",
                  flush=True)
            time.sleep(0.15)
        time.sleep(0.3)
    OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"scanned={scanned} candidates={len(candidates)} -> {OUT}")


if __name__ == "__main__":
    main()
