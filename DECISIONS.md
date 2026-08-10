# Design decisions

Numbered, append-only. Each entry records the decision, why, and what it costs us.
Referenced from code comments as `D-00n` where the reason is not obvious locally.

---

## D-001 — Hoist the answer bank out of the protocol

**Decision.** Experiments run in two stages. Stage A produces one independent answer per
`(task, agent, seed)` and persists it. Stage B runs protocols that *consume* that bank
and pay only for interaction and aggregation calls. `mas_harness` never calls
`teamwork.tasks.task.Task.execute()`.

**Why.** Upstream `CollaborativeMultipleChoiceQuestionTask.execute()` calls
`_collect_individual_answers()` internally, so N protocols over the same task set re-pay
for the independent phase N times *and* each protocol sees different independent
answers. That inflates cost roughly 5x for the MVP protocol set and breaks the paired
McNemar comparison the research report specifies as the primary test.

**Consequences.** Protocols 1 and 2 become free at the margin. All 15 coalitions of a
4-agent pool cost only their aggregation calls. Causal interventions are Stage-B
replays. The price is that we reimplement the protocol bodies rather than reusing
`execute()`; we port the prompt text and control flow out of
`_facilitate_collaboration` instead.

---

## D-002 — Import `teamwork` via a `.pth` file, vendor `TwinRouterBench`

**Decision.** `teamwork` is added to the venv import path through
`site-packages/upstream_teamwork.pth`. `TwinRouterBench`'s usage normalization and
pricing are copied into `mas_harness/clients/` with a provenance header.

**Why.** `pip install -e` on the upstream repo pulls `wandb`, `hydra-core` and
`omegaconf`, which only its `experiments/` runners need. Conversely importing
`swerouter` would pull `tiktoken`, `tokenizers` and optionally `swebench`/`docker`. The
two modules we want from it are ~250 lines of pure logic with no state.

**Consequences.** Upstream drift is not automatic. `mas_harness.doctor` verifies the
pinned SHAs in `UPSTREAM.md` so drift is at least detected.

---

## D-003 — Deterministic evaluation only; no LLM judge in the primary label

**Decision.** All task adapters are constructed with `use_llm_fallback=False`, and
`mas_harness/tasks/adapters.py` asserts that the flag is off.

**Why.** Upstream `_check_equiv_with_llm` issues an `openai.OpenAI` request for model
`gpt-5` directly from inside the scorer. That call is invisible to our cost accounting,
non-deterministic, and would make the label depend on a third model. The research
report is explicit: do not use an LLM judge when exact-match, multiple-choice or
executable tests are available.

**Consequences.** A small number of unparseable answers score 0 rather than being
rescued by a judge. We record `parse_failed` on every record so this is measurable
rather than silent, and `mas-gonogo` reports the parse-failure rate.

---

## D-004 — The expert is *predicted*, not revealed from ground truth

**Decision.** `mas_harness/protocols/expert.py` defines expert selectors. The default,
`calibrated`, ranks agents by their calibration-split accuracy conditioned on the task
domain, using only the calibration split. The ground-truth selector exists as
`oracle` and is used only to compute upper bounds.

**Why.** Upstream `decision_mode="reveal_expert"` picks the expert by comparing each
agent's independent answer against ground truth. That is an oracle. The report's
metrics are defined over the predicted expert `e_hat(x)`:
`EUR = P(Y_g = 1 | Y_{e_hat} = 1)` and `Dilution = P(Y_g = 0 | Y_{e_hat} = 1)`.
Computing these with an oracle expert would overstate both.

**Consequences.** We must reserve a calibration split, so the MVP task budget is split
into calibration and test rather than being fully evaluable. `ExpertID` (how often the
predicted expert is the true best) becomes a reportable quantity in its own right.

---

## D-005 — Cost is computed locally *and* read from the provider, then reconciled

**Decision.** Each call records four normalized token buckets, a locally computed USD
cost from a price snapshot taken at run start, and the provider's own reported cost.
`mas_harness/clients/pricing.py::reconcile` flags disagreements above a relative
tolerance.

**Why.** The report warns that OpenRouter prices move and must be queried
programmatically before each run. Provider-reported cost alone is not reproducible
after the fact; locally computed cost alone silently drifts when prices or cache
accounting change. TwinRouterBench's `trace_cost_audit.py` exists precisely because
these two diverge in practice — notably on Anthropic cache-write tokens.

**Consequences.** One extra HTTP request per run, and a `pricing_snapshot.json`
committed with each run's metadata.

---

## D-006 — OpenRouter first; local vLLM is a config change, not a code change

**Decision.** One client implementation talks to any OpenAI-compatible `/chat/completions`
endpoint. A pool entry's `provider` field selects the base URL and API key; `vllm`
points at a local server.

**Why.** Instructed to run API and large models through OpenRouter. `nvidia-smi` cannot
reach a driver on this host, so no local serving is assumed. But vLLM 0.18.1 is
installed and `Qwen/Qwen3-30B-A3B-Instruct-2507`, `meta-llama/Llama-3.3-70B-Instruct`
and `Qwen/Qwen3-32B` weights are already in the local HuggingFace cache, so local
agents should cost nothing to add later.

**Consequences.** vLLM does not report cost, so `provider: vllm` entries are priced at
zero USD and their compute is accounted separately as GPU-seconds.

---

## D-007 — Records are append-only JSONL, with Parquet as a derived view

**Decision.** Stage A and Stage B append to `answers.jsonl` / `episodes.jsonl`. Parquet
is generated on demand by `mas_harness.records.writer.to_parquet`.

**Why.** Long API-bound runs get interrupted. Append-only JSONL is resumable by reading
back the set of completed keys, survives partial writes at line granularity, and is
diffable. Parquet is the right analysis format but a bad ingest format.

**Consequences.** Resume is O(existing records) at startup, which is negligible at our
scale (thousands of records).

---

## D-008 — Coalition value is defined on a fixed aggregation protocol

**Decision.** The coalition axis varies *membership only*. The aggregation protocol is
held fixed within one coalition sweep and recorded on every episode.

**Why.** The report is explicit that the main coalition analysis must isolate
composition from aggregation, otherwise `v_x(S)` mixes two effects and the Harsanyi
decomposition is uninterpretable. Comparing aggregators is a separate, smaller sweep.

**Consequences.** `v_x(S)` is always reported together with its protocol id, and the
coalition metrics refuse to pool across protocols unless explicitly asked.

---

## D-009 — Singleton coalitions and pure-aggregation protocols make no API calls

**Decision.** A coalition of size 1 returns the banked answer directly. `p2_majority`
aggregates banked answers arithmetically. Neither issues a request.

**Why.** Both are deterministic functions of the bank. Issuing a call would add cost
and sampling noise without adding information.

**Consequences.** Some episodes have zero cost and zero latency, which is correct but
must not be mistaken for a failed run. Records carry `n_calls` so this is explicit.

---

## D-010 — HiddenBench substitute is constructed, not faked

**Decision.** HiddenBench is absent from the workspace. Rather than dropping the
distributed-information condition, `mas_harness/tasks/distributed.py` derives it from
existing multiple-choice tasks by partitioning the option set's supporting evidence
across agents via `AgentProfile.hidden_context`, which upstream `teamwork` already
supports.

**Why.** The report treats controlled distributed information as a primary substrate
for governance because it isolates information integration. Losing it entirely weakens
the design more than an explicitly-labelled substitute does.

**Consequences.** Results on this condition are *not* comparable to published
HiddenBench numbers and every record carries `suite: distributed_synth` so they can
never be silently pooled. Acquiring real HiddenBench remains open in `TODO.md`.

**Amended 2026-08-05, on implementation.** The construction is *option-set partitioning*,
not generated clue text. Each member sees the question stem plus a subset of the lettered
options; the union of subsets is the full option set, but the correct option is shown to
only `n_holders` members.

The rejected alternative was to have a strong model write N disjoint clues that are jointly
sufficient and individually insufficient. That costs money, leaks the answer in ways that
are tedious to detect, and — decisively — makes "individually insufficient" an *empirical
claim about a generated artifact*, which would need its own validation run and could quietly
fail. Partitioning makes the same property provable: a member that cannot see the correct
option cannot state it. Zero generation cost, nothing to validate.

Three properties are enforced in code and asserted per task by `verify_spec()`, which the
manifest builder runs over every task it emits:

- the correct option is visible to exactly the recorded holders;
- the union of visible sets is the whole option set, so the team is jointly sufficient;
- every member sees the *same number* of options, so visible-set size cannot correlate with
  holding the answer. Top-ups toward that uniform size draw only from non-gold options.

The holder rotates round-robin across the task list, so "the holder prevailed" cannot be
confounded with "the model in that seat prevailed" — the same confound role rotation exists
to remove (D-014).

Two further consequences. Private briefings are keyed by `agent_id`, so a manifest is bound
to a pool shape; `check_pool_matches()` refuses to run a mismatched pool, because a member
without a briefing is silently asked a multiple-choice question with no options and produces
garbage that reads as model failure rather than misconfiguration. And absolute accuracy in
this condition is not comparable to the full-information suites, since showing a member 3 of
10 options moves its prior from 1/10 to 1/3; the valid comparisons are across protocols
*within* the condition.

---

## D-011 — Multiple-choice extraction is re-implemented, not inherited

**Decision.** Correctness labels for multiple-choice tasks come from
`StrictChoice` in [`mas_harness/tasks/adapters.py`](mas_harness/tasks/adapters.py), not
from upstream `_extract_answer`. The upstream result is still computed and exposed via
`extraction_diagnostics()` so the disagreement rate is measurable. Boxed-math extraction
still uses upstream, and upstream `_is_equiv` (including the SymPy path) remains the
scorer for both.

**Why.** Upstream `_normalize_answer` ends its ladder with

```python
re.search(r'[\(\)]?([A-J])[\)\.\:\s]*$', text, re.IGNORECASE)
```

