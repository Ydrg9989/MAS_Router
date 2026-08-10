"""Protocol contract, registry, and the shared prompt text.

A protocol is a function from a fixed answer bank to a final decision. It is *not* allowed
to collect independent answers: those come from Stage A and are the same bytes for every
protocol, which is what makes protocol comparisons paired and affordable (D-001).

Consequences of that contract, all of which the implementations rely on:

* A protocol that only aggregates makes zero API calls and costs nothing (D-009).
* Re-running a protocol under a causal intervention is cheap, because the intervention
  edits the bank rather than re-generating it.
* Two protocols compared on the same task see literally identical member answers, so a
  difference between them is attributable to the protocol and not to sampling noise.

Prompt text is centralized here rather than inlined per protocol, because the report
requires a protocol card documenting exactly what each participant can observe, and that
document has to be derivable from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence
from typing import Protocol as TypingProtocol

from ..clients.openrouter import ChatClient
from ..pool.agents import Agent, AgentPool
from ..pool.roles import role_instruction
from ..records.schema import AnswerRecord, CallRecord, InterventionSpec, TurnRecord, UsageDict
from ..tasks.adapters import TaskSpec, TeamworkEvaluator, answer_format_instruction

# Speaker id for system-injected messages, matching the upstream teamwork convention.
FACILITATOR = -1
# Speaker id for the neutral aggregator, which is not a pool member.
AGGREGATOR = -2

# Exact replies we instruct participants to use, so that "did this happen" is decided by
# string matching rather than by a second LLM interpreting the first one's output.
CONCEDE_SENTINEL = "NO OVERRIDE"
NO_QUESTION_SENTINEL = "NO QUESTION NEEDED"
QUESTION_PREFIX = "QUESTION:"
ASK_PREFIX = "ASK:"


@dataclass
class ProtocolContext:
    """Everything a protocol may read. Deliberately narrow."""

    spec: TaskSpec
    evaluator: TeamworkEvaluator
    pool: AgentPool
    coalition: list[int]
    seed: int
    # Banked independent answers for exactly the coalition members, from Stage A.
    bank: dict[int, AnswerRecord]
    predicted_expert_id: int | None = None
    oracle_expert_id: int | None = None
    intervention: InterventionSpec = field(default_factory=InterventionSpec)
    # Calibration accuracy per agent, used for competence-weighted tie-breaks.
    competence: dict[int, float] = field(default_factory=dict)
    client: ChatClient | None = None
    max_rounds: int = 1

    def __post_init__(self) -> None:
        missing = [a for a in self.coalition if a not in self.bank]
        if missing:
            raise ValueError(
                f"protocol context for task {self.spec.task_id} is missing banked answers for "
                f"agents {missing}. Stage A must cover every coalition member before Stage B."
            )

    def agent(self, agent_id: int) -> Agent:
        return self.pool.by_id(agent_id)

    def members(self) -> list[Agent]:
        return [self.pool.by_id(a) for a in self.coalition]

    def require_client(self, protocol_id: str) -> ChatClient:
        if self.client is None:
            raise RuntimeError(
                f"protocol {protocol_id!r} needs to issue model calls but no client was "
                f"provided. Pass one, or use --dry-run to plan the call volume."
            )
        return self.client

    def speaking_order(self) -> list[int]:
        """Coalition order after any reordering intervention."""
        if self.intervention.kind == "reorder" and self.intervention.order:
            requested = [a for a in self.intervention.order if a in set(self.coalition)]
            remaining = [a for a in self.coalition if a not in set(requested)]
            return requested + remaining
        return list(self.coalition)


@dataclass
class ProtocolResult:
    """What a protocol returns. The runner turns this into an EpisodeRecord."""

    final_text: str
    final_answer: str
    transcript: list[TurnRecord] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_latency_ms(self) -> float:
        return sum(c.latency_ms for c in self.calls)

    def total_usage(self) -> UsageDict:
        total = UsageDict()
        for call in self.calls:
            total = UsageDict(
                input_tokens=total.input_tokens + call.usage.input_tokens,
                cache_read_tokens=total.cache_read_tokens + call.usage.cache_read_tokens,
                cache_write_tokens=total.cache_write_tokens + call.usage.cache_write_tokens,
                output_tokens=total.output_tokens + call.usage.output_tokens,
            )
        return total


class ProtocolFn(TypingProtocol):
    def __call__(self, context: ProtocolContext) -> Awaitable[ProtocolResult]: ...


@dataclass(frozen=True)
class ProtocolInfo:
    """Registry entry, including what the protocol costs and who sees what."""

    protocol_id: str
    fn: Callable[[ProtocolContext], Awaitable[ProtocolResult]]
    description: str
    # Expected model calls per episode, as a function of coalition size. Used by the
    # dry-run cost planner, and to assert that free protocols really are free.
    calls_per_episode: Callable[[int, int], int]
    # What each participant can observe. This is the protocol card the report asks for.
    observability: str
    uses_predicted_expert: bool = False
    interactive: bool = False


REGISTRY: dict[str, ProtocolInfo] = {}


def register(
    protocol_id: str,
    *,
    description: str,
    calls_per_episode: Callable[[int, int], int],
    observability: str,
    uses_predicted_expert: bool = False,
    interactive: bool = False,
):
    """Decorator registering a protocol implementation."""

    def decorator(fn):
        if protocol_id in REGISTRY:
            raise ValueError(f"protocol {protocol_id!r} is already registered")
        REGISTRY[protocol_id] = ProtocolInfo(
            protocol_id=protocol_id,
            fn=fn,
            description=description,
            calls_per_episode=calls_per_episode,
            observability=observability,
            uses_predicted_expert=uses_predicted_expert,
            interactive=interactive,
        )
        return fn

    return decorator


def get_protocol(protocol_id: str) -> ProtocolInfo:
    try:
        return REGISTRY[protocol_id]
    except KeyError:
        raise KeyError(
            f"unknown protocol {protocol_id!r}. Registered: {sorted(REGISTRY)}"
        ) from None


def available_protocols() -> list[str]:
    return sorted(REGISTRY)


def protocol_card() -> str:
    """Human-readable table of every protocol's cost profile and observability."""
    lines = ["# Protocol card", ""]
    for protocol_id in available_protocols():
        info = REGISTRY[protocol_id]
        lines.extend(
            [
                f"## {protocol_id}",
                "",
                info.description,
                "",
                f"- interactive: {info.interactive}",
                f"- uses predicted expert: {info.uses_predicted_expert}",
                f"- model calls for a 4-agent coalition, 2 rounds: "
                f"{info.calls_per_episode(4, 2)}",
                f"- observability: {info.observability}",
                "",
            ]
        )
    return "\n".join(lines)


