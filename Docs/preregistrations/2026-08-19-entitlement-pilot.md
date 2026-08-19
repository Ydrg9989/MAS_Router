<!-- doc-meta
type:          pre-registration
lifecycle:     FROZEN at commit time, before any API spend on these runs
evidence-base: none yet; thresholds inherited from the 2026-08-19 red-team review (R1)
-->

# Pre-registration: the entitlement pilot

**Direction adopted (D-047):** deference under provable ignorance — does an LLM group discount
peers who verifiably could not know, measured against the computable optimal discount? Novelty
gates run 2026-08-19: HiddenBench (arXiv 2505.11556) keeps asymmetry latent; 2606.01637 conditions
on authority; 2602.01011 on expertise labels; the access-label contrast is verifiably unoccupied.
Target: ICLR 2027 (abstract 2026-09-18, paper 2026-09-25).

**This pilot decides whether the direction survives its own red team, before the main study is
built.** It tests the substrate, not the flagship: no access-label protocols run here, and no
main-study claim may be drawn from pilot data.

## Runs (est. 360 calls, ~$1.50–4.00)

| run-id | manifest | pool | what |
|---|---|---|---|
| `dist30-coop` | `distributed30` | `openrouter4` | cooperative arm: members warned, may decline |
| `dist30-press` | `distributed30_pressure` | `openrouter4` | pressure arm: neither |
| `dist30-fullinfo` | `distctl30` | `openrouter4` | the same 30 questions, intact option sets |

Both distributed arms share identical partitions (same seed, D-015); `distctl30` is the
full-information twin filtered from `mvp366` (`scripts/build_fullinfo_control.py`).

## Measures

Per (member, task) where the member is a **non-holder** (3 × 30 = 90 observations per arm):
declared decline (`declared_no_answer`), strict-extraction abstention, out-of-set answering,
out-of-set **gold** guessing (`guessed_unseen_gold_rate`), and — from the control — that member's
full-information correctness on the same source question. Per task: holder correctness, and the
plurality outcome over the four members.

## Frozen hypotheses and thresholds

- **H1 — the manipulation moves behaviour.** Cooperative-arm non-holder decline rate exceeds the
  pressure-arm non-holder abstention rate by **> 30 pp**. (Red-team R1 threshold.)
- **H2 — calibration is not memorization (the contamination kill).** Split cooperative-arm
  non-holder observations by whether that member answered the intact question correctly in
  `dist30-fullinfo`. **Kill condition:** decline(full-info-correct) − decline(full-info-wrong)
  exceeds **half the pooled decline rate**. If a member declines mainly when it already knows the
  answer is off its menu, "calibration" is memorization detection and the abstention claims die.
  Report the per-member breakdown either way.
- **H3 — the construction holds.** Pooled `guessed_unseen_gold_rate` **< 10%**. A non-holder that
  recovers the unseen gold option by memory breaks provable insufficiency in practice.
- **H4 — the flagship event materializes.** In the pressure arm, the wrong-majority event (≥ 2
  non-holders agreeing on the same wrong visible option while the holder is correct) occurs on
  **≥ 30% of tasks**. Without a common wrong-majority there is nothing for entitlement labels to
  protect against, and the main study has no stakes.

## Decision rule, frozen

**GO** to the main study iff H1 ∧ ¬H2-kill ∧ H3 ∧ H4. Any failure → the direction closes at pilot
cost, logged in `DECISIONS.md`, exactly as the last three directions closed.

## What GO buys, stated in advance

The main study (separately pre-registered before its own spend): ~250 fresh tasks per arm
(**excluding these 30 source questions**), the access-label protocol pair (truthful/inverted,
cloning `protocols/conformity.py` with per-task labels from holder metadata), judge-adoption
measurement via `metrics/adoption.py`, n_holders ∈ {1, 2}, and the head-to-head access-vs-authority
label contrast, with the normative gap (measured deference − computable optimal discount) as the
headline quantity. Est. $50–170. The step-0 gate is re-run on the exact claim (fetching
arXiv 2606.00820 and 2607.01661 in full) before that pre-registration freezes.
