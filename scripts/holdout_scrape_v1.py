# -*- coding: utf-8 -*-
"""批 33-C 冻结保留集·步骤1:拉取**从未碰过**的 Wikidata 候选实体。

与 scripts/wikistate_scrape.py 同一**本地过滤规则**(sitelinks ≤ 5;带 P580+P582
的段值去重后 ≥ 3;链按 start 排序),只把"候选发现"从搜索 API 分页换成 WDQS:
搜索 API 按相关度排序 = 名人优先,前数千个 offset 命中率近零(实测 P54/P551
六分钟零命中);WDQS 直接给出"有 ≥3 个带起止日期的不同值"的实体集合。
链本身仍由 Special:EntityData 逐实体解析,时间串保留 Wikidata 原精度
(年/月精度的 `-00` 段与开发场语料一致)。

排除集 = 仓库内出现过的全部 QID(144 链 uid、L1/L2、历史 items/full/candidates)。

用法:python scripts/holdout_scrape_v1.py P551 14
产物:data/holdout_candidates_<PROP>.json
"""
import glob
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WDQS = "https://query.wikidata.org/sparql"

PROP = sys.argv[1] if len(sys.argv) > 1 else "P39"
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 40
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
OUT = ROOT / f"data/holdout_candidates_{PROP}.json"

MAX_SITELINKS = 5   # 与 wikistate_scrape.py 逐字一致(低知名度闸)
MIN_CHAIN = 3


def known_qids() -> set:
    qids = set()
    pats = ["data/wikistate_full*.json", "data/wikistate_items*.json",
            "data/wikistate_long_*.json", "data/wikistate_v3*.json",
            "data/wikistate_rel30.json", "data/wikistate_candidates*.json"]
    for pat in pats:
        for p in glob.glob(str(ROOT / pat)):
            try:
                d = json.loads(Path(p).read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(d, list):
                continue
            for e in d:
                if not isinstance(e, dict):
                    continue
                for k in ("uid", "qid"):
                    v = e.get(k)
                    if isinstance(v, str):
                        qids.update(re.findall(r"Q\d+", v))
    return qids


def sparql(q, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(WDQS, params={"query": q, "format": "json"},
                             headers={**UA,
                                      "Accept": "application/sparql-results+json"},
                             timeout=170)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:200]}"
        print(f"WDQS retry {i}: {last}", flush=True)
        time.sleep(8)
    raise RuntimeError(f"WDQS FAILED: {last}")


def discover():
    """路线 A(首选):WDQS 直接给"有 ≥3 个带起止日期的不同值"的实体。
    对 P551 这类限定语句量小的属性 13 秒返回;P108/P39/P54 的全局 GROUP BY
    在公共端点必 504(实测三次,含降 LIMIT / 加内层 LIMIT 子查询)。
    路线 B(回退):搜索 API `srsort=random` 随机抽样 —— 绕开相关度排序的
    "名人优先"偏置(实测 offset 0-150 命中率近零),随机样命中率 ≈7.5%。
    两条路线只负责**发现候选**,链的解析与过滤仍走 EntityData + 本地规则。"""
    try:
        q = f"""SELECT ?item (COUNT(DISTINCT ?v) AS ?n) WHERE {{
  ?item p:{PROP} ?st .
  ?st ps:{PROP} ?v ; pq:P580 ?s ; pq:P582 ?e .
}} GROUP BY ?item HAVING(COUNT(DISTINCT ?v) >= {MIN_CHAIN}) LIMIT {LIMIT}"""
        rows = sparql(q, tries=2)
        print(f"discovery route = WDQS ({len(rows)} rows)", flush=True)
        return [b["item"]["value"].rsplit("/", 1)[1] for b in rows], "wdqs"
    except RuntimeError as e:
        print(f"WDQS unavailable for {PROP} ({e}); falling back to "
              f"search API srsort=random", flush=True)
    seen, order = set(), []
    SEARCH = "https://www.wikidata.org/w/api.php"
    for _ in range(LIMIT // 50 + 1):
        try:
            r = requests.get(SEARCH, params={
                "action": "query", "list": "search", "format": "json",
                "srsearch": f"haswbstatement:{PROP}", "srnamespace": 0,
                "srlimit": 50, "srsort": "random"}, headers=UA, timeout=40)
            for h in r.json().get("query", {}).get("search", []):
                if h["title"] not in seen:
                    seen.add(h["title"])
                    order.append(h["title"])
        except Exception as ex:  # noqa: BLE001
            print(f"search retry: {type(ex).__name__}", flush=True)
            time.sleep(3)
        time.sleep(0.2)
    print(f"discovery route = search/random ({len(order)} ids)", flush=True)
    return order, "search_random"


def sitelinks_of(qids):
    out = {}
    for i in range(0, len(qids), 200):
        chunk = qids[i:i + 200]
        vals = " ".join(f"wd:{q}" for q in chunk)
        q = f"SELECT ?item ?sl WHERE {{ VALUES ?item {{ {vals} }} " \
            f"?item wikibase:sitelinks ?sl . }}"
        for b in sparql(q):
            out[b["item"]["value"].rsplit("/", 1)[1]] = int(b["sl"]["value"])
        time.sleep(0.3)
    return out


def dated_chain(claims):
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
    excl = known_qids()
    print(f"exclusion set: {len(excl)} QIDs", flush=True)
    ids, route = discover()
    pool = [q for q in ids if q not in excl]
    print(f"discovered (after exclusion): {len(pool)} via {route}", flush=True)
    if route == "wdqs":   # WDQS 路线先批量拿 sitelinks,省掉大量 EntityData
        sl = sitelinks_of(pool)
        pool = [q for q in pool if sl.get(q, 99) <= MAX_SITELINKS]
        print(f"after sitelinks<={MAX_SITELINKS}: {len(pool)}", flush=True)

    candidates = []
    API = "https://www.wikidata.org/w/api.php"
    for bi in range(0, len(pool), 25):
        if len(candidates) >= TARGET:
            break
        batch = pool[bi:bi + 25]
        ents = {}
        for _ in range(3):
            try:
                r = requests.get(API, params={
                    "action": "wbgetentities", "ids": "|".join(batch),
                    "props": "claims|labels|sitelinks", "languages": "en",
                    "format": "json"}, headers=UA, timeout=90)
                ents = r.json().get("entities", {})
                break
            except Exception as ex:  # noqa: BLE001
                print(f"wbgetentities retry: {type(ex).__name__}", flush=True)
                time.sleep(3)
        for qid in batch:
            if len(candidates) >= TARGET:
                break
            ent = ents.get(qid)
            if not isinstance(ent, dict) or "claims" not in ent:
                continue
            n_sl = len(ent.get("sitelinks", {}))
            if n_sl > MAX_SITELINKS:
                continue
            chain = dated_chain(ent.get("claims", {}))
            vals, dedup = [], []
            for c in chain:
                if c["position"] not in vals:
                    vals.append(c["position"])
                    dedup.append(c)
            if len(dedup) < MIN_CHAIN:
                continue
            label = ent.get("labels", {}).get("en", {}).get("value", qid)
            if re.fullmatch(r"Q\d+", label):
                continue
            candidates.append({"qid": qid, "label": label, "sitelinks": n_sl,
                               "chain": dedup})
            print(f"[{len(candidates):3d}] {qid} {label} sl={n_sl} "
                  f"chain={len(dedup)}", flush=True)
            OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=1),
                           encoding="utf-8")   # 增量落盘,可随时叫停
        time.sleep(0.2)
    OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"candidates={len(candidates)} -> {OUT}")


if __name__ == "__main__":
    main()