# ---- prompt construction ---------------------------------------------------------------


def system_prompt(agent: Agent, spec: TaskSpec | None = None) -> str:
    """The agent's system message, including any private evidence it holds.

    Private evidence is per (task, agent), so it lives on the task spec and is bound here
    rather than baked into the pool. Passing ``spec`` matters on every member-facing call,
    not just the first: in the distributed-information condition (D-010) an agent that
    loses its briefing during a debate round or a chair reply is being asked to defend a
    position whose basis it can no longer see.

    The neutral judge and chair prompts deliberately do *not* go through here. They hold no
    private evidence, which is the point: a chair can only obtain it by asking.
    """
    parts = [role_instruction(agent.role)]
    if agent.system_prompt:
        parts.append(agent.system_prompt)
    private = agent.hidden_context
    if spec is not None:
        private = spec.hidden_context.get(str(agent.agent_id), private)
    if private:
        parts.append(
            "You hold the following private information. No other team member has it, so "
            "you must state it explicitly if it is relevant:\n" + private
        )
    return "\n\n".join(parts)


def independent_prompt(spec: TaskSpec, agent: Agent) -> list[dict[str, str]]:
    """Stage-A prompt: solve the task alone, with no knowledge of any teammate."""
    return [
        {"role": "system", "content": system_prompt(agent, spec)},
        {"role": "user", "content": f"{spec.prompt}\n\n{answer_format_instruction(spec)}"},
    ]


def format_peer_answers(
    context: ProtocolContext,
    *,
    visible: Sequence[int],
    anonymize: bool = True,
    include_answer_only: bool = False,
    texts: Mapping[int, str] | None = None,
) -> str:
    """Render teammates' answers as the shared context for a protocol.

    ``texts`` overrides what each member is shown as having said. Multi-round debate needs
    this: from round two on, members must see each other's *latest* positions, and reading
    from the bank would silently replay round zero for the rest of the debate.

    ``anonymize`` replaces model identity with a positional label. It is on by default
    because the report warns that named model identity is itself an authority cue: an agent
    told it is reading "GPT-5" may defer for reasons unrelated to the argument. Authority is
    manipulated deliberately by the governance protocols, not leaked by accident here.

    The anonymization is only as good as the message content allows. It replaces the label we
    attach; it cannot scrub a model that self-identifies mid-answer ("As Claude, I..."). That
    residual leak is a limitation of the design, not something a regex should paper over,
    since silently rewriting model output would corrupt the transcript. If it turns out to be
    frequent, the honest fix is to measure and report the rate.
    """
    blocks: list[str] = []
    for position, agent_id in enumerate(visible):
        record = context.bank[agent_id]
        label = f"Member {position + 1}" if anonymize else context.agent(agent_id).name
        if include_answer_only:
            answer = record.extracted_answer or "(no answer stated)"
            blocks.append(f"{label} answered: {answer}")
        else:
            text = record.text if texts is None else texts.get(agent_id, record.text)
            blocks.append(f"--- {label} ---\n{text.strip() or '(no response)'}")
    return "\n\n".join(blocks) if blocks else "(no member responses are available)"


