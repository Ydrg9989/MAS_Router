"""Score S1-S4: is `independent_judge` aggregating, or is it just a better model?

D-044 showed the judge solves 18.6% of tasks on which every member was wrong, which no selection
rule can do. That makes the obvious alternative explanation — the aggregator model is simply
stronger than the pool — the thing that has to be ruled out, and it never has been, because D-024
deliberately kept that model out of the pools.

This scores the control against the frozen thresholds and decomposes the judge's advantage into
consensus deference, independent answering, and selection among members.

    python scripts/measure_aggregator_solo.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import numpy as np

from mas_harness import config
from mas_harness.records.writer import RunDirectory

JUDGE = "independent_judge"
VOTE = "independent_majority"
SOLO_RUN = "aggregator-solo"
EFFECT_PP = 2.0

SUITES = {
    "crosscap240": {
        "strong4": "crosscap-strong4",
        "decorrelated4": "crosscap-decorr4",
        "correlated4": "crosscap-corr4",
    },
    "hard366": {
        "strong4": "strong4-a",
        "decorrelated4": "decorr4-a",
        "correlated4": "correlated4-a",
    },
}
OUTPUT = config.RUNS_DIR / "aggregator_solo.json"


def solo_outcomes() -> tuple[dict[str, float], dict[str, bool]]:
    """The control model's banked answers, plus which of them failed to terminate."""
    correct: dict[str, float] = {}
    finished: dict[str, bool] = {}
    for record in RunDirectory(config.RUNS_DIR, SOLO_RUN).load_answers():
        correct[record.task_id] = float(record.correct)
        finished[record.task_id] = not record.parse_failed
    return correct, finished


def cell(run_id: str) -> dict[str, Any]:
    directory = RunDirectory(config.RUNS_DIR, run_id)
    classes = {
        t["task_id"]: t["task_class"]
        for t in json.loads((config.RUNS_DIR / run_id / "discrimination.json").read_text())["tasks"]
    }
    members: dict[str, dict[int, float]] = defaultdict(dict)
    for record in directory.load_answers():
        members[record.task_id][record.agent_id] = float(record.correct)

    outcome: dict[str, dict[str, float]] = defaultdict(dict)
    episodes = [e for e in directory.load_episodes() if e.intervention.kind == "none"]
    grand = max(len(e.coalition) for e in episodes)
    for episode in episodes:
        if len(episode.coalition) == grand:
            outcome[episode.protocol_id][episode.task_id] = float(episode.correct)
    return {"classes": classes, "outcome": outcome, "members": members}


