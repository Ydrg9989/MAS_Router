"""Under a fixed budget per task, does choosing an organization per capability beat choosing one?

D-035 found that a domain router given ground-truth capability labels loses to plain majority voting
on accuracy by 1.9 points, while making one model call where the vote makes four. That left the
honest version of the routing case open, and D-035 recorded it as something to measure rather than
assert: routing may buy efficiency even where it does not buy accuracy.

The question is posed as a budget rather than a cost penalty, deliberately. A first version swept a
penalty ``accuracy - lambda * cost`` and compared the two policies at matched lambda. That is
subtly wrong in a way that flatters routing: sweeping lambda over a set of organizations traces only
the *upper convex hull* of that set, so an organization that is Pareto-efficient yet sits inside the
hull is invisible to the global policy at every lambda. A routed policy mixes per capability and can
land in exactly that concave region, so it would appear to beat the global frontier while merely
filling a gap the sweep could never reach. A budget constraint has no such blind spot: at each
budget both policies take the most accurate organization they can afford, which is the full Pareto
frontier rather than its hull, and it is also the form a deployer's constraint actually takes.

So, at each budget in dollars per task, both policies are chosen on the same calibration tasks from
the same 30 organizations and scored on held-out tasks. The only difference is whether the choice is
made once for the suite or once per capability. Budgets are fixed from the full data so they mean
the same thing across resplits, and the authoritative numbers are means over random
calibration/test partitions, since D-033 found the single manifest split flatters routing.

Cost is what a deployment would pay, not what these runs happened to pay:

* Every call is repriced from its four token buckets against the run's frozen price snapshot, so
  cache hits are charged what a first run would cost rather than the $0 they recorded.
* ``independent_majority`` over a coalition of k charges all k members.
* ``single_expert`` charges only the member it consults. Its predictor reads calibration accuracy by
  domain and never inspects the current task's answers
  ([`mas_harness/pool/expert.py`](mas_harness/pool/expert.py)), so one call is what a deployment
  would make. `single_expert` over the whole pool is thus already a per-capability router, and the
  cheapest one in the family.

    python scripts/measure_cost_frontier.py
"""

from __future__ import annotations

import json
from collections import defaultdict

import numpy as np

from mas_harness import config
from mas_harness.clients.pricing import PricingTable, step_cost_usd
from mas_harness.records.schema import EpisodeRecord
from mas_harness.records.writer import RunDirectory
from mas_harness.tasks.manifest import Manifest

FREE_PROTOCOLS = ("single_expert", "independent_majority")

SUITES = {
    "hard366": {
        "manifest": "hard366.json",
        "runs": {"strong4": "strong4-a", "decorrelated4": "decorr4-a",
                 "correlated4": "correlated4-a"},
    },
    "crosscap240": {
        "manifest": "crosscap240.json",
        "runs": {"strong4": "crosscap-strong4", "decorrelated4": "crosscap-decorr4",
                 "correlated4": "crosscap-corr4"},
    },
}

N_SPLITS = 200
OUTPUT = config.RUNS_DIR / "cost_frontier.json"

Organization = tuple[str, tuple[int, ...]]


def consulted(episode: EpisodeRecord) -> list[int]:
    """Which members a deployment would actually pay for.

    `single_expert` reads one banked answer and records which, so charging it for the whole
    coalition would overstate its cost fourfold and invert the comparison this script exists for.
    """
    selected = episode.protocol_meta.get("selected_agent_id")
    if episode.protocol_id == "single_expert" and isinstance(selected, int):
        return [selected]
    return list(episode.coalition)


