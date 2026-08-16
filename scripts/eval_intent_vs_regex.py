#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""去耦合验证:事件算术判定 —— 关键词正则 vs LLM 意图分类。

背景(耦合审计 08-15,risk=high):qvf_router._EVENT_ARITH_RE 是 7 个关键词
短语的正则,用作路由特征("事件算术题一律 direct")。审计指其"改写即漏"。

真值来源:results/paraphrase_set_20260815.jsonl 的 1107 条盲写改写题带算子
标签(改写不变量保证算子不变),因此有免费的 ground truth:
  正类(事件算术)= count_changes / count_before / longest
  负类(状态查值)= first_last / tag_filter / join_at_change
  (tag_trend 语义两可——按年分桶计数——予以排除,不计入任一侧)

用法: python scripts/eval_intent_vs_regex.py [--n-per-side 150]
成本: haiku,每题约 150 in / 1 out,300 题约 $0.05。
"""
import argparse
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

# 注意:不得在此 setdefault 假 API key —— qvf_router 的 load_dotenv 默认不
# 覆盖已存在的环境变量,假 key 会让所有调用静默失败并回落 False(首轮冒烟
# 就踩了这个坑:LLM 侧 0/20 全 NO)。真 key 由 .env 提供。
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

POS_OPS = {"count_changes", "count_before", "longest"}
NEG_OPS = {"first_last", "tag_filter", "join_at_change"}
SEED = 20260816


def load_module(llm_intent):
    os.environ["QVF_LLM_INTENT"] = "1" if llm_intent else "0"
    spec = importlib.util.spec_from_file_location(f"qr{llm_intent}",
                                                  "scripts/qvf_router.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def metrics(pairs):
    """pairs: [(pred, truth)] → dict"""
    tp = sum(1 for p, t in pairs if p and t)
    fp = sum(1 for p, t in pairs if p and not t)
    fn = sum(1 for p, t in pairs if not p and t)
    tn = sum(1 for p, t in pairs if not p and not t)
    rec = tp / (tp + fn) if tp + fn else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": rec, "precision": prec, "f1": f1,
            "accuracy": (tp + tn) / len(pairs) if pairs else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-side", type=int, default=150)
    ap.add_argument("--out", default="results/intent_vs_regex_20260816.jsonl")
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            open("results/paraphrase_set_20260815.jsonl", encoding="utf-8")]
    pos = [r for r in rows if r.get("op") in POS_OPS]
    neg = [r for r in rows if r.get("op") in NEG_OPS]
    rnd = random.Random(SEED)
    rnd.shuffle(pos)
    rnd.shuffle(neg)
    sample = ([(r, True) for r in pos[:args.n_per_side]] +
              [(r, False) for r in neg[:args.n_per_side]])
    rnd.shuffle(sample)
    print(f"评测集:正类 {sum(1 for _, t in sample if t)} / "
          f"负类 {sum(1 for _, t in sample if not t)}")

    qr_off = load_module(False)
    qr_on = load_module(True)

    out = []
    reg_pairs, llm_pairs = [], []
    for i, (r, truth) in enumerate(sample, 1):
        q = r["question_para"]
        key = f"{r['question_id']}#p{r.get('para_idx', 0)}"
        reg = qr_off.is_event_arith(q)
        llm = qr_on.is_event_arith(q, "intent_eval", key)
        reg_pairs.append((reg, truth))
        llm_pairs.append((llm, truth))
        out.append({"key": key, "op": r.get("op"), "truth": truth,
                    "regex": reg, "llm": llm, "question": q})
        if i % 50 == 0:
            print(f"  ... {i}/{len(sample)}")

    qr_on.INTENT_CACHE_F.write_text(
        json.dumps(qr_on.intent_cache, ensure_ascii=False), encoding="utf-8")
    Path(args.out).write_text(
        "\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n",
        encoding="utf-8")

    mr, ml = metrics(reg_pairs), metrics(llm_pairs)
    print()
    print(f"{'判定器':10s} {'准确率':>7s} {'召回':>7s} {'精确率':>7s} {'F1':>7s}"
          f"  {'TP':>4s} {'FP':>4s} {'FN':>4s} {'TN':>4s}")
    for nm, m in (("关键词正则", mr), ("LLM 意图", ml)):
        print(f"{nm:10s} {m['accuracy']*100:6.1f}% {m['recall']*100:6.1f}% "
              f"{m['precision']*100:6.1f}% {m['f1']*100:6.1f}%  "
              f"{m['tp']:4d} {m['fp']:4d} {m['fn']:4d} {m['tn']:4d}")
    print()
    print(f"召回提升 {(ml['recall']-mr['recall'])*100:+.1f}pp;"
          f"精确率变化 {(ml['precision']-mr['precision'])*100:+.1f}pp;"
          f"准确率 {(ml['accuracy']-mr['accuracy'])*100:+.1f}pp")
    print(f"逐题明细 → {args.out}")


if __name__ == "__main__":
    main()
