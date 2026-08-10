"""Count aggregator non-termination exactly, per pool and per protocol.

D-028 records "25 of 366 tasks", which cannot be a per-protocol rate: the aggregator only ran on
each pool's discriminating subset, not on all 366. This establishes what the figure actually is
before the report quotes it.
"""

from __future__ import annotations

from collections import defaultdict

from mas_harness import config
from mas_harness.records.writer import RunDirectory

RUNS = ["strong4-a", "decorr4-a", "correlated4-a"]
AGGREGATOR_DECIDED = ("independent_judge", "chair_information_seeking")


def main() -> None:
    union: set[tuple[str, str]] = set()
    suites: dict[str, int] = defaultdict(int)

    for run in RUNS:
        ran: dict[str, set[str]] = defaultdict(set)
        dead: dict[str, set[str]] = defaultdict(set)
        for e in RunDirectory(config.RUNS_DIR, run).load_episodes():
            if e.intervention.kind != "none" or len(e.coalition) != 4:
                continue
            if e.protocol_id not in AGGREGATOR_DECIDED:
                continue
            ran[e.protocol_id].add(e.task_id)
            if not e.final_answer and any(c.finish_reason == "length" for c in e.calls):
                dead[e.protocol_id].add(e.task_id)
                union.add((run, e.task_id))
                suites[e.task_id.split("::")[0]] += 1

        print(f"\n{run}")
        for protocol in AGGREGATOR_DECIDED:
            n, d = len(ran[protocol]), len(dead[protocol])
            print(f"  {protocol:28s} {d:3d} of {n:3d} episodes  ({d/max(n,1)*100:.1f}%)")
        affected = dead[AGGREGATOR_DECIDED[0]] | dead[AGGREGATOR_DECIDED[1]]
        scope = ran[AGGREGATOR_DECIDED[0]] | ran[AGGREGATOR_DECIDED[1]]
        print(f"  {'distinct tasks affected':28s} {len(affected):3d} of {len(scope):3d} in scope")

    print(f"\ndistinct (pool, task) pairs affected across all three pools: {len(union)}")
    print(f"distinct tasks affected in at least one pool: {len({t for _, t in union})}")
    print(f"by suite (episode counts): {dict(suites)}")


if __name__ == "__main__":
    main()
