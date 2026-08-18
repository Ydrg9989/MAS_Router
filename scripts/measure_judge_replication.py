"""Score J1-J4 of the 2026-08-13 judge-replication pre-registration.

`independent_judge` was named in advance, before any `crosscap240` priced episode existed, because
D-042 found it the only one of five interaction protocols positive in all three `hard366` pools —
and because D-041 found that *choosing* the best protocol per pool is noise (split-half 0.00-0.17).
This applies the frozen thresholds to the new suite.

    python scripts/measure_judge_replication.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import numpy as np

from mas_harness import config
from mas_harness.metrics.research_questions import stratified_resplit, summarise
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

NAMED = "independent_judge"
AGGREGATION = ("independent_majority", "single_expert")
EFFECT_PP = 1.0
N_REPEATS = 60
OUTPUT = config.RUNS_DIR / "judge_replication.json"

SUITES = {
    "crosscap240": {
        "manifest": "crosscap240.json",
        "runs": {
            "strong4": "crosscap-strong4",
            "decorrelated4": "crosscap-decorr4",
            "correlated4": "crosscap-corr4",
        },
    },
    "hard366": {
        "manifest": "hard366.json",
        "runs": {
            "strong4": "strong4-a",
            "decorrelated4": "decorr4-a",
            "correlated4": "correlated4-a",
        },
    },
}


def load_cell(run_id: str, manifest: Manifest) -> dict[str, Any]:
    """Grand-coalition outcomes per protocol, plus the episodes the aggregator did not finish."""
    directory = RunDirectory(config.RUNS_DIR, run_id)
    outcomes: dict[str, dict[str, bool]] = defaultdict(dict)
    truncated: dict[str, set[str]] = defaultdict(set)
    sizes: dict[str, int] = {}

    episodes = [e for e in directory.load_episodes() if e.intervention.kind == "none"]
    grand = max(len(e.coalition) for e in episodes)
    for episode in episodes:
        if len(episode.coalition) != grand:
            continue
        outcomes[episode.protocol_id][episode.task_id] = bool(episode.correct)
        # D-028: a non-terminating aggregator call is missing data, not a wrong answer. It is
        # scored wrong by D-019, so it must be identifiable to report the second scoring.
        if any(c.finish_reason not in ("stop", None, "") for c in episode.calls):
            truncated[episode.protocol_id].add(episode.task_id)
        sizes[episode.protocol_id] = len(outcomes[episode.protocol_id])

    protocols = sorted(outcomes)
    shared = sorted(set.intersection(*[set(outcomes[p]) for p in protocols]))
    domains = {s.task_id: s.domain for s in manifest.tasks}
    labels = sorted({domains[t] for t in shared})
    return {
        "protocols": protocols,
        "tasks": shared,
        "correct": np.array([[float(outcomes[p][t]) for t in shared] for p in protocols]),
        "domain_index": np.array([labels.index(domains[t]) for t in shared]),
        "truncated": {p: sorted(truncated[p] & set(shared)) for p in protocols},
        "n_episodes": sizes,
    }


def score(cell: dict[str, Any], *, keep: np.ndarray | None = None, seed: int = 20260813):
    """Each protocol's gain over the calibration-chosen best aggregation rule, over resplits."""
    protocols = cell["protocols"]
    correct = cell["correct"] if keep is None else cell["correct"][:, keep]
    domain_index = cell["domain_index"] if keep is None else cell["domain_index"][keep]
    aggregation = [i for i, p in enumerate(protocols) if p in AGGREGATION]
    if not aggregation or correct.shape[1] < 8:
        return {"note": "too few tasks or no aggregation rule"}

    rng = np.random.default_rng(seed)
    gains: dict[str, list[float]] = defaultdict(list)
    winners: list[int] = []
    agree = 0
    for _ in range(N_REPEATS):
        train, test = stratified_resplit(domain_index, 0.5, rng)
        calibrated = correct[np.ix_(aggregation, train)].mean(axis=1)
        baseline_row = aggregation[int(np.argmax(calibrated))]
        baseline = float(correct[baseline_row, test].mean())
        for i, name in enumerate(protocols):
            gains[name].append(100.0 * (float(correct[i, test].mean()) - baseline))
        # J3: does the argmax *protocol* reproduce across the two halves of a split?
        winners.append(int(correct[:, train].mean(axis=1).argmax()))
        agree += int(winners[-1] == int(correct[:, test].mean(axis=1).argmax()))

    return {
        "n_tasks": int(correct.shape[1]),
        "gain_over_calibrated_aggregation": {n: summarise(v) for n, v in sorted(gains.items())},
        "argmax_protocol_reproducibility": agree / N_REPEATS,
        "accuracy": {n: float(correct[i].mean()) for i, n in enumerate(protocols)},
    }


