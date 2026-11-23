# Certified Computational Reuse Under Environmental Change

**Paper ID:** `paper-01` · **Version:** `0.1.0` · **Release Tier:** `scoped_preprint`  
**Initiative:** Temporal Science (`Living Computation` experimental program)  
**Exported Contract:** `TS-CERTIFIED-REUSE` (`v0.1.0`)  
**Claims Covered:** `TS-BASE-001`, `TS-001`, `TS-002`, `TS-003`, `TS-004`, `TS-CERTIFIED-REUSE`  
**Date:** November 22, 2026

> **Scope & Evidence Notice (`scoped_preprint` tier).**  
> This preprint's core exported claims (`TS-001`–`TS-004`) are scoped to **exact operation-count savings**, **certified soundness (`0` false-SAFE errors under stated premises)**, **bounded predictive synchronization**, and **`modeled_proxy` energy** derived from a deterministic five-dimensional resource ledger. Section 5.6 adds an initial **Apple M3 Max physical energy validation extension (`exp_hw01`–`exp_hw04`)** using per-process PMU (`proc_pid_rusage` `ri_energy_nj`) and whole-SoC internal accumulators (`libIOReport.dylib` `CPU + GPU + ANE + DRAM0 + DCS0 + AMCC0`) across both the synthetic DAG and two independently sourced real-code workloads (`117` Python stdlib modules and `71` `_pytest` modules). Those SoC accumulators are **not AC wall-plug or discrete SSD-rail measurements**, and cross-architecture (Intel/AMD RAPL) replication and uncontrolled historical Git commit evaluations remain open; accordingly, both the `energy_focused_paper` and `independently_validated_release` tiers remain formally **blocked**.

---

## Abstract

Algorithms are traditionally analyzed as isolated functions operating on fresh inputs, yet real computational systems repeatedly solve related instances over evolving environments. Incremental computation and caching reuse past work, but they typically lack formal validity regions, cheap drift detection, or complete lifecycle accounting of trace storage, maintenance, and retirement costs.

We introduce **certified computational reuse**: a framework in which historical execution traces are compiled into reusable local contracts guarded by exact, sound **computational canaries** with three-valued semantics (`SAFE`, `UNSAFE`, `UNKNOWN`). We prove three conditional results: (1) **Soundness (Theorem 1 / P6)**: for pure DAG subgraphs with exclusive ownership and verified interface equivalence, a `SAFE` canary verdict guarantees exact output equivalence (`0` false-SAFE errors); (2) **Amortized Payback (Theorem 2)**: reuse reduces net cumulative lifecycle cost if and only if avoided recomputation exceeds compilation, canary verification, storage, and fallback overhead, giving a closed-form break-even horizon $T^*$ and shock-rate crossover; and (3) **Synchronized Predictive Feasibility (P4)**: under bounded additive disturbances, an adaptive interval-bound observer maintains bounded prediction error strictly within tolerance while skipping redundant observations and detecting unmodeled regime shifts via `UNKNOWN`.

Across a `1,000`-node computational DAG evaluated over `40,004` updates in four environmental regimes and five targeted ablations, certified reuse achieves **`0` output mismatches** and **`0` false-SAFE errors** across `2,000+` adversarial fuzz probes. Under localized regime drift, surprise-driven trace compilation reduces total operations by **93.63%** relative to full recomputation and **15.32%** relative to a strong dirty-propagation incremental baseline (payback $T^* = 408$ steps). Critically, we also map where certified reuse **fails**: synchronous disk trace logging flips modeled energy negative (`-6.60%` to `-10.32%`) even while operation counts stay positive; full trace materialization inflates cost by `+167%`; high-entropy shocks (`p > 0.12`) erase savings unless adaptive contract retirement bounds overhead to `-5.48%`; periodic canaries fail silently (`77.6%–98.4%` error); and on stationary linear-Gaussian dynamics, simple periodic polling (`P = 3`) outperforms adaptive Kalman uncertainty sampling. All code, pinned artifacts, and an offline clean-environment reproduction bundle accompany this preprint.

---

## 1. Introduction

### 1.1 Motivation

In classical computational complexity, the cost of computing $f(x_t)$ at step $t$ is treated as a property of the function $f$ and the current input $x_t$. In persistent systems—physical controllers, streaming analytics pipelines, constraint solvers, and autonomous agents—the system rarely begins from scratch. It operates along a causal trajectory $x_1, x_2, \dots, x_t$ drawn from an environment that exhibits partial stability, recurring regimes, and occasional abrupt shifts.

