"""From three named pools to every four-agent pool the answer bank can support.

Every claim in `Docs/paper/CLAIM_EVIDENCE_MATRIX.md` rests on n = 3 pools per suite, and three of
them have exactly one dissenting cell each. With n = 3 a 2-versus-1 split is a coin toss. This
module turns the anecdotes into a distribution, at zero API cost, by exploiting the same two-stage
factorization the rest of the project runs on: `single_expert` and `independent_majority` are
deterministic functions of banked independent answers, so any coalition of any subset of the densely
banked agents can be replayed without a model call.

Three things make that more than a loop over `sharing_null.headroom_against_shared_member_null`.

``agent ids are pool-local, and the tie-breaks depend on them``
    Each run numbers its own members 0..3, so the same model is agent 2 in one run and agent 0 in
    another. Plurality ties break on the lowest supporting agent id and the expert predictor breaks
    ties the same way, so a naive re-numbering would silently change outcomes. :func:`global_order`
    derives one ordering by topological sort over the named pools' internal orders and asserts that
    it is consistent with all of them, which is what lets the sweep reuse a single id space and
    still reproduce the recorded episodes exactly.

``the coalitions overlap, so the work is shared``
    70 four-agent pools have 70 x 15 = 1,050 coalitions between them, but only
    C(8,1)+C(8,2)+C(8,3)+C(8,4) = 162 of them are distinct. Voting is computed once per distinct
    coalition and gathered per pool, which is a 6.5-fold saving before any vectorization.

``the null has to be joint, not per-pool``
    The 70 pools are drawn from 8 agents, so two pools sharing three members are nearly the same
    pool. Bonferroni over 70 tests would be wrong in the conservative direction and treating them as
    independent would be wrong in the dangerous one. Because `sharing_null` simulates at the *agent*
    level, one simulated 8-agent bank yields a statistic for all 70 pools at once, and repeating
    that
    gives the null distribution of the entire sweep with member sharing across pools exact by
    construction. That licenses a family-wise statement no per-cell test can make. See
    `Docs/preregistrations/2026-08-11-pool-sweep.md` section 3.

The plurality rule here is a vectorized restatement of `sharing_null._vote`, and
:func:`check_vote_agreement` exists to assert they agree rather than to hope so.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from .sharing_null import ABSTAIN, UNIQUE_BASE, TaskSpace

_UNREACHABLE = np.iinfo(np.int32).max


# ---- agent identity ---------------------------------------------------------------------------


def global_order(pool_orders: Mapping[str, Sequence[str]]) -> list[str]:
    """One agent ordering consistent with every pool's internal ordering.

    Raises if no such ordering exists, because in that case the sweep cannot reproduce the recorded
    episodes' tie-breaks under any single id space and the caller must be told rather than handed a
    subtly different grid.
    """
    successors: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for sequence in pool_orders.values():
        nodes.update(sequence)
        for i, earlier in enumerate(sequence):
            successors[earlier].update(sequence[i + 1 :])

    indegree = dict.fromkeys(nodes, 0)
    for later_set in successors.values():
        for node in later_set:
            indegree[node] += 1

    # Ties in the topological order are broken by name so the result is reproducible.
    available = sorted(n for n in nodes if indegree[n] == 0)
    order: list[str] = []
    while available:
        node = available.pop(0)
        order.append(node)
        for later in sorted(successors[node]):
            indegree[later] -= 1
            if indegree[later] == 0:
                available.append(later)
                available.sort()

    if len(order) != len(nodes):
        cycle = sorted(nodes - set(order))
        raise ValueError(
            "no agent ordering is consistent with every pool's internal order; "
            f"the pools disagree about {cycle}. Tie-breaks cannot be reproduced under one id space."
        )
    return order


# ---- the substrate ----------------------------------------------------------------------------


@dataclass
class Substrate:
    """Everything about one suite that does not depend on which pool is being scored."""

    suite: str
    agents: list[str]
    """Agent names in global id order; the global id of an agent is its index here."""
    tasks: list[str]
    classes: np.ndarray
    """(n_agents, n_tasks) equivalence-class id per answer, ABSTAIN for a non-answer."""
    correct: np.ndarray
    """(n_agents, n_tasks) float 0/1, the banked independent outcome."""
    cost: np.ndarray
    """(n_agents, n_tasks) USD, repriced from token buckets against the run's price snapshot."""
    correct_class: np.ndarray
    """(n_tasks,) the class that scores correct, or -2 where no agent found it."""
    wrong_classes: list[np.ndarray]
    wrong_weights: list[np.ndarray]
    domain_index: np.ndarray
    """(n_tasks,) index into ``capabilities``."""
    capabilities: list[str]
    domain_of_task: list[str]
    competence: np.ndarray
    """(n_agents,) calibration accuracy, the tie-break weight the recorded episodes used."""
    calibration: np.ndarray
    """Column indices of the manifest calibration split."""
    test: np.ndarray
    domain_accuracy: np.ndarray
    """(n_agents, n_capabilities) calibration accuracy by capability, for the expert predictor."""
    embeddings: np.ndarray | None = None
    embedding_method: str = ""
    embedding_fallback: bool = False

    @property
    def n_agents(self) -> int:
        return len(self.agents)

    @property
    def n_tasks(self) -> int:
        return len(self.tasks)


