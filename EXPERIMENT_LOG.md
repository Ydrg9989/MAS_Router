<!-- doc-meta
type:          ledger
lifecycle:     APPEND-ONLY — newest entry at top; contains superseded numbers by design
last-verified: 2026-08-11
evidence-base: data/runs/<run-id>/run_meta.json per entry
-->

# Experiment log

Append-only. Newest entry at the top. One entry per run that produced data, plus
entries for infrastructure milestones that change how later runs are interpreted.

Every entry must record: date, what was run, the exact command, the run id, cost, and
what was concluded. A run with no conclusion is an unfinished entry, not a finished one.

Runs are identified by `--run-id`; their artifacts live in `data/runs/<run-id>/`
alongside a `run_meta.json` capturing the pool, manifest hash, price snapshot and
upstream pins.

**This file is chronological and therefore contains superseded numbers.** For the settled
account, read [`Docs/archive/2026-08-10-governance-report.md`](Docs/archive/2026-08-10-governance-report.md), whose figures are
regenerated from the run records rather than transcribed.

---

## 2026-08-10 — the full report, and three figures that were wrong in this log

**What.** No new model calls. Every quantity in the log and in `DECISIONS.md` was recomputed from the
run records by [`scripts/collect_report_data.py`](scripts/collect_report_data.py) and written up as
[`Docs/archive/2026-08-10-governance-report.md`](Docs/archive/2026-08-10-governance-report.md). Three claims did not survive the check.

**1. D-028's "25 of 366 tasks, all GPQA-Diamond" was wrong twice.** The denominator was taken from the
suite, but the aggregator only ever ran on each pool's discriminating subset, so 366 was never the base.
The measured figure is 24 distinct pool-task pairs across 13 distinct tasks, at 1.4-4.7% per protocol
per pool. And of 37 affected episodes, 33 are GPQA-Diamond and **4 are MATH-500** — the concentration is
strong, not total. Neither correction changes D-028's conclusion, but "all GPQA-Diamond" was a claim
about the mechanism and it is false. Counted by
[`scripts/count_aggregator_truncation.py`](scripts/count_aggregator_truncation.py); D-028 amended.

**2. The headroom correlations were measured at n=120 and do not hold at n=366.** Recomputed over all
126 four-member subsets of the 9 reliable agents banked on the full suite:

| relationship | at n=366 | as first reported at n=120 |
|---|---:|---:|
| headroom vs mean error correlation | **−0.336** | −0.643 |
| headroom vs mean pool accuracy | **−0.307** | −0.618 |
| mean accuracy vs mean error correlation | **+0.821** | +0.741 |

The screen overstated the first two by roughly a factor of two. This is D-025's own warning applied to
D-023's evidence, and it further weakens the claim that decorrelation is only purchasable at low
competence — a tendency at −0.307, not the near-determinism −0.618 implied.

**3. The gate's "intervention flip rate" PASS is an artifact of its specification.** The criterion takes
the maximum over protocols, and the 24.5-25.0% that passes it comes entirely from `single_expert`, where
masking the predicted expert *necessarily* changes which answer is used. The meaningful number is the
vote's flip rate — 5.5%, 8.5% and 5.3% — and **no pool reaches the 10% threshold**. Read strictly,
governance fails all three of its criteria rather than two. The criterion needs re-specifying before it
is used again.

**Also corrected:** the project total is **$85.13**, not the $74.83 recorded on 2026-08-06, which
predated the $10.43 failed repair. `PROJECTSTATE.md` and `TODO.md` updated.

**Concluded.** None of this changes the gate's selection of delegation, and the direction of every
conclusion is intact. What it changes is the strength of three supporting claims, all three in the same
direction: the governance case is *weaker* than the log recorded, not stronger. Worth noting that all
three errors were transcription or denominator mistakes in prose rather than defects in the harness —
which is an argument for the report being generated from the records instead of written from them.

---

## 2026-08-06 — decorr4-a priced: the pre-registered prediction is refuted, for $17.93

**What.** The confirmatory test of [D-026](DECISIONS.md), written before the run: `expert_veto` was
predicted to beat `single_expert` on `decorrelated4` because that pool's errors are the most
decorrelated of the three (+0.382).

**Command.** As [`scripts/run_priced.sh`](scripts/run_priced.sh) but on `decorrelated4` and
`--tasks-from data/runs/decorr4-a/discrimination.json`; 975 new episodes, the 75 calibration ones
already banked. Analysis in [`scripts/test_d026.py`](scripts/test_d026.py).

**Cost.** $17.93 against a $48.80 estimate. Project total **$74.83**.

### The prediction failed

`expert_veto` minus `single_expert` is **−1.90pp** (n=210, 14 discordant, p=0.424), predicted strictly
positive. And the effect is not monotonic in the variable claimed to drive it:

| pool | error correlation | `expert_veto` |
|---|---:|---:|
| `decorrelated4` | +0.382 | **−1.90pp** |
| `strong4` | +0.408 | **+3.37pp** |
| `correlated4` | +0.579 | **−6.20pp** |

A moderator cannot act only in the middle of its own range. The +10.53pp interaction from yesterday's
two pools rested on 16 discordant items and did not replicate; it was sampling variation. D-026 is
withdrawn and the reasoning is in [D-027](DECISIONS.md).

The gate on this pool reads as on the others — governance FAIL on spread (7.14pp, closest of the three
and still short) and on dilution (5.1%), PASS on intervention flips (24.5%), delegation PASS on both,
coalition FAIL (9.3%).

### What three pools of priced episodes actually support

2,514 priced episodes across three pools. Effects are protocol minus `single_expert`, on each pool's
shared task set:

| protocol | `decorr` +0.382 | `strong` +0.408 | `corr` +0.579 | |
|---|---:|---:|---:|---|
| `independent_judge` | +4.76 | +0.56 | +0.00 | never negative |
| `chair_information_seeking` | +4.76 | +3.37 | −3.10 | sign varies |
| `debate_vote` | +5.24 | +0.00 | −3.88 | sign varies |
| `expert_veto` | −1.90 | +3.37 | −6.20 | sign varies |
| `expert_verifier` | −1.43 | +0.00 | −0.78 | never positive |
| `independent_majority` | −0.95 | +0.00 | −4.65 | never positive |

No protocol reliably beats deferring to the predicted expert, and the ones with the largest apparent
effects have the least stable signs. `independent_judge` never hurts and `expert_verifier` and plain
majority voting never help, which are the two patterns worth pre-registering *next* — and are
explicitly not findings here, because fifteen effects will produce a sign-stable one by chance.

**Concluded.** Governance drops to **NO GO** on accuracy grounds, and the honest reason is stronger
than the gate's: the effects exist but do not survive a change of pool. What does survive is the
influence measurement — mask-flip rates of 24.5-25.0% on all three pools, stable where accuracy effects
are not — so the governance material in this data is about influence diverging from competence, not
about which protocol wins. **Delegation is the direction**, passing both criteria on three independent
pools, with the caveat that configuration dominance reads exactly 75.0% against a 75% ceiling on
`decorrelated4` and needs more protocol families before it carries weight.

The refutation is the result worth having: the claim was one run from a paper, and it cost $17.93 and
one afternoon to kill rather than a post-publication correction.

---

## 2026-08-06 — strong4-a / correlated4-a priced: the gate fails, and the reason it fails is the finding

**What.** The five priced protocols on both pools' discriminating tasks — 894 episodes on the
treatment, 645 on the control — then the formal gate on each.

**Command.** [`scripts/run_priced.sh`](scripts/run_priced.sh), which is the two runs plus their
`--tasks-from` subsets, at concurrency 10.

**Cost.** $19.36 for `strong4-a` and $18.71 for `correlated4-a`, against dry-run estimates of $58.41
and $35.00 — so 3.0x and 1.9x conservative, the control being verbose. 94 minutes wall clock.
Running total for the project: **$56.90** of the $75 cap.

### The pre-registered gate

Identical verdicts on both pools: **governance PARTIAL, delegation GO, coalition NO GO.**

| criterion | threshold | `strong4-a` | `correlated4-a` |
|---|---|---:|---:|
| protocol spread | >= 8pp | 3.37pp FAIL | 6.20pp FAIL |
| correct-answer dilution | >= 15% | 7.9% FAIL | — FAIL |
| intervention flip rate | >= 10% | 25.0% PASS | 25.0% PASS |
| configuration dominance | <= 75% | 41.7% PASS | 58.3% PASS |
| semantic vs organizational | rho < 0.5, >= 20% differing | 0.028, 100% PASS | 0.063, 99.5% PASS |
| coalition top-k gap | >= 15% | 8.2% FAIL | 4.9% FAIL |

Power was adequate, so these are answers and not shrugs: at the observed 9.4% discordance an 8pp
paired difference needs 86 items and `strong4-a` has 178.

### Finding 1: no single protocol beats deferring to the predicted expert

Protocol minus `single_expert`, paired McNemar, on the tasks each pool's seven protocols share:

| protocol | `strong4-a` (n=178) | `correlated4-a` (n=129) |
|---|---:|---:|
| `expert_veto` | **+3.37pp** (8 disc, p=0.070) | **−6.20pp** (12 disc, p=0.039) |
| `chair_information_seeking` | +3.37pp (26 disc, p=0.327) | −3.10pp (20 disc, p=0.503) |
| `independent_judge` | +0.56pp (25 disc, p=1.000) | +0.00pp (18 disc, p=1.000) |
| `expert_verifier` | +0.00pp (8 disc, p=1.000) | −0.78pp (3 disc, p=1.000) |
| `debate_vote` | +0.00pp (22 disc, p=1.000) | −3.88pp (19 disc, p=0.359) |

