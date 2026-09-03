# -*- coding: utf-8 -*-
"""批 37 记分器:检索侧 RAG 基线家族 vs 归档 direct / smoc(同 140 题)。

口径沿用 scripts/b33A_score.py(load/acc/sign_p 直接 import):
- 去重:同一 question_id 保留**首次**出现;
- 配对 McNemar(精确二项符号检验)+ 链簇自助 CI(N=4000, seed=37);
- 成本按 haiku $1.00/M in、$5.00/M out(协调员口径),检索步 LLM 用量单列;
- 锚覆盖率:语料 chain[*].state_span 所在会话是否落在该题检索集合里
  (state_span → 会话为 1:1,已核 133/133,且与 sessions[*].chain_index 一致)。

direct 臂的检索集合归档里没有落盘,故用**同一套缓存向量**现场复算 dense
top-10(已用 count_tokens 对 12 题证明与 b33A_direct 的 usage_input_tokens
逐题相等,即复算集合与当年一致),仅用于算锚覆盖率,判决仍读归档行。

用法: QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b37_score.py \
        > results/b37_score_out.txt
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from b33A_score import DUP_STATS, acc, load, sign_p            # noqa: E402

N_BOOT, SEED = 4000, 37
P_IN, P_OUT = 1.00, 5.00                 # haiku 读者口径
J_IN, J_OUT = 15.00, 75.00               # claude-opus-5 判官口径(仅记账)
QREF = "results/b35_questions_sample36.jsonl"
DATA = "data/wikistate_full_ALL_v24.json"
DIRECT = "results/b33A_direct.jsonl"
SMOC = "results/b33A_smoc_v45.jsonl"
TYPES = ["change_count", "count_before", "first_vs_last", "longest_tenure"]
VARIANTS = ["dense_top30", "dense_top50", "session_top5", "hybrid_rrf", "mmr",
            "recency", "asof_filter", "rewrite", "rerank"]


def restrict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


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
    print("  n=%d q / %d chains | delta=%+.2fpp  b/c=%d/%d  McNemar p=%.4g"
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
    print("  chain sign test %dW/%dL/%dT p=%.4g | cluster boot 95%% CI "
          "[%+.2f,%+.2f]pp (N=%d, seed=%d)"
          % (cw, cl, ct, sign_p(cw, cl), lo, hi, N_BOOT, SEED))
    return delta


# ── 锚覆盖率 ────────────────────────────────────────────────────
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
    """返回 (全锚覆盖率, as-of 锚覆盖率, 定位失败锚数)。"""
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
    import re
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

    direct = restrict(load(DIRECT), qref)
    smoc = restrict(load(SMOC), qref)
    data = {}
    for v in VARIANTS:
        p = f"results/b37_{v}.jsonl"
        if (ROOT / p).exists():
            data[v] = restrict(load(p), qref)

    print("# Batch 37 — retrieval-side RAG baseline family (140 q / 36 chains)")
    print("# corpus data/wikistate_full_ALL_v24.json | questions "
          "results/b35_questions_sample36.jsonl")
    print("# reader claude-haiku-4-5 (max_tokens 800, temperature 0, frozen "
          "READER_SYSTEM + dated-transcript rendering of the archived direct arm)")
    print("# retriever OpenAIDenseRetriever/text-embedding-3-small (shared "
          "cached vectors) | judge qvf.judge.ClaudeJudge (claude-opus-5)")
    print("# paired references: %s (direct top-10) and %s (QVF smoc v45), "
          "first occurrence per question_id, same 140 qids\n" % (DIRECT, SMOC))

    print("## 0. Row ledger\n")
    print("| arm | raw rows | deduped | dup rows | first/later agreement | "
          "qid symdiff vs the 140 |")
    print("|---|---|---|---|---|---|")
    for name, pat, d in ([("direct(b33A)", DIRECT, direct),
                          ("smoc_v45(b33A)", SMOC, smoc)] +
                         [(v, f"results/b37_{v}.jsonl", data[v]) for v in data]):
        t, u, dp, ag = DUP_STATS.get(pat, (0, 0, 0, None))
        print("| %s | %d | %d | %d | %s | %d |"
              % (name, t, u, dp, ("%.1f%%" % ag) if ag is not None else "-",
                 len(set(d) ^ qref)))
    missing = [v for v in VARIANTS if v not in data]
    incomplete = {v: len(d) for v, d in data.items() if len(d) != 140}
    if missing:
        print("\nMISSING variant files (not run): %s" % ", ".join(missing))
    if incomplete:
        print("INCOMPLETE variants (n != 140): %s" % incomplete)

    # direct 的检索集合(现场复算,仅用于锚覆盖率)
    dcov = None
    try:
        import os
        if os.environ.get("QVF_EMBED_BACKEND") == "openai":
            import b37_rag_variants as B
            B.load_entries()
            B.load_emb_cache()
            store = B.Store(entries, B._retriever_cls())
            rows = {}
            for q in qs:
                got, _ = B.retrieve("dense_top10", store, q)
                rows[q["qid"]] = {"question_id": q["qid"], "uid": q["uid"],
                                  "retrieved_memory_ids": [m.memory_id for m in got]}
            dcov = coverage(rows, anchors, today_of)
    except Exception as e:                                     # noqa: BLE001
        print("\n(direct anchor coverage NOT computed: %s: %s)"
              % (type(e).__name__, str(e)[:120]))

    print("\n## 1. Headline\n")
    print("| variant | n | acc % | Δ vs direct pp | McNemar p | anchor cov % | "
          "as-of anchor cov % | mean in tok | mean out tok | retr in/out tok | "
          "$/q | median latency s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")

    def line(name, d, cov3, extra_cost=(0.0, 0.0)):
        a = acc(d)
        keys = sorted(set(direct) & set(d))
        b = sum(1 for q in keys if direct[q]["judge_correct"]
                and not d[q]["judge_correct"])
        c = sum(1 for q in keys if not direct[q]["judge_correct"]
                and d[q]["judge_correct"])
        dl = (sum(bool(d[q]["judge_correct"]) for q in keys)
              - sum(bool(direct[q]["judge_correct"]) for q in keys)) / \
            max(1, len(keys)) * 100
        mi = st.mean([r.get("usage_input_tokens") or 0 for r in d.values()])
        mo = st.mean([r.get("usage_output_tokens") or 0 for r in d.values()])
        ri = st.mean([r.get("retrieval_input_tokens") or 0 for r in d.values()])
        ro = st.mean([r.get("retrieval_output_tokens") or 0 for r in d.values()])
        lat = st.median([r.get("latency_s") or 0 for r in d.values()])
        cost = (mi + ri) / 1e6 * P_IN + (mo + ro) / 1e6 * P_OUT
        cv = ("%.1f" % cov3[0]) if cov3 and cov3[0] is not None else "-"
        cva = ("%.1f" % cov3[1]) if cov3 and cov3[1] is not None else "-"
        pv = sign_p(b, c) if name != "direct (reference)" else 1.0
        print("| %s | %d | %.2f | %s | %s | %s | %s | %.0f | %.0f | %.0f/%.0f | "
              "$%.4f | %.2f |"
              % (name, len(d), a,
                 "—" if name.startswith("direct") else "%+.2f" % dl,
                 "—" if name.startswith("direct") else "%.4g" % pv,
                 cv, cva, mi, mo, ri, ro, cost, lat))
        return a, dl, cost

    line("direct (reference)", direct, dcov)
    line("smoc_v45 (QVF)", smoc, None)
    for v in VARIANTS:
        if v in data:
            line(v, data[v], coverage(data[v], anchors, today_of))

    print("\n## 2. Accuracy by question type (%)\n")
    print("| variant | " + " | ".join(TYPES) + " |")
    print("|---|" + "---|" * len(TYPES))
    for name, d in [("direct", direct), ("smoc_v45", smoc)] + \
            [(v, data[v]) for v in VARIANTS if v in data]:
        cells = []
        for t in TYPES:
            x = by_type(d, t)
            cells.append("-" if x is None else "%.1f" % x)
        print("| %s | %s |" % (name, " | ".join(cells)))

    print("\n## 3. Paired vs direct top-10 (b33A)\n")
    for v in VARIANTS:
        if v in data:
            compare("%s vs direct" % v, direct, data[v])

    print("\n## 4. Paired vs smoc_v45 (QVF)\n")
    best = max((v for v in data), key=lambda v: acc(data[v]), default=None)
    if best:
        print("Strongest variant by accuracy: **%s** (%.2f%%)\n"
              % (best, acc(data[best])))
        compare("%s vs smoc_v45" % best, smoc, data[best])
    for v in VARIANTS:
        if v in data and v != best:
            compare("%s vs smoc_v45" % v, smoc, data[v], boot=False)
    compare("direct vs smoc_v45", smoc, direct, boot=False)

    print("\n## 5. Cost ledger (measured tokens, this batch only)\n")
    print("| variant | reader in | reader out | retrieval in | retrieval out | "
          "haiku $ | judge in | judge out | judge $ (opus-5) |")
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

    print("\n## 6. Retrieval-set diagnostics\n")
    print("| variant | mean memories rendered | mean anchors hit / question | "
          "questions with 0 anchors hit |")
    print("|---|---|---|")
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
        print("| %s | %.1f | %.2f | %d |"
              % (v, st.mean(ks), st.mean(hits), zero))
    return 0


if __name__ == "__main__":
    sys.exit(main())
