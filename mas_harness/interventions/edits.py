"""Causal interventions as edits to the answer bank.

The research report's causal claims rest on ``do(.)`` operations: mask a message, substitute
a correct one, permute speaking order, and compare the resulting decision against the
observational episode. Because Stage B replays a fixed bank, an intervention is a cheap edit
to that bank rather than a new round of generation. The observational and interventional
episodes therefore differ in exactly the intended way and in nothing else — same task, same
seed, same untouched members' text.

Influence for agent ``i`` under protocol ``g`` is then the flip rate

    I_i(x, g) = 1[ decision(bank) != decision(do(mask message_i) bank) ]

which is a genuine causal quantity on this design, unlike a correlation between speaking and
outcome.

Three families are implemented:

``mask``
    Remove a member's message. The member is still in the coalition and still counted in the
    denominator, but contributes nothing. This measures how much the decision depended on
    that member being heard.
``substitute_correct`` / ``substitute_wrong``
    Replace a member's message with one carrying a known-correct or known-wrong answer,
    drawn from a real banked answer where possible. Measures whether the protocol can pick up
    a correct answer injected at a given position — the report's "evidence-complete message"
    test.
``reorder``
    Permute the order members are presented in. Measures position effects, which are a
    property of the protocol rather than of any agent.
"""

from __future__ import annotations

import random
from typing import Iterable, Sequence

from ..records.schema import AnswerRecord, InterventionSpec
from ..tasks.adapters import TaskSpec

# What a masked member's message becomes. Explicit rather than an empty string, so a reader
# of the transcript can tell a masked turn from a model that returned nothing, and so the
# strict extractor records it as an abstention rather than a vote (D-011).
MASKED_TEXT = "(this member did not speak)"


def apply(
    bank: dict[int, AnswerRecord],
    spec: InterventionSpec,
    *,
    task: TaskSpec,
    donor_pool: Sequence[AnswerRecord] | None = None,
    seed: int = 0,
) -> dict[int, AnswerRecord]:
    """Return an edited copy of ``bank``. The input is never mutated.

    Not mutating matters: the same bank object is reused across every protocol and every
    intervention for a task, so an in-place edit would silently contaminate later episodes.
    """
    if spec.kind == "none":
        return dict(bank)

    edited = dict(bank)

    if spec.kind == "reorder":
        # Order is consumed by ProtocolContext.speaking_order(); the bank itself is unchanged.
        return edited

    target = spec.target_agent_id
    if target is None:
        raise ValueError(f"intervention {spec.kind!r} requires target_agent_id")
    if target not in edited:
        raise ValueError(
            f"intervention targets agent {target}, which is not in the bank "
            f"(members: {sorted(edited)})"
        )

    original = edited[target]

    if spec.kind == "mask":
        edited[target] = original.model_copy(
            update={
                "text": MASKED_TEXT,
                "extracted_answer": "",
                "correct": False,
                "parse_failed": True,
            }
        )
        return edited

    if spec.kind in ("substitute_correct", "substitute_wrong"):
        want_correct = spec.kind == "substitute_correct"
        donor = _pick_donor(
            donor_pool or [],
            task=task,
            want_correct=want_correct,
            exclude_agent_id=target,
            seed=seed,
        )
        if donor is not None:
            text, answer = donor.text, donor.extracted_answer
        else:
            text, answer = _synthesize(task, want_correct=want_correct)
        edited[target] = original.model_copy(
            update={
                "text": text,
                "extracted_answer": answer,
                "correct": want_correct,
                "parse_failed": not answer,
            }
        )
        return edited

    raise ValueError(f"unknown intervention kind {spec.kind!r}")


