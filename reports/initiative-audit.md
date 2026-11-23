# Phase 0 — Living Computation Repository Audit & Traceability Matrix

**Date:** November 22, 2026  
**Audited Repository:** `/Users/leoguinan/hack-personal/living-computation` (v0.1 – v0.3, read-only preserved)  
**Verified Automated Tests:** `25/25` passing (`pytest -q`, 4.50s — *automated verification, NOT independent peer review*)

---

## 1. Experiment-to-Claim-to-Paper Traceability Matrix

| Living Computation Artifact | Verified Results Location | Mapped Claims | Target Paper | Energy Tier |
|---|---|---|---|---|
| **Milestone 01+02** (1,000 nodes × 10,000 updates × 4 regimes) | `results/milestone_01_02/milestone_summary.json`, `avoidance_ledger.md` | `TS-BASE-001`, `TS-001`, `TS-002`, `TS-CERTIFIED-REUSE` | **Paper I** | `modeled_proxy_energy` |
| **Exp 1** (Trace-storage policy ablation) | `results/exp01_trace_reuse/exp01_summary.json` | `TS-BASE-001`, `TS-002` | **Paper I** | `modeled_proxy_energy` |
| **Exp 2** (Canary shock-rate phase transition) | `results/exp02_canaries/exp02_sweep.json` | `TS-001`, `TS-002` | **Paper I** | `modeled_proxy_energy` |
| **Exp 3** (Learning what to observe + dormant wake-up) | `results/exp03_observation/exp03_summary.json` | `TS-003` | **Paper I** | `modeled_proxy_energy` |
| **Exp 4** (SAT 2-SAT / Renamable-Horn / Backdoor-k) | `results/exp04_tractability/exp04_summary.json` | `TS-006`, `TS-TRANSFER-CERTIFICATE` | **Paper II** | `modeled_proxy_energy` |
| **Exp 5** (Upstream SAT enforcement & 2D phase diagram) | `results/exp05_v02_environment_synthesis/exp05_summary.json` | `TS-006`, `TS-HUMAN-CAPITAL` | **Paper II / IV** | `modeled_proxy_energy` + `simulated_human` |
| **Exp 7** (Simulated human computational capital) | `results/exp07_v02_human_capital/exp07_summary.json`, `contribution_to_savings_ledger.md` | `TS-008`, `TS-HUMAN-CAPITAL` | **Paper IV** | `modeled_proxy_energy` + `simulated_human` |
| **Exp 8** (Predictive synchronization & Pareto frontier) | `results/exp08_v02_predictive_sync/exp08_summary.json` | `TS-003`, `TS-CERTIFIED-REUSE` | **Paper I** | `modeled_proxy_energy` |
| **Exp 9** (Timespace trajectories & informational inertia) | `results/exp09_v02_timespace_inertia/exp09_summary.json` | `TS-004`, `TS-CERTIFIED-REUSE` | **Paper I** | `modeled_proxy_energy` |
| **Exp 10** (Human API stability & invalidation costs) | `results/exp10_v02_human_api/exp10_summary.json` | `TS-008`, `TS-HUMAN-CAPITAL` | **Paper IV** | `modeled_proxy_energy` + `simulated_human` |
| **Exp 11** (SHA-256 asymmetry & SAT leakage) | `results/exp11_v02_knowledge_asymmetry/exp11_summary.json` | `TS-009` | **Paper V** | `modeled_proxy_energy` |
| **Exp 12** (Transferable computation T1–T4 + certificates) | `results/exp12_v03_transfer/exp12_summary.json`, `transfer_certificates.json` | `TS-005`, `TS-TRANSFER-CERTIFICATE` | **Paper II** | `operation_counts_only` + `simulated_human` |
| **Exp 13** (WND Verifier + 8 adversarial attacks) | `results/exp13_v03_work_not_done/exp13_summary.json` | `TS-007`, `TS-WORK-NOT-DONE` | **Paper III** | `modeled_proxy_energy` |
| **Exp 14** (Proof of Creator evidence graph & Shapley) | `results/exp14_v03_proof_of_creator/exp14_summary.json` | `TS-009`, `TS-PROOF-OF-CREATOR` | **Paper V** | `operation_counts_only` |
| **Exp 15** (Compounding capital & churn boundary) | `results/exp15_v03_compounding_capital/exp15_summary.json` | `TS-007`, `TS-WORK-NOT-DONE` | **Paper III** | `operation_counts_only` |
| **Exp 16** (Computational optionality & counterexamples) | `results/exp16_v03_optionality/exp16_summary.json` | `TS-010`, `TS-PROOF-OF-CREATOR` | **Paper V** | `operation_counts_only` |
| **v0.3 End-to-End Chain** (Held-out seeds 9999 & 42424) | `results/milestone_v03_end_to_end/v03_chain_bundle.json` | `TS-010`, `TS-PROOF-OF-CREATOR` | **Paper V** | `modeled_proxy_energy` + `simulated_human` |

---

## 2. Proof Obligation & Missing Assumption Audit

| Obligation | Linked Claim | Status | Key Assumption / Gap Identified |
|---|---|---|---|
| **T1** (Lipschitz Canary Soundness) | `TS-001` | Proved under assumptions | Requires immutable exclusive cone + global Lipschitz ops |
| **T2** (Hit-Rate Payback) & **P6** (Atlas Soundness) | `TS-002` | Proved under assumptions | T2 assumes stationary trigger hit rate |
| **T3** (SAT Renamable-Horn & FPT Backdoor) | `TS-006` | Proved under assumptions | Restricted subfamilies only; does NOT address general 3-SAT |
| **P4** (Bounded-Disturbance Sync) | `TS-003` | Proved under assumptions | Requires finite $W_{\max}$; breaks down to 100% obs on Gaussian tails |
| **P5** (Non-Stationary Retirement Regret) | `TS-002` | **Partially Proved** | Online Markovian drift regret bound missing |
| **P7** (Human Advice Accounting) | `TS-008` | **Open / Conjecture** | Needs formal two-ledger Pareto break-even proof |
| **P8** (Human API Semantic Equivalence) | `TS-008` | **Open / Conjecture** | Needs formal observational equivalence algebra $\equiv_{\text{sem}}$ |
| **P9** (Observation Rate Lower Bound) | `TS-003` | **Open / Conjecture** | Needs rate-distortion lower bound on $\bar{\rho}(\varepsilon, \delta)$ |
| **P10–P16** (v0.3 Obligations) | `TS-005, TS-007, TS-009, TS-010` | Proved under assumptions | P11 relies on grounded external reality probe; P12/P13 are accounting invariants (not causation); P15 relies on SHA-256 + key custody |

---

## 3. Missing Evidence Report (Critical Gaps)

1. **Zero hardware-metered physical energy runs**: All energy numbers in v0.1–v0.3 are `modeled_proxy` (CPU time + memory/IO transfer model). No RAPL, `powermetrics`, or external watt-meter data exists yet.
2. **Zero human-subject data**: All human times in Exp 5, 7, 10, and 12 are synthetic models (`simulated_human_*_model`).
3. **Synthetic workloads only**: DAGs, SAT streams, and T1–T4 institutional environments are synthetically generated; no external industrial dataset or third-party replication has run yet.
4. **No compositional multi-claim WND verification**: Exp 13 verifies single-workload certificates; shared-baseline composition across overlapping claims is not yet implemented.
