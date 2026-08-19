"""The distributed-information condition (D-010), built by partitioning option sets.

HiddenBench is not obtainable, so the controlled distributed-information substrate is
constructed here from existing multiple-choice tasks. Every task built by this module
carries ``suite="distributed_synth"`` so its results can never be silently pooled with a
published benchmark.

Why partition the options rather than write clues
-------------------------------------------------
The obvious construction is to ask a strong model to write N disjoint clues that are
jointly sufficient and individually insufficient. We do not do that. It costs money, the
generator leaks the answer in ways that are tedious to detect, and "individually
insufficient" would then be an *empirical claim* needing its own validation run — a claim
about a generated artifact, which is exactly the kind of thing that quietly fails.

Partitioning the option set makes the same property **provable**. Each member sees the
question stem plus a subset of the lettered options. The union of the subsets is the whole
option set, but the correct option is shown to only ``n_holders`` members. A member who
cannot see the correct option cannot state it. No validation needed, no generation cost, no
leakage.

What this condition is for
--------------------------
It turns the governance question into its sharpest form. Under a unique holder, exactly one
member *can* be right and every other member is necessarily wrong. So:

* ``independent_majority`` fails by construction whenever the uninformed members answer
  anyway — the one correct vote is outnumbered. This is dilution with the competence
  explanation removed: the majority is not wrong because it reasons badly, it is wrong
  because it lacks the evidence and votes regardless.
* Whether they answer anyway is itself the measurement. A calibrated member that cannot see
  the correct option should decline, and declining is measurable here precisely because
  strict extraction treats an answerless message as an abstention rather than a vote (D-011).
  :func:`private_briefing` therefore exposes two arms — one that warns members and lets them
  decline, one that does not — because "protocols cannot rescue the holder" and "models
  abstain when they should" are different findings and must not be confused.
* ``chair_information_seeking`` and ``expert_veto`` are the protocols predicted to recover
  the answer, because one can *ask* and the other lets a single evidence-holder overturn a
  majority. The chair deliberately holds no private evidence of its own, so it can only
  succeed by asking.

Limits, stated because they bound the claims
--------------------------------------------
Absolute accuracy here is **not** comparable to the full-information condition. Showing a
member 3 of 10 options changes its prior from 1/10 to 1/3, so a holder is advantaged and a
non-holder is doomed. The meaningful comparisons are *within* this condition: across
protocols on the same partition, and against the same tasks with the holder count varied.
The full-information version of the same questions is a reference point for how hard the
underlying questions are, not a baseline to subtract.

A non-holder can still name the correct letter by guessing outside its visible set, which
would weaken the construction. :func:`out_of_set_rate` measures how often that happens so
it can be reported rather than assumed away.
"""

from __future__ import annotations

import hashlib
import random
import string
from dataclasses import dataclass
from typing import Any, Sequence

from .adapters import TaskSpec, build_evaluator

SUITE = "distributed_synth"

# A member shown a single option has no decision to make, so every member sees at least
# this many. Enforced by topping up with non-gold options, never with the gold one.
MIN_VISIBLE_OPTIONS = 2

# Below three options there is no room to hide the answer from anyone while still leaving
# the uninformed members a choice, so such tasks are dropped.
MIN_TOTAL_OPTIONS = 3

# The literal an uninformed member is told to use when it believes the answer is not among
# the options it can see. Chosen so that strict extraction yields "" (an abstention) while
# the declaration stays detectable in the transcript by :func:`declared_no_answer`.
NO_ANSWER_TOKEN = "NONE"


