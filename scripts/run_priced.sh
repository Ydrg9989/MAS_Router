#!/usr/bin/env bash
# The one irreducibly paid step: five protocols that transform answers rather than just select
# among them, on the tasks where the free protocols showed the pool can discriminate.
#
# Treatment and control are matched at single_expert 0.8989 and differ in error correlation
# (+0.408 against +0.579), so a governance effect present in one and absent in the other is
# attributable to decorrelation and not to competence (D-025).
set -euo pipefail
cd "$(dirname "$0")/.."

PROTOCOLS="independent_judge expert_verifier debate_vote expert_veto chair_information_seeking"

for pair in strong4:strong4-a correlated4:correlated4-a; do
    pool="${pair%%:*}"
    run="${pair##*:}"
    echo "############ ${run} ############"
    date -Is
    .venv/bin/python -m mas_harness.runners.episodes \
        --manifest data/manifests/hard366.json \
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
echo "ALL PRICED RUNS COMPLETE"
