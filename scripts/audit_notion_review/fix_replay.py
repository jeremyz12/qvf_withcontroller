# -*- coding: utf-8 -*-
"""零 API 回放:两项修复候选在 v45 / v48f 上的效果。
(a) 值规范化(读侧 compile 的 _norm 相邻合并口径,按槽位类去括注/公司后缀)
(b) 原句校验丢卡(source_span 全店找不到的卡直接丢)—— 用 b46d 的离线编译上限口径
"""
import json, re, sys, glob, copy
from collections import Counter
sys.path.insert(0, 'D:/ZZL_cluade'); sys.path.insert(0, 'D:/ZZL_cluade/scripts')
import b38e_score as B
import complex_query_arm as C
ROOT = 'D:/ZZL_cluade'
ents = {e['uid']: e for e in json.load(open(f'{ROOT}/data/wikistate_full_ALL_v24.json', encoding='utf-8'))}
qref = [json.loads(l) for l in open(f'{ROOT}/data/wsc_s5_v25.jsonl', encoding='utf-8') if l.strip()]
qs_by_uid = {}
for q in qref: qs_by_uid.setdefault(q['uid'], []).append(q)
CORP = re.compile(r"[,\s]+(llc|inc\.?|ltd\.?|corp\.?|corporation|limited|gmbh|plc)\b\.?$", re.I)
PAREN = re.compile(r"\s*\([^)]*\)\s*$")

def canon(slot_cls, v):
    v = str(v or '').strip()
    if slot_cls in ('employer', 'team', 'residence'):
        v2 = PAREN.sub('', v)
        if slot_cls != 'residence':
            v2 = CORP.sub('', v2)
        v2 = re.sub(r'^(the)\s+', '', v2, flags=re.I).strip()
        return v2 or v
    return v

def slot_cls_of(r, gslot):
    sc = (r.get('slot_class') or '').lower()
    if sc: return sc.split(':')[0]
    s = (r.get('slot') or '').lower()
    for c, al in C.SLOT_ALIASES.items():
        if any(a in s for a in al): return c
    return gslot

# ---------- (a) read-side compile replay ----------
def read_side_answers(uid, recs, mem_dates, gslot):
    """按 complex_query_arm 的池选择+卫生化+相邻 _norm 合并得到链,再按题型算答案。"""
    plan_slot = gslot
    pool = C._select_pool(recs, plan_slot, mem_dates, "how many times have I changed my " + gslot)
    pool = C._hygiene_pool(pool)
    chain = C._chain(pool, mem_dates)
    rows = [(C._rec_date(r, mem_dates), r) for r in chain]
    return rows

def answer_from_rows(qtype, question, rows):
    # 用 b38e 的 today 解析与日期口径,但相邻合并已由 _chain 用 _norm 完成 → 此处只按日期截断
    today_s, _ = B.parse_today(qtype, question)
    today = B.parse_ledger_date(today_s) if today_s else None
    if today is None: return None
    dated = []
    for d, r in rows:
        do = B.parse_ledger_date(d)
        if do is None: continue
        dated.append((do, str(r.get('value', '')), r))
    dated.sort(key=lambda x: x[0])
    if qtype == 'change_count':
        seq = [v for do, v, _ in dated if do <= today]
        return (len(seq) - 1) if seq else None
    if qtype == 'count_before':
        seq = [v for do, v, _ in dated if do < today]
        return len(seq) if seq else None
    if qtype == 'first_vs_last':
        seq = [v for do, v, _ in dated if do <= today]
        return f"first: {seq[0]}; most recent: {seq[-1]}" if seq else None
    if qtype == 'longest_tenure':
        seq = [(do, v) for do, v, _ in dated if do <= today]
        if not seq: return None
        spans = []
        for i, (do, v) in enumerate(seq):
            end = seq[i + 1][0] if i + 1 < len(seq) else today
            spans.append(((end - do).days, v))
        best = max(s for s, _ in spans)
        winners = {v for s, v in spans if s == best}
        return next(iter(winners)) if len(winners) == 1 else f"AMBIGUOUS:{next(iter(winners))}"
    return None

def replay_read_side(store, use_canon):
    n_eq = Counter(); n_tot = Counter(); per_q = {}
    for uid, e in ents.items():
        p = f'{ROOT}/results/{store}/{uid}.json'
        try: recs = json.load(open(p, encoding='utf-8'))['records']
        except FileNotFoundError: continue
        gslot = e['slot'].lower()
        if use_canon:
            recs = copy.deepcopy(recs)
            for r in recs: r['value'] = canon(slot_cls_of(r, gslot), r.get('value'))
        md = C._mem_dates(e)
        rows = read_side_answers(uid, recs, md, gslot)
        for q in qs_by_uid.get(uid, []):
            comp = answer_from_rows(q['qtype'], q['question'], rows)
            eq = B.gold_equal(q['qtype'], q['gold'], comp)
            n_tot[q['qtype']] += 1; n_eq[q['qtype']] += eq; per_q[q['qid']] = eq
    return n_eq, n_tot, per_q

# ---------- (b) span-verify drop replay (ceiling口径 = b46d compiled_ceiling) ----------
def mem_text(e):
    out = {}
    for si, s in enumerate(e['sessions']):
        for ti, t in enumerate(s['turns']):
            out[f'{e["uid"]}/s{si}#r{ti}'] = t
    return out

