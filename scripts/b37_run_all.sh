#!/usr/bin/env bash
# 批 37:检索侧 RAG 基线家族,逐臂**顺序**跑(一臂失败不挡其余),每臂 4 线程。
# 用法: bash scripts/b37_run_all.sh 2>&1 | tee results/b37_run.log
cd "$(dirname "$0")/.." || exit 1
export QVF_EMBED_BACKEND=openai
export PYTHONUTF8=1
for v in dense_top30 dense_top50 session_top5 hybrid_rrf mmr recency asof_filter rewrite rerank; do
  echo "=== BEGIN $v $(date -Is) ==="
  python -u scripts/b37_rag_variants.py --variant "$v" --workers 4 \
      --out "results/b37_${v}.jsonl" 2>&1 | tail -40
  echo "=== END $v rc=$? $(date -Is) ==="
done
echo "ALL VARIANTS FINISHED $(date -Is)"
