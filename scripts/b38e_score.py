# -*- coding: utf-8 -*-
"""批 38-E 记分器:断言类型过滤后的 derived 店 results/wt_cards_v47skf 在真实
读者上的表现,对照批 38-D 的离线预测(92.9% haiku / 95.7% sonnet-5)。

口径与 scripts/b38b_score.py 逐字相同(去重取首次出现;配对 McNemar = 精确
二项符号检验;全部比较限制到 results/b35_questions_sample36.jsonl 的同 140
题)。本文件在其结构与函数之上做的改动:

- 新增本批两条主臂:smoc_v47skf@haiku(mt800,capped 行用同名 _mt4000.jsonl
  校正合并,口径与 plainctx@sonnet5 的 mt800→mt4000 校正逐字相同)、
  smoc_v47skf@sonnet5(mt4000,单次)。
- 店级诊断(账目 vs 金标保真度 / 槽位车道 / 记录数)从三店(v45, v47s,
  v47sk)扩成四店,新增 v47skf。
- 配对 McNemar 新增任务书点名的四条:v47skf vs v47sk(两读者各一条)、
  v47skf vs v47s(两读者各一条)、v47skf@sonnet5 vs plainctx mt4000、
  v47skf@haiku vs v45@haiku。
- 新增:批 38-B 那"两个 v47sk 读者都还错"的 10 题,在 v47skf 下逐题现状。
- 新增:成本汇总(读者臂 usage token 成本,haiku $1/$5、sonnet-5 $2/$10
  每 M)。

用法: PYTHONUTF8=1 python scripts/b38e_score.py > results/b38e_score_out.txt
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

QREF = "results/b35_questions_sample36.jsonl"
CORPUS = "data/wikistate_full_ALL_v24.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
S5 = (2.00, 10.00)     # claude-sonnet-5 $/M in, out
H45 = (1.00, 5.00)     # claude-haiku-4-5 $/M in, out

ARMS = [
    ("smoc_v47skf@haiku (assertion-type filtered ledger, mt800, 0 capped)",
     ["results/b38e_smoc_v47skf_haiku-4-5.jsonl",
      "results/b38e_smoc_v47skf_haiku-4-5_mt4000.jsonl"], H45, "haiku-4-5",
     "本批"),
    ("smoc_v47skf@sonnet5(assertion-type filtered ledger, mt4000)",
     ["results/b38e_smoc_v47skf_sonnet-5.jsonl"], S5, "sonnet-5", "本批"),
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
    ("plainctx@sonnet5  (full text, mt800, 批36)",
     ["results/b36_plainctx_sonnet-5.jsonl"], S5, "sonnet-5", "批36"),
    ("plainctx@sonnet5  (trunc-corrected mt4000, 批36)",
     ["results/b36_plainctx_sonnet-5.jsonl",
      "results/b36_plainctx_sonnet-5_mt4000.jsonl"], S5, "sonnet-5", "批36"),
    ("plainctx@haiku    (full text, mt800, 批36)",
     ["results/b36_plainctx_haiku-4-5.jsonl"], H45, "haiku-4-5", "批36"),
]

STORES4 = [
    ("v45", "results/wt_cards_v45", "claude-haiku-4-5"),
    ("v47s", "results/wt_cards_v47s", "claude-sonnet-5"),
    ("v47sk", "results/wt_cards_v47sk", "claude-sonnet-5+canon"),
    ("v47skf", "results/wt_cards_v47skf", "claude-sonnet-5+canon+assertion-filter"),
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


# ── 写入侧诊断:编译账目 vs 金标链(四店同口径,逐字复用 scripts/b38b_score.py)
_ART = re.compile(r"^(the|a|an|le|la|les|l')\s+", re.I)
_PUNCT = re.compile(r"[^\w\s]", re.U)


def nv(s):
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
    return exact, date_off, missing, max(0, extra), sorted(lane), len(rows), rows


# ── 编译账目答案(与 scripts/b38d_compile.py 逐字相同的口径,内联复制以脱离
# 会话专属 scratchpad 依赖)——用于核对"账目上限"137/140 是否在 v47skf 上
# 复现,不是读者真实作答。
import collections as _collections
from datetime import date as _date

TODAY_RE = re.compile(r"Today is (\d{4}-\d{2}-\d{2})")
BEFORE_RE = re.compile(r"before (\d{4}-\d{2}-\d{2})")


def parse_today(qtype, question):
    if qtype == "count_before":
        m = BEFORE_RE.search(question)
        return m.group(1) if m else None, True
    m = TODAY_RE.search(question)
    return (m.group(1) if m else None), False


def parse_ledger_date(s):
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", s)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) and m.group(2) != "00" else 1
    da = int(m.group(3)) if m.group(3) and m.group(3) != "00" else 1
    try:
        return _date(y, mo, da)
    except ValueError:
        return None


def dated_rows(rows):
    out = []
    for d_str, r in rows:
        do = parse_ledger_date(d_str)
        if do is None:
            continue
        out.append((do, r.get("value"), r))
    out.sort(key=lambda t: t[0])
    return out


def compiled_change_count(rows, today_s):
    today = parse_ledger_date(today_s)
    if today is None:
        return None
    seq = [v for do, v, _r in dated_rows(rows) if do <= today]
    if not seq:
        return None
    n = 0
    for i in range(1, len(seq)):
        if not val_match(seq[i - 1], seq[i]):
            n += 1
    return n


def compiled_count_before(rows, today_s):
    today = parse_ledger_date(today_s)
    if today is None:
        return None
    seq = [v for do, v, _r in dated_rows(rows) if do < today]
    if not seq:
        return None
    uniq = []
    for v in seq:
        if not any(val_match(v, u) or val_match(u, v) for u in uniq):
            uniq.append(v)
    return len(uniq)


def compiled_longest_tenure(rows, today_s):
    today = parse_ledger_date(today_s)
    if today is None:
        return None, False
    dr = [(do, v) for do, v, _r in dated_rows(rows) if do <= today]
    if not dr:
        return None, False
    per = _collections.Counter()
    for i, (start, v) in enumerate(dr):
        end = dr[i + 1][0] if i + 1 < len(dr) else today
        end = min(end, today)
        if end > start:
            per[v] += (end - start).days
    if not per:
        return None, False
    top = per.most_common(2)
    uniq = len(top) == 1 or top[0][1] > top[1][1]
    return top[0][0], uniq


def compiled_first_vs_last(rows, today_s):
    today = parse_ledger_date(today_s)
    if today is None:
        return None, None
    dr = [(do, v) for do, v, _r in dated_rows(rows) if do <= today]
    if not dr:
        return None, None
    return dr[0][1], dr[-1][1]


def compiled_answer(qtype, question, rows):
    today_s, strict = parse_today(qtype, question)
    if today_s is None:
        return None
    if qtype == "change_count":
        return compiled_change_count(rows, today_s)
    if qtype == "count_before":
        return compiled_count_before(rows, today_s)
    if qtype == "longest_tenure":
        v, uniq = compiled_longest_tenure(rows, today_s)
        return v if uniq else (f"AMBIGUOUS:{v}" if v else None)
    if qtype == "first_vs_last":
        f, l = compiled_first_vs_last(rows, today_s)
        if f is None:
            return None
        return f"first: {f}; most recent: {l}"
    return None


def gold_equal(qtype, gold, compiled):
    if compiled is None:
        return False
    if qtype in ("change_count", "count_before"):
        try:
            return int(gold) == int(compiled)
        except (TypeError, ValueError):
            return False
    if qtype == "longest_tenure":
        if isinstance(compiled, str) and compiled.startswith("AMBIGUOUS:"):
            return False
        return val_match(gold, compiled)
    if qtype == "first_vs_last":
        gm = re.match(r"first: (.*); most recent: (.*)", str(gold))
        cm = re.match(r"first: (.*); most recent: (.*)", str(compiled))
        if not gm or not cm:
            return False
        return val_match(gm.group(1), cm.group(1)) and val_match(gm.group(2), cm.group(2))
    return False


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})
    qtype = {q["qid"]: q["qtype"] for q in qref}
    quid = {q["qid"]: q["uid"] for q in qref}
    qs_by_uid = {}
    for q in qref:
        qs_by_uid.setdefault(q["uid"], []).append(q)

    print("# Batch 38-E — assertion-type filter on wt_cards_v47sk, real "
          "readers\n")
    print("Hypothesis under test (results/opt_batch38d_verdict.md, offline "
          "replay, zero API calls): a deterministic assertion-type filter "
          "(drop plan/task/other_person/restate cards, keep start+unknown) "
          "applied to results/wt_cards_v47sk raises the compiled-ledger-vs-"
          "gold match from 131/140 to 137/140 with zero gold rows lost. "
          "Extrapolating from each reader's historical (ledger-ceiling vs "
          "real accuracy) gap, batch 38-D predicted ~92.9% for haiku-4.5 "
          "and ~95.7% for sonnet-5 on the real reader arm. Batch 38-E runs "
          "both readers for real on the derived store results/"
          "wt_cards_v47skf to test that prediction.\n")
    print(f"Questions: {QREF} ({len(qids)} qids / {len(uids)} chains); "
          f"corpus {CORPUS} (v2.4).")
    print("Runner: scripts/lb_reader_arm_b36b.py --arm smoc --cards-dir "
          "results/wt_cards_v47skf --workers 4 (unchanged from batch "
          "36-B/38/38-B).")
    print("Store: results/wt_cards_v47skf — built by scripts/"
          "b38e_build_v47skf.py from results/wt_cards_v47sk (36 chains), "
          "dropping cards whose assertion_type in "
          "{plan,task,other_person,restate}; see results/"
          "b38e_filter_log.json for the full drop list and hard-constraint "
          "check.\n")

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

    Fh = "smoc_v47skf@haiku (assertion-type filtered ledger, mt800, 0 capped)"
    Fs = "smoc_v47skf@sonnet5(assertion-type filtered ledger, mt4000)"
    Kh = "smoc_v47sk@haiku  (canon+date-refine, 批38-B)"
    Ks = "smoc_v47sk@sonnet5(canon+date-refine, 批38-B)"
    Sh = "smoc_v47s@haiku   (sonnet-5-built ledger, 批38)"
    Ss = "smoc_v47s@sonnet5 (sonnet-5-built ledger, 批38)"
    Vh = "smoc_v45@haiku    (haiku-built ledger, 批33-A)"
    Vs = "smoc_v45@sonnet5  (haiku-built ledger, 批36-B)"
    Pm4 = "plainctx@sonnet5  (trunc-corrected mt4000, 批36)"
    Pm8 = "plainctx@sonnet5  (full text, mt800, 批36)"
    Ph = "plainctx@haiku    (full text, mt800, 批36)"

    print("\n## 2. Paired McNemar (exact binomial sign test) on the 140 "
          "ids\n")
    print("Task-specified comparisons:")
    for a, b in [(Fh, Kh), (Fs, Ks), (Fh, Sh), (Fs, Ss), (Fs, Pm4), (Fh, Vh)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))
    print("\nSupporting comparisons:")
    for a, b in [(Fs, Fh), (Fh, Ph), (Fs, Pm8), (Fs, Vs)]:
        if g(a) and g(b):
            cmp2(a, g(a), b, g(b))

    print("\n## 3. The ten 'both v47sk readers wrong' questions of batch "
          "38-B — status under v47skf\n")
    if g(Kh) and g(Ks):
        both_wrong = [q for q in sorted(qids)
                      if q in g(Kh) and q in g(Ks)
                      and not g(Kh)[q]["judge_correct"]
                      and not g(Ks)[q]["judge_correct"]]
        print(f"n = {len(both_wrong)} (recomputed directly from this "
              "script's own v47sk@haiku / v47sk@sonnet5 loads, should equal "
              "batch 38-B's 10).\n")
        print("| qid | type | gold | v47sk@h | v47sk@s5 | v47skf@h | "
              "v47skf@s5 | now right? |")
        print("|---|---|---|---|---|---|---|---|")
        n_fixed_either = n_fixed_both = 0
        for q in both_wrong:
            fh_ok = q in g(Fh) and g(Fh)[q]["judge_correct"]
            fs_ok = q in g(Fs) and g(Fs)[q]["judge_correct"]
            if fh_ok or fs_ok:
                n_fixed_either += 1
            if fh_ok and fs_ok:
                n_fixed_both += 1
            tag = ("BOTH right" if fh_ok and fs_ok else
                   "haiku right" if fh_ok else
                   "sonnet5 right" if fs_ok else "still both wrong")
            print("| `%s` | %s | %r | %s | %s | %s | %s | %s |"
                  % (q, qtype[q], g(Kh)[q]["gold_answer"],
                     "X", "X",
                     "OK" if fh_ok else "X", "OK" if fs_ok else "X", tag))
        print(f"\n{n_fixed_either}/{len(both_wrong)} fixed by at least one "
              f"v47skf reader; {n_fixed_both}/{len(both_wrong)} fixed by "
              "both.")

    print("\n## 4. Write-side diagnostic: compiled ledger vs gold chain "
          "(four stores)\n")
    corpus = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}
    agg = {}
    diag_full = {}  # (tag, uid) -> full diag_uid() tuple, incl. rows (for §4b)
    for tag, store, _extr in STORES4:
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
    for tag, store, extr in STORES4:
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

    print("\n### 4b. Compiled-answer ceiling (offline, zero API — a "
          "reader that never makes a reasoning error, reading only this "
          "ledger) — v47sk vs v47skf, cf. results/opt_batch38d_verdict.md "
          "§4\n")
    print("Reproduces batch 38-D's methodology exactly (same "
          "compiled_answer()/gold_equal() as scripts/b38d_compile.py, "
          "inlined above) to confirm the store this batch actually built "
          "reproduces the 131/140 -> 137/140 uplift batch 38-D predicted "
          "offline.\n")
    print("| store | gold-equal | change_count | count_before | "
          "first_vs_last | longest_tenure |")
    print("|---|---|---|---|---|---|")
    for tag in ("v47sk", "v47skf"):
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

    print("\n## 5. Cost summary\n")
    print("### 5.1 Reader-arm cost (usage tokens, this batch's two arms)\n")
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
    print(f"\n**本批读者花费(判官另计)= ${reader_total:.3f}**（对照批 38-B "
          "两读者合计 $2.575，同一 36 链 / 140 题 / 两读者配置)。")

    print("\nSee results/b38e_provenance.txt for store directory sha256, "
          "reader-arm runtime windows and log-based cost cross-check.")


if __name__ == "__main__":
    main()
