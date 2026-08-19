<!-- doc-meta
type:          living
lifecycle:     update-in-place — never fork a v2; git history is the version record
last-verified: 2026-08-19
evidence-base: see §A5 traceability table
supersedes:    Docs/CURRENT_STATE.md (folded in, 2026-08-11)
-->

# Project state

**The single source of truth for where this project is.** Update this file in place; do not
write a new state report. `TODO.md` records what is not done. `DECISIONS.md` and
`EXPERIMENT_LOG.md` are append-only ledgers of how we got here.
[`Docs/README.md`](Docs/README.md) explains what every other document is.

Two parts: **A. Research state** — what we know and what is decided. **B. System state** —
what runs, and the invariants that make results trustworthy.

---

# Part A — Research state

## A1. The project in ten lines

Started 2026-08-04 as three candidate ICLR projects sharing one experimental substrate:
**epistemic governance**, **delegation-equivalent task representations**, **coalition
landscapes**. A pre-registered gate was to pick one on evidence.

All three failed. Governance died on a refuted pre-registration (D-026 → D-027). Coalition
failed its criterion on all three pools. Delegation was selected by the gate, then the gate
itself was shown to be non-falsifiable (D-029, D-030), and the direction closed on its own
merits (D-033 → D-036), then closed again at n=280 with four further research questions
(D-040, D-041).

**Where it ended, as of 2026-08-14.** The empirical work is complete and internally sound. Every
question the project posed has an answer, backed by 280 pools, five pre-registrations, and
instruments whose error rates are measured rather than assumed. **And every answer that is
interesting is already published** — see §A4 item 11 and
[`Docs/literature/ENSEMBLING_NOVELTY.md`](Docs/literature/ENSEMBLING_NOVELTY.md).

The two results that survive on their own terms:

- A **methodological negative**, family-wise over 280 pools with a calibrated instrument: oracle
  headroom is not evidence of routable structure, the cost comparison paired with it is unsound, and
  the one apparent routing win is priced-by-domain arbitrage (D-040 → D-042).
- A **mechanism**, with a single-model control: aggregation is worth +1.9 pp where members are
  unanimously correct and +5.6 pp where they split, but **−15.7 pp where they are unanimously
  wrong**, because reading four wrong answers halves a strong model's accuracy (D-043 → D-045).

Neither is novel. Prior work holds each, generally at larger scale.

⚠️ [`Docs/paper/PAPER_BACKBONE.md`](Docs/paper/PAPER_BACKBONE.md) predates all of this and is
**superseded**; [`Docs/paper/CLAIM_EVIDENCE_MATRIX.md`](Docs/paper/CLAIM_EVIDENCE_MATRIX.md) is
authoritative for numbers.

**Total spend: $139.78** of an originally allocated ~€3,000 — under 5%. See §A7; the ledger is
authoritative and the prose figures that predate it are not.

## A2. Current direction — the results are sound and the novelty is gone

**This section is a dated log, newest first.** Entries below the top one record what was believed at
the time and are deliberately not rewritten; several say things like "is now decisive" or "is the
highest-priority action", which were true when written and are not now. For current status read only
the top entry and §A1.

**2026-08-19: a seventh direction is closed and an eighth is adopted, both by the gate
discipline.** The composition-gated exposure proposal passed its novelty gate and failed its
arithmetic — a perfect gate is worth +0.97 pp pooled, below the bar that killed RQ5 (D-046,
[`Docs/proposals/2026-08-19-exposure-gating-REVIEW.md`](Docs/proposals/2026-08-19-exposure-gating-REVIEW.md)).
The **entitlement direction** replaces it (D-047): deference under provable ignorance on the
distributed-information substrate (D-010/D-015), where effect sizes are designed rather than
benchmark accidents and the access-label claim is verifiably unoccupied across two shelves.
A frozen pilot ([`2026-08-19-entitlement-pilot.md`](Docs/preregistrations/2026-08-19-entitlement-pilot.md))
gates it before the main study. Target ICLR 2027; NAACL 2027 ARR fallback. §A1's "nothing
experimental remains open" is superseded by this entry.

