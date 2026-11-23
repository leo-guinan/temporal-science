"""v0.2 Structured Telemetry & Strictly Unit-Separated Ledgers (Section 11).

Keeps physical energy, modeled energy, operation counts, human time, and monetary costs
in strictly separate ledgers so unlike units are NEVER silently added together.

Provides optional structured records for:
  - Observation acquisition cost (LC-17)
  - Predictive synchronization (horizon, tolerance, predicted/realized, violations; LC-18)
  - Predictive timespace movement & information gain (LC-16)
  - Human or simulated-human interventions & Contribution-to-Savings attribution (LC-11)
  - Semantic interface versions & human knowledge invalidation events (LC-12, LC-13, LC-14)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UnitSeparatedTotals:
    """Strict unit separation across physical/modeled energy, ops, human time, and money."""

    operation_counts: int = 0
    modeled_energy_joules: float = 0.0
    physical_energy_joules: Optional[float] = None  # None unless hardware RAPL/SMC measured
    human_time_s: float = 0.0
    human_time_source: str = "simulated_human_model"
    human_interactions: int = 0
    monetary_cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_counts": self.operation_counts,
            "modeled_energy_joules": round(self.modeled_energy_joules, 9),
            "physical_energy_joules": (
                round(self.physical_energy_joules, 9)
                if self.physical_energy_joules is not None
                else None
            ),
            "human_time_s": round(self.human_time_s, 6),
            "human_time_source": self.human_time_source,
            "human_interactions": self.human_interactions,
            "monetary_cost_usd": (
                round(self.monetary_cost_usd, 6)
                if self.monetary_cost_usd is not None
                else None
            ),
        }


@dataclass
class ObservationAcquisitionRecord:
    timestep: int
    sensors_queried: int
    raw_bytes: int
    stored_bytes: int
    acquisition_ops: int
    acquisition_modeled_joules: float
    information_gain_nats: Optional[float] = None
    action_changed: bool = False


@dataclass
class PredictionSyncRecord:
    timestep: int
    horizon_tau: int
    tolerance_eps: float
    permitted_delta: float
    predicted_value: float
    realized_value: float
    error: float
    violated_bound: bool
    canary_state: str  # "safe", "unsafe", "unknown"
    guarantee_type: str  # "empirical", "distributional", "restricted_worst_case"


@dataclass
class TimespaceMovementRecord:
    timestep: int
    divergence_metric: str  # e.g. "sqrt_jsd", "l2_predictive", "kl_gaussian"
    divergence_value: float
    information_gain_nats: float
    update_ops: int
    action_changed: bool


@dataclass
class HumanInterventionRecord:
    timestep: int
    source_id: str
    contribution_kind: str  # "witness", "structural_hint", "renegotiation", "authorization", "correction"
    human_time_s: float
    simulated: bool
    validation_ops: int
    accepted: bool
    validity_condition: str
    machine_ops_avoided: int = 0
    notes: str = ""


@dataclass
class InterfaceVersionRecord:
    timestep: int
    backend_version: str
    api_version: str
    semantic_change_detected: bool
    authorized: bool
    translation_ops: int


@dataclass
class KnowledgeInvalidationRecord:
    timestep: int
    affected_capability: str
    cause: str
    relearning_human_time_s: float
    recovery_interactions: int
    simulated: bool = True
    avoidable: Optional[bool] = None


@dataclass
class SavingsAttributionRecord:
    timestep: int
    source_contract_or_hint_id: str
    machine_ops_avoided: int
    validation_and_guard_ops: int
    modeled_joules_saved: float
    assumptions: List[str] = field(default_factory=list)


class ExtendedTelemetryLedger:
    """Optional structured v0.2 telemetry store preserving strict unit separation."""

    def __init__(
        self,
        experiment_version: str = "v0.2",
        human_time_source: str = "simulated_human_model",
    ) -> None:
        self.experiment_version = experiment_version
        self.totals = UnitSeparatedTotals(human_time_source=human_time_source)
        self.observations: List[ObservationAcquisitionRecord] = []
        self.predictions: List[PredictionSyncRecord] = []
        self.timespace_moves: List[TimespaceMovementRecord] = []
        self.human_interventions: List[HumanInterventionRecord] = []
        self.interface_versions: List[InterfaceVersionRecord] = []
        self.knowledge_invalidations: List[KnowledgeInvalidationRecord] = []
        self.savings_attributions: List[SavingsAttributionRecord] = []

    def add_human_intervention(self, rec: HumanInterventionRecord) -> None:
        self.human_interventions.append(rec)
        self.totals.human_time_s += rec.human_time_s
        self.totals.human_interactions += 1
        self.totals.operation_counts += rec.validation_ops

    def add_knowledge_invalidation(self, rec: KnowledgeInvalidationRecord) -> None:
        self.knowledge_invalidations.append(rec)
        self.totals.human_time_s += rec.relearning_human_time_s
        self.totals.human_interactions += rec.recovery_interactions

    def add_prediction_sync(self, rec: PredictionSyncRecord) -> None:
        self.predictions.append(rec)

    def sync_coverage_summary(self) -> Dict[str, Any]:
        """Compute empirical error coverage and explicitly test whether delta budget is satisfied."""
        if not self.predictions:
            return {"count": 0, "violation_rate": None, "sync_budget_satisfied": None}
        n = len(self.predictions)
        viols = sum(1 for p in self.predictions if p.violated_bound)
        rate = viols / n
        target_delta = self.predictions[-1].permitted_delta
        unknown_cnt = sum(1 for p in self.predictions if p.canary_state == "unknown")
        return {
            "count": n,
            "violations": viols,
            "empirical_violation_rate": round(rate, 6),
            "empirical_coverage": round(1.0 - rate, 6),
            "permitted_delta": target_delta,
            "sync_budget_satisfied": rate <= target_delta,
            "unknown_state_steps": unknown_cnt,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "experiment_version": self.experiment_version,
            "unit_separated_totals": self.totals.to_dict(),
            "counts": {
                "observations": len(self.observations),
                "predictions": len(self.predictions),
                "timespace_moves": len(self.timespace_moves),
                "human_interventions": len(self.human_interventions),
                "interface_versions": len(self.interface_versions),
                "knowledge_invalidations": len(self.knowledge_invalidations),
                "savings_attributions": len(self.savings_attributions),
            },
            "predictive_sync": self.sync_coverage_summary(),
        }
