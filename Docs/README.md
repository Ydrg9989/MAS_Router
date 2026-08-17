<!-- doc-meta
type:          living
lifecycle:     update-in-place — add a row whenever a document is added
last-verified: 2026-08-14
evidence-base: none (index only)
-->

# Documentation index

Every document has a declared **lifecycle**. Follow it: it is what stops the corpus turning into
a pile of half-superseded reports.

| lifecycle | rule | applies to |
|---|---|---|
| **living** | Update **in place**. Never fork a `_v2`, `_fixed`, `_final`. Git is the version history. | `PROJECTSTATE`, `TODO`, `README`, `UPSTREAM`, everything in `paper/` and `literature/` |
| **ledger** | **Append only.** Never edit or delete a past entry; correct it with a new one that says what it supersedes. | `DECISIONS.md`, `EXPERIMENT_LOG.md` |
| **frozen** | Dated at creation, **never edited afterwards**. A pre-registration that can be edited is not a pre-registration. | `preregistrations/`, `archive/` |
| **generated** | Produced by code. **Never hand-edit the body**; regenerate it. | `reference/PROTOCOL_CARD.md` |

Every file carries a `doc-meta` header block declaring its type, when it was last verified, and
the run artefacts its numbers come from.

---

## Read order

**New to the project?** `../README.md` (what the harness is) → `../PROJECTSTATE.md` (where we
are) → `paper/PAPER_BACKBONE.md` (what we are writing).

**Checking a number?** `paper/CLAIM_EVIDENCE_MATRIX.md` — every claim carries its artefact key.
Never trust a number quoted in prose without it.

**Wondering why something was done?** `../DECISIONS.md` (D-nnn) → `../EXPERIMENT_LOG.md` (runs).

---

## Root — living ledgers

| file | lifecycle | what it is |
|---|---|---|
| [`../README.md`](../README.md) | living | what the harness is, the two-stage design, how to run it |
| [`../PROJECTSTATE.md`](../PROJECTSTATE.md) | living | **single source of truth for current state.** Research state + system state |
| [`../TODO.md`](../TODO.md) | living | what is not done, ordered by what blocks what |
| [`../DECISIONS.md`](../DECISIONS.md) | ledger | numbered design decisions D-001…, referenced from code as `D-nnn` |
| [`../EXPERIMENT_LOG.md`](../EXPERIMENT_LOG.md) | ledger | one entry per run: command, run id, cost, conclusion. **Chronological, so it contains superseded numbers** |
| [`../UPSTREAM.md`](../UPSTREAM.md) | living | the four read-only upstream repos, pinned by commit SHA |

## `paper/` — the paper being written

| file | lifecycle | what it is |
|---|---|---|
| [`paper/FRAMEWORK.md`](paper/FRAMEWORK.md) | living | the formal position: notation, Proposition 1, Lemma 2, claims C1–C5 with falsifiers |
| [`paper/PAPER_BACKBONE.md`](paper/PAPER_BACKBONE.md) | living | one-sentence paper, three claims, contributions, figure plan, section order |
| [`paper/CLAIM_EVIDENCE_MATRIX.md`](paper/CLAIM_EVIDENCE_MATRIX.md) | living | **the authoritative numbers.** Every claim with its artefact key, counter-evidence and status |

## `literature/` — external knowledge

| file | lifecycle | what it is |
|---|---|---|
| [`literature/LITERATURE_REVIEW.md`](literature/LITERATURE_REVIEW.md) | living | routing / delegation methods. ⚠️ **Partly unverified** — one entry (`Nash-CredMAS`) does not exist; six more unchecked |
| [`literature/ROUTING_ARCHITECTURES.md`](literature/ROUTING_ARCHITECTURES.md) | living | nine routing methods compared by mechanism and metric |
| [`literature/NOVELTY_BOUNDARY.md`](literature/NOVELTY_BOUNDARY.md) | living | boundary against the **measurement-audit** literature |
| [`literature/RW_router.md`](literature/RW_router.md) | living | author-supplied taxonomy of 16 routing papers, with this project's two readings of it |
| [`literature/ENSEMBLING_NOVELTY.md`](literature/ENSEMBLING_NOVELTY.md) | living | ⚠️ **the ensembling and conformity check, 2026-08-14. Every headline claim the project holds is already published; every entry verified by fetching the arXiv record** |

