<!-- doc-meta
type:          living
lifecycle:     update-in-place
last-verified: 2026-08-14
evidence-base: none (describes the harness, not results)
-->

# MAS Harness

A shared experiment harness for research on **heterogeneous multi-agent LLM systems**.
Every experiment in this repository has the same shape:

```
task  x  agent pool  x  protocol / coalition  x  seed
      ->  outcome, transcript, cost, latency, metadata
```

One dataset produced by this harness feeds all three research directions described in
[`Docs/archive/2026-08-04-design-report.md`](Docs/archive/2026-08-04-design-report.md):
epistemic governance, delegation-equivalent task representations, and coalition
landscapes.

> ## Status, 2026-08-14
>
> **The empirical programme is complete and no paper is currently supportable from it.**
> All three directions closed on evidence, the delegation direction twice — once at n=3 pools and
> again at n=280 with four further research questions. The two results that survive on their own
> terms are a methodological negative about oracle headroom and a mechanism about what reading peer
> answers does to a strong model. **Both are already published by others**, mapped claim by claim in
> [`Docs/literature/ENSEMBLING_NOVELTY.md`](Docs/literature/ENSEMBLING_NOVELTY.md).
>
> Total spend **$139.78** of ~€3,000. 486 tests pass. Six pre-registrations, all written before their
> data existed; the sixth was implemented, tested, and then stopped by its own novelty gate for $0.
>
> Start at [`PROJECTSTATE.md`](PROJECTSTATE.md). Numbers come from
> [`Docs/paper/CLAIM_EVIDENCE_MATRIX.md`](Docs/paper/CLAIM_EVIDENCE_MATRIX.md) and nowhere else.
> [`Docs/paper/PAPER_BACKBONE.md`](Docs/paper/PAPER_BACKBONE.md) is **superseded and closed** — do
> not draft from it.

## The two-stage design

The single most important design decision is that **independent answers are produced
once and then replayed**.

```
Stage A (paid once)                 Stage B (cheap, replayed)
-------------------                 -------------------------
for each (task, agent, seed):       for each (task, pool, protocol, seed):
    independent answer          ->      read the bank, run only the
    -> data/runs/<run>/answers.jsonl    interaction + aggregation calls
                                     -> data/runs/<run>/episodes.jsonl
```

This matters for three reasons:

- **Cost.** Five protocols over 90 tasks would otherwise re-pay for the independent
  phase five times. Protocols 1 and 2 (calibrated single expert, independent
  majority) need *zero* extra API calls once the bank exists, which makes enumerating
  all 15 coalitions of a 4-agent pool nearly free.
- **Statistical validity.** Every protocol sees byte-identical independent answers, so
  protocol comparisons are exactly paired and McNemar's test is applicable.
- **Causal interventions.** `do(M_i = M_i^+)` is a Stage-B replay over a fixed bank, so
  masking, substituting or reordering a message only re-pays the interaction calls.

The upstream `teamwork` package fuses the protocol into the task and re-collects
answers inside every `Task.execute()` call, which is why we use it only as a task and
evaluator library. See `DECISIONS.md` D-001.

## Layout

```
mas_harness/
  clients/        OpenRouter + vLLM async client, response cache, token/USD accounting
  tasks/          immutable manifests, splits, teamwork evaluator adapters,
                  distributed-information condition by option-set partitioning
  pool/           agent pool definitions (model slug, provider, role, temperature)
  protocols/      protocol registry: 7 governance protocols over the answer bank
  interventions/  message masking / substitution / order permutation
  runners/        stage A (answer bank), stage B (episodes), grid driver
  records/        pydantic record schemas, JSONL+Parquet writer with resume
  metrics/        governance, delegation, coalition metrics + statistical tests
  analysis/       zero-cost free pilot, go/no-go gate, figures
configs/
  pools/          agent pool YAML
  protocols/      protocol parameter YAML
  suites/         task suite + experiment grid YAML
data/
  manifests/      immutable task manifests and splits (tracked)
  cache/          content-addressed LLM response cache (gitignored)
  runs/           answers.jsonl / episodes.jsonl per run (gitignored)
```

## Setup

```bash
cd /data/yiderigun/MAS_Router
export UV_CACHE_DIR=$PWD/.uv-cache TMPDIR=$PWD/.tmp
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev,figures]"

# Put the upstream teamwork package on the import path (already done once):
SP=$(.venv/bin/python -c "import site;print(site.getsitepackages()[0])")
echo "$PWD/multi-agent-teams-hold-experts-back" > "$SP/upstream_teamwork.pth"

cp .env.example .env    # then fill in OPENROUTER_API_KEY
```

Check the whole installation, including upstream pins, dataset availability, GPU
presence and API reachability:

```bash
.venv/bin/python -m mas_harness.doctor
```

## Walkthrough

### 1. Free pilot — validate the analysis code at zero cost

