"""Final analysis with repair-specific decomposition.

Usage: python scripts/analyze_repaired.py [mode]   (default: repaired)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

MODE = sys.argv[1] if len(sys.argv) > 1 else "repaired"
RESULTS = "results/decisive_stale_qwen3-4b.jsonl"
DATA = "data/stale_T1_T2_400_FULL.json"

recs = [json.loads(l) for l in open(RESULTS, encoding="utf-8")]
items = {it["uid"]: it for it in json.loads(Path(DATA).read_text(encoding="utf-8"))}


def uid_of(qid):
    return qid.split("_dim")[0]


def hit(ids, s_idx):
    return s_idx is not None and any(f"/s{s_idx}#" in m for m in ids or [])


print("=== FIVE-CONDITION FINAL ===")
agg = defaultdict(lambda: [0, 0])
by_dim = defaultdict(lambda: [0, 0])
for r in recs:
    if "error" in r:
        continue
    agg[r["mode"]][0] += 1
    agg[r["mode"]][1] += 1 if r.get("judge_correct") else 0
    k = (r["mode"], r["question_type"])
    by_dim[k][0] += 1
    by_dim[k][1] += 1 if r.get("judge_correct") else 0
for m in ("direct", "prompted", "filtered", "repaired", "repaired_dense", "oracle"):
    if m in agg:
        n, c = agg[m]
        print(f"{m:9s} n={n:>3} acc={c / max(n, 1):.3f}")
print()
for k in sorted(by_dim):
    n, c = by_dim[k]
    print(f"{k[0]:9s} {k[1]:12s} {c:>2}/{n:<3} = {c / max(n, 1):.3f}")

# ---- repaired decomposition ----
rows = [r for r in recs if r.get("mode") == MODE and "error" not in r]
print(f"\n=== {MODE}: retrieval repair effectiveness (n={len(rows)}) ===")
stats = defaultdict(lambda: [0, 0])
for r in rows:
    item = items.get(uid_of(r["question_id"]))
    if not item:
        continue
    old_idx, new_idx = (item.get("relevant_session_index") or [None, None])[:2]
    # first-pass = retrieved ids minus repair-added
    added = r.get("repair_added_ids") or []
    all_ids = r.get("retrieved_memory_ids") or []
    first_pass = [m for m in all_ids if m not in set(added)]
    fp_new = hit(first_pass, new_idx)
    triggered = bool(r.get("repair_triggered"))
    added_new = hit(added, new_idx)
    correct = bool(r.get("judge_correct"))

    if fp_new:
        cls = "first_pass_had_new"
    elif not triggered:
        cls = "MISSED_no_trigger(new absent, repair not fired)"
    elif added_new:
        cls = "repair_RECOVERED_new"
    else:
        cls = "repair_fired_but_new_still_missed"
    stats[cls][0] += 1
    stats[cls][1] += 1 if correct else 0
for cls in sorted(stats, key=lambda k: -stats[k][0]):
    n, c = stats[cls]
    print(f"{cls:46s} n={n:>3} acc={c / max(n, 1):.3f}")

trig = sum(1 for r in rows if r.get("repair_triggered"))
print(f"\nrepair trigger rate: {trig}/{len(rows)}")

# surgery outcome
print(f"\n=== {MODE}: surgery outcome ===")
surg = defaultdict(lambda: [0, 0])
for r in rows:
    item = items.get(uid_of(r["question_id"]))
    if not item:
        continue
    old_idx, new_idx = (item.get("relevant_session_index") or [None, None])[:2]
    kept = r.get("filtered_memory_ids") or []
    retrieved_new = hit(r.get("retrieved_memory_ids"), new_idx)
    if not retrieved_new:
        cls = "new_not_in_context"
    elif hit(kept, new_idx) and not hit(kept, old_idx):
        cls = "kept_new_only(ideal)"
    elif hit(kept, new_idx):
        cls = "kept_both"
    elif hit(kept, old_idx):
        cls = "kept_OLD_only(bad)"
    else:
        cls = "kept_neither"
    surg[cls][0] += 1
    surg[cls][1] += 1 if r.get("judge_correct") else 0
for cls in sorted(surg, key=lambda k: -surg[k][0]):
    n, c = surg[cls]
    print(f"{cls:26s} n={n:>3} acc={c / max(n, 1):.3f}")

# cost
ti = sum(r.get("usage_input_tokens", 0) for r in rows)
to = sum(r.get("usage_output_tokens", 0) for r in rows)
print(f"\n{MODE} API cost: in={ti} out={to} ~${ti / 1e6 * 5 + to / 1e6 * 25:.2f}")
