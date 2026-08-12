"""Full analysis of the decisive STALE experiment with error decomposition.

For each prompted-condition failure, attribute it to one of:
- retrieval_miss:    the new-state session's rounds never reached top-k
- adjudication_miss: new-state round retrieved, but engine did not block any
                     stale record (extraction failed to produce the replacement)
- reader_miss:       engine blocked stale evidence correctly, reader still wrong
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS = sys.argv[1] if len(sys.argv) > 1 else "results/decisive_stale_qwen3-4b.jsonl"
DATA = "data/stale_T1_T2_400_FULL.json"

recs = [json.loads(l) for l in open(RESULTS, encoding="utf-8")]
items = {it["uid"]: it for it in json.loads(Path(DATA).read_text(encoding="utf-8"))}


def uid_of(question_id: str) -> str:
    return question_id.split("_dim")[0]


# ---------------- overall aggregates ----------------
print("=== overall by mode ===")
agg = defaultdict(lambda: {"n": 0, "c": 0, "fb": 0})
for r in recs:
    if "error" in r:
        continue
    a = agg[r["mode"]]
    a["n"] += 1
    a["c"] += 1 if r.get("judge_correct") else 0
    a["fb"] += 1 if r.get("fallback_used") else 0
for m in sorted(agg):
    a = agg[m]
    print(f"{m:9s} n={a['n']:>3} acc={a['c'] / max(a['n'], 1):.3f} fallback={a['fb']}")

print("\n=== by mode x dim ===")
agg2 = defaultdict(lambda: [0, 0])
for r in recs:
    if "error" in r:
        continue
    k = (r["mode"], r["question_type"])
    agg2[k][0] += 1
    agg2[k][1] += 1 if r.get("judge_correct") else 0
for k in sorted(agg2):
    n, c = agg2[k]
    print(f"{k[0]:9s} {k[1]:12s} {c:>2}/{n:<3} = {c / max(n, 1):.3f}")

# ---------------- retrieval hit analysis ----------------
def session_retrieved(r: dict, s_idx) -> bool:
    if s_idx is None:
        return False
    ids = r.get("retrieved_memory_ids") or []
    return any(f"/s{s_idx}#" in mid for mid in ids)


print("\n=== prompted condition: error decomposition ===")
decomp = defaultdict(int)
examples = defaultdict(list)
for r in recs:
    if r.get("mode") != "prompted" or "error" in r:
        continue
    uid = uid_of(r["question_id"])
    item = items.get(uid)
    if item is None:
        continue
    old_idx, new_idx = (item.get("relevant_session_index") or [None, None])[:2]
    new_hit = session_retrieved(r, new_idx)
    old_hit = session_retrieved(r, old_idx)
    blocked = bool((r.get("engine_decision") or {}).get("blocked_as_current_ids"))
    correct = bool(r.get("judge_correct"))

    if correct:
        cls = "correct"
    elif not new_hit:
        cls = "retrieval_miss(new-state round not in top-k)"
    elif not blocked:
        cls = "adjudication_miss(new retrieved, nothing blocked)"
    else:
        cls = "reader_miss(blocked correctly, answer still wrong)"
    decomp[cls] += 1
    if len(examples[cls]) < 2:
        examples[cls].append((r["question_id"], old_hit, new_hit, blocked))

total_p = sum(decomp.values())
for cls in sorted(decomp, key=decomp.get, reverse=True):
    print(f"{cls:55s} {decomp[cls]:>3}/{total_p}  ({decomp[cls] / max(total_p, 1):.1%})")

print("\n=== direct condition: retrieval hits vs accuracy ===")
d = defaultdict(lambda: [0, 0])
for r in recs:
    if r.get("mode") != "direct" or "error" in r:
        continue
    uid = uid_of(r["question_id"])
    item = items.get(uid)
    if item is None:
        continue
    new_idx = (item.get("relevant_session_index") or [None, None])[1]
    key = "new_retrieved" if session_retrieved(r, new_idx) else "new_missed"
    d[key][0] += 1
    d[key][1] += 1 if r.get("judge_correct") else 0
for k, (n, c) in sorted(d.items()):
    print(f"{k:15s} n={n:>3} acc={c / max(n, 1):.3f}")

# same for prompted, conditional accuracy when new retrieved
print("\n=== prompted vs direct, on the subset where new-state round WAS retrieved ===")
sub = defaultdict(lambda: [0, 0])
for r in recs:
    if r.get("mode") not in ("prompted", "direct") or "error" in r:
        continue
    uid = uid_of(r["question_id"])
    item = items.get(uid)
    if item is None:
        continue
    new_idx = (item.get("relevant_session_index") or [None, None])[1]
    if session_retrieved(r, new_idx):
        sub[r["mode"]][0] += 1
        sub[r["mode"]][1] += 1 if r.get("judge_correct") else 0
for m, (n, c) in sorted(sub.items()):
    print(f"{m:9s} n={n:>3} acc={c / max(n, 1):.3f}")

# ---------------- engine stats & cost ----------------
print("\n=== engine + cost ===")
for mode in ("prompted", "oracle"):
    ms = [r for r in recs if r.get("mode") == mode and "error" not in r]
    acc_rec = sum(r.get("engine_accepted", 0) for r in ms)
    rej = sum(r.get("engine_rejected", 0) for r in ms)
    print(f"{mode}: accepted_records={acc_rec} rejected={rej} "
          f"rejection_rate={rej / max(acc_rec + rej, 1):.1%}")
ti = sum(r.get("usage_input_tokens", 0) for r in recs)
to = sum(r.get("usage_output_tokens", 0) for r in recs)
print(f"API tokens: in={ti} out={to}  approx cost=${ti / 1e6 * 5 + to / 1e6 * 25:.2f} (opus rates, judge excluded)")
