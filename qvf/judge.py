"""LLM-as-judge scoring of QA hypotheses.

NOTE ON COMPARABILITY: the official LongMemEval evaluation uses a GPT-4o judge
with per-question-type prompts; LoCoMo papers variously use F1, BLEU, and LLM
judges. This project standardizes on a Claude judge (identical across all
conditions), so absolute numbers are not directly comparable to other papers'
tables — within-paper comparisons (baseline vs QVF, ablations) are the primary
claims. Token-F1 for LoCoMo is additionally reported via eval/metrics.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from qvf import config


class JudgeVerdict(BaseModel):
    correct: bool = Field(
        description="Whether the model response is correct with respect to the gold answer."
    )
    reason: str = Field(description="One-sentence justification for the verdict.")


JUDGE_SYSTEM_PROMPT = """\
You are an impartial grader of question-answering systems that answer questions
about a user's long-term conversational history.

You will be given the question, the gold (reference) answer, and a model
response. Decide whether the model response is correct.

Grading rules (aligned with the official LongMemEval per-type protocol):
- Default: the response is correct if it contains the information of the gold
  answer, even with different wording, extra correct context, or a different
  format (dates may be expressed differently if they denote the same time).
  Answering only a subset of a multi-part gold answer is incorrect.
- The response is incorrect if it contradicts the gold answer, omits the asked
  information, or answers a different question.
- knowledge-update questions: correct as long as the response contains the
  UPDATED answer, even if it also mentions the outdated information.
- temporal-reasoning questions: the time/date/duration must match the gold
  answer, but off-by-one errors in day/week/month counting are acceptable.
- preference questions: the gold answer is a rubric; the response is correct
  if it is a reasonable personalized answer consistent with the rubric — it
  does not need to cover every rubric point.
- Abstention questions (marked in the input): correct if and only if the
  response identifies the question as unanswerable / declines / states the
  information is missing; any concrete guess is incorrect.
- Judge only correctness, not style or completeness beyond the asked fact.
"""


def _judge_user_prompt(
    question: str,
    gold_answer: str,
    response: str,
    question_type: Optional[str] = None,
    is_abstention: bool = False,
) -> str:
    parts = [f"QUESTION: {question}"]
    if question_type:
        parts.append(f"QUESTION TYPE: {question_type}")
    if is_abstention:
        parts.append(
            "NOTE: This is an abstention question — the information is NOT "
            "answerable from the user's history; a correct response must decline."
        )
    parts.append(f"GOLD ANSWER: {gold_answer}")
    parts.append(f"MODEL RESPONSE: {response}")
    return "\n\n".join(parts)


@dataclass
class JudgeResult:
    correct: bool
    reason: str


class ClaudeJudge:
    def __init__(
        self,
        model: Optional[str] = None,
        client: Optional[anthropic.Anthropic] = None,
        mock: Optional[bool] = None,
    ):
        self.model = model or config.DEFAULT_JUDGE_MODEL
        self.mock = config.mock_mode() if mock is None else mock
        self._client = client
        if not self.mock and self._client is None:
            self._client = anthropic.Anthropic()

    def judge(
        self,
        question: str,
        gold_answer: str,
        response: str,
        question_type: Optional[str] = None,
        is_abstention: bool = False,
    ) -> JudgeResult:
        if self.mock:
            # Trivial containment heuristic for plumbing tests.
            ok = gold_answer.strip().lower() in response.strip().lower()
            return JudgeResult(correct=ok, reason="mock containment check")
        user_prompt = _judge_user_prompt(
            question, gold_answer, response, question_type, is_abstention
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                api_response = self._client.messages.parse(
                    model=self.model,
                    max_tokens=config.JUDGE_MAX_TOKENS,
                    system=[
                        {
                            "type": "text",
                            "text": JUDGE_SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_prompt}],
                    output_format=JudgeVerdict,
                )
                verdict: JudgeVerdict = api_response.parsed_output
                if verdict is not None:
                    return JudgeResult(correct=verdict.correct, reason=verdict.reason)
                last_error = RuntimeError("parsed_output is None")
            except Exception as e:  # noqa: BLE001 — degenerate outputs raise ValidationError
                last_error = e
        # Both attempts failed (e.g. degenerate/truncated JSON): fall back to a
        # containment heuristic and mark the record so it can be re-judged.
        ok = gold_answer.strip().lower() in response.strip().lower()
        return JudgeResult(
            correct=ok,
            reason=f"FALLBACK containment heuristic after judge failure: {last_error}",
        )
