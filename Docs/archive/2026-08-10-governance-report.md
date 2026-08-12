<!-- doc-meta
type:          frozen
lifecycle:     ARCHIVED — never updated
last-verified: 2026-08-11
evidence-base: governance phase artefacts; SS10.6 verdict retired by D-029/D-030
-->

# Experimental report: epistemic governance in heterogeneous LLM teams

Complete account of the settings, results and conclusions of the MVP phase.
Generated 2026-08-10. Every number here is reproducible from
[`scripts/collect_report_data.py`](../../scripts/collect_report_data.py), whose output is committed at
`data/report_data.txt`; run identifiers refer to directories under `data/runs/`.

Companion documents: [`EXPERIMENT_LOG.md`](../../EXPERIMENT_LOG.md) is the chronological narrative,
[`DECISIONS.md`](../../DECISIONS.md) holds the 28 numbered design decisions, and
[`PROJECTSTATE.md`](../../PROJECTSTATE.md) records what currently works.

---

## 1. Summary

**Question.** Given a heterogeneous pool of LLMs and a hard question, which agents should answer, and
how should their answers be combined into a decision?

**Scale.** 366 hard tasks, 16 model configurations measured, 3 pools of 4 agents, 7 combination
protocols, 3 interventions plus an observational baseline. 14,890 banked answers and 76,179 episodes
for **$85.13**, all via OpenRouter, no GPU.

**Headline results.**

1. **No protocol reliably beats deferring to a predicted expert.** Across three pools and 18
   protocol-versus-baseline tests, nothing survives Holm correction; the smallest adjusted p is 0.694.
   This is qualified by (5) and by §12.1.
2. **Deliberation is not free of harm.** `debate_vote` cost 3.88pp in one pool, and plain majority
   voting was never positive in any pool.
3. **Pool composition dominates protocol choice.** The same rule swings from +3.37pp to −6.20pp
   depending only on which four models are in the pool.
4. **A pre-registered confirmation failed.** The one mechanism that appeared to explain (3) —
   error decorrelation moderating the expert veto — measured +10.53pp with p=0.0052 on two pools and
   was refuted on a third, for $17.93.
5. **The most promising protocol is unresolved, not negative.** `independent_judge` is non-negative in
   all three pools and reaches +6.97pp (p=0.0066) in one under a favourable but biased accounting of a
   harness defect. We cannot presently say whether it wins.

**Gate outcome, identical on all three pools:** governance PARTIAL, delegation **GO**, coalition NO GO.

---

## 2. Research question and directions

The project evaluates three candidate research directions against a shared experimental substrate of
`task x agent pool x protocol x seed -> outcome, transcript, cost, latency, metadata`.

| direction | claim under test | gate criteria |
|---|---|---|
| **Epistemic governance** | Influence over the team decision is separable from competence, and the rule allocating influence changes accuracy | protocol spread >= 8pp; correct-answer dilution >= 15%; intervention flip rate >= 10% |
| **Delegation-equivalent representations** | Tasks are better represented by which organizations succeed on them than by semantics | configuration dominance <= 75%; semantic-vs-organizational Spearman < 0.5 with >= 20% differing nearest neighbours |
| **Coalition landscapes** | Team value is non-additive; the strongest individuals are not the best team | top-k gap >= 15% of tasks |

The gate is pre-registered in the sense that thresholds were fixed before the priced runs. Its purpose
is to select one direction on evidence rather than preference.

---

## 3. Experimental design

### 3.1 The two-stage architecture

The central design decision (D-001) separates answer *generation* from answer *combination*.

**Stage A — the answer bank.** Each agent answers each task independently, with no knowledge of the
others. One call per `(task, agent, seed)`. Written to `answers.jsonl` with the full response text,
the extracted answer, correctness, and a complete call record.

**Stage B — episodes.** A protocol is a function from the banked answers to a final answer. Protocols
that only *select among* banked answers make zero new model calls and are replayed from disk for
$0.00. Protocols where agents react to one another make new calls.

Two of seven protocols are free. This is what makes the design affordable and is why exhaustive
coalition enumeration is possible at all: `hard366-a` produced **18,300 episodes in about 9 seconds
for $0.00**, covering all 15 non-empty coalitions of 4 agents plus every intervention.

The second benefit is statistical rather than economic. Every protocol sees byte-identical banked
answers for a given task, so protocol comparisons are exactly paired and McNemar's test applies.
Independent generation per protocol would have required substantially more tasks for the same power.

### 3.2 Cost model and controls

- **Prices** are snapshotted per run (`pricing_snapshot.json`) and are required even for `--dry-run`;
  an unpriced plan cannot be checked against a budget and the runner refuses to guess.
- **Budget caps** are per-run (`MAS_RUN_BUDGET_USD=75`) and per-day (`MAS_DAILY_BUDGET_USD=150`), not
  cumulative over the project.
- **The ledger charges what the provider reports**, not what we compute (D-017). OpenRouter routes to
  upstream providers with their own rates; measured discrepancies reached 2.69x. The computed figure is
  retained because the *disagreement* is the diagnostic.
