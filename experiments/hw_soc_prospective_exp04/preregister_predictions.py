#!/usr/bin/env python3
"""PREREGISTRATION SCRIPT for exp_hw04 (MUST RUN & SEAL BEFORE EXECUTING BENCHMARK!).

Produces two strictly prospective predictions for the `_pytest` incremental static
typechecker across q in {0.00, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00} (20 edits,
single-pass 71-module cold start) and seals `results/preregistered_predictions.json`
with an immutable SHA-256 fingerprint BEFORE a single full benchmark trial runs:

  1. Model 1 (`ZERO_SHOT_EXP03`):
     Uses ZERO hardware measurements from `_pytest` or `incremental_typechecker.py`!
     Extracts frozen per-KiB execution energy & canary validation energy strictly from
     `exp_hw03_summary.json` and multiplies by `_pytest`'s static pre-run source KiB.

  2. Model 2 (`PRIMITIVE_5TERM_PROSPECTIVE`):
     Implements the 5-component physical energy equation:
         E_reuse = E_dispatch + E_validation + E_execution + E_memory + E_maintenance
     Measures ONLY a tiny isolated 8-module micro-probe of the new typechecker's
     primitive per-KiB execution, dispatch, canary validation, and memory-rail ratio
     (ZERO runs on the full 71-module corpus or any churn rate q!), then predicts the
     entire 7-point churn curve and failure boundary q* prospectively.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import ast
import gc
import hashlib
import json
import statistics
import sys

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
HW01_DIR = TS_ROOT / "experiments" / "hw_energy_paper01"
HW02_DIR = TS_ROOT / "experiments" / "hw_soc_paper02"
HW03_SUMMARY = TS_ROOT / "experiments" / "hw_soc_breakeven_exp03" / "results" / "exp_hw03_summary.json"
for p in (HW01_DIR, HW02_DIR, EXP_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from telemetry_soc_macos import (
    IOReportEnergyReader,
    delta_dual,
    get_soc_machine_metadata,
    get_system_context,
    snapshot_dual,
)
from incremental_typechecker import (
    build_pytest_import_graph,
    discover_pytest_corpus,
    extract_type_interface,
    generate_pytest_edit_stream,
    transitive_importers,
    typecheck_single_module,
)

RESULTS_DIR = EXP_DIR / "results"
TARGET_QS = (0.00, 0.10, 0.25, 0.50, 0.75, 0.90, 1.00)
N_BLOCKS = 10
NUM_EDITS = 20


def _compute_static_workload_expectations(
    sources: Dict[str, str], rev: Dict[str, set]
) -> Dict[str, Any]:
    """Compute purely static graph/KiB expectations for the exact seeds exp_hw04 will run (ZERO execution)."""
    total_corpus_kib = sum(len(s.encode("utf-8")) for s in sources.values()) / 1024.0
    per_q: Dict[str, Dict[str, float]] = {}

    for q in TARGET_QS:
        inc_kibs, can_kibs, av_kibs, av_mods = [], [], [], []
        for b in range(N_BLOCKS):
            seed = 7000 + int(q * 100) * 100 + b * 29
            eds = generate_pytest_edit_stream(sources, rev, NUM_EDITS, q, seed)
            cur_kib = {m: len(s.encode("utf-8")) / 1024.0 for m, s in sources.items()}
            inc_k = total_corpus_kib  # single-pass cold start
            can_k = total_corpus_kib
            av_k = 0.0
            av_m = 0
            for ed in eds:
                cur_kib[ed.module_name] = len(ed.new_source.encode("utf-8")) / 1024.0
                ds = transitive_importers(rev, ed.module_name)
                ds_kib = sum(cur_kib[m] for m in ds)
                inc_k += cur_kib[ed.module_name] + ds_kib
                if ed.is_api_breaking:
                    can_k += cur_kib[ed.module_name] + ds_kib
                else:
                    can_k += cur_kib[ed.module_name]
                    av_k += ds_kib
                    av_m += len(ds)
            inc_kibs.append(inc_k)
            can_kibs.append(can_k)
            av_kibs.append(av_k)
            av_mods.append(av_m)

        per_q[f"{q:.2f}"] = {
            "q": q,
            "cold_start_kib": round(total_corpus_kib, 2),
            "expected_inc_total_kib": round(statistics.mean(inc_kibs), 2),
            "expected_canary_total_kib": round(statistics.mean(can_kibs), 2),
            "expected_avoided_kib": round(statistics.mean(av_kibs), 2),
            "expected_avoided_modules": round(statistics.mean(av_mods), 2),
        }

    return {
        "num_modules": len(sources),
        "total_corpus_kib": round(total_corpus_kib, 2),
        "per_q": per_q,
    }


def _extract_frozen_exp03_constants() -> Dict[str, float]:
    """Read frozen physical J/KiB constants strictly from completed exp_hw03_summary.json."""
    d = json.loads(HW03_SUMMARY.read_text(encoding="utf-8"))
    corpus = d["part_b_real_stdlib_ast"]["corpus"]
    mean_kib_per_mod = corpus["total_source_kib"] / corpus["num_modules"]
    m_proc = d["part_b_transfer_model"]["proc_cpu_energy_j"]
    m_soc = d["part_b_transfer_model"]["soc_package_j"]
    return {
        "exp03_mean_kib_per_module": round(mean_kib_per_mod, 4),
        "exp03_proc_j_per_kib": round(m_proc["e_per_avoided_module_j"] / mean_kib_per_mod, 6),
        "exp03_soc_j_per_kib": round(m_soc["e_per_avoided_module_j"] / mean_kib_per_mod, 6),
        "exp03_proc_overhead_per_edit_j": round(m_proc["e_canary_overhead_j"] / 20.0, 6),
        "exp03_soc_overhead_per_edit_j": round(m_soc["e_canary_overhead_j"] / 20.0, 6),
    }


def _run_5term_primitive_microprobe(
    ior: IOReportEnergyReader, sources: Dict[str, str], order: List[str]
) -> Dict[str, float]:
    """Measure ONLY 5 isolated primitive physical costs on an 8-module micro-slice (ZERO churn runs!)."""
    # Pick 8 representative medium-sized modules (spread across corpus size distribution)
    by_size = sorted(order, key=lambda m: len(sources[m]))
    probe_mods = [by_size[int(i * (len(by_size) - 1) / 7)] for i in range(8)]
    probe_kib = sum(len(sources[m].encode("utf-8")) for m in probe_mods) / 1024.0
    known = set(sources.keys())

    # Warm-up
    for m in probe_mods:
        typecheck_single_module(m, sources[m], known, {}, {})

    # 1. Execution + Memory primitive: repeat 8-module typecheck 12x (~1.0s clean window, N=3)
    exec_proc, exec_soc, exec_soc_cpu, exec_soc_mem = [], [], [], []
    reps = 12
    for _ in range(3):
        gc.collect()
        s0 = snapshot_dual(ior)
        for _ in range(reps):
            for m in probe_mods:
                typecheck_single_module(m, sources[m], known, {}, {})
        s1 = snapshot_dual(ior)
        p, s = delta_dual(ior, s0, s1)
        assert s is not None
        exec_proc.append(p.hardware_energy_j / (reps * probe_kib))
        exec_soc.append(s.soc_package_j / (reps * probe_kib))
        exec_soc_cpu.append(s.soc_cpu_j / (reps * probe_kib))
        exec_soc_mem.append(s.soc_memory_j / (reps * probe_kib))

    # 2. Validation + Dispatch + Maintenance primitive: SHA-256 public type-interface extraction + dict update
    trees = [ast.parse(sources[m]) for m in probe_mods]
    val_reps = 120
    val_proc, val_soc = [], []
    for _ in range(3):
        gc.collect()
        s0 = snapshot_dual(ior)
        cache: Dict[str, str] = {}
        for _ in range(val_reps):
            for m, t in zip(probe_mods, trees):
                h, _ = extract_type_interface(t)
                _ = (cache.get(m) == h)
                cache[m] = h
        s1 = snapshot_dual(ior)
        p, s = delta_dual(ior, s0, s1)
        assert s is not None
        val_proc.append(p.hardware_energy_j / (val_reps * len(probe_mods)))
        val_soc.append(s.soc_package_j / (val_reps * len(probe_mods)))

    e_exec_proc_per_kib = statistics.mean(exec_proc)
    e_exec_soc_per_kib = statistics.mean(exec_soc)
    e_soc_cpu_per_kib = statistics.mean(exec_soc_cpu)
    e_soc_mem_per_kib = statistics.mean(exec_soc_mem)
    e_val_maint_proc_per_edit = statistics.mean(val_proc)
    e_val_maint_soc_per_edit = statistics.mean(val_soc)

    # Note: In certified_type_canary, extract_type_interface is ALREADY executed inside typecheck_single_module,
    # so the incremental overhead per edit above strong_incremental_dag is ONLY dispatch + hash compare +
    # downstream-list maintenance (bounded above by the measured validation+maintenance microprobe).
    return {
        "probe_modules": probe_mods,
        "probe_total_kib": round(probe_kib, 2),
        "e_exec_proc_j_per_kib": round(e_exec_proc_per_kib, 6),
        "e_exec_soc_package_j_per_kib": round(e_exec_soc_per_kib, 6),
        "e_exec_soc_cpu_j_per_kib": round(e_soc_cpu_per_kib, 6),
        "e_exec_soc_memory_j_per_kib": round(e_soc_mem_per_kib, 6),
        "e_dispatch_val_maint_proc_j_per_edit": round(e_val_maint_proc_per_edit, 6),
        "e_dispatch_val_maint_soc_j_per_edit": round(e_val_maint_soc_per_edit, 6),
    }


def _build_predictions(
    static_exp: Dict[str, Any],
    proc_j_per_kib: float,
    soc_j_per_kib: float,
    proc_ov_per_edit: float,
    soc_ov_per_edit: float,
) -> Dict[str, Any]:
    preds: Dict[str, Any] = {}
    for qkey, st in static_exp["per_q"].items():
        inc_kib = st["expected_inc_total_kib"]
        av_kib = st["expected_avoided_kib"]
        ov_proc = NUM_EDITS * proc_ov_per_edit
        ov_soc = NUM_EDITS * soc_ov_per_edit

        e_inc_proc = inc_kib * proc_j_per_kib
        delta_proc = av_kib * proc_j_per_kib - ov_proc
        pct_proc = 100.0 * delta_proc / e_inc_proc if e_inc_proc > 0 else 0.0

        e_inc_soc = inc_kib * soc_j_per_kib
        delta_soc = av_kib * soc_j_per_kib - ov_soc
        pct_soc = 100.0 * delta_soc / e_inc_soc if e_inc_soc > 0 else 0.0

        preds[qkey] = {
            "q": st["q"],
            "pred_inc_proc_j": round(e_inc_proc, 4),
            "pred_delta_proc_j": round(delta_proc, 4),
            "pred_pct_proc": round(pct_proc, 2),
            "pred_inc_soc_j": round(e_inc_soc, 4),
            "pred_delta_soc_j": round(delta_soc, 4),
            "pred_pct_soc": round(pct_soc, 2),
        }

    # Predicted break-even API-breaking rate q* where av_kib(q*) * e_kib = NUM_EDITS * e_ov
    av_kib_q0 = static_exp["per_q"]["0.00"]["expected_avoided_kib"]
    q_star_proc = 1.0 - (NUM_EDITS * proc_ov_per_edit) / max(av_kib_q0 * proc_j_per_kib, 1e-12)
    q_star_soc = 1.0 - (NUM_EDITS * soc_ov_per_edit) / max(av_kib_q0 * soc_j_per_kib, 1e-12)
    return {
        "q_star_pred_proc": round(min(1.0, max(0.0, q_star_proc)), 4),
        "q_star_pred_soc": round(min(1.0, max(0.0, q_star_soc)), 4),
        "by_q": preds,
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sources, root = discover_pytest_corpus()
    deps, rev, order = build_pytest_import_graph(sources)
    static_exp = _compute_static_workload_expectations(sources, rev)
    exp03_const = _extract_frozen_exp03_constants()

    ior = IOReportEnergyReader()
    prim = _run_5term_primitive_microprobe(ior, sources, order)

    # Model 1: Zero-Shot Pure Transfer from exp_hw03 (ZERO measurements from _pytest!)
    model1_zero_shot = _build_predictions(
        static_exp,
        exp03_const["exp03_proc_j_per_kib"],
        exp03_const["exp03_soc_j_per_kib"],
        exp03_const["exp03_proc_overhead_per_edit_j"],
        exp03_const["exp03_soc_overhead_per_edit_j"],
    )

    # Model 2: 5-Component Primitive Prospective Model (calibrated ONLY on 8-module isolated micro-probe!)
    model2_5term = _build_predictions(
        static_exp,
        prim["e_exec_proc_j_per_kib"],
        prim["e_exec_soc_package_j_per_kib"],
        prim["e_dispatch_val_maint_proc_j_per_edit"],
        prim["e_dispatch_val_maint_soc_j_per_edit"],
    )

    core_doc = {
        "preregistration_id": "exp_hw04_prospective_pytest_typechecker_v1",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "machine": get_soc_machine_metadata(),
        "system_context_at_preregistration": get_system_context(),
        "target_repository": {
            "name": "_pytest (pytest 9.0.2)",
            "root": str(root),
            "num_modules": len(sources),
            "num_import_edges": sum(len(v) for v in deps.values()),
            "total_source_kib": static_exp["total_corpus_kib"],
        },
        "planned_protocol": {
            "n_blocks": N_BLOCKS,
            "num_edits_per_block": NUM_EDITS,
            "target_qs": list(TARGET_QS),
            "cold_start_passes": 1,
        },
        "static_workload_expectations": static_exp,
        "frozen_exp03_constants": exp03_const,
        "primitive_5term_microprobe": prim,
        "model1_zero_shot_exp03_predictions": model1_zero_shot,
        "model2_5term_primitive_predictions": model2_5term,
    }
    seal = hashlib.sha256(json.dumps(core_doc, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    sealed = {"preregistration_sha256": seal, **core_doc}

    out_path = RESULTS_DIR / "preregistered_predictions.json"
    out_path.write_text(json.dumps(sealed, indent=2), encoding="utf-8")
    print(f"SEALED PREREGISTERED PREDICTIONS -> {out_path}")
    print(f"SHA-256 SEAL: {seal}")
    print(f"exp_hw03 frozen J/KiB: proc={exp03_const['exp03_proc_j_per_kib']}, SoC={exp03_const['exp03_soc_j_per_kib']}")
    print(f"5-term microprobe J/KiB: proc={prim['e_exec_proc_j_per_kib']}, SoC={prim['e_exec_soc_package_j_per_kib']} (CPU={prim['e_exec_soc_cpu_j_per_kib']}, Mem={prim['e_exec_soc_memory_j_per_kib']})")
    print("Model 1 (Zero-Shot exp03) vs Model 2 (5-Term Primitive) Prospective Predictions:")
    for qk in [f"{q:.2f}" for q in TARGET_QS]:
        p1 = model1_zero_shot["by_q"][qk]
        p2 = model2_5term["by_q"][qk]
        print(
            f"  q={qk}: M1_proc={p1['pred_pct_proc']:+6.2f}% ({p1['pred_delta_proc_j']:+6.2f}J), "
            f"M2_proc={p2['pred_pct_proc']:+6.2f}% ({p2['pred_delta_proc_j']:+6.2f}J) | "
            f"M2_SoC={p2['pred_pct_soc']:+6.2f}% ({p2['pred_delta_soc_j']:+6.2f}J)"
        )


if __name__ == "__main__":
    main()
