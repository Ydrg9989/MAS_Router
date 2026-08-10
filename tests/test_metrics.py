"""Metrics and statistics, checked against planted ground truth and known identities."""

from __future__ import annotations

import numpy as np
import pytest

from mas_harness.metrics import governance, utility
from mas_harness.metrics.stats import (
    brier_score,
    expected_calibration_error,
    holm_bonferroni,
    mcnemar,
    negative_log_likelihood,
    paired_bootstrap,
    permutation_test,
    required_n_paired,
)
from mas_harness.records.schema import EpisodeRecord, InterventionSpec


def episode(
    *,
    task_id: str,
    protocol_id: str = "independent_majority",
    correct: bool,
    final_answer: str = "B",
    coalition: list[int] | None = None,
    individual_correct: dict[str, bool] | None = None,
    predicted_expert_id: int | None = 0,
    oracle_expert_id: int | None = None,
    intervention: InterventionSpec | None = None,
    domain: str = "physics",
    cost: float = 0.0,
    latency_ms: float = 0.0,
    meta: dict | None = None,
) -> EpisodeRecord:
    return EpisodeRecord(
        run_id="t",
        task_id=task_id,
        suite="mmlu_pro",
        domain=domain,
        pool_id="p",
        protocol_id=protocol_id,
        coalition=coalition or [0, 1, 2, 3],
        seed=0,
        intervention=intervention or InterventionSpec(),
        final_text="",
        final_answer=final_answer,
        ground_truth="B",
        correct=correct,
        parse_failed=False,
        individual_correct=individual_correct or {},
        predicted_expert_id=predicted_expert_id,
        oracle_expert_id=oracle_expert_id,
        protocol_meta=meta or {},
        total_cost_usd=cost,
        total_latency_ms=latency_ms,
    )


# ---- governance rates -------------------------------------------------------------------


def test_eur_and_dilution_are_complements_on_planted_data():
    """10 tasks where the predicted expert is right; the team keeps 7 of them."""
    episodes = [
        episode(
            task_id=f"t{i}",
            correct=i < 7,
            individual_correct={"0": True, "1": False, "2": False, "3": False},
        )
        for i in range(10)
    ]
    rates = governance.governance_rates(episodes)
    assert rates.n_expert_correct == 10
    assert rates.expert_utilization_rate == pytest.approx(0.7)
    assert rates.dilution_rate == pytest.approx(0.3)
    assert rates.expert_accuracy == pytest.approx(1.0)
    assert rates.net_expert_effect == pytest.approx(0.7 - 1.0)


def test_rescue_is_conditioned_on_the_expert_being_wrong():
    episodes = [
        episode(
            task_id=f"t{i}",
            correct=i < 4,
            individual_correct={"0": False, "1": True, "2": True, "3": True},
        )
        for i in range(10)
    ]
    rates = governance.governance_rates(episodes)
    assert rates.n_expert_wrong == 10
    assert rates.n_expert_correct == 0
    assert rates.rescue_rate == pytest.approx(0.4)
    assert np.isnan(rates.expert_utilization_rate)  # undefined, not zero


def test_tasks_with_no_expert_are_excluded_not_counted_as_failures():
    """A task nobody solved has no expert to utilize; it must not depress EUR."""
    episodes = [
        episode(task_id="t0", correct=True, individual_correct={"0": True}),
        episode(task_id="t1", correct=False, predicted_expert_id=None, individual_correct={}),
    ]
    rates = governance.governance_rates(episodes)
    assert rates.n_no_expert == 1
    assert rates.n_expert_correct == 1
    assert rates.expert_utilization_rate == pytest.approx(1.0)


def test_oracle_and_predicted_expert_give_different_rates():
    """D-004: the oracle is an upper bound, and the two must never be pooled."""
    episodes = [
        episode(
            task_id=f"t{i}",
            correct=False,
            predicted_expert_id=0,
            oracle_expert_id=1,
            individual_correct={"0": False, "1": True},
        )
        for i in range(10)
    ]
    predicted = governance.governance_rates(episodes, use_oracle=False)
    oracle = governance.governance_rates(episodes, use_oracle=True)
    # Against the prediction the expert was always wrong, so this is a rescue failure.
    assert predicted.n_expert_wrong == 10
    assert predicted.rescue_rate == pytest.approx(0.0)
    # Against the oracle the expert was always right, so it is total dilution.
    assert oracle.n_expert_correct == 10
    assert oracle.dilution_rate == pytest.approx(1.0)


