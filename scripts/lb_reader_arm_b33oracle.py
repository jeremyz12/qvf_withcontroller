# -*- coding: utf-8 -*-
"""批 33-F 上界臂跑批器(scripts/lb_reader_arm.py 的副本 + 两个 oracle 臂;
原件一字不改)。

新增两臂,都只把"读者看到的证据"换成金标本身,读者/提示词/解析/判官
与对照臂逐字同口径:

  oracle_evidence(F1):把 direct 臂的 top-10 检索记忆换成**金链锚句**
    (每个 chain 行的 state_span,带该行 date,按日期升序),
    system = ext_direct_arm.READER_SYSTEM(逐字),
    user   = ext_direct_arm.reader_content(question, 金句, _query_date(...)),
    答案 = 读者原文(与 direct 臂同,不走 parse_answer)。
    → 上界:检索完美时的 direct 臂。

  oracle_cards(F2):把 smoc 臂的账目换成**金链渲染的账目**
    (行格式逐字镜像 repro_batch3.render_card_ledger 的整本视图:
     `[entry n] <date> | <slot>: <value> — "<span>"`,span 截 120 字符),
    提示词 = repro_batch3.SMW_PROMPT(与 lb_reader_arm 的 smoc 臂同),
    parse_answer 照用。
    → 上界:建卡完美时的 smoc 臂。90.45 与它的差 = 写侧余量;
      100 − F2 = 金标/判官/读者残差。

用法(每臂 4 分片并行,并行度 ≤4):
  PYTHONUTF8=1 python scripts/lb_reader_arm_b33oracle.py \
      --reader anthropic:claude-haiku-4-5 --arm oracle_cards \
      --data data/wikistate_full_ALL_v24.json \
      --questions data/wsc_s5_v2.jsonl \
      --shard 0 --nshards 4 --out results/b33_F2_oracle_cards_shard0.jsonl
"""
from __future__ import annotations

import argparse
import json
import os as _os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import requests  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from qvf.retrieval import MemoryItem  # noqa: E402
from repro_batch3 import (PLAIN_PROMPT, SMW_PROMPT, parse_answer,  # noqa: E402
                          render_card_ledger, render_transcript)
from ext_direct_arm import (READER_SYSTEM, _memories, _query_date,  # noqa: E402
                            _retriever_cls, reader_content)

_THINK = re.compile(r"<think>.*?</think>", re.S)


# ── 33-F 金标渲染:两个 oracle 臂各一个纯函数,零 LLM、零检索 ──────────
def _gold_rows(entry: dict):
    """金链行按日期升序:[(date, value, state_span), ...]。"""
    rows = []
    for c in entry.get("chain", []):
        rows.append((str(c.get("date", "") or "9999"),
                     str(c.get("value", "")),
                     str(c.get("state_span", "") or "")))
    rows.sort(key=lambda x: x[0])
    return rows


def gold_memories(entry: dict):
    """F1:金锚句装成 MemoryItem(content=state_span,session_date=该行日期),
    供 ext_direct_arm.reader_content 逐字渲染(替换 top-10 检索结果)。"""
    uid = entry.get("uid", "")
    out = []
    for i, (d, _v, span) in enumerate(_gold_rows(entry)):
        out.append(MemoryItem(
            memory_id=f"{uid}/gold#{i}",
            content=span,
            metadata={"session_id": f"gold{i}",
                      "session_date": "" if d == "9999" else d},
        ))
    return out


def gold_ledger(entry: dict) -> str:
    """F2:金链渲染的账目。行格式逐字镜像 repro_batch3.render_card_ledger
    的整本视图分支(entry 序号 1 起、9999→undated、span 截 120)。

    QVF_B33F_DATEFIX=1(事后诊断臂,默认 0 时逐字节不变):把金链里的
    欠定日期 `YYYY-00-00` / `YYYY-MM-00` 按**出题器的隐含约定**补全为
    `YYYY-01-01` / `YYYY-MM-01` 再渲染。用途:判别 F2 残差里"日期欠定"
    一类到底是读者算不出,还是渲染面上根本无法恢复金标的解析约定。"""
    slot = entry.get("slot", "?")
    fix = _os.environ.get("QVF_B33F_DATEFIX") == "1"
    lines = []
    for n, (d, v, span) in enumerate(_gold_rows(entry), 1):
        if fix and d != "9999":
            p = (d.split("-") + ["01", "01"])[:3]
            d = f"{p[0]}-{p[1] if p[1] != '00' else '01'}-" \
                f"{p[2] if p[2] != '00' else '01'}"
        lines.append(f'[entry {n}] {d if d != "9999" else "undated"} | '
                     f'{slot}: {v} — "{span[:120]}"')
    return "\n".join(lines)


