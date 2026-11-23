# Prior-Work Literature & Novelty Audit

Version 0.1.0 · November 22, 2026  
*Addresses Part VIII (§23): explicitly separates borrowed foundations, unified mechanisms, novel claims, and distinguishing evidence.*

---

## 1. Discipline-by-Discipline Comparison

### A. Theoretical Computer Science
- **Established prior work**: Classical complexity ($\mathrm{P}, \mathrm{NP}, \mathrm{P/poly}$), parameterized complexity & backdoors (Williams–Gomes–Selman; Downey–Fellows), Lewis (1978) / Aspvall (1980) linear-time Renamable-Horn 2-SAT reduction, dynamic/incremental computation (Adapton, Salsa, self-adjusting computation / Acar et al.), amortized & online competitive analysis.
- **Directly borrowed**: Topological min-heap incremental propagation with early cutoff (used as our strong baseline), Lewis–Aspvall 2-SAT Horn-renamability reduction, FPT vertex-cover strong Horn-backdoor recognition, and pigeonhole $\lceil\log_2 M\rceil$ lower bound (P10).
- **Unified / extended**: Combining trace-driven sub-DAG extraction with exact global Lipschitz sensitivity propagation into disjoint **Multi-Anchor Validity Atlases** (`LipschitzMarginCanary`) that bypass intermediate DAG layers *before* conventional incremental propagation enters them; pairing SAT tractability recognition with explicit upstream enforcement, human-renegotiation ledgers, and adaptive policy retirement (Exp 5).
- **Distinguishing evidence**: Milestone 01+02 (`+15.3%` ops over optimal topological-heap early-cutoff incremental, $L_t$ cut 37%, 0 false-SAFE) and Exp 5's 2D enforcement-cost phase diagram.

### B. Information Theory, Learning & Computational Mechanics
- **Established prior work**: Rate-distortion theory (Shannon), causal-state reconstruction / $\varepsilon$-machines (Crutchfield & Shalizi), information bottleneck (Tishby), continual learning, concept drift detection (Page's CUSUM, ADWIN), forward-backward BIC/OMP feature selection.
- **Directly borrowed**: Forward-backward OMP with BIC, CUSUM drift triggers, Hellinger metric & Gaussian KL divergence.
- **Unified / extended**: Explicitly separating raw observation bytes, stored traces, KL information gain, timespace Hellinger movement, action flips, and maintenance ops under a single lifecycle accounting boundary (Exp 3, 9), plus combining residual CUSUM with round-robin omitted-sensor sentinels for dormant-sensor wake-up recovery.
- **Distinguishing evidence**: Exp 9's 6.08x Jump-to-Jitter ratio + memory-bloat counterexample (208x bytes $\to$ 196x ops & worse MSE) and Exp 3's dormant-sensor wake-up recovery.

### C. Control Theory & Physical Computation
- **Established prior work**: Kalman–Bucy filtering, event-triggered & self-triggered control (Heemels, Tabuada), POMDPs, thermodynamics of computation (Landauer, Bennett), energy-aware computing (RAPL / DVFS).
- **Directly borrowed**: Linear-Gaussian Kalman recursion, NIS ($\chi^2$) anomaly detection, bounded-disturbance invariant set propagation (P4).
- **Unified / extended**: Integrating event-triggered certified error bounds (P4) with explicit `SAFE`/`UNSAFE`/`UNKNOWN` canary escalation into the shared lifecycle energy–accuracy Pareto frontier (Exp 8), with strict refusal to claim synchronization when empirical violation rate exceeds $\delta$.
- **Honest gap**: Hardware-metered physical energy (RAPL / Apple Silicon `powermetrics` / external power meter) is NOT yet executed; all energy values in v0.1–v0.3 remain `modeled_proxy`.

### D. Scientific Infrastructure & Provenance
- **Established prior work**: Research Objects & **RO-Crate**, FAIR principles, Nanopublications, W3C PROV, Nix/Bazel reproducible builds, Lean/Coq formal proof assistants, content-addressed Merkle DAGs (Git, IPFS), Shapley value attribution in cooperative game theory.
- **Directly borrowed**: Canonical JSON + SHA-256 Merkle commitments, HMAC-SHA256 provenance tags, Shapley cooperative value formula, RO-Crate metadata structure.
- **Unified / extended**: **Verifiable Work Not Done Certificates** (Exp 13) with 3 non-equivalent verification tiers and 8-class adversarial rejection, linked via content-addressed causal evidence graphs to **Computational Optionality Ledgers** (Exp 16) and CRR executable claim contracts with automated downstream impact analysis.
- **Distinguishing evidence**: Exp 13's verification-economics proof (full replay = 9.3x saved work vs 612 ops formal-bound certification) and Exp 14's 5-scenario attribution/tamper audit.

### E. Human Capital & Institutional Research
- **Established prior work**: Human capital theory (Becker), organizational learning & tacit knowledge (Polanyi, Nonaka), HCI learnability & UI churn studies, collective intelligence, sociology of science.
- **Directly borrowed**: Framing learned human procedures as durable capital; conceptual vs. procedural training distinction.
- **Unified / extended**: Operationalizing a stable semantic **Human API** (`observe`, `intend`, `correct`, `authorize`, `evaluate`) with automated compatibility checking and strictly unit-separated `human_time_s` ledgers (Exp 7, 10, 12).
- **Honest gap**: All v0.2–v0.3 human measurements use synthetic agent models (`simulated_human_*_model`); zero real human-subject experiments have been run yet. No behavioral or psychological claims may be made without IRB-approved human studies.

---

## 2. Novelty Claim Audit Summary

| Claimed Contribution | Prior Foundation | Proposed Unification / Novel Angle | Status of Evidence |
|---|---|---|---|
| **Paper I**: Multi-Anchor Lipschitz Validity Atlas + adaptive retirement | Incremental computation + interval/Lipschitz analysis | Trace-synthesized disjoint validity balls bypassing intermediate DAG nodes with strict 5D lifecycle accounting | Verified in Python simulation; **hardware energy pending** |
| **Paper II**: P11 Transfer Certificates + T4 Institutional Enclosure probe | Domain adaptation + formal refinement/commutation | Operational transfer canaries separating internal schema consistency from external reality validity + selective module relearning | Verified on synthetic T1–T4 institutions; **held-out external domains pending** |
| **Paper III**: Tiered Work Not Done Certificates + verification economics | Counterfactual benchmarking + formal bounds | Anti-fraud 8-class WND verifier + explicit quantification of replay vs math-bound verification cost crossover | Verified on DAG + SAT; **compositional multi-claim WND & hardware metering pending** |
| **Paper IV**: Human API + Contribution-to-Savings Ledger | API wrappers + HCI + human capital economics | Semantic compatibility canary preventing silent semantic drift (CE-A) + explicit two-ledger accounting of human vs machine work | **Simulated only**; real human study required before empirical behavioral claims |
| **Paper V**: Proof of Creator + Computational Optionality | Merkle DAGs + Shapley values + real options / knapsack | Separating Creation, Realized WND, and Constrained Optionality ledgers on a single tamper-evident causal evidence graph | Verified end-to-end on held-out seeds; **external multi-party deployment pending** |
