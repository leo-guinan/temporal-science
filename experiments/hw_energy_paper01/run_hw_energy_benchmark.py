#!/usr/bin/env python3
"""Hardware-Metered Temporal-Advantage Benchmark for Paper I (Apple M3 Max).

Bridges the gap between abstract operation counts / modeled_proxy energy and
direct Apple Silicon per-process hardware PMU energy (`proc_pid_rusage`,
`RUSAGE_INFO_V6`: `ri_energy_nj`, `ri_penergy_nj`, `ri_instructions`, `ri_cycles`,
`ri_logical_writes`, `ri_diskio_byteswritten`).

Preserves `../living-computation/` strictly read-only: imports Paper I's exact
`build_milestone_network()`, `WorkloadEnvironment`, and engines directly.

Experiments:
  HW-1 : Exact unmodified Paper I 1,000-node DAG across all 4 regimes
         (10,000 updates x 5 interleaved randomized trials after warm-up),
         explicitly comparing Abstract Ops vs Modeled Proxy J vs Real Hardware J
         vs Retired Hardware Instructions vs Wall Time, including in-memory vs
         synchronous disk JSONL trace logging.
  HW-2 : Shock-rate crossover sweep (p in {0.00, 0.02, 0.05, 0.08, 0.10, 0.15, 0.30, 0.60},
         3,000 updates x 3 trials) comparing abstract op crossover vs physical energy crossover.
  HW-3 : Node compute-granularity scaling (K in {1, 5, 20, 80} pure deterministic
         kernel iterations per node, preserving exact outputs & 0 mismatches,
         3,000 updates x 3 trials) to measure the silicon compute-density boundary.
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
import tempfile

# Ensure read-only Living Computation core is importable
EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
LC_ROOT = (TS_ROOT / "../living-computation").resolve()
sys.path.insert(0, str(LC_ROOT))
sys.path.insert(0, str(EXP_DIR))

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
from core.dependency_graph import DependencyGraph, Node
from telemetry_macos import (
    delta_sample,
    get_machine_metadata,
    run_linearity_calibration,
    snapshot_raw,
)

RESULTS_DIR = EXP_DIR / "results"


def _ci95(values: List[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return 1.96 * statistics.stdev(values) / math.sqrt(len(values))


def _agg(values: List[float]) -> Dict[str, float]:
    return {
        "mean": round(statistics.mean(values), 6),
        "std": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
        "ci95": round(_ci95(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def _pct_savings(base: float, cand: float) -> float:
    return round(100.0 * (base - cand) / base, 3) if base > 0 else 0.0


def _make_granularity_graph(k_iters: int) -> DependencyGraph:
    """Build the exact 1,000-node Paper I DAG, optionally scaling pure node compute intensity K.

    For K == 1, returns the completely unmodified Paper I graph.
    For K > 1, wraps each non-input node's `evaluate` with K-1 deterministic fused arithmetic
    iterations that return the EXACT same float value (preserving Lipschitz bounds & 0 mismatches).
    """
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
                # Deterministic pure numeric kernel work (representing e.g. a K-element feature kernel)
                acc = val
                for j in range(1, k):
                    acc = (acc * 0.999999 + 1e-9 * j) - (acc * 0.999999 + 1e-9 * j) + val
                return val + (acc - val) * 0.0
            return _wrapped

        node.evaluate = _make_wrapped(orig_eval, k_iters)  # type: ignore[method-assign]
    return graph


def _measure_single_run(
    factory: Callable[[], Any],
    init_inputs: Dict[int, float],
    events: List[Any],
    ref_outputs: List[float] | None = None,
) -> Tuple[Dict[str, Any], List[float]]:
    gc.collect()
    eng = factory()
    s0 = snapshot_raw()
    outputs = eng.run(init_inputs, events)
    if hasattr(eng, "close"):
        eng.close()
    s1 = snapshot_raw()
    hw = delta_sample(s0, s1)
    summary = eng.ledger.summary()

    mismatches = 0
    if ref_outputs is not None:
        for r, c in zip(ref_outputs, outputs):
            if abs(r - c) > 1e-12:
                mismatches += 1

    rec = {
        "hardware_energy_j": hw.hardware_energy_j,
        "pcore_energy_j": hw.pcore_energy_j,
        "instructions": hw.instructions,
        "cycles": hw.cycles,
        "ipc": hw.ipc,
        "avg_power_w": hw.avg_power_w,
        "wall_time_s": hw.wall_time_s,
        "user_time_s": hw.user_time_s,
        "system_time_s": hw.system_time_s,
        "logical_writes_bytes": hw.logical_writes_bytes,
        "disk_bytes_written": hw.disk_bytes_written,
        "phys_footprint_end_mb": hw.phys_footprint_end_mb,
        "abstract_ops": summary["total_cost"]["steps"],
        "modeled_proxy_j": summary["total_cost"]["joules"],
        "mismatches": mismatches,
    }
    return rec, outputs


def _run_interleaved_trials(
    variants: Dict[str, Callable[[], Any]],
    init_inputs: Dict[int, float],
    events: List[Any],
    n_trials: int,
    seed: int,
    ref_outputs: List[float],
) -> Dict[str, Any]:
    rng = random.Random(seed)
    names = list(variants.keys())

    # 1 discarded warm-up pass for CPU frequency/caches/Python bytecode warm-up
    for nm in names:
        _measure_single_run(variants[nm], init_inputs, events, ref_outputs=ref_outputs)

    raw: Dict[str, List[Dict[str, Any]]] = {nm: [] for nm in names}
    for trial in range(n_trials):
        order = list(names)
        rng.shuffle(order)
        for nm in order:
            rec, _ = _measure_single_run(variants[nm], init_inputs, events, ref_outputs=ref_outputs)
            assert rec["mismatches"] == 0, f"Soundness error in {nm} trial {trial}: {rec['mismatches']}"
            raw[nm].append(rec)

    aggregated: Dict[str, Any] = {}
    for nm in names:
        rows = raw[nm]
        aggregated[nm] = {
            "n_trials": n_trials,
            "mismatches_total": sum(r["mismatches"] for r in rows),
            "abstract_ops": rows[0]["abstract_ops"],
            "modeled_proxy_j": _agg([r["modeled_proxy_j"] for r in rows]),
            "hardware_energy_j": _agg([r["hardware_energy_j"] for r in rows]),
            "pcore_energy_j": _agg([r["pcore_energy_j"] for r in rows]),
            "instructions": _agg([float(r["instructions"]) for r in rows]),
            "cycles": _agg([float(r["cycles"]) for r in rows]),
            "ipc": _agg([r["ipc"] for r in rows]),
            "avg_power_w": _agg([r["avg_power_w"] for r in rows]),
            "wall_time_s": _agg([r["wall_time_s"] for r in rows]),
            "user_time_s": _agg([r["user_time_s"] for r in rows]),
            "system_time_s": _agg([r["system_time_s"] for r in rows]),
            "logical_writes_bytes": _agg([float(r["logical_writes_bytes"]) for r in rows]),
            "disk_bytes_written": _agg([float(r["disk_bytes_written"]) for r in rows]),
            "phys_footprint_end_mb": _agg([r["phys_footprint_end_mb"] for r in rows]),
        }
    return aggregated


def _compare_pair(base: Dict[str, Any], cand: Dict[str, Any]) -> Dict[str, float]:
    return {
        "savings_abstract_ops_pct": _pct_savings(base["abstract_ops"], cand["abstract_ops"]),
        "savings_modeled_proxy_j_pct": _pct_savings(
            base["modeled_proxy_j"]["mean"], cand["modeled_proxy_j"]["mean"]
        ),
        "savings_hardware_energy_j_pct": _pct_savings(
            base["hardware_energy_j"]["mean"], cand["hardware_energy_j"]["mean"]
        ),
        "savings_instructions_pct": _pct_savings(
            base["instructions"]["mean"], cand["instructions"]["mean"]
        ),
        "savings_cycles_pct": _pct_savings(base["cycles"]["mean"], cand["cycles"]["mean"]),
        "savings_wall_time_pct": _pct_savings(base["wall_time_s"]["mean"], cand["wall_time_s"]["mean"]),
        "delta_hardware_energy_j": round(
            base["hardware_energy_j"]["mean"] - cand["hardware_energy_j"]["mean"], 6
        ),
    }


def run_exp_hw1(energy_model: EnergyModel, tmp_dir: Path) -> Dict[str, Any]:
    """Experiment HW-1: Exact unmodified Paper I 1,000-node DAG across all 4 regimes (10,000 updates x 5 trials)."""
    print("[HW-1] Running exact unmodified Paper I 1,000-node DAG across 4 regimes (10,000 updates x 5 trials)...")
    graph = build_milestone_network()
    out: Dict[str, Any] = {}

    # 1. localized_regime_drift (primary + disk JSONL trace comparison)
    env = WorkloadEnvironment(
        graph.input_ids,
        WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=10_000, seed=2026),
    )
    init_inputs, events = env.generate()
    ref_out = FullRecomputeEngine(graph, energy_model=energy_model).run(init_inputs, events)

    disk_trace_file = tmp_dir / "hw1_surprise_trace.jsonl"

    def _disk_factory():
        if disk_trace_file.exists():
            disk_trace_file.unlink()
        return LivingTraceContractEngine(
            graph,
            energy_model=energy_model,
            warmup_steps=150,
            trace_policy=TracePolicy.SURPRISE_DRIVEN,
            trace_path=disk_trace_file,
            enable_regime_cache=True,
            adaptive_retirement=False,
            name="living_disk_jsonl_surprise",
        )

    res_loc = _run_interleaved_trials(
        variants={
            "full_recompute": lambda: FullRecomputeEngine(graph, energy_model=energy_model),
            "strong_incremental": lambda: ConventionalIncrementalEngine(graph, energy_model=energy_model),
            "living_inmem_surprise": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.SURPRISE_DRIVEN,
                trace_path=None,
                enable_regime_cache=True,
                adaptive_retirement=False,
                name="living_inmem_surprise",
            ),
            "living_inmem_delta": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.RECONSTRUCTIBLE_DELTA,
                trace_path=None,
                enable_regime_cache=True,
                adaptive_retirement=False,
                name="living_inmem_delta",
            ),
            "living_disk_jsonl_surprise": _disk_factory,
        },
        init_inputs=init_inputs,
        events=events,
        n_trials=5,
        seed=101,
        ref_outputs=ref_out,
    )
    out["localized_regime_drift"] = {
        "systems": res_loc,
        "comparisons": {
            "living_inmem_surprise_vs_full": _compare_pair(res_loc["full_recompute"], res_loc["living_inmem_surprise"]),
            "living_inmem_surprise_vs_incremental": _compare_pair(
                res_loc["strong_incremental"], res_loc["living_inmem_surprise"]
            ),
            "living_inmem_delta_vs_incremental": _compare_pair(
                res_loc["strong_incremental"], res_loc["living_inmem_delta"]
            ),
            "living_disk_jsonl_vs_incremental": _compare_pair(
                res_loc["strong_incremental"], res_loc["living_disk_jsonl_surprise"]
            ),
        },
    }
    print(
        "  localized_regime_drift (inmem surprise vs inc): "
        f"ops={out['localized_regime_drift']['comparisons']['living_inmem_surprise_vs_incremental']['savings_abstract_ops_pct']:+.2f}%, "
        f"proxy_J={out['localized_regime_drift']['comparisons']['living_inmem_surprise_vs_incremental']['savings_modeled_proxy_j_pct']:+.2f}%, "
        f"HW_J={out['localized_regime_drift']['comparisons']['living_inmem_surprise_vs_incremental']['savings_hardware_energy_j_pct']:+.2f}%, "
        f"HW_inst={out['localized_regime_drift']['comparisons']['living_inmem_surprise_vs_incremental']['savings_instructions_pct']:+.2f}%"
    )
    print(
        "  localized_regime_drift (disk JSONL vs inc):     "
        f"ops={out['localized_regime_drift']['comparisons']['living_disk_jsonl_vs_incremental']['savings_abstract_ops_pct']:+.2f}%, "
        f"proxy_J={out['localized_regime_drift']['comparisons']['living_disk_jsonl_vs_incremental']['savings_modeled_proxy_j_pct']:+.2f}%, "
        f"HW_J={out['localized_regime_drift']['comparisons']['living_disk_jsonl_vs_incremental']['savings_hardware_energy_j_pct']:+.2f}%"
    )

    # 2. drift_and_regime_shift
    env2 = WorkloadEnvironment(
        graph.input_ids,
        WorkloadConfig(regime=WorkloadRegime.DRIFT_AND_REGIME_SHIFT, num_updates=10_000, seed=2026),
    )
    init2, ev2 = env2.generate()
    ref2 = FullRecomputeEngine(graph, energy_model=energy_model).run(init2, ev2)
    res_shift = _run_interleaved_trials(
        variants={
            "full_recompute": lambda: FullRecomputeEngine(graph, energy_model=energy_model),
            "strong_incremental": lambda: ConventionalIncrementalEngine(graph, energy_model=energy_model),
            "living_inmem_surprise": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.SURPRISE_DRIVEN,
                trace_path=None,
                enable_regime_cache=True,
                adaptive_retirement=False,
            ),
        },
        init_inputs=init2,
        events=ev2,
        n_trials=5,
        seed=102,
        ref_outputs=ref2,
    )
    out["drift_and_regime_shift"] = {
        "systems": res_shift,
        "comparisons": {
            "living_inmem_surprise_vs_full": _compare_pair(res_shift["full_recompute"], res_shift["living_inmem_surprise"]),
            "living_inmem_surprise_vs_incremental": _compare_pair(
                res_shift["strong_incremental"], res_shift["living_inmem_surprise"]
            ),
        },
    }
    print(
        "  drift_and_regime_shift (inmem surprise vs inc): "
        f"ops={out['drift_and_regime_shift']['comparisons']['living_inmem_surprise_vs_incremental']['savings_abstract_ops_pct']:+.2f}%, "
        f"HW_J={out['drift_and_regime_shift']['comparisons']['living_inmem_surprise_vs_incremental']['savings_hardware_energy_j_pct']:+.2f}%"
    )

    # 3. recurring_states
    env3 = WorkloadEnvironment(
        graph.input_ids,
        WorkloadConfig(regime=WorkloadRegime.RECURRING_STATES, num_updates=10_000, seed=2026),
    )
    init3, ev3 = env3.generate()
    ref3 = FullRecomputeEngine(graph, energy_model=energy_model).run(init3, ev3)
    res_rec = _run_interleaved_trials(
        variants={
            "strong_incremental": lambda: ConventionalIncrementalEngine(graph, energy_model=energy_model),
            "living_single_anchor": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.SURPRISE_DRIVEN,
                enable_regime_cache=False,
                adaptive_retirement=False,
                name="living_single_anchor",
            ),
            "living_multi_anchor_atlas": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.SURPRISE_DRIVEN,
                enable_regime_cache=True,
                adaptive_retirement=False,
                name="living_multi_anchor_atlas",
            ),
        },
        init_inputs=init3,
        events=ev3,
        n_trials=5,
        seed=103,
        ref_outputs=ref3,
    )
    out["recurring_states"] = {
        "systems": res_rec,
        "comparisons": {
            "single_anchor_vs_incremental": _compare_pair(res_rec["strong_incremental"], res_rec["living_single_anchor"]),
            "multi_anchor_vs_incremental": _compare_pair(
                res_rec["strong_incremental"], res_rec["living_multi_anchor_atlas"]
            ),
        },
    }
    print(
        "  recurring_states (multi-anchor vs inc):         "
        f"ops={out['recurring_states']['comparisons']['multi_anchor_vs_incremental']['savings_abstract_ops_pct']:+.2f}%, "
        f"HW_J={out['recurring_states']['comparisons']['multi_anchor_vs_incremental']['savings_hardware_energy_j_pct']:+.2f}%"
    )

    # 4. high_entropy_shock (failure boundary)
    env4 = WorkloadEnvironment(
        graph.input_ids,
        WorkloadConfig(regime=WorkloadRegime.HIGH_ENTROPY_SHOCK, num_updates=10_000, seed=2026),
    )
    init4, ev4 = env4.generate()
    ref4 = FullRecomputeEngine(graph, energy_model=energy_model).run(init4, ev4)
    res_shk = _run_interleaved_trials(
        variants={
            "strong_incremental": lambda: ConventionalIncrementalEngine(graph, energy_model=energy_model),
            "living_static_no_retire": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.SURPRISE_DRIVEN,
                enable_regime_cache=True,
                adaptive_retirement=False,
                name="living_static_no_retire",
            ),
            "living_adaptive_retire": lambda: LivingTraceContractEngine(
                graph,
                energy_model=energy_model,
                warmup_steps=150,
                trace_policy=TracePolicy.SURPRISE_DRIVEN,
                enable_regime_cache=True,
                adaptive_retirement=True,
                retire_min_checks=40,
                retire_min_hit_rate=0.35,
                name="living_adaptive_retire",
            ),
        },
        init_inputs=init4,
        events=ev4,
        n_trials=5,
        seed=104,
        ref_outputs=ref4,
    )
    out["high_entropy_shock"] = {
        "systems": res_shk,
        "comparisons": {
            "static_vs_incremental": _compare_pair(res_shk["strong_incremental"], res_shk["living_static_no_retire"]),
            "adaptive_retire_vs_incremental": _compare_pair(
                res_shk["strong_incremental"], res_shk["living_adaptive_retire"]
            ),
        },
    }
    print(
        "  high_entropy_shock (static -> retire vs inc):   "
        f"HW_J={out['high_entropy_shock']['comparisons']['static_vs_incremental']['savings_hardware_energy_j_pct']:+.2f}% -> "
        f"{out['high_entropy_shock']['comparisons']['adaptive_retire_vs_incremental']['savings_hardware_energy_j_pct']:+.2f}%"
    )
    return out


def run_exp_hw2_shock_sweep(energy_model: EnergyModel) -> List[Dict[str, Any]]:
    """Experiment HW-2: Physical Energy vs Abstract Ops crossover across shock probability p."""
    print("[HW-2] Running shock-rate physical-energy crossover sweep (3,000 updates x 3 trials)...")
    graph = build_milestone_network()
    rows = []
    for p in (0.00, 0.02, 0.05, 0.08, 0.10, 0.15, 0.30, 0.60):
        env = WorkloadEnvironment(
            graph.input_ids,
            WorkloadConfig(
                regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT,
                num_updates=3_000,
                seed=2026,
                shock_probability=p,
            ),
        )
        init_inputs, events = env.generate()
        ref = FullRecomputeEngine(graph, energy_model=energy_model).run(init_inputs, events)
        res = _run_interleaved_trials(
            variants={
                "strong_incremental": lambda: ConventionalIncrementalEngine(graph, energy_model=energy_model),
                "living_inmem_surprise": lambda: LivingTraceContractEngine(
                    graph,
                    energy_model=energy_model,
                    warmup_steps=150,
                    trace_policy=TracePolicy.SURPRISE_DRIVEN,
                    enable_regime_cache=True,
                    adaptive_retirement=False,
                ),
            },
            init_inputs=init_inputs,
            events=events,
            n_trials=3,
            seed=200 + int(p * 100),
            ref_outputs=ref,
        )
        cmp = _compare_pair(res["strong_incremental"], res["living_inmem_surprise"])
        row = {
            "shock_prob": p,
            "inc_hw_energy_j": res["strong_incremental"]["hardware_energy_j"],
            "living_hw_energy_j": res["living_inmem_surprise"]["hardware_energy_j"],
            **cmp,
        }
        rows.append(row)
        print(
            f"  p={p:4.2f}: ops={cmp['savings_abstract_ops_pct']:+6.2f}% | "
            f"proxy_J={cmp['savings_modeled_proxy_j_pct']:+6.2f}% | "
            f"HW_J={cmp['savings_hardware_energy_j_pct']:+6.2f}% | "
            f"HW_inst={cmp['savings_instructions_pct']:+6.2f}%"
        )
    return rows


def run_exp_hw3_granularity(energy_model: EnergyModel) -> List[Dict[str, Any]]:
    """Experiment HW-3: Physical silicon energy savings vs node compute granularity K."""
    print("[HW-3] Running node compute-granularity scaling sweep (K=1, 5, 20, 80; 3,000 updates x 3 trials)...")
    base_graph = build_milestone_network()
    env = WorkloadEnvironment(
        base_graph.input_ids,
        WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=3_000, seed=2026),
    )
    init_inputs, events = env.generate()
    ref_out = FullRecomputeEngine(base_graph, energy_model=energy_model).run(init_inputs, events)

    rows = []
    for k in (1, 5, 20, 80):
        g = _make_granularity_graph(k)
        res = _run_interleaved_trials(
            variants={
                "full_recompute": lambda g=g: FullRecomputeEngine(g, energy_model=energy_model),
                "strong_incremental": lambda g=g: ConventionalIncrementalEngine(g, energy_model=energy_model),
                "living_inmem_surprise": lambda g=g: LivingTraceContractEngine(
                    g,
                    energy_model=energy_model,
                    warmup_steps=150,
                    trace_policy=TracePolicy.SURPRISE_DRIVEN,
                    enable_regime_cache=True,
                    adaptive_retirement=False,
                ),
            },
            init_inputs=init_inputs,
            events=events,
            n_trials=3,
            seed=300 + k,
            ref_outputs=ref_out,
        )
        cmp_inc = _compare_pair(res["strong_incremental"], res["living_inmem_surprise"])
        cmp_full = _compare_pair(res["full_recompute"], res["living_inmem_surprise"])
        row = {
            "k_node_compute_iters": k,
            "full_hw_energy_j": res["full_recompute"]["hardware_energy_j"],
            "inc_hw_energy_j": res["strong_incremental"]["hardware_energy_j"],
            "living_hw_energy_j": res["living_inmem_surprise"]["hardware_energy_j"],
            "vs_incremental": cmp_inc,
            "vs_full": cmp_full,
        }
        rows.append(row)
        print(
            f"  K={k:2d}: vs_inc ops={cmp_inc['savings_abstract_ops_pct']:+6.2f}% | "
            f"HW_J={cmp_inc['savings_hardware_energy_j_pct']:+6.2f}% | "
            f"HW_inst={cmp_inc['savings_instructions_pct']:+6.2f}% | "
            f"wall={cmp_inc['savings_wall_time_pct']:+6.2f}% | "
            f"vs_full HW_J={cmp_full['savings_hardware_energy_j_pct']:+6.2f}%"
        )
    return rows


def generate_figures(hw1: Dict[str, Any], hw2: List[Dict[str, Any]], hw3: List[Dict[str, Any]]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Figure 1: HW-1 Abstract Ops vs Modeled Proxy J vs Real M3 Max Hardware J
    labels = [
        "Localized Drift\n(In-Mem Surprise)",
        "Localized Drift\n(Disk JSONL)",
        "Drift + Shift\n(In-Mem Surprise)",
        "Recurring States\n(Multi-Anchor)",
        "High-Entropy Shock\n(Static)",
        "High-Entropy Shock\n(Adaptive Retire)",
    ]
    cmps = [
        hw1["localized_regime_drift"]["comparisons"]["living_inmem_surprise_vs_incremental"],
        hw1["localized_regime_drift"]["comparisons"]["living_disk_jsonl_vs_incremental"],
        hw1["drift_and_regime_shift"]["comparisons"]["living_inmem_surprise_vs_incremental"],
        hw1["recurring_states"]["comparisons"]["multi_anchor_vs_incremental"],
        hw1["high_entropy_shock"]["comparisons"]["static_vs_incremental"],
        hw1["high_entropy_shock"]["comparisons"]["adaptive_retire_vs_incremental"],
    ]
    ops_v = [c["savings_abstract_ops_pct"] for c in cmps]
    proxy_v = [c["savings_modeled_proxy_j_pct"] for c in cmps]
    hw_j_v = [c["savings_hardware_energy_j_pct"] for c in cmps]
    hw_ins_v = [c["savings_instructions_pct"] for c in cmps]

    x = np.arange(len(labels))
    w = 0.20
    fig, ax = plt.subplots(figsize=(12.5, 5.4))
    ax.bar(x - 1.5 * w, ops_v, w, label="Abstract Ops Savings (%)", color="#2b6cb0")
    ax.bar(x - 0.5 * w, proxy_v, w, label="Modeled Proxy J Savings (%)", color="#805ad5")
    ax.bar(x + 0.5 * w, hw_j_v, w, label="Apple M3 Max Hardware Energy (ri_energy_nj %)", color="#2f855a")
    ax.bar(x + 1.5 * w, hw_ins_v, w, label="Retired Hardware Instructions (%)", color="#d69e2e")
    ax.axhline(0, color="black", linewidth=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Savings vs Strong Incremental Baseline (%)")
    ax.set_title("HW-1: Exact Unmodified Paper I 1,000-Node DAG — Abstract Ops vs Modeled Proxy vs Real M3 Max Hardware Energy")
    ax.legend(loc="lower left", fontsize=8.5)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "hw_energy_regime_comparison.png", dpi=160)
    plt.close(fig)

    # Figure 2: Side-by-side HW-2 Shock Crossover & HW-3 Compute Granularity Scaling
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.0, 5.0))

    ps = [r["shock_prob"] for r in hw2]
    ax1.plot(ps, [r["savings_abstract_ops_pct"] for r in hw2], "o-", color="#2b6cb0", label="Abstract Ops (%)")
    ax1.plot(ps, [r["savings_modeled_proxy_j_pct"] for r in hw2], "s--", color="#805ad5", label="Modeled Proxy J (%)")
    ax1.plot(ps, [r["savings_hardware_energy_j_pct"] for r in hw2], "D-", linewidth=2.2, color="#2f855a", label="Apple M3 Max HW Energy (%)")
    ax1.plot(ps, [r["savings_instructions_pct"] for r in hw2], "^:", color="#d69e2e", label="HW Retired Instructions (%)")
    ax1.axhline(0, color="black", linewidth=0.9)
    ax1.set_xlabel("Per-Step Shock Probability p")
    ax1.set_ylabel("Savings vs Strong Incremental (%)")
    ax1.set_title("HW-2: Shock-Rate Crossover (Ops vs Real Silicon Energy)")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    ks = [r["k_node_compute_iters"] for r in hw3]
    ax2.plot(ks, [r["vs_incremental"]["savings_abstract_ops_pct"] for r in hw3], "o--", color="#2b6cb0", label="Abstract Ops Savings (%)")
    ax2.plot(ks, [r["vs_incremental"]["savings_hardware_energy_j_pct"] for r in hw3], "D-", linewidth=2.2, color="#2f855a", label="Apple M3 Max HW Energy Savings (%)")
    ax2.plot(ks, [r["vs_incremental"]["savings_instructions_pct"] for r in hw3], "^-", color="#d69e2e", label="HW Retired Instructions Savings (%)")
    ax2.plot(ks, [r["vs_incremental"]["savings_wall_time_pct"] for r in hw3], "s:", color="#c53030", label="Wall-Clock Time Savings (%)")
    ax2.axhline(0, color="black", linewidth=0.9)
    ax2.set_xscale("log")
    ax2.set_xticks(ks)
    ax2.set_xticklabels([f"K={k}" for k in ks])
    ax2.set_xlabel("Pure Compute Intensity per DAG Node (K=1 is unmodified Paper I)")
    ax2.set_ylabel("Savings vs Strong Incremental (%)")
    ax2.set_title("HW-3: Hardware Energy vs Node Compute Granularity")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "hw_energy_crossover_and_granularity.png", dpi=160)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = get_machine_metadata()
    print(f"Hardware: {meta['cpu_brand']} ({meta['logical_cores']} cores, {meta['memory_gb']} GB) | {meta['platform']}")
    calib = run_linearity_calibration()
    print(
        f"Calibration linearity: 2x/1x={calib['ratio_2x_vs_1x_energy']}x, "
        f"4x/1x={calib['ratio_4x_vs_1x_energy']}x (inst 4x/1x={calib['ratio_4x_vs_1x_instructions']}x)"
    )

    energy_model = EnergyModel()
    with tempfile.TemporaryDirectory(prefix="ts_hw_energy_") as td:
        hw1 = run_exp_hw1(energy_model, Path(td))
    hw2 = run_exp_hw2_shock_sweep(energy_model)
    hw3 = run_exp_hw3_granularity(energy_model)

    generate_figures(hw1, hw2, hw3)

    payload = {
        "benchmark_id": "exp_hw01_paper01_apple_silicon",
        "version": "0.1.0",
        "machine": meta,
        "calibration": calib,
        "hw1_unmodified_paper01_regimes": hw1,
        "hw2_shock_rate_crossover": hw2,
        "hw3_node_granularity_scaling": hw3,
    }
    out_json = RESULTS_DIR / "hw_energy_summary.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved hardware benchmark summary -> {out_json}")


if __name__ == "__main__":
    main()