- **Caching** is content-addressed on `(model, messages, temperature, max_tokens, seed, extra_body)`.
  Re-running an identical configuration costs nothing, which is why banking `decorrelated4` after a
  member swap cost $0.26 rather than a full re-run.
- **Dry-run estimates are upper bounds, not forecasts.** Measured runs came in 1.9x to 3.0x under
  estimate, because the estimator budgets 4,200 output tokens per carried peer answer where reliable
  models average about 1,580.

### 3.3 Reproducibility

Manifests are content-hashed (`hard366` = `58f3177439...`), covering task ids, order and any private
briefings. Pools are hashed by content, so changing `max_tokens` on any member yields a different pool.
Every record carries `schema_version`, `run_id`, the pool id and the manifest hash. Records are written
as JSONL and mirrored to Parquet.

---

## 4. Task suite

### 4.1 Composition

`configs/suites/hard366.yaml`, seed 20260805, 366 tasks in three equal blocks of 122 across 12 domains:

| block | source | selection |
|---|---|---|
| `gpqa_diamond` | GPQA-Diamond | 122 of 198; graduate-level by construction |
| `math500` | MATH-500 | **level 5 only** — the hardest of five bands, 122 of 134 available |
| `mmlu_pro` | MMLU-Pro STEM | **theoremQA and scibench sources only**, 122 of 1,065 |

34% of tasks (123) are reserved as a calibration split used solely to fit the predicted expert; the
oracle expert is computed but never pooled with it (D-004).

### 4.2 Why difficulty was selected for

The predecessor suite was balanced across domains but not difficulty, and the pool scored 12/12 on both
MATH-500 and MMLU-Pro. This is not a power problem that more sampling fixes — it is structural. When
four agents give the same answer, every protocol returns that answer *by construction*, contributing a
concordant pair to every comparison and nothing to a McNemar test. **The maximum possible spread
between the best and worst protocol is bounded above by the fraction of tasks on which agents
disagree**, which was 11.1% against a gate threshold of 8pp (D-020).

### 4.3 Discrimination screening

Before any priced episode, the Stage-A bank is classified per task
([`mas_harness/analysis/discrimination.py`](../../mas_harness/analysis/discrimination.py)):

| class | meaning |
|---|---|
| `UNANIMOUS_CORRECT` / `UNANIMOUS_WRONG` | no protocol can differ from any other |
| `MAJORITY_CORRECT` | a vote succeeds; governance can only lose |
| `MINORITY_CORRECT` | **dilution possible** — a correct answer can be outvoted |
| `TIE` | **dilution possible** — the tie-break decides |

Screening is free because Stage A *is* the screen. Stage B is then targeted at discriminating tasks
plus a sampled control of non-discriminating ones — the control is not a spare, it tests the assumption
that unanimous tasks cannot change under a protocol, and dropping it would make that assumption
unfalsifiable.

---

## 5. Agent pools

### 5.1 Candidate screening

Sixteen model configurations were measured in total: four arrived with the original pool, and twelve
were screened as candidates in dedicated runs (`screen-a`, `screen-strong`). `gemini25flash` and
`gemini25flash-hi` are the same model at two reasoning budgets and are counted separately because they
behave differently. Three criteria, applied in order:

**Commit rate first (D-022).** A model must produce a readable answer on >= 95% of calls *before* it is
scored on anything else. This is a precondition on the instrument, not a quality ranking. An unfinished
or unparseable response is an abstention and scores as wrong, and to the headroom calculation an
abstention is indistinguishable from a decorrelated error — it is wrong, and wrong on different items
than a working model's mistakes. So an unreliable agent *inflates* the exact quantity used to select
pools. Run without this criterion, the selector's top recommendation had 30.51pp of apparent headroom,
of which most was missing data.

| agent | n | accuracy | commit | unfinished | out tok | $/call | admitted |
|---|---:|---:|---:|---:|---:|---:|---|
| `llama4scout` | 484 | 0.643 | 1.000 | 0.000 | 791 | $0.00033 | yes |
| `deepseek32` | 486 | 0.860 | 1.000 | 0.000 | 1,267 | $0.00059 | yes |
| `grok43` | 120 | 0.875 | 1.000 | 0.000 | 1,329 | $0.00368 | yes |
| `gpt5mini` | 366 | 0.883 | 1.000 | 0.000 | 2,227 | $0.00452 | yes |
| `novalite` | 486 | 0.498 | 0.996 | 0.004 | 699 | $0.00018 | yes |
| `mistral-small` | 366 | 0.604 | 0.992 | 0.008 | 1,140 | $0.00030 | yes |
| `gptoss120b` | 486 | 0.821 | 0.990 | 0.006 | 1,413 | $0.00044 | yes |
| `qwen3-30b` | 366 | 0.795 | 0.984 | 0.016 | 3,352 | $0.00091 | yes |
| `ring26` | 120 | 0.825 | 0.967 | 0.017 | 1,820 | $0.00116 | yes |
| `kimi-k2-thinking` | 120 | 0.825 | 0.925 | 0.075 | 6,927 | $0.01748 | **no** |
| `nemotron3ultra` | 120 | 0.808 | 0.850 | 0.150 | 5,254 | $0.01568 | **no** |
| `glm52` | 120 | 0.775 | 0.808 | 0.183 | 4,751 | $0.01176 | **no** |
| `minimax-m27` | 120 | 0.675 | 0.792 | 0.208 | 6,921 | $0.00909 | **no** |
| `gemini25flash` | 366 | 0.623 | 0.757 | 0.077 | 2,951 | $0.00745 | **no** |
| `gemini25flash-hi` | 120 | 0.558 | 0.650 | 0.150 | 4,484 | $0.01128 | **no** |
| `glm45air` | 118 | 0.534 | 0.602 | 0.398 | 7,985 | $0.00748 | **no** |

