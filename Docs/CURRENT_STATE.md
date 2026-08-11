# Current state: what was run, what it showed, what was decided

Written 2026-08-11 as a single entry point. The project has ~300 KB of documentation across six
files, two of which give **opposite verdicts on the same question**, with nothing marking which
is current. This file resolves that and is the thing to read first.

**Nothing here is new work.** It consolidates `DECISIONS.md`, `EXPERIMENT_LOG.md`,
`Docs/EXPERIMENT_REPORT.md`, `PROJECTSTATE.md`, `Docs/FRAMEWORK.md` and
`Docs/CLAIM_EVIDENCE_MATRIX.md`, plus two findings from the 2026-08-11 review.

---

## 0. Read-order and which documents are superseded

| Document | Status | What it is |
|---|---|---|
| **this file** | current | entry point |
| `Docs/CLAIM_EVIDENCE_MATRIX.md` | **current** | every claim with its artefact key. The authoritative numbers. |
| `Docs/FRAMEWORK.md` | **current** | the formal position: notation, Prop 1, Lemma 2, claims C1–C5 |
| `Docs/PAPER_BACKBONE.md` | **current** | the paper plan as of 2026-08-10 |
| `Docs/EXPERIMENT_REPORT.md` | ⚠️ **SUPERSEDED IN PART** | the settled account of the **governance phase only**. Its gate verdict says *"delegation **GO**"* — **that verdict was retired by D-029/D-030.** Everything in §1–§12 about the governance runs is still accurate. §10.6's direction selection is not. |
| `Docs/deep-research-report_corrected.md` | historical | the 2026-08-04 design report proposing three candidate projects |
| `Docs/Delegation_MAS_Literature_Review_fixed.md` | ⚠️ **partly unverified** | see §7 |
| `DECISIONS.md`, `EXPERIMENT_LOG.md` | current, append-only | the raw record |

**The single biggest source of confusion in the corpus:** `EXPERIMENT_REPORT.md` says delegation
passed its gate and is the chosen direction. `DECISIONS.md` D-029 and D-030 say that gate could
not have failed and the direction is closed. **D-029/D-030 are current.**

---

## 1. The project in ten lines

Started 2026-08-04 as three candidate ICLR projects sharing one experimental substrate:
**epistemic governance**, **delegation-equivalent task representations**, **coalition landscapes**.
A pre-registered gate was supposed to pick one on evidence.

All three failed. Governance died on a refuted pre-registration (D-027). Delegation was selected
by the gate, then the gate itself was shown to be non-falsifiable (D-029, D-030), and the
direction closed on its own merits (D-033). Coalition failed its criterion on all three pools and
was never pursued.

What survived is a **methodological negative**: the statistic the field uses to motivate routing
(oracle headroom) is not evidence of routable structure, and the cost comparison usually used
alongside it is unsound. That is the paper currently planned.

Total spend: **$85.13–$88.09** (see §8 note) of an originally allocated ~€3,000.

---

## 2. The substrate — settings

**Two-stage design (D-001).** Stage A banks one independent answer per (task, agent, seed).
Stage B replays protocols over the bank. Aggregation protocols are deterministic functions of
banked answers, so they cost nothing and interventions are exact computations rather than
re-runs. Upstream `Task.execute()` is never called, precisely to keep answers decoupled from
protocols.

**Suites**

| suite | tasks | composition | agents densely banked |
|---|---:|---|---:|
| `hard366` | 366 | GPQA-Diamond 122, MATH-500 level 5 122, MMLU-Pro theoremQA/scibench 122 | 10 |
| `crosscap240` | 240 | CRUXEval 60, AIME 60, ExploreToM 60, GPQA-Diamond 60 | 8 |
| `screen120` | 120 | subset of hard366 | 16 |
| retired | — | `mvp366`, `mvp90`, `pilot9` — saturated | — |
| built, never run | 30+30 | `distributed30`, `distributed30_pressure` | 0 |

`hard366` is deliberately homogeneous (three flavours of hard technical reasoning).
`crosscap240` was built (D-032) because *"every suite so far has been one capability in three
costumes."*

**Pools** — three four-agent pools, a manipulation run in both directions:

| pool | members | intent |
|---|---|---|
| `strong4` | grok43, gpt5mini, deepseek32, llama4scout | a dominant agent present — control |
| `decorrelated4` | gptoss120b, llama4scout, mistral-small, ring26 | decorrelated errors — treatment |
| `correlated4` | gpt5mini, deepseek32, gptoss120b, qwen3-30b | correlated errors — opposing control |

`strong4` and `correlated4` are matched at `single_expert` = 0.8989 both.

