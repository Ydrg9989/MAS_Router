"""Expert-centred protocols: the predicted expert plus a reviewer.

Protocol 5 of the research report, and the place where the governance question is sharpest.
``single_expert`` measures what the predicted expert achieves alone; ``expert_verifier``
adds exactly one reviewer and nothing else. The difference between them is attributable to
the review, so rescue (a wrong expert corrected) and dilution (a right expert talked out of
it) are separable rather than entangled with a full debate.

The verifier is chosen from the coalition, never from ground truth. When the pool defines an
agent with the ``verifier`` role that agent is used; otherwise the most competent non-expert
member is, and which rule fired is recorded.
"""

from __future__ import annotations

from ..records.schema import TurnRecord
from .base import (
    ProtocolContext,
    ProtocolResult,
    bank_turns,
    call_record_from_response,
    expert_revision_prompt,
    register,
    verifier_prompt,
)

# Exact reply we instruct the verifier to use when it finds nothing wrong. Matching it lets
# us separate "reviewed and approved" from "reviewed and objected" without an LLM judge.
NO_ERROR_SENTINEL = "NO ERROR FOUND"


def _select_expert(context: ProtocolContext) -> tuple[int, bool]:
    expert_id = context.predicted_expert_id
    if expert_id is not None and expert_id in context.bank:
        return expert_id, False
    return max(context.coalition, key=lambda a: (context.competence.get(a, 0.0), -a)), True


def _select_verifier(context: ProtocolContext, expert_id: int) -> tuple[int | None, str]:
    others = [a for a in context.coalition if a != expert_id]
    if not others:
        return None, "no_other_member"
    designated = [a for a in others if context.agent(a).role == "verifier"]
    if designated:
        return max(designated, key=lambda a: (context.competence.get(a, 0.0), -a)), "role"
    return max(others, key=lambda a: (context.competence.get(a, 0.0), -a)), "competence"


@register(
    "expert_verifier",
    description=(
        "The predicted expert's banked answer is reviewed by one other member, then the "
        "expert may revise. Two model calls. Isolates the effect of a single review from "
        "the effect of a full debate, so rescue and dilution are separately identifiable."
    ),
    calls_per_episode=lambda coalition_size, rounds: 2 if coalition_size > 1 else 0,
    observability=(
        "The verifier sees the task and the expert's full answer, but not who wrote it and "
        "not any other member's answer. The expert then sees the critique but not the "
        "verifier's identity. Neither sees ground truth or competence estimates."
    ),
    uses_predicted_expert=True,
    interactive=True,
)
async def expert_verifier(context: ProtocolContext) -> ProtocolResult:
    expert_id, used_fallback = _select_expert(context)
    verifier_id, verifier_rule = _select_verifier(context, expert_id)
    expert = context.agent(expert_id)
    candidate = context.bank[expert_id]

    transcript = bank_turns(context, [expert_id])

    if verifier_id is None:
        # A singleton coalition has nobody to review, so this degenerates to single_expert
        # and must cost nothing rather than inventing a reviewer.
        return ProtocolResult(
            final_text=candidate.text,
            final_answer=candidate.extracted_answer,
            transcript=transcript,
            calls=[],
            meta={
                "expert_agent_id": expert_id,
                "verifier_agent_id": None,
                "verifier_selection_rule": verifier_rule,
                "used_competence_fallback": used_fallback,
                "degenerate_singleton": True,
                "n_model_calls": 0,
            },
        )

    client = context.require_client("expert_verifier")
    verifier = context.agent(verifier_id)

    critique_response = await client.chat(
        model=verifier.model,
        messages=verifier_prompt(context, verifier, candidate_text=candidate.text),
        provider=verifier.provider,
        temperature=verifier.temperature,
        max_tokens=verifier.max_tokens,
        seed=context.seed,
        extra_body=verifier.extra_body or None,
    )
    critique = critique_response.text
    transcript.append(
        TurnRecord(
            speaker_id=verifier_id, role="verifier", stage="verify", content=critique
        )
    )
    calls = [
        call_record_from_response(
            critique_response, stage="verify", agent_id=verifier_id, model=verifier.model
        )
    ]

    objected = NO_ERROR_SENTINEL.lower() not in critique.lower()

    if not objected:
        # No objection: the expert's answer stands and the second call is skipped, which
        # keeps cost proportional to how much reviewing actually happened.
        return ProtocolResult(
            final_text=candidate.text,
            final_answer=candidate.extracted_answer,
            transcript=transcript,
            calls=calls,
            meta={
                "expert_agent_id": expert_id,
                "verifier_agent_id": verifier_id,
                "verifier_selection_rule": verifier_rule,
                "used_competence_fallback": used_fallback,
                "verifier_objected": False,
                "expert_changed_answer": False,
                "expert_initial_answer": candidate.extracted_answer,
                "n_model_calls": 1,
            },
        )

    revision_response = await client.chat(
        model=expert.model,
        messages=expert_revision_prompt(context, expert, critique=critique),
        provider=expert.provider,
        temperature=expert.temperature,
        max_tokens=expert.max_tokens,
        seed=context.seed,
        extra_body=expert.extra_body or None,
    )
    transcript.append(
        TurnRecord(
            speaker_id=expert_id,
            role=expert.role,
            stage="expert_revision",
            content=revision_response.text,
        )
    )
    calls.append(
        call_record_from_response(
            revision_response, stage="expert_revision", agent_id=expert_id, model=expert.model
        )
    )

    final_answer = context.evaluator.extract(revision_response.text)
    return ProtocolResult(
        final_text=revision_response.text,
        final_answer=final_answer,
        transcript=transcript,
        calls=calls,
        meta={
            "expert_agent_id": expert_id,
            "verifier_agent_id": verifier_id,
            "verifier_selection_rule": verifier_rule,
            "used_competence_fallback": used_fallback,
            "verifier_objected": True,
            "expert_initial_answer": candidate.extracted_answer,
            "expert_changed_answer": final_answer != candidate.extracted_answer,
            "n_model_calls": 2,
        },
    )
