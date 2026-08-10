"""Protocols 6 and 7, the report's proposed governance interventions.

Two things are being checked, and only the first is about code working:

1. The decision rules do what they claim. Under ``expert_veto`` an unsupported challenge must
   not move the answer and a supported one must; under ``chair_information_seeking`` the chair's
   question must reach the members it named and nobody else.
2. Each protocol is a *controlled* contrast against its MVP baseline. The pairs
   (expert_veto, expert_verifier) and (chair_information_seeking, independent_judge) are the
   whole argument, so the tests assert that the pair differs in the intended way and not in
   what each participant is shown.
"""

from __future__ import annotations

import asyncio

import pytest

from mas_harness.protocols import PROPOSED_PAIRS, PROPOSED_PROTOCOLS, get_protocol
from mas_harness.protocols.base import (
    ASK_PREFIX,
    CONCEDE_SENTINEL,
    NO_QUESTION_SENTINEL,
    QUESTION_PREFIX,
)
from mas_harness.protocols.governance import MAX_RESPONDENTS, parse_chair_query
from mas_harness.records.schema import InterventionSpec

from .test_protocols import build_context, run


def chair_reply(question: str = "Which source states the melting point?", ask: str = "Member 1"):
    """A well-formed chair query, in the format the prompt dictates."""
    return f"{QUESTION_PREFIX} {question}\n{ASK_PREFIX} {ask}"


def scripted(script: dict[str, str], default: str = "The answer is 'B'."):
    """Reply with the first scripted value whose key appears in the prompt."""

    def responder(request):
        content = "\n".join(str(m.get("content", "")) for m in request["messages"])
        for needle, reply in script.items():
            if needle in content:
                return reply
        return default

    return responder


# ---- registry ------------------------------------------------------------------------------


def test_proposed_protocols_are_registered_and_paired():
    for protocol_id in PROPOSED_PROTOCOLS:
        info = get_protocol(protocol_id)
        assert info.interactive is True
        baseline = PROPOSED_PAIRS[protocol_id]
        assert get_protocol(baseline) is not None
        # A proposed protocol that cost the same as its baseline would not be worth the
        # comparison; one that cost less is a bonus. Either way the planner must know.
        assert info.calls_per_episode(4, 2) > 0


def test_expert_veto_is_cheaper_than_the_baseline_it_is_paired_with():
    """The contrast is a decision rule, not extra compute, so veto must not cost more."""
    veto = get_protocol("expert_veto").calls_per_episode(4, 2)
    verifier = get_protocol("expert_verifier").calls_per_episode(4, 2)
    assert veto <= verifier


# ---- protocol 6: expert veto ---------------------------------------------------------------


def test_veto_makes_one_call_and_keeps_the_expert_answer_on_a_concession(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(lambda request: CONCEDE_SENTINEL)
    # The expert (agent 0, highest competence) is right; everyone else is wrong.
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)

    result = run("expert_veto", context)
    assert client.n_calls == 1
    assert result.final_answer == "B"
    assert result.meta["challenger_conceded"] is True
    assert result.meta["veto_upheld"] is False
    assert result.meta["expert_changed_answer"] is False


def test_veto_is_upheld_only_when_the_challenger_names_a_different_answer(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(
        lambda request: "Step three divides by zero, so the conclusion fails. The answer is 'C'."
    )
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)

    result = run("expert_veto", context)
    assert result.meta["veto_upheld"] is True
    assert result.meta["challenger_proposed_answer"] == "C"
    assert result.final_answer == "C"
    # A correct expert overturned by a wrong challenger: dilution through authority, which is
    # exactly the failure mode this protocol is built to expose rather than to hide.
    assert context.evaluator.score_extracted(result.final_answer) is False


def test_an_objection_without_an_alternative_does_not_overturn_the_expert(
    choice_task, pool, make_bank, stub_client
):
    """The evidence bar is the protocol. Vague disagreement must not be enough."""
    client = stub_client(lambda request: "I am not convinced by this reasoning at all.")
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)

    result = run("expert_veto", context)
    assert result.meta["challenger_conceded"] is False
    assert result.meta["challenge_named_alternative"] is False
    assert result.meta["veto_upheld"] is False
    assert result.final_answer == "B"


def test_a_challenger_restating_the_expert_answer_does_not_count_as_a_challenge(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(lambda request: "There is a slip in step two. The answer is 'B'.")
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)

    result = run("expert_veto", context)
    assert result.meta["challenge_named_alternative"] is False
    assert result.meta["veto_upheld"] is False
    assert result.final_answer == "B"


