"""E1, E2, E4 of the 2026-08-13 positive-selection pre-registration.

D-041 closed per-task routing. What survives is *which* organization to run, and the project has
never treated that as a question — it used the calibration argmax as an incumbent without asking
whether the incumbent is good. It is not: D-040 measures it losing 2.39 pp between calibration and
test, and D-037 established that gap is winner's curse rather than interaction, which makes it
partly recoverable.

    E1  seven fixed-organization selection rules      (both suites, 280 pools)
    E2  the budget comparison at flattened prices     (both suites, 280 pools)
    E4  each protocol as an a-priori rule             (hard366, 3 priced pools)

    python scripts/measure_positive_selection.py
    python scripts/measure_positive_selection.py --limit 6 --repeats 6   # smoke test
"""

from __future__ import annotations

import os

for _variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(_variable, "1")

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402

from mas_harness import config  # noqa: E402
from mas_harness.metrics.pool_sweep import (  # noqa: E402
    CoalitionIndex,
    expert_table,
    pool_coalitions,
    vote_outcomes,
)
from mas_harness.metrics.selection import (  # noqa: E402
    PoolSample,
    cross_pool_fit,
    evaluate_rules,
    organization_descriptor,
    protocol_rules,
)

_HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_sweep = _load("_pool_sweep_driver", "measure_pool_sweep.py")
_rq = _load("_rq_driver", "measure_research_questions.py")

OUTPUT = config.RUNS_DIR / "positive_selection.json"
SUITES = ("crosscap240", "hard366")

_STATE: dict[str, Any] = {}


def _prepare(suite: str) -> None:
    substrate, _, _, _, _ = _sweep.load_suite(suite)
    index = CoalitionIndex.build(substrate.n_agents, max_size=4)
    _STATE[suite] = {
        "substrate": substrate,
        "index": index,
        "votes": vote_outcomes(
            substrate.classes, index, substrate.competence, substrate.correct_class
        ),
    }


def _grid(suite: str, pool: tuple[int, ...]):
    state = _STATE[suite]
    return _rq.sweep_grid(pool, state["substrate"], state["index"], state["votes"])


def _flat_cost(suite: str, pool: tuple[int, ...]) -> np.ndarray:
    """Organization cost with the *domain* price channel removed, agent prices kept.

    D-040 read the tight-budget routing win as priced-by-domain arbitrage: the same organization
    is affordable on domains whose prompts and answers are short. Replacing each agent's per-task
    cost by that agent's own mean across tasks removes exactly that channel and nothing else —
    models still differ in price, so a genuine capability-matching gain would survive.
    """
    state = _STATE[suite]
    substrate = state["substrate"]
    per_agent = substrate.cost.mean(axis=1)
    flat = np.repeat(per_agent[:, None], substrate.n_tasks, axis=1)
    coalitions = pool_coalitions(pool)
    experts = expert_table(pool, substrate)
    chosen = experts[:, substrate.domain_index]
    return np.vstack(
        [
            np.array([flat[list(c)].sum(axis=0) for c in coalitions]),
            np.take_along_axis(flat, chosen, axis=0),
        ]
    )


def _sample(suite: str, pool: tuple[int, ...]) -> PoolSample:
    """Descriptors and calibration accuracy for the cross-pool fit, on the manifest split."""
    grid = _grid(suite, pool)
    train = _STATE[suite]["substrate"].calibration
    return PoolSample(
        features=np.array([organization_descriptor(grid, r, train) for r in range(grid.n_org)]),
        outcome=grid.correct[:, train].mean(axis=1),
    )


def _sample_worker(payload: tuple) -> tuple[np.ndarray, np.ndarray]:
    suite, pool = payload
    sample = _sample(suite, pool)
    return sample.features, sample.outcome


