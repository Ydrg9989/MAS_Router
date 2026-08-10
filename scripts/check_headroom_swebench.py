"""Does the oracle-headroom illusion hold outside this project's own data?

D-034 showed that the per-task maximum over thirty organizations sits at or below a no-interaction
null on every pool and suite here, so the routing prize this project chased never existed. That
matters far beyond this project only if the same statistic is what other people are quoting, on
other systems, at other scales.

SWE-bench Verified is the test. `agent-psychometrics` ships 134 independently built agent systems -
different scaffolds, base models, labs and years - by 500 instances, binary. A gap between the best
single system and "at least one system solves it" is exactly the number used to motivate routing,
ensembling and agent selection, and at 134 systems it is enormous. This script asks how much of it
survives removing the system-by-instance interaction.

    python scripts/check_headroom_swebench.py
"""

from __future__ import annotations

import json

import numpy as np

# Running this file puts `scripts/` on the path, so the pre-test's loader is importable directly
# and the two analyses cannot drift apart in how they read the matrix.
from pretest_specialist_routing import load

from mas_harness import config
from mas_harness.metrics.routing import headroom_against_no_interaction

TOP_K = [4, 8, 16, 32, None]
OUTPUT = config.RUNS_DIR / "headroom_null_swebench.json"


def main() -> None:
    from mas_harness.records.schema import EpisodeRecord

    outcomes, repo = load()
    accuracy = {s: float(np.mean(list(o.values()))) for s, o in outcomes.items()}
    ranked = sorted(accuracy, key=lambda s: -accuracy[s])
    tasks = sorted(repo)
    rng = np.random.default_rng(20260810)
    order = rng.permutation(len(tasks))
    train = [tasks[i] for i in order[: len(tasks) // 2]]
    test = [tasks[i] for i in order[len(tasks) // 2 :]]

    print(
        f"{len(outcomes)} systems x {len(tasks)} instances, "
        f"best {accuracy[ranked[0]]:.3f}, median {np.median(list(accuracy.values())):.3f}"
    )
    print(
        f"\n{'systems':>8s} {'best':>7s} {'oracle':>7s} {'headroom':>9s} "
        f"{'null':>8s} {'excess':>8s} {'p':>7s}"
    )

    report = {}
    for k in TOP_K:
        subjects = ranked[:k] if k else ranked
        episodes = [
            EpisodeRecord(
                run_id="swebench_verified",
                task_id=task,
                suite="swebench_verified",
                domain=repo[task],
                pool_id="agent-psychometrics",
                # Each system is its own organization, as in the specialist pre-test.
                protocol_id=subject,
                coalition=[0],
                seed=0,
                final_text="",
                final_answer="",
                ground_truth="",
                correct=solved,
                parse_failed=False,
            )
            for subject in subjects
            for task, solved in outcomes[subject].items()
        ]
        result = headroom_against_no_interaction(
            episodes, train_task_ids=train, test_task_ids=test, n_simulations=200
        )
        best = max(np.mean([outcomes[s][t] for t in test]) for s in subjects)
        oracle = float(
            np.mean([max(outcomes[s][t] for s in subjects) for t in test])
        )
        result["best_single_system"] = float(best)
        result["oracle_any_system"] = oracle
        report[str(k or "all")] = result
        print(
            f"{len(subjects):8d} {best:7.3f} {oracle:7.3f} "
            f"{result['observed_headroom_over_best']:9.2f} "
            f"{result['null_headroom_over_best_mean']:8.2f} "
            f"{result['excess_over_null_over_best']:+8.2f} "
            f"{result['p_value_over_best']:7.3f}"
        )

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
