# Batch 45 pre-registration: OpenAI-family re-judge (judge-family bias check)

Filed 2026-09-04, before scripts/b45_rejudge.py is run. Committed record of
what will be tested and how a pass/fail is read, so the analysis script
cannot be tuned to the outcome after the fact.

## Motivation

The main-table verdicts (results/b33A_score_out.txt, headline direct→smoc
+41.49pp on corpus v2.4/store v45/haiku-4.5 readers) were all scored by
`qvf.judge.ClaudeJudge` (default model `claude-opus-5`). The readers being
judged are also Claude-family (haiku-4.5) and the QVF generator/adapter
stack elsewhere in the project uses claude-opus-5 too. This raises a
judge-family bias concern: an opus-5 judge could be systematically lenient
or harsh toward Claude-family outputs in a way that inflates or deflates the
headline. Precedent for closing this exact channel exists in this repo —
`scripts/cross_judge_generic.py`, `scripts/cross_judge_chain.py`, and
`scripts/crossjudge_s5_twin.py` all re-judge archived Claude-judged rows
with `gpt-5-mini` via the OpenAI API, reusing `qvf.judge.JUDGE_SYSTEM_PROMPT`
verbatim. Batch 45 repeats that pattern on the four b33A key arms in full
(all 576 rows each, not a stratified sample).

## Judge prompt: identical text, model swapped only

- System prompt: `qvf.judge.JUDGE_SYSTEM_PROMPT`, byte-identical, passed
  verbatim as the `system` message to the OpenAI call (no ephemeral cache
  control — that is an Anthropic-only param, dropped as a mechanical
  necessity, not a wording change).
- User prompt: built with `qvf.judge._judge_user_prompt(question,
  gold_answer, response, question_type, is_abstention)` — the exact same
  function ClaudeJudge calls, not a hand-rolled re-implementation. (Note:
  this is stricter than the three precedent scripts above, which used a
  hand-rolled user-prompt string with a slightly different field order and
  an explicit "ABSTENTION QUESTION: no" line. Batch 45 imports the library
  function directly so the two judges see byte-identical user text, modulo
  the JSON-output instruction appended below.) `is_abstention` is always
  `False`: batch 45's four arms (direct, smoc_v45, smw, smwplain) run over
  `data/wsc_s5_v2.jsonl`, whose 576 questions are entirely
  change_count/count_before/first_vs_last/longest_tenure — zero abstention
  items (checked: `grep -c abstention data/wsc_s5_v2.jsonl` = 0).
- Output-format instruction: ClaudeJudge gets structured output via
  Anthropic's `messages.parse(..., output_format=JudgeVerdict)`, which has
  no direct Chat Completions equivalent. Appended one line to the user
  prompt — `Reply with ONLY a JSON object: {"correct": true/false,
  "reason": "<one sentence>"}` — and set `response_format={"type":
  "json_object"}` on the OpenAI call. This changes the output-parsing
  *mechanism*, not the grading instructions themselves; recorded as a
  deviation, not silently absorbed.
- Model: `gpt-5-mini` via `openai.OpenAI().chat.completions.create`,
  matching the three precedent scripts.
- Temperature: tested `temperature=0` first as instructed. Rejected by the
  API — `Unsupported value: 'temperature' does not support 0 with this
  model. Only the default (1) value is supported.` (verified live,
  2026-09-04). Falls back to default (unset, effectively 1), matching every
  precedent script, none of which passed `temperature` either.
- Reasoning effort: set `reasoning_effort="minimal"` (not present in any
  precedent script, which left it at the API default — "medium" for
  gpt-5-mini). This is a deliberate deviation for cost/latency control on a
  2304-call run; a smoke test on one row showed minimal effort still lands
  a correct, well-reasoned verdict with 0 hidden reasoning tokens billed vs.
  a nonzero, unbounded amount at default effort. Recorded as a deviation —
  if H1 fails, minimal-effort judging is the first thing to re-test at
  default effort on the disagreement set.
- Retry/fallback policy mirrors `ClaudeJudge.judge`: 2 attempts, then a
  containment-heuristic fallback (`gold_answer.strip().lower() in
  response.strip().lower()`) with the reason string prefixed `FALLBACK`.

## Scope

Four arms, `results/b33A_direct.jsonl`, `results/b33A_smoc_v45.jsonl`,
`results/b33A_smw.jsonl`, `results/b33A_smwplain.jsonl`. Dedupe by first
occurrence of `question_id` (matching `scripts/b33A_score.py`'s rule) —
checked in advance: all four files are already 576 raw rows / 576 unique
`question_id` (no duplicate writes for these particular arms per
`results/b33A_score_out.txt` §0), so dedup is a no-op here but the script
implements it generically anyway, matching project convention.

Output: `results/b45_rejudge_<arm>.jsonl`, one row per question with
`question_id, judge_correct_claude, judge_correct_gpt, judge_reason_gpt,
usage`. 4 worker threads.

## Hypotheses (stated before running)

- **H1 (per-row agreement):** for each of the four arms, per-row agreement
  between `judge_correct_claude` (archived) and `judge_correct_gpt` (new)
  is ≥ 90%.
- **H2 (headline stability):** the smoc_v45 − direct accuracy delta under
  the gpt judge is within ±5pp of the archived Claude-judge headline
  +41.49pp (v2.4 corpus, 576 q, results/b33A_score_out.txt §5 A1).
- **H3 (per-arm accuracy stability):** no arm's accuracy (gpt judge vs.
  Claude judge, same 576 rows) moves by more than 5pp.

Falling short of any of H1–H3 does not by itself overturn the main-table
result — QVF's own conditional-completeness work (§25 "K 移植" in
`results/opt_batch29_verdict.md`) already shows judge/grading-axis choice
can shift absolute numbers while leaving the QVF-favoring direction intact.
A miss here would be read as "the headline is judge-sensitive, investigate
which axis," not as an automatic reversal — that follow-up is not
prosecuted in this batch.

## Explicitly not covered by this batch

- filter/usability/compile/summary/smoc_v45g arms (only the four named key
  arms from the task).
- No re-run of chain-level sign tests, TOST, or cluster bootstrap under the
  gpt judge — those all require the full 9-arm ladder infrastructure and
  are out of scope; batch 45 reports arm-level accuracy, per-row agreement/
  κ, and McNemar only on the three requested ladder deltas (smoc−direct,
  smw−smwplain, smoc−smw).
- No claim about *why* any disagreement occurs beyond the 10-example
  qualitative read per arm requested in the task.
