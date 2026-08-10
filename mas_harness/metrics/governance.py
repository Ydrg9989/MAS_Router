"""Epistemic governance metrics: expert utilization, dilution, rescue, influence, leverage.

Implements the definitions in the research report. Two conventions run through all of them and
both are load-bearing:

**The expert is predicted, not revealed.** Every metric below defaults to ``e_hat(x)``, chosen
on calibration data (D-004). The oracle variant is computed too, but only as an upper bound,
and the two are never pooled. A dilution figure measured against an oracle answers a question
no router can act on.

**Influence is causal, not correlational.** ``I_i(x, g)`` is the flip rate of the final decision
under ``do(mask message_i)`` — an actual counterfactual replay from the same answer bank, not a
regression of outcome on who spoke. This is what the intervention layer exists to supply.

The central scientific quantity is the *gap* between competence and influence. An agent can be
the most competent member and have no influence, or the least competent and dominate. Leverage
and the influence-misalignment divergence below are the two ways the report asks for that gap to
be reported.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

from ..records.schema import EpisodeRecord

EPS = 1e-12


# ---- helpers ------------------------------------------------------------------------------


def observational(episodes: Iterable[EpisodeRecord]) -> list[EpisodeRecord]:
    """Episodes with no intervention applied. The baseline for every counterfactual."""
    return [e for e in episodes if e.intervention.kind == "none"]


def _expert_id(episode: EpisodeRecord, *, use_oracle: bool) -> int | None:
    return episode.oracle_expert_id if use_oracle else episode.predicted_expert_id


def _expert_was_correct(episode: EpisodeRecord, *, use_oracle: bool) -> bool | None:
    """Whether the reference expert answered this task correctly, or None if undefined."""
    expert = _expert_id(episode, use_oracle=use_oracle)
    if expert is None:
        return None
    return episode.individual_correct.get(str(expert))


def _agrees_with_expert(episode: EpisodeRecord, *, use_oracle: bool) -> bool | None:
    """Whether the team's final answer matches the expert's correctness outcome.

    We compare on *correctness* rather than on answer strings because the episode record does
    not retain each member's answer text, only whether it was right. When the expert was correct,
    the team agrees with the expert exactly when the team is also correct. When the expert was
    wrong, agreement is not identifiable from correctness alone, so this returns None and the
    metric that needs it restricts to the identifiable case.
    """
    expert_correct = _expert_was_correct(episode, use_oracle=use_oracle)
    if expert_correct is None:
        return None
    if expert_correct:
        return bool(episode.correct)
    return None


# ---- the report's core rates ----------------------------------------------------------------


@dataclass
class GovernanceRates:
    """Expert utilization, dilution and rescue for one (protocol, coalition) cell."""

    protocol_id: str
    n_episodes: int = 0

    # Tasks where the reference expert answered correctly.
    n_expert_correct: int = 0
    # ... and the team also got it right. Expert utilization.
    n_expert_correct_team_correct: int = 0

    # Tasks where the reference expert answered incorrectly.
    n_expert_wrong: int = 0
    # ... and the team got it right anyway. Rescue.
    n_expert_wrong_team_correct: int = 0

    n_no_expert: int = 0
    n_parse_failed: int = 0
    team_accuracy: float = float("nan")
    expert_accuracy: float = float("nan")
    use_oracle: bool = False

    @property
    def expert_utilization_rate(self) -> float:
        """``EUR = P(team correct | expert correct)``.

        The report's reading: how often the team actually uses a correct answer that was
        already available inside it. An EUR below 1 means available correctness was thrown
        away.
        """
        if self.n_expert_correct == 0:
            return float("nan")
        return self.n_expert_correct_team_correct / self.n_expert_correct

    @property
    def dilution_rate(self) -> float:
        """``Dilution = P(team wrong | expert correct) = 1 - EUR``.

        Reported separately from EUR despite being its complement, because it is the quantity
        the report's go/no-go threshold is stated in (>= 15%).
        """
        eur = self.expert_utilization_rate
        return float("nan") if np.isnan(eur) else 1.0 - eur

    @property
    def rescue_rate(self) -> float:
        """``Rescue = P(team correct | expert wrong)``.

        The upside of aggregation. Dilution and rescue must always be read together: a protocol
        can have high dilution and still be worth using if its rescue rate is higher.
        """
        if self.n_expert_wrong == 0:
            return float("nan")
        return self.n_expert_wrong_team_correct / self.n_expert_wrong

    @property
    def net_expert_effect(self) -> float:
        """Team accuracy minus expert accuracy: what the protocol adds over the expert alone."""
        if np.isnan(self.team_accuracy) or np.isnan(self.expert_accuracy):
            return float("nan")
        return self.team_accuracy - self.expert_accuracy

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "expert_utilization_rate": self.expert_utilization_rate,
                "dilution_rate": self.dilution_rate,
                "rescue_rate": self.rescue_rate,
                "net_expert_effect": self.net_expert_effect,
            }
        )
        return payload


def governance_rates(
    episodes: Sequence[EpisodeRecord], *, use_oracle: bool = False
) -> GovernanceRates:
    """EUR, dilution and rescue over one protocol's observational episodes."""
    episodes = observational(episodes)
    if not episodes:
        raise ValueError("no observational episodes supplied")
    protocol_ids = {e.protocol_id for e in episodes}
    if len(protocol_ids) > 1:
        raise ValueError(
            f"governance_rates expects one protocol at a time, got {sorted(protocol_ids)}"
        )

    rates = GovernanceRates(protocol_id=next(iter(protocol_ids)), use_oracle=use_oracle)
    rates.n_episodes = len(episodes)
    rates.n_parse_failed = sum(1 for e in episodes if e.parse_failed)
    rates.team_accuracy = float(np.mean([e.correct for e in episodes]))

    expert_outcomes: list[bool] = []
    for episode in episodes:
        expert_correct = _expert_was_correct(episode, use_oracle=use_oracle)
        if expert_correct is None:
            rates.n_no_expert += 1
            continue
        expert_outcomes.append(expert_correct)
        if expert_correct:
            rates.n_expert_correct += 1
            rates.n_expert_correct_team_correct += int(episode.correct)
        else:
            rates.n_expert_wrong += 1
            rates.n_expert_wrong_team_correct += int(episode.correct)

    rates.expert_accuracy = float(np.mean(expert_outcomes)) if expert_outcomes else float("nan")
    return rates


