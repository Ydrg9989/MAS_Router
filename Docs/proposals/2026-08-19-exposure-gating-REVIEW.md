<!-- doc-meta
type:          report
lifecycle:     frozen once the adoption decision is logged; until then update-in-place
last-verified: 2026-08-19
evidence-base: data/runs/aggregator_solo.json; the $0 class-share replay (script and
               per-pool table under the 2026-08-19 session scratchpad, exposure/); an
               11-agent verification pass in which every cited paper was fetched in-session
-->

# Review: the composition-gated peer exposure proposal — NO-GO as proposed

Reviews three documents drafted 2026-08-19 and not yet in the repo:
`2026-08-19-exposure-gating-proposal.md` (never provided to the reviewer; P1–P6 and E1–E5 are
known only by reference), `2026-08-19-exposure-framework.md`, and
`2026-08-19-exposure-implementation.md`. The idea: a per-task gate deciding whether the judge's
prompt includes the peers' answers, thresholding P(pool is right | answer pattern), built on
D-045's class decomposition (delta_R +1.9pp, delta_S +5.6pp, delta_W −15.7pp).

**Verdict: the step-0 novelty gate passes, narrowly — and the step-1 empirical gate fails, measured
for $0 before any pre-registration was frozen.** The oracle ceiling of the proposed gate is below
the bar this project used to kill RQ5, the transportability law A1 is contradicted-or-undecidable
in its own founding six cells, and the class the flagship "suspicious unanimity" rule governs holds
about one percent of tasks. The direction should be closed or fundamentally re-substrated, not run.

---

## 1. The effect ceiling fails the project's own kill standard

A **perfect** class-oracle gate (expose except where solo beats the judge, classes known) gains
over always-expose, per cell, from `aggregator_solo.json`:

| cell | oracle gain | tasks moved |
|---|---:|---:|
| crosscap240 / strong4 | +0.42 pp | 1 of 239 |
| crosscap240 / decorrelated4 | **+2.94 pp** | 7 of 238 |
| crosscap240 / correlated4 | +1.25 pp | 3 of 240 |
| hard366 / strong4 | +0.56 pp | 1 of 179 |
| hard366 / decorrelated4 | 0 | 0 |
| hard366 / correlated4 | 0 (judge beats solo on W) | 0 |
| **pooled** | **+0.97 pp** | **12 of 1,235** |

D-041 closed RQ5 with an oracle ceiling of +2.29 pp as "worth little even in principle." This
ceiling is smaller, and 7 of its 12 tasks sit in one 22-task cell. The realized degenerate gate
("withhold on unanimity, else expose") replays to +1.25 pp on crosscap240 and **−0.39 pp** on
hard366 — mean +0.4 pp.

