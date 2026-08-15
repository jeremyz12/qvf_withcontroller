# -*- coding: utf-8 -*-
"""新域建材·步骤1:单属性多值实体抓取 + 机械清洗(search API + EntityData)。

用途:零改动新域测试(study_logs/QVF_coupling_audit_20260815.md §三)的
建材线。目标属性如 P69(就读学校,闭集外)/ P1303(演奏乐器)/
P26(配偶,阳性对照)。系统侧(qvf_router / wt_qvf_prototype /
complex_query_arm)一行不改;本脚本是数据侧新件,不在被审对象内。

路线:与旧域 scripts/wikistate_scrape.py 完全同源 —— Wikidata 搜索 API
(haswbstatement:{PROP})分页 → 逐实体 Special:EntityData → 本地过滤。
候选采样与旧域同一管线,"闭集内 vs 闭集外"保持受控变量。
(先试过 WDQS SPARQL 聚合:person-first 与 qualifier-first 子查询均 504
超时;纯聚合可过但结果无序不可复现 —— 弃,证据记 meta。)

与旧线的两处口径放宽(新域属性的数据现实,记录在案):
  - 时间限定符:开始 = P580 或 P585(旧单属性线强制 P580+P582 双全;
    S6 多属性线已放宽为 P580/P585,此处同 S6 口径);P582 结束可选;
    仅有 P582(只有结束日期)的陈述视作"缺开始日期"剔除并计数
    (宣告式渲染需要开始日期作会话日期)。
  - 链深门槛:MIN_CHAIN_NEW = 2(多值;旧线为 3)。选取时链深降序
    优先(同任务书"链深≥2 优先"),再 sitelinks 升序、qid 定序。

机械清洗(逐项计数,全部入 meta;任务口径"乱序/缺日期/单值剔除并计数"):
  - 缺日期:无 P580/P585 开始限定符的陈述(含仅 P582 者);
  - 非法 start(BCE 负年份等)剔除;值缺失(somevalue)剔除;
  - end <= start(乱序·区间倒置)剔除;
  - 同值重复(按 QID)去重保首见;
  - start 严格递增,同日并列(乱序·不可排序)剔除;
  - 标签清洗:无英文标签(裸 QID)剔除、同标签不同 QID 去重保首见;
  - 清洗后不同值 < MIN_CHAIN_NEW → 整人剔除(单值剔除)。

低知名度沿旧线:sitelinks <= MAX_SITELINKS(=5)。部分日期(2003-00-00)
不归一,与旧域候选件同款保留(下游 parse_partial_date 两种形态都吃)。

输出:
  data/newdom_{PROP}.json       —— 链 JSON,布局与旧域候选件逐字同构
                                   (人级 {qid,label,sitelinks,chain},
                                   链步 {position,start,end});
  data/newdom_{PROP}.meta.json  —— 清洗计数/链深分布/限定符覆盖/命令行。

用法:
  python scripts/newdom_scrape.py --probe --prop P69 --scan 150
  python scripts/newdom_scrape.py --fetch --prop P69 --target 60 \
      [--overscan 80] [--scan-cap 1500]
  python scripts/newdom_scrape.py --smoke
"""
import argparse
import ast
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 与 scripts/wikistate_scrape.py 逐字一致(复制而非导入;--smoke 断言)──
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
SEARCH = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
MAX_SITELINKS = 5
# ──────────────────────────────────────────────────────────────
MIN_CHAIN_NEW = 2          # 新域门槛:多值(>=2);旧域单属性线为 3
API = SEARCH               # wbgetentities 标签解析同端点


