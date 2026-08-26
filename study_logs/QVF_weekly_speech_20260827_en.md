# QVF Weekly Report — Speech Script (Aug 27, 2026, English)

> Pairs with study_logs/QVF_weekly_20260827_en.pptx (16 slides). ~14–16 minutes at
> a normal pace. Bracketed lines are presenter notes, not to be read aloud.

---

## Slide 1 — Title (15s)

Good morning. This is the weekly update on QVF — Query-conditioned Validity
Filtering — our memory system for state questions in long-horizon conversations,
evaluated on our WikiState benchmark. This week was about verification, repair,
and infrastructure, so let me start with what changed.

## Slide 2 — This Week at a Glance (60s)

Six things happened this week. First, the headline number was re-verified: a full
independent rerun scored 89.0 against the original 87.8, inside the preregistered
two-point criterion, so the "pending re-verification" qualifier is removed and the
official headline is 88.4. Second, the ablation ladder on the cleaned v2 arena is
now complete — every stage is individually significant. Third, we repaired our
weakest question type through a preregistered fix — I'll show the full loop.
Fourth, the sixteen-system comparison is finalized, including a measured ceiling
for systems that stamp validity at write time. Fifth, the human verification
platform is live at rate dot wikistate dot org. And sixth, two honest-accounting
updates: we audited our own chain extraction on a natural corpus and filed the
result to limitations, and we reframed the cost claim to "same accuracy at one
fifth of the read cost."

## Slide 3 — Headline Re-verified (45s)

The discipline here: the criterion was written before the rerun — if the second
full run landed within two points of the first, the qualifier comes off. It landed
at 89.0, a gap of plus 1.2. So we now report the mean of the two runs, 88.4, with
both raw values. Per question type, the weakest is still counting — seventy-eight
percent — which is exactly what the next slide is about.

## Slide 4 — Repair Loop (75s)

This is the piece of the week I'd like you to remember, because it's a complete
diagnose-treat-verify loop. Diagnosis: our executor answers "how many times did I
change X" by counting chain rows. If a stray card sneaks into the chain, the code
confidently returns the wrong number. Treatment: we run a membership filter
before counting — a model proposes whether each card really belongs, but it must
attach a verbatim quote, and plain code authorizes the decision through string
containment checks. The acceptance criteria were written dead before running:
at least six points, p below 0.05, no regression on the guard type, no empty-pool
side effect. All three passed: fifty-five point six to sixty-three point nine,
the guard type actually improved, zero side effects, one dollar sixty total.
The full system moves from seventy-five point nine to seventy-eight point eight.
One exploratory note: after this repair, the gap between our two answer paths
narrows from six point eight to three point eight — once chains are clean, the
two ends converge. That tells us the gap was chain-noise tolerance, not a
fundamental difference.

## Slide 5 — Recap: One Memory, Three Validities (45s)

For anyone new to the project, the core idea in one exhibit. Take one memory —
"1989, I officially started at CERN." Ask three questions today. "Where do I work
now?" — that memory is expired. "Where did I work in 1990?" — it is the answer.
"How many times did I change employer?" — it is required evidence. Same memory,
same day, three different validities. So validity is a function of the memory
AND the query — it cannot be precomputed at write time. Systems that stamp
validity at write time hit a measured ceiling of eleven point seven percent on
our arena, against our eighty-three. That gap is mechanism, not engineering.

## Slide 6 — Pipeline Pseudocode (60s)

Here is the whole system as pseudocode — this was requested last time, and every
line maps to a function in the repository. Write side: each state declaration
becomes a card — value, date, and a verbatim quote; if the quote is not a
character-for-character substring of the source, the card is rejected. That's the
anti-hallucination anchor. Read side: the language model appears exactly twice —
once to translate the question into a small formal plan, once at the end to
phrase the answer. Everything between is code: keyed selection, date sorting,
adjacent merging, the membership filter for counting types, empty-chain fallback
to retrieval, and a deterministic executor. The number in the answer is decided
by code; the model cannot change it.

## Slide 7 — Executor (30s)

And the executor is almost embarrassingly simple — one line per question type.
Times changed is chain length minus one. Value at time t is an interval lookup.
Longest tenure is closed-interval day arithmetic. The point: once the chain is
right, temporal reasoning degenerates into array operations. That's the whole
design bet — and it's why answers are auditable and repairable.

## Slide 8 — One Question's Journey (45s)

Let me run the pipeline once more, from the data's point of view. Fifty thousand
characters of raw chat become seventy-eight cards at write time. When a question
arrives it is compiled into a two-field plan; cards are selected and date-sorted;
the membership filter ejects stray cards — seventy-five of them in last week's
batch; chaining leaves four rows, one per real transition; the executor computes
the number — and the answer is fixed right there; the reader model only phrases
it. Fifty thousand characters, seventy-eight cards, four rows, one number, one
sentence. Only noise is ever dropped, determinism rises toward the answer, and
every intermediate is saved to disk — that is what auditable physically means,
and why last week's repair could localize its target.

## Slide 9 — v2 Ladder (60s)

Main results on the cleaned arena — 576 questions, same reader, same judge,
paired tests. Reading down: plain retrieval forty-eight point six; organizing
evidence buys fourteen points; certifying roles buys three; letting code compute
the conclusion buys ten — each step individually significant, and the full
structure value is twenty-seven point three points at p equals ten to the minus
twenty-five, on an arena where every known exploit has been removed. The last
two rows: the cited reading protocol over the raw transcript, versus over our
ledger — statistically the same accuracy, at one fifth point five of the cost.
One footnote for rigor: the seventy-eight point eight includes this week's
repair; the plus-ten margin was measured pre-repair. And please note — v1 and
v2 absolute scores are not comparable; v2 is deliberately harder.

