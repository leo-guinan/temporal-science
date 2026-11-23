# Temporal Science — Unified Glossary & Notation

Reconciles Temporal Science foundational terminology (§3) with Living Computation v0.1–v0.3 definitions (`LC-1` through `LC-24`).

| Term | Symbol / ID | Definition | Relationship to Prior Concepts |
|---|---|---|---|
| **Computational State** | $S_t = (K_t, E_t, A_t, B_t)$ | Available validated knowledge $K_t$, environment state $E_t$, capabilities/actions $A_t$, and resource budgets $B_t$. | Unifies Living Computation's $C(P, E, K, A, t)$ across forward physical time $t$. |
| **Goal-Relevant Equivalence** | $s_1 \sim_Q s_2$ | Terminal states satisfying identical outcome/distribution/reliability requirements for query family $Q$. | Generalizes exact output parity (`atol=1e-12`), SAT satisfaction, and $\varepsilon(\tau)/\delta$ sync equivalence. |
| **Transition Energy (Theoretical)** | $E^*(s, [s^*]_Q)$ | Infimum of expected physical energy over valid policies reaching $[s^*]_Q$. | Theoretical lower bound; distinct from measured implementation energy $E_{\text{measured}}$. |
| **Temporal Advantage** | $TA_E$ / $\widehat{TA}_E$ | Difference in theoretical ($TA_E$) or measured ($\widehat{TA}_E$) transition energy between systems with different histories. | Operationalizes LC-1, LC-2, LC-9 under explicit physical/modeled energy separation. |
| **Causal Compression** | $Z_t = f(H_t)$ | Representation preserving causal structure needed for prediction or intervention while reducing processing. | Connects LC-2, LC-7, and computational mechanics ($\varepsilon$-machines / causal states). |
| **Temporal Tractability** | $\mathcal{F}_t(B)$ | Budget-feasible task frontier $\{q : C(q \mid S_t) \le B,\;\text{reliability met}\}$. | Stateful workload tractability; strictly distinct from classical P vs NP language classes. |
| **Validity Region & Atlas** | $\mathcal{V}_M$, $\mathcal{V}_{\mathcal{A}}$ | Certified input region (or union of balls) where a compressed capability remains sound. | LC-3, Theorem 1, P6 (`LipschitzMarginCanary`). |
| **Computational Canary** | $g_M \to \{\text{SAFE}, \text{UNSAFE}, \text{UNKNOWN}\}$ | Low-cost runtime guard monitoring validity assumptions with explicit uncertainty escalation. | LC-4, Exp 2, Exp 3, Exp 8. |
| **Transfer Certificate** | `TS-TRANSFER-CERTIFICATE` | Versioned contract specifying translation maps $(\phi_{\text{in}}, \phi_{\text{out}})$, external probes, and validity status. | LC-21, P11, Exp 12 (T1–T4). |
| **Verified Work Not Done** | $\mathrm{WND}(W, B, S)$ | Counterfactual resource reduction $C_B(W) - C_S(W)$ under outcome equivalence & complete accounting. | LC-22, P12, Exp 13 (`REPLAY_MEASURED`, `STATISTICALLY_ESTIMATED`, `MATHEMATICALLY_BOUNDED`). |
| **Human Computational Capital** | `TS-HUMAN-CAPITAL` | Validated human hints/constraints & procedural mastery preserved across changing backends via a Human API. | LC-11..LC-14, Exp 7, Exp 10. |
| **Proof of Creator** | `TS-PROOF-OF-CREATOR` | Content-addressed causal evidence graph linking work performed, verified WND, attribution, and optionality. | LC-23, P13, P15, Exp 14. |
| **Computational Optionality** | $\Delta\mathcal{A}$, $V_{\text{option}}(h)$ | Expansion of budget-feasible actions and conservative incremental optimal portfolio utility $V^*(K\cup\{h\}, B) - V^*(K, B)$. | LC-24, P16, Exp 16 (strictly separate from realized WND). |
