<!-- doc-meta
type:          living
lifecycle:     update-in-place
last-verified: 2026-08-14
evidence-base: external — 16 uploaded routing papers, author-supplied
-->

# Routing: a taxonomy of 16 papers

**Provenance.** Author-supplied comparison of 16 routing papers, added 2026-08-14. Complements
[`ROUTING_ARCHITECTURES.md`](ROUTING_ARCHITECTURES.md) (nine methods by mechanism) and
[`LITERATURE_REVIEW.md`](LITERATURE_REVIEW.md) (delegation and organization selection).

**Two readings this project takes from it, recorded 2026-08-14:**

1. **The field optimises cost, not accuracy.** Cost appears in the "primary optimization" column of
   almost every row, and the headline figures quoted are cost reductions — RouteMoA 89.8%,
   R2-Reasoner 84.46%, EvoRoute 80%, MasRouter 52%; WISERouter's entire formulation is a workload
   budget constraint. This matters because **Proposition 1 closes accuracy-routing (an interaction)
   and says nothing about cost-routing (a task main effect)**. The project's 280-pool negative is
   aimed at a channel the field mostly is not claiming. See `FRAMEWORK.md` §8.
2. **§15's proposed gap is the object this project already closed.** A persistent model of
   `P(Y | q, S, R, P, H)` is `q_θ(x, S, p)` with history; over 280 pools it gains −0.01 pp, and a
   router handed ground-truth capability labels gains +0.4 pp (D-033, D-040, D-041). Adding history
   improves the estimate of a main effect, which Proposition 1 shows cannot produce a varying argmax.

**What this document does *not* cover, and it is the gap that now matters most.** These 16 papers are
all routers. `independent_judge` — the project's one positive result — is not a router; it is an
LLM reading several answers and producing one, which belongs to the **ensembling / aggregation**
literature (Mixture-of-Agents, LLM-Blender, universal self-consistency). That literature is
**unreviewed here and in `LITERATURE_REVIEW.md`, which contains zero mentions of it.** Novelty for
D-043/D-044 cannot be assessed until it is written.

---

Yes. I went through the **16 uploaded routing papers**, and there is a much cleaner way to organize them than putting everything under one broad label of “LLM routing.”

The key distinction is **what the router is actually choosing**. The literature has evolved roughly from:

[
\text{query}\rightarrow\text{one model}
]

to

[
\text{query}\rightarrow\text{multiple experts}
]

to

[
\text{subtask/step}\rightarrow\text{model}
]

and finally to

[
\text{query}\rightarrow\text{entire MAS organization/workflow}.
]

That distinction is especially important because papers such as IRT-Router and WISERouter are fundamentally solving a different problem from MasRouter or GraphPlanner.

## 1. My recommended taxonomy

| Category                                         | Core question                                                     | Papers                                               |
| ------------------------------------------------ | ----------------------------------------------------------------- | ---------------------------------------------------- |
| **A. Single-model LLM routing**                  | “Which one LLM should answer this query?”                         | WISERouter, IRT-Router, ICL-Router, Arch-Router      |
| **B. Sparse expert / ensemble routing**          | “Which subset of models should participate?”                      | Skill-MoE, KABB, RouteMoA                            |
| **C. Multi-round / subtask routing**             | “Which model should handle each reasoning step/subtask?”          | Router-R1, R2-Reasoner                               |
| **D. Agentic / MAS workflow routing**            | “What agents, roles, models, and workflow should be constructed?” | MasRouter, GraphPlanner                              |
| **E. Experience-driven / self-adaptive routing** | “How should routing improve from previous executions?”            | Agent-as-a-Router, EvoRoute; also KABB, GraphPlanner |
| **F. Decentralized MAS routing**                 | “Can agents organize and route without a central controller?”     | AgentNet                                             |
| **G. Adjacent routing problems**                 | Tool/agent discovery, explainability, human preference            | ACE-Router, Topaz, Arch-Router                       |