**2026-08-14, last: the conformity follow-up is closed at its own gate, for $0.** A three-arm study
was designed, implemented and tested — `protocols/conformity.py`, `metrics/adoption.py`, 18 tests —
and its step-0 novelty gate stopped it before any spend. arXiv 2606.01637 already attaches authority
labels to peers, already manipulates the label independently of correctness, and already measures
adoption rather than accuracy. **Three separate proposals have now been closed by that one paper.**
See [`Docs/literature/CONFORMITY_PROPOSAL.md`](Docs/literature/CONFORMITY_PROPOSAL.md).

**2026-08-14, night: the ensembling and conformity literature was checked and it closes every
remaining claim** ([`Docs/literature/ENSEMBLING_NOVELTY.md`](Docs/literature/ENSEMBLING_NOVELTY.md)).
C1, C1' and C5a are held by *How Much of the Routing Gap Is Real?* (arXiv 2607.03436, Jul 2026) and
*RouteGuard* (arXiv 2608.07583, Aug 2026) — the latter also ships the pre-deployment routing
certificate this project would have built next, on 11 models and 36,497 prompts. D-045's S1 is held
by *Rethinking Mixture-of-Agents* (arXiv 2502.00674, Feb 2025) and *The Cost of Consensus* (arXiv
2605.00914, Apr 2026). D-045's S2/S3 — the anchoring asymmetry — is held by *Easier to Mislead Than
to Correct* (arXiv 2606.01637, Jun 2026), **in our setting, with our control, at four times our
scale**.

The 2026-08-11 novelty check missed four of these because it searched the *routing* shelf while the
project's findings were *ensembling and conformity*. The lesson generalises: re-scope the novelty
check when the result changes shape, not when the plan does.

**The results are not wrong — they are unoriginal.** No paper survives from the current findings. The
decision in front of the project is therefore not which paper to write but whether to consolidate,
re-scope, or change substrate; §A2b records the options.

## A2b. The prior direction record — undecided, and superseded by the novelty check above

As of 2026-08-11 the paper framing was **under active review** and no direction is committed. The
2026-08-11 review raised four things bearing on the choice; they are recorded in
[`Docs/literature/NOVELTY_BOUNDARY.md`](Docs/literature/NOVELTY_BOUNDARY.md) and in §A4 below.

**2026-08-13, morning: the pre-registered pool sweep is run (D-040), on both suites, for $0.** Three
pools became 280. It confirms C1 family-wise, dissolves the `correlated4` blocker, strengthens C2,
forces C3c to weaken, and adds a control to the cost reading. It also surfaces a threat none of the
review items anticipated — see §A4 item 5.

**2026-08-14, evening: the control lands against the headline and produces a better result (D-045).**
`claude-sonnet-5` banked as an ordinary pool member, $12.09. It beats whole-pool voting in four pools
of six on its own and beats the best individual member by +4.3 to +7.1 pp on `crosscap240`. Judge
minus solo clears the pre-registered +2.0 pp bar in only 3 of 6 pools, so **"a coordination protocol
beats a voting rule" is dead** — at 1.4–1.8× the cost of one call for 1.3–2.1 points, the deployment
answer is to use the strong model alone.

**What replaces it is better.** Decomposing by what the members did: aggregation is worth **+1.9 pp**
where they are unanimously correct, **+5.6 pp** where they split — and **−15.7 pp where they are
unanimously wrong**, because reading four wrong answers *halves* the model's accuracy (0.343 → 0.186;
0.591 → 0.273 in the worst cell). That is **expert dilution, in the opposite place from where D-044
looked for it**, measured with a single-model control. Whether the net is positive is a property of
the pool's error profile — and this project has 280 pools of those.

**2026-08-14, later: the judge is answering, not aggregating (D-044).** Run on the 245 tasks D-020
never priced, it solves **18.6% of tasks where every member was wrong** — which no selection rule can
do — and that accounts for **28% of its entire advantage over voting**. It does *not* damage correct
consensus (2 overrides of 230), so the expert-dilution reading is dead. The disagreement-triggered
cascade is also dead: it saves 22–38% of cost but loses 0.4–2.1 pp, because it never escalates where
the value is. **D-043's replication stands on full suites (+3.8 / +8.0 / +4.6 pp) but its
interpretation does not.** The aggregator-solo control is now decisive rather than hygienic.

