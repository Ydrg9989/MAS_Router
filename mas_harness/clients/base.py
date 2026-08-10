"""Shared client types: the response envelope and the spend guards."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .pricing import CostReconciliation
from .usage import UsageBuckets


class BudgetExceeded(RuntimeError):
    """Raised before a request is issued when it would breach a spend cap."""


@dataclass
class LLMResponse:
    """One completed model call, with everything needed to audit and price it."""

    text: str
    model_requested: str
    model_returned: str | None
    provider: str
    usage: UsageBuckets
    cost_usd: float
    reconciliation: CostReconciliation
    latency_ms: float
    prompt_hash: str
    cached: bool
    generation_id: str | None = None
    finish_reason: str | None = None
    attempts: int = 1
    raw_usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model_requested": self.model_requested,
            "model_returned": self.model_returned,
            "provider": self.provider,
            "usage": self.usage.to_dict(),
            "cost_usd": self.cost_usd,
            "cost_reconciliation": self.reconciliation.to_dict(),
            "latency_ms": self.latency_ms,
            "prompt_hash": self.prompt_hash,
            "cached": self.cached,
            "generation_id": self.generation_id,
            "finish_reason": self.finish_reason,
            "attempts": self.attempts,
        }


class SpendLedger:
    """Cross-run daily spend tracking, plus a per-run cap.

    Two independent guards, because they fail differently. The run cap stops a single
    runaway experiment; the daily cap stops a series of individually reasonable
    experiments from quietly consuming the whole budget. Both are checked *before*
    issuing a request, using a conservative estimate of what the request will cost.

    The ledger file is append-only JSONL so that concurrent runners do not clobber each
    other; the daily total is recomputed by reading it back.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        run_id: str,
        run_budget_usd: float,
        daily_budget_usd: float,
    ):
        self.path = Path(path)
        self.run_id = run_id
        self.run_budget_usd = float(run_budget_usd)
        self.daily_budget_usd = float(daily_budget_usd)
        self.run_spend_usd = 0.0
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._day = date.today().isoformat()
        self._day_spend_at_start = self._read_day_total(self._day)
        if self._day_spend_at_start >= self.daily_budget_usd:
            raise BudgetExceeded(
                f"daily budget already exhausted: ${self._day_spend_at_start:.4f} spent on "
                f"{self._day}, cap is ${self.daily_budget_usd:.2f}. Raise "
                f"MAS_DAILY_BUDGET_USD or wait until tomorrow."
            )

    def _read_day_total(self, day: str) -> float:
        if not self.path.exists():
            return 0.0
        total = 0.0
        with self.path.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("day") == day:
                    total += float(entry.get("cost_usd", 0.0))
        return total

    @property
    def day_spend_usd(self) -> float:
        return self._day_spend_at_start + self.run_spend_usd

    def check(self, projected_usd: float) -> None:
        """Raise if issuing a call costing roughly ``projected_usd`` would breach a cap."""
        if self.run_spend_usd + projected_usd > self.run_budget_usd:
            raise BudgetExceeded(
                f"run '{self.run_id}' would exceed its budget: spent "
                f"${self.run_spend_usd:.4f}, next call ~${projected_usd:.4f}, cap "
                f"${self.run_budget_usd:.2f}. Raise MAS_RUN_BUDGET_USD to continue."
            )
        if self.day_spend_usd + projected_usd > self.daily_budget_usd:
            raise BudgetExceeded(
                f"daily budget would be exceeded: ${self.day_spend_usd:.4f} spent today, "
                f"next call ~${projected_usd:.4f}, cap ${self.daily_budget_usd:.2f}."
            )

    def record(self, cost_usd: float, *, model: str, n_calls: int = 1) -> None:
        if cost_usd <= 0:
            return
        with self._lock:
            self.run_spend_usd += cost_usd
            entry = {
                "day": self._day,
                "run_id": self.run_id,
                "model": model,
                "cost_usd": cost_usd,
                "n_calls": n_calls,
            }
            with self.path.open("a") as handle:
                handle.write(json.dumps(entry) + "\n")

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_spend_usd": round(self.run_spend_usd, 6),
            "run_budget_usd": self.run_budget_usd,
            "day": self._day,
            "day_spend_usd": round(self.day_spend_usd, 6),
            "daily_budget_usd": self.daily_budget_usd,
        }
