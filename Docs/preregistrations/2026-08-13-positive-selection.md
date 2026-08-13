<!-- doc-meta
type:          frozen
lifecycle:     FROZEN — never edit after writing; results go to EXPERIMENT_LOG.md + DECISIONS.md
last-verified: 2026-08-13
evidence-base: not yet run
-->

# Pre-registration: the positive experiments

Written **before** running. D-041 closed per-task routing. This registers the four experiments that
could support a *positive* claim, with thresholds and a decision rule fixed in advance.

Status: **not yet run.** Locked 2026-08-13, after D-041 and before any arm was executed.

---

## 1. The claim being tested

Everything so far asked *which organization should run this task*. The answer is: the same one every
time. The question that survives is therefore **which one**, and the project has never treated that
as a research question — it has used the calibration argmax as an incumbent baseline without asking
whether the incumbent is any good.

It is not. D-040 measures the calibration argmax losing **2.39 pp** on `crosscap240` and **1.01 pp**
on `hard366` between calibration and test. D-037 established this is the winner's curse rather than
interaction, which matters: **unlike oracle headroom, this gap is real and partly recoverable.**
Shrinking a selected maximum toward the mean is a textbook remedy for exactly this bias, and no
routing paper in `Docs/literature/ROUTING_ARCHITECTURES.md` applies one — they all compare against
"the best model on validation".

So the positive claim is:

> **Choosing an organization better beats choosing one per task, and the calibration argmax is a
> poor way to choose.**

---

## 2. The experiments

### E1 — a better fixed-organization rule (the headline)

For every pool and every stratified resplit, seven rules each choosing **one** organization on
calibration, scored on test:

| rule | what it does |
|---|---|
| `argmax` | the incumbent: highest calibration accuracy |
| `one_se` | the simplest organization within one standard error of the best (already implemented) |
| `shrunk` | argmax of calibration accuracy shrunk toward the family mean by `n/(n+k)` |
| `whole_pool_vote` | the grand coalition's majority vote, chosen with **no calibration at all** |
| `largest_within_se` | among those within one SE, the largest coalition |
| `cross_pool` | fitted on the *other* pools, leave-one-pool-out, from pool descriptors |
| `oracle_fixed` | best organization on test — the attainable ceiling, not a policy |

Run on `crosscap240` (70 pools) and `hard366` (210 pools).

### E2 — price-flattened budget rerun

D-040 found routing winning at the tightest budgets in 97.1% of `crosscap240` pools and only 59.5%
of `hard366` ones, and read that as **priced-by-domain arbitrage** rather than capability matching.
That reading is an interpretation. Re-price every call at one flat rate per token, so no domain is
cheaper to serve than another, and re-run the budget comparison. If the tight-budget win survives
flat prices it is capability matching; if it disappears it is arbitrage.

### E3 — the alternative answer draw

`crosscap240` banked several agents twice and 49 of 959 repeated agent-tasks disagree. Every number
in D-040 and D-041 uses one bank composition. Rebuild from the other and recompute the sweep.

### E4 — interaction protocols, chosen a priori

D-041 found the *best* protocol per pool does not reproduce (split-half agreement 0.00–0.17), but
`independent_judge` fixed in advance beats the calibration-chosen best aggregation rule in 3 of 3
pools (+1.39, +5.98, +0.70). Test every protocol as an a-priori rule over resplits, so the claim is
about a *named, pre-specified* protocol rather than a selected one.

---

## 3. Predictions and thresholds

| # | Quantity | Predicted | Positive result if |
|---|---|---|---|
| **E1a** | Best alternative rule minus `argmax`, mean over pools | > 0 | **≥ +1.0 pp on both suites**, and ahead in ≥ 60% of pools |
| **E1b** | `whole_pool_vote` minus `argmax` | > 0 — the one organizational fact that has always reproduced | ≥ +1.0 pp on both suites |
| **E1c** | `cross_pool` minus `argmax` | > 0 if pool composition predicts the right organization | ≥ +1.0 pp, and beating `one_se` |
| **E2** | Tight-budget routed-minus-global gain, flat prices | falls to ≈ 0 — the D-040 reading is arbitrage | stays ≥ +2.0 pp, i.e. capability matching |
| **E3** | D-040's verdicts on the alternative draw | unchanged | any pre-registered verdict flips |
| **E4** | A named protocol's gain over the calibration-best aggregation rule | `independent_judge` > 0 in ≥ 2 of 3 pools | **≥ +1.0 pp in all 3 pools**, and the same protocol wins on both suites |

**+1.0 pp** is carried over from the 2026-08-13 RQ pre-registration for comparability.

## 4. Controls, non-negotiable

1. Every rule is frozen on calibration and scored on test. `oracle_fixed` is labelled a ceiling, never a policy.
2. `cross_pool` is fitted **leave-one-pool-out**, never on the pool it scores.
3. Resplits, not one partition.
4. E1 runs on both suites; a rule that works on one is reported as suite-specific.
5. E4 names the protocol **before** looking at which one wins on `crosscap240`. On the evidence so
   far that is `independent_judge`. Any other protocol winning is reported as exploratory.

## 5. The decision rule

**POSITIVE PAPER EXISTS** if E1a or E1b or E1c clears its bar on **both** suites, or E4 clears its
bar and replicates on a second suite.

**NO POSITIVE PAPER FROM THIS SUBSTRATE** if none clears. In that case the honest options are the
measurement-audit paper, or a new substrate.

E2 and E3 do not gate the decision: E2 sharpens an interpretation and E3 is a robustness check.
Both are reported whatever they say.

## 6. Why no outcome wastes the time

- **E1 positive** → a practical, constructive claim with 280 pools behind it, on a quantity the
  field has never questioned, and every negative result becomes its motivation.
- **E1 negative** → the calibration argmax is already near-optimal, which is itself a sharp
  statement: the winner's curse is real but not recoverable, and the 2.39 pp is not headroom either.
- **E2 either way** → resolves the last open interpretation in the claim-evidence matrix.
- **E3 flip** → the largest known threat in the project becomes a measured one.
- **E4 positive** → a named protocol recommendation, which is the most directly usable output the
  substrate could produce.
