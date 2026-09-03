# -*- coding: utf-8 -*-
"""批 38 记分器:写入侧抽取器换 claude-sonnet-5(店 v47s)vs haiku 建的 v45。

口径与 scripts/b33A_score.py / b36b_score.py 完全一致:
- 去重:同一 question_id 保留**首次**出现(b33A_score.load);
- 配对 McNemar = 精确二项符号检验(b33A_score.sign_p),报双向翻转数;
- 全部比较限制到 results/b35_questions_sample36.jsonl 的同 140 题;
- plainctx 的"截断校正 mt4000"沿用批 36-B 的合并口径(mt800 全量 +
  被截断题的 mt4000 重跑覆盖)。

用法: PYTHONUTF8=1 python scripts/b38_score.py > results/b38_score_out.txt
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import acc, load, sign_p  # noqa: E402

QREF = "results/b35_questions_sample36.jsonl"
CORPUS = "data/wikistate_full_ALL_v24.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
S5 = (2.00, 10.00)     # claude-sonnet-5 $/M in, out
H45 = (1.00, 5.00)     # claude-haiku-4-5 $/M in, out(与批 36/36-B 同表)

ARMS = [
    ("smoc_v47s@haiku   (sonnet-5-built ledger)",
     ["results/b38_smoc_v47s_haiku-4-5.jsonl"], H45, "haiku-4-5", "本批"),
    ("smoc_v47s@sonnet5 (sonnet-5-built ledger)",
     ["results/b38_smoc_v47s_sonnet-5.jsonl"], S5, "sonnet-5", "本批"),
    ("smoc_v45@haiku    (haiku-built ledger)",
     ["results/b33A_smoc_v45.jsonl"], H45, "haiku-4-5", "批 33-A"),
    ("smoc_v45@sonnet5  (haiku-built ledger)",
     ["results/b36b_smoc_sonnet5.jsonl"], S5, "sonnet-5", "批 36-B"),
    ("plainctx@sonnet5  (full text, mt800)",
     ["results/b36_plainctx_sonnet-5.jsonl"], S5, "sonnet-5", "批 36"),
    ("plainctx@sonnet5  (trunc-corrected mt4000)",
     ["results/b36_plainctx_sonnet-5.jsonl",
      "results/b36_plainctx_sonnet-5_mt4000.jsonl"], S5, "sonnet-5", "批 36"),
    ("plainctx@haiku    (full text, mt800)",
     ["results/b36_plainctx_haiku-4-5.jsonl"], H45, "haiku-4-5", "批 36"),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def load_many(paths, keys):
    m = {}
    for p in paths:
        m.update(restrict(load(p), keys))
    return m


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def stats(rows, pi, po):
    mi = st.mean([r.get("usage_input_tokens") or 0 for r in rows])
    mo = st.mean([r.get("usage_output_tokens") or 0 for r in rows])
    lat = st.median([r.get("latency_s") or 0 for r in rows])
    return mi, mo, lat, mi / 1e6 * pi + mo / 1e6 * po


def cmp2(name_a, a, name_b, b):
    keys = sorted(set(a) & set(b))
    if not keys:
        print("  %s vs %s : no overlap" % (name_a, name_b))
        return
    aw = sum(1 for q in keys if a[q]["judge_correct"] and not b[q]["judge_correct"])
    bw = sum(1 for q in keys if b[q]["judge_correct"] and not a[q]["judge_correct"])
    pa = sum(bool(a[q]["judge_correct"]) for q in keys) / len(keys) * 100
    pb = sum(bool(b[q]["judge_correct"]) for q in keys) / len(keys) * 100
    print("  n=%3d | A=%-42s %5.1f%%  B=%-42s %5.1f%% | delta(A-B) %+6.2fpp | "
          "A-only-right=%2d B-only-right=%2d | McNemar exact p=%.4g"
          % (len(keys), name_a, pa, name_b, pb, pa - pb, aw, bw, sign_p(aw, bw)))


# ── 写入侧诊断:编译账目(槽位的带日期取值序列)vs 金标链 ──────────────
_ART = re.compile(r"^(the|a|an|le|la|les|l')\s+", re.I)
_PUNCT = re.compile(r"[^\w\s]", re.U)


def nv(s):
    """值归一:去重音、小写、去标点、去冠词、压空白。"""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PUNCT.sub(" ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    s = _ART.sub("", s).strip()
    return s


def yr(d):
    m = re.match(r"(\d{4})", str(d or ""))
    return m.group(1) if m else ""


def val_match(gold_v, card_v):
    """金标值 vs 卡片值:归一后相等,或一方是另一方的整词子串。

    宽松方向是刻意的 —— sonnet-5 会把 employer/job_title 合成
    'faculty member at Tsinghua University',若按严格相等判会把它记成
    '缺行',那是记分口径的伪影而不是抽取失败。
    """
    g, c = nv(gold_v), nv(card_v)
    if not g or not c:
        return False
    if g == c:
        return True
    if len(g) >= 4 and re.search(r"\b" + re.escape(g) + r"\b", c):
        return True
    if len(c) >= 4 and re.search(r"\b" + re.escape(c) + r"\b", g):
        return True
    return False


def ledger_rows(uid, entry, cards_dir):
    """与 repro_batch3.render_card_ledger 同口径地取(日期, 记录)。"""
    from complex_query_arm import _mem_dates
    p = Path(ROOT) / cards_dir / f"{uid}.json"
    recs = json.loads(p.read_text(encoding="utf-8")).get("records", [])
    md = _mem_dates(entry)
    out = []
    for r in recs:
        d = r.get("stated_date") or md.get(r.get("source_memory_id", ""), "")
        out.append((d or "", r))
    out.sort(key=lambda x: x[0] or "9999")
    return out


def diag_uid(uid, entry, cards_dir):
    """返回 (exact, date_off, missing, extra, lane_slots, n_lane)。

    exact    金标行被某条账目行以「值匹配 + 年份相同」命中
    date_off 值命中但年份不同
    missing  值完全没命中
    extra    落在同一槽位车道、却不对应任何金标行的账目行
    车道定义:命中金标的那些卡片 slot 名 ∪ 名字里含金标 slot 词根的 slot 名。
    """
    gold = entry.get("chain") or []
    gslot = (entry.get("slot") or "").lower()
    rows = ledger_rows(uid, entry, cards_dir)
    used = set()
    exact = date_off = missing = 0
    lane = set()
    for g in gold:
        best = None
        for i, (d, r) in enumerate(rows):
            if i in used or not val_match(g.get("value"), r.get("value")):
                continue
            same_yr = yr(d) == yr(g.get("date"))
            if best is None or (same_yr and not best[1]):
                best = (i, same_yr)
            if same_yr:
                break
        if best is None:
            missing += 1
            continue
        used.add(best[0])
        lane.add((rows[best[0]][1].get("slot") or "?"))
        if best[1]:
            exact += 1
        else:
            date_off += 1
    for _d, r in rows:
        s = (r.get("slot") or "").lower()
        if gslot and (gslot in s or s in gslot):
            lane.add(r.get("slot") or "?")
    n_lane = sum(1 for _d, r in rows if (r.get("slot") or "?") in lane)
    extra = n_lane - (exact + date_off)
    return exact, date_off, missing, max(0, extra), sorted(lane), len(rows)


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})
    qtype = {q["qid"]: q["qtype"] for q in qref}
    quid = {q["qid"]: q["uid"] for q in qref}

    print("# Batch 38 — WRITE-side extractor swap: does a stronger card builder "
          "raise the QVF ledger ceiling?\n")
    print("Hypothesis under test (from batch 36b): the ledger arm is "
          "reader-insensitive (smoc 91.4%@haiku vs 90.7%@sonnet-5) while plain "
          "full-context reading with sonnet-5 reaches 97.1%, so the ledger's "
          "ceiling is set by WRITE-side card extraction, not by the reader. "
          "Batch 38 rebuilds the store with extractor = claude-sonnet-5 "
          "(store results/wt_cards_v47s, 36 chains) and reruns the ledger arm "
          "with both readers on the same 140 questions.\n")
    print(f"Questions: {QREF} ({len(qids)} qids / {len(uids)} chains); "
          f"corpus {CORPUS} (v2.4).")
    print("Runner: scripts/lb_reader_arm_b36b.py (unchanged from batch 36b).")
    print("Builder: scripts/wt_qvf_prototype_b38.py — see "
          "results/b38_provenance.txt for the exact diff vs the frozen "
          "scripts/wt_qvf_prototype.py.\n")

    print("## 1. Accuracy / cost table (all restricted to the same 140 qids)\n")
    hdr = ("| arm | reader | n | acc | " + " | ".join(TYPES) +
           " | in tok | out tok | median lat s | $/q |")
    print(hdr)
    print("|" + "---|" * (10 + len(TYPES)))
    data = {}
    for name, paths, price, reader, note in ARMS:
        d = load_many(paths, qids)
        if not d:
            print(f"| {name} | {reader} | 0 | (missing: {paths}) |")
            continue
        data[name] = d
        mi, mo, lat, cpq = stats(list(d.values()), *price)
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| %s | %s | %d | **%.1f%%** | %s | %.0f | %.0f | %.2f | $%.5f |"
              % (name, reader, len(d), acc(d), tys, mi, mo, lat, cpq))

    def g(k):
        return data.get(k)

    A = "smoc_v47s@haiku   (sonnet-5-built ledger)"
    B = "smoc_v47s@sonnet5 (sonnet-5-built ledger)"
    C = "smoc_v45@haiku    (haiku-built ledger)"
    D = "smoc_v45@sonnet5  (haiku-built ledger)"
    E = "plainctx@sonnet5  (trunc-corrected mt4000)"
    F = "plainctx@sonnet5  (full text, mt800)"

    print("\n## 2. Paired McNemar (exact binomial sign test) on the 140 ids\n")
    print("Pre-registered comparisons:")
    for a, b in [(A, C), (B, D), (B, E)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))
    print("\nSupporting comparisons:")
    for a, b in [(B, A), (A, E), (B, F), (C, D)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))

    print("\n## 3. Per-chain view: chains where the v45 ledger lost to plainctx "
          "under BOTH readers — did v47s fix them?\n")
    if all(g(x) for x in (A, B, C, D, E)):
        lost = []
        for u in uids:
            qs = [q for q in qids if quid[q] == u]
            def wrong(dd):
                return {q for q in qs if q in dd and not dd[q]["judge_correct"]}
            w45h, w45s = wrong(g(C)), wrong(g(D))
            wpc = wrong(g(E))
            # 「v45 账目在两个读者下都输给 plainctx」= 两读者下都存在
            # plainctx 答对而 v45 答错的题
            both = (w45h - wpc) & (w45s - wpc)
            if both:
                lost.append((u, sorted(both)))
        print(f"Chains meeting the criterion: {len(lost)} / {len(uids)}\n")
        print("| chain | qids v45 lost (both readers) | v47s@haiku fixed | "
              "v47s@sonnet5 fixed | v47s newly broken (any reader) |")
        print("|---|---|---|---|---|")
        tot_q = tot_fh = tot_fs = tot_nb = 0
        for u, qs_lost in lost:
            fh = [q for q in qs_lost if g(A).get(q, {}).get("judge_correct")]
            fs = [q for q in qs_lost if g(B).get(q, {}).get("judge_correct")]
            allq = [q for q in qids if quid[q] == u]
            nb = [q for q in allq
                  if (g(C).get(q, {}).get("judge_correct")
                      and not g(A).get(q, {}).get("judge_correct"))
                  or (g(D).get(q, {}).get("judge_correct")
                      and not g(B).get(q, {}).get("judge_correct"))]
            tot_q += len(qs_lost); tot_fh += len(fh); tot_fs += len(fs)
            tot_nb += len(nb)
            print("| %s | %d (%s) | %d | %d | %d |"
                  % (u, len(qs_lost),
                     ", ".join(q.rsplit("_", 1)[-1] for q in qs_lost),
                     len(fh), len(fs), len(nb)))
        print("| **total** | **%d** | **%d** | **%d** | **%d** |"
              % (tot_q, tot_fh, tot_fs, tot_nb))
        print("\n(\"newly broken\" counts questions in those same chains that "
              "v45 got right and v47s got wrong, under either reader.)")

    print("\n## 4. Write-side diagnostic: compiled ledger vs gold chain\n")
    print("For each chain, the slot's dated value sequence is read out of the "
          "store exactly as repro_batch3.render_card_ledger builds it "
          "(stated_date, else the source memory's session date), then matched "
          "1-1 against the corpus field chain[*].{value,date}.")
    print("  exact   = gold row matched on normalised value AND same year")
    print("  date-off= value matched but the year differs")
    print("  missing = gold row not present in the ledger at all")
    print("  extra   = ledger rows in the same slot lane that match no gold row\n")
    corpus = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}
    agg = {}
    rowsout = []
    for store, tag in (("results/wt_cards_v45", "v45"),
                       ("results/wt_cards_v47s", "v47s")):
        tot = Counter()
        per = {}
        for u in uids:
            e, d0, m, x, lane, nrec = diag_uid(u, ents[u], store)
            per[u] = (e, d0, m, x, lane, nrec)
            tot["exact"] += e; tot["date_off"] += d0
            tot["missing"] += m; tot["extra"] += x
            tot["gold"] += len(ents[u].get("chain") or [])
            tot["records"] += nrec
        agg[tag] = (tot, per)
    print("| store | extractor | gold rows | exact | date-off | missing | "
          "extra | total cards | perfect chains |")
    print("|---|---|---|---|---|---|---|---|---|")
    for tag, extr in (("v45", "claude-haiku-4-5"), ("v47s", "claude-sonnet-5")):
        tot, per = agg[tag]
        perfect = sum(1 for u in uids
                      if per[u][2] == 0 and per[u][1] == 0
                      and per[u][0] == len(ents[u].get("chain") or []))
        print("| %s | %s | %d | **%d** (%.1f%%) | %d | **%d** | %d | %d | %d/%d |"
              % (tag, extr, tot["gold"], tot["exact"],
                 tot["exact"] / max(1, tot["gold"]) * 100,
                 tot["date_off"], tot["missing"], tot["extra"],
                 tot["records"], perfect, len(uids)))

    print("\n### Per-chain (only chains where the two stores differ)\n")
    print("| chain | gold | v45 exact/date-off/missing/extra | "
          "v47s exact/date-off/missing/extra | v45 lane | v47s lane |")
    print("|---|---|---|---|---|---|")
    ndiff = 0
    for u in uids:
        a = agg["v45"][1][u]; b = agg["v47s"][1][u]
        if a[:4] == b[:4]:
            continue
        ndiff += 1
        ng = len(ents[u].get("chain") or [])
        print("| %s | %d | %d/%d/%d/%d | %d/%d/%d/%d | %s | %s |"
              % (u, ng, a[0], a[1], a[2], a[3], b[0], b[1], b[2], b[3],
                 ",".join(a[4]) or "-", ",".join(b[4]) or "-"))
    print(f"\n({ndiff} of {len(uids)} chains differ; the rest are identical on "
          "all four counts.)")

    print("\n### Slot-name vocabulary (write-side, all 36 chains)\n")
    for tag in ("v45", "v47s"):
        c = Counter()
        for u in uids:
            p = ROOT / f"results/wt_cards_{tag}" / f"{u}.json"
            for r in json.loads(p.read_text(encoding="utf-8"))["records"]:
                c[r.get("slot") or "?"] += 1
        print(f"- **{tag}**: {sum(c.values())} cards, {len(c)} distinct slot "
              f"names; top 12 = " +
              ", ".join(f"{k}({v})" for k, v in c.most_common(12)))

    # ── 5. 槽位碎片化(POST-HOC,非预注册)────────────────────────────
    print("\n## 5. POST-HOC: slot-name fragmentation (NOT pre-registered)\n")
    print("Found while reading the 4 questions both v47s readers still get "
          "wrong. A chain is 'fragmented' in a store when the gold chain's "
          "values land under MORE THAN ONE card `slot` name — e.g. the gold "
          "slot `position` split into `parliament_membership` + "
          "`civic_office`. The ledger renderer prints `slot: value` per row, "
          "so a reader asked 'how many times did my position change' counts "
          "only one of the two lanes.\n")

    def lanes(uid, store):
        e = ents[uid]
        rows = ledger_rows(uid, e, store)
        used, L = set(), []
        for gd in e.get("chain") or []:
            for i, (_d, r) in enumerate(rows):
                if i in used or not val_match(gd.get("value"), r.get("value")):
                    continue
                used.add(i)
                L.append(r.get("slot") or "?")
                break
        return sorted(set(L))

    lane45 = {u: lanes(u, "results/wt_cards_v45") for u in uids}
    lane47 = {u: lanes(u, "results/wt_cards_v47s") for u in uids}
    fr45 = {u: len(lane45[u]) > 1 for u in uids}
    fr47 = {u: len(lane47[u]) > 1 for u in uids}
    print("| chain | gold rows | v45 slot names | v47s slot names |")
    print("|---|---|---|---|")
    for u in uids:
        if not (fr45[u] or fr47[u]):
            continue
        print("| %s | %d | %s | %s |"
              % (u, len(ents[u].get("chain") or []),
                 ", ".join(lane45[u]), ", ".join(lane47[u])))
    print("\nChains whose gold values are split across >1 card slot name: "
          "**v45 %d/36, v47s %d/36** — the stronger extractor uses more "
          "semantically precise slot names and therefore fragments MORE."
          % (sum(fr45.values()), sum(fr47.values())))

    print("\n### Accuracy split by v47s fragmentation (the control matters)\n")
    print("| subset | n | v47s@sonnet5 | v47s@haiku | v45@sonnet5 | "
          "v45@haiku | plainctx@sonnet5 mt4000 |")
    print("|---|---|---|---|---|---|---|")
    for flag, lab in ((True, "v47s-fragmented chains (7)"),
                      (False, "v47s single-slot chains (29)")):
        qs = [q for q in qids if fr47[quid[q]] == flag]

        def a(d):
            return sum(1 for q in qs if d[q]["judge_correct"]) / len(qs) * 100
        print("| %s | %d | **%.1f%%** | %.1f%% | %.1f%% | %.1f%% | %.1f%% |"
              % (lab, len(qs), a(g(B)), a(g(A)), a(g(D)), a(g(C)), a(g(E))))
    for flag, lab in ((False, "single-slot"), (True, "fragmented")):
        qs = [q for q in qids if fr47[quid[q]] == flag]
        aw = sum(1 for q in qs if g(B)[q]["judge_correct"]
                 and not g(E)[q]["judge_correct"])
        bw = sum(1 for q in qs if g(E)[q]["judge_correct"]
                 and not g(B)[q]["judge_correct"])
        print("\n  paired on the %2d %s questions: smoc_v47s@sonnet5 vs "
              "plainctx@sonnet5 — smoc-only-right=%d, plainctx-only-right=%d, "
              "McNemar exact p=%.4g" % (len(qs), lab, aw, bw, sign_p(aw, bw)))
    import statistics as _st
    print("\nConfound check — fragmented chains are longer (mean %.1f gold "
          "rows vs %.1f), BUT plainctx@sonnet5 scores %.1f%% on exactly those "
          "26 questions, and v45@sonnet5 scores %.1f%%. So the subset is not "
          "intrinsically unanswerable; it is specifically hard for the v47s "
          "ledger."
          % (_st.mean([len(ents[u].get("chain") or []) for u in uids if fr47[u]]),
             _st.mean([len(ents[u].get("chain") or []) for u in uids
                       if not fr47[u]]),
             sum(1 for q in qids if fr47[quid[q]] and g(E)[q]["judge_correct"])
             / max(1, sum(1 for q in qids if fr47[quid[q]])) * 100,
             sum(1 for q in qids if fr47[quid[q]] and g(D)[q]["judge_correct"])
             / max(1, sum(1 for q in qids if fr47[quid[q]])) * 100))

    fq = [q for q in qids if fr47[quid[q]]]
    bad = [q for q in fq if not g(B)[q]["judge_correct"]]
    print("\n**Causal evidence, not just correlation:** v47s@sonnet5 fails %d "
          "of the %d fragmented questions. Of those %d failures, **%d were "
          "answered correctly by v45@sonnet5** (same reader, same question, "
          "same corpus — only the store changed) and %d by plainctx@sonnet5. "
          "So these failures are specific to THIS store, not to the questions."
          % (len(bad), len(fq), len(bad),
             sum(1 for q in bad if g(D)[q]["judge_correct"]),
             sum(1 for q in bad if g(E)[q]["judge_correct"])))

    print("\n### The 4 questions BOTH v47s readers still get wrong\n")
    for q in sorted(qids):
        if g(A)[q]["judge_correct"] or g(B)[q]["judge_correct"]:
            continue
        v45ok = ("v45@haiku=%s v45@sonnet5=%s"
                 % ("OK" if g(C)[q]["judge_correct"] else "X",
                    "OK" if g(D)[q]["judge_correct"] else "X"))
        print("- `%s` [%s] gold=%r | v47s@haiku=%r | v47s@sonnet5=%r | %s | "
              "plainctx@sonnet5 %s"
              % (q, qtype[q], g(A)[q]["gold_answer"],
                 str(g(A)[q]["answer"])[:55], str(g(B)[q]["answer"])[:55],
                 v45ok, "RIGHT" if g(E)[q]["judge_correct"] else "also wrong"))
    print("\nNote: `wikiP54020-Q98594955_v2cb` is NOT a v47s regression — "
          "v45@haiku gets it wrong too. Its gold date is `2024-00-00`, "
          "rendered in both ledgers as `2024`, so a reader cannot tell whether "
          "it falls strictly before 2024-06-29 and conservatively drops it. "
          "That is a gold-side date-precision problem shared by both stores.")

    print("\n### Second write-side regression: date granularity\n")
    print("The gold chain carries day-precision dates for some rows "
          "(e.g. `1857-03-01`); the card's `stated_date` may coarsen that to "
          "the year. Counted over the gold rows each store actually matched:\n")
    for tag in ("v45", "v47s"):
        coarse = tot = 0
        for u in uids:
            rows = ledger_rows(u, ents[u], f"results/wt_cards_{tag}")
            used = set()
            for gd in ents[u].get("chain") or []:
                gs = str(gd.get("date") or "")
                gprec = 0 if (gs.endswith("-00-00") or gs.endswith("-00")) else 1
                for i, (d, r) in enumerate(rows):
                    if i in used or not val_match(gd.get("value"),
                                                  r.get("value")):
                        continue
                    used.add(i)
                    tot += 1
                    if gprec and len(re.findall(r"\d+", str(d))) < 3:
                        coarse += 1
                    break
        print("- **%s**: %d / %d matched gold rows lose day precision in the "
              "rendered ledger (%.1f%%)" % (tag, coarse, tot,
                                            coarse / max(1, tot) * 100))
    print("\nThis is what breaks `wikiP551005-Q42324799_v2lt`: v45 kept "
          "`1857-03-01`, v47s wrote `1857`, so Buddenbrookhaus (1835-1846) and "
          "Amsterdam (1846-1857) tie at 11 years and both readers pick the "
          "wrong one. Gold is Amsterdam, which wins only on the month.")

    print("\n## 6. Build cost / provenance\n")
    print("See results/b38_provenance.txt.")


if __name__ == "__main__":
    main()
