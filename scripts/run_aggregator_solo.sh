#!/usr/bin/env bash
# The control that decides what D-043/D-044 are: is the judge aggregating, or is it a better model?
#
# Pre-registered in Docs/preregistrations/2026-08-14-aggregator-solo.md. Stage A only, one agent,
# both suites, into one run directory — task ids are disjoint across suites so a single
# answers.jsonl is unambiguous. Sequential rather than parallel because both write to that file.
set -euo pipefail
cd "$(dirname "$0")/.."

for suite in crosscap240 hard366; do
    echo "############ ${suite} ############"
    date -Is
    .venv/bin/python -m mas_harness.runners.answer_bank \
        --manifest "data/manifests/${suite}.json" \
        --pool configs/pools/aggregator_solo.yaml \
        --run-id aggregator-solo \
        --concurrency 8
    echo "DONE ${suite}"
done
echo "AGGREGATOR SOLO CONTROL COMPLETE"
