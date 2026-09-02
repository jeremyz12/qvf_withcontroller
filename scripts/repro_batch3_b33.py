# -*- coding: utf-8 -*-
"""scripts/repro_batch3.py — StateMemWrapper 及其匹配对照 × WikiState 聚合题。
预注册:results/repro_batch3_prereg.md(先于本文件运行提交)。
协议镜像 repro_batch2:同 15 库抽样、同读者(haiku-4-5)、同判官。
提示词逐字取自 arXiv 2608.19652 附录 F.1(PDF 抽取,2026-08-23)。
用法: python repro_batch3.py --system smw|smwctrl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic
from qvf.judge import ClaudeJudge
from repro_batch2 import sample_stores, VOLS, ROOT  # 同一抽样与数据卷

READER_MODEL = os.environ.get("QVF_READER_MODEL", "claude-haiku-4-5")
# 批16 读者升级用:默认值即冻结配置;覆盖时逐行 usage 照记,截断自查见 prereg。
READER_MAXTOK = int(os.environ.get("QVF_READER_MAXTOK", "800"))
TAIL_GUARD = 400_000  # 字符,照抄 F.3

# ── 附录 F.1 逐字提示词 ──────────────────────────────────────
SMW_PROMPT = """You are answering a question about a long conversation using state tracing.

## Question: {question}

## Conversation transcript: {transcript}

Work in TWO sections, in order:

## Section 1 -- State trace (under 250 words):
List, in chronological order, every turn that establishes, updates, or supersedes the entities the question asks about ([turn N] speaker: what changed). Include standing rules that govern the decision AND the most recent stated value of every input those rules apply to (amounts, quantities, dates, thresholds) -- even if mentioned only once or in passing; scan for them before concluding an input is unknown. Note derived values whose inputs later changed. End with the current operative value of each relevant entity. Commit to the trace BEFORE answering.

## Section 2 -- Resolution and answer:
Apply, in order:
(1) later supersedes earlier;
(2) standing rules outrank past one-off instances -- apply the rule to CURRENT inputs;
(3) recompute derived values from current inputs, never reuse stale cached numbers;
(4) a fact is only retired if actually superseded or expired.
End with exactly one final line:
ANSWER: <the specific value or decision the question asks for>"""

# 批 14 缓存排布确认变体(QVF_PROMPT_QLAST=1):同一 F.1 措辞,仅把
# Question 节移到 transcript 之后(稳定前缀在前,动态题面在后)。默认 0
# 时不选用,SMW_PROMPT 逐字节不变。
SMW_PROMPT_QLAST = """You are answering a question about a long conversation using state tracing.

## Conversation transcript: {transcript}

## Question: {question}

Work in TWO sections, in order:

## Section 1 -- State trace (under 250 words):
List, in chronological order, every turn that establishes, updates, or supersedes the entities the question asks about ([turn N] speaker: what changed). Include standing rules that govern the decision AND the most recent stated value of every input those rules apply to (amounts, quantities, dates, thresholds) -- even if mentioned only once or in passing; scan for them before concluding an input is unknown. Note derived values whose inputs later changed. End with the current operative value of each relevant entity. Commit to the trace BEFORE answering.

## Section 2 -- Resolution and answer:
Apply, in order:
(1) later supersedes earlier;
(2) standing rules outrank past one-off instances -- apply the rule to CURRENT inputs;
(3) recompute derived values from current inputs, never reuse stale cached numbers;
(4) a fact is only retired if actually superseded or expired.
End with exactly one final line:
ANSWER: <the specific value or decision the question asks for>"""

PLAIN_PROMPT = """Answer the question based on the conversation transcript. Reply with only the answer.

## Question: {question}

## Conversation transcript: {transcript}"""

CTRL_PROMPT = """You are answering a question about a long conversation.

## Question: {question}

## Conversation transcript: {transcript}

Work in TWO sections, in order:

## Section 1 -- Relevant information (under 250 words):
Summarize the information in the conversation that is relevant to the question. Commit to this summary BEFORE answering.

## Section 2 -- Answer:
End with exactly one final line:
ANSWER: <the specific value or decision the question asks for>"""


