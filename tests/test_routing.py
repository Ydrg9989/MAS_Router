"""Routing gains, checked against planted signal, planted noise, and the leaks that faked them.

Two of this project's delegation results turned out to be artifacts of how they were measured
(D-029, D-030), so the load-bearing tests here are the negative ones: that a gain disappears when
the task representation carries no information, and that the baseline is not quietly allowed to
see the test set. A test that only proves the model fits would have passed in both failed cases.

Embeddings are planted rather than computed. The point of each test is a known geometry, and a
downloaded encoder would make the tests slow, non-hermetic, and silently dependent on whether the
sentence-transformers fallback fired.
"""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics.delegation import TaskSpace
from mas_harness.metrics.routing import evaluate_routing, headroom_against_no_interaction

from .test_metrics import episode

PROTOCOLS = ["majority_vote", "debate"]
COALITIONS = [(0,), (1,), (2,), (0, 1), (0, 1, 2)]


def organizations() -> list[tuple[str, tuple[int, ...]]]:
    return [(p, c) for p in PROTOCOLS for c in COALITIONS]


def build(outcomes: dict[tuple[str, tuple[int, ...]], dict[str, bool]], *, cost: float = 0.0):
    """Episodes from an organization -> task -> correct table."""
    return [
        episode(
            task_id=task,
            protocol_id=protocol,
            coalition=list(coalition),
            correct=correct,
            cost=cost,
        )
        for (protocol, coalition), tasks in outcomes.items()
        for task, correct in tasks.items()
    ]


def planted(n_per_family: int, seed: int, *, signal: bool):
    """Two task families with different best organizations, or the same table with no families.

    When ``signal`` is on, family A is solved by the lone agent 0 and family B by the lone agent 1,
    so no single organization is best overall and a router that can read the family wins. When it
    is off, every organization has the same success rate everywhere: the marginal quality of each
    organization is preserved, and only the task-organization association is gone.
    """
    rng = np.random.default_rng(seed)
    families = {"a": (PROTOCOLS[0], (0,)), "b": (PROTOCOLS[0], (1,))}
    outcomes = {o: {} for o in organizations()}
    coordinates: dict[str, np.ndarray] = {}
    tasks_by_family: dict[str, list[str]] = {}

    for family, champion in families.items():
        ids = [f"{family}::{i:03d}" for i in range(n_per_family)]
        tasks_by_family[family] = ids
        for task in ids:
            # A clean two-cluster geometry, plus noise dimensions the projection must ignore.
            centre = np.array([1.0, 0.0] if family == "a" else [0.0, 1.0])
            coordinates[task] = np.concatenate([centre + rng.normal(0, 0.1, 2),
                                                rng.normal(0, 1.0, 6)])
            for organization in outcomes:
                if signal:
                    rate = 0.9 if organization == champion else 0.35
                else:
                    rate = 0.55
                outcomes[organization][task] = bool(rng.random() < rate)

    tasks = sorted(coordinates)
    space = TaskSpace(
        name="planted",
        task_ids=tasks,
        features=np.vstack([coordinates[t] for t in tasks]),
        method="planted two-cluster geometry",
    )
    train = [t for t in tasks if int(t.split("::")[1]) % 2 == 0]
    test = [t for t in tasks if int(t.split("::")[1]) % 2 == 1]
    return outcomes, space, train, test


def run(outcomes, space, train, test, **kwargs):
    return evaluate_routing(
        build(outcomes),
        task_space=space,
        train_task_ids=train,
        test_task_ids=test,
        n_bootstrap=400,
        seed=7,
        **kwargs,
    )


class TestItDetectsSignal:
    def test_a_planted_family_winner_is_routed_to(self):
        outcomes, space, train, test = planted(70, seed=1, signal=True)
        report = run(outcomes, space, train, test)

        assert report.verdict.startswith("GAIN")
        assert report.model.gain_over_fixed_best > 10.0
        assert report.model.p_value < 0.05
        assert report.model.n_distinct_organizations >= 2, "a router that never switches is fixed"

    def test_the_gain_is_a_real_fraction_of_the_headroom(self):
        outcomes, space, train, test = planted(70, seed=2, signal=True)
        report = run(outcomes, space, train, test)

        assert report.oracle_headroom > 0
        assert 0.3 < report.captured_fraction <= 1.0

    def test_the_oracle_bounds_every_rule(self):
        outcomes, space, train, test = planted(50, seed=3, signal=True)
        report = run(outcomes, space, train, test)

        oracle = report.results["oracle"].accuracy
        for name, result in report.results.items():
            assert result.accuracy <= oracle + 1e-9, f"{name} beat the oracle"


