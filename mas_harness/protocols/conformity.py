"""Does the judge read the evidence, or the label attached to it?

`independent_judge` shows the aggregator four banked answers under positional labels and nothing
else. D-045 measured what that costs: on tasks where every member was wrong, the judge scored 0.186
against the same model's 0.343 answering alone — reading four wrong answers halves its accuracy.
That is conformity, and the conformity literature has it (`Docs/literature/ENSEMBLING_NOVELTY.md`).

What that literature does not have is peers whose competence is **real and measured** rather than
asserted by the experimenter. This module supplies the manipulation: annotate each member with its
calibration accuracy, and then run the same protocol again with those annotations **reversed**.

``judge_labelled``
    Each member is shown with its true calibration accuracy.
``judge_inverted``
    The identical answers, in the identical order, with the accuracy annotations permuted so the
    weakest member is advertised as the strongest. The multiset of displayed numbers is unchanged;
    only which member carries which number moves.

**The inverted arm is not a deception check, it is what makes the study identifiable.** In the
truthful arm a member's advertised competence *is* its true competence, so the two are perfectly
collinear and no fit on that arm alone can say whether the judge is following the label or the
evidence. Reversing the annotation anti-correlates them, and the two arms pooled separate the
coefficients. See `Docs/literature/CONFORMITY_IMPLEMENTATION.md` section 2.

Both protocols are otherwise `independent_judge` exactly: same aggregator, same prompt, same single
call, same banked answers, same speaking order. The annotation is the only difference, which is what
makes the contrast attributable to it.
"""

from __future__ import annotations

from typing import Sequence

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

# How a member's measured competence is shown. Kept as one constant because the whole study rests
# on the judge attending to this string, and a pilot compares phrasings before anything is spent.
LABEL_TEMPLATE = "[past accuracy on similar tasks: {:.0%}]"


def competence_labels(
    context: ProtocolContext, order: Sequence[int], *, invert: bool
) -> dict[int, str]:
    """Annotation per member: its calibration accuracy, optionally reassigned in reverse rank.

    Inversion permutes *which member carries which number*, never the numbers themselves, so the
    judge sees an identical multiset of competences in both arms. Ties are left where they fall
    rather than broken artificially: with equal competence there is nothing to invert, and forcing a
    swap would manufacture a manipulation that the label does not actually express.
    """
    scores = {a: float(context.competence.get(a, 0.0)) for a in order}
    if invert:
        weakest_first = sorted(order, key=lambda a: (scores[a], a))
        strongest_first = sorted(order, key=lambda a: (-scores[a], a))
        scores = {
            member: scores[donor]
            for member, donor in zip(weakest_first, strongest_first, strict=True)
        }
    return {a: LABEL_TEMPLATE.format(v) for a, v in scores.items()}


async def _labelled_judge(context: ProtocolContext, *, invert: bool) -> ProtocolResult:
    """`independent_judge`, with a competence annotation on each member."""
    protocol_id = "judge_inverted" if invert else "judge_labelled"
    client = context.require_client(protocol_id)
    aggregator = context.pool.aggregator
    if aggregator is None:
        raise ValueError(
            f"pool {context.pool.pool_id!r} defines no aggregator, which "
            f"{protocol_id!r} requires. Add an `aggregator:` block to the pool YAML."
        )

    order = context.speaking_order()
    labels = competence_labels(context, order, invert=invert)
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
            # The analysis needs to know what each member was advertised as, per episode, because
            # the inverted arm's whole content is that this differs from the truth.
            "advertised_competence": {str(a): labels[a] for a in order},
            "true_competence": {str(a): context.competence.get(a, 0.0) for a in order},
            "labels_inverted": invert,
        },
    )


_OBSERVABILITY = (
    "The judge sees the task and every member's full response under positional labels, each "
    "annotated with a calibration accuracy. Members see nothing. In the inverted arm the "
    "annotations are reassigned in reverse rank, so the numbers shown are the same and the "
    "member they describe is not."
)


@register(
    "judge_labelled",
    description=(
        "`independent_judge` with each member annotated with its true calibration accuracy. "
        "Paired against `judge_inverted`, which shows the same numbers attached to the wrong "
        "members, so the pair separates following the label from weighing the evidence."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1,
    observability=_OBSERVABILITY,
)
async def judge_labelled(context: ProtocolContext) -> ProtocolResult:
    return await _labelled_judge(context, invert=False)


@register(
    "judge_inverted",
    description=(
        "`judge_labelled` with the competence annotations permuted into reverse rank: the "
        "weakest member is advertised as the strongest. Answers, order and every other input "
        "are byte-identical to `judge_labelled`, so the contrast is attributable to the label."
    ),
    calls_per_episode=lambda coalition_size, rounds: 1,
    observability=_OBSERVABILITY,
)
async def judge_inverted(context: ProtocolContext) -> ProtocolResult:
    return await _labelled_judge(context, invert=True)
