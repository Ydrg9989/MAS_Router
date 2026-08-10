"""Is the best configuration per group a real signal, or the argmax of noise?

The delegation direction rests on a claim with two halves: the best organization *varies* by task,
and that variation is *real*. `governance.protocol_dominance` measures only the first half, by
taking the argmax protocol in each domain and reporting how often one protocol wins everywhere.

That is not enough, and on the MVP data it is not even informative. Shuffling protocol labels
within each task destroys every genuine protocol difference while preserving task difficulty and
the domain structure; dominance measured on the shuffled data reads 54-59% against observed values
of 42-67%, and the null's 95th percentile falls on 75.0% — the gate's own threshold. The criterion
therefore passes at roughly the rate that pure noise passes it. The cause is the denominator: the
priced subsets hold a median of 8-15 tasks per domain and the thinnest domains hold one to three,
so a domain's "winning protocol" is often just whichever protocol got a single task right.

This module measures the missing half. A winner is only evidence if it *reproduces*: split a
group's tasks in half, take the argmax on each half independently, and ask whether the two halves
agree more often than chance. Real task-dependence produces agreement above the permutation null.
Argmax noise does not, however many groups it is averaged over.

Both quantities are reported together, because either alone is misleading. High reproducibility
with a single winner everywhere means one configuration is simply best and there is nothing to
route over. Varied winners with chance-level reproducibility means the variety is noise. The
delegation claim needs varied winners *and* reproducibility above the null.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

import numpy as np

from ..records.schema import EpisodeRecord

# A group needs enough tasks that each half of a split can distinguish protocols at all. Four is
# the floor at which both halves are non-empty and can disagree; groups below it are reported as
# excluded rather than silently averaged in, since they are exactly the ones that generate the
# spurious variety this module exists to detect.
MIN_TASKS_PER_GROUP = 4

# A group's winner must survive a resplit more often than not. Purely relative comparison against
# the permutation null is not enough: the null falls towards zero as the configuration family grows,
# so at 134 candidates an effectively random winner clears it.
MIN_REPRODUCIBILITY = 0.5

Grouping = Literal["domain", "suite"]


@dataclass
class GroupStability:
    """Split-half reproducibility of the argmax configuration within one group."""

    group: str
    n_tasks: int
    n_configurations: int
    winner: str | None
    winner_accuracy: float
    reproducibility: float
    """Fraction of random half-splits whose two halves choose the same configuration."""
    chance: float
    """1 / n_configurations: the agreement expected if the winner were drawn uniformly."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "n_tasks": self.n_tasks,
            "n_configurations": self.n_configurations,
            "winner": self.winner,
            "winner_accuracy": self.winner_accuracy,
            "reproducibility": self.reproducibility,
            "chance": self.chance,
        }


@dataclass
class StabilityReport:
    """Whether per-group winners are reproducible, and whether they vary."""

    grouping: Grouping
    groups: list[GroupStability] = field(default_factory=list)
    excluded_groups: dict[str, int] = field(default_factory=dict)
    reproducibility: float = float("nan")
    null_reproducibility: float = float("nan")
    reproducibility_p: float = float("nan")
    dominance: float = float("nan")
    null_dominance: float = float("nan")
    dominance_p: float = float("nan")
    n_permutations: int = 0

    dominant_configuration: str | None = None
    reproducibility_dominant: float = float("nan")
    """Mean reproducibility over groups won by the single most frequent winner."""
    reproducibility_off_dominant: float = float("nan")
    """Mean reproducibility over groups won by anything else. This is the routing signal."""
    n_off_dominant: int = 0

    @property
    def winners_are_reproducible(self) -> bool:
        """Agreement above the permutation null at the 5% level."""
        return bool(self.reproducibility_p < 0.05)

    @property
    def variety_is_reproducible(self) -> bool:
        """Do the groups that depart from the dominant configuration reproduce?

        This is the criterion that matters, and it is not implied by the previous one. A pool where
        one configuration is best nearly everywhere produces high *average* reproducibility from the
        groups it wins, while the handful of groups that pick something else are noise. Averaging
        the two hides exactly the quantity the delegation direction depends on: whether the
        departures from the single best configuration are real.

        Beating the null is necessary but not sufficient, and the absolute floor is why. As the
        number of configurations grows the null collapses - the argmax of 134 noisy candidates
        almost never survives a resplit, so the null reproducibility falls to 0.008 - and then a
        wholly unreproducible 0.009 clears it. Requiring the winner to replicate on at least half of
        random half-splits keeps the criterion meaningful at any family size, and is the weakest
        statement under which "the best configuration for this group is X" means anything.
        """
        if not self.n_off_dominant:
            return False
        return bool(
            self.reproducibility_off_dominant > self.null_reproducibility
            and self.reproducibility_off_dominant >= MIN_REPRODUCIBILITY
        )

    @property
    def verdict(self) -> str:
        if not self.groups:
            return "NO EVIDENCE - no group had enough tasks to split"
        if not self.winners_are_reproducible:
            return (
                "NO EVIDENCE - per-group winners are not reproducible above chance, so their "
                "variety cannot be distinguished from argmax noise"
            )
        if self.dominance > 0.75:
            return "NO EVIDENCE - winners reproduce, but one configuration wins nearly everywhere"
        if not self.variety_is_reproducible:
            return (
                "NO EVIDENCE - the groups won by the dominant configuration reproduce "
                f"({self.reproducibility_dominant:.2f}) but the {self.n_off_dominant} that depart "
                f"from it do not ({self.reproducibility_off_dominant:.2f} against a "
                f"{self.null_reproducibility:.2f} null and a {MIN_REPRODUCIBILITY} floor), so the "
                "variety is noise around a single best configuration"
            )
        return "EVIDENCE - winners reproduce above chance and the departures from the best are real"

    def to_dict(self) -> dict[str, Any]:
        return {
            "grouping": self.grouping,
            "n_groups": len(self.groups),
            "excluded_groups": self.excluded_groups,
            "min_tasks_per_group": MIN_TASKS_PER_GROUP,
            "reproducibility": self.reproducibility,
            "null_reproducibility": self.null_reproducibility,
            "reproducibility_p": self.reproducibility_p,
            "winners_are_reproducible": self.winners_are_reproducible,
            "dominance": self.dominance,
            "null_dominance": self.null_dominance,
            "dominance_p": self.dominance_p,
            "dominant_configuration": self.dominant_configuration,
            "reproducibility_dominant": self.reproducibility_dominant,
            "reproducibility_off_dominant": self.reproducibility_off_dominant,
            "n_off_dominant": self.n_off_dominant,
            "variety_is_reproducible": self.variety_is_reproducible,
            "n_permutations": self.n_permutations,
            "verdict": self.verdict,
            "groups": [g.to_dict() for g in self.groups],
        }


