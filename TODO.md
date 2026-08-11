# TODO

Ordered by what blocks what. `PROJECTSTATE.md` records what already works.

## The MVP is done — see `PROJECTSTATE.md`

- [x] **`OPENROUTER_API_KEY` set, slugs and prices confirmed, tokens measured.** 300 input / 4,200
      output per call, replacing the report's 1,200 / 500 planning figures. Twelve models screened for
      availability, price, accuracy and commit rate.
- [x] **Stage A, free Stage B and priced Stage B on three pools over `hard366`.** $57.98 for the three
      priced sweeps; $85.13 for the project including screening and the failed D-028 repair.
- [x] **The gate, run on all three pools.** Delegation GO, governance NO GO on accuracy, coalition
      NO GO. A pre-registered confirmatory test refuted the one governance mechanism that looked real
      (D-026, D-027).

## The delegation phase — closed, see D-029 through D-036

- [x] **Task encoder, organization model, selector.** Built as
      [`mas_harness/metrics/routing.py`](mas_harness/metrics/routing.py) and run on all six
      pool-by-suite cells. No gain over a frozen fixed-best baseline at calibration sizes from 57 to
      398 tasks. D-033.
- [x] **Test whether the null is a sample-size result.** It is not: the learning curve is flat over a
      sevenfold increase in calibration data while its spread halves.
- [x] **Test whether four capability groups were too few.** Fifteen domains on the pooled suite give
      off-dominant reproducibility of 0.10-0.29, below the 0.5 floor on all three pools.
- [x] **Test whether the headroom was ever real.** It was not. Against a null preserving organization
      accuracies and task difficulties but removing their interaction, observed headroom is at or
      below chance in all six cells. D-034.
- [x] **Re-test the pool-headroom precondition against the same null.** Done over four agents as
      singleton organizations, the family D-021 and D-023 actually used: excess headroom +1.33
      (p=0.330), −0.14 and +2.44 (p=0.203). The precondition that gated real spending does not clear
      the null either. D-035.
- [x] **Run the positive control the null needed.** Eight distinct agents on 238 `crosscap240` tasks
      with per-capability spreads to 0.833, and a pool selected on calibration to be maximally
      disjoint: excess −2.16 (p=0.883). The null cannot be beaten even by a pool assembled to beat it,
      and the reason is that for seven of eight agents the strongest capability is the same one.
      D-035.
- [x] **Measure the efficiency case D-035 left open.** Under a per-task budget, routing loses in all
      six cells (−0.48 to −3.15 points, positive in 2-29% of 200 resplits). The lambda-swept version
      that showed +2.6 to +16.6 points was a convex-hull artefact. D-036.
- [x] **Sharpen the headroom null to preserve member sharing.** Built as
      [`mas_harness/metrics/sharing_null.py`](mas_harness/metrics/sharing_null.py): simulate agents
      under additivity, then vote for real. Replay reproduces recorded episodes at agreement 1.0000 in
      all six cells, and planted specialists are detected at p<0.05. The null did fall as predicted,
      excesses rose one to three points, and the verdict held: one cell of six at p=0.045 against a
      Bonferroni threshold of 0.0083. D-037.
- [x] **Run the interaction likelihood-ratio test.** Done, D-038. Interaction is significant at
      `p<=0.005` at both the agent and organization level on `crosscap240` (excess departures +7.29,
      and +6.71/+4.21/+3.78 pp) and undetectable on `hard366`. The predicted agent-versus-organization
      contrast did not appear, so FRAMEWORK 5.3 was weakened from "aggregation destroys the
      interaction" to "absorbs the exploitable part". The central tension is now measured: the same
      three tables carry interaction at `p<=0.005` and sharp-null headroom excess of −0.23, −0.05 and
      −3.24.
- [x] **Regenerate the lambda artefact and measure Lemma 2.** Done, D-039. Both historical ranges
      retired as unreproducible; regenerated best-lambda gains are +3.36 to +7.99, and the hull
      diagnostic counts 3 to 9 Pareto-efficient organizations per cell that no lambda can reach.
- [x] **Persist the agent-by-capability table.** Done; `accuracy_by_capability` in
      `data/runs/headroom_null_specialists.json`. It was previously only ever printed to a terminal
      while carrying claim C4 and a planned figure.
- [ ] **Decide what the paper is.** Backbone and claim-evidence matrix now exist as
      [`Docs/PAPER_BACKBONE.md`](Docs/PAPER_BACKBONE.md) and
      [`Docs/CLAIM_EVIDENCE_MATRIX.md`](Docs/CLAIM_EVIDENCE_MATRIX.md), with three claims signed off.
      Remaining before drafting: the terminology ledger, and an explanation for `correlated4` being the
      one pool where the capability router beats voting.
- [ ] **Apply the null to the public matrices already on disk.** `agent-psychometrics` has
      `swebench_pro`, `gso` and `terminalbench` alongside the verified split already used, and
      `TwinRouterBench/data` has static and dynamic matrices. Free external validity for D-034 and
      D-036 beyond our own eight agents.
