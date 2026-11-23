# When Does Composable Research Infrastructure Pay Back? An Empirical Break-Even Analysis of Research Coordination Costs

**Experiment ID:** `exp_crr_breakeven_v01` · **System Evaluated:** Temporal Science CRR v0.2  
**Hardware Telemetry:** Apple M3 Max (`16` cores, `48 GB` RAM, `macOS-26.5.1-arm64`), XNU `proc_pid_rusage(RUSAGE_INFO_V6)`  
**Scope Notice:** *Machine-only timing, Apple Silicon per-process CPU energy (`ri_energy_nj`), storage footprint, and automated correctness metrics are directly measured. Human researcher time is **NOT** empirically measured in this study; it is presented solely as a clearly labeled analytical parametric model pending an IRB-approved human-subject workflow study.*  
**Date:** November 22, 2026

---

## Abstract

Structured research infrastructures—executable claim graphs, versioned artifact manifests, and automated scientific CI—promise faster replication and fewer silent propagation errors. Yet formalizing research imposes concrete setup, authoring, storage, and maintenance costs. Applying the break-even discipline of Temporal Science to its own infrastructure, we evaluate **Temporal Science CRR v0.2** as an experimental subject against two fair, strong baselines holding identical underlying research content: (1) a well-organized **Conventional Repository** using regex/`grep`, Python verifiers, and tarball packaging scripts, and (2) a **Modular Manual-Manifest Repository** with hand-maintained JSON reference indices and SHA-256 inventories.

Across six standardized research coordination tasks (`T1`–`T6`), the real `16`-claim, `5`-paper Temporal Science graph, and `12` held-out synthetic research graphs spanning $V \in \{5, 16, 40, 100\}$ claims, three dependency densities, and four edit-to-reuse churn regimes ($r_{\text{edit}} \in \{0.05, 0.25, 1.0, 4.0\}$), we measure **resource-specific break-even points** without collapsing time, energy, storage, and correctness into a single unit.

Our central finding is a sharp **resource-specific split**:
1. **Pure machine-only metadata coordination (negative result):** When downstream verification executes only lightweight unit checks (`~0.001 J`), unindexed `PyYAML`-backed CRR v0.2 **never breaks even** on machine wall time, Apple M3 Max CPU energy, or disk storage at any tested scale ($N^*_{\text{time}} = N^*_{\text{energy}} = N^*_{\text{storage}} = \text{None}$). Per-reuse machine overhead scales from `31.3 ms / 149 mJ` ($V=5$) to `477.7 ms / 2,367 mJ` ($V=100$), worsening to `932.4 ms / 4,736 mJ` under high churn ($r_{\text{edit}} = 4.0$), and disk footprint increases `3.6x` (`131 KiB` vs `36 KiB` at $V=16$).
2. **Avoided upstream compute reuse (conditional machine break-even):** When importing a SHA-256 verified CRR contract replaces redundant re-execution of a real measured upstream benchmark (`2.02 J` Paper I 1,000-node DAG from `exp_hw01`), machine CPU energy breaks even at **$N^*_{\text{energy}} = 1$** ($V=16$) and **$N^*_{\text{energy}} = 8$** ($V=40$), **and then loses again at $V = 100$** (`-0.35 J/reuse`, $N^* = \text{None}$) once unindexed `PyYAML` parsing exceeds `2.02 J`—pinpointing the exact graph scale where an indexed metadata store becomes mandatory. For heavier upstream workloads (`22.38 J` Full DAG or `300 J` 1-minute benchmark), machine CPU energy breaks even immediately at $N^*_{\text{energy}} = 1$ across all $V \le 100$.
3. **Scientific correctness & defect prevention (immediate dominance):** On the real 16-claim graph, everyday single-pass `grep` achieves only **`36.4%`** transitive impact recall (dropping to **`6%–17%`** at $V=100$), and automated QA catches only **`16.7%`** (`1/6`) of injected scientific/integrity defects in the conventional baseline and **`33.3%`** (`2/6`) in the modular manual baseline—compared to **`100.0%` (`6/6`) with `0%` false positives** for CRR v0.2.

