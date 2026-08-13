"""RQ2-RQ5 measure decisions, so the restrictions they impose have to actually bind.

Three properties carry these experiments. A held-out organization must be genuinely unseen by the
fit, or RQ4 measures nothing. An unobserved cell must be genuinely unavailable — including to the
competence features, which is the subtle one, because letting them read every singleton would hand
RQ3's sparse arm the dense arm's information and guarantee the answer. And the whole apparatus must
detect routable structure when it is planted, or a negative result is a statement about the
instrument rather than about the data.
"""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics.research_questions import (
    Grid,
    _competence,
    evaluate,
    generalization,
    routing_over_family,
    solo_or_collaborate,
    stratified_resplit,
    summarise,
    supervision_efficiency,
)

N_TASKS = 120
N_CAPABILITIES = 4


def make_grid(
    correct: np.ndarray, *, members=None, protocols=None, seed: int = 0
) -> Grid:
    """Embeddings encode the capability label, so structure is *findable* when it is present."""
    rng = np.random.default_rng(seed)
    n_org, n_task = correct.shape
    domain_index = np.arange(n_task) % N_CAPABILITIES
    one_hot = np.eye(N_CAPABILITIES)[domain_index]
    embeddings = np.hstack([one_hot * 3.0, rng.normal(0, 0.3, (n_task, 6))])
    if members is None:
        members = [(i % 4,) if i < 4 else tuple(sorted({i % 4, (i + 1) % 4})) for i in range(n_org)]
    if protocols is None:
        protocols = ["independent_majority"] * n_org
    return Grid(
        labels=[f"org{i}" for i in range(n_org)],
        tasks=[f"t{j}" for j in range(n_task)],
        correct=correct,
        members=list(members),
        protocols=list(protocols),
        domain_index=domain_index,
        embeddings=embeddings,
    )


def flat_grid(n_org: int = 8, rate: float = 0.6, seed: int = 1) -> Grid:
    """No structure: every organization equally good on every capability."""
    rng = np.random.default_rng(seed)
    return make_grid((rng.random((n_org, N_TASKS)) < rate).astype(float), seed=seed)


def specialist_grid(n_org: int = 8, seed: int = 2) -> Grid:
    """Planted structure: organization i is strong on capability i % 4 and weak elsewhere."""
    rng = np.random.default_rng(seed)
    domain_index = np.arange(N_TASKS) % N_CAPABILITIES
    probability = np.full((n_org, N_TASKS), 0.15)
    for row in range(n_org):
        probability[row, domain_index == row % N_CAPABILITIES] = 0.95
    return make_grid((rng.random((n_org, N_TASKS)) < probability).astype(float), seed=seed)


# Stratified, NOT `arange(0, n, 2)` / `arange(1, n, 2)`: with capabilities cycling every four
# tasks, an even/odd split puts capabilities 0 and 2 in train and 1 and 3 in test, so the router is
# asked to route capabilities it has never seen and scores below chance for a reason that has
# nothing to do with the code under test.
HALF = stratified_resplit(np.arange(N_TASKS) % N_CAPABILITIES, 0.5, np.random.default_rng(0))


class TestRestrictionsBind:
    def test_a_held_out_organization_does_not_enter_the_fit(self):
        """Changing a held-out row's outcomes must not change the model's other predictions."""
        grid = specialist_grid()
        seen = np.arange(grid.n_org - 2)
        train, test = HALF

        first = evaluate(grid, train, test, fit_rows=seen, baseline_rows=seen,
                         candidate_rows=seen, seed=5)
        mutated = Grid(**{**grid.__dict__, "correct": grid.correct.copy()})
        mutated.correct[grid.n_org - 1] = 1.0 - mutated.correct[grid.n_org - 1]
        second = evaluate(mutated, train, test, fit_rows=seen, baseline_rows=seen,
                          candidate_rows=seen, seed=5)

        assert first["q_theta"].accuracy == pytest.approx(second["q_theta"].accuracy)
        assert first["fixed_best"].accuracy == pytest.approx(second["fixed_best"].accuracy)

    def test_the_baseline_cannot_pick_an_organization_it_was_not_shown(self):
        grid = specialist_grid()
        seen = np.array([0, 1])
        arms = evaluate(grid, *HALF, fit_rows=seen, baseline_rows=seen,
                        candidate_rows=np.arange(grid.n_org), seed=6)
        # fixed_best scores exactly one of the two organizations it was allowed to consider.
        assert any(
            arms["fixed_best"].accuracy == pytest.approx(float(grid.correct[row, HALF[1]].mean()))
            for row in seen
        )

    def test_unobserved_cells_do_not_reach_the_competence_features(self):
        """The RQ3 leak that would guarantee the answer if it were left open."""
        grid = specialist_grid()
        train, _ = HALF
        observed = np.zeros((grid.n_org, grid.n_task), dtype=bool)
        observed[:, train[:6]] = True

        restricted = _competence(grid, train, observed)
        unrestricted = _competence(grid, train, None)
        assert restricted != unrestricted

        mutated = grid.correct.copy()
        mutated[:, train[6:]] = 1.0 - mutated[:, train[6:]]
        rebuilt = Grid(**{**grid.__dict__, "correct": mutated})
        assert _competence(rebuilt, train, observed) == restricted

    def test_the_router_only_ever_names_a_candidate(self):
        grid = specialist_grid()
        candidates = np.array([1, 3, 5])
        arms = evaluate(grid, *HALF, candidate_rows=candidates, seed=7)
        for name in ("q_theta", "q_theta_fixed", "oracle"):
            accuracy = arms[name].accuracy
            ceiling = float(grid.correct[np.ix_(candidates, HALF[1])].max(axis=0).mean())
            assert accuracy <= ceiling + 1e-9


