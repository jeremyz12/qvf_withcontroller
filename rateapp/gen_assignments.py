# -*- coding: utf-8 -*-
"""Generate rater assignments + app data for the self-hosted review site.

Design: N raters; every item gets exactly K=3 DISTINCT raters; loads balanced
(each rater ceil/floor of 149*3/N); per-rater item order shuffled. Deterministic
under --seed. Also emits one TEST rater (3 items) for smoke checks.

Usage: python gen_assignments.py --raters 8 [--seed 20260827]
Writes: appdata.json (server payload, gitignored), rater_links.txt (gitignored)
"""
import json, argparse, secrets, random, sys, collections

ap = argparse.ArgumentParser()
ap.add_argument('--raters', type=int, default=8)
ap.add_argument('--per-item', type=int, default=3)
ap.add_argument('--seed', type=int, default=20260827)
a = ap.parse_args()

rng = random.Random(a.seed)
tasks = json.load(open(r'D:\ZZL_cluade\data\labelstudio_tasks_chains_en.json', encoding='utf-8'))
items = [{'id': t['data']['item_id'], 'slot': t['data']['slot'],
          'chain_html': t['data']['chain_html'], 'raw_html': t['data']['raw_html']}
         for t in tasks]
instructions = open(r'D:\ZZL_cluade\data\labelstudio_instructions_chains_en.html', encoding='utf-8').read()

N, K = a.raters, a.per_item
total = len(items) * K
if N * ((total + N - 1) // N) < total or N < K:
    sys.exit('not enough raters')

# balanced greedy: for each item (random order), pick K distinct raters w/ lowest load
load = {i: 0 for i in range(N)}
assign = collections.defaultdict(list)
order = items[:]
rng.shuffle(order)
for it in order:
    picks = sorted(load, key=lambda r: (load[r], rng.random()))[:K]
    for r in picks:
        assign[r].append(it['id'])
        load[r] += 1
for r in assign:
    rng.shuffle(assign[r])

raters = []
for r in range(N):
    raters.append({'token': secrets.token_urlsafe(12), 'name': f'user{r+1}', 'items': assign[r]})
# TEST rater for smoke checks (first 3 items by id order; deleted after verification)
raters.append({'token': secrets.token_urlsafe(12), 'name': 'TEST', 'items': [i['id'] for i in items[:3]]})

admin_token = secrets.token_urlsafe(16)
json.dump({'items': items, 'raters': raters, 'admin_token': admin_token,
           'instructions': instructions},
          open(r'D:\ZZL_cluade\rateapp\appdata.json', 'w', encoding='utf-8'), ensure_ascii=False)

with open(r'D:\ZZL_cluade\rateapp\rater_links.txt', 'w', encoding='utf-8') as f:
    f.write(f"ADMIN dashboard:\nhttps://rate.wikistate.org/admin/{admin_token}\n\n")
    for r in raters:
        tag = ' (internal test link, not for distribution)' if r['name'] == 'TEST' else ''
        f.write(f"{r['name']} ({len(r['items'])} items){tag}:\nhttps://rate.wikistate.org/r/{r['token']}\n\n")

cnt = collections.Counter()
for r in raters[:N]:
    cnt[len(r['items'])] += 1
per_item = collections.Counter()
for r in raters[:N]:
    for i in r['items']:
        per_item[i] += 1
assert set(per_item.values()) == {K}, 'coverage violated'
assert all(len(set(r['items'])) == len(r['items']) for r in raters), 'duplicate item within rater'
print(f"raters {N}, items {len(items)}, per-item {K}, loads: {dict(cnt)}")
print("links -> rateapp/rater_links.txt  |  data -> rateapp/appdata.json")
