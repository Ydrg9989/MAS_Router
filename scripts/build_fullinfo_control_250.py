"""Build distctl250: the full-information twin of distributed250's source questions.

Unlike distctl30 (filtered from mvp366), the 250 fresh source questions are mostly unbanked, so
this builds the intact mmlu_pro specs directly from the source cache, restricted to exactly the
qids that distributed250 partitioned. Same prompts and extraction as every other mmlu_pro task.

    python scripts/build_fullinfo_control_250.py
"""

from __future__ import annotations

from datetime import UTC, datetime

from mas_harness import config
from mas_harness.tasks.manifest import SOURCES, Manifest, _mmlu_pro_specs

OUT = config.DATA_DIR / "manifests" / "distctl250.json"


def main() -> None:
    dist = Manifest.read(config.DATA_DIR / "manifests" / "distributed250.json")
    qids = {t.task_id.split("::")[2] for t in dist.tasks}
    assert len(qids) == 250, f"expected 250 source questions, got {len(qids)}"

    specs = [
        s for s in _mmlu_pro_specs(list(SOURCES["mmlu_pro"].rows()), stem_only=True)
        if s.task_id.split("::")[1] in qids
    ]
    assert len(specs) == 250, f"expected 250 matching mmlu_pro specs, got {len(specs)}"

    manifest = Manifest(
        manifest_id="distctl250",
        created_at=datetime.now(UTC).isoformat(),
        seed=dist.seed,
        tasks=sorted(specs, key=lambda s: s.task_id),
        splits={"calibration": [], "test": [s.task_id for s in specs]},
        description=(
            "Full-information control for distributed250: the identical 250 MMLU-Pro questions "
            "with intact option sets, built from the source cache. Exists solely for the "
            "at-scale H2 contamination check of the entitlement main study. Never pool with "
            "distributed_synth results."
        ),
    )
    path = manifest.write(OUT, force=False)
    print(f"wrote {path}  tasks={len(manifest.tasks)}  hash={manifest.content_hash[:16]}")


if __name__ == "__main__":
    main()
