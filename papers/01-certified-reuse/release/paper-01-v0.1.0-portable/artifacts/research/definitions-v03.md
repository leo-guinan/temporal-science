# Formal Definitions v0.3 — Transferable Computation, Work Not Done, Proof of Creator & Computational Optionality (LC-19 to LC-24)

Version 0.3 · November 22, 2026  
*Extends [definitions.md](definitions.md) (LC-1..LC-10) and [definitions-v02.md](definitions-v02.md) (LC-11..LC-18), both preserved unchanged.*

---

## 1. v0.3 Central Thesis & Value Decomposition

> **The true value of a living computational system lies not only in the work it performs, but in the work it makes unnecessary and the new work it makes possible.**

Three strictly separated forms of value (never merged into a single verified total):

1. **Work performed** (*Creation Ledger*): Resources expended to create, validate, or maintain a capability.
2. **Work not done** (*Realized Avoidance Ledger*): Resources counterfactually and demonstrably avoided through reuse while preserving required outcomes.
3. **Newly possible work** (*Computational Optionality Ledger*): Previously infeasible or uneconomical actions made feasible by the capability, together with conservative modeled expected utility.

**Proof of Creator composition** (a composition of independently verifiable evidence—not a literal arithmetic identity or blockchain consensus protocol):

$$\text{Proof of Work} \;+\; \text{Proof of Work Not Done} \;+\; \text{Evidence of Expanded Capability} \;\longrightarrow\; \text{Proof of Creator}$$

**Core Economic Principle**: For workload $W$, credible baseline $B$, and living system $S$ under identical outcome-equivalence and accounting boundaries:

$$\mathrm{WND}(W, B, S) = C_B(W) - C_S(W)$$

with machine operations, physical energy, modeled energy, memory, communication, human time, and monetary costs preserved in strictly separate unit channels.

---

## 2. Extended Concepts (LC-19 through LC-24)

### LC-19 — Computationally Actionable Information
Information has computational value when its acquisition alters the expected resource cost of achieving a defined goal. Distinguish:
1. Descriptive information.
2. Predictive information.
3. Decision-relevant information.
4. Structural information that simplifies computation (e.g., polarity witness, backdoor, Lipschitz cone).
5. Information whose future reuse prevents repeated work.

For workload $\mathcal{W}$, prior knowledge $K$, and permitted algorithm portfolio $\mathcal{A}$, gross computational value of a hint/capability $h$ is:

$$V_{\mathcal{A}}(h) = C^*_{\mathcal{A}}(\mathcal{W} \mid K) - C^*_{\mathcal{A}}(\mathcal{W} \mid K, h)$$

Net value must subtract acquisition, validation, retention, and maintenance costs.

### LC-20 — Predictive Stability with Selective Adaptation
A mature living computer resists irrelevant informational noise while adapting rapidly to meaningful environmental changes. Quantified via timespace divergence $D(q_{t-1}, q_t)$, routine jitter, Jump-to-Jitter ratio, change-detection latency, model accuracy, and adaptation cost—explicitly separating useful stability from overconfidence / inappropriate resistance to change.

### LC-21 — Transferable Computation
A computation is **transferable** when its correctness and relevant resource guarantees remain valid in a destination environment $E_{\text{dst}}$ under explicitly checked translation maps $(\phi_{\text{in}}, \phi_{\text{out}})$ and applicability assumptions.

Distinguish three validity scopes:
- **Local validity**: holds at the originating execution point.
- **Temporal validity**: holds across time $t \to t'$ in the same environment.
- **Cross-environment validity**: holds across distinct institutions, schemas, or distributions $E_{\text{src}} \to E_{\text{dst}}$.

Every transferable capability carries a versioned **Transfer Certificate** declaring semantics, source assumptions, destination requirements, translation evidence, validity status (`SAFE` / `UNSAFE` / `UNKNOWN`), and full transfer + validation costs.

### LC-22 — Verified Work Not Done
A counterfactually demonstrated reduction in required resource expenditure relative to a credible, declared baseline under an explicit outcome-equivalence standard.

Verification MUST reject or qualify claims that rely on:
- Work shifted to another person or external system (hidden human time).
- Deferred computation pushed outside the accounting window.
- Hidden preprocessing, warmup, or learning costs.
- Unreported monitoring, guarding, or maintenance overhead.
- Weakened correctness, quality, or silently dropped constraints.
- Inflated or strawman baselines, duplicated claims, or expired contracts.

Three non-equivalent claim tiers (never conflated):
1. `replay_measured` — independently replayed on identical workload inputs.
2. `statistically_estimated` — sampled with explicit confidence intervals & uncertainty.
3. `mathematically_bounded` — backed by a formal `RESTRICTED_WORST_CASE` or `GENERAL_WORST_CASE` complexity bound.

### LC-23 — Proof of Creator
A content-addressed causal provenance and verification protocol linking performed contributions to validated capabilities and verified downstream consequences. Separately establishes:
1. Contribution evidence (*Execution Proof*).
2. Authenticated provenance (contributor identity + keyed/signed commitment).
3. Capability validity (*Validity Proof*).
4. Counterfactual work avoided (*Value Evidence*: WND certificates).
5. Causal involvement (explicit dependency graph edges).
6. Transfer and reuse history.
7. Invalidation and retirement events.
8. Newly enabled capabilities (separate Option Ledger).

*Critical caveats*: A cryptographic digest establishes canonical integrity and tamper detection under stated cryptographic assumptions—it does **not** by itself establish empirical truth, human authorship, causation, or legal ownership. Attribution policy is kept strictly separate from the underlying causal evidence graph.

### LC-24 — Computational Optionality
The expansion of feasible future actions enabled by a contribution or capability $h$ under budget $B$ and correctness constraints:

$$\Delta\mathcal{A} = \mathcal{A}(K \cup \{h\}, B) \setminus \mathcal{A}(K, B)$$

Feasible-set count $|\Delta\mathcal{A}|$ alone does **not** establish economic value. Under an explicit decision model $V^*$ respecting resource budgets, capacities, mutual exclusions, dependencies, and risk/uncertainty:

$$V_{\text{option}}(h) = V^*(K \cup \{h\}, B) - V^*(K, B)$$

*Accounting discipline*: Three distinct ledgers—**Creation Ledger**, **Realized Avoidance Ledger**, and **Computational Optionality Ledger**—are maintained separately. Speculative expected option value is NEVER merged with realized verified savings.
