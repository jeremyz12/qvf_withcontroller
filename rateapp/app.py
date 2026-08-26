# -*- coding: utf-8 -*-
"""Self-hosted chain-verification review site (replaces Label Studio).

- Rater: /r/<token>  — fixed personal assignment, one item at a time, resume anytime.
- Admin: /admin/<token> — per-rater progress + global coverage. Read-only.
Answers are final (first submit wins). No accounts, no passwords: capability URLs.
"""
import json, os, sqlite3, time
from flask import Flask, g, request, redirect, abort, render_template_string, Response

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'rate.db')
DATA = os.path.join(HERE, 'appdata.json')
app = Flask(__name__)

def db():
    d = getattr(g, '_db', None)
    if d is None:
        d = g._db = sqlite3.connect(DB)
        d.row_factory = sqlite3.Row
    return d

@app.teardown_appcontext
def _close(_e):
    d = getattr(g, '_db', None)
    if d is not None:
        d.close()

def init():
    con = sqlite3.connect(DB)
    con.executescript('''
    CREATE TABLE IF NOT EXISTS raters(token TEXT PRIMARY KEY, name TEXT, items TEXT);
    CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, slot TEXT, chain_html TEXT, raw_html TEXT);
    CREATE TABLE IF NOT EXISTS answers(rater TEXT, item TEXT, verdict TEXT, note TEXT,
        ms INTEGER, ts REAL, PRIMARY KEY(rater, item));
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);''')
    if con.execute('SELECT 1 FROM items LIMIT 1').fetchone() is None:
        d = json.load(open(DATA, encoding='utf-8'))
        con.executemany('INSERT INTO items VALUES(?,?,?,?)',
                        [(i['id'], i['slot'], i['chain_html'], i['raw_html']) for i in d['items']])
        con.executemany('INSERT INTO raters VALUES(?,?,?)',
                        [(r['token'], r['name'], json.dumps(r['items'])) for r in d['raters']])
        con.execute('INSERT INTO meta VALUES(?,?)', ('admin', d['admin_token']))
        con.execute('INSERT INTO meta VALUES(?,?)', ('instructions', d['instructions']))
        con.commit()
    con.close()

init()

BASECSS = """
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;margin:0;background:#FAFAF7;color:#22262F}
.wrap{max-width:1080px;margin:0 auto;padding:18px 20px 60px}
.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.pill{background:#EEF3E8;color:#3E7A57;border-radius:99px;padding:3px 14px;font-size:13px;font-weight:600}
.bar{height:8px;background:#E4E1D5;border-radius:99px;overflow:hidden;margin:8px 0 18px}
.bar i{display:block;height:100%;background:#3E7A57}
h2{font-size:19px;margin:12px 0 6px}
.q{font-size:16.5px;font-weight:700;margin:14px 0 8px}
details{margin:8px 0;border:1px solid #E4E1D5;border-radius:8px;background:#fff;padding:8px 14px}
summary{cursor:pointer;font-weight:600;font-size:14px;color:#8A6A2F}
.opts{display:flex;gap:10px;margin:14px 0;flex-wrap:wrap}
.opts label{flex:1;min-width:180px;border:2px solid #E4E1D5;border-radius:10px;padding:12px 14px;
  cursor:pointer;background:#fff;font-size:15px;display:flex;gap:8px;align-items:center}
.opts input{transform:scale(1.3)}
.opts label.sel{border-color:#3E7A57;background:#EEF3E8}
textarea{width:100%;box-sizing:border-box;border:1px solid #E4E1D5;border-radius:8px;padding:10px;
  font-size:14px;font-family:inherit;min-height:64px}
button.go{background:#1F2A44;color:#fff;border:none;border-radius:8px;padding:12px 34px;
  font-size:16px;cursor:pointer;margin-top:12px}
button.go:hover{background:#2d3c60}
.note{font-size:13px;color:#6B7280;margin:6px 0}
.err{background:#FBEAE4;color:#A4552E;border-radius:8px;padding:10px 14px;margin:10px 0;font-size:14px}
table.adm{border-collapse:collapse;width:100%;background:#fff;font-size:14px}
table.adm th{background:#E8EDF6;text-align:left;padding:8px 12px;border:1px solid #C2CDDD}
table.adm td{padding:8px 12px;border:1px solid #C2CDDD}
"""