Before spending any budget, the entire coalition analysis pipeline is validated on a
real, fully dense outcome matrix that already exists on disk: 134 agents x 500 tasks
from `agent-psychometrics`.

```bash
.venv/bin/python -m mas_harness.analysis.free_pilot --benchmark swebench_verified --n-agents 4
```

This computes pairwise synergy, Harsanyi dividends, the higher-order interaction ratio
`R_{>=3}`, submodularity violation rates, error correlation, the top-k gap, and a
task-conditioned pairwise factorization — with no API calls.

### 2. Build task manifests

```bash
.venv/bin/python -m mas_harness.tasks.manifest build --suite configs/suites/mvp90.yaml
```

Manifests are immutable: each is content-hashed and refuses to be silently
overwritten. MATH-500, GPQA-Diamond and MMLU-Pro are read from the local
HuggingFace cache, so this step needs no network.

Two further suites build the **distributed-information condition**, which replaces the
unobtainable HiddenBench (D-010). Each question's option set is split across the four
members so that only one of them can see the correct option — a member that cannot see it
provably cannot state it, which separates "wrong for lack of evidence" from "wrong for lack
of ability".

```bash
.venv/bin/python -m mas_harness.tasks.manifest build --suite configs/suites/distributed30.yaml
.venv/bin/python -m mas_harness.tasks.manifest build \
    --suite configs/suites/distributed30_pressure.yaml
```

The two arms share a seed, so they draw the same questions and the same partitions and differ
only in what members are told: the first warns them and lets them decline, the second does
neither. Run and report both. On its own the cooperative arm shows that plurality voting
survives — but only because the lone holder is the only member voting, which is a fact about
calibration rather than about protocols (D-015).

### 3. Stage A — the answer bank

```bash
.venv/bin/python -m mas_harness.runners.answer_bank \
    --manifest data/manifests/mvp90.json \
    --pool configs/pools/openrouter4.yaml \
    --seeds 0 --run-id pilot01
```

### 4. Stage B — protocol episodes

Seven protocols are registered. The first five are the report's MVP baselines; the last
two are its proposed interventions, each deliberately paired with the baseline it differs
from by exactly one rule.

| Protocol | Calls per episode (4 agents) | Paired against |
|---|---:|---|
| `single_expert` | 0 | — |
| `independent_majority` | 0 | — |
| `independent_judge` | 1 | — |
| `expert_verifier` | 2 | — |
| `debate_vote` | 4 per extra round | `independent_majority` |
| `expert_veto` | 1 | `expert_verifier` |
| `chair_information_seeking` | 2–4 | `independent_judge` |

```bash
.venv/bin/python -m mas_harness.runners.episodes \
    --run-id pilot01 --manifest data/manifests/mvp90.json \
    --pool configs/pools/openrouter4.yaml \
    --protocols single_expert independent_majority debate_vote independent_judge \
                expert_verifier
```

Coalition enumeration, interventions and role rotation are extra axes on the same runner.
Always plan a priced sweep with `--dry-run` first.

```bash
# free: every one of the 15 non-empty coalitions, no API calls at all
... --protocols single_expert independent_majority --coalitions all

# causal influence: one baseline plus one masked message per member
... --protocols debate_vote --coalitions grand --interventions masks --dry-run

# break the role-vs-family confound: four Latin-square rotations
... --protocols expert_verifier expert_veto --role-rotation --dry-run
```

`--interventions` takes `none`, `masks`, `substitutions`, `reorder` or `all`.

### 5. Go / no-go gate

```bash
.venv/bin/python -m mas_harness.analysis.gonogo --run-id pilot01 \
    --manifest data/manifests/mvp90.json --pool configs/pools/openrouter4.yaml
```

This evaluates the report's continue and kill thresholds for all three directions and
prints a recommendation, so the day-14 project selection is mechanical rather than a
judgement call. A criterion whose evidence was never collected is reported as
`INSUFFICIENT`, never as a kill.

## Cost control

Every request records both our locally computed USD cost (four token buckets x a price
snapshot taken at run start) and the cost OpenRouter itself reports, then reconciles
them. Guards, in order of firing:

1. **Cache.** Content-addressed on `(model, messages, temperature, max_tokens, seed)`.
   A repeated request costs nothing.
2. **Run budget.** `MAS_RUN_BUDGET_USD` — the client refuses a request that would push
   the run's cumulative cost past the cap.
3. **Daily budget.** `MAS_DAILY_BUDGET_USD`, tracked across runs in
   `data/runs/spend_ledger.jsonl`.
4. **`--dry-run`** prints the projected call count and cost without issuing anything.

## Project documents

- `PROJECTSTATE.md` — what currently exists and what runs
- `DECISIONS.md` — numbered design decisions with rationale
- `EXPERIMENT_LOG.md` — append-only record of every run
- `TODO.md` — remaining work
- `UPSTREAM.md` — the four reference repos, pinned, and exactly what we take
