"""Unit and property tests for Living Computation core modules and benchmark engines."""

from __future__ import annotations

from pathlib import Path
import random

import pytest

from core import (
    CanaryState,
    ConventionalIncrementalEngine,
    CostCategory,
    DependencyGraph,
    FullRecomputeEngine,
    LipschitzMarginCanary,
    LivingTraceContractEngine,
    OpType,
    PeriodicCanaryEngine,
    TracePolicy,
    TraceStore,
    WorkloadConfig,
    WorkloadEnvironment,
    WorkloadRegime,
    build_milestone_network,
    compare_against_baseline,
)


def test_milestone_graph_structure() -> None:
    g = build_milestone_network(num_nodes=1000, num_inputs=120, seed=42)
    assert len(g) == 1000
    stats = g.graph_stats()
    assert stats["num_nodes"] == 1000
    assert stats["num_inputs"] == 120
    assert stats["is_dag"] is True
    assert stats["dag_depth"] >= 6
    # Verify strict topological ordering
    for node in g.nodes:
        for pid in node.parents:
            assert pid < node.node_id


@pytest.mark.parametrize(
    "regime",
    [
        WorkloadRegime.LOCALIZED_REGIME_DRIFT,
        WorkloadRegime.RECURRING_STATES,
        WorkloadRegime.DRIFT_AND_REGIME_SHIFT,
        WorkloadRegime.HIGH_ENTROPY_SHOCK,
    ],
)
def test_exact_output_equivalence_across_all_regimes(regime: WorkloadRegime) -> None:
    """Every sound engine must match FullRecomputeEngine identically across all updates."""
    g = build_milestone_network(num_nodes=400, num_inputs=48, seed=11)
    env = WorkloadEnvironment(
        g.input_ids,
        WorkloadConfig(regime=regime, num_updates=400, seed=99),
    )
    init_inputs, events = env.generate()

    full = FullRecomputeEngine(g)
    inc = ConventionalIncrementalEngine(g)
    living = LivingTraceContractEngine(g, warmup_steps=50, adaptive_retirement=False)
    living_retire = LivingTraceContractEngine(
        g, warmup_steps=50, adaptive_retirement=True, retire_min_checks=15, retire_min_hit_rate=0.4
    )

    out_full = full.run(init_inputs, events)
    out_inc = inc.run(init_inputs, events)
    out_living = living.run(init_inputs, events)
    out_living_retire = living_retire.run(init_inputs, events)

    assert len(out_full) == 401
    for t in range(len(out_full)):
        assert abs(out_inc[t] - out_full[t]) <= 1e-12, f"Incremental mismatch at t={t}"
        assert abs(out_living[t] - out_full[t]) <= 1e-12, f"Living mismatch at t={t} ({regime})"
        assert abs(out_living_retire[t] - out_full[t]) <= 1e-12, (
            f"Living(retire) mismatch at t={t} ({regime})"
        )

    # Ensure contracts were actually learned and triggered
    assert living.knowledge_ledger.summary()["num_contracts_learned"] > 0
    # Ensure cost accounting conservation holds identically
    for eng in (full, inc, living, living_retire):
        summed_steps = sum(v.steps for v in eng.ledger.totals_by_category.values())
        assert eng.ledger.total_cost.steps == summed_steps
        assert eng.ledger.total_cost.steps > 0


def test_lipschitz_margin_canary_fuzz_soundness() -> None:
    """Fuzz-test LipschitzMarginCanary with 2,000 random & adversarial perturbations: 0 false-SAFEs."""
    g = build_milestone_network(num_nodes=300, num_inputs=36, seed=7)
    rng = random.Random(12345)
    init_inputs = {nid: rng.uniform(-0.3, 0.3) for nid in g.input_ids}
    vals0 = g.evaluate_full(init_inputs)

    # Extract every contractible target in the graph
    cones = []
    for node in g.nodes:
        cone = g.extract_lipschitz_cone(node.node_id)
        if cone is not None:
            cones.append((node, cone))
    assert len(cones) > 0

    from core.contracts import GuaranteeLevel, LearnedRepresentation, ValidityContract

    false_safes = 0
    total_safes = 0
    for node, (boundary_ids, internal_ids, lip_map, _) in cones[:10]:
        vc = ValidityContract(
            contract_id=f"test_{node.node_id}",
            target_node_id=node.node_id,
            target_node_name=node.name,
            boundary_ids=boundary_ids,
            internal_ids=internal_ids,
            guarantee_level=GuaranteeLevel.RESTRICTED_WORST_CASE,
            sound=True,
            precondition_summary="test",
            assumptions=[],
            created_at_step=0,
        )
        rep = LearnedRepresentation(rep_id=f"r_{node.node_id}", contract=vc)
        canary = LipschitzMarginCanary(
            canary_id=f"c_{node.node_id}",
            representation=rep,
            target_node=node,
            lipschitz_by_boundary=lip_map,
            enable_regime_cache=False,
        )
        canary.reanchor(vals0, vals0[node.parents[0]], vals0[node.node_id])

        for step in range(200):
            # Mix small, medium, and near-boundary perturbations
            scale = rng.choice([0.01, 0.05, 0.2, 0.8, 2.0])
            pert = dict(init_inputs)
            for b in boundary_ids:
                if b in pert:
                    pert[b] = init_inputs[b] + rng.uniform(-scale, scale)
            vals_new = g.evaluate_full(pert)
            res = canary.check(boundary_ids, vals_new, timestep=step + 1)
            if res.state is CanaryState.SAFE:
                total_safes += 1
                if abs(res.cached_output - vals_new[node.node_id]) > 1e-12:
                    false_safes += 1

    assert total_safes > 0, "Expected at least some SAFE hits during fuzzing"
    assert false_safes == 0, f"Detected {false_safes} unsound false-SAFE canary events!"


