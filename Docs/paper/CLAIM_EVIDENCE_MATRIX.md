<!-- doc-meta
type:          living
lifecycle:     update-in-place — AUTHORITATIVE numbers; every row names its artefact key
last-verified: 2026-08-14
evidence-base: data/runs/*.json — see per-row Location column
-->

# Claim–Evidence Matrix

Companion to [`Docs/paper/PAPER_BACKBONE.md`](PAPER_BACKBONE.md). Every figure below was read from
the stored run artefacts in `data/runs/`, not transcribed from prose.

**2026-08-14 revision.** This file previously stopped at D-039 and described a six-cell study. It now
covers **D-040 through D-045**: 280 pools, four research questions, a purchased second suite, and the
control that resolved the judge result against its own headline. Three claims were **weakened**, two
counter-evidence rows **retired**, C3c is no longer supportable in its old wording, and C4h is
**refuted**.

⚠️ **Every claim here is sound and none is novel** — see the *Novelty status* section below before
citing any row.

Status vocabulary: supported / partially supported / weakened / unsupported / contradicted / open.

---

## Group 1 — the measurements mislead

| ID | Claim | Strength | Evidence | Location | Counter-evidence | Status |
|---|---|---|---|---|---|---|
| **C1a** | Under an additive model with monotone link, population oracle headroom is exactly zero | Guarantee | Proposition 1 with proof | [`FRAMEWORK.md` §3.1](FRAMEWORK.md) | None; it is a proof | supported |
| **C1b** | Observed headroom does not exceed a null removing agent-by-task interaction while preserving member sharing | Comparative | **280 pools, both suites.** Median excess −1.63 pp (p=0.945) on `crosscap240`, +0.14 (p=0.393) on `hard366`; **0 of 70** and 5 of 210 pools at p≤0.05 against 2.5 and 8.4 expected | `pool_sweep_*.json` → `family_wise_null`; D-040 | The six named cells individually gave +2.20 (p=0.045) at best; the sweep supersedes them | **strengthened** |
| **C1c** | The null is not vacuous, and its error rate is measured rather than assumed | Existence | Planted specialists detected at p<0.05; replay agreement 1.0000; **double-bootstrap false-positive rate 0.016 / 0.000 against a nominal 0.050** | `tests/test_pool_sweep.py`; `pool_sweep_*.json` → `calibration`; D-040 | The test *under*-rejects, so a null result is conservative | **strengthened** |
| **C1d** | The result holds on 134 public agent systems | Systematic | Excess −1.88 to −2.65, p = 0.940–0.970 | `headroom_null_swebench.json` | Uses the independent null; conservative direction | partially supported |
| **C1e** | A linear cost sweep reaches only the convex hull | Guarantee + existence | Lemma 2; **median 8 Pareto-efficient organizations per cell unreachable by any λ, range 1–16, across 280 pools** | `cost_frontier.json`, `pool_sweep_*.json`; D-039, D-040 | The λ result was our own analysis, not a published one | supported |
| **C1f** | Headroom is *insensitive*, not merely inflated: it misses interaction present in the same table | Comparative | **Organization-by-capability interaction at p≤0.05 in 100% of the 70 `crosscap240` pools**, median excess departure +4.41 pp, while headroom excess in those same pools is at or below the null | `pool_sweep_crosscap240.json` → `interaction`; D-038, D-040 | `hard366`/correlated4 is significant with a 0.26 pp effect — significance without magnitude | supported |

## Group 2 — per-task selection does not pay

| ID | Claim | Strength | Evidence | Location | Counter-evidence | Status |
|---|---|---|---|---|---|---|
| **C2a** | A leak-free learned outcome model does not beat the best fixed organization | Comparative | **Mean gain −0.01 pp over 70 pools and −0.46 over 210**, ahead in 43.2% / 30.2% of resplits, while the shuffled twin loses 2.42 pp and is beaten in 91% of pools | `pool_sweep_*.json` → `routing`; D-033, D-040 | ~~Semantic k-NN gains +1.40~~ **RETIRED**: at n=70 it is −0.06 pp, positive in 48.6% of pools | **strengthened** |
| **C2b** | The absence of gain is not a data-volume problem | Systematic | Flat over a sevenfold calibration sweep, 57→398 tasks | `routing_pooled.json`; D-033 | A sevenfold range may be far from asymptote | supported |
| **C2c** | A router given ground-truth capability labels does not beat whole-pool voting | Comparative | Voting is at or above it in **60.0%** of 70 `crosscap240` pools and 65.7% of 210 `hard366` pools; mean margin +0.29 / +0.27 pp, 5th–95th −5.1 to +7.5 | `pool_sweep_*.json` → `ladder`; D-040 | ~~`correlated4` inverts~~ **RETIRED**: it sits at the 55.7th percentile of 70. But give the router all 30 organizations and voting leads in only **44.3%** | **weakened** |
| **C2d** | Under a budget-matched comparison routing loses | Comparative | Unconstrained: positive in 15.7% of `crosscap240` and **0.0%** of 210 `hard366` pools | `pool_sweep_*.json` → `budget`; D-036, D-040 | Tight-budget wins **were** the counter-evidence; now explained — see C2e | supported |
| **C2e** | The tight-budget routing win is priced-by-domain arbitrage, not capability matching | Comparative, **causal manipulation** | Flattening the per-agent price across tasks **inverts** the win: +5.34 → **−5.78** pp on `crosscap240` (93% → 0% of pools) and +0.71 → −2.80 on `hard366` | `positive_selection.json` → `e2`; D-042 | None; this closes the last open interpretation | **new, supported** |
| **C2f** | Routing does not pay even when interaction protocols are in the choice set | Comparative | 35 organizations vs the identical 30 on the same tasks and splits: `q_θ` −1.05 / −0.64 / −0.67 pp, ahead in 25–27% of resplits; the protocol axis changes the gain by −0.41 pp | `research_questions.json` → `hard366_priced`; D-041 | None | **new, supported** |
| **C2g** | Delegation generalizes no better than it interpolates | Systematic | 70 pools: −0.29 IID, −0.18 domain holdout, **+0.81 agent holdout**, −0.22 organization holdout | `research_questions.json` → `rq4`; D-041 | Agent holdout looks positive; its **conditioning gain is −0.10 pp**, so the effect is a larger feasible set, not task-conditioning | **new, supported** |
| **C2h** | Choosing *whether* to collaborate is not learnable either | Comparative | −0.40 pp against the better of always-solo / always-collaborate, ahead in 18% of resplits, shuffled control −1.29 | `research_questions.json` → `rq5`; D-041 | A perfect oracle over the pair is worth only +2.29 pp, so little is available even in principle | **new, supported** |

## Group 3 — the mechanism, and what it is not

| ID | Claim | Strength | Evidence | Location | Counter-evidence | Status |
|---|---|---|---|---|---|---|
| **C3a** | Agents differ in overall strength and degradation rate rather than in what they suit | Association | 7 of 8 peak on code reasoning; none on theory of mind | `headroom_null_specialists.json` | 4 capabilities is coarse | supported |
| **C3b** | Even a pool selected for disjointness shows no excess headroom | Existence | `disjoint4` excess −2.16, p=0.883 | `headroom_null_specialists.json` | Drawn from 8 models, one provider | supported |
| **C3c** | ~~Aggregation is a substitute for routing~~ | ~~Mechanism~~ | At n=3 it looked like 2-of-3. **At n=280 it is a coin flip tilted toward voting** (60.0% / 65.7%), and with all 30 organizations available the router leads | `pool_sweep_*.json`; D-040 | — | **NOT SUPPORTABLE in its old wording.** The defensible version is "voting is hard to beat", not "aggregation substitutes for routing" |
| **C3d** | The binding constraint is selection variance, not task representation | Mechanism | Representation earns +2.40 pp (router beats its shuffled twin in 91% of pools); per-task choosing costs −2.42; net −0.01. **Conditioning gain is +0.07 pp** | `pool_sweep_crosscap240.json`; D-040 | The three quantities being equal may be coincidence at n=1 suite; on `hard366` they are +0.77 / −1.24 / −0.46 | **new, supported** |
| **C3e** | The winner's curse on the fixed choice is real but **not recoverable** | Comparative | Seven selection rules over 280 pools; nothing beats the calibration argmax. Ceiling `oracle_fixed` is only +1.61 / +1.18 pp | `positive_selection.json` → `e1`; D-042 | `cross_pool` looked like +1.26/+2.09 at 4–6 pools — an argmax over a small sample, our own false positive | **new, supported** |
| **C3f** | Classical shrinkage cannot correct that winner's curse | Guarantee | Equal *n* per organization makes any pull toward a scalar monotone in raw accuracy, so the argmax never moves | [`tests/test_selection.py`](../../tests/test_selection.py); D-042 | None; it is arithmetic | **new, supported** |

## Group 4 — the judge, resolved

| ID | Claim | Strength | Evidence | Location | Status |
|---|---|---|---|---|---|
| **C4a** | `independent_judge`, named a priori, beats the calibration-chosen best aggregation rule | Comparative | Six pools of six, two suites, both D-028 scorings. +4.65 / +7.42 / +3.38 pp on `crosscap240`, +1.42 / +6.09 / +1.33 on `hard366` | `judge_replication.json`; D-043 | supported, but see C4h |
| **C4b** | Picking the *best* protocol per pool is noise | Systematic | Split-half reproducibility 0.00–0.17 on `hard366`, 0.10 / 0.87 / 0.00 on `crosscap240`, mean 0.32 against a 0.5 floor | `judge_replication.json`; D-041, D-043 | supported |
| **C4c** | Over a full suite the judge beats voting by +3.8 / +8.0 / +4.6 pp, at 3.5–17.1× the cost | Comparative | All 239 / 238 / 240 tasks after pricing the 245 D-020 skipped | `judge_on_easy_tasks.json`; D-043, D-044 | supported |
| **C4d** | The judge answers as well as aggregates | Mechanism | It solves 18.6% of tasks where every member was wrong (11 of 59); 28% of its advantage over voting | `judge_on_easy_tasks.json`; D-044 | supported, **and superseded by C4f** |
| **C4e** | A judge does not damage a correct consensus | Existence | 2 overrides of 230 unanimous-correct tasks (0.991) | `judge_on_easy_tasks.json`; D-044 | supported |
| **C4f** | **Reading unanimously-wrong peer answers halves a strong model's accuracy** | **Mechanism, with a single-model control** | Pooled over six pools: solo **0.343**, judge **0.186**; 0.591 vs 0.273 in the worst cell. D-044's 18.6% is what *survives* the anchoring, not a gain from it | `aggregator_solo.json`; D-045 | **supported** |
| **C4g** | Aggregation helps where members split (+5.6 pp) and slightly where unanimously correct (+1.9 pp) | Comparative | Judge beats solo on split tasks in 6 pools of 6, +1.66 to +6.98 pp; solo scores 0.981 on unanimous-correct against voting's 1.000 | `aggregator_solo.json`; D-045 | supported |
| **C4h** | ~~The judge's advantage is aggregation~~ | — | The aggregator **alone** beats whole-pool voting in 4 pools of 6 and beats the best member by +4.3 to +7.1 pp on `crosscap240`. Judge minus solo clears the pre-registered +2.0 pp in only **3 of 6** | `aggregator_solo.json`; D-045 | **REFUTED. Use the strong model alone** |
| **C4i** | Member disagreement is a bad escalation signal | Comparative | A disagreement cascade saves 22 / 28 / 38% of cost and loses 1.26 / 2.10 / 0.42 pp | `judge_on_easy_tasks.json`; D-044 | supported |

## Group 5 — reproducibility

| ID | Claim | Strength | Evidence | Location | Status |
|---|---|---|---|---|---|
| **C5a** | Re-running the same seed is a different draw, large enough to invert a cell | Existence | 49 of 959 repeated `crosscap240` agent-tasks disagree on correctness, 121 on answer text, at temperature 0. `correlated4` vote-minus-router moves −2.50 → +0.63 | D-040 §item 5 | supported |
| **C5b** | Two of six pre-registered verdicts flip on the alternative draw | Systematic | P1, P5, P6 hold; **P2 AMBIGUOUS→REFUTED, P3 REFUTED→AMBIGUOUS** | `pool_sweep_crosscap240_altdraw.json`; D-042 | supported |

---

## Claim-strength audit

| Tempting | Problem | Defensible |
|---|---|---|
| "Aggregation is a substitute for routing" | C3c: a coin flip at n=280, and the router leads with all 30 organizations | "Whole-pool voting is hard to beat and needs no task representation" |
| "A coordination protocol beats a voting rule" | C4d: 28% of the effect is the judge solving what no member solved | "A judge beats a vote — and at least 28% of that is independent answering, not aggregation" |
| "Routing never works" | C2e: it wins at tight budgets, by arbitrage; and the negative is scoped to single-turn QA over 8–10 general-purpose LLMs | "Per-task selection did not pay in this family; the tight-budget win is a price effect" |
| "We found a better selection rule" | C3e: nothing beats the calibration argmax over 280 pools | "The winner's curse is real and not recoverable by any rule we tried" |
| "Escalate on disagreement" | C4f: it loses accuracy for its saving | "Disagreement does not identify where a judge adds value" |
| "The judge is worth it" | C4c: 3.5–17.1× the cost; C4g unrun | Nothing, until C4g runs |

## Novelty status — read this before citing any row

Every claim above is **internally sound and externally unoriginal**. Mapped in
[`../literature/ENSEMBLING_NOVELTY.md`](../literature/ENSEMBLING_NOVELTY.md):

| group | held by |
|---|---|
| C1, C1', C5a | *How Much of the Routing Gap Is Real?* (arXiv 2607.03436); *RouteGuard* (arXiv 2608.07583) |
| C2 family | RouteGuard proves best achievable routing gain equals gate informativeness, with a pre-deployment certificate on 11 models × 36,497 prompts |
| C4h | *Rethinking Mixture-of-Agents* (arXiv 2502.00674); *The Cost of Consensus* (arXiv 2605.00914) |
| C4f, C4g | *Easier to Mislead Than to Correct* (arXiv 2606.01637) — our setting, our control, 4× our scale |

**No paper is currently supportable from these rows.** They remain a correct and well-evidenced
record of what this substrate shows.

## Remaining evidence gaps, for completeness

1. **A second seed**, and the alternative-draw rerun for D-041 through D-045. D-042 already shows two
   of six pre-registered verdicts flip on an equally valid draw.
2. **One aggregator, one provider.** Every judge figure uses `claude-sonnet-5` on OpenRouter, so C4f
   is a claim about that model rather than about LLMs.
3. **Grand coalition only** for every priced protocol.

None of these blocks a claim, because no claim is being made.
