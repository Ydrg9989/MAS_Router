"""Content-addressed cache for LLM responses.

A cache hit costs nothing and returns byte-identical text, which is what makes Stage-B
protocol replays and causal-intervention re-runs affordable (D-001).

The key covers everything that can change the response: model, the full message list,
temperature, token limit, seed, and any extra request parameters. It deliberately does
*not* cover the run id or the agent id, so two runs asking the same question of the same
model share the answer.

Cache files are sharded two levels deep by key prefix, because a single flat directory
with tens of thousands of entries is slow to list on network filesystems.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

CACHE_SCHEMA_VERSION = 1


def cache_key(
    *,
    model: str,
    messages: list[Mapping[str, Any]],
    temperature: float,
    max_tokens: int,
    seed: int | None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Deterministic sha256 over everything that can change the response."""
    payload = {
        "schema": CACHE_SCHEMA_VERSION,
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
        "extra": dict(sorted((extra or {}).items())),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def prompt_hash(messages: list[Mapping[str, Any]]) -> str:
    """Hash of just the prompt, recorded on every record for reproducibility auditing."""
    blob = json.dumps(
        [{"role": m["role"], "content": m["content"]} for m in messages],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResponseCache:
    """Sharded on-disk JSON cache. Never evicts; see TODO.md."""

    def __init__(self, root: str | Path, *, enabled: bool = True):
        self.root = Path(root)
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        if self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / key[:2] / key[2:4] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self.path_for(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # A truncated entry from an interrupted write is a miss, not a crash.
            self.misses += 1
            return None
        self.hits += 1
        return payload

    def put(self, key: str, payload: Mapping[str, Any]) -> None:
        if not self.enabled:
            return
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory and rename, so a crash mid-write
        # can never leave a partially valid entry behind.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}
