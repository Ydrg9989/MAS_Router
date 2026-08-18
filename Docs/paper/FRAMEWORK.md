<!-- doc-meta
type:          living
lifecycle:     update-in-place
last-verified: 2026-08-14
evidence-base: data/runs/{pool_sweep_*,research_questions,positive_selection,judge_replication,judge_on_easy_tasks}.json
-->

# Framework, claims, and design

> **Status, 2026-08-14.** This file was written when the study was six pool-by-suite cells. It is now
> 280 pools, four additional research questions, a purchased second suite and five further decision
> records (D-040 to D-044). §8 has been rewritten against that evidence; **§1–§7 still describe the
> design correctly but their numbers are the six-cell versions** — for figures, use
> [`CLAIM_EVIDENCE_MATRIX.md`](CLAIM_EVIDENCE_MATRIX.md), which is authoritative. Two things in
> §5 no longer hold and are marked inline.

What the project is arguing, what each claim rests on, and the mathematics the argument needs. Written
before any paper structure, so that the structure follows the argument rather than the reverse.
`DECISIONS.md` records how we got here; `EXPERIMENT_LOG.md` records what was run. This file is the
statement of the position.

---

## 1. The object of study

### 1.1 Notation

| symbol | meaning |
|---|---|
| \(x \in \mathcal{X}\) | a task, drawn from a suite with distribution \(P_X\) |
| \(c(x)\) | the task's *capability* label (code execution, competition maths, theory of mind, graduate science) |
| \(A = \{a_1,\dots,a_n\}\) | the agent pool: \(n\) distinct LLM configurations, each with a price |
| \(S \subseteq A\), \(S \neq \emptyset\) | a coalition |
| \(p \in \Pi\) | a protocol: the rule turning a coalition's contributions into one answer |
| \(o = (S,p) \in \mathcal{O}\) | an **organization**. In the priced data \(\lvert\mathcal{O}\rvert = 30\): 15 non-empty coalitions over 4 agents, 2 protocols |
| \(Y(x,o,s) \in \{0,1\}\) | outcome under seed \(s\) |
| \(C(x,o,s) \ge 0\) | monetary cost |
| \(q(x,o) = \mathbb{E}_s\,[Y(x,o,s)]\) | success probability |

The experimental unit is the cell \((\text{task} \times \text{pool} \times \text{organization} \times \text{seed})\) mapping to outcome, transcript, cost, latency and metadata. Everything below is a
functional of that grid.

### 1.2 The two-stage factorization, and why it is what makes this affordable

For the *aggregation* protocols there exists a deterministic \(\phi_p\) with

$$
Y\big(x,(S,p),s\big) \;=\; \phi_p\Big(\{Z(x,a,s)\}_{a \in S}\Big),
$$

where \(Z(x,a,s)\) is agent \(a\)'s independent answer. `independent_majority` is a plurality vote over
answers grouped by task equivalence; `single_expert` selects one member using a predictor fitted on
calibration data alone.

Two consequences carry the whole project:

1. **Stage B is free.** 4,392 banked answers generate 57,489 episodes at zero marginal cost, which is
   why the project has cost USD 85.13 in total.
2. **Interventions are exact.** Masking, substituting or reordering a member's contribution is an edit
   to the bank, so \(do(\cdot)\) is applied to the same \(\phi_p\) rather than re-elicited. Causal
   quantities are computed, not estimated from re-runs.

The price is that protocols requiring genuine interaction (debate, chair questioning) fall outside
\(\phi_p\) and must be paid for. They ran on `hard366` only, which is why every cross-suite comparison
is restricted to the two free protocols.

---

## 2. The decision problem the field is implicitly posing

A **router** is a map \(\pi : \mathcal{X} \to \mathcal{O}\), with value

$$
V(\pi) \;=\; \mathbb{E}_x\big[\,q(x,\pi(x))\,\big].
$$

The relevant comparisons form a ladder, in increasing order of information:

| policy | definition | information used |
|---|---|---|
| best single agent | \(\max_{a} \mathbb{E}_x[q(x,(\{a\},\cdot))]\) | calibration outcomes |
| **best fixed organization** | \(V_{\mathrm{fix}} = \max_{o} \mathbb{E}_x[q(x,o)]\) | calibration outcomes |
| learned router | \(V(\hat\pi)\), \(\hat\pi\) fitted on calibration tasks | calibration outcomes + task text |
| **capability router** | \(\mathbb{E}_x\big[\max_o \mathbb{E}[q \mid c(x)]\big]\) | calibration outcomes + *ground-truth* capability label |
| oracle router | \(V_{\mathrm{orc}} = \mathbb{E}_x[\max_o q(x,o)]\) | per-task outcomes (unavailable) |