def test_veto_never_shows_the_challenger_who_wrote_the_answer(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(lambda request: CONCEDE_SENTINEL)
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)
    run("expert_veto", context)

    prompt = client.user_content(0)
    assert "alpha" not in prompt  # the expert's name
    assert choice_task.ground_truth not in prompt.replace("'B'", "")  # no leaked label
    assert "competence" not in prompt.lower()


def test_veto_selects_the_designated_verifier_role_over_the_most_competent_member(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(lambda request: CONCEDE_SENTINEL)
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)

    result = run("expert_veto", context)
    # Agent 2 holds the verifier role but is not the most competent non-expert (agent 1 is).
    assert result.meta["challenger_agent_id"] == 2
    assert result.meta["challenger_selection_rule"] == "role"


def test_veto_on_a_singleton_spends_nothing(choice_task, pool, make_bank, stub_client):
    client = stub_client(lambda request: CONCEDE_SENTINEL)
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(
        choice_task,
        pool,
        {0: bank[0]},
        coalition=[0],
        client=client,
        predicted_expert_id=0,
    )
    result = run("expert_veto", context)
    assert client.n_calls == 0
    assert result.meta["degenerate_singleton"] is True
    assert result.final_answer == "B"


def test_veto_falls_back_to_competence_when_no_expert_was_predicted(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(lambda request: CONCEDE_SENTINEL)
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=None)
    result = run("expert_veto", context)
    assert result.meta["used_competence_fallback"] is True
    assert result.meta["expert_agent_id"] == 0  # highest competence in the fixture


# ---- protocol 7: information-seeking chair -------------------------------------------------