def render_transcript(sessions, shuffle_uid: str = "") -> str:
    """全部会话按日期排序,轮次全局连续编号;会话间插日期行(与其他臂的
    日期可得性对齐);400k 字符尾部截断照抄 F.3(WikiState 远不触发)。
    shuffle_uid 非空时:会话呈现顺序按 SHA-256(uid+date) 确定性乱序
    (与 11.8 乱序对照同法),日期行原样保留。"""
    import hashlib
    if shuffle_uid:
        key = lambda x: hashlib.sha256(  # noqa: E731
            (shuffle_uid + x.get("date", "")).encode()).hexdigest()
    else:
        key = lambda x: x.get("date", "")  # noqa: E731
    lines = []
    n = 0
    for s in sorted(sessions, key=key):
        lines.append(f"--- session date: {s.get('date', 'undated')} ---")
        for t in s.get("turns", []):
            n += 1
            txt = str(t)
            try:  # turns 是字符串化的 {'role':..,'content':..}
                d = eval(txt, {"__builtins__": {}})  # noqa: S307 受控数据
                txt = f"{d.get('role', '?')}: {d.get('content', '')}"
            except Exception:  # noqa: BLE001
                pass
            lines.append(f"[turn {n}] {txt}")
    out = "\n".join(lines)
    return out[-TAIL_GUARD:] if len(out) > TAIL_GUARD else out


def render_card_ledger(uid: str, entry: dict, cards_dir: str = "",
                       shuffle: bool = False) -> str:
    """smoc 臂:卡片账目替代原文 transcript。日期经 _mem_dates 映射
    (与执行器同口径);按日期排序,格式见 opt_batch1_prereg。"""
    import hashlib
    from complex_query_arm import _mem_dates
    base = cards_dir or r"D:\ZZL_cluade/results/wt_cards_v42"
    cards_p = Path(base) / f"{uid}.json"
    recs = json.loads(cards_p.read_text(encoding="utf-8")).get("records", [])
    md = _mem_dates(entry)
    rows = []
    for r in recs:
        d = r.get("stated_date") or md.get(r.get("source_memory_id", ""), "")
        rows.append((d or "9999", r))
    if shuffle:  # 乱序判别臂:条目顺序打乱,日期字段原样保留
        rows.sort(key=lambda x: hashlib.sha256(
            (uid + str(x[1].get("record_id", ""))).encode()).hexdigest())
    else:
        rows.sort(key=lambda x: x[0])
    # 批14 视图门控(QVF_LEDGER_VIEW= ''|slot|slim;默认空=原整本视图,零改动)。
    # 语义逐字镜像批13抽样脚本 ledger_slim_probe.render:slot/slot_class 子串匹配,
    # 命中 <2 行回退整本;其余属性折叠为单行索引。乱序臂不适用。
    view = "" if shuffle else os.environ.get("QVF_LEDGER_VIEW", "")
    if view in ("slot", "slim"):
        s = (entry.get("slot") or "").lower()
        hit = lambda r: (s in (r.get("slot_class") or "").lower()  # noqa: E731
                         or s in (r.get("slot") or "").lower())
        picked = [(d, r) for d, r in rows if hit(r)]
        if len(picked) >= 2:
            rest = [(d, r) for d, r in rows if not hit(r)]
            lines = []
            for n, (d, r) in enumerate(picked, 1):
                date = d if d != "9999" else "undated"
                if view == "slim":
                    lines.append(f'[entry {n}] {date} | '
                                 f'{r.get("slot", "?")}: {r.get("value", "?")}')
                else:
                    span = (r.get("source_span") or "")[:120]
                    lines.append(f'[entry {n}] {date} | {r.get("slot", "?")}: '
                                 f'{r.get("value", "?")} — "{span}"')
            if rest:
                from collections import Counter
                cnt = Counter((r.get("slot") or "?") for _, r in rest)
                lines.append("[other attributes on file, collapsed: "
                             + ", ".join(f"{k}({v})" for k, v in cnt.most_common())
                             + "]")
            return "\n".join(lines)
        print(f"[{uid}] view={view}: <2 slot rows, fallback to full ledger",
              flush=True)
    lines = []
    for n, (d, r) in enumerate(rows, 1):
        span = (r.get("source_span") or "")[:120]
        lines.append(f'[entry {n}] {d if d != "9999" else "undated"} | '
                     f'{r.get("slot", "?")}: {r.get("value", "?")} — "{span}"')
    return "\n".join(lines)


