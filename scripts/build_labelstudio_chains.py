# -*- coding: utf-8 -*-
"""Build Project B — chain-level full-coverage verification (144 chains + 5 catch trials).

Each task shows one state chain (numbered HTML table) + the persona's full raw
session log (user messages, anchors highlighted). Raters judge whether the chain
is a correct and complete representation of the log.

Catch trials: 5 corrupted copies of real chains (one per injection type),
interleaved under neutral ids. The catch key is written ONLY to the local map
file, never into Label Studio task data.

Reads:  data/wikistate_full_ALL.json
Writes: data/labelstudio_tasks_chains_en.json   (149 tasks, neutral ids)
        data/labelstudio_chainproj_map.json     (id -> uid / catch / injection)
"""
import json, re, ast, html as H, random

STYLE = """<style>
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;margin:0;padding:2px;color:#222}
table{border-collapse:collapse;width:100%;background:#fff}
th{background:#e8edf6;text-align:left;padding:6px 10px;border:1px solid #c2cddd;font-size:13px}
td{padding:6px 10px;border:1px solid #c2cddd;font-size:13px;vertical-align:top}
tr:nth-child(even) td{background:#f6f8fc}
.rownum{color:#888;text-align:center;width:34px}
.scrollbox{max-height:440px;overflow-y:auto;border:1px solid #e0d7c4;border-radius:6px;background:#fffdf8}
.hd{position:sticky;top:0;background:#f0e9dc;font-weight:700;padding:6px 10px;font-size:12.5px;border-bottom:1px solid #d8ccb4}
.intro{font-size:12.5px;color:#555;margin:6px 10px}
.sess{margin:12px 10px 2px;font-weight:600;font-size:12.5px;color:#7a5b2b}
.anch{background:#7a5b2b;color:#fff;border-radius:3px;padding:0 5px;font-size:11px;margin-left:6px}
p{margin:2px 10px 6px;font-size:12.5px;line-height:1.55}
mark{background:#ffe9a8;padding:0 2px}
</style>"""

WRONG_VALUE = {'employer': 'Stanford University', 'position': 'senior policy advisor',
               'team': 'AC Milan', 'residence': 'Toronto'}
WRONG_VALUE2 = {'employer': 'Microsoft Research', 'position': 'deputy director',
                'team': 'FC Porto', 'residence': 'Vienna'}

def parse_turn(t):
    m = re.match(r"\{'role': '(\w+)', 'content': (.*?)\}?$", t, re.S)
    if not m:
        return None, t
    role, body = m.group(1), m.group(2)
    try:
        content = ast.literal_eval(body)
    except Exception:
        content = body
        if len(body) >= 2 and body[0] in "'\"":
            content = body[1:] if body[-1] != body[0] else body[1:-1]
        content = (content.replace("\\n", "\n")
                          .replace("\\'", "'")
                          .replace('\\"', '"'))
    return role, content

def esc_br(text):
    return H.escape(text).replace('\n', '<br>')

def chain_table(chain):
    rows = []
    for i, r in enumerate(chain, 1):
        rows.append(f"<tr><td class='rownum'>#{i}</td><td>{H.escape(r['date'])}</td>"
                    f"<td>{H.escape(r['value'])}</td>"
                    f"<td>“{H.escape(r['state_span'])}”</td></tr>")
    return (STYLE +
        "<table><thead><tr><th>ROW</th><th>DATE</th><th>VALUE</th>"
        "<th>SOURCE SENTENCE (verbatim anchor)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>")