def revision_prompt(
    context: ProtocolContext,
    agent: Agent,
    *,
    peer_block: str,
    round_index: int,
    own_text: str | None = None,
) -> list[dict[str, str]]:
    """Debate-round prompt: revise in light of what teammates said.

    The instruction to change position only for a stated reason is deliberate. Without it,
    the protocol measures social conformity plus reasoning; with it, a position change is at
    least accompanied by a claim we can inspect in the transcript.

    ``own_text`` defaults to the banked answer and is overridden from round two on, so an
    agent is reminded of what it said last round rather than what it said first.
    """
    own = (
        own_text if own_text is not None else context.bank[agent.agent_id].text
    ).strip() or "(no response)"
    return [
        {"role": "system", "content": system_prompt(agent, context.spec)},
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"You previously answered:\n{own}\n\n"
                f"Other members of your team answered:\n\n{peer_block}\n\n"
                f"This is discussion round {round_index}. Consider their reasoning. "
                f"If you find a concrete error in your own answer, correct it and say what "
                f"the error was. If you still believe your answer, say why the objections "
                f"do not hold. Do not change your answer merely because others disagree.\n\n"
                f"{answer_format_instruction(context.spec)}"
            ),
        },
    ]


def judge_prompt(context: ProtocolContext, *, peer_block: str) -> list[dict[str, str]]:
    """Neutral-aggregator prompt: decide between submitted answers without solving."""
    return [
        {"role": "system", "content": role_instruction("aggregator")},
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"Independent team members submitted these responses:\n\n{peer_block}\n\n"
                f"Decide which response is correct. Judge the reasoning, not the confidence "
                f"or the length. If several agree but their shared reasoning is wrong, do not "
                f"follow the majority.\n\n"
                f"{answer_format_instruction(context.spec)}"
            ),
        },
    ]


def verifier_prompt(
    context: ProtocolContext, verifier: Agent, *, candidate_text: str
) -> list[dict[str, str]]:
    """Verifier prompt: find a concrete error in one candidate answer, or say there is none."""
    return [
        {
            "role": "system",
            "content": system_prompt(verifier.with_role("verifier"), context.spec),
        },
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"A team member proposed this answer:\n\n{candidate_text}\n\n"
                f"Check it. If you find a specific error, state exactly where it is and what "
                f"the consequence is. If you find no error, reply with only: NO ERROR FOUND. "
                f"Do not manufacture an objection."
            ),
        },
    ]


def expert_revision_prompt(
    context: ProtocolContext, expert: Agent, *, critique: str
) -> list[dict[str, str]]:
    """Expert's response to a verifier critique: accept it or rebut it."""
    own = context.bank[expert.agent_id].text.strip() or "(no response)"
    return [
        {"role": "system", "content": system_prompt(expert, context.spec)},
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"Your answer was:\n{own}\n\n"
                f"A reviewer said:\n{critique}\n\n"
                f"If the objection identifies a real error, correct your answer. If it does "
                f"not, keep your answer and explain why the objection fails.\n\n"
                f"{answer_format_instruction(context.spec)}"
            ),
        },
    ]


def counterevidence_prompt(
    context: ProtocolContext, challenger: Agent, *, candidate_text: str
) -> list[dict[str, str]]:
    """Challenger prompt under expert veto: overturn the answer or concede.

    Distinct from :func:`verifier_prompt` because the veto rule needs a *checkable* bar. A
    free-form objection cannot be adjudicated without an LLM judge, so the challenger is
    required to name the answer it believes is correct. That turns "did the challenge meet the
    bar" into deterministic extraction rather than a second act of interpretation.
    """
    return [
        {
            "role": "system",
            "content": system_prompt(challenger.with_role("verifier"), context.spec),
        },
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"The team's designated expert proposed this answer:\n\n{candidate_text}\n\n"
                f"The expert's answer stands unless you can overturn it. To overturn it you "
                f"must do both of the following:\n"
                f"  1. Identify the specific error — the step, the misread condition, or the "
                f"false fact — and say why it is wrong.\n"
                f"  2. State the answer you believe is correct instead.\n\n"
                f"If you cannot do both, reply with only: {CONCEDE_SENTINEL}. Conceding is the "
                f"correct response when the answer looks right, and an unsupported challenge is "
                f"worse than none.\n\n"
                f"{answer_format_instruction(context.spec)}"
            ),
        },
    ]