def _pick_donor(
    donor_pool: Iterable[AnswerRecord],
    *,
    task: TaskSpec,
    want_correct: bool,
    exclude_agent_id: int,
    seed: int,
) -> AnswerRecord | None:
    """A real banked answer of the requested correctness for this task.

    Using a real answer keeps the substituted message stylistically in-distribution. A
    hand-written stub would differ from genuine model output in length, hedging and format,
    any of which could drive the flip rate for reasons unrelated to the answer it carries.
    """
    candidates = [
        record
        for record in donor_pool
        if record.task_id == task.task_id
        and record.agent_id != exclude_agent_id
        and bool(record.correct) == want_correct
        and record.extracted_answer
    ]
    if not candidates:
        return None
    return random.Random(f"{task.task_id}:{exclude_agent_id}:{seed}").choice(
        sorted(candidates, key=lambda r: (r.agent_id, r.seed))
    )


def _synthesize(task: TaskSpec, *, want_correct: bool) -> tuple[str, str]:
    """Fallback message when no real donor of the required correctness exists.

    Flagged by callers via ``InterventionSpec.detail`` so that episodes relying on a
    synthesized message can be excluded from the influence estimates if needed.
    """
    answer = task.ground_truth if want_correct else _plausible_wrong_answer(task)
    if task.answer_type == "choice":
        body = (
            "Working through the options, this one is the consistent choice. "
            f"The answer is '{answer}'."
        )
    else:
        body = f"Following the calculation through, the result is \\boxed{{{answer}}}."
    return body, answer


def _plausible_wrong_answer(task: TaskSpec) -> str:
    if task.answer_type == "choice":
        letters = "ABCDEFGHIJ"
        n_options = len(task.payload.get("options") or []) or 4
        for letter in letters[:n_options]:
            if letter != task.ground_truth.upper():
                return letter
        return "A"
    # For math, perturb rather than invent, so the wrong answer stays type-correct.
    try:
        return str(float(task.ground_truth) + 1)
    except (TypeError, ValueError):
        return f"{task.ground_truth} + 1"


# ---- enumeration ------------------------------------------------------------------------


def mask_interventions(coalition: Sequence[int]) -> list[InterventionSpec]:
    """One masking intervention per member: the per-agent influence sweep."""
    return [
        InterventionSpec(kind="mask", target_agent_id=agent_id, detail="single-member mask")
        for agent_id in sorted(coalition)
    ]


def substitution_interventions(
    coalition: Sequence[int], *, correct: bool = True
) -> list[InterventionSpec]:
    kind = "substitute_correct" if correct else "substitute_wrong"
    return [
        InterventionSpec(kind=kind, target_agent_id=agent_id, detail="donor-sourced message")
        for agent_id in sorted(coalition)
    ]


def reorder_interventions(
    coalition: Sequence[int], *, n_permutations: int = 2, seed: int = 0
) -> list[InterventionSpec]:
    """A few distinct permutations, always including the exact reversal.

    The reversal is included deliberately: it is the single permutation most likely to reveal
    a primacy or recency effect, so a small budget spent there is better than the same budget
    spent on random draws.
    """
    members = list(coalition)
    if len(members) < 2:
        return []

    specs: list[InterventionSpec] = [
        InterventionSpec(kind="reorder", order=list(reversed(members)), detail="reversal")
    ]
    rng = random.Random(seed)
    seen = {tuple(members), tuple(reversed(members))}
    attempts = 0
    while len(specs) < n_permutations and attempts < 50:
        attempts += 1
        candidate = members[:]
        rng.shuffle(candidate)
        if tuple(candidate) not in seen:
            seen.add(tuple(candidate))
            specs.append(
                InterventionSpec(kind="reorder", order=candidate, detail="random permutation")
            )
    return specs


def intervention_plan(
    coalition: Sequence[int],
    *,
    include_masks: bool = True,
    include_substitutions: bool = True,
    include_reorder: bool = True,
    n_permutations: int = 2,
    seed: int = 0,
) -> list[InterventionSpec]:
    """The observational episode plus every requested counterfactual.

    The observational episode is always first, because every intervention is scored as a
    difference against it and a missing baseline makes the whole set unusable.
    """
    plan = [InterventionSpec(kind="none")]
    if include_masks:
        plan.extend(mask_interventions(coalition))
    if include_substitutions:
        plan.extend(substitution_interventions(coalition, correct=True))
    if include_reorder:
        plan.extend(reorder_interventions(coalition, n_permutations=n_permutations, seed=seed))
    return plan