def _pool_worker(payload: tuple) -> dict[str, Any]:
    suite, pool, coefficients, repeats, seed = payload
    grid = _grid(suite, pool)
    substrate = _STATE[suite]["substrate"]
    real_cost = np.vstack(
        [
            np.array([substrate.cost[list(c)].sum(axis=0) for c in pool_coalitions(pool)]),
            np.take_along_axis(
                substrate.cost,
                expert_table(pool, substrate)[:, substrate.domain_index],
                axis=0,
            ),
        ]
    )
    return {
        "pool": list(pool),
        "members": [substrate.agents[a] for a in pool],
        "e1_rules": evaluate_rules(
            grid, coefficients=coefficients, n_repeats=repeats, seed=seed
        ),
        "e2_budget_real_prices": _sweep.budget_comparison(
            grid.correct, real_cost, grid.domain_index,
            substrate.calibration, substrate.test, n_splits=repeats, seed=seed,
        ),
        "e2_budget_flat_prices": _sweep.budget_comparison(
            grid.correct, _flat_cost(suite, pool), grid.domain_index,
            substrate.calibration, substrate.test, n_splits=repeats, seed=seed,
        ),
    }


def _init(suite: str) -> None:
    _prepare(suite)


def run_suite(suite: str, *, repeats: int, workers: int, limit: int, seed: int) -> dict[str, Any]:
    _prepare(suite)
    substrate = _STATE[suite]["substrate"]
    pools = [tuple(c) for c in itertools.combinations(range(substrate.n_agents), 4)]
    if limit:
        pools = pools[:limit]
    print(f"\n=== {suite}: {len(pools)} pools, {substrate.n_tasks} tasks")

    started = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(suite,)) as pool_ex:
        collected = list(pool_ex.map(_sample_worker, [(suite, p) for p in pools]))
    samples = [PoolSample(features=f, outcome=o) for f, o in collected]
    print(f"    descriptors for the cross-pool fit in {time.time() - started:.0f}s")

    # Leave-one-pool-out: the rule applied to a pool is never fitted on it.
    payloads = [
        (suite, pool, cross_pool_fit([s for j, s in enumerate(samples) if j != i]), repeats, seed)
        for i, pool in enumerate(pools)
    ]

    started = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(suite,)) as pool_ex:
        results = []
        for done, record in enumerate(pool_ex.map(_pool_worker, payloads), start=1):
            results.append(record)
            if done % 25 == 0 or done == len(payloads):
                print(f"    {done}/{len(payloads)} pools  ({time.time() - started:.0f}s)")
    return {"n_pools": len(results), "n_tasks": substrate.n_tasks, "pools": results}


