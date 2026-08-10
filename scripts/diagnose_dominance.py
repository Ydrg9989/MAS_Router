"""Is configuration dominance measuring task-dependence, or just protocol count?

`protocol_dominance` takes the argmax protocol in each of 12 domains and reports how often the same
one wins. The gate fails the delegation direction above 75%. Two things could make that number move
without any change in the science:

  1. **Protocol count.** More protocols means more competitors for each domain's argmax, so the
     winner's share falls mechanically. If that is the dominant effect, "widen the protocol family"
     passes the criterion by dilution rather than by discovering task-dependence.
  2. **Argmax noise.** Domains hold about 30 tasks, so per-domain accuracies are noisy and the
     argmax is partly random even when protocols are identical.

This measures both: the observed dominance, a permutation null in which protocol labels are shuffled
within each task (destroying real protocol differences while preserving task difficulty and the
domain structure), and the trend across random sub-families of size k.

Run before adding protocols, so the metric's behaviour is known in advance rather than rationalised
after the number moves.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import numpy as np

from mas_harness import config
from mas_harness.metrics.governance import protocol_dominance
from mas_harness.records.writer import RunDirectory

RUNS = ["strong4-a", "decorr4-a", "correlated4-a"]
SEED = 20260810
N_PERMUTATIONS = 2000


def load(run: str, grand_only: bool) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    """protocol -> task -> correct, and task -> domain, on the tasks every protocol ran.

    `grand_only` reproduces the difference between this diagnosis and the gate's own reading: the
    gate's `protocol_dominance` filters interventions but not coalition size, so a protocol's
    accuracy in a domain is pooled over all 15 coalitions of every size.
    """
    by_protocol: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    domain: dict[str, str] = {}
    for e in RunDirectory(config.RUNS_DIR, run).load_episodes():
        if e.intervention.kind != "none":
            continue
        if grand_only and len(e.coalition) != 4:
            continue
        by_protocol[e.protocol_id][e.task_id].append(bool(e.correct))
        domain[e.task_id] = e.domain
    shared = set.intersection(*[set(v) for v in by_protocol.values()])
    # Collapse repeated coalitions on a task to that task's mean, so a task counts once.
    return (
        {p: {t: bool(np.mean(v[t]) >= 0.5) for t in shared} for p, v in by_protocol.items()},
        {t: domain[t] for t in shared},
    )


def dominance(outcomes: dict[str, dict[str, bool]], domain: dict[str, str]) -> float:
    """Fraction of domains won by the single most frequent winner."""
    per_domain: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for protocol, tasks in outcomes.items():
        for task, correct in tasks.items():
            per_domain[domain[task]][protocol].append(correct)

    wins: dict[str, int] = defaultdict(int)
    for protocols in per_domain.values():
        means = {p: float(np.mean(v)) for p, v in protocols.items()}
        wins[max(means, key=lambda p: means[p])] += 1
    return max(wins.values()) / len(per_domain)


def permuted(outcomes, domain, rng):
    """Shuffle protocol labels within each task.

    Preserves how many protocols got the task right, so task difficulty and domain structure are
    untouched; destroys any systematic difference between protocols. Dominance measured here is the
    floor the metric reads when there is nothing to find.
    """
    protocols = sorted(outcomes)
    shuffled: dict[str, dict[str, bool]] = {p: {} for p in protocols}
    for task in domain:
        column = [outcomes[p][task] for p in protocols]
        rng.shuffle(column)
        for p, value in zip(protocols, column, strict=True):
            shuffled[p][task] = value
    return shuffled


def gate_reading(run: str) -> dict[str, object]:
    """Exactly what the gate computes, for comparison."""
    episodes = list(RunDirectory(config.RUNS_DIR, run).load_episodes())
    return protocol_dominance(episodes)


def main() -> None:
    rng = np.random.default_rng(SEED)
    print("=== the gate's own reading, for reference ===")
    for run in RUNS:
        g = gate_reading(run)
        print(f"  {run:15s} {g['dominance_fraction']*100:5.1f}%  "
              f"dominant={g['dominant_protocol']}  n_domains={g['n_domains']}")

    for run in RUNS:
        outcomes, domain = load(run, grand_only=True)
        protocols = sorted(outcomes)
        observed = dominance(outcomes, domain)

        null = np.array([
            dominance(permuted(outcomes, domain, rng), domain) for _ in range(N_PERMUTATIONS)
        ])
        p_value = float((null >= observed).mean())

        print(f"\n=== {run} ===")
        print(f"  {len(protocols)} protocols, {len(domain)} tasks, "
              f"{len(set(domain.values()))} domains")
        print(f"  observed dominance      {observed*100:5.1f}%   (gate fails above 75%)")
        print(f"  permutation null        {null.mean()*100:5.1f}% mean, "
              f"{np.percentile(null, 95)*100:.1f}% at the 95th pct")
        print(f"  P(null >= observed)     {p_value:.4f}  "
              f"{'-> indistinguishable from noise' if p_value > 0.05 else '-> real dominance'}")

        print("  dominance by family size, averaged over random sub-families:")
        for k in range(2, len(protocols) + 1):
            subsets = list(combinations(protocols, k))
            if len(subsets) > 40:
                idx = rng.choice(len(subsets), 40, replace=False)
                subsets = [subsets[i] for i in idx]
            values = [dominance({p: outcomes[p] for p in s}, domain) for s in subsets]
            print(f"    k={k}: {np.mean(values)*100:5.1f}%  "
                  f"(min {min(values)*100:.1f}, max {max(values)*100:.1f}, n={len(subsets)})")


if __name__ == "__main__":
    main()
