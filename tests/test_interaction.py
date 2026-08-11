"""The interaction test has to fire on planted crossing and stay quiet on additive data.

A test of ``gamma = 0`` is only worth reporting if it can go either way. The two tests that matter
here are the pair: additive data must not be flagged, and a planted rank reversal must be.
"""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics.interaction import (
    interaction_likelihood_ratio,
    outcomes_by_unit,
)

CAPABILITIES = ("code", "maths", "science", "theory_of_mind")


def build(
    rates: dict[str, dict[str, float]], *, n_per_capability: int = 40, seed: int = 7
) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    """Sample a balanced unit-by-task grid from per-unit, per-capability success rates."""
    rng = np.random.default_rng(seed)
    capability = {
        f"{cap}-{i}": cap for cap in CAPABILITIES for i in range(n_per_capability)
    }
    outcomes = {
        unit: {
            task: bool(rng.random() < rates[unit][cap]) for task, cap in capability.items()
        }
        for unit in rates
    }
    return outcomes, capability


def additive_rates() -> dict[str, dict[str, float]]:
    """Strength times difficulty: every unit ranks the capabilities in the same order."""
    strength = {"a": 0.0, "b": -0.5, "c": -1.0, "d": -1.5}
    difficulty = {"code": 1.4, "maths": 0.4, "science": 0.0, "theory_of_mind": -0.8}
    return {
        unit: {
            cap: float(1.0 / (1.0 + np.exp(-(s + d)))) for cap, d in difficulty.items()
        }
        for unit, s in strength.items()
    }


def crossing_rates() -> dict[str, dict[str, float]]:
    """Each unit owns one capability and collapses elsewhere: interaction with no main effect."""
    return {
        unit: {cap: (0.90 if cap == owned else 0.20) for cap in CAPABILITIES}
        for unit, owned in zip("abcd", CAPABILITIES, strict=True)
    }


class TestTheTestDiscriminates:
    def test_additive_data_is_not_flagged(self) -> None:
        outcomes, capability = build(additive_rates(), seed=11)
        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=100, seed=3)

        assert result.p_value_bootstrap > 0.05
        assert result.n_capabilities == 4
        assert result.n_tasks == 160

    def test_planted_crossing_is_detected(self) -> None:
        outcomes, capability = build(crossing_rates(), seed=13)
        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=100, seed=3)

        assert result.p_value_bootstrap < 0.05
        assert result.mean_absolute_departure_points > 5.0

    def test_the_largest_departures_name_the_planted_cells(self) -> None:
        outcomes, capability = build(crossing_rates(), seed=17)
        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=40, seed=3)

        owned = dict(zip("abcd", CAPABILITIES, strict=True))
        top = result.largest_departures[:4]
        assert all(d.departure_points > 0 for d in top)
        assert {(d.unit, d.capability) for d in top} == set(owned.items())


class TestMechanics:
    def test_the_statistic_is_non_negative_because_the_models_are_nested(self) -> None:
        outcomes, capability = build(additive_rates(), seed=5)
        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=20, seed=3)

        assert result.statistic >= -1e-6
        assert result.log_likelihood_interaction >= result.log_likelihood_additive - 1e-6
        assert result.degrees_of_freedom == (4 - 1) * (4 - 1)

    def test_the_same_seed_gives_the_same_p_value(self) -> None:
        outcomes, capability = build(crossing_rates(), seed=23)
        first = interaction_likelihood_ratio(outcomes, capability, n_simulations=30, seed=9)
        second = interaction_likelihood_ratio(outcomes, capability, n_simulations=30, seed=9)

        assert first.p_value_bootstrap == second.p_value_bootstrap
        assert first.statistic == pytest.approx(second.statistic)

    def test_unshared_tasks_are_dropped_so_the_grid_stays_balanced(self) -> None:
        outcomes, capability = build(additive_rates(), seed=29)
        dropped = sorted(outcomes["a"])[:10]
        for task in dropped:
            del outcomes["a"][task]

        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=10, seed=3)
        assert result.n_tasks == 150

    def test_a_p_value_can_never_be_reported_as_zero(self) -> None:
        outcomes, capability = build(crossing_rates(), seed=31)
        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=25, seed=3)

        assert result.p_value_bootstrap >= 1 / 26


class TestGuards:
    def test_one_capability_is_refused_rather_than_answered(self) -> None:
        outcomes, capability = build(additive_rates(), seed=37)
        flattened = dict.fromkeys(capability, "everything")

        result = interaction_likelihood_ratio(outcomes, flattened, n_simulations=10, seed=3)
        assert "single capability" in result.note
        assert np.isnan(result.statistic)

    def test_too_few_shared_tasks_is_refused(self) -> None:
        outcomes, capability = build(additive_rates(), n_per_capability=1, seed=41)
        result = interaction_likelihood_ratio(outcomes, capability, n_simulations=10, seed=3)

        assert "eight shared" in result.note


class TestCollapsingRecords:
    def test_records_collapse_to_a_nested_map(self) -> None:
        class Record:
            def __init__(self, agent_name: str, task_id: str, correct: bool) -> None:
                self.agent_name = agent_name
                self.task_id = task_id
                self.correct = correct

        records = [
            Record("grok43", "t1", True),
            Record("grok43", "t2", False),
            Record("deepseek32", "t1", False),
        ]
        assert outcomes_by_unit(records) == {
            "grok43": {"t1": True, "t2": False},
            "deepseek32": {"t1": False},
        }
