# -*- coding: utf-8 -*-
"""判官侧成本实测(冻结臂不落盘 judge usage,故离线复原后计量)。

输入侧 **精确**:逐行按 qvf.judge 的真实调用形状(JUDGE_SYSTEM_PROMPT 作
system、_judge_user_prompt 作 user)重建后调 messages.count_tokens
(免费端点,不产生推理费用),得到与判官实际收到的 input_tokens 同口径的计数。
输出侧 **抽样实测**:JudgeVerdict 是结构化短输出,用同一判官对 --sample 行
真跑一次读取 usage.output_tokens 取均值外推(默认 0 = 不跑,用 --out-mean 给定)。

用法:
  python scripts/ext_judge_cost_amemgym.py --in results/ext_amemgym_smoc.jsonl \
      --probe data/external/amemgym_probe.jsonl --out-mean 42
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from qvf import config  # noqa: E402
from qvf.judge import JUDGE_SYSTEM_PROMPT, _judge_user_prompt  # noqa: E402

PRICE = {"claude-opus-5": (5.0, 25.0), "claude-haiku-4-5": (1.0, 5.0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0=全量精确计数")
    ap.add_argument("--out-mean", type=float, required=True,
                    help="判官输出 token 均值(抽样实测值)")
    a = ap.parse_args()

    model = config.DEFAULT_JUDGE_MODEL
    pin, pout = PRICE[model]
    client = anthropic.Anthropic()
    rows = [json.loads(l) for l in open(a.inp, encoding="utf-8") if l.strip()]
    if a.limit:
        rows = rows[:a.limit]
    counts = []
    for i, r in enumerate(rows):
        up = _judge_user_prompt(r["question"], str(r["gold_answer"]),
                                r["answer"], r.get("question_type"), False)
        c = client.messages.count_tokens(
            model=model,
            system=[{"type": "text", "text": JUDGE_SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": up}])
        counts.append(c.input_tokens)
        if (i + 1) % 100 == 0:
            print(f"  counted {i+1}/{len(rows)}", flush=True)
    tot_in = sum(counts)
    n = len(rows)
    tot_out = a.out_mean * n
    cost = (tot_in * pin + tot_out * pout) / 1e6
    print(json.dumps({
        "file": a.inp, "judge_model": model, "n_rows": n,
        "judge_input_tokens_exact": tot_in,
        "judge_input_tokens_mean": round(statistics.mean(counts), 1),
        "judge_output_tokens_mean_sampled": a.out_mean,
        "judge_output_tokens_extrapolated": tot_out,
        "judge_cost_usd": round(cost, 4),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
