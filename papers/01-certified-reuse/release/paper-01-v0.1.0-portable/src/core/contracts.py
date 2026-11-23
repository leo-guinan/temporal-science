"""Validity contracts, learned representations, and the Knowledge & Avoidance Ledger.

Implements the central data objects from Section II & III:
  - GuaranteeLevel (Empirical, Distributional, Restricted worst-case, General worst-case)
  - ValidityContract (preconditions, assumptions, soundness, correctness guarantees)
  - LearnedRepresentation (compressed subcomputation + reconstruction/reuse state)
  - KnowledgeLedger (persistent history of learning, validation, invalidation, reuse,
    and avoided-computation provenance)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class GuaranteeLevel(str, Enum):
    """Four-tier guarantee taxonomy from Section II."""

    EMPIRICAL = "empirical"
    DISTRIBUTIONAL = "distributional"
    RESTRICTED_WORST_CASE = "restricted_worst_case"
    GENERAL_WORST_CASE = "general_worst_case"


@dataclass
class ValidityContract:
    """Formal specification of when a compressed subcomputation remains sound."""

    contract_id: str
    target_node_id: int
    target_node_name: str
    boundary_ids: Tuple[int, ...]
    internal_ids: Tuple[int, ...]
    guarantee_level: GuaranteeLevel
    sound: bool
    precondition_summary: str
    assumptions: List[str]
    created_at_step: int
    # Formal parameters (e.g., exact Lipschitz bounds, threshold, floating-point safety eps)
    parameters: Dict[str, Any] = field(default_factory=dict)
    # Runtime accounting
    hits: int = 0
    invalidations: int = 0
    nodes_avoided_total: int = 0
    estimated_joules_saved: float = 0.0
    active: bool = True

    @property
    def absorbed_node_count(self) -> int:
        """Number of node evaluations avoided when this contract fires SAFE (internal + target)."""
        return len(self.internal_ids) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "target_node_id": self.target_node_id,
            "target_node_name": self.target_node_name,
            "boundary_size": len(self.boundary_ids),
            "internal_size": len(self.internal_ids),
            "absorbed_node_count": self.absorbed_node_count,
            "guarantee_level": self.guarantee_level.value,
            "sound": self.sound,
            "precondition_summary": self.precondition_summary,
            "assumptions": list(self.assumptions),
            "created_at_step": self.created_at_step,
            "hits": self.hits,
            "invalidations": self.invalidations,
            "nodes_avoided_total": self.nodes_avoided_total,
            "estimated_joules_saved": round(self.estimated_joules_saved, 9),
            "active": self.active,
        }


@dataclass
class LearnedRepresentation:
    """A compressed subcomputation module backed by a ValidityContract and optional regime cache."""

    rep_id: str
    contract: ValidityContract
    # Reference execution anchor for Lipschitz-margin validity ball
    ref_boundary_values: Dict[int, float] = field(default_factory=dict)
    ref_pre_value: float = 0.0
    ref_output_value: float = 0.0
    ref_margin: float = 0.0
    # Optional exact boundary-state cache for recurring discrete/quantized regimes
    regime_cache: Dict[Tuple[float, ...], float] = field(default_factory=dict)
    max_regime_cache_size: int = 512

    def cache_regime(self, boundary_tuple: Tuple[float, ...], output_val: float) -> None:
        if len(self.regime_cache) >= self.max_regime_cache_size and boundary_tuple not in self.regime_cache:
            # Simple FIFO eviction to keep memory bounded
            first_key = next(iter(self.regime_cache))
            del self.regime_cache[first_key]
        self.regime_cache[boundary_tuple] = output_val


@dataclass
class LedgerEvent:
    """One auditable entry in the KnowledgeLedger."""

    timestep: int
    event_type: str  # "learned", "validated", "avoided", "invalidated", "retired", "counterexample"
    contract_id: str
    target_node_name: str
    reason: str
    assumptions: List[str] = field(default_factory=list)
    nodes_avoided: int = 0
    estimated_joules_saved: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestep": self.timestep,
            "event_type": self.event_type,
            "contract_id": self.contract_id,
            "target_node_name": self.target_node_name,
            "reason": self.reason,
            "assumptions": self.assumptions,
            "nodes_avoided": self.nodes_avoided,
            "estimated_joules_saved": round(self.estimated_joules_saved, 9),
            "details": self.details,
        }


class KnowledgeLedger:
    """Persistent ledger of learned representations, validations, invalidations, and avoided work."""

    def __init__(self, max_avoidance_samples: int = 500) -> None:
        self.contracts: Dict[str, ValidityContract] = {}
        self.lifecycle_events: List[LedgerEvent] = []
        self.avoidance_samples: List[LedgerEvent] = []
        self.max_avoidance_samples = max_avoidance_samples
        self.total_avoidance_events: int = 0
        self.total_nodes_avoided: int = 0
        self.total_estimated_joules_saved: float = 0.0
        self.total_invalidations: int = 0

    def register_contract(self, contract: ValidityContract, reason: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.contracts[contract.contract_id] = contract
        self.lifecycle_events.append(
            LedgerEvent(
                timestep=contract.created_at_step,
                event_type="learned",
                contract_id=contract.contract_id,
                target_node_name=contract.target_node_name,
                reason=reason,
                assumptions=list(contract.assumptions),
                details=details or {},
            )
        )

    def record_avoidance(
        self,
        timestep: int,
        contract: ValidityContract,
        reason: str,
        estimated_joules_saved: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        nodes_saved = contract.absorbed_node_count
        contract.hits += 1
        contract.nodes_avoided_total += nodes_saved
        contract.estimated_joules_saved += estimated_joules_saved
        self.total_avoidance_events += 1
        self.total_nodes_avoided += nodes_saved
        self.total_estimated_joules_saved += estimated_joules_saved

        # Store bounded sample of individual avoidance events (plus complete aggregate stats per contract)
        if len(self.avoidance_samples) < self.max_avoidance_samples:
            self.avoidance_samples.append(
                LedgerEvent(
                    timestep=timestep,
                    event_type="avoided",
                    contract_id=contract.contract_id,
                    target_node_name=contract.target_node_name,
                    reason=reason,
                    assumptions=list(contract.assumptions),
                    nodes_avoided=nodes_saved,
                    estimated_joules_saved=estimated_joules_saved,
                    details=details or {},
                )
            )

    def record_invalidation(
        self,
        timestep: int,
        contract: ValidityContract,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        contract.invalidations += 1
        self.total_invalidations += 1
        if len(self.lifecycle_events) < 2000:
            self.lifecycle_events.append(
                LedgerEvent(
                    timestep=timestep,
                    event_type="invalidated",
                    contract_id=contract.contract_id,
                    target_node_name=contract.target_node_name,
                    reason=reason,
                    assumptions=list(contract.assumptions),
                    details=details or {},
                )
            )

    def summary(self) -> Dict[str, Any]:
        sorted_contracts = sorted(
            self.contracts.values(),
            key=lambda c: c.nodes_avoided_total,
            reverse=True,
        )
        return {
            "num_contracts_learned": len(self.contracts),
            "num_active_contracts": sum(1 for c in self.contracts.values() if c.active),
            "total_avoidance_events": self.total_avoidance_events,
            "total_nodes_avoided": self.total_nodes_avoided,
            "total_estimated_joules_saved": round(self.total_estimated_joules_saved, 9),
            "total_invalidations": self.total_invalidations,
            "contracts": [c.to_dict() for c in sorted_contracts],
            "sample_avoidance_provenance": [e.to_dict() for e in self.avoidance_samples[:30]],
            "lifecycle_events_count": len(self.lifecycle_events),
        }
