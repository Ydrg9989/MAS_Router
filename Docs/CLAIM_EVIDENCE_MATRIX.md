# Claim–Evidence Matrix

Companion to [`Docs/PAPER_BACKBONE.md`](PAPER_BACKBONE.md). Every figure below was read from the stored
run artefacts in `data/runs/` on 2026-08-10, not transcribed from prose. Locations are given as
code path plus artefact key so any number can be re-derived.

Status vocabulary: supported / partially supported / unsupported / contradicted / pending.

---

## Main claims

| ID | Exact claim | Strength | Scope | Supporting evidence | Location | Counter-evidence / alternatives | Missing evidence | Status | Sections |
|---|---|---|---|---|---|---|---|---|---|
| **C1a** | Under an additive outcome model with strictly increasing link, the per-task-optimal organization is the same for every task, so population oracle headroom is exactly zero | Guarantee | Assumes no interaction term and monotone link | Proposition 1 with proof | [`FRAMEWORK.md` §3.1](FRAMEWORK.md) | None; it is a proof. The assumption is what is arguable, which is why C1b tests it empirically | Nothing | supported | Intro, §4 |
| **C1b** | Observed oracle headroom does not exceed a null that removes agent-by-task interaction while preserving member sharing | Comparative | 6 pool-by-suite cells, 30 organizations each, 200 simulations, headroom measured against the best organization *on test* | Excess over sharp null: `+2.20` (p=0.045), `+1.16` (0.260), `−0.07` (0.585), `−0.23` (0.605), `−0.05` (0.560), `−3.24` (0.965). Bonferroni threshold for 6 cells is 0.0083, so none survives | [`mas_harness/metrics/sharing_null.py`](../mas_harness/metrics/sharing_null.py), [`scripts/check_headroom_shared_members.py`](../scripts/check_headroom_shared_members.py), `data/runs/headroom_null_shared_members.json` → `[suite][pool]["shared_member_null"]["excess_over_null_over_best"]` | `hard366`/`strong4` at p=0.045 is nominally significant and must be reported as such. The independent null gives a *different* per-cell ordering (`+0.02`, `−1.54`, `−2.46`, `+0.44`, `−2.66`, `−1.05`), showing the choice of null matters | Second seed; the interaction likelihood-ratio test | supported | §4, §6-R1 |
| **C1c** | The null is not vacuous: it detects interaction when interaction is planted, and it reproduces the real protocols exactly | Existence | Synthetic four-specialist structure; replay check on recorded episodes | Planted specialisation detected at p<0.05 with excess >5 points; replay agreement with recorded episodes `1.0000` in all six cells | [`tests/test_sharing_null.py`](../tests/test_sharing_null.py) `test_planted_specialisation_is_detected`; `…["shared_member_null"]["replay_agreement_with_recorded_episodes"]` | The power check is synthetic. The *real*-data positive control is weaker: see C3b | A real pool that exceeds the null | supported | §4 |
| **C1d** | The result holds on an external matrix of 134 public agent systems | Systematic | SWE-bench Verified, 240 test tasks, top-K sweep K∈{4,8,16,32,134} | Excess over null: `−1.88`, `−2.95`, `−2.40`, `−2.42`, `−2.65`; p = 0.940–0.970. Observed headroom rises with K (`8.33`→`14.58`) exactly as the null predicts it should | [`scripts/check_headroom_swebench.py`](../scripts/check_headroom_swebench.py), `data/runs/headroom_null_swebench.json` | Uses the **independent** null, because published systems cannot be decomposed into members. This is the conservative direction, so it weakens the test but not the conclusion | A member-decomposable public matrix | partially supported | §6-R1 |
| **C1f** | Headroom is insensitive, not merely inflated: it misses interaction that is present in the same outcome table | Comparative | Same 6 cells, same tables; capability labels are dataset provenance; bootstrap null with 200 simulations | Likelihood-ratio test of \(\gamma_{u,c(x)}=0\). On `crosscap240` all three pools show organization-by-capability interaction at \(p\le0.005\) with excess departures `+6.71`, `+4.21`, `+3.78` pp, while sharp-null headroom excess on those same tables is `−0.23`, `−0.05`, `−3.24` (\(p\) = 0.605, 0.560, 0.965). On `hard366` neither instrument fires (agents \(p=0.164\); organizations \(p\) = 0.692, 0.731) | [`mas_harness/metrics/interaction.py`](../mas_harness/metrics/interaction.py), [`scripts/measure_interaction.py`](../scripts/measure_interaction.py), `data/runs/interaction.json`; [`DECISIONS.md` D-038](../DECISIONS.md) | `hard366`/correlated4 is significant at \(p\le0.005\) with an excess of `+0.26` pp on 10,980 observations — significance without magnitude, and a caution the paper should state rather than hide | A second seed; finer capability labels | supported | §4, §6-R1 |
| **C1e** | Sweeping a linear cost penalty and comparing a routed policy against the swept baseline flatters routing, because the sweep reaches only the convex hull of candidates | Guarantee + existence | Lemma 2 is general; the demonstration is our own six cells | Lemma 2 with proof; regenerated λ-swept best gains `+3.36`, `−0.02`, `+1.06`, `+7.02`, `+3.47`, `+7.99` points, positive in 44–94% of 200 resplits, against budget-matched `−3.15`, `−1.70`, `−2.48`, `−0.48`, `−1.97`, `−3.94` on the same data. Hull diagnostic: of 30 organizations per cell, 7–14 are Pareto-efficient, only 3–6 reachable by any λ, leaving **3–9 Pareto-efficient but invisible** | [`FRAMEWORK.md` §6.1](FRAMEWORK.md), [`scripts/measure_cost_frontier.py`](../scripts/measure_cost_frontier.py), `data/runs/cost_frontier.json` → `retracted_lambda_sweep`, `hull_diagnostic`; [`DECISIONS.md` D-036, D-039](../DECISIONS.md) | The λ result was our own analysis, not a published one. We must not imply a specific paper made this error, only that the instrument is unsound | Nothing blocking; the hull count now carries the argument without the retracted numbers | supported | §4, §6-R3 |
| **C2a** | A leak-free learned outcome model does not beat the best fixed organization | Comparative | 6 cells, 60 resplits, frozen prompt embeddings, all features and baselines fit on calibration only | `q_theta` gain over fixed-best: `+0.33`, `−0.53`, `−0.42`, `+0.08`, `−1.78`, `+0.03` points; ahead in 47%, 22%, 28%, 43%, 13%, 35% of resplits. Shuffled-representation control is worse in every cell (`−0.32` to `−2.80`), so the representation is doing nothing rather than being mis-scaled | [`mas_harness/metrics/routing.py`](../mas_harness/metrics/routing.py), [`scripts/measure_routing.py`](../scripts/measure_routing.py), `data/runs/routing.json` → `[suite]["pools"][pool]["over_splits"]["gain_over_fixed_best"]` | Semantic k-NN gains `+1.40` (77% of splits) on `hard366`/`strong4` and `+1.01` (70%) on `crosscap240`/`strong4`. A crude baseline beating our model needs explaining, and prevents "no router works" phrasing | A stronger model class; more agents per pool | supported | §6-R2 |
| **C2b** | The absence of gain is not a data-volume problem | Systematic | Pooled 569 tasks, 15 domains, calibration swept 10%→70% (≈57→398 tasks), 40 resplits per point | `q_theta` gain stays in `[−1.28, +0.37]` across the sweep with no trend; oracle headroom simultaneously stays at `+4.08` to `+9.72`, so the "prize" is stable while the ability to claim it does not grow | [`scripts/measure_routing_pooled.py`](../scripts/measure_routing_pooled.py), `data/runs/routing_pooled.json` → `["pools"][pool]["curve"]` | A sevenfold range may still be far from the asymptote | Larger suites | supported | §6-R2 |
| **C2c** | A router given ground-truth capability labels beats the best single agent but not whole-pool voting | Comparative | `crosscap240`, 159 test tasks, 8 agents as singleton organizations, per-capability choice made optimal on calibration | Best single / capability router / whole-pool vote / oracle. `strong4`: 0.792 / 0.830 / **0.836** / 0.937. `decorrelated4`: **0.843** / 0.736 / 0.811 / 0.931. `correlated4`: 0.805 / **0.881** / 0.855 / 0.943 | [`scripts/check_headroom_specialists.py`](../scripts/check_headroom_specialists.py) `aggregation_versus_routing`, `data/runs/headroom_null_specialists.json` | **`correlated4` contradicts the clean version**: the router beats voting by 2.5 points there. And in `decorrelated4` the router loses to the best *single agent* by 10.7 points, i.e. per-capability calibration choices generalise badly. Both must be reported | Why the correlated pool is the one where routing helps | partially supported | §6-R2 |
| **C2d** | Under a budget-matched comparison routing loses at unconstrained budgets | Comparative | 6 cells, resplits, costs repriced from token buckets against the pricing snapshot | Routed minus global at unconstrained budget: `−3.15` (ahead in 2% of resplits), `−1.70` (9%), `−2.48` (8%), `−0.48` (29%), `−1.97` (11%), `−3.94` (7%) | `data/runs/cost_frontier.json` → `unlimited_budget_gain_pp`; [`DECISIONS.md` D-036](../DECISIONS.md) | **At the tightest budgets routing wins** in all three `crosscap240` cells: `+4.05` (81%), `+2.68` (89%), `+13.91` (100%). We read this as buying a cheaper organization on cheap-to-serve domains, which is arbitrage over prices rather than matching organizations to task demands — but that reading is an interpretation, not a measurement | An analysis separating price arbitrage from capability matching, e.g. re-running with flattened prices | partially supported | §6-R3 |
| **C3a** | These agents differ in overall strength and in degradation rate rather than in what they are suited to | Association | 8 agents, 4 capabilities, `crosscap240`, recomputed 2026-08-10 | 7 of 8 peak on code reasoning, 1 on competition maths, **none** on theory of mind or graduate science. Spread ranges from 0.160 (`deepseek32`: 0.850/0.690/0.800/0.800) to 0.833 (`grok43`: 0.967 code, 0.133 theory of mind) | [`scripts/check_headroom_specialists.py`](../scripts/check_headroom_specialists.py) `accuracy_by_domain`; **printed to stdout, not stored** — see provenance flag P2 | 4 capabilities is a coarse partition; a finer one might reveal crossing. Note `grok43` vs `deepseek32` *is* a genuine rank reversal, so the claim is about the dominant pattern, not universality | Finer capability labels; more agent families | supported | §6-R4 |
| **C3b** | Even a pool selected specifically for disjointness shows no excess headroom | Existence (falsification) | `disjoint4` = best agent per capability chosen on calibration; 159 test tasks, 300 simulations | `disjoint4` excess over null `−2.16`, p=0.883. Comparators: `generalist4` `−0.83` (p=0.723), `all8` `−0.80` (p=0.690), and even `all8` with oracle 0.981 against best single 0.843 shows no excess | `data/runs/headroom_null_specialists.json` | The pool is drawn from 8 models on one provider. A genuinely disjoint pool may require fine-tuned or tool-specialised agents, which we did not test | A tool-specialised or fine-tuned pool | supported | §6-R4 |
| **C3c** | Aggregation is a substitute for routing: voting collects the *exploitable* part of the crossing interaction without knowing which tasks are which | Mechanism | Same 3 pools, `crosscap240` | Voting is at or above the capability router in 2 of 3 pools while requiring no task representation; and voting exceeds the best single agent in 2 of 3 (`strong4` 0.836 vs 0.792, `correlated4` 0.855 vs 0.805) | C2c row | In `decorrelated4` voting is *below* the best single agent (0.811 vs 0.843), so aggregation is not free either. And C1f refutes the stronger version of this claim: interaction survives aggregation into organizations at \(p\le0.005\), so "voting removes the interaction" is false — only "voting removes the part worth routing on" is supportable | A decomposition of when voting beats its best member | partially supported | §6-R4, Discussion |