def expert_identification_rate(
    episodes: Sequence[EpisodeRecord], *, key: str = "declared_best_agent_id"
) -> dict[str, Any]:
    """``ExpertID``: how often a protocol's *declared* expert matches the reference.

    Only meaningful for protocols that declare one (explicit expert voting, chair selection).
    Reported against both the oracle and the calibrated prediction, because a protocol can be
    good at identifying who happens to be right on this task while being useless at predicting
    who will be right in general.
    """
    episodes = observational(episodes)
    declared = [(e, e.protocol_meta.get(key)) for e in episodes]
    usable = [(e, d) for e, d in declared if d is not None]
    if not usable:
        return {
            "n_declaring": 0,
            "note": f"no episode carries protocol_meta[{key!r}]; protocol declares no expert",
        }

    matches_oracle = [
        int(d == e.oracle_expert_id) for e, d in usable if e.oracle_expert_id is not None
    ]
    matches_predicted = [
        int(d == e.predicted_expert_id) for e, d in usable if e.predicted_expert_id is not None
    ]
    # Was the declared agent actually right on this task, regardless of who else was?
    declared_correct = [
        int(bool(e.individual_correct.get(str(d)))) for e, d in usable
    ]
    return {
        "n_declaring": len(usable),
        "n_episodes": len(episodes),
        "declaration_rate": len(usable) / len(episodes),
        "match_oracle_expert": float(np.mean(matches_oracle)) if matches_oracle else float("nan"),
        "match_predicted_expert": float(np.mean(matches_predicted))
        if matches_predicted
        else float("nan"),
        "declared_agent_was_correct": float(np.mean(declared_correct)),
    }


