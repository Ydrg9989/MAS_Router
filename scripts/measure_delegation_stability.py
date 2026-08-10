"""Re-read the delegation criterion with a metric that can fail.

`protocol_dominance` gave delegation its GO, and `scripts/diagnose_dominance.py` showed that it
passes at roughly the rate pure noise passes it. This reruns the three pools under
`metrics.stability.winner_stability`, which additionally requires each group's winning
configuration to *reproduce* across a split of that group's tasks.

Reported at two granularities and two definitions of a configuration, because the criterion's
answer may depend on both and that dependence is itself worth knowing:

  * grouping `domain` (12 groups, thin) against `suite` (3 groups, thicker);
  * protocol-only configurations against protocol-and-coalition, which is what a router picks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mas_harness import config
from mas_harness.metrics.stability import winner_stability
from mas_harness.records.writer import RunDirectory

RUNS = ["strong4-a", "decorr4-a", "correlated4-a"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", default=RUNS)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    summary: dict[str, dict] = {}
    for run in args.runs:
        episodes = list(RunDirectory(config.RUNS_DIR, run).load_episodes())
        print(f"\n{'=' * 74}\n{run}\n{'=' * 74}")
        summary[run] = {}

        for grouping in ("domain", "suite"):
            for by_configuration in (False, True):
                label = f"{grouping} x {'config' if by_configuration else 'protocol'}"
                report = winner_stability(
                    episodes,
                    grouping=grouping,
                    by_configuration=by_configuration,
                    n_splits=300,
                    n_permutations=300,
                )
                summary[run][label] = report.to_dict()

                n_config = report.groups[0].n_configurations if report.groups else 0
                print(f"\n  --- {label} ---")
                print(f"    groups {len(report.groups):2d} usable, "
                      f"{len(report.excluded_groups)} below the {4}-task floor; "
                      f"{n_config} configurations")
                print(f"    reproducibility {report.reproducibility:.3f}  "
                      f"null {report.null_reproducibility:.3f}  "
                      f"p={report.reproducibility_p:.4f}")
                print(f"    dominance       {report.dominance*100:5.1f}%  "
                      f"null {report.null_dominance*100:5.1f}%  "
                      f"p={report.dominance_p:.4f}")
                print(f"    {report.verdict}")

        # The decisive reading. The paid protocols only ran on the discriminating subset, so every
        # analysis above is confined to it. The two free protocols ran on all 366 tasks across all
        # 15 coalitions, which is both better powered and the axis a router mostly controls: which
        # agents participate, rather than which rule combines them.
        for grouping in ("domain", "suite"):
            label = f"{grouping} x coalition (free protocols, all tasks)"
            report = winner_stability(
                episodes,
                grouping=grouping,
                by_configuration=True,
                only_protocols=["single_expert", "independent_majority"],
                n_splits=300,
                n_permutations=300,
            )
            summary[run][label] = report.to_dict()
            n_tasks = sum(g.n_tasks for g in report.groups)
            n_config = report.groups[0].n_configurations if report.groups else 0
            print(f"\n  --- {label} ---")
            print(f"    groups {len(report.groups):2d}, {n_tasks} tasks, "
                  f"{n_config} configurations")
            print(f"    reproducibility {report.reproducibility:.3f}  "
                  f"null {report.null_reproducibility:.3f}  "
                  f"p={report.reproducibility_p:.4f}")
            print(f"    dominance       {report.dominance*100:5.1f}%  "
                  f"null {report.null_dominance*100:5.1f}%  "
                  f"p={report.dominance_p:.4f}")
            print(f"    dominant config {report.dominant_configuration}")
            print(f"    reproducibility on it   {report.reproducibility_dominant:.3f}  "
                  f"({len(report.groups) - report.n_off_dominant} groups)")
            print(f"    reproducibility off it  {report.reproducibility_off_dominant:.3f}  "
                  f"({report.n_off_dominant} groups)  <- the routing signal")
            print(f"    {report.verdict}")

    out = Path(args.out or Path(config.RUNS_DIR) / "delegation_stability.json")
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
