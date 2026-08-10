"""Stage A: build the answer bank.

One independent answer per (task, agent, seed), written append-only with resume. This is the
only stage that necessarily spends money on generation, and every protocol, coalition and
causal intervention downstream reads from what it produces (D-001).

    python -m mas_harness.runners.answer_bank --manifest data/manifests/mvp90.json \
        --pool configs/pools/openrouter4.yaml --run-id mvp90-r1 --dry-run
    python -m mas_harness.runners.answer_bank --manifest data/manifests/mvp90.json \
        --pool configs/pools/openrouter4.yaml --run-id mvp90-r1

Always dry-run first. It prints the exact call count and a priced estimate from the live
snapshot without issuing a single request.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from tqdm import tqdm

from .. import config
from ..clients.base import BudgetExceeded, SpendLedger
from ..clients.openrouter import ChatClient
from ..clients.pricing import PricingTable, load_or_fetch, step_cost_usd
from ..clients.usage import UsageBuckets
from ..pool.agents import Agent, AgentPool
from ..protocols.base import independent_prompt
from ..records.schema import AnswerRecord, CallRecord, RunMeta, UsageDict, answer_key_str
from ..records.writer import JsonlWriter, RunDirectory, to_parquet
from ..tasks.adapters import TaskSpec, build_evaluator
from ..tasks.distributed import check_pool_matches
from ..tasks.manifest import Manifest

# Planning figures, used only by --dry-run, and measured rather than assumed. The research
# report's guesses of 1,200 input and 500 output were both wrong; so was the first correction,
# because it came from an easy suite. These come from probe-fixed, 48 calls on hard GPQA
# questions with the token and termination fixes in place: 308 input, 4,169 output.
#
# Output length tracks task difficulty far more than input length does, and this project
# deliberately selects hard tasks (D-020), so estimating from an easy suite understates cost
# by roughly a factor of three. See EXPERIMENT_LOG.md.
PLANNED_INPUT_TOKENS = 300
PLANNED_OUTPUT_TOKENS = 4_200


def plan(
    manifest: Manifest, pool: AgentPool, seeds: Sequence[int], done: set[str]
) -> list[tuple[TaskSpec, Agent, int]]:
    """Every (task, agent, seed) still to be generated, in a stable order."""
    work: list[tuple[TaskSpec, Agent, int]] = []
    for spec in manifest.tasks:
        for agent in pool:
            for seed in seeds:
                if answer_key_str(spec.task_id, agent.agent_id, seed) in done:
                    continue
                work.append((spec, agent, seed))
    return work


def estimate_cost(
    work: Sequence[tuple[TaskSpec, Agent, int]], pricing: PricingTable
) -> tuple[float, dict[str, int]]:
    """Priced estimate under the report's token assumptions, per model."""
    usage = UsageBuckets(PLANNED_INPUT_TOKENS, 0, 0, PLANNED_OUTPUT_TOKENS)
    total = 0.0
    counts: dict[str, int] = {}
    for _, agent, _ in work:
        counts[agent.model] = counts.get(agent.model, 0) + 1
        if agent.provider != "openrouter":
            continue
        # A missing price is reported by the caller rather than guessed at.
        with contextlib.suppress(KeyError):
            total += step_cost_usd(usage, pricing.get(agent.model))
    return total, counts


def committed(finish_reason: str | None) -> bool:
    """Whether the model actually finished, so its answer represents a conclusion.

    Only a natural stop counts. A response cut off by the token cap, or terminated by a
    provider error, was still mid-thought when it ended, and scraping a letter out of it does
    not recover an answer the model never gave.

    This is not hypothetical. In the probe-gpqa run Gemini 2.5 Flash ran to the 24,576-token
    cap on 5 of 12 questions, emitting 88,000 characters of unterminated chemistry
    exploration. Three of those still yielded a letter under strict extraction, because the
    text is full of provisional lines like "this would give B" written while enumerating
    possibilities the model went on to reject. The extractor takes the last match, which in a
    truncated stream is wherever the guillotine fell — not a conclusion.

    Recording those as answers would be worse than losing them. A wrong answer and a
    non-answer are different events, and only the second is honestly an abstention. Silently
    converting the first into the second inflates the error rate of exactly those agents that
    reason at length, which is the same verbosity bias that D-018 exists to prevent.
    """
    return finish_reason in (None, "stop", "end_turn", "eos", "stop_sequence")


