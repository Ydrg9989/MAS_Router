#!/usr/bin/env bash
# `independent_judge` on the tasks D-020 never priced: those where all four members agreed.
#
# Pre-registered in Docs/preregistrations/2026-08-14-judge-on-easy-tasks.md. Three pools run
# concurrently rather than in series — 245 episodes total, so the wall clock is dominated by
# latency rather than by any rate limit, and each writes to its own run directory.
set -euo pipefail
cd "$(dirname "$0")/.."

pids=()
for pair in strong4:crosscap-strong4 decorrelated4:crosscap-decorr4 correlated4:crosscap-corr4; do
    pool="${pair%%:*}"; run="${pair##*:}"
    (
      .venv/bin/python -m mas_harness.runners.episodes \
        --manifest data/manifests/crosscap240.json \
        --pool "configs/pools/${pool}.yaml" \
        --run-id "${run}" \
        --protocols independent_judge \
        --coalitions grand --interventions none \
        --tasks-from "data/runs/${run}/skipped_tasks.json" \
        --concurrency 8 > "logs/judge-skipped-${run}.log" 2>&1
      echo "DONE ${run}"
    ) &
    pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done
echo "ALL SKIPPED-TASK JUDGE RUNS COMPLETE"
