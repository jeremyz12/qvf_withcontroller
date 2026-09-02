# -*- coding: utf-8 -*-
"""榜单缺口补跑器:可插拔读者(openai / ollama / anthropic / gemini:<model>)
× 五臂(smoc 账目 / ledgerplain / direct top-10 / fullplain / closedbook)。
渲染/提示词/判官 import 冻结原件;token 与延迟逐行照记
(ollama 记 prompt_eval/eval_count 与 total_duration;gemini 记
prompt/candidates/thoughts token count)。

批 33-K 副本(原件 scripts/lb_reader_arm.py 不得改动):新增
`gemini:<model>` 分支(google-genai SDK,temperature=0,429/5xx 退避重试,
usage_metadata 逐项入档)。

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
    call_reader.last_meta = {}
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
    if kind == "gemini":
        # 批 33-K:第三厂商读者(Google)。temperature=0;usage_metadata 三项
        # (prompt / candidates / thoughts)逐项记账;429 与 5xx 指数退避重试。
        from google import genai
        from google.genai import types
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
                print(f"  gemini retry {att} ({msg[:70]}) sleep {sl}s",
                      flush=True)
                time.sleep(sl)
        else:  # pragma: no cover
            raise last
        try:
            txt = r.text or ""
        except Exception:  # noqa: BLE001  截断/空候选时 .text 可能抛错
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
        return txt, pt, ct + th, time.time() - t0
    if kind == "ollama":
        msgs = ([{"role": "system", "content": system}] if system else []) + \
            [{"role": "user", "content": user}]
        # (原件此处有局部 `import os as _os`;副本删之——它会把 _os 变成整个
        #  函数的局部名,令 gemini 分支读不到模块级 _os。行为等价。)
        payload = {
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": 0, "num_ctx": 12288,
                        "num_predict": int(_os.environ.get(
                            "QVF_OLLAMA_NUMPREDICT", "1200"))}}
        if _os.environ.get("QVF_OLLAMA_NOTHINK") == "1":
            payload["think"] = False  # 思考型本地模型关思考(qwen3.5 空答教训)
        r = requests.post("http://localhost:11434/api/chat", json=payload,
                          timeout=600).json()
        if "error" in r and "think" in str(r.get("error", "")):
            payload.pop("think", None)  # 模型不支持 think 参数则回退
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
    ap.add_argument("--uids", default=None,
                    help="仅跑该文件列出的 uid(每行一个),用于 b27 十店探针子集")
    ap.add_argument("--uid-stride", type=int, default=1,
                    help="按 uid 排序后每 K 个取 1(K=2 → 144 链取 72 链 / "
                         "288 题,四题型天然平衡);确定性、可复现")
    a = ap.parse_args()
    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    if a.uids:
        keep = {u.strip() for u in
                Path(a.uids).read_text(encoding="utf-8").split() if u.strip()}
        qs = [q for q in qs if q["uid"] in keep]
        print(f"uid filter {a.uids}: {len(keep)} uids -> {len(qs)} questions",
              flush=True)
    if a.uid_stride > 1:
        allu = sorted({q["uid"] for q in qs})
        keep = set(allu[::a.uid_stride])
        qs = [q for q in qs if q["uid"] in keep]
        print(f"uid stride {a.uid_stride}: {len(keep)}/{len(allu)} uids -> "
              f"{len(qs)} questions", flush=True)
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
                # 批 32-B′ 读侧对照臂:只计用户本人的状态
                user += ("\n\nImportant: count ONLY states that belong to the "
                         "user themself. Ledger entries about other people "
                         "(family, coworkers, friends, acquaintances) must be "
                         "ignored even if they are listed.")
        elif a.arm == "ledgerplain":
            # 协议税判别臂:同一账目 + 裸问答提示(无两段式协议)——
            # 分离"账目内容价值"与"协议跟随成本"。
            if uid not in led:
                led[uid] = render_card_ledger(uid, entries[uid],
                                              cards_dir=a.cards_dir)
            sys_p = ""
            user = PLAIN_PROMPT.format(question=q["question"],
                                       transcript="Dated memory ledger of "
                                       "the user:\n" + led[uid])
        elif a.arm == "closedbook":
            # 闭卷基线:零上下文,纯参数知识答题——量化"化名+长尾闸"后的
            # 参数泄漏上限(基准论文标准行)。
            sys_p = ""
            user = ("Answer the question from your own knowledge. If you "
                    "cannot know the answer, give your best guess.\n\n"
                    f"Question: {q['question']}")
        elif a.arm == "fullplain":
            # 全文裸读:整段对话按日期序原样入上下文 + 纯问答提示(repro_batch3
            # PLAIN_PROMPT 逐字),即"把全部当成上下文然后提问"。
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
        meta = {}
        for attempt in range(3):
            try:
                raw, ti, to, lat = call_reader(a.reader, sys_p, user)
                meta = dict(getattr(call_reader, "last_meta", {}) or {})
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
            "latency_s": round(lat, 2), "usage_meta": meta},
            ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct} ({lat:.1f}s)", flush=True)
    print(f"LB ARM DONE {a.reader}/{a.arm}: {ok}/{n} = "
          f"{ok / max(1, n) * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
