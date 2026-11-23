"""Automated verification tests for exp_hw02 Whole-SoC Energy Validation."""

from __future__ import annotations

from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = REPO_ROOT / "experiments" / "hw_soc_paper02"
RES_DIR = EXP_DIR / "results"


def test_exp_hw02_outputs_integrity_and_honest_conclusions() -> None:
    sum_path = RES_DIR / "exp_hw02_summary.json"
    raw_path = RES_DIR / "exp_hw02_raw_blocks.json"
    assert sum_path.exists() and raw_path.exists()
    assert (EXP_DIR / "METHODOLOGY_AND_ASSESSMENT.md").exists()
    for fig in (
        "fig1_soc_vs_process_regimes.png",
        "fig2_soc_crossover_concentrated.png",
        "fig3_soc_granularity_and_rails.png",
    ):
        assert (RES_DIR / fig).exists(), f"Missing figure {fig}"

    data = json.loads(sum_path.read_text(encoding="utf-8"))
    assert data["n_blocks_per_condition"] >= 10
    assert "Wall-plug AC power" in data["machine"]["exposed_soc_rails"]["explicitly_unmeasured"]

    # Zero mismatches across all core regimes
    for suite_key in ("c1_localized_regime_drift", "c1_high_entropy_shock"):
        for vname, vdata in data[suite_key]["variants"].items():
            assert vdata["mismatches_total"] == 0, f"Mismatch in {suite_key}/{vname}"

    # Verify decisive whole-SoC advantage vs Full Recomputation
    vs_full = data["c1_localized_regime_drift"]["paired_vs_full"]["living_inmem_surprise"]
    assert vs_full["soc_package_j"]["paired_pct_mean"] > 80.0
    assert vs_full["soc_package_j"]["significant_005"] is True
    assert vs_full["soc_memory_j"]["paired_pct_mean"] > 80.0

    # Verify disk logging hurts process CPU energy significantly vs incremental
    disk_inc = data["c1_localized_regime_drift"]["paired_vs_incremental"]["living_disk_jsonl_surprise"]
    assert disk_inc["proc_cpu_energy_j"]["paired_pct_mean"] < -3.0
    assert disk_inc["proc_cpu_energy_j"]["significant_005"] is True

    # Verify granularity scaling establishes statistically significant whole-SoC savings at K=20 and K=80
    gran = {r["k_granularity"]: r["paired_vs_incremental"]["living_inmem_surprise"] for r in data["c2_granularity_scaling"]}
    assert gran[20]["soc_package_j"]["paired_pct_mean"] > 5.0
    assert gran[20]["soc_package_j"]["significant_005"] is True
    assert gran[80]["soc_package_j"]["paired_pct_mean"] > 25.0
    assert gran[80]["soc_package_j"]["significant_005"] is True

    # Verify concentrated shock sweep covers 10 points around p=0.08-0.10
    probs = [r["shock_probability"] for r in data["c3_concentrated_shock_crossover"]]
    for p_req in (0.06, 0.07, 0.08, 0.09, 0.10, 0.12):
        assert p_req in probs
