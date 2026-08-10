"""Async client for any OpenAI-compatible ``/chat/completions`` endpoint.

One implementation serves both OpenRouter and a local vLLM server, because vLLM speaks
the same wire protocol. A pool member's ``provider`` field selects the base URL, API key
and pricing behaviour; adding local agents is therefore a config change (D-006).

Responsibilities, in the order they fire on each call:

1. content-addressed cache lookup (free, byte-identical)
2. spend guard against the run and daily caps
3. HTTP request with bounded concurrency and retry with exponential backoff
4. usage normalization, local pricing, reconciliation against provider-reported cost
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx

from .base import BudgetExceeded, LLMResponse, SpendLedger
from .cache import ResponseCache, cache_key, prompt_hash
from .pricing import PricingTable, reconcile, step_cost_usd
from .usage import normalize_usage, provider_reported_cost

RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

# Used only to pre-check the spend guard before a call, since the true cost is unknown
# until the response arrives. Deliberately pessimistic.
PROJECTED_INPUT_TOKENS = 4_000
PROJECTED_OUTPUT_TOKENS = 1_000

# Headroom on the pre-call projection. OpenRouter's per-model price is a headline figure and
# the request is routed to one of several upstream providers with their own rates, so the
# amount actually billed is not knowable before the response arrives. The pilot9-a run
# measured Qwen3-30B at 2.69x our computed figure; 3x covers that with a little room. Only
# the guard uses this — recorded costs are the provider's own numbers, never inflated.
PROJECTION_SAFETY_FACTOR = 3.0


@dataclass(frozen=True)
class Endpoint:
    """Where to send requests for a given provider, and whether it charges money."""

    provider: str
    base_url: str
    api_key: str
    priced: bool

    @classmethod
    def for_provider(cls, provider: str) -> "Endpoint":
        provider = provider.lower()
        if provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in, "
                    "or run with --dry-run to plan without issuing requests."
                )
            return cls(
                provider="openrouter",
                base_url=os.environ.get(
                    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
                ).rstrip("/"),
                api_key=key,
                priced=True,
            )
        if provider == "vllm":
            return cls(
                provider="vllm",
                base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8001/v1").rstrip("/"),
                api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
                priced=False,
            )
        raise ValueError(f"unknown provider {provider!r}; expected 'openrouter' or 'vllm'")


class ChatClient:
    """Async OpenAI-compatible chat client with caching, retries and cost accounting."""

    def __init__(
        self,
        *,
        pricing: PricingTable,
        ledger: SpendLedger,
        cache_dir: str | Path,
        use_cache: bool = True,
        max_concurrency: int = 8,
        # Eight rather than five because the observed failure mode is not a transient blip:
        # OpenRouter's shared upstream pools return 429 "engine_overloaded" for stretches
        # longer than a five-attempt window survives. In pilot9-a that cost one agent 4 of its
        # 9 answers, and a missing cell in the answer bank is worse than a slow one — it
        # unbalances the design that every later paired comparison depends on.
        max_attempts: int = 8,
        timeout_s: float = 180.0,
        retry_base_delay_s: float = 1.0,
        dry_run: bool = False,
    ):
        self.pricing = pricing
        self.ledger = ledger
        self.cache = ResponseCache(cache_dir, enabled=use_cache)
        self.max_attempts = max_attempts
        self.timeout_s = timeout_s
        self.retry_base_delay_s = retry_base_delay_s
        self.dry_run = dry_run
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._endpoints: dict[str, Endpoint] = {}
        # Requests that would have been issued in dry-run mode.
        self.planned_calls = 0

    # ---- lifecycle ----------------------------------------------------------------

    async def __aenter__(self) -> "ChatClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    def _endpoint(self, provider: str) -> Endpoint:
        if provider not in self._endpoints:
            self._endpoints[provider] = Endpoint.for_provider(provider)
        return self._endpoints[provider]

    def _http(self, endpoint: Endpoint) -> httpx.AsyncClient:
        if endpoint.provider not in self._clients:
            headers = {
                "Authorization": f"Bearer {endpoint.api_key}",
                "Content-Type": "application/json",
            }
            if endpoint.provider == "openrouter":
                # OpenRouter uses these for attribution; harmless elsewhere.
                headers["HTTP-Referer"] = os.environ.get(
                    "OPENROUTER_REFERER", "https://example.invalid/mas-harness"
                )
                headers["X-Title"] = os.environ.get("OPENROUTER_TITLE", "MAS Organization Study")
            self._clients[endpoint.provider] = httpx.AsyncClient(
                base_url=endpoint.base_url,
                headers=headers,
                timeout=self.timeout_s,
            )
        return self._clients[endpoint.provider]

    # ---- the call -----------------------------------------------------------------

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
        """Issue one chat completion, or return the cached one."""
        messages = [dict(m) for m in messages]
        key = cache_key(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            extra=extra_body,
        )
        p_hash = prompt_hash(messages)

        cached = self.cache.get(key)
        if cached is not None:
            return self._response_from_payload(
                cached, model=model, provider=provider, prompt_hash=p_hash, cached=True
            )

        if self.dry_run:
            self.planned_calls += 1
            return self._dry_run_response(model=model, provider=provider, prompt_hash=p_hash)

        endpoint = self._endpoint(provider)
        if endpoint.priced:
            self.ledger.check(self._projected_cost(model))

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            payload["seed"] = seed
        if endpoint.provider == "openrouter":
            # Ask OpenRouter to return its own cost figure so we can reconcile (D-005).
            payload["usage"] = {"include": True}
        if extra_body:
            payload.update(dict(extra_body))

        data, latency_ms, attempts = await self._post_with_retry(endpoint, payload)

        raw_usage = data.get("usage") or {}
        usage = normalize_usage(endpoint.provider, raw_usage)
        if endpoint.priced:
            computed = step_cost_usd(usage, self.pricing.get(model))
        else:
            computed = 0.0
        recon = reconcile(computed, provider_reported_cost(raw_usage) if endpoint.priced else None)

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{model} returned no choices: {data!r}")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()

        record = {
            "text": text,
            "model_returned": data.get("model"),
            "generation_id": data.get("id"),
            "finish_reason": choices[0].get("finish_reason"),
            "usage": usage.to_dict(),
            "raw_usage": dict(raw_usage),
            "cost_usd": computed,
            "cost_reconciliation": recon.to_dict(),
            "latency_ms": latency_ms,
            "attempts": attempts,
            "provider": endpoint.provider,
        }
        self.cache.put(key, record)
        if endpoint.priced:
            # Charge the budget what the provider says it charged us, not what we computed.
            # OpenRouter's per-model price is a headline figure: the request is routed to one
            # of several upstream providers with their own rates, so our figure can be off in
            # either direction. Measured in the pilot9-a run: Qwen3-30B billed up to 2.69x our
            # estimate, Mistral-Small 0.80x. Recording the estimate would let a run overrun
            # its cap before the ledger noticed. The computed figure is still kept on the
            # record, because the *disagreement* is the diagnostic (D-005).
            self.ledger.record(recon.reported_usd or computed, model=model)

        return self._response_from_payload(
            record, model=model, provider=endpoint.provider, prompt_hash=p_hash, cached=False
        )

    async def _post_with_retry(
        self, endpoint: Endpoint, payload: Mapping[str, Any]
    ) -> tuple[dict[str, Any], float, int]:
        """POST with bounded concurrency, retrying transient failures with backoff."""
        client = self._http(endpoint)
        last_error: BaseException | None = None
        started = time.monotonic()

        for attempt in range(1, self.max_attempts + 1):
            try:
                async with self._semaphore:
                    response = await client.post("/chat/completions", json=dict(payload))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                await self._backoff(attempt)
                continue

            if response.status_code in RETRYABLE_STATUS:
                last_error = RuntimeError(
                    f"HTTP {response.status_code} from {endpoint.provider}: {response.text[:400]}"
                )
                if attempt >= self.max_attempts:
                    break
                await self._backoff(attempt, retry_after=response.headers.get("retry-after"))
                continue

            if response.status_code >= 400:
                # Non-retryable: a bad slug or a rejected request should fail loudly and
                # immediately rather than burning the retry budget.
                raise RuntimeError(
                    f"HTTP {response.status_code} from {endpoint.provider} for "
                    f"model {payload.get('model')!r}: {response.text[:600]}"
                )

            data = response.json()
            if "error" in data and not data.get("choices"):
                last_error = RuntimeError(f"provider error payload: {data['error']!r}")
                if attempt >= self.max_attempts:
                    break
                await self._backoff(attempt)
                continue

            latency_ms = (time.monotonic() - started) * 1000.0
            return data, latency_ms, attempt

        raise RuntimeError(
            f"giving up on {payload.get('model')!r} after {self.max_attempts} attempts: "
            f"{last_error}"
        ) from last_error

    async def _backoff(self, attempt: int, *, retry_after: str | None = None) -> None:
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), 60.0))
                return
            except ValueError:
                pass
        # Full jitter, so many concurrent workers do not retry in lockstep.
        delay = self.retry_base_delay_s * (2 ** (attempt - 1))
        await asyncio.sleep(random.uniform(0.0, min(delay, 30.0)))

    def _projected_cost(self, model: str) -> float:
        """A deliberately pessimistic estimate of what the next call will cost.

        Used only by the pre-call budget guard, where erring high is the safe direction: an
        over-estimate stops a run slightly early, an under-estimate lets it overrun the cap.
        The margin exists because the actual upstream provider is not known until the response
        comes back and can bill several times the headline rate.
        """
        from .usage import UsageBuckets

        try:
            pricing = self.pricing.get(model)
        except KeyError:
            # No price means we cannot bound the call; treat as free for the guard and let
            # the post-hoc reconciliation surface it.
            return 0.0
        return PROJECTION_SAFETY_FACTOR * step_cost_usd(
            UsageBuckets(PROJECTED_INPUT_TOKENS, 0, 0, PROJECTED_OUTPUT_TOKENS), pricing
        )

    def _response_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        model: str,
        provider: str,
        prompt_hash: str,
        cached: bool,
    ) -> LLMResponse:
        from .pricing import CostReconciliation
        from .usage import UsageBuckets

        usage = UsageBuckets(**payload["usage"])
        recon_raw = payload.get("cost_reconciliation") or {}
        recon = CostReconciliation(
            computed_usd=recon_raw.get("computed_usd", payload.get("cost_usd", 0.0)),
            reported_usd=recon_raw.get("reported_usd"),
            agrees=recon_raw.get("agrees", True),
            relative_error=recon_raw.get("relative_error"),
        )
        return LLMResponse(
            text=payload["text"],
            model_requested=model,
            model_returned=payload.get("model_returned"),
            provider=payload.get("provider", provider),
            usage=usage,
            # A cache hit is free at the margin: the money was already spent and recorded
            # by the run that populated the entry.
            cost_usd=0.0 if cached else float(payload.get("cost_usd", 0.0)),
            reconciliation=recon,
            latency_ms=0.0 if cached else float(payload.get("latency_ms", 0.0)),
            prompt_hash=prompt_hash,
            cached=cached,
            generation_id=payload.get("generation_id"),
            finish_reason=payload.get("finish_reason"),
            attempts=int(payload.get("attempts", 1)),
            raw_usage=dict(payload.get("raw_usage") or {}),
        )

    def _dry_run_response(self, *, model: str, provider: str, prompt_hash: str) -> LLMResponse:
        from .pricing import CostReconciliation
        from .usage import UsageBuckets

        return LLMResponse(
            text="",
            model_requested=model,
            model_returned=None,
            provider=provider,
            usage=UsageBuckets.zero(),
            cost_usd=0.0,
            reconciliation=CostReconciliation(0.0, None, True, None),
            latency_ms=0.0,
            prompt_hash=prompt_hash,
            cached=False,
            finish_reason="dry_run",
        )

    def stats(self) -> dict[str, Any]:
        return {
            "cache": self.cache.stats(),
            "spend": self.ledger.summary(),
            "planned_calls_dry_run": self.planned_calls,
        }


__all__ = ["ChatClient", "Endpoint", "BudgetExceeded", "LLMResponse"]
