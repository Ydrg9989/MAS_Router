"""Attempt to rebuild aggregator episodes that died at the token cap. THIS DID NOT WORK — see D-028.

Kept as the record of a failed repair. On 25 of 366 tasks, all GPQA-Diamond, Claude Sonnet 5
spends all 16,384 output tokens on internal reasoning and emits zero visible characters, so
D-019 scores the episode as an abstention and therefore wrong. That penalty lands only on the
two protocols the aggregator decides.

The hypothesis was D-018's remedy for the same pathology in Gemini: clamp the reasoning budget
so visible output is guaranteed room. It failed. OpenRouter's reasoning parameters are silently
ignored for Anthropic models, and the retried episodes came back with the identical 16,384
tokens and the same empty content, at a cost of $9.57. `scripts/probe_aggregator.py`
established why: `max_tokens`, `effort` and `exclude` all produce identical non-termination.

Do not re-run this expecting a different outcome. Aggregator non-termination is treated as
missing data instead (D-028).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from mas_harness import config

POOLS = {
    "strong4-a": "strong4",
    "decorr4-a": "decorrelated4",
    "correlated4-a": "correlated4",
}
REASONING_CAP = 4096
PROTOCOLS = ["independent_judge", "chair_information_seeking", "expert_verifier"]


def clamped_pool(pool_name: str, out_dir: Path) -> Path:
    """The same pool with the aggregator's reasoning budget bounded."""
    source = Path("configs/pools") / f"{pool_name}.yaml"
    spec = yaml.safe_load(source.read_text())
    aggregator = spec["aggregator"]
    extra = dict(aggregator.get("extra_body") or {})
    extra["reasoning"] = {"max_tokens": REASONING_CAP}
    aggregator["extra_body"] = extra
    spec["pool_id"] = f"{spec['pool_id']}_fixagg"
    spec["description"] = (
        f"{spec.get('description', '').strip()} Aggregator reasoning clamped to "
        f"{REASONING_CAP} tokens so visible output is guaranteed room (see D-028)."
    )
    target = out_dir / f"{pool_name}_fixagg.yaml"
    target.write_text(yaml.safe_dump(spec, sort_keys=False))
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pool_dir = Path("configs/pools")
    for run, pool_name in POOLS.items():
        tasks_file = Path(f"data/retry_{run}.json")
        if not tasks_file.exists():
            print(f"skipping {run}: no {tasks_file}")
            continue
        n_tasks = len(json.loads(tasks_file.read_text()))
        if n_tasks == 0:
            print(f"skipping {run}: nothing truncated")
            continue

        retry_run = f"{run}-retry"
        src = Path(config.RUNS_DIR) / run
        dst = Path(config.RUNS_DIR) / retry_run
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("answers.jsonl", "answers.parquet", "pricing_snapshot.json"):
            if (src / name).exists() and not (dst / name).exists():
                shutil.copy2(src / name, dst / name)

        cmd = [
            sys.executable,
            "-m",
            "mas_harness.runners.episodes",
            "--manifest",
            "data/manifests/hard366.json",
            "--pool",
            str(clamped_pool(pool_name, pool_dir)),
            "--run-id",
            retry_run,
            "--protocols",
            *PROTOCOLS,
            "--coalitions",
            "grand",
            "--interventions",
            "none",
            "--tasks-from",
            str(tasks_file),
            "--concurrency",
            str(args.concurrency),
        ]
        if args.dry_run:
            cmd.append("--dry-run")
        print(f"\n######## {retry_run}: {n_tasks} tasks ########", flush=True)
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
