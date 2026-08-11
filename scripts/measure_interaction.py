"""Is the interaction real at the agent level and invisible at the organization level?

FRAMEWORK 5.2 asks for this and TODO has carried it since D-037. The headroom tests say only that a
per-task maximum over organizations cannot beat a null with no agent-by-task interaction. That is a
statement about an *estimator*, and on its own it leaves two very different worlds
indistinguishable: either there is no interaction, or there is interaction headroom cannot see.

The capability table in FRAMEWORK 5.1 points at the second. This script settles it by testing
``gamma = 0`` in ``sigma(alpha_u + beta_x + gamma_{u,c(x)})`` at two levels of the same data:

``agents``
    Eight distinct models on the shared `crosscap240` tasks, capability being which benchmark the
    task came from. This is where the reversals live.

``organizations``
    The thirty coalition-by-protocol organizations in each of the six pool-by-suite cells. This is
    the level at which every headroom figure in the project was computed.

If agents show interaction and organizations do not, then aggregation into coalitions is what hides
it, and "aggregation absorbs specialisation" stops being an interpretation and becomes a
measurement.

    python scripts/measure_interaction.py
"""

from __future__ import annotations

import json
from collections import defaultdict

from mas_harness import config
from mas_harness.metrics.interaction import InteractionTest, interaction_likelihood_ratio
from mas_harness.records.writer import RunDirectory

FREE_PROTOCOLS = ("single_expert", "independent_majority")
SUITES = {
    "hard366": {
        "strong4": "strong4-a",
        "decorrelated4": "decorr4-a",
        "correlated4": "correlated4-a",
    },
    "crosscap240": {
        "strong4": "crosscap-strong4",
        "decorrelated4": "crosscap-decorr4",
        "correlated4": "crosscap-corr4",
    },
}
N_SIMULATIONS = 200
OUTPUT = config.RUNS_DIR / "interaction.json"


def agent_outcomes(runs: dict[str, str]) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    """Agent name to task to correctness, plus the capability of each task.

    Keyed by name rather than id because pools overlap; an agent appearing in two pools contributes
    the same banked answer, so the first one wins and the grid stays consistent.
    """
    outcomes: dict[str, dict[str, bool]] = defaultdict(dict)
    capability: dict[str, str] = {}
    for run_id in runs.values():
        for record in RunDirectory(config.RUNS_DIR, run_id).load_answers():
            outcomes[record.agent_name].setdefault(record.task_id, bool(record.correct))
            capability[record.task_id] = record.domain
    return dict(outcomes), capability


def organization_outcomes(run_id: str) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    """Organization label to task to correctness, for clean episodes of the free protocols."""
    directory = RunDirectory(config.RUNS_DIR, run_id)
    capability = {r.task_id: r.domain for r in directory.load_answers()}

    outcomes: dict[str, dict[str, bool]] = defaultdict(dict)
    for episode in directory.load_episodes():
        if episode.intervention.kind != "none" or episode.protocol_id not in FREE_PROTOCOLS:
            continue
        members = "+".join(str(a) for a in sorted(episode.coalition))
        outcomes[f"{episode.protocol_id}[{members}]"][episode.task_id] = bool(episode.correct)
    return dict(outcomes), capability


def line(name: str, result: InteractionTest) -> str:
    if result.note:
        return f"  {name:28s} {result.note}"
    return (
        f"  {name:28s} units={result.n_units:3d} tasks={result.n_tasks:3d} "
        f"caps={result.n_capabilities} LR={result.statistic:8.1f} "
        f"df={result.degrees_of_freedom:3d} p_boot={result.p_value_bootstrap:.4f} "
        f"departure={result.mean_absolute_departure_points:5.2f}pp "
        f"(null {result.null_mean_absolute_departure_points:5.2f}, "
        f"excess {result.excess_departure_points:+5.2f})"
    )


def main() -> None:
    report: dict[str, dict] = {"n_simulations": N_SIMULATIONS, "agents": {}, "organizations": {}}

    print("Agent level, capability = source benchmark")
    for suite, runs in SUITES.items():
        outcomes, capability = agent_outcomes(runs)
        result = interaction_likelihood_ratio(
            outcomes, capability, n_simulations=N_SIMULATIONS
        )
        report["agents"][suite] = result.as_dict()
        print(line(suite, result))
        for departure in result.largest_departures[:5]:
            print(
                f"      {departure.unit:14s} {departure.capability:18s} "
                f"observed={departure.observed:.3f} additive={departure.additive_prediction:.3f} "
                f"departure={departure.departure_points:+6.1f}pp"
            )

    print("\nOrganization level, the family every headroom figure was maximised over")
    for suite, runs in SUITES.items():
        report["organizations"][suite] = {}
        for pool, run_id in runs.items():
            outcomes, capability = organization_outcomes(run_id)
            result = interaction_likelihood_ratio(
                outcomes, capability, n_simulations=N_SIMULATIONS
            )
            report["organizations"][suite][pool] = result.as_dict()
            print(line(f"{suite}/{pool}", result))

    OUTPUT.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main()