- [ ] **Pre-register before testing the two sign-stable patterns**: `independent_judge` never hurting,
      `expert_verifier` and plain majority never helping. D-027 records why they are not findings yet.
- [ ] **Write up governance as an influence result rather than an accuracy one.** Mask-flip rates of
      24.5-25.0% and the competence-versus-leverage divergence replicated on all three pools; the
      accuracy effects did not.

## Task substrates

- [x] **Distributed-information condition.** Built by option-set partitioning in
      `mas_harness/tasks/distributed.py` (D-010, D-015). Two arms are committed:
      `configs/suites/distributed30.yaml` (cooperative) and
      `distributed30_pressure.yaml` (pressure). Both must be run and reported together.
- [ ] **HiddenBench itself.** Still absent, and still preferable to a substitute for the
      *published-comparison* claim. Not on HuggingFace under an obvious slug; would need
      the 65 tasks from the paper's release. No longer blocking, since the constructed
      condition covers the scientific need — but if it is not obtained, the paper must say
      the distributed condition is constructed and describe the partitioning.
- [ ] **Report `out_of_set_rate` on the first real distributed run.** The construction's
      one residual leak is a member naming a letter it was never shown. It is measured;
      if it is high, the pressure arm has to be discounted rather than explained away.
- [ ] **EvalPlus (HumanEval+ / MBPP+).** Needs the `evalplus` package plus a sandboxed
      executor. The harness has no code-execution path at all yet. This is the fourth
      MVP domain in the report; the MVP currently ships three.
- [ ] Organizational-psychology tasks for direct comparability with the expert-dilution
      paper exist upstream (`lost_at_sea`, `moon_survival`, `student_body_president`) but
      are ranking tasks, so they need a ranking evaluator and an L1 scorer rather than
      the exact-match path. Low priority.

## Compute

- [x] **GPU diagnostic: this host has none.** `nvidia-smi` cannot reach a driver *and*
      there are no `/dev/nvidia*` device nodes, so it is not a sandbox artifact. The vLLM
      branch is closed for now; OpenRouter only, which D-006 anticipated.
- [ ] If GPUs are provisioned later: `Qwen/Qwen3-30B-A3B-Instruct-2507`,
      `meta-llama/Llama-3.3-70B-Instruct` and `Qwen/Qwen3-32B` are already in the local HF
      cache, and adding them is a pool YAML change, not a code change (D-006).
      `Mistral-Small-3.2-24B-Instruct` is *not* cached and would need ~48 GB.
      Benchmark real vLLM throughput and memory before trusting the report's GPU-hour
      estimates.

## Method work, after the pilot

- [ ] Delegation direction: task encoder (frozen embeddings + bilinear scoring) and the
      semantic / capability / organizational similarity matrices. `metrics/delegation.py`
      computes fingerprints and regret; the *learned* encoder is not written.
- [ ] Coalition direction: the DeepSets / Set Transformer baseline. The additive and
      pairwise-factorization models are implemented; the permutation-invariant set model
      is not.
- [ ] Governance direction: the governance selector itself. `metrics/governance.py`
      measures everything the report defines, but the selector
      `argmax_g [q_g(x) - lambda C - mu L - rho R]` is only implemented as an oracle and
      a domain-conditional baseline, not as a learned model.
- [ ] IRT competence baseline. `agent-psychometrics/experiment_new_tasks/feature_irt.py`
      is the thing to lift; needs `pip install -e ".[irt]"` for `pyro-ppl`.
- [ ] MasRouter-style configuration classifier as a routing baseline.

## Rigor

- [ ] Latin-square role rotation is implemented (`pool/roles.py`) and wired into Stage B
      (`--role-rotation`), but has never been run. It multiplies the priced episode count
      by the pool size, so it needs a stratified subset defined in a suite config rather
      than being applied to the whole manifest.
- [ ] Three-seed replication on a stratified 20-30% subset (report's guidance) — the
      seed axis works but no multi-seed run has been done.
- [ ] Second API model family for provider-independence validation.
- [ ] Protocol card: `mas_harness.protocols.protocol_card()` generates it from the registry,
      but it has not been written out as a tracked artifact and reviewed against what the
      implementations actually show each participant.
- [ ] Report the `challenge_named_alternative` rate for `expert_veto` (D-013). A high rate
      of challenges that object without naming an alternative would mean the protocol is
      measuring instruction-following rather than governance.
- [ ] Report the `loose_invented_answer` rate from `extraction_diagnostics()` as a
      methodological note, since our multiple-choice numbers are not directly comparable to
      the expert-dilution paper's (D-011).

## Known rough edges

- [ ] `metrics/stats.py::mixed_effects_logit` uses `statsmodels` binomial GEE with an
      exchangeable correlation structure clustered on task, which is not the same as the
      crossed task+seed random effects the report specifies. Adequate for the pilot;
      needs a proper crossed-effects fit (or `pymer4`/R) for the paper.
- [ ] Harsanyi decomposition is exact and exhaustive, so it is exponential in pool size.
      Fine at 4-5 agents, refuses above 12.
- [ ] The response cache never evicts. It is content-addressed under `data/cache/`;
      watch disk, which was at 96% when the harness was built.
