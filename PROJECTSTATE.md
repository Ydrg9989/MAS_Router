# Project state

What exists and runs today. `TODO.md` records what does not. Updated 2026-08-10.

**The MVP is complete and the gate has been run.** Three agent pools, 366 hard tasks, 4,392 banked
answers and 57,489 episodes across the three pools, **$85.13** for the project as a whole. The outcome:
**delegation is the direction**, governance is a NO GO on accuracy, coalition is a NO GO. The reasoning
is in `EXPERIMENT_LOG.md` and `DECISIONS.md` D-021 through D-028; the short version is that governance
protocols do produce effects but the effects change sign when the pool changes, and a pre-registered
test of the one mechanism that looked real refuted it.

**A full account of settings, results and conclusions is in
[`Docs/EXPERIMENT_REPORT.md`](Docs/EXPERIMENT_REPORT.md)**, whose figures are regenerated from the run
records by `scripts/collect_report_data.py`. Read that before the log, which is chronological and
therefore contains superseded numbers.

**Delegation has since been closed as well, and the report above predates that.** The direction was
pursued on the `delegation` branch through a cross-capability suite (`crosscap240`, D-032) and then
through the learned router the direction had always proposed but never built (D-033). The router
exists, is leak-free, and gains nothing at calibration sizes from 57 to 398 tasks. **D-034 explains
why: there is nothing to win.** The "oracle headroom" this project has quoted since D-021 is what a
per-task maximum over a wide, semi-independent family produces by itself; against a null that
preserves organization accuracies and task difficulties while removing the organization-by-task
interaction, observed headroom is at or below chance in all six pool-by-suite cells. See D-029
through D-034 and the last four `EXPERIMENT_LOG.md` entries.

**Any headroom figure elsewhere in this file predates that null and should not be read as an
opportunity**, including the per-pool table below, which was the gate for buying priced episodes.

## Status at a glance

| Layer | State | Where |
|---|---|---|
| Environment, upstream pins, preflight | works | `pyproject.toml`, `UPSTREAM.md`, `mas_harness/doctor.py` |
| Cost accounting, cache, spend caps | works | `mas_harness/clients/` |
| Task manifests, splits, evaluators | works, 3 of 4 MVP suites | `mas_harness/tasks/` |
| Distributed-information condition | works, two arms | `mas_harness/tasks/distributed.py` |
| Agent pools, predicted expert, role rotation | works | `mas_harness/pool/` |
| Stage A answer bank | works, never run for real | `mas_harness/runners/answer_bank.py` |
| Protocols 1–7 | works | `mas_harness/protocols/` |
| Causal interventions | works | `mas_harness/interventions/edits.py` |
| Stage B episodes, records, Parquet | works | `mas_harness/runners/episodes.py`, `records/` |
| Governance / delegation / coalition metrics | works | `mas_harness/metrics/` |
| Statistics and power | works, one caveat | `mas_harness/metrics/stats.py` |
| Go/no-go gate | works | `mas_harness/analysis/gonogo.py` |
| Free pilot on SWE-bench Verified | run, results below | `mas_harness/analysis/free_pilot.py` |
| Task discrimination screen | works, run on 3 pools | `mas_harness/analysis/discrimination.py` |
| Pool headroom precondition | works, run on 3 pools | `mas_harness/analysis/headroom.py` |
| Candidate pool selector | works, 12 models screened | `mas_harness/analysis/pool_select.py` |
| Winner reproducibility (split-half + null) | works, run on 15 domains | `mas_harness/metrics/stability.py` |
| Learned router `q(x, S, p)` + baseline ladder | works, run on 6 cells, no gain | `mas_harness/metrics/routing.py` |
| Coding domain (EvalPlus) | not available, no sandbox | see `TODO.md` |
| GPUs / local vLLM | host has no GPU at all | see `TODO.md` |

391 tests pass and `ruff check` is clean over `mas_harness`, `scripts` and `tests`.

Five manifests are built and content-hashed: `hard366` (the main suite, 366 tasks selected for
difficulty — GPQA-Diamond 122, MATH-500 level 5 122, hard MMLU-Pro sources 122), `screen120` (a
sampled subset of it for candidate screening, so its calls are cache hits on the full run), `mvp90`,
and the two distributed arms (`distributed30`, `distributed30_pressure`).

The earlier `mvp90`-style suites were saturated — protocols cannot differ on tasks every agent gets
right — which is why `hard366` exists and why discrimination is now screened before Stage B is priced
(D-020).

## The three pools and what they showed

All three use `anthropic/claude-sonnet-5` as aggregator so the pool contrast is not confounded with
judge identity (D-024). Headroom is `P(at least one member correct) − best member`, the total accuracy
any governance rule can win, and it is checked before a pool receives priced episodes (D-021, D-023).

