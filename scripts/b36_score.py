# -*- coding: utf-8 -*-
"""批 36 记分器:"现实直读"基线(plainctx,整库原文 + 裸提示)对 33-A 四臂。

口径与 scripts/b33A_score.py / b35_score.py 相同:
- 去重:同一 question_id 保留**首次**出现(b33A_score.load);
- 配对 McNemar = 精确二项符号检验(b33A_score.sign_p),报双向翻转数;
- 全部比较限制到 results/b35_questions_sample36.jsonl 的同 140 题(题面逐字相同)。

用法: PYTHONUTF8=1 python scripts/b36_score.py > results/b36_score_out.txt
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p  # noqa: E402
from repro_batch3 import render_transcript  # noqa: E402

QREF = "results/b35_questions_sample36.jsonl"
DATA = "data/wikistate_full_ALL_v24.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]

NEW = [
    ("plainctx:haiku-4-5", "results/b36_plainctx_haiku-4-5.jsonl", 1.00, 5.00),
    ("plainctx:sonnet-5", "results/b36_plainctx_sonnet-5.jsonl", 2.00, 10.00),
]
# 33-A 对照臂(全部 haiku-4-5 读者、同一 ClaudeJudge)
REF = [
    ("b33A_smwplain (full text + plain QA prompt)", "results/b33A_smwplain.jsonl", 1.00, 5.00),
    ("b33A_smw      (full text + F.1 protocol)", "results/b33A_smw.jsonl", 1.00, 5.00),
    ("b33A_direct   (dense top-10 + excerpts framing)", "results/b33A_direct.jsonl", 1.00, 5.00),
    ("b33A_smoc_v45 (QVF card ledger + F.1)", "results/b33A_smoc_v45.jsonl", 1.00, 5.00),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def stats(rows, pi, po):
    mi = st.mean([r.get("usage_input_tokens") or 0 for r in rows])
    mo = st.mean([r.get("usage_output_tokens") or 0 for r in rows])
    lat = st.median([r.get("latency_s") or 0 for r in rows])
    return mi, mo, lat, mi / 1e6 * pi + mo / 1e6 * po


def compare(label, base, test):
    """base=对照臂, test=新臂;delta 与翻转都以 test 为主语。"""
    keys = sorted(set(base) & set(test))
    if not keys:
        print("  %-48s no overlap" % label)
        return
    b = sum(1 for q in keys if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in keys if not base[q]["judge_correct"] and test[q]["judge_correct"])
    ab = sum(bool(base[q]["judge_correct"]) for q in keys) / len(keys) * 100
    at = sum(bool(test[q]["judge_correct"]) for q in keys) / len(keys) * 100
    clusters = defaultdict(int)
    for q in keys:
        uid = test[q].get("uid") or base[q].get("uid") or q.split("_")[0]
        clusters[uid] += 1
    print("  vs %-46s n=%d | base %5.1f%% -> test %5.1f%% | delta %+6.2fpp | "
          "flips base-right->test-wrong=%2d, base-wrong->test-right=%2d | "
          "McNemar(exact) p=%.4g"
          % (label, len(keys), ab, at, at - ab, b, c, sign_p(b, c)))


def main():
    qref = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qids = {q["qid"] for q in qref}
    uids = sorted({q["uid"] for q in qref})

    print("# Batch 36 — REALISTIC DIRECT baseline (plainctx): whole raw memory in the "
          "prompt, plain call\n")
    print("Arm definition (scripts/b36_plain_fullctx.py):")
    print("  system = \"You are a helpful assistant.\"")
    print("  user   = \"Below is the complete record of my past conversations with you, "
          "in chronological order.\\n\\n<transcript>\\n\\nQuestion: <question>\"")
    print("  max_tokens=800; temperature=0 on haiku only (claude-sonnet-5 rejects the "
          "parameter); no retrieval, no protocol, no length cap, no \"excerpts retrieved "
          "from memory\" framing.")
    print("  transcript = repro_batch3.render_transcript(entry['sessions']) — the SAME "
          "function batch 33-A's smw/smwplain used (AST-verified byte-identical to the "
          "copy in repro_batch3_b33.py), so the paired contrast isolates the prompt "
          "framing only.")
    print("  judge = qvf.judge.ClaudeJudge() default model (claude-opus-5), same call "
          "pattern as scripts/lb_reader_arm.py.\n")
    print("Corpus: %s (v2.4) | Questions: %s (%d q, %d chains)\n"
          % (DATA, QREF, len(qids), len(uids)))

    # ── 誊录统计 ────────────────────────────────────────────────
    entries = {e["uid"]: e for e in
               json.loads((ROOT / DATA).read_text(encoding="utf-8"))}
    chars, turns, sess, roles, trunc = [], [], [], defaultdict(int), 0
    for u in uids:
        ss = entries[u].get("sessions", [])
        sess.append(len(ss))
        chars.append(len(render_transcript(ss)))
        nt = 0
        for s in ss:
            for x in s.get("turns", []):
                nt += 1
                stx = str(x)
                if stx.startswith("{'role'"):
                    r = stx.split("'")[3]
                    roles[r] += 1
                    if r == "assistant":
                        try:
                            eval(stx, {"__builtins__": {}})  # noqa: S307
                        except Exception:  # noqa: BLE001
                            trunc += 1
                else:
                    roles["bare-string chain turn"] += 1
        turns.append(nt)
    print("## 0. Transcript (what the reader actually saw)\n")
    print("| metric | min | median | mean | max |")
    print("|---|---|---|---|---|")
    print("| chars / store | %d | %d | %d | %d |"
          % (min(chars), st.median(chars), st.mean(chars), max(chars)))
    print("| sessions / store | %d | %d | %.1f | %d |"
          % (min(sess), st.median(sess), st.mean(sess), max(sess)))
    print("| turns / store | %d | %d | %.1f | %d |"
          % (min(turns), st.median(turns), st.mean(turns), max(turns)))
    print("\nTurn composition across the %d stores: %s" % (len(uids), dict(roles)))
    print("ASSISTANT TURNS ARE INCLUDED: %d assistant turns are rendered verbatim in the "
          "transcript, interleaved with %d user turns and %d bare-string chain turns, in "
          "date order, each session preceded by a `--- session date: YYYY-MM-DD ---` line."
          % (roles["assistant"], roles["user"], roles["bare-string chain turn"]))
    print("Caveat (a property of the v2.4 corpus, identical for batch 33-A's smw/smwplain "
          "arms): %d of %d assistant turns are stored PRE-TRUNCATED at 400 characters, so "
          "render_transcript's dict-repr unpacking fails on them and they appear as the "
          "raw truncated repr `{'role': 'assistant', 'content': \"...` rather than as "
          "`assistant: ...`. Nothing is dropped — the text is verbatim what the corpus "
          "holds — but assistant replies are cut off mid-sentence in the corpus itself."
          % (trunc, roles["assistant"]))

    # ── 数据装载 ────────────────────────────────────────────────
    new = {}
    for n, p, pi, po in NEW:
        d = restrict(load(p), qids)
        new[n] = (d, pi, po)
    ref = {}
    for n, p, pi, po in REF:
        ref[n] = (restrict(load(p), qids), pi, po)

    print("\n## 1. Dedupe / coverage audit\n")
    print("| file | rows read | unique qid | dups dropped | dup agreement | "
          "kept (in 140-q set) |")
    print("|---|---|---|---|---|---|")
    for n, p, _, _ in NEW + REF:
        t, u, dp, ag = DUP_STATS.get(p, (0, 0, 0, None))
        kept = len((new.get(n) or ref.get(n))[0])
        print("| %s | %d | %d | %d | %s | %d |"
              % (p, t, u, dp, ("%.1f%%" % ag) if ag is not None else "-", kept))

    # ── 主表 ────────────────────────────────────────────────────
    print("\n## 2. Headline (same 140 question_ids)\n")
    hdr = ("| arm | reader | n | acc | " + " | ".join(TYPES) +
           " | mean in tok | mean out tok | median lat s | $/q |")
    print(hdr)
    print("|---" * (7 + len(TYPES)) + "|")
    order = [(n, new[n][0], new[n][1], new[n][2], n.split(":")[1]) for n in new] + \
            [(n, ref[n][0], ref[n][1], ref[n][2], "haiku-4-5") for n in ref]
    for n, d, pi, po, rd in order:
        if not d:
            print("| %s | %s | 0 | (no rows) |" % (n, rd))
            continue
        mi, mo, lat, cpq = stats(list(d.values()), pi, po)
        tys = " | ".join(("%.1f" % by_type(d, t)) if by_type(d, t) is not None
                         else "-" for t in TYPES)
        print("| %s | %s | %d | %.1f%% | %s | %.0f | %.0f | %.2f | $%.5f |"
              % (n, rd, len(d), acc(d), tys, mi, mo, lat, cpq))
    print("\nPrices: haiku-4-5 $1.00/M in, $5.00/M out; claude-sonnet-5 $2.00/M in, "
          "$10.00/M out. Reader cost only (judge excluded).")

    # ── 配对比较 ────────────────────────────────────────────────
    print("\n## 3. Paired comparisons (McNemar exact binomial, same question_ids)\n")
    for n in new:
        d = new[n][0]
        if not d:
            continue
        print("### %s (test) vs each archived arm (base)" % n)
        for rn in ref:
            compare(rn, ref[rn][0], d)
        print()
    if all(new[n][0] for n in new):
        ns = list(new)
        print("### reader effect inside plainctx")
        compare(ns[0] + " (base)", new[ns[0]][0], new[ns[1]][0])
        print()

    # ── 读者错误自查 ────────────────────────────────────────────
    print("## 4. Run integrity\n")
    for n in new:
        d = new[n][0]
        if not d:
            continue
        errs = [q for q, r in d.items() if r.get("reader_error")]
        empt = [q for q, r in d.items() if not (r.get("answer") or "").strip()]
        fb = [q for q, r in d.items()
              if str(r.get("judge_reason", "")).startswith("FALLBACK")]
        maxout = [q for q, r in d.items() if (r.get("usage_output_tokens") or 0) >= 800]
        print("  %-22s rows=%d | reader errors=%d | empty answers=%d | "
              "judge fallbacks=%d | output hit max_tokens(800)=%d"
              % (n, len(d), len(errs), len(empt), len(fb), len(maxout)))
        if maxout:
            print("     truncated-output qids: %s" % ", ".join(sorted(maxout)[:10]))

    # ── 5. 截断灵敏度(非主表) ─────────────────────────────────
    print("\n## 5. Truncation sensitivity (NOT the headline; max_tokens 800 -> 4000 "
          "rerun of exactly the questions whose output hit the 800 cap)\n")
    print("Why: claude-sonnet-5 has extended thinking on by default and max_tokens caps "
          "thinking + visible text together, so a question that spends 800 tokens "
          "thinking returns an EMPTY text block and is graded wrong. This is a cap "
          "artifact, not a reasoning failure. The 800-token protocol above is the "
          "coordinator-specified headline; this section bounds how much it costs.\n")
    SENS = [("plainctx:haiku-4-5", "results/b36_plainctx_haiku-4-5.jsonl",
             "results/b36_plainctx_haiku-4-5_mt4000.jsonl"),
            ("plainctx:sonnet-5", "results/b36_plainctx_sonnet-5.jsonl",
             "results/b36_plainctx_sonnet-5_mt4000.jsonl")]
    for n, base_p, re_p in SENS:
        if not (ROOT / re_p).exists():
            print("  %-22s no rerun file" % n)
            continue
        base = restrict(load(base_p), qids)
        redo = restrict(load(re_p), qids)
        was = sum(1 for q in redo if base[q]["judge_correct"])
        now = sum(1 for q in redo if redo[q]["judge_correct"])
        merged = dict(base)
        merged.update(redo)
        emp_b = sum(1 for q in redo if not (base[q].get("answer") or "").strip())
        emp_a = sum(1 for q in redo if not (redo[q].get("answer") or "").strip())
        pi, po = (new[n][1], new[n][2])
        _, _, _, c0 = stats(list(base.values()), pi, po)
        mi, mo, lat, c1 = stats(list(merged.values()), pi, po)
        print("  %-22s reran %d capped q | correct %d/%d -> %d/%d | empty answers "
              "%d -> %d | arm accuracy %.1f%% (800) -> %.1f%% (truncation-corrected)"
              % (n, len(redo), was, len(redo), now, len(redo), emp_b, emp_a,
                 acc(base), acc(merged)))
        print("       cost/q $%.5f -> $%.5f | mean out tok -> %.0f | median lat -> "
              "%.2fs" % (c0, c1, mo, lat))
        for rn in ref:
            compare("[corrected] " + rn, ref[rn][0], merged)
        print()


if __name__ == "__main__":
    main()
