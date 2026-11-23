"""Experiment 9 (v0.2) — Timespace Trajectories & Informational Inertia (LC-15, LC-16, LC-17, H9).

Compares five memory architectures on the identical evolving observation stream:
  1. stateless_short_window    : Reference baseline (sliding 25-step window; low inertia, high jitter)
  2. naive_infinite_memory     : Counterexample 1 (accumulates unbounded precision -> overconfident,
                                 sluggish adaptation after regime shifts)
  3. bloated_irrelevant_memory : Counterexample 2 (stores 36 irrelevant features -> huge memory_bytes
                                 and O(D^2) maintenance burden without predictive sufficiency)
  4. exponential_forgetting_rls: Conventional baseline (fixed forgetting factor lambda=0.96)
  5. living_canary_memory      : Mature sufficient memory + Surprise Canary selective precision retirement

Separately measures (LC-15, LC-16, LC-17):
  - Physical memory bytes vs predictive sufficiency vs maintenance ops
  - Hellinger metric D_H(q_{t-1}, q_t) in [0, 1] (bounded true metric in timespace)
  - KL information gain D_KL(q_t || q_{t-1}) in nats (tracked separately from D_H & compute ops)
  - Action flip rate (whether an observation actually changed the downstream decision)
  - Jump-to-Jitter ratio: mean timespace movement during true shifts / mean routine movement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import time

import numpy as np

from core.canary import CanaryState
from core.cost_ledger import CostCategory, CostLedger, EnergyModel, ResourceVector
from core.telemetry import ExtendedTelemetryLedger, TimespaceMovementRecord


@dataclass
class TimespaceConfig:
    d_relevant: int = 4
    d_irrelevant: int = 36
    num_steps: int = 1800
    shift_steps: Tuple[int, ...] = (600, 1200)
    obs_noise_std: float = 0.35
    prior_obs_count: int = 0  # optional pre-accumulated prior experience before t=0
    seed: int = 909


@dataclass
class TimespaceDataset:
    X_full: np.ndarray  # (T, d_rel + d_irr)
    y: np.ndarray  # (T,)
    theta_true: np.ndarray  # (T, d_rel)
    true_action: np.ndarray  # (T,) bool: (X_rel . theta_true >= 0)
    config: TimespaceConfig


def generate_timespace_stream(cfg: TimespaceConfig) -> TimespaceDataset:
    rng = np.random.default_rng(cfg.seed)
    T = cfg.num_steps
    d_tot = cfg.d_relevant + cfg.d_irrelevant
    X_full = rng.normal(0.0, 1.0, size=(T, d_tot))

    # Build piecewise-constant ground-truth regimes with clear structural shifts
    boundaries = [0] + list(cfg.shift_steps) + [T]
    theta_true = np.zeros((T, cfg.d_relevant), dtype=np.float64)
    prev_th: Optional[np.ndarray] = None
    for seg_idx in range(len(boundaries) - 1):
        a, b = boundaries[seg_idx], boundaries[seg_idx + 1]
        if prev_th is None:
            th = rng.uniform(0.6, 1.4, size=cfg.d_relevant) * rng.choice([-1.0, 1.0], size=cfg.d_relevant)
        else:
            # Flip signs and shift magnitudes so the regime shift is genuinely consequential
            th = -0.85 * prev_th + rng.normal(0.0, 0.55, size=cfg.d_relevant)
        theta_true[a:b] = th
        prev_th = th

    signal = np.sum(X_full[:, : cfg.d_relevant] * theta_true, axis=1)
    y = signal + rng.normal(0.0, cfg.obs_noise_std, size=T)
    true_action = signal >= 0.0

    return TimespaceDataset(
        X_full=X_full,
        y=y,
        theta_true=theta_true,
        true_action=true_action,
        config=cfg,
    )


def gaussian_hellinger_and_kl(
    mu0: np.ndarray, cov0: np.ndarray, mu1: np.ndarray, cov1: np.ndarray
) -> Tuple[float, float]:
    """Compute exact Hellinger metric D_H(q0, q1) in [0, 1] and KL divergence D_KL(q1 || q0) in nats.

    Hellinger is a bounded true metric (symmetric, triangle inequality, always finite);
    KL measures Bayesian information gain in nats from prior q0 to posterior q1.
    """
    d = len(mu0)
    # Regularize slightly for numerical stability
    eps = 1e-9 * np.eye(d)
    c0 = cov0 + eps
    c1 = cov1 + eps
    c_avg = 0.5 * (c0 + c1)
    diff = mu1 - mu0

    sign0, logdet0 = np.linalg.slogdet(c0)
    sign1, logdet1 = np.linalg.slogdet(c1)
    sign_a, logdet_a = np.linalg.slogdet(c_avg)

    # Bhattacharyya distance D_B -> Hellinger D_H = sqrt(1 - exp(-D_B))
    quad_avg = float(diff @ np.linalg.solve(c_avg, diff))
    d_b = 0.125 * quad_avg + 0.5 * (logdet_a - 0.5 * (logdet0 + logdet1))
    d_b = max(0.0, d_b)
    hellinger = math.sqrt(max(0.0, 1.0 - math.exp(-d_b)))

    # KL(q1 || q0) = 0.5 * (tr(c0^-1 c1) + diff^T c0^-1 diff - d + log(|c0|/|c1|))
    tr_term = float(np.trace(np.linalg.solve(c0, c1)))
    quad_0 = float(diff @ np.linalg.solve(c0, diff))
    kl = 0.5 * (tr_term + quad_0 - d + (logdet0 - logdet1))
    kl = max(0.0, kl)
    return hellinger, kl


@dataclass
class TimespaceRunResult:
    system_name: str
    ledger: CostLedger
    telemetry: ExtendedTelemetryLedger
    memory_bytes: int
    routine_mse: float
    post_shift_mse: float
    action_accuracy: float
    action_flip_rate: float
    mean_routine_hellinger: float
    mean_shift_hellinger: float
    jump_to_jitter_ratio: float
    mean_routine_kl_nats: float
    mean_shift_kl_nats: float
    shift_adaptation_steps: Optional[float]
    canary_resets: int
    hellinger_series: np.ndarray
    mse_series: np.ndarray

    def summary(self) -> Dict[str, Any]:
        return {
            "system": self.system_name,
            "memory_bytes": self.memory_bytes,
            "total_ops": self.ledger.total_cost.steps,
            "total_modeled_joules": round(self.ledger.total_cost.joules, 6),
            "routine_mse": round(self.routine_mse, 5),
            "post_shift_mse": round(self.post_shift_mse, 5),
            "action_accuracy": round(self.action_accuracy, 4),
            "action_flip_rate": round(self.action_flip_rate, 4),
            "mean_routine_hellinger": round(self.mean_routine_hellinger, 6),
            "mean_shift_hellinger": round(self.mean_shift_hellinger, 6),
            "jump_to_jitter_ratio": round(self.jump_to_jitter_ratio, 3),
            "mean_routine_kl_nats": round(self.mean_routine_kl_nats, 6),
            "mean_shift_kl_nats": round(self.mean_shift_kl_nats, 6),
            "mean_shift_adaptation_steps": (
                round(self.shift_adaptation_steps, 2)
                if self.shift_adaptation_steps is not None
                else None
            ),
            "canary_resets": self.canary_resets,
        }


def run_timespace_system(
    dataset: TimespaceDataset,
    mode: str,
    window_size: int = 25,
    forgetting_lambda: float = 0.96,
    prior_obs_override: Optional[int] = None,
    irrelevant_dims_override: Optional[int] = None,
    energy_model: Optional[EnergyModel] = None,
) -> TimespaceRunResult:
    """Run one memory architecture on `dataset` and record full timespace trajectory & inertia."""
    em = energy_model or EnergyModel()
    cfg = dataset.config
    T = cfg.num_steps
    sigma2 = cfg.obs_noise_std ** 2

    if mode == "bloated_irrelevant_memory":
        n_irr = irrelevant_dims_override if irrelevant_dims_override is not None else cfg.d_irrelevant
        d = cfg.d_relevant + min(n_irr, cfg.d_irrelevant)
        X = dataset.X_full[:, :d]
    else:
        d = cfg.d_relevant
        X = dataset.X_full[:, :d]
    y = dataset.y

    ledger = CostLedger(system_name=mode, algorithm_version=f"exp09_v02_{mode}", energy_model=em)
    telemetry = ExtendedTelemetryLedger(experiment_version="v0.2")

    # Initialize Bayesian Gaussian belief N(mu, cov)
    prior_n = prior_obs_override if prior_obs_override is not None else cfg.prior_obs_count
    mu = np.zeros(d, dtype=np.float64)
    # If pre-accumulated prior_n > 0, initialize near regime-1 with high precision
    if prior_n > 0:
        mu[: cfg.d_relevant] = dataset.theta_true[0]
        cov = (sigma2 / max(1.0, float(prior_n))) * np.eye(d)
    else:
        cov = 2.0 * np.eye(d)

    # Sliding window storage for stateless_short_window
    win_X: List[np.ndarray] = []
    win_y: List[float] = []

    # Residual EWMA/CUSUM surprise canary for living_canary_memory
    cusum_nis = 0.0
    canary_resets = 0
    prev_action: Optional[bool] = None

    hellinger_series = np.zeros(T, dtype=np.float64)
    kl_series = np.zeros(T, dtype=np.float64)
    sq_err_series = np.zeros(T, dtype=np.float64)
    action_correct = np.zeros(T, dtype=bool)
    action_flipped = np.zeros(T, dtype=bool)

    # Physical memory bytes of retained state (strictly separated from sufficiency!)
    if mode == "stateless_short_window":
        mem_bytes = window_size * (d + 1) * 8 + d * d * 8
    else:
        mem_bytes = (d + d * d) * 8 + (64 if mode == "living_canary_memory" else 0)

    for t in range(T):
        t0 = time.perf_counter()
        c0 = time.process_time()

        x_t = X[t]
        y_t = float(y[t])

        # 1. Predict before observing y_t
        y_hat = float(np.dot(x_t, mu))
        pred_var = float(x_t @ cov @ x_t) + sigma2
        err = y_t - y_hat
        sq_err_series[t] = err * err
        act = y_hat >= 0.0
        action_correct[t] = (act == bool(dataset.true_action[t]))
        flipped = (prev_action is not None) and (act != prev_action)
        action_flipped[t] = flipped
        prev_action = act

        mu_prev = mu.copy()
        cov_prev = cov.copy()

        exec_ops = d * 2
        guard_ops = 0
        reconfig_ops = 0
        c_safe = 0
        c_unsafe = 0

        # 2. Update internal representation K_t -> K_{t+1}
        if mode == "stateless_short_window":
            win_X.append(x_t)
            win_y.append(y_t)
            if len(win_X) > window_size:
                win_X.pop(0)
                win_y.pop(0)
            Aw = np.vstack(win_X)
            yw = np.array(win_y)
            prec = (Aw.T @ Aw) / sigma2 + 0.5 * np.eye(d)
            cov = np.linalg.inv(prec)
            mu = cov @ ((Aw.T @ yw) / sigma2)
            exec_ops += len(win_X) * d * d + d ** 3

        elif mode in ("naive_infinite_memory", "bloated_irrelevant_memory"):
            # Exact Bayesian RLS update (rank-1 Sherman-Morrison): O(d^2)
            Px = cov @ x_t
            denom = sigma2 + float(np.dot(x_t, Px))
            k_gain = Px / denom
            mu = mu + k_gain * err
            cov = cov - np.outer(k_gain, Px)
            cov = 0.5 * (cov + cov.T)
            exec_ops += 3 * d * d + 2 * d

        elif mode == "exponential_forgetting_rls":
            # Conventional RLS with fixed forgetting factor lambda
            Px = cov @ x_t
            denom = forgetting_lambda * sigma2 + float(np.dot(x_t, Px))
            k_gain = Px / denom
            mu = mu + k_gain * err
            cov = (cov - np.outer(k_gain, Px)) / forgetting_lambda
            cov = 0.5 * (cov + cov.T)
            exec_ops += 3 * d * d + 3 * d

        elif mode == "living_canary_memory":
            # Surprise canary: standardized squared prediction error (NIS)
            nis = (err * err) / max(1e-9, pred_var)
            cusum_nis = max(0.0, cusum_nis + (nis - 2.6))
            guard_ops += d * 2 + 4

            if cusum_nis > 12.0:
                # Genuine regime shift detected! Selectively retire stale prior precision
                c_unsafe = 1
                canary_resets += 1
                cov = 1.5 * np.eye(d)
                cusum_nis = 0.0
                reconfig_ops += d * d
            else:
                c_safe = 1

            # Standard Bayesian RLS update on (possibly refreshed) precision
            Px = cov @ x_t
            denom = sigma2 + float(np.dot(x_t, Px))
            k_gain = Px / denom
            mu = mu + k_gain * err
            cov = cov - np.outer(k_gain, Px)
            cov = 0.5 * (cov + cov.T)
            exec_ops += 3 * d * d + 2 * d
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # 3. Measure timespace movement (Hellinger metric) & KL information gain separately
        d_h, kl_nats = gaussian_hellinger_and_kl(mu_prev, cov_prev, mu, cov)
        hellinger_series[t] = d_h
        kl_series[t] = kl_nats

        telemetry.timespace_moves.append(
            TimespaceMovementRecord(
                timestep=t,
                divergence_metric="hellinger",
                divergence_value=d_h,
                information_gain_nats=kl_nats,
                update_ops=exec_ops + guard_ops + reconfig_ops,
                action_changed=flipped,
            )
        )

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        tot_ops = max(1, exec_ops + guard_ops + reconfig_ops)

        def _vec(ops: int) -> ResourceVector:
            f = ops / tot_ops
            return ResourceVector(
                steps=ops,
                time_s=elapsed * f,
                joules=em.estimate_joules(cpu_elapsed * f, memory_bytes=mem_bytes),
                memory_bytes=mem_bytes,
            )

        ledger.record_step(
            timestep=t,
            total_nodes=d,
            visited_nodes=d,
            costs={
                CostCategory.EXECUTION: _vec(exec_ops),
                CostCategory.GUARDING: _vec(guard_ops),
                CostCategory.RECONFIGURATION: _vec(reconfig_ops),
            },
            output_value=y_hat,
            active_memory_bytes=mem_bytes,
            canaries_safe=c_safe,
            canaries_unsafe=c_unsafe,
        )

    # Partition routine vs post-shift windows (30 steps after each shift = adaptation window)
    shift_mask = np.zeros(T, dtype=bool)
    for s_step in cfg.shift_steps:
        shift_mask[s_step : min(T, s_step + 30)] = True
    routine_mask = np.zeros(T, dtype=bool)
    routine_mask[150:] = ~shift_mask[150:]

    routine_mse = float(np.mean(sq_err_series[routine_mask])) if np.any(routine_mask) else 0.0
    post_shift_mse = float(np.mean(sq_err_series[shift_mask])) if np.any(shift_mask) else 0.0
    mean_r_h = float(np.mean(hellinger_series[routine_mask])) if np.any(routine_mask) else 0.0
    mean_s_h = float(np.mean(hellinger_series[shift_mask])) if np.any(shift_mask) else 0.0
    mean_r_kl = float(np.mean(kl_series[routine_mask])) if np.any(routine_mask) else 0.0
    mean_s_kl = float(np.mean(kl_series[shift_mask])) if np.any(shift_mask) else 0.0
    j2j = mean_s_h / max(1e-9, mean_r_h)

    # Compute mean steps after each shift until rolling 15-step MSE drops below 2.5 * sigma^2
    thresh_mse = 2.5 * sigma2
    adapt_times: List[int] = []
    for s_step in cfg.shift_steps:
        end = min(T, s_step + 400)
        seg = sq_err_series[s_step:end]
        found = None
        for k in range(15, len(seg)):
            if float(np.mean(seg[k - 15 : k])) <= thresh_mse:
                found = k
                break
        if found is not None:
            adapt_times.append(found)
    mean_adapt = float(np.mean(adapt_times)) if len(adapt_times) == len(cfg.shift_steps) else None

    return TimespaceRunResult(
        system_name=mode,
        ledger=ledger,
        telemetry=telemetry,
        memory_bytes=mem_bytes,
        routine_mse=routine_mse,
        post_shift_mse=post_shift_mse,
        action_accuracy=float(np.mean(action_correct[150:])),
        action_flip_rate=float(np.mean(action_flipped[150:])),
        mean_routine_hellinger=mean_r_h,
        mean_shift_hellinger=mean_s_h,
        jump_to_jitter_ratio=j2j,
        mean_routine_kl_nats=mean_r_kl,
        mean_shift_kl_nats=mean_s_kl,
        shift_adaptation_steps=mean_adapt,
        canary_resets=canary_resets,
        hellinger_series=hellinger_series,
        mse_series=sq_err_series,
    )