class TestTheInstrumentFires:
    def test_planted_structure_is_found(self):
        """If routing cannot pay here it cannot pay anywhere: the label is in the embedding."""
        arms = evaluate(specialist_grid(), *HALF, seed=11)
        assert arms["q_theta"].gain_pp > 10.0
        assert arms["q_theta"].gain_pp > arms["q_theta_shuffled"].gain_pp + 5.0
        assert arms["q_theta"].n_distinct > 1

    def test_flat_data_yields_no_gain(self):
        arms = evaluate(flat_grid(), *HALF, seed=12)
        assert arms["q_theta"].gain_pp < 5.0

    def test_conditioning_gain_separates_structure_from_a_bigger_choice_set(self):
        """q_theta minus its own task-independent argmax: near zero with nothing to condition on.

        Averaged over splits, not measured on one. A per-task argmax over eight organizations
        fitted on sixty tasks is exactly the high-variance quantity D-033 showed can swing fifteen
        points on a single partition — asserting on one draw would test the noise, not the code.
        """
        def conditioning(grid, seeds=range(8)):
            values = []
            for seed in seeds:
                train, test = stratified_resplit(
                    grid.domain_index, 0.5, np.random.default_rng(seed)
                )
                arms = evaluate(grid, train, test, seed=seed)
                if "q_theta" in arms and "q_theta_fixed" in arms:
                    values.append(arms["q_theta"].gain_pp - arms["q_theta_fixed"].gain_pp)
            return float(np.mean(values))

        planted = conditioning(specialist_grid())
        flat = conditioning(flat_grid())
        assert planted > 10.0, planted
        assert flat < planted / 2.0, (flat, planted)


class TestSupervisionEfficiency:
    def test_reports_every_requested_budget(self):
        out = supervision_efficiency(flat_grid(), fractions=(0.1, 0.5), n_repeats=2, seed=21)
        assert set(out["budgets"]) == {"0.1", "0.5"}
        for entry in out["budgets"].values():
            assert "dense_gain_over_fixed_best" in entry
            assert "observational_gain_over_fixed_best" in entry

    def test_dense_supervision_helps_when_there_is_structure_to_learn(self):
        out = supervision_efficiency(specialist_grid(), fractions=(0.2,), n_repeats=6, seed=22)
        assert out["budgets"]["0.2"]["dense_minus_observational_pp"] > 0.0


class TestGeneralization:
    def test_all_three_regimes_are_reported(self):
        grid = specialist_grid()
        lodo = {
            f"d{c}": (
                np.flatnonzero(grid.domain_index != c),
                np.flatnonzero(grid.domain_index == c),
            )
            for c in range(N_CAPABILITIES)
        }
        out = generalization(grid, lodo=lodo, n_repeats=3, seed=31)
        for regime in ("iid", "domain_holdout", "agent_holdout", "organization_holdout"):
            assert regime in out
            assert "gain" in out[regime]

    def test_domain_holdout_is_harder_than_iid_on_planted_capability_structure(self):
        """Holding out a capability removes exactly the signal the router needs for it."""
        grid = specialist_grid()
        lodo = {
            f"d{c}": (
                np.flatnonzero(grid.domain_index != c),
                np.flatnonzero(grid.domain_index == c),
            )
            for c in range(N_CAPABILITIES)
        }
        out = generalization(grid, lodo=lodo, n_repeats=4, seed=32)
        assert out["iid"]["gain"]["mean"] > out["domain_holdout"]["gain"]["mean"]


class TestSoloOrCollaborate:
    def test_reports_the_pair_and_its_oracle(self):
        out = solo_or_collaborate(specialist_grid(), n_repeats=6, seed=41)
        assert out["oracle_over_the_pair"]["mean"] >= -1e-9
        assert 0.0 <= out["frac_choices_solo"]["mean"] <= 1.0

    def test_refuses_a_grid_with_no_teams(self):
        grid = make_grid(np.ones((4, N_TASKS)), members=[(i,) for i in range(4)])
        assert "note" in solo_or_collaborate(grid, n_repeats=2)


class TestPlumbing:
    def test_resplit_keeps_every_domain_on_both_sides(self):
        rng = np.random.default_rng(0)
        domain_index = np.arange(N_TASKS) % N_CAPABILITIES
        train, test = stratified_resplit(domain_index, 0.5, rng)
        assert set(domain_index[train].tolist()) == set(range(N_CAPABILITIES))
        assert set(domain_index[test].tolist()) == set(range(N_CAPABILITIES))
        assert not set(train.tolist()) & set(test.tolist())

    def test_summarise_ignores_non_finite_values(self):
        out = summarise([1.0, float("nan"), 3.0])
        assert out["n"] == 2
        assert out["mean"] == pytest.approx(2.0)

    def test_restricting_the_family_changes_the_organization_count(self):
        grid = specialist_grid()
        full = routing_over_family(grid, n_repeats=2, seed=51)
        half = routing_over_family(grid, n_repeats=2, restrict_rows=np.arange(4), seed=51)
        assert full["n_organizations"] == grid.n_org
        assert half["n_organizations"] == 4
