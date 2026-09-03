# -*- coding: utf-8 -*-
"""批 39 记分器:规模轴 L2(30 店 / 120 题)上的检索侧基线 vs 归档账目三臂。

口径沿用 scripts/b37_score.py(它自己沿用 b33A_score 的 load/acc/sign_p):
- 去重:同一 question_id 保留**首次**出现;
- 配对 McNemar(精确二项符号检验)+ 店级簇自助 CI(N=4000, seed=39);
- 读者成本按 haiku $1.00/M in、$5.00/M out(协调员口径),检索步 LLM 用量单列;
- 判官成本按 claude-opus-5 $5.00/M in、$25.00/M out(官方 list price)**单独**列出;
- 锚覆盖率:语料 chain[*].state_span 所在会话是否落在该题检索集合里
  (L2 上 120 个锚已核 120/120 唯一命中,且与 sessions[*].chain_index 一致)。

参照臂(归档,批 33-D 头条口径,各 120 行拼成):
  ledger      全账目 smoc  = b33d_smoc_L2_new20 (80) + b33d_smoc_L2_old10_repro (40)
  projection  槽位投影      = b33d_slot_L2_new20 (80) + b33_smoc_L2probe_slot (40)
  fulltext    haiku 全文    = b33d_full_haiku_L2_new15 (60) + b27_full_haiku_L2 (60)
三臂都不做检索,故锚覆盖率对它们**无定义**(表中 n/a)。

用法: QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b39_score.py \
        > results/b39_score_out.txt
"""
from __future__ import annotations

import json
import random
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p            # noqa: E402

N_BOOT, SEED = 4000, 39
P_IN, P_OUT = 1.00, 5.00                 # haiku 读者口径(协调员指定)
J_IN, J_OUT = 5.00, 25.00                # claude-opus-5 判官官方 list price
QREF = "data/wsc_long_L1_questions.jsonl"
DATA = "data/wikistate_long_L2_b33.json"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
VARIANTS = ["direct", "dense_top50", "dense_top100", "rerank"]

# 归档参照臂:每条是 (显示名, [组成文件]);行按 question_id 首次出现去重后合并。
REFS = [
    ("ledger (QVF full)", ["results/b33d_smoc_L2_new20.jsonl",
                           "results/b33d_smoc_L2_old10_repro.jsonl"]),
    ("projection (slot)", ["results/b33d_slot_L2_new20.jsonl",
                           "results/b33_smoc_L2probe_slot.jsonl"]),
    ("haiku full text",  ["results/b33d_full_haiku_L2_new15.jsonl",
                          "results/b27_full_haiku_L2.jsonl"]),
]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


def load_many(paths):
    out = {}
    for p in paths:
        for q, r in load(p).items():
            out.setdefault(q, r)
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
    """base = 参照臂,test = 被比较臂;delta = test - base。"""
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
    print("  flips: base-right->test-wrong = %d | base-wrong->test-right = %d"
          % (b, c))
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


