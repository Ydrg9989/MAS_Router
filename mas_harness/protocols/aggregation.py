"""Protocols that aggregate the answer bank without any agent interaction.

Protocols 1, 2 and 4 of the research report. The first two make no model calls at all
(D-009), which is the reason the whole two-stage design pays for itself: two of the five
MVP protocols are free once Stage A exists, and they are the baselines every other
protocol is measured against.
"""

from __future__ import annotations

from ..records.schema import TurnRecord
from .base import (
    AGGREGATOR,
    ProtocolContext,
    ProtocolResult,
    bank_turns,
    call_record_from_response,
    format_peer_answers,
    judge_prompt,
    register,
)
from .voting import majority_threshold_met, tally


@register(
    "single_expert",
    description=(
        "The predicted expert answers alone. No interaction. This is the calibrated "
        "top-1 routing baseline: if no protocol beats it, team structure is not buying "
        "anything and the governance question is moot."
    ),
    calls_per_episode=lambda coalition_size, rounds: 0,
    observability="The expert sees only the task. No member observes any other member.",
    uses_predicted_expert=True,
)
async def single_expert(context: ProtocolContext) -> ProtocolResult:
    expert_id = context.predicted_expert_id
    if expert_id is None or expert_id not in context.bank:
        # Fall back to the most competent available member rather than failing the episode,
        # and record that this happened so it is never mistaken for a real prediction.
        expert_id = max(
            context.coalition, key=lambda a: (context.competence.get(a, 0.0), -a)
        )
        fallback = True
    else:
        fallback = False

    record = context.bank[expert_id]
    return ProtocolResult(
        final_text=record.text,
        final_answer=record.extracted_answer,
        transcript=bank_turns(context, [expert_id]),
        calls=[],
        meta={
            "selected_agent_id": expert_id,
            "predicted_expert_id": context.predicted_expert_id,
            "used_competence_fallback": fallback,
            "n_model_calls": 0,
        },
    )


@register(
    "independent_majority",
    description=(
        "Plurality vote over the independent answers, with answers grouped by task "
        "equivalence and abstentions excluded. Ties break on summed calibration "
        "competence. No interaction, so no influence: this isolates aggregation from "
        "persuasion."
    ),
    calls_per_episode=lambda coalition_size, rounds: 0,
    observability=(
        "No member observes any other member. The aggregation is mechanical and sees only "
        "the extracted answers."
    ),
)
async def independent_majority(context: ProtocolContext) -> ProtocolResult:
    answers = {a: context.bank[a].extracted_answer for a in context.coalition}
    result = tally(answers, context.evaluator, competence=context.competence)

    winner_text = ""
    if result.winner_support:
        winner_text = context.bank[min(result.winner_support)].text

    return ProtocolResult(
        final_text=winner_text,
        final_answer=result.winner,
        transcript=bank_turns(context, context.speaking_order()),
        calls=[],
        meta={
            **result.to_meta(),
            "absolute_majority": majority_threshold_met(result),
            "n_model_calls": 0,
        },
    )


@register(
    "independent_judge",
    description=(
        "A neutral aggregator that did not attempt the task reads every independent "
        "answer and picks the final one. One model call. Tests whether an outside reader "
        "can recognise the correct answer that a vote would have discarded."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1,
    observability=(
        "The judge sees the task and every member's full response, anonymized to "
        "positional labels. Members see nothing."
    ),
)
async def independent_judge(context: ProtocolContext) -> ProtocolResult:
    client = context.require_client("independent_judge")
    aggregator = context.pool.aggregator
    if aggregator is None:
        raise ValueError(
            f"pool {context.pool.pool_id!r} defines no aggregator, which "
            f"'independent_judge' requires. Add an `aggregator:` block to the pool YAML."
        )

    order = context.speaking_order()
    peer_block = format_peer_answers(context, visible=order, anonymize=True)
    messages = judge_prompt(context, peer_block=peer_block)

    response = await client.chat(
        model=aggregator.model,
        messages=messages,
        provider=aggregator.provider,
        temperature=aggregator.temperature,
        max_tokens=aggregator.max_tokens,
        seed=context.seed,
        extra_body=aggregator.extra_body or None,
    )

    # Recorded for comparison: what a mechanical vote would have concluded on the same
    # answers. The judge-versus-vote difference is the quantity of interest.
    vote = tally(
        {a: context.bank[a].extracted_answer for a in order},
        context.evaluator,
        competence=context.competence,
    )

    transcript = bank_turns(context, order)
    transcript.append(
        TurnRecord(
            speaker_id=AGGREGATOR,
            role="aggregator",
            stage="judge",
            content=response.text,
        )
    )

    final_answer = context.evaluator.extract(response.text)
    return ProtocolResult(
        final_text=response.text,
        final_answer=final_answer,
        transcript=transcript,
        calls=[
            call_record_from_response(
                response, stage="judge", agent_id=AGGREGATOR, model=aggregator.model
            )
        ],
        meta={
            "aggregator_model": aggregator.model,
            "visible_order": order,
            "vote_would_have_said": vote.winner,
            "vote_counts": vote.counts,
            "judge_overrode_vote": final_answer != vote.winner,
            "n_model_calls": 1,
        },
    )
