# -*- coding: utf-8 -*-
"""P④ WikiState 聚合题集 v2 生成器(预注册 opt_batch6_prereg P④,零 LLM)。
修三缺陷:①change_count 题面写死口径;②longest_tenure 末段计入至 Today
(消除"链尾恒不赢"捷径);③gold 分布平衡(锚点选择贪心压众数占比 ≤35%)。
店/链不动,只重出题。确定性:锚点候选枚举 + 贪心按 uid 排序,无随机数。
"""
from __future__ import annotations

import collections
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
VOLS = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
        "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
SLOT_WORD = {"employer": "employer", "position": "position",
             "team": "team", "residence": "residence"}

CC_NOTE = (" (Count only transitions between different values; the initial "
           "value does not count as a change.)")
LT_NOTE = (" (The segment you currently hold counts up to today.)")


def d(s):
    """Wikidata 年/月精度日期(-00-00 / -00)归一到区间起点。"""
    y, m, dd = (s[:10] + "-01-01")[:10].split("-")[:3]
    m = "01" if m == "00" else m
    dd = "01" if dd == "00" else dd
    return date(int(y), int(m), int(dd))


def load_chains():
    out = []
    seen = set()
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            if e["uid"] in seen:
                continue
            seen.add(e["uid"])
            ch = e.get("chain") or []
            if len(ch) >= 3 and all(c.get("date") for c in ch):
                out.append((e["uid"], e.get("slot", "attribute"), ch))
    return sorted(out)


def anchors(ch):
    """候选 Today 锚:各相邻转移窗口中点 + 链尾后 180/540 天。"""
    cand = []
    for i in range(1, len(ch)):
        a, b = d(ch[i - 1]["date"]), d(ch[i]["date"])
        if (b - a).days >= 2:
            cand.append((a + (b - a) / 2, i))  # 锚落在第 i 次转移之前
    tail = d(ch[-1]["date"])
    cand.append((tail + timedelta(days=180), len(ch)))
    cand.append((tail + timedelta(days=540), len(ch)))
    return cand


def tenure_gold(ch, today):
    """同值多段累加;末段计入至 today。返回 (value, 唯一?)。"""
    per = collections.Counter()
    for i, c in enumerate(ch):
        start = d(c["date"])
        if start > today:
            break
        end = d(ch[i + 1]["date"]) if i + 1 < len(ch) else today
        end = min(end, today)
        if end > start:
            per[c["value"]] += (end - start).days
    if not per:
        return None, False
    top = per.most_common(2)
    uniq = len(top) == 1 or top[0][1] > top[1][1]
    return top[0][0], uniq


def main():
    chains = load_chains()
    print(f"chains: {len(chains)}")
    hist_cc = collections.Counter()
    hist_cb = collections.Counter()
    lt_tail_hits = 0
    lt_n = 0
    rows = []
    for uid, slot, ch in chains:
        w = SLOT_WORD.get(slot, slot)
        cand = anchors(ch)
        # ① change_count:贪心选使全局 gold 直方图最平的锚
        best = None
        for today, k in cand:
            g = k - 1  # 至 today 已发生 k-1 次转移(链上第 i 条=第 i-1 次转移后)
            # k = 锚之前的链条数;转移数 = k-1
            if g < 1:
                continue
            key = (hist_cc[g], g)  # 先选当前计数最小的 gold
            if best is None or key < best[0]:
                best = (key, today, g)
        if best:
            _, today, g = best
            hist_cc[g] += 1
            rows.append({"uid": uid, "qid": f"{uid}_v2cc",
                         "qtype": "change_count",
                         "question": f"(Today is {today.isoformat()}.) How many"
                                     f" times did I change my {w}?" + CC_NOTE,
                         "gold": g})
        # ② count_before:同法,gold = 截止日前不同值数
        best = None
        for today, k in cand:
            vals = {ch[i]["value"] for i in range(min(k, len(ch)))}
            g = len(vals)
            key = (hist_cb[g], g)
            if best is None or key < best[0]:
                best = (key, today, g)
        if best:
            _, today, g = best
            hist_cb[g] += 1
            rows.append({"uid": uid, "qid": f"{uid}_v2cb",
                         "qtype": "count_before",
                         "question": f"How many different {w} values did I "
                                     f"have before {today.isoformat()}? "
                                     f"(strictly before that date)",
                         "gold": g})
        # ③ longest_tenure:末段计入;要求唯一最大;锚优先取能让链尾值
        #    有机会赢的(消除捷径),否则取第一个唯一解
        pick = None
        lt_cand = list(cand)
        # 计算型锚:让链尾值恰好反超所需的 Today(约 1/4 库启用,uid 哈希定)
        import hashlib
        if int(hashlib.sha256(uid.encode()).hexdigest(), 16) % 4 == 0:
            tail_start = d(ch[-1]["date"])
            per = collections.Counter()
            for i, c in enumerate(ch[:-1]):
                per[c["value"]] += (d(ch[i + 1]["date"]) - d(c["date"])).days
            prior_tail = per.get(ch[-1]["value"], 0)
            best_other = max((v for k2, v in per.items()
                              if k2 != ch[-1]["value"]), default=0)
            need = best_other - prior_tail + 30
            if 0 < need < 366 * 40:
                lt_cand.append((tail_start + timedelta(days=need), len(ch)))
        for today, k in sorted(lt_cand, key=lambda t: -t[0].toordinal()):
            gv, uniq = tenure_gold(ch, today)
            if gv is None or not uniq:
                continue
            if pick is None:
                pick = (today, gv)
            if gv == ch[-1]["value"]:
                pick = (today, gv)
                break
        if pick:
            today, gv = pick
            lt_n += 1
            lt_tail_hits += (gv == ch[-1]["value"])
            rows.append({"uid": uid, "qid": f"{uid}_v2lt",
                         "qtype": "longest_tenure",
                         "question": f"(Today is {today.isoformat()}.) Which "
                                     f"{w} did I hold the longest?" + LT_NOTE,
                         "gold": gv})
        # ④ first_vs_last(约定无缺陷,保留原式)
        rows.append({"uid": uid, "qid": f"{uid}_v2fl",
                     "qtype": "first_vs_last",
                     "question": f"(Today is {(d(ch[-1]['date']) + timedelta(days=180)).isoformat()}.)"
                                 f" What was my first {w}, and what is my most"
                                 f" recent one?",
                     "gold": f"first: {ch[0]['value']}; most recent: "
                             f"{ch[-1]['value']}"})
    out = ROOT / "data/wsc_s5_v2.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # 分布报告(预注册判据)
    def top_share(h):
        tot = sum(h.values())
        return max(h.values()) / tot * 100 if tot else 0
    rep = {
        "n_questions": len(rows),
        "change_count_gold_hist": dict(sorted(hist_cc.items())),
        "change_count_mode_share": round(top_share(hist_cc), 1),
        "count_before_gold_hist": dict(sorted(hist_cb.items())),
        "count_before_mode_share": round(top_share(hist_cb), 1),
        "longest_tenure_tail_share": round(lt_tail_hits / max(1, lt_n) * 100, 1),
        "criteria": {
            "mode_share_le_35": top_share(hist_cc) <= 35 and top_share(hist_cb) <= 35,
            "tail_share_gt_10": lt_tail_hits / max(1, lt_n) * 100 > 10,
        },
    }
    (ROOT / "data/wsc_s8_v2.meta.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
