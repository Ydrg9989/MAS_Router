"""Find out why the aggregator burns 16,384 tokens and returns nothing.

Rebuilds the exact `independent_judge` prompt for a task that failed, then issues the raw request
several ways and dumps the whole response message. The point is to distinguish three explanations
that the stored records cannot tell apart:

  1. the answer exists in a `reasoning` field we discard at `openrouter.py:222`;
  2. `reasoning: {max_tokens: N}` is silently ignored for this model, so the clamp never applied;
  3. the model genuinely cannot finish, and the episode is missing data rather than a harness bug.

Bypasses `ChatClient` deliberately: that class strips everything except `content`, which is the very
thing under investigation.
"""

from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from mas_harness import config
from mas_harness.pool.agents import AgentPool
from mas_harness.protocols.base import ProtocolContext, format_peer_answers, judge_prompt
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.adapters import build_evaluator
from mas_harness.tasks.manifest import Manifest

VARIANTS = {
    "as_configured": {},
    "reasoning_capped_1024": {"reasoning": {"max_tokens": 1024}},
    "reasoning_effort_low": {"reasoning": {"effort": "low"}},
    "reasoning_excluded": {"reasoning": {"exclude": True}},
}


async def probe(url, headers, payload, label):
    async with httpx.AsyncClient(timeout=600) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning") or "").strip()
    print(f"\n=== {label} ===")
    print(f"  finish_reason : {choice.get('finish_reason')}")
    print(f"  output tokens : {usage.get('completion_tokens')}")
    print(f"  message keys  : {sorted(message)}")
    print(f"  content       : {len(content)} chars")
    print(f"  reasoning     : {len(reasoning)} chars")
    if content:
        print(f"  content tail  : ...{content[-200:]}")
    if reasoning:
        print(f"  reasoning tail: ...{reasoning[-300:]}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="strong4-a")
    ap.add_argument("--pool", default="configs/pools/strong4.yaml")
    ap.add_argument("--task-id", default="gpqa_diamond::102")
    args = ap.parse_args()

    manifest = Manifest.read("data/manifests/hard366.json")
    spec = manifest.by_id()[args.task_id]
    pool = AgentPool.from_yaml(args.pool)
    bank = {
        r.agent_id: r
        for r in RunDirectory(config.RUNS_DIR, args.run_id).load_answers()
        if r.task_id == args.task_id
    }

    context = ProtocolContext(
        spec=spec,
        evaluator=build_evaluator(spec),
        pool=pool,
        coalition=sorted(bank),
        seed=0,
        bank=bank,
        client=None,
    )
    messages = judge_prompt(
        context, peer_block=format_peer_answers(context, visible=context.speaking_order(),
                                                anonymize=True)
    )
    aggregator = pool.aggregator
    print(f"task {args.task_id}  aggregator {aggregator.model}")
    print(f"prompt: {sum(len(m['content']) for m in messages)} chars")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
    }
    for label, extra in VARIANTS.items():
        payload = {
            "model": aggregator.model,
            "messages": [dict(m) for m in messages],
            "temperature": aggregator.temperature,
            "max_tokens": aggregator.max_tokens,
            "usage": {"include": True},
            **extra,
        }
        try:
            await probe(url, headers, payload, label)
        except Exception as exc:  # noqa: BLE001 - a probe should report, not abort
            print(f"\n=== {label} ===\n  FAILED: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
