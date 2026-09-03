# -*- coding: utf-8 -*-
"""批 41 记分器:第二次抽取 + 联集 + 断言类型过滤后的 derived 店
results/wt_cards_v47skf2 在真实读者上的表现,对照 results/wt_cards_v47skf
(批 38-E)与 plainctx@sonnet5 mt4000(批 36)。

结构与函数逐字沿用 scripts/b38e_score.py(去重取首次出现;配对 McNemar =
精确二项符号检验;全部比较限制到 results/b35_questions_sample36.jsonl 的同
140 题)。本文件在其结构之上做的改动:

- 新增本批两条主臂:smoc_v47skf2@haiku(mt800,capped 行用同名
  _mt4000.jsonl 校正合并)、smoc_v47skf2@sonnet5(mt4000,单次)。
- 店级诊断(账目 vs 金标保真度 / 槽位车道 / 记录数)从四店(v45, v47s,
  v47sk, v47skf)扩成五店,新增 v47skf2。
- 配对 McNemar 新增:v47skf2 vs v47skf(两读者各一条)、v47skf2@sonnet5 vs
  plainctx mt4000、v47skf2@haiku vs v45@haiku。
- wikiP39037-Q3525068 三题(批 38-E 残留缺口)逐题现状,v47skf vs v47skf2。
- 抽取不稳定性:results/wt_cards_v47s(批 38,第一次抽取)vs
  results/wt_cards_v47s_pass2(本批,第二次抽取)在 3 条目标链上的逐卡
  差异统计。
- 成本汇总(读者臂 + 本批建店/联集的额外 API 花费)。

用法: PYTHONUTF8=1 python scripts/b41_score.py > results/b41_score_out.txt
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import acc, load, sign_p  # noqa: E402
from b38e_score import (compiled_answer, diag_uid, gold_equal,  # noqa: E402
                        nv, val_match, yr)

QREF = "results/b35_questions_sample36.jsonl"
CORPUS = "data/wikistate_full_ALL_v24.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
S5 = (2.00, 10.00)     # claude-sonnet-5 $/M in, out
H45 = (1.00, 5.00)     # claude-haiku-4-5 $/M in, out
TARGET_UIDS = ["wikiP39037-Q3525068", "wikiP39006-Q5220520",
               "wikiP39017-Q24568849"]

ARMS = [
    ("smoc_v47skf2@haiku (2nd-pass union+filter, mt800, capped-row corrected)",
     ["results/b41_smoc_v47skf2_haiku-4-5.jsonl",
      "results/b41_smoc_v47skf2_haiku-4-5_mt4000.jsonl"], H45, "haiku-4-5",
     "本批"),
    ("smoc_v47skf2@sonnet5(2nd-pass union+filter, mt4000)",
     ["results/b41_smoc_v47skf2_sonnet-5.jsonl"], S5, "sonnet-5", "本批"),
    ("smoc_v47skf@haiku  (assertion-filtered, 批38-E)",
     ["results/b38e_smoc_v47skf_haiku-4-5.jsonl",
      "results/b38e_smoc_v47skf_haiku-4-5_mt4000.jsonl"], H45, "haiku-4-5",
     "批38-E"),
    ("smoc_v47skf@sonnet5(assertion-filtered, 批38-E)",
     ["results/b38e_smoc_v47skf_sonnet-5.jsonl"], S5, "sonnet-5", "批38-E"),
    ("smoc_v47sk@haiku  (canon+date-refine, 批38-B)",
     ["results/b38b_smoc_v47sk_haiku-4-5.jsonl"], H45, "haiku-4-5", "批38-B"),
    ("smoc_v47sk@sonnet5(canon+date-refine, 批38-B)",
     ["results/b38b_smoc_v47sk_sonnet-5.jsonl"], S5, "sonnet-5", "批38-B"),
    ("smoc_v47s@haiku   (sonnet-5-built ledger, 批38)",
     ["results/b38_smoc_v47s_haiku-4-5.jsonl"], H45, "haiku-4-5", "批38"),
    ("smoc_v47s@sonnet5 (sonnet-5-built ledger, 批38)",
     ["results/b38_smoc_v47s_sonnet-5.jsonl"], S5, "sonnet-5", "批38"),
    ("smoc_v45@haiku    (haiku-built ledger, 批33-A)",
     ["results/b33A_smoc_v45.jsonl"], H45, "haiku-4-5", "批33-A"),
    ("smoc_v45@sonnet5  (haiku-built ledger, 批36-B)",
     ["results/b36b_smoc_sonnet5.jsonl"], S5, "sonnet-5", "批36-B"),
    ("plainctx@sonnet5  (trunc-corrected mt4000, 批36)",
     ["results/b36_plainctx_sonnet-5.jsonl",
      "results/b36_plainctx_sonnet-5_mt4000.jsonl"], S5, "sonnet-5", "批36"),
    ("plainctx@haiku    (full text, mt800, 批36)",
     ["results/b36_plainctx_haiku-4-5.jsonl"], H45, "haiku-4-5", "批36"),
]

STORES5 = [
    ("v45", "results/wt_cards_v45", "claude-haiku-4-5"),
    ("v47s", "results/wt_cards_v47s", "claude-sonnet-5"),
    ("v47sk", "results/wt_cards_v47sk", "claude-sonnet-5+canon"),
    ("v47skf", "results/wt_cards_v47skf", "claude-sonnet-5+canon+assertion-filter"),
    ("v47skf2", "results/wt_cards_v47skf2",
     "claude-sonnet-5+canon+2nd-pass-union(3 chains)+assertion-filter"),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def load_many(paths, keys):
    m = {}
    for p in paths:
        if not (ROOT / p).exists():
            continue
        m.update(restrict(load(p), keys))
    return m


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def stats(rows, pi, po):
    mi = st.mean([r.get("usage_input_tokens") or 0 for r in rows])
    mo = st.mean([r.get("usage_output_tokens") or 0 for r in rows])
    lat = st.median([r.get("latency_s") or 0 for r in rows])
    ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
    to = sum(r.get("usage_output_tokens") or 0 for r in rows)
    return mi, mo, lat, mi / 1e6 * pi + mo / 1e6 * po, ti / 1e6 * pi + to / 1e6 * po


def cap_count(paths, keys):
    d = load_many(paths, keys)
    have = [r for r in d.values() if "stop_reason" in r]
    if not have:
        return None
    capped = sum(1 for r in have if r.get("stop_reason") == "max_tokens")
    return capped, len(have)


def cmp2(name_a, a, name_b, b):
    keys = sorted(set(a) & set(b))
    if not keys:
        print("  %s vs %s : no overlap" % (name_a, name_b))
        return
    aw = sum(1 for q in keys if a[q]["judge_correct"] and not b[q]["judge_correct"])
    bw = sum(1 for q in keys if b[q]["judge_correct"] and not a[q]["judge_correct"])
    pa = sum(bool(a[q]["judge_correct"]) for q in keys) / len(keys) * 100
    pb = sum(bool(b[q]["judge_correct"]) for q in keys) / len(keys) * 100
    print("  n=%3d | A=%-52s %5.1f%%  B=%-52s %5.1f%% | delta(A-B) %+6.2fpp | "
          "A-only-right=%2d B-only-right=%2d | McNemar exact p=%.4g"
          % (len(keys), name_a, pa, name_b, pb, pa - pb, aw, bw, sign_p(aw, bw)))


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})
    qtype = {q["qid"]: q["qtype"] for q in qref}
    qs_by_uid = {}
    for q in qref:
        qs_by_uid.setdefault(q["uid"], []).append(q)

    print("# Batch 41 — extraction instability (2nd pass) on the 3 chains "
          "flagged by batch 38-D's variance table, real readers\n")
    print("Pre-registration: results/opt_batch41_prereg.md (written before "
          "any build/reader call). Ground-truth correction made there "
          "(§0): of the 3 flagged chains, only wikiP39037-Q3525068 actually "
          "has missing gold anchors in results/wt_cards_v47sk / v47skf (2 "
          "rows missing: 1784 '16th Parliament', 1794 'colonial governor of "
          "Guadeloupe'); wikiP39006-Q5220520 and wikiP39017-Q24568849 are "
          "already 3/3 and 5/5 in v47sk/v47skf (their anchor loss in the "
          "batch 38-D variance table is specific to the unrelated v45 "
          "144-chain haiku store).\n")
    print(f"Questions: {QREF} ({len(qids)} qids / {len(uids)} chains); "
          f"corpus {CORPUS} (v2.4).")
    print("Runner: scripts/lb_reader_arm_b36b.py --arm smoc --cards-dir "
          "results/wt_cards_v47skf2 --workers 4 (unchanged from batch "
          "36-B/38/38-B/38-E).")
    print("Store: results/wt_cards_v47skf2 — built by scripts/"
          "b41_build_v47skf2.py: for the 3 target chains, union "
          "results/wt_cards_v47sk cards with a fresh 2nd-pass extraction "
          "results/wt_cards_v47s_pass2 (scripts/wt_qvf_prototype_b38.py, "
          "identical command/env to the results/wt_cards_v47s build, only "
          "--cards-dir changed), dedupe key = (slot_class-or-slot, "
          "value-normalized, stated_date, source_span), then apply the "
          "same assertion-type filter as scripts/b38e_build_v47skf.py; the "
          "other 33 chains are copied byte-identical from "
          "results/wt_cards_v47skf. See results/b41_filter_log.json for "
          "the full union/drop log and hard-constraint check.\n")

    print("## 1. Accuracy / cost table (all restricted to the same 140 "
          "qids)\n")
    hdr = ("| arm | reader | note | n | acc | " + " | ".join(TYPES) +
           " | in tok | out tok | median lat s | $/q | $ total |")
    print(hdr)
    print("|" + "---|" * (11 + len(TYPES)))
    data = {}
    for name, paths, price, reader, note in ARMS:
        d = load_many(paths, qids)
        if not d:
            print(f"| {name} | {reader} | {note} | 0 | (missing: {paths}) |")
            continue
        data[name] = d
        mi, mo, lat, cpq, total = stats(list(d.values()), *price)
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| %s | %s | %s | %d | **%.1f%%** | %s | %.0f | %.0f | %.2f | "
              "$%.5f | $%.3f |"
              % (name, reader, note, len(d), acc(d), tys, mi, mo, lat, cpq,
                 total))

    print("\n### max_tokens 上限命中数(按 stop_reason 字段,凡该字段存在即报)\n")
    print("| arm | reader | capped rows | rows w/ stop_reason |")
    print("|---|---|---|---|")
    for name, paths, price, reader, note in ARMS:
        cc = cap_count(paths, qids)
        if cc is None:
            print(f"| {name} | {reader} | (no stop_reason field) | - |")
        else:
            capped, tot = cc
            print(f"| {name} | {reader} | {capped} | {tot} |")

    def g(k):
        return data.get(k)

    F2h = "smoc_v47skf2@haiku (2nd-pass union+filter, mt800, capped-row corrected)"
    F2s = "smoc_v47skf2@sonnet5(2nd-pass union+filter, mt4000)"
    Fh = "smoc_v47skf@haiku  (assertion-filtered, 批38-E)"
    Fs = "smoc_v47skf@sonnet5(assertion-filtered, 批38-E)"
    Vh = "smoc_v45@haiku    (haiku-built ledger, 批33-A)"
    Pm4 = "plainctx@sonnet5  (trunc-corrected mt4000, 批36)"

    print("\n## 2. Paired McNemar (exact binomial sign test) on the 140 "
          "ids\n")
    print("Task-specified / prereg comparisons:")
    for a, b in [(F2h, Fh), (F2s, Fs), (F2s, Pm4), (F2h, Vh)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))
    print("\nSupporting comparisons:")
    for a, b in [(F2s, F2h)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))

    print("\n## 3. The three wikiP39037-Q3525068 questions (batch 38-E's "
          "残留缺口) — status under v47skf2\n")
    print("| qid | type | gold | v47skf@h | v47skf@s5 | v47skf2@h | "
          "v47skf2@s5 |")
    print("|---|---|---|---|---|---|---|")
    p37 = [q for q in sorted(qids) if q.startswith("wikiP39037-Q3525068")]
    for q in p37:
        def mark(name):
            d = g(name)
            if not d or q not in d:
                return "?"
            return "OK" if d[q]["judge_correct"] else "X"
        gold = None
        for arm_name in (Fh, Fs, F2h, F2s):
            if g(arm_name) and q in g(arm_name):
                gold = g(arm_name)[q]["gold_answer"]
                break
        print("| `%s` | %s | %r | %s | %s | %s | %s |"
              % (q, qtype.get(q, "?"), gold, mark(Fh), mark(Fs), mark(F2h),
                 mark(F2s)))

    print("\n## 4. Write-side diagnostic: compiled ledger vs gold chain "
          "(five stores)\n")
    corpus = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}
    agg = {}
    diag_full = {}
    for tag, store, _extr in STORES5:
        tot = Counter()
        per = {}
        for u in uids:
            e, d0, m, x, lane, nrec, rows = diag_uid(u, ents[u], store)
            diag_full[(tag, u)] = (e, d0, m, x, lane, nrec, rows)
            per[u] = (e, d0, m, x, lane, nrec)
            tot["exact"] += e; tot["date_off"] += d0
            tot["missing"] += m; tot["extra"] += x
            tot["gold"] += len(ents[u].get("chain") or [])
            tot["records"] += nrec
        agg[tag] = (tot, per)
    print("| store | extractor | gold rows | exact | date-off | missing | "
          "extra | total cards | perfect chains |")
    print("|---|---|---|---|---|---|---|---|---|")
    for tag, store, extr in STORES5:
        tot, per = agg[tag]
        perfect = sum(1 for u in uids
                      if per[u][2] == 0 and per[u][1] == 0
                      and per[u][0] == len(ents[u].get("chain") or []))
        print("| %s | %s | %d | **%d** (%.1f%%) | %d | **%d** | %d | %d | "
              "%d/%d |"
              % (tag, extr, tot["gold"], tot["exact"],
                 tot["exact"] / max(1, tot["gold"]) * 100,
                 tot["date_off"], tot["missing"], tot["extra"],
                 tot["records"], perfect, len(uids)))

    print("\n### 4b. Gold-anchor status on the 3 target chains, all five "
          "stores (exact/gold)\n")
    print("| uid | gold | v45 | v47s | v47sk | v47skf | v47skf2 |")
    print("|---|---|---|---|---|---|---|")
    for u in TARGET_UIDS:
        row = [f"{diag_full[(tag, u)][0]}/{len(ents[u].get('chain') or [])}"
               for tag, _s, _e in STORES5]
        print("| %s | %d | %s |" % (u, len(ents[u].get("chain") or []),
                                    " | ".join(row)))

    print("\n### 4c. Compiled-answer ceiling (offline, zero API — a "
          "reader that never makes a reasoning error, reading only this "
          "ledger) — v47skf vs v47skf2, H2 target >= 139/140\n")
    print("| store | gold-equal | change_count | count_before | "
          "first_vs_last | longest_tenure |")
    print("|---|---|---|---|---|---|")
    for tag in ("v47sk", "v47skf", "v47skf2"):
        n_eq = n_tot = 0
        by_t = Counter(); by_t_tot = Counter()
        for u in uids:
            _e, _d0, _m, _x, lane_slots, _nrec, rows = diag_full[(tag, u)]
            lane_set = set(lane_slots)
            lane_rows = [(dd, r) for dd, r in rows
                         if (r.get("slot") or "?") in lane_set]
            for q in qs_by_uid.get(u, []):
                comp = compiled_answer(q["qtype"], q["question"], lane_rows)
                eq = gold_equal(q["qtype"], q["gold"], comp)
                n_tot += 1; by_t_tot[q["qtype"]] += 1
                if eq:
                    n_eq += 1; by_t[q["qtype"]] += 1
        print("| %s | **%d/%d** | %s |"
              % (tag, n_eq, n_tot,
                 " | ".join(f"{by_t[t]}/{by_t_tot[t]}" for t in TYPES)))

    print("\n## 5. Extraction instability: pass 1 (results/wt_cards_v47s) "
          "vs pass 2 (results/wt_cards_v47s_pass2) on the 3 target chains\n")
    print("Same script (scripts/wt_qvf_prototype_b38.py), same env "
          "(QVF_CARD_MODEL=claude-sonnet-5, QVF_CARD_THINKING=off, "
          "max_tokens=16000, one call per chain), same corpus — the only "
          "difference between the two card sets is which API call "
          "happened to run (temperature=0 is not sent for sonnet-5, so "
          "run-to-run variance is real nondeterminism, not a seed "
          "artifact).\n")
    print("| uid | pass1 n | pass2 n | pass1-only (by slot,value,date) | "
          "pass2-only | common | pass1 gold-exact | pass2 gold-exact |")
    print("|---|---|---|---|---|---|---|---|")

    def key3(r):
        return (nv(r.get("slot")), nv(r.get("value")),
                (r.get("stated_date") or ""))

    for u in TARGET_UIDS:
        p1 = json.loads((ROOT / "results/wt_cards_v47s" / f"{u}.json")
                        .read_text(encoding="utf-8"))["records"]
        p2 = json.loads((ROOT / "results/wt_cards_v47s_pass2" / f"{u}.json")
                        .read_text(encoding="utf-8"))["records"]
        k1 = Counter(key3(r) for r in p1)
        k2 = Counter(key3(r) for r in p2)
        common = sum((k1 & k2).values())
        only1 = sum((k1 - k2).values())
        only2 = sum((k2 - k1).values())
        e1 = diag_full[("v47s", u)][0]
        # pass2 alone gold-exact recomputed directly (not in STORES5 loop)
        e2, _d2, _m2, _x2, _lane2, _n2, _rows2 = diag_uid(
            u, ents[u], "results/wt_cards_v47s_pass2")
        print("| %s | %d | %d | %d | %d | %d | %d/%d | %d/%d |"
              % (u, len(p1), len(p2), only1, only2, common,
                 e1, len(ents[u].get("chain") or []),
                 e2, len(ents[u].get("chain") or [])))

    print("\n## 6. Cost summary\n")
    print("### 6.1 Reader-arm cost (usage tokens, this batch's two arms)\n")
    print("| arm | reader | in tok total | out tok total | $ |")
    print("|---|---|---|---|---|")
    reader_total = 0.0
    for name, paths, price, reader, note in ARMS[:2]:
        d = load_many(paths, qids)
        ti = sum(r.get("usage_input_tokens") or 0 for r in d.values())
        to = sum(r.get("usage_output_tokens") or 0 for r in d.values())
        usd = ti / 1e6 * price[0] + to / 1e6 * price[1]
        reader_total += usd
        print(f"| {name} | {reader} | {ti:,} | {to:,} | ${usd:.3f} |")
    print(f"| **reader total** | | | | **${reader_total:.3f}** |")

    print("\n### 6.2 Build cost (2nd-pass extraction, 3 chains)\n")
    build_log = ROOT / "results/b41_build_pass2.log"
    tin = tout = 0
    if build_log.exists():
        for line in build_log.read_text(encoding="utf-8").splitlines():
            m = re.search(r"in=(\d+) out=(\d+)", line)
            if m and "cards" in line:
                tin += int(m.group(1)); tout += int(m.group(2))
    build_usd = tin / 1e6 * 2.00 + tout / 1e6 * 10.00
    print(f"3 chains, claude-sonnet-5: in={tin:,} out={tout:,} "
          f"${build_usd:.3f}")

    print(f"\n**本批总花费(建店 + 联集(离线,$0) + 读者,判官另计)= "
          f"${reader_total + build_usd:.3f}**")

    print("\nSee results/b41_provenance.txt for store directory sha256, "
          "reader-arm runtime windows and log-based cost cross-check.")


if __name__ == "__main__":
    main()
