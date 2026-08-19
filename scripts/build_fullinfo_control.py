"""Build distctl30: the full-information twin of distributed30's source questions.

The entitlement pilot (Docs/preregistrations/2026-08-19-entitlement-pilot.md) needs each pool
member's FULL-INFORMATION correctness on exactly the 30 MMLU-Pro questions that distributed30
partitions, to test whether non-holder "calibration" is really memorization detection: a member
that abstains because its visible set lacks the gold option is indistinguishable from one that
memorized the answer and notices it is off-menu — unless we know whether it can solve the intact
question at all.

mvp366 already contains all 30 source questions (same derivation path, full option sets), so this
filters that manifest rather than re-deriving: same prompts, same ground truth, same extraction.

    python scripts/build_fullinfo_control.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from mas_harness import config
from mas_harness.tasks.manifest import Manifest

OUT = config.DATA_DIR / "manifests" / "distctl30.json"


def main() -> None:
    dist = Manifest.read(config.DATA_DIR / "manifests" / "distributed30.json")
    # distributed task ids look like distributed_synth::mmlu_pro::<qid>::<source>
    qids = {t.task_id.split("::")[2] for t in dist.tasks}
    assert len(qids) == 30, f"expected 30 source questions, got {len(qids)}"

    mvp = Manifest.read(config.DATA_DIR / "manifests" / "mvp366.json")
    tasks = [
        t for t in mvp.tasks
        if t.suite == "mmlu_pro" and t.task_id.split("::")[1] in qids
    ]
    assert len(tasks) == 30, f"expected 30 matching mvp366 tasks, got {len(tasks)}"

    manifest = Manifest(
        manifest_id="distctl30",
        created_at=datetime.now(timezone.utc).isoformat(),
        seed=dist.seed,
        tasks=tasks,
        splits={"calibration": [], "test": [t.task_id for t in tasks]},
        description=(
            "Full-information control for distributed30: the identical 30 MMLU-Pro questions "
            "with intact option sets, filtered from mvp366. Exists solely to measure each "
            "member's memorization/solvability baseline for the entitlement pilot's "
            "contamination test (H2). Never pool with distributed_synth results."
        ),
    )
    path = manifest.write(OUT, force=False)
    print(f"wrote {path}  tasks={len(manifest.tasks)}  hash={manifest.content_hash[:16]}")


if __name__ == "__main__":
    main()
