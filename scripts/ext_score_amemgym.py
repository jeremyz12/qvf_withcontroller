# -*- coding: utf-8 -*-
"""AMemGym 官方判分(exact-match)+ ClaudeJudge 并报 + 簇(persona)统计。

官方判据(src/amemgym/eval/metric.py::state_similarity, metric="accuracy",
逐字重建):被选选项的 state 列表必须与金状态
[period["state"][k] for k in required_info] **整体相等**,部分对得 0 分。
官方 harness 要求读者输出 {"answer": int};解析失败时 overall.py 回退到
random.randint(1, n_choices)(random.seed(42))。本脚本三口径并报:

  EM_official  = 官方口径:号码解析失败 -> 种子 42 均匀随机回退(与 overall.py 同)
  EM_strict    = 解析失败一律判错(保守下界)
  EM_rescue    = 号码解析失败时,若答案里**唯一**逐字命中某个选项文本则采信
                 (诊断口径,超出官方规则)
  judge        = 各臂内联 ClaudeJudge 逐行 judge_correct(gold = "N: <选项原文>")

号码解析分层(预注册,先中先用):
  T1 首个非空行以 "<数字>" 开头(含 "3" / "3:" / "3." / "3 —")
  T2 "option/choice/answer" 后接数字
  T3 全文里落在 [1, n_choices] 内的第一个独立整数
其余记 parse_fail。

用法:
  python scripts/ext_score_amemgym.py --probe data/external/amemgym_probe.jsonl \
      --arm smoc results/ext_amemgym_smoc.jsonl \
      --arm direct results/ext_amemgym_direct.jsonl \
      --out results/ext_amemgym_scored.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

T1 = re.compile(r"^\s*\**\s*(\d+)\s*(?:[:.)\]\-—]|\s|$)")
T2 = re.compile(r"(?:option|choice|answer|opción)\s*(?:number\s*)?[#:\s]*\**\s*(\d+)",
                re.I)
T3 = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def parse_choice(answer: str, n_choices: int):
    """returns (1-based choice, tier) or (None, "fail")"""
    a = (answer or "").strip()
    if not a:
        return None, "fail"
    first_line = next((l for l in a.splitlines() if l.strip()), "")
    m = T1.match(first_line)
    if m and 1 <= int(m.group(1)) <= n_choices:
        return int(m.group(1)), "T1"
    m = T2.search(a)
    if m and 1 <= int(m.group(1)) <= n_choices:
        return int(m.group(1)), "T2"
    for m in T3.finditer(a):
        v = int(m.group(1))
        if 1 <= v <= n_choices:
            return v, "T3"
    return None, "fail"


def rescue_by_text(answer: str, choices: list) -> int | None:
    """答案里唯一逐字命中某选项(取选项前 120 字符作指纹)时采信。"""
    a = (answer or "")
    hits = [i + 1 for i, c in enumerate(choices) if c[:120] and c[:120] in a]
    return hits[0] if len(hits) == 1 else None


# ---------------- 统计 ----------------
def mcnemar(pairs):
    """pairs: list of (a_correct, b_correct) -> (b_only, c_only, two-sided exact p)"""
    b = sum(1 for x, y in pairs if x and not y)   # a right, b wrong
    c = sum(1 for x, y in pairs if y and not x)
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i)
    p = min(1.0, 2.0 * p / (2 ** n))
    return b, c, p


def cluster_bootstrap(by_cluster, fn, n_boot=10000, seed=33):
    """by_cluster: {cluster: [row,...]}; fn(rows)->float. 返回 (点估, lo, hi)."""
    rng = random.Random(seed)
    keys = sorted(by_cluster)
    point = fn([r for k in keys for r in by_cluster[k]])
    vals = []
    for _ in range(n_boot):
        pick = [rng.choice(keys) for _ in keys]
        rows = [r for k in pick for r in by_cluster[k]]
        v = fn(rows)
        if v is not None:
            vals.append(v)
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[int(0.975 * len(vals)) - 1]
    return point, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--arm", nargs=2, action="append", metavar=("NAME", "PATH"),
                    required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    probe = {}
    for l in open(a.probe, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            probe[r["qid"]] = r

    arms = {}
    for name, path in a.arm:
        rows = {}
        rng = random.Random(42)          # 与 overall.py 的 random.seed(42) 同
        for l in open(path, encoding="utf-8"):
            if not l.strip():
                continue
            row = json.loads(l)
            qid = row["question_id"]
            p = probe[qid]
            meta = p["meta"]
            n_ch = meta["n_choices"]
            gold = meta["gold_choice_1based"]
            gold_state = meta["golden_state"]
            states = meta["choice_states"]
            pick, tier = parse_choice(row.get("answer", ""), n_ch)
            fail = pick is None
            pick_off = pick if pick is not None else rng.randint(1, n_ch)
            em_off = float(states[pick_off - 1] == gold_state)
            em_strict = 0.0 if fail else float(states[pick - 1] == gold_state)
            pr = pick
            if fail:
                choices_txt = [c for c in _choice_texts(p["question"], n_ch)]
                pr = rescue_by_text(row.get("answer", ""), choices_txt)
            em_resc = (float(states[pr - 1] == gold_state) if pr is not None
                       else em_off)
            rows[qid] = {
                "qid": qid, "uid": row["uid"],
                "period": meta["period_index"], "n_choices": n_ch,
                "gold_choice": gold, "pick": pick, "tier": tier,
                "parse_fail": fail,
                "em_official": em_off, "em_strict": em_strict,
                "em_rescue": em_resc,
                "judge": bool(row.get("judge_correct")),
                "in_tok": row.get("usage_input_tokens") or 0,
                "out_tok": row.get("usage_output_tokens") or 0,
                "latency": row.get("latency_s") or 0.0,
                "protocol_deviation": bool(row.get("protocol_deviation")),
            }
        arms[name] = rows
        print(f"[{name}] {len(rows)} rows from {path}")

    common = sorted(set.intersection(*[set(v) for v in arms.values()]))
    print(f"paired questions: {len(common)}")

    out = {"n_paired": len(common), "arms": {}, "paired": {}}
    for name, rows in arms.items():
        sub = [rows[q] for q in common]
        by_c = defaultdict(list)
        for r in sub:
            by_c[r["uid"]].append(r)
        rec = {}
        for metric in ("em_official", "em_strict", "em_rescue"):
            pt, lo, hi = cluster_bootstrap(
                by_c, lambda rs, m=metric: 100.0 * sum(r[m] for r in rs) / len(rs))
            rec[metric] = {"pct": round(pt, 2), "ci95": [round(lo, 2), round(hi, 2)]}
        pt, lo, hi = cluster_bootstrap(
            by_c, lambda rs: 100.0 * sum(r["judge"] for r in rs) / len(rs))
        rec["judge"] = {"pct": round(pt, 2), "ci95": [round(lo, 2), round(hi, 2)]}
        rec["parse_fail"] = round(100.0 * sum(r["parse_fail"] for r in sub) / len(sub), 2)
        rec["tiers"] = {t: sum(1 for r in sub if r["tier"] == t)
                        for t in ("T1", "T2", "T3", "fail")}
        rec["protocol_deviation"] = sum(r["protocol_deviation"] for r in sub)
        rec["mean_in_tok"] = round(statistics.mean(r["in_tok"] for r in sub), 1)
        rec["mean_out_tok"] = round(statistics.mean(r["out_tok"] for r in sub), 1)
        rec["mean_latency_s"] = round(statistics.mean(r["latency"] for r in sub), 2)
        rec["by_period"] = {
            str(p): round(100.0 * statistics.mean(
                [r["em_official"] for r in sub if r["period"] == p]), 1)
            for p in sorted({r["period"] for r in sub})}
        out["arms"][name] = rec
        print(f"[{name}] EM_official {rec['em_official']['pct']}% "
              f"CI{rec['em_official']['ci95']} | EM_strict {rec['em_strict']['pct']}% "
              f"| judge {rec['judge']['pct']}% | parse_fail {rec['parse_fail']}%")

    names = list(arms)
    if len(names) == 2:
        A, B = names
        for metric in ("em_official", "em_strict", "em_rescue", "judge"):
            pairs = [(bool(arms[B][q][metric]), bool(arms[A][q][metric]))
                     for q in common]
            b, c, p = mcnemar(pairs)
            by_c = defaultdict(list)
            for q in common:
                by_c[arms[A][q]["uid"]].append(
                    (float(arms[B][q][metric]) - float(arms[A][q][metric])))
            pt, lo, hi = cluster_bootstrap(
                by_c, lambda rs: 100.0 * sum(rs) / len(rs))
            out["paired"][metric] = {
                "delta_%s_minus_%s" % (B, A): round(pt, 2),
                "cluster_ci95": [round(lo, 2), round(hi, 2)],
                "mcnemar_b_%s_only" % B: b, "mcnemar_c_%s_only" % A: c,
                "mcnemar_p": round(p, 6),
            }
            print(f"[paired {metric}] {B}-{A} = {pt:+.2f}pp "
                  f"CI[{lo:+.2f},{hi:+.2f}] b={b} c={c} p={p:.4g}")

    # 官方 random 基线(仅采样的 600 题上重算 eval/random.py 的口径)
    rnd = []
    for q in common:
        meta = probe[q]["meta"]
        gs = meta["golden_state"]
        rnd.append(statistics.mean(
            [1.0 if s == gs else 0.0 for s in meta["choice_states"]]))
    out["official_random_baseline_pct"] = round(100.0 * statistics.mean(rnd), 2)
    print(f"official random baseline on these 600: "
          f"{out['official_random_baseline_pct']}%")

    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    for name, rows in arms.items():
        p = Path(a.out).with_suffix("").as_posix() + f".{name}.rows.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for q in common:
                f.write(json.dumps(rows[q], ensure_ascii=False) + "\n")
    print("wrote", a.out)


def _choice_texts(question: str, n: int):
    """从题面还原 n 个选项文本(题面里选项块形如 '1: ...' 逐行)。"""
    out = []
    body = question
    for i in range(1, n + 1):
        m = re.search(r"(?m)^%d: (.*)$" % i, body)
        out.append(m.group(1) if m else "")
    return out


if __name__ == "__main__":
    main()
