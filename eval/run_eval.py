"""Run baseline / QVF pipelines over a benchmark and score the results.

Examples:
    # Mock-mode plumbing check on LongMemEval oracle split
    set QVF_MOCK=1
    python eval/run_eval.py --benchmark longmemeval --data data/longmemeval_oracle.json --mode both --limit 2 --no-judge

    # Real run on 50 questions, QVF condition only
    python eval/run_eval.py --benchmark longmemeval --data data/longmemeval_s.json --mode qvf --limit 50 --out results/lme_s_qvf.jsonl

    # LoCoMo
    python eval/run_eval.py --benchmark locomo --data data/locomo10.json --mode both --limit 20

Outputs one JSONL record per (question, mode) with the hypothesis, validity
map, judge verdict, F1, and token usage; prints per-type aggregates at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

# Allow running as a script from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm

from eval.datasets import QAInstance, load_locomo, load_longmemeval
from eval.metrics import aggregate_by_type, token_f1
from qvf.judge import ClaudeJudge
from qvf.pipeline import (
    BaselinePipeline,
    FilterOnlyPipeline,
    PromptOnlyPipeline,
    QVFPipeline,
)

PIPELINE_CLASSES = {
    "baseline": BaselinePipeline,
    "qvf": QVFPipeline,
    "filter": FilterOnlyPipeline,
    "prompt-only": PromptOnlyPipeline,
}


def run_one(pipeline, instance: QAInstance) -> dict:
    t0 = time.time()
    result = pipeline.answer(
        instance.question, instance.memories, instance.question_date
    )
    elapsed = time.time() - t0
    record = {
        "question_id": instance.question_id,
        "question_type": instance.question_type,
        "question": instance.question,
        "gold_answer": instance.gold_answer,
        "is_abstention": instance.is_abstention,
        "answer": result.answer,
        "retrieved_memory_ids": result.retrieved_memory_ids,
        "adapter_warnings": result.adapter_warnings,
        "usage_input_tokens": result.usage_input_tokens,
        "usage_output_tokens": result.usage_output_tokens,
        "latency_s": round(elapsed, 2),
        "f1": token_f1(result.answer, instance.gold_answer),
    }
    if result.validity_map is not None:
        record["validity_map"] = result.validity_map.model_dump(mode="json")
    if result.analysis_text is not None:
        record["analysis_text"] = result.analysis_text
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", choices=["longmemeval", "locomo"], required=True)
    parser.add_argument("--data", required=True, help="Path to the dataset JSON file")
    parser.add_argument(
        "--mode",
        default="both",
        help="Comma-separated subset of {baseline,qvf,filter,prompt-only}, "
        "or 'both' (baseline+qvf) or 'all' (all four conditions)",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 = all questions")
    parser.add_argument(
        "--sample-per-type",
        type=int,
        default=0,
        help="Take the first N questions of each question type (abstention "
        "questions count as their own bucket). Applied before --limit.",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out", default=None, help="JSONL output path")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument(
        "--offset", type=int, default=0, help="Skip the first N questions"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Append to --out if it exists, skipping (question_id, mode) pairs "
        "already present",
    )
    args = parser.parse_args()

    loader = load_longmemeval if args.benchmark == "longmemeval" else load_locomo
    instances = loader(args.data)
    if args.sample_per_type:
        buckets: dict = {}
        sampled = []
        for inst in instances:
            key = "abstention" if inst.is_abstention else str(inst.question_type)
            if buckets.get(key, 0) < args.sample_per_type:
                buckets[key] = buckets.get(key, 0) + 1
                sampled.append(inst)
        instances = sampled
        print(f"Stratified sample: {buckets}")
    if args.offset:
        instances = instances[args.offset :]
    if args.limit:
        instances = instances[: args.limit]
    print(f"Loaded {len(instances)} QA instances from {args.data}")

    if args.mode == "both":
        modes = ["baseline", "qvf"]
    elif args.mode == "all":
        modes = list(PIPELINE_CLASSES)
    else:
        modes = [m.strip() for m in args.mode.split(",") if m.strip()]
        unknown = [m for m in modes if m not in PIPELINE_CLASSES]
        if unknown:
            parser.error(f"unknown mode(s): {unknown}")
    pipelines = {m: PIPELINE_CLASSES[m](top_k=args.top_k) for m in modes}
    judge = None if args.no_judge else ClaudeJudge()

    out_path = Path(
        args.out
        or f"results/{args.benchmark}_{args.mode}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    done: set = set()
    if args.resume and out_path.exists():
        with out_path.open("r", encoding="utf-8") as fin:
            for line in fin:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                done.add((r.get("question_id"), r.get("mode")))
                records.append(r)
        print(f"Resuming: {len(done)} (question, mode) pairs already done")

    open_mode = "a" if (args.resume and out_path.exists()) else "w"
    with out_path.open(open_mode, encoding="utf-8") as fout:
        for instance in tqdm(instances, desc="questions"):
            for mode, pipeline in pipelines.items():
                if (instance.question_id, mode) in done:
                    continue
                try:
                    record = run_one(pipeline, instance)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    record = {
                        "question_id": instance.question_id,
                        "question_type": instance.question_type,
                        "error": traceback.format_exc(limit=3),
                    }
                record["mode"] = mode
                if judge is not None and "error" not in record:
                    try:
                        verdict = judge.judge(
                            instance.question,
                            instance.gold_answer,
                            record["answer"],
                            instance.question_type,
                            instance.is_abstention,
                        )
                        record["judge_correct"] = verdict.correct
                        record["judge_reason"] = verdict.reason
                    except Exception:  # noqa: BLE001 — never let a judge error kill the run
                        traceback.print_exc()
                        record["judge_correct"] = None
                        record["judge_error"] = traceback.format_exc(limit=2)
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                fout.flush()
                records.append(record)

    print(f"\nWrote {len(records)} records to {out_path}")
    for mode in pipelines:
        mode_records = [r for r in records if r.get("mode") == mode and "error" not in r]
        errors = sum(1 for r in records if r.get("mode") == mode and "error" in r)
        print(f"\n=== {mode} (n={len(mode_records)}, errors={errors}) ===")
        aggregates = aggregate_by_type(mode_records)
        for qtype, stats in aggregates.items():
            print(
                f"  {qtype:_<30} n={stats['n']:>4}  "
                f"acc={stats['accuracy']:.3f}  f1={stats['mean_f1']:.3f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
