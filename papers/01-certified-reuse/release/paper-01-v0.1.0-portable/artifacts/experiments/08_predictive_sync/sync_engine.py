"""Experiment 8 (v0.2) — Predictive Synchronization (LC-18, H8, P4).

Implements the predictive synchronization benchmark:
    Pr[ d(R_hat(t + tau), R(t + tau)) <= eps(tau) ] >= 1 - delta

Compares four observers on identical evolving multi-dimensional environments:
  1. continuous_kalman            : Observes every step (gold-standard accuracy baseline)
  2. periodic_kalman              : Observes every P steps (swept over P)
  3. adaptive_kalman_uncertainty  : Kalman predictive-variance adaptive observer + NIS shift canary
  4. adaptive_certified_bound     : P4 certified worst-case error-radius observer + assumption canary

Strict synchronization discipline:
  - `sync_budget_satisfied` is True iff empirical violation rate <= permitted `delta`.
  - When assumptions break (mid-stream regime shift), adaptive observers explicitly enter
    `CanaryState.UNKNOWN` and escalate to continuous observation until re-calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import time

import numpy as np
from scipy.stats import norm

from core.canary import CanaryState
from core.contracts import GuaranteeLevel
from core.cost_ledger import CostCategory, CostLedger, EnergyModel, ResourceVector
from core.telemetry import ExtendedTelemetryLedger, PredictionSyncRecord


@dataclass
class SyncEnvConfig:
    dims: int = 6
    num_steps: int = 3000
    phi_range: Tuple[float, float] = (0.75, 0.90)
    disturbance_mode: str = "bounded"  # "bounded" (Uniform[-W, W]) or "gaussian" (N(0, sigma_w^2))
    w_scale: float = 0.08  # W_max for bounded, sigma_w for gaussian
    noise_scale: float = 0.03  # eta_max for bounded, sigma_eta for gaussian
    shift_step: Optional[int] = 1500
    post_shift_w_multiplier: float = 2.0
    sensor_cost_ops: int = 40
    sensor_cost_joules: float = 8.0e-4
    seed: int = 808


@dataclass
class SyncDataset:
    R: np.ndarray  # true state (T, d)
    Z: np.ndarray  # noisy measurements (T, d)
    phi: np.ndarray  # AR(1) contraction coefficients (d,)
    w_true_series: np.ndarray  # true disturbance scale per step (T,)
    config: SyncEnvConfig


def generate_sync_environment(cfg: SyncEnvConfig) -> SyncDataset:
    rng = np.random.default_rng(cfg.seed)
    T, d = cfg.num_steps, cfg.dims
    phi = rng.uniform(cfg.phi_range[0], cfg.phi_range[1], size=d)
    R = np.zeros((T, d), dtype=np.float64)
    Z = np.zeros((T, d), dtype=np.float64)
    w_scale_t = np.full(T, cfg.w_scale, dtype=np.float64)
    if cfg.shift_step is not None and cfg.shift_step < T:
        w_scale_t[cfg.shift_step :] = cfg.w_scale * cfg.post_shift_w_multiplier

    R[0] = rng.normal(0.0, 0.25, size=d)
    for t in range(T):
        if t > 0:
            ws = w_scale_t[t]
            if cfg.disturbance_mode == "bounded":
                w = rng.uniform(-ws, ws, size=d)
            else:
                w = rng.normal(0.0, ws, size=d)
            R[t] = phi * R[t - 1] + w

        if cfg.disturbance_mode == "bounded":
            eta = rng.uniform(-cfg.noise_scale, cfg.noise_scale, size=d)
        else:
            eta = rng.normal(0.0, cfg.noise_scale, size=d)
        Z[t] = R[t] + eta

    return SyncDataset(R=R, Z=Z, phi=phi, w_true_series=w_scale_t, config=cfg)


@dataclass
class SyncRunResult:
    observer_name: str
    horizon_tau: int
    tolerance_eps: float
    permitted_delta: float
    ledger: CostLedger
    telemetry: ExtendedTelemetryLedger
    observation_rate: float
    empirical_violation_rate: float
    sync_budget_satisfied: bool
    pre_shift_violation_rate: float
    post_shift_violation_rate: float
    mean_error: float
    max_error: float
    calibration_ece: float  # Expected calibration gap between predicted & realized coverage
    detection_latency_steps: Optional[int]
    unknown_steps: int
    errors_series: np.ndarray
    observed_mask: np.ndarray

    def summary(self) -> Dict[str, Any]:
        return {
            "observer": self.observer_name,
            "horizon_tau": self.horizon_tau,
            "tolerance_eps": self.tolerance_eps,
            "permitted_delta": self.permitted_delta,
            "observation_rate": round(self.observation_rate, 4),
            "empirical_violation_rate": round(self.empirical_violation_rate, 5),
            "sync_budget_satisfied": self.sync_budget_satisfied,
            "pre_shift_violation_rate": round(self.pre_shift_violation_rate, 5),
            "post_shift_violation_rate": round(self.post_shift_violation_rate, 5),
            "mean_error": round(self.mean_error, 5),
            "max_error": round(self.max_error, 5),
            "calibration_gap": round(self.calibration_ece, 5),
            "detection_latency_steps": self.detection_latency_steps,
            "unknown_steps": self.unknown_steps,
            "total_ops": self.ledger.total_cost.steps,
            "total_modeled_joules": round(self.ledger.total_cost.joules, 6),
            "by_category": {
                cat.value: vec.to_dict() for cat, vec in self.ledger.totals_by_category.items()
            },
        }


def _lookahead_geom(phi: np.ndarray, tau: int, power: int = 1) -> np.ndarray:
    """Compute sum_{j=0}^{tau-1} |phi|^(power * j) safely."""
    r = np.abs(phi) ** power
    out = np.zeros_like(r)
    for j in range(tau):
        out += r ** j
    return out


def run_sync_observer(
    dataset: SyncDataset,
    mode: str,  # "continuous_kalman", "periodic_kalman", "adaptive_kalman_uncertainty", "adaptive_certified_bound"
    horizon_tau: int = 2,
    tolerance_eps: float = 0.35,
    permitted_delta: float = 0.05,
    period: int = 4,
    warmup_steps: int = 120,
    max_blind_steps: int = 12,
    recalib_window: int = 40,
    energy_model: Optional[EnergyModel] = None,
) -> SyncRunResult:
    """Run one predictive synchronization observer over `dataset` with full cost & error-budget accounting."""
    em = energy_model or EnergyModel()
    cfg = dataset.config
    R, Z, phi = dataset.R, dataset.Z, dataset.phi
    T, d = R.shape
    eval_T = T - horizon_tau

    obs_name = f"{mode}_p{period}" if mode == "periodic_kalman" else mode
    ledger = CostLedger(system_name=obs_name, algorithm_version=f"exp08_v02_{obs_name}", energy_model=em)
    telemetry = ExtendedTelemetryLedger(experiment_version="v0.2")

    # Convert bounded uniform variance if needed: Var(Uniform[-a, a]) = a^2 / 3
    if cfg.disturbance_mode == "bounded":
        est_sigma_w2 = (cfg.w_scale ** 2) / 3.0
        est_sigma_eta2 = (cfg.noise_scale ** 2) / 3.0
        est_w_max = cfg.w_scale
        eta_max = cfg.noise_scale
    else:
        est_sigma_w2 = cfg.w_scale ** 2
        est_sigma_eta2 = cfg.noise_scale ** 2
        # For Gaussian, 3.5-sigma gives an empirical high-confidence radius (not worst-case!)
        est_w_max = 3.5 * cfg.w_scale
        eta_max = 3.5 * cfg.noise_scale

    # State estimate & Kalman variance
    x_hat = np.zeros(d, dtype=np.float64)
    P_var = np.full(d, est_sigma_eta2, dtype=np.float64)
    # Certified worst-case error radius (for P4)
    e_cert = np.full(d, eta_max, dtype=np.float64)

    phi_tau = phi ** horizon_tau
    geom1 = _lookahead_geom(phi, horizon_tau, power=1)
    geom2 = _lookahead_geom(phi, horizon_tau, power=2)

    errors = np.zeros(eval_T, dtype=np.float64)
    observed_mask = np.zeros(eval_T, dtype=bool)
    predicted_fail_probs = np.zeros(eval_T, dtype=np.float64)
    violations_bool = np.zeros(eval_T, dtype=bool)

    steps_since_obs = 0
    recalib_remaining = 0
    recalib_residuals: List[np.ndarray] = []
    first_shift_detect_step: Optional[int] = None
    unknown_steps = 0

    # Quantile for union bound across d dims: Pr[max_i |err_i| > eps] <= sum_i Pr[|err_i| > eps] <= delta
    per_dim_delta = max(1e-6, permitted_delta / (2.0 * d))
    z_crit = float(norm.ppf(1.0 - per_dim_delta))

    for t in range(eval_T):
        t0 = time.perf_counter()
        c0 = time.process_time()

        exec_ops = 0
        guard_ops = 0
        learn_ops = 0
        acquire = False
        canary_state = CanaryState.SAFE
        guarantee = GuaranteeLevel.EMPIRICAL

        # 1. Propagate prior from t-1 to t
        if t == 0:
            acquire = True
        else:
            x_hat = phi * x_hat
            P_var = (phi ** 2) * P_var + est_sigma_w2
            e_cert = np.abs(phi) * e_cert + est_w_max
            exec_ops += d * 3

            # Decide whether to acquire measurement at step t
            if mode == "continuous_kalman":
                acquire = True
                guarantee = GuaranteeLevel.DISTRIBUTIONAL
            elif mode == "periodic_kalman":
                acquire = (t % period == 0)
                guarantee = GuaranteeLevel.EMPIRICAL
                guard_ops += 1
            elif mode == "adaptive_kalman_uncertainty":
                guarantee = GuaranteeLevel.DISTRIBUTIONAL
                if t < warmup_steps or recalib_remaining > 0:
                    acquire = True
                    if recalib_remaining > 0:
                        canary_state = CanaryState.UNKNOWN
                else:
                    # Exact independent-Gaussian max-norm failure probability Pr[max_i |err_i| > eps]
                    lookahead_var = (phi_tau ** 2) * P_var + est_sigma_w2 * geom2
                    lookahead_std = np.sqrt(np.maximum(1e-12, lookahead_var))
                    in_tol = np.clip(2.0 * norm.cdf(tolerance_eps / lookahead_std) - 1.0, 0.0, 1.0)
                    pred_fail_p = 1.0 - float(np.prod(in_tol))
                    guard_ops += d * 4
                    if pred_fail_p > permitted_delta or steps_since_obs >= max_blind_steps:
                        acquire = True
                        canary_state = CanaryState.UNSAFE
                    else:
                        acquire = False
                        canary_state = CanaryState.SAFE
            elif mode == "adaptive_certified_bound":
                guarantee = (
                    GuaranteeLevel.RESTRICTED_WORST_CASE
                    if cfg.disturbance_mode == "bounded"
                    else GuaranteeLevel.DISTRIBUTIONAL
                )
                if t < warmup_steps or recalib_remaining > 0:
                    acquire = True
                    if recalib_remaining > 0:
                        canary_state = CanaryState.UNKNOWN
                else:
                    # P4 exact worst-case lookahead bound E_cert(t, tau)
                    E_cert = np.abs(phi_tau) * e_cert + est_w_max * geom1
                    guard_ops += d * 3
                    if float(np.max(E_cert)) > tolerance_eps or steps_since_obs >= max_blind_steps:
                        acquire = True
                        canary_state = CanaryState.UNSAFE
                    else:
                        acquire = False
                        canary_state = CanaryState.SAFE
            else:
                raise ValueError(f"Unknown observer mode: {mode}")

        # 2. If acquiring measurement z_t: pay acquisition cost, run shift canary, update state
        acq_ops = 0
        acq_joules = 0.0
        if acquire:
            observed_mask[t] = True
            z_t = Z[t]
            acq_ops = cfg.sensor_cost_ops
            acq_joules = cfg.sensor_cost_joules
            innov = z_t - x_hat

            # Shift / assumption-violation detection BEFORE updating x_hat (after warmup)
            if t >= warmup_steps and recalib_remaining == 0 and t > 0:
                if mode == "adaptive_kalman_uncertainty":
                    # Normalized Innovation Squared (NIS) check against chi-square-like bound
                    S_innov = P_var + est_sigma_eta2
                    nis = float(np.sum((innov ** 2) / np.maximum(1e-12, S_innov)))
                    guard_ops += d * 3
                    # For d=6, E[NIS]=6, std=sqrt(12)~3.46; threshold d + 4.5*sqrt(2d) catches shifts cleanly
                    if nis > (d + 4.5 * math.sqrt(2.0 * d)):
                        canary_state = CanaryState.UNKNOWN
                        recalib_remaining = recalib_window
                        recalib_residuals.clear()
                        if cfg.shift_step is not None and t >= cfg.shift_step and first_shift_detect_step is None:
                            first_shift_detect_step = t - cfg.shift_step
                elif mode == "adaptive_certified_bound":
                    # P4 falsification check: |z_t - x_hat| MUST be <= e_cert + eta_max if W_max held!
                    guard_ops += d * 2
                    if float(np.max(np.abs(innov))) > float(np.max(e_cert + eta_max)) * 1.001:
                        canary_state = CanaryState.UNKNOWN
                        recalib_remaining = recalib_window
                        recalib_residuals.clear()
                        if cfg.shift_step is not None and t >= cfg.shift_step and first_shift_detect_step is None:
                            first_shift_detect_step = t - cfg.shift_step

            # Kalman update (or direct reset for bounded P4)
            if mode == "adaptive_certified_bound" and cfg.disturbance_mode == "bounded":
                # Direct measurement reset strictly satisfies |x_hat - R_t| <= eta_max (P4 assumption 3)
                prev_z = x_hat.copy()
                x_hat = z_t.copy()
                e_cert = np.full(d, eta_max, dtype=np.float64)
                P_var = np.full(d, est_sigma_eta2, dtype=np.float64)
                exec_ops += d * 2
            else:
                K_gain = P_var / np.maximum(1e-12, P_var + est_sigma_eta2)
                x_hat = x_hat + K_gain * innov
                P_var = (1.0 - K_gain) * P_var
                e_cert = np.full(d, eta_max, dtype=np.float64)
                exec_ops += d * 4

            # Warmup or recalibration parameter estimation (strictly zero leakage!)
            if t > 0 and (t < warmup_steps or recalib_remaining > 0):
                # Estimate one-step innovation z_t - phi * z_{t-1}
                one_step_res = Z[t] - phi * Z[t - 1]
                recalib_residuals.append(one_step_res)
                if t == warmup_steps - 1:
                    arr = np.vstack(recalib_residuals)
                    learn_ops += arr.size * 3
                    emp_var = max(1e-6, float(np.mean(arr ** 2)) - (1.0 + float(np.mean(phi ** 2))) * est_sigma_eta2)
                    est_sigma_w2 = max(1e-6, emp_var)
                    if cfg.disturbance_mode == "bounded":
                        # Conservative empirical bound on W_max from warmup observations
                        est_w_max = max(0.01, float(np.max(np.abs(arr))) - (1.0 - 0.5) * eta_max)
                    else:
                        est_w_max = 3.5 * math.sqrt(est_sigma_w2)
                    recalib_residuals.clear()
                elif recalib_remaining > 0:
                    recalib_remaining -= 1
                    if recalib_remaining == 0 and recalib_residuals:
                        arr = np.vstack(recalib_residuals)
                        learn_ops += arr.size * 3
                        emp_var = max(1e-6, float(np.mean(arr ** 2)) - (1.0 + float(np.mean(phi ** 2))) * est_sigma_eta2)
                        est_sigma_w2 = max(1e-6, emp_var)
                        if cfg.disturbance_mode == "bounded":
                            est_w_max = max(est_w_max, float(np.max(np.abs(arr))))
                        else:
                            est_w_max = 3.5 * math.sqrt(est_sigma_w2)
                        recalib_residuals.clear()
                        e_cert = np.full(d, eta_max, dtype=np.float64)

            steps_since_obs = 0
        else:
            steps_since_obs += 1

        # 3. Produce tau-step lookahead prediction R_hat(t + tau) and evaluate against realized R(t + tau)
        r_hat_future = phi_tau * x_hat
        r_true_future = R[t + horizon_tau]
        err = float(np.max(np.abs(r_hat_future - r_true_future)))
        violated = err > tolerance_eps
        errors[t] = err
        violations_bool[t] = violated

        # Exact predicted max-norm failure probability under current Kalman uncertainty model
        cur_lookahead_var = (phi_tau ** 2) * P_var + est_sigma_w2 * geom2
        cur_std = np.sqrt(np.maximum(1e-12, cur_lookahead_var))
        cur_in_tol = np.clip(2.0 * norm.cdf(tolerance_eps / cur_std) - 1.0, 0.0, 1.0)
        predicted_fail_probs[t] = 1.0 - float(np.prod(cur_in_tol))

        if canary_state is CanaryState.UNKNOWN:
            unknown_steps += 1

        telemetry.add_prediction_sync(
            PredictionSyncRecord(
                timestep=t,
                horizon_tau=horizon_tau,
                tolerance_eps=tolerance_eps,
                permitted_delta=permitted_delta,
                predicted_value=float(r_hat_future[0]),
                realized_value=float(r_true_future[0]),
                error=err,
                violated_bound=violated,
                canary_state=canary_state.value,
                guarantee_type=guarantee.value,
            )
        )

        elapsed = time.perf_counter() - t0
        cpu_elapsed = time.process_time() - c0
        comp_j = em.estimate_joules(cpu_elapsed, memory_bytes=(exec_ops + guard_ops) * 8)

        ledger.record_step(
            timestep=t,
            total_nodes=d,
            visited_nodes=d if acquire else 0,
            costs={
                CostCategory.EXECUTION: ResourceVector(
                    steps=exec_ops + acq_ops,
                    time_s=elapsed,
                    joules=acq_joules + comp_j,
                    memory_bytes=(exec_ops + acq_ops) * 8,
                ),
                CostCategory.GUARDING: ResourceVector(steps=guard_ops),
                CostCategory.LEARNING: ResourceVector(steps=learn_ops),
            },
            output_value=float(r_hat_future[0]),
            canaries_safe=1 if canary_state is CanaryState.SAFE else 0,
            canaries_unsafe=1 if canary_state is CanaryState.UNSAFE else 0,
            canaries_unknown=1 if canary_state is CanaryState.UNKNOWN else 0,
        )

    # Evaluate post-warmup synchronization compliance (no warmup leakage!)
    eval_sl = slice(warmup_steps, eval_T)
    emp_viol_rate = float(np.mean(violations_bool[eval_sl]))
    obs_rate = float(np.mean(observed_mask[eval_sl]))
    mean_err = float(np.mean(errors[eval_sl]))
    max_err = float(np.max(errors[eval_sl]))
    cal_gap = abs(float(np.mean(predicted_fail_probs[eval_sl])) - emp_viol_rate)

    if cfg.shift_step is not None and cfg.shift_step > warmup_steps:
        pre_viol = float(np.mean(violations_bool[warmup_steps : cfg.shift_step]))
        post_viol = float(np.mean(violations_bool[cfg.shift_step : eval_T]))
    else:
        pre_viol = emp_viol_rate
        post_viol = emp_viol_rate

    return SyncRunResult(
        observer_name=obs_name,
        horizon_tau=horizon_tau,
        tolerance_eps=tolerance_eps,
        permitted_delta=permitted_delta,
        ledger=ledger,
        telemetry=telemetry,
        observation_rate=obs_rate,
        empirical_violation_rate=emp_viol_rate,
        sync_budget_satisfied=(emp_viol_rate <= permitted_delta),
        pre_shift_violation_rate=pre_viol,
        post_shift_violation_rate=post_viol,
        mean_error=mean_err,
        max_error=max_err,
        calibration_ece=cal_gap,
        detection_latency_steps=first_shift_detect_step,
        unknown_steps=unknown_steps,
        errors_series=errors,
        observed_mask=observed_mask,
    )
