#!/usr/bin/env python3
"""exp_hw03 — Physical Temporal Advantage Break-Even & Real-World Transfer Validation.

Objectives:
  1. Dense K-transition mapping (K in {1, 2, 3, 5, 8, 12, 16, 25, 40, 80}) on the
     Paper I 1,000-node DAG with pinned Python 3.11.7 runtime, N = 8 interleaved
     independently seeded blocks, and dual-layer Apple M3 Max telemetry
     (process CPU PMU `ri_energy_nj` + whole-SoC `IOReport` `CPU+GPU+ANE+DRAM+DCS+AMCC`).
  2. Out-of-sample predictive physical break-even model:
     Fit primitives strictly on K_train = {1, 25, 80} and predict ΔE(K) and exact
     break-even K* OUT-OF-SAMPLE on held-out K_test = {2, 3, 5, 8, 12, 16, 40}.
  3. Independently sourced, non-synthetic real-world workload:
     117 real Python 3.11 standard-library modules (~2.1 MiB, 236 real import edges)
     incremental AST static-analysis pipeline comparing `full_rebuild`,
     `strong_incremental_dag`, and `certified_ast_canary` (0 mismatches) across
     API-breaking churn rates q in {0.00, 0.10, 0.25, 0.50, 0.75, 1.00}, including
     FULL LIFECYCLE cold-start corpus indexing + out-of-domain predictive model transfer.

Preserves `living-computation/`, `exp_hw01`, `exp_hw02`, and `crr_breakeven` untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
import gc
import json
import math
import os
import random
import statistics
import sys
import time

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
LC_ROOT = (TS_ROOT / "../living-computation").resolve()
HW01_DIR = TS_ROOT / "experiments" / "hw_energy_paper01"
HW02_DIR = TS_ROOT / "experiments" / "hw_soc_paper02"
for p in (LC_ROOT, HW01_DIR, HW02_DIR, EXP_DIR):
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
from real_ast_workload import (
    RealASTAnalysisEngine,
    build_import_graph,
    discover_stdlib_corpus,
    generate_real_edit_stream,
)
from predictive_model import (
    evaluate_out_of_sample_dag,
    evaluate_real_ast_transfer_model,
    fit_physical_dag_energy_model,
)

RESULTS_DIR = EXP_DIR / "results"
N_BLOCKS = 8
ALL_KS = (1, 2, 3, 5, 8, 12, 16, 25, 40, 80)
TRAIN_KS = {1, 25, 80}
TEST_KS = [k for k in ALL_KS if k not in TRAIN_KS]
AST_QS = (0.00, 0.10, 0.25, 0.50, 0.75, 1.00)


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


def _make_granularity_graph(k_iters: int) -> DependencyGraph:
    graph = build_milestone_network()
    if k_iters <= 1:
        return graph
    for node in graph.nodes:
        if node.op.value == "input":
            continue
        orig_eval = node.evaluate

        def _wrap(fn: Callable, k: int) -> Callable:
            def _wrapped(values):
                val = fn(values)
                acc = val
                for j in range(1, k):
                    acc = (acc * 0.999999 + 1e-9 * j) - (acc * 0.999999 + 1e-9 * j) + val
                return val + (acc - val) * 0.0
            return _wrapped

        node.evaluate = _wrap(orig_eval, k_iters)  # type: ignore[method-assign]
    return graph


def run_part_a_dense_k_sweep(ior: IOReportEnergyReader, em: EnergyModel) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Part A: Dense K transition (K=1,2,3,5,8,12,16,25,40,80) over N=8 paired blocks (5,000 updates/run).

    For K <= 5, runs 2 consecutive identical passes inside one measurement window so the integration
    window exceeds ~0.5-1.0s and divides measured energies by 2 (reporting exact per-5,000-update energy).
    """
    print(f"[Part A] Dense K-transition sweep across {ALL_KS} ({N_BLOCKS} paired blocks x 5,000 updates)...")
    base_g = build_milestone_network()
    rng = random.Random(303)

    # Pre-generate 8 independent seeded workloads (5,000 updates each) + exact ground-truth outputs
    workloads = []
    for b in range(N_BLOCKS):
        seed_b = 3000 + b * 29
        env = WorkloadEnvironment(
            base_g.input_ids,
            WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=5_000, seed=seed_b),
        )
        init_in, evs = env.generate()
        ref = FullRecomputeEngine(base_g, energy_model=em).run(init_in, evs)
        workloads.append((seed_b, init_in, evs, ref))

    rows_summary: List[Dict[str, Any]] = []
    raw_by_k: Dict[str, Any] = {}

    for k in ALL_KS:
        g = _make_granularity_graph(k)
        reps = 2 if k <= 5 else 1

        # Warm-up pass
        ConventionalIncrementalEngine(g, energy_model=em).run(workloads[0][1], workloads[0][2][:500])

        inc_rows, liv_rows = [], []
        for b, (seed_b, init_in, evs, ref) in enumerate(workloads):
            order = ["inc", "liv"]
            rng.shuffle(order)
            for tag in order:
                gc.collect()
                s0 = snapshot_dual(ior)
                last_eng = None
                for _ in range(reps):
                    if tag == "inc":
                        eng = ConventionalIncrementalEngine(g, energy_model=em)
                    else:
                        eng = LivingTraceContractEngine(
                            g,
                            energy_model=em,
                            warmup_steps=150,
                            trace_policy=TracePolicy.SURPRISE_DRIVEN,
                            enable_regime_cache=True,
                            adaptive_retirement=False,
                        )
                    out = eng.run(init_in, evs)
                    if hasattr(eng, "close"):
                        eng.close()
                    mismatches = sum(1 for r, c in zip(ref, out) if abs(r - c) > 1e-12)
                    assert mismatches == 0, f"Soundness mismatch at K={k} block {b} {tag}"
                    last_eng = eng
                s1 = snapshot_dual(ior)
                proc, soc = delta_dual(ior, s0, s1)
                assert soc is not None and last_eng is not None
                lsum = last_eng.ledger.summary()
                rec = {
                    "block": b,
                    "seed": seed_b,
                    "reps_in_window": reps,
                    "window_wall_s": proc.wall_time_s,
                    "wall_time_s": proc.wall_time_s / reps,
                    "proc_cpu_energy_j": proc.hardware_energy_j / reps,
                    "instructions": proc.instructions / reps,
                    "soc_cpu_j": soc.soc_cpu_j / reps,
                    "soc_memory_j": soc.soc_memory_j / reps,
                    "soc_package_j": soc.soc_package_j / reps,
                    "abstract_ops": lsum["total_cost"]["steps"],
                    "exec_nodes_eval": lsum["by_category"]["execution"]["steps"],
                    "mismatches": 0,
                }
                (inc_rows if tag == "inc" else liv_rows).append(rec)

        metrics = ("abstract_ops", "wall_time_s", "proc_cpu_energy_j", "instructions", "soc_cpu_j", "soc_memory_j", "soc_package_j")
        paired = {m: _paired_stats([r[m] for r in inc_rows], [r[m] for r in liv_rows]) for m in metrics}
        inc_nodes_mean = statistics.mean([r["exec_nodes_eval"] for r in inc_rows])
        liv_nodes_mean = statistics.mean([r["exec_nodes_eval"] for r in liv_rows])
        nodes_avoided = inc_nodes_mean - liv_nodes_mean

        row = {
            "k_granularity": k,
            "split": "train" if k in TRAIN_KS else "test_heldout",
            "reps_in_window": reps,
            "mean_window_wall_s": round(statistics.mean([r["window_wall_s"] for r in inc_rows]), 3),
            "inc_nodes_eval_mean": round(inc_nodes_mean, 1),
            "liv_nodes_eval_mean": round(liv_nodes_mean, 1),
            "nodes_avoided_mean": round(nodes_avoided, 1),
            "inc_mean": {m: round(statistics.mean([r[m] for r in inc_rows]), 6) for m in metrics},
            "liv_mean": {m: round(statistics.mean([r[m] for r in liv_rows]), 6) for m in metrics},
            "paired": paired,
        }
        rows_summary.append(row)
        raw_by_k[f"K{k}"] = {"inc": inc_rows, "liv": liv_rows}
        print(
            f"  K={k:2d} [{row['split']:12s}] (win={row['mean_window_wall_s']:.2f}s): "
            f"proc_E={paired['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{paired['proc_cpu_energy_j']['paired_pct_ci95']:.2f} (p={paired['proc_cpu_energy_j']['p_value']:.4f}) | "
            f"SoC_pkg={paired['soc_package_j']['paired_pct_mean']:+6.2f}%±{paired['soc_package_j']['paired_pct_ci95']:.2f} (p={paired['soc_package_j']['p_value']:.4f}) | "
            f"SoC_mem={paired['soc_memory_j']['paired_pct_mean']:+6.2f}%"
        )

    return rows_summary, raw_by_k


