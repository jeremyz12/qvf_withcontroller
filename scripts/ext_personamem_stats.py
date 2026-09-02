# -*- coding: utf-8 -*-
"""批 33-G1 PersonaMem-v2 外场统计:smoc vs direct 配对分析 + 成本/延迟。

统计口径与 scripts/bootstrap_ci.py **同源**(直接 import 其 sign_test_p /
cluster_sign_counts,不复制实现):
  - 配对 McNemar = 判别对上的精确二项双侧检验(= 该文件的 sign_test_p);
  - 簇 = persona(uid),簇级自助 95% CI 按整簇有放回重采样;
  - 另报簇级符号检验(每 persona 一票)。

成本按实测 usage token 折牌价:haiku-4.5 $1/$5 per M(读者/建卡),
opus-5 $5/$25 per M(ClaudeJudge),OpenAI text-embedding-3-small $0.02/M。

用法:
  python scripts/ext_personamem_stats.py \
      --smoc "results/ext_personamem_smoc_s*.jsonl" \
      --direct "results/ext_personamem_direct_s*.jsonl" \
      --probe data/external/personamem/personamem_probe.jsonl \
      --cards-dir results/ext_cards_personamem
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import random
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
_argv = sys.argv
sys.argv = [_argv[0]]              # bootstrap_ci 模块级读 argv[1] 当 N_BOOT
from bootstrap_ci import cluster_sign_counts, sign_test_p  # noqa: E402
sys.argv = _argv

N_BOOT = 10000
SEED = 20260902
P_HAIKU_IN, P_HAIKU_OUT = 1.0, 5.0     # $/M tok
P_OPUS_IN, P_OPUS_OUT = 5.0, 25.0
P_EMBED = 0.02


def load(pattern: str) -> dict:
    rows = {}
    for f in sorted(glob.glob(pattern)):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows[r["question_id"]] = r
    return rows


def boot_ci(clusters: dict, n: int, rng: random.Random):
    ckeys = list(clusters)
    deltas = []
    for _ in range(N_BOOT):
        sample = [clusters[rng.choice(ckeys)] for _ in ckeys]
        m = sum(len(c) for c in sample)
        if m == 0:
            continue
        deltas.append((sum(a for c in sample for a, _ in c)
                       - sum(b for c in sample for _, b in c)) / m)
    deltas.sort()
    return deltas[int(0.025 * len(deltas))], deltas[int(0.975 * len(deltas))]


def analyse(name, items, uid_of, rng):
    n = len(items)
    if not n:
        return None
    a_ok = sum(a for a, _ in items.values())
    b_ok = sum(b for _, b in items.values())
    w = sum(1 for a, b in items.values() if a and not b)
    l = sum(1 for a, b in items.values() if b and not a)
    clusters = defaultdict(list)
    for q, pair in items.items():
        clusters[uid_of[q]].append(pair)
    cw, cl, ct = cluster_sign_counts(clusters)
    lo, hi = boot_ci(clusters, n, rng)
    return dict(name=name, n=n, clusters=len(clusters),
                smoc=a_ok / n * 100, direct=b_ok / n * 100,
                delta=(a_ok - b_ok) / n * 100, b=w, c=l,
                p=sign_test_p(w, l), cw=cw, cl=cl, ct=ct,
                cluster_p=sign_test_p(cw, cl), ci_lo=lo * 100, ci_hi=hi * 100)


_LET = re.compile(r"\b([ABCD])\b")


def letter_of(ans: str):
    m = _LET.search((ans or "").strip()[:120])
    return m.group(1) if m else None


def arm_cost(rows: dict):
    ti = sum(r.get("usage_input_tokens") or 0 for r in rows.values())
    to = sum(r.get("usage_output_tokens") or 0 for r in rows.values())
    ji = sum(r.get("judge_input_tokens") or 0 for r in rows.values())
    jo = sum(r.get("judge_output_tokens") or 0 for r in rows.values())
    reader = (ti * P_HAIKU_IN + to * P_HAIKU_OUT) / 1e6
    judge = (ji * P_OPUS_IN + jo * P_OPUS_OUT) / 1e6
    lat = [r.get("latency_s") or 0 for r in rows.values()]
    return dict(n=len(rows), tin=ti, tout=to, jin=ji, jout=jo,
                reader_usd=reader, judge_usd=judge,
                lat_mean=st.mean(lat) if lat else 0,
                lat_median=st.median(lat) if lat else 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoc", required=True)
    ap.add_argument("--direct", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--cards-dir", default="results/ext_cards_personamem")
    ap.add_argument("--unified", default="data/external/personamem/personamem_unified.json")
    a = ap.parse_args()
    rng = random.Random(SEED)

    probe = {}
    for line in open(a.probe, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            probe[r["qid"]] = r
    S, D = load(a.smoc), load(a.direct)
    common = sorted(set(S) & set(D) & set(probe))
    print(f"paired questions: {len(common)} (smoc {len(S)}, direct {len(D)}, "
          f"probe {len(probe)})")
    items = {q: (int(bool(S[q].get("judge_correct"))),
                 int(bool(D[q].get("judge_correct")))) for q in common}
    uid_of = {q: probe[q]["uid"] for q in common}

    rows = [analyse("ALL", items, uid_of, rng)]
    for s in ("ask_to_forget", "who_other", "self_standard"):
        sub = {q: v for q, v in items.items() if probe[q]["qtype"] == s}
        r = analyse(s, sub, uid_of, rng)
        if r:
            rows.append(r)
    print()
    print(f"{'stratum':16s} {'n':>4s} {'clu':>4s} {'smoc':>6s} {'direct':>7s} "
          f"{'delta':>7s} {'b/c':>9s} {'McNemar p':>10s} "
          f"{'cluster 95% CI':>20s} {'cluWLT':>10s} {'clu p':>8s}")
    for r in rows:
        print(f"{r['name']:16s} {r['n']:>4d} {r['clusters']:>4d} "
              f"{r['smoc']:>6.1f} {r['direct']:>7.1f} {r['delta']:>+7.1f} "
              f"{r['b']:>4d}/{r['c']:<4d} {r['p']:>10.4g} "
              f"[{r['ci_lo']:>+6.1f},{r['ci_hi']:>+6.1f}]     "
              f"{r['cw']}/{r['cl']}/{r['ct']:<4d} {r['cluster_p']:>8.4g}")

    # ── 判据 G ────────────────────────────────────────────
    A = rows[0]
    verdict = "PASS" if (A["delta"] > 0 and A["ci_lo"] > 0) else "FAIL"
    print(f"\nCriterion G (smoc - direct > 0 AND cluster CI excludes 0): "
          f"{verdict}  (delta={A['delta']:+.1f}pp, CI=[{A['ci_lo']:+.1f},"
          f"{A['ci_hi']:+.1f}])")

    # ── 成本 / 延迟 ───────────────────────────────────────
    cs, cd = arm_cost({q: S[q] for q in common}), arm_cost({q: D[q] for q in common})
    cards = sorted(Path(a.cards_dir).glob("*.json"))
    bin_ = bout = ncards = 0
    for f in cards:
        d = json.loads(f.read_text(encoding="utf-8"))
        bin_ += d.get("usage_in", 0)
        bout += d.get("usage_out", 0)
        ncards += len(d.get("records", []))
    build_usd = (bin_ * P_HAIKU_IN + bout * P_HAIKU_OUT) / 1e6
    # direct 臂嵌入成本:每店记忆流全量嵌入一次(题按 uid 复用检索器)
    uni = json.loads(Path(a.unified).read_text(encoding="utf-8"))
    chars = {e["uid"]: sum(len(t) for s in e["sessions"] for t in s["turns"])
             for e in uni}
    used = {probe[q]["uid"] for q in common}
    embed_tok = sum(chars[u] for u in used if u in chars) / 4.0
    embed_usd = embed_tok / 1e6 * P_EMBED

    print(f"\nBUILD (write phase, haiku-4.5): stores={len(cards)} "
          f"cards={ncards} in={bin_:,} out={bout:,} -> ${build_usd:.2f} "
          f"(${build_usd / max(1, len(cards)):.4f}/store, "
          f"${build_usd / max(1, len(common)):.4f}/question amortised)")
    print(f"EMBED (direct arm, text-embedding-3-small, est. tok=chars/4): "
          f"{embed_tok:,.0f} tok -> ${embed_usd:.3f}")
    for nm, c in (("smoc", cs), ("direct", cd)):
        rq = c["reader_usd"] / c["n"]
        jq = c["judge_usd"] / c["n"]
        print(f"{nm:7s} n={c['n']} reader tok in/out={c['tin']:,}/{c['tout']:,} "
              f"(${rq * 1000:.2f}/1k q reader) judge tok in/out="
              f"{c['jin']:,}/{c['jout']:,} | $/q reader={rq:.5f} "
              f"judge={jq:.5f} total={(rq + jq):.5f} | latency mean "
              f"{c['lat_mean']:.1f}s median {c['lat_median']:.1f}s")
    smoc_q = cs["reader_usd"] / cs["n"] + build_usd / len(common)
    dir_q = cd["reader_usd"] / cd["n"] + embed_usd / len(common)
    print(f"$/question incl. amortised write side: smoc={smoc_q:.5f} "
          f"direct={dir_q:.5f} (judge excluded, it is evaluation-only)")
    print(f"TOTAL measured spend this track (build+arms+judge): "
          f"${build_usd + embed_usd + cs['reader_usd'] + cs['judge_usd'] + cd['reader_usd'] + cd['judge_usd']:.2f}")

    # ── 附:协议偏差 + 字母一致性(零成本自查) ──────────
    dev = sum(1 for q in common if S[q].get("protocol_deviation"))
    agree_s = agree_d = miss_s = miss_d = 0
    for q in common:
        gl = probe[q]["meta"]["gold_letter"]
        ls, ld = letter_of(S[q].get("answer", "")), letter_of(D[q].get("answer", ""))
        if ls is None:
            miss_s += 1
        elif (ls == gl) == bool(S[q].get("judge_correct")):
            agree_s += 1
        if ld is None:
            miss_d += 1
        elif (ld == gl) == bool(D[q].get("judge_correct")):
            agree_d += 1
    print(f"\nsmoc protocol deviations (no ANSWER: line): {dev}/{len(common)}")
    print(f"judge vs deterministic letter-match agreement: "
          f"smoc {agree_s}/{len(common) - miss_s} (no letter parsed: {miss_s}); "
          f"direct {agree_d}/{len(common) - miss_d} (no letter parsed: {miss_d})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