# ── 网络层(--probe/--fetch 才走;--smoke 全程不触碰)─────────
def _get(url, params=None, timeout=30, max_attempts=4):
    """礼貌抓取 + 429/5xx 退避重试(尊重 Retry-After)。"""
    import requests  # 懒导入:--smoke / py_compile 不需要网络栈
    for attempt in range(max_attempts):
        r = requests.get(url, params=params, headers=UA, timeout=timeout)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == max_attempts - 1:
                r.raise_for_status()
            retry_after = r.headers.get("Retry-After")
            wait = (int(retry_after) if retry_after and retry_after.isdigit()
                    else 15 * (attempt + 1))
            print(f"HTTP {r.status_code}, backoff {wait}s "
                  f"(attempt {attempt + 1}/{max_attempts})", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


def resolve_labels(qids) -> dict:
    """wbgetentities 批量英文标签,承 wikistate_build.resolve_labels。"""
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        data = _get(API, params={
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "labels", "languages": "en", "format": "json"})
        for qid, ent in data.get("entities", {}).items():
            labels[qid] = ent.get("labels", {}).get("en", {}).get("value", qid)
        time.sleep(0.2)
    return labels


# ── 陈述抽取 + 机械清洗(纯函数,罐头可冒烟)──────────────────
def _qual_time(qualifiers: dict, pid: str):
    try:
        return qualifiers[pid][0]["datavalue"]["value"]["time"]
    except Exception:
        return None


def extract_steps(claims: dict, prop: str, counters: dict):
    """EntityData claims → (n_all, raw_steps [{position,start,end}])。

    开始 = P580 或 P585(先到先得);缺开始 → missing_date;BCE 负年份
    → bad_start;值缺失(somevalue/novalue)→ missing_value。"""
    steps, n_all = [], 0
    for st in claims.get(prop, []):
        n_all += 1
        q = st.get("qualifiers", {})
        t = _qual_time(q, "P580") or _qual_time(q, "P585")
        if t is None:
            counters["missing_date"] += 1
            continue
        if not str(t).startswith("+") or not str(t)[1:5].isdigit():
            counters["bad_start"] += 1        # BCE / 畸形时间
            continue
        try:
            val = st["mainsnak"]["datavalue"]["value"]["id"]
        except Exception:
            counters["missing_value"] += 1
            continue
        end = _qual_time(q, "P582")
        if end is not None and (not str(end).startswith("+")
                                or not str(end)[1:5].isdigit()):
            end = None
        steps.append({"position": val, "start": str(t)[1:11],
                      "end": str(end)[1:11] if end else None})
    return n_all, steps


def clean_chain(steps, counters: dict) -> list:
    """raw_steps → 清洗后链步(升序、同值去重、同日并列剔除、区间倒置
    剔除)。计数键:disorder_end_before_start、dup_value、tie_start。"""
    kept = []
    for s in steps:
        if s["end"] is not None and s["end"] <= s["start"]:
            counters["disorder_end_before_start"] += 1   # 乱序:区间倒置
            continue
        kept.append(dict(s))
    kept.sort(key=lambda s: (s["start"], s["position"]))
    out, seen_vals = [], set()
    for s in kept:
        if s["position"] in seen_vals:
            counters["dup_value"] += 1        # 同值重复陈述
            continue
        if out and s["start"] <= out[-1]["start"]:
            counters["tie_start"] += 1        # 乱序:同日并列,不可严格排序
            continue
        seen_vals.add(s["position"])
        out.append(s)
    return out


def label_clean(chain, labels, counters: dict) -> list:
    """标签清洗:裸 QID 标签剔除、同标签去重保首见(不同 QID 同名等)。
    标签不入库(渲染阶段再解析),布局保持 {position,start,end}。"""
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
    return {"missing_date": 0, "bad_start": 0, "missing_value": 0,
            "disorder_end_before_start": 0, "dup_value": 0, "tie_start": 0,
            "no_label": 0, "dup_label": 0,
            "single_after_clean": 0, "sitelinks_reject": 0}


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


# ── 扫描(search API 分页 + EntityData 逐实体)────────────────
def scan(prop: str, counters: dict, overscan: int, scan_cap: int,
         verbose=True):
    """返回 (pre_candidates, scanned, offset)。pre 候选:sitelinks 过滤 +
    机械清洗后链深 >= MIN_CHAIN_NEW(标签清洗在终选阶段)。"""
    pre, seen = [], set()
    offset, scanned = 0, 0
    while len(pre) < overscan and scanned < scan_cap and offset < 10000:
        data = _get(SEARCH, params={
            "action": "query", "list": "search", "format": "json",
            "srsearch": f"haswbstatement:{prop}", "srnamespace": 0,
            "srlimit": 50, "sroffset": offset})
        hits = data.get("query", {}).get("search", [])
        if not hits:
            break
        offset += 50
        for h in hits:
            qid = h["title"]
            if qid in seen or not qid.startswith("Q"):
                continue
            seen.add(qid)
            if len(pre) >= overscan or scanned >= scan_cap:
                break
            scanned += 1
            try:
                ent = _get(ENTITY.format(qid=qid))["entities"][qid]
            except Exception:
                continue
            sl = len(ent.get("sitelinks", {}))
            if sl > MAX_SITELINKS:
                counters["sitelinks_reject"] += 1
                time.sleep(0.15)
                continue
            _, steps = extract_steps(ent.get("claims", {}), prop, counters)
            chain = clean_chain(steps, counters)
            if len(chain) < MIN_CHAIN_NEW:
                counters["single_after_clean"] += 1
                time.sleep(0.15)
                continue
            label = ent.get("labels", {}).get("en", {}).get("value", qid)
            pre.append({"qid": qid, "label": label, "sitelinks": sl,
                        "chain": chain})
            if verbose:
                print(f"[{len(pre):3d}] {qid} {label} sl={sl} "
                      f"chain={len(chain)} (scanned {scanned})", flush=True)
            time.sleep(0.15)
        time.sleep(0.3)
    return pre, scanned, offset


# ── --probe ──────────────────────────────────────────────────
def run_probe(prop: str, scan_n: int):
    counters = new_counters()
    t0 = time.time()
    pre, scanned, offset = scan(prop, counters, overscan=10 ** 9,
                                scan_cap=scan_n, verbose=False)
    print(f"probe {prop}: scanned={scanned} pre_hits={len(pre)} "
          f"({100 * len(pre) / max(1, scanned):.1f}%) offset={offset} "
          f"t={time.time() - t0:.0f}s counters={counters}")


# ── --fetch ──────────────────────────────────────────────────
def run_fetch(prop: str, target: int, overscan: int, scan_cap: int,
              out_path: Path):
    counters = new_counters()
    t0 = time.time()
    pre, scanned, offset = scan(prop, counters, overscan, scan_cap)
    print(f"scan done: {len(pre)} pre-candidates from {scanned} scanned "
          f"({time.time() - t0:.0f}s); resolving value labels...", flush=True)
    value_qids = sorted({s["position"] for c in pre for s in c["chain"]})
    labels = resolve_labels(value_qids)
    cands = select_candidates(pre, labels, counters, target)

    from collections import Counter
    depth = Counter(len(c["chain"]) for c in cands)
    qual = {"steps_total": sum(len(c["chain"]) for c in cands),
            "steps_with_end_P582": sum(1 for c in cands for s in c["chain"]
                                       if s.get("end"))}
    sls = Counter(c["sitelinks"] for c in cands)
    for c in cands:
        print(f"{c['qid']} {c['label']} sl={c['sitelinks']} "
              f"chain={len(c['chain'])}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cands, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    meta = {
        "prop": prop, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": " ".join(sys.argv),
        "route": ("search API haswbstatement + Special:EntityData, 与旧域 "
                  "wikistate_scrape.py 同源;WDQS SPARQL 聚合两种写法均 "
                  "504 超时、纯聚合无序不可复现,弃"),
        "max_sitelinks": MAX_SITELINKS, "min_chain_new": MIN_CHAIN_NEW,
        "qualifier_rule": "start=P580|P585(必需), end=P582(可选);仅 P582 计缺日期",
        "scanned": scanned, "search_offset": offset,
        "pre_candidates": len(pre), "candidates_written": len(cands),
        "target": target, "overscan": overscan, "scan_cap": scan_cap,
        "cleaning_counters": counters,
        "chain_depth_dist": {str(k): v for k, v in sorted(depth.items())},
        "sitelinks_dist": {str(k): v for k, v in sorted(sls.items())},
        "qualifier_coverage": qual,
        "selection_rule": "sort(-chain_depth, sitelinks asc, qid) top target",
        "note": ("布局与旧域候选件(wikistate_candidates*.json)逐字同构;"
                 "部分日期(YYYY-00-00)不归一,与旧域同款。"),
    }
    out_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"scanned={scanned} candidates={len(cands)} -> {out_path}")
    print(f"cleaning={counters}")
    print(f"depth_dist={dict(sorted(depth.items()))} qual={qual}")


