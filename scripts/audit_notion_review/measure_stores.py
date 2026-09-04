import json, glob, collections, statistics, os
ROOT='D:/ZZL_cluade'
corpus={e['uid']:e for e in json.load(open(f'{ROOT}/data/wikistate_full_ALL_v24.json',encoding='utf-8'))}
GOLD4={'employer','position','team','residence'}
def load(store):
    out={}
    for f in glob.glob(f'{ROOT}/results/{store}/*.json'):
        j=json.load(open(f,encoding='utf-8')); out[j.get('uid') or os.path.basename(f)[:-5]]=j
    return out
for store in ('wt_cards_v45','wt_cards_v48','wt_cards_v48f'):
    S=load(store); n=len(S)
    recs=[r for j in S.values() for r in j['records']]
    per=[len(j['records']) for j in S.values()]
    keys=collections.Counter(k for r in recs for k in r.keys())
    print(f'\n=== {store}: stores={n} cards={len(recs)} per-store mean={statistics.mean(per):.1f} median={statistics.median(per)} min={min(per)} max={max(per)}')
    print('  fields present (share of cards):', {k: round(v/len(recs),2) for k,v in keys.items() if k not in ('record_id','source_memory_id','source_span','entity','slot','value')})
    # usage
    ui=[j.get('usage_in',0) for j in S.values()]; uo=[j.get('usage_out',0) for j in S.values()]
    if any(ui): print(f'  build tokens/store: in mean={statistics.mean(ui):.0f} out mean={statistics.mean(uo):.0f}; total in={sum(ui)} out={sum(uo)}')
    ent=collections.Counter((r.get('entity') or '').lower() for r in recs)
    print('  entity top:', ent.most_common(4))
    if keys.get('owner'):
        own=collections.Counter((r.get('owner') or '') for r in recs); print('  owner top:', own.most_common(4))
        neq=sum(1 for r in recs if (r.get('owner') or '') and (r.get('entity') or '').lower()!=(r.get('owner') or '').lower())
        print(f'  owner != entity (non-empty owner): {neq}/{len(recs)}')
    if keys.get('slot_class'):
        sc=collections.Counter((r.get('slot_class') or '').split(':')[0] for r in recs)
        print('  slot_class top:', sc.most_common(8)); print('  share in 4 gold classes:', round(sum(v for k,v in sc.items() if k in GOLD4)/len(recs),3))
    tr=collections.Counter(r.get('temporal_relation') for r in recs); print('  temporal_relation:', dict(tr))
    cond=sum(1 for r in recs if (r.get('condition') or '').strip()); imp=sum(1 for r in recs if r.get('implies_stale_slots')); tags=sum(1 for r in recs if r.get('value_tags'))
    print(f'  condition non-empty {cond} ({cond/len(recs):.1%}); implies_stale_slots non-empty {imp} ({imp/len(recs):.1%}); value_tags non-empty {tags}')
    # relation edges resolve
    tot=res=0
    for j in S.values():
        ids={r.get('record_id') for r in j['records']}
        for r in j['records']:
            for t in (r.get('relation_target_record_ids') or []):
                tot+=1; res+= t in ids
    print(f'  relation edges: {tot} total, {res} resolve within store, {tot-res} dangling; cards with edges {sum(1 for r in recs if r.get("relation_target_record_ids"))}')
    # claim char share
    tot_chars=sum(len(json.dumps(r,ensure_ascii=False)) for r in recs); claim_chars=sum(len(r.get('claim') or '') for r in recs); span_chars=sum(len(r.get('source_span') or '') for r in recs)
    rel_chars=sum(len(json.dumps({k:r.get(k) for k in ('temporal_relation','relation_target_record_ids','condition','implies_stale_slots','slot_cardinality')},ensure_ascii=False)) for r in recs)
    print(f'  chars: total {tot_chars}, claim {claim_chars/tot_chars:.1%}, source_span {span_chars/tot_chars:.1%}, relation+species fields {rel_chars/tot_chars:.1%}')
    # slot (raw) mapping to gold slot: how many cards per store fall in gold slot lane by naive alias
    ALIAS={'employer':['employer','company','organization','organisation','affiliation','workplace','work','job'],'position':['position','occupation','role','title','office','parliament','job_title','political'],'team':['team','club','squad'],'residence':['residence','home','city','address','location','lives']}
    lane=[]
    for uid,j in S.items():
        gs=corpus[uid]['slot'].lower(); cues=ALIAS.get(gs,[gs])
        k=sum(1 for r in j['records'] if any(c in ((r.get('slot_class') or '')+' '+(r.get('slot') or '')).lower() for c in cues))
        lane.append((k,len(corpus[uid]['chain'])))
    print(f'  gold-slot lane cards per store mean={statistics.mean(x for x,_ in lane):.1f} vs gold rows mean={statistics.mean(g for _,g in lane):.2f}; other-slot cards mean={statistics.mean(len(j["records"]) for j in S.values())-statistics.mean(x for x,_ in lane):.1f}')
# corpus size and batch count
CH=320000
lens=[]
for uid,e in corpus.items():
    tot=0
    for s in e['sessions']:
        for t in s['turns']:
            tot+=len(t)+60
    lens.append(tot)
print(f'\n=== corpus: chars/store mean={statistics.mean(lens):.0f} max={max(lens)}; stores over {CH} chars (multi-batch): {sum(1 for x in lens if x>CH)}/144; approx tokens/store mean={statistics.mean(lens)/4:.0f}')
