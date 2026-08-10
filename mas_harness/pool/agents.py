"""Agent pool definitions.

An agent is a model slug plus a provider, a role and sampling settings. Heterogeneity is
expressed by putting different model *families* in one pool, which is the axis the
research questions are about: the report warns that a measured "verifier effect" could
otherwise just be a model-family effect, which is why ``family`` is recorded separately
from ``model`` and why role rotation exists (see :mod:`mas_harness.pool.roles`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

VALID_PROVIDERS = frozenset({"openrouter", "vllm"})
VALID_ROLES = frozenset({"generalist", "solver", "verifier", "evidence_curator", "aggregator"})


@dataclass(frozen=True)
class Agent:
    """One member of a pool."""

    agent_id: int
    name: str
    provider: str
    model: str
    role: str = "generalist"
    family: str = "unknown"
    temperature: float = 0.0
    max_tokens: int = 1024
    system_prompt: str = ""
    # Set only by the distributed-information suite; the private evidence this agent holds.
    hidden_context: str = ""
    extra_body: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider not in VALID_PROVIDERS:
            raise ValueError(
                f"agent {self.name!r}: provider {self.provider!r} not in {sorted(VALID_PROVIDERS)}"
            )
        if self.role not in VALID_ROLES:
            raise ValueError(
                f"agent {self.name!r}: role {self.role!r} not in {sorted(VALID_ROLES)}"
            )

    def with_role(self, role: str) -> "Agent":
        return Agent(**{**self.__dict__, "role": role})

    def with_hidden_context(self, hidden_context: str) -> "Agent":
        return Agent(**{**self.__dict__, "hidden_context": hidden_context})

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class AgentPool:
    """An ordered, immutable set of agents with a stable id."""

    pool_id: str
    agents: tuple[Agent, ...]
    description: str = ""
    # The model used to aggregate or judge when a protocol needs a neutral third party.
    # Kept separate from the pool so aggregation cost does not depend on coalition
    # membership, which would confound v_x(S) (D-008).
    aggregator: Agent | None = None

    def __post_init__(self) -> None:
        ids = [a.agent_id for a in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError(f"pool {self.pool_id!r} has duplicate agent_ids: {ids}")
        if sorted(ids) != list(range(len(ids))):
            raise ValueError(
                f"pool {self.pool_id!r} agent_ids must be 0..n-1 for coalition "
                f"bitmasking, got {ids}"
            )

    def __len__(self) -> int:
        return len(self.agents)

    def __iter__(self):
        return iter(self.agents)

    @property
    def agent_ids(self) -> list[int]:
        return [a.agent_id for a in self.agents]

    @property
    def families(self) -> list[str]:
        return [a.family for a in self.agents]

    def by_id(self, agent_id: int) -> Agent:
        for agent in self.agents:
            if agent.agent_id == agent_id:
                return agent
        raise KeyError(f"no agent {agent_id} in pool {self.pool_id!r}")

    def subset(self, agent_ids: Iterable[int]) -> list[Agent]:
        wanted = set(agent_ids)
        return [a for a in self.agents if a.agent_id in wanted]

    @property
    def models(self) -> list[str]:
        """Every distinct model slug used by the pool, including the aggregator."""
        slugs = [a.model for a in self.agents]
        if self.aggregator is not None:
            slugs.append(self.aggregator.model)
        return sorted(set(slugs))

    @property
    def content_hash(self) -> str:
        payload = {
            "pool_id": self.pool_id,
            "agents": [a.to_dict() for a in self.agents],
            "aggregator": self.aggregator.to_dict() if self.aggregator else None,
        }
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "pool_id": self.pool_id,
            "description": self.description,
            "content_hash": self.content_hash,
            "agents": [a.to_dict() for a in self.agents],
            "aggregator": self.aggregator.to_dict() if self.aggregator else None,
        }

    def with_roles(self, roles: Sequence[str], *, pool_id: str | None = None) -> "AgentPool":
        """Return a copy with roles reassigned in agent order (used by role rotation).

        A rotation must be given its own ``pool_id``: episodes are keyed on it, so reusing the
        base id would make two rotations collide in the resume set and silently drop one.
        """
        if len(roles) != len(self.agents):
            raise ValueError(f"expected {len(self.agents)} roles, got {len(roles)}")
        return AgentPool(
            pool_id=pool_id or self.pool_id,
            agents=tuple(a.with_role(r) for a, r in zip(self.agents, roles, strict=True)),
            description=self.description,
            aggregator=self.aggregator,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentPool":
        agents = []
        for index, entry in enumerate(payload["agents"]):
            entry = dict(entry)
            entry.setdefault("agent_id", index)
            entry.setdefault("name", entry["model"].split("/")[-1])
            agents.append(Agent(**entry))
        aggregator_entry = payload.get("aggregator")
        aggregator = None
        if aggregator_entry:
            aggregator_entry = dict(aggregator_entry)
            # The aggregator is not a pool member; -1 keeps it out of coalition bitmasks.
            aggregator_entry.setdefault("agent_id", -1)
            aggregator_entry.setdefault("name", aggregator_entry["model"].split("/")[-1])
            aggregator_entry.setdefault("role", "aggregator")
            aggregator = Agent(**aggregator_entry)
        return cls(
            pool_id=payload["pool_id"],
            agents=tuple(agents),
            description=payload.get("description", ""),
            aggregator=aggregator,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentPool":
        return cls.from_dict(yaml.safe_load(Path(path).read_text()))


def all_nonempty_coalitions(agent_ids: Sequence[int]) -> list[list[int]]:
    """Every non-empty subset, ordered by size then lexicographically.

    For four agents this is the 15 subsets the research report enumerates exhaustively.
    Refuses above 12 agents, where exhaustive enumeration stops being sane.
    """
    n = len(agent_ids)
    if n > 12:
        raise ValueError(f"exhaustive coalition enumeration refused for {n} agents (2^{n} subsets)")
    ids = sorted(agent_ids)
    subsets: list[list[int]] = []
    for mask in range(1, 1 << n):
        subsets.append([ids[i] for i in range(n) if mask & (1 << i)])
    subsets.sort(key=lambda s: (len(s), s))
    return subsets


def coalitions_of_size(agent_ids: Sequence[int], size: int) -> list[list[int]]:
    from itertools import combinations

    return [list(c) for c in combinations(sorted(agent_ids), size)]
