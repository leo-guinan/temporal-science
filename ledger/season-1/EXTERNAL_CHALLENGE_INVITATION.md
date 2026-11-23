# External Research Season 1 — Energy-Model Falsification Challenge (`v1.1.0`)

**Status:** Open for independent external runs (`v0.1.1-external-season-1`)  
**Kit:** `challenge-kit-v1.1.0.tar.gz` (Python 3.10+ stdlib only, zero `pip` installs)  
**Protocol:** `TS-PROTO-HW-ENERGY-v1.0.0` (`prospective-energy-protocol-v1.md`)

## The Question

Can a lightweight, 5-component energy model calibrated on a small disjoint micro-probe **prospectively predict** the physical energy savings (or overhead) of certified incremental reuse versus strong incremental recomputation on a codebase and hardware platform **we did not choose**?

On our own Apple M3 Max machine (AC-powered `proc_pid_rusage` + `IOReport` whole-SoC, **not** AC wall-plug energy), the blind model achieved $R^2 = 0.987$ (CPU) and $R^2 = 0.945$ (Whole-SoC) on a 71-module `_pytest` type-signature workload—while also revealing concrete failure boundaries (fine-grained `K=1` Python scalar tasks, disk logging overhead, zero-shot absolute Joules across algorithms, and router calibration payback under asymmetric loss).

That internal evidence is not independent validation. The `energy_focused_paper` and `independently_validated_release` gates remain intentionally **BLOCKED** until outside researchers test whether the model holds, narrows, or breaks on their own workloads and hardware.

## What We Are Asking You to Do (~15 Minutes)

1. **Choose your own Python repository**—ideally using its **real Git commit history** (`--git-history N`) or your own independent edit stream (`--edits-json FILE`), rather than synthetic churn.
2. **Run on your own hardware**, especially Linux Intel/AMD RAPL (`powercap`), non-M3 Apple Silicon, or a wall-plug power meter.
3. **Try to break the model.** Look for workloads, churn patterns, cache regimes, or hardware telemetry scopes where predictions diverge from measured energy.

```bash
tar -xzf challenge-kit-v1.1.0.tar.gz
cd challenge-kit-v1.1.0

# 1. Inspect available telemetry & verify energy accounting scope on your machine
python3 challenge_runner.py --probe-only

# 2. Run a blind prospective test against a real Git history on a repo you choose
python3 challenge_runner.py \
  --target-dir /path/to/your/python-repo \
  --git-history 10 \
  --output results_external.json
```

## Negative Results Count as Contributions

Every valid run—whether it **confirms** predictive accuracy on new hardware, **narrows** the validity regime, **falsifies** the 5-term model outright, or exposes a **protocol flaw**—will be recorded transparently in the public Season 1 observation ledger (`ledger/season-1/energy-challenge.json`) with full attribution to the contributor.
