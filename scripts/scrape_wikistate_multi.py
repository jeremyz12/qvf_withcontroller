# -*- coding: utf-8 -*-
"""WikiState S6 跨槽位 join·步骤1:多属性候选实体抓取(WDQS SPARQL)。

目标:S6 跨槽位 join 题需要同一人身上同时有 >=2 个属性(P39 任职 / P108
雇主 / P54 队籍 / P551 居住地),且每条属性链各有 >=3 条带开始时间限定符
(P580 起始时间 或 P585 时间点)的陈述。原单属性路线
(scripts/wikistate_scrape.py:搜索 API + EntityData 逐实体过滤)对这种
交集条件命中率过低,改走 https://query.wikidata.org/sparql 聚合一次筛出。

模式(互斥):
  --probe   只跑实体统计查询(带 LIMIT),打印命中计数,不写文件;
  --fetch   实体查询 + 逐人明细查询,组装候选记录并写 json;
  --smoke   零网络自检:SPARQL 字符串级语法检查 + 罐头 SPARQL JSON 响应
            的组装冒烟 + 与 wikistate_scrape.py 的 UA/常量逐字一致断言。

候选记录 schema 与既有 data/wikistate_candidates*.json 对齐:人级
{"qid","label","sitelinks"} 与链步骤 {"position","start","end"} 布局逐字
沿用(P551/P54/P108 的链步骤在既有文件里同样用 "position" 键);多属性版
新增三键:"uid"(wikiM###-Q…,沿用 wikistate_render 的
wiki{PROP}{i:03d}-{qid} 命名族,M = multi)、"props"(属性对)、
"chains"(按属性分组,值为既有链布局)。仅要求开始时间限定符,故 "end"
无 P582 时为 null(既有单属性线强制 P580+P582,此处口径按 S6 放宽)。

低知名度偏好沿用原线:sitelinks <= MAX_SITELINKS 过滤 + sitelinks 升序
(SPARQL ORDER BY ASC + 本地再排,uid 序号即该序)。

礼貌抓取:全部请求 1 次 / 2 秒 + 学术 UA。SPARQL 返回的日期是规约后的
完整日期(部分日期如 2014-00-00 会变成 2014-01-01),下游
parse_partial_date 两种形态都吃,无碍。

UA / MAX_SITELINKS / MIN_CHAIN 与 scripts/wikistate_scrape.py 逐字一致
(复制而非导入:该脚本模块级读 sys.argv 定属性,导入会吃掉本脚本参数;
--smoke 以 ast 解析其源码断言等价,同 complex_query_arm 对 SLOT_ALIASES
的处理)。

用法:
  python scripts/scrape_wikistate_multi.py --probe --props P108,P551 --limit 50
  python scripts/scrape_wikistate_multi.py --fetch --props P39,P108 --limit 50 \
      [--out data/wikistate_candidates_multi_P39_P108.json]
  python scripts/scrape_wikistate_multi.py --smoke
"""
import argparse
import ast
import json
import re
import time
from pathlib import Path

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
# ── 与 scripts/wikistate_scrape.py 逐字一致(复制而非导入;--smoke 断言)──
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
MAX_SITELINKS = 5
MIN_CHAIN = 3
# ──────────────────────────────────────────────────────────────
RATE_SECONDS = 2.0        # WDQS 礼貌间隔:1 请求 / 2 秒
ALLOWED_PROPS = ("P39", "P108", "P54", "P551")

_UID_RE = re.compile(r"wikiM\d{3}-Q\d+")


# ── SPARQL 文本构造 ──────────────────────────────────────────
def entity_query(pa: str, pb: str, limit: int) -> str:
    """实体统计查询:人(Q5)+ 双属性各 >=MIN_CHAIN 条带开始时间限定符
    (P580/P585)的陈述 + 低知名度(sitelinks <= MAX_SITELINKS,升序)。"""
    return f"""SELECT ?person ?sitelinks (SAMPLE(?lbl) AS ?label)
       (COUNT(DISTINCT ?stA) AS ?nA) (COUNT(DISTINCT ?stB) AS ?nB) WHERE {{
  ?person wdt:P31 wd:Q5 ;
          wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks <= {MAX_SITELINKS})
  ?person p:{pa} ?stA .
  {{ ?stA pq:P580 ?dA }} UNION {{ ?stA pq:P585 ?dA }}
  ?person p:{pb} ?stB .
  {{ ?stB pq:P580 ?dB }} UNION {{ ?stB pq:P585 ?dB }}
  OPTIONAL {{ ?person rdfs:label ?lbl . FILTER(LANG(?lbl) = "en") }}
}}
GROUP BY ?person ?sitelinks
HAVING ((COUNT(DISTINCT ?stA) >= {MIN_CHAIN}) && (COUNT(DISTINCT ?stB) >= {MIN_CHAIN}))
ORDER BY ASC(?sitelinks)
LIMIT {int(limit)}"""


