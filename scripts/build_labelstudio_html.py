# -*- coding: utf-8 -*-
"""Rebuild Label Studio tasks with real HTML rendering (v3):
- chain_html: styled <table> of the state chain + convention note
- raw_html:  the persona's FULL session log (every user message of every
  session, verbatim; assistant replies omitted), anchor sentences <mark>ed

HyperText renders task-data HTML inside an iframe, so the <style> block must
be embedded in the HTML itself (config <Style> does not reach the iframe).

Reads:  data/labelstudio_tasks_en.json      (question/gold/chain_text reused)
        study_logs/wikistate_gold_rating.html (ITEMS: chain rows with spans)
        data/wikistate_full_ALL.json          (raw sessions per uid)
Writes: data/labelstudio_tasks_en.json       (adds chain_html + raw_html)
"""
import json, re, ast, html as H, sys

STYLE = """<style>
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;margin:0;padding:2px;color:#222}
table{border-collapse:collapse;width:100%;background:#fff}
th{background:#e8edf6;text-align:left;padding:6px 10px;border:1px solid #c2cddd;font-size:13px}
td{padding:6px 10px;border:1px solid #c2cddd;font-size:13px;vertical-align:top}
tr:nth-child(even) td{background:#f6f8fc}
.conv{margin-top:8px;font-size:12.5px;color:#555}
.scrollbox{max-height:440px;overflow-y:auto;border:1px solid #e0d7c4;border-radius:6px;background:#fffdf8}
.hd{position:sticky;top:0;background:#f0e9dc;font-weight:700;padding:6px 10px;font-size:12.5px;border-bottom:1px solid #d8ccb4}
.intro{font-size:12.5px;color:#555;margin:6px 10px}
.sess{margin:12px 10px 2px;font-weight:600;font-size:12.5px;color:#7a5b2b}
.anch{background:#7a5b2b;color:#fff;border-radius:3px;padding:0 5px;font-size:11px;margin-left:6px}
p{margin:2px 10px 6px;font-size:12.5px;line-height:1.55}
mark{background:#ffe9a8;padding:0 2px}
</style>"""

def parse_turn(t):
    """Role comes from the prefix; assistant turns are stored truncated (no
    closing quote/brace), so parse leniently and never rely on the tail."""
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

htmlsrc = open('study_logs/wikistate_gold_rating.html', encoding='utf-8').read()
items = {it['id']: it for it in json.loads(
    re.search(r'const ITEMS\s*=\s*(\[.*?\]);', htmlsrc, re.S).group(1))}
full = {e['uid']: e for e in json.load(open('data/wikistate_full_ALL.json', encoding='utf-8'))}
tasks = json.load(open('data/labelstudio_tasks_en.json', encoding='utf-8'))

for task in tasks:
    d = task['data']
    it = items[d['item_id']]
    uid = d['item_id'].rsplit('_', 1)[0]
    entry = full[uid]
    sessions = entry['sessions']

    # ---- chain_html: real table + convention note (wording reused from chain_text)
    conv = next((ln[len('CONVENTION:'):].strip()
                 for ln in d['chain_text'].splitlines()
                 if ln.startswith('CONVENTION:')), '')
    rows = []
    for row in it['chain']:
        rows.append(f"<tr><td>{H.escape(row['date'])}</td>"
                    f"<td>{H.escape(row['value'])}</td>"
                    f"<td>“{H.escape(row['span'])}”</td></tr>")
    d['chain_html'] = (STYLE +
        "<table><thead><tr><th>DATE</th><th>VALUE</th>"
        "<th>SOURCE SENTENCE (verbatim anchor)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<div class='conv'>CONVENTION: {H.escape(conv)}</div>")

    # ---- raw_html: full log, all user messages, anchors marked
    # map each anchor to (session index, user message index within session)
    anchors_at = {}   # (si, mi) -> [anchor numbers]
    for k, row in enumerate(it['chain'], 1):
        span = row['span']
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
        if hit is None:
            print(f"WARN unmatched anchor: {d['item_id']} #{k}", file=sys.stderr)
            continue
        anchors_at.setdefault(hit, []).append(k)

    parts = [STYLE,
        "<div class='scrollbox'>",
        ("<div class='hd'>RAW MEMORY — the persona's full session log "
         "(scroll inside this box)</div>"),
        (f"<div class='intro'>All {len(sessions)} sessions "
         f"({sessions[0]['date']} … {sessions[-1]['date']}), every user message "
         f"quoted verbatim; assistant replies omitted (state declarations occur only "
         f"in user messages). Anchor sentences are <mark>highlighted</mark>.</div>")]
    for si, s in enumerate(sessions):
        badge = ''
        ks_here = sorted(k for (s2, _), ks in anchors_at.items() if s2 == si for k in ks)
        if ks_here:
            badge = f"<span class='anch'>anchor {', '.join('#'+str(k) for k in ks_here)}</span>"
        parts.append(f"<div class='sess'>Session {si+1} · {H.escape(s['date'])}{badge}</div>")
        mi = -1
        for t in s['turns']:
            role, content = parse_turn(t)
            if role == 'user' or role is None:
                mi += 1
                body = esc_br(content)
                for k in anchors_at.get((si, mi), []):
                    span_esc = esc_br(it['chain'][k - 1]['span'])
                    body = body.replace(span_esc, f"<mark>{span_esc}</mark>")
                parts.append(f"<p>{body}</p>")
    parts.append("</div>")
    d['raw_html'] = ''.join(parts)
    d.pop('raw_text', None)

json.dump(tasks, open('data/labelstudio_tasks_en.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
marks = [t['data']['raw_html'].count('<mark>') - 1 for t in tasks]  # -1: intro's own
need = [len(items[t['data']['item_id']]['chain']) for t in tasks]
bad = [(t['data']['item_id'], m, n) for t, m, n in zip(tasks, marks, need) if m < n]
lens = sorted(len(t['data']['raw_html']) for t in tasks)
print(f"tasks: {len(tasks)}  raw_html chars min/median/max: {lens[0]}/{lens[len(lens)//2]}/{lens[-1]}")
print(f"anchors highlighted vs needed — deficient tasks: {bad if bad else 'none'}")
