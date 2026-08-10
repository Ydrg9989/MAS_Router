# Literature Review: Delegation, Routing, and Organization Selection in LLM Multi-Agent Systems

## 1. Executive Summary

Recent work from 2025–2026 shows that **history-aware delegation in heterogeneous LLM multi-agent systems is already a substantial research area**.

Several ideas that initially appeared novel are now well covered by existing work:

- maintaining persistent records of agent performance;
- routing tasks to agents based on historical success;
- retrieving similar historical tasks;
- selecting complementary subsets of agents;
- dynamically selecting collaboration modes or MAS architectures;
- adapting routing policies over time;
- modeling task-specific rather than global agent competence.

The strongest recent papers relevant to our project are:

1. **KABB** — ICML 2025
2. **ReSo** — EMNLP 2025 Main
3. **AgentNet** — NeurIPS 2025
4. **MasRouter** — ACL 2025 Long
5. **RouterHGC** — ACL 2026 Findings
6. **MaAS** — ICML 2025
7. **FlexRouter** — COLM 2026
8. **Nash-CredMAS** — ACL 2026 Findings
9. **Agent Psychometrics** — COLM 2026
10. **DecoR** — ACL 2026 Long
11. **EvoRoute** — ACL 2026 Long
12. **Skill-MoE** — ICML 2026

The central conclusion from this literature is:

> **“Maintain historical agent performance and use it for task-conditioned delegation” is no longer sufficient as the main novelty of a paper.**

A potentially stronger research direction is instead to study **organization-induced task representations**:

> Rather than defining task similarity using semantics, skills, or manually specified capability dimensions, define two tasks as similar when the same **agent organizations** succeed or fail on them.

This leads naturally to a new prediction problem:

$$
q_\theta(x,S,p)
=
P\!\left(
Y=1
\mid
x,S,p
\right),
$$

where:

- \(x\) is the task,
- \(S\) is an agent subset,
- \(p\) is a collaboration or decision protocol,
- \(Y\) is the correctness of the **final collective decision**.

This formulation is substantially broader than conventional model routing.

---

## 2. High-Level Comparison

| Paper | Main Routing Unit | Uses Historical Performance? | Selects Agent Subsets? | Selects Protocol / Architecture? | Overlap with Our Original Idea |
|---|---|---:|---:|---:|---:|
| **KABB** | Task \(\rightarrow\) expert subset | Yes | Yes | No | Very high |
| **ReSo** | Subtask \(\rightarrow\) agent | Yes | Candidate search | No | Very high |
| **AgentNet** | Task/subtask \(\rightarrow\) agent network | Yes | Dynamically | Partially | High |
| **MasRouter** | Query \(\rightarrow\) MAS configuration | Not central | Yes | Yes | Very high |
| **RouterHGC** | Query \(\rightarrow\) MAS configuration | Uses configuration outcomes | Yes | Yes | Very high |
| **MaAS** | Query \(\rightarrow\) MAS architecture | Learned experience | Yes | Yes | High |
| **FlexRouter** | Query \(\rightarrow\) model subset | Yes | Yes | No | Very high |
| **Nash-CredMAS** | Context \(\rightarrow\) active panel | Yes | Yes | Interaction family fixed | High |
| **Agent Psychometrics** | Task-agent pair \(\rightarrow\) success probability | Yes | No | No | Important baseline |
| **DecoR** | Query \(\rightarrow\) model | Yes | No | No | Very high |
| **EvoRoute** | Workflow step \(\rightarrow\) model | Yes | No | Architecture mostly fixed | High |
| **Skill-MoE** | Instance \(\rightarrow\) expert subset | Skill-performance profiles | Yes | Aggregation only | High |

---

## 3. KABB — ICML 2025

### 3.1 Research Question

KABB studies the following problem:

> Given a heterogeneous pool of experts and a new task, how should a system dynamically select an appropriate subset of experts while accounting for task requirements, historical performance, complementarity, and computational cost?

This is one of the closest existing papers to our original history-aware delegation idea.

### 3.2 Task and Expert Representation

KABB does not rely only on raw semantic embeddings. Its expert-selection mechanism incorporates several signals, including:

- task difficulty;
- semantic or knowledge relevance;
- dependency complexity;
- historical effectiveness;
- expert complementarity;
- execution cost.