---

## 1. Introduction

Meta-research tools—FAIR data packages, RO-Crates, workflow registries, and Composable Research Repositories (CRRs)—are frequently advocated on qualitative grounds without measuring whether their adoption saves more resources than they consume. In Temporal Science, any knowledge-preservation architecture is subject to a strict break-even condition:

$$C_{\text{CRR}}(N) = C_{\text{setup}} + C_{\text{maintenance}}(N) + C_{\text{reuse}}(N) \;<\; C_{\text{baseline}}(N)$$

Because computational wall time, physical CPU energy, disk storage, scientific defect escape rate, and human researcher attention are **incommensurable resources**, collapsing them into a single dollar or score hides critical failure modes. This paper evaluates CRR v0.2 empirically across separate resource axes, explicitly documenting **where CRR loses** as well as where it wins.

---

## 2. Experimental Design and Controls

### 2.1 Three Fair Conditions (Identical Underlying Research Content)

To avoid strawman comparisons against unorganized prose dumps, all three conditions are materialized from the **exact same `ResearchGraphSpec`** holding identical proofs (`*_proof.md`), experiment JSON summaries (`*_results.json`), and executable Python verifiers (`*_verifier.py`):

1. **`conventional` (Strong Ordinary Research Repo):** Clean per-paper Markdown manuscripts (`papers/paper-*.md`) with consistent headings, explicit assumption lists, and evidence paths; operated with standard Python regex/`grep`, verifier execution, and `tarfile + hashlib` packaging scripts.
2. **`modular_manual` (Manual-Manifest Repo):** Identical papers plus manually maintained per-paper JSON artifact SHA-256 manifests (`manifests/*_manifest.json`) and a flat claim reference index (`manifests/reference_index.json`), without formal scientific-composition rules (`S1`–`S5`).
3. **`crr_v02` (Temporal Science CRR v0.2):** Executable YAML claim contracts (`research/claims/*/claim.yaml`), `paper.yaml` manifests, and the unmodified `tools/research.py` engine (`validate_repository`, `compute_impact`, `build_paper`, `verify_build`), charged in full for initial schema authoring, validation, and rebuild overhead.

### 2.2 Six Standardized Tasks (`T1`–`T6`)

- **`T1` Reproduce a published result:** Verify paper artifacts and execute paper verification scripts.
- **`T2` Locate a theorem's assumptions & evidence:** Retrieve exact assumptions, proof file, experiment data, and verifier script for a target claim.
- **`T3` Upstream update & transitive impact analysis:** Given an upstream claim edit, identify **all** transitively affected downstream claims and papers. We evaluate *both* everyday single-pass `grep` (accuracy analysis) and a strong iterative fixed-point regex scanner achieving `100%` recall (equal-outcome timing/energy baseline).
- **`T4` Detect broken dependencies & unsupported guarantees:** Run automated QA against clean repos (false-positive check) and six injected defects: `D1_MISSING_ARTIFACT`, `D2_ARTIFACT_TAMPERED` (1-byte flip), `D3_INVALIDATED_UPSTREAM`, `D4_FORMAL_STATUS_INFLATION`, `D5_ENERGY_TIER_INFLATION`, and `D6_SIMULATED_SCOPE_MISUSE`.
- **`T5` Assemble & verify a portable package:** Build a `.tar.gz` release archive, unpack it into a clean temporary directory, and verify checksums + verifiers.
- **`T6` Incorporate a new claim (maintenance charge):** Add a new claim with evidence, update references/manifests, and re-validate/rebuild—explicitly charging CRR's maintenance overhead per edit.

### 2.3 Workloads and Hardware Telemetry

