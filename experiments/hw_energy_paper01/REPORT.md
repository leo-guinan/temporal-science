# Hardware-Metered Temporal-Advantage Benchmark — Paper I (`exp_hw01`)

**Date:** November 22, 2026  
**Hardware:** Apple M3 Max (`16` logical cores, `48.0 GB` RAM, `macOS-26.5.1-arm64`, Python `3.11.7`)  
**Telemetry API:** macOS XNU `proc_pid_rusage(os.getpid(), RUSAGE_INFO_V6)` (`ri_energy_nj`, `ri_penergy_nj`, `ri_instructions`, `ri_cycles`, `ri_user_time`, `ri_system_time`, `ri_logical_writes`, `ri_diskio_byteswritten`)  
**Data:** `results/hw_energy_summary.json`  
**Figures:** `results/hw_energy_regime_comparison.png`, `results/hw_energy_crossover_and_granularity.png`  
**Reference Code:** Read-only `../living-computation/core/` (zero bytes modified)

---

## 1. Measurement Scope & Metrological Honesty

- **What this measures directly on silicon:** Per-process Apple M3 Max CPU hardware PMU energy (`ri_energy_nj` / `ri_penergy_nj`, ~99.99% P-core), hardware retired instructions (`ri_instructions`), hardware clock cycles (`ri_cycles`), wall/user/kernel time, and OS disk write bytes. Every trial runs after a discarded warm-up pass, with `gc.collect()`, randomized variant order per trial to prevent thermal/DVFS ordering bias, and exact `0`-mismatch verification against `FullRecomputeEngine`.
- **Linearity calibration (`1x / 2x / 4x` deterministic loop):** Hardware instructions scaled `4.0026x` (`4x/1x`); hardware CPU energy scaled `3.9095x` (`4x/1x`, `~5.3–6.2 W` P-core dynamic power).
- **What this does NOT measure (explicit boundary):** `proc_pid_rusage` captures per-process CPU core + kernel-syscall CPU energy, **not** off-package SSD flash controller rail power, external DRAM rail power, or AC wall-plug power. Because of that boundary, Paper I's `energy_focused_paper` release gate remains **blocked** until full-package/DRAM/SSD metering (e.g., `sudo powermetrics --samplers cpu_power,gpu_power,ane_power` or Intel RAPL / external wattmeter) and non-synthetic workload replication are added.

---

## 2. Experiment HW-1 — Exact Unmodified Paper I 1,000-Node DAG Across All 4 Regimes

**Setup:** Exact unmodified Paper I DAG (`1,000` nodes, `2,167` edges, `120` inputs, depth `25`), `10,000` updates per regime, `N = 5` interleaved randomized trials, **`0` mismatches across all trials**.

| Regime & Variant (vs Strong Incremental unless noted) | Abstract Ops Savings | Modeled Proxy J Savings | **M3 Max HW Energy (`ri_energy_nj`) Savings** | HW Retired Instructions Savings | Wall-Clock Savings | Mean HW Energy ± 95% CI (J) |
|---|---:|---:|---:|---:|---:|---:|
| `localized_regime_drift` — In-Mem Surprise **(vs Full)** | **+93.63%** | +91.54% | **+90.98%** | +92.33% | +89.72% | `2.018 ± 0.031` vs `22.382 ± 0.049` |
| `localized_regime_drift` — In-Mem Surprise (vs Inc) | +15.32% | +8.82% | **+9.33%** | **+17.49%** | +1.01% | `2.018 ± 0.031` vs `2.226 ± 0.013` |
| `localized_regime_drift` — In-Mem Delta (vs Inc) | +14.20% | +10.02% | **+8.51%** | +15.89% | +2.62% | `2.036 ± 0.031` vs `2.226 ± 0.013` |
| `localized_regime_drift` — **Disk JSONL Surprise** (vs Inc) | +15.32% | `-1.43%` | **`+1.60%`** *(83% erased!)* | +11.50% | **`-6.76%`** | `2.190 ± 0.005` (`1.53 MiB` disk writes) |
| `drift_and_regime_shift` — In-Mem Surprise (vs Inc) | +15.48% | +11.49% | **+12.73%** | +19.72% | +4.08% | Positive & non-overlapping CI |
| `recurring_states` — Multi-Anchor Atlas (vs Inc) | `-3.18%` | `-9.52%` | **`-3.80%`** | +6.91% | `-12.6%` | Negative (matches op-count sign) |
| `high_entropy_shock` — Static (vs Inc) | `-47.5%` | `-23.7%` | **`-18.52%`** | `-9.5%` | `-25.1%` | Failure boundary |
| `high_entropy_shock` — Adaptive Retirement (vs Inc) | `-1.8%` | `-21.7%` | **`-17.85%`** | `-12.3%` | `-22.4%` | **Key silicon finding (see below)** |

### Three Key Microarchitectural Findings from HW-1

