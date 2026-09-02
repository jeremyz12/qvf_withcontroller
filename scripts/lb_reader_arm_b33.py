# -*- coding: utf-8 -*-
"""批 33-E 专用跑批器 = scripts/lb_reader_arm.py 的副本(原件冻结不改)
+ 三处增量:

  ① `--arm plan`:检索"选中集合"由离线计划文件给定
     (scripts/b33e_retrieval.py 产出),渲染/系统提示词/读者调用与
     `--arm direct` 逐字节相同(同 READER_SYSTEM、同 reader_content、
     同 haiku-4-5),唯一差别就是**选了哪 10 条**——这是 33-E 要测的量;
  ② 逐行落判官 token(judge_input_tokens/judge_output_tokens),
     使成本可由 usage 实测而非估算;
  ③ `--cache-from`:读者输入完全相同(同题 + 同记忆 id 序列)时复用既有
     结果行,不重复调用。温度 0 下同输入同输出,复用是精确的,并使配对
     McNemar 的"同检索题"成为构造性平局;每行标 `reused_from`。
  另加 `--shard i/j` 便于 ≤4 路并行。

用法(33-E):
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/lb_reader_arm_b33.py \
     --reader anthropic:claude-haiku-4-5 --arm plan \
     --plan results/b33e_plan_rerank.jsonl \
     --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
     --shard 0/4 --out results/b33e_rerank_shard0.jsonl
"""
from __future__ import annotations

import argparse
import glob as _glob
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


def _load_cache(spec: str) -> dict:
    """从既有结果 jsonl(需含 retrieved_memory_ids)建 (qid, ids) -> 行 缓存。"""
    out = {}
    files = []
    for part in spec.split(","):
        part = part.strip()
        if part:
            files.extend(_glob.glob(part))
    for f in files:
        for l in open(f, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            ids = r.get("retrieved_memory_ids")
            if not ids:
                continue
            out[(r["question_id"], tuple(ids))] = r
    print(f"cache: {len(out)} rows from {len(files)} files", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True)
    ap.add_argument("--arm", choices=["smoc", "direct", "fullplain",
                                      "closedbook", "ledgerplain", "plan"],
                    required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", default="data/wikistate_full_ALL.json")
    ap.add_argument("--cards-dir", default="results/wt_cards_v43_20260828")
    ap.add_argument("--plan", default="", help="--arm plan 的检索计划 jsonl")
    ap.add_argument("--cache-from", default="", help="逗号分隔的结果 jsonl 通配")
    ap.add_argument("--shard", default="", help="i/j -> questions[i::j]")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    if a.shard:
        i, j = (int(x) for x in a.shard.split("/"))
        qs = qs[i::j]
    plan = {}
    if a.arm == "plan":
        if not a.plan:
            raise SystemExit("--arm plan 需要 --plan")
        for l in open(a.plan, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                plan[r["qid"]] = r["memory_ids"]
    cache = _load_cache(a.cache_from) if a.cache_from else {}
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")
            if l.strip()} if outp.exists() else set()
    fh = open(outp, "a", encoding="utf-8")
    judge = ClaudeJudge()
    led, retr, memidx = {}, {}, {}
    retr_cls = _retriever_cls() if a.arm == "direct" else None
    n = ok = n_reuse = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done or uid not in entries:
            continue
        mem_ids = None
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
        elif a.arm == "plan":
            # 与 direct 分支唯一的差别:选中集合来自计划文件。
            if uid not in memidx:
                memidx[uid] = {m.memory_id: m for m in _memories(entries[uid])}
            mem_ids = plan.get(qid)
            if mem_ids is None:
                continue  # 计划尚未覆盖该题(计划文件仍在生成);下轮 --resume 补
            got = [memidx[uid][i] for i in mem_ids]
            sys_p = READER_SYSTEM
            user = reader_content(q["question"], got,
                                  _query_date(entries[uid], q["question"]))
        else:
            if uid not in retr:
                retr[uid] = retr_cls(_memories(entries[uid]))
            got = retr[uid].retrieve(q["question"], top_k=10)
            mem_ids = [m.memory_id for m in got]
            sys_p = READER_SYSTEM
            user = reader_content(q["question"], got,
                                  _query_date(entries[uid], q["question"]))

        hit = cache.get((qid, tuple(mem_ids))) if mem_ids else None
        if hit is not None:
            row = dict(hit)
            row.update({"question_id": qid, "mode": f"{a.arm}:{a.reader}",
                        "reused_from": hit.get("mode", "?")})
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            n_reuse += 1
            ok += bool(row.get("judge_correct"))
            print(f"[{qid}] REUSE {row.get('judge_correct')}", flush=True)
            continue

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
        ju0 = dict(judge.total_usage)
        v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
        row = {
            "question_id": qid, "mode": f"{a.arm}:{a.reader}", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred[:2000],
            "protocol_deviation": dev,
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "judge_input_tokens":
                judge.total_usage["input_tokens"] - ju0["input_tokens"],
            "judge_output_tokens":
                judge.total_usage["output_tokens"] - ju0["output_tokens"],
            "judge_model": judge.model,
            "latency_s": round(lat, 2)}
        if mem_ids is not None:
            row["retrieved_memory_ids"] = mem_ids
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct} ({lat:.1f}s)", flush=True)
    print(f"LB ARM DONE {a.reader}/{a.arm}: {ok}/{n} = "
          f"{ok / max(1, n) * 100:.1f}% (reused {n_reuse})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
