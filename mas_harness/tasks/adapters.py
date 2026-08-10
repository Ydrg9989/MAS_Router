"""Task specs and evaluators, built on the upstream ``teamwork`` task classes.

We use ``teamwork`` for the task description prompt, the ground truth, and — crucially —
the SymPy-backed answer equivalence check, which is the hardened part of that codebase and
which there is no reason to rewrite.

We do *not* call ``Task.execute()``: that method fuses the interaction protocol into the
task and re-collects independent answers on every invocation (D-001).

Three upstream behaviours are changed here:

* ``use_llm_fallback=False`` — upstream ``_check_equiv_with_llm`` issues an unlogged,
  uncosted ``gpt-5`` request from inside the scorer (D-003). :func:`build_evaluator`
  asserts the flag is off rather than trusting the default.
* ``decision_mode`` is irrelevant because we never run their collaboration loop; it is
  pinned to the no-op value so that constructing a task cannot trigger protocol logic.
* Multiple-choice extraction is re-implemented (D-011). The upstream terminal-letter rule
  in ``_normalize_answer`` is ``r'[\\(\\)]?([A-J])[\\)\\.\\:\\s]*$'``, which has no left
  word boundary, so it matches the final *character* of ordinary prose: "I have nothing to
  add." extracts "D" and "no answer at all here" extracts "E". Since ``_extract_answer``
  applies that rule to the whole message, an abstention silently becomes a confident vote.
  That is not survivable for this project — vote tallies, dilution and expert-utilization
  all depend on distinguishing "said nothing" from "voted wrong". :class:`StrictChoice`
  reproduces the upstream pattern ladder with proper token boundaries; the loose result is
  still recorded so the disagreement rate can be reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from teamwork.tasks.gpqa_diamond_problem_task import GPQADiamondProblemTask
from teamwork.tasks.math_500_problem_task import Math500ProblemTask
from teamwork.tasks.mmlu_pro_problem_task import MMLUProProblemTask

# Suites whose answers are a single letter, versus a boxed mathematical expression.
CHOICE_SUITES = frozenset({"gpqa_diamond", "mmlu_pro", "distributed_synth"})
MATH_SUITES = frozenset({"math500"})

_UPSTREAM_CLASSES: dict[str, type] = {
    "math500": Math500ProblemTask,
    "gpqa_diamond": GPQADiamondProblemTask,
    "mmlu_pro": MMLUProProblemTask,
    # The distributed-information substitute reuses the MMLU-Pro evaluator because its
    # answers are the same A-J letters (D-010).
    "distributed_synth": MMLUProProblemTask,
}


@dataclass(frozen=True)
class TaskSpec:
    """One task, fully specified and independent of any protocol or agent pool."""

    task_id: str
    suite: str
    domain: str
    answer_type: str  # "choice" | "boxed_math"
    prompt: str
    ground_truth: str
    # Raw upstream fields, kept so the evaluator can be rebuilt from a manifest alone.
    payload: dict[str, Any] = field(default_factory=dict)
    # Per-agent private evidence, used only by the distributed-information suite (D-010).
    hidden_context: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "suite": self.suite,
            "domain": self.domain,
            "answer_type": self.answer_type,
            "prompt": self.prompt,
            "ground_truth": self.ground_truth,
            "payload": self.payload,
            "hidden_context": self.hidden_context,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskSpec":
        return cls(
            task_id=payload["task_id"],
            suite=payload["suite"],
            domain=payload["domain"],
            answer_type=payload["answer_type"],
            prompt=payload["prompt"],
            ground_truth=payload["ground_truth"],
            payload=payload.get("payload", {}),
            hidden_context=payload.get("hidden_context", {}),
        )


class StrictChoice:
    """Multiple-choice extraction with token boundaries (D-011).

    The pattern ladder mirrors the upstream priority order, so it agrees with every fixture
    in ``tests/test_multiple_choice_eval.py``, but each letter group is bounded so it cannot
    match a letter embedded in a word.

    Returns the empty string for text that declares no answer. That is a meaningful
    outcome, not a failure to try: an agent that abstains must not be counted as voting.
    """

    # Highest priority: the phrasing our prompts explicitly mandate.
    MANDATED = re.compile(
        r"""the\s+answer\s+is\s*['"\u2018\u2019]?\s*([A-J])\b""", re.IGNORECASE
    )

    # Then the other explicit answer declarations, in upstream's order.
    DECLARED = (
        re.compile(r"""\b(?:final\s+answer|answer)\s*(?:is)?\s*[:=]\s*['"]?\s*([A-J])\b""", re.I),
        re.compile(r"""\b(?:option|choice)\s+['"]?\s*\(?\s*([A-J])\s*\)?\b""", re.I),
        re.compile(
            r"""\b(?:choose|select|pick|vote\s+for|going\s+with)\s+(?:option\s+|choice\s+)?"""
            r"""['"]?\s*\(?\s*([A-J])\s*\)?(?:\b|['"])""",
            re.I,
        ),
        re.compile(r"""\(\s*([A-J])\s*\)""", re.I),
    )

    # The whole message is just a letter, possibly parenthesized or punctuated.
    BARE = re.compile(r"""^\s*\(?\s*([A-J])\s*\)?\s*[\.\:]?\s*$""", re.IGNORECASE)

    # Last resort: a standalone letter token at the very end of the message. The leading
    # (?<![A-Za-z]) is exactly what the upstream rule is missing.
    TERMINAL = re.compile(
        r"""(?<![A-Za-z])\(?\s*([A-J])\s*\)?\s*[\.\:,;!]?\s*$""", re.IGNORECASE
    )

    @classmethod
    def extract(cls, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        if (match := cls.BARE.match(text)) is not None:
            return match.group(1).upper()

        # Take the last match: models revise themselves, and the final statement wins.
        for pattern in (cls.MANDATED, *cls.DECLARED):
            matches = pattern.findall(text)
            if matches:
                return matches[-1].upper()

        if (match := cls.TERMINAL.search(text)) is not None:
            return match.group(1).upper()
        return ""


class Evaluator(Protocol):
    """Deterministic answer extraction and scoring for one task."""

    def extract(self, text: str) -> str: ...

    def score(self, text: str) -> bool: ...


class TeamworkEvaluator:
    """Adapter exposing an upstream task's extraction and equivalence logic."""

    def __init__(self, spec: TaskSpec):
        self.spec = spec
        upstream_cls = _UPSTREAM_CLASSES.get(spec.suite)
        if upstream_cls is None:
            raise ValueError(
                f"no upstream evaluator for suite {spec.suite!r}; "
                f"known: {sorted(_UPSTREAM_CLASSES)}"
            )
        # agent_ids/max_rounds are required by the upstream constructor but only matter to
        # the collaboration loop, which we never run.
        self._task = upstream_cls(
            agent_ids=[0],
            max_rounds=1,
            problem_data=spec.payload,
            unique_id=spec.task_id,
            seed=0,
            decision_mode="expert_not_mentioned",
            use_llm_fallback=False,
        )
        # D-003: refuse to score if the judge path is somehow live.
        if getattr(self._task, "use_llm_fallback", False):
            raise AssertionError(
                "teamwork LLM-judge fallback is enabled; it issues uncosted gpt-5 calls "
                "from inside the scorer. See DECISIONS.md D-003."
            )
        self._task.llm_fallback_api_key = None

    def extract(self, text: str) -> str:
        """The authoritative extraction used for every correctness label.

        Multiple choice uses :class:`StrictChoice` (D-011). Boxed-math keeps the upstream
        extractor, whose fallback requires a trailing *number* rather than a trailing
        letter and so does not have the same failure mode.
        """
        if self.spec.answer_type == "choice":
            return StrictChoice.extract(text)
        return self.extract_loose(text)

    def extract_loose(self, text: str) -> str:
        """The upstream extractor, kept for diagnostics and for boxed-math answers."""
        try:
            return self._task._extract_answer(text or "")
        except Exception:
            # A malformed generation must produce a parse failure, never crash a run.
            return ""

    def extraction_diagnostics(self, text: str) -> dict[str, Any]:
        """Where strict and loose extraction disagree, so the rate can be reported."""
        strict = self.extract(text)
        loose = self.extract_loose(text)
        return {
            "strict": strict,
            "loose": loose,
            "disagree": strict != loose,
            # The dangerous direction: the loose extractor invented an answer.
            "loose_invented_answer": bool(loose and not strict),
        }

    def score(self, text: str) -> bool:
        return self.score_extracted(self.extract(text))

    def score_extracted(self, extracted: str) -> bool:
        """Score an already-extracted answer, for aggregating banked answers."""
        return self.equivalent(extracted, self.spec.ground_truth)

    def equivalent(self, first: str, second: str) -> bool:
        """The task's own equivalence relation between two extracted answers.

        Needed wherever two *answers* are compared rather than an answer against ground
        truth: grouping votes, and deciding whether a challenger actually named a different
        answer. String comparison would split ``1/2`` from ``0.5`` and systematically
        overstate disagreement on math tasks.

        An empty answer is an abstention, and an abstention is equivalent to nothing at all,
        including another abstention.
        """
        if not first or not second:
            return False
        try:
            return bool(self._task._is_equiv(first, second))
        except Exception:
            # A malformed answer must produce a non-match, never crash a run.
            return first.strip() == second.strip()


def build_evaluator(spec: TaskSpec) -> TeamworkEvaluator:
    """Build the deterministic evaluator for a task spec."""
    return TeamworkEvaluator(spec)


def answer_format_instruction(spec: TaskSpec) -> str:
    """The exact final-answer format we require, matched to the upstream extractor.

    The upstream regexes are tuned to specific phrasings — for multiple choice, the
    highest-priority pattern is literally ``the answer is 'X'``. Any protocol prompt that
    asks for a final answer must use this wording, or extraction silently degrades to the
    lower-priority fallback patterns.
    """
    if spec.answer_type == "choice":
        return (
            "End your response with EXACTLY this format: The answer is 'X' "
            "where X is the letter of the correct option."
        )
    return (
        "End your response with your final answer wrapped in \\boxed{}. "
        "For example: \\boxed{42}."
    )
