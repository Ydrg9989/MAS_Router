"""The cross-capability suites: extraction, grading, and the failure modes that cost money.

Two classes of bug are being guarded against, both of which have already happened once in this
project. D-011: a loose extractor turning prose into a confident answer, so abstention becomes a
vote. D-020: a suite every agent answers identically, so no protocol comparison can separate
anything and the run buys nothing.
"""

from __future__ import annotations

import pytest

from mas_harness.tasks.adapters import (
    NativeEvaluator,
    TaggedAnswer,
    answer_format_instruction,
    build_evaluator,
)
from mas_harness.tasks.manifest import (
    _aime_specs,
    _cruxeval_specs,
    _exploretom_specs,
)


def spec_for(answer_type: str, ground_truth: str):
    from mas_harness.tasks.adapters import TaskSpec

    suite = {
        "python_literal": "cruxeval",
        "integer": "aime",
        "short_text": "exploretom",
    }[answer_type]
    return TaskSpec(
        task_id=f"{suite}::t",
        suite=suite,
        domain="d",
        answer_type=answer_type,
        prompt="p",
        ground_truth=ground_truth,
    )


class TestExtractionRefusesToInventAnswers:
    """The D-011 property, restated for tagged answers."""

    @pytest.mark.parametrize(
        "text",
        [
            "I have nothing to add.",
            "I am not sure what this returns.",
            "The function is complex and I cannot simulate it.",
            "",
            "   ",
        ],
    )
    def test_prose_without_a_tag_is_an_abstention(self, text):
        assert TaggedAnswer.extract(text) == ""

    def test_a_tagged_answer_is_found_anywhere_in_the_response(self):
        assert TaggedAnswer.extract("Reasoning...\n[ANSWER]42[/ANSWER]\nDone.") == "42"

    def test_the_last_tag_wins_when_the_model_revises_itself(self):
        text = "First [ANSWER]11[/ANSWER] but on reflection [ANSWER]12[/ANSWER]"
        assert TaggedAnswer.extract(text) == "12"

    def test_the_declared_fallback_is_accepted_without_a_tag(self):
        assert TaggedAnswer.extract("so the answer is: 91") == "91"

    def test_a_response_truncated_after_the_open_tag_still_yields_its_answer(self):
        """From the smoke run: max_tokens cut "[ANSWER][][/ANSWER]" to "[ANSWER][][/"."""
        text = "1. `0` (first) -> `[]`\n\nthe list is empty.\n\n[ANSWER][][/"
        assert TaggedAnswer.extract(text) == "[]"

    def test_truncation_before_any_tag_remains_a_parse_failure(self):
        assert TaggedAnswer.extract("Let me simulate the loop. Step 1: the list is [3, 2") == ""

    def test_boxed_is_accepted_because_models_reach_for_it_regardless(self):
        """From the smoke run: an AIME answer given as \\boxed{721} with no tag."""
        assert TaggedAnswer.extract("so p+q = 721.\n\n\\[\n\\boxed{721}\n\\]") == "721"

    def test_an_abstention_never_equals_another_abstention(self):
        evaluator = NativeEvaluator(spec_for("integer", "42"))
        assert not evaluator.equivalent("", "")
        assert not evaluator.score("no idea")


class TestPythonLiteralGrading:
    @pytest.mark.parametrize(
        ("predicted", "truth", "expected"),
        [
            ("[1, 2]", "[1,2]", True),
            ("[(4, 1), (2, 3)]", "[(4,1),(2,3)]", True),
            ("'hello'", "'hello'", True),
            ("{'a': 1}", "{'a':1}", True),
            ("[1, 2]", "[2, 1]", False),
            ("42", "42.0", False),
            ("not a literal", "42", False),
        ],
    )
    def test_whitespace_does_not_change_the_verdict(self, predicted, truth, expected):
        evaluator = NativeEvaluator(spec_for("python_literal", truth))
        assert evaluator.score(f"[ANSWER]{predicted}[/ANSWER]") is expected

    def test_unparseable_output_falls_back_to_string_comparison(self):
        evaluator = NativeEvaluator(spec_for("python_literal", "<object at 0x1>"))
        assert evaluator.score("[ANSWER]<object  at   0x1>[/ANSWER]")


