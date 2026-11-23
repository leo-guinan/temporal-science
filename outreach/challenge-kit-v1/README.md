# Challenge the Temporal Energy Model — External Replication Kit (`v1.1.0`)

**Core Falsifiable Question:**
> *Does our five-term physical energy prediction model ($E_{\text{reuse}} = E_{\text{dispatch}} + E_{\text{validation}} + E_{\text{execution}} + E_{\text{memory}} + E_{\text{maintenance}}$) continue to predict energy savings and break-even churn when an independent researcher chooses the codebase, edit stream, and hardware?*

You do **not** need to accept the broader Temporal Science framework to run this challenge. This kit has **zero third-party dependencies** (Python 3.10+ standard library only) and runs directly on **any Python repository on your machine**.

---

## 1. Quickstart (5–15 Minutes, Zero `pip install`)

### Step 1 — Strictly Blind Preregistration (Seals SHA-256)
Runs a disjoint `<= 10%` primitive micro-probe and seals `challenge_preregistration.json` using ONLY static repository summary statistics (**zero shared execution seeds**):

```bash
python3 challenge_runner.py \
  --repo /path/to/your/python/repo \
  --phase preregister \
  --out ./my_challenge_run \
  --blocks 10 \
  --edits 20
```

### Step 2 — Independent Blind Evaluation (Choose Any of 3 Modes)

1. **Real Uncontrolled Git Commit History (Strongest External Test — Independent Generator!):**
   Replays the actual last `N` historical Git commits touching `.py` files in your repository (`0`-mismatch verified):
   ```bash
   python3 challenge_runner.py \
     --repo /path/to/your/git/python/repo \
     --phase evaluate \
     --out ./my_challenge_run \
     --git-history 25
   ```

2. **Researcher-Supplied External Edit Stream (`--edits-json`):**
   Supply your own JSON array `[{"module": "<mod_name>", "new_source": "..."}, ...]` produced by any external tool or fuzzer:
   ```bash
   python3 challenge_runner.py \
     --repo /path/to/your/python/repo \
     --phase evaluate \
     --out ./my_challenge_run \
     --edits-json ./my_custom_edits.json
   ```

3. **Experimentally Mutated Blind Churn Sweep (Fresh Unseen `--seed`):**
   ```bash
   python3 challenge_runner.py \
     --repo /path/to/your/python/repo \
     --phase evaluate \
     --out ./my_challenge_run \
     --seed 424242
   ```

---

## 2. Explicit Telemetry Boundaries & Linux RAPL Handling

Every output JSON records a structured `telemetry` block that **never conflates process-attributed CPU energy, package RAPL counters, and AC wall-plug power**:

- **`process_attributed_cpu_pmu` (macOS Apple Silicon):** Uses `proc_pid_rusage(RUSAGE_INFO_V6)` (`ri_energy_nj`, retired instructions, cycles; zero `sudo`). Explicitly tagged `"is_wall_plug_energy": false, "includes_dram": false`.
- **`package_rapl_hardware` (Linux Intel/AMD):** Auto-discovers all `/sys/class/powercap/intel-rapl*` domains, records each domain's `name` (`package-0`, `dram`, `core`) and `max_energy_range_uj`, computes exact modular counter-rollover deltas `(max_range - start) + end` without double-counting subdomains inside packages, and explicitly logs `PermissionError` paths on hardened kernels before falling back cleanly. Explicitly tagged `"is_wall_plug_energy": false`.
- **`wall_cpu_time_only` (Fallback / External Wall-Plug Meter):** Records wall-clock and CPU time plus exact UTC ISO timestamps (`start_utc`, `end_utc`) for aligning an external AC wall-plug or USB-C wattmeter log.

---

## 3. What Would Falsify or Narrow Our Model?

We publish confirmations, narrowings, and falsifications with equal weight:
1. **Real-History / Custom-Stream Failure:** Real Git commits (`--git-history`) or external edits (`--edits-json`) where realized savings diverge substantially from sealed primitive predictions or where calibration fails to pay back.
2. **Cross-Architecture / Wall-Plug Divergence:** Linux RAPL or external AC wall-plug wattmeter measurements overturning the Apple Silicon energy savings trend.
3. **Blind Churn Failure:** Strict-blind prospective $R^2 < 0.70$ or $\text{MAE} > 10$ percentage points on a real multi-module codebase.

Full formal protocol rules are frozen in `prospective-energy-protocol-v1.md` included in this archive.
