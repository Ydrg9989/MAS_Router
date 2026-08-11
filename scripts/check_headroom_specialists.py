"""Can the no-interaction null be exceeded at all, by any pool we can assemble from real agents?

D-034 retired the oracle-headroom statistic because observed headroom never exceeded a null that
removes the organization-by-task interaction. A null that is only ever satisfied is worth little: it
could be measuring something no data can beat. The claim needs a case where it fires.

The cheapest candidate is already banked. `crosscap240` Stage A covers eight distinct agents on 240
tasks spanning four capabilities, and their rankings visibly reverse - grok43 is 0.97 on code
execution and 0.13 on theory of mind while deepseek32 is 0.85 and 0.80. That is agent-by-task
interaction in the raw data. D-034 measured headroom over *organizations*, where coalitions and
majority voting average four members together and could plausibly wash it out, so individual agents
are the sharper test.

Two things are checked here, and the difference between them is the point:

``real pools``
    The four members of each pool as shipped. This is also the precondition that D-021 and D-023
    used to decide which pools received priced episodes, computed over four agents rather than
    thirty organizations, and never tested against a null. TODO lists it as outstanding.
``a pool chosen to be maximally disjoint``
    The best agent on each capability, selected on calibration tasks and scored on test tasks. If
    the null cannot be beaten even by a pool assembled specifically to beat it, from agents already
    known to reverse rank, then the instrument is suspect. If it can, the null is sound and the
    finding becomes an existence condition rather than a blanket negative.

    python scripts/check_headroom_specialists.py
"""

from __future__ import annotations

import json
from collections import defaultdict

import numpy as np

from mas_harness import config
from mas_harness.metrics.routing import headroom_against_no_interaction
from mas_harness.records.schema import EpisodeRecord
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

RUNS = {
    "strong4": "crosscap-strong4",
    "decorrelated4": "crosscap-decorr4",
    "correlated4": "crosscap-corr4",
}
OUTPUT = config.RUNS_DIR / "headroom_null_specialists.json"


def load() -> tuple[dict[str, dict[str, bool]], dict[str, str], dict[str, list[str]]]:
    """agent name -> task -> correct, task -> domain, pool -> members.

    Agents are keyed by name rather than id because the pools overlap: `llama4scout` sits in two
    and `gpt5mini`, `deepseek32` and `gptoss120b` each sit in two, so the eight distinct agents are
    spread across twelve slots.
    """
    outcomes: dict[str, dict[str, bool]] = defaultdict(dict)
    domain: dict[str, str] = {}
    members: dict[str, list[str]] = {}
    for pool, run_id in RUNS.items():
        names: set[str] = set()
        for record in RunDirectory(config.RUNS_DIR, run_id).load_answers():
            outcomes[record.agent_name].setdefault(record.task_id, bool(record.correct))
            domain[record.task_id] = record.domain
            names.add(record.agent_name)
        members[pool] = sorted(names)

    shared = set.intersection(*[set(t) for t in outcomes.values()])
    return (
        {a: {t: v for t, v in o.items() if t in shared} for a, o in outcomes.items()},
        {t: d for t, d in domain.items() if t in shared},
        members,
    )


def accuracy_by_domain(
    outcomes: dict[str, dict[str, bool]], domain: dict[str, str], tasks: list[str]
) -> dict[str, dict[str, float]]:
    by_domain: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        by_domain[domain[task]].append(task)
    return {
        agent: {
            d: float(np.mean([outcomes[agent][t] for t in ts]))
            for d, ts in sorted(by_domain.items())
        }
        for agent in sorted(outcomes)
    }


def episodes_for(
    agents: list[str], outcomes: dict[str, dict[str, bool]], domain: dict[str, str]
) -> list[EpisodeRecord]:
    """One singleton organization per agent, so the null sees agents rather than coalitions."""
    return [
        EpisodeRecord(
            run_id="crosscap240",
            task_id=task,
            suite="crosscap240",
            domain=domain[task],
            pool_id="recombined",
            protocol_id=agent,
            coalition=[0],
            seed=0,
            final_text="",
            final_answer="",
            ground_truth="",
            correct=solved,
            parse_failed=False,
        )
        for agent in agents
        for task, solved in outcomes[agent].items()
    ]


def aggregation_versus_routing(
    domain: dict[str, str], calibration: list[str], test: list[str]
) -> dict[str, dict[str, float]]:
    """Does majority voting already collect what a perfect domain router would?

    The table above shows enormous per-capability spreads, so routing each domain to its best agent
    ought to beat the best single agent by a wide margin - and it does. The question that decides
    whether routing is worth building is a different one: whether it beats simply running everyone
    and voting, which requires no task representation, no calibration, and no router.

    The domain router here is deliberately generous. It is given the true capability label of every
    test task and picks that capability's best agent using calibration data, so it is an upper
    bound on what any learned router over individual agents could achieve.
    """
    results: dict[str, dict[str, float]] = {}
    for pool, run_id in RUNS.items():
        row = _one_pool(run_id, domain, calibration, test)
        if row:
            results[pool] = row
    return results


