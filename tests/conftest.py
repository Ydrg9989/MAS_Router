"""Shared fixtures: a synthetic task, a synthetic pool, and a stub LLM client.

Everything here is deterministic and offline. The stub client records every request it
receives, which lets tests assert on call counts and on exactly what each participant was
shown — the observability claims in the protocol card are checked, not just documented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import pytest

from mas_harness.clients.base import LLMResponse
from mas_harness.clients.pricing import CostReconciliation
from mas_harness.clients.usage import UsageBuckets
from mas_harness.pool.agents import Agent, AgentPool
from mas_harness.records.schema import AnswerRecord, CallRecord, UsageDict
from mas_harness.tasks.adapters import TaskSpec, build_evaluator


@pytest.fixture
def choice_task() -> TaskSpec:
    return TaskSpec(
        task_id="mmlu_pro::demo",
        suite="mmlu_pro",
        domain="physics",
        answer_type="choice",
        prompt="What is the answer to the demo question?",
        ground_truth="B",
        payload={"question": "demo", "options": ["w", "x", "y", "z"], "answer": "B"},
    )


@pytest.fixture
def pool() -> AgentPool:
    agents = tuple(
        Agent(
            agent_id=index,
            name=name,
            provider="openrouter",
            model=f"vendor/{name}",
            family=name,
            role=role,
            max_tokens=64,
        )
        for index, (name, role) in enumerate(
            [
                ("alpha", "generalist"),
                ("beta", "generalist"),
                ("gamma", "verifier"),
                ("delta", "generalist"),
            ]
        )
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
    return AgentPool(pool_id="testpool", agents=agents, aggregator=aggregator)


def make_answer(
    task: TaskSpec,
    agent: Agent,
    answer: str,
    *,
    seed: int = 0,
    text: str | None = None,
) -> AnswerRecord:
    """One banked Stage-A answer, scored through the real evaluator.

    The default body deliberately does not name the agent, because anonymization in
    ``format_peer_answers`` replaces the *label* and cannot scrub the message content.
    Tests distinguish agents by their answer letter instead.
    """
    evaluator = build_evaluator(task)
    body = (
        text
        if text is not None
        else f"Working through the problem step by step. The answer is '{answer}'."
    )
    extracted = evaluator.extract(body)
    return AnswerRecord(
        run_id="test",
        task_id=task.task_id,
        suite=task.suite,
        domain=task.domain,
        agent_id=agent.agent_id,
        agent_name=agent.name,
        model=agent.model,
        provider=agent.provider,
        seed=seed,
        text=body,
        extracted_answer=extracted,
        ground_truth=task.ground_truth,
        correct=evaluator.score_extracted(extracted),
        parse_failed=not extracted,
        call=CallRecord(
            stage="independent",
            agent_id=agent.agent_id,
            model=agent.model,
            provider=agent.provider,
            usage=UsageDict(input_tokens=100, output_tokens=50),
            cost_usd=0.001,
        ),
    )


@pytest.fixture
def make_answer_for() -> Callable[..., AnswerRecord]:
    """:func:`make_answer` for an arbitrary task, not just the shared choice fixture."""
    return make_answer


@pytest.fixture
def make_bank(choice_task, pool) -> Callable[[Sequence[str]], dict[int, AnswerRecord]]:
    """Build a bank from one answer letter per agent, in agent order.

    Strict zipping is deliberate: a test that passes three letters for four agents almost
    certainly means to plant a different structure than the one it would silently get.
    """

    def build(answers: Sequence[str], *, seed: int = 0) -> dict[int, AnswerRecord]:
        return {
            agent.agent_id: make_answer(choice_task, agent, answer, seed=seed)
            for agent, answer in zip(pool.agents, answers, strict=True)
        }

    return build


@dataclass
class StubClient:
    """Stands in for :class:`ChatClient`, returning scripted text.

    ``responder`` receives the request and returns the reply body, so a test can make the
    reply depend on what the model was shown. Requests are retained in full so tests can
    assert on observability.
    """

    responder: Callable[[dict[str, Any]], str] = lambda request: "The answer is 'B'."
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        provider: str = "openrouter",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: int | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        request = {
            "model": model,
            "messages": [dict(m) for m in messages],
            "provider": provider,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": seed,
        }
        self.requests.append(request)
        text = self.responder(request)
        return LLMResponse(
            text=text,
            model_requested=model,
            model_returned=model,
            provider=provider,
            usage=UsageBuckets(100, 0, 0, 20),
            cost_usd=0.002,
            reconciliation=CostReconciliation(0.002, 0.002, True, 0.0),
            latency_ms=12.0,
            prompt_hash="stub",
            cached=False,
        )

    @property
    def n_calls(self) -> int:
        return len(self.requests)

    def prompts_containing(self, needle: str) -> list[dict[str, Any]]:
        return [
            request
            for request in self.requests
            if any(needle in str(m.get("content", "")) for m in request["messages"])
        ]

    def user_content(self, index: int = 0) -> str:
        return "\n".join(
            str(m["content"]) for m in self.requests[index]["messages"] if m["role"] == "user"
        )

    def system_content(self, index: int = 0) -> str:
        return "\n".join(
            str(m["content"]) for m in self.requests[index]["messages"] if m["role"] == "system"
        )


@pytest.fixture
def stub_client() -> Callable[..., StubClient]:
    def build(responder: Callable[[dict[str, Any]], str] | None = None) -> StubClient:
        return StubClient(responder=responder or (lambda request: "The answer is 'B'."))

    return build
