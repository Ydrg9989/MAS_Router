"""Stage B: run protocols and coalitions over an existing answer bank.

Reads the Stage-A bank, fits the predicted expert on the calibration split only (D-004), then
sweeps the requested protocols, coalitions, seeds and interventions. Two of the five MVP
protocols make no model calls, so a large part of this stage is free (D-009).

    # free: aggregation-only protocols over every coalition
    python -m mas_harness.runners.episodes --run-id mvp90-r1 --pool configs/pools/openrouter4.yaml \
        --manifest data/manifests/mvp90.json --protocols single_expert independent_majority \
        --coalitions all

    # priced: plan first
    python -m mas_harness.runners.episodes --run-id mvp90-r1 --pool configs/pools/openrouter4.yaml \
        --manifest data/manifests/mvp90.json --protocols debate_vote independent_judge \
        expert_verifier --coalitions grand --interventions masks --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from tqdm import tqdm

from .. import config
from ..clients.base import BudgetExceeded, SpendLedger
from ..clients.openrouter import ChatClient
from ..clients.pricing import PricingTable, load_or_fetch, step_cost_usd
from ..clients.usage import UsageBuckets
from ..interventions import edits
from ..pool.agents import AgentPool, all_nonempty_coalitions, coalitions_of_size
from ..pool.expert import (
    ExpertPredictor,
    Strategy,
    fit_expert_predictor,
    observations_from_records,
    oracle_expert,
)
from ..pool.roles import role_rotations
from ..protocols import (
    FREE_PROTOCOLS,
    MVP_PROTOCOLS,
    PROPOSED_PAIRS,
    ProtocolContext,
    available_protocols,
    get_protocol,
)
from ..records.schema import (
    AnswerRecord,
    EpisodeRecord,
    InterventionSpec,
    RunMeta,
    episode_key_str,
)
from ..records.writer import JsonlWriter, RunDirectory, to_parquet
from ..tasks.adapters import TaskSpec, build_evaluator
from ..tasks.manifest import Manifest

# Planning figures measured on hard tasks (probe-fixed, 48 calls), not assumed and not taken
# from an easy suite. See EXPERIMENT_LOG.md.
PLANNED_INPUT_TOKENS = 300
PLANNED_OUTPUT_TOKENS = 4_200

# An aggregator prompt carries the task plus every member's *full* answer, so its size is set
# by how verbose the members were, not by the task. At a measured 4,169 output tokens per
# member on hard questions, a four-member coalition puts roughly 16,700 tokens of peer answers
# in front of the aggregator. This figure matters more than any other here, because the
# aggregator is the most expensive model in the pool and is the only input that grows with
# coalition size.
PLANNED_AGGREGATOR_BASE_TOKENS = 500
PLANNED_PEER_ANSWER_TOKENS = 4_200


class Bank:
    """Indexed view over Stage-A records."""

    def __init__(self, records: Sequence[AnswerRecord]):
        self.records = list(records)
        self._by_key: dict[tuple[str, int, int], AnswerRecord] = {
            (r.task_id, r.agent_id, r.seed): r for r in records
        }
        self._by_task: dict[str, list[AnswerRecord]] = {}
        for record in records:
            self._by_task.setdefault(record.task_id, []).append(record)

    def for_coalition(
        self, task_id: str, coalition: Sequence[int], seed: int
    ) -> dict[int, AnswerRecord] | None:
        """Banked answers for exactly these members, or None if any is missing.

        Falls back to seed 0 for a member banked only at the default seed, so a multi-seed
        protocol sweep does not require a multi-seed bank.
        """
        out: dict[int, AnswerRecord] = {}
        for agent_id in coalition:
            record = self._by_key.get((task_id, agent_id, seed)) or self._by_key.get(
                (task_id, agent_id, 0)
            )
            if record is None:
                return None
            out[agent_id] = record
        return out

    def donors(self, task_id: str) -> list[AnswerRecord]:
        return self._by_task.get(task_id, [])

    def task_ids(self) -> list[str]:
        return sorted(self._by_task)


def resolve_coalitions(pool: AgentPool, mode: str, size: int | None) -> list[list[int]]:
    if mode == "all":
        return all_nonempty_coalitions(pool.agent_ids)
    if mode == "grand":
        return [sorted(pool.agent_ids)]
    if mode == "singletons":
        return [[a] for a in sorted(pool.agent_ids)]
    if mode == "size":
        if not size:
            raise ValueError("--coalition-size is required when --coalitions size is used")
        return coalitions_of_size(pool.agent_ids, size)
    raise ValueError(f"unknown coalition mode {mode!r}")


def resolve_interventions(
    mode: str, coalition: Sequence[int], *, seed: int, n_permutations: int
) -> list[InterventionSpec]:
    if mode == "none":
        return [InterventionSpec(kind="none")]
    if mode == "masks":
        return [InterventionSpec(kind="none"), *edits.mask_interventions(coalition)]
    if mode == "substitutions":
        return [
            InterventionSpec(kind="none"),
            *edits.substitution_interventions(coalition, correct=True),
        ]
    if mode == "reorder":
        return [
            InterventionSpec(kind="none"),
            *edits.reorder_interventions(coalition, n_permutations=n_permutations, seed=seed),
        ]
    if mode == "all":
        return edits.intervention_plan(coalition, n_permutations=n_permutations, seed=seed)
    raise ValueError(f"unknown intervention mode {mode!r}")


def _mean_member_call_cost(pool: AgentPool, pricing: PricingTable, input_tokens: int) -> float:
    """Cost of one member call at the planning token figures, averaged over the pool.

    Averaging is the right approximation here because which member speaks depends on the
    protocol and on the calibration fit, neither of which the planner knows.
    """
    usage = UsageBuckets(input_tokens, 0, 0, PLANNED_OUTPUT_TOKENS)
    prices = [
        step_cost_usd(usage, pricing.get(a.model))
        for a in pool
        if a.provider == "openrouter" and a.model in pricing
    ]
    return sum(prices) / len(prices) if prices else 0.0


def _prompt_tokens_carrying(n_peer_answers: int) -> int:
    """Size of a prompt that quotes ``n_peer_answers`` full member answers.

    Every interactive protocol builds its prompt this way, so cost scales with coalition
    size and with how verbose the members were — not with the task, which is short.
    """
    return PLANNED_AGGREGATOR_BASE_TOKENS + n_peer_answers * PLANNED_PEER_ANSWER_TOKENS


def _aggregator_call_cost(pool: AgentPool, pricing: PricingTable, n_peer_answers: int) -> float:
    aggregator = pool.aggregator
    if aggregator is None or aggregator.model not in pricing:
        return 0.0
    usage = UsageBuckets(_prompt_tokens_carrying(n_peer_answers), 0, 0, PLANNED_OUTPUT_TOKENS)
    return step_cost_usd(usage, pricing.get(aggregator.model))


def estimate_episode_cost(
    protocol_id: str, coalition_size: int, rounds: int, pool: AgentPool, pricing: PricingTable
) -> float:
    """Planning estimate for one episode of one protocol.

    Deliberately an upper bound for the protocols that can finish early: ``expert_veto`` and
    ``chair_information_seeking`` skip calls when a challenge concedes or the chair asks
    nothing, and a plan that under-promises is safer than one that surprises the budget.
    """
    info = get_protocol(protocol_id)
    n_calls = info.calls_per_episode(coalition_size, rounds)
    if n_calls == 0:
        return 0.0

    if protocol_id == "independent_judge":
        return _aggregator_call_cost(pool, pricing, coalition_size)

    if protocol_id == "chair_information_seeking":
        # Two chair calls carrying every member's answer, plus the capped member replies,
        # whose prompts hold only one prior answer and the question.
        n_replies = max(0, n_calls - 2)
        return 2 * _aggregator_call_cost(
            pool, pricing, coalition_size
        ) + n_replies * _mean_member_call_cost(pool, pricing, _prompt_tokens_carrying(1))

    # Member calls whose prompt carries the other members' answers (debate, verification).
    return n_calls * _mean_member_call_cost(
        pool, pricing, _prompt_tokens_carrying(max(1, coalition_size - 1))
    )


def fit_predictor(
    bank: Bank, manifest: Manifest, *, strategy: Strategy
) -> ExpertPredictor:
    calibration = manifest.splits.get("calibration") or []
    if not calibration:
        raise ValueError(
            f"manifest {manifest.manifest_id!r} has no calibration split; e_hat cannot be "
            f"fitted without one (D-004)"
        )
    banked_calibration = [t for t in calibration if t in set(bank.task_ids())]
    if not banked_calibration:
        raise ValueError(
            "Stage A covered none of the calibration split, so e_hat cannot be fitted. "
            "Run Stage A over the full manifest, not just the test split."
        )
    return fit_expert_predictor(
        observations_from_records(bank.records),
        strategy=strategy,
        calibration_task_ids=banked_calibration,
    )


def read_task_subset(path: str | None) -> list[str] | None:
    """Task ids from a discrimination report or a bare JSON list.

    The discriminating tasks and the drift control sample are unioned deliberately: the control
    is not a spare, it is the sample that tests the assumption that unanimous tasks cannot
    change under a protocol, and dropping it would make that assumption unfalsifiable.
    """
    if path is None:
        return None
    payload = json.loads(Path(path).read_text())
    if isinstance(payload, list):
        return [str(t) for t in payload]
    selection = payload.get("selection")
    if not isinstance(selection, dict):
        raise ValueError(
            f"{path} is neither a JSON list of task ids nor a discrimination report "
            f"with a 'selection' object"
        )
    return sorted(
        {*selection.get("stage_b_tasks", []), *selection.get("control_tasks", [])}
    )


def resolve_pools(pool: AgentPool, *, role_rotation: bool) -> list[AgentPool]:
    """The pools to run: just the given one, or its Latin-square role rotations.

    Rotation exists to break the confound between model identity and role: if one family
    always verifies, a "verifier effect" and a "family effect" are the same number. The
    rotations carry distinct pool ids, so their episodes are separate records rather than
    colliding in the resume set.
    """
    if not role_rotation:
        return [pool]
    return [rotated for _, rotated in role_rotations(pool)]


async def run_stage_b(
    *,
    manifest: Manifest,
    pool: AgentPool,
    run_id: str,
    runs_root: Path,
    protocols: Sequence[str],
    coalition_mode: str,
    coalition_size: int | None,
    intervention_mode: str,
    n_permutations: int,
    seeds: Sequence[int],
    rounds: int,
    expert_strategy: Strategy,
    concurrency: int,
    dry_run: bool,
    test_split_only: bool,
    resume: bool = True,
    role_rotation: bool = False,
    only_task_ids: Sequence[str] | None = None,
) -> dict:
    run_dir = RunDirectory(runs_root, run_id)
    bank = Bank(run_dir.load_answers())
    if not bank.records:
        raise FileNotFoundError(
            f"no Stage-A answers in {run_dir.answers_path}. Run "
            f"`python -m mas_harness.runners.answer_bank --run-id {run_id} ...` first."
        )

    predictor = fit_predictor(bank, manifest, strategy=expert_strategy)
    competence = dict(predictor.accuracy_global)

    tasks = manifest.tasks
    if test_split_only:
        test_ids = set(manifest.splits.get("test") or [])
        tasks = [t for t in tasks if t.task_id in test_ids]
    # Applied after the predictor is fitted, so restricting which tasks get episodes never
    # changes which answers calibrate e_hat. Stage A is already paid for; narrowing Stage B
    # to the tasks that can discriminate must not narrow the expert's evidence.
    if only_task_ids is not None:
        wanted = set(only_task_ids)
        unknown = wanted - {t.task_id for t in tasks}
        if unknown:
            raise ValueError(
                f"{len(unknown)} requested task id(s) are not in the manifest "
                f"(first few: {sorted(unknown)[:3]})"
            )
        tasks = [t for t in tasks if t.task_id in wanted]
    tasks = [t for t in tasks if t.task_id in set(bank.task_ids())]

    coalitions = resolve_coalitions(pool, coalition_mode, coalition_size)
    pools = resolve_pools(pool, role_rotation=role_rotation)
    done = run_dir.completed_episode_keys() if resume else set()

    # Enumerate the work up front so cost can be priced before anything is sent.
    Work = tuple[AgentPool, TaskSpec, str, list[int], int, InterventionSpec]
    work: list[Work] = []
    for spec in tasks:
        for coalition in coalitions:
            if bank.for_coalition(spec.task_id, coalition, 0) is None:
                continue
            for protocol_id in protocols:
                # Free protocols read no role instructions, so rotating roles would produce
                # byte-identical episodes under different keys. Run them once.
                active_pools = [pool] if protocol_id in FREE_PROTOCOLS else pools
                interventions = (
                    resolve_interventions(
                        intervention_mode, coalition, seed=0, n_permutations=n_permutations
                    )
                    # Interventions on a single-member coalition are degenerate.
                    if len(coalition) > 1
                    else [InterventionSpec(kind="none")]
                )
                for active in active_pools:
                    for seed in seeds:
                        for intervention in interventions:
                            key = episode_key_str(
                                spec.task_id,
                                active.pool_id,
                                protocol_id,
                                coalition,
                                seed,
                                intervention.label(),
                            )
                            if key in done:
                                continue
                            work.append(
                                (active, spec, protocol_id, coalition, seed, intervention)
                            )

    pricing = load_or_fetch(run_dir.pricing_path)
    pricing = pricing.with_free_models([a.model for a in pool if a.provider == "vllm"])
    estimated = sum(
        estimate_episode_cost(protocol_id, len(coalition), rounds, active, pricing)
        for active, _, protocol_id, coalition, _, _ in work
    )
    per_protocol: dict[str, int] = {}
    for _, _, protocol_id, _, _, _ in work:
        per_protocol[protocol_id] = per_protocol.get(protocol_id, 0) + 1

    summary = {
        "run_id": run_id,
        "n_tasks": len(tasks),
        "n_coalitions": len(coalitions),
        "n_role_rotations": len(pools),
        "protocols": list(protocols),
        "seeds": list(seeds),
        "intervention_mode": intervention_mode,
        "n_planned_episodes": len(work),
        "n_already_done": len(done),
        "episodes_per_protocol": per_protocol,
        "estimated_cost_usd": estimated,
        "free_episodes": sum(1 for _, _, p, _, _, _ in work if p in FREE_PROTOCOLS),
        "expert_predictor": predictor.to_dict(),
    }

    if dry_run:
        summary["dry_run"] = True
        return summary

    budget = config.BudgetConfig.from_env()
    needs_client = any(p not in FREE_PROTOCOLS for p in protocols)
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
            stage="B",
            manifest_path=manifest.manifest_id,
            manifest_hash=manifest.content_hash,
            pool_id=pool.pool_id,
            pool_hash=pool.content_hash,
            seeds=list(seeds),
            protocols=list(protocols),
            pricing_snapshot=str(run_dir.pricing_path),
            pricing_captured_at=pricing.captured_at,
            upstream_pins=config.UPSTREAM_PINS,
            git_commit=config.git_commit(),
            notes=(
                f"expert_strategy={expert_strategy}; interventions={intervention_mode}; "
                f"role_rotations={[p.pool_id for p in pools]}"
            ),
        )
    )

    writer = JsonlWriter(run_dir.episodes_path)
    stopped_early: str | None = None
    client: ChatClient | None = None

    async def execute(item: Work) -> None:
        nonlocal stopped_early
        active_pool, spec, protocol_id, coalition, seed, intervention = item
        if stopped_early:
            return

        raw_bank = bank.for_coalition(spec.task_id, coalition, seed)
        if raw_bank is None:
            return
        evaluator = build_evaluator(spec)
        edited = edits.apply(
            raw_bank, intervention, task=spec, donor_pool=bank.donors(spec.task_id), seed=seed
        )
        correct_by_agent = {a: bool(r.correct) for a, r in raw_bank.items()}

        context = ProtocolContext(
            spec=spec,
            evaluator=evaluator,
            pool=active_pool,
            coalition=list(coalition),
            seed=seed,
            bank=edited,
            predicted_expert_id=predictor.predict(domain=spec.domain, coalition=coalition),
            oracle_expert_id=oracle_expert(correct_by_agent, coalition=coalition),
            intervention=intervention,
            competence=competence,
            client=client,
            max_rounds=rounds,
        )

        try:
            result = await get_protocol(protocol_id).fn(context)
        except BudgetExceeded as exc:
            stopped_early = str(exc)
            return
        except Exception as exc:
            tqdm.write(
                f"  failed {spec.task_id} / {protocol_id} / {coalition} / "
                f"{intervention.label()}: {type(exc).__name__}: {exc}"
            )
            return

        writer.write(
            EpisodeRecord(
                run_id=run_id,
                task_id=spec.task_id,
                suite=spec.suite,
                domain=spec.domain,
                pool_id=active_pool.pool_id,
                protocol_id=protocol_id,
                coalition=sorted(coalition),
                seed=seed,
                intervention=intervention,
                final_text=result.final_text,
                final_answer=result.final_answer,
                ground_truth=spec.ground_truth,
                correct=evaluator.score_extracted(result.final_answer),
                parse_failed=not result.final_answer,
                individual_correct={str(a): v for a, v in sorted(correct_by_agent.items())},
                predicted_expert_id=context.predicted_expert_id,
                oracle_expert_id=context.oracle_expert_id,
                protocol_meta=result.meta,
                n_calls=len(result.calls),
                total_cost_usd=result.total_cost_usd,
                total_latency_ms=result.total_latency_ms,
                usage=result.total_usage(),
                calls=result.calls,
                transcript=result.transcript,
            )
        )

    progress = tqdm(total=len(work), desc=f"stage B [{run_id}]", unit="episode")

    async def guarded(item: Work) -> None:
        async with semaphore:
            await execute(item)
            progress.update(1)

    semaphore = asyncio.Semaphore(concurrency)
    if needs_client:
        async with ChatClient(
            pricing=pricing,
            ledger=ledger,
            cache_dir=config.CACHE_DIR / "responses",
            max_concurrency=concurrency,
        ) as active:
            client = active
            await asyncio.gather(*(guarded(item) for item in work))
            summary["client_stats"] = active.stats()
    else:
        await asyncio.gather(*(guarded(item) for item in work))
    progress.close()

    writer.close()
    summary["stopped_early"] = stopped_early
    summary["n_written"] = writer.n_written
    summary["actual_cost_usd"] = ledger.run_spend_usd
    summary["episodes_path"] = str(run_dir.episodes_path)
    if writer.n_written:
        summary["parquet_path"] = str(to_parquet(run_dir.episodes_path))

    episodes = run_dir.load_episodes()
    observational = [e for e in episodes if e.intervention.kind == "none"]
    if observational:
        summary["accuracy_by_protocol"] = {
            protocol_id: round(
                sum(e.correct for e in observational if e.protocol_id == protocol_id)
                / max(1, sum(1 for e in observational if e.protocol_id == protocol_id)),
                4,
            )
            for protocol_id in sorted({e.protocol_id for e in observational})
        }
    return summary


def print_summary(summary: dict) -> None:
    print(f"\nStage B [{summary['run_id']}]")
    print(
        f"  scope       : {summary['n_tasks']} tasks x {summary['n_coalitions']} coalitions "
        f"x {len(summary['protocols'])} protocols x {len(summary['seeds'])} seed(s), "
        f"interventions={summary['intervention_mode']}, "
        f"role rotations={summary.get('n_role_rotations', 1)}"
    )
    for protocol_id, baseline in sorted(PROPOSED_PAIRS.items()):
        if protocol_id in summary["protocols"] and baseline not in summary["protocols"]:
            print(
                f"  WARNING     : {protocol_id} was run without its baseline {baseline}. The "
                f"comparison will confound the governance rule with the extra calls."
            )
    print(
        f"  episodes    : {summary['n_planned_episodes']} planned "
        f"({summary['free_episodes']} free), {summary['n_already_done']} already done"
    )
    for protocol_id, count in sorted(summary["episodes_per_protocol"].items()):
        marker = " (free)" if protocol_id in FREE_PROTOCOLS else ""
        print(f"      {count:6d}  {protocol_id}{marker}")
    print(f"  est. cost   : ${summary['estimated_cost_usd']:.2f}")
    predictor = summary["expert_predictor"]
    print(
        f"  e_hat       : strategy={predictor['strategy']}, global={predictor['global_expert']}, "
        f"{len(predictor['by_domain'])} domain overrides, fitted on "
        f"{predictor['n_calibration_tasks']} calibration tasks"
    )

    if summary.get("dry_run"):
        print("\n  dry run: nothing was sent. Drop --dry-run to execute.")
        return

    print(f"  written     : {summary['n_written']} episodes -> {summary['episodes_path']}")
    print(f"  actual cost : ${summary['actual_cost_usd']:.4f}")
    if summary.get("stopped_early"):
        print(f"  STOPPED EARLY: {summary['stopped_early']}")
    if "accuracy_by_protocol" in summary:
        print("  accuracy (observational episodes only):")
        for protocol_id, accuracy in summary["accuracy_by_protocol"].items():
            print(f"      {accuracy:.3f}  {protocol_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage B: run protocols over the answer bank")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--protocols", nargs="+", default=MVP_PROTOCOLS, choices=available_protocols()
    )
    parser.add_argument(
        "--coalitions", default="grand", choices=["all", "grand", "singletons", "size"]
    )
    parser.add_argument("--coalition-size", type=int, default=None)
    parser.add_argument(
        "--interventions",
        default="none",
        choices=["none", "masks", "substitutions", "reorder", "all"],
    )
    parser.add_argument("--n-permutations", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--rounds", type=int, default=2, help="debate rounds including round 0")
    parser.add_argument(
        "--expert-strategy", default="domain", choices=["global", "domain"]
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--test-split-only",
        action="store_true",
        help="restrict to the manifest test split, keeping calibration unused for reporting",
    )
    parser.add_argument(
        "--role-rotation",
        action="store_true",
        help=(
            "run every Latin-square role rotation, so role and model family are crossed "
            "rather than nested. Multiplies the priced episode count by the pool size."
        ),
    )
    parser.add_argument(
        "--tasks-from",
        default=None,
        help=(
            "restrict episodes to a task subset: a discrimination.json (its "
            "selection.stage_b_tasks plus selection.control_tasks are used) or a JSON list "
            "of task ids. e_hat is still calibrated on the whole bank."
        ),
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--runs-root", default=str(config.RUNS_DIR))
    args = parser.parse_args(argv)

    config.load_env()
    summary = asyncio.run(
        run_stage_b(
            manifest=Manifest.read(args.manifest),
            pool=AgentPool.from_yaml(args.pool),
            run_id=args.run_id,
            runs_root=Path(args.runs_root),
            protocols=args.protocols,
            coalition_mode=args.coalitions,
            coalition_size=args.coalition_size,
            intervention_mode=args.interventions,
            n_permutations=args.n_permutations,
            seeds=args.seeds,
            rounds=args.rounds,
            expert_strategy=args.expert_strategy,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            test_split_only=args.test_split_only,
            resume=not args.no_resume,
            role_rotation=args.role_rotation,
            only_task_ids=read_task_subset(args.tasks_from),
        )
    )
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
