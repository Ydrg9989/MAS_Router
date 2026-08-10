"""Audit delegation's second criterion and the routing evidence behind it.

Two checks, both free, both missing from the gate.

**1. The similarity criterion has no noise control.** The gate passes delegation when semantic and
organizational task-similarity correlate below 0.5 with at least 20% differing nearest neighbours,
reading that as the organizational space capturing something semantics does not. But an
organizational space built from pure noise is *also* uncorrelated with semantics and *also* has
different neighbours - more so, not less. So the criterion is maximally satisfied by having no
structure at all. Here the organizational space is rebuilt from outcomes whose configuration labels
have been shuffled within each task, which destroys any real differential fit while preserving task
difficulty, and the criterion is re-read on it.

**2. The routing evidence leaks the answer.** `nearest_neighbour_routing_regret` places a test task
in the space, finds its nearest *training* task, and adopts that task's best configuration. For the
semantic space that is legitimate: a prompt embedding exists before anything is run. For the
organizational and capability spaces the test task's coordinates *are* its own outcomes, so the
neighbour is a task solved by the same configurations, and the configuration adopted is one that
solved the test task. Reported regret near zero is the signature, not a success.

The honest router is the semantic one, and its numbers are already in the gate's evidence.
"""

from __future__ import annotations

import numpy as np

from mas_harness import config
from mas_harness.metrics import delegation
from mas_harness.metrics.utility import configuration_stats
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

RUNS = ["strong4-a", "decorr4-a", "correlated4-a"]
MANIFEST = "data/manifests/hard366.json"
N_PERMUTATIONS = 25
SEED = 20260810


def permute_outcomes(episodes, rng):
    """Shuffle configuration labels within each task.

    Operates on copies so the caller's episodes are untouched. Preserves how many configurations
    solved each task; destroys which ones.
    """
    by_task: dict[str, list] = {}
    for e in episodes:
        by_task.setdefault(e.task_id, []).append(e)

    out = []
    for group in by_task.values():
        flags = [bool(e.correct) for e in group]
        rng.shuffle(flags)
        for e, flag in zip(group, flags, strict=True):
            clone = e.model_copy(deep=False)
            clone.correct = flag
            out.append(clone)
    return out


def main() -> None:
    manifest = Manifest.read(MANIFEST)
    by_id = manifest.by_id()
    rng = np.random.default_rng(SEED)

    for run in RUNS:
        rd = RunDirectory(config.RUNS_DIR, run)
        episodes = [e for e in rd.load_episodes() if e.intervention.kind == "none"]
        task_ids = sorted({e.task_id for e in episodes} & set(by_id))
        semantic = delegation.semantic_space(task_ids, [by_id[t].prompt for t in task_ids])

        real = delegation.compare_spaces(
            semantic, delegation.organizational_space(episodes), k=1
        )
        null_rho, null_diff = [], []
        for _ in range(N_PERMUTATIONS):
            shuffled = delegation.organizational_space(permute_outcomes(episodes, rng))
            comparison = delegation.compare_spaces(semantic, shuffled, k=1)
            null_rho.append(comparison["spearman_similarity_correlation"])
            null_diff.append(comparison["frac_differing_nearest_neighbours"])

        print(f"\n=== {run} ===")
        print(f"  semantic space: {semantic.method}")
        print("  criterion: Spearman < 0.5 AND >= 20% differing nearest neighbours")
        print(f"    observed   rho={real['spearman_similarity_correlation']:+.4f}  "
              f"differing={real['frac_differing_nearest_neighbours']*100:5.1f}%  -> PASS")
        print(f"    label-noise rho={np.mean(null_rho):+.4f}  "
              f"differing={np.mean(null_diff)*100:5.1f}%  -> "
              f"{'PASS' if np.mean(null_rho) < 0.5 and np.mean(null_diff) >= 0.2 else 'FAIL'}")
        print("    => the criterion cannot separate real structure from no structure"
              if np.mean(null_rho) < 0.5 and np.mean(null_diff) >= 0.2
              else "    => the criterion does discriminate")

        stats = configuration_stats(episodes)
        calibration = [t for t in manifest.splits.get("calibration", []) if t in set(task_ids)]
        test = [t for t in manifest.splits.get("test", []) if t in set(task_ids)]
        print("  routing regret (lower is better; 0 is an oracle):")
        for space in (
            semantic,
            delegation.capability_space(rd.load_answers()),
            delegation.organizational_space(episodes),
        ):
            r = delegation.nearest_neighbour_routing_regret(
                space, stats, train_task_ids=calibration, test_task_ids=test
            )
            leaks = space.name in ("organizational", "capability")
            print(f"    {space.name:15s} routed={r['routed_mean_regret']:.4f}  "
                  f"fixed_best={r['fixed_best_mean_regret']:.4f}  "
                  f"gain={r['regret_improvement_over_fixed_best']:+.4f}  "
                  f"{'LEAKS: coordinates are the test task own outcomes' if leaks else 'honest'}")


if __name__ == "__main__":
    main()