def render_ledger_plus(uid: str, entry: dict, t_q: str,
                       roles: bool = False, calc: bool = False,
                       cards_dir: str = "") -> str:
    """批 9 账目增强:在 smoc 账目上机械注入认证角色(算法4)与/或
    槽位汇总块(算法5,断言臂设计)。t_q = 题面日期;纯代码零 LLM。"""
    from complex_query_arm import _mem_dates
    from datetime import date as _date

    def pd(x):
        import re as _re
        m0 = _re.search(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(x))
        if not m0:
            return None
        y = int(m0.group(1))
        mo = int(m0.group(2) or 1) or 1
        dd = int(m0.group(3) or 1) or 1
        try:
            return _date(y, min(max(mo, 1), 12), min(max(dd, 1), 28))
        except ValueError:
            return None
    base = cards_dir or r"D:\ZZL_cluade/results/wt_cards_v42"
    recs = json.loads((Path(base) / f"{uid}.json").read_text(
        encoding="utf-8")).get("records", [])
    md = _mem_dates(entry)
    rows = []
    for r in recs:
        d = (r.get("stated_date") or "").strip() or             md.get(r.get("source_memory_id", ""), "")
        if d:
            rows.append((d, r))
    rows.sort(key=lambda x: x[0])
    tq = pd(t_q) or _date(2100, 1, 1)
    # 槽位组:(owner, slot_class or slot)
    groups: dict = {}
    for i, (d, r) in enumerate(rows):
        key = ((r.get("owner") or ""), r.get("slot_class") or r.get("slot") or "")
        groups.setdefault(key, []).append(i)
    role_of = {}
    if roles:
        for key, idxs in groups.items():
            seq = [(rows[i][0], i) for i in idxs]
            seq.sort()
            for j, (d, i) in enumerate(seq):
                di = pd(d)
                dnext = pd(seq[j + 1][0]) if j + 1 < len(seq) else None
                if di and di > tq:
                    role_of[i] = "not-yet-active"
                elif dnext and dnext <= tq:
                    role_of[i] = "superseded"
                else:
                    role_of[i] = "current"
    lines = []
    for n, (i, (d, r)) in enumerate(zip(range(len(rows)), rows), 1):
        span = (r.get("source_span") or "")[:120]
        tail = f'  [role: {role_of.get(i, "?")}]' if roles else ""
        lines.append(f'[entry {n}] {d} | {r.get("slot", "?")}: '
                     f'{r.get("value", "?")} — "{span}"{tail}')
    if calc:
        lines.append("")
        lines.append("[computed slot summaries — derived by code from the "
                     "entries above, as of " + t_q + "]")
        for key, idxs in sorted(groups.items()):
            seq = sorted((rows[i][0], (rows[i][1].get("value") or "").strip())
                         for i in idxs)
            seq = [(d, v) for d, v in seq if v and pd(d) and pd(d) <= tq]
            if len(seq) < 2:
                continue
            merged = [seq[0]]
            for d, v in seq[1:]:
                if v.lower() != merged[-1][1].lower():
                    merged.append((d, v))
            per = {}
            for j, (d, v) in enumerate(merged):
                end = pd(merged[j + 1][0]) if j + 1 < len(merged) else tq
                st = pd(d)
                if st and end and end > st:
                    per[v] = per.get(v, 0) + (end - st).days
            distinct = len({v.lower() for _, v in merged})
            longest = max(per, key=per.get) if per else "?"
            lines.append(f"  {key[1]}: {distinct} distinct values; "
                         f"{len(merged) - 1} changes; longest-held: {longest}")
    return "\n".join(lines)


