<!-- doc-meta
type:          frozen
lifecycle:     FROZEN — never edit after writing; results go to EXPERIMENT_LOG.md + DECISIONS.md
last-verified: 2026-08-13
evidence-base: not yet run
-->

# Pre-registration: does `independent_judge` replicate on `crosscap240`?

Written **before** the run, and before any `crosscap240` priced episode exists. This is the only
experiment in the project that requires new spending, and the only route from this substrate to a
positive result (D-042).

Status: **not yet run.** Locked 2026-08-13.

---

## 1. The claim, named in advance

D-042 established two things about the five interaction protocols on `hard366`:

- **Choosing the best one per pool is noise.** Split-half agreement of the argmax protocol is
  0.00–0.17, far below `stability.py`'s 0.5 floor. This is the D-029 pattern and it means no
  "pick the best protocol" result is admissible.
- **One protocol named *a priori* is positive in all three pools.** Against the
  calibration-chosen best aggregation rule, over 60 resplits: `independent_judge` gains **+1.42**
  (ahead in 68% of resplits), **+6.09** (100%) and **+1.33** (55%). It is the only one of the five
  positive in all three, and it is the protocol `TODO.md` already flagged as sign-stable before any
  of these numbers existed.

So the claim tested here is fixed now, in writing, before the data exists:

> **`independent_judge` beats the calibration-chosen best aggregation rule.**

No other protocol is under test. If `chair_information_seeking` or `debate_vote` happens to win on
`crosscap240`, that is **exploratory** and must be reported as such — they already failed on
`correlated4` (−2.36 and −2.56) and naming them now would be the winner's curse D-042 documented.

## 2. Why a second suite, and why this one

Every priced episode in the project is on `hard366`, which D-038 showed carries **no detectable
agent-by-capability interaction**. `crosscap240` carries a great deal — p≤0.05 in 100% of its 70
pools, median excess departure +4.41 pp (D-040). A protocol advantage that holds on both a
homogeneous and a genuinely cross-capability suite is a different claim from one measured once.

## 3. Design

Identical instrument to the `hard366` priced runs, deliberately:

| | |
|---|---|
| suite | `crosscap240` (240 tasks, four capabilities) |
| pools | `strong4`, `decorrelated4`, `correlated4` — the same three, same YAMLs |
| protocols | `independent_judge`, `expert_verifier`, `debate_vote`, `expert_veto`, `chair_information_seeking` |
| coalitions | grand only, matching `scripts/run_priced.sh` |
| tasks | each pool's discriminating subset, computed from banked answers before the run |
| run ids | `crosscap-strong4`, `crosscap-decorr4`, `crosscap-corr4` — appended to the existing Stage A banks |
| aggregator | `anthropic/claude-sonnet-5`, unchanged |

### The prompt is deliberately NOT repaired

D-028 identified a fix — require the answer letter before the explanation, capping the cost of
aggregator non-termination at zero — and deferred it because it "invalidates the whole priced
cache". There is no `crosscap240` priced cache to invalidate, so the fix could be applied here.

**It is not, and the reason is the claim.** Changing the prompt would mean the second suite used a
different instrument from the first, and "replicates on a second suite" would be confounded with
"replicates under a better prompt". Keeping the prompt identical makes the ~4% non-termination
handicap apply equally to both suites, which leaves `independent_judge`'s advantage a **conservative
floor** on each. The repaired prompt is the follow-up if this replicates, not a variable in it.

### Dual scoring, per D-028

Every aggregator-decided figure is reported twice — scored-as-wrong and with non-terminating
episodes excluded — and neither is privileged. Scored-as-wrong is the deployment figure; excluded is
a biased upper bound, because non-termination concentrates on the hardest items.

## 4. Predictions and thresholds

| # | Quantity | Predicted | Positive if | Refuted if |
|---|---|---|---|---|
| **J1** | `independent_judge` minus the calibration-chosen best aggregation rule, mean over 60 resplits | > 0 in all three pools | **≥ +1.0 pp in ≥ 2 of 3 pools**, and non-negative in the third | < +1.0 pp in ≥ 2 of 3, or negative in ≥ 2 |
| **J2** | The same, with non-terminating episodes excluded | ≥ J1 | J1 holds under both scorings | the sign differs between scorings |
| **J3** | Split-half reproducibility of the *argmax* protocol | < 0.5, as on `hard366` | — | ≥ 0.5, which would mean protocol selection is learnable after all and is a **larger** result than J1 |
| **J4** | Aggregator non-termination rate for `independent_judge` | 3–5%, as on `hard366` | — | > 10%, in which case the suite is not comparable and J1 is uninterpretable |

**+1.0 pp** is carried from the two 2026-08-13 pre-registrations for comparability.

## 5. The decision rule

**POSITIVE PAPER** if J1 is positive under both scorings of J2. The claim becomes: *a named
coordination protocol beats aggregation across two suites and six pools, while per-task routing
between organizations does not pay at all* — a positive, usable recommendation with 280 pools of
negative context behind it.

**NO POSITIVE PAPER FROM THIS SUBSTRATE** if J1 is refuted. In that case the interaction-protocol
advantage was a `hard366` artefact, every direction is closed, and the honest options are the
measurement-audit paper or a new substrate. **No further spending is justified on this substrate
either way** — this run is the last purchase.

## 6. Budget and stopping

- Estimate: **$60–90** for three pools, from the `hard366` priced runs ($20.21, $19.18, $18.71) at
  comparable subset sizes. `--dry-run` came in 1.9–3.0× above measured cost historically (D-017), so
  a dry-run estimate of up to ~$200 is consistent with this.
- Caps: per-run $75 and per-day $150 remain in force. **If a per-run cap fires, stop and report** —
  do not raise it.
- Project total before this run: **$88.09** of ~€3,000.

## 7. Why no outcome wastes the money

- **J1 positive** → the positive ICLR result, on two suites.
- **J1 refuted** → the one surviving positive claim was a single-suite artefact, which closes the
  substrate honestly and completely rather than leaving an untested "most promising" thread.
- **J3 refuted** → protocol selection is learnable where organization selection is not, which is a
  bigger result than J1 and reopens a direction on evidence.
- **J4 refuted** → the aggregator fails differently on this suite, which is a finding about the
  instrument that bears on every aggregator-decided number in the project.