def test_trace_jsonl_persistence_and_replay(tmp_path: Path) -> None:
    """Append-only JSONL traces must deterministically replay exact ground-truth outputs."""
    g = build_milestone_network(num_nodes=250, num_inputs=30, seed=5)
    env = WorkloadEnvironment(
        g.input_ids,
        WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=120, seed=5),
    )
    init_inputs, events = env.generate()
    trace_file = tmp_path / "trace.jsonl"

    living = LivingTraceContractEngine(
        g,
        warmup_steps=40,
        trace_policy=TracePolicy.RECONSTRUCTIBLE_DELTA,
        trace_path=trace_file,
    )
    living.run(init_inputs, events)
    living.close()

    assert trace_file.exists()
    loaded = list(TraceStore.iter_jsonl(trace_file))
    assert len(loaded) == 121
    replay = TraceStore.verify_deterministic_replay(g, loaded, sample_timesteps=[0, 25, 60, 120])
    assert replay["replay_exact"] is True
    assert replay["mismatches"] == 0
    # Verify trace recording overhead was honestly charged
    assert living.ledger.totals_by_category[CostCategory.TRACE_RECORDING].steps > 0
    assert living.ledger.totals_by_category[CostCategory.TRACE_RECORDING].communication_bytes > 0


def test_periodic_canary_exposes_unknown_and_missed_invalidations() -> None:
    """Periodic sampled monitors must report UNKNOWN states and measurable failure rates under shocks."""
    g = build_milestone_network(num_nodes=350, num_inputs=40, seed=19)
    env = WorkloadEnvironment(
        g.input_ids,
        WorkloadConfig(
            regime=WorkloadRegime.HIGH_ENTROPY_SHOCK,
            num_updates=250,
            seed=19,
        ),
    )
    init_inputs, events = env.generate()
    full = FullRecomputeEngine(g)
    periodic = PeriodicCanaryEngine(g, warmup_steps=40, audit_period=20)

    out_full = full.run(init_inputs, events)
    out_per = periodic.run(init_inputs, events)

    mismatches = sum(1 for a, b in zip(out_full, out_per) if abs(a - b) > 1e-9)
    summary = periodic.ledger.summary()
    assert summary["total_canaries_unknown"] > 0
    assert mismatches > 0, "Expected periodic sampling to miss some invalidations under shocks"


def test_living_beats_full_and_incremental_on_localized_regime() -> None:
    """Verify H1 & H3: Living engine achieves positive cumulative savings and finite payback."""
    g = build_milestone_network(num_nodes=600, num_inputs=72, seed=42)
    env = WorkloadEnvironment(
        g.input_ids,
        WorkloadConfig(
            regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT,
            num_updates=1200,
            seed=42,
        ),
    )
    init_inputs, events = env.generate()

    full = FullRecomputeEngine(g)
    inc = ConventionalIncrementalEngine(g)
    living = LivingTraceContractEngine(g, warmup_steps=100)

    out_f = full.run(init_inputs, events)
    out_i = inc.run(init_inputs, events)
    out_l = living.run(init_inputs, events)

    assert all(abs(a - b) <= 1e-12 for a, b in zip(out_f, out_l))
    cmp_full = compare_against_baseline(full.ledger, living.ledger)
    cmp_inc = compare_against_baseline(inc.ledger, living.ledger)

    assert cmp_full["savings_steps"] > 0
    assert cmp_full["payback_step_ops"] is not None
    assert cmp_inc["savings_steps"] > 0
    assert cmp_inc["payback_step_ops"] is not None
