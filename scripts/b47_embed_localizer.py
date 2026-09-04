# -*- coding: utf-8 -*-
"""批 47-C:两阶段抽取的 Stage 1 —— 嵌入式候选定位器的锚句召回(写时、无题)。

对每个店:把全部用户轮次用 OpenAI text-embedding-3-small 嵌入;对四个槽位类各给
若干"状态开始"释义作查询,取每轮次对该类的最大余弦;每类取 top-k 轮次,四类取并集
作为 Stage 1 的候选集。指标:542 条金标锚句所在轮次落入候选集的比例(召回)与
候选集占全部轮次的比例(保留率)。零判官、零抽取;嵌入成本约 $0.03。

用法:PYTHONUTF8=1 python scripts/b47_embed_localizer.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")
from openai import OpenAI  # noqa: E402

ROOT = Path(r"D:\ZZL_cluade")
EMB_MODEL = "text-embedding-3-small"
CACHE = ROOT / "results" / "b47_emb_turns.npz"  # .gitignore: results/*_emb_*.npz

QUERIES = {
    "employer": [
        "I started a new job at a new employer today",
        "I officially joined an organisation as a researcher, lecturer or staff member",
        "As of today I work at a university, laboratory, company or institute",
        "I have taken up a post at a new institution",
    ],
    "position": [
        "I was appointed or elected to a new position, office or role",
        "I am now a member of parliament, a minister, a chair or a director",
        "I have started serving in a new post or title",
        "I became the head, president, mayor or governor",
    ],
    "team": [
        "I signed with a new team or club",
        "I have joined a new football, basketball or sports club",
        "I now play for a different team",
        "I transferred to another club this season",
    ],
    "residence": [
        "I moved to a new city, town or country",
        "I now live in a new home or apartment",
        "We relocated and settled into our new place",
        "As of this week my home address changed",
    ],
}
# 通用记忆的 Stage 1 查询集(批 49):四个金标类之外补 schema 其余类目与"泛化状态变更"线索。
# 用于检验两阶段抽取是否只对 WikiState 的四类特调(QVF_CARD_STAGE1_QUERIES=general)。
QUERIES_GENERAL = dict(QUERIES)
QUERIES_GENERAL.update({
    "device": ["I got a new phone, laptop, tablet or camera", "I switched to a different device or upgraded my gadget", "My new car, bike or vehicle arrived"],
    "location": ["I am currently travelling and staying somewhere else", "I am at a different place right now, away from home", "I'm visiting another city this week"],
    "relationship": ["I started or ended a relationship, got engaged, married or divorced", "My partner and I broke up", "I have a new partner now"],
    "provider": ["I switched my subscription, bank, insurer, phone plan or internet provider", "I cancelled a service and signed up with another company", "I changed my gym membership or streaming plan"],
    "health": ["My diet, medication or health situation changed", "I stopped eating something or started a new routine", "The doctor changed my treatment"],
    "habit": ["I no longer do what I used to do every day", "I picked up a new hobby or dropped an old one", "My daily routine or commute changed"],
    "education": ["I enrolled in a course, school or degree programme", "I graduated or left my studies", "I started learning something new formally"],
    "pet_family": ["We adopted a pet or a pet passed away", "A family member moved in or out", "We had a baby"],
    "finance": ["I bought or sold a house, car or a big item", "My salary, rent or loan situation changed", "I started saving or investing differently"],
    "generic_change": ["Update: things have changed since I last mentioned this", "Actually that is no longer the case, now it is different", "I used to, but these days I do something else", "As of now my situation is different from before", "I switched, changed, stopped or started something recently", "Correction to what I said earlier"],
})
KS = [3, 5, 8, 12, 20, 40]


def turn_text(t: str) -> str:
    try:
        d = ast.literal_eval(t)
        if isinstance(d, dict):
            return str(d.get("content", t))
    except Exception:  # noqa: BLE001
        m = re.search(r"'content':\s*(\"(.*)\"|'(.*)')\s*[,}]", t, re.S)
        if m:
            return m.group(2) if m.group(2) is not None else m.group(3)
    return t


def embed(client, texts, bs=256):
    out = []
    for i in range(0, len(texts), bs):
        chunk = [t[:6000] if t.strip() else "." for t in texts[i:i + bs]]
        r = client.embeddings.create(model=EMB_MODEL, input=chunk)
        out.extend([d.embedding for d in r.data])
    v = np.asarray(out, dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


def main():
    corpus = json.load(open(ROOT / "data" / "wikistate_full_ALL_v24.json", encoding="utf-8"))
    client = OpenAI()
    # 1) 收集用户轮次
    turns = []  # (uid, key, text)
    for e in corpus:
        for si, s in enumerate(e["sessions"]):
            for ti, t in enumerate(s["turns"]):
                if not t.startswith("{'role': 'assistant'"):  # 语料里用户轮多为纯文本,助手轮才带 dict 标记
                    turns.append((e["uid"], f"s{si}#r{ti}", turn_text(t), t))
    print(f"user turns: {len(turns)}")
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=True)
        assert int(z["n"]) == len(turns), "cache mismatch"
        V = z["V"]
    else:
        t0 = time.time(); V = embed(client, [t for _, _, t, _ in turns])
        np.savez(CACHE, V=V, n=len(turns)); print(f"embedded in {time.time()-t0:.0f}s")
    Q = {c: embed(client, qs) for c, qs in QUERIES.items()}
    idx_by_uid = {}
    for i, (uid, _k, _t, _raw) in enumerate(turns):
        idx_by_uid.setdefault(uid, []).append(i)
    # 2) 每店:各类分数 = 对该类各释义的最大余弦
    tot_rows = 0; rec = {k: 0 for k in KS}; kept = {k: 0 for k in KS}; tot_turns = 0
    rec_own = {k: 0 for k in KS}  # 只用金标槽位一类的查询(乐观上界)
    missed = []
    for e in corpus:
        ids = idx_by_uid.get(e["uid"], [])
        if not ids:
            continue
        M = V[ids]  # n x d
        scores = {c: (M @ Q[c].T).max(axis=1) for c in QUERIES}
        n = len(ids); tot_turns += n
        gslot = e["slot"].lower()
        # 金标锚句所在轮次(局部索引)
        anchors = []
        for row in e["chain"]:
            sp = row["state_span"]
            j = next((k for k, i in enumerate(ids) if sp in turns[i][3] or sp in turns[i][2]), None)
            if j is None:
                j = next((k for k, i in enumerate(ids) if sp[:60] in turns[i][3] or sp[:60] in turns[i][2]), None)
            anchors.append(j)
        tot_rows += len(anchors)
        for k in KS:
            cand = set()
            for c in QUERIES:
                top = np.argsort(-scores[c])[:k]
                cand.update(top.tolist())
            kept[k] += len(cand)
            own = set(np.argsort(-scores.get(gslot, scores["employer"]))[:k].tolist())
            for j in anchors:
                if j is not None and j in cand:
                    rec[k] += 1
                if j is not None and j in own:
                    rec_own[k] += 1
                if k == 40 and (j is None or j not in cand) and len(missed) < 10:
                    missed.append((gslot, turns[ids[j]][2][:100] if j is not None else "<anchor turn not found>"))
    print(f"gold rows {tot_rows}, user turns {tot_turns}")
    print("k | recall(4-class union) | kept share | recall(gold-class query only)")
    for k in KS:
        print(f"{k:3d} | {rec[k]/tot_rows:6.1%} | {kept[k]/tot_turns:6.1%} | {rec_own[k]/tot_rows:6.1%}")
    print("missed at k=40 (union):")
    for m in missed:
        print("  ", m)
    out = {"model": EMB_MODEL, "gold_rows": tot_rows, "user_turns": tot_turns,
           "recall_union": {k: rec[k] / tot_rows for k in KS}, "kept_share": {k: kept[k] / tot_turns for k in KS},
           "recall_gold_class": {k: rec_own[k] / tot_rows for k in KS}, "missed_k40": missed}
    (ROOT / "results" / "b47_embed_localizer.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
