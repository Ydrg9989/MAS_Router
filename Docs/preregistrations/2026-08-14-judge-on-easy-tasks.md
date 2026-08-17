<!-- doc-meta
type:          frozen
lifecycle:     FROZEN — never edit after writing; results go to EXPERIMENT_LOG.md + DECISIONS.md
last-verified: 2026-08-14
evidence-base: not yet run
-->

# Pre-registration: what the judge does where the members already agree

Written before the run. Short, because it tests one thing, but pre-registered because the
interesting outcome is the one that would be easiest to find by looking afterwards.

Status: **not yet run.** Locked 2026-08-14.

---

## 1. The gap this closes

D-020 paid for priced protocols only on each pool's **discriminating** tasks — those where the four
members did not all give the same answer — plus a ~15% control sample. That was correct
cost discipline: on a unanimous task a vote, an expert and a debate all return the same thing.

It leaves three things unmeasured, and D-043's numbers inherit all of them:

1. **Every figure in D-043 is on a hard subset, not a workload.** The judge's +1.12 to +7.69 pp over
   voting is measured on tasks selected *because* the members disagreed. A deployer sees the full
   distribution, in which 37% / 30% / 54% of `crosscap240` is unanimous.
2. **A cascade's saving cannot be computed.** Escalating to the judge only on disagreement saves
   exactly the calls the priced data excluded by construction.
3. **The premise behind skipping them is untested.** A vote returns the members' answer by
   definition; a *judge* reads four answers and writes its own, so it can override all four. Whether
   it does is unknown.

## 2. What is run

`independent_judge` only, on the 245 tasks never priced: 75 / 60 / 110 for `strong4` /
`decorrelated4` / `correlated4`, of which 196 are UNANIMOUS_CORRECT and 49 UNANIMOUS_WRONG. Voting
and expert outcomes on these tasks are already free from the banked answers. Same prompt, same
aggregator, same pools — nothing changes but the task list.

**Estimated cost $3–6.** Project total before: $122.25.

## 3. Predictions and thresholds

| # | Quantity | Predicted | Notable if |
|---|---|---|---|
| **H1** | Judge accuracy on **UNANIMOUS_CORRECT** tasks | ≈ 1.0 — the judge concurs with four identical correct answers | **≤ 0.98**, i.e. it overrides a correct consensus more than rarely. At 196 tasks, 0.98 is four overrides |
| **H2** | Judge accuracy on **UNANIMOUS_WRONG** tasks | ≈ 0 — four identical wrong answers give it nothing to work with | **≥ 0.05**, i.e. it rescues tasks no member solved |
| **H3** | Judge minus vote on the **full suite** | positive but smaller than the subset figure, since unanimous tasks contribute zero difference under H1 | full-suite gain ≤ half the subset gain |
| **H4** | Cascade (vote if unanimous, else judge) against judge-always | equal accuracy, 30–54% fewer judge calls | cascade accuracy **exceeds** judge-always, which requires H1 to fail |

**H1 failing is the interesting outcome and it is named here in advance.** If the judge damages
easy items, the cascade is not merely cheaper — it is *more accurate than the judge alone*, and the
finding is aggregation harming consensus rather than a cost trick. The only current evidence is
`crosscap240/decorrelated4`'s ~12 unanimous controls, where the judge scored 0.857 against voting's
1.000. That is n≈12 and it is why this is being measured rather than asserted.

## 4. Controls

- Voting, expert and oracle outcomes on these tasks come from the existing bank and are **not**
  re-elicited, so the comparison is exactly paired.
- Results are reported per task class (UNANIMOUS_CORRECT, UNANIMOUS_WRONG) separately, never pooled,
  because the two make opposite predictions and pooling them would hide both.
- D-028 dual scoring still applies: any aggregator non-termination is reported both ways.

## 5. Why no outcome wastes the money

- **H1 holds** → the cascade is a clean cost result and every D-043 number gains a workload-level
  restatement, which is what a deployment claim needs.
- **H1 fails** → aggregation damages items a plain vote gets right, which is a mechanism finding and
  connects directly to the expert-dilution work this project sits beside.
- **H2 fires** → the judge contributes knowledge rather than only selecting among members, which
  would change what `independent_judge` is understood to be doing and would bear on the aggregator
  confound in D-043.
