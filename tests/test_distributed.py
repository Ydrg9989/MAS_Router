"""Tests for the distributed-information condition (D-010).

The construction's whole value is that individual insufficiency is *provable* rather than
empirically validated, so these tests check the proof obligations directly: only the holders
can see the correct option, the union of visible sets is complete, no member is advantaged by
set size, and the briefing actually reaches the member on every call it makes — not just the
first one.
"""

from __future__ import annotations

import asyncio
import random
import string
from collections import Counter

import pytest

from mas_harness.pool.agents import Agent, AgentPool
from mas_harness.protocols.base import (
    ProtocolContext,
    chair_query_prompt,
    chair_response_prompt,
    independent_prompt,
    judge_prompt,
    revision_prompt,
    system_prompt,
)
from mas_harness.tasks.adapters import TaskSpec, build_evaluator
from mas_harness.tasks.distributed import (
    MIN_VISIBLE_OPTIONS,
    NO_ANSWER_TOKEN,
    build_distributed_specs,
    can_answer_correctly,
    check_pool_matches,
    declared_no_answer,
    holder_agent_ids,
    out_of_set_rate,
    partition_options,
    verify_spec,
    visible_options,
    visible_size,
)

AGENT_IDS = [0, 1, 2, 3]


def source_task(index: int, *, n_options: int = 10, gold: str = "D") -> TaskSpec:
    options = [f"option {letter}" for letter in string.ascii_uppercase[:n_options]]
    return TaskSpec(
        task_id=f"mmlu_pro::src{index:03d}",
        suite="mmlu_pro",
        domain="physics",
        answer_type="choice",
        prompt=f"Question {index} with all options inline.",
        ground_truth=gold,
        payload={"question": f"Stem of question {index}?", "options": options, "answer": gold},
    )


@pytest.fixture
def specs() -> list[TaskSpec]:
    return build_distributed_specs(
        [source_task(i) for i in range(12)],
        n_positions=4,
        agent_ids=AGENT_IDS,
        seed=7,
    )


# ---- the partition itself ---------------------------------------------------------------


def test_only_the_holders_can_see_the_correct_option():
    letters = list(string.ascii_uppercase[:10])
    part = partition_options(
        letters, "D", n_positions=4, holders=[2], rng=random.Random(0)
    )
    assert part.holders == (2,)
    assert part.sees_gold(2)
    assert [p for p in range(4) if part.sees_gold(p)] == [2]


def test_the_union_of_visible_sets_is_the_whole_option_set():
    for n_options in range(3, 11):
        letters = list(string.ascii_uppercase[:n_options])
        part = partition_options(
            letters, letters[1], n_positions=4, holders=[0], rng=random.Random(n_options)
        )
        covered = {letter for options in part.visible for letter in options}
        assert covered == set(letters), n_options


def test_every_member_sees_the_same_number_of_options():
    """Otherwise set size would correlate with holding the answer."""
    for n_options in range(3, 11):
        letters = list(string.ascii_uppercase[:n_options])
        part = partition_options(
            letters, letters[-1], n_positions=4, holders=[1], rng=random.Random(n_options)
        )
        sizes = {len(options) for options in part.visible}
        assert len(sizes) == 1, (n_options, [len(o) for o in part.visible])
        assert sizes.pop() == visible_size(n_options, 4)


def test_nobody_sees_fewer_options_than_the_floor():
    letters = list(string.ascii_uppercase[:10])
    part = partition_options(
        letters, "A", n_positions=4, holders=[0], rng=random.Random(1)
    )
    assert all(len(options) >= MIN_VISIBLE_OPTIONS for options in part.visible)


def test_multiple_holders_are_all_recorded():
    letters = list(string.ascii_uppercase[:10])
    part = partition_options(
        letters, "F", n_positions=4, holders=[0, 3], rng=random.Random(2)
    )
    assert part.holders == (0, 3)
    assert part.sees_gold(0) and part.sees_gold(3)
    assert not part.sees_gold(1) and not part.sees_gold(2)


def test_the_partition_is_deterministic_given_the_same_rng():
    letters = list(string.ascii_uppercase[:10])
    first = partition_options(letters, "C", n_positions=4, holders=[1], rng=random.Random(5))
    second = partition_options(letters, "C", n_positions=4, holders=[1], rng=random.Random(5))
    assert first.visible == second.visible


