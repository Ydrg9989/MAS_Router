"""The conformity arms manipulate one string, so that string has to be the only thing that moves.

Four properties are load-bearing. `format_peer_answers` is shared by every protocol in the package,
so adding a parameter to it must leave the default rendering byte-identical or every result in the
project moves at once. The inverted arm must be a true reversal that shows the same numbers to the
judge. Adoption must be matched with the task's own equivalence relation rather than string
equality. And the fitted model must recover the coefficient that generated the data — otherwise a
null result is a statement about the instrument, which is the trap D-029 and D-030 both fell into.
"""

from __future__ import annotations

import numpy as np

from mas_harness.metrics.adoption import (
    AdoptionRow,
    adoption_rows,
    fit_adoption_model,
)
from mas_harness.protocols.conformity import LABEL_TEMPLATE, competence_labels


class FakeEvaluator:
    """Equivalence up to case and surrounding whitespace, so it is not string equality."""

    def equivalent(self, first: str, second: str) -> bool:
        return bool(first) and bool(second) and first.strip().lower() == second.strip().lower()


class FakeContext:
    def __init__(self, competence):
        self.competence = dict(competence)


class TestLabels:
    def test_inversion_reverses_the_ranking(self):
        context = FakeContext({0: 0.9, 1: 0.5, 2: 0.7, 3: 0.3})
        order = [0, 1, 2, 3]
        truthful = competence_labels(context, order, invert=False)
        inverted = competence_labels(context, order, invert=True)

        strongest = max(order, key=lambda a: context.competence[a])
        weakest = min(order, key=lambda a: context.competence[a])
        assert truthful[strongest] == LABEL_TEMPLATE.format(0.9)
        # The weakest member is advertised with the strongest member's number.
        assert inverted[weakest] == LABEL_TEMPLATE.format(0.9)
        assert inverted[strongest] == LABEL_TEMPLATE.format(0.3)

    def test_the_judge_sees_the_same_numbers_in_both_arms(self):
        context = FakeContext({0: 0.9, 1: 0.5, 2: 0.7, 3: 0.3})
        order = [0, 1, 2, 3]
        assert sorted(competence_labels(context, order, invert=False).values()) == sorted(
            competence_labels(context, order, invert=True).values()
        )

    def test_ties_are_left_alone_rather_than_swapped(self):
        """With equal competence there is nothing to invert; forcing a swap would fake a signal."""
        context = FakeContext({0: 0.6, 1: 0.6})
        order = [0, 1]
        assert competence_labels(context, order, invert=True) == competence_labels(
            context, order, invert=False
        )

    def test_a_missing_competence_does_not_crash_the_arm(self):
        labels = competence_labels(FakeContext({0: 0.8}), [0, 1], invert=False)
        assert labels[1] == LABEL_TEMPLATE.format(0.0)


class TestAdoptionMatching:
    def _rows(self, answers, final, correct=None):
        order = sorted(answers)
        return adoption_rows(
            task_id="t1", pool="p", arm="A", order=order,
            member_answers=answers,
            member_correct=correct or dict.fromkeys(order, False),
            final_answer=final,
            advertised=dict.fromkeys(order, 0.5),
            true=dict.fromkeys(order, 0.5),
            evaluator=FakeEvaluator(),
        )

    def test_equivalent_but_textually_different_answers_count_as_adopted(self):
        rows, novel = self._rows({0: "Paris", 1: "London"}, final=" paris ")
        assert not novel
        assert {r.member: r.adopted for r in rows} == {0: 1, 1: 0}

    def test_an_answer_no_member_gave_is_recorded_as_novel(self):
        """D-044's rescue behaviour: the judge states something none of them said."""
        rows, novel = self._rows({0: "Paris", 1: "London"}, final="Berlin")
        assert novel
        assert all(r.adopted == 0 for r in rows)

    def test_every_member_sharing_the_adopted_answer_is_credited(self):
        rows, _ = self._rows({0: "Paris", 1: "paris", 2: "London"}, final="Paris")
        assert {r.member: r.adopted for r in rows} == {0: 1, 1: 1, 2: 0}

    def test_majority_membership_is_computed_over_equivalence_classes(self):
        rows, _ = self._rows({0: "Paris", 1: "paris", 2: "London"}, final="Paris")
        assert {r.member: r.in_majority for r in rows} == {0: 1, 1: 1, 2: 0}

    def test_an_abstaining_member_is_never_in_the_majority(self):
        rows, _ = self._rows({0: "", 1: "London"}, final="London")
        assert {r.member: r.in_majority for r in rows} == {0: 0, 1: 1}

    def test_position_is_recorded_so_order_effects_are_separable(self):
        rows, _ = self._rows({0: "Paris", 1: "London"}, final="Paris")
        assert [r.position for r in rows] == [0, 1]


