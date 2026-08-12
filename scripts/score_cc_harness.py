# -*- coding: utf-8 -*-
"""判分 Claude Code harness 测试的答卷:与主实验同一个 opus 判官,可与阶梯直接对比。

用法:python scripts/score_cc_harness.py [答卷路径,默认 cc_harness_test/answers.jsonl]
答卷格式:每行 {"question_id": "...", "answer": "..."}
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from qvf.judge import ClaudeJudge  # noqa: E402

ans_path = sys.argv[1] if len(sys.argv) > 1 else r"cc_harness_test\answers.jsonl"
if "deploy_dim2" in ans_path:
    key_path = r"results\cc_harness_key_stale400.json"
    exam_path = r"cc_harness_test\exam_stale400_s50.json"
elif "stale400t2" in ans_path:
    key_path = r"results\cc_harness_key_stale400t2.json"
    exam_path = r"cc_harness_test\exam_stale400t2_s50.json"
elif "stale400" in ans_path:
    key_path = r"results\cc_harness_key_stale400.json"
    exam_path = r"cc_harness_test\exam_stale400_s50.json"
else:
    key_path = r"results\cc_harness_key.json"
    exam_path = r"cc_harness_test\exam_chain53.json"
key = json.load(open(key_path, encoding="utf-8"))
exam = json.load(open(exam_path, encoding="utf-8"))
q_text = {q["question_id"]: q["question"] for it in exam for q in it["questions"]}

answers = {}
for l in open(ans_path, encoding="utf-8"):
    s = l.strip()
    if not s:
        continue
    r = json.loads(s)
    answers[r["question_id"]] = r["answer"]

judge = ClaudeJudge()
agg = defaultdict(lambda: [0, 0])
rows = []
for qid, gold in key.items():
    if qid not in answers:
        continue
    v = judge.judge(q_text[qid], gold["gold"], answers[qid],
                    question_type=f"chain-{gold['dim']}")
    agg[gold["dim"]][0] += int(v.correct)
    agg[gold["dim"]][1] += 1
    rows.append({"question_id": qid, "dim": gold["dim"],
                 "judge_correct": v.correct, "judge_reason": v.reason})

out = Path(ans_path).with_suffix(".judged.jsonl")
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
               encoding="utf-8")
tot = sum(v[0] for v in agg.values())
n = sum(v[1] for v in agg.values())
total_q = len(key)
print(f"已判 {n}/{total_q}(缺 {total_q-n})")
for k, v in sorted(agg.items()):
    print(f"  {k}: {v[0]}/{v[1]} = {v[0]/max(1,v[1]):.1%}")
print(f"  TOTAL: {tot}/{n} = {tot/max(1,n):.1%}")
if "stale400" in ans_path:
    print("""
参照(同 50 条 150 问切片,haiku-4.5 读者):
  dense 直读 34.0% | QVF 39.9% | 政策提示 51.3%
  oracle 直读 48.7% | oracle QVF 49.3%""")
else:
    print("""
参照(同 212 问,haiku-4.5 读者):
  直读 top-10 39.6% | QVF 59.2% | 政策提示 65.1%
  全文直读 53.3% | 全文提示 84.4% | 全文+QVF 78.3% | oracle+QVF 87.3%""")
print(f"明细已存 {out}")
