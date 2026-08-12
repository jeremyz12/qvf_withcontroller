"""Free retrieval-layer micro-benchmark: BM25 vs dense on STALE.

Measures, per (item, dim) query: does top-k contain the new-state session's
rounds? Also measures the dense repair-query hit rate. No LLM calls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.stale_dataset import load_stale
from qvf.retrieval import BM25Retriever, OllamaDenseRetriever

TOP_K = 10
instances = load_stale("data/stale_T1_T2_400_FULL.json", limit_items=35)


def hit(memories, s_idx):
    return any(f"/s{s_idx}#" in m.memory_id for m in memories)


stats = {"bm25": 0, "dense": 0, "dense_repair": 0, "either_dense": 0, "n": 0}
repair_q = (
    "The user's situation recently changed: they moved, switched, updated, "
    "quit, started, or got something new. What is the user's current state now?"
)
for inst in instances:
    new_idx = inst.extra.get("new_session_index")
    if new_idx is None:
        continue
    stats["n"] += 1
    bm = BM25Retriever(inst.memories).retrieve(inst.question, top_k=TOP_K)
    dn_r = OllamaDenseRetriever(inst.memories)
    dn = dn_r.retrieve(inst.question, top_k=TOP_K)
    dr = dn_r.retrieve(repair_q, top_k=TOP_K)
    b, d, r = hit(bm, new_idx), hit(dn, new_idx), hit(dr, new_idx)
    stats["bm25"] += b
    stats["dense"] += d
    stats["dense_repair"] += r
    stats["either_dense"] += d or r

n = stats["n"]
print(f"queries: {n}")
print(f"BM25 first-pass new-state hit:          {stats['bm25']}/{n} = {stats['bm25']/n:.1%}")
print(f"Dense first-pass new-state hit:         {stats['dense']}/{n} = {stats['dense']/n:.1%}")
print(f"Dense generic repair-query hit:         {stats['dense_repair']}/{n} = {stats['dense_repair']/n:.1%}")
print(f"Dense first-pass OR repair hit:         {stats['either_dense']}/{n} = {stats['either_dense']/n:.1%}")