Two of these do specific work. **Best fixed organization** is the baseline any routing claim must
beat, because it is what a practitioner gets for free by picking one system and keeping it. The
**capability router** is an *upper bound on any learned router* whose representation is a function of
the capability partition: it is handed the label a learned model would have to infer, and its per-group
choice is optimal on calibration. If the capability router fails, no learned router over that family
can succeed. This is the single most load-bearing design decision in the project, because it converts
"our model did not work" into "no model of this kind can work here".

**Oracle headroom** is

$$
H \;=\; V_{\mathrm{orc}} - V_{\mathrm{fix}} \;\ge\; 0 .
$$

\(H\) is the quantity routing papers cite as the prize. Section 3 shows it is not one.

---

## 3. Contribution 1 — oracle headroom is not evidence of routable structure

### 3.1 Under additivity the population headroom is exactly zero

**Proposition 1.** Suppose \(q(x,o) = g(\alpha_o + \beta_x)\) for some strictly increasing \(g\), with
organization effect \(\alpha_o\) and task effect \(\beta_x\) and no interaction term. Then
\(\arg\max_o q(x,o) = \arg\max_o \alpha_o\) for every \(x\), so the oracle router is a *constant* map, it
coincides with the best fixed organization, and \(H = 0\).

*Proof.* For fixed \(x\), \(g\) is increasing, so ordering organizations by \(q(x,o)\) orders them by
\(\alpha_o\), independent of \(x\). Likewise \(\mathbb{E}_x[g(\alpha_o+\beta_x)]\) is increasing in
\(\alpha_o\), so the best fixed organization is also \(\arg\max_o \alpha_o\). The two maximisers coincide
and the difference vanishes. \(\square\)

So \(H > 0\) requires an interaction term. That is the sense in which headroom *seems* to be evidence.

### 3.2 But the empirical estimator is positive even when the truth is zero

With finitely many seeds, \(\hat q(x,o)\) is a noisy Bernoulli mean, and

$$
\hat H = \frac{1}{m}\sum_x \max_o \hat q(x,o) - \max_o \frac{1}{m}\sum_x \hat q(x,o) > 0 \quad\text{almost surely,}
$$

because a per-task maximum over \(\lvert\mathcal{O}\rvert\) noisy estimates is biased upward while the
outer maximum over organization means is not. The bias grows with \(\lvert\mathcal{O}\rvert\) and shrinks
with the number of seeds. In our grid \(\lvert\mathcal{O}\rvert = 30\) with one seed, which is the
worst case.

**Therefore \(\hat H\) must be compared against its own null distribution, never against zero.** Every
published headroom figure we are aware of is compared against zero.

### 3.3 The test

Fit the additive model \(\Pr[Y(x,o) = 1] = \sigma(\alpha_o + \beta_x)\) by penalised logistic regression
on train tasks; simulate Bernoulli outcomes on test tasks; recompute \(\hat H\) per simulation. The
\(p\)-value is the fraction of simulations with \(\hat H_{\text{null}} \ge \hat H_{\text{obs}}\)
([`mas_harness/metrics/routing.py`](../../mas_harness/metrics/routing.py),
`headroom_against_no_interaction`).

Result: excess is at or below chance in all six pool-by-suite cells, largest \(+0.44\) points at
\(p = 0.43\); over the four-agent family that D-021 and D-023 used to justify spending, \(+1.33\)
(\(p=0.330\)), \(-0.14\) and \(+2.44\) (\(p=0.203\)); on the 134-system SWE-bench Verified matrix, observed
headroom sits *below* the null.

### 3.4 The weakness in the first null, and its repair

The null of §3.3 draws each organization's outcome independently given the fitted marginals. Real
organizations **share members**: `independent_majority` over \(\{a_1,a_2,a_3\}\) and over
\(\{a_1,a_2,a_4\}\) agree whenever \(a_1\) and \(a_2\) do. Positive correlation across organizations makes
the *real* per-task maximum smaller than an independent maximum at the same marginals, so the null's
oracle is too generous and the test **under-rejects**.

