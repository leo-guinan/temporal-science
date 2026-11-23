"""Unified v0.3 Evidence Architecture & Three Separate Value Ledgers (§11 & §12).

Implements:
  - Deterministic canonical JSON serialization + SHA-256 content addressing + HMAC provenance
  - Three strictly separated ledgers (preventing double-counting & speculative conflation):
      A. PerformedWorkLedger (Creation Ledger)
      B. WorkNotDoneLedger (Realized Avoidance Ledger, with explicit non-equivalent ClaimTiers)
      C. ComputationalOptionalityLedger (Option Ledger — never merged with realized savings)
  - Versioned certificates: TransferCertificate, WorkNotDoneCertificate
  - Content-addressed CausalEvidenceGraph & ProofOfCreatorFingerprint verifier

Note on cryptographic scope (P15 / LC-23):
  SHA-256 + canonical JSON provide reproducible commitments and tamper detection under
  standard collision-resistance assumptions. They do NOT by themselves establish empirical
  truth, legal ownership, or real-world human identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
import hashlib
import hmac
import json


def canonical_json(obj: Any) -> str:
    """Deterministic UTF-8 canonical JSON serialization (sorted keys, compact separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_canonical(obj: Any) -> str:
    """SHA-256 hex digest of the canonical JSON representation of `obj`."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def hmac_authenticate(secret_key: str, payload_digest: str) -> str:
    """Standard HMAC-SHA256 provenance tag binding a contributor key to a payload digest."""
    return hmac.new(
        secret_key.encode("utf-8"),
        payload_digest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class ClaimTier(str, Enum):
    """Non-equivalent Work Not Done verification tiers (LC-22 / Experiment 13)."""

    REPLAY_MEASURED = "replay_measured"
    STATISTICALLY_ESTIMATED = "statistically_estimated"
    MATHEMATICALLY_BOUNDED = "mathematically_bounded"


class ProofKind(str, Enum):
    """Three separate forms of proof (§11) — never conflated."""

    EXECUTION_PROOF = "execution_proof"
    VALIDITY_PROOF = "validity_proof"
    VALUE_EVIDENCE = "value_evidence"


# ---------------------------------------------------------------------------
# A. Performed Work Ledger (Creation Ledger)
# ---------------------------------------------------------------------------

@dataclass
class PerformedWorkEntry:
    entry_id: str
    contributor_id: str
    work_description: str
    input_commitment: str
    output_commitment: str
    start_step: int
    end_step: int
    machine_ops: int
    modeled_joules: float
    simulated_human_time_s: float = 0.0
    physical_joules: Optional[float] = None
    verified: bool = True
    resulting_capability_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PerformedWorkLedger:
    """Records resources expended to create, validate, or maintain capabilities."""

    def __init__(self, version: str = "v0.3") -> None:
        self.version = version
        self.entries: List[PerformedWorkEntry] = []

    def record(self, entry: PerformedWorkEntry) -> PerformedWorkEntry:
        self.entries.append(entry)
        return entry

    def summary(self) -> Dict[str, Any]:
        return {
            "ledger_type": "performed_work_creation_ledger",
            "version": self.version,
            "entry_count": len(self.entries),
            "total_machine_ops": sum(e.machine_ops for e in self.entries),
            "total_modeled_joules": round(sum(e.modeled_joules for e in self.entries), 9),
            "total_simulated_human_time_s": round(
                sum(e.simulated_human_time_s for e in self.entries), 4
            ),
            "physical_joules_measured": any(e.physical_joules is not None for e in self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# B. Work Not Done Ledger & Certificate (Realized Avoidance Ledger)
# ---------------------------------------------------------------------------

@dataclass
class WorkNotDoneCertificate:
    """Versioned counterfactual certificate establishing verified Work Not Done (Exp 13)."""

    certificate_id: str
    version: str
    workload_id: str
    workload_commitment: str
    capability_id: str
    baseline_name: str
    improved_system_name: str
    required_outcome_spec: str
    outcome_equivalent: bool
    claim_tier: ClaimTier
    # Complete multi-channel baseline costs
    baseline_machine_ops: int
    baseline_modeled_joules: float
    baseline_human_time_s: float
    # Complete multi-channel improved system costs (explicit breakdown — no hidden overhead!)
    actual_exec_ops: int
    actual_preprocessing_ops: int
    actual_learning_ops: int
    actual_guarding_ops: int
    actual_maintenance_ops: int
    actual_deferred_ops: int
    actual_modeled_joules: float
    actual_human_time_s: float
    # Measurement metadata & contract bounds
    measurement_method: str
    uncertainty_margin_ops: float
    contract_valid: bool
    contract_expired: bool
    constraints_dropped: int = 0
    validity_assumptions: List[str] = field(default_factory=list)
    expiration_rule: str = "Invalidated upon assumption violation or schema drift"
    # Verification verdict populated by verifier
    verified: Optional[bool] = None
    rejection_reasons: List[str] = field(default_factory=list)
    certificate_digest: Optional[str] = None

    @property
    def total_actual_machine_ops(self) -> int:
        return (
            self.actual_exec_ops
            + self.actual_preprocessing_ops
            + self.actual_learning_ops
            + self.actual_guarding_ops
            + self.actual_maintenance_ops
            + self.actual_deferred_ops
        )

    @property
    def net_wnd_machine_ops(self) -> int:
        return self.baseline_machine_ops - self.total_actual_machine_ops

    @property
    def net_wnd_modeled_joules(self) -> float:
        return self.baseline_modeled_joules - self.actual_modeled_joules

    @property
    def net_wnd_human_time_s(self) -> float:
        return self.baseline_human_time_s - self.actual_human_time_s

    def canonical_payload(self) -> Dict[str, Any]:
        d = asdict(self)
        d["claim_tier"] = self.claim_tier.value
        d.pop("verified", None)
        d.pop("rejection_reasons", None)
        d.pop("certificate_digest", None)
        return d

    def compute_digest(self) -> str:
        return sha256_canonical(self.canonical_payload())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["claim_tier"] = self.claim_tier.value
        d["total_actual_machine_ops"] = self.total_actual_machine_ops
        d["net_wnd_machine_ops"] = self.net_wnd_machine_ops
        d["net_wnd_modeled_joules"] = round(self.net_wnd_modeled_joules, 9)
        d["net_wnd_human_time_s"] = round(self.net_wnd_human_time_s, 4)
        return d


class WorkNotDoneLedger:
    """Tracks only verified realized counterfactual work avoided (strictly separate from option value)."""

    def __init__(self, version: str = "v0.3") -> None:
        self.version = version
        self.certificates: List[WorkNotDoneCertificate] = []

    def record(self, cert: WorkNotDoneCertificate) -> WorkNotDoneCertificate:
        self.certificates.append(cert)
        return cert

    def summary(self) -> Dict[str, Any]:
        verified_certs = [c for c in self.certificates if c.verified is True]
        return {
            "ledger_type": "realized_work_not_done_ledger",
            "version": self.version,
            "total_certificates": len(self.certificates),
            "verified_certificates": len(verified_certs),
            "rejected_certificates": sum(1 for c in self.certificates if c.verified is False),
            "verified_net_wnd_machine_ops": sum(c.net_wnd_machine_ops for c in verified_certs),
            "verified_net_wnd_modeled_joules": round(
                sum(c.net_wnd_modeled_joules for c in verified_certs), 9
            ),
            "verified_net_wnd_human_time_s": round(
                sum(c.net_wnd_human_time_s for c in verified_certs), 4
            ),
            "by_claim_tier": {
                tier.value: sum(
                    c.net_wnd_machine_ops for c in verified_certs if c.claim_tier is tier
                )
                for tier in ClaimTier
            },
        }


# ---------------------------------------------------------------------------
# C. Computational Optionality Ledger (Option Ledger — strictly separated!)
# ---------------------------------------------------------------------------

@dataclass
class OptionalityEntry:
    option_id: str
    enabling_capability_id: str
    newly_feasible_task_ids: List[str]
    previously_binding_constraints: List[str]
    future_required_ops: int
    maintenance_ops: int
    expected_option_value: float  # V*(K U {h}, B) - V*(K, B) under explicit decision model
    uncertainty_low: float
    uncertainty_high: float
    utility_model_description: str
    realized_value: Optional[float] = None
    expired: bool = False
    expiration_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ComputationalOptionalityLedger:
    """Tracks newly feasible future actions and conservative modeled option values.

    NEVER merged into verified realized savings!
    """

    def __init__(self, version: str = "v0.3") -> None:
        self.version = version
        self.entries: List[OptionalityEntry] = []

    def record(self, entry: OptionalityEntry) -> OptionalityEntry:
        self.entries.append(entry)
        return entry

    def summary(self) -> Dict[str, Any]:
        active = [e for e in self.entries if not e.expired]
        realized = [e.realized_value for e in self.entries if e.realized_value is not None]
        return {
            "ledger_type": "computational_optionality_ledger_SPECULATIVE_SEPARATE",
            "version": self.version,
            "entry_count": len(self.entries),
            "active_options": len(active),
            "expired_options": len(self.entries) - len(active),
            "total_newly_feasible_tasks": sum(len(e.newly_feasible_task_ids) for e in self.entries),
            "modeled_expected_option_value": round(sum(e.expected_option_value for e in active), 4),
            "modeled_uncertainty_band": [
                round(sum(e.uncertainty_low for e in active), 4),
                round(sum(e.uncertainty_high for e in active), 4),
            ],
            "realized_value_from_executed_options": round(sum(realized), 4),
            "entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Transfer Certificate (Experiment 12)
# ---------------------------------------------------------------------------

@dataclass
class TransferCertificate:
    certificate_id: str
    version: str
    capability_id: str
    source_institution: str
    destination_institution: str
    transfer_category: str  # "T1_syntactic", "T2_semantic", "T3_structural_drift", "T4_institutional_enclosure"
    task_semantics: str
    source_assumptions: List[str]
    destination_requirements: List[str]
    translation_evidence: str
    validity_status: str  # "safe", "unsafe", "unknown"
    translation_ops: int
    validation_ops: int
    human_adaptation_s: float
    net_ops_avoided: int
    external_prediction_error: Optional[float] = None
    failure_boundary_notes: str = ""
    certificate_digest: Optional[str] = None

    def seal(self) -> str:
        payload = asdict(self)
        payload.pop("certificate_digest", None)
        self.certificate_digest = sha256_canonical(payload)
        return self.certificate_digest

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Content-Addressed Causal Evidence Graph & Proof of Creator Fingerprint (Exp 14)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceNode:
    node_id: str
    stage: str  # "contribution", "trace", "capability", "contract", "reuse", "wnd_certificate", "attribution", "invalidation", "optionality"
    proof_kind: str  # ProofKind value
    contributor_id: str
    timestamp_step: int
    payload: Dict[str, Any]
    parent_ids: List[str] = field(default_factory=list)
    parent_digests: List[str] = field(default_factory=list)
    digest: str = ""
    auth_signature: str = ""

    def compute_digest(self) -> str:
        body = {
            "node_id": self.node_id,
            "stage": self.stage,
            "proof_kind": self.proof_kind,
            "contributor_id": self.contributor_id,
            "timestamp_step": self.timestamp_step,
            "payload": self.payload,
            "parent_ids": sorted(self.parent_ids),
            "parent_digests": sorted(self.parent_digests),
        }
        return sha256_canonical(body)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CausalEvidenceGraph:
    """Content-addressed acyclic evidence graph with deterministic Proof of Creator fingerprinting."""

    def __init__(self, graph_id: str, version: str = "v0.3") -> None:
        self.graph_id = graph_id
        self.version = version
        self.nodes: Dict[str, EvidenceNode] = {}
        self._order: List[str] = []

    def add_node(
        self,
        node_id: str,
        stage: str,
        proof_kind: ProofKind,
        contributor_id: str,
        timestamp_step: int,
        payload: Dict[str, Any],
        parent_ids: Optional[Sequence[str]] = None,
        contributor_secret: Optional[str] = None,
    ) -> EvidenceNode:
        if node_id in self.nodes:
            raise ValueError(f"Duplicate evidence node_id: {node_id}")
        pids = sorted(parent_ids) if parent_ids else []
        p_digests: List[str] = []
        for pid in pids:
            if pid not in self.nodes:
                raise ValueError(f"Missing parent evidence node: {pid}")
            p_digests.append(self.nodes[pid].digest)

        node = EvidenceNode(
            node_id=node_id,
            stage=stage,
            proof_kind=proof_kind.value,
            contributor_id=contributor_id,
            timestamp_step=timestamp_step,
            payload=payload,
            parent_ids=pids,
            parent_digests=p_digests,
        )
        node.digest = node.compute_digest()
        if contributor_secret is not None:
            node.auth_signature = hmac_authenticate(contributor_secret, node.digest)
        self.nodes[node_id] = node
        self._order.append(node_id)
        return node

    def compute_fingerprint(self) -> str:
        """Canonical root SHA-256 Proof of Creator fingerprint over the entire evidence graph."""
        ordered_digests = [self.nodes[nid].digest for nid in sorted(self.nodes.keys())]
        return sha256_canonical(
            {
                "graph_id": self.graph_id,
                "version": self.version,
                "node_digests": ordered_digests,
            }
        )

    def verify_integrity(
        self, contributor_keys: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, List[str]]:
        """Independently verify every node digest, parent link, and contributor HMAC tag."""
        errors: List[str] = []
        for nid in self._order:
            node = self.nodes[nid]
            # 1. Verify parent links & parent digest bindings
            expected_p_digests: List[str] = []
            for pid in sorted(node.parent_ids):
                if pid not in self.nodes:
                    errors.append(f"Node {nid} references missing parent {pid}")
                else:
                    expected_p_digests.append(self.nodes[pid].digest)
            if sorted(node.parent_digests) != sorted(expected_p_digests):
                errors.append(f"Node {nid} parent digest mismatch (upstream tampering detected)")

            # 2. Recompute node canonical SHA-256 digest
            recomputed = node.compute_digest()
            if node.digest != recomputed:
                errors.append(f"Node {nid} digest mismatch (payload tampering detected)")

            # 3. Verify HMAC provenance if contributor keys supplied
            if contributor_keys is not None and node.auth_signature:
                key = contributor_keys.get(node.contributor_id)
                if key is None:
                    errors.append(f"Node {nid} has unknown contributor_id {node.contributor_id}")
                else:
                    expected_sig = hmac_authenticate(key, node.digest)
                    if not hmac.compare_digest(node.auth_signature, expected_sig):
                        errors.append(f"Node {nid} invalid provenance signature (forgery/misattribution)")

        return len(errors) == 0, errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "version": self.version,
            "fingerprint_sha256": self.compute_fingerprint(),
            "node_count": len(self.nodes),
            "nodes": [self.nodes[nid].to_dict() for nid in self._order],
        }