The exclusions are dominated by extended-reasoning models that fail to terminate: all seven excluded
models average over 2,900 output tokens per call and the four worst average over 4,400. Verbosity alone
is not disqualifying — `qwen3-30b` averages 3,352 tokens and commits 98.4% of the time — but every
model that failed the floor is a verbose one, and the excluded models are also the expensive ones, at
$0.0074 to $0.0175 per call against $0.0002 to $0.0045 for those admitted. Reliability and cost happen
to point the same way here, so nothing was sacrificed to enforce the floor.

### 5.2 The headroom precondition

Every protocol decides *among answers already in the bank*, so `P(at least one member correct)` is a
hard ceiling and the best single member is the baseline every governance rule must beat.

> **headroom = P(at least one member correct) − accuracy(best member)**

This is the entire accuracy budget available to all governance rules combined. A pool whose headroom is
below the gate threshold cannot pass the gate *by arithmetic*, regardless of which protocols are bought
(D-021). The check runs on the free Stage-A bank and is a precondition on the pool.

This precondition retired a pool before it was priced: `hard366-a` had 4.37pp of headroom against an
8pp gate, so buying its episodes would have produced a NO GO that was arithmetic rather than evidence.

### 5.3 What actually drives headroom

The first diagnosis — that a dominant agent compresses headroom — was incomplete. The refutation is a
single row: the most competence-homogeneous pool available, 1.6pp from best to second, has only 4.92pp
of headroom. Its members are near-equal *and* wrong about the same things. Homogeneity was necessary
and not sufficient; **error decorrelation is the design variable** and dominance is one of two ways to
lose it (D-023).

Recomputed over all 126 four-member subsets of the 9 reliable agents banked on the full suite
([`scripts/recheck_headroom_correlations.py`](../../scripts/recheck_headroom_correlations.py)):

| relationship | at n=366 | as first measured at n=120 |
|---|---:|---:|
| headroom vs mean error correlation | **−0.336** | −0.643 |
| headroom vs mean pool accuracy | **−0.307** | −0.618 |
| mean accuracy vs mean error correlation | **+0.821** | +0.741 |

**The n=120 screen overstated the first two relationships by roughly a factor of two.** Only the third
survives at full strength, and it is the one that matters mechanically: strong models agree with each
other, and agreement is what destroys headroom.

The weakening of the headroom-versus-accuracy correlation to −0.307 matters for the design. D-023 had
read −0.618 as meaning decorrelation is purchasable only at low competence, which would have made every
governance result confounded with weakness. It is a real tendency — the eight highest-headroom subsets
all sit between 0.638 and 0.734 mean accuracy — but it is not a law, and `strong4` is the exception
that the experiment is built on: 8.20pp of headroom at 0.823.

### 5.4 The three pools

All three share `anthropic/claude-sonnet-5` as aggregator, fixed across pools so the pool contrast is
not confounded with judge identity (D-024). All members run at temperature 0.0 and `max_tokens` 16,384.

| | `strong4` (treatment) | `decorrelated4` (replication) | `correlated4` (control) |
|---|---|---|---|
| members | `grok43`, `gpt5mini`, `deepseek32`, `llama4scout` | `gptoss120b`, `mistral-small`, `llama4scout`, `ring26` | `gpt5mini`, `deepseek32`, `gptoss120b`, `qwen3-30b` |
| accuracies | .885, .883, .866, .658 | .825, .604, .658, .847 | .883, .866, .825, .795 |
| mean accuracy | 0.823 | 0.734 | 0.842 |
| dominance gap | **0.27pp** | 2.19pp | 1.64pp |
| competence range | 22.68pp | 24.32pp | 8.74pp |
| mean error correlation | **+0.408** | **+0.382** | **+0.579** |
| ceiling | 96.72% | 93.99% | 93.17% |
| best member | 88.52% | 84.70% | 88.25% |
| **headroom** | **8.20pp** admissible | **9.29pp** admissible | **4.92pp** fails by design |

`correlated4` is the control and is *designed* to fail the headroom precondition: its members are
near-equal in competence yet wrong about the same things. The tool's own diagnostic states this without
being told — "the members are near-equal (1.6pp from best to second) but err together at +0.579, so
competence homogeneity is not the constraint".

**The identifying property of the design** is that `strong4` and `correlated4` reach *identical*
`single_expert` accuracy on the full suite — 0.8989 both (§10.3) — and are matched on dominance to
within 1.4pp, while differing in error correlation by 0.171. A difference in governance outcome between
them cannot be attributed to competence.

### 5.5 Selection method

Pools are selected on the **full 366 tasks**, never on the 120-task screen (D-025). The screen decides
only which models are excluded as broken instruments and which are worth banking in full. This rule was
learned by violating it twice:

