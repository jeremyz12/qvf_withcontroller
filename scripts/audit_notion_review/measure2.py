import json, glob, os, sys, re, collections, statistics
sys.path.insert(0,'D:/ZZL_cluade'); sys.path.insert(0,'D:/ZZL_cluade/scripts')
ROOT='D:/ZZL_cluade'
corpus={e['uid']:e for e in json.load(open(f'{ROOT}/data/wikistate_full_ALL_v24.json',encoding='utf-8'))}
import b38e_score as B
print('val_match src:'); import inspect; print(inspect.getsource(B.val_match)[:900])
def norm(s): return ' '.join(str(s).lower().replace('_',' ').replace('-',' ').split())
def toks(s): return set(re.findall(r'[a-z0-9]+', norm(s)))-{'the','of','at','a','an','in','and'}
for store in ('wt_cards_v45','wt_cards_v48f'):
    cdir=f'{ROOT}/results/{store}'
    adj_total=adj_alias=chains_touched=0; ex=[]
    for uid,e in corpus.items():
        try: rows=B.ledger_rows(uid,e,cdir)
        except Exception as err: print('ledger_rows fail',uid,err); continue
        gslot=e['slot'].lower()
        lane=[(d,r) for d,r in rows if gslot in (r.get('slot') or '').lower() or (r.get('slot') or '').lower() in gslot]
        lane.sort(key=lambda x: str(x[0]))
        touched=False
        for (d1,r1),(d2,r2) in zip(lane,lane[1:]):
            a,b=norm(r1.get('value')),norm(r2.get('value'))
            if a==b: continue
            adj_total+=1
            ta,tb=toks(a),toks(b)
            j=len(ta&tb)/max(1,len(ta|tb))
            if a in b or b in a or j>=0.5:
                adj_alias+=1; touched=True
                if len(ex)<8: ex.append((uid[-9:],a[:50],b[:50]))
        chains_touched+=touched
    print(f'\n{store}: adjacent value-changes in gold lane {adj_total}; near-duplicate (alias-like) {adj_alias} in {chains_touched} chains')
    for x in ex: print('   ',x)
# span verbatim check
def mem_text(e):
    out={}
    for si,s in enumerate(e['sessions']):
        for ti,t in enumerate(s['turns']):
            out[f'{e["uid"]}/s{si}#r{ti}']=t
    return out
for store in ('wt_cards_v45','wt_cards_v48f'):
    own=elsewhere=nowhere=tot=0; sample_ids=[]
    for f in glob.glob(f'{ROOT}/results/{store}/*.json'):
        j=json.load(open(f,encoding='utf-8')); uid=j['uid']; e=corpus[uid]; mt=mem_text(e); allt='\n'.join(mt.values())
        if not sample_ids: sample_ids=[r['source_memory_id'] for r in j['records'][:2]]+list(mt)[:2]
        for r in j['records']:
            sp=(r.get('source_span') or '').strip(); tot+=1
            if not sp: nowhere+=1; continue
            if sp in mt.get(r.get('source_memory_id'),''): own+=1
            elif sp in allt: elsewhere+=1
            else: nowhere+=1
    print(f'\n{store}: spans verbatim in own memory {own/tot:.1%}, elsewhere in store {elsewhere/tot:.1%}, not found (paraphrased/fabricated) {nowhere/tot:.1%}  (n={tot}); id sample {sample_ids}')
