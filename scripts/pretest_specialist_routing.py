"""Does reproducible per-domain specialisation exist at all? A free test before buying a pool.

D-029 found that four strong generalists on hard STEM produce exactly one reproducible fact: run
majority vote over the whole pool. The natural reading is that the pool was too homogeneous - four
generalists on three flavours of hard reasoning have nothing to route between - and that a
specialised pool on a heterogeneous suite would behave differently. Acting on that reading means
building new task adapters and paying for new Stage A banks.

It can be checked first, for nothing. `agent-psychometrics` ships a dense agent-by-task outcome
matrix for SWE-bench Verified: 134 systems by 500 instances, binary. The instances carry a natural
grouping in the repository they patch - astropy, django, sympy and so on - which demand visibly
different knowledge. And 134 independently built agent systems are far more heterogeneous than any
four-model pool.

So this is the specialist hypothesis under conditions much more favourable than the ones being
proposed. If reproducible per-repository winners exist here, specialisation-based routing is real
and a specialised pool is worth building. If even here the answer is one dominant system plus noise,
the problem is not pool composition and the money would be wasted.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from mas_harness.metrics.stability import winner_stability
from mas_harness.records.schema import EpisodeRecord

MATRIX = "agent-psychometrics/data/swebench_verified/responses.jsonl"
# Realistic pool sizes. The full 134 includes systems from 2023 that solve almost nothing, and a
# router would never consider them; the top slices are the honest test.
TOP_K = [8, 16, 32, None]
MIN_TASKS_PER_REPO = 12


def load():
    """subject -> task -> solved, keeping subjects that attempted every task."""
    rows = [json.loads(line) for line in Path(MATRIX).read_text().splitlines() if line.strip()]
    tasks = sorted({t for r in rows for t in r["responses"]})
    full = {
        r["subject_id"]: {t: bool(r["responses"][t]) for t in tasks}
        for r in rows
        if len(r["responses"]) == len(tasks)
    }
    # SWE-bench instance ids look like "astropy__astropy-12907"; the repository is the group.
    repo = {t: t.split("__")[0] for t in tasks}
    counts = defaultdict(int)
    for t in tasks:
        counts[repo[t]] += 1
    keep = {t: r for t, r in repo.items() if counts[r] >= MIN_TASKS_PER_REPO}
    return {s: {t: v for t, v in o.items() if t in keep} for s, o in full.items()}, keep


def episodes_from(outcomes, repo):
    """Present each system as a protocol so the existing metric applies unchanged."""
    return [
        EpisodeRecord(
            run_id="swebench_verified",
            task_id=task,
            suite="swebench_verified",
            domain=repo[task],
            pool_id="agent-psychometrics",
            protocol_id=subject,
            coalition=[0],
            seed=0,
            final_text="",
            final_answer="",
            ground_truth="",
            correct=solved,
            parse_failed=False,
        )
        for subject, tasks in outcomes.items()
        for task, solved in tasks.items()
    ]


def main() -> None:
    outcomes, repo = load()
    accuracy = {s: float(np.mean(list(o.values()))) for s, o in outcomes.items()}
    ranked = sorted(accuracy, key=lambda s: -accuracy[s])
    n_repos = len(set(repo.values()))
    print(f"{len(outcomes)} systems x {len(repo)} instances over {n_repos} repositories "
          f"(>= {MIN_TASKS_PER_REPO} instances each)")
    print(f"best system {ranked[0]} at {accuracy[ranked[0]]:.3f}, "
          f"median {np.median(list(accuracy.values())):.3f}")

    for k in TOP_K:
        subjects = ranked[:k] if k else ranked
        report = winner_stability(
            episodes_from({s: outcomes[s] for s in subjects}, repo),
            grouping="domain",
            n_splits=200,
            n_permutations=120,
        )
        print(f"\n=== top {k or 'all'} systems "
              f"({accuracy[subjects[-1]]:.3f} to {accuracy[subjects[0]]:.3f}) ===")
        print(f"  reproducibility {report.reproducibility:.3f}  "
              f"null {report.null_reproducibility:.3f}  p={report.reproducibility_p:.4f}")
        print(f"  dominance       {report.dominance*100:5.1f}%  "
              f"null {report.null_dominance*100:5.1f}%")
        print(f"  dominant system {report.dominant_configuration}")
        print(f"  reproducibility on it   {report.reproducibility_dominant:.3f} "
              f"({len(report.groups) - report.n_off_dominant} repos)")
        print(f"  reproducibility off it  {report.reproducibility_off_dominant:.3f} "
              f"({report.n_off_dominant} repos)  <- the routing signal")
        print(f"  {report.verdict}")


if __name__ == "__main__":
    main()
