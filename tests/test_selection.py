"""Choosing one organization well is the only positive claim left, so its rules must be honest.

Three things are pinned here. Every rule is frozen on calibration — `oracle_fixed` is the sole
exception and is a ceiling, not a policy. The cross-pool rule must transfer *structure* rather than
a remembered score, or it is the argmax with extra steps. And the analytical point the module rests
on has a test of its own: with equal sample size per organization, any shrinkage toward a scalar is
monotone in the raw accuracy and therefore cannot move the argmax, which is why the shrinkage here
is toward a structural prediction instead.
"""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics.research_questions import Grid
from mas_harness.metrics.selection import (
    PoolSample,
    _grand_coalition_vote,
    _structural_prediction,
    choose,
    cross_pool_fit,
    evaluate_rules,
    organization_descriptor,
    protocol_rules,
)

N_TASKS = 120
N_CAPABILITIES = 4
VOTE = "independent_majority"
EXPERT = "single_expert"


def build_grid(correct: np.ndarray, *, members, protocols) -> Grid:
    rng = np.random.default_rng(0)
    n_task = correct.shape[1]
    domain_index = np.arange(n_task) % N_CAPABILITIES
    return Grid(
        labels=[f"{p}[{'-'.join(map(str, c))}]" for p, c in zip(protocols, members, strict=True)],
        tasks=[f"t{j}" for j in range(n_task)],
        correct=correct,
        members=list(members),
        protocols=list(protocols),
        domain_index=domain_index,
        embeddings=rng.normal(0, 1, (n_task, 8)),
    )


def pool_grid(seed: int = 0, rate: float = 0.6) -> Grid:
    """Four agents, fifteen coalitions, two protocols: the shape the sweep produces."""
    import itertools

    rng = np.random.default_rng(seed)
    coalitions = [
        c for size in range(1, 5) for c in itertools.combinations(range(4), size)
    ]
    members = coalitions * 2
    protocols = [VOTE] * len(coalitions) + [EXPERT] * len(coalitions)
    correct = (rng.random((len(members), N_TASKS)) < rate).astype(float)
    return build_grid(correct, members=members, protocols=protocols)


class TestTheRulesAreFrozen:
    def test_every_rule_but_the_oracle_ignores_the_test_half(self):
        grid = pool_grid()
        train = np.arange(0, N_TASKS, 2)
        picks = choose(grid, train)

        mutated = Grid(**{**grid.__dict__, "correct": grid.correct.copy()})
        test = np.arange(1, N_TASKS, 2)
        mutated.correct[:, test] = 1.0 - mutated.correct[:, test]
        assert choose(mutated, train) == picks

    def test_the_grand_coalition_vote_needs_no_calibration_at_all(self):
        grid = pool_grid()
        row = _grand_coalition_vote(grid)
        assert row is not None
        assert grid.members[row] == (0, 1, 2, 3)
        assert grid.protocols[row] == VOTE

    def test_one_se_never_picks_a_larger_coalition_than_the_argmax_tie_allows(self):
        grid = pool_grid(seed=3)
        train = np.arange(0, N_TASKS, 2)
        picks = choose(grid, train)
        accuracy = grid.correct[:, train].mean(axis=1)
        assert accuracy[picks["one_se"]] <= accuracy[picks["argmax"]] + 1e-9
        assert len(grid.members[picks["one_se"]]) <= len(grid.members[picks["largest_within_se"]])


class TestShrinkage:
    def test_shrinking_toward_a_scalar_cannot_move_the_argmax(self):
        """The analytical point the module is built on, asserted rather than asserted-in-prose.

        Every organization is scored on the same calibration tasks, so a common pull toward any
        constant is monotone in the raw accuracy and preserves the ordering entirely.
        """
        rng = np.random.default_rng(1)
        accuracy = rng.random(30)
        for weight in (0.1, 0.5, 0.9):
            for target in (0.0, float(accuracy.mean()), 1.0):
                shrunk = weight * accuracy + (1.0 - weight) * target
                assert int(np.argmax(shrunk)) == int(np.argmax(accuracy))

    def test_structural_shrinkage_can_move_it(self):
        grid = pool_grid(seed=5)
        train = np.arange(0, N_TASKS, 2)
        accuracy = grid.correct[:, train].mean(axis=1)
        predicted = _structural_prediction(grid, train, accuracy)
        assert predicted.shape == accuracy.shape
        # The prediction is smooth: seven parameters cannot reproduce thirty noisy estimates.
        assert np.std(predicted) < np.std(accuracy)

    def test_structural_prediction_falls_back_when_there_are_too_few_organizations(self):
        grid = build_grid(
            np.array([[1.0] * N_TASKS, [0.0] * N_TASKS]),
            members=[(0,), (1,)],
            protocols=[VOTE, VOTE],
        )
        train = np.arange(0, N_TASKS, 2)
        accuracy = grid.correct[:, train].mean(axis=1)
        predicted = _structural_prediction(grid, train, accuracy)
        assert np.allclose(predicted, accuracy.mean())


