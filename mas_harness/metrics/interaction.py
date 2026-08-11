"""Is the agent-by-capability interaction real, even though headroom cannot detect it?

D-034 and D-037 established that observed oracle headroom does not exceed a null that removes
agent-by-task interaction. That is a statement about what a *per-task maximum* can see, and it is
easy to misread as "there is no interaction". The capability profiles in FRAMEWORK 5.1 say
otherwise: ``grok43`` is 0.967 on code and 0.133 on theory of mind while ``deepseek32`` is 0.850
and 0.800, which is a rank reversal in plain sight.

This module tests the interaction directly, as FRAMEWORK 5.2 asks. Fit

    additive       logit P(correct) = alpha_u + beta_x
    interaction    logit P(correct) = alpha_u + beta_x + gamma_{u,c(x)}

and test ``gamma = 0`` by likelihood ratio, where ``u`` is a unit (an agent or an organization),
``x`` a task and ``c(x)`` the task's capability.

Two deliberate choices:

``the p-value comes from a parametric bootstrap, not from chi-squared``
    One nuisance parameter per task with only a handful of units observed per task is the classic
    incidental-parameter setting, where the maximum-likelihood fit is biased and the asymptotic
    chi-squared reference distribution is not trustworthy. Simulating under the fitted additive
    model and refitting both models carries the same bias into the null, so the comparison stays
    honest. The chi-squared value is still reported, for reference only.

``departures are reported in accuracy points, not in log-odds``
    A table of ``gamma`` coefficients is unreadable and, with the collinearity between the
    main-effect and interaction blocks, not uniquely determined. Observed minus additive-predicted
    accuracy per
    unit-capability cell says the same thing in units a reader can check against FRAMEWORK 5.1.

Running this at both levels is the point. Interaction that is significant over agents but weak over
organizations is the sharpest available statement of "the structure is real, and aggregating it into
organizations is what hides it".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field

import numpy as np

DEFAULT_SEED = 20260810


@dataclass(frozen=True)
class Departure:
    """One unit-capability cell, in accuracy points away from the additive prediction."""

    unit: str
    capability: str
    n_tasks: int
    observed: float
    additive_prediction: float
    departure_points: float


@dataclass(frozen=True)
class InteractionTest:
    n_units: int
    n_tasks: int
    n_capabilities: int
    log_likelihood_additive: float
    log_likelihood_interaction: float
    statistic: float
    degrees_of_freedom: int
    p_value_bootstrap: float
    p_value_chi_squared: float
    n_simulations: int
    mean_absolute_departure_points: float
    null_mean_absolute_departure_points: float = float("nan")
    """What the same statistic reaches under the additive null: the noise floor for a cell mean."""
    excess_departure_points: float = float("nan")
    largest_departures: list[Departure] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _balanced_grid(
    outcomes: Mapping[str, Mapping[str, bool]], capability: Mapping[str, str]
) -> tuple[list[str], list[str], np.ndarray] | None:
    """Units by tasks, kept to tasks every unit attempted and that carry a capability label."""
    units = sorted(outcomes)
    if len(units) < 2:
        return None

    shared = set.intersection(*(set(outcomes[u]) for u in units))
    tasks = sorted(t for t in shared if t in capability)
    if len(tasks) < 8:
        return None

    grid = np.array([[bool(outcomes[u][t]) for t in tasks] for u in units], dtype=float)
    return units, tasks, grid


def _designs(
    n_units: int, n_tasks: int, capability_index: np.ndarray
) -> tuple["object", "object"]:
    """Additive and interaction design matrices, one row per unit-task pair in row-major order."""
    from scipy import sparse

    unit_of_row = np.repeat(np.arange(n_units), n_tasks)
    task_of_row = np.tile(np.arange(n_tasks), n_units)
    n_capabilities = int(capability_index.max()) + 1

    additive = sparse.hstack(
        [
            sparse.csr_matrix(
                (np.ones(n_units * n_tasks), (np.arange(n_units * n_tasks), unit_of_row)),
                shape=(n_units * n_tasks, n_units),
            ),
            sparse.csr_matrix(
                (np.ones(n_units * n_tasks), (np.arange(n_units * n_tasks), task_of_row)),
                shape=(n_units * n_tasks, n_tasks),
            ),
        ],
        format="csr",
    )

    cell = unit_of_row * n_capabilities + capability_index[task_of_row]
    interaction = sparse.hstack(
        [
            additive,
            sparse.csr_matrix(
                (np.ones(n_units * n_tasks), (np.arange(n_units * n_tasks), cell)),
                shape=(n_units * n_tasks, n_units * n_capabilities),
            ),
        ],
        format="csr",
    )
    return additive, interaction


def _fit(design, labels: np.ndarray, *, regularisation: float) -> tuple[float, np.ndarray]:
    """Return (log likelihood, fitted probabilities). Degenerate labels give a saturated fit."""
    from sklearn.linear_model import LogisticRegression

    if len(set(labels.tolist())) < 2:
        rate = float(labels.mean())
        probability = np.full(labels.shape, min(max(rate, 1e-6), 1 - 1e-6))
    else:
        model = LogisticRegression(
            C=regularisation, max_iter=3000, fit_intercept=False, solver="lbfgs"
        )
        model.fit(design, labels)
        probability = model.predict_proba(design)[:, 1]

    clipped = np.clip(probability, 1e-9, 1 - 1e-9)
    log_likelihood = float(
        np.sum(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped))
    )
    return log_likelihood, probability


def _mean_absolute_departure(
    labels: np.ndarray,
    probability: np.ndarray,
    *,
    n_units: int,
    n_tasks: int,
    capability_index: np.ndarray,
) -> float:
    """Mean over unit-capability cells of |observed - additive-predicted| accuracy, in points."""
    seen = labels.reshape(n_units, n_tasks)
    expected = probability.reshape(n_units, n_tasks)
    total = 0.0
    count = 0
    for c in range(int(capability_index.max()) + 1):
        columns = np.flatnonzero(capability_index == c)
        if not columns.size:
            continue
        total += float(
            np.sum(np.abs(seen[:, columns].mean(axis=1) - expected[:, columns].mean(axis=1)))
        )
        count += n_units
    return 100.0 * total / max(count, 1)


def _statistic(
    additive,
    interaction,
    labels: np.ndarray,
    *,
    regularisation: float,
    n_units: int,
    n_tasks: int,
    capability_index: np.ndarray,
):
    """Likelihood ratio and the departure table that goes with it, for one outcome vector.

    The departure is returned alongside because it has to be recomputed under every simulation.
    With sixty-odd tasks per capability cell, sampling noise alone moves a cell mean by several
    accuracy points, so a raw departure figure is not an effect size. Only the excess over the
    null's own departure is.
    """
    additive_ll, additive_probability = _fit(additive, labels, regularisation=regularisation)
    interaction_ll, _ = _fit(interaction, labels, regularisation=regularisation)
    departure = _mean_absolute_departure(
        labels,
        additive_probability,
        n_units=n_units,
        n_tasks=n_tasks,
        capability_index=capability_index,
    )
    return (
        2.0 * (interaction_ll - additive_ll),
        additive_ll,
        interaction_ll,
        additive_probability,
        departure,
    )


def interaction_likelihood_ratio(
    outcomes: Mapping[str, Mapping[str, bool]],
    capability: Mapping[str, str],
    *,
    n_simulations: int = 200,
    seed: int = DEFAULT_SEED,
    regularisation: float = 10.0,
    n_report: int = 8,
) -> InteractionTest:
    """Test agent-by-capability (or organization-by-capability) interaction by likelihood ratio.

    ``outcomes`` maps unit to task to correctness; ``capability`` maps task to its capability label.
    Tasks are restricted to those every unit attempted, so the grid is balanced and the two models
    see identical data.
    """
    from scipy import stats

    prepared = _balanced_grid(outcomes, capability)
    if prepared is None:
        return InteractionTest(
            n_units=len(outcomes),
            n_tasks=0,
            n_capabilities=0,
            log_likelihood_additive=float("nan"),
            log_likelihood_interaction=float("nan"),
            statistic=float("nan"),
            degrees_of_freedom=0,
            p_value_bootstrap=float("nan"),
            p_value_chi_squared=float("nan"),
            n_simulations=0,
            mean_absolute_departure_points=float("nan"),
            note="need at least two units and eight shared labelled tasks",
        )

    units, tasks, grid = prepared
    capabilities = sorted({capability[t] for t in tasks})
    capability_index = np.array([capabilities.index(capability[t]) for t in tasks])
    n_units, n_tasks, n_capabilities = len(units), len(tasks), len(capabilities)

    if n_capabilities < 2:
        return InteractionTest(
            n_units=n_units,
            n_tasks=n_tasks,
            n_capabilities=n_capabilities,
            log_likelihood_additive=float("nan"),
            log_likelihood_interaction=float("nan"),
            statistic=float("nan"),
            degrees_of_freedom=0,
            p_value_bootstrap=float("nan"),
            p_value_chi_squared=float("nan"),
            n_simulations=0,
            mean_absolute_departure_points=float("nan"),
            note="interaction is undefined with a single capability",
        )

    additive, interaction = _designs(n_units, n_tasks, capability_index)
    labels = grid.reshape(-1)
    shape = dict(n_units=n_units, n_tasks=n_tasks, capability_index=capability_index)
    observed, additive_ll, interaction_ll, additive_probability, observed_departure = _statistic(
        additive, interaction, labels, regularisation=regularisation, **shape
    )

    rng = np.random.default_rng(seed)
    null = np.empty(n_simulations)
    null_departure = np.empty(n_simulations)
    for i in range(n_simulations):
        simulated = (rng.random(additive_probability.shape) < additive_probability).astype(float)
        null[i], _, _, _, null_departure[i] = _statistic(
            additive, interaction, simulated, regularisation=regularisation, **shape
        )

    # Add-one so a test that never exceeds the observed value reports 1/(n+1) rather than zero.
    p_bootstrap = float((1 + int(np.sum(null >= observed))) / (1 + n_simulations))
    degrees_of_freedom = (n_units - 1) * (n_capabilities - 1)
    p_chi_squared = float(stats.chi2.sf(max(observed, 0.0), degrees_of_freedom))

    predicted = additive_probability.reshape(n_units, n_tasks)
    departures: list[Departure] = []
    for u, unit in enumerate(units):
        for c, name in enumerate(capabilities):
            columns = np.flatnonzero(capability_index == c)
            if not columns.size:
                continue
            seen = float(grid[u, columns].mean())
            expected = float(predicted[u, columns].mean())
            departures.append(
                Departure(
                    unit=unit,
                    capability=name,
                    n_tasks=int(columns.size),
                    observed=seen,
                    additive_prediction=expected,
                    departure_points=100.0 * (seen - expected),
                )
            )

    departures.sort(key=lambda d: -abs(d.departure_points))
    return InteractionTest(
        n_units=n_units,
        n_tasks=n_tasks,
        n_capabilities=n_capabilities,
        log_likelihood_additive=additive_ll,
        log_likelihood_interaction=interaction_ll,
        statistic=float(observed),
        degrees_of_freedom=degrees_of_freedom,
        p_value_bootstrap=p_bootstrap,
        p_value_chi_squared=p_chi_squared,
        n_simulations=n_simulations,
        mean_absolute_departure_points=float(observed_departure),
        null_mean_absolute_departure_points=float(null_departure.mean()),
        excess_departure_points=float(observed_departure - null_departure.mean()),
        largest_departures=departures[:n_report],
    )


def outcomes_by_unit(
    records: Sequence[object], *, unit_attribute: str = "agent_name"
) -> dict[str, dict[str, bool]]:
    """Collapse records carrying ``task_id``, ``correct`` and a unit attribute into a nested map."""
    collected: dict[str, dict[str, bool]] = {}
    for record in records:
        unit = str(getattr(record, unit_attribute))
        collected.setdefault(unit, {})[str(record.task_id)] = bool(record.correct)
    return collected