async def generate_one(
    client: ChatClient,
    spec: TaskSpec,
    agent: Agent,
    seed: int,
    *,
    run_id: str,
) -> AnswerRecord:
    evaluator = build_evaluator(spec)
    messages = independent_prompt(spec, agent)
    response = await client.chat(
        model=agent.model,
        messages=messages,
        provider=agent.provider,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        seed=seed,
        extra_body=agent.extra_body or None,
    )
    diagnostics = evaluator.extraction_diagnostics(response.text)
    extracted = "" if not committed(response.finish_reason) else diagnostics["strict"]
    return AnswerRecord(
        run_id=run_id,
        task_id=spec.task_id,
        suite=spec.suite,
        domain=spec.domain,
        agent_id=agent.agent_id,
        agent_name=agent.name,
        model=agent.model,
        provider=agent.provider,
        seed=seed,
        text=response.text,
        extracted_answer=extracted,
        ground_truth=spec.ground_truth,
        correct=evaluator.score_extracted(extracted),
        parse_failed=not extracted,
        call=CallRecord(
            stage="independent",
            agent_id=agent.agent_id,
            model=agent.model,
            provider=response.provider,
            model_returned=response.model_returned,
            usage=UsageDict(**response.usage.to_dict()),
            cost_usd=response.cost_usd,
            provider_reported_cost_usd=response.reconciliation.reported_usd,
            cost_agrees=response.reconciliation.agrees,
            latency_ms=response.latency_ms,
            prompt_hash=response.prompt_hash,
            cached=response.cached,
            attempts=response.attempts,
            generation_id=response.generation_id,
            finish_reason=response.finish_reason,
        ),
    )


