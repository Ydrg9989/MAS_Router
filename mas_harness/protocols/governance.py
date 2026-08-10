"""Protocols 6 and 7: the report's proposed governance interventions.

Protocols 1-5 are baselines that describe how existing systems allocate influence. These two
are the contribution: each changes *who decides* rather than who speaks, and each is designed
so the change is measurable against a baseline that differs in exactly one rule.

``expert_veto``
    Paired against ``expert_verifier``. Both spend one verifier call on the same candidate
    answer; they differ only in who holds the last word. Under ``expert_verifier`` the expert
    adjudicates the objection, so authority is unconditional. Under ``expert_veto`` a
    challenge that meets a stated evidence bar is upheld mechanically, so authority is
    conditional on surviving evidence. Comparing the two isolates the decision rule from the
    review itself, which no amount of prompt tuning can do.

``chair_information_seeking``
    Paired against ``independent_judge``. Both end with a neutral non-participant choosing the
    final answer from the same banked responses; the chair may first ask one targeted question.
    The difference is therefore attributable to *soliciting* evidence, which is the mechanism
    the report needs for distributed-information tasks where the deciding fact is held
    privately and never volunteered.

Both keep the decision rule out of the model's hands wherever it can be decided
deterministically. Whether a challenge met the bar, and which members the chair asked, are
resolved by extraction and string matching, not by a second model interpreting the first.
"""

from __future__ import annotations

import re

from ..records.schema import TurnRecord
from .base import (
    AGGREGATOR,
    ASK_PREFIX,
    CONCEDE_SENTINEL,
    NO_QUESTION_SENTINEL,
    QUESTION_PREFIX,
    ProtocolContext,
    ProtocolResult,
    bank_turns,
    call_record_from_response,
    chair_decision_prompt,
    chair_query_prompt,
    chair_response_prompt,
    counterevidence_prompt,
    format_peer_answers,
    register,
)
from .expert import _select_expert, _select_verifier
from .voting import tally

# Upper bound on how many members the chair may question in one episode. The chair can ask
# fewer; it cannot ask more. Without a cap, a chair that names everyone turns a 3-call
# protocol into an n+2-call one and the cost planner's estimate stops being an estimate.
MAX_RESPONDENTS = 2

_MEMBER_LABEL = re.compile(r"member\s*(\d+)", re.IGNORECASE)


# ---- protocol 6: expert veto ---------------------------------------------------------------


