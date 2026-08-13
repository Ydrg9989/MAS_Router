"""Choosing *which* fixed organization to run — the question the project never asked.

Every routing experiment here treats "the best organization on calibration" as the incumbent
baseline, and every one of them reports that a router cannot beat it. What none of them asked is
whether the incumbent is any good.

It is not. D-040 measures the calibration argmax losing **2.39 pp** on `crosscap240` and 1.01 pp on
`hard366` between calibration and test. D-037 established that this gap is the winner's curse rather
than interaction, and that distinction is what makes it interesting: unlike oracle headroom, which
is the maximum of a noisy family and therefore phantom, **a selection bias in a chosen maximum is
real and partly recoverable**. Shrinking a selected estimate toward the family mean is the textbook
remedy, and no method in `Docs/literature/ROUTING_ARCHITECTURES.md` applies one — they all compare
against "the best model on validation" as if that were free of selection noise.

So this module implements seven rules for choosing one organization and scores them against each
other. Two of them use no calibration data at all, which is the cleanest possible answer to a
winner's curse, and one is fitted across *other pools* so that pool composition rather than pool
outcomes drives the choice.

`oracle_fixed` is a ceiling and is labelled as such: it reads test outcomes and is never a policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .research_questions import Grid, stratified_resplit, summarise

# Shrinkage strength for `shrunk`, in units of calibration tasks. With k tasks of evidence per
# organization the estimate is pulled toward the family mean by k/(k+SHRINKAGE_K); at the ~80
# calibration tasks these suites carry that is a pull of about a fifth, which is the right order
# for a maximum selected over thirty candidates.
SHRINKAGE_K = 20.0

RULES = (
    "argmax",
    "one_se",
    "shrunk",
    "whole_pool_vote",
    "largest_within_se",
    "cross_pool",
    "oracle_fixed",
)


def _standard_error(best: float, n: int) -> float:
    accuracy = float(np.clip(best, 0.0, 1.0))
    return float(np.sqrt(max(accuracy * (1.0 - accuracy), 1e-6) / max(n, 1)))


def _grand_coalition_vote(grid: Grid) -> int | None:
    """The whole pool running the aggregation protocol, chosen with no calibration at all.

    D-029 found this to be the one organizational fact that reproduced on every suite and pool, so
    it is carried as a named rule rather than left for the argmax to rediscover.
    """
    size = max(len(c) for c in grid.members)
    candidates = [
        row
        for row, coalition in enumerate(grid.members)
        if len(coalition) == size and grid.protocols[row] == "independent_majority"
    ]
    return candidates[0] if candidates else None


def _structural_prediction(
    grid: Grid, train: np.ndarray, accuracy: np.ndarray
) -> np.ndarray:
    """What an organization's structure predicts its accuracy to be, fitted on this pool.

    A least-squares fit of calibration accuracy on the same descriptors `cross_pool` uses, but
    within the pool rather than across pools. Its role is to be a *smooth* target to shrink toward:
    it cannot chase the noise in any individual organization's estimate because it has seven
    parameters for thirty organizations.
    """
    features = np.array(
        [organization_descriptor(grid, row, train) for row in range(grid.n_org)]
    )
    if grid.n_org <= features.shape[1] + 1:
        return np.full(grid.n_org, float(accuracy.mean()))
    coefficients, *_ = np.linalg.lstsq(features, accuracy, rcond=None)
    return features @ coefficients


def choose(
    grid: Grid,
    train: np.ndarray,
    *,
    cross_pool_scores: np.ndarray | None = None,
) -> dict[str, int]:
    """One organization per rule, every rule frozen on ``train``.

    ``cross_pool_scores`` is a per-organization score fitted on *other* pools; supplying it enables
    the `cross_pool` rule, which is the only one that uses information from outside this pool.
    """
    accuracy = grid.correct[:, train].mean(axis=1)
    n = len(train)
    best = float(accuracy.max())
    error = _standard_error(best, n)
    within = np.flatnonzero(accuracy >= best - error)

    picks: dict[str, int] = {"argmax": int(np.argmax(accuracy))}
    picks["one_se"] = int(
        min(within, key=lambda i: (len(grid.members[i]), grid.labels[i]))
    )
    picks["largest_within_se"] = int(
        max(within, key=lambda i: (len(grid.members[i]), -i))
    )

    # Shrink toward a *structural* prediction, not toward the family mean.
    #
    # Classical shrinkage cannot help here and it is worth being explicit about why: every
    # organization is scored on the same calibration tasks, so every estimate has the same n, and
    # any common shrinkage — James-Stein, a Beta-binomial posterior, a convex pull toward the grand
    # mean — is a *monotone* transformation of the raw accuracy. The argmax is unchanged and the
    # winner's curse survives intact. The bias is only correctable using information that
    # distinguishes organizations, which here means their structure: protocol, size, and the
    # strength of their members relative to the pool.
    predicted = _structural_prediction(grid, train, accuracy)
    weight = n / (n + SHRINKAGE_K)
    picks["shrunk"] = int(np.argmax(weight * accuracy + (1.0 - weight) * predicted))

    vote = _grand_coalition_vote(grid)
    if vote is not None:
        picks["whole_pool_vote"] = vote
    if cross_pool_scores is not None:
        picks["cross_pool"] = int(np.argmax(cross_pool_scores))
    return picks


def organization_descriptor(grid: Grid, row: int, train: np.ndarray) -> np.ndarray:
    """What an organization looks like, without reference to how well it did on this pool.

    Deliberately excludes this pool's outcomes for the organization itself: the `cross_pool` rule
    must transfer a *shape* — protocol, size, member strength relative to the pool — rather than a
    remembered score, or it is just the argmax with extra steps.
    """
    coalition = grid.members[row]
    singles = {
        grid.members[r][0]: float(grid.correct[r, train].mean())
        for r in range(grid.n_org)
        if len(grid.members[r]) == 1
    }
    scores = [singles.get(a, 0.5) for a in coalition]
    pool_mean = float(np.mean(list(singles.values()))) if singles else 0.5
    pool_best = float(np.max(list(singles.values()))) if singles else 0.5
    return np.array(
        [
            1.0,
            float(grid.protocols[row] == "independent_majority"),
            len(coalition) / max(1, len(singles)),
            float(np.mean(scores)) - pool_mean,
            float(np.max(scores)) - pool_best,
            float(np.max(scores) - np.min(scores)),
            float(np.mean(scores)),
        ]
    )


@dataclass
class PoolSample:
    """One pool's contribution to the cross-pool fit: descriptors and realised accuracies."""

    features: np.ndarray
    outcome: np.ndarray