class TestItRejectsNoise:
    def test_no_task_structure_produces_no_reported_gain(self):
        outcomes, space, train, test = planted(70, seed=11, signal=False)
        report = run(outcomes, space, train, test)

        assert not report.verdict.startswith("GAIN")

    def test_the_shuffled_control_destroys_a_real_gain(self):
        """The control's job: same model, same choice set, association removed."""
        outcomes, space, train, test = planted(70, seed=12, signal=True)
        report = run(outcomes, space, train, test)

        assert report.model.gain_over_fixed_best > report.control.gain_over_fixed_best
        assert report.control.gain_over_fixed_best < 5.0

    def test_a_gain_matched_by_the_control_is_not_reported_as_real(self):
        """Constructed directly, since the honest pipeline rarely produces it."""
        outcomes, space, train, test = planted(40, seed=13, signal=False)
        report = run(outcomes, space, train, test)
        report.results["q_theta"].gain_over_fixed_best = 4.0
        report.results["q_theta"].p_value = 0.01
        report.results["q_theta_shuffled"].gain_over_fixed_best = 4.5

        assert report.verdict.startswith("NOT REAL")


class TestHeadroomIsTestedAgainstNoInteraction:
    """A per-task maximum over many noisy organizations is large with nothing to route to, which
    is how this project came to believe in a routing prize that did not exist (D-034)."""

    def check(self, outcomes, train, test, n_simulations=60):
        return headroom_against_no_interaction(
            build(outcomes),
            train_task_ids=train,
            test_task_ids=test,
            n_simulations=n_simulations,
            seed=7,
        )

    def test_additive_outcomes_do_not_beat_the_null(self):
        """Organizations differ, tasks differ, but no organization suits any task."""
        rng = np.random.default_rng(31)
        tasks = [f"t{i:03d}" for i in range(120)]
        difficulty = {t: rng.uniform(-1.0, 1.0) for t in tasks}
        outcomes = {}
        for rank, organization in enumerate(organizations()):
            strength = 0.6 + 0.04 * (rank % 5)
            outcomes[organization] = {
                t: bool(rng.random() < np.clip(strength + difficulty[t] * 0.2, 0.05, 0.95))
                for t in tasks
            }
        result = self.check(outcomes, tasks[:60], tasks[60:])

        assert result["observed_headroom_over_best"] > 3.0, "the raw statistic is large anyway"
        assert result["p_value_over_best"] > 0.05
        assert abs(result["excess_over_null_over_best"]) < 3.0

    def test_a_planted_interaction_beats_the_null(self):
        """Two families, each solved only by its own organization and by nothing else.

        The non-champions have to be genuinely useless, which is itself the lesson. A wide family
        of merely mediocre organizations pushes the per-task maximum towards one under the null as
        readily as under real structure, so the excess shrinks even when the interaction is
        perfect. That is why the six measured cells show no excess and why the raw statistic was
        never evidence.
        """
        rng = np.random.default_rng(33)
        champions = {"a": organizations()[0], "b": organizations()[1]}
        outcomes = {o: {} for o in organizations()}
        tasks = []
        for family, champion in champions.items():
            for i in range(80):
                task = f"{family}::{i:03d}"
                tasks.append(task)
                for organization in outcomes:
                    rate = 0.9 if organization == champion else 0.03
                    outcomes[organization][task] = bool(rng.random() < rate)

        train = [t for t in tasks if int(t.split("::")[1]) % 2 == 0]
        test = [t for t in tasks if int(t.split("::")[1]) % 2 == 1]
        result = self.check(outcomes, train, test, n_simulations=100)

        assert result["excess_over_null_over_best"] > 5.0
        assert result["p_value_over_best"] < 0.05


