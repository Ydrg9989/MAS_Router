"""RQ2-RQ5: the four delegation questions that were specified and never run.

`Docs/literature/LITERATURE_REVIEW.md` §24 defines five research questions for the delegation
direction. RQ1 was retired (D-030) and RQ2 was closed for *aggregation* families (D-033, D-040).
But every routing result in this project chose among 15 coalitions crossed with 2 aggregation
rules, and RQ3, RQ4 and RQ5 were never built at all. This module supplies the missing four, under
the controls the pre-registration of 2026-08-13 fixes.

``RQ2'`` **interaction in the choice set.** Add the five priced protocols to the family, so the
    router can choose *debate* rather than only *which subset votes*. That is the decision MasRouter
    calls collaboration-mode selection, and no experiment here has ever posed it.
``RQ3``  **is dense counterfactual supervision worth collecting?** A deployment logs one
    organization per task; this project has all thirty. At a matched budget of observed cells, does
    the dense design buy more than an ordinary execution log? A question about data, not routers.
``RQ4``  **does any of it generalize?** Every routing number so far comes from an IID split. Held
    out by domain, by agent, and by organization, the numbers are free and have never been computed.
``RQ5``  **when not to collaborate.** A narrower decision than "which organization": solo or team.

Everything here delegates the actual model to `routing.py`'s primitives rather than reimplementing
them, so the leakage discipline is the same instrument that produced D-033 and D-040. Two deviations
are deliberate and marked in the code: fitting must be restricted to an arbitrary set of *observed
cells* (RQ3 needs this, and the competence features have to respect it or the dense arm's advantage
leaks into the sparse one), and scoring must be restricted to an arbitrary set of *candidate rows*
(RQ4 needs this).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .routing import _best_row, _pair_matrix, _task_features


@dataclass
class Grid:
    """An organization-by-task outcome table, plus what a router is allowed to see.

    Deliberately not `routing._Grid`: that one is built from episodes and carries cost and latency
    this module does not use. The shared thing is the *primitives* applied to it.
    """

    labels: list[str]
    tasks: list[str]
    correct: np.ndarray
    """(n_organizations, n_tasks) float 0/1."""
    members: list[tuple[int, ...]]
    """Coalition membership per organization, for agent holdout and the solo/collaborate split."""
    protocols: list[str]
    domain_index: np.ndarray
    embeddings: np.ndarray

    @property
    def n_org(self) -> int:
        return len(self.labels)

    @property
    def n_task(self) -> int:
        return len(self.tasks)


def _competence(grid: Grid, train: np.ndarray, observed: np.ndarray | None) -> dict[int, float]:
    """Per-agent competence from singleton organizations, over *observed* training cells only.

    `routing._organization_features` computes this from every singleton row on every training task.
    RQ3 cannot use that: in the observational arm most cells were never seen, and letting the
    features read them would hand the sparse arm the dense arm's information.
    """
    scores: dict[int, float] = {}
    for row, coalition in enumerate(grid.members):
        if len(coalition) != 1:
            continue
        columns = train if observed is None else train[observed[row, train]]
        if columns.size:
            scores.setdefault(coalition[0], float(grid.correct[row, columns].mean()))
    return scores


def _organization_features(
    grid: Grid, train: np.ndarray, observed: np.ndarray | None = None
) -> np.ndarray:
    """Protocol, membership, size and member competence — the same feature set as `routing.py`."""
    protocols = sorted(set(grid.protocols))
    agents = sorted({a for coalition in grid.members for a in coalition})
    competence = _competence(grid, train, observed)

    rows = []
    for row in range(grid.n_org):
        coalition = grid.members[row]
        scores = [competence.get(a, 0.5) for a in coalition]
        rows.append(
            [
                *[float(grid.protocols[row] == p) for p in protocols],
                *[float(a in coalition) for a in agents],
                len(coalition) / max(1, len(agents)),
                float(np.mean(scores)),
                float(np.max(scores)),
                float(np.max(scores) - np.min(scores)),
            ]
        )
    matrix = np.asarray(rows, dtype=float)
    spread = matrix.std(axis=0, keepdims=True)
    return matrix / np.where(spread < 1e-12, 1.0, spread)


def _fit_scores(
    grid: Grid,
    task_features: np.ndarray,
    organization_features: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    *,
    observed: np.ndarray | None,
    fit_rows: np.ndarray,
    penalty: float,
) -> np.ndarray | None:
    """Fit q on the observed training cells and predict every test task by organization.

    Mirrors `routing._model_scores`, with two additions the pre-registration requires: ``observed``
    restricts which (organization, task) cells enter the fit, and ``fit_rows`` restricts which
    organizations are fitted on at all, which is what an agent or organization holdout means.
    """
    from sklearn.linear_model import LogisticRegression

    pairs = _pair_matrix(task_features[train], organization_features)
    labels = grid.correct[:, train].T.reshape(-1)
    # `_pair_matrix` stacks task-major: row (i * n_org + j) is train task i with organization j.
    keep = np.zeros(len(labels), dtype=bool)
    for position, column in enumerate(train):
        base = position * grid.n_org
        for row in fit_rows:
            if observed is None or observed[row, column]:
                keep[base + row] = True
    if keep.sum() < 8 or len(set(labels[keep].tolist())) < 2:
        return None

    model = LogisticRegression(C=penalty, max_iter=3000)
    model.fit(pairs[keep], labels[keep])
    predicted = model.predict_proba(
        _pair_matrix(task_features[test], organization_features)
    )[:, 1]
    return predicted.reshape(len(test), grid.n_org)


@dataclass
class Arm:
    """One policy's accuracy on the test tasks, and how it compares to the frozen baseline."""

    name: str
    accuracy: float
    gain_pp: float = float("nan")
    n_distinct: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"accuracy": self.accuracy, "gain_pp": self.gain_pp, "n_distinct": self.n_distinct}


