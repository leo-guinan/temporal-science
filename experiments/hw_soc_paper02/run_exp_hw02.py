#!/usr/bin/env python3
"""Whole-SoC Energy Validation for Paper I (`exp_hw02`, Apple M3 Max).

Tests whether Paper I's measured per-process CPU energy advantage (`exp_hw01`)
survives under a broader Apple M3 Max whole-SoC accounting boundary capturing:
  - Process-isolated CPU hardware PMU energy (`proc_pid_rusage` `ri_energy_nj`)
  - Whole-SoC CPU complex (`IOReport` `CPU Energy`)
  - Whole-SoC Memory & Cache Fabric (`IOReport` `DRAM0 + DCS0 + AMCC0`)
  - Whole-SoC Package Combined (`CPU + GPU + ANE + DRAM0 + DCS0 + AMCC0`)
  - Local-idle-subtracted incremental SoC energy (paired per-block idle bracketing)

Experimental Design & Controls:
  - N = 10 interleaved, independently seeded blocks (seed = 2026 + b * 17) per condition
  - Randomized condition order inside every block b = 0..9
  - Local idle bracketing (0.5 s idle window before + after each block)
  - Dedicated 10-pair telemetry-overhead control (with vs without IOReport active)
  - Background load (`getloadavg`) & thermal pressure (`pmset -g therm`) logging
  - Exact 0-mismatch verification against FullRecomputeEngine on every single block
  - Paired statistics: mean paired diff, 95% Student-t CI (df = N-1), paired Cohen's dz,
    and two-sided paired t-test p-value (scipy.stats.ttest_rel)

Campaigns:
  C1 (Core Regimes, 10,000 updates x 10 blocks):
      - localized_regime_drift: full, incremental, in-memory reuse, disk-logged reuse
      - high_entropy_shock    : incremental, static reuse, adaptive retirement
  C2 (Granularity Scaling, 3,000 updates x 10 blocks):
      - K in {1, 5, 20, 80}: incremental vs in-memory reuse (+ full at K=1)
  C3 (Concentrated Shock Crossover, 3,000 updates x 10 blocks):
      - p in {0.00, 0.04, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, 0.30}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import gc
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
LC_ROOT = (TS_ROOT / "../living-computation").resolve()
HW01_DIR = TS_ROOT / "experiments" / "hw_energy_paper01"
for p in (LC_ROOT, HW01_DIR, EXP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("MPLCONFIGDIR", "/tmp/temporal_science_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats as sp_stats

from core import (
    ConventionalIncrementalEngine,
    EnergyModel,
    FullRecomputeEngine,
    LivingTraceContractEngine,
    TracePolicy,
    WorkloadConfig,
    WorkloadEnvironment,
    WorkloadRegime,
    build_milestone_network,
)
from core.dependency_graph import DependencyGraph
from telemetry_macos import run_linearity_calibration
from telemetry_soc_macos import (
    IOReportEnergyReader,
    delta_dual,
    get_soc_machine_metadata,
    get_system_context,
    snapshot_dual,
)

RESULTS_DIR = EXP_DIR / "results"
N_BLOCKS = 10


def _t_ci95(values: List[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    sd = statistics.stdev(values)
    tcrit = float(sp_stats.t.ppf(0.975, df=n - 1))
    return tcrit * sd / math.sqrt(n)


def _agg_t(values: List[float]) -> Dict[str, float]:
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 6),
        "std": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
        "ci95": round(_t_ci95(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def _paired_stats(base_vals: List[float], cand_vals: List[float]) -> Dict[str, Any]:
    """Paired block-by-block comparison: positive diff means cand SAVED resource vs base."""
    assert len(base_vals) == len(cand_vals) and len(base_vals) >= 2
    diffs = [b - c for b, c in zip(base_vals, cand_vals)]
    pcts = [100.0 * (b - c) / b if abs(b) > 1e-12 else 0.0 for b, c in zip(base_vals, cand_vals)]
    mean_d = statistics.mean(diffs)
    sd_d = statistics.stdev(diffs)
    ci_d = _t_ci95(diffs)
    dz = (mean_d / sd_d) if sd_d > 1e-12 else (float("inf") if abs(mean_d) > 0 else 0.0)
    if sd_d > 1e-12:
        t_stat, p_val = sp_stats.ttest_rel(base_vals, cand_vals)
        p_val_f = float(p_val)
        t_stat_f = float(t_stat)
    else:
        t_stat_f = 0.0
        p_val_f = 1.0
    mean_base = statistics.mean(base_vals)
    mean_cand = statistics.mean(cand_vals)
    ratio_sav_pct = 100.0 * (mean_base - mean_cand) / mean_base if abs(mean_base) > 1e-12 else 0.0
    return {
        "base_mean": round(mean_base, 6),
        "cand_mean": round(mean_cand, 6),
        "paired_diff_mean": round(mean_d, 6),
        "paired_diff_ci95": round(ci_d, 6),
        "paired_pct_mean": round(statistics.mean(pcts), 3),
        "paired_pct_ci95": round(_t_ci95(pcts), 3),
        "ratio_savings_pct": round(ratio_sav_pct, 3),
        "cohens_dz": round(dz, 3) if math.isfinite(dz) else 999.0,
        "t_stat": round(t_stat_f, 3),
        "p_value": round(p_val_f, 6),
        "significant_005": bool(p_val_f < 0.05 and (mean_d - ci_d) * (mean_d + ci_d) > 0),
    }


def _make_granularity_graph(k_iters: int) -> DependencyGraph:
    graph = build_milestone_network()
    if k_iters <= 1:
        return graph
    for node in graph.nodes:
        if node.op.value == "input":
            continue
        orig_eval = node.evaluate

        def _make_wrapped(fn: Callable, k: int) -> Callable:
            def _wrapped(values):
                val = fn(values)
                acc = val
                for j in range(1, k):
                    acc = (acc * 0.999999 + 1e-9 * j) - (acc * 0.999999 + 1e-9 * j) + val
                return val + (acc - val) * 0.0
            return _wrapped

        node.evaluate = _make_wrapped(orig_eval, k_iters)  # type: ignore[method-assign]
    return graph


def _measure_idle_power(ior: IOReportEnergyReader, duration_s: float = 0.40) -> Dict[str, float]:
    """Sample quiet idle SoC power over `duration_s` to bracket a trial block."""
    gc.collect()
    s0 = snapshot_dual(ior)
    time.sleep(duration_s)
    s1 = snapshot_dual(ior)
    proc, soc = delta_dual(ior, s0, s1)
    assert soc is not None
    w = max(proc.wall_time_s, 1e-9)
    return {
        "duration_s": round(w, 4),
        "idle_soc_cpu_w": soc.soc_cpu_j / w,
        "idle_soc_compute_w": soc.soc_compute_j / w,
        "idle_soc_memory_w": soc.soc_memory_j / w,
        "idle_soc_package_w": soc.soc_package_j / w,
        "idle_soc_all_w": soc.soc_all_exposed_j / w,
    }


def _run_one_measured(
    ior: Optional[IOReportEnergyReader],
    factory: Callable[[], Any],
    init_inputs: Dict[int, float],
    events: List[Any],
    ref_outputs: List[float],
    idle_w: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    gc.collect()
    eng = factory()
    s0 = snapshot_dual(ior)
    outputs = eng.run(init_inputs, events)
    if hasattr(eng, "close"):
        eng.close()
    s1 = snapshot_dual(ior)
    proc, soc = delta_dual(ior, s0, s1)
    summary = eng.ledger.summary()

    mismatches = sum(1 for r, c in zip(ref_outputs, outputs) if abs(r - c) > 1e-12)
    assert mismatches == 0, f"Soundness mismatch detected: {mismatches}"

    rec: Dict[str, Any] = {
        "wall_time_s": proc.wall_time_s,
        "user_time_s": proc.user_time_s,
        "system_time_s": proc.system_time_s,
        "proc_cpu_energy_j": proc.hardware_energy_j,
        "proc_pcore_energy_j": proc.pcore_energy_j,
        "instructions": proc.instructions,
        "cycles": proc.cycles,
        "ipc": proc.ipc,
        "disk_bytes_written": proc.disk_bytes_written,
        "logical_writes_bytes": proc.logical_writes_bytes,
        "abstract_ops": summary["total_cost"]["steps"],
        "modeled_proxy_j": summary["total_cost"]["joules"],
        "mismatches": mismatches,
    }
    if soc is not None:
        rec["soc_cpu_j"] = soc.soc_cpu_j
        rec["soc_gpu_j"] = soc.soc_gpu_j
        rec["soc_ane_j"] = soc.soc_ane_j
        rec["soc_compute_j"] = soc.soc_compute_j
        rec["soc_dram_j"] = soc.soc_dram_j
        rec["soc_dcs_j"] = soc.soc_dcs_j
        rec["soc_amcc_j"] = soc.soc_amcc_j
        rec["soc_memory_j"] = soc.soc_memory_j
        rec["soc_package_j"] = soc.soc_package_j
        rec["soc_disp_media_io_j"] = soc.soc_disp_media_io_j
        rec["soc_all_exposed_j"] = soc.soc_all_exposed_j
        if idle_w is not None:
            dt = proc.wall_time_s
            rec["soc_cpu_net_j"] = soc.soc_cpu_j - idle_w["idle_soc_cpu_w"] * dt
            rec["soc_compute_net_j"] = soc.soc_compute_j - idle_w["idle_soc_compute_w"] * dt
            rec["soc_memory_net_j"] = soc.soc_memory_j - idle_w["idle_soc_memory_w"] * dt
            rec["soc_package_net_j"] = soc.soc_package_j - idle_w["idle_soc_package_w"] * dt
    return rec


def run_measurement_overhead_control(ior: IOReportEnergyReader, energy_model: EnergyModel) -> Dict[str, Any]:
    """Quantify exact overhead of IOReport sampling over 10 paired interleaved trials."""
    print("[Control 0] Running 10-pair telemetry measurement overhead control...")
    g = build_milestone_network()
    env = WorkloadEnvironment(
        g.input_ids, WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=3_000, seed=9001)
    )
    init_in, evs = env.generate()
    ref = FullRecomputeEngine(g, energy_model=energy_model).run(init_in, evs)
    rng = random.Random(42)

    no_ior_rows, with_ior_rows = [], []
    # Warm-up
    _run_one_measured(None, lambda: ConventionalIncrementalEngine(g, energy_model=energy_model), init_in, evs, ref)

    for _ in range(N_BLOCKS):
        pair = [False, True]
        rng.shuffle(pair)
        for use_ior in pair:
            r = _run_one_measured(
                ior if use_ior else None,
                lambda: ConventionalIncrementalEngine(g, energy_model=energy_model),
                init_in,
                evs,
                ref,
            )
            (with_ior_rows if use_ior else no_ior_rows).append(r)

    wall_cmp = _paired_stats([r["wall_time_s"] for r in no_ior_rows], [r["wall_time_s"] for r in with_ior_rows])
    e_cmp = _paired_stats([r["proc_cpu_energy_j"] for r in no_ior_rows], [r["proc_cpu_energy_j"] for r in with_ior_rows])
    print(
        f"  IOReport overhead: Δwall={-wall_cmp['paired_diff_mean']*1e3:+.3f} ms "
        f"(p={wall_cmp['p_value']:.3f}), Δproc_E={-e_cmp['paired_diff_mean']*1e3:+.3f} mJ (p={e_cmp['p_value']:.3f})"
    )
    return {
        "n_pairs": N_BLOCKS,
        "without_ioreport_wall_s": _agg_t([r["wall_time_s"] for r in no_ior_rows]),
        "with_ioreport_wall_s": _agg_t([r["wall_time_s"] for r in with_ior_rows]),
        "without_ioreport_proc_e_j": _agg_t([r["proc_cpu_energy_j"] for r in no_ior_rows]),
        "with_ioreport_proc_e_j": _agg_t([r["proc_cpu_energy_j"] for r in with_ior_rows]),
        "paired_wall_comparison": wall_cmp,
        "paired_proc_energy_comparison": e_cmp,
    }


def run_blocked_suite(
    ior: IOReportEnergyReader,
    name: str,
    graph_fn: Callable[[], DependencyGraph],
    regime: WorkloadRegime,
    num_updates: int,
    variant_factories: Callable[[DependencyGraph, int, Path], Dict[str, Callable[[], Any]]],
    energy_model: EnergyModel,
    tmp_dir: Path,
    n_blocks: int = N_BLOCKS,
    shock_probability: Optional[float] = None,
    idle_duration_s: float = 0.35,
) -> Dict[str, Any]:
    """Execute `n_blocks` independently seeded, interleaved, idle-bracketed trial blocks."""
    graph = graph_fn()
    rng = random.Random(hash(name) & 0xFFFFFFFF)

    # Discarded warm-up block
    w_cfg = WorkloadConfig(
        regime=regime,
        num_updates=min(1_000, num_updates),
        seed=1999,
        **({"shock_probability": shock_probability} if shock_probability is not None else {}),
    )
    w_in, w_ev = WorkloadEnvironment(graph.input_ids, w_cfg).generate()
    w_ref = FullRecomputeEngine(graph, energy_model=energy_model).run(w_in, w_ev)
    for fn in variant_factories(graph, -1, tmp_dir).values():
        _run_one_measured(ior, fn, w_in, w_ev, w_ref)

    per_variant_blocks: Dict[str, List[Dict[str, Any]]] = {}
    idle_blocks: List[Dict[str, float]] = []
    block_contexts: List[Dict[str, Any]] = []

    for b in range(n_blocks):
        seed_b = 2026 + b * 17
        cfg = WorkloadConfig(
            regime=regime,
            num_updates=num_updates,
            seed=seed_b,
            **({"shock_probability": shock_probability} if shock_probability is not None else {}),
        )
        init_in, evs = WorkloadEnvironment(graph.input_ids, cfg).generate()
        ref = FullRecomputeEngine(graph, energy_model=energy_model).run(init_in, evs)

        factories = variant_factories(graph, b, tmp_dir)
        vnames = list(factories.keys())
        for vn in vnames:
            per_variant_blocks.setdefault(vn, [])

        idle_pre = _measure_idle_power(ior, duration_s=idle_duration_s)
        ctx = get_system_context()
        order = list(vnames)
        rng.shuffle(order)

        block_raw: Dict[str, Dict[str, Any]] = {}
        for vn in order:
            block_raw[vn] = _run_one_measured(ior, factories[vn], init_in, evs, ref, idle_w=None)

        idle_post = _measure_idle_power(ior, duration_s=idle_duration_s)
        idle_avg = {
            k: 0.5 * (idle_pre[k] + idle_post[k])
            for k in ("idle_soc_cpu_w", "idle_soc_compute_w", "idle_soc_memory_w", "idle_soc_package_w", "idle_soc_all_w")
        }
        idle_blocks.append(idle_avg)
        block_contexts.append({"block": b, "seed": seed_b, "order": order, "load1m": ctx["loadavg_1m"]})

        # Compute paired local-idle-subtracted net SoC energies for every variant in block b
        for vn in vnames:
            r = block_raw[vn]
            dt = r["wall_time_s"]
            r["block"] = b
            r["seed"] = seed_b
            r["soc_cpu_net_j"] = r["soc_cpu_j"] - idle_avg["idle_soc_cpu_w"] * dt
            r["soc_compute_net_j"] = r["soc_compute_j"] - idle_avg["idle_soc_compute_w"] * dt
            r["soc_memory_net_j"] = r["soc_memory_j"] - idle_avg["idle_soc_memory_w"] * dt
            r["soc_package_net_j"] = r["soc_package_j"] - idle_avg["idle_soc_package_w"] * dt
            per_variant_blocks[vn].append(r)

    # Summarize per-variant metrics & paired comparisons vs `strong_incremental` (and `full_recompute` if present)
    metrics_keys = (
        "abstract_ops",
        "modeled_proxy_j",
        "wall_time_s",
        "proc_cpu_energy_j",
        "instructions",
        "cycles",
        "ipc",
        "disk_bytes_written",
        "soc_cpu_j",
        "soc_compute_j",
        "soc_memory_j",
        "soc_dram_j",
        "soc_dcs_j",
        "soc_amcc_j",
        "soc_package_j",
        "soc_cpu_net_j",
        "soc_memory_net_j",
        "soc_package_net_j",
    )
    variants_summary: Dict[str, Any] = {}
    for vn, rows in per_variant_blocks.items():
        variants_summary[vn] = {
            "mismatches_total": sum(r["mismatches"] for r in rows),
            **{k: _agg_t([float(r[k]) for r in rows]) for k in metrics_keys},
        }

    compare_metrics = (
        "abstract_ops",
        "modeled_proxy_j",
        "wall_time_s",
        "proc_cpu_energy_j",
        "instructions",
        "soc_cpu_j",
        "soc_compute_j",
        "soc_memory_j",
        "soc_package_j",
        "soc_cpu_net_j",
        "soc_package_net_j",
    )
    paired_vs_inc: Dict[str, Any] = {}
    if "strong_incremental" in per_variant_blocks:
        inc_rows = per_variant_blocks["strong_incremental"]
        for vn, rows in per_variant_blocks.items():
            if vn == "strong_incremental":
                continue
            paired_vs_inc[vn] = {
                m: _paired_stats([float(r[m]) for r in inc_rows], [float(r[m]) for r in rows])
                for m in compare_metrics
            }

    paired_vs_full: Dict[str, Any] = {}
    if "full_recompute" in per_variant_blocks:
        full_rows = per_variant_blocks["full_recompute"]
        for vn, rows in per_variant_blocks.items():
            if vn == "full_recompute":
                continue
            paired_vs_full[vn] = {
                m: _paired_stats([float(r[m]) for r in full_rows], [float(r[m]) for r in rows])
                for m in compare_metrics
            }

    return {
        "suite_name": name,
        "n_blocks": n_blocks,
        "num_updates": num_updates,
        "shock_probability": shock_probability,
        "idle_power_w": {
            k: _agg_t([ib[k] for ib in idle_blocks])
            for k in ("idle_soc_cpu_w", "idle_soc_compute_w", "idle_soc_memory_w", "idle_soc_package_w")
        },
        "block_contexts": block_contexts,
        "variants": variants_summary,
        "paired_vs_incremental": paired_vs_inc,
        "paired_vs_full": paired_vs_full,
        "raw_blocks": per_variant_blocks,
    }


def generate_figures(
    c1_loc: Dict[str, Any],
    c1_shk: Dict[str, Any],
    c2_gran: List[Dict[str, Any]],
    c3_sweep: List[Dict[str, Any]],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Figure 1: Process CPU Energy vs Whole-SoC Package Energy (Raw & Idle-Subtracted) across Conditions ---
    cond_specs = [
        ("In-Mem Reuse\n(vs Full)", c1_loc["paired_vs_full"]["living_inmem_surprise"]),
        ("In-Mem Reuse\n(vs Inc)", c1_loc["paired_vs_incremental"]["living_inmem_surprise"]),
        ("Disk-Logged\n(vs Inc)", c1_loc["paired_vs_incremental"]["living_disk_jsonl_surprise"]),
        ("High-Entropy\nStatic (vs Inc)", c1_shk["paired_vs_incremental"]["living_static_no_retire"]),
        ("High-Entropy\nRetire (vs Inc)", c1_shk["paired_vs_incremental"]["living_adaptive_retire"]),
    ]
    fig, ax = plt.subplots(figsize=(12.2, 5.4))
    x = np.arange(len(cond_specs))
    w = 0.19
    series = [
        ("abstract_ops", "Abstract Ops (%)", "#2b6cb0"),
        ("proc_cpu_energy_j", "Process CPU PMU (ri_energy_nj %)", "#2f855a"),
        ("soc_package_j", "Whole-SoC Package Raw (CPU+GPU+ANE+Mem %)", "#dd6b20"),
        ("soc_package_net_j", "Whole-SoC Package Idle-Subtracted (%)", "#805ad5"),
    ]
    for idx, (mkey, label, color) in enumerate(series):
        means = [c[mkey]["paired_pct_mean"] for _, c in cond_specs]
        errs = [c[mkey]["paired_pct_ci95"] for _, c in cond_specs]
        ax.bar(x + (idx - 1.5) * w, means, w, yerr=errs, capsize=3, color=color, label=label, alpha=0.92)
    ax.axhline(0, color="black", linewidth=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([lbl for lbl, _ in cond_specs], fontsize=9)
    ax.set_ylabel("Paired Energy / Op Savings ± 95% t-CI (%)")
    ax.set_title("exp_hw02 (N=10 Paired Blocks): Process CPU Energy vs Whole-SoC Package Energy (Apple M3 Max)")
    ax.legend(loc="lower left", fontsize=8.5)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig1_soc_vs_process_regimes.png", dpi=160)
    plt.close(fig)

    # --- Figure 2: Concentrated Shock Crossover (p = 0.00..0.30, N=10 Blocks) ---
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    ps = [r["shock_probability"] for r in c3_sweep]
    for mkey, label, col, mk, ls in (
        ("abstract_ops", "Abstract Ops (%)", "#2b6cb0", "o", "--"),
        ("proc_cpu_energy_j", "Process CPU PMU (ri_energy_nj %)", "#2f855a", "D", "-"),
        ("soc_package_j", "Whole-SoC Package Raw (%)", "#dd6b20", "s", "-."),
        ("soc_package_net_j", "Whole-SoC Package Idle-Subtracted (%)", "#805ad5", "^", ":"),
    ):
        ys = np.array([r["paired_vs_incremental"]["living_inmem_surprise"][mkey]["paired_pct_mean"] for r in c3_sweep])
        ci = np.array([r["paired_vs_incremental"]["living_inmem_surprise"][mkey]["paired_pct_ci95"] for r in c3_sweep])
        ax.plot(ps, ys, marker=mk, linestyle=ls, linewidth=2.0, color=col, label=label)
        if mkey in ("proc_cpu_energy_j", "soc_package_j"):
            ax.fill_between(ps, ys - ci, ys + ci, color=col, alpha=0.14)
    ax.axvspan(0.07, 0.11, color="#fefcbf", alpha=0.5, label="Concentrated Crossover Band (p=0.07-0.11)")
    ax.axhline(0, color="black", linewidth=0.9)
    ax.set_xlabel("Per-Step Shock Probability p (10 Independently Seeded Blocks per Point)")
    ax.set_ylabel("Paired Savings vs Strong Incremental ± 95% t-CI (%)")
    ax.set_title("exp_hw02: Concentrated Shock-Crossover Validation (Process PMU vs Whole-SoC Energy)")
    ax.legend(fontsize=8.2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_soc_crossover_concentrated.png", dpi=160)
    plt.close(fig)

    # --- Figure 3: Granularity Scaling (K=1, 5, 20, 80) + Whole-SoC Rail Decomposition ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2))
    ks = [r["k_granularity"] for r in c2_gran]
    for mkey, label, col, mk, ls in (
        ("abstract_ops", "Abstract Ops (%)", "#2b6cb0", "o", "--"),
        ("proc_cpu_energy_j", "Process CPU PMU (%)", "#2f855a", "D", "-"),
        ("soc_cpu_j", "SoC CPU Complex (%)", "#38a169", "^", "-."),
        ("soc_memory_j", "SoC Memory+Fabric (DRAM+DCS+AMCC %)", "#d69e2e", "v", ":"),
        ("soc_package_j", "Whole-SoC Package Raw (%)", "#dd6b20", "s", "-"),
    ):
        ys = [r["paired_vs_incremental"]["living_inmem_surprise"][mkey]["paired_pct_mean"] for r in c2_gran]
        errs = [r["paired_vs_incremental"]["living_inmem_surprise"][mkey]["paired_pct_ci95"] for r in c2_gran]
        ax1.errorbar(ks, ys, yerr=errs, marker=mk, linestyle=ls, capsize=3, linewidth=2.0, color=col, label=label)
    ax1.axhline(0, color="black", linewidth=0.9)
    ax1.set_xscale("log")
    ax1.set_xticks(ks)
    ax1.set_xticklabels([f"K={k}" for k in ks])
    ax1.set_xlabel("Node Compute Granularity K (K=1 is unmodified Paper I)")
    ax1.set_ylabel("Paired Savings vs Strong Incremental ± 95% t-CI (%)")
    ax1.set_title("A. Granularity Scaling Across Process & Whole-SoC Rails (N=10)")
    ax1.legend(fontsize=7.8)
    ax1.grid(alpha=0.3)

    # Right: Stacked rail breakdown (Joules per 10,000 updates in localized_regime_drift)
    sys_order = ["strong_incremental", "living_inmem_surprise", "living_disk_jsonl_surprise"]
    sys_labels = ["Strong Incremental", "In-Mem Certified Reuse", "Disk-Logged Reuse"]
    cpu_j = [c1_loc["variants"][s]["soc_cpu_j"]["mean"] for s in sys_order]
    mem_j = [c1_loc["variants"][s]["soc_memory_j"]["mean"] for s in sys_order]
    gpu_ane_j = [
        c1_loc["variants"][s]["soc_compute_j"]["mean"] - c1_loc["variants"][s]["soc_cpu_j"]["mean"]
        for s in sys_order
    ]
    proc_j = [c1_loc["variants"][s]["proc_cpu_energy_j"]["mean"] for s in sys_order]
    xs = np.arange(len(sys_order))
    ax2.bar(xs - 0.18, proc_j, 0.32, color="#2f855a", label="Process CPU PMU (ri_energy_nj)")
    ax2.bar(xs + 0.18, cpu_j, 0.32, color="#dd6b20", label="Whole-SoC CPU Complex")
    ax2.bar(xs + 0.18, mem_j, 0.32, bottom=cpu_j, color="#d69e2e", label="Whole-SoC Memory (DRAM+DCS+AMCC)")
    ax2.bar(xs + 0.18, gpu_ane_j, 0.32, bottom=np.array(cpu_j) + np.array(mem_j), color="#805ad5", label="Whole-SoC GPU+ANE")
    ax2.set_xticks(xs)
    ax2.set_xticklabels(sys_labels, fontsize=8.8)
    ax2.set_ylabel("Mean Energy per 10,000 Updates (Joules)")
    ax2.set_title("B. Process CPU vs Whole-SoC Rail Decomposition (Localized Drift)")
    ax2.legend(fontsize=7.8)
    ax2.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig3_soc_granularity_and_rails.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ior = IOReportEnergyReader()
    meta = get_soc_machine_metadata()
    start_ctx = get_system_context()
    calib = run_linearity_calibration()
    print(f"Hardware: {meta['cpu_brand']} ({meta['logical_cores']} cores) | load1m={start_ctx['loadavg_1m']}")
    print(f"Process PMU linearity: 4x/1x energy={calib['ratio_4x_vs_1x_energy']}x, inst={calib['ratio_4x_vs_1x_instructions']}x")

    em = EnergyModel()
    overhead_ctrl = run_measurement_overhead_control(ior, em)

    with tempfile.TemporaryDirectory(prefix="exp_hw02_") as td:
        tdir = Path(td)

        # Campaign 1A: localized_regime_drift (10 blocks x 10,000 updates)
        print(f"[C1A] localized_regime_drift ({N_BLOCKS} interleaved blocks x 10,000 updates)...")
        def _loc_factories(g: DependencyGraph, b: int, td_p: Path) -> Dict[str, Callable[[], Any]]:
            dp = td_p / f"disk_trace_b{b}.jsonl"
            def _mk_disk():
                if dp.exists():
                    dp.unlink()
                return LivingTraceContractEngine(
                    g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                    trace_path=dp, enable_regime_cache=True, adaptive_retirement=False,
                    name="living_disk_jsonl_surprise",
                )
            return {
                "full_recompute": lambda: FullRecomputeEngine(g, energy_model=em),
                "strong_incremental": lambda: ConventionalIncrementalEngine(g, energy_model=em),
                "living_inmem_surprise": lambda: LivingTraceContractEngine(
                    g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                    trace_path=None, enable_regime_cache=True, adaptive_retirement=False,
                    name="living_inmem_surprise",
                ),
                "living_disk_jsonl_surprise": _mk_disk,
            }

        c1_loc = run_blocked_suite(
            ior, "c1_localized_regime_drift", build_milestone_network,
            WorkloadRegime.LOCALIZED_REGIME_DRIFT, 10_000, _loc_factories, em, tdir, n_blocks=N_BLOCKS,
        )
        for vn in ("living_inmem_surprise", "living_disk_jsonl_surprise"):
            p = c1_loc["paired_vs_incremental"][vn]
            print(
                f"  {vn:28s} vs inc: "
                f"proc_E={p['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{p['proc_cpu_energy_j']['paired_pct_ci95']:.2f} (p={p['proc_cpu_energy_j']['p_value']:.4f}) | "
                f"SoC_pkg={p['soc_package_j']['paired_pct_mean']:+6.2f}%±{p['soc_package_j']['paired_pct_ci95']:.2f} (p={p['soc_package_j']['p_value']:.4f}) | "
                f"SoC_net={p['soc_package_net_j']['paired_pct_mean']:+6.2f}%±{p['soc_package_net_j']['paired_pct_ci95']:.2f}"
            )

        # Campaign 1B: high_entropy_shock (10 blocks x 10,000 updates)
        print(f"[C1B] high_entropy_shock ({N_BLOCKS} interleaved blocks x 10,000 updates)...")
        def _shk_factories(g: DependencyGraph, b: int, td_p: Path) -> Dict[str, Callable[[], Any]]:
            return {
                "strong_incremental": lambda: ConventionalIncrementalEngine(g, energy_model=em),
                "living_static_no_retire": lambda: LivingTraceContractEngine(
                    g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                    enable_regime_cache=True, adaptive_retirement=False, name="living_static_no_retire",
                ),
                "living_adaptive_retire": lambda: LivingTraceContractEngine(
                    g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                    enable_regime_cache=True, adaptive_retirement=True,
                    retire_min_checks=40, retire_min_hit_rate=0.35, name="living_adaptive_retire",
                ),
            }

        c1_shk = run_blocked_suite(
            ior, "c1_high_entropy_shock", build_milestone_network,
            WorkloadRegime.HIGH_ENTROPY_SHOCK, 10_000, _shk_factories, em, tdir, n_blocks=N_BLOCKS,
        )
        for vn in ("living_static_no_retire", "living_adaptive_retire"):
            p = c1_shk["paired_vs_incremental"][vn]
            print(
                f"  {vn:28s} vs inc: "
                f"proc_E={p['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{p['proc_cpu_energy_j']['paired_pct_ci95']:.2f} | "
                f"SoC_pkg={p['soc_package_j']['paired_pct_mean']:+6.2f}%±{p['soc_package_j']['paired_pct_ci95']:.2f}"
            )

        # Campaign 2: Granularity scaling K in {1, 5, 20, 80} (10 blocks x 3,000 updates)
        print(f"[C2] Node granularity scaling K=1, 5, 20, 80 ({N_BLOCKS} interleaved blocks x 3,000 updates)...")
        c2_gran: List[Dict[str, Any]] = []
        for k in (1, 5, 20, 80):
            def _gran_factories(g: DependencyGraph, b: int, td_p: Path, kk: int = k) -> Dict[str, Callable[[], Any]]:
                d = {
                    "strong_incremental": lambda: ConventionalIncrementalEngine(g, energy_model=em),
                    "living_inmem_surprise": lambda: LivingTraceContractEngine(
                        g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                        enable_regime_cache=True, adaptive_retirement=False, name="living_inmem_surprise",
                    ),
                }
                if kk == 1:
                    d["full_recompute"] = lambda: FullRecomputeEngine(g, energy_model=em)
                return d

            res_k = run_blocked_suite(
                ior, f"c2_granularity_K{k}", lambda kk=k: _make_granularity_graph(kk),
                WorkloadRegime.LOCALIZED_REGIME_DRIFT, 3_000, _gran_factories, em, tdir,
                n_blocks=N_BLOCKS, idle_duration_s=0.25,
            )
            res_k["k_granularity"] = k
            c2_gran.append(res_k)
            p = res_k["paired_vs_incremental"]["living_inmem_surprise"]
            print(
                f"  K={k:2d}: proc_E={p['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{p['proc_cpu_energy_j']['paired_pct_ci95']:.2f} "
                f"(dz={p['proc_cpu_energy_j']['cohens_dz']:+.2f}, p={p['proc_cpu_energy_j']['p_value']:.4f}) | "
                f"SoC_pkg={p['soc_package_j']['paired_pct_mean']:+6.2f}%±{p['soc_package_j']['paired_pct_ci95']:.2f} "
                f"(dz={p['soc_package_j']['cohens_dz']:+.2f}, p={p['soc_package_j']['p_value']:.4f}) | "
                f"SoC_mem={p['soc_memory_j']['paired_pct_mean']:+6.2f}%"
            )

        # Campaign 3: Concentrated shock crossover around p ≈ 0.08–0.10 (10 blocks x 3,000 updates)
        print(f"[C3] Concentrated shock-crossover sweep ({N_BLOCKS} interleaved blocks x 3,000 updates)...")
        c3_sweep: List[Dict[str, Any]] = []
        for prob in (0.00, 0.04, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, 0.30):
            def _sw_factories(g: DependencyGraph, b: int, td_p: Path) -> Dict[str, Callable[[], Any]]:
                return {
                    "strong_incremental": lambda: ConventionalIncrementalEngine(g, energy_model=em),
                    "living_inmem_surprise": lambda: LivingTraceContractEngine(
                        g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                        enable_regime_cache=True, adaptive_retirement=False, name="living_inmem_surprise",
                    ),
                }

            res_p = run_blocked_suite(
                ior, f"c3_shock_p{prob:.2f}", build_milestone_network,
                WorkloadRegime.LOCALIZED_REGIME_DRIFT, 3_000, _sw_factories, em, tdir,
                n_blocks=N_BLOCKS, shock_probability=prob, idle_duration_s=0.20,
            )
            c3_sweep.append(res_p)
            p = res_p["paired_vs_incremental"]["living_inmem_surprise"]
            print(
                f"  p={prob:4.2f}: ops={p['abstract_ops']['paired_pct_mean']:+6.2f}% | "
                f"proc_E={p['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{p['proc_cpu_energy_j']['paired_pct_ci95']:.2f} "
                f"(p={p['proc_cpu_energy_j']['p_value']:.4f}) | "
                f"SoC_pkg={p['soc_package_j']['paired_pct_mean']:+6.2f}%±{p['soc_package_j']['paired_pct_ci95']:.2f} "
                f"(p={p['soc_package_j']['p_value']:.4f})"
            )

    end_ctx = get_system_context()
    generate_figures(c1_loc, c1_shk, c2_gran, c3_sweep)

    # Save raw telemetry separately from compact summary so raw blocks are auditable
    raw_out = RESULTS_DIR / "exp_hw02_raw_blocks.json"
    raw_out.write_text(
        json.dumps(
            {
                "c1_localized_regime_drift": c1_loc["raw_blocks"],
                "c1_high_entropy_shock": c1_shk["raw_blocks"],
                "c2_granularity": {f"K{r['k_granularity']}": r["raw_blocks"] for r in c2_gran},
                "c3_shock_sweep": {f"p{r['shock_probability']:.2f}": r["raw_blocks"] for r in c3_sweep},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def _strip_raw(d: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in d.items() if k != "raw_blocks"}

    summary_payload = {
        "experiment_id": "exp_hw02_whole_soc_apple_m3_max",
        "version": "0.1.0",
        "n_blocks_per_condition": N_BLOCKS,
        "machine": meta,
        "system_context_start": start_ctx,
        "system_context_end": end_ctx,
        "calibration": calib,
        "measurement_overhead_control": overhead_ctrl,
        "c1_localized_regime_drift": _strip_raw(c1_loc),
        "c1_high_entropy_shock": _strip_raw(c1_shk),
        "c2_granularity_scaling": [_strip_raw(r) for r in c2_gran],
        "c3_concentrated_shock_crossover": [_strip_raw(r) for r in c3_sweep],
    }
    sum_out = RESULTS_DIR / "exp_hw02_summary.json"
    sum_out.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(f"\nSaved summary -> {sum_out}")
    print(f"Saved raw telemetry -> {raw_out}")


if __name__ == "__main__":
    main()