**Protocols** — 7 implemented. Two are free (zero model calls): `single_expert`,
`independent_majority`. Five are priced: `independent_judge`, `expert_verifier`, `debate_vote`,
`expert_veto`, `chair_information_seeking`.

⚠️ **The five priced protocols ran on `hard366` only**, and only on each pool's discriminating
subset (129–210 tasks). **`crosscap240` — the only suite where interaction is detectable — has
never seen a single priced protocol.** Every cross-suite claim therefore rests on 15 coalitions ×
2 protocols = 30 "organizations", where the two protocols are vote and solo.

**Scale on disk:** 6,024 banked answers across 16 agents; 97,531 episodes; 99 MB response cache.
The figure quoted in the paper — 4,392 answers → 57,489 episodes — is the three priced `hard366`
pools specifically.

**Constraints:** single seed (`seeds: [0]`, temperature 0) everywhere; no GPU on this host; no
code-execution sandbox; per-run cap $75, per-day $150.

---

## 3. What was run, in order

| phase | runs | cost | what it settled |
|---|---|---:|---|
| **1. Instrument debugging** | `pilot9-a/b`, `probe-gpqa`, `probe-fixed`, `mvp366-a` (halted) | ~$1.5 | Truncation was being scored as incompetence (D-019). Suites were saturated, not the harness. Task **discrimination** must be screened before Stage B is priced (D-020) |
| **2. Pool design** | `hard366-a`, `screen-a`, `screen-strong`, `cand4-a` | ~$17 | Headroom on `hard366-a` was 4.37pp against an 8pp gate (D-021) — spending would have bought an arithmetic NO GO. Commit-rate floor ≥95% (D-022). Design variable pivoted to **error decorrelation** (D-023) |
| **3. Priced governance** | `strong4-a`, `correlated4-a`, `decorr4-a` | ~$57 | The three-pool sweep, 7 protocols each. Produced the gate verdicts and the falsification episode |
| **4. Delegation, free** | `crosscap` Stage A + all analysis | ~$3.6 | Everything from D-029 to D-039 cost **$0** |
| **5. Failed repair** | `*-retry` ×3 | ~$10.4 | D-028 aggregator non-termination could not be repaired; Anthropic reasoning controls on OpenRouter are silently ignored |

---

## 4. Results, by direction

### 4.1 Governance — NO GO

**Settings:** 3 pools × 7 protocols × discriminating subsets, plus single-member masking
interventions (1,464 pairs per protocol per pool).

- **No protocol reliably beats deferring to a predicted expert.** 18 protocol-versus-baseline
  tests; nothing survives Holm correction; smallest adjusted *p* = 0.694.
- **Deliberation can harm.** `debate_vote` cost 3.88pp in one pool; plain majority voting was
  never positive in any pool.
- **Pool composition dominates protocol choice.** The same rule swings **+3.37pp to −6.20pp**
  depending only on which four models are present.
- **A pre-registered confirmation failed (D-026 → D-027).** Error decorrelation moderating the
  expert veto measured **+10.53pp, 95% CI [+3.16, +17.89], p=0.0052** on two pools, and
  **−1.90pp (p=0.424)** on the third. *"A moderator cannot produce a positive effect only in the
  middle of its own range."* Cost to refute: $17.93.
- **Unresolved, not negative:** `independent_judge` is non-negative in all three pools. Rescored
  with non-terminating aggregator episodes dropped (D-028): **+2.91 (p=0.38), +6.97 (p=0.0066),
  +3.25 (p=0.42)**. The honest reading is that it is the most promising protocol measured **and
  we cannot tell whether it wins.**
- **What survived is about influence, not accuracy.** Masking changes the *vote's* decision
  **5.5% / 8.5% / 5.3%** of the time. Leverage diverges from competence within every pool —
  `llama4scout` at 0.658 accuracy has a **0.5%** flip rate.

### 4.2 Delegation — closed

- **Learned router `q_theta` gains nothing** over a frozen best-fixed baseline: **+0.33, −0.53,
  −0.42, +0.08, −1.78, +0.03** points across 6 cells / 60 resplits; ahead in 13–47% of resplits.
  A shuffled-representation control is worse in every cell, so the representation is inert rather
  than mis-scaled.
- **Not a data-volume problem.** Pooled 569 tasks, calibration swept 10%→70% (≈57→398 tasks):
  gain stays in [−1.28, +0.37] with no trend.
- **A crude baseline beats the learned model.** Semantic k-NN gains **+1.40 (77% of resplits)** on
  `hard366`/`strong4` and **+1.01 (70%)** on `crosscap240`/`strong4`.