The categories overlap deliberately. For example, **KABB is both expert-subset routing and historical/adaptive routing**, while **GraphPlanner is both MAS routing and history-aware routing**.

---

# 2. Category A — Classical single-model LLM routing

This is the most traditional definition of routing:

[
R(q)\rightarrow M_i.
]

The query arrives, the router predicts which model is best, **one model is called**, and the routing problem ends.

### IRT-Router

**Core idea:** represent models as test-takers and queries as test items.

IRT-Router uses Item Response Theory to explicitly model:

[
P(\text{model }m\text{ solves }q)
=================================

f(
\text{model ability},
\text{query difficulty/attributes}
).
]

It therefore gives an interpretable latent capability profile for models and difficulty profile for queries. It also uses semantic-neighbor warm-up to address new-query cold start. 

This is particularly interesting because it turns routing into a **competence estimation problem**, rather than simply learning an arbitrary classifier.

**Strength:** interpretable model competence.

**Weakness for MAS:** it models an individual LLM's ability, not interactions between agents or team performance.

---

### ICL-Router

ICL-Router attacks a closely related problem from a different direction: **how do we represent a model's capabilities so that new LLMs can be added without retraining the router?**

It evaluates a model on a relatively small collection of queries and compresses query-performance examples into **in-context vectors** representing that model's capability profile. The router then receives the model profile plus the new query and predicts whether the model can solve it. 

Conceptually:

[
\text{model profile}
====================

{(q_i,\text{performance}_{m,i})}
\rightarrow z_m,
]

then

[
P(Y=1\mid q,z_m).
]

This is more explicitly a **model representation / cold-start** paper than an online-routing paper.

---

### Arch-Router

Arch-Router is quite different.

Rather than learning:

[
q\rightarrow \text{predicted model performance},
]

it learns:

[
q\rightarrow\text{human-defined routing policy}
\rightarrow M.
]

For example:

> finance + summarization → Model A

or

> image editing → Model B.

Its Domain–Action taxonomy separates the semantic routing decision from the actual model assignment, so models can be swapped without retraining the router. 

So Arch-Router is mainly about **human preference and operational flexibility**, not learning empirical agent competence.

---

### WISERouter

WISERouter takes yet another angle.

It formulates LLM routing as a **constrained contextual multi-armed bandit**:

[
\max
\mathbb E\left[
\sum_{t=1}^{T}Y_t
\right]
]

subject to a workload-level constraint

[
\mathbb E\left[
\sum_{t=1}^{T}S_t
\right]
\leq bT.
]

The important novelty is that the budget applies to the **whole workload**, rather than imposing the same budget on every individual query. It also has offline and online variants and learns from sparse query-model observations. 

This makes WISERouter more of an **online resource-allocation/bandit paper** than a capability-representation paper.

### Comparing these four

|                        | IRT-Router            | ICL-Router                           | Arch-Router           | WISERouter             |
| ---------------------- | --------------------- | ------------------------------------ | --------------------- | ---------------------- |
| Selection              | One LLM               | One LLM                              | One LLM               | One LLM                |
| Main representation    | Ability × difficulty  | Query-performance capability vectors | Domain-action policy  | Contextual reward/cost |
| Historical performance | Offline response data | Explicit capability examples         | No                    | Yes, online possible   |
| Online adaptation      | Limited/warm-up       | Mainly new-model profiling           | Policy can be edited  | **Yes**                |
| Interpretability       | **High**              | Medium                               | **High**              | Medium                 |
| Cost objective         | Yes                   | Secondary                            | User policy dependent | **Central**            |
| New-model support      | Some                  | **Strong**                           | **Strong**            | Naturally possible     |
| MAS interactions       | No                    | No                                   | No                    | No                     |

These papers answer:

> **Which model is individually best for the query?**

They do **not** answer:

> Which models should collaborate, and how?

That is the main transition into the next group.

---

# 3. Category B — Selecting a subset of experts

