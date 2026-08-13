"""Run RQ2-RQ5 and apply the go/no-go rule fixed in the 2026-08-13 pre-registration.

Four of the delegation direction's five research questions were specified and never run. This
driver runs them, on banked data, for $0, and then applies the decision rule *as written* rather
than as it looks after seeing the numbers.

    RQ2'  routing with the five interaction protocols in the choice set  (hard366, 3 pools)
    RQ3   dense counterfactual supervision against an execution log      (crosscap240, 70 pools)
    RQ4   domain, agent and organization holdout                         (crosscap240, 70 pools)
    RQ5   solo or collaborate                                            (crosscap240, 70 pools)

    python scripts/measure_research_questions.py
    python scripts/measure_research_questions.py --limit 6 --repeats 4   # smoke test
"""

from __future__ import annotations

import os

# Before numpy: one BLAS thread per worker, since the parallelism is at the pool level. D-040
# measured a several-fold slowdown when both layers thread.
for _variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(_variable, "1")

import argparse  # noqa: E402

# `scripts/` is not a package, so the sweep driver is loaded by path. Reusing it rather than
# reimplementing the substrate is what keeps this driver behind the pool sweep's section 9 gate.
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
    organization_outcomes,
    pool_coalitions,
    vote_outcomes,
)
from mas_harness.metrics.research_questions import (  # noqa: E402
    Grid,
    generalization,
    routing_over_family,
    solo_or_collaborate,
    supervision_efficiency,
)
from mas_harness.records.writer import RunDirectory  # noqa: E402
from mas_harness.tasks.manifest import Manifest  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_pool_sweep_driver", pathlib.Path(__file__).resolve().parent / "measure_pool_sweep.py"
)
_pool_sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pool_sweep)
SUITES, load_suite = _pool_sweep.SUITES, _pool_sweep.load_suite

VOTE = "independent_majority"
EXPERT = "single_expert"
AGGREGATION = (VOTE, EXPERT)
OUTPUT = config.RUNS_DIR / "research_questions.json"

# The threshold that matters, fixed in the pre-registration: roughly half the selection-variance
# cost measured in D-040 and a tenth of the phantom headroom. Below it, nothing is distinguishable
# from the noise D-033 showed swamps single-split routing numbers.
EFFECT_PP = 1.0
AHEAD_FRACTION = 0.60


# ---- grids -----------------------------------------------------------------------------------


def sweep_grid(pool: tuple[int, ...], substrate, index, votes) -> Grid:
    """The 30-organization grid for one four-agent pool, from the certified sweep reconstruction."""
    coalitions = pool_coalitions(pool)
    outcomes = organization_outcomes(
        pool, substrate=substrate, index=index, votes=votes,
        agent_correct=substrate.correct, experts=expert_table(pool, substrate),
    )
    return Grid(
        labels=[f"{VOTE}[{c}]" for c in coalitions] + [f"{EXPERT}[{c}]" for c in coalitions],
        tasks=list(substrate.tasks),
        correct=outcomes,
        members=list(coalitions) * 2,
        protocols=[VOTE] * len(coalitions) + [EXPERT] * len(coalitions),
        domain_index=substrate.domain_index,
        embeddings=substrate.embeddings,
    )


def priced_grid(run_id: str, manifest: Manifest, embeddings_by_task: dict[str, np.ndarray]) -> Grid:
    """Every organization that ran on `hard366`, including the five interaction protocols.

    The priced protocols ran on the grand coalition only, over each pool's discriminating subset,
    so the family is 15 coalitions x 2 aggregation rules + 5 x 1 = 35 and the task set is the
    intersection. Both facts are properties of what was bought, not choices made here.
    """
    directory = RunDirectory(config.RUNS_DIR, run_id)
    correct: dict[tuple[str, tuple[int, ...]], dict[str, bool]] = {}
    for episode in directory.load_episodes():
        if episode.intervention.kind != "none":
            continue
        key = (episode.protocol_id, tuple(sorted(episode.coalition)))
        correct.setdefault(key, {})[episode.task_id] = bool(episode.correct)

    keys = sorted(correct)
    shared = sorted(set.intersection(*[set(correct[k]) for k in keys]) & set(embeddings_by_task))
    domains = {s.task_id: s.domain for s in manifest.tasks}
    labels = sorted({domains[t] for t in shared})
    return Grid(
        labels=[f"{p}[{'-'.join(map(str, c))}]" for p, c in keys],
        tasks=shared,
        correct=np.array([[float(correct[k][t]) for t in shared] for k in keys]),
        members=[c for _, c in keys],
        protocols=[p for p, _ in keys],
        domain_index=np.array([labels.index(domains[t]) for t in shared]),
        embeddings=np.array([embeddings_by_task[t] for t in shared]),
    )