- **Oracle headroom does not exceed a matched null.** Excess over the member-sharing null:
  **+2.20 (p=0.045), +1.16, −0.07, −0.23, −0.05, −3.24**. Bonferroni threshold for 6 cells is
  0.0083; at least one p<0.05 among six occurs 26% of the time under the global null.
- **Externally too.** 134 public SWE-bench systems, K ∈ {4,8,16,32,134}: excess **−1.88 to
  −2.65**, p = 0.940–0.970. Observed headroom rises with K exactly as the null predicts.
- **The null has power** (planted four-specialist structure detected at p<0.05, excess >5pp) and
  **reproduces recorded episodes at agreement 1.0000** in all six cells.
- **A capability router with ground-truth labels** (best single / router / whole-pool vote / oracle):
  `strong4` 0.792 / 0.830 / **0.836** / 0.937 · `decorrelated4` **0.843** / 0.736 / 0.811 / 0.931
  · `correlated4` 0.805 / **0.881** / 0.855 / 0.943.
- **Budget-matched, routing loses** at unconstrained budget in all six cells: **−3.15, −1.70,
  −2.48, −0.48, −1.97, −3.94**. **But routing wins at the tightest budgets** in all three
  `crosscap240` cells: **+4.05 (81%), +2.68 (89%), +13.91 (100%)**.
- **The λ-sweep artefact.** Regenerated best-λ gains **+3.36, −0.02, +1.06, +7.02, +3.47, +7.99**
  against budget-matched **−0.48 to −3.94** on the same data. Hull diagnostic: of 30
  organizations per cell, 7–14 are Pareto-efficient, only 3–6 reachable by any λ, leaving **3–9
  Pareto-efficient but invisible**.

### 4.3 Coalition landscapes — NO GO, never pursued

Top-k gap **8.20 / 9.29 / 4.92%** against a ≥15% threshold.

### 4.4 The mechanism

- **Interaction is real** (D-038, likelihood-ratio with parametric bootstrap):
  `crosscap240` agents p≤0.005, excess **+7.29pp**; organizations p≤0.005 all three pools, excess
  **+6.71 / +4.21 / +3.78pp**. `hard366` shows nothing at agent level (p=0.164) and nothing at
  organization level in two of three pools.
- **This validates the suite manipulation directly** and kills the "your tasks were too alike"
  objection.
- **But headroom cannot see it.** On the same three `crosscap240` tables carrying interaction at
  p≤0.005, headroom excess is −0.23, −0.05, −3.24 (p = 0.605, 0.560, 0.965). **Headroom is
  insensitive, not merely inflated.**
- **Profiles share one difficulty ordering.** Over 238 `crosscap240` tasks, 8 agents:
  **7 of 8 peak on code**, the eighth on maths, **none on theory of mind**. Spreads run 0.160
  (`deepseek32`) to 0.833 (`grok43`: 0.967 code, 0.133 theory of mind).
- **A positive control fails.** `disjoint4` — the best agent per capability, chosen on
  calibration — shows excess **−2.16, p=0.883**.

---

## 5. The gate, and why it is the crux

Pre-registered thresholds, identical verdict on all three pools
(`Docs/EXPERIMENT_REPORT.md` §10.6):

| criterion | threshold | strong4 | decorr4 | correlated4 |
|---|---|---|---|---|
| protocol spread | ≥ 8pp | 3.37 FAIL | 7.14 FAIL | 6.20 FAIL |
| correct-answer dilution | ≥ 15% | 7.95 FAIL | 5.14 FAIL | 10.62 FAIL |
| coalition top-k gap | ≥ 15% | 8.20 FAIL | 9.29 FAIL | 4.92 FAIL |
| intervention flip rate | ≥ 10% | 25.0 PASS | 24.5 PASS | 25.0 PASS |
| configuration dominance | ≤ 75% | 41.7 PASS | **75.0 PASS** | 58.3 PASS |
| semantic vs organizational ρ | < 0.5 | 0.048 PASS | 0.048 PASS | 0.063 PASS |

**All three PASSes were later shown by the project's own audits to be non-criteria:**

- *flip rate* — carried entirely by `single_expert`, where masking the predicted expert
  necessarily changes the answer. The meaningful number is the vote's 5.3–8.5%, and **no pool
  reaches 10%**. Self-described as *"an artifact of the criterion's specification."*
- *configuration dominance* (D-029) — label-shuffled noise reads 54–59%, and the noise null's
  95th percentile lands **exactly on the 75.0% threshold**.
- *semantic vs organizational ρ* (D-030) — observed +0.0275 against noise +0.0350. Also, the
  routing evidence leaked, because *"the test task's coordinates are its own outcomes."*

