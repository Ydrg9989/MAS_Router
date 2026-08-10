"""Is the routing null a real absence, or just too little calibration data?

`scripts/measure_routing.py` found no leak-free router beating a frozen fixed-best baseline on
either suite, over sixty resplits, with four to eleven points of oracle headroom sitting unclaimed.
There are two very different reasons that could happen. Either per-task organization preferences do
not exist at a scale a router can act on, or they exist and eighty to a hundred and twenty
calibration tasks are nowhere near enough to find them.

Only a learning curve separates those. This script pools the two suites, which share three pools,
the same two free protocols, and therefore the same thirty organizations. Pooling buys two things
at once: 569 unique tasks instead of 240, so calibration can run to nearly 400 tasks, and fifteen
domains instead of four, which is the group count the stability estimate was short of.

If the gain climbs with calibration size, the direction is alive and the answer is data. If it sits
at zero across a four-fold increase, the headroom is not addressable and that is the finding.

    python scripts/measure_routing_pooled.py
"""

from __future__ import annotations

import json

from mas_harness import config
from mas_harness.metrics.delegation import semantic_space
from mas_harness.metrics.routing import routing_over_splits
from mas_harness.metrics.stability import winner_stability
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

FREE_PROTOCOLS = ("single_expert", "independent_majority")
MANIFESTS = ("hard366.json", "crosscap240.json")
POOLS = {
    "strong4": ("strong4-a", "crosscap-strong4"),
    "decorrelated4": ("decorr4-a", "crosscap-decorr4"),
    "correlated4": ("correlated4-a", "crosscap-corr4"),
}
FRACTIONS = (0.10, 0.20, 0.35, 0.50, 0.70)
N_SPLITS = 40

OUTPUT = config.RUNS_DIR / "routing_pooled.json"


def load_tasks() -> tuple[dict[str, str], dict[str, str]]:
    """Prompts and domains over the union of both manifests; 37 GPQA tasks appear in both."""
    prompts: dict[str, str] = {}
    domains: dict[str, str] = {}
    for name in MANIFESTS:
        for spec in Manifest.read(config.DATA_DIR / "manifests" / name).tasks:
            prompts.setdefault(spec.task_id, spec.prompt)
            domains.setdefault(spec.task_id, spec.domain)
    return prompts, domains


def load_episodes(run_ids: tuple[str, ...]):
    """Observational episodes from several runs, with the shared GPQA tasks counted once.

    The two suites were executed separately, so an overlapping task carries one episode per run
    for the same organization. Keeping both would weight those tasks double in every accuracy
    the analysis computes.
    """
    seen: set[tuple] = set()
    episodes = []
    for run_id in run_ids:
        for episode in RunDirectory(config.RUNS_DIR, run_id).load_episodes():
            if episode.intervention.kind != "none":
                continue
            key = (
                episode.task_id,
                episode.protocol_id,
                tuple(sorted(episode.coalition)),
                episode.seed,
            )
            if key in seen:
                continue
            seen.add(key)
            episodes.append(episode)
    return episodes


def main() -> None:
    prompts, domains = load_tasks()
    tasks = sorted(prompts)
    space = semantic_space(tasks, [prompts[t] for t in tasks])
    print(f"pooled suite: {len(tasks)} tasks, {len(set(domains.values()))} domains")
    print(f"embedding: {space.method}")
    if space.fallback_used:
        print("WARNING: embedding fallback in use")

    report: dict[str, dict] = {"n_tasks": len(tasks), "embedding": space.method, "pools": {}}

    for pool, run_ids in POOLS.items():
        episodes = load_episodes(run_ids)
        covered = {e.task_id for e in episodes}
        print(f"\n=== {pool}: {len(episodes)} episodes over {len(covered)} tasks")

        stability = winner_stability(
            episodes,
            grouping="domain",
            by_configuration=True,
            only_protocols=FREE_PROTOCOLS,
        )
        print(
            f"  stability over {len(stability.groups)} domains: "
            f"reproducibility={stability.reproducibility:.3f} "
            f"(null {stability.null_reproducibility:.3f}, p={stability.reproducibility_p:.3f}), "
            f"dominance={stability.dominance:.2f}"
        )
        print(
            f"    off-dominant={stability.reproducibility_off_dominant:.3f} "
            f"over {stability.n_off_dominant} domains"
        )
        print(f"    {stability.verdict}")

        curve = {}
        for fraction in FRACTIONS:
            result = routing_over_splits(
                episodes,
                task_space=space,
                domains={t: d for t, d in domains.items() if t in covered},
                n_splits=N_SPLITS,
                calibration_fraction=fraction,
                only_protocols=FREE_PROTOCOLS,
            )
            curve[f"{fraction:.2f}"] = result
            n_train = int(round(fraction * len(covered)))
            model = result["gain_over_fixed_best"]["q_theta"]
            control = result["gain_over_fixed_best"]["q_theta_shuffled"]
            knn = result["gain_over_fixed_best"]["semantic_knn"]
            print(
                f"  calib={fraction:.2f} (~{n_train:3d} tasks)  "
                f"q_theta {model['mean']:+5.2f} pp (sd {model['sd']:.2f}, "
                f"ahead {model['frac_positive']:.0%})  "
                f"control {control['mean']:+5.2f}  knn {knn['mean']:+5.2f}  "
                f"headroom {result['oracle_headroom']['mean']:5.2f}"
            )

        report["pools"][pool] = {
            "n_episodes": len(episodes),
            "n_tasks": len(covered),
            "stability": stability.to_dict(),
            "curve": curve,
        }

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