Here routing becomes:

[
q\rightarrow S_q,\qquad S_q\subseteq{M_1,\ldots,M_K}.
]

This is much closer to MAS because several models may contribute to the final answer.

## Skill-MoE

Skill-MoE first infers what **skills** a particular instance requires, such as algebra or probability, and then selects models that are historically strong on those skills.

So:

[
q
\rightarrow
\text{skills}(q)
\rightarrow
{M_{i_1},...,M_{i_k}}
\rightarrow
\text{Aggregator}.
]

Unlike multi-round debate, the experts generate a single round of outputs and an aggregator combines them. It also introduces clever batching so a pool of 16 experts can be served efficiently. 

This is an important paper because the routing granularity moves from **task/domain** to **instance-level skills**.

---

## KABB

KABB is substantially more dynamic.

It combines:

* semantic/knowledge similarity,
* task-expert relationships,
* historical performance,
* time decay,
* and Thompson Sampling.

Its knowledge-distance model uses concept overlap, dependency structure, and historical effectiveness to choose the top-(k) experts. Historical evidence is continuously updated, with older observations becoming less important. 

Conceptually:

[
P(a\text{ is useful}\mid x,\mathcal H_t)
]

changes over time.

Among your uploaded papers, **KABB is one of the clearest examples of persistent performance-conditioned expert selection**.

---

## RouteMoA

RouteMoA solves a somewhat different problem: classical Mixture-of-Agents is expensive because every model is called before deciding which responses are useful.

The figure on page 2 makes the distinction particularly clear:

[
\text{Classical MoA: all models execute}
]

versus

[
\text{RouteMoA: router selects models before inference}.
]

A lightweight scorer first predicts promising models from the query; only those models execute. Later self- and cross-assessment signals refine the rankings. 

It reports very large efficiency gains in the large model-pool setting: up to **89.8% cost reduction and 63.6% latency reduction** in the uploaded version. 

### The conceptual difference

Skill-MoE says:

[
\boxed{\text{required skill}\rightarrow\text{expert}}
]

KABB says:

[
\boxed{\text{knowledge match + historical success}\rightarrow\text{expert subset}}
]

RouteMoA says:

[
\boxed{\text{predicted usefulness}\rightarrow\text{sparse MoA activation}}.
]

They all select subsets, but the scientific question is different.

---

# 4. Category C — Fine-grained reasoning / subtask routing

This is an important conceptual leap.

Rather than:

[
q\rightarrow M,
]

these papers use something closer to:

[
q
\rightarrow
(t_1,t_2,\ldots,t_n)
]

and then

[
t_j\rightarrow M_{i_j}.
]

## R2-Reasoner / Route-and-Reason

R2-Reasoner explicitly decomposes a complex reasoning task and assigns different subtasks to different-sized models.

A cheap model might solve an easy intermediate computation, whereas an expensive frontier model handles the difficult step. 

Its architecture has two major learned components:

[
\text{Task Decomposer}
]

and

[
\text{Subtask Allocator}.
]

Training combines SFT with RL/GRPO through a staged optimization procedure.

The paper reports **84.46% API cost reduction** while maintaining competitive reasoning accuracy. 

---

## Router-R1

Router-R1 is even more dynamic.

Instead of decomposing everything in advance, the routing LLM repeatedly chooses between:

[
\texttt{think}
]

and

[
\texttt{route}(M_i).
]

A response from a selected model is added to the router's context, after which it can reason again and choose another model. 

So Router-R1 models routing as a sequential policy:

[
s_t
\rightarrow
a_t
\in
{
\text{think},
\text{route}(M_1),
...,
\text{route}(M_K)
}.
]

It uses RL and combines final-answer reward, format reward, and a cost penalty.

The key distinction is:

**R2-Reasoner:** explicitly decompose → allocate subtasks.

**Router-R1:** dynamically interleave reasoning and routing.

