<!-- doc-meta
type:          living
lifecycle:     update-in-place
last-verified: 2026-08-11
evidence-base: via Docs/paper/CLAIM_EVIDENCE_MATRIX.md — do not quote numbers directly
-->

# Paper Backbone

Built with `.cursor/research-paper-writing-skills` Mode 2. Evidence inventory is
[`Docs/paper/FRAMEWORK.md`](FRAMEWORK.md) (formal framework and design), [`DECISIONS.md`](../../DECISIONS.md)
(D-001 to D-037) and [`EXPERIMENT_LOG.md`](../../EXPERIMENT_LOG.md) (what was run). Claim-level evidence
with exact locations is [`Docs/paper/CLAIM_EVIDENCE_MATRIX.md`](CLAIM_EVIDENCE_MATRIX.md).

**Status: awaiting author sign-off on the one-sentence paper, the three claims, the contribution list
and the section order.** Per the skill's Gate C, no prose drafting until those four are approved.

---

## One-sentence paper

> We study whether selecting a *different* agent organization per task beats committing to one in
> heterogeneous LLM multi-agent systems, and show that the coverage-style headroom used to motivate
> such selection is not evidence that anything is there to select, using a 569-task by 30-organization
> counterfactual grid with nulls that preserve member sharing plus an external 134-system matrix,
> which matters because the field's motivating statistic and its cost-adjusted comparison both
> manufacture opportunities that do not survive a matched control.

### Archetype

**Primary: empirical phenomenon / behavioural evaluation** (`paper-archetypes.md` §2) — the
contribution is a finding plus the experimental design that isolates it. **Secondary: theory**
(§5) for Proposition 1 and Lemma 2, which are what turn the empirical negative into an explanation
rather than a null result. Do **not** structure this as a method paper; there is no proposed router,
and pretending otherwise would invert the argument.

### What should the reader remember one week later?

1. A per-task maximum over many organizations is large *by construction* and blind to the thing it is
   supposed to measure. Under an additive model its population value is exactly zero, and on tables
   that provably do contain interaction it still shows no excess over a matched null.
2. Per-task selection rarely beat one well-chosen organization — not with a learned router, and not
   even when handed ground-truth capability labels, where it lost to plain majority voting in two pools
   of three. Running the whole pool and voting is the stronger and simpler policy, and needs no task
   representation at all.
3. The reason is not that specialisation is absent — it is measurably present. It is that seven of
   eight agents peak on the same capability, and aggregation already collects the crossing that does
   exist, without needing to know which tasks are which.

---

## Central claims

Three, per Gate B. The five working claims in `FRAMEWORK.md` §8 compress as: C1+C5-methodological to
Claim 1, C2+C3+C5-empirical to Claim 2, C4 to Claim 3.

### Claim 1 — Two standard measurements manufacture routing opportunities that do not exist

- **Exact wording:** *Oracle (coverage-minus-best) headroom and cost-penalty-swept frontier
  comparisons both report large routing opportunities on data containing none. Headroom's population
  value is exactly zero under an additive outcome model, so a positive estimate is uninformative until
  compared against a matched null; and sweeping a linear cost penalty restricts a fixed baseline to the
  convex hull of the available organizations while the routed policy draws from all of them. Headroom
  is moreover **insensitive rather than merely inflated**: on the three cross-capability cells it shows
  no excess over the null while a likelihood-ratio test finds organization-by-capability interaction in
  the same outcome tables at \(p\le0.005\).*
- **Type/strength:** Theory (two formal results, each with an empirical demonstration) plus
  **existence** of the artefact in our own analysis and in a public matrix, plus a **comparative**
  demonstration that the two instruments disagree on identical data.
- **Scope:** Proposition 1 assumes a strictly increasing link and no interaction term. Lemma 2 is a
  property of linear scalarisation and holds generally. The empirical demonstrations are on our six
  pool-by-suite cells and on SWE-bench Verified.
- **Why it matters:** These are the two quantities the routing literature uses to argue that
  organization selection is worth building. FlexRouter's coverage objective
  \(P(\exists a \in S : Y_a = 1)\) is the same functional as our headroom
  ([literature review §9.2-9.3](../literature/LITERATURE_REVIEW.md)). If the motivating number
  is not evidence, the field's framing needs repair independently of whether any particular router works.

### Claim 2 — Per-task organization selection does not beat committing to one, at three levels of information

