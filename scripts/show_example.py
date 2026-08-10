"""Print one real task as the two-stage design sees it: the bank, then every rule's verdict.

A teaching aid. Picks a task where the four banked answers disagree and the seven rules do not all
land in the same place, which is the case that makes the design's point: the answers were paid for
once and every rule is a different reading of the same four strings.
"""

from __future__ import annotations

import argparse

from mas_harness import config
from mas_harness.records.writer import RunDirectory

FREE = {"single_expert", "independent_majority"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="strong4-a")
    args = ap.parse_args()

    rd = RunDirectory(config.RUNS_DIR, args.run_id)

    bank: dict[str, list] = {}
    for a in rd.load_answers():
        bank.setdefault(a.task_id, []).append(a)

    episodes: dict[str, dict] = {}
    for e in rd.load_episodes():
        if e.intervention.kind == "none" and len(e.coalition) == 4:
            episodes.setdefault(e.task_id, {})[e.protocol_id] = e

    for task_id, records in bank.items():
        finals = episodes.get(task_id, {})
        distinct = {r.extracted_answer for r in records}
        if len(distinct) < 3 or len(finals) < 7:
            continue
        if len({e.final_answer for e in finals.values()}) < 2:
            continue

        print(f"TASK {task_id}   suite={records[0].suite}   truth={records[0].ground_truth}")
        print("\n  STAGE A — each model answers alone. Paid once, then cached forever.")
        for r in sorted(records, key=lambda r: r.agent_name):
            verdict = "correct" if r.correct else "wrong"
            answer = r.extracted_answer or "(abstained)"
            cost = r.call.provider_reported_cost_usd or r.call.cost_usd or 0.0
            print(f"    {r.agent_name:14s} -> {answer:11s} {verdict:8s}  ${cost:.5f}")

        print("\n  STAGE B — seven rules read those same four answers.")
        for protocol, episode in sorted(finals.items(), key=lambda kv: -kv[1].correct):
            verdict = "correct" if episode.correct else "wrong"
            answer = episode.final_answer or "(none)"
            tag = "FREE, replayed from disk" if protocol in FREE else f"{episode.n_calls} new calls"
            print(
                f"    {protocol:28s} -> {answer:11s} {verdict:8s}  "
                f"${episode.total_cost_usd:.5f}  {tag}"
            )
        return

    print("no task in this run has three distinct answers and a split verdict")


if __name__ == "__main__":
    main()