def parse_answer(raw: str):
    """末行 ANSWER: 解析;无则取末非空行并记协议偏差。"""
    ans_lines = [l for l in raw.splitlines() if l.strip().upper().startswith("ANSWER:")]
    if ans_lines:
        return ans_lines[-1].split(":", 1)[1].strip(), False
    tail = [l.strip() for l in raw.splitlines() if l.strip()]
    return (tail[-1] if tail else ""), True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["smw", "smwctrl", "smwplain",
                                         "smwshuf", "smoc", "smocshuf",
                                         "smoctwin", "smocrep", "smoctwinmf",
                                         "smocr", "smocc", "smocrc"], required=True)
    ap.add_argument("--full", action="store_true",
                    help="全 418 题(105 库);默认 15 库 60 题抽样")
    ap.add_argument("--twin-seed", default="main", choices=["main", "s21", "s22"],
                    help="孪生臂的种子批(2c 并池用)")
    ap.add_argument("--cards-dir", default="", help="覆盖卡片目录(P② 注入实验用)")
    ap.add_argument("--out", default="", help="覆盖输出文件路径")
    ap.add_argument("--uids-file", default="", help="只跑该文件(每行一个 uid)中的库")
    ap.add_argument("--questions-file", default="",
                    help="题源 jsonl(uid/qid/qtype/question/gold),替代默认 418 抽样")
    ap.add_argument("--data", default="",
                    help="[批33-A 新增] 覆盖语料 json(单文件),替代 VOLS 多卷装载")
    a = ap.parse_args()
    _QLAST = int(os.environ.get("QVF_PROMPT_QLAST", "0") or 0)
    _SMWP = SMW_PROMPT_QLAST if _QLAST else SMW_PROMPT
    prompt_tpl = {"smw": _SMWP, "smwshuf": _SMWP, "smoc": _SMWP,
                  "smocshuf": SMW_PROMPT, "smoctwin": SMW_PROMPT,
                  "smocrep": SMW_PROMPT, "smoctwinmf": SMW_PROMPT,
                  "smocr": SMW_PROMPT, "smocc": SMW_PROMPT, "smocrc": SMW_PROMPT,
                  "smwctrl": CTRL_PROMPT, "smwplain": PLAIN_PROMPT}[a.system]
    CARD_ARMS = {"smoc", "smocshuf", "smoctwin", "smocrep", "smoctwinmf"}
    PERQ_ARMS = {"smocr": (True, False), "smocc": (False, True),
                 "smocrc": (True, True)}
    TWIN_ARMS = {"smoctwin", "smoctwinmf"}

    entries = {}
    if a.system in ("smoctwin", "smoctwinmf"):  # 孪生考场:另一套语料/题源/卡片库
        seed_cfg = {
            "main": ("data/replchain_50.json", "results/twinC_repl_direct.jsonl"),
            "s21": ("data/replchain_s21_p10.json", "results/s21_repl_direct.jsonl"),
            "s22": ("data/replchain_s22_p10.json", "results/s22_repl_direct.jsonl"),
        }[a.twin_seed]
        for e in json.loads((ROOT / seed_cfg[0]).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
        by_uid = {}
        for r in (json.loads(l) for l in open(
                ROOT / seed_cfg[1], encoding="utf-8")):
            by_uid.setdefault(r["uid"], []).append(
                {"qid": r["question_id"], "qtype": r["question_type"],
                 "question": r["question"], "gold": r["gold_answer"]})
        picked = sorted(by_uid)
    else:
        for v in ([a.data] if a.data else VOLS):   # [批33-A] --data 覆盖
            for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
                entries.setdefault(e["uid"], e)
        if a.questions_file:
            by_uid = {}
            for q in (json.loads(l) for l in open(ROOT / a.questions_file,
                                                  encoding="utf-8")):
                by_uid.setdefault(q["uid"], []).append(q)
            picked = sorted(by_uid)
        else:
            picked, by_uid = sample_stores()
            if a.full:
                picked = sorted(by_uid)  # 全量 105 库;已跑行靠 resume 跳过
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    seed_sfx = "" if a.twin_seed == "main" else f"_{a.twin_seed}"
    out_p = (ROOT / a.out) if a.out else \
        ROOT / f"results/wsc_s5_{a.system}{seed_sfx}.jsonl"
    if a.uids_file:
        keep = {l.strip() for l in open(ROOT / a.uids_file, encoding="utf-8")
                if l.strip()}
        picked = [u for u in picked if u in keep] or sorted(keep & set(by_uid))
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}
    fh = open(out_p, "a", encoding="utf-8")
    n_dev = 0
    for uid in picked:
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            continue
        if a.system in PERQ_ARMS:
            transcript = None  # 逐题渲染(角色/汇总依赖题面日期)
        elif a.system in CARD_ARMS:
            try:
                transcript = render_card_ledger(
                    uid, entries[uid],
                    cards_dir=a.cards_dir or ({
                        ("smoctwin", "main"): r"D:\ZZL_cluade/results/wt_cards_twinC_repl",
                        ("smoctwinmf", "main"): r"D:\ZZL_cluade/results/wt_cards_twinC_repl_mf",
                        ("smoctwin", "s21"): r"D:\ZZL_cluade/results/wt_cards_s21_repl",
                        ("smoctwinmf", "s21"): r"D:\ZZL_cluade/results/wt_cards_s21_repl_mf",
                        ("smoctwin", "s22"): r"D:\ZZL_cluade/results/wt_cards_s22_repl",
                        ("smoctwinmf", "s22"): r"D:\ZZL_cluade/results/wt_cards_s22_repl_mf",
                    }.get((a.system, a.twin_seed), "")),
                    shuffle=(a.system == "smocshuf"))
            except FileNotFoundError:
                print(f"[{uid}] no card file, skipped", flush=True)
                continue
        elif False:
            transcript = render_card_ledger(
                uid, entries[uid],
                cards_dir=a.cards_dir or ({
                    ("smoctwin", "main"): r"D:\ZZL_cluade/results/wt_cards_twinC_repl",
                    ("smoctwinmf", "main"): r"D:\ZZL_cluade/results/wt_cards_twinC_repl_mf",
                    ("smoctwin", "s21"): r"D:\ZZL_cluade/results/wt_cards_s21_repl",
                    ("smoctwinmf", "s21"): r"D:\ZZL_cluade/results/wt_cards_s21_repl_mf",
                    ("smoctwin", "s22"): r"D:\ZZL_cluade/results/wt_cards_s22_repl",
                    ("smoctwinmf", "s22"): r"D:\ZZL_cluade/results/wt_cards_s22_repl_mf",
                }.get((a.system, a.twin_seed), "")),
                shuffle=(a.system == "smocshuf"))
        else:
            transcript = render_transcript(
                entries[uid].get("sessions", []),
                shuffle_uid=uid if a.system == "smwshuf" else "")
        for q in qs:
            t0 = time.time()
            if a.system in PERQ_ARMS:
                import re as _re
                m = _re.search(r"(?:Today is |before )([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{2}|[0-9]{4})",
                               q["question"])
                tq = (m.group(1) if m else "2100-01-01")
                ro, ca = PERQ_ARMS[a.system]
                transcript = render_ledger_plus(uid, entries[uid], tq,
                                                roles=ro, calc=ca)
            content = prompt_tpl.format(question=q["question"],
                                        transcript=transcript)
            raw, ti, to = "", 0, 0
            for attempt in range(3):
                try:
                    kw = dict(model=READER_MODEL, max_tokens=READER_MAXTOK,
                              messages=[{"role": "user", "content": content}])
                    if READER_MODEL.startswith("claude-haiku"):
                        kw["temperature"] = 0.0  # sonnet-5 拒收 temperature(存档陷阱)
                    r = client.messages.create(**kw)
                    raw = "".join(b.text for b in r.content if b.type == "text")
                    ti, to = r.usage.input_tokens, r.usage.output_tokens
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"retry {attempt}: {type(e).__name__}: {str(e)[:80]}",
                          flush=True)
                    time.sleep(4)
            pred, deviated = parse_answer(raw)
            n_dev += deviated
            v = judge.judge(q["question"], str(q["gold"]), pred, q["qtype"])
            fh.write(json.dumps({
                "question_id": q["qid"], "mode": a.system, "uid": uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": pred, "raw_trace": raw,
                "protocol_deviation": deviated,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "latency_s": round(time.time() - t0, 2)},
                ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] answered {len(qs)}", flush=True)
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\n{a.system}: {acc:.2f}% (n={rows and len(rows)}); "
          f"protocol deviations this run: {n_dev}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
