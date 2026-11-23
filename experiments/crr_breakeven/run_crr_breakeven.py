#!/usr/bin/env python3
"""CRR Research Coordination Break-Even Experiment (Apple Silicon M3 Max).

Compares three fair research repository architectures across 6 standardized
coordination tasks (T1-T6), measuring machine wall time, Apple M3 Max hardware
CPU energy (`proc_pid_rusage(RUSAGE_INFO_V6)` -> `ri_energy_nj`), retired
instructions, storage footprint, and scientific correctness (T3 transitive
impact recall + T4 6-class defect detection).

Explicitly separates:
  - Directly measured machine-only automation cost (seconds, hardware Joules, bytes)
  - Objective structural effort (files scanned, metadata lines authored/edited)
  - Parametric analytical human-time break-even contours (clearly labeled NOT measured human data)

Preserves `../living-computation/` and existing `temporal-science/` CRR v0.2
baselines strictly untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import gc
import json
import math
import os
import random
import shutil
import statistics
import sys
import tempfile

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
HW_EXP_DIR = TS_ROOT / "experiments" / "hw_energy_paper01"
TOOLS_DIR = TS_ROOT / "tools"
for p in (EXP_DIR, HW_EXP_DIR, TOOLS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("MPLCONFIGDIR", "/tmp/temporal_science_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import research as crr  # type: ignore
from telemetry_macos import (
    delta_sample,
    get_machine_metadata,
    run_linearity_calibration,
    snapshot_raw,
)
from workloads import (
    ResearchGraphSpec,
    directory_size_bytes,
    generate_heldout_graph,
    load_real_temporal_science_spec,
    materialize_conventional_repo,
    materialize_crr_v02_repo,
    materialize_modular_manual_repo,
)
from conditions import (
    DEFECT_TYPES,
    ground_truth_transitive_impact,
    inject_defect,
    task_t1_reproduce,
    task_t2_locate_assumptions,
    task_t3_impact_analysis,
    task_t4_detect_defects,
    task_t5_assemble_and_verify_bundle,
    task_t6_incorporate_new_claim,
)

RESULTS_DIR = EXP_DIR / "results"
CONDITIONS = ("conventional", "modular_manual", "crr_v02")


def _agg(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {"mean": 0.0, "std": 0.0, "ci95": 0.0}
    mean = statistics.mean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
    return {"mean": round(mean, 7), "std": round(std, 7), "ci95": round(ci95, 7)}


def _measure_fn(fn: Callable[[], Any]) -> Tuple[Dict[str, Any], Any]:
    gc.collect()
    s0 = snapshot_raw()
    out = fn()
    s1 = snapshot_raw()
    d = delta_sample(s0, s1)
    return (
        {
            "wall_time_s": d.wall_time_s,
            "user_time_s": d.user_time_s,
            "system_time_s": d.system_time_s,
            "hardware_energy_j": d.hardware_energy_j,
            "instructions": d.instructions,
            "cycles": d.cycles,
        },
        out,
    )


def _setup_workspace(condition: str, root: Path, spec: ResearchGraphSpec) -> Dict[str, Any]:
    """Measure full setup/indexing cost C_setup for a condition (including CRR initial validate+build)."""
    def _do_setup() -> Dict[str, int]:
        if condition == "conventional":
            return materialize_conventional_repo(root, spec)
        if condition == "modular_manual":
            return materialize_modular_manual_repo(root, spec)
        if condition == "crr_v02":
            stats = materialize_crr_v02_repo(root, spec)
            ok, errs, _ = crr.validate_repository(root)
            assert ok, f"CRR clean setup validation failed on {spec.name}: {errs}"
            for pid in sorted(spec.papers.keys()):
                crr.build_paper(pid, repo_root=root)
            return stats
        raise ValueError(condition)

    m, stats = _measure_fn(_do_setup)
    m["storage_bytes"] = directory_size_bytes(root)
    m["authored_metadata_lines"] = stats["authored_metadata_lines"]
    m["authored_metadata_bytes"] = stats["authored_metadata_bytes"]
    return m


def evaluate_graph_suite(
    spec: ResearchGraphSpec,
    n_trials: int = 5,
    seed: int = 500,
    run_defect_suite: bool = True,
) -> Dict[str, Any]:
    """Run Setup + Tasks T1-T6 + Correctness/Defect analysis across all 3 conditions on `spec`."""
    rng = random.Random(seed)
    first_paper = sorted(spec.papers.keys())[0]
    last_paper = sorted(spec.papers.keys())[-1]
    target_root_cid = spec.claims[0].cid
    target_mid_cid = spec.claims[min(1, len(spec.claims) - 1)].cid
    parent_for_t6 = spec.claims[0]
    gt_downstream, gt_papers = ground_truth_transitive_impact(spec, target_root_cid)

    with tempfile.TemporaryDirectory(prefix=f"crr_bench_{spec.name}_") as td:
        base = Path(td)
        roots = {c: base / c for c in CONDITIONS}

        # 1. Setup measurement (N=3 interleaved passes for stable setup time/energy, keeping final workspace)
        setup_runs: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CONDITIONS}
        for _ in range(min(3, n_trials)):
            order = list(CONDITIONS)
            rng.shuffle(order)
            for cond in order:
                setup_runs[cond].append(_setup_workspace(cond, roots[cond], spec))

        setup_summary: Dict[str, Any] = {}
        for cond in CONDITIONS:
            rows = setup_runs[cond]
            setup_summary[cond] = {
                "wall_time_s": _agg([r["wall_time_s"] for r in rows]),
                "hardware_energy_j": _agg([r["hardware_energy_j"] for r in rows]),
                "instructions": _agg([float(r["instructions"]) for r in rows]),
                "storage_bytes": rows[-1]["storage_bytes"],
                "authored_metadata_lines": rows[-1]["authored_metadata_lines"],
                "authored_metadata_bytes": rows[-1]["authored_metadata_bytes"],
            }

        # 2. Measure Tasks T1, T2, T3 (strong equal-outcome), T4 (clean check), T5 (portable bundle)
        task_names = ("T1_reproduce", "T2_locate", "T3_impact", "T4_validate_clean", "T5_bundle")
        raw_tasks: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
            c: {t: [] for t in task_names} for c in CONDITIONS
        }
        task_meta: Dict[str, Dict[str, Any]] = {c: {} for c in CONDITIONS}

        # 1 warm-up pass
        for cond in CONDITIONS:
            task_t1_reproduce(cond, roots[cond], first_paper)
            task_t2_locate_assumptions(cond, roots[cond], target_mid_cid)
            task_t3_impact_analysis(cond, roots[cond], target_root_cid, single_pass_grep=False)
            task_t4_detect_defects(cond, roots[cond], first_paper)
            task_t5_assemble_and_verify_bundle(cond, roots[cond], first_paper)

        for _ in range(n_trials):
            order = list(CONDITIONS)
            rng.shuffle(order)
            for cond in order:
                r1, o1 = _measure_fn(lambda c=cond: task_t1_reproduce(c, roots[c], first_paper))
                raw_tasks[cond]["T1_reproduce"].append(r1)
                task_meta[cond]["T1_reproduce"] = o1

                r2, o2 = _measure_fn(lambda c=cond: task_t2_locate_assumptions(c, roots[c], target_mid_cid))
                raw_tasks[cond]["T2_locate"].append(r2)
                task_meta[cond]["T2_locate"] = o2

                r3, o3 = _measure_fn(
                    lambda c=cond: task_t3_impact_analysis(c, roots[c], target_root_cid, single_pass_grep=False)
                )
                raw_tasks[cond]["T3_impact"].append(r3)
                task_meta[cond]["T3_impact"] = o3

                r4, o4 = _measure_fn(lambda c=cond: task_t4_detect_defects(c, roots[c], first_paper))
                raw_tasks[cond]["T4_validate_clean"].append(r4)
                task_meta[cond]["T4_validate_clean"] = o4

                r5, o5 = _measure_fn(lambda c=cond: task_t5_assemble_and_verify_bundle(c, roots[c], first_paper))
                raw_tasks[cond]["T5_bundle"].append(r5)
                task_meta[cond]["T5_bundle"] = o5

        # 3. Measure Task T6 (incorporate new claim) on fresh workspace copies per trial so edits don't accumulate
        t6_raw: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CONDITIONS}
        t6_meta: Dict[str, Any] = {}
        for tr in range(n_trials):
            order = list(CONDITIONS)
            rng.shuffle(order)
            for cond in order:
                cp = base / f"t6_{cond}_{tr}"
                shutil.copytree(roots[cond], cp)
                r6, o6 = _measure_fn(
                    lambda c=cond, p=cp, k=tr: task_t6_incorporate_new_claim(
                        c, p, last_paper, f"HO-NEW-{k:02d}", parent_for_t6.cid, parent_for_t6.version
                    )
                )
                t6_raw[cond].append(r6)
                t6_meta[cond] = o6
                shutil.rmtree(cp)

        # 4. Correctness analysis: T3 single-pass grep vs strong iterative grep vs modular vs CRR
        single_grep_out = task_t3_impact_analysis("conventional", roots["conventional"], target_root_cid, single_pass_grep=True)

        def _f1(pred: Set[str], truth: Set[str]) -> Dict[str, float]:
            tp = len(pred & truth)
            rec = tp / len(truth) if truth else 1.0
            prec = tp / len(pred) if pred else (1.0 if not truth else 0.0)
            f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
            return {
                "recall": round(rec, 4),
                "precision": round(prec, 4),
                "f1": round(f1, 4),
                "predicted_count": len(pred),
                "truth_count": len(truth),
            }

        t3_accuracy = {
            "conventional_single_grep": _f1(set(single_grep_out["downstream_claims"]), gt_downstream),
            "conventional_iterative_grep": _f1(
                set(task_meta["conventional"]["T3_impact"]["downstream_claims"]), gt_downstream
            ),
            "modular_manual": _f1(set(task_meta["modular_manual"]["T3_impact"]["downstream_claims"]), gt_downstream),
            "crr_v02": _f1(set(task_meta["crr_v02"]["T3_impact"]["downstream_claims"]), gt_downstream),
        }

        # 5. Correctness analysis: T4 6-class injected scientific & integrity defect detection
        defect_results: Dict[str, Dict[str, Any]] = {}
        if run_defect_suite:
            for cond in CONDITIONS:
                per_def: Dict[str, bool] = {}
                clean_fp = bool(task_meta[cond]["T4_validate_clean"]["detected"])
                for dtype in DEFECT_TYPES:
                    dcopy = base / f"def_{cond}_{dtype}"
                    shutil.copytree(roots[cond], dcopy)
                    inject_defect(cond, dcopy, spec, dtype)
                    res_d = task_t4_detect_defects(cond, dcopy, first_paper)
                    per_def[dtype] = bool(res_d["detected"])
                    shutil.rmtree(dcopy)
                detected_n = sum(1 for v in per_def.values() if v)
                defect_results[cond] = {
                    "per_defect_detected": per_def,
                    "detected_count": detected_n,
                    "total_defects": len(DEFECT_TYPES),
                    "detection_rate": round(detected_n / len(DEFECT_TYPES), 4),
                    "false_positive_on_clean": clean_fp,
                }

        # Aggregate task metrics
        tasks_summary: Dict[str, Dict[str, Any]] = {c: {} for c in CONDITIONS}
        for cond in CONDITIONS:
            for t in task_names:
                rows = raw_tasks[cond][t]
                tasks_summary[cond][t] = {
                    "wall_time_s": _agg([r["wall_time_s"] for r in rows]),
                    "hardware_energy_j": _agg([r["hardware_energy_j"] for r in rows]),
                    "instructions": _agg([float(r["instructions"]) for r in rows]),
                    "meta": task_meta[cond][t],
                }
            rows6 = t6_raw[cond]
            tasks_summary[cond]["T6_incorporate"] = {
                "wall_time_s": _agg([r["wall_time_s"] for r in rows6]),
                "hardware_energy_j": _agg([r["hardware_energy_j"] for r in rows6]),
                "instructions": _agg([float(r["instructions"]) for r in rows6]),
                "meta": t6_meta[cond],
            }

        return {
            "graph_name": spec.name,
            "num_claims": len(spec.claims),
            "num_papers": len(spec.papers),
            "density": spec.density_label,
            "ground_truth_downstream_count": len(gt_downstream),
            "ground_truth_affected_papers": len(gt_papers),
            "setup": setup_summary,
            "tasks": tasks_summary,
            "t3_impact_accuracy": t3_accuracy,
            "t4_defect_detection": defect_results,
        }


def compute_breakeven_model(
    suite: Dict[str, Any],
    edit_to_reuse_ratio: float = 0.25,
    bundle_freq: float = 0.25,
    max_n: int = 500,
) -> Dict[str, Any]:
    """Compute resource-specific break-even N* separately for Wall Time, CPU Energy, and Storage.

    Per-reuse-event workload:
      C_reuse(1) = T1_reproduce + T2_locate + T3_impact + T4_validate_clean + bundle_freq * T5_bundle
      C_maint(1) = edit_to_reuse_ratio * T6_incorporate
      C_total(N) = C_setup + N * (C_reuse(1) + C_maint(1))
    """
    out: Dict[str, Any] = {
        "edit_to_reuse_ratio": edit_to_reuse_ratio,
        "bundle_freq": bundle_freq,
        "per_condition": {},
        "breakeven_crr_vs_conventional": {},
        "breakeven_crr_vs_modular": {},
    }

    for resource in ("wall_time_s", "hardware_energy_j"):
        per_cond: Dict[str, Dict[str, float]] = {}
        for cond in CONDITIONS:
            c_setup = suite["setup"][cond][resource]["mean"]
            t = suite["tasks"][cond]
            c_reuse = (
                t["T1_reproduce"][resource]["mean"]
                + t["T2_locate"][resource]["mean"]
                + t["T3_impact"][resource]["mean"]
                + t["T4_validate_clean"][resource]["mean"]
                + bundle_freq * t["T5_bundle"][resource]["mean"]
            )
            c_maint = edit_to_reuse_ratio * t["T6_incorporate"][resource]["mean"]
            per_cond[cond] = {
                "c_setup": round(c_setup, 7),
                "c_reuse_per_event": round(c_reuse, 7),
                "c_maint_per_event": round(c_maint, 7),
                "c_slope_per_event": round(c_reuse + c_maint, 7),
            }
        out["per_condition"][resource] = per_cond

        for baseline_name, target_key in (
            ("conventional", "breakeven_crr_vs_conventional"),
            ("modular_manual", "breakeven_crr_vs_modular"),
        ):
            b = per_cond[baseline_name]
            c = per_cond["crr_v02"]
            delta_setup = c["c_setup"] - b["c_setup"]
            delta_slope = b["c_slope_per_event"] - c["c_slope_per_event"]
            if delta_setup <= 0 and delta_slope >= 0:
                n_star: Optional[int] = 1
            elif delta_slope > 0:
                n_raw = math.ceil(delta_setup / delta_slope)
                n_star = n_raw if n_raw <= max_n else None
            else:
                n_star = None  # CRR slope >= baseline slope: never breaks even on this resource!
            out[target_key][resource] = {
                "n_star": n_star,
                "delta_setup_crr_minus_base": round(delta_setup, 7),
                "per_event_saving_base_minus_crr": round(delta_slope, 7),
                "crr_wins_asymptotically": delta_slope > 0,
            }

    # Storage overhead (explicitly never breaks even in single-repo disk bytes!)
    sb_conv = suite["setup"]["conventional"]["storage_bytes"]
    sb_mod = suite["setup"]["modular_manual"]["storage_bytes"]
    sb_crr = suite["setup"]["crr_v02"]["storage_bytes"]
    out["storage_overhead"] = {
        "conventional_bytes": sb_conv,
        "modular_manual_bytes": sb_mod,
        "crr_v02_bytes": sb_crr,
        "crr_overhead_vs_conv_bytes": sb_crr - sb_conv,
        "crr_overhead_vs_conv_pct": round(100.0 * (sb_crr - sb_conv) / sb_conv, 2) if sb_conv else 0.0,
        "n_star_storage": None,
    }
    return out


def compute_parametric_human_surface() -> Dict[str, Any]:
    """ANALYTICAL PARAMETRIC MODEL ONLY — NOT MEASURED HUMAN RESEARCHER DATA.

    Maps researcher-minutes break-even N*_human = ceil(H_setup / (delta_h_reuse - r_edit * h_maint))
    across plausible setup costs and per-reuse verification savings so a future IRB human study
    can locate its empirical coordinates directly on this surface.
    """
    h_setup_vals = [30, 60, 120, 240]  # extra minutes to author CRR contracts initially
    delta_h_vals = [5, 15, 30, 60]     # minutes saved per downstream reuse/audit event
    r_edit = 0.25
    h_maint_extra = 4.0                # extra minutes per upstream edit to maintain YAML contracts

    grid: List[Dict[str, Any]] = []
    for hs in h_setup_vals:
        row: Dict[str, Any] = {"h_setup_min": hs, "n_star_by_delta_h_min": {}}
        for dh in delta_h_vals:
            net = dh - r_edit * h_maint_extra
            row["n_star_by_delta_h_min"][str(dh)] = math.ceil(hs / net) if net > 0 else None
        grid.append(row)
    return {
        "disclaimer": "ANALYTICAL_PARAMETRIC_MODEL — NOT MEASURED HUMAN DATA. Requires IRB human-subject study for empirical calibration.",
        "assumed_r_edit": r_edit,
        "assumed_h_maint_extra_min": h_maint_extra,
        "grid": grid,
    }


def compute_avoided_compute_breakeven(
    sensitivity_rows: List[Dict[str, Any]],
    real_be: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Evaluate machine-only CPU-energy & wall-time break-even when CRR verified contract import
    replaces redundant upstream experiment re-execution on real Apple M3 Max workloads (`exp_hw01`).

    Compares:
      - E_exp = 0.001 J (trivial unit test; pure metadata coordination)
      - E_exp = 2.018 J, t = 0.412 s (measured Paper I 1,000-node DAG certified run, exp_hw01)
      - E_exp = 22.382 J, t = 4.010 s (measured Paper I 1,000-node DAG full recompute, exp_hw01)
      - E_exp = 300.0 J, t = 60.0 s (representative 1-minute upstream ML/scientific benchmark)
    """
    workloads = [
        ("trivial_test_1mJ", 0.001, 0.0002),
        ("paper01_dag_2J_measured", 2.018149, 0.41227),
        ("paper01_full_22J_measured", 22.382286, 4.010173),
        ("benchmark_1min_300J", 300.0, 60.0),
    ]
    med_rows = [
        r for r in sensitivity_rows if r["density"] == "medium" and abs(r["edit_to_reuse_ratio"] - 0.25) < 1e-9
    ]
    results: List[Dict[str, Any]] = []
    for r in med_rows:
        v = r["num_claims"]
        # CRR net machine overhead per reuse event (positive number = extra cost of CRR vs conventional)
        crr_extra_e_j = -r["energy_saving_per_event_mj"] / 1000.0
        crr_extra_t_s = -r["wall_saving_per_event_ms"] / 1000.0
        delta_setup_e_j = (r["crr_setup_energy_mj"] - r["conv_setup_energy_mj"]) / 1000.0
        for wname, e_exp_j, t_exp_s in workloads:
            net_e_saving_per_reuse = e_exp_j - crr_extra_e_j
            net_t_saving_per_reuse = t_exp_s - crr_extra_t_s
            n_star_e = math.ceil(delta_setup_e_j / net_e_saving_per_reuse) if net_e_saving_per_reuse > 0 else None
            results.append(
                {
                    "num_claims": v,
                    "workload": wname,
                    "upstream_reexec_energy_j": e_exp_j,
                    "upstream_reexec_time_s": t_exp_s,
                    "crr_metadata_overhead_j": round(crr_extra_e_j, 4),
                    "net_energy_saving_per_reuse_j": round(net_e_saving_per_reuse, 4),
                    "net_time_saving_per_reuse_s": round(net_t_saving_per_reuse, 4),
                    "n_star_energy": n_star_e,
                    "crr_wins_on_machine_energy": net_e_saving_per_reuse > 0,
                }
            )
    return results