Conceptually, expert selection depends on a utility of the form

$$
U(S,x)
=
f\!\left(
\operatorname{Match}(S,x),
\operatorname{History}(S,x),
\operatorname{Complementarity}(S),
\operatorname{Cost}(S)
\right),
$$

where \(S\) is an expert subset and \(x\) is the current task.

### 3.3 Historical Performance

KABB maintains historical evidence about expert and team effectiveness. Thus, it already contains the core pattern

$$
\text{past performance}
\rightarrow
\text{future expert selection}.
$$

It also allows historical evidence to decay over time, preventing very old interactions from permanently dominating the router.

### 3.4 Exploration vs. Exploitation

KABB uses a Bayesian bandit formulation. This matters because a purely greedy router can create a feedback loop:

$$
\text{Agent A selected often}
\rightarrow
\text{more observations for A}
\rightarrow
\text{higher confidence in A}
\rightarrow
\text{Agent A selected even more often}.
$$

A Thompson-sampling-style mechanism permits exploration of under-observed expert combinations.

### 3.5 Novelty Conflict

KABB already covers:

- historical performance-based routing;
- task-aware expert selection;
- expert subset selection;
- competence-cost trade-offs;
- complementarity-aware team construction;
- online adaptation.

Therefore, a paper framed simply as *“we record which agents performed well in the past and use this information to select agents for similar future tasks”* would overlap heavily with KABB.

### 3.6 Remaining Gap

KABB essentially follows

$$
\text{task properties}
\rightarrow
\text{task-expert compatibility}
\rightarrow
\text{expert subset}.
$$

A potentially different direction is

$$
\text{historical organization outcomes}
\rightarrow
\text{task representation}
\rightarrow
\text{organization selection}.
$$

Instead of defining task similarity first, **organization behavior itself defines the task space**.

---

## 4. ReSo — EMNLP 2025 Main

### 4.1 Research Question

ReSo asks:

> Can a multi-agent system learn to dynamically allocate subtasks to agents based on historical performance instead of relying on manually fixed role assignments?

The system decomposes a complex task into a DAG and delegates subtasks to agents.

### 4.2 Dynamic Agent Database

Each agent contains static and dynamic information. Dynamic information includes quantities such as

$$
R(a)=\text{historical reward of agent }a,
$$

$$
C(a)=\text{execution cost of agent }a,
$$

and

$$
N(a)=\text{number of previous assignments}.
$$

This is a direct persistent competence-memory mechanism.

### 4.3 Delegation Mechanism

Conceptually, candidate suitability combines relevance and historical performance:

$$
\operatorname{Score}(a,x)
=
\operatorname{Match}(a,x)
\cdot
\operatorname{Performance}(a).
$$

A typical performance term can incorporate cost:

$$
\operatorname{Performance}(a)
=
R(a)-\beta C(a),
$$

where \(\beta\geq 0\) controls the cost penalty.

### 4.4 Novelty Conflict

ReSo already covers

$$
\text{task relevance}
+
\text{historical performance}
+
\text{cost}
+
\text{exploration}
\rightarrow
\text{agent delegation}.
$$

Therefore, *“persistent performance profiles for future task assignment”* is not enough as a contribution.

### 4.5 Remaining Difference

ReSo primarily learns

$$
\text{subtask}
\rightarrow
\text{individual agent}.
$$

Our potential formulation is richer:

$$
\text{task}
\rightarrow
(\text{agent subset},\text{coordination protocol}).
$$

---

## 5. AgentNet — NeurIPS 2025

### 5.1 Main Idea

AgentNet proposes decentralized coordination rather than a fixed centralized orchestrator. Agents can dynamically execute, forward, delegate, split tasks, and form coordination structures.

### 5.2 Task Representation

A task has a capability-requirement representation

$$
x\mapsto c_x,
$$

and each agent has a capability vector

$$
c_a.
$$

Initial routing can therefore be expressed as

$$
a^\star
=
\arg\max_{a\in\mathcal A}
\operatorname{sim}(c_x,c_a).
$$

### 5.3 Persistent Capability Updating

Agent capability representations evolve with experience. A generic exponentially weighted update is