- **Graphs:** (a) Real `16`-claim, `5`-paper Temporal Science graph (`5` interleaved trials); (b) Held-out `40`-claim, `10`-paper synthetic graph (`seed=7040`, `5` trials); (c) Sensitivity sweep across $V \in \{5, 16, 40, 100\}$ claims $\times$ $\{\text{sparse}, \text{medium}, \text{dense}\}$ $\times$ edit-to-reuse ratios $r_{\text{edit}} \in \{0.05, 0.25, 1.0, 4.0\}$ (`3` interleaved trials per cell).
- **Hardware Metering:** Apple M3 Max per-process hardware PMU CPU energy (`ri_energy_nj`), retired instructions, CPU cycles, and wall time via `proc_pid_rusage(RUSAGE_INFO_V6)` (linearity calibration `4x/1x = 4.001x` instructions, `3.46x–4.15x` energy; excludes off-package SSD/DRAM/AC wall rails).

---

## 3. Results

### 3.1 Setup Cost, Per-Task Cost, and Storage Overhead (Real 16-Claim, 5-Paper Graph)

| Metric (Real 16-Claim, 5-Paper Graph) | `conventional` | `modular_manual` | `crr_v02` | CRR Ratio vs Conv |
|---|---:|---:|---:|---:|
| **Setup Wall Time** ($C_{\text{setup}}$) | `6.4 ms` | `8.6 ms` | **`314.3 ms`** | `49.2x` heavier |
| **Setup M3 Max CPU Energy** ($C_{\text{setup}}$) | `35.2 mJ` | `39.4 mJ` | **`1,570.6 mJ`** | `44.7x` heavier |
| **Repository Storage Footprint** | `35.9 KiB` | `51.7 KiB` | **`131.4 KiB`** | `3.66x` (`+265.5%`) |
| **Authored Metadata Lines** | `271` | `700` | **`957`** | `3.53x` more lines |
| **`T3` Transitive Impact (Wall / Energy)** | `1.20 ms / 7.0 mJ` *(iter. grep)* | `0.2 ms / ~1 mJ` | **`23.9 ms / 118.1 mJ`** | `20x` heavier |
| **`T4` Clean Validation (Wall / Energy)** | `3.69 ms / 15.4 mJ` | `~5 ms / ~20 mJ` | **`33.6 ms / 164.2 mJ`** | `9.1x` heavier |
| **`T5` Portable Bundle (Wall / Energy)** | `15.9 ms / 55.8 mJ` | `~17 ms / ~60 mJ` | **`78.3 ms / 347.3 mJ`** | `4.9x` heavier |
| **`T6` Incorporate Claim (Wall / Energy / Lines)** | `1.23 ms / 16.2 mJ / 14 lines` | `~3 ms / ~25 mJ / 32 lines` | **`92.3 ms / 446.5 mJ / 40 lines`** | `75x` time / `28x` energy |

**Root Cause Analysis:** Profiling retired instructions confirms why pure metadata queries in CRR v0.2 are heavier than `conventional` and `modular_manual`: every CLI invocation re-parses all `16` `claim.yaml` and `5` `paper.yaml` files using pure-Python `PyYAML` (`423.6 M` instructions for `T3_impact` vs `19.2 M` for iterative regex scanning of 5 Markdown files).

### 3.2 Scientific Correctness and Defect Detection (`T3` and `T4`)

| Correctness Metric | `conventional` (Single `grep`) | `conventional` (Iter. `grep`) | `modular_manual` | **`crr_v02`** |
|---|---:|---:|---:|---:|
| **`T3` Transitive Impact Recall (Real 16-claim)** | **`36.4%`** *(4/11)* | `100.0%` *(11/11)* | `100.0%` *(11/11)* | **`100.0%`** *(11/11)* |
| **`T3` Transitive Impact Recall ($V=100$ sparse/med/dense)** | **`6% / 11% / 17%`** | `100.0%` | `100.0%` | **`100.0%`** |
| **`T4` Defect Detection (`D1`–`D6`)** | **`16.7%`** *(1/6: `D1` only)* | `16.7%` *(1/6)* | **`33.3%`** *(2/6: `D1, D2`)* | **`100.0%`** *(6/6)* |
| **`T4` False Positives on Clean Repo** | `0%` | `0%` | `0%` | **`0%`** |