def main() -> None:
    report: dict[str, Any] = {
        "generated_by": "scripts/measure_judge_replication.py",
        "preregistration": "Docs/preregistrations/2026-08-13-judge-replication.md",
        "named_protocol": NAMED,
        "suites": {},
    }

    for suite, spec in SUITES.items():
        manifest = Manifest.read(config.DATA_DIR / "manifests" / spec["manifest"])
        report["suites"][suite] = {}
        for pool, run_id in spec["runs"].items():
            cell = load_cell(run_id, manifest)
            # J2's second scoring: drop every task where ANY grand-coalition protocol failed to
            # terminate, so the comparison stays paired across protocols rather than giving each
            # one its own task set.
            bad = set().union(*cell["truncated"].values()) if cell["truncated"] else set()
            keep = np.array([i for i, t in enumerate(cell["tasks"]) if t not in bad])
            report["suites"][suite][pool] = {
                "run_id": run_id,
                "n_tasks": len(cell["tasks"]),
                "n_tasks_after_excluding_truncated": int(len(keep)),
                "truncation_rate": {
                    p: len(v) / max(len(cell["tasks"]), 1) for p, v in cell["truncated"].items()
                },
                "as_scored": score(cell),
                "truncated_excluded": score(cell, keep=keep) if len(keep) >= 8 else {},
            }

    def judge(suite: str, pool: str, variant: str) -> dict[str, float]:
        node = report["suites"][suite][pool].get(variant, {})
        return node.get("gain_over_calibrated_aggregation", {}).get(NAMED, {})

    target = "crosscap240"
    pools = list(SUITES[target]["runs"])
    j1 = [judge(target, p, "as_scored").get("mean", float("nan")) for p in pools]
    j2 = [judge(target, p, "truncated_excluded").get("mean", float("nan")) for p in pools]
    j3 = [
        report["suites"][target][p]["as_scored"]["argmax_protocol_reproducibility"]
        for p in pools
    ]
    j4 = [report["suites"][target][p]["truncation_rate"].get(NAMED, 0.0) for p in pools]

    decision = {
        "J1_gain_pp": dict(zip(pools, j1, strict=True)),
        "J1_positive": bool(
            sum(g >= EFFECT_PP for g in j1) >= 2 and all(g >= 0 for g in j1)
        ),
        "J2_gain_pp_truncated_excluded": dict(zip(pools, j2, strict=True)),
        "J2_signs_agree": bool(all(np.sign(a) == np.sign(b) for a, b in zip(j1, j2, strict=True))),
        "J3_argmax_protocol_reproducibility": dict(zip(pools, j3, strict=True)),
        "J3_refuted_selection_is_learnable": bool(np.mean(j3) >= 0.5),
        "J4_truncation_rate": dict(zip(pools, j4, strict=True)),
        "J4_refuted_suite_not_comparable": bool(max(j4) > 0.10),
    }
    decision["verdict"] = (
        "POSITIVE"
        if decision["J1_positive"] and decision["J2_signs_agree"]
        and not decision["J4_refuted_suite_not_comparable"]
        else "REFUTED"
    )
    report["decision"] = decision
    OUTPUT.write_text(json.dumps(report, indent=1))

    for suite in SUITES:
        print(f"\n=== {suite}: {NAMED} minus the calibration-chosen best aggregation rule")
        print(f"{'pool':16s} {'as scored':>22s} {'truncated excluded':>22s} {'trunc rate':>11s}")
        for pool in SUITES[suite]["runs"]:
            a = judge(suite, pool, "as_scored")
            b = judge(suite, pool, "truncated_excluded")
            rate = report["suites"][suite][pool]["truncation_rate"].get(NAMED, 0.0)
            print(
                f"{pool:16s} {a.get('mean', float('nan')):+8.2f} pp "
                f"({a.get('frac_positive', float('nan')):.0%})"
                f"   {b.get('mean', float('nan')):+8.2f} pp "
                f"({b.get('frac_positive', float('nan')):.0%})   {rate:10.1%}"
            )

    print("\n=== J3: does the argmax protocol reproduce across a split? (predicted < 0.5)")
    for pool in pools:
        value = report["suites"][target][pool]["as_scored"]["argmax_protocol_reproducibility"]
        print(f"    {pool:16s} {value:.2f}")

    print("\n=== the pre-registered decision")
    for key in ("J1_positive", "J2_signs_agree", "J3_refuted_selection_is_learnable",
                "J4_refuted_suite_not_comparable"):
        print(f"    {key:38s} {decision[key]}")
    print(f"\n    VERDICT: {decision['verdict']}")
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
