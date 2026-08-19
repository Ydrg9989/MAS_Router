<!-- doc-meta
type:          pre-registration
lifecycle:     FROZEN at commit time, before any API spend on these runs
evidence-base: pilot artefact data/runs/entitlement_pilot.json (GO on all four gates, $0.90)
-->

# Pre-registration: the entitlement main study

**The claim (D-047).** Shown peers' answers plus true, in-context-verifiable evidence-access
labels, does an LLM judge discount peers who provably could not know — measured against the
computable optimal discount? Step-0 gates: two shelves swept 2026-08-19; the two abstract-only
neighbours (2606.00820, 2607.01661) re-read in full the same day and CLEAR — the first attaches no
access labels and defines no normative baseline (its own null: suppressing adoption gains nothing
because harmful and beneficial influence cancel — which a *targeted* discount, requiring access
labels, is built to break); the second keeps its evidence asymmetry latent and unlabelled.

## Runs

**Stage A** (~3,000 calls, est. $8–12): `dist250-coop` / `dist250-press` / `dist250-press-h2` on
`distributed250{,_pressure,_pressure_h2}` × `openrouter4`. Fresh seed 20260819; the 30 pilot
source questions are excluded from all three manifests (verified: overlap 0); coop and pressure
share identical partitions (verified: 250/250).

**Stage B episodes** (grand coalition only, ~2,250 episodes, est. $28–40 at the $0.0144 anchor):

| bank | protocols |
|---|---|
| `dist250-press` | `independent_judge`, `judge_access_labelled`, `judge_access_inverted`, `judge_access_sets`, `judge_labelled` |
| `dist250-coop` | `independent_judge`, `judge_access_labelled` |
| `dist250-press-h2` | `independent_judge`, `judge_access_labelled` |

Planned total ≤ $52; hard cap $75. D-019/D-028 scoring rules apply unchanged. Episodes run only on
tasks with all four banked member answers. Single draw at temperature 0; the D-040 item-5
nondeterminism caveat applies and no alt-draw is budgeted.

## Frozen hypotheses

Definitions. *Adoption*: the judge's final answer is answer-equivalent to that member's banked
answer (equivalence via the task evaluator, as in `metrics/adoption.py`). *Wrong-majority task*
(pressure arm): ≥2 non-holders agree on the same wrong visible option while a holder is correct —
pilot base rate 33%, so ~83 of 250 tasks expected.

- **M1 — labels move adoption, identified by inversion.** Pooling `judge_access_labelled` and
  `judge_access_inverted` on `dist250-press`: adoption of advertised-holders exceeds adoption of
  advertised-non-holders by **≥ +10 pp**, with true-holder status controlled (the
  advertised-minus-true contrast, exactly as `adoption.py` identifies it).
- **M2 — the normative gap, the headline.** On wrong-majority tasks under truthful labels, the
  optimal policy follows the labelled holder (correct by the event's definition). Frozen branches
  for the follow-the-labelled-holder rate: **≥ 0.80 → "labels restore entitlement"** (and
  `judge_access_labelled` must also beat `independent_judge` by ≥ +5 pp overall on the pressure
  bank); **≤ 0.60 → "conformity persists under provable ignorance"** — the 2606.01637 asymmetry
  surviving a label whose optimal response is computable, which extends 2602.01011's
  "leveraging, not identification" to the strongest cue. Between 0.60 and 0.80: reported as
  measured, no branch claimed.
- **M3 — entitlement vs credentials.** `judge_access_labelled` minus `judge_labelled` (measured
  competence labels, same prompt shape) on the pressure bank: notable if **≥ +3 pp**; the adoption
  contrast per label type reported alongside.
- **M4 — structure vs conclusion.** `judge_access_sets` (option letters only, no designation):
  notable if it captures **≥ half** of `judge_access_labelled`'s accuracy gain over
  `independent_judge` — the judge can *derive* entitlement, not merely obey it.
- **M5 — dose-response (descriptive, no threshold).** All effects at n_holders = 2 on
  `dist250-press-h2`, reported next to n_holders = 1.

## What kills what

M1 failing kills the manipulation (the judge does not read access labels at all) and the direction
reverts to the wrong-majority persistence result only. M2's middle band with a failed M3 and M4
means no paper claim survives beyond replication of known conformity — record and stop. The H2
contamination check re-runs at scale on `dist250-coop` non-holders (n≈750) with the pilot's rule;
a kill there retracts the calibration reading but not M1–M4, which do not rest on member
self-knowledge.

## Analysis

`scripts/measure_entitlement_main.py`, to be written and committed **before any Stage B spend**,
scoring M1–M5 exactly as above and writing `data/runs/entitlement_main.json`. Member-level
conformity (members seeing labels, not just the judge) is explicitly out of scope for this study.

---

## Amendment, 2026-08-20 — additive, before any Stage B spend

The "What kills what" section promises the H2 contamination check at scale on `dist250-coop`, but
the Runs table omitted the input that check needs: full-information answers on the 250 fresh
source questions, which — unlike the pilot's 30 — are not in any existing bank. Added:

| run-id | manifest | pool | what |
|---|---|---|---|
| `dist250-fullinfo` | `distctl250` | `openrouter4` | the 250 source questions, intact option sets (~1,000 calls, est. $3) |

`distctl250` is built by `scripts/build_fullinfo_control_250.py` from the source cache, restricted
to exactly the partitioned qids. Nothing else changes: no hypothesis, threshold, or branch is
touched, and the planned total rises to ≤ $55 against the unchanged $75 hard cap. Recorded as an
amendment rather than silently edited into the frozen table.
