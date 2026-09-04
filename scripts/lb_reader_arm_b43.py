# -*- coding: utf-8 -*-
"""批 43 读者矩阵跑批器:三个新读者(openai:gpt-5-mini / gemini:gemini-3.6-flash
/ ollama:qwen3:14b) x 三臂(direct top-10 / smoc 账目 / plainctx 全文裸读),
在与 haiku-4.5 / claude-sonnet-5 完全相同的 140 题(results/b35_questions_sample36.jsonl,
36 链)上补齐读者矩阵。原件不得改动,均只读 import:

  - scripts/lb_reader_arm_b33k.py 的 call_reader() openai/gemini/ollama 三支
    (gemini SDK 调用式、429/5xx 退避、usage_metadata 记账逐字复制;ollama 分支
    新增 --num-ctx 可调,原件写死 12288)。
  - scripts/lb_reader_arm_b36b.py 的 direct/smoc 提示词构造与线程池/预算闸
    结构(build_prompt 的 smoc/direct 两支逐字复制)。
  - scripts/b36_plain_fullctx.py 的 PLAINCTX_SYSTEM / PLAINCTX_USER 两个模板
    逐字复制 —— 这是任务书点名"plain whole-memory-in-prompt"的确切措辞,
    本文件把它从"只认 anthropic"扩到三个新读者,提示词本身一个字不改,
    以保证与既有 haiku-4.5 / sonnet-5 两行(results/b36_plainctx_*.jsonl)
    可直接同表比较。

新增(相对三份原件均是纯增量,不改变任何一份原件的默认行为):
  1) `--num-ctx`(仅 ollama 用,默认 20480):本任务 36 链全文均值 ~52K 字符
     / 实测 prompt_eval_count 中位数 ~1.3 万 token,原件 ollama 分支写死
     12288 会截断 plainctx 臂;20480 经实测(冒烟表)在 RTX 5080 16GB 上
     100% GPU 常驻,单题 ~13s。
  2) `--num-predict`(默认 4096,对齐既有 qwen3:14b 探针60"思考 + 4096 预算"
     配置,见 results/QVF_results_compendium_20260830.md 第47行)。
  3) arm=plainctx 分支(三份原件都没有这个 arm 名字;direct/smoc 两支逐字
     照抄 b36b)。
  4) 价目表补 gpt-5-mini($0.25/$2.00 每 Mtok,项目既有口径)与
     gemini-3.6-flash($0.75/$3.75 每 Mtok promo 价,见 opt_batch33_K 判决
     §一);ollama 恒为 $0(本地算力,不计入 --budget 闸)。
  5) 预算闸按 `results/b43_*.jsonl` glob 累计跨调用花费,与 b36b 同结构。

用法:
  PYTHONUTF8=1 python scripts/lb_reader_arm_b43.py \
      --reader openai:gpt-5-mini --arm smoc \
      --cards-dir results/wt_cards_v47skf --workers 4 \
      --data data/wikistate_full_ALL_v24.json \
      --questions results/b35_questions_sample36.jsonl \
      --out results/b43_smoc_gpt5mini.jsonl
  PYTHONUTF8=1 python scripts/lb_reader_arm_b43.py \
      --reader ollama:qwen3:14b --arm plainctx --workers 1 \
      --questions results/b35_questions_sample36.jsonl \
      --out results/b43_plainctx_qwen3-14b.jsonl
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

# ── plainctx 提示词:逐字复制 scripts/b36_plain_fullctx.py，一个字不改 ──
PLAINCTX_SYSTEM = "You are a helpful assistant."
PLAINCTX_USER = ("Below is the complete record of my past conversations with "
                 "you, in chronological order.\n\n{transcript}\n\n"
                 "Question: {question}")

# 读者侧现价($/百万 token,in/out)。
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
    "gpt-5-mini": (0.25, 2.00),
    "gemini-3.6-flash": (0.75, 3.75),
    "qwen3:14b": (0.0, 0.0),
}
DEFAULT_PRICE = (3.0, 15.0)


def price_of(model: str):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICE


def cost_of(model: str, tin, tout) -> float:
    pin, pout = price_of(model)
    return (tin or 0) / 1e6 * pin + (tout or 0) / 1e6 * pout


def prior_spend(pattern: str = "results/b43_*.jsonl") -> float:
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


def call_reader(reader: str, system: str, user: str, num_ctx: int = 20480,
                num_predict: int = 4096):
    """openai / gemini / ollama 三支逐字复制自 scripts/lb_reader_arm_b33k.py
    call_reader()(该文件"批 33-K 副本,原件 scripts/lb_reader_arm.py 不得
    改动"),唯一改动是 ollama 分支的 num_ctx / num_predict 从写死改为形参。"""
    kind, model = reader.split(":", 1)
    call_reader.last_meta = {}
    t0 = time.time()
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
    if kind == "gemini":
        from google import genai
        from google.genai import types
        with call_reader._lock:
            cli = call_reader._gem = getattr(call_reader, "_gem", None) or \
                genai.Client(api_key=(_os.environ.get("GEMINI_API_KEY")
                                      or _os.environ.get("GOOGLE_API_KEY")))
        cfg_kw = dict(temperature=0.0,
                      max_output_tokens=int(_os.environ.get(
                          "QVF_GEMINI_MAXTOK", "8192")))
        if system:
            cfg_kw["system_instruction"] = system
        lvl = _os.environ.get("QVF_GEMINI_THINKING")
        if lvl:
            cfg_kw["thinking_config"] = types.ThinkingConfig(
                thinking_level=lvl)
        cfg = types.GenerateContentConfig(**cfg_kw)
        last = None
        r = None
        for att in range(6):
            try:
                t0 = time.time()
                r = cli.models.generate_content(model=model, contents=user,
                                                config=cfg)
                break
            except Exception as e:  # noqa: BLE001
                last = e
                code = getattr(e, "code", None) or getattr(
                    e, "status_code", None)
                msg = str(e)
                retryable = (code in (429, 500, 502, 503, 504)) or any(
                    s in msg for s in ("429", "500", "502", "503", "504",
                                       "RESOURCE_EXHAUSTED", "UNAVAILABLE",
                                       "INTERNAL", "DEADLINE_EXCEEDED"))
                if att == 5 or not retryable:
                    raise
                sl = min(60, 4 * (2 ** att))
                print("  gemini retry %d (%s) sleep %ds"
                      % (att, msg[:70], sl), flush=True)
                time.sleep(sl)
        else:  # pragma: no cover
            raise last
        try:
            txt = r.text or ""
        except Exception:  # noqa: BLE001
            txt = ""
        if not txt and getattr(r, "candidates", None):
            parts = getattr(getattr(r.candidates[0], "content", None),
                            "parts", None) or []
            txt = "".join(getattr(p, "text", "") or "" for p in parts
                          if not getattr(p, "thought", False))
        um = getattr(r, "usage_metadata", None)
        pt = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
        ct = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
        th = int(getattr(um, "thoughts_token_count", 0) or 0) if um else 0
        tt = int(getattr(um, "total_token_count", 0) or 0) if um else 0
        fr = (getattr(r.candidates[0], "finish_reason", None)
              if getattr(r, "candidates", None) else None)
        call_reader.last_meta = {
            "prompt_token_count": pt, "candidates_token_count": ct,
            "thoughts_token_count": th, "total_token_count": tt,
            "finish_reason": str(fr)}
        return txt, pt, ct + th, time.time() - t0, str(fr)
    if kind == "ollama":
        msgs = ([{"role": "system", "content": system}] if system else []) + \
            [{"role": "user", "content": user}]
        payload = {
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": 0, "num_ctx": num_ctx,
                        "num_predict": num_predict}}
        if _os.environ.get("QVF_OLLAMA_NOTHINK") == "1":
            payload["think"] = False
        r = requests.post("http://localhost:11434/api/chat", json=payload,
                          timeout=600).json()
        if "error" in r and "think" in str(r.get("error", "")):
            payload.pop("think", None)
            r = requests.post("http://localhost:11434/api/chat",
                              json=payload, timeout=600).json()
        txt = _THINK.sub("", (r.get("message") or {}).get("content", "")).strip()
        call_reader.last_meta = {
            "prompt_eval_count": r.get("prompt_eval_count"),
            "eval_count": r.get("eval_count"),
            "total_duration_ns": r.get("total_duration")}
        return txt, r.get("prompt_eval_count", 0), r.get("eval_count", 0), \
            r.get("total_duration", 0) / 1e9, r.get("done_reason", "")
    raise ValueError(kind)


