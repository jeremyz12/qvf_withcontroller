"""Lexical metrics (token F1 / exact match) and result aggregation."""

from __future__ import annotations

import re
import string
from collections import Counter, defaultdict
from typing import Dict, Iterable, List


def normalize_text(s: str) -> str:
    s = s.lower()
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def token_f1(prediction: str, gold: str) -> float:
    pred_tokens = normalize_text(prediction).split()
    gold_tokens = normalize_text(gold).split()
    if not pred_tokens or not gold_tokens:
        return float(pred_tokens == gold_tokens)
    common = Counter(pred_tokens) & Counter(gold_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision = num_same / len(pred_tokens)
    recall = num_same / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def exact_match(prediction: str, gold: str) -> bool:
    return normalize_text(prediction) == normalize_text(gold)


def aggregate_by_type(records: Iterable[dict], key: str = "question_type") -> Dict:
    """Aggregate accuracy / F1 by question type over result records.

    Each record is expected to carry: question_type, and optionally
    judge_correct (bool) and f1 (float).
    """
    by_type: Dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0, "f1_sum": 0.0})
    total = {"n": 0, "correct": 0, "f1_sum": 0.0}
    for r in records:
        t = str(r.get(key) or "unknown")
        by_type[t]["n"] += 1
        total["n"] += 1
        if r.get("judge_correct"):
            by_type[t]["correct"] += 1
            total["correct"] += 1
        f1 = r.get("f1")
        if f1 is not None:
            by_type[t]["f1_sum"] += f1
            total["f1_sum"] += f1

    def finish(d: dict) -> dict:
        n = max(d["n"], 1)
        return {
            "n": d["n"],
            "accuracy": d["correct"] / n,
            "mean_f1": d["f1_sum"] / n,
        }

    out = {t: finish(d) for t, d in sorted(by_type.items())}
    out["__overall__"] = finish(total)
    return out
