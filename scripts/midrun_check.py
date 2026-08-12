"""Quick mid-run health check for decisive experiment results."""
import json
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "results/decisive_stale_qwen3-4b.jsonl"
recs = [json.loads(l) for l in open(path, encoding="utf-8")]
agg = defaultdict(lambda: {"n": 0, "c": 0, "fb": 0, "rej": 0, "acc": 0})
for r in recs:
    if "error" in r:
        continue
    a = agg[r["mode"]]
    a["n"] += 1
    a["c"] += 1 if r.get("judge_correct") else 0
    a["fb"] += 1 if r.get("fallback_used") else 0
    a["rej"] += r.get("engine_rejected", 0)
    a["acc"] += r.get("engine_accepted", 0)
for m in sorted(agg):
    a = agg[m]
    print(
        f"{m:9s} n={a['n']:>3} acc={a['c'] / max(a['n'], 1):.3f} "
        f"fallback={a['fb']} engine_rec_accepted={a['acc']} rejected={a['rej']}"
    )
print("errors:", sum(1 for r in recs if "error" in r))
