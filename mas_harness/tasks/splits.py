"""Deterministic, domain-stratified splits.

Two split families are needed by the research plan and they are different things:

* ``calibration`` vs ``test`` — required because the predicted expert must be chosen from
  calibration data only (D-004). Without this split, EUR and dilution are computed with an
  oracle and are overstated.
* leave-one-domain-out — required by the delegation direction, which must show that an
  organizational representation transfers across surface domains rather than memorizing
  them.

All splits are stratified by domain and seeded, so a manifest always yields the same
split for the same seed.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Iterable, Sequence


def stratified_split(
    items: Sequence[tuple[str, str]],
    *,
    fraction: float,
    seed: int,
) -> tuple[list[str], list[str]]:
    """Split ``(task_id, domain)`` pairs into (first, second) stratified by domain.

    ``fraction`` is the share going to the first group. Stratification is per-domain, and
    rounding uses ``round`` so a domain with very few tasks still contributes to both
    groups where possible.
    """
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"fraction must be strictly between 0 and 1, got {fraction}")

    by_domain: dict[str, list[str]] = defaultdict(list)
    for task_id, domain in items:
        by_domain[domain].append(task_id)

    rng = random.Random(seed)
    first: list[str] = []
    second: list[str] = []
    for domain in sorted(by_domain):
        task_ids = sorted(by_domain[domain])
        rng.shuffle(task_ids)
        n_first = int(round(len(task_ids) * fraction))
        # Never let a domain contribute zero to either side when it has >= 2 tasks.
        if len(task_ids) >= 2:
            n_first = max(1, min(len(task_ids) - 1, n_first))
        first.extend(task_ids[:n_first])
        second.extend(task_ids[n_first:])
    return sorted(first), sorted(second)


def leave_one_domain_out(
    items: Sequence[tuple[str, str]],
) -> dict[str, tuple[list[str], list[str]]]:
    """For each domain, return (train ids, held-out ids)."""
    by_domain: dict[str, list[str]] = defaultdict(list)
    for task_id, domain in items:
        by_domain[domain].append(task_id)

    folds: dict[str, tuple[list[str], list[str]]] = {}
    for held_out in sorted(by_domain):
        test = sorted(by_domain[held_out])
        train = sorted(
            task_id for domain, ids in by_domain.items() if domain != held_out for task_id in ids
        )
        folds[held_out] = (train, test)
    return folds


def k_fold(task_ids: Sequence[str], *, k: int, seed: int) -> list[tuple[list[str], list[str]]]:
    """Plain k-fold over task ids, seeded. Used for cross-validated selectors."""
    if k < 2:
        raise ValueError(f"k must be at least 2, got {k}")
    ids = sorted(task_ids)
    if len(ids) < k:
        raise ValueError(f"cannot make {k} folds from {len(ids)} tasks")
    rng = random.Random(seed)
    rng.shuffle(ids)
    folds: list[tuple[list[str], list[str]]] = []
    for fold_index in range(k):
        test = sorted(ids[fold_index::k])
        train = sorted(set(ids) - set(test))
        folds.append((train, test))
    return folds


def stratified_subset(
    items: Sequence[tuple[str, str]],
    *,
    fraction: float,
    seed: int,
) -> list[str]:
    """A domain-stratified subset, for the repeated-seed and role-rotation subsets.

    The research report recommends spending repeated seeds on a stratified 20-30% subset
    rather than re-running every task.
    """
    subset, _ = stratified_split(items, fraction=fraction, seed=seed)
    return subset


def counts_by(items: Iterable[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for _, key in items:
        counts[key] += 1
    return dict(sorted(counts.items()))