def build_substrate(
    *,
    suite: str,
    answers_by_agent: Mapping[str, Mapping[str, Any]],
    cost_by_agent: Mapping[str, Mapping[str, float]],
    spaces: Mapping[str, TaskSpace],
    space_agent_ids: Mapping[str, int],
    domain_of: Mapping[str, str],
    calibration_task_ids: Sequence[str],
    test_task_ids: Sequence[str],
    agent_order: Sequence[str],
) -> Substrate:
    """Assemble the agent-by-task tables the sweep reads.

    ``spaces`` is keyed by task and its ``classes`` map is keyed by whatever agent id was used when
    the equivalence classes were built; ``space_agent_ids`` maps agent *name* to that id, so the
    caller can build the class structure once with one numbering and reindex here.
    """
    agents = list(agent_order)
    tasks = sorted(
        set.intersection(*[set(answers_by_agent[a]) for a in agents]) & set(spaces) & set(domain_of)
    )
    if len(agents) < 4 or len(tasks) < 8:
        raise ValueError(f"{suite}: need at least four agents and eight shared tasks")

    classes = np.array(
        [[spaces[t].classes.get(space_agent_ids[a], ABSTAIN) for t in tasks] for a in agents]
    )
    correct = np.array([[float(bool(answers_by_agent[a][t])) for t in tasks] for a in agents])
    cost = np.array([[float(cost_by_agent[a].get(t, 0.0)) for t in tasks] for a in agents])

    capabilities = sorted({domain_of[t] for t in tasks})
    domain_index = np.array([capabilities.index(domain_of[t]) for t in tasks])

    index = {t: i for i, t in enumerate(tasks)}
    calibration = np.array(sorted(index[t] for t in set(calibration_task_ids) if t in index))
    test = np.array(sorted(index[t] for t in set(test_task_ids) if t in index))
    if len(calibration) < 4 or len(test) < 4:
        raise ValueError(f"{suite}: manifest split leaves too few tasks")

    competence = correct[:, calibration].mean(axis=1)
    domain_accuracy = np.zeros((len(agents), len(capabilities)))
    for c in range(len(capabilities)):
        columns = calibration[domain_index[calibration] == c]
        if columns.size:
            domain_accuracy[:, c] = correct[:, columns].mean(axis=1)

    return Substrate(
        suite=suite,
        agents=agents,
        tasks=tasks,
        classes=classes,
        correct=correct,
        cost=cost,
        correct_class=np.array(
            [spaces[t].correct_class if spaces[t].correct_class is not None else -2 for t in tasks]
        ),
        wrong_classes=[np.asarray(spaces[t].wrong_classes) for t in tasks],
        wrong_weights=[np.asarray(spaces[t].wrong_weights) for t in tasks],
        domain_index=domain_index,
        capabilities=capabilities,
        domain_of_task=[domain_of[t] for t in tasks],
        competence=competence,
        calibration=calibration,
        test=test,
        domain_accuracy=domain_accuracy,
    )