def main() -> None:
    solo, finished = solo_outcomes()
    report: dict[str, Any] = {
        "generated_by": "scripts/measure_aggregator_solo.py",
        "preregistration": "Docs/preregistrations/2026-08-14-aggregator-solo.md",
        "n_solo_tasks": len(solo),
        "solo_commit_rate": float(np.mean(list(finished.values()))),
        "suites": {},
    }

    print("=== S1: the judge against the model that IS the judge, on paired tasks")
    print(f"{'suite / pool':28s} {'n':>4s} {'vote':>7s} {'solo':>7s} {'judge':>7s} "
          f"{'judge−solo':>11s} {'solo−vote':>10s}")
    for suite, runs in SUITES.items():
        report["suites"][suite] = {}
        for pool, run_id in runs.items():
            data = cell(run_id)
            judge, vote = data["outcome"][JUDGE], data["outcome"][VOTE]
            shared = sorted(set(judge) & set(vote) & set(solo))
            if not shared:
                continue
            j = float(np.mean([judge[t] for t in shared]))
            v = float(np.mean([vote[t] for t in shared]))
            s = float(np.mean([solo[t] for t in shared]))
            best_member = max(
                float(np.mean([data["members"][t].get(a, 0.0) for t in shared]))
                for a in sorted({a for t in shared for a in data["members"][t]})
            )

            by_class: dict[str, Any] = {}
            for name in ("UNANIMOUS_CORRECT", "UNANIMOUS_WRONG", "DISCRIMINATING"):
                if name == "DISCRIMINATING":
                    tasks = [t for t in shared if not data["classes"].get(t, "").startswith("UNAN")]
                else:
                    tasks = [t for t in shared if data["classes"].get(t) == name]
                if not tasks:
                    continue
                by_class[name] = {
                    "n": len(tasks),
                    "share": len(tasks) / len(shared),
                    "vote": float(np.mean([vote[t] for t in tasks])),
                    "solo": float(np.mean([solo[t] for t in tasks])),
                    "judge": float(np.mean([judge[t] for t in tasks])),
                }

            report["suites"][suite][pool] = {
                "n_tasks": len(shared), "vote": v, "solo": s, "judge": j,
                "best_single_member": best_member,
                "judge_minus_solo_pp": 100.0 * (j - s),
                "solo_minus_vote_pp": 100.0 * (s - v),
                "solo_minus_best_member_pp": 100.0 * (s - best_member),
                "by_class": by_class,
            }
            print(f"{suite + ' / ' + pool:28s} {len(shared):4d} {v:7.3f} {s:7.3f} {j:7.3f} "
                  f"{100 * (j - s):+11.2f} {100 * (s - v):+10.2f}")

    print("\n=== S2/S3: the decomposition, by what the members did")
    print(f"{'suite / pool':28s} {'class':20s} {'n':>4s} {'share':>6s} "
          f"{'vote':>7s} {'solo':>7s} {'judge':>7s}")
    for suite, pools in report["suites"].items():
        for pool, entry in pools.items():
            for name, c in entry["by_class"].items():
                print(f"{suite + ' / ' + pool:28s} {name:20s} {c['n']:4d} {c['share']:6.0%} "
                      f"{c['vote']:7.3f} {c['solo']:7.3f} {c['judge']:7.3f}")

    flat = [e for pools in report["suites"].values() for e in pools.values()]
    deltas = [e["judge_minus_solo_pp"] for e in flat]

    def pooled(name: str, field: str) -> float:
        num = sum(e["by_class"][name][field] * e["by_class"][name]["n"]
                  for e in flat if name in e["by_class"])
        den = sum(e["by_class"][name]["n"] for e in flat if name in e["by_class"])
        return num / den if den else float("nan")

    decision = {
        "S1_judge_minus_solo_pp": deltas,
        "S1_mean_pp": float(np.mean(deltas)),
        "S1_n_pools_clearing_2pp": int(sum(d >= EFFECT_PP for d in deltas)),
        "S1_result_survives": bool(all(d >= EFFECT_PP for d in deltas)),
        "S2_solo_on_unanimous_wrong": pooled("UNANIMOUS_WRONG", "solo"),
        "S2_judge_on_unanimous_wrong": pooled("UNANIMOUS_WRONG", "judge"),
        "S3_solo_on_unanimous_correct": pooled("UNANIMOUS_CORRECT", "solo"),
        "S3_consensus_deference_is_worth_something": bool(
            pooled("UNANIMOUS_CORRECT", "solo") < 0.995
        ),
        "S4_solo_minus_best_member_pp": [e["solo_minus_best_member_pp"] for e in flat],
        "solo_commit_rate": report["solo_commit_rate"],
    }
    decision["verdict"] = (
        "JUDGE ADDS SOMETHING" if decision["S1_result_survives"]
        else "THE JUDGE IS LARGELY THE MODEL"
    )
    report["decision"] = decision
    OUTPUT.write_text(json.dumps(report, indent=1))

    print("\n=== the pre-registered outcomes")
    print(f"    S1 judge − solo: {[f'{d:+.2f}' for d in deltas]}  "
          f"mean {decision['S1_mean_pp']:+.2f} pp, {decision['S1_n_pools_clearing_2pp']}/6 clear +2.0")
    print(f"    S2 on unanimous-WRONG   solo {decision['S2_solo_on_unanimous_wrong']:.3f} "
          f"vs judge {decision['S2_judge_on_unanimous_wrong']:.3f}")
    print(f"    S3 on unanimous-CORRECT solo {decision['S3_solo_on_unanimous_correct']:.3f} "
          f"(consensus deference worth something: {decision['S3_consensus_deference_is_worth_something']})")
    print(f"    S4 solo − best member: {[f'{d:+.1f}' for d in decision['S4_solo_minus_best_member_pp']]}")
    print(f"    solo commit rate {decision['solo_commit_rate']:.3f}")
    print(f"\n    VERDICT: {decision['verdict']}")
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
