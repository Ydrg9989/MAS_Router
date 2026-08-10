"""Go/no-go gate: the report's day-14 project selection, made mechanical.

The point of encoding the thresholds in code is that they are fixed *before* the numbers come
in. A criterion decided after seeing the data is not a criterion. So this script reads a run
directory, evaluates every continue and kill condition the research report states, and prints a
recommendation. Nothing here interprets or argues; it reports whether each stated bar was met.

    python -m mas_harness.analysis.gonogo --run-id mvp90-r1 --manifest data/manifests/mvp90.json

Two honesty features are built in. Every criterion reports the sample size it was evaluated on,
and any criterion whose sample is too small to be meaningful is marked ``INSUFFICIENT`` rather
than passed or failed — at 90 tasks several of them will be. And the recommendation is refused
outright if the required evidence for a direction was never collected, instead of defaulting to
a kill.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .. import config
from ..metrics import coalition as C
from ..metrics import delegation, governance, utility
from ..metrics.stats import holm_bonferroni, mcnemar, paired_bootstrap, required_n_paired
from ..pool.agents import AgentPool
from ..records.schema import AnswerRecord, EpisodeRecord
from ..records.writer import RunDirectory
from ..tasks.manifest import Manifest

PASS = "PASS"
FAIL = "FAIL"
INSUFFICIENT = "INSUFFICIENT"

# Minimum paired items before a threshold verdict is meaningful rather than noise.
MIN_ITEMS_FOR_VERDICT = 20
MIN_PAIRS_FOR_INTERVENTION = 15


@dataclass
class Criterion:
    """One stated threshold, its observed value, and the verdict."""

    direction: str
    name: str
    threshold: str
    observed: float | None
    verdict: str
    n: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateReport:
    run_id: str
    generated_at: str
    criteria: list[Criterion] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)

    def add(self, criterion: Criterion) -> None:
        self.criteria.append(criterion)

    def by_direction(self, direction: str) -> list[Criterion]:
        return [c for c in self.criteria if c.direction == direction]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "criteria": [c.to_dict() for c in self.criteria],
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


def _verdict(observed: float | None, threshold: float, n: int, *, minimum: int, above: bool = True):
    if observed is None or np.isnan(observed):
        return INSUFFICIENT
    if n < minimum:
        return INSUFFICIENT
    return PASS if (observed >= threshold if above else observed <= threshold) else FAIL


# ---- direction 1: epistemic governance ---------------------------------------------------


def evaluate_governance(
    report: GateReport, episodes: Sequence[EpisodeRecord], competence: dict[int, float]
) -> None:
    observational = governance.observational(episodes)

    spread = governance.protocol_spread(episodes)
    report.evidence["protocol_spread"] = {
        k: v for k, v in spread.items() if k != "paired_outcomes"
    }
    report.add(
        Criterion(
            direction="governance",
            name="protocol spread",
            threshold=">= 8pp between best and worst protocol",
            observed=spread.get("spread_pp"),
            verdict=_verdict(
                spread.get("spread_pp"),
                8.0,
                spread.get("n_common_items", 0),
                minimum=MIN_ITEMS_FOR_VERDICT,
            ),
            n=spread.get("n_common_items", 0),
            detail=(
                f"best={spread.get('best_protocol')} worst={spread.get('worst_protocol')}; "
                f"accuracies={spread.get('accuracy_by_protocol')}"
            ),
        )
    )

    # Pairwise significance across protocols, Holm-corrected across the whole family.
    paired = spread.get("paired_outcomes") or {}
    p_values: dict[str, float] = {}
    effects: dict[str, dict[str, Any]] = {}
    protocol_ids = sorted(paired)
    common = sorted(set.intersection(*(set(v) for v in paired.values()))) if paired else []
    for i, first in enumerate(protocol_ids):
        for second in protocol_ids[i + 1 :]:
            a = [paired[first][k] for k in common]
            b = [paired[second][k] for k in common]
            if not a:
                continue
            test = mcnemar(a, b)
            boot = paired_bootstrap([float(x) for x in a], [float(x) for x in b], seed=0)
            label = f"{first}_vs_{second}"
            p_values[label] = test.p_value
            effects[label] = {
                "effect_pp": test.effect * 100,
                "ci_low_pp": boot.ci_low * 100,
                "ci_high_pp": boot.ci_high * 100,
                "discordant": test.detail.get("discordant"),
                "p_raw": test.p_value,
            }
    corrected = holm_bonferroni(p_values) if p_values else {}
    for label, entry in corrected.items():
        effects[label].update(
            {"p_adjusted": entry["p_adjusted"], "reject": entry["reject"]}
        )
    report.evidence["protocol_pairwise"] = effects
    report.evidence["n_significant_after_holm"] = sum(
        1 for e in effects.values() if e.get("reject")
    )

    # Dilution on the predicted expert, per protocol.
    dilution_by_protocol: dict[str, Any] = {}
    for protocol_id in sorted({e.protocol_id for e in observational}):
        subset = [e for e in observational if e.protocol_id == protocol_id]
        try:
            rates = governance.governance_rates(subset, use_oracle=False)
        except ValueError:
            continue
        oracle = governance.governance_rates(subset, use_oracle=True)
        dilution_by_protocol[protocol_id] = {
            "predicted": rates.to_dict(),
            "oracle_upper_bound": {
                "dilution_rate": oracle.dilution_rate,
                "expert_utilization_rate": oracle.expert_utilization_rate,
                "rescue_rate": oracle.rescue_rate,
            },
        }
    report.evidence["governance_rates"] = dilution_by_protocol

    # The report's threshold applies to the aggregation protocols, where dilution is possible
    # at all. single_expert cannot dilute by construction, so including it would drag the
    # maximum down for a structural reason rather than an empirical one.
    candidates = {
        p: v
        for p, v in dilution_by_protocol.items()
        if p != "single_expert" and not np.isnan(v["predicted"]["dilution_rate"])
    }
    if candidates:
        worst_protocol = max(candidates, key=lambda p: candidates[p]["predicted"]["dilution_rate"])
        worst = candidates[worst_protocol]["predicted"]
        observed = worst["dilution_rate"] * 100
        n = worst["n_expert_correct"]
    else:
        worst_protocol, observed, n = None, None, 0

    report.add(
        Criterion(
            direction="governance",
            name="correct-answer dilution",
            threshold=">= 15% of tasks where the PREDICTED expert is correct",
            observed=observed,
            verdict=_verdict(observed, 15.0, n, minimum=MIN_ITEMS_FOR_VERDICT),
            n=n,
            detail=f"worst non-trivial protocol: {worst_protocol}",
        )
    )

    # Causal influence: the intervention flip rate.
    flip_rates: dict[str, Any] = {}
    for protocol_id in sorted({e.protocol_id for e in episodes}):
        subset = [e for e in episodes if e.protocol_id == protocol_id]
        profile = governance.influence_profile(subset, competence=competence, kind="mask")
        if profile.influence:
            flip_rates[protocol_id] = profile.to_dict()
    report.evidence["influence_profiles"] = flip_rates

    all_rates = [
        v["mean_flip_rate"] for v in flip_rates.values() if not np.isnan(v["mean_flip_rate"])
    ]
    total_pairs = sum(
        sum(v["n_pairs"].values()) for v in flip_rates.values()
    )
    best_flip = max(all_rates) * 100 if all_rates else None
    report.add(
        Criterion(
            direction="governance",
            name="intervention flip rate",
            threshold=">= 10% of masked messages change the decision",
            observed=best_flip,
            verdict=_verdict(
                best_flip, 10.0, total_pairs, minimum=MIN_PAIRS_FOR_INTERVENTION
            ),
            n=total_pairs,
            detail=(
                "requires --interventions masks in Stage B"
                if not flip_rates
                else f"max over {len(flip_rates)} protocols"
            ),
        )
    )

    report.evidence["order_sensitivity"] = {
        protocol_id: governance.order_sensitivity(
            [e for e in episodes if e.protocol_id == protocol_id]
        )
        for protocol_id in sorted({e.protocol_id for e in episodes})
    }
    report.evidence["substitution_uptake"] = {
        protocol_id: governance.substitution_uptake(
            [e for e in episodes if e.protocol_id == protocol_id]
        )
        for protocol_id in sorted({e.protocol_id for e in episodes})
    }


# ---- direction 2: delegation-equivalent representations -----------------------------------


def evaluate_delegation(
    report: GateReport,
    episodes: Sequence[EpisodeRecord],
    answers: Sequence[AnswerRecord],
    manifest: Manifest,
) -> None:
    dominance = governance.protocol_dominance(episodes)
    report.evidence["protocol_dominance"] = dominance
    observed = dominance.get("dominance_fraction")
    report.add(
        Criterion(
            direction="delegation",
            name="configuration dominance",
            threshold="<= 75% of domains won by one configuration (higher kills the direction)",
            observed=observed * 100 if observed is not None else None,
            verdict=_verdict(
                observed * 100 if observed is not None else None,
                75.0,
                dominance.get("n_domains", 0),
                minimum=3,
                above=False,
            ),
            n=dominance.get("n_domains", 0),
            detail=f"dominant={dominance.get('dominant_protocol')}",
        )
    )

    by_id = manifest.by_id()
    task_ids = sorted({e.task_id for e in episodes if e.task_id in by_id})
    if len(task_ids) < 4:
        report.add(
            Criterion(
                direction="delegation",
                name="semantic vs organizational similarity",
                threshold="correlation < 0.5 AND >= 20% differing nearest neighbours",
                observed=None,
                verdict=INSUFFICIENT,
                n=len(task_ids),
                detail="need at least 4 tasks with episodes to build a similarity space",
            )
        )
        return

    semantic = delegation.semantic_space(task_ids, [by_id[t].prompt for t in task_ids])
    organizational = delegation.organizational_space(episodes)
    capability = delegation.capability_space(answers)

    semantic_vs_org = delegation.compare_spaces(semantic, organizational, k=1)
    capability_vs_org = delegation.compare_spaces(capability, organizational, k=1)
    report.evidence["space_comparisons"] = {
        "semantic_vs_organizational": semantic_vs_org,
        "capability_vs_organizational": capability_vs_org,
    }

    correlation = semantic_vs_org["spearman_similarity_correlation"]
    differing = semantic_vs_org["frac_differing_nearest_neighbours"] * 100
    n_tasks = semantic_vs_org["n_tasks"]
    # Both halves of the report's conjunction must hold.
    if correlation is None or np.isnan(correlation) or n_tasks < MIN_ITEMS_FOR_VERDICT:
        verdict = INSUFFICIENT
    else:
        verdict = PASS if (correlation < 0.5 and differing >= 20.0) else FAIL

    report.add(
        Criterion(
            direction="delegation",
            name="semantic vs organizational similarity",
            threshold="Spearman correlation < 0.5 AND >= 20% differing nearest neighbours",
            observed=correlation,
            verdict=verdict,
            n=n_tasks,
            detail=(
                f"differing nearest neighbours {differing:.1f}%; "
                f"semantic method: {semantic.method}"
                + (
                    " (WEAK FALLBACK, treat a low correlation cautiously)"
                    if semantic.fallback_used
                    else ""
                )
            ),
        )
    )

    stats = utility.configuration_stats(episodes)
    calibration = [t for t in manifest.splits.get("calibration", []) if t in set(task_ids)]
    test = [t for t in manifest.splits.get("test", []) if t in set(task_ids)]
    if calibration and test:
        report.evidence["nn_routing_regret"] = {
            space.name: delegation.nearest_neighbour_routing_regret(
                space, stats, train_task_ids=calibration, test_task_ids=test
            )
            for space in (semantic, capability, organizational)
        }


# ---- direction 3: coalition landscapes ----------------------------------------------------


def evaluate_coalitions(
    report: GateReport,
    episodes: Sequence[EpisodeRecord],
    answers: Sequence[AnswerRecord],
    pool: AgentPool,
) -> None:
    observational = governance.observational(episodes)
    n_agents = len(pool)

    # Observed coalition values, on a fixed aggregation protocol (D-008).
    protocol_id = "independent_majority"
    subset = [e for e in observational if e.protocol_id == protocol_id]
    if not subset:
        report.add(
            Criterion(
                direction="coalition",
                name="top-k gap",
                threshold=">= 5pp gap on >= 15% of tasks",
                observed=None,
                verdict=INSUFFICIENT,
                n=0,
                detail=f"no '{protocol_id}' episodes; run Stage B with --coalitions all",
            )
        )
        return

    by_task: dict[str, dict[int, float]] = {}
    for episode in subset:
        by_task.setdefault(episode.task_id, {})[
            C.mask_of(episode.coalition)
        ] = float(episode.correct)

    n_masks = 1 << n_agents
    complete = [t for t, values in by_task.items() if len(values) == n_masks - 1]
    report.evidence["coalition_coverage"] = {
        "n_tasks_with_episodes": len(by_task),
        "n_tasks_with_all_coalitions": len(complete),
        "n_coalitions_required": n_masks - 1,
        "protocol_used": protocol_id,
    }

    if not complete:
        report.add(
            Criterion(
                direction="coalition",
                name="top-k gap",
                threshold=">= 5pp gap on >= 15% of tasks",
                observed=None,
                verdict=INSUFFICIENT,
                n=0,
                detail=(
                    f"no task has all {n_masks - 1} coalitions; Stage B must run with "
                    f"--coalitions all for the exhaustive analysis"
                ),
            )
        )
        return

    values = np.zeros((len(complete), n_masks))
    for row, task_id in enumerate(complete):
        for mask, value in by_task[task_id].items():
            values[row, mask] = value
    values[:, 0] = 0.0

    competence = np.array(
        [
            float(np.mean([r.correct for r in answers if r.agent_id == agent_id]) or 0.0)
            if any(r.agent_id == agent_id for r in answers)
            else 0.0
            for agent_id in range(n_agents)
        ]
    )

    dividends = C.harsanyi_dividends(values)
    ratio = C.higher_order_ratio(dividends, min_order=3)
    submodularity = C.submodularity_violations(values)
    synergies = {
        f"{i}_{j}": float(s.mean()) for (i, j), s in C.synergy_matrix(values, n_agents).items()
    }

    gaps = {}
    for k in range(1, n_agents):
        try:
            gaps[f"k{k}"] = C.top_k_gap(values, competence, k)
        except ValueError:
            continue

    report.evidence["coalition_analysis"] = {
        "n_tasks": len(complete),
        "mean_R_ge3": float(ratio.mean()),
        "submodularity_violation_rate": submodularity["mean_violation_rate"],
        "frac_tasks_with_submodularity_violation": submodularity["tasks_with_any_violation"],
        "mean_pairwise_synergy": synergies,
        "individual_accuracy": competence.tolist(),
        "top_k_gaps": {
            key: {
                "mean_gap": gap["mean_gap"],
                "frac_tasks_gap_ge_5pp": gap["frac_tasks_gap_ge_5pp"],
                "baseline_members": gap["baseline_members"],
            }
            for key, gap in gaps.items()
        },
    }

    best = max(
        (gap["frac_tasks_gap_ge_5pp"] for gap in gaps.values()), default=None
    )
    report.add(
        Criterion(
            direction="coalition",
            name="top-k gap",
            threshold=">= 15% of tasks where the best same-size coalition beats top-k by >= 5pp",
            observed=best * 100 if best is not None else None,
            verdict=_verdict(
                best * 100 if best is not None else None,
                15.0,
                len(complete),
                minimum=MIN_ITEMS_FOR_VERDICT,
            ),
            n=len(complete),
            detail=f"max over k=1..{n_agents - 1}",
        )
    )


# ---- recommendation -------------------------------------------------------------------------


def recommend(report: GateReport) -> dict[str, Any]:
    """Summarize each direction. Refuses to recommend where evidence was never collected."""
    summary: dict[str, Any] = {}
    for direction in ("governance", "delegation", "coalition"):
        criteria = report.by_direction(direction)
        passed = [c.name for c in criteria if c.verdict == PASS]
        failed = [c.name for c in criteria if c.verdict == FAIL]
        insufficient = [c.name for c in criteria if c.verdict == INSUFFICIENT]

        if not criteria:
            status = "NOT EVALUATED"
        elif insufficient and not passed:
            status = "INCONCLUSIVE - collect the missing evidence before deciding"
        elif passed and not failed:
            status = "GO"
        elif passed:
            status = "PARTIAL - some thresholds met, some not"
        else:
            status = "NO GO on the stated thresholds"

        summary[direction] = {
            "status": status,
            "passed": passed,
            "failed": failed,
            "insufficient": insufficient,
        }

    ranked = [d for d, v in summary.items() if v["status"] == "GO"]
    partial = [d for d, v in summary.items() if v["status"].startswith("PARTIAL")]
    summary["selection"] = (
        ranked[0]
        if len(ranked) == 1
        else (
            f"multiple directions cleared ({', '.join(ranked)}); choose on strength of effect"
            if ranked
            else (
                f"no direction cleared outright; strongest partial: {', '.join(partial)}"
                if partial
                else "insufficient evidence for any direction"
            )
        )
    )
    return summary


def build_report(
    *, run_id: str, runs_root: Path, manifest: Manifest, pool: AgentPool
) -> GateReport:
    run_dir = RunDirectory(runs_root, run_id)
    answers = run_dir.load_answers()
    episodes = run_dir.load_episodes()
    if not episodes:
        raise FileNotFoundError(
            f"no episodes in {run_dir.episodes_path}. Run Stage B before the gate."
        )

    competence: dict[int, float] = {}
    for agent in pool:
        own = [r.correct for r in answers if r.agent_id == agent.agent_id]
        if own:
            competence[agent.agent_id] = float(np.mean(own))

    report = GateReport(
        run_id=run_id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    report.evidence["scope"] = {
        "n_answers": len(answers),
        "n_episodes": len(episodes),
        "n_observational_episodes": len(governance.observational(episodes)),
        "n_tasks": len({e.task_id for e in episodes}),
        "protocols": sorted({e.protocol_id for e in episodes}),
        "intervention_kinds": sorted({e.intervention.kind for e in episodes}),
        "individual_accuracy": {str(k): v for k, v in sorted(competence.items())},
        "total_cost_usd": float(sum(e.total_cost_usd for e in episodes))
        + float(sum(a.call.cost_usd for a in answers)),
    }

    evaluate_governance(report, episodes, competence)
    evaluate_delegation(report, episodes, answers, manifest)
    evaluate_coalitions(report, episodes, answers, pool)

    # Power context: how many tasks an 8-point effect would actually need.
    spread = report.evidence.get("protocol_spread", {})
    pairwise = report.evidence.get("protocol_pairwise", {})
    discordances = [
        e["discordant"] / max(1, spread.get("n_common_items", 1))
        for e in pairwise.values()
        if e.get("discordant")
    ]
    if discordances:
        rate = float(np.mean(discordances))
        try:
            report.evidence["power"] = {
                "mean_discordance_rate": rate,
                "n_required_for_8pp_at_80_power": required_n_paired(
                    effect_pp=8.0, discordance_rate=rate
                ),
                "n_required_for_5pp_at_80_power": required_n_paired(
                    effect_pp=5.0, discordance_rate=rate
                ),
                "n_available": spread.get("n_common_items"),
            }
        except ValueError as exc:
            report.evidence["power"] = {"mean_discordance_rate": rate, "error": str(exc)}

    report.recommendation = recommend(report)
    return report


def print_report(report: GateReport) -> None:
    scope = report.evidence.get("scope", {})
    print(f"\nGo/No-Go gate — run {report.run_id}  ({report.generated_at})")
    print(
        f"  scope: {scope.get('n_tasks')} tasks, {scope.get('n_episodes')} episodes "
        f"({scope.get('n_observational_episodes')} observational), "
        f"{len(scope.get('protocols', []))} protocols, "
        f"${scope.get('total_cost_usd', 0.0):.2f} spent"
    )
    print(f"  interventions present: {scope.get('intervention_kinds')}")

    for direction in ("governance", "delegation", "coalition"):
        criteria = report.by_direction(direction)
        if not criteria:
            continue
        print(f"\n  {direction.upper()}")
        for criterion in criteria:
            observed = (
                f"{criterion.observed:.3f}" if criterion.observed is not None
                and not np.isnan(criterion.observed) else "n/a"
            )
            print(f"    [{criterion.verdict:12}] {criterion.name}")
            print(f"        threshold : {criterion.threshold}")
            print(f"        observed  : {observed}   (n={criterion.n})")
            if criterion.detail:
                print(f"        note      : {criterion.detail}")

    power = report.evidence.get("power")
    if power and "n_required_for_8pp_at_80_power" in power:
        print(
            f"\n  POWER: at {power['mean_discordance_rate']:.1%} discordance, detecting an 8pp "
            f"paired difference at 80% power needs ~{power['n_required_for_8pp_at_80_power']} "
            f"items; this run has {power['n_available']}."
        )

    print("\n  RECOMMENDATION")
    for direction in ("governance", "delegation", "coalition"):
        entry = report.recommendation.get(direction)
        if entry:
            print(f"    {direction:12}: {entry['status']}")
            if entry["insufficient"]:
                print(f"        missing evidence for: {', '.join(entry['insufficient'])}")
    print(f"    selection   : {report.recommendation.get('selection')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the report's go/no-go thresholds")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--runs-root", default=str(config.RUNS_DIR))
    parser.add_argument("--out", default=None, help="write the full JSON report here")
    args = parser.parse_args(argv)

    config.load_env()
    report = build_report(
        run_id=args.run_id,
        runs_root=Path(args.runs_root),
        manifest=Manifest.read(args.manifest),
        pool=AgentPool.from_yaml(args.pool),
    )
    print_report(report)

    out = Path(args.out) if args.out else Path(args.runs_root) / args.run_id / "gonogo.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, default=float))
    print(f"\n  full report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
