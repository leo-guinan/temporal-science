# Formal Definitions v0.2 — Timespace, Predictive Synchronization & Human–Machine Living Computation (LC-11 to LC-18)

Version 0.2 · November 22, 2026  
*Extends [definitions.md](definitions.md) (LC-1 through LC-10 are preserved unchanged).*

---

## 1. Updated Central Research Thesis

A **living computer** is a causally ordered system that observes an evolving environment, maintains a goal-relative predictive representation, and selects actions while minimizing lifecycle resource costs subject to explicit correctness and prediction-error constraints.

$$\text{Spacetime} \xrightarrow{\text{Observation}} \text{Timespace} \xrightarrow{\text{Prediction}} \text{Action} \longrightarrow \text{Spacetime}$$

- **Spacetime**: the physical or simulated environment and its causally evolving states $R_t$.
- **Timespace**: our proposed mathematical modeling space of goal-relative informational and predictive representations $K_t$ of that environment. *(Timespace is a mathematical modeling construct, not a claim about an additional physical spacetime dimension.)*
- **Observation**: measurement processes converting selected aspects of $R_t$ into internal informational updates.
- **Memory**: retained historical information, validated contracts, and reusable computational structures.
- **Action**: interventions informed by $K_t$ that influence $R_{t+1}$.

**Primary Design Question**:
> What is the minimum lifecycle cost of keeping a useful predictive representation synchronized with an evolving environment within specified error bounds?

**Governing Research Principle**:
> A living computer should spend resources acquiring and maintaining useful information only when doing so provides sufficient expected value under its correctness and prediction requirements. For human participants, the same system should preserve previously learned interactions where appropriate and account for the cost of unnecessarily invalidating human knowledge.

---

## 2. Extended Concepts (LC-11 through LC-18)

### LC-11 — Human–Machine Living Computation
Humans participate in living computation by supplying observations, candidate witnesses, structural constraints, corrections, authorizations, and environmental interventions.

Every human (or simulated-human) contribution $h$ is modeled explicitly with six fields:
1. **Prior information**: state of $K_t$ available before $h$.
2. **Supplied content**: formal artifact (witness, structural hint, constraint, correction, or authorization) — strictly distinguishing **advice**, **witnesses**, **interactive proofs**, and **human-generated algorithmic representations**.
3. **Human cost**: explicit human time and interaction effort (`human_time_s`, interaction count) — recorded in a dedicated ledger, never silently collapsed into machine CPU steps or presented as measured human cognitive joules when simulated.
4. **Validation cost & reliability**: machine verification work and reliability rate.
5. **Machine work avoided**: verifiable reduction in subsequent machine search/recomputation.
6. **Reuse & invalidation history**: lifetime audit trail in the **Contribution-to-Savings Ledger**.

*Complexity caveat*: Human-assisted polynomial-time machine execution does **not** establish $\mathrm{P} = \mathrm{NP}$; advice and witness-assisted computation belong to separate complexity classes (e.g., $\mathrm{P/poly}$ or interactive/verified settings).

### LC-12 — Human API
A stable semantic interface mediating between human participants and evolving computational backends. Initial operations:
- `observe(query)` — request goal-relative environmental or model state.
- `intend(goal, constraints)` — declare desired outcome and mandatory constraints.
- `correct(target, evidence)` — supply a counterexample, label, or repair.
- `authorize(proposal, scope)` — approve a consequential policy, constraint relaxation, or semantic change.
- `evaluate(outcome, criteria)` — inspect correctness, cost ledger, and validity guarantees.

**Compatibility Condition**: Underlying implementations may evolve freely while preserving observable semantic equivalence for human-facing operations; any consequential semantic shift MUST be detected by a compatibility check and require explicit `authorize` acknowledgment rather than silent breakage.

### LC-13 — Human Learning Stability
Previously acquired human procedural knowledge and interaction patterns are modeled as reusable computational capital.

- **Human knowledge invalidation metric**: fraction and recovery cost of previously valid human procedures broken by a system change (measuring relearning steps, search for moved functionality, error correction, and coordination overhead).
- **Necessary vs. unnecessary retraining**: explicitly distinguish conceptual education required by a genuinely new capability from avoidable implementation retraining caused by unstable interfaces.
- **Engagement-incentive hypothesis**: treat interfaces that induce repeated checking/exploration without improving task outcomes as a testable hypothesis rather than an assumed property of every evolving UI.