def test_governance_rates_rejects_mixed_protocols():
    episodes = [
        episode(task_id="t0", protocol_id="a", correct=True, individual_correct={"0": True}),
        episode(task_id="t1", protocol_id="b", correct=True, individual_correct={"0": True}),
    ]
    with pytest.raises(ValueError, match="one protocol at a time"):
        governance.governance_rates(episodes)


# ---- influence --------------------------------------------------------------------------


def test_influence_is_the_paired_flip_rate_under_masking():
    """Agent 1 is decisive on 8 of 10 tasks; agent 2 on none."""
    episodes = []
    for i in range(10):
        episodes.append(episode(task_id=f"t{i}", correct=True, final_answer="B"))
        episodes.append(
            episode(
                task_id=f"t{i}",
                correct=i >= 8,
                final_answer="B" if i >= 8 else "A",
                intervention=InterventionSpec(kind="mask", target_agent_id=1),
            )
        )
        episodes.append(
            episode(
                task_id=f"t{i}",
                correct=True,
                final_answer="B",
                intervention=InterventionSpec(kind="mask", target_agent_id=2),
            )
        )

    profile = governance.influence_profile(
        episodes, competence={0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5}
    )
    assert profile.influence[1] == pytest.approx(0.8)
    assert profile.influence[2] == pytest.approx(0.0)
    assert profile.n_pairs[1] == 10
    # Masking agent 1 broke correct answers, so the flips go the wrong way.
    assert profile.flips_to_wrong[1] == 8


def test_unpaired_interventions_are_skipped_not_pooled():
    """An intervention with no matching baseline must not be compared against a mean."""
    episodes = [
        episode(task_id="t0", correct=True),
        episode(
            task_id="t_orphan",
            correct=False,
            final_answer="A",
            intervention=InterventionSpec(kind="mask", target_agent_id=1),
        ),
    ]
    profile = governance.influence_profile(episodes, competence={1: 0.5})
    assert profile.influence == {}


def test_leverage_is_one_when_influence_tracks_competence():
    profile = governance.InfluenceProfile(
        protocol_id="p",
        influence={0: 0.4, 1: 0.2},
        competence={0: 0.8, 1: 0.4},
    )
    leverage = profile.leverage()
    assert leverage[0] == pytest.approx(1.0)
    assert leverage[1] == pytest.approx(1.0)
    assert profile.misalignment_kl() == pytest.approx(0.0, abs=1e-9)


def test_misalignment_kl_is_positive_when_the_weak_agent_dominates():
    """The governance failure the report is about: influence decoupled from competence."""
    aligned = governance.InfluenceProfile(
        protocol_id="p", influence={0: 0.6, 1: 0.2}, competence={0: 0.9, 1: 0.3}
    )
    inverted = governance.InfluenceProfile(
        protocol_id="p", influence={0: 0.2, 1: 0.6}, competence={0: 0.9, 1: 0.3}
    )
    assert inverted.misalignment_kl() > aligned.misalignment_kl()
    assert inverted.leverage()[1] > 1.0
    assert inverted.leverage()[0] < 1.0


def test_order_sensitivity_detects_a_position_effect():
    episodes = []
    for i in range(10):
        episodes.append(episode(task_id=f"t{i}", correct=True, final_answer="B"))
        episodes.append(
            episode(
                task_id=f"t{i}",
                correct=i >= 7,
                final_answer="B" if i >= 7 else "A",
                intervention=InterventionSpec(kind="reorder", order=[3, 2, 1, 0]),
            )
        )
    result = governance.order_sensitivity(episodes)
    assert result["n_pairs"] == 10
    assert result["order_flip_rate"] == pytest.approx(0.7)
    assert result["n_order_made_wrong"] == 7