def load_cell(
    run_id: str, tasks: set[str]
) -> tuple[list[Organization], list[str], np.ndarray, np.ndarray]:
    """Organizations, the tasks all of them cover, and their outcome and cost matrices."""
    directory = RunDirectory(config.RUNS_DIR, run_id)
    prices = PricingTable.read(config.RUNS_DIR / run_id / "pricing_snapshot.json")
    per_answer = {
        (r.agent_id, r.task_id): step_cost_usd(r.call.usage, prices.get(r.model))
        for r in directory.load_answers()
    }

    correct: dict[Organization, dict[str, bool]] = defaultdict(dict)
    cost: dict[Organization, dict[str, float]] = defaultdict(dict)
    for episode in directory.load_episodes():
        if episode.intervention.kind != "none" or episode.protocol_id not in FREE_PROTOCOLS:
            continue
        if episode.task_id not in tasks:
            continue
        organization = (episode.protocol_id, tuple(sorted(episode.coalition)))
        spend = sum(per_answer.get((a, episode.task_id), 0.0) for a in consulted(episode))
        # Protocols that talk add calls on top of the banked answers. Zero for these two, but
        # computed rather than assumed so this stays correct if the family widens.
        spend += sum(step_cost_usd(c.usage, prices.get(c.model)) for c in episode.calls)
        correct[organization][episode.task_id] = bool(episode.correct)
        cost[organization][episode.task_id] = spend

    organizations = sorted(correct)
    shared = sorted(set.intersection(*[set(correct[o]) for o in organizations]))
    outcomes = np.array([[float(correct[o][t]) for t in shared] for o in organizations])
    spend = np.array([[cost[o][t] for t in shared] for o in organizations])
    return organizations, shared, outcomes, spend


def _afford(accuracy: np.ndarray, spend: np.ndarray, budget: float) -> int | None:
    """The most accurate organization costing no more than ``budget``, cheapest breaking ties."""
    feasible = np.flatnonzero(spend <= budget * (1 + 1e-9))
    if feasible.size == 0:
        return None
    return int(feasible[np.lexsort((spend[feasible], -accuracy[feasible]))[0]])


def policies_at_budget(
    outcomes: np.ndarray,
    cost: np.ndarray,
    domain_index: np.ndarray,
    train: np.ndarray,
    budget: float,
) -> tuple[int, np.ndarray] | None:
    """The best affordable organization overall, and the best affordable one per capability."""
    accuracy = outcomes[:, train].mean(axis=1)
    spend = cost[:, train].mean(axis=1)
    global_pick = _afford(accuracy, spend, budget)
    if global_pick is None:
        return None

    routed = np.full(outcomes.shape[1], global_pick, dtype=int)
    for d in np.unique(domain_index):
        columns = train[domain_index[train] == d]
        if not columns.size:
            continue
        local = _afford(
            outcomes[:, columns].mean(axis=1), cost[:, columns].mean(axis=1), budget
        )
        if local is not None:
            routed[domain_index == d] = local
    return global_pick, routed


def lambda_grid(cost: np.ndarray, n: int = 12) -> np.ndarray:
    """Twelve penalties from "cost is free" to "cost dominates", scaled to this cell's prices."""
    span = float(cost.mean(axis=1).max() - cost.mean(axis=1).min())
    if span <= 0:
        return np.zeros(1)
    return np.geomspace(0.01 / span, 10.0 / span, n)


def policies_at_lambda(
    outcomes: np.ndarray,
    cost: np.ndarray,
    domain_index: np.ndarray,
    train: np.ndarray,
    penalty: float,
) -> tuple[int, np.ndarray]:
    """The retracted instrument: argmax of ``accuracy - penalty * cost``, global and per capability.

    Kept because Lemma 2 needs a demonstration, not because the comparison is sound. See D-036.
    """
    utility = outcomes[:, train].mean(axis=1) - penalty * cost[:, train].mean(axis=1)
    global_pick = int(np.argmax(utility))

    routed = np.full(outcomes.shape[1], global_pick, dtype=int)
    for d in np.unique(domain_index):
        columns = train[domain_index[train] == d]
        if not columns.size:
            continue
        local = outcomes[:, columns].mean(axis=1) - penalty * cost[:, columns].mean(axis=1)
        routed[domain_index == d] = int(np.argmax(local))
    return global_pick, routed


