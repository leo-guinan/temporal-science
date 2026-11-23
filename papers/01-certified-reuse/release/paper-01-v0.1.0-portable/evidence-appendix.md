# Auto-Generated Evidence Appendix — Certified Computational Reuse Under Environmental Change

- **Paper ID**: `paper-01` | **Version**: `0.1.0` | **Exported Contract**: `TS-CERTIFIED-REUSE`
- **Build Fingerprint (SHA-256)**: `7f6c78d9e7ad40c208d9b8b7172f79bdd53e94c9c2e98b089d7ede620bb75a77`
- **Pinned Artifacts Verified**: `42` files

## 1. Tiered Release Gate Status

| Release Tier | Ready? | Scope / Blockers |
|---|---|---|
| `technical_report` | `True` | Methods, formal proofs under stated assumptions, and preliminary operation/modeled-energy results. |
| `scoped_preprint` | `True` | Scoped strictly to operation-count savings, 0-false-SAFE soundness, and modeled_proxy energy; excludes hardware physical-energy claims. |
| `energy_focused_paper` | `False` | True wall-plug AC / discrete SSD-rail energy metering and cross-architecture (Intel/AMD RAPL) independent replication remain required (§19). Note: exp_hw02-04 (AC-powered Apple M3 Max IOReport whole-SoC) now establish full-lifecycle whole-SoC energy savings and preregistered prospective predictability across synthetic DAGs (K>=3), 117 stdlib AST modules, and 71 _pytest typechecked modules (exp_hw04 5-term prospective R^2=0.9997 proc / 0.9610 SoC). |
| `independently_validated_release` | `False` | Independent external replication on non-synthetic workloads and formal P5/P9 proof review. |

## 2. Claim Inventory & Evidence Tiers

| Claim ID | Version | Kind | Status | Energy Tier |
|---|---|---|---|---|
| `TS-BASE-001` | `1.0.0` | `definition` | `formally_proved_under_assumptions` | `modeled_proxy_energy` |
| `TS-001` | `0.1.0` | `theorem` | `formally_proved_under_assumptions` | `modeled_proxy_energy` |
| `TS-002` | `0.1.0` | `theorem` | `formally_proved_under_assumptions` | `modeled_proxy_energy` |
| `TS-003` | `0.1.0` | `theorem` | `formally_proved_under_assumptions` | `modeled_proxy_energy` |
| `TS-004` | `0.1.0` | `empirical_finding` | `empirically_supported` | `modeled_proxy_energy` |
| `TS-CERTIFIED-REUSE` | `0.1.0` | `theorem` | `partially_supported` | `modeled_proxy_energy` |

## 3. Assumptions, Counterexamples & Limitations

### `TS-BASE-001` — Every computational system's lifecycle resource expenditure is measured as a 5-dimensional vector (steps, time_s, joules, memory_bytes, communication_bytes) partitioned exhaustively across execution, trace_recording, learning, guarding, and reconfiguration, with physical energy, modeled proxy energy, human time, and monetary projections maintained in strictly separate unit ledgers.
- **Assumptions**:
  - All system operations are instrumented under a shared accounting boundary.
  - Modeled energy is explicitly tagged `modeled_proxy` whenever hardware counters are absent.
  - Unlike physical and human units are never summed without an explicit conversion model.
- **Documented Counterexamples & Failure Boundaries**:
  - Exp 1 synchronous JSONL trace serialization flips modeled energy negative (-7.1%) while cutting ops (+12.7%), proving steps and energy must stay separate.
- **Limitations**:
  - Proxy energy model does not substitute for hardware RAPL/SMC or external power metering.

### `TS-001` — For a deterministic topologically ordered computational DAG G and an exclusive globally Lipschitz-continuous sub-DAG cone I feeding a saturating or discrete target node v in {THRESHOLD, RELU, CLAMP}, if boundary drift satisfies sum_{b in B} L_b * |u_b - u0_b| + eps_fp < margin(p(u0)), then skipping evaluation of all nodes in I U {v} produces an output observationally identical to full DAG evaluation (RESTRICTED_WORST_CASE guarantee, zero false-SAFE errors).
- **Assumptions**:
  - Target DAG is deterministic and topologically ordered with immutable internal cone structure.
  - Every internal node in cone I belongs to LIPSCHITZ_CONTINUOUS_OPS with exact partial bounds.
  - Exclusive ownership holds: no node outside I U {v} reads any node in I.
  - IEEE-754 safety margin eps_fp strictly dominates floating-point rounding error.
- **Documented Counterexamples & Failure Boundaries**:
  - High-entropy shock regime (Exp 1+2): soundness holds (0 errors) but hit rate collapses, causing -47.7% op overhead without adaptive retirement.
  - Periodically sampled canaries (Exp 2, P=5..50): lack formal soundness and suffer 77.6%-98.4% output mismatch rates.