which has no left word boundary, so it matches the final *character* of ordinary prose.
`_extract_answer` applies it to the whole message at priority 2. Measured on the actual
adapter: `"I have nothing to add."` extracts `D`, `"no answer at all here"` extracts `E`,
`"hello world"` extracts `D`, `"I defer to my colleague."` extracts `E`. Roughly ten of
twenty-six terminal letters are in range, and English words ending in `d` or `e` are
extremely common, so the false-extraction rate on answerless prose is high. The upstream
test suite misses it only because its negative fixture, `"I agree with the team"`, happens
to end in `m`.

This is not survivable here. Every governance metric — vote tallies, EUR, dilution,
rescue, leverage — depends on distinguishing "abstained" from "voted wrong". An
abstention silently converted into a confident vote changes the majority tally and
biases dilution in an uncontrolled direction. It also inflates apparent participation,
which is precisely the quantity under study.

`StrictChoice` reproduces the upstream priority ladder with bounded letter groups and
passes all eleven extraction fixtures from upstream
`tests/test_multiple_choice_eval.py`, including the `I`-as-pronoun cases. A trailing
standalone letter is still accepted, because models do not always obey the mandated
format and a bare final letter is a real answer; a letter inside a word is not.

**Consequences.** Empty extraction is a first-class outcome recorded as
`parse_failed`, distinct from an incorrect answer. Protocols must therefore handle
abstention explicitly rather than assuming every participant votes. Our multiple-choice
numbers are not directly comparable to the expert-dilution paper's, and the
`loose_invented_answer` rate should be reported as a methodological note.

---

## D-012 — The proposed protocols are one-rule contrasts, not richer systems

**Decision.** Protocols 6 and 7 in
[`mas_harness/protocols/governance.py`](mas_harness/protocols/governance.py) are each
defined as a minimal edit to an existing MVP baseline, and the pairing is recorded in
`PROPOSED_PAIRS` so the runner can warn when one is run without the other.

- `expert_veto` versus `expert_verifier`: identical review of the same candidate answer;
  the only difference is who holds the last word. Under `expert_verifier` the expert
  adjudicates the objection, so authority is unconditional. Under `expert_veto` a
  challenge that clears a stated evidence bar is upheld mechanically, so authority is
  conditional on surviving evidence. Veto uses *one* call, not two, so it is also cheaper
  than the baseline it is meant to beat.
- `chair_information_seeking` versus `independent_judge`: both end with a neutral
  non-participant choosing from the same banked answers. The chair may first ask one
  targeted question of up to two members.

**Why.** The report's claim is about governance rules, not about scaffolding. A proposed
protocol that added a rule *and* two extra calls *and* a longer prompt would win for
reasons we could not attribute. Fixing the comparison at one rule is what makes the
result an argument rather than a demo.

**Consequences.** Neither proposed protocol can be evaluated alone: reporting
`expert_veto` accuracy without `expert_verifier` on the same tasks and coalitions is
meaningless, and `mas_harness.runners.episodes` prints a warning when that happens. The
veto rule also gives the expert no rebuttal, which is a deliberate asymmetry: a rule that
let the expert answer the challenge would collapse back into protocol 5.

---

## D-013 — Whether a governance rule fired is decided by extraction, not by a judge

**Decision.** Every branch point in protocols 6 and 7 is resolved deterministically. A
challenge counts as counterevidence only if the challenger did not emit `NO OVERRIDE`
*and* an answer can be extracted from its message *and* that answer is not equivalent to
the expert's under the task's own equivalence relation. The chair's question and
addressees are parsed from `QUESTION:` / `ASK:` lines, with positional `Member k` labels
mapped back through the order the chair was actually shown.

**Why.** The alternative is asking a model whether the first model's objection was
substantive, which imports the judge's biases into the definition of the metric and makes
the flip rate unreproducible. It would also violate D-003 by putting an LLM inside a
primary label.

**Consequences.** The evidence bar has to be stated in the prompt, so `expert_veto` cannot
share its verifier call with `expert_verifier` through the response cache — the two
prompts genuinely differ. A challenger that objects well but forgets to name an
alternative is recorded as *not* overturning the expert; this is visible as
`challenge_named_alternative: false` and should be reported as a rate, because a high one
means the protocol is measuring instruction-following rather than governance. The
respondent cap (`MAX_RESPONDENTS = 2`) is enforced in code rather than trusted to the
prompt, so a chair that names everyone cannot silently inflate the episode's cost past
what the planner quoted.

---

## D-014 — Role rotation produces distinct pools, and free protocols are not rotated

**Decision.** `role_rotations()` returns pools carrying their own `pool_id`
(`<base>-rot0` and so on), and `--role-rotation` on the Stage-B runner expands the work
plan over them. Protocols in `FREE_PROTOCOLS` are run once regardless, not once per
rotation.

**Why.** Two separate reasons. Distinct ids because episodes are keyed on
`(task, pool, protocol, coalition, seed, intervention)`; reusing the base id would make
two rotations collide in the resume set and silently drop all but one. Skipping the free
protocols because they never construct a prompt, so a rotation would produce
byte-identical episodes under different keys — four times the records for no variation,
and a distorted denominator in every rate computed over them.

**Consequences.** Rotation multiplies the priced episode count by the pool size, so it is
a post-pilot instrument applied to a stratified subset, not a default. The assumption that
free protocols ignore roles is asserted in `tests/test_roles.py` rather than left as a
comment, because if it ever stops holding the runner would be discarding real variation.

---

## D-015 — The distributed-information condition ships as two arms, not one

**Decision.** The partition is one thing; what members are *told about it* is another, and
the second is a build-time flag pair on
[`mas_harness/tasks/distributed.py`](mas_harness/tasks/distributed.py). Two suites are
committed, sharing a seed so they draw the same questions and the same partitions and differ
only in briefing text:

- [`configs/suites/distributed30.yaml`](configs/suites/distributed30.yaml) — *cooperative*.
  Members are told the option set was divided and that only one of them can see the correct
  option, and are given a way to decline (`The answer is 'NONE'`).
- [`configs/suites/distributed30_pressure.yaml`](configs/suites/distributed30_pressure.yaml)
  — *pressure*. Neither warning nor escape hatch, so every uninformed member picks a wrong
  option and the lone holder is outnumbered three to one by construction.

**Why.** Running only one arm would produce a result that reads as being about protocols
while actually being about something else. In the cooperative arm a well-calibrated pool
abstains, the holder is the only member voting, and plurality voting *succeeds* — which
says nothing about governance and everything about calibration. In the pressure arm the
majority is wrong by construction, so plurality voting fails no matter how good the models
are. Only the contrast separates "this protocol surfaces held evidence" from "these models
know when to keep quiet".

The declining sentinel is chosen so that strict extraction yields an abstention (D-011),
which makes it invisible to vote tallies automatically, while `declared_no_answer()` keeps it
distinguishable from an unparseable message. Those two must not be conflated: a member that
recognizes it cannot see the answer is behaving well, and one that emits prose is not.

**Consequences.** Every distributed run is two runs, and reporting one alone is a
methodological error, not merely an incomplete result. `payload.distributed.arm` labels each
task so the two can never be pooled by accident. The pressure arm asks members to choose
among options that do not contain the answer, which is mildly adversarial toward the model;
that is the intended stimulus and is disclosed by the label rather than hidden. A residual
leak remains — a member can name a letter it was never shown — so `out_of_set_rate()`
measures it, and a high rate is grounds for discounting the arm rather than something to
assume away.

---

## D-016 — A manifest's content hash covers what members are shown, not just task identity

**Decision.** `Manifest.content_hash` now includes a digest of each task's
`hidden_context` alongside its id, suite and ground truth. Two related bugs were fixed at
the same time: per-suite sampling seeds are derived with `hashlib` rather than the builtin
`hash()`, and the distributed suite is trimmed to size through the stratified sampler rather
than by slicing an id-sorted list.

**Why.** Three separate ways the reproducibility story was not true.

`hash()` on a `str` is salted per interpreter. `_sample` was seeded with
`seed + abs(hash(suite)) % 10_000`, so rebuilding a manifest drew a *different* task set on
every process — measured directly: three runs, three values. That defeats the immutability
check in `Manifest.write`, whose whole purpose is to compare hashes and distinguish "identical
rebuild, no-op" from "different contents, refuse". `mvp90` could not be rebuilt.

The hash covered only `{task_id, suite, ground_truth}`. For the distributed suite the
partition *is* the task: two manifests can name the same questions with the same answers while
showing members completely different option subsets. Confirmed on the real files — changing
the partition algorithm left `distributed30`'s hash untouched. A changed partition would have
passed the immutability check unnoticed, which is exactly the silent-divergence failure the
hash exists to prevent.

Slicing an id-sorted list to reach the requested count discarded the domain balance the
oversample was drawn with: the first build of `distributed30` came out as 7 biology, 7
chemistry, 7 computer science, 7 engineering, 1 math, 1 physics. Trimming through
`_sample` instead gives 5 of each.

**Consequences.** All three manifests were rebuilt and their hashes changed. Nothing depended
on the old ones, because no run has happened. The hash is now sensitive to briefing text, so
the two distributed arms are distinct manifests as they should be — but it also means a purely
cosmetic edit to briefing wording is a new manifest, which is the correct and slightly
inconvenient behaviour.

---

## D-017 — The budget is charged what the provider says, not what we compute

**Decision.** `SpendLedger` records the provider-reported cost of each call, falling back to
our locally computed figure only when the provider returns none. The pre-call guard multiplies
its projection by 3.

**Why.** An OpenRouter model price is a headline rate; the request is routed to one of several
upstream providers who bill at their own rates, and which one serves a given call is not
knowable in advance. Measured in `pilot9-a`: Qwen3-30B billed 2.69x our computed figure,
Mistral-Small 0.80x, with 10 of 32 calls disagreeing by more than 2%. Recording our own
estimate would let a run overrun its cap silently, in the one direction that costs money.

