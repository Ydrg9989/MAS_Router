"""Paths, environment loading and budget defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The repository root, resolved from this file so the harness works regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"
MANIFEST_DIR = DATA_DIR / "manifests"
CONFIG_DIR = REPO_ROOT / "configs"
SPEND_LEDGER = RUNS_DIR / "spend_ledger.jsonl"

UPSTREAM_PINS: dict[str, str] = {
    "multi-agent-teams-hold-experts-back": "a8833a2",
    "agent-psychometrics": "8c882718",
    "agent-scaling": "6f3bfb7",
    "TwinRouterBench": "430acec",
}

HARNESS_VERSION = "0.1.0"


def load_env(path: str | Path | None = None) -> None:
    """Load ``.env`` if present. Never overrides an already-exported variable."""
    from dotenv import load_dotenv

    load_dotenv(path or REPO_ROOT / ".env", override=False)


@dataclass(frozen=True)
class BudgetConfig:
    run_usd: float
    daily_usd: float

    @classmethod
    def from_env(cls) -> "BudgetConfig":
        return cls(
            run_usd=float(os.environ.get("MAS_RUN_BUDGET_USD", "25")),
            daily_usd=float(os.environ.get("MAS_DAILY_BUDGET_USD", "100")),
        )


def git_commit() -> str | None:
    """Current harness commit, recorded on every run for reproducibility."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def upstream_actual_pins() -> dict[str, str | None]:
    """Read the real HEAD of each upstream clone, to compare against UPSTREAM.md."""
    import subprocess

    actual: dict[str, str | None] = {}
    for name in UPSTREAM_PINS:
        path = REPO_ROOT / name
        if not path.exists():
            actual[name] = None
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            actual[name] = result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            actual[name] = None
    return actual
