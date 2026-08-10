"""Coalition-value analysis: synergy, Harsanyi decomposition, submodularity, prediction.

Implements the coalition-landscape direction of the research report. The central object is
the coalition value tensor

    v[x, mask] = P(Y_{x,S,g} = 1) - lambda * C(S, g),   S = agents in `mask`

indexed by task and by a bitmask over pool agent ids, with ``mask == 0`` (the empty
coalition) pinned to zero so the Harsanyi dividends are well defined.

Everything here is exact rather than sampled, which is affordable because the report
restricts the main analysis to four agents (15 non-empty coalitions). The exhaustive
routines refuse above 12 agents.

A note on what these numbers mean. When the tensor is built from *observed* episodes, the
values are real. When it is built from independent per-agent outcomes via
:func:`simulate_coalition_values`, they are a counterfactual reconstruction under an
assumed aggregation rule, and any conclusion inherits that assumption. The free pilot uses
the simulated path deliberately, to exercise this code on real data at zero cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Literal, Sequence

import numpy as np

AggregationRule = Literal["any", "plurality_distinct_errors", "majority_strict", "best_member"]


# ---- tensor construction --------------------------------------------------------------


def mask_of(agent_ids: Sequence[int]) -> int:
    mask = 0
    for agent_id in agent_ids:
        mask |= 1 << agent_id
    return mask


def members_of(mask: int, n_agents: int) -> list[int]:
    return [i for i in range(n_agents) if mask & (1 << i)]


def popcount(mask: int) -> int:
    return bin(mask).count("1")


def simulate_coalition_values(
    outcomes: np.ndarray,
    *,
    rule: AggregationRule = "plurality_distinct_errors",
    tie_break: float = 0.5,
) -> np.ndarray:
    """Reconstruct ``v[x, mask]`` from independent per-agent correctness.

    ``outcomes`` is a ``(n_tasks, n_agents)`` binary array. The returned tensor is
    ``(n_tasks, 2**n_agents)`` float, with column 0 (empty coalition) equal to zero.

    The rules differ in what they assume about *wrong* answers, which the binary matrix
    does not record:

    ``any``
        The coalition is correct if any member is. An upper bound that assumes a perfect
        verifier can always recognise the right answer.
    ``plurality_distinct_errors``
        Wrong answers are assumed mutually distinct, so each has vote count one. The
        correct answer wins outright with two or more correct members, and ties with the
        singletons when exactly one member is correct. Reasonable for open-ended outputs
        such as code patches; wrong for multiple choice, where wrong answers collide.
    ``majority_strict``
        The coalition is correct only if strictly more than half its members are.
        Appropriate when wrong answers do collide.
    ``best_member``
        The lowest-indexed member decides, so callers pass agents pre-sorted by calibrated
        competence. This is the top-1 routing baseline.

    ``tie_break`` is the probability the correct answer survives a tie, used by the
    plurality rule. It enters as a fractional value rather than a coin flip so the tensor
    stays deterministic.
    """
    outcomes = np.asarray(outcomes)
    if outcomes.ndim != 2:
        raise ValueError(f"outcomes must be 2-D (n_tasks, n_agents), got {outcomes.shape}")
    n_tasks, n_agents = outcomes.shape
    if n_agents > 12:
        raise ValueError(f"refusing exhaustive enumeration for {n_agents} agents")

    n_masks = 1 << n_agents
    values = np.zeros((n_tasks, n_masks), dtype=float)

    for mask in range(1, n_masks):
        members = members_of(mask, n_agents)
        member_outcomes = outcomes[:, members]
        n_correct = member_outcomes.sum(axis=1)
        size = len(members)

        if rule == "any":
            values[:, mask] = (n_correct >= 1).astype(float)
        elif rule == "majority_strict":
            values[:, mask] = (n_correct * 2 > size).astype(float)
        elif rule == "best_member":
            values[:, mask] = member_outcomes[:, 0].astype(float)
        elif rule == "plurality_distinct_errors":
            n_wrong = size - n_correct
            outright = n_correct >= 2
            # Exactly one correct member ties with each distinct wrong answer.
            tied = (n_correct == 1) & (n_wrong >= 1)
            solo = (n_correct == 1) & (n_wrong == 0)  # singleton coalition, correct
            values[:, mask] = outright.astype(float) + solo.astype(float)
            values[tied, mask] = tie_break
        else:
            raise ValueError(f"unknown aggregation rule {rule!r}")

    return values


def apply_cost_penalty(
    values: np.ndarray,
    *,
    per_agent_cost: Sequence[float] | None = None,
    lambda_cost: float = 0.0,
) -> np.ndarray:
    """Subtract ``lambda_cost * C(S)`` from every coalition value.

    Cost is additive in members, which is exactly right for the independent-commitment
    protocol the report fixes for the main coalition analysis (D-008).
    """
    if lambda_cost == 0.0 or per_agent_cost is None:
        return values
    n_agents = int(np.log2(values.shape[1]))
    costs = np.asarray(per_agent_cost, dtype=float)
    if costs.shape[0] != n_agents:
        raise ValueError(f"expected {n_agents} per-agent costs, got {costs.shape[0]}")
    penalty = np.array(
        [
            costs[members_of(mask, n_agents)].sum() if mask else 0.0
            for mask in range(values.shape[1])
        ]
    )
    return values - lambda_cost * penalty[None, :]


# ---- Harsanyi / Moebius decomposition -------------------------------------------------


def harsanyi_dividends(values: np.ndarray) -> np.ndarray:
    """Moebius transform of the coalition value function, per task.

    Returns an array shaped like ``values`` where entry ``[x, T]`` is

        Delta_x(T) = sum_{U subset T} (-1)^{|T| - |U|} v_x(U)

    computed with the fast inverse zeta transform in O(n * 2^n) rather than the naive
    O(3^n) double sum, which matters once the pool grows past about eight agents.
    """
    values = np.asarray(values, dtype=float)
    n_masks = values.shape[1]
    n_agents = n_masks.bit_length() - 1
    if 1 << n_agents != n_masks:
        raise ValueError(f"value tensor width {n_masks} is not a power of two")

    dividends = values.copy()
    for bit in range(n_agents):
        stride = 1 << bit
        for mask in range(n_masks):
            if mask & stride:
                dividends[:, mask] -= dividends[:, mask ^ stride]
    return dividends


def higher_order_ratio(dividends: np.ndarray, *, min_order: int = 3) -> np.ndarray:
    """Per-task ``R_{>=k}``: the share of total interaction mass at order k and above.

    The report's interpretation: if this is consistently small, pairwise complementarity
    models are scientifically justified. If it is large, that is itself an important
    negative result about simple complementarity models.
    """
    dividends = np.asarray(dividends, dtype=float)
    n_masks = dividends.shape[1]
    n_agents = n_masks.bit_length() - 1
    orders = np.array([popcount(mask) for mask in range(n_masks)])

    absolute = np.abs(dividends)
    total = absolute[:, orders >= 1].sum(axis=1)
    high = absolute[:, orders >= min_order].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(total > 0, high / total, 0.0)
    del n_agents
    return ratio


def pairwise_synergy(values: np.ndarray, i: int, j: int) -> np.ndarray:
    """``Syn_ij(x) = v({i,j}) - v({i}) - v({j})``, with ``v(empty) = 0``."""
    if i == j:
        raise ValueError("pairwise synergy requires two distinct agents")
    both = values[:, mask_of([i, j])]
    return both - values[:, mask_of([i])] - values[:, mask_of([j])]


def synergy_matrix(values: np.ndarray, n_agents: int) -> dict[tuple[int, int], np.ndarray]:
    return {(i, j): pairwise_synergy(values, i, j) for i, j in combinations(range(n_agents), 2)}


# ---- submodularity --------------------------------------------------------------------


def submodularity_violations(values: np.ndarray) -> dict[str, Any]:
    """Test the local characterization of submodularity, per task.

    A set function is submodular iff for every ``S`` and every distinct ``i, j`` outside
    ``S``:

        v(S + i) + v(S + j) >= v(S + i + j) + v(S)

    This local form is equivalent to the marginal-returns definition the report states, and
    checking it is O(2^n * n^2) rather than O(3^n).

    Measuring the violation rate tests whether greedy team construction is theoretically
    justified — which the report flags as a useful result in either direction.
    """
    values = np.asarray(values, dtype=float)
    n_tasks, n_masks = values.shape
    n_agents = n_masks.bit_length() - 1

    violations = np.zeros(n_tasks, dtype=int)
    comparisons = 0
    worst = np.zeros(n_tasks, dtype=float)

    for base in range(n_masks):
        outside = [a for a in range(n_agents) if not base & (1 << a)]
        for i, j in combinations(outside, 2):
            comparisons += 1
            lhs = values[:, base | (1 << i)] + values[:, base | (1 << j)]
            rhs = values[:, base | (1 << i) | (1 << j)] + values[:, base]
            deficit = rhs - lhs  # positive means submodularity is violated
            violated = deficit > 1e-12
            violations += violated.astype(int)
            worst = np.maximum(worst, np.where(violated, deficit, 0.0))

    rate = violations / comparisons if comparisons else np.zeros(n_tasks)
    return {
        "comparisons_per_task": comparisons,
        "violations_per_task": violations,
        "violation_rate_per_task": rate,
        "mean_violation_rate": float(rate.mean()) if comparisons else 0.0,
        "tasks_with_any_violation": float((violations > 0).mean()),
        "worst_violation_per_task": worst,
        "max_violation": float(worst.max()) if n_tasks else 0.0,
    }


# ---- error diversity ------------------------------------------------------------------


def error_correlation(outcomes: np.ndarray) -> np.ndarray:
    """Pairwise correlation of *error* indicators across tasks.

    For binary vectors the Pearson correlation is the phi coefficient. Agents whose errors
    are uncorrelated are the ones a coalition can benefit from; agents with correlated
    errors share failure modes and stack redundantly. Pairs with no variance in error
    (an agent that is always right or always wrong) yield zero rather than NaN.
    """
    outcomes = np.asarray(outcomes)
    errors = 1 - outcomes
    n_agents = errors.shape[1]
    correlation = np.zeros((n_agents, n_agents), dtype=float)
    for i in range(n_agents):
        correlation[i, i] = 1.0
        for j in range(i + 1, n_agents):
            a, b = errors[:, i].astype(float), errors[:, j].astype(float)
            if a.std() < 1e-12 or b.std() < 1e-12:
                value = 0.0
            else:
                value = float(np.corrcoef(a, b)[0, 1])
            correlation[i, j] = correlation[j, i] = value
    return correlation


# ---- selection: oracle, top-k, regret -------------------------------------------------


def best_coalition_per_task(values: np.ndarray) -> np.ndarray:
    """Argmax mask per task over non-empty coalitions."""
    # Column 0 is the empty coalition and must never win.
    candidates = values[:, 1:]
    return 1 + np.argmax(candidates, axis=1)


def top_k_mask(individual_competence: Sequence[float], k: int) -> int:
    """Mask of the k individually strongest agents."""
    order = np.argsort(-np.asarray(individual_competence, dtype=float), kind="stable")
    return mask_of([int(a) for a in order[:k]])


def top_k_gap(values: np.ndarray, individual_competence: Sequence[float], k: int) -> dict[str, Any]:
    """``TopKGap = v_x(S*) - v_x(S_top-k)``, restricted to same-size coalitions.

    Comparing the best coalition of *any* size against a size-k baseline would conflate
    complementarity with simply spending more, so the oracle here is the best coalition of
    the same size.
    """
    values = np.asarray(values, dtype=float)
    n_agents = values.shape[1].bit_length() - 1
    same_size = [mask for mask in range(1, values.shape[1]) if popcount(mask) == k]
    if not same_size:
        raise ValueError(f"no coalitions of size {k} for {n_agents} agents")

    baseline_mask = top_k_mask(individual_competence, k)
    baseline = values[:, baseline_mask]
    best_same_size = values[:, same_size].max(axis=1)
    gap = best_same_size - baseline
    return {
        "k": k,
        "baseline_mask": baseline_mask,
        "baseline_members": members_of(baseline_mask, n_agents),
        "gap_per_task": gap,
        "mean_gap": float(gap.mean()),
        # The report's continue signal: top-k is >= 5 points below the best same-size
        # coalition on 15% or more of tasks.
        "frac_tasks_gap_ge_5pp": float((gap >= 0.05).mean()),
        "frac_tasks_gap_positive": float((gap > 1e-12).mean()),
    }


def selection_regret(values: np.ndarray, chosen_masks: Sequence[int]) -> np.ndarray:
    """``v_x(S*) - v_x(S_hat)`` per task, over non-empty coalitions."""
    values = np.asarray(values, dtype=float)
    best = values[:, 1:].max(axis=1)
    chosen = values[np.arange(values.shape[0]), np.asarray(chosen_masks, dtype=int)]
    return best - chosen


# ---- predictive models ----------------------------------------------------------------


@dataclass
class CoalitionDataset:
    """Long-format (task, coalition) observations for model fitting."""

    task_index: np.ndarray  # (n_obs,) int
    masks: np.ndarray  # (n_obs,) int
    outcome: np.ndarray  # (n_obs,) float in [0, 1]
    n_agents: int
    task_difficulty: np.ndarray | None = None  # (n_obs,) float, the b(x) term

    def __len__(self) -> int:
        return len(self.outcome)


def build_coalition_dataset(
    values: np.ndarray,
    *,
    task_difficulty: np.ndarray | None = None,
    include_singletons: bool = True,
) -> CoalitionDataset:
    values = np.asarray(values, dtype=float)
    n_tasks, n_masks = values.shape
    n_agents = n_masks.bit_length() - 1

    masks = [
        mask
        for mask in range(1, n_masks)
        if include_singletons or popcount(mask) > 1
    ]
    task_index = np.repeat(np.arange(n_tasks), len(masks))
    mask_column = np.tile(np.asarray(masks), n_tasks)
    outcome = values[task_index, mask_column]
    difficulty = None
    if task_difficulty is not None:
        difficulty = np.asarray(task_difficulty, dtype=float)[task_index]
    return CoalitionDataset(
        task_index=task_index,
        masks=mask_column,
        outcome=outcome,
        n_agents=n_agents,
        task_difficulty=difficulty,
    )


def design_matrix(
    dataset: CoalitionDataset,
    *,
    pairwise: bool,
    include_size: bool = True,
) -> tuple[np.ndarray, list[str]]:
    """Features for the additive and pairwise models of the report.

    Additive:  logit P = b(x) + sum_{i in S} alpha_i
    Pairwise:  logit P = b(x) + sum_{i in S} alpha_i + sum_{i<j in S} beta_ij

    A coalition-size column is included by default so that the pairwise terms are not
    absorbing a pure size effect, which the report calls out explicitly: complementarity
    must survive controlling for individual accuracy and coalition size.
    """
    n_agents = dataset.n_agents
    columns: list[np.ndarray] = []
    names: list[str] = []

    if dataset.task_difficulty is not None:
        columns.append(dataset.task_difficulty)
        names.append("task_difficulty")

    for agent in range(n_agents):
        columns.append(((dataset.masks >> agent) & 1).astype(float))
        names.append(f"alpha_{agent}")

    if include_size:
        sizes = np.array([popcount(int(m)) for m in dataset.masks], dtype=float)
        columns.append(sizes)
        names.append("size")

    if pairwise:
        for i, j in combinations(range(n_agents), 2):
            both = (((dataset.masks >> i) & 1) & ((dataset.masks >> j) & 1)).astype(float)
            columns.append(both)
            names.append(f"beta_{i}_{j}")

    return np.column_stack(columns), names


@dataclass
class FitResult:
    name: str
    feature_names: list[str] = field(default_factory=list)
    coefficients: dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0
    train_log_loss: float = float("nan")
    test_log_loss: float = float("nan")
    test_brier: float = float("nan")
    test_auc: float = float("nan")
    n_train: int = 0
    n_test: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
            "train_log_loss": self.train_log_loss,
            "test_log_loss": self.test_log_loss,
            "test_brier": self.test_brier,
            "test_auc": self.test_auc,
            "n_train": self.n_train,
            "n_test": self.n_test,
        }


def fit_logistic(
    dataset: CoalitionDataset,
    *,
    pairwise: bool,
    train_rows: np.ndarray,
    test_rows: np.ndarray,
    name: str,
    l2: float = 1.0,
) -> FitResult:
    """Fit the additive or pairwise coalition model and score it on held-out rows.

    Outcomes may be fractional (the plurality rule produces 0.5 on ties), so the fit uses
    sample weighting over duplicated 0/1 targets rather than requiring hard labels.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score

    features, names = design_matrix(dataset, pairwise=pairwise)
    y = dataset.outcome

    x_train, y_train = features[train_rows], y[train_rows]
    x_test, y_test = features[test_rows], y[test_rows]

    # Represent fractional targets as both classes with complementary weights.
    x_aug = np.vstack([x_train, x_train])
    y_aug = np.concatenate([np.ones_like(y_train), np.zeros_like(y_train)])
    w_aug = np.concatenate([y_train, 1.0 - y_train])
    keep = w_aug > 1e-12
    if len(np.unique(y_aug[keep])) < 2:
        raise ValueError(f"{name}: training targets are degenerate; cannot fit")

    model = LogisticRegression(C=1.0 / max(l2, 1e-9), max_iter=2000)
    model.fit(x_aug[keep], y_aug[keep], sample_weight=w_aug[keep])

    def _log_loss(x: np.ndarray, target: np.ndarray) -> float:
        if len(target) == 0:
            return float("nan")
        probability = model.predict_proba(x)[:, 1]
        probability = np.clip(probability, 1e-12, 1 - 1e-12)
        return float(
            -np.mean(target * np.log(probability) + (1 - target) * np.log(1 - probability))
        )

    result = FitResult(
        name=name,
        feature_names=names,
        coefficients={n: float(c) for n, c in zip(names, model.coef_[0], strict=True)},
        intercept=float(model.intercept_[0]),
        train_log_loss=_log_loss(x_train, y_train),
        test_log_loss=_log_loss(x_test, y_test),
        n_train=int(len(y_train)),
        n_test=int(len(y_test)),
    )
    if len(y_test):
        probability = model.predict_proba(x_test)[:, 1]
        result.test_brier = float(brier_score_loss(np.round(y_test), probability))
        hard = np.round(y_test)
        if len(np.unique(hard)) > 1:
            result.test_auc = float(roc_auc_score(hard, probability))
    return result


def held_out_coalition_split(
    dataset: CoalitionDataset,
    *,
    held_out_masks: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Split so that entire coalitions are unseen in training.

    This is the report's critical novelty test for the coalition direction: predicting the
    value of coalitions never observed. A held-out-task split does not test it, because the
    same coalitions appear in training on other tasks.
    """
    held = {int(m) for m in held_out_masks}
    is_test = np.array([int(m) in held for m in dataset.masks])
    return np.where(~is_test)[0], np.where(is_test)[0]


def held_out_task_split(
    dataset: CoalitionDataset,
    *,
    held_out_tasks: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    held = {int(t) for t in held_out_tasks}
    is_test = np.array([int(t) in held for t in dataset.task_index])
    return np.where(~is_test)[0], np.where(is_test)[0]