# ---- causal influence -----------------------------------------------------------------------


@dataclass
class InfluenceProfile:
    """Per-agent causal influence and its relation to competence, for one protocol."""

    protocol_id: str
    influence: dict[int, float] = field(default_factory=dict)
    n_pairs: dict[int, int] = field(default_factory=dict)
    competence: dict[int, float] = field(default_factory=dict)
    # Directional breakdown: did masking the agent help or hurt?
    flips_to_correct: dict[int, int] = field(default_factory=dict)
    flips_to_wrong: dict[int, int] = field(default_factory=dict)

    @property
    def agents(self) -> list[int]:
        return sorted(self.influence)

    def influence_share(self) -> dict[int, float]:
        total = sum(self.influence.values())
        if total <= EPS:
            n = max(1, len(self.influence))
            return dict.fromkeys(self.influence, 1.0 / n)
        return {a: v / total for a, v in self.influence.items()}

    def competence_share(self) -> dict[int, float]:
        total = sum(self.competence.get(a, 0.0) for a in self.influence)
        if total <= EPS:
            n = max(1, len(self.influence))
            return dict.fromkeys(self.influence, 1.0 / n)
        return {a: self.competence.get(a, 0.0) / total for a in self.influence}

    def leverage(self) -> dict[int, float]:
        """``L_i``: influence share divided by competence share.

        Above 1 means the agent moves the decision more than its competence warrants; below 1
        means it is under-weighted. Defined as a ratio rather than a difference so it is
        comparable across coalitions of different sizes and across protocols with different
        overall flip rates.
        """
        influence = self.influence_share()
        competence = self.competence_share()
        return {a: influence[a] / max(competence[a], EPS) for a in self.agents}

    def misalignment_kl(self) -> float:
        """``KL(influence || competence)`` over the agent distribution.

        Zero exactly when influence is allocated in proportion to competence. The report's
        single-number summary of governance quality: a protocol with a large divergence is
        letting something other than competence decide.
        """
        influence = self.influence_share()
        competence = self.competence_share()
        return float(
            sum(
                influence[a] * np.log(max(influence[a], EPS) / max(competence[a], EPS))
                for a in self.agents
            )
        )

    def spearman_influence_vs_competence(self) -> float:
        from scipy import stats

        if len(self.agents) < 3:
            return float("nan")
        influence = [self.influence[a] for a in self.agents]
        competence = [self.competence.get(a, 0.0) for a in self.agents]
        if len(set(influence)) < 2 or len(set(competence)) < 2:
            return float("nan")
        return float(stats.spearmanr(influence, competence).statistic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "influence": {str(a): self.influence[a] for a in self.agents},
            "n_pairs": {str(a): self.n_pairs.get(a, 0) for a in self.agents},
            "competence": {str(a): self.competence.get(a, float("nan")) for a in self.agents},
            "influence_share": {str(a): v for a, v in sorted(self.influence_share().items())},
            "competence_share": {str(a): v for a, v in sorted(self.competence_share().items())},
            "leverage": {str(a): v for a, v in sorted(self.leverage().items())},
            "flips_to_correct": {str(a): self.flips_to_correct.get(a, 0) for a in self.agents},
            "flips_to_wrong": {str(a): self.flips_to_wrong.get(a, 0) for a in self.agents},
            "misalignment_kl": self.misalignment_kl(),
            "spearman_influence_vs_competence": self.spearman_influence_vs_competence(),
            "mean_flip_rate": float(np.mean(list(self.influence.values())))
            if self.influence
            else float("nan"),
            "max_flip_rate": float(max(self.influence.values()))
            if self.influence
            else float("nan"),
        }


