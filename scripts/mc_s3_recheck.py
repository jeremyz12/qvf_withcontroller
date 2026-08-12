# -*- coding: utf-8 -*-
"""MemConflict 问题标签 opus 复核:同一分类提示词,haiku 标签 vs opus 标签。

决定 MC 名义 60% 在题率是否成立(尤其 S3 标签是否虚高)。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from scripts.problem_align_slice import CLS_PROMPT, ProblemClass, load_rows  # noqa: E402

MODEL = "claude-opus-5"
raw_cache = json.loads(Path(r"results/problem_labels.json").read_text(encoding="utf-8"))
cache = {k.split("|", 1)[1]: v for k, v in raw_cache.items()
         if k.startswith("MemConflict|")}
rows = load_rows(r"results/mc_fresh_direct.jsonl", "dense_direct")
if not rows:
    rows = load_rows(r"results/final_mc_h45.jsonl")
mc_qids = [q for q in rows if q in cache]
print(f"MC questions with cached labels: {len(mc_qids)}")

client = anthropic.Anthropic()
out = {}
agree = 0
for i, qid in enumerate(mc_qids):
    r = rows[qid]
    old = cache[qid]["label"] if isinstance(cache[qid], dict) else cache[qid]
    new, reason = "?", ""
    for attempt in range(3):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=2000,
                system=CLS_PROMPT,
                messages=[{"role": "user", "content":
                           f"QUESTION: {r.get('question','')}\n\nGOLD ANSWER: {r.get('gold_answer','')}"}],
                output_format=ProblemClass,
            )
            if resp.parsed_output:
                new, reason = resp.parsed_output.label, resp.parsed_output.reason
                break
        except Exception as e:  # noqa: BLE001
            print(f"[{qid}] attempt {attempt}: {type(e).__name__}", flush=True)
    out[qid] = {"haiku": old, "opus": new, "reason": reason}
    if new == old:
        agree += 1
    if (i + 1) % 20 == 0:
        print(f"[{i+1}/{len(mc_qids)}] agree so far {agree}/{i+1}", flush=True)

Path(r"results/mc_labels_opus.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
from collections import Counter
h = Counter(v["haiku"] for v in out.values())
o = Counter(v["opus"] for v in out.values())
ins_h = sum(c for k, c in h.items() if k != "OUT")
ins_o = sum(c for k, c in o.items() if k != "OUT")
n = len(out)
print("haiku dist:", dict(h), f"in-scope {ins_h}/{n} = {ins_h/n*100:.0f}%")
print("opus  dist:", dict(o), f"in-scope {ins_o}/{n} = {ins_o/n*100:.0f}%")
print(f"agreement: {agree}/{n} = {agree/n*100:.0f}%")
s3flip = sum(1 for v in out.values() if v["haiku"] == "S3" and v["opus"] != "S3")
print(f"S3(haiku) flipped by opus: {s3flip}/{h.get('S3', 0)}")