def test_chair_asks_then_decides_with_the_expected_call_count(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(
        scripted(
            {
                "you may ask for exactly one piece": chair_reply(ask="Member 1, Member 2"),
                "The team's chair asks": "The source is a 1998 handbook table.",
            },
            default="On the gathered evidence, the answer is 'B'.",
        )
    )
    bank = make_bank(["A", "B", "B", "A"])
    context = build_context(choice_task, pool, bank, client=client)

    result = run("chair_information_seeking", context)
    # One query, two replies, one decision.
    assert client.n_calls == 4
    assert result.meta["asked_question"] is True
    assert result.meta["n_respondents"] == 2
    assert result.meta["query_targets"] == [0, 1]
    assert result.final_answer == "B"
    assert result.meta["n_model_calls"] == 4


def test_chair_that_needs_nothing_skips_straight_to_the_decision(
    choice_task, pool, make_bank, stub_client
):
    """Cost is adaptive: the round trip is only paid when the chair actually wants evidence."""
    client = stub_client(
        scripted(
            {"you may ask for exactly one piece": NO_QUESTION_SENTINEL},
            default="The answer is 'B'.",
        )
    )
    bank = make_bank(["B", "B", "B", "B"])
    context = build_context(choice_task, pool, bank, client=client)

    result = run("chair_information_seeking", context)
    assert client.n_calls == 2
    assert result.meta["asked_question"] is False
    assert result.meta["n_respondents"] == 0
    assert result.meta["query_targets"] == []


def test_chair_questions_reach_only_the_named_members(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(
        scripted(
            {"you may ask for exactly one piece": chair_reply(ask="Member 3")},
            default="The answer is 'B'.",
        )
    )
    bank = make_bank(["A", "A", "B", "A"])
    context = build_context(choice_task, pool, bank, client=client)

    result = run("chair_information_seeking", context)
    assert result.meta["query_targets"] == [2]
    asked = [r for r in client.requests if "The team's chair asks" in str(r["messages"])]
    assert len(asked) == 1
    assert asked[0]["model"] == pool.by_id(2).model


def test_a_queried_member_does_not_see_the_other_members_answers(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(
        scripted(
            {"you may ask for exactly one piece": chair_reply(ask="Member 2")},
            default="The answer is 'B'.",
        )
    )
    # Distinct letters, so a leak of somebody else's answer would be visible in the prompt.
    bank = make_bank(["A", "B", "C", "D"])
    context = build_context(choice_task, pool, bank, client=client)
    run("chair_information_seeking", context)

    member_prompt = next(
        r for r in client.requests if "The team's chair asks" in str(r["messages"])
    )
    content = "\n".join(str(m["content"]) for m in member_prompt["messages"])
    assert "The answer is 'B'." in content  # its own prior answer
    for foreign in ("'A'", "'C'", "'D'"):
        assert foreign not in content
    assert "Member" not in content  # not told who else was asked


def test_chair_respects_the_respondent_cap(choice_task, pool, make_bank, stub_client):
    """A chair naming everyone must not silently turn a 4-call episode into an n+2-call one."""
    client = stub_client(
        scripted(
            {
                "you may ask for exactly one piece": chair_reply(
                    ask="Member 1, Member 2, Member 3, Member 4"
                )
            },
            default="The answer is 'B'.",
        )
    )
    context = build_context(choice_task, pool, make_bank(["A", "B", "B", "A"]), client=client)
    result = run("chair_information_seeking", context)
    assert result.meta["n_respondents"] == MAX_RESPONDENTS
    assert client.n_calls == 2 + MAX_RESPONDENTS


def test_chair_records_whether_it_questioned_the_predicted_expert(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(
        scripted(
            {"you may ask for exactly one piece": chair_reply(ask="Member 4")},
            default="The answer is 'B'.",
        )
    )
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "B", "A"]), client=client, predicted_expert_id=1
    )
    result = run("chair_information_seeking", context)
    assert result.meta["query_targets"] == [3]
    assert result.meta["queried_predicted_expert"] is False


def test_chair_records_what_a_vote_would_have_said(choice_task, pool, make_bank, stub_client):
    """The chair-versus-vote difference is the quantity of interest, so it must be recorded."""
    client = stub_client(
        scripted(
            {"you may ask for exactly one piece": NO_QUESTION_SENTINEL},
            default="Weighing the evidence, the answer is 'B'.",
        )
    )
    # A 3-1 wrong majority: the vote says A, so an evidence-led chair must be able to override.
    context = build_context(choice_task, pool, make_bank(["A", "B", "A", "A"]), client=client)
    result = run("chair_information_seeking", context)
    assert result.meta["vote_would_have_said"] == "A"
    assert result.meta["chair_overrode_vote"] is True
    assert result.final_answer == "B"


def test_chair_requires_an_aggregator(choice_task, pool, make_bank, stub_client):
    from dataclasses import replace

    context = build_context(
        choice_task,
        replace(pool, aggregator=None),
        make_bank(["A", "B", "B", "A"]),
        client=stub_client(),
    )
    with pytest.raises(ValueError, match="no aggregator"):
        asyncio.run(get_protocol("chair_information_seeking").fn(context))


def test_reorder_intervention_permutes_who_member_one_is(
    choice_task, pool, make_bank, stub_client
):
    """The chair's labels are positional, so a reorder must redirect the question."""
    client = stub_client(
        scripted(
            {"you may ask for exactly one piece": chair_reply(ask="Member 1")},
            default="The answer is 'B'.",
        )
    )
    context = build_context(
        choice_task,
        pool,
        make_bank(["A", "B", "B", "A"]),
        client=client,
        intervention=InterventionSpec(kind="reorder", order=[3, 2, 1, 0]),
    )
    result = run("chair_information_seeking", context)
    assert result.meta["visible_order"] == [3, 2, 1, 0]
    assert result.meta["query_targets"] == [3]


# ---- the chair's reply parser ---------------------------------------------------------------


def test_parser_maps_labels_through_the_presented_order():
    question, targets = parse_chair_query(chair_reply(ask="Member 2"), order=[5, 7, 9])
    assert question
    assert targets == [7]


def test_parser_treats_the_sentinel_as_no_question():
    assert parse_chair_query(f"  {NO_QUESTION_SENTINEL}  ", order=[0, 1]) == ("", [])


def test_parser_drops_out_of_range_and_duplicate_labels():
    _, targets = parse_chair_query(
        chair_reply(ask="Member 1, Member 1, Member 9"), order=[4, 5]
    )
    assert targets == [4]


def test_parser_broadcasts_a_question_with_no_usable_addressee():
    """A malformed ASK line must not silently discard a question the chair did ask."""
    question, targets = parse_chair_query(
        f"{QUESTION_PREFIX} What is the source?\n{ASK_PREFIX} everyone please", order=[0, 1, 2]
    )
    assert question == "What is the source?"
    assert targets == [0, 1][:MAX_RESPONDENTS]


def test_parser_accepts_a_question_asked_in_prose():
    question, targets = parse_chair_query(
        "Which handbook lists that value?\nASK: Member 1", order=[0, 1]
    )
    assert question == "Which handbook lists that value?"
    assert targets == [0]


def test_parser_returns_nothing_for_an_empty_reply():
    assert parse_chair_query("", order=[0, 1]) == ("", [])
    assert parse_chair_query("   \n  ", order=[0, 1]) == ("", [])