def evaluate(
    grid: Grid,
    train: np.ndarray,
    test: np.ndarray,
    *,
    observed: np.ndarray | None = None,
    fit_rows: np.ndarray | None = None,
    candidate_rows: np.ndarray | None = None,
    baseline_rows: np.ndarray | None = None,
    n_components: int = 16,
    penalty: float = 0.1,
    seed: int = 20260813,
) -> dict[str, Arm]:
    """The baseline ladder on one split, with every restriction the four RQs need.

    ``fit_rows`` organizations the model may learn from; ``candidate_rows`` those it may choose at
    test time; ``baseline_rows`` those the frozen fixed-best may choose. They differ exactly when
    something is held out: under organization holdout the model fits and the baseline chooses on the
    seen 60%, while the router chooses from all of them.
    """
    rng = np.random.default_rng(seed)
    fit_rows = np.arange(grid.n_org) if fit_rows is None else np.asarray(fit_rows)
    candidate_rows = np.arange(grid.n_org) if candidate_rows is None else np.asarray(candidate_rows)
    baseline_rows = fit_rows if baseline_rows is None else np.asarray(baseline_rows)

    train_accuracy = np.full(grid.n_org, -np.inf)
    for row in baseline_rows:
        columns = train if observed is None else train[observed[row, train]]
        if columns.size:
            train_accuracy[row] = float(grid.correct[row, columns].mean())
    if not np.isfinite(train_accuracy).any():
        return {}

    usable = [int(r) for r in baseline_rows if np.isfinite(train_accuracy[r])]
    fixed = _best_row(train_accuracy, usable)
    baseline = grid.correct[fixed, test]
    arms = {"fixed_best": Arm("fixed_best", float(baseline.mean()), 0.0, 1)}

    def record(name: str, chosen: np.ndarray) -> None:
        outcome = grid.correct[chosen, test]
        arms[name] = Arm(
            name,
            float(outcome.mean()),
            100.0 * float((outcome - baseline).mean()),
            int(len(set(chosen.tolist()))),
        )

    organization_features = _organization_features(grid, train, observed)
    task_features = _task_features(grid.embeddings, train, n_components=n_components)

    scores = _fit_scores(
        grid, task_features, organization_features, train, test,
        observed=observed, fit_rows=fit_rows, penalty=penalty,
    )
    if scores is not None:
        record("q_theta", candidate_rows[scores[:, candidate_rows].argmax(axis=1)])
        # The model's own task-*independent* choice: one organization, the one it ranks highest on
        # average. Under a holdout the router may choose from organizations the frozen baseline has
        # never seen, so a gain over that baseline confounds task-conditioning with a larger
        # feasible set — the same unmatched-comparison defect Lemma 2 identifies in a lambda sweep.
        # `q_theta` minus `q_theta_fixed` is the part that is actually about conditioning on x.
        marginal = int(candidate_rows[scores[:, candidate_rows].mean(axis=0).argmax()])
        record("q_theta_fixed", np.full(len(test), marginal))

    # The control that D-029 and D-030 died for the lack of: same model, same choice set, the
    # task-to-embedding association destroyed. A gain the twin also achieves is not a gain.
    shuffled = grid.embeddings.copy()
    rng.shuffle(shuffled)
    control = _fit_scores(
        grid, _task_features(shuffled, train, n_components=n_components), organization_features,
        train, test, observed=observed, fit_rows=fit_rows, penalty=penalty,
    )
    if control is not None:
        record("q_theta_shuffled", candidate_rows[control[:, candidate_rows].argmax(axis=1)])

    record("oracle", candidate_rows[grid.correct[np.ix_(candidate_rows, test)].argmax(axis=0)])
    return arms


