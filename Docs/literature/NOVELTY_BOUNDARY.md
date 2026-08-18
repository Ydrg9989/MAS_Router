<!-- doc-meta
type:          living
lifecycle:     update-in-place
last-verified: 2026-08-11 (⚠️ superseded 2026-08-14 — see below)
evidence-base: external; verified by direct reading 2026-08-11
-->

# Novelty boundary

> ⚠️ **Superseded 2026-08-14 by [`ENSEMBLING_NOVELTY.md`](ENSEMBLING_NOVELTY.md).**
>
> This check searched the *measurement-audit / routing* shelf and found one paper. It missed four
> that close the project's claims outright, because it was scoped to the question the project started
> with rather than the findings it ended up with — which were **ensembling and conformity**, not
> routing. Read it as the record of what was believed on 2026-08-11, and read `ENSEMBLING_NOVELTY.md`
> for what is actually true.

Why this file exists: [`Delegation_MAS_Literature_Review_fixed.md`](LITERATURE_REVIEW.md)
surveys **routing methods**. The paper this project is now writing is a **measurement-audit**
paper, and that is a different literature. This file records the boundary against the
audit / psychometrics / ensemble-diagnostics shelf, checked on 2026-08-11.

Verdict vocabulary: **collision** (overlaps a claim we intend to make) / **adjacent** (near, must
be cited and differentiated) / **foil** (near, and its limitations are our opening) /
**corroboration** (independent support for something we claim).

---

## 1. The one that could have killed the paper

**"Are Diversity Metrics Measuring Diversity? A Capability-Controlled Audit of Majority-Vote Gain
in LLM Ensembles"** — arXiv 2607.20768, July 2026.
**Verdict: corroboration + foil. Not a collision.**

Read in full because it was the closest thing to C1b/C1c. What it does: 30 models on MMLU-Pro
(356 items) and 29 on TruthfulQA (338 items), **all exhaustive size-2–4 subsets — 31,900
ensembles** — asking whether diversity metrics predict majority-vote gain after controlling for
member capability.

Why it does not collide:

| Dimension | 2607.20768 | This project |
|---|---|---|
| Unit | ensembles of single models under plurality vote | organizations = coalition × protocol |
| Control | partial Spearman, regressing out best/mean member accuracy | matched null that removes agent×task interaction while preserving member sharing |
| Structure | correlational; **no** IRT, factor structure, or matrix rank | the central measurement |
| Routing | **excluded by scope** | the object of study |
| Headroom vs null | descriptive only | tested |

Their own scope sentence: *"we audit that classical intuition rather than learned aggregators,
routers, or judges."* That is our territory, excluded by name.

**Three things in it that help us, and must be cited as such:**

1. **An independent replication of the headroom illusion at n = 31,900.** *"oracle gain is
   positive in 100% of subsets, yet simple voting beats the strongest member in only 9.98%."*
   This is the phenomenon `check_oracle_headroom.py` and D-034 describe, observed at a scale we
   cannot reach — and the summary is explicit that **they do not formally test it against a
   null**. Our `sharing_null.py` is the missing instrument for a gap somebody else has now
   documented publicly.
2. **They hit the member-sharing problem and do not solve it.** Their 31,900 subsets are
   overlapping, *"a design that trades independence for coverage."* That is precisely the
   correlation `FRAMEWORK.md` §3.4 identifies and the sharp null repairs. This is the strongest
   available argument that the null is a contribution rather than an internal control.
3. **A one-axis result in another vocabulary.** Strict diversity correlates with (1 − mean
   accuracy) at **ρ = +0.991**, and only **1.1–1.5%** of its variance survives capability
   control. "Diversity is mostly capability" is the same claim as "the outcome matrix is
   dominated by one axis", arrived at correlationally. Direction A predicts this.

**Consequence:** their large-n descriptive finding + our null and theory is a better paper than
either alone, and the citation is friendly rather than defensive.

---

## 2. IRT-Router — the foil for Proposition 1′

**"IRT-Router: Effective and Interpretable Multi-LLM Routing via Item Response Theory"** —
ACL 2025 Long, arXiv 2506.01048. **Verdict: foil.**

The closest prior work to the dimensionality framing, and its limitations are the opening:

- **Dimensionality is a hyperparameter, never measured.** *"The Dimension 𝒩 of MIRT-Router and
  NIRT-Router are both set to 25."* Sensitivity analysis sweeps 𝒩 ∈ {5,…,25} as grid search.
  There is no estimate of the *true* latent dimension and no model-selection criterion.
- **No theory of when routing can help.** No result resembling Proposition 1′; no statement that
  unidimensional ability makes the per-query argmax constant.
- **No oracle-headroom analysis and no null.**
- **Single LLMs only:** *"our goal is to assign each query…to the most suitable LLM Mj∈ℳ."* No
  coalitions, no protocols.
- **No voting or ensemble baseline at all.** Baselines are Small/Large LLM, HybridLLM, RouteLLM,
  RouterBench — every one a single-model router.

Scale: 20 LLMs, 12 datasets, 24,430 training queries.

**The positioning sentence this licenses:** the closest prior work fits a *25-dimensional* latent
ability model to justify routing, without measuring whether more than one dimension is present,
without testing the routing gain against a null, and without ever comparing against voting over
the same models.

---

## 3. Observational Scaling Laws — the constraint on how we phrase things

