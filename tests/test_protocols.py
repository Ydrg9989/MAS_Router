"""Protocol behaviour, cost profile, and the observability claims in the protocol card.

Every test runs offline against a scripted client. Two themes recur, because they are the
things most likely to silently break the science:

* the two aggregation-only protocols must make **zero** model calls, since the whole
  two-stage design (D-001, D-009) is justified by that being true;
* the protocols must reproduce the phenomena the research report is about — correct-answer
  dilution, rescue, abstention — on planted inputs where the right answer is known.
"""

from __future__ import annotations

import asyncio

import pytest

from mas_harness.protocols import FREE_PROTOCOLS, MVP_PROTOCOLS, ProtocolContext, get_protocol
from mas_harness.protocols.voting import tally
from mas_harness.records.schema import InterventionSpec
from mas_harness.tasks.adapters import build_evaluator


def build_context(choice_task, pool, bank, **overrides) -> ProtocolContext:
    defaults = dict(
        spec=choice_task,
        evaluator=build_evaluator(choice_task),
        pool=pool,
        coalition=sorted(bank),
        seed=0,
        bank=bank,
        competence={0: 0.9, 1: 0.6, 2: 0.5, 3: 0.4},
        max_rounds=2,
    )
    defaults.update(overrides)
    return ProtocolContext(**defaults)


def run(protocol_id: str, context: ProtocolContext):
    return asyncio.run(get_protocol(protocol_id).fn(context))


# ---- contract -------------------------------------------------------------------------


def test_every_mvp_protocol_is_registered():
    for protocol_id in MVP_PROTOCOLS:
        assert get_protocol(protocol_id).fn is not None


def test_context_rejects_a_bank_missing_a_coalition_member(choice_task, pool, make_bank):
    bank = make_bank(["B", "B", "A", "A"])
    del bank[3]
    with pytest.raises(ValueError, match="missing banked answers"):
        ProtocolContext(
            spec=choice_task,
            evaluator=build_evaluator(choice_task),
            pool=pool,
            coalition=[0, 1, 2, 3],
            seed=0,
            bank=bank,
        )


@pytest.mark.parametrize("protocol_id", sorted(FREE_PROTOCOLS))
def test_free_protocols_make_no_model_calls(protocol_id, choice_task, pool, make_bank):
    """D-009. If this ever fails, the cost model of the whole project is wrong."""
    context = build_context(choice_task, pool, make_bank(["B", "A", "A", "C"]), client=None)
    result = run(protocol_id, context)
    assert result.calls == []
    assert result.total_cost_usd == 0.0
    assert result.meta["n_model_calls"] == 0


def test_interactive_protocols_refuse_to_run_without_a_client(choice_task, pool, make_bank):
    context = build_context(choice_task, pool, make_bank(["B", "A", "A", "C"]), client=None)
    for protocol_id in ("debate_vote", "independent_judge"):
        with pytest.raises(RuntimeError, match="no client was provided"):
            run(protocol_id, context)


# ---- single expert ---------------------------------------------------------------------


def test_single_expert_uses_the_predicted_expert(choice_task, pool, make_bank):
    bank = make_bank(["A", "B", "A", "A"])
    context = build_context(choice_task, pool, bank, predicted_expert_id=1)
    result = run("single_expert", context)
    assert result.final_answer == "B"
    assert result.meta["selected_agent_id"] == 1
    assert result.meta["used_competence_fallback"] is False


def test_single_expert_falls_back_visibly_when_no_expert_is_predicted(
    choice_task, pool, make_bank
):
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "C", "D"]), predicted_expert_id=None
    )
    result = run("single_expert", context)
    # Agent 0 has the highest competence in the fixture.
    assert result.meta["selected_agent_id"] == 0
    assert result.meta["used_competence_fallback"] is True


