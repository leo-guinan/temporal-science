"""Experiment 1 — Computational Memory & Trace-Storage Policy Ablation.

Sweeps trace-storage policies (FULL_MATERIALIZED, RECONSTRUCTIBLE_DELTA, SURPRISE_DRIVEN)
and warmup lengths to measure exactly when historical trace instrumentation pays back
against full recomputation and conventional incremental computation (H1).
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    compare_against_baseline,
)


def main() -> None:
    out_dir = ROOT / "results" / "exp01_trace_reuse"
    out_dir.mkdir(parents=True, exist_ok=True)

    energy = EnergyModel()
    graph = build_milestone_network(num_nodes=1000, num_inputs=120, seed=42)
    env = WorkloadEnvironment(
        graph.input_ids,
        WorkloadConfig(
            regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT,
            num_updates=5000,
            seed=101,
        ),
    )
    init_inputs, events = env.generate()

    full = FullRecomputeEngine(graph, energy_model=energy)
    inc = ConventionalIncrementalEngine(graph, energy_model=energy)
    full.run(init_inputs, events)
    inc.run(init_inputs, events)

    results = {
        "full_recomputation": full.ledger.summary(),
        "conventional_incremental": inc.ledger.summary(),
        "ablations": [],
    }

    print("Experiment 1 — Trace-Storage Policy Ablation (1,000 nodes, 5,000 updates)")
    print("-" * 88)
    print(f"{'Policy':<24} {'Warmup':>6} {'Total Ops':>10} {'Trace Ops':>10} {'vs Inc Ops':>11} {'vs Inc J':>10} {'Payback':>8}")
    print("-" * 88)

    for policy in (
        TracePolicy.FULL_MATERIALIZED,
        TracePolicy.RECONSTRUCTIBLE_DELTA,
        TracePolicy.SURPRISE_DRIVEN,
    ):
        for warmup in (75, 150):
            eng = LivingTraceContractEngine(
                graph,
                energy_model=energy,
                warmup_steps=warmup,
                trace_policy=policy,
                name=f"living_{policy.value}_w{warmup}",
            )
            eng.run(init_inputs, events)
            eng.close()
            cmp_inc = compare_against_baseline(inc.ledger, eng.ledger)
            summary = eng.ledger.summary()
            trace_ops = summary["by_category"]["trace_recording"]["steps"]
            results["ablations"].append(
                {
                    "policy": policy.value,
                    "warmup_steps": warmup,
                    "summary": summary,
                    "vs_incremental": cmp_inc,
                }
            )
            print(
                f"{policy.value:<24} {warmup:>6} {summary['total_cost']['steps']:>10,} "
                f"{trace_ops:>10,} {cmp_inc['savings_steps_pct']:>+10.2f}% "
                f"{cmp_inc['savings_joules_pct']:>+9.2f}% {str(cmp_inc['payback_step_ops']):>8}"
            )

    (out_dir / "exp01_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to {out_dir / 'exp01_summary.json'}")


if __name__ == "__main__":
    main()