Nothing survives Holm correction across the ten tests; the smallest adjusted p is 0.386. Whatever
`e_hat` picks is hard to improve on by talking about it, which is the report's thesis holding in the
uncomfortable direction: `debate_vote` never helps and costs 4pp in the control.

### Finding 2: the veto reverses sign with pool composition, and that is the largest effect present

`expert_veto` is the *best* protocol in the decorrelated pool and the *worst* in the correlated one.
The two pools were built to be matched on `single_expert` accuracy (0.8989 both) and on dominance
(0.3pp against 1.6pp) and to differ only in error correlation (+0.408 against +0.579), so this is the
interaction the design exists to detect:

| | effect of `expert_veto` |
|---|---:|
| decorrelated pool | **+3.37pp** |
| correlated pool | **−6.20pp** |
| interaction | **+9.57pp**, 95% CI [+3.66, +15.70], p=0.0010 |

Each pool screened its own discriminating tasks, so pool and task set were confounded. Restricted to
the 95 tasks both pools ran, where the comparison is properly paired, the effect is *larger*:
**+10.53pp**, 95% CI [+3.16, +17.89], **p=0.0052**, with the sign differing on 14 of 95 tasks. The
mechanism is legible: giving a designated expert the power to overturn a majority recovers answers when
peers fail independently, and destroys them when peers fail together, because in the correlated pool the
majority the veto overrides was usually right for the same reason the expert was wrong.

**Three reasons not to believe this yet.** It rests on 5 and 11 discordant tasks — 16 items carrying a
10pp interaction, hence a CI three percentage points wide at the low end. No component effect is
individually significant after correction. And the hypothesis was formed *after* seeing the sign flip:
the gate asks for spread within a pool, and nothing pre-registered predicted a moderator, because when
the gate was written we did not know pool composition was one.

**Concluded.** On the criteria as written, delegation is the GO and governance is PARTIAL. But the
governance direction failed a test that measures the wrong thing: protocol spread *within* one pool is
near zero precisely because the pool determines whether governance helps, and averaging over pools that
disagree in sign is how a real effect reads as no effect. The interaction is now an out-of-sample
prediction rather than a story — `decorrelated4` is banked, independent, and has the same decorrelation
property (+0.382), so `expert_veto` must help there too. That is a $17.50 confirmatory test of a
directional claim made in advance, and it is the natural next run.

---

## 2026-08-05 — screen-a / screen-strong / decorr4-a / correlated4-a: the two-pool design, priced

**What.** Ten candidate models screened on shared tasks, the two Stage-B pools selected from the
survivors, both banked over the full 366-task suite, the entire free half of Stage B run on each,
and the priced sweep calibrated on a 15-task slice.

**Commands.**

```bash
# screen ten candidates: six mid-tier, then six strong ones from unmeasured lineages
.venv/bin/python -m mas_harness.runners.answer_bank \
    --manifest data/manifests/screen120.json --pool configs/pools/candidates.yaml \
    --run-id screen-a --concurrency 12
.venv/bin/python -m mas_harness.runners.answer_bank \
    --manifest data/manifests/screen120.json --pool configs/pools/candidates_strong.yaml \
    --run-id screen-strong --concurrency 12
.venv/bin/python -m mas_harness.runners.answer_bank \
    --manifest data/manifests/hard366.json --pool configs/pools/candidates4.yaml \
    --run-id cand4-a --concurrency 12

# select on all 366 tasks, not on the screen
.venv/bin/python -m mas_harness.analysis.pool_select \
    --runs hard366-a cand4-a decorrelated4-a \
    --pools configs/pools/openrouter4.yaml configs/pools/candidates4.yaml \
            configs/pools/decorrelated4.yaml \
    --size 4 --out data/runs/pool_selection_366b.json

# bank both pools, check the precondition, screen for discrimination
for p in decorrelated4:decorr4-a correlated4:correlated4-a; do
    .venv/bin/python -m mas_harness.runners.answer_bank \
        --manifest data/manifests/hard366.json --pool configs/pools/${p%%:*}.yaml \
        --run-id ${p##*:} --concurrency 10
    .venv/bin/python -m mas_harness.analysis.headroom --run-id ${p##*:} --gate-pp 8
    .venv/bin/python -m mas_harness.analysis.discrimination \
        --run-id ${p##*:} --manifest data/manifests/hard366.json
done

# the free half of Stage B, both pools
.venv/bin/python -m mas_harness.runners.episodes \
    --manifest data/manifests/hard366.json --pool configs/pools/decorrelated4.yaml \
    --run-id decorr4-a --protocols single_expert independent_majority \
    --coalitions all --interventions none --concurrency 16
.venv/bin/python -m mas_harness.runners.episodes \
    --manifest data/manifests/hard366.json --pool configs/pools/decorrelated4.yaml \
    --run-id decorr4-a --protocols single_expert independent_majority \
    --coalitions grand --interventions all --concurrency 16

# calibrate the priced sweep before committing to it
.venv/bin/python -m mas_harness.runners.episodes \
    --manifest data/manifests/hard366.json --pool configs/pools/decorrelated4.yaml \
    --run-id decorr4-a --protocols independent_judge expert_verifier debate_vote \
    expert_veto chair_information_seeking \
    --coalitions grand --interventions none --tasks-from data/calib15.json --concurrency 6
```

**Cost.** $2.43 for `screen-a`, $7.06 for `screen-strong`, $0.36 for `cand4-a`, $0.26 for `ring26`
and $0.86 for `grok43` on the full suite, $0.00 for all three pool banks (cache hits) and for all
54,900 free episodes, $1.25 for the calibration slice. Running total for the project: **$18.83**.

### Finding 1: D-021 was the wrong diagnosis — correlation is, and homogeneity was a proxy

Twelve models screened, five excluded by the commit-rate floor (D-022): `minimax-m27` at 0.792,
`glm52` at 0.808, `nemotron3ultra` at 0.850, `kimi-k2-thinking` at 0.925, `gemini25flash-hi` at
0.650 and `glm45air` at 0.602. Across the 70 four-member subsets of the survivors, headroom
correlates with mean pairwise error correlation at **−0.643** and with mean pool accuracy at
**−0.618**, while accuracy correlates with error correlation at **+0.741**.

The refutation of D-021 is one row of that table: `deepseek32, gpt5mini, gptoss120b, qwen3-30b` is
the most competence-homogeneous pool available — **1.6pp** from best to second — and its headroom is
**4.92pp**, short of the gate. Homogeneity was necessary and not sufficient. The design variable is
error decorrelation, and dominance is one of two ways to lose it (D-023).

### Finding 2: decorrelation *does* survive at high competence — D-023's cost claim is refuted

D-023 recorded that decorrelation is available only at lower absolute accuracy, on the strength of
the −0.618 correlation above. That was an artifact of which models had been banked on the full suite.
`grok43` was screened, passed at **0.875 with a 1.000 commit rate**, and was then never carried past
120 tasks, so the n=366 selection never saw it. Banked for $0.86 it scores **0.885 on all 366 tasks**
with zero parse failures — the strongest and most reliable agent measured anywhere in this project —
and it is concise, averaging 1,329 output tokens where `kimi-k2-thinking` averages 6,927.

The pool it makes possible, `strong4` = `grok43, gpt5mini, deepseek32, llama4scout`, breaks the
trade-off the earlier slate implied:

| | `strong4` | `decorrelated4` | `correlated4` (control) |
|---|---:|---:|---:|
| mean member accuracy | **0.823** | 0.734 | 0.842 |
| dominance gap | **0.3pp** | 2.19pp | 1.6pp |
| error correlation | **+0.408** | +0.382 | +0.579 |
| ceiling | 96.72% | 93.99% | 93.17% |
| headroom | **8.20pp** | 9.29pp | 4.92pp — fails |
| `single_expert` accuracy | **0.8989** | 0.8552 | **0.8989** |

`strong4` and the control land on *exactly* the same `single_expert` accuracy, 0.8989 both, while
differing in headroom by 3.28pp and in error correlation by 0.171. That is the manipulation the design
wanted and could not previously have: competence held constant at the baseline that matters, dominance
matched to within 1.3pp, decorrelation varied. `decorrelated4` remains a useful low-competence
replication, but it confounds the contrast with an 11pp competence deficit and is no longer the
primary treatment.

### Finding 3: selection must run at n=366, because the screen's ranking does not survive

`ring26` looked like a strict improvement on the 120-task screen — headroom 9.89 to 10.83pp, dominance
3.02 to 1.67pp, correlation +0.409 to +0.392, all four criteria at once. Re-measured on 366 tasks it
*cost* 1.1pp of headroom (9.84 to 8.74pp) and *raised* correlation (+0.409 to +0.447). One task is
0.83pp at n=120 and 0.27pp at n=366, so pools separated by two tasks on the screen were not separated
at all. The screen is now used only to exclude broken instruments and to decide which models are worth
banking on the full suite; the selection itself runs at n=366.

### The two pools

Selected on the design's identifying requirement — matched on dominance, separated on correlation —
rather than on headroom alone, from the three admissible candidates at n=366:

