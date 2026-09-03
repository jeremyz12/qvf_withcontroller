# -*- coding: utf-8 -*-
"""批 36-B 副本(原件 scripts/lb_reader_arm.py 全程只读、零改动)。

目的:把 33-A 的 smoc / direct 两臂 + 归档的 fullplain 臂,用**同一读者**
claude-sonnet-5 在批 35 的同 140 题上重跑一遍,消掉批 36 "QVF(haiku)对
全上下文(sonnet-5)"的跨读者口径瑕疵。

相对原件的**全部**差异(逐条,均为不改变既有默认行为的增量):
  1) anthropic 分支的 max_tokens 由写死 800 改为 `--max-tokens`(默认 **800**,
     与原件逐字节同值)。理由:claude-sonnet-5 默认开思考,max_tokens 同时
     封顶"思考 + 可见文本",800 会把 14% 的题掐成空答(批 36 §五实测)。
     本批 sonnet-5 三臂一律 4000,并逐行落盘 reader_max_tokens。
  2) temperature 闸**语义不变**:原件即 `if model.startswith("claude-haiku")`,
     故 claude-sonnet-5 本来就不发 temperature(该模型收到 temperature 会 400)。
     这里把它写成显式的 _wants_temperature() 并加注释,行为对任何读者都
     与原件相同 —— 没有为本批新增或删除任何一个参数。
  3) `--workers`(默认 1 = 原件的串行行为)。>1 时逐题相互独立,提示词与
     判官调用式不变;账目/检索器在起线程**之前**串行预建,避免竞态重建。
  4) 行 schema 是 33-A 的**超集**:原有 14 个键逐字保留,新增
     reader_model / reader_max_tokens / stop_reason / judge_input_tokens /
     judge_output_tokens / reader_error / cards_dir(33-A 未记读者型号,
     批 36 §六.2 把"无法从产物核实读者"列为遗留缺陷,本批就地补上)。
  5) `--budget`:跨 results/b36b_*_sonnet5.jsonl 累计的读者花费闸。

用法(本批实跑命令见 results/opt_batch36_verdict.md §36b):
  PYTHONUTF8=1 python scripts/lb_reader_arm_b36b.py \
      --reader anthropic:claude-sonnet-5 --arm smoc \
      --cards-dir results/wt_cards_v45 --max-tokens 4000 --workers 4 \
      --data data/wikistate_full_ALL_v24.json \
      --questions results/b35_questions_sample36.jsonl \
      --out results/b36b_smoc_sonnet5.jsonl
"""
from __future__ import annotations

import argparse
import json
import os as _os
import queue
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import requests  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import (PLAIN_PROMPT, SMW_PROMPT, parse_answer,  # noqa: E402
                          render_card_ledger, render_transcript)
from ext_direct_arm import (READER_SYSTEM, _memories, _query_date,  # noqa: E402
                            _retriever_cls, reader_content)

_THINK = re.compile(r"<think>.*?</think>", re.S)

# 读者侧现价($/百万 token)。与 scripts/b36_plain_fullctx.py 同表。
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}
DEFAULT_PRICE = (3.0, 15.0)


def price_of(model: str):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICE


def cost_of(model: str, tin, tout) -> float:
    pin, pout = price_of(model)
    return (tin or 0) / 1e6 * pin + (tout or 0) / 1e6 * pout


def prior_spend(pattern: str = "results/b36b_*_sonnet5.jsonl") -> float:
    tot = 0.0
    for p in sorted(ROOT.glob(pattern)):
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            tot += cost_of(d.get("reader_model", ""),
                           d.get("usage_input_tokens"),
                           d.get("usage_output_tokens"))
    return tot


def _wants_temperature(model: str) -> bool:
    """原件语义逐字保留:只有 claude-haiku* 发 temperature=0。
    claude-sonnet-5 收到 temperature / top_p 会返回 400,故必须省略。"""
    return model.startswith("claude-haiku")


