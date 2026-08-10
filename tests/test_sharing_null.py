"""The member-sharing null: does it reproduce the protocols, and does it fire when it should?

A null is only worth citing if something can beat it. `headroom_against_no_interaction` is
conservative because it draws organizations independently when they in fact share members, so the
replacement in `sharing_null.py` simulates agents and votes for real. These tests pin the two
properties that makes it usable: that outcomes are genuinely shared between overlapping coalitions,
and that planted agent-by-task interaction is detected while additive data is not.
"""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics.sharing_null import (
    ABSTAIN,
    _organization_outcomes,
    _vote,
    build_task_spaces,
    headroom_against_shared_member_null,
)
from mas_harness.records.schema import AnswerRecord, CallRecord, EpisodeRecord

CORRECT = "T"


class FakeEvaluator:
    """String equality for equivalence, and one designated correct answer."""

    def equivalent(self, first: str, second: str) -> bool:
        return bool(first) and bool(second) and first.strip() == second.strip()

    def score_extracted(self, answer: str) -> bool:
        return answer.strip() == CORRECT


def answer(task: str, agent: int, extracted: str) -> AnswerRecord:
    return AnswerRecord(
        run_id="t",
        task_id=task,
        suite="s",
        domain=task.split("-")[0],
        agent_id=agent,
        agent_name=f"a{agent}",
        model="m",
        provider="p",
        seed=0,
        text="",
        extracted_answer=extracted,
        ground_truth=CORRECT,
        correct=extracted == CORRECT,
        parse_failed=not extracted,
        call=CallRecord(stage="answer", model="m", provider="p"),
    )


def episode(task: str, protocol: str, coalition: tuple[int, ...], correct: bool) -> EpisodeRecord:
    return EpisodeRecord(
        run_id="t",
        task_id=task,
        suite="s",
        domain=task.split("-")[0],
        pool_id="pool",
        protocol_id=protocol,
        coalition=list(coalition),
        seed=0,
        final_text="",
        final_answer="",
        ground_truth=CORRECT,
        correct=correct,
        parse_failed=False,
        protocol_meta={"selected_agent_id": min(coalition)},
    )


def coalitions_of(agents: list[int]) -> list[tuple[int, ...]]:
    out: list[tuple[int, ...]] = []
    for mask in range(1, 1 << len(agents)):
        out.append(tuple(agents[i] for i in range(len(agents)) if mask >> i & 1))
    return sorted(out)


class TestVoting:
    def test_plurality_wins(self):
        assert _vote([1, 1, 2], [0, 1, 2], {}) == 1

    def test_abstentions_do_not_count(self):
        assert _vote([ABSTAIN, ABSTAIN, 7], [0, 1, 2], {}) == 7

    def test_all_abstaining_has_no_winner(self):
        assert _vote([ABSTAIN, ABSTAIN], [0, 1], {}) is None

    def test_ties_break_on_summed_competence(self):
        # One vote each; agent 1 is the more competent, so its answer wins.
        assert _vote([3, 4], [0, 1], {0: 0.2, 1: 0.9}) == 4

    def test_ties_with_equal_competence_break_on_lowest_agent(self):
        assert _vote([3, 4], [0, 1], {0: 0.5, 1: 0.5}) == 3


class TestTaskSpaces:
    def test_classes_correctness_and_distractor_weights(self):
        records = [
            answer("d-1", 0, CORRECT),
            answer("d-1", 1, "F1"),
            answer("d-1", 2, "F1"),
            answer("d-1", 3, ""),
        ]
        space = build_task_spaces(records, {"d-1": FakeEvaluator()})["d-1"]

        assert space.classes[1] == space.classes[2], "identical answers must share a class"
        assert space.classes[3] == ABSTAIN
        assert space.correct_class == space.classes[0]
        # One distractor, holding all of the wrong-answer mass.
        assert space.wrong_classes == (space.classes[1],)
        assert space.wrong_weights == pytest.approx((1.0,))