# ---- coalitions -------------------------------------------------------------------------------


@dataclass
class CoalitionIndex:
    """Every distinct coalition over the banked agents, grouped by size for vectorization."""

    coalitions: list[tuple[int, ...]]
    position: dict[tuple[int, ...], int]
    members_by_size: dict[int, np.ndarray]
    """size -> (n_of_that_size, size) array of agent ids."""
    rows_by_size: dict[int, np.ndarray]
    """size -> the rows of ``coalitions`` those members correspond to."""

    @classmethod
    def build(cls, n_agents: int, max_size: int = 4) -> "CoalitionIndex":
        coalitions: list[tuple[int, ...]] = []
        for size in range(1, max_size + 1):
            coalitions.extend(itertools.combinations(range(n_agents), size))
        position = {c: i for i, c in enumerate(coalitions)}

        members_by_size: dict[int, np.ndarray] = {}
        rows_by_size: dict[int, np.ndarray] = {}
        for size in range(1, max_size + 1):
            rows = [i for i, c in enumerate(coalitions) if len(c) == size]
            rows_by_size[size] = np.asarray(rows)
            members_by_size[size] = np.asarray([coalitions[i] for i in rows])
        return cls(coalitions, position, members_by_size, rows_by_size)


def vote_outcomes(
    classes: np.ndarray, index: CoalitionIndex, competence: np.ndarray, correct_class: np.ndarray
) -> np.ndarray:
    """Plurality outcome of every coalition on every task, as a (n_coalitions, n_tasks) 0/1 array.

    A vectorized restatement of `sharing_null._vote`: abstentions do not vote, ties break on summed
    calibration competence and then on the lowest supporting agent id. Per member we compute how
    many coalition members share its class, their summed competence and their lowest id; every
    member of a class carries the same triple, so selecting a member selects a class.

    The three criteria are applied as **exact successive filters** rather than packed into one
    weighted key. `_vote` compares summed competences with ``==``, so two classes whose sums differ
    by one unit in the last place are *not* tied there and never reach the id rule. Any packing
    fine enough to preserve that would be dominated by the id term, so the tiers are kept separate;
    the competence sum is likewise accumulated in ascending member order, which is the order
    `_vote`'s ``sum`` uses, so the two agree bit for bit.
    """
    n_tasks = classes.shape[1]
    outcomes = np.zeros((len(index.coalitions), n_tasks))

    for size, members in index.members_by_size.items():
        if not members.size:
            continue
        taken = classes[members]  # (n, size, n_tasks)
        valid = taken != ABSTAIN
        agree = (
            (taken[:, :, None, :] == taken[:, None, :, :])
            & valid[:, :, None, :]
            & valid[:, None, :, :]
        )

        count = agree.sum(axis=2).astype(float)
        support_competence = np.zeros_like(count)
        for k in range(size):
            support_competence += agree[:, :, k, :] * competence[members][:, None, k, None]
        lowest = np.where(agree, members[:, None, :, None], _UNREACHABLE).min(axis=2)

        # Tier 1: the largest bloc. Tier 2: among those, the greatest summed competence.
        # Tier 3: among those, the lowest supporting agent id.
        blocs = np.where(valid, count, -np.inf)
        leaders = valid & (blocs == blocs.max(axis=1, keepdims=True))
        scored = np.where(leaders, support_competence, -np.inf)
        leaders &= scored == scored.max(axis=1, keepdims=True)
        best = np.where(leaders, lowest, _UNREACHABLE).argmin(axis=1)

        winner = np.take_along_axis(taken, best[:, None, :], axis=1)[:, 0, :]
        outcomes[index.rows_by_size[size]] = (
            valid.any(axis=1) & (winner == correct_class[None, :])
        ).astype(float)
    return outcomes