def summarise_e1(results: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    names = sorted({n for p in results["pools"] for n in p["e1_rules"]["gain_over_argmax"]})
    for name in names:
        values = np.array(
            [
                p["e1_rules"]["gain_over_argmax"][name]["mean"]
                for p in results["pools"]
                if name in p["e1_rules"]["gain_over_argmax"]
            ]
        )
        values = values[np.isfinite(values)]
        if not values.size:
            continue
        out[name] = {
            "mean_gain_pp": float(values.mean()),
            "median_gain_pp": float(np.median(values)),
            "frac_pools_positive": float((values > 0).mean()),
            "frac_pools_over_1pp": float((values >= 1.0).mean()),
            "n_pools": int(values.size),
        }
    return out


def summarise_e2(results: dict[str, Any]) -> dict[str, Any]:
    def collect(key: str, field: str) -> float:
        values = [p[key].get(field, np.nan) for p in results["pools"]]
        values = [v for v in values if np.isfinite(v)]
        return float(np.mean(values)) if values else float("nan")

    def positive(key: str, field: str) -> float:
        values = [p[key].get(field, np.nan) for p in results["pools"]]
        values = [v for v in values if np.isfinite(v)]
        return float(np.mean(np.array(values) > 0)) if values else float("nan")

    return {
        "real_prices": {
            "tightest_gain_pp": collect("e2_budget_real_prices", "tightest_gain_pp"),
            "tightest_frac_pools_positive": positive("e2_budget_real_prices", "tightest_gain_pp"),
            "unconstrained_gain_pp": collect("e2_budget_real_prices", "unconstrained_gain_pp"),
        },
        "flat_prices": {
            "tightest_gain_pp": collect("e2_budget_flat_prices", "tightest_gain_pp"),
            "tightest_frac_pools_positive": positive("e2_budget_flat_prices", "tightest_gain_pp"),
            "unconstrained_gain_pp": collect("e2_budget_flat_prices", "unconstrained_gain_pp"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=60)
    parser.add_argument("--workers", type=int, default=min(96, os.cpu_count() or 8))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260813)
    arguments = parser.parse_args()

    started = time.time()
    print("=== positive-selection experiments, pre-registered 2026-08-13")
    report: dict[str, Any] = {
        "generated_by": "scripts/measure_positive_selection.py",
        "preregistration": "Docs/preregistrations/2026-08-13-positive-selection.md",
        "suites": {},
    }
    for suite in SUITES:
        results = run_suite(
            suite, repeats=arguments.repeats, workers=arguments.workers,
            limit=arguments.limit, seed=arguments.seed,
        )
        report["suites"][suite] = {
            "n_pools": results["n_pools"],
            "n_tasks": results["n_tasks"],
            "e1": summarise_e1(results),
            "e2": summarise_e2(results),
            "pools": results["pools"],
        }

    print("\n=== E4: each protocol as an a-priori rule (hard366, priced pools)")
    e4: dict[str, Any] = {}
    manifest_path = config.DATA_DIR / "manifests" / "hard366.json"
    from mas_harness.metrics.delegation import semantic_space
    from mas_harness.tasks.manifest import Manifest

    manifest = Manifest.read(manifest_path)
    by_id = manifest.by_id()
    tasks = sorted(by_id)
    space = semantic_space(tasks, [by_id[t].prompt for t in tasks])
    embeddings = dict(zip(space.task_ids, space.features, strict=True))
    for name, run_id in _rq.SUITES["hard366"]["named"].items():
        grid = _rq.priced_grid(run_id, manifest, embeddings)
        e4[name] = protocol_rules(grid, n_repeats=arguments.repeats, seed=arguments.seed)
    report["e4_protocols"] = e4

    OUTPUT.write_text(json.dumps(report, indent=1))

    print("\n=== E1: gain over the calibration argmax (mean over pools)")
    header = f"{'rule':22s}" + "".join(f"{s:>26s}" for s in SUITES)
    print(header)
    rules = sorted(report["suites"][SUITES[0]]["e1"])
    for rule in rules:
        cells = []
        for suite in SUITES:
            entry = report["suites"][suite]["e1"].get(rule)
            cells.append(
                f"{entry['mean_gain_pp']:+8.2f} pp ({entry['frac_pools_positive']:.0%} of pools)"
                if entry else f"{'-':>26s}"
            )
        print(f"{rule:22s}" + "".join(f"{c:>26s}" for c in cells))

    print("\n=== E2: tight-budget routed-minus-global gain, real vs flattened prices")
    for suite in SUITES:
        e2 = report["suites"][suite]["e2"]
        print(
            f"    {suite:12s} real {e2['real_prices']['tightest_gain_pp']:+6.2f} pp "
            f"({e2['real_prices']['tightest_frac_pools_positive']:.0%} of pools)   "
            f"flat {e2['flat_prices']['tightest_gain_pp']:+6.2f} pp "
            f"({e2['flat_prices']['tightest_frac_pools_positive']:.0%} of pools)"
        )

    print("\n=== E4: protocol gain over the calibration-chosen best aggregation rule")
    protocols = sorted(
        {p for v in e4.values() if "gain_over_calibrated_aggregation" in v
         for p in v["gain_over_calibrated_aggregation"]}
    )
    print(f"{'protocol':28s}" + "".join(f"{n:>18s}" for n in e4))
    for protocol in protocols:
        cells = []
        for entry in e4.values():
            node = entry.get("gain_over_calibrated_aggregation", {}).get(protocol)
            cells.append(
                f"{node['mean']:+7.2f} ({node['frac_positive']:.0%})" if node else "-"
            )
        print(f"{protocol:28s}" + "".join(f"{c:>18s}" for c in cells))

    print(f"\nwrote {OUTPUT}  (total {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
