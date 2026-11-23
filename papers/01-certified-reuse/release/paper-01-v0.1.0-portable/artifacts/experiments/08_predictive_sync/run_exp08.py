"""Experiment 8 Runner (v0.2) — Predictive Synchronization (LC-18, H8, P4).

Runs:
  1. Primary bounded-disturbance environment with mid-stream regime shift (W_max doubles at t=1500)
     comparing continuous Kalman, periodic Kalman (P=2,3,5,8,12), adaptive Kalman uncertainty,
     and P4 certified-bound adaptive observer.
  2. Stationary Gaussian calibration & Pareto sweep over tolerance eps, failure budget delta,
     horizon tau, sensor noise, and disturbance scale.
  3. Produces the Energy–Accuracy Pareto Frontier with explicit feasibility boundary (viol <= delta)
     and regime-shift dynamics plots in results/exp08_v02_predictive_sync/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
EXP8_DIR = Path(__file__).resolve().parent
for p in (ROOT, EXP8_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("MPLCONFIGDIR", "/tmp/living_computation_mpl")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from sync_engine import (  # noqa: E402
    SyncEnvConfig,
    SyncRunResult,
    generate_sync_environment,
    run_sync_observer,
)

RESULTS_DIR = ROOT / "results" / "exp08_v02_predictive_sync"


def make_plots(
    primary_results: List[SyncRunResult],
    pareto_results: List[SyncRunResult],
    horizon_rows: List[Dict[str, Any]],
    primary_cfg: SyncEnvConfig,
    target_delta: float,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    # --- Plot 1: Energy–Accuracy Pareto Frontier (with explicit delta feasibility line!) ---
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 5.0))

    for ax, res_list, title in [
        (axes[0], primary_results, "Regime-Shift Bounded Env (W_max jumps 1.85x at t=1500)"),
        (axes[1], pareto_results, "Stationary Gaussian Environment (tau=2, eps=0.48)"),
    ]:
        # Separate periodic curve from point observers
        periodic = [r for r in res_list if r.observer_name.startswith("periodic_kalman")]
        periodic.sort(key=lambda r: r.ledger.total_cost.joules)
        ax.plot(
            [r.ledger.total_cost.joules for r in periodic],
            [r.empirical_violation_rate * 100 for r in periodic],
            color="#7f8c8d",
            marker="o",
            lw=1.8,
            ls="--",
            label="Periodic Kalman (P=2..12)",
        )
        for r in periodic:
            ax.annotate(
                r.observer_name.replace("periodic_kalman_", ""),
                (r.ledger.total_cost.joules, r.empirical_violation_rate * 100),
                textcoords="offset points",
                xytext=(4, 4),
                fontsize=7.8,
                color="#555",
            )

        special_styles = {
            "continuous_kalman": ("Continuous Kalman", "#2c3e50", "s", 85),
            "adaptive_kalman_uncertainty": ("Adaptive Kalman (Uncertainty)", "#2980b9", "^", 110),
            "adaptive_certified_bound": ("Adaptive Certified (P4 Bound)", "#27ae60", "D", 110),
        }
        for r in res_list:
            if r.observer_name in special_styles:
                lbl, col, mk, sz = special_styles[r.observer_name]
                sat_tag = "SYNC OK" if r.sync_budget_satisfied else "VIOLATES delta"
                ax.scatter(
                    [r.ledger.total_cost.joules],
                    [r.empirical_violation_rate * 100],
                    color=col,
                    marker=mk,
                    s=sz,
                    zorder=5,
                    label=f"{lbl} [{sat_tag}]",
                )

        ax.axhline(
            target_delta * 100,
            color="#c0392b",
            ls=":",
            lw=1.8,
            label=f"Error Budget delta = {target_delta*100:.1f}%",
        )
        ax.axhspan(0, target_delta * 100, color="#27ae60", alpha=0.07)
        ax.set_xlabel("Total Modeled Energy (Sensing + Compute, J)")
        ax.set_ylabel("Empirical Bound Violation Rate (%)")
        ax.set_title(title)
        ax.set_ylim(-0.5, max(target_delta * 100 * 3.0, max(r.empirical_violation_rate * 100 for r in res_list) * 1.15))
        ax.legend(fontsize=7.8, loc="upper right")

    fig.suptitle(
        "Experiment 8 (v0.2) — Predictive Synchronization Energy–Accuracy Pareto Frontier",
        fontsize=12.5,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "exp08_pareto_frontier.png", dpi=160)
    plt.close(fig)

    # --- Plot 2: Regime-Shift Error Dynamics & Horizon Scaling ---
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 4.8))

    ax = axes[0]
    by_name = {r.observer_name: r for r in primary_results}
    win = 40
    for key, lbl, col, ls in [
        ("continuous_kalman", "Continuous Kalman", "#2c3e50", ":"),
        ("periodic_kalman_p5", "Periodic (P=5)", "#c0392b", "--"),
        ("adaptive_kalman_uncertainty", "Adaptive Kalman", "#2980b9", "-"),
        ("adaptive_certified_bound", "Adaptive Certified (P4)", "#27ae60", "-"),
    ]:
        if key in by_name:
            errs = by_name[key].errors_series
            roll = np.convolve(errs, np.ones(win) / win, mode="valid")
            ax.plot(np.arange(win - 1, len(errs)), roll, label=lbl, color=col, ls=ls, lw=1.8)
    ax.axhline(by_name["continuous_kalman"].tolerance_eps, color="#e67e22", ls="--", lw=1.4, label="Tolerance eps")
    if primary_cfg.shift_step is not None:
        ax.axvline(primary_cfg.shift_step, color="#8e44ad", ls=":", lw=1.5, label="Regime Shift (t=1500)")
    ax.set_title("Rolling Lookahead Error vs Tolerance (Bounded + Shift)")
    ax.set_xlabel("Timestep t")
    ax.set_ylabel("40-step Mean Max-Norm Lookahead Error")
    ax.legend(fontsize=8.0, loc="upper left")

    # Panel B: Observation rate vs Horizon tau (keeping sync budget satisfied)
    ax = axes[1]
    taus = sorted({r["horizon_tau"] for r in horizon_rows})
    for mode, lbl, col, mk in [
        ("adaptive_kalman_uncertainty", "Adaptive Kalman (Uncertainty)", "#2980b9", "^"),
        ("adaptive_certified_bound", "Adaptive Certified (P4)", "#27ae60", "D"),
    ]:
        rates = [
            [r["observation_rate"] * 100 for r in horizon_rows if r["horizon_tau"] == tau and r["observer"] == mode][0]
            for tau in taus
        ]
        ax.plot(taus, rates, label=lbl, color=col, marker=mk, lw=2.0, ms=7)
    ax.axhline(100.0, color="#7f8c8d", ls="--", lw=1.2, label="Continuous Observation (100%)")
    ax.set_xticks(taus)
    ax.set_xlabel("Prediction Horizon tau (steps)")
    ax.set_ylabel("Required Observation Rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Observation Rate Scaling with Prediction Horizon tau")
    ax.legend(fontsize=8.5)

    fig.suptitle(
        "Experiment 8 (v0.2) — Regime-Shift Escalation & Horizon Scaling",
        fontsize=12.5,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "exp08_sync_dynamics.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target_delta = 0.05

    print("=" * 102)
    print("EXPERIMENT 8 (v0.2) — PREDICTIVE SYNCHRONIZATION (LC-18, H8, P4)")
    print("=" * 102)

    # 1. Primary bounded-disturbance environment with feasible mid-stream regime shift (1.75x)
    primary_cfg = SyncEnvConfig(
        dims=6,
        num_steps=3000,
        phi_range=(0.86, 0.94),
        disturbance_mode="bounded",
        w_scale=0.12,
        noise_scale=0.025,
        shift_step=1500,
        post_shift_w_multiplier=1.85,
        seed=808,
    )
    ds_primary = generate_sync_environment(primary_cfg)
    eps_primary = 0.50
    tau_primary = 2

    primary_results: List[SyncRunResult] = [
        run_sync_observer(ds_primary, "continuous_kalman", horizon_tau=tau_primary, tolerance_eps=eps_primary, permitted_delta=target_delta),
        run_sync_observer(ds_primary, "adaptive_kalman_uncertainty", horizon_tau=tau_primary, tolerance_eps=eps_primary, permitted_delta=target_delta),
        run_sync_observer(ds_primary, "adaptive_certified_bound", horizon_tau=tau_primary, tolerance_eps=eps_primary, permitted_delta=target_delta),
    ]
    for p in (2, 3, 5, 8, 12):
        primary_results.append(
            run_sync_observer(ds_primary, "periodic_kalman", horizon_tau=tau_primary, tolerance_eps=eps_primary, permitted_delta=target_delta, period=p)
        )

    print(f"\n[1/3] Primary Bounded Environment + Mid-Stream Shift (tau={tau_primary}, eps={eps_primary}, delta={target_delta}):")
    print(
        f"{'Observer':<28} {'Obs%':>6} {'Energy(J)':>10} {'Viol%':>7} {'Pre%':>7} {'Post%':>7} "
        f"{'SyncOK':>7} {'CalGap':>7} {'DetLat':>7} {'Unk'}"
    )
    print("-" * 104)
    for r in primary_results:
        print(
            f"{r.observer_name:<28} {r.observation_rate*100:>5.1f}% {r.ledger.total_cost.joules:>10.4f} "
            f"{r.empirical_violation_rate*100:>6.2f}% {r.pre_shift_violation_rate*100:>6.2f}% "
            f"{r.post_shift_violation_rate*100:>6.2f}% {str(r.sync_budget_satisfied):>7} "
            f"{r.calibration_ece:>7.4f} {str(r.detection_latency_steps):>7} {r.unknown_steps}"
        )

    # 2. Stationary Gaussian Pareto frontier sweep (tau=2, eps=0.45, delta=0.05)
    gauss_cfg = SyncEnvConfig(
        dims=6,
        num_steps=3000,
        phi_range=(0.86, 0.94),
        disturbance_mode="gaussian",
        w_scale=0.11,
        noise_scale=0.025,
        shift_step=None,
        seed=809,
    )
    ds_gauss = generate_sync_environment(gauss_cfg)
    eps_gauss = 0.48
    pareto_results: List[SyncRunResult] = [
        run_sync_observer(ds_gauss, "continuous_kalman", horizon_tau=2, tolerance_eps=eps_gauss, permitted_delta=target_delta),
        run_sync_observer(ds_gauss, "adaptive_kalman_uncertainty", horizon_tau=2, tolerance_eps=eps_gauss, permitted_delta=target_delta),
        run_sync_observer(ds_gauss, "adaptive_certified_bound", horizon_tau=2, tolerance_eps=eps_gauss, permitted_delta=target_delta),
    ]
    for p in (2, 3, 5, 8, 12):
        pareto_results.append(
            run_sync_observer(ds_gauss, "periodic_kalman", horizon_tau=2, tolerance_eps=eps_gauss, permitted_delta=target_delta, period=p)
        )

    print(f"\n[2/3] Stationary Gaussian Pareto Benchmark (tau=2, eps={eps_gauss}, delta={target_delta}):")
    print("-" * 104)
    for r in pareto_results:
        print(
            f"{r.observer_name:<28} {r.observation_rate*100:>5.1f}% {r.ledger.total_cost.joules:>10.4f} "
            f"{r.empirical_violation_rate*100:>6.2f}% {'—':>7} {'—':>7} "
            f"{str(r.sync_budget_satisfied):>7} {r.calibration_ece:>7.4f}"
        )

    # 3. Parameter sweeps: horizon tau, tolerance eps, failure budget delta, and sensor noise
    print("\n[3/3] Parameter Sweeps (Horizon tau, Tolerance eps, Failure Budget delta, Noise):")
    stat_bounded_cfg = SyncEnvConfig(
        dims=6, num_steps=2000, phi_range=(0.86, 0.94), disturbance_mode="bounded", w_scale=0.14, noise_scale=0.025, shift_step=None, seed=810
    )
    ds_stat_b = generate_sync_environment(stat_bounded_cfg)

    horizon_rows: List[Dict[str, Any]] = []
    for tau in (1, 2, 3, 5):
        for mode in ("adaptive_kalman_uncertainty", "adaptive_certified_bound"):
            r = run_sync_observer(ds_stat_b, mode, horizon_tau=tau, tolerance_eps=0.52, permitted_delta=0.05)
            horizon_rows.append(r.summary())
            print(
                f"  tau={tau} | {mode:<28} | obs={r.observation_rate*100:5.1f}% | "
                f"viol={r.empirical_violation_rate*100:5.2f}% | sync_ok={r.sync_budget_satisfied}"
            )

    eps_delta_rows: List[Dict[str, Any]] = []
    for eps in (0.35, 0.48, 0.65):
        for delta in (0.01, 0.05, 0.15):
            r = run_sync_observer(ds_gauss, "adaptive_kalman_uncertainty", horizon_tau=2, tolerance_eps=eps, permitted_delta=delta)
            eps_delta_rows.append(r.summary())

    noise_rows: List[Dict[str, Any]] = []
    for ns in (0.01, 0.04, 0.10):
        ds_n = generate_sync_environment(
            SyncEnvConfig(dims=6, num_steps=2000, phi_range=(0.86, 0.94), disturbance_mode="bounded", w_scale=0.14, noise_scale=ns, shift_step=None, seed=820 + int(ns * 100))
        )
        r = run_sync_observer(ds_n, "adaptive_certified_bound", horizon_tau=2, tolerance_eps=0.52, permitted_delta=0.05)
        row = r.summary()
        row["noise_scale"] = ns
        noise_rows.append(row)

    make_plots(primary_results, pareto_results, horizon_rows, primary_cfg, target_delta)

    payload = {
        "experiment_version": "v0.2",
        "primary_config": primary_cfg.__dict__,
        "primary_results": [r.summary() for r in primary_results],
        "gaussian_config": gauss_cfg.__dict__,
        "gaussian_pareto_results": [r.summary() for r in pareto_results],
        "horizon_sweep": horizon_rows,
        "eps_delta_sweep": eps_delta_rows,
        "noise_sweep": noise_rows,
    }
    (RESULTS_DIR / "exp08_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nArtifacts saved to: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
