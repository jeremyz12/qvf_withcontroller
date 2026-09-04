# -*- coding: utf-8 -*-
"""Static one-file browser for the full WikiState v2 dataset (144 cases).

Each page = one case: gold chain table (green-framed) + the 4 questions with
gold answers highlighted + the persona's full raw session log with anchor
sentences highlighted. Prev/Next + dropdown + arrow-key navigation.

Usage: python scripts/build_dataset_viewer.py <out.html>
"""
import json, re, ast, html as H, sys, collections

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
        content = (content.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"'))
    return role, content

def esc_br(text):
    return H.escape(text).replace('\n', '<br>')

def chain_table(chain):
    rows = []
    for i, r in enumerate(chain, 1):
        rows.append(f"<tr><td class='rownum'>#{i}</td><td>{H.escape(r['date'])}</td>"
                    f"<td>{H.escape(r['value'])}</td>"
                    f"<td>“{H.escape(r['state_span'])}”</td></tr>")
    return ("<table><thead><tr><th>ROW</th><th>DATE</th><th>VALUE</th>"
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
        if hit:
            anchors_at.setdefault(hit, []).append(k)
    parts = ["<div class='scrollbox'>",
             "<div class='hd'>RAW MEMORY — full session log (scroll inside this box)</div>",
             (f"<div class='intro'>All {len(sessions)} sessions "
              f"({sessions[0]['date']} … {sessions[-1]['date']}); every user message verbatim, "
              f"assistant replies omitted. Chain anchors are <mark>highlighted</mark>.</div>")]
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

QTYPE_LABEL = {'change_count': 'change count', 'count_before': 'count before date',
               'first_vs_last': 'first vs last', 'longest_tenure': 'longest tenure'}

import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument('--data', required=True); _ap.add_argument('--questions', required=True); _ap.add_argument('--out', required=True); _ap.add_argument('--title', default='WikiState v2.5 dataset browser')
_a = _ap.parse_args()
full = json.load(open(_a.data, encoding='utf-8'))
qs = [json.loads(l) for l in open(_a.questions, encoding='utf-8')]
byuid = collections.defaultdict(list)
for q in qs:
    byuid[q['uid']].append(q)

cases = []
for e in full:
    qlist = sorted(byuid.get(e['uid'], []), key=lambda q: q['qtype'])
    cases.append({
        'uid': e['uid'], 'slot': e['slot'],
        'chain_html': chain_table(e['chain']),
        'raw_html': raw_log(e['sessions'], e['chain']),
        'questions': [{'qtype': QTYPE_LABEL.get(q['qtype'], q['qtype']),
                       'q': q['question'], 'gold': str(q['gold'])} for q in qlist],
    })

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;margin:0;background:#FAFAF7;color:#22262F}
.wrap{max-width:1100px;margin:0 auto;padding:14px 20px 60px}
.nav{display:flex;gap:10px;align-items:center;flex-wrap:wrap;position:sticky;top:0;
  background:#FAFAF7;padding:10px 0;border-bottom:2px solid #1F2A44;z-index:5}
.nav b{font-size:17px}
.nav button{background:#1F2A44;color:#fff;border:none;border-radius:7px;padding:7px 16px;
  font-size:14px;cursor:pointer}
.nav button:disabled{background:#C6C9D2}
.nav select{padding:6px;border-radius:7px;border:1px solid #C6C9D2;font-size:13px;max-width:340px}
.hint{color:#6B7280;font-size:12.5px;margin-left:auto}
.case-head{margin:16px 0 4px;font-size:15px;color:#6B7280}
.case-head b{color:#22262F;font-size:17px}
.slotpill{background:#E8EDF6;color:#1F2A44;border-radius:99px;padding:2px 12px;font-size:13px;font-weight:600;margin-left:8px}
.goldframe{border:2px solid #3E7A57;border-radius:10px;padding:10px 12px;margin:10px 0;background:#fff}
.goldlabel{color:#3E7A57;font-weight:700;font-size:13px;letter-spacing:.05em;margin-bottom:6px}
table{border-collapse:collapse;width:100%;background:#fff}
th{background:#e8edf6;text-align:left;padding:6px 10px;border:1px solid #c2cddd;font-size:13px}
td{padding:6px 10px;border:1px solid #c2cddd;font-size:13px;vertical-align:top}
tr:nth-child(even) td{background:#f6f8fc}
.rownum{color:#888;text-align:center;width:36px}
.qrow{display:flex;gap:10px;align-items:flex-start;background:#fff;border:1px solid #E4E1D5;
  border-radius:9px;padding:9px 12px;margin:7px 0}
.qtype{background:#8A6A2F;color:#fff;border-radius:5px;padding:2px 9px;font-size:11.5px;
  white-space:nowrap;margin-top:2px}
.qtext{flex:1;font-size:14px}
.gold{background:#EEF3E8;color:#3E7A57;border:1.5px solid #3E7A57;border-radius:7px;
  padding:2px 12px;font-weight:700;font-size:14px;white-space:nowrap}
.scrollbox{max-height:430px;overflow-y:auto;border:1px solid #e0d7c4;border-radius:6px;background:#fffdf8;margin-top:12px}
.hd{position:sticky;top:0;background:#f0e9dc;font-weight:700;padding:6px 10px;font-size:12.5px;border-bottom:1px solid #d8ccb4}
.intro{font-size:12.5px;color:#555;margin:6px 10px}
.sess{margin:12px 10px 2px;font-weight:600;font-size:12.5px;color:#7a5b2b}
.anch{background:#7a5b2b;color:#fff;border-radius:3px;padding:0 5px;font-size:11px;margin-left:6px}
p{margin:2px 10px 6px;font-size:12.5px;line-height:1.55}
mark{background:#ffe9a8;padding:0 2px}
</style></head><body><div class="wrap">
<div class="nav">
  <b>__TITLE__</b>
  <button id="prev">&larr; Prev</button>
  <select id="sel"></select>
  <button id="next">Next &rarr;</button>
  <span class="hint" id="pos"></span>
  <span class="hint">keys: &larr; / &rarr;</span>
</div>
<div id="case"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const CASES = JSON.parse(document.getElementById('data').textContent);
const sel = document.getElementById('sel');
CASES.forEach((c,i)=>{const o=document.createElement('option');o.value=i;
  o.textContent=(i+1)+'. '+c.uid+' ('+c.slot+')';sel.appendChild(o);});
let cur = Math.max(0, Math.min(CASES.length-1, (parseInt(location.hash.slice(1))||1)-1));
function render(){
  const c = CASES[cur];
  sel.value = cur;
  document.getElementById('pos').textContent = 'Case '+(cur+1)+' / '+CASES.length;
  document.getElementById('prev').disabled = cur===0;
  document.getElementById('next').disabled = cur===CASES.length-1;
  location.hash = cur+1;
  let qhtml = c.questions.map(q =>
    '<div class="qrow"><span class="qtype">'+q.qtype+'</span>'+
    '<span class="qtext">'+q.q.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</span>'+
    '<span class="gold">gold: '+String(q.gold).replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</span></div>').join('');
  document.getElementById('case').innerHTML =
    '<div class="case-head"><b>'+c.uid+'</b><span class="slotpill">'+c.slot+'</span></div>'+
    '<div class="goldframe"><div class="goldlabel">GOLD CHAIN — the answer backbone (all golds derive from these rows)</div>'+
    c.chain_html+'</div>'+
    '<div class="goldframe" style="border-color:#8A6A2F"><div class="goldlabel" style="color:#8A6A2F">QUESTIONS &amp; GOLD ANSWERS</div>'+
    qhtml+'</div>'+ c.raw_html;
  window.scrollTo(0,0);
}
document.getElementById('prev').onclick = ()=>{if(cur>0){cur--;render();}};
document.getElementById('next').onclick = ()=>{if(cur<CASES.length-1){cur++;render();}};
sel.onchange = ()=>{cur=parseInt(sel.value);render();};
document.addEventListener('keydown', e=>{
  if(e.key==='ArrowLeft'&&cur>0){cur--;render();}
  if(e.key==='ArrowRight'&&cur<CASES.length-1){cur++;render();}});
render();
</script></body></html>"""

out = _a.out
data = json.dumps(cases, ensure_ascii=False).replace('</', '<\\/')
open(out, 'w', encoding='utf-8').write(PAGE.replace('__TITLE__', _a.title).replace('__DATA__', data))
print(f"cases: {len(cases)} -> {out}  ({len(data)/1e6:.1f} MB data)")
