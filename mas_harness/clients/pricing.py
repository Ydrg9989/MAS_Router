"""Per-model prices, USD cost from token buckets, and provider-cost reconciliation.

The cost function is adapted from TwinRouterBench ``swerouter/pricing.py`` (pinned
commit 430acec). The price *snapshot* machinery is ours: the research report is explicit
that OpenRouter prices must be queried programmatically immediately before launching an
experiment, because model and provider prices change.

Every run therefore writes a ``pricing_snapshot.json`` next to its records, and cost is
always computed against that frozen snapshot rather than against whatever the live
endpoint happens to say later. See DECISIONS.md D-005.

Run as a CLI to refresh or inspect a snapshot:

    python -m mas_harness.clients.pricing snapshot --out data/runs/prices.json
    python -m mas_harness.clients.pricing show --snapshot data/runs/prices.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .usage import UsageBuckets

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Relative disagreement between our computed cost and the provider's own figure that we
# are willing to tolerate before flagging. Providers round, and cache accounting differs
# at the margin, so an exact match is not expected.
COST_RECONCILE_RTOL = 0.02
COST_RECONCILE_ATOL_USD = 1e-6


class PricingUnavailable(RuntimeError):
    """No price snapshot on disk and no route to the provider's price list."""


@dataclass(frozen=True)
class ModelPricing:
    """USD per one million tokens, per bucket."""

    model_id: str
    input_per_m: float
    output_per_m: float
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0

    def __post_init__(self) -> None:
        for name in ("input_per_m", "output_per_m", "cache_read_per_m", "cache_write_per_m"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"ModelPricing.{name} must be numeric for {self.model_id!r}")
            if value < 0:
                raise ValueError(f"ModelPricing.{name} must be non-negative for {self.model_id!r}")

    @classmethod
    def free(cls, model_id: str) -> "ModelPricing":
        """A locally served model: real GPU cost, but no monetary cost (D-006)."""
        return cls(model_id=model_id, input_per_m=0.0, output_per_m=0.0)


class PricingTable:
    """A frozen set of per-model prices, plus the metadata to reproduce it."""

    def __init__(self, prices: Mapping[str, ModelPricing], *, captured_at: str, source: str):
        self._prices = dict(prices)
        self.captured_at = captured_at
        self.source = source

    def __contains__(self, model_id: object) -> bool:
        return model_id in self._prices

    def __len__(self) -> int:
        return len(self._prices)

    @property
    def model_ids(self) -> list[str]:
        return sorted(self._prices)

    def get(self, model_id: str) -> ModelPricing:
        try:
            return self._prices[model_id]
        except KeyError:
            raise KeyError(
                f"no price for model {model_id!r} in snapshot captured {self.captured_at}. "
                f"Known models: {self.model_ids}. Refresh with "
                f"`python -m mas_harness.clients.pricing snapshot`."
            ) from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "source": self.source,
            "prices": {mid: asdict(p) for mid, p in sorted(self._prices.items())},
        }

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
        return path

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PricingTable":
        prices = {
            mid: ModelPricing(**entry) for mid, entry in payload.get("prices", {}).items()
        }
        return cls(
            prices,
            captured_at=payload.get("captured_at", "unknown"),
            source=payload.get("source", "unknown"),
        )

    @classmethod
    def read(cls, path: str | Path) -> "PricingTable":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def with_free_models(self, model_ids: list[str]) -> "PricingTable":
        """Return a copy with locally served models added at zero price."""
        merged = dict(self._prices)
        for mid in model_ids:
            merged.setdefault(mid, ModelPricing.free(mid))
        return PricingTable(merged, captured_at=self.captured_at, source=self.source)


def step_cost_usd(usage: UsageBuckets, pricing: ModelPricing) -> float:
    """USD cost of one call from its four token buckets and the model's prices."""
    return (
        usage.input_tokens * pricing.input_per_m
        + usage.cache_read_tokens * pricing.cache_read_per_m
        + usage.cache_write_tokens * pricing.cache_write_per_m
        + usage.output_tokens * pricing.output_per_m
    ) / 1_000_000.0


@dataclass(frozen=True)
class CostReconciliation:
    """Comparison of our computed cost against the provider's reported cost."""

    computed_usd: float
    reported_usd: float | None
    agrees: bool
    relative_error: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reconcile(computed_usd: float, reported_usd: float | None) -> CostReconciliation:
    """Flag disagreement between local and provider-reported cost (D-005).

    A missing provider figure is not a disagreement; some providers, and every local
    vLLM server, do not report one.
    """
    if reported_usd is None:
        return CostReconciliation(computed_usd, None, True, None)
    denominator = max(abs(reported_usd), COST_RECONCILE_ATOL_USD)
    relative_error = abs(computed_usd - reported_usd) / denominator
    agrees = (
        abs(computed_usd - reported_usd) <= COST_RECONCILE_ATOL_USD
        or relative_error <= COST_RECONCILE_RTOL
    )
    return CostReconciliation(computed_usd, reported_usd, agrees, relative_error)