def test_a_partition_that_cannot_hide_the_answer_is_refused():
    # Two options and a member that must see at least two: hiding the gold one is impossible.
    with pytest.raises(ValueError, match="non-gold"):
        partition_options(["A", "B"], "A", n_positions=2, holders=[0], rng=random.Random(0))


def test_a_gold_option_outside_the_set_is_refused():
    with pytest.raises(ValueError, match="not among"):
        partition_options(["A", "B", "C"], "Z", n_positions=2, holders=[0], rng=random.Random(0))


def test_a_partition_with_no_holder_is_refused():
    with pytest.raises(ValueError, match="at least one position"):
        partition_options(list("ABCD"), "A", n_positions=2, holders=[], rng=random.Random(0))


# ---- derived specs ---------------------------------------------------------------------


def test_derived_specs_pass_their_own_verification(specs):
    assert len(specs) == 12
    for spec in specs:
        verify_spec(spec)


def test_the_shared_prompt_does_not_leak_the_options(specs):
    """The point of the condition: the option list is private, not shared."""
    for spec in specs:
        options = spec.payload["options"]
        assert not any(option in spec.prompt for option in options)
        assert "divided among your team" in spec.prompt


def test_each_agent_gets_a_briefing_naming_only_its_own_options(specs):
    spec = specs[0]
    for agent_id in AGENT_IDS:
        briefing = spec.hidden_context[str(agent_id)]
        mine = set(visible_options(spec, agent_id))
        for letter, text in zip(string.ascii_uppercase, spec.payload["options"], strict=False):
            assert (text in briefing) == (letter in mine), (agent_id, letter)


def test_can_answer_correctly_agrees_with_the_recorded_holders(specs):
    for spec in specs:
        holders = holder_agent_ids(spec)
        for agent_id in AGENT_IDS:
            assert can_answer_correctly(spec, agent_id) == (agent_id in holders)


def test_exactly_one_agent_can_be_right_under_a_unique_holder(specs):
    for spec in specs:
        assert sum(can_answer_correctly(spec, a) for a in AGENT_IDS) == 1


def test_the_holder_rotates_so_no_position_is_favoured(specs):
    counts = Counter(holder_agent_ids(spec)[0] for spec in specs)
    assert set(counts) == set(AGENT_IDS)
    # 12 tasks over 4 positions, round-robin: exactly balanced.
    assert set(counts.values()) == {3}


def test_ground_truth_survives_the_derivation(specs):
    for spec in specs:
        evaluator = build_evaluator(spec)
        assert evaluator.score_extracted(spec.ground_truth)
        assert spec.suite == "distributed_synth"


def test_tasks_with_too_few_options_are_dropped():
    kept = build_distributed_specs(
        [source_task(0, n_options=2, gold="A"), source_task(1, n_options=10)],
        n_positions=4,
        agent_ids=AGENT_IDS,
    )
    assert [s.payload["source_task_id"] for s in kept] == ["mmlu_pro::src001"]


def test_derivation_is_deterministic_across_calls():
    first = build_distributed_specs(
        [source_task(i) for i in range(4)], n_positions=4, agent_ids=AGENT_IDS, seed=3
    )
    second = build_distributed_specs(
        [source_task(i) for i in range(4)], n_positions=4, agent_ids=AGENT_IDS, seed=3
    )
    assert [s.hidden_context for s in first] == [s.hidden_context for s in second]


def test_a_different_seed_changes_the_partition():
    first = build_distributed_specs(
        [source_task(i) for i in range(4)], n_positions=4, agent_ids=AGENT_IDS, seed=3
    )
    second = build_distributed_specs(
        [source_task(i) for i in range(4)], n_positions=4, agent_ids=AGENT_IDS, seed=99
    )
    assert [s.hidden_context for s in first] != [s.hidden_context for s in second]


def test_holders_stay_put_when_only_the_briefing_changes():
    """The two arms must be comparable task by task, differing only in what members are told."""
    sources = [source_task(i) for i in range(8)]
    cooperative = build_distributed_specs(
        sources, n_positions=4, agent_ids=AGENT_IDS, seed=11
    )
    pressure = build_distributed_specs(
        sources,
        n_positions=4,
        agent_ids=AGENT_IDS,
        seed=11,
        announce_structure=False,
        allow_declining=False,
    )
    for a, b in zip(cooperative, pressure, strict=True):
        assert a.task_id == b.task_id
        assert holder_agent_ids(a) == holder_agent_ids(b)
        assert a.payload["distributed"]["visible_by_agent_id"] == (
            b.payload["distributed"]["visible_by_agent_id"]
        )
        assert a.hidden_context != b.hidden_context