class TestMemberSharingIsPreserved:
    def test_overlapping_coalitions_reuse_the_same_simulated_answer(self):
        """A coalition gains nothing from a member that abstains, which is only true if the
        member's simulated answer is shared rather than redrawn per organization."""
        agents = [0, 1]
        tasks = ["d-1", "d-2"]
        records = [answer(t, 0, "") for t in tasks] + [
            answer("d-1", 1, CORRECT),
            answer("d-2", 1, "F1"),
        ]
        spaces = build_task_spaces(records, dict.fromkeys(tasks, FakeEvaluator()))
        # Agent 0 abstains everywhere, so {0,1} must match {1} exactly.
        table = np.array([[ABSTAIN, ABSTAIN], [spaces["d-1"].classes[1], spaces["d-2"].classes[1]]])

        outcomes = _organization_outcomes(
            table,
            agents=agents,
            tasks=tasks,
            spaces=[spaces[t] for t in tasks],
            coalitions=[(1,), (0, 1)],
            experts={},
            protocols=["independent_majority"],
            competence={0: 0.0, 1: 1.0},
        )
        assert outcomes[0].tolist() == outcomes[1].tolist()
        assert outcomes[0].tolist() == [1.0, 0.0]


def build_case(
    outcome: np.ndarray, agents: list[int], tasks: list[str], rng: np.random.Generator
) -> tuple[list[AnswerRecord], list[EpisodeRecord]]:
    """Answers realising ``outcome[agent, task]``, plus episodes over every coalition.

    Wrong answers are drawn from a three-distractor pool so that agents sometimes agree on being
    wrong, which is what makes plurality voting non-trivial.
    """
    records = [
        answer(
            task,
            agent,
            CORRECT if outcome[i, j] else f"F{rng.integers(3)}",
        )
        for i, agent in enumerate(agents)
        for j, task in enumerate(tasks)
    ]
    episodes = [
        episode(task, protocol, coalition, False)
        for protocol in ("independent_majority", "single_expert")
        for coalition in coalitions_of(agents)
        for task in tasks
    ]
    return records, episodes


def run(records, episodes, tasks, **kwargs):
    half = len(tasks) // 2
    return headroom_against_shared_member_null(
        records,
        episodes,
        evaluators=dict.fromkeys(tasks, FakeEvaluator()),
        train_task_ids=tasks[:half],
        test_task_ids=tasks[half:],
        n_simulations=120,
        **kwargs,
    )


class TestTheNullDiscriminates:
    def test_additive_data_shows_no_excess(self):
        """Agents differ in strength and tasks in difficulty, but nothing interacts."""
        rng = np.random.default_rng(0)
        agents = [0, 1, 2, 3]
        tasks = [f"d{j % 2}-{j}" for j in range(120)]
        strength = np.array([1.2, 0.6, 0.0, -0.6])
        difficulty = rng.normal(0.0, 1.0, len(tasks))
        probability = 1 / (1 + np.exp(-(strength[:, None] + difficulty[None, :])))
        outcome = rng.random(probability.shape) < probability

        records, episodes = build_case(outcome, agents, tasks, rng)
        report = run(records, episodes, tasks)

        assert report["p_value"] > 0.05, report
        assert abs(report["excess_over_null"]) < 8.0, report

    def test_planted_specialisation_is_detected(self):
        """Four agents, four capabilities, each agent good at exactly one.

        This is the structure routing assumes and D-035 could not find in real pools. The null must
        fire here, or it is measuring nothing.
        """
        rng = np.random.default_rng(1)
        agents = [0, 1, 2, 3]
        tasks = [f"d{j % 4}-{j}" for j in range(160)]
        capability = np.array([j % 4 for j in range(len(tasks))])
        probability = np.where(
            capability[None, :] == np.arange(4)[:, None], 0.95, 0.02
        )
        outcome = rng.random(probability.shape) < probability

        records, episodes = build_case(outcome, agents, tasks, rng)
        report = run(records, episodes, tasks)

        assert report["p_value"] < 0.05, report
        assert report["excess_over_null"] > 5.0, report


class TestReporting:
    def test_replay_agreement_is_reported(self):
        rng = np.random.default_rng(2)
        agents = [0, 1, 2]
        tasks = [f"d0-{j}" for j in range(40)]
        outcome = rng.random((len(agents), len(tasks))) < 0.6
        records, episodes = build_case(outcome, agents, tasks, rng)
        report = run(records, episodes, tasks)
        # Every episode above was built with correct=False, so agreement measures disagreement
        # with a deliberately wrong record set: the point is that it is computed and finite.
        assert 0.0 <= report["replay_agreement_with_recorded_episodes"] <= 1.0

    def test_too_little_data_is_refused_rather_than_guessed(self):
        rng = np.random.default_rng(3)
        tasks = ["d0-1", "d0-2"]
        records, episodes = build_case(np.ones((2, 2), bool), [0, 1], tasks, rng)
        assert "note" in run(records, episodes, tasks)