## Slide 10 — Sixteen Systems (45s)

The landscape table. Most commercial memory products score below plain
retrieval on state questions — Mem0 at twenty-seven, LangMem at forty, A-MEM at
forty-three against a fifty-two baseline — so the baseline is not a strawman;
the products actively hurt. Each row got a mechanism autopsy: extraction loses
chains, graph systems rank chit-chat edges above state edges. And the
stamp-at-write ledger at eleven point seven is the measured ceiling I mentioned.
Two rows are dagger-marked and excluded from comparative claims where we
couldn't separate integration issues from genuine failure — that's the honesty
standard we borrowed from the field.

## Slide 11 — Concurrent Work: StateMem (60s)

On August twentieth a concurrent paper appeared — StateMem — same lane, worth
addressing head-on. Three differences. Framing: they treat validity as a
property of the memory — avoid answering with superseded states; we formalize
it as a function of the memory-query pair — half of our benchmark requires
superseded states as evidence, a question class their benchmark barely
contains. Mechanism: theirs works at answer time; ours builds write-time
structure and lets code execute. Measurement: their transferable component —
the reading protocol — we cite verbatim and evaluate fully: it is the strongest
non-QVF configuration on our arena, eighty-four point five; the same protocol
over our ledger reaches statistically the same accuracy at one fifth the read
cost, and is shuffle-robust — the value sits in storage structure, not reading
instructions. Their benchmark is described as released but no public repository
exists yet, so full cross-evaluation is pending; we measured everything
measurable today, and a data request is drafted.

## Slide 12 — Shuffle Ladder (45s)

Our cleanest single experiment. Same content, same dates — we only shuffle the
order of entries. Reading the full transcript directly: minus forty-eight
points. Information unchanged, performance halved — the model's sense of time
was parasitic on context order. The reading protocol over the transcript: minus
six, still significant. Over our ledger: minus two point six, statistically
zero. The code path: immune, because sorted-by-date doesn't care about input
order. Each level of structure removes a level of order dependence — temporal
awareness moved from context order into date fields.

## Slide 13 — Cost (45s)

Cost in the most intuitive unit: what a hundred correct-ish answers buy.
Baseline retrieval: forty-nine correct for thirteen cents — cheap, and wrong
half the time. Our code path: seventy-nine correct for twenty-seven cents. Our
headline config: eighty-three for fifty cents. The only same-accuracy
alternative costs five and a half times more. The write side is a one-time
six-dollar investment that amortizes with reuse. And the honest note we say
before anyone asks: with prompt caching, full-context stuffing is two point
eight times cheaper in total dollars — but it is capped at fifty percent
accuracy at any budget. We checked at fifteen times the budget: no gain.
Accuracy is not purchasable.

## Slide 14 — WikiState v2 (40s)

The arena itself. Chains come from Wikidata property histories of real people,
rendered into dated first-person chat sessions with verbatim anchor sentences;
questions and gold answers are generated by code — zero manual labels. The
important part: we audited our own v1 and found three exploitable defects —
answer skew, an open-segment shortcut, and a wording ambiguity — and fixed all
three in v2. The audit-and-repair story goes into the paper; it's more credible
than claiming a perfect benchmark.

## Slide 15 — Human Verification Platform (45s)

And the last mile of dataset credibility is now live: rate dot wikistate dot
org. Every one of the 144 chains gets verified by three independent raters, who
see the chain table and the full raw session log with anchors highlighted — so
they can check both that anchors aren't out of context and that nothing was
missed. Five planted-error catch trials measure attention rather than assuming
it. About sixty items, two hours per rater, eight raters, recruiting now. The
output is Fleiss' kappa, agreement rates, and an adjudicated dataset v2.1.

## Slide 16 — Boundaries & Next (40s)

The honest half, stated before anyone asks. v1 and v2 absolute numbers are not
comparable. Natural-corpus chain extraction is not solved — our own audit on
LoCoMo produced a thirty-five percent revision rate, and that number, with its
failure taxonomy, goes into limitations as a first-hand quantification. And
parametric temporal drift — the ChronoScope disease — self-heals as models
improve; store-side state selection does not. That second disease is our
territory. Next steps: collect the human verification data, two scoped external
arenas as candidates, and paper drafting toward ACL or NAACL 2027 — the system
itself is frozen, the evidence is complete. Thank you — happy to take questions.

---

## Q&A quick cards

- **Why two answer paths?** One system, two consumption modes of the same
  memory structure: ledger reading scores highest; code computation is
  auditable and arithmetic-stable. After this week's repair they differ by 3.8
  points, p = 0.051 — the gap was chain-noise tolerance. Production advice:
  route by question type.
- **Isn't the reading protocol borrowed?** Yes, cited verbatim. The controlled
  comparison shows the value is in our ledger, not the prompt: same protocol
  on raw transcript = same accuracy at 5.5× the cost.
- **Can we trust synthetic data?** Real Wikidata histories; verbatim anchors;
  144/144 chains under 3-rater human verification with catch trials; and we
  published our own arena's defects and fixes.
- **Why did certification value shrink on v2?** Conventions moved into the
  question text, absorbing part of what certification used to carry — component
  value depends on where information is externalized; that's a datapoint, not
  an embarrassment.
- **LME numbers?** Temporal-reasoning subset +12.8 (p=0.01) with built-in
  placebo; knowledge-update ties the strongest baseline; cite with the
  Aug-17 configuration note.
