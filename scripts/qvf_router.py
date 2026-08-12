# -*- coding: utf-8 -*-
"""QVF-Router v1:调用门 + 读取时/写入时按题路由的整合系统评测。

路由决策逐题真算(mini 聚焦调用 + 卡片库链深查表,均为部署可用信号);
答案从既有三臂结果按题组合——路由为确定性函数,组合即整合系统输出。
路由规则(原则先行,不做数据调参):
  ① scope=unclear 且无预设值 → direct(调用门:非时序直通)
  ② 聚焦槽位在卡片库中的不同取值数 ≥3(深链) → wt(档案卡裁决)
  ③ 其余(浅更新/杂讯库) → rt(检索后现场抽取)
臂缺行时按 rt→direct 降级并计数。"""
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from scripts.wt_qvf_prototype import (FOCUS_PROMPT, QueryFocusMini, _norm,  # noqa: E402
                                      _slot_match)

CARDS = Path(r"results/wt_cards")
CACHE_F = Path(r"results/router_focus_cache.json")
MODEL = "claude-haiku-4-5"


def normkey(k):
    k = re.sub(r"_query$", "", k)
    m = re.match(r"(.+?)_(dim\d)", k)
    if m:
        return f"{m.group(1)}|{m.group(2)}"
    return re.sub(r"_q1$", "", k)


def load_arm(path, mode=None):
    d = {}
    if not Path(path).exists():
        return d
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if not s:
            continue
        r = json.loads(s)
        if "error" in r:
            continue
        if mode and r.get("mode") != mode:
            continue
        d[normkey(r["question_id"])] = bool(r.get("judge_correct"))
    return d


BENCHES = [
    # name, data(chain-schema), direct, rt, wt   (None = 无该臂)
    ("chain-212", "data/stale_chain_full.json",
     ("results/framing_chain_h45.jsonl", None),
     ("results/framing_qvf_chain_h45.jsonl", None),
     ("results/wtqvf3_chain_h45.jsonl", None)),
    ("confirm-228", "data/stale_chain_confirm.json",
     ("results/framing_direct_confirm_h45.jsonl", None),
     ("results/framing_qvf_confirm_h45.jsonl", None),
     ("results/wtqvf3_confirm.jsonl", None)),
    ("stale-150", "data/stale400_s50_wt.json",
     ("results/framing_stale50_h45.jsonl", None),
     ("results/framing_qvf_stale50_h45.jsonl", None),
     ("results/wtqvf3_stale50.jsonl", None)),
    ("wiki-P39", "data/wikistate_full.json",
     ("results/wiki_direct_h45.jsonl", None),
     ("results/wiki_qvf_h45.jsonl", None),
     ("results/wiki_wtqvf3_test.jsonl", None)),
    ("wiki-P39-ext", "data/wikistate_full_P39_ext.json",
     ("results/wiki_direct_P39_ext.jsonl", None),
     ("results/wiki_qvf_P39_ext.jsonl", None),
     ("results/wiki_wtqvf3_P39_ext.jsonl", None)),
    ("wiki-P108-w2", "data/wikistate_full_P108_w2.json",
     ("results/wiki_direct_P108_w2.jsonl", None),
     ("results/wiki_qvf_P108_w2.jsonl", None),
     ("results/wiki_wtqvf3_P108_w2.jsonl", None)),
    ("wiki-P108-ext", "data/wikistate_full_P108_ext.json",
     ("results/wiki_direct_P108_ext.jsonl", None),
     ("results/wiki_qvf_P108_ext.jsonl", None),
     ("results/wiki_wtqvf3_P108_ext.jsonl", None)),
    ("wiki-P54-w2", "data/wikistate_full_P54_w2.json",
     ("results/wiki_direct_P54_w2.jsonl", None),
     ("results/wiki_qvf_P54_w2.jsonl", None),
     ("results/wiki_wtqvf3_P54_w2.jsonl", None)),
    ("wiki-P54-ext", "data/wikistate_full_P54_ext.json",
     ("results/wiki_direct_P54_ext.jsonl", None),
     ("results/wiki_qvf_P54_ext.jsonl", None),
     ("results/wiki_wtqvf3_P54_ext.jsonl", None)),
    ("wiki-P551", "data/wikistate_full_P551.json",
     ("results/wiki_direct_P551.jsonl", None), None,
     ("results/wiki_wtqvf3_P551.jsonl", None)),
    ("LME-TR", "data/lme_temporal_reasoning_wt.json",
     ("results/tr_full133.jsonl", "dense_direct"),
     ("results/final2_lmet_h45.jsonl", None),
     ("results/wtqvf3_lmetr.jsonl", None)),
    ("LME-KU", "data/lme_knowledge_update_wt.json",
     ("results/final2_lmek_h45.jsonl", "dense_direct"),
     ("results/final2_lmek_h45.jsonl", "minimal_rules_species2"),
     ("results/wtqvf3_lmeku.jsonl", None)),
    ("LoCoMo", "data/locomo_wt.json",
     ("results/locomo_direct_h45.jsonl", None),
     ("results/locomo_qvf_h45.jsonl", None),
     ("results/wtqvf3_locomo.jsonl", None)),
    # 全量原版考场(系统级整体测量;STALE 条目 50+ 无卡片库=冷库,深度0→rt)
    ("STALE-full", "data/stale400_full_wt.json",
     ("results/stale400_full_direct_v2.jsonl", None),
     ("results/stale400_full_qvf_v2.jsonl", None),
     ("results/wtqvf3_stale50.jsonl", None)),
    ("LoCoMo-full", "data/locomo_full.json",
     ("results/locomo_full_direct.jsonl", None),
     ("results/locomo_full_qvf.jsonl", None),
     ("results/wtqvf3_locomo_full.jsonl", None)),
]