def detail_query(qid: str, prop: str) -> str:
    """单人单属性明细:全部带开始时间限定符的陈述(值 + start + 可选 end)。"""
    return f"""SELECT ?value ?start ?end WHERE {{
  wd:{qid} p:{prop} ?st .
  ?st ps:{prop} ?value .
  {{ ?st pq:P580 ?start }} UNION {{ ?st pq:P585 ?start }}
  OPTIONAL {{ ?st pq:P582 ?end }}
}}"""


# ── 网络层(--probe/--fetch 才会走到;--smoke 全程不触碰)──────
_LAST_REQ = [0.0]


def _throttle():
    wait = RATE_SECONDS - (time.monotonic() - _LAST_REQ[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_REQ[0] = time.monotonic()


def sparql(query: str) -> dict:
    _throttle()
    r = requests.get(ENDPOINT, params={"query": query, "format": "json"},
                     headers=UA, timeout=120)
    r.raise_for_status()
    return r.json()


# ── SPARQL JSON → 候选记录组装(纯函数,罐头响应可冒烟)────────
def _bind(row: dict, var: str):
    b = row.get(var)
    return b.get("value") if isinstance(b, dict) else None


def _tail_qid(uri: str) -> str:
    return str(uri).rsplit("/", 1)[-1]


def _short_date(t: str) -> str:
    """'1979-10-01T00:00:00Z' / '+1979-10-01…' → '1979-10-01'(同原线
    start[1:11] 的取头十位口径,SPARQL 侧无 '+' 前缀则直接取)。"""
    return str(t).lstrip("+")[:10]


def assemble_chain(rows) -> list:
    """明细行 → 链:按 start 排序后按值去重(保首见),同原线
    dated_p39 + 去重逻辑;end 缺失(无 P582)记 null。"""
    steps = []
    for row in rows:
        val, start = _bind(row, "value"), _bind(row, "start")
        if not val or not start:
            continue
        end = _bind(row, "end")
        steps.append({"position": _tail_qid(val), "start": _short_date(start),
                      "end": _short_date(end) if end else None})
    steps.sort(key=lambda s: s["start"])
    vals, dedup = [], []
    for s in steps:
        if s["position"] not in vals:
            vals.append(s["position"])
            dedup.append(s)
    return dedup


def assemble_candidates(entity_rows, details, props) -> list:
    """实体行 + 明细响应 → 候选记录列表(本地复核每条链去重后仍
    >= MIN_CHAIN;sitelinks 升序;uid = wikiM{序号:03d}-{qid})。

    details: {qid: {prop: bindings 行列表}}。
    """
    base = []
    for row in entity_rows:
        qid = _tail_qid(_bind(row, "person") or "")
        if not qid.startswith("Q") or qid not in details:
            continue
        chains = {}
        for p in props:
            chain = assemble_chain(details[qid].get(p, []))
            if len(chain) < MIN_CHAIN:
                chains = None
                break
            chains[p] = chain
        if chains is None:
            continue
        label = _bind(row, "label") or qid
        sl = int(_bind(row, "sitelinks") or 0)
        base.append({"qid": qid, "label": label, "sitelinks": sl,
                     "chains": chains})
    base.sort(key=lambda c: (c["sitelinks"], c["qid"]))
    out = []
    for i, c in enumerate(base):
        out.append({"uid": f"wikiM{i:03d}-{c['qid']}", "qid": c["qid"],
                    "label": c["label"], "sitelinks": c["sitelinks"],
                    "props": list(props), "chains": c["chains"]})
    return out


# ── --probe ──────────────────────────────────────────────────
def run_probe(pa: str, pb: str, limit: int):
    rows = sparql(entity_query(pa, pb, limit))["results"]["bindings"]
    sls = [int(_bind(r, "sitelinks") or 0) for r in rows]
    n_label = sum(1 for r in rows if _bind(r, "label"))
    n_full = sum(1 for r in rows
                 if int(_bind(r, "nA") or 0) >= MIN_CHAIN
                 and int(_bind(r, "nB") or 0) >= MIN_CHAIN)
    print(f"probe {pa}+{pb} LIMIT {limit}: persons={len(rows)} "
          f"chains_ok={n_full} en_label={n_label} "
          f"sitelinks_min={min(sls) if sls else '-'} "
          f"sitelinks_max={max(sls) if sls else '-'}")


# ── --fetch ──────────────────────────────────────────────────
def run_fetch(pa: str, pb: str, limit: int, out_path: Path):
    rows = sparql(entity_query(pa, pb, limit))["results"]["bindings"]
    print(f"entity query: {len(rows)} persons, fetching details "
          f"(2 queries/person, {RATE_SECONDS}s apart)...", flush=True)
    details = {}
    for i, row in enumerate(rows):
        qid = _tail_qid(_bind(row, "person") or "")
        if not qid.startswith("Q"):
            continue
        try:
            details[qid] = {p: sparql(detail_query(qid, p))["results"]["bindings"]
                            for p in (pa, pb)}
        except Exception as e:  # noqa: BLE001 —— 单人失败不拖垮整批,同原线
            print(f"[{i + 1}/{len(rows)}] {qid} SKIP {type(e).__name__}",
                  flush=True)
            continue
        print(f"[{i + 1}/{len(rows)}] {qid} fetched", flush=True)
    cands = assemble_candidates(rows, details, (pa, pb))
    for c in cands:
        sizes = "+".join(str(len(c["chains"][p])) for p in (pa, pb))
        print(f"[{c['uid']}] {c['qid']} {c['label']} sl={c['sitelinks']} "
              f"chains={sizes}", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cands, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"persons={len(rows)} candidates={len(cands)} -> {out_path}")


# ── --smoke:零网络自检 ──────────────────────────────────────
def _check_sparql(q: str, required) -> list:
    """字符串级语法检查:括号配平(且运行余额不为负)、引号成对、
    必需 token 在场。"""
    errs = []
    for a, b in (("{", "}"), ("(", ")")):
        bal = 0
        for ch in q:
            bal += (ch == a) - (ch == b)
            if bal < 0:
                errs.append(f"negative balance for {a}{b}")
                break
        if bal > 0:
            errs.append(f"unbalanced {a}{b}")
    if q.count('"') % 2:
        errs.append("unbalanced double quotes")
    for tok in required:
        if tok not in q:
            errs.append(f"missing token: {tok}")
    return errs


def _scrape_consts() -> dict:
    """ast 解析 wikistate_scrape.py 源码提取 UA/MAX_SITELINKS/MIN_CHAIN
    (不导入 —— 该模块级读 sys.argv)。"""
    src = (Path(__file__).resolve().parent / "wikistate_scrape.py"
           ).read_text(encoding="utf-8")
    out = {}
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("UA", "MAX_SITELINKS", "MIN_CHAIN")):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def _lit(value: str, **extra) -> dict:
    return {"type": "literal", "value": value, **extra}


def _ent(qid: str) -> dict:
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}