def test_single_expert_never_selects_a_non_member(choice_task, pool, make_bank):
    bank = make_bank(["A", "B", "C", "D"])
    coalition = [2, 3]
    context = build_context(
        choice_task,
        pool,
        {a: bank[a] for a in coalition},
        coalition=coalition,
        predicted_expert_id=0,
    )
    result = run("single_expert", context)
    assert result.meta["selected_agent_id"] in coalition


# ---- majority: dilution, rescue, abstention -------------------------------------------


def test_majority_dilutes_a_lone_correct_expert(choice_task, pool, make_bank):
    """The phenomenon the governance direction exists to study.

    Agent 1 is right; three teammates agree on a wrong answer. A plurality vote discards the
    correct answer, while single_expert keeps it. The gap between the two protocols on the
    same bank *is* the dilution.
    """
    bank = make_bank(["A", "B", "A", "A"])
    majority = run("independent_majority", build_context(choice_task, pool, bank))
    expert = run(
        "single_expert", build_context(choice_task, pool, bank, predicted_expert_id=1)
    )

    assert majority.final_answer == "A"
    assert expert.final_answer == "B" == choice_task.ground_truth
    assert majority.meta["vote_counts"] == {"A": 3, "B": 1}
    assert majority.meta["absolute_majority"] is True


def test_majority_rescues_a_wrong_expert(choice_task, pool, make_bank):
    """The mirror case: the vote is right where the predicted expert is wrong."""
    bank = make_bank(["B", "A", "B", "B"])
    majority = run("independent_majority", build_context(choice_task, pool, bank))
    expert = run(
        "single_expert", build_context(choice_task, pool, bank, predicted_expert_id=1)
    )
    assert majority.final_answer == "B" == choice_task.ground_truth
    assert expert.final_answer == "A"


def test_abstentions_are_excluded_from_the_tally(choice_task, pool, make_bank):
    """D-011. An agent that declares no answer must not be counted as voting."""
    bank = make_bank(["B", "A", "A", "A"])
    bank[2] = bank[2].model_copy(
        update={
            "text": "I have nothing to add.",
            "extracted_answer": "",
            "parse_failed": True,
            "correct": False,
        }
    )
    bank[3] = bank[3].model_copy(
        update={
            "text": "I defer to my colleagues.",
            "extracted_answer": "",
            "parse_failed": True,
            "correct": False,
        }
    )
    result = run("independent_majority", build_context(choice_task, pool, bank))
    assert sorted(result.meta["abstentions"]) == [2, 3]
    assert result.meta["n_voting"] == 2
    assert result.meta["vote_counts"] == {"B": 1, "A": 1}
    # A 1-1 tie among voters, broken by competence: agent 0 (0.9) outranks agent 1 (0.6).
    assert result.meta["tie_break"] == "competence"
    assert result.final_answer == "B"


def test_answers_are_grouped_by_equivalence_not_string(pool, make_bank):
    """1/2 and 0.5 are one vote for the same position, not a split."""
    from mas_harness.tasks.adapters import TaskSpec

    math_task = TaskSpec(
        task_id="math500::demo",
        suite="math500",
        domain="algebra",
        answer_type="boxed_math",
        prompt="p",
        ground_truth="0.5",
        payload={"problem": "p", "solution": "\\boxed{0.5}"},
    )
    evaluator = build_evaluator(math_task)
    answers = {0: "1/2", 1: "0.5", 2: "\\frac{1}{2}", 3: "7"}
    result = tally(answers, evaluator)
    assert len(result.groups) == 2
    assert len(result.winner_support) == 3
    assert evaluator.score_extracted(result.winner)


def test_tally_with_no_votes_reports_no_winner(choice_task):
    evaluator = build_evaluator(choice_task)
    result = tally({0: "", 1: ""}, evaluator)
    assert result.winner == ""
    assert result.tie_break == "no_votes"
    assert result.n_voting == 0


# ---- judge ------------------------------------------------------------------------------