| pool | dom | corr | head | \|Δdom\| vs control | Δcorr vs control |
|---|---:|---:|---:|---:|---:|
| `gptoss120b, llama4scout, mistral-small, ring26` | 2.19pp | +0.382 | 9.29pp | **0.54** | **0.197** |
| `gptoss120b, llama4scout, mistral-small, qwen3-30b` | 3.01pp | +0.409 | 9.84pp | 1.36 | 0.170 |
| `gptoss120b, llama4scout, qwen3-30b, ring26` | 2.19pp | +0.447 | 8.74pp | 0.54 | 0.132 |

| | `strong4-a` | `decorr4-a` | control `correlated4-a` |
|---|---|---|---|
| members | `grok43`, `gpt5mini`, `deepseek32`, `llama4scout` | `gptoss120b`, `llama4scout`, `mistral-small`, `ring26` | `gpt5mini`, `deepseek32`, `gptoss120b`, `qwen3-30b` |
| accuracies | 0.885, 0.882, 0.866, 0.658 | 0.825, 0.658, 0.604, 0.847 | 0.882, 0.866, 0.825, 0.795 |
| dominance gap | 0.3pp | 2.19pp | 1.6pp |
| error correlation | **+0.408** | **+0.382** | **+0.579** |
| ceiling / best member | 96.72% / 88.52% | 93.99% / 84.70% | 93.17% / 88.25% |
| headroom | **8.20pp** — admissible | **9.29pp** — admissible | **4.92pp** — fails by design |
| discriminating tasks | 39.9% (146 + 33 control) | 49.5% (181 + 29 control) | 23.5% (86 + 43 control) |
| dilution eligible | 15.3% | 24.6% | 10.9% |

The control is the pool D-023 was written about: near-perfect competence homogeneity, and half the
headroom, because its members are wrong about the same things. Its own diagnostic says so without
being told — "the members are near-equal (1.6pp from best to second) but err together at +0.579, so
competence homogeneity is not the constraint". All three pools use `anthropic/claude-sonnet-5` as
aggregator (D-024).

### Finding 4: the free protocols cannot reach the gate on any pool

Grand coalition, all 366 tasks, observational, plus the single-member mask flip rate on the vote:

| pool | `single_expert` | `independent_majority` | spread | discordant | mask flips |
|---|---:|---:|---:|---:|---:|
| `strong4-a` | 0.8989 | 0.8962 | 0.27pp | 19 (5.2%) | 5.5% |
| `decorr4-a` | 0.8552 | 0.8497 | 0.55pp | 18 (4.9%) — expert 10, vote 8 | 8.5% |
| `correlated4-a` | 0.8989 | 0.8825 | 1.64pp | 16 (4.4%) — expert 11, vote 5 | 5.3% |

Two protocols that disagree on 5% of items cannot differ by 8pp; the discordance *is* the bound. This
is not the D-020 or D-021 failure returning — headroom is 8.20pp and 39.9% of tasks discriminate on
`strong4-a` — it is that both free protocols read the same bank and mostly reach the same conclusion
from it. The gate is reachable only through protocols that transform the answers, and `single_expert`
already exceeds the best member on every pool (0.8989 against 0.8852 on `strong4-a`, 0.8552 against
0.8470 on `decorr4-a`), so most of the remaining headroom has to be won by a *worse* protocol rather
than a better one. Under the report's thesis that is the expected direction, but it is a prediction the
free half cannot test.

The mask flip rates are worth noting on their own: 8.5% on the decorrelated pool against 5.3% and 5.5%
on the other two, so removing one member changes the vote's decision half again as often when the
members disagree more — the causal-influence criterion behaving exactly as the mechanism predicts.

### Finding 5: the priced sweep costs $30-50, not $88-146, and the ordering is already visible

The estimator planned $3.75 for the slice and it cost **$1.2467** — 3.0x conservative, as D-024
warned, because it budgets 4,200 output tokens per carried peer answer where the reliable candidates
average 1,580. Applying that measured factor to the dry-run estimates: **$19.5** for `strong4-a`'s 179
tasks, **$17.5** for `decorr4-a`'s 210 and **$12** for the control's 129 — $31.5 for the two-pool
design or $49 for all three, against a $75 run cap. Wall clock was 7.4 s/episode at concurrency 6, so
roughly 1.5 h per pool at concurrency 12.

All seven protocols on the same 15 tasks, which is 2 tasks per percentage point and therefore an
ordering rather than a measurement:

| protocol | accuracy on the slice |
|---|---:|
| `single_expert`, `independent_judge`, `expert_veto`, `chair_information_seeking` | 0.800 |
| `debate_vote`, `expert_verifier` | 0.733 |
| `independent_majority` | 0.667 |

The vote is last and deferring to the expert is first, which is the direction the report predicts and
the opposite of what an additive account of team value would say. Note that `independent_majority`
reads 0.667 on this slice against 0.8497 on the full suite, which is what selecting for discrimination
does to an absolute rate: these 15 tasks were sampled from the 210 where the protocols *can* differ, so
no accuracy here is comparable to a full-suite figure. Only the between-protocol ordering is.

**Concluded.** The instrument is finished and three pools are characterized, two of them admissible.
Every precondition that killed an earlier run has been checked in advance this time: suite
discrimination (D-020) at 39.9-49.5%, pool headroom (D-021, D-023) at 8.20pp and 9.29pp, commit rates
(D-022) at 1.000 for every member of `strong4`, aggregator fixed across pools (D-024), and cost
measured rather than estimated. The design also improved in the course of checking it: `strong4` pairs
against the control at *identical* `single_expert` accuracy, which `decorrelated4` could not do.
What remains is the one irreducibly paid step: five protocols across 179-308 tasks per pool, $31.50
for the two-pool design, after which the gate can be evaluated on real numbers.

---

## 2026-08-05 — hard366-a: the suite is fixed, the pool is now the binding constraint

**What.** Stage A over the rebuilt 366-task hard manifest, then the discrimination screen, then
the entire free half of Stage B — all 15 coalitions observationally, plus masks, correct-answer
substitutions and reorderings on the grand coalition. 1,464 answers and 18,300 episodes.

**Commands.**

```bash
.venv/bin/python -m mas_harness.runners.answer_bank \
    --manifest data/manifests/hard366.json --pool configs/pools/openrouter4.yaml \
    --run-id hard366-a --concurrency 14

.venv/bin/python -m mas_harness.analysis.discrimination \
    --run-id hard366-a --manifest data/manifests/hard366.json

.venv/bin/python -m mas_harness.runners.episodes \
    --manifest data/manifests/hard366.json --pool configs/pools/openrouter4.yaml \
    --run-id hard366-a --protocols single_expert independent_majority \
    --coalitions all --interventions none --concurrency 16

.venv/bin/python -m mas_harness.runners.episodes \
    --manifest data/manifests/hard366.json --pool configs/pools/openrouter4.yaml \
    --run-id hard366-a --protocols single_expert independent_majority \
    --coalitions grand --interventions all --concurrency 16
```

**Cost.** $4.56 for Stage A. **$0.00** for all 18,300 episodes, which is the two-stage design
(D-001) doing exactly what it was built for: 10,980 episodes in 5 seconds and 7,320 more in 4.
Running total for the project: **$6.66**.

**Stage A health.** Accuracy `gpt5mini` 0.882, `qwen3-30b` 0.795, `gemini25flash` 0.623,
`mistral-small` 0.604. Parse failures 6.7%, unfinished 2.5% — down from 25% before D-018/D-019,
and now concentrated in Gemini at 7.6%. 309 of 1,464 calls disagreed with the provider's own cost
figure by more than 2%, which is why the ledger charges the provider's number (D-017).

### Finding 1: the rebuilt suite works

46.2% of tasks are discriminating, against 11.1% on `pilot9-b`. 13.4% are dilution-eligible — 22
`MINORITY_CORRECT` and 27 `TIE` tasks where a correct expert can be outvoted. Per suite,
GPQA-Diamond is 57.4% discriminating at 0.592 mean agent accuracy, MATH-500 level 5 is 45.1% at
0.855, and the hard MMLU-Pro sources are 36.1% at 0.732. Nothing is saturated. The ceiling on
protocol spread is now 46.2pp against a gate threshold of 8pp, so D-020's problem is solved.

### Finding 2: the phenomenon is real, and small

Dilution is genuinely present. On the 49 tasks where it is possible at all, `independent_majority`
loses **22.9%** of the tasks its predicted expert got right, against `single_expert` at 0%.
Masking one member of the grand coalition changes the vote's decision **25%** of the time, so the
gate's causal-influence criterion passes at n=2,928 pairs. The influence profile is exactly the
competence-versus-influence gap the report asks for:

| agent | competence | mask flip rate | leverage | flips to correct / to wrong |
|---|---:|---:|---:|---:|
| `gpt5mini` | 0.883 | 0.131 | 2.13 | +7 / −21 |
| `qwen3-30b` | 0.795 | 0.030 | 0.54 | +5 / −2 |
| `gemini25flash` | 0.623 | 0.025 | 0.57 | +1 / −7 |
| `mistral-small` | 0.604 | 0.016 | 0.39 | +4 / **−0** |

`mistral-small` is the clean case: every decision its presence changes, it changes for the worse.
`KL(influence ‖ competence)` is 0.256 for the vote. Order sensitivity is 0.000 for both free
protocols, which is the correct sanity check — neither reads speaking order — so any order effect
found later is attributable to the priced protocols rather than to the harness.

But pooled over all 366 tasks, dilution is only **2.48%**, and the two free protocols disagree on
just **11 of 366** grand-coalition tasks (3.0%). At that discordance a 5pp effect is not merely
undetectable, it is *arithmetically impossible*; a 3pp effect would need 136 items, and we have
366.

