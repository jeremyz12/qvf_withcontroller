# -*- coding: utf-8 -*-
"""榜单缺口补跑器:可插拔读者(openai:<model> / ollama:<model>)× 两臂
(smoc 账目 / direct top-10)。渲染/提示词/判官 import 冻结原件;
token 与延迟逐行照记(ollama 记 prompt_eval/eval_count 与 total_duration)。

用法:
  python scripts/lb_reader_arm.py --reader openai:gpt-5-mini --arm smoc \
      --cards-dir results/wt_cards_v43_20260828 \
      --questions data/wsc_s5_v2.jsonl --out results/wsc_v2_smoc_v43_gpt5mini.jsonl
  python scripts/lb_reader_arm.py --reader ollama:qwen3:14b --arm direct \
      --questions data/lb_sample60.jsonl --out results/lb_qwen14b_direct.jsonl
"""
from __future__ import annotations

import argparse
import json
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
from repro_batch3 import SMW_PROMPT, parse_answer, render_card_ledger  # noqa: E402
from ext_direct_arm import (READER_SYSTEM, _memories, _query_date,  # noqa: E402
                            _retriever_cls, reader_content)

_THINK = re.compile(r"<think>.*?</think>", re.S)


def call_reader(reader: str, system: str, user: str):
    kind, model = reader.split(":", 1)
    t0 = time.time()
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
        r = requests.post("http://localhost:11434/api/chat", json={
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": 0, "num_ctx": 12288,
                        "num_predict": 1200}}, timeout=600).json()
        txt = _THINK.sub("", (r.get("message") or {}).get("content", "")).strip()
        return txt, r.get("prompt_eval_count", 0), r.get("eval_count", 0), \
            r.get("total_duration", 0) / 1e9
    raise ValueError(kind)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True)
    ap.add_argument("--arm", choices=["smoc", "direct"], required=True)
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
            "latency_s": round(lat, 2)}, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct} ({lat:.1f}s)", flush=True)
    print(f"LB ARM DONE {a.reader}/{a.arm}: {ok}/{n} = "
          f"{ok / max(1, n) * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
