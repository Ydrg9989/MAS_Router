"""Can a learned model of q(x, S, p) route better than refusing to route?

The delegation direction has so far been measured negatively: `metrics.stability` asks whether
per-group winners survive a resplit, and on homogeneous suites they do not (D-029). That is a
statement about whether signal *exists*, not about whether anything can *use* it. This module is
the positive half. It fits

    q(x, S, p) = P(correct | task x, coalition S, protocol p)

and then routes each test task to the organization the model believes is best, scoring the choice
against the outcome that was actually banked for that organization on that task. Because the
episode grid is dense - every coalition and protocol ran on every task - the counterfactual for
any routing decision is observed rather than estimated, which is what makes this evaluable at all.

Three leakage traps sit in the obvious implementation, and all three have already fired in this
project once:

``the task representation``
    `delegation.organizational_space` builds a task's coordinates out of how every configuration
    performed on *that task*, then routes by nearest neighbour in that space. A router given the
    answer key scores near-oracle and means nothing (D-030). Here the task side is a frozen text
    embedding of the prompt and nothing else, and the projection that reduces it is fit on
    training prompts alone.

``the baseline``
    `utility.fixed_best_selection` picks its single configuration by maximising utility on the set
    it is scored on. Handed the test set, the "baseline any router must beat" is itself an oracle
    over configurations, which understates the router by exactly the amount the baseline cheats.
    Every baseline here is fit on training tasks and frozen before it sees a test task.

``the feature side``
    Agent competence features are real predictors, and computing them over all tasks leaks test
    outcomes into the organization representation. They are computed from singleton coalitions on
    training tasks only.

A gain over a properly frozen fixed-best baseline is still not evidence on its own, because the
argmax of a noisy model over thirty organizations drifts away from the best fixed choice and can
win by luck on a small test set. So the report carries a control: the same pipeline, refit with
task embeddings shuffled between tasks. That destroys every task-organization association while
preserving the marginal quality of each organization and the size of the choice set. A real
router beats fixed-best and its shuffled twin does not.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from ..records.schema import EpisodeRecord
from .utility import Configuration, configuration_stats

if TYPE_CHECKING:
    from .delegation import TaskSpace

# The whole-pool majority vote is the one organizational fact that reproduced on every suite and
# pool measured so far (D-029), so it is carried as a named baseline rather than left to be
# rediscovered by fixed-best. If routing cannot beat "always run everyone and vote", it has not
# earned the machinery.
WHOLE_POOL_PROTOCOL = "majority_vote"


@dataclass
class RouterResult:
    """What one routing rule chose on the test tasks, and what it got for it."""

    name: str
    accuracy: float
    utility: float
    n_distinct_organizations: int
    mean_cost_usd: float
    gain_over_fixed_best: float = float("nan")
    """Percentage points of accuracy, positive meaning better than the frozen fixed-best rule."""
    ci_low: float = float("nan")
    ci_high: float = float("nan")
    p_value: float = float("nan")
    n_discordant: int = 0
    """Test tasks where this rule and fixed-best disagreed on the outcome, not just the choice."""
    chosen: dict[str, str] = field(default_factory=dict)
    """Test task to organization label. Kept so the choices can be read by domain afterwards."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "accuracy": self.accuracy,
            "utility": self.utility,
            "n_distinct_organizations": self.n_distinct_organizations,
            "mean_cost_usd": self.mean_cost_usd,
            "gain_over_fixed_best": self.gain_over_fixed_best,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "p_value": self.p_value,
            "n_discordant": self.n_discordant,
            "chosen": self.chosen,
        }


