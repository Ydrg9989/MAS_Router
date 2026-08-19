"""Does the judge respect epistemic entitlement, or only credentials?

The distributed-information condition (D-010) makes peer wrongness *provable*: a member whose
visible option subset lacks the correct option cannot state it, so its answer carries no evidence
about the truth. The conformity literature manipulates credentials — authority roles (arXiv
2606.01637), expertise labels (2602.01011), measured accuracy (`protocols/conformity.py`) — and
finds models follow them regardless of correctness. None of it attaches the one label with a
computable optimal response: **evidence access**.

This module supplies that manipulation, as three arms over `independent_judge`:

``judge_access_labelled``
    Each member is annotated with the truth: whether the option subset it was shown contained the
    correct option. Under this label the optimal policy is computable — a member labelled as
    unable to see the correct option contributes nothing, so any deference to it is measurable
    over-deference.
``judge_access_inverted``
    The identical answers with the designations reassigned: the true holder is advertised as
    unable to know, and one deterministically chosen non-holder is advertised as the holder. The
    multiset of designations is unchanged. As in `conformity.py`, the inverted arm is what makes
    the study identifiable: truthful labels are collinear with the truth, and the pooled contrast
    separates following-the-label from weighing-the-evidence.
``judge_access_sets``
    No designation at all: each member is annotated with the option letters it was shown. The
    judge is given the access *structure* and must combine it with its own reading of the task.
    This arm separates "can use a conclusion handed to it" from "can reason about entitlement".

All three are otherwise `independent_judge` exactly — same aggregator, same prompt shape, same
single call, same banked answers, same speaking order — so contrasts are attributable to the
annotation, and all three refuse to run on non-distributed tasks rather than silently labelling
everyone a holder.
"""

from __future__ import annotations

import hashlib
from typing import Any, Sequence

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
from .voting import tally

# The two designation strings. Constants for the same reason as conformity.LABEL_TEMPLATE: the
# study rests on the judge attending to these exact words.
HOLDER_LABEL = "[this member's visible options DID include the correct answer]"
NON_HOLDER_LABEL = "[this member's visible options did NOT include the correct answer]"
SETS_TEMPLATE = "[this member was shown only options {}]"


def _distributed_meta(context: ProtocolContext) -> dict[str, Any]:
    meta = context.spec.payload.get("distributed")
    if not meta:
        raise ValueError(
            f"task {context.spec.task_id} carries no distributed payload; the entitlement "
            f"protocols are only defined where evidence access is a matter of construction."
        )
    return meta


def _false_holder(task_id: str, non_holders: Sequence[int]) -> int:
    """The non-holder advertised as the holder in the inverted arm.

    Deterministic in the task id alone so replays agree, and approximately balanced across
    positions over a suite, so the inverted designation is not confounded with one member.
    """
    digest = hashlib.sha256(task_id.encode("utf-8")).digest()
    return sorted(non_holders)[int.from_bytes(digest[:4], "big") % len(non_holders)]


def access_labels(
    context: ProtocolContext, order: Sequence[int], *, mode: str
) -> tuple[dict[int, str], dict[str, Any]]:
    """Annotation per member, plus the ground-truth record the analysis needs."""
    meta = _distributed_meta(context)
    holders = {int(a) for a in meta["holder_agent_ids"]}
    visible = {int(a): list(v) for a, v in meta["visible_by_agent_id"].items()}

    if mode == "sets":
        labels = {a: SETS_TEMPLATE.format(", ".join(visible[a])) for a in order}
        advertised = {a: (a in holders) for a in order}  # sets arm advertises nothing false
    elif mode in ("truthful", "inverted"):
        advertised = {a: (a in holders) for a in order}
        if mode == "inverted":
            non_holders = [a for a in order if a not in holders]
            false_holder = _false_holder(context.spec.task_id, non_holders)
            advertised = dict.fromkeys(order, False)
            advertised[false_holder] = True
        labels = {a: (HOLDER_LABEL if advertised[a] else NON_HOLDER_LABEL) for a in order}
    else:
        raise ValueError(f"unknown access-label mode {mode!r}")

    truth_record = {
        "true_holder_agent_ids": sorted(holders),
        "advertised_holder_agent_ids": sorted(a for a in order if advertised[a]),
        "visible_by_agent_id": {str(a): visible[a] for a in order},
        "label_mode": mode,
    }
    return labels, truth_record


async def _access_judge(context: ProtocolContext, *, mode: str) -> ProtocolResult:
    protocol_id = {
        "truthful": "judge_access_labelled",
        "inverted": "judge_access_inverted",
        "sets": "judge_access_sets",
    }[mode]
    client = context.require_client(protocol_id)
    aggregator = context.pool.aggregator
    if aggregator is None:
        raise ValueError(
            f"pool {context.pool.pool_id!r} defines no aggregator, which "
            f"{protocol_id!r} requires. Add an `aggregator:` block to the pool YAML."
        )

    order = context.speaking_order()
    labels, truth_record = access_labels(context, order, mode=mode)
    peer_block = format_peer_answers(
        context, visible=order, anonymize=True, competence_labels=labels
    )
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

    vote = tally(
        {a: context.bank[a].extracted_answer for a in order},
        context.evaluator,
        competence=context.competence,
    )

    transcript = bank_turns(context, order)
    transcript.append(
        TurnRecord(
            speaker_id=AGGREGATOR, role="aggregator", stage="judge", content=response.text
        )
    )

    return ProtocolResult(
        final_text=response.text,
        final_answer=context.evaluator.extract(response.text),
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
            **truth_record,
        },
    )


_OBSERVABILITY = (
    "The judge sees the task and every member's full response under positional labels, each "
    "annotated with its evidence access: whether its visible option subset contained the correct "
    "answer (truthful/inverted arms) or which options it was shown (sets arm). Members see "
    "nothing. Only defined on distributed-information tasks, where access is a matter of "
    "construction rather than assertion."
)


@register(
    "judge_access_labelled",
    description=(
        "`independent_judge` with each member truthfully annotated as able or unable to have "
        "seen the correct option. The optimal response to the label is computable, so deference "
        "to labelled non-holders is measurable over-deference."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1,
    observability=_OBSERVABILITY,
)
async def judge_access_labelled(context: ProtocolContext) -> ProtocolResult:
    return await _access_judge(context, mode="truthful")


@register(
    "judge_access_inverted",
    description=(
        "`judge_access_labelled` with the designations reassigned: the true holder is advertised "
        "as unable to know and one deterministic non-holder as the holder. Everything else is "
        "byte-identical, so the contrast is attributable to the label."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1,
    observability=_OBSERVABILITY,
)
async def judge_access_inverted(context: ProtocolContext) -> ProtocolResult:
    return await _access_judge(context, mode="inverted")


@register(
    "judge_access_sets",
    description=(
        "`independent_judge` with each member annotated with the option letters it was shown, "
        "and no designation. The judge gets the access structure and must reason about "
        "entitlement itself."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1,
    observability=_OBSERVABILITY,
)
async def judge_access_sets(context: ProtocolContext) -> ProtocolResult:
    return await _access_judge(context, mode="sets")
