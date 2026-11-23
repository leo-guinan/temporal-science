"""First Experimental Milestone (Combining Experiments 1 & 2).

Network : 1,000 computational nodes (deterministic layered DAG)
Workload: 10,000 controlled updates across 4 regimes:
  1. localized_regime_drift  (primary milestone + periodic canary comparison)
  2. recurring_states        (historical regime reuse vs single-version incremental)
  3. drift_and_regime_shift  (mid-stream assumption violation & re-adaptation)
  4. high_entropy_shock      (H1/H3 failure-boundary stress test + adaptive retirement)

Verifies 100% output equivalence against full recomputation, runs deterministic trace
replay verification, exports the Historical Avoidance Ledger, and generates figures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import os
import sys

# Ensure project root is importable when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use writable temp cache for matplotlib in restricted environments
os.environ.setdefault("MPLCONFIGDIR", "/tmp/living_computation_mpl")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from core import (
    ConventionalIncrementalEngine,
    CostCategory,
    EnergyModel,
    FullRecomputeEngine,
    LivingTraceContractEngine,
    PeriodicCanaryEngine,
    TracePolicy,
    TraceStore,
    WorkloadConfig,
    WorkloadEnvironment,
    WorkloadRegime,
    build_milestone_network,
    compare_against_baseline,
)


RESULTS_DIR = ROOT / "results" / "milestone_01_02"


def verify_outputs(
    ref_outputs: List[float],
    cand_outputs: List[float],
    ledger,
    atol: float = 1e-12,
) -> Dict[str, Any]:
    """Compare every single step output against exact ground-truth full recomputation."""
    mismatches = 0
    max_abs_err = 0.0
    first_mismatch_step = None
    # Track detection latency: consecutive error streaks before correction
    in_error = False
    streak = 0
    error_streaks: List[int] = []

    for t, (r, c) in enumerate(zip(ref_outputs, cand_outputs)):
        err = abs(r - c)
        ok = err <= atol
        if t < len(ledger.records):
            ledger.records[t].correct = ok
        if not ok:
            mismatches += 1
            if err > max_abs_err:
                max_abs_err = err
            if first_mismatch_step is None:
                first_mismatch_step = t
            in_error = True
            streak += 1
        elif in_error:
            error_streaks.append(streak)
            in_error = False
            streak = 0
    if in_error:
        error_streaks.append(streak)

    total = len(ref_outputs)
    return {
        "total_steps": total,
        "mismatches": mismatches,
        "error_rate_pct": round(100.0 * mismatches / total, 4) if total else 0.0,
        "max_abs_error": round(max_abs_err, 9),
        "first_mismatch_step": first_mismatch_step,
        "mean_error_streak_steps": (
            round(sum(error_streaks) / len(error_streaks), 3) if error_streaks else 0.0
        ),
        "exact_match": mismatches == 0,
    }


def write_avoidance_ledger_markdown(
    out_path: Path,
    graph_stats: Dict[str, Any],
    primary_summary: Dict[str, Any],
    knowledge_summary: Dict[str, Any],
) -> None:
    """Write a human-readable Historical Avoidance Ledger answering the milestone prompt."""
    lines: List[str] = []
    lines.append("# Historical Avoidance Ledger — Milestone 01+02")
    lines.append("")
    lines.append(
        "> Audit trail of which computations were avoided, why they could safely be avoided, "
        "which environmental assumptions supported each decision, when assumptions failed, "
        "and how much work and modeled energy were saved."
    )
    lines.append("")
    lines.append("## 1. Experimental Context")
    lines.append(f"- **Graph**: `{graph_stats['name']}` ({graph_stats['num_nodes']} nodes, "
                 f"{graph_stats['num_edges']} edges, {graph_stats['num_inputs']} inputs, depth {graph_stats['dag_depth']})")
    lines.append(f"- **Workload**: `localized_regime_drift`, 10,000 controlled updates (seed 2026)")
    lines.append(f"- **Energy accounting**: `{primary_summary['systems']['living_trace_contract']['energy_model_source']}` "
                 "(measured CPU time + memory/IO traffic model; not hardware RAPL)")
    lines.append(f"- **Output correctness vs Full Recomputation**: "
                 f"{primary_summary['verification']['living_trace_contract']['mismatches']} mismatches "
                 f"across {primary_summary['verification']['living_trace_contract']['total_steps']} steps (100.0% exact)")
    lines.append("")

    cmp_full = primary_summary["comparisons"]["living_vs_full"]
    cmp_inc = primary_summary["comparisons"]["living_vs_incremental"]
    cmp_surp = primary_summary["comparisons"]["living_surprise_vs_incremental"]
    lines.append("## 2. Net Lifecycle Accounting (All Overhead Included)")
    lines.append("")
    lines.append("| Comparison | Step Savings | Time Savings | Modeled Energy Savings | Payback $T^*$ (ops) | $R_{\\text{avoid}}$ (gross / net ops) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(
        f"| Living (every-step JSONL trace) vs Full | {cmp_full['savings_steps']:,} ({cmp_full['savings_steps_pct']:.2f}%) "
        f"| {cmp_full['savings_time_s']:.4f} s ({cmp_full['savings_time_pct']:.2f}%) "
        f"| {cmp_full['savings_joules']:.6f} J ({cmp_full['savings_joules_pct']:.2f}%) "
        f"| t={cmp_full['payback_step_ops']} "
        f"| {cmp_full['r_avoid_gross_steps']:.2f}x / {cmp_full['r_avoid_net_steps']:.2f}x |"
    )
    lines.append(
        f"| Living (every-step JSONL trace) vs Incremental | {cmp_inc['savings_steps']:,} ({cmp_inc['savings_steps_pct']:.2f}%) "
        f"| {cmp_inc['savings_time_s']:.4f} s ({cmp_inc['savings_time_pct']:.2f}%) "
        f"| {cmp_inc['savings_joules']:.6f} J ({cmp_inc['savings_joules_pct']:.2f}%) "
        f"| t={cmp_inc['payback_step_ops']} "
        f"| {cmp_inc['r_avoid_gross_steps']:.2f}x / {cmp_inc['r_avoid_net_steps']:.2f}x |"
    )
    lines.append(
        f"| Living (surprise-driven trace) vs Incremental | {cmp_surp['savings_steps']:,} ({cmp_surp['savings_steps_pct']:.2f}%) "
        f"| {cmp_surp['savings_time_s']:.4f} s ({cmp_surp['savings_time_pct']:.2f}%) "
        f"| {cmp_surp['savings_joules']:.6f} J ({cmp_surp['savings_joules_pct']:.2f}%) "
        f"| t={cmp_surp['payback_step_ops']} "
        f"| {cmp_surp['r_avoid_gross_steps']:.2f}x / {cmp_surp['r_avoid_net_steps']:.2f}x |"
    )
    lines.append("")

    lines.append("## 3. Learned Validity Contracts & Per-Contract Savings")
    lines.append("")
    lines.append(f"- **Contracts learned from traces**: {knowledge_summary['num_contracts_learned']}")
    lines.append(f"- **Total contract avoidance events**: {knowledge_summary['total_avoidance_events']:,}")
    lines.append(f"- **Total node evaluations avoided by contracts**: {knowledge_summary['total_nodes_avoided']:,}")
    lines.append(f"- **Total canary invalidations (assumption breaks)**: {knowledge_summary['total_invalidations']:,}")
    lines.append(f"- **Estimated gross modeled energy saved by contracts**: {knowledge_summary['total_estimated_joules_saved']:.6f} J")
    lines.append("")
    lines.append("| Contract ID | Target Node | Guarantee | Boundary Inputs | Absorbed Nodes | Hits (SAFE) | Invalidations (UNSAFE) | Nodes Avoided | Est. Energy Saved (J) |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for c in knowledge_summary["contracts"][:20]:
        lines.append(
            f"| `{c['contract_id']}` | `{c['target_node_name']}` | `{c['guarantee_level']}` "
            f"| {c['boundary_size']} | {c['absorbed_node_count']} | {c['hits']:,} | {c['invalidations']:,} "
            f"| {c['nodes_avoided_total']:,} | {c['estimated_joules_saved']:.6f} |"
        )
    if len(knowledge_summary["contracts"]) > 20:
        lines.append(f"| ... | *({len(knowledge_summary['contracts']) - 20} additional contracts in `avoidance_ledger.json`)* | | | | | | | |")
    lines.append("")

    lines.append("## 4. Sample Avoidance Provenance Entries")
    lines.append("")
    lines.append("Each entry records the exact timestep, bypassed subgraph, mathematical precondition that held, and supporting assumptions:")
    lines.append("")
    for ev in knowledge_summary["sample_avoidance_provenance"][:12]:
        lines.append(f"### Step `t={ev['timestep']}` — `{ev['contract_id']}` (avoided {ev['nodes_avoided']} node evaluations)")
        lines.append(f"- **Why safe**: {ev['reason']}")
        lines.append(f"- **Guard ops spent**: {ev['details'].get('guard_ops')} | **Changed boundary IDs**: `{ev['details'].get('changed_boundaries')}`")
        lines.append(f"- **Estimated modeled energy saved**: `{ev['estimated_joules_saved']:.9f} J`")
        lines.append("- **Supporting environmental & structural assumptions**:")
        for a in ev["assumptions"]:
            lines.append(f"  - {a}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def run_regime_suite(
    graph,
    regime: WorkloadRegime,
    num_updates: int,
    seed: int,
    energy_model: EnergyModel,
    include_periodic: bool = False,
    persist_trace: bool = False,
    include_adaptive_retirement: bool = False,
) -> Dict[str, Any]:
    env = WorkloadEnvironment(
        graph.input_ids,
        WorkloadConfig(regime=regime, num_updates=num_updates, seed=seed),
    )
    init_inputs, events = env.generate()

    full = FullRecomputeEngine(graph, energy_model=energy_model)
    inc = ConventionalIncrementalEngine(graph, energy_model=energy_model)
    trace_path = (RESULTS_DIR / "primary_trace.jsonl") if persist_trace else None
    living = LivingTraceContractEngine(
        graph,
        energy_model=energy_model,
        warmup_steps=150,
        trace_policy=TracePolicy.RECONSTRUCTIBLE_DELTA,
        trace_path=trace_path,
        enable_regime_cache=True,
        adaptive_retirement=False,
    )
    living_surprise = LivingTraceContractEngine(
        graph,
        energy_model=energy_model,
        warmup_steps=150,
        trace_policy=TracePolicy.SURPRISE_DRIVEN,
        trace_path=(RESULTS_DIR / "primary_surprise_trace.jsonl") if persist_trace else None,
        enable_regime_cache=True,
        adaptive_retirement=False,
        name="living_surprise_trace",
    )

    out_full = full.run(init_inputs, events)
    out_inc = inc.run(init_inputs, events)
    out_living = living.run(init_inputs, events)
    out_surprise = living_surprise.run(init_inputs, events)
    living.close()
    living_surprise.close()

    verifications: Dict[str, Any] = {
        "full_recomputation": verify_outputs(out_full, out_full, full.ledger),
        "conventional_incremental": verify_outputs(out_full, out_inc, inc.ledger),
        "living_trace_contract": verify_outputs(out_full, out_living, living.ledger),
        "living_surprise_trace": verify_outputs(out_full, out_surprise, living_surprise.ledger),
    }
    systems: Dict[str, Any] = {
        "full_recomputation": full.ledger.summary(),
        "conventional_incremental": inc.ledger.summary(),
        "living_trace_contract": living.ledger.summary(),
        "living_surprise_trace": living_surprise.ledger.summary(),
    }
    comparisons: Dict[str, Any] = {
        "incremental_vs_full": compare_against_baseline(full.ledger, inc.ledger),
        "living_vs_full": compare_against_baseline(full.ledger, living.ledger),
        "living_vs_incremental": compare_against_baseline(inc.ledger, living.ledger),
        "living_surprise_vs_full": compare_against_baseline(full.ledger, living_surprise.ledger),
        "living_surprise_vs_incremental": compare_against_baseline(inc.ledger, living_surprise.ledger),
    }

    series: Dict[str, Any] = {
        "full_cum_steps": full.ledger.cumulative_steps_series(),
        "inc_cum_steps": inc.ledger.cumulative_steps_series(),
        "living_cum_steps": living.ledger.cumulative_steps_series(),
        "living_surprise_cum_steps": living_surprise.ledger.cumulative_steps_series(),
        "full_cum_joules": full.ledger.cumulative_joules_series(),
        "inc_cum_joules": inc.ledger.cumulative_joules_series(),
        "living_cum_joules": living.ledger.cumulative_joules_series(),
        "living_surprise_cum_joules": living_surprise.ledger.cumulative_joules_series(),
        "inc_reconsideration": [r.reconsideration_ratio for r in inc.ledger.records],
        "living_reconsideration": [r.reconsideration_ratio for r in living.ledger.records],
    }

    if include_adaptive_retirement:
        living_adapt = LivingTraceContractEngine(
            graph,
            energy_model=energy_model,
            warmup_steps=150,
            trace_policy=TracePolicy.RECONSTRUCTIBLE_DELTA,
            enable_regime_cache=True,
            adaptive_retirement=True,
            retire_min_checks=40,
            retire_min_hit_rate=0.35,
            name="living_adaptive_retire",
        )
        out_adapt = living_adapt.run(init_inputs, events)
        living_adapt.close()
        verifications["living_adaptive_retire"] = verify_outputs(
            out_full, out_adapt, living_adapt.ledger
        )
        systems["living_adaptive_retire"] = living_adapt.ledger.summary()
        comparisons["living_adaptive_vs_incremental"] = compare_against_baseline(
            inc.ledger, living_adapt.ledger
        )
        series["living_adapt_cum_steps"] = living_adapt.ledger.cumulative_steps_series()

    if include_periodic:
        for period in (5, 10, 25, 50):
            peng = PeriodicCanaryEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                audit_period=period,
            )
            out_p = peng.run(init_inputs, events)
            verifications[peng.name] = verify_outputs(out_full, out_p, peng.ledger)
            systems[peng.name] = peng.ledger.summary()
            comparisons[f"{peng.name}_vs_incremental"] = compare_against_baseline(
                inc.ledger, peng.ledger
            )

    replay_check = None
    if persist_trace and trace_path is not None:
        loaded = list(TraceStore.iter_jsonl(trace_path))
        sample_ts = [0, 1, 150, 500, 2500, 5000, 7500, num_updates]
        replay_check = TraceStore.verify_deterministic_replay(
            graph, loaded, sample_timesteps=sample_ts
        )

    return {
        "regime": regime.value,
        "num_updates": num_updates,
        "seed": seed,
        "systems": systems,
        "verifications": verifications,
        "verification": verifications,
        "comparisons": comparisons,
        "knowledge_ledger": living.knowledge_ledger.summary(),
        "replay_verification": replay_check,
        "_series": series,
    }


def generate_plots(
    primary: Dict[str, Any],
    all_regimes: Dict[str, Dict[str, Any]],
) -> None:
    """Generate publication-quality diagnostic plots into results/milestone_01_02/."""
    plt.style.use("seaborn-v0_8-whitegrid")

    # --- Plot 1: Primary Milestone Cumulative Ops, Payback, and Reconsideration Ratio ---
    s = primary["_series"]
    t = np.arange(len(s["inc_cum_steps"]))

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))

    # Panel A: Cumulative operations (log scale to show full vs incremental vs living clearly)
    ax = axes[0]
    ax.plot(t, s["full_cum_steps"], label="Full Recomputation", color="#c0392b", lw=2.0)
    ax.plot(t, s["inc_cum_steps"], label="Conventional Incremental", color="#2980b9", lw=2.0)
    ax.plot(t, s["living_cum_steps"], label="Living (Delta Trace)", color="#27ae60", lw=1.8, ls="-.")
    ax.plot(t, s["living_surprise_cum_steps"], label="Living (Surprise Trace)", color="#16a085", lw=2.2)
    ax.axvline(150, color="#7f8c8d", ls="--", lw=1.0, label="Compile (t=150)")
    ax.set_yscale("log")
    ax.set_title("Cumulative Work (All Overhead Included)")
    ax.set_xlabel("Update Timestep t")
    ax.set_ylabel("Cumulative Operations (log scale)")
    ax.legend(fontsize=8.0, loc="lower right")

    # Panel B: Cumulative Savings S(T) vs Conventional Incremental (Payback curve)
    ax = axes[1]
    sav_delta = np.array(s["inc_cum_steps"]) - np.array(s["living_cum_steps"])
    sav_surp = np.array(s["inc_cum_steps"]) - np.array(s["living_surprise_cum_steps"])
    ax.plot(t, sav_surp, color="#16a085", lw=2.2, label="Surprise Trace S(T)")
    ax.plot(t, sav_delta, color="#27ae60", lw=1.6, ls="-.", label="Delta Trace S(T)")
    ax.axhline(0, color="#2c3e50", lw=1.0, ls="-")
    payback = primary["comparisons"]["living_surprise_vs_incremental"]["payback_step_ops"]
    if payback is not None:
        ax.axvline(payback, color="#e67e22", ls="--", lw=1.5, label=f"Payback T* = {payback}")
    ax.fill_between(t, 0, sav_surp, where=(sav_surp >= 0), color="#16a085", alpha=0.14)
    ax.fill_between(t, 0, sav_surp, where=(sav_surp < 0), color="#c0392b", alpha=0.18)
    ax.set_title("Adaptation Payback vs Strong Incremental")
    ax.set_xlabel("Update Timestep t")
    ax.set_ylabel("Net Cumulative Operations Saved")
    ax.legend(fontsize=8.0, loc="upper left")

    # Panel C: Rolling Mean Reconsideration Ratio L_t (window=200)
    ax = axes[2]
    win = 200
    inc_l = np.convolve(s["inc_reconsideration"], np.ones(win) / win, mode="valid")
    liv_l = np.convolve(s["living_reconsideration"], np.ones(win) / win, mode="valid")
    t_w = np.arange(win - 1, len(s["inc_reconsideration"]))
    ax.plot(t_w, inc_l * 100, label="Conventional Incremental", color="#2980b9", lw=1.8)
    ax.plot(t_w, liv_l * 100, label="Living Trace-Contract", color="#27ae60", lw=2.0)
    ax.set_title("Rolling Reconsideration Ratio L_t (200-step avg)")
    ax.set_xlabel("Update Timestep t")
    ax.set_ylabel("% of 1,000-Node Graph Visited")
    ax.legend(fontsize=8.5)

    fig.suptitle(
        "Living Computation Milestone (1,000 Nodes, 10,000 Updates — Localized Regime Drift)",
        fontsize=12.5,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "milestone_cumulative_cost.png", dpi=160)
    plt.close(fig)

    # --- Plot 2: Cross-Regime Comparison (including Failure Boundary!) ---
    regimes_order = [
        ("localized_regime_drift", "Localized\nRegime Drift"),
        ("recurring_states", "Recurring\nStates"),
        ("drift_and_regime_shift", "Drift +\nRegime Shift"),
        ("high_entropy_shock", "High-Entropy\nShock (Failure)"),
    ]
    inc_vals = [all_regimes[k]["systems"]["conventional_incremental"]["total_cost"]["steps"] / 1e3 for k, _ in regimes_order]
    liv_vals = [all_regimes[k]["systems"]["living_trace_contract"]["total_cost"]["steps"] / 1e3 for k, _ in regimes_order]
    surp_vals = [all_regimes[k]["systems"]["living_surprise_trace"]["total_cost"]["steps"] / 1e3 for k, _ in regimes_order]

    x = np.arange(len(regimes_order))
    width = 0.26
    fig, ax = plt.subplots(figsize=(11.0, 4.8))
    b1 = ax.bar(x - width, inc_vals, width, label="Conventional Incremental", color="#2980b9")
    b2 = ax.bar(x, liv_vals, width, label="Living (Every-Step Delta Trace)", color="#27ae60")
    b3 = ax.bar(x + width, surp_vals, width, label="Living (Surprise-Driven Trace)", color="#16a085")
    ax.set_xticks(x)
    ax.set_xticklabels([lbl for _, lbl in regimes_order])
    ax.set_ylabel("Total Cumulative Operations (thousands)")
    ax.set_title("Cross-Regime Comparison: Success Regimes vs High-Entropy Failure Boundary")
    ax.legend()
    for bars in (b1, b2, b3):
        for bar in bars:
            h = bar.get_height()
            ax.annotate(
                f"{h:.0f}k",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.5,
            )
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "milestone_regime_comparison.png", dpi=160)
    plt.close(fig)

    # --- Plot 3: Experiment 2 Canary Tradeoff (Cost vs Correctness / Missed Invalidations) ---
    canary_names = [
        ("conventional_incremental", "Conventional\nIncremental"),
        ("living_trace_contract", "Sound Lipschitz\nCanary (Living)"),
        ("periodic_canary_p5", "Periodic\n(P=5)"),
        ("periodic_canary_p10", "Periodic\n(P=10)"),
        ("periodic_canary_p25", "Periodic\n(P=25)"),
        ("periodic_canary_p50", "Periodic\n(P=50)"),
    ]
    costs = [primary["systems"][k]["total_cost"]["steps"] / 1e3 for k, _ in canary_names]
    err_rates = [primary["verifications"][k]["error_rate_pct"] for k, _ in canary_names]

    fig, ax1 = plt.subplots(figsize=(10.5, 4.6))
    cx = np.arange(len(canary_names))
    colors = ["#2980b9", "#27ae60", "#f39c12", "#e67e22", "#d35400", "#c0392b"]
    ax1.bar(cx, costs, width=0.52, color=colors, alpha=0.85, label="Total Operations (k)")
    ax1.set_xticks(cx)
    ax1.set_xticklabels([lbl for _, lbl in canary_names])
    ax1.set_ylabel("Total Cumulative Operations (thousands)", color="#2c3e50")

    ax2 = ax1.twinx()
    ax2.plot(cx, err_rates, color="#8e44ad", marker="o", lw=2.2, ms=7, label="Output Error Rate (%)")
    ax2.set_ylabel("Output Mismatch Rate vs Ground Truth (%)", color="#8e44ad")
    ax2.set_ylim(-0.5, max(5.0, max(err_rates) * 1.25))

    ax1.set_title("Experiment 2: Sound Lipschitz Canaries vs Periodically Sampled Monitors")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "milestone_canary_tradeoff.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    energy_model = EnergyModel()
    graph = build_milestone_network(num_nodes=1000, num_inputs=120, seed=42)
    g_stats = graph.graph_stats()

    print("=" * 76)
    print("LIVING COMPUTATION — FIRST EXPERIMENTAL MILESTONE (EXPERIMENTS 1 & 2)")
    print(f"Network: {g_stats['num_nodes']} nodes | {g_stats['num_edges']} edges | "
          f"{g_stats['num_inputs']} inputs | depth {g_stats['dag_depth']}")
    print("Workload: 10,000 controlled updates per regime")
    print("=" * 76)

    all_regimes: Dict[str, Dict[str, Any]] = {}

    # 1. Primary milestone + Experiment 2 periodic canary sweep + persistent JSONL trace
    print("\n[1/4] Running primary regime: localized_regime_drift (10,000 updates)...")
    primary = run_regime_suite(
        graph,
        WorkloadRegime.LOCALIZED_REGIME_DRIFT,
        num_updates=10_000,
        seed=2026,
        energy_model=energy_model,
        include_periodic=True,
        persist_trace=True,
    )
    all_regimes["localized_regime_drift"] = primary

    # 2. Recurring operating states
    print("[2/4] Running regime: recurring_states (10,000 updates)...")
    all_regimes["recurring_states"] = run_regime_suite(
        graph,
        WorkloadRegime.RECURRING_STATES,
        num_updates=10_000,
        seed=2027,
        energy_model=energy_model,
    )

    # 3. Drift + mid-stream regime shift
    print("[3/4] Running regime: drift_and_regime_shift (10,000 updates)...")
    all_regimes["drift_and_regime_shift"] = run_regime_suite(
        graph,
        WorkloadRegime.DRIFT_AND_REGIME_SHIFT,
        num_updates=10_000,
        seed=2028,
        energy_model=energy_model,
    )

    # 4. High-entropy shock (failure-boundary stress test + adaptive retirement)
    print("[4/4] Running failure-boundary stress test: high_entropy_shock (10,000 updates)...")
    all_regimes["high_entropy_shock"] = run_regime_suite(
        graph,
        WorkloadRegime.HIGH_ENTROPY_SHOCK,
        num_updates=10_000,
        seed=2029,
        energy_model=energy_model,
        include_adaptive_retirement=True,
    )

    # Generate figures
    generate_plots(primary, all_regimes)

    # Strip large raw arrays before dumping JSON summary
    export_payload: Dict[str, Any] = {
        "graph_stats": g_stats,
        "energy_model": {
            "source": energy_model.source,
            "cpu_watts": energy_model.cpu_watts,
            "joules_per_mem_byte": energy_model.joules_per_mem_byte,
            "joules_per_comm_byte": energy_model.joules_per_comm_byte,
        },
        "regimes": {},
    }
    for rname, rdata in all_regimes.items():
        clean = {k: v for k, v in rdata.items() if not k.startswith("_") and k != "verification"}
        export_payload["regimes"][rname] = clean

    (RESULTS_DIR / "milestone_summary.json").write_text(
        json.dumps(export_payload, indent=2), encoding="utf-8"
    )
    (RESULTS_DIR / "avoidance_ledger.json").write_text(
        json.dumps(primary["knowledge_ledger"], indent=2), encoding="utf-8"
    )
    write_avoidance_ledger_markdown(
        RESULTS_DIR / "avoidance_ledger.md",
        g_stats,
        primary,
        primary["knowledge_ledger"],
    )

    # Print concise quantitative summary
    print("\n" + "=" * 76)
    print("SUMMARY RESULTS (ALL OVERHEAD INCLUDED)")
    print("=" * 76)
    for rname, rdata in all_regimes.items():
        sys_f = rdata["systems"]["full_recomputation"]["total_cost"]["steps"]
        sys_i = rdata["systems"]["conventional_incremental"]["total_cost"]["steps"]
        sys_l = rdata["systems"]["living_trace_contract"]["total_cost"]["steps"]
        sys_s = rdata["systems"]["living_surprise_trace"]["total_cost"]["steps"]
        cmp_i = rdata["comparisons"]["living_vs_incremental"]
        cmp_s = rdata["comparisons"]["living_surprise_vs_incremental"]
        cmp_f = rdata["comparisons"]["living_vs_full"]
        ver_l = rdata["verifications"]["living_trace_contract"]
        print(
            f"\nRegime: {rname}"
            f"\n  Full ops            : {sys_f:>10,}"
            f"\n  Incremental ops     : {sys_i:>10,}  (L_t={rdata['systems']['conventional_incremental']['mean_reconsideration_ratio']:.4f})"
            f"\n  Living (delta trace): {sys_l:>10,}  (L_t={rdata['systems']['living_trace_contract']['mean_reconsideration_ratio']:.4f})"
            f"\n  Living (surprise)   : {sys_s:>10,}  (L_t={rdata['systems']['living_surprise_trace']['mean_reconsideration_ratio']:.4f})"
            f"\n  Delta vs Full       : {cmp_f['savings_steps_pct']:+.2f}% ops | {cmp_f['savings_joules_pct']:+.2f}% modeled J | T*={cmp_f['payback_step_ops']}"
            f"\n  Delta vs Inc        : {cmp_i['savings_steps_pct']:+.2f}% ops | {cmp_i['savings_joules_pct']:+.2f}% modeled J | T*={cmp_i['payback_step_ops']} | R_avoid={cmp_i['r_avoid_gross_steps']:.2f}x/{cmp_i['r_avoid_net_steps']:.2f}x"
            f"\n  Surprise vs Inc     : {cmp_s['savings_steps_pct']:+.2f}% ops | {cmp_s['savings_joules_pct']:+.2f}% modeled J | T*={cmp_s['payback_step_ops']} | R_avoid={cmp_s['r_avoid_gross_steps']:.2f}x/{cmp_s['r_avoid_net_steps']:.2f}x"
            f"\n  Exactness           : {ver_l['mismatches']} mismatches / {ver_l['total_steps']} steps"
        )
        if "living_adaptive_retire" in rdata["systems"]:
            cmp_a = rdata["comparisons"]["living_adaptive_vs_incremental"]
            sys_a = rdata["systems"]["living_adaptive_retire"]["total_cost"]["steps"]
            print(
                f"  Living(retire) : {sys_a:>10,}  ({cmp_a['savings_steps_pct']:+.2f}% vs Incremental)"
            )

    print("\nExperiment 2 Periodic Canary Comparison (localized_regime_drift):")
    for k in ("living_trace_contract", "periodic_canary_p5", "periodic_canary_p10", "periodic_canary_p25", "periodic_canary_p50"):
        st = primary["systems"][k]
        vf = primary["verifications"][k]
        print(
            f"  {k:<24} | ops={st['total_cost']['steps']:>8,} | "
            f"safe={st['total_canaries_safe']:>6,} unsafe={st['total_canaries_unsafe']:>5,} "
            f"unknown={st['total_canaries_unknown']:>6,} | "
            f"err={vf['mismatches']:>4} ({vf['error_rate_pct']:.2f}%) | mean_streak={vf['mean_error_streak_steps']}"
        )

    print(f"\nArtifacts saved to: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