### Finding 3: one dominant agent is what compresses the effect (D-021)

`P(at least one member correct)` on the grand coalition is 92.62% and `gpt5mini` alone scores
88.25%, so **4.37pp** is the total accuracy available to every governance rule combined. The gate
asks for 8pp. No protocol we had not yet paid for could have cleared it.

Headroom tracks the presence of the dominant agent, not the difficulty of the tasks:

| coalition | ceiling | best member | headroom |
|---|---:|---:|---:|
| `gemini25flash` + `mistral-small` | 79.51% | 62.30% | **17.21pp** |
| `gemini25flash` + `qwen3-30b` + `mistral-small` | 89.07% | 79.51% | 9.56pp |
| `gemini25flash` + `qwen3-30b` | 86.89% | 79.51% | 7.38pp |
| grand coalition | 92.62% | 88.25% | 4.37pp |
| `gpt5mini` + `qwen3-30b` | 89.89% | 88.25% | 1.64pp |

The expert-versus-aggregation effect *reverses sign* across the split: with `gpt5mini` present,
deferring to the expert wins by 0.74pp at 1.8% discordance; without it, the vote wins by 4.58pp
at 5.1% discordance. On `gemini25flash` + `mistral-small`, two agents 1.9pp apart in competence
whose errors decorrelate, the vote beats the stronger member by 12.6pp.

Every coalition containing `gpt5mini` also scores *at or below* `gpt5mini` alone (0.8825 solo
versus 0.8689 for the full four), so there is no complementarity for the coalition direction to
find either. That is what the gate's 4.4% top-k gap was reporting.

**Concluded.** The harness, the suite and the metrics are all working; the free half of Stage B
now produces every governance number the report asks for at zero marginal cost. The binding
constraint has moved from task difficulty to pool composition, and competence homogeneity is
promoted to a design variable (D-021). Stage B must not be priced on this pool: the gate is
unreachable on it by arithmetic. The next run screens candidate peer models for a
comparable-competence pool, keeping the present pool as the dominant-agent control that shows the
governance effect vanishing.

**Delegation direction, incidentally.** With real `sentence-transformers` embeddings rather than
the TF-IDF fallback, semantic and organizational task similarity correlate at Spearman **0.105**
with 98.9% of tasks having a different nearest neighbour in the two spaces. That criterion passes
on n=366. Configuration dominance reads 83.3% and fails, but with only two protocols in the
family that number is not yet interpretable.

---

## 2026-08-05 — mvp366-a (halted) / probe-gpqa / probe-fixed: the suite, not the harness, was the problem

**What.** Stage A on the powered 366-task manifest, halted at 118 of 1,464 calls when 25% of
responses were found to be truncating again. Two probes followed: `probe-gpqa` lifted the cap
to 24,576 to measure the natural length distribution, and `probe-fixed` verified the remedy.

**Cost.** $0.61 (halted) + $0.46 (probe) + $0.27 (verify) = **$1.35**. Running total for the
project to date: **$2.10**.

### Finding 1: MATH-500 and MMLU-Pro STEM are saturated for this pool

The Stage B run on `pilot9-b` produced *identical* outcomes for all seven protocols on all
nine tasks — zero discordant pairs — and the chair declined to ask a question every time. The
answer bank explains why: MATH-500 scored 12/12 and MMLU-Pro STEM 12/12, while GPQA-Diamond
scored 7/12. Seven of the nine tasks had all four agents give the same correct answer.

This is a structural ceiling, not a small-sample accident. When four agents agree, every
protocol returns their answer by construction, so the task contributes a concordant pair to
every comparison and nothing at all to a McNemar test. **The spread between the best and worst
protocol cannot exceed the fraction of tasks on which agents disagree.** On `pilot9-b` that
ceiling was 11.1pp against a gate threshold of 8pp; aiming an 8-point effect at a suite with
that little room would have returned NO GO on evidence incapable of saying otherwise.

Once the token bugs below were fixed, GPQA-Diamond measured **66.7% discriminating and 33.3%
dilution-eligible**, against 0% for both other domains. The phenomenon is observable; the
domain mix was hiding it. `mas_harness/analysis/discrimination.py` now computes this from the
answer bank alone, before any protocol is priced.

### Finding 2: 8192 was still too small, and the third estimate came from measurement

GPQA-Diamond output averaged 3,713 tokens with the 90th percentile sitting exactly on the 8192
cap. Lifting the cap to 24,576 in `probe-gpqa` gave the distribution that should have set it:
the longest *self-terminating* response was 13,606 tokens (Qwen3-30B), against 6,742
(GPT-5-mini), 4,712 (Gemini) and 1,023 (Mistral-Small). The pool is now at **16384**.

### Finding 3: Gemini 2.5 Flash does not reliably terminate, and a parameter fixes it

On 5 of 12 GPQA questions Gemini ran to the 24,576-token wall, emitting up to 88,000
characters of unterminated chemistry that circled through possibilities without concluding.
Since its terminating responses never exceeded 4,712 tokens, this is non-termination rather
than long reasoning, and no achievable cap fixes it. Three further calls returned provider
errors, so two thirds of its GPQA answers were unusable and its cost was 3x any other member.

`reasoning: {enabled: false}` did not help — it still ran to the wall. `reasoning:
{max_tokens: 2048}` did: the same question finished in 4,706 tokens with a boxed answer.
Verified on all 12 in `probe-fixed`, where its unfinished rate fell from over 40% to 16.7%
and the pool's overall unfinished rate to 4.2%. The consequence is that Gemini is now a
*configured system* rather than a vendor default, and the paper cannot make a capability claim
about "Gemini 2.5 Flash" from this pool. The alternative was dropping the model and with it
the four-family heterogeneity the pool exists to provide.

### Finding 4: a data-integrity bug — unfinished responses were being scored as answers

`parse_failed` was computed as `not extracted`, ignoring `finish_reason` entirely. Three of
Gemini's five runaway responses still yielded a letter under strict extraction, because
unterminated reasoning is full of provisional lines like "this would give B" written while
enumerating options the model went on to reject. The extractor takes the last match, which in
a truncated stream is wherever the cut fell rather than a conclusion. One errored response
with zero reported output tokens was likewise banked as a valid answer.

A response that never terminated is an abstention, not a wrong answer, and conflating the two
inflates the error rate of precisely those agents that reason at length — the same verbosity
bias D-018 exists to prevent. Stage A now requires a natural stop before an answer counts, and
reports the unfinished rate per agent as its own line rather than folding it into parse
failures.

**Concluded.** The halted `mvp366-a` bank must not be used: it is 25% truncated and predates
the integrity fix. The suite needs rebuilding around material that discriminates —
GPQA-Diamond (198 available), MATH-500 level 5 (134 available) and the harder MMLU-Pro STEM
sources (`theoremQA` 524, `scibench` 541) are the candidates. Because Stage A *is* the screen,
answers banked while screening are reused by Stage B, so nothing is paid for twice.

---

## 2026-08-05 — pilot9-a / pilot9-b: first live runs. Truncation was masquerading as incompetence

**What.** The report's day-11 token-calibration pilot, run twice. Nine tasks (three each from
MATH-500, GPQA-Diamond, MMLU-Pro STEM) x 4 agents. `pilot9-a` used the pool as committed,
`max_tokens: 1024`. `pilot9-b` repeated it at `max_tokens: 8192` after `pilot9-a` failed.

**Commands.**

```bash
.venv/bin/python -m mas_harness.tasks.manifest build --suite configs/suites/pilot9.yaml
.venv/bin/python -m mas_harness.runners.answer_bank --manifest data/manifests/pilot9.json \
    --pool configs/pools/openrouter4.yaml --run-id pilot9-a --concurrency 6
.venv/bin/python -m mas_harness.runners.answer_bank --manifest data/manifests/pilot9.json \
    --pool configs/pools/openrouter4.yaml --run-id pilot9-b --concurrency 4
```

**Cost.** $0.0433 (pilot9-a, 32 calls) + $0.0698 (pilot9-b, 36 calls) = **$0.113**, both
figures provider-reported.

### The finding that mattered

| | pilot9-a (1024) | pilot9-b (8192) |
|---|---|---|
| records written | 32 of 36 | 36 of 36 |
| `finish_reason: length` | 12 | 1 |
| parse failure rate | 28.1% | 0.0% |
| pooled accuracy | 0.531 | 0.861 |

Every one of the nine parse failures in `pilot9-a` had `finish_reason: length`. The extractor
was not at fault: the models were cut off mid-derivation before stating an answer. Raising the
cap moved pooled accuracy from 0.531 to 0.861, and per-agent accuracy from
`{0.67, 0.44, 0.56, 0.40}` to `{0.89, 0.89, 0.78, 0.89}`.

Had the MVP run at 1024, it would have measured a fictional world in which all four agents are
mediocre and roughly indistinguishable. That is not a cost error, it is a validity error, and
it would have gone straight to the heart of the project: the expert-based protocols
(`single_expert`, `expert_verifier`, `expert_veto`) all presuppose that competence differences
exist and are detectable. Truncation flattens exactly that signal, and flattens it *unevenly*
— the agents that reason at length are penalised most, so the "expert" would have been an
artifact of brevity.

### Three further problems, all fixed

