<!-- doc-meta
type:          frozen
lifecycle:     FROZEN — never edit after writing; results go to EXPERIMENT_LOG.md + DECISIONS.md
last-verified: 2026-08-11
evidence-base: not yet run
-->

# Step 1 pre-registration: from 6 cells to 70 pools

Written **before** the sweep is run, in the style of D-026. Every prediction below has a branch
for the outcome that would refute it, and a stated consequence. The point is that no outcome of
this sweep is uninformative — see §6.

Status: **not yet run.** Predictions locked 2026-08-11.

---

## 1. Purpose

Every claim in `Docs/paper/CLAIM_EVIDENCE_MATRIX.md` rests on **n = 6** pool-by-suite cells with one
seed. Three of those claims have exactly one dissenting cell each, and the matrix records all
three as unexplained. With n = 3 pools per suite, a 2-versus-1 split is indistinguishable from a
coin toss.

8 agents are densely banked on `crosscap240` and 10 on `hard366`. C(8,4) = **70** four-agent
pools and C(10,4) = **210** on `hard366` are computable from the answer bank at **zero API cost**,
because `single_expert` and `independent_majority` are in `FREE_PROTOCOLS` and make no model
calls (`mas_harness/protocols/__init__.py`).

This step converts three anecdotes into a distribution.

---

## 2. What is computed

For each of the 70 pools on `crosscap240` (and 210 on `hard366`), over its 15 coalitions × 2 free
protocols = 30 organizations:

**Policy values** — best single agent, best fixed organization, whole-pool majority vote,
capability router (per-capability argmax fitted on calibration), learned router `q_theta`,
oracle.

**Structure statistics** — oracle headroom \(H\); excess over the member-sharing null and its
\(p\); interaction likelihood-ratio statistic at agent and organization level; budget-matched
routed-minus-global gain at unconstrained and tight budgets.

**Pool descriptors** (the regressors) — mean member accuracy; ability spread (max − min); mean
pairwise error correlation; double-fault rate; distractor concentration; ability range in logit
space; cost spread across members.

Reuse without modification: `mas_harness/metrics/sharing_null.py`,
`mas_harness/metrics/routing.py`, `mas_harness/metrics/interaction.py`,
`mas_harness/metrics/utility.py`. All four already take a pool as input. Drivers to generalise
over subsets rather than named pools: `scripts/check_headroom_shared_members.py`,
`scripts/measure_routing.py`, `scripts/measure_interaction.py`,
`scripts/measure_cost_frontier.py`.

---

## 3. The methodological upgrade: a joint null over the whole sweep

**The 70 pools are not independent.** They are drawn from 8 agents, so any two pools sharing three
members are nearly the same pool. Treating 70 pools as 70 tests and applying Bonferroni would be
wrong in the conservative direction, and reporting them as independent would be wrong in the
dangerous direction.

The existing null already solves this, and this is the reason it is worth more than an internal
control. `sharing_null.py` simulates at the **agent** level under \(\sigma(\alpha_a + \beta_x)\)
and pushes simulated answers through the real \(\phi_p\). So:

> Simulate the **8-agent bank** once per replicate, then compute the statistic for **all 70
> pools** from that same simulated bank. Repeat 200–1000 times. This yields the null distribution
> of the *entire 70-pool sweep*, with member sharing across pools exact by construction.

That licenses a family-wise statement no per-cell test can make:

> *"Across all 70 four-agent pools, the observed distribution of headroom excess is not
> distinguishable from the distribution the same sweep produces under a no-interaction null at
> matched marginals."*

This is precisely the correction that arXiv 2607.20768 identifies and does not make — its 31,900
subsets are overlapping, *"a design that trades independence for coverage."* See
[`NOVELTY_BOUNDARY.md`](../literature/NOVELTY_BOUNDARY.md) §1.

---

## 4. Deliverables

**Artefact:** `data/runs/pool_sweep_crosscap240.json` and `..._hard366.json` — one record per
pool with every quantity in §2, plus the joint-null replicates.

**Figure A — the headroom distribution.** Observed headroom excess for 70 pools (points) against
the joint-null band (shaded). *Expected if C1 holds:* the point cloud sits inside the band, and
the three named pools are unremarkable members of it. This figure replaces Table 2 and is
strictly stronger than six Bonferroni-corrected p-values.

**Figure B — the policy ladder as a distribution.** For each of 70 pools, whole-pool vote minus
capability router. *Expected if Claim 3 holds:* mass predominantly ≥ 0. **The width and sign of
this distribution is the single most decisive number in the sweep** — see P2.

**Figure C — the regression.** Routing gain against pool descriptors. This is where `correlated4`
either becomes explicable or becomes noise.

**Table — the three named pools' percentiles** in the 70-pool distribution on every statistic.

---

## 5. Pre-registered predictions