# ---- per-pool work ---------------------------------------------------------------------------


def run_pool(payload: tuple) -> dict[str, Any]:
    pool, substrate, index, votes, lodo_names, repeats, seed = payload
    started = time.time()
    grid = sweep_grid(pool, substrate, index, votes)

    position = {t: i for i, t in enumerate(grid.tasks)}
    lodo = {
        domain: (
            np.array(sorted(position[t] for t in train if t in position)),
            np.array(sorted(position[t] for t in test if t in position)),
        )
        for domain, (train, test) in lodo_names.items()
    }

    return {
        "pool": list(pool),
        "members": [substrate.agents[a] for a in pool],
        "rq3_supervision": supervision_efficiency(grid, n_repeats=repeats, seed=seed),
        "rq4_generalization": generalization(grid, lodo=lodo, n_repeats=repeats, seed=seed),
        "rq5_solo_or_collaborate": solo_or_collaborate(
            grid, n_repeats=max(repeats * 3, 8), seed=seed
        ),
        "seconds": time.time() - started,
    }


def run_priced(payload: tuple) -> dict[str, Any]:
    pool_name, run_id, repeats, seed = payload
    manifest = Manifest.read(config.DATA_DIR / "manifests" / "hard366.json")
    from mas_harness.metrics.delegation import semantic_space

    by_id = manifest.by_id()
    tasks = sorted(by_id)
    space = semantic_space(tasks, [by_id[t].prompt for t in tasks])
    embeddings = dict(zip(space.task_ids, space.features, strict=True))

    grid = priced_grid(run_id, manifest, embeddings)
    aggregation_rows = np.array(
        [r for r, p in enumerate(grid.protocols) if p in AGGREGATION]
    )
    return {
        "pool": pool_name,
        "run_id": run_id,
        "n_tasks": grid.n_task,
        "protocols": sorted(set(grid.protocols)),
        # Same tasks, same splits, two choice sets: the difference is the protocol axis alone.
        "full_family": routing_over_family(grid, n_repeats=repeats, seed=seed),
        "aggregation_only": routing_over_family(
            grid, n_repeats=repeats, restrict_rows=aggregation_rows, seed=seed
        ),
    }


# ---- the pre-registered decision --------------------------------------------------------------


