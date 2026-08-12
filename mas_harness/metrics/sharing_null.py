"""A no-interaction null that reproduces member sharing, by simulating agents and voting for real.

`headroom_against_no_interaction` in [`routing.py`](routing.py) draws each *organization's* outcome
independently given fitted marginals. That is the wrong independence. Organizations share members:
`independent_majority` over {a1,a2,a3} and over {a1,a2,a4} agree whenever a1 and a2 do, and a
coalition containing a weak member inherits that weakness everywhere it appears. Real per-task
maxima are therefore smaller than independent maxima at the same marginals, so the null's oracle is
too generous and the test under-rejects. It is very likely why the SWE-bench matrix came out *below*
its null rather than at it. See `Docs/paper/FRAMEWORK.md` section 3.4.

The two-stage design fixes this for free. Simulate at the *agent* level under an additive
agent-by-task model, then push the simulated answers through the real protocol function. Member
sharing is then exact, because a single simulated answer for a1 feeds every organization containing
a1, and the only thing removed is agent-by-task interaction - precisely the content of "different
agents suit different tasks".

Three pieces of observed structure are preserved deliberately, because removing them would test more
than one thing at once:

* **Per-task difficulty**, via the task main effect.
* **Per-agent strength and abstention propensity**, via the agent main effect and a per-agent
  abstention rate among its non-correct outputs.
* **How concentrated the wrong answers are on each task.** This matters more than it looks: on a
  multiple-choice item four agents can converge on one distractor and outvote a correct minority,
  while on an open-response maths item wrong answers are nearly all distinct and a single correct
  member wins. Simulated wrong answers are drawn from the task's own empirical distribution over
  wrong answer classes, so plurality voting stays meaningful.

What is destroyed is any association between *which* agent fails and *which* task it fails on.

Answers are represented by integer equivalence-class ids rather than strings. The class structure is
computed once per task with the task's own equivalence relation, which is SymPy-backed for maths and
far too slow to call inside a simulation loop. Grouping by precomputed class assumes the relation is
transitive; the assumption is checked rather than trusted, by replaying the observed answers through
the same code path and comparing against the recorded episodes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..records.schema import AnswerRecord, EpisodeRecord

ABSTAIN = -1
# Wrong answers nobody else gave are encoded above this, one per agent slot, so that two agents
# independently producing an unseen wrong answer never accidentally form a voting bloc.
UNIQUE_BASE = 1_000_000


@dataclass
class TaskSpace:
    """The answers observed on one task, as equivalence classes."""

    classes: dict[int, int]
    """Agent id -> the class it answered, or ABSTAIN."""
    correct_class: int | None
    """The class that scores correct, if any agent found it."""
    wrong_classes: tuple[int, ...]
    """Distinct wrong classes observed, for sampling."""
    wrong_weights: tuple[float, ...]
    """Their observed frequencies, so distractor concentration is preserved."""


def build_task_spaces(
    answers: Sequence[AnswerRecord], evaluators: Mapping[str, Any]
) -> dict[str, TaskSpace]:
    """Group each task's observed answers into equivalence classes, once."""
    by_task: dict[str, list[AnswerRecord]] = defaultdict(list)
    for record in answers:
        by_task[record.task_id].append(record)

    spaces: dict[str, TaskSpace] = {}
    for task, records in by_task.items():
        evaluator = evaluators[task]
        # Canonical representatives, in agent order, so class ids are reproducible.
        representatives: list[str] = []
        classes: dict[int, int] = {}
        for record in sorted(records, key=lambda r: r.agent_id):
            answer = (record.extracted_answer or "").strip()
            if not answer:
                classes[record.agent_id] = ABSTAIN
                continue
            for index, canonical in enumerate(representatives):
                if evaluator.equivalent(answer, canonical):
                    classes[record.agent_id] = index
                    break
            else:
                representatives.append(answer)
                classes[record.agent_id] = len(representatives) - 1

        correct = [
            index
            for index, canonical in enumerate(representatives)
            if evaluator.score_extracted(canonical)
        ]
        wrong = Counter(
            c for c in classes.values() if c != ABSTAIN and c not in correct
        )
        total = sum(wrong.values()) or 1
        spaces[task] = TaskSpace(
            classes=classes,
            correct_class=correct[0] if correct else None,
            wrong_classes=tuple(wrong),
            wrong_weights=tuple(v / total for v in wrong.values()),
        )
    return spaces