| pool | members | error corr | headroom | `single_expert` |
|---|---|---:|---:|---:|
| `strong4` | `grok43`, `gpt5mini`, `deepseek32`, `llama4scout` | +0.408 | 8.20pp | 0.8989 |
| `decorrelated4` | `gptoss120b`, `llama4scout`, `mistral-small`, `ring26` | +0.382 | 9.29pp | 0.8552 |
| `correlated4` | `gpt5mini`, `deepseek32`, `gptoss120b`, `qwen3-30b` | +0.579 | 4.92pp | 0.8989 |

Protocol accuracy minus `single_expert`, on each pool's discriminating tasks:

| protocol | `decorr` | `strong` | `corr` | |
|---|---:|---:|---:|---|
| `independent_judge` | +4.76 | +0.56 | +0.00 | never negative |
| `chair_information_seeking` | +4.76 | +3.37 | −3.10 | sign varies |
| `debate_vote` | +5.24 | +0.00 | −3.88 | sign varies |
| `expert_veto` | −1.90 | +3.37 | −6.20 | sign varies |
| `expert_verifier` | −1.43 | +0.00 | −0.78 | never positive |
| `independent_majority` | −0.95 | +0.00 | −4.65 | never positive |

Nothing survives Holm correction across the ten tests on the first two pools. `independent_judge` never
hurting and `expert_verifier` never helping are candidates for a future pre-registration, **not**
findings: with fifteen effects, a sign-stable one is unremarkable under the null.

The stable governance result is about influence rather than accuracy. Masking one member changes the
decision 24.5-25.0% of the time on every pool, and the mask-flip profile separates competence from
leverage cleanly — in `hard366-a`, `mistral-small` changed four decisions to correct and zero to wrong,
while `gpt5mini` at 0.883 competence carried 2.13x its share of influence.

## What has actually been executed

- **The full MVP against OpenRouter.** Stage A on three pools over `hard366`, the free half of Stage B
  on each (all 15 coalitions, masks, correct-answer substitutions, reorderings), the priced half on
  each pool's discriminating subset, and the gate on all three. 12 candidate models screened. See
  `EXPERIMENT_LOG.md` for per-run commands, costs and conclusions.
- **A pre-registered prediction, tested and refuted** (D-026, D-027). A pool-by-protocol interaction
  found post-hoc on two pools measured +10.53pp with a 95% CI of [+3.16, +17.89] and p=0.0052, and did
  not replicate on the third: the moderator would have had to act only in the middle of its own range.
  It cost $17.93 to refute. This is the single most useful thing the harness has done.
- **The free pilot**, on the verified 134-agent x 500-task SWE-bench matrix from
  `agent-psychometrics`. This validated the whole coalition-analysis path — pairwise
  synergy, Harsanyi dividends, `R_{>=3}`, submodularity violations, error correlation,
  top-k gap, pairwise factorization — at zero cost. See `EXPERIMENT_LOG.md`.
- **The full harness end to end on a synthetic answer bank** (`tests/test_pipeline.py`):
  manifest, Stage A bank, predicted-expert fit on the calibration split only, Stage B over
  every one of the 15 coalitions and two free protocols, masking interventions, JSONL and
  Parquet records, resume, and the go/no-go gate. The bank is planted so dilution, rescue
  and a contested 2-2 vote are known in advance, and the tests assert the metrics recover
  them.

- **The distributed-information condition, mechanically.** With the option set partitioned
  and a unique holder, the real `independent_majority` protocol can never carry the correct
  answer on a plurality — only one member is able to cast it. Verified over the derived
  tasks: the correct answer wins only when a full four-way split hands it to the tie-break,
  never on the merits. Deferring to the holder recovers every task, which is the ceiling
  protocols 6 and 7 are aiming at without being told who the holder is.

Costs to date, all OpenRouter, no GPU used anywhere: **$85.13 total** — $16.73 building the suite and
screening pools, $57.98 for the three priced pool sweeps, and $10.43 on the failed attempt to repair
aggregator non-termination (D-028). Caps are per-run ($75) and per-day ($150), not cumulative, so
nothing is currently constrained.

## The seven protocols

Baselines 1–5 describe how existing systems allocate influence. Protocols 6–7 are the
report's proposed interventions, each paired with the baseline it differs from by exactly
one rule (D-012).

| Protocol | Calls (4 agents) | Decision rule |
|---|---:|---|
| `single_expert` | 0 | the predicted expert's banked answer |
| `independent_majority` | 0 | plurality over banked answers, abstentions excluded |
| `independent_judge` | 1 | a neutral aggregator picks |
| `expert_verifier` | 2 | one review, then the **expert** has the last word |
| `debate_vote` | 4 per extra round | revise simultaneously, then vote |
| `expert_veto` | 1 | the expert stands unless a challenge clears an evidence bar |
| `chair_information_seeking` | 2–4 | a chair may ask one question, then decides |