def decide(report: dict[str, Any]) -> dict[str, Any]:
    """Apply §5 of the pre-registration exactly: thresholds, controls, and the majority rule."""
    pools = report["crosscap240_pools"]

    def pooled(path: list[str]) -> dict[str, float]:
        values = []
        for entry in pools:
            node: Any = entry
            for key in path:
                node = node.get(key, {}) if isinstance(node, dict) else {}
            if isinstance(node, dict) and np.isfinite(node.get("mean", np.nan)):
                values.append(node["mean"])
        array = np.asarray(values, dtype=float)
        if not array.size:
            return {"mean": float("nan"), "frac_pools_positive": float("nan"), "n_pools": 0}
        return {
            "mean": float(array.mean()),
            "median": float(np.median(array)),
            "frac_pools_positive": float((array > 0).mean()),
            "frac_pools_over_threshold": float((array >= EFFECT_PP).mean()),
            "n_pools": int(array.size),
        }

    priced = report["hard366_priced"]
    full = [p["full_family"]["gain_over_fixed_best"].get("q_theta", {}) for p in priced]
    full_ctl = [
        p["full_family"]["gain_over_fixed_best"].get("q_theta_shuffled", {}) for p in priced
    ]
    agg = [p["aggregation_only"]["gain_over_fixed_best"].get("q_theta", {}) for p in priced]

    def mean_of(entries, key="mean"):
        vals = [e.get(key, np.nan) for e in entries]
        vals = [v for v in vals if np.isfinite(v)]
        return float(np.mean(vals)) if vals else float("nan")

    q2a_gain, q2a_ahead = mean_of(full), mean_of(full, "frac_positive")
    q2a = {
        "gain_pp": q2a_gain,
        "frac_resplits_ahead": q2a_ahead,
        "shuffled_control_pp": mean_of(full_ctl),
        "n_pools_over_threshold": int(sum(1 for e in full if e.get("mean", -9) >= EFFECT_PP)),
        "refuted": bool(q2a_gain >= EFFECT_PP and q2a_ahead >= AHEAD_FRACTION),
    }
    q2b_delta = q2a_gain - mean_of(agg)
    q2b = {
        "full_family_pp": q2a_gain,
        "aggregation_only_pp": mean_of(agg),
        "delta_pp": q2b_delta,
        "refuted": bool(np.isfinite(q2b_delta) and q2b_delta >= EFFECT_PP),
    }

    budgets = sorted({b for p in pools for b in p["rq3_supervision"]["budgets"]}, key=float)
    dense_vs_log = {}
    dense_gain = {}
    for budget in budgets:
        deltas, gains = [], []
        for entry in pools:
            node = entry["rq3_supervision"]["budgets"].get(budget)
            if not node:
                continue
            if np.isfinite(node.get("dense_minus_observational_pp", np.nan)):
                deltas.append(node["dense_minus_observational_pp"])
            mean = node["dense_gain_over_fixed_best"].get("mean", np.nan)
            if np.isfinite(mean):
                gains.append(mean)
        dense_vs_log[budget] = float(np.mean(deltas)) if deltas else float("nan")
        dense_gain[budget] = float(np.mean(gains)) if gains else float("nan")
    unstarved = {}
    for budget in budgets:
        values = [
            p["rq3_supervision"]["budgets"][budget]["dense_gain_over_unstarved_baseline"]["mean"]
            for p in pools
            if budget in p["rq3_supervision"]["budgets"]
            and np.isfinite(
                p["rq3_supervision"]["budgets"][budget]
                ["dense_gain_over_unstarved_baseline"].get("mean", np.nan)
            )
        ]
        unstarved[budget] = float(np.mean(values)) if values else float("nan")
    finite_deltas = [v for v in dense_vs_log.values() if np.isfinite(v)]
    q3a = {
        "dense_minus_observational_pp_by_budget": dense_vs_log,
        "refuted": bool(finite_deltas and all(v < 0 for v in finite_deltas)),
    }
    best_dense = max((v for v in dense_gain.values() if np.isfinite(v)), default=float("nan"))
    best_unstarved = max((v for v in unstarved.values() if np.isfinite(v)), default=float("nan"))
    q3b = {
        "dense_gain_over_fixed_best_by_budget": dense_gain,
        "best_budget_gain_pp": best_dense,
        "refuted": bool(np.isfinite(best_dense) and best_dense >= EFFECT_PP),
        # The audit of the pre-registered criterion itself. At small budgets the frozen baseline is
        # chosen from a handful of observed tasks, so "gain over fixed-best" measures the baseline's
        # degradation. Against a baseline that knows each organization's overall training accuracy —
        # which any deployer does — the same routers are compared on equal footing.
        "dense_gain_over_unstarved_baseline_by_budget": unstarved,
        "best_budget_gain_over_unstarved_pp": best_unstarved,
        "refuted_against_unstarved_baseline": bool(
            np.isfinite(best_unstarved) and best_unstarved >= EFFECT_PP
        ),
    }

    regimes = ("domain_holdout", "agent_holdout", "organization_holdout")
    # `conditioning_gain` is reported but NOT used by the rule: the pre-registration is frozen and
    # names the raw gain. It is here because under a holdout the router may choose from
    # organizations the frozen baseline never saw, so the raw gain mixes task-conditioning with a
    # larger feasible set. The shuffled twin, which gets the same enlarged set, is what the frozen
    # rule uses to control for that; the conditioning gain isolates it directly. If the two ever
    # disagree, the decision entry must say so rather than quietly prefer one.
    q4_detail = {
        regime: {
            "gain": pooled(["rq4_generalization", regime, "gain"]),
            "shuffled": pooled(["rq4_generalization", regime, "shuffled"]),
            "conditioning_gain": pooled(["rq4_generalization", regime, "conditioning_gain"]),
        }
        for regime in regimes
    }
    q4_detail["iid_reference"] = {
        "gain": pooled(["rq4_generalization", "iid", "gain"]),
        "conditioning_gain": pooled(["rq4_generalization", "iid", "conditioning_gain"]),
    }
    cleared = [
        regime
        for regime in regimes
        if q4_detail[regime]["gain"].get("mean", -9) >= EFFECT_PP
        and q4_detail[regime]["shuffled"].get("mean", 9) < EFFECT_PP
    ]
    q4 = {**q4_detail, "regimes_over_threshold": cleared, "refuted": bool(len(cleared) >= 2)}

    q5_gain = pooled(["rq5_solo_or_collaborate", "gain_over_better_fixed_policy"])
    q5_ctl = pooled(["rq5_solo_or_collaborate", "shuffled_control"])
    ahead = [
        p["rq5_solo_or_collaborate"]["gain_over_better_fixed_policy"].get("frac_positive", np.nan)
        for p in pools
    ]
    ahead = [v for v in ahead if np.isfinite(v)]
    q5 = {
        "gain": q5_gain,
        "shuffled_control": q5_ctl,
        "oracle_over_the_pair": pooled(["rq5_solo_or_collaborate", "oracle_over_the_pair"]),
        "mean_frac_resplits_ahead": float(np.mean(ahead)) if ahead else float("nan"),
        "refuted": bool(
            q5_gain.get("mean", -9) >= EFFECT_PP
            and (np.mean(ahead) if ahead else 0) >= AHEAD_FRACTION
        ),
    }

    # GO requires all three conditions of §5: threshold cleared, control not cleared, majority.
    def control_clean(name: str) -> bool:
        if name == "Q2a":
            return q2a["shuffled_control_pp"] < EFFECT_PP
        if name == "Q4":
            return True  # already required per-regime above
        if name == "Q5":
            return q5_ctl.get("mean", 9) < EFFECT_PP
        return True

    def majority(name: str) -> bool:
        if name == "Q2a":
            return q2a["n_pools_over_threshold"] > len(priced) / 2
        if name == "Q4":
            return all(
                q4_detail[r]["gain"].get("frac_pools_over_threshold", 0) > 0.5 for r in cleared
            ) if cleared else False
        if name == "Q5":
            return q5_gain.get("frac_pools_over_threshold", 0) > 0.5
        return True

    triggers = [
        name
        for name, entry in (("Q2a", q2a), ("Q2b", q2b), ("Q3b", q3b), ("Q4", q4), ("Q5", q5))
        if entry["refuted"] and control_clean(name) and majority(name)
    ]
    # A trigger that does not survive its own audit is reported as such rather than silently
    # dropped or silently honoured. Q3b is the only criterion here with a known defect.
    audited = [
        name
        for name in triggers
        if name != "Q3b" or q3b["refuted_against_unstarved_baseline"]
    ]

    return {
        "threshold_pp": EFFECT_PP,
        "ahead_fraction": AHEAD_FRACTION,
        "Q2a_interaction_family": q2a,
        "Q2b_protocol_axis_adds": q2b,
        "Q3a_dense_beats_log": q3a,
        "Q3b_dense_arm_pays": q3b,
        "Q4_generalization": q4,
        "Q5_solo_or_collaborate": q5,
        "go_triggers_as_written": triggers,
        "go_triggers_surviving_audit": audited,
        "verdict_as_written": "GO" if triggers else "NO-GO",
        "verdict": "GO" if audited else "NO-GO",
        "rule": (
            "GO if at least one of Q2a, Q2b, Q3b, Q4, Q5 is refuted in the direction of routing "
            "working, the shuffled twin does not clear the same bar, and the effect holds on a "
            "majority of pools. Q3a is reportable either way and outside the rule."
        ),
    }


