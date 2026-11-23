# `exp_hw04` — Prospective, Cross-Workload Temporal-Energy Validation on `_pytest`

**Experiment ID:** `exp_hw04_prospective_pytest_typechecker` · **Version:** `0.1.0`  
**Preregistration SHA-256 Seal:** `2867e5df892c97271d23f0fba8ff592e4816e6f30f5e83015ea67702bfb63925`  
**Preregistered UTC:** `2026-11-23T00:58:17.404509+00:00` · **Executed UTC:** `2026-11-23T01:04:33Z`  
**Hardware & Controls:** Apple M3 Max (`16` cores, `48 GB` RAM, `macOS-26.5.1-arm64`), **AC Power**, pinned **Python `3.11.7`**, `N = 10` paired interleaved blocks, dual-layer telemetry (`proc_pid_rusage(RUSAGE_INFO_V6)` + whole-SoC `libIOReport.dylib` Energy Model `CPU + GPU + ANE + DRAM0 + DCS0 + AMCC0`).  
**Artifacts:** `results/preregistered_predictions.json`, `results/exp_hw04_summary.json`, `results/exp_hw04_raw_blocks.json`  
**Figures:** `results/fig1_prospective_vs_measured_joules.png`, `results/fig2_rails_and_prospective_parity.png`

---

## 1. Strict Prospective Protocol & Workload Independence

To test whether the physical temporal-advantage energy model generalizes **prospectively** to a completely new codebase and a different computational task without post-hoc curve fitting:

1. **Independently Sourced Codebase & Distinct Task:**
   - Replaced `exp_hw03`'s Python stdlib corpus (`email/http/...`) and cyclomatic-complexity task with **`_pytest` (`pytest 9.0.2`)**—`71` real, heavily typed non-test `.py` modules (`1,279.1 KiB`, `310` acyclic real inter-module import edges after deterministic cycle condensation).
   - Implemented a **real Incremental Static Type-Signature & Cross-Module Call-Arity Checker** (`incremental_typechecker.py`) using `ast.unparse` on parameter/return annotations, class inheritance tables, and cross-module call-site arity checks, with a clean **single-pass `1 × 71` cold-start lifecycle** (resolving `exp_hw03`'s two-pass `2 × 117` setup convention) and **`0` output mismatches** across all `10` blocks and `7` churn levels.
2. **SHA-256 Sealed Preregistration Before Execution:**
   - Before executing a single trial of `run_exp_hw04.py`, `preregister_predictions.py` generated and sealed **two prospective models** into `results/preregistered_predictions.json`:
     - **Model 1 (`ZERO_SHOT_EXP03`):** Zero hardware measurements on `_pytest` or the new typechecker; uses frozen `J/KiB` and per-edit overhead constants strictly from `exp_hw03_summary.json` multiplied by `_pytest`'s static source KiB.
     - **Model 2 (`PRIMITIVE_5TERM_PROSPECTIVE`):** Implements $E_{\text{reuse}} = E_{\text{dispatch}} + E_{\text{validation}} + E_{\text{execution}} + E_{\text{memory}} + E_{\text{maintenance}}$, calibrating its 5 primitives strictly on an isolated `8`-module micro-probe (`0` runs on the full `71`-module corpus or any churn rate $q$).
   - `run_exp_hw04.py` verified the preregistration SHA-256 seal both **before** and **after** running the 10-block benchmark and scored both models with **zero refitting**.

---

## 2. Prospective Predictions vs. Measured Hardware Reality (`N = 10` Paired Blocks)

### 2.1 Three-Way Full-Lifecycle Comparison (`5` edits, `q = 0.20`, `N = 10` blocks, `0` mismatches)
- `certified_type_canary` vs `full_typecheck`: Process CPU PMU **`+76.46 ± 6.84%`**, Whole-SoC Package **`+76.92 ± 6.24%`**.

### 2.2 Full-Lifecycle 7-Point Churn Sweep (`20` edits + `71`-module cold start, `N = 10` blocks)

| API-Breaking Rate $q$ | Pred M2 Proc (%) | **Measured Proc CPU PMU (%)** | Pred M2 Whole-SoC (%) | **Measured Whole-SoC Package (%)** | Whole-SoC $p$-value |
|---:|---:|---:|---:|---:|---:|
| `0.00` *(private refactors)* | `+89.20%` | **`+89.18 ± 0.79%`** | `+89.20%` | **`+88.96 ± 1.39%`** | `< 1e-5` |
| `0.10` | `+78.82%` | **`+79.06 ± 4.53%`** | `+78.82%` | **`+79.20 ± 5.01%`** | `< 1e-5` |
| `0.25` | `+68.74%` | **`+69.23 ± 6.16%`** | `+68.74%` | **`+68.99 ± 6.31%`** | `< 1e-5` |
| `0.50` | `+39.14%` | **`+39.05 ± 7.83%`** | `+39.14%` | **`+40.76 ± 10.10%`** | `0.0001` |
| `0.75` | `+18.90%` | **`+18.88 ± 7.03%`** | `+18.90%` | **`+21.15 ± 7.23%`** | `0.0002` |
| `0.90` *(boundary)* | `+11.14%` | **`+10.68 ± 5.86%`** | `+11.14%` | `+7.23 ± 9.80%` | `0.1276` *(boundary)* |
| `1.00` *(100% API breaks)* | `-0.07%` | **`-0.24 ± 0.44%`** | `-0.07%` | **`-0.94 ± 4.19%`** | `0.6942` *(negative bound)* |

### 2.3 Strict Prospective Accuracy Scores (Zero Post-Hoc Refitting)

| Frozen Prospective Model | Energy Boundary | Prospective $R^2_{\text{Joules}}$ | Prospective $R^2_{\%}$ | MAE (Joules) | MAE (pct-pts) | Obs/Pred Scale Ratio |
|---|---|---:|---:|---:|---:|---:|
| **Model 1 (`ZERO_SHOT_EXP03`)** | Process CPU PMU | `+0.8112` | **`+0.9999`** | `1.645 J` | **`0.33 pp`** | `0.787x` |
| **Model 1 (`ZERO_SHOT_EXP03`)** | Whole-SoC Package | **`-0.5450`** *(fails abs J!)* | `+0.9639` | `11.691 J` | `6.06 pp` | `0.533x` |
| **Model 2 (`5-Term Primitive`)** | Process CPU PMU | **`+0.9997`** | **`+0.9999`** | **`0.071 J`** | **`0.21 pp`** | **`1.009x`** |
| **Model 2 (`5-Term Primitive`)** | Whole-SoC Package | **`+0.9610`** | **`+0.9969`** | **`2.097 J`** | **`1.36 pp`** | **`1.135x`** |

---

## 3. Core Scientific Finding: What Transfers Zero-Shot vs. What Requires Primitive Calibration

Comparing Model 1 against Model 2 prospectively yields a crisp, actionable law for hardware energy transfer:

1. **Fractional energy savings (%) transfer zero-shot across codebases and algorithms** (Model 1: `MAE = 0.33 pp`, `R²_% = 0.9999` on Process CPU; `MAE = 6.06 pp`, `R²_% = 0.9639` on Whole-SoC) because per-KiB execution cost cancels between numerator and denominator whenever canary overhead is small relative to avoided downstream analysis.
2. **Absolute physical Joules do NOT transfer zero-shot across different algorithms or ambient SoC states** (Model 1 fails on Whole-SoC absolute Joules: `R²_J = -0.545`, `obs/pred = 0.533x`) because `exp_hw03`'s stdlib complexity walk under higher ambient load (`0.00490 J/KiB` SoC) differed by ~`2x` from `_pytest`'s typechecker (`0.00230 J/KiB` SoC).
3. **A tiny 8-module, 5-component primitive microprobe (Model 2) restores exact prospective Joule prediction across BOTH boundaries without running the full workload:** Process CPU jumps to **$R^2_{\text{Joules}} = +0.9997$ (`MAE = 0.071 J`, `0.21 pp`)**, and Whole-SoC Package jumps from `R² = -0.545` to **$R^2_{\text{Joules}} = +0.9610$ (`MAE = 2.10 J`, `1.36 pp`)**!

---

## 4. Remaining Boundaries & Gate Status

- **Still experimentally mutated edits:** The `_pytest` source code (`71` modules, `310` edges) is 100% real independently authored code, while the 20-edit churn streams remain controlled experimental constructions (not yet uncontrolled historical Git commit logs).
- **Still single hardware architecture & SoC-internal telemetry:** Whole-SoC `IOReport` excludes AC wall-plug power and discrete SSD rails, and cross-architecture validation (Intel/AMD RAPL) remains open. Accordingly, Paper I's `energy_focused_paper` release gate in `papers/01-certified-reuse/paper.yaml` remains honestly **`ready: false`**.

---

## 5. Independent Methodological Audit (`results/exp_hw04_audit.json`)

To address the four critical validity questions before citing `exp_hw04` externally, we audited the sealed artifacts read-only via `audit_exp_hw04.py`:

### Q1. Preregistration Independence & Shared-Seed Sensitivity Disclosure
- **Disclosure:** `preregister_predictions.py` ran **zero** hardware trials on the 71-module `_pytest` corpus or churn sweep (so physical scaling and Joule/SoC predictions were genuinely prospective and sealed before execution). However, `_compute_static_workload_expectations` evaluated `expected_avoided_kib` on the **same 10 static RNG seeds** (`7000 + int(q*100)*100 + b*29`) later run by `run_exp_hw04.py`, eliminating seed-to-seed fanout stochasticity from the conditional-schedule scores (`MAE = 0.21 pp`).
- **Strictly Blind Unseen-Schedule Check (ZERO seed sharing):** Replacing exact-seed `expected_avoided_kib` with the corpus population mean fanout (`E[avoided_kib | q] = (1 - q) * 20 * mean_downstream_kib`, zero knowledge of the 10 execution seeds) preserves strong prospective accuracy:
  - **Model 2 (`5-Term Primitive`, Strictly Blind):** Process CPU **$R^2_{\text{Joules}} = 0.9869$** (`MAE = 0.430 J`, **`2.08 pp`**); Whole-SoC Package **$R^2_{\text{Joules}} = 0.9450$** (`MAE = 2.252 J`, **`1.48 pp`**).
  - **Model 1 (`Zero-Shot`, Strictly Blind):** Process CPU **`R²_% = 0.9937`** (`MAE = 2.07 pp`), confirming the dimensionless fractional savings transfer even under strictly blind expectations.
- **Protocol Hardening:** Our frozen protocol (`protocols/prospective-energy-protocol-v1.md`) explicitly bans sharing execution RNG seeds between preregistration and evaluation.

### Q2. Calibration Energy Cost & Payback ($N^*_{\text{cal}}$)
- Model 2's 8-module micro-probe (`1` warm-up + `3 × 12` execution reps + `3 × 120 × 8` validation reps) consumed **`7.267 J` (Process CPU)** and **`17.406 J` (Whole-SoC Package)**.
- Subsequent 20-edit runs required to repay calibration energy: **`N*_cal = 1` run** at `q = 0.00–0.25`, **`2` runs** at `q = 0.50`, **`3` runs** at `q = 0.75`, and **`5` (CPU) / `6` (Whole-SoC) runs** at `q = 0.90`.

### Q3. Equal-Work Symmetry
- Both `strong_incremental_dag` and `certified_type_canary` execute identical `1 × 71` cold starts, identical AST/type-interface/arity checking, and share the same precomputed acyclic import graph (`0` output mismatches across every block).

### Q4. Hardware & Workload Boundaries
- Validated on a single Apple M3 Max (AC Power, Python `3.11.7`). Cross-architecture RAPL, true wall-plug AC metering, discrete SSD rails, and uncontrolled historical Git commits remain open requirements.

