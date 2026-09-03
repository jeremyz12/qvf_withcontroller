# -*- coding: utf-8 -*-
"""批 38-B 记分器:写入侧两处规范化(槽位名归一 + 日期粒度细化)是否把碎片化
与日期丢失压掉、并把账目分数抬到与全文直读打平?

口径与 scripts/b38_score.py 逐字相同(去重取首次出现;配对 McNemar = 精确
二项符号检验;全部比较限制到 results/b35_questions_sample36.jsonl 的同 140
题)。本文件在其结构与函数之上做的唯一改动:

- "本批" 臂从 smoc_v47s@{haiku,sonnet5} 换成 smoc_v47sk@{haiku,sonnet5}
  (results/b38b_smoc_v47sk_*.jsonl);v45 / v47s 降级为参照臂,原样保留。
- 店级诊断(账目 vs 金标保真度 / 槽位车道碎片化 / 日期粒度丢失)从两店
  (v45, v47s) 扩成三店(v45, v47s, v47sk)。
- 逐链视图新增:批 38 定义的「26 条碎片化题 / 114 条其余题」子集
  (划分依据 = v47s 店的槽位碎片化,与预注册 §prereg 逐字一致,不随本批
  重新计算)上,v47sk 两个读者的分数与 v47s、plainctx 并排。
- 配对 McNemar 新增预注册的四条:v47sk vs v47s(两个读者各一条)、
  v47sk@sonnet5 vs plainctx mt4000(合并文件口径同 b38_score.py)、
  v47sk@haiku vs v45@haiku。
- 新增:按 stop_reason 统计撞 max_tokens 上限的行数(逐臂,凡该字段存在
  即报)。
- 新增:成本汇总——读者臂 usage token 成本(haiku $1/$5、sonnet-5 $2/$10
  每 M)+ 建卡器成本(若 scratchpad/b38b/build_v47sk_*.log 在场则解析,
  口径与 scripts/b38_provenance.py 的建店成本表相同)。

用法: PYTHONUTF8=1 python scripts/b38b_score.py > results/b38b_score_out.txt
"""
from __future__ import annotations

import glob
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

QREF = "results/b35_questions_sample36.jsonl"
CORPUS = "data/wikistate_full_ALL_v24.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
S5 = (2.00, 10.00)     # claude-sonnet-5 $/M in, out
H45 = (1.00, 5.00)     # claude-haiku-4-5 $/M in, out(与批 36/36-B/38 同表)
# 注:项目自有的 scratchpad/ 目录(仓库内、随批次持久保存的建店日志),
# 不是本次会话的临时 scratchpad —— 建店日志实测落在这里
# (scratchpad/b38b/build_v47sk_*.log),与 scripts/b38_provenance.py 里
# 那个会话专属临时路径不是同一目录,不可复用。
SCRATCH = ROOT / "scratchpad"