- `ring26` improved all four selection criteria at n=120 and *cost* 1.1pp of headroom at n=366. One
  task is 0.83pp at n=120 and 0.27pp at n=366, so pools separated by two tasks on the screen are not
  separated at all.
- `grok43` passed the screen with the best accuracy and reliability of the twelve, then was left at 120
  tasks while pools were ranked without it. Its absence caused an entire paragraph of D-023 to assert
  as an empirical finding that decorrelation at high competence does not exist. Banking it cost $0.86
  and produced `strong4`, which is now the primary treatment.

---

## 6. Protocols

Two baselines are free; five cost money. Protocols 6 and 7 (`expert_veto`,
`chair_information_seeking`) are the proposed interventions, each paired with the baseline it differs
from by exactly one rule so the pair isolates that rule (D-012).

| protocol | calls (4 agents) | decision rule | pairs with |
|---|---:|---|---|
| `single_expert` | **0** | the predicted expert's banked answer | — |
| `independent_majority` | **0** | plurality over banked answers, abstentions excluded | — |
| `independent_judge` | 1 | a neutral aggregator reads all answers and picks | — |
| `expert_verifier` | 2 | one member reviews the expert, then the **expert** decides | `expert_veto` |
| `debate_vote` | 4 per extra round | members see all answers, revise simultaneously, vote | — |
| `expert_veto` | 1 | the expert stands unless a challenger identifies a specific error **and** names a different answer | `expert_verifier` |
| `chair_information_seeking` | 2–4 | a chair may ask one targeted question of up to two members, then decides | `independent_judge` |

Full observability specifications are generated from the registry itself in
[`Docs/reference/PROTOCOL_CARD.md`](../reference/PROTOCOL_CARD.md), so they cannot drift from the code.

**Load-bearing invariants**, asserted by tests rather than intended:

- The two free protocols make exactly zero model calls.
- Every protocol on a task sees byte-identical banked answers.
- The predicted expert is fitted on the calibration split only.
- An answerless message is an abstention, not a vote. Upstream extraction returned a confident letter
  for ordinary prose, so extraction was reimplemented (D-011).
- A response that did not finish is an abstention regardless of whether a letter can be extracted
  (D-019).
- Every branch point in the governance protocols is resolved by extraction or string matching, never by
  a second model call (D-003, D-013).
- Interventions never mutate the input bank.

**Known limitation of anonymization:** it applies to message *labels*, not content. A model writing
"As GPT-5 I think..." de-anonymizes itself and the harness does not rewrite it.

---

## 7. Interventions

Applied to the grand coalition, all free because they are replays:

| intervention | manipulation | measures |
|---|---|---|
| `mask` | remove one member's message | that member's causal influence on the decision |
| `substitute_correct` | replace one member's answer with the correct one | recoverability — whether a correct answer would be adopted |
| `reorder` | permute speaking order | position effects |
| `none` | observational | baseline |

---

## 8. Metrics and statistics

- **Paired comparison** via McNemar on discordant pairs; protocols see identical banked answers so
  pairing is exact.
- **Multiplicity** via Holm step-down across the family of protocol comparisons. §10.3 corrects over
  all 18 protocol-versus-baseline tests jointly (6 protocols x 3 pools). The gate corrects within a
  pool over the 10 pairwise comparisons among 5 protocols, where uncorrected alpha 0.05 gives roughly a
  40% chance of at least one false positive.
- **Effect intervals** via paired bootstrap, 20,000 resamples.
- **Power** reported per run: at the observed discordance, the item count needed for 80% power to
  detect the gate's 8pp difference.
- **Cost reconciliation** between computed and provider-reported figures, per call.

---

## 9. Runs executed

| run | purpose | answers | episodes | paid calls | cost |
|---|---|---:|---:|---:|---:|
| `pilot9-a` | first live Stage A, 9 tasks | 32 | 0 | 32 | $0.04 |
| `pilot9-b` | rerun after raising `max_tokens` | 36 | 315 | 117 | $0.70 |
| `probe-gpqa` | measure real token distributions | 44 | 0 | 44 | $0.46 |
| `probe-fixed` | verify the Gemini reasoning clamp | 48 | 0 | 47 | $0.26 |
| `mvp366-a` | halted: truncation at 25% | 118 | 0 | 114 | $0.59 |
| `hard366-a` | first full pool on the hard suite | 1,464 | 18,300 | 1,416 | $4.56 |
| `screen-a` | screen 6 mid-tier candidates | 718 | 0 | 718 | $2.43 |
| `screen-strong` | screen 6 strong candidates | 720 | 0 | 720 | $7.06 |
| `cand4-a` | bank 4 reliable candidates in full | 1,462 | 0 | 982 | $0.36 |
| `decorrelated4-a` | superseded pool revision | 1,464 | 0 | 246 | $0.26 |
| `strong4-a` | **treatment pool, full** | 1,464 | 19,194 | 1,933 | $20.09 |
| `decorr4-a` | **replication pool, full** | 1,464 | 19,350 | 2,035 | $19.18 |
| `correlated4-a` | **control pool, full** | 1,464 | 18,945 | 1,233 | $18.71 |
| `strong4-a-retry` | failed repair of truncation | 1,464 | 24 | 280 | $4.19 |
| `decorr4-a-retry` | failed repair of truncation | 1,464 | 30 | 44 | $3.24 |
| `correlated4-a-retry` | failed repair of truncation | 1,464 | 21 | 29 | $2.99 |
| | | **14,890** | **76,179** | **9,990** | **$85.13** |

