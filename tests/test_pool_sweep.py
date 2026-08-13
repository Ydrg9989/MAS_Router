"""The sweep generalises three pools to seventy, so its reconstruction has to be exact.

Two properties carry the whole step. The vectorized plurality must agree with the reference
implementation in `sharing_null`, because every pool's outcome table is built from it and a
divergence would be invisible in the aggregate. And one agent id space must reproduce the tie-breaks
of pools that numbered their members differently, because plurality ties and the expert predictor
both break on the lowest id.

The joint null gets the same treatment `sharing_null` got: a test that it does not fire on additive
data and a test that it does fire on planted specialisation, so "no excess over the joint null" is a
statement from an instrument known to work.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from mas_harness.metrics.pool_sweep import (
    CoalitionIndex,
    Substrate,
    SweepNull,
    additive_agent_model,
    expert_table,
    global_order,
    headroom,
    organization_outcomes,
    pool_coalitions,
    simulate_bank,
    vote_outcomes,
)
from mas_harness.metrics.sharing_null import ABSTAIN, _headroom, _vote

CAPABILITIES = ["code", "math", "science", "tom"]


def substrate_from(
    classes: np.ndarray, correct: np.ndarray, *, n_capabilities: int = 4
) -> Substrate:
    """A minimal substrate over synthetic answers, with capabilities cycled across tasks."""
    n_agents, n_tasks = classes.shape
    domain_index = np.arange(n_tasks) % n_capabilities
    calibration = np.arange(0, n_tasks, 2)
    test = np.arange(1, n_tasks, 2)
    competence = correct[:, calibration].mean(axis=1)

    domain_accuracy = np.zeros((n_agents, n_capabilities))
    for c in range(n_capabilities):
        columns = calibration[domain_index[calibration] == c]
        if columns.size:
            domain_accuracy[:, c] = correct[:, columns].mean(axis=1)

    return Substrate(
        suite="synthetic",
        agents=[f"a{i}" for i in range(n_agents)],
        tasks=[f"t{i}" for i in range(n_tasks)],
        classes=classes,
        correct=correct,
        cost=np.ones((n_agents, n_tasks)),
        correct_class=np.zeros(n_tasks, dtype=int),
        wrong_classes=[np.array([1, 2]) for _ in range(n_tasks)],
        wrong_weights=[np.array([0.5, 0.5]) for _ in range(n_tasks)],
        domain_index=domain_index,
        capabilities=CAPABILITIES[:n_capabilities],
        domain_of_task=[CAPABILITIES[d] for d in domain_index],
        competence=competence,
        calibration=calibration,
        test=test,
        domain_accuracy=domain_accuracy,
    )


def random_bank(n_agents: int, n_tasks: int, seed: int, *, abstain: float = 0.1):
    """Class ids drawn so that ties, abstentions and unanimity all occur."""
    rng = np.random.default_rng(seed)
    classes = rng.integers(0, 3, size=(n_agents, n_tasks))
    classes[rng.random((n_agents, n_tasks)) < abstain] = ABSTAIN
    return classes, (classes == 0).astype(float)


class TestGlobalOrder:
    def test_orders_agree_with_every_pool(self):
        order = global_order(
            {
                "strong4": ["grok43", "gpt5mini", "deepseek32", "llama4scout"],
                "decorrelated4": ["gptoss120b", "mistral-small", "llama4scout", "ring26"],
                "correlated4": ["gpt5mini", "deepseek32", "gptoss120b", "qwen3-30b"],
            }
        )
        assert len(order) == 8
        for sequence in (
            ["grok43", "gpt5mini", "deepseek32", "llama4scout"],
            ["gptoss120b", "mistral-small", "llama4scout", "ring26"],
            ["gpt5mini", "deepseek32", "gptoss120b", "qwen3-30b"],
        ):
            positions = [order.index(name) for name in sequence]
            assert positions == sorted(positions)

    def test_contradictory_orders_are_refused_not_guessed(self):
        with pytest.raises(ValueError, match="no agent ordering"):
            global_order({"one": ["a", "b"], "two": ["b", "a"]})

    def test_result_is_deterministic(self):
        pools = {"one": ["c", "a"], "two": ["d", "b"]}
        assert global_order(pools) == global_order(pools)


class TestVectorizedVote:
    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_agrees_with_the_reference_implementation(self, seed):
        classes, _ = random_bank(6, 40, seed)
        competence = np.linspace(0.4, 0.9, 6)
        correct_class = np.zeros(40, dtype=int)
        index = CoalitionIndex.build(6, max_size=4)

        fast = vote_outcomes(classes, index, competence, correct_class)
        lookup = {a: float(competence[a]) for a in range(6)}
        for row, coalition in enumerate(index.coalitions):
            for t in range(40):
                winner = _vote([classes[a, t] for a in coalition], coalition, lookup)
                expected = float(winner is not None and winner == correct_class[t])
                assert fast[row, t] == expected, (coalition, t)

    def test_ties_break_on_competence_then_lowest_id(self):
        # Two agents each: classes 0 and 1 tie on count, so competence decides, then the id.
        classes = np.array([[0], [0], [1], [1]])
        index = CoalitionIndex.build(4, max_size=4)
        grand = index.position[(0, 1, 2, 3)]

        favouring_one = vote_outcomes(
            classes, index, np.array([0.1, 0.1, 0.9, 0.9]), np.zeros(1, dtype=int)
        )
        assert favouring_one[grand, 0] == 0.0

        equal = vote_outcomes(
            classes, index, np.array([0.5, 0.5, 0.5, 0.5]), np.zeros(1, dtype=int)
        )
        assert equal[grand, 0] == 1.0

    def test_all_abstaining_scores_zero(self):
        classes = np.full((4, 3), ABSTAIN)
        index = CoalitionIndex.build(4, max_size=4)
        outcomes = vote_outcomes(classes, index, np.full(4, 0.5), np.zeros(3, dtype=int))
        assert outcomes.sum() == 0.0

    def test_overlapping_coalitions_share_their_members_answers(self):
        classes, _ = random_bank(5, 30, seed=7)
        index = CoalitionIndex.build(5, max_size=4)
        outcomes = vote_outcomes(classes, index, np.full(5, 0.5), np.zeros(30, dtype=int))
        # Two coalitions differing in one member agree wherever the shared majority is decisive.
        left = outcomes[index.position[(0, 1, 2)]]
        right = outcomes[index.position[(0, 1, 3)]]
        unanimous = (classes[0] == classes[1]) & (classes[0] != ABSTAIN)
        assert np.array_equal(left[unanimous], right[unanimous])


class TestCoalitionIndex:
    def test_counts_every_non_empty_subset_up_to_the_cap(self):
        index = CoalitionIndex.build(8, max_size=4)
        assert len(index.coalitions) == 8 + 28 + 56 + 70
        assert {len(c) for c in index.coalitions} == {1, 2, 3, 4}

    def test_a_four_agent_pool_has_fifteen_coalitions(self):
        assert len(pool_coalitions((2, 3, 5, 7))) == 15
        assert pool_coalitions((2, 3, 5, 7))[-1] == (2, 3, 5, 7)


class TestHeadroom:
    def test_matches_the_reference_for_one_pool(self):
        rng = np.random.default_rng(3)
        organizations = (rng.random((30, 40)) < 0.7).astype(float)
        calibration, test = np.arange(0, 40, 2), np.arange(1, 40, 2)

        picked, best = headroom(organizations, calibration, test)
        expected_picked, expected_best = _headroom(organizations, calibration, test)
        assert picked == pytest.approx(expected_picked)
        assert best == pytest.approx(expected_best)

    def test_scores_a_stack_of_pools_in_one_call(self):
        rng = np.random.default_rng(4)
        stack = (rng.random((5, 30, 40)) < 0.7).astype(float)
        calibration, test = np.arange(0, 40, 2), np.arange(1, 40, 2)

        picked, best = headroom(stack, calibration, test)
        assert picked.shape == best.shape == (5,)
        for i in range(5):
            one, two = _headroom(stack[i], calibration, test)
            assert picked[i] == pytest.approx(one)
            assert best[i] == pytest.approx(two)

    def test_is_never_negative_against_the_best_on_test(self):
        rng = np.random.default_rng(5)
        stack = (rng.random((8, 30, 40)) < 0.5).astype(float)
        _, best = headroom(stack, np.arange(0, 40, 2), np.arange(1, 40, 2))
        assert np.all(best >= -1e-9)


class TestExpertTable:
    def test_prefers_the_pools_per_capability_best_when_it_is_a_member(self):
        classes, correct = random_bank(4, 40, seed=11)
        substrate = substrate_from(classes, correct)
        # Make agent 3 dominant on capability 0 and hopeless elsewhere.
        substrate.domain_accuracy[:] = 0.5
        substrate.domain_accuracy[3, 0] = 0.99
        substrate.competence[:] = np.array([0.8, 0.7, 0.6, 0.1])

        table = expert_table((0, 1, 2, 3), substrate)
        coalitions = pool_coalitions((0, 1, 2, 3))
        for row, coalition in enumerate(coalitions):
            if 3 in coalition:
                assert table[row, 0] == 3
            else:
                # Falls through to the pool's global best that is present, then to the local best.
                assert table[row, 0] in coalition

    def test_never_names_a_non_member(self):
        classes, correct = random_bank(6, 40, seed=12)
        substrate = substrate_from(classes, correct)
        for pool in itertools.combinations(range(6), 4):
            table = expert_table(pool, substrate)
            for row, coalition in enumerate(pool_coalitions(pool)):
                assert set(table[row].tolist()) <= set(coalition)

    def test_a_singleton_consults_its_only_member(self):
        classes, correct = random_bank(4, 20, seed=13)
        substrate = substrate_from(classes, correct)
        table = expert_table((0, 1, 2, 3), substrate)
        for row, coalition in enumerate(pool_coalitions((0, 1, 2, 3))):
            if len(coalition) == 1:
                assert set(table[row].tolist()) == set(coalition)


class TestOrganizationOutcomes:
    def test_thirty_rows_vote_first_then_expert(self):
        classes, correct = random_bank(4, 24, seed=17)
        substrate = substrate_from(classes, correct)
        index = CoalitionIndex.build(4, max_size=4)
        votes = vote_outcomes(classes, index, substrate.competence, substrate.correct_class)

        table = organization_outcomes(
            (0, 1, 2, 3),
            substrate=substrate,
            index=index,
            votes=votes,
            agent_correct=correct,
            experts=expert_table((0, 1, 2, 3), substrate),
        )
        assert table.shape == (30, 24)
        # Row 14 is the grand coalition's vote; rows 15-18 are the singleton experts.
        assert np.array_equal(table[14], votes[index.position[(0, 1, 2, 3)]])
        for i in range(4):
            assert np.array_equal(table[15 + i], correct[i])

    def test_a_singleton_vote_is_just_that_agent(self):
        classes, correct = random_bank(4, 24, seed=18)
        substrate = substrate_from(classes, correct)
        index = CoalitionIndex.build(4, max_size=4)
        votes = vote_outcomes(classes, index, substrate.competence, substrate.correct_class)
        for i in range(4):
            assert np.array_equal(votes[index.position[(i,)]], correct[i])


class TestJointNull:
    """Does the sweep-wide null behave the way a null has to?"""

    def _sweep(self, correct: np.ndarray, classes: np.ndarray, n_simulations: int = 120):
        substrate = substrate_from(classes, correct)
        n_agents = correct.shape[0]
        index = CoalitionIndex.build(n_agents, max_size=4)
        pools = list(itertools.combinations(range(n_agents), 4))
        probability, abstain_rate = additive_agent_model(substrate)
        experts = {p: expert_table(p, substrate) for p in pools}
        rows = {p: np.array([index.position[c] for c in pool_coalitions(p)]) for p in pools}

        def table(class_matrix, correctness):
            votes = vote_outcomes(
                class_matrix, index, substrate.competence, substrate.correct_class
            )
            return np.stack(
                [
                    np.vstack(
                        [
                            votes[rows[p]],
                            np.take_along_axis(
                                correctness, experts[p][:, substrate.domain_index], axis=0
                            ),
                        ]
                    )
                    for p in pools
                ]
            )

        observed_picked, observed_best = headroom(
            table(classes, correct), substrate.calibration, substrate.test
        )
        rng = np.random.default_rng(0)
        picked = np.empty((n_simulations, len(pools)))
        best = np.empty((n_simulations, len(pools)))
        for i in range(n_simulations):
            simulated, simulated_correct = simulate_bank(substrate, probability, abstain_rate, rng)
            picked[i], best[i] = headroom(
                table(simulated, simulated_correct), substrate.calibration, substrate.test
            )
        return SweepNull(
            pools=pools,
            observed=observed_best,
            observed_vs_picked=observed_picked,
            replicates=best,
            replicates_vs_picked=picked,
            n_simulations=n_simulations,
        )

    def _additive(self, seed: int, n_agents: int = 5, n_tasks: int = 160):
        rng = np.random.default_rng(seed)
        strength = np.linspace(-0.4, 0.8, n_agents)[:, None]
        difficulty = rng.normal(0.0, 0.9, n_tasks)[None, :]
        probability = 1.0 / (1.0 + np.exp(-(strength + difficulty)))
        correct = (rng.random((n_agents, n_tasks)) < probability).astype(float)
        return correct, np.where(correct == 1.0, 0, rng.integers(1, 3, size=correct.shape))

    def _planted(self, seed: int, n_agents: int = 5, n_tasks: int = 160):
        rng = np.random.default_rng(seed)
        domain_index = np.arange(n_tasks) % 4
        probability = np.full((n_agents, n_tasks), 0.04)
        for agent in range(n_agents):
            probability[agent, domain_index == agent % 4] = 0.97
        correct = (rng.random((n_agents, n_tasks)) < probability).astype(float)
        return correct, np.where(correct == 1.0, 0, rng.integers(1, 3, size=correct.shape))

    def test_planted_specialisation_is_detected(self):
        """Each agent competent on exactly one capability: the sweep-wide test must fire.

        Without this the sweep's headline — no pool of seventy exceeds the joint null — would be a
        statement from an instrument that never fires, which is not evidence about the data.
        """
        for seed in (21, 22, 23):
            null = self._sweep(*self._planted(seed), n_simulations=200)
            assert null.family_wise()["p_median"] <= 0.05, seed
            assert float(np.median(null.excess)) > 4.0, seed

    def test_planted_structure_scores_above_matched_additive_structure(self):
        """Planted specialisation must out-score additive data generated at the same shape.

        Deliberately *not* asserted as a nominal false-positive rate. The parametric bootstrap is
        not exactly exchangeable: the additive fit is penalised, so null tables are drawn from a
        smoother process than the one that produced the observed table, and a per-task maximum
        notices. At this size the bias is worth several points, which is why additive data here does
        not sit at zero. The bias is upward, so it makes a *rejection* suspect and a failure to
        reject conservative — and its size on the real substrate is measured by
        `measure_pool_sweep.calibration_check` rather than assumed here.
        """
        planted = float(
            np.mean([np.median(self._sweep(*self._planted(s)).excess) for s in (21, 22, 23)])
        )
        additive = float(
            np.mean([np.median(self._sweep(*self._additive(s)).excess) for s in (20, 24, 25)])
        )
        assert planted > additive + 2.0, (planted, additive)

    def test_p_values_are_bounded_away_from_zero(self):
        """Add-one smoothing, so a statistic never reached reports 1/(n+1) rather than zero."""
        rng = np.random.default_rng(22)
        correct = (rng.random((5, 60)) < 0.6).astype(float)
        classes = np.where(correct == 1.0, 0, rng.integers(1, 3, size=correct.shape))
        null = self._sweep(correct, classes, n_simulations=40)
        assert np.all(null.p_values > 0.0)
        assert np.all(null.p_values <= 1.0)


class TestSimulateBank:
    def test_correct_answers_take_the_tasks_correct_class(self):
        classes, correct = random_bank(4, 30, seed=31)
        substrate = substrate_from(classes, correct)
        probability, abstain_rate = additive_agent_model(substrate)
        simulated, is_correct = simulate_bank(
            substrate, probability, abstain_rate, np.random.default_rng(1)
        )
        for a in range(4):
            for t in range(30):
                if is_correct[a, t]:
                    assert simulated[a, t] == substrate.correct_class[t]
                else:
                    assert simulated[a, t] != substrate.correct_class[t]

    def test_wrong_answers_come_from_the_tasks_own_distractors(self):
        classes, correct = random_bank(4, 30, seed=32)
        substrate = substrate_from(classes, correct)
        probability, abstain_rate = additive_agent_model(substrate)
        simulated, is_correct = simulate_bank(
            substrate, probability, abstain_rate, np.random.default_rng(2)
        )
        wrong = simulated[(is_correct == 0) & (simulated != ABSTAIN)]
        assert set(wrong.tolist()) <= {1, 2}