def _outcomes(
    episodes: Sequence[EpisodeRecord],
    *,
    grouping: Grouping,
    by_configuration: bool,
    only_protocols: Sequence[str] | None = None,
) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    """configuration -> task -> correct, and task -> group, on tasks every configuration ran.

    Restricting to the shared task set is what makes the argmax a fair comparison: a protocol
    evaluated on an easier subset would win its group for a reason that has nothing to do with
    organization. The priced protocols only ran on the discriminating subset, so without this the
    comparison silently mixes denominators.
    """
    keep = set(only_protocols) if only_protocols else None
    raw: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    group: dict[str, str] = {}
    for e in episodes:
        if e.intervention.kind != "none":
            continue
        if keep is not None and e.protocol_id not in keep:
            continue
        key = (
            f"{e.protocol_id}[{'-'.join(map(str, sorted(e.coalition)))}]"
            if by_configuration
            else e.protocol_id
        )
        raw[key][e.task_id].append(bool(e.correct))
        group[e.task_id] = e.domain if grouping == "domain" else e.suite

    if not raw:
        return {}, {}
    shared = set.intersection(*[set(tasks) for tasks in raw.values()])
    outcomes = {
        key: {t: bool(np.mean(tasks[t]) >= 0.5) for t in shared} for key, tasks in raw.items()
    }
    return outcomes, {t: group[t] for t in shared}


def _argmax(outcomes: dict[str, dict[str, bool]], tasks: Sequence[str]) -> str | None:
    """The configuration with the highest accuracy on `tasks`, ties broken by name.

    Deterministic tie-breaking is deliberate. Random tie-breaking would inflate the null's
    disagreement rate and make observed reproducibility look better than it is.
    """
    if not tasks:
        return None
    means = {c: float(np.mean([outcomes[c][t] for t in tasks])) for c in sorted(outcomes)}
    best = max(means.values())
    return min(c for c, m in means.items() if m == best)


def _reproducibility(
    outcomes: dict[str, dict[str, bool]],
    tasks: Sequence[str],
    *,
    n_splits: int,
    rng: np.random.Generator,
) -> float:
    """Fraction of random half-splits on which both halves pick the same configuration."""
    tasks = list(tasks)
    if len(tasks) < MIN_TASKS_PER_GROUP:
        return float("nan")
    agree = 0
    half = len(tasks) // 2
    for _ in range(n_splits):
        order = rng.permutation(len(tasks))
        left = [tasks[i] for i in order[:half]]
        right = [tasks[i] for i in order[half : 2 * half]]
        agree += _argmax(outcomes, left) == _argmax(outcomes, right)
    return agree / n_splits