def call_reader(reader: str, system: str, user: str, max_tokens: int = 800):
    kind, model = reader.split(":", 1)
    t0 = time.time()
    if kind == "anthropic":
        import anthropic
        with call_reader._lock:
            cli = call_reader._ant = getattr(call_reader, "_ant", None) or \
                anthropic.Anthropic()
        kw = dict(model=model, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": user}])
        if system:
            kw["system"] = system
        if _wants_temperature(model):
            kw["temperature"] = 0.0
        r = cli.messages.create(**kw)
        txt = "".join(b.text for b in r.content if b.type == "text")
        return txt, r.usage.input_tokens, r.usage.output_tokens, \
            time.time() - t0, r.stop_reason
    if kind == "openai":
        from openai import OpenAI
        with call_reader._lock:
            cli = call_reader._oai = getattr(call_reader, "_oai", None) or \
                OpenAI()
        msgs = ([{"role": "system", "content": system}] if system else []) + \
            [{"role": "user", "content": user}]
        r = cli.chat.completions.create(model=model, messages=msgs,
                                        max_completion_tokens=4000)
        txt = r.choices[0].message.content or ""
        return txt, r.usage.prompt_tokens, r.usage.completion_tokens, \
            time.time() - t0, r.choices[0].finish_reason
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
            r.get("total_duration", 0) / 1e9, r.get("done_reason", "")
    raise ValueError(kind)


call_reader._lock = threading.Lock()


def build_prompt(a, q, entries, led, retr):
    """提示词构造逐字复用原件 main() 的分支,零改写。"""
    uid = q["uid"]
    if a.arm == "smoc":
        sys_p = ""
        user = SMW_PROMPT.format(question=q["question"], transcript=led[uid])
        if _os.environ.get("QVF_LEDGER_SELF") == "1":
            user += ("\n\nImportant: count ONLY states that belong to the "
                     "user themself. Ledger entries about other people "
                     "(family, coworkers, friends, acquaintances) must be "
                     "ignored even if they are listed.")
    elif a.arm == "ledgerplain":
        sys_p = ""
        user = PLAIN_PROMPT.format(question=q["question"],
                                   transcript="Dated memory ledger of "
                                   "the user:\n" + led[uid])
    elif a.arm == "closedbook":
        sys_p = ""
        user = ("Answer the question from your own knowledge. If you "
                "cannot know the answer, give your best guess.\n\n"
                "Question: " + q["question"])
    elif a.arm == "fullplain":
        sys_p = ""
        user = PLAIN_PROMPT.format(question=q["question"], transcript=led[uid])
    else:
        got = retr[uid].retrieve(q["question"], top_k=10)
        sys_p = READER_SYSTEM
        user = reader_content(q["question"], got,
                              _query_date(entries[uid], q["question"]))
    return sys_p, user


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
    ap.add_argument("--max-tokens", type=int, default=800,
                    help="原件写死 800;sonnet-5 思考与可见文本共用该预算")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--budget", type=float, default=8.0,
                    help="results/b36b_*_sonnet5.jsonl 累计读者花费上限($)")
    a = ap.parse_args()
    model = a.reader.split(":", 1)[1]

    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")
            if l.strip()} if outp.exists() else set()
    todo = [q for q in qs if q["qid"] not in done and q["uid"] in entries]
    print("[plan] %d questions, %d already done, %d to run | arm=%s reader=%s "
          "max_tokens=%d temperature_sent=%s"
          % (len(qs), len(done), len(todo), a.arm, a.reader, a.max_tokens,
             _wants_temperature(model)), flush=True)
    if not todo:
        print("nothing to do")
        return 0

    # ── 上下文预建(串行,避免多线程重复构造) ──────────────────
    led, retr = {}, {}
    uids = sorted({q["uid"] for q in todo})
    if a.arm in ("smoc", "ledgerplain"):
        for u in uids:
            led[u] = render_card_ledger(u, entries[u], cards_dir=a.cards_dir)
    elif a.arm == "fullplain":
        for u in uids:
            led[u] = render_transcript(entries[u].get("sessions", []))
    elif a.arm == "direct":
        cls = _retriever_cls()
        for i, u in enumerate(uids, 1):
            retr[u] = cls(_memories(entries[u]))
            print("  [index] %d/%d %s" % (i, len(uids), u), flush=True)
    if led:
        ls = sorted(len(v) for v in led.values())
        print("[context] stores=%d chars min=%d median=%d mean=%.0f max=%d"
              % (len(ls), ls[0], ls[len(ls) // 2], sum(ls) / len(ls), ls[-1]),
              flush=True)

    spend0 = prior_spend()
    print("[budget] prior b36b reader spend = $%.3f; cap $%.2f"
          % (spend0, a.budget), flush=True)

    judge = ClaudeJudge()
    lock = threading.Lock()
    fh = open(outp, "a", encoding="utf-8")
    state = {"spend": spend0, "n": 0, "ok": 0, "stop": False, "skipped": 0}
    qq: "queue.Queue" = queue.Queue()
    for q in todo:
        qq.put(q)

    def worker():
        while True:
            try:
                q = qq.get_nowait()
            except queue.Empty:
                return
            sys_p, user = build_prompt(a, q, entries, led, retr)
            with lock:
                if state["stop"]:
                    state["skipped"] += 1
                    qq.task_done()
                    continue
                est = cost_of(model, len(user) / 3.4, a.max_tokens)
                if state["spend"] + est > a.budget:
                    state["stop"] = True
                    state["skipped"] += 1
                    print("[budget] STOP: $%.2f + est $%.3f > $%.2f"
                          % (state["spend"], est, a.budget), flush=True)
                    qq.task_done()
                    continue
            raw, ti, to, lat, stop = "", 0, 0, 0.0, ""
            err = ""
            for attempt in range(3):
                try:
                    raw, ti, to, lat, stop = call_reader(
                        a.reader, sys_p, user, a.max_tokens)
                    err = ""
                    break
                except Exception as e:  # noqa: BLE001
                    err = "%s: %s" % (type(e).__name__, str(e)[:160])
                    print("retry %d [%s]: %s" % (attempt, q["qid"], err),
                          flush=True)
                    time.sleep(4)
            pred, dev = (parse_answer(raw) if a.arm == "smoc" else (raw, False))
            v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
            row = {
                "question_id": q["qid"], "mode": "%s:%s" % (a.arm, a.reader),
                "uid": q["uid"], "question_type": q.get("qtype"),
                "question": q["question"], "gold_answer": q["gold"],
                "answer": pred[:2000], "protocol_deviation": dev,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "latency_s": round(lat, 2),
                # ── 33-A schema 之外的增量 ──
                "reader_model": model, "reader_max_tokens": a.max_tokens,
                "stop_reason": stop, "reader_error": err,
                "judge_input_tokens": v.usage_input_tokens,
                "judge_output_tokens": v.usage_output_tokens,
                "cards_dir": (a.cards_dir if a.arm in ("smoc", "ledgerplain")
                              else "")}
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                state["spend"] += cost_of(model, ti, to)
                state["n"] += 1
                state["ok"] += bool(v.correct)
                print("[%s] %s in=%s out=%s stop=%s (%.1fs) $%.2f"
                      % (q["qid"], v.correct, ti, to, stop, lat,
                         state["spend"]), flush=True)
            qq.task_done()

    ths = [threading.Thread(target=worker, daemon=True)
           for _ in range(max(1, a.workers))]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    fh.close()
    n, ok = state["n"], state["ok"]
    print("B36B ARM DONE %s/%s: %d/%d = %.1f%% | skipped(budget)=%d | "
          "reader spend $%.3f | judge %s"
          % (a.reader, a.arm, ok, n, ok / max(1, n) * 100, state["skipped"],
             state["spend"], judge.total_usage))
    return 0


if __name__ == "__main__":
    sys.exit(main())