def synthetic(n_tasks: int, *, driver: str, strength: float = 3.0, seed: int = 0):
    """Adoption generated purely from one regressor, with the other anti-correlated half the time.

    Half the tasks are a truthful arm (advertised == true) and half an inverted arm (advertised is
    the reverse ranking), which is exactly the pooled design the real study produces.
    """
    rng = np.random.default_rng(seed)
    rows: list[AdoptionRow] = []
    for task in range(n_tasks):
        # Deliberately NOT sorted by position: if competence rose with position, the `position`
        # regressor would absorb part of the signal and the recovered contrast would be
        # asymmetric between the two generating processes for a reason that has nothing to do
        # with the design. Real speaking order is not sorted by competence either.
        true = rng.uniform(0.3, 0.9, 4)
        inverted = task % 2 == 1
        order_by_strength = np.argsort(true)
        advertised = true.copy()
        if inverted:
            advertised[order_by_strength] = true[order_by_strength[::-1]]
        signal = advertised if driver == "advertised" else true
        logits = strength * (signal - signal.mean()) / max(signal.std(), 1e-9)
        probability = 1.0 / (1.0 + np.exp(-logits))
        for member in range(4):
            rows.append(
                AdoptionRow(
                    task_id=f"t{task}", pool="p",
                    arm="inverted" if inverted else "truthful",
                    member=member, position=member,
                    advertised=float(advertised[member]), true=float(true[member]),
                    adopted=int(rng.random() < probability[member]),
                    member_correct=0, in_majority=0,
                )
            )
    return rows


class TestTheModelIsIdentified:
    """Without these, a null coefficient says nothing about the data."""

    def test_it_recovers_an_advertised_driven_process(self):
        """The contrast, not the two coefficients: see the module docstring on why."""
        out = fit_adoption_model(synthetic(400, driver="advertised", seed=1))
        assert out["coefficients"]["advertised"] > 0.5
        assert out["advertised_minus_true"] > 2.0

    def test_it_recovers_a_true_driven_process(self):
        out = fit_adoption_model(synthetic(400, driver="true", seed=2))
        assert out["coefficients"]["true"] > 0.5
        assert out["advertised_minus_true"] < -2.0

    def test_the_contrast_separates_the_two_generating_processes(self):
        """The statistic the study will report must order the two worlds correctly."""
        label_driven = fit_adoption_model(synthetic(400, driver="advertised", seed=7))
        evidence_driven = fit_adoption_model(synthetic(400, driver="true", seed=7))
        assert (
            label_driven["advertised_minus_true"]
            > evidence_driven["advertised_minus_true"] + 4.0
        )

    def test_pooling_both_arms_keeps_the_design_well_conditioned(self):
        """The inverted arm is what makes the two coefficients separable at all.

        On the truthful arm alone, advertised competence *is* true competence, so the two columns
        are identical and the design is singular. That is not a numerical nuisance — it is the
        reason the study cannot be run without the inverted arm.
        """
        rows = synthetic(400, driver="advertised", seed=3)
        pooled = fit_adoption_model(rows)
        truthful_only = fit_adoption_model([r for r in rows if r.arm == "truthful"])
        assert np.isfinite(pooled["condition_number"])
        assert pooled["condition_number"] < 20.0
        assert truthful_only["condition_number"] > pooled["condition_number"] * 100

    def test_it_is_powered_for_a_small_effect_at_the_planned_sample_size(self):
        """~1,900 rows is what 475 tasks x 4 members gives; a weak signal must still register."""
        out = fit_adoption_model(synthetic(475, driver="advertised", strength=0.35, seed=4))
        low, high = out["ci95"]["advertised"]
        assert low > 0.0, (low, high)

    def test_a_process_driven_by_neither_yields_no_competence_effect(self):
        rng = np.random.default_rng(5)
        rows = synthetic(400, driver="true", seed=6)
        for row in rows:
            row.adopted = int(rng.random() < 0.4)
        out = fit_adoption_model(rows)
        assert abs(out["advertised_minus_true"]) < 1.0
        for name in ("advertised", "true"):
            low, high = out["ci95"][name]
            assert low < 0.0 < high, (name, low, high)


class TestSharedFormattingIsUnchanged:
    def test_the_default_rendering_is_byte_identical_without_labels(self):
        """`format_peer_answers` is shared by every protocol; the new parameter must be inert."""
        import inspect

        from mas_harness.protocols import base

        source = inspect.getsource(base.format_peer_answers)
        # The annotation is applied only inside a guard on the new parameter.
        assert "if competence_labels is not None" in source
        guarded = source.split("if competence_labels is not None")[1]
        assert guarded.lstrip().startswith("and agent_id in competence_labels:")

    def test_the_parameter_defaults_to_none(self):
        import inspect

        from mas_harness.protocols import base

        signature = inspect.signature(base.format_peer_answers)
        assert signature.parameters["competence_labels"].default is None