def test_substitution_uptake_counts_repairs():
    episodes = []
    for i in range(10):
        episodes.append(episode(task_id=f"t{i}", correct=False, final_answer="A"))
        episodes.append(
            episode(
                task_id=f"t{i}",
                correct=i < 6,
                final_answer="B" if i < 6 else "A",
                intervention=InterventionSpec(kind="substitute_correct", target_agent_id=2),
            )
        )
    result = governance.substitution_uptake(episodes)
    assert result["n_pairs"] == 10
    assert result["n_repaired_by_agent"]["2"] == 6
    assert result["overall_accuracy_after_injection"] == pytest.approx(0.6)


# ---- protocol comparison ----------------------------------------------------------------


def test_protocol_spread_restricts_to_common_items():
    """A protocol with partial coverage must not be compared on a different task set."""
    episodes = [
        *[episode(task_id=f"t{i}", protocol_id="a", correct=True) for i in range(10)],
        # Protocol b only ran on the first 5 tasks, and got them all right.
        *[episode(task_id=f"t{i}", protocol_id="b", correct=True) for i in range(5)],
    ]
    result = governance.protocol_spread(episodes)
    assert result["n_common_items"] == 5
    assert result["accuracy_by_protocol"] == {"a": 1.0, "b": 1.0}
    assert result["spread_pp"] == pytest.approx(0.0)


def test_protocol_dominance_reports_the_winner_per_domain():
    episodes = [
        # Protocol a wins math, protocol b wins physics: neither dominates.
        *[episode(task_id=f"m{i}", domain="math", protocol_id="a", correct=True) for i in range(5)],
        *[
            episode(task_id=f"m{i}", domain="math", protocol_id="b", correct=False)
            for i in range(5)
        ],
        *[
            episode(task_id=f"p{i}", domain="phys", protocol_id="a", correct=False)
            for i in range(5)
        ],
        *[episode(task_id=f"p{i}", domain="phys", protocol_id="b", correct=True) for i in range(5)],
    ]
    result = governance.protocol_dominance(episodes)
    assert result["best_protocol_by_domain"] == {"math": "a", "phys": "b"}
    # A perfect split means no dominance, which is the interesting case for delegation.
    assert result["dominance_fraction"] == pytest.approx(0.5)


# ---- utility and regret ------------------------------------------------------------------


def test_utility_penalizes_cost_and_latency():
    episodes = [
        episode(task_id=f"t{i}", protocol_id="cheap", correct=i < 8, cost=0.0, latency_ms=0.0)
        for i in range(10)
    ] + [
        episode(task_id=f"t{i}", protocol_id="pricey", correct=True, cost=0.05, latency_ms=2000.0)
        for i in range(10)
    ]
    stats = utility.configuration_stats(episodes)
    by_label = {c.label: e for c, e in stats.items()}
    cheap = by_label["cheap[0-1-2-3]"]
    pricey = by_label["pricey[0-1-2-3]"]

    assert cheap.accuracy == pytest.approx(0.8)
    assert pricey.accuracy == pytest.approx(1.0)
    # At lambda=0 the accurate one wins; at a high enough lambda the cheap one does.
    assert pricey.utility(lambda_per_usd=0.0, mu_per_second=0.0) > cheap.utility(
        lambda_per_usd=0.0, mu_per_second=0.0
    )
    assert cheap.utility(lambda_per_usd=10.0, mu_per_second=0.0) > pricey.utility(
        lambda_per_usd=10.0, mu_per_second=0.0
    )


def test_pareto_frontier_excludes_dominated_configurations():
    episodes = [
        episode(task_id="t0", protocol_id="good_cheap", correct=True, cost=0.01),
        episode(task_id="t0", protocol_id="bad_pricey", correct=False, cost=0.10),
        episode(task_id="t0", protocol_id="good_pricey", correct=True, cost=0.10),
    ]
    stats = utility.configuration_stats(episodes)
    frontier = {c.protocol_id for c in utility.pareto_frontier(stats)}
    assert "good_cheap" in frontier
    assert "bad_pricey" not in frontier
    assert "good_pricey" not in frontier