**2026-08-14: `independent_judge` replicates on `crosscap240` (D-043) — the project's first positive
result.** Pre-registered and named in advance. Against the calibration-chosen best aggregation rule it
gains +4.65 / +7.42 / +3.38 pp on the new suite and +1.42 / +6.09 / +1.33 on the old — **six pools of
six, two suites, both D-028 scorings**, and larger where interaction is real. Against whole-pool
voting on paired tasks it is positive in all six (+1.12 to +7.69 pp) at **3.5–17.1× the cost**.
Picking the best protocol per pool remains noise (split-half 0.32), so only the a-priori name is
admissible. **One confound blocks any claim:** the judge model has never been measured answering
alone. That control costs ~$3–6 and is the highest-priority action in the project.

**2026-08-13, evening: the positive experiments are run (D-042).** Selection rules cannot beat the
calibration argmax on either suite (ceiling only +1.2–1.6 pp, nothing captures it), the tight-budget
routing win **inverts** under flattened prices and is therefore arbitrage, and two of six
pre-registered verdicts flip on an equally valid answer draw. **One positive claim survives:**
`independent_judge`, named a priori, beats the calibration-chosen best aggregation rule in 3 of 3
pools (+1.42 / +6.09 / +1.33) with a handicap that runs in its favour. It cannot clear its
replication clause because the priced protocols never ran on `crosscap240`. **That run, ~$60–90 with
the D-028 repair, is the only route from this substrate to a positive result, and the first time
since D-023 that spending is the highest-value action.**

**2026-08-13, afternoon: RQ2–RQ5 are run and delegation-as-routing is closed (D-041). NO-GO.** The
four research questions that had been specified and never built are now tested, under thresholds
fixed in advance. All four are negative; the single GO trigger failed its own audit and the
correction moved the verdict away from GO. **The direction "a learned model picks the organization
per task" is closed on this grid.** What survives is the selection-variance diagnosis (D-040), the
supervision-efficiency crossover (RQ3), and a new positive: making interaction protocols available
to a *fixed* choice is worth **+2.18 pp**, while routing among them is worth nothing.

## A3. What is safe to claim