Across all 280 pools (class shares computed from Stage A banks, sanity-pinned to reproduce the
named pools' W counts 18/22/19 exactly): the oracle bound u_W × 15.7 pp clears the 2 pp bar in
**2 of 280 pools** (2.44 and 2.02 pp, both weak-member pools nobody would deploy). Medians: 1.32 pp
(crosscap240), 0.94 pp (hard366).

## 2. A1 — the "empirical heart" — is broken at birth

delta_W on the only cells where it is measurable: **−18.6 pp on crosscap240** (solo 22/59 vs judge
11/59) and **exactly 0.0 pp on hard366** (solo 2/11 vs judge 2/11). The pooled −15.7 pp is one
suite's effect. At n_W = 3–22 per pool, per-pool CIs span ±25–50 pp: the law is simultaneously
contradicted across suites and unfalsifiable within pools. The 280-pool enumeration does not help —
pools share tasks, so W events are pseudo-replicated; the effective sample is the ~30–70 distinct
all-wrong tasks per suite, and growing it requires harder *tasks*, not more pools or more money.

## 3. The flagship class is nearly empty, and the docs' key assumption is reversed

The framework assumed "W_cons carries most of the mass." Measured: **W_scat dominates in 100% of
crosscap240 pools** (mean u_Wcons 1.0% vs u_Wscat 7.8%) and 91% of hard366 pools. The
"suspicious unanimity" threshold (Cor 2.1) governs a ~1% class; its cons-only oracle bound never
exceeds 0.6 pp in any of 280 pools. Judge episodes exist for only **9 W_cons tasks across all six
cells** — delta on that class is not measurable from existing data, and buying hard366 coverage
(~580 episodes, ~$13) cannot fix the class being rare.

Further corrections to the docs' constants, from the real artifacts: pooled delta_R is **+1.235 pp**
(322→318 of 324; the +1.9 pp figure assumes the judge is perfect on R — it misses 2). The threshold
is therefore **0.927, not 0.89**, with delta-method 95% CI **[0.82, 1.0]** — "never expose any
unanimous pattern" is inside the interval. The Prop 3 certificate's quoted 0.31 pp half-width omits
the dominant term: SE(delta_W) = 7.3 pp contributes ±0.72 pp at u_W = 0.05, so the certified
quantity G ≈ 0.79 pp has CI (0.07, 1.50) — an honest certificate outputs ABSTAIN nearly everywhere.
The escape identity's algebra is correct under within-class ignorability, but the gate conditions on
the very pattern that predicts the judge's within-class behaviour, so the clean product form is an
approximation needing a two-covariance remainder, not an identity.

## 4. The step-0 novelty gate: pass, with demotions

Fifteen-plus papers fetched and verified in-session (none from memory). Per claim:

| claim | status |
|---|---|
| 1. Per-instance gating of whether an aggregator *sees* peer answers | **Unoccupied** — but must be framed as an instantiation of advice-conditional learning-to-defer ([2603.14324](https://arxiv.org/abs/2603.14324) formalizes same-expert-with/without-advice as an action space) and distinguished by name from ARMOR-MAD ([2606.13197](https://arxiv.org/abs/2606.13197), agreement-gated debate — D-044's cascade logic), Minority Sentinel ([2606.29270](https://arxiv.org/abs/2606.29270), output override), DOWN ([2504.05047](https://arxiv.org/abs/2504.05047)), ABC ([2407.02348](https://arxiv.org/abs/2407.02348)) |
| 2. A1 composition law | Novelty untouched by any shelf — but empirically broken (§2); Lemma 1's algebra is Kuncheva 2003 |
| 3. "Suspicious unanimity" threshold | **Demoted**: the suspicion belongs to Gunn et al. 2016 ([1601.00900](https://arxiv.org/abs/1601.00900)), the empirical premise to [2607.08065](https://arxiv.org/abs/2607.08065) (48% of high-agreement GPQA entries wrong); only the specific threshold survives, and §3 shows it is statistically unstable |
| 4. Escape identity | **Demoted to standard machinery**: segment = ROCCH randomized interpolation (Provost–Fawcett); escape = Youden's J re-expressed; conditional-policy escape = Hardt et al. 2016 geometry; the qualitative observation is already in [2608.11247](https://arxiv.org/abs/2608.11247) ("a point above the line requires information from outside the exchange"). No prior statement of the formula found — because it is one line of textbook decision theory |
| 5. EXPOSE/WITHHOLD/ABSTAIN certificate | Survives as specialization only — it would be the **third** CI-certificate in this space, after RouteGuard (2608.07583) and [2606.27288](https://arxiv.org/abs/2606.27288), which is real (verified: 67 models; Prop 1 ceiling Acc ≤ 1−β for selection policies; Prop 3 pairwise-marginals impossibility; ships its own Clopper–Pearson certificate) |

The feared killer is clean: **[2606.01637](https://arxiv.org/html/2606.01637)'s mitigation section
tests only two uniform interventions (CoT, reflect-then-revise), both fail, and its discussion
recommends content verification — never per-instance exposure control.** The fourth time this paper
was checked against a proposal, it did not close one. The space is genuinely open; the prize on this
substrate is what is not there.

## 5. What survives, and the one honest pivot

- The **280-pool class-share sheet** is computed, pinned, and reusable ($0).
- The measured fact that scattered-wrong dominates consensus-wrong is real and small.
- The verified literature map above is a durable asset for any future proposal in this space.
- **The pivot, if the gate idea is to live:** its binding constraint is that u_W is 2–8% and not
  manipulable on a symmetric multiple-choice substrate. The repo already contains a substrate where
  u_W is a *design variable*: the distributed-information condition (D-010/D-015,
  `mas_harness/tasks/distributed.py`), in which a unique evidence-holder makes "the majority is
  provably wrong" common by construction. Exposure gating there has stakes bounded by design, not
  by benchmark accident. That direction would need its own step-0 gate before a line is written.

## 6. Implementation-plan corrections, recorded in case any part is reused

The plan was audited against the tree: solo bank is effectively complete (crosscap240 240/240,
hard366 365/366, abstentions scored wrong per D-011/D-019); 1,174 free judge+solo gate-ladder pairs
exist across the six cells; pool descriptors already carry double-fault and distractor
concentration. Corrections: the W_cons/W_scat split must use the equivalence machinery
(`tasks/adapters.py` evaluators, `sharing_null.build_task_spaces`), not
`analysis/discrimination.py`'s raw-string classes; `load_suite()` lives in the non-importable
`scripts/` layer, so composition work should extend `metrics/pool_sweep.py` rather than duplicate
its loader; rename the proposed `frontier.py` (collides with the cost frontier); the P6 alt-draw
exists **only for crosscap240** (hard366's 2,196 duplicate agent-tasks disagree on nothing, so
"every verdict under both draws" is infeasible on one suite); stray judge episodes in `pilot9-b`
and the `*-retry` dirs must be excluded.
