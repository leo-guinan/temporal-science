"""Experiment 3 — Learning What to Observe (H2): Causal Sensor Environment & Adaptive Observer.

Constructs a simulated environment with:
  - Core causal sensors (always relevant to the target goal)
  - Redundant sensors (noisy linear combinations of core sensors — traps naive correlation filters)
  - Conditionally relevant / dormant sensors (silent in Phase 1, wake up mid-stream at t_shift,
    plus rare critical hazard pulses)
  - Irrelevant distractor sensors (pure noise / unrelated dynamics with varying acquisition cost)

Compares four observation policies under full cost accounting (acquisition + compute + learning + canary):
  1. ObserveAllPolicy (Baseline A)
  2. OracleRelevantPolicy (Ground-truth upper bound)
  3. StaticLearnedObserver (Learns once; exposes H2 failure condition under relevance drift)
  4. LivingAdaptiveObserver (Sparse cost-aware selection + RelevanceDriftCanary for re-adaptation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import math
import time

import numpy as np

from core.canary import CanaryState
from core.cost_ledger import CostCategory, CostLedger, EnergyModel, ResourceVector


@dataclass
class SensorSpec:
    """Metadata and ground-truth role of a sensor (roles are hidden from learners)."""

    sensor_id: int
    name: str
    role: str  # "core", "redundant", "conditional", "irrelevant"
    acquisition_cost_ops: float  # sensing/compute work per reading
    acquisition_joules: float  # physical sensing energy per reading (J)


@dataclass
class ObservationEnvConfig:
    num_core: int = 8
    num_redundant: int = 8
    num_conditional: int = 4
    num_irrelevant: int = 40
    num_steps: int = 5000
    shift_step: int = 2000
    rare_event_prob: float = 0.015
    noise_std: float = 0.05
    seed: int = 303


@dataclass
class ObservationDataset:
    specs: List[SensorSpec]
    X: np.ndarray  # shape (T, M)
    y: np.ndarray  # shape (T,)
    is_rare_event: np.ndarray  # shape (T,) bool
    true_active_sets: List[Set[int]]  # exact ground-truth relevant sensor IDs per step
    config: ObservationEnvConfig


def generate_observation_environment(cfg: ObservationEnvConfig) -> ObservationDataset:
    """Generate a deterministic multi-sensor stream with known causal structure & mid-stream drift."""
    rng = np.random.default_rng(cfg.seed)
    M = cfg.num_core + cfg.num_redundant + cfg.num_conditional + cfg.num_irrelevant
    T = cfg.num_steps

    specs: List[SensorSpec] = []
    idx = 0
    core_ids: List[int] = []
    redundant_ids: List[int] = []
    cond_ids: List[int] = []
    irrel_ids: List[int] = []

    for i in range(cfg.num_core):
        cost = float(rng.uniform(4.0, 10.0))
        specs.append(SensorSpec(idx, f"core_{i:02d}", "core", cost, cost * 2.5e-5))
        core_ids.append(idx)
        idx += 1
    for i in range(cfg.num_redundant):
        cost = float(rng.uniform(6.0, 14.0))
        specs.append(SensorSpec(idx, f"red_{i:02d}", "redundant", cost, cost * 2.5e-5))
        redundant_ids.append(idx)
        idx += 1
    for i in range(cfg.num_conditional):
        cost = float(rng.uniform(5.0, 11.0))
        specs.append(SensorSpec(idx, f"cond_{i:02d}", "conditional", cost, cost * 2.5e-5))
        cond_ids.append(idx)
        idx += 1
    for i in range(cfg.num_irrelevant):
        cost = float(rng.uniform(4.0, 16.0))
        specs.append(SensorSpec(idx, f"irrel_{i:02d}", "irrelevant", cost, cost * 2.5e-5))
        irrel_ids.append(idx)
        idx += 1

    X = np.zeros((T, M), dtype=np.float64)

    # 1. Core sensors: smooth AR(1) physical processes
    for cid in core_ids:
        v = 0.0
        phi = rng.uniform(0.65, 0.88)
        for t in range(T):
            v = phi * v + rng.normal(0.0, 0.45)
            X[t, cid] = v

    # 2. Redundant sensors: noisy linear combinations of core sensors
    for i, rid in enumerate(redundant_ids):
        p1 = core_ids[i % len(core_ids)]
        p2 = core_ids[(i + 1) % len(core_ids)]
        X[:, rid] = 0.7 * X[:, p1] + 0.3 * X[:, p2] + rng.normal(0.0, 0.08, size=T)

    # 3. Conditional sensors: dormant (~0 noise) before shift_step; wake up after shift_step!
    # Also inject occasional rare hazard spikes in the last conditional sensor even after warmup.
    is_rare = np.zeros(T, dtype=bool)
    for k, cid in enumerate(cond_ids):
        # Dormant baseline
        X[: cfg.shift_step, cid] = rng.normal(0.0, 0.01, size=cfg.shift_step)
        # Active post-shift AR(1) process
        v = 0.0
        for t in range(cfg.shift_step, T):
            v = 0.75 * v + rng.normal(0.0, 0.65)
            X[t, cid] = v

    # Inject rare critical events on cond_ids[-1] during [shift_step // 2, shift_step)
    if cond_ids:
        rare_cid = cond_ids[-1]
        for t in range(max(300, cfg.shift_step // 2), cfg.shift_step):
            if rng.random() < cfg.rare_event_prob:
                X[t, rare_cid] = rng.choice([-2.8, 2.8])
                is_rare[t] = True

    # 4. Irrelevant sensors: independent AR(1) distractors
    for iid in irrel_ids:
        v = 0.0
        phi = rng.uniform(0.3, 0.9)
        for t in range(T):
            v = phi * v + rng.normal(0.0, 0.6)
            X[t, iid] = v

    # True goal function y_t = w_core . X_core + w_cond . X_cond + noise
    w_core = rng.uniform(0.6, 1.4, size=len(core_ids)) * rng.choice([-1.0, 1.0], size=len(core_ids))
    w_cond = rng.uniform(0.9, 1.6, size=len(cond_ids)) * rng.choice([-1.0, 1.0], size=len(cond_ids))

    y = np.zeros(T, dtype=np.float64)
    y += X[:, core_ids] @ w_core
    y += X[:, cond_ids] @ w_cond
    y += rng.normal(0.0, cfg.noise_std, size=T)

    # Ground-truth active set per timestep
    base_set = set(core_ids)
    post_set = set(core_ids) | set(cond_ids)
    true_active: List[Set[int]] = []
    for t in range(T):
        if t >= cfg.shift_step:
            true_active.append(post_set)
        elif is_rare[t] and cond_ids:
            true_active.append(base_set | {cond_ids[-1]})
        else:
            true_active.append(base_set)

    return ObservationDataset(
        specs=specs,
        X=X,
        y=y,
        is_rare_event=is_rare,
        true_active_sets=true_active,
        config=cfg,
    )


def fit_cost_aware_omp(
    X_win: np.ndarray,
    y_win: np.ndarray,
    sensor_costs: np.ndarray,
    bic_cost_weight: float = 0.08,
    max_features: int = 24,
) -> Tuple[List[int], np.ndarray, float, int]:
    """Forward-backward stepwise OMP with BIC + sensing-cost penalty.

    Naturally eliminates both irrelevant distractors AND redundant noisy copies of core
    sensors because each added sensor must beat the BIC + acquisition-cost threshold,
    and backward pruning removes any early proxy superseded by true causal parents.

    Returns: (selected_indices, weights_with_intercept, residual_std, learn_ops)
    """
    n, m = X_win.shape
    learn_ops = n * m
    # Standardize columns for numerically stable correlation scoring
    means = X_win.mean(axis=0)
    stds = X_win.std(axis=0)
    active_cols = np.where(stds > 1e-4)[0]

    selected: List[int] = []
    best_score = float("inf")
    best_coef = np.array([float(y_win.mean())])
    best_resid_std = float(y_win.std())

    def eval_subset(cols: List[int]) -> Tuple[np.ndarray, float, float]:
        if not cols:
            A = np.ones((n, 1))
        else:
            A = np.column_stack([np.ones(n), X_win[:, cols]])
        coef, _, _, _ = np.linalg.lstsq(A, y_win, rcond=None)
        resid = y_win - A @ coef
        mse = max(1e-12, float(np.mean(resid * resid)))
        cost_pen = float(np.sum(sensor_costs[cols])) if cols else 0.0
        # BIC + sensing cost penalty
        score = n * math.log(mse) + len(cols) * math.log(n) * 1.5 + bic_cost_weight * cost_pen
        return coef, math.sqrt(mse), score

    best_coef, best_resid_std, best_score = eval_subset([])
    current_resid = y_win - best_coef[0]

    for _ in range(min(max_features, len(active_cols))):
        # Score remaining candidates by absolute correlation with current residual
        best_cand = None
        best_gain = -1.0
        r_norm = float(np.linalg.norm(current_resid))
        if r_norm < 1e-9:
            break
        for j in active_cols:
            if j in selected:
                continue
            learn_ops += n
            col = (X_win[:, j] - means[j]) / stds[j]
            corr = abs(float(np.dot(col, current_resid))) / (math.sqrt(n) * r_norm)
            gain = corr / (1.0 + 0.015 * sensor_costs[j])
            if gain > best_gain:
                best_gain = gain
                best_cand = int(j)

        if best_cand is None or best_gain < 0.03:
            break

        cand_subset = selected + [best_cand]
        coef, r_std, score = eval_subset(cand_subset)
        learn_ops += n * (len(cand_subset) + 1) ** 2

        if score < best_score - 1.5:
            selected = cand_subset
            best_coef = coef
            best_resid_std = r_std
            best_score = score
            A = np.column_stack([np.ones(n), X_win[:, selected]])
            current_resid = y_win - A @ best_coef
        else:
            break

    # Backward pruning pass: drop any redundant proxy whose removal improves BIC+cost score
    improved = True
    while improved and len(selected) > 1:
        improved = False
        for idx_drop in range(len(selected)):
            trial = selected[:idx_drop] + selected[idx_drop + 1 :]
            coef, r_std, score = eval_subset(trial)
            learn_ops += n * (len(trial) + 1) ** 2
            if score < best_score:
                selected = trial
                best_coef = coef
                best_resid_std = r_std
                best_score = score
                improved = True
                break

    return selected, best_coef, best_resid_std, learn_ops


@dataclass
class ObserverRunResult:
    policy_name: str
    ledger: CostLedger
    preds: np.ndarray
    selected_counts: List[int]
    safety_violations: int
    mae: float
    mse: float
    pre_shift_mse: float
    post_shift_mse: float
    adaptation_latency_steps: Optional[int]
    final_selected_sensors: List[int]
    total_observation_joules: float
    canary_triggers: List[Dict[str, Any]] = field(default_factory=list)


def run_observation_policy(
    dataset: ObservationDataset,
    mode: str,  # "observe_all", "oracle_relevant", "static_learned", "living_adaptive"
    warmup_steps: int = 250,
    safety_error_threshold: float = 0.50,
    sentinel_probes_per_step: int = 1,
    reid_window: int = 110,
    energy_model: Optional[EnergyModel] = None,
) -> ObserverRunResult:
    """Execute one observation policy across the full dataset with complete cost accounting."""
    em = energy_model or EnergyModel()
    X, y = dataset.X, dataset.y
    T, M = X.shape
    sensor_ops = np.array([s.acquisition_cost_ops for s in dataset.specs], dtype=np.float64)
    sensor_joules = np.array([s.acquisition_joules for s in dataset.specs], dtype=np.float64)

    ledger = CostLedger(system_name=mode, algorithm_version=f"exp03_{mode}_v1", energy_model=em)
    preds = np.zeros(T, dtype=np.float64)
    selected_counts: List[int] = []
    canary_triggers: List[Dict[str, Any]] = []

    selected: List[int] = list(range(M))
    coef: np.ndarray = np.zeros(M + 1, dtype=np.float64)
    resid_std: float = 0.25

    # Baseline distribution stats for omitted sensors (used by sentinel probe)
    omitted_mean = np.zeros(M, dtype=np.float64)
    omitted_std = np.ones(M, dtype=np.float64)
    sentinel_cursor = 0

    # Drift canary state (CUSUM on prediction residuals)
    cusum_pos = 0.0
    reid_remaining = 0
    reid_buffer_X: List[np.ndarray] = []
    reid_buffer_y: List[float] = []
    total_obs_joules = 0.0

    # For observe_all / oracle_relevant, fit ridge/OLS online after warmup cleanly
    oracle_fitted_pre = False
    oracle_fitted_post = False

    for t in range(T):
        t0 = time.perf_counter()
        c0 = time.process_time()

        learn_cost = ResourceVector()
        guard_cost = ResourceVector()
        reconfig_cost = ResourceVector()
        canaries_safe = 0
        canaries_unsafe = 0
        canaries_unknown = 0

        # Determine which sensors are acquired at step t
        if mode == "observe_all":
            acquired = list(range(M))
            if t == warmup_steps:
                tl0 = time.perf_counter()
                cl0 = time.process_time()
                A = np.column_stack([np.ones(warmup_steps), X[:warmup_steps]])
                coef, _, _, _ = np.linalg.lstsq(A, y[:warmup_steps], rcond=None)
                selected = list(range(M))
                learn_cost = ResourceVector(
                    steps=warmup_steps * M * 2,
                    time_s=time.perf_counter() - tl0,
                    joules=em.estimate_joules(time.process_time() - cl0),
                )
            elif t == dataset.config.shift_step + reid_window:
                # Allow observe_all to refit after shift too for a fair full-sensing baseline
                tl0 = time.perf_counter()
                cl0 = time.process_time()
                w0 = dataset.config.shift_step
                A = np.column_stack([np.ones(reid_window), X[w0:t]])
                coef, _, _, _ = np.linalg.lstsq(A, y[w0:t], rcond=None)
                learn_cost = ResourceVector(
                    steps=reid_window * M * 2,
                    time_s=time.perf_counter() - tl0,
                    joules=em.estimate_joules(time.process_time() - cl0),
                )

        elif mode == "oracle_relevant":
            true_s = sorted(dataset.true_active_sets[t])
            acquired = true_s
            if t == warmup_steps and not oracle_fitted_pre:
                selected = sorted(dataset.true_active_sets[t])
                A = np.column_stack([np.ones(warmup_steps), X[:warmup_steps, selected]])
                coef, _, _, _ = np.linalg.lstsq(A, y[:warmup_steps], rcond=None)
                oracle_fitted_pre = True
            elif t == dataset.config.shift_step + reid_window and not oracle_fitted_post:
                selected = sorted(dataset.true_active_sets[t])
                w0 = dataset.config.shift_step
                A = np.column_stack([np.ones(reid_window), X[w0:t, selected]])
                coef, _, _, _ = np.linalg.lstsq(A, y[w0:t], rcond=None)
                oracle_fitted_post = True

        elif mode == "static_learned":
            if t < warmup_steps:
                acquired = list(range(M))
            else:
                if t == warmup_steps:
                    tl0 = time.perf_counter()
                    cl0 = time.process_time()
                    selected, coef, resid_std, l_ops = fit_cost_aware_omp(
                        X[:warmup_steps], y[:warmup_steps], sensor_ops
                    )
                    learn_cost = ResourceVector(
                        steps=l_ops,
                        time_s=time.perf_counter() - tl0,
                        joules=em.estimate_joules(time.process_time() - cl0),
                    )
                acquired = selected

        elif mode == "living_adaptive":
            if t < warmup_steps:
                acquired = list(range(M))
            elif t == warmup_steps:
                acquired = list(range(M))
                tl0 = time.perf_counter()
                cl0 = time.process_time()
                selected, coef, resid_std, l_ops = fit_cost_aware_omp(
                    X[:warmup_steps], y[:warmup_steps], sensor_ops
                )
                omitted_mean = X[:warmup_steps].mean(axis=0)
                omitted_std = np.maximum(0.015, X[:warmup_steps].std(axis=0))
                learn_cost = ResourceVector(
                    steps=l_ops + warmup_steps * M,
                    time_s=time.perf_counter() - tl0,
                    joules=em.estimate_joules(time.process_time() - cl0),
                )
            elif reid_remaining > 0:
                # Re-identification burst: acquire all sensors to re-discover newly relevant ones
                acquired = list(range(M))
                reid_buffer_X.append(X[t])
                reid_buffer_y.append(float(y[t]))
                reid_remaining -= 1
                if reid_remaining == 0:
                    tl0 = time.perf_counter()
                    cl0 = time.process_time()
                    Xw = np.vstack(reid_buffer_X)
                    yw = np.array(reid_buffer_y)
                    # Include recent window if helpful, prioritizing post-shift buffer
                    new_sel, new_coef, new_std, l_ops = fit_cost_aware_omp(Xw, yw, sensor_ops)
                    selected = new_sel
                    coef = new_coef
                    resid_std = new_std
                    omitted_mean = Xw.mean(axis=0)
                    omitted_std = np.maximum(0.015, Xw.std(axis=0))
                    reid_buffer_X.clear()
                    reid_buffer_y.clear()
                    cusum_pos = 0.0
                    learn_cost = ResourceVector(
                        steps=l_ops,
                        time_s=time.perf_counter() - tl0,
                        joules=em.estimate_joules(time.process_time() - cl0),
                    )
                    reconfig_cost = ResourceVector(steps=len(selected) + 1)
            else:
                # Selective sensing + low-cost round-robin sentinel probe on omitted sensors
                omitted = [j for j in range(M) if j not in selected]
                probed: List[int] = []
                sentinel_triggered = False
                g_ops = 0
                g_joules = 0.0
                if omitted and sentinel_probes_per_step > 0:
                    for _ in range(min(sentinel_probes_per_step, len(omitted))):
                        sid = omitted[sentinel_cursor % len(omitted)]
                        sentinel_cursor += 1
                        probed.append(sid)
                        g_ops += int(round(sensor_ops[sid])) + 2
                        g_joules += float(sensor_joules[sid])
                        z = abs(X[t, sid] - omitted_mean[sid]) / omitted_std[sid]
                        if z > 8.0:
                            sentinel_triggered = True
                            canary_triggers.append(
                                {
                                    "timestep": t,
                                    "source": "sentinel_distribution_shift",
                                    "sensor_id": sid,
                                    "sensor_name": dataset.specs[sid].name,
                                    "z_score": round(float(z), 2),
                                }
                            )
                acquired = selected  # sentinel cost is accounted in GUARDING so no double count
                if sentinel_triggered:
                    canaries_unsafe += 1
                    reid_remaining = reid_window
                    reid_buffer_X.clear()
                    reid_buffer_y.clear()
                guard_cost = ResourceVector(steps=g_ops, joules=g_joules)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Prediction using current selected subset
        if t < warmup_steps:
            pred = float(y[t])  # warmup observation phase
            pred_ops = len(acquired)
        else:
            if selected and len(coef) == len(selected) + 1:
                pred = float(coef[0] + np.dot(coef[1:], X[t, selected]))
                pred_ops = len(selected) * 2
            else:
                pred = float(coef[0]) if len(coef) > 0 else 0.0
                pred_ops = 1

        preds[t] = pred

        # Post-prediction residual surprise canary (for living_adaptive during selective mode)
        if mode == "living_adaptive" and t > warmup_steps and reid_remaining == 0:
            err = abs(pred - float(y[t]))
            # Standardized CUSUM drift detector over prediction residuals
            k_slack = max(0.15, 2.5 * resid_std)
            cusum_pos = max(0.0, cusum_pos + (err - k_slack))
            guard_cost.steps += 2
            if cusum_pos > max(1.2, 6.0 * resid_std):
                canaries_unsafe += 1
                reid_remaining = reid_window
                reid_buffer_X.clear()
                reid_buffer_y.clear()
                cusum_pos = 0.0
                canary_triggers.append(
                    {
                        "timestep": t,
                        "source": "residual_cusum_surprise",
                        "abs_error": round(err, 4),
                        "threshold": round(max(1.2, 6.0 * resid_std), 4),
                    }
                )
            elif canaries_unsafe == 0:
                canaries_safe += 1

        # Acquisition + compute costs (honest full accounting)
        acq_ops = int(round(float(np.sum(sensor_ops[acquired])))) if acquired else 0
        acq_joules = float(np.sum(sensor_joules[acquired])) if acquired else 0.0
        total_obs_joules += acq_joules + guard_cost.joules

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        exec_cost = ResourceVector(
            steps=acq_ops + pred_ops,
            time_s=elapsed,
            joules=acq_joules + em.estimate_joules(cpu_elapsed, memory_bytes=len(acquired) * 16),
            memory_bytes=len(acquired) * 16,
        )

        # Count total sensors read this step (including sentinel probes for honest count)
        n_read = len(acquired) + (sentinel_probes_per_step if (mode == "living_adaptive" and t > warmup_steps and reid_remaining == 0) else 0)
        selected_counts.append(min(M, n_read))

        ledger.record_step(
            timestep=t,
            total_nodes=M,
            visited_nodes=min(M, n_read),
            costs={
                CostCategory.EXECUTION: exec_cost,
                CostCategory.LEARNING: learn_cost,
                CostCategory.GUARDING: guard_cost,
                CostCategory.RECONFIGURATION: reconfig_cost,
            },
            output_value=pred,
            canaries_safe=canaries_safe,
            canaries_unsafe=canaries_unsafe,
            canaries_unknown=canaries_unknown,
        )

    # Evaluate accuracy pre-shift and post-shift (excluding warmup)
    eval_slice = slice(warmup_steps + 1, T)
    errs = np.abs(preds[eval_slice] - y[eval_slice])
    sq_errs = (preds[eval_slice] - y[eval_slice]) ** 2
    mae = float(np.mean(errs))
    mse = float(np.mean(sq_errs))
    safety_violations = int(np.sum(errs > safety_error_threshold))

    pre_sl = slice(warmup_steps + 1, dataset.config.shift_step)
    post_sl = slice(dataset.config.shift_step, T)
    pre_mse = float(np.mean((preds[pre_sl] - y[pre_sl]) ** 2))
    post_mse = float(np.mean((preds[post_sl] - y[post_sl]) ** 2))

    # Adaptation latency: steps after shift_step until rolling 20-step MAE drops below safety_error_threshold / 2
    adaptation_latency: Optional[int] = None
    post_errs = np.abs(preds[dataset.config.shift_step :] - y[dataset.config.shift_step :])
    win = 20
    for k in range(win, len(post_errs)):
        if float(np.mean(post_errs[k - win : k])) < (safety_error_threshold * 0.5):
            adaptation_latency = k
            break

    return ObserverRunResult(
        policy_name=mode,
        ledger=ledger,
        preds=preds,
        selected_counts=selected_counts,
        safety_violations=safety_violations,
        mae=mae,
        mse=mse,
        pre_shift_mse=pre_mse,
        post_shift_mse=post_mse,
        adaptation_latency_steps=adaptation_latency,
        final_selected_sensors=list(selected),
        total_observation_joules=total_obs_joules,
        canary_triggers=canary_triggers,
    )