| Claim | Strength | Evidence |
|---|---|---|
| Oracle headroom does not exceed a matched null preserving member sharing | strong | **280 pools across both suites** (D-040) + 6 named cells + 134 public systems; median excess −1.63 / +0.14 pp, 0/70 and 5/210 pools at p≤0.05 against 2.5 and 8.4 expected; null replays real episodes at agreement 1.0000, fires on planted specialists, and its false-positive rate is measured at 0.016 / 0.000 against a nominal 0.050 |
| Interaction is present in `crosscap240`, absent in `hard366` | strong | D-038; p≤0.005 at agent and organization level vs p=0.164. **D-040: p≤0.05 in 100% of the 70 `crosscap240` pools, median excess departure +4.41 pp** |
| Headroom is *insensitive* to interaction, not merely inflated | strong | the same tables carry interaction at p≤0.05 in every pool while headroom excess is at or below the null in all of them |
| A learned router gains nothing here, and it is not a data-volume problem | strong | D-033 flat learning curve 57→398 tasks; **D-040: mean gain −0.01 pp over 70 pools and −0.46 pp over 210, ahead in 43.2% / 30.2% of resplits, while the shuffled control loses 2.42 pp** |
| A linear cost sweep reaches only the convex hull | strong | 3–9 of 30 Pareto-efficient organizations unreachable at any λ in the named cells; **median 8 across 280 pools** |
| Routing loses at unconstrained budget and wins only at the tightest budgets on the *cross-capability* suite | strong | D-040: unconstrained positive in 15.7% of `crosscap240` and **0.0%** of `hard366` pools; tightest +5.11 pp in 97.1% vs +0.65 pp in 59.5% |
| Routing does not pay even when the choice set contains interaction protocols, but the best *fixed* organization gains +2.18 pp from having them | strong | D-041: `q_θ` −1.05 / −0.64 / −0.67 pp on 35 organizations; fixed-best accuracy 0.819/0.829/0.863 → 0.864/0.862/0.851 |
| Delegation generalizes no better than it interpolates | strong | D-041: −0.29 IID, −0.18 domain holdout, +0.81 agent holdout (conditioning gain **−0.10**), −0.22 organization holdout, over 70 pools |
| Choosing *whether* to collaborate is not learnable either | strong | D-041: −0.40 pp against the better fixed policy, ahead in 18% of resplits; a perfect oracle over the pair is worth only +2.29 pp |
| Dense counterfactual supervision beats an execution log above 20% of the grid, and loses below it | moderate | D-041: dense minus log −2.44, −0.80, +0.35, +1.81, +2.53 pp across the budget sweep |
| ~~`independent_judge` beats aggregation~~ | **retired as a headline** | D-045: the aggregator alone beats voting in 4 pools of 6 and the judge clears +2.0 pp over it in only 3 of 6. Use the strong model alone. **And the survivors are not novel** — see §A4 item 11 |
| **Reading unanimously-wrong peer answers halves a strong model's accuracy** | **strong** | D-045: solo 0.343 vs judge 0.186 pooled over six pools, 0.591 vs 0.273 in the worst cell. Expert dilution, with a single-model control |
| Aggregation helps where members split (+5.6 pp) and slightly where they are unanimously correct (+1.9 pp) | strong | D-045: judge beats solo on split tasks in 6 pools of 6, +1.66 to +6.98 pp |
| A judge does not damage a correct consensus | strong | D-044: 2 overrides of 230 unanimous-correct tasks |
| Member disagreement is a bad escalation signal | strong | D-044: a disagreement cascade saves 22–38% of cost and loses 0.4–2.1 pp, because 28% of the value is on unanimously-wrong tasks |
| Picking the *best* protocol per pool is noise | strong | D-041 and D-043: split-half reproducibility 0.00–0.17 on `hard366`, 0.10/0.87/0.00 on `crosscap240` |

## A4. What is weak, contested, or overclaimed

1. **"Rules out an entire family of routers."** The capability router bounds only routers whose
   representation is a function of a **four-way dataset-provenance partition**. Every router in
   the literature uses more. Overclaimed in `PAPER_BACKBONE.md`; `FRAMEWORK.md` §2 is correct.
2. ~~**"Aggregation is a substitute for routing."** Rests on 2 of 3 pools. **n=3.**~~
   **Measured at n=280 (D-040) and it must weaken.** Voting is at or above the oracle-labelled
   capability router in 60.0% of `crosscap240` and 65.7% of `hard366` pools, mean margin ≈ +0.28 pp,
   5th–95th −5.1 to +7.5. Give the router all thirty organizations and voting leads in only 44.3% of
   `crosscap240` pools. It is a coin flip tilted toward voting, not a substitution result. **C3c is
   the claim most damaged by the sweep.**
3. ~~**Three dissenting results, recorded and unexplained.**~~ **Two dissolve, one survives with a
   control (D-040).** Semantic k-NN goes to mean −0.06 pp, positive in 48.6% of 70 pools. The
   `correlated4` capability-router inversion sits at the 55.7th percentile — and see item 5 for why
   it existed at all. The tight-budget routing win *survives and sharpens*: it is specific to
   `crosscap240` (+5.11 pp in 97.1% of pools) and near-absent on `hard366` (+0.65 pp, 59.5%), which
   is what price arbitrage predicts and capability matching does not.
4. **Proposition 1** assumes no interaction and concludes no exploitable structure — close to
   definitional. **Lemma 2** is a textbook fact about weighted-sum scalarisation.
5. **Re-running the same seed is a different draw, and it is large enough to invert a cell.**
   `crosscap240` banked several agents twice; of 959 repeated agent-tasks, **49 disagree on
   correctness and 121 differ in answer text** at temperature 0. Rebuilding `correlated4` from the
   alternative draw moves vote-minus-router from −2.50 pp to +0.63 pp. `hard366` has zero
   disagreements only because its runs shared the response cache. This supersedes the old "one seed
   everywhere" caveat, which understated the problem, and it is now the **largest known threat to any
   single-cell number in the project**, including several that predate D-040.