def _vote(
    classes: Sequence[int], agents: Sequence[int], competence: Mapping[int, float]
) -> int | None:
    """Plurality over equivalence classes, with the tie-breaks `protocols/voting.py` uses.

    Abstentions are excluded; ties break on summed calibration competence, then on the lowest
    supporting agent id, so there is no random branch.
    """
    support: dict[int, list[int]] = defaultdict(list)
    for agent, klass in zip(agents, classes, strict=True):
        if klass != ABSTAIN:
            support[klass].append(agent)
    if not support:
        return None

    top = max(len(v) for v in support.values())
    leaders = [k for k, v in support.items() if len(v) == top]
    if len(leaders) == 1:
        return leaders[0]

    scored = {k: sum(competence.get(a, 0.0) for a in support[k]) for k in leaders}
    best = max(scored.values())
    leaders = [k for k in leaders if scored[k] == best]
    if len(leaders) == 1:
        return leaders[0]
    return min(leaders, key=lambda k: min(support[k]))


def _organization_outcomes(
    agent_classes: np.ndarray,
    *,
    agents: Sequence[int],
    tasks: Sequence[str],
    spaces: Sequence[TaskSpace],
    coalitions: Sequence[tuple[int, ...]],
    experts: Mapping[tuple[str, tuple[int, ...]], int],
    protocols: Sequence[str],
    competence: Mapping[int, float],
) -> np.ndarray:
    """Apply the protocols to an agent-by-task table of class ids.

    ``agent_classes`` is indexed [agent slot, task]. The returned matrix is
    [organization, task], with organizations ordered protocol-major to match ``protocols``.
    """
    slot = {agent: i for i, agent in enumerate(agents)}
    outcomes = np.zeros((len(protocols) * len(coalitions), len(tasks)))

    for t, space in enumerate(spaces):
        column = agent_classes[:, t]
        row = 0
        for protocol in protocols:
            for coalition in coalitions:
                if protocol == "independent_majority":
                    winner = _vote(
                        [column[slot[a]] for a in coalition], coalition, competence
                    )
                else:
                    # The expert predictor reads calibration accuracy by domain and never inspects
                    # the current task's answers, so the recorded choice is reusable as is.
                    expert = experts.get((tasks[t], coalition))
                    if expert is None:
                        expert = max(coalition, key=lambda a: (competence.get(a, 0.0), -a))
                    winner = column[slot[expert]]
                    if winner == ABSTAIN:
                        winner = None
                outcomes[row, t] = float(
                    winner is not None and winner == space.correct_class
                )
                row += 1
    return outcomes


def _headroom(correct: np.ndarray, train: np.ndarray, test: np.ndarray) -> tuple[float, float]:
    best = correct[:, test].max(axis=0).mean()
    fixed = int(np.argmax(correct[:, train].mean(axis=1)))
    return (
        100.0 * float(best - correct[fixed, test].mean()),
        100.0 * float(best - correct[:, test].mean(axis=1).max()),
    )


