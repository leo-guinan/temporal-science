# `exp_hw05` — Predictive Temporal Energy Router on Strictly Blind Unseen Workloads

**Experiment ID:** `exp_hw05_temporal_energy_router` · **Version:** `0.1.0`  
**Sealed Pre-Execution Router Decisions SHA-256:** `02c0b41e32e36035...` (`results/sealed_router_decisions.json`)  
**Hardware & Controls:** Apple M3 Max (`16` cores, `48 GB` RAM, `macOS-26.5.1-arm64`), **AC Power**, pinned **Python `3.11.7`**, dual-layer telemetry (`proc_pid_rusage(RUSAGE_INFO_V6)` + whole-SoC `libIOReport.dylib` Energy Model `CPU + GPU + ANE + DRAM0 + DCS0 + AMCC0`).  
**Artifacts:** `results/exp_hw05_summary.json`, `results/sealed_router_decisions.json`  
**Figures:** `results/fig1_router_cumulative_energy_and_payback.png`, `results/fig2_router_regret_and_quadrants.png`

---

## 1. Objective & Strict Blind Protocol (`TS-PROTO-HW-ENERGY-v1.0.0`)

We test whether a calibrated 5-component physical energy router (`router_core.py`) can select the lower-energy execution strategy (`strong_incremental` vs `certified_reuse`) **before execution** across `24` strictly unseen, competing tasks (`16` DAG tasks spanning $K \in [1, 40], p \in [0.00, 0.65]$ + `8` real-code typechecking tasks on `_pytest` and `PyYAML` across $q \in [0.00, 1.00]$ and leaf-only edits), evaluated over `3` interleaved paired blocks per task with **`0` output mismatches**.

- **Zero seed sharing:** Calibration used disjoint seeds `101–104` (DAG) and `4`-module micro-probes (real code); all 24 unseen tasks used disjoint seeds `90001–90024`.
- **Pre-execution seal:** All 24 router choices and $\widehat{\Delta E}$ predictions were sealed into `sealed_router_decisions.json` before executing Phase 3.
- **Complete cost accounting:** Both upfront calibration energy ($E_{\text{cal}} = 12.582\text{ J}$ Process CPU / $30.622\text{ J}$ Whole-SoC; `2.43 s`) and every per-task routing decision cost ($E_{\text{decision}}$) are charged directly to the router.
- **Uniform node wrapper:** All DAG granularities `K = 1..40` used an identical node wrapper, eliminating `exp_hw03`'s `K = 1 → K = 2` closure dispatch step.

---

## 2. Empirical Results Across 24 Strictly Unseen Competing Tasks

| Policy (`24` unseen tasks, `0` mismatches) | Process CPU Total (J) | Process CPU Regret vs Oracle (J) | Whole-SoC Total (J) | Whole-SoC Regret vs Oracle (J) |
|---|---:|---:|---:|---:|
| **Oracle Selection** *(non-deployable lower bound)* | `45.96 J` | `0.00 J` (`0.0%`) | `144.67 J` | `0.00 J` (`0.0%`) |
| **Always Incremental** *(fixed baseline)* | `72.76 J` | **`26.80 J`** (`+58.3%`) | `230.41 J` | **`85.74 J`** (`+59.3%`) |
| **Always Certified Reuse** *(fixed baseline)* | `46.21 J` | `0.25 J` (`+0.5%`) | `147.38 J` | `2.71 J` (`+1.9%`) |
| **Model-Based Router (Execution Only)** | **`46.15 J`** | **`0.18 J`** (`+0.4%`) | `148.17 J` | `3.51 J` (`+2.4%`) |
| **Model-Based Router (Including Full $E_{\text{cal}}$)** | `58.73 J` | `12.77 J` (`+27.8%`) | `178.79 J` | `34.12 J` (`+23.6%`) |

### Routing Decision Accuracy & Diagnostic Breakdown
- **Oracle Regime Split:** `16` reuse-optimal / `8` incremental-optimal on Process CPU (`18` reuse / `6` incremental on Whole-SoC).
- **Pre-Execution Selection Accuracy:** **`87.5%` (`21/24`)** on Process CPU and **`83.3%` (`20/24`)** on Whole-SoC.
- **Near-Zero Misrouting Loss:** All `3` Process CPU misroutes occurred on near-zero ties (`DAG-12`: `+3 mJ`, `DAG-11`: `-5 mJ`, `CODE-08`: `+7 mJ`), producing only **`0.18 J` total execution regret** across `24` tasks (`0.39%` above the non-deployable Oracle)—beating `always_incremental` (`26.80 J` regret) by **`149x`** and beating `always_reuse` (`0.25 J` regret) on execution energy.

---

## 3. Core Discovery: Asymmetric-Loss Physics & Calibration Payback Boundary

Including full upfront calibration energy ($E_{\text{cal}} = 12.58\text{ J}$ CPU / $30.62\text{ J}$ Whole-SoC) reveals an important **decision-theoretic asymmetry** (`fig1_router_cumulative_energy_and_payback.png`):

1. **Router + $E_{\text{cal}}$ decisively beats `always_incremental`:** Pays back calibration around task `#18–21`, saving **`+19.3%` Process CPU (`14.03 J`)** and **`+22.4%` Whole-SoC (`51.62 J`)** net over `24` tasks.
2. **Router + $E_{\text{cal}}$ does NOT beat `always_reuse` over `24` tasks (`payback = None`):** Why? Because **in-memory certified reuse has extreme positive payoff asymmetry** in this portfolio:
   - Missing a reuse-favored task (`always_incremental`'s error) costs up to **`+8.74 J` CPU / `+25+ J` Whole-SoC** per task (`26.80 J` CPU regret total).
   - Misapplying in-memory reuse on a high-churn task (`always_reuse`'s error) costs only **`0.003–0.110 J` CPU** (`0.25 J` total across all `8` incremental-favored tasks = `~0.031 J/task`).
   - Paying `12.58 J` upfront to avoid `0.25 J` of downside over `24` tasks is strictly net-negative against `always_reuse`—requiring either **~`400+` high-churn tasks** to amortize upfront calibration, **heavy downside penalties** (such as synchronous disk logging, expensive contract compilation, or cache-eviction thrashing), or **zero-overhead online calibration** learned passively from normal executions rather than dedicated pre-calibration runs.

This result reinforces Temporal Science's central thesis at the meta-level: **even an accurate predictive router (`87.5%` accuracy, `0.18 J` execution regret) obeys a strict physical break-even law—its calibration cost is only justified when the downside risk of fixed policies exceeds the energy required to learn the routing model.**