6. **Eight to ten agents, one provider, two protocols** in every cross-suite comparison.
7. **The paper may be arguing on the wrong axis.** The routing literature's headline claims are
   about **cost**, not accuracy. Our budget result finds routing losing at *unconstrained*
   budget — where routers are not deployed — while winning at tight budgets, where they are.
   D-040 makes this sharper, not softer: unconstrained routing is positive in **0 of 210** `hard366`
   pools while tight-budget routing is positive in **97.1%** of `crosscap240` pools.
8. ~~**Roughly 4% of the substrate has been used.**~~ **The free four-agent family is now fully
   enumerated on both suites** — 70 + 210 pools, D-040. Still unused: the five priced protocols on
   `crosscap240`, aggregation-only protocols beyond the two free ones, three public matrices, and the
   six banks with answers but no episodes.
9. **`Nash-CredMAS` in the literature review does not exist**; six other entries are unverified.
11. **Every surviving claim is already published, and the check that should have caught it was
    scoped to the wrong field.** [`Docs/literature/ENSEMBLING_NOVELTY.md`](Docs/literature/ENSEMBLING_NOVELTY.md)
    maps each claim to prior work: C1/C1'/C5a to arXiv 2607.03436 and RouteGuard 2608.07583, the
    judge result to 2502.00674 and 2605.00914, the anchoring asymmetry to 2606.01637 — the last in
    our setting, with our control, at four times our scale. The 2026-08-11 novelty check missed four
    of these because it searched the *routing* shelf while the findings were *ensembling and
    conformity*. **Re-scope the novelty check when the result changes shape, not when the plan does.**
10. **P4's mechanism regressors do not replicate.** Neither pre-registered directional claim holds on
    both suites: ability spread predicts routing gain *positively* (+0.15, +0.28) where negative was
    predicted. FRAMEWORK §5's mechanism is descriptive at n=280, not predictive.

## A5. Traceability — which artefact backs which claim

Every run directory carries `run_meta.json` with pool, manifest content-hash, price snapshot and
upstream pins. That is the authoritative version record; this table is the index into it.

| Artefact (`data/runs/`) | Produced by | Decision | Date |
|---|---|---|---|
| `strong4-a/`, `decorr4-a/`, `correlated4-a/` | `scripts/run_priced.sh` | D-024 … D-028 | 2026-08-06 |
| `hard366-a/`, `crosscap-*/` | Stage A + free Stage B | D-020, D-032 | 08-05, 08-10 |
| `headroom_null.json` | `check_oracle_headroom.py` | D-034 | 2026-08-08 |
| `headroom_null_swebench.json` | `check_headroom_swebench.py` | D-034 | 2026-08-08 |
| `headroom_null_specialists.json` | `check_headroom_specialists.py` | D-035 | 2026-08-09 |
| `headroom_null_shared_members.json` | `check_headroom_shared_members.py` | D-037 | 2026-08-10 |
| `routing.json`, `routing_pooled.json` | `measure_routing*.py` | D-033 | 2026-08-07 |
| `cost_frontier.json` | `measure_cost_frontier.py` | D-036, D-039 | 08-08, 08-10 |
| `interaction.json` | `measure_interaction.py` | D-038 | 2026-08-10 |
| `pool_sweep_crosscap240.json`, `pool_sweep_hard366.json` | `measure_pool_sweep.py` | D-040 | 2026-08-13 |
| `research_questions.json` | `measure_research_questions.py` | D-041 | 2026-08-13 |
| `positive_selection.json`, `pool_sweep_crosscap240_altdraw.json` | `measure_positive_selection.py`, `measure_pool_sweep.py --tag _altdraw` | D-042 | 2026-08-13 |
| `judge_replication.json`, `crosscap-*/episodes.jsonl` (priced) | `run_priced_crosscap.sh`, `measure_judge_replication.py` | D-043 | 2026-08-14 |
| `judge_on_easy_tasks.json` | `run_judge_on_skipped.sh`, `measure_judge_on_easy_tasks.py` | D-044 | 2026-08-14 |
| `aggregator_solo.json`, `aggregator-solo/answers.jsonl` | `run_aggregator_solo.sh`, `measure_aggregator_solo.py` | D-045 | 2026-08-14 |
| `figures/pool_sweep_*` | `report_pool_sweep.py` | D-040 | 2026-08-13 |
| *(none — designed, gated, never run)* | `protocols/conformity.py`, `metrics/adoption.py` | closed at step 0 | 2026-08-14 |