# ── --smoke:零网络自检 ──────────────────────────────────────
def _scrape_consts() -> dict:
    src = (Path(__file__).resolve().parent / "wikistate_scrape.py"
           ).read_text(encoding="utf-8")
    out = {}
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("UA", "SEARCH", "MAX_SITELINKS")):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def _claim(val_qid, start=None, end=None, point=None, somevalue=False):
    """EntityData 形态的 P69 陈述罐头。"""
    st = {"mainsnak": ({"snaktype": "somevalue"} if somevalue else
                       {"snaktype": "value",
                        "datavalue": {"value": {"id": val_qid}}}),
          "qualifiers": {}}
    def _t(t):
        return [{"datavalue": {"value": {"time": t}}}]
    if start:
        st["qualifiers"]["P580"] = _t(start)
    if point:
        st["qualifiers"]["P585"] = _t(point)
    if end:
        st["qualifiers"]["P582"] = _t(end)
    return st


# 罐头:全清洗路径逐项踩到。
FIX_CLAIMS_A = {"P69": [
    _claim("Q100", start="+1991-09-01T00:00:00Z"),                # 正常
    _claim("Q100", point="+1991-09-01T00:00:00Z"),                # 同值重复
    _claim("Q101", start="+1995-09-01T00:00:00Z",
           end="+1994-01-01T00:00:00Z"),                          # 区间倒置
    _claim("Q102", start="+1995-09-01T00:00:00Z"),                # 正常
    _claim("Q103", start="+1995-09-01T00:00:00Z"),                # 同日并列
    _claim("Q104"),                                               # 缺日期
    _claim("Q105", end="+2004-06-30T00:00:00Z"),                  # 仅 P582
    _claim("Q106", start="-0350-01-01T00:00:00Z"),                # BCE
    _claim("Q107", start="+2005-00-00T00:00:00Z"),                # 部分日期,正常
    _claim(None, start="+2010-09-01T00:00:00Z", somevalue=True),  # 值缺失
]}
FIX_CLAIMS_B = {"P69": [
    _claim("Q200", start="+2001-09-01T00:00:00Z",
           end="+2004-06-30T00:00:00Z"),
    _claim("Q201", point="+2004-09-01T00:00:00Z"),                # P585 开始
]}
FIX_CLAIMS_DROP = {"P69": [   # 标签清洗后单值 → 整人剔除
    _claim("Q300", start="+2001-09-01T00:00:00Z"),
    _claim("Q301", start="+2003-09-01T00:00:00Z"),                # 无英文标签
]}
FIX_LABELS = {"Q100": "Northfield Grammar", "Q102": "Eastvale Academy",
              "Q107": "Harbor Polytechnic",
              "Q200": "Midtown Prep", "Q201": "Lakeside Institute",
              "Q300": "Q300-only School", "Q301": "Q301",
              "Q400": "Alpha Prep", "Q401": "Beta Institute",
              "Q402": "Gamma Polytechnic"}
