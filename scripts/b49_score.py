# -*- coding: utf-8 -*-
"""批 49 评分(零 API):最新配置是否只对 WikiState 特调。
  --part arenas : STALE / MemOps(b19 新鲜 120 题)旧 smoc / direct 对 lane4 / general 新店,判官口径 arena_judge_pass(haiku,与批 19 同)
  --part sonnet : v51f@sonnet-5(140 题)对 v47skf@sonnet、v45@sonnet(36b)、全上下文(36b)
  --part long   : 104K 30 店 120 题:v51Lf 全账目/投影 × haiku/sonnet 对批 33-D/39/40 文件
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")


def load(path, key="judge_correct", idkey=("question_id", "qid")):
    """path 可含通配符(分片文件合并读取)。"""
    import glob
    d = {}; tin = []; tout = []
    files = sorted(glob.glob(str(ROOT / path))) if any(c in path for c in "*?[") else ([str(ROOT / path)] if (ROOT / path).exists() else [])
    if not files:
        return None, 0, 0
    lines = [l for f in files for l in open(f, encoding="utf-8")]
    for l in lines:
        if not l.strip():
            continue
        r = json.loads(l); qid = next((r[k] for k in idkey if k in r), None)
        d[qid] = bool(r.get(key)); tin.append(r.get("usage_input_tokens", r.get("reader_in", 0)) or 0); tout.append(r.get("usage_output_tokens", r.get("reader_out", 0)) or 0)
    return d, (st.mean(tin) if tin else 0), (st.mean(tout) if tout else 0)


def acc(d):
    return 100 * sum(d.values()) / len(d)


def mcnemar(a, b):
    keys = sorted(set(a) & set(b))
    ao = sum(1 for k in keys if a[k] and not b[k]); bo = sum(1 for k in keys if b[k] and not a[k]); n = ao + bo
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(ao, bo) + 1)) / 2 ** n)
    return len(keys), ao, bo, p


def line(name, d, ti, to):
    print(f"  {name:48s} n={len(d):3d} acc={acc(d):5.1f} in/q={ti:6.0f} out/q={to:5.0f}")


def compare(x, dx, y, dy):
    n, ao, bo, p = mcnemar(dx, dy)
    print(f"  {x} vs {y}: n={n} delta={100*(ao-bo)/n:+.1f}pp A-only={ao} B-only={bo} McNemar p={p:.3g}")


def part_arenas():
    for arena, old_smoc, old_direct in (("stale", "results/ext_stale_smoc_b19.rejudged.jsonl", "results/ext_stale_direct_b19.rejudged.jsonl"),
                                        ("memops", "results/ext_memops_smoc_b19.rejudged.jsonl", "results/ext_memops_direct_b19.rejudged.jsonl")):
        print(f"== {arena} (b19 fresh 120 q; judge = arena_judge_pass, haiku) ==")
        runs = {"direct (b19)": old_direct, "smoc old cards (b19)": old_smoc,
                "smoc v51 lane4": f"results/b49_ext_{arena}_smoc_v51_lane4.rejudged.jsonl",
                "smoc v51 general": f"results/b49_ext_{arena}_smoc_v51_general.rejudged.jsonl",
                "smoc v52 no-Stage1 (haiku extractor, 20 stores)": f"results/b49_ext_{arena}_smoc_v52nostage.rejudged.jsonl"}
        D = {}
        for name, p in runs.items():
            d, ti, to = load(p, key="arena_judge_pass")
            if d is None:
                print(f"  {name}: absent ({p})"); continue
            D[name] = d; line(name, d, ti, to)
            # by dimension
            byd = defaultdict(list)
            for k, v in d.items():
                byd[k.rsplit("-", 1)[-1] if "-" in k else "?"].append(v)
            print("      " + " | ".join(f"{dim} {100*sum(v)/len(v):.0f}" for dim, v in sorted(byd.items())))
        for x in ("smoc v51 lane4", "smoc v51 general", "smoc v52 no-Stage1 (haiku extractor, 20 stores)"):
            if x in D:
                for y in ("smoc old cards (b19)", "direct (b19)"):
                    compare(x, D[x], y, D[y])
                if x.startswith("smoc v52") :
                    sub = set(D[x])
                    for y in ("smoc old cards (b19)", "direct (b19)", "smoc v51 lane4", "smoc v51 general"):
                        if y in D:
                            dy = {k: v for k, v in D[y].items() if k in sub}
                            print(f"    [same 20 stores] {y}: acc={acc(dy):.1f} (n={len(dy)})")


def part_sonnet():
    print("== WikiState 140 q / 36 chains, reader claude-sonnet-5 ==")
    runs = {"v52f (SLIM+KEYS, batch 49)": "results/b49_smoc_v52f_sonnet5.jsonl",
            "v51f (batch 48 config, no KEYS)": "results/b48_smoc_v51f_sonnet5.jsonl",
            "v47skf (batch 38e)": "results/b38e_smoc_v47skf_sonnet-5.jsonl",
            "v45 (batch 36b)": "results/b36b_smoc_sonnet5.jsonl",
            "full context plain (36b)": "results/b36b_fullplain_sonnet5.jsonl",
            "direct (36b)": "results/b36b_direct_sonnet5.jsonl"}
    D = {}
    for name, p in runs.items():
        d, ti, to = load(p)
        if d is None:
            print(f"  {name}: absent"); continue
        D[name] = d; line(name, d, ti, to)
    for y in ("v47skf (batch 38e)", "v45 (batch 36b)", "full context plain (36b)"):
        if "v52f (SLIM+KEYS, batch 49)" in D and y in D:
            compare("v52f", D["v52f (SLIM+KEYS, batch 49)"], y, D[y])


def part_long():
    print("== 104K: 30 stores / 120 q ==")
    runs = {
        "haiku ledger v51Lf": "results/b49_ledger_L2_v51Lf_haiku.jsonl",
        "haiku projection v51Lf": "results/b49_slot_L2_v51Lf_haiku.jsonl",
        "sonnet ledger v51Lf": "results/b49_ledger_L2_v51Lf_sonnet5.jsonl",
        "sonnet projection v51Lf": "results/b49_slot_L2_v51Lf_sonnet5.jsonl",
        "sonnet ledger old (b40)": "results/b40_ledger_L2_sonnet5.jsonl",
        "sonnet projection old (b40)": "results/b40_slot_L2_sonnet5.jsonl",
        "sonnet full context (b40/46a)": "results/b40_plainctx_L2_sonnet5.jsonl",
        "sonnet top-100 (b40)": "results/b40_top100_L2_sonnet5.jsonl",
        "haiku ledger old (33-D)": "results/b33d_smoc_L2_*_s[0-9].jsonl",
        "haiku projection old (33-D)": "results/b33d_slot_L2_*_s[0-9].jsonl",
        "haiku direct (b39)": "results/b39_direct_L2.jsonl",
        "haiku top-100 (b39)": "results/b39_dense_top100_L2.jsonl",
    }
    D = {}
    for name, p in runs.items():
        d, ti, to = load(p)
        if d is None:
            print(f"  {name}: absent ({p})"); continue
        D[name] = d; line(name, d, ti, to)
    for x, y in (("haiku ledger v51Lf", "haiku ledger old (33-D)"), ("haiku projection v51Lf", "haiku projection old (33-D)"),
                 ("haiku ledger v51Lf", "haiku top-100 (b39)"), ("sonnet ledger v51Lf", "sonnet ledger old (b40)"),
                 ("sonnet projection v51Lf", "sonnet projection old (b40)"), ("sonnet ledger v51Lf", "sonnet full context (b40/46a)")):
        if x in D and y in D:
            compare(x, D[x], y, D[y])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--part", choices=["arenas", "sonnet", "long"], required=True)
    a = ap.parse_args(); {"arenas": part_arenas, "sonnet": part_sonnet, "long": part_long}[a.part]()