Of the $85.13, **$57.98** is the three priced pool sweeps, **$10.43** is the failed repair described in
§12, and **$16.73** is suite construction, candidate screening and diagnostics.

---

## 10. Results

### 10.1 Stage A

Per-pool member accuracy on all 366 tasks, with reliability:

| pool | agent | accuracy | commit | unfinished |
|---|---|---:|---:|---:|
| `strong4` | `grok43` | 0.8852 | 1.0000 | 0.0000 |
| | `gpt5mini` | 0.8825 | 1.0000 | 0.0000 |
| | `deepseek32` | 0.8661 | 1.0000 | 0.0000 |
| | `llama4scout` | 0.6585 | 1.0000 | 0.0000 |
| `decorrelated4` | `ring26` | 0.8470 | 0.9727 | 0.0219 |
| | `gptoss120b` | 0.8251 | 0.9891 | 0.0082 |
| | `llama4scout` | 0.6585 | 1.0000 | 0.0000 |
| | `mistral-small` | 0.6038 | 0.9918 | 0.0082 |
| `correlated4` | `gpt5mini` | 0.8825 | 1.0000 | 0.0000 |
| | `deepseek32` | 0.8661 | 1.0000 | 0.0000 |
| | `gptoss120b` | 0.8251 | 0.9891 | 0.0082 |
| | `qwen3-30b` | 0.7951 | 0.9836 | 0.0164 |

### 10.2 Discrimination

| pool | discriminating | dilution eligible | mean agent acc | Stage B scope |
|---|---:|---:|---:|---|
| `strong4` | 39.9% | 15.3% | 0.8231 | 146 + 33 control |
| `decorrelated4` | **49.5%** | **24.6%** | 0.7336 | 181 + 29 control |
| `correlated4` | 23.5% | 10.9% | 0.8422 | 86 + 43 control |

By suite, GPQA-Diamond discriminates most in every pool (28.7%, 49.2%, 61.5%) and MMLU-Pro least
(15.6%, 23.8%, 37.7%), with MATH-500 level 5 between them (26.2%, 46.7%, 49.2%). The suite rebuild
worked: 46.2% discriminating on `hard366-a` against 11.1% on the saturated predecessor, which raises
the arithmetic ceiling on protocol spread from 11.1pp to 46.2pp.

### 10.3 Protocol accuracy

**The free protocols on all 366 tasks.** These ran on the full suite and are the figures to quote for
absolute performance:

| pool | `single_expert` | `independent_majority` |
|---|---:|---:|
| `strong4` | **0.8989** | 0.8962 |
| `decorrelated4` | 0.8552 | 0.8497 |
| `correlated4` | **0.8989** | 0.8825 |

This is the identifying property of the design in one row: `strong4` and `correlated4` reach *identical*
`single_expert` accuracy while differing in error correlation by 0.171.

**The paid protocols on the discriminating subsets.** Everything below is computed only on the tasks a
pool's seven protocols all ran, because the paid protocols were restricted to the discriminating subset
while the free ones cover all 366. Mixing the two denominators is what makes the runner's own
per-protocol summary non-comparable across rows. Consequently these accuracies are **lower** than the
full-suite figures above by construction — the subset is selected precisely because it is hard — and
they are **not comparable across pools**, only within one.

**`strong4-a` (n=178).** Spread 3.37pp — FAIL.

| protocol | accuracy | vs expert | discordant | p |
|---|---:|---:|---:|---:|
| `expert_veto` | 0.8764 | +3.37pp | 8 | 0.0703 |
| `chair_information_seeking` | 0.8764 | +3.37pp | 26 | 0.3269 |
| `independent_judge` | 0.8483 | +0.56pp | 25 | 1.0000 |
| `expert_verifier` | 0.8427 | +0.00pp | 8 | 1.0000 |
| `debate_vote` | 0.8427 | +0.00pp | 22 | 1.0000 |
| `single_expert` | 0.8427 | — | — | — |
| `independent_majority` | 0.8427 | +0.00pp | 18 | 1.0000 |

**`decorr4-a` (n=210).** Spread 7.14pp — FAIL, but closest of the three.

| protocol | accuracy | vs expert | discordant | p |
|---|---:|---:|---:|---:|
| `debate_vote` | 0.8857 | +5.24pp | 27 | 0.0522 |
| `independent_judge` | 0.8810 | +4.76pp | 28 | 0.0872 |
| `chair_information_seeking` | 0.8810 | +4.76pp | 26 | 0.0755 |
| `single_expert` | 0.8333 | — | — | — |
| `independent_majority` | 0.8238 | −0.95pp | 18 | 0.8145 |
| `expert_verifier` | 0.8190 | −1.43pp | 15 | 0.6072 |
| `expert_veto` | 0.8143 | −1.90pp | 14 | 0.4240 |