def test_utility_frontier_flags_a_lambda_dependent_winner():
    episodes = [
        episode(task_id=f"t{i}", protocol_id="cheap", correct=i < 8, cost=0.0) for i in range(10)
    ] + [
        episode(task_id=f"t{i}", protocol_id="pricey", correct=True, cost=0.05) for i in range(10)
    ]
    stats = utility.configuration_stats(episodes)
    result = utility.utility_frontier(stats, lambdas=(0.0, 100.0))
    assert result["n_distinct_winners"] == 2
    assert result["winner_is_lambda_invariant"] is False


def test_oracle_selection_has_zero_regret_and_fixed_best_does_not():
    """Planted so no single configuration is best everywhere."""
    episodes = []
    for i in range(10):
        episodes.append(episode(task_id=f"t{i}", protocol_id="a", correct=i % 2 == 0))
        episodes.append(episode(task_id=f"t{i}", protocol_id="b", correct=i % 2 == 1))
    stats = utility.configuration_stats(episodes)
    by_label = {c.label: c for c in stats}

    oracle = {
        f"t{i}": by_label["a[0-1-2-3]"] if i % 2 == 0 else by_label["b[0-1-2-3]"]
        for i in range(10)
    }
    assert utility.decision_regret(stats, chosen=oracle)["mean_regret"] == pytest.approx(0.0)

    fixed = utility.decision_regret(stats, chosen=utility.fixed_best_selection(stats))
    assert fixed["mean_regret"] == pytest.approx(0.5)


def test_dynamic_regret_accumulates_and_splits_by_half():
    episodes = []
    for i in range(10):
        episodes.append(episode(task_id=f"t{i}", protocol_id="a", correct=i >= 5))
        episodes.append(episode(task_id=f"t{i}", protocol_id="b", correct=True))
    stats = utility.configuration_stats(episodes)
    by_label = {c.label: c for c in stats}
    # Always pick the worse configuration early, the better one late.
    sequence = [
        (f"t{i}", by_label["a[0-1-2-3]"] if i < 5 else by_label["b[0-1-2-3]"])
        for i in range(10)
    ]
    result = utility.dynamic_regret(stats, chosen_sequence=sequence)
    assert result["final_regret"] == pytest.approx(5.0)
    assert result["first_half_rate"] > result["second_half_rate"]


# ---- statistics ---------------------------------------------------------------------------


def test_mcnemar_uses_only_discordant_pairs():
    # 10 concordant-correct, 8 where only a is right, 2 where only b is right.
    a = [True] * 10 + [True] * 8 + [False] * 2
    b = [True] * 10 + [False] * 8 + [True] * 2
    result = mcnemar(a, b)
    assert result.detail["discordant"] == 10
    assert result.detail["a_only"] == 8
    assert result.n == 20
    assert result.effect == pytest.approx(18 / 20 - 12 / 20)
    assert result.p_value < 0.15


def test_mcnemar_with_identical_outcomes_reports_no_evidence():
    outcomes = [True, False, True, True]
    result = mcnemar(outcomes, outcomes)
    assert result.p_value == 1.0
    assert result.effect == 0.0
    assert result.detail["discordant"] == 0


def test_mcnemar_detects_a_large_planted_difference():
    a = [True] * 40 + [False] * 10
    b = [False] * 40 + [False] * 10
    assert mcnemar(a, b).p_value < 1e-8


def test_paired_bootstrap_ci_collapses_when_the_difference_is_constant():
    """A constant paired difference has no resampling variance, so the CI is a point.

    This is the sanity check that the bootstrap resamples *items* and preserves the pairing:
    resampling a and b independently would produce a wide interval here.
    """
    rng = np.random.default_rng(0)
    a = rng.random(300)
    b = a - 0.1
    result = paired_bootstrap(a, b, n_resamples=2000, seed=1)
    assert result.effect == pytest.approx(0.1, abs=1e-9)
    assert result.ci_low == pytest.approx(0.1, abs=1e-9)
    assert result.ci_high == pytest.approx(0.1, abs=1e-9)