- **Exact wording:** *On 569 tasks across three agent pools and 30 organizations, choosing an
  organization per task rarely beat choosing one for the whole suite: a learned outcome model gained
  between \(-1.78\) and \(+0.33\) points and was ahead in at most 47% of resplits; a router given
  ground-truth capability labels beat the best single agent in two pools of three, but beat plain
  majority voting over the same members in only one; and in a budget-matched comparison the routed
  policy lost at unconstrained budgets in all six pool-by-suite cells.*
- **Type/strength:** **Comparative** and **systematic** — across two suites, three pools, 40-200
  resplits, and a sevenfold sweep of calibration size. Not causal, and not general beyond the stated
  family. Note the deliberate hedge "rarely": two of the three ladder levels have one dissenting cell
  each (see counter-evidence below), and the claim must not be worded as a clean sweep.
- **Scope:** 30 organizations built from 4-agent pools and the two protocols that ran on every task;
  eight distinct models, one provider; one seed per cell; capability labels are dataset provenance.
- **Why it matters:** The capability router is an **upper bound on any router whose representation is a
  function of the capability partition**, so this is not "our model underperformed". The comparison
  against whole-pool voting is also absent from the baseline ladder the literature review compiles
  (§26), which lists globally-best-agent, other routers, complementarity selectors and the oracle.

### Claim 3 — The mechanism is a shared difficulty ordering, and aggregation absorbs what crossing exists

- **Exact wording:** *These agents differ in overall strength and in how steeply they degrade more than
  in what they are suited to: for seven of eight, the strongest of four capabilities is the same one,
  and none is strongest at theory of mind, despite per-capability spreads up to 0.833. The crossing
  interaction that remains is statistically unambiguous (\(p\le0.005\)) yet does not make selection pay,
  because majority voting over a heterogeneous pool already realises each member's strength without
  knowing which tasks are which.*
- **Type/strength:** **Mechanism**, supported by a measured interaction test and a falsification test:
  a pool selected on calibration data specifically to maximise disjointness still shows no excess
  headroom (\(-2.16\), \(p=0.883\)).
- **Scope:** Eight agents, four provenance-based capability labels, one suite. **Note the correction:**
  the natural stronger claim — that aggregating agents into coalitions destroys the interaction — is
  refuted by our own test, which finds it significant at the organization level too. What aggregation
  removes is the *exploitable* part, which is a weaker and more careful statement.
- **Why it matters:** It converts the negative into a boundary condition with a testable precondition,
  and it explains why headroom cannot see the interaction that does exist: specialisation redistributes
  coverage rather than expanding it, since an agent that collapses on a capability leaves the union of
  successes on the same tasks where it creates an opening.

---

## Contributions

| Contribution | Type | New value |
|---|---|---|
| Proposition 1: population oracle headroom is exactly zero under an additive model with monotone link, so the oracle router is a constant map | Theory | Shows the field's motivating statistic is uninformative *by construction*, not merely noisy |
| Lemma 2: a linear cost sweep reaches only the upper convex hull, so routed-versus-swept-baseline comparisons are unmatched | Theory | Identifies an artefact that inflated our own analysis by +2.6 to +16.6 points while passing held-out selection and 200 resplits |
| A no-interaction null that preserves member sharing, by simulating agents and running the real protocols | Analysis / method-for-measurement | Replaces an organization-independent null that under-rejects; validated at replay agreement 1.0000 and shown to fire on planted specialists |
| The paired diagnosis: a bootstrap interaction test alongside the headroom null, on identical tables | Analysis | Separates "no structure" from "the instrument cannot see the structure", which no headroom figure can do alone |
| The layered negative with an oracle-label upper bound | Empirical finding | Rules out an entire family of routers rather than one instance |
| The mechanism: profiles as monotone transformations of one difficulty ordering; aggregation as a substitute for routing | Analysis | Explains the negative and yields the precondition under which routing could pay |
| The two-stage counterfactual harness: 4,392 banked answers on `hard366` generating 57,489 episodes across three pools, with \$85.13 of API spend for the whole project including the second suite, and exact `do(.)` interventions | Systems / resource | Makes dense organization-level counterfactuals affordable; the literature review notes such supervision is richer than standard routing logs (§13) |

**[AUTHOR DECISION]** Six is too many to foreground. Recommend three headline contributions —
Proposition 1 + Lemma 2 as one "the measurements are broken" item, the layered negative, and the
mechanism — with the null and the harness as supporting.

---

## Non-claims and out-of-scope items

State these explicitly; each is a claim a reader may wrongly infer.

- **Not** that multi-agent systems or aggregation are useless. Whole-pool majority voting is the
  *winner* in this study, and the Condorcet effect it exploits is real under exactly the
  semi-independence our null assumes.
