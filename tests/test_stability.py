"""Winner reproducibility, checked against planted signal and planted noise.

The metric exists because `protocol_dominance` cannot tell a real per-group winner from the argmax
of noise. So the load-bearing test is not that the metric runs: it is that the metric *rejects*
data with no structure in it, on exactly the shape of data where dominance was fooled.
"""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics.stability import (
    MIN_REPRODUCIBILITY,
    MIN_TASKS_PER_GROUP,
    winner_stability,
)

from .test_metrics import episode

DOMAINS = ["physics", "chemistry", "biology", "math"]
PROTOCOLS = ["alpha", "beta", "gamma", "delta"]


def build(outcomes: dict[str, dict[str, bool]], domain_of: dict[str, str]):
    """Episodes from a protocol -> task -> correct table."""
    return [
        episode(
            task_id=task,
            protocol_id=protocol,
            correct=correct,
            domain=domain_of[task],
        )
        for protocol, tasks in outcomes.items()
        for task, correct in tasks.items()
    ]


def coin_flips(n_tasks_per_domain: int, seed: int):
    """Every protocol independently right with probability 0.5. No structure whatsoever."""
    rng = np.random.default_rng(seed)
    domain_of, outcomes = {}, {p: {} for p in PROTOCOLS}
    for domain in DOMAINS:
        for i in range(n_tasks_per_domain):
            task = f"{domain}::{i}"
            domain_of[task] = domain
            for p in PROTOCOLS:
                outcomes[p][task] = bool(rng.random() < 0.5)
    return outcomes, domain_of


class TestItRejectsNoise:
    def test_pure_noise_is_not_reproducible(self):
        """The case that motivated the module: dominance looks fine, reproducibility does not."""
        outcomes, domain_of = coin_flips(30, seed=1)
        report = winner_stability(
            build(outcomes, domain_of), n_splits=200, n_permutations=120, seed=7
        )

        assert report.reproducibility_p > 0.05
        assert not report.winners_are_reproducible
        assert "NO EVIDENCE" in report.verdict

    def test_noise_still_produces_varied_winners(self):
        """Why dominance alone passes: argmax over noise looks like healthy variety."""
        outcomes, domain_of = coin_flips(30, seed=2)
        report = winner_stability(
            build(outcomes, domain_of), n_splits=100, n_permutations=60, seed=7
        )

        assert report.dominance <= 0.75, "noise should not look dominated"
        assert not report.winners_are_reproducible, "yet there is nothing real here"

    def test_thin_groups_are_excluded_not_averaged(self):
        """One-task domains are where spurious winners come from, so they must not count."""
        outcomes, domain_of = coin_flips(30, seed=3)
        for i, domain in enumerate(["thin_a", "thin_b"]):
            task = f"{domain}::0"
            domain_of[task] = domain
            for p in PROTOCOLS:
                outcomes[p][task] = i == 0

        report = winner_stability(
            build(outcomes, domain_of), n_splits=40, n_permutations=20, seed=7
        )

        assert set(report.excluded_groups) == {"thin_a", "thin_b"}
        assert {g.group for g in report.groups} == set(DOMAINS)


class TestItDetectsSignal:
    def test_a_planted_per_domain_winner_reproduces(self):
        """Each domain has a genuinely best protocol; the metric must find it."""
        rng = np.random.default_rng(11)
        domain_of, outcomes = {}, {p: {} for p in PROTOCOLS}
        best = dict(zip(DOMAINS, PROTOCOLS, strict=True))
        for domain in DOMAINS:
            for i in range(40):
                task = f"{domain}::{i}"
                domain_of[task] = domain
                for p in PROTOCOLS:
                    rate = 0.9 if p == best[domain] else 0.4
                    outcomes[p][task] = bool(rng.random() < rate)

        report = winner_stability(
            build(outcomes, domain_of), n_splits=200, n_permutations=120, seed=7
        )

        assert report.winners_are_reproducible
        assert report.reproducibility > report.null_reproducibility
        assert {g.winner for g in report.groups} == set(PROTOCOLS)
        assert report.dominance == pytest.approx(0.25)
        assert "EVIDENCE" in report.verdict and "NO EVIDENCE" not in report.verdict

    def test_one_protocol_best_everywhere_is_reproducible_but_not_delegable(self):
        """Reproducible winners are necessary, not sufficient: nothing to route over."""
        rng = np.random.default_rng(12)
        domain_of, outcomes = {}, {p: {} for p in PROTOCOLS}
        for domain in DOMAINS:
            for i in range(40):
                task = f"{domain}::{i}"
                domain_of[task] = domain
                for p in PROTOCOLS:
                    outcomes[p][task] = bool(rng.random() < (0.9 if p == "alpha" else 0.3))

        report = winner_stability(
            build(outcomes, domain_of), n_splits=200, n_permutations=120, seed=7
        )

        assert report.winners_are_reproducible
        assert report.dominance == pytest.approx(1.0)
        assert "NO EVIDENCE" in report.verdict
        assert "wins nearly everywhere" in report.verdict


