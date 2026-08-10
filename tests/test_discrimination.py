"""Tests for the task-discrimination screener.

The screener answers one question before any money is spent: on how many tasks could two
protocols possibly disagree? Getting it wrong is expensive in the direction that matters, since
an over-optimistic answer buys a Stage B run that cannot detect the effect it was bought to
detect.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mas_harness.analysis.discrimination import (
    DILUTION_ELIGIBLE,
    MAJORITY_CORRECT,
    MINORITY_CORRECT,
    TIE,
    UNANIMOUS_CORRECT,
    UNANIMOUS_WRONG,
    classify_task,
    diagnose,
    select_for_stage_b,
    summarize,
)

# The choice_task fixture has ground truth "B"; anything else is a wrong vote.
GT = "B"
WRONG = "C"
OTHER_WRONG = "D"


def _bank(make_answer_for, task, pool, verdicts):
    """One answer per named agent, where ``verdicts`` maps agent name -> extracted answer."""
    return [
        make_answer_for(task, agent, verdicts[agent.name])
        for agent in pool.agents
        if agent.name in verdicts
    ]


def _names(pool):
    return [a.name for a in pool.agents]


class TestClassifyTask:
    def test_everyone_right_and_agreeing_is_unanimous_correct(
        self, choice_task, pool, make_answer_for
    ):
        records = _bank(
            make_answer_for, choice_task, pool, dict.fromkeys(_names(pool), GT)
        )
        assert classify_task(records) == UNANIMOUS_CORRECT

    def test_everyone_wrong_is_unanimous_wrong(self, choice_task, pool, make_answer_for):
        records = _bank(
            make_answer_for, choice_task, pool, dict.fromkeys(_names(pool), WRONG)
        )
        assert classify_task(records) == UNANIMOUS_WRONG

    def test_all_wrong_but_disagreeing_is_still_unrecoverable(
        self, choice_task, pool, make_answer_for
    ):
        """Disagreement alone does not help if nobody holds the correct answer."""
        names = _names(pool)
        verdicts = dict.fromkeys(names[:2], WRONG) | dict.fromkeys(names[2:], OTHER_WRONG)
        assert classify_task(_bank(make_answer_for, choice_task, pool, verdicts)) == (
            UNANIMOUS_WRONG
        )

    def test_three_of_four_right_is_majority_correct(self, choice_task, pool, make_answer_for):
        names = _names(pool)
        verdicts = dict.fromkeys(names[:3], GT) | {names[3]: WRONG}
        assert classify_task(_bank(make_answer_for, choice_task, pool, verdicts)) == (
            MAJORITY_CORRECT
        )

    def test_two_of_four_right_is_a_tie(self, choice_task, pool, make_answer_for):
        names = _names(pool)
        verdicts = dict.fromkeys(names[:2], GT) | dict.fromkeys(names[2:], WRONG)
        assert classify_task(_bank(make_answer_for, choice_task, pool, verdicts)) == TIE

    def test_one_of_four_right_is_minority_correct(self, choice_task, pool, make_answer_for):
        names = _names(pool)
        verdicts = {names[0]: GT} | dict.fromkeys(names[1:], WRONG)
        assert classify_task(_bank(make_answer_for, choice_task, pool, verdicts)) == (
            MINORITY_CORRECT
        )

    def test_only_minority_correct_and_tie_permit_dilution(self):
        """A correct expert can only be outvoted when correct is not the plurality answer."""
        assert set(DILUTION_ELIGIBLE) == {MINORITY_CORRECT, TIE}

    def test_an_abstention_is_not_counted_as_a_wrong_vote(
        self, choice_task, pool, make_answer_for
    ):
        """Silence must not manufacture a minority-correct task.

        Two agents right, two silent. Counting silence as a wrong vote would read this as a
        TIE and imply voting fails here, when the vote is in fact unanimous among those who
        actually voted (D-011).
        """
        names = _names(pool)
        records = _bank(
            make_answer_for,
            choice_task,
            pool,
            dict.fromkeys(names[:2], GT) | dict.fromkeys(names[2:], ""),
        )
        assert classify_task(records) == UNANIMOUS_CORRECT

    def test_all_agents_abstaining_is_unrecoverable(self, choice_task, pool, make_answer_for):
        records = _bank(make_answer_for, choice_task, pool, dict.fromkeys(_names(pool), ""))
        assert classify_task(records) == UNANIMOUS_WRONG


class TestDiagnoseAndSummarize:
    def test_the_spread_ceiling_equals_the_discriminating_fraction(
        self, choice_task, pool, make_answer_for
    ):
        """The headline planning number, and the reason this module exists.

        Nine unanimous tasks plus one split task cannot yield more than a 10-point difference
        between any two protocols, because nine of the ten return the same answer under every
        protocol.
        """
        names = _names(pool)
        records = []
        for i in range(10):
            task = replace(choice_task, task_id=f"t{i}")
            verdicts = (
                {names[0]: GT} | dict.fromkeys(names[1:], WRONG)
                if i == 0
                else dict.fromkeys(names, GT)
            )
            records.extend(_bank(make_answer_for, task, pool, verdicts))

        summary = summarize(diagnose(records))
        assert summary["n_tasks"] == 10
        assert summary["discriminating_frac"] == pytest.approx(0.1)
        assert summary["max_possible_protocol_spread_pp"] == pytest.approx(10.0)
        assert summary["dilution_eligible_frac"] == pytest.approx(0.1)

    def test_extra_seeds_do_not_inflate_apparent_disagreement(
        self, choice_task, pool, make_answer_for
    ):
        """Within-agent variance across seeds is a different question from between-agent
        disagreement, so only seed 0 is classified."""
        seed0 = _bank(make_answer_for, choice_task, pool, dict.fromkeys(_names(pool), GT))
        seed1 = [
            r.model_copy(update={"seed": 1, "extracted_answer": WRONG, "correct": False})
            for r in seed0
        ]
        diagnoses = diagnose([*seed0, *seed1])
        assert len(diagnoses) == 1
        assert diagnoses[0].task_class == UNANIMOUS_CORRECT

    def test_a_saturated_suite_is_visible_per_suite(self, choice_task, pool, make_answer_for):
        """The per-suite breakdown is what caught MATH-500 and MMLU-Pro sitting at ceiling
        while GPQA-Diamond still discriminated. A pooled figure would have hidden it."""
        names = _names(pool)
        records = []
        for i in range(4):
            easy = replace(choice_task, task_id=f"easy{i}", suite="mmlu_pro")
            records.extend(_bank(make_answer_for, easy, pool, dict.fromkeys(names, GT)))
        for i in range(4):
            hard = replace(choice_task, task_id=f"hard{i}", suite="gpqa_diamond")
            verdicts = {names[0]: GT} | dict.fromkeys(names[1:], WRONG)
            records.extend(_bank(make_answer_for, hard, pool, verdicts))

        by_suite = summarize(diagnose(records))["by_suite"]
        assert by_suite["mmlu_pro"]["mean_agent_accuracy"] == pytest.approx(1.0)
        assert by_suite["mmlu_pro"]["discriminating_frac"] == pytest.approx(0.0)
        assert by_suite["gpqa_diamond"]["discriminating_frac"] == pytest.approx(1.0)
        assert by_suite["gpqa_diamond"]["mean_agent_accuracy"] == pytest.approx(0.25)

    def test_empty_input_does_not_divide_by_zero(self):
        assert summarize([])["n_tasks"] == 0


class TestSelection:
    def _mixed(self, choice_task, pool, make_answer_for, n_split=6, n_unanimous=14):
        names = _names(pool)
        records = []
        for i in range(n_split):
            task = replace(choice_task, task_id=f"split{i}")
            verdicts = {names[0]: GT} | dict.fromkeys(names[1:], WRONG)
            records.extend(_bank(make_answer_for, task, pool, verdicts))
        for i in range(n_unanimous):
            task = replace(choice_task, task_id=f"unan{i}")
            records.extend(_bank(make_answer_for, task, pool, dict.fromkeys(names, GT)))
        return diagnose(records)

    def test_every_discriminating_task_is_kept(self, choice_task, pool, make_answer_for):
        diagnoses = self._mixed(choice_task, pool, make_answer_for)
        selection = select_for_stage_b(diagnoses, sample_fraction=0.15, seed=0)
        assert set(selection["stage_b_tasks"]) == {f"split{i}" for i in range(6)}

    def test_non_discriminating_tasks_are_sampled_not_dropped(
        self, choice_task, pool, make_answer_for
    ):
        """The control sample is what tests the assumption that a unanimous group holds its
        answer; dropping them outright would assume the answer."""
        diagnoses = self._mixed(choice_task, pool, make_answer_for)
        selection = select_for_stage_b(diagnoses, sample_fraction=0.5, seed=0)
        assert selection["control_tasks"], "a positive sample fraction must retain controls"
        assert set(selection["control_tasks"]).isdisjoint(selection["stage_b_tasks"])
        covered = (
            set(selection["stage_b_tasks"])
            | set(selection["control_tasks"])
            | set(selection["skipped_tasks"])
        )
        assert covered == {d.task_id for d in diagnoses}

    def test_a_zero_sample_fraction_skips_every_non_discriminating_task(
        self, choice_task, pool, make_answer_for
    ):
        diagnoses = self._mixed(choice_task, pool, make_answer_for)
        selection = select_for_stage_b(diagnoses, sample_fraction=0.0, seed=0)
        assert selection["control_tasks"] == []
        assert len(selection["skipped_tasks"]) == 14

    def test_selection_is_deterministic_given_a_seed(self, choice_task, pool, make_answer_for):
        diagnoses = self._mixed(choice_task, pool, make_answer_for)
        first = select_for_stage_b(diagnoses, sample_fraction=0.3, seed=7)
        second = select_for_stage_b(diagnoses, sample_fraction=0.3, seed=7)
        assert first == second

    def test_a_different_seed_can_choose_a_different_control_sample(
        self, choice_task, pool, make_answer_for
    ):
        diagnoses = self._mixed(
            choice_task, pool, make_answer_for, n_split=2, n_unanimous=40
        )
        samples = {
            tuple(select_for_stage_b(diagnoses, sample_fraction=0.2, seed=s)["control_tasks"])
            for s in range(6)
        }
        assert len(samples) > 1
