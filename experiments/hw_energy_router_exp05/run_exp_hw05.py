#!/usr/bin/env python3
"""exp_hw05 — Predictive Temporal Energy Router on Strictly Blind Unseen Workloads.

Tests whether a calibrated 5-component physical energy router selects the
least-energy strategy (`strong_incremental` vs `certified_reuse`) across a
balanced, strictly unseen 24-task competing portfolio (16 DAG tasks across
granularity K & shock p + 8 real-code typechecking tasks on `_pytest` & `PyYAML`)
better than either fixed policy—even AFTER charging 100% of its own calibration
energy E_cal and per-task routing decision energy E_decision!

Compared Policies (all verified for exact 0-mismatch correctness):
  1. `always_incremental` : Fixed conventional strong incremental baseline.
  2. `always_reuse`       : Fixed certified reuse (always builds/checks canaries).
  3. `model_based_router` : Uses ONLY pre-execution observables + disjoint micro-calibration
                            (zero peeking at unseen task seeds or outcomes); pays full E_cal + E_decision.
  4. `oracle_selection`   : Non-deployable retrospective lower-bound reference picking min(E_inc, E_reuse).

Strict Blind Compliance (`TS-PROTO-HW-ENERGY-v1.0.0`):
  - Calibration seeds (100..199) are 100% disjoint from unseen evaluation seeds (90000..99999).
  - Pre-execution router choices & ΔE predictions are sealed BEFORE running the 24 unseen tasks.
  - Both Process CPU PMU (`ri_energy_nj`) and Whole-SoC Package (`IOReport` `CPU+GPU+ANE+DRAM+DCS+AMCC`)
    are recorded on AC Power with pinned Python 3.11.7 across N = 3 interleaved paired blocks per task.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
import ast
import gc
import hashlib
import importlib
import json
import math
import os
import random
import statistics
import sys

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
LC_ROOT = (TS_ROOT / "../living-computation").resolve()
HW01_DIR = TS_ROOT / "experiments" / "hw_energy_paper01"
HW02_DIR = TS_ROOT / "experiments" / "hw_soc_paper02"
HW04_DIR = TS_ROOT / "experiments" / "hw_soc_prospective_exp04"
for p in (LC_ROOT, HW01_DIR, HW02_DIR, HW04_DIR, EXP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("MPLCONFIGDIR", "/tmp/temporal_science_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

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
from incremental_typechecker import (
    IncrementalTypecheckEngine,
    TypecheckEdit,
    build_pytest_import_graph,
    discover_pytest_corpus,
    extract_type_interface,
    transitive_importers,
    typecheck_single_module,
)
from router_core import CodeTaskSpec, DAGTaskSpec, TemporalEnergyRouter

RESULTS_DIR = EXP_DIR / "results"
N_EVAL_BLOCKS = 3


def _make_granularity_graph(k_iters: int) -> DependencyGraph:
    """Uniform node wrapper across ALL K (including K=1) to eliminate the K=1->K=2 dispatch step!"""
    graph = build_milestone_network()
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


def _discover_pkg_corpus(pkg_name: str) -> Dict[str, str]:
    if pkg_name == "_pytest":
        srcs, _ = discover_pytest_corpus()
        return srcs
    mod = importlib.import_module(pkg_name)
    root = Path(mod.__file__).parent
    srcs: Dict[str, str] = {}
    for py in sorted(root.rglob("*.py")):
        if "tests" in py.parts:
            continue
        parts = [pkg_name] + list(py.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        srcs[".".join(parts)] = py.read_text(encoding="utf-8", errors="replace")
    return srcs


def _make_code_edits(
    sources: Dict[str, str], rev: Dict[str, set], num_edits: int, q: float, leaf_only: bool, seed: int
) -> List[TypecheckEdit]:
    rng = random.Random(seed)
    if leaf_only:
        cands = [m for m in sorted(sources) if len(transitive_importers(rev, m)) == 0]
        if not cands:
            cands = sorted(sources, key=lambda m: len(transitive_importers(rev, m)))[:5]
    else:
        cands = [m for m in sorted(sources) if len(transitive_importers(rev, m)) >= 2]
        if not cands:
            cands = sorted(sources)
    cur = dict(sources)
    edits: List[TypecheckEdit] = []
    for step in range(num_edits):
        m = rng.choice(cands)
        brk = rng.random() < q
        if brk:
            snip = f"\ndef router_api_v{step}(a: int, b: int = {step}) -> int:\n    return a + b\n"
        else:
            snip = f"\ndef _router_priv_{step}(x: int) -> int:\n    return (x + {step}) ^ 1\n"
        cur[m] = cur[m] + snip
        edits.append(TypecheckEdit(step, m, brk, cur[m]))
    return edits


def calibrate_router(
    ior: IOReportEnergyReader,
    em: EnergyModel,
    code_corpora: Dict[str, Tuple[Dict[str, str], Dict[str, set], Dict[str, set], List[str]]],
) -> Tuple[TemporalEnergyRouter, Dict[str, Any]]:
    """Run disjoint micro-calibration and measure exact total calibration energy E_cal!"""
    print("[Phase 1] Running disjoint micro-calibration (charging exact E_cal to router)...")
    router = TemporalEnergyRouter()
    cal_s0 = snapshot_dual(ior)

    # 1A. DAG calibration: 4 disjoint corner points (K, p) on seeds 101..104 (3,000 updates)
    cal_dag_points = [(1, 0.00, 101), (1, 0.30, 102), (20, 0.00, 103), (20, 0.30, 104)]
    cal_dag_rows = []
    base_g = build_milestone_network()
    for k, p, seed in cal_dag_points:
        g = _make_granularity_graph(k)
        env = WorkloadEnvironment(
            base_g.input_ids,
            WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=3_000, seed=seed, shock_probability=p),
        )
        init_in, evs = env.generate()
        # Run inc & liv once each on disjoint calibration seed
        gc.collect()
        s0 = snapshot_dual(ior)
        eng_i = ConventionalIncrementalEngine(g, energy_model=em)
        eng_i.run(init_in, evs)
        s1 = snapshot_dual(ior)
        pi, si = delta_dual(ior, s0, s1)
        assert si is not None

        gc.collect()
        s0 = snapshot_dual(ior)
        eng_l = LivingTraceContractEngine(
            g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
            enable_regime_cache=True, adaptive_retirement=False,
        )
        eng_l.run(init_in, evs)
        eng_l.close()
        s1 = snapshot_dual(ior)
        pl, sl = delta_dual(ior, s0, s1)
        assert sl is not None

        inc_eval = eng_i.ledger.summary()["by_category"]["execution"]["steps"]
        liv_eval = eng_l.ledger.summary()["by_category"]["execution"]["steps"]
        cal_dag_rows.append(
            {
                "k_granularity": k,
                "shock_prob": p,
                "inc_nodes_eval": inc_eval,
                "nodes_avoided": max(0, inc_eval - liv_eval),
                "inc": {"proc_cpu_energy_j": pi.hardware_energy_j, "soc_package_j": si.soc_package_j},
                "liv": {"proc_cpu_energy_j": pl.hardware_energy_j, "soc_package_j": sl.soc_package_j},
            }
        )
    router.fit_dag_primitives(cal_dag_rows, calib_updates=3_000)

    # 1B. Real-code disjoint micro-probe (4 modules per repo, 6 exec reps + 40 val reps)
    for rname, (srcs, deps, rev, order) in code_corpora.items():
        known = set(srcs)
        mod_kib = {m: len(s.encode("utf-8")) / 1024.0 for m, s in srcs.items()}
        cands = [m for m in sorted(srcs) if len(transitive_importers(rev, m)) >= 2] or sorted(srcs)
        mean_ds_kib = statistics.mean(sum(mod_kib[d] for d in transitive_importers(rev, m)) for m in cands)

        by_sz = sorted(order, key=lambda m: len(srcs[m]))
        pmods = [by_sz[int(i * (len(by_sz) - 1) / 3)] for i in range(4)]
        pkib = sum(mod_kib[m] for m in pmods)

        gc.collect()
        s0 = snapshot_dual(ior)
        for _ in range(6):
            for m in pmods:
                typecheck_single_module(m, srcs[m], known, {}, {}, deps[m])
        s1 = snapshot_dual(ior)
        pe, se = delta_dual(ior, s0, s1)
        assert se is not None

        trees = [ast.parse(srcs[m]) for m in pmods]
        gc.collect()
        s0 = snapshot_dual(ior)
        cache: Dict[str, str] = {}
        for _ in range(40):
            for m, t in zip(pmods, trees):
                h, _ = extract_type_interface(t)
                _ = (cache.get(m) == h)
                cache[m] = h
        s1 = snapshot_dual(ior)
        pv, sv = delta_dual(ior, s0, s1)
        assert sv is not None

        router.register_code_primitives(
            rname,
            mean_ds_kib=mean_ds_kib,
            e_exec_proc_per_kib=pe.hardware_energy_j / (6 * pkib),
            e_exec_soc_per_kib=se.soc_package_j / (6 * pkib),
            e_val_proc_per_edit=pv.hardware_energy_j / (40 * len(pmods)),
            e_val_soc_per_edit=sv.soc_package_j / (40 * len(pmods)),
        )

    cal_s1 = snapshot_dual(ior)
    cal_p, cal_s = delta_dual(ior, cal_s0, cal_s1)
    assert cal_s is not None
    router.calibration_energy_proc_j = cal_p.hardware_energy_j
    router.calibration_energy_soc_j = cal_s.soc_package_j
    router.calibration_wall_s = cal_p.wall_time_s
    print(
        f"  Calibration COMPLETE: E_cal_proc={router.calibration_energy_proc_j:.3f} J, "
        f"E_cal_SoC={router.calibration_energy_soc_j:.3f} J, wall={router.calibration_wall_s:.2f} s"
    )
    return router, router.summary_dict()


def build_unseen_competing_portfolio() -> List[Any]:
    """24 strictly unseen competing tasks (disjoint seeds 90001..90024) mixing reuse-favored,
    incremental-favored, and boundary regimes across both DAG and real-code domains."""
    dag_tasks = [
        # Clearly reuse-favored (low p, medium-high K)
        DAGTaskSpec("DAG-01", "dag", k_granularity=25, shock_prob=0.00, num_updates=3_000, unseen_seed=90001, regime_hint="reuse_favored"),
        DAGTaskSpec("DAG-02", "dag", k_granularity=40, shock_prob=0.02, num_updates=3_000, unseen_seed=90002, regime_hint="reuse_favored"),
        DAGTaskSpec("DAG-03", "dag", k_granularity=15, shock_prob=0.03, num_updates=3_000, unseen_seed=90003, regime_hint="reuse_favored"),
        DAGTaskSpec("DAG-04", "dag", k_granularity=30, shock_prob=0.05, num_updates=3_000, unseen_seed=90004, regime_hint="reuse_favored"),
        DAGTaskSpec("DAG-05", "dag", k_granularity=10, shock_prob=0.01, num_updates=3_000, unseen_seed=90005, regime_hint="reuse_favored"),
        DAGTaskSpec("DAG-06", "dag", k_granularity=20, shock_prob=0.04, num_updates=3_000, unseen_seed=90006, regime_hint="reuse_favored"),
        # Boundary / competitive regime (genuine ambiguity!)
        DAGTaskSpec("DAG-07", "dag", k_granularity=2,  shock_prob=0.06, num_updates=3_000, unseen_seed=90007, regime_hint="boundary"),
        DAGTaskSpec("DAG-08", "dag", k_granularity=5,  shock_prob=0.12, num_updates=3_000, unseen_seed=90008, regime_hint="boundary"),
        DAGTaskSpec("DAG-09", "dag", k_granularity=8,  shock_prob=0.15, num_updates=3_000, unseen_seed=90009, regime_hint="boundary"),
        DAGTaskSpec("DAG-10", "dag", k_granularity=1,  shock_prob=0.05, num_updates=3_000, unseen_seed=90010, regime_hint="boundary"),
        # Clearly incremental-favored (high shock / volatility where certified reuse loses!)
        DAGTaskSpec("DAG-11", "dag", k_granularity=1,  shock_prob=0.25, num_updates=3_000, unseen_seed=90011, regime_hint="inc_favored"),
        DAGTaskSpec("DAG-12", "dag", k_granularity=3,  shock_prob=0.35, num_updates=3_000, unseen_seed=90012, regime_hint="inc_favored"),
        DAGTaskSpec("DAG-13", "dag", k_granularity=5,  shock_prob=0.45, num_updates=3_000, unseen_seed=90013, regime_hint="inc_favored"),
        DAGTaskSpec("DAG-14", "dag", k_granularity=10, shock_prob=0.55, num_updates=3_000, unseen_seed=90014, regime_hint="inc_favored"),
        DAGTaskSpec("DAG-15", "dag", k_granularity=2,  shock_prob=0.60, num_updates=3_000, unseen_seed=90015, regime_hint="inc_favored"),
        DAGTaskSpec("DAG-16", "dag", k_granularity=15, shock_prob=0.65, num_updates=3_000, unseen_seed=90016, regime_hint="inc_favored"),
    ]
    code_tasks = [
        # Real-code reuse-favored
        CodeTaskSpec("CODE-01", "code_typecheck", "_pytest", api_break_prob=0.00, num_edits=15, leaf_only=False, unseen_seed=90017, regime_hint="reuse_favored"),
        CodeTaskSpec("CODE-02", "code_typecheck", "_pytest", api_break_prob=0.25, num_edits=15, leaf_only=False, unseen_seed=90018, regime_hint="reuse_favored"),
        CodeTaskSpec("CODE-03", "code_typecheck", "yaml",    api_break_prob=0.10, num_edits=15, leaf_only=False, unseen_seed=90019, regime_hint="reuse_favored"),
        CodeTaskSpec("CODE-04", "code_typecheck", "_pytest", api_break_prob=0.50, num_edits=15, leaf_only=False, unseen_seed=90020, regime_hint="reuse_favored"),
        # Real-code incremental-favored (100% API breaks or zero-fanout leaf edits!)
        CodeTaskSpec("CODE-05", "code_typecheck", "_pytest", api_break_prob=1.00, num_edits=15, leaf_only=False, unseen_seed=90021, regime_hint="inc_favored"),
        CodeTaskSpec("CODE-06", "code_typecheck", "_pytest", api_break_prob=0.20, num_edits=15, leaf_only=True,  unseen_seed=90022, regime_hint="inc_favored"),
        CodeTaskSpec("CODE-07", "code_typecheck", "yaml",    api_break_prob=1.00, num_edits=15, leaf_only=False, unseen_seed=90023, regime_hint="inc_favored"),
        CodeTaskSpec("CODE-08", "code_typecheck", "yaml",    api_break_prob=0.10, num_edits=15, leaf_only=True,  unseen_seed=90024, regime_hint="inc_favored"),
    ]
    # Interleave deterministically so cumulative calibration payback curve sees mixed tasks throughout
    rng = random.Random(202605)
    portfolio: List[Any] = dag_tasks + code_tasks
    rng.shuffle(portfolio)
    return portfolio


def generate_figures(
    task_results: List[Dict[str, Any]],
    policy_summary: Dict[str, Any],
    router_meta: Dict[str, Any],
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Figure 1: Cumulative Physical Energy (Including Calibration E_cal!) & Calibration Payback ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.4))
    xs = np.arange(0, len(task_results) + 1)

    for ax, ekey, cal_e, title, ylabel in (
        (ax1, "proc_cpu_energy_j", router_meta["calibration_energy_proc_j"], "A. Cumulative Process CPU Energy (Incl. Calibration E_cal)", "Cumulative M3 Max Process CPU Energy (J)"),
        (ax2, "soc_package_j", router_meta["calibration_energy_soc_j"], "B. Cumulative Whole-SoC Package Energy (Incl. Calibration E_cal)", "Cumulative M3 Max Whole-SoC Package Energy (J)"),
    ):
        c_inc = [0.0]
        c_reu = [0.0]
        c_ora = [0.0]
        c_rtr = [cal_e]  # Router starts at t=0 ALREADY paying full E_cal!
        for r in task_results:
            ei = r["measured_inc"][ekey]
            er = r["measured_reuse"][ekey]
            edec = r["router_decision_cost"][ekey]
            chosen_e = (er if r["router_choice"][ekey] == "certified_reuse" else ei) + edec
            c_inc.append(c_inc[-1] + ei)
            c_reu.append(c_reu[-1] + er)
            c_ora.append(c_ora[-1] + min(ei, er))
            c_rtr.append(c_rtr[-1] + chosen_e)

        ax.plot(xs, c_inc, "--", linewidth=2.0, color="#4a5568", label=f"Always Incremental ({c_inc[-1]:.1f} J)")
        ax.plot(xs, c_reu, "-.", linewidth=2.0, color="#dd6b20", label=f"Always Certified Reuse ({c_reu[-1]:.1f} J)")
        ax.plot(xs, c_rtr, "-", linewidth=2.4, color="#2f855a", label=f"Model-Based Router + E_cal ({c_rtr[-1]:.1f} J)")
        ax.plot(xs, c_ora, ":", linewidth=2.0, color="#2b6cb0", label=f"Oracle Lower Bound ({c_ora[-1]:.1f} J)")

        # Mark exact calibration payback task where Router + E_cal beats BOTH fixed policies
        pb = next((i for i in range(1, len(xs)) if c_rtr[i] < c_inc[i] and c_rtr[i] < c_reu[i]), None)
        if pb is not None:
            ax.axvline(pb, color="#2f855a", linestyle=":", alpha=0.6)
            ax.scatter([pb], [c_rtr[pb]], color="#2f855a", s=55, zorder=5)
            ax.annotate(f"Payback\ntask #{pb}", (pb + 0.4, c_rtr[pb] * 0.86), fontsize=8.5, color="#2f855a", fontweight="bold")
        ax.set_xlabel("Unseen Tasks Completed (Mixed Competing Stream)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=8.2, loc="upper left")
        ax.grid(alpha=0.3)

    fig.suptitle("exp_hw05: Temporal Energy Router vs Fixed Policies & Oracle (24 Strictly Unseen Tasks)", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(RESULTS_DIR / "fig1_router_cumulative_energy_and_payback.png", dpi=160)
    plt.close(fig)

    # --- Figure 2: Selection Regret Bar Comparison + Per-Task Predicted vs Measured ΔE ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.2))
    pols = ["always_incremental", "always_reuse", "router_exec_only", "router_with_cal"]
    plbls = ["Always\nIncremental", "Always\nReuse", "Router\n(Exec Regret)", "Router\n(Incl. E_cal)"]
    reg_proc = [policy_summary["proc_cpu_energy_j"][p]["regret_vs_oracle_j"] for p in pols]
    reg_soc = [policy_summary["soc_package_j"][p]["regret_vs_oracle_j"] for p in pols]
    x = np.arange(len(pols))
    w = 0.36
    ax1.bar(x - w / 2, reg_proc, w, color="#2f855a", label="Process CPU Regret vs Oracle (J)")
    ax1.bar(x + w / 2, reg_soc, w, color="#dd6b20", label="Whole-SoC Regret vs Oracle (J)")
    for i, (vp, vs) in enumerate(zip(reg_proc, reg_soc)):
        ax1.text(i - w / 2, vp + 0.6, f"{vp:.1f}J", ha="center", fontsize=8, fontweight="bold")
        ax1.text(i + w / 2, vs + 0.6, f"{vs:.1f}J", ha="center", fontsize=8, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(plbls, fontsize=8.8)
    ax1.set_ylabel("Total Selection Regret Above Oracle (Joules, Lower = Better)")
    ax1.set_title("A. Total Selection Regret Across 24 Unseen Competing Tasks")
    ax1.legend(fontsize=8.2)
    ax1.grid(axis="y", alpha=0.3)

    # Right: Per-task Predicted vs Measured ΔE (Process CPU) showing 4 decision quadrants!
    prd = [r["pred_delta_j"]["proc_cpu_energy_j"] for r in task_results]
    obs = [r["measured_delta_j"]["proc_cpu_energy_j"] for r in task_results]
    ok = [r["router_correct"]["proc_cpu_energy_j"] for r in task_results]
    ax2.axhline(0, color="black", linewidth=0.9)
    ax2.axvline(0, color="black", linewidth=0.9)
    lo, hi = min(prd + obs) - 0.5, max(prd + obs) + 0.5
    ax2.plot([lo, hi], [lo, hi], "k--", alpha=0.5, label="Perfect Prediction (y = x)")
    ax2.scatter([p for p, c in zip(prd, ok) if c], [o for o, c in zip(obs, ok) if c],
                s=70, color="#2f855a", marker="o", label=f"Correct Route ({sum(ok)}/{len(ok)})")
    if any(not c for c in ok):
        ax2.scatter([p for p, c in zip(prd, ok) if not c], [o for o, c in zip(obs, ok) if not c],
                    s=85, color="#e53e3e", marker="X", label=f"Misrouted ({sum(not c for c in ok)}/{len(ok)})")
    ax2.set_xlabel("Router Pre-Execution Predicted ΔE = E_inc - E_reuse (J)")
    ax2.set_ylabel("Measured Hardware ΔE = E_inc - E_reuse (J)")
    ax2.set_title("B. Per-Task Routing Decision Quadrants (Process CPU PMU)")
    ax2.legend(fontsize=8.2)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig2_router_regret_and_quadrants.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ior = IOReportEnergyReader()
    meta = get_soc_machine_metadata()
    start_ctx = get_system_context()
    calib = run_linearity_calibration()
    print(f"Hardware: {meta['cpu_brand']} | Python {meta['python_version']} | load1m={start_ctx['loadavg_1m']} | {start_ctx['pmset_batt']}")

    em = EnergyModel()
    code_corpora = {}
    for rname in ("_pytest", "yaml"):
        s = _discover_pkg_corpus(rname)
        d, rv, od = build_pytest_import_graph(s)
        code_corpora[rname] = (s, d, rv, od)

    # Phase 1: Disjoint calibration (charged in full!)
    router, router_meta = calibrate_router(ior, em, code_corpora)

    # Phase 2: Build 24 strictly unseen tasks & seal pre-execution router choices BEFORE executing!
    portfolio = build_unseen_competing_portfolio()
    pre_exec_decisions: List[Dict[str, Any]] = []
    for task in portfolio:
        d_s0 = snapshot_dual(ior)
        if task.domain == "dag":
            c_p, dp = router.predict_and_route_dag(task, "proc_cpu_energy_j")
            c_s, ds = router.predict_and_route_dag(task, "soc_package_j")
        else:
            c_p, dp = router.predict_and_route_code(task, "proc_cpu_energy_j")
            c_s, ds = router.predict_and_route_code(task, "soc_package_j")
        d_s1 = snapshot_dual(ior)
        dp_m, ds_m = delta_dual(ior, d_s0, d_s1)
        assert ds_m is not None
        pre_exec_decisions.append(
            {
                "task_id": task.task_id,
                "domain": task.domain,
                "regime_hint": task.regime_hint,
                "choice_proc": c_p,
                "choice_soc": c_s,
                "pred_delta_proc_j": round(dp, 6),
                "pred_delta_soc_j": round(ds, 6),
                "decision_proc_j": dp_m.hardware_energy_j,
                "decision_soc_j": ds_m.soc_package_j,
                "decision_wall_s": dp_m.wall_time_s,
            }
        )
    seal = hashlib.sha256(
        json.dumps(pre_exec_decisions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (RESULTS_DIR / "sealed_router_decisions.json").write_text(
        json.dumps({"sealed_at_utc": datetime.now(timezone.utc).isoformat(), "sha256": seal, "decisions": pre_exec_decisions}, indent=2),
        encoding="utf-8",
    )
    print(f"[Phase 2] SEALED 24 pre-execution router choices (SHA-256: {seal[:16]}...) BEFORE running unseen tasks!")

    # Phase 3: Evaluate both admissible strategies on all 24 unseen tasks (N_EVAL_BLOCKS interleaved paired runs)
    print(f"[Phase 3] Executing 24 unseen competing tasks ({N_EVAL_BLOCKS} interleaved paired blocks each)...")
    rng = random.Random(555)
    base_dag = build_milestone_network()
    dag_graph_cache: Dict[int, DependencyGraph] = {}
    task_results: List[Dict[str, Any]] = []

    for task, dec in zip(portfolio, pre_exec_decisions):
        inc_proc, inc_soc, reu_proc, reu_soc = [], [], [], []
        for b in range(N_EVAL_BLOCKS):
            seed_b = task.unseen_seed + b * 1000
            pair = ["strong_incremental", "certified_reuse"]
            rng.shuffle(pair)

            if task.domain == "dag":
                if task.k_granularity not in dag_graph_cache:
                    dag_graph_cache[task.k_granularity] = _make_granularity_graph(task.k_granularity)
                g = dag_graph_cache[task.k_granularity]
                env = WorkloadEnvironment(
                    base_dag.input_ids,
                    WorkloadConfig(
                        regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT,
                        num_updates=task.num_updates,
                        seed=seed_b,
                        shock_probability=task.shock_prob,
                    ),
                )
                init_in, evs = env.generate()
                outs = {}
                for strat in pair:
                    gc.collect()
                    s0 = snapshot_dual(ior)
                    if strat == "strong_incremental":
                        eng = ConventionalIncrementalEngine(g, energy_model=em)
                    else:
                        eng = LivingTraceContractEngine(
                            g, energy_model=em, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN,
                            enable_regime_cache=True, adaptive_retirement=False,
                        )
                    out = eng.run(init_in, evs)
                    if hasattr(eng, "close"):
                        eng.close()
                    s1 = snapshot_dual(ior)
                    p_m, s_m = delta_dual(ior, s0, s1)
                    assert s_m is not None
                    outs[strat] = out
                    if strat == "strong_incremental":
                        inc_proc.append(p_m.hardware_energy_j); inc_soc.append(s_m.soc_package_j)
                    else:
                        reu_proc.append(p_m.hardware_energy_j); reu_soc.append(s_m.soc_package_j)
                assert all(abs(a - b_) <= 1e-12 for a, b_ in zip(outs["strong_incremental"], outs["certified_reuse"]))
            else:
                srcs, deps, rev, order = code_corpora[task.repo_name]
                eds = _make_code_edits(srcs, rev, task.num_edits, task.api_break_prob, task.leaf_only, seed_b)
                fps = {}
                for strat in pair:
                    gc.collect()
                    s0 = snapshot_dual(ior)
                    mode = "strong_incremental_dag" if strat == "strong_incremental" else "certified_type_canary"
                    eng = IncrementalTypecheckEngine(mode, srcs, deps, rev, order)
                    fp = eng.run_full_lifecycle(eds)
                    s1 = snapshot_dual(ior)
                    p_m, s_m = delta_dual(ior, s0, s1)
                    assert s_m is not None
                    fps[strat] = fp
                    if strat == "strong_incremental":
                        inc_proc.append(p_m.hardware_energy_j); inc_soc.append(s_m.soc_package_j)
                    else:
                        reu_proc.append(p_m.hardware_energy_j); reu_soc.append(s_m.soc_package_j)
                assert fps["strong_incremental"] == fps["certified_reuse"]

        mi_p, mr_p = statistics.mean(inc_proc), statistics.mean(reu_proc)
        mi_s, mr_s = statistics.mean(inc_soc), statistics.mean(reu_soc)
        ora_p = "certified_reuse" if mr_p < mi_p else "strong_incremental"
        ora_s = "certified_reuse" if mr_s < mi_s else "strong_incremental"

        rec = {
            "task_id": task.task_id,
            "domain": task.domain,
            "regime_hint": task.regime_hint,
            "measured_inc": {"proc_cpu_energy_j": round(mi_p, 6), "soc_package_j": round(mi_s, 6)},
            "measured_reuse": {"proc_cpu_energy_j": round(mr_p, 6), "soc_package_j": round(mr_s, 6)},
            "measured_delta_j": {"proc_cpu_energy_j": round(mi_p - mr_p, 6), "soc_package_j": round(mi_s - mr_s, 6)},
            "pred_delta_j": {"proc_cpu_energy_j": dec["pred_delta_proc_j"], "soc_package_j": dec["pred_delta_soc_j"]},
            "oracle_choice": {"proc_cpu_energy_j": ora_p, "soc_package_j": ora_s},
            "router_choice": {"proc_cpu_energy_j": dec["choice_proc"], "soc_package_j": dec["choice_soc"]},
            "router_correct": {
                "proc_cpu_energy_j": dec["choice_proc"] == ora_p,
                "soc_package_j": dec["choice_soc"] == ora_s,
            },
            "router_decision_cost": {
                "proc_cpu_energy_j": round(dec["decision_proc_j"], 6),
                "soc_package_j": round(dec["decision_soc_j"], 6),
            },
            "mismatches": 0,
        }
        task_results.append(rec)
        print(
            f"  {task.task_id:7s} [{task.regime_hint:13s}]: "
            f"OBS ΔE_proc={mi_p-mr_p:+6.3f}J (PRED={dec['pred_delta_proc_j']:+6.3f}J) "
            f"router={dec['choice_proc'][:5]} vs oracle={ora_p[:5]} [{'OK' if rec['router_correct']['proc_cpu_energy_j'] else 'MISS'}] | "
            f"SoC_ok={'OK' if rec['router_correct']['soc_package_j'] else 'MISS'}"
        )

    # Aggregate policy comparison & regret (separately for Process CPU and Whole-SoC!)
    policy_summary: Dict[str, Any] = {}
    for ekey, cal_e in (
        ("proc_cpu_energy_j", router.calibration_energy_proc_j),
        ("soc_package_j", router.calibration_energy_soc_j),
    ):
        tot_inc = sum(r["measured_inc"][ekey] for r in task_results)
        tot_reu = sum(r["measured_reuse"][ekey] for r in task_results)
        tot_ora = sum(min(r["measured_inc"][ekey], r["measured_reuse"][ekey]) for r in task_results)
        tot_rtr_exec = sum(
            (r["measured_reuse"][ekey] if r["router_choice"][ekey] == "certified_reuse" else r["measured_inc"][ekey])
            + r["router_decision_cost"][ekey]
            for r in task_results
        )
        tot_rtr_full = tot_rtr_exec + cal_e
        acc = sum(1 for r in task_results if r["router_correct"][ekey]) / len(task_results)

        # Payback task index where router (including full E_cal!) beats BOTH fixed policies
        c_inc = c_reu = 0.0
        c_rtr = cal_e
        payback_idx = None
        for idx, r in enumerate(task_results, start=1):
            c_inc += r["measured_inc"][ekey]
            c_reu += r["measured_reuse"][ekey]
            c_rtr += (
                r["measured_reuse"][ekey] if r["router_choice"][ekey] == "certified_reuse" else r["measured_inc"][ekey]
            ) + r["router_decision_cost"][ekey]
            if payback_idx is None and c_rtr < c_inc and c_rtr < c_reu:
                payback_idx = idx

        policy_summary[ekey] = {
            "oracle_true_reuse_count": sum(1 for r in task_results if r["oracle_choice"][ekey] == "certified_reuse"),
            "oracle_true_inc_count": sum(1 for r in task_results if r["oracle_choice"][ekey] == "strong_incremental"),
            "router_selection_accuracy": round(acc, 4),
            "calibration_energy_j": round(cal_e, 4),
            "calibration_payback_task_index": payback_idx,
            "oracle": {"total_energy_j": round(tot_ora, 4), "regret_vs_oracle_j": 0.0, "regret_pct": 0.0},
            "always_incremental": {
                "total_energy_j": round(tot_inc, 4),
                "regret_vs_oracle_j": round(tot_inc - tot_ora, 4),
                "regret_pct": round(100.0 * (tot_inc - tot_ora) / tot_ora, 2),
            },
            "always_reuse": {
                "total_energy_j": round(tot_reu, 4),
                "regret_vs_oracle_j": round(tot_reu - tot_ora, 4),
                "regret_pct": round(100.0 * (tot_reu - tot_ora) / tot_ora, 2),
            },
            "router_exec_only": {
                "total_energy_j": round(tot_rtr_exec, 4),
                "regret_vs_oracle_j": round(tot_rtr_exec - tot_ora, 4),
                "regret_pct": round(100.0 * (tot_rtr_exec - tot_ora) / tot_ora, 2),
            },
            "router_with_cal": {
                "total_energy_j": round(tot_rtr_full, 4),
                "regret_vs_oracle_j": round(tot_rtr_full - tot_ora, 4),
                "regret_pct": round(100.0 * (tot_rtr_full - tot_ora) / tot_ora, 2),
                "savings_vs_always_inc_pct": round(100.0 * (tot_inc - tot_rtr_full) / tot_inc, 2),
                "savings_vs_always_reuse_pct": round(100.0 * (tot_reu - tot_rtr_full) / tot_reu, 2),
            },
        }

    print("\n=== exp_hw05 TEMPORAL ENERGY ROUTER SUMMARY (24 UNSEEN TASKS) ===")
    for ek in ("proc_cpu_energy_j", "soc_package_j"):
        ps = policy_summary[ek]
        print(
            f"  [{ek}] acc={ps['router_selection_accuracy']*100:.1f}% "
            f"(oracle split: {ps['oracle_true_reuse_count']} reuse / {ps['oracle_true_inc_count']} inc) | "
            f"AlwaysInc={ps['always_incremental']['total_energy_j']:.2f}J (reg={ps['always_incremental']['regret_vs_oracle_j']:.2f}J) | "
            f"AlwaysReuse={ps['always_reuse']['total_energy_j']:.2f}J (reg={ps['always_reuse']['regret_vs_oracle_j']:.2f}J) | "
            f"Router(exec)={ps['router_exec_only']['total_energy_j']:.2f}J (reg={ps['router_exec_only']['regret_vs_oracle_j']:.2f}J) | "
            f"Router(+E_cal)={ps['router_with_cal']['total_energy_j']:.2f}J (payback=task #{ps['calibration_payback_task_index']})"
        )

    end_ctx = get_system_context()
    generate_figures(task_results, policy_summary, router_meta)

    summary = {
        "experiment_id": "exp_hw05_temporal_energy_router",
        "version": "0.1.0",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sealed_decisions_sha256": seal,
        "strict_blind_disjoint_seeds": True,
        "n_unseen_tasks": len(task_results),
        "n_eval_blocks_per_task": N_EVAL_BLOCKS,
        "mismatches_total": 0,
        "machine": meta,
        "system_context_start": start_ctx,
        "system_context_end": end_ctx,
        "calibration": calib,
        "router_calibration": router_meta,
        "policy_comparison": policy_summary,
        "per_task_results": task_results,
    }
    out_p = RESULTS_DIR / "exp_hw05_summary.json"
    out_p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved exp_hw05 summary -> {out_p}")


if __name__ == "__main__":
    main()
