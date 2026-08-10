"""Vote tallying with explicit abstention handling.

Abstention is a real outcome here, not a zero (D-011): an agent whose message declares no
answer is excluded from the tally rather than counted as voting for something. Recording
abstentions separately is what lets the governance metrics distinguish "the expert was
drowned out" from "the expert never spoke".

Answers are grouped by *equivalence*, not string identity, so that ``1/2`` and ``0.5`` are
one vote for the same position rather than two votes that split the correct answer. Doing
this by string comparison would systematically understate agreement on math tasks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..tasks.adapters import TeamworkEvaluator


@dataclass
class VoteTally:
    """The result of counting votes over a set of answers."""

    votes: dict[int, str] = field(default_factory=dict)
    abstentions: list[int] = field(default_factory=list)
    # Canonical answer -> the agents supporting it.
    groups: dict[str, list[int]] = field(default_factory=dict)
    winner: str = ""
    winner_support: list[int] = field(default_factory=list)
    tied_with: list[str] = field(default_factory=list)
    tie_break: str = "none"

    @property
    def counts(self) -> dict[str, int]:
        return {answer: len(agents) for answer, agents in self.groups.items()}

    @property
    def n_voting(self) -> int:
        return len(self.votes) - len(self.abstentions)

    @property
    def unanimous(self) -> bool:
        return self.n_voting > 0 and len(self.groups) == 1

    def to_meta(self) -> dict[str, Any]:
        return {
            "votes": {str(k): v for k, v in sorted(self.votes.items())},
            "vote_counts": self.counts,
            "vote_groups": {k: sorted(v) for k, v in sorted(self.groups.items())},
            "abstentions": sorted(self.abstentions),
            "n_voting": self.n_voting,
            "winner": self.winner,
            "winner_support": sorted(self.winner_support),
            "tied_with": sorted(self.tied_with),
            "tie_break": self.tie_break,
            "unanimous": self.unanimous,
        }


def group_equivalent(
    answers: Mapping[int, str], evaluator: TeamworkEvaluator
) -> dict[str, list[int]]:
    """Group agents by answer equivalence, using the task's own equivalence relation.

    The canonical label for a group is the first answer string seen for it, so labels are
    stable given a stable agent order.
    """
    groups: dict[str, list[int]] = {}
    for agent_id in sorted(answers):
        answer = answers[agent_id]
        if not answer:
            continue
        for canonical in groups:
            if evaluator.equivalent(answer, canonical):
                groups[canonical].append(agent_id)
                break
        else:
            groups[answer] = [agent_id]
    return groups


def tally(
    answers: Mapping[int, str],
    evaluator: TeamworkEvaluator,
    *,
    competence: Mapping[int, float] | None = None,
    priority: Sequence[int] | None = None,
) -> VoteTally:
    """Count votes, breaking ties deterministically.

    Ties are broken in this order, and the mechanism used is always recorded:

    1. ``priority`` — an ordered list of agents whose vote wins a tie. Protocols pass the
       predicted expert here, which is exactly the "authority" manipulation under study.
    2. summed calibration competence of each answer's supporters.
    3. lowest supporting agent id, so a rerun is reproducible.

    A tie broken by coin flip would add variance to every protocol comparison and make the
    paired tests less sensitive, so there is no random branch.
    """
    votes = {int(a): (answers[a] or "").strip() for a in answers}
    abstentions = [a for a, answer in votes.items() if not answer]
    groups = group_equivalent(votes, evaluator)

    result = VoteTally(votes=votes, abstentions=abstentions, groups=groups)
    if not groups:
        result.tie_break = "no_votes"
        return result

    top = max(len(agents) for agents in groups.values())
    leaders = [answer for answer, agents in groups.items() if len(agents) == top]

    if len(leaders) == 1:
        result.winner = leaders[0]
        result.winner_support = groups[leaders[0]]
        result.tie_break = "none"
        return result

    result.tied_with = leaders

    if priority:
        for agent_id in priority:
            for answer in leaders:
                if agent_id in groups[answer]:
                    result.winner = answer
                    result.winner_support = groups[answer]
                    result.tie_break = f"priority_agent_{agent_id}"
                    return result

    if competence:
        scored = {
            answer: sum(competence.get(a, 0.0) for a in groups[answer]) for answer in leaders
        }
        best = max(scored.values())
        best_answers = [a for a, s in scored.items() if s == best]
        if len(best_answers) == 1:
            result.winner = best_answers[0]
            result.winner_support = groups[best_answers[0]]
            result.tie_break = "competence"
            return result
        leaders = best_answers

    winner = min(leaders, key=lambda answer: min(groups[answer]))
    result.winner = winner
    result.winner_support = groups[winner]
    result.tie_break = "lowest_agent_id"
    return result


def majority_threshold_met(result: VoteTally, *, strict: bool = True) -> bool:
    """Whether the winner holds an absolute majority of the non-abstaining voters."""
    if not result.winner:
        return False
    support = len(result.winner_support)
    return support * 2 > result.n_voting if strict else support * 2 >= result.n_voting
