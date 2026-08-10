"""Task layer: evaluator contract, manifest immutability, split determinism.

The evaluator cases mirror the fixtures in the upstream test suite
(``multi-agent-teams-hold-experts-back/tests/test_math_eval.py`` and
``tests/test_multiple_choice_eval.py``), re-asserted through *our* adapter. The point is to
detect drift in the adapter or in a pinned upstream, since every correctness label in the
project flows through these two methods.
"""

from __future__ import annotations

import pytest

from mas_harness.tasks.adapters import TaskSpec, answer_format_instruction, build_evaluator
from mas_harness.tasks.splits import k_fold, leave_one_domain_out, stratified_split


def choice_spec(ground_truth: str = "B") -> TaskSpec:
    return TaskSpec(
        task_id="t-choice",
        suite="mmlu_pro",
        domain="test",
        answer_type="choice",
        prompt="",
        ground_truth=ground_truth,
        payload={"question": "q", "options": ["a", "b", "c", "d"], "answer": ground_truth},
    )


def math_spec(ground_truth: str = "42") -> TaskSpec:
    return TaskSpec(
        task_id="t-math",
        suite="math500",
        domain="algebra",
        answer_type="boxed_math",
        prompt="",
        ground_truth=ground_truth,
        payload={"problem": "p", "solution": f"\\boxed{{{ground_truth}}}"},
    )


# ---- multiple choice ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The answer is A", "A"),
        ("Answer: C", "C"),
        ("(A)", "A"),
        ("After careful consideration, the answer is D.", "D"),
        ("My reasoning leads me to choose (E)", "E"),
        ("The answer is 'B'.", "B"),
        ("The answer is 'I'", "I"),
        ("the answer is a", "A"),
        # 'I' as a pronoun must not be mistaken for option I.
        ("I think the answer is B", "B"),
        ("I believe we should choose C", "C"),
        ("I agree with the team", ""),
    ],
)
def test_choice_extraction_matches_upstream_fixtures(text, expected):
    assert build_evaluator(choice_spec()).extract(text) == expected


def test_choice_scoring_is_case_insensitive():
    evaluator = build_evaluator(choice_spec("B"))
    assert evaluator.score("The answer is 'B'")
    assert evaluator.score("the answer is b")
    assert not evaluator.score("The answer is 'C'")


def test_unparseable_choice_answer_scores_false_not_raises():
    evaluator = build_evaluator(choice_spec("B"))
    assert evaluator.extract("no answer at all here") == ""
    assert evaluator.score("no answer at all here") is False


@pytest.mark.parametrize(
    "text",
    [
        # Every one of these is extracted as a confident answer by the upstream
        # terminal-letter rule, because it lacks a left word boundary (D-011).
        "no answer at all here",  # -> 'E' upstream
        "I have nothing to add.",  # -> 'D' upstream
        "hello world",  # -> 'D' upstream
        "I defer to my colleague.",  # -> 'E' upstream
        "I agree with the team",
        "This is a hard problem.",
        "Let me reconsider everything carefully.",
        "I cannot determine this from the information given.",
        "",
    ],
)
def test_prose_without_an_answer_is_an_abstention(text):
    """An agent that declares no answer must not be recorded as voting.

    Vote tallies, dilution and expert utilization all depend on telling "said nothing"
    apart from "voted wrong", so a spurious extraction here corrupts the primary metrics.
    """
    assert build_evaluator(choice_spec()).extract(text) == ""


def test_loose_extractor_invention_is_detectable():
    """We keep the upstream result so the disagreement rate can be reported, not hidden."""
    evaluator = build_evaluator(choice_spec())
    diagnostics = evaluator.extraction_diagnostics("I have nothing to add.")
    assert diagnostics["strict"] == ""
    assert diagnostics["loose"] == "D"
    assert diagnostics["loose_invented_answer"] is True

    agreed = evaluator.extraction_diagnostics("The answer is 'B'")
    assert agreed["strict"] == agreed["loose"] == "B"
    assert agreed["disagree"] is False


@pytest.mark.parametrize(
    "text,expected",
    [
        # A trailing standalone letter is still accepted: models do not always comply
        # with the mandated format, and a bare final letter is a real answer.
        ("I think it's A, but actually B", "B"),
        ("Weighing everything, D", "D"),
        ("... so the result is C.", "C"),
        # But a letter inside a word is not.
        ("Weighing everything, decided", ""),
    ],
)
def test_terminal_letter_requires_a_token_boundary(text, expected):
    assert build_evaluator(choice_spec()).extract(text) == expected


