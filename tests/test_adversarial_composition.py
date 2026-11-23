"""Adversarial scientific-composition and artifact-integrity test suite for CRR v0.2.

Each test constructs an isolated synthetic CRR repository in `tmp_path` with a
deliberate scientific or integrity violation and asserts that `validate_repository`
or `verify_build` rejects it with the exact expected diagnostic code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import sys
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import research as crr  # type: ignore


def _write_claim(repo: Path, cid: str, overrides: Dict[str, Any] | None = None) -> None:
    artifact = repo / "artifacts" / f"{cid}.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(f"evidence for {cid}\n", encoding="utf-8")

    claim: Dict[str, Any] = {
        "id": cid,
        "version": "0.1.0",
        "title": f"Claim {cid}",
        "kind": "theorem",
        "status": "formally_proved_under_assumptions",
        "paper_id": "paper-test",
        "statement": f"Statement of {cid}.",
        "assumptions": ["Explicit assumption A."],
        "depends_on": [],
        "evidence": {
            "proofs": [f"artifacts/{cid}.txt"],
            "experiments": [f"artifacts/{cid}.txt"],
            "counterexamples": [],
        },
        "guarantee": {
            "type": "restricted_worst_case",
            "scope": "bounded_deterministic_dags",
            "energy_evidence_tier": "modeled_proxy_energy",
        },
        "validity": {
            "requirements": ["Exact input match"],
            "invalidation_conditions": ["Hidden mutation"],
        },
        "provenance": {
            "contributors": ["adversarial-test"],
            "source_artifacts": [f"artifacts/{cid}.txt"],
        },
        "limitations": ["Synthetic test claim."],
    }
    if overrides:
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(claim.get(k), dict):
                claim[k].update(v)
            else:
                claim[k] = v

    cdir = repo / "research" / "claims" / cid
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "claim.yaml").write_text(yaml.safe_dump(claim, sort_keys=False), encoding="utf-8")


def _write_paper(repo: Path, paper_id: str, claims: List[str], exported: str) -> None:
    pdir = repo / "papers" / paper_id
    pdir.mkdir(parents=True, exist_ok=True)
    paper = {
        "id": paper_id,
        "version": "0.1.0",
        "title": f"Test Paper {paper_id}",
        "exported_contract": exported,
        "claims": claims,
        "imports": [],
        "reference_experiments": [],
        "publication_gate": {
            "tiers": {
                "technical_report": {"ready": True, "scope_note": "ok"},
                "scoped_preprint": {"ready": True, "scope_note": "ok"},
                "energy_focused_paper": {"ready": False, "blockers": ["No RAPL"]},
                "independently_validated_release": {"ready": False, "blockers": ["No external replication"]},
            }
        },
    }
    (pdir / "paper.yaml").write_text(yaml.safe_dump(paper, sort_keys=False), encoding="utf-8")


def test_rejects_invalidated_and_contradicted_upstream_dependencies(tmp_path: Path) -> None:
    _write_claim(tmp_path, "C-UP", {"status": "invalidated"})
    _write_claim(
        tmp_path,
        "C-DOWN",
        {
            "status": "empirically_supported",
            "depends_on": [{"id": "C-UP", "version": "0.1.0"}],
        },
    )
    _write_paper(tmp_path, "paper-test", ["C-UP", "C-DOWN"], "C-DOWN")

    ok, errors, _ = crr.validate_repository(tmp_path)
    assert not ok
    assert any("INVALID_UPSTREAM_STATUS" in e for e in errors)


def test_rejects_formal_status_inflation(tmp_path: Path) -> None:
    _write_claim(tmp_path, "C-CONJ", {"kind": "empirical_finding", "status": "empirically_supported"})
    _write_claim(
        tmp_path,
        "C-THM",
        {
            "kind": "theorem",
            "status": "formally_proved_under_assumptions",
            "depends_on": [{"id": "C-CONJ", "version": "0.1.0"}],
        },
    )
    _write_paper(tmp_path, "paper-test", ["C-CONJ", "C-THM"], "C-THM")

    ok, errors, _ = crr.validate_repository(tmp_path)
    assert not ok
    assert any("FORMAL_STATUS_INFLATION" in e for e in errors)


def test_rejects_silent_energy_tier_inflation_unless_hardware_metered(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        "C-PROXY",
        {
            "status": "empirically_supported",
            "guarantee": {"energy_evidence_tier": "modeled_proxy_energy"},
        },
    )
    _write_claim(
        tmp_path,
        "C-PHYS-BAD",
        {
            "status": "empirically_supported",
            "depends_on": [{"id": "C-PROXY", "version": "0.1.0"}],
            "guarantee": {"energy_evidence_tier": "physically_measured_energy"},
        },
    )
    _write_paper(tmp_path, "paper-test", ["C-PROXY", "C-PHYS-BAD"], "C-PHYS-BAD")

    ok, errors, _ = crr.validate_repository(tmp_path)
    assert not ok
    assert any("ENERGY_TIER_INFLATION" in e for e in errors)

    # Explicitly setting hardware_energy_metered=True clears S3
    _write_claim(
        tmp_path,
        "C-PHYS-BAD",
        {
            "status": "empirically_supported",
            "depends_on": [{"id": "C-PROXY", "version": "0.1.0"}],
            "guarantee": {
                "energy_evidence_tier": "physically_measured_energy",
                "hardware_energy_metered": True,
            },
        },
    )
    ok_fixed, errors_fixed, _ = crr.validate_repository(tmp_path)
    assert ok_fixed, f"Expected pass when hardware_energy_metered=True, got: {errors_fixed}"


def test_rejects_simulated_human_scope_misuse(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        "C-SIM",
        {
            "kind": "causal_hypothesis",
            "status": "partially_supported",
            "guarantee": {"scope": "simulated_human_agents_only"},
        },
    )
    _write_claim(
        tmp_path,
        "C-REAL",
        {
            "kind": "causal_hypothesis",
            "status": "partially_supported",
            "depends_on": [{"id": "C-SIM", "version": "0.1.0"}],
            "guarantee": {"scope": "real_human_subjects_clinical"},
        },
    )
    _write_paper(tmp_path, "paper-test", ["C-SIM", "C-REAL"], "C-REAL")

    ok, errors, _ = crr.validate_repository(tmp_path)
    assert not ok
    assert any("SCOPE_MISUSE" in e for e in errors)


def test_rejects_guarantee_inflation(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        "C-RESTR",
        {"guarantee": {"type": "restricted_worst_case"}},
    )
    _write_claim(
        tmp_path,
        "C-GEN",
        {
            "depends_on": [{"id": "C-RESTR", "version": "0.1.0"}],
            "guarantee": {"type": "general_worst_case"},
        },
    )
    _write_paper(tmp_path, "paper-test", ["C-RESTR", "C-GEN"], "C-GEN")

    ok, errors, _ = crr.validate_repository(tmp_path)
    assert not ok
    assert any("GUARANTEE_INFLATION" in e for e in errors)


def test_rejects_circular_dependencies_and_version_mismatch(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        "C-A",
        {"depends_on": [{"id": "C-B", "version": "0.1.0"}]},
    )
    _write_claim(
        tmp_path,
        "C-B",
        {"depends_on": [{"id": "C-A", "version": "9.9.9"}]},
    )
    _write_paper(tmp_path, "paper-test", ["C-A", "C-B"], "C-A")

    ok, errors, _ = crr.validate_repository(tmp_path)
    assert not ok
    assert any("CIRCULAR_DEPENDENCY" in e for e in errors)
    assert any("VERSION_MISMATCH" in e for e in errors)


def test_verify_build_detects_single_byte_artifact_tampering(tmp_path: Path) -> None:
    _write_claim(tmp_path, "C-OK", {})
    _write_paper(tmp_path, "paper-test", ["C-OK"], "C-OK")

    crr.build_paper("paper-test", repo_root=tmp_path)
    ok_before, errs_before = crr.verify_build("paper-test", repo_root=tmp_path)
    assert ok_before, f"Expected clean verify_build, got {errs_before}"

    # Tamper with 1 byte of the pinned evidence artifact
    target = tmp_path / "artifacts" / "C-OK.txt"
    target.write_text(target.read_text(encoding="utf-8") + "!", encoding="utf-8")

    ok_after, errs_after = crr.verify_build("paper-test", repo_root=tmp_path)
    assert not ok_after
    assert any("ARTIFACT_TAMPERED" in e for e in errs_after)