- **Limitations**:
  - Applies only to continuous Lipschitz cones feeding flat/saturated target gates, not arbitrary discontinuous DAGs.
  - Energy savings are currently modeled via CPU-time/memory proxy rather than hardware power metering.

### `TS-002` — The union of K certified global-Lipschitz validity balls (Multi-Anchor Validity Atlas, P6) preserves exact observational equivalence on every input falling inside any ball, and achieves positive net operation savings over conventional incremental computation iff empirical hit rate h exceeds h_min = (c_guard + c_reanchor) / (k_eff + c_reanchor) (Theorem 2).
- **Assumptions**:
  - Global Lipschitz vector L holds across all cached anchors (inherited from TS-001).
  - Stationary trigger statistics for exact Theorem 2 break-even bound; online drift regret (P5) remains open.
- **Documented Counterexamples & Failure Boundaries**:
  - Exp 2 shock-rate sweep: static contracts flip net-negative above shock probability p ~ 0.11 (-30.05% at p=0.60).
  - Exp 1 full_materialized traces: -167% ops vs incremental (never pays back).
  - Milestone recurring_states: combinatorial boundary mixing yields -3.34% ops even with Multi-Anchor Atlas.
- **Limitations**:
  - Non-stationary adaptive-retirement regret bound (P5) is only partially proved.
  - Synchronous disk JSONL tracing offsets modeled energy savings (-2.3% to -7.1%) despite +14-15% op savings.

### `TS-003` — For contractive dynamics R_{t+1} = phi * R_t + w_t with |phi| < 1, bounded disturbance |w_t| <= W_max, and bounded measurement noise |eta_t| <= eta_max, an adaptive observer triggering observation whenever E_cert(t, tau) > eps(tau) guarantees 0% lookahead bound violations when feasible, and detects broken W_max assumptions via CanaryState.UNKNOWN escalation.
- **Assumptions**:
  - Known contraction coefficient |phi| < 1 and bounded disturbance |w_t| <= W_max.
  - Feasibility condition: |phi|^tau * eta_max + W_max * (1 - |phi|^tau)/(1 - |phi|) <= eps(tau).
- **Documented Counterexamples & Failure Boundaries**:
  - Exp 8 stationary linear-Gaussian regime: tuned periodic_kalman_p3 (33.4% obs, 1.15 J, 3.72% viol) outperforms adaptive_kalman_uncertainty (78.1% obs, 2.53 J, 1.42% viol).
  - Exp 8 unbounded Gaussian noise: P4 certified observer degrades to 100% continuous observation.
  - Exp 8 super-critical 2.4x shift: even continuous observation suffers 20.29% violations (irreducible P9 predictability floor).
  - Exp 3 adaptive observer: 203 safety violations & 0.2700 post-MSE vs 59 violations & 0.0222 MSE for observe-all.
- **Limitations**:
  - Information-theoretic observation lower bound (P9) remains open.
  - Physical sensor energy is modeled rather than hardware-metered.

### `TS-004` — Combining mature sufficient Bayesian memory with a residual-surprise precision-retirement canary reduces routine timespace movement (Hellinger metric D_H = 0.043, 4.2x quieter than sliding-window baselines) while achieving rapid adaptation (19 steps, 6.08x Jump-to-Jitter ratio) and 98.85% action accuracy across structural regime shifts.
- **Assumptions**:
  - Piece-wise stationary linear-Gaussian observation model with abrupt regime shifts.
  - Known relevant feature subset for mature sufficient memory.
- **Documented Counterexamples & Failure Boundaries**:
  - Naive infinite memory (overconfident inertia): fails to adapt after shifts (65.94% action accuracy, Adapt=None).
  - Bloated irrelevant memory (bytes != sufficiency): 208x raw memory bytes explodes maintenance ops 196x while worsening MSE.
- **Limitations**:
  - Empirical simulation result; formal competitive regret bounds under continuous drift remain open.

### `TS-CERTIFIED-REUSE` — Previously executed computation can be safely reused within explicitly verified validity regions (Lipschitz cones, Multi-Anchor Validity Atlases, and bounded-disturbance P4 sync bounds), reducing cumulative operations relative to full recomputation and strong conventional incremental baselines within characterized volatility regimes.
- **Assumptions**:
  - Inherits all assumptions of TS-BASE-001, TS-001, TS-002, TS-003, and TS-004.
  - Energy savings claims remain scoped to operation counts and modeled_proxy energy until hardware metering is executed.
- **Documented Counterexamples & Failure Boundaries**:
  - High-entropy shocks, recurring combinatorial boundaries, synchronous disk JSONL I/O, stationary Gaussian Kalman optimality of periodic sensing, and overconfident memory.
- **Limitations**:
  - Marked partially_supported pending physical hardware energy metering (RAPL/powermetrics) and P5/P9 proofs.
  - Does not claim P = NP, universal energy savings, or sound canaries for arbitrary environments.