This raises a concrete operational question:

> **When does retaining, compressing, and validating computational history strictly reduce total lifecycle computational cost compared to a strong stateless or incremental baseline—once every overhead of observation, storage, verification, and fallback is counted honestly?**

The honest answer is **conditionally, not universally**. Naive caching produces silent errors when hidden assumptions drift; naive trace recording burns more storage and I/O than it saves; and naive retention of stale models degrades performance when regimes shift abruptly.

### 1.2 Contributions

This paper makes four bounded contributions:

1. **Five-Dimensional Complete Lifecycle Accounting (`TS-BASE-001`).** We formalize a strict resource ledger separating exact computation operations, observation cost, communication cost, storage/maintenance cost, and explicit `modeled_proxy` energy, with mandatory separation between operation counts, modeled proxy energy, and unavailable physical hardware energy.
2. **Trace-to-Contract Compilation with Exact Canaries (`TS-001`, Theorems 1–2 / P6).** We construct a Trace-to-Contract compiler and Multi-Anchor Validity Atlas guarded by exact boundary canaries (`SAFE` / `UNSAFE` / `UNKNOWN`), proving zero false-SAFE error under pure exclusive-ownership DAGs and deriving exact break-even conditions.
3. **Adaptive Observation, Predictive Synchronization, and Timespace Inertia (`TS-002`, `TS-003` / P4, `TS-004`).** We extend certified reuse from DAG execution to sensor observation and predictive state maintenance, demonstrating `75.95%` modeled energy savings on drifting sensor networks, `0.00%` violation bounded synchronization under `1.85x` regime shifts (P4), and `6.08x` Jump/Jitter separation under canary-gated memory decay.
4. **Explicit Failure Boundaries & Self-Contained Reproduction.** We publish six verified negative/boundary results—cases where certified reuse loses to simpler baselines or turns negative—alongside a standalone `.tar.gz` reproduction bundle verified in an isolated clean environment.

### 1.3 Explicit Non-Claims

To prevent over-interpretation, this paper explicitly **does not claim**:
- Any result regarding worst-case complexity class separation or `P = NP`.
- Physically measured hardware energy savings (no RAPL or `powermetrics` instrumentation is included in this version).
- Universal superiority of adaptive reuse over incremental computation or periodic polling across arbitrary workloads or volatility regimes.
- Existence of cheap sound canaries for arbitrary opaque or discontinuous programs.

---

## 2. Formal Framework and Resource Ledger (`TS-BASE-001`)

We model a persistent computing system interacting with an environment over discrete steps $t = 1, \dots, T$ via the causal loop:

$$\text{Spacetime} \xrightarrow{\text{Observation}} \text{Timespace} \xrightarrow{\text{Prediction / Contract}} \text{Action / Output} \xrightarrow{\text{Effect}} \text{Spacetime}$$

where **Spacetime** denotes the external environment state $s_t$ and **Timespace** denotes the system's internal predictive and contractual representation $M_t$.

### 2.1 Five-Dimensional Resource Ledger

Every baseline and every living-computation variant is charged identically across five channels:

$$\mathbf{R}_t = \left(C^{\text{comp}}_t,\; C^{\text{obs}}_t,\; C^{\text{comm}}_t,\; C^{\text{mem}}_t,\; E^{\text{proxy}}_t\right)$$

- $C^{\text{comp}}_t$: exact computational operations (node evaluations, canary checks, contract compilations, fallback repairs, retirement checks).
- $C^{\text{obs}}_t$: observation/sensing queries executed at step $t$.
- $C^{\text{comm}}_t$: serialized bytes transmitted or persisted.
- $C^{\text{mem}}_t$: active representation bytes and per-step maintenance operations.
- $E^{\text{proxy}}_t$: deterministic modeled energy proxy computed from fixed linear hardware-inspired weights (operation, memory read/write, disk I/O, sensor query).

**Accounting Conservation Rule.** No startup, trace-compilation, canary-verification, storage-maintenance, or miss-fallback cost may be omitted or shifted off-ledger.

**Evidence Tier Separation.** Throughout this paper:
- `operation_counts_only` refers to exact, deterministic counts of executed primitive operations.
- `modeled_proxy_energy` refers to $E^{\text{proxy}}_t$ computed under explicit fixed cost weights.
- `physically_measured_energy` is **absent** in this preprint and never implied by $E^{\text{proxy}}_t$.

