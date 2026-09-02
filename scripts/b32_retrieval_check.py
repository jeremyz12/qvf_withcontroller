# -*- coding: utf-8 -*-
"""批32机制核验:离线重跑 top-10 检索,看更正会话/双锚句是否进入 direct 的视野。"""
import json, sys
sys.path.insert(0, 'scripts'); sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env')
from ext_direct_arm import _memories, _retriever_cls
from collections import Counter

def txt(m):
    try: return " ".join(str(v) for v in vars(m).values()).lower()
    except Exception: return str(m).lower()

d = {e['uid']: e for e in json.loads(open('data/wikistate_v3C.json', encoding='utf-8').read())}
qs = [json.loads(l) for l in open('data/wsc_v3_new.jsonl', encoding='utf-8')]
R = _retriever_cls(); cache = {}
hit = Counter(); tot = Counter(); both = 0; n_sc = 0
out = open('results/b32_retrieval_check.jsonl', 'w', encoding='utf-8')
for i, q in enumerate(qs, 1):
    e = d[q['uid']]
    if q['uid'] not in cache: cache[q['uid']] = R(_memories(e))
    got = [txt(m) for m in cache[q['uid']].retrieve(q['question'], top_k=10)]
    t = q['qtype']; tot[t] += 1
    corr = any('quick correction on something i mentioned before' in x for x in got)
    anchors = sum(1 for c in e['chain'] if any(c['state_span'].lower()[:40] in x for x in got))
    hit[t] += corr
    if t == 'scoped_count':
        n_sc += 1; both += anchors >= 2
    out.write(json.dumps({'qid': q['qid'], 'qtype': t, 'corr_in_top10': corr, 'anchors_in_top10': anchors}) + '\n')
    if i % 50 == 0: print(f'[{i}/{len(qs)}]', flush=True)
print("direct top-10 命中更正会话:", {t: f"{hit[t]}/{tot[t]} ({hit[t]/tot[t]*100:.0f}%)" for t in tot})
print(f"scoped_count top-10 含 >=2 条链锚句:{both}/{n_sc} ({both/n_sc*100:.0f}%)")