---

## Claim-strength audit

Wording that the evidence does **not** support, and the wording it does:

| Tempting | Problem | Defensible |
|---|---|---|
| "There is no agent-by-task interaction" | Refuted by our own likelihood-ratio test at \(p\le0.005\) (C1f). This sentence must not appear anywhere | "Observed headroom does not exceed what an interaction-free process produces at matched marginals, on tables that do contain interaction" |
| "Aggregation destroys the interaction" | Also refuted by C1f: it is significant at the organization level, not only the agent level | "Aggregation absorbs the *exploitable* part of the interaction" |
| "Routing does not work" | Three dissenting cells (C2a, C2c, C2d counter-evidence) | "Per-task selection did not reliably beat committing to one organization in this family" |
| "Oracle headroom is meaningless" | It is a valid upper bound; it is uninformative *as motivation* | "Oracle headroom is not evidence of routable structure" |
| "We beat published routers" | No reimplementation | "We test the premise those systems are built on" |
| "Cost-aware routing is unsound" | Lemma 2 concerns the *comparison instrument*, not cost-aware routing itself | "Comparing against a λ-swept baseline is unsound; use budget matching" |

---

## Provenance flags

Recorded rather than silently reconciled, per the skill's rule on preserving uncertainty.

- **P1 — CLOSED, and the closure is itself a finding.** The λ figures had no surviving artefact and the
  two records disagreed: [`FRAMEWORK.md` §6.1](FRAMEWORK.md) said `+2.6` to `+16.6` in 86–100% of
  resplits, [`DECISIONS.md` D-036](../DECISIONS.md) said `+4` to `+16` at p≤0.006. A faithful
  re-implementation reproduces **neither** (`−0.02` to `+7.99`, positive in 44–94%). Both historical
  ranges are retired; the paper cites the regenerated numbers, which have an artefact behind them
  (`retracted_lambda_sweep` in `data/runs/cost_frontier.json`). The qualitative artefact is unaffected —
  the sign still flips against budget matching — and the hull diagnostic added alongside it now carries
  the argument without depending on any magnitude. See D-039.
