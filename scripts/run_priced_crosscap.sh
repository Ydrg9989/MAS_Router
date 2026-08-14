#!/usr/bin/env bash
# The last purchase on this substrate: the five interaction protocols on `crosscap240`.
#
# Pre-registered in Docs/preregistrations/2026-08-13-judge-replication.md. D-042 left
# `independent_judge` as the one surviving positive claim, measured on `hard366` only — a suite
# D-038 showed carries no detectable interaction. This run supplies the second suite, on the one
# where interaction is real, and it is the only route from this substrate to a positive result.
#
# The aggregator prompt is deliberately NOT repaired (D-028's fix is deferred again on purpose):
# changing it would confound "replicates on a second suite" with "replicates under a better prompt".
# The ~4% non-termination handicap therefore applies equally to both suites, which leaves the
# judge's advantage a conservative floor on each.
set -euo pipefail
cd "$(dirname "$0")/.."

PROTOCOLS="independent_judge expert_verifier debate_vote expert_veto chair_information_seeking"

for pair in strong4:crosscap-strong4 decorrelated4:crosscap-decorr4 correlated4:crosscap-corr4; do
    pool="${pair%%:*}"
    run="${pair##*:}"
    echo "############ ${run} ############"
    date -Is
    .venv/bin/python -m mas_harness.runners.episodes \
        --manifest data/manifests/crosscap240.json \
        --pool "configs/pools/${pool}.yaml" \
        --run-id "${run}" \
        --protocols ${PROTOCOLS} \
        --coalitions grand \
        --interventions none \
        --tasks-from "data/runs/${run}/discrimination.json" \
        --concurrency 10
    echo "DONE ${run}"
    date -Is
done
echo "ALL CROSSCAP PRICED RUNS COMPLETE"