def test_the_two_arms_differ_in_whether_declining_is_offered():
    sources = [source_task(0)]
    (cooperative,) = build_distributed_specs(
        sources, n_positions=4, agent_ids=AGENT_IDS, seed=1
    )
    (pressure,) = build_distributed_specs(
        sources,
        n_positions=4,
        agent_ids=AGENT_IDS,
        seed=1,
        announce_structure=False,
        allow_declining=False,
    )
    assert cooperative.payload["distributed"]["arm"] == "cooperative"
    assert pressure.payload["distributed"]["arm"] == "pressure"

    briefed = cooperative.hidden_context["0"]
    forced = pressure.hidden_context["0"]
    assert NO_ANSWER_TOKEN in briefed and "Exactly one member" in briefed
    assert NO_ANSWER_TOKEN not in forced and "Exactly one member" not in forced


# ---- declining and out-of-set answers ---------------------------------------------------


def test_a_declared_decline_is_an_abstention_not_a_vote(specs):
    """The NONE declaration must not be extracted as a letter, or it would be counted."""
    evaluator = build_evaluator(specs[0])
    text = f"None of the options I can see is correct. The answer is '{NO_ANSWER_TOKEN}'."
    assert evaluator.extract(text) == ""
    assert declared_no_answer(text)


def test_declining_is_distinguishable_from_failing_to_answer():
    assert declared_no_answer("The answer is 'NONE'.")
    assert declared_no_answer("the answer is none")
    assert declared_no_answer("NONE")
    assert not declared_no_answer("I am not sure what to say here.")
    assert not declared_no_answer("The answer is 'B'.")


def test_out_of_set_answers_are_measured_not_assumed_away(specs):
    spec = specs[0]
    holder = holder_agent_ids(spec)[0]
    other = next(a for a in AGENT_IDS if a != holder)
    unseen = next(
        letter
        for letter in string.ascii_uppercase[: spec.payload["distributed"]["n_options"]]
        if letter not in visible_options(spec, other)
    )
    stats = out_of_set_rate(
        spec,
        {holder: spec.ground_truth, other: unseen},
    )
    assert stats["n_answers"] == 2
    assert stats["out_of_set_rate"] == 0.5


def test_a_nonholder_naming_the_unseen_gold_is_flagged_as_a_guess(specs):
    spec = specs[0]
    other = next(a for a in AGENT_IDS if a not in holder_agent_ids(spec))
    stats = out_of_set_rate(spec, {other: spec.ground_truth})
    assert stats["guessed_unseen_gold_rate"] == 1.0


def test_abstentions_are_not_counted_in_the_out_of_set_denominator(specs):
    stats = out_of_set_rate(specs[0], {0: "", 1: ""})
    assert stats["n_answers"] == 0
    assert stats["out_of_set_rate"] == 0.0


# ---- the briefing reaches the member ----------------------------------------------------


def pool_for(agent_ids=AGENT_IDS) -> AgentPool:
    agents = tuple(
        Agent(
            agent_id=agent_id,
            name=f"m{agent_id}",
            provider="openrouter",
            model=f"vendor/m{agent_id}",
            family=f"f{agent_id}",
            max_tokens=64,
        )
        for agent_id in agent_ids
    )
    aggregator = Agent(
        agent_id=-1,
        name="judge",
        provider="openrouter",
        model="vendor/judge",
        family="judge",
        role="aggregator",
        max_tokens=64,
    )
    return AgentPool(pool_id="dpool", agents=agents, aggregator=aggregator)


def test_stage_a_shows_each_member_its_own_briefing(specs):
    spec = specs[0]
    pool = pool_for()
    for agent in pool.agents:
        messages = independent_prompt(spec, agent)
        system = next(m["content"] for m in messages if m["role"] == "system")
        assert spec.hidden_context[str(agent.agent_id)] in system