**`correlated4-a` (n=129).** Spread 6.20pp — FAIL.

| protocol | accuracy | vs expert | discordant | p |
|---|---:|---:|---:|---:|
| `independent_judge` | 0.8760 | +0.00pp | 18 | 1.0000 |
| `single_expert` | 0.8760 | — | — | — |
| `expert_verifier` | 0.8682 | −0.78pp | 3 | 1.0000 |
| `chair_information_seeking` | 0.8450 | −3.10pp | 20 | 0.5034 |
| `debate_vote` | 0.8372 | −3.88pp | 19 | 0.3593 |
| `independent_majority` | 0.8295 | −4.65pp | 16 | 0.2101 |
| `expert_veto` | 0.8140 | −6.20pp | 12 | 0.0386 |

**Multiplicity.** Holm across all 18 tests: the smallest adjusted p is **0.694**
(`correlated4-a | expert_veto`), then 0.888 (`decorr4-a | debate_vote`). **Nothing is significant.**

### 10.4 Sign stability across pools

The same protocol, the same baseline, three pools ordered by error correlation:

| protocol | `decorr` +0.382 | `strong` +0.408 | `corr` +0.579 | pattern |
|---|---:|---:|---:|---|
| `independent_judge` | +4.76 | +0.56 | +0.00 | never negative |
| `chair_information_seeking` | +4.76 | +3.37 | −3.10 | sign varies |
| `debate_vote` | +5.24 | +0.00 | −3.88 | sign varies |
| `expert_veto` | −1.90 | +3.37 | −6.20 | sign varies |
| `expert_verifier` | −1.43 | +0.00 | −0.78 | never positive |
| `independent_majority` | −0.95 | +0.00 | −4.65 | never positive |

`independent_judge` never hurting, and `expert_verifier` and plain majority never helping, are the two
patterns worth a future pre-registration. **They are not findings.** With six protocols and three
pools there are eighteen effects, and a sign-stable one is unremarkable under the null. Naming them as
results now would repeat precisely the error described in §11.

### 10.5 Influence

Single-member masking, 1,464 pairs per protocol per pool:

| pool | `independent_majority` | `single_expert` |
|---|---:|---:|
| `strong4` | 5.5% | 25.0% |
| `decorrelated4` | **8.5%** | 24.5% |
| `correlated4` | 5.3% | 25.0% |

**An important caveat that qualifies the gate.** The gate's "intervention flip rate" criterion takes
the maximum over protocols, so its 24.5–25.0% PASS is carried entirely by `single_expert` — where
masking the predicted expert *necessarily* changes which agent's answer is used. That is close to
tautological and is not evidence of deliberative influence. The meaningful number is the vote's
**5.3–8.5%**, and no pool reaches the 10% threshold on it. **Read strictly, governance fails this
criterion too, and the gate's PASS is an artifact of the criterion's specification.** It should be
re-specified to exclude `single_expert` before it is relied on again.

What the per-member breakdown does show is a genuine divergence between competence and leverage. In
`decorrelated4`, masking `ring26` changes the vote 11.2% of the time and `gptoss120b` 16.4%, while
`mistral-small` changes it 2.5% — and in `strong4`, `llama4scout` at 0.658 accuracy has a 0.5% flip
rate, contributing almost nothing to the decision despite being present in it.

### 10.6 Gate

Identical verdicts on all three pools: **governance PARTIAL, delegation GO, coalition NO GO**,
selection = delegation.

| criterion | threshold | `strong4` | `decorr4` | `correlated4` |
|---|---|---:|---:|---:|
| protocol spread | >= 8pp | 3.37 FAIL | 7.14 FAIL | 6.20 FAIL |
| correct-answer dilution | >= 15% | 7.95 FAIL | 5.14 FAIL | 10.62 FAIL |
| intervention flip rate | >= 10% | 25.0 PASS | 24.5 PASS | 25.0 PASS |
| configuration dominance | <= 75% | 41.7 PASS | **75.0 PASS** | 58.3 PASS |
| semantic vs organizational | rho < 0.5 | 0.048 PASS | 0.048 PASS | 0.063 PASS |
| coalition top-k gap | >= 15% | 8.20 FAIL | 9.29 FAIL | 4.92 FAIL |

**Power.** At the observed discordance, detecting an 8pp paired difference at 80% power needs:

| pool | discordance | needed for 8pp | needed for 5pp | available |
|---|---:|---:|---:|---:|
| `strong4-a` | 9.4% | 86 | 270 | 178 |
| `decorr4-a` | 10.1% | 97 | 294 | 210 |
| `correlated4-a` | 12.3% | 130 | 365 | **129** |

So the 8pp gate failures are answers rather than shrugs on two pools, and `correlated4-a` sits one item
short of its own requirement — call it marginal. **All three are underpowered for a 5pp effect**, which
matters because most of the observed effects are in the 3–6pp range: absence of significance at that
magnitude is uninformative here, and the sign-stability analysis in §10.4 exists because the p-values
cannot carry the argument alone.

