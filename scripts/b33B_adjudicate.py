# -*- coding: utf-8 -*-
"""scripts/b33B_adjudicate.py — 批 33-B (e) 步的独立复裁(claude-haiku-4-5,两遍)。

对 results/b33B_handinspect.md 覆盖的同一批题(读侧残渣 + 金标平局 + 全部
first_vs_last 错),把"读者当时看到的该槽位状态链 + 题面 + 金标 + 读者答案"
交给一个与判官/读者同档但独立的 haiku 复裁器,四选一:
  model_wrong        账目足以唯一推出金标,读者答错(读侧)
  gold_ambiguous     账目支持不止一个可辩护答案(如任期并列),金标非唯一
  judge_error        读者答案其实与金标一致,判官误判
  ledger_insufficient 账目缺少推出金标所需信息(写侧)

跑两遍(独立采样)以测复裁器自身稳定性;不改主归类,只作旁证。

用法:
  PYTHONUTF8=1 python scripts/b33B_adjudicate.py
产物:results/b33B_adjudication.jsonl(逐题两遍标签)+ 控制台聚合。
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")
import anthropic  # noqa: E402

MODEL = "claude-haiku-4-5"
N_PASSES = 2

SYS = """You are adjudicating a single benchmark item. You are given:
  (1) the question asked,
  (2) the dated state chain that was visible to the answering model (this is
      the ONLY evidence it had for the queried attribute),
  (3) the benchmark's gold answer,
  (4) the answering model's response.

Decide which ONE of these best explains the mismatch:
  "model_wrong"          - the chain uniquely determines the gold answer and
                           the model simply computed/read it wrong.
  "gold_ambiguous"       - the chain supports more than one defensible answer
                           (e.g. two values are tied or separated only by a
                           rounding-level difference), so gold is not uniquely
                           determined by the evidence.
  "judge_error"          - the model's response actually states the gold answer
                           and was marked wrong in error.
  "ledger_insufficient"  - the chain lacks states needed to derive gold at all.

Conventions used by the benchmark: change_count counts transitions strictly up
to the stated Today; count_before counts DISTINCT values with dates strictly
before the stated date; longest_tenure accumulates days per value with the last
segment running to Today; first_vs_last reports the earliest and latest values.

Reply with STRICT JSON only: {"label": "...", "reason": "<=30 words"}"""


def main():
    tax = [json.loads(l) for l in
           open(ROOT / "results/b33B_taxonomy.jsonl", encoding="utf-8")]
    ws = {w["uid"]: w for w in (json.loads(l) for l in
          open(ROOT / "results/b33B_writeside.jsonl", encoding="utf-8"))}
    runs = {}
    for f in ["results/b31_smoc_v22_full.jsonl", "results/b31_smoc_v23.jsonl",
              "results/b31_smoc_v24.jsonl"]:
        for l in open(ROOT / f, encoding="utf-8"):
            r = json.loads(l)
            runs[r["question_id"]] = r

    errs = [t for t in tax if not t["judge_correct"]]
    items = [t for t in errs if t["top_class"] in ("read", "gold")
             or t["question_type"] == "first_vs_last"]
    print(f"复裁 {len(items)} 题 × {N_PASSES} 遍 = {len(items)*N_PASSES} 次 haiku 调用")

    client = anthropic.Anthropic()
    out, tin, tout = [], 0, 0
    for t in items:
        w = ws[t["uid"]]
        chain = "\n".join(f"  {d} -> {v}" for d, v in w["ledger_chain"]) \
            or "  (empty: no states for this attribute were selectable)"
        user = (f"Question: {runs[t['question_id']]['question']}\n\n"
                f"State chain visible to the model (date -> value):\n{chain}\n\n"
                f"Gold answer: {t['gold_answer']}\n\n"
                f"Model response: {t['answer']}")
        labs, reasons = [], []
        for _ in range(N_PASSES):
            resp = client.messages.create(
                model=MODEL, max_tokens=300, system=SYS,
                messages=[{"role": "user", "content": user}])
            tin += resp.usage.input_tokens
            tout += resp.usage.output_tokens
            txt = "".join(b.text for b in resp.content if b.type == "text")
            try:
                j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
            except Exception:  # noqa: BLE001
                j = {"label": "PARSE_FAIL", "reason": txt[:120]}
            labs.append(j.get("label"))
            reasons.append(j.get("reason"))
        out.append(dict(question_id=t["question_id"], uid=t["uid"],
                        question_type=t["question_type"],
                        our_class=t["top_class"], write_mode=t["write_mode"],
                        labels=labs, reasons=reasons,
                        agree=bool(labs[0] == labs[1])))
        print(f"  {t['question_id']:<34} ours={t['top_class']:<5} haiku={labs}")

    (ROOT / "results/b33B_adjudication.jsonl").write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n",
        encoding="utf-8")

    print("\n两遍自一致:", sum(1 for o in out if o["agree"]), "/", len(out))
    print("pass1 标签:", dict(Counter(o["labels"][0] for o in out)))
    print("pass2 标签:", dict(Counter(o["labels"][1] for o in out)))
    MAP = {"model_wrong": "read", "gold_ambiguous": "gold",
           "judge_error": "gold", "ledger_insufficient": "write"}
    for p in (0, 1):
        cm = Counter((o["our_class"], MAP.get(o["labels"][p], "?")) for o in out)
        print(f"pass{p+1} 与本脚本主归类交叉(ours, haiku):", dict(cm))
    cost = tin / 1e6 * 1.0 + tout / 1e6 * 5.0
    print(f"\ntokens in={tin} out={tout}  成本 ≈ ${cost:.4f} "
          f"(haiku-4.5 $1/M in, $5/M out)")


if __name__ == "__main__":
    main()