def cross_pool_fit(samples: Sequence[PoolSample]) -> np.ndarray | None:
    """Least-squares map from organization descriptors to calibration accuracy, across pools."""
    if not samples:
        return None
    x = np.vstack([s.features for s in samples])
    y = np.concatenate([s.outcome for s in samples])
    if len(y) < x.shape[1] + 2:
        return None
    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    return coefficients


def evaluate_rules(
    grid: Grid,
    *,
    coefficients: np.ndarray | None = None,
    n_repeats: int = 60,
    calibration_fraction: float = 0.5,
    seed: int = 20260813,
) -> dict[str, Any]:
    """Score every selection rule over resplits, as accuracy and as gain over the argmax."""
    rng = np.random.default_rng(seed)
    accuracy: dict[str, list[float]] = {}
    gain: dict[str, list[float]] = {}

    for _ in range(n_repeats):
        train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
        scores = (
            np.array(
                [organization_descriptor(grid, row, train) @ coefficients
                 for row in range(grid.n_org)]
            )
            if coefficients is not None
            else None
        )
        picks = choose(grid, train, cross_pool_scores=scores)
        picks["oracle_fixed"] = int(np.argmax(grid.correct[:, test].mean(axis=1)))

        incumbent = float(grid.correct[picks["argmax"], test].mean())
        for name, row in picks.items():
            value = float(grid.correct[row, test].mean())
            accuracy.setdefault(name, []).append(value)
            gain.setdefault(name, []).append(100.0 * (value - incumbent))

    return {
        "n_repeats": n_repeats,
        "accuracy": {name: summarise(v) for name, v in sorted(accuracy.items())},
        "gain_over_argmax": {name: summarise(v) for name, v in sorted(gain.items())},
    }


def protocol_rules(
    grid: Grid,
    *,
    n_repeats: int = 60,
    calibration_fraction: float = 0.5,
    seed: int = 20260813,
) -> dict[str, Any]:
    """Each protocol on the grand coalition as an *a-priori* rule, versus a calibrated baseline.

    D-041 found the calibration-best protocol does not reproduce across a resplit (0.00-0.17), which
    is the D-029 pattern. A protocol named in advance has no winner's curse at all, so this is the
    only form in which a protocol recommendation is worth making. The comparator is the best
    aggregation rule *chosen on calibration*, which is what a practitioner would otherwise do.
    """
    size = max(len(c) for c in grid.members)
    grand = {
        grid.protocols[row]: row
        for row in range(grid.n_org)
        if len(grid.members[row]) == size
    }
    aggregation = [
        row for name, row in grand.items()
        if name in ("independent_majority", "single_expert")
    ]
    if len(grand) < 2 or not aggregation:
        return {"note": "no grand-coalition protocol family here"}

    rng = np.random.default_rng(seed)
    gains: dict[str, list[float]] = {}
    for _ in range(n_repeats):
        train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
        calibrated = grid.correct[np.ix_(aggregation, train)].mean(axis=1)
        baseline_row = aggregation[int(np.argmax(calibrated))]
        baseline = float(grid.correct[baseline_row, test].mean())
        for name, row in grand.items():
            gains.setdefault(name, []).append(
                100.0 * (float(grid.correct[row, test].mean()) - baseline)
            )
    return {
        "n_repeats": n_repeats,
        "n_tasks": grid.n_task,
        "gain_over_calibrated_aggregation": {n: summarise(v) for n, v in sorted(gains.items())},
    }
