# -*- coding: utf-8 -*-
"""批 33-I 诊断臂:ledgerplain(同一账目 + 裸问答提示,无 F.1 两段式协议)。

用途:把"账目里没有内容"与"协议逼出弃答"分开。
语义逐字镜像冻结原件 scripts/lb_reader_arm.py 的 ledgerplain 分支:
  user = PLAIN_PROMPT.format(question=..., transcript="Dated memory ledger of "
                             "the user:\n" + render_card_ledger(...))
  pred = raw(不走 parse_answer,无协议偏差概念)
读者 / 温度 / 判官 / 渲染器全部 import 自冻结原件。

用法:
  python scripts/b33i_ledgerplain_arm.py --data data/lme_single_session_preference_wt.json \
      --cards-dir results/wt_cards_b33i_lme --qtype single-session-preference \
      --out results/b33i_lme_ssp_ledgerplain.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")

import anthropic  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import (  # noqa: E402
    PLAIN_PROMPT,
    READER_MAXTOK,
    READER_MODEL,
    render_card_ledger,
)

ROOT = Path(r"D:\ZZL_cluade")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cards-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--qtype", default="")
    a = ap.parse_args()

    entries = json.loads((ROOT / a.data).read_text(encoding="utf-8"))
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    out_p = ROOT / a.out
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"]
                for l in open(out_p, encoding="utf-8")}
    fh = open(out_p, "a", encoding="utf-8")
    for e in entries:
        uid = e["uid"]
        qs = [(f"{uid}_{dim}_query", dim, q)
              for dim, q in (e.get("probing_queries") or {}).items()]
        qs = [x for x in qs if x[0] not in done]
        if not qs:
            continue
        try:
            ledger = render_card_ledger(uid, e, cards_dir=a.cards_dir)
        except FileNotFoundError:
            print(f"[{uid}] no card file, skipped", flush=True)
            continue
        for qid, dim, q in qs:
            t0 = time.time()
            qtype = a.qtype or f"chain-{dim}"
            content = PLAIN_PROMPT.format(
                question=q["q"],
                transcript="Dated memory ledger of the user:\n" + ledger)
            raw, ti, to = "", 0, 0
            for attempt in range(3):
                try:
                    kw = dict(model=READER_MODEL, max_tokens=READER_MAXTOK,
                              messages=[{"role": "user", "content": content}])
                    if READER_MODEL.startswith("claude-haiku"):
                        kw["temperature"] = 0.0
                    r = client.messages.create(**kw)
                    raw = "".join(b.text for b in r.content if b.type == "text")
                    ti, to = r.usage.input_tokens, r.usage.output_tokens
                    break
                except Exception as ex:  # noqa: BLE001
                    print(f"retry {attempt}: {type(ex).__name__}: "
                          f"{str(ex)[:90]}", flush=True)
                    time.sleep(4)
            pred = raw
            is_abs = qid.split("_")[0].endswith("abs")
            v = judge.judge(q["q"], str(q.get("gold", "")), pred, qtype, is_abs)
            fh.write(json.dumps({
                "question_id": qid, "mode": "ledgerplain", "uid": uid,
                "question_type": qtype, "question": q["q"],
                "gold_answer": q.get("gold", ""), "answer": pred,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "judge_input_tokens": v.usage_input_tokens,
                "judge_output_tokens": v.usage_output_tokens,
                "latency_s": round(time.time() - t0, 2),
                "reader_model": READER_MODEL, "cards_dir": a.cards_dir,
            }, ensure_ascii=False) + "\n")
            fh.flush()
    fh.close()
    print(f"LEDGERPLAIN DONE; JUDGE TOTAL USAGE: {judge.total_usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
