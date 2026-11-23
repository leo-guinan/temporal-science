# TS-001 — Soundness of Lipschitz-Margin Validity Region Canaries

**Exported by**: Paper I (`01-certified-reuse`)  
**Kind**: `theorem` | **Status**: `formally_proved_under_assumptions` | **Version**: `0.1.0`

## Plain-Language Explanation
Conventional incremental computation (such as topological dirty-bit propagation with value-equality early cutoff) must still re-evaluate upstream preprocessing nodes whenever an input changes, only halting after it reaches a threshold or saturating node whose output happens not to change.

`TS-001` establishes that when the Trace-to-Contract Compiler extracts an **exclusive continuous cone** feeding a saturating/discrete gate (`THRESHOLD`, `RELU`, `CLAMP`) and propagates exact global partial Lipschitz bounds $L_b$, an $O(|B_{\text{changed}}|)$ boundary canary can mathematically certify whether the gate output is invariant *before* entering the cone—skipping the entire intermediate sub-DAG with **zero false-SAFE errors**.

## Verified Empirical Footprint (Living Computation v0.1)
- **Graph**: 1,000-node DAG (`living_milestone_dag_1000n_s42`, 2,167 edges, 120 inputs, depth 25).
- **Exactness**: `0` mismatches across `40,004` updates (4 regimes × 10,001 steps) and `0` false-SAFE events in 2,000 adversarial boundary fuzz probes.
- **Avoided Work**: 31 discovered contracts avoided `300,216` node evaluations across `14,296` SAFE hits (`localized_regime_drift`), cutting graph reconsideration ratio $L_t$ by **37.2%** (`0.0664` → `0.0414`).
- **Explicit Failure Boundary**: Under `high_entropy_shock`, soundness still holds (0 errors), but canary misses dominate and static contracts incur `-47.7%` op overhead relative to conventional incremental unless adaptive retirement is enabled.