**Rule going forward:** any document quoting a number names the artefact key it came from, as
[`Docs/paper/CLAIM_EVIDENCE_MATRIX.md`](Docs/paper/CLAIM_EVIDENCE_MATRIX.md) already does per row.

## A6. Open questions

1. ~~Is *"aggregation substitutes for routing"* real, or an n=3 artifact?~~ **Answered (D-040):
   neither. It is a coin flip tilted toward voting — 60.0% / 65.7% of 280 pools. C3c must weaken.**
2. ~~Why does the capability router beat voting in `correlated4`?~~ **Answered (D-040): it does not,
   robustly. The pool sits at the 55.7th percentile of 70, and the inversion does not survive the
   alternative answer draw of the same four agents (−2.50 pp → +0.63 pp).**
3. ~~Are the tight-budget routing wins capability matching or domain-price arbitrage?~~ **Answered
   (D-042): arbitrage. Flattening the domain price channel inverts the win from +5.34 pp to −5.78 pp
   on `crosscap240` and from +0.71 to −2.80 on `hard366`, positive in 0% of pools on both.**
4. ~~Does `independent_judge` actually win?~~ **Answered (D-043, D-044, D-045).** It beats
   aggregation in six pools of six, but the aggregator *alone* beats voting in four of six, and the
   judge clears +2.0 pp over it in only three. At least 28% of its edge is solving tasks no member
   solved. The honest deployment answer is to use the strong model alone.
5. ~~`crosscap240` under the five priced protocols — never run.~~ **Run 2026-08-14 (D-043), $34.16.**
   2,365 priced episodes on discriminating subsets of 165 / 180 / 130 tasks, plus 244 more on the
   previously-skipped unanimous tasks (D-044).
6. ~~A second seed.~~ **Partly answered and worse than expected (D-040):** the duplicate banking in
   hand is a second draw and disagrees on 5.1% of `crosscap240` agent-tasks.
7. ~~Do the sweep's conclusions hold under the alternative answer draw?~~ **Answered (D-042): P1, P5
   and P6 hold; P2 and P3 flip.** The headline is robust to the draw; the marginal claims are not.
8. ~~RQ2–RQ5, never built.~~ **Answered (D-041): all four negative, NO-GO on RQ2-style delegation.**
9. ~~Why is the best fixed organization better with interaction protocols available?~~ **Answered
   across D-042 to D-045.** "Pick the best protocol" is noise; `independent_judge` named a priori is
   positive everywhere; and D-045 shows the effect is largely the aggregator's own competence.
10. ~~Which pool compositions make aggregation net-harmful?~~ **Designed and gated, not run.** The
    question is well-posed and the substrate suits it, but the manipulation it rests on is already
    published (§A4 item 11).

**What is actually open, as of 2026-08-14.** Nothing that another experiment on this substrate would
settle. Every empirical question the project posed has an answer, and every answer that is
*interesting* is also already in the literature. The open questions are now editorial and strategic,
not experimental:

- What, if anything, is written up, and as what — a methods contribution about the process, or
  nothing.
- Whether the substrate is retargeted at a problem far enough from this one that a three-month lead
  does not decide it. Agentic or tool-using tasks are the obvious candidate and would need a
  code-execution sandbox the harness does not have.

## A7. Bookkeeping discrepancies to reconcile before publication