## `reference/` — generated facts about the system

| file | lifecycle | what it is |
|---|---|---|
| [`reference/PROTOCOL_CARD.md`](reference/PROTOCOL_CARD.md) | generated | each protocol's cost profile and observability, emitted from the registry so it cannot drift from code |

## `preregistrations/` — frozen before running

Named `YYYY-MM-DD-<slug>.md`. **Never edited after the run**; that is the whole point. Results
go in `EXPERIMENT_LOG.md` and a `DECISIONS.md` entry, not back into the pre-registration.

| file | status |
|---|---|
| [`preregistrations/2026-08-11-pool-sweep.md`](preregistrations/2026-08-11-pool-sweep.md) | run 2026-08-13 → D-040. P1/P5/P6 confirmed, P2 ambiguous, P3 refuted on its threshold, P4 partial |
| [`preregistrations/2026-08-13-rq2-rq5.md`](preregistrations/2026-08-13-rq2-rq5.md) | run 2026-08-13 → D-041. All four negative; the one GO trigger failed its own audit. **NO-GO** |
| [`preregistrations/2026-08-13-positive-selection.md`](preregistrations/2026-08-13-positive-selection.md) | run 2026-08-13 → D-042. E1 failed, E2 proved the budget win is arbitrage, E3 flipped two verdicts, E4 left one live claim |
| [`preregistrations/2026-08-13-judge-replication.md`](preregistrations/2026-08-13-judge-replication.md) | run 2026-08-14 → D-043. J1–J4 all met; `independent_judge` replicates in six pools of six. $34.16 |
| [`preregistrations/2026-08-14-judge-on-easy-tasks.md`](preregistrations/2026-08-14-judge-on-easy-tasks.md) | run 2026-08-14 → D-044. H1 and H4 refuted, **H2 fires**: the judge answers rather than aggregates. $5.44 |

## `archive/` — historical, superseded, never updated

Named `YYYY-MM-DD-<slug>.md`. Kept because they record what was believed at the time.

| file | what it is | why archived |
|---|---|---|
| [`archive/2026-08-04-design-report.md`](archive/2026-08-04-design-report.md) | the original three-project design report | its project selection was overtaken by events; its **decision rules remain instructive** |
| [`archive/2026-08-10-governance-report.md`](archive/2026-08-10-governance-report.md) | full account of the governance phase | §1–§12 still accurate. ⚠️ **§10.6's verdict "delegation GO" was retired by D-029/D-030** |

## Reading the 2026-08-13/14 sequence

Five pre-registrations were written and run in two days, each answering the previous one's open
question. Read them in order — pool sweep (D-040) → RQ2–RQ5 (D-041) → positive selection (D-042) →
judge replication (D-043) → judge on easy tasks (D-044) — and note that **all five were written
before their data existed**.

Three of them record something that fired and was then killed by its own audit: D-041's Q3b
criterion (a starved baseline), D-042's smoke test (a per-pool argmax over six pools), and D-044's
cascade (proposed in-session on data from which the deciding tasks had been filtered out). That
pattern is the point of the sequence, not an embarrassment in it.

**Which document to trust for a number:** `paper/CLAIM_EVIDENCE_MATRIX.md`. `paper/FRAMEWORK.md` §8
for claims and falsifiers. `paper/PAPER_BACKBONE.md` is **superseded** and marked so.

---

## Conventions

- **Numbers carry provenance.** Any document quoting a figure names the artefact key it came
  from. `paper/CLAIM_EVIDENCE_MATRIX.md` does this per row; follow that pattern.
- **Run versions live in `run_meta.json`** inside each `data/runs/<run-id>/` — pool, manifest
  content-hash, price snapshot, upstream pins. That is the authoritative version record;
  `PROJECTSTATE.md` §A5 indexes it.
- **Superseded means labelled, not deleted.** Mark what replaced it and when.
- **Do not write a new state report.** Update `PROJECTSTATE.md`.