def chair_query_prompt(context: ProtocolContext, *, peer_block: str) -> list[dict[str, str]]:
    """Chair prompt: ask for the one piece of missing evidence, or decline to ask.

    The chair is told to name which members to ask. Who it chooses is a governance
    observable in its own right — a chair that consistently questions the least competent
    member is misallocating attention in the same way a vote misallocates influence.
    """
    return [
        {"role": "system", "content": role_instruction("chair")},
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"Independent team members submitted these responses:\n\n{peer_block}\n\n"
                f"They may disagree because some of them hold information the others do not. "
                f"Before deciding, you may ask for exactly one piece of missing evidence.\n\n"
                f"If a question would resolve the disagreement, reply in this format:\n"
                f"  {QUESTION_PREFIX} <your single question>\n"
                f"  {ASK_PREFIX} <the members to ask, for example: Member 1, Member 3>\n\n"
                f"If no question would help — the answers agree, or the disagreement is a "
                f"reasoning error rather than missing information — reply with only: "
                f"{NO_QUESTION_SENTINEL}"
            ),
        },
    ]


def chair_response_prompt(
    context: ProtocolContext, agent: Agent, *, question: str
) -> list[dict[str, str]]:
    """Member prompt: answer the chair's question about your own reasoning.

    The member keeps its private evidence here, which is the whole mechanism by which an
    information-seeking chair can outperform a vote: the chair asks, and the one member that
    holds the missing fact is able to state it.
    """
    own = context.bank[agent.agent_id].text.strip() or "(no response)"
    return [
        {"role": "system", "content": system_prompt(agent, context.spec)},
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"You previously answered:\n{own}\n\n"
                f"The team's chair asks:\n{question}\n\n"
                f"Answer the question directly. State any fact you relied on that you did not "
                f"write down before, and say plainly if you do not know. Do not restate your "
                f"whole solution."
            ),
        },
    ]


def chair_decision_prompt(
    context: ProtocolContext, *, peer_block: str, evidence_block: str
) -> list[dict[str, str]]:
    """Chair prompt: decide, having seen the original answers and the replies."""
    return [
        {"role": "system", "content": role_instruction("chair")},
        {
            "role": "user",
            "content": (
                f"{context.spec.prompt}\n\n"
                f"Independent team members submitted these responses:\n\n{peer_block}\n\n"
                f"You asked for missing evidence and received:\n\n{evidence_block}\n\n"
                f"Decide the final answer. Weigh the evidence you gathered, not the number of "
                f"members holding a position: a single member with a decisive fact outranks a "
                f"majority without one.\n\n"
                f"{answer_format_instruction(context.spec)}"
            ),
        },
    ]


# ---- helpers shared by implementations -------------------------------------------------


def call_record_from_response(
    response, *, stage: str, agent_id: int | None, model: str
) -> CallRecord:
    return CallRecord(
        stage=stage,
        agent_id=agent_id,
        model=model,
        provider=response.provider,
        model_returned=response.model_returned,
        usage=UsageDict(**response.usage.to_dict()),
        cost_usd=response.cost_usd,
        provider_reported_cost_usd=response.reconciliation.reported_usd,
        cost_agrees=response.reconciliation.agrees,
        latency_ms=response.latency_ms,
        prompt_hash=response.prompt_hash,
        cached=response.cached,
        attempts=response.attempts,
        generation_id=response.generation_id,
        finish_reason=response.finish_reason,
    )


def bank_turns(context: ProtocolContext, visible: Sequence[int]) -> list[TurnRecord]:
    """Transcript turns representing the banked Stage-A answers.

    Recorded on every episode even though they cost nothing here, so a transcript is
    readable on its own without joining back to the answer bank.
    """
    return [
        TurnRecord(
            speaker_id=agent_id,
            role=context.agent(agent_id).role,
            stage="independent",
            content=context.bank[agent_id].text,
        )
        for agent_id in visible
    ]
