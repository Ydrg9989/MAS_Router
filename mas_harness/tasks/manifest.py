"""Immutable, content-hashed task manifests.

A manifest is the frozen definition of "which tasks, in which order, with which splits".
Once written it refuses to be silently overwritten, because every answer bank and episode
file downstream references it by hash. Rebuilding with different contents requires an
explicit ``--force``, and the hash change is then visible in every run's ``run_meta.json``.

Build one from a suite config:

    python -m mas_harness.tasks.manifest build --suite configs/suites/mvp90.yaml
    python -m mas_harness.tasks.manifest show --manifest data/manifests/mvp90.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from .adapters import CHOICE_SUITES, TaskSpec, build_evaluator
from .distributed import SUITE as DISTRIBUTED_SUITE
from .distributed import build_distributed_specs, verify_spec
from .sources import MMLU_PRO_STEM_CATEGORIES, SOURCES
from .splits import counts_by, leave_one_domain_out, stratified_split

MANIFEST_SCHEMA_VERSION = 1
DEFAULT_MANIFEST_DIR = Path("data/manifests")


@dataclass
class Manifest:
    manifest_id: str
    created_at: str
    seed: int
    tasks: list[TaskSpec]
    splits: dict[str, list[str]]
    description: str = ""
    schema_version: int = MANIFEST_SCHEMA_VERSION

    # ---- identity ----

    @property
    def content_hash(self) -> str:
        """Hash over what each task actually presents, plus ordering.

        Deliberately excludes ``created_at`` so that rebuilding the same manifest twice
        produces the same hash, and includes the ordering so a reshuffle is a new manifest.

        Private briefings are included because for the distributed-information suite the
        partition *is* the task (D-010): two manifests can name the same questions with the
        same answers while showing the members completely different option subsets. Hashing
        identity alone would call those identical and let a changed partition pass the
        immutability check in :meth:`write` unnoticed.
        """
        payload = [
            {
                "task_id": t.task_id,
                "suite": t.suite,
                "gt": t.ground_truth,
                "private": hashlib.sha256(
                    json.dumps(t.hidden_context, sort_keys=True).encode()
                ).hexdigest()[:16],
            }
            for t in self.tasks
        ]
        blob = json.dumps(
            {"manifest_id": self.manifest_id, "seed": self.seed, "tasks": payload},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def task_ids(self) -> list[str]:
        return [t.task_id for t in self.tasks]

    def domain_pairs(self) -> list[tuple[str, str]]:
        return [(t.task_id, t.domain) for t in self.tasks]

    def suite_pairs(self) -> list[tuple[str, str]]:
        return [(t.task_id, t.suite) for t in self.tasks]

    def by_id(self) -> dict[str, TaskSpec]:
        return {t.task_id: t for t in self.tasks}

    def subset(self, task_ids: Iterable[str]) -> list[TaskSpec]:
        wanted = set(task_ids)
        return [t for t in self.tasks if t.task_id in wanted]

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "created_at": self.created_at,
            "seed": self.seed,
            "description": self.description,
            "content_hash": self.content_hash,
            "n_tasks": len(self.tasks),
            "counts_by_suite": counts_by(self.suite_pairs()),
            "counts_by_domain": counts_by(self.domain_pairs()),
            "splits": {k: sorted(v) for k, v in self.splits.items()},
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def write(self, path: str | Path, *, force: bool = False) -> Path:
        path = Path(path)
        if path.exists() and not force:
            existing = json.loads(path.read_text())
            if existing.get("content_hash") == self.content_hash:
                return path  # Identical rebuild is a no-op, not an error.
            raise FileExistsError(
                f"{path} already exists with a different content_hash "
                f"({existing.get('content_hash')[:12]} vs {self.content_hash[:12]}). "
                f"Manifests are immutable because runs reference them by hash; pass "
                f"--force only if no run depends on the old one."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def read(cls, path: str | Path) -> "Manifest":
        payload = json.loads(Path(path).read_text())
        manifest = cls(
            manifest_id=payload["manifest_id"],
            created_at=payload["created_at"],
            seed=payload["seed"],
            tasks=[TaskSpec.from_dict(t) for t in payload["tasks"]],
            splits={k: list(v) for k, v in payload.get("splits", {}).items()},
            description=payload.get("description", ""),
            schema_version=payload.get("schema_version", MANIFEST_SCHEMA_VERSION),
        )
        recorded = payload.get("content_hash")
        if recorded and recorded != manifest.content_hash:
            raise ValueError(
                f"{path} content_hash mismatch: file says {recorded[:12]}, "
                f"recomputed {manifest.content_hash[:12]}. The manifest was edited by hand."
            )
        return manifest


# ---- construction ---------------------------------------------------------------------


def _math500_specs(rows: list[dict[str, Any]]) -> list[TaskSpec]:
    specs: list[TaskSpec] = []
    for row in rows:
        payload = {"problem": row.get("problem", ""), "solution": row.get("solution", "")}
        task_id = f"math500::{row.get('unique_id') or len(specs)}"
        spec = TaskSpec(
            task_id=task_id,
            suite="math500",
            domain=str(row.get("subject") or "math").strip().lower(),
            answer_type="boxed_math",
            prompt="",
            ground_truth="",
            payload=payload,
        )
        specs.append(_finalize(spec, dataset_answer=row.get("answer")))
    return [s for s in specs if s is not None]


def _gpqa_specs(rows: list[dict[str, Any]]) -> list[TaskSpec]:
    specs: list[TaskSpec] = []
    for index, row in enumerate(rows):
        payload = {"question": row.get("question", ""), "answer": row.get("answer", "")}
        spec = TaskSpec(
            task_id=f"gpqa_diamond::{index}",
            suite="gpqa_diamond",
            # GPQA Diamond ships no per-question subject in this mirror; the suite is the
            # domain for stratification purposes.
            domain="gpqa_science",
            answer_type="choice",
            prompt="",
            ground_truth="",
            payload=payload,
        )
        specs.append(_finalize(spec))
    return [s for s in specs if s is not None]


def _mmlu_pro_specs(rows: list[dict[str, Any]], *, stem_only: bool) -> list[TaskSpec]:
    specs: list[TaskSpec] = []
    for row in rows:
        category = str(row.get("category") or "").strip().lower()
        if stem_only and category not in MMLU_PRO_STEM_CATEGORIES:
            continue
        options = row.get("options") or []
        if isinstance(options, str):
            # Some cached revisions store the option list as a repr string.
            try:
                options = json.loads(options.replace("'", '"'))
            except json.JSONDecodeError:
                continue
        payload = {
            "question_id": row.get("question_id", ""),
            "question": row.get("question", ""),
            "options": list(options),
            "answer": row.get("answer", ""),
        }
        spec = TaskSpec(
            task_id=f"mmlu_pro::{row.get('question_id')}::{row.get('src','')}",
            suite="mmlu_pro",
            domain=category or "unknown",
            answer_type="choice",
            prompt="",
            ground_truth="",
            payload=payload,
        )
        specs.append(_finalize(spec))
    return [s for s in specs if s is not None]


def _finalize(spec: TaskSpec, *, dataset_answer: Any = None) -> TaskSpec | None:
    """Fill in the prompt and ground truth from the upstream evaluator, or drop the task.

    A task whose ground truth cannot be extracted is dropped at build time rather than
    silently scoring every agent zero at run time. For MATH-500 the extracted boxed answer
    is cross-checked against the dataset's own ``answer`` column; a disagreement is
    recorded so it can be inspected rather than hidden.
    """
    evaluator = build_evaluator(spec)
    upstream = evaluator._task
    try:
        ground_truth = str(upstream.get_ground_truth() or "").strip()
        prompt = str(upstream.get_task_description(0) or "").strip()
    except Exception:
        return None
    if not ground_truth or not prompt:
        return None

    payload = dict(spec.payload)
    if dataset_answer is not None:
        recorded = str(dataset_answer).strip()
        payload["dataset_answer"] = recorded
        payload["gt_matches_dataset_answer"] = recorded == ground_truth

    return TaskSpec(
        task_id=spec.task_id,
        suite=spec.suite,
        domain=spec.domain,
        answer_type=spec.answer_type,
        prompt=prompt,
        ground_truth=ground_truth,
        payload=payload,
        hidden_context=spec.hidden_context,
    )


def _suite_seed(seed: int, suite: str) -> int:
    """A per-suite sampling seed that is stable across processes.

    ``hash()`` on a string is salted per interpreter, so using it here made the sampled task
    set — and therefore ``content_hash`` — different on every rebuild. That silently defeats
    the immutability check in :meth:`Manifest.write`, which compares hashes to decide whether
    a rebuild is a no-op or a conflict.
    """
    digest = hashlib.sha256(f"{seed}::{suite}".encode()).hexdigest()
    return seed + int(digest[:8], 16) % 10_000


def _sample(specs: list[TaskSpec], *, n: int | None, seed: int) -> list[TaskSpec]:
    """Sample n tasks, stratified across domains, deterministically."""
    if n is None or n >= len(specs):
        return specs
    from collections import defaultdict

    by_domain: dict[str, list[TaskSpec]] = defaultdict(list)
    for spec in specs:
        by_domain[spec.domain].append(spec)

    rng = random.Random(seed)
    for bucket in by_domain.values():
        bucket.sort(key=lambda s: s.task_id)
        rng.shuffle(bucket)

    # Round-robin across domains so the sample is as balanced as the data allows.
    chosen: list[TaskSpec] = []
    domains = sorted(by_domain)
    cursor = 0
    while len(chosen) < n:
        progressed = False
        for domain in domains:
            bucket = by_domain[domain]
            if cursor < len(bucket):
                chosen.append(bucket[cursor])
                progressed = True
                if len(chosen) == n:
                    break
        if not progressed:
            break
        cursor += 1
    return sorted(chosen, key=lambda s: s.task_id)


def _filter_rows(suite: str, rows: list[dict[str, Any]], entry: dict[str, Any]) -> list[dict]:
    """Apply difficulty filters that act on source columns absent from ``TaskSpec``.

    These exist because a suite the pool answers correctly every time cannot distinguish
    protocols, however many tasks it contains (D-020). Difficulty is therefore a first-class
    selection criterion, and both usable signals live in source columns that the spec drops:
    MATH-500 ships a ``level`` and MMLU-Pro a ``src`` naming the sub-corpus a question came
    from, whose difficulty varies far more than its subject category does.
    """
    levels = entry.get("levels")
    if levels is not None:
        if suite != "math500":
            raise ValueError(f"'levels' applies only to math500, not {suite!r}")
        wanted = {str(level) for level in levels}
        rows = [r for r in rows if str(r.get("level")) in wanted]
        if not rows:
            raise ValueError(f"no math500 rows at levels {sorted(wanted)}")

    sources = entry.get("sources")
    if sources is not None:
        if suite != "mmlu_pro":
            raise ValueError(f"'sources' applies only to mmlu_pro, not {suite!r}")
        # Match on the prefix before the first hyphen: srcs look like "stemez-Biology",
        # "ori_mmlu-college_physics", "theoremQA", "scibench".
        wanted = {str(s).lower() for s in sources}
        rows = [r for r in rows if str(r.get("src", "")).split("-")[0].lower() in wanted]
        if not rows:
            raise ValueError(f"no mmlu_pro rows from sources {sorted(wanted)}")

    return rows


def _select(entry: dict[str, Any], *, seed: int) -> list[TaskSpec]:
    """Build and sample the tasks for one dataset-backed suite entry."""
    suite = entry["suite"]
    if suite not in SOURCES:
        raise ValueError(f"unknown suite {suite!r}; known: {sorted(SOURCES)}")
    rows = _filter_rows(suite, list(SOURCES[suite].rows()), entry)
    if suite == "math500":
        specs = _math500_specs(rows)
    elif suite == "gpqa_diamond":
        specs = _gpqa_specs(rows)
    elif suite == "mmlu_pro":
        specs = _mmlu_pro_specs(rows, stem_only=bool(entry.get("stem_only", True)))
    else:
        raise AssertionError(f"unhandled suite {suite!r}")

    if entry.get("domains"):
        wanted = {str(d).lower() for d in entry["domains"]}
        specs = [s for s in specs if s.domain in wanted]

    selected = _sample(specs, n=entry.get("n"), seed=_suite_seed(seed, suite))
    if entry.get("n") and len(selected) < int(entry["n"]):
        raise ValueError(
            f"suite {suite!r} yielded only {len(selected)} usable tasks, "
            f"but {entry['n']} were requested"
        )
    return selected


def _derive_distributed(entry: dict[str, Any], *, seed: int) -> list[TaskSpec]:
    """Build the distributed-information suite from a multiple-choice source suite (D-010).

    Oversamples the source by a small margin because tasks with too few options are dropped
    during derivation, then trims back to the requested count so the suite size is exact.
    """
    source_suite = entry.get("derive_from", "mmlu_pro")
    if source_suite not in CHOICE_SUITES:
        raise ValueError(
            f"distributed_synth can only be derived from a multiple-choice suite; "
            f"{source_suite!r} is not one of {sorted(CHOICE_SUITES)}"
        )
    requested = entry.get("n")
    source_entry = dict(entry)
    source_entry["suite"] = source_suite
    if requested:
        source_entry["n"] = int(requested) + 10
    sources = _select(source_entry, seed=seed)

    agent_ids = list(entry.get("agent_ids") or range(int(entry.get("n_positions", 4))))
    specs = build_distributed_specs(
        sources,
        n_positions=len(agent_ids),
        agent_ids=agent_ids,
        seed=seed,
        n_holders=int(entry.get("n_holders", 1)),
        announce_structure=bool(entry.get("announce_structure", True)),
        allow_declining=bool(entry.get("allow_declining", True)),
    )
    if requested:
        if len(specs) < int(requested):
            raise ValueError(
                f"distributed_synth yielded only {len(specs)} usable tasks from "
                f"{source_suite!r}, but {requested} were requested"
            )
        # Trim through the stratified sampler, not by slicing: slicing an id-sorted list
        # discards the domain balance the oversample was drawn with.
        specs = _sample(specs, n=int(requested), seed=_suite_seed(seed, DISTRIBUTED_SUITE))
    for spec in specs:
        verify_spec(spec)
    return specs


def build_manifest(suite_config: dict[str, Any]) -> Manifest:
    """Build a manifest from a suite config dict."""
    manifest_id = suite_config["manifest_id"]
    seed = int(suite_config.get("seed", 0))
    calibration_fraction = float(suite_config.get("calibration_fraction", 1.0 / 3.0))

    all_specs: list[TaskSpec] = []
    for entry in suite_config["suites"]:
        suite = entry["suite"]
        if suite == DISTRIBUTED_SUITE:
            all_specs.extend(_derive_distributed(entry, seed=seed))
            continue
        all_specs.extend(_select(entry, seed=seed))

    all_specs.sort(key=lambda s: (s.suite, s.task_id))
    pairs = [(s.task_id, s.domain) for s in all_specs]
    calibration, test = stratified_split(pairs, fraction=calibration_fraction, seed=seed)

    splits: dict[str, list[str]] = {"calibration": calibration, "test": test}
    for domain, (train_ids, held_out) in leave_one_domain_out(pairs).items():
        splits[f"lodo_train::{domain}"] = train_ids
        splits[f"lodo_test::{domain}"] = held_out

    return Manifest(
        manifest_id=manifest_id,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        seed=seed,
        tasks=all_specs,
        splits=splits,
        description=str(suite_config.get("description", "")),
    )


def load_suite_config(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and inspect task manifests")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build a manifest from a suite config")
    build.add_argument("--suite", required=True, help="path to a suite YAML")
    build.add_argument("--out", default=None, help="output path (default data/manifests/<id>.json)")
    build.add_argument("--force", action="store_true", help="overwrite a differing manifest")

    show = sub.add_parser("show", help="summarize an existing manifest")
    show.add_argument("--manifest", required=True)
    show.add_argument("--sample", type=int, default=0, help="print N task prompts")

    args = parser.parse_args(argv)

    if args.command == "build":
        config = load_suite_config(args.suite)
        manifest = build_manifest(config)
        out = Path(args.out) if args.out else DEFAULT_MANIFEST_DIR / f"{manifest.manifest_id}.json"
        path = manifest.write(out, force=args.force)
        print(f"manifest '{manifest.manifest_id}' -> {path}")
        print(f"  content_hash : {manifest.content_hash}")
        print(f"  tasks        : {len(manifest.tasks)}")
        print(f"  by suite     : {counts_by(manifest.suite_pairs())}")
        print(f"  by domain    : {counts_by(manifest.domain_pairs())}")
        print(
            f"  splits       : calibration={len(manifest.splits['calibration'])} "
            f"test={len(manifest.splits['test'])}"
        )
        mismatched = [
            t.task_id
            for t in manifest.tasks
            if t.payload.get("gt_matches_dataset_answer") is False
        ]
        if mismatched:
            print(
                f"  NOTE: {len(mismatched)} MATH-500 tasks where the boxed answer extracted "
                f"from the reference solution differs from the dataset 'answer' column "
                f"(flagged in payload.gt_matches_dataset_answer, kept)"
            )
        return 0

    manifest = Manifest.read(args.manifest)
    print(f"manifest '{manifest.manifest_id}' created {manifest.created_at}")
    print(f"  content_hash : {manifest.content_hash}")
    print(f"  tasks        : {len(manifest.tasks)}")
    print(f"  by suite     : {counts_by(manifest.suite_pairs())}")
    print(f"  by domain    : {counts_by(manifest.domain_pairs())}")
    print(f"  choice suites: {sorted(CHOICE_SUITES & set(dict(manifest.suite_pairs()).values()))}")
    for split_name in sorted(manifest.splits):
        if not split_name.startswith("lodo_"):
            print(f"  split {split_name}: {len(manifest.splits[split_name])}")
    for spec in manifest.tasks[: args.sample]:
        print(f"\n--- {spec.task_id} [{spec.suite}/{spec.domain}] gt={spec.ground_truth!r}")
        print(spec.prompt[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
