# Foundations of Temporal Science

Version 0.1.0 · November 22, 2026  
*Foundational Technical Note — Part I (§1–§3) of the Temporal Science Research Initiative.*

---

## 1. Central Research Question & Conditional Hypothesis

> **Central Question**: How does a computational system's history change the energy required to reach an equivalent future state?

> **Conditional Hypothesis**: Accumulated, validated causal knowledge can reduce the energy required for future goal-directed state transitions by enabling systems to avoid unnecessary discovery, observation, computation, communication, and intervention—*provided that acquisition, validation, maintenance, and transfer costs remain below the avoided work*.

History is not an additional mystical state variable. Its effects arise strictly through retained information, validated capabilities, physical modifications to the environment, and binding resource constraints inherited from previous transitions.

---

## 2. Formal State-Transition Model

### 2.1 Computational State
Represent a system at physical time $t$ as:

$$S_t = (K_t, E_t, A_t, B_t), \qquad S_{t+1} = F(S_t, O_t, U_t)$$

- $K_t$: retained knowledge, validated contracts, and compressed computational history.
- $E_t$: evolving environmental state and dynamics.
- $A_t$: available algorithms, actions, and transferred capabilities.
- $B_t$: physical, computational, communication, and human-time budgets.
- $O_t, U_t$: selective observations and interventions/updates.

### 2.2 Goal-Relevant Equivalence ($\sim_Q$)
Two terminal states satisfy $s_1 \sim_Q s_2$ relative to query/goal family $Q$ iff they meet identical declared outcome, distributional, or reliability specifications:
- *Deterministic example*: exact DAG output parity `|y_1 - y_2| <= 1e-12` (Milestone 01+02) or verified SAT assignment satisfaction (Exp 4, 5, 7).
- *Stochastic example*: predictive synchronization $\Pr[d(\hat{R}(t+\tau), R(t+\tau)) \le \varepsilon(\tau)] \ge 1 - \delta$ (Exp 8).
- *Counterexample to superficial equivalence*: In Exp 12 (`T4_institutional_enclosure`), internal institutional scores match 100%, yet external ground-truth reality diverges—demonstrating why $\sim_Q$ must bind to grounded external criteria.

### 2.3 Transition Energy ($E^*$) and Temporal Advantage ($TA_E$ vs $\widehat{TA}_E$)
- **Theoretical minimum transition energy**:
  $$E^*(s, [s^*]_Q) = \inf_{\pi \in \Pi_{\mathrm{valid}}} \mathbb{E}\big[E_{\mathrm{physical}}(\pi)\big]$$
- **Theoretical vs. empirical temporal advantage**:
  $$TA_E(A, B; Q) = E^*(s_B, [s^*]_Q) - E^*(s_A, [s^*]_Q), \qquad \widehat{TA}_E = E_{\mathrm{measured}, B} - E_{\mathrm{measured}, A}$$
- *Critical separation*: Living Computation v0.1–v0.3 currently reports operation counts and `modeled_proxy` joules—NOT hardware-metered $E_{\text{physical}}$ and NOT global theoretical minima $E^*$. Bridging $\widehat{TA}_E$ to hardware-metered joules is an explicit Phase 3 / Paper I priority (§19).

### 2.4 Causal Compression
A compressed representation $Z_t = f(H_t)$ preserves predictive (or stronger action-conditioned interventional) sufficiency for query family $Q$ while reducing processing.
- *Counterexample (bytes $\neq$ energy)*: In Exp 1, synchronous JSONL trace serialization (`reconstructible_delta`) cut operations by `12.7%` yet increased modeled energy by `+7.1%` due to I/O overhead; in Exp 9, retaining 60 irrelevant dimensions increased raw memory 208x and maintenance ops 196x while worsening MSE.

### 2.5 Temporal Tractability ($\mathcal{F}_t(B)$)
The budget-feasible frontier at time $t$:

$$\mathcal{F}_t(B) = \{ q : C(q \mid S_t) \le B,\; \text{required reliability achieved} \}$$

- *Strict separation from P vs NP*: Classical P and NP classify asymptotic worst-case formal language complexity. $\mathcal{F}_t(B)$ tracks which concrete workloads become solvable within finite budget $B$ for a stateful system with validated knowledge $K_t$ (e.g., Exp 4 Lewis-Aspvall Renamable-Horn & Exp 16 frontier tasks unlocked under $B = 10{,}000$ ops).

### 2.6 Computational Capital ($\mathcal{V}(K)$)
Evaluated strictly as a **two-component pair** (never summed into a single verified scalar):

$$\mathcal{V}(K) = \big(\mathrm{WND}_{\mathrm{verified}},\; \Delta V^*_{\mathrm{future}}\big)$$

- $\mathrm{WND}_{\mathrm{verified}}$: counterfactually verified realized avoidance (Exp 13).
- $\Delta V^*_{\mathrm{future}} = V^*(K \cup \{h\}, B) - V^*(K, B)$: conservative modeled option value under an explicit budget- and mutex-constrained decision model (Exp 16).
- *Counterexample to monotonic capital*: Exp 15 (high churn turns retained capabilities into `-95%` maintenance liabilities) and Exp 16 CE3 (mandatory maintenance crowds out prior feasible tasks, yielding $V_{\text{option}} = -70 < 0$).
