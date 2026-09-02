# -*- coding: utf-8 -*-
"""批 33-G4:对已落盘的臂输出重跑 ClaudeJudge(只在判官那次失败/未记账时用)。

背景:诊断子臂第一版的读者代理把 qvf.judge 的 messages.parse 也挡掉了,
60 次判官调用全部落进 ClaudeJudge 的兜底"含金串"启发式(judgeusage 里
no_usage=60)。读者输出已存,重判即可,不必重跑读者。

用法: PYTHONUTF8=1 python scripts/ext_minteval_rejudge.py --in <jsonl>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from qvf.judge import ClaudeJudge  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--force", action="store_true",
                    help="全部重判(默认只重判 judge_input_tokens 缺失的行)")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.inp, encoding="utf-8") if l.strip()]
    judge = ClaudeJudge()
    n = ok = 0
    for r in rows:
        if not a.force and r.get("judge_input_tokens"):
            continue
        v = judge.judge(r["question"], str(r["gold_answer"]), r["answer"],
                        r.get("question_type"))
        r["judge_correct"] = v.correct
        r["judge_reason"] = v.reason
        r["judge_input_tokens"] = v.usage_input_tokens
        r["judge_output_tokens"] = v.usage_output_tokens
        r["rejudged"] = True
        n += 1
        ok += bool(v.correct)
        print("[%s] judge=%s" % (r["question_id"], v.correct), flush=True)
    with open(a.inp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    p = Path(a.inp).with_suffix(".judgeusage.json")
    p.write_text(json.dumps({"calls": judge.total_usage["calls"],
                             "input_tokens": judge.total_usage["input_tokens"],
                             "output_tokens": judge.total_usage["output_tokens"],
                             "no_usage": 0, "rejudge": True},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(bool(x.get("judge_correct")) for x in rows)
    print("rejudged %d rows (%d correct in this pass); file acc %d/%d = %.1f%%"
          % (n, ok, tot, len(rows), tot / max(1, len(rows)) * 100))
    print("judge usage ->", p, judge.total_usage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