1. **The spend ledger was recording the wrong number.** It recorded our locally computed cost.
   OpenRouter's per-model price is a headline figure and requests are routed to one of several
   upstream providers at their own rates: measured, Qwen3-30B billed up to **2.69x** our
   estimate and Mistral-Small **0.80x**. The ledger now records the provider's own figure and
   the pre-call guard carries a 3x safety factor. The computed figure is still stored, because
   the disagreement is the diagnostic D-005 was built for — 10 of 32 calls disagreed by more
   than 2%, and that is now understood rather than mysterious.
2. **One agent lost 4 of its 9 answers to HTTP 429** "engine_overloaded" on OpenRouter's
   shared upstream pool, which outlasts a five-attempt retry window. Raised to eight attempts;
   `pilot9-b` then completed 36 of 36. A missing cell is worse than a slow one, because it
   unbalances the paired design every later comparison depends on.
3. **`max_tokens` is not a cost control.** Qwen returned 2562 and 6808 output tokens under a
   1024 cap: some upstream providers do not honour it. It is a truncation guard only; cost is
   controlled by the ledger.

### Measured token figures, replacing the report's assumptions

The report assumed 1,200 input and 500 output per call. Measured: **285 input** (4.2x
overestimate) and **1,552 output** (3.1x underestimate). Both planning constants are updated.

The aggregator figure was worse. It assumed a flat 4,000-token prompt, but an aggregator
prompt quotes every member's full answer, so at 1,552 tokens per member a four-member
coalition puts ~6,900 tokens in front of it. Aggregator cost now scales with coalition size,
which changes the projected cost of the two most expensive protocols by roughly 70%.

### Projected cost of the real experiment, at measured rates

Stage A is negligible: $0.0019 per call, so 366 tasks x 4 agents is $2.84. Stage B over the
grand coalition with all seven protocols is $14 at 90 tasks, $32 at 200, and **$58 at 366** —
and 87% of that is the two protocols that use the Claude aggregator
(`chair_information_seeking` 59%, `independent_judge` 28%). The all-15-coalition sweep remains
free, because the two protocols it uses make no API calls (D-009).

**Concluded.** The harness works end to end against live models and the cost model is now
measured rather than assumed. `pilot9-a` should not be used for anything: its answer bank is
28% truncated and 4 cells short. Nine tasks cannot support any claim about protocols, and no
accuracy figure here should be quoted — the point was calibration, and the calibration
changed the design.

---

## 2026-08-05 — Infrastructure: distributed-information condition, and three reproducibility bugs

**What.** Built the controlled distributed-information substrate that replaces the
unobtainable HiddenBench (D-010, D-015), and fixed three bugs found while doing it (D-016).

**The construction.** Option-set partitioning rather than generated clue text: each member
sees the question stem plus a subset of the lettered options, the union covers the whole set,
and only the designated holders can see the correct one. This makes individual insufficiency
*provable* — a member that cannot see the correct option cannot state it — instead of an
empirical claim about generated text that would need its own validation run. Zero generation
cost. Every member sees the same number of options so set size cannot betray the holder, and
the holder rotates round-robin so "the holder prevailed" is not "the model in that seat
prevailed".

Two arms are committed, sharing a seed so they draw the same questions and the same
partitions and differ only in what members are told: `distributed30` warns members and lets
them decline, `distributed30_pressure` does neither. Both are needed, because the cooperative
arm alone would show that plurality voting *succeeds* (the holder is the only member voting)
which is a fact about calibration, not governance.

**Verified mechanically, no API calls.** Over the derived tasks, the real
`independent_majority` protocol never carries the correct answer on a plurality — only one
member can cast it, so a correct outcome only ever came from a four-way split resolved by the
deterministic tie-break. Deferring to the holder recovers every task. That is the gap
protocols 6 and 7 have to close without being told who the holder is.

**Three bugs found and fixed.**

1. *Manifests were not reproducible.* `_sample` was seeded with `abs(hash(suite))`, and
   `hash()` on a string is salted per interpreter — measured three different values in three
   processes. Every rebuild drew a different task set, which defeats the point of the
   content-hash immutability check. Now derived with `hashlib`.
2. *The content hash did not cover the partition.* It hashed only task id, suite and ground
   truth, so changing the partitioning algorithm left `distributed30`'s hash unchanged. For
   this suite the partition *is* the task. The hash now includes a digest of the private
   briefings.
3. *The distributed suite was domain-skewed.* Oversampling then slicing an id-sorted list
   gave 7/7/7/7/1/1 across six domains. Trimming through the stratified sampler gives 5 of
   each.

Also: a pool whose agent ids do not match the manifest's is now refused before any spend,
because a member without a briefing is silently asked a multiple-choice question with no
options and produces garbage that reads as model failure. And `--dry-run` with no route to
the price list now explains itself instead of surfacing an `httpx.ProxyError` traceback.

**GPU diagnostic.** This host has no GPU: `nvidia-smi` cannot reach a driver *and* there are
no `/dev/nvidia*` device nodes, so it is not a sandbox artifact. The local-vLLM branch is
closed; OpenRouter only, as D-006 anticipated.

**Cost.** $0.00. No API calls were issued. Three manifests rebuilt (`mvp90`,
`distributed30`, `distributed30_pressure`); all hashes changed, and nothing depended on the
old ones because no run has happened.

**Concluded.** 266 tests pass, lint clean. A Stage A dry run over a distributed arm plans 120
calls. The harness is complete for the MVP, the proposed interventions, and the
distributed-information condition. Still blocked only on `OPENROUTER_API_KEY`.

---

## 2026-08-04 — Infrastructure: proposed protocols, role rotation, end-to-end validation

**What.** Completed the harness: added protocols 6 and 7 (`expert_veto`,
`chair_information_seeking`) as one-rule contrasts against the baselines they are paired
with (D-012, D-013), wired Latin-square role rotation into Stage B behind
`--role-rotation` (D-014), and validated the full pipeline end to end on a synthetic
answer bank.

**The end-to-end validation.** `tests/test_pipeline.py` plants a 40-task, 4-agent bank in
which agent 1 is right on 36 of 40 while the other three agree on a wrong answer on 24 of
them, plus one 2-2 contested group. It then runs the *real* Stage-B runner over all 15
coalitions, the real record writers, and the real gate. Every quantity was derived by hand
before the run and asserted: single-expert accuracy 0.90 versus majority 0.40 on the grand
coalition, a dilution rate of 26.8% pooled over coalitions, and a mask-flip rate of exactly
4/40 for the two agents holding the contested winning answer and 0 for the other two.

**Bug found and fixed.** Multi-round debate re-showed members the *round-zero* banked
answers in every round after the first, because the peer block was read from the answer
bank rather than from the running positions. Rounds beyond the second would therefore not
have been a debate at all. Fixed by threading the previous round's positions through
`format_peer_answers(texts=...)` and `revision_prompt(own_text=...)`, with a snapshot per
round so simultaneous revision really is simultaneous. Regression test:
`tests/test_roles.py::test_debate_round_two_shows_the_latest_positions_not_the_bank`. The
default two-round configuration was unaffected, so no earlier result is invalidated —
there are no earlier results.

**Also.** Pinned the ruff rule set explicitly in `pyproject.toml`, since a clean lint run
is only evidence if the rule set does not drift with the installed version.

**Cost.** $0.00. No API calls were issued.

**Concluded.** 226 tests pass, lint is clean. The harness is complete for the MVP and the
proposed interventions. Stage A remains blocked only on `OPENROUTER_API_KEY`.

---

## 2026-08-04 — Infrastructure: harness foundation stood up

**What.** Created the `mas_harness` package, the two-stage answer-bank/episode design,
the OpenRouter client with cost accounting, task manifests over the local HuggingFace
cache, the seven-protocol registry, the intervention layer, the metrics and statistics
modules, and the go/no-go gate.

**Environment.** Python 3.12.11 venv at `.venv`, `teamwork` on the import path via
`upstream_teamwork.pth`. Upstream repos pinned in `UPSTREAM.md`.

**Verified against real data, zero API cost.** The free pilot ran on
`agent-psychometrics/data/swebench_verified/responses.jsonl` (134 agents x 500 tasks,
density 1.0). See the entry below.

**Cost.** $0.00. No API calls were issued.

**Concluded.** The harness is ready for Stage A. No `OPENROUTER_API_KEY` is present in
the environment yet, so no live run has been attempted; `mas_harness.doctor` reports
this as the single remaining blocker for Stage A.

---

## 2026-08-04 — Free pilot: coalition analysis validated on the SWE-bench Verified matrix

**What.** Validated the entire coalition analysis pipeline against a real, fully dense
agent-by-task outcome matrix before committing any budget.

**Command.**

```bash
.venv/bin/python -m mas_harness.analysis.free_pilot \
    --benchmark swebench_verified --n-agents 4 --n-pools 200 --seed 0
```

**Data.** 134 agents x 500 tasks, density 1.0, per-agent accuracy 0.4%-79.2%.

**Cost.** $0.00 — the matrix is already on disk.

**Concluded.** See the generated report at
`data/runs/free_pilot/<benchmark>_report.json` and the summary printed by the command.
The purpose of this run is to prove the analysis code is correct and numerically
sensible, not to make a claim about heterogeneous LLM teams — the "agents" in this
matrix are whole scaffold+model systems answering independently, so coalition values
here are *simulated* from independent outcomes rather than observed from real
interaction. That distinction is recorded on the report as
`"coalition_values": "simulated_from_independent"`.

---

## 2026-08-10 — crosscap240 Stage A and free Stage B on all three pools