$$
c_a^{(t+1)}
=
\beta c_a^{(t)}
+
(1-\beta)\Delta c_a^{(t+1)},
$$

where \(\beta\in[0,1]\) balances historical and recent evidence.

### 5.4 Important Assumption

AgentNet assumes that capability similarity predicts delegation quality:

$$
\operatorname{sim}(c_x,c_a)
\approx
\text{appropriateness of agent }a\text{ for task }x.
$$

Our potential question is whether capability-space similarity is actually aligned with the **best organization**.

---

## 6. MasRouter — ACL 2025 Long

### 6.1 Research Question

MasRouter formalizes **Multi-Agent System Routing (MASR)**. Instead of

$$
x\rightarrow \text{LLM},
$$

it studies

$$
x\rightarrow \text{MAS configuration}.
$$

A configuration can be represented schematically as

$$
g=(M,R,T),
$$

where \(M\) denotes model assignments, \(R\) agent roles, and \(T\) collaboration topology or mode.

### 6.2 Hierarchical Routing

MasRouter approximately decomposes routing as

$$
x
\rightarrow
\text{collaboration mode}
\rightarrow
\text{agent roles}
\rightarrow
\text{LLM assignments}.
$$

### 6.3 Optimization Objective

A generic utility-cost objective is

$$
J(g;x)
=
U(g;x)-\lambda C(g;x),
$$

where \(\lambda\geq 0\).

### 6.4 Novelty Conflict

The claim *“different tasks should use different combinations of agents and collaboration protocols”* is no longer novel by itself. The contribution must instead concern **how configuration suitability is represented and learned**.

---

## 7. RouterHGC — ACL 2026 Findings

### 7.1 Motivation

Sequential routing can suffer from cascading mistakes:

$$
\text{wrong mode}
\rightarrow
\text{wrong role set}
\rightarrow
\text{wrong model assignment}.
$$

RouterHGC instead models query and MAS configuration components jointly.

### 7.2 Heterogeneous Graph

A heterogeneous graph can be written as

$$
G_x=(V_x,E_x),
$$

with node types such as query, collaboration mode, agent role, and LLM.

### 7.3 Contrastive Supervision

The learned score should satisfy

$$
s(x,g^+)>s(x,g^-),
$$

where \(g^+\) is a better-performing configuration than \(g^-\).

### 7.4 Important Distinction

RouterHGC still fundamentally learns

$$
x\rightarrow g.
$$

Our stronger hypothesis is

$$
x
\rightarrow
\mathbf v(x)
\rightarrow
g,
$$

where \(\mathbf v(x)\) is an organization-performance fingerprint. Thus, the **task representation itself** must become the scientific object of study.

---

## 8. MaAS — ICML 2025

### 8.1 Core Motivation

MaAS argues that one static MAS architecture should not be used for every task. Its conceptual optimization problem is

$$
g_x^\star
=
\arg\max_{g\in\mathcal G}
\left[
U(x,g)-\lambda C(x,g)
\right].
$$

### 8.2 Novelty Conflict

We cannot claim *“different tasks require different MAS architectures”* as the main novelty. MaAS already makes this premise central.

The more interesting question is:

> **What information determines organizational equivalence between tasks?**

---

## 9. FlexRouter — COLM 2026

### 9.1 Main Problem

Selecting individually strong models is insufficient if they fail on the same instances.

### 9.2 Coverage Objective

FlexRouter emphasizes answer coverage:

$$
P\!\left(
\exists a\in S:Y_a=1
\right).
$$

This differs from average competence:

$$
\frac{1}{|S|}
\sum_{a\in S}P(Y_a=1).
$$

### 9.3 Connection to Our Headroom Analysis

Our MVP uses the closely related quantity

$$
\operatorname{Headroom}(S)
=
P\!\left(
\exists a\in S:Y_a=1
\right)
-
\max_{a\in S}P(Y_a=1).
$$

### 9.4 Critical Difference

FlexRouter primarily optimizes whether **at least one model is correct**. A MAS ultimately cares about whether the **collective decision is correct**:

$$
P(Y_g=1).
$$

For example, if

$$
(Y_1,Y_2,Y_3,Y_4)=(1,0,0,0),
$$

then answer coverage is successful, but majority voting is wrong. Hence,

