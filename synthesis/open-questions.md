# Persistent Open Research Questions & Evidence Backlog

Version 0.1.0 · November 22, 2026  
*Tracks unresolved theoretical obligations, physical measurement gaps, and Part XI (§34) open questions.*

---

## 1. Priority Critical Evidence Gaps (Blocking Final Publication Gates)

1. **Physical Energy Metering (§19 — Blocking Paper I & Paper III strongest tier)**:
   - Current repository measures operation counts, wall-clock/CPU time, and `modeled_proxy` joules.
   - Required experiment: Run fresh recomputation, cached incremental, validity-monitored reuse, and causally compressed reuse on a dedicated hardware benchmark (Linux RAPL / macOS `powermetrics` outside sandbox / external USB-C/wall power meter) with idle baseline subtraction, fixed CPU governor, repeated trials, and confidence intervals.
2. **Real Human-Subject Validation (§8 — Blocking Paper IV behavioral claims)**:
   - Current Experiments 5, 7, 10, and 12 use explicitly labeled synthetic human-time models (`simulated_human_*_model`).
   - Required experiment: IRB-approved controlled user study comparing conventional changing workflows vs. Human API semantic interfaces, directly measuring human task time, error recovery, and conceptual comprehension.
3. **Compositional Work Not Done Verification (§7 — Paper III extension)**:
   - Prove exact non-overlapping composition rules when two WND certificates share upstream capabilities or partially overlapping baselines without double-counting.
4. **Independent Out-of-Distribution Replication (§18)**:
   - Reproduce Papers I–V benchmarks using independently authored workload generators, larger graphs ($10^4$–$10^5$ nodes), real-world SAT benchmarks (e.g., SAT Competition industrial families), and non-synthetic institutional datasets.

---

## 2. Unresolved Formal Proof Obligations

| ID | Topic | Current Status | Needed for Completion |
|---|---|---|---|
| **P5** | Online Adaptive Retirement Regret Under Non-Stationary Drift | `PARTIALLY PROVED` | Tight online competitive / regret bound for adaptive retirement under Markovian regime switching |
| **P7** | Human Advice Two-Ledger Break-Even Theorem | `OPEN / CONJECTURE` | Formal Pareto characterization of bounded advice size $|h|$, verification ops, and amortized human time across $R$ instances |
| **P8** | Semantic Interface Behavioral Equivalence ($\equiv_{\text{sem}}$) | `OPEN / CONJECTURE` | Bisimulation / observational equivalence algebra for `observe/intend/correct/authorize/evaluate` with formal exception semantics |
| **P9** | Information-Theoretic Observation Rate Lower Bounds | `OPEN / CONJECTURE` | Rate-distortion / control-under-communication lower bound on minimum average observation rate $\bar{\rho}$ for $(\varepsilon(\tau), \delta)$ synchronization |

---

## 3. Domain Backlog (§34)

- **Energy & Causal Compression**: Lower bounds on physical transition energy $E^*(s, [s^*]_Q)$ separating compute, memory hierarchy, communication, and physical actuation.
- **Memory & Temporal Tractability**: Scaling of acquisition/validation/maintenance costs under stochastic structural change; optimal retirement policies when drift is non-stationary.
- **Information & Synchronization**: Interventional causal-state compression (preserving action-conditioned distributions, not merely observational correlation).
- **Transferability**: Automatic invariant discovery across heterogeneous institutional schemas without hand-specified translation candidates.
- **Human Computational Capital**: Governance, privacy, consent, and agency rules ensuring contributors retain control over shared procedural knowledge; careful literature review separating inherited knowledge from financial/institutional privilege.
- **Proof of Creator**: Identifiability limits of causal attribution from observational evidence graphs; Sybil-resistance and independent-discovery adjudication in open networks.
- **Computational Optionality**: Multi-stage stochastic dynamic programming for option portfolios under correlated expiration and competitive obsolescence.
