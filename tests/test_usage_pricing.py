"""Cost accounting: bucket normalization, pricing arithmetic, reconciliation, spend caps.

The invariant under test throughout is that billed prompt tokens are partitioned, never
double counted: ``input + cache_read + cache_write == prompt_tokens``. Getting this wrong
understates or overstates spend silently, which is the failure mode the vendored
TwinRouterBench module exists to prevent.
"""

from __future__ import annotations

import json

import pytest

from mas_harness.clients.base import BudgetExceeded, SpendLedger
from mas_harness.clients.cache import ResponseCache, cache_key, prompt_hash
from mas_harness.clients.pricing import ModelPricing, PricingTable, reconcile, step_cost_usd
from mas_harness.clients.usage import (
    UsageBuckets,
    normalize_usage,
    provider_reported_cost,
)

# ---- normalization --------------------------------------------------------------------


def test_openai_shape_without_cache():
    usage = normalize_usage("openai", {"prompt_tokens": 100, "completion_tokens": 40})
    assert usage == UsageBuckets(100, 0, 0, 40)
    assert usage.total_prompt_tokens == 100
    assert usage.total_tokens == 140


def test_openrouter_cache_read_is_subtracted_from_prompt_tokens():
    usage = normalize_usage(
        "openrouter",
        {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 800},
        },
    )
    assert usage == UsageBuckets(200, 800, 0, 50)
    assert usage.total_prompt_tokens == 1000


def test_openrouter_cache_write_is_also_subtracted():
    usage = normalize_usage(
        "openrouter",
        {
            "prompt_tokens": 1000,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 600, "cache_write_tokens": 300},
        },
    )
    assert usage == UsageBuckets(100, 600, 300, 10)
    assert usage.total_prompt_tokens == 1000


def test_anthropic_cache_tokens_are_additive_not_subtractive():
    """Anthropic reports input_tokens EXCLUDING cache, unlike OpenAI-shaped providers."""
    usage = normalize_usage(
        "anthropic",
        {
            "input_tokens": 100,
            "cache_read_input_tokens": 700,
            "cache_creation_input_tokens": 200,
            "output_tokens": 30,
        },
    )
    assert usage == UsageBuckets(100, 700, 200, 30)
    assert usage.total_prompt_tokens == 1000


def test_gemini_and_deepseek_shapes():
    gemini = normalize_usage(
        "gemini",
        {
            "prompt_token_count": 500,
            "cached_content_token_count": 200,
            "candidates_token_count": 60,
        },
    )
    assert gemini == UsageBuckets(300, 200, 0, 60)

    deepseek = normalize_usage(
        "deepseek",
        {
            "prompt_tokens": 900,
            "prompt_cache_hit_tokens": 400,
            "prompt_cache_miss_tokens": 500,
            "completion_tokens": 20,
        },
    )
    assert deepseek == UsageBuckets(500, 400, 0, 20)
    assert deepseek.total_prompt_tokens == 900


def test_float_token_counts_are_accepted_but_fractional_ones_are_not():
    assert normalize_usage("openrouter", {"prompt_tokens": 10.0, "completion_tokens": 2.0})
    with pytest.raises(ValueError, match="whole tokens"):
        normalize_usage("openrouter", {"prompt_tokens": 10.5, "completion_tokens": 2})


def test_anthropic_style_aliases_on_an_openai_compatible_server():
    """A local server reporting Anthropic key names must not be priced at zero."""
    usage = normalize_usage("vllm", {"input_tokens": 80, "output_tokens": 20})
    assert usage == UsageBuckets(80, 0, 0, 20)


def test_missing_usage_raises_rather_than_defaulting_to_free():
    with pytest.raises(ValueError, match="no usage payload"):
        normalize_usage("openrouter", None)
    with pytest.raises(ValueError, match="missing required key"):
        normalize_usage("openrouter", {"some_other_field": 1})


def test_cache_exceeding_prompt_tokens_is_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        normalize_usage(
            "openrouter",
            {
                "prompt_tokens": 100,
                "completion_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 150},
            },
        )


def test_negative_counts_are_rejected():
    with pytest.raises(ValueError, match="negative"):
        normalize_usage("openai", {"prompt_tokens": -1, "completion_tokens": 5})
    with pytest.raises(ValueError):
        UsageBuckets(-1, 0, 0, 0)


def test_unsupported_provider_is_rejected():
    with pytest.raises(ValueError, match="unsupported provider"):
        normalize_usage("some-new-provider", {"prompt_tokens": 1, "completion_tokens": 1})


def test_buckets_add_componentwise():
    total = UsageBuckets(1, 2, 3, 4) + UsageBuckets(10, 20, 30, 40)
    assert total == UsageBuckets(11, 22, 33, 44)
    assert UsageBuckets.zero().total_tokens == 0


def test_provider_reported_cost_extraction():
    assert provider_reported_cost({"cost": 0.0123}) == pytest.approx(0.0123)
    assert provider_reported_cost({"total_cost": 1}) == pytest.approx(1.0)
    assert provider_reported_cost({"cost": True}) is None  # bool is not a cost
    assert provider_reported_cost(None) is None


# ---- pricing --------------------------------------------------------------------------