FIX_CLAIMS_DEEP = {"P69": [
    _claim("Q400", start="+1980-09-01T00:00:00Z"),
    _claim("Q401", start="+1984-09-01T00:00:00Z"),
    _claim("Q402", start="+1988-09-01T00:00:00Z"),
]}


def run_smoke():
    # ① 抽取 + 机械清洗计数逐项核对(A 件踩全路径)。
    counters = new_counters()
    n_all, steps = extract_steps(FIX_CLAIMS_A, "P69", counters)
    assert n_all == 10, n_all
    chain = clean_chain(steps, counters)
    assert [s["position"] for s in chain] == ["Q100", "Q102", "Q107"], chain
    assert chain[0]["start"] == "1991-09-01" and chain[0]["end"] is None
    assert chain[2]["start"] == "2005-00-00", "部分日期应原样保留"
    assert counters["missing_date"] == 2, counters   # Q104 + 仅P582 Q105
    assert counters["bad_start"] == 1, counters      # BCE Q106
    assert counters["missing_value"] == 1, counters  # somevalue
    assert counters["disorder_end_before_start"] == 1, counters  # Q101
    assert counters["dup_value"] == 1, counters      # Q100 重复
    assert counters["tie_start"] == 1, counters      # Q103 并列

    # ② P585 可作开始(B 件);终选:标签清洗 + 深链优先 + 布局。
    cb = new_counters()
    _, steps_b = extract_steps(FIX_CLAIMS_B, "P69", cb)
    chain_b = clean_chain(steps_b, cb)
    assert [s["position"] for s in chain_b] == ["Q200", "Q201"], chain_b
    _, steps_d = extract_steps(FIX_CLAIMS_DROP, "P69", cb)
    chain_d = clean_chain(steps_d, cb)
    _, steps_deep = extract_steps(FIX_CLAIMS_DEEP, "P69", cb)
    chain_deep = clean_chain(steps_deep, cb)
    pre = [
        {"qid": "Q910001", "label": "Al Fixture", "sitelinks": 1,
         "chain": chain},
        {"qid": "Q910002", "label": "Bea Example", "sitelinks": 3,
         "chain": chain_b},
        {"qid": "Q910003", "label": "Cody Dropcase", "sitelinks": 0,
         "chain": chain_d},
        {"qid": "Q910004", "label": "Dee Deepchain", "sitelinks": 5,
         "chain": chain_deep},
    ]
    sel = select_candidates(pre, FIX_LABELS, cb, target=60)
    # Q910003 剔除(Q301 裸 QID → 1 值);深链优先:A(3)与 Deep(3)按
    # sitelinks 升序 → Q910001 先;Q910002(2)最后。
    assert [c["qid"] for c in sel] == ["Q910001", "Q910004", "Q910002"], sel
    assert cb["no_label"] == 1 and cb["single_after_clean"] == 1, cb
    for c in sel:
        assert list(c.keys()) == ["qid", "label", "sitelinks", "chain"]
        for s in c["chain"]:
            assert list(s.keys()) == ["position", "start", "end"]
        starts = [s["start"] for s in c["chain"]]
        assert starts == sorted(starts) and len(set(starts)) == len(starts)
    sel2 = select_candidates(pre, FIX_LABELS, new_counters(), target=2)
    assert [c["qid"] for c in sel2] == ["Q910001", "Q910004"]

    # ③ 布局与旧域候选件逐字对齐(存在才查,离线安全)。
    ref = ROOT / "data" / "wikistate_candidates_P108.json"
    if ref.exists():
        ref0 = json.loads(ref.read_text(encoding="utf-8"))[0]
        assert list(ref0.keys()) == ["qid", "label", "sitelinks", "chain"], \
            f"reference person layout drifted: {list(ref0.keys())}"
        assert list(ref0["chain"][0].keys()) == ["position", "start", "end"], \
            f"reference step layout drifted: {list(ref0['chain'][0].keys())}"

    # ④ UA / SEARCH / MAX_SITELINKS 与 wikistate_scrape.py 逐字一致。
    consts = _scrape_consts()
    assert consts == {"UA": UA, "SEARCH": SEARCH,
                      "MAX_SITELINKS": MAX_SITELINKS}, consts

    print(f"SMOKE OK: extract+clean counters exact-match, P585-start ok, "
          f"selection depth-first ok, layout aligned, ua_consts_equal=True")


# ── CLI ──────────────────────────────────────────────────────
def main():
    apr = argparse.ArgumentParser(description=__doc__)
    mode = apr.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--fetch", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    apr.add_argument("--prop", default="P69",
                     help="目标属性(默认 P69 就读学校)")
    apr.add_argument("--scan", type=int, default=150,
                     help="probe 模式扫描实体数(默认 150)")
    apr.add_argument("--target", type=int, default=60,
                     help="清洗后保留实体数上限(默认 60,任务书 40-60)")
    apr.add_argument("--overscan", type=int, default=80,
                     help="预选池上限(默认 80,供深链优先终选)")
    apr.add_argument("--scan-cap", type=int, default=1500,
                     help="扫描实体数上限(默认 1500)")
    apr.add_argument("--out", default=None,
                     help="输出路径(默认 data/newdom_{PROP}.json)")
    args = apr.parse_args()

    if args.smoke:
        run_smoke()
        return
    if args.probe:
        run_probe(args.prop, args.scan)
        return
    out = Path(args.out) if args.out else ROOT / "data" / f"newdom_{args.prop}.json"
    run_fetch(args.prop, args.target, args.overscan, args.scan_cap, out)


if __name__ == "__main__":
    main()
