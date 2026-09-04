# -*- coding: utf-8 -*-
"""批 40 记分器:104K 店(L2,30 店 / 120 题)× 强读者 claude-sonnet-5——
QVF 槽位投影 / QVF 全账目 / 稠密 top-100 / 现实全文直读(plainctx)四臂。

口径沿用 scripts/b39_score.py(它自己沿用 b33A_score 的 load/acc/sign_p):
- 去重:同一 question_id 保留**首次**出现;
- 配对 McNemar(精确二项符号检验)+ 店级簇自助 CI(N=4000, seed=40);
- 读者成本按 claude-sonnet-5 $2.00/M in、$10.00/M out(协调员口径);
- 判官成本按 claude-opus-5 $5.00/M in、$25.00/M out(官方 list price)单列;
- 锚覆盖率(仅 top100 臂有定义):同 scripts/b39_score.py 的 anchor_index/coverage。

参照(归档,不重跑,$0):
  104K x haiku  : 批 33-D/39 头条(ledger/projection/fulltext)
  14K  x haiku  : 批 36 头条 plainctx@haiku(mt800,haiku 不开思考、800 已够)
  14K  x sonnet : 批 36 头条 plainctx@sonnet5(mt800 与 mt4000 截断校正)

用法: PYTHONUTF8=1 python scripts/b40_score.py > results/b40_score_out.txt
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p            # noqa: E402

N_BOOT, SEED = 4000, 40
P_IN, P_OUT = 2.00, 10.00                # claude-sonnet-5 读者口径
J_IN, J_OUT = 5.00, 25.00                # claude-opus-5 判官官方 list price
QREF = "data/wsc_long_L1_questions.jsonl"
DATA = "data/wikistate_long_L2_b33.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]

# ── 本批四臂(全部 claude-sonnet-5,max_tokens=4000,不发 temperature) ──
ARMS = [
    ("projection (slot)@sonnet5", "results/b40_slot_L2_sonnet5.jsonl"),
    ("ledger (QVF full)@sonnet5", "results/b40_ledger_L2_sonnet5.jsonl"),
    ("dense_top100@sonnet5",      "results/b40_top100_L2_sonnet5.jsonl"),
    ("plainctx (full context)@sonnet5", "results/b40_plainctx_L2_sonnet5.jsonl"),
]
KEY = {n: n for n, _ in ARMS}
PROJ, LEDGER, TOP100, PLAIN = [n for n, _ in ARMS]

# ── 归档参照:104K x haiku(批 33-D/39 头条) ─────────────────────
REFS_104K_HAIKU = [
    ("ledger (QVF full)@haiku(104K)", ["results/b33d_smoc_L2_new20.jsonl",
                                       "results/b33d_smoc_L2_old10_repro.jsonl"]),
    ("projection (slot)@haiku(104K)", ["results/b33d_slot_L2_new20.jsonl",
                                       "results/b33_smoc_L2probe_slot.jsonl"]),
    ("fulltext(fullplain)@haiku(104K)", ["results/b33d_full_haiku_L2_new15.jsonl",
                                         "results/b27_full_haiku_L2.jsonl"]),
    ("dense_top100@haiku(104K)", ["results/b39_dense_top100_L2.jsonl"]),
]

# ── 归档参照:14K(L0,批 36/36-B,不同题集/不同店,只取头条数字对照) ──
REFS_14K = [
    ("plainctx@haiku(14K,mt800)", ["results/b36_plainctx_haiku-4-5.jsonl"]),
    ("plainctx@sonnet5(14K,mt800)", ["results/b36_plainctx_sonnet-5.jsonl"]),
    ("plainctx@sonnet5(14K,mt4000 截断校正)",
     ["results/b36_plainctx_sonnet-5.jsonl",
      "results/b36_plainctx_sonnet-5_mt4000.jsonl"]),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def load_many(paths, prefer_last=True):
    """paths 靠后的文件覆盖靠前的(用于 mt800→mt4000 截断校正合并,
    与 b36b_score.py 的合并口径一致)。"""
    out = {}
    for p in paths:
        for q, r in load(p).items():
            if prefer_last or q not in out:
                out[q] = r
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, (c - h) * 100), min(1.0, c + h) * 100)


def by_type(d, t):
    rs = [r for r in d.values() if r.get("question_type") == t]
    return (sum(1 for r in rs if r["judge_correct"]) / len(rs) * 100) if rs else None


def compare(label, base, test, boot=True):
    keys = sorted(set(base) & set(test))
    if not keys:
        print("### " + label + ": no overlap")
        return None
    b = sum(1 for q in keys if base[q]["judge_correct"] and not test[q]["judge_correct"])
    c = sum(1 for q in keys if not base[q]["judge_correct"] and test[q]["judge_correct"])
    delta = (sum(bool(test[q]["judge_correct"]) for q in keys)
             - sum(bool(base[q]["judge_correct"]) for q in keys)) / len(keys) * 100
    clusters = defaultdict(list)
    for q in keys:
        uid = test[q].get("uid") or base[q].get("uid") or q.split("_")[0]
        clusters[uid].append((int(bool(test[q]["judge_correct"])),
                              int(bool(base[q]["judge_correct"]))))
    print("### " + label)
    print("  n=%d q / %d stores | delta=%+.2fpp  b/c=%d/%d  McNemar p=%.4g"
          % (len(keys), len(clusters), delta, b, c, sign_p(b, c)))
    if not boot:
        return delta
    random.seed(SEED)
    ks = list(clusters)
    ds = []
    for _ in range(N_BOOT):
        samp = [clusters[random.choice(ks)] for _ in ks]
        num = sum(x - y for it in samp for x, y in it)
        den = sum(len(it) for it in samp)
        ds.append(num / den * 100)
    ds.sort()
    lo, hi = ds[int(.025 * N_BOOT)], ds[int(.975 * N_BOOT)]
    cw = sum(1 for it in clusters.values() if sum(x - y for x, y in it) > 0)
    cl = sum(1 for it in clusters.values() if sum(x - y for x, y in it) < 0)
    ct = len(clusters) - cw - cl
    print("  store sign test %dW/%dL/%dT p=%.4g | cluster boot 95%% CI "
          "[%+.2f,%+.2f]pp (N=%d, seed=%d)"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi, N_BOOT, SEED))
    return delta


def anchor_index(entries):
    out = {}
    for uid, e in entries.items():
        rows = []
        for c in e.get("chain", []):
            span = c.get("state_span", "")
            sid = None
            for si, s in enumerate(e.get("sessions", [])):
                if any(span and span in str(t) for t in s.get("turns", [])):
                    sid = f"s{si}"
                    break
            rows.append((sid, str(c.get("date", ""))))
        out[uid] = rows
    return out


def sess_of(mid: str) -> str:
    return mid.rsplit("/", 1)[-1].split("#")[0]


def coverage(rows, anchors, today_of):
    tot = cov = tot_a = cov_a = miss = 0
    for r in rows.values():
        got = {sess_of(m) for m in (r.get("retrieved_memory_ids") or [])}
        t0 = today_of.get(r["question_id"], "9999-12-31")
        for sid, adate in anchors.get(r["uid"], []):
            if sid is None:
                miss += 1
                continue
            tot += 1
            cov += sid in got
            if adate <= t0:
                tot_a += 1
                cov_a += sid in got
    return (cov / tot * 100 if tot else None,
            cov_a / tot_a * 100 if tot_a else None, miss, tot, tot_a)


def main() -> int:
    qs = [json.loads(l) for l in open(ROOT / QREF, encoding="utf-8") if l.strip()]
    qref = {q["qid"] for q in qs}
    entries = {e["uid"]: e for e in
               json.loads((ROOT / DATA).read_text(encoding="utf-8"))}
    import re
    trex = re.compile(r"\(Today is ([0-9][0-9-]*)\.?\)")
    today_of = {}
    for q in qs:
        m = trex.search(q["question"])
        if m:
            today_of[q["qid"]] = m.group(1)
        else:
            ds = [s.get("date", "") for s in entries[q["uid"]]["sessions"]]
            today_of[q["qid"]] = max(ds) if ds else "9999-12-31"
    anchors = anchor_index(entries)

    data = {}
    for name, path in ARMS:
        if (ROOT / path).exists():
            data[name] = restrict(load(path), qref)

    print("# Batch 40 score — 104K-token L2 stores x strong reader "
          "(claude-sonnet-5, max_tokens=4000, no temperature)")
    print("# corpus %s | questions %s (120 = 30 uid x 4 qtypes)" % (DATA, QREF))
    print("# judge qvf.judge.ClaudeJudge (claude-opus-5, frozen)\n")

    print("## 0. Row ledger / completeness\n")
    print("| arm | source rows | deduped | dup rows | qid symdiff vs the 120 | "
          "non-end_turn stop | truncated-empty (no judge match) |")
    print("|---|---|---|---|---|---|---|")
    for name, path in ARMS:
        if name not in data:
            print("| %s | MISSING (%s) | | | | | |" % (name, path))
            continue
        d = data[name]
        t, u, dp, ag = DUP_STATS.get(path, (0, 0, 0, None))
        nend = sum(1 for r in d.values()
                   if r.get("stop_reason") and r.get("stop_reason") != "end_turn")
        print("| %s | %d | %d | %d | %d | %d | - |"
              % (name, t, u, dp, len(set(d) ^ qref), nend))
    missing = [n for n, _ in ARMS if n not in data]
    incomplete = {n: len(data[n]) for n in data if len(data[n]) != 120}
    if missing:
        print("\nMISSING arms (not run / not finished): %s" % ", ".join(missing))
    if incomplete:
        print("INCOMPLETE arms (n != 120, likely a budget stop — reported "
              "as-is per prereg, not extrapolated): %s" % incomplete)

    print("\n## 1. Headline (accuracy with Wilson 95% CI)\n")
    print("| arm | n | acc % | Wilson 95% | mean in tok | mean out tok | "
          "reader $/q | reader $ total | median latency s |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, _ in ARMS:
        if name not in data:
            continue
        d = data[name]
        n = len(d)
        k = sum(1 for r in d.values() if r.get("judge_correct"))
        lo, hi = wilson(k, n)
        mi = st.mean(r.get("usage_input_tokens") or 0 for r in d.values())
        mo = st.mean(r.get("usage_output_tokens") or 0 for r in d.values())
        lat = st.median(r.get("latency_s") or 0 for r in d.values())
        cost_q = mi / 1e6 * P_IN + mo / 1e6 * P_OUT
        cost_tot = sum((r.get("usage_input_tokens") or 0) / 1e6 * P_IN +
                       (r.get("usage_output_tokens") or 0) / 1e6 * P_OUT
                       for r in d.values())
        print("| %s | %d | %.2f | [%.1f, %.1f] | %.0f | %.0f | $%.4f | $%.2f | %.2f |"
              % (name, n, k / max(1, n) * 100, lo, hi, mi, mo, cost_q, cost_tot, lat))

    if TOP100 in data:
        cov = coverage(data[TOP100], anchors, today_of)
        print("\ndense_top100 anchor coverage: all=%.1f%% as-of=%.1f%% "
              "(locate-fail=%d of tot=%d/as-of=%d)" % cov)

    print("\n## 2. Accuracy by question type (% correct; n up to 30 each)\n")
    print("| arm | " + " | ".join(TYPES) + " |")
    print("|---|" + "---|" * len(TYPES))
    for name, _ in ARMS:
        if name not in data:
            continue
        d = data[name]
        cells = ["-" if by_type(d, t) is None else "%.1f" % by_type(d, t)
                 for t in TYPES]
        print("| %s | %s |" % (name, " | ".join(cells)))

    print("\n## 3. Paired McNemar — every pair among the four b40 arms "
          "(same overlapping qids)\n")
    for (n1, _), (n2, _) in combinations(ARMS, 2):
        if n1 in data and n2 in data:
            compare("%s vs %s" % (n1, n2), data[n1], data[n2], boot=False)
    print()

    print("\n## 4. Store-level cluster bootstrap — H2/H3 headline comparisons\n")
    if PROJ in data and PLAIN in data:
        print("**H2: projection vs full context (plainctx)**")
        compare("%s vs %s" % (PROJ, PLAIN), data[PLAIN], data[PROJ])
        print()
    if PROJ in data and TOP100 in data:
        print("**H3: top100 vs projection**")
        compare("%s vs %s" % (TOP100, PROJ), data[PROJ], data[TOP100])
        print()
    if PROJ in data and LEDGER in data:
        print("(reference) projection vs QVF full ledger, same reader")
        compare("%s vs %s" % (PROJ, LEDGER), data[LEDGER], data[PROJ])
        print()
    if LEDGER in data and PLAIN in data:
        print("(reference) QVF full ledger vs full context, same reader")
        compare("%s vs %s" % (LEDGER, PLAIN), data[PLAIN], data[LEDGER])
        print()
    if LEDGER in data and TOP100 in data:
        print("(reference) top100 vs QVF full ledger, same reader")
        compare("%s vs %s" % (TOP100, LEDGER), data[LEDGER], data[TOP100])
        print()

    print("\n## 5. Cost ledger (measured tokens, this batch only)\n")
    print("| arm | reader in | reader out | reader $ ($2/$10) | judge in | "
          "judge out | judge $ (opus-5 $5/$25) |")
    print("|---|---|---|---|---|---|---|")
    tot = [0] * 4
    for name, _ in ARMS:
        if name not in data:
            continue
        d = data[name].values()
        ti = sum(r.get("usage_input_tokens") or 0 for r in d)
        to = sum(r.get("usage_output_tokens") or 0 for r in d)
        ji = sum(r.get("judge_input_tokens") or 0 for r in d)
        jo = sum(r.get("judge_output_tokens") or 0 for r in d)
        for i, x in enumerate((ti, to, ji, jo)):
            tot[i] += x
        print("| %s | %d | %d | $%.3f | %d | %d | $%.3f |"
              % (name, ti, to, ti / 1e6 * P_IN + to / 1e6 * P_OUT, ji, jo,
                 ji / 1e6 * J_IN + jo / 1e6 * J_OUT))
    print("| **TOTAL** | %d | %d | $%.3f | %d | %d | $%.3f |"
          % (tot[0], tot[1], tot[0] / 1e6 * P_IN + tot[1] / 1e6 * P_OUT,
             tot[2], tot[3], tot[2] / 1e6 * J_IN + tot[3] / 1e6 * J_OUT))

    print("\n## 6. Truncation diagnostics (stop_reason != end_turn, "
          "max_tokens=4000 budget)\n")
    print("| arm | n | truncated | truncated % | mean in tok (truncated) | "
          "mean in tok (not truncated) | acc on truncated % | acc on rest % |")
    print("|---|---|---|---|---|---|---|---|")
    for name, _ in ARMS:
        if name not in data:
            continue
        d = list(data[name].values())
        trunc = [r for r in d if r.get("stop_reason") and
                 r.get("stop_reason") != "end_turn"]
        rest = [r for r in d if r not in trunc]
        mi_t = st.mean(r["usage_input_tokens"] for r in trunc) if trunc else 0
        mi_r = st.mean(r["usage_input_tokens"] for r in rest) if rest else 0
        acc_t = (sum(1 for r in trunc if r["judge_correct"]) / len(trunc) * 100
                  if trunc else float("nan"))
        acc_r = (sum(1 for r in rest if r["judge_correct"]) / len(rest) * 100
                  if rest else float("nan"))
        print("| %s | %d | %d | %.1f | %.0f | %.0f | %.1f | %.1f |"
              % (name, len(d), len(trunc), len(trunc) / max(1, len(d)) * 100,
                 mi_t, mi_r, acc_t, acc_r))

    print("\n## 7. Archived reference — 104K x haiku (batch 33-D / 39, $0, "
          "not rerun)\n")
    print("| arm | n | acc % |")
    print("|---|---|---|")
    for name, paths in REFS_104K_HAIKU:
        d = restrict(load_many(paths), qref)
        if d:
            print("| %s | %d | %.2f |" % (name, len(d), acc(d)))

    print("\n## 8. Archived reference — 14K / L0 (batch 36, different "
          "question sample & store set, $0, not rerun — sample-composition "
          "caveat applies, see verdict)\n")
    print("| arm | n | acc % |")
    print("|---|---|---|")
    for name, paths in REFS_14K:
        d = load_many(paths)
        if d:
            print("| %s | %d | %.2f |" % (name, len(d), acc(d)))

    print("\n## 9. Four-cell table (scale x reader), headline full-context "
          "arm per cell\n")
    print("| | haiku-4.5 | sonnet-5 |")
    print("|---|---|---|")
    h14 = load_many(["results/b36_plainctx_haiku-4-5.jsonl"])
    s14 = load_many(["results/b36_plainctx_sonnet-5.jsonl",
                     "results/b36_plainctx_sonnet-5_mt4000.jsonl"])
    h104 = restrict(load_many(["results/b33d_full_haiku_L2_new15.jsonl",
                               "results/b27_full_haiku_L2.jsonl"]), qref)
    s104 = data.get(PLAIN, {})
    print("| 14K (L0) | %.1f%% (n=%d, plainctx mt800) | %.1f%% (n=%d, "
          "plainctx mt4000 corrected) |" % (acc(h14), len(h14), acc(s14), len(s14)))
    print("| 104K (L2) | %.1f%% (n=%d, fullplain=PLAIN_PROMPT) | %s |"
          % (acc(h104), len(h104),
             ("%.1f%% (n=%d, plainctx mt4000)" % (acc(s104), len(s104)))
             if s104 else "MISSING"))
    print("\nCaveat: the 14K row uses the `plainctx` prompt (realistic "
          "wording, no length cap) on a different 140-q / different-store "
          "sample (`results/b35_questions_sample36.jsonl`); the 104K-haiku "
          "cell uses `fullplain`=`PLAIN_PROMPT` (\"reply with only the "
          "answer\") on the 30-store L2 sample. Only the sonnet-5 column "
          "(14K plainctx -> 104K plainctx, same prompt) is a clean same-"
          "prompt scale comparison; the haiku row and the cross-row "
          "comparisons mix prompt variants and sample composition.")

    print("\n## 10. Per-store correct-count distribution (of 4 questions each)\n")
    print("| arm | 0 | 1 | 2 | 3 | 4 |")
    print("|---|---|---|---|---|---|")
    for name, _ in ARMS:
        if name not in data:
            continue
        d = data[name]
        per = defaultdict(int)
        for r in d.values():
            per[r["uid"]] += int(bool(r.get("judge_correct")))
        cnt = defaultdict(int)
        for u in per:
            cnt[per[u]] += 1
        print("| %s | %d | %d | %d | %d | %d |"
              % (name, cnt[0], cnt[1], cnt[2], cnt[3], cnt[4]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
