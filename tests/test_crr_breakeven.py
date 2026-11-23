"""Automated verification tests for the CRR Research Coordination Break-Even experiment."""

from __future__ import annotations

from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = REPO_ROOT / "experiments" / "crr_breakeven"
RES_DIR = EXP_DIR / "results"


def test_crr_breakeven_summary_and_figures_exist_and_verify_core_findings() -> None:
    summary_path = RES_DIR / "crr_breakeven_summary.json"
    assert summary_path.exists(), "Run experiments/crr_breakeven/run_crr_breakeven.py first"
    data = json.loads(summary_path.read_text(encoding="utf-8"))

    # 1. Verify all 4 figures & scoped manuscript exist
    for fname in (
        "fig1_resource_breakeven_curves.png",
        "fig2_sensitivity_and_negative_cases.png",
        "fig3_correctness_and_parametric_human.png",
        "fig4_avoided_compute_breakeven.png",
    ):
        assert (RES_DIR / fname).exists(), f"Missing figure {fname}"
    assert (EXP_DIR / "manuscript.md").exists()

    # 2. Verify real Temporal Science 16-claim correctness metrics
    real = data["real_temporal_science_suite"]
    assert real["num_claims"] == 16
    assert real["num_papers"] == 5
    assert real["t3_impact_accuracy"]["conventional_single_grep"]["recall"] < 0.5
    assert real["t3_impact_accuracy"]["conventional_iterative_grep"]["recall"] == 1.0
    assert real["t3_impact_accuracy"]["crr_v02"]["recall"] == 1.0

    t4 = real["t4_defect_detection"]
    assert t4["conventional"]["detection_rate"] < 0.3
    assert t4["modular_manual"]["detection_rate"] < 0.5
    assert t4["crr_v02"]["detection_rate"] == 1.0
    assert t4["crr_v02"]["false_positive_on_clean"] is False

    # 3. Verify explicit negative cases are recorded honestly
    # NC-1: Pure metadata machine-only break-even is None at V=16 and V=40
    assert data["real_temporal_science_breakeven"]["breakeven_crr_vs_conventional"]["hardware_energy_j"]["n_star"] is None
    assert data["heldout_40c_breakeven"]["breakeven_crr_vs_conventional"]["hardware_energy_j"]["n_star"] is None

    # NC-3: CRR storage footprint strictly exceeds conventional
    st = data["real_temporal_science_breakeven"]["storage_overhead"]
    assert st["crr_v02_bytes"] > st["conventional_bytes"]
    assert st["n_star_storage"] is None

    # NC-2: High churn (r_edit=4.0) strictly worsens per-event energy deficit vs low churn (r_edit=0.05) at V=40
    v40_churn = {
        r["edit_to_reuse_ratio"]: r["energy_saving_per_event_mj"]
        for r in data["sensitivity_sweep"]
        if r["num_claims"] == 40 and r["density"] == "medium"
    }
    assert v40_churn[4.0] < v40_churn[0.05]

    # 4. Verify avoided-compute regime exhibits real break-even at V=16/40 for 2.02 J and loses at V=100
    ac = {(r["num_claims"], r["workload"]): r for r in data["avoided_compute_regime"]}
    assert ac[(16, "paper01_dag_2J_measured")]["crr_wins_on_machine_energy"] is True
    assert ac[(40, "paper01_dag_2J_measured")]["crr_wins_on_machine_energy"] is True
    assert ac[(100, "paper01_dag_2J_measured")]["crr_wins_on_machine_energy"] is False
    assert ac[(100, "paper01_full_22J_measured")]["n_star_energy"] == 1

    # 5. Verify human surface is explicitly labeled analytical-only (never conflated with measured human data)
    assert "NOT MEASURED HUMAN DATA" in data["parametric_human_surface_analytical_only"]["disclaimer"]