$$
\boxed{
\text{answer coverage}
\neq
\text{organization effectiveness}
}.
$$

This distinction is central to our potential contribution.

---

## 10. Nash-CredMAS — ACL 2026 Findings

### 10.1 Research Question

Nash-CredMAS asks which agents should participate at a given interaction step.

### 10.2 The Counterfactual Problem

Historical logs normally observe only the selected organization. If only \(g_1\) is executed for task \(x\), then

$$
Y_x(g_1)
$$

is observed, whereas

$$
Y_x(g_2),Y_x(g_3),\ldots
$$

are missing.

### 10.3 Marginal Value Estimation

A conceptual marginal-value predictor is

$$
V_\phi(H_t,a)
\approx
\mathbb E\!\left[Y\mid H_t,\operatorname{include}(a)\right]
-
\mathbb E\!\left[Y\mid H_t,\operatorname{exclude}(a)\right],
$$

where \(H_t\) is the current interaction history.

### 10.4 Why This Matters for Us

Our Stage A / Stage B architecture can produce denser supervision. For the same task \(x\), we can evaluate

$$
Y_x(g_1),Y_x(g_2),\ldots,Y_x(g_K).
$$

This gives something close to a task-by-organization outcome matrix:

$$
\mathbf Y
=
\left[Y_{ik}\right]_{
\substack{i=1,\ldots,N\\k=1,\ldots,K}
}.
$$

This is substantially richer than standard observational routing logs.

---

## 11. Agent Psychometrics — COLM 2026

### 11.1 Research Question

Agent Psychometrics asks whether we can predict whether a particular agent will solve a particular task, rather than relying only on aggregate benchmark accuracy.

### 11.2 Classical IRT

In a one-parameter logistic IRT model,

$$
P(Y_{ij}=1\mid\theta_i,\beta_j)
=
\sigma(\theta_i-\beta_j),
$$

where

$$
\sigma(z)=\frac{1}{1+e^{-z}}.
$$

Here \(\theta_i\) is agent ability and \(\beta_j\) task difficulty.

### 11.3 Feature-Aware Extension

A conceptual feature-aware form is

$$
P(Y=1\mid a,x)
=
\sigma\!\left(\theta(a)-\beta(x)\right).
$$

Agent ability may be decomposed as

$$
\theta(a)
=
\theta_{\mathrm{LLM}}
+
\theta_{\mathrm{scaffold}}.
$$

### 11.4 Why It Matters for Our Evaluation

If our organization model predicts

$$
q_\theta(x,g),
$$

it must outperform a strong individual-competence strategy such as

$$
a^\star(x)
=
\arg\max_a P(Y_a=1\mid x).
$$

Otherwise, the apparent value of MAS routing may be explained primarily by task-conditioned individual competence.

---

## 12. DecoR — ACL 2026 Long

### 12.1 Main Critique

DecoR argues that semantic routers can fall into a **query memorization trap**: surface similarity does not necessarily reflect the capabilities required by a task.

### 12.2 Capability Decomposition

DecoR maps a query to

$$
p(x)
=
\{S(x),K(x),D(x)\},
$$

where \(S(x)\) denotes skills, \(K(x)\) knowledge requirements, and \(D(x)\) difficulty.

### 12.3 Historical Matching

Suppose the historical dataset is

$$
\mathcal H
=
\left\{
(x_i,m_{ij},r_{ij})
\right\}.
$$

For a new task, DecoR retrieves historically similar capability profiles and estimates which model is likely to perform well.

### 12.4 Novelty Conflict

We cannot claim *“semantic similarity is insufficient, so we use capability-aware historical matching”* as a new idea.

### 12.5 Remaining Question

DecoR still defines the relevant task dimensions explicitly. Our alternative question is:

> Do we need to define the capability ontology at all?

The organization outcomes themselves may induce latent specialization dimensions.

---

## 13. EvoRoute — ACL 2026 Long

### 13.1 Main Idea

EvoRoute accumulates execution experience and routes individual steps inside agentic workflows.

### 13.2 Historical Knowledge Base

A historical record can be represented schematically as

$$
\mathcal K
=
\left\{
(x_i,r_i,m_i,t_i,y_i,c_i,\ell_i)
\right\}_{i=1}^{N},
$$