**Two cautions on the delegation PASS.** Configuration dominance reads exactly 75.0 against a 75%
ceiling on `decorrelated4` — passing by a margin of zero on one of three pools, with only seven
protocols to generate configurations. And the semantic-versus-organizational comparison used a TF-IDF
fallback in some runs when `sentence-transformers` could not reach the network; both paths were
measured and agree (Spearman 0.028–0.105 with real embeddings, 0.048–0.063 with the fallback), so the
criterion is not an artifact of the fallback, but each report must be read for which method it used.

---

## 11. The falsification episode

This is the most methodologically important result and is reported in full because the outcome was
negative.

**The observation.** After the first two priced pools, `expert_veto` was the best protocol in
`strong4` (+3.37pp) and the worst in `correlated4` (−6.20pp). Those pools were matched at
`single_expert` = 0.8989 and on dominance, differing only in error correlation. The interaction
measured **+9.57pp, 95% CI [+3.66, +15.70], p=0.0010**.

**The confound check.** Each pool had screened its own discriminating tasks, so pool and task set were
confounded. Restricted to the 95 tasks both pools ran, where the comparison is properly paired, the
effect was *larger*: **+10.53pp, 95% CI [+3.16, +17.89], p=0.0052**, with the sign differing on 14 of
95 tasks.

**The mechanism.** Letting a designated expert overturn a majority recovers answers when peers fail
independently and destroys them when peers fail together, because in a correlated pool the majority
being overridden was usually right for the same reason the expert was wrong.

**The pre-registration.** Before running the third pool, the prediction was written down (D-026):
`expert_veto` minus `single_expert` on `decorrelated4` (correlation +0.382, *more* decorrelated than
`strong4`) will be **strictly positive**; a point estimate at or below zero falsifies the mechanism,
and no reading of a null rescues it. Known weaknesses were recorded in advance, including that
`decorrelated4` is 9pp weaker in mean member accuracy.

**The result.** **−1.90pp** (n=210, 14 discordant, p=0.424). Falsified. And the effect is not
monotonic in the variable claimed to drive it:

| pool | error correlation | `expert_veto` |
|---|---:|---:|
| `decorrelated4` | +0.382 | **−1.90pp** |
| `strong4` | +0.408 | **+3.37pp** |
| `correlated4` | +0.579 | **−6.20pp** |

A moderator cannot act only in the middle of its own range.

**What it was.** The interaction rested on 5 and 11 discordant tasks — sixteen items carrying a 10pp
effect with p=0.005. That is the shape of sampling variation in a small discordant set. The bootstrap
interval was honest about its width and still excluded zero, which is the lesson worth keeping: **a
tight-looking interval computed on sixteen informative items tells you what those sixteen items said,
not that the effect is stable.**

**Cost of the refutation: $17.93.** The claim was one run away from being written into a paper.

---

## 12. Known defects and their effect on conclusions

### 12.1 Aggregator non-termination (D-028) — affects a headline conclusion

On a minority of tasks `claude-sonnet-5` spends all 16,384 output tokens on internal reasoning and emits
**zero** visible characters. `finish_reason` is `length`, so the episode is scored as an abstention and
therefore wrong. The penalty lands **only** on `independent_judge` and `chair_information_seeking` —
the two protocols the aggregator decides — and never on member-decided protocols.

Measured exactly ([`scripts/count_aggregator_truncation.py`](../../scripts/count_aggregator_truncation.py)):

| pool | `independent_judge` | `chair_information_seeking` | distinct tasks |
|---|---|---|---|
| `strong4` | 7 of 179 (3.9%) | 7 of 178 (3.9%) | 8 of 179 in scope |
| `decorrelated4` | 9 of 210 (4.3%) | 3 of 210 (1.4%) | 9 of 210 in scope |
| `correlated4` | 6 of 129 (4.7%) | 5 of 129 (3.9%) | 7 of 129 in scope |

**This corrects D-028**, which recorded "25 of 366 tasks, all GPQA-Diamond". The true figure is 24
distinct pool-task pairs (13 distinct tasks) within the priced discriminating subsets, not out of 366 —
the aggregator never ran on the other tasks. And the concentration is strong but not total: of 37
affected episodes, 33 are GPQA-Diamond and **4 are MATH-500**. The direction of D-028's argument is
unchanged, since dropping these episodes still removes disproportionately hard items.

Re-scored with the non-terminating episodes excluded:

| pool | `independent_judge` as scored | excluded | `chair` as scored | excluded |
|---|---:|---:|---:|---:|
| `strong4` | +0.56pp | +2.92pp (p=0.383) | +3.37pp | +5.85pp (p=0.053) |
| `decorrelated4` | +4.76pp | **+6.97pp (p=0.0066)** | +4.76pp | +5.31pp (p=0.043) |
| `correlated4` | +0.00pp | +3.25pp (p=0.424) | −3.10pp | −0.81pp (p=1.000) |

**The repair failed and cost $10.43.** OpenRouter's reasoning controls are silently ignored for
Anthropic models. Probed on the exact failing prompt, all four settings produced identical
non-termination:

| variant | output tokens | visible content | reasoning field |
|---|---:|---:|---:|
| as configured | 16,384 | 0 chars | 16,024 chars |
| `reasoning: {max_tokens: 1024}` | 16,384 | 0 chars | 15,634 chars |
| `reasoning: {effort: "low"}` | 16,384 | 0 chars | 15,366 chars |
| `reasoning: {exclude: true}` | 16,384 | 0 chars | hidden |