The repair uses the two-stage factorization of §1.2. Simulate at the *agent* level under an additive
agent-by-task model \(\sigma(\alpha_a + \beta_x)\), then push the simulated answers through the real
\(\phi_p\). Member sharing is then exact, because one simulated answer for \(a_1\) feeds every
organization containing \(a_1\), and the only thing removed is agent-by-task interaction. Three pieces
of observed structure are preserved on purpose: per-task difficulty, per-agent strength and
abstention propensity, and **how concentrated each task's wrong answers are** — on a multiple-choice
item four agents can converge on one distractor and outvote a correct minority, while on an
open-response maths item wrong answers are nearly all distinct and a lone correct member wins.
Implemented in [`mas_harness/metrics/sharing_null.py`](../../mas_harness/metrics/sharing_null.py).

**The diagnosis was right and the verdict is unchanged.** Replaying the observed answers through the
fast equivalence-class voting path reproduces the recorded episodes at agreement **1.0000 in all six
cells**, which certifies both the reimplementation and the transitivity of the equivalence relation.
The sharp null's headroom is substantially lower than the independent null's, exactly as the
correlation argument predicts — on `hard366` it falls from 6.97, 8.95 and 6.16 to 4.79, 6.25 and 3.78
— so excesses move up by one to three points. They do not move enough to change anything. Against the
best organization on test, excesses under the sharp null are \(+2.20\) (\(p=0.045\)), \(+1.16\), \(-0.07\),
\(-0.23\), \(-0.05\) and \(-3.24\). One cell of six below \(0.05\) is what the global null predicts; at least
one \(p<0.05\) among six tests occurs 26% of the time, and the Bonferroni threshold here is \(0.0083\).

**The test has power.** A planted structure of four agents over four capabilities, each competent at
exactly one, is detected at \(p<0.05\) with an excess above 5 points
([`tests/test_sharing_null.py`](../../tests/test_sharing_null.py)). So "no excess" is now a statement
from an instrument that fires when the structure is there, which is what §3.3 could not claim.

**One statistic to avoid.** Headroom measured against the *calibration-picked* organization rather
than the best organization on test conflates interaction with selection noise. On
`crosscap240`/`decorrelated4` it reads \(+10.55\) at \(p=0.010\), but the calibration-picked organization
underperforms the best test organization by 11.3 points there — the winner's curse D-033 documented,
not interaction. Against the best test organization the same cell reads \(-0.05\). Only the second
variant answers a question about the structure of the outcome table.

**Scope, now that the null is sharp.** Claim C1 can say that observed headroom does not exceed a null
that removes agent-by-task interaction while preserving member sharing, difficulty, strength,
abstention and distractor concentration, on a test with demonstrated power. It still should not be
phrased as "no interaction exists": §5.2 shows crossing interaction does exist. The correct statement
is that the interaction present is not of a kind or magnitude that a per-task maximum can detect.

---

## 4. Contribution 2 — the negative, established at three levels

Ordered so that each level makes the next one's failure unsurprising rather than anecdotal.

**Level 1: a learned router gains nothing.** A leak-free \(q_\theta(x,S,p)\) with frozen prompt
embeddings, protocol and coalition features and calibration-derived competence gains nothing over a
frozen fixed-best baseline, on both suites, all three pools, over 60 resplits, with a flat learning
curve across a sevenfold increase in calibration size (D-033).

**Level 2: a router with ground-truth labels also fails, which bounds every learned router.** The
capability router of Section 2 beats the best single agent in two pools of three — so the
specialisation is real and exploitable — but does not beat plain majority voting over the same four
agents: \(-0.6\), \(-7.5\) and \(+2.5\) points. Majority voting needs no task representation, no calibration
and no router.

**Level 3: the efficiency defence fails under the correct comparison.** Section 6.

The three levels answer three different objections: "your model was bad", "your representation was
bad", and "you measured the wrong currency".

---

## 5. Contribution 3 — the mechanism

Interaction is not absent. It is present, large, and *structured in a way that makes routing useless*.

**5.1 Profiles are near-monotone transformations of one difficulty ordering.** Accuracy by capability
over 238 shared `crosscap240` tasks, eight distinct agents:

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

For **seven of the eight, the strongest capability is code**; for the eighth it is maths. Not one agent
is best at theory of mind. Agents differ in overall strength and in how steeply they fall, not in what
they are *for*. That is main-effect structure with a steepness parameter, and Proposition 1 says such
structure yields no routable headroom.