# 罐头 SPARQL JSON 响应(与 WDQS application/sparql-results+json 同构)。
# Q900001:无英文标签(label 回落 qid)、P585 起始、乱序日期、end 缺失、
#          '+' 前缀日期、同值重复行 —— 全部组装路径都踩到;
# Q900002:常规三段链;
# Q900003:P551 三条陈述仅 2 个不同值,本地复核应整人淘汰。
_FIX_PA, _FIX_PB = "P108", "P551"
FIXTURE_ENTITY = {"results": {"bindings": [
    {"person": _ent("Q900002"), "sitelinks": _lit("4"),
     "label": _lit("Bea Example", **{"xml:lang": "en"}),
     "nA": _lit("3"), "nB": _lit("3")},
    {"person": _ent("Q900001"), "sitelinks": _lit("1"),
     "nA": _lit("4"), "nB": _lit("3")},
    {"person": _ent("Q900003"), "sitelinks": _lit("0"),
     "label": _lit("Cody Dropcase", **{"xml:lang": "en"}),
     "nA": _lit("3"), "nB": _lit("3")},
]}}
FIXTURE_DETAILS = {
    "Q900001": {
        "P108": [
            {"value": _ent("Q42944"), "start": _lit("2019-02-01T00:00:00Z"),
             "end": _lit("2020-02-01T00:00:00Z")},
            {"value": _ent("Q501758"), "start": _lit("+2014-05-01T00:00:00Z"),
             "end": _lit("2018-12-01T00:00:00Z")},
            {"value": _ent("Q501758"), "start": _lit("2014-05-01T00:00:00Z"),
             "end": _lit("2018-12-01T00:00:00Z")},   # P580+P585 双限定重复行
            {"value": _ent("Q337641"), "start": _lit("2015-09-15T00:00:00Z")},
        ],
        "P551": [
            {"value": _ent("Q55"), "start": _lit("1991-01-20T00:00:00Z"),
             "end": _lit("2004-03-01T00:00:00Z")},
            {"value": _ent("Q142"), "start": _lit("2004-03-01T00:00:00Z")},
            {"value": _ent("Q145"), "start": _lit("2007-03-01T00:00:00Z")},
        ],
    },
    "Q900002": {
        "P108": [
            {"value": _ent("Q1"), "start": _lit("2001-01-01T00:00:00Z"),
             "end": _lit("2002-01-01T00:00:00Z")},
            {"value": _ent("Q2"), "start": _lit("2002-01-01T00:00:00Z"),
             "end": _lit("2003-01-01T00:00:00Z")},
            {"value": _ent("Q3"), "start": _lit("2003-01-01T00:00:00Z")},
        ],
        "P551": [
            {"value": _ent("Q60"), "start": _lit("2000-06-01T00:00:00Z")},
            {"value": _ent("Q64"), "start": _lit("2005-06-01T00:00:00Z")},
            {"value": _ent("Q84"), "start": _lit("2010-06-01T00:00:00Z")},
        ],
    },
    "Q900003": {
        "P108": [
            {"value": _ent("Q10"), "start": _lit("2001-01-01T00:00:00Z")},
            {"value": _ent("Q11"), "start": _lit("2002-01-01T00:00:00Z")},
            {"value": _ent("Q12"), "start": _lit("2003-01-01T00:00:00Z")},
        ],
        "P551": [   # 3 条陈述、仅 2 个不同值 → 去重后 2 < MIN_CHAIN,整人淘汰
            {"value": _ent("Q20"), "start": _lit("2001-01-01T00:00:00Z")},
            {"value": _ent("Q21"), "start": _lit("2002-01-01T00:00:00Z")},
            {"value": _ent("Q20"), "start": _lit("2003-01-01T00:00:00Z")},
        ],
    },
}


