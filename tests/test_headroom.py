"""Tests for the pool-headroom precondition (D-021).

The check exists to refuse a pool before Stage B is paid for, so the failure mode that matters is
an over-optimistic verdict: reporting headroom a protocol could not actually reach would buy a
Stage B run that cannot clear the gate. These tests pin the arithmetic and the two cases where it
is easy to be over-optimistic — abstentions, and a partially answered bank.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mas_harness.analysis.headroom import analyze, verdict

GT = "B"
WRONG = "C"
OTHER_WRONG = "D"


@pytest.fixture
def tasks(choice_task):
    """Four distinct tasks sharing ground truth "B"."""
    return [replace(choice_task, task_id=f"mmlu_pro::t{i}") for i in range(4)]


def _bank(make_answer_for, tasks, pool, per_task):
    """``per_task`` maps task index -> {agent name: extracted answer}."""
    return [
        make_answer_for(task, agent, per_task[index][agent.name])
        for index, task in enumerate(tasks)
        for agent in pool.agents
        if agent.name in per_task[index]
    ]


class TestCeilingAndHeadroom:
    def test_the_ceiling_is_the_rate_at_which_someone_is_right(
        self, tasks, pool, make_answer_for
    ):
        # alpha is right on tasks 0 and 1; beta rescues task 2; nobody gets task 3.
        per_task = [
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": GT, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))

        assert report["n_tasks"] == 4
        assert report["individual_accuracy"]["alpha"] == pytest.approx(0.5)
        assert report["individual_accuracy"]["beta"] == pytest.approx(0.25)

        grand = report["grand_coalition"]
        # Someone is right on three of four tasks, and the best member gets two.
        assert grand["ceiling"] == pytest.approx(0.75)
        assert grand["best_member"] == pytest.approx(0.5)
        assert grand["headroom_pp"] == pytest.approx(25.0)

    def test_a_member_who_is_never_uniquely_right_adds_no_headroom(
        self, tasks, pool, make_answer_for
    ):
        # delta duplicates alpha exactly, so the pair's ceiling is alpha's own accuracy.
        per_task = [
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": GT},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": GT},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        pair = next(
            c for c in report["coalitions"] if c["agent_names"] == ["alpha", "delta"]
        )
        assert pair["ceiling"] == pytest.approx(0.5)
        assert pair["headroom_pp"] == pytest.approx(0.0)

    def test_a_dominant_agent_compresses_headroom_relative_to_a_peer_pool(
        self, tasks, pool, make_answer_for
    ):
        # alpha dominates: right on everything the others are, plus one more.
        per_task = [
            {"alpha": GT, "beta": GT, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": WRONG, "gamma": GT, "delta": WRONG},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": GT},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        assert report["dominant_agent"] == "alpha"
        assert (
            report["mean_headroom_pp_without_dominant"]
            > report["mean_headroom_pp_with_dominant"]
        )


class TestAbstentionsDoNotInflateTheCeiling:
    def test_an_unparseable_response_cannot_supply_the_ceiling(
        self, tasks, pool, make_answer_for
    ):
        """A member who committed to nothing offers no answer for a protocol to pick up."""
        per_task = [
            {"alpha": WRONG, "beta": "", "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": "", "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": "", "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": "", "gamma": WRONG, "delta": WRONG},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        assert report["grand_coalition"]["ceiling"] == pytest.approx(0.0)
        assert report["grand_coalition"]["headroom_pp"] == pytest.approx(0.0)


class TestVerdict:
    def test_a_pool_below_the_gate_is_refused_and_diagnosed(
        self, tasks, pool, make_answer_for
    ):
        per_task = [
            {"alpha": GT, "beta": GT, "gamma": GT, "delta": GT},
            {"alpha": GT, "beta": GT, "gamma": GT, "delta": GT},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": OTHER_WRONG},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        # Someone is right on 3 of 4 and alpha alone gets 3 of 4, so there is no headroom.
        decision = verdict(report, gate_pp=8.0)
        assert decision["admissible"] is False
        assert "alpha" in decision["diagnosis"]

    def test_a_pool_with_room_is_admitted(self, tasks, pool, make_answer_for):
        per_task = [
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": GT, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": GT, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": GT},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        decision = verdict(report, gate_pp=8.0)
        # Every task is solved by exactly one member: ceiling 100%, best member 25%.
        assert report["grand_coalition"]["ceiling"] == pytest.approx(1.0)
        assert decision["admissible"] is True
        assert decision["diagnosis"] == "pool is admissible"

    def test_the_gate_threshold_is_a_parameter_not_a_constant(
        self, tasks, pool, make_answer_for
    ):
        per_task = [
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": GT, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": GT, "gamma": WRONG, "delta": WRONG},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        headroom = report["grand_coalition"]["headroom_pp"]
        assert verdict(report, gate_pp=headroom - 1)["admissible"] is True
        assert verdict(report, gate_pp=headroom + 1)["admissible"] is False


class TestShortfallIsAttributedToTheRightCause:
    """D-023: dominance and shared failure modes both destroy headroom, and the remedies differ.

    The tool blamed dominance unconditionally until `correlated4` — 1.6pp from best to second, and
    still short of the gate — showed that reading to be wrong in exactly the case built to test it.
    """

    def test_a_dominant_member_is_named_as_the_cause(self, tasks, pool, make_answer_for):
        per_task = [
            {"alpha": GT, "beta": GT, "gamma": GT, "delta": GT},
            {"alpha": GT, "beta": GT, "gamma": GT, "delta": GT},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": WRONG, "delta": OTHER_WRONG},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        assert report["top1_minus_top2_pp"] > 5.0
        diagnosis = verdict(report, gate_pp=8.0)["diagnosis"]
        assert "alpha" in diagnosis
        assert "above the next member" in diagnosis

    def test_near_equal_members_who_err_together_are_not_blamed_on_dominance(
        self, tasks, pool, make_answer_for
    ):
        """Every member identical: zero dominance gap, correlation 1.0, no headroom."""
        per_task = [
            dict.fromkeys(["alpha", "beta", "gamma", "delta"], GT),
            dict.fromkeys(["alpha", "beta", "gamma", "delta"], GT),
            dict.fromkeys(["alpha", "beta", "gamma", "delta"], WRONG),
            dict.fromkeys(["alpha", "beta", "gamma", "delta"], WRONG),
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        assert report["top1_minus_top2_pp"] == pytest.approx(0.0)
        assert report["mean_error_correlation"] == pytest.approx(1.0)

        diagnosis = verdict(report, gate_pp=8.0)["diagnosis"]
        assert "err together" in diagnosis
        assert "above the next member" not in diagnosis

    def test_error_correlation_is_reported_per_pair_so_the_culprit_is_locatable(
        self, tasks, pool, make_answer_for
    ):
        # alpha and beta agree on everything; gamma is the complement of both.
        per_task = [
            {"alpha": GT, "beta": GT, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": GT, "gamma": WRONG, "delta": GT},
            {"alpha": WRONG, "beta": WRONG, "gamma": GT, "delta": WRONG},
            {"alpha": WRONG, "beta": WRONG, "gamma": GT, "delta": GT},
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        pairs = report["pairwise_error_correlation"]
        assert pairs["alpha / beta"] == pytest.approx(1.0)
        assert pairs["alpha / gamma"] == pytest.approx(-1.0)


class TestDenominator:
    def test_tasks_missing_an_agent_are_excluded_so_the_denominator_matches(
        self, tasks, pool, make_answer_for
    ):
        """A partially answered task would otherwise credit absent members with a miss."""
        per_task = [
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": GT, "beta": WRONG, "gamma": WRONG, "delta": WRONG},
            {"alpha": WRONG, "beta": GT},  # gamma and delta never ran
        ]
        report = analyze(_bank(make_answer_for, tasks, pool, per_task))
        assert report["n_tasks"] == 3
        assert report["n_tasks_in_bank"] == 4
        assert report["individual_accuracy"]["alpha"] == pytest.approx(1.0)

    def test_an_empty_bank_is_an_error_not_a_zero(self):
        with pytest.raises(ValueError, match="no seed-0 answers"):
            analyze([])