RATER_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>WikiState Review</title>
<style>{{basecss}}</style></head><body><div class="wrap">
<div class="top"><b>WikiState Chain Verification</b>
<span class="pill">{{done}} / {{total}} done &middot; {{name}}</span></div>
<div class="bar"><i style="width:{{pct}}%"></i></div>
{% if err %}<div class="err">{{err}}</div>{% endif %}
<details><summary>Instructions (read once before starting)</summary>{{instructions|safe}}</details>
<div class="q">Item {{done+1}} of {{total}} &nbsp;&middot;&nbsp; Chain ID: {{item.id}} &nbsp;&middot;&nbsp; Slot: {{item.slot}}</div>
<div class="q" style="font-weight:400">Does the state chain below correctly and completely represent the persona's
 &lsquo;{{item.slot}}&rsquo; history as stated in the raw session log?</div>
{{item.chain_html|safe}}
{{item.raw_html|safe}}
<div class="q">Check all four: (1) every anchor sentence appears in the log; (2) each DATE matches its
 session date; (3) each VALUE matches its sentence; (4) no state change in the log is missing from the chain.</div>
<form method="post" id="f">
<input type="hidden" name="item" value="{{item.id}}">
<input type="hidden" name="t0" id="t0" value="">
<div class="opts">
<label id="l1"><input type="radio" name="verdict" value="correct"> <b>1</b>&nbsp;Correct and complete</label>
<label id="l2"><input type="radio" name="verdict" value="errors"> <b>2</b>&nbsp;Has errors</label>
<label id="l3"><input type="radio" name="verdict" value="unsure"> <b>3</b>&nbsp;Unsure</label>
</div>
<div class="note">If &ldquo;Has errors&rdquo; or &ldquo;Unsure&rdquo;: say which row and what is wrong
 (e.g. &ldquo;row #2 date mismatch&rdquo;, &ldquo;a change around 1995 is missing&rdquo;).</div>
<textarea name="note" placeholder="note (required for options 2 and 3)"></textarea><br>
<button class="go" type="submit">Submit &rarr; next item</button>
<div class="note">Keyboard: 1 / 2 / 3 select an option. Answers are final &mdash; you cannot edit after submitting.
 Progress is saved on every submit; you can close this page and return via the same link.</div>
</form></div>
<script>
document.getElementById('t0').value = Date.now();
const ls = {1:'l1',2:'l2',3:'l3'};
function selstyle(){ for (const id of ['l1','l2','l3']) {
  const l = document.getElementById(id);
  l.classList.toggle('sel', l.querySelector('input').checked); } }
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA') return;
  if (ls[e.key]) { document.getElementById(ls[e.key]).querySelector('input').checked = true; selstyle(); }});
document.querySelectorAll('.opts input').forEach(i => i.addEventListener('change', selstyle));
document.getElementById('f').addEventListener('submit', e => {
  const v = document.querySelector('input[name=verdict]:checked');
  const note = document.querySelector('textarea[name=note]').value.trim();
  if (!v) { alert('Please pick 1, 2 or 3.'); e.preventDefault(); return; }
  if (v.value !== 'correct' && !note) { alert('Please add a short note for options 2/3.'); e.preventDefault(); }});
</script></body></html>"""

DONE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>WikiState Review</title>
<meta name="robots" content="noindex,nofollow"><style>{{basecss}}</style></head><body><div class="wrap">
<h2>All done &mdash; thank you! 🎉</h2>
<p>You completed all {{total}} items assigned to you ({{name}}). Your contribution will be
acknowledged in the paper. You can close this page.</p></div></body></html>"""