- **Not** that no agent-by-task interaction exists. It does (Claim 3). The statement is that the
  interaction present is not of a kind a per-task maximum can detect, and not large enough to make
  selection pay.
- **Not** that routing can never work. Claim 2 is bounded by our organization family, pools, and
  capability labels; Claim 3 states the precondition it would need.
- **Not** a comparison against published routers. We did not reimplement MasRouter, RouterHGC,
  FlexRouter or KABB, and must not imply we outperformed them.
- **Not** a cost-optimality result. Routing does win at the tightest budgets in the cross-capability
  suite; we read that as priced-by-domain arbitrage and label it as an interpretation, not a
  demonstration of delegation.
- **Out of scope:** the governance and coalition-value directions (D-021 to D-028), the
  distributed-information condition, and all five priced interaction protocols, which ran on one suite
  only.

---

## Figure and table plan

Minimum set to establish three claims. Ordered by the argument, not by chronology.

| Item | Question answered | Claim | Reader should inspect | Expected pattern if true | Counter-pattern | Scope / caveat |
|---|---|---|---|---|---|---|
| **Figure 1** (2 panels) | What is an organization, and is the headroom real? | 1 | Left: the task-by-organization grid and the two-stage split. Right: observed headroom against the sharp null, six cells + SWE-bench | Observed bar sits inside the null's distribution in every cell | Observed clearly above null in several cells | One seed; SWE-bench uses the conservative null |
| **Figure 2** | Do agents differ in *what* they are for, or only in *how much*? | 3 | One line per agent across four capabilities | Mostly parallel lines peaking on the same capability, with a visible minority crossing | Lines crossing everywhere with distinct peaks | Eight agents, one suite, provenance-based labels. Source now stored: `accuracy_by_capability` |
| **Figure 5** (the pivot) | Do the two instruments disagree on the same data? | 1 | Per cell, interaction excess-departure beside sharp-null headroom excess | `crosscap240`: interaction bars large and significant, headroom bars at or below zero | Both agreeing in sign | Provenance-based labels; bootstrap null |
| **Figure 3** | Does any amount of information make selection pay? | 2 | Ladder per pool: best single agent, learned router, capability router with true labels, whole-pool vote, oracle | Vote at or above every implementable policy; oracle far above all | Capability router above the vote — **this occurs in `correlated4` (+2.5)** and must be shown, not omitted | Two protocols; capability labels generous |
| **Figure 4** | Does selection pay under a budget? | 2 | Accuracy against \$/task, routed versus global, per cell | Routed at or below global at the right of each curve | Routed above global at the left — **this occurs in all three `crosscap240` cells**, and the figure must make the tight-budget region visible rather than cropping it | Our price snapshot; left-edge gains are domain-price arbitrage, and the text must say so |
| **Table 1** | What was manipulated? | — | Suites (homogeneous vs cross-capability) crossed with pools (dominant / decorrelated / correlated) | — | — | Design table, no result |
| **Table 2** | How much headroom survives each null? | 1 | Observed, independent null, sharp null, excess, \(p\), six cells | Excess near zero; one cell at \(p=0.045\) against a 0.0083 threshold | Multiple cells surviving correction | — |
| **Table 3** | Is the artefact in the cost comparison real, and why? | 1 | λ-swept gain (−0.02 to +7.99) beside budget-matched gain (−0.48 to −3.94), plus the hull counts | Sign flips between formulations; 3–9 Pareto organizations per cell unreachable by any λ | Both agree, or the invisible set is empty | Regenerated; the two historical ranges are retired as unreproducible (D-039) |
| **Table 4** | Does the null have power? | 1 | Planted four-specialist structure: excess and \(p\) | Detected, \(p<0.05\), excess > 5 pts | Not detected | Synthetic, in the test suite |

**[AUTHOR DECISION]** Figure 1's right panel and Table 2 overlap. Either make Figure 1 purely the
object plus a single headline cell, or drop Table 2 to the appendix.

---

## Section outline

1. **Introduction** — the problem, the two broken measurements, the layered negative, the mechanism.
2. **Related work** — routers that select subsets and configurations; coverage objectives; explicitly
   what is *not* new here, following the literature review's own list of already-covered claims (§21).
3. **Setup** — organizations, the outcome grid, the two-stage factorization, the baseline ladder with
   the capability router as an upper bound.
4. **Why the usual measurements mislead** — Proposition 1, Lemma 2, and the member-sharing null with
   its validation and power check.
