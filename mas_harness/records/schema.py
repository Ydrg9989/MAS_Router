"""Record schemas for the two experiment stages.

Everything the analysis layer needs is derivable from two append-only tables:

* ``answers.jsonl``  — one :class:`AnswerRecord` per (task, agent, seed) from Stage A
* ``episodes.jsonl`` — one :class:`EpisodeRecord` per (task, pool, protocol, coalition,
  seed, intervention) from Stage B

The governance metrics, the delegation utility matrix ``U(x, c)`` and the coalition value
tensor ``v_x(S)`` are all views over ``episodes.jsonl`` joined to ``answers.jsonl``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UsageDict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.output_tokens
        )


class CallRecord(BaseModel):
    """One LLM request made while running a protocol."""

    model_config = ConfigDict(extra="forbid")

    # What the call was for, e.g. "debate_round_1", "judge", "verifier".
    stage: str
    agent_id: int | None = None
    model: str
    provider: str
    model_returned: str | None = None
    usage: UsageDict = Field(default_factory=UsageDict)
    cost_usd: float = 0.0
    provider_reported_cost_usd: float | None = None
    cost_agrees: bool = True
    latency_ms: float = 0.0
    prompt_hash: str = ""
    cached: bool = False
    attempts: int = 1
    generation_id: str | None = None
    finish_reason: str | None = None


class TurnRecord(BaseModel):
    """One message in a transcript.

    ``speaker_id`` follows the upstream ``teamwork`` convention: -1 is the facilitator
    (a system-injected message, not a model call).
    """

    model_config = ConfigDict(extra="forbid")

    speaker_id: int
    role: str = "agent"
    stage: str = ""
    content: str


class AnswerRecord(BaseModel):
    """Stage A: one agent's independent answer to one task."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    run_id: str
    task_id: str
    suite: str
    domain: str
    agent_id: int
    agent_name: str
    model: str
    provider: str
    seed: int

    text: str
    extracted_answer: str
    ground_truth: str
    correct: bool
    parse_failed: bool

    call: CallRecord

    def key(self) -> tuple[str, int, int]:
        return (self.task_id, self.agent_id, self.seed)


InterventionKind = Literal["none", "mask", "substitute_correct", "substitute_wrong", "reorder"]


class InterventionSpec(BaseModel):
    """The ``do(.)`` applied to the answer bank before a Stage-B replay.

    ``none`` is the observational episode. Everything else is a counterfactual whose
    comparison against the matching observational episode gives the causal influence
    ``I_i(x, g)`` defined in the research report.
    """

    model_config = ConfigDict(extra="forbid")

    kind: InterventionKind = "none"
    # Which agent's message was intervened on. None for order permutations.
    target_agent_id: int | None = None
    # For reorder: the permutation of agent ids actually used.
    order: list[int] | None = None
    detail: str = ""

    def label(self) -> str:
        if self.kind == "none":
            return "none"
        if self.kind == "reorder":
            return f"reorder:{'-'.join(str(a) for a in (self.order or []))}"
        return f"{self.kind}:a{self.target_agent_id}"


class EpisodeRecord(BaseModel):
    """Stage B: one protocol run over one task with one coalition."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    run_id: str
    task_id: str
    suite: str
    domain: str

    pool_id: str
    protocol_id: str
    # Sorted agent ids that participated. Length 1 for singleton coalitions.
    coalition: list[int]
    seed: int
    intervention: InterventionSpec = Field(default_factory=InterventionSpec)

    final_text: str
    final_answer: str
    ground_truth: str
    correct: bool
    parse_failed: bool

    # ---- competence context, copied from the bank so episodes are self-contained ----
    individual_correct: dict[str, bool] = Field(default_factory=dict)
    predicted_expert_id: int | None = None
    oracle_expert_id: int | None = None
    # Protocol-internal outcomes: votes, declared expert, coordinator, veto fired, etc.
    protocol_meta: dict[str, Any] = Field(default_factory=dict)

    # ---- cost and provenance ----
    n_calls: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    usage: UsageDict = Field(default_factory=UsageDict)
    calls: list[CallRecord] = Field(default_factory=list)
    transcript: list[TurnRecord] = Field(default_factory=list)

    def key(self) -> tuple[str, str, str, str, int, str]:
        coalition = "-".join(str(a) for a in self.coalition)
        return (
            self.task_id,
            self.pool_id,
            self.protocol_id,
            coalition,
            self.seed,
            self.intervention.label(),
        )


class RunMeta(BaseModel):
    """Everything needed to reproduce a run, written once per run directory."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    created_at: str
    stage: str
    manifest_path: str
    manifest_hash: str
    pool_id: str
    pool_hash: str
    seeds: list[int]
    protocols: list[str] = Field(default_factory=list)
    pricing_snapshot: str = ""
    pricing_captured_at: str = ""
    upstream_pins: dict[str, str] = Field(default_factory=dict)
    harness_version: str = "0.1.0"
    git_commit: str | None = None
    notes: str = ""


def answer_key_str(task_id: str, agent_id: int, seed: int) -> str:
    return f"{task_id}|{agent_id}|{seed}"


def episode_key_str(
    task_id: str,
    pool_id: str,
    protocol_id: str,
    coalition: list[int],
    seed: int,
    intervention_label: str,
) -> str:
    members = "-".join(str(a) for a in sorted(coalition))
    return f"{task_id}|{pool_id}|{protocol_id}|{members}|{seed}|{intervention_label}"
