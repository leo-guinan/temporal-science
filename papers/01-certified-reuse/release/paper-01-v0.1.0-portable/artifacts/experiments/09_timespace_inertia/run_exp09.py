"""Experiment 9 Runner (v0.2) — Timespace Trajectories & Informational Inertia (H9).

Runs:
  1. Primary 1,800-step stream with two structural regime shifts (t=600, t=1200) comparing
     all five memory architectures.
  2. Prior observation count sweep (N_0 in {10, 50, 200, 1000}) quantifying informational inertia.
  3. Raw memory size sweep (irrelevant dims in {0, 10, 30, 60}) separating bytes from predictive sufficiency.
  4. Saves JSON summary and plots to results/exp09_v02_timespace_inertia/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
EXP9_DIR = Path(__file__).resolve().parent
for p in (ROOT, EXP9_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("MPLCONFIGDIR", "/tmp/living_computation_mpl")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from timespace_core import (  # noqa: E402
    TimespaceConfig,
    TimespaceRunResult,
    generate_timespace_stream,
    run_timespace_system,
)

RESULTS_DIR = ROOT / "results" / "exp09_v02_timespace_inertia"

MODES = [
    "stateless_short_window",
    "naive_infinite_memory",
    "bloated_irrelevant_memory",
    "exponential_forgetting_rls",
    "living_canary_memory",
]


def make_plots(
    primary: Dict[str, TimespaceRunResult],
    prior_rows: List[Dict[str, Any]],
    bloat_rows: List[Dict[str, Any]],
    shift_steps: tuple,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    # --- Plot 1: Timespace Movement (Hellinger) & Rolling MSE across Shifts ---
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.8))

    styles = [
        ("stateless_short_window", "Stateless Window (25)", "#7f8c8d", ":"),
        ("naive_infinite_memory", "Naive Infinite Memory (Overconfident)", "#c0392b", "--"),
        ("exponential_forgetting_rls", "Forgetting RLS (lam=0.96)", "#e67e22", "-."),
        ("living_canary_memory", "Living Canary Memory", "#27ae60", "-"),
    ]

    # Panel A: Timespace movement trajectory D_H(q_{t-1}, q_t)
    ax = axes[0]
    for key, lbl, col, ls in styles:
        h = primary[key].hellinger_series
        roll = np.convolve(h, np.ones(10) / 10, mode="valid")
        ax.plot(np.arange(9, len(h)), roll, label=lbl, color=col, ls=ls, lw=1.7)
    for s in shift_steps:
        ax.axvline(s, color="#8e44ad", ls=":", lw=1.3)
    ax.set_yscale("log")
    ax.set_title("Timespace Movement D_H(q_{t-1}, q_t) (10-step avg)")
    ax.set_xlabel("Timestep t")
    ax.set_ylabel("Hellinger Metric (log scale)")
    ax.legend(fontsize=7.8, loc="upper right")

    # Panel B: Rolling MSE (showing naive infinite memory's catastrophic post-shift lag!)
    ax = axes[1]
    for key, lbl, col, ls in styles:
        m = primary[key].mse_series
        roll = np.convolve(m, np.ones(25) / 25, mode="valid")
        ax.plot(np.arange(24, len(m)), roll, label=lbl, color=col, ls=ls, lw=1.8)
    for s in shift_steps:
        ax.axvline(s, color="#8e44ad", ls=":", lw=1.3, label="Regime Shift" if s == shift_steps[0] else None)
    ax.set_yscale("log")
    ax.set_title("Predictive Error Across Shifts (25-step MSE)")
    ax.set_xlabel("Timestep t")
    ax.set_ylabel("Mean Squared Error (log scale)")
    ax.legend(fontsize=7.8, loc="upper right")

    # Panel C: Jump-to-Jitter Ratio (H9 signature)
    ax = axes[2]
    bar_keys = [
        ("stateless_short_window", "Stateless\nWindow"),
        ("naive_infinite_memory", "Naive Inf.\nMemory"),
        ("exponential_forgetting_rls", "Forgetting\nRLS"),
        ("living_canary_memory", "Living\nCanary"),
    ]
    vals = [primary[k].jump_to_jitter_ratio for k, _ in bar_keys]
    cols = ["#7f8c8d", "#c0392b", "#e67e22", "#27ae60"]
    bars = ax.bar([lbl for _, lbl in bar_keys], vals, color=cols, alpha=0.88, width=0.52)
    for b in bars:
        h = b.get_height()
        ax.annotate(f"{h:.1f}x", xy=(b.get_x() + b.get_width() / 2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=9)
    ax.set_title("H9 Signature: Shift-Jump / Routine-Jitter Ratio")
    ax.set_ylabel("Mean Shift D_H / Mean Routine D_H")

    fig.suptitle(
        "Experiment 9 (v0.2) — Timespace Trajectories & Informational Inertia",
        fontsize=12.5,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "exp09_timespace_trajectories.png", dpi=160)
    plt.close(fig)

    # --- Plot 2: Raw Memory Bytes vs Predictive Sufficiency & Maintenance Burden ---
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6))

    # Panel A: Prior count N_0 inertia sweep
    ax = axes[0]
    ns = sorted({r["prior_obs_count"] for r in prior_rows})
    for mode, lbl, col, mk in [
        ("naive_infinite_memory", "Naive Infinite Memory (Overconfident)", "#c0392b", "s"),
        ("living_canary_memory", "Living Canary Memory", "#27ae60", "o"),
    ]:
        pmse = [
            [r["post_shift_mse"] for r in prior_rows if r["prior_obs_count"] == n0 and r["system"] == mode][0]
            for n0 in ns
        ]
        ax.plot([str(n0) for n0 in ns], pmse, label=lbl, color=col, marker=mk, lw=2.2, ms=7)
    ax.set_xlabel("Pre-Accumulated Prior Observation Count N_0")
    ax.set_ylabel("Post-Shift MSE (30-step adaptation window)")
    ax.set_title("Informational Inertia vs Prior Experience N_0")
    ax.legend(fontsize=8.5)

    # Panel B: Raw memory size vs maintenance ops & predictive MSE (bytes != sufficiency!)
    ax1 = axes[1]
    kb = [r["memory_bytes"] / 1024.0 for r in bloat_rows]
    ops_k = [r["total_ops"] / 1e3 for r in bloat_rows]
    rmses = [r["routine_mse"] for r in bloat_rows]
    x_lbl = [f"{r['irrelevant_dims']} irr\n({b:.1f} KB)" for r, b in zip(bloat_rows, kb)]
    ax1.bar(x_lbl, ops_k, width=0.45, color="#e67e22", alpha=0.82, label="Maintenance Ops (k)")
    ax1.set_ylabel("Total Maintenance & Update Ops (thousands)", color="#e67e22")
    ax1.set_xlabel("Irrelevant Retained Memory Dimensions (Raw Size)")
    ax2 = ax1.twinx()
    ax2.plot(x_lbl, rmses, color="#8e44ad", marker="o", lw=2.2, ms=7, label="Routine MSE (worse ->)")
    ax2.set_ylabel("Routine Prediction MSE", color="#8e44ad")
    ax1.set_title("Raw Retained Memory Size vs Maintenance Burden & Error")

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "exp09_inertia_and_sufficiency.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 106)
    print("EXPERIMENT 9 (v0.2) — TIMESPACE TRAJECTORIES & INFORMATIONAL INERTIA (LC-15, LC-16, H9)")
    print("=" * 106)

    cfg = TimespaceConfig(
        d_relevant=4,
        d_irrelevant=36,
        num_steps=1800,
        shift_steps=(600, 1200),
        obs_noise_std=0.35,
        seed=909,
    )
    ds = generate_timespace_stream(cfg)
    primary: Dict[str, TimespaceRunResult] = {}
    for m in MODES:
        primary[m] = run_timespace_system(ds, m)

    print(
        f"\n{'System':<28} {'Mem(B)':>7} {'Ops':>9} {'RoutMSE':>8} {'ShftMSE':>8} "
        f"{'ActAcc':>7} {'Rout D_H':>9} {'Shft D_H':>9} {'Jump/Jit':>9} {'AdaptT':>7} {'Resets'}"
    )
    print("-" * 112)
    for m in MODES:
        r = primary[m]
        print(
            f"{m:<28} {r.memory_bytes:>7,} {r.ledger.total_cost.steps:>9,} "
            f"{r.routine_mse:>8.4f} {r.post_shift_mse:>8.4f} {r.action_accuracy*100:>6.2f}% "
            f"{r.mean_routine_hellinger:>9.5f} {r.mean_shift_hellinger:>9.5f} "
            f"{r.jump_to_jitter_ratio:>8.2f}x {str(round(r.shift_adaptation_steps, 1) if r.shift_adaptation_steps else None):>7} "
            f"{r.canary_resets}"
        )

    # Sweep 1: Prior observation count N_0 (informational inertia)
    print("\nSweep 1 — Prior Observation Count N_0 (Informational Inertia):")
    prior_rows: List[Dict[str, Any]] = []
    ds_prior = generate_timespace_stream(
        TimespaceConfig(d_relevant=4, d_irrelevant=0, num_steps=1000, shift_steps=(400,), seed=910)
    )
    for n0 in (10, 50, 200, 1000):
        for mode in ("naive_infinite_memory", "living_canary_memory"):
            r = run_timespace_system(ds_prior, mode, prior_obs_override=n0)
            row = r.summary()
            row["prior_obs_count"] = n0
            prior_rows.append(row)
            print(
                f"  N_0={n0:>4} | {mode:<24} | rout_D_H={r.mean_routine_hellinger:.5f} | "
                f"post_shift_mse={r.post_shift_mse:.4f} | adapt={r.shift_adaptation_steps}"
            )

    # Sweep 2: Raw retained memory size (irrelevant dimensions) vs sufficiency & maintenance cost
    print("\nSweep 2 — Raw Memory Size (Irrelevant Dims) vs Maintenance Burden & Predictive Sufficiency:")
    bloat_rows: List[Dict[str, Any]] = []
    ds_bloat = generate_timespace_stream(
        TimespaceConfig(d_relevant=4, d_irrelevant=60, num_steps=1200, shift_steps=(600,), seed=911)
    )
    for n_irr in (0, 10, 30, 60):
        r = run_timespace_system(ds_bloat, "bloated_irrelevant_memory", irrelevant_dims_override=n_irr)
        row = r.summary()
        row["irrelevant_dims"] = n_irr
        bloat_rows.append(row)
        print(
            f"  irr={n_irr:>2} (D={4+n_irr:>2}, mem={r.memory_bytes:>6,} B) | "
            f"ops={r.ledger.total_cost.steps:>10,} | rout_mse={r.routine_mse:.4f} | post_mse={r.post_shift_mse:.4f}"
        )

    make_plots(primary, prior_rows, bloat_rows, cfg.shift_steps)

    payload = {
        "experiment_version": "v0.2",
        "config": cfg.__dict__,
        "primary": {m: primary[m].summary() for m in MODES},
        "prior_inertia_sweep": prior_rows,
        "memory_bloat_sweep": bloat_rows,
    }
    (RESULTS_DIR / "exp09_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nArtifacts saved to: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
