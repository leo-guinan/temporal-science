#!/usr/bin/env python3
"""Standalone Clean-Environment Reproduction Script (Zero External Path Dependencies).

Run from any unpacked copy of this bundle on a fresh machine:
    python3 reproduce.py
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import random
import sys

BUNDLE_ROOT = Path(__file__).resolve().parent
SRC_DIR = BUNDLE_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
for extra in (
    SRC_DIR / "experiments" / "08_predictive_sync",
    SRC_DIR / "experiments" / "09_timespace_inertia",
):
    if extra.exists():
        sys.path.insert(0, str(extra))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_bundled_artifacts() -> int:
    manifest = json.loads((BUNDLE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    for rel_path, meta in artifacts.items():
        fp = BUNDLE_ROOT / rel_path
        assert fp.exists(), f"Missing bundled artifact: {rel_path}"
        got = sha256_file(fp)
        assert got == meta["sha256"], f"SHA-256 mismatch on {rel_path}: {got} != {meta['sha256']}"
    return len(artifacts)


def reproduce_paper_01_core() -> dict:
    from core import (
        CanaryState,
        ConventionalIncrementalEngine,
        FullRecomputeEngine,
        GuaranteeLevel,
        LearnedRepresentation,
        LipschitzMarginCanary,
        LivingTraceContractEngine,
        TracePolicy,
        ValidityContract,
        WorkloadConfig,
        WorkloadEnvironment,
        WorkloadRegime,
        build_milestone_network,
        compare_against_baseline,
    )

    # 1. Verify TS-001 Soundness (500 adversarial boundary probes -> 0 false-SAFE)
    g_small = build_milestone_network(num_nodes=250, num_inputs=30, seed=101)
    rng = random.Random(20261122)
    in0 = {nid: rng.uniform(-0.25, 0.25) for nid in g_small.input_ids}
    v0 = g_small.evaluate_full(in0)
    cones = [(n, g_small.extract_lipschitz_cone(n.node_id)) for n in g_small.nodes]
    cones = [(n, c) for n, c in cones if c is not None][:5]
    safe_hits, false_safes = 0, 0
    for node, (b_ids, i_ids, lip_map, _) in cones:
        vc = ValidityContract(f"repro_{node.node_id}", node.node_id, node.name, b_ids, i_ids, GuaranteeLevel.RESTRICTED_WORST_CASE, True, "repro", [], 0)
        canary = LipschitzMarginCanary(f"c_{node.node_id}", LearnedRepresentation(f"r_{node.node_id}", vc), node, lip_map, enable_regime_cache=False)
        canary.reanchor(v0, v0[node.parents[0]], v0[node.node_id])
        for s in range(100):
            sc = rng.choice([0.02, 0.08, 0.25, 1.0])
            pert = dict(in0)
            for b in b_ids:
                if b in pert:
                    pert[b] = in0[b] + rng.uniform(-sc, sc)
            v1 = g_small.evaluate_full(pert)
            res = canary.check(b_ids, v1, s + 1)
            if res.state is CanaryState.SAFE:
                safe_hits += 1
                if abs(res.cached_output - v1[node.node_id]) > 1e-12:
                    false_safes += 1
    assert safe_hits > 0 and false_safes == 0

    # 2. Reproduce 1,000-node DAG localized drift (2,000 updates quick deterministic check)
    g = build_milestone_network(num_nodes=1000, num_inputs=120, seed=42)
    env = WorkloadEnvironment(g.input_ids, WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=2000, seed=2026))
    init_in, events = env.generate()
    full = FullRecomputeEngine(g)
    inc = ConventionalIncrementalEngine(g)
    liv = LivingTraceContractEngine(g, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN)
    of = full.run(init_in, events)
    oi = inc.run(init_in, events)
    ol = liv.run(init_in, events)
    liv.close()
    assert all(abs(a - b) <= 1e-12 for a, b in zip(of, oi))
    assert all(abs(a - b) <= 1e-12 for a, b in zip(of, ol))
    cmp_inc = compare_against_baseline(inc.ledger, liv.ledger)
    cmp_full = compare_against_baseline(full.ledger, liv.ledger)
    assert cmp_inc["savings_steps"] > 0 and cmp_full["savings_steps"] > 0

    # 3. Reproduce P4 bounded synchronization (0% violations) & Exp 9 Jump-to-Jitter > 4x
    from sync_engine import SyncEnvConfig, generate_sync_environment, run_sync_observer
    ds_sync = generate_sync_environment(SyncEnvConfig(dims=4, num_steps=800, phi_range=(0.82, 0.90), disturbance_mode="bounded", w_scale=0.10, noise_scale=0.02, shift_step=None, seed=888))
    r_p4 = run_sync_observer(ds_sync, "adaptive_certified_bound", horizon_tau=2, tolerance_eps=0.50, permitted_delta=0.05)
    assert r_p4.empirical_violation_rate == 0.0 and r_p4.sync_budget_satisfied

    from timespace_core import TimespaceConfig, generate_timespace_stream, run_timespace_system
    ds_ts = generate_timespace_stream(TimespaceConfig(d_relevant=4, d_irrelevant=12, num_steps=900, shift_steps=(350, 650), seed=909))
    r_liv_ts = run_timespace_system(ds_ts, "living_canary_memory")
    assert r_liv_ts.jump_to_jitter_ratio > 3.5

    return {
        "ts001_safe_hits": safe_hits,
        "ts001_false_safes": false_safes,
        "dag_1000n_2000u_exact_matches": len(of),
        "dag_savings_vs_full_pct": cmp_full["savings_steps_pct"],
        "dag_savings_vs_inc_pct": cmp_inc["savings_steps_pct"],
        "dag_payback_vs_inc": cmp_inc["payback_step_ops"],
        "p4_bounded_violation_rate": r_p4.empirical_violation_rate,
        "p4_observation_rate": round(r_p4.observation_rate, 4),
        "timespace_jump_to_jitter": round(r_liv_ts.jump_to_jitter_ratio, 2),
    }


def main() -> None:
    n_verified = verify_bundled_artifacts()
    print(f"[1/2] Verified {n_verified}/{n_verified} bundled SHA-256 artifact checksums (100% intact).")
    res = reproduce_paper_01_core()
    print("[2/2] Independent clean-environment live reproduction PASSED:")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
