# -*- coding: utf-8 -*-
"""批 36-B 记分器:同读者(claude-sonnet-5)三臂 vs 批 36 现实直读 / 33-A 同臂。

口径与 scripts/b33A_score.py / b36_score.py 相同:
- 去重:同一 question_id 保留**首次**出现(b33A_score.load);
- 配对 McNemar = 精确二项符号检验(b33A_score.sign_p),报双向翻转数;
- 全部比较限制到 results/b35_questions_sample36.jsonl 的同 140 题。

用法: PYTHONUTF8=1 python scripts/b36b_score.py > results/b36b_score_out.txt
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p  # noqa: E402

QREF = "results/b35_questions_sample36.jsonl"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
S5 = (2.00, 10.00)     # claude-sonnet-5 $/M in, out
H45 = (1.00, 5.00)     # claude-haiku-4-5 $/M in, out (批 36 主表同价)

# name -> (files, prices, reader, note)  多文件时后者覆盖前者(截断校正合并)
ARMS = [
    ("smoc@sonnet5      (QVF ledger v45 + F.1)",
     ["results/b36b_smoc_sonnet5.jsonl"], S5, "sonnet-5", "本批"),
    ("direct@sonnet5    (dense top-10 + excerpts)",
     ["results/b36b_direct_sonnet5.jsonl"], S5, "sonnet-5", "本批"),
    ("fullplain@sonnet5 (full text + plain QA)",
     ["results/b36b_fullplain_sonnet5.jsonl"], S5, "sonnet-5", "本批"),
    ("plainctx@sonnet5  (full text + realistic prompt, mt800)",
     ["results/b36_plainctx_sonnet-5.jsonl"], S5, "sonnet-5", "批 36"),
    ("plainctx@sonnet5  (same, truncation-corrected mt4000)",
     ["results/b36_plainctx_sonnet-5.jsonl",
      "results/b36_plainctx_sonnet-5_mt4000.jsonl"], S5, "sonnet-5", "批 36"),
    ("smoc@haiku        (QVF ledger v45 + F.1)",
     ["results/b33A_smoc_v45.jsonl"], H45, "haiku-4-5", "批 33-A"),
    ("direct@haiku      (dense top-10 + excerpts)",
     ["results/b33A_direct.jsonl"], H45, "haiku-4-5", "批 33-A"),
    ("smwplain@haiku    (= fullplain, full text + plain QA)",
     ["results/b33A_smwplain.jsonl"], H45, "haiku-4-5", "批 33-A"),
    ("smw@haiku         (full text + F.1)",
     ["results/b33A_smw.jsonl"], H45, "haiku-4-5", "批 33-A"),
    ("plainctx@haiku    (full text + realistic prompt, mt800)",
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
    """delta / 翻转均以 A 为主语(A - B)。"""
    keys = sorted(set(a) & set(b))
    if not keys:
        print("  %s vs %s : no overlap" % (name_a, name_b))
        return
    aw = sum(1 for q in keys if a[q]["judge_correct"] and not b[q]["judge_correct"])
    bw = sum(1 for q in keys if b[q]["judge_correct"] and not a[q]["judge_correct"])
    pa = sum(bool(a[q]["judge_correct"]) for q in keys) / len(keys) * 100
    pb = sum(bool(b[q]["judge_correct"]) for q in keys) / len(keys) * 100
    print("  n=%3d | %-34s %5.1f%%  vs  %-34s %5.1f%% | delta(A-B) %+6.2fpp | "
          "flips A-only-right=%2d, B-only-right=%2d | McNemar exact p=%.4g"
          % (len(keys), name_a, pa, name_b, pb, pa - pb, aw, bw, sign_p(aw, bw)))


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})

    print("# Batch 36b — SAME-READER (claude-sonnet-5) rerun of the QVF ledger arm "
          "and two reference arms\n")
    print("Why: batch 36 compared plainctx@sonnet-5 against smoc@haiku-4-5 — a "
          "CROSS-READER contrast. This batch reruns smoc / direct / fullplain with "
          "reader claude-sonnet-5 on exactly the same 140 questions so the "
          "comparison is within-reader.\n")
    print("Runner: scripts/lb_reader_arm_b36b.py (copy of the frozen "
          "scripts/lb_reader_arm.py; the ONLY differences are --max-tokens "
          "(default still 800), --workers (default still 1), --budget, and extra "
          "logged fields. Prompt construction for smoc / direct / fullplain is "
          "copied verbatim from the original main()).")
    print("Sampling params: the ORIGINAL lb_reader_arm.py already sends "
          "temperature=0 only when model.startswith('claude-haiku'), so "
          "claude-sonnet-5 was never sent temperature — no guard had to be added; "
          "the copy just makes that explicit (_wants_temperature). Verified "
          "empirically: claude-sonnet-5 returns 400 "
          "'`temperature` is deprecated for this model.' (and the same for "
          "`top_p`), and succeeds with neither parameter.")
    print("max_tokens = 4000 for every sonnet-5 run in this batch (recorded per "
          "row as reader_max_tokens). Reason: sonnet-5 has extended thinking on "
          "by default and max_tokens caps thinking + visible text together; batch "
          "36 lost 20/140 questions to the 800 cap.")
    print("Corpus data/wikistate_full_ALL_v24.json (v2.4); store "
          "results/wt_cards_v45 (READ-ONLY, not rebuilt); questions %s "
          "(%d q / %d chains); judge qvf.judge.ClaudeJudge() = claude-opus-5.\n"
          % (QREF, len(qids), len(uids)))

    # ── 提示词同一性核验 ────────────────────────────────────────
    from repro_batch3 import PLAIN_PROMPT as P3, render_transcript as R3
    import repro_batch3_b33 as B33
    same_prompt = (P3 == B33.PLAIN_PROMPT)
    data = json.loads((ROOT / "data/wikistate_full_ALL_v24.json").read_text(
        encoding="utf-8"))
    e0 = next(e for e in data if e["uid"] == uids[0])
    same_render = (R3(e0.get("sessions", [])) == B33.render_transcript(
        e0.get("sessions", [])))
    print("## 0. Arm identity check\n")
    print("  fullplain (this batch) == smwplain (33-A)?  PLAIN_PROMPT identical: "
          "%s | render_transcript output identical on %s: %s | system prompt empty "
          "in both: True" % (same_prompt, uids[0], same_render))
    print("  => fullplain@sonnet5 is the SAME arm as b33A_smwplain@haiku, only the "
          "reader differs.\n")

    # ── 装载 ────────────────────────────────────────────────────
    D = {}
    for name, paths, pr, reader, note in ARMS:
        D[name] = (load_many(paths, qids), pr, reader, note)

    print("## 1. Coverage / integrity\n")
    print("| arm | file(s) | rows | unique qid in 140-set | reader errors | "
          "judge fallbacks | empty answers | stop_reason != end_turn |")
    print("|---|---|---|---|---|---|---|---|")
    for name, paths, pr, reader, note in ARMS:
        d = D[name][0]
        tot = sum(DUP_STATS.get(p, (0,))[0] for p in paths)
        errs = sum(1 for r in d.values() if r.get("reader_error"))
        fb = sum(1 for r in d.values()
                 if str(r.get("judge_reason", "")).startswith("FALLBACK"))
        emp = sum(1 for r in d.values() if not str(r.get("answer") or "").strip())
        sr = [k for k, r in d.items()
              if r.get("stop_reason") not in (None, "", "end_turn")]
        print("| %s | %s | %d | %d | %d | %d | %d | %d |"
              % (name.strip(), ", ".join(paths), tot, len(d), errs, fb, emp,
                 len(sr)))
    miss = sorted(qids - set(D["fullplain@sonnet5 (full text + plain QA)"][0]))
    if miss:
        print("\n  !! fullplain@sonnet5 is INCOMPLETE (%d/140). Missing: %s"
              % (len(D["fullplain@sonnet5 (full text + plain QA)"][0]),
                 ", ".join(miss)))
        print("     Cause: the $8 reader-spend cap tripped mid-run (the budget "
              "gate stopped the queue at $7.95; in-flight calls carried the "
              "batch total to $8.137). Completing these 2 questions costs about "
              "$0.08 more.")

    # ── 主表 ────────────────────────────────────────────────────
    print("\n## 2. Headline table (restricted to the same 140 question_ids)\n")
    print("| arm | reader | source | n | acc | " + " | ".join(TYPES) +
          " | mean in tok | mean out tok | median lat s | $/q |")
    print("|---" * (11 + 0) + "|")
    for name, paths, pr, reader, note in ARMS:
        d, (pi, po), rd, nt = D[name]
        if not d:
            print("| %s | %s | %s | 0 | (no rows) | | | | | | | |"
                  % (name.strip(), rd, nt))
            continue
        mi, mo, lat, cpq = stats(list(d.values()), pi, po)
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| %s | %s | %s | %d | **%.1f%%** | %s | %.0f | %.0f | %.2f | $%.5f |"
              % (name.strip(), rd, nt, len(d), acc(d), tys, mi, mo, lat, cpq))
    print("\nPrices: claude-sonnet-5 $2.00/M in, $10.00/M out; claude-haiku-4-5 "
          "$1.00/M in, $5.00/M out. Reader cost only (judge excluded).")

    # ── 配对 ────────────────────────────────────────────────────
    K = list(D)
    smoc5, dir5, full5 = K[0], K[1], K[2]
    pl800, plmt, smocH, dirH, swpH, smwH, plH = K[3], K[4], K[5], K[6], K[7], K[8], K[9]

    print("\n## 3. Paired McNemar (exact binomial) — the lines the task asked for\n")
    print("  [same reader = sonnet-5, the contrast batch 36 could not make]")
    cmp2("smoc@sonnet5", D[smoc5][0], "plainctx@sonnet5 mt800", D[pl800][0])
    cmp2("smoc@sonnet5", D[smoc5][0], "plainctx@sonnet5 mt4000-corr", D[plmt][0])
    cmp2("direct@sonnet5", D[dir5][0], "plainctx@sonnet5 mt800", D[pl800][0])
    cmp2("direct@sonnet5", D[dir5][0], "plainctx@sonnet5 mt4000-corr", D[plmt][0])
    cmp2("fullplain@sonnet5", D[full5][0], "plainctx@sonnet5 mt800", D[pl800][0])
    cmp2("fullplain@sonnet5", D[full5][0], "plainctx@sonnet5 mt4000-corr",
         D[plmt][0])
    print("\n  [reader effect, arm held fixed]")
    cmp2("smoc@sonnet5", D[smoc5][0], "smoc@haiku", D[smocH][0])
    cmp2("direct@sonnet5", D[dir5][0], "direct@haiku", D[dirH][0])
    cmp2("fullplain@sonnet5", D[full5][0], "smwplain@haiku (=fullplain)",
         D[swpH][0])

    print("\n## 4. Extra same-reader lines (not requested, but they are the "
          "within-reader ladder)\n")
    cmp2("smoc@sonnet5", D[smoc5][0], "direct@sonnet5", D[dir5][0])
    cmp2("smoc@sonnet5", D[smoc5][0], "fullplain@sonnet5", D[full5][0])
    cmp2("plainctx@sonnet5 mt4000", D[plmt][0], "fullplain@sonnet5", D[full5][0])
    print("\n  [the haiku ladder on the same 140 q, for reference]")
    cmp2("smoc@haiku", D[smocH][0], "plainctx@haiku", D[plH][0])
    cmp2("smoc@haiku", D[smocH][0], "smw@haiku", D[smwH][0])
    cmp2("smoc@haiku", D[smocH][0], "direct@haiku", D[dirH][0])

    # ── 成本 ────────────────────────────────────────────────────
    print("\n## 5. Cost at equal reader (claude-sonnet-5)\n")
    base = stats(list(D[plmt][0].values()), *S5)[3]
    print("| arm | $/q | x vs plainctx@sonnet5(corrected) | in tok/q | "
          "x in-token vs plainctx |")
    print("|---|---|---|---|---|")
    bi = stats(list(D[plmt][0].values()), *S5)[0]
    for n in (smoc5, dir5, full5, pl800, plmt):
        d, pr, rd, nt = D[n]
        mi, mo, lat, c = stats(list(d.values()), *pr)
        print("| %s | $%.5f | %.2fx | %.0f | %.2fx |"
              % (n.strip(), c, c / base, mi, mi / bi))

    # ── 判官成本 ────────────────────────────────────────────────
    print("\n## 6. Judge-side cost of THIS batch (claude-opus-5 $5/M in, $25/M out)\n")
    ji = jo = jn = 0
    for n in (smoc5, dir5, full5):
        for r in D[n][0].values():
            if r.get("judge_input_tokens") is not None:
                ji += r["judge_input_tokens"] or 0
                jo += r["judge_output_tokens"] or 0
                jn += 1
    print("  judged rows with usage recorded: %d | in %d / out %d tok | $%.3f"
          % (jn, ji, jo, ji / 1e6 * 5 + jo / 1e6 * 25))
    ri = ro = 0.0
    for n in (smoc5, dir5, full5):
        for r in D[n][0].values():
            ri += (r.get("usage_input_tokens") or 0) / 1e6 * 2
            ro += (r.get("usage_output_tokens") or 0) / 1e6 * 10
    print("  reader spend of this batch (3 arms, as landed on disk): $%.3f"
          % (ri + ro))


if __name__ == "__main__":
    main()
