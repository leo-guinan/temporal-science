# Whole-SoC Energy Validation & Paper I Energy-Evidence Assessment (`exp_hw02`)

**Experiment ID:** `exp_hw02_whole_soc_apple_m3_max` · **Version:** `0.1.0`  
**Date:** November 22, 2026  
**Hardware:** Apple M3 Max (`16` logical cores, `48.0 GB` unified RAM, `macOS-26.5.1-arm64`)  
**Raw Telemetry & Summary:** `results/exp_hw02_summary.json`, `results/exp_hw02_raw_blocks.json`  
**Figures:** `results/fig1_soc_vs_process_regimes.png`, `results/fig2_soc_crossover_concentrated.png`, `results/fig3_soc_granularity_and_rails.png`

---

## 1. Exposed Telemetry & Energy-Accounting Methodology

### 1.1 `powermetrics` Probe & Backend Selection
1. Inspecting `powermetrics --help` confirmed documented samplers: `tasks, battery, network, disk, interrupts, cpu_power, thermal, sfi, gpu_power, ane_power`.
2. Running `powermetrics` without root returned `powermetrics must be invoked as the superuser`, and a command-boundary check (`sudo -n powermetrics ...`) confirmed non-interactive `sudo` requires an interactive password.
3. With explicit command-boundary user approval (`BypassSandbox: true`, zero OS bypasses), we queried macOS's standard `libIOReport.dylib` `"Energy Model"` hardware accumulator interface—the exact Apple Silicon hardware telemetry backend read by `powermetrics`—exposing **325 live hardware energy channels** simultaneously with per-process `proc_pid_rusage(os.getpid(), RUSAGE_INFO_V6)`.

### 1.2 Non-Overlapping Rail Definitions (Zero Double-Counting)
Every execution window $[t_{\text{start}}, t_{\text{end}}]$ records exact hardware accumulator deltas across five strictly non-overlapping boundaries:
- **Process-Isolated CPU PMU (`proc_cpu_energy_j`)**: `proc_pid_rusage` `ri_energy_nj` (strictly isolated to the benchmark Python process).
- **Whole-SoC CPU Complex (`soc_cpu_j`)**: `IOReport` `CPU Energy` (covers `EACC_CPU + PACC0_CPU + PACC1_CPU`, cores + SRAM + CPM).
- **Whole-SoC Compute (`soc_compute_j`)**: `CPU Energy + GPU Energy + ANE0` (equivalent to `powermetrics` Combined Power).
- **Whole-SoC Memory & Fabric (`soc_memory_j`)**: `DRAM0 + DCS0 (DRAM Controller) + AMCC0 (Apple Memory Cache Controller)`.
- **Whole-SoC Package (`soc_package_j`)**: `soc_compute_j + soc_memory_j`.
- **Idle-Subtracted Net SoC (`soc_package_net_j`)**: $E_{\text{SoC,pkg}} - \bar{P}_{\text{idle}, b} \cdot \Delta t$, where $\bar{P}_{\text{idle}, b}$ is the mean of a `0.35 s` idle window immediately before and immediately after block $b$.

> **Explicit Scope Limitation (NOT Wall-Plug Measurements):** Whole-SoC `IOReport` energy estimates are **Apple Silicon internal SoC energy model accumulators**, **not** AC wall-plug power measurements. They exclude AC/DC adapter losses, display panel backlight, discrete SSD NAND flash package rails, cooling fans, and battery charging circuitry. Moreover, because `IOReport` measures the whole chip, ambient OS background load adds variance to short (`< 1 s`) windows.

### 1.3 Scientific Controls Recorded
- **Paired Interleaved Blocking (`N = 10` blocks):** Every block $b \in \{0,\dots,9\}$ uses an independent workload seed (`2026 + 17b`) and shuffles variant execution order randomly within the block. All statistics report paired differences ($\text{base}_b - \text{cand}_b$), 95% Student-$t$ CIs ($\text{df}=9$), paired Cohen's $d_z$, and two-sided paired $t$-test $p$-values.
- **Process PMU Linearity Calibration (`1x / 2x / 4x`):** `4x/1x = 4.0193x` hardware energy, `3.9960x` retired instructions.
- **Measurement Overhead Control (`10` pairs):** Enabling `IOReport` alongside `proc_pid_rusage` added `+2.889 ms` wall time (`p = 0.0006`) and `+0.682 mJ` CPU energy (`p = 0.926`, statistically indistinguishable from zero).
- **Ambient Conditions Logged Transparently (Critical Confounders!):**
  - **Power source:** Machine ran on **Battery Power (`19% → 14%`, discharging)** rather than AC wall power.
  - **Thermal state:** `pmset -g therm` recorded no thermal or performance warning levels throughout the entire run.
  - **Background load:** Active desktop load averaged `load1m = 6.63 → 6.51`, producing ambient whole-SoC idle power of **`8.43 ± 2.69 W`** (range `4.62–16.56 W`: CPU `3.00 W`, GPU/ANE `0.74 W`, Memory/Fabric `4.70 W`).
  - **Python runtime shift (`3.11.7 → 3.12.1`):** Outside the sandbox, `python3` resolved to Python `3.12.1` (vs `3.11.7` in `exp_hw01`). Python `3.12`'s specializing adaptive interpreter accelerated scalar DAG arithmetic (`strong_incremental` dropped from `2.23 J` in `exp_hw01` to `1.91 J` here), narrowing fine-grained `K = 1` headroom—a genuinely informative runtime-sensitivity finding preserved in full below.