- **P2 — CLOSED.** `accuracy_by_capability` is written into
  `data/runs/headroom_null_specialists.json` with all-task and calibration-only variants, peak
  capability and spread. Values reproduce the earlier recomputation and FRAMEWORK §5.1 exactly.

## Evidence gaps blocking a claim

1. ~~Interaction likelihood-ratio test.~~ **Run, D-038.** It closed the gap and produced C1f, the
   sharpest row in this matrix. It also forced a correction to C3c: aggregation does not destroy the
   interaction, it absorbs the exploitable part.
2. **A second seed.** Every cell is one seed. Cheap for the two free protocols via replay; the priced
   protocols would need new spend.
3. **Explanation for `correlated4`** being the pool where capability routing helps (C2c). Currently an
   unexplained inversion sitting inside a central claim, and now doubly interesting because it is also
   the one `hard366` cell with significant organization-level interaction (C1f).
4. **Price-flattened budget rerun** to separate arbitrage from capability matching (C2d).
5. **Member-decomposable public matrix**, to upgrade C1d from the conservative null.

---

## Claim wording decisions

- "Organization" = coalition × protocol. Fixed once, used everywhere; `DECISIONS.md` also uses
  "configuration", which must be normalised before drafting.
- "Headroom" always means per-task maximum minus the accuracy of the best **single organization
  measured on the same test tasks**. The calibration-picked variant is retired
  ([`DECISIONS.md` D-037](../DECISIONS.md)) because it conflates interaction with winner's curse; it must
  not reappear in the paper.
- "Null" without qualification means the member-sharing null. The independent null is always named as
  such, and reported only where the sharp one is unavailable (C1d).
- Report percentage points as `pp` and keep two decimals, matching the artefacts.
