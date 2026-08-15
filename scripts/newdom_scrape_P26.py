# -*- coding: utf-8 -*-
"""新域建材·步骤1(P26 专线):配偶多值实体抓取 + 机械清洗。

用途:零改动新域测试(study_logs/QVF_coupling_audit_20260815.md §三)之
P26(配偶,映射闭集内 relationship —— qvf_router.SLOT_ALIASES 已含
spouse/wife/husband/married 别名,阳性对照)。系统侧一行不改;本脚本是
数据侧新件。通用线见 scripts/newdom_scrape.py;P26 需要专线,原因是
数据形态考证(2026-08-15 WDQS 实测,证据件入 scratchpad
newdom_P26_wdqs_evidence.*):

  sitelinks<=5 且 >=2 条带 P580/P585 限定符 P26 的人物,按低知名度序取
  300 人逐人清洗,仅 7 人存活 —— 瓶颈不是缺日期(20)而是配偶无英文
  标签(no_label=541,连带 single_after_clean=293):低知名度人物的
  配偶更低知名度,绝大多数为裸 QID。通用搜索扫描线(search API)在同
  口径下命中率同样受此制约且不可预算。

  对策(本线两处偏离通用线,逐项入档):
  ① 实体查询把"配偶有英文标签"推进 SPARQL(COUNT DISTINCT 带英文
     标签的配偶值 >= 2),直接按可用性选人 —— 群体级别的标签流失率
     已由证据件量化(541/582 步),查询侧过滤不再逐人计数;
  ② 知名度上限按 --probe 定标。定标结论(2026-08-15,LIMIT 800):
     标签可用性推进查询侧后,sitelinks=0 一档即有 >=800 可用人物
     (nUsable 2:732 / 3:61 / 4:4 / 5:2 / 9:1)—— 旧线口径 <=5 保持
     不放宽,裸答风险面与旧域一致(早先"仅 7 人存活"是未推进标签
     约束时逐人清洗的样本流失,非群体不足)。
  ③ 深链优先预选:实体查询带回 nUsable,本地按 (-nUsable, sitelinks,
     qid) 排序后仅对前 --overscan(默认 90)人跑逐人明细 —— 深链全部
     进预选池,明细耗时从全量 ~27 分钟压到 ~3-4 分钟。

其余口径与通用线一致:开始 = P580 或 P585(必需),P582 结束可选;
明细级机械清洗逐项计数(缺日期/坏日期/区间倒置/同值重复/同日并列/
裸 QID 标签/同名标签/清洗后 <2 整人剔除);链深降序优先,再 sitelinks
升序、qid 定序,截 --target;部分日期(2003-00-00 规约为 2003-01-01,
SPARQL 侧固有形态,下游 parse_partial_date 两种都吃)。礼貌抓取
1 请求/2 秒 + 429/5xx 退避重试(尊重 Retry-After)。

输出(布局与旧域候选件逐字同构;uid 由渲染线按文件序分配):
  data/newdom_P26.json       人级 {qid,label,sitelinks,chain},
                             链步 {position,start,end};
  data/newdom_P26.meta.json  清洗计数/链深分布/sitelinks 分布/命令行。

用法:
  python scripts/newdom_scrape_P26.py --probe [--max-sitelinks 50]
  python scripts/newdom_scrape_P26.py --fetch --max-sitelinks N --target 60
  python scripts/newdom_scrape_P26.py --smoke
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 自包含:不从 scripts.newdom_scrape 导入(通用线在并行会话中活跃重写;
# 漂移由各自 smoke 兜底)。UA 与 wikistate_scrape.py 逐字一致。
ENDPOINT = "https://query.wikidata.org/sparql"
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
API = "https://www.wikidata.org/w/api.php"
RATE_SECONDS = 2.0         # WDQS 礼貌间隔,同 scrape_wikistate_multi

PROP = "P26"
MIN_CHAIN_NEW = 2          # 多值门槛,同通用线(旧域单属性线为 3)


# ── SPARQL 文本 ──────────────────────────────────────────────
def entity_query(max_sitelinks: int, limit: int) -> str:
    """实体查询:人 + >=2 个「带 P580/P585 开始限定符且配偶有英文标签」
    的不同配偶值 + 人物本人有英文标签 + 低知名度,双键排序可复现。"""
    return f"""SELECT ?person ?sitelinks (SAMPLE(?plbl) AS ?label)
       (COUNT(DISTINCT ?sp) AS ?nUsable) WHERE {{
  ?person wdt:P31 wd:Q5 ;
          wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks <= {int(max_sitelinks)})
  ?person p:{PROP} ?st .
  {{ ?st pq:P580 ?d }} UNION {{ ?st pq:P585 ?d }}
  ?st ps:{PROP} ?sp .
  ?sp rdfs:label ?slbl . FILTER(LANG(?slbl) = "en")
  ?person rdfs:label ?plbl . FILTER(LANG(?plbl) = "en")
}}
GROUP BY ?person ?sitelinks
HAVING (COUNT(DISTINCT ?sp) >= {MIN_CHAIN_NEW})
ORDER BY ASC(?sitelinks) ASC(?person)
LIMIT {int(limit)}"""


def detail_query(qid: str) -> str:
    """单人明细:全部 P26 陈述(值 + 可选 start + 可选 end)。start 为
    OPTIONAL —— 无 P580/P585 者照常返回,本地计入 missing_date。"""
    return f"""SELECT ?value ?start ?end WHERE {{
  wd:{qid} p:{PROP} ?st .
  ?st ps:{PROP} ?value .
  OPTIONAL {{ {{ ?st pq:P580 ?start }} UNION {{ ?st pq:P585 ?start }} }}
  OPTIONAL {{ ?st pq:P582 ?end }}
}}"""


# ── 网络层(--probe/--fetch 才走;--smoke 全程不触碰)─────────
_LAST_REQ = [0.0]


def _throttle():
    wait = RATE_SECONDS - (time.monotonic() - _LAST_REQ[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_REQ[0] = time.monotonic()


def sparql(query: str, max_attempts: int = 5) -> dict:
    import requests  # 懒导入:--smoke / py_compile 不需要网络栈
    for attempt in range(max_attempts):
        _throttle()
        r = requests.get(ENDPOINT, params={"query": query, "format": "json"},
                         headers=UA, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == max_attempts - 1:
                r.raise_for_status()
            retry_after = r.headers.get("Retry-After")
            wait = (int(retry_after) if retry_after and retry_after.isdigit()
                    else 30 * (attempt + 1))
            print(f"WDQS {r.status_code}, backoff {wait}s "
                  f"(attempt {attempt + 1}/{max_attempts})", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


def resolve_labels(qids) -> dict:
    """wbgetentities 批量英文标签,承 wikistate_build.resolve_labels;
    entities 缺失(错误体/非法 id)即重试并最终报错 —— 不静默空标签
    (静默会让下游把整批合法 QID 误判为无标签)。"""
    import requests
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        for attempt in range(4):
            r = requests.get(API, params={
                "action": "wbgetentities", "ids": "|".join(batch),
                "props": "labels", "languages": "en", "format": "json"},
                headers=UA, timeout=30)
            ents = r.json().get("entities")
            if ents:
                for qid, ent in ents.items():
                    labels[qid] = ent.get("labels", {}).get(
                        "en", {}).get("value", qid)
                break
            print(f"wbgetentities empty/error (attempt {attempt + 1}/4), "
                  f"backoff", flush=True)
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"wbgetentities failed: {batch[:3]}…")
        time.sleep(0.2)
    return labels


# ── SPARQL JSON 工具 ─────────────────────────────────────────
def _bind(row, var):
    b = row.get(var)
    return b.get("value") if isinstance(b, dict) else None


def _tail_qid(uri):
    return str(uri).rsplit("/", 1)[-1]


def _short_date(t):
    return str(t).lstrip("+")[:10]


def _is_date(s):
    return str(s)[:4].isdigit()


# ── 机械清洗(纯函数,罐头可冒烟;计数键与通用线同名)─────────
def new_counters() -> dict:
    return {"missing_date": 0, "bad_start": 0, "missing_value": 0,
            "disorder_end_before_start": 0, "dup_value": 0, "tie_start": 0,
            "no_label": 0, "dup_label": 0, "single_after_clean": 0}


def clean_chain(rows, counters: dict) -> list:
    """明细行 → 清洗链步 [{position,start,end}](升序、同值去重、同日
    并列剔除、区间倒置剔除、缺日期/坏日期剔除)。"""
    import re as _re
    steps = []
    for row in rows:
        val, start = _bind(row, "value"), _bind(row, "start")
        if not val:
            continue
        if not _re.fullmatch(r"Q\d+", _tail_qid(val)):
            counters["missing_value"] += 1    # unknown-value genid 节点
            continue
        if not start:
            counters["missing_date"] += 1     # 缺日期(含仅 P582 者)
            continue
        start = _short_date(start)
        if not _is_date(start):
            counters["bad_start"] += 1        # genid / BCE 畸形
            continue
        end = _bind(row, "end")
        end = _short_date(end) if end else None
        if end is not None and not _is_date(end):
            end = None
        if end is not None and end <= start:
            counters["disorder_end_before_start"] += 1   # 乱序:区间倒置
            continue
        steps.append({"position": _tail_qid(val), "start": start, "end": end})
    steps.sort(key=lambda s: (s["start"], s["position"]))
    out, seen = [], set()
    for s in steps:
        if s["position"] in seen:
            counters["dup_value"] += 1        # 双限定重复行 / 复婚同人
            continue
        if out and s["start"] <= out[-1]["start"]:
            counters["tie_start"] += 1        # 乱序:同日并列不可严格排序
            continue
        seen.add(s["position"])
        out.append(s)
    return out


def label_clean(chain, labels, counters: dict) -> list:
    """标签清洗:裸 QID 剔除、同标签去重保首见。标签不入库(渲染线再
    解析),布局保持 {position,start,end}。"""
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


def select_candidates(pre, labels, counters, target: int) -> list:
    """标签清洗 + 终选:链深降序 / sitelinks 升序 / qid 定序,截 target。"""
    base = []
    for c in pre:
        chain = label_clean(c["chain"], labels, counters)
        if len(chain) < MIN_CHAIN_NEW:
            counters["single_after_clean"] += 1
            continue
        base.append({"qid": c["qid"], "label": c["label"],
                     "sitelinks": c["sitelinks"], "chain": chain})
    base.sort(key=lambda c: (-len(c["chain"]), c["sitelinks"], c["qid"]))
    return base[:target]


# ── --probe:sitelinks 分层定标(单查询)──────────────────────
def run_probe(max_sitelinks: int, limit: int):
    rows = sparql(entity_query(max_sitelinks, limit))["results"]["bindings"]
    from collections import Counter
    sls = [int(_bind(r, "sitelinks") or 0) for r in rows]
    tiers = {t: sum(1 for s in sls if s <= t) for t in (5, 10, 20, 30, 50)
             if t <= max_sitelinks or t == max_sitelinks}
    n_dist = Counter(int(_bind(r, "nUsable") or 0) for r in rows)
    print(f"probe {PROP} sitelinks<={max_sitelinks} LIMIT {limit}: "
          f"persons={len(rows)} "
          f"tier_counts(<=t)={tiers} "
          f"nUsable_dist={dict(sorted(n_dist.items()))} "
          f"sitelinks_min={min(sls) if sls else '-'} "
          f"sitelinks_max={max(sls) if sls else '-'}")


# ── --fetch ──────────────────────────────────────────────────
def run_fetch(max_sitelinks: int, target: int, limit: int, overscan: int,
              out_path: Path):
    counters = new_counters()
    t0 = time.time()
    rows = sparql(entity_query(max_sitelinks, limit))["results"]["bindings"]
    # 深链优先预选:(-nUsable, sitelinks, qid) 排序取前 overscan 人。
    rows.sort(key=lambda r: (-int(_bind(r, "nUsable") or 0),
                             int(_bind(r, "sitelinks") or 0),
                             _tail_qid(_bind(r, "person") or "")))
    n_entity = len(rows)
    rows = rows[:overscan]
    print(f"entity query: {n_entity} persons (sitelinks<={max_sitelinks}); "
          f"detail-fetching top {len(rows)} by (-nUsable, sitelinks, qid) "
          f"(1 query/person, {RATE_SECONDS}s apart)...", flush=True)
    pre, fetch_errors = [], 0
    for i, row in enumerate(rows):
        qid = _tail_qid(_bind(row, "person") or "")
        if not qid.startswith("Q"):
            continue
        try:
            detail = sparql(detail_query(qid))["results"]["bindings"]
        except Exception as e:  # noqa: BLE001 —— 单人失败不拖垮整批
            fetch_errors += 1
            print(f"[{i + 1}/{len(rows)}] {qid} SKIP {type(e).__name__}",
                  flush=True)
            continue
        chain = clean_chain(detail, counters)
        if len(chain) < MIN_CHAIN_NEW:
            counters["single_after_clean"] += 1
            continue
        pre.append({"qid": qid, "label": _bind(row, "label") or qid,
                    "sitelinks": int(_bind(row, "sitelinks") or 0),
                    "chain": chain})
        if (i + 1) % 20 == 0:
            print(f"[{i + 1}/{len(rows)}] fetched, pre={len(pre)}",
                  flush=True)
    print(f"detail done: {len(pre)} pre-candidates "
          f"({time.time() - t0:.0f}s); resolving value labels...", flush=True)
    value_qids = sorted({s["position"] for c in pre for s in c["chain"]})
    labels = resolve_labels(value_qids)
    cands = select_candidates(pre, labels, counters, target)

    from collections import Counter
    depth = Counter(len(c["chain"]) for c in cands)
    sls = Counter(c["sitelinks"] for c in cands)
    qual = {"steps_total": sum(len(c["chain"]) for c in cands),
            "steps_with_end_P582": sum(1 for c in cands for s in c["chain"]
                                       if s.get("end"))}
    for c in cands:
        print(f"{c['qid']} {c['label']} sl={c['sitelinks']} "
              f"chain={len(c['chain'])}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cands, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    meta = {
        "prop": PROP, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": " ".join(sys.argv),
        "route": ("P26 专线:WDQS person-first 实体查询(配偶英文标签可用性"
                  "推进查询侧,COUNT DISTINCT 带标签配偶 >= 2)+ 逐人明细 + "
                  "本地机械清洗。通用线(search API)与 sitelinks<=5 口径在"
                  "本属性不可达 40-60 目标:证据件 scratchpad/"
                  "newdom_P26_wdqs_evidence.*(300 人仅 7 存活,"
                  "no_label=541)"),
        "endpoint": ENDPOINT,
        "max_sitelinks": max_sitelinks,
        "max_sitelinks_note": ("--probe 定标(LIMIT 800):标签可用性推进"
                               "查询侧后 sitelinks=0 一档 >=800 可用人物,"
                               "旧线口径 <=5 保持不放宽(早先证据件的 "
                               "7/300 是未推进标签约束的样本流失);LEAK "
                               "过滤仍留下一阶段(wikistate_build 同款)"),
        "min_chain_new": MIN_CHAIN_NEW,
        "qualifier_rule": ("start=P580|P585(必需), end=P582(可选);"
                           "仅 P582 计缺日期"),
        "entity_rows": n_entity, "detail_fetched": len(rows),
        "overscan": overscan, "detail_fetch_errors": fetch_errors,
        "pre_candidates": len(pre), "candidates_written": len(cands),
        "target": target, "entity_limit": limit,
        "cleaning_counters": counters,
        "chain_depth_dist": {str(k): v for k, v in sorted(depth.items())},
        "sitelinks_dist": {str(k): v for k, v in sorted(sls.items())},
        "qualifier_coverage": qual,
        "selection_rule": "sort(-chain_depth, sitelinks asc, qid) top target",
        "note": ("布局与旧域候选件(wikistate_candidates*.json)逐字同构;"
                 "SPARQL 侧部分日期已规约(2003-00-00 → 2003-01-01),"
                 "与 S6 多属性线同形态,下游 parse_partial_date 兼容。"),
    }
    out_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"entity_rows={n_entity} candidates={len(cands)} -> {out_path}")
    print(f"cleaning={counters}")
    print(f"depth_dist={dict(sorted(depth.items()))} "
          f"sitelinks_dist={dict(sorted(sls.items()))} qual={qual}")


# ── --smoke:零网络自检 ──────────────────────────────────────
def _lit(v, **extra):
    return {"type": "literal", "value": str(v), **extra}


def _ent(qid):
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}


FIX_DETAILS_A = [   # 全清洗路径:'+'前缀 / 双限定重复 / 区间倒置 / 并列 /
    # genid / 缺日期 / 仅 P582
    {"value": _ent("Q800011"), "start": _lit("+1980-05-10T00:00:00Z"),
     "end": _lit("1994-01-01T00:00:00Z")},
    {"value": _ent("Q800012"), "start": _lit("1995-06-01T00:00:00Z")},
    {"value": _ent("Q800012"), "start": _lit("+1995-06-01T00:00:00Z")},
    {"value": _ent("Q800013"), "start": _lit("1998-01-01T00:00:00Z"),
     "end": _lit("1997-01-01T00:00:00Z")},
    {"value": _ent("Q800014"), "start": _lit("1995-06-01T00:00:00Z")},
    {"value": _ent("Q800015"),
     "start": _lit("http://www.wikidata.org/.well-known/genid/abc")},
    {"value": _ent("Q800016")},
    {"value": _ent("Q800017"), "end": _lit("2004-06-30T00:00:00Z")},
    {"value": _ent("Q800018"), "start": _lit("2003-09-20T00:00:00Z")},
    {"value": {"type": "uri", "value": "http://www.wikidata.org/.well-known/"
               "genid/58fde4d65c2161126d8051677a1cd32e"},
     "start": _lit("2005-01-01T00:00:00Z")},   # unknown-value 配偶(真实形态)
]
FIX_DETAILS_B = [
    {"value": _ent("Q800021"), "start": _lit("1990-01-01T00:00:00Z"),
     "end": _lit("2000-01-01T00:00:00Z")},
    {"value": _ent("Q800022"), "start": _lit("1998-06-01T00:00:00Z")},
]
FIX_DETAILS_DROP = [
    {"value": _ent("Q800031"), "start": _lit("1990-01-01T00:00:00Z")},
    {"value": _ent("Q800032"), "start": _lit("1992-01-01T00:00:00Z")},
]
FIX_LABELS = {"Q800011": "Miriam Voss", "Q800012": "Petra Lindqvist",
              "Q800014": "Petra Lindqvist",   # 同名不同 QID(并列已剔)
              "Q800018": "Sofia Andrade",
              "Q800021": "Tomas Reiner", "Q800022": "Elena Brandt",
              "Q800031": "Ana Duarte", "Q800032": "Q800032"}


def run_smoke():
    # ① SPARQL 字符串级检查(括号/引号配平 + 必需 token)。
    for q, req in ((entity_query(20, 400), [
            "SELECT", "wdt:P31 wd:Q5", "wikibase:sitelinks",
            "FILTER(?sitelinks <= 20)", f"p:{PROP} ?st", "pq:P580",
            "pq:P585", "UNION", f"ps:{PROP} ?sp",
            'FILTER(LANG(?slbl) = "en")', 'FILTER(LANG(?plbl) = "en")',
            "GROUP BY", f"HAVING (COUNT(DISTINCT ?sp) >= {MIN_CHAIN_NEW})",
            "ORDER BY ASC(?sitelinks) ASC(?person)", "LIMIT 400"]),
            (detail_query("Q42"), [
                "SELECT", f"wd:Q42 p:{PROP} ?st", f"ps:{PROP}", "pq:P580",
                "pq:P585", "UNION", "OPTIONAL", "pq:P582"])):
        for a, b in (("{", "}"), ("(", ")")):
            bal = 0
            for ch in q:
                bal += (ch == a) - (ch == b)
                assert bal >= 0, f"negative balance {a}{b}"
            assert bal == 0, f"unbalanced {a}{b}"
        assert q.count('"') % 2 == 0
        for tok in req:
            assert tok in q, f"missing token: {tok}"

    # ② 明细清洗计数逐项手核(A 件踩全路径)。
    c = new_counters()
    chain = clean_chain(FIX_DETAILS_A, c)
    assert [s["position"] for s in chain] == \
        ["Q800011", "Q800012", "Q800018"], chain
    assert chain[0]["start"] == "1980-05-10" and chain[0]["end"] == \
        "1994-01-01", "'+' 前缀剥离 + 10 位日期"
    assert chain[1]["end"] is None
    assert c["missing_date"] == 2, c      # Q800016 + 仅P582 Q800017
    assert c["bad_start"] == 1, c         # genid start Q800015
    assert c["missing_value"] == 1, c     # unknown-value genid 配偶
    assert c["disorder_end_before_start"] == 1, c   # Q800013
    assert c["dup_value"] == 1, c         # Q800012 双限定重复
    assert c["tie_start"] == 1, c         # Q800014 与 Q800012 同日并列

    # ③ 终选:标签清洗 + 深链优先 + 布局同构 + 截断。
    cb = new_counters()
    chain_b = clean_chain(FIX_DETAILS_B, cb)
    chain_d = clean_chain(FIX_DETAILS_DROP, cb)
    pre = [
        {"qid": "Q910002", "label": "Bea Example", "sitelinks": 3,
         "chain": chain_b},
        {"qid": "Q910001", "label": "Ada Casefold", "sitelinks": 4,
         "chain": chain},
        {"qid": "Q910003", "label": "Cody Dropcase", "sitelinks": 0,
         "chain": chain_d},
    ]
    sel = select_candidates(pre, FIX_LABELS, cb, target=60)
    # Q910003 剔除(Q800032 裸 QID → 1 < 2);深链优先:Ada(3)先于 Bea(2)
    assert [x["qid"] for x in sel] == ["Q910001", "Q910002"], sel
    assert cb["no_label"] == 1 and cb["single_after_clean"] == 1, cb
    for x in sel:
        assert list(x.keys()) == ["qid", "label", "sitelinks", "chain"]
        for s in x["chain"]:
            assert list(s.keys()) == ["position", "start", "end"]
        starts = [s["start"] for s in x["chain"]]
        assert starts == sorted(starts) and len(set(starts)) == len(starts)
    sel2 = select_candidates(pre, FIX_LABELS, new_counters(), target=1)
    assert [x["qid"] for x in sel2] == ["Q910001"]

    # ④ 布局与旧域候选件逐字对齐(存在才查,离线安全)。
    ref = ROOT / "data" / "wikistate_candidates_P108.json"
    if ref.exists():
        ref0 = json.loads(ref.read_text(encoding="utf-8"))[0]
        assert list(ref0.keys()) == ["qid", "label", "sitelinks", "chain"]
        assert list(ref0["chain"][0].keys()) == ["position", "start", "end"]

    print("SMOKE OK: sparql syntax (label-availability pushdown) + "
          "detail-clean counters exact-match + selection depth-first + "
          "layout aligned")


# ── CLI ──────────────────────────────────────────────────────
def main():
    try:  # Windows GBK 控制台防线:人名含变音符不应打断落盘
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    apr = argparse.ArgumentParser(description=__doc__)
    mode = apr.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--fetch", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    apr.add_argument("--max-sitelinks", type=int, default=50,
                     help="知名度上限(probe 定标用;fetch 用定标终值)")
    apr.add_argument("--limit", type=int, default=400,
                     help="实体查询 LIMIT(默认 400)")
    apr.add_argument("--target", type=int, default=60,
                     help="清洗后保留实体数上限(任务书 40-60)")
    apr.add_argument("--overscan", type=int, default=90,
                     help="逐人明细预选池上限(深链优先排序后截取)")
    apr.add_argument("--out", default=None)
    args = apr.parse_args()

    if args.smoke:
        run_smoke()
        return
    if args.probe:
        run_probe(args.max_sitelinks, args.limit)
        return
    out = Path(args.out) if args.out else ROOT / "data" / f"newdom_{PROP}.json"
    run_fetch(args.max_sitelinks, args.target, args.limit, args.overscan, out)


if __name__ == "__main__":
    main()