@dataclass
class RoutingReport:
    """The baseline ladder on one pool and one suite."""

    n_train_tasks: int = 0
    n_test_tasks: int = 0
    n_organizations: int = 0
    embedding_method: str = ""
    embedding_fallback: bool = False
    fixed_best_train_accuracy: float = float("nan")
    results: dict[str, RouterResult] = field(default_factory=dict)

    @property
    def selection_gap(self) -> float:
        """Points the fixed-best organization loses between calibration and test.

        The winner's curse, measured. If this exceeds the oracle headroom then choosing *one*
        organization is already harder than the problem routing is trying to solve, and no
        comparison against a fixed baseline is stable.
        """
        fixed = self.results.get("fixed_best")
        if fixed is None or not np.isfinite(self.fixed_best_train_accuracy):
            return float("nan")
        return 100.0 * (self.fixed_best_train_accuracy - fixed.accuracy)

    @property
    def model(self) -> RouterResult | None:
        return self.results.get("q_theta")

    @property
    def control(self) -> RouterResult | None:
        return self.results.get("q_theta_shuffled")

    @property
    def oracle_headroom(self) -> float:
        """Accuracy points between the frozen fixed-best rule and the per-task oracle.

        The entire prize. A router's gain is only interpretable as a fraction of this.
        """
        oracle, fixed = self.results.get("oracle"), self.results.get("fixed_best")
        if oracle is None or fixed is None:
            return float("nan")
        return 100.0 * (oracle.accuracy - fixed.accuracy)

    @property
    def captured_fraction(self) -> float:
        """Share of the available headroom the model actually captured."""
        model = self.model
        headroom = self.oracle_headroom
        if model is None or not np.isfinite(headroom) or headroom <= 0:
            return float("nan")
        return model.gain_over_fixed_best / headroom

    @property
    def verdict(self) -> str:
        model, control = self.model, self.control
        if model is None:
            return "NO RESULT - the model did not fit"
        if not np.isfinite(self.oracle_headroom) or self.oracle_headroom <= 0:
            return "NO HEADROOM - one fixed organization is already per-task optimal"
        if model.p_value >= 0.05 or model.gain_over_fixed_best <= 0:
            return (
                f"NO GAIN - routing scores {model.gain_over_fixed_best:+.1f} points against a "
                f"frozen fixed-best baseline (p={model.p_value:.3f}) with "
                f"{self.oracle_headroom:.1f} points of headroom available"
            )
        if control is not None and control.gain_over_fixed_best >= model.gain_over_fixed_best:
            return (
                f"NOT REAL - routing gains {model.gain_over_fixed_best:+.1f} points but the "
                f"shuffled-embedding control gains {control.gain_over_fixed_best:+.1f}, so the "
                "gain does not come from the task representation"
            )
        return (
            f"GAIN - routing scores {model.gain_over_fixed_best:+.1f} points over frozen "
            f"fixed-best (p={model.p_value:.3f}), capturing {self.captured_fraction:.0%} of the "
            f"{self.oracle_headroom:.1f} points of oracle headroom, against "
            f"{control.gain_over_fixed_best:+.1f} for the shuffled control"
            if control
            else f"GAIN - routing scores {model.gain_over_fixed_best:+.1f} points"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_train_tasks": self.n_train_tasks,
            "n_test_tasks": self.n_test_tasks,
            "n_organizations": self.n_organizations,
            "embedding_method": self.embedding_method,
            "embedding_fallback": self.embedding_fallback,
            "oracle_headroom": self.oracle_headroom,
            "selection_gap": self.selection_gap,
            "captured_fraction": self.captured_fraction,
            "verdict": self.verdict,
            "results": {name: r.to_dict() for name, r in sorted(self.results.items())},
        }


# ---- outcome table -------------------------------------------------------------------------


@dataclass
class _Grid:
    """The dense organization x task outcome table these routers choose within."""

    organizations: list[Configuration]
    tasks: list[str]
    correct: np.ndarray  # (n_org, n_task) float 0/1
    cost: np.ndarray
    latency: np.ndarray

    def index_of(self, tasks: Sequence[str]) -> list[int]:
        position = {t: i for i, t in enumerate(self.tasks)}
        return [position[t] for t in tasks if t in position]