**Consequence.** Ledger totals now match the invoice, and the local computation is demoted to
what it is good for: a cross-check. Keeping both is the whole point of D-005, and the
disagreement is data rather than noise — a persistent gap for one model means it is being
served by a provider at a different rate, which is worth knowing before attributing a cost
difference to a protocol.

---

## D-018 — `max_tokens` is a validity guard, not a cost control

**Decision.** Every pool member gets `max_tokens: 8192`, well above the 6,808 tokens the most
verbose agent actually used. Cost is bounded by the spend ledger alone.

**Why.** At 1024, 28% of `pilot9-a` responses were truncated mid-derivation and yielded no
extractable answer, which the harness scores as an abstention. This is not a harmless loss of
data. It is a *biased* loss: agents that reason at length are truncated most, so a cap
suppresses precisely the competence differences that `single_expert`, `expert_verifier` and
`expert_veto` are built to exploit. Restoring the headroom moved pooled accuracy from 0.531 to
0.861 — the agents were never mediocre, they were being cut off.

Two further reasons not to treat the cap as a budget: some upstream providers ignore it
outright (Qwen returned 6,808 tokens under a 1024 cap), and a high cap is nearly free anyway,
because a model that finishes in 500 tokens is not billed for the headroom it did not use.

**Consequence.** Truncation is eliminated as a confound, and any residual `finish_reason:
length` is now a reportable anomaly rather than routine. The cap must be re-checked if a
longer-reasoning model joins the pool.

---

## D-019 — A response that did not finish is an abstention, never an answer

**Decision.** Stage A records an extracted answer only when `finish_reason` indicates a
natural stop. Responses cut off by the token cap or ended by a provider error are banked as
abstentions with their text retained, and the unfinished rate is reported per agent.

**Why.** Extraction takes the last matching answer in the text, which is sound for a completed
argument and wrong for a truncated one. Unterminated reasoning is full of provisional
statements — "this would give B" written while enumerating options the model then rejects — so
in a cut-off stream the "last answer" is wherever the guillotine fell. Measured in
`probe-gpqa`: three of Gemini's five runaway responses yielded a confident-looking letter this
way, and one errored response reporting zero output tokens was banked as a valid answer.

The bias is not symmetric, which is what makes it dangerous. Truncation strikes the agents
that reason at length, so scoring their cut-off streams as wrong answers systematically
understates exactly the models the expert-based protocols are meant to identify.

**Consequence.** Abstention rate and error rate stay distinguishable, which the governance
metrics need since an abstention is not a vote (D-011). The cost is that a genuinely
unparseable but complete response and a truncated one are both abstentions; `finish_reason` is
kept on every record so the two can be separated in analysis.

---

## D-020 — Tasks are screened for discrimination before Stage B is priced

**Decision.** `mas_harness/analysis/discrimination.py` classifies every task from the Stage-A
bank alone, and Stage B runs on the discriminating tasks plus a sampled control of the rest.

**Why.** When every agent independently gives the same answer, every protocol returns that
answer for a structural reason, so the task yields a concordant pair in every comparison and
contributes nothing to a McNemar test. The maximum possible spread between two protocols is
therefore the fraction of tasks on which agents disagree. In `pilot9-b` that was 11.1% against
a gate threshold of 8pp — an experiment arithmetically unable to find the effect it was
designed to find, regardless of how many tasks were added.

Screening is free in both senses. It reads the bank rather than calling models, and because
Stage A *is* the screen, the answers it examines are the same ones Stage B replays, so nothing
is paid for twice.

**Consequence.** Selecting on disagreement changes the population, and accuracy figures from
the selected subset are conditional rather than representative of the benchmark. The paper
must report the selection rule and the discrimination rates alongside any accuracy number.
Non-discriminating tasks are sampled rather than dropped, because "a unanimous group holds its
answer" is an assumption about interactive protocols, and the control sample is what tests it.

---

## D-021 — Pool headroom is checked before Stage B is priced, and it gates the pool, not the suite

**Decision.** A pool is admissible for the governance experiment only if the rate at which *at
least one* member answers correctly exceeds the best single member's accuracy by more than the
effect the gate asks for. The check runs on the Stage-A bank, costs nothing, and is a
precondition on the pool rather than a result.

**Why.** Every protocol in the registry decides among answers already in the bank, so
`P(at least one member correct)` is a hard ceiling and the strongest member is the baseline
every governance rule has to beat. The difference is all the accuracy that governance can
possibly win. On `hard366-a` that difference is **4.37pp** against a gate threshold of 8pp, so
no protocol we could add — judge, verifier, debate, veto or chair — could have cleared the gate.
Buying those episodes would have produced a NO GO that was arithmetic, not evidence.

The cause is pool shape, not task difficulty. D-020 fixed the suite: 46.2% of the 366 hard tasks
are discriminating, up from 11.1%. What remains is that `gpt5mini` is 8.7pp better than the next
member and 28pp better than the weakest, and the effect of that is stark:

| coalition | headroom | expert vs vote |
|---|---:|---:|
| with `gpt5mini` | 1.6–4.4pp | expert wins by 0.7pp, 1.8% discordance |
| without it | 5.2–17.2pp | vote wins by 4.6pp, 5.1% discordance |

Every coalition containing the dominant agent is *worse* than that agent alone, so there is no
complementarity for the coalition direction to find either — which is what the 4.4% top-k gap
was reporting. The extreme case is instructive: `gemini25flash` + `mistral-small`, 1.9pp apart in
competence, has 17.21pp of headroom and 13.1% discordance, and the vote beats deferring to the
stronger of them by 12.6pp.

**Consequence.** Competence homogeneity becomes an explicit design variable rather than an
accident of which models were cheap. The sign of the expert-versus-aggregation effect reverses
with it, which makes pool composition a manipulation worth running in both directions rather
than a nuisance to be tuned away: a dominant-agent pool is the control that shows the governance
effect disappearing. The cost is that absolute accuracy is not comparable across pools, so
protocol contrasts must be read within a pool.

**Amended by D-023.** Competence homogeneity turned out to be necessary and not sufficient: the
screen found a pool 1.7pp from top to second whose headroom is still only 5.83pp, because its
members' errors coincide. The design variable is error decorrelation, and dominance is one of two
ways to lose it.

---

## D-022 — An agent's commit rate is a precondition on the instrument, not a score to rank it by

**Decision.** Before a candidate model is scored on accuracy or complementarity, it must produce a
readable answer on at least 95% of calls. Below that it is excluded from pool selection as a broken
instrument. `commit_rates` in `mas_harness/analysis/pool_select.py` measures it from the bank, and
the exclusions are printed and recorded in the report.

**Why.** An unfinished or unparseable response is an abstention and scores as wrong (D-011, D-019).
To `headroom` an abstention is indistinguishable from a decorrelated error: it is wrong, and it is
wrong on different items than a working model's mistakes. So an unreliable agent inflates the exact
quantity the selector maximizes, and the selector will prefer it.

This is not hypothetical. Run without the criterion, the selector's top recommendation was
`gemini25flash-hi, glm45air, mistral-small, novalite` at 30.51pp of headroom — a pool whose two
highest-headroom contributors commit on 0.650 and 0.602 of calls. Most of that 30pp was missing
data. The measured slate separates cleanly, which is where the threshold comes from:

| agent | commit rate | unfinished | accuracy |
|---|---:|---:|---:|
| `gpt5mini`, `deepseek32`, `llama4scout`, `novalite` | 1.000 | 0.000 | — |
| `gptoss120b`, `mistral-small` | 0.992 | 0.000–0.008 | — |
| `qwen3-30b` | 0.984 | 0.016 | — |
| `gemini25flash` | 0.757 | 0.077 | 0.623 |
| `gemini25flash-hi` | 0.650 | 0.150 | 0.558 |
| `glm45air` | 0.602 | 0.398 | 0.534 |

**Consequence.** `gemini25flash` fails this criterion at 0.757 and is nevertheless kept in
`openrouter4`, which is now an admitted defect in the control pool rather than an oversight: it was
banked before the criterion existed, it is the only Google-family member, and the control pool's job
is to show the governance effect vanishing under dominance, which its 24% abstention rate does not
threaten. No pool built after this decision may include it, and any accuracy figure for it is a
figure about our extraction as much as about the model.

The criterion also settles the reasoning-budget question `candidates.yaml` was built to ask. Raising
Gemini's budget from 2,048 to 8,192 tokens made it worse on all three axes — accuracy 0.551 against
0.653, non-termination 0.150 against 0.077, commit rate 0.650 against 0.757 — so the clamp was not
suppressing performance and stays.

---

## D-023 — Error decorrelation is the design variable; competence homogeneity is a proxy for it

**Decision.** Pools are designed on measured error decorrelation, with the dominance gap kept as a
constraint rather than the objective. The three-pool design is a manipulation of decorrelation with
competence structure crossed against it, not a single peer pool replacing a single dominant one.

**Why.** D-021 read the `hard366-a` failure as dominance, because dominance was the visible feature.
Screening ten models on 120 shared tasks shows that was the symptom. Across the 35 four-member
subsets of the seven reliable candidates, headroom correlates with mean pairwise error correlation at
**−0.643** and with mean pool accuracy at **−0.618**, and accuracy correlates with error correlation
at **+0.741**. The strong models agree with each other, and agreement is what destroys headroom:

| pool | mean accuracy | dominance gap | error corr | headroom |
|---|---:|---:|---:|---:|
| `deepseek32`, `gpt5mini`, `gptoss120b`, `qwen3-30b` | 0.821 | **1.7pp** | +0.595 | **5.83pp** |
| `deepseek32`, `gptoss120b`, `llama4scout`, `qwen3-30b` | 0.756 | 3.3pp | +0.436 | 8.33pp |
| `gptoss120b`, `qwen3-30b`, `llama4scout`, `novalite` | 0.673 | 3.3pp | +0.336 | 10.00pp |