# ---- splits ----------------------------------------------------------------------------------


def stratified_resplit(
    domain_index: np.ndarray, fraction: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """A calibration/test partition keeping each domain's share, as `routing_over_splits` does."""
    left: list[int] = []
    right: list[int] = []
    for domain in np.unique(domain_index):
        columns = np.flatnonzero(domain_index == domain)
        rng.shuffle(columns)
        cut = max(2, int(round(fraction * len(columns))))
        left.extend(columns[:cut].tolist())
        right.extend(columns[cut:].tolist())
    return np.array(sorted(left)), np.array(sorted(right))


def summarise(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if not array.size:
        return {"mean": float("nan"), "sd": float("nan"), "frac_positive": float("nan"), "n": 0}
    return {
        "mean": float(array.mean()),
        "sd": float(array.std(ddof=1)) if array.size > 1 else 0.0,
        "q05": float(np.quantile(array, 0.05)),
        "q95": float(np.quantile(array, 0.95)),
        "frac_positive": float((array > 0).mean()),
        "n": int(array.size),
    }


# ---- RQ3: supervision efficiency -------------------------------------------------------------


def supervision_efficiency(
    grid: Grid,
    *,
    fractions: Sequence[float] = (0.05, 0.10, 0.20, 0.50, 1.00),
    n_repeats: int = 12,
    calibration_fraction: float = 0.5,
    seed: int = 20260813,
) -> dict[str, Any]:
    """At a matched budget of observed cells, does the dense design beat an execution log?

    The two arms spend the same number of observations. ``dense`` sees every organization on a few
    tasks; ``observational`` sees one uniformly-random organization on many. The second is the shape
    of the logs a deployed router would actually have, which is why it is the right comparator for a
    claim that dense counterfactual supervision is worth its cost.
    """
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {"fractions": list(fractions), "n_repeats": n_repeats, "budgets": {}}

    for fraction in fractions:
        dense_gain: list[float] = []
        sparse_gain: list[float] = []
        dense_accuracy: list[float] = []
        sparse_accuracy: list[float] = []
        dense_gain_unstarved: list[float] = []
        starved_baseline: list[float] = []
        full_baseline: list[float] = []

        for repeat in range(n_repeats):
            train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
            budget = max(grid.n_org, int(round(fraction * grid.n_org * len(train))))
            # The comparator a deployer actually has: you always know your organizations' overall
            # accuracy, even when you have not observed every one of them on every task. Gain
            # against the *starved* baseline is the pre-registered quantity, and at small budgets it
            # measures how badly that baseline is estimated rather than how well the router routes.
            unstarved_row = int(np.argmax(grid.correct[:, train].mean(axis=1)))
            unstarved = float(grid.correct[unstarved_row, test].mean())

            dense = np.zeros((grid.n_org, grid.n_task), dtype=bool)
            n_dense_tasks = int(np.clip(budget // grid.n_org, 2, len(train)))
            dense[:, rng.choice(train, size=n_dense_tasks, replace=False)] = True

            sparse = np.zeros((grid.n_org, grid.n_task), dtype=bool)
            n_sparse = int(min(budget, len(train)))
            for column in rng.choice(train, size=n_sparse, replace=False):
                # One organization per task: an ordinary log, not a counterfactual grid.
                sparse[rng.integers(0, grid.n_org), column] = True

            for mask, gains, accuracies in (
                (dense, dense_gain, dense_accuracy),
                (sparse, sparse_gain, sparse_accuracy),
            ):
                arms = evaluate(grid, train, test, observed=mask, seed=seed + repeat)
                model = arms.get("q_theta")
                if model is not None:
                    gains.append(model.gain_pp)
                    accuracies.append(model.accuracy)
                    if mask is dense:
                        dense_gain_unstarved.append(100.0 * (model.accuracy - unstarved))
                        starved_baseline.append(arms["fixed_best"].accuracy)
                        full_baseline.append(unstarved)

        out["budgets"][f"{fraction:g}"] = {
            "observed_fraction": fraction,
            "dense_gain_over_fixed_best": summarise(dense_gain),
            "observational_gain_over_fixed_best": summarise(sparse_gain),
            "dense_gain_over_unstarved_baseline": summarise(dense_gain_unstarved),
            "starved_baseline_accuracy": summarise(starved_baseline),
            "unstarved_baseline_accuracy": summarise(full_baseline),
            "dense_minus_observational_pp": 100.0
            * float(np.mean(dense_accuracy) - np.mean(sparse_accuracy))
            if dense_accuracy and sparse_accuracy
            else float("nan"),
        }
    return out


# ---- RQ4: generalization ---------------------------------------------------------------------


def generalization(
    grid: Grid,
    *,
    lodo: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
    n_repeats: int = 12,
    calibration_fraction: float = 0.5,
    seed: int = 20260813,
) -> dict[str, Any]:
    """Domain, agent and organization holdout, each against a baseline blinded the same way."""
    rng = np.random.default_rng(seed)
    agents = sorted({a for coalition in grid.members for a in coalition})
    out: dict[str, Any] = {}

    def harvest(arms, gains, controls, conditioning):
        """Raw gain over the frozen baseline, the shuffled twin, and the conditioning-only gain."""
        if "q_theta" in arms:
            gains.append(arms["q_theta"].gain_pp)
            if "q_theta_fixed" in arms:
                conditioning.append(arms["q_theta"].gain_pp - arms["q_theta_fixed"].gain_pp)
        if "q_theta_shuffled" in arms:
            controls.append(arms["q_theta_shuffled"].gain_pp)

    # -- IID reference, so the three holdouts are read against the easy case rather than zero.
    iid: list[float] = []
    iid_control: list[float] = []
    iid_conditioning: list[float] = []
    for repeat in range(n_repeats):
        train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
        harvest(evaluate(grid, train, test, seed=seed + repeat), iid, iid_control, iid_conditioning)
    out["iid"] = {
        "gain": summarise(iid),
        "shuffled": summarise(iid_control),
        "conditioning_gain": summarise(iid_conditioning),
    }

    # -- domain holdout, from the lodo splits already built into every manifest.
    if lodo:
        gains: list[float] = []
        controls: list[float] = []
        conditioning: list[float] = []
        per_domain: dict[str, float] = {}
        for domain, (train, test) in sorted(lodo.items()):
            if len(train) < 8 or len(test) < 8:
                continue
            arms = evaluate(grid, train, test, seed=seed)
            harvest(arms, gains, controls, conditioning)
            if "q_theta" in arms:
                per_domain[domain] = arms["q_theta"].gain_pp
        out["domain_holdout"] = {
            "gain": summarise(gains),
            "shuffled": summarise(controls),
            "conditioning_gain": summarise(conditioning),
            "per_domain": per_domain,
        }

    # -- agent holdout: a new member joins the pool and the model has never seen its organizations.
    gains, controls, conditioning = [], [], []
    for agent in agents:
        seen = np.array([r for r, c in enumerate(grid.members) if agent not in c])
        if seen.size < 4:
            continue
        for repeat in range(max(2, n_repeats // len(agents))):
            train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
            harvest(
                evaluate(
                    grid, train, test, fit_rows=seen, baseline_rows=seen,
                    candidate_rows=np.arange(grid.n_org), seed=seed + repeat,
                ),
                gains, controls, conditioning,
            )
    out["agent_holdout"] = {
        "gain": summarise(gains),
        "shuffled": summarise(controls),
        "conditioning_gain": summarise(conditioning),
    }

    # -- organization holdout: can the model profitably reach into arrangements it never fitted on?
    gains, controls, conditioning = [], [], []
    for repeat in range(n_repeats):
        train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
        seen = np.sort(rng.permutation(grid.n_org)[: max(4, int(0.6 * grid.n_org))])
        harvest(
            evaluate(
                grid, train, test, fit_rows=seen, baseline_rows=seen,
                candidate_rows=np.arange(grid.n_org), seed=seed + repeat,
            ),
            gains, controls, conditioning,
        )
    out["organization_holdout"] = {
        "gain": summarise(gains),
        "shuffled": summarise(controls),
        "conditioning_gain": summarise(conditioning),
    }
    return out


# ---- RQ5: when not to collaborate ------------------------------------------------------------


def solo_or_collaborate(
    grid: Grid,
    *,
    n_repeats: int = 40,
    calibration_fraction: float = 0.5,
    n_components: int = 16,
    penalty: float = 0.1,
    seed: int = 20260813,
) -> dict[str, Any]:
    """A narrower decision than "which organization": for this task, one agent or a team?

    The two candidates are frozen on calibration — the best singleton and the best multi-member
    organization — so the only thing being learned is *which of the two* to use per task. Scored
    against always-solo, always-collaborate, and the per-task oracle over the pair.
    """
    rng = np.random.default_rng(seed)
    solo_rows = np.array([r for r, c in enumerate(grid.members) if len(c) == 1])
    team_rows = np.array([r for r, c in enumerate(grid.members) if len(c) > 1])
    if not solo_rows.size or not team_rows.size:
        return {"note": "grid has no solo or no multi-member organizations"}

    gains: list[float] = []
    controls: list[float] = []
    oracle_gains: list[float] = []
    solo_share: list[float] = []
    best_fixed_is_solo: list[float] = []

    for _repeat in range(n_repeats):
        train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
        train_accuracy = grid.correct[:, train].mean(axis=1)
        best_solo = int(solo_rows[np.argmax(train_accuracy[solo_rows])])
        best_team = int(team_rows[np.argmax(train_accuracy[team_rows])])
        pair = np.array([best_solo, best_team])

        solo_outcome = grid.correct[best_solo, test]
        team_outcome = grid.correct[best_team, test]
        better = solo_outcome if solo_outcome.mean() >= team_outcome.mean() else team_outcome
        best_fixed_is_solo.append(float(solo_outcome.mean() >= team_outcome.mean()))

        organization_features = _organization_features(grid, train)
        task_features = _task_features(grid.embeddings, train, n_components=n_components)
        scores = _fit_scores(
            grid, task_features, organization_features, train, test,
            observed=None, fit_rows=np.arange(grid.n_org), penalty=penalty,
        )
        if scores is not None:
            chosen = pair[scores[:, pair].argmax(axis=1)]
            outcome = grid.correct[chosen, test]
            gains.append(100.0 * float((outcome - better).mean()))
            solo_share.append(float(np.mean(chosen == best_solo)))

        shuffled = grid.embeddings.copy()
        rng.shuffle(shuffled)
        control = _fit_scores(
            grid, _task_features(shuffled, train, n_components=n_components), organization_features,
            train, test, observed=None, fit_rows=np.arange(grid.n_org), penalty=penalty,
        )
        if control is not None:
            chosen = pair[control[:, pair].argmax(axis=1)]
            controls.append(100.0 * float((grid.correct[chosen, test] - better).mean()))

        oracle = np.maximum(solo_outcome, team_outcome)
        oracle_gains.append(100.0 * float((oracle - better).mean()))

    return {
        "gain_over_better_fixed_policy": summarise(gains),
        "shuffled_control": summarise(controls),
        "oracle_over_the_pair": summarise(oracle_gains),
        "frac_choices_solo": summarise(solo_share),
        "frac_splits_where_solo_is_the_better_fixed_policy": summarise(best_fixed_is_solo),
    }


# ---- RQ2': routing when interaction protocols are in the choice set ---------------------------


def routing_over_family(
    grid: Grid,
    *,
    n_repeats: int = 60,
    calibration_fraction: float = 0.5,
    restrict_rows: np.ndarray | None = None,
    seed: int = 20260813,
) -> dict[str, Any]:
    """The standard ladder over resplits, optionally restricted to a sub-family of organizations.

    ``restrict_rows`` is what makes the RQ2' comparison controlled: run once over all 35
    organizations and once over the 30 aggregation-only ones **on the same tasks and the same
    splits**, so the difference isolates the protocol axis rather than the task subset.
    """
    rng = np.random.default_rng(seed)
    rows = np.arange(grid.n_org) if restrict_rows is None else np.asarray(restrict_rows)
    collected: dict[str, list[float]] = {}
    accuracies: dict[str, list[float]] = {}

    for repeat in range(n_repeats):
        train, test = stratified_resplit(grid.domain_index, calibration_fraction, rng)
        arms = evaluate(
            grid, train, test, fit_rows=rows, candidate_rows=rows, baseline_rows=rows,
            seed=seed + repeat,
        )
        for name, arm in arms.items():
            collected.setdefault(name, []).append(arm.gain_pp)
            accuracies.setdefault(name, []).append(arm.accuracy)

    return {
        "n_organizations": int(len(rows)),
        "n_tasks": grid.n_task,
        "n_repeats": n_repeats,
        "gain_over_fixed_best": {n: summarise(v) for n, v in sorted(collected.items())},
        "accuracy": {n: summarise(v) for n, v in sorted(accuracies.items())},
    }
