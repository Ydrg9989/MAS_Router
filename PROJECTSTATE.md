<!-- doc-meta
type:          living
lifecycle:     update-in-place — never fork a v2; git history is the version record
last-verified: 2026-08-11
evidence-base: see §A5 traceability table
supersedes:    Docs/CURRENT_STATE.md (folded in, 2026-08-11)
-->

# Project state

**The single source of truth for where this project is.** Update this file in place; do not
write a new state report. `TODO.md` records what is not done. `DECISIONS.md` and
`EXPERIMENT_LOG.md` are append-only ledgers of how we got here.
[`Docs/README.md`](Docs/README.md) explains what every other document is.

Two parts: **A. Research state** — what we know and what is decided. **B. System state** —
what runs, and the invariants that make results trustworthy.

---

# Part A — Research state

## A1. The project in ten lines

Started 2026-08-04 as three candidate ICLR projects sharing one experimental substrate:
**epistemic governance**, **delegation-equivalent task representations**, **coalition
landscapes**. A pre-registered gate was to pick one on evidence.

All three failed. Governance died on a refuted pre-registration (D-026 → D-027). Coalition
failed its criterion on all three pools. Delegation was selected by the gate, then the gate
itself was shown to be non-falsifiable (D-029, D-030), and the direction closed on its own
merits (D-033 → D-036).

What survives is a **methodological negative**: oracle headroom is not evidence of routable
structure, and the cost comparison usually paired with it is unsound. That is the paper
currently planned in [`Docs/paper/PAPER_BACKBONE.md`](Docs/paper/PAPER_BACKBONE.md).

**Total spend: $85.13–$88.09** (see §A7) of an originally allocated ~€3,000.

## A2. Current direction — undecided, under review

As of 2026-08-11 the paper framing is **under active review** and no direction is committed.
The 2026-08-11 review raised four things bearing on the choice; they are recorded in
[`Docs/literature/NOVELTY_BOUNDARY.md`](Docs/literature/NOVELTY_BOUNDARY.md) and in §A4 below.

## A3. What is safe to claim

| Claim | Strength | Evidence |
|---|---|---|
| Oracle headroom does not exceed a matched null preserving member sharing | strong | 6 cells + 134 public systems; null replays real episodes at agreement 1.0000 and fires on planted specialists |
| Interaction is present in `crosscap240`, absent in `hard366` | strong | D-038; p≤0.005 at agent and organization level vs p=0.164 |
| Headroom is *insensitive* to interaction, not merely inflated | strong | the same tables carry interaction at p≤0.005 while headroom excess is −0.23 / −0.05 / −3.24 |
| A learned router gains nothing here, and it is not a data-volume problem | strong | D-033; flat learning curve, 57→398 calibration tasks |
| A linear cost sweep reaches only the convex hull | strong | 3–9 of 30 Pareto-efficient organizations unreachable at any λ |

## A4. What is weak, contested, or overclaimed

1. **"Rules out an entire family of routers."** The capability router bounds only routers whose
   representation is a function of a **four-way dataset-provenance partition**. Every router in
   the literature uses more. Overclaimed in `PAPER_BACKBONE.md`; `FRAMEWORK.md` §2 is correct.
2. **"Aggregation is a substitute for routing."** Rests on 2 of 3 pools. **n=3.**
3. **Three dissenting results, recorded and unexplained** — semantic k-NN beats the learned
   model (+1.40, 77% of resplits); the capability router beats voting in `correlated4` (+2.5);
   routing wins at the tightest budgets in all three `crosscap240` cells.
4. **Proposition 1** assumes no interaction and concludes no exploitable structure — close to
   definitional. **Lemma 2** is a textbook fact about weighted-sum scalarisation.
5. **One seed everywhere.** This maximises exactly the upward bias in Ĥ that the paper is about.
6. **Eight agents, one provider, two protocols** in every cross-suite comparison.
7. **The paper may be arguing on the wrong axis.** The routing literature's headline claims are
   about **cost**, not accuracy. Our budget result finds routing losing at *unconstrained*
   budget — where routers are not deployed — while winning at tight budgets, where they are.
8. **Roughly 4% of the substrate has been used.** 8 agents are dense on both suites, so 70
   four-agent pools are computable free; 3 were studied. Aggregation-only protocols cost zero
   model calls; 2 were tested. Three public matrices are unused.
9. **`Nash-CredMAS` in the literature review does not exist**; six other entries are unverified.

## A5. Traceability — which artefact backs which claim

Every run directory carries `run_meta.json` with pool, manifest content-hash, price snapshot and
upstream pins. That is the authoritative version record; this table is the index into it.