The first row is the refutation: it is the most competence-homogeneous pool available, 1.7pp from top
to second, and it fails the gate anyway. A pool selected on homogeneity alone would have been bought
and would have produced the same arithmetic NO GO as `hard366-a` for a different reason.

**Consequence.** This dissociates two mechanisms that `hard366-a` confounded, and the middle row
becomes a control worth paying for rather than a rejected candidate: it holds competence homogeneity
at its best achievable value while varying decorrelation. The claim the design can then support is
that governance headroom comes from decorrelation and not from peer competence — a stronger and more
falsifiable statement than "dominant agents suppress governance effects".

It also imposes a cost the paper must state. Decorrelation is available here only at lower absolute
accuracy: the decorrelated pool averages 0.673 against 0.821 for the homogeneous one. So a recovered
answer in the decorrelated pool is one that a *weaker* set of agents produced, and the governance
effect must not be read as "governance beats a strong model". Whether decorrelation at high
competence exists at all is an open empirical question on this candidate slate, and answering it
would need models selected for divergent training rather than for price. The `screen-strong` run
tests exactly that, on six lineages not previously measured.

**Partly refuted by D-025.** The accuracy cost stated here was an artifact of coverage, not a finding.
`grok43` passed the screen at 0.875 and was never banked on the full suite, so the selector that
produced the −0.618 accuracy/headroom correlation never saw it. With it banked,
`grok43, gpt5mini, deepseek32, llama4scout` has 8.20pp of headroom at 0.823 mean accuracy against the
control's 0.842 — decorrelation at high competence does exist here. What survives is the mechanism:
correlation is the design variable, and the three-pool contrast is unchanged. What does not survive is
the claim that the paper must concede a competence deficit; it must not, because the primary treatment
and the control now reach the same `single_expert` accuracy to four decimal places.

---

## D-024 — The aggregator is fixed across pools and chosen as a cost lever, not per protocol

**Decision.** One aggregator model serves every protocol that needs a neutral third party, it is
identical across every pool that receives priced episodes, and it is
`anthropic/claude-sonnet-5` at $2/$10 per M rather than `anthropic/claude-sonnet-4.6` at $3/$15.

**Why fixed.** `independent_judge` and `chair_information_seeking` are the two protocols whose
decision is made by the aggregator, and the whole point of the two-pool design (D-023) is that the
only difference between the pools is their members. An aggregator that varied with the pool would
confound the pool contrast with judge identity, and the judge is the agent actually choosing the
answer in those two protocols.

**Why it is the cost lever.** The aggregator drives 87% of the priced sweep. Per-protocol dry-run
estimates on 199 tasks, grand coalition, one seed, no interventions:

| protocol | est. cost | called |
|---|---:|---|
| `chair_information_seeking` | $48.12 | aggregator ×2, members ×2 |
| `independent_judge` | $22.87 | aggregator ×1 |
| `debate_vote` | $5.94 | members ×4 |
| `expert_verifier` | $2.97 | members ×2 |
| `expert_veto` | $1.48 | members ×1 |

The chair dominates because it sends the full anonymized peer block twice — once to compose its
question, once to decide — and that block is the concatenation of every member's complete response.
So aggregator input price is multiplied by coalition verbosity twice per episode.

**Why Sonnet 5 rather than Haiku.** Haiku 4.5 at $1/$5 would cut the sweep to roughly $27, but the
judge's competence is not a free parameter: `independent_judge` and the chair exist to test whether a
neutral reader can recognise a correct answer a vote would discard, and a weaker reader would make
that look impossible for reasons that have nothing to do with governance. Sonnet 5 is strictly
preferable to 4.6 — same family, newer, one third cheaper — so it costs nothing scientifically.

**Consequence.** `openrouter4` keeps Sonnet 4.6 in its config because its bank is already written and
it receives only free protocols, where the aggregator is never called. If it is ever promoted to a
priced pool it must be re-declared with Sonnet 5 first, and that changes its pool content hash.
Separately, the estimator plans 4,200 output tokens per peer answer while the reliable candidates
average 1,580, so these figures are roughly 2.7x conservative on the carrying term; the priced sweep
is still to be measured on a small slice before the full run is committed.

---

## D-025 — Pools are selected on the full suite, and a candidate that passes the screen must be banked before it is ranked

**Decision.** The 120-task screen decides only two things: which models are excluded as broken
instruments (D-022), and which are worth banking on all 366 tasks. Every quantity that a pool is
*chosen* on — headroom, dominance gap, error correlation — is read at n=366. A model that passed the
commit floor is banked on the full suite before any pool is ranked with or without it.

**Why.** Both halves of this rule were learned by violating them.

`ring26` improved all four selection criteria at n=120 — headroom 9.89 to 10.83pp, dominance 3.02 to
1.67pp, correlation +0.409 to +0.392, accuracy 0.720 to 0.752 — and was substituted into the treatment
pool on that basis. Re-measured at n=366 it *cost* 1.1pp of headroom and *raised* correlation. One task
is 0.83pp at n=120 and 0.27pp at n=366, so pools separated by two tasks on the screen are not separated
at all, and the screen ranked twelve models by differences of that size.

`grok43` is the more expensive mistake. It passed the screen at 0.875 with a 1.000 commit rate — the
best of the twelve on both axes — and was then left at 120 tasks while the selector ran over the nine
models that happened to be banked. Because it was absent, the selector could not see the pool that
answers D-023's open question, and D-023 was written asserting that decorrelation at high competence
does not exist on this slate. It does. `grok43` scores **0.885 on 366 tasks**, and
`grok43, gpt5mini, deepseek32, llama4scout` has **8.20pp** of headroom at **0.823** mean accuracy:

| pool | mean acc | dom | corr | headroom | `single_expert` |
|---|---:|---:|---:|---:|---:|
| `strong4` | 0.823 | **0.3pp** | +0.408 | **8.20pp** | **0.8989** |
| `decorrelated4` | 0.734 | 2.19pp | +0.382 | 9.29pp | 0.8552 |
| `correlated4` (control) | 0.842 | 1.6pp | +0.579 | 4.92pp | **0.8989** |

The cost of the omission was not the $0.86 the extra banking turned out to cost; it was that a whole
paragraph of D-023 stated as an empirical finding something that was a gap in coverage.

**Consequence.** `strong4` becomes the primary treatment and `decorrelated4` a low-competence
replication. This is a materially better design than the two-pool one it replaces: `strong4` and the
control reach *identical* `single_expert` accuracy (0.8989 both) and are matched on dominance to within
1.3pp, so the pools differ in decorrelation and in essentially nothing else that the outcome depends
on. Under `decorrelated4` the treatment was 11pp weaker on average, and any governance effect would
have been open to the objection that it was really about competence.

The rule has a cost of its own: banking every screen survivor on the full suite is more expensive than
banking the ones that look best. At the prices here that is a few dollars, and it is cheap next to
writing a decision record about an artifact.

---

## D-026 — Pre-registration: the veto's sign is predicted to follow error decorrelation, tested on a pool not yet priced

**Written before the `decorr4-a` priced run, deliberately.** The interaction it tests was found
post-hoc on `strong4-a` and `correlated4-a` (+10.53pp on shared tasks, 95% CI [+3.16, +17.89],
p=0.0052). A post-hoc interaction supported by 16 discordant items is a hypothesis, not a result. This
record exists so that the next run is a test of it rather than a second look at it.

**The claim.** `expert_veto` improves accuracy when pool members' errors are decorrelated and degrades
it when they are correlated, because the majority a veto overrides is more often right when peers fail
together.

**The prediction.** On `decorrelated4` (`gptoss120b, llama4scout, mistral-small, ring26`, mean pairwise
error correlation **+0.382**, headroom 9.29pp), the paired difference
`accuracy(expert_veto) − accuracy(single_expert)` on the pool's discriminating tasks will be
**strictly positive**. This is directional and one-tailed; it was +3.37pp on `strong4-a` at +0.408
correlation and −6.20pp on `correlated4-a` at +0.579.

**What confirms it.** A positive point estimate, and a pool-by-protocol interaction against
`correlated4-a` whose 95% CI excludes zero on the tasks the two pools share.

**What falsifies it.** A point estimate at or below zero. There is no reading of a null or negative
result here that rescues the mechanism, because `decorrelated4` sits *between* the two measured pools
on nothing and *with* the treatment on the one variable claimed to matter — it is more decorrelated
than `strong4` (+0.382 against +0.408) and has more headroom (9.29pp against 8.20pp). If decorrelation
drives the sign, this is the pool where the effect should be clearest.

**Known weaknesses of the test, recorded in advance.** `decorrelated4` is 9pp weaker in mean member
accuracy than `strong4` (0.734 against 0.823) and 4.4pp lower on `single_expert` (0.8552 against
0.8989), so a positive result is not a clean replication at matched competence — it is a replication of
the *direction* at different competence. Its 15-task calibration slice is already banked and will be
reused, so the run is 195 new tasks and not a fully independent 210. And a one-tailed prediction on one
protocol is a single test: confirming it licenses the claim about `expert_veto`, not about governance
protocols generally.

**Cost.** ~$16.30, roughly $52.55 of dry-run estimate at the measured 3.0x conservatism, less the
calibration episodes already paid for. Per-run cap is $75 and today's spend is $38.07 against a $150
daily cap, so the run fits without raising anything.

---

## D-027 — D-026 is falsified. The veto interaction was noise, and the pre-registration is what caught it

**Outcome.** The prediction failed. On `decorrelated4`, `expert_veto` minus `single_expert` is
**−1.90pp** (n=210, 14 discordant, p=0.424) where D-026 predicted strictly positive. Worse for the
mechanism, the effect is not monotonic in the variable claimed to drive it:

| pool | mean error correlation | `expert_veto` effect |
|---|---:|---:|
| `decorrelated4` | +0.382 | **−1.90pp** |
| `strong4` | +0.408 | **+3.37pp** |
| `correlated4` | +0.579 | **−6.20pp** |

A moderator cannot produce a positive effect only in the middle of its own range. Error decorrelation
does not explain the veto's sign, the +10.53pp interaction (95% CI [+3.16, +17.89], p=0.0052) did not
replicate, and by the terms written down in advance there is no reading that rescues it. D-026 is
withdrawn.

**What it was.** The interaction rested on 5 and 11 discordant tasks across two pools. Sixteen items
carried a 10pp effect with a p-value of 0.005, which is exactly the shape of a finding that is really
sampling variation in a small discordant set. The bootstrap CI was honest about width and still
excluded zero, which is worth remembering: a tight-looking interval computed on 16 informative items is
not evidence of stability, only of what those 16 items happened to say.

**Why this is a good outcome.** The claim was one run away from a paper. It cost **$17.93** to refute,
the refutation is unambiguous because the prediction was directional and recorded first, and no
reviewer had to find it. Had the two-pool result been written up, the third pool would have refuted it
after publication. This is the two-stage design and the pre-registration discipline paying for
themselves in the same run.

**Consequence for the governance direction.** Its status drops from PARTIAL to **NO GO**, and on
better grounds than the gate's. Across three pools, five priced protocols and 2,514 priced episodes, no
protocol reliably beats deferring to the predicted expert, and the protocols with the largest apparent
effects are the ones whose sign is least stable:

| protocol | `decorr` +0.382 | `strong` +0.408 | `corr` +0.579 | |
|---|---:|---:|---:|---|
| `independent_judge` | +4.76 | +0.56 | +0.00 | never negative |
| `chair_information_seeking` | +4.76 | +3.37 | −3.10 | sign varies |
| `debate_vote` | +5.24 | +0.00 | −3.88 | sign varies |
| `expert_veto` | −1.90 | +3.37 | −6.20 | sign varies |
| `expert_verifier` | −1.43 | +0.00 | −0.78 | never positive |
| `independent_majority` | −0.95 | +0.00 | −4.65 | never positive |

`independent_judge` is non-negative in all three pools and `expert_verifier` and plain majority voting
are never positive in any. Those are the two patterns worth a *future* pre-registration, and they are
explicitly **not** results here: with five protocols and three pools there are fifteen effects, and
finding one that never changes sign is unremarkable under the null. Naming them as findings now would
repeat the error D-026 was written to catch.

**Consequence for the project.** Delegation is the direction. It passed both criteria on all three
pools independently — configuration dominance 41.7%, 58.3% and 75.0% against a 75% ceiling, and
semantic-versus-organizational Spearman 0.028 to 0.063 with 99.5-100% of tasks having a different
nearest neighbour in the two spaces. Note the 75.0% reading on `decorrelated4` sits exactly on the
threshold, so that criterion is passing by a margin of zero on one of three pools and needs more
protocol families before it can carry weight.

Governance is not worthless, it is *reframed*: the mask-flip rate is 24.5-25.0% on every pool, so
influence and competence genuinely diverge, and that measurement is stable where the accuracy effects
are not. The publishable governance claim from this data is about influence, not about which protocol
wins.

---

## D-028 — Aggregator non-termination is missing data, not a wrong answer, and OpenRouter's reasoning controls do not work for Anthropic models

**The defect.** `anthropic/claude-sonnet-5` sometimes spends all 16,384 output tokens on internal
reasoning and emits **zero** visible characters. `finish_reason` is `length`, so D-019 records an
abstention, which scores as wrong. The penalty lands only on `independent_judge` and
`chair_information_seeking`, the two protocols the aggregator decides. Member-decided protocols are
untouched. So the harness was systematically penalizing exactly the protocols whose whole purpose is to
read everything before deciding.

**Corrected 2026-08-10.** This record originally said "25 of 366 tasks, all GPQA-Diamond". Both halves
were wrong, and the error is instructive: the denominator was taken from the suite rather than from
what the aggregator actually ran on. The paid protocols only ever ran on each pool's discriminating
subset, so 366 was never the right base. Measured directly by
[`scripts/count_aggregator_truncation.py`](scripts/count_aggregator_truncation.py):

| pool | `independent_judge` | `chair_information_seeking` | distinct tasks affected |
|---|---|---|---|
| `strong4` | 7 of 179 (3.9%) | 7 of 178 (3.9%) | 8 of 179 in scope |
| `decorrelated4` | 9 of 210 (4.3%) | 3 of 210 (1.4%) | 9 of 210 in scope |
| `correlated4` | 6 of 129 (4.7%) | 5 of 129 (3.9%) | 7 of 129 in scope |

24 distinct pool-task pairs, 13 distinct tasks. Nor is the concentration total: of 37 affected
episodes, 33 are GPQA-Diamond and **4 are MATH-500**. Neither correction changes any conclusion below —
the per-protocol rate is about 4% either way, and dropping the episodes still removes disproportionately
hard items — but "all GPQA-Diamond" was a claim about the mechanism, and it is not true.

The magnitude is not negligible. Re-scored with the truncated episodes dropped:

| pool | as scored | truncated dropped |
|---|---:|---:|
| `strong4` | +0.56pp | +2.91pp (p=0.38) |
| `decorrelated4` | +4.76pp | +6.97pp (**p=0.0066**) |
| `correlated4` | +0.00pp | +3.25pp (p=0.42) |

**Reasoning controls are silently ignored.** Probed on the exact failing prompt
([`scripts/probe_aggregator.py`](scripts/probe_aggregator.py)), all three OpenRouter reasoning
parameters produced *identical* 16,384-token non-terminating responses:

| variant | output tokens | content | reasoning |
|---|---:|---:|---:|
| as configured | 16,384 | 0 chars | 16,024 chars |
| `reasoning: {max_tokens: 1024}` | 16,384 | 0 chars | 15,634 chars |
| `reasoning: {effort: "low"}` | 16,384 | 0 chars | 15,366 chars |
| `reasoning: {exclude: true}` | 16,384 | 0 chars | hidden |

`exclude` suppresses the *display* of reasoning, not its *generation* — it burns the same budget and
returns nothing at all. This is specific to Anthropic on OpenRouter: the identical parameter fixed
Gemini's runaway generation in D-018, which is why it was tried here. **Cost of learning this: $9.57**
on a retry run that could not have worked, plus $0.66 on the probe that explained why. Recorded so it
is not repeated.

**The answer is not recoverable.** The `reasoning` field does contain 16,024 characters, so the text
exists, but it terminates mid-sentence with the model still working — "which complicates the retro-DA
mechanism" — having reached no conclusion. There is no answer to extract. Reading `message.reasoning`
in addition to `message.content` would not rescue these episodes.

**Decision.** Aggregator non-termination is reported as **missing data**, and every accuracy figure for
an aggregator-decided protocol is reported twice: scored-as-wrong, and with the non-terminating
episodes excluded. Neither number is privileged. Scored-as-wrong is the honest deployment figure,
because a judge that returns nothing has genuinely failed to judge. Excluded is an upper bound and a
biased one, because non-termination concentrates on the hardest tasks — all 25 are GPQA-Diamond — so
dropping them removes items the judge was more likely to get wrong anyway.

**Why this does not change the headline.** Even on the optimistic bound, the judge's advantage over
`single_expert` is significant in one pool of three, and that one pool is `decorrelated4` — the same
pool whose `expert_veto` result looked good and then failed to replicate (D-027). One-of-three with the
favourable accounting is not "reliably beats"; D-027's conclusion stands. But it stands for a weaker
reason than stated there, and the honest version is that the judge is the most promising protocol we
measured and we cannot presently tell whether it wins.

**Consequence.** Raising `max_tokens` is the only remaining lever and it is untested; the model may
simply reason longer, since it showed no sign of converging at 16,384. Before any further aggregator
spending, the open question is whether these tasks are answerable by this model at any budget. A
cheaper design change would be to require the answer letter *before* the explanation, which caps the
cost of non-termination at zero — but it alters every aggregator prompt and therefore invalidates the
whole priced cache, so it belongs to the next round rather than this one.

---

## D-029 — The delegation GO was an artifact. A criterion that cannot fail is not evidence, and neither of delegation's two criteria had a noise control

**Decision.** `protocol_dominance` is retired as evidence. Any claim that the best organization
depends on the task must show that the per-group winner **reproduces** across a split of that group's
tasks, and specifically that the groups *departing* from the single best configuration reproduce.
Implemented in [`mas_harness/metrics/stability.py`](mas_harness/metrics/stability.py).

**Why.** The gate awarded delegation a GO on two criteria. The first, configuration dominance, is
noise. Shuffling protocol labels within each task destroys every real protocol difference while
preserving task difficulty and the domain structure; dominance on the shuffled data reads 54-59%
against observed values of 42-67%, and the null's 95th percentile lands on **75.0%** — the gate's own
threshold. Observed dominance is *below* the null mean in two of three pools, and
`P(null >= observed)` is 0.76, 0.97 and 0.38. The criterion passes at about the rate noise passes it.

The cause is the denominator. The priced subsets hold a median of 8-15 tasks per domain and the
thinnest domains hold **one to three**, so a domain's "winning protocol" is frequently just whichever
protocol got a single task right. Adding protocols would have made this worse while appearing to help:
averaged over random sub-families, dominance falls from 74-85% at four protocols to 58-75% at seven,
purely by dilution. The planned "widen the protocol family" fix would have moved the number away from
the threshold and measured nothing.

**What replaces it, and what it says.** Reproducibility is measured on the two free protocols across
**all 366 tasks and all 15 coalitions** — better powered than the priced subset and free, since those
episodes were already banked. The result is the same in all three pools and both groupings:

| pool | dominant configuration | groups it wins | reproducibility on it | groups departing | reproducibility off it | null |
|---|---|---:|---:|---:|---:|---:|
| `strong4` | `independent_majority[0-1-2-3]` | 8 | 0.98 | 4 | **0.01** | 0.28 |
| `decorrelated4` | `independent_majority[0-1-2-3]` | 9 | 0.92 | 3 | **0.02** | 0.20 |
| `correlated4` | `independent_majority[0-1-2-3]` | 7 | 1.00 | 5 | **0.15** | 0.38 |

The one reproducible fact is *run majority vote over the whole pool*. Every domain that picks anything
else is not merely unproven — it reproduces **below** the noise floor. There is nothing to route over.

Aggregate reproducibility looks healthy (0.65-0.69, p <= 0.0033) and is entirely carried by the
domains the dominant configuration wins. That is why the report separates the two: averaging them
conceals the only quantity routing depends on.

**The second criterion is untested and suspect for the same reason.** Semantic-versus-organizational
Spearman of 0.048-0.063 was read as the organizational space capturing something semantics does not.
But that space is built from per-task utility vectors over configurations, and this record establishes
that those vectors are mostly noise. **Noise is uncorrelated with semantics too.** The criterion has no
permutation null, so it cannot presently distinguish "a real organizational structure orthogonal to
meaning" from "no structure at all". It must not be cited until it has one.

**Consequence.** All three directions now fail on the MVP data, and delegation fails for a more
interesting reason than the other two: not that the effect is small, but that the measurement could
not have come out any other way. No further spending on extending the priced protocols — the
authorized ~$120-180 would have bought more of the axis with no reproducible signal.

**The cost of catching it here.** $0. The check ran on banked episodes, before the branch's first
protocol was written. Had it run after, the new protocols would have lowered dominance, the criterion
would have passed by a wider margin, and the artifact would have been reported as a fix.

---

## D-030 — Delegation's second criterion also cannot fail, and the routing evidence for the direction leaks the answer

**Decision.** The semantic-versus-organizational similarity criterion is retired alongside
configuration dominance (D-029). Routing regret computed in the organizational or capability space
is withdrawn as evidence for anything. A task space may only be credited with routing value if its
coordinates for a task are available **before** any configuration is run on that task.

**The criterion passes identically on noise.** Rebuilding the organizational space from outcomes
whose configuration labels are shuffled within each task destroys all differential fit while leaving
task difficulty intact. The criterion cannot tell the difference
([`scripts/audit_delegation_criterion.py`](scripts/audit_delegation_criterion.py)):

| pool | observed rho | noise rho | observed differing | noise differing |
|---|---:|---:|---:|---:|
| `strong4` | +0.0275 | +0.0350 | 100.0% | 99.7% |
| `decorrelated4` | +0.0411 | +0.0428 | 99.5% | 99.5% |
| `correlated4` | +0.0629 | +0.0578 | 99.5% | 99.8% |

The logic was inverted from the start. The criterion rewards *low* correlation with semantics and
*high* neighbour disagreement, and a structureless space maximises both. It was satisfied most
easily by having nothing to say. Both of delegation's criteria therefore passed for the same reason:
neither had a null, and neither could fail.

**The routing evidence leaks.** `nearest_neighbour_routing_regret` locates a test task in the space,
takes its nearest *training* task and adopts that task's best configuration. In the semantic space
that is legitimate, because a prompt embedding exists before anything runs. In the organizational and
capability spaces the test task's coordinates **are its own outcomes**, so its nearest neighbour is a
task solved by the same configurations and the adopted configuration is one that already solved it.
Near-oracle regret is the signature of the leak, not a result:

| pool | semantic (honest) | capability (leaks) | organizational (leaks) | fixed best |
|---|---:|---:|---:|---:|
| `strong4` | 0.0902 (**−0.0123**) | 0.0244 | 0.0079 | 0.0779 |
| `decorrelated4` | 0.1189 (**+0.0316**) | 0.0324 | 0.0160 | 0.1505 |
| `correlated4` | 0.0494 (**−0.0124**) | 0.0206 | 0.0123 | 0.0370 |

**The only honest router loses to a fixed best configuration in two pools of three**, and its one win
is on the pool whose results have failed to replicate twice already (D-027, D-029). This agrees with
D-029 from an independent direction: if the reproducible fact is "run majority vote over the whole
pool", then a fixed configuration is hard to beat and a router should indeed fail.

**What is actually untested.** The direction's real proposal was to *predict* a task's delegation
fingerprint from features known in advance, then route on the prediction. That was never built, so it
has not been refuted — but the evidence offered for it was two criteria that could not fail and a
regret comparison that read the labels. Nothing currently supports starting the encoder.

**Consequence.** All three directions fail on the MVP data. Delegation is not merely unsupported; the
apparatus that supported it was measuring nothing, on both criteria and in the operational test. Any
replacement criterion ships with a permutation null and a leakage check in the same commit as the
criterion itself.

---

## D-031 — Specialisation does not rescue delegation. 134 real agent systems across 8 codebases show no reproducible per-domain winner

**Decision.** Do not build a specialised pool or new task adapters on the current evidence. The
hypothesis was pre-tested for $0 on public data and failed under conditions considerably more
favourable than the proposed experiment
([`scripts/pretest_specialist_routing.py`](scripts/pretest_specialist_routing.py)).

**The hypothesis.** D-029 and D-030 could be explained by pool composition rather than by the absence
of routing: four strong generalists on three flavours of hard STEM may simply have nothing to route
between. The remedy would be a specialised pool on a heterogeneous suite - which needs new sources,
new evaluators, and fresh Stage A banks.

**The free test.** `agent-psychometrics` ships SWE-bench Verified as a dense matrix of 134
independently built agent systems by 479 instances, grouped by the repository each instance patches
(8 repositories with at least 12 instances). This is far more heterogeneous than any four-model pool:
different scaffolds, different base models, different labs, different years, on eight distinct
codebases. If specialisation-based routing exists anywhere, it should be visible here.

| pool | accuracy range | reproducibility | null | off-dominant | verdict |
|---|---|---:|---:|---:|---|
| top 8 | 0.772-0.804 | 0.114 | 0.185 | 0.040 | NO EVIDENCE |
| top 16 | 0.745-0.804 | 0.119 | 0.097 | 0.073 | NO EVIDENCE |
| top 32 | 0.710-0.804 | 0.072 | 0.056 | 0.007 | NO EVIDENCE |
| all 134 | 0.004-0.804 | 0.073 | 0.011 | 0.009 | NO EVIDENCE |

The winning system for a repository survives a resplit of that repository's instances between 0.7%
and 7.3% of the time. One system, `trae_doubao_seed_code`, is the argmax in the plurality of
repositories at every pool size, and every repository that departs from it departs unreproducibly.

**A floor was added to the metric, because it produced a false positive here.** At 134 candidates the
permutation null collapses to 0.011 - the argmax of 134 noisy systems essentially never survives a
resplit - so an off-dominant reproducibility of 0.009 cleared it and the report read EVIDENCE. That
is the same failure mode as D-029: a comparison that cannot fail once its reference point degenerates.
`variety_is_reproducible` now also requires the winner to replicate on at least half of random
half-splits (`MIN_REPRODUCIBILITY`), which is the weakest absolute statement under which "the best
configuration for this group is X" means anything.

**What this does and does not establish.** Eight Python repositories differ in knowledge but not in
*capability*: they are all software engineering. A suite spanning code, competition mathematics and
theory of mind would be more heterogeneous than astropy against django, and this result does not
close that off. What it does is move the burden of proof. Specialisation was the leading explanation
for the D-029 null, and in the largest public agent-by-task matrix available it does not produce
reproducible per-group winners at any pool size. A specialised pool should not be bought until some
cheaper evidence says routing signal exists.

**Cost of the test.** $0, against an estimated several hundred dollars and multiple weeks for the
adapters, evaluators and banks the specialised design would have required.

---

## D-032 — A cross-capability suite, because every suite so far has been one capability in three costumes

**Decision.** Add `cruxeval`, `aime` and `exploretom` as first-class suites and build
[`configs/suites/crosscap240.yaml`](configs/suites/crosscap240.yaml): 60 tasks each of code
execution reasoning, competition mathematics, theory of mind, and graduate science.

**Why these four.** D-029 found one reproducible fact on `hard366` and D-031 found the same on 134
agent systems across 8 SWE-bench repositories. Both share a weakness: `hard366` is GPQA-Diamond,
MATH-500 level 5 and MMLU-Pro theoremQA/scibench, which is hard technical reasoning three times over,
and eight Python repositories differ in knowledge but are all software engineering. Neither can
distinguish "routing does not exist" from "these tasks demand the same thing". This suite demands
four different things, and theory of mind in particular shares no technical content with the others.

**Design choices that follow from earlier failures.**

*Sixty per domain, not 122.* The delegation metric splits each domain's tasks in half, and
`hard366`'s median of 8-15 tasks per domain is precisely why its per-domain winners were noise
(D-029). Sixty is four to seven times thicker. AIME caps the balance at 60 - thirty problems from
2024 and thirty from 2025 - and balance is worth more than raw count here.

*Output prediction rather than code generation.* CRUXEval asks what a function returns. Generation
would need sandboxed execution, which is a subsystem rather than an adapter, and its pass rate would
depend on the harness as much as on the model. Output prediction demands the same execution
reasoning and grades by comparing a Python literal.

*False-belief stories only.* ExploreToM stories where belief and reality agree are answerable by
reading comprehension, so every agent gets them right and they contribute nothing to a protocol
comparison - D-020's saturation failure in a different costume. The filter cuts 13,309 rows to 7,316.