@register(
    "expert_veto",
    description=(
        "The predicted expert's answer stands unless a challenger both identifies a specific "
        "error and names a different answer. One model call. Paired with expert_verifier, "
        "which spends the same call but gives the expert the last word, so the pair isolates "
        "the decision rule from the review."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1 if coalition_size > 1 else 0,
    observability=(
        "The challenger sees the task and the expert's full answer, anonymized, and is told "
        "that the answer stands by default. It does not see other members' answers, the "
        "expert's identity, competence estimates, or ground truth. The expert is not consulted "
        "again, so it never sees the challenge."
    ),
    uses_predicted_expert=True,
    interactive=True,
)
async def expert_veto(context: ProtocolContext) -> ProtocolResult:
    expert_id, used_fallback = _select_expert(context)
    challenger_id, challenger_rule = _select_verifier(context, expert_id)
    candidate = context.bank[expert_id]
    transcript = bank_turns(context, [expert_id])

    base_meta = {
        "expert_agent_id": expert_id,
        "challenger_agent_id": challenger_id,
        "challenger_selection_rule": challenger_rule,
        "used_competence_fallback": used_fallback,
        "expert_initial_answer": candidate.extracted_answer,
    }

    if challenger_id is None:
        # Nobody to challenge, so the veto is vacuous and must cost nothing.
        return ProtocolResult(
            final_text=candidate.text,
            final_answer=candidate.extracted_answer,
            transcript=transcript,
            calls=[],
            meta={
                **base_meta,
                "degenerate_singleton": True,
                "challenge_attempted": False,
                "veto_upheld": False,
                "n_model_calls": 0,
            },
        )

    client = context.require_client("expert_veto")
    challenger = context.agent(challenger_id)

    response = await client.chat(
        model=challenger.model,
        messages=counterevidence_prompt(context, challenger, candidate_text=candidate.text),
        provider=challenger.provider,
        temperature=challenger.temperature,
        max_tokens=challenger.max_tokens,
        seed=context.seed,
        extra_body=challenger.extra_body or None,
    )
    transcript.append(
        TurnRecord(
            speaker_id=challenger_id,
            role="verifier",
            stage="challenge",
            content=response.text,
        )
    )
    calls = [
        call_record_from_response(
            response, stage="challenge", agent_id=challenger_id, model=challenger.model
        )
    ]

    conceded = CONCEDE_SENTINEL.lower() in response.text.lower()
    proposed = "" if conceded else context.evaluator.extract(response.text)
    # Three ways a challenge fails, all recorded separately: it conceded, it stated no
    # alternative, or its alternative was the expert's answer restated.
    differs = bool(proposed) and not context.evaluator.equivalent(
        proposed, candidate.extracted_answer
    )
    upheld = not conceded and differs

    final_text = response.text if upheld else candidate.text
    final_answer = proposed if upheld else candidate.extracted_answer

    return ProtocolResult(
        final_text=final_text,
        final_answer=final_answer,
        transcript=transcript,
        calls=calls,
        meta={
            **base_meta,
            "challenge_attempted": True,
            "challenger_conceded": conceded,
            "challenger_proposed_answer": proposed,
            "challenge_named_alternative": differs,
            "veto_upheld": upheld,
            "expert_changed_answer": final_answer != candidate.extracted_answer,
            "n_model_calls": 1,
        },
    )


# ---- protocol 7: information-seeking chair -------------------------------------------------


def parse_chair_query(text: str, *, order: list[int]) -> tuple[str, list[int]]:
    """Extract the chair's question and the members it named.

    Positional labels are mapped back through ``order``, which is the same order the chair was
    shown, so a reordering intervention permutes who "Member 1" refers to exactly as intended.
    An out-of-range label is dropped rather than clamped: silently redirecting a question to a
    different agent would corrupt the very quantity we are measuring.
    """
    if NO_QUESTION_SENTINEL.lower() in text.lower():
        return "", []

    question = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(QUESTION_PREFIX):
            question = stripped[len(QUESTION_PREFIX) :].strip()
            break
    if not question:
        # The chair answered in prose. Take the first non-empty line rather than discarding a
        # question that was asked in a format we did not dictate.
        question = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not question:
        return "", []

    ask_line = next(
        (line for line in text.splitlines() if line.strip().upper().startswith(ASK_PREFIX)), ""
    )
    positions = [int(match) for match in _MEMBER_LABEL.findall(ask_line)]
    targets: list[int] = []
    for position in positions:
        if 1 <= position <= len(order):
            agent_id = order[position - 1]
            if agent_id not in targets:
                targets.append(agent_id)
    # A question with no valid addressee is put to everyone: the chair asked for information,
    # and dropping the question because the label was malformed would understate the protocol.
    return question, (targets or list(order))[:MAX_RESPONDENTS]


@register(
    "chair_information_seeking",
    description=(
        "A neutral chair reads the independent answers, may ask one targeted question of up "
        "to two members, then decides. Two to four model calls. Paired with "
        "independent_judge, which decides from the same answers without asking, so the pair "
        "isolates the value of soliciting evidence that was never volunteered."
    ),
    calls_per_episode=lambda coalition_size, rounds: 2
    + min(coalition_size, MAX_RESPONDENTS),
    observability=(
        "The chair sees the task and every member's full response, anonymized to positional "
        "labels, and later the replies to its question. A queried member sees the task, its "
        "own prior answer and the question, but not other members' answers and not who else "
        "was asked. Nobody sees ground truth or competence estimates."
    ),
    interactive=True,
)
async def chair_information_seeking(context: ProtocolContext) -> ProtocolResult:
    client = context.require_client("chair_information_seeking")
    chair = context.pool.aggregator
    if chair is None:
        raise ValueError(
            f"pool {context.pool.pool_id!r} defines no aggregator, which "
            f"'chair_information_seeking' uses as the chair. Add an `aggregator:` block to "
            f"the pool YAML."
        )

    order = context.speaking_order()
    peer_block = format_peer_answers(context, visible=order, anonymize=True)
    transcript = bank_turns(context, order)

    query_response = await client.chat(
        model=chair.model,
        messages=chair_query_prompt(context, peer_block=peer_block),
        provider=chair.provider,
        temperature=chair.temperature,
        max_tokens=chair.max_tokens,
        seed=context.seed,
        extra_body=chair.extra_body or None,
    )
    calls = [
        call_record_from_response(
            query_response, stage="chair_query", agent_id=AGGREGATOR, model=chair.model
        )
    ]
    transcript.append(
        TurnRecord(
            speaker_id=AGGREGATOR,
            role="chair",
            stage="chair_query",
            content=query_response.text,
        )
    )

    question, targets = parse_chair_query(query_response.text, order=order)

    replies: dict[int, str] = {}
    for agent_id in targets:
        member = context.agent(agent_id)
        reply = await client.chat(
            model=member.model,
            messages=chair_response_prompt(context, member, question=question),
            provider=member.provider,
            temperature=member.temperature,
            max_tokens=member.max_tokens,
            seed=context.seed,
            extra_body=member.extra_body or None,
        )
        replies[agent_id] = reply.text
        calls.append(
            call_record_from_response(
                reply, stage="chair_reply", agent_id=agent_id, model=member.model
            )
        )
        transcript.append(
            TurnRecord(
                speaker_id=agent_id,
                role=member.role,
                stage="chair_reply",
                content=reply.text,
            )
        )

    evidence_block = (
        "\n\n".join(
            f"--- Member {order.index(agent_id) + 1} replied ---\n{text.strip() or '(no reply)'}"
            for agent_id, text in replies.items()
        )
        if replies
        else "(you asked for no further evidence)"
    )
    decision_response = await client.chat(
        model=chair.model,
        messages=chair_decision_prompt(
            context, peer_block=peer_block, evidence_block=evidence_block
        ),
        provider=chair.provider,
        temperature=chair.temperature,
        max_tokens=chair.max_tokens,
        seed=context.seed,
        extra_body=chair.extra_body or None,
    )
    calls.append(
        call_record_from_response(
            decision_response, stage="chair_decision", agent_id=AGGREGATOR, model=chair.model
        )
    )
    transcript.append(
        TurnRecord(
            speaker_id=AGGREGATOR,
            role="chair",
            stage="chair_decision",
            content=decision_response.text,
        )
    )

    final_answer = context.evaluator.extract(decision_response.text)
    vote = tally(
        {a: context.bank[a].extracted_answer for a in order},
        context.evaluator,
        competence=context.competence,
    )

    return ProtocolResult(
        final_text=decision_response.text,
        final_answer=final_answer,
        transcript=transcript,
        calls=calls,
        meta={
            "chair_model": chair.model,
            "visible_order": order,
            "asked_question": bool(question),
            "question": question,
            "query_targets": targets,
            # Whether the chair questioned the member the calibration says is strongest. A
            # chair that never does is misallocating attention, which is the same failure the
            # governance metrics measure for influence.
            "queried_predicted_expert": context.predicted_expert_id in targets,
            "n_respondents": len(replies),
            "vote_would_have_said": vote.winner,
            "chair_overrode_vote": final_answer != vote.winner,
            "n_model_calls": len(calls),
        },
    )
