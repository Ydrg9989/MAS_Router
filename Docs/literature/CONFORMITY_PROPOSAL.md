<!-- doc-meta
type:          living
lifecycle:     update-in-place — this is a proposal, not a result
last-verified: 2026-08-14
evidence-base: gap analysis against ENSEMBLING_NOVELTY.md; no experiment run
-->

# Proposal: does LLM conformity track *real* peer competence, or only advertised competence?

Written 2026-08-14 after `ENSEMBLING_NOVELTY.md` closed every existing claim. This is the one
question in the conformity space that the project's substrate is unusually well suited to, that the
literature has left open, and that has a practical consequence if it resolves either way.

**Status: proposal. Nothing run. Do not cite any number here — there are none.**

---

## 1. What the conformity literature already varies

| Manipulation | Paper |
|---|---|
| Peer **correctness**, set by the experimenter | [Easier to Mislead Than to Correct](https://arxiv.org/html/2606.01637) |
| Peer **labels** ("expert"), stated **confidence**, **majority size** | [It's Not Always Sycophancy: Conformity as a Function of Epistemic Uncertainty](https://arxiv.org/html/2605.27288v1) |
| Whether a **speaker exists at all** | [Most LLM Conformity Needs No Speaker](https://arxiv.org/html/2607.05545) |
| **Homogeneous** agent teams, debate rounds | [The Cost of Consensus](https://arxiv.org/pdf/2605.00914) |
| Conformity **mitigations** and their trade-off | [Resistance-Receptivity Frontier](https://arxiv.org/html/2608.11247) |

Two things are common to all of them. The peers are **simulated, homogeneous, or labelled** —
correctness is assigned by the experimenter, or competence is asserted in the prompt. And the peer
set is **fixed**: nobody varies *who is in the room* as a designed factor.

## 2. The gap

> **Nobody has asked whether LLM conformity tracks peers' *actual, measured* competence, with the
> advertised competence held constant — or whether it responds only to the label and the count.**

The distinction is not cosmetic. A model that defers to a peer *labelled* expert is responding to a
token in its context. A model that defers to a peer that is *genuinely* more accurate is doing
something epistemically correct. These have opposite engineering implications:

- **If conformity tracks reality** → multi-agent systems are already weighting evidence sensibly, and
  the fix for dilution is better pools.
- **If conformity tracks the label only** → every MAS that puts a strong and a weak model in one room
  is mis-weighting evidence, and the fix is architectural: surface measured competence, or weight by
  it, rather than letting a majority of weak members outvote a strong one.

## 3. Why this substrate is unusually good for it

Three assets, none of which the papers above have.

**Real peers with measured competence.** 8–10 models banked on every task, per-domain accuracy from
0.454 to 0.885, error correlation from +0.38 to +0.58, and **280 enumerated pools** with descriptors
(ability spread, double-fault rate, distractor concentration). Peer competence is a *measured
covariate*, not an experimenter's setting.

**Causal control over the peer set.** [`mas_harness/interventions/edits.py`](../../mas_harness/interventions/edits.py)
implements `mask`, `substitute_correct`, `substitute_wrong` and `reorder` as edits to the banked
answers, drawing donor messages from **real banked answers** so substituted peers stay stylistically
in distribution. The task, the seed and the untouched members are byte-identical between arms, so
`do(·)` is exact rather than estimated. Observational conformity studies cannot do this.

**The unlabelled baseline already exists.** `protocols/base.py` anonymises members to positional
labels (`Member 1…4`) by default, and `anonymize` is already a parameter. So D-045's six pools ×
~600 tasks **are** the no-label arm, already paid for. The manipulation is one prompt variant away.

## 4. The design

Three arms over the same tasks, same pools, same banked answers. Only the peer *presentation*
changes.

| arm | peers shown as | tests |
|---|---|---|
| **A — anonymous** | `Member 1…4`, no competence information | **already banked** (D-043/D-045) |
| **B — truthfully labelled** | each member tagged with its *measured* per-domain accuracy | can the model use true competence when given it? |
| **C — inverted labels** | the same answers, with competence tags **permuted** so the weakest member is advertised as strongest | does it follow the label or the evidence? |

**C is the crux.** If behaviour in C follows the (false) label rather than the answers, conformity is
authority-following, not evidence-weighting. If C ≈ A, the labels are inert and the model is doing
something else entirely.

Two further factors, free from the existing grid:

- **Competence spread of the pool** — pools range from 0.16 to 0.83 in member spread. Does dilution
  worsen when a strong member is outnumbered by weak ones? This is the question the 280-pool
  descriptor set exists to answer and it is the practical payoff.
- **Minority-correct items** — the `MINORITY_CORRECT` class is already labelled per task by
  `analysis/discrimination.py`. These are the items where dilution can be observed at all, and they
  are pre-identified rather than searched for after the fact.

## 5. Pre-registered predictions (to be frozen before running)

| # | Quantity | Prediction | Notable if |
|---|---|---|---|
| P1 | Arm B minus arm A | ≈ 0 — true competence labels are not used | ≥ +2 pp, i.e. surfacing competence helps |
| P2 | Arm C minus arm A | negative — inverted labels mislead | ≈ 0, i.e. labels are inert and only the answers matter |
| P3 | \|C − A\| versus \|B − A\| | comparable, since both are label manipulations | asymmetric, which separates authority-following from evidence-weighting |
| P4 | Dilution vs pool ability spread | dilution grows with spread | flat, i.e. it is majority size alone |

**The kill condition, stated now:** if B ≈ C ≈ A on every suite, the labels do nothing, and the study
reduces to a replication of [2606.01637](https://arxiv.org/html/2606.01637). That is a real
possibility and it should end the direction rather than be written around.

## 6. Cost and sequence

| step | cost | gate |
|---|---|---|
| 0. Re-run the novelty check on this exact question | $0, one day | if it is taken, stop here |
| 1. Arms B and C on `crosscap240`, 3 pools, discriminating subsets (~475 tasks × 2) | ~$20 | P2 must move, or stop |
| 2. Extend to `hard366` and a **second aggregator model** | ~$40 | one model is not a claim about LLMs |
| 3. Pool-composition sweep on more of the 280 pools | ~$60–100 | only if P4 shows structure |

Under **$150 total**, against $139.78 spent of ~€3,000.

## 7. Honest risks

1. **The space is moving fast.** [2608.11247](https://arxiv.org/html/2608.11247) is dated 5 August
   2026. Step 0 is not a formality — re-run it immediately before step 1, and again before writing.
2. **A null is likely.** [2607.05545](https://arxiv.org/html/2607.05545) reports that most conformity
   survives removing the speaker entirely, which predicts labels are inert and P2 ≈ 0.
3. **One provider.** Everything here is OpenRouter. Step 2 is not optional.
4. **This is an increment on an occupied space.** It is a well-posed and answerable increment with a
   clear practical consequence — it is not a new field.
