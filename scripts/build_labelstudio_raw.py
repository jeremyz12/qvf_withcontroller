# -*- coding: utf-8 -*-
"""Add raw session data (original user messages containing each anchor) to the
Label Studio English task set, so raters can verify anchors in context.

Reads:  data/labelstudio_tasks_en.json  (chain_text reused verbatim)
        study_logs/wikistate_gold_rating.html  (ITEMS: chain rows with spans)
        data/wikistate_full_ALL.json  (raw sessions per uid)
Writes: data/labelstudio_tasks_en.json  (adds data.raw_text, fixes CONVENTION dup)
"""
import json, re, ast, sys

MAX_MSG = 2200  # chars per quoted message; longer ones truncated around the anchor

def parse_turn(t):
    m = re.match(r"\{'role': '(\w+)', 'content': (.*)\}$", t, re.S)
    if not m:
        return None, t
    role, body = m.group(1), m.group(2)
    try:
        content = ast.literal_eval(body)
    except Exception:
        content = body
        if len(body) >= 2 and body[0] in "'\"" and body[-1] == body[0]:
            content = body[1:-1]
        content = (content.replace("\\n", "\n")
                          .replace("\\'", "'")
                          .replace('\\"', '"'))
    return role, content

def clip(msg, span):
    if len(msg) <= MAX_MSG:
        return msg
    i = msg.find(span)
    if i < 0:
        return msg[:MAX_MSG] + " [... truncated ...]"
    half = (MAX_MSG - len(span)) // 2
    lo, hi = max(0, i - half), min(len(msg), i + len(span) + half)
    out = msg[lo:hi]
    if lo > 0:
        out = "[... truncated ...] " + out
    if hi < len(msg):
        out = out + " [... truncated ...]"
    return out

html = open('study_logs/wikistate_gold_rating.html', encoding='utf-8').read()
items = {it['id']: it for it in json.loads(
    re.search(r'const ITEMS\s*=\s*(\[.*?\]);', html, re.S).group(1))}
full = {e['uid']: e for e in json.load(open('data/wikistate_full_ALL.json', encoding='utf-8'))}
tasks = json.load(open('data/labelstudio_tasks_en.json', encoding='utf-8'))

n_fixed = 0
for task in tasks:
    d = task['data']
    it = items[d['item_id']]
    uid = d['item_id'].rsplit('_', 1)[0]
    entry = full[uid]
    sessions = entry['sessions']
    dates = [s['date'] for s in sessions]

    # locate, for every chain row, the session + user message containing its span
    found = []  # (session_idx, session_date, message, [anchor numbers])
    for k, row in enumerate(it['chain'], 1):
        span = row['span']
        hit = None
        for si, s in enumerate(sessions):
            for t in s['turns']:
                role, content = parse_turn(t)
                if content and span in content:
                    hit = (si, s['date'], content)
                    break
            if hit:
                break
        if hit is None:
            print(f"WARN unmatched anchor: {d['item_id']} #{k}", file=sys.stderr)
            continue
        for f in found:
            if f[0] == hit[0] and f[2] == hit[2]:
                f[3].append(k)
                break
        else:
            found.append([hit[0], hit[1], hit[2], [k]])

    blocks = [
        (f"This persona's full log has {len(sessions)} sessions "
         f"({dates[0]} ... {dates[-1]}). Below: the original user messages that "
         f"contain each anchor, quoted verbatim from the session log.")
    ]
    for si, sdate, msg, ks in found:
        which = ", ".join(f"#{k}" for k in ks)
        span0 = it['chain'][ks[0] - 1]['span']
        blocks.append(f"--- anchor {which} | session dated {sdate} ---\n{clip(msg, span0)}")
    d['raw_text'] = "\n\n".join(blocks)

    if 'CONVENTION: Convention:' in d['chain_text']:
        d['chain_text'] = d['chain_text'].replace('CONVENTION: Convention:', 'CONVENTION:')
        n_fixed += 1

json.dump(tasks, open('data/labelstudio_tasks_en.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
lens = sorted(len(t['data']['raw_text']) for t in tasks)
print(f"tasks: {len(tasks)}  convention-dup fixed: {n_fixed}")
print(f"raw_text chars  min/median/max: {lens[0]}/{lens[len(lens)//2]}/{lens[-1]}")
