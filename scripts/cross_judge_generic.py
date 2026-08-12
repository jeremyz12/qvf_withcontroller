"""Cross-family judge replication: gpt-5-mini re-judges the STALE-Chain
held-out arms (dense_direct + minimal_rules_species2) that claude-opus judged,
closing the generator-family==judge-family circularity channel.

Outputs per-arm accuracy under the OpenAI judge, opus/gpt judge agreement,
and the re-derived paired sign test.
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from openai import OpenAI

from qvf.judge import JUDGE_SYSTEM_PROMPT

client = OpenAI()

rows = []
for f in glob.glob(r"D:\ZZL_cluade\results\chainfull_s*.jsonl"):
    for l in open(f, encoding="utf-8"):
        s = l.strip()
        if not s:
            continue
        r = json.loads(s)
        if "error" in r:
            continue
        rows.append(r)

print(f"re-judging {len(rows)} rows with gpt-5-mini", file=sys.stderr)
out_path = Path(r"D:\ZZL_cluade\results\chainfull_crossjudge.jsonl")
done = set()
if out_path.exists():
    for l in open(out_path, encoding="utf-8"):
        try:
            d = json.loads(l)
            done.add((d["question_id"], d["mode"]))
        except Exception:
            pass

with out_path.open("a", encoding="utf-8") as fout:
    for i, r in enumerate(rows):
        key = (r["question_id"], r["mode"])
        if key in done:
            continue
        user = (
            f"QUESTION: {r['question']}\n\n"
            f"GOLD ANSWER: {r['gold_answer']}\n\n"
            f"MODEL RESPONSE: {r.get('answer','')}\n\n"
            f"QUESTION TYPE: {r.get('question_type')}\n"
            f"ABSTENTION QUESTION: no\n\n"
            "Reply with ONLY a JSON object: "
            '{"correct": true/false, "reason": "<one sentence>"}'
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-5-mini",
                max_completion_tokens=2048,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            )
            text = resp.choices[0].message.content or ""
            start = text.index("{")
            end = text.rindex("}") + 1
            verdict = json.loads(text[start:end])
            fout.write(json.dumps({
                "question_id": r["question_id"],
                "mode": r["mode"],
                "opus_correct": bool(r.get("judge_correct")),
                "gpt_correct": bool(verdict.get("correct")),
                "gpt_reason": str(verdict.get("reason", ""))[:200],
            }, ensure_ascii=False) + "\n")
            fout.flush()
        except Exception as e:  # noqa: BLE001
            fout.write(json.dumps({
                "question_id": r["question_id"], "mode": r["mode"],
                "error": str(e)[:200]}) + "\n")
            fout.flush()
        if (i + 1) % 50 == 0:
            print(f"{i+1}/{len(rows)}", file=sys.stderr)

# summary
from collections import defaultdict
from math import comb

agree = tot = 0
acc = defaultdict(lambda: [0, 0])
pair = defaultdict(dict)
for l in open(out_path, encoding="utf-8"):
    d = json.loads(l)
    if "error" in d:
        continue
    tot += 1
    agree += int(d["opus_correct"] == d["gpt_correct"])
    acc[d["mode"]][0] += int(d["gpt_correct"])
    acc[d["mode"]][1] += 1
    pair[d["question_id"]][d["mode"]] = d["gpt_correct"]
print(f"judge agreement: {agree}/{tot} = {agree/max(1,tot):.1%}")
for m, (a, n) in acc.items():
    print(f"gpt-judge acc {m}: {a}/{n} = {a/max(1,n):.1%}")
w = l2 = 0
for qid, d in pair.items():
    if len(d) < 2:
        continue
    x = d.get("dense_direct")
    y = d.get("minimal_rules_species2")
    if y and not x:
        w += 1
    elif x and not y:
        l2 += 1
n = w + l2
p = sum(comb(n, k) for k in range(w, n + 1)) / 2**n if n else 1.0
print(f"paired under gpt judge: W={w} L={l2} p={p:.2e}")