def test_a_members_briefing_survives_a_debate_round(specs, make_answer_for):
    """The regression that matters: an agent that loses its evidence mid-protocol is being
    asked to defend a position whose basis it can no longer see."""
    spec = specs[0]
    pool = pool_for()
    bank = {a.agent_id: make_answer_for(spec, a, "A") for a in pool.agents}
    context = ProtocolContext(
        spec=spec,
        evaluator=build_evaluator(spec),
        pool=pool,
        coalition=tuple(AGENT_IDS),
        bank=bank,
        seed=0,
    )
    for agent in pool.agents:
        messages = revision_prompt(context, agent, peer_block="peers", round_index=1)
        system = next(m["content"] for m in messages if m["role"] == "system")
        assert spec.hidden_context[str(agent.agent_id)] in system


def test_a_member_keeps_its_briefing_when_the_chair_asks(specs, make_answer_for):
    spec = specs[0]
    pool = pool_for()
    bank = {a.agent_id: make_answer_for(spec, a, "A") for a in pool.agents}
    context = ProtocolContext(
        spec=spec,
        evaluator=build_evaluator(spec),
        pool=pool,
        coalition=tuple(AGENT_IDS),
        bank=bank,
        seed=0,
    )
    messages = chair_response_prompt(context, pool.agents[0], question="Which option is yours?")
    system = next(m["content"] for m in messages if m["role"] == "system")
    assert spec.hidden_context["0"] in system


def test_the_chair_and_judge_hold_no_private_evidence(specs, make_answer_for):
    """A chair that already held the evidence could not demonstrate the value of asking."""
    spec = specs[0]
    pool = pool_for()
    bank = {a.agent_id: make_answer_for(spec, a, "A") for a in pool.agents}
    context = ProtocolContext(
        spec=spec,
        evaluator=build_evaluator(spec),
        pool=pool,
        coalition=tuple(AGENT_IDS),
        bank=bank,
        seed=0,
    )
    for messages in (
        judge_prompt(context, peer_block="peers"),
        chair_query_prompt(context, peer_block="peers"),
    ):
        joined = "\n".join(str(m["content"]) for m in messages)
        for agent_id in AGENT_IDS:
            assert spec.hidden_context[str(agent_id)] not in joined


def test_the_task_spec_briefing_beats_a_stale_one_on_the_agent(specs):
    """Private evidence is per (task, agent), so the spec must win over anything on the pool."""
    spec = specs[0]
    agent = pool_for().agents[0].with_hidden_context("stale evidence from another task")
    system = system_prompt(agent, spec)
    assert "stale evidence" not in system
    assert spec.hidden_context["0"] in system


def test_an_ordinary_task_leaves_the_agents_own_context_alone(choice_task):
    agent = pool_for().agents[0].with_hidden_context("agent-level context")
    assert "agent-level context" in system_prompt(agent, choice_task)


# ---- guards ----------------------------------------------------------------------------


def test_a_pool_missing_a_briefed_agent_is_refused(specs):
    with pytest.raises(ValueError, match="no options"):
        check_pool_matches(specs, [0, 1, 2])


def test_a_matching_pool_passes(specs):
    check_pool_matches(specs, AGENT_IDS)
    check_pool_matches(specs, [*AGENT_IDS, 9])


def test_ordinary_suites_are_unaffected_by_the_guard(choice_task):
    check_pool_matches([choice_task], [42])


def test_stage_a_refuses_a_mismatched_pool(specs, tmp_path):
    from mas_harness.runners.answer_bank import run_stage_a
    from mas_harness.tasks.manifest import Manifest

    manifest = Manifest(
        manifest_id="d", created_at="now", seed=0, tasks=list(specs), splits={}
    )
    with pytest.raises(ValueError, match="no options"):
        asyncio.run(
            run_stage_a(
                manifest=manifest,
                pool=pool_for([0, 1]),
                seeds=[0],
                run_id="mismatch",
                runs_root=tmp_path,
                concurrency=1,
                dry_run=True,
                refresh_prices=False,
            )
        )


# ---- the phenomenon the condition is built to expose ------------------------------------


def pressure_bank(spec, pool, make_answer_for):
    """The pressure arm's expected behaviour: the holder is right, everyone else guesses.

    Each uninformed member names an option it can actually see, which is necessarily wrong.
    This is what the condition is designed to produce, so a protocol's behaviour on this bank
    is the thing worth measuring.
    """
    bank = {}
    for agent in pool.agents:
        if can_answer_correctly(spec, agent.agent_id):
            answer = spec.ground_truth
        else:
            answer = visible_options(spec, agent.agent_id)[0]
        bank[agent.agent_id] = make_answer_for(spec, agent, answer)
    return bank


