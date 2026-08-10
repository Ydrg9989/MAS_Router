"""Debate then vote: protocol 3 of the research report.

Round 0 is the banked independent answers, injected free of charge. Each subsequent round
has every member revise in light of what the others said, then the final positions are
tallied. The comparison against ``independent_majority`` on the *same* bank is what isolates
the effect of interaction from the effect of aggregation: both protocols see identical
round-0 answers, so any difference is caused by the discussion.

Cost is ``coalition_size * (rounds - 1)`` model calls, which makes this the most expensive
MVP protocol and the reason the report caps rounds at two.

Members revise simultaneously within a round rather than sequentially. Sequential revision
would confound the protocol with speaking order on every round; order is manipulated
deliberately by the reorder intervention instead.
"""

from __future__ import annotations

import asyncio

from ..records.schema import TurnRecord
from .base import (
    ProtocolContext,
    ProtocolResult,
    bank_turns,
    call_record_from_response,
    format_peer_answers,
    register,
    revision_prompt,
)
from .voting import majority_threshold_met, tally


@register(
    "debate_vote",
    description=(
        "Members see each other's independent answers, revise once per round, then vote on "
        "final positions. Round 0 is replayed free from the answer bank; only revisions cost "
        "money. Revision is simultaneous within a round, so speaking order is not a hidden "
        "variable."
    ),
    calls_per_episode=lambda coalition_size, rounds: coalition_size * max(0, rounds - 1),
    observability=(
        "Each member sees the task, its own previous answer, and every other member's "
        "previous answer under anonymized positional labels. No member sees ground truth or "
        "any competence estimate."
    ),
    interactive=True,
)
async def debate_vote(context: ProtocolContext) -> ProtocolResult:
    client = context.require_client("debate_vote")
    order = context.speaking_order()

    transcript = bank_turns(context, order)
    calls = []
    # Current position per agent, seeded from the bank and updated each round.
    positions = {a: context.bank[a].extracted_answer for a in order}
    position_texts = {a: context.bank[a].text for a in order}
    round_history: list[dict] = [
        {"round": 0, "answers": dict(positions), "changed": []},
    ]

    async def revise(agent_id: int, round_index: int, seen: dict[int, str]):
        """One member's revision. ``seen`` is the previous round's positions, not the bank."""
        agent = context.agent(agent_id)
        peers = [a for a in order if a != agent_id]
        response = await client.chat(
            model=agent.model,
            messages=revision_prompt(
                context,
                agent,
                peer_block=format_peer_answers(
                    context, visible=peers, anonymize=True, texts=seen
                ),
                round_index=round_index,
                own_text=seen[agent_id],
            ),
            provider=agent.provider,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            seed=context.seed,
            extra_body=agent.extra_body or None,
        )
        return agent_id, response

    for round_index in range(1, max(1, context.max_rounds)):
        # Snapshot the positions so simultaneous revision really is simultaneous: every member
        # in this round sees the same state, whatever order the coroutines happen to finish in.
        seen = dict(position_texts)
        results = await asyncio.gather(*(revise(a, round_index, seen) for a in order))

        changed = []
        for agent_id, response in results:
            agent = context.agent(agent_id)
            new_answer = context.evaluator.extract(response.text)
            if new_answer != positions[agent_id]:
                changed.append(agent_id)
            positions[agent_id] = new_answer
            position_texts[agent_id] = response.text
            transcript.append(
                TurnRecord(
                    speaker_id=agent_id,
                    role=agent.role,
                    stage=f"debate_round_{round_index}",
                    content=response.text,
                )
            )
            calls.append(
                call_record_from_response(
                    response,
                    stage=f"debate_round_{round_index}",
                    agent_id=agent_id,
                    model=agent.model,
                )
            )
        round_history.append(
            {"round": round_index, "answers": dict(positions), "changed": sorted(changed)}
        )

    result = tally(positions, context.evaluator, competence=context.competence)
    winner_text = (
        position_texts.get(min(result.winner_support), "") if result.winner_support else ""
    )

    initial = round_history[0]["answers"]
    n_switched = sum(1 for a in order if initial.get(a) != positions.get(a))

    return ProtocolResult(
        final_text=winner_text,
        final_answer=result.winner,
        transcript=transcript,
        calls=calls,
        meta={
            **result.to_meta(),
            "absolute_majority": majority_threshold_met(result),
            "rounds": context.max_rounds,
            "round_history": round_history,
            "n_agents_switched_answer": n_switched,
            "initial_answers": {str(k): v for k, v in sorted(initial.items())},
            "n_model_calls": len(calls),
        },
    )