def raw_log(sessions, chain):
    anchors_at = {}
    for k, row in enumerate(chain, 1):
        span = row['state_span']
        hit = None
        for si, s in enumerate(sessions):
            mi = -1
            for t in s['turns']:
                role, content = parse_turn(t)
                if role == 'user' or role is None:
                    mi += 1
                    if content and span in content:
                        hit = (si, mi)
                        break
            if hit:
                break
        if hit:                      # fabricated catch anchors legitimately miss
            anchors_at.setdefault(hit, []).append(k)
    parts = [STYLE, "<div class='scrollbox'>",
        "<div class='hd'>RAW MEMORY — the persona's full session log (scroll inside this box)</div>",
        (f"<div class='intro'>All {len(sessions)} sessions "
         f"({sessions[0]['date']} … {sessions[-1]['date']}), every user message "
         f"quoted verbatim; assistant replies omitted (state declarations occur only "
         f"in user messages). Chain-row anchors are <mark>highlighted</mark> where found.</div>")]
    for si, s in enumerate(sessions):
        ks_here = sorted(k for (s2, _), ks in anchors_at.items() if s2 == si for k in ks)
        badge = (f"<span class='anch'>row {', '.join('#'+str(k) for k in ks_here)}</span>"
                 if ks_here else '')
        parts.append(f"<div class='sess'>Session {si+1} · {H.escape(s['date'])}{badge}</div>")
        mi = -1
        for t in s['turns']:
            role, content = parse_turn(t)
            if role == 'user' or role is None:
                mi += 1
                body = esc_br(content)
                for k in anchors_at.get((si, mi), []):
                    span_esc = esc_br(chain[k - 1]['state_span'])
                    body = body.replace(span_esc, f"<mark>{span_esc}</mark>")
                parts.append(f"<p>{body}</p>")
    parts.append("</div>")
    return ''.join(parts)

def shift_year(date, delta):
    return f"{int(date[:4]) + delta}{date[4:]}"

def inject(entry, kind):
    """Return a corrupted deep copy of entry's chain and a description."""
    chain = [dict(r) for r in entry['chain']]
    slot = entry['slot']
    if kind == 'date_shift':
        chain[1]['date'] = shift_year(chain[1]['date'], 2)
        desc = f"row #2 date shifted +2 years (now {chain[1]['date']})"
    elif kind == 'delete_row':
        removed = chain.pop(1)
        desc = f"row for '{removed['value']}' ({removed['date']}) deleted — missing transition"
    elif kind == 'value_swap':
        chain[1]['value'], chain[2]['value'] = chain[2]['value'], chain[1]['value']
        desc = "values of rows #2 and #3 swapped (anchor sentences unchanged)"
    elif kind == 'fabricate_anchor':
        wrong = WRONG_VALUE[slot]
        chain[1]['value'] = wrong
        chain[1]['state_span'] = f"I can officially confirm the switch to {wrong} as of today"
        desc = f"row #2 replaced with fabricated value/anchor '{wrong}' (not in log)"
    elif kind == 'add_row':
        wrong = WRONG_VALUE2[slot]
        mid = shift_year(chain[-2]['date'], 1)
        chain.insert(len(chain) - 1, {'value': wrong, 'date': mid,
            'state_span': f"quick update: as of this week it's officially {wrong} for me"})
        desc = f"fabricated extra row '{wrong}' ({mid}) inserted (no support in log)"
    return chain, desc

full = json.load(open('data/wikistate_full_ALL.json', encoding='utf-8'))
rng = random.Random(42)

candidates = [e for e in full if len(e['chain']) >= 4]
catch_src = rng.sample(candidates, 5)
kinds = ['date_shift', 'delete_row', 'value_swap', 'fabricate_anchor', 'add_row']

items = []   # (uid, slot, chain, sessions, catch, injection)
for e in full:
    items.append((e['uid'], e['slot'], e['chain'], e['sessions'], False, None))
for e, kind in zip(catch_src, kinds):
    chain, desc = inject(e, kind)
    items.append((e['uid'], e['slot'], chain, e['sessions'], True, f"{kind}: {desc}"))

rng.shuffle(items)

tasks, mapping = [], {}
for n, (uid, slot, chain, sessions, catch, injection) in enumerate(items, 1):
    disp = f"chain-{n:03d}"
    tasks.append({'data': {
        'item_id': disp, 'slot': slot,
        'chain_html': chain_table(chain),
        'raw_html': raw_log(sessions, chain)}})
    mapping[disp] = {'uid': uid, 'catch': catch, 'injection': injection}

json.dump(tasks, open('data/labelstudio_tasks_chains_en.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
json.dump(mapping, open('data/labelstudio_chainproj_map.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
n_catch = sum(1 for m in mapping.values() if m['catch'])
print(f"tasks: {len(tasks)} (catch trials: {n_catch})")
print("catch items:", {k: v['injection'] for k, v in mapping.items() if v['catch']})