# ── 锚覆盖率(与 b37_score 同函数) ───────────────────────────────
def anchor_index(entries):
    """uid -> [(session_id, anchor_date)],由 chain[*].state_span 定位所在会话。"""
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
    """返回 (全锚覆盖率, as-of 锚覆盖率, 定位失败锚数, 全锚数, as-of 锚数)。"""
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

    refs = {name: restrict(load_many(paths), qref) for name, paths in REFS}
    ledger = refs["ledger (QVF full)"]
    proj = refs["projection (slot)"]
    full = refs["haiku full text"]

    data = {}
    for v in VARIANTS:
        p = f"results/b39_{v}_L2.jsonl"
        if (ROOT / p).exists():
            data[v] = restrict(load(p), qref)

    print("# Batch 39 — retrieval baselines at L2 scale (30 stores / 120 q)")
    print("# corpus %s | questions %s" % (DATA, QREF))
    print("# stores: ~440.6K chars median (~104K tok), 271.5 sessions, "
          "1353 turns median; 120 chain anchors total")
    print("# reader claude-haiku-4-5 (max_tokens 800, temperature 0, frozen "
          "READER_SYSTEM + dated-transcript rendering; identical to batch 37)")
    print("# retriever OpenAIDenseRetriever/text-embedding-3-small over "
          "40,585 turn vectors (results/b39_emb_L2_turns.npz, shared by all "
          "variants) | judge qvf.judge.ClaudeJudge (claude-opus-5, frozen)")
    print("# archived reference arms are batch 33-D headline rows "
          "(results/opt_batch33_D_scaleL2_verdict.md)\n")

    print("## 0. Row ledger\n")
    print("| arm | source rows | deduped | dup rows | first/later agreement | "
          "qid symdiff vs the 120 | FALLBACK judge rows |")
    print("|---|---|---|---|---|---|---|")
    for name, paths in REFS:
        d = refs[name]
        t = u = dp = 0
        ags = []
        for p in paths:
            a, b_, c_, ag = DUP_STATS.get(p, (0, 0, 0, None))
            t += a
            u += b_
            dp += c_
            if ag is not None:
                ags.append(ag)
        fb = sum(1 for r in d.values()
                 if str(r.get("judge_reason", "")).startswith("FALLBACK"))
        print("| %s | %d | %d | %d | %s | %d | %d |"
              % (name, t, len(d), dp,
                 ("%.1f%%" % st.mean(ags)) if ags else "-",
                 len(set(d) ^ qref), fb))
    for v in VARIANTS:
        if v not in data:
            continue
        p = f"results/b39_{v}_L2.jsonl"
        t, u, dp, ag = DUP_STATS.get(p, (0, 0, 0, None))
        fb = sum(1 for r in data[v].values()
                 if str(r.get("judge_reason", "")).startswith("FALLBACK"))
        print("| %s | %d | %d | %d | %s | %d | %d |"
              % (v, t, u, dp, ("%.1f%%" % ag) if ag is not None else "-",
                 len(set(data[v]) ^ qref), fb))
    missing = [v for v in VARIANTS if v not in data]
    incomplete = {v: len(d) for v, d in data.items() if len(d) != 120}
    if missing:
        print("\nMISSING variant files (not run): %s" % ", ".join(missing))
    if incomplete:
        print("INCOMPLETE variants (n != 120): %s" % incomplete)

    print("\n## 1. Headline (accuracy with Wilson 95% CI)\n")
    print("| arm | n | acc % | Wilson 95% | anchor cov % | as-of anchor cov % | "
          "mean in tok | mean out tok | retr in/out tok | reader $/q | "
          "median latency s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")

    def line(name, d, cov3):
        n = len(d)
        k = sum(1 for r in d.values() if r.get("judge_correct"))
        lo, hi = wilson(k, n)
        mi = st.mean([r.get("usage_input_tokens") or 0 for r in d.values()])
        mo = st.mean([r.get("usage_output_tokens") or 0 for r in d.values()])
        ri = st.mean([r.get("retrieval_input_tokens") or 0 for r in d.values()])
        ro = st.mean([r.get("retrieval_output_tokens") or 0 for r in d.values()])
        lat = st.median([r.get("latency_s") or 0 for r in d.values()])
        cost = (mi + ri) / 1e6 * P_IN + (mo + ro) / 1e6 * P_OUT
        cv = ("%.1f" % cov3[0]) if cov3 and cov3[0] is not None else "n/a"
        cva = ("%.1f" % cov3[1]) if cov3 and cov3[1] is not None else "n/a"
        print("| %s | %d | %.2f | [%.1f, %.1f] | %s | %s | %.0f | %.0f | "
              "%.0f/%.0f | $%.4f | %.2f |"
              % (name, n, k / max(1, n) * 100, lo, hi, cv, cva, mi, mo, ri, ro,
                 cost, lat))

    for name, _ in REFS:
        line(name, refs[name], None)
    for v in VARIANTS:
        if v in data:
            line(v, data[v], coverage(data[v], anchors, today_of))

    print("\n## 2. Accuracy by question type (% correct; n=30 each)\n")
    print("| arm | " + " | ".join(TYPES) + " |")
    print("|---|" + "---|" * len(TYPES))
    for name, d in [(n, refs[n]) for n, _ in REFS] + \
            [(v, data[v]) for v in VARIANTS if v in data]:
        cells = ["-" if by_type(d, t) is None else "%.1f" % by_type(d, t)
                 for t in TYPES]
        print("| %s | %s |" % (name, " | ".join(cells)))

    print("\n## 3. Paired McNemar — each variant vs each archived arm "
          "(same 120 qids)\n")
    for refname, base in (("ledger 54.2", ledger), ("projection 61.7", proj),
                          ("haiku full text 7.5", full)):
        for v in VARIANTS:
            if v in data:
                compare("%s vs %s" % (v, refname), base, data[v], boot=False)
        print()

    best = max((v for v in data), key=lambda v: acc(data[v]), default=None)
    if best:
        print("\n## 4. Store-level cluster bootstrap — best variant vs "
              "ledger / projection\n")
        print("Strongest retrieval variant by accuracy: **%s** (%.2f%%)\n"
              % (best, acc(data[best])))
        compare("%s vs ledger (QVF full)" % best, ledger, data[best])
        compare("%s vs projection (slot)" % best, proj, data[best])
        compare("%s vs haiku full text" % best, full, data[best])
        print("\n(reference, archived-only) projection vs ledger:")
        compare("projection vs ledger", ledger, proj)

    print("\n## 5. Cost ledger (measured tokens, this batch only)\n")
    print("| variant | reader in | reader out | retrieval in | retrieval out | "
          "haiku $ ($1/$5) | judge in | judge out | judge $ (opus-5 $5/$25) |")
    print("|---|---|---|---|---|---|---|---|---|")
    tot = [0] * 6
    for v in VARIANTS:
        if v not in data:
            continue
        d = data[v].values()
        ti = sum(r.get("usage_input_tokens") or 0 for r in d)
        to = sum(r.get("usage_output_tokens") or 0 for r in d)
        ri = sum(r.get("retrieval_input_tokens") or 0 for r in d)
        ro = sum(r.get("retrieval_output_tokens") or 0 for r in d)
        ji = sum(r.get("judge_input_tokens") or 0 for r in d)
        jo = sum(r.get("judge_output_tokens") or 0 for r in d)
        for i, x in enumerate((ti, to, ri, ro, ji, jo)):
            tot[i] += x
        print("| %s | %d | %d | %d | %d | $%.3f | %d | %d | $%.3f |"
              % (v, ti, to, ri, ro,
                 (ti + ri) / 1e6 * P_IN + (to + ro) / 1e6 * P_OUT,
                 ji, jo, ji / 1e6 * J_IN + jo / 1e6 * J_OUT))
    print("| **TOTAL** | %d | %d | %d | %d | $%.3f | %d | %d | $%.3f |"
          % (tot[0], tot[1], tot[2], tot[3],
             (tot[0] + tot[2]) / 1e6 * P_IN + (tot[1] + tot[3]) / 1e6 * P_OUT,
             tot[4], tot[5], tot[4] / 1e6 * J_IN + tot[5] / 1e6 * J_OUT))
    print("\nEmbeddings: 40,585 turn vectors x text-embedding-3-small, one-off "
          "cache build (~3.3M tok, ~$0.07 at $0.02/M) + 1 query embedding per "
          "question per variant (negligible).")

    print("\n## 6. Retrieval-set diagnostics\n")
    print("| variant | mean memories rendered | mean anchors hit / question | "
          "questions with 0 anchors hit | mean anchors per store |")
    print("|---|---|---|---|---|")
    for v in VARIANTS:
        if v not in data:
            continue
        ks, hits, zero = [], [], 0
        for r in data[v].values():
            got = {sess_of(m) for m in (r.get("retrieved_memory_ids") or [])}
            ks.append(len(r.get("retrieved_memory_ids") or []))
            h = sum(1 for sid, _ in anchors.get(r["uid"], []) if sid in got)
            hits.append(h)
            zero += (h == 0)
        print("| %s | %.1f | %.2f | %d | %.2f |"
              % (v, st.mean(ks), st.mean(hits), zero,
                 st.mean([len(anchors[u]) for u in anchors])))

    print("\n## 7. Accuracy conditioned on anchor recall "
          "(does the failure sit before or after retrieval?)\n")
    print("| variant | anchor bucket | n q | variant acc % | "
          "ledger acc % (same q) | projection acc % (same q) |")
    print("|---|---|---|---|---|---|")
    full_recall = {}
    for v in VARIANTS:
        if v not in data:
            continue
        buckets = defaultdict(list)
        for qid, r in data[v].items():
            got = {sess_of(m) for m in (r.get("retrieved_memory_ids") or [])}
            a = [s for s, _ in anchors[r["uid"]] if s is not None]
            hit = sum(1 for s in a if s in got)
            b = ("ALL anchors" if a and hit == len(a)
                 else ("ZERO anchors" if hit == 0 else "some anchors"))
            buckets[b].append(qid)
        full_recall[v] = set(buckets["ALL anchors"])
        for b in ("ALL anchors", "some anchors", "ZERO anchors"):
            ids = buckets[b]
            if not ids:
                continue

            def f(dd, ids=ids):
                return sum(1 for q in ids if dd[q]["judge_correct"]) / len(ids) * 100
            print("| %s | %s | %d | %.1f | %.1f | %.1f |"
                  % (v, b, len(ids), f(data[v]), f(ledger), f(proj)))

    if best and full_recall.get(best):
        sub = full_recall[best]
        print("\n### 7b. Paired tests restricted to the best variant's "
              "full-recall subset (n=%d)\n" % len(sub))
        compare("%s vs ledger [full-recall subset]" % best,
                {k: v for k, v in ledger.items() if k in sub},
                {k: v for k, v in data[best].items() if k in sub})
        compare("%s vs projection [full-recall subset]" % best,
                {k: v for k, v in proj.items() if k in sub},
                {k: v for k, v in data[best].items() if k in sub})

    print("\n## 8. Per-store correct-count distribution (of 4 questions each)\n")
    print("| arm | 0 | 1 | 2 | 3 | 4 |")
    print("|---|---|---|---|---|---|")
    for name, d in [(n, refs[n]) for n, _ in REFS] + \
            [(v, data[v]) for v in VARIANTS if v in data]:
        cnt = defaultdict(int)
        per = defaultdict(int)
        for r in d.values():
            per[r["uid"]] += int(bool(r.get("judge_correct")))
        for u in per:
            cnt[per[u]] += 1
        print("| %s | %d | %d | %d | %d | %d |"
              % (name, cnt[0], cnt[1], cnt[2], cnt[3], cnt[4]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