Neither, however, has **persistent cross-task performance memory as its primary contribution**.

---

# 5. Category D — Actual MAS routing

This category is perhaps the most important conceptual boundary in the set.

A proper MAS router should not merely ask:

> Which LLM should I call?

It asks:

> **What multi-agent organization should I create for this task?**

## MasRouter — probably the foundational uploaded paper for this definition

MasRouter explicitly defines **Multi-Agent System Routing (MASR)**.

Its routing space is:

[
\mathcal S=(\mathcal M,\mathcal R,\mathcal T),
]

where:

* (\mathcal M): possible LLMs,
* (\mathcal R): possible agent roles,
* (\mathcal T): collaboration topologies/modes.

The router determines:

[
q
\rightarrow
{
\text{collaboration mode},
\text{roles},
\text{LLMs}
}.
]

The paper explicitly argues that simply extending a single-model router to MAS is insufficient, because MAS routing additionally requires collaboration-mode selection, dynamic numbers of agents, role allocation, and model assignment. 

Its cascaded design is approximately:

[
q
\xrightarrow{\text{Collaboration Determiner}}
T
\xrightarrow{\text{Role Allocator}}
R_1,\ldots,R_k
\xrightarrow{\text{LLM Router}}
M_1,\ldots,M_k.
]

This paper is **ACL 2025 Long Paper** in the uploaded version. 

---

# 6. GraphPlanner — a major step beyond MasRouter

GraphPlanner, published at **ICLR 2026**, explicitly distinguishes three generations of routers in its Table 1 and Figure 1:

[
\text{Single-round}
\rightarrow
\text{Multi-round}
\rightarrow
\boxed{\text{Agentic routing}}.
]



Instead of merely selecting a model, at every step GraphPlanner chooses a pair:

[
(a_t,m_t)
]

where

[
a_t\in
{\text{Planner, Executor, Summarizer}}
]

and (m_t) is the LLM backbone.

Thus it generates a **workflow**, rather than just making model-selection decisions.

Its other major contribution is **GARNet**, a heterogeneous graph containing relationships among:

[
\text{queries}
\leftrightarrow
\text{agents}
\leftrightarrow
\text{responses}.
]

It combines current-workflow memory with historical interaction memory, and trains the policy using PPO. 

The distinction from MasRouter is important:

| MasRouter                                   | GraphPlanner                                     |
| ------------------------------------------- | ------------------------------------------------ |
| Configures MAS through cascaded controllers | Generates sequential agentic workflow            |
| Collaboration mode + roles + models         | Role-model decisions step by step                |
| Primarily query-conditioned                 | Query + current workflow + **historical memory** |
| No central historical-memory contribution   | **Historical graph memory is central**           |
| MAS configuration                           | Agentic workflow generation                      |

GraphPlanner therefore sits substantially closer to **history-aware agent coordination**.

---

# 7. Category E — Experience-driven routing

A second major trend in these papers is moving from:

[
R(q;\theta)
]

to

[
R(q,\mathcal H_t;\theta),
]

where (\mathcal H_t) is experience accumulated from previous executions.

This is potentially more important than the particular ML algorithm.

## Agent-as-a-Router

This paper makes the argument particularly explicitly:

> routing is limited by **information deficit**, not merely router reasoning ability.

In its preliminary experiment, providing the LLM router with performance statistics improves average performance from 41.41 to 47.74, a reported **15.3% relative improvement**. 

It consequently introduces the:

[
\boxed{\text{Context}\rightarrow\text{Action}\rightarrow
\text{Feedback}\rightarrow\text{Context}}
]

or **C-A-F loop**.

For every incoming coding task:

[
c_t
\rightarrow
a_t=M_i
\rightarrow
\text{execute}
\rightarrow
\text{verify}
\rightarrow
c_{t+1}.
]

Its ACRouter therefore contains an Orchestrator, Verifier, and Memory.

Importantly, it evaluates using **cumulative regret** over a stream of tasks instead of treating every routing example independently. 