ARMS = [
    ("smoc_v47sk@haiku  (canon+date-refine ledger)",
     ["results/b38b_smoc_v47sk_haiku-4-5.jsonl"], H45, "haiku-4-5", "本批"),
    ("smoc_v47sk@sonnet5(canon+date-refine ledger)",
     ["results/b38b_smoc_v47sk_sonnet-5.jsonl"], S5, "sonnet-5", "本批"),
    ("smoc_v47s@haiku   (sonnet-5-built ledger)",
     ["results/b38_smoc_v47s_haiku-4-5.jsonl"], H45, "haiku-4-5", "批 38"),
    ("smoc_v47s@sonnet5 (sonnet-5-built ledger)",
     ["results/b38_smoc_v47s_sonnet-5.jsonl"], S5, "sonnet-5", "批 38"),
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

# 三店:标签 -> (目录, 抽取器)
STORES3 = [
    ("v45", "results/wt_cards_v45", "claude-haiku-4-5"),
    ("v47s", "results/wt_cards_v47s", "claude-sonnet-5"),
    ("v47sk", "results/wt_cards_v47sk", "claude-sonnet-5+canon"),
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
    ti = sum(r.get("usage_input_tokens") or 0 for r in rows)
    to = sum(r.get("usage_output_tokens") or 0 for r in rows)
    return mi, mo, lat, mi / 1e6 * pi + mo / 1e6 * po, ti / 1e6 * pi + to / 1e6 * po


def cap_count(paths, keys):
    """撞 max_tokens 上限的行数 / 有 stop_reason 字段的行数(去重后限于 keys)。"""
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


def lanes(uid, entry, store):
    rows = ledger_rows(uid, entry, store)
    used, L = set(), []
    for gd in entry.get("chain") or []:
        for i, (_d, r) in enumerate(rows):
            if i in used or not val_match(gd.get("value"), r.get("value")):
                continue
            used.add(i)
            L.append(r.get("slot") or "?")
            break
    return sorted(set(L))


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})
    qtype = {q["qid"]: q["qtype"] for q in qref}
    quid = {q["qid"]: q["uid"] for q in qref}

    print("# Batch 38-B — write-side normalisation: contract problem or model "
          "problem?\n")
    print("Hypothesis under test (from batch 38 §九): batch 38 found that "
          "swapping the card-builder extractor haiku->sonnet-5 closed the "
          "missing-row gap (122/133 -> 133/133 vs gold) but end-to-end only "
          "moved 91.4->92.9 (haiku reader) / 90.7->92.1 (sonnet-5 reader), "
          "both n.s., still short of the 97.1% plain full-context ceiling. "
          "Post-hoc diagnosis pinned the gap on two write-side regressions "
          "introduced BY the stronger extractor: slot-name fragmentation "
          "(v45 2/36 chains -> v47s 7/36) and date-precision loss (v47s "
          "24/133 matched gold rows lose day precision, v45 only 2/122). "
          "Batch 38-B tests whether these are CONTRACT problems, fixable by "
          "deterministic post-extraction normalisation on the SAME "
          "extractor/corpus/questions/reader/runner (store "
          "results/wt_cards_v47sk, same 36 chains), rather than MODEL "
          "problems. Four pre-registered hypotheses (results/"
          "opt_batch38b_prereg.md §二): H1 fragmented chains <= 2/36; H2 "
          "batch-38's 26 fragmented-chain questions >= 88% @sonnet5; H3 "
          "overall >= 95% and n.s. vs plainctx mt4000; H4 ledger fidelity "
          "stays 133/133 (missing=0, date_off=0).\n")
    print(f"Questions: {QREF} ({len(qids)} qids / {len(uids)} chains); "
          f"corpus {CORPUS} (v2.4).")
    print("Runner: scripts/lb_reader_arm_b36b.py (unchanged from batch 36-B "
          "/ 38).")
    print("Builder: scripts/wt_qvf_prototype_b38b.py — b38 copy +172 lines "
          "pure-addition, two post-extraction normalisation flags "
          "(QVF_CARD_SLOT_CANON, QVF_CARD_DATE_REFINE); see "
          "results/b38b_provenance.txt for the exact diff.\n")

    print("## 1. Accuracy / cost table (all restricted to the same 140 qids)\n")
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

    Ah = "smoc_v47sk@haiku  (canon+date-refine ledger)"
    As = "smoc_v47sk@sonnet5(canon+date-refine ledger)"
    Sh = "smoc_v47s@haiku   (sonnet-5-built ledger)"
    Ss = "smoc_v47s@sonnet5 (sonnet-5-built ledger)"
    Vh = "smoc_v45@haiku    (haiku-built ledger)"
    Vs = "smoc_v45@sonnet5  (haiku-built ledger)"
    Pm4 = "plainctx@sonnet5  (trunc-corrected mt4000)"
    Pm8 = "plainctx@sonnet5  (full text, mt800)"
    Ph = "plainctx@haiku    (full text, mt800)"

    print("\n## 2. Paired McNemar (exact binomial sign test) on the 140 ids\n")
    print("Pre-registered comparisons (results/opt_batch38b_prereg.md §二):")
    for a, b in [(Ah, Sh), (As, Ss), (As, Pm4), (Ah, Vh)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))
    print("\nSupporting comparisons:")
    for a, b in [(As, Ah), (Ah, Ph), (As, Pm8), (As, Vs), (Sh, Vh), (Ss, Vs)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))

    print("\n## 3. Per-chain view: chains where the v45 ledger lost to plainctx "
          "under BOTH readers — did v47s / v47sk fix them?\n")
    if all(g(x) for x in (Ah, As, Sh, Ss, Vh, Vs, Pm4)):
        lost = []
        for u in uids:
            qs = [q for q in qids if quid[q] == u]

            def wrong(dd):
                return {q for q in qs if q in dd and not dd[q]["judge_correct"]}
            w45h, w45s = wrong(g(Vh)), wrong(g(Vs))
            wpc = wrong(g(Pm4))
            both = (w45h - wpc) & (w45s - wpc)
            if both:
                lost.append((u, sorted(both)))
        print(f"Chains meeting the criterion: {len(lost)} / {len(uids)}\n")
        print("| chain | qids v45 lost (both readers) | v47s@h fixed | "
              "v47s@s5 fixed | v47sk@h fixed | v47sk@s5 fixed | "
              "v47sk newly broken (any reader) |")
        print("|---|---|---|---|---|---|---|")
        tot_q = tot_fsh = tot_fss = tot_fkh = tot_fks = tot_nb = 0
        for u, qs_lost in lost:
            fsh = [q for q in qs_lost if g(Sh).get(q, {}).get("judge_correct")]
            fss = [q for q in qs_lost if g(Ss).get(q, {}).get("judge_correct")]
            fkh = [q for q in qs_lost if g(Ah).get(q, {}).get("judge_correct")]
            fks = [q for q in qs_lost if g(As).get(q, {}).get("judge_correct")]
            allq = [q for q in qids if quid[q] == u]
            nb = [q for q in allq
                  if (g(Vh).get(q, {}).get("judge_correct")
                      and not g(Ah).get(q, {}).get("judge_correct"))
                  or (g(Vs).get(q, {}).get("judge_correct")
                      and not g(As).get(q, {}).get("judge_correct"))]
            tot_q += len(qs_lost); tot_fsh += len(fsh); tot_fss += len(fss)
            tot_fkh += len(fkh); tot_fks += len(fks); tot_nb += len(nb)
            print("| %s | %d (%s) | %d | %d | %d | %d | %d |"
                  % (u, len(qs_lost),
                     ", ".join(q.rsplit("_", 1)[-1] for q in qs_lost),
                     len(fsh), len(fss), len(fkh), len(fks), len(nb)))
        print("| **total** | **%d** | **%d** | **%d** | **%d** | **%d** | "
              "**%d** |"
              % (tot_q, tot_fsh, tot_fss, tot_fkh, tot_fks, tot_nb))
        print("\n(\"newly broken\" counts questions in those same chains that "
              "v45 got right and v47sk got wrong, under either reader.)")

    print("\n## 4. Write-side diagnostic: compiled ledger vs gold chain "
          "(three stores)\n")
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
    for tag, store, _extr in STORES3:
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
    for tag, store, extr in STORES3:
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

    print("\n### Per-chain diff, v47s vs v47sk (did the patch change the "
          "compiled ledger?)\n")
    print("| chain | gold | v47s exact/date-off/missing/extra | "
          "v47sk exact/date-off/missing/extra | v47s lane | v47sk lane |")
    print("|---|---|---|---|---|---|")
    ndiff = 0
    for u in uids:
        a = agg["v47s"][1][u]; b = agg["v47sk"][1][u]
        if a[:4] == b[:4]:
            continue
        ndiff += 1
        ng = len(ents[u].get("chain") or [])
        print("| %s | %d | %d/%d/%d/%d | %d/%d/%d/%d | %s | %s |"
              % (u, ng, a[0], a[1], a[2], a[3], b[0], b[1], b[2], b[3],
                 ",".join(a[4]) or "-", ",".join(b[4]) or "-"))
    print(f"\n({ndiff} of {len(uids)} chains differ between v47s and v47sk on "
          "all four counts; the rest are identical.)")

    print("\n### Per-chain diff, v45 vs v47s (retained from batch 38, "
          "reference only)\n")
    print("| chain | gold | v45 exact/date-off/missing/extra | "
          "v47s exact/date-off/missing/extra | v45 lane | v47s lane |")
    print("|---|---|---|---|---|---|")
    ndiff2 = 0
    for u in uids:
        a = agg["v45"][1][u]; b = agg["v47s"][1][u]
        if a[:4] == b[:4]:
            continue
        ndiff2 += 1
        ng = len(ents[u].get("chain") or [])
        print("| %s | %d | %d/%d/%d/%d | %d/%d/%d/%d | %s | %s |"
              % (u, ng, a[0], a[1], a[2], a[3], b[0], b[1], b[2], b[3],
                 ",".join(a[4]) or "-", ",".join(b[4]) or "-"))
    print(f"\n({ndiff2} of {len(uids)} chains differ; the rest are identical.)")

    print("\n### Slot-name vocabulary (write-side, all 36 chains, three "
          "stores)\n")
    for tag, store, _extr in STORES3:
        c = Counter()
        for u in uids:
            p = ROOT / store / f"{u}.json"
            for r in json.loads(p.read_text(encoding="utf-8"))["records"]:
                c[r.get("slot") or "?"] += 1
        print(f"- **{tag}**: {sum(c.values())} cards, {len(c)} distinct slot "
              f"names; top 12 = " +
              ", ".join(f"{k}({v})" for k, v in c.most_common(12)))

    # ── 5. 槽位碎片化(三店)────────────────────────────────────────
    print("\n## 5. Slot-name fragmentation (three stores)\n")
    print("A chain is 'fragmented' in a store when the gold chain's values "
          "land under MORE THAN ONE card `slot` name. The ledger renderer "
          "prints `slot: value` per row, so a reader asked 'how many times "
          "did my position change' counts only one of the lanes.\n")

    lane_by_store = {tag: {u: lanes(u, ents[u], store) for u in uids}
                      for tag, store, _e in STORES3}
    fr_by_store = {tag: {u: len(lane_by_store[tag][u]) > 1 for u in uids}
                   for tag, _s, _e in STORES3}
    fr45, fr47, fr47sk = fr_by_store["v45"], fr_by_store["v47s"], fr_by_store["v47sk"]

    print("| chain | gold rows | v45 slot names | v47s slot names | "
          "v47sk slot names |")
    print("|---|---|---|---|---|")
    for u in uids:
        if not (fr45[u] or fr47[u] or fr47sk[u]):
            continue
        print("| %s | %d | %s | %s | %s |"
              % (u, len(ents[u].get("chain") or []),
                 ", ".join(lane_by_store["v45"][u]),
                 ", ".join(lane_by_store["v47s"][u]),
                 ", ".join(lane_by_store["v47sk"][u])))
    n45, n47, n47k = sum(fr45.values()), sum(fr47.values()), sum(fr47sk.values())
    print("\nChains whose gold values are split across >1 card slot name: "
          "**v45 %d/36, v47s %d/36, v47sk %d/36**." % (n45, n47, n47k))
    print("\n**H1 判据(results/opt_batch38b_prereg.md §二)**: v47sk 碎片化链数 "
          "<= 2/36 记「证实」;落在 3-6 之间记「部分证实」;仍为 7 记「被否定」。"
          f" 本批实测 v47sk = **{n47k}/36**。")

    print("\n### 3.x Accuracy split by v47s fragmentation (batch-38 partition, "
          "kept fixed) — v47sk vs v47s vs plainctx\n")
    print("Partition is v47s's own fragmentation (frozen from batch 38, NOT "
          "recomputed on v47sk) — this is the 26-question / 114-question "
          "split named in the batch 38-B task.\n")
    print("| subset | n | v47sk@sonnet5 | v47sk@haiku | v47s@sonnet5 | "
          "v47s@haiku | v45@sonnet5 | v45@haiku | plainctx@sonnet5 mt4000 |")
    print("|---|---|---|---|---|---|---|---|---|")
    frag_qs = other_qs = None
    for flag, lab in ((True, "v47s-fragmented chains (26)"),
                      (False, "v47s single-slot chains (114)")):
        qs = [q for q in qids if fr47[quid[q]] == flag]
        if flag:
            frag_qs = qs
        else:
            other_qs = qs

        def a(d):
            present = [q for q in qs if q in d]
            if not present:
                return float("nan")
            return sum(1 for q in present if d[q]["judge_correct"]) / len(present) * 100
        print("| %s | %d | **%.1f%%** | %.1f%% | %.1f%% | %.1f%% | %.1f%% | "
              "%.1f%% | %.1f%% |"
              % (lab, len(qs), a(g(As)), a(g(Ah)), a(g(Ss)), a(g(Sh)),
                 a(g(Vs)), a(g(Vh)), a(g(Pm4))))

    frag_qs_s = [q for q in frag_qs if q in g(As)]
    print("\n**H2 判据**: 批 38 那 26 道碎片化题上 v47sk@sonnet5 >= 88%% 记「证实」;"
          "未过 88%% 但显著高于 v47s@sonnet5 的 69.2%% 记「部分证实」;<= 76.9%% "
          "(即只修好 <=2 题)记「被否定」。 本批实测 v47sk@sonnet5 = "
          "**%.1f%%** (%d/%d)%s。"
          % ((sum(1 for q in frag_qs_s if g(As)[q]["judge_correct"])
              / len(frag_qs_s) * 100) if frag_qs_s else float("nan"),
             sum(1 for q in frag_qs_s if g(As)[q]["judge_correct"]),
             len(frag_qs_s),
             "" if len(frag_qs_s) == len(frag_qs)
             else f" [WARNING: only {len(frag_qs_s)}/{len(frag_qs)} of the "
                  "26 present — data incomplete]"))

    print("\nPaired McNemar on the two subsets:")
    for qs, lab in ((frag_qs, "26 fragmented"), (other_qs, "114 other")):
        for name_a, name_b in ((As, Pm4), (As, Ss), (Ah, Sh)):
            da, db = g(name_a), g(name_b)
            qs_p = [q for q in qs if q in da and q in db]
            aw = sum(1 for q in qs_p if da[q]["judge_correct"]
                     and not db[q]["judge_correct"])
            bw = sum(1 for q in qs_p if db[q]["judge_correct"]
                     and not da[q]["judge_correct"])
            print("  n=%3d | %s | A=%s B=%s | A-only-right=%d B-only-right=%d "
                  "| McNemar exact p=%.4g"
                  % (len(qs_p), lab, name_a.strip(), name_b.strip(), aw, bw,
                     sign_p(aw, bw)))

    fq = frag_qs_s
    bad = [q for q in fq if not g(As)[q]["judge_correct"]]
    print("\n**Residual failures on the 26 fragmented questions "
          "(v47sk@sonnet5):** %d / %d still wrong. Of those, %d were "
          "answered correctly by v47s@sonnet5 (regression fixed elsewhere "
          "would show here as still-broken), %d by v45@sonnet5, %d by "
          "plainctx@sonnet5."
          % (len(bad), len(fq),
             sum(1 for q in bad if q in g(Ss) and g(Ss)[q]["judge_correct"]),
             sum(1 for q in bad if q in g(Vs) and g(Vs)[q]["judge_correct"]),
             sum(1 for q in bad if q in g(Pm4) and g(Pm4)[q]["judge_correct"])))

    print("\n### Questions BOTH v47sk readers still get wrong\n")
    n_both_wrong = 0
    for q in sorted(qids):
        if q not in g(Ah) or q not in g(As):
            continue
        if g(Ah)[q]["judge_correct"] or g(As)[q]["judge_correct"]:
            continue
        n_both_wrong += 1
        v45ok = ("v45@haiku=%s v45@sonnet5=%s"
                 % ("OK" if q in g(Vh) and g(Vh)[q]["judge_correct"] else "X",
                    "OK" if q in g(Vs) and g(Vs)[q]["judge_correct"] else "X"))
        v47sok = ("v47s@haiku=%s v47s@sonnet5=%s"
                  % ("OK" if q in g(Sh) and g(Sh)[q]["judge_correct"] else "X",
                     "OK" if q in g(Ss) and g(Ss)[q]["judge_correct"] else "X"))
        print("- `%s` [%s] gold=%r | v47sk@haiku=%r | v47sk@sonnet5=%r | %s | "
              "%s | plainctx@sonnet5 %s"
              % (q, qtype[q], g(Ah)[q]["gold_answer"],
                 str(g(Ah)[q]["answer"])[:55], str(g(As)[q]["answer"])[:55],
                 v45ok, v47sok,
                 "RIGHT" if (q in g(Pm4) and g(Pm4)[q]["judge_correct"])
                 else "also wrong"))
    print(f"\n{n_both_wrong} question(s) both v47sk readers get wrong.")

    print("\n### Date granularity loss (three stores)\n")
    print("The gold chain carries day-precision dates for some rows "
          "(e.g. `1857-03-01`); the card's `stated_date` may coarsen that to "
          "the year. Counted over the gold rows each store actually matched:\n")
    date_agg = {}
    for tag, store, _extr in STORES3:
        coarse = tot = 0
        for u in uids:
            rows = ledger_rows(u, ents[u], store)
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
        date_agg[tag] = (coarse, tot)
        print("- **%s**: %d / %d matched gold rows lose day precision in the "
              "rendered ledger (%.1f%%)" % (tag, coarse, tot,
                                            coarse / max(1, tot) * 100))
    print("\n**H4 判据**: 编译账目 vs 金标仍 133/133(missing=0、date_off=0)记"
          "「证实」;出现 missing>0 或 date_off>0 记「规范化引入了新的保真度"
          "代价」。 本批实测 v47sk: missing=%d, date_off=%d, exact=%d/%d "
          "(gold=%d)。"
          % (agg["v47sk"][0]["missing"], agg["v47sk"][0]["date_off"],
             agg["v47sk"][0]["exact"], agg["v47sk"][0]["gold"],
             agg["v47sk"][0]["gold"]))

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

    print("\n### 6.2 Builder cost (scratchpad/b38b/build_v47sk_*.log, if "
          "present)\n")
    B_IN, B_OUT = 2.00, 10.00  # claude-sonnet-5, same as builder model
    logs = sorted(glob.glob(str(SCRATCH / "b38b" / "build_v47sk_*.log")))
    build_cost = 0.0
    if not logs:
        print("(no build logs found under "
              f"{SCRATCH / 'b38b'} — builder cost unavailable, see "
              "results/b38b_provenance.txt for whatever else is recorded.)")
    else:
        print("| log | chains | in tok | out tok | $ |")
        print("|---|---|---|---|---|")
        g_in = g_out = g_n = 0
        for lg in logs:
            txt = Path(lg).read_text(encoding="utf-8", errors="replace")
            items = re.findall(
                r"^\[(.*?)\] (\d+) cards \((\d+) batch\), "
                r"in=(\d+) out=(\d+) \((\d+)s\)", txt, re.M)
            ti = sum(int(x[3]) for x in items)
            to = sum(int(x[4]) for x in items)
            g_in += ti; g_out += to; g_n += len(items)
            print(f"| `{Path(lg).name}` | {len(items)} | {ti:,} | {to:,} | "
                  f"${ti / 1e6 * B_IN + to / 1e6 * B_OUT:.3f} |")
        build_cost = g_in / 1e6 * B_IN + g_out / 1e6 * B_OUT
        print(f"| **合计** | **{g_n}** | **{g_in:,}** | **{g_out:,}** | "
              f"**${build_cost:.3f}** |")
        if g_n:
            print(f"\n逐链均值:in {g_in / g_n:,.0f} / out {g_out / g_n:,.0f} "
                  f"tok = ${build_cost / g_n:.4f}/链 (cf. 批 38 smoke "
                  "$0.139/链、批 38 全店 ~ 同量级)。")

    print(f"\n**本批总花费(建店 + 读者,判官另计)= ${build_cost + reader_total:.2f}"
          f"** (建店 ${build_cost:.2f} + 读者 ${reader_total:.2f})。")

    print("\nSee results/b38b_provenance.txt for directory sha256, build "
          "window, and full reader-arm provenance.")


if __name__ == "__main__":
    main()
