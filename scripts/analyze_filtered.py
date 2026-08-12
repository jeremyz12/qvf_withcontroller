"""Why did the context-surgery (filtered) condition not improve?

Decompose filtered rows on the subset where the new-state round WAS retrieved:
did the surgery keep the new round, keep only the old round, or keep nothing?
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = "results/decisive_stale_qwen3-4b.jsonl"
DATA = "data/stale_T1_T2_400_FULL.json"

recs = [json.loads(l) for l in open(RESULTS, encoding="utf-8")]
items = {it["uid"]: it for it in json.loads(Path(DATA).read_text(encoding="utf-8"))}


def uid_of(qid):
    return qid.split("_dim")[0]


def hit(ids, s_idx):
    return s_idx is not None and any(f"/s{s_idx}#" in m for m in ids or [])


rows = [r for r in recs if r.get("mode") == "filtered" and "error" not in r]
print(f"filtered rows: {len(rows)}")

decomp = defaultdict(lambda: [0, 0])  # class -> [n, correct]
strat = defaultdict(lambda: [0, 0])
for r in rows:
    item = items.get(uid_of(r["question_id"]))
    if not item:
        continue
    old_idx, new_idx = (item.get("relevant_session_index") or [None, None])[:2]
    retrieved_new = hit(r.get("retrieved_memory_ids"), new_idx)
    kept = r.get("filtered_memory_ids") or []
    kept_new = hit(kept, new_idx)
    kept_old = hit(kept, old_idx)
    correct = bool(r.get("judge_correct"))

    s = r.get("filter_strategy") or "?"
    strat[s][0] += 1
    strat[s][1] += 1 if correct else 0

    if not retrieved_new:
        cls = "new_not_retrieved"
    elif kept_new and not kept_old:
        cls = "surgery_kept_new_only(ideal)"
    elif kept_new and kept_old:
        cls = "surgery_kept_both"
    elif kept_old and not kept_new:
        cls = "surgery_kept_OLD_only(bad)"
    else:
        cls = "surgery_kept_neither"
    decomp[cls][0] += 1
    decomp[cls][1] += 1 if correct else 0

print("\n=== surgery outcome on filtered rows ===")
for cls in sorted(decomp, key=lambda k: -decomp[k][0]):
    n, c = decomp[cls]
    print(f"{cls:32s} n={n:>3} acc={c / max(n, 1):.3f}")

print("\n=== by filter strategy ===")
for s in sorted(strat, key=lambda k: -strat[k][0]):
    n, c = strat[s]
    print(f"{s:22s} n={n:>3} acc={c / max(n, 1):.3f}")

# sample wrong answers in the ideal class
print("\n=== samples: kept_new_only but WRONG (reader still failed on clean context) ===")
shown = 0
for r in rows:
    if shown >= 3:
        break
    item = items.get(uid_of(r["question_id"]))
    if not item:
        continue
    old_idx, new_idx = (item.get("relevant_session_index") or [None, None])[:2]
    kept = r.get("filtered_memory_ids") or []
    if hit(kept, new_idx) and not hit(kept, old_idx) and not r.get("judge_correct"):
        print(f"[{r['question_type']}] {r['question'][:70]}")
        print(f"  kept: {kept}")
        print(f"  answer: {str(r.get('answer'))[:180]}")
        print(f"  judge: {str(r.get('judge_reason'))[:120]}")
        print()
        shown += 1