def _grid(
    episodes: Sequence[EpisodeRecord], *, only_protocols: Sequence[str] | None
) -> _Grid | None:
    """Restrict to the tasks every organization ran, so the argmax is a fair comparison."""
    keep = set(only_protocols) if only_protocols else None
    stats = configuration_stats(episodes)
    if keep is not None:
        stats = {c: e for c, e in stats.items() if c.protocol_id in keep}
    if not stats:
        return None

    shared = set.intersection(*[set(e.per_task_correct) for e in stats.values()])
    if not shared:
        return None

    organizations = sorted(stats, key=lambda c: c.label)
    tasks = sorted(shared)
    shape = (len(organizations), len(tasks))
    correct = np.zeros(shape)
    cost = np.zeros(shape)
    latency = np.zeros(shape)
    for row, configuration in enumerate(organizations):
        entry = stats[configuration]
        for column, task in enumerate(tasks):
            correct[row, column] = float(entry.per_task_correct[task])
            cost[row, column] = entry.per_task_cost.get(task, 0.0)
            latency[row, column] = entry.per_task_latency.get(task, 0.0)
    return _Grid(organizations=organizations, tasks=tasks, correct=correct, cost=cost,
                 latency=latency)


# ---- features ------------------------------------------------------------------------------


def _organization_features(grid: _Grid, train: Sequence[int]) -> np.ndarray:
    """Protocol, membership, size, and member competence measured on training tasks only."""
    protocols = sorted({c.protocol_id for c in grid.organizations})
    agents = sorted({a for c in grid.organizations for a in c.coalition})

    singleton_rows: dict[int, list[int]] = defaultdict(list)
    for row, configuration in enumerate(grid.organizations):
        if len(configuration.coalition) == 1:
            singleton_rows[configuration.coalition[0]].append(row)
    competence = {
        agent: float(np.mean(grid.correct[np.ix_(rows, train)])) if train else 0.5
        for agent, rows in singleton_rows.items()
    }

    features = []
    for configuration in grid.organizations:
        protocol_hot = [float(configuration.protocol_id == p) for p in protocols]
        member_hot = [float(a in configuration.coalition) for a in agents]
        scores = [competence.get(a, 0.5) for a in configuration.coalition]
        features.append(
            [
                *protocol_hot,
                *member_hot,
                len(configuration.coalition) / max(1, len(agents)),
                float(np.mean(scores)),
                float(np.max(scores)),
                # Spread stands in for within-coalition heterogeneity: a mixed-strength team and
                # a uniformly mid team share a mean but behave differently under aggregation.
                float(np.max(scores) - np.min(scores)),
            ]
        )
    matrix = np.asarray(features, dtype=float)
    spread = matrix.std(axis=0, keepdims=True)
    return matrix / np.where(spread < 1e-12, 1.0, spread)


def _task_features(
    embeddings: np.ndarray, train: Sequence[int], *, n_components: int
) -> np.ndarray:
    """Project prompt embeddings down, fitting the projection on training tasks alone."""
    from sklearn.decomposition import PCA

    n_components = int(min(n_components, len(train) - 1, embeddings.shape[1]))
    if n_components < 1:
        return np.zeros((embeddings.shape[0], 1))
    pca = PCA(n_components=n_components, random_state=0)
    pca.fit(embeddings[train])
    reduced = pca.transform(embeddings)
    spread = reduced[train].std(axis=0, keepdims=True)
    return (reduced - reduced[train].mean(axis=0, keepdims=True)) / np.where(
        spread < 1e-12, 1.0, spread
    )


def _pair_matrix(task: np.ndarray, organization: np.ndarray) -> np.ndarray:
    """Main effects plus their outer product, the bilinear term the routing signal lives in."""
    n_task, d = task.shape
    n_org, m = organization.shape
    z = np.repeat(task, n_org, axis=0)
    h = np.tile(organization, (n_task, 1))
    interaction = (z[:, :, None] * h[:, None, :]).reshape(n_task * n_org, d * m)
    return np.hstack([z, h, interaction])


# ---- routers -------------------------------------------------------------------------------


def _outcome_of(grid: _Grid, columns: Sequence[int], rows: np.ndarray) -> tuple[np.ndarray, ...]:
    """The banked correctness, cost and latency of the chosen organization on each test task."""
    picked = np.asarray(rows)
    index = np.asarray(columns)
    return grid.correct[picked, index], grid.cost[picked, index], grid.latency[picked, index]


