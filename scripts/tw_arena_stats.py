# -*- coding: utf-8 -*-
"""33-G3 Temporal Wiki 外场统计:四臂准确率(总/分关系)、配对 McNemar
(= 项目冻结的精确双侧符号检验)、按实体簇的自助 95% CI、以及全口径 $/题。

统计三件套**直接 import 自 scripts/bootstrap_ci.py**(sign_test_p /
cluster_sign_counts / report / print_row),不复制一行,口径与全库一致
(SEED=20260803,N_BOOT=10000,簇 = 一个实体 uid)。

价格(list price,与 scripts/cost_usd_recompute.py、b1_run_p39.py 同表):
  claude-haiku-4-5 $1.00/$5.00 每 M tok(读者、建卡)
  claude-opus-5    $5.00/$25.00 每 M tok(ClaudeJudge)
  text-embedding-3-small $0.02/M tok(direct 臂检索;tiktoken 精确计数)

用法:PYTHONUTF8=1 python scripts/tw_arena_stats.py
"""
from __future__ import annotations

import collections
import glob
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from bootstrap_ci import report  # noqa: E402

P_H_IN, P_H_OUT = 1.00, 5.00
P_O_IN, P_O_OUT = 5.00, 25.00
P_EMBED = 0.02
SEED, N_BOOT = 20260803, 10000

ARMS = ["smoc", "direct", "fullplain", "closedbook"]
FILES = {a: ROOT / f"results/ext_temporalwiki_{a}.jsonl" for a in ARMS}
JUSE = {a: ROOT / f"results/ext_temporalwiki_judgeusage_{a}.jsonl" for a in ARMS}
DATA = ROOT / "data/external/temporalwiki_unified.json"
PROBE = ROOT / "data/external/temporalwiki_probe.jsonl"
CARDS = ROOT / "results/ext_cards_temporalwiki"


