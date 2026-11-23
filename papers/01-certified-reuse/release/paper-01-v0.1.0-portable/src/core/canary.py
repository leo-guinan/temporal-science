"""Computational Canary interface with explicit SAFE / UNSAFE / UNKNOWN states.

Implements LC-4 (Computational canary) and Experiment 2's reusable monitor interface:
  - LipschitzMarginCanary: sound event-driven validity-region guard (zero missed invalidations)
  - ExactDirtyCanary: sound dependency-equality guard
  - PeriodicAuditCanary: sampled/probabilistic monitor with explicit UNKNOWN states and
    measurable missed-invalidation rates
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.contracts import LearnedRepresentation
from core.dependency_graph import Node, OpType


class CanaryState(str, Enum):
    """Explicit three-valued canary status (Experiment 2 research output)."""

    SAFE = "safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"


@dataclass
class CanaryCheckResult:
    """Outcome and exact operation cost of evaluating a canary."""

    state: CanaryState
    guard_ops: int
    reason: str
    cached_output: Optional[float] = None
    margin_remaining: Optional[float] = None
    used_regime_cache: bool = False


class Canary(ABC):
    """Abstract reusable canary interface attached to a LearnedRepresentation / ValidityContract."""

    def __init__(self, canary_id: str, representation: LearnedRepresentation) -> None:
        self.canary_id = canary_id
        self.representation = representation
        self.checks: int = 0
        self.safe_count: int = 0
        self.unsafe_count: int = 0
        self.unknown_count: int = 0

    @abstractmethod
    def check(
        self,
        changed_boundary_ids: Sequence[int],
        current_values: Sequence[float],
        timestep: int,
    ) -> CanaryCheckResult:
        """Check whether the representation remains valid after boundary changes."""

    @abstractmethod
    def reanchor(self, current_values: Sequence[float], pre_value: float, output_value: float) -> int:
        """Update anchor state after recomputation; returns maintenance ops spent."""


def compute_saturation_margin(node: Node, pre_value: float) -> float:
    """Exact distance from `pre_value` to the nearest point where `node`'s output can change.

    Returns 0.0 when `pre_value` lies in a non-constant (linear/boundary) region.
    """
    if node.op is OpType.THRESHOLD:
        theta = float(node.params["threshold"])
        return abs(pre_value - theta)
    if node.op is OpType.RELU:
        theta = float(node.params.get("threshold", 0.0))
        if pre_value < theta:
            return theta - pre_value
        return 0.0
    if node.op is OpType.CLAMP:
        lo = float(node.params["lo"])
        hi = float(node.params["hi"])
        if pre_value < lo:
            return lo - pre_value
        if pre_value > hi:
            return hi - pre_value
        return 0.0
    return 0.0


@dataclass
class ValidityBall:
    """One certified Lipschitz validity ball B(u0, margin) in a Multi-Anchor Validity Atlas."""

    ref_boundary_tuple: Tuple[float, ...]
    ref_pre_value: float
    ref_output_value: float
    ref_margin: float
    fp_eps: float
    hits: int = 0


class LipschitzMarginCanary(Canary):
    """Sound event-driven validity-region canary using exact global Lipschitz bounds.

    Theorem (Multi-Anchor Soundness):
        Because L is a global Lipschitz upper bound on p(u) across all R^|B|,
        for ANY cached anchor j with margin m_j > 0:
            sum_{b in B} L_b * |u_b - u_b^(j)| + eps_fp^(j) < m_j
            ==> target(p(u)) == y^(j)
        holds for EVERY u in that validity ball (RESTRICTED_WORST_CASE guarantee,
        zero missed invalidations).

    Maintains:
      - Fast active-anchor incremental drift check (O(|changed|) ops on nominal steps)
      - Exact historical boundary-signature lookup (`regime_cache`, O(1) dict hit)
      - Multi-Anchor Validity Atlas (up to `max_atlas_balls` disjoint balls for
        recurring noisy/perturbed operating regimes)
    """

    def __init__(
        self,
        canary_id: str,
        representation: LearnedRepresentation,
        target_node: Node,
        lipschitz_by_boundary: Dict[int, float],
        enable_regime_cache: bool = True,
        max_atlas_balls: int = 6,
    ) -> None:
        super().__init__(canary_id, representation)
        self.target_node = target_node
        self.boundary_ids: Tuple[int, ...] = representation.contract.boundary_ids
        self.lipschitz_by_boundary: Dict[int, float] = dict(lipschitz_by_boundary)
        self._lipschitz_tuple: Tuple[float, ...] = tuple(
            self.lipschitz_by_boundary.get(b, 0.0) for b in self.boundary_ids
        )
        self._boundary_index: Dict[int, int] = {
            b: idx for idx, b in enumerate(self.boundary_ids)
        }
        self.enable_regime_cache = enable_regime_cache
        self.max_atlas_balls = max(1, max_atlas_balls)
        self._per_boundary_drift: List[float] = [0.0] * len(self.boundary_ids)
        self._active_ref_tuple: Tuple[float, ...] = (0.0,) * len(self.boundary_ids)
        self._fp_eps: float = 1e-9
        self.atlas: List[ValidityBall] = []
        self.atlas_hits: int = 0
        self.regime_cache_hits: int = 0

    def _activate_ball(self, ball: ValidityBall, current_values: Sequence[float]) -> int:
        """Promote a matching atlas ball to the active fast-path anchor."""
        rep = self.representation
        self._active_ref_tuple = ball.ref_boundary_tuple
        rep.ref_pre_value = ball.ref_pre_value
        rep.ref_output_value = ball.ref_output_value
        rep.ref_margin = ball.ref_margin
        self._fp_eps = ball.fp_eps
        for idx, b in enumerate(self.boundary_ids):
            ref_v = ball.ref_boundary_tuple[idx]
            rep.ref_boundary_values[b] = ref_v
            self._per_boundary_drift[idx] = self._lipschitz_tuple[idx] * abs(
                current_values[b] - ref_v
            )
        return len(self.boundary_ids)

    def reanchor(
        self, current_values: Sequence[float], pre_value: float, output_value: float
    ) -> int:
        rep = self.representation
        ops = 0
        scale_sum = 1.0 + abs(pre_value)
        ref_vals: List[float] = []
        for idx, b in enumerate(self.boundary_ids):
            val = current_values[b]
            ref_vals.append(val)
            rep.ref_boundary_values[b] = val
            self._per_boundary_drift[idx] = 0.0
            scale_sum += self._lipschitz_tuple[idx] * abs(val)
            ops += 1

        ref_tuple = tuple(ref_vals)
        margin = compute_saturation_margin(self.target_node, pre_value)
        fp_eps = 1e-9 * scale_sum

        self._active_ref_tuple = ref_tuple
        rep.ref_pre_value = pre_value
        rep.ref_output_value = output_value
        rep.ref_margin = margin
        self._fp_eps = fp_eps

        # Store nontrivial validity balls in the Multi-Anchor Atlas (bounded LRU/LFU)
        if margin > 0.0:
            new_ball = ValidityBall(
                ref_boundary_tuple=ref_tuple,
                ref_pre_value=pre_value,
                ref_output_value=output_value,
                ref_margin=margin,
                fp_eps=fp_eps,
            )
            # Avoid duplicating an already well-covered anchor
            replaced = False
            for i, existing in enumerate(self.atlas):
                if existing.ref_boundary_tuple == ref_tuple:
                    self.atlas[i] = new_ball
                    replaced = True
                    break
            if not replaced:
                if len(self.atlas) >= self.max_atlas_balls:
                    # Evict least-used ball (preferring to keep high-hit regimes)
                    evict_idx = min(range(len(self.atlas)), key=lambda i: self.atlas[i].hits)
                    self.atlas[evict_idx] = new_ball
                else:
                    self.atlas.append(new_ball)

        if self.enable_regime_cache:
            rep.cache_regime(ref_tuple, output_value)
            ops += 1
        return ops

    def check(
        self,
        changed_boundary_ids: Sequence[int],
        current_values: Sequence[float],
        timestep: int,
    ) -> CanaryCheckResult:
        self.checks += 1
        rep = self.representation
        guard_ops = 0

        # 1. Fast path: update exact drift for changed boundary inputs on active anchor
        for b in changed_boundary_ids:
            idx = self._boundary_index[b]
            self._per_boundary_drift[idx] = self._lipschitz_tuple[idx] * abs(
                current_values[b] - self._active_ref_tuple[idx]
            )
            guard_ops += 1

        total_drift = sum(self._per_boundary_drift)
        guard_ops += 1

        if rep.ref_margin > 0.0 and (total_drift + self._fp_eps) < rep.ref_margin:
            self.safe_count += 1
            remaining = rep.ref_margin - total_drift - self._fp_eps
            return CanaryCheckResult(
                state=CanaryState.SAFE,
                guard_ops=guard_ops,
                reason=(
                    f"Lipschitz validity ball holds: drift={total_drift:.6f} "
                    f"< margin={rep.ref_margin:.6f} (remaining={remaining:.6f})"
                ),
                cached_output=rep.ref_output_value,
                margin_remaining=remaining,
            )

        # 2. Exact boundary-state lookup in historical regime cache (O(1) hash lookup)
        cur_tuple: Optional[Tuple[float, ...]] = None
        if self.enable_regime_cache and rep.regime_cache:
            cur_tuple = tuple(current_values[b] for b in self.boundary_ids)
            guard_ops += 1
            cached = rep.regime_cache.get(cur_tuple)
            if cached is not None:
                self.safe_count += 1
                self.regime_cache_hits += 1
                return CanaryCheckResult(
                    state=CanaryState.SAFE,
                    guard_ops=guard_ops,
                    reason="Exact historical boundary state matched in learned regime cache",
                    cached_output=cached,
                    margin_remaining=None,
                    used_regime_cache=True,
                )

        # 3. Multi-Anchor Validity Atlas scan (handles recurring regimes with continuous jitter!)
        if len(self.atlas) > 1:
            if cur_tuple is None:
                cur_tuple = tuple(current_values[b] for b in self.boundary_ids)
            lips = self._lipschitz_tuple
            for ball in self.atlas:
                if ball.ref_boundary_tuple == self._active_ref_tuple:
                    continue
                if ball.ref_margin <= 0.0:
                    continue
                limit = ball.ref_margin - ball.fp_eps
                if limit <= 0.0:
                    continue
                b_drift = 0.0
                exceeded = False
                for cur_v, ref_v, lip in zip(cur_tuple, ball.ref_boundary_tuple, lips):
                    guard_ops += 1
                    b_drift += lip * abs(cur_v - ref_v)
                    if b_drift >= limit:
                        exceeded = True
                        break
                if not exceeded:
                    ball.hits += 1
                    self.safe_count += 1
                    self.atlas_hits += 1
                    # Promote hit ball to active anchor for O(1) subsequent hits
                    self._activate_ball(ball, current_values)
                    remaining = limit - b_drift
                    return CanaryCheckResult(
                        state=CanaryState.SAFE,
                        guard_ops=guard_ops,
                        reason=(
                            f"Multi-Anchor Validity Atlas hit: drift={b_drift:.6f} "
                            f"< margin={ball.ref_margin:.6f} (remaining={remaining:.6f})"
                        ),
                        cached_output=ball.ref_output_value,
                        margin_remaining=remaining,
                        used_regime_cache=True,
                    )

        self.unsafe_count += 1
        return CanaryCheckResult(
            state=CanaryState.UNSAFE,
            guard_ops=guard_ops,
            reason=(
                f"Validity margin exceeded across {len(self.atlas)} atlas ball(s): "
                f"active_drift={total_drift:.6f} >= margin={rep.ref_margin:.6f}; "
                "recomputation required"
            ),
            cached_output=None,
            margin_remaining=rep.ref_margin - total_drift,
        )


class ExactDirtyCanary(Canary):
    """Sound exact-equality boundary canary (SAFE iff all boundary values match anchor)."""

    def __init__(self, canary_id: str, representation: LearnedRepresentation) -> None:
        super().__init__(canary_id, representation)
        self.boundary_ids = representation.contract.boundary_ids

    def reanchor(
        self, current_values: Sequence[float], pre_value: float, output_value: float
    ) -> int:
        rep = self.representation
        for b in self.boundary_ids:
            rep.ref_boundary_values[b] = current_values[b]
        rep.ref_pre_value = pre_value
        rep.ref_output_value = output_value
        return len(self.boundary_ids)

    def check(
        self,
        changed_boundary_ids: Sequence[int],
        current_values: Sequence[float],
        timestep: int,
    ) -> CanaryCheckResult:
        self.checks += 1
        rep = self.representation
        ops = 0
        for b in changed_boundary_ids:
            ops += 1
            if current_values[b] != rep.ref_boundary_values.get(b):
                self.unsafe_count += 1
                return CanaryCheckResult(
                    state=CanaryState.UNSAFE,
                    guard_ops=ops,
                    reason=f"Boundary input {b} changed from anchor",
                )
        self.safe_count += 1
        return CanaryCheckResult(
            state=CanaryState.SAFE,
            guard_ops=max(1, ops),
            reason="All boundary inputs match anchor exactly",
            cached_output=rep.ref_output_value,
        )


class PeriodicAuditCanary(Canary):
    """Periodically sampled monitor for Experiment 2 comparison.

    Only audits every `audit_period` steps (returning UNKNOWN on un-audited steps
    while optimistically reusing the cached value, or forcing recomputation on audit).
    This explicitly exposes the tradeoff between lower guard cost and missed invalidations.
    """

    def __init__(
        self,
        canary_id: str,
        representation: LearnedRepresentation,
        audit_period: int = 10,
        drift_threshold: float = 0.0,
    ) -> None:
        super().__init__(canary_id, representation)
        self.audit_period = max(1, audit_period)
        self.drift_threshold = drift_threshold
        self.boundary_ids = representation.contract.boundary_ids
        self._last_audit_step: int = -1

    def reanchor(
        self, current_values: Sequence[float], pre_value: float, output_value: float
    ) -> int:
        rep = self.representation
        for b in self.boundary_ids:
            rep.ref_boundary_values[b] = current_values[b]
        rep.ref_pre_value = pre_value
        rep.ref_output_value = output_value
        return len(self.boundary_ids)

    def check(
        self,
        changed_boundary_ids: Sequence[int],
        current_values: Sequence[float],
        timestep: int,
    ) -> CanaryCheckResult:
        self.checks += 1
        rep = self.representation
        if self._last_audit_step < 0 or (timestep - self._last_audit_step) >= self.audit_period:
            self._last_audit_step = timestep
            ops = 0
            max_delta = 0.0
            for b in self.boundary_ids:
                ops += 1
                d = abs(current_values[b] - rep.ref_boundary_values.get(b, 0.0))
                if d > max_delta:
                    max_delta = d
            if max_delta > self.drift_threshold:
                self.unsafe_count += 1
                return CanaryCheckResult(
                    state=CanaryState.UNSAFE,
                    guard_ops=ops,
                    reason=f"Periodic audit at t={timestep} detected delta={max_delta:.4f}",
                )
            self.safe_count += 1
            return CanaryCheckResult(
                state=CanaryState.SAFE,
                guard_ops=ops,
                reason=f"Periodic audit at t={timestep} passed (max_delta={max_delta:.4f})",
                cached_output=rep.ref_output_value,
            )

        # Between audits: validity is UNKNOWN (optimistic reuse carries measurable risk)
        self.unknown_count += 1
        return CanaryCheckResult(
            state=CanaryState.UNKNOWN,
            guard_ops=1,
            reason=f"Skipped audit at t={timestep} (period={self.audit_period}); state UNKNOWN",
            cached_output=rep.ref_output_value,
        )