def check_vote_agreement(
    substrate: Substrate, index: CoalitionIndex, spaces: Sequence[TaskSpace], sample: int = 24
) -> float:
    """Agreement between the vectorized plurality and `sharing_null`'s reference implementation."""
    from .sharing_null import _vote

    rng = np.random.default_rng(0)
    fast = vote_outcomes(substrate.classes, index, substrate.competence, substrate.correct_class)
    rows = rng.choice(len(index.coalitions), size=min(sample, len(index.coalitions)), replace=False)
    competence = {a: float(substrate.competence[a]) for a in range(substrate.n_agents)}

    agree = total = 0
    for row in rows:
        coalition = index.coalitions[row]
        for t in range(substrate.n_tasks):
            winner = _vote(
                [substrate.classes[a, t] for a in coalition], coalition, competence
            )
            slow = float(winner is not None and winner == spaces[t].correct_class)
            agree += int(slow == fast[row, t])
            total += 1
    return agree / max(total, 1)


# ---- the expert predictor, as a lookup ---------------------------------------------------------


def expert_table(pool: Sequence[int], substrate: Substrate) -> np.ndarray:
    """Which member `single_expert` consults, per coalition of ``pool`` and per capability.

    A faithful lookup form of `pool.expert.ExpertPredictor.predict` under the ``domain`` strategy:
    the per-capability calibration argmax over the *pool* if it is in the coalition, else the pool's
    global calibration argmax if it is, else the best available member by capability accuracy, then
    global accuracy, then lowest id. The predictor is fitted over the pool because that is what the
    runner does, so the choice depends on the pool and not only on the coalition.

    **A capability with fewer than `MIN_CALIBRATION_TASKS_PER_DOMAIN` calibration tasks has no
    per-capability entry at all** and falls straight through to the global expert, because at that
    size the estimate is noise. `crosscap240` never triggers this — every capability has twenty
    calibration tasks — but `hard366` splits into twelve domains and several are below the floor, so
    omitting it silently changes which member `single_expert` consults there.

    Returns (n_coalitions_of_pool, n_capabilities) of global agent ids, indexed by the pool's
    coalitions in :func:`pool_coalitions` order.
    """
    from ..pool.expert import MIN_CALIBRATION_TASKS_PER_DOMAIN

    members = list(pool)
    n_capabilities = len(substrate.capabilities)

    accuracy = substrate.domain_accuracy[members]  # (4, n_capabilities)
    overall = substrate.competence[members]
    calibration_domains = substrate.domain_index[substrate.calibration]
    # Ties on the lowest global id, matching `fit_expert_predictor`'s `-a`.
    preferred: list[int | None] = []
    for c in range(n_capabilities):
        if int(np.sum(calibration_domains == c)) < MIN_CALIBRATION_TASKS_PER_DOMAIN:
            preferred.append(None)
        else:
            preferred.append(members[int(np.lexsort((members, -accuracy[:, c]))[0])])
    global_expert = members[int(np.lexsort((members, -overall))[0])]

    coalitions = pool_coalitions(pool)
    table = np.zeros((len(coalitions), n_capabilities), dtype=int)
    for row, coalition in enumerate(coalitions):
        present = set(coalition)
        for c in range(n_capabilities):
            if preferred[c] is not None and preferred[c] in present:
                table[row, c] = preferred[c]
            elif global_expert in present:
                table[row, c] = global_expert
            else:
                candidates = list(coalition)
                keys = np.array([substrate.domain_accuracy[a, c] for a in candidates])
                secondary = np.array([substrate.competence[a] for a in candidates])
                table[row, c] = candidates[
                    int(np.lexsort((candidates, -secondary, -keys))[0])
                ]
    return table


