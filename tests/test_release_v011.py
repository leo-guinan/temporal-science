"""Automated integrity tests for immutable release `v0.1.1-external-season-1`."""

from __future__ import annotations

from pathlib import Path
import hashlib
import tarfile

REPO_ROOT = Path(__file__).resolve().parents[1]
REL_DIR = REPO_ROOT / "release" / "v0.1.1-external-season-1"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_release_v011_artifacts_checksums_and_honest_disclosures() -> None:
    assert REL_DIR.is_dir(), "Run release/stage_release_v0_1_1.py first"
    sums_p = REL_DIR / "SHA256SUMS.txt"
    assert sums_p.exists()

    expected_files = {
        "CITATION.cff",
        "RELEASE_NOTES.md",
        "challenge-kit-v1.1.0.tar.gz",
        "exp_hw04-methodological-audit.json",
        "exp_hw04-report.md",
        "paper-01-manuscript.md",
        "paper-01-v0.1.0-portable.tar.gz",
        "prospective-energy-protocol-v1.md",
        "prospective-energy-protocol-v1.yaml",
        "prospectus.md",
        "raw-results-v0.1.1.tar.gz",
    }

    # Verify every entry in SHA256SUMS.txt matches disk byte-for-byte
    seen = set()
    for line in sums_p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, fname = line.split("  ", 1)
        fpath = REL_DIR / fname
        assert fpath.exists(), f"Missing release file listed in SHA256SUMS.txt: {fname}"
        assert _sha256(fpath) == digest, f"SHA-256 mismatch on release artifact: {fname}"
        seen.add(fname)
    assert seen == expected_files

    # Verify challenge-kit-v1.1.0.tar.gz uses versioned root directory (never silently overwriting v1)
    with tarfile.open(REL_DIR / "challenge-kit-v1.1.0.tar.gz", "r:gz") as tf:
        names = tf.getnames()
        assert any(n == "challenge-kit-v1.1.0/challenge_runner.py" for n in names)

    # Verify RELEASE_NOTES explicitly separates internal tests from independent external replication
    notes = (REL_DIR / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "do not constitute independent external replication" in notes
    assert "BLOCKED" in notes
    assert "challenge-kit-v1.1.0.tar.gz" in notes