# ---- math ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The answer is \\boxed{42}", "42"),
        ("Result: \\boxed{\\frac{1}{2}}", "\\frac{1}{2}"),
        # The last boxed expression wins, which matters when a model revises itself.
        ("First \\boxed{10}, but actually \\boxed{20}", "20"),
    ],
)
def test_math_extraction_matches_upstream_fixtures(text, expected):
    assert build_evaluator(math_spec()).extract(text) == expected


@pytest.mark.parametrize(
    "candidate,truth",
    [
        ("42", "42"),
        ("42", "42.0"),
        ("\\dfrac{1}{2}", "\\frac{1}{2}"),
        ("1/2", "0.5"),
        ("x + y", "y + x"),
    ],
)
def test_math_equivalence_accepts_equivalent_forms(candidate, truth):
    evaluator = build_evaluator(math_spec(truth))
    assert evaluator.score(f"\\boxed{{{candidate}}}")


def test_math_equivalence_rejects_wrong_answers():
    evaluator = build_evaluator(math_spec("42"))
    assert not evaluator.score("\\boxed{43}")


def test_llm_judge_fallback_is_disabled():
    """D-003: the upstream scorer can issue an unlogged gpt-5 call. It must be off."""
    evaluator = build_evaluator(math_spec())
    assert evaluator._task.use_llm_fallback is False
    assert evaluator._task.llm_fallback_api_key is None


def test_score_extracted_agrees_with_score():
    evaluator = build_evaluator(choice_spec("D"))
    text = "The answer is 'D'"
    assert evaluator.score(text) == evaluator.score_extracted(evaluator.extract(text))


def test_answer_format_instruction_matches_the_extractor_priority():
    """The prompt must ask for the phrasing the extractor ranks highest."""
    assert "The answer is 'X'" in answer_format_instruction(choice_spec())
    assert "\\boxed{}" in answer_format_instruction(math_spec())

    # And the requested phrasing must actually round-trip.
    evaluator = build_evaluator(choice_spec("C"))
    assert evaluator.extract("The answer is 'C'") == "C"


def test_unknown_suite_is_rejected():
    spec = TaskSpec(
        task_id="x",
        suite="not_a_suite",
        domain="d",
        answer_type="choice",
        prompt="",
        ground_truth="A",
    )
    with pytest.raises(ValueError, match="no upstream evaluator"):
        build_evaluator(spec)


# ---- splits ----------------------------------------------------------------------------


def pairs(n_per_domain: int = 10, domains=("math", "physics", "bio")):
    return [(f"{d}-{i}", d) for d in domains for i in range(n_per_domain)]


def test_stratified_split_is_deterministic_and_disjoint():
    items = pairs()
    a1, b1 = stratified_split(items, fraction=0.3, seed=7)
    a2, b2 = stratified_split(items, fraction=0.3, seed=7)
    assert (a1, b1) == (a2, b2)
    assert not set(a1) & set(b1)
    assert set(a1) | set(b1) == {t for t, _ in items}


def test_stratified_split_changes_with_seed():
    items = pairs()
    assert stratified_split(items, fraction=0.3, seed=1) != stratified_split(
        items, fraction=0.3, seed=2
    )


def test_stratified_split_represents_every_domain_on_both_sides():
    items = pairs()
    calibration, test = stratified_split(items, fraction=0.34, seed=0)
    for side in (calibration, test):
        assert {t.split("-")[0] for t in side} == {"math", "physics", "bio"}


def test_stratified_split_never_empties_a_small_domain():
    items = [("a-0", "a"), ("a-1", "a"), ("b-0", "b"), ("b-1", "b")]
    first, second = stratified_split(items, fraction=0.05, seed=0)
    assert len(first) == 2 and len(second) == 2


def test_stratified_split_rejects_degenerate_fractions():
    with pytest.raises(ValueError):
        stratified_split(pairs(), fraction=0.0, seed=0)
    with pytest.raises(ValueError):
        stratified_split(pairs(), fraction=1.0, seed=0)


def test_leave_one_domain_out_holds_out_exactly_one_domain():
    folds = leave_one_domain_out(pairs())
    assert set(folds) == {"math", "physics", "bio"}
    for domain, (train, test) in folds.items():
        assert all(t.startswith(domain) for t in test)
        assert not any(t.startswith(domain) for t in train)
        assert not set(train) & set(test)


def test_k_fold_partitions_exactly_once():
    ids = [f"t{i}" for i in range(20)]
    folds = k_fold(ids, k=4, seed=3)
    assert len(folds) == 4
    seen: list[str] = []
    for train, test in folds:
        assert not set(train) & set(test)
        assert set(train) | set(test) == set(ids)
        seen.extend(test)
    assert sorted(seen) == sorted(ids)
