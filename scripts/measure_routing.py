"""Does a learned router beat not routing, and does the answer depend on the suite?

The contrast this script exists to produce holds everything fixed except capability heterogeneity.
Both suites were run on the same three pools with the same two free protocols, so each cell has the
same 30 organizations and the same model; only the tasks differ. hard366 is three flavours of hard
technical reasoning, where per-domain winners did not reproduce (D-029). crosscap240 demands four
different kinds of thinking, where the departures from the dominant organization did reproduce on
at least one pool.

If routing gains on crosscap240 and not on hard366, the delegation direction has an existence
condition rather than a method, and that is the paper.

    python scripts/measure_routing.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from mas_harness import config
from mas_harness.metrics.delegation import semantic_space
from mas_harness.metrics.routing import evaluate_routing, routing_over_splits
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

# The two protocols that ran on every task of both suites. Including the paid protocols would
# silently restrict every analysis to each pool's discriminating subset and break the comparison.
FREE_PROTOCOLS = ("single_expert", "independent_majority")

SUITES = {
    "hard366": {
        "manifest": "hard366.json",
        "runs": {"strong4": "strong4-a", "decorrelated4": "decorr4-a",
                 "correlated4": "correlated4-a"},
    },
    "crosscap240": {
        "manifest": "crosscap240.json",
        "runs": {"strong4": "crosscap-strong4", "decorrelated4": "crosscap-decorr4",
                 "correlated4": "crosscap-corr4"},
    },
}

OUTPUT = config.RUNS_DIR / "routing.json"

# Enough partitions that the mean gain is stable to well under a tenth of a point, which is the
# resolution the conclusion turns on. The manifest split is reported alongside as one draw.
N_SPLITS = 60


def domain_of(manifest: Manifest) -> dict[str, str]:
    return {spec.task_id: spec.domain for spec in manifest.tasks}


def main() -> None:
    report: dict[str, dict] = {}

    for suite, spec in SUITES.items():
        manifest = Manifest.read(config.DATA_DIR / "manifests" / spec["manifest"])
        by_id = manifest.by_id()
        tasks = sorted(by_id)
        # Embed once per suite: the three pools share the task set, and the encoder is the slow
        # part. This also guarantees the pools are compared in an identical task geometry.
        space = semantic_space(tasks, [by_id[t].prompt for t in tasks])
        domains = domain_of(manifest)
        print(f"\n=== {suite}  ({len(tasks)} tasks, {space.method})")
        if space.fallback_used:
            print("    WARNING: embedding fallback in use, semantic baseline is weak")

        report[suite] = {"n_tasks": len(tasks), "embedding": space.method, "pools": {}}

        for pool, run_id in spec["runs"].items():
            episodes = [
                e
                for e in RunDirectory(config.RUNS_DIR, run_id).load_episodes()
                if e.intervention.kind == "none"
            ]
            result = evaluate_routing(
                episodes,
                task_space=space,
                train_task_ids=manifest.splits["calibration"],
                test_task_ids=manifest.splits["test"],
                only_protocols=FREE_PROTOCOLS,
            )
            payload = result.to_dict()

            model = result.model
            if model is not None:
                # Where does it route? A router that switches only within one domain is a
                # different claim from one that separates the capabilities.
                by_domain: dict[str, Counter] = defaultdict(Counter)
                for task, organization in model.chosen.items():
                    by_domain[domains.get(task, "?")][organization] += 1
                payload["q_theta_choices_by_domain"] = {
                    domain: dict(counts.most_common(3)) for domain, counts in sorted(
                        by_domain.items()
                    )
                }

            report[suite]["pools"][pool] = payload

            print(f"\n  -- {pool}  ({run_id})")
            print(
                f"     {result.n_train_tasks} train / {result.n_test_tasks} test tasks, "
                f"{result.n_organizations} organizations"
            )
            for name, entry in sorted(result.results.items(), key=lambda kv: -kv[1].accuracy):
                gain = "" if name == "fixed_best" else f"{entry.gain_over_fixed_best:+6.1f} pp"
                significance = (
                    ""
                    if name in {"fixed_best", "oracle"}
                    else f"  p={entry.p_value:.3f}  [{entry.ci_low:+.1f}, {entry.ci_high:+.1f}]"
                )
                print(
                    f"     {name:24s} acc={entry.accuracy:.3f}  {gain:>10s}"
                    f"  orgs={entry.n_distinct_organizations:2d}{significance}"
                )
            print(
                f"     headroom={result.oracle_headroom:.1f} pp   "
                f"selection gap={result.selection_gap:+.1f} pp"
            )
            print(f"     {result.verdict}")

            repeated = routing_over_splits(
                episodes,
                task_space=space,
                domains=domains,
                n_splits=N_SPLITS,
                only_protocols=FREE_PROTOCOLS,
            )
            payload["over_splits"] = repeated
            print(f"     over {repeated['n_splits']} resplits:")
            for name, entry in sorted(
                repeated["gain_over_fixed_best"].items(), key=lambda kv: -kv[1]["mean"]
            ):
                if name == "fixed_best":
                    continue
                print(
                    f"       {name:24s} {entry['mean']:+6.2f} pp  sd={entry['sd']:.2f}"
                    f"  [{entry['q05']:+.1f}, {entry['q95']:+.1f}]"
                    f"  ahead in {entry['frac_positive']:.0%} of splits"
                )
            print(
                f"       {'headroom':24s} {repeated['oracle_headroom']['mean']:6.2f} pp"
                f"  sd={repeated['oracle_headroom']['sd']:.2f}"
            )
            print(
                f"       {'selection gap':24s} {repeated['selection_gap']['mean']:+6.2f} pp"
                f"  sd={repeated['selection_gap']['sd']:.2f}"
            )

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