**Runs.** `crosscap-strong4`, `crosscap-decorr4`, `crosscap-corr4`, launched as three parallel
processes with per-process run caps of $15/$5/$8 so their sum could not breach the daily cap. The
ledger reads the day's total once at construction, so parallel processes do not see each other's
spend; the per-run cap is the guard that still works.

**Cost.** $3.64 today, against a $9.61 dry-run estimate. Stage A: strong4 $2.11, corr4 $1.05,
decorr4 $0.46, plus a $0.02 smoke test. Stage B was free: 21,552 episodes over two protocols and all
15 coalitions, at $0.00.

**The smoke test paid for itself.** Twelve tasks for $0.022 surfaced two extraction failures that
would have run through all 2,880 Stage A calls. One model answered AIME with `\boxed{721}` - correct -
and no `[ANSWER]` tag; another was cut off by `max_tokens` mid-delimiter at `[ANSWER][][/`, so a
complete and correct `[]` would have scored zero. Both are now accepted: `\boxed{}` because it is an
explicit declaration rather than a terminal-token guess, and an unterminated open tag because the
answer was reached before truncation. Parse failures on the full runs came in at 1.1-3.1%.

**The suite discriminates, unlike hard366.** Agents disagree on 42-80% of tasks depending on suite and
pool, against the 11% that made mvp366 useless (D-020). More importantly the *ranking reverses across
capabilities*, which no previous suite produced: in `strong4`, grok43 is the best agent on code
reasoning at 0.97 and the worst on theory of mind at 0.13, while deepseek32 is 0.85 and 0.80. In
`corr4`, deepseek32 leads theory of mind at 0.82 while gpt5mini leads every other capability and
scores 0.32 there.

**Reproducibility is 10-50x better than hard366, and still not decisive.** Off-dominant
reproducibility - whether the capabilities that depart from the single best configuration reproduce -
against a 0.5 floor:

| pool | reproducibility | null | dominance | on dominant | off dominant | verdict |
|---|---:|---:|---:|---:|---:|---|
| `crosscap-strong4` | 0.402 | 0.042 | 50.0% | 0.583 (2) | 0.220 (2) | no evidence |
| `crosscap-decorr4` | 0.558 | 0.039 | 50.0% | 0.382 (2) | **0.735** (2) | evidence |
| `crosscap-corr4` | 0.409 | 0.042 | 25.0% | 0.237 (1) | 0.467 (3) | no evidence |

On hard366 the same statistic read 0.01, 0.02 and 0.15. Here it reads 0.22, 0.74 and 0.47, and
`decorrelated4` clears the floor outright.

**Where the signal sits.** Theory of mind is the capability that departs from the dominant
configuration in all three pools, and it reproduces at 0.44, 0.76 and 0.63 - the most orthogonal
capability behaving exactly as the D-032 hypothesis predicted. GPQA-Diamond is the opposite: it
departs too, but reproduces at 0.00, 0.00 and 0.24, contributing nothing but noise.

**The limitation is the number of groups, not the number of tasks.** Four capabilities means the
off-dominant statistic averages two or three groups, so it swings between pools for reasons that may
be sampling alone. Sixty tasks per group is adequate; four groups is not. The next round should add
capabilities rather than tasks - gsm8k, ai2_arc, MATH-500 and MMLU-Pro are all in the local cache and
would take the design to eight groups for roughly $4.

---

## 2026-08-10 — the first leak-free router, on both suites and all three pools. $0

**What was built.** [`mas_harness/metrics/routing.py`](mas_harness/metrics/routing.py) fits
`q(x, S, p)`, the probability that a coalition running a protocol solves a task, and routes each
test task to its argmax. Task features are frozen MiniLM embeddings of the prompt, reduced by a PCA
fit on calibration tasks alone; organization features are protocol, membership, size and member
competence measured on calibration singletons. Twelve tests in
[`tests/test_routing.py`](tests/test_routing.py) cover planted signal, planted noise, and the two
leaks that manufactured the earlier delegation results.

**Both leaks from D-030 are closed, including one in the baseline.**
`utility.fixed_best_selection` chooses its single configuration by maximising utility *on the set it
is then scored on*, so the "baseline any router must beat" was itself an oracle over configurations.
Every baseline here is frozen on calibration tasks before it sees a test task, and a test asserts it
scores zero on data where the calibration winner is the test loser.

**Design, identical in all six cells.** Both suites ran on the same three pools with the same two
free protocols, so every cell offers the same 30 organizations and differs only in the tasks. 366
tasks (123 calibration) for `hard366`, 240 (79) for `crosscap240`.

**The single manifest split looked promising and was noise.** On `crosscap-decorr4` the best single
agent beat the best organization by 10.7 points (p=0.001) and `q_theta` scored +2.5 (p=0.070). Over
60 stratified resplits those became +0.39 and −1.78. Reporting one split would have produced two
false findings, so `routing_over_splits` now repeats the whole evaluation and the resplit mean is
the number of record.

**Result: nothing captures the headroom, on either suite.** Mean gain over the frozen fixed-best
baseline across 60 resplits, in accuracy points:

| suite / pool | headroom | q_theta | shuffled control | semantic kNN | selection gap |
|---|---:|---:|---:|---:|---:|
| `hard366` / `strong4` | 8.29 | +0.33 | −0.32 | +1.40 | +2.89 |
| `hard366` / `decorrelated4` | 8.54 | −0.53 | −1.09 | −0.16 | +2.22 |
| `hard366` / `correlated4` | 4.44 | −0.42 | −1.32 | −0.51 | +1.91 |
| `crosscap240` / `strong4` | 9.38 | +0.08 | −2.80 | +1.01 | +2.11 |
| `crosscap240` / `decorrelated4` | 11.10 | −1.78 | −1.18 | −0.96 | +2.85 |
| `crosscap240` / `correlated4` | 8.43 | +0.03 | −1.99 | −1.36 | +2.02 |

`q_theta` is ahead of doing nothing in 13-47% of splits depending on the cell, never a majority. The
cross-capability suite does **not** rescue routing: its three cells average −0.56 against −0.21 for
the homogeneous suite, the opposite of the D-032 prediction.

**But the representation is not worthless, and that is the interesting part.** The shuffled-embedding
control loses 1-3 points in every cell, so *choosing per task at all* costs about two points of
variance when there are 30 organizations and ~100 calibration tasks. The real embedding beats its own
shuffled twin in 5 of 6 cells. The semantic signal is real and worth roughly what the selection
variance costs, which nets to zero. Selection variance, not representation quality, is what is
binding.

**The same effect appears in the baseline.** Identifying one fixed best organization from calibration
data costs 1.9-2.9 points on average, with a spread of 3.2-5.3 points - a quarter to a half of the
headroom being competed for, spent before any routing happens.

---

## 2026-08-10 — pooled suites: the learning curve is flat and the group-count fix fails. $0

**Why pool.** Two questions were open. Whether the routing null is an absence or a sample-size
result, which needs a learning curve; and whether `crosscap240`'s off-dominant reproducibility of
0.735 was real, which needs more than the two groups it averaged. Both suites ran on the same three
pools with the same two free protocols and share 37 GPQA tasks, so they concatenate into 569 unique
tasks over 15 domains with calibration sets up to 398 - four times either suite alone, and the group
count the previous entry said was the binding limitation.

**The learning curve does not exist.** Mean `q_theta` gain over frozen fixed-best, 40 resplits per
point, as calibration grows sevenfold:

| calibration tasks | 57 | 114 | 199 | 284 | 398 |
|---|---:|---:|---:|---:|---:|
| `strong4` | +0.27 | −0.21 | −0.20 | +0.15 | +0.37 |
| `decorrelated4` | −1.02 | −1.28 | −0.86 | −1.12 | −1.22 |
| `correlated4` | +0.24 | −0.61 | −1.03 | −1.04 | −0.67 |

Flat in all three pools, against 4.1-9.7 points of headroom that stays available throughout. The
spread halves as calibration grows - `correlated4` goes from sd 1.94 to 0.68 - so the estimate
becomes *more* precise and stays at zero. This is the strongest form the negative can take: not
"we could not detect a gain" but "there is no gain to detect at any calibration size this design
can reach".

**The shuffled control does not improve either**, holding at −0.8 to −2.3 across the whole sweep. The
cost of choosing per task is not a small-sample effect that more calibration data pays off.

**Fifteen groups kill the crosscap reproducibility result.** The previous entry attributed the
swing between pools to averaging two or three groups and predicted more capabilities would settle
it. It settles it against the hypothesis:

| pool | reproducibility | null | dominance | off-dominant | verdict |
|---|---:|---:|---:|---:|---|
| `strong4` | 0.636 | 0.232 | 0.67 | 0.100 (5) | no evidence |
| `decorrelated4` | 0.703 | 0.171 | 0.67 | 0.257 (5) | no evidence |
| `correlated4` | 0.622 | 0.313 | 0.47 | 0.291 (8) | no evidence |

Overall reproducibility is far above the null in all three pools (p=0.000) and the groups won by the
dominant configuration reproduce at 0.90-1.00. But the departures - the only part routing could act
on - reproduce at 0.10 to 0.29, all below the 0.5 floor. `decorrelated4`'s 0.735 on `crosscap240`
was an average over two groups and did not survive contact with fifteen.

**Reading.** Both open questions are now closed in the same direction, and they agree with the
routing result rather than merely accompanying it: there is one broadly best organization per pool,
the per-domain departures from it are noise, and a router therefore has nothing to learn - which is
exactly what a flat learning curve at zero looks like from the modelling side.

---

## 2026-08-10 — the headroom was never there. $0