def call_reader(reader: str, system: str, user: str):
    kind, model = reader.split(":", 1)
    t0 = time.time()
    if kind == "anthropic":
        import anthropic
        cli = call_reader._ant = getattr(call_reader, "_ant", None) or \
            anthropic.Anthropic()
        kw = dict(model=model, max_tokens=800,
                  messages=[{"role": "user", "content": user}])
        if system:
            kw["system"] = system
        if model.startswith("claude-haiku"):
            kw["temperature"] = 0.0
        r = cli.messages.create(**kw)
        txt = "".join(b.text for b in r.content if b.type == "text")
        return txt, r.usage.input_tokens, r.usage.output_tokens, \
            time.time() - t0
    if kind == "openai":
        from openai import OpenAI
        cli = call_reader._oai = getattr(call_reader, "_oai", None) or OpenAI()
        msgs = ([{"role": "system", "content": system}] if system else []) + \
            [{"role": "user", "content": user}]
        r = cli.chat.completions.create(model=model, messages=msgs,
                                        max_completion_tokens=4000)
        txt = r.choices[0].message.content or ""
        return txt, r.usage.prompt_tokens, r.usage.completion_tokens, \
            time.time() - t0
    if kind == "ollama":
        msgs = ([{"role": "system", "content": system}] if system else []) + \
            [{"role": "user", "content": user}]
        import os as _os2
        payload = {
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": 0, "num_ctx": 12288,
                        "num_predict": int(_os2.environ.get(
                            "QVF_OLLAMA_NUMPREDICT", "1200"))}}
        if _os2.environ.get("QVF_OLLAMA_NOTHINK") == "1":
            payload["think"] = False
        r = requests.post("http://localhost:11434/api/chat", json=payload,
                          timeout=600).json()
        if "error" in r and "think" in str(r.get("error", "")):
            payload.pop("think", None)
            r = requests.post("http://localhost:11434/api/chat",
                              json=payload, timeout=600).json()
        txt = _THINK.sub("", (r.get("message") or {}).get("content", "")).strip()
        return txt, r.get("prompt_eval_count", 0), r.get("eval_count", 0), \
            r.get("total_duration", 0) / 1e9
    raise ValueError(kind)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True)
    ap.add_argument("--arm", choices=["smoc", "direct", "fullplain",
                                      "closedbook", "ledgerplain",
                                      "oracle_evidence", "oracle_cards"],
                    required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", default="data/wikistate_full_ALL.json")
    ap.add_argument("--cards-dir", default="results/wt_cards_v43_20260828")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    if a.nshards > 1:
        qs = qs[a.shard::a.nshards]
    outp = Path(a.out)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")} \
        if outp.exists() else set()
    fh = open(outp, "a", encoding="utf-8")
    judge = ClaudeJudge()
    led, retr = {}, {}
    retr_cls = _retriever_cls() if a.arm == "direct" else None
    n = ok = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done or uid not in entries:
            continue
        if a.arm == "smoc":
            if uid not in led:
                led[uid] = render_card_ledger(uid, entries[uid],
                                              cards_dir=a.cards_dir)
            sys_p = ""
            user = SMW_PROMPT.format(question=q["question"],
                                     transcript=led[uid])
            if _os.environ.get("QVF_LEDGER_SELF") == "1":
                user += ("\n\nImportant: count ONLY states that belong to the "
                         "user themself. Ledger entries about other people "
                         "(family, coworkers, friends, acquaintances) must be "
                         "ignored even if they are listed.")
        elif a.arm == "oracle_cards":
            # 33-F2:金链渲染的账目 + smoc 臂同一 SMW_PROMPT。
            if uid not in led:
                led[uid] = gold_ledger(entries[uid])
            sys_p = ""
            user = SMW_PROMPT.format(question=q["question"],
                                     transcript=led[uid])
        elif a.arm == "oracle_evidence":
            # 33-F1:金锚句替换 top-10 检索 + direct 臂同一 READER_SYSTEM/格式。
            if uid not in retr:
                retr[uid] = gold_memories(entries[uid])
            sys_p = READER_SYSTEM
            user = reader_content(q["question"], retr[uid],
                                  _query_date(entries[uid], q["question"]))
        elif a.arm == "ledgerplain":
            if uid not in led:
                led[uid] = render_card_ledger(uid, entries[uid],
                                              cards_dir=a.cards_dir)
            sys_p = ""
            user = PLAIN_PROMPT.format(question=q["question"],
                                       transcript="Dated memory ledger of "
                                       "the user:\n" + led[uid])
        elif a.arm == "closedbook":
            sys_p = ""
            user = ("Answer the question from your own knowledge. If you "
                    "cannot know the answer, give your best guess.\n\n"
                    f"Question: {q['question']}")
        elif a.arm == "fullplain":
            if uid not in led:
                led[uid] = render_transcript(entries[uid].get("sessions", []))
            sys_p = ""
            user = PLAIN_PROMPT.format(question=q["question"],
                                       transcript=led[uid])
        else:
            if uid not in retr:
                retr[uid] = retr_cls(_memories(entries[uid]))
            got = retr[uid].retrieve(q["question"], top_k=10)
            sys_p = READER_SYSTEM
            user = reader_content(q["question"], got,
                                  _query_date(entries[uid], q["question"]))
        raw, ti, to, lat = "", 0, 0, 0.0
        for attempt in range(3):
            try:
                raw, ti, to, lat = call_reader(a.reader, sys_p, user)
                break
            except Exception as e:  # noqa: BLE001
                print(f"retry {attempt}: {type(e).__name__}: {str(e)[:80]}",
                      flush=True)
                time.sleep(4)
        # 解析口径随对照臂:账目类走 ANSWER: 协议解析,证据类取读者原文。
        pred, dev = (parse_answer(raw)
                     if a.arm in ("smoc", "oracle_cards") else (raw, False))
        v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
        fh.write(json.dumps({
            "question_id": qid, "mode": f"{a.arm}:{a.reader}", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred[:2000],
            "protocol_deviation": dev,
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_input_tokens": v.usage_input_tokens,
            "judge_output_tokens": v.usage_output_tokens,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "latency_s": round(lat, 2)}, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct} ({lat:.1f}s)", flush=True)
    print(f"LB ARM DONE {a.reader}/{a.arm} shard{a.shard}/{a.nshards}: "
          f"{ok}/{n} = {ok / max(1, n) * 100:.1f}%")
    print(f"JUDGE USAGE {json.dumps(judge.total_usage)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