def influence_profile(
    episodes: Sequence[EpisodeRecord],
    *,
    competence: dict[int, float] | None = None,
    kind: str = "mask",
) -> InfluenceProfile:
    """Causal influence per agent, from paired observational and interventional episodes.

    Pairing is on ``(task, coalition, seed)``: the intervention episode differs from its
    baseline only in the ``do(.)`` that was applied, so a decision flip is attributable to that
    edit. Unpaired interventions are skipped rather than compared against a pooled mean, which
    would reintroduce exactly the confounding the design removes.
    """
    protocol_ids = {e.protocol_id for e in episodes}
    if len(protocol_ids) > 1:
        raise ValueError(
            f"influence_profile expects one protocol at a time, got {sorted(protocol_ids)}"
        )

    baselines: dict[tuple[str, str, int], EpisodeRecord] = {}
    for episode in episodes:
        if episode.intervention.kind == "none":
            key = (episode.task_id, "-".join(map(str, episode.coalition)), episode.seed)
            baselines[key] = episode

    flips: dict[int, list[int]] = defaultdict(list)
    to_correct: dict[int, int] = defaultdict(int)
    to_wrong: dict[int, int] = defaultdict(int)

    for episode in episodes:
        if episode.intervention.kind != kind:
            continue
        target = episode.intervention.target_agent_id
        if target is None:
            continue
        key = (episode.task_id, "-".join(map(str, episode.coalition)), episode.seed)
        baseline = baselines.get(key)
        if baseline is None:
            continue
        flipped = int(episode.final_answer != baseline.final_answer)
        flips[target].append(flipped)
        if flipped:
            if episode.correct and not baseline.correct:
                to_correct[target] += 1
            elif baseline.correct and not episode.correct:
                to_wrong[target] += 1

    profile = InfluenceProfile(
        protocol_id=next(iter(protocol_ids)) if protocol_ids else "",
        competence=dict(competence or {}),
        flips_to_correct=dict(to_correct),
        flips_to_wrong=dict(to_wrong),
    )
    for agent_id, outcomes in flips.items():
        profile.influence[agent_id] = float(np.mean(outcomes))
        profile.n_pairs[agent_id] = len(outcomes)
    return profile


def substitution_uptake(episodes: Sequence[EpisodeRecord]) -> dict[str, Any]:
    """Does injecting a correct answer at a member's position change the decision?

    The report's evidence-completeness test. A protocol that ignores a correct message
    substituted into a member slot is failing at information integration regardless of its
    headline accuracy, and the per-position breakdown shows whether uptake depends on *who*
    carries the message.
    """
    baselines = {
        (e.task_id, "-".join(map(str, e.coalition)), e.seed): e
        for e in episodes
        if e.intervention.kind == "none"
    }

    per_agent: dict[int, list[bool]] = defaultdict(list)
    fixed: dict[int, int] = defaultdict(int)
    n_pairs = 0
    for episode in episodes:
        if episode.intervention.kind != "substitute_correct":
            continue
        target = episode.intervention.target_agent_id
        if target is None:
            continue
        baseline = baselines.get(
            (episode.task_id, "-".join(map(str, episode.coalition)), episode.seed)
        )
        if baseline is None:
            continue
        n_pairs += 1
        per_agent[target].append(bool(episode.correct))
        if episode.correct and not baseline.correct:
            fixed[target] += 1

    if not n_pairs:
        return {"n_pairs": 0, "note": "no paired substitute_correct episodes"}

    return {
        "n_pairs": n_pairs,
        "accuracy_after_injection_by_agent": {
            str(a): float(np.mean(v)) for a, v in sorted(per_agent.items())
        },
        "overall_accuracy_after_injection": float(
            np.mean([ok for values in per_agent.values() for ok in values])
        ),
        "n_repaired_by_agent": {str(a): fixed.get(a, 0) for a in sorted(per_agent)},
        "n_repaired_total": sum(fixed.values()),
    }


