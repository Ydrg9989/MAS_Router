<!-- doc-meta
type:          living
lifecycle:     update-in-place — add a row whenever a document is added
last-verified: 2026-08-11
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
| [`literature/NOVELTY_BOUNDARY.md`](literature/NOVELTY_BOUNDARY.md) | living | boundary against the **measurement-audit** literature, which is what this paper actually competes with |

## `reference/` — generated facts about the system

| file | lifecycle | what it is |
|---|---|---|
| [`reference/PROTOCOL_CARD.md`](reference/PROTOCOL_CARD.md) | generated | each protocol's cost profile and observability, emitted from the registry so it cannot drift from code |

## `preregistrations/` — frozen before running

Named `YYYY-MM-DD-<slug>.md`. **Never edited after the run**; that is the whole point. Results
go in `EXPERIMENT_LOG.md` and a `DECISIONS.md` entry, not back into the pre-registration.

| file | status |
|---|---|
| [`preregistrations/2026-08-11-pool-sweep.md`](preregistrations/2026-08-11-pool-sweep.md) | **not yet run** — 70-pool sweep, six predictions with refutation branches |

## `archive/` — historical, superseded, never updated

Named `YYYY-MM-DD-<slug>.md`. Kept because they record what was believed at the time.

| file | what it is | why archived |
|---|---|---|
| [`archive/2026-08-04-design-report.md`](archive/2026-08-04-design-report.md) | the original three-project design report | its project selection was overtaken by events; its **decision rules remain instructive** |
| [`archive/2026-08-10-governance-report.md`](archive/2026-08-10-governance-report.md) | full account of the governance phase | §1–§12 still accurate. ⚠️ **§10.6's verdict "delegation GO" was retired by D-029/D-030** |

---

## Conventions

- **Numbers carry provenance.** Any document quoting a figure names the artefact key it came
  from. `paper/CLAIM_EVIDENCE_MATRIX.md` does this per row; follow that pattern.
- **Run versions live in `run_meta.json`** inside each `data/runs/<run-id>/` — pool, manifest
  content-hash, price snapshot, upstream pins. That is the authoritative version record;
  `PROJECTSTATE.md` §A5 indexes it.
- **Superseded means labelled, not deleted.** Mark what replaced it and when.
- **Do not write a new state report.** Update `PROJECTSTATE.md`.
