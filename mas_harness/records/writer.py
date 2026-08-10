"""Append-only JSONL record writing, resume support, and Parquet export.

Long API-bound runs get interrupted, so JSONL append is the ingest format and Parquet is
a derived view (D-007). Resume works by reading back the keys already present and
skipping them, which is O(existing records) at startup — negligible at our scale.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from pydantic import BaseModel

from .schema import AnswerRecord, EpisodeRecord, RunMeta, answer_key_str, episode_key_str


class JsonlWriter:
    """Thread-safe append-only writer that flushes every record.

    Flushing on every write costs throughput but means an interrupted run loses at most
    the record in flight, which matters far more when each record represents money
    already spent.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle = self.path.open("a", encoding="utf-8")
        self.n_written = 0

    def write(self, record: BaseModel | dict[str, Any]) -> None:
        payload = record.model_dump() if isinstance(record, BaseModel) else record
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            self._handle.write(line + "\n")
            self._handle.flush()
            self.n_written += 1

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.close()

    def __enter__(self) -> "JsonlWriter":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield records, tolerating a truncated final line from an interrupted run."""
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Only the last line can legitimately be partial.
                nxt = handle.readline()
                if nxt:
                    raise ValueError(f"{path}:{line_no} is corrupt, not merely truncated") from None
                return


class RunDirectory:
    """Layout and resume bookkeeping for one run."""

    def __init__(self, root: str | Path, run_id: str):
        self.run_id = run_id
        self.path = Path(root) / run_id
        self.path.mkdir(parents=True, exist_ok=True)

    @property
    def answers_path(self) -> Path:
        return self.path / "answers.jsonl"

    @property
    def episodes_path(self) -> Path:
        return self.path / "episodes.jsonl"

    @property
    def meta_path(self) -> Path:
        return self.path / "run_meta.json"

    @property
    def pricing_path(self) -> Path:
        return self.path / "pricing_snapshot.json"

    def write_meta(self, meta: RunMeta) -> Path:
        # Stage B adds to a Stage A run directory, so meta is merged rather than replaced.
        existing: dict[str, Any] = {}
        if self.meta_path.exists():
            existing = json.loads(self.meta_path.read_text())
        fresh = {k: v for k, v in meta.model_dump().items() if v not in (None, "", [], {})}
        merged = {**existing, **fresh}
        history = existing.get("stage_history", [])
        history.append({"stage": meta.stage, "at": meta.created_at})
        merged["stage_history"] = history
        self.meta_path.write_text(json.dumps(merged, indent=2, sort_keys=True, default=str))
        return self.meta_path

    def read_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            raise FileNotFoundError(
                f"no run_meta.json in {self.path}. Run Stage A first "
                f"(python -m mas_harness.runners.answer_bank)."
            )
        return json.loads(self.meta_path.read_text())

    # ---- resume ----

    def completed_answer_keys(self) -> set[str]:
        return {
            answer_key_str(r["task_id"], r["agent_id"], r["seed"])
            for r in read_jsonl(self.answers_path)
        }

    def completed_episode_keys(self) -> set[str]:
        keys: set[str] = set()
        for r in read_jsonl(self.episodes_path):
            intervention = r.get("intervention") or {}
            label = _intervention_label(intervention)
            keys.add(
                episode_key_str(
                    r["task_id"],
                    r["pool_id"],
                    r["protocol_id"],
                    list(r["coalition"]),
                    r["seed"],
                    label,
                )
            )
        return keys

    def load_answers(self) -> list[AnswerRecord]:
        return [AnswerRecord.model_validate(r) for r in read_jsonl(self.answers_path)]

    def load_episodes(self) -> list[EpisodeRecord]:
        return [EpisodeRecord.model_validate(r) for r in read_jsonl(self.episodes_path)]


def _intervention_label(intervention: dict[str, Any]) -> str:
    kind = intervention.get("kind", "none")
    if kind == "none":
        return "none"
    if kind == "reorder":
        order = intervention.get("order") or []
        return f"reorder:{'-'.join(str(a) for a in order)}"
    return f"{kind}:a{intervention.get('target_agent_id')}"


# ---- Parquet export -------------------------------------------------------------------

# Nested columns that analysis reads as scalars; flattened on export so that the Parquet
# view is queryable without unnesting.
_ANSWER_FLATTEN = {
    "cost_usd": ("call", "cost_usd"),
    "latency_ms": ("call", "latency_ms"),
    "cached": ("call", "cached"),
    "prompt_hash": ("call", "prompt_hash"),
}


def to_parquet(
    jsonl_path: str | Path,
    parquet_path: str | Path | None = None,
    *,
    drop_columns: Sequence[str] = ("transcript", "calls"),
) -> Path:
    """Flatten a records JSONL file into Parquet for analysis.

    Transcripts and per-call records are dropped by default: they are the bulk of the
    bytes and are only needed when inspecting individual episodes, for which the JSONL is
    the better source.
    """
    import pandas as pd

    jsonl_path = Path(jsonl_path)
    parquet_path = Path(parquet_path) if parquet_path else jsonl_path.with_suffix(".parquet")
    rows = list(read_jsonl(jsonl_path))
    if not rows:
        raise ValueError(f"{jsonl_path} contains no records")

    flattened: list[dict[str, Any]] = []
    for row in rows:
        out = {k: v for k, v in row.items() if k not in drop_columns}
        for target, (parent, child) in _ANSWER_FLATTEN.items():
            if isinstance(row.get(parent), dict) and child in row[parent]:
                out[target] = row[parent][child]
        usage = out.pop("usage", None)
        if isinstance(usage, dict):
            for k, v in usage.items():
                out[f"usage_{k}"] = v
        call = out.pop("call", None)
        if isinstance(call, dict):
            call_usage = call.get("usage") or {}
            for k, v in call_usage.items():
                out[f"usage_{k}"] = v
            out["model"] = out.get("model") or call.get("model")
        intervention = out.pop("intervention", None)
        if isinstance(intervention, dict):
            out["intervention_kind"] = intervention.get("kind", "none")
            out["intervention_target"] = intervention.get("target_agent_id")
            out["intervention_label"] = _intervention_label(intervention)
        for key in ("coalition",):
            if isinstance(out.get(key), list):
                out[f"{key}_size"] = len(out[key])
                out[key] = "-".join(str(a) for a in out[key])
        for key in ("individual_correct", "protocol_meta"):
            if key in out:
                out[key] = json.dumps(out[key], default=str)
        flattened.append(out)

    frame = pd.DataFrame(flattened)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def write_records(path: str | Path, records: Iterable[BaseModel]) -> int:
    with JsonlWriter(path) as writer:
        for record in records:
            writer.write(record)
        return writer.n_written