class TestIntegerGrading:
    @pytest.mark.parametrize(
        ("predicted", "expected"),
        [("33", True), ("033", True), ("\\boxed{33}", True), ("1,033", False), ("34", False)],
    )
    def test_integer_forms(self, predicted, expected):
        evaluator = NativeEvaluator(spec_for("integer", "33"))
        assert evaluator.score(f"[ANSWER]{predicted}[/ANSWER]") is expected

    def test_prose_around_the_number_is_tolerated(self):
        evaluator = NativeEvaluator(spec_for("integer", "204"))
        assert evaluator.score("[ANSWER]The answer is 204[/ANSWER]")


class TestShortTextGrading:
    @pytest.mark.parametrize(
        ("predicted", "expected"),
        [
            ("cardboard box", True),
            ("the cardboard box", True),
            ("Cardboard Box.", True),
            ("  cardboard   box ", True),
            ("wooden drawer", False),
        ],
    )
    def test_articles_case_and_punctuation_are_ignored(self, predicted, expected):
        evaluator = NativeEvaluator(spec_for("short_text", "cardboard box"))
        assert evaluator.score(f"[ANSWER]{predicted}[/ANSWER]") is expected


class TestPromptsMatchTheExtractor:
    """The D-011 lesson in its positive form: the mandated format must be the parsed one."""

    @pytest.mark.parametrize(
        "answer_type", ["python_literal", "integer", "short_text"]
    )
    def test_the_instruction_names_the_tags_extraction_requires(self, answer_type):
        instruction = answer_format_instruction(spec_for(answer_type, "x"))
        assert TaggedAnswer.OPEN in instruction
        assert TaggedAnswer.CLOSE in instruction

    @pytest.mark.parametrize(
        "answer_type", ["python_literal", "integer", "short_text"]
    )
    def test_the_worked_example_in_the_instruction_actually_parses(self, answer_type):
        instruction = answer_format_instruction(spec_for(answer_type, "x"))
        example = instruction.split("For example: ")[1].rstrip(".")
        assert TaggedAnswer.extract(example) != "", f"{answer_type} example does not parse"


class TestSpecsBuildFromRealRows:
    def test_cruxeval_rows_become_gradeable_specs(self):
        rows = [{"id": "sample_0", "code": "def f(x):\n    return x + 1", "input": "1",
                 "output": "2"}]
        (spec,) = _cruxeval_specs(rows)
        assert spec.suite == "cruxeval" and spec.domain == "code_reasoning"
        assert "def f(x)" in spec.prompt and "f(1)" in spec.prompt
        assert build_evaluator(spec).score("[ANSWER]2[/ANSWER]")

    def test_aime_rows_become_gradeable_specs(self):
        rows = [{"ID": "2024-II-4", "Problem": "Find n.", "Answer": "33"}]
        (spec,) = _aime_specs(rows, year_tag="2024")
        assert spec.task_id == "aime::2024::2024-II-4"
        assert build_evaluator(spec).score("[ANSWER]33[/ANSWER]")

    def test_exploretom_keeps_only_false_belief_stories(self):
        rows = [
            {"infilled_story": "s1", "question": "q", "expected_answer": "box",
             "sprop=is_false_belief_story_1st_and_2nd": True, "sprop=global_idx": 1},
            {"infilled_story": "s2", "question": "q", "expected_answer": "box",
             "sprop=is_false_belief_story_1st_and_2nd": False, "sprop=global_idx": 2},
        ]
        kept = _exploretom_specs(rows, false_belief_only=True)
        assert len(kept) == 1
        assert kept[0].payload["false_belief"] is True
        assert len(_exploretom_specs(rows, false_belief_only=False)) == 2

    def test_rows_missing_ground_truth_are_dropped_not_scored_zero(self):
        assert _cruxeval_specs([{"id": "x", "code": "def f(): pass", "output": ""}]) == []
        assert _aime_specs([{"ID": "x", "Problem": "p", "Answer": ""}], year_tag="2024") == []
