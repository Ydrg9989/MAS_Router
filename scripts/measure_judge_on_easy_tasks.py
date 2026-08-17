"""Score H1-H4 of the 2026-08-14 pre-registration: what the judge does where members already agree.

D-020 never priced the tasks on which all four members gave the same answer, on the reasoning that
no protocol could differ there. That is true of a *vote*, which returns the members' answer by
definition. It is not true of a *judge*, which reads four answers and writes its own.

    python scripts/measure_judge_on_easy_tasks.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import numpy as np

from mas_harness import config
from mas_harness.clients.pricing import PricingTable, step_cost_usd
from mas_harness.records.writer import RunDirectory

JUDGE = "independent_judge"
VOTE = "independent_majority"
RUNS = {
    "strong4": "crosscap-strong4",
    "decorrelated4": "crosscap-decorr4",
    "correlated4": "crosscap-corr4",
}
OUTPUT = config.RUNS_DIR / "judge_on_easy_tasks.json"


def load(run_id: str) -> dict[str, Any]:
    directory = RunDirectory(config.RUNS_DIR, run_id)
    prices = PricingTable.read(config.RUNS_DIR / run_id / "pricing_snapshot.json")
    per_answer = {
        (r.agent_id, r.task_id): step_cost_usd(r.call.usage, prices.get(r.model))
        for r in directory.load_answers()
    }
    classes = {
        t["task_id"]: t["task_class"]
        for t in json.loads((config.RUNS_DIR / run_id / "discrimination.json").read_text())["tasks"]
    }

    outcome: dict[str, dict[str, float]] = defaultdict(dict)
    cost: dict[str, dict[str, float]] = defaultdict(dict)
    truncated: dict[str, set[str]] = defaultdict(set)
    episodes = [e for e in directory.load_episodes() if e.intervention.kind == "none"]
    grand = max(len(e.coalition) for e in episodes)
    for episode in episodes:
        if len(episode.coalition) != grand:
            continue
        outcome[episode.protocol_id][episode.task_id] = float(episode.correct)
        cost[episode.protocol_id][episode.task_id] = sum(
            per_answer.get((a, episode.task_id), 0.0) for a in episode.coalition
        ) + sum(step_cost_usd(c.usage, prices.get(c.model)) for c in episode.calls)
        if any(c.finish_reason not in ("stop", None, "") for c in episode.calls):
            truncated[episode.protocol_id].add(episode.task_id)
    return {"outcome": outcome, "cost": cost, "classes": classes, "truncated": truncated}


def main() -> None:
    report: dict[str, Any] = {
        "generated_by": "scripts/measure_judge_on_easy_tasks.py",
        "preregistration": "Docs/preregistrations/2026-08-14-judge-on-easy-tasks.md",
        "pools": {},
    }
    print("=== H1/H2: the judge on tasks where every member gave the same answer")
    print(f"{'pool':16s} {'class':20s} {'n':>4s} {'vote':>7s} {'judge':>7s} {'delta pp':>9s}")
    for pool, run_id in RUNS.items():
        cell = load(run_id)
        judge, vote, classes = cell["outcome"][JUDGE], cell["outcome"][VOTE], cell["classes"]
        entry: dict[str, Any] = {"run_id": run_id, "by_class": {}}
        for name in ("UNANIMOUS_CORRECT", "UNANIMOUS_WRONG"):
            tasks = sorted(t for t in judge if classes.get(t) == name and t in vote)
            if not tasks:
                continue
            j = float(np.mean([judge[t] for t in tasks]))
            v = float(np.mean([vote[t] for t in tasks]))
            entry["by_class"][name] = {
                "n": len(tasks), "judge": j, "vote": v, "delta_pp": 100.0 * (j - v),
                "n_judge_overrides_a_correct_consensus": int(
                    sum(1 for t in tasks if vote[t] == 1.0 and judge[t] == 0.0)
                ),
                "n_judge_rescues": int(sum(1 for t in tasks if vote[t] == 0.0 and judge[t] == 1.0)),
            }
            print(f"{pool:16s} {name:20s} {len(tasks):4d} {v:7.3f} {j:7.3f} {100 * (j - v):+9.2f}")
        report["pools"][pool] = entry

    print("\n=== H3/H4: the full suite, and the cascade")
    print(f"{'pool':16s} {'n':>4s} {'vote':>7s} {'judge':>7s} {'cascade':>8s} "
          f"{'judge $':>9s} {'cascade $':>10s} {'saved':>7s}")
    for pool, run_id in RUNS.items():
        cell = load(run_id)
        judge, vote = cell["outcome"][JUDGE], cell["outcome"][VOTE]
        jcost, vcost, classes = cell["cost"][JUDGE], cell["cost"][VOTE], cell["classes"]
        shared = sorted(set(judge) & set(vote))
        easy = [t for t in shared if classes.get(t, "").startswith("UNANIMOUS")]

        # The cascade: take the members' answer when they agree, escalate to the judge otherwise.
        cascade = [vote[t] if t in set(easy) else judge[t] for t in shared]
        cascade_cost = [vcost[t] if t in set(easy) else jcost[t] for t in shared]
        j, v, c = (
            float(np.mean([judge[t] for t in shared])),
            float(np.mean([vote[t] for t in shared])),
            float(np.mean(cascade)),
        )
        jc, cc = float(np.mean([jcost[t] for t in shared])), float(np.mean(cascade_cost))
        report["pools"][pool]["full_suite"] = {
            "n_tasks": len(shared), "n_unanimous": len(easy),
            "vote": v, "judge": j, "cascade": c,
            "judge_minus_vote_pp": 100.0 * (j - v),
            "cascade_minus_judge_pp": 100.0 * (c - j),
            "judge_cost_per_task": jc, "cascade_cost_per_task": cc,
            "cost_saved_frac": 1.0 - cc / jc if jc else float("nan"),
        }
        print(f"{pool:16s} {len(shared):4d} {v:7.3f} {j:7.3f} {c:8.3f} "
              f"{jc:9.5f} {cc:10.5f} {1 - cc / jc:6.0%}")

    overrides = sum(
        e["by_class"].get("UNANIMOUS_CORRECT", {}).get("n_judge_overrides_a_correct_consensus", 0)
        for e in report["pools"].values()
    )
    total_correct = sum(
        e["by_class"].get("UNANIMOUS_CORRECT", {}).get("n", 0) for e in report["pools"].values()
    )
    rescues = sum(
        e["by_class"].get("UNANIMOUS_WRONG", {}).get("n_judge_rescues", 0)
        for e in report["pools"].values()
    )
    total_wrong = sum(
        e["by_class"].get("UNANIMOUS_WRONG", {}).get("n", 0) for e in report["pools"].values()
    )
    cascade_deltas = [e["full_suite"]["cascade_minus_judge_pp"] for e in report["pools"].values()]
    report["decision"] = {
        "H1_judge_accuracy_on_unanimous_correct": 1.0 - overrides / max(total_correct, 1),
        "H1_overrides": overrides,
        "H1_n": total_correct,
        "H1_notable_judge_damages_consensus": bool(1.0 - overrides / max(total_correct, 1) <= 0.98),
        "H2_rescue_rate_on_unanimous_wrong": rescues / max(total_wrong, 1),
        "H2_notable_judge_contributes_knowledge": bool(rescues / max(total_wrong, 1) >= 0.05),
        "H4_cascade_minus_judge_pp": cascade_deltas,
        "H4_notable_cascade_beats_judge": bool(all(d >= 0 for d in cascade_deltas)),
    }
    OUTPUT.write_text(json.dumps(report, indent=1))

    d = report["decision"]
    print("\n=== the pre-registered outcomes")
    print(f"    H1 judge on unanimous-correct: {d['H1_judge_accuracy_on_unanimous_correct']:.3f} "
          f"({d['H1_overrides']} overrides of {d['H1_n']})  notable={d['H1_notable_judge_damages_consensus']}")
    print(f"    H2 rescue rate on unanimous-wrong: {d['H2_rescue_rate_on_unanimous_wrong']:.3f} "
          f"notable={d['H2_notable_judge_contributes_knowledge']}")
    print(f"    H4 cascade minus judge: {[f'{x:+.2f}' for x in d['H4_cascade_minus_judge_pp']]} "
          f"notable={d['H4_notable_cascade_beats_judge']}")
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