### 2.2 Guarantee Taxonomy

Every claim is tagged with one of four explicit guarantee tiers:
1. `general_worst_case` (not claimed anywhere in Paper I),
2. `restricted_worst_case` (exact deterministic guarantee under explicit structural assumptions, e.g., Theorem 1 and P4),
3. `conditional` / `distributional` (amortized or regime-dependent guarantee, e.g., Theorem 2),
4. `empirical` (observed on specified seeded benchmarks).

---

## 3. Certified Computational Reuse (`TS-001`)

Consider a pure directed acyclic computation graph $G = (V, E)$ partitioned into candidate reusable subgraphs $\{S_k\}$ with explicit input boundary $\partial_{\text{in}}(S_k)$ and output boundary $\partial_{\text{out}}(S_k)$.

### 3.1 Trace-to-Contract Compilation and Multi-Anchor Validity Atlas

A **Contract** $\mathcal{C}_k = (S_k, \mathcal{A}_k, \kappa_k)$ binds a subgraph $S_k$ to an **Anchor Atlas** $\mathcal{A}_k = \{(x^{(j)}, y^{(j)})\}_{j=1}^{m}$ of verified input-output boundary snapshots and an exact **Computational Canary** $\kappa_k: \partial_{\text{in}}(S_k) \to \{\texttt{SAFE}, \texttt{UNSAFE}, \texttt{UNKNOWN}\}$.

- `SAFE(j)`: the current input boundary exactly matches verified anchor $x^{(j)} \in \mathcal{A}_k$, authorizing immediate output emission $y^{(j)}$ without evaluating interior nodes of $S_k$.
- `UNSAFE`: the boundary departs from all anchored states; the system falls back immediately to dirty-propagation recomputation and updates the surprise tracker.
- `UNKNOWN`: insufficient observability or unverified structural preconditions; treated conservatively identically to `UNSAFE` (never emits a cached output).

To bound overhead under non-stationary shock regimes, each contract tracks an exponentially weighted hit-rate utility and triggers **adaptive retirement** when marginal verification cost exceeds avoided recomputation over a sliding window.

### 3.2 Theorem 1 (Canary Soundness / P6)

**Assumptions:**
1. *Purity & Determinism:* Every node $v \in S_k$ computes a pure deterministic function of its incoming edges with no hidden state or external side effects.
2. *Exclusive Ownership:* No interior node of $S_k$ is mutated externally or shared across overlapping uncoordinated contracts.
3. *Exact Interface Match:* $\kappa_k(x_t) = \texttt{SAFE}(j)$ holds if and only if the exact input boundary vector $x_t|_{\partial_{\text{in}}(S_k)} = x^{(j)}$.
4. *Conservative Fallback:* Any `UNSAFE` or `UNKNOWN` verdict executes exact ground-truth evaluation.

**Statement:** Under Assumptions 1–4, for every step $t \ge 1$ and every input trajectory, the output of certified reuse is bitwise identical to full recomputation (`0` false-SAFE errors).

**Proof Sketch:** If $\kappa_k(x_t) = \texttt{SAFE}(j)$, Assumption 3 ensures $x_t|_{\partial_{\text{in}}(S_k)} = x^{(j)}$. By induction on topological depth of $S_k$ using Assumptions 1 and 2, every interior node and therefore $\partial_{\text{out}}(S_k)$ evaluates identically to the archived verified execution $y^{(j)}$. Otherwise Assumption 4 invokes exact evaluation. Full machine-checkable verification is given in `research/claims/TS-001/proof.md` and `tests/test_ts001.py`. $\square$

### 3.3 Theorem 2 (Amortized Break-Even & Payback Horizon)

Let $C_{\text{comp}}$ be one-time compilation cost, $c_{\text{check}}$ be per-step canary check cost, $c_{\text{store}}$ be per-step trace/atlas maintenance cost, $g_{\text{save}}$ be operations saved on a `SAFE` hit, and $h \in [0, 1]$ be the empirical `SAFE` hit rate. Net cumulative operation savings after $T$ steps are:

$$\Delta C(T) = T \cdot \big(h \cdot g_{\text{save}} - c_{\text{check}} - c_{\text{store}}\big) - C_{\text{comp}}$$