*Tagged answers, and extraction that refuses to guess.* These answers are a Python literal, an
integer and a short noun phrase, none of which a terminal-token rule can recover without recreating
D-011, where prose ending in a letter became a confident vote. The prompt mandates `[ANSWER]...
[/ANSWER]` and extraction requires it, with one fallback for an explicit "the answer is". Anything
else is a parse failure, which keeps abstention distinguishable from error. Tests assert that the
worked example in each instruction actually parses, since the D-011 bug was exactly a mandated format
the extractor did not implement.

**Status.** Adapters, manifest and 38 tests are in; the manifest builds to 240 tasks balanced 60 per
domain, 80 calibration and 160 test. Nothing has been run. Stage A on this suite is roughly $3-6 by
comparison with `hard366-a` at $4.56, and **discrimination must be checked before any protocol is
priced**: if the pool agrees on nearly every task, no comparison can separate anything and the suite
needs to get harder rather than larger (D-020).

---

## D-033 — Build the router before buying more capabilities. The headroom is real, and selection variance eats all of it

**Decision.** Do not buy the eight-capability expansion the previous entry proposed. Build
`q(x, S, p)` first on data already banked, because it costs nothing and it turned out to answer a
different and more important question than the expansion would have.

**Why the expansion was dropped.** The candidates available in the local cache - gsm8k, ai2_arc,
mmlu-redux, MATH-500 at mixed levels - are close to saturated for these pools. A group in which every
organization ties contributes an argmax over ties, which is noise; four such groups would pull the
reproducibility statistic *toward* the null rather than stabilising it. That is D-020's saturation
failure re-entering through the door marked "more groups". The genuinely distinct hard capabilities
in the cache are already in `crosscap240`.

**What was built instead.** [`mas_harness/metrics/routing.py`](mas_harness/metrics/routing.py), the
first honest implementation of the direction's actual proposal: predict which organization solves a
task from features available in advance, then route on the prediction. D-030 noted this had never
been built and so had never been refuted. It is now built and it is now refuted.

**The baseline was leaking too, which no earlier entry noticed.**
`utility.fixed_best_selection` maximises utility over the set it is scored on, so when D-030 compared
a router against "the best fixed configuration", the comparator had itself seen the test outcomes.
Everything in the new module is frozen on calibration tasks, and a test asserts the baseline scores
zero where the calibration winner is the test loser.

**Result, over 60 stratified resplits per cell.** Mean gain over the frozen fixed-best baseline, in
accuracy points, with both suites on the same three pools and the same 30 organizations:

| suite | strong4 | decorrelated4 | correlated4 | mean headroom |
|---|---:|---:|---:|---:|
| `hard366` | +0.33 | −0.53 | −0.42 | 7.1 |
| `crosscap240` | +0.08 | −1.78 | +0.03 | 9.6 |

Between four and eleven points of oracle headroom exist in every cell, and no leak-free rule claims
any of it. Semantic k-nearest-neighbour routing is equally flat (+1.40 to −1.36). Cross-capability
tasks did not help: their three cells average −0.56 against −0.21 for the homogeneous suite, which is
the opposite of what D-032 predicted.

**One split would have produced two false findings.** On the manifest split of `crosscap-decorr4` the
best single agent beat the best organization by 10.7 points at p=0.001, and the model scored +2.5 at
p=0.070. Over resplits those are +0.39 and −1.78. Single-split routing numbers are not reportable at
these sample sizes, and `routing_over_splits` is now the reporting unit.

**The diagnosis, which is the part worth keeping.** The shuffled-embedding control - same model, same
30 choices, task-embedding association destroyed - loses 1 to 2.8 points in every cell. So choosing
per task at all costs about two points of variance here. The real embedding beats its own shuffled
twin in 5 of 6 cells, meaning the semantic representation genuinely carries information; it is worth
about what the selection variance costs, and the two cancel. The binding constraint is not the task
representation, which is where both the report and the literature put it. It is that picking one of
30 organizations from ~100 calibration tasks is itself a high-variance operation - the same effect
costs the *fixed* baseline 1.9 to 2.9 points, with a spread of 3.2 to 5.3.

**The sample-size defence was tested and fails.**
[`scripts/measure_routing_pooled.py`](scripts/measure_routing_pooled.py) pools the two suites into
569 unique tasks over 15 domains and sweeps calibration from 57 to 398 tasks. The gain is flat in all
three pools across a sevenfold increase (`strong4` +0.27 to +0.37, `decorrelated4` −1.02 to −1.22,
`correlated4` +0.24 to −0.67) while the headroom stays at 4.1-9.7 points. The spread halves as
calibration grows, so the estimate becomes more precise and stays at zero. The null is an absence,
not a detection failure.

**The group-count defence fails in the same run.** D-032's remaining hope was that `crosscap240`'s
0.735 off-dominant reproducibility on `decorrelated4` was real and merely under-powered at four
groups. At fifteen groups it reads 0.100, 0.257 and 0.291 - all below the 0.5 floor, on all three
pools. Overall reproducibility is genuinely above the null (0.62-0.70 against 0.17-0.31, p=0.000)
and the dominant configuration's groups reproduce at 0.90-1.00, so the metric is working; it is the
*departures* that are noise. One organization is broadly best per pool and the per-domain variety
around it is not real.

**Consequence for the direction.** Delegation as "a better task representation improves routing" is
closed. Three independent lines agree: no reproducible per-domain winner at 15 groups, no gain from a
leak-free learned router at any calibration size, and no gain from semantic nearest-neighbour
routing. This entry originally added a fourth claim - that 4-11 points of oracle headroom nonetheless
sit unclaimed - and **D-034 withdraws it.** The headroom is what a maximum over thirty noisy
organizations produces when no organization is better suited to any task. Selection variance is still
the correct description of why routing loses to doing nothing; there is simply also nothing for it to
win.

---

## D-034 — There was no prize. The oracle headroom is the maximum of a wide noisy family, not a routing opportunity

**Decision.** Withdraw the claim, made in D-033 and in every pool screen since D-021, that a
substantial routing opportunity exists over the best fixed organization. Report headroom only
against a no-interaction null from now on, and treat any bare "oracle minus best" figure as
uninterpretable.

**Why the check was run.** D-033 concluded that 4-11 accuracy points went unclaimed by every
leak-free router at every calibration size. That is a strange result to leave standing: a real,
large, systematically unreachable opportunity is a much stronger claim than a null, and it rested
entirely on a statistic - per-task maximum minus one organization - that is large whenever the
family is wide and the members fail semi-independently. Thirty organizations at roughly 85% accuracy
will contain a correct one on almost every task, whether or not any of them suits it.

**The null.** An additive logistic model of outcome on organization and task, main effects only, fit
to the observed table and used to simulate replacements
([`routing.headroom_against_no_interaction`](mas_harness/metrics/routing.py)). Organization
accuracies and task difficulties are preserved exactly; the organization-by-task interaction is
removed. That interaction is the whole content of "different organizations suit different tasks", so
the null is the hypothesis the delegation direction has been trying to reject.

**Result: observed headroom does not exceed the null in any cell.** Against the best organization on
the same tasks, so selection noise is absent from both sides:

| suite / pool | observed | null | excess | p |
|---|---:|---:|---:|---:|
| `hard366` / `strong4` | 7.00 | 6.97 | +0.02 | 0.635 |
| `hard366` / `decorrelated4` | 7.41 | 8.95 | −1.54 | 0.940 |
| `hard366` / `correlated4` | 3.70 | 6.16 | −2.46 | 0.995 |
| `crosscap240` / `strong4` | 10.00 | 9.56 | +0.44 | 0.430 |
| `crosscap240` / `decorrelated4` | 8.18 | 10.84 | −2.66 | 0.970 |
| `crosscap240` / `correlated4` | 6.25 | 7.30 | −1.05 | 0.845 |

Five of six sit below the null. The largest excess is +0.44 points at p=0.43.

**The apparent exception was the baseline, again.** Measured against the calibration-picked fixed
organization rather than the best one, `crosscap240`/`decorrelated4` reads +5.24 at p=0.010. That is
the same cell that produced the 0.735 off-dominant reproducibility (killed at 15 groups) and the
10.7-point single-agent anomaly (killed by resplitting). Its calibration draw selected an
organization scoring 0.736 on test where a single agent scored 0.843; the excess is that error. Every
positive result this project has recorded on `decorrelated4` has now failed on re-measurement three
times (D-027, D-029, here), which is itself worth remembering.

**This is the coherent explanation for everything since D-029.** No reproducible per-domain winner on
`hard366`, none on 134 SWE-bench systems, none at 15 domains on the pooled suite, a flat routing
learning curve from 57 to 398 calibration tasks, and no gain from semantic nearest-neighbour routing.
Those are five symptoms. The cause is that the outcome tables contain no organization-by-task
interaction to find.

**What is now suspect elsewhere.** The pool-headroom precondition (D-021, D-023) that decided which
pools received priced episodes computes `P(at least one member correct) - best member` over four
agents. Four is a narrower family than thirty, so the inflation is smaller, but it is the same
statistic and 8.20, 9.29 and 4.92 points have never been tested against this null. Any future use of
headroom as a gate must carry the null with it, in the same commit, as D-030 required of criteria.

**What survives.** Not a method and not an opportunity, but an apparatus and a negative: a dense
counterfactual grid of 30 organizations by 569 tasks on three pools, leak-free routing evaluation
with frozen baselines, and four independent falsification tools (permutation nulls, split-half
reproducibility with an absolute floor, shuffled-representation controls, and this no-interaction
simulation) that between them retired four positive results the project had previously believed.

**The result generalises, which is what makes it a contribution rather than a post-mortem.** Applied
to 134 independently built agent systems on 479 SWE-bench Verified instances
([`scripts/check_headroom_swebench.py`](scripts/check_headroom_swebench.py)), the observed gap
between the best single system and "at least one system solves it" is *below* the no-interaction null
at every family size from 4 to 134: 8.33 against 10.22 points at four systems, rising to 14.58
against 17.23 at all 134. The headline gap grows with family width, as a maximum over a wider noisy
family must, and the null grows faster. The excess is negative throughout, so real agent systems are
*less* complementary than independence predicts - they share base models and failure modes.