def pool_coalitions(pool: Sequence[int]) -> list[tuple[int, ...]]:
    """The 15 non-empty coalitions of a four-agent pool, in the order the grids use."""
    members = sorted(pool)
    return [
        c
        for size in range(1, len(members) + 1)
        for c in itertools.combinations(members, size)
    ]


def organization_outcomes(
    pool: Sequence[int],
    *,
    substrate: Substrate,
    index: CoalitionIndex,
    votes: np.ndarray,
    agent_correct: np.ndarray,
    experts: np.ndarray,
) -> np.ndarray:
    """(30, n_tasks) outcomes for one pool: 15 majority-vote rows then 15 single-expert rows.

    ``votes`` is the coalition-by-task table from :func:`vote_outcomes` and ``agent_correct`` the
    agent-by-task correctness the experts are scored against; passing both explicitly is what lets a
    simulation reuse this function unchanged.

    Row order is protocol-major with ``independent_majority`` first, matching the label sort
    ``independent_majority[...] < single_expert[...]`` that `routing._grid` produces.
    """
    coalitions = pool_coalitions(pool)
    rows = np.array([index.position[c] for c in coalitions])
    vote_block = votes[rows]

    chosen = experts[:, substrate.domain_index]  # (15, n_tasks) agent id per task
    expert_block = np.take_along_axis(agent_correct, chosen, axis=0)
    return np.vstack([vote_block, expert_block])


# ---- headroom, over many pools at once ---------------------------------------------------------


