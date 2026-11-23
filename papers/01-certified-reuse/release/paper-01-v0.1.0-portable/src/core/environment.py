"""Deterministic seeded workload environments and environment policies.

Provides identical, replayable disturbance streams across all compared systems
(Experimental Control #3) covering both structured regimes and adversarial/high-entropy
failure-boundary regimes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
import random


class WorkloadRegime(str, Enum):
    LOCALIZED_REGIME_DRIFT = "localized_regime_drift"
    RECURRING_STATES = "recurring_states"
    DRIFT_AND_REGIME_SHIFT = "drift_and_regime_shift"
    HIGH_ENTROPY_SHOCK = "high_entropy_shock"


@dataclass
class EnvironmentPolicy:
    """Rules governing allowed environmental states and transitions (LC-5 foundation)."""

    policy_id: str
    value_bounds: Tuple[float, float] = (-5.0, 5.0)
    max_changed_inputs_per_step: Optional[int] = None
    max_step_delta: Optional[float] = None
    description: str = "Unconstrained nominal sensor environment"

    def check_transition(
        self, prev_inputs: Dict[int, float], delta: Dict[int, float]
    ) -> Tuple[bool, Optional[str]]:
        if self.max_changed_inputs_per_step is not None and len(delta) > self.max_changed_inputs_per_step:
            return False, f"Changed {len(delta)} inputs > limit {self.max_changed_inputs_per_step}"
        lo, hi = self.value_bounds
        for k, v in delta.items():
            if v < lo or v > hi:
                return False, f"Input {k}={v:.4f} outside [{lo}, {hi}]"
            if self.max_step_delta is not None and k in prev_inputs:
                if abs(v - prev_inputs[k]) > self.max_step_delta:
                    return False, f"Input {k} jumped by {abs(v - prev_inputs[k]):.4f} > {self.max_step_delta}"
        return True, None


@dataclass
class UpdateEvent:
    """A single deterministic environmental update."""

    timestep: int
    delta: Dict[int, float]
    regime_label: str = "nominal"
    is_shock: bool = False


@dataclass
class WorkloadConfig:
    """Configuration for a reproducible workload sequence."""

    regime: WorkloadRegime = WorkloadRegime.LOCALIZED_REGIME_DRIFT
    num_updates: int = 10_000
    seed: int = 2026
    changes_per_step: Tuple[int, int] = (1, 3)
    nominal_jitter_std: float = 0.04
    shock_probability: float = 0.04
    shock_magnitude: float = 1.6
    num_recurring_profiles: int = 8


class WorkloadEnvironment:
    """Generates a deterministic initial input state and sequence of UpdateEvents."""

    def __init__(
        self,
        input_ids: List[int],
        config: WorkloadConfig,
        policy: Optional[EnvironmentPolicy] = None,
    ) -> None:
        self.input_ids = list(input_ids)
        self.config = config
        self.policy = policy or EnvironmentPolicy(policy_id="default_unconstrained")

    def generate(self) -> Tuple[Dict[int, float], List[UpdateEvent]]:
        """Pre-generate the exact deterministic workload so every engine receives identical inputs."""
        rng = random.Random(self.config.seed)
        cfg = self.config
        n_in = len(self.input_ids)

        # Baseline nominal sensor values centered gently in [-0.25, 0.25]
        nominal: Dict[int, float] = {
            nid: round(rng.uniform(-0.22, 0.22), 5) for nid in self.input_ids
        }
        current = dict(nominal)
        events: List[UpdateEvent] = []

        # Pre-generate recurring profiles if needed
        profiles: List[Dict[int, float]] = []
        if cfg.regime is WorkloadRegime.RECURRING_STATES:
            for p_idx in range(cfg.num_recurring_profiles):
                prof = {}
                for nid in self.input_ids:
                    # Mix of low-nominal and active-high regimes across profiles
                    if (nid + p_idx) % 5 == 0:
                        prof[nid] = round(rng.uniform(0.6, 1.3), 4)
                    else:
                        prof[nid] = round(rng.uniform(-0.3, 0.3), 4)
                profiles.append(prof)
            current = dict(profiles[0])
            nominal = dict(profiles[0])

        lo, hi = self.policy.value_bounds

        def clamp_val(x: float) -> float:
            if x < lo:
                return lo
            if x > hi:
                return hi
            return round(x, 6)

        for t in range(1, cfg.num_updates + 1):
            delta: Dict[int, float] = {}
            is_shock = False
            label = cfg.regime.value

            if cfg.regime is WorkloadRegime.LOCALIZED_REGIME_DRIFT:
                if rng.random() < cfg.shock_probability:
                    # Localized shock: 2-4 adjacent sensors jump significantly (crossing gates)
                    is_shock = True
                    label = "localized_shock"
                    start = rng.randrange(n_in)
                    width = rng.randint(2, 4)
                    for k in range(width):
                        nid = self.input_ids[(start + k) % n_in]
                        jump = rng.uniform(-cfg.shock_magnitude, cfg.shock_magnitude)
                        val = clamp_val(nominal[nid] + jump)
                        current[nid] = val
                        delta[nid] = val
                else:
                    # Small localized mean-reverting drift around current/nominal state
                    k_chg = rng.randint(cfg.changes_per_step[0], cfg.changes_per_step[1])
                    chosen = rng.sample(self.input_ids, k=min(k_chg, n_in))
                    for nid in chosen:
                        # Gentle Ornstein-Uhlenbeck pull toward nominal + jitter
                        nxt = current[nid] + 0.25 * (nominal[nid] - current[nid]) + rng.gauss(
                            0.0, cfg.nominal_jitter_std
                        )
                        val = clamp_val(nxt)
                        current[nid] = val
                        delta[nid] = val

            elif cfg.regime is WorkloadRegime.RECURRING_STATES:
                # Subsystem-localized switches among recurring discrete profile values
                prof = profiles[rng.randrange(len(profiles))]
                start = (rng.randrange(max(1, n_in // 4)) * 4) % n_in
                width = rng.randint(2, 4)
                for k in range(width):
                    nid = self.input_ids[(start + k) % n_in]
                    val = prof[nid]
                    current[nid] = val
                    delta[nid] = val
                label = "recurring_profile_switch"

            elif cfg.regime is WorkloadRegime.DRIFT_AND_REGIME_SHIFT:
                # Phase 1 (0..40%): nominal; Phase 2 (40..60%): regime shift; Phase 3 (60..100%): new stable
                frac = t / cfg.num_updates
                if 0.40 <= frac < 0.60:
                    label = "regime_shift"
                    is_shock = True
                    k_chg = rng.randint(3, 6)
                    chosen = rng.sample(self.input_ids, k=min(k_chg, n_in))
                    for nid in chosen:
                        # Shift nominal operating point upward by +0.9 so gates flip
                        target = nominal[nid] + 0.95
                        nxt = current[nid] + 0.35 * (target - current[nid]) + rng.gauss(0.0, 0.12)
                        val = clamp_val(nxt)
                        current[nid] = val
                        delta[nid] = val
                else:
                    offset = 0.0 if frac < 0.40 else 0.95
                    label = "stable_phase_1" if frac < 0.40 else "stable_phase_2"
                    k_chg = rng.randint(cfg.changes_per_step[0], cfg.changes_per_step[1])
                    chosen = rng.sample(self.input_ids, k=min(k_chg, n_in))
                    for nid in chosen:
                        target = nominal[nid] + offset
                        nxt = current[nid] + 0.3 * (target - current[nid]) + rng.gauss(
                            0.0, cfg.nominal_jitter_std
                        )
                        val = clamp_val(nxt)
                        current[nid] = val
                        delta[nid] = val

            elif cfg.regime is WorkloadRegime.HIGH_ENTROPY_SHOCK:
                # Adversarial failure-boundary stress test: large unpredictable random jumps
                is_shock = True
                label = "high_entropy_shock"
                k_chg = rng.randint(8, 16)
                chosen = rng.sample(self.input_ids, k=min(k_chg, n_in))
                for nid in chosen:
                    val = clamp_val(rng.uniform(-2.2, 2.2))
                    current[nid] = val
                    delta[nid] = val

            events.append(
                UpdateEvent(
                    timestep=t,
                    delta=delta,
                    regime_label=label,
                    is_shock=is_shock,
                )
            )

        return nominal, events
