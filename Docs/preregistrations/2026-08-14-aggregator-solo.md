<!-- doc-meta
type:          frozen
lifecycle:     FROZEN — never edit after writing; results go to EXPERIMENT_LOG.md + DECISIONS.md
last-verified: 2026-08-14
evidence-base: not yet run
-->

# Pre-registration: is the judge aggregating, or is it just a better model?

Written before the run. This is the control that decides what the project's only positive result
*is*, so its outcomes are named in advance — including the one that would kill the result.

Status: **not yet run.** Locked 2026-08-14.

---

## 1. Why this is the decisive experiment

`independent_judge` beats the calibration-chosen best aggregation rule in six pools of six across two
suites (D-043), and beats whole-pool voting by +3.8 / +8.0 / +4.6 pp on full suites (D-044). The
protocol has `anthropic/claude-sonnet-5` read four banked answers and produce a final one.

D-044 then showed it solves **18.6% of tasks on which every member was wrong** — 28% of its entire
advantage over voting. **No selection rule can do that.** So the judge contributes its own knowledge,
and the obvious alternative explanation for the whole result is that this model is simply better than
the pool members.

That model has never been measured answering alone, because D-024 deliberately kept it out of the
pools so the pool contrast would not be confounded with judge identity. Correct at the time; it is
why the confound is open now.

## 2. What is run

Stage A only. One agent — `claude-sonnet-5` with the settings copied verbatim from the `aggregator:`
block of `strong4.yaml` — banked on **crosscap240 (240 tasks)** and **hard366 (366 tasks)**, run id
`aggregator-solo`, pool [`configs/pools/aggregator_solo.yaml`](../../configs/pools/aggregator_solo.yaml).

606 calls. No Stage B, no coalitions. Voting, judge and member outcomes already exist and are not
re-elicited, so every comparison below is exactly paired on task id.

**Estimated cost $8–15.** Project total before: $127.69 of ~€3,000.

## 3. Predictions, and what each outcome means

Let `solo` be this model's accuracy and `judge` the `independent_judge` accuracy on the same tasks.

| # | Quantity | Predicted | Interpretation if it holds |
|---|---|---|---|
| **S1** | `solo` minus `judge`, full suite | −2 to +2 pp | The judge's advantage over voting **is** this model's competence. The positive result is "add a stronger model", not a multi-agent finding |
| **S2** | `solo` on **UNANIMOUS_WRONG** tasks | ≈ 0.186, matching the judge's rescue rate | The rescues are pure solo ability; reading the members adds nothing there |
| **S3** | `solo` on **UNANIMOUS_CORRECT** tasks | < 1.000 | Deferring to a correct consensus is worth something the model does not have alone — the one place aggregation demonstrably adds value |
| **S4** | `solo` minus best single pool member | > 0 | The model is stronger than the pool, which is the premise of the whole confound |

**The result survives only if S1 is clearly negative** — the judge beating the model that *is* the
judge means reading peer answers adds something. Threshold, fixed here: **judge − solo ≥ +2.0 pp on
both suites**, with S3 < 1.000 supplying the mechanism.

**The result dies if S1 is near zero or positive.** In that case D-043 and D-044 describe a strong
model with extra steps, and this project has no positive result about multi-agent systems.

## 4. The decomposition this makes possible

Beyond the verdict, the run partitions the judge's +3.8 to +8.0 pp into three sources, on tasks
classified by what the members did:

- **UNANIMOUS_CORRECT** — judge ≈ vote ≈ 1.000. If `solo` < 1.000 here, *consensus deference* is a
  real contribution and its size is `1.000 − solo` weighted by class frequency.
- **UNANIMOUS_WRONG** — voting scores 0 by construction. Judge scores 0.186. If `solo` ≈ 0.186 the
  contribution is *independent answering*; if `solo` < 0.186 then reading four wrong answers still
  helped, which would be a genuinely surprising finding.
- **DISCRIMINATING** — members split. The residual after the first two is *selection among members*,
  the only part that is aggregation in the ordinary sense.

Those three add to the whole effect, so the paper's sentence about what a judge does can be written
from measurement rather than assertion, whichever way S1 falls.

## 5. Controls

- Same provider, model, temperature and `max_tokens` as the aggregator block. Same Stage A prompt as
  every other banked agent.
- **Commit rate reported alongside accuracy.** D-028 has this model emitting nothing on ~4% of
  aggregator calls, scored wrong by D-019. If it happens here the solo arm is handicapped — but the
  judge carries the identical handicap in every D-043/D-044 figure, so the comparison remains
  like-for-like. Both scorings are reported.
- Every comparison is paired on task id against outcomes already banked.

## 6. Why no outcome wastes the money

- **S1 negative** → the positive result is real and now has a mechanism, decomposed three ways.
- **S1 near zero** → the project has no positive result, which is worth $8–15 to learn *before*
  writing a paper rather than after a reviewer asks.
- **S3 = 1.000** → deferring to consensus adds nothing, which sharpens the negative and says
  something clean about when aggregation is pointless.
- **S2 far below the judge's 0.186** → reading four *wrong* answers improves the model, which would
  be the most interesting outcome available and would reopen the aggregation framing entirely.