**So: every criterion that could fail, failed. Every criterion that passed, could not fail.**
The direction that was selected was selected on non-evidence.

And the 2026-08-04 design report had already written the decision rule for this exact pattern:
*"One configuration and one coalition dominate almost everywhere → Do not pursue these projects
without changing the task and agent design."* The substrate was kept and the paper was changed
instead. That override is the origin of the current framing.

---

## 6. What is safe to claim, and what is not

**Well supported**
- Oracle headroom does not exceed a matched null preserving member sharing, on 6 cells + 134
  public systems, with an instrument shown to fire on planted structure and to replay real
  episodes exactly.
- Interaction is present in `crosscap240` and absent in `hard366`, at both levels.
- Headroom is insensitive to interaction present in the same table.
- A learned router gains nothing here, and it is not a data-volume problem.
- A linear cost sweep reaches only the convex hull; 3–9 Pareto-efficient organizations per cell
  are unreachable at any λ.

**Weak, contested, or overclaimed**
- *"Rules out an entire family of routers."* The capability router bounds only routers whose
  representation is a function of a **four-way dataset-provenance partition**. Every router in
  the literature review uses more.
- *"Aggregation is a substitute for routing."* Rests on 2 of 3 pools. n=3.
- **The three dissenting results** — semantic k-NN beating the learned model; the capability
  router beating voting in `correlated4`; routing winning at the tightest budgets — are recorded
  and unexplained.
- **Proposition 1** assumes no interaction and concludes no exploitable structure; close to
  definitional. **Lemma 2** is a textbook fact about weighted-sum scalarisation.
- **One seed everywhere.** This maximises exactly the upward bias in \(\hat H\) the paper is about.
- **Eight agents, one provider, two protocols** in every cross-suite comparison.

---

## 7. What the 2026-08-11 review added

1. **The novelty boundary was surveyed against the wrong literature.** The lit review covers
   routing *methods*; the paper is a measurement *audit*. Checked against the audit shelf
   ([`NOVELTY_BOUNDARY.md`](NOVELTY_BOUNDARY.md)): the nearest paper (arXiv 2607.20768) is **not
   a collision** — it excludes routers by scope, has no null and no latent-structure analysis —
   and it independently reproduces the headroom illusion at 31,900 subsets. IRT-Router fixes
   dimensionality at 25 as a hyperparameter and never measures it.
2. **`Nash-CredMAS` does not exist.** It appears to merge two real papers. `DecoR`'s real title
   is *"Beyond Query Memorization…"*. Six lit-review entries remain unverified.
3. **About 4% of the substrate has been used.** 8 agents are dense on both suites, so **70
   four-agent pools** are computable free; 3 were studied. Aggregation-only protocols cost zero
   model calls; 2 were tested. Three public matrices sit unused, one with **5 trials per cell**.
   Full transcripts are retained and have never been analysed.
4. **The paper may be arguing on the wrong axis.** The routing literature's headline claims are
   about **cost**, not accuracy (MixLLM "97.3% quality at 24.2% cost"; IPR "43.9% cost
   reduction"; EvoRoute "cost ~80%"). Claims 2–3 are accuracy claims. And our own budget result
   finds routing losing at *unconstrained* budget — where routers are not deployed — while
   **winning at tight budgets**, which is where they are.

---

## 8. Known bookkeeping discrepancies

- **Total spend** is recorded as **$85.13** in `PROJECTSTATE.md` and **$88.09** in
  `data/runs/spend_ledger.jsonl` (11,622 calls). Per-run figures also differ by ~$1 between
  sources (e.g. `strong4-a` $19.36 vs $20.21). Reconcile before any figure appears in the paper.
- `data/runs/calib15/` is empty; `dry-*` and `plan-*` contain only price snapshots.
- No `discrimination.json` or `gonogo.json` was persisted for any `crosscap` run.
- Six banks have answers but **no episodes** — free Stage B value never spent.
- Terminology is inconsistent across `DECISIONS.md`: "organization" / "configuration" /
  "coalition" / "pool". Flagged as an open blocker before drafting.

---

## 9. Genuinely open questions

1. Is the *"aggregation substitutes for routing"* claim real, or an n=3 artifact?
2. Why does the capability router beat voting in `correlated4` — mechanism, or noise?
3. Are the tight-budget routing wins capability matching or domain-price arbitrage? The
   separating experiment (price-flattened rerun) is designed and **unrun**.
4. Does `independent_judge` actually win? D-028's defect blocks the answer, and the fix
   invalidates the priced cache.
5. What happens on `crosscap240` under the five priced protocols — never run.
6. Is a second seed consistent with the first? Free for the two free protocols via replay.
