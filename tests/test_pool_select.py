"""Tests for the pool selector.

The selector's job is to refuse bad pools, so the tests are mostly about refusal. Two failure
modes would be expensive: silently picking a pool with a dominant member, which is the problem
D-021 exists to prevent, and picking a pool of near-chance agents because weak members maximize
headroom mechanically. Both are pinned here, along with the cross-pool identity handling, since
agent ids are pool-local and merging on them would conflate different models.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mas_harness.analysis.pool_select import (
    commit_rates,
    error_correlation,
    load_banks,
    score_subsets,
    select,
)

GT = "B"
WRONG = "C"


@pytest.fixture
def tasks(choice_task):
    return [replace(choice_task, task_id=f"mmlu_pro::t{i}") for i in range(8)]


def _matrix(pattern: dict[str, str]) -> dict[str, dict[str, bool]]:
    """Build a correctness matrix from one string of hits and misses per agent.

    ``{"alpha": "11110000"}`` means alpha is right on the first four tasks and wrong on the rest.
    Far more legible than nested dicts when the point of a test is a specific overlap structure.
    """
    length = {len(v) for v in pattern.values()}
    assert len(length) == 1, "every agent needs a verdict on every task"
    n = length.pop()
    return {
        f"t{i}": {name: bits[i] == "1" for name, bits in pattern.items()}
        for i in range(n)
    }


class TestErrorCorrelation:
    def test_identical_agents_correlate_perfectly(self):
        corr = error_correlation(
            _matrix({"a": "11110000", "b": "11110000"}), ["a", "b"]
        )
        assert corr[("a", "b")] == pytest.approx(1.0)

    def test_complementary_agents_correlate_negatively(self):
        corr = error_correlation(
            _matrix({"a": "11110000", "b": "00001111"}), ["a", "b"]
        )
        assert corr[("a", "b")] == pytest.approx(-1.0)

    def test_a_constant_agent_has_no_defined_correlation_and_is_reported_as_zero(self):
        """An agent right on everything has no variance; it must not crash or skew a subset."""
        corr = error_correlation(
            _matrix({"a": "11111111", "b": "11110000"}), ["a", "b"]
        )
        assert corr[("a", "b")] == 0.0


class TestScoring:
    def test_headroom_is_the_ceiling_minus_the_best_member(self):
        # a gets 4 of 8, b gets a different 4: together they cover everything.
        matrix = _matrix({"a": "11110000", "b": "00001111"})
        families = {"a": "fam_a", "b": "fam_b"}
        [candidate] = score_subsets(matrix, families, size=2)
        assert candidate.ceiling == pytest.approx(1.0)
        assert candidate.best == pytest.approx(0.5)
        assert candidate.headroom_pp == pytest.approx(50.0)
        assert candidate.dominance_gap_pp == pytest.approx(0.0)

    def test_a_redundant_member_contributes_no_headroom(self):
        matrix = _matrix({"a": "11110000", "b": "11110000"})
        families = {"a": "fam_a", "b": "fam_b"}
        [candidate] = score_subsets(matrix, families, size=2)
        assert candidate.headroom_pp == pytest.approx(0.0)
        assert candidate.mean_error_correlation == pytest.approx(1.0)

    def test_shared_family_is_counted_so_lineage_can_be_ranked_on(self):
        matrix = _matrix({"a": "11110000", "b": "00111100", "c": "00001111"})
        families = {"a": "same", "b": "same", "c": "other"}
        by_names = {tuple(c.names): c for c in score_subsets(matrix, families, size=2)}
        assert by_names[("a", "b")].n_families == 1
        assert by_names[("a", "c")].n_families == 2

    def test_asking_for_more_members_than_were_measured_is_an_error(self):
        matrix = _matrix({"a": "1100", "b": "0011"})
        with pytest.raises(ValueError, match="only 2 measured agents"):
            score_subsets(matrix, {"a": "x", "b": "y"}, size=3)


class TestSelectionCriteria:
    def test_a_dominant_member_is_rejected_even_with_ample_headroom(self):
        """The hard366-a failure mode: one member far ahead makes governance uninteresting."""
        # a is right on 7 of 8; b and c pick up the one it misses plus little else.
        matrix = _matrix({"a": "11111110", "b": "10000001", "c": "01000001"})
        families = {"a": "fa", "b": "fb", "c": "fc"}
        candidates = score_subsets(matrix, families, size=3)
        [only] = candidates
        assert only.headroom_pp == pytest.approx(12.5)
        assert only.dominance_gap_pp > 5.0

        decision = select(candidates, gate_pp=8.0, max_dominance_pp=5.0, min_best_accuracy=0.3)
        assert decision["recommended"] is None
        assert decision["failed_dominance"] == 1

    def test_a_pool_of_near_chance_agents_is_rejected_as_too_weak(self):
        """Weak members maximize headroom mechanically, which is not a governance finding."""
        matrix = _matrix({"a": "10000000", "b": "01000000", "c": "00100000"})
        families = {"a": "fa", "b": "fb", "c": "fc"}
        candidates = score_subsets(matrix, families, size=3)
        assert candidates[0].headroom_pp == pytest.approx(25.0)

        decision = select(candidates, gate_pp=8.0, max_dominance_pp=5.0, min_best_accuracy=0.55)
        assert decision["recommended"] is None
        assert decision["failed_too_weak"] == 1

    def test_a_balanced_complementary_pool_is_admitted(self):
        matrix = _matrix({"a": "11111000", "b": "11100111", "c": "00111111"})
        families = {"a": "fa", "b": "fb", "c": "fc"}
        decision = select(
            score_subsets(matrix, families, size=3),
            gate_pp=8.0,
            max_dominance_pp=5.0,
            min_best_accuracy=0.55,
        )
        assert decision["recommended"] is not None
        assert set(decision["recommended"]["names"]) == {"a", "b", "c"}

    def test_distinct_families_outrank_headroom(self):
        # The same-family pair has more headroom, so family must be the primary key to win.
        matrix = _matrix({"a": "11110000", "b": "00001111", "c": "00001110"})
        families = {"a": "shared", "b": "shared", "c": "other"}
        decision = select(
            score_subsets(matrix, families, size=2),
            gate_pp=8.0,
            max_dominance_pp=100.0,
            min_best_accuracy=0.0,
        )
        assert decision["recommended"]["n_families"] == 2

    def test_the_criteria_are_reported_so_a_choice_is_auditable(self):
        matrix = _matrix({"a": "11110000", "b": "00001111"})
        decision = select(
            score_subsets(matrix, {"a": "fa", "b": "fb"}, size=2),
            gate_pp=1.0,
            max_dominance_pp=2.0,
            min_best_accuracy=0.4,
        )
        assert decision["criteria"] == {
            "gate_pp": 1.0,
            "max_dominance_pp": 2.0,
            "min_best_accuracy": 0.4,
        }


class TestLoadBanks:
    def test_banks_merge_on_name_and_intersect_on_task(
        self, tmp_path, tasks, pool, make_answer_for
    ):
        """Two runs, overlapping on some tasks: only the shared, fully answered ones survive."""
        from mas_harness.records.writer import JsonlWriter, RunDirectory

        first, second = pool.agents[0], pool.agents[1]
        # Run one covers tasks 0-3 with `first`; run two covers tasks 2-5 with `second`.
        for run_id, agent, subset in (
            ("runA", first, tasks[0:4]),
            ("runB", second, tasks[2:6]),
        ):
            run = RunDirectory(tmp_path, run_id)
            writer = JsonlWriter(run.answers_path)
            for task in subset:
                writer.write(make_answer_for(task, agent, GT))
            writer.close()

        correct, families = load_banks(["runA", "runB"], tmp_path)
        assert set(families) == {first.name, second.name}
        # Only tasks 2 and 3 have an answer from both agents.
        assert len(correct) == 2
        assert all(len(row) == 2 for row in correct.values())

    def test_a_missing_run_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_banks(["nope"], tmp_path)

    def test_no_overlap_at_all_is_an_error_that_says_how_close_it_got(
        self, tmp_path, tasks, pool, make_answer_for
    ):
        from mas_harness.records.writer import JsonlWriter, RunDirectory

        for run_id, agent, subset in (
            ("runA", pool.agents[0], tasks[0:2]),
            ("runB", pool.agents[1], tasks[2:4]),
        ):
            run = RunDirectory(tmp_path, run_id)
            writer = JsonlWriter(run.answers_path)
            for task in subset:
                writer.write(make_answer_for(task, agent, WRONG))
            writer.close()

        with pytest.raises(ValueError, match="best-covered task has 1"):
            load_banks(["runA", "runB"], tmp_path)


class TestCommitRate:
    """An abstaining agent must not be mistaken for a complementary one.

    This is the artifact that makes the criterion necessary: a model whose responses cannot be
    parsed is wrong on a *different* set of items than a working model, so `headroom` rewards it
    exactly as it would reward genuine decorrelation.
    """

    def test_unreadable_responses_lower_the_rate_without_touching_accuracy(
        self, tasks, pool, make_answer_for
    ):
        agent = pool.agents[0]
        records = [make_answer_for(t, agent, GT) for t in tasks[:2]]
        records += [
            make_answer_for(t, agent, GT, text="I am unable to determine this.")
            for t in tasks[2:4]
        ]
        assert commit_rates(records) == {agent.name: 0.5}

    def test_an_abstaining_agent_looks_complementary_and_is_excluded_by_rate(
        self, tmp_path, tasks, pool, make_answer_for
    ):
        """Same bank, two views: with the abstainer it has headroom, without it there is none."""
        from mas_harness.records.writer import JsonlWriter, RunDirectory

        worker, abstainer = pool.agents[0], pool.agents[1]
        run = RunDirectory(tmp_path, "runA")
        writer = JsonlWriter(run.answers_path)
        for index, task in enumerate(tasks):
            # The worker is right on the first half, wrong on the second.
            writer.write(make_answer_for(task, worker, GT if index < 4 else WRONG))
            # The abstainer never answers, so every one of its records is an abstention.
            writer.write(
                make_answer_for(task, abstainer, GT, text="I cannot answer this question.")
            )
        writer.close()

        rates = commit_rates(run.load_answers())
        assert rates[worker.name] == 1.0
        assert rates[abstainer.name] == 0.0

        with_both, families = load_banks(["runA"], tmp_path)
        [pair] = score_subsets(with_both, families, size=2)
        # The abstainer adds nothing, and the selector can see that here only because a total
        # abstainer is the easy case; a partial one would register as complementary.
        assert pair.headroom_pp == pytest.approx(0.0)

        kept, families = load_banks(
            ["runA"], tmp_path, exclude=[n for n, r in rates.items() if r < 0.95]
        )
        assert set(families) == {worker.name}
        assert len(kept) == len(tasks)
