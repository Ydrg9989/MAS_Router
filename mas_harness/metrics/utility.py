"""Utility, regret, and the cost-aware selection objective.

The report defines the object a router is actually trying to maximize as

    U(x, c) = P(correct | x, c) - lambda * Cost(x, c) - mu * Latency(x, c)

for a task ``x`` and a configuration ``c`` (a coalition together with a protocol). Reporting
accuracy alone hides the fact that the most accurate configuration is often the most expensive
one, and a routing result that ignores cost is not a routing result.

``lambda`` and ``mu`` are not physical constants. They encode how much a point of accuracy is
worth in dollars and seconds, and any conclusion about which configuration "wins" holds only
for a stated pair. So :func:`utility_frontier` sweeps them rather than picking one, and the
Pareto frontier is reported unconditionally since it is the part that does not depend on the
trade-off.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

from ..records.schema import EpisodeRecord

# Default trade-off weights. lambda is per USD, mu is per second, both chosen so that a
# realistic MVP episode's penalty is small relative to one accuracy point; they exist to make
# the objective well-defined, not to assert an exchange rate.
DEFAULT_LAMBDA_PER_USD = 1.0
DEFAULT_MU_PER_SECOND = 0.001


@dataclass(frozen=True)
class Configuration:
    """A coalition plus a protocol: the thing a router chooses."""

    protocol_id: str
    coalition: tuple[int, ...]

    @property
    def label(self) -> str:
        return f"{self.protocol_id}[{'-'.join(map(str, self.coalition))}]"

    @classmethod
    def of(cls, episode: EpisodeRecord) -> "Configuration":
        return cls(protocol_id=episode.protocol_id, coalition=tuple(sorted(episode.coalition)))


@dataclass
class ConfigurationStats:
    """Observed accuracy, cost and latency for one configuration on one task set."""

    configuration: Configuration
    n: int = 0
    accuracy: float = float("nan")
    mean_cost_usd: float = 0.0
    mean_latency_s: float = 0.0
    per_task_correct: dict[str, bool] = field(default_factory=dict)
    per_task_cost: dict[str, float] = field(default_factory=dict)
    per_task_latency: dict[str, float] = field(default_factory=dict)

    def utility(
        self,
        *,
        lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
        mu_per_second: float = DEFAULT_MU_PER_SECOND,
    ) -> float:
        return (
            self.accuracy
            - lambda_per_usd * self.mean_cost_usd
            - mu_per_second * self.mean_latency_s
        )

    def task_utility(
        self,
        task_id: str,
        *,
        lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
        mu_per_second: float = DEFAULT_MU_PER_SECOND,
    ) -> float:
        return (
            float(self.per_task_correct.get(task_id, False))
            - lambda_per_usd * self.per_task_cost.get(task_id, 0.0)
            - mu_per_second * self.per_task_latency.get(task_id, 0.0)
        )

    def to_dict(self, **weights) -> dict[str, Any]:
        return {
            "configuration": self.configuration.label,
            "protocol_id": self.configuration.protocol_id,
            "coalition": list(self.configuration.coalition),
            "coalition_size": len(self.configuration.coalition),
            "n": self.n,
            "accuracy": self.accuracy,
            "mean_cost_usd": self.mean_cost_usd,
            "mean_latency_s": self.mean_latency_s,
            "utility": self.utility(**weights),
        }


def configuration_stats(
    episodes: Iterable[EpisodeRecord], *, observational_only: bool = True
) -> dict[Configuration, ConfigurationStats]:
    """Aggregate episodes into per-configuration statistics."""
    grouped: dict[Configuration, list[EpisodeRecord]] = defaultdict(list)
    for episode in episodes:
        if observational_only and episode.intervention.kind != "none":
            continue
        grouped[Configuration.of(episode)].append(episode)

    stats: dict[Configuration, ConfigurationStats] = {}
    for configuration, records in grouped.items():
        entry = ConfigurationStats(configuration=configuration, n=len(records))
        entry.accuracy = float(np.mean([r.correct for r in records]))
        entry.mean_cost_usd = float(np.mean([r.total_cost_usd for r in records]))
        entry.mean_latency_s = float(np.mean([r.total_latency_ms / 1000.0 for r in records]))
        for record in records:
            entry.per_task_correct[record.task_id] = bool(record.correct)
            entry.per_task_cost[record.task_id] = record.total_cost_usd
            entry.per_task_latency[record.task_id] = record.total_latency_ms / 1000.0
        stats[configuration] = entry
    return stats


def pareto_frontier(stats: dict[Configuration, ConfigurationStats]) -> list[Configuration]:
    """Configurations not dominated on both accuracy (higher) and cost (lower).

    Reported because it is the trade-off-free part of the answer: a configuration off the
    frontier is worse for *every* positive lambda, which is a much stronger statement than
    losing at one particular lambda.
    """
    entries = list(stats.values())
    frontier: list[Configuration] = []
    for candidate in entries:
        dominated = any(
            other is not candidate
            and other.accuracy >= candidate.accuracy
            and other.mean_cost_usd <= candidate.mean_cost_usd
            and (
                other.accuracy > candidate.accuracy
                or other.mean_cost_usd < candidate.mean_cost_usd
            )
            for other in entries
        )
        if not dominated:
            frontier.append(candidate.configuration)
    return sorted(frontier, key=lambda c: (stats[c].mean_cost_usd, -stats[c].accuracy))


def utility_frontier(
    stats: dict[Configuration, ConfigurationStats],
    *,
    lambdas: Sequence[float] = (0.0, 0.1, 1.0, 10.0, 100.0),
    mu_per_second: float = DEFAULT_MU_PER_SECOND,
) -> dict[str, Any]:
    """Which configuration wins as the cost weight sweeps.

    A winner that is stable across several orders of magnitude of lambda is a robust finding.
    A winner that changes at every lambda tells us the choice is entirely about the trade-off
    and not about the configurations, which is itself worth reporting.
    """
    winners: dict[str, str] = {}
    for lambda_value in lambdas:
        scored = {
            configuration: entry.utility(
                lambda_per_usd=lambda_value, mu_per_second=mu_per_second
            )
            for configuration, entry in stats.items()
        }
        if scored:
            winners[f"lambda={lambda_value}"] = max(scored, key=scored.get).label

    distinct = len(set(winners.values()))
    return {
        "winners_by_lambda": winners,
        "n_distinct_winners": distinct,
        "winner_is_lambda_invariant": distinct <= 1,
        "pareto_frontier": [c.label for c in pareto_frontier(stats)],
        "mu_per_second": mu_per_second,
    }


# ---- regret --------------------------------------------------------------------------------


def decision_regret(
    stats: dict[Configuration, ConfigurationStats],
    *,
    chosen: dict[str, Configuration],
    lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
    mu_per_second: float = DEFAULT_MU_PER_SECOND,
) -> dict[str, Any]:
    """Per-task utility gap between the best configuration and the chosen one.

    The oracle here is per-task, so this is regret against a router that knows the outcome in
    advance. That is deliberately unattainable: the point is to bound how much a *learnable*
    router could possibly gain, which is the number that decides whether the delegation
    direction is worth pursuing.
    """
    weights = {"lambda_per_usd": lambda_per_usd, "mu_per_second": mu_per_second}
    task_ids = sorted({t for entry in stats.values() for t in entry.per_task_correct})
    if not task_ids:
        return {"n_tasks": 0, "note": "no per-task outcomes"}

    regrets: list[float] = []
    oracle_utilities: list[float] = []
    chosen_utilities: list[float] = []
    per_task: dict[str, float] = {}
    missing = 0

    for task_id in task_ids:
        available = {c: e for c, e in stats.items() if task_id in e.per_task_correct}
        if not available:
            continue
        utilities = {c: e.task_utility(task_id, **weights) for c, e in available.items()}
        best = max(utilities.values())
        selection = chosen.get(task_id)
        if selection is None or selection not in utilities:
            missing += 1
            continue
        gap = best - utilities[selection]
        regrets.append(gap)
        per_task[task_id] = gap
        oracle_utilities.append(best)
        chosen_utilities.append(utilities[selection])

    if not regrets:
        return {"n_tasks": 0, "n_missing_selection": missing, "note": "no scorable tasks"}

    return {
        "n_tasks": len(regrets),
        "n_missing_selection": missing,
        "mean_regret": float(np.mean(regrets)),
        "median_regret": float(np.median(regrets)),
        "max_regret": float(np.max(regrets)),
        "frac_tasks_zero_regret": float(np.mean([r <= 1e-12 for r in regrets])),
        "mean_oracle_utility": float(np.mean(oracle_utilities)),
        "mean_chosen_utility": float(np.mean(chosen_utilities)),
        "per_task_regret": per_task,
        "lambda_per_usd": lambda_per_usd,
        "mu_per_second": mu_per_second,
    }


def fixed_best_selection(
    stats: dict[Configuration, ConfigurationStats],
    *,
    lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
    mu_per_second: float = DEFAULT_MU_PER_SECOND,
) -> dict[str, Configuration]:
    """The single best configuration overall, applied to every task.

    This is the baseline any task-conditional router must beat. If per-task routing cannot
    improve on one fixed configuration, task representations are not buying anything.
    """
    if not stats:
        return {}
    best = max(
        stats.values(),
        key=lambda e: e.utility(lambda_per_usd=lambda_per_usd, mu_per_second=mu_per_second),
    ).configuration
    task_ids = sorted({t for entry in stats.values() for t in entry.per_task_correct})
    return dict.fromkeys(task_ids, best)


def dynamic_regret(
    stats: dict[Configuration, ConfigurationStats],
    *,
    chosen_sequence: Sequence[tuple[str, Configuration]],
    lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
    mu_per_second: float = DEFAULT_MU_PER_SECOND,
) -> dict[str, Any]:
    """Cumulative regret over an ordered stream of routing decisions.

    Separate from :func:`decision_regret` because it exposes *when* a router does badly. A
    router that is poor early and good later is learning; one with a linear regret curve is not.
    """
    weights = {"lambda_per_usd": lambda_per_usd, "mu_per_second": mu_per_second}
    cumulative: list[float] = []
    running = 0.0
    for task_id, selection in chosen_sequence:
        available = {c: e for c, e in stats.items() if task_id in e.per_task_correct}
        if not available or selection not in available:
            cumulative.append(running)
            continue
        utilities = {c: e.task_utility(task_id, **weights) for c, e in available.items()}
        running += max(utilities.values()) - utilities[selection]
        cumulative.append(running)

    if not cumulative:
        return {"n_steps": 0, "note": "empty decision sequence"}
    n = len(cumulative)
    half = n // 2
    return {
        "n_steps": n,
        "cumulative_regret": cumulative,
        "final_regret": cumulative[-1],
        "mean_regret_per_step": cumulative[-1] / n,
        "first_half_rate": (cumulative[half] / half) if half else float("nan"),
        "second_half_rate": ((cumulative[-1] - cumulative[half]) / (n - half))
        if half
        else float("nan"),
    }