def hull_diagnostic(outcomes: np.ndarray, cost: np.ndarray, names: list[str]) -> dict:
    """How many organizations are Pareto-optimal but unreachable by any linear penalty?

    Lemma 2 says a lambda sweep reaches only the upper convex hull of the (cost, accuracy) cloud.
    Organizations that are Pareto-efficient yet interior to that hull are therefore invisible to the
    global policy at every lambda, while a routed policy picks per capability from all of them. The
    size of that invisible set is the whole mechanism of the artefact, measured here directly.
    """
    accuracy = outcomes.mean(axis=1)
    spend = cost.mean(axis=1)

    pareto = [
        i
        for i in range(len(accuracy))
        if not np.any(
            (spend <= spend[i] + 1e-12)
            & (accuracy >= accuracy[i] - 1e-12)
            & ((spend < spend[i] - 1e-12) | (accuracy > accuracy[i] + 1e-12))
        )
    ]

    # The hull is exactly the set reachable by some penalty, so enumerate it that way: sweep a dense
    # grid of penalties and collect every argmax. Ties go to the first index, matching the sweep.
    reachable = set()
    for penalty in np.concatenate([[0.0], lambda_grid(cost, n=400)]):
        reachable.add(int(np.argmax(accuracy - penalty * spend)))

    interior = sorted(set(pareto) - reachable)
    return {
        "n_organizations": int(len(accuracy)),
        "n_pareto": len(pareto),
        "n_reachable_by_some_lambda": len(reachable),
        "n_pareto_but_unreachable": len(interior),
        "pareto_but_unreachable": [names[i] for i in interior],
    }


