"""Test the D-026 pre-registration: the veto's sign follows error decorrelation.

Reads the priced episodes from all three pools and reports the veto effect against each pool's
measured error correlation. The prediction, recorded before `decorr4-a` was priced, is that the
effect is strictly positive on `decorrelated4` (+0.382 correlation).

Accuracies are computed only on the tasks a pool's seven protocols all ran, because the paid
protocols were restricted to the discriminating subset while the free ones cover all 366; mixing the
two denominators is what makes the runner's own summary non-comparable across protocols.
"""

from __future__ import annotations

import numpy as np

from mas_harness import config
from mas_harness.metrics.stats import mcnemar
from mas_harness.records.writer import RunDirectory

PRICED = [
    "independent_judge",
    "expert_verifier",
    "debate_vote",
    "expert_veto",
    "chair_information_seeking",
]
BASE = "single_expert"
CORRELATION = {"decorr4-a": 0.382, "strong4-a": 0.408, "correlated4-a": 0.579}


def load(run: str) -> dict[str, dict[str, bool]]:
    by: dict[str, dict[str, bool]] = {}
    for e in RunDirectory(config.RUNS_DIR, run).load_episodes():
        if e.intervention.kind == "none" and len(e.coalition) == 4:
            by.setdefault(e.protocol_id, {})[e.task_id] = bool(e.correct)
    return by


def vectors(by, tasks, protocol):
    return np.array([by[protocol][t] for t in tasks], dtype=float)


def main() -> None:
    out = {r: load(r) for r in CORRELATION}
    shared = {
        r: sorted(set.intersection(*[set(by[p]) for p in [*PRICED, BASE]]))
        for r, by in out.items()
    }

    tasks = shared["decorr4-a"]
    veto = vectors(out["decorr4-a"], tasks, "expert_veto")
    base = vectors(out["decorr4-a"], tasks, BASE)
    effect = (veto.mean() - base.mean()) * 100
    result = mcnemar(veto.astype(bool).tolist(), base.astype(bool).tolist())

    print("=== D-026: decorr4-a, expert_veto minus single_expert, predicted positive ===")
    print(
        f"  n={len(tasks)}  effect {effect:+.2f}pp  "
        f"discordant {int((veto != base).sum())}  p={result.p_value:.4f}"
    )
    print(f"  PREDICTION strictly positive -> {'CONFIRMED' if effect > 0 else 'FALSIFIED'}")

    print("\n=== every protocol on decorr4-a's shared tasks ===")
    acc = {
        p: float(vectors(out["decorr4-a"], tasks, p).mean())
        for p in [*PRICED, BASE, "independent_majority"]
    }
    for p in sorted(acc, key=lambda k: -acc[k]):
        print(f"    {acc[p]:.4f}  {p:28s} {(acc[p] - acc[BASE]) * 100:+6.2f}pp vs expert")
    spread = (max(acc.values()) - min(acc.values())) * 100
    print(f"  spread {spread:.2f}pp — {'PASS' if spread >= 8 else 'FAIL'} at the 8pp gate")

    print("\n=== veto effect against error correlation, three pools ===")
    for run in sorted(CORRELATION, key=lambda r: CORRELATION[r]):
        ts = shared[run]
        effect_run = (
            vectors(out[run], ts, "expert_veto").mean() - vectors(out[run], ts, BASE).mean()
        ) * 100
        print(
            f"  corr +{CORRELATION[run]:.3f}  {run:15s} n={len(ts):3d}  "
            f"veto {effect_run:+6.2f}pp"
        )


if __name__ == "__main__":
    main()