def test_judge_makes_exactly_one_call_and_sees_every_member(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client()
    bank = make_bank(["A", "B", "A", "A"])
    result = run("independent_judge", build_context(choice_task, pool, bank, client=client))

    assert client.n_calls == 1
    assert result.meta["n_model_calls"] == 1
    prompt = client.user_content(0)
    for letter in ("A", "B"):
        assert f"The answer is '{letter}'" in prompt
    # Four members rendered, all anonymized.
    for position in range(1, 5):
        assert f"Member {position}" in prompt
    for agent in pool.agents:
        assert agent.name not in prompt


def test_judge_override_of_the_vote_is_recorded(choice_task, pool, make_bank, stub_client):
    """The judge-versus-vote difference is the quantity of interest, so it is explicit."""
    bank = make_bank(["A", "A", "A", "B"])
    client = stub_client(lambda request: "Reviewing the reasoning. The answer is 'B'.")
    result = run("independent_judge", build_context(choice_task, pool, bank, client=client))
    assert result.final_answer == "B"
    assert result.meta["vote_would_have_said"] == "A"
    assert result.meta["judge_overrode_vote"] is True


def test_judge_requires_an_aggregator(choice_task, pool, make_bank, stub_client):
    from dataclasses import replace

    poolless = replace(pool, aggregator=None)
    context = build_context(choice_task, poolless, make_bank(["A", "B", "A", "A"]),
                            client=stub_client())
    with pytest.raises(ValueError, match="defines no aggregator"):
        run("independent_judge", context)


# ---- debate ------------------------------------------------------------------------------


def test_debate_costs_one_call_per_member_per_revision_round(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client()
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "A", "A"]), client=client, max_rounds=2
    )
    result = run("debate_vote", context)
    assert client.n_calls == 4  # 4 members x (2 rounds - 1 free round)
    assert result.meta["n_model_calls"] == 4
    assert get_protocol("debate_vote").calls_per_episode(4, 2) == 4


def test_debate_with_one_round_is_free_and_equals_the_vote(
    choice_task, pool, make_bank, stub_client
):
    """Round 0 is the bank, so a single-round debate must not call anything."""
    client = stub_client()
    bank = make_bank(["A", "B", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, max_rounds=1)
    result = run("debate_vote", context)
    assert client.n_calls == 0
    assert result.final_answer == "A"


def test_debate_members_see_peers_but_not_their_own_answer_as_a_peer(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client()
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "C", "D"]), client=client, max_rounds=2
    )
    run("debate_vote", context)
    for index in range(4):
        prompt = client.user_content(index)
        # Three peers are shown, so exactly three positional labels appear.
        assert sum(f"Member {position}" in prompt for position in range(1, 5)) == 3
        assert "You previously answered" in prompt


def test_debate_records_who_switched(choice_task, pool, make_bank, stub_client):
    # Everyone is told to answer B; agents 0, 2 and 3 started on A and must be logged.
    client = stub_client(lambda request: "On reflection. The answer is 'B'.")
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "A", "A"]), client=client, max_rounds=2
    )
    result = run("debate_vote", context)
    assert result.meta["n_agents_switched_answer"] == 3
    assert result.meta["round_history"][1]["changed"] == [0, 2, 3]
    assert result.final_answer == "B"


# ---- expert + verifier -------------------------------------------------------------------


def test_verifier_approval_skips_the_revision_call(choice_task, pool, make_bank, stub_client):
    client = stub_client(lambda request: "NO ERROR FOUND")
    bank = make_bank(["A", "B", "A", "A"])
    context = build_context(
        choice_task, pool, bank, client=client, predicted_expert_id=1
    )
    result = run("expert_verifier", context)
    assert client.n_calls == 1
    assert result.meta["verifier_objected"] is False
    assert result.meta["expert_changed_answer"] is False
    assert result.final_answer == "B"