This is one of the closest papers to the general concept of a router learning from a model's **long-term execution history**.

---

## EvoRoute

EvoRoute applies a similar idea at a finer granularity inside agentic systems.

Before an agentic workflow step, it retrieves similar previous executions, identifies a **Pareto-optimal model set** over:

[
(\text{performance},\text{cost},\text{latency}),
]

and selects from that set. The result is then added back to the evolving knowledge base. 

Its pipeline is approximately:

[
\text{subtask}
\rightarrow
\text{retrieve historical experiences}
\rightarrow
\text{Pareto filter}
\rightarrow
\text{select model}.
]

It reports up to roughly **80% lower cost and 70% lower latency** on its agentic evaluations. 

The difference from Agent-as-a-Router is:

[
\text{ACRouter: task stream}\rightarrow\text{one model/task}
]

whereas

[
\text{EvoRoute: agentic workflow step}\rightarrow\text{model}.
]

---

# 8. Category F — Decentralized MAS routing

## AgentNet

AgentNet is conceptually quite different from the rest.

Most routing papers assume:

[
\text{Central Router}\rightarrow\text{Agents}.
]

AgentNet asks whether that central router is necessary at all.

Agents maintain their own local experience, dynamically specialize, and route tasks through an evolving **DAG**. Each agent contains its own execution/routing mechanisms and a RAG-based memory of successful trajectories. 

So its conceptual model is:

[
A_i
\rightarrow
A_j
\rightarrow
A_k
]

rather than:

[
R
\rightarrow
{A_i,A_j,A_k}.
]

It therefore focuses on:

[
\boxed{
\text{decentralization + dynamic topology + evolving expertise}
}
]

rather than purely predicting which model is best.

For routing research, I would consider AgentNet an **adjacent MAS coordination paper**, rather than a clean model-routing baseline.

---

# 9. Three important adjacent papers

## ACE-Router

ACE-Router's original problem is **routing among huge collections of MCP tools**, rather than primarily choosing LLM backbones.

It trains a history-aware routing agent using graph-expanded candidate sets and synthesized multi-turn trajectories. Importantly, the paper shows that the resulting routing approach can transfer from **tool routing to agent selection**. 

So I would place it under:

[
\boxed{\text{resource discovery / Agent Web routing}}
]

rather than ordinary MAS model routing.

Still, its ideas about **large candidate spaces + multi-turn history** are quite relevant.

---

## Topaz

Topaz is primarily about **explainability**.

It constructs human-readable skill profiles and routes workflow subtasks according to capability/cost trade-offs while recording the actual optimization traces. 

Thus the scientific question is not primarily:

> Can we route better?

but:

> Can a developer understand **why this model was chosen for this task at this cost?**

It is especially useful when considering interpretable agent-performance profiles.

The uploaded version is a **CHI 2026 HCXAI workshop Spotlight**, rather than a full main-conference routing paper. 

---

# 10. Full comparison of the 16 papers

This table is probably the most useful compact summary.