**The check.** Every headroom figure this project has reported is a per-task maximum minus one
organization. That statistic is large whenever the family is wide and noisy: thirty organizations
that are each 85% accurate and fail semi-independently will contain a correct one on almost every
task, whether or not any of them is *suited* to it. Before concluding that a real prize goes
unclaimed, the prize had to be tested
([`scripts/check_oracle_headroom.py`](scripts/check_oracle_headroom.py)).

**The null.** An additive logistic model of outcome on organization and task, main effects only, is
fit to each observed table and used to simulate replacement tables. Every organization keeps its
overall accuracy, every task keeps its difficulty, and the organization-by-task interaction - the
entire content of "different organizations suit different tasks" - is removed. Headroom is then
recomputed on the simulated tables.

**Observed headroom is at or below the no-interaction null in all six cells.** Measured against the
best organization on the same tasks, so that selection noise is absent from both sides:

| suite / pool | observed | null | excess | p |
|---|---:|---:|---:|---:|
| `hard366` / `strong4` | 7.00 | 6.97 | +0.02 | 0.635 |
| `hard366` / `decorrelated4` | 7.41 | 8.95 | −1.54 | 0.940 |
| `hard366` / `correlated4` | 3.70 | 6.16 | −2.46 | 0.995 |
| `crosscap240` / `strong4` | 10.00 | 9.56 | +0.44 | 0.430 |
| `crosscap240` / `decorrelated4` | 8.18 | 10.84 | −2.66 | 0.970 |
| `crosscap240` / `correlated4` | 6.25 | 7.30 | −1.05 | 0.845 |

**The one apparent exception was a baseline artifact.** Measured against the calibration-picked fixed
organization, `crosscap240`/`decorrelated4` showed +5.24 over the null at p=0.010 - the same cell
that produced the 0.735 off-dominant reproducibility and the 10.7-point single-agent anomaly. Its
calibration draw picked a fixed organization that scored 0.736 on test when a single agent scored
0.843, and the inflated gap is that mistake, not an interaction. Against the best organization on
test it reads −2.66.

**What this settles.** The four to eleven points of "unclaimed headroom" reported throughout this
project, including in the entry immediately above, are what maximising over a wide noisy family
produces when there is nothing to find. No router failed to capture a prize; there was no prize. The
flat learning curve, the unreproducible per-domain departures, and the null routing gain are three
views of one fact.

**A precondition needs re-examining.** The pool-headroom gate that decided which pools received
priced episodes (D-021, D-023) uses the same statistic, `P(at least one member correct) - best
member`, over four agents rather than thirty organizations. Four is a much narrower family so the
inflation is smaller, but it is the same inflation and those figures - 8.20, 9.29 and 4.92 points -
have not been tested against this null.

---

## 2026-08-10 — the same illusion on 134 public agent systems. $0

**Why this matters more than the internal result.** A null that only fires on this project's own
grid says the pools were unlucky. The statistic it retires - best single system against "at least one
system solves it" - is the standard motivation for agent routing, selection and ensembling, so the
question is whether it holds up anywhere. SWE-bench Verified through `agent-psychometrics` is the
hardest available test: 134 independently built systems, different scaffolds, base models, labs and
years, on 479 instances
([`scripts/check_headroom_swebench.py`](scripts/check_headroom_swebench.py)).

**Observed headroom is below the no-interaction null at every pool size.**

| systems | best single | oracle | headroom | null | excess | p |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0.804 | 0.887 | 8.33 | 10.22 | −1.88 | 0.940 |
| 8 | 0.804 | 0.896 | 9.17 | 12.12 | −2.95 | 0.970 |
| 16 | 0.804 | 0.921 | 11.67 | 14.07 | −2.40 | 0.955 |
| 32 | 0.804 | 0.929 | 12.50 | 14.92 | −2.42 | 0.965 |
| 134 | 0.804 | 0.950 | 14.58 | 17.23 | −2.65 | 0.970 |

The headline gap grows from 8 to 15 points as the family widens, exactly as it should when the
statistic is measuring family width rather than complementarity, and the null grows faster
throughout. At no size does the observed gap exceed what independent failure produces.

**The excess is consistently negative, which is its own finding.** Real agent systems are *less*
complementary than independence would predict - they share base models, training data and failure
modes - so the honest reading is not merely "there is no bonus" but "there is a correlation penalty".

**Scope, carefully.** This concerns per-task *selection*: the claim that different systems suit
different tasks, which is what a router needs. It says nothing against *aggregation*. Voting over
semi-independent members genuinely beats the best member under exactly the independence this null
assumes, which is the Condorcet effect and is why D-029 found whole-pool majority vote to be the one
reproducible organizational fact. Complementarity in the aggregation sense is real here; what does
not exist is a per-task assignment of tasks to systems.

---

## 2026-08-10 — the positive control fails, and explains why. $0

**What was being tested.** A null that is only ever satisfied might simply be unbeatable, so D-034
needs a case where it fires. The cheapest candidate was already banked: `crosscap240` Stage A covers
eight distinct agents on 238 shared tasks over four capabilities, and their per-capability accuracies
differ enormously. Individual agents are also the sharper test, since D-034 measured organizations,
where four members are averaged together by voting
([`scripts/check_headroom_specialists.py`](scripts/check_headroom_specialists.py)).

**The interaction is unmistakable in the raw table.** Accuracy by capability, over all 238 tasks:

| agent | code | maths | science | theory of mind | spread |
|---|---:|---:|---:|---:|---:|
| ring26 | 0.883 | 0.862 | 0.767 | 0.700 | 0.183 |
| deepseek32 | 0.850 | 0.690 | 0.800 | 0.800 | 0.160 |
| gpt5mini | 0.933 | 0.828 | 0.800 | 0.233 | 0.700 |
| qwen3-30b | 0.783 | 0.707 | 0.683 | 0.600 | 0.183 |
| grok43 | 0.967 | 0.793 | 0.817 | 0.133 | 0.833 |
| gptoss120b | 0.600 | 0.776 | 0.667 | 0.383 | 0.393 |
| llama4scout | 0.650 | 0.172 | 0.533 | 0.583 | 0.478 |
| mistral-small | 0.783 | 0.310 | 0.483 | 0.233 | 0.550 |

**No pool exceeds the null, including one assembled to.** Selecting the best agent per capability on
calibration tasks and scoring on test tasks gives excess −2.16 (p=0.883). The three shipped pools
give +1.33 (p=0.330), −0.14 and +2.44 (p=0.203). All eight together give −0.80.

**Why, and this is the finding.** Look at which capability each agent is *best* at: for seven of
eight it is code, and for the eighth it is maths. Not one agent's strongest capability is theory of
mind. The profiles are near-monotone transformations of a single difficulty ordering - code above
maths and science, theory of mind far below - and agents differ in overall strength and in how
steeply they fall, not in what they are for. That is main-effect structure, which is exactly what the
additive null models, so the null fits well and there is no excess to find. The genuine crossing is
narrow: `deepseek32` and `ring26` hold up on theory of mind (0.800, 0.700) where `grok43` and
`gpt5mini` collapse (0.133, 0.233).

**Specialisation also cuts both ways for the oracle.** When `grok43` falls to 0.133 on theory of
mind it creates a routing opportunity *and* removes a member from the union on those same tasks. For
a per-task maximum the two effects roughly cancel, which is why headroom does not respond to
interaction even where interaction plainly exists.

**The practical consequence: voting already collects it.** A domain router handed the *true*
capability label of every test task, picking each capability's best agent from calibration - an upper
bound on any learned router over individual agents - against plain majority vote over the same four
agents:

| pool | best single | domain router | majority vote | oracle | router − vote |
|---|---:|---:|---:|---:|---:|
| `strong4` | 0.792 | 0.830 | 0.836 | 0.937 | −0.6 pp |
| `decorrelated4` | 0.843 | 0.736 | 0.811 | 0.931 | −7.5 pp |
| `correlated4` | 0.805 | 0.881 | 0.855 | 0.943 | +2.5 pp |

Routing beats the best single agent in two pools of three, so the specialisation is real and
exploitable. It does not beat running everyone and voting, which needs no task representation, no
calibration and no router.

**One honest qualification, and it is the strongest remaining case for routing.** The router makes
one call where the vote makes four. Losing 1.9 points on average at a quarter of the cost is a real
trade, and a cost-adjusted comparison could favour routing. The claim this supports is therefore
narrow and specific: routing does not buy *accuracy* over aggregation. Its case is efficiency.

---

## 2026-08-10 — the efficiency case does not survive either, and two wrong ways to ask. $0

**What was being tested.** The qualification above, which was the last live argument for routing:
that per-capability selection buys accuracy per dollar even though it does not buy accuracy. Both
policies are chosen on the same calibration tasks from the same 30 organizations, and differ only in
whether the choice is made once for the suite or once per capability
([`scripts/measure_cost_frontier.py`](scripts/measure_cost_frontier.py)). Cost is repriced from token
buckets against each run's frozen snapshot, so cache hits are charged what a first run would pay;
`independent_majority` over k members is charged for k, and `single_expert` for the one member it
consults, since its predictor reads calibration accuracy and never inspects the current answers.

**Two formulations that flattered routing, and why.** A first pass swept a cost penalty
`accuracy - lambda * cost` and took the best gap over twelve lambdas, comparing against the most
favourable rival, giving +4 to +16 points at p<=0.006. Both the lambda and the rival were chosen on
the data that scored them, which is the D-034 artefact exactly. Moving that selection to a held-out
half of the test tasks and averaging over 200 resplits still gave +2.6 to +16.6 points, positive in
86 to 100 per cent of splits, which looked like a genuine result.