def _dominance(outcomes: dict[str, dict[str, bool]], by_group: dict[str, list[str]]) -> float:
    """Fraction of *groups* won by the single most frequent winner."""
    wins: dict[str, int] = defaultdict(int)
    n_groups = 0
    for tasks in by_group.values():
        winner = _argmax(outcomes, tasks)
        if winner is not None:
            wins[winner] += 1
            n_groups += 1
    return max(wins.values()) / n_groups if n_groups else float("nan")


def _permute(
    outcomes: dict[str, dict[str, bool]], tasks: Sequence[str], rng: np.random.Generator
) -> dict[str, dict[str, bool]]:
    """Shuffle configuration labels within each task.

    Preserves how many configurations solved each task, so task difficulty and group structure
    survive untouched, while any systematic difference between configurations is destroyed. This
    is the distribution the metric reads when there is nothing to find.
    """
    keys = sorted(outcomes)
    out: dict[str, dict[str, bool]] = {c: {} for c in keys}
    for task in tasks:
        column = [outcomes[c][task] for c in keys]
        rng.shuffle(column)
        for c, value in zip(keys, column, strict=True):
            out[c][task] = value
    return out


def winner_stability(
    episodes: Sequence[EpisodeRecord],
    *,
    grouping: Grouping = "domain",
    by_configuration: bool = False,
    only_protocols: Sequence[str] | None = None,
    n_splits: int = 400,
    n_permutations: int = 500,
    seed: int = 20260810,
) -> StabilityReport:
    """Reproducibility and variety of the best configuration per group.

    Set ``by_configuration`` to treat each protocol-coalition pair as its own configuration, which
    is what a router actually chooses; the default compares protocols on the grand coalition only,
    matching `protocol_dominance` so the two are directly comparable.

    ``only_protocols`` restricts the comparison before the shared-task intersection is taken, which
    matters more than it sounds: the paid protocols ran only on each pool's discriminating subset,
    so including them shrinks every analysis to that subset. Passing the two free protocols recovers
    all 366 tasks and all 15 coalitions.
    """
    rng = np.random.default_rng(seed)
    report = StabilityReport(grouping=grouping, n_permutations=n_permutations)

    outcomes, group_of = _outcomes(
        episodes,
        grouping=grouping,
        by_configuration=by_configuration,
        only_protocols=only_protocols,
    )
    if not outcomes:
        return report

    by_group: dict[str, list[str]] = defaultdict(list)
    for task, group in group_of.items():
        by_group[group].append(task)
    for tasks in by_group.values():
        tasks.sort()

    usable = {g: t for g, t in by_group.items() if len(t) >= MIN_TASKS_PER_GROUP}
    report.excluded_groups = {
        g: len(t) for g, t in sorted(by_group.items()) if len(t) < MIN_TASKS_PER_GROUP
    }
    if not usable:
        return report

    n_config = len(outcomes)
    for group, tasks in sorted(usable.items()):
        winner = _argmax(outcomes, tasks)
        report.groups.append(
            GroupStability(
                group=group,
                n_tasks=len(tasks),
                n_configurations=n_config,
                winner=winner,
                winner_accuracy=(
                    float(np.mean([outcomes[winner][t] for t in tasks])) if winner else float("nan")
                ),
                reproducibility=_reproducibility(
                    outcomes, tasks, n_splits=n_splits, rng=rng
                ),
                chance=1.0 / n_config,
            )
        )

    report.reproducibility = float(np.mean([g.reproducibility for g in report.groups]))
    report.dominance = _dominance(outcomes, usable)

    counts: dict[str, int] = defaultdict(int)
    for g in report.groups:
        if g.winner is not None:
            counts[g.winner] += 1
    if counts:
        top = max(sorted(counts), key=lambda c: counts[c])
        report.dominant_configuration = top
        on = [g.reproducibility for g in report.groups if g.winner == top]
        off = [g.reproducibility for g in report.groups if g.winner != top]
        report.n_off_dominant = len(off)
        report.reproducibility_dominant = float(np.mean(on)) if on else float("nan")
        report.reproducibility_off_dominant = float(np.mean(off)) if off else float("nan")

    all_tasks = sorted(group_of)
    null_repro = np.empty(n_permutations)
    null_dom = np.empty(n_permutations)
    for i in range(n_permutations):
        shuffled = _permute(outcomes, all_tasks, rng)
        null_repro[i] = float(
            np.mean(
                [
                    _reproducibility(shuffled, tasks, n_splits=max(40, n_splits // 8), rng=rng)
                    for tasks in usable.values()
                ]
            )
        )
        null_dom[i] = _dominance(shuffled, usable)

    report.null_reproducibility = float(null_repro.mean())
    report.null_dominance = float(null_dom.mean())
    # One-tailed: real structure makes winners *more* reproducible than shuffled labels do.
    report.reproducibility_p = float((null_repro >= report.reproducibility).mean())
    report.dominance_p = float((null_dom >= report.dominance).mean())
    return report