| Paper                  | What is routed?            | Granularity      | Main routing signal                             | Historical memory?  | Training / algorithm             | Primary optimization          |
| ---------------------- | -------------------------- | ---------------- | ----------------------------------------------- | ------------------- | -------------------------------- | ----------------------------- |
| **IRT-Router**         | LLM                        | Query            | Latent ability × query difficulty               | Limited             | IRT / neural IRT                 | Accuracy + cost               |
| **ICL-Router**         | LLM                        | Query            | Query-performance capability profile            | Static profile      | In-context vector learning       | Accuracy / generalization     |
| **Arch-Router**        | LLM                        | Query            | Domain-action preference                        | No                  | 1.5B learned router              | Human preference              |
| **WISERouter**         | LLM                        | Query            | Contextual reward/cost                          | **Online**          | Constrained contextual bandit    | **Workload budget + reward**  |
| **Skill-MoE**          | Expert subset              | Instance         | Required skills × model skills                  | Capability profiles | Symbolic / gradient-free         | Accuracy + compute            |
| **KABB**               | Expert subset              | Task             | Knowledge distance + past performance           | **Yes**             | Bayesian / Thompson sampling     | Performance + cost            |
| **RouteMoA**           | MoA model subset           | Layer/query      | Predicted model performance + posterior judging | Not persistent      | Lightweight scorer + judges      | Performance + cost + latency  |
| **Router-R1**          | Models                     | Reasoning round  | Current reasoning state                         | Within task         | RL                               | Accuracy + cost               |
| **R2-Reasoner**        | Models                     | Subtask          | Subtask difficulty                              | No central history  | SFT + GRPO                       | Accuracy + cost               |
| **MasRouter**          | MAS configuration          | Query            | Query representation                            | Not central         | Cascaded learned controllers     | MAS performance + cost        |
| **GraphPlanner**       | Role + model + workflow    | Workflow step    | Query + workflow + graph memory                 | **Yes**             | PPO + heterogeneous graph        | Performance + GPU cost        |
| **Agent-as-a-Router**  | Model                      | Task stream      | Verified execution experience                   | **Central**         | Agent + memory / bandit framing  | Cumulative regret             |
| **EvoRoute**           | Model                      | Agentic subtask  | Retrieved experience                            | **Central**         | Retrieval + Pareto selection     | Performance + cost + latency  |
| **AgentNet**           | Task between agents        | MAS execution    | Local expertise + trajectories                  | **Yes**             | RAG + evolving DAG               | Adaptability / scalability    |
| **ACE-Router**         | Tool / agent               | Interaction step | Full interaction history                        | **Yes/contextual**  | Trajectory-trained routing agent | Retrieval accuracy / scale    |
| **Topaz**              | Model for workflow subtask | Subtask          | Explicit skills + cost                          | Static              | Transparent optimization         | Explainability + cost-quality |

---

# 11. There are really four generations of routing here

Looking across all these papers, I think the literature evolution becomes quite clear.

### Generation 1 — Predict the best LLM

[
q\rightarrow M.
]

IRT-Router, ICL-Router, WISERouter, Arch-Router.

The unit being modeled is the **individual model**.

---

### Generation 2 — Recruit specialists

[
q\rightarrow{M_2,M_5,M_7}.
]

Skill-MoE, KABB, RouteMoA.

Now **specialization and complementarity** become relevant.

---

### Generation 3 — Route reasoning dynamically

[
q
\rightarrow
t_1\rightarrow M_2
\rightarrow
t_2\rightarrow M_7
\rightarrow\cdots.
]

Router-R1, R2-Reasoner, EvoRoute.

Routing becomes a **sequential decision problem**.

---

### Generation 4 — Construct an organization

[
q
\rightarrow
(\text{agents},\text{roles},\text{models},\text{topology},\text{workflow}).
]

MasRouter and especially GraphPlanner move here.

GraphPlanner's own Table 1 on page 2 essentially makes this argument: it separates **single-round**, **multi-round**, and **multi-agent** routing, with GraphPlanner distinguished by both historical memory and graph structure. 

This is the strongest conceptual taxonomy in the uploaded collection.

---

# 12. Another crucial axis: where does knowledge about agents come from?

There is also a second taxonomy that I think is even more interesting scientifically.

### Semantic knowledge

> “This looks like a math question.”

Examples:

**Arch-Router, RouteMoA.**

---

### Explicit skill/capability knowledge

> “This requires algebra and model A has high algebra ability.”

Examples:

**Skill-MoE, IRT-Router, Topaz.**

---

### Static empirical performance

> “Model A solved these evaluation questions.”

Example:

**ICL-Router.**

---

### Persistent execution history

> “Model A has repeatedly succeeded on previous tasks like this.”

Examples:

**KABB, Agent-as-a-Router, EvoRoute, GraphPlanner, AgentNet.**