where entries can represent task/subtask, role, selected model, tool context, success, cost, and latency.

### 13.3 Retrieval

A candidate experience set can be constructed as

$$
\mathcal K_{\mathrm{cand}}
=
\mathcal K_{\mathrm{semantic}}
\cup
\mathcal K_{\mathrm{role}}
\cup
\mathcal K_{\mathrm{tool}}.
$$

### 13.4 Novelty Conflict

The statement *“existing routers do not learn from execution history”* is no longer defensible.

### 13.5 Difference from Our Setting

EvoRoute primarily studies

$$
\text{workflow step}
\rightarrow
\text{LLM backbone},
$$

whereas our intended action space is

$$
\text{task}
\rightarrow
(\text{agent subset},\text{protocol}).
$$

---

## 14. Skill-MoE — ICML 2026

### 14.1 Main Problem

Different task instances require different skills, so Skill-MoE performs instance-level expert recruitment.

### 14.2 Skill Representation

A task is mapped to a required skill set

$$
x
\rightarrow
S_x
=
\{s_1,s_2,\ldots,s_k\}.
$$

Suppose expert \(a\) has competence vector

$$
c_a=(c_{a1},c_{a2},\ldots,c_{ad}),
$$

and task \(x\) has requirement vector

$$
r_x=(r_{x1},r_{x2},\ldots,r_{xd}).
$$

Routing can be expressed conceptually as

$$
\operatorname{Compat}(a,x)
=
f(c_a,r_x).
$$

### 14.3 Collaboration

The selected experts reason independently and an aggregator synthesizes their outputs. The design philosophy is:

> **Select the right experts rather than relying on expensive multi-round deliberation.**

### 14.4 Novelty Conflict

A paper framed as *“infer required skills and select specialized agents”* would substantially overlap with Skill-MoE.

The more interesting alternative is to allow skill-like latent dimensions to emerge from organization outcomes.

---

## 15. Five Major Research Families

### 15.1 Capability Matching

Representative papers:

- KABB;
- AgentNet;
- DecoR;
- Skill-MoE.

General formulation:

$$
x
\xrightarrow{f}
z_x
\xrightarrow{\text{matching}}
a\;\text{or}\;S.
$$

The core assumption is that task requirements can be represented explicitly enough to predict appropriate experts.

### 15.2 Historical Performance Routing

Representative papers:

- ReSo;
- AgentNet;
- KABB;
- EvoRoute;
- DecoR.

Generic formulation:

$$
\mathcal H
=
\{\text{past task},\text{chosen agent},\text{outcome}\},
$$

followed by

$$
(x_{\mathrm{new}},\mathcal H)
\rightarrow
\text{delegation decision}.
$$

This space is already crowded.

### 15.3 MAS Configuration Routing

Representative papers:

- MasRouter;
- RouterHGC;
- MaAS.

Generic formulation:

$$
x\rightarrow g_x,
$$

where \(g_x\) may specify the number of agents, roles, models, topology, protocol, and compute allocation.

### 15.4 Complementary Set Selection

Representative papers:

- FlexRouter;
- KABB;
- Skill-MoE;
- Nash-CredMAS.

These works recognize that

$$
\arg\max_S\sum_{a\in S}P(Y_a=1)
$$

is generally not equivalent to selecting the most useful team because dependencies among agent errors matter.

### 15.5 Task-Level Agent Performance Modeling

Representative work:

- Agent Psychometrics.

Core objective:

$$
P(Y=1\mid x,a).
$$

This is conceptually upstream of delegation.

---

## 16. What Is No Longer a Strong Novelty Claim?

The following claims should be avoided:

1. **“Existing MAS treats agents as equally competent.”** Too broad and no longer true.
2. **“Existing MAS does not maintain agent performance history.”** ReSo, AgentNet, KABB, and EvoRoute already do.
3. **“We select agents based on similar historical tasks.”** Already covered by several history-aware routers.
4. **“We select complementary agents rather than only the strongest ones.”** Covered by FlexRouter, KABB, Skill-MoE, and Nash-CredMAS.
5. **“Different tasks require different MAS configurations.”** Central to MasRouter, RouterHGC, and MaAS.

