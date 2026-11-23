"""Experiment 2 — The Computational Canary (Disturbance Frequency & Monitor Sweep).

Varies disturbance shock probability from 0% to 50% and compares:
  - Conventional Incremental (no contract guards)
  - Sound Event-Driven Lipschitz-Margin Canaries (SAFE / UNSAFE, 0 missed invalidations)
  - Periodically Sampled Canaries (SAFE / UNSAFE / UNKNOWN, quantified error rate)
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
    PeriodicCanaryEngine,
    TracePolicy,
    WorkloadConfig,
    WorkloadEnvironment,
    WorkloadRegime,
    build_milestone_network,
    compare_against_baseline,
)


def main() -> None:
    out_dir = ROOT / "results" / "exp02_canaries"
    out_dir.mkdir(parents=True, exist_ok=True)

    energy = EnergyModel()
    graph = build_milestone_network(num_nodes=1000, num_inputs=120, seed=42)
    shock_probs = [0.0, 0.02, 0.05, 0.15, 0.35, 0.60]
    sweep = []

    print("Experiment 2 — Canary Cost & Failure Boundary vs Shock Frequency (1,000 nodes, 3,000 updates)")
    print("-" * 100)
    print(
        f"{'Shock p':>7} {'Inc Ops':>9} {'Sound Ops':>10} {'Sound vs Inc':>13} "
        f"{'SAFE/UNSAFE':>13} {'P10 Ops':>9} {'P10 Err%':>9}"
    )
    print("-" * 100)

    for sp in shock_probs:
        env = WorkloadEnvironment(
            graph.input_ids,
            WorkloadConfig(
                regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT,
                num_updates=3000,
                seed=202 + int(sp * 1000),
                shock_probability=sp,
            ),
        )
        init_inputs, events = env.generate()

        inc = ConventionalIncrementalEngine(graph, energy_model=energy)
        sound = LivingTraceContractEngine(
            graph,
            energy_model=energy,
            warmup_steps=100,
            trace_policy=TracePolicy.SURPRISE_DRIVEN,
        )
        p10 = PeriodicCanaryEngine(graph, energy_model=energy, warmup_steps=100, audit_period=10)

        out_inc = inc.run(init_inputs, events)
        out_sound = sound.run(init_inputs, events)
        out_p10 = p10.run(init_inputs, events)
        sound.close()

        sound_err = sum(1 for a, b in zip(out_inc, out_sound) if abs(a - b) > 1e-12)
        p10_err = sum(1 for a, b in zip(out_inc, out_p10) if abs(a - b) > 1e-12)
        assert sound_err == 0, f"Sound canary violated exactness at shock_p={sp}!"

        cmp_inc = compare_against_baseline(inc.ledger, sound.ledger)
        s_sum = sound.ledger.summary()
        p_sum = p10.ledger.summary()
        p10_err_pct = 100.0 * p10_err / len(out_inc)

        sweep.append(
            {
                "shock_probability": sp,
                "incremental_ops": inc.ledger.total_cost.steps,
                "sound_living_ops": sound.ledger.total_cost.steps,
                "sound_vs_inc_pct": cmp_inc["savings_steps_pct"],
                "sound_safe": s_sum["total_canaries_safe"],
                "sound_unsafe": s_sum["total_canaries_unsafe"],
                "sound_errors": sound_err,
                "periodic_p10_ops": p10.ledger.total_cost.steps,
                "periodic_p10_unknown": p_sum["total_canaries_unknown"],
                "periodic_p10_error_pct": round(p10_err_pct, 3),
            }
        )
        print(
            f"{sp:>7.2f} {inc.ledger.total_cost.steps:>9,} {sound.ledger.total_cost.steps:>10,} "
            f"{cmp_inc['savings_steps_pct']:>+12.2f}% "
            f"{s_sum['total_canaries_safe']:>6}/{s_sum['total_canaries_unsafe']:<6} "
            f"{p10.ledger.total_cost.steps:>9,} {p10_err_pct:>8.2f}%"
        )

    (out_dir / "exp02_sweep.json").write_text(json.dumps(sweep, indent=2), encoding="utf-8")
    print(f"\nSaved to {out_dir / 'exp02_sweep.json'}")


if __name__ == "__main__":
    main()
