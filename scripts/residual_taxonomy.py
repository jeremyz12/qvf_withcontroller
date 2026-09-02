# -*- coding: utf-8 -*-
"""scripts/residual_taxonomy.py — 批 33-B:v2.4 头条(90.45)55 条残余失败归类。

预注册:results/opt_batch33_prereg.md §33-B(判据 B1:金标类比例 < 20%)。
上游语境:results/ladder_decontamination_20260902.md §二。

零 API。四刀,顺序与预注册一致:
  (a) 重建头条跑:results/b31_smoc_v22_full.jsonl <- v23 <- v24(后者按
      question_id 覆盖),断言 n=576 / acc 90.45 / 错 55;
  (b) 重渲染读者当时所见账目:scripts/repro_batch3.render_card_ledger
      × results/wt_cards_v44clean × data/wikistate_full_ALL_v24.json;
  (c) 写侧:账目链 vs 金链,四模式取自 scripts/card_quality_eval
      (zero_cards / missing_value / extra_value / wrong_value_or_order);
  (d) 读侧:冻结确定性执行器(complex_query_arm._select_pool_frozen + _chain,
      导入路径与 scripts/opt_batch18_diagnose.py 一致)按 gen_wsc_v2 的
      金标算式在账目链上复算四种题型;复算 == 金标 ⇒ 账目已含答案 ⇒ 读侧漏;
      复算 != 金标 ⇒ 账目不足以推出金标 ⇒ 写侧漏(子类取 (c) 的四模式)。
  (e) 读侧残渣 + 5 条 first_vs_last 导出人工看金标歧义/判官错(judge_reason 随行)。

选池口径说明(必读,与 card_quality_eval 的差异及理由):
  card_quality_eval.card_sequence 按 `slot_class == target_slot` 过滤,但
  results/wt_cards_v44clean 的 8313 条记录**全部没有 slot_class 字段**
  (普查:0/8313),该过滤在本店上退化为"全部零卡",不可用。故本脚本的
  账目链改由冻结生产路径 _select_pool_frozen(其无键回退支 = _slot_match
  槽位词重叠)+ _chain 产出 —— 这正是读者面前那本账目里"该槽位的状态序列",
  而**失败模式四分类函数 classify_failure 与金链规约 source_sequence 逐字
  复用 card_quality_eval**。脚本同时打印严格 slot_class 版本作为退化证据。

产物(全部新建,不写入任何既有卡店目录):
  results/b33B_merged_v24.jsonl     重建的 576 行头条跑
  results/b33B_ledgers.jsonl        144 个 uid 的重渲染账目全文
  results/b33B_writeside.jsonl      逐 uid 写侧明细(账目链 / 金链 / 四模式)
  results/b33B_taxonomy.jsonl       逐题归类(576 行,含 55 错的三大类标签)
  results/b33B_summary.json         全部聚合数字
  results/b33B_handinspect.md       (e) 的人工检视清单

用法:
  PYTHONUTF8=1 python scripts/residual_taxonomy.py
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# 账目视图必须是默认整本视图(读者当时的配置);否则渲染出的不是同一本账目。
assert os.environ.get("QVF_LEDGER_VIEW", "") == "", "QVF_LEDGER_VIEW 必须为空"

from repro_batch3 import render_card_ledger  # noqa: E402
from complex_query_arm import (  # noqa: E402
    _chain, _mem_dates, _norm, _pdate, _rec_date, _select_pool_frozen,
)
from card_quality_eval import (  # noqa: E402
    card_sequence as cqe_card_sequence,
    classify_failure,
    source_sequence,
)

CARDS = ROOT / "results/wt_cards_v44clean"
GOLD = ROOT / "data/wikistate_full_ALL_v24.json"
RUNS = ["results/b31_smoc_v22_full.jsonl",
        "results/b31_smoc_v23.jsonl",
        "results/b31_smoc_v24.jsonl"]
_TODAY_RE = re.compile(r"\(Today is ([0-9][0-9-]*)\.?\)")
_BEFORE_RE = re.compile(r"before (\d{4}-\d{2}-\d{2})")
# 金标平局判据:longest_tenure 头两名任期天数的相对差 ≤ 该百分比即判"金标平局"
# (整年粒度下两值同数,差异只由闰日/月首规约产生)。
GOLD_TIE_PCT = 1.0


# ── 统计小工具 ────────────────────────────────────────────────
def wilson(k: int, n: int, z: float = 1.96):
    """Wilson score 区间(百分比)。"""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 2), round(100 * max(0.0, c - h), 2),
            round(100 * min(1.0, c + h), 2))


def _num(s):
    m = re.search(r"-?\d+", str(s))
    return int(m.group()) if m else None


def _eqv(a: str, b: str) -> bool:
    """值级相等:归一后相等或互为子串(与 card_quality_eval.match_values 同精神)。"""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a


# ── 金标算式(逐字镜像 scripts/gen_wsc_v2.py)─────────────────
def tenure_winner(seq, today):
    """gen_wsc_v2.tenure_gold 的同式实现:同值多段累加,末段计至 today。

    seq = [(date, value)] 升序。返回 (winner_value, 是否唯一)。
    """
    per = Counter()
    for i, (start, val) in enumerate(seq):
        if start is None or start > today:
            break
        end = seq[i + 1][0] if i + 1 < len(seq) else today
        if end is None:
            end = today
        end = min(end, today)
        if end > start:
            per[val] += (end - start).days
    if not per:
        return None, False
    top = per.most_common(2)
    uniq = len(top) == 1 or top[0][1] > top[1][1]
    return top[0][0], uniq, dict(per)


def exec_answer(qtype: str, question: str, seq):
    """在给定状态序列 seq=[(date,value)] 上按金标算式复算答案。"""
    if not seq:
        return None, "empty_chain"
    m = _TODAY_RE.search(question or "")
    today = _pdate(m.group(1)) if m else None
    if qtype == "change_count":
        if today is None:
            return None, "no_today"
        k = sum(1 for d, _ in seq if d is not None and d <= today)
        return (k - 1 if k else None), f"k={k}"
    if qtype == "count_before":
        m2 = _BEFORE_RE.search(question or "")
        if not m2:
            return None, "no_before_date"
        qd = _pdate(m2.group(1))
        vals = [v for d, v in seq if d is not None and d < qd]
        return len(set(vals)), f"vals={sorted(set(vals))}"
    if qtype == "longest_tenure":
        if today is None:
            return None, "no_today"
        w, uniq, per = tenure_winner(seq, today)
        return w, f"uniq={uniq} days={per}"
    if qtype == "first_vs_last":
        return (seq[0][1], seq[-1][1]), ""
    return None, "unknown_qtype"


def tenure_gap(note: str):
    """从 exec_*_note 里取回 days=... 并算头两名的相对差 与 整年粒度是否并列。"""
    import ast
    m = re.search(r"days=(\{.*\})$", note or "")
    if not m:
        return None
    try:
        per = ast.literal_eval(m.group(1))
    except Exception:  # noqa: BLE001
        return None
    v = sorted(per.values(), reverse=True)
    if len(v) < 2:
        return None
    rel = (v[0] - v[1]) / v[0] if v[0] else 0.0
    same_year = round(v[0] / 365.25) == round(v[1] / 365.25)
    return dict(top=v[0], second=v[1], rel_gap=round(100 * rel, 3),
                tie_at_year_granularity=bool(same_year))


def exec_matches_gold(qtype, ex, gold_answer):
    if ex is None:
        return False
    if qtype in ("change_count", "count_before"):
        return _num(gold_answer) is not None and int(ex) == _num(gold_answer)
    if qtype == "longest_tenure":
        return _eqv(str(ex), str(gold_answer))
    if qtype == "first_vs_last":
        g = str(gold_answer)
        mf = re.search(r"first:\s*(.+?);\s*most recent:\s*(.+)$", g)
        if not mf:
            return False
        return _eqv(ex[0], mf.group(1)) and _eqv(ex[1], mf.group(2))
    return False


# ── 主流程 ────────────────────────────────────────────────────
def main():
    out_dir = ROOT / "results"

    # (a) 重建头条
    merged = {}
    prov = {}
    for f in RUNS:
        for line in open(ROOT / f, encoding="utf-8"):
            r = json.loads(line)
            merged[r["question_id"]] = r
            prov[r["question_id"]] = f
    rows = [merged[q] for q in sorted(merged)]
    n = len(rows)
    n_ok = sum(1 for r in rows if r["judge_correct"])
    acc = round(100 * n_ok / n, 2)
    assert n == 576 and acc == 90.45 and n - n_ok == 55, (n, acc, n - n_ok)
    with open(out_dir / "b33B_merged_v24.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({**r, "_source_file": prov[r["question_id"]]},
                                ensure_ascii=False) + "\n")

    entries = {e["uid"]: e for e in json.loads(GOLD.read_text(encoding="utf-8"))}

    # 复现性旁注:店 mtime vs 该 uid 存活行所属跑批的完成时间
    run_mtime = {f: (ROOT / f).stat().st_mtime for f in RUNS}
    drift = []
    for uid in sorted({r["uid"] for r in rows}):
        src = {prov[r["question_id"]] for r in rows if r["uid"] == uid}
        newest_run = max(run_mtime[s] for s in src)
        st = (CARDS / f"{uid}.json").stat().st_mtime
        if st > newest_run:
            drift.append(uid)

    # (b) 重渲染账目 + (c) 写侧
    ledgers = {}
    write_rows = {}
    cqe_strict_modes = Counter()
    for uid, e in entries.items():
        led = render_card_ledger(uid, e, cards_dir=str(CARDS))
        ledgers[uid] = led
        recs = json.loads((CARDS / f"{uid}.json").read_text(
            encoding="utf-8")).get("records", [])
        md = _mem_dates(e)
        slot = e.get("slot", "")
        # 一人称问题(全库四题型皆是),owner 字段本店不存在 -> 与题面无关
        pool = _select_pool_frozen(recs, slot, md, "my " + slot)
        ch = _chain(pool, md)
        led_seq_recs = [(_pdate(_rec_date(r, md)), r.get("value", "")) for r in ch]
        led_vals = [_norm(v) for _, v in led_seq_recs]
        gold_vals = source_sequence(e)
        gold_seq = [(_pdate(c.get("date", "")), c.get("value", ""))
                    for c in sorted(e.get("chain", []),
                                    key=lambda c: c.get("date", ""))]
        mode = classify_failure(led_vals, gold_vals)
        # 金链值是否在账目任意槽位上出现过(区分"没抽到"与"抽到但槽位错")
        all_vals = [r.get("value", "") for r in recs]
        cover = [any(_eqv(gv, av) for av in all_vals) for gv in gold_vals]
        # 退化证据:card_quality_eval 严格 slot_class 口径
        strict_seq, _ = cqe_card_sequence(
            json.loads((CARDS / f"{uid}.json").read_text(encoding="utf-8")),
            slot, md)
        cqe_strict_modes[classify_failure(strict_seq, gold_vals)] += 1
        write_rows[uid] = dict(
            uid=uid, slot=slot, pool_size=len(pool),
            ledger_chain=[(d.isoformat() if d else None, v)
                          for d, v in led_seq_recs],
            gold_chain=[(d.isoformat() if d else None, v) for d, v in gold_seq],
            ledger_vals=led_vals, gold_vals=gold_vals,
            write_mode=mode,
            gold_values_covered_any_slot=sum(cover), gold_values_n=len(gold_vals),
            n_records=len(recs), ledger_lines=len(led.splitlines()),
        )
        write_rows[uid]["_seq"] = led_seq_recs
        write_rows[uid]["_gold_seq"] = gold_seq

    with open(out_dir / "b33B_ledgers.jsonl", "w", encoding="utf-8") as fh:
        for uid in sorted(ledgers):
            fh.write(json.dumps({"uid": uid, "ledger": ledgers[uid]},
                                ensure_ascii=False) + "\n")
    with open(out_dir / "b33B_writeside.jsonl", "w", encoding="utf-8") as fh:
        for uid in sorted(write_rows):
            w = {k: v for k, v in write_rows[uid].items()
                 if not k.startswith("_")}
            fh.write(json.dumps(w, ensure_ascii=False) + "\n")

    # (d) 读侧复算(全 576,便于报"账目上限")
    tax = []
    for r in rows:
        uid, qt = r["uid"], r["question_type"]
        w = write_rows[uid]
        ex, note = exec_answer(qt, r["question"], w["_seq"])
        gx, gnote = exec_answer(qt, r["question"], w["_gold_seq"])
        ok_led = exec_matches_gold(qt, ex, r["gold_answer"])
        ok_gold = exec_matches_gold(qt, gx, r["gold_answer"])
        # ── 三大类判定 ───────────────────────────────────────
        # 读侧 = 冻结执行器能从"读者当时那本账目"复算出金标,且账目链未退化
        #        (链长 == 金链长)。退化保护:P39015 型 —— 账目只剩 1 个状态,
        #        执行器"唯一候选即胜出"偶然对上金标,实为写侧漏 5 个状态。
        # 写侧 = 其余(账目链本身不足以推出金标),子类取 card_quality_eval 四模式。
        # 金标类 = 读侧残渣中 longest_tenure 的**整年粒度并列**(见下,gap 判据)。
        gap = tenure_gap(gnote) if qt == "longest_tenure" else None
        cls = None
        if not r["judge_correct"]:
            degenerate = len(w["_seq"]) != len(w["_gold_seq"])
            if ok_led and not degenerate:
                cls = "read"
                if gap and gap["rel_gap"] <= GOLD_TIE_PCT:
                    cls = "gold"          # 金标平局:头两名任期相对差 ≤1%
            else:
                cls = "write"
        tax.append(dict(
            gold_tenure_gap=gap,
            question_id=r["question_id"], uid=uid, question_type=qt,
            source_file=prov[r["question_id"]],
            gold_answer=r["gold_answer"], answer=r["answer"],
            judge_correct=r["judge_correct"], judge_reason=r.get("judge_reason"),
            write_mode=w["write_mode"],
            exec_on_ledger=(list(ex) if isinstance(ex, tuple) else ex),
            exec_note=note,
            exec_on_goldchain=(list(gx) if isinstance(gx, tuple) else gx),
            exec_goldchain_note=gnote,
            exec_reproduces_gold_from_ledger=ok_led,
            exec_reproduces_gold_from_goldchain=ok_gold,
            top_class=cls,
        ))
    with open(out_dir / "b33B_taxonomy.jsonl", "w", encoding="utf-8") as fh:
        for t in tax:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")

    errs = [t for t in tax if not t["judge_correct"]]
    assert len(errs) == 55

    # 链聚集
    per_chain = Counter(t["uid"] for t in errs)
    dist = Counter(per_chain.values())
    p_err = 55 / 576
    # 每链 4 题的二项期望
    exp = {k: 144 * math.comb(4, k) * p_err ** k * (1 - p_err) ** (4 - k)
           for k in range(1, 5)}

    # 计数方向
    direction = Counter()
    for t in errs:
        if t["question_type"] in ("change_count", "count_before"):
            a, g = _num(t["answer"]), _num(t["gold_answer"])
            if a is None or g is None:
                direction["unparsed"] += 1
            elif a < g:
                direction["undercount"] += 1
            elif a > g:
                direction["overcount"] += 1
            else:
                direction["equal_but_judged_wrong"] += 1

    # 写侧再分:账目里"值根本没有" vs "值在场但槽位名/形态不合"
    write_split = Counter()
    for t in errs:
        if t["top_class"] != "write":
            continue
        w = write_rows[t["uid"]]
        full = (w["gold_values_covered_any_slot"] == w["gold_values_n"])
        write_split["write_B_值在场但选不出" if full else "write_A_值缺失"] += 1

    # 金标平局判据的基率对照(全部 144 道 longest_tenure)
    lt = [t for t in tax if t["question_type"] == "longest_tenure"]
    tie = [t for t in lt if t["gold_tenure_gap"]
           and t["gold_tenure_gap"]["rel_gap"] <= GOLD_TIE_PCT]
    non = [t for t in lt if t not in tie]
    tie_stats = dict(
        n_tie=len(tie), tie_wrong=sum(1 for t in tie if not t["judge_correct"]),
        n_nontie=len(non),
        nontie_wrong=sum(1 for t in non if not t["judge_correct"]))
    tie_stats["tie_err_rate"] = round(
        100 * tie_stats["tie_wrong"] / max(1, tie_stats["n_tie"]), 2)
    tie_stats["nontie_err_rate"] = round(
        100 * tie_stats["nontie_wrong"] / max(1, tie_stats["n_nontie"]), 2)
    def _fisher_right(a, b, c, d):
        """2x2 单侧(富集方向)Fisher 精确 p。"""
        n = a + b + c + d
        tot = 0.0
        for x in range(a, min(a + b, a + c) + 1):
            tot += (math.comb(a + b, x) * math.comb(c + d, a + c - x)
                    / math.comb(n, a + c))
        return tot
    tie_stats["fisher_p_one_sided"] = round(_fisher_right(
        tie_stats["tie_wrong"], tie_stats["n_tie"] - tie_stats["tie_wrong"],
        tie_stats["nontie_wrong"],
        tie_stats["n_nontie"] - tie_stats["nontie_wrong"]), 5)
    tie_stats["enrichment"] = round(
        tie_stats["tie_err_rate"] / max(1e-9, tie_stats["nontie_err_rate"]), 2)

    # 判官机械扫描:答案文本里金标是否其实在场(判官假阴性候选)
    judge_susp = []
    for t in errs:
        g, a = str(t["gold_answer"]), str(t["answer"])
        if t["question_type"] in ("change_count", "count_before"):
            nums = re.findall(r"-?\d+", a)
            if nums and set(nums) == {g}:
                judge_susp.append(t["question_id"])
        elif t["question_type"] == "longest_tenure":
            if _norm(g) in _norm(a):
                judge_susp.append(t["question_id"])
        else:
            mf = re.search(r"first:\s*(.+?);\s*most recent:\s*(.+)$", g)
            if mf and _norm(mf.group(1)) in _norm(a) \
                    and _norm(mf.group(2)) in _norm(a):
                judge_susp.append(t["question_id"])

    cls_cnt = Counter(t["top_class"] for t in errs)
    summary = dict(
        merged=dict(n=n, correct=n_ok, acc=acc, errors=n - n_ok,
                    by_type=dict(Counter(t["question_type"] for t in errs)),
                    provenance=dict(Counter(prov.values()))),
        store_drift_uids=drift,
        cqe_strict_slot_class_modes=dict(cqe_strict_modes),
        write_modes_all_144=dict(Counter(w["write_mode"]
                                         for w in write_rows.values())),
        chain_clustering=dict(n_error_chains=len(per_chain),
                              dist={str(k): v for k, v in sorted(dist.items())},
                              expected_binomial={str(k): round(v, 2)
                                                 for k, v in exp.items()}),
        count_direction=dict(direction),
        exec_upper_bound=dict(
            from_ledger=sum(1 for t in tax
                            if t["exec_reproduces_gold_from_ledger"]),
            from_goldchain=sum(1 for t in tax
                               if t["exec_reproduces_gold_from_goldchain"]),
            n=len(tax)),
        top_class=dict(cls_cnt),
        top_class_ci={k: dict(zip(("pct", "lo", "hi"), wilson(v, 55)))
                      for k, v in cls_cnt.items()},
        write_split=dict(write_split),
        subtable_5way={m: dict(Counter(t["top_class"] for t in errs
                                       if t["write_mode"] == m))
                       for m in ["correct", "zero_cards", "missing_value",
                                 "extra_value", "wrong_value_or_order"]},
        subtable_by_qtype={q: dict(Counter(t["top_class"] for t in errs
                                           if t["question_type"] == q))
                           for q in ["change_count", "count_before",
                                     "longest_tenure", "first_vs_last"]},
        gold_tie_basrate=tie_stats,
        judge_false_negative_candidates=judge_susp,
        B1_gold_share_pct=round(100 * cls_cnt.get("gold", 0) / 55, 2),
        B1_pass=bool(100 * cls_cnt.get("gold", 0) / 55 < 20),
    )
    (out_dir / "b33B_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # (e) 人工检视清单:读侧残渣 + 全部 first_vs_last 错
    insp = [t for t in errs
            if t["top_class"] in ("read", "gold")
            or t["question_type"] == "first_vs_last"]
    lines = ["# 33-B 人工检视清单(读侧残渣 + 全部 first_vs_last 错)", "",
             f"共 {len(insp)} 条。", ""]
    for t in insp:
        w = write_rows[t["uid"]]
        lines += [
            f"## {t['question_id']}  [{t['question_type']}] class={t['top_class']} write_mode={t['write_mode']}",
            f"- Q: {[r for r in rows if r['question_id']==t['question_id']][0]['question']}",
            f"- gold: {t['gold_answer']}",
            f"- answer: {str(t['answer'])[:400]}",
            f"- judge_reason: {str(t['judge_reason'])[:400]}",
            f"- exec_on_ledger: {t['exec_on_ledger']}  ({t['exec_note']})",
            f"- exec_on_goldchain: {t['exec_on_goldchain']}  ({t['exec_goldchain_note']})",
            f"- ledger_chain: {w['ledger_chain']}",
            f"- gold_chain: {w['gold_chain']}",
            "",
        ]
    (out_dir / "b33B_handinspect.md").write_text("\n".join(lines),
                                                 encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n--- 三大类(未做金标/判官改判前)---")
    for k, v in sorted(Counter(t["top_class"] for t in errs).items()):
        print(k, v, wilson(v, 55))
    print(f"\n人工检视清单 {len(insp)} 条 -> results/b33B_handinspect.md")


if __name__ == "__main__":
    main()