---

## 17. A More Promising Research Gap: Organization-Induced Task Representations

The existing literature usually begins by defining a task representation

$$
z_x=f(x),
$$

where \(z_x\) may encode semantics, skills, knowledge, difficulty, tools, roles, or manually specified capability dimensions. The router then learns

$$
z_x\rightarrow g.
$$

A different possibility is to allow **organizational behavior itself to define the task representation**.

---

## 18. Organizational Fingerprints

Let

$$
\mathcal G=\{g_1,g_2,\ldots,g_K\}
$$

be a family of candidate organizations. Define

$$
g=(S,p),
$$

where

- \(S\subseteq\mathcal A\) is an agent subset;
- \(p\in\mathcal P\) is a coordination or aggregation protocol.

For each historical task \(x\), define its organization-value vector

$$
\mathbf v(x)
=
\begin{bmatrix}
v_x(g_1)\\
v_x(g_2)\\
\vdots\\
v_x(g_K)
\end{bmatrix}
\in\mathbb R^K.
$$

For a simple correctness-only formulation,

$$
v_x(g)=Y_x(g)\in\{0,1\}.
$$

For a cost-aware formulation,

$$
v_x(g)
=
Y_x(g)-\lambda C_x(g)-\mu L_x(g),
$$

where \(C_x(g)\) is cost, \(L_x(g)\) latency, and \(\lambda,\mu\geq 0\).

---

## 19. Organizational Equivalence

Two tasks \(x_i\) and \(x_j\) are organizationally similar if their fingerprints are similar:

$$
\operatorname{sim}_{\mathrm{org}}(x_i,x_j)
=
\operatorname{sim}\!\left(
\mathbf v(x_i),\mathbf v(x_j)
\right).
$$

For cosine similarity,

$$
\operatorname{sim}_{\mathrm{org}}(x_i,x_j)
=
\frac{
\mathbf v(x_i)^\top\mathbf v(x_j)
}{
\|\mathbf v(x_i)\|_2\,\|\mathbf v(x_j)\|_2
}.
$$

Alternatively,

$$
d_{\mathrm{org}}(x_i,x_j)
=
\left\|\mathbf v(x_i)-\mathbf v(x_j)\right\|_2.
$$

The scientific hypothesis is:

> Two tasks can be organizationally equivalent even when semantically dissimilar, and semantically similar tasks can require different organizations.

Formally,

$$
\operatorname{sim}_{\mathrm{sem}}(x_i,x_j)
\not\Rightarrow
\operatorname{sim}_{\mathrm{org}}(x_i,x_j).
$$

---

## 20. Why This Is Different from Existing Work

| Existing Work | Primary Task Representation | Our Potential Difference |
|---|---|---|
| KABB | Knowledge + semantics + historical performance | Organization outcome pattern |
| ReSo | Semantic compatibility + agent reward | Full organization-response vector |
| AgentNet | Capability requirement vector | Behavior-induced latent task space |
| MasRouter | Query latent representation | Organization-conditioned task representation |
| RouterHGC | Query-configuration graph | Multi-configuration outcome geometry |
| MaAS | Query-conditioned architecture search | Learn task geometry from organization outcomes |
| FlexRouter | Individual competence + complementarity | Final collective outcome |
| Nash-CredMAS | Causal marginal contribution | Dense paired organization outcomes |
| Agent Psychometrics | Agent ability and task difficulty | Higher-order organization effects |
| DecoR | Skills + Knowledge + Difficulty | No predefined capability ontology |
| EvoRoute | Semantic/role/tool historical similarity | Organization-level instead of model-level routing |
| Skill-MoE | Explicit skill requirements | Latent specialization induced by outcomes |

---

## 21. A Second Potential Contribution: Dense Counterfactual Organization Supervision

Most routing datasets observe something like

$$
D_{\mathrm{obs}}
=
\{(x_i,g_i,Y_i)\}_{i=1}^{N}.
$$

Only one organization \(g_i\) is executed for task \(x_i\). Thus,

$$
Y_{x_i}(g_i)
$$

is observed while

$$
Y_{x_i}(g),\qquad g\neq g_i,
$$

is generally unobserved.

Our two-stage design allows substantially denser evaluation:

