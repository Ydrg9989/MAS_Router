"""Choose a pool from measured candidates, on the criteria D-021 makes preconditions.

The governance experiment needs a pool whose members leave room for a governance rule to matter.
`headroom.py` says whether a *given* pool does; this says which pool to build out of the models
that have been measured. It reads several Stage-A banks at once, keyed on agent name because ids
are pool-local, restricts them to the tasks all candidates attempted, and scores every subset of
the requested size.

Three quantities decide it, and they are not interchangeable:

**Headroom.** ``P(at least one member correct) - max member accuracy``. The entire accuracy budget
available to expert selection, aggregation, debate, veto and chair combined. This is the objective.

**Dominance gap.** Best member minus second best. The diagnostic from `hard366-a`: an 8.7pp gap
collapsed headroom to 4.37pp, and coalitions without the dominant member averaged 9.84pp. A
constraint rather than an objective, because a pool can have adequate headroom and still be
uninteresting if one member supplies all of it — the governance rules would then be competing to
rediscover "ask the strong one".

**Error correlation.** Mean pairwise correlation of the per-task correctness vectors. Headroom
*is* decorrelation made concrete, so this mostly restates it, and it earns its place for the one
case where the two come apart: members of similar accuracy whose errors coincide give low headroom
for a reason that accuracy alone does not reveal, and knowing which of the two is happening
changes whether the fix is a different model or a different band.

The order matters. Maximizing headroom alone would pick the weakest available members, since a pool
of near-chance agents has enormous headroom and no scientific interest — a rule that recovers a
correct answer nobody could reliably produce is not a governance finding. So the selector reports
the frontier rather than a single winner, and the floor on the best member's accuracy is an
explicit argument.

    python -m mas_harness.analysis.pool_select --runs hard366-a screen-a --size 4 \
        --pools configs/pools/openrouter4.yaml configs/pools/candidates.yaml
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

from .. import config
from ..pool.agents import AgentPool
from ..records.schema import AnswerRecord
from ..records.writer import RunDirectory
from .headroom import correctness_matrix, error_correlation

# Defaults are the gate's own numbers where one exists, and stated reasoning where it does not.
DEFAULT_GATE_PP = 8.0
# Above this, one member is doing the work and the pool reproduces the hard366-a problem.
DEFAULT_MAX_DOMINANCE_PP = 5.0
# Below this, the pool is too weak for a recovered answer to be an interesting recovery.
DEFAULT_MIN_BEST_ACCURACY = 0.55
# Below this share of readable responses an agent is a broken instrument, not a peer. Set at the
# level that separates the measured candidates cleanly: seven sit at or above 0.98, and the three
# below it are at 0.76, 0.65 and 0.60.
DEFAULT_MIN_COMMIT_RATE = 0.95


@dataclass
class Candidate:
    """One subset of the measured agents, scored on the D-021 criteria."""

    names: list[str]
    accuracies: list[float]
    ceiling: float
    best: float
    worst: float
    headroom_pp: float
    dominance_gap_pp: float
    competence_spread_pp: float
    mean_error_correlation: float
    max_error_correlation: float
    families: list[str]
    n_families: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def admissible(
        self,
        *,
        gate_pp: float,
        max_dominance_pp: float,
        min_best_accuracy: float,
    ) -> bool:
        return (
            self.headroom_pp >= gate_pp
            and self.dominance_gap_pp <= max_dominance_pp
            and self.best >= min_best_accuracy
        )


def declared_families(pool_paths: Sequence[str | Path]) -> dict[str, str]:
    """Agent name to declared family, read from pool YAML.

    Family is a pool-level declaration and is not written into `AnswerRecord`, so it has to come
    from the configs that produced the banks. It cannot be inferred from the slug:
    `openai/gpt-5-mini` and `openai/gpt-oss-120b` share a vendor and not a lineage, and lineage
    is what the ranking treats as a confound.
    """
    out: dict[str, str] = {}
    for path in pool_paths:
        pool = AgentPool.from_yaml(path)
        for agent in pool.agents:
            out[agent.name] = agent.family
    return out


def read_banks(run_ids: Sequence[str], runs_root: Path) -> list[AnswerRecord]:
    """Every Stage-A record from the named runs, concatenated."""
    out: list[AnswerRecord] = []
    for run_id in run_ids:
        answers = RunDirectory(runs_root, run_id).load_answers()
        if not answers:
            raise FileNotFoundError(f"no answers in run {run_id!r}")
        out.extend(answers)
    return out


def commit_rates(answers: Iterable[AnswerRecord]) -> dict[str, float]:
    """Per agent, the fraction of responses that yielded a readable answer at all.

    Distinct from accuracy and not a competence measure. An agent that truncates or emits
    unparseable text abstains (D-011, D-019), and abstentions look exactly like decorrelated errors
    to `headroom`: they are wrong, and they are wrong on different items than a working agent's
    mistakes. So a broken instrument inflates the very quantity the selector maximizes, and the
    resulting pool would promise governance headroom that is really missing data.
    """
    seen: dict[str, int] = {}
    committed: dict[str, int] = {}
    for record in answers:
        seen[record.agent_name] = seen.get(record.agent_name, 0) + 1
        if not record.parse_failed and record.extracted_answer:
            committed[record.agent_name] = committed.get(record.agent_name, 0) + 1
    return {name: committed.get(name, 0) / total for name, total in seen.items()}


def load_banks(
    run_ids: Sequence[str],
    runs_root: Path,
    *,
    families: Mapping[str, str] | None = None,
    exclude: Iterable[str] = (),
) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    """Merge several Stage-A banks into one task-by-name correctness matrix.

    Restricted to the tasks every agent attempted. A candidate measured on a different task set
    would otherwise be compared on a different denominator, and since the screen deliberately
    covers a subset of the main suite, that intersection is the whole point.

    Any agent absent from `families` falls back to the vendor prefix of its model slug, which
    under-splits lineage but never invents a distinction that is not there.
    """
    declared = dict(families or {})
    dropped = set(exclude)
    kept = [r for r in read_banks(run_ids, runs_root) if r.agent_name not in dropped]
    resolved: dict[str, str] = {}
    for record in kept:
        resolved.setdefault(
            record.agent_name,
            declared.get(record.agent_name) or record.model.split("/")[0],
        )

    names = sorted(resolved)
    merged = correctness_matrix(kept, key=lambda r: r.agent_name)
    complete = {t: row for t, row in merged.items() if len(row) == len(names)}
    if not complete:
        counts = {t: len(row) for t, row in merged.items()}
        best = max(counts.values()) if counts else 0
        raise ValueError(
            f"no task has an answer from all {len(names)} agents "
            f"({sorted(names)}); the best-covered task has {best}"
        )
    return complete, resolved


def score_subsets(
    correct: Mapping[str, Mapping[str, bool]],
    families: Mapping[str, str],
    *,
    size: int,
) -> list[Candidate]:
    """Every subset of the given size, scored. No filtering; the caller applies the criteria."""
    names = sorted(families)
    if size > len(names):
        raise ValueError(f"asked for pools of {size} from only {len(names)} measured agents")
    tasks = sorted(correct)
    n = len(tasks)
    solo = {name: sum(correct[t][name] for t in tasks) / n for name in names}
    corr = error_correlation(correct, names)

    out: list[Candidate] = []
    for combo in combinations(names, size):
        ceiling = sum(any(correct[t][m] for m in combo) for t in tasks) / n
        ranked = sorted((solo[m] for m in combo), reverse=True)
        pairs = [
            corr[(a, b)] if (a, b) in corr else corr[(b, a)]
            for a, b in combinations(combo, 2)
        ]
        fams = [families[m] for m in combo]
        out.append(
            Candidate(
                names=list(combo),
                accuracies=[round(solo[m], 4) for m in combo],
                ceiling=ceiling,
                best=ranked[0],
                worst=ranked[-1],
                headroom_pp=(ceiling - ranked[0]) * 100,
                dominance_gap_pp=(ranked[0] - ranked[1]) * 100,
                competence_spread_pp=(ranked[0] - ranked[-1]) * 100,
                mean_error_correlation=float(np.mean(pairs)),
                max_error_correlation=float(np.max(pairs)),
                families=fams,
                n_families=len(set(fams)),
            )
        )
    return out


def select(
    candidates: Sequence[Candidate],
    *,
    gate_pp: float = DEFAULT_GATE_PP,
    max_dominance_pp: float = DEFAULT_MAX_DOMINANCE_PP,
    min_best_accuracy: float = DEFAULT_MIN_BEST_ACCURACY,
) -> dict[str, Any]:
    """Admissible subsets, ranked, plus which criterion eliminated the rest.

    Reporting the binding criterion is the useful part when nothing qualifies: "no subset had
    enough headroom" and "every subset with enough headroom was too weak to be interesting" call
    for different remedies, and the counts distinguish them.
    """
    admissible = [
        c
        for c in candidates
        if c.admissible(
            gate_pp=gate_pp,
            max_dominance_pp=max_dominance_pp,
            min_best_accuracy=min_best_accuracy,
        )
    ]
    # Prefer distinct families, then headroom. Family count first because shared lineage is a
    # confound rather than a quantity to trade off against effect size.
    ranked = sorted(admissible, key=lambda c: (-c.n_families, -c.headroom_pp))
    return {
        "criteria": {
            "gate_pp": gate_pp,
            "max_dominance_pp": max_dominance_pp,
            "min_best_accuracy": min_best_accuracy,
        },
        "n_scored": len(candidates),
        "n_admissible": len(admissible),
        "failed_headroom": sum(1 for c in candidates if c.headroom_pp < gate_pp),
        "failed_dominance": sum(
            1 for c in candidates if c.dominance_gap_pp > max_dominance_pp
        ),
        "failed_too_weak": sum(1 for c in candidates if c.best < min_best_accuracy),
        "recommended": ranked[0].to_dict() if ranked else None,
        "admissible": [c.to_dict() for c in ranked],
    }


def print_report(
    correct: Mapping[str, Mapping[str, bool]],
    families: Mapping[str, str],
    candidates: Sequence[Candidate],
    decision: dict[str, Any],
    *,
    rates: Mapping[str, float] | None = None,
    excluded: Mapping[str, float] | None = None,
    top: int = 12,
) -> None:
    tasks = sorted(correct)
    names = sorted(families)
    solo = {m: sum(correct[t][m] for t in tasks) / len(tasks) for m in names}

    if excluded:
        print("\n  excluded as unreliable instruments (readable-response rate):")
        for name, rate in sorted(excluded.items(), key=lambda kv: kv[1]):
            print(f"    {rate:.3f}  {name}")

    print(f"\nPool selection — {len(names)} measured agents on {len(tasks)} shared tasks\n")
    print("  measured accuracy:")
    for name, accuracy in sorted(solo.items(), key=lambda kv: -kv[1]):
        commit = f"  commit {rates[name]:.3f}" if rates and name in rates else ""
        print(f"    {accuracy:.3f}  {name:<20} ({families[name]}){commit}")

    corr = error_correlation(correct, names)
    print("\n  most correlated pairs (shared failure modes):")
    for (a, b), value in sorted(corr.items(), key=lambda kv: -kv[1])[:5]:
        print(f"    {value:+.3f}  {a} / {b}")
    print("  least correlated pairs (complementary):")
    for (a, b), value in sorted(corr.items(), key=lambda kv: kv[1])[:5]:
        print(f"    {value:+.3f}  {a} / {b}")

    criteria = decision["criteria"]
    print(
        f"\n  criteria: headroom >= {criteria['gate_pp']:.0f}pp, "
        f"dominance gap <= {criteria['max_dominance_pp']:.0f}pp, "
        f"best member >= {criteria['min_best_accuracy']:.2f}"
    )
    print(
        f"  of {decision['n_scored']} subsets: {decision['n_admissible']} admissible "
        f"({decision['failed_headroom']} lacked headroom, "
        f"{decision['failed_dominance']} had a dominant member, "
        f"{decision['failed_too_weak']} too weak)"
    )

    print(f"\n  {'pool':<52}{'head':>7}{'dom':>7}{'corr':>7}{'fams':>6}")
    print("  " + "-" * 79)
    ordered = sorted(candidates, key=lambda c: -c.headroom_pp)[:top]
    for c in ordered:
        ok = c.admissible(
            gate_pp=criteria["gate_pp"],
            max_dominance_pp=criteria["max_dominance_pp"],
            min_best_accuracy=criteria["min_best_accuracy"],
        )
        label = ", ".join(c.names)
        if len(label) > 50:
            label = label[:47] + "..."
        print(
            f"  {label:<52}{c.headroom_pp:6.2f}p{c.dominance_gap_pp:6.2f}p"
            f"{c.mean_error_correlation:+7.3f}{c.n_families:6d}"
            f"{'  <-' if ok else ''}"
        )

    best = decision["recommended"]
    if best is None:
        print("\n  NOTHING QUALIFIES on these criteria. Loosen one explicitly, or measure more"
              " candidates; do not pick the least-bad subset silently.")
        return
    print(f"\n  RECOMMENDED: {', '.join(best['names'])}")
    print(f"      accuracies      : {best['accuracies']}")
    print(f"      ceiling         : {best['ceiling'] * 100:.2f}%")
    print(f"      headroom        : {best['headroom_pp']:.2f}pp")
    print(f"      dominance gap   : {best['dominance_gap_pp']:.2f}pp")
    print(f"      error corr      : mean {best['mean_error_correlation']:+.3f}, "
          f"max {best['max_error_correlation']:+.3f}")
    print(f"      families        : {best['families']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pick a comparable-competence pool from measured Stage-A banks"
    )
    parser.add_argument("--runs", nargs="+", required=True, help="run ids to merge")
    parser.add_argument(
        "--pools",
        nargs="*",
        default=[],
        help="pool YAML that produced these banks, for declared families",
    )
    parser.add_argument("--runs-root", default=str(config.RUNS_DIR))
    parser.add_argument("--size", type=int, default=4)
    parser.add_argument("--gate-pp", type=float, default=DEFAULT_GATE_PP)
    parser.add_argument("--max-dominance-pp", type=float, default=DEFAULT_MAX_DOMINANCE_PP)
    parser.add_argument("--min-best-accuracy", type=float, default=DEFAULT_MIN_BEST_ACCURACY)
    parser.add_argument(
        "--min-commit-rate",
        type=float,
        default=DEFAULT_MIN_COMMIT_RATE,
        help="drop agents whose responses are readable less often than this",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    config.load_env()
    runs_root = Path(args.runs_root)
    rates = commit_rates(read_banks(args.runs, runs_root))
    excluded = {n: r for n, r in rates.items() if r < args.min_commit_rate}
    correct, families = load_banks(
        args.runs,
        runs_root,
        families=declared_families(args.pools),
        exclude=excluded,
    )
    candidates = score_subsets(correct, families, size=args.size)
    decision = select(
        candidates,
        gate_pp=args.gate_pp,
        max_dominance_pp=args.max_dominance_pp,
        min_best_accuracy=args.min_best_accuracy,
    )
    print_report(correct, families, candidates, decision, rates=rates, excluded=excluded)

    payload = {
        "runs": list(args.runs),
        "n_tasks": len(correct),
        "agents": {name: families[name] for name in sorted(families)},
        "commit_rates": rates,
        "excluded_unreliable": excluded,
        "min_commit_rate": args.min_commit_rate,
        "decision": decision,
        "all_subsets": [c.to_dict() for c in candidates],
    }
    out = Path(args.out) if args.out else config.RUNS_DIR / "pool_selection.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  full report -> {out}\n")
    return 0 if decision["recommended"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