**5.2 Crossing interaction is real, and measured.** `deepseek32` and `ring26` hold up on theory of mind
(0.800, 0.700) where `grok43` and `gpt5mini` collapse (0.133, 0.233). The likelihood-ratio test of
\(\gamma_{u,c(x)} = 0\) in \(\sigma(\alpha_u + \beta_x + \gamma_{u,c(x)})\) has now been run at both levels
of the same data ([`mas_harness/metrics/interaction.py`](../../mas_harness/metrics/interaction.py), D-038).
The p-value is a parametric bootstrap under the fitted additive model rather than a chi-squared tail,
because one nuisance parameter per task is the incidental-parameter setting; the effect size is the
excess of mean absolute cell departure over the null's own departure, because at these cell sizes
sampling noise alone moves a cell mean by two to four points.

| level | `hard366` | `crosscap240` |
|---|---|---|
| agents (8) | \(p=0.164\), excess \(-0.00\) pp | \(p\le0.005\), excess \(+7.29\) pp |
| organizations (30) | \(p=0.692 / 0.731 / \le0.005\), excess \(-0.35 / -0.07 / +0.26\) pp | \(p\le0.005\) in all three, excess \(+6.71 / +4.21 / +3.78\) pp |

Two consequences. The suite manipulation is validated directly: the homogeneous suite has no detectable
interaction at either level and the cross-capability suite has a great deal, so no negative result in
Section 4 can be dismissed as "the tasks were too alike". And Section 3's finding becomes sharper. On
the three `crosscap240` cells the sharp-null headroom excesses are \(-0.23\), \(-0.05\) and \(-3.24\)
(\(p = 0.605, 0.560, 0.965\)) on outcome tables that carry organization-by-capability interaction at
\(p\le0.005\). **Headroom is not merely inflated by noise; it is insensitive to interaction that is
demonstrably present in the same table.** `hard366`/correlated4 makes the converse point: significant at
\(p\le0.005\) with an excess of \(0.26\) points on 10,980 observations, a p-value that is not an effect size.

**5.3 Aggregation absorbs the exploitable part.** ⚠️ **Superseded by D-040.** At n=3 pools this read
as a 2-of-3 pattern. Over 280 pools whole-pool voting is at or above the oracle-labelled capability
router in 60.0% / 65.7% of pools — a coin flip tilted toward voting — and when the router is given
all thirty organizations, voting leads in only 44.3%. "Aggregation is a substitute for routing" is
**not supportable**; "voting is hard to beat and needs no task representation" is. The paragraph
below is retained as the record of what was believed. This is the substantive claim, and 5.2
constrains how it may be stated. The prediction that aggregation would *destroy* the interaction is refuted: it is
significant over organizations, not only over agents. What aggregation removes is the part worth
routing on. Voting over a heterogeneous pool already realises each member's expertise on the tasks where
that member is strong, without needing to know which tasks those are. Routing and voting are therefore
substitutes, and voting wins because it needs no representation. Formally, majority vote already
benefits from the Condorcet effect under exactly the semi-independence the null of Section 3 assumes,
which is why whole-pool majority vote was the one organizational fact that reproduced (D-029).

**5.4 A statistical corollary, now with a measurement behind it.** A per-task maximum is insensitive to
interaction of this kind because specialisation redistributes coverage rather than expanding it: an
agent that collapses on a capability creates an opportunity there and simultaneously leaves the union of
successes on those same tasks. Section 5.2 turns this from an argument into an observation — the same
three outcome tables carry interaction at \(p\le0.005\) and headroom excesses that are negative or within
noise.

---

## 6. Contribution 4 — a linear cost penalty is the wrong instrument

**6.1 What went wrong.** Sweeping \(\lambda\) in \(\text{accuracy} - \lambda\cdot\text{cost}\) and
comparing the routed policy against the \(\lambda\)-selected global policy gives, over 200 resplits,
best-\(\lambda\) gains of \(+3.36\), \(-0.02\), \(+1.06\), \(+7.02\), \(+3.47\) and \(+7.99\) points, positive in 44
to 94 per cent of resplits. On the same data the budget-matched comparison gives \(-0.48\) to \(-3.94\).
Leak-free, resplit-stable, and an artefact. (Earlier drafts quoted \(+2.6\) to \(+16.6\); that run's
artefact did not survive a rewrite of the script and the figure is retired in favour of these, which
have one — D-039.)

