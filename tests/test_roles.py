"""Latin-square role rotation, and the multi-round debate state it interacts with.

Rotation exists to break one specific confound: if the same model family always verifies, a
measured "verifier effect" and a "family effect" are the same number. These tests check the
square is actually crossed, that rotations are distinguishable in the records, and that the
free protocols are not multiplied by rotations they cannot observe.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mas_harness.pool.roles import (
    DEFAULT_ROLE_CYCLE,
    latin_square,
    role_rotations,
    verify_crossed,
)
from mas_harness.protocols import FREE_PROTOCOLS
from mas_harness.protocols.base import format_peer_answers, system_prompt
from mas_harness.runners.episodes import resolve_pools

from .test_protocols import build_context, run

# ---- the square ----------------------------------------------------------------------------


def test_latin_square_has_each_value_once_per_row_and_column():
    square = latin_square(4)
    assert len(square) == 4
    for row in square:
        assert sorted(row) == [0, 1, 2, 3]
    for column in range(4):
        assert sorted(row[column] for row in square) == [0, 1, 2, 3]


def test_rotations_cross_role_with_agent(pool):
    rotations = role_rotations(pool)
    assert len(rotations) == len(pool)
    assert verify_crossed(rotations)

    # Every agent holds every role exactly once across the four rotations.
    for agent_id in pool.agent_ids:
        held = [rotated.by_id(agent_id).role for _, rotated in rotations]
        assert sorted(held) == sorted(DEFAULT_ROLE_CYCLE)

    # And within a rotation, every role is held by exactly one agent.
    for _, rotated in rotations:
        assert sorted(a.role for a in rotated) == sorted(DEFAULT_ROLE_CYCLE)


def test_each_rotation_gets_its_own_pool_id(pool):
    """Episodes are keyed on pool_id, so equal ids would make rotations collide on resume."""
    ids = [rotated.pool_id for _, rotated in role_rotations(pool)]
    assert len(set(ids)) == len(ids)
    assert all(pool_id.startswith(pool.pool_id) for pool_id in ids)


def test_rotation_changes_roles_without_changing_models_or_ids(pool):
    for _, rotated in role_rotations(pool):
        assert [a.agent_id for a in rotated] == pool.agent_ids
        assert [a.model for a in rotated] == [a.model for a in pool]
        assert [a.family for a in rotated] == [a.family for a in pool]
        assert rotated.aggregator == pool.aggregator


def test_rotation_refuses_a_mismatched_role_count(pool):
    with pytest.raises(ValueError, match="one role per agent"):
        role_rotations(pool, roles=("solver", "verifier"))


def test_verify_crossed_rejects_a_square_that_repeats_a_role(pool):
    degenerate = [("rot0", pool.with_roles(["solver"] * 4, pool_id="p-rot0"))] * 2
    assert verify_crossed(degenerate) is False


def test_role_reaches_the_prompt(pool):
    """The rotation is only meaningful if the assigned role changes what the agent is told."""
    rotations = role_rotations(pool)
    prompts = {
        rotated.by_id(0).role: system_prompt(rotated.by_id(0)) for _, rotated in rotations
    }
    assert len(set(prompts.values())) == len(prompts)
    assert "verifier" in prompts["verifier"].lower()


# ---- the runner's expansion ----------------------------------------------------------------


def test_resolve_pools_is_a_no_op_unless_rotation_is_asked_for(pool):
    assert resolve_pools(pool, role_rotation=False) == [pool]
    assert len(resolve_pools(pool, role_rotation=True)) == len(pool)


def test_free_protocols_read_no_roles(choice_task, pool, make_bank):
    """Why the runner does not multiply free protocols by rotations: they cannot observe them.

    If this ever stops being true, ``run_stage_b`` would be dropping real variation on the
    floor, so the assumption is asserted rather than left as a comment.
    """
    bank = make_bank(["B", "A", "A", "C"])
    for protocol_id in sorted(FREE_PROTOCOLS):
        baseline = run(protocol_id, build_context(choice_task, pool, bank, client=None))
        for _, rotated in role_rotations(pool):
            rotated_result = run(
                protocol_id, build_context(choice_task, rotated, bank, client=None)
            )
            assert rotated_result.final_answer == baseline.final_answer
            assert rotated_result.calls == []


def test_expert_verifier_selects_by_role_so_rotation_moves_the_verifier(
    choice_task, pool, make_bank, stub_client
):
    """The confound rotation exists to break, demonstrated: who verifies follows the role."""
    bank = make_bank(["B", "A", "A", "A"])
    chosen = {}
    for rotation_id, rotated in role_rotations(pool):
        client = stub_client(lambda request: "NO ERROR FOUND")
        result = run(
            "expert_verifier",
            build_context(choice_task, rotated, bank, client=client, predicted_expert_id=0),
        )
        chosen[rotation_id] = result.meta["verifier_agent_id"]
    # Agent 0 is the expert in every rotation, so it is never also the verifier; the remaining
    # three each take the job as the square rotates.
    assert 0 not in chosen.values()
    assert len(set(chosen.values())) > 1


# ---- multi-round debate state ---------------------------------------------------------------


def test_debate_round_two_shows_the_latest_positions_not_the_bank(
    choice_task, pool, make_bank, stub_client
):
    """A third round must debate round two's answers, not replay round zero's."""
    round_marker = "REVISED IN ROUND 1"

    def responder(request):
        content = "\n".join(str(m["content"]) for m in request["messages"])
        if "discussion round 1" in content:
            return f"{round_marker}. The answer is 'C'."
        return "Holding position. The answer is 'C'."

    client = stub_client(responder)
    bank = make_bank(["A", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, max_rounds=3)
    result = run("debate_vote", context)

    assert client.n_calls == 8  # four members x two revision rounds
    round_two = [r for r in client.requests if "discussion round 2" in str(r["messages"])]
    assert len(round_two) == 4
    for request in round_two:
        content = "\n".join(str(m["content"]) for m in request["messages"])
        # Peers are shown their round-1 revisions ...
        assert round_marker in content
        # ... and the banked round-0 answer is gone from the prompt entirely.
        assert "'A'" not in content

    assert result.meta["round_history"][-1]["round"] == 2
    assert result.final_answer == "C"


def test_debate_revision_is_simultaneous_within_a_round(
    choice_task, pool, make_bank, stub_client
):
    """Every member in a round sees the same state, whatever order the calls complete in."""
    seen: list[str] = []

    def responder(request):
        content = "\n".join(str(m["content"]) for m in request["messages"])
        if "discussion round 1" in content:
            seen.append(content)
        return "The answer is 'B'."

    client = stub_client(responder)
    context = build_context(
        choice_task, pool, make_bank(["A", "A", "A", "A"]), client=client, max_rounds=2
    )
    run("debate_vote", context)

    assert len(seen) == 4
    # No member saw another member's round-1 answer, which only round 2 should carry.
    assert all("'B'" not in content for content in seen)


def test_peer_block_override_only_replaces_the_named_members(choice_task, pool, make_bank):
    bank = make_bank(["A", "B", "C", "D"])
    context = build_context(choice_task, pool, bank, client=None)
    block = format_peer_answers(
        context, visible=[0, 1], anonymize=True, texts={0: "overridden text"}
    )
    assert "overridden text" in block
    assert "'B'" in block  # agent 1 still reads from the bank
    assert "'A'" not in block


def test_single_round_debate_makes_no_calls_and_matches_the_vote(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client()
    context = build_context(
        choice_task, pool, make_bank(["B", "B", "A", "A"]), client=client, max_rounds=1
    )
    result = run("debate_vote", context)
    assert client.n_calls == 0
    assert result.meta["n_agents_switched_answer"] == 0


def test_rotation_pool_survives_a_round_trip_through_the_dict_form(pool):
    from mas_harness.pool.agents import AgentPool

    _, rotated = role_rotations(pool)[1]
    restored = AgentPool.from_dict(rotated.to_dict())
    assert restored.content_hash == rotated.content_hash
    assert [a.role for a in restored] == [a.role for a in rotated]


def test_aggregator_is_untouched_by_rotation(pool):
    """The neutral aggregator is not a pool member, so rotation must not reassign its role."""
    for _, rotated in role_rotations(pool):
        assert rotated.aggregator.role == "aggregator"


def test_rotation_ids_are_stable_across_calls(pool):
    first = [rid for rid, _ in role_rotations(pool)]
    second = [rid for rid, _ in role_rotations(pool)]
    assert first == second == ["rot0", "rot1", "rot2", "rot3"]


def test_pool_with_roles_rejects_an_unknown_role(pool):
    with pytest.raises(ValueError, match="role"):
        pool.with_roles(["solver", "verifier", "not_a_role", "generalist"])


def test_dropping_the_aggregator_leaves_a_valid_pool(pool):
    """Guard for the trick the chair test uses: a pool without an aggregator is still legal."""
    stripped = replace(pool, aggregator=None)
    assert stripped.aggregator is None
    assert stripped.agent_ids == pool.agent_ids
    assert stripped.content_hash != pool.content_hash
