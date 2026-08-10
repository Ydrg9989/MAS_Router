"""Recompute the headroom / accuracy / error-correlation relationships the report quotes.

`EXPERIMENT_LOG.md` and `DECISIONS.md` disagree on how many four-member subsets the original
correlations were computed over (70 against 35), so the figure is recomputed here on the full
n=366 banks rather than either document being trusted. This also re-reads the relationship with
`grok43` present, which is the correction D-025 records.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from mas_harness import config
from mas_harness.analysis.pool_select import load_banks

# D-022: models below the commit floor inflate headroom with missing data rather than with
# decorrelated errors, so they cannot appear in a subset whose headroom is being measured.
UNRELIABLE = {"gemini25flash", "gemini25flash-hi", "glm45air", "glm52", "minimax-m27",
              "kimi-k2-thinking", "nemotron3ultra"}

# `screen-strong` is deliberately excluded: it covers only 120 tasks and `load_banks` intersects
# task sets, so including it would silently shrink every pool to the screen and reproduce exactly
# the n=120 mistake D-025 records. `grok43` is still present because `strong4-a` banked it in full.
RUNS = ["hard366-a", "cand4-a", "strong4-a", "decorr4-a", "correlated4-a"]


def main() -> None:
    by_task, families = load_banks(RUNS, config.RUNS_DIR)
    print(f"tasks in the intersection: {len(by_task)}")

    full: dict[str, dict[str, bool]] = {}
    for task, per_agent in by_task.items():
        for agent, correct in per_agent.items():
            full.setdefault(agent, {})[task] = correct
    full = {
        a: v for a, v in full.items() if len(v) == len(by_task) and a not in UNRELIABLE
    }

    print(f"reliable agents banked on every task: {len(full)}")
    for a in sorted(full, key=lambda a: -float(np.mean(list(full[a].values())))):
        print(f"  {a:16s} n={len(full[a]):4d} acc={np.mean(list(full[a].values())):.4f} "
              f"family={families.get(a)}")

    names = sorted(full)
    tasks = sorted(by_task)
    correct = {a: np.array([full[a][t] for t in tasks], dtype=bool) for a in names}

    rows = []
    for subset in combinations(names, 4):
        matrix = np.stack([correct[a] for a in subset])
        ceiling = float(matrix.any(axis=0).mean())
        best = float(matrix.mean(axis=1).max())
        acc = float(matrix.mean())
        # Correlation between error indicators, the quantity D-023 is about.
        errors = (~matrix).astype(float)
        pairs = [
            float(np.corrcoef(errors[i], errors[j])[0, 1])
            for i in range(4)
            for j in range(i + 1, 4)
        ]
        rows.append(((ceiling - best) * 100, acc, float(np.mean(pairs)), subset))

    headroom = np.array([r[0] for r in rows])
    accuracy = np.array([r[1] for r in rows])
    correlation = np.array([r[2] for r in rows])

    def r(x: np.ndarray, y: np.ndarray) -> float:
        return float(np.corrcoef(x, y)[0, 1])

    print(f"\n{len(rows)} four-member subsets (C({len(names)},4))")
    print(f"  corr(headroom, mean error correlation) = {r(headroom, correlation):+.3f}")
    print(f"  corr(headroom, mean pool accuracy)     = {r(headroom, accuracy):+.3f}")
    print(f"  corr(accuracy, mean error correlation) = {r(accuracy, correlation):+.3f}")

    print("\n  top 8 subsets by headroom:")
    for h, a, c, s in sorted(rows, reverse=True)[:8]:
        print(f"    {h:6.2f}pp  acc={a:.3f} corr={c:+.3f}  {', '.join(s)}")


if __name__ == "__main__":
    main()