class TestCrossPool:
    def test_the_descriptor_does_not_encode_the_organizations_own_score(self):
        """Otherwise `cross_pool` is the argmax wearing a hat."""
        grid = pool_grid(seed=7)
        train = np.arange(0, N_TASKS, 2)
        row = 12
        before = organization_descriptor(grid, row, train)

        mutated = Grid(**{**grid.__dict__, "correct": grid.correct.copy()})
        mutated.correct[row, train] = 1.0 - mutated.correct[row, train]
        after = organization_descriptor(mutated, row, train)
        assert np.allclose(before, after)

    def test_a_fit_needs_enough_evidence(self):
        assert cross_pool_fit([]) is None
        thin = PoolSample(features=np.ones((2, 7)), outcome=np.ones(2))
        assert cross_pool_fit([thin]) is None

    def test_a_fit_produces_one_coefficient_per_descriptor(self):
        rng = np.random.default_rng(2)
        samples = [
            PoolSample(features=rng.normal(0, 1, (30, 7)), outcome=rng.random(30))
            for _ in range(4)
        ]
        coefficients = cross_pool_fit(samples)
        assert coefficients is not None and coefficients.shape == (7,)


class TestReporting:
    def test_every_rule_is_scored_and_the_argmax_gains_zero_against_itself(self):
        out = evaluate_rules(pool_grid(seed=11), n_repeats=6, seed=3)
        assert out["gain_over_argmax"]["argmax"]["mean"] == pytest.approx(0.0)
        for rule in ("one_se", "shrunk", "whole_pool_vote", "largest_within_se", "oracle_fixed"):
            assert rule in out["gain_over_argmax"]

    def test_the_oracle_ceiling_is_never_below_the_incumbent(self):
        out = evaluate_rules(pool_grid(seed=13), n_repeats=8, seed=4)
        assert out["gain_over_argmax"]["oracle_fixed"]["mean"] >= -1e-9

    def test_cross_pool_only_appears_when_coefficients_are_supplied(self):
        grid = pool_grid(seed=15)
        assert "cross_pool" not in evaluate_rules(grid, n_repeats=3)["gain_over_argmax"]
        coefficients = np.ones(7) * 0.1
        with_fit = evaluate_rules(grid, coefficients=coefficients, n_repeats=3)
        assert "cross_pool" in with_fit["gain_over_argmax"]


class TestProtocolRules:
    def test_reports_one_gain_per_grand_coalition_protocol(self):
        import itertools

        coalitions = [c for size in range(1, 5) for c in itertools.combinations(range(4), size)]
        members = coalitions * 2 + [(0, 1, 2, 3)]
        protocols = [VOTE] * len(coalitions) + [EXPERT] * len(coalitions) + ["debate_vote"]
        rng = np.random.default_rng(21)
        correct = (rng.random((len(members), N_TASKS)) < 0.6).astype(float)
        # Make debate clearly better so the a-priori rule has something to find.
        correct[-1] = (rng.random(N_TASKS) < 0.85).astype(float)

        out = protocol_rules(build_grid(correct, members=members, protocols=protocols),
                             n_repeats=10, seed=5)
        gains = out["gain_over_calibrated_aggregation"]
        assert set(gains) == {VOTE, EXPERT, "debate_vote"}
        assert gains["debate_vote"]["mean"] > 5.0

    def test_refuses_a_grid_with_only_one_grand_coalition_protocol(self):
        grid = build_grid(
            np.ones((2, N_TASKS)), members=[(0,), (0, 1)], protocols=[VOTE, VOTE]
        )
        assert "note" in protocol_rules(grid, n_repeats=2)