| Artefact (`data/runs/`) | Produced by | Decision | Date |
|---|---|---|---|
| `strong4-a/`, `decorr4-a/`, `correlated4-a/` | `scripts/run_priced.sh` | D-024 … D-028 | 2026-08-06 |
| `hard366-a/`, `crosscap-*/` | Stage A + free Stage B | D-020, D-032 | 08-05, 08-10 |
| `headroom_null.json` | `check_oracle_headroom.py` | D-034 | 2026-08-08 |
| `headroom_null_swebench.json` | `check_headroom_swebench.py` | D-034 | 2026-08-08 |
| `headroom_null_specialists.json` | `check_headroom_specialists.py` | D-035 | 2026-08-09 |
| `headroom_null_shared_members.json` | `check_headroom_shared_members.py` | D-037 | 2026-08-10 |
| `routing.json`, `routing_pooled.json` | `measure_routing*.py` | D-033 | 2026-08-07 |
| `cost_frontier.json` | `measure_cost_frontier.py` | D-036, D-039 | 08-08, 08-10 |
| `interaction.json` | `measure_interaction.py` | D-038 | 2026-08-10 |

**Rule going forward:** any document quoting a number names the artefact key it came from, as
[`Docs/paper/CLAIM_EVIDENCE_MATRIX.md`](Docs/paper/CLAIM_EVIDENCE_MATRIX.md) already does per row.

## A6. Open questions

1. Is *"aggregation substitutes for routing"* real, or an n=3 artifact?
2. Why does the capability router beat voting in `correlated4` — mechanism, or noise?
3. Are the tight-budget routing wins capability matching or domain-price arbitrage? The
   separating experiment (price-flattened rerun) is designed and **unrun**.
4. Does `independent_judge` actually win? D-028's defect blocks the answer, and the fix
   invalidates the priced cache.
5. `crosscap240` under the five priced protocols — never run.
6. A second seed — free for the two free protocols via replay.

## A7. Bookkeeping discrepancies to reconcile before publication

- **Total spend** reads **$85.13** historically and **$88.09** in
  `data/runs/spend_ledger.jsonl` (11,622 calls); per-run figures differ by ~$1
  (`strong4-a` $19.36 vs $20.21).
- `data/runs/calib15/` is empty; `dry-*` and `plan-*` hold only price snapshots.
- No `discrimination.json` or `gonogo.json` was persisted for any `crosscap` run.
- Six banks have answers but **no episodes** — free Stage B value never spent.
- Terminology is inconsistent across `DECISIONS.md`: "organization" / "configuration" /
  "coalition" / "pool". Open blocker before drafting.

---

# Part B — System state

## B1. Status at a glance

| Layer | State | Where |
|---|---|---|
| Environment, upstream pins, preflight | works | `pyproject.toml`, `UPSTREAM.md`, `mas_harness/doctor.py` |
| Cost accounting, cache, spend caps | works | `mas_harness/clients/` |
| Task manifests, splits, evaluators | works, 3 of 4 MVP domains | `mas_harness/tasks/` |
| Distributed-information condition | built, **never run against real models** | `mas_harness/tasks/distributed.py` |
| Agent pools, predicted expert, role rotation | works | `mas_harness/pool/` |
| Stage A answer bank | works, run on both suites | `mas_harness/runners/answer_bank.py` |
| Protocols 1–7 | works | `mas_harness/protocols/` |
| Causal interventions | works | `mas_harness/interventions/edits.py` |
| Stage B episodes, records, Parquet | works | `mas_harness/runners/episodes.py`, `records/` |
| Governance / delegation / coalition metrics | works | `mas_harness/metrics/` |
| No-interaction nulls (independent + member-sharing) | works | `mas_harness/metrics/sharing_null.py` |
| Interaction likelihood-ratio test | works | `mas_harness/metrics/interaction.py` |
| Go/no-go gate | works, **criteria retired** — see D-029, D-030 | `mas_harness/analysis/gonogo.py` |
| Learned router + baseline ladder | works, run on 6 cells, no gain | `mas_harness/metrics/routing.py` |
| Coding domain (EvalPlus) | unavailable, no sandbox | `TODO.md` |
| GPUs / local vLLM | host has **no GPU at all** | `TODO.md` |

**412 tests pass**; `ruff check` clean over `mas_harness`, `scripts`, `tests`.

## B2. Substrate

**Two-stage design (D-001).** Stage A banks one independent answer per (task, agent, seed).
Stage B replays protocols over the bank. Aggregation protocols are deterministic functions of
banked answers, so they cost nothing and `do(·)` interventions are exact computations rather
than re-elicitations. Upstream `Task.execute()` is never called.