def headroom(
    organizations: np.ndarray, calibration: np.ndarray, test: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Oracle headroom against the calibration-picked and the best-on-test organization.

    ``organizations`` is (..., n_organizations, n_tasks), so a whole sweep of pools is scored in one
    call. The second variant is the one the paper uses: measuring against the calibration pick
    conflates interaction with the winner's curse (D-037).
    """
    per_task_best = organizations[..., test].max(axis=-2).mean(axis=-1)
    calibration_means = organizations[..., calibration].mean(axis=-1)
    picked = calibration_means.argmax(axis=-1)
    test_means = organizations[..., test].mean(axis=-1)
    picked_accuracy = np.take_along_axis(test_means, picked[..., None], axis=-1)[..., 0]
    return (
        100.0 * (per_task_best - picked_accuracy),
        100.0 * (per_task_best - test_means.max(axis=-1)),
    )


def simulate_bank(
    substrate: Substrate,
    probability: np.ndarray,
    abstain_rate: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """One draw of the whole agent bank under the additive no-interaction model.

    Returns (class ids, correctness). Correct answers take the task's correct class; wrong answers
    are drawn from the task's own empirical distribution over wrong classes so that per-task
    distractor concentration survives, and a task with no observed wrong class gets a per-agent
    unique id so two agents never form a voting bloc by accident.
    """
    n_agents, n_tasks = substrate.correct.shape
    is_correct = rng.random((n_agents, n_tasks)) < probability
    abstains = (~is_correct) & (rng.random((n_agents, n_tasks)) < abstain_rate[:, None])

    simulated = np.full((n_agents, n_tasks), ABSTAIN)
    draws = rng.random((n_agents, n_tasks))
    for t in range(n_tasks):
        options, weights = substrate.wrong_classes[t], substrate.wrong_weights[t]
        column = np.where(is_correct[:, t], substrate.correct_class[t], ABSTAIN)
        if options.size:
            picked = options[np.searchsorted(np.cumsum(weights), draws[:, t] * weights.sum())
                             .clip(0, options.size - 1)]
        else:
            picked = UNIQUE_BASE + np.arange(n_agents)
        column = np.where(is_correct[:, t], column, np.where(abstains[:, t], ABSTAIN, picked))
        simulated[:, t] = column
    return simulated, is_correct.astype(float)


def additive_agent_model(substrate: Substrate) -> tuple[np.ndarray, np.ndarray]:
    """Fit sigma(alpha_agent + beta_task) and the per-agent abstention propensity.

    Fitted on every task rather than on calibration only, matching
    `sharing_null.headroom_against_shared_member_null`: the null's job is to reproduce the observed
    marginals as closely as possible so that any excess is attributable to interaction, and fitting
    on everything makes the test conservative, which is the safe direction for "there is no excess".
    """
    from sklearn.linear_model import LogisticRegression

    n_agents, n_tasks = substrate.correct.shape
    design = np.zeros((n_agents * n_tasks, n_agents + n_tasks))
    rows = np.arange(n_agents * n_tasks)
    design[rows, np.repeat(np.arange(n_agents), n_tasks)] = 1.0
    design[rows, n_agents + np.tile(np.arange(n_tasks), n_agents)] = 1.0

    model = LogisticRegression(C=10.0, max_iter=2000)
    model.fit(design, substrate.correct.reshape(-1))
    probability = model.predict_proba(design)[:, 1].reshape(n_agents, n_tasks)

    abstain_rate = np.array(
        [
            float(
                np.mean(
                    [
                        substrate.classes[a, t] == ABSTAIN
                        for t in range(n_tasks)
                        if not substrate.correct[a, t]
                    ]
                    or [0.0]
                )
            )
            for a in range(n_agents)
        ]
    )
    return probability, abstain_rate


@dataclass
class SweepNull:
    """The joint null distribution of the whole sweep."""

    pools: list[tuple[int, ...]]
    observed: np.ndarray
    """(n_pools,) observed headroom against the best organization on test."""
    observed_vs_picked: np.ndarray
    replicates: np.ndarray
    """(n_simulations, n_pools) null headroom against the best organization on test."""
    replicates_vs_picked: np.ndarray
    n_simulations: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def excess(self) -> np.ndarray:
        return self.observed - self.replicates.mean(axis=0)

    @property
    def p_values(self) -> np.ndarray:
        """Per-pool p-values. Correct marginally; not a family-wise statement on their own."""
        return (1 + (self.replicates >= self.observed[None, :]).sum(axis=0)) / (
            1 + self.n_simulations
        )

    def family_wise(self) -> dict[str, Any]:
        """Does the observed cloud of 70 pools sit inside the cloud the null produces?

        Four summaries of the same comparison, each answering an objection to the others: the median
        pool, the most extreme pool, the count clearing a nominal per-pool threshold, and the mean.
        Each observed statistic is referred to the distribution of the *same* statistic over
        replicates, so member sharing across pools is preserved rather than assumed away.
        """
        excess_replicates = self.replicates - self.replicates.mean(axis=0, keepdims=True)
        observed_excess = self.excess

        def tail(observed_value: float, null_values: np.ndarray) -> float:
            return float((1 + int(np.sum(null_values >= observed_value))) / (1 + len(null_values)))

        nominal = float(
            np.mean(
                self.p_values
                <= 0.05
            )
        )
        null_nominal = np.array(
            [
                float(
                    np.mean(
                        (self.replicates >= self.replicates[i][None, :]).mean(axis=0)
                        <= 0.05
                    )
                )
                for i in range(min(self.n_simulations, 200))
            ]
        )
        return {
            "median_excess": float(np.median(observed_excess)),
            "p_median": tail(
                float(np.median(observed_excess)), np.median(excess_replicates, axis=1)
            ),
            "mean_excess": float(observed_excess.mean()),
            "p_mean": tail(float(observed_excess.mean()), excess_replicates.mean(axis=1)),
            "max_excess": float(observed_excess.max()),
            "p_max": tail(float(observed_excess.max()), excess_replicates.max(axis=1)),
            "frac_pools_p_below_05": nominal,
            "null_frac_pools_p_below_05_mean": float(null_nominal.mean()),
            "null_frac_pools_p_below_05_q95": float(np.quantile(null_nominal, 0.95)),
            "n_pools": len(self.pools),
            "n_simulations": self.n_simulations,
        }