Two of the seven cost nothing once Stage A exists, which is what makes exhaustive coalition
enumeration affordable (D-001, D-009).

## Load-bearing invariants

These are asserted by tests, not merely intended. If one breaks, a scientific claim breaks
with it.

- The two free protocols make **zero** model calls. The entire cost argument rests on it.
- Every protocol on a given task sees byte-identical banked answers, so protocol
  comparisons are exactly paired and McNemar applies.
- The predicted expert is fitted on the calibration split only; the oracle is computed but
  never pooled with it (D-004).
- An answerless message is an abstention, not a vote. Upstream extraction returns a
  confident letter for ordinary prose, so extraction was re-implemented (D-011).
- Interventions never mutate the input bank; the same bank object is reused across every
  protocol and intervention for a task.
- Every branch point in the governance protocols is resolved by extraction or string
  matching, never by a second model (D-003, D-013).
- Role rotations carry distinct pool ids, so they cannot collide in the resume set (D-014).
- In the distributed condition, the correct option is visible to exactly the recorded
  holders, the union of visible option sets is complete, and every member sees the same
  number of options so set size cannot betray the holder (D-010). Checked per task at build
  time, not just in tests.
- A member's private evidence follows it into every call it makes — debate revisions, chair
  replies, verifier reviews — while the judge and chair hold none. An agent that lost its
  briefing mid-protocol would be defending a position whose basis it could no longer see.
- Manifest content hashes cover the private briefings, so a changed partition is a changed
  manifest (D-016).

## Known limitations worth stating up front

- Three of four MVP domains are available: MATH-500, GPQA-Diamond, MMLU-Pro STEM. There is
  no code-execution path, so the coding domain is absent.
- The distributed condition is *constructed*, not HiddenBench, and is labelled
  `distributed_synth` everywhere (D-010). Absolute accuracy on it is not comparable to the
  full-information suites, because partitioning ten options across four members moves a
  member's prior from 1/10 to about 1/3. Compare protocols within the condition.
- Its one residual leak is that a member can name a letter it was never shown.
  `out_of_set_rate()` measures this; it has not yet been measured on real model output.
- `mixed_effects_logit` clusters on task via GEE rather than fitting crossed task+seed
  random effects. Adequate for the pilot, not for the paper.
- The semantic task space falls back to character n-gram TF-IDF when `sentence-transformers` cannot
  reach the network, and the fallback is reported in every comparison because a low
  semantic-versus-organizational correlation means much less if the semantic space is weak. Both paths
  have now been measured and agree (Spearman 0.028-0.105 with real embeddings, 0.048-0.063 with the
  fallback), so the criterion is not an artifact of the fallback — but any given run's report must be
  read for which method it used.
- **The delegation criterion passing is thinner than it looks.** Configuration dominance reads 41.7%,
  58.3% and 75.0% across the three pools against a 75% ceiling, so on `decorrelated4` it passes by a
  margin of exactly zero. With only seven protocols there are few configurations to dominate, and the
  number will move as protocol families are added.
- Harsanyi decomposition is exact and therefore exponential in pool size. Fine at four or
  five agents; it refuses above twelve.
- Planning token figures are now measured (300 input / 4,200 output per call) but remain deliberately
  conservative: measured priced runs came in 1.9-3.0x under their dry-run estimates, because the
  estimator budgets 4,200 output tokens per carried peer answer where reliable models average 1,580.
  Treat `--dry-run` as an upper bound, not a forecast.
- Absolute accuracy is not comparable across pools, only protocol contrasts within one (D-021). Nor is
  any accuracy measured on a discriminating subset comparable to a full-suite figure: the subset is
  selected *because* protocols differ there, so `independent_majority` reads 0.667 on a 15-task slice
  against 0.8497 on all 366.

## Next actions

The gate chose delegation, so the next phase is the delegation direction: representing tasks by which
agent organizations succeed on them rather than by semantics.

1. Write the learned models `TODO.md` lists as missing — task encoder, set-valued organization model,
   selector — and train them on the banked outcomes. The data is already on disk: 4,392 answers and
   57,489 episodes across three pools, all replayable at zero cost.
2. Widen the protocol family before leaning on configuration dominance. Seven protocols give too few
   configurations for the 75% ceiling to mean much, and one pool already sits exactly on it.
3. Pre-register the two sign-stable patterns before testing them: `independent_judge` never hurting,
   `expert_verifier` and plain majority never helping. D-027 explains why they are not yet findings.
4. Report the governance material as an influence result, which is what replicated: mask-flip rates of
   24.5-25.0% and the competence-versus-leverage divergence, both stable across all three pools.
5. Stage A and B over both distributed arms remain unrun, and `out_of_set_rate()` has still never been
   measured on real model output.