- **Total spend** is **$139.78** in `data/runs/spend_ledger.jsonl`, which is authoritative. The
  historical prose figure of **$85.13** and the pre-2026-08-14 ledger figure of **$88.09** differ by
  ~$3 for reasons never traced; per-run figures differ by ~$1 (`strong4-a` $19.36 vs $20.21). The
  2026-08-14 additions are exact: $34.16 priced `crosscap240` (D-043), $5.44 skipped tasks (D-044),
  $12.09 aggregator solo (D-045). **Quote the ledger, not the prose.**
- `data/runs/calib15/` is empty; `dry-*` and `plan-*` hold only price snapshots.
- ~~No `discrimination.json` for any `crosscap` run.~~ Written 2026-08-14 for all three; `gonogo.json` still absent.
- Six banks have answers but **no episodes** — free Stage B value never spent.
- Terminology is inconsistent across `DECISIONS.md`: "organization" / "configuration" /
  "coalition" / "pool". Open blocker before drafting.

---

# Part B — System state

## B1. Status at a glance

| Layer | State | Where |
|---|---|---|
| Environment, upstream pins, preflight | works | `pyproject.toml`, `UPSTREAM.md`, `mas_harness/doctor.py` |
| Cost accounting, cache, spend caps | works | `mas_harness/clients/` |
| Task manifests, splits, evaluators | works, 3 of 4 MVP domains | `mas_harness/tasks/` |
| Distributed-information condition | built, **never run against real models** | `mas_harness/tasks/distributed.py` |
| Agent pools, predicted expert, role rotation | works | `mas_harness/pool/` |
| Stage A answer bank | works, run on both suites | `mas_harness/runners/answer_bank.py` |
| Protocols 1–7 | works | `mas_harness/protocols/` |
| Causal interventions | works | `mas_harness/interventions/edits.py` |
| Stage B episodes, records, Parquet | works | `mas_harness/runners/episodes.py`, `records/` |
| Governance / delegation / coalition metrics | works | `mas_harness/metrics/` |
| No-interaction nulls (independent + member-sharing) | works | `mas_harness/metrics/sharing_null.py` |
| Interaction likelihood-ratio test | works | `mas_harness/metrics/interaction.py` |
| Go/no-go gate | works, **criteria retired** — see D-029, D-030 | `mas_harness/analysis/gonogo.py` |
| Learned router + baseline ladder | works, run on 6 cells and 280 pools, no gain | `mas_harness/metrics/routing.py` |
| Pool sweep: joint null, policy ladder, descriptors over every 4-agent pool | works, run on both suites (D-040) | `mas_harness/metrics/pool_sweep.py` |
| RQ2–RQ5: interaction families, supervision efficiency, three holdouts, solo-or-collaborate | works, run (D-041) | `mas_harness/metrics/research_questions.py` |
| Fixed-organization selection rules, a-priori protocol rules | works, run (D-042) | `mas_harness/metrics/selection.py` |
| Competence-label arms and the adoption model | **built and tested, never run** — gated at step 0 | `mas_harness/protocols/conformity.py`, `mas_harness/metrics/adoption.py` |
| Coding domain (EvalPlus) | unavailable, no sandbox | `TODO.md` |
| GPUs / local vLLM | host has **no GPU at all** | `TODO.md` |

**486 tests pass** (412 + 26 sweep + 16 research questions + 14 selection + 18 conformity); `ruff check` clean over `mas_harness`, `scripts`, `tests`.

## B2. Substrate

**Two-stage design (D-001).** Stage A banks one independent answer per (task, agent, seed).
Stage B replays protocols over the bank. Aggregation protocols are deterministic functions of
banked answers, so they cost nothing and `do(·)` interventions are exact computations rather
than re-elicitations. Upstream `Task.execute()` is never called.

**Suites** — 9 manifests built and content-hashed.

| suite | tasks | composition | agents densely banked |
|---|---:|---|---:|
| `hard366` | 366 | GPQA-Diamond 122, MATH-500 L5 122, MMLU-Pro theoremQA/scibench 122 | 10 |
| `crosscap240` | 240 | CRUXEval 60, AIME 60, ExploreToM 60, GPQA-Diamond 60 | 8 |
| `screen120` | 120 | subset of `hard366`, so its calls are cache hits | 16 |
| `distributed30`, `distributed30_pressure` | 30 each | synthetic partitioned-option arms | 0 — never banked |
| `mvp366`, `mvp90`, `pilot9`, `crosscap12` | — | retired: saturated | — |