def test_paired_bootstrap_ci_brackets_a_noisy_true_difference():
    rng = np.random.default_rng(0)
    a = rng.normal(0.6, 0.2, 400)
    b = rng.normal(0.5, 0.2, 400)
    result = paired_bootstrap(a, b, n_resamples=4000, seed=1)
    assert result.ci_low < 0.1 < result.ci_high
    assert result.ci_low > 0  # a real effect: the interval excludes zero


def test_paired_bootstrap_ci_includes_zero_for_no_effect():
    rng = np.random.default_rng(3)
    a = rng.random(200)
    b = rng.random(200)
    result = paired_bootstrap(a, b, n_resamples=2000, seed=2)
    assert result.ci_low < 0 < result.ci_high
    assert result.p_value > 0.05


def test_permutation_test_agrees_with_bootstrap_on_direction():
    rng = np.random.default_rng(7)
    a = rng.random(200) + 0.3
    b = rng.random(200)
    perm = permutation_test(a, b, n_permutations=2000, seed=0)
    boot = paired_bootstrap(a, b, n_resamples=2000, seed=0)
    assert perm.p_value < 0.01
    assert np.sign(perm.effect) == np.sign(boot.effect)


def test_permutation_p_value_is_never_zero():
    a = [1.0] * 50
    b = [0.0] * 50
    assert permutation_test(a, b, n_permutations=100).p_value > 0


def test_holm_is_monotone_and_less_conservative_than_bonferroni():
    p_values = {"a": 0.001, "b": 0.02, "c": 0.04, "d": 0.9}
    corrected = holm_bonferroni(p_values, alpha=0.05)
    adjusted = [corrected[k]["p_adjusted"] for k in ("a", "b", "c", "d")]
    assert adjusted == sorted(adjusted)  # monotone in raw p
    assert corrected["a"]["reject"] is True
    # Bonferroni would give 0.02*4 = 0.08 > 0.05; Holm gives 0.02*3 = 0.06, still rejected? No.
    assert corrected["a"]["p_adjusted"] == pytest.approx(0.004)
    assert corrected["d"]["reject"] is False


def test_holm_stops_rejecting_after_the_first_failure():
    """Step-down: once a hypothesis is retained, every larger p is retained too."""
    corrected = holm_bonferroni({"a": 0.001, "b": 0.5, "c": 0.6}, alpha=0.05)
    assert corrected["a"]["reject"] is True
    assert corrected["b"]["reject"] is False
    assert corrected["c"]["reject"] is False


def test_brier_and_nll_reward_calibrated_confidence():
    outcomes = [True] * 50 + [False] * 50
    confident_correct = [0.99] * 50 + [0.01] * 50
    hedged = [0.5] * 100
    assert brier_score(confident_correct, outcomes) < brier_score(hedged, outcomes)
    assert negative_log_likelihood(confident_correct, outcomes) < negative_log_likelihood(
        hedged, outcomes
    )


def test_ece_is_near_zero_for_a_calibrated_predictor():
    rng = np.random.default_rng(11)
    probabilities = rng.random(5000)
    outcomes = rng.random(5000) < probabilities
    result = expected_calibration_error(probabilities, outcomes, n_bins=10)
    assert result["ece"] < 0.03
    assert result["n"] == 5000


def test_ece_is_large_for_an_overconfident_predictor():
    outcomes = [True] * 50 + [False] * 50
    probabilities = [0.99] * 100  # always sure, right half the time
    result = expected_calibration_error(probabilities, outcomes, n_bins=10)
    assert result["ece"] > 0.45


def test_power_calculation_scales_with_effect_size():
    """Smaller effects need more items. The report's 8pp figure is the reference point."""
    small = required_n_paired(effect_pp=5.0, discordance_rate=0.3)
    large = required_n_paired(effect_pp=8.0, discordance_rate=0.3)
    assert small > large
    # At MVP scale (90 tasks), an 8pp effect is not reliably detectable.
    assert large > 90


def test_power_rejects_an_impossible_effect():
    with pytest.raises(ValueError, match="impossible"):
        required_n_paired(effect_pp=40.0, discordance_rate=0.1)
