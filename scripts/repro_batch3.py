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

READER_MODEL = "claude-haiku-4-5"
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
    lines = []
    for n, (d, r) in enumerate(rows, 1):
        span = (r.get("source_span") or "")[:120]
        lines.append(f'[entry {n}] {d if d != "9999" else "undated"} | '
                     f'{r.get("slot", "?")}: {r.get("value", "?")} — "{span}"')
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
                                         "smoctwin", "smocrep"], required=True)
    ap.add_argument("--full", action="store_true",
                    help="全 418 题(105 库);默认 15 库 60 题抽样")
    a = ap.parse_args()
    prompt_tpl = {"smw": SMW_PROMPT, "smwshuf": SMW_PROMPT, "smoc": SMW_PROMPT,
                  "smocshuf": SMW_PROMPT, "smoctwin": SMW_PROMPT,
                  "smocrep": SMW_PROMPT,
                  "smwctrl": CTRL_PROMPT, "smwplain": PLAIN_PROMPT}[a.system]
    CARD_ARMS = {"smoc", "smocshuf", "smoctwin", "smocrep"}

    entries = {}
    if a.system == "smoctwin":  # 孪生污染考场:另一套语料/题源/卡片库
        for e in json.loads((ROOT / "data/replchain_50.json"
                             ).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
        by_uid = {}
        for r in (json.loads(l) for l in open(
                ROOT / "results/twinC_repl_direct.jsonl", encoding="utf-8")):
            by_uid.setdefault(r["uid"], []).append(
                {"qid": r["question_id"], "qtype": r["question_type"],
                 "question": r["question"], "gold": r["gold_answer"]})
        picked = sorted(by_uid)
    else:
        for v in VOLS:
            for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
                entries.setdefault(e["uid"], e)
        picked, by_uid = sample_stores()
        if a.full:
            picked = sorted(by_uid)  # 全量 105 库;已跑行靠 resume 跳过
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    out_p = ROOT / f"results/wsc_s5_{a.system}.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}
    fh = open(out_p, "a", encoding="utf-8")
    n_dev = 0
    for uid in picked:
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            continue
        if a.system in CARD_ARMS:
            transcript = render_card_ledger(
                uid, entries[uid],
                cards_dir=(r"D:\ZZL_cluade/results/wt_cards_twinC_repl"
                           if a.system == "smoctwin" else ""),
                shuffle=(a.system == "smocshuf"))
        else:
            transcript = render_transcript(
                entries[uid].get("sessions", []),
                shuffle_uid=uid if a.system == "smwshuf" else "")
        for q in qs:
            t0 = time.time()
            content = prompt_tpl.format(question=q["question"],
                                        transcript=transcript)
            raw, ti, to = "", 0, 0
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=READER_MODEL, max_tokens=800, temperature=0.0,
                        messages=[{"role": "user", "content": content}])
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
