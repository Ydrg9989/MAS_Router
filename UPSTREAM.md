# Upstream reference repositories

The four repositories in this workspace are **read-only references**. `mas_harness`
never modifies them. They are gitignored by this repository and pinned here by
commit SHA so that any behaviour we depend on can be reproduced exactly.

| Directory | Upstream | Pinned commit | Date |
|---|---|---|---|
| `multi-agent-teams-hold-experts-back/` | https://github.com/apappu97/multi-agent-teams-hold-experts-back | `a8833a2` | 2026-05-27 |
| `agent-psychometrics/` | https://github.com/dariakryvosheieva/agent-psychometrics | `8c882718` | 2026-07-25 |
| `agent-scaling/` | https://github.com/ybkim95/agent-scaling | `6f3bfb7` | 2026-05-26 |
| `TwinRouterBench/` | https://github.com/CommonstackAI/TwinRouterBench | `430acec` | 2026-07-10 |

Verify the pins at any time with `python -m mas_harness.doctor`.

## What we take from each, and how

### `multi-agent-teams-hold-experts-back` — imported as a library

Added to the venv import path via
`.venv/lib/python3.12/site-packages/upstream_teamwork.pth`. This deliberately
avoids `pip install -e`, which would pull in `wandb`, `hydra-core` and `omegaconf`
that only the upstream `experiments/` runners need.

We import **only the task and evaluator surface**:

- `teamwork.tasks.math_500_problem_task.Math500ProblemTask`
- `teamwork.tasks.gpqa_diamond_problem_task.GPQADiamondProblemTask`
- `teamwork.tasks.mmlu_pro_problem_task.MMLUProProblemTask`

and from their base classes the methods `get_task_description`,
`get_ground_truth`, `_extract_answer`, `_normalize_answer`, `_is_equiv`.

We **never** call `Task.execute()`. That method fuses the interaction protocol
into the task and re-collects independent answers on every invocation; see
`DECISIONS.md` D-001.

Two upstream behaviours are deliberately suppressed, both in
`mas_harness/tasks/adapters.py`:

1. `use_llm_fallback=False` — upstream `_check_equiv_with_llm` fires an
   unlogged, uncosted `gpt-5` request from inside the scorer.
2. Ground-truth expert reveal is not used as the default expert; see D-004.

### `TwinRouterBench` — vendored code

`swerouter/usage.py` and `swerouter/pricing.py` were adapted (not imported) into
`mas_harness/clients/usage.py` and `mas_harness/clients/pricing.py`. Vendoring
rather than importing avoids depending on `tiktoken`/`tokenizers`/`swebench`, and
the provenance header in each file records the upstream origin.

### `agent-psychometrics` — data and statistics

Read directly from disk, no import:

- `data/swebench_verified/responses.jsonl` — 134 agents x 500 tasks, density 1.0
- `data/terminalbench/responses.jsonl` — 112 x 89, with `model`/`agent_org` metadata
- `data/swebench_pro/responses.jsonl` — 14 x 730
- `data/gso/responses.jsonl` — 15 x 102

Used by `mas_harness/analysis/free_pilot.py` as a zero-cost substrate for the
coalition analysis code. Its `py_irt/` fork needs `pyro-ppl`, which is in the
optional `irt` extra and not installed by default.

### `agent-scaling` — patterns only

No code or data dependency. The decorator-registry shape in
`agent_scaling/agents/registry.py` informed `mas_harness/protocols/registry.py`.