**Pools** — all use `anthropic/claude-sonnet-5` as aggregator so the pool contrast is not
confounded with judge identity (D-024).

| pool | members | error corr | `single_expert` |
|---|---|---:|---:|
| `strong4` | grok43, gpt5mini, deepseek32, llama4scout | +0.408 | 0.8989 |
| `decorrelated4` | gptoss120b, llama4scout, mistral-small, ring26 | +0.382 | 0.8552 |
| `correlated4` | gpt5mini, deepseek32, gptoss120b, qwen3-30b | +0.579 | 0.8989 |

**Protocols** — 7, described in
[`Docs/reference/PROTOCOL_CARD.md`](Docs/reference/PROTOCOL_CARD.md). Two are free (zero model
calls): `single_expert`, `independent_majority`. Five are priced.

⚠️ **The five priced protocols ran on `hard366` only**, on each pool's discriminating subset
(129–210 tasks). **`crosscap240` — the only suite where interaction is detectable — has never
seen a priced protocol.** Every cross-suite claim rests on 15 coalitions × 2 protocols = 30
"organizations", where the two protocols are vote and solo.

**On disk:** 6,024 banked answers across 16 agents; 97,531 episodes; 99 MB response cache.
The figure quoted in the paper — 4,392 answers → 57,489 episodes — is the three priced
`hard366` pools specifically.

**Constraints:** single seed (`seeds: [0]`, temperature 0) everywhere — and note D-040: re-running
that seed is not deterministic, 49 of 959 repeated `crosscap240` agent-tasks disagree on correctness.
No GPU; no code-execution sandbox; caps are per-run ($75) and per-day ($150), not cumulative.

## B3. Load-bearing invariants

Asserted by tests, not merely intended. If one breaks, a scientific claim breaks with it.

- The two free protocols make **zero** model calls. The entire cost argument rests on it.
- Every protocol on a task sees byte-identical banked answers, so comparisons are exactly
  paired and McNemar applies.
- The predicted expert is fitted on the calibration split only; the oracle is computed but
  never pooled with it (D-004).
- An answerless message is an abstention, not a vote (D-011).
- Interventions never mutate the input bank.
- Every branch point in the governance protocols is resolved by extraction or string matching,
  never by a second model (D-003, D-013).
- Role rotations carry distinct pool ids, so they cannot collide in the resume set (D-014).
- In the distributed condition the correct option is visible to exactly the recorded holders,
  the union of visible option sets is complete, and every member sees the same number of
  options (D-010). Checked per task at build time.
- Manifest content hashes cover private briefings, so a changed partition is a changed
  manifest (D-016).

## B4. Known limitations

- Three of four MVP domains available; no code-execution path, so the coding domain is absent.
- The distributed condition is *constructed*, not HiddenBench, and labelled `distributed_synth`
  (D-010). Compare protocols within the condition, never across.
  `out_of_set_rate()` has never been measured on real model output.
- `mixed_effects_logit` clusters on task via GEE rather than fitting crossed task+seed random
  effects. Adequate for a pilot, not for the paper.
- The semantic task space falls back to character n-gram TF-IDF when `sentence-transformers`
  cannot reach the network. Both paths measured and agreeing (Spearman 0.028–0.105 real,
  0.048–0.063 fallback), but each report must be read for which it used.
- **Configuration dominance is retired** (D-029) — diluted by adding protocols, and its noise
  null's 95th percentile lands exactly on the 75% threshold. Superseded by split-half winner
  reproducibility in `mas_harness/metrics/stability.py`. Any figure quoting it predates D-029.
- Harsanyi decomposition is exact and therefore exponential; refuses above twelve agents.
- `--dry-run` came in 1.9–3.0× above measured cost. Treat it as an upper bound, not a forecast.
- Absolute accuracy is not comparable across pools, only protocol contrasts within one (D-021).
  Nor is accuracy on a discriminating subset comparable to a full-suite figure.