def headroom_against_shared_member_null(
    answers: Sequence[AnswerRecord],
    episodes: Sequence[EpisodeRecord],
    *,
    evaluators: Mapping[str, Any],
    train_task_ids: Sequence[str],
    test_task_ids: Sequence[str],
    protocols: Sequence[str] = ("independent_majority", "single_expert"),
    n_simulations: int = 200,
    seed: int = 20260810,
) -> dict[str, Any]:
    """Observed oracle headroom against a null that keeps member sharing and removes interaction.

    The additive model is fit to every task rather than to the training tasks only. That is
    deliberate and matches `headroom_against_no_interaction`: the null's job is to reproduce the
    observed marginals as closely as possible, so that any excess is attributable to interaction
    rather than to the null fitting badly. It also makes the test conservative, which is the safe
    direction for a claim of the form "there is no excess".
    """
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(seed)
    spaces = build_task_spaces(answers, evaluators)

    observed_by_agent: dict[int, dict[str, bool]] = defaultdict(dict)
    for record in answers:
        observed_by_agent[record.agent_id][record.task_id] = bool(record.correct)
    agents = sorted(observed_by_agent)
    tasks = sorted(set.intersection(*[set(o) for o in observed_by_agent.values()]))
    tasks = [t for t in tasks if t in spaces]
    if len(agents) < 2 or len(tasks) < 8:
        return {"note": "too few agents or tasks"}

    train = np.array([i for i, t in enumerate(tasks) if t in set(train_task_ids)])
    test = np.array([i for i, t in enumerate(tasks) if t in set(test_task_ids)])
    if len(train) < 4 or len(test) < 4:
        return {"note": "too few tasks in a split"}

    usable = [e for e in episodes if e.intervention.kind == "none" and e.protocol_id in protocols]
    coalitions = sorted({tuple(sorted(e.coalition)) for e in usable})
    experts = {
        (e.task_id, tuple(sorted(e.coalition))): int(v)
        for e in usable
        if e.protocol_id == "single_expert"
        and (v := e.protocol_meta.get("selected_agent_id")) is not None
    }
    competence = {
        a: float(np.mean([observed_by_agent[a][tasks[i]] for i in train])) for a in agents
    }

    # ---- observed table, and a check that the fast path reproduces the recorded episodes ----
    observed_classes = np.array(
        [[spaces[t].classes.get(a, ABSTAIN) for t in tasks] for a in agents]
    )
    kwargs = {
        "agents": agents,
        "tasks": tasks,
        "spaces": [spaces[t] for t in tasks],
        "coalitions": coalitions,
        "experts": experts,
        "protocols": protocols,
        "competence": competence,
    }
    replayed = _organization_outcomes(observed_classes, **kwargs)

    recorded = {
        (e.protocol_id, tuple(sorted(e.coalition)), e.task_id): bool(e.correct) for e in usable
    }
    index = {t: i for i, t in enumerate(tasks)}
    agree = total = 0
    row = 0
    for protocol in protocols:
        for coalition in coalitions:
            for task, t in index.items():
                truth = recorded.get((protocol, coalition, task))
                if truth is not None:
                    total += 1
                    agree += int(bool(replayed[row, t]) == truth)
            row += 1
    agreement = agree / total if total else float("nan")

    observed, observed_vs_best = _headroom(replayed, train, test)

    # ---- the null: additive agent-by-task model, propagated through the protocols ----
    correctness = np.array([[observed_by_agent[a][t] for t in tasks] for a in agents], dtype=float)
    n_agent, n_task = correctness.shape
    design = np.zeros((n_agent * n_task, n_agent + n_task))
    rows = np.arange(n_agent * n_task)
    design[rows, np.repeat(np.arange(n_agent), n_task)] = 1.0
    design[rows, n_agent + np.tile(np.arange(n_task), n_agent)] = 1.0
    labels = correctness.reshape(-1)
    if len(set(labels.tolist())) < 2:
        return {"observed_headroom": observed, "note": "degenerate outcomes"}

    model = LogisticRegression(C=10.0, max_iter=2000)
    model.fit(design, labels)
    probability = model.predict_proba(design)[:, 1].reshape(n_agent, n_task)

    # Abstention is treated as an agent-level propensity among non-correct outputs: a main effect,
    # consistent with removing only the agent-by-task association.
    abstain_rate = np.array(
        [
            np.mean(
                [
                    spaces[t].classes.get(a, ABSTAIN) == ABSTAIN
                    for t in tasks
                    if not observed_by_agent[a][t]
                ]
                or [0.0]
            )
            for a in agents
        ]
    )

    wrong_choices = [
        (np.array(spaces[t].wrong_classes), np.array(spaces[t].wrong_weights)) for t in tasks
    ]
    correct_class = np.array(
        [spaces[t].correct_class if spaces[t].correct_class is not None else -2 for t in tasks]
    )

    null = np.empty(n_simulations)
    null_vs_best = np.empty(n_simulations)
    for i in range(n_simulations):
        simulated = np.full((n_agent, n_task), ABSTAIN)
        is_correct = rng.random((n_agent, n_task)) < probability
        abstains = (~is_correct) & (rng.random((n_agent, n_task)) < abstain_rate[:, None])
        for t in range(n_task):
            options, weights = wrong_choices[t]
            for a in range(n_agent):
                if is_correct[a, t]:
                    simulated[a, t] = correct_class[t]
                elif abstains[a, t]:
                    simulated[a, t] = ABSTAIN
                elif options.size:
                    simulated[a, t] = int(rng.choice(options, p=weights))
                else:
                    simulated[a, t] = UNIQUE_BASE + a
        null[i], null_vs_best[i] = _headroom(
            _organization_outcomes(simulated, **kwargs), train, test
        )

    excess = observed - float(null.mean())
    excess_vs_best = observed_vs_best - float(null_vs_best.mean())
    return {
        "n_agents": n_agent,
        "n_test_tasks": len(test),
        "n_organizations": len(protocols) * len(coalitions),
        "replay_agreement_with_recorded_episodes": agreement,
        "observed_headroom": observed,
        "null_headroom_mean": float(null.mean()),
        "null_headroom_q95": float(np.quantile(null, 0.95)),
        "excess_over_null": excess,
        "p_value": float(np.mean(null >= observed)),
        "observed_headroom_over_best": observed_vs_best,
        "null_headroom_over_best_mean": float(null_vs_best.mean()),
        "excess_over_null_over_best": excess_vs_best,
        "p_value_over_best": float(np.mean(null_vs_best >= observed_vs_best)),
        "n_simulations": n_simulations,
    }
