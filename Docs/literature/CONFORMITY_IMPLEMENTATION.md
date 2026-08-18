<!-- doc-meta
type:          living
lifecycle:     update-in-place — implementation plan, not a result
last-verified: 2026-08-14
evidence-base: none; design only. Companion to CONFORMITY_PROPOSAL.md
-->

# Implementation plan: the competence-label arms

Companion to [`CONFORMITY_PROPOSAL.md`](CONFORMITY_PROPOSAL.md). Nothing here has been run.

---

## 1. The measurement is adoption, not accuracy

The obvious analysis — compare arm accuracies — is the weak one. Accuracy gives **one observation
per task** (~475 per arm), the effects are a few points, and D-045's own numbers showed how easily
that is swamped.

The strong analysis asks **whose answer the judge adopted**. For each episode and each member:

```
adopted_i = 1[ final_answer  ≡  member_i's banked answer ]      (task's own equivalence relation)
```

That is **475 tasks × 4 members ≈ 1,900 observations per arm**, and it measures the mechanism
directly rather than through its effect on correctness. Three outcomes per episode, all informative:
the judge adopts a member, adopts the majority answer, or **writes something none of them said** —
the last being D-044's rescue behaviour, now measurable as a rate that labels might move.

## 2. Why arm C is necessary — the identification argument

This is the part to get right, and it is not merely a deception check.

The model to fit, pooled over arms:

```
P(adopt member i)  ~  advertised_competence_i  +  true_competence_i  +  is_majority_i  +  position_i
```

- In **arm A** neither competence term is visible.
- In **arm B** advertised and true competence are **perfectly collinear** — the label *is* the truth.
  Fitted on B alone, the two coefficients are not separately identifiable. Arm B by itself cannot
  distinguish authority-following from evidence-weighting.
- In **arm C** they are **anti-correlated by construction**.

**Pooling B and C breaks the collinearity and identifies both coefficients separately.** That is the
whole design. Arm C is not an add-on; without it there is no experiment.

Reading the result:

| `advertised` coefficient | `true` coefficient | conclusion |
|---|---|---|
| large | ≈ 0 | **authority-following** — the model reads the label, not the evidence |
| ≈ 0 | large | evidence-weighting — labels are inert, the answers carry it |
| both large | — | partial calibration; report the ratio |
| both ≈ 0 | — | conformity is majority-driven only, consistent with [2607.05545](https://arxiv.org/html/2607.05545). **Kill condition.** |

## 3. Design decisions, fixed now

**The label is global calibration accuracy**, not per-domain. It is constant per member across a
suite, which keeps interpretation clean and avoids a domain confound, and it is already plumbed:
`ProtocolContext.competence` carries exactly this mapping and `tally()` already consumes it. A
per-domain variant is a follow-up if the primary moves, not a first cut.

**Arm C reverses the competence ranking.** Deterministic, no RNG, maximally informative: the
strongest member is advertised as weakest and vice versa. Documented in the protocol description so
it cannot be mistaken for a bug.

**Only the label moves.** Answers, order, task, seed and every other member are byte-identical across
arms. Arm C changes the annotation and nothing else.

**New protocol ids, same run directory.** `judge_labelled` and `judge_inverted` produce distinct
episode keys `(task, pool, protocol, coalition, seed, intervention)`, so they append to the existing
runs and `--no-resume` semantics keep working. No new run directory, no re-banking.

## 4. Files

| file | change | notes |
|---|---|---|
| `mas_harness/protocols/base.py` | add `competence_labels: Mapping[int, str] \| None = None` to `format_peer_answers`; when present, append to the member label | **Default `None` must render byte-identically to today.** A regression test pins this, because every existing protocol shares this function |
| `mas_harness/protocols/conformity.py` | **new.** Register `judge_labelled` and `judge_inverted` | Delegate to a shared helper that takes a label-builder; the two protocols differ in one function |
| `mas_harness/metrics/adoption.py` | **new.** `adopted_member()` using the task evaluator's `equivalent()`; assemble the per-member design matrix; fit the pooled logistic model | Reuse `build_task_spaces`'s equivalence-class approach and carry its transitivity caveat |
| `scripts/measure_conformity.py` | **new.** Driver: build labels, run arms, fit the model, apply the pre-registered thresholds | Mirror `measure_judge_replication.py`'s shape |
| `tests/test_conformity.py` | **new.** See §6 | |
| `Docs/preregistrations/2026-08-XX-conformity.md` | **new, frozen before running** | Predictions from `CONFORMITY_PROPOSAL.md` §5 plus the coefficient table above |

Everything else — banking, pricing, resume, discrimination classes, episode records — is untouched.

## 5. Sequence

| step | what | cost | gate |
|---|---|---|---|
| 0 | Re-run the novelty check on *this exact question* | $0 | if taken, stop |
| 1 | **Prompt pilot**: 30 tasks, one pool, arms B and C | ~$1 | does the judge's output even reference the labels? If it ignores them entirely, reconsider the label format before spending more |
| 2 | `crosscap240`, 3 pools, discriminating subsets, arms B and C (~950 calls) | ~$14 | the pooled model must show a non-zero coefficient on *something*, or stop |
| 3 | `hard366` (~1,040 calls) **and a second aggregator model** | ~$30 | one model is not a claim about LLMs |
| 4 | Pool-composition sweep over more of the 280 pools | ~$60–100 | only if P4 shows structure |

Rate from the priced run: **$0.0144 per judge episode** (2,365 episodes for $34.16). Steps 1–3 are
**under $50**; the whole programme is under $150 against $139.78 spent of ~€3,000.

**Step 1 is not optional.** The entire study rests on the judge attending to a short annotation in a
long prompt. Thirty tasks will show whether it does.

## 6. Tests that must exist before any spend

1. **Regression.** `format_peer_answers` with `competence_labels=None` returns byte-identical output
   to the current implementation, on a fixture covering anonymised, named, and answer-only modes.
   Every existing protocol depends on this.
2. **Inversion.** The arm-C label map is a true reversal of the arm-B map: the argmax of one is the
   argmin of the other, and the multiset of labels is identical between arms.
3. **Only the label differs.** Rendering the same bank under B and C differs *only* in the annotation
   substrings — assert equality after stripping them.
4. **Adoption matching honours equivalence.** Two textually different but equivalent answers count as
   the same adoption; a textually similar but inequivalent one does not.
5. **Identification.** On synthetic data where adoption is generated purely from the *advertised*
   label, the fitted model recovers a large advertised coefficient and ≈ 0 true coefficient — and the
   reverse for data generated from true competence. Without this the null is uninterpretable.
6. **Power.** On synthetic data with a planted 5 pp adoption shift, the design detects it at n≈1,900.
   If it cannot, the study is underpowered and step 2 should not run.

Tests 5 and 6 are the analogue of the planted-specialists check in `test_pool_sweep.py`: they make a
null result a statement about the data rather than about the instrument.

## 7. Known risks

1. **The judge may ignore the labels.** Most likely outcome, and predicted by
   [2607.05545](https://arxiv.org/html/2607.05545). Step 1 detects it for $1.
2. **Prompt-format sensitivity.** A result that holds for one annotation phrasing and not another is
   a finding about prompts. Pilot at least two phrasings in step 1 and report both.
3. **D-028 non-termination** (~4% for this aggregator) is identical across arms and cancels in the
   contrast, but must be reported per arm.
4. **Answer-draw non-determinism** (D-040 item 5): the *members'* answers are banked and fixed, so
   they are identical across arms. Only the judge call is re-elicited. This design is therefore
   *less* exposed to that threat than D-043 was.
5. **One provider.** Step 3 is not optional.
