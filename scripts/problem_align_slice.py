# -*- coding: utf-8 -*-
"""问题对齐重切分:按"多状态时序选取"定义逐题分类既有基准,
再用已有判分行在【含问题子集】上重出配对判决(零新实验)。

分类:S1 当前态选取 / S2 点时刻回溯 / S3 轨迹重建 / S4 过时前提反驳 /
OUT 超纲(静态事实、时长/排序计算、错误信息冲突、条件共存、弃答等)。"""
import glob
import json
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402


class ProblemClass(BaseModel):
    label: str = Field(description="One of: S1, S2, S3, S4, OUT")
    reason: str = Field(description="One short clause.")


CLS_PROMPT = """Classify whether this QA item instantiates the Temporal State
Selection problem: an attribute of a person/entity has MULTIPLE values over
time in the memory history, and answering requires selecting/combining the
right state(s) by time semantics.

Labels:
- S1: asks the CURRENT value of an attribute that has been updated over time.
- S2: asks the value AT a specific past time/date (requires interval reasoning
  over state validity periods).
- S3: asks how the value EVOLVED / the ordered history of states.
- S4: the question PRESUPPOSES an outdated value while asking for help.
- OUT: anything else — static fact never updated, duration/elapsed-time
  arithmetic, event ordering between different events, misinformation vs truth
  conflicts, conditional coexisting values, unanswerable/abstention checks,
  aggregation/counting, preferences without state change.

Judge from the question AND the gold answer (the gold reveals whether an update
exists)."""


def load_rows(pat, mode=None):
    d = {}
    for f in glob.glob(pat):
        for l in open(f, encoding="utf-8"):
            s = l.strip()
            if not s:
                continue
            r = json.loads(s)
            if "error" in r:
                continue
            if mode and r.get("mode") != mode:
                continue
            d[r["question_id"]] = r
    return d


BENCHES = [
    ("LME-TR",
     (r"results/tr_full133.jsonl", "dense_direct"),
     (r"results/final2_lmet_h45.jsonl", None),
     (r"results/final2_lmet_gpt_direct.jsonl", None),
     (r"results/final2_lmet_gpt_species2.jsonl", None)),
    ("LME-KU",
     (r"results/final2_lmek_h45.jsonl", "dense_direct"),
     (r"results/final2_lmek_h45.jsonl", "minimal_rules_species2"),
     (r"results/final2_lmek_gpt.jsonl", "dense_direct"),
     (r"results/final2_lmek_gpt.jsonl", "minimal_rules_species2")),
    ("MemConflict",
     (r"results/mc_fresh_direct.jsonl", "dense_direct"),
     (r"results/final_mc_h45.jsonl", None),
     (r"results/final_mc_gpt_direct.jsonl", None),
     (r"results/final_mc_gpt_species2.jsonl", None)),
    ("LoCoMo-adv",
     (r"results/final_lca_h45_direct.jsonl", None),
     (r"results/final_lca_h45.jsonl", None),
     (r"results/final_lca_gpt_direct.jsonl", None),
     (r"results/final_lca_gpt_abstain.jsonl", None)),
    ("LoCoMo-single",
     (r"results/final_lcs_h45_direct.jsonl", None),
     (r"results/final_lcs_h45.jsonl", None),
     (r"results/final_lcs_gpt_direct.jsonl", None),
     (r"results/final_lcs_gpt_abstain.jsonl", None)),
]

CACHE = Path(r"results/problem_labels.json")


def p1s(w, l):
    n = w + l
    return sum(comb(n, k) for k in range(max(w, l), n + 1)) / 2 ** n if n else 1.0


def main():
    client = anthropic.Anthropic()
    labels = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    for name, d_h, q_h, d_g, q_g in BENCHES:
        base_h = load_rows(*d_h)
        for qid, r in base_h.items():
            key = f"{name}|{qid}"
            if key in labels:
                continue
            try:
                resp = client.messages.parse(
                    model="claude-haiku-4-5", max_tokens=300,
                    system=[{"type": "text", "text": CLS_PROMPT,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content":
                               f"QUESTION: {r.get('question','')}\n"
                               f"GOLD ANSWER: {str(r.get('gold_answer',''))[:400]}"}],
                    output_format=ProblemClass,
                )
                pc = resp.parsed_output
                labels[key] = pc.label if pc else "OUT"
            except Exception:
                labels[key] = "?"
        CACHE.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
        print(f"[{name}] classified {sum(1 for k in labels if k.startswith(name+'|'))}",
              flush=True)

    print("\n== 问题对齐配对判决(仅含题子集 S1-S4)==")
    for name, d_h, q_h, d_g, q_g in BENCHES:
        for stack, d_spec, q_spec in (("haiku", d_h, q_h), ("gpt", d_g, q_g)):
            base = load_rows(*d_spec)
            arm = load_rows(*q_spec)
            in_w = in_l = in_n = out_w = out_l = out_n = 0
            for qid, r in arm.items():
                b = base.get(qid)
                if not b:
                    continue
                lab = labels.get(f"{name}|{qid}", "OUT")
                p1 = bool(b.get("judge_correct"))
                p2 = bool(r.get("judge_correct"))
                w = 1 if (p2 and not p1) else 0
                l = 1 if (p1 and not p2) else 0
                if lab in ("S1", "S2", "S3", "S4"):
                    in_w += w; in_l += l; in_n += 1
                else:
                    out_w += w; out_l += l; out_n += 1
            print(f"{name:12s} {stack:5s} 含题子集 n={in_n:3d}: QVF {in_w}胜{in_l}负 "
                  f"p={p1s(in_w, in_l):.3g} | 超纲 n={out_n:3d}: {out_w}胜{out_l}负")
    from collections import Counter
    for name, *_ in BENCHES:
        c = Counter(v for k, v in labels.items() if k.startswith(name + "|"))
        print(f"{name} 问题含量: {dict(c)}")


if __name__ == "__main__":
    main()