def test_a_vote_can_never_be_carried_by_correct_votes_under_a_unique_holder(
    specs, make_answer_for
):
    """Dilution with the competence explanation removed: the majority lacks the evidence.

    The precise claim is that the correct answer can never *win* a plurality here, because
    only one member is able to cast it. A vote that nonetheless lands on the right answer did
    so through the deterministic tie-break, not through agreement — so the assertion is about
    how the vote was decided, not merely about the accuracy it happened to produce.
    """
    from mas_harness.protocols import get_protocol

    decided_by_tie_break = 0
    won_on_the_merits = 0
    pool = pool_for()
    for spec in specs:
        evaluator = build_evaluator(spec)
        bank = pressure_bank(spec, pool, make_answer_for)
        assert sum(record.correct for record in bank.values()) == 1
        context = ProtocolContext(
            spec=spec,
            evaluator=evaluator,
            pool=pool,
            coalition=tuple(AGENT_IDS),
            bank=bank,
            seed=0,
        )
        result = asyncio.run(get_protocol("independent_majority").fn(context))
        meta = result.meta
        if not evaluator.score_extracted(result.final_answer):
            continue
        # The correct answer had exactly one supporter, so it cannot have out-voted anything.
        assert len(meta["winner_support"]) == 1
        if meta["tie_break"] != "none":
            decided_by_tie_break += 1
        else:
            won_on_the_merits += 1
    assert won_on_the_merits == 0
    # And the rescues are rare: a tie-break rescue needs a full split with no plurality.
    assert decided_by_tie_break < len(specs) / 2


def test_deferring_to_the_holder_recovers_every_task(specs, make_answer_for):
    """The ceiling the governance protocols are aiming at: the evidence is in the room."""
    from mas_harness.protocols import get_protocol

    pool = pool_for()
    wins = 0
    for spec in specs:
        evaluator = build_evaluator(spec)
        bank = pressure_bank(spec, pool, make_answer_for)
        holder = holder_agent_ids(spec)[0]
        context = ProtocolContext(
            spec=spec,
            evaluator=evaluator,
            pool=pool,
            coalition=tuple(AGENT_IDS),
            bank=bank,
            seed=0,
            # A protocol that identifies the evidence holder as the expert recovers the
            # answer; the point of protocols 6 and 7 is to do this without being told.
            competence={agent_id: (1.0 if agent_id == holder else 0.0) for agent_id in AGENT_IDS},
        )
        result = asyncio.run(get_protocol("single_expert").fn(context))
        wins += evaluator.score_extracted(result.final_answer)
    assert wins == len(specs)


def test_declining_lets_the_holder_carry_the_vote(specs, make_answer_for):
    """The cooperative arm's other outcome: abstention, not accuracy, decides the vote."""
    from mas_harness.protocols import get_protocol

    pool = pool_for()
    wins = 0
    for spec in specs:
        evaluator = build_evaluator(spec)
        bank = {}
        for agent in pool.agents:
            if can_answer_correctly(spec, agent.agent_id):
                bank[agent.agent_id] = make_answer_for(spec, agent, spec.ground_truth)
            else:
                bank[agent.agent_id] = make_answer_for(
                    spec,
                    agent,
                    "",
                    text=f"I cannot see the correct option. The answer is '{NO_ANSWER_TOKEN}'.",
                )
        context = ProtocolContext(
            spec=spec,
            evaluator=evaluator,
            pool=pool,
            coalition=tuple(AGENT_IDS),
            bank=bank,
            seed=0,
        )
        result = asyncio.run(get_protocol("independent_majority").fn(context))
        wins += evaluator.score_extracted(result.final_answer)
    assert wins == len(specs)


def test_a_changed_partition_changes_the_manifest_hash(specs):
    """For this suite the partition is the task, so immutability must cover it."""
    from mas_harness.tasks.manifest import Manifest

    other = build_distributed_specs(
        [source_task(i) for i in range(12)], n_positions=4, agent_ids=AGENT_IDS, seed=8
    )
    first = Manifest(manifest_id="d", created_at="t", seed=0, tasks=list(specs), splits={})
    second = Manifest(manifest_id="d", created_at="t", seed=0, tasks=other, splits={})
    assert first.task_ids == second.task_ids
    assert first.content_hash != second.content_hash