class TestItDoesNotLeak:
    def test_fixed_best_is_chosen_on_train_not_test(self):
        """The trap in `utility.fixed_best_selection`, which maximises on the set it is scored on.

        Agent 0's organization is best on training tasks and worst on test tasks. A leak-free
        baseline must therefore score badly here; one that peeks would score at the top.
        """
        tasks = [f"t{i:03d}" for i in range(80)]
        train, test = tasks[:40], tasks[40:]
        winner, loser = (PROTOCOLS[0], (0,)), (PROTOCOLS[0], (1,))
        outcomes = {o: {} for o in organizations()}
        for organization in outcomes:
            for task in tasks:
                on_train = task in set(train)
                if organization == winner:
                    outcomes[organization][task] = on_train
                elif organization == loser:
                    outcomes[organization][task] = not on_train
                else:
                    outcomes[organization][task] = False

        rng = np.random.default_rng(5)
        space = TaskSpace(
            name="uninformative",
            task_ids=tasks,
            features=rng.normal(size=(len(tasks), 8)),
            method="pure noise",
        )
        report = run(outcomes, space, train, test)

        assert report.results["fixed_best"].accuracy == pytest.approx(0.0), (
            "the train winner scores zero on test; anything higher means the baseline peeked"
        )
        assert report.results["oracle"].accuracy == pytest.approx(1.0)

    def test_only_shared_tasks_are_compared(self):
        """An organization missing tasks would otherwise be judged on an easier subset."""
        outcomes, space, train, test = planted(30, seed=4, signal=True)
        thin = next(iter(outcomes))
        dropped = sorted(outcomes[thin])[:20]
        for task in dropped:
            del outcomes[thin][task]

        report = run(outcomes, space, train, test)

        assert report.n_train_tasks + report.n_test_tasks == 60 - len(dropped)


class TestMechanics:
    def test_results_are_deterministic_given_a_seed(self):
        outcomes, space, train, test = planted(40, seed=6, signal=True)
        a = run(outcomes, space, train, test)
        b = run(outcomes, space, train, test)

        assert a.to_dict() == b.to_dict()

    def test_cost_weights_change_what_is_chosen(self):
        """The most accurate organization is the biggest one, so pricing must trade it away."""
        rng = np.random.default_rng(8)
        tasks = [f"t{i:03d}" for i in range(80)]
        train, test = tasks[:40], tasks[40:]
        episodes = [
            episode(
                task_id=task,
                protocol_id=protocol,
                coalition=list(coalition),
                correct=bool(rng.random() < (0.9 if len(coalition) == 3 else 0.8)),
                cost=0.10 * len(coalition),
            )
            for protocol, coalition in organizations()
            for task in tasks
        ]
        space = TaskSpace(
            name="uninformative",
            task_ids=tasks,
            features=rng.normal(size=(len(tasks), 8)),
            method="pure noise",
        )
        common = dict(task_space=space, train_task_ids=train, test_task_ids=test,
                      n_bootstrap=200, seed=7)
        free = evaluate_routing(episodes, **common)
        priced = evaluate_routing(episodes, lambda_per_usd=5.0, **common)

        assert free.results["fixed_best"].mean_cost_usd == pytest.approx(0.30)
        assert priced.results["fixed_best"].mean_cost_usd == pytest.approx(0.10)
        assert priced.results["fixed_best"].accuracy < free.results["fixed_best"].accuracy

    def test_requires_exactly_one_task_representation(self):
        outcomes, space, train, test = planted(20, seed=9, signal=True)
        with pytest.raises(ValueError, match="exactly one"):
            evaluate_routing(
                build(outcomes), train_task_ids=train, test_task_ids=test
            )

    def test_interventions_are_excluded(self):
        from mas_harness.records.schema import InterventionSpec

        outcomes, space, train, test = planted(30, seed=10, signal=True)
        poisoned = [
            episode(
                task_id=task,
                protocol_id=PROTOCOLS[0],
                coalition=[0],
                correct=True,
                intervention=InterventionSpec(kind="mask", target_agent_id=0),
            )
            for task in sorted(space.task_ids)
        ]
        common = dict(task_space=space, train_task_ids=train, test_task_ids=test,
                      n_bootstrap=200, seed=7)

        clean = evaluate_routing(build(outcomes), **common)
        mixed = evaluate_routing(build(outcomes) + poisoned, **common)

        assert clean.to_dict() == mixed.to_dict()
