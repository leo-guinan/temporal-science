"""CRR v0.2 structural, dependency-impact, build-reproducibility, verification, and tiered release-gate tests."""

from __future__ import annotations

from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import research as crr  # type: ignore


def test_crr_validate_all_claims_and_papers() -> None:
    ok, errors, warnings = crr.validate_repository()
    assert ok, f"CRR validation errors: {errors}"
    assert len(crr.load_all_claims()) == 16
    assert len(crr.load_all_papers()) == 5


def test_crr_impact_query_traces_across_all_five_papers() -> None:
    impact = crr.compute_impact("TS-001")
    assert "TS-002" in impact["direct_dependents"]
    assert "TS-CERTIFIED-REUSE" in impact["direct_dependents"]
    assert "TS-TRANSFER-CERTIFICATE" in impact["all_downstream_claims"]
    assert "TS-WORK-NOT-DONE" in impact["all_downstream_claims"]
    assert "TS-PROOF-OF-CREATOR" in impact["all_downstream_claims"]
    assert impact["affected_papers"] == ["paper-01", "paper-02", "paper-03", "paper-04", "paper-05"]


def test_crr_reproducible_paper_build_verify_and_ro_crate() -> None:
    m1 = crr.build_paper("paper-01")
    m2 = crr.build_paper("paper-01")
    assert m1["build_fingerprint_sha256"] == m2["build_fingerprint_sha256"]
    assert len(m1["pinned_artifacts"]) >= 12
    build_dir = REPO_ROOT / "papers" / "01-certified-reuse" / "build"
    assert (build_dir / "manifest.json").exists()
    assert (build_dir / "ro-crate-metadata.json").exists()
    assert (build_dir / "evidence-appendix.md").exists()
    crate = json.loads((build_dir / "ro-crate-metadata.json").read_text(encoding="utf-8"))
    assert crate["@context"] == "https://w3id.org/ro/crate/1.1/context"

    ok, errs = crr.verify_build("paper-01")
    assert ok, f"verify_build failed unexpectedly: {errs}"


def test_crr_tiered_release_gates_separate_scoped_preprint_from_unmet_tiers() -> None:
    # Paper I passes technical_report and scoped_preprint (operation counts + modeled_proxy energy)
    r_tr, _, b_tr = crr.check_release_gate("paper-01", tier="technical_report")
    assert r_tr is True and b_tr == []

    r_sp, note_sp, b_sp = crr.check_release_gate("paper-01", tier="scoped_preprint")
    assert r_sp is True and b_sp == []
    assert "modeled_proxy" in note_sp

    # Paper I still honestly blocks energy_focused_paper and independently_validated_release
    r_ef, _, b_ef = crr.check_release_gate("paper-01", tier="energy_focused_paper")
    assert r_ef is False
    assert any("energy" in b.lower() for b in b_ef)

    r_iv, _, b_iv = crr.check_release_gate("paper-01", tier="independently_validated_release")
    assert r_iv is False
    assert len(b_iv) >= 1

    # Paper IV passes technical_report but blocks scoped_preprint pending real human studies
    r4_tr, _, _ = crr.check_release_gate("paper-04", tier="technical_report")
    assert r4_tr is True
    r4_sp, _, b4_sp = crr.check_release_gate("paper-04", tier="scoped_preprint")
    assert r4_sp is False
    assert any("human" in b.lower() for b in b4_sp)