NeurIPS 2024, arXiv 2405.10938. **Verdict: adjacent; constrains the abstract.**

Established: *"language model performance is a function of a low-dimensional capability space."*
~100 public models, 21 families; PC1 ≈ 80% of variance, top 3 ≈ 97%.

**We must not claim "LLM capability is low-dimensional" as a finding.** It is published.
The differentiators, in order of strength:

1. **Unit.** Their PCA is over *aggregate benchmark scores* — one number per model per
   benchmark. Ours is a *per-item binary outcome matrix*. Aggregate scores cannot exhibit
   agent-by-task interaction at all, so their result cannot answer the routing question even in
   principle. **[VERIFY]** confirm the unit from the full text before drafting; the PDF did not
   extract cleanly and this differentiator is load-bearing.
2. **Level.** Nothing in that literature measures dimensionality of **organizations**
   (coalition × protocol). Our two-stage harness is the only apparatus here that can.
3. **Consequence.** They use low-dimensionality as a *predictor* of scaling. Nobody has used it
   as a **decision rule** for whether organizational design can pay.

---

## 4. Remaining entries

| Claim in lit review | Status |
|---|---|
| MasRouter, ACL 2025 Long | ✅ verified — [aclanthology.org/2025.acl-long.757](https://aclanthology.org/2025.acl-long.757/) |
| EvoRoute, ACL 2026 Long | ✅ verified — [aclanthology.org/2026.acl-long.1771](https://aclanthology.org/2026.acl-long.1771/) |
| RouterHGC | ✅ verified — heterogeneous-graph contrastive router for MAS |
| DecoR, ACL 2026 Long | ✅ verified — real title is *"Beyond Query Memorization: LLM Routing with Query Decomposition and Historical Matching"*, arXiv 2605.25558. **Cite by real title, not the acronym.** |
| Agent Psychometrics, COLM 2026 | ✅ vendored in-tree; matrices confirmed on disk |
| **Nash-CredMAS, ACL 2026 Findings** | 🔴 **does not exist under this name.** Nearest real work is *"An Adversary-Resistant Multi-Agent LLM System via Credibility Scoring"* (arXiv 2505.24239, IJCNLP 2025) and *"From Debate to Equilibrium: Belief-Driven Multi-Agent LLM Reasoning via Bayesian Nash Equilibrium"* (arXiv 2506.08292, ICML 2025). The lit-review entry appears to **merge two separate papers into one invented name**. Its §10 content must be re-derived from whichever is actually meant, or the entry dropped. |
| KABB, ReSo, AgentNet, MaAS, FlexRouter, Skill-MoE | ⏳ not re-verified this pass. Given the Nash-CredMAS finding, **every entry must be verified against a real title, venue and arXiv ID before the related-work section is drafted.** |

**Integrity note.** One fabricated entry in a twelve-entry review is a citation risk in its own
right, and it is also a reason not to trust the review's headline verdict — *"'Maintain
historical agent performance and use it for task-conditioned delegation' is no longer sufficient
as the main novelty"* — without re-checking. That verdict is what has been driving the project's
sense that the idea is unoriginal.

---

## 5. The differentiation paragraph

To be adapted into related work. Written before any Step 1–3 experiment, per the plan.

> Two literatures bear on this work. The first builds routers that select a model or a
> multi-agent configuration per query, and the closest of these, IRT-Router, models LLM ability
> with a 25-dimensional item-response model. That dimension is set as a hyperparameter and swept
> by grid search; the true latent dimension is never estimated, the routing gain is never tested
> against a null, and no ensemble or voting baseline appears among the comparisons. The second
> shows that model capability is low-dimensional in aggregate — a single principal component of
> benchmark *scores* explains roughly 80% of variance across a hundred models — and uses this to
> predict scaling, not to decide whether per-query selection is worth building. Neither literature
> measures dimensionality in the per-item outcome matrix where agent-by-task interaction would
> have to live, and neither measures it for *organizations*: coalitions crossed with coordination
> protocols. We do both, and show that the dimension count, rather than oracle headroom, is what
> determines whether organizational selection can pay. A recent capability-controlled audit of
> ensemble diversity reports the phenomenon our theory predicts — oracle gain positive in 100% of
> 31,900 model subsets while plurality voting beats the strongest member in under 10% — but
> reports it descriptively, without a matched null, and over overlapping subsets whose shared
> membership it notes but does not correct. Our null is constructed precisely to preserve that
> shared membership while removing the interaction.

---

## 6. Consequences for the plan

- **Step 0's kill risk did not fire.** Direction A survives, with sharper positioning than
  before: IRT-Router is the foil, ObsScaling is the constraint, 2607.20768 is corroboration.
- **Prop 1′ is unstated in the nearest prior work**, confirmed by direct reading of IRT-Router.
- **Two new required actions**, neither in the original plan:
  1. Verify the remaining six lit-review entries against real titles/venues/IDs.
  2. Confirm the ObsScaling PCA unit from full text — the "aggregate scores vs per-item
     outcomes" distinction is load-bearing for the abstract.
- **The `hard366` null result gains value.** 2607.20768's audit runs on MMLU-Pro and TruthfulQA,
  both multiple-choice; our contrast between a homogeneous suite with no detectable interaction
  and a cross-capability suite carrying interaction at p ≤ 0.005 is a manipulation their design
  cannot perform.
