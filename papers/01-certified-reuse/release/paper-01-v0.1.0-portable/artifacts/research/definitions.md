# Formal Definitions — Living Computation

Version 0.1 · November 22, 2026

## 1. The Ten Core Concepts (LC-1 to LC-10)

| ID | Concept | Operational Definition in This Codebase |
|---|---|---|
| **LC-1** | Living computation | A stateful system executing the closed loop $\text{Observe} \to \text{Compute} \to \text{Trace} \to \text{Learn} \to \text{Constrain} \to \text{Validate} \to \text{Reuse}$ over forward-moving physical time $t$. |
| **LC-2** | Adaptive computational compression | Reducing cumulative future cost $C(P,E,K,A,t)$ by synthesizing smaller representations from historical execution traces. |
| **LC-3** | Representation validity region | A formal subset $\mathcal{V}_M \subseteq \mathcal{D}_B$ of boundary states over which a compressed representation $M$ provably produces the identical output as full evaluation. |
| **LC-4** | Computational canary | A low-cost monitor $g_M: \Delta E_t \to \{\text{SAFE}, \text{UNSAFE}, \text{UNKNOWN}\}$ attached to a `ValidityContract` (`core/canary.py`). |
| **LC-5** | Environment synthesis | Discovering and enforcing `EnvironmentPolicy` transition constraints that preserve tractable problem families. |
| **LC-6** | Persistent computational traces | Append-only `ExecutionTrace` logs (`core/trace.py`) explicitly distinguishing *materialized* snapshots from *reconstructible* delta+checkpoint traces. |
| **LC-7** | Recursive computational compression | Absorbing repeated or low-output-entropy multi-node subgraphs into reusable `LearnedRepresentation` modules. |
| **LC-8** | Dependency localization | Containing environmental perturbations at module boundaries so downstream reconsideration ratio $L_t$ stays small. |
| **LC-9** | Engineered computational asymmetry | Structuring problem instances and environments so authorized/informed participants pay systematically lower cost than uninformed participants. |
| **LC-10** | Asymmetric computational entropy | Retaining private historical witnesses/contracts that shrink internal search uncertainty while keeping external uncertainty high. |

## 2. Resource Cost Vector & Accounting Boundary

Computational cost is modeled as a 5-component physical resource vector (`core/cost_ledger.py`):

$$C(P, E, K, A, t) = (\text{steps}, \text{time}_s, \text{joules}, \text{memory}_{\text{bytes}}, \text{communication}_{\text{bytes}})$$

Every operation in a run is assigned to exactly one of five exhaustive categories:

1. `execution` ($C_{\text{exec}}$): node evaluation and input application.
2. `trace_recording` ($C_{\text{trace}}$): trace creation, serialization, and storage.
3. `learning` ($C_{\text{learning}}$): trace analysis, cone extraction, Lipschitz certification, and contract validation.
4. `guarding` ($C_{\text{guarding}}$): canary checks and post-invalidation re-anchoring.
5. `reconfiguration` ($C_{\text{reconfig}}$): routing updates or contract retirement.

Total lifecycle cost is strictly conservative:

$$C_{\text{total}}(T) = C_{\text{exec}}(T) + C_{\text{trace}}(T) + C_{\text{learning}}(T) + C_{\text{guarding}}(T) + C_{\text{reconfig}}(T)$$

## 3. Guarantee Taxonomy

Every `ValidityContract` declares one of four explicit guarantee levels (`GuaranteeLevel`):

- **Empirical**: observed accurate on tested workloads; no formal proof.
- **Distributional**: expected correctness or cost bound under a specified input distribution.
- **Restricted worst-case**: mathematically proven for *every* input inside a formally defined admissible class / validity region $\mathcal{V}_M$.
- **General worst-case**: mathematically proven for *every* valid input in the unrestricted problem domain.

## 4. Shared Quantitative Metrics

- **Reconsideration ratio**:
  $$L_t = \frac{|V_{\text{visited}, t}|}{|V|}$$
- **Cumulative savings**:
  $$S(T) = C_{\text{baseline, total}}(T) - C_{\text{adaptive, total}}(T)$$
- **Adaptation payback**:
  $$T^* = \min \{ T \ge 0 : S(T) > 0 \}$$
- **Cost of avoiding work ($R_{\text{avoid}}$)** — reported in both gross and net forms to prevent double-counting:
  - Let $C_{\text{overhead}} = C_{\text{trace}} + C_{\text{learning}} + C_{\text{guarding}} + C_{\text{reconfig}}$.
  - Gross avoidance per overhead unit:
    $$R_{\text{avoid, gross}} = \frac{C_{\text{baseline, total}} - C_{\text{adaptive, exec}}}{C_{\text{overhead}}}$$
  - Net savings per overhead unit:
    $$R_{\text{avoid, net}} = \frac{C_{\text{baseline, total}} - C_{\text{adaptive, total}}}{C_{\text{overhead}}} = R_{\text{avoid, gross}} - 1$$
