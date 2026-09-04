import json, re, collections, statistics
ROOT='D:/ZZL_cluade'
corpus=json.load(open(f'{ROOT}/data/wikistate_full_ALL_v24.json',encoding='utf-8'))
PAT = re.compile(r"\b(moved to|moving to|new (job|place|apartment|house|car|phone)|start(ed|ing) (a|my|at)|switch(ed|ing)|quit|got (a|my) (new|first)|adopt(ed)?|bought|just joined|promoted|broke up|engaged|married|no longer|used to (live|work))\b", re.I)
START = re.compile(r"\b(appointed|started as|start as|am now|i'm now|as of today|began serving|took office|elected|became|promoted to|started working as|returned as|officially started|joined|signed with|transferred to|relocated|moved|now (work|live|play)|member of|hired|new role|position)\b", re.I)
SLOT = re.compile(r"\b(employer|company|firm|university|college|institute|lab|team|club|squad|parliament|council|minister|professor|fellow|director|chair|residence|live|living|apartment|house|city|home|office|job|work|position|role|title)\b", re.I)
def turns_of(sess):
    for t in sess['turns']:
        yield t
tot_rows=hit_pat=hit_start=hit_any=0; kept_pat=kept_any=tot_turns=0; user_turns=0
sess_hit_any=sess_tot=0
miss_examples=[]
for e in corpus:
    for s in e['sessions']:
        for t in s['turns']:
            tot_turns+=1
            is_user="'role': 'user'" in t[:40]
            if is_user: user_turns+=1
            p=bool(PAT.search(t)); a=p or bool(START.search(t) and SLOT.search(t))
            kept_pat+=p; kept_any+=a
    for row in e['chain']:
        sp=row['state_span']; tot_rows+=1
        found=[t for s in e['sessions'] for t in s['turns'] if sp in t]
        if not found:
            # try loose: first 60 chars
            found=[t for s in e['sessions'] for t in s['turns'] if sp[:60] in t]
        t=found[0] if found else ''
        p=bool(PAT.search(t)); st=bool(START.search(t) and SLOT.search(t)); a=p or st
        hit_pat+=p; hit_start+=st; hit_any+=a
        if not a and len(miss_examples)<12: miss_examples.append((e['slot'],sp[:110]))
print(f'gold rows {tot_rows}; turns {tot_turns} (user {user_turns})')
print(f'LoCoMo PAT regex: anchor recall {hit_pat/tot_rows:.1%}; turns kept {kept_pat/tot_turns:.1%}')
print(f'PAT + start/slot cues: anchor recall {hit_any/tot_rows:.1%}; turns kept {kept_any/tot_turns:.1%}')
print('missed examples:'); [print('  ',m) for m in miss_examples]