`exclude` suppresses only the *display* of reasoning, not its generation or its billing. The same
parameter genuinely fixed Gemini's runaway generation earlier (D-018), which is why it was tried. The
answer is also not recoverable from the discarded `reasoning` field: the text stops mid-sentence with
the model still working, having reached no conclusion.

**Reporting rule adopted.** Aggregator non-termination is **missing data**, and every
aggregator-decided figure is reported both ways. Neither is privileged: scored-as-wrong is the honest
deployment number, because a judge returning nothing has failed to judge; excluded is an upper bound
and a biased one, because non-termination concentrates on the hardest tasks — 33 of 37 affected
episodes are GPQA-Diamond.

**Effect on the headline.** Even on the optimistic accounting, `independent_judge` beats
`single_expert` significantly in one pool of three — and that pool is `decorrelated4`, the same pool
whose `expert_veto` result looked good and failed to replicate. One-of-three under favourable
accounting is not "reliably beats". The conclusion stands, but the accurate statement is **not** "no
protocol beats the expert"; it is that `independent_judge` is the most promising protocol measured and
we cannot presently tell whether it wins.

### 12.2 Superseded and diagnostic runs

`mvp366-a` was halted at 25% truncation and `decorrelated4-a` was superseded by a member swap; both
remain on disk. `pilot9-a`'s Stage A used `max_tokens` 1024 and is not comparable to later runs.

---

## 13. Decisions

The 28 numbered decisions are in [`DECISIONS.md`](../../DECISIONS.md). Those that shaped the experiment:

| id | decision |
|---|---|
| D-001 | Two-stage design: bank answers once, replay protocols |
| D-003, D-013 | Protocol branch points resolved by extraction, never a second model |
| D-004 | Predicted expert fitted on calibration split only |
| D-010, D-015, D-016 | Distributed-information condition constructed by option partitioning |
| D-011 | Answerless text is an abstention; extraction reimplemented |
| D-012 | Each proposed protocol pairs with a baseline differing by one rule |
| D-017 | Budget charged what the provider reports, not what we compute |
| D-018 | `max_tokens` is a validity guard, not a cost control |
| D-019 | An unfinished response is an abstention, never an answer |
| D-020 | Tasks screened for discrimination before Stage B is priced |
| D-021 | Pool headroom checked before Stage B is priced; gates the pool |
| D-022 | Commit rate >= 95% is a precondition on the instrument, not a score |
| D-023 | Error decorrelation is the design variable; homogeneity is a proxy |
| D-024 | Aggregator fixed across pools; chosen as the cost lever |
| D-025 | Pools selected at n=366; screen survivors must be banked before ranking |
| D-026 | Pre-registration of the veto/decorrelation prediction |
| D-027 | D-026 falsified; governance drops to NO GO on accuracy |
| D-028 | Aggregator non-termination is missing data; reasoning controls do not work for Anthropic |

---

## 14. Limitations

1. **Three domains, not four.** No code-execution path exists, so EvalPlus is absent.
2. **Absolute accuracy is not comparable across pools** (D-021), nor is any accuracy measured on a
   discriminating subset comparable to a full-suite figure — the subset is selected *because* protocols
   differ there.
3. **One seed.** Banked answers are temperature 0, so extra seeds would vary only protocol-internal
   randomness. Order effects were measured free and are 0.000 for the free protocols.
4. **The intervention flip rate criterion is near-tautological as specified** (§10.5) and should be
   re-specified before use.
5. **Configuration dominance passes by a zero margin on one pool** and has too few protocol families to
   be meaningful.
6. **Anonymization covers labels, not content.**
7. **`mixed_effects_logit` clusters on task via GEE** rather than fitting crossed task+seed random
   effects — adequate for an MVP, not for a paper.
8. **The distributed-information condition has never been run live**, and `out_of_set_rate()` has never
   been measured on real model output.
9. **Aggregator non-termination is unresolved** (§12.1) and blocks a clean answer on the most promising
   protocol.
10. **`decorrelated4` confounds decorrelation with competence**, averaging 0.734 against the control's
    0.842. `strong4` exists precisely to break that confound and should carry any governance claim.

---

## 15. What follows

**Delegation is the direction the gate chose.** The three learned models it needs — task encoder,
set-valued organization model, selector — are unwritten, and their training data already exists:
4,392 banked answers and 57,489 episodes across the three pools, all replayable at zero cost.

Before governance is revisited, three things should change:

1. **Fix or route around aggregator non-termination.** Requiring the answer letter *before* the
   explanation caps the cost of non-termination at zero, but it alters every aggregator prompt and
   therefore invalidates the entire priced cache — it belongs to the next round.
2. **Pre-register the two sign-stable patterns** before testing them, and test them on pools not used
   to find them.
3. **Re-specify the intervention flip rate** to exclude `single_expert`.

The governance material that survived is about **influence rather than accuracy**: masking changes the
vote's decision 5.3–8.5% of the time, and leverage diverges from competence within every pool. That is
a smaller claim than the one the project set out to make, and it is the one the data supports.
