# -*- coding: utf-8 -*-
"""批 45:OpenAI 族判官复判(判官同族偏置排除)。

预注册:results/opt_batch45_prereg.md(先于本文件运行提交)。
判官提示词与 qvf.judge.ClaudeJudge 完全一致(同 JUDGE_SYSTEM_PROMPT、同
_judge_user_prompt),只换模型 -> gpt-5-mini(temperature=0 被 API 拒绝,
回退默认;reasoning_effort=minimal,详见预注册"偏离"节)。

用法: PYTHONUTF8=1 python scripts/b45_rejudge.py
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

from openai import OpenAI
from qvf.judge import JUDGE_SYSTEM_PROMPT, _judge_user_prompt

ROOT = Path(r"D:\ZZL_cluade")
N_THREADS = 4
MODEL = "gpt-5-mini"

ARMS = [
    ("direct", "results/b33A_direct.jsonl"),
    ("smoc_v45", "results/b33A_smoc_v45.jsonl"),
    ("smw", "results/b33A_smw.jsonl"),
    ("smwplain", "results/b33A_smwplain.jsonl"),
]

JSON_SUFFIX = (
    '\n\nReply with ONLY a JSON object: '
    '{"correct": true/false, "reason": "<one sentence>"}'
)

client = OpenAI()
print_lock = threading.Lock()


def dedupe_first(path: Path):
    """Keep FIRST occurrence per question_id (matches scripts/b33A_score.py)."""
    seen = {}
    raw = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "error" in r:
            continue
        raw += 1
        q = r["question_id"]
        if q not in seen:
            seen[q] = r
    return list(seen.values()), raw, len(seen)


def gpt_judge_one(r: dict) -> dict:
    """Judge one row with gpt-5-mini using the identical ClaudeJudge prompt."""
    question = r["question"]
    gold = r["gold_answer"]
    response = r.get("answer", "")
    qtype = r.get("question_type")
    user_prompt = _judge_user_prompt(question, gold, response, qtype, False) + JSON_SUFFIX

    last_error = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                max_completion_tokens=2048,
                reasoning_effort="minimal",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = resp.choices[0].message.content or ""
            verdict = json.loads(text)
            u = resp.usage
            return {
                "question_id": r["question_id"],
                "judge_correct_claude": bool(r.get("judge_correct")),
                "judge_correct_gpt": bool(verdict.get("correct")),
                "judge_reason_gpt": str(verdict.get("reason", ""))[:500],
                "usage": {
                    "input_tokens": getattr(u, "prompt_tokens", None),
                    "output_tokens": getattr(u, "completion_tokens", None),
                },
            }
        except Exception as e:  # noqa: BLE001
            last_error = e
    # both attempts failed -> containment-heuristic fallback, matches
    # qvf.judge.ClaudeJudge's own fallback policy
    ok = str(gold).strip().lower() in str(response).strip().lower()
    return {
        "question_id": r["question_id"],
        "judge_correct_claude": bool(r.get("judge_correct")),
        "judge_correct_gpt": ok,
        "judge_reason_gpt": f"FALLBACK containment heuristic after judge failure: {last_error}",
        "usage": {"input_tokens": None, "output_tokens": None},
    }


def run_arm(arm: str, path: str):
    rows, raw, deduped = dedupe_first(ROOT / path)
    out_path = ROOT / f"results/b45_rejudge_{arm}.jsonl"
    done = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["question_id"])
            except Exception:
                pass
    todo = [r for r in rows if r["question_id"] not in done]
    with print_lock:
        print(f"[{arm}] raw={raw} deduped={deduped} already_done={len(done)} todo={len(todo)}",
              file=sys.stderr)
    if not todo:
        return

    lock = threading.Lock()
    idx = {"i": 0}
    t0 = time.time()

    def worker():
        while True:
            with lock:
                i = idx["i"]
                if i >= len(todo):
                    return
                idx["i"] += 1
            r = todo[i]
            out = gpt_judge_one(r)
            with lock:
                with out_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(out, ensure_ascii=False) + "\n")
                n = i + 1
                if n % 40 == 0 or n == len(todo):
                    with print_lock:
                        print(f"[{arm}] {n}/{len(todo)} ({time.time()-t0:.0f}s)",
                              file=sys.stderr)

    threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def main():
    for arm, path in ARMS:
        run_arm(arm, path)
    print("done.", file=sys.stderr)


if __name__ == "__main__":
    main()
