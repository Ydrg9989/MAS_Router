"""Statistical tests for paired protocol comparisons.

The design is paired by construction: every protocol sees the same tasks and the same banked
answers (D-001). Paired tests are therefore both valid and considerably more sensitive than
two-sample tests, which matters a great deal at 90 tasks — the report's own power table puts
80% power for an 8-point paired effect at roughly 366 tasks, so at MVP scale we need every bit
of sensitivity available and we must be honest about what remains underpowered.

Everything here reports effect sizes with intervals, not just p-values. A protocol difference
of 2 points with a CI spanning zero is a different scientific statement from a 2-point
difference with a tight CI, and only the interval distinguishes them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass
class TestResult:
    name: str
    statistic: float
    p_value: float
    effect: float
    ci_low: float = float("nan")
    ci_high: float = float("nan")
    n: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def significant_at_05(self) -> bool:
        return self.p_value < 0.05

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def mcnemar(a: Sequence[bool], b: Sequence[bool], *, exact: bool = True) -> TestResult:
    """Paired test for two binary-outcome protocols on the same items.

    Only the discordant pairs carry information. The exact binomial version is used by
    default because at 90 tasks the discordant count is often small enough that the
    chi-squared approximation is unreliable.

    ``effect`` is the accuracy difference ``mean(a) - mean(b)``, in proportion units.
    """
    from scipy import stats

    a_array = np.asarray(a, dtype=bool)
    b_array = np.asarray(b, dtype=bool)
    if a_array.shape != b_array.shape:
        raise ValueError(f"paired arrays must match: {a_array.shape} vs {b_array.shape}")
    if a_array.size == 0:
        raise ValueError("cannot test empty arrays")

    a_only = int(np.sum(a_array & ~b_array))
    b_only = int(np.sum(~a_array & b_array))
    discordant = a_only + b_only

    if discordant == 0:
        # Identical decisions on every item: no evidence of difference, and no test to run.
        return TestResult(
            name="mcnemar",
            statistic=0.0,
            p_value=1.0,
            effect=0.0,
            n=int(a_array.size),
            detail={"a_only": 0, "b_only": 0, "discordant": 0, "note": "no discordant pairs"},
        )

    if exact:
        p_value = float(stats.binomtest(a_only, discordant, 0.5).pvalue)
        statistic = float(a_only)
    else:
        statistic = (abs(a_only - b_only) - 1) ** 2 / discordant
        p_value = float(stats.chi2.sf(statistic, df=1))

    return TestResult(
        name="mcnemar_exact" if exact else "mcnemar_chi2",
        statistic=statistic,
        p_value=p_value,
        effect=float(a_array.mean() - b_array.mean()),
        n=int(a_array.size),
        detail={"a_only": a_only, "b_only": b_only, "discordant": discordant},
    )


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> TestResult:
    """Bootstrap CI for the paired mean difference, resampling *items* not observations.

    Resampling items keeps the pairing intact, which is the whole point: resampling
    observations independently would destroy the correlation that makes the comparison
    sensitive.

    The reported p-value is the two-sided bootstrap proportion of resamples on the wrong side
    of zero. It is a rough companion to the interval, not a substitute for McNemar on binary
    outcomes.
    """
    a_array = np.asarray(a, dtype=float)
    b_array = np.asarray(b, dtype=float)
    if a_array.shape != b_array.shape:
        raise ValueError(f"paired arrays must match: {a_array.shape} vs {b_array.shape}")
    n = a_array.size
    if n == 0:
        raise ValueError("cannot bootstrap empty arrays")

    differences = a_array - b_array
    observed = float(differences.mean())

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n, size=(n_resamples, n))
    draws = differences[indices].mean(axis=1)

    alpha = (1.0 - confidence) / 2.0
    low, high = np.percentile(draws, [100 * alpha, 100 * (1 - alpha)])
    # Two-sided bootstrap p-value: twice the smaller tail, capped at 1.
    tail = min(float((draws <= 0).mean()), float((draws >= 0).mean()))
    p_value = min(1.0, 2.0 * tail)

    return TestResult(
        name="paired_bootstrap",
        statistic=observed,
        p_value=p_value,
        effect=observed,
        ci_low=float(low),
        ci_high=float(high),
        n=int(n),
        detail={"n_resamples": n_resamples, "confidence": confidence},
    )


def permutation_test(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_permutations: int = 10_000,
    seed: int = 0,
) -> TestResult:
    """Paired permutation test: randomly flip the sign of each pair's difference.

    The exact null for a paired design under exchangeability, and it makes no distributional
    assumption. Preferred over a paired t-test on binary or heavily skewed outcomes.
    """
    a_array = np.asarray(a, dtype=float)
    b_array = np.asarray(b, dtype=float)
    differences = a_array - b_array
    n = differences.size
    if n == 0:
        raise ValueError("cannot permute empty arrays")
    observed = float(differences.mean())

    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_permutations, n))
    null = (signs * differences).mean(axis=1)
    # +1 in numerator and denominator so a p-value is never exactly zero.
    p_value = float((np.sum(np.abs(null) >= abs(observed)) + 1) / (n_permutations + 1))

    return TestResult(
        name="paired_permutation",
        statistic=observed,
        p_value=p_value,
        effect=observed,
        n=int(n),
        detail={"n_permutations": n_permutations},
    )


def holm_bonferroni(
    p_values: Mapping[str, float], *, alpha: float = 0.05
) -> dict[str, dict[str, Any]]:
    """Holm step-down correction across a family of tests.

    Necessary here because the MVP compares five protocols pairwise, which is ten tests: at
    alpha 0.05 uncorrected, the chance of at least one false positive is around 40%. Holm is
    uniformly more powerful than Bonferroni and requires no independence assumption.
    """
    if not p_values:
        return {}
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    m = len(ordered)
    results: dict[str, dict[str, Any]] = {}
    max_adjusted = 0.0
    still_rejecting = True
    for rank, (name, p_value) in enumerate(ordered):
        # Enforce monotonicity of adjusted p-values.
        adjusted = min(1.0, max(max_adjusted, (m - rank) * p_value))
        max_adjusted = adjusted
        if still_rejecting and adjusted > alpha:
            still_rejecting = False
        results[name] = {
            "p_raw": float(p_value),
            "p_adjusted": float(adjusted),
            "rank": rank + 1,
            "reject": bool(still_rejecting and adjusted <= alpha),
            "threshold": alpha / (m - rank),
        }
    return results


def mixed_effects_logit(
    outcome: Sequence[bool],
    *,
    task_id: Sequence[str],
    fixed_effects: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    """Logistic regression with task clustering.

    LIMITATION, stated plainly: this fits a binomial GEE with an exchangeable working
    correlation clustered on task. The report specifies crossed random effects for task *and*
    seed. GEE gives correct cluster-robust standard errors for the task grouping but does not
    model a seed effect, so seed-driven variance is absorbed into residual noise. That is
    adequate for the pilot and understates precision rather than overstating it, which is the
    safe direction; a proper crossed fit is open in TODO.md.
    """
    import pandas as pd
    import statsmodels.api as sm

    frame = pd.DataFrame({"y": np.asarray(outcome, dtype=float), "task": list(task_id)})
    for name, values in fixed_effects.items():
        frame[name] = np.asarray(values, dtype=float)

    predictors = sm.add_constant(frame[list(fixed_effects)], has_constant="add")
    model = sm.GEE(
        frame["y"],
        predictors,
        groups=frame["task"],
        family=sm.families.Binomial(),
        cov_struct=sm.cov_struct.Exchangeable(),
    )
    fitted = model.fit()

    return {
        "method": "binomial GEE, exchangeable, clustered on task",
        "limitation": "no seed random effect; see docstring and TODO.md",
        "n_observations": int(len(frame)),
        "n_clusters": int(frame["task"].nunique()),
        "coefficients": {k: float(v) for k, v in fitted.params.items()},
        "std_errors": {k: float(v) for k, v in fitted.bse.items()},
        "p_values": {k: float(v) for k, v in fitted.pvalues.items()},
        "odds_ratios": {k: float(np.exp(v)) for k, v in fitted.params.items()},
    }


# ---- calibration --------------------------------------------------------------------------


def brier_score(probabilities: Sequence[float], outcomes: Sequence[bool]) -> float:
    p = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    y = np.asarray(outcomes, dtype=float)
    return float(np.mean((p - y) ** 2))


def negative_log_likelihood(probabilities: Sequence[float], outcomes: Sequence[bool]) -> float:
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1 - 1e-12)
    y = np.asarray(outcomes, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(
    probabilities: Sequence[float], outcomes: Sequence[bool], *, n_bins: int = 10
) -> dict[str, Any]:
    """Binned ECE, plus the per-bin detail needed to draw a reliability diagram.

    Equal-width bins, and empty bins contribute nothing rather than being imputed. ECE is
    sensitive to bin count, so the count is always reported alongside the value.
    """
    p = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    y = np.asarray(outcomes, dtype=float)
    if p.size == 0:
        raise ValueError("cannot compute ECE on empty input")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # Right-closed bins so p == 1.0 lands in the last bin rather than out of range.
    assignments = np.clip(np.digitize(p, edges[1:-1], right=True), 0, n_bins - 1)

    ece = 0.0
    max_gap = 0.0
    bins: list[dict[str, Any]] = []
    for index in range(n_bins):
        mask = assignments == index
        count = int(mask.sum())
        if count == 0:
            bins.append({"bin": index, "count": 0})
            continue
        confidence = float(p[mask].mean())
        accuracy = float(y[mask].mean())
        gap = abs(confidence - accuracy)
        weight = count / p.size
        ece += weight * gap
        max_gap = max(max_gap, gap)
        bins.append(
            {
                "bin": index,
                "count": count,
                "mean_confidence": confidence,
                "mean_accuracy": accuracy,
                "gap": gap,
            }
        )

    return {
        "ece": float(ece),
        "max_calibration_error": float(max_gap),
        "n_bins": n_bins,
        "n": int(p.size),
        "bins": bins,
    }


# ---- power ---------------------------------------------------------------------------------


def required_n_paired(
    *, effect_pp: float, discordance_rate: float, alpha: float = 0.05, power: float = 0.80
) -> int:
    """Items needed to detect a paired accuracy difference of ``effect_pp`` percentage points.

    Uses the normal approximation to McNemar. ``discordance_rate`` is the fraction of items
    where the two protocols disagree; it must be estimated from a pilot, and the required n is
    very sensitive to it, which is exactly why the report puts a pilot before the powered run.
    """
    from scipy import stats

    if not 0 < discordance_rate <= 1:
        raise ValueError(f"discordance_rate must be in (0, 1], got {discordance_rate}")
    effect = abs(effect_pp) / 100.0
    if effect <= 0:
        raise ValueError("effect_pp must be non-zero")
    if effect > discordance_rate:
        raise ValueError(
            f"an accuracy difference of {effect_pp}pp is impossible with only "
            f"{discordance_rate:.1%} discordance"
        )

    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    # Proportion of discordant pairs favouring the better protocol.
    p = 0.5 * (1 + effect / discordance_rate)
    numerator = z_alpha * 0.5 + z_beta * np.sqrt(p * (1 - p))
    n_discordant = (numerator / (p - 0.5)) ** 2
    return int(np.ceil(n_discordant / discordance_rate))
