#!/usr/bin/env bash
# 批 33-C 保留集:建店(4 分片)→ 三臂读者。全部命令逐字可复现。
set -u
cd /d/ZZL_cluade

STAGE="${1:-all}"

if [ "$STAGE" = "cards" ] || [ "$STAGE" = "all" ]; then
  # 建店:results/wt_cards_holdout(新建,OWNER_GATE=0,建后只读)
  mkdir -p results/wt_cards_holdout
  PYTHONUTF8=1 python -c "
import json
d=json.load(open('data/wikistate_holdout_v1.json',encoding='utf-8'))
u=[e['uid'] for e in d]
for i in range(4):
    open(f'scratchpad/holdout_uids_{i}.txt','w').write(','.join(u[i::4]))
print(len(u))
"
  for i in 0 1 2 3; do
    QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 nohup python -u scripts/wt_qvf_prototype.py \
      --phase write --data data/wikistate_holdout_v1.json \
      --cards-dir results/wt_cards_holdout \
      --uids "$(cat scratchpad/holdout_uids_$i.txt)" \
      > scratchpad/holdout_cards_$i.log 2>&1 &
  done
  wait
  echo "CARDS DONE: $(ls results/wt_cards_holdout | wc -l) files"
fi

if [ "$STAGE" = "arms" ] || [ "$STAGE" = "all" ]; then
  PYTHONUTF8=1 nohup python -u scripts/lb_reader_arm.py \
    --reader anthropic:claude-haiku-4-5 --arm smoc \
    --data data/wikistate_holdout_v1.json \
    --questions data/wsc_holdout_v1.jsonl \
    --cards-dir results/wt_cards_holdout \
    --out results/holdout_smoc.jsonl > scratchpad/holdout_smoc.log 2>&1 &

  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 nohup python -u scripts/lb_reader_arm.py \
    --reader anthropic:claude-haiku-4-5 --arm direct \
    --data data/wikistate_holdout_v1.json \
    --questions data/wsc_holdout_v1.jsonl \
    --cards-dir results/wt_cards_holdout \
    --out results/holdout_direct.jsonl > scratchpad/holdout_direct.log 2>&1 &

  PYTHONUTF8=1 nohup python -u scripts/lb_reader_arm.py \
    --reader anthropic:claude-haiku-4-5 --arm fullplain \
    --data data/wikistate_holdout_v1.json \
    --questions data/wsc_holdout_v1.jsonl \
    --cards-dir results/wt_cards_holdout \
    --out results/holdout_fullplain.jsonl > scratchpad/holdout_fullplain.log 2>&1 &
  wait
  echo "ARMS DONE"
fi