**Lemma 2.** For \(\lambda \ge 0\), \(\arg\max_o\,(v_o - \lambda c_o)\) lies on the upper convex hull of
\(\{(c_o, v_o)\}_{o \in \mathcal{O}}\). Hence the organizations reachable by *any* \(\lambda\) are the hull
vertices \(\mathcal{O}_{\mathrm{hull}} \subseteq \mathcal{O}_{\mathrm{Pareto}} \subseteq \mathcal{O}\).

An organization that is Pareto-efficient but interior to the hull is therefore invisible to the global
policy at every \(\lambda\), while the routed policy chooses per capability from all of \(\mathcal{O}\).
The comparison silently gives the two sides different feasible sets, and the gap is widest exactly
where the Pareto frontier is concave. Holding out data does not help, because the defect is in the
shape of the question.

The invisible set is not a theoretical curiosity here. Counting it directly (D-039): of 30
organizations per cell, 7 to 14 are Pareto-efficient, only 3 to 6 are reachable by any \(\lambda\), and
**3 to 9 are Pareto-efficient yet invisible to the global policy at every \(\lambda\)**.

**6.2 The correct instrument is a budget.** Fix \(b\) in dollars per task; each policy takes the most
accurate organization it can *afford*:

$$
V_{\mathrm{fix}}(b) = \max\{v_o : c_o \le b\}, \qquad V_{\mathrm{route}}(b) = \sum_k w_k \max\{v^{(k)}_o : c^{(k)}_o \le b\},
$$

with \(w_k\) the frequency of capability \(k\). This reaches the full Pareto frontier rather than its hull,
has no free parameter, and is the constraint a deployer actually faces.

**6.3 Result.** Routing loses in all six cells at an unconstrained budget, by 0.48 to 3.15 points,
positive in 2 to 29 per cent of 200 resplits, and is negative at most budgets throughout the curve. At
the tightest budget in every cell, all capabilities receive the same organization. The one substantial
exception, \(+11.53\) points in `crosscap240`/`correlated4` at USD 0.000453 per task, is **priced-by-domain
arbitrage**: \(c^{(k)}_o \le b < c_o\) for some capabilities, because prompts and answers are shorter
there. Real, legitimate, and not delegation.

**6.4 Cost must be reconstructed, not read off.** Episode records show USD 0 for bank replays and Stage A
records show USD 0 for cache hits; either would invert the comparison. Every call is repriced from its
four token buckets against the run's frozen price snapshot. `independent_majority` over \(k\) members is
charged for \(k\); `single_expert` is charged for the one member it consults, because its predictor reads
calibration accuracy by domain and never inspects the current task's answers.

---

## 7. Design: what is manipulated, and why

The suite and the pool are crossed, so that "routing fails" is tested against the two conditions under
which it should most plausibly succeed.

**Pool composition — three levels, run in both directions.**

| pool | intent |
|---|---|
| `strong4` | a dominant agent present: the control in which governance and routing *should* fail |
| `decorrelated4` | members chosen to decorrelate errors at comparable competence: the treatment |
| `correlated4` | members chosen for correlated errors: the opposing control |

**Suite — the capability-diversity manipulation.** `hard366` is three flavours of hard technical
reasoning (GPQA-Diamond, MATH-500 level 5, MMLU-Pro theoremQA/scibench), homogeneous by construction.
`crosscap240` was built specifically to demand four different kinds of thinking (CRUXEval code
execution, AIME competition maths, ExploreToM theory of mind, GPQA-Diamond science). If routing has an
existence condition, this contrast finds it. It did not.

**Splits and resplits.** A frozen calibration/test split per manifest, plus means over 40 to 200
stratified random repartitions, because the manifest split was shown to flatter routing.

**Leak-free constraints, enforced in code.** Task representations come from prompt text only; the
embedding projection, every baseline, the expert predictor and the fixed-best choice are fitted on
calibration tasks only; intervention episodes are excluded from all outcome analyses.

**Nulls, in place of thresholds.** Permutation and parametric nulls for winner reproducibility, and the
additive null of Section 3, replacing the fixed go/no-go thresholds the project began with — which
D-029 showed were dilutable by adding protocols.

---

## 8. The claims, with scope and falsifiers