1. **Real silicon energy savings exceed wall-clock savings at fine granularity (`K = 1`):** On `localized_regime_drift`, wall-clock time barely moved (`+1.01%`, `0.416 s → 0.412 s`) because canary dict/boundary checks lowered IPC from `5.15` to `4.32`. Yet **real Apple M3 Max hardware CPU energy dropped `+9.33%`** (`2.226 ± 0.013 J` → `2.018 ± 0.031 J`, non-overlapping 95% CIs) because `-17.49%` fewer retired instructions lowered average P-core dynamic power from `5.35 W` to `4.90 W` (`-8.4%`). Timing wall-clock seconds alone would have masked this physical energy reduction.
2. **Disk logging energy collapse confirmed on real hardware:** Synchronous disk JSONL trace persistence wrote `1.53 MiB` (`1,605,632 B` disk writes), left abstract ops untouched at `+15.32%`, slowed wall time to `-6.76%`, and collapsed CPU hardware energy advantage from `+9.33%` down to `+1.60%`—**before** even accounting for off-package SSD flash controller power.
3. **Adaptive retirement limitation exposed by real silicon:** Under `high_entropy_shock`, retiring contracts eliminated most abstract contract-check ops (`-47.5% → -1.8%`), yet real hardware CPU energy improved only from `-18.52%` to `-17.85%` because the Python surprise-tracking and ledger bookkeeping loop remained active. Reducing high-entropy hardware overhead requires short-circuiting trace/surprise instrumentation itself once volatility crosses threshold.

---

## 3. Experiment HW-2 — Physical-Energy vs. Operation-Count Shock Crossover

**Setup:** `localized_regime_drift` with shock probability $p \in \{0.00, 0.02, 0.05, 0.08, 0.10, 0.15, 0.30, 0.60\}$, `3,000` updates × `3` interleaved trials.

| Shock Rate $p$ | Abstract Ops (%) | Modeled Proxy J (%) | **M3 Max HW Energy (%)** | HW Retired Instructions (%) |
|---:|---:|---:|---:|---:|
| `0.00` | +25.87% | +22.80% | **+17.25%** | +23.57% |
| `0.02` | +20.43% | +17.74% | **+12.69%** | +20.27% |
| `0.05` | +12.69% | +13.55% | **+8.99%** | +15.72% |
| `0.08` | +4.37% | +3.92% | **`-0.56%`** *(crosses zero!)* | +10.61% |
| `0.10` | +1.98% | +5.50% | **`+0.24%`** *(at crossover)* | +9.15% |
| `0.15` | `-5.90%` | `-0.75%` | **`-2.30%`** | +4.70% |
| `0.30` | `-19.15%` | `-9.23%` | **`-9.83%`** | `-3.19%` |
| `0.60` | `-31.40%` | `-18.76%` | **`-17.35%`** | `-11.43%` |

**Finding:** Real hardware CPU energy crosses zero **tighter** ($p^*_{\text{phys}} \approx 0.08\text{–}0.10$) than abstract operation counts ($p^*_{\text{ops}} \approx 0.11\text{–}0.12$) and much tighter than retired hardware instructions ($p^*_{\text{inst}} \approx 0.22$). Both abstract ops and raw instruction counts overestimate physical energy headroom near the volatility boundary.

---

## 4. Experiment HW-3 — Node Compute-Granularity Scaling Law

**Setup:** `localized_regime_drift` (`3,000` updates × `3` trials) sweeping pure deterministic compute intensity per DAG node $K \in \{1, 5, 20, 80\}$ while keeping mathematical outputs and Lipschitz bounds **100% identical** (`0` mismatches; $K=1$ is the completely unmodified Paper I DAG).

| Node Compute Granularity $K$ | Abstract Ops vs Inc (%) | **M3 Max HW Energy vs Inc (%)** | HW Instructions vs Inc (%) | Wall Time vs Inc (%) | **M3 Max HW Energy vs Full (%)** |
|---:|---:|---:|---:|---:|---:|
| `K = 1` *(unmodified Paper I)* | +14.95% | **+8.27%** | +17.06% | +5.96% | **+91.06%** |
| `K = 5` | +14.95% | **+21.88%** | +25.50% | +19.14% | **+93.18%** |
| `K = 20` | +14.95% | **+29.64%** | +32.06% | +28.30% | **+94.36%** |
| `K = 80` | +14.95% | **+34.85%** | +36.49% | +32.88% | **+95.08%** |

**Finding (Granularity Inversion):** Abstract operation counting charges `1` op for a boundary canary check and `1` op for an interior node evaluation regardless of node weight. On real silicon:
- At ultra-fine scalar Python granularity (`K = 1`), Python canary/bookkeeping dispatch makes real hardware energy savings (`+8.27%`) **smaller** than abstract op savings (`+14.95%`).
- For realistic node compute density (`K >= 5`), boundary canary cost stays $O(1)$ while avoided interior node cost scales with $K$, driving real M3 Max hardware energy savings to **`+21.88%` → `+34.85%`** vs. Strong Incremental (`+93.18%` → `+95.08%` vs. Full)—**more than double** the unweighted abstract op-count prediction!

---

## 5. Companion Whole-System `powermetrics` Verification Command

To cross-check these per-process PMU measurements against whole-SoC `CPU + GPU + ANE + DRAM` power rails on macOS (requires interactive `sudo`):

```bash
sudo powermetrics --samplers cpu_power,gpu_power,ane_power -i 200 -n 60 > /tmp/powermetrics_hw01.txt &
python3 temporal-science/experiments/hw_energy_paper01/run_hw_energy_benchmark.py
```
