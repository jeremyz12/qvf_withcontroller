# -*- coding: utf-8 -*-
"""把题目文件按"尚未在输出里"切成 N 片,供并发读取;用法:
python scripts/shard_questions.py <questions> <existing_out> <N> <prefix>"""
import json, sys
from pathlib import Path
qf, outf, n, prefix = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
done = set()
if Path(outf).exists():
    done = {json.loads(l)['question_id'] for l in open(outf, encoding='utf-8')}
qs = [json.loads(l) for l in open(qf, encoding='utf-8') if json.loads(l)['qid'] not in done]
for i in range(n):
    with open(f"{prefix}_{i}.jsonl", 'w', encoding='utf-8') as f:
        for q in qs[i::n]: f.write(json.dumps(q, ensure_ascii=False) + '\n')
print(f"{qf}: 已完成 {len(done)},剩余 {len(qs)} → {n} 片(每片≈{len(qs)//n})")
