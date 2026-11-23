"""Automated verification tests for exp_hw03 Physical Break-Even and Real-World AST Transfer."""

from __future__ import annotations

from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = REPO_ROOT / "experiments" / "hw_soc_breakeven_exp03"
RES_DIR = EXP_DIR / "results"


def test_exp_hw03_outputs_oos_accuracy_and_real_ast_savings() -> None:
    sum_path = RES_DIR / "exp_hw03_summary.json"
    raw_path = RES_DIR / "exp_hw03_raw_blocks.json"
    assert sum_path.exists() and raw_path.exists()
    assert (EXP_DIR / "REPORT.md").exists()
    for fig in (
        "fig1_dense_k_transition_and_model.png",
        "fig2_real_stdlib_ast_transfer.png",
        "fig3_oos_prediction_diagnostics.png",
    ):
        assert (RES_DIR / fig).exists(), f"Missing figure {fig}"

    data = json.loads(sum_path.read_text(encoding="utf-8"))
    assert data["n_blocks"] >= 8
    assert "AC Power" in data["system_context_start"]["pmset_batt"]

    # Part A: Out-of-sample predictive model accuracy on held-out K
    ev_proc = data["part_a_predictive_model"]["proc_cpu_energy_j"]["out_of_sample_eval"]
    ev_soc = data["part_a_predictive_model"]["soc_package_j"]["out_of_sample_eval"]
    assert ev_proc["r2_joules"] > 0.90
    assert ev_soc["r2_joules"] > 0.65
    assert ev_proc["sign_accuracy"] == 1.0
    assert ev_soc["sign_accuracy"] == 1.0

    # Part B: Real-world 117-module Python stdlib AST workload (0 mismatches, strong whole-SoC win, q=1 negative)
    part_b = data["part_b_real_stdlib_ast"]
    assert part_b["corpus"]["num_modules"] >= 100
    assert part_b["corpus"]["mismatches_total"] == 0
    assert part_b["five_edit_full_rebuild_comparison"]["canary_vs_full_rebuild"]["soc_package_j"]["paired_pct_mean"] > 75.0

    by_q = {r["api_break_prob"]: r for r in part_b["api_break_sweep_20_edits_full_lifecycle"]}
    assert by_q[0.0]["paired_vs_incremental"]["soc_package_j"]["paired_pct_mean"] > 50.0
    assert by_q[0.25]["paired_vs_incremental"]["soc_package_j"]["significant_005"] is True
    assert by_q[0.75]["paired_vs_incremental"]["soc_package_j"]["significant_005"] is True
    assert by_q[1.0]["paired_vs_incremental"]["proc_cpu_energy_j"]["paired_pct_mean"] < 0.0

    # Out-of-domain transfer R^2 on real stdlib AST
    assert data["part_b_transfer_model"]["proc_cpu_energy_j"]["out_of_sample_r2"] > 0.95
    assert data["part_b_transfer_model"]["soc_package_j"]["out_of_sample_r2"] > 0.55
