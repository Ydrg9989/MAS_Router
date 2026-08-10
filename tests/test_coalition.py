"""Correctness tests for the coalition analysis.

These are the tests that matter most, because the coalition numbers are the ones we would
otherwise have no independent way to check. Each test pins a mathematical identity or a
known-sign result rather than a value we happened to observe.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pytest

from mas_harness.metrics import coalition as C


def naive_harsanyi(values: np.ndarray) -> np.ndarray:
    """The O(3^n) definition, used only to check the fast transform."""
    n_masks = values.shape[1]
    n_agents = n_masks.bit_length() - 1
    out = np.zeros_like(values)
    for target in range(n_masks):
        members = C.members_of(target, n_agents)
        for size in range(len(members) + 1):
            for subset in combinations(members, size):
                sign = (-1) ** (len(members) - size)
                out[:, target] += sign * values[:, C.mask_of(subset)]
    return out


@pytest.fixture
def random_values() -> np.ndarray:
    rng = np.random.default_rng(1234)
    values = rng.random((20, 1 << 4))
    values[:, 0] = 0.0  # v(empty) = 0 by definition
    return values


def test_harsanyi_matches_naive_definition(random_values):
    fast = C.harsanyi_dividends(random_values)
    slow = naive_harsanyi(random_values)
    np.testing.assert_allclose(fast, slow, atol=1e-12)


def test_harsanyi_inverts_to_original_values(random_values):
    """v(S) must equal the sum of dividends over all subsets of S."""
    dividends = C.harsanyi_dividends(random_values)
    n_masks = random_values.shape[1]
    n_agents = n_masks.bit_length() - 1
    for mask in range(n_masks):
        members = C.members_of(mask, n_agents)
        total = np.zeros(random_values.shape[0])
        for size in range(len(members) + 1):
            for subset in combinations(members, size):
                total += dividends[:, C.mask_of(subset)]
        np.testing.assert_allclose(total, random_values[:, mask], atol=1e-10)


def test_additive_value_function_has_no_higher_order_interaction():
    """A purely additive v has zero dividends above order 1, so R_{>=2} must be zero."""
    n_agents = 4
    contributions = np.array([0.1, 0.2, 0.3, 0.4])
    values = np.zeros((5, 1 << n_agents))
    for mask in range(1 << n_agents):
        values[:, mask] = contributions[C.members_of(mask, n_agents)].sum()

    dividends = C.harsanyi_dividends(values)
    orders = np.array([C.popcount(m) for m in range(1 << n_agents)])
    assert np.abs(dividends[:, orders >= 2]).max() < 1e-12
    np.testing.assert_allclose(C.higher_order_ratio(dividends, min_order=2), 0.0, atol=1e-12)
    # Order-1 dividends recover the individual contributions exactly.
    for agent in range(n_agents):
        np.testing.assert_allclose(
            dividends[:, C.mask_of([agent])], contributions[agent], atol=1e-12
        )


def test_coverage_function_is_submodular():
    """The 'any member is correct' rule is a coverage function, hence provably submodular.

    Finding any violation here would mean the submodularity test itself is wrong.
    """
    rng = np.random.default_rng(7)
    outcomes = (rng.random((200, 4)) < 0.5).astype(int)
    values = C.simulate_coalition_values(outcomes, rule="any")
    result = C.submodularity_violations(values)
    assert result["violations_per_task"].sum() == 0
    assert result["max_violation"] == 0.0


def test_strict_majority_is_not_submodular():
    """A threshold rule is supermodular near its threshold, so violations must appear.

    This is the complement of the coverage test: it confirms the detector is not simply
    reporting zero for everything.
    """
    outcomes = np.array([[1, 1, 0, 0], [1, 1, 1, 0], [0, 1, 1, 1]])
    values = C.simulate_coalition_values(outcomes, rule="majority_strict")
    result = C.submodularity_violations(values)
    assert result["violations_per_task"].sum() > 0


def test_pairwise_synergy_matches_definition():
    outcomes = np.array([[1, 0], [0, 1], [1, 1], [0, 0]])
    values = C.simulate_coalition_values(outcomes, rule="any")
    synergy = C.pairwise_synergy(values, 0, 1)
    expected = (
        values[:, C.mask_of([0, 1])] - values[:, C.mask_of([0])] - values[:, C.mask_of([1])]
    )
    np.testing.assert_allclose(synergy, expected)
    # Disjoint successes are the textbook complementary case: OR gains a full point.
    assert synergy[0] == pytest.approx(0.0)  # only agent 0 correct -> no gain over max
    assert synergy[2] == pytest.approx(-1.0)  # both correct -> redundant, OR double-counts


def test_singleton_values_equal_individual_outcomes():
    rng = np.random.default_rng(3)
    outcomes = (rng.random((50, 4)) < 0.6).astype(int)
    for rule in ("any", "majority_strict", "plurality_distinct_errors"):
        values = C.simulate_coalition_values(outcomes, rule=rule)
        for agent in range(4):
            np.testing.assert_allclose(
                values[:, C.mask_of([agent])], outcomes[:, agent], atol=1e-12
            ), rule


def test_empty_coalition_is_zero():
    outcomes = np.ones((3, 3), dtype=int)
    for rule in ("any", "majority_strict", "plurality_distinct_errors", "best_member"):
        values = C.simulate_coalition_values(outcomes, rule=rule)
        assert (values[:, 0] == 0.0).all(), rule


def test_top_k_gap_is_never_negative():
    """The oracle is the best coalition of the same size, so the gap cannot be negative."""
    rng = np.random.default_rng(11)
    outcomes = (rng.random((100, 4)) < 0.5).astype(int)
    values = C.simulate_coalition_values(outcomes, rule="any")
    competence = outcomes.mean(axis=0)
    for k in (1, 2, 3):
        gap = C.top_k_gap(values, competence, k)
        assert gap["gap_per_task"].min() >= -1e-12


def test_top_k_gap_detects_a_planted_complementary_pair():
    """Two weak agents with disjoint successes must beat the two individually strongest."""
    n_tasks = 100
    outcomes = np.zeros((n_tasks, 4), dtype=int)
    # Agents 0 and 1 are strong but perfectly redundant.
    outcomes[: int(0.7 * n_tasks), 0] = 1
    outcomes[: int(0.7 * n_tasks), 1] = 1
    # Agents 2 and 3 are weaker but complementary: together they cover everything.
    outcomes[: n_tasks // 2, 2] = 1
    outcomes[n_tasks // 2 :, 3] = 1

    values = C.simulate_coalition_values(outcomes, rule="any")
    competence = outcomes.mean(axis=0)
    gap = C.top_k_gap(values, competence, 2)
    assert gap["baseline_members"] == [0, 1]
    assert gap["mean_gap"] > 0.25
    assert gap["frac_tasks_gap_ge_5pp"] > 0.25


def test_error_correlation_recovers_planted_structure():
    n_tasks = 500
    rng = np.random.default_rng(5)
    base = (rng.random(n_tasks) < 0.5).astype(int)
    outcomes = np.column_stack(
        [
            base,  # agent 0
            base,  # agent 1: identical, so errors correlate perfectly
            (rng.random(n_tasks) < 0.5).astype(int),  # agent 2: independent
            1 - base,  # agent 3: exact opposite
        ]
    )
    correlation = C.error_correlation(outcomes)
    assert correlation[0, 1] == pytest.approx(1.0, abs=1e-9)
    assert correlation[0, 3] == pytest.approx(-1.0, abs=1e-9)
    assert abs(correlation[0, 2]) < 0.15


def test_error_correlation_handles_zero_variance():
    """An always-correct agent has no error variance; report 0 rather than NaN."""
    outcomes = np.column_stack([np.ones(10, dtype=int), (np.arange(10) % 2)])
    correlation = C.error_correlation(outcomes)
    assert correlation[0, 1] == 0.0
    assert not np.isnan(correlation).any()


def test_cost_penalty_is_additive_in_members():
    values = np.ones((4, 1 << 3))
    values[:, 0] = 0.0
    penalized = C.apply_cost_penalty(values, per_agent_cost=[1.0, 2.0, 4.0], lambda_cost=0.1)
    assert penalized[0, C.mask_of([0])] == pytest.approx(1.0 - 0.1 * 1.0)
    assert penalized[0, C.mask_of([0, 2])] == pytest.approx(1.0 - 0.1 * 5.0)
    assert penalized[0, 0] == pytest.approx(0.0)


def test_selection_regret_is_zero_for_the_oracle():
    rng = np.random.default_rng(2)
    values = rng.random((30, 1 << 3))
    values[:, 0] = 0.0
    best = C.best_coalition_per_task(values)
    np.testing.assert_allclose(C.selection_regret(values, best), 0.0, atol=1e-12)


def test_exhaustive_enumeration_refuses_large_pools():
    with pytest.raises(ValueError, match="refusing"):
        C.simulate_coalition_values(np.zeros((2, 13), dtype=int))


def test_pairwise_model_beats_additive_on_planted_interaction():
    """With a real pair interaction present, the pairwise model must fit better."""
    n_tasks, n_agents = 300, 4
    rng = np.random.default_rng(17)
    outcomes = (rng.random((n_tasks, n_agents)) < 0.5).astype(int)
    # OR aggregation creates genuine pairwise structure (complementary coverage).
    values = C.simulate_coalition_values(outcomes, rule="any")
    difficulty = outcomes.mean(axis=1)
    dataset = C.build_coalition_dataset(values, task_difficulty=difficulty)

    train, test = C.held_out_coalition_split(dataset, held_out_masks=[C.mask_of([0, 1])])
    additive = C.fit_logistic(dataset, pairwise=False, train_rows=train, test_rows=test, name="a")
    pairwise = C.fit_logistic(dataset, pairwise=True, train_rows=train, test_rows=test, name="p")
    assert pairwise.train_log_loss < additive.train_log_loss


def test_held_out_coalition_split_excludes_the_mask_entirely():
    values = np.zeros((10, 1 << 3))
    dataset = C.build_coalition_dataset(values)
    held = C.mask_of([0, 1])
    train, test = C.held_out_coalition_split(dataset, held_out_masks=[held])
    assert set(dataset.masks[test].tolist()) == {held}
    assert held not in set(dataset.masks[train].tolist())
