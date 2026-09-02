# -*- coding: utf-8 -*-
"""批32-B机制核验:语料D上离线重跑 top-10,统计第三人称干扰会话被检入的比例。"""
import json, sys
sys.path.insert(0, 'scripts'); sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env')
from ext_direct_arm import _memories, _retriever_cls

def txt(m):
    try: return " ".join(str(v) for v in vars(m).values()).lower()
    except Exception: return str(m).lower()

d = {e['uid']: e for e in json.loads(open('data/wikistate_v3D.json', encoding='utf-8').read())}
dl = {}
for l in open('results/v3D_distractor_log.jsonl', encoding='utf-8'):
    r = json.loads(l); dl.setdefault(r['uid'], []).append(r['text'].lower()[:60])
qs = [json.loads(l) for l in open('data/wsc_s5_v2.jsonl', encoding='utf-8')]
R = _retriever_cls(); cache = {}
tot = 0; any_hit = 0; slots = 0
out = open('results/b32_distractor_pull.jsonl', 'w', encoding='utf-8')
for i, q in enumerate(qs, 1):
    e = d[q['uid']]
    if q['uid'] not in cache: cache[q['uid']] = R(_memories(e))
    got = [txt(m) for m in cache[q['uid']].retrieve(q['question'], top_k=10)]
    k = sum(1 for g in got if any(t in g for t in dl.get(q['uid'], [])))
    tot += 1; any_hit += (k > 0); slots += k
    out.write(json.dumps({'qid': q['qid'], 'qtype': q['qtype'], 'distractors_in_top10': k}) + '\n')
    if i % 100 == 0: print(f'[{i}/{len(qs)}]', flush=True)
print(f"top-10 含至少 1 个干扰会话的题:{any_hit}/{tot} ({any_hit/tot*100:.0f}%);平均每题占 {slots/tot:.2f}/10 个槽")
