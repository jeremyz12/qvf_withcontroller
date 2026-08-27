# -*- coding: utf-8 -*-
"""Three-rater design (2026-08-28 final): author does all 149; two seniors each
do one half plus a 20-item shared overlap (author-free kappa sample). Catch
trials spread so each senior meets 3 of the 5. Admin token and items reused
from the existing appdata.json.

Usage: python rateapp/gen_assignments_3p.py
"""
import json, secrets, random

rng = random.Random(20260828)
app = json.load(open(r'D:\ZZL_cluade\rateapp\appdata.json', encoding='utf-8'))
mp = json.load(open(r'D:\ZZL_cluade\data\labelstudio_chainproj_map.json', encoding='utf-8'))
items = app['items']
ids = [i['id'] for i in items]
catch = [i for i in ids if mp[i]['catch']]
normal = [i for i in ids if not mp[i]['catch']]
assert len(catch) == 5 and len(normal) == 144
rng.shuffle(normal)
rng.shuffle(catch)

S = normal[:19] + catch[:1]          # 20 shared
A = normal[19:82] + catch[1:3]       # 63 + 2 = 65
B = normal[82:] + catch[3:]          # 62 + 2 = 64
assert len(S) == 20 and len(A) == 65 and len(B) == 64
assert set(S) | set(A) | set(B) == set(ids) and not (set(S) & set(A)) and not (set(A) & set(B))

def mk(name, item_list):
    lst = item_list[:]
    rng.shuffle(lst)
    return {'token': secrets.token_urlsafe(12), 'name': name, 'items': lst}

raters = [mk('author', ids), mk('senior1', A + S), mk('senior2', B + S)]
app['raters'] = raters
json.dump(app, open(r'D:\ZZL_cluade\rateapp\appdata.json', 'w', encoding='utf-8'), ensure_ascii=False)

with open(r'D:\ZZL_cluade\rateapp\rater_links.txt', 'w', encoding='utf-8') as f:
    f.write(f"ADMIN dashboard:\nhttps://rate.wikistate.org/admin/{app['admin_token']}\n\n")
    for r in raters:
        f.write(f"{r['name']} ({len(r['items'])} items):\nhttps://rate.wikistate.org/r/{r['token']}\n\n")

for r in raters:
    nc = sum(1 for i in r['items'] if mp[i]['catch'])
    print(f"{r['name']}: {len(r['items'])} items, catch trials {nc}")
print("overlap (author-free kappa sample): 20 items shared by senior1 & senior2")
print("links -> rateapp/rater_links.txt")