def run_part_b_real_ast_workload(ior: IOReportEnergyReader) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Part B: Real-World 117-Module Python 3.11 Stdlib AST Incremental Analysis Pipeline."""
    print(f"\n[Part B] Real-world 117-module Python stdlib AST workload ({N_BLOCKS} paired blocks x 20 edits)...")
    stdlib_root = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    sources = discover_stdlib_corpus(stdlib_root)
    deps, rev, order = build_import_graph(sources)
    total_edges = sum(len(v) for v in deps.values())
    total_kb = round(sum(len(s.encode("utf-8")) for s in sources.values()) / 1024.0, 1)
    print(f"  Corpus: {len(sources)} real stdlib .py modules ({total_kb} KiB), {total_edges} real import edges.")

    rng = random.Random(404)

    # 1. Full-rebuild comparison on 5 edits x N_BLOCKS (to quantify full_rebuild vs inc vs canary with 0 mismatches)
    full_comp_rows: Dict[str, List[Dict[str, Any]]] = {"full_rebuild": [], "strong_incremental_dag": [], "certified_ast_canary": []}
    for b in range(N_BLOCKS):
        eds5 = generate_real_edit_stream(sources, rev, num_edits=5, api_break_prob=0.20, seed=5000 + b * 19)
        modes = ["full_rebuild", "strong_incremental_dag", "certified_ast_canary"]
        rng.shuffle(modes)
        fps: Dict[str, List[str]] = {}
        for mode in modes:
            gc.collect()
            s0 = snapshot_dual(ior)
            eng = RealASTAnalysisEngine(mode, sources, rev, order)
            fp = eng.run_full_lifecycle(eds5)
            s1 = snapshot_dual(ior)
            proc, soc = delta_dual(ior, s0, s1)
            assert soc is not None
            fps[mode] = fp
            full_comp_rows[mode].append(
                {
                    "block": b,
                    "wall_time_s": proc.wall_time_s,
                    "proc_cpu_energy_j": proc.hardware_energy_j,
                    "instructions": proc.instructions,
                    "soc_cpu_j": soc.soc_cpu_j,
                    "soc_memory_j": soc.soc_memory_j,
                    "soc_package_j": soc.soc_package_j,
                    "modules_analyzed_total": eng.modules_analyzed_setup + eng.modules_analyzed_edits,
                    "modules_avoided": eng.modules_avoided,
                }
            )
        assert fps["full_rebuild"] == fps["strong_incremental_dag"] == fps["certified_ast_canary"], "AST mismatch!"

    metrics = ("wall_time_s", "proc_cpu_energy_j", "instructions", "soc_cpu_j", "soc_memory_j", "soc_package_j")
    full_vs_canary = {
        m: _paired_stats([r[m] for r in full_comp_rows["full_rebuild"]], [r[m] for r in full_comp_rows["certified_ast_canary"]])
        for m in metrics
    }
    print(
        "  Real AST (5 edits, q=0.20) canary vs full_rebuild: "
        f"proc_E={full_vs_canary['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{full_vs_canary['proc_cpu_energy_j']['paired_pct_ci95']:.2f}, "
        f"SoC_pkg={full_vs_canary['soc_package_j']['paired_pct_mean']:+6.2f}%±{full_vs_canary['soc_package_j']['paired_pct_ci95']:.2f}"
    )

    # 2. Full API-breaking churn sweep q in {0.00, 0.10, 0.25, 0.50, 0.75, 1.00} (20 edits x N_BLOCKS, full lifecycle!)
    q_summaries: List[Dict[str, Any]] = []
    raw_by_q: Dict[str, Any] = {}
    for q in AST_QS:
        inc_rows, can_rows = [], []
        for b in range(N_BLOCKS):
            eds20 = generate_real_edit_stream(sources, rev, num_edits=20, api_break_prob=q, seed=6000 + int(q * 100) * 100 + b * 23)
            modes = ["strong_incremental_dag", "certified_ast_canary"]
            rng.shuffle(modes)
            fps = {}
            for mode in modes:
                gc.collect()
                s0 = snapshot_dual(ior)
                eng = RealASTAnalysisEngine(mode, sources, rev, order)
                fp = eng.run_full_lifecycle(eds20)
                s1 = snapshot_dual(ior)
                proc, soc = delta_dual(ior, s0, s1)
                assert soc is not None
                fps[mode] = fp
                rec = {
                    "block": b,
                    "wall_time_s": proc.wall_time_s,
                    "proc_cpu_energy_j": proc.hardware_energy_j,
                    "instructions": proc.instructions,
                    "soc_cpu_j": soc.soc_cpu_j,
                    "soc_memory_j": soc.soc_memory_j,
                    "soc_package_j": soc.soc_package_j,
                    "modules_analyzed_setup": eng.modules_analyzed_setup,
                    "modules_analyzed_edits": eng.modules_analyzed_edits,
                    "modules_avoided": eng.modules_avoided,
                    "canaries_safe": eng.canaries_safe,
                    "canaries_checked": eng.canaries_checked,
                }
                (inc_rows if mode == "strong_incremental_dag" else can_rows).append(rec)
            assert fps["strong_incremental_dag"] == fps["certified_ast_canary"], f"AST mismatch at q={q} b={b}"

        paired_inc = {m: _paired_stats([r[m] for r in inc_rows], [r[m] for r in can_rows]) for m in metrics}
        q_row = {
            "api_break_prob": q,
            "split": "train_endpoint" if q in (0.0, 1.0) else "test_heldout",
            "modules_avoided_mean": round(statistics.mean([r["modules_avoided"] for r in can_rows]), 1),
            "safe_hit_rate": round(
                statistics.mean([r["canaries_safe"] / max(1, r["canaries_checked"]) for r in can_rows]), 4
            ),
            "inc_mean": {m: round(statistics.mean([r[m] for r in inc_rows]), 6) for m in metrics},
            "can_mean": {m: round(statistics.mean([r[m] for r in can_rows]), 6) for m in metrics},
            "paired_vs_incremental": paired_inc,
        }
        q_summaries.append(q_row)
        raw_by_q[f"q{q:.2f}"] = {"inc": inc_rows, "canary": can_rows}
        print(
            f"  q={q:4.2f} [{q_row['split']:14s}] (avoided={q_row['modules_avoided_mean']:5.1f} mods): "
            f"proc_E={paired_inc['proc_cpu_energy_j']['paired_pct_mean']:+6.2f}%±{paired_inc['proc_cpu_energy_j']['paired_pct_ci95']:.2f} (p={paired_inc['proc_cpu_energy_j']['p_value']:.4f}) | "
            f"SoC_pkg={paired_inc['soc_package_j']['paired_pct_mean']:+6.2f}%±{paired_inc['soc_package_j']['paired_pct_ci95']:.2f} (p={paired_inc['soc_package_j']['p_value']:.4f})"
        )

    part_b = {
        "corpus": {
            "source": "Python 3.11 standard library (email, http, urllib, unittest, json, logging, collections, importlib)",
            "num_modules": len(sources),
            "num_import_edges": total_edges,
            "total_source_kib": total_kb,
            "mismatches_total": 0,
        },
        "five_edit_full_rebuild_comparison": {
            "canary_vs_full_rebuild": full_vs_canary,
            "full_mean_proc_j": round(statistics.mean([r["proc_cpu_energy_j"] for r in full_comp_rows["full_rebuild"]]), 4),
            "inc_mean_proc_j": round(statistics.mean([r["proc_cpu_energy_j"] for r in full_comp_rows["strong_incremental_dag"]]), 4),
            "canary_mean_proc_j": round(statistics.mean([r["proc_cpu_energy_j"] for r in full_comp_rows["certified_ast_canary"]]), 4),
            "full_mean_soc_j": round(statistics.mean([r["soc_package_j"] for r in full_comp_rows["full_rebuild"]]), 4),
            "canary_mean_soc_j": round(statistics.mean([r["soc_package_j"] for r in full_comp_rows["certified_ast_canary"]]), 4),
        },
        "api_break_sweep_20_edits_full_lifecycle": q_summaries,
    }
    return part_b, {"five_edit_full": full_comp_rows, "q_sweep": raw_by_q}


def generate_figures(
    dag_rows: List[Dict[str, Any]],
    m_proc: Dict[str, Any],
    ev_proc: Dict[str, Any],
    m_soc: Dict[str, Any],
    ev_soc: Dict[str, Any],
    part_b: Dict[str, Any],
    ast_mod_proc: Dict[str, Any],
    ast_mod_soc: Dict[str, Any],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Figure 1: Dense K Transition & Out-of-Sample Predictive Physical Break-Even Model ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.3))
    ks = np.array([r["k_granularity"] for r in dag_rows], dtype=float)
    k_smooth = np.geomspace(1.0, 80.0, 200)

    # Left: ΔE (Joules) Observed vs Out-of-Sample Model Prediction
    for m_obj, ekey, col, lbl in (
        (m_proc, "proc_cpu_energy_j", "#2f855a", "Process CPU PMU (ri_energy_nj)"),
        (m_soc, "soc_package_j", "#dd6b20", "Whole-SoC Package (CPU+GPU+ANE+Mem)"),
    ):
        y_obs = np.array([r["paired"][ekey]["paired_diff_mean"] for r in dag_rows])
        y_ci = np.array([r["paired"][ekey]["paired_diff_ci95"] for r in dag_rows])
        train_mask = np.array([r["k_granularity"] in TRAIN_KS for r in dag_rows])
        y_pred_line = m_obj["delta_intercept_j"] + m_obj["delta_slope_j_per_k"] * k_smooth

        ax1.plot(k_smooth, y_pred_line, "--", color=col, linewidth=1.8, alpha=0.85,
                 label=f"{lbl} Model (K*={m_obj['k_star_pred']:.2f})")
        ax1.errorbar(ks[train_mask], y_obs[train_mask], yerr=y_ci[train_mask], fmt="s", markersize=7,
                     color=col, capsize=3, label=f"{lbl} Train (K=1,25,80)")
        ax1.errorbar(ks[~train_mask], y_obs[~train_mask], yerr=y_ci[~train_mask], fmt="o", markersize=6.5,
                     markerfacecolor="white", markeredgewidth=2.0, color=col, capsize=3, label=f"{lbl} Held-Out Test")
    ax1.axhline(0, color="black", linewidth=0.9)
    ax1.set_xscale("log")
    ax1.set_xticks(ks)
    ax1.set_xticklabels([str(int(x)) for x in ks], fontsize=8.5)
    ax1.set_xlabel("Node Compute Granularity K (Log Scale)")
    ax1.set_ylabel("Paired Energy Saved ΔE = E_inc - E_living (J / 5,000 updates)")
    ax1.set_title(f"A. Dense K Transition & Out-of-Sample Fit (Proc R²={ev_proc['r2_joules']:.3f}, SoC R²={ev_soc['r2_joules']:.3f})")
    ax1.legend(fontsize=7.3, loc="upper left")
    ax1.grid(alpha=0.3)

    # Right: Percentage Savings Across Transition K=1..80
    for ekey, col, mk, lbl in (
        ("abstract_ops", "#2b6cb0", "x", "Abstract Ops (%)"),
        ("proc_cpu_energy_j", "#2f855a", "D", "Process CPU PMU (%)"),
        ("soc_package_j", "#dd6b20", "s", "Whole-SoC Package Raw (%)"),
        ("soc_memory_j", "#805ad5", "^", "Whole-SoC Memory+Fabric (%)"),
    ):
        ys = [r["paired"][ekey]["paired_pct_mean"] for r in dag_rows]
        cis = [r["paired"][ekey]["paired_pct_ci95"] for r in dag_rows]
        ax2.errorbar(ks, ys, yerr=cis, marker=mk, capsize=3, linewidth=1.9, color=col, label=lbl)
    ax2.axhline(0, color="black", linewidth=0.9)
    ax2.set_xscale("log")
    ax2.set_xticks(ks)
    ax2.set_xticklabels([str(int(x)) for x in ks], fontsize=8.5)
    ax2.set_xlabel("Node Compute Granularity K (Log Scale)")
    ax2.set_ylabel("Paired Savings vs Strong Incremental ± 95% t-CI (%)")
    ax2.set_title("B. Dense Transition Curve (K=1..80, Pinned Python 3.11.7, N=8)")
    ax2.legend(fontsize=8.2, loc="lower right")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig1_dense_k_transition_and_model.png", dpi=160)
    plt.close(fig)

    # --- Figure 2: Real-World 117-Module Stdlib AST Workload & Out-of-Domain Model Transfer ---
    q_rows = part_b["api_break_sweep_20_edits_full_lifecycle"]
    qs = np.array([r["api_break_prob"] for r in q_rows])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.4, 5.2))
    # Left: Percentage energy savings across API-breaking rate q (Full Lifecycle!)
    for ekey, col, mk, lbl in (
        ("proc_cpu_energy_j", "#2f855a", "D", "Process CPU PMU (%)"),
        ("soc_package_j", "#dd6b20", "s", "Whole-SoC Package Raw (%)"),
        ("soc_memory_j", "#805ad5", "^", "Whole-SoC Memory+Fabric (%)"),
        ("wall_time_s", "#2b6cb0", "o", "Wall-Clock Time (%)"),
    ):
        ys = [r["paired_vs_incremental"][ekey]["paired_pct_mean"] for r in q_rows]
        cis = [r["paired_vs_incremental"][ekey]["paired_pct_ci95"] for r in q_rows]
        ax1.errorbar(qs, ys, yerr=cis, marker=mk, capsize=3, linewidth=2.0, color=col, label=lbl)
    ax1.axhline(0, color="black", linewidth=0.9)
    ax1.set_xlabel("API-Breaking Edit Rate q (0=Private Refactors, 1=All API Breaks)")
    ax1.set_ylabel("Full-Lifecycle Savings vs Strong Incremental ± 95% t-CI (%)")
    ax1.set_title("A. Real-World 117-Module Python Stdlib AST Analysis (Full Lifecycle)")
    ax1.legend(fontsize=8.2)
    ax1.grid(alpha=0.3)

    # Right: Observed vs Out-of-Sample Predicted ΔE (J) on Real-World AST Workload
    for amod, ekey, col, lbl in (
        (ast_mod_proc, "proc_cpu_energy_j", "#2f855a", "Process CPU PMU"),
        (ast_mod_soc, "soc_package_j", "#dd6b20", "Whole-SoC Package"),
    ):
        obs_d = [r["paired_vs_incremental"][ekey]["paired_diff_mean"] for r in q_rows]
        obs_ci = [r["paired_vs_incremental"][ekey]["paired_diff_ci95"] for r in q_rows]
        pred_d = [
            r["modules_avoided_mean"] * amod["e_per_avoided_module_j"] - amod["e_canary_overhead_j"]
            for r in q_rows
        ]
        ax2.errorbar(qs, obs_d, yerr=obs_ci, fmt="o", capsize=3, color=col, label=f"{lbl} Observed (N=8)")
        ax2.plot(qs, pred_d, "--", linewidth=2.0, color=col,
                 label=f"{lbl} Model (OOS R²={amod['out_of_sample_r2']:.3f}, q*={amod['q_star_pred']:.2f})")
    ax2.axhline(0, color="black", linewidth=0.9)
    ax2.set_xlabel("API-Breaking Edit Rate q (Fit on q=0,1; Tested on q=0.10,0.25,0.50,0.75)")
    ax2.set_ylabel("Net Full-Lifecycle Energy Saved ΔE (Joules)")
    ax2.set_title("B. Out-of-Domain Transfer of Break-Even Equation to Real Stdlib AST")
    ax2.legend(fontsize=8.0)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_real_stdlib_ast_transfer.png", dpi=160)
    plt.close(fig)

    # --- Figure 3: Out-of-Sample Predicted vs Observed Parity Plot (Both Synthetic DAG & Real AST!) ---
    fig, ax = plt.subplots(figsize=(7.6, 6.2))
    # DAG held-out test points
    dag_obs_p = [x["obs_delta_j"] for x in ev_proc["per_k"]]
    dag_prd_p = [x["pred_delta_j"] for x in ev_proc["per_k"]]
    dag_obs_s = [x["obs_delta_j"] for x in ev_soc["per_k"]]
    dag_prd_s = [x["pred_delta_j"] for x in ev_soc["per_k"]]
    # AST held-out test points
    ast_obs_p = [x["obs_delta_j"] for x in ast_mod_proc["per_q"]]
    ast_prd_p = [x["pred_delta_j"] for x in ast_mod_proc["per_q"]]
    ast_obs_s = [x["obs_delta_j"] for x in ast_mod_soc["per_q"]]
    ast_prd_s = [x["pred_delta_j"] for x in ast_mod_soc["per_q"]]

    all_vals = dag_obs_p + dag_prd_p + dag_obs_s + dag_prd_s + ast_obs_p + ast_prd_p + ast_obs_s + ast_prd_s
    lo, hi = min(all_vals) - 0.5, max(all_vals) + 0.5
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=1.2, alpha=0.7, label="Perfect Prediction (y = x)")
    ax.scatter(dag_prd_p, dag_obs_p, s=65, marker="o", color="#2f855a", label=f"DAG Held-Out K (Proc CPU, R²={ev_proc['r2_joules']:.3f})")
    ax.scatter(dag_prd_s, dag_obs_s, s=65, marker="s", color="#dd6b20", label=f"DAG Held-Out K (Whole-SoC, R²={ev_soc['r2_joules']:.3f})")
    ax.scatter(ast_prd_p, ast_obs_p, s=85, marker="D", color="#2b6cb0", label=f"Real Stdlib AST Held-Out q (Proc CPU, R²={ast_mod_proc['out_of_sample_r2']:.3f})")
    ax.scatter(ast_prd_s, ast_obs_s, s=85, marker="^", color="#805ad5", label=f"Real Stdlib AST Held-Out q (Whole-SoC, R²={ast_mod_soc['out_of_sample_r2']:.3f})")
    ax.axhline(0, color="gray", linewidth=0.7, alpha=0.5)
    ax.axvline(0, color="gray", linewidth=0.7, alpha=0.5)
    ax.set_xlabel("Model-Predicted Energy Saved ΔE_pred (Joules)")
    ax.set_ylabel("Directly Measured Hardware Energy Saved ΔE_obs (Joules)")
    ax.set_title("exp_hw03 Out-of-Sample Parity: Synthetic DAG + Real 117-Module Stdlib AST")
    ax.legend(fontsize=8.2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig3_oos_prediction_diagnostics.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ior = IOReportEnergyReader()
    meta = get_soc_machine_metadata()
    start_ctx = get_system_context()
    calib = run_linearity_calibration()
    print(f"Hardware: {meta['cpu_brand']} | Python {meta['python_version']} | load1m={start_ctx['loadavg_1m']} | {start_ctx['pmset_batt']}")
    print(f"Linearity: 4x/1x energy={calib['ratio_4x_vs_1x_energy']}x, inst={calib['ratio_4x_vs_1x_instructions']}x")

    em = EnergyModel()
    dag_rows, dag_raw = run_part_a_dense_k_sweep(ior, em)

    train_rows = [r for r in dag_rows if r["k_granularity"] in TRAIN_KS]
    test_rows = [r for r in dag_rows if r["k_granularity"] not in TRAIN_KS]
    m_proc = fit_physical_dag_energy_model(train_rows, "proc_cpu_energy_j")
    ev_proc = evaluate_out_of_sample_dag(m_proc, test_rows)
    m_soc = fit_physical_dag_energy_model(train_rows, "soc_package_j")
    ev_soc = evaluate_out_of_sample_dag(m_soc, test_rows)

    print(
        f"\n[Model Part A — DAG Out-of-Sample on K={TEST_KS}]\n"
        f"  Proc CPU : K*_pred={m_proc['k_star_pred']}, OOS R²={ev_proc['r2_joules']}, MAE={ev_proc['mae_joules']:.4f} J ({ev_proc['mae_pct_pts']:.2f} pct-pts), sign_acc={ev_proc['sign_accuracy']}\n"
        f"  Whole-SoC: K*_pred={m_soc['k_star_pred']}, OOS R²={ev_soc['r2_joules']}, MAE={ev_soc['mae_joules']:.4f} J ({ev_soc['mae_pct_pts']:.2f} pct-pts), sign_acc={ev_soc['sign_accuracy']}"
    )

    part_b, ast_raw = run_part_b_real_ast_workload(ior)
    ast_rows = part_b["api_break_sweep_20_edits_full_lifecycle"]
    ast_mod_proc = evaluate_real_ast_transfer_model(ast_rows, "proc_cpu_energy_j")
    ast_mod_soc = evaluate_real_ast_transfer_model(ast_rows, "soc_package_j")
    print(
        f"\n[Model Part B — Real Stdlib AST Out-of-Sample on q=0.10,0.25,0.50,0.75]\n"
        f"  Proc CPU : q*_pred={ast_mod_proc['q_star_pred']}, OOS R²={ast_mod_proc['out_of_sample_r2']}, MAE={ast_mod_proc['out_of_sample_mae_j']:.4f} J ({ast_mod_proc['out_of_sample_mae_pct_pts']:.2f} pct-pts)\n"
        f"  Whole-SoC: q*_pred={ast_mod_soc['q_star_pred']}, OOS R²={ast_mod_soc['out_of_sample_r2']}, MAE={ast_mod_soc['out_of_sample_mae_j']:.4f} J ({ast_mod_soc['out_of_sample_mae_pct_pts']:.2f} pct-pts)"
    )

    end_ctx = get_system_context()
    generate_figures(dag_rows, m_proc, ev_proc, m_soc, ev_soc, part_b, ast_mod_proc, ast_mod_soc)

    (RESULTS_DIR / "exp_hw03_raw_blocks.json").write_text(
        json.dumps({"part_a_dag_raw": dag_raw, "part_b_real_ast_raw": ast_raw}, indent=2),
        encoding="utf-8",
    )
    summary = {
        "experiment_id": "exp_hw03_physical_breakeven_and_transfer",
        "version": "0.1.0",
        "n_blocks": N_BLOCKS,
        "machine": meta,
        "system_context_start": start_ctx,
        "system_context_end": end_ctx,
        "calibration": calib,
        "part_a_dense_k_sweep": dag_rows,
        "part_a_predictive_model": {
            "proc_cpu_energy_j": {"fit": m_proc, "out_of_sample_eval": ev_proc},
            "soc_package_j": {"fit": m_soc, "out_of_sample_eval": ev_soc},
        },
        "part_b_real_stdlib_ast": part_b,
        "part_b_transfer_model": {
            "proc_cpu_energy_j": ast_mod_proc,
            "soc_package_j": ast_mod_soc,
        },
    }
    sum_p = RESULTS_DIR / "exp_hw03_summary.json"
    sum_p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved exp_hw03 summary -> {sum_p}")


if __name__ == "__main__":
    main()
