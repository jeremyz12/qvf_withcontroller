"""Analyze a results JSONL: abstention split, per-type accuracy, error cases, cost."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

path = sys.argv[1] if len(sys.argv) > 1 else "results/stratified_s_5pt.jsonl"
recs = [json.loads(l) for l in open(path, encoding="utf-8")]
modes = sorted({r["mode"] for r in recs})

print("=== abstention split ===")
for mode in modes:
    abst = [r for r in recs if r["mode"] == mode and r["is_abstention"]]
    ok = sum(1 for r in abst if r.get("judge_correct"))
    print(f"{mode}: abstention {ok}/{len(abst)}")

print("\n=== non-abstention by type ===")
agg = defaultdict(lambda: [0, 0])
for r in recs:
    if not r["is_abstention"]:
        k = (r["mode"], str(r["question_type"]))
        agg[k][0] += 1
        agg[k][1] += 1 if r.get("judge_correct") else 0
for k in sorted(agg):
    n, c = agg[k]
    print(f"{k[0]:9s} {k[1]:30s} {c}/{n}")

print("\n=== cost ===")
for mode in modes:
    ms = [r for r in recs if r["mode"] == mode]
    ti = sum(r.get("usage_input_tokens", 0) for r in ms)
    to = sum(r.get("usage_output_tokens", 0) for r in ms)
    cost = ti / 1e6 * 5 + to / 1e6 * 25
    lats = sorted(r.get("latency_s", 0) for r in ms)
    print(
        f"{mode:9s} in={ti:9d} out={to:8d} cost=${cost:.2f} "
        f"(${cost / max(len(ms), 1):.3f}/q) lat_med={lats[len(lats) // 2]:.0f}s"
    )

print("\n=== QVF errors (with baseline comparison) ===")
by_id = defaultdict(dict)
for r in recs:
    by_id[r["question_id"]][r["mode"]] = r
for qid, d in by_id.items():
    q = d.get("qvf")
    if q is None or q.get("judge_correct"):
        continue
    b = d.get("baseline", {})
    tag = str(q["question_type"]) + ("/ABS" if q["is_abstention"] else "")
    print(f"[{tag}] {q['question'][:70]}")
    print(f"  gold: {str(q['gold_answer'])[:80]}")
    print(f"  qvf : {q['answer'][:130]}")
    print(f"  base: {b.get('answer', '')[:130]} (correct={b.get('judge_correct')})")
    vm = q.get("validity_map", {})
    print(f"  suff: {vm.get('sufficiency')} risks: {vm.get('risk_flags')}")
    print(f"  judge: {q.get('judge_reason', '')[:110]}")
    print()

print("=== baseline errors QVF fixed ===")
for qid, d in by_id.items():
    q, b = d.get("qvf"), d.get("baseline")
    if q is None or b is None:
        continue
    if q.get("judge_correct") and not b.get("judge_correct"):
        tag = str(q["question_type"]) + ("/ABS" if q["is_abstention"] else "")
        print(f"[{tag}] {q['question'][:70]}")
        print(f"  gold: {str(q['gold_answer'])[:80]}")
        print(f"  base: {b['answer'][:130]}")
        print(f"  qvf : {q['answer'][:130]}")
        print()