This last group marks an important change:

[
\boxed{
\text{routing from what we think a model can do}
\quad\rightarrow\quad
\text{routing from what it has actually done}
}
]

Agent-as-a-Router makes this distinction particularly explicitly through its “information deficit” argument. 

---

# 13. Which papers are closest to each other?

I would group them into these direct comparison sets:

| Research question                | Papers to compare directly                                        |
| -------------------------------- | ----------------------------------------------------------------- |
| Model competence representation  | **IRT-Router ↔ ICL-Router ↔ Skill-MoE**                           |
| Online/bandit routing            | **WISERouter ↔ KABB ↔ Agent-as-a-Router**                         |
| Sparse multi-model routing       | **Skill-MoE ↔ KABB ↔ RouteMoA**                                   |
| Sequential reasoning routing     | **Router-R1 ↔ R2-Reasoner ↔ EvoRoute**                            |
| Full MAS routing                 | **MasRouter ↔ GraphPlanner**                                      |
| Experience/memory                | **KABB ↔ GraphPlanner ↔ EvoRoute ↔ Agent-as-a-Router ↔ AgentNet** |
| Interpretable routing            | **IRT-Router ↔ Topaz ↔ Arch-Router**                              |
| Open-ended agent/tool ecosystems | **ACE-Router ↔ AgentNet**                                         |

I would **not**, for example, directly compare WISERouter against MasRouter as if they were equivalent methods. Their action spaces are fundamentally different:

[
\mathcal A_{\text{WISE}}
========================

{M_1,\ldots,M_K}
]

whereas MasRouter has something closer to

[
\mathcal A_{\text{MAS}}
=======================

\mathcal T
\times
\mathcal R^k
\times
\mathcal M^k.
]

That distinction matters a lot when constructing baselines.

---

# 14. If the focus is specifically MAS routing, these are the papers I would prioritize

I would read the collection in approximately this conceptual order:

1. **MasRouter — ACL 2025:** establishes the MAS routing problem itself. 
2. **GraphPlanner — ICLR 2026:** extends routing to role/model/workflow generation with persistent graph memory. 
3. **KABB:** dynamic expert selection using knowledge and historical performance. 
4. **EvoRoute:** experience-conditioned model selection inside agentic workflows. 
5. **Agent-as-a-Router:** probably the cleanest argument for routing based on accumulated execution history. 
6. **Skill-MoE — ICML 2026:** strong capability/specialization-based alternative. 
7. **RouteMoA — ACL 2026:** strong efficiency-oriented subset-selection baseline. 
8. **AgentNet:** useful if decentralized coordination or changing expertise matters. 

The remaining single-LLM routers are extremely useful as **conceptual and experimental baselines**, but they are not solving the full MAS organization problem.

---

# 15. The most important research gap visible across this collection

A striking pattern appears across these papers.

Most methods model one of:

[
P(Y\mid q,M)
]

or

[
P(Y\mid q,{M_i})
]

or learn

[
\pi(M_t\mid q,h_t).
]

MasRouter and GraphPlanner expand the output space to an organization, but even there the literature mostly asks:

> **Given the query, which configuration should we choose?**

Much less work is explicitly trying to learn a persistent model of:

[
P(
Y
\mid
q,
\underbrace{\text{agent composition}}*{S},
\underbrace{\text{roles}}*{R},
\underbrace{\text{protocol}}*{P},
\underbrace{\text{historical organizational outcomes}}*{\mathcal H}
).
]

That is a substantially different object from simply maintaining an individual LLM capability score.

So the uploaded papers collectively show that **“history-aware model selection” itself is already quite crowded**—KABB, ACRouter, EvoRoute and GraphPlanner all use historical information in meaningful ways. But **history at the level of complete organizations, agent interactions, complementarity, and organization-conditioned task similarity** is considerably less directly covered by this set.

That distinction is, in my view, the most useful conclusion from reading these papers together.
RW