It was not. Sweeping a linear penalty over a set of points traces only the *upper convex hull* of
that set, so any organization that is Pareto-efficient while sitting inside the hull is invisible to
the global policy at every lambda. A routed policy mixes per capability and can land precisely in
that concave region, appearing to beat the global frontier while merely filling a gap the sweep can
never reach. The gain was an artefact of the question's shape.

**The formulation without a blind spot.** Fix a budget in dollars per task and let each policy take
the most accurate organization it can afford. That reaches the full Pareto frontier rather than its
hull, needs no penalty parameter, and is the form a deployer's constraint actually takes. Budgets are
the distinct organization prices, so they are exactly the points where the affordable set changes.

**Result: routing loses at an unconstrained budget, in all six cells.** Mean gain over 200 resplits,
routed minus global:

| suite | pool | unlimited budget | positive in |
|---|---|---:|---:|
| `hard366` | `strong4` | −3.15 pp | 2% |
| `hard366` | `decorrelated4` | −1.70 pp | 9% |
| `hard366` | `correlated4` | −2.48 pp | 8% |
| `crosscap240` | `strong4` | −0.48 pp | 29% |
| `crosscap240` | `decorrelated4` | −1.97 pp | 11% |
| `crosscap240` | `correlated4` | −3.94 pp | 7% |

**And it mostly loses under tight budgets too.** Across roughly twenty budgets per cell the curve is
negative at most points. The one substantial exception is `crosscap240`/`correlated4` at
$0.000453 per task: +11.53 points, positive in 100% of 200 splits, with the routed policy spending
$0.000397 against the global policy's $0.000315, both inside budget.

**That exception is not capability specialisation.** The routed policy wins there because an
organization's price *varies by capability* - shorter prompts and shorter answers on some domains -
so an organization whose average price exceeds the budget is still affordable on the domains where it
is cheap. Real, and a legitimate way to spend a budget, but a different claim from "different tasks
suit different organizations", and confined to one cell of six at one narrow band of budgets. At the
very tightest budget in every one of the six cells, all capabilities receive the *same* organization,
so routing degenerates to the global policy exactly where the budget binds hardest.

**Conclusion.** The efficiency case that D-035 left open does not survive a properly posed budget
comparison. Routing buys neither accuracy nor accuracy per dollar over choosing one organization
well. The residual effect that does exist is priced-by-domain arbitrage, not delegation.

---

## 2026-08-10 — the headroom null, sharpened. $0

**Why.** Writing `Docs/paper/FRAMEWORK.md` exposed a real defect in the D-034 null: it draws organizations
independently, but organizations share members, so its oracle is too generous and the test
under-rejects. D-034's conclusion was therefore conservative rather than wrong, and a conservative test
cannot carry the claim.

**What was built.** An agent-level null that simulates correctness from `sigma(alpha_a + beta_x)`,
converts it to answers, and pushes those through the real voting and expert-selection code
([`mas_harness/metrics/sharing_null.py`](mas_harness/metrics/sharing_null.py), 11 tests). Member
sharing is exact. Per-task difficulty, per-agent strength, per-agent abstention rate and each task's
distractor concentration are preserved; only the association between which agent fails and which task
it fails on is removed.

**Validation.** Replaying the observed answers reproduces the recorded episodes at agreement 1.0000 in
all six cells, certifying both the fast equivalence-class voting and the transitivity of the upstream
equivalence relation. Four planted specialists over four capabilities are detected at p<0.05 with
excess above 5 points, so the test has power.

**The null did move, in the predicted direction.** Headroom against the best test organization, mean of
200 simulations:

| suite / pool | observed | independent null | sharp null | sharp excess | p |
|---|---:|---:|---:|---:|---:|
| `hard366`/`strong4` | 7.00 | 6.97 | 4.79 | +2.20 | 0.045 |
| `hard366`/`decorrelated4` | 7.41 | 8.95 | 6.25 | +1.16 | 0.260 |
| `hard366`/`correlated4` | 3.70 | 6.16 | 3.78 | −0.07 | 0.585 |
| `crosscap240`/`strong4` | 10.00 | 9.56 | 10.22 | −0.23 | 0.605 |
| `crosscap240`/`decorrelated4` | 8.18 | 10.84 | 8.23 | −0.05 | 0.560 |
| `crosscap240`/`correlated4` | 6.25 | 7.30 | 9.49 | −3.24 | 0.965 |

**Verdict unchanged.** One cell of six under 0.05, where at least one such cell arises 26% of the time
under the global null and the Bonferroni threshold is 0.0083. D-034 stands, now on an instrument with
demonstrated power.

**A statistic retired along the way.** Headroom against the *calibration-picked* organization reads
+10.55 at p=0.010 on `crosscap240`/`decorrelated4`, which looks like a finding until one notices the
calibration pick underperforms the best test organization by 11.3 points in that cell. That is the
winner's curse of D-033, not interaction; the same cell reads −0.05 against the best test organization.
Only the latter is about the structure of the outcome table.

**Not sharpenable.** The 134 SWE-bench systems have no member decomposition, so that external
validation remains the conservative independent null and is labelled as such.

---

## 2026-08-10 — Three evidence gaps closed before drafting: the interaction test, the lambda artefact, the capability table

Building `Docs/paper/PAPER_BACKBONE.md` and `Docs/paper/CLAIM_EVIDENCE_MATRIX.md` surfaced three things that had to
be settled before any prose: a central claim resting on descriptive geometry rather than a test, a
headline number with no surviving artefact, and a planned figure whose data had only ever been printed
to a terminal. All three are free — no API spend. Total project cost remains $85.13.

**1. The interaction likelihood-ratio test (D-038).** New module
[`mas_harness/metrics/interaction.py`](mas_harness/metrics/interaction.py) with ten tests; driver
[`scripts/measure_interaction.py`](scripts/measure_interaction.py); artefact `data/runs/interaction.json`.
Fits `sigma(alpha_u + beta_x)` against `sigma(alpha_u + beta_x + gamma_{u,c(x)})` and tests `gamma = 0`
by parametric bootstrap, at both the agent and the organization level.

    agents        hard366       LR  104.0  df  77  p=0.164   excess departure  -0.00 pp
    agents        crosscap240   LR  301.9  df  21  p<=0.005  excess departure  +7.29 pp
    organizations hard366/strong4        LR  293.9 df 319 p=0.692   -0.35 pp
    organizations hard366/decorrelated4  LR  305.9 df 319 p=0.731   -0.07 pp
    organizations hard366/correlated4    LR  410.4 df 319 p<=0.005  +0.26 pp
    organizations crosscap240/strong4        LR 1185.2 df 87 p<=0.005 +6.71 pp
    organizations crosscap240/decorrelated4  LR  662.6 df 87 p<=0.005 +4.21 pp
    organizations crosscap240/correlated4    LR  685.2 df 87 p<=0.005 +3.78 pp

Three findings. The suite manipulation is validated for the first time directly: no detectable
interaction anywhere on `hard366`, large interaction at both levels on `crosscap240`. The predicted
agent-versus-organization contrast did **not** appear — aggregation does not destroy the interaction,
so FRAMEWORK 5.3's wording was too strong and has been weakened to "absorbs the exploitable part". And
the headline sharpens: on the three `crosscap240` cells, interaction is significant at `p<=0.005` while
sharp-null headroom excess on the *same tables* is −0.23, −0.05 and −3.24 (`p` = 0.605, 0.560, 0.965).
Headroom is insensitive, not merely inflated.

Two methodological notes. The p-value is a parametric bootstrap, not chi-squared, because one nuisance
parameter per task is the incidental-parameter setting. The effect size is the excess of mean absolute
cell departure over the null's own departure, added after noticing that the raw departure of 6-9 pp is
roughly what sampling noise alone produces at sixty tasks per cell — reporting it unadjusted would have
repeated the exact error the headroom statistic makes. `hard366`/correlated4 illustrates the point:
`p<=0.005` with an excess of 0.26 pp on 10,980 observations.

**2. The lambda-sweep artefact, regenerated (D-039).** The historical figures had no artefact behind
them and the two records disagreed (FRAMEWORK 6.1: +2.6 to +16.6 in 86-100% of resplits; D-036: +4 to
+16 at `p<=0.006`). A faithful re-implementation over 200 resplits gives best-lambda gains of +3.36,
−0.02, +1.06, +7.02, +3.47 and +7.99 points, positive in 44-94%. **It reproduces neither record**, so
both are retired and the paper cites the regenerated numbers. The qualitative artefact is intact: the
same data gives −0.48 to −3.94 under budget matching, so the sign still flips.

Added alongside it, a hull diagnostic that measures Lemma 2 rather than only proving it. Of 30
organizations per cell, 7-14 are Pareto-efficient, only 3-6 are reachable by any lambda, and 3-9 are
Pareto-efficient yet invisible to the global policy at every lambda. That count is the artefact's
mechanism, stated without reference to any retracted number.

**3. The capability table, persisted.** `accuracy_by_capability` now written into
`data/runs/headroom_null_specialists.json` with all-task and calibration-only variants, peak capability
and spread per agent. Values reproduce the FRAMEWORK 5.1 table exactly: seven of eight agents peak on
code reasoning, one on competition maths, none on theory of mind or graduate science, spread from 0.160
(`deepseek32`) to 0.833 (`grok43`).

Full suite: 412 tests pass.