As shown in `results/fig1_resource_breakeven_curves.png` (Panel D) and `results/fig3_correctness_and_parametric_human.png` (Left), neither `conventional` nor `modular_manual` detects semantic scientific-composition defects (`D3` invalidated upstream, `D4` formal status inflation, `D5` silent energy-tier inflation, `D6` simulated-to-real human scope misuse). On scientific safety, CRR breaks even at **$N^*_{\text{defect}} = 1$**.

### 3.3 Sensitivity Analysis and Explicit Negative Cases Where CRR Loses

Across all `18` cells of the sensitivity sweep (`results/fig2_sensitivity_and_negative_cases.png`), four negative regimes where CRR loses are explicitly verified:

1. **NC-1 — Pure Metadata Coordination (No Avoided Upstream Compute):** Across every graph size $V \in \{5, 16, 40, 100\}$ and density, unindexed CRR v0.2 never reaches machine wall-time or CPU-energy break-even against strong conventional tooling ($N^*_{\text{time}} = N^*_{\text{energy}} = \text{None}$). Per-reuse CPU energy deficit grows linearly with $V$: `-149 mJ` ($V=5$) → `-428 mJ` ($V=16$) → `-1,090 mJ` ($V=40$) → `-2,367 mJ` ($V=100$).
2. **NC-2 — High-Churn Exploratory Projects ($r_{\text{edit}} \gg 1$):** At $V=40$ (medium density), increasing edit-to-reuse churn from $r_{\text{edit}} = 0.05$ to $4.0$ inflates CRR's per-reuse overhead `5.3x`—from `-178.9 ms / -895.1 mJ` to **`-932.4 ms / -4,735.8 mJ`** per reuse event. Maintaining formal contracts during rapid pre-stabilization exploration is strictly net-negative.
3. **NC-3 — Single-Repository Storage Footprint:** CRR v0.2 consumes `3.6x–3.8x` more disk bytes than `conventional` (`32 KiB` vs `9 KiB` at $V=5$; `615 KiB` vs `170 KiB` at $V=100$) with no storage break-even ($N^*_{\text{storage}} = \text{None}$).
4. **NC-4 — Scale Ceiling of Unindexed `PyYAML` Even Under Real Avoided Compute:** See §3.4 below—at $V = 100$, unindexed YAML parsing (`2.37 J`) overtakes even a real `2.02 J` upstream Paper I benchmark!

### 3.4 Machine-Only Break-Even Under Real Avoided Upstream Computation (`exp_hw01` Energies)

When importing a verified CRR build replaces redundant re-execution of an upstream computational experiment (using directly measured Apple M3 Max energies from `exp_hw01`), machine-only CPU energy break-even emerges sharply (`results/fig4_avoided_compute_breakeven.png`):

| Graph Size $V$ (Med, $r_{\text{edit}}=0.25$) | CRR Metadata Overhead / Reuse | Trivial Test (`0.001 J`) | **Paper I DAG (`2.02 J`, `exp_hw01`)** | **Paper I Full DAG (`22.38 J`, `exp_hw01`)** | 1-Min Benchmark (`300 J`) |
|---:|---:|---:|---:|---:|---:|
| `V = 5` | `0.15 J` | Loses (`N*=None`) | **Wins: `+1.87 J/ev`, `N*=1`** | **Wins: `+22.23 J/ev`, `N*=1`** | **Wins: `N*=1`** |
| `V = 16` | `0.43 J` | Loses (`N*=None`) | **Wins: `+1.59 J/ev`, `N*=1`** | **Wins: `+21.95 J/ev`, `N*=1`** | **Wins: `N*=1`** |
| `V = 40` | `1.09 J` | Loses (`N*=None`) | **Wins: `+0.93 J/ev`, `N*=8`** | **Wins: `+21.29 J/ev`, `N*=1`** | **Wins: `N*=1`** |
| **`V = 100`** | **`2.37 J`** | Loses (`N*=None`) | **LOSES: `-0.35 J/ev`, `N*=None`** | **Wins: `+20.02 J/ev`, `N*=1`** | **Wins: `N*=1`** |