def order_sensitivity(episodes: Sequence[EpisodeRecord]) -> dict[str, Any]:
    """How often permuting presentation order alone changes the decision.

    A protocol whose output depends on order is not aggregating evidence, it is responding to
    position. This is a property of the protocol, so it is reported per protocol rather than
    per agent.
    """
    baselines = {
        (e.task_id, "-".join(map(str, e.coalition)), e.seed): e
        for e in episodes
        if e.intervention.kind == "none"
    }
    flips: list[int] = []
    accuracy_changes: list[int] = []
    for episode in episodes:
        if episode.intervention.kind != "reorder":
            continue
        baseline = baselines.get(
            (episode.task_id, "-".join(map(str, episode.coalition)), episode.seed)
        )
        if baseline is None:
            continue
        flips.append(int(episode.final_answer != baseline.final_answer))
        accuracy_changes.append(int(episode.correct) - int(baseline.correct))

    if not flips:
        return {"n_pairs": 0, "note": "no paired reorder episodes"}
    return {
        "n_pairs": len(flips),
        "order_flip_rate": float(np.mean(flips)),
        "mean_accuracy_change": float(np.mean(accuracy_changes)),
        "n_order_made_correct": int(sum(1 for c in accuracy_changes if c > 0)),
        "n_order_made_wrong": int(sum(1 for c in accuracy_changes if c < 0)),
    }


# ---- protocol comparison ---------------------------------------------------------------------


def protocol_spread(episodes: Sequence[EpisodeRecord]) -> dict[str, Any]:
    """Accuracy of each protocol on the tasks where every protocol ran.

    Restricting to the common task set is what makes the spread a paired comparison. Computing
    each protocol's accuracy over whatever tasks it happens to have and then differencing would
    confound protocol effects with coverage differences from failed or budget-truncated runs.
    """
    episodes = observational(episodes)
    if not episodes:
        return {"n_protocols": 0, "note": "no observational episodes"}

    by_protocol: dict[str, dict[str, bool]] = defaultdict(dict)
    for episode in episodes:
        by_protocol[episode.protocol_id][
            f"{episode.task_id}|{'-'.join(map(str, episode.coalition))}|{episode.seed}"
        ] = bool(episode.correct)

    common = set.intersection(*(set(v) for v in by_protocol.values())) if by_protocol else set()
    accuracies = {
        protocol_id: float(np.mean([outcomes[k] for k in sorted(common)]))
        for protocol_id, outcomes in sorted(by_protocol.items())
    } if common else {}

    spread = (max(accuracies.values()) - min(accuracies.values())) if accuracies else float("nan")
    return {
        "n_protocols": len(by_protocol),
        "n_common_items": len(common),
        "accuracy_by_protocol": accuracies,
        "spread_pp": spread * 100 if accuracies else float("nan"),
        "best_protocol": max(accuracies, key=accuracies.get) if accuracies else None,
        "worst_protocol": min(accuracies, key=accuracies.get) if accuracies else None,
        "paired_outcomes": {p: {k: v[k] for k in sorted(common)} for p, v in by_protocol.items()},
    }


def protocol_dominance(episodes: Sequence[EpisodeRecord]) -> dict[str, Any]:
    """Per-domain best protocol, and how often one protocol wins everywhere.

    The report's kill criterion for the delegation direction is a single configuration
    dominating above 70-75%: if one protocol is best regardless of the task, there is nothing
    for a task representation to route over.
    """
    episodes = observational(episodes)
    by_domain: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for episode in episodes:
        by_domain[episode.domain][episode.protocol_id].append(bool(episode.correct))

    winners: dict[str, str] = {}
    accuracy: dict[str, dict[str, float]] = {}
    for domain, protocols in sorted(by_domain.items()):
        means = {p: float(np.mean(v)) for p, v in sorted(protocols.items())}
        accuracy[domain] = means
        if means:
            winners[domain] = max(means, key=means.get)

    if not winners:
        return {"n_domains": 0, "note": "no observational episodes"}

    counts: dict[str, int] = defaultdict(int)
    for winner in winners.values():
        counts[winner] += 1
    top = max(counts.values())
    return {
        "n_domains": len(winners),
        "accuracy_by_domain": accuracy,
        "best_protocol_by_domain": winners,
        "win_counts": dict(sorted(counts.items())),
        "dominant_protocol": max(counts, key=counts.get),
        "dominance_fraction": top / len(winners),
    }