5. **Study design** — suites, pools, protocols, splits and resplits, leak-free constraints, cost
   reconstruction.
6. **Results** — R1 headroom against both nulls and on SWE-bench; R2 the three-level selection
   negative; R3 the budget comparison and the λ artefact; R4 the mechanism and the disjoint-pool
   falsification.
7. **Discussion** — routing and aggregation as substitutes; what a pool would have to look like for
   selection to pay.
8. **Limitations** — one seed; SWE-bench's conservative null; two protocols; eight models on one
   provider; provenance-based capability labels; the unrun interaction test.
9. **Conclusion**.

### Space allocation

Sections 4 and 6 take roughly half the paper: they carry all three claims. Section 2 must be compact
and non-adversarial. Section 5 needs only enough detail to trust Section 6, with the harness in an
appendix.

---

## Paragraph outline

One bullet per planned paragraph; each bullet is that paragraph's message.

**Introduction**
- Heterogeneous LLM agents differ in cost and competence, so a natural proposal is to route each task
  to the organization best suited to it, and a growing family of systems does exactly that.
- The motivating evidence is almost always a gap between the best fixed choice and a per-task maximum,
  which is presented as an unclaimed opportunity.
- That gap is not evidence: under an additive outcome model it is exactly zero in the population, so
  every reported positive value is interaction *or estimation noise*.
  **[LITERATURE CHECK NEEDED]** the stronger sentence — that no published headroom figure is tested
  against a null — is not yet verified. What *is* supported is that the review's own eight essential
  baseline families end with "Oracle: best observed organization — how much headroom remains?"
  ([literature review §26](../literature/LITERATURE_REVIEW.md)), i.e. headroom is treated as a
  quantity to be measured rather than a hypothesis to be tested. Use that unless the stronger claim is
  checked.
- We build a counterfactual grid that makes the test possible: 569 tasks, 30 organizations, three
  pools contrasted deliberately, with organization outcomes replayable at zero marginal cost.
- Result one: observed headroom does not exceed a null that removes agent-by-task interaction while
  preserving member sharing, difficulty, strength, abstention and distractor concentration — on a test
  we show fires on planted specialists.
- Result two: selection does not reliably pay at any level of information, including a router handed
  ground-truth capability labels, which upper-bounds an entire family. Whole-pool voting is at least as
  good in two pools of three and needs no task representation at all.
- Result three, and the explanation: these agents share one difficulty ordering, seven of eight peaking
  on the same capability, and voting already collects the narrow crossing that exists.
- A second measurement warning falls out: a linear cost sweep flattered routing by up to 16.6 points in
  our own analysis, and survived held-out selection, because such a sweep restricts the fixed baseline
  to a convex hull.
- Contributions and what we do *not* claim.

**Setup**
- An organization is a coalition crossed with a protocol; the object of study is the outcome grid over
  tasks, organizations and seeds.
- The two-stage factorization: aggregation protocols are deterministic functions of banked independent
  answers, which makes 57,489 episodes free and interventions exact.
- The baseline ladder, and why the capability router is an upper bound rather than one more model.

**Why the usual measurements mislead**
- Proposition 1 and its proof: monotone link plus additivity makes the oracle router constant.
- Therefore the empirical estimator is positive almost surely, with bias growing in the number of
  organizations and shrinking in seeds; it must be compared to its own null.
- A null drawing organizations independently is the wrong one, because organizations share members and
  real maxima are correspondingly smaller.
- Our null instead simulates agents additively and runs the real protocols, preserving what must be
  preserved and destroying only the agent-task association.
- Two validations: exact replay of recorded episodes, and detection of planted specialists.
- Lemma 2 and its consequence for cost-adjusted comparisons.

**Study design**
- Suites: one homogeneous, one built to demand four different kinds of thinking, so the existence
  condition for routing is given its best chance.
- Pools: dominant-agent, decorrelated and correlated, so pool composition is a manipulation run in both
  directions rather than a convenience sample.
- Splits, resplits and leak-free constraints, including why the manifest split alone is not reported.
- Cost reconstruction from token buckets, and why recorded costs would have inverted the comparison.

**Results** — one subsection per R1-R4, each: question, why this design answers it, exact numbers with
pointer to figure or table, interpretation, and the boundary or unresolved alternative.

**Discussion**
- Routing and aggregation are substitutes, and aggregation needs no task representation.
- What a pool would have to look like for selection to pay, stated as a measurable precondition.
- Why a negative here is informative rather than merely absent: the upper-bound design.

---

## Working abstract

