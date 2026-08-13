"""Step 1: from six pool-by-suite cells to every four-agent pool the bank supports.

Pre-registered in `Docs/preregistrations/2026-08-11-pool-sweep.md`, predictions locked
2026-08-11. Every claim in the claim-evidence matrix rests on n = 3 pools per
suite and three of them have exactly one dissenting cell each; at n = 3 a 2-versus-1 split is a coin
toss. `single_expert` and `independent_majority` make no model calls, so C(8,4) = 70 pools on
`crosscap240` and C(10,4) = 210 on `hard366` are computable from the existing answer bank for $0.

The design decision that makes this more than a loop: **the null is joint**. The 70 pools are drawn
from 8 agents, so two pools sharing three members are nearly the same pool. `sharing_null` simulates
at the agent level, so one simulated bank yields a statistic for every pool at once and repeating it
gives the null distribution of the *whole sweep*, with member sharing across pools exact by
construction. That is the correction arXiv 2607.20768 identifies in its 31,900 overlapping subsets
and does not make.

Everything downstream of the reconstruction runs through the *existing* measurement code, by
synthesising the episode records a real Stage B would have written. That is what makes section 9's
verification gate meaningful: if the three named pools reproduce their published numbers, the
generalised driver is the same instrument and not a lookalike.

    python scripts/measure_pool_sweep.py --suite crosscap240
    python scripts/measure_pool_sweep.py --suite hard366 --splits 40
"""

from __future__ import annotations

import os

# One BLAS thread per process, set before numpy is imported. Each pool is an independent process, so
# the parallelism is already at the pool level; leaving BLAS free to thread as well oversubscribes
# the machine by the product of the two and the sweep runs several times slower. An explicit setting
# from the caller wins.
for _variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(_variable, "1")

import argparse  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from collections import defaultdict  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from typing import Any, Sequence  # noqa: E402

import numpy as np  # noqa: E402

from mas_harness import config  # noqa: E402
from mas_harness.clients.pricing import PricingTable, step_cost_usd  # noqa: E402
from mas_harness.metrics.interaction import interaction_likelihood_ratio  # noqa: E402
from mas_harness.metrics.pool_sweep import (  # noqa: E402
    CoalitionIndex,
    Substrate,
    SweepNull,
    additive_agent_model,
    build_substrate,
    check_vote_agreement,
    expert_table,
    global_order,
    headroom,
    organization_outcomes,
    pool_coalitions,
    simulate_bank,
    vote_outcomes,
)
from mas_harness.metrics.routing import routing_over_splits  # noqa: E402
from mas_harness.metrics.sharing_null import build_task_spaces  # noqa: E402
from mas_harness.records.schema import EpisodeRecord, InterventionSpec  # noqa: E402
from mas_harness.records.writer import RunDirectory  # noqa: E402
from mas_harness.tasks.adapters import build_evaluator  # noqa: E402
from mas_harness.tasks.manifest import Manifest  # noqa: E402

FREE_PROTOCOLS = ("single_expert", "independent_majority")
VOTE = "independent_majority"
EXPERT = "single_expert"

SUITES = {
    "crosscap240": {
        "manifest": "crosscap240.json",
        # The three named pools, whose numbers the section 9 gate must reproduce.
        "named": {
            "strong4": "crosscap-strong4",
            "decorrelated4": "crosscap-decorr4",
            "correlated4": "crosscap-corr4",
        },
        # Every run whose Stage A bank covers this suite; their union is the agent set.
        "banks": ["crosscap-strong4", "crosscap-decorr4", "crosscap-corr4"],
    },
    "hard366": {
        "manifest": "hard366.json",
        "named": {
            "strong4": "strong4-a",
            "decorrelated4": "decorr4-a",
            "correlated4": "correlated4-a",
        },
        "banks": ["strong4-a", "decorr4-a", "correlated4-a", "hard366-a", "cand4-a"],
    },
}


# ---- loading ----------------------------------------------------------------------------------


def _usable(record: Any) -> bool:
    """Did this call produce an answer at all, as opposed to failing to return one?

    D-019 scores an unfinished response as an abstention and D-028 records non-termination as
    *missing data* rather than a wrong answer. When the same agent and task appear in two runs and
    one of them errored, the error is therefore the less informative record, not a competing draw.
    """
    return not record.parse_failed and record.call.finish_reason not in {None, "", "error"}