def _parse_openrouter_model(entry: Mapping[str, Any]) -> ModelPricing | None:
    """Convert one ``/api/v1/models`` entry into per-million-token prices.

    OpenRouter quotes prices per *single* token as decimal strings, so they are scaled by
    1e6 here. Entries whose prices are absent or unparseable are skipped rather than
    guessed at.
    """
    model_id = entry.get("id")
    pricing = entry.get("pricing")
    if not isinstance(model_id, str) or not isinstance(pricing, Mapping):
        return None

    def per_million(key: str) -> float | None:
        raw = pricing.get(key)
        if raw is None or raw == "":
            return None
        try:
            return float(raw) * 1_000_000.0
        except (TypeError, ValueError):
            return None

    prompt = per_million("prompt")
    completion = per_million("completion")
    if prompt is None or completion is None:
        return None
    # Negative sentinels (-1) mean "variable / not applicable" upstream.
    if prompt < 0 or completion < 0:
        return None
    return ModelPricing(
        model_id=model_id,
        input_per_m=prompt,
        output_per_m=completion,
        cache_read_per_m=max(per_million("input_cache_read") or 0.0, 0.0),
        cache_write_per_m=max(per_million("input_cache_write") or 0.0, 0.0),
    )


def fetch_openrouter_prices(*, api_key: str | None = None, timeout: float = 30.0) -> PricingTable:
    """Query the live OpenRouter model list and build a snapshot.

    The endpoint is public, but an API key is sent when available because some
    deployments rate-limit anonymous callers more aggressively.
    """
    import httpx

    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(OPENROUTER_MODELS_URL, headers=headers, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # The bare httpx traceback is a poor first experience, and the actionable fact — that
        # even a dry run needs prices, and how to supply them offline — is not in it.
        raise PricingUnavailable(
            f"could not reach {OPENROUTER_MODELS_URL}: {type(exc).__name__}: {exc}\n"
            f"Prices are required even for --dry-run, because an unpriced plan cannot be "
            f"checked against the budget. If this machine has no route to OpenRouter, take a "
            f"snapshot somewhere that does and copy it in:\n"
            f"    python -m mas_harness.clients.pricing snapshot --out data/runs/<run-id>/"
            f"pricing_snapshot.json"
        ) from exc
    payload = response.json()

    entries = payload.get("data")
    if not isinstance(entries, list):
        raise ValueError(f"unexpected {OPENROUTER_MODELS_URL} payload: missing 'data' list")

    prices: dict[str, ModelPricing] = {}
    for entry in entries:
        parsed = _parse_openrouter_model(entry) if isinstance(entry, Mapping) else None
        if parsed is not None:
            prices[parsed.model_id] = parsed
    if not prices:
        raise ValueError("OpenRouter returned no usable prices")

    return PricingTable(
        prices,
        captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source=OPENROUTER_MODELS_URL,
    )


def load_or_fetch(
    snapshot_path: str | Path,
    *,
    refresh: bool = False,
    api_key: str | None = None,
) -> PricingTable:
    """Read a price snapshot, fetching and writing one if absent or if refresh is asked."""
    snapshot_path = Path(snapshot_path)
    if snapshot_path.exists() and not refresh:
        return PricingTable.read(snapshot_path)
    table = fetch_openrouter_prices(api_key=api_key)
    table.write(snapshot_path)
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenRouter price snapshots")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="fetch live prices and write a snapshot")
    snap.add_argument("--out", default="data/runs/pricing_snapshot.json")
    snap.add_argument("--models", nargs="*", default=None, help="only report these slugs")

    show = sub.add_parser("show", help="print prices from an existing snapshot")
    show.add_argument("--snapshot", default="data/runs/pricing_snapshot.json")
    show.add_argument("--models", nargs="*", default=None)

    args = parser.parse_args(argv)

    if args.command == "snapshot":
        table = fetch_openrouter_prices()
        path = table.write(args.out)
        print(f"wrote {len(table)} model prices to {path} (captured {table.captured_at})")
    else:
        table = PricingTable.read(args.snapshot)
        print(f"snapshot captured {table.captured_at} from {table.source}: {len(table)} models")

    wanted = args.models
    if wanted:
        missing = [m for m in wanted if m not in table]
        for model_id in wanted:
            if model_id in table:
                p = table.get(model_id)
                print(
                    f"  {model_id}: in ${p.input_per_m:.4f}/M  out ${p.output_per_m:.4f}/M  "
                    f"cache_read ${p.cache_read_per_m:.4f}/M  "
                    f"cache_write ${p.cache_write_per_m:.4f}/M"
                )
        if missing:
            print(f"MISSING from snapshot: {missing}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