Therefore:
1. **Positive asymptotic savings** occur if and only if $h > h^* = \frac{c_{\text{check}} + c_{\text{store}}}{g_{\text{save}}}$.
2. Whenever $h > h^*$, the **payback horizon** is $T^* = \left\lceil \frac{C_{\text{comp}}}{h \cdot g_{\text{save}} - c_{\text{check}} - c_{\text{store}}} \right\rceil$.
3. Whenever $h < h^*$, static retention accumulates unbounded net loss proportional to $T$, proving why **adaptive retirement** is structurally required under high-volatility regimes. $\square$

---

## 4. Adaptive Observation, Predictive Synchronization, and Timespace Inertia (`TS-002`, `TS-003`, `TS-004`)

Beyond static DAG execution, a living computer must decide **what to observe**, **when to synchronize**, and **how fast to forget**:

1. **Cost-Aware Adaptive Observation (`TS-002`).** Each sensor $i$ incurs observation cost $c_i^{\text{obs}}$. A living observer allocates sampling frequency to high-relevance channels while reserving a low-rate canary probe budget over dormant sensors to detect relevance drift (when previously irrelevant sensors suddenly govern the target).
2. **Bounded Predictive Synchronization (`TS-003` / P4).** Consider a linear dynamical state $x_{t+1} = \Phi x_t + w_t$ with bounded disturbance $\|w_t\|_\infty \le \epsilon$, prediction error budget $\delta$, and maximum un-observed horizon $\tau$. By propagating exact worst-case interval bounds $r_k = \epsilon \sum_{j=0}^{k-1} \|\Phi\|^j$, an adaptive certified-bound observer (`P4`) skips observation while $r_k \le \delta$, observes immediately before $r_k$ exceeds $\delta$, and emits `UNKNOWN` whenever an actual measurement violates the certified interval (signaling an unmodeled regime shift).
   - *Guarantee (`restricted_worst_case`):* Under $\|w_t\|_\infty \le \epsilon$, prediction error never exceeds $\delta$ (`0.00%` violations) prior to a regime shift, and any shift violating the bound is detected on the next observation.
   - *Explicit failure mode:* On unbounded Gaussian noise ($w_t \sim \mathcal{N}(0, \sigma^2 I)$), no finite worst-case bound exists, so P4 conservatively degrades to `100%` continuous observation.
3. **Timespace Inertia & Canary-Gated Memory (`TS-004`).** Retaining infinite historical traces creates *timespace inertia* (slow adaptation to regime shifts); retaining irrelevant features inflates maintenance cost linearly with memory footprint. Canary-gated memory maintains low routine variance during stability while accelerating decay upon confirmed canary surprise, maximizing the **Jump/Jitter ratio** (responsiveness during true regime shifts divided by routine state jitter).

---

## 5. Empirical Evaluation

All results below are pinned to SHA-256 verified JSON summaries from `living-computation/results/` and independently reproduced in our portable release bundle.

### 5.1 Milestone 01+02: 1,000-Node Computational DAG Across Four Regimes

**Setup:** Pure DAG with `1,000` nodes, `2,167` edges, `120` external inputs, depth `25`, evaluated over `10,000` sequential updates per regime (`40,004` total updates including initialization), compared against both **Full Recomputation** and a **Strong Incremental** dirty-propagation baseline.

| Regime (`10,000` updates each) | Full Recomputation (ops) | Strong Incremental (ops) | Living Certified Reuse (ops) | Savings vs Full | Savings vs Incremental | Payback $T^*$ | False-SAFE / Mismatches |
|---|---:|---:|---:|---:|---:|---:|---:|
| `localized_regime_drift` (in-memory surprise trace) | 8,821,276 | 663,878 | **562,200** | **+93.63%** | **+15.32%** | 408 | `0 / 0` |
| `drift_and_regime_shift` (in-memory delta trace) | 8,900,000+ | 656,574 | **563,759** | **+93.7%** | **+14.14%** | 382 | `0 / 0` |
| `recurring_states` (single-anchor vs Multi-Anchor Atlas) | 8,821,276 | baseline | Multi-Anchor Atlas | — | `-12.47%` → **`-3.34%`** | — | `0 / 0` |
| `high_entropy_shock` (raw static vs adaptive retirement) | 8,821,276 | baseline | Adaptive Retirement | — | `-47.67%` → **`-5.48%`** | N/A | `0 / 0` |