- **Output Correctness:** **`0` mismatches** against `FullRecomputeEngine` across every single block and campaign (`100.0%` exact equivalence).

---

## 2. Empirical Results (`N = 10` Paired Interleaved Blocks)

### 2.1 Campaign C1: Core Paper I Conditions (`10,000` updates × 10 independent seeds)

| Comparison (`N = 10` blocks, `K = 1` unmodified DAG) | Abstract Ops (%) | Process CPU PMU `ri_energy_nj` (%) | Whole-SoC Package Raw (%) | Whole-SoC Memory+Fabric (%) | Statistical Verdict |
|---|---:|---:|---:|---:|---|
| **In-Mem Reuse vs Full** (`localized_regime_drift`) | `+93.69 ± 0.07%` | **`+87.75 ± 0.21%`** *(p < 1e-5, dz=+92.5)* | **`+88.12 ± 1.36%`** *(p < 1e-5, dz=+5.91)* | **`+86.88 ± 1.01%`** *(p < 1e-5)* | **Decisive win on all rails** (`45.53 → 5.36 J`) |
| **In-Mem Reuse vs Strong Inc** (`localized_regime_drift`) | `+15.73 ± 0.77%` | `+1.18 ± 1.82%` *(p = 0.182, dz=+0.46)* | `-1.21 ± 21.34%` *(p = 0.766, dz=+0.10)* | `-1.53 ± 14.22%` *(p = 0.923)* | **NOT significant at `K=1` on Py 3.12 + battery** |
| **Disk-Logged Reuse vs Strong Inc** (`localized_regime_drift`) | `+15.73 ± 0.77%` | **`-8.21 ± 2.49%`** *(p = 0.00003, dz=-2.40)* | `-19.90 ± 23.61%` *(p = 0.152)* | **`-19.02 ± 16.98%`** *(p = 0.0373)* | **Significant hardware energy LOSS** (incl. DRAM/fabric) |
| **Static Reuse vs Strong Inc** (`high_entropy_shock`) | `-47.2%` | **`-22.69 ± 0.91%`** | `-20.11 ± 13.83%` | negative | Failure boundary confirmed |
| **Adaptive Retire vs Strong Inc** (`high_entropy_shock`) | `-1.8%` | **`-19.23 ± 0.49%`** | `-18.01 ± 14.61%` | negative | Retiring contracts alone misses Python trace-loop energy |

**Crucial Disagreement Preserved Between `exp_hw01` and `exp_hw02` at `K = 1`:** In `exp_hw01` (single seed `2026`, Python `3.11.7`), unmodified `K = 1` in-memory reuse saved `+9.33%` process CPU energy vs Strong Incremental. Under `exp_hw02` (`10` independent seeds, Python `3.12.1`, battery power, `load1m ≈ 6.6`), that `K = 1` margin shrank to **`+1.18 ± 1.82%` (`p = 0.182`)** on process CPU and **`-1.21 ± 21.34%` (`p = 0.766`)** on whole-SoC package energy, even while retired instructions remained significantly lower (`+7.47 ± 0.43%`, `p < 1e-5`). At `K = 1`, scalar Python interpreter dispatch overhead leaves no robust hardware-energy margin against Strong Incremental.

### 2.2 Campaign C2: Node Compute-Granularity Scaling (`K = 1, 5, 20, 80`, `3,000` updates × 10 blocks)

| Granularity $K$ (vs Strong Incremental) | Abstract Ops (%) | Process CPU PMU (%) | Whole-SoC Package Raw (%) | Whole-SoC Memory+Fabric (%) | Whole-SoC Verdict |
|---:|---:|---:|---:|---:|---|
| **`K = 1`** *(unmodified scalar Python)* | `+14.8%` | `+3.23 ± 2.54%` *(p = 0.0186, dz=+0.91)* | `-3.33 ± 15.71%` *(p = 0.881)* | `-7.18%` | **Not established on whole-SoC** |
| **`K = 5`** | `+14.8%` | **`+15.13 ± 2.17%`** *(p < 1e-5, dz=+4.58)* | `+6.26 ± 20.91%` *(p = 0.533)* | `+13.12%` | Process CPU established; whole-SoC noise-limited |
| **`K = 20`** | `+14.8%` | **`+26.00 ± 1.39%`** *(p < 1e-5, dz=+13.67)* | **`+13.40 ± 7.70%`** *(p = 0.0023, dz=+1.33)* | **`+16.51%`** | **Whole-SoC advantage statistically established** |
| **`K = 80`** | `+14.8%` | **`+33.92 ± 0.89%`** *(p < 1e-5, dz=+27.66)* | **`+36.40 ± 5.37%`** *(p < 1e-5, dz=+2.61)* | **`+33.62%`** | **Strong whole-SoC win across CPU + DRAM/Fabric** |

