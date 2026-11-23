"""Automated verification tests for exp_hw05 Predictive Temporal Energy Router."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = REPO_ROOT / "experiments" / "hw_energy_router_exp05"
RES_DIR = EXP_DIR / "results"


def test_exp_hw05_router_integrity_accuracy_and_honest_calibration_accounting() -> None:
    sum_p = RES_DIR / "exp_hw05_summary.json"
    seal_p = RES_DIR / "sealed_router_decisions.json"
    assert sum_p.exists() and seal_p.exists()
    assert (EXP_DIR / "REPORT.md").exists()
    assert (RES_DIR / "fig1_router_cumulative_energy_and_payback.png").exists()
    assert (RES_DIR / "fig2_router_regret_and_quadrants.png").exists()

    summary = json.loads(sum_p.read_text(encoding="utf-8"))
    sealed = json.loads(seal_p.read_text(encoding="utf-8"))
    recomputed = hashlib.sha256(
        json.dumps(sealed["decisions"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert recomputed == sealed["sha256"] == summary["sealed_decisions_sha256"]

    assert summary["strict_blind_disjoint_seeds"] is True
    assert summary["n_unseen_tasks"] == 24
    assert summary["mismatches_total"] == 0

    proc = summary["policy_comparison"]["proc_cpu_energy_j"]
    soc = summary["policy_comparison"]["soc_package_j"]

    # High routing accuracy across genuinely competing portfolio (both strategies win >= 6 tasks)
    assert proc["oracle_true_reuse_count"] >= 6 and proc["oracle_true_inc_count"] >= 6
    assert proc["router_selection_accuracy"] >= 0.80
    assert soc["router_selection_accuracy"] >= 0.75

    # Execution-only router beats both fixed baselines on Process CPU regret
    assert proc["router_exec_only"]["regret_vs_oracle_j"] < proc["always_incremental"]["regret_vs_oracle_j"]
    assert proc["router_exec_only"]["regret_vs_oracle_j"] < proc["always_reuse"]["regret_vs_oracle_j"]

    # Full-lifecycle router (including E_cal) beats always_incremental on BOTH CPU and Whole-SoC
    assert proc["router_with_cal"]["total_energy_j"] < proc["always_incremental"]["total_energy_j"]
    assert soc["router_with_cal"]["total_energy_j"] < soc["always_incremental"]["total_energy_j"]

    # Explicit honest accounting: calibration energy is positive and charged in full
    assert proc["calibration_energy_j"] > 5.0
    assert soc["calibration_energy_j"] > 10.0