**Scope of the claim.** It concerns per-task *selection*, which is what routing needs. It is not an
argument against *aggregation*: voting over semi-independent members beats the best member under
precisely the independence this null assumes, which is why whole-pool majority vote is the one
organizational fact that reproduced everywhere (D-029). The distinction is the paper: complementarity
in the aggregation sense is real and routine, while the per-task assignment of tasks to systems that
the routing literature quotes the same statistic to motivate is not there.

---

## D-035 — The positive control fails, and the reason is the paper: agent profiles share one difficulty ordering, and voting already collects what routing would

**Decision.** Do not buy a specialist pool. Reframe the contribution from "routing does not work" to
"the statistic that motivates routing cannot detect routable structure, and where such structure
exists aggregation already collects it". The positive control D-034 needed was run for $0 on banked
data and it fails in an informative way.

**Why a positive control was required.** D-034 rests on a null that observed data never exceeds. A
null that nothing can beat is not evidence about the data; it might be a defective instrument. The
claim needed a case where it fires.

**The test.** `crosscap240` Stage A covers eight distinct agents on 238 shared tasks over four
capabilities ([`scripts/check_headroom_specialists.py`](scripts/check_headroom_specialists.py)).
Individual agents rather than organizations, because voting over four members could plausibly average
away an interaction that is present in the members. Per-capability spreads run to 0.833 - `grok43` is
0.967 on code execution and 0.133 on theory of mind - so interaction is not in doubt.

**No pool exceeds the null, including one selected to.** Best agent per capability, chosen on
calibration and scored on test: excess −2.16 (p=0.883). Shipped pools: +1.33 (p=0.330), −0.14, +2.44
(p=0.203). All eight: −0.80.

**The explanation, which is the substantive result.** For seven of the eight agents the strongest
capability is code, and for the eighth it is maths. No agent is *best* at theory of mind. The profiles
are near-monotone transformations of one difficulty ordering, with agents differing in overall
strength and in steepness rather than in what they are suited to. That is main-effect structure, which
is precisely what the additive null represents - hence the good fit and the absent excess. Genuine
crossing exists but is narrow, confined to `deepseek32` and `ring26` holding up on theory of mind
where `grok43` and `gpt5mini` collapse.

**And specialisation is self-cancelling for the oracle statistic.** An agent that collapses on a
capability creates a routing opportunity there and simultaneously leaves the union of successes on
those same tasks. For a per-task maximum the two effects roughly offset, which is why headroom is
insensitive to interaction even when interaction is large. This is a *mechanism* for D-034 rather
than a restatement of it.

**Aggregation already collects the exploitable part.** A domain router given the true capability label
of every test task and each capability's calibration-best agent - an upper bound on any learned router
over agents - against plain majority vote over the same four agents: −0.6, −7.5 and +2.5 points.
Routing does beat the best single agent in two pools of three, so the specialisation is real and
usable; it does not beat running everyone and voting, which requires no representation, no calibration
and no router.

**The qualification that keeps this honest.** The router makes one call where the vote makes four.
Giving up 1.9 accuracy points on average for a quarter of the cost is a genuine trade and a
cost-adjusted comparison may favour routing. So the supported claim is narrow: routing does not buy
accuracy over aggregation, and its case is efficiency. Any cost-adjusted claim must be measured, not
asserted, since the four pools differ in per-call price by more than an order of magnitude.

---

## D-036 — The efficiency case for routing does not survive a properly posed budget comparison, and a linear cost penalty is the wrong way to ask

**Decision.** Close the routing question. Routing buys neither accuracy (D-035) nor accuracy per
dollar. Record the convex-hull artefact as a methodological finding in its own right, because it
produced a convincing false positive twice in a row in this analysis.

**What was open.** D-035 established that a domain router with ground-truth capability labels loses
1.9 accuracy points to plain majority voting while making one call instead of four, and flagged the
cost-adjusted comparison as the strongest remaining argument for routing - to be measured, not
asserted.

**Two formulations that produced a false positive.** Sweeping `accuracy - lambda * cost` and
reporting the best gap over twelve lambdas gave +4 to +16 points at p<=0.006, with lambda and the
comparison rival both chosen on the data that scored them: the D-034 artefact, self-inflicted. Moving
that selection to a held-out half of the test tasks and averaging over 200 resplits *still* gave +2.6
to +16.6 points, positive in 86 to 100 per cent of splits. Leak-free, resplit-stable, and wrong.

**The reason, which generalises beyond this project.** Sweeping a linear penalty over a set of points
traces only the *upper convex hull* of that set. An organization that is Pareto-efficient but sits
inside the hull is unreachable by the global policy at every lambda. A routed policy mixes per
capability and can land in that concave region, so it appears to dominate the global frontier while
merely filling a gap the sweep cannot reach. Any paper comparing a mixed or routed policy against a
lambda-swept fixed baseline is exposed to this, and holding out data does not fix it, because the
artefact is in the shape of the question rather than in the selection.

**The formulation without the blind spot.** Fix a budget in dollars per task; each policy takes the
most accurate organization it can afford. This reaches the full Pareto frontier rather than its hull,
has no penalty parameter, and matches the constraint a deployer actually has. Budgets are set to the
distinct organization prices, the points at which the affordable set changes
([`scripts/measure_cost_frontier.py`](scripts/measure_cost_frontier.py)).

**Result.** At an unconstrained budget routing loses in all six pool-by-suite cells, by 0.48 to 3.15
points, positive in 2 to 29 per cent of 200 resplits. Across roughly twenty budgets per cell the
curve is negative at most points. At the tightest budget in every cell all capabilities receive the
same organization, so routing degenerates to the global policy exactly where the budget binds hardest.

**The one exception, and what it actually is.** `crosscap240`/`correlated4` at $0.000453 per task
gains +11.53 points, positive in 100% of 200 splits. The cause is that an organization's price varies
by capability, so one whose average price exceeds the budget remains affordable on the domains where
its prompts and answers are short. That is real and a legitimate use of a budget, but it is
priced-by-domain arbitrage rather than delegation, and it appears in one cell of six at one narrow
band of budgets. It does not support a routing claim.

**Cost accounting note.** Episode records show $0 for bank replays and Stage A records show $0 for
cache hits, so both would have understated deployment cost and inverted the comparison. Every call
here is repriced from its four token buckets against the run's frozen price snapshot;
`independent_majority` over k members is charged for k, and `single_expert` for the single member it
consults, its predictor reading calibration accuracy by domain rather than the current task's answers.

---

## D-037 — The headroom null was conservative; sharpened to preserve member sharing, the verdict holds

**Decision.** Keep D-034. Replace the organization-level independent null with an agent-level null
that propagates simulated answers through the real protocol function, and report the sharp version as
primary for our own data. Retire the calibration-picked headroom variant from any claim about table
structure.

**The defect.** `headroom_against_no_interaction` draws each *organization's* outcome independently
given fitted marginals, but organizations share members: `independent_majority` over {a1,a2,a3} and
over {a1,a2,a4} agree whenever a1 and a2 do. Positive correlation makes real per-task maxima smaller
than independent maxima at matched marginals, so the null's oracle is too generous and the test
under-rejects. A conservative test cannot support "there is no excess", which is what D-034 claimed.

**The repair, free because of the two-stage design.** Simulate agent correctness under
`sigma(alpha_a + beta_x)`, convert to answers, and push them through the real voting and
expert-selection logic ([`mas_harness/metrics/sharing_null.py`](mas_harness/metrics/sharing_null.py)).
One simulated answer for a1 feeds every organization containing a1, so sharing is exact. Preserved on
purpose: per-task difficulty, per-agent strength, per-agent abstention propensity, and each task's
distractor concentration — the last matters because four agents converging on one multiple-choice
distractor can outvote a correct minority, whereas open-response wrong answers are nearly all distinct.
Destroyed: any association between which agent fails and which task it fails on.

**Two validations, because a hand-rolled protocol replay is exactly the kind of thing that silently
diverges.** Replaying observed answers through the fast equivalence-class path reproduces the recorded
episodes at agreement 1.0000 in all six cells, which also certifies that the SymPy-backed equivalence
relation is transitive on this data. And a planted structure of four agents over four capabilities,
each competent at exactly one, is detected at p<0.05 with excess above 5 points, so the instrument
fires when the structure is present.

**The diagnosis was correct.** The sharp null's headroom is materially lower: on `hard366`, against the
best test organization, 6.97, 8.95 and 6.16 become 4.79, 6.25 and 3.78. Excesses move up by one to
three points across the board.

**The verdict is unchanged.** Against the best organization on test, excesses under the sharp null are
+2.20 (p=0.045), +1.16, −0.07, −0.23, −0.05 and −3.24. One cell of six under 0.05 is what the global
null predicts: at least one p<0.05 among six tests happens 26% of the time, and the Bonferroni
threshold is 0.0083. C1 now rests on a test with demonstrated power rather than on a conservative one.

**One variant retired.** Headroom against the *calibration-picked* organization conflates interaction
with selection noise. On `crosscap240`/`decorrelated4` it reads +10.55 at p=0.010 under the sharp null,
but the calibration-picked organization underperforms the best test organization there by 11.3 points —
the winner's curse of D-033, not interaction. The same cell reads −0.05 against the best test
organization. Only the latter answers a question about the structure of the outcome table, and it is
the variant D-034 quoted.

**Scope that remains.** The SWE-bench validation cannot be sharpened: those 134 systems are opaque
frameworks with no member decomposition, so it stays the conservative version and must be labelled so.
And "no detectable excess" still must not be written as "no interaction": §5.2 of `FRAMEWORK.md` shows
crossing interaction exists. The supportable statement is that the interaction present is not of a kind
a per-task maximum can detect.