### 2.3 Campaign C3: Concentrated Shock-Crossover Sweep (`p = 0.00..0.30`, `K = 1`, `N = 10` blocks)

| Shock Rate $p$ | Abstract Ops (%) | Process CPU PMU (%) | Whole-SoC Package Raw (%) | Observation |
|---:|---:|---:|---:|---|
| `0.00` | `+26.41%` | **`+10.01 ± 1.91%`** *(p < 1e-5)* | `+4.34 ± 8.44%` *(p = 0.258)* | Positive CPU energy only at very low shock rates |
| `0.04` | `+14.83%` | `+1.60 ± 2.67%` *(p = 0.186)* | `-19.41 ± 30.58%` *(p = 0.197)* | Already loses statistical significance |
| **`0.06`** | `+9.40%` | **`-0.74 ± 3.10%`** *(p = 0.640)* | `-12.54 ± 28.07%` *(p = 0.713)* | **CPU energy crosses zero (`p ≈ 0.05–0.06`, half of op crossover!)** |
| `0.07–0.08` | `+7.21% / +5.56%` | `-1.44% / -1.68%` | `-11.43% (p=0.006) / -0.08%` | Negative on silicon while ops still > +5% |
| `0.09–0.12` | `+3.54% → -0.52%` | **`-4.04% → -7.04%`** *(all p <= 0.005)* | **`-14.15% (p=0.030) → -7.76% (p=0.030)`** | **Statistically significant LOSS on BOTH CPU and Whole-SoC** |
| `0.15–0.30` | `-5.19% → -17.30%` | **`-9.46% → -17.41%`** *(all p < 1e-5)* | `-14.17% → -10.48%` | Sustained loss regime |

---

## 3. Updated Paper I Energy-Evidence Assessment & Release-Gate Decision

### Gate Decision: **DO NOT PROMOTE `energy_focused_paper` (Remains `ready: false`)**

**What physical claims ARE now empirically supported (with 10-block paired CIs on Apple M3 Max):**
1. **Whole-SoC energy reduction vs Full Recomputation:** `+88.12 ± 1.36%` whole-SoC package energy (`CPU + GPU + ANE + DRAM + DCS + AMCC`, `45.53 J → 5.36 J`, `p < 1e-5`) and `+86.88 ± 1.01%` DRAM/memory-fabric energy (`18.72 J → 2.44 J`).
2. **Whole-SoC energy reduction vs Strong Incremental at realistic node compute granularity (`K >= 20`):** `+13.40 ± 7.70%` (`p = 0.0023`) at `K = 20` and **`+36.40 ± 5.37%` (`p < 1e-5`, including `+33.62%` DRAM/memory-fabric savings)** at `K = 80`.
3. **Negative physical regimes directly proven on silicon:** Synchronous disk JSONL logging significantly degrades process CPU energy (`-8.21 ± 2.49%`, `p = 0.00003`) and DRAM/fabric energy (`-19.02 ± 16.98%`, `p = 0.037`); fine-grained `K = 1` scalar Python reuse fails to establish a statistically significant whole-SoC advantage against Strong Incremental (`-1.21 ± 21.34%`, `p = 0.766`); and physical energy crosses negative near `p ≈ 0.05–0.06` (`K=1`), well before the abstract op crossover (`p ≈ 0.11–0.12`).

**What remains unmeasured / blocking `energy_focused_paper`:**
1. **Quiet-host AC-powered whole-SoC runs:** Ambient load (`load1m ≈ 6.6`, idle `8.43 ± 2.69 W`) and low battery (`19% → 14%`) widened sub-second whole-SoC CIs to `±15–21%`; quiet dedicated-host runs on AC power with longer integration windows (`>= 5 s`) are needed to tighten `K = 1` and `K = 5` whole-SoC uncertainty.
2. **Wall-plug / external power-meter and discrete SSD rail measurements:** `IOReport` does not meter AC wall power, PSU losses, or discrete SSD NAND flash power.
3. **Non-synthetic real-world workloads & cross-architecture (Intel/AMD RAPL) replication:** Needed to generalize beyond a synthetic Python DAG on a single Apple M3 Max laptop.