def _one_pool(
    run_id: str, domain: dict[str, str], calibration: list[str], test: list[str]
) -> dict[str, float] | None:
    directory = RunDirectory(config.RUNS_DIR, run_id)
    by_agent: dict[str, dict[str, bool]] = defaultdict(dict)
    agent_ids: dict[str, int] = {}
    for record in directory.load_answers():
        by_agent[record.agent_name][record.task_id] = bool(record.correct)
        agent_ids[record.agent_name] = record.agent_id
    agents = sorted(by_agent)
    whole_pool = tuple(sorted(agent_ids.values()))

    vote = {
        e.task_id: bool(e.correct)
        for e in directory.load_episodes()
        if e.intervention.kind == "none"
        and e.protocol_id == "independent_majority"
        and tuple(sorted(e.coalition)) == whole_pool
    }

    def usable(tasks: list[str]) -> list[str]:
        return [t for t in tasks if t in vote and all(t in by_agent[a] for a in agents)]

    def mean(agent: str, tasks: list[str]) -> float:
        return float(np.mean([by_agent[agent][t] for t in tasks]))

    train, held = usable(calibration), usable(test)
    if not train or not held:
        return None

    best_single = max(agents, key=lambda a: mean(a, train))
    by_domain: dict[str, list[str]] = defaultdict(list)
    for task in held:
        by_domain[domain[task]].append(task)

    routed: list[bool] = []
    for capability, tasks in by_domain.items():
        local = [t for t in train if domain[t] == capability]
        expert = max(agents, key=lambda a: mean(a, local)) if local else best_single
        routed.extend(by_agent[expert][t] for t in tasks)

    return {
        "n_test": len(held),
        "best_single_agent": mean(best_single, held),
        "domain_router_over_agents": float(np.mean(routed)),
        "whole_pool_majority_vote": float(np.mean([vote[t] for t in held])),
        "oracle_over_agents": float(np.mean([max(by_agent[a][t] for a in agents) for t in held])),
        "best_single_agent_name": best_single,
    }


def main() -> None:
    outcomes, domain, members = load()
    manifest = Manifest.read(config.DATA_DIR / "manifests" / "crosscap240.json")
    calibration = [t for t in manifest.splits["calibration"] if t in domain]
    test = [t for t in manifest.splits["test"] if t in domain]

    print(f"{len(outcomes)} distinct agents on {len(domain)} shared tasks")
    print(f"{len(calibration)} calibration / {len(test)} test\n")

    table = accuracy_by_domain(outcomes, domain, sorted(domain))
    domains = sorted(set(domain.values()))
    print(f"{'agent':16s}" + "".join(f"{d[:14]:>16s}" for d in domains) + f"{'spread':>9s}")
    for agent, row in sorted(table.items(), key=lambda kv: -np.mean(list(kv[1].values()))):
        spread = max(row.values()) - min(row.values())
        print(f"{agent:16s}" + "".join(f"{row[d]:16.3f}" for d in domains) + f"{spread:9.3f}")

    # Chosen on calibration tasks only; the pool is a decision like any other and selecting it on
    # the tasks it is then scored on is the leak that D-030 and D-033 were about.
    calibration_table = accuracy_by_domain(outcomes, domain, calibration)
    disjoint: list[str] = []
    for d in domains:
        ranked = sorted(calibration_table, key=lambda a: -calibration_table[a][d])
        pick = next((a for a in ranked if a not in disjoint), ranked[0])
        disjoint.append(pick)
    generalists = sorted(
        calibration_table,
        key=lambda a: -float(np.mean(list(calibration_table[a].values()))),
    )[:4]

    pools = {
        **members,
        "disjoint4 (best per capability)": disjoint,
        "generalist4 (best overall)": generalists,
        "all8": sorted(outcomes),
    }

    print(f"\n{'pool':34s} {'members':>7s} {'best':>7s} {'oracle':>7s} "
          f"{'headroom':>9s} {'null':>8s} {'excess':>8s} {'p':>7s}")
    report = {
        "accuracy_by_capability": {
            "n_tasks": len(domain),
            "capabilities": domains,
            "all_tasks": table,
            "calibration_tasks": calibration_table,
            "peak_capability": {a: max(row, key=row.get) for a, row in table.items()},
            "spread": {a: max(row.values()) - min(row.values()) for a, row in table.items()},
        }
    }
    for name, agents in pools.items():
        agents = list(dict.fromkeys(agents))
        result = headroom_against_no_interaction(
            episodes_for(agents, outcomes, domain),
            train_task_ids=calibration,
            test_task_ids=test,
            n_simulations=300,
        )
        best = max(float(np.mean([outcomes[a][t] for t in test])) for a in agents)
        oracle = float(np.mean([max(outcomes[a][t] for a in agents) for t in test]))
        result["members"] = agents
        result["best_single_agent"] = best
        result["oracle_any_agent"] = oracle
        report[name] = result
        print(
            f"{name:34s} {len(agents):7d} {best:7.3f} {oracle:7.3f} "
            f"{result['observed_headroom_over_best']:9.2f} "
            f"{result['null_headroom_over_best_mean']:8.2f} "
            f"{result['excess_over_null_over_best']:+8.2f} "
            f"{result['p_value_over_best']:7.3f}"
        )

    print(f"\ndisjoint4 = {', '.join(disjoint)}")

    versus = aggregation_versus_routing(domain, calibration, test)
    print(
        f"\n{'pool':16s} {'best single':>12s} {'domain router':>14s} "
        f"{'majority vote':>14s} {'oracle':>8s}  {'router - vote':>13s}"
    )
    for pool, row in versus.items():
        edge = 100 * (row["domain_router_over_agents"] - row["whole_pool_majority_vote"])
        print(
            f"{pool:16s} {row['best_single_agent']:12.3f} "
            f"{row['domain_router_over_agents']:14.3f} "
            f"{row['whole_pool_majority_vote']:14.3f} {row['oracle_over_agents']:8.3f}  "
            f"{edge:+12.1f} pp"
        )

    report["aggregation_versus_routing"] = versus
    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
