"""Executable CRR verification test for Claim TS-001 against Living Computation reference code."""

from __future__ import annotations

from pathlib import Path
import random
import sys

LC_ROOT = Path(__file__).resolve().parents[5] / "living-computation"
if str(LC_ROOT) not in sys.path:
    sys.path.insert(0, str(LC_ROOT))

from core import (
    CanaryState,
    GuaranteeLevel,
    LearnedRepresentation,
    LipschitzMarginCanary,
    ValidityContract,
    build_milestone_network,
)


def test_ts001_lipschitz_margin_soundness() -> None:
    """Verify Claim TS-001: zero false-SAFE canary hits across 500 random boundary perturbations."""
    g = build_milestone_network(num_nodes=250, num_inputs=30, seed=101)
    rng = random.Random(20261122)
    init_inputs = {nid: rng.uniform(-0.25, 0.25) for nid in g.input_ids}
    vals0 = g.evaluate_full(init_inputs)

    cones = [(n, g.extract_lipschitz_cone(n.node_id)) for n in g.nodes]
    cones = [(n, c) for n, c in cones if c is not None][:5]
    assert len(cones) > 0

    safe_hits = 0
    false_safes = 0
    for node, (b_ids, i_ids, lip_map, _) in cones:
        vc = ValidityContract(
            contract_id=f"ts001_{node.node_id}",
            target_node_id=node.node_id,
            target_node_name=node.name,
            boundary_ids=b_ids,
            internal_ids=i_ids,
            guarantee_level=GuaranteeLevel.RESTRICTED_WORST_CASE,
            sound=True,
            precondition_summary="TS-001 check",
            assumptions=[],
            created_at_step=0,
        )
        rep = LearnedRepresentation(rep_id=f"rep_{node.node_id}", contract=vc)
        canary = LipschitzMarginCanary(
            canary_id=f"c_{node.node_id}",
            representation=rep,
            target_node=node,
            lipschitz_by_boundary=lip_map,
            enable_regime_cache=False,
        )
        canary.reanchor(vals0, vals0[node.parents[0]], vals0[node.node_id])

        for step in range(100):
            scale = rng.choice([0.02, 0.08, 0.25, 1.0])
            pert = dict(init_inputs)
            for b in b_ids:
                if b in pert:
                    pert[b] = init_inputs[b] + rng.uniform(-scale, scale)
            vals1 = g.evaluate_full(pert)
            res = canary.check(b_ids, vals1, timestep=step + 1)
            if res.state is CanaryState.SAFE:
                safe_hits += 1
                if abs(res.cached_output - vals1[node.node_id]) > 1e-12:
                    false_safes += 1

    assert safe_hits > 0
    assert false_safes == 0