ADMIN_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Review Admin</title>
<meta name="robots" content="noindex,nofollow"><meta http-equiv="refresh" content="60">
<style>{{basecss}}</style></head><body><div class="wrap">
<h2>WikiState Review &mdash; Admin</h2>
<p class="note">Auto-refreshes every 60 s. Answers total: {{n_ans}} / {{n_slots}} slots.</p>
<h2>Raters</h2>
<table class="adm"><tr><th>Rater</th><th>Done / Assigned</th><th>Median sec/item</th><th>Last activity (UTC)</th></tr>
{% for r in raters %}<tr><td>{{r.name}}</td><td>{{r.done}} / {{r.total}}</td>
<td>{{r.med}}</td><td>{{r.last}}</td></tr>{% endfor %}</table>
<h2>Item coverage</h2>
<table class="adm"><tr><th>Answers per item</th><th># items</th></tr>
{% for k, v in cov %}<tr><td>{{k}}</td><td>{{v}}</td></tr>{% endfor %}</table>
</div></body></html>"""

@app.route('/robots.txt')
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype='text/plain')

@app.route('/')
def index():
    return Response("WikiState review site. Use your personal link.", mimetype='text/plain')

@app.route('/r/<token>', methods=['GET', 'POST'])
def rater(token):
    r = db().execute('SELECT * FROM raters WHERE token=?', (token,)).fetchone()
    if not r:
        abort(404)
    assigned = json.loads(r['items'])
    err = None
    if request.method == 'POST':
        item = request.form.get('item', '')
        verdict = request.form.get('verdict', '')
        note = (request.form.get('note') or '').strip()
        try:
            ms = max(0, int(time.time() * 1000) - int(request.form.get('t0') or 0))
        except ValueError:
            ms = 0
        if item in assigned and verdict in ('correct', 'errors', 'unsure'):
            if verdict != 'correct' and not note:
                err = 'A short note is required for options 2 and 3.'
            else:
                db().execute('INSERT OR IGNORE INTO answers VALUES(?,?,?,?,?,?)',
                             (token, item, verdict, note, ms, time.time()))
                db().commit()
                return redirect(request.path)
    done_rows = db().execute('SELECT item FROM answers WHERE rater=?', (token,)).fetchall()
    done_set = {x['item'] for x in done_rows}
    nxt = next((i for i in assigned if i not in done_set), None)
    ctx = dict(basecss=BASECSS, name=r['name'], total=len(assigned), done=len(done_set),
               pct=round(100 * len(done_set) / max(1, len(assigned))))
    if nxt is None:
        return render_template_string(DONE_PAGE, **ctx)
    it = db().execute('SELECT * FROM items WHERE id=?', (nxt,)).fetchone()
    instructions = db().execute('SELECT v FROM meta WHERE k=?', ('instructions',)).fetchone()['v']
    return render_template_string(RATER_PAGE, item=it, err=err, instructions=instructions, **ctx)

@app.route('/admin/<token>')
def admin(token):
    ok = db().execute('SELECT v FROM meta WHERE k=?', ('admin',)).fetchone()
    if not ok or ok['v'] != token:
        abort(404)
    raters = []
    n_slots = 0
    for r in db().execute('SELECT * FROM raters ORDER BY name').fetchall():
        assigned = json.loads(r['items'])
        n_slots += len(assigned)
        rows = db().execute('SELECT ms, ts FROM answers WHERE rater=? ORDER BY ms', (r['token'],)).fetchall()
        med = round(rows[len(rows) // 2]['ms'] / 1000) if rows else '—'
        last = time.strftime('%m-%d %H:%M', time.gmtime(max(x['ts'] for x in rows))) if rows else '—'
        raters.append(dict(name=r['name'], done=len(rows), total=len(assigned), med=med, last=last))
    n_ans = db().execute('SELECT COUNT(*) c FROM answers').fetchone()['c']
    per = {x['item']: x['c'] for x in
           db().execute('SELECT item, COUNT(*) c FROM answers GROUP BY item').fetchall()}
    n_items = db().execute('SELECT COUNT(*) c FROM items').fetchone()['c']
    cnt = {}
    for i in db().execute('SELECT id FROM items').fetchall():
        k = per.get(i['id'], 0)
        cnt[k] = cnt.get(k, 0) + 1
    cov = sorted(cnt.items())
    return render_template_string(ADMIN_PAGE, basecss=BASECSS, raters=raters,
                                  n_ans=n_ans, n_slots=n_slots, cov=cov)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8081)