def test_verifier_objection_triggers_a_revision(choice_task, pool, make_bank, stub_client):
    def responder(request):
        content = "\n".join(str(m["content"]) for m in request["messages"])
        if "A reviewer said" in content:
            return "You are right to object. The answer is 'B'."
        return "Step three is wrong: the sign is inverted."

    client = stub_client(responder)
    bank = make_bank(["A", "A", "A", "A"])
    context = build_context(choice_task, pool, bank, client=client, predicted_expert_id=0)
    result = run("expert_verifier", context)

    assert client.n_calls == 2
    assert result.meta["verifier_objected"] is True
    assert result.meta["expert_initial_answer"] == "A"
    assert result.meta["expert_changed_answer"] is True
    # A rescue: the expert was wrong and the review fixed it.
    assert result.final_answer == choice_task.ground_truth


def test_verifier_can_dilute_a_correct_expert(choice_task, pool, make_bank, stub_client):
    """The failure mode the report cares about: review talks a correct expert out of it."""

    def responder(request):
        content = "\n".join(str(m["content"]) for m in request["messages"])
        if "A reviewer said" in content:
            return "Fair point, I withdraw. The answer is 'A'."
        return "I believe option B misreads the question."

    client = stub_client(responder)
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "A", "A"]), client=client, predicted_expert_id=1
    )
    result = run("expert_verifier", context)
    assert result.meta["expert_initial_answer"] == "B"
    assert result.final_answer == "A"
    assert result.meta["expert_changed_answer"] is True


def test_verifier_prefers_the_role_designated_member(choice_task, pool, make_bank, stub_client):
    client = stub_client(lambda request: "NO ERROR FOUND")
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "A", "A"]), client=client, predicted_expert_id=0
    )
    result = run("expert_verifier", context)
    # Agent 2 carries role='verifier' in the fixture pool.
    assert result.meta["verifier_agent_id"] == 2
    assert result.meta["verifier_selection_rule"] == "role"


def test_singleton_coalition_degenerates_without_spending(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client()
    bank = make_bank(["B", "A", "A", "A"])
    context = build_context(
        choice_task,
        pool,
        {0: bank[0]},
        coalition=[0],
        client=client,
        predicted_expert_id=0,
    )
    result = run("expert_verifier", context)
    assert client.n_calls == 0
    assert result.meta["degenerate_singleton"] is True
    assert result.final_answer == "B"


def test_verifier_does_not_learn_who_wrote_the_answer(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client(lambda request: "NO ERROR FOUND")
    context = build_context(
        choice_task, pool, make_bank(["A", "B", "A", "A"]), client=client, predicted_expert_id=1
    )
    run("expert_verifier", context)
    prompt = client.user_content(0)
    assert "A team member proposed" in prompt
    assert "beta" not in prompt  # the expert's name


# ---- speaking order ----------------------------------------------------------------------


def test_reorder_intervention_changes_the_presentation_order(
    choice_task, pool, make_bank, stub_client
):
    client = stub_client()
    bank = make_bank(["A", "B", "C", "D"])
    context = build_context(
        choice_task,
        pool,
        bank,
        client=client,
        intervention=InterventionSpec(kind="reorder", order=[3, 2, 1, 0]),
    )
    assert context.speaking_order() == [3, 2, 1, 0]
    run("independent_judge", context)
    prompt = client.user_content(0)
    # Member 1 is now agent 3, whose answer is D.
    assert prompt.index("The answer is 'D'") < prompt.index("The answer is 'A'")


def test_reorder_with_a_partial_order_keeps_every_member(choice_task, pool, make_bank):
    context = build_context(
        choice_task,
        pool,
        make_bank(["A", "B", "C", "D"]),
        intervention=InterventionSpec(kind="reorder", order=[2, 0]),
    )
    assert sorted(context.speaking_order()) == [0, 1, 2, 3]
    assert context.speaking_order()[:2] == [2, 0]
