"""Delegation-equivalent task representations.

The delegation direction asks whether tasks should be represented by *which organizations work
on them* rather than by what they are about. This module builds the three task similarity
spaces the report contrasts and measures how much they disagree.

``semantic``
    Cosine similarity of frozen text embeddings of the task prompt. What a conventional router
    uses.
``capability``
    Similarity of the vector of per-agent independent correctness. Two tasks are close if the
    same agents can solve them.
``organizational``
    Similarity of the *delegation fingerprint*: the utility vector over configurations. Two
    tasks are close if the same team-and-protocol arrangements work on them. This is the
    representation the direction proposes.

The claim the report needs is that the organizational space is not a relabelling of the
semantic one. That is exactly what :func:`compare_spaces` measures: a low correlation between
the similarity matrices plus a high rate of differing nearest neighbours. Both are required —
correlation alone can be low while the neighbourhoods agree, and it is the neighbourhoods that
determine what a nearest-neighbour router actually does.

Embeddings are optional. Without ``sentence-transformers`` installed the semantic space falls
back to character n-gram TF-IDF, which is weaker but keeps the comparison runnable offline. The
fallback is always reported, never silent, because a low semantic-organizational correlation is
much less interesting if the semantic space is bad.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from ..records.schema import AnswerRecord, EpisodeRecord
from .utility import (
    DEFAULT_LAMBDA_PER_USD,
    DEFAULT_MU_PER_SECOND,
    Configuration,
    ConfigurationStats,
    configuration_stats,
)


@dataclass
class TaskSpace:
    """A similarity structure over tasks, plus how it was built."""

    name: str
    task_ids: list[str]
    features: np.ndarray  # (n_tasks, n_features)
    method: str
    fallback_used: bool = False

    def similarity(self) -> np.ndarray:
        """Cosine similarity, with zero vectors treated as similar to nothing."""
        norms = np.linalg.norm(self.features, axis=1, keepdims=True)
        safe = np.where(norms < 1e-12, 1.0, norms)
        unit = self.features / safe
        similarity = unit @ unit.T
        # A task with no signal (an all-zero row) should not be reported as similar to itself.
        dead = (norms.ravel() < 1e-12)
        similarity[dead, :] = 0.0
        similarity[:, dead] = 0.0
        np.fill_diagonal(similarity, 1.0)
        return np.clip(similarity, -1.0, 1.0)

    def nearest_neighbours(self, k: int = 1) -> dict[str, list[str]]:
        similarity = self.similarity()
        np.fill_diagonal(similarity, -np.inf)
        out: dict[str, list[str]] = {}
        for index, task_id in enumerate(self.task_ids):
            order = np.argsort(-similarity[index])[:k]
            out[task_id] = [self.task_ids[j] for j in order]
        return out


def semantic_space(
    task_ids: Sequence[str], prompts: Sequence[str], *, model_name: str | None = None
) -> TaskSpace:
    """Frozen text embeddings of the task prompts, with an offline fallback."""
    model_name = model_name or "sentence-transformers/all-MiniLM-L6-v2"
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        features = np.asarray(model.encode(list(prompts), show_progress_bar=False), dtype=float)
        return TaskSpace(
            name="semantic",
            task_ids=list(task_ids),
            features=features,
            method=f"sentence-transformers:{model_name}",
        )
    except Exception as exc:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=4096)
        features = vectorizer.fit_transform(list(prompts)).toarray()
        return TaskSpace(
            name="semantic",
            task_ids=list(task_ids),
            features=np.asarray(features, dtype=float),
            method=f"tfidf char_wb 3-5 (fallback: {type(exc).__name__})",
            fallback_used=True,
        )


def capability_space(answers: Iterable[AnswerRecord]) -> TaskSpace:
    """Per-task vector of which agents solved it independently."""
    by_task: dict[str, dict[int, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for record in answers:
        by_task[record.task_id][record.agent_id].append(bool(record.correct))

    task_ids = sorted(by_task)
    agent_ids = sorted({a for task in by_task.values() for a in task})
    features = np.zeros((len(task_ids), len(agent_ids)), dtype=float)
    for row, task_id in enumerate(task_ids):
        for column, agent_id in enumerate(agent_ids):
            outcomes = by_task[task_id].get(agent_id)
            # Averaged over seeds, so a task solved on two of three seeds sits between 0 and 1.
            features[row, column] = float(np.mean(outcomes)) if outcomes else 0.0
    return TaskSpace(
        name="capability",
        task_ids=task_ids,
        features=features,
        method=f"per-agent independent accuracy over {len(agent_ids)} agents",
    )


def organizational_space(
    episodes: Iterable[EpisodeRecord],
    *,
    lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
    mu_per_second: float = DEFAULT_MU_PER_SECOND,
) -> TaskSpace:
    """Per-task delegation fingerprint: the utility of every configuration on that task."""
    episodes = list(episodes)
    stats = configuration_stats(episodes)
    configurations = sorted(stats, key=lambda c: c.label)
    task_ids = sorted({t for entry in stats.values() for t in entry.per_task_correct})

    features = np.zeros((len(task_ids), len(configurations)), dtype=float)
    for row, task_id in enumerate(task_ids):
        for column, configuration in enumerate(configurations):
            entry = stats[configuration]
            if task_id in entry.per_task_correct:
                features[row, column] = entry.task_utility(
                    task_id, lambda_per_usd=lambda_per_usd, mu_per_second=mu_per_second
                )
    # Centre each column so a configuration that is uniformly good does not dominate the
    # geometry; similarity should reflect *differential* fit, not overall configuration quality.
    features = features - features.mean(axis=0, keepdims=True)
    return TaskSpace(
        name="organizational",
        task_ids=task_ids,
        features=features,
        method=(
            f"utility over {len(configurations)} configurations, column-centred, "
            f"lambda={lambda_per_usd}, mu={mu_per_second}"
        ),
    )


def delegation_fingerprints(
    episodes: Iterable[EpisodeRecord], **weights
) -> dict[str, dict[str, float]]:
    """Per-task utility of each configuration, keyed by label. Human-readable form."""
    episodes = list(episodes)
    stats = configuration_stats(episodes)
    task_ids = sorted({t for entry in stats.values() for t in entry.per_task_correct})
    return {
        task_id: {
            configuration.label: entry.task_utility(task_id, **weights)
            for configuration, entry in sorted(stats.items(), key=lambda kv: kv[0].label)
            if task_id in entry.per_task_correct
        }
        for task_id in task_ids
    }


def align(spaces: Sequence[TaskSpace]) -> list[TaskSpace]:
    """Restrict every space to the tasks all of them cover, in one shared order."""
    if not spaces:
        return []
    common = sorted(set.intersection(*(set(space.task_ids) for space in spaces)))
    if not common:
        raise ValueError(
            "the supplied task spaces share no tasks; cannot compare them. "
            f"Sizes: {[(s.name, len(s.task_ids)) for s in spaces]}"
        )
    aligned: list[TaskSpace] = []
    for space in spaces:
        index = {task_id: position for position, task_id in enumerate(space.task_ids)}
        rows = [index[task_id] for task_id in common]
        aligned.append(
            TaskSpace(
                name=space.name,
                task_ids=common,
                features=space.features[rows],
                method=space.method,
                fallback_used=space.fallback_used,
            )
        )
    return aligned


def compare_spaces(a: TaskSpace, b: TaskSpace, *, k: int = 1) -> dict[str, Any]:
    """Correlate two similarity structures and compare their nearest neighbours.

    Correlation is computed over the strict upper triangle only, since the diagonal is 1 by
    construction and including it inflates agreement.
    """
    from scipy import stats as scipy_stats

    a, b = align([a, b])
    similarity_a, similarity_b = a.similarity(), b.similarity()
    triangle = np.triu_indices(len(a.task_ids), k=1)
    flat_a, flat_b = similarity_a[triangle], similarity_b[triangle]

    if len(flat_a) < 3 or len(set(flat_a)) < 2 or len(set(flat_b)) < 2:
        pearson = spearman = float("nan")
    else:
        pearson = float(np.corrcoef(flat_a, flat_b)[0, 1])
        spearman = float(scipy_stats.spearmanr(flat_a, flat_b).statistic)

    neighbours_a, neighbours_b = a.nearest_neighbours(k), b.nearest_neighbours(k)
    differing = [
        task_id
        for task_id in a.task_ids
        if not set(neighbours_a[task_id]) & set(neighbours_b[task_id])
    ]

    return {
        "space_a": a.name,
        "space_b": b.name,
        "method_a": a.method,
        "method_b": b.method,
        "fallback_used": a.fallback_used or b.fallback_used,
        "n_tasks": len(a.task_ids),
        "n_pairs": int(len(flat_a)),
        "pearson_similarity_correlation": pearson,
        "spearman_similarity_correlation": spearman,
        "k": k,
        "frac_differing_nearest_neighbours": len(differing) / max(1, len(a.task_ids)),
        "n_differing_nearest_neighbours": len(differing),
    }


def nearest_neighbour_routing_regret(
    space: TaskSpace,
    stats: dict[Configuration, ConfigurationStats],
    *,
    train_task_ids: Sequence[str],
    test_task_ids: Sequence[str],
    lambda_per_usd: float = DEFAULT_LAMBDA_PER_USD,
    mu_per_second: float = DEFAULT_MU_PER_SECOND,
) -> dict[str, Any]:
    """Route each test task to the best configuration for its nearest *training* task.

    This is the operational test of a task space: not "do these similarity matrices differ" but
    "does routing by this similarity produce better decisions". A space can differ from the
    semantic one and still be useless; only regret settles it.
    """
    from .utility import decision_regret, fixed_best_selection

    weights = {"lambda_per_usd": lambda_per_usd, "mu_per_second": mu_per_second}
    position = {task_id: index for index, task_id in enumerate(space.task_ids)}
    train = [t for t in train_task_ids if t in position]
    test = [t for t in test_task_ids if t in position]
    if not train or not test:
        return {"note": "train or test tasks absent from the space", "n_test": len(test)}

    similarity = space.similarity()

    # Best configuration for each training task, from observed per-task utilities.
    best_for_train: dict[str, Configuration] = {}
    for task_id in train:
        utilities = {
            configuration: entry.task_utility(task_id, **weights)
            for configuration, entry in stats.items()
            if task_id in entry.per_task_correct
        }
        if utilities:
            best_for_train[task_id] = max(utilities, key=utilities.get)

    chosen: dict[str, Configuration] = {}
    for task_id in test:
        row = similarity[position[task_id]]
        ranked = sorted(
            (t for t in best_for_train), key=lambda t: -row[position[t]]
        )
        if ranked:
            chosen[task_id] = best_for_train[ranked[0]]

    test_stats = {
        configuration: ConfigurationStats(
            configuration=configuration,
            n=sum(1 for t in test if t in entry.per_task_correct),
            accuracy=float(
                np.mean([entry.per_task_correct[t] for t in test if t in entry.per_task_correct])
            )
            if any(t in entry.per_task_correct for t in test)
            else float("nan"),
            mean_cost_usd=float(
                np.mean([entry.per_task_cost.get(t, 0.0) for t in test])
            ),
            mean_latency_s=float(np.mean([entry.per_task_latency.get(t, 0.0) for t in test])),
            per_task_correct={
                t: entry.per_task_correct[t] for t in test if t in entry.per_task_correct
            },
            per_task_cost={t: entry.per_task_cost.get(t, 0.0) for t in test},
            per_task_latency={t: entry.per_task_latency.get(t, 0.0) for t in test},
        )
        for configuration, entry in stats.items()
    }

    routed = decision_regret(test_stats, chosen=chosen, **weights)
    fixed = decision_regret(
        test_stats, chosen=fixed_best_selection(test_stats, **weights), **weights
    )
    improvement = (
        fixed.get("mean_regret", float("nan")) - routed.get("mean_regret", float("nan"))
    )
    return {
        "space": space.name,
        "n_train": len(train),
        "n_test": len(test),
        "routed_mean_regret": routed.get("mean_regret"),
        "fixed_best_mean_regret": fixed.get("mean_regret"),
        "regret_improvement_over_fixed_best": improvement,
        "routing_beats_fixed_best": bool(improvement > 0),
        "n_distinct_configurations_chosen": len(set(chosen.values())),
    }
