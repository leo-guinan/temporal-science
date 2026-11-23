# Paper I — Certified Computational Reuse Under Environmental Change

**Module ID**: `paper-01` | **Version**: `0.1.0` | **Exported Contract**: `TS-CERTIFIED-REUSE`  
**Status**: Preprint-ready (operation counts & modeled proxy energy); **blocked for final energetic release pending hardware power metering (§19)**.

## 1. Central Claim
Previously executed computation can be safely reused within explicitly certified validity regions (`TS-001`, `TS-002`, `TS-003`), reducing cumulative operations relative to both full recomputation and strong topological incremental baselines within bounded volatility regimes while maintaining selective shift responsiveness (`TS-004`).

## 2. Verified Evidence Mapping (Living Computation v0.1–v0.2)
- **Milestone 01+02 (`1,000` nodes × `10,000` updates × 4 regimes)**:
  - `0` mismatches across `40,004` updates; `0` false-SAFE hits across `2,000` adversarial fuzz probes.
  - Surprise-trace Living engine with Multi-Anchor Validity Atlas saves **+93.5%** ops vs full recomputation and **+15.32%** ops vs optimal topological-heap early-cutoff incremental (`localized_regime_drift`, payback `t=408`, $R_{\text{avoid}}=1.68\times$, $L_t$ cut 37%).
  - Full Historical Avoidance Ledger tracks `300,216` avoided node evaluations across `31` learned contracts.
- **Exp 1 & Exp 2 Sweeps**: Trace-storage ablation (`full_materialized` `-167%` vs `surprise_driven` `+13.23%` ops / `+17.15%` modeled J) and exact shock-frequency crossover (`+24.6%` at $p=0.00$ crossing zero near $p \approx 0.11$, `-30.1%` at $p=0.60$); periodic monitors (`P=5..50`) suffer `77.6%–98.4%` error rates.
- **Exp 3 & Exp 8 (Observation & Predictive Synchronization)**: P4 certified observer achieves `0.00%` violations under a `1.85x` mid-stream shift (`-14.8%` modeled J, `5`-step `UNKNOWN` detection), while explicitly preserving Exp 3's `203` vs `59` violation trade-off and Exp 8's stationary Gaussian periodic-advantage boundary.
- **Exp 9 (Timespace Inertia)**: `living_canary_memory` achieves `6.08x` Jump-to-Jitter ratio, `19`-step shift recovery, and `98.85%` action accuracy vs `65.94%` for overconfident naive infinite memory and `196x` maintenance explosion for bloated irrelevant memory.

## 3. Formal Contributions & Open Gaps
- **Proved (`RESTRICTED_WORST_CASE`)**: Theorem 1 (`TS-001`), Theorem 2 & P6 (`TS-002`), P4 (`TS-003`).
- **Open**: P5 (online adaptive retirement regret under Markovian drift), P9 (rate-distortion observation lower bound).

## 4. Explicit Limitations & Non-Claims
Does NOT prove P = NP, universal energy reduction, or sound canaries for arbitrary discontinuous functions. All energy numbers are `modeled_proxy` pending hardware power metering.
