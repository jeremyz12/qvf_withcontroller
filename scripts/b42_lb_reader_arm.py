# -*- coding: utf-8 -*-
"""批 42:smoc/direct 读者臂(逐字复用 scripts/lb_reader_arm.py 的渲染/提示词/
判官/检索器 import),唯一改动:**判官侧 token 逐行落盘**并在结束时打印
judge.total_usage——修复 opt_batch33_C_holdout_verdict.md §二 9 末尾记录的
遗留项("判官侧 token 不落盘,三臂判官成本为估算"),使批 42 的成本表全部为
实测而非估算。逻辑与臂位口径(smoc/direct/fullplain/closedbook/ledgerplain)
与原件逐字相同。

用法与 lb_reader_arm.py 相同:
  python scripts/b42_lb_reader_arm.py --reader anthropic:claude-haiku-4-5 \
      --arm smoc --data data/wikistate_holdout2_v1.json \
      --questions data/wsc_holdout2_v1.jsonl \
      --cards-dir results/wt_cards_holdout2 --out results/b42_smoc_holdout2.jsonl
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
from repro_batch3 import (PLAIN_PROMPT, SMW_PROMPT, parse_answer,  # noqa: E402
                          render_card_ledger, render_transcript)
from ext_direct_arm import (READER_SYSTEM, _memories, _query_date,  # noqa: E402
                            _retriever_cls, reader_content)

_THINK = re.compile(r"<think>.*?</think>", re.S)


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
        payload = {
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": 0, "num_ctx": 12288,
                        "num_predict": int(_os.environ.get(
                            "QVF_OLLAMA_NUMPREDICT", "1200"))}}
        if _os.environ.get("QVF_OLLAMA_NOTHINK") == "1":
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
                                      "closedbook", "ledgerplain"],
                    required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", default="data/wikistate_full_ALL.json")
    ap.add_argument("--cards-dir", default="results/wt_cards_v43_20260828")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
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
        pred, dev = (parse_answer(raw) if a.arm == "smoc" else (raw, False))
        v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
        fh.write(json.dumps({
            "question_id": qid, "mode": f"{a.arm}:{a.reader}", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred[:2000],
            "protocol_deviation": dev,
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "judge_input_tokens": v.usage_input_tokens,
            "judge_output_tokens": v.usage_output_tokens,
            "latency_s": round(lat, 2)}, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct} ({lat:.1f}s)", flush=True)
    print(f"LB ARM DONE {a.reader}/{a.arm}: {ok}/{n} = "
          f"{ok / max(1, n) * 100:.1f}%")
    print(f"judge usage: {judge.total_usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