Key verified findings:
- **Zero soundness errors:** `0` output mismatches across `40,004` updates and `0` false-SAFE verdicts across `2,000` adversarial fuzz probes plus Multi-Anchor Atlas fuzzing.
- **Avoided work ratio:** In `localized_regime_drift`, `31` compiled contracts avoided `300,216` interior node evaluations, yielding $R_{\text{avoid}} = 1.68\times$ gross (`+0.68x` net) and lowering mean recomputed fraction $L_t$ from `0.0664` to `0.0414`.
- **Operation counts vs. modeled energy separation (critical finding):** Switching trace persistence from in-memory delta logging to synchronous disk JSONL logging preserves positive operation-count savings (`+15.32%` ops) while **flipping `modeled_proxy` energy negative** (`-6.60%` surprise trace, `-10.32%` delta trace). Under in-memory delta trace in `drift_and_regime_shift`, both operations (`+14.14%`) and modeled energy (`+14.95%`) are positive. This empirically demonstrates why operation counts alone cannot be equated with energy savings.

### 5.2 Experiment 1 & Experiment 2: Trace Storage Ablation and Shock-Rate Crossover

- **Experiment 1 (Trace-Storage Ablation, `5,000` updates):**
  - `full_materialized` trace recording suffers **`-167%` net ops** (never reaches payback).
  - `surprise_driven` trace recording achieves **`+13.23%` ops** and **`+17.15%` modeled proxy J** (payback $T^* = 577$).
