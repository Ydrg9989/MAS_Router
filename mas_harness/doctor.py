"""Preflight check: is this installation able to run an experiment?

Answers, in one place, the questions that otherwise get discovered halfway through a paid
run: are the upstream pins what we think, are the datasets readable, is there a GPU, is
there an API key, and do the configured model slugs still exist at the prices we assume.

    python -m mas_harness.doctor
    python -m mas_harness.doctor --pool configs/pools/openrouter4.yaml --check-prices
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config

OK = "ok"
WARN = "warn"
FAIL = "fail"

_MARK = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))

    def print(self) -> None:
        width = max(len(name) for _, name, _ in self.rows) if self.rows else 10
        for status, name, detail in self.rows:
            line = f"{_MARK[status]} {name.ljust(width)}"
            if detail:
                line += f"  {detail}"
            print(line)

    @property
    def worst(self) -> str:
        if any(s == FAIL for s, _, _ in self.rows):
            return FAIL
        if any(s == WARN for s, _, _ in self.rows):
            return WARN
        return OK


def check_python(report: Report) -> None:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro} at {sys.executable}"
    status = OK if (version.major, version.minor) >= (3, 11) else FAIL
    report.add(status, "python", detail)
    in_venv = sys.prefix != sys.base_prefix
    report.add(
        OK if in_venv else WARN,
        "virtualenv",
        "active" if in_venv else "not in a venv; upstream deps may collide",
    )


def check_dependencies(report: Report) -> None:
    required = [
        "httpx",
        "pydantic",
        "yaml",
        "pyarrow",
        "pandas",
        "numpy",
        "scipy",
        "sklearn",
        "statsmodels",
        "sympy",
        "datasets",
    ]
    missing = []
    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        report.add(FAIL, "dependencies", f"missing: {', '.join(missing)} (pip install -e .)")
    else:
        report.add(OK, "dependencies", f"{len(required)} core modules importable")

    try:
        import pyro  # noqa: F401

        report.add(OK, "pyro (optional)", "IRT baseline available")
    except ImportError:
        report.add(WARN, "pyro (optional)", 'IRT baseline unavailable; pip install -e ".[irt]"')


def check_teamwork(report: Report) -> None:
    try:
        import teamwork
    except ImportError as exc:
        report.add(
            FAIL,
            "teamwork import",
            f"{exc}. Add the upstream repo to the venv path: "
            f'echo "$PWD/multi-agent-teams-hold-experts-back" > '
            f'$(python -c "import site;print(site.getsitepackages()[0])")/upstream_teamwork.pth',
        )
        return
    report.add(OK, "teamwork import", str(Path(teamwork.__file__).parent))

    try:
        from .tasks.adapters import TaskSpec, build_evaluator

        spec = TaskSpec(
            task_id="selftest",
            suite="mmlu_pro",
            domain="test",
            answer_type="choice",
            prompt="",
            ground_truth="B",
            payload={"question": "q", "options": ["a", "b"], "answer": "B"},
        )
        evaluator = build_evaluator(spec)
        extracted = evaluator.extract("Reasoning here. The answer is 'B'.")
        if extracted == "B" and evaluator.score("The answer is 'B'."):
            report.add(OK, "evaluator selftest", "choice extraction and scoring agree")
        else:
            report.add(FAIL, "evaluator selftest", f"extracted {extracted!r}, expected 'B'")
    except Exception as exc:
        report.add(FAIL, "evaluator selftest", f"{type(exc).__name__}: {exc}")


def check_upstream_pins(report: Report) -> None:
    actual = config.upstream_actual_pins()
    drifted = []
    absent = []
    for name, expected in config.UPSTREAM_PINS.items():
        got = actual.get(name)
        if got is None:
            absent.append(name)
        elif not got.startswith(expected[:7]) and not expected.startswith(got[:7]):
            drifted.append(f"{name}: expected {expected}, found {got}")
    if absent:
        report.add(WARN, "upstream clones", f"absent: {', '.join(absent)}")
    if drifted:
        report.add(WARN, "upstream pins", "; ".join(drifted) + " (update UPSTREAM.md)")
    elif not absent:
        report.add(OK, "upstream pins", f"{len(config.UPSTREAM_PINS)} repos match UPSTREAM.md")


def check_datasets(report: Report) -> None:
    from .tasks.sources import available_suites

    status = available_suites()
    present = [name for name, ok in status.items() if ok]
    missing = [name for name, ok in status.items() if not ok]
    if present:
        report.add(OK, "hf datasets", f"cached: {', '.join(sorted(present))}")
    if missing:
        report.add(FAIL, "hf datasets", f"not cached: {', '.join(sorted(missing))}")
    report.add(
        WARN,
        "hiddenbench",
        "absent; the distributed-information condition is the constructed option-set "
        "partition, labelled distributed_synth and not comparable to published "
        "HiddenBench results (D-010)",
    )


def check_manifests(report: Report) -> None:
    if not config.MANIFEST_DIR.exists():
        report.add(WARN, "manifests", "none built yet (python -m mas_harness.tasks.manifest build)")
        return
    manifests = sorted(config.MANIFEST_DIR.glob("*.json"))
    if not manifests:
        report.add(WARN, "manifests", "none built yet")
        return
    from .tasks.manifest import Manifest

    details = []
    for path in manifests:
        try:
            manifest = Manifest.read(path)
            details.append(f"{manifest.manifest_id}({len(manifest.tasks)})")
        except Exception as exc:
            report.add(FAIL, f"manifest {path.name}", f"{type(exc).__name__}: {exc}")
    if details:
        report.add(OK, "manifests", ", ".join(details))


def check_gpu(report: Report) -> None:
    if shutil.which("nvidia-smi") is None:
        report.add(WARN, "gpu", "nvidia-smi not on PATH; OpenRouter-only operation (D-006)")
        return
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report.add(WARN, "gpu", f"nvidia-smi failed: {exc}")
        return
    if result.returncode != 0:
        report.add(
            WARN,
            "gpu",
            "nvidia-smi cannot reach a driver; local vLLM agents unavailable, "
            "OpenRouter-only operation (D-006)",
        )
        return
    gpus = [line for line in result.stdout.strip().splitlines() if line.strip()]
    report.add(OK, "gpu", f"{len(gpus)} visible: {'; '.join(gpus)}")


def check_disk(report: Report) -> None:
    usage = shutil.disk_usage(config.REPO_ROOT)
    free_gb = usage.free / 1e9
    pct_used = 100.0 * usage.used / usage.total
    detail = f"{free_gb:.0f} GB free, {pct_used:.0f}% used"
    status = OK if free_gb > 100 else (WARN if free_gb > 20 else FAIL)
    report.add(status, "disk", detail)


def check_api(report: Report, *, pool_path: str | None, check_prices: bool) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        report.add(
            FAIL,
            "openrouter key",
            "OPENROUTER_API_KEY unset. This is the only blocker for Stage A. "
            "cp .env.example .env and fill it in.",
        )
    else:
        report.add(OK, "openrouter key", f"set ({len(key)} chars)")

    budget = config.BudgetConfig.from_env()
    report.add(
        OK,
        "budget caps",
        f"run ${budget.run_usd:.2f}, daily ${budget.daily_usd:.2f}",
    )

    if not pool_path:
        return
    try:
        from .pool.agents import AgentPool

        pool = AgentPool.from_yaml(pool_path)
    except Exception as exc:
        report.add(FAIL, "pool config", f"{type(exc).__name__}: {exc}")
        return
    report.add(
        OK,
        "pool config",
        f"{pool.pool_id}: {len(pool.agents)} agents ({', '.join(a.model for a in pool.agents)})",
    )

    if not check_prices:
        return
    if not key:
        report.add(WARN, "price check", "skipped: no API key")
        return
    try:
        from .clients.pricing import fetch_openrouter_prices

        table = fetch_openrouter_prices()
    except Exception as exc:
        report.add(FAIL, "price check", f"could not fetch live prices: {type(exc).__name__}: {exc}")
        return
    missing = [a.model for a in pool.agents if a.provider == "openrouter" and a.model not in table]
    if missing:
        report.add(
            FAIL,
            "price check",
            f"slugs absent from OpenRouter: {', '.join(missing)}. Update the pool YAML.",
        )
    else:
        priced = [a.model for a in pool.agents if a.provider == "openrouter"]
        detail = ", ".join(
            f"{m} ${table.get(m).input_per_m:.2f}/${table.get(m).output_per_m:.2f}" for m in priced
        )
        report.add(OK, "price check", detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the harness installation")
    parser.add_argument("--pool", default=None, help="also validate a pool YAML")
    parser.add_argument(
        "--check-prices",
        action="store_true",
        help="query OpenRouter to confirm every pool slug exists and print its price",
    )
    args = parser.parse_args(argv)

    config.load_env()
    report = Report()
    check_python(report)
    check_dependencies(report)
    check_teamwork(report)
    check_upstream_pins(report)
    check_datasets(report)
    check_manifests(report)
    check_gpu(report)
    check_disk(report)
    check_api(report, pool_path=args.pool, check_prices=args.check_prices)

    report.print()
    worst = report.worst
    print()
    if worst == FAIL:
        print("Result: FAIL — at least one blocker above must be fixed before Stage A.")
        return 1
    if worst == WARN:
        print("Result: WARN — usable, but read the warnings above.")
        return 0
    print("Result: OK — ready to run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