def load_suite(
    suite: str,
    *,
    priority: Sequence[str] | None = None,
    only_priority: bool = False,
    agents: Sequence[str] | None = None,
    with_embeddings: bool = True,
) -> tuple[Substrate, list, dict[str, str], Any, dict[str, Any]]:
    """Build the agent-by-task substrate from every run whose bank covers this suite.

    **An agent appearing in two runs does not necessarily carry the same banked answer.** At
    temperature 0 the two draws ought to be identical, and 92-95% of the time they are, but 13 to 20
    of 240 tasks differ per agent pair — provider non-determinism plus a handful of failed calls.
    The sweep needs one coherent bank, so one record per (agent, task) is chosen by a stated rule:
    a call that returned an answer beats one that errored, and ties go to the earlier run in
    ``priority``. The disagreement is measured and returned rather than silently resolved, because
    it is a second seed hiding in the data and it bears on every one-seed caveat in the project.

    ``priority`` puts a run's own answers first and ``only_priority`` excludes every other run,
    which is what the section 9 gate needs: a named pool must be scored on the bank its episodes
    were actually generated from, including where that bank is missing a task the others cover.
    """
    spec = SUITES[suite]
    order_of_runs = list(priority) if priority else list(spec["banks"])
    if not only_priority:
        order_of_runs += [r for r in spec["banks"] if r not in order_of_runs]

    manifest = Manifest.read(config.DATA_DIR / "manifests" / spec["manifest"])
    by_id = manifest.by_id()
    evaluators = {task_id: build_evaluator(s) for task_id, s in by_id.items()}
    domain_of = {s.task_id: s.domain for s in manifest.tasks}

    candidates: dict[str, dict[str, list[tuple[int, Any, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for rank, run_id in enumerate(order_of_runs):
        directory = RunDirectory(config.RUNS_DIR, run_id)
        prices = PricingTable.read(config.RUNS_DIR / run_id / "pricing_snapshot.json")
        for record in directory.load_answers():
            if record.task_id not in evaluators:
                continue
            candidates[record.agent_name][record.task_id].append(
                (rank, record, step_cost_usd(record.call.usage, prices.get(record.model)))
            )

    answers_by_agent: dict[str, dict[str, Any]] = defaultdict(dict)
    cost_by_agent: dict[str, dict[str, float]] = defaultdict(dict)
    records_by_agent: dict[str, dict[str, Any]] = defaultdict(dict)
    repeated = disagreeing = differing_answer = 0
    for name, tasks in candidates.items():
        for task, drawn in tasks.items():
            if len(drawn) > 1:
                repeated += 1
                disagreeing += int(len({bool(r.correct) for _, r, _ in drawn}) > 1)
                # Two draws can agree on correctness and still differ in *which* wrong answer they
                # gave, which changes the equivalence classes and therefore the vote.
                differing_answer += int(
                    len({(r.extracted_answer or "").strip() for _, r, _ in drawn}) > 1
                )
            rank, record, cost = min(drawn, key=lambda d: (not _usable(d[1]), d[0]))
            answers_by_agent[name][task] = bool(record.correct)
            cost_by_agent[name][task] = cost
            records_by_agent[name][task] = record

    replication = {
        "n_repeated_agent_tasks": repeated,
        "n_disagreeing_on_correctness": disagreeing,
        "n_differing_answer_text": differing_answer,
        "disagreement_rate": disagreeing / repeated if repeated else 0.0,
        "answer_difference_rate": differing_answer / repeated if repeated else 0.0,
        "bank_priority": order_of_runs,
    }

    # One global id space, derived from the named pools so that plurality tie-breaks and the expert
    # predictor's `-a` reproduce the recorded episodes exactly.
    pool_orders: dict[str, list[str]] = {}
    for pool, run_id in spec["named"].items():
        seen: dict[int, str] = {}
        for record in RunDirectory(config.RUNS_DIR, run_id).load_answers():
            seen.setdefault(record.agent_id, record.agent_name)
        pool_orders[pool] = [seen[i] for i in sorted(seen)]
    order = global_order(pool_orders)
    order = order + sorted(set(answers_by_agent) - set(order))

    allowed = set(agents) if agents is not None else None
    dense = [
        a
        for a in order
        if (allowed is None or a in allowed) and len(answers_by_agent[a]) >= 0.98 * len(evaluators)
    ]

    # Equivalence classes are built once per task from every agent's answer, using each agent's
    # global id, so the class structure is shared by every pool in the sweep.
    space_agent_ids = {name: i for i, name in enumerate(dense)}
    flat = [
        records_by_agent[name][task].model_copy(update={"agent_id": space_agent_ids[name]})
        for name in dense
        for task in records_by_agent[name]
    ]
    spaces = build_task_spaces(flat, evaluators)

    substrate = build_substrate(
        suite=suite,
        answers_by_agent=answers_by_agent,
        cost_by_agent=cost_by_agent,
        spaces=spaces,
        space_agent_ids=space_agent_ids,
        domain_of=domain_of,
        calibration_task_ids=manifest.splits["calibration"],
        test_task_ids=manifest.splits["test"],
        agent_order=dense,
    )

    space = None
    if with_embeddings:
        from mas_harness.metrics.delegation import semantic_space

        space = semantic_space(substrate.tasks, [by_id[t].prompt for t in substrate.tasks])
        substrate.embeddings = space.features
        substrate.embedding_method = space.method
        substrate.embedding_fallback = space.fallback_used

    ordered_spaces = [spaces[t] for t in substrate.tasks]
    return substrate, ordered_spaces, domain_of, space, replication


# ---- episode synthesis ------------------------------------------------------------------------


def synthesize(
    pool: tuple[int, ...], substrate: Substrate, index: CoalitionIndex, votes: np.ndarray
) -> list[EpisodeRecord]:
    """The episode records a real Stage B would have written for this pool.

    Written so the sweep can hand the *existing* measurement functions their normal input rather
    than a parallel implementation of them. Cost follows `measure_cost_frontier.consulted`: a vote
    over k members pays for k, an expert pays for the one member it consults.
    """
    coalitions = pool_coalitions(pool)
    experts = expert_table(pool, substrate)
    rows = np.array([index.position[c] for c in coalitions])
    vote_block = votes[rows]
    chosen = experts[:, substrate.domain_index]
    expert_block = np.take_along_axis(substrate.correct, chosen, axis=0)

    pool_id = "sweep-" + "-".join(map(str, pool))
    clean = InterventionSpec()
    records: list[EpisodeRecord] = []
    for row, coalition in enumerate(coalitions):
        members = list(coalition)
        vote_cost = substrate.cost[members].sum(axis=0)
        expert_cost = np.take_along_axis(substrate.cost, chosen[row][None, :], axis=0)[0]
        for protocol, outcomes, spend in (
            (VOTE, vote_block[row], vote_cost),
            (EXPERT, expert_block[row], expert_cost),
        ):
            for t, task in enumerate(substrate.tasks):
                records.append(
                    EpisodeRecord(
                        run_id="pool_sweep",
                        task_id=task,
                        suite=substrate.suite,
                        domain=substrate.domain_of_task[t],
                        pool_id=pool_id,
                        protocol_id=protocol,
                        coalition=members,
                        seed=0,
                        intervention=clean,
                        final_text="",
                        final_answer="",
                        ground_truth="",
                        correct=bool(outcomes[t]),
                        parse_failed=False,
                        predicted_expert_id=int(chosen[row, t]),
                        protocol_meta={"selected_agent_id": int(chosen[row, t])}
                        if protocol == EXPERT
                        else {},
                        total_cost_usd=float(spend[t]),
                    )
                )
    return records


# ---- per-pool statistics ----------------------------------------------------------------------


def descriptors(pool: tuple[int, ...], substrate: Substrate) -> dict[str, float]:
    """The regressors of prediction P4, all measured on calibration tasks only."""
    members = list(pool)
    columns = substrate.calibration
    correct = substrate.correct[np.ix_(members, columns)]
    accuracy = correct.mean(axis=1)

    errors = 1.0 - correct
    correlations = []
    for i, j in itertools.combinations(range(len(members)), 2):
        a, b = errors[i], errors[j]
        if a.std() < 1e-12 or b.std() < 1e-12:
            continue
        correlations.append(float(np.corrcoef(a, b)[0, 1]))

    logit = np.log(np.clip(accuracy, 1e-3, 1 - 1e-3) / (1 - np.clip(accuracy, 1e-3, 1 - 1e-3)))
    price = substrate.cost[np.ix_(members, columns)].mean(axis=1)

    # How concentrated a task's wrong answers are, averaged over calibration tasks: the quantity the
    # sharp null preserves, because convergence on one distractor can outvote a correct minority.
    # Reported as the largest share of the wrong answers falling on a single class.
    concentration = []
    for t in columns:
        wrong = [
            substrate.classes[a, t]
            for a in members
            if substrate.classes[a, t] not in (-1, substrate.correct_class[t])
        ]
        if len(wrong) > 1:
            counts = np.array([wrong.count(w) for w in set(wrong)], dtype=float)
            concentration.append(float(counts.max() / counts.sum()))
    return {
        "mean_member_accuracy": float(accuracy.mean()),
        "ability_spread": float(accuracy.max() - accuracy.min()),
        "ability_range_logit": float(logit.max() - logit.min()),
        "mean_pairwise_error_correlation": (
            float(np.mean(correlations)) if correlations else float("nan")
        ),
        "double_fault_rate": float(
            np.mean(
                [
                    float(np.mean(errors[i] * errors[j]))
                    for i, j in itertools.combinations(range(len(members)), 2)
                ]
            )
        ),
        "distractor_concentration": (
            float(np.mean(concentration)) if concentration else float("nan")
        ),
        "cost_spread_usd": float(price.max() - price.min()),
        "mean_cost_usd": float(price.mean()),
    }


def _afford(accuracy: np.ndarray, spend: np.ndarray, budget: float) -> int | None:
    feasible = np.flatnonzero(spend <= budget * (1 + 1e-9))
    if feasible.size == 0:
        return None
    return int(feasible[np.lexsort((spend[feasible], -accuracy[feasible]))[0]])


def budget_comparison(
    outcomes: np.ndarray,
    cost: np.ndarray,
    domain_index: np.ndarray,
    calibration: np.ndarray,
    test: np.ndarray,
    n_splits: int,
    seed: int,
) -> dict[str, Any]:
    """Routed minus global at matched budget, at the loosest and tightest budgets.

    The same instrument as `measure_cost_frontier`, reduced to the two ends of the curve that
    prediction P6 is about: the unconstrained budget where the field does not deploy routers, and
    the tightest feasible budget where it does.
    """
    budgets = np.unique(np.round(cost.mean(axis=1), 12))
    if not budgets.size:
        return {}
    rng = np.random.default_rng(seed)
    fraction = len(calibration) / (len(calibration) + len(test))

    gains: dict[float, list[float]] = {float(b): [] for b in budgets}
    for _ in range(n_splits):
        left: list[int] = []
        right: list[int] = []
        for d in np.unique(domain_index):
            columns = np.flatnonzero(domain_index == d)
            rng.shuffle(columns)
            cut = max(1, int(round(fraction * len(columns))))
            left.extend(columns[:cut].tolist())
            right.extend(columns[cut:].tolist())
        train, held = np.array(sorted(left)), np.array(sorted(right))

        accuracy = outcomes[:, train].mean(axis=1)
        spend = cost[:, train].mean(axis=1)
        for budget in budgets:
            global_pick = _afford(accuracy, spend, budget)
            if global_pick is None:
                continue
            routed = np.full(outcomes.shape[1], global_pick, dtype=int)
            for d in np.unique(domain_index):
                columns = train[domain_index[train] == d]
                if not columns.size:
                    continue
                local = _afford(
                    outcomes[:, columns].mean(axis=1), cost[:, columns].mean(axis=1), budget
                )
                if local is not None:
                    routed[domain_index == d] = local
            gains[float(budget)].append(
                100.0
                * float(outcomes[routed[held], held].mean() - outcomes[global_pick, held].mean())
            )

    populated = {b: v for b, v in gains.items() if v}
    if not populated:
        return {}
    loosest, tightest = max(populated), min(populated)

    # Lemma 2's diagnostic: Pareto-efficient organizations no linear penalty can reach.
    accuracy = outcomes.mean(axis=1)
    spend = cost.mean(axis=1)
    pareto = [
        i
        for i in range(len(accuracy))
        if not np.any(
            (spend <= spend[i] + 1e-12)
            & (accuracy >= accuracy[i] - 1e-12)
            & ((spend < spend[i] - 1e-12) | (accuracy > accuracy[i] + 1e-12))
        )
    ]
    span = float(spend.max() - spend.min())
    penalties = (
        np.concatenate([[0.0], np.geomspace(0.01 / span, 10.0 / span, 400)])
        if span > 0
        else np.zeros(1)
    )
    reachable = {int(np.argmax(accuracy - p * spend)) for p in penalties}
    return {
        "unconstrained_gain_pp": float(np.mean(populated[loosest])),
        "unconstrained_frac_positive": float(np.mean(np.array(populated[loosest]) > 0)),
        "tightest_gain_pp": float(np.mean(populated[tightest])),
        "tightest_frac_positive": float(np.mean(np.array(populated[tightest]) > 0)),
        "tightest_budget_usd": float(tightest),
        "best_budget_gain_pp": float(max(np.mean(v) for v in populated.values())),
        "n_budgets": len(populated),
        "n_pareto": len(pareto),
        "n_reachable_by_some_lambda": len(reachable),
        "n_pareto_but_unreachable": len(sorted(set(pareto) - reachable)),
    }


def policy_ladder(
    pool: tuple[int, ...],
    substrate: Substrate,
    organizations: np.ndarray,
) -> dict[str, float]:
    """The information ladder, all choices frozen on calibration and scored on test.

    ``capability_router_agents`` is the C2c comparison: each capability's calibration-best *member*,
    against plain majority voting over the same members. ``capability_router_orgs`` gives the same
    router the whole 30-organization family. Both are upper bounds on any learned router whose
    representation is a function of the capability partition, because they are handed the label.
    """
    members = list(pool)
    calibration, test = substrate.calibration, substrate.test
    domain = substrate.domain_index

    def per_capability(table: np.ndarray) -> float:
        picked = np.zeros(len(substrate.tasks), dtype=int)
        overall = int(np.argmax(table[:, calibration].mean(axis=1)))
        picked[:] = overall
        for c in range(len(substrate.capabilities)):
            columns = calibration[domain[calibration] == c]
            if columns.size:
                picked[domain == c] = int(np.argmax(table[:, columns].mean(axis=1)))
        return float(table[picked[test], test].mean())

    agents = substrate.correct[members]
    whole_pool = organizations[len(pool_coalitions(pool)) - 1]  # the grand coalition's vote row

    calibration_means = organizations[:, calibration].mean(axis=1)
    fixed = int(np.argmax(calibration_means))
    best_agent = int(np.argmax(agents[:, calibration].mean(axis=1)))

    return {
        "best_single_agent": float(agents[best_agent, test].mean()),
        "best_fixed_organization": float(organizations[fixed, test].mean()),
        "whole_pool_vote": float(whole_pool[test].mean()),
        "capability_router_agents": per_capability(agents),
        "capability_router_orgs": per_capability(organizations),
        "oracle": float(organizations[:, test].max(axis=0).mean()),
    }


def evaluate_pool(payload: tuple) -> dict[str, Any]:
    """Everything measured for one pool. Runs in a worker process."""
    pool, substrate, index, votes, space, domains, n_splits, n_interaction, seed = payload
    started = time.time()

    organizations = organization_outcomes(
        pool,
        substrate=substrate,
        index=index,
        votes=votes,
        agent_correct=substrate.correct,
        experts=expert_table(pool, substrate),
    )
    observed_vs_picked, observed = headroom(organizations, substrate.calibration, substrate.test)

    record: dict[str, Any] = {
        "pool": list(pool),
        "members": [substrate.agents[a] for a in pool],
        "observed_headroom_over_best": float(observed),
        "observed_headroom_over_picked": float(observed_vs_picked),
        "ladder": policy_ladder(pool, substrate, organizations),
        "descriptors": descriptors(pool, substrate),
    }

    episodes = synthesize(pool, substrate, index, votes)
    repeated = routing_over_splits(
        episodes,
        task_space=space,
        domains=domains,
        n_splits=n_splits,
        only_protocols=FREE_PROTOCOLS,
        seed=seed,
    )
    record["routing"] = {
        "n_splits": repeated["n_splits"],
        "oracle_headroom": repeated["oracle_headroom"],
        "selection_gap": repeated["selection_gap"],
        "gain_over_fixed_best": {
            name: entry
            for name, entry in repeated["gain_over_fixed_best"].items()
            if name in {"q_theta", "q_theta_shuffled", "semantic_knn", "oracle",
                        "fixed_best_single_agent", "fixed_best_1se"}
        },
    }

    labels = [f"{VOTE}[{'-'.join(map(str, c))}]" for c in pool_coalitions(pool)] + [
        f"{EXPERT}[{'-'.join(map(str, c))}]" for c in pool_coalitions(pool)
    ]
    capability = dict(zip(substrate.tasks, substrate.domain_of_task, strict=True))
    organization_map = {
        label: dict(zip(substrate.tasks, (bool(v) for v in row), strict=True))
        for label, row in zip(labels, organizations, strict=True)
    }
    agent_map = {
        substrate.agents[a]: dict(
            zip(substrate.tasks, (bool(v) for v in substrate.correct[a]), strict=True)
        )
        for a in pool
    }
    for level, outcomes in (("organizations", organization_map), ("agents", agent_map)):
        result = interaction_likelihood_ratio(
            outcomes, capability, n_simulations=n_interaction, seed=seed
        )
        record.setdefault("interaction", {})[level] = {
            "statistic": result.statistic,
            "degrees_of_freedom": result.degrees_of_freedom,
            "p_value_bootstrap": result.p_value_bootstrap,
            "excess_departure_points": result.excess_departure_points,
            "mean_absolute_departure_points": result.mean_absolute_departure_points,
        }

    coalitions = pool_coalitions(pool)
    experts = expert_table(pool, substrate)
    cost = np.vstack(
        [
            np.array([substrate.cost[list(c)].sum(axis=0) for c in coalitions]),
            np.array(
                [
                    np.take_along_axis(
                        substrate.cost, experts[row][substrate.domain_index][None, :], axis=0
                    )[0]
                    for row in range(len(coalitions))
                ]
            ),
        ]
    )
    record["budget"] = budget_comparison(
        organizations,
        cost,
        substrate.domain_index,
        substrate.calibration,
        substrate.test,
        n_splits=n_splits,
        seed=seed,
    )
    record["seconds"] = time.time() - started
    return record


# ---- the joint null ---------------------------------------------------------------------------


def joint_null(
    substrate: Substrate,
    index: CoalitionIndex,
    pools: list[tuple[int, ...]],
    *,
    n_simulations: int,
    seed: int,
    workers: int,
) -> SweepNull:
    """Simulate the whole bank, score every pool from it, repeat.

    One simulated bank per replicate feeds all pools, so member sharing *across* pools is exact and
    the resulting distribution is that of the entire sweep rather than of one cell.
    """
    probability, abstain_rate = additive_agent_model(substrate)
    experts = {pool: expert_table(pool, substrate) for pool in pools}
    rows = {pool: np.array([index.position[c] for c in pool_coalitions(pool)]) for pool in pools}

    observed_correct = vote_outcomes(
        substrate.classes, index, substrate.competence, substrate.correct_class
    )
    observed = np.stack(
        [
            organization_outcomes(
                pool,
                substrate=substrate,
                index=index,
                votes=observed_correct,
                agent_correct=substrate.correct,
                experts=experts[pool],
            )
            for pool in pools
        ]
    )
    observed_vs_picked, observed_vs_best = headroom(
        observed, substrate.calibration, substrate.test
    )

    chunks = _split_evenly(n_simulations, workers)
    arguments = [
        (substrate, index, pools, probability, abstain_rate, experts, rows, size, seed + i)
        for i, size in enumerate(chunks)
        if size
    ]
    if len(arguments) == 1:
        collected = [_null_chunk(arguments[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(arguments)) as executor:
            collected = list(executor.map(_null_chunk, arguments))

    picked = np.concatenate([c[0] for c in collected])
    best = np.concatenate([c[1] for c in collected])
    return SweepNull(
        pools=pools,
        observed=observed_vs_best,
        observed_vs_picked=observed_vs_picked,
        replicates=best,
        replicates_vs_picked=picked,
        n_simulations=len(best),
    )


def calibration_check(
    substrate: Substrate,
    index: CoalitionIndex,
    pools: list[tuple[int, ...]],
    *,
    n_outer: int,
    n_inner: int,
    seed: int,
    workers: int,
) -> dict[str, Any]:
    """How often does the family-wise test reject when the truth is additive? A double bootstrap.

    The null of :func:`joint_null` is a parametric bootstrap: fit sigma(alpha_a + beta_x) to the
    observed bank, simulate from the fit, compare. That comparison is not exactly exchangeable. The
    fit is penalised (C=10, one parameter per task), so the simulated tables are drawn from a
    *smoother* process than the one that produced the observed table, and the per-task maximum is
    sensitive to exactly that smoothing. The direction is knowable in advance — it inflates observed
    headroom relative to the null — but the size is not, so it is measured here rather than argued.

    Each outer replicate is a bank simulated under the fitted additive model and then treated as if
    it were real: refit, simulate ``n_inner`` inner banks from *its* fit, and compute the same
    family-wise p-value. Under a correctly calibrated test those p-values are uniform and 5% of them
    fall below 0.05. Anything above 5% is the test's false-positive rate on data that is additive by
    construction, and it bounds how much of an observed rejection could be an artefact.
    """
    probability, abstain_rate = additive_agent_model(substrate)
    experts = {pool: expert_table(pool, substrate) for pool in pools}
    rows = {pool: np.array([index.position[c] for c in pool_coalitions(pool)]) for pool in pools}

    chunks = _split_evenly(n_outer, workers)
    arguments = [
        (
            substrate,
            index,
            pools,
            probability,
            abstain_rate,
            experts,
            rows,
            size,
            n_inner,
            seed + 7919 * i,
        )
        for i, size in enumerate(chunks)
        if size
    ]
    if len(arguments) == 1:
        collected = [_calibration_chunk(arguments[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(arguments)) as executor:
            collected = list(executor.map(_calibration_chunk, arguments))

    p_values = np.concatenate(collected)
    return {
        "n_outer": int(len(p_values)),
        "n_inner": n_inner,
        "false_positive_rate_at_05": float(np.mean(p_values <= 0.05)),
        "false_positive_rate_at_10": float(np.mean(p_values <= 0.10)),
        "median_p_value": float(np.median(p_values)),
        "note": (
            "p-values of the family-wise median-excess test on banks that are additive by "
            "construction. 0.05 is calibrated; above it the test over-rejects and an observed "
            "rejection would need discounting. Under-rejection makes a null result conservative."
        ),
    }


def _calibration_chunk(payload: tuple) -> np.ndarray:
    substrate, index, pools, probability, abstain_rate, experts, rows, n_outer, n_inner, seed = (
        payload
    )
    rng = np.random.default_rng(seed)

    def table(classes: np.ndarray, correct: np.ndarray) -> np.ndarray:
        votes = vote_outcomes(classes, index, substrate.competence, substrate.correct_class)
        return np.stack(
            [
                np.vstack(
                    [
                        votes[rows[pool]],
                        np.take_along_axis(
                            correct, experts[pool][:, substrate.domain_index], axis=0
                        ),
                    ]
                )
                for pool in pools
            ]
        )

    p_values = np.empty(n_outer)
    for i in range(n_outer):
        classes, correct = simulate_bank(substrate, probability, abstain_rate, rng)
        pseudo = Substrate(**{**substrate.__dict__, "classes": classes, "correct": correct})
        inner_probability, inner_abstain = additive_agent_model(pseudo)
        _, observed = headroom(table(classes, correct), substrate.calibration, substrate.test)

        inner = np.empty((n_inner, len(pools)))
        for j in range(n_inner):
            inner_classes, inner_correct = simulate_bank(
                pseudo, inner_probability, inner_abstain, rng
            )
            _, inner[j] = headroom(
                table(inner_classes, inner_correct), substrate.calibration, substrate.test
            )
        excess = observed - inner.mean(axis=0)
        reference = np.median(inner - inner.mean(axis=0, keepdims=True), axis=1)
        p_values[i] = (1 + int(np.sum(reference >= np.median(excess)))) / (1 + n_inner)
    return p_values


def _split_evenly(total: int, parts: int) -> list[int]:
    base, remainder = divmod(total, max(parts, 1))
    return [base + (1 if i < remainder else 0) for i in range(max(parts, 1))]


def _null_chunk(payload: tuple) -> tuple[np.ndarray, np.ndarray]:
    substrate, index, pools, probability, abstain_rate, experts, rows, n, seed = payload
    rng = np.random.default_rng(seed)
    picked = np.empty((n, len(pools)))
    best = np.empty((n, len(pools)))
    for i in range(n):
        classes, correct = simulate_bank(substrate, probability, abstain_rate, rng)
        votes = vote_outcomes(classes, index, substrate.competence, substrate.correct_class)
        table = np.stack(
            [
                np.vstack(
                    [
                        votes[rows[pool]],
                        np.take_along_axis(
                            correct, experts[pool][:, substrate.domain_index], axis=0
                        ),
                    ]
                )
                for pool in pools
            ]
        )
        picked[i], best[i] = headroom(table, substrate.calibration, substrate.test)
    return picked, best


# ---- the section 9 gate -----------------------------------------------------------------------


def verification_gate(suite: str) -> dict[str, Any]:
    """The three named pools must reproduce the recorded episodes and the published numbers.

    A mismatch is a bug in the generalised driver, not a finding. This is a hard gate on the rest of
    the sweep, per section 9 of the pre-registration.

    Each pool is rebuilt from *its own* run's bank and its own four agents, because that is the data
    its episodes were generated from. Scoring it on the pooled eight-agent bank would fail for a
    reason that has nothing to do with the driver: where two runs banked different answers for the
    same agent and task, the pooled bank can only keep one of them.
    """
    spec = SUITES[suite]
    report: dict[str, Any] = {}
    for pool_name, run_id in spec["named"].items():
        directory = RunDirectory(config.RUNS_DIR, run_id)
        local_to_name: dict[int, str] = {}
        for record in directory.load_answers():
            local_to_name.setdefault(record.agent_id, record.agent_name)

        substrate, _, _, _, _ = load_suite(
            suite,
            priority=[run_id],
            only_priority=True,
            agents=list(local_to_name.values()),
            with_embeddings=False,
        )
        index = CoalitionIndex.build(substrate.n_agents, max_size=4)
        votes = vote_outcomes(
            substrate.classes, index, substrate.competence, substrate.correct_class
        )
        members = tuple(range(substrate.n_agents))
        to_global = {i: substrate.agents.index(n) for i, n in local_to_name.items()}

        reconstructed = organization_outcomes(
            members,
            substrate=substrate,
            index=index,
            votes=votes,
            agent_correct=substrate.correct,
            experts=expert_table(members, substrate),
        )
        coalitions = pool_coalitions(members)
        position = {(VOTE, c): row for row, c in enumerate(coalitions)} | {
            (EXPERT, c): len(coalitions) + row for row, c in enumerate(coalitions)
        }
        task_index = {t: i for i, t in enumerate(substrate.tasks)}

        agree = total = 0
        for episode in directory.load_episodes():
            if episode.intervention.kind != "none" or episode.protocol_id not in FREE_PROTOCOLS:
                continue
            column = task_index.get(episode.task_id)
            if column is None:
                continue
            coalition = tuple(sorted(to_global[a] for a in episode.coalition))
            row = position.get((episode.protocol_id, coalition))
            if row is None:
                continue
            total += 1
            agree += int(bool(reconstructed[row, column]) == bool(episode.correct))

        observed_vs_picked, observed = headroom(
            reconstructed, substrate.calibration, substrate.test
        )
        report[pool_name] = {
            "members": [substrate.agents[a] for a in members],
            "n_tasks": substrate.n_tasks,
            "episode_replay_agreement": agree / max(total, 1),
            "n_episodes_compared": total,
            "observed_headroom_over_best": float(observed),
            "observed_headroom_over_picked": float(observed_vs_picked),
        }
    return report


def published_headroom(suite: str) -> dict[str, float]:
    path = config.RUNS_DIR / "headroom_null_shared_members.json"
    if not path.exists():
        return {}
    stored = json.loads(path.read_text()).get(suite, {})
    return {
        pool: float(entry["shared_member_null"]["observed_headroom_over_best"])
        for pool, entry in stored.items()
        if "shared_member_null" in entry
        and "observed_headroom_over_best" in entry["shared_member_null"]
    }


# ---- predictions ------------------------------------------------------------------------------


def evaluate_predictions(
    records: list[dict[str, Any]], null: SweepNull, named: dict[str, tuple[int, ...]]
) -> dict[str, Any]:
    """Score the six locked predictions. Each carries its refutation branch from section 5."""
    excess = null.excess
    p_values = null.p_values
    family = null.family_wise()

    ladders = [r["ladder"] for r in records]
    vote_minus_router = np.array(
        [entry["whole_pool_vote"] - entry["capability_router_agents"] for entry in ladders]
    )
    vote_minus_router_orgs = np.array(
        [entry["whole_pool_vote"] - entry["capability_router_orgs"] for entry in ladders]
    )
    q_theta = np.array(
        [
            r["routing"]["gain_over_fixed_best"].get("q_theta", {}).get("mean", float("nan"))
            for r in records
        ]
    )
    unconstrained = np.array(
        [r["budget"].get("unconstrained_gain_pp", float("nan")) for r in records]
    )
    tightest = np.array([r["budget"].get("tightest_gain_pp", float("nan")) for r in records])

    keys = sorted(records[0]["descriptors"])
    design = np.array([[r["descriptors"][k] for k in keys] for r in records])
    targets = {
        "capability_router_minus_vote": -vote_minus_router,
        "q_theta_gain": q_theta,
        "headroom_excess": excess,
        "tightest_budget_gain": tightest,
    }
    correlations: dict[str, dict[str, float]] = {}
    for name, target in targets.items():
        finite = np.isfinite(target)
        correlations[name] = {}
        for column, key in enumerate(keys):
            values = design[finite, column]
            if values.std() < 1e-12 or target[finite].std() < 1e-12:
                correlations[name][key] = float("nan")
                continue
            correlations[name][key] = float(np.corrcoef(values, target[finite])[0, 1])

    index_of = {tuple(r["pool"]): i for i, r in enumerate(records)}

    def percentile(values: np.ndarray, pool: tuple[int, ...]) -> float:
        i = index_of[pool]
        return float(100.0 * np.mean(values <= values[i]))

    return {
        "P1_headroom_excess_over_joint_null": {
            "prediction": (
                "median excess ~ 0; cloud inside the null band; ~nominal rate significant"
            ),
            "median_excess_pp": float(np.median(excess)),
            "mean_excess_pp": float(excess.mean()),
            "frac_pools_positive": float(np.mean(excess > 0)),
            "n_pools_p_below_05": int(np.sum(p_values <= 0.05)),
            "n_pools": len(records),
            "family_wise": family,
            "verdict": "CONFIRMED"
            if family["p_median"] > 0.05 and family["p_max"] > 0.05
            else "REFUTED",
        },
        "P2_vote_at_least_capability_router": {
            "prediction": ">= 70% of pools have whole-pool vote >= capability router",
            "frac_vote_at_least_router_agents": float(np.mean(vote_minus_router >= 0)),
            "mean_margin_pp": float(100.0 * vote_minus_router.mean()),
            "q05_margin_pp": float(100.0 * np.quantile(vote_minus_router, 0.05)),
            "q95_margin_pp": float(100.0 * np.quantile(vote_minus_router, 0.95)),
            "frac_vote_at_least_router_orgs": float(np.mean(vote_minus_router_orgs >= 0)),
            "verdict": _branch(float(np.mean(vote_minus_router >= 0)), 0.70, 0.50),
        },
        "P3_learned_router_beats_fixed_best": {
            "prediction": "<= 30% of pools have q_theta ahead of the frozen fixed-best baseline",
            "frac_pools_positive": float(np.nanmean(q_theta > 0)),
            "mean_gain_pp": float(np.nanmean(q_theta)),
            "q95_gain_pp": float(np.nanquantile(q_theta, 0.95)),
            "verdict": "CONFIRMED"
            if np.nanmean(q_theta > 0) <= 0.30
            else ("REFUTED" if np.nanmean(q_theta > 0) > 0.50 else "AMBIGUOUS"),
        },
        "P4_descriptors_predict_routing_gain": {
            "prediction": (
                "ability spread predicts routing gain negatively; "
                "decorrelation predicts vote gain positively"
            ),
            "correlations": correlations,
            # The two named directional claims, reported separately from "some descriptor
            # correlates with something", which is a much weaker statement and the only one the
            # refutation branch (all |rho| < 0.2) actually tests.
            "spread_vs_routing_gain": correlations["capability_router_minus_vote"][
                "ability_spread"
            ],
            "spread_vs_routing_gain_sign_as_predicted": bool(
                correlations["capability_router_minus_vote"]["ability_spread"] < 0
            ),
            "error_correlation_vs_routing_gain": correlations["capability_router_minus_vote"][
                "mean_pairwise_error_correlation"
            ],
            "error_correlation_sign_as_predicted": bool(
                correlations["capability_router_minus_vote"]["mean_pairwise_error_correlation"] > 0
            ),
            "max_abs_correlation": float(
                np.nanmax([abs(v) for row in correlations.values() for v in row.values()])
            ),
            "max_abs_correlation_with_a_routing_gain": float(
                np.nanmax(
                    [
                        abs(v)
                        for target in ("capability_router_minus_vote", "q_theta_gain")
                        for v in correlations[target].values()
                    ]
                )
            ),
            "verdict": "PARTIAL"
            if np.nanmax([abs(v) for row in correlations.values() for v in row.values()]) >= 0.2
            else "REFUTED",
            "note": (
                "The refutation branch (all |rho| < 0.2) does not fire, so descriptors are not "
                "inert. But the two directional claims split: error decorrelation moves routing "
                "gain in the predicted direction and ability spread moves it in the opposite one, "
                "and no descriptor reaches |rho| = 0.3 against either routing gain. The strongest "
                "relationships in the sweep are with headroom excess, not with routing gain, so "
                "FRAMEWORK section 5's mechanism has descriptive support at best."
            ),
        },
        "P5_correlated4_percentile": {
            "prediction": (
                "correlated4 sits inside the 5th-95th percentile on capability router minus vote"
            ),
            **{
                f"{name}_percentile_router_minus_vote": percentile(-vote_minus_router, pool)
                for name, pool in named.items()
            },
            **{
                f"{name}_percentile_headroom_excess": percentile(excess, pool)
                for name, pool in named.items()
            },
            "verdict": "CONFIRMED"
            if 5.0 <= percentile(-vote_minus_router, named["correlated4"]) <= 95.0
            else "REFUTED",
        },
        "P6_budget_matched": {
            "prediction": (
                "negative at unconstrained budget; positive at tight budgets in a majority"
            ),
            "unconstrained_mean_pp": float(np.nanmean(unconstrained)),
            "unconstrained_frac_positive": float(np.nanmean(unconstrained > 0)),
            "tightest_mean_pp": float(np.nanmean(tightest)),
            "tightest_frac_positive": float(np.nanmean(tightest > 0)),
            "verdict": "CONFIRMED"
            if np.nanmean(unconstrained) < 0 and np.nanmean(tightest > 0) > 0.50
            else "PARTIAL",
        },
    }


def _branch(value: float, confirm: float, refute: float) -> str:
    if value >= confirm:
        return "CONFIRMED"
    return "REFUTED" if value < refute else "AMBIGUOUS"


# ---- driver -----------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="crosscap240", choices=sorted(SUITES))
    parser.add_argument("--simulations", type=int, default=200)
    parser.add_argument("--splits", type=int, default=60)
    parser.add_argument("--interaction-simulations", type=int, default=200)
    parser.add_argument("--calibration-outer", type=int, default=64)
    parser.add_argument("--calibration-inner", type=int, default=100)
    parser.add_argument("--workers", type=int, default=min(64, os.cpu_count() or 8))
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--limit", type=int, default=0, help="score only the first N pools")
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument(
        "--bank-priority",
        default="",
        help="comma-separated run ids whose answers win when an agent was banked more than once; "
             "the alternative draw of D-040 item 5 is selected by reversing the default order",
    )
    parser.add_argument("--tag", default="", help="suffix for the output artefact")
    arguments = parser.parse_args()

    started = time.time()
    gate: dict[str, Any] | None = None
    print(f"=== pool sweep: {arguments.suite}")
    priority = [r for r in arguments.bank_priority.split(",") if r] or None
    substrate, spaces, domains, space, replication = load_suite(
        arguments.suite, priority=priority
    )
    index = CoalitionIndex.build(substrate.n_agents, max_size=4)
    print(
        f"    {substrate.n_agents} agents, {substrate.n_tasks} tasks, "
        f"{len(index.coalitions)} distinct coalitions, embedding {substrate.embedding_method}"
        f"{' (FALLBACK)' if substrate.embedding_fallback else ''}"
    )
    print(f"    agents: {', '.join(substrate.agents)}")
    print(
        f"    bank: {replication['n_repeated_agent_tasks']} agent-tasks banked more than once, "
        f"{replication['n_disagreeing_on_correctness']} differ on correctness "
        f"({replication['disagreement_rate']:.1%}), "
        f"{replication['n_differing_answer_text']} differ in answer text "
        f"({replication['answer_difference_rate']:.1%}) — see load_suite"
    )

    votes = vote_outcomes(
        substrate.classes, index, substrate.competence, substrate.correct_class
    )

    if not arguments.skip_gate:
        agreement = check_vote_agreement(substrate, index, spaces)
        print(f"\n--- gate 1: vectorized plurality vs sharing_null._vote: {agreement:.4f}")
        if agreement < 1.0:
            raise SystemExit("the vectorized vote disagrees with the reference implementation")

        gate = verification_gate(arguments.suite)
        published = published_headroom(arguments.suite)
        print("--- gate 2: named pools against the recorded episodes and published numbers")
        failed = False
        for pool_name, entry in gate.items():
            reference = published.get(pool_name)
            delta = (
                abs(entry["observed_headroom_over_best"] - reference)
                if reference is not None
                else float("nan")
            )
            status = (
                "ok"
                if entry["episode_replay_agreement"] == 1.0
                and (reference is None or delta < 0.005)
                else "MISMATCH"
            )
            failed |= status == "MISMATCH"
            print(
                f"    {pool_name:14s} replay={entry['episode_replay_agreement']:.4f} "
                f"({entry['n_episodes_compared']} episodes, {entry['n_tasks']} tasks)  "
                f"headroom={entry['observed_headroom_over_best']:6.2f}  published="
                f"{reference if reference is not None else float('nan'):6.2f}  {status}"
            )
        if failed:
            raise SystemExit("verification gate failed; fix the driver before trusting the sweep")

    pools = [tuple(c) for c in itertools.combinations(range(substrate.n_agents), 4)]
    named = {}
    for pool_name, run_id in SUITES[arguments.suite]["named"].items():
        seen: dict[int, str] = {}
        for record in RunDirectory(config.RUNS_DIR, run_id).load_answers():
            seen.setdefault(record.agent_id, record.agent_name)
        named[pool_name] = tuple(sorted(substrate.agents.index(n) for n in seen.values()))
    if arguments.limit:
        keep = set(named.values())
        pools = [p for p in pools if p in keep] + [
            p for p in pools if p not in keep
        ][: max(0, arguments.limit - len(keep))]

    print(f"\n--- joint null over {len(pools)} pools, {arguments.simulations} replicates")
    null_started = time.time()
    null = joint_null(
        substrate,
        index,
        pools,
        n_simulations=arguments.simulations,
        seed=arguments.seed,
        workers=min(arguments.workers, arguments.simulations),
    )
    print(f"    done in {time.time() - null_started:.1f}s")
    family = null.family_wise()
    print(
        f"    median excess {family['median_excess']:+.2f} pp (p={family['p_median']:.3f}), "
        f"max {family['max_excess']:+.2f} pp (p={family['p_max']:.3f}), "
        f"{family['frac_pools_p_below_05']:.1%} of pools at p<=0.05 "
        f"(null expects {family['null_frac_pools_p_below_05_mean']:.1%})"
    )

    print(
        f"\n--- calibration: {arguments.calibration_outer} additive banks x "
        f"{arguments.calibration_inner} inner replicates"
    )
    calibration_started = time.time()
    calibration = calibration_check(
        substrate,
        index,
        pools,
        n_outer=arguments.calibration_outer,
        n_inner=arguments.calibration_inner,
        seed=arguments.seed,
        workers=min(arguments.workers, max(arguments.calibration_outer, 1)),
    )
    print(
        f"    false-positive rate at 0.05: {calibration['false_positive_rate_at_05']:.3f} "
        f"(nominal 0.050), median p {calibration['median_p_value']:.3f} "
        f"({time.time() - calibration_started:.0f}s)"
    )

    print(f"\n--- per-pool statistics on {arguments.workers} workers")
    payloads = [
        (
            pool,
            substrate,
            index,
            votes,
            space,
            domains,
            arguments.splits,
            arguments.interaction_simulations,
            arguments.seed,
        )
        for pool in pools
    ]
    pool_started = time.time()
    with ProcessPoolExecutor(max_workers=arguments.workers) as executor:
        records = []
        for done, record in enumerate(executor.map(evaluate_pool, payloads), start=1):
            records.append(record)
            if done % 10 == 0 or done == len(payloads):
                print(f"    {done}/{len(payloads)} pools  ({time.time() - pool_started:.0f}s)")

    order = {tuple(p): i for i, p in enumerate(pools)}
    records.sort(key=lambda r: order[tuple(r["pool"])])
    for i, record in enumerate(records):
        record["headroom_excess_over_joint_null"] = float(null.excess[i])
        record["p_value_joint_null"] = float(null.p_values[i])
        record["null_headroom_mean"] = float(null.replicates[:, i].mean())

    predictions = evaluate_predictions(records, null, named)

    output = config.RUNS_DIR / f"pool_sweep_{arguments.suite}{arguments.tag}.json"
    output.write_text(
        json.dumps(
            {
                "suite": arguments.suite,
                "generated_by": "scripts/measure_pool_sweep.py",
                "preregistration": "Docs/preregistrations/2026-08-11-pool-sweep.md",
                "n_pools": len(pools),
                "n_agents": substrate.n_agents,
                "agents": substrate.agents,
                "n_tasks": substrate.n_tasks,
                "capabilities": substrate.capabilities,
                "embedding_method": substrate.embedding_method,
                "embedding_fallback": substrate.embedding_fallback,
                "n_simulations": null.n_simulations,
                "n_splits": arguments.splits,
                "named_pools": {k: list(v) for k, v in named.items()},
                "gate": gate,
                "bank_replication": replication,
                "family_wise_null": family,
                "calibration": calibration,
                "predictions": predictions,
                "pools": records,
                "joint_null_replicates": null.replicates.tolist(),
            },
            indent=1,
        )
    )
    print("\n--- predictions")
    for key, entry in predictions.items():
        print(f"    {key:38s} {entry['verdict']}")
    print(f"\nwrote {output}  (total {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
