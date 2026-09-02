# -*- coding: utf-8 -*-
"""批 33-I:任意 wt-schema 语料上的 smoc(卡片账目)臂。

渲染器 / 提示词 / 读者 / 解析 / 判官全部 import 自冻结原件
`scripts/repro_batch3.py`(render_card_ledger / SMW_PROMPT / parse_answer /
READER_MODEL / READER_MAXTOK),本文件只负责:
  ① 从任意 wt-schema JSON(scripts/adapt_lme_for_wt.py 产物、data/mab_fc_*.json)
     取 entries 与 probing_queries —— 原件把语料卷写死成 WikiState 的 VOLS;
  ② 把真实考场 question_type 传给判官(而非 stale_chain 载入器的 "chain-q1"),
     使账目臂与 direct 臂在判官提示词上同口径。
零改动地复用原件语义;不修改 results/ 下任何既有文件。

用法:
  python scripts/b33i_smoc_arm.py --data data/lme_single_session_preference_wt.json \
      --cards-dir results/wt_cards_b33i_lme --qtype single-session-preference \
      --out results/b33i_smoc_lme_ssp.jsonl
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
    READER_MAXTOK,
    READER_MODEL,
    SMW_PROMPT,
    parse_answer,
    render_card_ledger,
)

ROOT = Path(r"D:\ZZL_cluade")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cards-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--qtype", default="", help="判官所见考场题型;空则用 chain-<dim>")
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
    n_dev = 0
    for e in entries:
        uid = e["uid"]
        qs = [(f"{uid}_{dim}_query", dim, q)
              for dim, q in (e.get("probing_queries") or {}).items()]
        qs = [x for x in qs if x[0] not in done]
        if not qs:
            continue
        try:
            transcript = render_card_ledger(uid, e, cards_dir=a.cards_dir)
        except FileNotFoundError:
            print(f"[{uid}] no card file, skipped", flush=True)
            continue
        for qid, dim, q in qs:
            t0 = time.time()
            qtype = a.qtype or f"chain-{dim}"
            content = SMW_PROMPT.format(question=q["q"], transcript=transcript)
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
                    print(f"retry {attempt}: {type(ex).__name__}: {str(ex)[:90]}",
                          flush=True)
                    time.sleep(4)
            pred, deviated = parse_answer(raw)
            n_dev += deviated
            is_abs = qid.split("_")[0].endswith("abs") or "_abs_" in qid
            v = judge.judge(q["q"], str(q.get("gold", "")), pred, qtype, is_abs)
            fh.write(json.dumps({
                "question_id": qid, "mode": "smoc", "uid": uid,
                "question_type": qtype, "question": q["q"],
                "gold_answer": q.get("gold", ""), "answer": pred,
                "raw_trace": raw, "protocol_deviation": deviated,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "judge_input_tokens": v.usage_input_tokens,
                "judge_output_tokens": v.usage_output_tokens,
                "latency_s": round(time.time() - t0, 2),
                "reader_model": READER_MODEL,
                "cards_dir": a.cards_dir,
            }, ensure_ascii=False) + "\n")
            fh.flush()
    fh.close()
    print(f"SMOC DONE protocol_deviation={n_dev}")
    print(f"JUDGE TOTAL USAGE: {judge.total_usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
