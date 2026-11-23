"""Physical resource vector and full-lifecycle cost accounting ledger.

Implements the Living Computation measurement framework (Section II & VI):
    C(P, E, K, A, t) -> ResourceVector(steps, time_s, joules, memory_bytes, communication_bytes)

All cost categories (execution, trace recording, learning, guarding, reconfiguration)
are accounted for under a single boundary so preprocessing or monitoring work is never hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CostCategory(str, Enum):
    """Explicit cost categories so no overhead is hidden outside the accounting boundary."""

    EXECUTION = "execution"
    TRACE_RECORDING = "trace_recording"
    LEARNING = "learning"
    GUARDING = "guarding"
    RECONFIGURATION = "reconfiguration"


OVERHEAD_CATEGORIES = (
    CostCategory.TRACE_RECORDING,
    CostCategory.LEARNING,
    CostCategory.GUARDING,
    CostCategory.RECONFIGURATION,
)


@dataclass(frozen=True)
class EnergyModel:
    """Explicit, documented energy estimation model when hardware RAPL/SMC is unavailable.

    Note: On sandboxed/non-root hosts, hardware energy counters cannot be queried directly.
    Rather than conflating step count with energy or fabricating sensor readings, this model
    combines measured CPU time, memory traffic, and communication/serialization traffic with
    explicitly documented coefficients and labels every report with `source`.
    """

    cpu_watts: float = 3.5  # Active single-core power draw (J/s)
    joules_per_mem_byte: float = 5.0e-11  # ~50 pJ/byte DRAM/cache hierarchy transfer
    joules_per_comm_byte: float = 2.0e-10  # ~200 pJ/byte I/O / serialization / IPC
    source: str = "modeled_proxy"

    def estimate_joules(
        self, cpu_time_s: float, memory_bytes: int = 0, communication_bytes: int = 0
    ) -> float:
        return (
            self.cpu_watts * max(0.0, cpu_time_s)
            + self.joules_per_mem_byte * max(0, memory_bytes)
            + self.joules_per_comm_byte * max(0, communication_bytes)
        )


@dataclass
class ResourceVector:
    """5-dimensional physical resource measurement C = (steps, time, joules, memory, communication)."""

    steps: int = 0
    time_s: float = 0.0
    joules: float = 0.0
    memory_bytes: int = 0
    communication_bytes: int = 0

    def add_inplace(self, other: ResourceVector) -> None:
        self.steps += other.steps
        self.time_s += other.time_s
        self.joules += other.joules
        self.memory_bytes += other.memory_bytes
        self.communication_bytes += other.communication_bytes

    def __add__(self, other: ResourceVector) -> ResourceVector:
        return ResourceVector(
            steps=self.steps + other.steps,
            time_s=self.time_s + other.time_s,
            joules=self.joules + other.joules,
            memory_bytes=self.memory_bytes + other.memory_bytes,
            communication_bytes=self.communication_bytes + other.communication_bytes,
        )

    def __sub__(self, other: ResourceVector) -> ResourceVector:
        return ResourceVector(
            steps=self.steps - other.steps,
            time_s=self.time_s - other.time_s,
            joules=self.joules - other.joules,
            memory_bytes=self.memory_bytes - other.memory_bytes,
            communication_bytes=self.communication_bytes - other.communication_bytes,
        )

    def weighted_economic_cost(
        self,
        w_step: float = 0.0,
        w_time: float = 0.0,
        w_joule: float = 1.0,
        w_memory: float = 0.0,
        w_comm: float = 0.0,
    ) -> float:
        """Optional economic projection that preserves the raw vector untouched."""
        return (
            w_step * self.steps
            + w_time * self.time_s
            + w_joule * self.joules
            + w_memory * self.memory_bytes
            + w_comm * self.communication_bytes
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": self.steps,
            "time_s": round(self.time_s, 9),
            "joules": round(self.joules, 9),
            "memory_bytes": self.memory_bytes,
            "communication_bytes": self.communication_bytes,
        }


@dataclass
class StepRecord:
    """Single timestep accounting record for one workload update."""

    timestep: int
    total_nodes: int
    visited_nodes: int
    by_category: Dict[CostCategory, ResourceVector]
    output_value: float
    correct: Optional[bool] = None
    contracts_hit: int = 0
    contracts_missed: int = 0
    canaries_safe: int = 0
    canaries_unsafe: int = 0
    canaries_unknown: int = 0
    nodes_avoided_by_contracts: int = 0

    @property
    def reconsideration_ratio(self) -> float:
        """L_t = |V_visited,t| / |V|."""
        if self.total_nodes <= 0:
            return 0.0
        return self.visited_nodes / self.total_nodes

    @property
    def total_cost(self) -> ResourceVector:
        total = ResourceVector()
        for vec in self.by_category.values():
            total.add_inplace(vec)
        return total


class CostLedger:
    """Complete cumulative and per-step resource accounting for an experimental run."""

    def __init__(
        self,
        system_name: str,
        algorithm_version: str,
        energy_model: Optional[EnergyModel] = None,
    ) -> None:
        self.system_name = system_name
        self.algorithm_version = algorithm_version
        self.energy_model = energy_model or EnergyModel()
        self.records: List[StepRecord] = []
        self.totals_by_category: Dict[CostCategory, ResourceVector] = {
            cat: ResourceVector() for cat in CostCategory
        }
        self.peak_memory_bytes: int = 0

    def record_step(
        self,
        timestep: int,
        total_nodes: int,
        visited_nodes: int,
        costs: Dict[CostCategory, ResourceVector],
        output_value: float,
        active_memory_bytes: int = 0,
        contracts_hit: int = 0,
        contracts_missed: int = 0,
        canaries_safe: int = 0,
        canaries_unsafe: int = 0,
        canaries_unknown: int = 0,
        nodes_avoided_by_contracts: int = 0,
    ) -> StepRecord:
        full_costs: Dict[CostCategory, ResourceVector] = {}
        for cat in CostCategory:
            vec = costs.get(cat, ResourceVector())
            full_costs[cat] = vec
            self.totals_by_category[cat].add_inplace(vec)

        if active_memory_bytes > self.peak_memory_bytes:
            self.peak_memory_bytes = active_memory_bytes

        rec = StepRecord(
            timestep=timestep,
            total_nodes=total_nodes,
            visited_nodes=visited_nodes,
            by_category=full_costs,
            output_value=output_value,
            contracts_hit=contracts_hit,
            contracts_missed=contracts_missed,
            canaries_safe=canaries_safe,
            canaries_unsafe=canaries_unsafe,
            canaries_unknown=canaries_unknown,
            nodes_avoided_by_contracts=nodes_avoided_by_contracts,
        )
        self.records.append(rec)
        return rec

    @property
    def total_cost(self) -> ResourceVector:
        total = ResourceVector()
        for vec in self.totals_by_category.values():
            total.add_inplace(vec)
        return total

    @property
    def execution_cost(self) -> ResourceVector:
        return self.totals_by_category[CostCategory.EXECUTION]

    @property
    def overhead_cost(self) -> ResourceVector:
        total = ResourceVector()
        for cat in OVERHEAD_CATEGORIES:
            total.add_inplace(self.totals_by_category[cat])
        return total

    @property
    def learning_and_guarding_cost(self) -> ResourceVector:
        return (
            self.totals_by_category[CostCategory.LEARNING]
            + self.totals_by_category[CostCategory.GUARDING]
        )

    def cumulative_steps_series(self) -> List[int]:
        out: List[int] = []
        acc = 0
        for rec in self.records:
            acc += rec.total_cost.steps
            out.append(acc)
        return out

    def cumulative_joules_series(self) -> List[float]:
        out: List[float] = []
        acc = 0.0
        for rec in self.records:
            acc += rec.total_cost.joules
            out.append(acc)
        return out

    def cumulative_time_series(self) -> List[float]:
        out: List[float] = []
        acc = 0.0
        for rec in self.records:
            acc += rec.total_cost.time_s
            out.append(acc)
        return out

    def mean_reconsideration_ratio(self) -> float:
        if not self.records:
            return 0.0
        return sum(r.reconsideration_ratio for r in self.records) / len(self.records)

    def correctness_summary(self) -> Dict[str, Any]:
        checked = [r for r in self.records if r.correct is not None]
        mismatches = [r for r in checked if not r.correct]
        return {
            "checked_steps": len(checked),
            "mismatches": len(mismatches),
            "accuracy": (len(checked) - len(mismatches)) / len(checked) if checked else None,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "system_name": self.system_name,
            "algorithm_version": self.algorithm_version,
            "timesteps": len(self.records),
            "energy_model_source": self.energy_model.source,
            "total_cost": self.total_cost.to_dict(),
            "peak_memory_bytes": self.peak_memory_bytes,
            "by_category": {
                cat.value: vec.to_dict() for cat, vec in self.totals_by_category.items()
            },
            "mean_reconsideration_ratio": round(self.mean_reconsideration_ratio(), 6),
            "total_contracts_hit": sum(r.contracts_hit for r in self.records),
            "total_contracts_missed": sum(r.contracts_missed for r in self.records),
            "total_canaries_safe": sum(r.canaries_safe for r in self.records),
            "total_canaries_unsafe": sum(r.canaries_unsafe for r in self.records),
            "total_canaries_unknown": sum(r.canaries_unknown for r in self.records),
            "total_nodes_avoided_by_contracts": sum(
                r.nodes_avoided_by_contracts for r in self.records
            ),
            "correctness": self.correctness_summary(),
        }


def compare_against_baseline(
    baseline: CostLedger, adaptive: CostLedger
) -> Dict[str, Any]:
    """Compute S(T), adaptation payback T*, and gross/net R_avoid against a baseline.

    Avoids double-counting by explicitly distinguishing:
        C_total      = C_exec + C_trace + C_learning + C_guarding + C_reconfig
        C_overhead   = C_trace + C_learning + C_guarding + C_reconfig
        S(T)         = C_baseline_total(T) - C_adaptive_total(T)
        R_avoid_gross = (C_baseline_total - C_adaptive_exec) / C_overhead
        R_avoid_net   = (C_baseline_total - C_adaptive_total) / C_overhead = R_avoid_gross - 1
    """
    base_steps = baseline.cumulative_steps_series()
    adap_steps = adaptive.cumulative_steps_series()
    base_joules = baseline.cumulative_joules_series()
    adap_joules = adaptive.cumulative_joules_series()
    base_time = baseline.cumulative_time_series()
    adap_time = adaptive.cumulative_time_series()

    n = min(len(base_steps), len(adap_steps))

    def _payback(b_series: List[float] | List[int], a_series: List[float] | List[int]) -> Optional[int]:
        for t in range(n):
            if b_series[t] - a_series[t] > 0:
                return t
        return None

    def _ratio(num: float, den: float) -> Optional[float]:
        if den <= 0:
            return None
        return num / den

    b_tot = baseline.total_cost
    a_tot = adaptive.total_cost
    a_exec = adaptive.execution_cost
    a_ovh = adaptive.overhead_cost

    return {
        "baseline": baseline.system_name,
        "adaptive": adaptive.system_name,
        "savings_steps": b_tot.steps - a_tot.steps,
        "savings_steps_pct": (
            round(100.0 * (b_tot.steps - a_tot.steps) / b_tot.steps, 3)
            if b_tot.steps > 0
            else 0.0
        ),
        "savings_time_s": round(b_tot.time_s - a_tot.time_s, 6),
        "savings_time_pct": (
            round(100.0 * (b_tot.time_s - a_tot.time_s) / b_tot.time_s, 3)
            if b_tot.time_s > 0
            else 0.0
        ),
        "savings_joules": round(b_tot.joules - a_tot.joules, 9),
        "savings_joules_pct": (
            round(100.0 * (b_tot.joules - a_tot.joules) / b_tot.joules, 3)
            if b_tot.joules > 0
            else 0.0
        ),
        "payback_step_ops": _payback(base_steps, adap_steps),
        "payback_step_joules": _payback(base_joules, adap_joules),
        "payback_step_time": _payback(base_time, adap_time),
        "r_avoid_gross_steps": _ratio(b_tot.steps - a_exec.steps, a_ovh.steps),
        "r_avoid_net_steps": _ratio(b_tot.steps - a_tot.steps, a_ovh.steps),
        "r_avoid_gross_joules": _ratio(b_tot.joules - a_exec.joules, a_ovh.joules),
        "r_avoid_net_joules": _ratio(b_tot.joules - a_tot.joules, a_ovh.joules),
    }