def load(a):
    rows = {}
    for l in open(FILES[a], encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            rows[r["question_id"]] = r
    return rows


def main() -> int:
    probe = {json.loads(l)["qid"]: json.loads(l)
             for l in open(PROBE, encoding="utf-8") if l.strip()}
    arms = {a: load(a) for a in ARMS}
    common = set.intersection(*[set(v) for v in arms.values()])
    qids = sorted(common)
    print(f"# 33-G3 Temporal Wiki — {len(qids)} 题四臂齐全 "
          f"(各臂落盘 {[len(arms[a]) for a in ARMS]})")
    uid_of = {q: probe[q]["uid"] for q in qids}
    rel_of = {q: probe[q]["meta"]["relation"] for q in qids}

    # ── 准确率 ────────────────────────────────────────────────
    print("\n## 总体准确率")
    print("| 臂 | 正确 | n | acc |")
    print("|---|---|---|---|")
    acc = {}
    for a in ARMS:
        ok = sum(1 for q in qids if arms[a][q]["judge_correct"])
        acc[a] = ok / len(qids) * 100
        print(f"| {a} | {ok} | {len(qids)} | {acc[a]:.1f} |")

    print("\n## 分关系准确率(n = 题数)")
    rels = sorted({rel_of[q] for q in qids},
                  key=lambda r: -sum(1 for q in qids if rel_of[q] == r))
    print("| relation | slot | n | " + " | ".join(ARMS) + " |")
    print("|---|---|---|" + "---|" * len(ARMS))
    for r in rels:
        sub = [q for q in qids if rel_of[q] == r]
        slot = probe[sub[0]]["meta"]["slot"]
        cells = [f"{sum(1 for q in sub if arms[a][q]['judge_correct'])/len(sub)*100:.1f}"
                 for a in ARMS]
        print(f"| {r} | {slot} | {len(sub)} | " + " | ".join(cells) + " |")

    # ── 按"问的是店内哪一档快照"分层(论文的近因陷阱轴)────────
    entries = {e["uid"]: e for e in json.loads(DATA.read_text(encoding="utf-8"))}
    def role(q):
        ys = [int(s["date"][:4]) for s in entries[uid_of[q]]["sessions"]]
        y = probe[q]["meta"]["as_of_year"]
        return "最早快照" if y == min(ys) else ("最新快照" if y == max(ys) else "中间快照")
    print("\n## 按提问年份在店内的位置分层(近因陷阱轴)")
    print("| 位置 | n | " + " | ".join(ARMS) + " |")
    print("|---|---|" + "---|" * len(ARMS))
    for k in ["最早快照", "中间快照", "最新快照"]:
        sub = [q for q in qids if role(q) == k]
        if not sub:
            continue
        cells = [f"{sum(1 for q in sub if arms[a][q]['judge_correct'])/len(sub)*100:.1f}"
                 for a in ARMS]
        print(f"| {k} | {len(sub)} | " + " | ".join(cells) + " |")

    # ── 配对检验 + 簇 CI ─────────────────────────────────────
    print("\n## 配对比较(精确双侧符号检验 = McNemar;簇 = 实体 uid)")
    pairs = [("smoc", "direct"), ("smoc", "fullplain"), ("smoc", "closedbook"),
             ("direct", "closedbook"), ("fullplain", "closedbook"),
             ("direct", "fullplain")]
    print("| 对比 | Δ(pp) | 簇 95% CI | b/c | McNemar p | 簇 W/L/T | 簇 p | 簇数 |")
    print("|---|---|---|---|---|---|---|---|")
    stats = {}
    for t, b in pairs:
        items = {q: (bool(arms[t][q]["judge_correct"]),
                     bool(arms[b][q]["judge_correct"])) for q in qids}
        clusters = collections.defaultdict(list)
        for q, pair in items.items():
            clusters[uid_of[q]].append(pair)
        r = report(f"{t} vs {b}", items, clusters, random.Random(SEED), N_BOOT)
        stats[(t, b)] = r
        print(f"| {t} − {b} | {r['delta']*100:+.1f} | "
              f"[{r['ci_lo']*100:+.1f}, {r['ci_hi']*100:+.1f}] | "
              f"{r['w']}/{r['l']} | {r['naive_p']:.3g} | "
              f"{r['cw']}/{r['cl']}/{r['ct']} | {r['cluster_p']:.3g} | "
              f"{r['n_clusters']} |")

    # ── 证据可得性(上界诊断)────────────────────────────────
    import re as _re
    _S = {"the", "of", "and", "for", "club", "football", "party", "national",
          "united", "city", "university", "company", "association", "team"}
    def _tk(s):
        return [t for t in _re.findall(r"[A-Za-zÀ-ɏ]{4,}", (s or "").lower())
                if t not in _S]
    sys.path.insert(0, str(ROOT / "scripts"))
    from repro_batch3 import render_card_ledger, render_transcript  # noqa: E402
    ent = {e["uid"]: e for e in json.loads(DATA.read_text(encoding="utf-8"))}
    tx_hit = led_hit = 0
    for q in qids:
        u = uid_of[q]
        w = set(_tk(str(probe[q]["gold"])))
        tx = render_transcript(ent[u]["sessions"]).lower()
        ld = render_card_ledger(u, ent[u], cards_dir=str(CARDS)).lower()
        if w and any(t in tx for t in w):
            tx_hit += 1
        if w and any(t in ld for t in w):
            led_hit += 1
    print(f"\n## 证据可得性(gold 标签词是否出现在读者可见文本里)\n"
          f"- 全文(fullplain/direct 底料):{tx_hit}/{len(qids)} "
          f"= {tx_hit/len(qids)*100:.1f}%\n"
          f"- 卡片账目(smoc 底料):{led_hit}/{len(qids)} "
          f"= {led_hit/len(qids)*100:.1f}%(写侧保真上界)")

    # ── 去污染子集(闭卷答错的题 = 参数知识给不出答案的那部分)────
    clean = [q for q in qids if not arms["closedbook"][q]["judge_correct"]]
    if clean:
        print(f"\n## 去污染子集(闭卷答错的 {len(clean)} 题)")
        print("| 臂 | acc |")
        print("|---|---|")
        for a in ARMS:
            ok = sum(1 for q in clean if arms[a][q]["judge_correct"])
            print(f"| {a} | {ok/len(clean)*100:.1f} ({ok}/{len(clean)}) |")
        items = {q: (bool(arms["smoc"][q]["judge_correct"]),
                     bool(arms["direct"][q]["judge_correct"])) for q in clean}
        cl = collections.defaultdict(list)
        for q, pr in items.items():
            cl[uid_of[q]].append(pr)
        r = report("clean smoc vs direct", items, cl, random.Random(SEED), N_BOOT)
        print(f"- smoc − direct = {r['delta']*100:+.1f}pp,簇 CI "
              f"[{r['ci_lo']*100:+.1f}, {r['ci_hi']*100:+.1f}],b/c={r['w']}/{r['l']},"
              f" McNemar p={r['naive_p']:.3g},簇 p={r['cluster_p']:.3g},"
              f"簇数 {r['n_clusters']}")

    # ── 污染判据 ─────────────────────────────────────────────
    print("\n## 污染对照(闭卷)")
    verdict = "CONTAMINATED" if acc["closedbook"] >= acc["direct"] else "NOT CONTAMINATED"
    print(f"- closedbook {acc['closedbook']:.1f} vs direct {acc['direct']:.1f} "
          f"→ **{verdict}**(判据:闭卷 ≥ direct 即标污染)")
    # 论文自带的参数化偏置诊断:闭卷答案是否落在"最近/最频繁答案"上
    for a in ARMS:
        hit_recent = hit_freq = n = 0
        for q in qids:
            m = probe[q]["meta"]
            ans = (arms[a][q].get("answer") or "").lower()
            mr, mf = m.get("most_recent_answer"), m.get("most_frequent_answer")
            gold = str(probe[q]["gold"])
            n += 1
            if mr and mr != gold and mr.lower() in ans:
                hit_recent += 1
            if mf and mf != gold and mf.lower() in ans:
                hit_freq += 1
        print(f"- {a}: 答案含**非本年**的 most_recent_answer {hit_recent}/{n} "
              f"({hit_recent/n*100:.1f}%)、most_frequent_answer {hit_freq}/{n} "
              f"({hit_freq/n*100:.1f}%)")

    # ── 成本 ────────────────────────────────────────────────
    print("\n## 成本(全部来自 usage token;list price)")
    cards = [json.loads(Path(f).read_text(encoding="utf-8"))
             for f in glob.glob(str(CARDS / "*.json"))]
    c_in = sum(c.get("usage_in", 0) for c in cards)
    c_out = sum(c.get("usage_out", 0) for c in cards)
    build_usd = c_in / 1e6 * P_H_IN + c_out / 1e6 * P_H_OUT
    print(f"- 建卡:{len(cards)} 店,in={c_in:,} out={c_out:,} → "
          f"${build_usd:.3f}(摊到 {len(qids)} 题 = ${build_usd/len(qids):.5f}/题)")

    # direct 臂嵌入 token(tiktoken 精确计数,cl100k_base)
    emb_usd = 0.0
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        entries = {e["uid"]: e for e in json.loads(DATA.read_text(encoding="utf-8"))}
        used = {uid_of[q] for q in qids}
        etok = sum(len(enc.encode(t)) for u in used
                   for s in entries[u]["sessions"] for t in s["turns"])
        qtok = sum(len(enc.encode(probe[q]["question"])) for q in qids)
        emb_usd = (etok + qtok) / 1e6 * P_EMBED
        print(f"- direct 嵌入:记忆 {etok:,} tok + 查询 {qtok:,} tok → ${emb_usd:.4f}")
    except Exception as e:  # noqa: BLE001
        print(f"- direct 嵌入:tiktoken 不可用({e}),未计入")

    juse = {}
    for a in ARMS:
        if JUSE[a].exists():
            juse[a] = [json.loads(l) for l in open(JUSE[a], encoding="utf-8")
                       if l.strip()]
    print("\n| 臂 | 读者 in/题 | 读者 out/题 | 判官 in/题 | 判官 out/题 | "
          "读+判 $/题 | 全口径 $/题 | 延迟 s/题 |")
    print("|---|---|---|---|---|---|---|---|")
    costs = {}
    for a in ARMS:
        rs = [arms[a][q] for q in qids]
        ri = sum(r.get("usage_input_tokens", 0) for r in rs) / len(rs)
        ro = sum(r.get("usage_output_tokens", 0) for r in rs) / len(rs)
        lat = sum(r.get("latency_s", 0) for r in rs) / len(rs)
        jl = juse.get(a, [])
        ji = sum(x["judge_in"] or 0 for x in jl) / max(1, len(jl))
        jo = sum(x["judge_out"] or 0 for x in jl) / max(1, len(jl))
        read_usd = ri / 1e6 * P_H_IN + ro / 1e6 * P_H_OUT
        judge_usd = ji / 1e6 * P_O_IN + jo / 1e6 * P_O_OUT
        full = read_usd + judge_usd
        if a == "smoc":
            full += build_usd / len(qids)
        if a == "direct":
            full += emb_usd / len(qids)
        costs[a] = (read_usd, judge_usd, full)
        print(f"| {a} | {ri:,.0f} | {ro:,.0f} | {ji:,.0f} | {jo:,.0f} | "
              f"${read_usd + judge_usd:.5f} | ${full:.5f} | {lat:.1f} |")
    total = sum((costs[a][0] + costs[a][1]) * len(qids) for a in ARMS) \
        + build_usd + emb_usd
    print(f"\n- **本轨实测总成本 ${total:.2f}**"
          f"(建卡 ${build_usd:.2f} + 四臂读者与判官 "
          f"${total - build_usd - emb_usd:.2f} + 嵌入 ${emb_usd:.3f})")

    # ── 协议偏差 / 空答自检 ───────────────────────────────────
    dev = sum(1 for q in qids if arms["smoc"][q].get("protocol_deviation"))
    empt = {a: sum(1 for q in qids if not (arms[a][q].get("answer") or "").strip())
            for a in ARMS}
    print(f"- smoc 协议偏差 {dev}/{len(qids)};空答 {empt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
