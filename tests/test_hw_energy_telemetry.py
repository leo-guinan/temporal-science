"""Verification tests for the Paper I Apple Silicon hardware-metered energy benchmark."""

from __future__ import annotations

from pathlib import Path
import json
import platform
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
HW_DIR = REPO_ROOT / "experiments" / "hw_energy_paper01"
if str(HW_DIR) not in sys.path:
    sys.path.insert(0, str(HW_DIR))


def test_hw_energy_summary_integrity_and_zero_mismatches() -> None:
    summary_path = HW_DIR / "results" / "hw_energy_summary.json"
    assert summary_path.exists(), "Run experiments/hw_energy_paper01/run_hw_energy_benchmark.py first"
    data = json.loads(summary_path.read_text(encoding="utf-8"))

    # Verify explicit measurement boundary is documented
    assert "Excludes off-package SSD" in data["machine"]["measurement_scope"]

    # Verify zero soundness mismatches across every HW-1 regime & variant
    hw1 = data["hw1_unmodified_paper01_regimes"]
    for regime, block in hw1.items():
        for sys_name, metrics in block["systems"].items():
            assert metrics["mismatches_total"] == 0, f"Soundness error in {regime}/{sys_name}"

    # Verify real hardware energy advantage on unmodified Paper I localized_regime_drift
    loc_cmp = hw1["localized_regime_drift"]["comparisons"]["living_inmem_surprise_vs_incremental"]
    assert loc_cmp["savings_hardware_energy_j_pct"] > 5.0
    assert loc_cmp["savings_instructions_pct"] > 10.0

    # Verify disk logging degrades hardware energy savings substantially relative to in-memory
    disk_cmp = hw1["localized_regime_drift"]["comparisons"]["living_disk_jsonl_vs_incremental"]
    assert disk_cmp["savings_hardware_energy_j_pct"] < loc_cmp["savings_hardware_energy_j_pct"] - 5.0

    # Verify granularity scaling increases real hardware energy savings monotonically K=1 -> K=80
    hw3 = data["hw3_node_granularity_scaling"]
    hw_j_by_k = [r["vs_incremental"]["savings_hardware_energy_j_pct"] for r in hw3]
    assert hw_j_by_k == sorted(hw_j_by_k)
    assert hw_j_by_k[-1] > hw_j_by_k[0] + 15.0

    # Verify figures exist
    assert (HW_DIR / "results" / "hw_energy_regime_comparison.png").exists()
    assert (HW_DIR / "results" / "hw_energy_crossover_and_granularity.png").exists()


def test_macos_proc_pid_rusage_telemetry_returns_positive_energy_and_instructions() -> None:
    if platform.system() != "Darwin":
        return
    import telemetry_macos as tm  # type: ignore

    s0 = tm.snapshot_raw()
    acc = sum((i * 3) ^ (i >> 1) for i in range(400_000))
    assert acc > 0
    s1 = tm.snapshot_raw()
    d = tm.delta_sample(s0, s1)
    assert d.hardware_energy_j > 0.0
    assert d.instructions > 1_000_000
    assert d.cycles > 100_000