cache = json.loads(CACHE_F.read_text(encoding="utf-8")) if CACHE_F.exists() else {}
client = anthropic.Anthropic()


def focus_of(bench, qid, question):
    key = f"{bench}|{qid}"
    if key in cache:
        return cache[key]
    out = {"slot": "", "scope": "unclear", "presupposed": ""}
    for _ in range(3):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=400, system=FOCUS_PROMPT,
                messages=[{"role": "user", "content": question}],
                output_format=QueryFocusMini)
            f = resp.parsed_output
            if f:
                out = {"slot": f.slot, "scope": f.scope,
                       "presupposed": f.presupposed_value}
                break
        except Exception:  # noqa: BLE001
            continue
    cache[key] = out
    return out


def chain_depth(uid, slot, presupposed=""):
    """v3 同款分量深度:关系边+槽位模糊匹配并查集 → 含聚焦槽位的最佳分量的
    不同取值数(无槽位命中时按预设值锚定)。"""
    f = CARDS / f"{uid}.json"
    if not f.exists():
        return 0
    recs = json.loads(f.read_text(encoding="utf-8")).get("records", [])
    n = len(recs)
    if not n:
        return 0
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    id2idx = {r.get("record_id"): i for i, r in enumerate(recs) if r.get("record_id")}
    for i, r in enumerate(recs):
        for t in (r.get("relation_target_record_ids") or []):
            j = id2idx.get(t)
            if j is not None:
                union(i, j)
    for i in range(n):
        for j in range(i + 1, n):
            if _slot_match(recs[i].get("slot", ""), recs[j].get("slot", "")):
                union(i, j)
    comps = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    pv = _norm(presupposed)

    def hits(idx):
        h = sum(1 for i in idx if _slot_match(recs[i].get("slot", ""), slot))
        if not h and pv:
            h = sum(1 for i in idx if pv and pv in _norm(recs[i].get("value", "")))
        return h

    def dated_vals(idx):
        return {_norm(recs[i].get("value", "")) for i in idx
                if recs[i].get("stated_date") and _norm(recs[i].get("value", ""))}

    best, best_score = None, -1
    for idx in comps.values():
        h = hits(idx)
        if h == 0:
            continue
        rel = sum(len(recs[i].get("relation_target_record_ids") or []) for i in idx)
        score = 4 * h + min(rel, 3)
        if score > best_score:
            best_score, best = score, idx
    comp_depth = len(dated_vals(best)) if best else 0
    # v1.3:所有含槽位命中的分量的带日期取值并集(修槽位词汇分裂低估;
    # 带日期要求防杂讯膨胀)
    hit_union = []
    for idx in comps.values():
        if hits(idx):
            hit_union.extend(idx)
    direct_idx = [i for i in range(n)
                  if _slot_match(recs[i].get("slot", ""), slot)]
    return max(comp_depth, len(dated_vals(hit_union)), len(dated_vals(direct_idx)))