- **Experiment 2 (Shock-Rate Sweep, `3,000` updates per rate $p$):**
  - Net operation savings vs. strong incremental scale smoothly with stability: **`+24.59%`** ($p=0.00$), **`+18.40%`** ($p=0.02$), **`+9.34%`** ($p=0.05$), crossing zero near **$p \approx 0.10\text{–}0.12$** (~`53%` SAFE hit rate, matching Theorem 2's analytical threshold $h^*$), turning negative at **`-5.08%`** ($p=0.15$) and **`-30.05%`** ($p=0.60$).
  - **Periodic canary failure:** Unsound periodic checking (`P = 5..50`) incurs **`77.6%–98.4%`** silent output error rates—confirming that exact boundary verification (or explicit `UNKNOWN` fallback) is mandatory for safety.

### 5.3 Experiment 3: Cost-Aware Adaptive Observation Under Relevance Drift (`TS-002`)

**Setup:** `60` heterogeneous sensors over `5,000` steps with a mid-run relevance drift activating `4` previously dormant sensors.

| Strategy | Modeled Proxy Energy | Savings vs Observe-All | Post-Drift Recovery | Post-Drift MSE | Safety Violations |
|---|---:|---:|---:|---:|---:|
| `observe_all` (baseline) | 72.88 J | 0.00% | Immediate | 0.0222 | 59 |
| `static_learned` (no canary probes) | — | — | **Never recovers** | **6.2302** | **2,533** |
| `living_adaptive` (canary probes) | **17.52 J** | **+75.95%** | **131 steps** | 0.2700 | 203 |

This result establishes an explicit **accuracy-versus-energy trade-off**: adaptive canary probing saves `75.95%` modeled energy and avoids the catastrophic failure of static learned selection (`2,533` violations), but incurs higher transient post-drift error (`203` vs `59` violations) than continuous full observation.

### 5.4 Experiment 8: Synchronized Predictive Computation (`TS-003` / P4)

**Setup:** `6`-dimensional dynamical system with tolerance $\delta = 0.05$, lookahead $\tau = 2$, evaluated across both bounded-disturbance regime shift (`1.85x` shift, $\epsilon = 0.50$) and stationary linear-Gaussian dynamics.

| Regime / Policy | Violation Rate (Pre / Post) | Modeled J vs Continuous | Shift Detection Latency | Sync Guarantee |
|---|---:|---:|---:|---|
| **Bounded `1.85x` shift — `adaptive_certified_bound` (P4)** | **0.00% / 0.00%** | **-14.8%** | **5 steps (`UNKNOWN`)** | `SyncOK = True` |
| **Bounded `1.85x` shift — `adaptive_kalman_uncertainty`** | 0.24% (overall) | -28.6% | 10 steps | Empirical |
| **Bounded `1.85x` shift — `periodic_p5`** | Fails post-shift (**9.15% > 5%**) | — | None | Violated |
| **Stationary linear-Gaussian — `periodic_p3` (negative control)** | **3.72%** (`33.4%` obs) | **1.15 J** | N/A | **Beats adaptive Kalman (`2.53 J`, `78.1%` obs)** |
| **Unbounded Gaussian — `adaptive_certified_bound` (P4)** | 0.00% | 0.0% (`100%` obs) | N/A | Degrades to full obs (boundary) |

### 5.5 Experiment 9: Timespace Inertia & Canary-Gated Memory (`TS-004`)

**Setup:** `1,800` steps with abrupt regime shifts at $t = 600$ and $t = 1200$.

| Memory Policy | Routine Hellinger Jitter | Jump/Jitter Ratio | Post-Shift Recovery | Action Accuracy | Status |
|---|---:|---:|---:|---:|---|
| **`living_canary_memory`** | **0.04296** (lowest) | **6.08x** (highest) | **19 steps** (fastest) | **98.85%** | Best trade-off |
| `naive_infinite_memory` (Counterexample 1) | Low | Low | **None (fails to adapt)** | **65.94%** | Fails under shift |
| `bloated_irrelevant_memory` (Counterexample 2) | Degraded | Degraded | Slow | Worse MSE | `208x` bytes → `196x` maint. ops |

### 5.6 Physical Hardware-Energy Extension & Prospective Cross-Workload Validation (`exp_hw01`–`exp_hw04`)

To test whether abstract operation-count savings survive on real silicon—and whether physical energy break-even boundaries can be predicted prospectively—we executed four progressive Apple M3 Max hardware benchmarks (`experiments/hw_energy_paper01/` through `experiments/hw_soc_prospective_exp04/`) pairing per-process CPU hardware PMU energy (`proc_pid_rusage(RUSAGE_INFO_V6)` `ri_energy_nj`) with whole-SoC internal accumulators (`libIOReport.dylib` `"Energy Model"`: `CPU + GPU + ANE + DRAM0 + DCS0 + AMCC0`, explicitly distinct from AC wall-plug power). All runs verified **`0` output mismatches**.

1. **Fragility at Fine Scalar Granularity (`K = 1`) & Whole-SoC Transition (`exp_hw01`–`exp_hw03`):**
   - Although a single-seed Python `3.11.7` pilot (`exp_hw01`) showed `+9.33%` process CPU energy savings at `K = 1`, expanding to `N = 10` independent seeds under battery power and Python `3.12.1` (`exp_hw02`) reduced the `K = 1` margin against Strong Incremental to `+1.18 ± 1.82%` (`p = 0.182`) on process CPU and `-1.21 ± 21.34%` (`p = 0.766`) on Whole-SoC Package—proving that `K = 1` scalar Python reuse is not robustly energy-positive against Strong Incremental, and that physical CPU energy crosses negative near shock rate $p \approx 0.05\text{–}0.06$ (half the abstract-op crossover $p \approx 0.11\text{–}0.12$).
   - Synchronous disk JSONL logging significantly degraded hardware energy vs. Strong Incremental (`-8.21 ± 2.49%` process CPU, `p = 0.00003`; `-19.02 ± 16.98%` Whole-SoC Memory+Fabric, `p = 0.037`).
   - Increasing pure node compute granularity $K \in \{1..80\}$ on AC Power with pinned Python `3.11.7` (`exp_hw03`, `N = 8` paired blocks) produced statistically significant Whole-SoC savings from `K >= 3` (`+14.04 ± 11.79%`, `p = 0.0285`) up to **`+36.16 ± 4.93%` Whole-SoC** (`+35.32%` Memory+Fabric, `p < 1e-5`) at `K = 80`. *(A discrete dispatch jump between unwrapped `K = 1` and closure-wrapped `K >= 2` is explicitly documented in `exp_hw03/REPORT.md`.)*

2. **Two Independently Sourced Real-Code Workloads (`exp_hw03` & `exp_hw04`, Full Lifecycle Included):**
   - **117 Python 3.11 stdlib modules (`exp_hw03`, `2.1 MiB`, `236` real import edges, `2 × 117` two-pass cold start + `20` experimentally mutated edits):** Certified public-interface AST canaries reduced Whole-SoC energy by **`+82.16 ± 1.98%`** vs. full rebuild and **`+63.89%` (`q=0.00`) → `+47.72%` (`q=0.25`) → `+35.68%` (`q=0.50`) → `+18.68%` (`q=0.75`)** (`p <= 0.0001`) vs. strong incremental analysis, turning negative at `q = 1.00` (`-8.37 ± 13.64%`, `p = 0.185`).
   - **71 `_pytest` modules (`exp_hw04`, `1.28 MiB`, `310` acyclic real import edges, single-pass `1 × 71` cold start + `20` edits, incremental static type-signature & call-arity checker, `N = 10` paired blocks on AC Power):** Certified type-signature canaries reduced Whole-SoC energy by **`+76.92 ± 6.24%`** vs. full typecheck and **`+88.96 ± 1.39%` (`q=0.00`) → `+68.99 ± 6.31%` (`q=0.25`) → `+40.76 ± 10.10%` (`q=0.50`) → `+21.15 ± 7.23%` (`q=0.75`)** (`p <= 0.0002`) vs. strong incremental typechecking, reaching the boundary at `q = 0.90` (`+7.23 ± 9.80%`, `p = 0.128`) and `-0.94 ± 4.19%` (`p = 0.694`) at `q = 1.00`.

3. **Prospective 5-Component Energy Prediction & Methodological Audit (`exp_hw04`):**
   - Prior to executing `exp_hw04`, we SHA-256-sealed two prospective models (`preregistered_predictions.json`, zero refitting) decomposed into $E_{\text{reuse}} = E_{\text{dispatch}} + E_{\text{validation}} + E_{\text{execution}} + E_{\text{memory}} + E_{\text{maintenance}}$:
     - **Model 1 (Zero-Shot from `exp_hw03` alone):** Fractional `%` savings transferred accurately (`R²_% = 0.9999` conditional / `0.9937` strictly blind, `MAE = 2.07 pp` CPU), whereas **absolute Whole-SoC Joules failed zero-shot (`R²_J = -0.545`)** due to ~`2x` per-KiB algorithm and ambient-load differences.
     - **Model 2 (5-Term Primitive Micro-Probe on `8` disjoint modules; calibration cost `7.27 J` CPU / `17.41 J` Whole-SoC, repaying in `N*_cal = 1–3` runs for `q <= 0.75`):** Achieved **$R^2_{\text{Joules}} = 0.9997$ (CPU)** / **`0.9610` (Whole-SoC)** conditional on the static edit schedule, and **$R^2_{\text{Joules}} = 0.9869$ (`MAE = 2.08 pp`, CPU)** / **`0.9450` (`MAE = 1.48 pp`, Whole-SoC)** under a **strictly blind unseen-schedule audit** using only static corpus population means and `q` (explicitly disclosing and correcting `exp_hw04`'s shared static RNG seed schedule; see `exp_hw04/results/exp_hw04_audit.json`).
   - Together, `exp_hw03` and `exp_hw04` motivate the frozen external evaluation protocol (`protocols/prospective-energy-protocol-v1.md`) and the separable transfer hypothesis $\Delta E \approx E_{\text{baseline}} \cdot f(K, q, \mathcal{V}) - E_{\text{overhead}}$.

---

## 6. Consolidated Failure Boundaries and Negative Results

A core discipline of Temporal Science is treating failure boundaries as first-class scientific outputs rather than footnotes. Across Paper I, six explicit failure regimes were verified:

1. **Synchronous Disk I/O Inversion:** Persisting traces synchronously to disk turns `modeled_proxy` energy negative (`-6.60%` to `-10.32%`) even when operation counts drop by `+15.32%`.
2. **Full Trace Materialization Penalty:** Recording full unpruned execution traces increases total operations by `+167%` and never reaches payback.
3. **Volatility Crossover ($p > 0.12$):** When environmental shocks drive `SAFE` hit rates below the Theorem 2 threshold (~`53%`), static contract reuse becomes a net liability (`-5.08%` at $p=0.15$ to `-47.67%` under high-entropy shock); adaptive retirement bounds loss to `-5.48%` but cannot manufacture positive savings out of pure noise.
4. **Silent Failure of Unsound Periodic Canaries:** Checking contracts periodically (`P = 5..50`) causes `77.6%–98.4%` silent output errors.
5. **Stationary Linear-Gaussian Simplicity Limit:** When dynamics are stationary and well-modeled by a known linear-Gaussian process, fixed periodic polling (`P = 3`, `1.15 J`) beats adaptive Kalman uncertainty sampling (`2.53 J`), and P4 interval bounds degrade to `100%` observation on unbounded Gaussian noise.
6. **Memory Pathologies:** Retaining infinite un-decayed history causes permanent adaptation failure (`65.94%` accuracy), while retaining irrelevant dimensions incurs a `196x` maintenance-operation blowup (`208x` memory) with worse predictive accuracy.

---

## 7. Related Work and Novelty Boundaries

As documented in `research/literature/novelty-audit.md`, Paper I builds directly on mature literatures and claims novelty only at their **verified integration under complete lifecycle accounting**:

- **Incremental & Self-Adjusting Computation (Acar et al.; Adapton; Salsa):** Strong dirty-propagation incremental computation is our primary baseline, not a strawman. Paper I adds multi-anchor contract compression, exact `SAFE`/`UNSAFE`/`UNKNOWN` boundary canaries, and adaptive retirement when volatility exceeds Theorem 2's threshold.
- **Event-Triggered Control & Kalman Filtering:** Adaptive observation (`TS-002`) and predictive synchronization (`TS-003`) connect directly to event-triggered state estimation. We explicitly show where standard periodic control outperforms adaptive estimation (stationary linear-Gaussian).
- **Concept Drift Detection & Continual Learning:** Timespace inertia (`TS-004`) formalizes the stability-plasticity trade-off through the Jump/Jitter ratio and full maintenance-cost accounting.

---

## 8. Limitations, Open Obligations, and Falsification Criteria

### 8.1 Current Blockers for Higher Release Tiers
- **`energy_focused_paper` (BLOCKED):** While `exp_hw01`–`exp_hw04` establish AC-powered Apple M3 Max process-PMU and whole-SoC (`IOReport`) energy savings and prospective predictability across synthetic DAGs and two real-code workloads, true **AC wall-plug / discrete SSD-rail** metering, uncontrolled historical Git commit streams, and **cross-architecture (Intel/AMD RAPL)** replication remain required before promoting this tier.
- **`independently_validated_release` (BLOCKED):** Requires independent external replication by researchers other than the initiative authors following the frozen blind protocol (`protocols/prospective-energy-protocol-v1.md`), plus formal proof audit of open obligations `P5` and `P9`.

### 8.2 What Would Falsify or Narrow This Paper?
We actively invite external researchers to challenge Paper I—starting with the concrete question: *Does the 5-term physical energy prediction model continue to work when someone other than its creator chooses the problem?* Any of the following verified demonstrations would falsify or materially narrow its claims:
1. A counterexample where a pure, exclusively owned DAG subgraph produces a `SAFE` verdict whose output differs from full recomputation (falsifying `TS-001` / Theorem 1).
2. Independent execution of `protocols/prospective-energy-protocol-v1.md` on a real-world workload (e.g., Rust/TypeScript/Python build graph or Git history on Intel/AMD RAPL or wall-plug wattmeter) showing that the 5-term primitive model fails to predict break-even or that memory/cache effects negate reuse savings even at realistic compute granularity.
3. A non-synthetic workload with localized regime drift where a well-engineered strong incremental baseline consistently beats certified reuse across all trace-compilation thresholds.
4. A proof or benchmark showing that `TS-002` or `TS-004` canary overhead cannot stay below periodic baselines in realistic multi-regime drift environments.

---

## 9. Exported Research Contract (`TS-CERTIFIED-REUSE`) and Portable Reproduction

Paper I exports the versioned research contract `TS-CERTIFIED-REUSE (v0.1.0)` consumed downstream by Papers II–V:
- **Guarantees exported:** Sound local contract reuse (`0` false-SAFE under Theorem 1 premises), analytical payback/retirement boundary (Theorem 2), and bounded predictive sync (`P4`).
- **Caveats exported:** `modeled_proxy` energy only; no hardware energy claim; strict failure boundaries under high entropy ($p > 0.12$), synchronous disk logging, and unbounded Gaussian noise.

### Standalone Clean-Environment Reproduction

Paper I is distributed as a self-contained portable archive (`papers/01-certified-reuse/release/paper-01-v0.1.0-portable.tar.gz`) containing **zero external relative paths**. To reproduce independently in any clean directory:

```bash
tar -xzf paper-01-v0.1.0-portable.tar.gz
cd paper-01-v0.1.0-portable
python3 reproduce.py
```

The standalone `reproduce.py` script verifies SHA-256 checksums of every bundled artifact, executes the machine-checked `TS-001` contract soundness test, re-runs a live verification of the `1,000`-node DAG (`0` mismatches, `0` false-SAFE), checks P4 bounded synchronization (`0.00%` violations), and checks Experiment 9 Jump/Jitter separation without accessing any file outside the unpacked directory.