This reveals a concrete, actionable engineering law: **unindexed `PyYAML` CRR v0.2 breaks even on machine CPU energy whenever avoided upstream computation $E_{\text{exp}} > 0.024 \cdot V\;\text{J}$** (at $r_{\text{edit}} = 0.25$). Beyond $V \approx 85$ claims for `2 J`-class workloads, replacing on-the-fly YAML re-parsing with a cached JSON/SQLite dependency index is required to sustain machine-level energy savings.

### 3.5 Parametric Analytical Human-Time Break-Even Surface (NOT Measured Human Data)

> **Explicit Scope Boundary:** No human-subject timing data was collected in this experiment. The table below is a purely analytical parametric calculation ($N^*_{\text{human}} = \lceil H_{\text{setup}} / (\Delta h - r_{\text{edit}} \cdot h_{\text{maint}}) \rceil$ with $r_{\text{edit}} = 0.25$, $h_{\text{maint}} = 4\text{ min}$) provided so a future IRB-approved researcher study can directly calibrate empirical break-even (`results/fig3_correctness_and_parametric_human.png`, Right):

| Assumed Initial CRR Authoring Setup $H_{\text{setup}}$ | $\Delta h = 5\text{ min}$ saved/reuse | $\Delta h = 15\text{ min}$ saved/reuse | $\Delta h = 30\text{ min}$ saved/reuse | $\Delta h = 60\text{ min}$ saved/reuse |
|---|---:|---:|---:|---:|
| `30 min` | `N* = 8` | `N* = 3` | `N* = 2` | `N* = 1` |
| `60 min` | `N* = 15` | `N* = 5` | `N* = 3` | `N* = 2` |
| `120 min` | `N* = 30` | `N* = 9` | `N* = 5` | `N* = 3` |
| `240 min` | `N* = 60` | `N* = 18` | `N* = 9` | `N* = 5` |

---

## 4. Practical Guidance & Threats to Validity

### When to Adopt vs. Avoid CRR v0.2
- **Avoid CRR** during rapid single-author exploratory prototyping ($r_{\text{edit}} \gg 1$), one-off small papers with no downstream consumers ($V \le 5, N \le 3$), or pure low-compute text repositories where scientific-composition CI is unnecessary.
- **Adopt CRR** once a research program spans multiple interdependent papers ($V \ge 15$), where single-pass `grep` misses `64%–94%` of transitive dependencies, where silent status/energy/scope inflation carries real scientific risk, or where importing verified contracts avoids re-running multi-joule/multi-minute upstream experiments.

### Threats to Validity
1. **No empirical human timing:** Human break-even values in §3.5 are strictly parametric and require an IRB-approved controlled researcher study.
2. **Parser implementation dependence:** CRR v0.2's machine overhead is dominated by pure-Python `PyYAML`; a C-backed YAML (`CSafeLoader`) or cached JSON/SQLite index would cut machine overhead by an estimated `10x–50x` (left to future optimization so CRR v0.2 is evaluated unmodified).
3. **Single hardware platform & per-process energy scope:** Energy measurements come from Apple M3 Max per-process PMU (`ri_energy_nj`) and exclude off-package SSD/DRAM/AC wall power.

---

## 5. Reproduction

```bash
python3 temporal-science/experiments/crr_breakeven/run_crr_breakeven.py
pytest -q temporal-science/tests/test_crr_breakeven.py
```
