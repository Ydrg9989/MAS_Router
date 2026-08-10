"""Which tasks can distinguish protocols at all, and which are dead weight.

The pilot9-b run exposed a problem that no amount of extra sampling would have fixed. Of nine
tasks, seven had all four agents independently give the same correct answer. On such a task
every protocol returns that answer for a structural reason: debate has nothing to revise, a
judge has nothing to choose between, a veto has nothing to challenge. The task contributes a
concordant pair to every comparison and therefore contributes exactly nothing to a McNemar
test, which reads only discordant pairs.

The consequence is a hard ceiling that is easy to miss when planning. The spread between the
best and worst protocol cannot exceed the fraction of tasks on which the agents disagree. Aim
at an 8-point effect on a suite where agents disagree on 11% of tasks and the experiment is
arithmetically unable to find it, however many tasks are added and however real the phenomenon
is. The gate would then return NO GO for the governance direction on evidence that never had
the capacity to say otherwise.

This module classifies each task by what protocols could possibly do with it, using only the
Stage-A answer bank — so it costs nothing and runs before any protocol is priced. The classes
are ordered by how much they can teach:

``MINORITY_CORRECT``
    A minority of agents is right. Plurality voting fails here by construction while deferring
    to the right expert succeeds, so this is the only class in which correct-answer dilution
    can be observed at all. The scarcest and most valuable class.
``TIE``
    Correct and incorrect answers are evenly split, so the outcome turns entirely on the
    tie-break rule. Discriminating, and the class where aggregation design matters most.
``MAJORITY_CORRECT``
    The majority is right, so voting already succeeds. Protocols can still differ — an
    interactive protocol can talk itself out of a correct majority, which is the *rescue*
    phenomenon's mirror image — but the vote baseline is hard to beat.
``UNANIMOUS_WRONG``
    Everyone is wrong and agrees. No protocol that only reads these answers can recover; the
    information is simply absent from the pool. Useful only as an accuracy denominator.
``UNANIMOUS_CORRECT``
    Everyone is right and agrees. Costs money to run and cannot produce a discordant pair.

A caveat that keeps this honest: unanimity makes protocols *nearly* rather than strictly
identical. An interactive protocol can still talk a unanimous group out of a correct answer,
and a judge is free to write an answer nobody proposed. Those events are the reason
``sample_fraction`` exists in :func:`select_for_stage_b` rather than dropping unanimous tasks
outright — the drift rate is an empirical question, and assuming it is zero would be assuming
away a real failure mode.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .. import config
from ..records.schema import AnswerRecord
from ..records.writer import RunDirectory
from ..tasks.manifest import Manifest
from ..tasks.splits import stratified_subset

MINORITY_CORRECT = "MINORITY_CORRECT"
TIE = "TIE"
MAJORITY_CORRECT = "MAJORITY_CORRECT"
UNANIMOUS_WRONG = "UNANIMOUS_WRONG"
UNANIMOUS_CORRECT = "UNANIMOUS_CORRECT"

# Ordered by how much a task of each class can teach, most informative first.
CLASS_ORDER = (MINORITY_CORRECT, TIE, MAJORITY_CORRECT, UNANIMOUS_WRONG, UNANIMOUS_CORRECT)

# Classes on which at least two protocols can return different answers.
DISCRIMINATING = frozenset({MINORITY_CORRECT, TIE, MAJORITY_CORRECT})

# Classes on which deferring to a correct expert beats a plurality vote.
DILUTION_ELIGIBLE = frozenset({MINORITY_CORRECT, TIE})


@dataclass
class TaskDiagnosis:
    """What the answer bank says one task can and cannot distinguish."""

    task_id: str
    suite: str
    domain: str
    n_agents: int
    n_correct: int
    n_abstained: int
    n_distinct_answers: int
    task_class: str
    correct_agents: list[str] = field(default_factory=list)

    @property
    def discriminating(self) -> bool:
        """Whether two protocols could return different answers on this task."""
        return self.task_class in DISCRIMINATING and self.n_distinct_answers > 1

    @property
    def dilution_eligible(self) -> bool:
        """Whether a correct expert could be outvoted here."""
        return self.task_class in DILUTION_ELIGIBLE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["discriminating"] = self.discriminating
        d["dilution_eligible"] = self.dilution_eligible
        return d


def classify_task(records: Sequence[AnswerRecord]) -> str:
    """Assign one task to a discrimination class from its independent answers.

    Abstentions are excluded from the correct/incorrect tally rather than counted as wrong.
    An agent that produced no extractable answer did not cast a vote, and treating silence as
    a wrong vote would manufacture exactly the minority-correct cases this module exists to
    find (D-011).
    """
    voting = [r for r in records if not r.parse_failed and r.extracted_answer]
    if not voting:
        return UNANIMOUS_WRONG

    n_correct = sum(1 for r in voting if r.correct)
    n_voting = len(voting)
    distinct = len({r.extracted_answer for r in voting})

    if n_correct == 0:
        return UNANIMOUS_WRONG
    if n_correct == n_voting and distinct == 1:
        return UNANIMOUS_CORRECT
    if n_correct * 2 > n_voting:
        return MAJORITY_CORRECT
    if n_correct * 2 == n_voting:
        return TIE
    return MINORITY_CORRECT


def diagnose(answers: Iterable[AnswerRecord]) -> list[TaskDiagnosis]:
    """Classify every task represented in a Stage-A answer bank.

    Answers are grouped by task and seed 0 only. Extra seeds measure within-agent variance,
    which is a different question from whether the agents disagree with each other, and mixing
    them would inflate the apparent disagreement.
    """
    by_task: dict[str, list[AnswerRecord]] = defaultdict(list)
    for record in answers:
        if record.seed == 0:
            by_task[record.task_id].append(record)

    out: list[TaskDiagnosis] = []
    for task_id, records in sorted(by_task.items()):
        voting = [r for r in records if not r.parse_failed and r.extracted_answer]
        out.append(
            TaskDiagnosis(
                task_id=task_id,
                suite=records[0].suite,
                domain=records[0].domain,
                n_agents=len(records),
                n_correct=sum(1 for r in records if r.correct),
                n_abstained=len(records) - len(voting),
                n_distinct_answers=len({r.extracted_answer for r in voting}),
                task_class=classify_task(records),
                correct_agents=sorted(r.agent_name for r in records if r.correct),
            )
        )
    return out


def summarize(diagnoses: Sequence[TaskDiagnosis]) -> dict[str, Any]:
    """Aggregate rates overall and by suite, plus the implied ceiling on protocol spread."""
    n = len(diagnoses)
    if n == 0:
        return {"n_tasks": 0}

    by_class = Counter(d.task_class for d in diagnoses)
    discriminating = [d for d in diagnoses if d.discriminating]
    eligible = [d for d in diagnoses if d.dilution_eligible]

    per_suite: dict[str, Any] = {}
    for suite in sorted({d.suite for d in diagnoses}):
        subset = [d for d in diagnoses if d.suite == suite]
        n_sub = len(subset)
        per_suite[suite] = {
            "n_tasks": n_sub,
            "mean_agent_accuracy": sum(d.n_correct for d in subset)
            / sum(d.n_agents for d in subset),
            "classes": dict(Counter(d.task_class for d in subset)),
            "discriminating_frac": sum(1 for d in subset if d.discriminating) / n_sub,
            "dilution_eligible_frac": sum(1 for d in subset if d.dilution_eligible) / n_sub,
        }

    return {
        "n_tasks": n,
        "classes": {c: by_class.get(c, 0) for c in CLASS_ORDER},
        "class_fractions": {c: by_class.get(c, 0) / n for c in CLASS_ORDER},
        "discriminating_frac": len(discriminating) / n,
        "dilution_eligible_frac": len(eligible) / n,
        # The headline planning number: no protocol can beat another by more than this, because
        # every other task returns the same answer under every protocol.
        "max_possible_protocol_spread_pp": 100.0 * len(discriminating) / n,
        "mean_agent_accuracy": sum(d.n_correct for d in diagnoses)
        / sum(d.n_agents for d in diagnoses),
        "by_suite": per_suite,
    }


def select_for_stage_b(
    diagnoses: Sequence[TaskDiagnosis],
    *,
    sample_fraction: float = 0.15,
    seed: int = 0,
) -> dict[str, list[str]]:
    """Split tasks into those Stage B must run and a control sample of the rest.

    Every discriminating task is kept, because those are the only ones that can produce a
    discordant pair. Non-discriminating tasks are *sampled* rather than dropped, for a reason
    worth stating plainly: the claim that a unanimous group cannot be talked out of its answer
    is an assumption, and this sample is what tests it. If drift turns out to be common the
    sample becomes the finding; if it is absent, the sample justifies extrapolating the
    unanimous tasks' outcome from Stage A alone and the full-population accuracy follows
    without paying for them.
    """
    keep = [d for d in diagnoses if d.discriminating]
    rest = [d for d in diagnoses if not d.discriminating]

    control: list[TaskDiagnosis] = []
    if rest and sample_fraction > 0:
        # Stratify on suite crossed with class, so the control sample cannot end up made
        # entirely of unanimous-correct tasks and miss the all-wrong ones, whose drift is the
        # more interesting direction: a group that agrees on a wrong answer is exactly where a
        # protocol might plausibly rescue one.
        chosen = set(
            stratified_subset(
                [(d.task_id, f"{d.suite}/{d.task_class}") for d in rest],
                fraction=min(1.0, sample_fraction),
                seed=seed,
            )
        )
        control = [d for d in rest if d.task_id in chosen]

    return {
        "stage_b_tasks": sorted(d.task_id for d in keep),
        "control_tasks": sorted(d.task_id for d in control),
        "skipped_tasks": sorted(
            d.task_id for d in rest if d.task_id not in {c.task_id for c in control}
        ),
    }


def _print_report(summary: dict[str, Any], selection: dict[str, list[str]]) -> None:
    n = summary["n_tasks"]
    print(f"\nDiscrimination analysis — {n} tasks, mean agent accuracy "
          f"{summary['mean_agent_accuracy']:.3f}\n")

    print("  task classes:")
    for cls in CLASS_ORDER:
        count = summary["classes"][cls]
        frac = summary["class_fractions"][cls]
        marker = "  <- dilution observable here" if cls in DILUTION_ELIGIBLE and count else ""
        print(f"    {cls:<20} {count:>5}  ({frac:6.1%}){marker}")

    print(f"\n  discriminating           : {summary['discriminating_frac']:6.1%}"
          "  (protocols can differ)")
    print(f"  dilution eligible        : {summary['dilution_eligible_frac']:6.1%}"
          "  (a correct expert can be outvoted)")
    print(f"  CEILING on protocol spread: {summary['max_possible_protocol_spread_pp']:5.1f}pp"
          "  (gate needs 8pp)")

    print("\n  by suite:")
    for suite, s in summary["by_suite"].items():
        flag = "  SATURATED" if s["mean_agent_accuracy"] >= 0.95 else ""
        print(f"    {suite:<16} n={s['n_tasks']:<5} acc={s['mean_agent_accuracy']:.3f} "
              f"discriminating={s['discriminating_frac']:6.1%}{flag}")

    print(f"\n  Stage B plan: {len(selection['stage_b_tasks'])} discriminating tasks + "
          f"{len(selection['control_tasks'])} control, "
          f"{len(selection['skipped_tasks'])} skipped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify tasks by whether any protocol could distinguish them"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--runs-root", default=str(config.RUNS_DIR))
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=0.15,
        help="share of non-discriminating tasks kept as a drift control",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=None, help="write the selection JSON here")
    args = parser.parse_args(argv)

    config.load_env()
    Manifest.read(args.manifest)  # read for its side effect: fail early on a bad path
    run = RunDirectory(Path(args.runs_root), args.run_id)
    diagnoses = diagnose(run.load_answers())
    summary = summarize(diagnoses)
    selection = select_for_stage_b(
        diagnoses, sample_fraction=args.sample_fraction, seed=args.seed
    )
    _print_report(summary, selection)

    payload = {
        "run_id": args.run_id,
        "manifest": args.manifest,
        "summary": summary,
        "selection": selection,
        "tasks": [d.to_dict() for d in diagnoses],
    }
    out = Path(args.out) if args.out else run.path / "discrimination.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  full report -> {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
