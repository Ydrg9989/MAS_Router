"""How much accuracy a pool leaves for governance to win. A precondition, not a result (D-021).

Every protocol in the registry decides among answers that are already in the Stage-A bank. The
two free ones do so strictly; the priced ones can in principle write an answer nobody proposed,
but that is a failure mode rather than a source of accuracy. So for a coalition the reachable
ceiling is the rate at which *at least one* member answers correctly — a perfect governance rule
finds that answer, and no rule can beat it without new information — and the baseline any rule
has to beat is the strongest single member. The difference between them is the entire accuracy
budget available to expert selection, aggregation, debate, veto and chair combined.

If that budget is smaller than the effect the gate asks for, the gate is unreachable on this pool
by arithmetic, and no amount of extra tasks or extra protocols changes it. Discovering that from
the bank costs nothing; discovering it from a priced Stage B costs the whole Stage B.

The check also localizes *why*. Headroom is created by members whose errors decorrelate at
comparable competence and destroyed by one member dominating, so the report contrasts coalitions
containing the strongest agent against those without it. On ``hard366-a`` the grand coalition had
4.37pp of headroom against an 8pp threshold, while dropping the dominant member raised it to
9.56pp — the pool, not the suite, was the constraint.

    python -m mas_harness.analysis.headroom --run-id hard366-a --gate-pp 8
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

from .. import config
from ..records.schema import AnswerRecord
from ..records.writer import RunDirectory

# The gate's protocol-spread threshold, in percentage points. Kept as a default rather than
# imported from gonogo so that a pool can be screened against a different bar deliberately.
DEFAULT_GATE_PP = 8.0


@dataclass
class CoalitionHeadroom:
    """The accuracy budget available to governance on one coalition."""

    agent_ids: list[int]
    agent_names: list[str]
    size: int
    ceiling: float
    best_member: float
    best_member_name: str
    worst_member: float
    contains_dominant: bool

    @property
    def headroom(self) -> float:
        """Ceiling minus the strongest member: all the accuracy governance can win."""
        return self.ceiling - self.best_member

    @property
    def competence_spread(self) -> float:
        return self.best_member - self.worst_member

    def clears(self, gate_pp: float) -> bool:
        return self.headroom * 100 >= gate_pp

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["headroom"] = self.headroom
        d["headroom_pp"] = self.headroom * 100
        d["competence_spread_pp"] = self.competence_spread * 100
        return d


def committed_correct(record: AnswerRecord) -> bool:
    """Whether this record supplies a correct answer a protocol could actually read.

    An unfinished or unparseable response is an abstention (D-011, D-019), so it cannot be the
    answer a perfect governance rule picks up. Counting it would credit the pool with information
    no protocol could read. Shared with the pool selector so the two cannot disagree about what
    counts as an answer.
    """
    return bool(record.correct and not record.parse_failed and record.extracted_answer)


def correctness_matrix(
    answers: Iterable[AnswerRecord],
    *,
    key: Callable[[AnswerRecord], Any] = lambda r: r.agent_id,
    seed: int = 0,
) -> dict[str, dict[Any, bool]]:
    """Per task, whether each agent committed to a correct answer.

    ``key`` selects how agents are identified. Within one pool the numeric id is right; across
    pools it must be the name, because ids are pool-local and would silently collide.
    """
    correct: dict[str, dict[Any, bool]] = {}
    for record in answers:
        if record.seed != seed:
            continue
        correct.setdefault(record.task_id, {})[key(record)] = committed_correct(record)
    return correct


def error_correlation(
    correct: Mapping[str, Mapping[Any, bool]], keys: Sequence[Any]
) -> dict[tuple[Any, Any], float]:
    """Pairwise correlation of per-task correctness vectors.

    Computed on correctness rather than on error, which gives the same coefficient and avoids a
    sign confusion. A constant vector — an agent right on everything or nothing — has no variance
    and no defined correlation, reported as 0.0 so it neither helps nor penalizes a subset.

    Lives here rather than in the pool selector because headroom *is* decorrelation expressed as
    accuracy, and the two must be measured off the same matrix or they can disagree.
    """
    tasks = sorted(correct)
    vectors = {k: np.array([float(correct[t][k]) for t in tasks]) for k in keys}
    out: dict[tuple[Any, Any], float] = {}
    for first, second in combinations(keys, 2):
        a, b = vectors[first], vectors[second]
        if a.std() == 0 or b.std() == 0:
            out[(first, second)] = 0.0
        else:
            out[(first, second)] = float(np.corrcoef(a, b)[0, 1])
    return out


def analyze(answers: Sequence[AnswerRecord]) -> dict[str, Any]:
    """Headroom for every coalition of size two or more, plus the dominance diagnosis."""
    correct = correctness_matrix(answers)
    tasks = sorted(correct)
    if not tasks:
        raise ValueError("no seed-0 answers in the bank")

    names = {r.agent_id: r.agent_name for r in answers}
    agent_ids = sorted(names)
    # Restrict to tasks every agent attempted, so a coalition's ceiling and its members'
    # accuracies are measured on the same denominator.
    complete = [t for t in tasks if len(correct[t]) == len(agent_ids)]
    if not complete:
        raise ValueError("no task has an answer from every agent")

    solo = {
        agent_id: sum(correct[t][agent_id] for t in complete) / len(complete)
        for agent_id in agent_ids
    }
    dominant = max(solo, key=solo.get)
    ranked = sorted(solo.values(), reverse=True)

    rows: list[CoalitionHeadroom] = []
    for size in range(2, len(agent_ids) + 1):
        for combo in combinations(agent_ids, size):
            ceiling = sum(
                any(correct[t][a] for a in combo) for t in complete
            ) / len(complete)
            rows.append(
                CoalitionHeadroom(
                    agent_ids=list(combo),
                    agent_names=[names[a] for a in combo],
                    size=size,
                    ceiling=ceiling,
                    best_member=max(solo[a] for a in combo),
                    best_member_name=names[max(combo, key=lambda a: solo[a])],
                    worst_member=min(solo[a] for a in combo),
                    contains_dominant=dominant in combo,
                )
            )

    grand = next(r for r in rows if r.size == len(agent_ids))
    with_dominant = [r for r in rows if r.contains_dominant]
    without = [r for r in rows if not r.contains_dominant]

    restricted = {t: correct[t] for t in complete}
    corr = error_correlation(restricted, agent_ids)
    pairs = {f"{names[a]} / {names[b]}": v for (a, b), v in corr.items()}

    return {
        "n_tasks": len(complete),
        "n_tasks_in_bank": len(tasks),
        "individual_accuracy": {names[a]: solo[a] for a in agent_ids},
        "dominant_agent": names[dominant],
        # Headroom is decorrelation expressed as accuracy, so the correlation is what distinguishes
        # a pool that fails because one member dominates from one that fails because its members
        # are wrong about the same things. Those call for different remedies.
        "mean_error_correlation": float(np.mean(list(corr.values()))) if corr else 0.0,
        "max_error_correlation": float(np.max(list(corr.values()))) if corr else 0.0,
        "pairwise_error_correlation": pairs,
        # The gap to the runner-up is the single number that predicts whether aggregation can
        # beat deferral: a pool with one clearly best member has almost nothing to aggregate.
        "top1_minus_top2_pp": (ranked[0] - ranked[1]) * 100 if len(ranked) > 1 else 0.0,
        "competence_range_pp": (ranked[0] - ranked[-1]) * 100,
        "grand_coalition": grand.to_dict(),
        "coalitions": [r.to_dict() for r in sorted(rows, key=lambda r: (r.size, -r.headroom))],
        "mean_headroom_pp_with_dominant": (
            100 * sum(r.headroom for r in with_dominant) / len(with_dominant)
            if with_dominant
            else float("nan")
        ),
        "mean_headroom_pp_without_dominant": (
            100 * sum(r.headroom for r in without) / len(without)
            if without
            else float("nan")
        ),
    }


# Above this top-1-to-top-2 gap, one member is far enough ahead to be the explanation on its own.
# Matches the pool selector's dominance constraint so the two tools cannot disagree.
DOMINANCE_PP = 5.0
# Above this mean pairwise correlation, the members are wrong about the same things.
HIGH_CORRELATION = 0.5


def diagnose_shortfall(report: dict[str, Any], *, gate_pp: float) -> str:
    """Why a pool lacks headroom, distinguishing dominance from shared failure modes.

    The two causes are not interchangeable and D-023 exists because conflating them cost a run:
    a dominant member is fixed by replacing it, whereas members that err together are fixed only by
    finding a genuinely different lineage, and a pool can fail on correlation while being as
    competence-equal as the candidate slate allows.
    """
    grand_pp = report["grand_coalition"]["headroom_pp"]
    gap = report["top1_minus_top2_pp"]
    corr = report["mean_error_correlation"]
    budget = (
        f"every governance rule combined can win at most {grand_pp:.2f}pp, below the "
        f"{gate_pp:.0f}pp the gate asks for"
    )
    dominant = gap > DOMINANCE_PP
    correlated = corr >= HIGH_CORRELATION
    if dominant and correlated:
        return (
            f"{report['dominant_agent']} is {gap:.1f}pp above the next member *and* the members "
            f"err together at {corr:+.3f}; {budget}"
        )
    if dominant:
        return (
            f"{report['dominant_agent']} is {gap:.1f}pp above the next member; {budget}"
        )
    if correlated:
        return (
            f"the members are near-equal ({gap:.1f}pp from best to second) but err together at "
            f"{corr:+.3f}, so competence homogeneity is not the constraint; {budget}"
        )
    return (
        f"neither dominance ({gap:.1f}pp) nor correlation ({corr:+.3f}) is extreme, so the pool is "
        f"simply too accurate for much to be recoverable; {budget}"
    )


def verdict(report: dict[str, Any], *, gate_pp: float = DEFAULT_GATE_PP) -> dict[str, Any]:
    """Whether the pool can support the gate, and if not, which sub-coalition could."""
    grand_pp = report["grand_coalition"]["headroom_pp"]
    alternatives = [
        c
        for c in report["coalitions"]
        if c["headroom_pp"] >= gate_pp and c["size"] >= 2
    ]
    best = max(alternatives, key=lambda c: (c["size"], c["headroom_pp"]), default=None)
    return {
        "gate_pp": gate_pp,
        "grand_headroom_pp": grand_pp,
        "admissible": grand_pp >= gate_pp,
        "n_coalitions_clearing_gate": len(alternatives),
        "largest_clearing_coalition": best,
        "diagnosis": (
            "pool is admissible"
            if grand_pp >= gate_pp
            else diagnose_shortfall(report, gate_pp=gate_pp)
        ),
    }


def print_report(report: dict[str, Any], decision: dict[str, Any]) -> None:
    print(f"\nPool headroom — {report['n_tasks']} tasks with a full set of answers\n")
    print("  individual accuracy:")
    for name, accuracy in sorted(report["individual_accuracy"].items(), key=lambda kv: -kv[1]):
        mark = "  <- dominant" if name == report["dominant_agent"] else ""
        print(f"    {accuracy:.3f}  {name}{mark}")
    print(
        f"    top-1 minus top-2 {report['top1_minus_top2_pp']:.1f}pp, "
        f"full range {report['competence_range_pp']:.1f}pp"
    )
    print(
        f"    error correlation mean {report['mean_error_correlation']:+.3f}, "
        f"max {report['max_error_correlation']:+.3f}\n"
    )

    print(f"  {'coalition':<50}{'ceiling':>9}{'best':>8}{'headroom':>10}")
    print("  " + "-" * 77)
    for c in report["coalitions"]:
        label = ", ".join(c["agent_names"])
        flag = "  clears" if c["headroom_pp"] >= decision["gate_pp"] else ""
        print(
            f"  {label:<50}{c['ceiling'] * 100:8.2f}%{c['best_member'] * 100:7.2f}%"
            f"{c['headroom_pp']:9.2f}pp{flag}"
        )

    print(
        f"\n  mean headroom with the dominant agent   : "
        f"{report['mean_headroom_pp_with_dominant']:.2f}pp"
    )
    print(
        f"  mean headroom without it               : "
        f"{report['mean_headroom_pp_without_dominant']:.2f}pp"
    )

    status = "ADMISSIBLE" if decision["admissible"] else "NOT ADMISSIBLE"
    print(f"\n  [{status}] at a {decision['gate_pp']:.0f}pp gate")
    print(f"      {decision['diagnosis']}")
    if not decision["admissible"] and decision["largest_clearing_coalition"]:
        best = decision["largest_clearing_coalition"]
        print(
            f"      largest coalition that would clear it: "
            f"{', '.join(best['agent_names'])} at {best['headroom_pp']:.2f}pp"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a pool leaves enough accuracy for governance to win"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-root", default=str(config.RUNS_DIR))
    parser.add_argument(
        "--gate-pp",
        type=float,
        default=DEFAULT_GATE_PP,
        help="the protocol-spread effect the gate asks for, in percentage points",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    config.load_env()
    run = RunDirectory(Path(args.runs_root), args.run_id)
    report = analyze(run.load_answers())
    decision = verdict(report, gate_pp=args.gate_pp)
    print_report(report, decision)

    out = Path(args.out) if args.out else run.path / "headroom.json"
    out.write_text(json.dumps({"report": report, "verdict": decision}, indent=2) + "\n")
    print(f"\n  full report -> {out}\n")
    return 0 if decision["admissible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