$$
\{Y_{x_i}(g_1),Y_{x_i}(g_2),\ldots,Y_{x_i}(g_K)\}.
$$

This approximates a dense task-organization matrix:

$$
\mathbf Y
=
\begin{bmatrix}
Y_{11} & Y_{12} & \cdots & Y_{1K}\\
Y_{21} & Y_{22} & \cdots & Y_{2K}\\
\vdots & \vdots & \ddots & \vdots\\
Y_{N1} & Y_{N2} & \cdots & Y_{NK}
\end{bmatrix}.
$$

This supervision could enable better task representations, more sample-efficient routing, better calibration, stronger OOD generalization, and more reliable organization-interaction estimates.

---

## 22. A Unified Organization-Level Prediction Problem

Instead of predicting only individual competence,

$$
P(Y=1\mid x,a),
$$

we can model

$$
\boxed{
q_\theta(x,S,p)
=
P\!\left(
Y_g=1
\mid
x,S,p
\right)
}
$$

with

$$
g=(S,p).
$$

Single-agent execution is then simply the special case

$$
|S|=1.
$$

Thus, the organization space can include:

- single expert;
- two-agent teams;
- three-agent teams;
- full teams;
- majority voting;
- independent judging;
- expert verification;
- debate;
- veto;
- information-seeking chair;
- future protocols.

---

## 23. Organization Selection

Given a learned value model,

$$
g^\star(x)
=
\arg\max_{g\in\mathcal G}q_\theta(x,g).
$$

With cost awareness,

$$
g^\star(x)
=
\arg\max_{g\in\mathcal G}
\left[q_\theta(x,g)-\lambda C(g)\right].
$$

A more general objective is

$$
g^\star(x)
=
\arg\max_{g\in\mathcal G}
\left[
q_\theta(x,g)
-
\lambda C(g)
-
\mu L(g)
-
\rho R(g)
\right],
$$

where \(C\) is cost, \(L\) latency, \(R\) a risk or robustness penalty, and \(\lambda,\mu,\rho\geq 0\).

---

## 24. Candidate Research Questions

### RQ1 — Task Representation

> **Can tasks be represented more effectively by the organizations that succeed on them than by semantic or capability-based similarity?**

### RQ2 — Organization-Level Delegation

> **Can an organization-conditioned value model predict the best agent subset and coordination protocol for unseen tasks?**

Formally,

$$
\hat g(x)
=
\arg\max_{g\in\mathcal G}q_\theta(x,g),
$$

and compare it with

$$
g_{\mathrm{oracle}}(x)
=
\arg\max_{g\in\mathcal G}Y_x(g).
$$

### RQ3 — Counterfactual Supervision

> **Does dense paired organization-level supervision enable more sample-efficient and reliable delegation than ordinary observational execution histories?**

A possible experiment varies the observed fraction

$$
r\in\{0.05,0.10,0.20,0.50,1.00\}.
$$

### RQ4 — Generalization

> **Does organization-conditioned delegation generalize to unseen tasks, domains, agent compositions, and newly introduced agents?**

Potential regimes include:

- IID task split;
- domain holdout;
- agent holdout;
- organization holdout.

### RQ5 — When Not to Collaborate

> **Can the selector identify when single-agent execution is preferable to multi-agent collaboration?**

---

## 25. Suggested Core Model

### 25.1 Task Encoder

Let

$$
z_x=f_\phi(x)
$$

be the task representation. The first version can use frozen embeddings.

### 25.2 Agent Representation

For each agent \(a\), define

$$
h_a
=
\left[
h_a^{\mathrm{global}},
h_a^{\mathrm{domain}},
h_a^{\mathrm{cost}},
h_a^{\mathrm{behavior}}
\right].
$$

Potential components include global accuracy, domain-conditioned accuracy, IRT ability, cost, error profile, and a learned behavioral embedding.

### 25.3 Set-Valued Organization Representation

A simple permutation-invariant representation is

$$
h_S
=
\sum_{a\in S}h_a.
$$

A richer pairwise model is

$$
h_S
=
\sum_{a\in S}h_a
+
\sum_{\substack{a,b\in S\\a<b}}
\psi(h_a,h_b).
$$

Include protocol representation \(h_p\):