# ---- driver ----------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--priced-repeats", type=int, default=60)
    parser.add_argument("--workers", type=int, default=min(96, os.cpu_count() or 8))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260813)
    arguments = parser.parse_args()

    started = time.time()
    print("=== RQ2-RQ5, pre-registered 2026-08-13")

    print("\n--- RQ2': routing with the five interaction protocols in the choice set")
    priced_payloads = [
        (name, run_id, arguments.priced_repeats, arguments.seed)
        for name, run_id in SUITES["hard366"]["named"].items()
    ]
    with ProcessPoolExecutor(max_workers=min(3, arguments.workers)) as executor:
        priced = list(executor.map(run_priced, priced_payloads))
    for entry in priced:
        full = entry["full_family"]["gain_over_fixed_best"].get("q_theta", {})
        agg = entry["aggregation_only"]["gain_over_fixed_best"].get("q_theta", {})
        control = entry["full_family"]["gain_over_fixed_best"].get("q_theta_shuffled", {})
        print(
            f"    {entry['pool']:14s} {entry['n_tasks']:3d} tasks  "
            f"{entry['full_family']['n_organizations']:2d} orgs: "
            f"q_theta {full.get('mean', float('nan')):+6.2f} pp "
            f"(ahead {full.get('frac_positive', float('nan')):.0%}, "
            f"shuffled {control.get('mean', float('nan')):+6.2f})   vs "
            f"{entry['aggregation_only']['n_organizations']} orgs: "
            f"{agg.get('mean', float('nan')):+6.2f} pp"
        )

    print("\n--- RQ3/4/5 on every four-agent pool of crosscap240")
    substrate, _, _, _, _ = load_suite("crosscap240")
    index = CoalitionIndex.build(substrate.n_agents, max_size=4)
    votes = vote_outcomes(substrate.classes, index, substrate.competence, substrate.correct_class)
    manifest = Manifest.read(config.DATA_DIR / "manifests" / "crosscap240.json")
    lodo_names = {
        name.split("::", 1)[1]: (
            manifest.splits[name], manifest.splits[f"lodo_test::{name.split('::', 1)[1]}"]
        )
        for name in manifest.splits
        if name.startswith("lodo_train::")
    }
    print(f"    {len(lodo_names)} leave-one-domain-out splits: {', '.join(sorted(lodo_names))}")

    pools = [tuple(c) for c in itertools.combinations(range(substrate.n_agents), 4)]
    if arguments.limit:
        pools = pools[: arguments.limit]
    payloads = [
        (pool, substrate, index, votes, lodo_names, arguments.repeats, arguments.seed)
        for pool in pools
    ]
    pool_started = time.time()
    with ProcessPoolExecutor(max_workers=arguments.workers) as executor:
        results = []
        for done, record in enumerate(executor.map(run_pool, payloads), start=1):
            results.append(record)
            if done % 10 == 0 or done == len(payloads):
                print(f"    {done}/{len(payloads)} pools  ({time.time() - pool_started:.0f}s)")

    report = {
        "generated_by": "scripts/measure_research_questions.py",
        "preregistration": "Docs/preregistrations/2026-08-13-rq2-rq5.md",
        "n_pools": len(results),
        "n_tasks_crosscap240": substrate.n_tasks,
        "agents": substrate.agents,
        "hard366_priced": priced,
        "crosscap240_pools": results,
    }
    report["decision"] = decide(report)
    OUTPUT.write_text(json.dumps(report, indent=1))

    decision = report["decision"]
    print("\n--- the pre-registered predictions")
    for key in ("Q2a_interaction_family", "Q2b_protocol_axis_adds", "Q3a_dense_beats_log",
                "Q3b_dense_arm_pays", "Q4_generalization", "Q5_solo_or_collaborate"):
        print(f"    {key:28s} refuted={str(decision[key]['refuted']):5s}")
    q3b = decision["Q3b_dense_arm_pays"]
    print("\n--- the audit of Q3b's own criterion")
    print(f"    {'budget':>8s} {'vs starved baseline':>21s} {'vs unstarved baseline':>23s}")
    for budget in sorted(q3b["dense_gain_over_fixed_best_by_budget"], key=float):
        print(
            f"    {budget:>8s} {q3b['dense_gain_over_fixed_best_by_budget'][budget]:+21.2f} "
            f"{q3b['dense_gain_over_unstarved_baseline_by_budget'][budget]:+23.2f}"
        )
    print(f"\n    triggers as written:    {decision['go_triggers_as_written'] or 'none'}")
    print(f"    triggers after audit:   {decision['go_triggers_surviving_audit'] or 'none'}")
    print(f"    VERDICT: {decision['verdict']}")
    print(f"\nwrote {OUTPUT}  (total {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
