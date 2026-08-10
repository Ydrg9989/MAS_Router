"""Zero-cost validation of the coalition analysis on a real outcome matrix.

The ``agent-psychometrics`` repository ships dense agent-by-task correctness matrices —
notably SWE-bench Verified at 134 agents x 500 tasks with density 1.0. That is enough to
exercise every piece of :mod:`mas_harness.metrics.coalition` on real data before a single
API call is made, which is the cheapest possible way to find out that the analysis code is
wrong.

What this run does and does not establish:

* It **does** establish that the Harsanyi decomposition, the submodularity test, the
  synergy estimates, the top-k gap and the additive-versus-pairwise comparison are
  implemented correctly and produce numerically sensible values on real data.
* It **does not** establish anything about heterogeneous LLM *teams*. Each "agent" in this
  matrix is a whole scaffold-plus-model system that answered independently. Coalition
  values are therefore reconstructed under an assumed aggregation rule rather than
  observed, and every report is stamped
  ``"coalition_values": "simulated_from_independent"``.

    python -m mas_harness.analysis.free_pilot --benchmark swebench_verified --n-agents 4
    python -m mas_harness.analysis.free_pilot --benchmark terminalbench --pool-strategy top
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .. import config
from ..metrics import coalition as C

PSYCHOMETRICS_ROOT = config.REPO_ROOT / "agent-psychometrics" / "data"

BENCHMARKS = {
    "swebench_verified": "swebench_verified/responses.jsonl",
    "terminalbench": "terminalbench/responses.jsonl",
    "swebench_pro": "swebench_pro/responses.jsonl",
    "gso": "gso/responses.jsonl",
}

AGGREGATION_RULES: tuple[C.AggregationRule, ...] = (
    "plurality_distinct_errors",
    "any",
    "majority_strict",
)


@dataclass
class OutcomeMatrix:
    """Dense agent-by-task correctness, plus whatever metadata the source carried."""

    benchmark: str
    agent_names: list[str]
    task_ids: list[str]
    # (n_tasks, n_agents) — task-major, because every coalition routine is per-task.
    outcomes: np.ndarray
    metadata: list[dict[str, Any]]

    @property
    def n_agents(self) -> int:
        return self.outcomes.shape[1]

    @property
    def n_tasks(self) -> int:
        return self.outcomes.shape[0]

    @property
    def density(self) -> float:
        return float(self._observed.sum() / self._observed.size)

    def agent_accuracy(self) -> np.ndarray:
        return self.outcomes.mean(axis=0)

    def task_solve_rate(self) -> np.ndarray:
        return self.outcomes.mean(axis=1)

    _observed: np.ndarray = None  # type: ignore[assignment]


def load_outcome_matrix(benchmark: str) -> OutcomeMatrix:
    """Read a ``responses.jsonl`` matrix, keeping only tasks every agent attempted."""
    if benchmark not in BENCHMARKS:
        raise ValueError(f"unknown benchmark {benchmark!r}; known: {sorted(BENCHMARKS)}")
    path = PSYCHOMETRICS_ROOT / BENCHMARKS[benchmark]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. The agent-psychometrics repo must be present at "
            f"{config.REPO_ROOT / 'agent-psychometrics'} (see UPSTREAM.md)."
        )

    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"{path} is empty")

    # Intersect task ids so the matrix is genuinely dense rather than padded with zeros,
    # which would silently turn "not attempted" into "failed".
    common: set[str] | None = None
    for row in rows:
        keys = set(row["responses"].keys())
        common = keys if common is None else (common & keys)
    task_ids = sorted(common or set())
    if not task_ids:
        raise ValueError(f"{path}: agents share no common tasks")

    agent_names = [str(row["subject_id"]) for row in rows]
    outcomes = np.zeros((len(task_ids), len(rows)), dtype=np.int8)
    for agent_index, row in enumerate(rows):
        responses = row["responses"]
        for task_index, task_id in enumerate(task_ids):
            value = responses[task_id]
            if isinstance(value, dict):
                # Terminal-Bench per-attempt form: {"successes": k, "trials": n}.
                trials = int(value.get("trials", 0) or 0)
                successes = int(value.get("successes", 0) or 0)
                value = 1 if trials and successes * 2 > trials else 0
            outcomes[task_index, agent_index] = int(bool(int(value)))

    metadata = [{k: v for k, v in row.items() if k != "responses"} for row in rows]
    matrix = OutcomeMatrix(
        benchmark=benchmark,
        agent_names=agent_names,
        task_ids=task_ids,
        outcomes=outcomes,
        metadata=metadata,
    )
    matrix._observed = np.ones_like(outcomes, dtype=bool)
    return matrix


# ---- pool selection -------------------------------------------------------------------


def select_pools(
    matrix: OutcomeMatrix,
    *,
    n_agents: int,
    n_pools: int,
    strategy: str,
    seed: int,
) -> list[list[int]]:
    """Choose which agent subsets to treat as pools.

    The strategies matter because coalition structure is not strategy-invariant: a pool of
    four near-identical frontier systems has almost no synergy to find, while a spread pool
    does. ``stratified`` is the default because it is the closest analogue of the
    heterogeneous pool the research report specifies.
    """
    accuracy = matrix.agent_accuracy()
    order = np.argsort(-accuracy, kind="stable")
    rng = random.Random(seed)

    if strategy == "top":
        return [[int(a) for a in order[:n_agents]]]

    if strategy == "stratified":
        # One agent from each equal-width quantile band of the accuracy distribution, so
        # every pool spans weak to strong.
        bands = np.array_split(order, n_agents)
        pools: list[list[int]] = []
        for _ in range(n_pools):
            pool = [int(rng.choice(list(band))) for band in bands if len(band)]
            if len(set(pool)) == n_agents:
                pools.append(sorted(pool))
        return pools or [[int(a) for a in order[:n_agents]]]

    if strategy == "random":
        pools = []
        for _ in range(n_pools):
            pools.append(sorted(rng.sample(range(matrix.n_agents), n_agents)))
        return pools

    raise ValueError(f"unknown pool strategy {strategy!r}; use stratified, random or top")


# ---- analysis -------------------------------------------------------------------------


def analyse_pool(
    matrix: OutcomeMatrix,
    pool: Sequence[int],
    *,
    rule: C.AggregationRule,
) -> dict[str, Any]:
    """Descriptive coalition analysis for one pool under one aggregation rule."""
    outcomes = matrix.outcomes[:, list(pool)]
    values = C.simulate_coalition_values(outcomes, rule=rule)
    dividends = C.harsanyi_dividends(values)
    ratio = C.higher_order_ratio(dividends, min_order=3)
    submodularity = C.submodularity_violations(values)
    competence = outcomes.mean(axis=0)
    n_agents = len(pool)

    synergies = C.synergy_matrix(values, n_agents)
    errors = C.error_correlation(outcomes)

    gaps = {}
    for k in range(1, n_agents):
        try:
            gap = C.top_k_gap(values, competence, k)
        except ValueError:
            continue
        gaps[f"k{k}"] = {
            "mean_gap": gap["mean_gap"],
            "frac_tasks_gap_ge_5pp": gap["frac_tasks_gap_ge_5pp"],
            "baseline_members": [int(pool[m]) for m in gap["baseline_members"]],
        }

    best_masks = C.best_coalition_per_task(values)
    full_mask = (1 << n_agents) - 1
    return {
        "pool_agent_indices": [int(a) for a in pool],
        "pool_agent_names": [matrix.agent_names[a] for a in pool],
        "individual_accuracy": [float(x) for x in competence],
        "grand_coalition_value": float(values[:, full_mask].mean()),
        "best_single_value": float(
            max(values[:, C.mask_of([i])].mean() for i in range(n_agents))
        ),
        "oracle_best_value": float(values[:, 1:].max(axis=1).mean()),
        "mean_R_ge3": float(ratio.mean()),
        "median_R_ge3": float(np.median(ratio)),
        "frac_tasks_R_ge3_above_0.2": float((ratio > 0.2).mean()),
        "submodularity_mean_violation_rate": submodularity["mean_violation_rate"],
        "submodularity_tasks_with_any_violation": submodularity["tasks_with_any_violation"],
        "mean_pairwise_synergy": {
            f"{pool[i]}_{pool[j]}": float(s.mean()) for (i, j), s in synergies.items()
        },
        "mean_error_correlation": float(
            errors[np.triu_indices(n_agents, k=1)].mean() if n_agents > 1 else 0.0
        ),
        "top_k_gaps": gaps,
        "frac_tasks_grand_coalition_optimal": float((best_masks == full_mask).mean()),
        "frac_tasks_singleton_optimal": float(
            np.isin(best_masks, [C.mask_of([i]) for i in range(n_agents)]).mean()
        ),
    }


def fit_pool_models(
    matrix: OutcomeMatrix,
    pool: Sequence[int],
    *,
    rule: C.AggregationRule,
    seed: int,
) -> dict[str, Any]:
    """Additive versus pairwise coalition models, on held-out coalitions and held-out tasks.

    The held-out-coalition split is the one that matters: it asks whether pair interactions
    estimated on some coalitions predict coalitions never observed, which the report calls
    the critical novelty test for this direction.

    Task difficulty ``b(x)`` is computed from the agents *outside* the pool, so it carries
    no information about how the pool's own members performed.
    """
    pool = list(pool)
    outcomes = matrix.outcomes[:, pool]
    values = C.simulate_coalition_values(outcomes, rule=rule)

    outside = [a for a in range(matrix.n_agents) if a not in set(pool)]
    difficulty = (
        matrix.outcomes[:, outside].mean(axis=1)
        if outside
        else matrix.task_solve_rate()
    )

    dataset = C.build_coalition_dataset(values, task_difficulty=difficulty)
    n_agents = len(pool)
    rng = random.Random(seed)

    # Hold out two coalitions of size >= 2, so the pairwise model must extrapolate.
    candidates = [m for m in range(1, 1 << n_agents) if C.popcount(m) >= 2]
    held_masks = rng.sample(candidates, min(2, len(candidates)))
    train_rows, test_rows = C.held_out_coalition_split(dataset, held_out_masks=held_masks)

    held_tasks = rng.sample(range(matrix.n_tasks), max(1, matrix.n_tasks // 5))
    task_train, task_test = C.held_out_task_split(dataset, held_out_tasks=held_tasks)

    results: dict[str, Any] = {
        "held_out_masks": held_masks,
        "held_out_mask_members": [
            [int(pool[i]) for i in C.members_of(m, n_agents)] for m in held_masks
        ],
    }
    for split_name, (tr, te) in {
        "held_out_coalition": (train_rows, test_rows),
        "held_out_task": (task_train, task_test),
    }.items():
        block: dict[str, Any] = {}
        for label, pairwise in (("additive", False), ("pairwise", True)):
            try:
                fit = C.fit_logistic(
                    dataset,
                    pairwise=pairwise,
                    train_rows=tr,
                    test_rows=te,
                    name=f"{split_name}/{label}",
                )
                block[label] = fit.to_dict()
            except Exception as exc:  # degenerate targets on an easy/hard pool
                block[label] = {"error": f"{type(exc).__name__}: {exc}"}
        additive = block.get("additive", {})
        pairwise_block = block.get("pairwise", {})
        if "test_log_loss" in additive and "test_log_loss" in pairwise_block:
            add_ll = additive["test_log_loss"]
            pair_ll = pairwise_block["test_log_loss"]
            block["pairwise_improves_log_loss"] = bool(pair_ll < add_ll)
            block["log_loss_reduction"] = float(add_ll - pair_ll)
            block["relative_log_loss_reduction"] = (
                float((add_ll - pair_ll) / add_ll) if add_ll > 0 else 0.0
            )
        results[split_name] = block
    return results


def synergy_stability(
    matrix: OutcomeMatrix,
    pool: Sequence[int],
    *,
    rule: C.AggregationRule,
    n_bootstrap: int = 200,
    seed: int = 0,
) -> dict[str, Any]:
    """Bootstrap over tasks to see which pair synergies keep their sign.

    The report's continue signal asks for at least two agent pairs with *stable* positive or
    negative synergy. Stability is operationalized here as a bootstrap confidence interval
    for the mean pair synergy that excludes zero.
    """
    pool = list(pool)
    outcomes = matrix.outcomes[:, pool]
    values = C.simulate_coalition_values(outcomes, rule=rule)
    n_agents = len(pool)
    n_tasks = values.shape[0]
    rng = np.random.default_rng(seed)

    stable: dict[str, Any] = {}
    n_stable = 0
    for (i, j), synergy in C.synergy_matrix(values, n_agents).items():
        draws = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            idx = rng.integers(0, n_tasks, n_tasks)
            draws[b] = synergy[idx].mean()
        low, high = np.percentile(draws, [2.5, 97.5])
        excludes_zero = bool(low > 0 or high < 0)
        n_stable += int(excludes_zero)
        stable[f"{pool[i]}_{pool[j]}"] = {
            "mean": float(synergy.mean()),
            "ci_low": float(low),
            "ci_high": float(high),
            "stable_nonzero": excludes_zero,
        }
    return {"pairs": stable, "n_stable_pairs": n_stable, "n_pairs": len(stable)}


def run_free_pilot(
    *,
    benchmark: str,
    n_agents: int,
    n_pools: int,
    n_fit_pools: int,
    strategy: str,
    seed: int,
    out_dir: Path,
) -> dict[str, Any]:
    matrix = load_outcome_matrix(benchmark)
    pools = select_pools(
        matrix, n_agents=n_agents, n_pools=n_pools, strategy=strategy, seed=seed
    )
    accuracy = matrix.agent_accuracy()

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "harness_version": config.HARNESS_VERSION,
        "benchmark": benchmark,
        "coalition_values": "simulated_from_independent",
        "caveat": (
            "Each agent is an independent scaffold+model system, not a member of an "
            "interacting team. Coalition values are reconstructed under an assumed "
            "aggregation rule. This run validates the analysis code; it is not evidence "
            "about heterogeneous LLM teams."
        ),
        "matrix": {
            "n_agents": matrix.n_agents,
            "n_tasks": matrix.n_tasks,
            "density": matrix.density,
            "agent_accuracy_min": float(accuracy.min()),
            "agent_accuracy_median": float(np.median(accuracy)),
            "agent_accuracy_max": float(accuracy.max()),
            "frac_tasks_with_disagreement": float(
                (
                    (matrix.outcomes.sum(axis=1) > 0)
                    & (matrix.outcomes.sum(axis=1) < matrix.n_agents)
                ).mean()
            ),
        },
        "settings": {
            "n_agents_per_pool": n_agents,
            "n_pools": len(pools),
            "n_fit_pools": min(n_fit_pools, len(pools)),
            "pool_strategy": strategy,
            "seed": seed,
        },
        "by_rule": {},
    }

    def collector(per_pool: list[dict[str, Any]]):
        def collect(key: str) -> list[float]:
            return [p[key] for p in per_pool if isinstance(p.get(key), (int, float))]

        return collect

    for rule in AGGREGATION_RULES:
        per_pool = [analyse_pool(matrix, pool, rule=rule) for pool in pools]
        collect = collector(per_pool)

        summary: dict[str, Any] = {
            "n_pools": len(per_pool),
            "mean_R_ge3": float(np.mean(collect("mean_R_ge3"))),
            "median_R_ge3": float(np.median(collect("mean_R_ge3"))),
            "mean_submodularity_violation_rate": float(
                np.mean(collect("submodularity_mean_violation_rate"))
            ),
            "mean_frac_tasks_with_submodularity_violation": float(
                np.mean(collect("submodularity_tasks_with_any_violation"))
            ),
            "mean_error_correlation": float(np.mean(collect("mean_error_correlation"))),
            "mean_grand_coalition_value": float(np.mean(collect("grand_coalition_value"))),
            "mean_best_single_value": float(np.mean(collect("best_single_value"))),
            "mean_oracle_best_value": float(np.mean(collect("oracle_best_value"))),
            "mean_frac_tasks_grand_coalition_optimal": float(
                np.mean(collect("frac_tasks_grand_coalition_optimal"))
            ),
        }
        summary["mean_synergy_gap_vs_best_single"] = (
            summary["mean_grand_coalition_value"] - summary["mean_best_single_value"]
        )

        for k in range(1, n_agents):
            key = f"k{k}"
            fractions = [
                p["top_k_gaps"][key]["frac_tasks_gap_ge_5pp"]
                for p in per_pool
                if key in p["top_k_gaps"]
            ]
            if fractions:
                summary[f"mean_frac_tasks_topk_gap_ge_5pp_{key}"] = float(np.mean(fractions))

        fit_pools = pools[: min(n_fit_pools, len(pools))]
        fits = [
            fit_pool_models(matrix, pool, rule=rule, seed=seed + index)
            for index, pool in enumerate(fit_pools)
        ]
        improvements = [
            f["held_out_coalition"].get("relative_log_loss_reduction")
            for f in fits
            if isinstance(f.get("held_out_coalition"), dict)
            and f["held_out_coalition"].get("relative_log_loss_reduction") is not None
        ]
        summary["pairwise_vs_additive_held_out_coalition"] = {
            "n_fits": len(improvements),
            "mean_relative_log_loss_reduction": float(np.mean(improvements))
            if improvements
            else None,
            "frac_fits_pairwise_better": float(
                np.mean([i > 0 for i in improvements]) if improvements else 0.0
            ),
        }

        stability = [
            synergy_stability(matrix, pool, rule=rule, seed=seed + index)
            for index, pool in enumerate(fit_pools)
        ]
        summary["synergy_stability"] = {
            "mean_stable_pairs": float(np.mean([s["n_stable_pairs"] for s in stability])),
            "n_pairs": stability[0]["n_pairs"] if stability else 0,
            "frac_pools_with_ge2_stable_pairs": float(
                np.mean([s["n_stable_pairs"] >= 2 for s in stability])
            ),
        }

        report["by_rule"][rule] = {
            "summary": summary,
            "example_pool": per_pool[0] if per_pool else None,
            "example_fit": fits[0] if fits else None,
            "example_stability": stability[0] if stability else None,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{benchmark}_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=float))
    report["_path"] = str(out_path)
    return report


def print_summary(report: dict[str, Any]) -> None:
    matrix = report["matrix"]
    print(f"\nFree pilot: {report['benchmark']}  (no API calls, cost $0.00)")
    print(
        f"  matrix        : {matrix['n_agents']} agents x {matrix['n_tasks']} tasks, "
        f"density {matrix['density']:.3f}"
    )
    print(
        f"  agent accuracy: min {matrix['agent_accuracy_min']:.3f} / "
        f"median {matrix['agent_accuracy_median']:.3f} / max {matrix['agent_accuracy_max']:.3f}"
    )
    print(f"  disagreement  : {matrix['frac_tasks_with_disagreement']:.1%} of tasks")
    settings = report["settings"]
    print(
        f"  pools         : {settings['n_pools']} x {settings['n_agents_per_pool']} agents "
        f"({settings['pool_strategy']}), {settings['n_fit_pools']} used for model fits"
    )

    for rule, block in report["by_rule"].items():
        s = block["summary"]
        print(f"\n  --- aggregation rule: {rule}")
        print(
            f"    grand coalition {s['mean_grand_coalition_value']:.3f} vs "
            f"best single {s['mean_best_single_value']:.3f} "
            f"(synergy gap {s['mean_synergy_gap_vs_best_single']:+.3f}), "
            f"oracle {s['mean_oracle_best_value']:.3f}"
        )
        print(
            f"    R>=3 interaction mass  : mean {s['mean_R_ge3']:.3f}, "
            f"median {s['median_R_ge3']:.3f}"
        )
        print(
            f"    submodularity violated : {s['mean_submodularity_violation_rate']:.3f} of "
            f"comparisons, {s['mean_frac_tasks_with_submodularity_violation']:.1%} of tasks"
        )
        print(f"    mean error correlation : {s['mean_error_correlation']:.3f}")
        for key in sorted(k for k in s if k.startswith("mean_frac_tasks_topk_gap")):
            print(f"    {key.replace('mean_frac_tasks_topk_gap_ge_5pp_', 'top-k gap >=5pp, ')}"
                  f": {s[key]:.1%} of tasks")
        pv = s["pairwise_vs_additive_held_out_coalition"]
        if pv["mean_relative_log_loss_reduction"] is not None:
            print(
                f"    pairwise vs additive on HELD-OUT COALITIONS: "
                f"{pv['mean_relative_log_loss_reduction']:+.1%} log-loss reduction, "
                f"pairwise better in {pv['frac_fits_pairwise_better']:.0%} of {pv['n_fits']} fits"
            )
        st = s["synergy_stability"]
        print(
            f"    stable pair synergies  : {st['mean_stable_pairs']:.1f} of {st['n_pairs']} pairs, "
            f"{st['frac_pools_with_ge2_stable_pairs']:.0%} of pools have >=2"
        )

    print(f"\n  report written to {report.get('_path')}")
    print(
        "\n  Reminder: coalition values here are simulated from independent outcomes. "
        "This validates the analysis code, not a claim about LLM teams."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the coalition analysis on a free, dense outcome matrix"
    )
    parser.add_argument("--benchmark", default="swebench_verified", choices=sorted(BENCHMARKS))
    parser.add_argument("--n-agents", type=int, default=4, help="pool size (report uses 4)")
    parser.add_argument("--n-pools", type=int, default=200, help="pools sampled for descriptives")
    parser.add_argument("--n-fit-pools", type=int, default=20, help="pools used for model fits")
    parser.add_argument(
        "--pool-strategy",
        default="stratified",
        choices=["stratified", "random", "top"],
        help="stratified spans the accuracy range; top takes the strongest agents",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", default=str(config.RUNS_DIR / "free_pilot"))
    args = parser.parse_args(argv)

    report = run_free_pilot(
        benchmark=args.benchmark,
        n_agents=args.n_agents,
        n_pools=args.n_pools,
        n_fit_pools=args.n_fit_pools,
        strategy=args.pool_strategy,
        seed=args.seed,
        out_dir=Path(args.out_dir),
    )
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