$$
h_g
=
\phi_{\mathrm{org}}(h_S,h_p).
$$

A DeepSets version is

$$
h_S
=
\rho\!\left(
\sum_{a\in S}\phi(h_a)
\right).
$$

### 25.4 Value Model

A simple bilinear predictor is

$$
q_\theta(x,g)
=
\sigma\!\left(
z_x^\top W h_g+b
\right),
$$

where

$$
z_x\in\mathbb R^{d_x},
\qquad
h_g\in\mathbb R^{d_g},
\qquad
W\in\mathbb R^{d_x\times d_g}.
$$

It estimates

$$
q_\theta(x,g)
\approx
P(Y_g=1\mid x,g).
$$

A bilinear model is attractive as an MVP because it tests whether a learnable task-organization compatibility space exists without excessive model capacity.

---

## 26. Essential Baselines

| Baseline Family | Example | Scientific Question |
|---|---|---|
| Global competence | Globally best agent | Is task-conditioning needed? |
| Task-conditioned competence | IRT / Agent Psychometrics | Is MAS needed at all? |
| Semantic history | Embedding kNN | Is semantic similarity sufficient? |
| Capability history | DecoR-style representation | Are explicit capability dimensions sufficient? |
| Dynamic MAS routing | MasRouter / RouterHGC-style model | Is our representation better than direct query-to-configuration routing? |
| Complementarity | FlexRouter / KABB-style selection | Do organization outcomes add information beyond error diversity? |
| Historical delegation | ReSo-style score | Is our model better than persistent individual-agent histories? |
| Oracle | Best observed organization | How much headroom remains? |

---

## 27. Stronger Paper-Level Hypothesis

A stronger hypothesis than the original history-aware delegation idea is:

> **Agent organizations induce a task geometry that is distinct from semantic or capability-based similarity. Tasks are organizationally equivalent when similar agent subsets and coordination rules succeed on them. Learning this behavioral structure can enable more reliable task delegation than routing from task semantics or individual competence alone.**

This gives three falsifiable claims.

### Claim 1 — Organizational Similarity Is Distinct

$$
\operatorname{sim}_{\mathrm{sem}}
\not\approx
\operatorname{sim}_{\mathrm{org}}.
$$

Low correlation alone is not enough; organizational similarity must also be predictively useful.

### Claim 2 — Organizational Representation Improves Routing

For unseen tasks,

$$
\operatorname{Utility}\!\left(
\hat g_{\mathrm{org}}(x)
\right)
>
\operatorname{Utility}\!\left(
\hat g_{\mathrm{semantic}}(x)
\right),
$$

and ideally

$$
\operatorname{Utility}\!\left(
\hat g_{\mathrm{org}}(x)
\right)
>
\operatorname{Utility}\!\left(
\hat a_{\mathrm{competence}}(x)
\right).
$$

### Claim 3 — The Representation Generalizes

The strongest result would be robustness under distribution shift:

$$
x_{\mathrm{test}}
\sim
P_{\mathrm{OOD}}
\neq
P_{\mathrm{train}}.
$$

Examples include unseen domains, unseen task families, unseen organizations, and partially unseen agent pools.

---

## 28. Final Assessment

The original project framing

> **“Maintain long-term agent performance history and use similar-task performance to delegate future tasks.”**

is too close to recent work.

The more promising scientific question is not merely:

> **Who should solve the task?**

It is:

> **What makes two tasks equivalent from the perspective of a heterogeneous multi-agent system?**

Existing methods usually assume that task equivalence can be derived from semantics, skills, knowledge, difficulty, or tool requirements. Our potential hypothesis is different:

$$
\boxed{
\text{Task similarity should be induced by the organizations that succeed on the tasks.}
}
$$

This leads naturally to a task-by-organization learning problem:

$$
(x,g)
\longrightarrow
v_x(g),
$$

with

$$
g=(S,p).
$$

The resulting framework unifies:

- single-agent delegation;
- agent subset selection;
- coalition selection;
- protocol selection;
- cost-aware routing;
- prediction of when collaboration should be avoided.

If the empirical results support it, the contribution would therefore be less about introducing **another routing heuristic** and more about introducing a different way to conceptualize and learn **task structure in heterogeneous multi-agent systems**.