def run_smoke():
    # ① SPARQL 字符串级语法检查:全部无序属性对 + 全部单属性明细。
    n_q = 0
    for i, pa in enumerate(ALLOWED_PROPS):
        for pb in ALLOWED_PROPS[i + 1:]:
            q = entity_query(pa, pb, 50)
            errs = _check_sparql(q, [
                "SELECT", "wdt:P31 wd:Q5", "wikibase:sitelinks",
                f"FILTER(?sitelinks <= {MAX_SITELINKS})",
                f"p:{pa} ?stA", f"p:{pb} ?stB", "pq:P580", "pq:P585",
                "UNION", "GROUP BY", "HAVING", f">= {MIN_CHAIN}",
                "ORDER BY ASC(?sitelinks)", "LIMIT 50"])
            assert not errs, f"entity_query({pa},{pb}): {errs}"
            n_q += 1
    for p in ALLOWED_PROPS:
        q = detail_query("Q42", p)
        errs = _check_sparql(q, [
            "SELECT", f"wd:Q42 p:{p} ?st", f"ps:{p}", "pq:P580", "pq:P585",
            "UNION", "OPTIONAL", "pq:P582"])
        assert not errs, f"detail_query({p}): {errs}"
        n_q += 1

    # ② 罐头响应组装冒烟。
    cands = assemble_candidates(FIXTURE_ENTITY["results"]["bindings"],
                                FIXTURE_DETAILS, (_FIX_PA, _FIX_PB))
    assert [c["qid"] for c in cands] == ["Q900001", "Q900002"], \
        f"expected Q900003 dropped + sitelinks asc, got {[c['qid'] for c in cands]}"
    assert all(_UID_RE.fullmatch(c["uid"]) for c in cands), \
        f"uid pattern: {[c['uid'] for c in cands]}"
    assert cands[0]["uid"] == "wikiM000-Q900001"
    assert cands[1]["uid"] == "wikiM001-Q900002"
    assert cands[0]["label"] == "Q900001", "label fallback to qid"
    assert cands[1]["label"] == "Bea Example"
    assert [c["sitelinks"] for c in cands] == [1, 4], "sitelinks ascending"
    for c in cands:
        assert list(c.keys()) == ["uid", "qid", "label", "sitelinks",
                                  "props", "chains"]
        assert c["props"] == [_FIX_PA, _FIX_PB]
        for p in c["props"]:
            chain = c["chains"][p]
            assert len(chain) >= MIN_CHAIN
            starts = [s["start"] for s in chain]
            assert starts == sorted(starts), "chain sorted by start"
            assert all(list(s.keys()) == ["position", "start", "end"]
                       for s in chain), "step layout position/start/end"
    a = cands[0]["chains"]["P108"]
    assert [s["position"] for s in a] == ["Q501758", "Q337641", "Q42944"], \
        "sort + dedup keep-first"
    assert a[0]["start"] == "2014-05-01", "'+' prefix stripped, 10-char date"
    assert a[1]["end"] is None, "missing P582 -> null end"

    # ③ 与既有候选文件的链步骤布局逐字对齐(存在才查,离线安全)。
    ref = Path(__file__).resolve().parent.parent / "data" / \
        "wikistate_candidates.json"
    if ref.exists():
        ref_step = json.loads(ref.read_text(encoding="utf-8"))[0]["chain"][0]
        assert list(ref_step.keys()) == ["position", "start", "end"], \
            f"reference layout drifted: {list(ref_step.keys())}"

    # ④ UA/常量与 wikistate_scrape.py 逐字一致断言(复制而非导入)。
    consts = _scrape_consts()
    assert consts == {"UA": UA, "MAX_SITELINKS": MAX_SITELINKS,
                      "MIN_CHAIN": MIN_CHAIN}, f"const drift: {consts}"

    print(f"SMOKE OK: sparql_checked={n_q} fixture_candidates={len(cands)} "
          f"(1 dropped by MIN_CHAIN) ua_consts_equal=True")


