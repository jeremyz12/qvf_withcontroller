# -*- coding: utf-8 -*-
"""scripts/longest_tenure_regold.py — as-of-Today 约定重导 gold + 五臂归档重判。

预注册:results/longest_tenure_gold_prereg.md(提交 6447748,先于本文件运行)。
产物:results/longest_tenure_regold_20260820.json(新 gold 与变更清单)
      results/rejudge_lt_<arm>.jsonl(五臂重判行,不覆盖归档)
      控制台打印修复后计算段与 headline。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

ROOT = Path(r"D:\ZZL_cluade")
VOLS = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
        "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
ARMS = {
    "direct":  "results/wsc_direct_s5_all_b1_union.jsonl",
    "warned":  "results/wsc_warned_s5_all_b1.jsonl",
    "filter":  "results/wsc_s5_filter_only.jsonl",
    "usability": "results/wsc_s5_usability.jsonl",
    "compile": "results/wsc_s5_test_v42b1_union.jsonl",
}


def pd(s: str) -> date:
    y, m, d = (int(x) for x in str(s).split("-"))
    return date(y, m, d)


def regold() -> dict:
    """按 as-of-Today 约定重导每个 uid 的 longest_tenure gold。"""
    out = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            chain = e.get("chain") or []
            if len(chain) < 2:
                continue
            try:
                parsed = [pd(c["date"]) for c in chain]
            except Exception:
                continue
            values = [str(c.get("value") or "") for c in chain]
            today = parsed[-1]
            per: dict = {}
            for i in range(len(chain) - 1):
                per[values[i]] = per.get(values[i], 0) + (parsed[i + 1] - parsed[i]).days
            per[values[-1]] = per.get(values[-1], 0) + 0  # 末段 = Today − start_last
            # as-of-Today:末段天数
            per[values[-1]] += (today - parsed[-1]).days
            best = max(per.values())
            winners = [x for x, d in per.items() if d == best]
            out[e["uid"]] = {"winners": winners, "per_value": per,
                             "ambiguous": len(winners) != 1,
                             "gold_new": winners[0] if len(winners) == 1 else None}
    return out


def main() -> int:
    ng = regold()
    # 归档 longest_tenure 行(以编译臂为基准枚举 qid/旧 gold/问题)
    base = [json.loads(l) for l in open(ROOT / ARMS["compile"], encoding="utf-8")
            if '"longest_tenure"' in l]
    rows = {r["question_id"]: r for r in base}
    changed = kept = dropped = cur_ans = 0
    plan = {}
    for qid, r in rows.items():
        uid = r["uid"]
        g = ng.get(uid)
        if not g or g["ambiguous"]:
            dropped += 1
            continue
        old = str(r["gold_answer"])
        if g["gold_new"] != old:
            changed += 1
        else:
            kept += 1
        plan[qid] = {"uid": uid, "question": r["question"],
                     "gold_old": old, "gold_new": g["gold_new"]}
    # "当前值即答案"占比:新 gold == 链末值
    lastv = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            ch = e.get("chain") or []
            if ch:
                lastv[e["uid"]] = str(ch[-1].get("value") or "")
    cur_ans = sum(1 for q, p in plan.items() if p["gold_new"] == lastv.get(p["uid"]))
    summary = {"n_archived": len(rows), "survive": len(plan), "changed": changed,
               "kept": kept, "dropped_ambiguous": dropped,
               "gold_is_current_value": cur_ans}
    print(json.dumps(summary, ensure_ascii=False))
    (ROOT / "results/longest_tenure_regold_20260820.json").write_text(
        json.dumps({"summary": summary, "plan": plan}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # 五臂重判
    from qvf.judge import ClaudeJudge
    judge = ClaudeJudge()
    for arm, path in ARMS.items():
        arch = {json.loads(l)["question_id"]: json.loads(l)
                for l in open(ROOT / path, encoding="utf-8")}
        dst = ROOT / f"results/rejudge_lt_{arm}.jsonl"
        done = set()
        if dst.exists():
            done = {json.loads(l)["question_id"] for l in open(dst, encoding="utf-8")}
        with open(dst, "a", encoding="utf-8") as f:
            for qid, p in plan.items():
                if qid in done or qid not in arch:
                    continue
                a = arch[qid]
                v = judge.judge(p["question"], p["gold_new"], a.get("answer") or "",
                                "longest_tenure")
                f.write(json.dumps({"question_id": qid, "uid": p["uid"],
                                    "gold_new": p["gold_new"],
                                    "gold_old": p["gold_old"],
                                    "judge_correct": v.correct,
                                    "judge_reason": v.reason},
                                   ensure_ascii=False) + "\n")
                f.flush()
        n = sum(1 for _ in open(dst, encoding="utf-8"))
        print(f"[{arm}] rejudged -> {dst.name} ({n} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