@dataclass(frozen=True)
class Partition:
    """Which options each position can see, and who holds the correct one."""

    visible: tuple[tuple[str, ...], ...]  # by position
    holders: tuple[int, ...]
    gold: str

    def __post_init__(self) -> None:
        letters = {letter for options in self.visible for letter in options}
        holding = [i for i, options in enumerate(self.visible) if self.gold in options]
        if tuple(holding) != tuple(sorted(self.holders)):
            raise AssertionError(
                f"holders {self.holders} disagree with who can actually see {self.gold!r} "
                f"({holding}); the partition would misattribute the necessary information"
            )
        if self.gold not in letters:
            raise AssertionError("the correct option is visible to nobody: task is unsolvable")
        for position, options in enumerate(self.visible):
            if len(options) < min(MIN_VISIBLE_OPTIONS, len(letters)):
                raise AssertionError(
                    f"position {position} sees only {len(options)} option(s); a member with "
                    f"one option is not making a decision"
                )

    @property
    def n_positions(self) -> int:
        return len(self.visible)

    def sees_gold(self, position: int) -> bool:
        return self.gold in self.visible[position]


def _rng(seed: int, key: str) -> random.Random:
    """A deterministic RNG. ``hash()`` is salted per process, so it cannot be used here."""
    digest = hashlib.sha256(f"{seed}::{key}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def visible_size(n_options: int, n_positions: int) -> int:
    """How many options every member sees.

    Equal for all members, which matters: if the holder saw more options than everybody
    else, visible-set size would correlate with holding the answer. That is both a leak and
    a nuisance variable, since a member choosing among four options is doing a different
    task than one choosing among two.
    """
    return max(MIN_VISIBLE_OPTIONS, -(-n_options // n_positions))


def partition_options(
    letters: Sequence[str],
    gold: str,
    *,
    n_positions: int,
    holders: Sequence[int],
    rng: random.Random,
) -> Partition:
    """Split ``letters`` across positions so only ``holders`` can see ``gold``.

    Every position ends up seeing exactly :func:`visible_size` options. The gold option is
    placed first and consumes one of its holders' slots; the remaining capacity is filled
    round-robin from the non-gold options, which guarantees the union is complete. Leftover
    capacity is filled with non-gold options the position has not already been shown, so
    some options are visible to more than one member. That overlap is harmless — only the
    gold option's visibility is controlled — and it keeps set sizes uniform.

    Top-ups never use the gold option: that would hand the necessary information to a member
    the design says does not have it.
    """
    if gold not in letters:
        raise ValueError(f"gold option {gold!r} is not among {list(letters)}")
    if not holders:
        raise ValueError("at least one position must hold the correct option")
    if not set(holders) <= set(range(n_positions)):
        raise ValueError(f"holders {list(holders)} out of range for {n_positions} positions")

    others = [letter for letter in letters if letter != gold]
    size = visible_size(len(letters), n_positions)
    if size > len(others):
        raise ValueError(
            f"cannot show {size} options to a member that must not see the correct one: "
            f"only {len(others)} of the {len(letters)} options are non-gold"
        )

    rng.shuffle(others)
    visible: list[set[str]] = [set() for _ in range(n_positions)]
    capacity = [size] * n_positions
    for position in holders:
        visible[position].add(gold)
        capacity[position] -= 1

    # Round-robin the non-gold options into the remaining capacity. Cycling by position
    # keeps the distribution even; placing every option exactly once guarantees coverage.
    queue = list(others)
    position = 0
    while queue:
        placed = False
        for offset in range(n_positions):
            slot = (position + offset) % n_positions
            if capacity[slot] > 0 and queue:
                visible[slot].add(queue.pop(0))
                capacity[slot] -= 1
                placed = True
        position = (position + 1) % n_positions
        if not placed:
            raise AssertionError(
                f"no capacity left for options {queue}; {n_positions} members seeing "
                f"{size} of {len(letters)} options cannot cover the full set"
            )

    for slot in range(n_positions):
        spare = [letter for letter in others if letter not in visible[slot]]
        rng.shuffle(spare)
        while capacity[slot] > 0 and spare:
            visible[slot].add(spare.pop())
            capacity[slot] -= 1

    order = {letter: index for index, letter in enumerate(letters)}
    covered = set().union(*visible)
    if covered != set(letters):
        raise AssertionError(
            f"options {sorted(set(letters) - covered)} are visible to nobody; the team "
            f"cannot see the full option set and the condition is not jointly sufficient"
        )
    return Partition(
        visible=tuple(tuple(sorted(options, key=order.__getitem__)) for options in visible),
        holders=tuple(sorted(holders)),
        gold=gold,
    )


def private_briefing(
    options: Sequence[str],
    visible: Sequence[str],
    *,
    n_holders: int,
    n_positions: int,
    announce_structure: bool,
    allow_declining: bool,
) -> str:
    """The private evidence block for one position.

    ``announce_structure`` and ``allow_declining`` together define which question the
    condition asks, and they are the reason both are exposed as build-time flags:

    * Both on — the *cooperative* arm. A member that cannot see the correct option is told
      that is possible and given a way to say so, so its abstention rate measures
      calibration and self-knowledge. If models abstain well, plurality voting survives
      because the holder is the only one voting; if they answer anyway despite being warned,
      that is a strong result about confidence over evidence.
    * Both off — the *pressure* arm. A member must choose from the options in front of it,
      so every uninformed member necessarily votes wrong and the holder is outnumbered by
      construction. This measures whether any protocol can resist a confidently wrong
      majority, which is the governance question in its hardest form.

    Neither arm is the "real" one. Reporting one without the other would let a reader mistake
    a fact about model calibration for a fact about protocols, or vice versa.
    """
    letters = list(string.ascii_uppercase[: len(options)])
    shown = [
        f"{letter}) {text}"
        for letter, text in zip(letters, options, strict=True)
        if letter in set(visible)
    ]
    parts = ["These are the answer options you can see:", "\n".join(shown)]

    if announce_structure:
        if n_holders == 1:
            parts.append(
                f"The full option set was divided among the {n_positions} members of your "
                f"team. Exactly one member can see the correct option, and it may not be you."
            )
        else:
            parts.append(
                f"The full option set was divided among the {n_positions} members of your "
                f"team. {n_holders} of them can see the correct option, and you may not be "
                f"one of them."
            )
    else:
        parts.append(
            f"The full option set was divided among the {n_positions} members of your team. "
            f"Other members can see options you cannot."
        )

    if allow_declining:
        parts.append(
            f"Choose only from the options listed above. If you believe none of them is "
            f"correct, say so and end your response with exactly: "
            f"The answer is '{NO_ANSWER_TOKEN}'. Declining is the right answer when the "
            f"correct option is not one you can see; do not guess a letter you have not "
            f"been shown."
        )
    else:
        parts.append(
            "Choose the best of the options listed above. Do not name a letter you have not "
            "been shown."
        )
    return "\n\n".join(parts)


def build_distributed_specs(
    sources: Sequence[TaskSpec],
    *,
    n_positions: int,
    agent_ids: Sequence[int],
    seed: int = 0,
    n_holders: int = 1,
    announce_structure: bool = True,
    allow_declining: bool = True,
) -> list[TaskSpec]:
    """Derive distributed-information tasks from multiple-choice source tasks.

    ``holders`` rotates round-robin over the task list so each position holds the necessary
    information on an equal share of tasks. Without that rotation, "the holder prevailed"
    would be confounded with "the model that happens to sit in that position prevailed",
    which is the same confound role rotation exists to remove (D-014).
    """
    if len(agent_ids) != n_positions:
        raise ValueError(f"{n_positions} positions but {len(agent_ids)} agent ids")
    if not 1 <= n_holders <= n_positions:
        raise ValueError(f"n_holders={n_holders} outside 1..{n_positions}")

    specs: list[TaskSpec] = []
    for index, source in enumerate(sorted(sources, key=lambda s: s.task_id)):
        options = list(source.payload.get("options") or [])
        if len(options) < MIN_TOTAL_OPTIONS:
            continue
        letters = list(string.ascii_uppercase[: len(options)])
        gold = source.ground_truth.strip().upper()
        if gold not in letters:
            continue
        # Capacity feasibility for multi-holder partitions: gold consumes n_holders slots, and
        # every other option still needs at least one. Equal visible_size makes this a hard
        # arithmetic constraint (e.g. 8 options, 4 positions, 2 holders: 4x2-2 = 6 slots for 7
        # remaining options), so infeasible tasks are dropped here exactly like short-option
        # tasks — the oversample margin absorbs the loss and partition_options keeps its
        # assertion as a proof, not a filter.
        size = visible_size(len(letters), n_positions)
        if n_positions * size - n_holders < len(letters) - 1:
            continue

        # Round-robin the holder, then take the next n_holders positions cyclically so that
        # multi-holder configurations stay balanced too.
        first = index % n_positions
        holders = [(first + offset) % n_positions for offset in range(n_holders)]

        partition = partition_options(
            letters,
            gold,
            n_positions=n_positions,
            holders=holders,
            rng=_rng(seed, source.task_id),
        )

        hidden_context = {
            str(agent_ids[position]): private_briefing(
                options,
                partition.visible[position],
                n_holders=n_holders,
                n_positions=n_positions,
                announce_structure=announce_structure,
                allow_declining=allow_declining,
            )
            for position in range(n_positions)
        }

        # The stem comes from the raw question field, never from the upstream task
        # description: that description embeds the full option list, which is exactly what
        # must not be shared.
        stem = str(source.payload.get("question") or "").strip()
        if not stem:
            continue
        prompt = (
            f"{stem}\n\n"
            f"The answer options for this question have been divided among your team. You "
            f"can see only some of them."
        )

        payload = dict(source.payload)
        payload.update(
            {
                "source_task_id": source.task_id,
                "source_suite": source.suite,
                "distributed": {
                    "n_positions": n_positions,
                    "required_agent_ids": list(agent_ids),
                    "holder_positions": list(partition.holders),
                    "holder_agent_ids": [agent_ids[p] for p in partition.holders],
                    "n_holders": n_holders,
                    "visible_by_agent_id": {
                        str(agent_ids[p]): list(partition.visible[p])
                        for p in range(n_positions)
                    },
                    "gold": gold,
                    "n_options": len(options),
                    "visible_size": len(partition.visible[0]),
                    "announce_structure": announce_structure,
                    "allow_declining": allow_declining,
                    "arm": (
                        "cooperative"
                        if announce_structure and allow_declining
                        else "pressure"
                        if not announce_structure and not allow_declining
                        else "mixed"
                    ),
                    "seed": seed,
                },
            }
        )

        specs.append(
            TaskSpec(
                task_id=f"{SUITE}::{source.task_id}",
                suite=SUITE,
                domain=source.domain,
                answer_type="choice",
                prompt=prompt,
                ground_truth=gold,
                payload=payload,
                hidden_context=hidden_context,
            )
        )
    return specs


# ---- reading the condition back out of a spec ------------------------------------------


def distributed_meta(spec: TaskSpec) -> dict[str, Any]:
    meta = spec.payload.get("distributed")
    if not isinstance(meta, dict):
        raise ValueError(f"{spec.task_id} carries no distributed-information metadata")
    return meta


def holder_agent_ids(spec: TaskSpec) -> list[int]:
    """The agents that can actually see the correct option."""
    return [int(a) for a in distributed_meta(spec)["holder_agent_ids"]]


def visible_options(spec: TaskSpec, agent_id: int) -> list[str]:
    return list(distributed_meta(spec)["visible_by_agent_id"][str(agent_id)])


def can_answer_correctly(spec: TaskSpec, agent_id: int) -> bool:
    """Whether this agent was given the information needed to be right.

    The ground truth about necessity, which is what makes influence measurable here: a
    correct answer from an agent for which this is False is a guess, not knowledge.
    """
    return spec.ground_truth.strip().upper() in visible_options(spec, agent_id)


def declared_no_answer(text: str) -> bool:
    """Whether a member explicitly declined rather than failing to state an answer.

    Strict extraction maps both to an abstention, which is right for vote tallying but
    wrong for measuring self-knowledge: an agent that recognizes it cannot see the answer is
    behaving well, and one that emits unparseable prose is not.
    """
    lowered = (text or "").lower()
    return NO_ANSWER_TOKEN.lower() in lowered and (
        f"answer is '{NO_ANSWER_TOKEN.lower()}'" in lowered
        or f'answer is "{NO_ANSWER_TOKEN.lower()}"' in lowered
        or f"answer is {NO_ANSWER_TOKEN.lower()}" in lowered
        or lowered.strip() == NO_ANSWER_TOKEN.lower()
    )


def out_of_set_rate(spec: TaskSpec, answers: dict[int, str]) -> dict[str, float]:
    """How often members named an option they were never shown.

    A high rate means the partition is leaking: members are guessing across the whole
    lettered range instead of choosing among what they hold, and the "provably insufficient"
    property stops doing its work. Reported rather than assumed away.
    """
    out_of_set = 0
    guessed_gold = 0
    considered = 0
    for agent_id, answer in answers.items():
        letter = (answer or "").strip().upper()
        if not letter:
            continue
        considered += 1
        if letter not in visible_options(spec, agent_id):
            out_of_set += 1
            if letter == spec.ground_truth.strip().upper():
                guessed_gold += 1
    if not considered:
        return {"out_of_set_rate": 0.0, "guessed_unseen_gold_rate": 0.0, "n_answers": 0}
    return {
        "out_of_set_rate": out_of_set / considered,
        "guessed_unseen_gold_rate": guessed_gold / considered,
        "n_answers": considered,
    }


def check_pool_matches(specs: Sequence[TaskSpec], agent_ids: Sequence[int]) -> None:
    """Refuse to run a distributed manifest against a pool it was not built for.

    Private briefings are keyed by agent id. If the pool's ids do not cover the manifest's,
    the mismatched members silently receive no briefing and are asked a multiple-choice
    question with no options attached — which produces garbage that looks like model failure
    rather than a configuration error. Failing loudly here is the difference between losing a
    config and losing a day of spend and the conclusion drawn from it.
    """
    distributed = [s for s in specs if s.suite == SUITE]
    if not distributed:
        return
    available = {int(a) for a in agent_ids}
    required: set[int] = set()
    for spec in distributed:
        required |= {int(a) for a in distributed_meta(spec)["required_agent_ids"]}
    if not required <= available:
        raise ValueError(
            f"the distributed-information suite needs agent ids {sorted(required)} but the "
            f"pool provides {sorted(available)}. Members without a briefing would be asked a "
            f"multiple-choice question with no options. Fix `agent_ids` in the suite config "
            f"or use the pool the manifest was built for."
        )


def verify_spec(spec: TaskSpec) -> None:
    """Assert the construction still holds for a spec read back from a manifest.

    Cheap enough to run over a whole manifest, and worth running: the properties this
    checks are the ones every claim about the condition rests on.
    """
    meta = distributed_meta(spec)
    gold = spec.ground_truth.strip().upper()
    visible = meta["visible_by_agent_id"]
    holders = [str(a) for a in meta["holder_agent_ids"]]

    can_see = [agent_id for agent_id, options in visible.items() if gold in options]
    if sorted(can_see) != sorted(holders):
        raise AssertionError(
            f"{spec.task_id}: recorded holders {sorted(holders)} but {sorted(can_see)} can "
            f"see the correct option"
        )
    letters = set(string.ascii_uppercase[: int(meta["n_options"])])
    covered = {letter for options in visible.values() for letter in options}
    if covered != letters:
        raise AssertionError(
            f"{spec.task_id}: options {sorted(letters - covered)} visible to nobody"
        )
    for agent_id in visible:
        if agent_id not in spec.hidden_context:
            raise AssertionError(f"{spec.task_id}: agent {agent_id} has no private briefing")
        if len(visible[agent_id]) < min(MIN_VISIBLE_OPTIONS, len(letters)):
            raise AssertionError(f"{spec.task_id}: agent {agent_id} sees too few options")
    # The ground truth must still be scorable by the ordinary evaluator.
    if not build_evaluator(spec).score_extracted(gold):
        raise AssertionError(f"{spec.task_id}: ground truth {gold!r} does not score as correct")