def route(uid, focus):
    if focus["scope"] == "unclear" and not focus["presupposed"]:
        return "direct"
    depth = chain_depth(uid, focus["slot"], focus.get("presupposed", ""))
    if focus["scope"] in ("trajectory", "point_in_time"):
        return "wt" if depth >= 2 else "rt"
    return "wt" if depth >= 3 else "rt"


def main():
    grand = Counter()
    grand_router = grand_direct = grand_n = 0
    print(f"{'bench':14s} {'n':>4s} {'direct':>7s} {'rt':>6s} {'wt':>6s} "
          f"{'ROUTER':>7s}  路由分布(direct/rt/wt) 降级")
    for name, data_f, d_spec, r_spec, w_spec in BENCHES:
        arms = {}
        arms["direct"] = load_arm(*d_spec)
        arms["rt"] = load_arm(*r_spec) if r_spec else {}
        arms["wt"] = load_arm(*w_spec) if w_spec else {}
        items = json.loads(Path(data_f).read_text(encoding="utf-8"))
        qs = []
        for it in items:
            for dim, q in it.get("probing_queries", {}).items():
                qid = normkey(f"{it['uid']}_{dim}")
                qs.append((it["uid"], qid, q["q"]))
        # 整体测量口径:只要求兜底臂(direct)在场;路由臂缺行走降级链
        # (wt 仅部分覆盖的场次=冷库语义;P39 原卷仍限 test-52 由 wt 行天然决定)
        qs = [x for x in qs if x[1] in arms["direct"]]
        if name == "wiki-P39":  # dev-5 隔离:P39 原卷仍只评 test-52
            qs = [x for x in qs if x[1] in arms["wt"]]
        with ThreadPoolExecutor(max_workers=8) as ex:
            focuses = list(ex.map(lambda x: focus_of(name, x[1], x[2]), qs))
        CACHE_F.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        dist = Counter()
        fallback = 0
        correct = 0
        for (uid, qid, _q), fo in zip(qs, focuses):
            r = route(uid, fo)
            dist[r] += 1
            pick = r
            if qid not in arms[pick]:
                fallback += 1
                pick = "rt" if "rt" != r and qid in arms["rt"] else "direct"
                if qid not in arms[pick]:
                    pick = "direct"
            correct += bool(arms[pick].get(qid, False))
        n = len(qs)
        accs = {a: (sum(v for k, v in arms[a].items() if k in {q[1] for q in qs})
                    / n * 100 if arms[a] else float("nan")) for a in arms}
        racc = correct / n * 100 if n else 0
        print(f"{name:14s} {n:4d} {accs['direct']:6.1f}% "
              f"{(accs['rt'] if arms['rt'] else float('nan')):5.1f}% "
              f"{accs['wt']:5.1f}% {racc:6.1f}%  "
              f"{dist['direct']}/{dist['rt']}/{dist['wt']} 降级{fallback}")
        grand_router += correct
        grand_direct += sum(v for k, v in arms["direct"].items() if k in {q[1] for q in qs})
        grand_n += n
        for k, v in dist.items():
            grand[k] += v
    print(f"\nTOTAL n={grand_n}: direct {grand_direct/grand_n*100:.1f}% → "
          f"ROUTER {grand_router/grand_n*100:.1f}%  路由分布 {dict(grand)}")


if __name__ == "__main__":
    main()
