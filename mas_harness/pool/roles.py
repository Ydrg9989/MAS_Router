"""Latin-square role rotation.

The research report is explicit about this confound: if one model family always plays the
verifier, a measured "verifier effect" is indistinguishable from a model-family effect.
The fix is to rotate the same families through every role on a stratified subset, so that
role and family are crossed rather than nested.

A Latin square gives each agent every role exactly once across the rotations, and each
role exactly one agent per rotation, with the minimum number of runs (n rotations rather
than n! permutations).
"""

from __future__ import annotations

from typing import Sequence

from .agents import AgentPool

# Role set used by the asymmetric protocols. Order matters: it defines the square.
DEFAULT_ROLE_CYCLE: tuple[str, ...] = ("solver", "verifier", "evidence_curator", "generalist")


def latin_square(n: int) -> list[list[int]]:
    """A cyclic Latin square of order n: row r assigns column c the value (c + r) mod n."""
    if n < 1:
        raise ValueError(f"n must be positive, got {n}")
    return [[(column + row) % n for column in range(n)] for row in range(n)]


def role_rotations(
    pool: AgentPool,
    *,
    roles: Sequence[str] = DEFAULT_ROLE_CYCLE,
) -> list[tuple[str, AgentPool]]:
    """Every rotation of ``roles`` across ``pool``, as (rotation_id, pool) pairs.

    Requires as many roles as agents, because a Latin square is square. With four agents
    and four roles this yields four pools, and every agent holds every role once.
    """
    n = len(pool)
    if len(roles) != n:
        raise ValueError(
            f"role rotation needs one role per agent: pool has {n} agents, "
            f"{len(roles)} roles given ({list(roles)})"
        )

    rotations: list[tuple[str, AgentPool]] = []
    for row_index, row in enumerate(latin_square(n)):
        assigned = [roles[value] for value in row]
        rotation_id = f"rot{row_index}"
        rotations.append(
            (
                rotation_id,
                pool.with_roles(assigned, pool_id=f"{pool.pool_id}-{rotation_id}"),
            )
        )
    return rotations


def verify_crossed(rotations: Sequence[tuple[str, AgentPool]]) -> bool:
    """Confirm every agent holds every role exactly once across the rotations."""
    if not rotations:
        return False
    seen: dict[int, list[str]] = {}
    for _, pool in rotations:
        for agent in pool:
            seen.setdefault(agent.agent_id, []).append(agent.role)
    reference = sorted(set(next(iter(seen.values()))))
    every_agent_same_roles = all(sorted(set(roles)) == reference for roles in seen.values())
    no_agent_repeats_a_role = all(len(set(roles)) == len(roles) for roles in seen.values())
    return every_agent_same_roles and no_agent_repeats_a_role


ROLE_INSTRUCTIONS: dict[str, str] = {
    "generalist": (
        "You are a generalist team member. Reason about the problem on its merits and "
        "state your position clearly."
    ),
    "solver": (
        "You are the solver. Produce a complete solution with explicit reasoning. Do not "
        "defer to other members simply because they disagree; change your answer only for "
        "a stated reason."
    ),
    "verifier": (
        "You are the verifier. Your job is to look for concrete errors in the proposed "
        "answers: arithmetic slips, misread conditions, unjustified steps. Raise a "
        "specific objection with evidence, or state explicitly that you found no error. "
        "Do not object merely to appear rigorous."
    ),
    "evidence_curator": (
        "You are the evidence curator. Identify which facts the answer depends on, state "
        "which of them you can confirm, and name any that are missing or uncertain."
    ),
    "aggregator": (
        "You are a neutral aggregator. You did not attempt the problem yourself. Weigh the "
        "submitted answers on the quality of their reasoning and report a single final "
        "answer."
    ),
    "chair": (
        "You are the chair of a team that has already answered independently. You did not "
        "attempt the problem yourself. Your job is to find out what the team is missing "
        "before you decide: identify the specific fact or step the disagreement turns on, "
        "ask for it, and then decide on the evidence rather than on the head count."
    ),
}


def role_instruction(role: str) -> str:
    return ROLE_INSTRUCTIONS.get(role, ROLE_INSTRUCTIONS["generalist"])
