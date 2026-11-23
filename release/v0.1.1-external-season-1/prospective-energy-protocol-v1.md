# Frozen Prospective Physical Energy Evaluation Protocol (v1.0.0)

**Protocol ID:** `TS-PROTO-HW-ENERGY-v1.0.0` · **Status:** Frozen for Independent External Replication  
**Initiative:** Temporal Science (`temporal-science/protocols/`)  
**Target Hypotheses:**
1. **Five-Component Physical Accounting Law:**
   $$E_{\text{reuse}} = E_{\text{dispatch}} + E_{\text{validation}} + E_{\text{execution}} + E_{\text{memory}} + E_{\text{maintenance}}$$
   with non-overlapping boundary definitions preventing double-counting.
2. **Separable Structural vs. Physical Scale Hypothesis:**
   $$\Delta E \approx E_{\text{baseline}} \cdot f(K, q, \mathcal{V}) - E_{\text{overhead}}$$
   testing whether dimensionless fractional savings $f(K, q, \mathcal{V})$ transfer across workloads even when physical energy scale $E_{\text{baseline}}$ requires local primitive calibration.

---

## 1. Non-Negotiable Preregistration Rules (Anti-Leakage Controls)

Any evaluation claiming prospective compliance with `TS-PROTO-HW-ENERGY-v1.0.0` MUST satisfy all five rules:

1. **Strict Blind Schedule Rule (No Shared Seeds):** Preregistered predictions MUST NOT inspect the exact RNG seeds, commit sequence, or per-step operation counts of the held-out evaluation runs. Predictions may use ONLY static repository/graph summary statistics (e.g., module count, source size distribution, mean downstream fanout, declared churn parameter $q$ or granularity $K$) and primitive calibration measurements from a disjoint micro-slice. *(Lesson encoded directly from the `exp_hw04` audit.)*
2. **Immutable Pre-Execution Commitment:** Predictions for EVERY evaluated configuration (both positive and expected negative/failure regimes) MUST be serialized to JSON with a UTC timestamp and SHA-256 commitment digest **before** a single evaluation trial executes, and the digest MUST be re-verified after execution with **zero post-hoc refitting**.
3. **Full Lifecycle & Calibration Payback Accounting:** Reported net energy MUST include cold-start representation construction, canary/contract validation, dispatch, memory/storage maintenance, and fallback recomputation. Whenever local primitive calibration is used (e.g., an 8-module micro-probe), its exact calibration energy $E_{\text{cal}}$ and payback count $N^*_{\text{cal}} = \lceil E_{\text{cal}} / \Delta E_{\text{run}} \rceil$ MUST be reported explicitly.
4. **Equal-Work & Zero-Mismatch Verification:** Every compared strategy (`full`, `strong_incremental`, `certified_reuse`) MUST produce bitwise-identical (or tolerance-verified) outputs over identical inputs with symmetric dependency-graph accounting.
5. **Explicit Negative-Boundary Inclusion:** Every evaluation MUST include at least one high-churn ($q \to 1.0$) or ultra-fine-granularity ($K \to 1$) regime where certified reuse is expected to lose or become statistically indistinguishable from the incremental baseline.

---

## 2. Mandatory Hardware Telemetry & Environmental Controls

| Requirement | Specification |
|---|---|
| **Power source** | AC mains power (never low battery); log power state before and after execution. |
| **Runtime pinning** | Pin exact interpreter/compiler version and binary path across calibration and evaluation. |
| **Blocking & ordering** | Minimum `N >= 8` (recommended `N = 10`) interleaved, independently seeded paired blocks; randomize condition order within every block; discard 1 warm-up pass. |
| **Telemetry boundary disclosure** | Explicitly separate: (a) Process CPU PMU (`ri_energy_nj` / Linux `perf` / RAPL core), (b) Whole-SoC / Package + DRAM (`IOReport` / `powermetrics` / Intel RAPL pkg+DRAM), and (c) Wall-plug AC wattmeter. **Never label SoC or RAPL counters as wall-plug energy.** |
| **Controls** | Log linearity calibration (`1x/2x/4x`), telemetry overhead control (paired with vs without sampler), ambient load average, thermal throttling state, and disk I/O bytes. |
| **Statistics** | Report paired differences, 95% Student-$t$ CIs ($\text{df} = N - 1$), paired Cohen's $d_z$, two-sided paired $t$-test $p$-values, and out-of-sample / prospective $R^2$, MAE (Joules and percentage points), and signed bias. |

---

## 3. Minimum Challenge Protocol for External Researchers

An independent researcher can test, replicate, or falsify Temporal Science's predictive energy model on a workload **they** choose in four steps:

1. **Select an independent workload** with real reusable substructure (e.g., an incremental Rust/TypeScript/Python compiler or build graph, a real Git commit history, or a streaming feature pipeline) and a strong incremental baseline.
2. **Run a disjoint primitive micro-probe** (`<= 10%` of the corpus) to measure the 5 energy components ($E_{\text{dispatch}}, E_{\text{validation}}, E_{\text{execution}}, E_{\text{memory}}, E_{\text{maintenance}}$) and record $E_{\text{cal}}$.
3. **Seal `preregistered_predictions.json` (SHA-256)** predicting net Joules, percentage savings, and break-even churn/granularity ($q^*$ or $K^*$) on unseen evaluation streams using ONLY static summary statistics.
4. **Execute `N >= 10` paired interleaved blocks** on your hardware (Apple Silicon `IOReport`/`powermetrics`, Linux Intel/AMD RAPL, or an external wattmeter) and report prospective $R^2$, MAE, calibration payback $N^*_{\text{cal}}$, and all discrepancies—whether they confirm, narrow, or falsify the model.