Placeholders marked. To be rewritten after Section 6 is stable.

> Heterogeneous LLM agents differ in cost and competence, motivating systems that route each task to a
> suitable agent subset and coordination protocol. The evidence offered for this is typically a gap
> between the best fixed choice and a per-task maximum over candidates. We show this gap is not
> evidence of routable structure: under an additive outcome model with monotone link, the per-task
> optimum is the same organization for every task, so the population gap is exactly zero and any
> observed value reflects interaction or estimation noise. Interpreting it therefore requires a null
> [LITERATURE CHECK NEEDED: whether any published headroom figure is tested against one].
> On a counterfactual grid of 569 tasks by 30 organizations (coalition times
> protocol) across three deliberately contrasted agent pools, observed headroom does not exceed a null
> that removes agent-by-task interaction while preserving member sharing, task difficulty, agent
> strength, abstention and per-task distractor concentration; the same holds on a public matrix of 134
> agent systems. This is not because the data lack structure: a likelihood-ratio test finds
> organization-by-capability interaction in the same outcome tables at [p≤0.005], so the statistic is
> insensitive rather than merely inflated. Consistently, per-task selection rarely pays: a learned
> outcome model gains at most
> [+0.33] points and is ahead in at most 47% of resplits, a router given ground-truth capability labels
> beats the best single agent in two pools of three but beats plain majority voting over the same
> members in only one, and in a budget-matched comparison routing loses at unconstrained budgets in all
> six pool-by-suite cells. The reason is that these agents' capability profiles are near-monotone
> transformations of a single difficulty ordering — seven of eight peak on the same capability — and
> aggregation already collects the exploitable part of the crossing that exists. We also show that
> comparing a routed policy against a cost-penalty-swept baseline flatters routing by up to [8] points,
> because such a sweep reaches only the convex hull of the candidate set, leaving [3 to 9] of 30
> Pareto-efficient organizations unreachable at any penalty.

### Title options — [AUTHOR DECISION]

1. *Oracle Headroom Is Not a Routing Opportunity in Multi-Agent LLM Systems*
2. *Nothing to Route To: Per-Task Organization Selection Does Not Beat Committing to One*
3. *Aggregation Absorbs Specialisation: Why Routing Between LLM Agent Organizations Does Not Pay*
4. *Two Measurements That Manufacture Routing Opportunities*

Option 1 names the central object and is the most predictable from the title, which is what
`section-guides.md` asks for. Option 3 leads with the mechanism and would suit a venue that
discounts negative results.

---

## Open gates and blockers

- **Gate B is now met for all three claims.** The interaction test was run (D-038), which upgraded
  Claim 3's "interaction is real" from descriptive geometry to a measured effect and simultaneously
  forced a correction: aggregation does not destroy the interaction, it absorbs the exploitable part.
- **Claims, contributions and section order signed off** by the author on 2026-08-10. Titles remain
  open.
- **Known counter-evidence to surface, not bury.** Three dissenting results, one per ladder level.
  Claim 2's "rarely" is calibrated to these, and each must appear in the results text.
  1. **Semantic k-NN** gains \(+1.40\) points in 77% of resplits on `hard366`/`strong4` and \(+1.01\)
     in 70% on `crosscap240`/`strong4`; near zero or negative in the other four cells. A crude
     nearest-neighbour rule does better than the learned model, which is itself worth a sentence.
  2. **The capability router beats voting in `correlated4`** (0.881 against 0.855, \(+2.5\) points).
     The pool built from *correlated* agents is the one where routing helps, which is the opposite of
     the intuition and currently unexplained.
  3. **Routing wins at the tightest budgets** in all three `crosscap240` cells (\(+4.05\), \(+2.68\),
     \(+13.91\), ahead in 81-100% of resplits). Our reading is domain-price arbitrage rather than
     delegation; that reading is an interpretation and must be labelled as one.
- **Terminology ledger not yet built.** "Organization", "coalition", "protocol", "pool", "headroom",
  "capability" and "configuration" are used inconsistently across `DECISIONS.md`; fix before drafting.
- **Both provenance defects are closed.** P1: the λ figures were regenerated, reproduce *neither*
  historical record, and both records are retired in favour of the new artefact (D-039). P2: the
  capability table is persisted. Neither closure changed a conclusion, but P1 would have put an
  unreproducible number in a table.
- **The results section needs a new subsection.** R1 now has two halves — headroom does not exceed the
  null, *and* the interaction test on the same tables does. Ordering them in that sequence is what makes
  Claim 1 land; reversing it reads as a contradiction.
