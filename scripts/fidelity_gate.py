# -*- coding: utf-8 -*-
"""scripts/fidelity_gate.py — 保真度门控断言:纯代码链体检 + 归档答案重放。

零新 LLM 调用:门的四个信号里三个是纯代码,一个用嵌入(text-embedding-3-small,
≈$0.01);"门控系统"的成绩由**归档答案重放**得出——门过用断言臂(编译臂)的已存
答案,门不过用展示臂(卡片臂/filter 臂)的已存答案,判分复用归档判官结果。

设计、信号、判据全部在 results/fidelity_gate_prereg.md 预注册(先于本文件运行提交)。
dev=替换孪生批(阈值只在此定,Youden);test=集合孪生批 + WikiState 聚合题集。
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

#: 宣告语言正则(预注册固定):状态转变/获得类动词
_DECL = re.compile(r"(start|switch|chang|mov(e|ed|ing)|new |now |sign|join|got |"
                   r"bought|adopt|began|upgrad|replac|picked up|added|learn)", re.I)


def _norm_qid(q: str) -> str:
    return q[:-6] if q.endswith("_query") else q


def load_rows(p: str) -> dict:
    return {_norm_qid(r["question_id"]): r
            for r in (json.loads(l) for l in open(ROOT / p, encoding="utf-8"))}


def embed_coherence(values, client, cache):
    """链内值两两余弦均值。值 <2 时返回 1.0(单值链无不一致可言)。"""
    vals = [v for v in dict.fromkeys(values) if v.strip()]
    if len(vals) < 2:
        return 1.0
    todo = [v for v in vals if v not in cache]
    if todo:
        resp = client.embeddings.create(model="text-embedding-3-small", input=todo)
        for v, d in zip(todo, resp.data):
            cache[v] = d.embedding
    import numpy as np
    m = np.array([cache[v] for v in vals])
    m = m / np.linalg.norm(m, axis=1, keepdims=True)
    sims = m @ m.T
    n = len(vals)
    return float((sims.sum() - n) / (n * (n - 1)))


def store_signals(uid, entry, cards_dir, arm_mod, client, ecache):
    """四信号 + 链尾标签。与执行器同一 _select_pool/_chain。"""
    md = arm_mod._mem_dates(entry)
    recs = arm_mod._load_records(uid)
    chain = arm_mod._chain(arm_mod._select_pool(recs, entry.get("slot") or "", md, ""), md)
    if not chain:
        return None
    spans = [str(r.get("source_span") or "") for r in chain]
    vals = [str(r.get("value") or "") for r in chain]
    # 记忆原文全串(逐字锚点合规检查)
    blob = "\n".join(str(t) for s in entry.get("sessions", []) for t in s.get("turns", []))
    s_decl = sum(1 for s in spans if _DECL.search(s)) / len(chain)
    s_date = sum(1 for r in chain if str(r.get("stated_date") or "").strip()) / len(chain)
    s_span = sum(1 for s in spans if s and s in blob) / len(chain)
    s_coher = embed_coherence(vals, client, ecache)
    score = s_decl + s_date + s_span + s_coher
    # 标签:链尾 vs 金链尾(双向包含)
    gold_vals = [str(c.get("value") or "") for c in (entry.get("chain") or [])]
    tail_ok = None
    if gold_vals and any(v.strip() for v in gold_vals):
        g, t = gold_vals[-1].lower(), vals[-1].lower()
        tail_ok = bool(g and t and (g in t or t in g))
    return {"uid": uid, "s_decl": s_decl, "s_date": s_date, "s_span": s_span,
            "s_coher": s_coher, "score": score, "tail_ok": tail_ok}


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def main() -> int:
    os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
    from openai import OpenAI
    client = OpenAI()
    ecache: dict = {}

    CORPORA = {
        "repl": {  # dev
            "data": "data/replchain_50.json", "cards": "results/wt_cards_twinC_repl",
            "assert": "results/twinC_repl_compile.jsonl",
            "display": "results/twinC_repl_wt.jsonl",
        },
        "set": {   # test
            "data": "data/setchain_50.json", "cards": "results/wt_cards_twinC_set",
            "assert": "results/twinC_set_compile.jsonl",
            "display": "results/twinC_set_wt.jsonl",
        },
        "wiki": {  # test(展示臂 = filter 模式,如实声明的不对称)
            "data": ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
                     "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"],
            "cards": "results/wt_cards_v42",
            "assert": "results/wsc_s5_test_v42b1_union.jsonl",
            "display": "results/wsc_s5_filter_only.jsonl",
        },
    }
    out = {}
    for tag, cfg in CORPORA.items():
        os.environ["QVF_CARDS_KEYED"] = cfg["cards"]
        for m in list(sys.modules):
            if m.startswith("scripts"):
                del sys.modules[m]
        import scripts.complex_query_arm as A
        files = cfg["data"] if isinstance(cfg["data"], list) else [cfg["data"]]
        entries = {}
        for f in files:
            for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
                entries.setdefault(e["uid"], e)
        arm_assert = load_rows(cfg["assert"])
        arm_display = load_rows(cfg["display"])
        qids = sorted(set(arm_assert) & set(arm_display))
        uids = sorted({q.split("_dim")[0] if "_dim" in q else arm_assert[q]["uid"]
                       for q in qids})
        sigs = {}
        for u in uids:
            if u not in entries:
                continue
            s = store_signals(u, entries[u], cfg["cards"], A, client, ecache)
            if s:
                sigs[u] = s
        out[tag] = {"sigs": sigs, "assert": arm_assert, "display": arm_display,
                    "qids": qids}
        lab = [s for s in sigs.values() if s["tail_ok"] is not None]
        print(f"[{tag}] 库 {len(sigs)},带标签 {len(lab)},"
              f"链尾对 {sum(s['tail_ok'] for s in lab)}/{len(lab)}")

    # ── dev(替换批)定阈值:Youden ──
    dev = [s for s in out["repl"]["sigs"].values() if s["tail_ok"] is not None]
    pos = sorted(s["score"] for s in dev if s["tail_ok"])
    neg = sorted(s["score"] for s in dev if not s["tail_ok"])
    best_tau, best_j = None, -1
    for tau in sorted(set(pos + neg)):
        tpr = sum(1 for p in pos if p >= tau) / len(pos)
        fpr = sum(1 for n in neg if n >= tau) / len(neg)
        if tpr - fpr > best_j:
            best_j, best_tau = tpr - fpr, tau
    print(f"\ndev(替换批)AUC = {auc(pos, neg):.3f};阈值 τ = {best_tau:.3f} "
          f"(Youden J={best_j:.3f}),冻结")

    # ── test:AUC + 重放 ──
    print(f"\n{'语料':8s} {'AUC':>6s} {'纯断言':>8s} {'纯展示':>8s} {'门控':>8s} "
          f"{'门过率':>7s}  判据")
    results = {}
    for tag in ("repl", "set", "wiki"):
        o = out[tag]
        lab = [s for s in o["sigs"].values() if s["tail_ok"] is not None]
        a = auc([s["score"] for s in lab if s["tail_ok"]],
                [s["score"] for s in lab if not s["tail_ok"]])
        ok = lambda m, q: bool(m[q].get("judge_correct"))
        qids = o["qids"]
        acc_a = sum(ok(o["assert"], q) for q in qids) / len(qids) * 100
        acc_d = sum(ok(o["display"], q) for q in qids) / len(qids) * 100
        gated = passed = 0
        for q in qids:
            u = q.split("_dim")[0] if "_dim" in q else o["assert"][q]["uid"]
            s = o["sigs"].get(u)
            use_assert = (s is None) or (s["score"] >= best_tau)
            passed += use_assert
            gated += ok(o["assert"] if use_assert else o["display"], q)
        acc_g = gated / len(qids) * 100
        results[tag] = (a, acc_a, acc_d, acc_g, passed / len(qids))
        note = ""
        if tag == "set":
            note = "C2 " + ("✅" if acc_g >= max(acc_a, acc_d) - 1 else "❌")
        if tag == "wiki":
            note = "C3 " + ("✅" if acc_g >= acc_a - 1.5 else "❌")
        print(f"  {tag:6s} {a:6.3f} {acc_a:7.2f}% {acc_d:7.2f}% {acc_g:7.2f}% "
              f"{passed / len(qids) * 100:6.1f}%  {note}")
    c1 = results["set"][0] >= 0.70 and results["wiki"][0] >= 0.70
    print(f"\nC1 门判别力(set/wiki AUC≥0.70): {'✅' if c1 else '❌'} "
          f"(set {results['set'][0]:.3f} / wiki {results['wiki'][0]:.3f})")
    emb_n = len(ecache)
    print(f"\n成本:嵌入 {emb_n} 个值 ≈ ${emb_n * 8 / 1e6 * 0.02:.4f};LLM 调用 0;判官调用 0")
    json.dump({t: {u: s for u, s in out[t]["sigs"].items()} for t in out},
              open(ROOT / "results/fidelity_gate_signals.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
