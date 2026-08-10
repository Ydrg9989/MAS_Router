"""Predicted expert selection, ``e_hat(x)``.

This module exists because of D-004. The upstream ``teamwork`` code has a
``reveal_expert`` decision mode that announces the agent whose answer matched ground
truth, which is an oracle: it cannot exist at inference time, and a dilution number
measured against it answers a question nobody can act on.

The research report's ``EUR`` and ``Dilution`` are defined against the *predicted* expert.
So the predictor is a first-class object here, fitted on the calibration split only, and
the oracle is retained solely as a labelled upper bound.

Three strategies, in increasing strength:

``global``
    One agent for all tasks: the highest calibration accuracy. The report's "calibrated
    single expert" baseline, and the honest floor.
``domain``
    Per-domain argmax on calibration accuracy, falling back to the global choice for a
    domain with too little calibration data. This is the strongest predictor available
    without training anything.
``oracle``
    Any agent correct on this task. Not a predictor. Used only to bound how much
    performance a perfect router would leave on the table.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

Strategy = Literal["global", "domain", "oracle"]

# Below this many calibration tasks a per-domain estimate is noise, so we fall back.
MIN_CALIBRATION_TASKS_PER_DOMAIN = 5


@dataclass(frozen=True)
class Observation:
    """One banked independent answer, reduced to what expert selection needs."""

    task_id: str
    agent_id: int
    domain: str
    correct: bool


@dataclass
class ExpertPredictor:
    """A fitted ``e_hat``, plus the evidence it was fitted on."""

    strategy: Strategy
    global_expert: int | None = None
    by_domain: dict[str, int] = field(default_factory=dict)
    accuracy_global: dict[int, float] = field(default_factory=dict)
    accuracy_by_domain: dict[str, dict[int, float]] = field(default_factory=dict)
    n_calibration_tasks: int = 0
    calibration_task_ids: list[str] = field(default_factory=list)
    fallback_domains: list[str] = field(default_factory=list)

    def predict(self, *, domain: str, coalition: Sequence[int] | None = None) -> int | None:
        """The predicted expert for a task, restricted to ``coalition`` when given.

        Restriction matters: the pool-wide best agent may not be in the coalition being
        evaluated, and silently returning a non-member would make the protocol consult an
        agent that is not playing.
        """
        if self.strategy == "oracle":
            raise ValueError(
                "the oracle predictor has no task-independent prediction; "
                "call oracle_expert() with per-task outcomes"
            )

        candidates = list(coalition) if coalition is not None else None

        preferred = self.by_domain.get(domain) if self.strategy == "domain" else None
        for choice in (preferred, self.global_expert):
            if choice is None:
                continue
            if candidates is None or choice in candidates:
                return choice

        if not candidates:
            return None
        # Best available coalition member by domain accuracy, then global accuracy.
        domain_accuracy = self.accuracy_by_domain.get(domain, {})
        return max(
            candidates,
            key=lambda a: (domain_accuracy.get(a, -1.0), self.accuracy_global.get(a, -1.0), -a),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "global_expert": self.global_expert,
            "by_domain": dict(sorted(self.by_domain.items())),
            "accuracy_global": {str(k): v for k, v in sorted(self.accuracy_global.items())},
            "n_calibration_tasks": self.n_calibration_tasks,
            "fallback_domains": sorted(self.fallback_domains),
        }


def fit_expert_predictor(
    observations: Iterable[Observation],
    *,
    strategy: Strategy = "domain",
    calibration_task_ids: Iterable[str] | None = None,
) -> ExpertPredictor:
    """Fit ``e_hat`` on calibration observations only.

    ``calibration_task_ids`` is not optional in spirit: passing ``None`` fits on every
    observation given, which is only correct if the caller has already filtered to the
    calibration split. The runner always passes the split explicitly.
    """
    allowed = set(calibration_task_ids) if calibration_task_ids is not None else None

    correct_global: dict[int, int] = defaultdict(int)
    total_global: dict[int, int] = defaultdict(int)
    correct_domain: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    total_domain: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    task_ids: set[str] = set()

    for observation in observations:
        if allowed is not None and observation.task_id not in allowed:
            continue
        task_ids.add(observation.task_id)
        total_global[observation.agent_id] += 1
        correct_global[observation.agent_id] += int(observation.correct)
        total_domain[observation.domain][observation.agent_id] += 1
        correct_domain[observation.domain][observation.agent_id] += int(observation.correct)

    if not task_ids:
        raise ValueError(
            "no calibration observations matched; cannot fit e_hat. Check that Stage A "
            "covered the calibration split."
        )

    accuracy_global = {
        agent: correct_global[agent] / total_global[agent] for agent in sorted(total_global)
    }
    accuracy_by_domain = {
        domain: {
            agent: correct_domain[domain][agent] / total_domain[domain][agent]
            for agent in sorted(total_domain[domain])
        }
        for domain in sorted(total_domain)
    }

    # Ties broken by lowest agent id, so a rebuild is deterministic.
    global_expert = max(accuracy_global, key=lambda a: (accuracy_global[a], -a))

    by_domain: dict[str, int] = {}
    fallback_domains: list[str] = []
    if strategy == "domain":
        for domain, accuracies in accuracy_by_domain.items():
            n_tasks = max(total_domain[domain].values()) if total_domain[domain] else 0
            if n_tasks < MIN_CALIBRATION_TASKS_PER_DOMAIN:
                fallback_domains.append(domain)
                continue
            by_domain[domain] = max(accuracies, key=lambda a: (accuracies[a], -a))

    return ExpertPredictor(
        strategy=strategy,
        global_expert=global_expert,
        by_domain=by_domain,
        accuracy_global=accuracy_global,
        accuracy_by_domain=accuracy_by_domain,
        n_calibration_tasks=len(task_ids),
        calibration_task_ids=sorted(task_ids),
        fallback_domains=fallback_domains,
    )


def oracle_expert(
    correct_by_agent: dict[int, bool], *, coalition: Sequence[int] | None = None
) -> int | None:
    """Any agent that got this task right. An upper bound, never a predictor.

    Returns ``None`` when no member is correct, which is the honest answer: on that task
    there is no expert to utilize, and it must be excluded from EUR rather than counted as
    a failure to identify one.
    """
    candidates = (
        [a for a in coalition if correct_by_agent.get(a, False)]
        if coalition is not None
        else [a for a, ok in correct_by_agent.items() if ok]
    )
    return min(candidates) if candidates else None


def observations_from_records(records: Iterable[Any]) -> list[Observation]:
    """Build observations from Stage-A :class:`AnswerRecord` objects.

    Repeated seeds are averaged implicitly: each (task, agent, seed) contributes one
    observation, so an agent evaluated on three seeds carries three times the weight for
    that task. That is the intended behaviour — more evidence per task should count for
    more — but it means calibration accuracy is per-*answer*, not per-task.
    """
    return [
        Observation(
            task_id=record.task_id,
            agent_id=record.agent_id,
            domain=record.domain,
            correct=bool(record.correct),
        )
        for record in records
    ]
