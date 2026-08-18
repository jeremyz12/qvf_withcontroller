# armdom

**Arm dominance audit + zero-LLM routing for multi-strategy memory / RAG systems.**

If your system picks between several retrieval or memory strategies ("arms") per query,
`armdom` reads your per-question logs and answers three questions — with no model calls
and no API cost:

1. **Is any arm strictly dominated?** (lower accuracy *and* higher token cost, on the same
   questions) — those arms are pure waste and should be deleted, not routed around.
2. **Does your online router earn its keep?** It fits zero-LLM routers on question text and
   store metadata, and reports the accuracy/token delta against whatever your system does today.
3. **Where is the ceiling?** The per-question oracle over your existing arms, so you know how
   much routing headroom actually exists before you invest in a better router.

`armdom` does not replace your system. It ingests logs and emits a config.

## Install

```bash
pip install -e .
```

No dependencies beyond the Python standard library (3.9+).

## Input format

One JSON object per line. One line per (question, arm) outcome:

```json
{"qid": "q001", "uid": "store-42", "arm": "dense_rag", "correct": true, "tokens": 1830, "question": "What phone am I using these days?"}
{"qid": "q001", "uid": "store-42", "arm": "graph_memory", "correct": false, "tokens": 9120, "question": "What phone am I using these days?"}
```

| field | required | meaning |
|---|---|---|
| `qid` | yes | question id; groups the arms that answered the same question |
| `arm` | yes | strategy name |
| `correct` | yes | boolean outcome under your judge |
| `tokens` | yes | total billed tokens for that arm on that question |
| `uid` | no | **store** id. Enables per-store adaptive routing (see below) |
| `question` | no | question text. Enables lexical routing |
| `group` | no | corpus/benchmark label. Used only for robustness reporting, never as a feature |

An optional `baseline` line per question records what your current system actually did:

```json
{"qid": "q001", "baseline": true, "arm": "graph_memory", "correct": false, "tokens": 9120}
```

## Use

```bash
armdom audit logs.jsonl
armdom audit logs.jsonl --emit report.json
armdom audit logs.jsonl --metric score      # single number, for CI / autoresearch loops
```

## What it reports

**Dominance matrix.** Every ordered arm pair on the questions where both ran. An arm is
reported as dominated only if it loses on accuracy *and* costs more. Per-group breakdown is
printed alongside: an arm that is dominated in aggregate but not within groups is reported as
**unstable, not dominated** — aggregate-only dominance is usually a mix effect.

**Strategy table, same denominator.** Every strategy is scored on *all* rows. When a strategy
picks an arm that did not run on some question, it falls back down `FALLBACK_ORDER` and the
fallback counts against it. This matters: scoring each arm on its own available subset inflates
low-coverage arms — in the reference dataset a constant arm read 72.56% on its own subset and
67.88% once fallbacks were counted.

**Routers.** All zero-LLM, all evaluated with store-level held-out splits (the same `uid` never
crosses folds) over multiple seeds:

- `lexical` — bucket by question prefix / wh-word / skeleton, with a backoff chain
- `shrinkage` — hierarchical empirical-Bayes pooling across bucket levels
- `combined` — backoff chain plus **per-store online adaptation**

**Ceiling.** Per-question oracle over your arms, cost-minimising among arms that were correct.

## Per-store adaptation

Memory systems serve a *persistent store* that gets asked many questions over time. `armdom`'s
`combined` router accumulates, per store, which arm has been working on *that* store, and shrinks
it toward the global prior by support. Two deployment-honesty constraints are enforced in the
implementation, not just documented:

- **Prequential** — a question is routed using only that store's *earlier* questions.
- **Bandit** — only the *chosen* arm's outcome updates the store state. Arms you did not run are
  not observable in deployment, so they are not observable here either.

In the reference dataset this adds +0.39 score over text-only routing (paired over 20 seeds,
t = 6.74, 19/20 seeds). **The pure store signal, used alone, is negative** — it is a complement
to question-level routing, not a substitute. Report it that way.

## Scoring

`score = accuracy_pp − w × tokens_per_question / 1000`, with `w = 0.5` by default (`--token-weight`).
`w` is a policy choice about what a token is worth to you; it is not estimated from data. State it
whenever you report a score.

## Reference result

On a four-arm long-term-memory system (4,633 questions, 1,037 stores, 15 corpora):

| | factory router | armdom config | delta |
|---|---|---|---|
| tokens/question | 3,439 | 1,841–1,875 | **−45.5% to −46.5%** |
| online LLM routing calls | 1 per question | **0** | — |
| accuracy | 72.24% | 70.29%–72.82% | **−1.95 pp to +0.58 pp** |

**The token saving is robust; the accuracy change is not established.** The accuracy range is
not noise — it is the gap between two policies for the 5.2% of questions where the router picks
an arm that has no archived result (see the arm-unavailability section above). Until those
questions are actually run, the accuracy effect is unmeasured, and the honest claim is
"same accuracy or slightly worse, at 46% of the tokens."

**Most of the token saving came from deleting one arm, not from smarter routing.** The deleted
arm cost 7.8–16.4× the tokens of its alternatives for +0.17 pp. Per-corpus, the config beats the
factory router on 9 of 15 corpora — the gains concentrate where the factory router was sending
questions to the expensive arm, and three corpora lose 4.3–4.6 pp. Report both numbers.

## ⚠ 未跑过的臂:一个必须由你决定的口径

日志里某道题没有某条臂的结果时,有两种含义,armdom 分不出来:

1. **该臂在这道题上不适用**——回落到别的臂是正确行为
2. **实验没跑它**——它的真实表现是**未知**,不是"回落臂的表现"

armdom 默认按 (1) 处理(`FALLBACK_ORDER` 回落),并在结果里报
`arm_unavailable_rate`。**这个数不为零时,分数是有条件的**:参考数据集上
路由 5.2% 的题落在这里,把准确率结论从 **+0.58pp** 拉到 **−1.95pp**
(悲观口径:未跑过的臂一律记为答错),而 token 节省在两种口径下都稳定在 −45~46%。

**报分时必须同页给出 `arm_unavailable_rate` 和两种口径下的区间**,否则你会
把一个未测量的洞报成一个确定的收益。这个洞是本工具在真实接线时才暴露出来的
(离线评估自己看不见它)。

## What armdom will not tell you

- Whether a *better* arm exists. It only compares arms you already ran.
- Whether the oracle gap is reachable. In the reference dataset the per-question oracle sits
  6.8 score points above the best deployable router, and question text does not close it —
  fine-grained buckets reach 77.59 in-sample but 71.65 held out, which is overfitting, not signal.
- Anything about a single-arm system.

## Prior art

Lightweight query routing over RAG strategies is established: lexical features beating semantic
embeddings for routing (arXiv 2604.03455), cost-aware bundle selection (arXiv 2606.02581), and
transferable surface-feature routers (arXiv 2604.09019). `armdom` does not claim novelty for
zero-LLM routing. What those papers do not do — and what this tool adds — is (a) test whether one
of your strategies is *dominated* rather than merely expensive, and (b) route with **per-store
state** rather than statelessly per query.

## License

MIT.
