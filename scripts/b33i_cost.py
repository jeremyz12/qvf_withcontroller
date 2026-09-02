# -*- coding: utf-8 -*-
"""33-I 全轮成本账($0):建卡 + 读端 + 判官 + 嵌入。"""
import json, os, sys
P_IN,P_OUT,J_IN,J_OUT = 1.0,5.0,5.0,25.0
EMB_RATE = 0.02/1e6
def L(p): return [json.loads(l) for l in open(p,encoding='utf-8')] if os.path.exists(p) else []
tot=0.0; rows=[]
for d in ['results/wt_cards_b33i_lme','results/wt_cards_b33i_mab','results/wt_cards_b33i_lme_ms',
          'results/wt_cards_b33i_lme_ssu','results/wt_cards_b33i_lme_ssa']:
    if not os.path.isdir(d): continue
    ti=to=0;n=0
    for f in os.listdir(d):
        c=json.load(open(os.path.join(d,f),encoding='utf-8')); ti+=c.get('usage_in',0); to+=c.get('usage_out',0); n+=1
    u=ti/1e6*P_IN+to/1e6*P_OUT; tot+=u; rows.append(('BUILD '+d.split('/')[-1],n,u))
JR_SSP, JR_SHORT = 0.00756, 0.00276
READS=[('b33i_lme_ssp_smoc',None),('b33i_lme_ssp_direct',JR_SSP),('b33i_lme_ssp_ledgerplain',None),
       ('b33i_mabfc_mh6k_wt',JR_SHORT),('b33i_mabfc_mh6k_direct',JR_SHORT),
       ('b33i_mabfc_mh32k_wt',JR_SHORT),('b33i_mabfc_mh32k_wt_p0',JR_SHORT),('b33i_mabfc_mh32k_wt_p1',JR_SHORT),
       ('b33i_mabfc_mh32k_direct',JR_SHORT),
       ('b33i_lme_ms_smoc',None),('b33i_lme_ms_direct',JR_SHORT),
       ('b33i_lme_ssu_smoc',None),('b33i_lme_ssu_direct',JR_SHORT),
       ('b33i_lme_ssa_smoc',None),('b33i_lme_ssa_direct',JR_SHORT)]
for tag,jr in READS:
    r=L('results/'+tag+'.jsonl')
    if not r: continue
    i=sum(x.get('usage_input_tokens',0) or 0 for x in r); o=sum(x.get('usage_output_tokens',0) or 0 for x in r)
    ji=sum(x.get('judge_input_tokens',0) or 0 for x in r); jo=sum(x.get('judge_output_tokens',0) or 0 for x in r)
    u=i/1e6*P_IN+o/1e6*P_OUT + ((ji/1e6*J_IN+jo/1e6*J_OUT) if ji else len(r)*(jr or 0))
    tot+=u; rows.append(('READ '+tag,len(r),u))
# embeddings: direct arms embed the full haystack once per question
data=json.load(open('data/longmemeval_s_cleaned.json',encoding='utf-8'))
bysp={}
for x in data: bysp.setdefault(x['question_type'],[]).append(x)
emb=0.0
for sp,f in [('single-session-preference','b33i_lme_ssp_direct'),('multi-session','b33i_lme_ms_direct'),
             ('single-session-user','b33i_lme_ssu_direct'),('single-session-assistant','b33i_lme_ssa_direct')]:
    r=L('results/'+f+'.jsonl')
    if not r: continue
    ids={x['question_id'] for x in r}
    ch=sum(len(str(t.get('content',''))) for x in bysp[sp] if x['question_id'] in ids
           for ss in x['haystack_sessions'] for t in ss)
    emb+=ch/3.6*EMB_RATE
emb += (48992+323650)/3.6*EMB_RATE*2
tot+=emb; rows.append(('EMBED openai',0,emb))
for t,n,u in rows: print('%-42s n=%4d  $%7.4f'%(t,n,u))
print('-'*62)
print('%-42s        $%7.4f'%('TOTAL (usage-token accounting)',tot))
print('%-42s        $%7.4f'%('+ mh_32k unlogged (reconstructed, central)',1.60))
print('%-42s        $%7.4f  [cap $65]'%('TOTAL incl. reconstruction',tot+1.60))
