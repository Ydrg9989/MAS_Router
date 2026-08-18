<!-- doc-meta
type:          living
lifecycle:     update-in-place
last-verified: 2026-08-14
evidence-base: external; every entry verified by fetching the arXiv record, not from memory
-->

# The ensembling and conformity literature, and what it leaves of this project

Written 2026-08-14, after D-045. `LITERATURE_REVIEW.md` and `RW_router.md` both cover **routing**.
This project's actual findings — a judge reading peer answers, and what that does to a strong model —
belong to **ensembling** and **conformity**, which neither document touches. This is that check.

**Every entry below was verified by fetching the arXiv record.** The project has been burned once by
a fabricated citation (`Nash-CredMAS`, see `NOVELTY_BOUNDARY.md`), so nothing here is from memory.

---

## 1. The verdict, up front

**Every headline claim this project holds has already been published, most of it in the last four
months, generally at larger scale.**

| Our claim | Prior work | Their result |
|---|---|---|
| **C1** Oracle headroom is not evidence; compare to a null, not to zero | **How Much of the Routing Gap Is Real?** (Chen, [2607.03436](https://arxiv.org/pdf/2607.03436), Jul 2026) | Decomposes the router-to-oracle gap into *reproducible specialist advantage* and *single-draw label noise*; argues it must be evaluated against a null baseline rather than zero |
| **C5a** Re-running the same seed is a different draw, and it inflates the oracle | Same paper | "the single-draw oracle is an upward-biased estimate of any reproducible ceiling" |
| **C1'/C3** Complementarity exists but is not realisable; headroom does not predict gain | **RouteGuard** (Sun & Yang, [2608.07583](https://arxiv.org/html/2608.07583), 5 Aug 2026) | Proves best achievable routing gain equals gate informativeness Phi exactly; **"+9.6 pp oracle headroom yielded +0.0 pp routing gain — the gate was uninformative"**. Ships a finite-sample pre-deployment certificate. RouterBench, 11 models, 36,497 prompts |
| The pre-flight "can routing help here?" test proposed on 2026-08-14 | RouteGuard | Exactly this, with a Bernstein bracket and a matching Le Cam lower bound |
| Voting rarely converts complementarity into a win | **Are Diversity Metrics Measuring Diversity?** ([2607.20768](https://arxiv.org/html/2607.20768v1)) | Voting wins in **9.98%** of canonical size-3 subsets |
| **D-045 S1** The judge is largely the model; use the strong model alone | **Rethinking Mixture-of-Agents** (Li et al., Princeton, [2502.00674](https://arxiv.org/abs/2502.00674), Feb 2025) | Self-MoA — aggregating from the single top model — beats standard MoA by 6.6% on AlpacaEval 2.0, 3.8% across MMLU/CRUX/MATH. Identifies the quality-versus-diversity trade-off |
| Same, with cost | **The Cost of Consensus** (Bertalanic & Fortuna, [2605.00914](https://arxiv.org/pdf/2605.00914), Apr 2026) | Isolated self-correction beats unguided debate at **2.1-3.4x fewer tokens**; modal sycophancy to 85.5%; oracle gap to 32.3 pp |
| **D-045 S2/S3** Wrong peers harm more than correct peers help | **Easier to Mislead Than to Correct** (Qu, Fu & Hu, [2606.01637](https://arxiv.org/html/2606.01637), Jun 2026) | All-wrong peers raise harmful revision **15.6% to 62.9% (+47.3 pp)**; all-correct peers raise beneficial revision 32.7% to 51.5% (+18.8 pp). Asymmetry **5x** (OR 28.5 vs 5.2) |

### The closest paper, in detail

[2606.01637](https://arxiv.org/html/2606.01637) is not merely adjacent. It shares our **setting**
(one-shot: answer independently, see peers simultaneously, then decide — not iterative debate), our
**control** (the same model answering alone, within-subjects), our **partition** (by whether peers
were all-correct or all-wrong), and our **headline** (the harm is much larger than the benefit). It
runs 4 models x 7 QA datasets x 2,500 instances. D-045 runs 1 aggregator x 2 suites x ~600 tasks.

Our numbers agree with theirs. Solo 0.343 -> judge 0.186 on unanimously-wrong items is their harmful
revision; solo 0.981 -> ~1.000 on unanimously-correct items is their beneficial revision; our -15.7 pp
against +1.9 pp is their +47.3 against +18.8. **We independently reproduced a published result at one
quarter of the scale, two months later.**

## 2. Why the 2026-08-11 novelty check missed all of this

`NOVELTY_BOUNDARY.md` searched the measurement-audit / psychometrics / ensemble-diagnostics shelf for
**routing**, and found one paper. Four of the six above predate that check —
[2502.00674](https://arxiv.org/abs/2502.00674) by eighteen months,
[2605.00914](https://arxiv.org/pdf/2605.00914) by four months,
[2606.01637](https://arxiv.org/html/2606.01637) by two,
[2607.03436](https://arxiv.org/pdf/2607.03436) by one.

The check did not fail through carelessness. It failed because **the project believed it was doing
routing research, and its results were actually ensembling and conformity research.** The literature
was scoped to the question we started with rather than to the findings we ended up with. That is a
generalisable lesson: re-scope the novelty check every time the *result* changes shape, not every
time the plan does.

## 3. What is left unoccupied

Stated conservatively. None of it is currently a paper.

1. **The organization axis.** Every paper above routes or ensembles among *models*. None has
   coalition x protocol as the unit, none enumerates 280 pools. RouteGuard's largest pool is 11
   models with a gate; ours is 30 organizations over 4 members, densely counterfactual.
2. **Conformity as a function of *real* pool composition.**
   [2606.01637](https://arxiv.org/html/2606.01637) uses *simulated* peers whose correctness the
   experimenter sets. We have real heterogeneous pools with measured error correlation, and 280 of
   them. "Which pool compositions make aggregation net-harmful?" is a design question none of these
   papers asks, because none of them varies the pool.
3. **Supervision efficiency** (D-041 RQ3: dense counterfactual grids versus execution logs, crossing
   at 20% of the grid). Nothing found covering it. Also the thinnest of the three.

Each is an increment on an occupied space, not a new space.

## 4. What this does to the project's options

- **The measurement-audit paper is closed.** [2607.03436](https://arxiv.org/pdf/2607.03436) and
  [2608.07583](https://arxiv.org/html/2608.07583) hold C1, C1', C5a and the pre-flight test between
  them, with theory and larger evaluations.
- **The judge paper is closed.** [2502.00674](https://arxiv.org/abs/2502.00674) and
  [2605.00914](https://arxiv.org/pdf/2605.00914) hold S1.
- **The anchoring paper is closed.** [2606.01637](https://arxiv.org/html/2606.01637) holds S2 and S3,
  in our setting, with our control, at four times our scale.

What the project has is a **very good substrate and an unusually disciplined method**, which arrived
independently at conclusions the field reached across four separate papers. That validates the
method. It is not a publication.

## 4b. The follow-up proposal is closed too, by the same paper

`CONFORMITY_PROPOSAL.md` asked whether conformity tracks *real measured* peer competence rather than
advertised competence, and planned three arms: anonymous, truthfully labelled, and inverted labels.
Its own step-0 gate closed it on 2026-08-14.

[2606.01637](https://arxiv.org/html/2606.01637) already attaches authority labels to peers, already
manipulates the label **independently of correctness** — "authority-labeled peers can endorse either
the correct answer or a wrong answer" — and already measures **adoption** rather than accuracy, as
"authority-aligned revision". That is the proposed arms B and C, the identification strategy, and the
dependent variable.

What survives is that their peers are simulated from paraphrase templates while ours would be real
models with measured accuracy, and their label is a role rather than a number. Those are robustness
differences, not contributions.

**Three proposals have now been closed by this same paper**: D-045's decomposition, the anchoring
write-up, and the competence-label study. That concentration is itself the signal — the question this
project keeps arriving at is one that a larger group answered in June.

## 5. Read in full before any further work

1. [2606.01637](https://arxiv.org/html/2606.01637) — closest to D-045. Read first.
2. [2608.07583](https://arxiv.org/html/2608.07583) — closest to D-040/041/042, and it ships the
   certificate this project would have built next.
3. [2607.03436](https://arxiv.org/pdf/2607.03436) — closest to C1 and C5a.
4. [2502.00674](https://arxiv.org/abs/2502.00674) — the MoA correction, and the oldest.
5. [2605.00914](https://arxiv.org/pdf/2605.00914) — the cost argument.
6. [2607.20768](https://arxiv.org/html/2607.20768v1) — already in `NOVELTY_BOUNDARY.md`.
