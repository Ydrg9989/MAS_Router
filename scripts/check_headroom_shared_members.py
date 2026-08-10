"""Re-run the headroom test against a null that keeps member sharing, and see if the verdict holds.

D-034 concluded that observed oracle headroom does not exceed a no-interaction null. `FRAMEWORK.md`
section 3.4 identifies a real weakness in that null: it draws organizations independently, but
organizations share members, so its oracle is too generous and the test under-rejects. That makes
the conclusion conservative rather than wrong - but a conservative test cannot support a strong
claim, and the SWE-bench matrix landing *below* its null is the symptom.

[`mas_harness/metrics/sharing_null.py`](../mas_harness/metrics/sharing_null.py) replaces it:
simulate agents under an additive agent-by-task model, then vote for real. This script runs both
nulls on the same six cells so the difference is visible, and reports the replay agreement that
certifies the fast equivalence-class voting reproduces the recorded episodes.

Two outcomes are informative. If the excess stays near zero under the sharp null, D-034 is confirmed
on a test that can actually fire, and the claim strengthens from "not evidence for interaction" to
something much closer to "no routable interaction at this scale". If the excess becomes significant,
D-034 was an artefact of the conservative null and must be revised.

    python scripts/check_headroom_shared_members.py
"""

from __future__ import annotations

import json

from mas_harness import config
from mas_harness.metrics.routing import headroom_against_no_interaction
from mas_harness.metrics.sharing_null import headroom_against_shared_member_null
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.adapters import build_evaluator
from mas_harness.tasks.manifest import Manifest

FREE_PROTOCOLS = ("independent_majority", "single_expert")

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

N_SIMULATIONS = 200
OUTPUT = config.RUNS_DIR / "headroom_null_shared_members.json"


def main() -> None:
    report: dict[str, dict] = {}
    for suite, spec in SUITES.items():
        manifest = Manifest.read(config.DATA_DIR / "manifests" / spec["manifest"])
        by_id = manifest.by_id()
        evaluators = {task_id: build_evaluator(s) for task_id, s in by_id.items()}
        calibration = manifest.splits["calibration"]
        test = manifest.splits["test"]
        report[suite] = {}
        print(f"\n=== {suite}  ({len(by_id)} tasks)")

        for pool, run_id in spec["runs"].items():
            directory = RunDirectory(config.RUNS_DIR, run_id)
            answers = [a for a in directory.load_answers() if a.task_id in evaluators]
            episodes = [
                e
                for e in directory.load_episodes()
                if e.intervention.kind == "none"
                and e.protocol_id in FREE_PROTOCOLS
                and e.task_id in evaluators
            ]

            sharp = headroom_against_shared_member_null(
                answers,
                episodes,
                evaluators=evaluators,
                train_task_ids=calibration,
                test_task_ids=test,
                protocols=FREE_PROTOCOLS,
                n_simulations=N_SIMULATIONS,
            )
            independent = headroom_against_no_interaction(
                episodes,
                train_task_ids=calibration,
                test_task_ids=test,
                only_protocols=FREE_PROTOCOLS,
                n_simulations=N_SIMULATIONS,
            )
            report[suite][pool] = {"shared_member_null": sharp, "independent_null": independent}

            print(f"\n  -- {pool}  ({run_id})")
            if "note" in sharp:
                print(f"     skipped: {sharp['note']}")
                continue
            print(
                f"     {sharp['n_agents']} agents, {sharp['n_organizations']} organizations, "
                f"{sharp['n_test_tasks']} test tasks"
            )
            print(
                "     replay agreement with recorded episodes: "
                f"{sharp['replay_agreement_with_recorded_episodes']:.4f}"
            )
            print(f"     {'null':22s} {'observed':>9s} {'null':>8s} {'excess':>8s} {'p':>7s}")
            for name, entry, obs, mean, exc, p in (
                (
                    "shared members (sharp)",
                    sharp,
                    "observed_headroom",
                    "null_headroom_mean",
                    "excess_over_null",
                    "p_value",
                ),
                (
                    "independent (old)",
                    independent,
                    "observed_headroom",
                    "null_headroom_mean",
                    "excess_over_null",
                    "p_value",
                ),
            ):
                if obs in entry:
                    print(
                        f"     {name:22s} {entry[obs]:9.2f} {entry[mean]:8.2f} "
                        f"{entry[exc]:+8.2f} {entry[p]:7.3f}"
                    )

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
