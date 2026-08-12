<!-- doc-meta
type:          generated
lifecycle:     REGENERATE from mas_harness.protocols.protocol_card(); header block is hand-maintained
last-verified: 2026-08-11
evidence-base: mas_harness/protocols/ registry
-->

<!-- GENERATED FILE. Do not edit by hand.

Regenerate the BODY with:
    .venv/bin/python -c "from mas_harness.protocols import protocol_card; print(protocol_card())"

then re-prepend this header block, which is hand-maintained and is NOT produced by
protocol_card(). Everything below the header is generated.

This card is generated from the protocol registry itself, so it cannot drift from the code.
Its purpose is to make the observability of each protocol reviewable: what a participant can
see determines what a result means, and "the expert was ignored" is only interesting if the
others could not simply see who the expert was. Every claim below is checked by a test in
tests/test_protocols.py or tests/test_governance_protocols.py.

Known limitation: anonymization applies to the *labels* on messages, not to their content. A
model that writes "As GPT-5 I think..." de-anonymizes itself and the harness does not rewrite
it. Measured on real transcripts before any de-anonymization claim is made in the paper.
-->

# Protocol card

## chair_information_seeking

A neutral chair reads the independent answers, may ask one targeted question of up to two members, then decides. Two to four model calls. Paired with independent_judge, which decides from the same answers without asking, so the pair isolates the value of soliciting evidence that was never volunteered.

- interactive: True
- uses predicted expert: False
- model calls for a 4-agent coalition, 2 rounds: 4
- observability: The chair sees the task and every member's full response, anonymized to positional labels, and later the replies to its question. A queried member sees the task, its own prior answer and the question, but not other members' answers and not who else was asked. Nobody sees ground truth or competence estimates.

## debate_vote

Members see each other's independent answers, revise once per round, then vote on final positions. Round 0 is replayed free from the answer bank; only revisions cost money. Revision is simultaneous within a round, so speaking order is not a hidden variable.

- interactive: True
- uses predicted expert: False
- model calls for a 4-agent coalition, 2 rounds: 4
- observability: Each member sees the task, its own previous answer, and every other member's previous answer under anonymized positional labels. No member sees ground truth or any competence estimate.

## expert_verifier

The predicted expert's banked answer is reviewed by one other member, then the expert may revise. Two model calls. Isolates the effect of a single review from the effect of a full debate, so rescue and dilution are separately identifiable.

- interactive: True
- uses predicted expert: True
- model calls for a 4-agent coalition, 2 rounds: 2
- observability: The verifier sees the task and the expert's full answer, but not who wrote it and not any other member's answer. The expert then sees the critique but not the verifier's identity. Neither sees ground truth or competence estimates.

## expert_veto

The predicted expert's answer stands unless a challenger both identifies a specific error and names a different answer. One model call. Paired with expert_verifier, which spends the same call but gives the expert the last word, so the pair isolates the decision rule from the review.

- interactive: True
- uses predicted expert: True
- model calls for a 4-agent coalition, 2 rounds: 1
- observability: The challenger sees the task and the expert's full answer, anonymized, and is told that the answer stands by default. It does not see other members' answers, the expert's identity, competence estimates, or ground truth. The expert is not consulted again, so it never sees the challenge.

## independent_judge

A neutral aggregator that did not attempt the task reads every independent answer and picks the final one. One model call. Tests whether an outside reader can recognise the correct answer that a vote would have discarded.

- interactive: False
- uses predicted expert: False
- model calls for a 4-agent coalition, 2 rounds: 1
- observability: The judge sees the task and every member's full response, anonymized to positional labels. Members see nothing.

## independent_majority

Plurality vote over the independent answers, with answers grouped by task equivalence and abstentions excluded. Ties break on summed calibration competence. No interaction, so no influence: this isolates aggregation from persuasion.

- interactive: False
- uses predicted expert: False
- model calls for a 4-agent coalition, 2 rounds: 0
- observability: No member observes any other member. The aggregation is mechanical and sees only the extracted answers.

## single_expert

The predicted expert answers alone. No interaction. This is the calibrated top-1 routing baseline: if no protocol beats it, team structure is not buying anything and the governance question is moot.

- interactive: False
- uses predicted expert: True
- model calls for a 4-agent coalition, 2 rounds: 0
- observability: The expert sees only the task. No member observes any other member.