def _model_scores(
    task_features: np.ndarray,
    organization_features: np.ndarray,
    grid: _Grid,
    train: Sequence[int],
    test: Sequence[int],
    *,
    penalty: float,
) -> np.ndarray | None:
    """Fit q on training pairs, return predicted success for every test task by organization."""
    from sklearn.linear_model import LogisticRegression

    x_train = _pair_matrix(task_features[train], organization_features)
    y_train = grid.correct[:, train].T.reshape(-1)
    if len(set(y_train.tolist())) < 2:
        return None

    model = LogisticRegression(C=penalty, max_iter=3000)
    model.fit(x_train, y_train)
    x_test = _pair_matrix(task_features[test], organization_features)
    return model.predict_proba(x_test)[:, 1].reshape(len(test), len(grid.organizations))


def _knn_scores(
    embeddings: np.ndarray, grid: _Grid, train: Sequence[int], test: Sequence[int], *, k: int
) -> np.ndarray:
    """Mean training-task accuracy of each organization over a test task's nearest neighbours."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    unit = embeddings / np.where(norms < 1e-12, 1.0, norms)
    similarity = unit[test] @ unit[train].T
    k = int(min(k, len(train)))
    scores = []
    for row in similarity:
        neighbours = [train[j] for j in np.argsort(-row)[:k]]
        scores.append(grid.correct[:, neighbours].mean(axis=1))
    return np.vstack(scores)


def _best_row(values: np.ndarray, candidates: Sequence[int]) -> int:
    """Highest-scoring row among ``candidates``; ties go to the lowest index.

    Organizations are held in label order, so the tie-break is deterministic and independent of
    the data - which matters because most ties here are between organizations that behaved
    identically on the training tasks.
    """
    subset = np.asarray(candidates)
    return int(subset[int(np.argmax(values[subset]))])


def _one_standard_error_row(grid: _Grid, values: np.ndarray, n_train: int) -> int:
    """The simplest organization statistically indistinguishable from the training winner.

    Taking the argmax over thirty organizations on a hundred-odd calibration tasks is a
    winner's-curse machine: the selected organization's training accuracy is biased upward by
    roughly the selection noise, which at these sample sizes is comparable to the entire oracle
    headroom. The standard remedy is to treat everything within one standard error of the best as
    tied and break the tie on simplicity - here the smallest coalition, which is also the cheapest.
    """
    best = float(values.max())
    accuracy = float(np.clip(best, 0.0, 1.0))
    standard_error = float(np.sqrt(max(accuracy * (1.0 - accuracy), 1e-6) / max(n_train, 1)))
    tied = [i for i in range(len(grid.organizations)) if values[i] >= best - standard_error]
    return min(tied, key=lambda i: (len(grid.organizations[i].coalition),
                                    grid.organizations[i].label))


# ---- entry point ---------------------------------------------------------------------------


def evaluate_routing(
    episodes: Sequence[EpisodeRecord],
    *,
    prompts: dict[str, str] | None = None,
    task_space: "TaskSpace | None" = None,
    train_task_ids: Sequence[str],
    test_task_ids: Sequence[str],
    only_protocols: Sequence[str] | None = None,
    n_components: int = 16,
    k_neighbours: int = 8,
    penalty: float = 0.1,
    lambda_per_usd: float = 0.0,
    mu_per_second: float = 0.0,
    n_bootstrap: int = 2000,
    seed: int = 20260810,
) -> RoutingReport:
    """Fit q(x, S, p) on training tasks and score its routing against a frozen baseline ladder.

    Supply either ``prompts`` (embedded here) or a prebuilt ``task_space``; the latter exists so a
    caller sweeping several pools over one suite embeds the prompts once, and so tests can plant a
    known geometry instead of depending on a downloaded encoder.

    ``lambda_per_usd`` and ``mu_per_second`` default to zero so the headline number is accuracy,
    matching what the model predicts. Setting them makes every rule choose - and be scored on -
    cost-adjusted utility instead, using training-set cost estimates to choose and realised test
    costs to score.
    """
    from .delegation import TaskSpace, semantic_space

    if (prompts is None) == (task_space is None):
        raise ValueError("supply exactly one of `prompts` or `task_space`")

    rng = np.random.default_rng(seed)
    report = RoutingReport()

    grid = _grid(list(episodes), only_protocols=only_protocols)
    if grid is None:
        return report

    if task_space is None:
        space = semantic_space(grid.tasks, [prompts.get(t, t) for t in grid.tasks])
    else:
        # Reorder to the grid's task order, since every matrix below is indexed by it.
        index = {t: i for i, t in enumerate(task_space.task_ids)}
        missing = [t for t in grid.tasks if t not in index]
        if missing:
            raise ValueError(f"task_space is missing {len(missing)} of the grid's tasks")
        space = TaskSpace(
            name=task_space.name,
            task_ids=list(grid.tasks),
            features=task_space.features[[index[t] for t in grid.tasks]],
            method=task_space.method,
            fallback_used=task_space.fallback_used,
        )

    train = grid.index_of(sorted(set(train_task_ids)))
    test = grid.index_of(sorted(set(test_task_ids)))
    if len(train) < 4 or len(test) < 4:
        return report

    report.n_train_tasks = len(train)
    report.n_test_tasks = len(test)
    report.n_organizations = len(grid.organizations)
    report.embedding_method = space.method
    report.embedding_fallback = space.fallback_used

    organization_features = _organization_features(grid, train)

    # Choice time may only use costs estimated on training tasks; scoring uses realised ones.
    estimated_penalty = (
        lambda_per_usd * grid.cost[:, train].mean(axis=1)
        + mu_per_second * grid.latency[:, train].mean(axis=1)
    )

    def choose(scores: np.ndarray) -> np.ndarray:
        """Argmax over organizations of a (n_test, n_org) score matrix, net of expected cost."""
        return np.asarray((scores - estimated_penalty[None, :]).argmax(axis=1))

    choices: dict[str, np.ndarray] = {}

    train_utility = grid.correct[:, train].mean(axis=1) - estimated_penalty
    fixed = _best_row(train_utility, list(range(len(grid.organizations))))
    choices["fixed_best"] = np.full(len(test), fixed)
    report.fixed_best_train_accuracy = float(grid.correct[fixed, train].mean())

    choices["fixed_best_1se"] = np.full(
        len(test), _one_standard_error_row(grid, train_utility, len(train))
    )

    singletons = [i for i, c in enumerate(grid.organizations) if len(c.coalition) == 1]
    if singletons:
        choices["fixed_best_single_agent"] = np.full(
            len(test), _best_row(train_utility, singletons)
        )

    pool_size = len({a for c in grid.organizations for a in c.coalition})
    whole_pool = [
        i
        for i, c in enumerate(grid.organizations)
        if c.protocol_id == WHOLE_POOL_PROTOCOL and len(c.coalition) == pool_size
    ]
    if whole_pool:
        choices["whole_pool_majority"] = np.full(len(test), whole_pool[0])

    choices["semantic_knn"] = choose(_knn_scores(space.features, grid, train, test, k=k_neighbours))

    # The oracle is the one rule allowed realised outcomes: it exists to bound the prize.
    realised = (
        grid.correct[:, test]
        - lambda_per_usd * grid.cost[:, test]
        - mu_per_second * grid.latency[:, test]
    )
    choices["oracle"] = np.asarray(realised.argmax(axis=0))

    task_features = _task_features(space.features, train, n_components=n_components)
    scores = _model_scores(
        task_features, organization_features, grid, train, test, penalty=penalty
    )
    if scores is not None:
        choices["q_theta"] = choose(scores)

    shuffled = space.features.copy()
    rng.shuffle(shuffled)
    control_scores = _model_scores(
        _task_features(shuffled, train, n_components=n_components),
        organization_features,
        grid,
        train,
        test,
        penalty=penalty,
    )
    if control_scores is not None:
        choices["q_theta_shuffled"] = choose(control_scores)

    baseline_correct, _, _ = _outcome_of(grid, test, choices["fixed_best"])
    for name, rows in choices.items():
        correct, cost, latency = _outcome_of(grid, test, rows)
        utility = correct - lambda_per_usd * cost - mu_per_second * latency
        result = RouterResult(
            name=name,
            accuracy=float(correct.mean()),
            utility=float(utility.mean()),
            n_distinct_organizations=int(len(set(rows.tolist()))),
            mean_cost_usd=float(cost.mean()),
            chosen={
                grid.tasks[column]: grid.organizations[row].label
                for column, row in zip(test, rows.tolist(), strict=True)
            },
        )
        difference = correct - baseline_correct
        result.gain_over_fixed_best = 100.0 * float(difference.mean())
        result.n_discordant = int(np.count_nonzero(difference))
        if name != "fixed_best" and n_bootstrap:
            draws = rng.integers(0, len(difference), size=(n_bootstrap, len(difference)))
            samples = difference[draws].mean(axis=1)
            result.ci_low = 100.0 * float(np.quantile(samples, 0.025))
            result.ci_high = 100.0 * float(np.quantile(samples, 0.975))
            # One-tailed: the claim is that routing helps, so the null is that it does not.
            result.p_value = float(np.mean(samples <= 0.0))
        report.results[name] = result

    return report


def headroom_against_no_interaction(
    episodes: Sequence[EpisodeRecord],
    *,
    train_task_ids: Sequence[str],
    test_task_ids: Sequence[str],
    only_protocols: Sequence[str] | None = None,
    n_simulations: int = 200,
    seed: int = 20260810,
) -> dict[str, Any]:
    """How much of the oracle headroom survives when there is provably nothing to route to?

    Every headroom figure in this project is the per-task maximum over organizations minus one
    fixed organization, and that is not by itself evidence of an opportunity. Thirty organizations
    that are each about 85% accurate and fail semi-independently will, on most tasks, contain at
    least one that happens to be right, so the maximum runs far above any of them even when no
    organization is genuinely better suited to any task. Read naively, a pure-noise ensemble looks
    like a large routing prize.

    The null here removes exactly the thing routing needs and keeps everything else. An additive
    logistic model of outcome on organization and task - main effects only, no interaction - is fit
    to the observed table, then outcome tables are simulated from it. Each organization keeps its
    overall accuracy and each task keeps its difficulty; what is destroyed is any organization-by-
    task interaction, which is the entire content of "different organizations suit different tasks".

    The reportable quantity is the excess of observed headroom over this null. If it is near zero,
    the prize was an artifact of maximising over a wide noisy family, and a router failing to reach
    it is the correct behaviour rather than a modelling failure.
    """
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(seed)
    grid = _grid(list(episodes), only_protocols=only_protocols)
    if grid is None:
        return {"note": "no shared tasks"}

    train = grid.index_of(sorted(set(train_task_ids)))
    test = grid.index_of(sorted(set(test_task_ids)))
    if len(train) < 4 or len(test) < 4:
        return {"note": "too few tasks"}

    from scipy import sparse

    n_org, n_task = grid.correct.shape
    org_index = np.repeat(np.arange(n_org), n_task)
    task_index = np.tile(np.arange(n_task), n_org)
    # One row per organization-task pair with exactly two non-zeros. Dense, this is 300 MB for the
    # 134-system SWE-bench matrix; sparse it is a few megabytes.
    n_rows = n_org * n_task
    design = sparse.csr_matrix(
        (
            np.ones(2 * n_rows),
            np.column_stack([org_index, n_org + task_index]).reshape(-1),
            np.arange(0, 2 * n_rows + 1, 2),
        ),
        shape=(n_rows, n_org + n_task),
    )
    labels = grid.correct.reshape(-1)

    def headroom(correct: np.ndarray) -> tuple[float, float]:
        """Against the calibration-selected organization, and against the best one on test.

        The second removes selection noise from both sides of the comparison. It is not a valid
        baseline for a router - it reads test outcomes - but this function is asking about the
        structure of the outcome table rather than evaluating a decision rule, and the null is
        computed the same way, so the comparison is fair and the first variant's dependence on one
        possibly unlucky calibration draw is removed.
        """
        best = correct[:, test].max(axis=0).mean()
        fixed = int(np.argmax(correct[:, train].mean(axis=1)))
        return (
            100.0 * float(best - correct[fixed, test].mean()),
            100.0 * float(best - correct[:, test].mean(axis=1).max()),
        )

    observed, observed_vs_best = headroom(grid.correct)
    if len(set(labels.tolist())) < 2:
        return {"observed": observed, "note": "degenerate outcomes"}

    # Weak regularisation: with one parameter per task the fit is near-saturated by construction,
    # and the point is to reproduce the marginals, not to generalise.
    model = LogisticRegression(C=10.0, max_iter=2000)
    model.fit(design, labels)
    probability = model.predict_proba(design)[:, 1].reshape(n_org, n_task)

    null = np.empty(n_simulations)
    null_vs_best = np.empty(n_simulations)
    for i in range(n_simulations):
        simulated = (rng.random((n_org, n_task)) < probability).astype(float)
        null[i], null_vs_best[i] = headroom(simulated)

    return {
        "n_test_tasks": len(test),
        "n_organizations": n_org,
        "observed_headroom": observed,
        "null_headroom_mean": float(null.mean()),
        "null_headroom_q95": float(np.quantile(null, 0.95)),
        "excess_over_null": observed - float(null.mean()),
        "p_value": float((null >= observed).mean()),
        "observed_headroom_over_best": observed_vs_best,
        "null_headroom_over_best_mean": float(null_vs_best.mean()),
        "excess_over_null_over_best": observed_vs_best - float(null_vs_best.mean()),
        "p_value_over_best": float((null_vs_best >= observed_vs_best).mean()),
        "n_simulations": n_simulations,
    }


def routing_over_splits(
    episodes: Sequence[EpisodeRecord],
    *,
    task_space: "TaskSpace",
    domains: dict[str, str],
    n_splits: int = 50,
    calibration_fraction: float = 0.34,
    seed: int = 20260810,
    **kwargs: Any,
) -> dict[str, Any]:
    """Repeat the whole evaluation over random calibration/test partitions.

    One partition gives one number, and the numbers here are small relative to how much a
    partition moves them: the fixed-best organization alone swings several accuracy points
    between splits, which is a large fraction of the headroom being competed for. A gain that
    survives resplitting is a property of the pool and suite; one that does not is a property of
    the split. The splits are stratified by domain so every partition keeps the capability mix
    that the whole crosscap design exists to create.

    Returns per-rule mean gain over fixed-best, its spread across splits, and the fraction of
    splits in which the rule came out ahead.
    """
    rng = np.random.default_rng(seed)
    by_domain: dict[str, list[str]] = defaultdict(list)
    for task, domain in sorted(domains.items()):
        by_domain[domain].append(task)

    gains: dict[str, list[float]] = defaultdict(list)
    accuracies: dict[str, list[float]] = defaultdict(list)
    headroom: list[float] = []
    selection: list[float] = []

    for _ in range(n_splits):
        train: list[str] = []
        test: list[str] = []
        for tasks in by_domain.values():
            order = rng.permutation(len(tasks))
            cut = max(2, int(round(calibration_fraction * len(tasks))))
            train.extend(tasks[i] for i in order[:cut])
            test.extend(tasks[i] for i in order[cut:])

        report = evaluate_routing(
            episodes,
            task_space=task_space,
            train_task_ids=train,
            test_task_ids=test,
            n_bootstrap=0,
            **kwargs,
        )
        if not report.results:
            continue
        for name, result in report.results.items():
            gains[name].append(result.gain_over_fixed_best)
            accuracies[name].append(result.accuracy)
        headroom.append(report.oracle_headroom)
        selection.append(report.selection_gap)

    def summarise(values: list[float]) -> dict[str, float]:
        array = np.asarray(values, dtype=float)
        return {
            "mean": float(array.mean()),
            "sd": float(array.std(ddof=1)) if len(array) > 1 else float("nan"),
            "q05": float(np.quantile(array, 0.05)),
            "q95": float(np.quantile(array, 0.95)),
            "frac_positive": float((array > 0).mean()),
        }

    return {
        "n_splits": len(headroom),
        "calibration_fraction": calibration_fraction,
        "oracle_headroom": summarise(headroom),
        "selection_gap": summarise(selection),
        "gain_over_fixed_best": {n: summarise(v) for n, v in sorted(gains.items())},
        "accuracy": {n: summarise(v) for n, v in sorted(accuracies.items())},
    }