async def run_stage_a(
    *,
    manifest: Manifest,
    pool: AgentPool,
    seeds: Sequence[int],
    run_id: str,
    runs_root: Path,
    concurrency: int,
    dry_run: bool,
    refresh_prices: bool,
    resume: bool = True,
) -> dict:
    run_dir = RunDirectory(runs_root, run_id)
    # Checked before planning, and before --dry-run reports anything, because a pool/manifest
    # mismatch invalidates the run rather than merely mispricing it.
    check_pool_matches(manifest.tasks, [a.agent_id for a in pool])
    done = run_dir.completed_answer_keys() if resume else set()
    work = plan(manifest, pool, seeds, done)

    pricing = load_or_fetch(run_dir.pricing_path, refresh=refresh_prices)
    pricing = pricing.with_free_models([a.model for a in pool if a.provider == "vllm"])
    missing_prices = [
        a.model for a in pool if a.provider == "openrouter" and a.model not in pricing
    ]

    estimated, per_model = estimate_cost(work, pricing)
    summary = {
        "run_id": run_id,
        "n_tasks": len(manifest.tasks),
        "n_agents": len(pool),
        "seeds": list(seeds),
        "n_planned_calls": len(work),
        "n_already_done": len(done),
        "estimated_cost_usd": estimated,
        "calls_per_model": per_model,
        "missing_prices": missing_prices,
        "pricing_captured_at": pricing.captured_at,
    }

    if dry_run:
        summary["dry_run"] = True
        return summary

    if missing_prices:
        raise RuntimeError(
            f"no live price for {missing_prices}; refusing to spend against an unknown rate. "
            f"Fix the slugs in the pool YAML or rerun with --refresh-prices."
        )

    budget = config.BudgetConfig.from_env()
    ledger = SpendLedger(
        config.SPEND_LEDGER,
        run_id=run_id,
        run_budget_usd=budget.run_usd,
        daily_budget_usd=budget.daily_usd,
    )
    run_dir.write_meta(
        RunMeta(
            run_id=run_id,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            stage="A",
            manifest_path=str(manifest.manifest_id),
            manifest_hash=manifest.content_hash,
            pool_id=pool.pool_id,
            pool_hash=pool.content_hash,
            seeds=list(seeds),
            pricing_snapshot=str(run_dir.pricing_path),
            pricing_captured_at=pricing.captured_at,
            upstream_pins=config.UPSTREAM_PINS,
            git_commit=config.git_commit(),
        )
    )

    writer = JsonlWriter(run_dir.answers_path)
    stopped_early: str | None = None

    async with ChatClient(
        pricing=pricing,
        ledger=ledger,
        cache_dir=config.CACHE_DIR / "responses",
        max_concurrency=concurrency,
    ) as client:
        semaphore = asyncio.Semaphore(concurrency)
        progress = tqdm(total=len(work), desc=f"stage A [{run_id}]", unit="call")

        async def worker(item: tuple[TaskSpec, Agent, int]) -> None:
            nonlocal stopped_early
            spec, agent, seed = item
            async with semaphore:
                if stopped_early:
                    return
                try:
                    record = await generate_one(client, spec, agent, seed, run_id=run_id)
                except BudgetExceeded as exc:
                    # Stop cleanly: everything already written stays valid and resumable.
                    stopped_early = str(exc)
                    return
                except Exception as exc:
                    progress.write(
                        f"  failed {spec.task_id} / {agent.name} / seed {seed}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    return
                writer.write(record)
                progress.update(1)

        await asyncio.gather(*(worker(item) for item in work))
        progress.close()
        summary["client_stats"] = client.stats()

    writer.close()
    summary["stopped_early"] = stopped_early
    summary["n_written"] = writer.n_written
    summary["actual_cost_usd"] = ledger.run_spend_usd
    summary["answers_path"] = str(run_dir.answers_path)

    if writer.n_written:
        summary["parquet_path"] = str(to_parquet(run_dir.answers_path))

    records = run_dir.load_answers()
    if records:
        summary["accuracy_by_agent"] = {
            agent.name: round(
                sum(r.correct for r in records if r.agent_id == agent.agent_id)
                / max(1, sum(1 for r in records if r.agent_id == agent.agent_id)),
                4,
            )
            for agent in pool
        }
        summary["parse_failure_rate"] = round(
            sum(r.parse_failed for r in records) / len(records), 4
        )
        # Reported per agent and separately from parse failures, because the two have
        # different causes and different remedies. A parse failure can mean the model
        # declined; an unfinished response means we never heard the answer, and a rate that
        # concentrates in one agent is a property of that model rather than of the tasks.
        unfinished = [r for r in records if not committed(r.call.finish_reason)]
        summary["unfinished_rate"] = round(len(unfinished) / len(records), 4)
        if unfinished:
            summary["unfinished_by_agent"] = {
                agent.name: round(
                    sum(1 for r in unfinished if r.agent_id == agent.agent_id)
                    / max(1, sum(1 for r in records if r.agent_id == agent.agent_id)),
                    4,
                )
                for agent in pool
                if any(r.agent_id == agent.agent_id for r in unfinished)
            }
        summary["cost_reconciliation_disagreements"] = sum(
            1 for r in records if not r.call.cost_agrees
        )
    return summary


def print_summary(summary: dict) -> None:
    print(f"\nStage A [{summary['run_id']}]")
    print(
        f"  scope        : {summary['n_tasks']} tasks x {summary['n_agents']} agents "
        f"x {len(summary['seeds'])} seed(s)"
    )
    print(
        f"  calls        : {summary['n_planned_calls']} planned, "
        f"{summary['n_already_done']} already banked"
    )
    if summary.get("missing_prices"):
        print(f"  MISSING PRICE: {summary['missing_prices']}")
    print(
        f"  est. cost    : ${summary['estimated_cost_usd']:.2f} at "
        f"{PLANNED_INPUT_TOKENS} in / {PLANNED_OUTPUT_TOKENS} out tokens per call "
        f"(prices captured {summary['pricing_captured_at']})"
    )
    for model, count in sorted(summary.get("calls_per_model", {}).items()):
        print(f"      {count:5d}  {model}")

    if summary.get("dry_run"):
        print("\n  dry run: nothing was sent. Drop --dry-run to execute.")
        return

    print(f"  written      : {summary['n_written']} records -> {summary['answers_path']}")
    print(f"  actual cost  : ${summary['actual_cost_usd']:.4f}")
    if summary.get("client_stats"):
        cache = summary["client_stats"]["cache"]
        print(f"  cache        : {cache['hits']} hits, {cache['misses']} misses")
    if summary.get("stopped_early"):
        print(f"  STOPPED EARLY: {summary['stopped_early']}")
    if "accuracy_by_agent" in summary:
        print("  accuracy     :")
        for name, accuracy in summary["accuracy_by_agent"].items():
            print(f"      {accuracy:.3f}  {name}")
        print(f"  parse failures: {summary['parse_failure_rate']:.3f}")
        if summary.get("unfinished_rate"):
            print(
                f"  UNFINISHED    : {summary['unfinished_rate']:.3f} of responses hit the token "
                f"cap or errored, and are recorded as abstentions, not answers"
            )
            for name, rate in (summary.get("unfinished_by_agent") or {}).items():
                print(f"      {rate:.3f}  {name}")
        if summary.get("cost_reconciliation_disagreements"):
            print(
                f"  COST MISMATCH : {summary['cost_reconciliation_disagreements']} calls where "
                f"our figure and the provider's disagree by more than 2%"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage A: build the answer bank")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--limit", type=int, default=None, help="use only the first N tasks")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true", help="plan and price, send nothing")
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--runs-root", default=str(config.RUNS_DIR))
    args = parser.parse_args(argv)

    config.load_env()
    manifest = Manifest.read(args.manifest)
    if args.limit:
        manifest.tasks = manifest.tasks[: args.limit]
    pool = AgentPool.from_yaml(args.pool)

    summary = asyncio.run(
        run_stage_a(
            manifest=manifest,
            pool=pool,
            seeds=args.seeds,
            run_id=args.run_id,
            runs_root=Path(args.runs_root),
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            refresh_prices=args.refresh_prices,
            resume=not args.no_resume,
        )
    )
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
