"""Normalize provider ``usage`` payloads into four canonical token buckets.

Adapted from TwinRouterBench ``swerouter/usage.py`` (pinned commit 430acec, see
UPSTREAM.md). Vendored rather than imported to avoid depending on ``tiktoken`` and
``tokenizers``; see DECISIONS.md D-002.

Providers report prompt-cache usage in mutually incompatible ways, and the difference
matters because cache reads and cache writes are priced differently from fresh input
tokens. Collapsing everything into ``prompt_tokens`` mis-bills Anthropic ephemeral cache
writes in particular, which is what motivated the upstream module.

The invariant maintained here is:

    input_tokens + cache_read_tokens + cache_write_tokens == prompt tokens billed
    output_tokens                                         == completion tokens billed

Missing keys, wrong types and negative counts raise rather than defaulting to zero: a
silently zero-cost run is worse than a crashed one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# ``vllm`` is an OpenAI-compatible local server; it reports OpenAI-shaped usage but
# carries no price, so it is normalized identically and priced at zero (D-006).
SUPPORTED_PROVIDERS: frozenset[str] = frozenset(
    {"openrouter", "openai", "anthropic", "gemini", "deepseek", "vllm", "openai_compat"}
)

_OPENAI_SHAPED = frozenset({"openrouter", "openai", "vllm", "openai_compat"})


@dataclass(frozen=True)
class UsageBuckets:
    """Canonical four-bucket token usage for a single LLM call."""

    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "output_tokens",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"UsageBuckets.{name} must be int, got {type(value).__name__}")
            if value < 0:
                raise ValueError(f"UsageBuckets.{name} must be non-negative, got {value}")

    @property
    def total_prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "output_tokens": self.output_tokens,
        }

    def __add__(self, other: "UsageBuckets") -> "UsageBuckets":
        return UsageBuckets(
            input_tokens=self.input_tokens + other.input_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )

    @classmethod
    def zero(cls) -> "UsageBuckets":
        return cls(0, 0, 0, 0)


def _count(value: Any, *, field: str, provider: str) -> int:
    """Coerce a JSON numeric token count to int. OpenRouter sometimes emits ``1.0``."""
    if value is None:
        return 0
    if isinstance(value, bool):
        raise TypeError(f"usage.{field} from {provider!r} must be numeric, got bool")
    if isinstance(value, int):
        n = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(
                f"usage.{field} from {provider!r} must be whole tokens, got {value!r}"
            )
        n = int(value)
    else:
        raise TypeError(
            f"usage.{field} from {provider!r} must be numeric, got {type(value).__name__}"
        )
    if n < 0:
        raise ValueError(f"usage.{field} from {provider!r} is negative: {n}")
    return n


def _required(raw: Mapping[str, Any], key: str, *, provider: str) -> int:
    if key not in raw:
        raise ValueError(f"usage payload from {provider!r} is missing required key {key!r}")
    return _count(raw[key], field=key, provider=provider)


def _optional(raw: Mapping[str, Any], key: str, *, provider: str) -> int:
    if key not in raw or raw[key] is None:
        return 0
    return _count(raw[key], field=key, provider=provider)


def _normalize_openai_shaped(raw: Mapping[str, Any], provider: str) -> UsageBuckets:
    """OpenAI envelope plus the OpenRouter cache extensions.

    OpenRouter forwards ``prompt_tokens_details.cached_tokens`` (a cache read) and
    ``prompt_tokens_details.cache_write_tokens`` (e.g. an Anthropic ephemeral write).
    Both are already included in ``prompt_tokens``, so they are subtracted out rather
    than added on.

    Some OpenAI-compatible servers report Anthropic-style ``input_tokens`` /
    ``output_tokens`` while leaving the canonical keys at zero. When both canonical
    counts are zero and the aliases are not, the aliases are used, so that a
    misreporting server produces a real cost rather than a silent zero.
    """
    prompt = _optional(raw, "prompt_tokens", provider=provider)
    completion = _optional(raw, "completion_tokens", provider=provider)
    if prompt == 0 and completion == 0:
        alias_in = _optional(raw, "input_tokens", provider=provider)
        alias_out = _optional(raw, "output_tokens", provider=provider)
        if alias_in or alias_out:
            prompt, completion = alias_in, alias_out
        else:
            prompt = _required(raw, "prompt_tokens", provider=provider)
            completion = _required(raw, "completion_tokens", provider=provider)

    cache_read = 0
    cache_write = 0
    details = raw.get("prompt_tokens_details")
    if isinstance(details, Mapping):
        cache_read = _optional(details, "cached_tokens", provider=provider)
        cache_write = _optional(details, "cache_write_tokens", provider=provider)
    elif details is not None:
        raise TypeError(
            f"usage.prompt_tokens_details from {provider!r} must be an object, "
            f"got {type(details).__name__}"
        )

    billed_prefix = cache_read + cache_write
    if billed_prefix > prompt:
        raise ValueError(
            f"cached({cache_read}) + cache_write({cache_write}) exceeds "
            f"prompt_tokens({prompt}) for {provider!r}"
        )
    return UsageBuckets(
        input_tokens=prompt - billed_prefix,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        output_tokens=completion,
    )


def _normalize_anthropic(raw: Mapping[str, Any]) -> UsageBuckets:
    return UsageBuckets(
        input_tokens=_required(raw, "input_tokens", provider="anthropic"),
        cache_read_tokens=_optional(raw, "cache_read_input_tokens", provider="anthropic"),
        cache_write_tokens=_optional(raw, "cache_creation_input_tokens", provider="anthropic"),
        output_tokens=_required(raw, "output_tokens", provider="anthropic"),
    )


def _normalize_gemini(raw: Mapping[str, Any]) -> UsageBuckets:
    prompt = _required(raw, "prompt_token_count", provider="gemini")
    cached = _optional(raw, "cached_content_token_count", provider="gemini")
    if cached > prompt:
        raise ValueError(
            f"gemini cached_content_token_count({cached}) exceeds prompt_token_count({prompt})"
        )
    if "candidates_token_count" in raw:
        output = _required(raw, "candidates_token_count", provider="gemini")
    else:
        output = _required(raw, "output_token_count", provider="gemini")
    return UsageBuckets(
        input_tokens=prompt - cached,
        cache_read_tokens=cached,
        cache_write_tokens=0,
        output_tokens=output,
    )


def _normalize_deepseek(raw: Mapping[str, Any]) -> UsageBuckets:
    hit = _optional(raw, "prompt_cache_hit_tokens", provider="deepseek")
    if "prompt_cache_miss_tokens" in raw:
        miss = _required(raw, "prompt_cache_miss_tokens", provider="deepseek")
    else:
        total = _required(raw, "prompt_tokens", provider="deepseek")
        if hit > total:
            raise ValueError(
                f"deepseek prompt_cache_hit_tokens({hit}) exceeds prompt_tokens({total})"
            )
        miss = total - hit
    return UsageBuckets(
        input_tokens=miss,
        cache_read_tokens=hit,
        cache_write_tokens=0,
        output_tokens=_required(raw, "completion_tokens", provider="deepseek"),
    )


def normalize_usage(provider: str, raw_usage: Mapping[str, Any] | None) -> UsageBuckets:
    """Map a provider-specific ``usage`` object onto :class:`UsageBuckets`."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"unsupported provider {provider!r}; supported: {sorted(SUPPORTED_PROVIDERS)}"
        )
    if raw_usage is None:
        raise ValueError(f"provider {provider!r} returned no usage payload")
    if not isinstance(raw_usage, Mapping):
        raise TypeError(f"raw_usage must be a mapping, got {type(raw_usage).__name__}")

    if provider == "anthropic":
        return _normalize_anthropic(raw_usage)
    if provider == "gemini":
        return _normalize_gemini(raw_usage)
    if provider == "deepseek":
        return _normalize_deepseek(raw_usage)
    if provider in _OPENAI_SHAPED:
        return _normalize_openai_shaped(raw_usage, provider)
    raise AssertionError(f"unreachable provider branch: {provider!r}")


def provider_reported_cost(raw_usage: Mapping[str, Any] | None) -> float | None:
    """Extract the provider's own USD cost when it supplies one.

    OpenRouter returns ``usage.cost`` when the request opts into usage accounting. We
    keep it alongside our locally computed figure and reconcile the two (D-005).
    """
    if not isinstance(raw_usage, Mapping):
        return None
    for key in ("cost", "total_cost"):
        value = raw_usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None