def stratified_split(
    domain_index: np.ndarray, fraction: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    left: list[int] = []
    right: list[int] = []
    for d in np.unique(domain_index):
        columns = np.flatnonzero(domain_index == d)
        rng.shuffle(columns)
        cut = max(1, int(round(fraction * len(columns))))
        left.extend(columns[:cut].tolist())
        right.extend(columns[cut:].tolist())
    return np.array(sorted(left)), np.array(sorted(right))


def curve(
    outcomes: np.ndarray,
    cost: np.ndarray,
    domain_index: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    budgets: np.ndarray,
) -> list[dict]:
    rows = []
    for budget in budgets:
        chosen = policies_at_budget(outcomes, cost, domain_index, train, budget)
        if chosen is None:
            continue
        global_pick, routed = chosen
        rows.append(
            {
                "budget": float(budget),
                "global_accuracy": float(outcomes[global_pick, test].mean()),
                "global_cost": float(cost[global_pick, test].mean()),
                "global_pick": int(global_pick),
                "routed_accuracy": float(outcomes[routed[test], test].mean()),
                "routed_cost": float(cost[routed[test], test].mean()),
                "routed_n_distinct": int(len(set(routed[test].tolist()))),
                "gain_pp": 100
                * float(outcomes[routed[test], test].mean() - outcomes[global_pick, test].mean()),
            }
        )
    return rows


def main() -> None:
    report: dict[str, dict] = {}
    for suite, spec in SUITES.items():
        manifest = Manifest.read(config.DATA_DIR / "manifests" / spec["manifest"])
        domains = {s.task_id: s.domain for s in manifest.tasks}
        report[suite] = {}
        print(f"\n=== {suite}")

        for pool, run_id in spec["runs"].items():
            organizations, tasks, outcomes, cost = load_cell(run_id, set(domains))
            index = {t: i for i, t in enumerate(tasks)}
            labels = sorted({domains[t] for t in tasks})
            domain_index = np.array([labels.index(domains[t]) for t in tasks])
            names = [f"{p}|{'-'.join(map(str, c))}" for p, c in organizations]

            # Budgets are the distinct organization prices on the full data: exactly the points at
            # which the affordable set changes, and fixed so they mean the same across resplits.
            budgets = np.unique(np.round(cost.mean(axis=1), 12))

            train = np.array(sorted(index[t] for t in manifest.splits["calibration"] if t in index))
            test = np.array(sorted(index[t] for t in manifest.splits["test"] if t in index))
            manifest_curve = curve(outcomes, cost, domain_index, train, test, budgets)

            rng = np.random.default_rng(12345)
            fraction = len(train) / (len(train) + len(test))
            gains = {float(b): [] for b in budgets}
            penalties = lambda_grid(cost)
            lambda_gains: dict[float, list[float]] = {float(p): [] for p in penalties}
            for _ in range(N_SPLITS):
                tr, te = stratified_split(domain_index, fraction, rng)
                for row in curve(outcomes, cost, domain_index, tr, te, budgets):
                    gains[row["budget"]].append(row["gain_pp"])
                for penalty in penalties:
                    pick, routed = policies_at_lambda(outcomes, cost, domain_index, tr, penalty)
                    lambda_gains[float(penalty)].append(
                        100
                        * float(outcomes[routed[te], te].mean() - outcomes[pick, te].mean())
                    )

            resplit = {
                f"{b:.6g}": {
                    "mean": float(np.mean(v)),
                    "sd": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
                    "frac_positive": float(np.mean(np.array(v) > 0)),
                    "n": len(v),
                }
                for b, v in gains.items()
                if v
            }
            best_budget = max(resplit, key=lambda b: resplit[b]["mean"])

            print(f"\n  -- {pool}  ({len(tasks)} tasks, {len(organizations)} organizations, "
                  f"{len(labels)} capabilities)")
            print(f"     {'budget $/task':>13s} {'global acc':>11s} {'routed acc':>11s} "
                  f"{'routed $':>10s} {'orgs':>5s} {'gain':>8s} | {'resplit gain':>12s} "
                  f"{'pos':>5s}")
            for row in manifest_curve:
                key = f"{row['budget']:.6g}"
                entry = resplit.get(key)
                tail = (
                    f" | {entry['mean']:+9.2f} pp {entry['frac_positive']:5.0%}"
                    if entry
                    else ""
                )
                print(
                    f"     {row['budget']:13.6f} {row['global_accuracy']:11.3f} "
                    f"{row['routed_accuracy']:11.3f} {row['routed_cost']:10.6f} "
                    f"{row['routed_n_distinct']:5d} {row['gain_pp']:+7.2f}{tail}"
                )

            unlimited = resplit[f"{budgets[-1]:.6g}"]
            print(
                f"     unlimited budget: {unlimited['mean']:+.2f} pp "
                f"(positive in {unlimited['frac_positive']:.0%} of splits)"
            )
            top = resplit[best_budget]
            print(
                f"     best budget ${float(best_budget):.6f}: {top['mean']:+.2f} pp "
                f"(positive in {top['frac_positive']:.0%}) -- a maximum over "
                f"{len(resplit)} budgets, so read the curve, not this row"
            )

            sweep = {
                f"{p:.6g}": {
                    "mean": float(np.mean(v)),
                    "frac_positive": float(np.mean(np.array(v) > 0)),
                    "n": len(v),
                }
                for p, v in lambda_gains.items()
                if v
            }
            best_lambda = max(sweep, key=lambda k: sweep[k]["mean"])
            hull = hull_diagnostic(outcomes, cost, names)
            print(
                f"     RETRACTED lambda sweep, best of {len(sweep)}: "
                f"{sweep[best_lambda]['mean']:+.2f} pp "
                f"(positive in {sweep[best_lambda]['frac_positive']:.0%}) at lambda="
                f"{float(best_lambda):.4g}"
            )
            print(
                f"     hull: {hull['n_pareto']} of {hull['n_organizations']} organizations are "
                f"Pareto-efficient, {hull['n_reachable_by_some_lambda']} reachable by some lambda, "
                f"{hull['n_pareto_but_unreachable']} Pareto but invisible to every lambda"
            )

            report[suite][pool] = {
                "organizations": names,
                "capabilities": labels,
                "manifest_split_curve": manifest_curve,
                "resplit_gain_by_budget": resplit,
                "unlimited_budget_gain_pp": unlimited,
                "retracted_lambda_sweep": {
                    "note": "D-036: unsound instrument, kept only to demonstrate Lemma 2",
                    "gain_by_lambda": sweep,
                    "best_lambda": float(best_lambda),
                    "best_gain_pp": sweep[best_lambda],
                },
                "hull_diagnostic": hull,
                "picks_at_tightest_budget": {
                    labels[d]: names[p]
                    for d, p in enumerate(
                        (policies_at_budget(
                            outcomes, cost, domain_index, train, float(budgets[0])
                        ) or (0, np.zeros(len(tasks), int)))[1][
                            [int(np.flatnonzero(domain_index == d)[0]) for d in range(len(labels))]
                        ]
                    )
                },
            }

    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
