#!/usr/bin/env bash
# 批 33-D 规模轴 L2:三臂在 30 店 × 4 题 = 120 上的补跑(并行度 4)。
# 只跑"存档没有的行":smoc/slot 补 20 个新建店(80 题),haiku 全文补 15 个新店(60 题)。
# 用法: bash scripts/b33d_run_arms.sh <arm>   # arm ∈ smoc | slot | full
set -u
cd /d/ZZL_cluade
ARM="${1:?arm: smoc|slot|full}"
case "$ARM" in
  smoc)
    for i in 0 1 2 3; do
      PYTHONUTF8=1 python -u scripts/lb_reader_arm.py \
        --reader anthropic:claude-haiku-4-5 --arm smoc \
        --data data/wikistate_long_L2_b33.json \
        --cards-dir results/wt_cards_b33_L2 \
        --questions scratchpad/b33d_q_new20_s$i.jsonl \
        --out results/b33d_smoc_L2_new20_s$i.jsonl \
        > scratchpad/b33d_run_smoc_$i.log 2>&1 &
    done; wait ;;
  slot)
    for i in 0 1 2 3; do
      PYTHONUTF8=1 QVF_LEDGER_VIEW=slot python -u scripts/lb_reader_arm.py \
        --reader anthropic:claude-haiku-4-5 --arm smoc \
        --data data/wikistate_long_L2_b33.json \
        --cards-dir results/wt_cards_b33_L2 \
        --questions scratchpad/b33d_q_new20_s$i.jsonl \
        --out results/b33d_slot_L2_new20_s$i.jsonl \
        > scratchpad/b33d_run_slot_$i.log 2>&1 &
    done; wait ;;
  full)
    for i in 0 1 2 3; do
      PYTHONUTF8=1 python -u scripts/lb_reader_arm.py \
        --reader anthropic:claude-haiku-4-5 --arm fullplain \
        --data data/wikistate_long_L2_b33.json \
        --questions scratchpad/b33d_q_new15_s$i.jsonl \
        --out results/b33d_full_haiku_L2_new15_s$i.jsonl \
        > scratchpad/b33d_run_full_$i.log 2>&1 &
    done; wait ;;
esac
echo "ARM $ARM DONE"