call_reader._lock = threading.Lock()
call_reader.last_meta = {}


def build_prompt(a, q, entries, led, retr):
    uid = q["uid"]
    if a.arm == "smoc":
        sys_p = ""
        user = SMW_PROMPT.format(question=q["question"], transcript=led[uid])
    elif a.arm == "plainctx":
        sys_p = PLAINCTX_SYSTEM
        user = PLAINCTX_USER.format(transcript=led[uid],
                                    question=q["question"])
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
    else:  # direct
        got = retr[uid].retrieve(q["question"], top_k=10)
        sys_p = READER_SYSTEM
        user = reader_content(q["question"], got,
                              _query_date(entries[uid], q["question"]))
    return sys_p, user


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True)
    ap.add_argument("--arm", choices=["smoc", "direct", "plainctx",
                                      "closedbook", "ledgerplain"],
                    required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--cards-dir", default="results/wt_cards_v47skf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--budget", type=float, default=6.0,
                    help="results/b43_*.jsonl 累计读者花费上限($);ollama 恒 $0")
    ap.add_argument("--num-ctx", type=int, default=20480,
                    help="仅 ollama;36 链全文实测中位数 prompt_eval ~1.3万 tok")
    ap.add_argument("--num-predict", type=int, default=4096,
                    help="仅 ollama;对齐既有 qwen3:14b 探针60配置")
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
    print("[plan] %d questions, %d already done, %d to run | arm=%s reader=%s"
          % (len(qs), len(done), len(todo), a.arm, a.reader), flush=True)
    if not todo:
        print("nothing to do")
        return 0

    led, retr = {}, {}
    uids = sorted({q["uid"] for q in todo})
    if a.arm in ("smoc", "ledgerplain"):
        for u in uids:
            led[u] = render_card_ledger(u, entries[u], cards_dir=a.cards_dir)
    elif a.arm == "plainctx":
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
    print("[budget] prior b43 reader spend = $%.3f; cap $%.2f"
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
                est = cost_of(model, len(user) / 3.4, 1200)
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
                        a.reader, sys_p, user, a.num_ctx, a.num_predict)
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
                "reader_model": model, "stop_reason": stop, "reader_error": err,
                "judge_input_tokens": v.usage_input_tokens,
                "judge_output_tokens": v.usage_output_tokens,
                "cards_dir": (a.cards_dir if a.arm in ("smoc", "ledgerplain")
                              else ""),
                "usage_meta": dict(getattr(call_reader, "last_meta", {}) or {})}
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                state["spend"] += cost_of(model, ti, to)
                state["n"] += 1
                state["ok"] += bool(v.correct)
                print("[%s] %s in=%s out=%s stop=%s (%.1fs) $%.3f"
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
    print("B43 ARM DONE %s/%s: %d/%d = %.1f%% | skipped(budget)=%d | "
          "reader spend $%.3f | judge %s"
          % (a.reader, a.arm, ok, n, ok / max(1, n) * 100, state["skipped"],
             state["spend"], judge.total_usage))
    return 0


if __name__ == "__main__":
    sys.exit(main())