class TestItSeparatesRealVarietyFromNoiseAroundOneWinner:
    """The distinction that decided the MVP data: high average reproducibility can come entirely
    from the groups a single dominant configuration wins, while the groups that depart from it are
    noise. Averaging the two conceals the only quantity routing depends on."""

    def build_one_best_plus_noisy_departures(self, seed: int):
        """`alpha` is genuinely best in most domains; two domains are pure coin flips."""
        rng = np.random.default_rng(seed)
        domains = [*DOMAINS, "noisy_a", "noisy_b"]
        domain_of, outcomes = {}, {p: {} for p in PROTOCOLS}
        for domain in domains:
            noisy = domain.startswith("noisy")
            for i in range(40):
                task = f"{domain}::{i}"
                domain_of[task] = domain
                for p in PROTOCOLS:
                    rate = 0.5 if noisy else (0.9 if p == "alpha" else 0.35)
                    outcomes[p][task] = bool(rng.random() < rate)
        return outcomes, domain_of

    def test_noisy_departures_are_reported_as_no_evidence(self):
        outcomes, domain_of = self.build_one_best_plus_noisy_departures(seed=21)
        report = winner_stability(
            build(outcomes, domain_of), n_splits=300, n_permutations=120, seed=7
        )

        assert report.dominant_configuration == "alpha"
        assert report.winners_are_reproducible, "the average is carried by alpha's domains"
        assert report.reproducibility_dominant > 0.9
        assert report.reproducibility_off_dominant < 0.5
        assert not report.variety_is_reproducible
        assert "NO EVIDENCE" in report.verdict
        assert "noise around a single best configuration" in report.verdict

    def test_a_collapsed_null_does_not_let_noise_through(self):
        """The floor's reason for existing, found when the metric passed 134 SWE-bench systems.

        With a large configuration family the argmax almost never survives a resplit even under real
        structure, so the permutation null falls towards zero. A relative test alone then accepts an
        off-dominant reproducibility of 0.009 for clearing a 0.008 null.
        """
        rng = np.random.default_rng(23)
        many = [f"c{i:03d}" for i in range(60)]
        domain_of, outcomes = {}, {c: {} for c in many}
        for domain in [*DOMAINS, "noisy_a", "noisy_b"]:
            for i in range(30):
                task = f"{domain}::{i}"
                domain_of[task] = domain
                for c in many:
                    rate = 0.5 if domain.startswith("noisy") else (0.9 if c == "c000" else 0.3)
                    outcomes[c][task] = bool(rng.random() < rate)

        report = winner_stability(
            build(outcomes, domain_of), n_splits=200, n_permutations=60, seed=7
        )

        assert report.null_reproducibility < 0.2, "the null has collapsed, as intended"
        assert report.reproducibility_off_dominant < MIN_REPRODUCIBILITY
        assert not report.variety_is_reproducible
        assert "NO EVIDENCE" in report.verdict

    def test_real_departures_pass(self):
        """Same shape, but the two departing domains have a genuine different winner."""
        rng = np.random.default_rng(22)
        domains = [*DOMAINS, "beta_land_a", "beta_land_b"]
        domain_of, outcomes = {}, {p: {} for p in PROTOCOLS}
        for domain in domains:
            champion = "beta" if domain.startswith("beta_land") else "alpha"
            for i in range(40):
                task = f"{domain}::{i}"
                domain_of[task] = domain
                for p in PROTOCOLS:
                    outcomes[p][task] = bool(rng.random() < (0.9 if p == champion else 0.35))

        report = winner_stability(
            build(outcomes, domain_of), n_splits=300, n_permutations=120, seed=7
        )

        assert report.dominant_configuration == "alpha"
        assert report.n_off_dominant == 2
        assert report.reproducibility_off_dominant > 0.9
        assert report.variety_is_reproducible
        assert "EVIDENCE" in report.verdict and "NO EVIDENCE" not in report.verdict


class TestMechanics:
    def test_grouping_by_suite_pools_domains(self):
        outcomes, domain_of = coin_flips(10, seed=4)
        episodes = build(outcomes, domain_of)
        by_domain = winner_stability(episodes, n_splits=40, n_permutations=20, seed=7)
        by_suite = winner_stability(
            episodes, grouping="suite", n_splits=40, n_permutations=20, seed=7
        )

        assert len(by_domain.groups) == len(DOMAINS)
        assert len(by_suite.groups) == 1, "the fixture uses a single suite"
        assert by_suite.groups[0].n_tasks == sum(g.n_tasks for g in by_domain.groups)

    def test_a_group_below_the_floor_cannot_be_split(self):
        outcomes, domain_of = coin_flips(MIN_TASKS_PER_GROUP - 1, seed=5)
        report = winner_stability(
            build(outcomes, domain_of), n_splits=20, n_permutations=10, seed=7
        )

        assert report.groups == []
        assert "no group had enough tasks" in report.verdict

    def test_results_are_deterministic_given_a_seed(self):
        outcomes, domain_of = coin_flips(20, seed=6)
        episodes = build(outcomes, domain_of)
        a = winner_stability(episodes, n_splits=60, n_permutations=30, seed=99)
        b = winner_stability(episodes, n_splits=60, n_permutations=30, seed=99)

        assert a.reproducibility == b.reproducibility
        assert a.reproducibility_p == b.reproducibility_p
        assert [g.winner for g in a.groups] == [g.winner for g in b.groups]

    def test_interventions_are_excluded(self):
        """Masked and substituted episodes are counterfactuals, not observations."""
        from mas_harness.records.schema import InterventionSpec

        outcomes, domain_of = coin_flips(10, seed=8)
        episodes = build(outcomes, domain_of)
        poisoned = [
            episode(
                task_id=t,
                protocol_id="alpha",
                correct=True,
                domain=d,
                intervention=InterventionSpec(kind="mask", target_agent_id=0),
            )
            for t, d in domain_of.items()
        ]

        clean = winner_stability(episodes, n_splits=40, n_permutations=20, seed=7)
        mixed = winner_stability(episodes + poisoned, n_splits=40, n_permutations=20, seed=7)

        assert [g.to_dict() for g in clean.groups] == [g.to_dict() for g in mixed.groups]