def generate_figures(
    real_suite: Dict[str, Any],
    heldout_40_suite: Dict[str, Any],
    be_40_med: Dict[str, Any],
    sensitivity_rows: List[Dict[str, Any]],
    human_surface: Dict[str, Any],
    avoided_compute_rows: List[Dict[str, Any]],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    colors = {"conventional": "#4a5568", "modular_manual": "#805ad5", "crr_v02": "#2f855a"}
    labels = {
        "conventional": "Conventional (Strong grep/pytest)",
        "modular_manual": "Modular Manual Manifests",
        "crr_v02": "CRR v0.2 (Executable Contracts)",
    }

    # --- Figure 1: Resource-Specific Break-Even Curves (Held-Out 40-Claim Program, r_edit=0.25) ---
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 9.2))
    ns = np.arange(0, 61)

    # Panel A: Wall Time (s)
    ax = axes[0, 0]
    for cond in CONDITIONS:
        p = be_40_med["per_condition"]["wall_time_s"][cond]
        y = p["c_setup"] + ns * p["c_slope_per_event"]
        ax.plot(ns, y, linewidth=2.2, color=colors[cond], label=labels[cond])
    nst = be_40_med["breakeven_crr_vs_conventional"]["wall_time_s"]["n_star"]
    if nst is not None and nst <= 60:
        p_c = be_40_med["per_condition"]["wall_time_s"]["crr_v02"]
        ax.axvline(nst, color="#2f855a", linestyle="--", alpha=0.6)
        ax.scatter([nst], [p_c["c_setup"] + nst * p_c["c_slope_per_event"]], color="#2f855a", zorder=5)
        ax.annotate(f"N*_time = {nst}", (nst + 1.2, p_c["c_setup"] + nst * p_c["c_slope_per_event"] * 0.9), fontsize=9, color="#2f855a", fontweight="bold")
    ax.set_xlabel("Research Reuse Events (N)")
    ax.set_ylabel("Cumulative Machine Wall Time (s)")
    ax.set_title("A. Machine Wall Time (40-Claim Held-Out Graph, r_edit=0.25)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Panel B: Apple M3 Max Hardware CPU Energy (J)
    ax = axes[0, 1]
    for cond in CONDITIONS:
        p = be_40_med["per_condition"]["hardware_energy_j"][cond]
        y = p["c_setup"] + ns * p["c_slope_per_event"]
        ax.plot(ns, y, linewidth=2.2, color=colors[cond], label=labels[cond])
    nse = be_40_med["breakeven_crr_vs_conventional"]["hardware_energy_j"]["n_star"]
    if nse is not None and nse <= 60:
        p_c = be_40_med["per_condition"]["hardware_energy_j"]["crr_v02"]
        ax.axvline(nse, color="#2f855a", linestyle="--", alpha=0.6)
        ax.scatter([nse], [p_c["c_setup"] + nse * p_c["c_slope_per_event"]], color="#2f855a", zorder=5)
        ax.annotate(f"N*_energy = {nse}", (nse + 1.2, p_c["c_setup"] + nse * p_c["c_slope_per_event"] * 0.9), fontsize=9, color="#2f855a", fontweight="bold")
    ax.set_xlabel("Research Reuse Events (N)")
    ax.set_ylabel("Cumulative M3 Max Hardware CPU Energy (J)")
    ax.set_title("B. Apple M3 Max Hardware CPU Energy (ri_energy_nj)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Panel C: Storage Overhead (KB) across V=5..100 (Negative Case NC-3!)
    ax = axes[1, 0]
    med_rows = [r for r in sensitivity_rows if r["density"] == "medium" and abs(r["edit_to_reuse_ratio"] - 0.25) < 1e-9]
    vs = [r["num_claims"] for r in med_rows]
    x = np.arange(len(vs))
    w = 0.26
    for i, cond in enumerate(CONDITIONS):
        kbs = [r["storage_bytes"][cond] / 1024.0 for r in med_rows]
        ax.bar(x + (i - 1) * w, kbs, w, color=colors[cond], label=labels[cond])
    ax.set_xticks(x)
    ax.set_xticklabels([f"V={v}" for v in vs])
    ax.set_ylabel("Repository Footprint (KiB)")
    ax.set_title("C. Disk Storage Footprint (CRR Always Uses More Bytes — NC-3)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # Panel D: Expected Undetected Scientific Defects Escaping per N Defect Opportunities
    ax = axes[1, 1]
    d_ns = np.arange(0, 21)
    for cond in CONDITIONS:
        miss_rate = 1.0 - heldout_40_suite["t4_defect_detection"][cond]["detection_rate"]
        ax.plot(d_ns, d_ns * miss_rate, linewidth=2.4, color=colors[cond], label=f"{labels[cond]} (miss={miss_rate*100:.1f}%)")
    ax.set_xlabel("Injected Scientific / Integrity Defect Opportunities")
    ax.set_ylabel("Cumulative Undetected Escaped Defects")
    ax.set_title("D. Scientific Safety: Undetected Defects Escaping QA (T4)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    fig.suptitle("Resource-Specific Break-Even Curves: Machine Time, Silicon Energy, Storage & Defect Escape", fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(RESULTS_DIR / "fig1_resource_breakeven_curves.png", dpi=160)
    plt.close(fig)

    # --- Figure 2: Sensitivity Across Network Size V, Density, & Edit Churn (Negative Cases!) ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.0, 5.2))

    # Left: Per-event CPU energy savings (Conventional - CRR) vs Network Size V & Density
    for dens, marker, ls in (("sparse", "o", "--"), ("medium", "s", "-"), ("dense", "D", "-.")):
        sub = [r for r in sensitivity_rows if r["density"] == dens and abs(r["edit_to_reuse_ratio"] - 0.25) < 1e-9]
        sub.sort(key=lambda r: r["num_claims"])
        xs = [r["num_claims"] for r in sub]
        ys = [r["energy_saving_per_event_mj"] for r in sub]
        ax1.plot(xs, ys, marker=marker, linestyle=ls, linewidth=2.0, label=f"Density: {dens}")
    y_lo = min(-500, min(r["energy_saving_per_event_mj"] for r in sensitivity_rows) * 1.12)
    ax1.axhline(0, color="black", linewidth=1.0)
    ax1.fill_between([0, 105], y_lo, 0, color="#fed7d7", alpha=0.35, label="CRR Loses on Pure Metadata CPU Energy")
    ax1.set_xlim(0, 105)
    ax1.set_ylim(y_lo, 250)
    ax1.set_xlabel("Research Graph Size V (Claims)")
    ax1.set_ylabel("Per-Reuse CPU Energy Margin: Conv - CRR (mJ)")
    ax1.set_title("Sensitivity to Network Size & Density (r_edit = 0.25)")
    ax1.legend(fontsize=8.5)
    ax1.grid(alpha=0.3)

    # Right: Churn Sensitivity (Edit-to-Reuse Ratio r_edit on V=40 medium) — Negative Case NC-2!
    churn_sub = [r for r in sensitivity_rows if r["num_claims"] == 40 and r["density"] == "medium"]
    churn_sub.sort(key=lambda r: r["edit_to_reuse_ratio"])
    rs = [r["edit_to_reuse_ratio"] for r in churn_sub]
    e_margins = [r["energy_saving_per_event_mj"] for r in churn_sub]
    t_margins = [r["wall_saving_per_event_ms"] for r in churn_sub]
    ax2.plot(rs, e_margins, "D-", linewidth=2.2, color="#2f855a", label="CPU Energy Margin: Conv - CRR (mJ/event)")
    ax2.plot(rs, t_margins, "s--", linewidth=2.0, color="#2b6cb0", label="Wall Time Margin: Conv - CRR (ms/event)")
    ax2.axhline(0, color="black", linewidth=1.0)
    ax2.set_xscale("log")
    ax2.set_xticks(rs)
    ax2.set_xticklabels([f"{r:g}x" for r in rs])
    ax2.set_xlabel("Edit-to-Reuse Ratio r_edit (Churn Frequency)")
    ax2.set_ylabel("Per-Reuse Margin (Positive = CRR Wins; Negative = CRR Loses)")
    ax2.set_title("Negative Case NC-2: High-Churn Maintenance Overhead (V=40)")
    ax2.legend(fontsize=8.5)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_sensitivity_and_negative_cases.png", dpi=160)
    plt.close(fig)

    # --- Figure 3: Correctness (T3 + T4) & Clearly Labeled Parametric Human-Time Surface ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2))

    # Left: Correctness comparison on Real Temporal Science 16-claim graph
    cats = [
        "T3 Impact\n(Single grep)",
        "T3 Impact\n(Iter. grep)",
        "T3 Impact\n(Mod./CRR)",
        "T4 Defects\n(Conv.)",
        "T4 Defects\n(Modular)",
        "T4 Defects\n(CRR v0.2)",
    ]
    vals = [
        100.0 * real_suite["t3_impact_accuracy"]["conventional_single_grep"]["recall"],
        100.0 * real_suite["t3_impact_accuracy"]["conventional_iterative_grep"]["recall"],
        100.0 * real_suite["t3_impact_accuracy"]["crr_v02"]["recall"],
        100.0 * real_suite["t4_defect_detection"]["conventional"]["detection_rate"],
        100.0 * real_suite["t4_defect_detection"]["modular_manual"]["detection_rate"],
        100.0 * real_suite["t4_defect_detection"]["crr_v02"]["detection_rate"],
    ]
    bar_colors = ["#e53e3e", "#4a5568", "#2f855a", "#e53e3e", "#805ad5", "#2f855a"]
    bars = ax1.bar(np.arange(len(cats)), vals, color=bar_colors, width=0.62)
    for b, v in zip(bars, vals):
        ax1.text(b.get_x() + b.get_width() / 2.0, v + 2.0, f"{v:.1f}%", ha="center", fontsize=8.5, fontweight="bold")
    ax1.set_xticks(np.arange(len(cats)))
    ax1.set_xticklabels(cats, fontsize=8.5)
    ax1.set_ylim(0, 114)
    ax1.set_ylabel("Recall / Detection Rate (%)")
    ax1.set_title("Empirical Correctness (Real 16-Claim, 5-Paper Graph)")
    ax1.grid(axis="y", alpha=0.3)

    # Right: Analytical Parametric Human-Time Break-Even Heatmap (STRICTLY LABELED NOT MEASURED DATA)
    h_setups = [r["h_setup_min"] for r in human_surface["grid"]]
    d_hs = [5, 15, 30, 60]
    mat = np.array([[r["n_star_by_delta_h_min"][str(d)] for d in d_hs] for r in human_surface["grid"]], dtype=float)
    ax2.imshow(np.log10(mat + 1.0), cmap="YlGn_r", aspect="auto")
    ax2.set_xticks(np.arange(len(d_hs)))
    ax2.set_xticklabels([f"{d} min" for d in d_hs])
    ax2.set_yticks(np.arange(len(h_setups)))
    ax2.set_yticklabels([f"{h} min" for h in h_setups])
    for i in range(len(h_setups)):
        for j in range(len(d_hs)):
            ax2.text(j, i, f"N*={int(mat[i, j])}", ha="center", va="center", color="black", fontsize=9.5, fontweight="bold")
    ax2.set_xlabel("Assumed Human Verification Time Saved per Reuse (Δh)")
    ax2.set_ylabel("Assumed Initial CRR Authoring Setup (H_setup)")
    ax2.set_title("ANALYTICAL ONLY (Not Measured Human Data): Parametric N*_human")

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig3_correctness_and_parametric_human.png", dpi=160)
    plt.close(fig)

    # --- Figure 4: Avoided Upstream Compute Regime (When Verified Contract Import Replaces Re-Execution) ---
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    for wname, label, col, mk in (
        ("trivial_test_1mJ", "Trivial Test (0.001 J — Pure Metadata)", "#e53e3e", "x"),
        ("paper01_dag_2J_measured", "Measured Paper I DAG (2.02 J, exp_hw01)", "#2b6cb0", "o"),
        ("paper01_full_22J_measured", "Measured Paper I Full DAG (22.38 J, exp_hw01)", "#2f855a", "D"),
    ):
        sub = sorted([r for r in avoided_compute_rows if r["workload"] == wname], key=lambda r: r["num_claims"])
        ax.plot(
            [r["num_claims"] for r in sub],
            [r["net_energy_saving_per_reuse_j"] for r in sub],
            marker=mk,
            linewidth=2.2,
            color=col,
            label=label,
        )
    ax.axhline(0, color="black", linewidth=1.0)
    ax.set_xlabel("Research Graph Size V (Claims, Medium Density, r_edit=0.25)")
    ax.set_ylabel("Net M3 Max CPU Energy Saving per Reuse (J)")
    ax.set_title("Machine-Only CPU Energy Regime: Verified Contract Import vs Upstream Re-Execution")
    ax.legend(fontsize=8.5)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig4_avoided_compute_breakeven.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = get_machine_metadata()
    calib = run_linearity_calibration()
    print(f"Hardware: {meta['cpu_brand']} ({meta['logical_cores']} cores) | calib 4x/1x={calib['ratio_4x_vs_1x_energy']}x")

    # 1. Real Temporal Science 16-claim, 5-paper graph (mirrored identically into all 3 conditions)
    print("[1/3] Evaluating Real Temporal Science Graph (16 claims, 5 papers, 5 trials)...")
    real_spec = load_real_temporal_science_spec(TS_ROOT)
    real_suite = evaluate_graph_suite(real_spec, n_trials=5, seed=501, run_defect_suite=True)
    real_be = compute_breakeven_model(real_suite, edit_to_reuse_ratio=0.25)

    print("  Real TS T3 recall:", {k: v["recall"] for k, v in real_suite["t3_impact_accuracy"].items()})
    print("  Real TS T4 defect detection:", {k: v["detection_rate"] for k, v in real_suite["t4_defect_detection"].items()})
    print(
        "  Real TS Break-Even (CRR vs Conv, r_edit=0.25): "
        f"N*_time={real_be['breakeven_crr_vs_conventional']['wall_time_s']['n_star']}, "
        f"N*_energy={real_be['breakeven_crr_vs_conventional']['hardware_energy_j']['n_star']}"
    )

    # 2. Primary Held-Out 40-claim, 10-paper graph
    print("[2/3] Evaluating Primary Held-Out Graph (40 claims, 10 papers, medium density, 5 trials)...")
    ho40_spec = generate_heldout_graph(num_claims=40, density="medium", seed=7040, name="heldout_40c_medium")
    ho40_suite = evaluate_graph_suite(ho40_spec, n_trials=5, seed=502, run_defect_suite=True)
    ho40_be = compute_breakeven_model(ho40_suite, edit_to_reuse_ratio=0.25)
    print(
        "  Held-out 40c Break-Even (CRR vs Conv, r_edit=0.25): "
        f"N*_time={ho40_be['breakeven_crr_vs_conventional']['wall_time_s']['n_star']}, "
        f"N*_energy={ho40_be['breakeven_crr_vs_conventional']['hardware_energy_j']['n_star']}"
    )

    # 3. Full Sensitivity Sweep: V in {5, 16, 40, 100} x density in {sparse, medium, dense} + churn sweep
    print("[3/3] Running Sensitivity Sweep (V in {5,16,40,100} x density + edit-to-reuse churn sweep)...")
    sensitivity_rows: List[Dict[str, Any]] = []
    cached_suites: Dict[Tuple[int, str], Dict[str, Any]] = {(40, "medium"): ho40_suite}

    for v in (5, 16, 40, 100):
        for dens in ("sparse", "medium", "dense"):
            if (v, dens) in cached_suites:
                st = cached_suites[(v, dens)]
            else:
                sp = generate_heldout_graph(
                    num_claims=v,
                    density=dens,
                    seed=8000 + v * 10 + ("sparse", "medium", "dense").index(dens),
                    name=f"heldout_{v}c_{dens}",
                )
                st = evaluate_graph_suite(sp, n_trials=3, seed=600 + v, run_defect_suite=False)
                cached_suites[(v, dens)] = st

            ratios = (0.05, 0.25, 1.0, 4.0) if (v == 40 and dens == "medium") or (v == 5 and dens == "medium") else (0.25,)
            for r_edit in ratios:
                be = compute_breakeven_model(st, edit_to_reuse_ratio=r_edit)
                t_cmp = be["breakeven_crr_vs_conventional"]["wall_time_s"]
                e_cmp = be["breakeven_crr_vs_conventional"]["hardware_energy_j"]
                m_cmp = be["breakeven_crr_vs_modular"]["hardware_energy_j"]
                row = {
                    "num_claims": v,
                    "num_papers": st["num_papers"],
                    "density": dens,
                    "edit_to_reuse_ratio": r_edit,
                    "t3_single_grep_recall": st["t3_impact_accuracy"]["conventional_single_grep"]["recall"],
                    "wall_saving_per_event_ms": round(t_cmp["per_event_saving_base_minus_crr"] * 1000.0, 3),
                    "energy_saving_per_event_mj": round(e_cmp["per_event_saving_base_minus_crr"] * 1000.0, 3),
                    "n_star_wall_vs_conv": t_cmp["n_star"],
                    "n_star_energy_vs_conv": e_cmp["n_star"],
                    "n_star_energy_vs_modular": m_cmp["n_star"],
                    "storage_bytes": {c: st["setup"][c]["storage_bytes"] for c in CONDITIONS},
                    "crr_setup_energy_mj": round(be["per_condition"]["hardware_energy_j"]["crr_v02"]["c_setup"] * 1000.0, 2),
                    "conv_setup_energy_mj": round(be["per_condition"]["hardware_energy_j"]["conventional"]["c_setup"] * 1000.0, 2),
                }
                sensitivity_rows.append(row)
                print(
                    f"  V={v:3d} {dens:6s} r_edit={r_edit:4.2f}: "
                    f"Δt={row['wall_saving_per_event_ms']:+7.2f}ms/ev, "
                    f"ΔE={row['energy_saving_per_event_mj']:+7.2f}mJ/ev, "
                    f"N*_time={str(row['n_star_wall_vs_conv']):>4s}, "
                    f"N*_E={str(row['n_star_energy_vs_conv']):>4s}, "
                    f"single_grep_rec={row['t3_single_grep_recall']:.2f}"
                )

    human_surface = compute_parametric_human_surface()
    avoided_compute = compute_avoided_compute_breakeven(sensitivity_rows, real_be)
    generate_figures(real_suite, ho40_suite, ho40_be, sensitivity_rows, human_surface, avoided_compute)

    summary = {
        "experiment_id": "exp_crr_breakeven_v01",
        "machine": meta,
        "calibration": calib,
        "real_temporal_science_suite": real_suite,
        "real_temporal_science_breakeven": real_be,
        "heldout_40c_suite": ho40_suite,
        "heldout_40c_breakeven": ho40_be,
        "sensitivity_sweep": sensitivity_rows,
        "avoided_compute_regime": avoided_compute,
        "parametric_human_surface_analytical_only": human_surface,
    }
    out_json = RESULTS_DIR / "crr_breakeven_summary.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved CRR break-even summary -> {out_json}")


if __name__ == "__main__":
    main()
