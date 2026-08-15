# -*- coding: utf-8 -*-
"""新域建材·步骤1(P1303 专线):演奏乐器多值实体抓取 + 机械清洗。

用途:零改动新域测试(study_logs/QVF_coupling_audit_20260815.md §三)之
P1303(演奏乐器,完全域外)。系统侧一行不改;本脚本是数据侧新件。
通用单属性线见 scripts/newdom_scrape.py(P26/P69 用);P1303 需要专线,
原因是数据形态考证(2026-08-15 WDQS 实测,先于定稿):

  P1303 主陈述带时间限定符在全 Wikidata 仅 P580×46 / P582×8 / P585×7 条,
  多值人物仅 7 人 —— 40-60 目标在"主陈述限定符"口径下不可达(负结果
  入档)。乐器×时间的真实记载主要活在乐队成员陈述上:乐队 p:P527
  (有成员)与人物 p:P463(成员于)陈述常带 pq:P1303(该语境演奏的
  乐器)+ pq:P580/P582。三形态并集(P527 侧 + P463 侧 + P1303 主陈述)
  实测多值人物 52 人(sitelinks<=50)。值仍是 P1303 乐器 QID、日期仍是
  真实 P580/P585 限定符,属性域(演奏乐器)与完全域外性质不变。

同日并列口径(与通用线 tie_start 剔除不同,入档):乐器域天然集值 ——
一条成员陈述常以同一 P580 列多件乐器(同日真实共同开始),按通用线
tie_start 剔除会把 52 人坍缩到 11 人(首轮 --fetch 实测 tie_dropped=68)
且丢弃真实事实。本线保留同日不同值步骤并计数(same_day_kept),链内
排序键 (start, position) 确定;"链深优先"以不同日期数(date_depth)
为第一序,值数(value_depth)第二序 —— 时间跨度记载者优先,同
任务书"链深≥2 优先"。真乱序(区间倒置 end<=start)仍剔除。

其余清洗与通用线同口径(逐项计数入 meta):缺开始日期(含仅 P582)/
非日期 start(genid)/ 同值重复保首见 / 裸 QID 标签 / 同标签不同 QID /
清洗后 <2 值整人剔除。

知名度:sitelinks<=50(通用线 5 在本属性只剩 31 人,按 --probe 分布
放宽,中等偏低,写 meta)。

输出(布局与通用线/旧域候选件逐字同构;uid 由渲染线按文件序分配):
  data/newdom_P1303.json       人级 {qid,label,sitelinks,chain},
                               链步 {position,start,end}(同日可并列);
  data/newdom_P1303.meta.json  清洗计数/两种链深分布/限定符覆盖/命令行。

用法:
  python scripts/newdom_scrape_P1303.py --probe [--max-sitelinks 50]
  python scripts/newdom_scrape_P1303.py --fetch [--max-sitelinks 50] [--target 60]
  python scripts/newdom_scrape_P1303.py --smoke
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 自包含:不从 scripts.newdom_scrape 导入(该通用线在并行会话中活跃
# 重写,2026-08-15 已两度改型;本线常量/工具与其同口径,漂移由各自
# smoke 兜底)。UA 与 wikistate_scrape.py 逐字一致。
ENDPOINT = "https://query.wikidata.org/sparql"
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
API = "https://www.wikidata.org/w/api.php"
RATE_SECONDS = 2.0         # WDQS 礼貌间隔,同 scrape_wikistate_multi

PROP = "P1303"
MIN_CHAIN_NEW = 2          # 多值门槛,同通用线
DEFAULT_MAX_SL = 20        # --probe 定标:5→31人不足;50 混入 Eagles/
#                            Scorpions 级名人(裸答泄漏向"泛化成立"方向
#                            偏置,反审计);20 → 42 人,含全部多日期实体
OUT = ROOT / "data" / f"newdom_{PROP}.json"
META = OUT.with_suffix(".meta.json")


# ── 基础工具(与通用线同口径,自包含定义)─────────────────────
_LAST_REQ = [0.0]


def _throttle():
    wait = RATE_SECONDS - (time.monotonic() - _LAST_REQ[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_REQ[0] = time.monotonic()


def sparql(query: str) -> dict:
    import requests  # 懒导入:--smoke 零网络
    _throttle()
    r = requests.get(ENDPOINT, params={"query": query, "format": "json"},
                     headers=UA, timeout=120)
    r.raise_for_status()
    return r.json()


def resolve_labels(qids) -> dict:
    """wbgetentities 批量英文标签(承 wikistate_build.resolve_labels)。"""
    import requests
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        r = requests.get(API, params={
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "labels", "languages": "en", "format": "json"},
            headers=UA, timeout=30)
        for qid, ent in r.json().get("entities", {}).items():
            labels[qid] = ent.get("labels", {}).get("en", {}).get(
                "value", qid)
        time.sleep(0.2)
    return labels


def _bind(row: dict, var: str):
    b = row.get(var)
    return b.get("value") if isinstance(b, dict) else None


def _tail_qid(uri: str) -> str:
    return str(uri).rsplit("/", 1)[-1]


def _short_date(t: str) -> str:
    return str(t).lstrip("+")[:10]


def _is_date(s) -> bool:
    return str(s)[:4].isdigit()


def label_clean(chain, labels, counters: dict) -> list:
    """标签清洗:裸 QID 标签剔除、同标签去重保首见(同通用线口径)。"""
    out, seen = [], set()
    for s in chain:
        lb = str(labels.get(s["position"], s["position"]))
        if lb.startswith("Q") and lb[1:].isdigit():
            counters["no_label"] += 1
            continue
        if lb in seen:
            counters["dup_label"] += 1
            continue
        seen.add(lb)
        out.append(dict(s))
    return out


def new_counters() -> dict:
    return {"missing_date": 0, "bad_start": 0,
            "disorder_end_before_start": 0, "dup_value": 0, "tie_start": 0,
            "no_label": 0, "dup_label": 0, "single_after_clean": 0}


# ── SPARQL 文本(三形态并集)─────────────────────────────────
_DATED = "{ ?st pq:P580 ?d } UNION { ?st pq:P585 ?d }"


def entity_query(max_sitelinks: int, limit: int) -> str:
    return f"""SELECT ?person ?sitelinks (SAMPLE(?lbl) AS ?label)
       (COUNT(DISTINCT ?inst) AS ?n) WHERE {{
  {{ ?band p:P527 ?st . ?st ps:P527 ?person ; pq:{PROP} ?inst . {_DATED} }}
  UNION
  {{ ?person p:P463 ?st . ?st pq:{PROP} ?inst . {_DATED} }}
  UNION
  {{ ?person p:{PROP} ?st . ?st ps:{PROP} ?inst . {_DATED} }}
  ?person wdt:P31 wd:Q5 ;
          wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks <= {int(max_sitelinks)})
  OPTIONAL {{ ?person rdfs:label ?lbl . FILTER(LANG(?lbl) = "en") }}
}}
GROUP BY ?person ?sitelinks
HAVING (COUNT(DISTINCT ?inst) >= {MIN_CHAIN_NEW})
ORDER BY ASC(?sitelinks) ASC(?person)
LIMIT {int(limit)}"""


def detail_query(qid: str) -> str:
    """单人明细:三形态全部 (陈述,乐器) 记录(含无日期/仅 P582 者,供
    清洗计数)。start 拆 ?p580/?p585 两列,供限定符覆盖统计。"""
    return f"""SELECT ?value ?p580 ?p585 ?end WHERE {{
  {{ ?band p:P527 ?st . ?st ps:P527 wd:{qid} ; pq:{PROP} ?value . }}
  UNION
  {{ wd:{qid} p:P463 ?st . ?st pq:{PROP} ?value . }}
  UNION
  {{ wd:{qid} p:{PROP} ?st . ?st ps:{PROP} ?value . }}
  OPTIONAL {{ ?st pq:P580 ?p580 }}
  OPTIONAL {{ ?st pq:P585 ?p585 }}
  OPTIONAL {{ ?st pq:P582 ?end }}
}}"""


# ── 机械清洗(纯函数;同日不同值保留并计数)───────────────────
def p1303_counters() -> dict:
    n = new_counters()
    n.pop("tie_start", None)       # 本线不剔同日并列,改计 same_day_kept
    n["same_day_kept"] = 0
    n["qual_via_P580"] = 0
    n["qual_via_P585"] = 0
    return n


def clean_chain(rows, counters: dict) -> list:
    """明细行 → 清洗后链步 [{position,start,end}](值为裸 QID;
    (start,position) 升序,同日不同值并列保留)。"""
    steps = []
    for row in rows:
        val = _bind(row, "value")
        if not val:
            continue
        start_raw = _bind(row, "p580") or _bind(row, "p585")
        if not start_raw:
            counters["missing_date"] += 1     # 缺开始日期(含仅 P582 者)
            continue
        start = _short_date(start_raw)
        if not _is_date(start):
            counters["bad_start"] += 1        # unknown-value genid URL 等
            continue
        end = _bind(row, "end")
        end = _short_date(end) if end else None
        if end is not None and not _is_date(end):
            end = None
        if end is not None and end <= start:
            counters["disorder_end_before_start"] += 1   # 乱序:区间倒置
            continue
        via = "P580" if _bind(row, "p580") else "P585"
        steps.append({"position": _tail_qid(val), "start": start, "end": end,
                      "_via": via})
    steps.sort(key=lambda s: (s["start"], s["position"]))
    out, seen_vals = [], set()
    for s in steps:
        if s["position"] in seen_vals:
            counters["dup_value"] += 1        # 同值重复(跨乐队再现等)保首见
            continue
        if out and s["start"] == out[-1]["start"]:
            counters["same_day_kept"] += 1    # 同日不同值:保留(集值域)
        seen_vals.add(s["position"])
        counters[f"qual_via_{s['_via']}"] += 1
        out.append({"position": s["position"], "start": s["start"],
                    "end": s["end"]})
    return out


def date_depth(chain) -> int:
    return len({s["start"] for s in chain})


def assemble(entity_rows, details, labels, counters, target: int) -> list:
    """实体行 + 明细 + 标签 → 清洗幸存候选。排序:不同日期数降序(时间
    跨度优先)→ 值数降序 → sitelinks 升序 → qid;截 target。"""
    base = []
    seen_qid = set()
    for row in entity_rows:
        qid = _tail_qid(_bind(row, "person") or "")
        if not qid.startswith("Q") or qid in seen_qid or qid not in details:
            continue
        seen_qid.add(qid)
        chain = clean_chain(details[qid], counters)
        chain = label_clean(chain, labels, counters)
        if len(chain) < MIN_CHAIN_NEW:
            counters["single_after_clean"] += 1
            continue
        base.append({"qid": qid, "label": _bind(row, "label") or qid,
                     "sitelinks": int(_bind(row, "sitelinks") or 0),
                     "chain": chain})
    base.sort(key=lambda c: (-date_depth(c["chain"]), -len(c["chain"]),
                             c["sitelinks"], c["qid"]))
    return base[:target]


# ── --probe ──────────────────────────────────────────────────
def run_probe(max_sitelinks: int, limit: int):
    from collections import Counter
    rows = sparql(entity_query(max_sitelinks, limit))["results"]["bindings"]
    sls = [int(_bind(r, "sitelinks") or 0) for r in rows]
    ns = Counter(int(_bind(r, "n") or 0) for r in rows)
    print(f"probe {PROP} max_sl={max_sitelinks} LIMIT {limit}: "
          f"persons={len(rows)} inst_count_dist={dict(sorted(ns.items()))}")
    for cut in (3, 5, 10, 20, 50):
        print(f"  sl<={cut:3d}: persons={sum(1 for v in sls if v <= cut)}")


# ── --fetch ──────────────────────────────────────────────────
def run_fetch(max_sitelinks: int, limit: int, target: int):
    from collections import Counter
    rows = sparql(entity_query(max_sitelinks, limit))["results"]["bindings"]
    print(f"entity query: {len(rows)} persons, fetching details "
          f"(1 query/person, {RATE_SECONDS}s apart)...", flush=True)
    details = {}
    for i, row in enumerate(rows):
        qid = _tail_qid(_bind(row, "person") or "")
        if not qid.startswith("Q") or qid in details:
            continue
        try:
            details[qid] = sparql(detail_query(qid))["results"]["bindings"]
        except Exception as e:  # noqa: BLE001 —— 单人失败不拖垮整批
            print(f"[{i + 1}/{len(rows)}] {qid} SKIP {type(e).__name__}",
                  flush=True)
            continue
        if (i + 1) % 20 == 0:
            print(f"[{i + 1}/{len(rows)}] fetched", flush=True)
    value_qids = {_tail_qid(_bind(r, "value"))
                  for rws in details.values() for r in rws
                  if _bind(r, "value")}
    print(f"resolving {len(value_qids)} value labels...", flush=True)
    labels = resolve_labels(value_qids)

    counters = p1303_counters()
    cands = assemble(rows, details, labels, counters, target)

    vdepth = Counter(len(c["chain"]) for c in cands)
    ddepth = Counter(date_depth(c["chain"]) for c in cands)
    end_cov = sum(1 for c in cands for s in c["chain"] if s.get("end"))
    steps = sum(len(c["chain"]) for c in cands)
    for c in cands[:10]:
        safe = str(c["label"]).encode("ascii", "replace").decode()
        print(f"  {c['qid']} {safe} sl={c['sitelinks']} "
              f"values={len(c['chain'])} dates={date_depth(c['chain'])}")

    OUT.write_text(json.dumps(cands, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    meta = {
        "prop": PROP, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": " ".join(sys.argv), "endpoint": ENDPOINT,
        "max_sitelinks": max_sitelinks, "min_chain_new": MIN_CHAIN_NEW,
        "entity_rows": len(rows), "detail_fetched": len(details),
        "candidates_written": len(cands), "target": target,
        "cleaning_counters": counters,
        "value_depth_dist": dict(sorted(vdepth.items())),
        "date_depth_dist": dict(sorted(ddepth.items())),
        "qualifier_coverage": {
            "steps_total": steps,
            "via_P580": counters["qual_via_P580"],
            "via_P585": counters["qual_via_P585"],
            "steps_with_end_P582": end_cov},
        "statement_shapes": "union of band-side P527(pq:P1303,pq:P580/585) "
                            "+ person-side P463(pq:P1303,pq:P580/585) "
                            "+ direct P1303 main statements(pq:P580/585)",
        "shape_evidence": "direct-only availability (WDQS 2026-08-15): "
                          "46/8/7 statements with pq:P580/P582/P585; "
                          "7 multi-value persons => target 40-60 unreachable "
                          "on direct shape; union => 52 persons at sl<=50",
        "same_day_policy": "same-day different-value steps KEPT and counted "
                           "(set-valued domain; generic-line tie_start drop "
                           "would collapse 52->11 persons, measured); "
                           "selection prioritises distinct-date depth",
        "selection_rule": "sort(-date_depth, -value_depth, sitelinks asc, "
                          "qid) top target",
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"candidates={len(cands)} value_depth={dict(sorted(vdepth.items()))} "
          f"date_depth={dict(sorted(ddepth.items()))}")
    print(f"cleaning={counters}")
    print(f"-> {OUT}\n-> {META}")


# ── --smoke:零网络自检 ──────────────────────────────────────
def _lit(v):
    return {"type": "literal", "value": v}


def _ent(qid):
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}


def _check_sparql(q: str, required) -> list:
    errs = []
    for a, b in (("{", "}"), ("(", ")")):
        bal = 0
        for ch in q:
            bal += (ch == a) - (ch == b)
            if bal < 0:
                errs.append(f"negative balance {a}{b}")
                break
        if bal > 0:
            errs.append(f"unbalanced {a}{b}")
    if q.count('"') % 2:
        errs.append("unbalanced quotes")
    for tok in required:
        if tok not in q:
            errs.append(f"missing token: {tok}")
    return errs


# 罐头:Q1 = 深例(P580×3 + P585×1 + 仅P582×1 + 无日期×1 + genid×1 +
# 同值重复×1 + 同日不同值×1 + 区间倒置×1);Q2 = 同值双陈述 → 清洗后
# 单值整人剔除;Q3 = 同日双乐器(date_depth=1)→ 保留但排 Q1 后
# (date_depth 优先);Q4 = 标签清洗致单值(裸 QID + 同名)整人剔除。
FIXTURE_ENTITY = {"results": {"bindings": [
    {"person": _ent("Q3"), "sitelinks": _lit("0"),
     "label": {**_lit("Cass Sameday"), "xml:lang": "en"}, "n": _lit("2")},
    {"person": _ent("Q1"), "sitelinks": _lit("3"),
     "label": {**_lit("Alice Muse"), "xml:lang": "en"}, "n": _lit("5")},
    {"person": _ent("Q2"), "sitelinks": _lit("1"), "n": _lit("2")},
    {"person": _ent("Q4"), "sitelinks": _lit("2"),
     "label": {**_lit("Drop Label"), "xml:lang": "en"}, "n": _lit("2")},
]}}
FIXTURE_DETAILS = {
    "Q1": [
        {"value": _ent("Q6607"), "p580": _lit("+1990-03-01T00:00:00Z"),
         "end": _lit("1995-01-01T00:00:00Z")},
        {"value": _ent("Q5994"), "p585": _lit("1995-06-01T00:00:00Z")},
        {"value": _ent("Q8338"), "p580": _lit("2001-09-01T00:00:00Z")},
        {"value": _ent("Q1339"), "p580": _lit("2001-09-01T00:00:00Z")},  # 同日
        {"value": _ent("Q46185"), "end": _lit("1999-01-01T00:00:00Z")},  # 仅P582
        {"value": _ent("Q11404")},                                       # 无日期
        {"value": _ent("Q17172850"),
         "p580": _lit("http://www.wikidata.org/.well-known/genid/x")},
        {"value": _ent("Q6607"), "p580": _lit("1992-01-01T00:00:00Z")},  # 重值
        {"value": _ent("Q4991371"), "p580": _lit("2005-01-01T00:00:00Z"),
         "end": _lit("2004-01-01T00:00:00Z")},                           # 倒置
    ],
    "Q2": [
        {"value": _ent("Q6607"), "p580": _lit("1990-01-01T00:00:00Z")},
        {"value": _ent("Q6607"), "p585": _lit("1993-01-01T00:00:00Z")},
    ],
    "Q3": [
        {"value": _ent("Q5994"), "p580": _lit("1988-07-01T00:00:00Z")},
        {"value": _ent("Q6607"), "p580": _lit("1988-07-01T00:00:00Z")},
    ],
    "Q4": [
        {"value": _ent("Q99001"), "p580": _lit("1990-01-01T00:00:00Z")},  # 裸QID
        {"value": _ent("Q99002"), "p580": _lit("1994-01-01T00:00:00Z")},
        {"value": _ent("Q99003"), "p580": _lit("1998-01-01T00:00:00Z")},  # 同名
    ],
}
FIX_LABELS = {"Q6607": "guitar", "Q5994": "piano", "Q8338": "bass guitar",
              "Q1339": "keyboard", "Q99001": "Q99001", "Q99002": "melodica",
              "Q99003": "melodica", "Q4991371": "drum kit"}


def run_smoke():
    q = entity_query(50, 400)
    errs = _check_sparql(q, [
        "SELECT", "p:P527 ?st", "ps:P527 ?person", "p:P463 ?st",
        f"p:{PROP} ?st", f"ps:{PROP} ?inst", f"pq:{PROP} ?inst",
        "pq:P580", "pq:P585", "UNION",
        "wdt:P31 wd:Q5", "wikibase:sitelinks", "FILTER(?sitelinks <= 50)",
        "GROUP BY", f"HAVING (COUNT(DISTINCT ?inst) >= {MIN_CHAIN_NEW})",
        "ORDER BY ASC(?sitelinks)", "LIMIT 400"])
    assert not errs, f"entity_query: {errs}"
    q = detail_query("Q42")
    errs = _check_sparql(q, [
        "SELECT", "ps:P527 wd:Q42", "wd:Q42 p:P463 ?st",
        f"wd:Q42 p:{PROP} ?st", f"ps:{PROP} ?value", f"pq:{PROP} ?value",
        "pq:P580", "pq:P585", "pq:P582", "OPTIONAL"])
    assert not errs, f"detail_query: {errs}"

    counters = p1303_counters()
    cands = assemble(FIXTURE_ENTITY["results"]["bindings"], FIXTURE_DETAILS,
                     FIX_LABELS, counters, target=60)
    # 排序:Q1(dates=3)在前,Q3(dates=1)在后;Q2/Q4 整人剔除。
    assert [c["qid"] for c in cands] == ["Q1", "Q3"], \
        f"got {[c['qid'] for c in cands]}"
    for c in cands:
        assert list(c.keys()) == ["qid", "label", "sitelinks", "chain"]
        for s in c["chain"]:
            assert list(s.keys()) == ["position", "start", "end"]
    a = cands[0]["chain"]
    # 同日并列 (Q1339 keyboard / Q8338 bass guitar @2001-09-01) 均保留,
    # (start,position) 序:Q1339 < Q8338 字典序。
    assert [s["position"] for s in a] == \
        ["Q6607", "Q5994", "Q1339", "Q8338"], a
    assert a[0]["start"] == "1990-03-01", "'+' stripped, 10-char date"
    assert a[0]["end"] == "1995-01-01" and a[1]["end"] is None
    assert date_depth(a) == 3 and date_depth(cands[1]["chain"]) == 1
    assert counters["missing_date"] == 2       # 仅P582 + 完全无日期
    assert counters["bad_start"] == 1          # genid
    assert counters["disorder_end_before_start"] == 1
    assert counters["dup_value"] == 2          # Q1 重值 + Q2 同值双陈述
    assert counters["same_day_kept"] == 1 + 1  # Q1 同日对 + Q3 同日对
    assert counters["no_label"] == 1 and counters["dup_label"] == 1
    assert counters["single_after_clean"] == 2  # Q2(同值)+ Q4(标签清洗)
    # qual_via 计"值清洗后保留步"(标签清洗前):Q1 3+Q2 1+Q3 2+Q4 3
    assert counters["qual_via_P580"] == 9 and counters["qual_via_P585"] == 1
    print(f"SMOKE OK: sparql checked; fixture candidates={len(cands)}; "
          f"counters={counters}")


# ── CLI ──────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--fetch", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-sitelinks", type=int, default=DEFAULT_MAX_SL,
                    help=f"知名度上限(默认 {DEFAULT_MAX_SL},--probe 定标)")
    ap.add_argument("--limit", type=int, default=400,
                    help="实体查询 LIMIT(默认 400)")
    ap.add_argument("--target", type=int, default=60,
                    help="候选上限(预注册 40-60,默认 60)")
    args = ap.parse_args()
    if args.smoke:
        run_smoke()
    elif args.probe:
        run_probe(args.max_sitelinks, args.limit)
    else:
        run_fetch(args.max_sitelinks, args.limit, args.target)


if __name__ == "__main__":
    main()
