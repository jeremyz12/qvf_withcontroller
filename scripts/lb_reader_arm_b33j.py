# -*- coding: utf-8 -*-
"""批 33-J 专用读者臂(scripts/lb_reader_arm.py 的副本 + 三处增量,原件不动)。

增量(相对 lb_reader_arm.py):
  ① 新臂 `rtl` —— 读时账目(read-time ledger,J1):
     检索 top-K(与 direct 臂**同一检索器同一 K**,QVF_EMBED_BACKEND=openai)
     → 对这 K 条记忆跑**同一建卡提示词**(wt_qvf_prototype._catalog_prompt(),
     旗标全关 = CATALOG_PROMPT 逐字)→ 用 render_card_ledger 的**同一行格式**
     渲染 → 同 SMW_PROMPT 读者。写时臂唯一的差别是卡在哪里建。
  ② `--patch-dates`(J4):smoc/ledgerplain 臂渲染出账目后,按金链锚点把
     "粒度比金标粗"的行的日期字段改写回金标日期(只改日期,不动任何其它
     字节);与 scripts/ledger_fidelity_audit.py 的判定逻辑逐字同源。
  ③ 溯源字段:每行落 corpus 路径/sha256、cards_dir、git_rev、top_k、
     embed backend、reader、arm、建卡 usage(rtl)。--data/--cards-dir 必填。

用法见 results/opt_batch33_J_bundle_verdict.md。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os as _os
import re
import subprocess
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

# ── J4:账目日期补丁(与 ledger_fidelity_audit.py 同源判定) ──────────
DATE_TOK = re.compile(r"\[entry \d+\]\s+(\S+)\s*\|")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _gran(d):
    y, m, dd = str(d).split("-")
    return 1 if m == "00" else (2 if dd == "00" else 3)


def _gold_str(d):
    """金标日期按其真实粒度渲染(2012-08-00 -> 2012-08;1971-01-11 原样)。"""
    y, m, dd = str(d).split("-")
    if m == "00":
        return y
    if dd == "00":
        return f"{y}-{m}"
    return f"{y}-{m}-{dd}"


def patch_ledger_dates(ledger: str, chain: list):
    """把账目里"日期粒度比金标粗"的锚行改回金标日期。只改日期 token。
    命中规则与 ledger_fidelity_audit.main() 逐字一致:按金链顺序,取第一条
    包含该 value(规范化后子串)的账目行。返回 (新账目, 被改行数)。"""
    lines = ledger.split("\n")
    n = 0
    for c in chain:
        v = _norm(c.get("value", ""))
        if not v:
            continue
        for i, ln in enumerate(lines):
            if v in _norm(ln):
                m = DATE_TOK.match(ln)
                if m and len(m.group(1).split("-")) < _gran(c["date"]):
                    lines[i] = ln[:m.start(1)] + _gold_str(c["date"]) + \
                        ln[m.end(1):]
                    n += 1
                break
    return "\n".join(lines), n


# ── J1:读时建账目 ────────────────────────────────────────────────
def _rtl_ledger(uid, entry, memories, catalog_prompt, card_model, client):
    """对检索到的 memories 跑建卡提示词,再按 render_card_ledger 的行格式渲染。
    返回 (ledger_text, n_records, in_tok, out_tok)。"""
    from complex_query_arm import _mem_dates
    from wt_qvf_prototype import CatalogExtraction
    payload = [{"memory_id": m.memory_id,
                "date": (m.metadata or {}).get("session_date", ""),
                "text": m.content} for m in memories]
    recs, ti, to = [], 0, 0
    for attempt in range(3):
        try:
            resp = client.messages.parse(
                model=card_model, max_tokens=16000, temperature=0.0,
                system=[{"type": "text", "text": catalog_prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user",
                           "content": "MEMORY ROUNDS (JSON):\n"
                           + json.dumps(payload, ensure_ascii=False)}],
                output_format=CatalogExtraction,
            )
            cat = resp.parsed_output
            recs = [r.model_dump() for r in (cat.records if cat else [])]
            ti, to = resp.usage.input_tokens, resp.usage.output_tokens
            break
        except Exception as e:  # noqa: BLE001
            print(f"  rtl catalog retry {attempt}: {type(e).__name__}: "
                  f"{str(e)[:80]}", flush=True)
            time.sleep(4)
    # ── 渲染:逐字复用 render_card_ledger 的行格式与排序 ──
    md = _mem_dates(entry)
    rows = []
    for r in recs:
        d = r.get("stated_date") or md.get(r.get("source_memory_id", ""), "")
        rows.append((d or "9999", r))
    rows.sort(key=lambda x: x[0])
    lines = []
    for n, (d, r) in enumerate(rows, 1):
        span = (r.get("source_span") or "")[:120]
        lines.append(f'[entry {n}] {d if d != "9999" else "undated"} | '
                     f'{r.get("slot", "?")}: {r.get("value", "?")} — "{span}"')
    return "\n".join(lines), len(recs), ti, to


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
                                      "closedbook", "ledgerplain", "rtl"],
                    required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", required=True)          # 溯源纪律:必填
    ap.add_argument("--cards-dir", default="")        # rtl/direct 不需要
    ap.add_argument("--out", required=True)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--patch-dates", action="store_true",
                    help="J4:把账目里粒度比金标粗的锚行日期改回金标日期")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--shard-mode", choices=["stride", "block"],
                    default="stride")
    ap.add_argument("--card-model", default="claude-haiku-4-5",
                    help="rtl 臂建卡模型(与写时建卡默认同款)")
    a = ap.parse_args()
    if a.arm in ("smoc", "ledgerplain") and not a.cards_dir:
        ap.error("--cards-dir is required for smoc/ledgerplain")

    raw_corpus = Path(a.data).read_bytes()
    corpus_sha = hashlib.sha256(raw_corpus).hexdigest()[:16]
    try:
        git_rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True,
                                 cwd=str(Path(__file__).resolve().parent.parent)
                                 ).stdout.strip()
    except Exception:  # noqa: BLE001
        git_rev = ""
    entries = {e["uid"]: e for e in json.loads(raw_corpus.decode("utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    if a.nshards > 1:
        if a.shard_mode == "block":
            # 连续分块:同一 uid 的 4 道题落在同一分片,检索器/建卡缓存不被打散
            ch = -(-len(qs) // a.nshards)
            qs = qs[a.shard * ch:(a.shard + 1) * ch]
        else:
            qs = [q for i, q in enumerate(qs) if i % a.nshards == a.shard]
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")} \
        if outp.exists() else set()
    fh = open(outp, "a", encoding="utf-8")
    judge = ClaudeJudge()
    led, retr = {}, {}
    need_retr = a.arm in ("direct", "rtl")
    retr_cls = _retriever_cls() if need_retr else None
    cat_prompt = card_client = None
    if a.arm == "rtl":
        import anthropic
        from wt_qvf_prototype import _catalog_prompt
        cat_prompt = _catalog_prompt()
        card_client = anthropic.Anthropic()
    prov = {"corpus": a.data, "corpus_sha256_16": corpus_sha,
            "cards_dir": a.cards_dir, "git_rev": git_rev, "top_k": a.top_k,
            "embed_backend": _os.environ.get("QVF_EMBED_BACKEND", ""),
            "patch_dates": bool(a.patch_dates)}
    n = ok = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done or uid not in entries:
            continue
        extra = {}
        if a.arm in ("smoc", "ledgerplain"):
            key = (uid, bool(a.patch_dates))
            if key not in led:
                lg = render_card_ledger(uid, entries[uid],
                                        cards_dir=a.cards_dir)
                if a.patch_dates:
                    lg, npatch = patch_ledger_dates(lg,
                                                    entries[uid].get("chain", []))
                    extra["ledger_dates_patched"] = npatch
                led[key] = (lg, extra.get("ledger_dates_patched", 0))
            lg, npatch = led[key]
            extra["ledger_dates_patched"] = npatch
            sys_p = ""
            if a.arm == "smoc":
                user = SMW_PROMPT.format(question=q["question"], transcript=lg)
            else:
                user = PLAIN_PROMPT.format(
                    question=q["question"],
                    transcript="Dated memory ledger of the user:\n" + lg)
        elif a.arm == "rtl":
            if uid not in retr:
                retr[uid] = retr_cls(_memories(entries[uid]))
            got = retr[uid].retrieve(q["question"], top_k=a.top_k)
            ck = tuple(m.memory_id for m in got)
            if ck not in led:
                led[ck] = _rtl_ledger(uid, entries[uid], got, cat_prompt,
                                      a.card_model, card_client)
                extra["rtl_catalog_cached"] = False
            else:
                extra["rtl_catalog_cached"] = True
            lg, nrec, cti, cto = led[ck]
            extra.update({"rtl_n_records": nrec,
                          "rtl_catalog_input_tokens": cti,
                          "rtl_catalog_output_tokens": cto,
                          "retrieved_memory_ids": list(ck)})
            sys_p = ""
            user = SMW_PROMPT.format(question=q["question"], transcript=lg)
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
            got = retr[uid].retrieve(q["question"], top_k=a.top_k)
            sys_p = READER_SYSTEM
            user = reader_content(q["question"], got,
                                  _query_date(entries[uid], q["question"]))
            extra["retrieved_memory_ids"] = [m.memory_id for m in got]
        raw, ti, to, lat = "", 0, 0, 0.0
        for attempt in range(3):
            try:
                raw, ti, to, lat = call_reader(a.reader, sys_p, user)
                break
            except Exception as e:  # noqa: BLE001
                print(f"retry {attempt}: {type(e).__name__}: {str(e)[:80]}",
                      flush=True)
                time.sleep(4)
        pred, dev = (parse_answer(raw) if a.arm in ("smoc", "rtl")
                     else (raw, False))
        v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
        row = {
            "question_id": qid, "mode": f"{a.arm}:{a.reader}", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred[:2000],
            "protocol_deviation": dev,
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "judge_input_tokens": getattr(v, "usage_input_tokens", None),
            "judge_output_tokens": getattr(v, "usage_output_tokens", None),
            "judge_model": judge.model,
            "latency_s": round(lat, 2)}
        row.update(extra)
        row["prov"] = prov
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        ok += bool(v.correct)
        print(f"[{qid}] {v.correct} ({lat:.1f}s)", flush=True)
    print(f"LB ARM DONE {a.reader}/{a.arm}: {ok}/{n} = "
          f"{ok / max(1, n) * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
