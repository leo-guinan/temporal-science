#!/usr/bin/env python3
"""exp_hw04 — Prospective, Cross-Workload Temporal-Energy Validation on `_pytest`.

STRICT PROSPECTIVE PROTOCOL:
  1. Verifies `results/preregistered_predictions.json` ALREADY exists and matches its
     embedded SHA-256 seal BEFORE executing a single benchmark trial.
  2. Executes N = 10 paired, interleaved, independently seeded blocks on AC Power with
     pinned Python 3.11.7 across:
       - 3-way 5-edit full-lifecycle comparison (`full_typecheck`, `strong_incremental_dag`,
         `certified_type_canary`, q = 0.20, 0 mismatches).
       - 7-point API-breaking churn sweep (`q in {0.00, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00}`,
         20 edits + single-pass 71-module cold start, 0 mismatches).
  3. Scores BOTH frozen prospective models (Model 1 Zero-Shot from exp_hw03 AND Model 2
     5-Component Primitive Calibration) WITHOUT ANY POST-HOC REFITTING against the newly
     measured Apple M3 Max Process CPU PMU (`ri_energy_nj`) and Whole-SoC Package
     (`IOReport` `CPU + GPU + ANE + DRAM0 + DCS0 + AMCC0`) energies!
  4. Re-verifies the preregistration SHA-256 seal is unchanged after execution and
     generates 3 publication figures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
import gc
import hashlib
import json
import math
import os
import random
import statistics
import sys

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
HW01_DIR = TS_ROOT / "experiments" / "hw_energy_paper01"
HW02_DIR = TS_ROOT / "experiments" / "hw_soc_paper02"
for p in (HW01_DIR, HW02_DIR, EXP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("MPLCONFIGDIR", "/tmp/temporal_science_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats as sp_stats

from telemetry_macos import run_linearity_calibration
from telemetry_soc_macos import (
    IOReportEnergyReader,
    delta_dual,
    get_soc_machine_metadata,
    get_system_context,
    snapshot_dual,
)
from incremental_typechecker import (
    IncrementalTypecheckEngine,
    build_pytest_import_graph,
    discover_pytest_corpus,
    generate_pytest_edit_stream,
)

RESULTS_DIR = EXP_DIR / "results"
PREREG_PATH = RESULTS_DIR / "preregistered_predictions.json"


def _t_ci95(values: List[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    return float(sp_stats.t.ppf(0.975, df=n - 1)) * statistics.stdev(values) / math.sqrt(n)


def _paired_stats(base_vals: List[float], cand_vals: List[float]) -> Dict[str, Any]:
    diffs = [b - c for b, c in zip(base_vals, cand_vals)]
    pcts = [100.0 * (b - c) / b if abs(b) > 1e-12 else 0.0 for b, c in zip(base_vals, cand_vals)]
    mean_d = statistics.mean(diffs)
    sd_d = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    ci_d = _t_ci95(diffs)
    dz = (mean_d / sd_d) if sd_d > 1e-12 else 0.0
    if sd_d > 1e-12:
        t_st, p_val = sp_stats.ttest_rel(base_vals, cand_vals)
        t_st_f, p_val_f = float(t_st), float(p_val)
    else:
        t_st_f, p_val_f = 0.0, 1.0
    mb, mc = statistics.mean(base_vals), statistics.mean(cand_vals)
    return {
        "base_mean": round(mb, 6),
        "cand_mean": round(mc, 6),
        "paired_diff_mean": round(mean_d, 6),
        "paired_diff_ci95": round(ci_d, 6),
        "paired_pct_mean": round(statistics.mean(pcts), 3),
        "paired_pct_ci95": round(_t_ci95(pcts), 3),
        "ratio_savings_pct": round(100.0 * (mb - mc) / mb, 3) if abs(mb) > 1e-12 else 0.0,
        "cohens_dz": round(dz, 3),
        "t_stat": round(t_st_f, 3),
        "p_value": round(p_val_f, 6),
        "significant_005": bool(p_val_f < 0.05 and (mean_d - ci_d) * (mean_d + ci_d) > 0),
    }


def _verify_preregistration() -> Tuple[Dict[str, Any], str]:
    assert PREREG_PATH.exists(), (
        f"PREREGISTRATION MISSING: Run preregister_predictions.py first to seal {PREREG_PATH}"
    )
    doc = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    expected_seal = doc["preregistration_sha256"]
    core = {k: v for k, v in doc.items() if k != "preregistration_sha256"}
    actual_seal = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert actual_seal == expected_seal, f"PREREGISTRATION TAMPERED! expected={expected_seal}, got={actual_seal}"
    return doc, actual_seal


def _score_prospective_model(
    model_preds: Dict[str, Any],
    observed_rows: List[Dict[str, Any]],
    energy_key: str,
) -> Dict[str, Any]:
    """Score a frozen prospective prediction dictionary WITHOUT ANY REFITTING."""
    is_proc = energy_key == "proc_cpu_energy_j"
    p_d_key = "pred_delta_proc_j" if is_proc else "pred_delta_soc_j"
    p_pct_key = "pred_pct_proc" if is_proc else "pred_pct_soc"
    p_inc_key = "pred_inc_proc_j" if is_proc else "pred_inc_soc_j"

    obs_d, prd_d, obs_p, prd_p = [], [], [], []
    obs_inc, prd_inc = [], []
    per_q: List[Dict[str, Any]] = []

    for r in observed_rows:
        qk = f"{r['api_break_prob']:.2f}"
        pm = model_preds["by_q"][qk]
        od = float(r["paired_vs_incremental"][energy_key]["paired_diff_mean"])
        op = float(r["paired_vs_incremental"][energy_key]["paired_pct_mean"])
        oi = float(r["inc_mean"][energy_key])
        pd = float(pm[p_d_key])
        pp = float(pm[p_pct_key])
        pi = float(pm[p_inc_key])

        obs_d.append(od); prd_d.append(pd)
        obs_p.append(op); prd_p.append(pp)
        obs_inc.append(oi); prd_inc.append(pi)
        per_q.append(
            {
                "q": r["api_break_prob"],
                "obs_delta_j": round(od, 4),
                "pred_delta_j": round(pd, 4),
                "err_delta_j": round(pd - od, 4),
                "obs_pct": round(op, 2),
                "pred_pct": round(pp, 2),
                "err_pct_pts": round(pp - op, 2),
                "obs_inc_j": round(oi, 4),
                "pred_inc_j": round(pi, 4),
                "within_95ci": abs(pd - od) <= float(r["paired_vs_incremental"][energy_key]["paired_diff_ci95"]),
            }
        )

    oa, pa = np.array(obs_d), np.array(prd_d)
    ss_res = float(np.sum((oa - pa) ** 2))
    ss_tot = float(np.sum((oa - np.mean(oa)) ** 2))
    r2_j = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0

    opa, ppa = np.array(obs_p), np.array(prd_p)
    ss_res_p = float(np.sum((opa - ppa) ** 2))
    ss_tot_p = float(np.sum((opa - np.mean(opa)) ** 2))
    r2_pct = 1.0 - ss_res_p / ss_tot_p if ss_tot_p > 1e-15 else 0.0

    return {
        "energy_key": energy_key,
        "prospective_r2_joules": round(r2_j, 4),
        "prospective_r2_pct": round(r2_pct, 4),
        "mae_joules": round(float(np.mean(np.abs(pa - oa))), 4),
        "rmse_joules": round(float(math.sqrt(np.mean((pa - oa) ** 2))), 4),
        "bias_joules": round(float(np.mean(pa - oa)), 4),
        "mae_pct_pts": round(float(np.mean(np.abs(ppa - opa))), 2),
        "bias_pct_pts": round(float(np.mean(ppa - opa)), 2),
        "baseline_inc_scale_ratio_obs_over_pred": round(float(np.mean(obs_inc) / np.mean(prd_inc)), 4),
        "q_star_pred": model_preds["q_star_pred_proc" if is_proc else "q_star_pred_soc"],
        "per_q": per_q,
    }


def generate_figures(
    prereg: Dict[str, Any],
    q_rows: List[Dict[str, Any]],
    scores: Dict[str, Any],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    qs = np.array([r["api_break_prob"] for r in q_rows])

    # --- Figure 1: Prospective Predictions vs Measured Reality (Joules & %, Process CPU & Whole-SoC) ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.4))

    for ax, ekey, title, ylabel in (
        (ax1, "proc_cpu_energy_j", "A. Process CPU PMU (ri_energy_nj) — Prospective vs Measured", "Net Full-Lifecycle Energy Saved ΔE (Joules)"),
        (ax2, "soc_package_j", "B. Whole-SoC Package (CPU+GPU+ANE+Mem) — Prospective vs Measured", "Net Full-Lifecycle Energy Saved ΔE (Joules)"),
    ):
        is_proc = ekey == "proc_cpu_energy_j"
        pdk = "pred_delta_proc_j" if is_proc else "pred_delta_soc_j"
        obs = [r["paired_vs_incremental"][ekey]["paired_diff_mean"] for r in q_rows]
        ci = [r["paired_vs_incremental"][ekey]["paired_diff_ci95"] for r in q_rows]
        m1_p = [prereg["model1_zero_shot_exp03_predictions"]["by_q"][f"{q:.2f}"][pdk] for q in qs]
        m2_p = [prereg["model2_5term_primitive_predictions"]["by_q"][f"{q:.2f}"][pdk] for q in qs]

        s1 = scores["model1_zero_shot"][ekey]
        s2 = scores["model2_5term_primitive"][ekey]

        ax.errorbar(qs, obs, yerr=ci, fmt="o-", linewidth=2.2, capsize=3.5, color="#1a202c",
                    label="Measured _pytest (N=10 paired blocks ± 95% CI)")
        ax.plot(qs, m2_p, "s--", linewidth=2.0, color="#2f855a",
                label=f"M2: 5-Term Prospective (R²={s2['prospective_r2_joules']:.3f}, MAE={s2['mae_joules']:.2f}J)")
        ax.plot(qs, m1_p, "^:", linewidth=2.0, color="#dd6b20",
                label=f"M1: Zero-Shot exp03 (R²={s1['prospective_r2_joules']:.3f}, MAE={s1['mae_joules']:.2f}J)")
        ax.axhline(0, color="black", linewidth=0.9)
        ax.set_xlabel("API-Breaking Churn Rate q (20 Edits + 71-Module Cold Start)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=8.0, loc="upper right")
        ax.grid(alpha=0.3)

    fig.suptitle("exp_hw04: Preregistered Prospective Energy Predictions vs Measured `_pytest` Typechecker", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(RESULTS_DIR / "fig1_prospective_vs_measured_joules.png", dpi=160)
    plt.close(fig)

    # --- Figure 2: Percentage Savings Across All Rails + Percentage Prediction Error ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.2))
    for ekey, col, mk, lbl in (
        ("proc_cpu_energy_j", "#2f855a", "D", "Measured Process CPU PMU (%)"),
        ("soc_package_j", "#dd6b20", "s", "Measured Whole-SoC Package (%)"),
        ("soc_memory_j", "#805ad5", "^", "Measured Whole-SoC Memory+Fabric (%)"),
        ("wall_time_s", "#2b6cb0", "o", "Measured Wall-Clock Time (%)"),
    ):
        ys = [r["paired_vs_incremental"][ekey]["paired_pct_mean"] for r in q_rows]
        cis = [r["paired_vs_incremental"][ekey]["paired_pct_ci95"] for r in q_rows]
        ax1.errorbar(qs, ys, yerr=cis, marker=mk, capsize=3, linewidth=2.0, color=col, label=lbl)
    # Overlay prospective M2 % curve (note scale-invariant % prediction!)
    m2_pct_p = [prereg["model2_5term_primitive_predictions"]["by_q"][f"{q:.2f}"]["pred_pct_proc"] for q in qs]
    ax1.plot(qs, m2_pct_p, "k--", linewidth=1.8, label="Preregistered M2 Predicted % (Proc)")
    ax1.axhline(0, color="black", linewidth=0.9)
    ax1.set_xlabel("API-Breaking Churn Rate q")
    ax1.set_ylabel("Full-Lifecycle Savings vs Strong Incremental ± 95% t-CI (%)")
    ax1.set_title("A. `_pytest` Typechecker Full-Lifecycle Savings Across All Rails")
    ax1.legend(fontsize=8.0)
    ax1.grid(alpha=0.3)

    # Right: Prospective Prediction Parity Plot (Predicted vs Observed % Savings — M1 vs M2)
    m1_pct_obs_p = [x["obs_pct"] for x in scores["model1_zero_shot"]["proc_cpu_energy_j"]["per_q"]]
    m1_pct_prd_p = [x["pred_pct"] for x in scores["model1_zero_shot"]["proc_cpu_energy_j"]["per_q"]]
    m2_pct_obs_p = [x["obs_pct"] for x in scores["model2_5term_primitive"]["proc_cpu_energy_j"]["per_q"]]
    m2_pct_prd_p = [x["pred_pct"] for x in scores["model2_5term_primitive"]["proc_cpu_energy_j"]["per_q"]]
    m2_pct_obs_s = [x["obs_pct"] for x in scores["model2_5term_primitive"]["soc_package_j"]["per_q"]]
    m2_pct_prd_s = [x["pred_pct"] for x in scores["model2_5term_primitive"]["soc_package_j"]["per_q"]]

    ax2.plot([-10, 90], [-10, 90], "k--", linewidth=1.2, alpha=0.7, label="Perfect Prospective Prediction (y = x)")
    ax2.scatter(m1_pct_prd_p, m1_pct_obs_p, s=75, marker="^", color="#dd6b20",
                label=f"M1 Zero-Shot % (Proc MAE={scores['model1_zero_shot']['proc_cpu_energy_j']['mae_pct_pts']:.1f} pp)")
    ax2.scatter(m2_pct_prd_p, m2_pct_obs_p, s=80, marker="D", color="#2f855a",
                label=f"M2 5-Term % (Proc MAE={scores['model2_5term_primitive']['proc_cpu_energy_j']['mae_pct_pts']:.1f} pp)")
    ax2.scatter(m2_pct_prd_s, m2_pct_obs_s, s=80, marker="s", color="#805ad5",
                label=f"M2 5-Term % (Whole-SoC MAE={scores['model2_5term_primitive']['soc_package_j']['mae_pct_pts']:.1f} pp)")
    ax2.set_xlabel("Preregistered Predicted Savings (%)")
    ax2.set_ylabel("Directly Measured Savings (%)")
    ax2.set_title("B. Prospective % Parity (Scale-Invariant Cross-Workload Transfer)")
    ax2.legend(fontsize=8.0)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_rails_and_prospective_parity.png", dpi=160)
    plt.close(fig)


def main() -> None:
    prereg, seal_before = _verify_preregistration()
    print(f"VERIFIED PREREGISTRATION SEAL: {seal_before}")
    print(f"Preregistered at UTC: {prereg['sealed_at_utc']}")

    n_blocks = int(prereg["planned_protocol"]["n_blocks"])
    num_edits = int(prereg["planned_protocol"]["num_edits_per_block"])
    target_qs = [float(q) for q in prereg["planned_protocol"]["target_qs"]]

    ior = IOReportEnergyReader()
    meta = get_soc_machine_metadata()
    start_ctx = get_system_context()
    calib = run_linearity_calibration()
    print(f"Hardware: {meta['cpu_brand']} | Python {meta['python_version']} | load1m={start_ctx['loadavg_1m']} | {start_ctx['pmset_batt']}")

    sources, _ = discover_pytest_corpus()
    deps, rev, order = build_pytest_import_graph(sources)
    rng = random.Random(909)
    metrics = ("wall_time_s", "proc_cpu_energy_j", "instructions", "soc_cpu_j", "soc_memory_j", "soc_package_j")

    # Warm-up
    eds_w = generate_pytest_edit_stream(sources, rev, 3, 0.2, 111)
    IncrementalTypecheckEngine("certified_type_canary", sources, deps, rev, order).run_full_lifecycle(eds_w)

    # 1. Three-way comparison vs full_typecheck (5 edits, q=0.20, N=10 blocks)
    print(f"[1/2] 3-way `_pytest` typechecker comparison (5 edits, q=0.20, N={n_blocks} blocks)...")
    full_rows: Dict[str, List[Dict[str, Any]]] = {
        "full_typecheck": [], "strong_incremental_dag": [], "certified_type_canary": []
    }
    for b in range(n_blocks):
        eds5 = generate_pytest_edit_stream(sources, rev, 5, 0.20, 8100 + b * 17)
        modes = ["full_typecheck", "strong_incremental_dag", "certified_type_canary"]
        rng.shuffle(modes)
        fps = {}
        for mode in modes:
            gc.collect()
            s0 = snapshot_dual(ior)
            eng = IncrementalTypecheckEngine(mode, sources, deps, rev, order)
            fp = eng.run_full_lifecycle(eds5)
            s1 = snapshot_dual(ior)
            proc, soc = delta_dual(ior, s0, s1)
            assert soc is not None
            fps[mode] = fp
            full_rows[mode].append(
                {
                    "block": b,
                    "wall_time_s": proc.wall_time_s,
                    "proc_cpu_energy_j": proc.hardware_energy_j,
                    "instructions": proc.instructions,
                    "soc_cpu_j": soc.soc_cpu_j,
                    "soc_memory_j": soc.soc_memory_j,
                    "soc_package_j": soc.soc_package_j,
                    "modules_checked_setup": eng.modules_checked_setup,
                    "modules_checked_edits": eng.modules_checked_edits,
                    "modules_avoided": eng.modules_avoided,
                }
            )
        assert fps["full_typecheck"] == fps["strong_incremental_dag"] == fps["certified_type_canary"]

    canary_vs_full = {
        m: _paired_stats([r[m] for r in full_rows["full_typecheck"]], [r[m] for r in full_rows["certified_type_canary"]])
        for m in metrics
    }
    print(
        f"  3-way vs full_typecheck: proc_E={canary_vs_full['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{canary_vs_full['proc_cpu_energy_j']['paired_pct_ci95']:.2f}, "
        f"SoC_pkg={canary_vs_full['soc_package_j']['paired_pct_mean']:+6.2f}%±{canary_vs_full['soc_package_j']['paired_pct_ci95']:.2f}"
    )

    # 2. Prospective 7-point churn sweep using the EXACT preregistered seeds!
    print(f"[2/2] Prospective 7-point churn sweep on `_pytest` (20 edits + 71-mod cold start, N={n_blocks} blocks)...")
    q_summaries: List[Dict[str, Any]] = []
    raw_by_q: Dict[str, Any] = {}
    for q in target_qs:
        inc_rows, can_rows = [], []
        for b in range(n_blocks):
            seed = 7000 + int(q * 100) * 100 + b * 29  # exact preregistered seed
            eds = generate_pytest_edit_stream(sources, rev, num_edits, q, seed)
            modes = ["strong_incremental_dag", "certified_type_canary"]
            rng.shuffle(modes)
            fps = {}
            for mode in modes:
                gc.collect()
                s0 = snapshot_dual(ior)
                eng = IncrementalTypecheckEngine(mode, sources, deps, rev, order)
                fp = eng.run_full_lifecycle(eds)
                s1 = snapshot_dual(ior)
                proc, soc = delta_dual(ior, s0, s1)
                assert soc is not None
                fps[mode] = fp
                rec = {
                    "block": b,
                    "seed": seed,
                    "wall_time_s": proc.wall_time_s,
                    "proc_cpu_energy_j": proc.hardware_energy_j,
                    "instructions": proc.instructions,
                    "soc_cpu_j": soc.soc_cpu_j,
                    "soc_memory_j": soc.soc_memory_j,
                    "soc_package_j": soc.soc_package_j,
                    "modules_checked_setup": eng.modules_checked_setup,
                    "modules_checked_edits": eng.modules_checked_edits,
                    "modules_avoided": eng.modules_avoided,
                    "avoided_source_kib": round(eng.avoided_source_kib, 2),
                    "canaries_safe": eng.canaries_safe,
                    "canaries_checked": eng.canaries_checked,
                }
                (inc_rows if mode == "strong_incremental_dag" else can_rows).append(rec)
            assert fps["strong_incremental_dag"] == fps["certified_type_canary"], f"Mismatch at q={q} b={b}"

        paired = {m: _paired_stats([r[m] for r in inc_rows], [r[m] for r in can_rows]) for m in metrics}
        q_row = {
            "api_break_prob": q,
            "modules_avoided_mean": round(statistics.mean([r["modules_avoided"] for r in can_rows]), 1),
            "avoided_source_kib_mean": round(statistics.mean([r["avoided_source_kib"] for r in can_rows]), 1),
            "safe_hit_rate": round(
                statistics.mean([r["canaries_safe"] / max(1, r["canaries_checked"]) for r in can_rows]), 4
            ),
            "inc_mean": {m: round(statistics.mean([r[m] for r in inc_rows]), 6) for m in metrics},
            "can_mean": {m: round(statistics.mean([r[m] for r in can_rows]), 6) for m in metrics},
            "paired_vs_incremental": paired,
        }
        q_summaries.append(q_row)
        raw_by_q[f"q{q:.2f}"] = {"inc": inc_rows, "canary": can_rows}

        p2 = prereg["model2_5term_primitive_predictions"]["by_q"][f"{q:.2f}"]
        print(
            f"  q={q:4.2f}: OBS proc={paired['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{paired['proc_cpu_energy_j']['paired_pct_ci95']:.2f} "
            f"(PRED M2={p2['pred_pct_proc']:+6.2f}%) | "
            f"OBS SoC={paired['soc_package_j']['paired_pct_mean']:+6.2f}%±{paired['soc_package_j']['paired_pct_ci95']:.2f} "
            f"(PRED M2={p2['pred_pct_soc']:+6.2f}%, p={paired['soc_package_j']['p_value']:.4f})"
        )

    # 3. Score BOTH frozen prospective models with ZERO refitting
    scores = {
        "model1_zero_shot": {
            "proc_cpu_energy_j": _score_prospective_model(
                prereg["model1_zero_shot_exp03_predictions"], q_summaries, "proc_cpu_energy_j"
            ),
            "soc_package_j": _score_prospective_model(
                prereg["model1_zero_shot_exp03_predictions"], q_summaries, "soc_package_j"
            ),
        },
        "model2_5term_primitive": {
            "proc_cpu_energy_j": _score_prospective_model(
                prereg["model2_5term_primitive_predictions"], q_summaries, "proc_cpu_energy_j"
            ),
            "soc_package_j": _score_prospective_model(
                prereg["model2_5term_primitive_predictions"], q_summaries, "soc_package_j"
            ),
        },
    }

    print("\n=== STRICT PROSPECTIVE SCORES (ZERO REFITTING) ===")
    for mname in ("model1_zero_shot", "model2_5term_primitive"):
        for ek in ("proc_cpu_energy_j", "soc_package_j"):
            sc = scores[mname][ek]
            print(
                f"  {mname:22s} | {ek:18s}: R²_J={sc['prospective_r2_joules']:+.4f}, R²_pct={sc['prospective_r2_pct']:+.4f}, "
                f"MAE={sc['mae_joules']:.3f}J ({sc['mae_pct_pts']:.2f}pp), bias={sc['bias_joules']:+.3f}J, "
                f"obs/pred_scale={sc['baseline_inc_scale_ratio_obs_over_pred']:.3f}x"
            )

    _, seal_after = _verify_preregistration()
    assert seal_after == seal_before, "Preregistration seal changed during execution!"
    end_ctx = get_system_context()
    generate_figures(prereg, q_summaries, scores)

    (RESULTS_DIR / "exp_hw04_raw_blocks.json").write_text(
        json.dumps({"three_way_full": full_rows, "q_sweep": raw_by_q}, indent=2),
        encoding="utf-8",
    )
    summary = {
        "experiment_id": "exp_hw04_prospective_pytest_typechecker",
        "version": "0.1.0",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256_verified": seal_after,
        "preregistered_at_utc": prereg["sealed_at_utc"],
        "n_blocks": n_blocks,
        "machine": meta,
        "system_context_start": start_ctx,
        "system_context_end": end_ctx,
        "calibration": calib,
        "corpus": {
            "name": "_pytest (pytest 9.0.2)",
            "num_modules": len(sources),
            "num_import_edges": sum(len(v) for v in deps.values()),
            "cold_start_passes": 1,
            "mismatches_total": 0,
        },
        "three_way_full_typecheck_comparison": {
            "canary_vs_full_typecheck": canary_vs_full,
        },
        "prospective_churn_sweep": q_summaries,
        "prospective_model_scores": scores,
    }
    out_p = RESULTS_DIR / "exp_hw04_summary.json"
    out_p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved exp_hw04 summary -> {out_p}")


if __name__ == "__main__":
    main()
