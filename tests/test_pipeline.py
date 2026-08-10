"""End-to-end: synthetic answer bank -> Stage B -> records -> go/no-go gate.

This is the test that the harness *runs*, as opposed to each piece working in isolation. It
writes a real run directory, executes the real Stage-B runner over the free protocols and every
coalition, reads the records back through the real loaders, and drives the real gate.

No network, no API key, no money. The bank is planted so every phenomenon is known in advance,
and the planted structure is chosen so the predicted expert is agent 1 under *any* calibration
split (see :func:`planted_answers`), which keeps the assertions below independent of the split
seed.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from mas_harness.analysis.gonogo import FAIL, INSUFFICIENT, PASS, build_report
from mas_harness.clients.pricing import ModelPricing, PricingTable
from mas_harness.interventions import edits
from mas_harness.pool.agents import all_nonempty_coalitions
from mas_harness.pool.expert import (
    Observation,
    fit_expert_predictor,
    observations_from_records,
    oracle_expert,
)
from mas_harness.records.schema import InterventionSpec
from mas_harness.records.writer import JsonlWriter, RunDirectory, to_parquet
from mas_harness.runners.answer_bank import committed
from mas_harness.runners.episodes import run_stage_b
from mas_harness.tasks.adapters import TaskSpec, build_evaluator
from mas_harness.tasks.manifest import Manifest
from mas_harness.tasks.splits import stratified_split

from .conftest import make_answer

DOMAINS = ("physics", "chemistry", "biology", "math")
N_GROUPS = 10
N_TASKS = N_GROUPS * len(DOMAINS)  # 40

# Groups 0-5: only agent 1 is right and the rest agree on one wrong answer. Any vote loses
# these, so they are the planted dilution cases.
DILUTION_GROUPS = range(0, 6)
CONSENSUS_GROUPS = (6, 7)
TIE_GROUP = 8
RESCUE_GROUP = 9


def planted_answers(task_index: int) -> list[str]:
    """One answer letter per agent. Ground truth is always ``B``.

    Per domain this gives agent 1 nine correct out of ten and agent 2 four out of ten, so on
    a five-task calibration sample agent 1 scores at least 4/5 and agent 2 at most 4/5. Agent 1
    therefore wins every per-domain argmax (ties break to the lower id) whichever tasks the
    split happens to pick — the tests below do not depend on the split seed.
    """
    group = task_index // len(DOMAINS)
    if group in DILUTION_GROUPS:
        wrong = "A" if group < 4 else "C"  # two distinct wrong answers, same structure
        return [wrong, "B", wrong, wrong]
    if group in CONSENSUS_GROUPS:
        return ["B", "B", "B", "B"]
    if group == TIE_GROUP:
        return ["A", "B", "B", "A"]  # 2-2, broken by summed competence
    return ["B", "A", "B", "B"]  # rescue: agent 1 is wrong, the vote saves it


def dilution_task_ids() -> set[str]:
    return {
        f"mmlu_pro::syn{i:03d}"
        for i in range(N_TASKS)
        if i // len(DOMAINS) in DILUTION_GROUPS
    }


def synthetic_tasks() -> list[TaskSpec]:
    return [
        TaskSpec(
            task_id=f"mmlu_pro::syn{i:03d}",
            suite="mmlu_pro",
            domain=DOMAINS[i % len(DOMAINS)],
            answer_type="choice",
            prompt=f"Synthetic question {i} concerning {DOMAINS[i % len(DOMAINS)]}.",
            ground_truth="B",
            payload={"question": f"q{i}", "options": ["w", "x", "y", "z"], "answer": "B"},
        )
        for i in range(N_TASKS)
    ]


@pytest.fixture
def synthetic_run(tmp_path, pool):
    """A manifest plus a complete Stage-A answer bank in a temporary run directory."""
    tasks = synthetic_tasks()
    calibration, test = stratified_split(
        [(t.task_id, t.domain) for t in tasks], fraction=0.5, seed=0
    )
    manifest = Manifest(
        manifest_id="synthetic",
        created_at="2026-08-04T00:00:00+00:00",
        seed=0,
        tasks=tasks,
        splits={"calibration": calibration, "test": test},
    )
    manifest.write(tmp_path / "manifest.json")

    runs_root = tmp_path / "runs"
    run_dir = RunDirectory(runs_root, "syn")
    with JsonlWriter(run_dir.answers_path) as writer:
        for index, task in enumerate(tasks):
            for agent, answer in zip(pool.agents, planted_answers(index), strict=True):
                writer.write(make_answer(task, agent, answer))

    # A frozen price snapshot, so the runner never reaches for the live price endpoint.
    PricingTable(
        {a.model: ModelPricing(a.model, 1.0, 3.0) for a in [*pool.agents, pool.aggregator]},
        captured_at="2026-08-04T00:00:00+00:00",
        source="test fixture",
    ).write(run_dir.pricing_path)

    return runs_root, "syn", Manifest.read(tmp_path / "manifest.json"), pool


def run_free_stage_b(runs_root, run_id, manifest, pool, **overrides):
    kwargs = dict(
        manifest=manifest,
        pool=pool,
        run_id=run_id,
        runs_root=runs_root,
        protocols=["single_expert", "independent_majority"],
        coalition_mode="all",
        coalition_size=None,
        intervention_mode="none",
        n_permutations=2,
        seeds=[0],
        rounds=1,
        expert_strategy="domain",
        concurrency=4,
        dry_run=False,
        test_split_only=False,
        role_rotation=False,
    )
    kwargs.update(overrides)
    return asyncio.run(run_stage_b(**kwargs))


# ---- the bank -----------------------------------------------------------------------------


def test_synthetic_bank_has_the_planted_structure(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    answers = RunDirectory(runs_root, run_id).load_answers()
    assert len(answers) == N_TASKS * len(pool)

    accuracy = {
        agent.agent_id: float(np.mean([r.correct for r in answers if r.agent_id == agent.agent_id]))
        for agent in pool
    }
    assert accuracy == {0: 0.3, 1: 0.9, 2: 0.4, 3: 0.3}
    # Nobody is degenerate: every agent is right somewhere and wrong somewhere, so no metric
    # below is computed on an empty stratum.
    assert all(0.0 < value < 1.0 for value in accuracy.values())
    assert all(not r.parse_failed for r in answers)


def test_expert_predictor_uses_calibration_only(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    answers = RunDirectory(runs_root, run_id).load_answers()
    calibration = manifest.splits["calibration"]

    predictor = fit_expert_predictor(
        observations_from_records(answers), strategy="domain", calibration_task_ids=calibration
    )
    assert predictor.n_calibration_tasks == len(calibration)
    # No test task may have touched the fit (D-004).
    assert not set(predictor.calibration_task_ids) & set(manifest.splits["test"])
    assert predictor.global_expert == 1
    assert set(predictor.by_domain.values()) == {1}
    assert predictor.fallback_domains == []


def test_predictor_restricts_its_prediction_to_the_coalition(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    answers = RunDirectory(runs_root, run_id).load_answers()
    predictor = fit_expert_predictor(
        observations_from_records(answers),
        strategy="domain",
        calibration_task_ids=manifest.splits["calibration"],
    )
    for coalition in all_nonempty_coalitions(pool.agent_ids):
        prediction = predictor.predict(domain="physics", coalition=coalition)
        assert prediction in coalition
        # Agent 1 is the pool-wide expert, so it is chosen whenever it is available.
        assert prediction == 1 or 1 not in coalition


def test_predictor_falls_back_when_a_domain_is_too_thin():
    observations = [
        Observation(task_id=f"t{i}", agent_id=0, domain="common", correct=True) for i in range(20)
    ] + [Observation(task_id="rare0", agent_id=1, domain="rare", correct=True)]
    predictor = fit_expert_predictor(observations, strategy="domain")
    assert predictor.fallback_domains == ["rare"]
    assert "rare" not in predictor.by_domain
    assert predictor.predict(domain="rare") == predictor.global_expert


def test_oracle_returns_none_when_nobody_is_correct():
    assert oracle_expert({0: False, 1: False}) is None
    assert oracle_expert({0: False, 1: True}) == 1


# ---- Stage B ------------------------------------------------------------------------------


def test_dry_run_spends_nothing_and_writes_nothing(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    summary = run_free_stage_b(runs_root, run_id, manifest, pool, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["estimated_cost_usd"] == 0.0
    assert summary["n_planned_episodes"] == N_TASKS * 15 * 2  # 15 non-empty coalitions
    assert summary["free_episodes"] == summary["n_planned_episodes"]
    assert not RunDirectory(runs_root, run_id).episodes_path.exists()


def test_dry_run_prices_the_priced_protocols_and_reports_the_call_volume(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    summary = run_free_stage_b(
        runs_root,
        run_id,
        manifest,
        pool,
        protocols=["debate_vote", "expert_veto", "chair_information_seeking"],
        coalition_mode="grand",
        rounds=2,
        dry_run=True,
    )
    assert summary["n_planned_episodes"] == N_TASKS * 3
    assert summary["free_episodes"] == 0
    assert summary["estimated_cost_usd"] > 0
    assert not RunDirectory(runs_root, run_id).episodes_path.exists()


def test_role_rotation_multiplies_priced_protocols_only(synthetic_run):
    """Rotations are only worth paying for where a role instruction is actually read."""
    runs_root, run_id, manifest, pool = synthetic_run
    summary = run_free_stage_b(
        runs_root,
        run_id,
        manifest,
        pool,
        protocols=["independent_majority", "debate_vote"],
        coalition_mode="grand",
        role_rotation=True,
        dry_run=True,
    )
    assert summary["n_role_rotations"] == len(pool)
    assert summary["episodes_per_protocol"]["independent_majority"] == N_TASKS
    assert summary["episodes_per_protocol"]["debate_vote"] == N_TASKS * len(pool)


def test_free_protocols_cost_nothing_end_to_end(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    summary = run_free_stage_b(runs_root, run_id, manifest, pool)

    assert summary["n_written"] == N_TASKS * 15 * 2
    assert summary["actual_cost_usd"] == 0.0
    assert summary["stopped_early"] is None

    episodes = RunDirectory(runs_root, run_id).load_episodes()
    assert len(episodes) == summary["n_written"]
    assert all(e.n_calls == 0 for e in episodes)
    assert all(e.total_cost_usd == 0.0 for e in episodes)
    assert all(e.ground_truth == "B" for e in episodes)
    assert all(e.individual_correct for e in episodes)


def test_accuracy_matches_the_planted_design(synthetic_run):
    """The grand coalition: routing to the expert beats voting by exactly the planted margin."""
    runs_root, run_id, manifest, pool = synthetic_run
    summary = run_free_stage_b(runs_root, run_id, manifest, pool, coalition_mode="grand")
    accuracy = summary["accuracy_by_protocol"]
    # Agent 1 is right on 36 of 40; the vote wins only the 16 non-dilution tasks.
    assert accuracy["single_expert"] == pytest.approx(0.9)
    assert accuracy["independent_majority"] == pytest.approx(0.4)


def test_resume_skips_completed_episodes(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    first = run_free_stage_b(runs_root, run_id, manifest, pool)
    second = run_free_stage_b(runs_root, run_id, manifest, pool)
    assert second["n_planned_episodes"] == 0
    assert second["n_already_done"] == first["n_written"]
    assert second["n_written"] == 0


def test_dilution_is_visible_in_the_episode_records(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool, coalition_mode="grand")
    episodes = RunDirectory(runs_root, run_id).load_episodes()

    majority = {e.task_id: e for e in episodes if e.protocol_id == "independent_majority"}
    expert = {e.task_id: e for e in episodes if e.protocol_id == "single_expert"}

    for task_id in dilution_task_ids():
        assert sum(majority[task_id].individual_correct.values()) == 1
        assert majority[task_id].predicted_expert_id == 1
        assert expert[task_id].correct is True
        assert majority[task_id].correct is False


def test_parquet_export_flattens_the_records(synthetic_run):
    import pandas as pd

    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool)
    run_dir = RunDirectory(runs_root, run_id)

    frame = pd.read_parquet(to_parquet(run_dir.episodes_path))
    assert len(frame) == N_TASKS * 15 * 2
    for column in (
        "task_id",
        "protocol_id",
        "coalition",
        "coalition_size",
        "correct",
        "intervention_kind",
        "total_cost_usd",
    ):
        assert column in frame.columns
    # Transcripts and per-call records are dropped from the analysis view by design (D-007).
    assert "transcript" not in frame.columns
    assert "calls" not in frame.columns
    assert set(frame["coalition_size"].unique()) == {1, 2, 3, 4}


def test_run_meta_records_reproducibility_context(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool, coalition_mode="grand")
    meta = RunDirectory(runs_root, run_id).read_meta()
    assert meta["manifest_hash"] == manifest.content_hash
    assert meta["pool_hash"] == pool.content_hash
    assert meta["upstream_pins"]
    assert any(entry["stage"] == "B" for entry in meta["stage_history"])


# ---- interventions over the real bank ------------------------------------------------------


def test_masking_does_not_mutate_the_input_bank(choice_task, make_bank):
    bank = make_bank(["A", "B", "A", "A"])
    original = bank[1].text
    edited = edits.apply(bank, InterventionSpec(kind="mask", target_agent_id=1), task=choice_task)
    assert bank[1].text == original
    assert edited[1].text == edits.MASKED_TEXT
    assert edited[1].extracted_answer == ""
    assert edited[1].parse_failed is True


def test_masked_member_abstains_rather_than_voting(choice_task, make_bank):
    """A masked message must read as an abstention, not as a vote (D-011)."""
    from mas_harness.protocols.voting import tally

    evaluator = build_evaluator(choice_task)
    assert evaluator.extract(edits.MASKED_TEXT) == ""

    bank = make_bank(["A", "B", "A", "A"])
    edited = edits.apply(bank, InterventionSpec(kind="mask", target_agent_id=0), task=choice_task)
    result = tally({a: r.extracted_answer for a, r in edited.items()}, evaluator)
    assert result.abstentions == [0]
    assert result.n_voting == 3
    assert result.counts == {"A": 2, "B": 1}


def test_substitution_reuses_a_real_donor_answer(choice_task, make_bank):
    bank = make_bank(["A", "B", "A", "A"])
    edited = edits.apply(
        bank,
        InterventionSpec(kind="substitute_correct", target_agent_id=0),
        task=choice_task,
        donor_pool=list(bank.values()),
    )
    assert edited[0].correct is True
    assert edited[0].extracted_answer == "B"
    # Agent 1's genuine correct answer was reused rather than a stub being invented.
    assert edited[0].text == bank[1].text


def test_substitution_synthesizes_only_when_no_donor_exists(choice_task, make_bank):
    bank = make_bank(["A", "A", "A", "A"])
    edited = edits.apply(
        bank,
        InterventionSpec(kind="substitute_correct", target_agent_id=0),
        task=choice_task,
        donor_pool=list(bank.values()),
    )
    assert edited[0].extracted_answer == "B"
    assert edited[0].correct is True
    assert edited[0].text not in {r.text for r in bank.values()}


def test_intervention_plan_always_starts_with_the_baseline():
    plan = edits.intervention_plan([0, 1, 2, 3])
    assert plan[0].kind == "none"
    assert {spec.kind for spec in plan} == {"none", "mask", "substitute_correct", "reorder"}
    assert sum(1 for s in plan if s.kind == "mask") == 4
    # Labels are the resume keys, so they must be unique within a plan.
    assert len({s.label() for s in plan}) == len(plan)


def test_reorder_is_skipped_for_a_singleton():
    assert edits.reorder_interventions([0]) == []


def test_masks_produce_paired_episodes_and_a_causal_influence_profile(synthetic_run):
    from mas_harness.metrics.governance import influence_profile

    runs_root, run_id, manifest, pool = synthetic_run
    summary = run_free_stage_b(
        runs_root,
        run_id,
        manifest,
        pool,
        protocols=["independent_majority"],
        coalition_mode="grand",
        intervention_mode="masks",
    )
    assert summary["n_planned_episodes"] == N_TASKS * 5  # baseline + one mask per member

    episodes = RunDirectory(runs_root, run_id).load_episodes()
    profile = influence_profile(episodes, competence=dict.fromkeys(pool.agent_ids, 0.5))
    assert set(profile.influence) == set(pool.agent_ids)
    assert all(count == N_TASKS for count in profile.n_pairs.values())

    # Only the 2-2 contested tasks can flip under a single mask, and only by removing one of
    # the two members holding the winning answer.
    assert profile.influence[1] == pytest.approx(4 / N_TASKS)
    assert profile.influence[2] == pytest.approx(4 / N_TASKS)
    assert profile.influence[0] == 0.0
    assert profile.influence[3] == 0.0
    assert profile.flips_to_wrong.get(1) == 4


# ---- the gate ------------------------------------------------------------------------------


def test_gate_evaluates_every_direction_and_serializes(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool)
    report = build_report(run_id=run_id, runs_root=runs_root, manifest=manifest, pool=pool)

    assert {c.direction for c in report.criteria} == {"governance", "delegation", "coalition"}
    assert all(c.verdict in {PASS, FAIL, INSUFFICIENT} for c in report.criteria)
    assert report.recommendation["selection"]
    json.dumps(report.to_dict(), default=float)  # the CLI writes this to disk


def test_gate_marks_uncollected_evidence_insufficient_not_failed(synthetic_run):
    """A criterion whose evidence was never gathered must not read as a kill."""
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool, intervention_mode="none")
    report = build_report(run_id=run_id, runs_root=runs_root, manifest=manifest, pool=pool)

    flip = next(c for c in report.criteria if c.name == "intervention flip rate")
    assert flip.verdict == INSUFFICIENT
    assert "--interventions masks" in flip.detail
    assert "intervention flip rate" in report.recommendation["governance"]["insufficient"]


def test_gate_detects_the_planted_dilution_and_protocol_spread(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool)
    report = build_report(run_id=run_id, runs_root=runs_root, manifest=manifest, pool=pool)

    dilution = next(c for c in report.criteria if c.name == "correct-answer dilution")
    assert dilution.verdict == PASS
    assert dilution.observed >= 15.0

    rates = report.evidence["governance_rates"]["independent_majority"]
    assert rates["predicted"]["dilution_rate"] > 0.15
    # The oracle figure is reported alongside, never pooled with the prediction (D-004).
    assert "oracle_upper_bound" in rates
    # single_expert cannot dilute by construction, and must not drag the maximum down.
    assert report.evidence["governance_rates"]["single_expert"]["predicted"]["dilution_rate"] == 0.0

    spread = next(c for c in report.criteria if c.name == "protocol spread")
    assert spread.verdict == PASS
    assert spread.observed > 8.0


def test_gate_reports_the_coalition_analysis_on_complete_coverage(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool)
    report = build_report(run_id=run_id, runs_root=runs_root, manifest=manifest, pool=pool)

    coverage = report.evidence["coalition_coverage"]
    assert coverage["n_coalitions_required"] == 15
    assert coverage["n_tasks_with_all_coalitions"] == N_TASKS

    analysis = report.evidence["coalition_analysis"]
    assert analysis["n_tasks"] == N_TASKS
    assert 0.0 <= analysis["mean_R_ge3"] <= 1.0
    assert len(analysis["mean_pairwise_synergy"]) == 6  # every unordered pair
    assert set(analysis["top_k_gaps"]) == {"k1", "k2", "k3"}
    assert analysis["top_k_gaps"]["k1"]["baseline_members"] == [1]


def test_gate_refuses_the_coalition_analysis_without_full_coverage(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool, coalition_mode="grand")
    report = build_report(run_id=run_id, runs_root=runs_root, manifest=manifest, pool=pool)

    criterion = next(c for c in report.criteria if c.name == "top-k gap")
    assert criterion.verdict == INSUFFICIENT
    assert "--coalitions all" in criterion.detail


def test_gate_reports_power_next_to_the_available_sample(synthetic_run):
    runs_root, run_id, manifest, pool = synthetic_run
    run_free_stage_b(runs_root, run_id, manifest, pool, coalition_mode="grand")
    report = build_report(run_id=run_id, runs_root=runs_root, manifest=manifest, pool=pool)

    power = report.evidence["power"]
    assert power["n_available"] == N_TASKS
    if "n_required_for_8pp_at_80_power" in power:
        assert power["n_required_for_8pp_at_80_power"] > 0


class TestUnfinishedResponsesAreNotAnswers:
    """A response that never terminated is an abstention, not a wrong answer.

    Discovered in the probe-gpqa run: Gemini 2.5 Flash ran to a 24,576-token cap on 5 of 12
    GPQA questions, and three of those still yielded a letter under strict extraction, because
    unterminated reasoning is full of provisional lines like "this would give B" written while
    enumerating options the model went on to reject. The extractor takes the last match, which
    in a truncated stream is wherever the cut fell rather than a conclusion.
    """

    @pytest.mark.parametrize("reason", ["stop", "end_turn", "eos", "stop_sequence", None])
    def test_a_finished_response_counts(self, reason):
        assert committed(reason)

    @pytest.mark.parametrize("reason", ["length", "error", "content_filter", "tool_calls"])
    def test_an_unfinished_response_does_not_count(self, reason):
        assert not committed(reason)

    def test_a_truncated_response_is_banked_as_an_abstention_despite_containing_a_letter(
        self, choice_task
    ):
        """The end-to-end behaviour that matters: extraction must not rescue a cut-off stream."""
        text = (
            "Let me enumerate. If the ring opens first, the answer is 'A'. "
            "But that ignores stereochemistry, so instead the answer is 'B'. "
            "Reconsidering the migration step, we would get"
        )
        evaluator = build_evaluator(choice_task)

        # What the extractor sees in isolation: a confident-looking, entirely provisional letter.
        assert evaluator.extract(text) == "B"

        # What the runner must record once it knows the stream never terminated.
        extracted = "" if not committed("length") else evaluator.extract(text)
        assert extracted == ""
        assert evaluator.score_extracted(extracted) is False

    def test_the_same_text_counts_when_the_model_actually_finished(self, choice_task):
        text = "After weighing both routes, the answer is 'B'."
        evaluator = build_evaluator(choice_task)
        extracted = "" if not committed("stop") else evaluator.extract(text)
        assert extracted == "B"
