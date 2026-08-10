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
    # Datasets split across named configs, each contributing one shard under the same file
    # name. AIME 2025 ships as AIME2025-I and AIME2025-II; globbing without the config would
    # match both and silently keep whichever was written last, halving the suite.
    configs: tuple[str, ...] = ()
    # HF's cache directory name is not simply the lowercased repo: CamelCase is snake-cased, so
    # "facebook/ExploreToM" lands in "facebook___explore_to_m". Rather than reimplement a rule that
    # is theirs to change, a source may state its directory outright.
    cache_dirname_override: str | None = None

    @property
    def cache_dirname(self) -> str:
        if self.cache_dirname_override:
            return self.cache_dirname_override
        namespace, name = self.hf_repo.split("/", 1)
        return f"{namespace}___{name.lower()}"

    def _resolve_one(self, config: str | None) -> Path:
        root = hf_datasets_root()
        relative = f"{self.cache_dirname}/{config or '*'}/*/*/{self.shard_glob}"
        matches = sorted(root.glob(relative))
        if not matches:
            raise FileNotFoundError(
                f"no cached Arrow shard for {self.hf_repo} (suite {self.suite!r}"
                f"{f', config {config}' if config else ''}).\n"
                f"Looked for: {root / relative}\n"
                f"Either the dataset is not cached under HF_HOME={os.environ.get('HF_HOME')} "
                f"or the shard name changed."
            )
        # Multiple revisions of one config can be cached; the most recent wins.
        return Path(max(matches, key=lambda p: Path(p).stat().st_mtime))

    def resolve(self) -> Path:
        """The single shard, for sources that have one. Raises for multi-config sources."""
        if self.configs:
            raise ValueError(
                f"{self.suite!r} spans {len(self.configs)} configs; use resolve_all()"
            )
        return self._resolve_one(None)

    def resolve_all(self) -> list[Path]:
        return [self._resolve_one(c) for c in self.configs] if self.configs \
            else [self._resolve_one(None)]

    def rows(self) -> Iterator[dict[str, Any]]:
        from datasets import Dataset

        for shard in self.resolve_all():
            for row in Dataset.from_file(str(shard)):
                yield dict(row)


SOURCES: dict[str, ArrowSource] = {
    "math500": ArrowSource("math500", "HuggingFaceH4/MATH-500", "math-500-test.arrow"),
    "gpqa_diamond": ArrowSource(
        "gpqa_diamond", "fingertap/GPQA-Diamond", "gpqa-diamond-test.arrow"
    ),
    "mmlu_pro": ArrowSource("mmlu_pro", "TIGER-Lab/MMLU-Pro", "mmlu-pro-test.arrow"),
    # The cross-capability suites (D-032). Each demands something the hard-STEM suites do not,
    # which is the condition D-031 could not rule out.
    "cruxeval": ArrowSource("cruxeval", "cruxeval-org/cruxeval", "cruxeval-test.arrow"),
    "aime": ArrowSource("aime", "Maxwell-Jia/AIME_2024", "aime_2024-train.arrow"),
    "aime2025": ArrowSource(
        "aime2025",
        "opencompass/AIME2025",
        "aime2025-test.arrow",
        configs=("AIME2025-I", "AIME2025-II"),
    ),
    "exploretom": ArrowSource(
        "exploretom",
        "facebook/ExploreToM",
        "explore_to_m-train.arrow",
        cache_dirname_override="facebook___explore_to_m",
    ),
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
