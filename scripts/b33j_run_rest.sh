#!/bin/sh
# 批 33-J 剩余跑批链(J2 收口 -> J3 建店+三臂 -> J1 续跑),并发恒 <=4。
set -u
cd /d/ZZL_cluade || exit 1
export PYTHONUTF8=1
export QVF_EMBED_BACKEND=openai

# ── 1) 等 J2 跑满 576 ──────────────────────────────────────────
while [ "$(cat results/b33j/j2_*.jsonl 2>/dev/null | wc -l)" -lt 576 ]; do sleep 60; done
echo "STAGE J2 DONE"

# ── 2) J3:无填充语料建卡(1 进程) ────────────────────────────
python scripts/wt_qvf_prototype.py --phase write \
  --data data/b33j_nofiller_30.json \
  --cards-dir results/wt_cards_b33j_nofiller > results/b33j/log_j3_build.txt 2>&1
echo "STAGE J3 CARDS DONE $(ls results/wt_cards_b33j_nofiller | wc -l)"

# ── 3) J3:三臂 × 120 题(3 进程) ─────────────────────────────
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/b33j_nofiller_30.json --cards-dir results/wt_cards_b33j_nofiller \
  --questions data/b33j_nofiller_30_q120.jsonl \
  --out results/b33j/j3_smoc_nofiller_s0.jsonl > results/b33j/log_j3_smoc.txt 2>&1 &
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/b33j_nofiller_30.json \
  --questions data/b33j_nofiller_30_q120.jsonl \
  --out results/b33j/j3_direct_nofiller_s0.jsonl > results/b33j/log_j3_direct.txt 2>&1 &
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm fullplain \
  --data data/b33j_nofiller_30.json \
  --questions data/b33j_nofiller_30_q120.jsonl \
  --out results/b33j/j3_fullplain_nofiller_s0.jsonl > results/b33j/log_j3_full.txt 2>&1 &
wait
echo "STAGE J3 ARMS DONE $(cat results/b33j/j3_*_nofiller_s0.jsonl | wc -l)"

# ── 4) J1 续跑(4 分片,block 分片,断点续) ────────────────────
for s in 0 1 2 3; do
  python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm rtl \
    --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
    --out results/b33j/j1_rtl_s$s.jsonl --nshards 4 --shard $s --shard-mode block \
    >> results/b33j/log_j1_s$s.txt 2>&1 &
done
wait
echo "STAGE J1 DONE $(cat results/b33j/j1_rtl_s*.jsonl | wc -l)"
echo "ALL B33J STAGES COMPLETE"
