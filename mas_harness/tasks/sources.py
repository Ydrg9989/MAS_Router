"""Read benchmark data from the local HuggingFace cache, read-only.

Deliberately does not call ``datasets.load_dataset``: that writes lock files into the
HF cache directory, which fails when the cache is not writable, and it can reach for the
network. Arrow shards are opened directly through ``Dataset.from_file``, which
memory-maps and never writes.

Manifests are built once from these sources and then frozen, so nothing downstream of
``mas_harness.tasks.manifest`` needs HuggingFace at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

DEFAULT_HF_HOME = "/data/yiderigun/.cache/huggingface"


def hf_datasets_root() -> Path:
    home = os.environ.get("HF_HOME") or DEFAULT_HF_HOME
    return Path(home) / "datasets"


@dataclass(frozen=True)
class ArrowSource:
    """Where a benchmark's shard lives in the HF cache."""

    suite: str
    hf_repo: str  # e.g. "HuggingFaceH4/MATH-500"
    shard_glob: str  # e.g. "math-500-test.arrow"

    @property
    def cache_dirname(self) -> str:
        # HF replaces "/" with "___" and lowercases the dataset name component.
        namespace, name = self.hf_repo.split("/", 1)
        return f"{namespace}___{name.lower()}"

    def resolve(self) -> Path:
        root = hf_datasets_root()
        relative = f"{self.cache_dirname}/*/*/*/{self.shard_glob}"
        pattern = str(root / relative)
        matches = sorted(root.glob(relative))
        if not matches:
            raise FileNotFoundError(
                f"no cached Arrow shard for {self.hf_repo} (suite {self.suite!r}).\n"
                f"Looked for: {pattern}\n"
                f"Either the dataset is not cached under HF_HOME={os.environ.get('HF_HOME')} "
                f"or the shard name changed."
            )
        # Multiple revisions can be cached; the most recent wins.
        return Path(max(matches, key=lambda p: Path(p).stat().st_mtime))

    def rows(self) -> Iterator[dict[str, Any]]:
        from datasets import Dataset

        dataset = Dataset.from_file(str(self.resolve()))
        for row in dataset:
            yield dict(row)


SOURCES: dict[str, ArrowSource] = {
    "math500": ArrowSource("math500", "HuggingFaceH4/MATH-500", "math-500-test.arrow"),
    "gpqa_diamond": ArrowSource(
        "gpqa_diamond", "fingertap/GPQA-Diamond", "gpqa-diamond-test.arrow"
    ),
    "mmlu_pro": ArrowSource("mmlu_pro", "TIGER-Lab/MMLU-Pro", "mmlu-pro-test.arrow"),
}

# MMLU-Pro categories the research report calls "knowledge-intensive STEM".
MMLU_PRO_STEM_CATEGORIES = frozenset(
    {"physics", "chemistry", "biology", "engineering", "computer science", "math"}
)


def available_suites() -> dict[str, bool]:
    """Which configured suites are actually present in the local cache."""
    status: dict[str, bool] = {}
    for name, source in SOURCES.items():
        try:
            source.resolve()
            status[name] = True
        except FileNotFoundError:
            status[name] = False
    return status