def ceiling(store, drop_unverified):
    import tempfile, os, shutil
    tmp = None
    if drop_unverified:
        tmp = tempfile.mkdtemp(prefix='spanv_', dir='C:/Users/25243/AppData/Local/Temp/claude')
        dropped = kept = 0
        for f in glob.glob(f'{ROOT}/results/{store}/*.json'):
            j = json.load(open(f, encoding='utf-8')); e = ents[j['uid']]; allt = '\n'.join(mem_text(e).values())
            keep = [r for r in j['records'] if (r.get('source_span') or '').strip() and (r['source_span'].strip() in allt)]
            dropped += len(j['records']) - len(keep); kept += len(keep)
            j2 = dict(j); j2['records'] = keep
            json.dump(j2, open(os.path.join(tmp, os.path.basename(f)), 'w', encoding='utf-8'), ensure_ascii=False)
        store_dir = tmp
        print(f'  span-verify: dropped {dropped}, kept {kept}')
    else:
        store_dir = f'{ROOT}/results/{store}'
    n_eq = n_tot = 0; by_t = Counter(); by_tt = Counter()
    for uid in ents:
        try: _e, _d0, _m, _x, lane_slots, _n, rows = B.diag_uid(uid, ents[uid], store_dir)
        except FileNotFoundError: continue
        lane = set(lane_slots); lane_rows = [(dd, r) for dd, r in rows if (r.get('slot') or '?') in lane]
        for q in qs_by_uid.get(uid, []):
            comp = B.compiled_answer(q['qtype'], q['question'], lane_rows); eq = B.gold_equal(q['qtype'], q['gold'], comp)
            n_tot += 1; by_tt[q['qtype']] += 1; n_eq += eq; by_t[q['qtype']] += eq
    if tmp: shutil.rmtree(tmp, ignore_errors=True)
    return n_eq, n_tot, by_t, by_tt

for store in ('wt_cards_v45', 'wt_cards_v48f'):
    print(f'\n=== {store} ===')
    b_eq, b_tot, bq = replay_read_side(store, False)
    c_eq, c_tot, cq = replay_read_side(store, True)
    tot = sum(b_tot.values())
    print(f'(a) read-side compile replay, {tot} q: baseline gold-equal {sum(b_eq.values())} ({100*sum(b_eq.values())/tot:.1f}%) -> canon {sum(c_eq.values())} ({100*sum(c_eq.values())/tot:.1f}%)')
    for t in sorted(b_tot): print(f'     {t:15s} {b_eq[t]}/{b_tot[t]} -> {c_eq[t]}/{c_tot[t]}')
    flips_up = [q for q in bq if not bq[q] and cq[q]]; flips_dn = [q for q in bq if bq[q] and not cq[q]]
    print(f'     wrong->right {len(flips_up)}, right->wrong {len(flips_dn)} {flips_dn[:5]}')
    e0 = ceiling(store, False); e1 = ceiling(store, True)
    print(f'(b) ceiling (b46d口径) baseline {e0[0]}/{e0[1]} ({100*e0[0]/e0[1]:.1f}%) -> span-verified {e1[0]}/{e1[1]} ({100*e1[0]/e1[1]:.1f}%)')
    for t in sorted(e0[3]): print(f'     {t:15s} {e0[2][t]}/{e0[3][t]} -> {e1[2][t]}/{e1[3][t]}')


# ---------- (c) 值规范化对金标车道链长的影响(渲染路径代理:_norm 相邻合并) ----------
def lane_chain_len(recs, gslot, md, use_canon):
    lane = [r for r in recs if slot_cls_of(r, gslot) == gslot]
    lane.sort(key=lambda r: C._rec_date(r, md) or '9999')
    out = []
    for r in lane:
        v = canon(gslot, r.get('value')) if use_canon else str(r.get('value') or '')
        v = C._norm(v)
        if not v or not C._rec_date(r, md):
            continue
        if out and out[-1] == v:
            continue
        out.append(v)
    return len(out)


def chain_len_effect(store):
    changed = tot = 0; q_aff = Counter(); q_tot = Counter(); ch = 0
    for uid, e in ents.items():
        try:
            recs = json.load(open(f'{ROOT}/results/{store}/{uid}.json', encoding='utf-8'))['records']
        except FileNotFoundError:
            continue
        gslot = e['slot'].lower(); md = C._mem_dates(e)
        for r in recs:
            tot += 1; changed += canon(slot_cls_of(r, gslot), r.get('value')) != str(r.get('value') or '').strip()
        l0 = lane_chain_len(recs, gslot, md, False); l1 = lane_chain_len(recs, gslot, md, True); ch += l0 != l1
        for q in qs_by_uid.get(uid, []):
            q_tot[q['qtype']] += 1
            if l0 != l1 and q['qtype'] in ('change_count', 'count_before', 'longest_tenure'):
                q_aff[q['qtype']] += 1
    print(f'(c) {store}: canon changes {changed}/{tot} values; gold-lane chain length changes in {ch}/144 chains; '
          'questions affected: ' + ', '.join(f'{t} {q_aff[t]}/{q_tot[t]}' for t in sorted(q_tot)))


for store in ('wt_cards_v45', 'wt_cards_v48f'):
    chain_len_effect(store)