Rewritten 2026-08-14 against D-040 to D-044. Numbers are in
[`CLAIM_EVIDENCE_MATRIX.md`](CLAIM_EVIDENCE_MATRIX.md); this table carries scope and falsifiers.

| # | claim | scope limit | what would falsify it |
|---|---|---|---|
| C1 | Oracle headroom is not evidence of routable structure | one seed, one answer draw; SWE-bench uses the conservative null | the sweep showing excess in a coherent subset of pools, or the calibrated false-positive rate exceeding nominal |
| C1' | Headroom is *insensitive*, not merely inflated | provenance-based capability labels | headroom excess and interaction agreeing in sign across pools |
| C2 | No learned router beats a frozen best fixed organization | 30–35 organizations, 4-agent pools, single-turn QA | a router gaining ≥1 pp on this grid with a clean shuffled control |
| C2' | Nor with interaction protocols in the choice set, nor under domain, agent or organization holdout, nor for the solo-versus-collaborate decision | grand coalition for the priced protocols | any regime clearing +1 pp with the twin below it |
| C3 | The binding constraint is selection variance, not task representation | conditioning gain measured on two suites | a representation whose conditioning gain exceeds its selection cost |
| C3' | The winner's curse on the *fixed* choice is real but not recoverable | seven rules tried | a rule beating the calibration argmax by ≥1 pp on both suites |
| C4 | A linear cost sweep manufactures routing gains; a budget does not | our price snapshot | routed beating global at matched budget under flattened prices |
| C4' | The tight-budget win is priced-by-domain arbitrage | per-agent mean flattening | the win surviving flat prices |
| C5 | `independent_judge`, named a priori, beats aggregation in six pools of six across two suites | one aggregator, one provider, grand coalition; 3.5–17.1× the cost | **superseded by C7** |
| ~~C6~~ | ~~28% of that advantage is the judge answering, not aggregating~~ | — | **superseded by C7**: the rescues are what *survives* the anchoring, not a gain from it |
| **C7** | **Reading unanimously-wrong peers halves a strong model's accuracy — solo 0.343, judge 0.186 pooled over six pools** | one aggregator; 59 unanimously-wrong tasks | the effect vanishing under a second aggregator model |
| **C8** | **The judge's advantage over voting is largely the aggregator's own competence.** It beats voting alone in 4 pools of 6; judge minus solo clears +2.0 pp in only 3 of 6 | our price snapshot | — |

C1, C1', C3', C4 and C4' are methodological and travel beyond this project. C2, C2', C3, C7 and C8
are empirical and bounded by the grid.

**Novelty, stated here because §8 is where a drafter would start.** Every claim in this table is
already published — see [`../literature/ENSEMBLING_NOVELTY.md`](../literature/ENSEMBLING_NOVELTY.md).
The claims are correct; they are not new. Do not draft from this table without reading that file.

**What the negative does *not* cover, stated plainly.** Every result here is single-turn question
answering with exact-match grading, over 8–10 general-purpose chat LLMs from one provider, choosing
among 30–35 answer-level organizations. It says nothing about routing *reasoning steps* within a
task, routing *agentic workflow steps* with tool use, or routing among model classes that differ by
more than these do. Those are the regimes most of the current routing literature occupies.

## 9. Known gaps, honestly

1. **One seed per cell.** \(\hat q(x,o)\) is a single Bernoulli draw, which maximises the upward bias in
   \(\hat H\) that Section 3.2 describes. It does not threaten C2, C3 or C5, all of which compare
   policies rather than maxima, but the paper should be explicit.
2. **SWE-bench still uses the independent null.** The 134 systems are opaque agent frameworks with no
   member decomposition, so the agent-level simulation of §3.4 cannot be applied to them. That
   external validation therefore remains the conservative version, and should be reported as such.
3. ~~The interaction likelihood-ratio test (§5.2) has not been run.~~ **Run, D-038.** It delivered the
   cleanest statement of "interaction is real, headroom does not detect it", and refuted the
   agent-versus-organization contrast §5.3 had predicted.
4. **Two protocols in every cross-suite comparison.** The five priced protocols ran on `hard366` only,
   so the protocol dimension of \(\mathcal{O}\) is thin exactly where capability diversity is richest.
5. **Eight agents, one provider.** All models are served through OpenRouter, and the profile table that
   carries C4 rests on eight of them.
6. **Capability labels are dataset provenance.** \(c(x)\) is which benchmark a task came from, which is a
   proxy for capability, and a generous one for the capability router.