| # | Quantity | Prediction | Refuted if | Consequence if refuted |
|---|---|---|---|---|
| **P1** | Headroom excess over joint null, 70 pools | Median ≈ 0; observed cloud inside the null band; significant pools at roughly the nominal rate (~3–4 of 70 at α=0.05) | A coherent subset clearly exceeds the band | **Not a loss.** We have found *which* pools carry routable structure — the payload of Direction A. Regress membership of that subset on descriptors. |
| **P2** | Fraction of 70 pools where whole-pool vote ≥ capability router | ≥ 70% | < 50% | **Claim 3 is refuted.** Routing beats voting more often than not; the paper pivots to "when does it", which is a *positive* paper. Better to learn this in 3 days than after drafting. |
| **P3** | Fraction where learned `q_theta` beats best fixed organization | ≤ 30% | > 50% | C2 is in trouble. Re-audit for leakage first (D-033 found the *baseline* leaking once already). |
| **P4** | Regression of routing gain on descriptors | Ability spread predicts routing gain **negatively**; error decorrelation predicts vote gain **positively** | No descriptor has predictive power (all \|ρ\| < 0.2) | The mechanism story in `FRAMEWORK.md` §5 has no support at n=70 and must be withdrawn or reduced to description. |
| **P5** | `correlated4`'s percentile on "capability router − vote" | Inside the bulk (5th–95th) | Above the 95th | It is a genuine anomaly and needs a mechanism, as the matrix already says |
| **P6** | Budget-matched routed-minus-global across 70 pools, at unconstrained *and* tight budgets | Negative at unconstrained; **positive at tight budgets in a majority of pools** | Tight-budget gain is near zero everywhere | The price-arbitrage reading in C2d is wrong and the tight-budget wins in the three named cells were noise |

**P5 is the cheapest win available.** The unexplained `correlated4` inversion is an open blocker
in `PAPER_BACKBONE.md` and TODO. In a sample of three, a 2-versus-1 split needs no explanation at
all. Placing it in a distribution of 70 most likely dissolves the blocker without any new theory.

**P6 is now load-bearing** — see §7.

---

## 6. Why no outcome wastes the three days

This is the argument for running Step 1 before committing to any direction.

- **P1 confirmed** → C1 upgrades from six cells to a family-wise statement over 70 pools with a
  correct joint null. Strictly stronger than the current paper.
- **P1 refuted** → we have located routable structure and the paper becomes "here is where
  routing pays and here is how to find it" — a positive contribution.
- **P2 confirmed** → Claim 3 upgrades from *comparative* to *systematic* on the strength ladder.
- **P2 refuted** → the current Claim 3 was an artifact of n=3 and we learn it before drafting
  rather than in review.

The one genuinely bad outcome is P4 refuted *and* P1 confirmed: no structure and no explanation
of the variation, leaving a purely descriptive null result. In that case fall back to
Direction D as planned.

---

## 7. What `Docs/literature/ROUTING_ARCHITECTURES.md` changes

Reading the nine methods surveyed there, **their headline claims are about cost, not accuracy**:
MixLLM *"97.3% of GPT-4's answer quality at only 24.2% of the cost"*; IPR *"~43.9% cost
reduction"*; EvoRoute *"cost ~80%, latency ~70%"* reduction; MasRouter *"up to ~52% cost
reduction"*; Routesplain and Tryage both framed as accuracy-**cost** tradeoffs.

Two consequences, both serious:

1. **The current paper attacks routing on the wrong axis.** Claims 2 and 3 are accuracy claims —
   routing does not beat a fixed organization or a vote *on accuracy*. A reviewer from this
   community answers: *we never claimed accuracy gains; we claimed a 4× cost reduction at
   equivalent quality.* The accuracy negative does not touch that.
2. **Our own data may agree with the literature in the regime it actually operates in.** C2d
   finds routing losing at *unconstrained* budget — where nobody deploys a router — and
   **winning at the tightest budgets** (+4.05, +2.68, +13.91, ahead in 81–100% of resplits),
   which is exactly the deployment regime. As currently framed, the paper's headline negative
   sits in the irrelevant regime and its counter-evidence sits in the relevant one.

**The repair, and it is an opportunity.** Every method in that survey justifies sparse gating by
assuming querying all models is too expensive — *"rather than querying all LLMs, they select a
small subset to save cost."* **Not one of the nine compares against spending the same budget on
several cheap models plus aggregation.** That baseline is absent from the field, and this project
is uniquely equipped to supply it: exact costs repriced from token buckets (§6.4 of
`FRAMEWORK.md`), dense counterfactuals over all coalitions, and free replay.

The question the field has not asked:

> **At equal dollar cost per task, is it better to route to one strong model, or to vote over
> several cheap ones?**

This reframes the paper from an accuracy negative into a positive, practical claim on the axis
the field actually competes on — and it makes P6 and the currently-unrun **price-flattened
rerun** (evidence gap #4 in the matrix) central rather than optional, because they separate
capability matching from domain-price arbitrage.

---

## 8. Implementation notes

- **Vectorise the joint null.** 200 replicates × 70 pools × 15 coalitions × 240 tasks is ~50M
  vote evaluations. Per-episode Python will not finish; compute votes as array operations over
  the equivalence-class encoding `sharing_null.py` already builds.
- **Reuse the calibration/test splits** and the resplit machinery in
  `mas_harness/metrics/routing.py`; do not introduce a new split convention.
- **Leak discipline is unchanged**: the capability router's per-group choice, the fixed-best
  choice, the embedding projection and `q_theta` are all fitted on calibration only.
- `hard366` has 10 dense agents → 210 pools. Run `crosscap240` (70) first; it is the suite that
  carries interaction and is therefore the informative one.

## 9. Verification

The three named pools must reproduce their published numbers **exactly** — `strong4`,
`decorrelated4` and `correlated4` must match `data/runs/headroom_null_shared_members.json` and
`data/runs/routing.json` to two decimals. Any mismatch is a bug in the generalised driver, not a
finding. This is the first thing to check and it is a hard gate on the rest of the sweep.

Cost: **$0**. Estimated 2–3 days, most of it in vectorising the joint null.