def test_step_cost_prices_each_bucket_separately():
    pricing = ModelPricing(
        model_id="m",
        input_per_m=1.0,
        output_per_m=10.0,
        cache_read_per_m=0.1,
        cache_write_per_m=2.0,
    )
    usage = UsageBuckets(1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert step_cost_usd(usage, pricing) == pytest.approx(1.0 + 0.1 + 2.0 + 10.0)


def test_cache_read_is_cheaper_than_fresh_input_at_equal_prompt_size():
    pricing = ModelPricing("m", input_per_m=3.0, output_per_m=15.0, cache_read_per_m=0.3)
    fresh = step_cost_usd(UsageBuckets(10_000, 0, 0, 500), pricing)
    cached = step_cost_usd(UsageBuckets(1_000, 9_000, 0, 500), pricing)
    assert cached < fresh


def test_free_model_costs_nothing():
    assert step_cost_usd(UsageBuckets(10**6, 0, 0, 10**6), ModelPricing.free("local")) == 0.0


def test_reconcile_flags_disagreement_but_tolerates_rounding():
    assert reconcile(1.0, 1.005).agrees
    assert not reconcile(1.0, 2.0).agrees
    # A missing provider figure is not a disagreement.
    missing = reconcile(1.0, None)
    assert missing.agrees and missing.relative_error is None


def test_pricing_table_round_trips_and_reports_unknown_models(tmp_path):
    table = PricingTable(
        {"a/b": ModelPricing("a/b", 1.0, 2.0)}, captured_at="2026-01-01", source="test"
    )
    path = table.write(tmp_path / "prices.json")
    reloaded = PricingTable.read(path)
    assert reloaded.get("a/b").output_per_m == 2.0
    assert reloaded.captured_at == "2026-01-01"
    with pytest.raises(KeyError, match="no price for model"):
        reloaded.get("missing/model")


def test_local_models_can_be_added_at_zero_price():
    table = PricingTable({}, captured_at="t", source="s").with_free_models(["local/qwen"])
    assert table.get("local/qwen").input_per_m == 0.0


# ---- cache ----------------------------------------------------------------------------


def test_cache_key_covers_every_response_determining_field():
    base = dict(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.0,
        max_tokens=10,
        seed=1,
    )
    reference = cache_key(**base)
    assert cache_key(**base) == reference  # deterministic
    assert cache_key(**{**base, "model": "other"}) != reference
    assert cache_key(**{**base, "temperature": 0.7}) != reference
    assert cache_key(**{**base, "max_tokens": 11}) != reference
    assert cache_key(**{**base, "seed": 2}) != reference
    assert cache_key(**{**base, "messages": [{"role": "user", "content": "ho"}]}) != reference
    assert cache_key(**{**base, "extra": {"top_p": 0.9}}) != reference


def test_cache_key_ignores_extraneous_message_fields():
    """Only role and content reach the model, so only they may affect the key."""
    a = cache_key(
        model="m",
        messages=[{"role": "user", "content": "hi", "name": "alice"}],
        temperature=0.0,
        max_tokens=10,
        seed=None,
    )
    b = cache_key(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.0,
        max_tokens=10,
        seed=None,
    )
    assert a == b


def test_prompt_hash_is_stable_and_distinguishes_prompts():
    one = [{"role": "user", "content": "a"}]
    two = [{"role": "user", "content": "b"}]
    assert prompt_hash(one) == prompt_hash(one)
    assert prompt_hash(one) != prompt_hash(two)


def test_cache_round_trip_and_stats(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    assert cache.get("abc123") is None
    cache.put("abc123", {"text": "hello"})
    assert cache.get("abc123") == {"text": "hello"}
    assert cache.stats() == {"hits": 1, "misses": 1}


def test_corrupt_cache_entry_is_a_miss_not_a_crash(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    key = "ff" * 32
    path = cache.path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert cache.get(key) is None


def test_disabled_cache_never_reads_or_writes(tmp_path):
    cache = ResponseCache(tmp_path / "cache", enabled=False)
    cache.put("k", {"text": "x"})
    assert cache.get("k") is None
    assert not (tmp_path / "cache").exists()


# ---- spend guards ---------------------------------------------------------------------


def test_run_budget_blocks_before_the_call(tmp_path):
    ledger = SpendLedger(
        tmp_path / "ledger.jsonl", run_id="r", run_budget_usd=1.0, daily_budget_usd=100.0
    )
    ledger.record(0.9, model="m")
    ledger.check(0.05)  # still inside the cap
    with pytest.raises(BudgetExceeded, match="run 'r' would exceed"):
        ledger.check(0.2)


def test_daily_budget_accumulates_across_runs(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = SpendLedger(path, run_id="r1", run_budget_usd=100.0, daily_budget_usd=1.0)
    first.record(0.8, model="m")

    second = SpendLedger(path, run_id="r2", run_budget_usd=100.0, daily_budget_usd=1.0)
    assert second.day_spend_usd == pytest.approx(0.8)
    with pytest.raises(BudgetExceeded, match="daily budget"):
        second.check(0.5)


def test_exhausted_daily_budget_refuses_to_start_a_run(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = SpendLedger(path, run_id="r1", run_budget_usd=100.0, daily_budget_usd=1.0)
    first.record(1.5, model="m")
    with pytest.raises(BudgetExceeded, match="already exhausted"):
        SpendLedger(path, run_id="r2", run_budget_usd=100.0, daily_budget_usd=1.0)


def test_ledger_is_append_only_jsonl(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = SpendLedger(path, run_id="r", run_budget_usd=10.0, daily_budget_usd=10.0)
    ledger.record(0.1, model="a")
    ledger.record(0.2, model="b")
    entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert [e["model"] for e in entries] == ["a", "b"]
    assert ledger.run_spend_usd == pytest.approx(0.3)


def test_zero_cost_calls_are_not_recorded(tmp_path):
    """Cache hits and local models must not create ledger noise."""
    path = tmp_path / "ledger.jsonl"
    ledger = SpendLedger(path, run_id="r", run_budget_usd=10.0, daily_budget_usd=10.0)
    ledger.record(0.0, model="local")
    assert not path.exists() or path.read_text() == ""