# ── CLI ──────────────────────────────────────────────────────
def main():
    apr = argparse.ArgumentParser(description=__doc__)
    mode = apr.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true",
                      help="只跑实体统计查询,打印命中计数")
    mode.add_argument("--fetch", action="store_true",
                      help="抓取 + 组装 + 写候选 json")
    mode.add_argument("--smoke", action="store_true",
                      help="零网络自检(语法 + 罐头组装 + 常量等价)")
    apr.add_argument("--props", default="P108,P551",
                     help="属性对,逗号分隔,如 P108,P551(限 "
                          + "/".join(ALLOWED_PROPS) + ")")
    apr.add_argument("--limit", type=int, default=50,
                     help="实体查询 LIMIT(默认 50)")
    apr.add_argument("--out", default=None,
                     help="fetch 输出路径(默认 data/wikistate_candidates_"
                          "multi_{PA}_{PB}.json)")
    args = apr.parse_args()

    if args.smoke:
        run_smoke()
        return

    props = tuple(p.strip() for p in args.props.split(",") if p.strip())
    if len(props) != 2 or props[0] == props[1] or \
            any(p not in ALLOWED_PROPS for p in props):
        apr.error(f"--props 需要两个不同属性,取值限 {ALLOWED_PROPS},"
                  f"得到 {props}")
    pa, pb = props
    if args.probe:
        run_probe(pa, pb, args.limit)
    else:
        out = Path(args.out) if args.out else Path(
            f"data/wikistate_candidates_multi_{pa}_{pb}.json")
        run_fetch(pa, pb, args.limit, out)


if __name__ == "__main__":
    main()
