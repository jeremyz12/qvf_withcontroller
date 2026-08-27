# -*- coding: utf-8 -*-
"""外部考场 smoc 臂:统一店格式 + 卡店 → 账目读法(冻结 repro_batch3 语义)。

复用而非复制:SMW_PROMPT / render_card_ledger / parse_answer 直接 import 自
scripts/repro_batch3.py(账目渲染与 v2 考场逐字节同款;QVF_LEDGER_VIEW 门控
同样生效,外场探针默认整本视图)。读者 haiku t=0 max_tokens=800,判官
ClaudeJudge——与 WikiState 各臂同口径。

用法:
  python scripts/ext_smoc_arm.py --data data/external/<arena>_unified.json \
      --questions data/external/<arena>_probe.jsonl \
      --cards-dir results/ext_cards_<arena> \
      --out results/ext_<arena>_smoc.jsonl --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import (READER_MODEL, SMW_PROMPT, parse_answer,  # noqa: E402
                          render_card_ledger)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--cards-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8")
          if l.strip()]
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if a.resume and outp.exists():
        done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")}
    fh = open(outp, "a" if a.resume else "w", encoding="utf-8")
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    ledger_cache: dict = {}
    n_run = n_ok = n_dev = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done or uid not in entries:
            continue
        cutoff = q.get("cutoff") or ""
        ck = (uid, cutoff)
        if ck not in ledger_cache:
            try:
                led = render_card_ledger(uid, entries[uid], cards_dir=a.cards_dir)
                if cutoff:
                    # 批 17 外场:账目行按日期 <= cutoff 过滤并重编号
                    # (行格式 "[entry n] DATE | ...";undated 保留)。
                    kept = []
                    for line in led.splitlines():
                        try:
                            d = line.split("] ", 1)[1].split(" | ", 1)[0]
                        except IndexError:
                            kept.append(line)
                            continue
                        if d == "undated" or d <= cutoff:
                            kept.append(line)
                    led = "\n".join(
                        (f"[entry {n}] " + l.split("] ", 1)[1])
                        if l.startswith("[entry ") else l
                        for n, l in enumerate(kept, 1))
                ledger_cache[ck] = led
            except FileNotFoundError:
                print(f"[{uid}] no card file, skipped", flush=True)
                ledger_cache[ck] = None
        transcript = ledger_cache[ck]
        if transcript is None:
            continue
        t0 = time.time()
        content = SMW_PROMPT.format(question=q["question"], transcript=transcript)
        raw, ti, to = "", 0, 0
        for attempt in range(3):
            try:
                kw = dict(model=READER_MODEL, max_tokens=800,
                          messages=[{"role": "user", "content": content}])
                if READER_MODEL.startswith("claude-haiku"):
                    kw["temperature"] = 0.0
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
        v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
        fh.write(json.dumps({
            "question_id": qid, "mode": "ext_smoc", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": pred, "raw_trace": raw,
            "protocol_deviation": deviated,
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "latency_s": round(time.time() - t0, 2)},
            ensure_ascii=False) + "\n")
        fh.flush()
        n_run += 1
        n_ok += bool(v.correct)
        print(f"[{qid}] judge={v.correct} ({time.time() - t0:.1f}s)", flush=True)
    acc = f"{n_ok}/{n_run} = {n_ok / n_run * 100:.1f}%" if n_run else "n/a"
    print(f"EXT SMOC DONE: ran {n_run} (skipped {len(done)}); acc {acc}; "
          f"protocol deviations {n_dev}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
