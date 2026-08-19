# -*- coding: utf-8 -*-
"""scripts/twin_leak_audit.py — 孪生批生成器泄漏 $0 机械审计 + 归档分层复算。

来源:持续优化循环 rank-2(首轮攻击面审计,2026-08-20)。零 API 调用。
判据(预先写入 study_logs/OPTIMIZATION_LOOP_STATE.md 队列节):
  干净层内 集合装配−直读 符号不变(≥0pp)且 替换批链尾错 ≥30% 且 过滤增益方向不变
    → 攻击大半消解,数字加"泄漏审计后稳健"注记;
  若 +2.66pp 在干净层翻负、或剔除含线索状态后链尾错 <25%
    → 主张3对应措辞降级,43% 诊断撤出对外口径。

审计两项:
  (a) 对侧措辞残留:替换批后续状态(chain[1:])的金会话文本含累积线索词;
      集合批后续状态含替换线索词。攻击声称 21/127 与 0/136。
  (b) 交叉值复述:任一会话文本提及 ≥2 个不同链值(计数/当前值题可单会话直答)。
      攻击声称 集合 18/47、替换 6/44(按条目)。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 攻击原文给出的累积线索词表(替换批中出现即异常)
CUM_CUES = re.compile(r"\b(also|another|as well|plus|and now)\b|\bstill\b", re.I)
# 替换线索词表(集合批中出现即异常;攻击未给表,此处自定义并如实声明)
REPL_CUES = re.compile(
    r"\b(instead|switch(ed|ing)?|no longer|replac(e|ed|ing)|swap(ped|ping)?|"
    r"quit|stopped|gave up|dropp(ed|ing)|moved on from|done with)\b", re.I)


def sess_text(s) -> str:
    return " ".join(
        t.get("content", "") if isinstance(t, dict) else str(t)
        for t in s.get("turns", []))


def audit_corpus(path: str, cue_pat: re.Pattern, cue_name: str):
    data = json.load(open(ROOT / path, encoding="utf-8"))
    res = {"corpus": path, "cue_set": cue_name, "entries": len(data),
           "later_states": 0, "cued_states": 0,
           "cued_entries": set(), "xval_entries": set(), "rows": []}
    for e in data:
        uid, chain = e["uid"], e.get("chain") or []
        # (a) 后续状态的金会话文本含对侧线索
        cued_here = []
        for i, st in enumerate(chain[1:], start=1):
            res["later_states"] += 1
            txt = " ".join(st.get("session_turns") or [])
            m = cue_pat.search(txt)
            if m:
                res["cued_states"] += 1
                cued_here.append((i, m.group(0)))
                res["cued_entries"].add(uid)
        # (b) 交叉值复述:任一会话提及 ≥2 个不同链值
        vals = [str(c.get("value") or "").strip() for c in chain]
        xval_sessions = []
        for s in e.get("sessions", []):
            low = sess_text(s).lower()
            hit = [v for v in vals if v and v.lower() in low]
            if len(set(hit)) >= 2:
                xval_sessions.append((s.get("chain_index"), sorted(set(hit))[:3]))
        if xval_sessions:
            res["xval_entries"].add(uid)
        res["rows"].append({"uid": uid, "cued_states": cued_here,
                            "xval_sessions": xval_sessions[:4]})
    return res


def _norm_qid(q: str) -> str:
    return q[:-6] if q.endswith("_query") else q


def load_rows(p: str) -> dict:
    out = {}
    for line in open(ROOT / p, encoding="utf-8"):
        r = json.loads(line)
        out[_norm_qid(r["question_id"])] = r
    return out


def uid_of(r: dict) -> str:
    return r.get("uid") or _norm_qid(r["question_id"]).split("_dim")[0]


def policy_set(setsem: dict, direct: dict) -> dict:
    """S2 策略重放:空证据(evidence_n==0)整题回退直读,其余用集合装配行。"""
    return {q: (direct[q] if not setsem[q].get("evidence_n") else setsem[q])
            for q in setsem if q in direct}


def policy_repl(wt_mf: dict, direct: dict) -> dict:
    """替换批组合策略重放:current 题型路由直读;卡片为空(notes_n==0)回退直读;其余 wt(过滤后)。"""
    out = {}
    for q, r in wt_mf.items():
        if q not in direct:
            continue
        qt = str(r.get("question_type") or "")
        if "current" in qt or "_dim1" in q:
            out[q] = direct[q]
        elif not r.get("notes_n"):
            out[q] = direct[q]
        else:
            out[q] = r
    return out


def stratify_rows(A: dict, B: dict, leaky_uids: set, label: str, names=("A", "B")):
    """同题配对:两个 {qid: row} 字典,按 uid 是否泄漏分层。返回表行。"""
    qids = sorted(set(A) & set(B))
    strata = {"全部": qids,
              "干净层": [q for q in qids if uid_of(A[q]) not in leaky_uids],
              "泄漏层": [q for q in qids if uid_of(A[q]) in leaky_uids]}
    lines = [f"### {label}", "",
             f"配对题数 {len(qids)}(A={names[0]},B={names[1]})", "",
             "| 层 | n | A | B | Δ(A−B) | b/c(A错B对/A对B错) |", "|---|---|---|---|---|---|"]
    verdicts = {}
    for name, qs in strata.items():
        if not qs:
            lines.append(f"| {name} | 0 | – | – | – | – |")
            continue
        a = sum(1 for q in qs if A[q].get("judge_correct")) / len(qs) * 100
        b = sum(1 for q in qs if B[q].get("judge_correct")) / len(qs) * 100
        cb = sum(1 for q in qs if not A[q].get("judge_correct") and B[q].get("judge_correct"))
        cc = sum(1 for q in qs if A[q].get("judge_correct") and not B[q].get("judge_correct"))
        lines.append(f"| {name} | {len(qs)} | {a:.2f}% | {b:.2f}% | {a-b:+.2f}pp | {cb}/{cc} |")
        verdicts[name] = a - b
    return lines, verdicts


def main() -> int:
    rep = audit_corpus("data/replchain_50.json", CUM_CUES, "累积线索(攻击原表)")
    st = audit_corpus("data/setchain_50.json", REPL_CUES, "替换线索(自定义表,见文件头)")
    # 集合批也扫累积线索占比作对照(其语义下累积词是正常的,仅供对称性参考)
    st_cum = audit_corpus("data/setchain_50.json", CUM_CUES, "累积线索")

    out = ["# 孪生批泄漏审计(2026-08-20,$0 机械)", "",
           "线索词表:累积 = also/another/as well/plus/and now/still;替换 = 见脚本头(自定义,如实声明)。", "",
           "## (a) 对侧措辞残留(后续状态的金会话)", "",
           "| 语料 | 对侧线索 | 后续状态 | 命中状态 | 命中率 | 涉事条目 | 攻击声称 |",
           "|---|---|---|---|---|---|---|",
           f"| 替换批 | 累积词 | {rep['later_states']} | {rep['cued_states']} | "
           f"{rep['cued_states']/rep['later_states']*100:.1f}% | {len(rep['cued_entries'])}/{rep['entries']} | 21/127 |",
           f"| 集合批 | 替换词 | {st['later_states']} | {st['cued_states']} | "
           f"{st['cued_states']/st['later_states']*100:.1f}% | {len(st['cued_entries'])}/{st['entries']} | 0/136 |",
           "",
           "## (b) 交叉值复述(任一会话提及 ≥2 个链值)", "",
           "| 语料 | 涉事条目 | 攻击声称 |", "|---|---|---|",
           f"| 集合批 | {len(st['xval_entries'])}/{st['entries']} | 18/47 |",
           f"| 替换批 | {len(rep['xval_entries'])}/{rep['entries']} | 6/44 |", ""]

    # ── 分层复算(75.0/78.8 是策略重放数字,此处重建策略后分层)──
    set_sem = load_rows("results/twinC_set_compile_setsem.jsonl")
    set_dir = load_rows("results/twinC_set_direct.jsonl")
    lines, v_set = stratify_rows(policy_set(set_sem, set_dir), set_dir,
                                 st["xval_entries"],
                                 "集合批:S2 策略(装配+空证据回退)vs 直读(泄漏=交叉值复述)",
                                 ("S2策略重放", "twinC_set_direct"))
    out += lines + [""]
    lines, _ = stratify_rows(set_sem, set_dir, st["xval_entries"],
                             "集合批:S1 纯装配(无回退)vs 直读(参考)",
                             ("twinC_set_compile_setsem", "twinC_set_direct"))
    out += lines + [""]
    wt_mf = load_rows("results/twinC_repl_wt_mf.jsonl")
    repl_dir = load_rows("results/twinC_repl_direct.jsonl")
    lines, v_rep = stratify_rows(policy_repl(wt_mf, repl_dir), repl_dir,
                                 rep["cued_entries"],
                                 "替换批:组合策略(过滤+题型路由+空回退)vs 直读(泄漏=累积线索残留)",
                                 ("组合策略重放", "twinC_repl_direct"))
    out += lines + [""]
    lines, v_mf = stratify_rows(load_rows("results/twinC_repl_compile_mf.jsonl"),
                                load_rows("results/twinC_repl_compile.jsonl"),
                                rep["cued_entries"],
                                "替换批:过滤后编译 vs 过滤前编译(增益方向)",
                                ("compile_mf", "compile"))
    out += lines + [""]

    # 链尾错误率分层(fidelity_gate_signals.json 的 tail_ok 标签)
    try:
        sigs = json.load(open(ROOT / "results/fidelity_gate_signals.json", encoding="utf-8"))
        lab = {u: s["tail_ok"] for u, s in sigs.get("repl", {}).items()
               if s.get("tail_ok") is not None}
        rows = []
        for name, uids in [("全部", set(lab)),
                           ("干净层", set(lab) - rep["cued_entries"]),
                           ("泄漏层", set(lab) & rep["cued_entries"])]:
            if not uids:
                continue
            err = sum(1 for u in uids if not lab[u]) / len(uids) * 100
            rows.append(f"| {name} | {len(uids)} | {err:.1f}% |")
        out += ["### 替换批链尾错误率(过滤前,tail_ok 标签)", "",
                "| 层 | 库数 | 链尾错误率 |", "|---|---|---|"] + rows + [""]
        clean_uids = set(lab) - rep["cued_entries"]
        tail_err_clean = (sum(1 for u in clean_uids if not lab[u]) / len(clean_uids) * 100
                          if clean_uids else float("nan"))
    except FileNotFoundError:
        out += ["(fidelity_gate_signals.json 缺失,链尾分层跳过)", ""]
        tail_err_clean = float("nan")

    # ── 判据 ──
    c1 = v_set.get("干净层", float("nan"))
    c2 = tail_err_clean
    c3 = v_mf.get("干净层", float("nan"))
    out += ["## 判据判定(判据先于本脚本写入循环状态文件)", "",
            f"- 干净层 集合装配−直读 = {c1:+.2f}pp(要求 ≥0 不翻负):{'✅' if c1 >= 0 else '❌ 翻负'}",
            f"- 干净层 链尾错误率 = {c2:.1f}%(≥30% 诊断保留;<25% 撤出口径):"
            f"{'✅ 保留' if c2 >= 30 else ('❌ 撤出' if c2 < 25 else '⚠️ 25–30 区间,降级为约数')}",
            f"- 干净层 过滤增益 = {c3:+.2f}pp(要求方向为正):{'✅' if c3 > 0 else '❌ 方向翻转'}",
            ""]
    # 逐条目明细(附录)
    out += ["## 附录:涉事条目", "",
            "替换批累积线索条目:" + ", ".join(sorted(rep["cued_entries"])) or "无", "",
            "集合批交叉值复述条目:" + ", ".join(sorted(st["xval_entries"])) or "无", "",
            f"(对照:集合批含累积词的后续状态 {st_cum['cued_states']}/{st_cum['later_states']}"
            f"——该侧语义下属正常表述,仅供词面对称性参考)", ""]

    dst = ROOT / "results/twin_leak_audit_20260820.md"
    dst.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print(f"\n写入 {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
