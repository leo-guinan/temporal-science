"""Automated verification tests for exp_hw04 Preregistered Prospective Validation."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = REPO_ROOT / "experiments" / "hw_soc_prospective_exp04"
RES_DIR = EXP_DIR / "results"


def test_exp_hw04_preregistration_seal_and_prospective_scores() -> None:
    prereg_p = RES_DIR / "preregistered_predictions.json"
    sum_p = RES_DIR / "exp_hw04_summary.json"
    raw_p = RES_DIR / "exp_hw04_raw_blocks.json"
    assert prereg_p.exists() and sum_p.exists() and raw_p.exists()
    assert (EXP_DIR / "REPORT.md").exists()
    assert (RES_DIR / "fig1_prospective_vs_measured_joules.png").exists()
    assert (RES_DIR / "fig2_rails_and_prospective_parity.png").exists()

    # 1. Verify preregistration SHA-256 integrity & timestamp ordering (preregistered BEFORE execution)
    prereg = json.loads(prereg_p.read_text(encoding="utf-8"))
    summary = json.loads(sum_p.read_text(encoding="utf-8"))
    core = {k: v for k, v in prereg.items() if k != "preregistration_sha256"}
    recomputed_seal = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert recomputed_seal == prereg["preregistration_sha256"]
    assert summary["preregistration_sha256_verified"] == recomputed_seal
    assert summary["preregistered_at_utc"] < summary["executed_at_utc"]

    # 2. Verify corpus independence, single-pass cold start, 0 mismatches, and AC power
    assert summary["corpus"]["num_modules"] == 71
    assert summary["corpus"]["cold_start_passes"] == 1
    assert summary["corpus"]["mismatches_total"] == 0
    assert summary["n_blocks"] >= 10
    assert "AC Power" in summary["system_context_start"]["pmset_batt"]

    # 3. Verify 5-component prospective model (Model 2) achieves high accuracy on BOTH Process CPU & Whole-SoC
    m2_proc = summary["prospective_model_scores"]["model2_5term_primitive"]["proc_cpu_energy_j"]
    m2_soc = summary["prospective_model_scores"]["model2_5term_primitive"]["soc_package_j"]
    assert m2_proc["prospective_r2_joules"] > 0.99
    assert m2_proc["mae_pct_pts"] < 1.0
    assert m2_soc["prospective_r2_joules"] > 0.90
    assert m2_soc["mae_pct_pts"] < 3.0

    # 4. Verify honest Model 1 contrast: zero-shot % transfers accurately while abs Whole-SoC J requires calibration
    m1_proc = summary["prospective_model_scores"]["model1_zero_shot"]["proc_cpu_energy_j"]
    m1_soc = summary["prospective_model_scores"]["model1_zero_shot"]["soc_package_j"]
    assert m1_proc["prospective_r2_pct"] > 0.99
    assert m1_soc["prospective_r2_joules"] < m2_soc["prospective_r2_joules"]

    # 5. Verify independent audit & frozen prospective evaluation protocol exist and pass blind thresholds
    audit_p = RES_DIR / "exp_hw04_audit.json"
    assert audit_p.exists()
    audit = json.loads(audit_p.read_text(encoding="utf-8"))
    blind_m2 = audit["q1_preregistration_independence"]["strictly_blind_unseen_schedule_scores"]["model2_5term_primitive"]
    assert blind_m2["proc_cpu_energy_j"]["blind_r2_joules"] > 0.95
    assert blind_m2["soc_package_j"]["blind_r2_joules"] > 0.90
    assert audit["q2_calibration_cost_and_payback"]["payback_runs_by_q"]["0.25"]["n_star_cal_soc_runs"] == 1
    assert (REPO_ROOT / "protocols" / "prospective-energy-protocol-v1.md").exists()
    assert (REPO_ROOT / "protocols" / "prospective-energy-protocol-v1.yaml").exists()