### LC-14 — Time Violence *(Proposed Normative / Economic Construct)*
*Working definition*: avoidable system-induced invalidation of accumulated human computational capital, particularly when system operators retain value derived from prior human work while externalizing adaptation costs onto users or workers without adequate support or compensation.

*(Status: proposed normative/economic construct, not a physical quantity. Measured retraining costs alone do not establish deliberate exploitation; analyses must separate observed effects, technical necessity, economic incentives, and intent.)*

Measurable components:
1. Prior human work invested (`human_time_s`, prior interactions).
2. Capabilities invalidated by system change.
3. Relearning and recovery time.
4. Value of lost access or capability.
5. Adaptation support or compensation provided.
6. Asymmetric distribution of benefits vs. adaptation burdens.

### LC-15 — Informational Inertia
The incremental lifecycle cost that a retained representation $K_t$ imposes—or saves—when the environment changes, evaluated explicitly relative to a stated reference architecture (e.g., stateless recomputation or conventional incremental state estimation).

Four strictly separated components (never equating bytes, statistical complexity, mass, or energy):
1. **Physical storage cost** (`memory_bytes`, persistence I/O).
2. **Maintenance & validation cost** (`guarding`, `learning`, `reconfiguration`).
3. **Predictive usefulness** (error reduction / synchronization coverage).
4. **Future computational work avoided** (net savings $S(T)$).

### LC-16 — Predictive Timespace
The space $\mathcal{T}$ of goal-relative predictive representations $q_t = P(K_t)$ equipped with an explicitly chosen divergence or metric $D(q_{t-1}, q_t)$ measuring representation movement after an observation:
- **Jensen–Shannon divergence (JSD)** or **square-root JSD** (bounded, symmetric; $\sqrt{\text{JSD}}$ is a true metric even when supports differ).
- **Task-specific prediction distance** (e.g., $L_2$ or Wasserstein distance between predictive distributions $\hat{R}_{t+\tau}$).
- **KL divergence** (only when absolute continuity $q_t \ll q_{t-1}$ is guaranteed; explicitly noted as non-metric and potentially infinite when supports differ).

Crucial asymmetry: many routine observations may induce near-zero timespace movement ($D \approx 0$), whereas a single surprising observation during a regime shift may induce a large representation jump.

### LC-17 — Observation Transfer
The measurement channel mapping selected environmental state $R_t$ into internal representation updates $K_t$. Five distinct quantities are tracked separately (never assuming observed bits equal information gained or energy saved):
1. **Raw observations** (sensors queried / bytes acquired).
2. **Stored measurements** (retained trace/buffer bytes).
3. **Actual information gain** (reduction in predictive entropy / variance).
4. **Predictive-state movement** ($D(q_{t-1}, q_t)$ in timespace).
5. **Action change** (whether the selected control/decision action actually changed).

### LC-18 — Predictive Synchronization
Let $R_t$ be environmental state, $K_t$ be internal memory, and $\hat{R}(t+\tau) = P_\tau(K_t)$ be the system's prediction at horizon $\tau \ge 1$. For an explicit error metric $d$, target tolerance $\varepsilon(\tau) > 0$, and permitted failure probability $\delta \in [0, 1)$, **predictive synchronization** holds if and only if:

$$\Pr\!\big[\, d(\hat{R}(t+\tau),\, R(t+\tau)) \le \varepsilon(\tau) \,\big] \ge 1 - \delta$$

Mandatory reporting rules:
1. State the probability model, horizon $\tau$, monitored variables, and environmental assumptions explicitly.
2. Distinguish **empirical error coverage** from **certified (`RESTRICTED_WORST_CASE`) guarantees**.
3. **Strict synchronization claim rule**: never describe an observer as maintaining predictive synchronization unless its empirical or certified violation rate satisfies $\hat{p}_{\text{viol}} \le \delta$.
4. When a reliable bound is unavailable (e.g., assumption violation or regime shift), transition to `CanaryState.UNKNOWN` and escalate observation rather than claiming `SAFE`.