**Suites** — 9 manifests built and content-hashed.

| suite | tasks | composition | agents densely banked |
|---|---:|---|---:|
| `hard366` | 366 | GPQA-Diamond 122, MATH-500 L5 122, MMLU-Pro theoremQA/scibench 122 | 10 |
| `crosscap240` | 240 | CRUXEval 60, AIME 60, ExploreToM 60, GPQA-Diamond 60 | 8 |
| `screen120` | 120 | subset of `hard366`, so its calls are cache hits | 16 |
| `distributed30`, `distributed30_pressure` | 30 each | synthetic partitioned-option arms | 0 — never banked |
| `mvp366`, `mvp90`, `pilot9`, `crosscap12` | — | retired: saturated | — |

**Pools** — all use `anthropic/claude-sonnet-5` as aggregator so the pool contrast is not
confounded with judge identity (D-024).

| pool | members | error corr | `single_expert` |
|---|---|---:|---:|
| `strong4` | grok43, gpt5mini, deepseek32, llama4scout | +0.408 | 0.8989 |
| `decorrelated4` | gptoss120b, llama4scout, mistral-small, ring26 | +0.382 | 0.8552 |
| `correlated4` | gpt5mini, deepseek32, gptoss120b, qwen3-30b | +0.579 | 0.8989 |

**Protocols** — 7, described in
[`Docs/reference/PROTOCOL_CARD.md`](Docs/reference/PROTOCOL_CARD.md). Two are free (zero model
calls): `single_expert`, `independent_majority`. Five are priced.

⚠️ **The five priced protocols ran on `hard366` only**, on each pool's discriminating subset
(129–210 tasks). **`crosscap240` — the only suite where interaction is detectable — has never
seen a priced protocol.** Every cross-suite claim rests on 15 coalitions × 2 protocols = 30
"organizations", where the two protocols are vote and solo.

**On disk:** 6,024 banked answers across 16 agents; 97,531 episodes; 99 MB response cache.
The figure quoted in the paper — 4,392 answers → 57,489 episodes — is the three priced
`hard366` pools specifically.

**Constraints:** single seed (`seeds: [0]`, temperature 0) everywhere; no GPU; no code-execution
sandbox; caps are per-run ($75) and per-day ($150), not cumulative.

## B3. Load-bearing invariants

Asserted by tests, not merely intended. If one breaks, a scientific claim breaks with it.

- The two free protocols make **zero** model calls. The entire cost argument rests on it.
- Every protocol on a task sees byte-identical banked answers, so comparisons are exactly
  paired and McNemar applies.
- The predicted expert is fitted on the calibration split only; the oracle is computed but
  never pooled with it (D-004).
- An answerless message is an abstention, not a vote (D-011).
- Interventions never mutate the input bank.
- Every branch point in the governance protocols is resolved by extraction or string matching,
  never by a second model (D-003, D-013).
- Role rotations carry distinct pool ids, so they cannot collide in the resume set (D-014).
- In the distributed condition the correct option is visible to exactly the recorded holders,
  the union of visible option sets is complete, and every member sees the same number of
  options (D-010). Checked per task at build time.
- Manifest content hashes cover private briefings, so a changed partition is a changed
  manifest (D-016).

## B4. Known limitations

- Three of four MVP domains available; no code-execution path, so the coding domain is absent.
- The distributed condition is *constructed*, not HiddenBench, and labelled `distributed_synth`
  (D-010). Compare protocols within the condition, never across.
  `out_of_set_rate()` has never been measured on real model output.
- `mixed_effects_logit` clusters on task via GEE rather than fitting crossed task+seed random
  effects. Adequate for a pilot, not for the paper.
- The semantic task space falls back to character n-gram TF-IDF when `sentence-transformers`
  cannot reach the network. Both paths measured and agreeing (Spearman 0.028–0.105 real,
  0.048–0.063 fallback), but each report must be read for which it used.
- **Configuration dominance is retired** (D-029) — diluted by adding protocols, and its noise
  null's 95th percentile lands exactly on the 75% threshold. Superseded by split-half winner
  reproducibility in `mas_harness/metrics/stability.py`. Any figure quoting it predates D-029.
- Harsanyi decomposition is exact and therefore exponential; refuses above twelve agents.
- `--dry-run` came in 1.9–3.0× above measured cost. Treat it as an upper bound, not a forecast.
- Absolute accuracy is not comparable across pools, only protocol contrasts within one (D-021).
  Nor is accuracy on a discriminating subset comparable to a full-suite figure.
