# -*- coding: utf-8 -*-
"""批 47 评分(零 API):三项修复的离线判据。

  --part entail : 从 results/wt_cards_v48e_ent(全部卡 + 蕴含标签)派生四个过滤变体,
                  比较 金标行漏失 / 车道多出行 / 编译上限(b46d 口径,560 题)
  --part slim   : results/wt_cards_v50s(精简 schema,36 链)对 v47s(同 36 链、同抽取器、
                  完整 schema):编译上限(140 题)、金标行、建店 token
  --part valnorm: results/b47_smoc_v48fc_haiku_run1.jsonl 对 b46d 的 v48f run1/run2:
                  准确率、配对 McNemar、受值规范化影响的题子集
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from math import comb
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade"); sys.path.insert(0, r"D:\ZZL_cluade\scripts")
import b38e_score as B  # noqa: E402
import b46d_build_v48f as F  # noqa: E402  (keep(): 38-E 关键词断言过滤,逐字复用)

ROOT = Path(r"D:\ZZL_cluade")
ENTS = {e["uid"]: e for e in json.load(open(ROOT / "data/wikistate_full_ALL_v24.json", encoding="utf-8"))}


def load_q(path):
    qs = [json.loads(l) for l in open(ROOT / path, encoding="utf-8") if l.strip()]
    by = {}
    for q in qs:
        by.setdefault(q["uid"], []).append(q)
    return qs, by


def ceiling_and_diag(store_dir, qs_by_uid):
    n_eq = n_tot = 0; by_t = Counter(); by_tt = Counter()
    exact = missing = extra = 0; miss_uids = {}
    for uid in ENTS:
        try:
            e_, d0, m, x, lane_slots, _n, rows = B.diag_uid(uid, ENTS[uid], store_dir)
        except FileNotFoundError:
            continue
        exact += e_; missing += m; extra += x; miss_uids[uid] = m
        lane = set(lane_slots); lane_rows = [(dd, r) for dd, r in rows if (r.get("slot") or "?") in lane]
        for q in qs_by_uid.get(uid, []):
            comp = B.compiled_answer(q["qtype"], q["question"], lane_rows)
            eq = B.gold_equal(q["qtype"], q["gold"], comp)
            n_tot += 1; by_tt[q["qtype"]] += 1; n_eq += eq; by_t[q["qtype"]] += eq
    return {"eq": n_eq, "tot": n_tot, "by_t": dict(by_t), "by_tt": dict(by_tt),
            "exact": exact, "missing": missing, "extra": extra, "miss_uids": miss_uids}


def write_variant(src_dir, dst_dir, pred):
    dst_dir.mkdir(parents=True, exist_ok=True)
    n = k = 0
    for f in sorted(src_dir.glob("*.json")):
        j = json.load(open(f, encoding="utf-8"))
        recs = [r for r in j["records"] if pred(r)]
        n += len(j["records"]); k += len(recs)
        j2 = dict(j); j2["records"] = recs
        json.dump(j2, open(dst_dir / f.name, "w", encoding="utf-8"), ensure_ascii=False)
    return n, k


def part_entail():
    qs, by = load_q("data/wsc_s5_v25.jsonl")
    src = ROOT / "results/wt_cards_v48e_ent"
    tmp = Path(tempfile.mkdtemp(prefix="b47ent_", dir=r"C:\Users\25243\AppData\Local\Temp\claude"))
    variants = {
        "v48 base (no filter)": lambda r: True,
        "keyword filter (38-E rules)": lambda r: F.keep(r),
        "entail: drop plan/task/other/hypo/ended, keep restate": lambda r: r.get("entailed", True) and r.get("assertion_type", "start") not in ("plan", "task", "other_person", "hypothetical", "ended"),
        "entail: also drop restate": lambda r: r.get("entailed", True) and r.get("assertion_type", "start") in ("start", "unclear", "unjudged"),
        "entail: drop by TYPE only (plan/task/other/hypo/ended), ignore entailed flag": lambda r: r.get("assertion_type", "start") not in ("plan", "task", "other_person", "hypothetical", "ended"),
        "entail: drop by TYPE only + restate": lambda r: r.get("assertion_type", "start") in ("start", "unclear", "unjudged"),
        "entail + keyword (both must keep)": lambda r: F.keep(r) and r.get("entailed", True) and r.get("assertion_type", "start") not in ("plan", "task", "other_person", "hypothetical", "ended"),
    }
    base_miss = None
    print(f"questions {len(qs)}; source {src}")
    print("variant | cards kept | gold exact | missing | lane extra | ceiling | per type")
    for name, pred in variants.items():
        d = tmp / name.split(" ")[0].replace(":", "")
        d = tmp / str(abs(hash(name)))
        n, k = write_variant(src, d, pred)
        r = ceiling_and_diag(str(d), by)
        flips = 0
        if base_miss is None:
            base_miss = r["miss_uids"]
        else:
            flips = sum(max(0, r["miss_uids"][u] - base_miss.get(u, 0)) for u in r["miss_uids"])
        per = ", ".join(f"{t} {r['by_t'].get(t,0)}/{r['by_tt'][t]}" for t in sorted(r["by_tt"]))
        print(f"{name} | {k}/{n} | {r['exact']}/542 | {r['missing']} (new hit->miss {flips}) | {r['extra']} | {r['eq']}/{r['tot']} = {100*r['eq']/r['tot']:.1f}% | {per}")
    # 标签分布
    types = Counter(); ent_false = 0
    for f in src.glob("*.json"):
        for r in json.load(open(f, encoding="utf-8"))["records"]:
            types[r.get("assertion_type")] += 1; ent_false += not r.get("entailed", True)
    print("label distribution:", dict(types), "entailed=false:", ent_false)
    shutil.rmtree(tmp, ignore_errors=True)


def part_slim():
    qs, by = load_q("results/b35_questions_sample36.jsonl")
    print(f"questions {len(qs)} on 36 chains")
    for store in ("results/wt_cards_v47s", "results/wt_cards_v47skf", "results/wt_cards_v50s", "results/wt_cards_v50s2"):
        d = ROOT / store
        if not d.exists():
            print(store, "absent"); continue
        r = ceiling_and_diag(str(d), by)
        ui = uo = n = cards = chars = 0
        for f in d.glob("*.json"):
            j = json.load(open(f, encoding="utf-8")); n += 1
            ui += j.get("usage_in", 0); uo += j.get("usage_out", 0); cards += len(j["records"])
            chars += sum(len(json.dumps(x, ensure_ascii=False)) for x in j["records"])
        per = ", ".join(f"{t} {r['by_t'].get(t,0)}/{r['by_tt'][t]}" for t in sorted(r["by_tt"]))
        print(f"{store}: stores {n}, cards {cards}, chars/card {chars/max(1,cards):.0f}, build in/out per store {ui/max(1,n):.0f}/{uo/max(1,n):.0f} | gold exact {r['exact']}/133 missing {r['missing']} extra {r['extra']} | ceiling {r['eq']}/{r['tot']} = {100*r['eq']/r['tot']:.1f}% | {per}")


def mcnemar(a, b):
    """a, b: dict qid -> bool;精确二项符号检验 p。"""
    keys = sorted(set(a) & set(b))
    ao = sum(1 for k in keys if a[k] and not b[k]); bo = sum(1 for k in keys if b[k] and not a[k])
    n = ao + bo
    if n == 0:
        return len(keys), ao, bo, 1.0
    p = sum(comb(n, i) for i in range(0, min(ao, bo) + 1)) / 2 ** n * 2
    return len(keys), ao, bo, min(1.0, p)


def part_valnorm():
    def load(path):
        d = {}
        for l in open(ROOT / path, encoding="utf-8"):
            if l.strip():
                r = json.loads(l); d[r["question_id"]] = bool(r["judge_correct"])
        return d
    new = load("results/b47_smoc_v48fc_haiku_run1.jsonl")
    r1 = load("results/b46d_smoc_v48f_haiku_run1.jsonl"); r2 = load("results/b46d_smoc_v48f_haiku_run2.jsonl")
    qs, _ = load_q("data/wsc_s5_v25.jsonl"); qt = {q["qid"]: q["qtype"] for q in qs}; qu = {q["qid"]: q["uid"] for q in qs}
    # 受影响的链:v48fc 里有 value_raw 的店
    aff = set()
    for f in (ROOT / "results/wt_cards_v48fc").glob("*.json"):
        j = json.load(open(f, encoding="utf-8"))
        if any("value_raw" in r for r in j["records"]):
            aff.add(j["uid"])
    acc = lambda d: 100 * sum(d.values()) / len(d)
    print(f"v48fc run1: n={len(new)} acc={acc(new):.2f} | v48f run1 {acc(r1):.2f} run2 {acc(r2):.2f}")
    for name, base in (("v48f run1", r1), ("v48f run2", r2)):
        n, ao, bo, p = mcnemar(new, base)
        print(f"  paired vs {name}: n={n} v48fc-only-right={ao} base-only-right={bo} delta={100*(ao-bo)/n:+.2f}pp McNemar p={p:.3f}")
    sub = [q for q in new if qu[q] in aff]
    print(f"  affected chains {len(aff)} / questions {len(sub)}: v48fc {100*sum(new[q] for q in sub)/max(1,len(sub)):.1f} vs run1 {100*sum(r1[q] for q in sub)/max(1,len(sub)):.1f} vs run2 {100*sum(r2[q] for q in sub)/max(1,len(sub)):.1f}")
    for t in sorted(set(qt.values())):
        ks = [q for q in new if qt[q] == t]
        print(f"  {t:15s} v48fc {100*sum(new[q] for q in ks)/len(ks):.1f} | run1 {100*sum(r1[q] for q in ks)/len(ks):.1f} | run2 {100*sum(r2[q] for q in ks)/len(ks):.1f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--part", choices=["entail", "slim", "valnorm"], required=True)
    a = ap.parse_args()
    {"entail": part_entail, "slim": part_slim, "valnorm": part_valnorm}[a.part]()
