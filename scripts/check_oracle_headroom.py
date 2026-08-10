"""Is the oracle headroom a routing prize, or the maximum of thirty noisy organizations?

Every headroom number this project has reported - 4.9 to 9.3 points in the pool screens, 4 to 11 in
the routing evaluation - is a per-task maximum minus one fixed organization. That statistic is large
even when nothing is routable, because thirty organizations that fail semi-independently will
usually contain one that happens to be right. D-033 concluded that a real prize goes unclaimed; this
script checks whether the prize was ever there.

    python scripts/check_oracle_headroom.py
"""

from __future__ import annotations

import json

from mas_harness import config
from mas_harness.metrics.routing import headroom_against_no_interaction
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

FREE_PROTOCOLS = ("single_expert", "independent_majority")
CELLS = {
    ("hard366", "strong4"): "strong4-a",
    ("hard366", "decorrelated4"): "decorr4-a",
    ("hard366", "correlated4"): "correlated4-a",
    ("crosscap240", "strong4"): "crosscap-strong4",
    ("crosscap240", "decorrelated4"): "crosscap-decorr4",
    ("crosscap240", "correlated4"): "crosscap-corr4",
}

OUTPUT = config.RUNS_DIR / "headroom_null.json"


def main() -> None:
    manifests = {
        name: Manifest.read(config.DATA_DIR / "manifests" / f"{name}.json")
        for name in {suite for suite, _ in CELLS}
    }
    report = {}

    print(
        f"{'cell':30s} {'vs calibration-picked fixed':>29s}    "
        f"{'vs best organization on test':>30s}"
    )
    print(
        f"{'':30s} {'obs':>8s} {'null':>8s} {'excess':>8s}    "
        f"{'obs':>8s} {'null':>8s} {'excess':>8s} {'p':>6s}"
    )
    for (suite, pool), run_id in CELLS.items():
        manifest = manifests[suite]
        episodes = [
            e
            for e in RunDirectory(config.RUNS_DIR, run_id).load_episodes()
            if e.intervention.kind == "none"
        ]
        result = headroom_against_no_interaction(
            episodes,
            train_task_ids=manifest.splits["calibration"],
            test_task_ids=manifest.splits["test"],
            only_protocols=FREE_PROTOCOLS,
        )
        report[f"{suite}/{pool}"] = result
        print(
            f"{suite + '/' + pool:30s} "
            f"{result['observed_headroom']:8.2f} {result['null_headroom_mean']:8.2f} "
            f"{result['excess_over_null']:+8.2f}    "
            f"{result['observed_headroom_over_best']:8.2f} "
            f"{result['null_headroom_over_best_mean']:8.2f} "
            f"{result['excess_over_null_over_best']:+8.2f} "
            f"{result['p_value_over_best']:6.3f}"
        )

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
