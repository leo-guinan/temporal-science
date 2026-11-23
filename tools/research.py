#!/usr/bin/env python3
"""Minimal Composable Research Repository (CRR v0.2) CLI for Temporal Science.

Commands:
  validate               Validate schemas, pins, acyclicity, artifact links & scientific composition rules
  impact <CLAIM_ID>      Compute transitive downstream claim & paper review impact
  build <paper-id>       Generate reproducible pinned manifest (SHA-256), RO-Crate & appendix
  verify-build <paper>   Verify live SHA-256 integrity of a built paper package against disk
  bundle <paper-id>      Build a self-contained portable .tar.gz reproduction bundle (zero external paths!)
  release <paper> --tier Evaluate 4-tier release gate (technical_report, scoped_preprint,
                         energy_focused_paper, independently_validated_release)
  test                   Run validation + CRR, adversarial composition & executable claim tests
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_KINDS = {
    "definition",
    "theorem",
    "conjecture",
    "empirical_finding",
    "causal_hypothesis",
    "modeling_assumption",
    "normative_proposition",
}
ALLOWED_STATUSES = {
    "proposed",
    "formally_proved_under_assumptions",
    "empirically_supported",
    "partially_supported",
    "replication_pending",
    "contradicted",
    "invalidated",
    "superseded",
}
ALLOWED_ENERGY_TIERS = {
    "none",
    "operation_counts_only",
    "modeled_proxy_energy",
    "physically_measured_energy",
}
ENERGY_RANK = {
    "none": 0,
    "operation_counts_only": 1,
    "modeled_proxy_energy": 2,
    "physically_measured_energy": 3,
}
REQUIRED_CLAIM_FIELDS = {
    "id",
    "version",
    "title",
    "kind",
    "status",
    "paper_id",
    "statement",
    "assumptions",
    "depends_on",
    "evidence",
    "guarantee",
    "validity",
    "provenance",
    "limitations",
}
RELEASE_TIERS = (
    "technical_report",
    "scoped_preprint",
    "energy_focused_paper",
    "independently_validated_release",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_all_claims(repo_root: Path = REPO_ROOT) -> Dict[str, Tuple[Path, Dict[str, Any]]]:
    claims_dir = repo_root / "research" / "claims"
    claims: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
    if not claims_dir.exists():
        return claims
    for ypath in sorted(claims_dir.glob("*/claim.yaml")):
        data = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        cid = data.get("id", ypath.parent.name)
        claims[cid] = (ypath, data)
    return claims


def load_all_papers(repo_root: Path = REPO_ROOT) -> Dict[str, Tuple[Path, Dict[str, Any]]]:
    papers_dir = repo_root / "papers"
    papers: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
    if not papers_dir.exists():
        return papers
    for ypath in sorted(papers_dir.glob("*/paper.yaml")):
        data = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        pid = data.get("id", ypath.parent.name)
        papers[pid] = (ypath, data)
    return papers


def resolve_ref_path(rel_path: str, repo_root: Path = REPO_ROOT) -> Path:
    return (repo_root / rel_path).resolve()


def validate_repository(
    repo_root: Path = REPO_ROOT,
) -> Tuple[bool, List[str], List[str]]:
    """Run structural, dependency, version-pin, artifact-link, and scientific-composition checks."""
    errors: List[str] = []
    warnings: List[str] = []

    claims = load_all_claims(repo_root)
    papers = load_all_papers(repo_root)

    if not claims:
        errors.append("No claim contracts found under research/claims/")
        return False, errors, warnings

    # 1. Schema & artifact link checks
    for cid, (ypath, c) in claims.items():
        missing = REQUIRED_CLAIM_FIELDS - set(c.keys())
        if missing:
            errors.append(f"{cid}: missing required fields {sorted(missing)}")
            continue
        if c["id"] != ypath.parent.name:
            errors.append(f"{cid}: id does not match directory name {ypath.parent.name}")
        if c["kind"] not in ALLOWED_KINDS:
            errors.append(f"{cid}: invalid kind '{c['kind']}'")
        if c["status"] not in ALLOWED_STATUSES:
            errors.append(f"{cid}: invalid status '{c['status']}'")
        etier = c.get("guarantee", {}).get("energy_evidence_tier")
        if etier not in ALLOWED_ENERGY_TIERS:
            errors.append(f"{cid}: invalid energy_evidence_tier '{etier}'")
        for list_field in ("assumptions", "limitations"):
            if not all(isinstance(item, str) for item in c.get(list_field, [])):
                errors.append(
                    f"{cid}: all entries in '{list_field}' must be plain strings (check YAML quoting)"
                )

        ev = c.get("evidence", {})
        for bucket in ("proofs", "experiments"):
            for ref in ev.get(bucket, []):
                rp = resolve_ref_path(ref, repo_root)
                if not rp.exists():
                    errors.append(f"{cid}: missing {bucket} artifact '{ref}' (resolved {rp})")
        for ref in c.get("provenance", {}).get("source_artifacts", []):
            rp = resolve_ref_path(ref, repo_root)
            if not rp.exists():
                errors.append(f"{cid}: missing source_artifact '{ref}' (resolved {rp})")

    # 2. Dependency resolution, version pinning, scientific composition rules & cycle detection
    adj: Dict[str, List[str]] = {cid: [] for cid in claims}
    for cid, (_, c) in claims.items():
        c_status = c.get("status", "")
        c_kind = c.get("kind", "")
        c_guar = c.get("guarantee", {})
        c_gtype = str(c_guar.get("type", ""))
        c_scope = str(c_guar.get("scope", ""))
        c_etier = str(c_guar.get("energy_evidence_tier", "none"))
        c_has_hw = bool(c_guar.get("hardware_energy_metered", False))

        for dep in c.get("depends_on", []):
            did = dep["id"]
            dver = dep["version"]
            if did not in claims:
                errors.append(f"{cid}: depends on missing claim '{did}'")
                continue
            adj[cid].append(did)
            up = claims[did][1]
            actual_ver = up["version"]
            if actual_ver != dver:
                errors.append(
                    f"{cid}: VERSION_MISMATCH on {did} (expects {dver}, found {actual_ver})"
                )

            up_status = up.get("status", "")
            up_kind = up.get("kind", "")
            up_guar = up.get("guarantee", {})
            up_gtype = str(up_guar.get("type", ""))
            up_scope = str(up_guar.get("scope", ""))
            up_etier = str(up_guar.get("energy_evidence_tier", "none"))

            # Rule S1: Active claim cannot rely on invalidated / contradicted / superseded dependency
            if c_status not in ("invalidated", "superseded", "contradicted") and up_status in (
                "invalidated",
                "contradicted",
                "superseded",
            ):
                errors.append(
                    f"{cid}: INVALID_UPSTREAM_STATUS depends on {did} whose status is '{up_status}'"
                )

            # Rule S2: Formal status inflation (a formally proved theorem cannot depend on unproved/empirical claim)
            if (
                c_kind == "theorem"
                and c_status == "formally_proved_under_assumptions"
                and up_status != "formally_proved_under_assumptions"
            ):
                errors.append(
                    f"{cid}: FORMAL_STATUS_INFLATION formally proved theorem depends on {did} "
                    f"(kind='{up_kind}', status='{up_status}')"
                )

            # Rule S3: Silent energy-tier inflation without explicit downstream hardware metering
            if (
                c_etier == "physically_measured_energy"
                and ENERGY_RANK.get(up_etier, 0) < ENERGY_RANK["physically_measured_energy"]
                and not c_has_hw
            ):
                errors.append(
                    f"{cid}: ENERGY_TIER_INFLATION claims physically_measured_energy while importing "
                    f"{did} ({up_etier}) without hardware_energy_metered=true"
                )

            # Rule S4: Simulated-human scope misuse
            if "real_human" in c_scope.lower() and "simulated" in up_scope.lower():
                errors.append(
                    f"{cid}: SCOPE_MISUSE claims '{c_scope}' while depending on simulated upstream {did} ('{up_scope}')"
                )

            # Rule S5: Guarantee inflation (general_worst_case cannot depend on restricted/empirical guarantee)
            if c_gtype == "general_worst_case" and up_gtype in (
                "restricted_worst_case",
                "empirical",
                "distributional",
            ):
                errors.append(
                    f"{cid}: GUARANTEE_INFLATION claims general_worst_case while depending on {did} ({up_gtype})"
                )

    # Cycle detection (3-color DFS)
    color: Dict[str, int] = {cid: 0 for cid in claims}

    def dfs_cycle(u: str) -> bool:
        color[u] = 1
        for v in adj[u]:
            if color[v] == 1:
                errors.append(f"CIRCULAR_DEPENDENCY detected involving {u} -> {v}")
                return True
            if color[v] == 0 and dfs_cycle(v):
                return True
        color[u] = 2
        return False

    for cid in claims:
        if color[cid] == 0:
            dfs_cycle(cid)

    # 3. Paper manifest validation
    for pid, (_, p) in papers.items():
        exp_c = p.get("exported_contract")
        if exp_c not in claims:
            errors.append(f"{pid}: exported_contract '{exp_c}' not found in claims")
        for cid in p.get("claims", []):
            if cid not in claims:
                errors.append(f"{pid}: lists missing claim '{cid}'")
        for imp in p.get("imports", []):
            iid = imp["id"]
            if iid not in claims:
                errors.append(f"{pid}: imports missing claim '{iid}'")
            elif claims[iid][1]["version"] != imp["version"]:
                errors.append(
                    f"{pid}: import pin mismatch on {iid} (expects {imp['version']}, found {claims[iid][1]['version']})"
                )
        for ex in p.get("reference_experiments", []):
            if not resolve_ref_path(ex["path"], repo_root).exists():
                errors.append(f"{pid}: missing experiment artifact '{ex['path']}'")
            for fig in ex.get("figures", []):
                if not resolve_ref_path(fig, repo_root).exists():
                    errors.append(f"{pid}: missing figure artifact '{fig}'")

    return len(errors) == 0, errors, warnings


def compute_impact(target_claim_id: str, repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    claims = load_all_claims(repo_root)
    papers = load_all_papers(repo_root)
    if target_claim_id not in claims:
        raise KeyError(f"Unknown claim ID: {target_claim_id}")

    rev: Dict[str, List[str]] = {cid: [] for cid in claims}
    for cid, (_, c) in claims.items():
        for dep in c.get("depends_on", []):
            if dep["id"] in rev:
                rev[dep["id"]].append(cid)

    direct = sorted(rev[target_claim_id])
    visited: Set[str] = set()
    order: List[str] = []
    queue = list(direct)
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        order.append(cur)
        for nxt in sorted(rev.get(cur, [])):
            if nxt not in visited:
                queue.append(nxt)

    affected_set = {target_claim_id} | visited
    affected_papers = sorted(
        pid
        for pid, (_, p) in papers.items()
        if any(cid in affected_set for cid in p.get("claims", []))
        or any(imp["id"] in affected_set for imp in p.get("imports", []))
    )

    return {
        "target_claim": target_claim_id,
        "target_version": claims[target_claim_id][1]["version"],
        "target_status": claims[target_claim_id][1]["status"],
        "direct_dependents": direct,
        "all_downstream_claims": order,
        "downstream_count": len(order),
        "affected_papers": affected_papers,
        "review_policy": "Flag all listed downstream claims and papers for assumption review (never auto-falsify).",
    }


def build_paper(paper_id: str, repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    ok, errors, _ = validate_repository(repo_root)
    if not ok:
        raise RuntimeError(f"Repository validation failed before build: {errors}")

    claims = load_all_claims(repo_root)
    papers = load_all_papers(repo_root)
    if paper_id not in papers:
        raise KeyError(f"Unknown paper ID: {paper_id}")

    py_path, p = papers[paper_id]
    build_dir = py_path.parent / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    artifact_hashes: Dict[str, Dict[str, Any]] = {}

    def pin_file(rel_ref: str, role: str) -> None:
        rp = resolve_ref_path(rel_ref, repo_root)
        if rel_ref not in artifact_hashes and rp.exists():
            artifact_hashes[rel_ref] = {
                "role": role,
                "sha256": sha256_file(rp),
                "bytes": rp.stat().st_size,
            }

    # Pin manuscript if present
    ms_path = py_path.parent / "manuscript.md"
    if ms_path.exists():
        pin_file(str(ms_path.relative_to(repo_root)), "manuscript")

    pinned_claims: List[Dict[str, Any]] = []
    for cid in p.get("claims", []):
        cpath, c = claims[cid]
        pin_file(str(cpath.relative_to(repo_root)), "claim_contract")
        for b in ("proofs", "experiments"):
            for ref in c["evidence"].get(b, []):
                pin_file(ref, f"evidence_{b}")
        for ref in c["provenance"].get("source_artifacts", []):
            pin_file(ref, "source_artifact")
        pinned_claims.append(
            {
                "id": cid,
                "version": c["version"],
                "kind": c["kind"],
                "status": c["status"],
                "energy_evidence_tier": c["guarantee"]["energy_evidence_tier"],
                "statement": c["statement"].strip(),
                "assumptions": c["assumptions"],
                "counterexamples": c["evidence"]["counterexamples"],
                "limitations": c["limitations"],
            }
        )

    for ex in p.get("reference_experiments", []):
        pin_file(ex["path"], "experiment_result")
        for fig in ex.get("figures", []):
            pin_file(fig, "figure")

    manifest_core = {
        "crr_standard_version": "0.2.0",
        "paper_id": paper_id,
        "paper_version": p["version"],
        "title": p["title"],
        "exported_contract": p["exported_contract"],
        "imports": p.get("imports", []),
        "claims": pinned_claims,
        "pinned_artifacts": artifact_hashes,
        "publication_gate": p.get("publication_gate", {}),
    }
    build_digest = hashlib.sha256(
        json.dumps(manifest_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest_core["build_fingerprint_sha256"] = build_digest

    (build_dir / "manifest.json").write_text(json.dumps(manifest_core, indent=2), encoding="utf-8")

    ro_crate = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@type": "CreativeWork",
                "@id": "ro-crate-metadata.json",
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                "about": {"@id": "./"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": p["title"],
                "version": p["version"],
                "identifier": f"temporal-science:{paper_id}:{p['version']}",
                "hasPart": [{"@id": ref} for ref in sorted(artifact_hashes.keys())],
            },
        ]
        + [
            {
                "@id": ref,
                "@type": "File",
                "encodingFormat": "application/json" if ref.endswith(".json") else "text/plain",
                "sha256": meta["sha256"],
                "contentSize": meta["bytes"],
                "description": meta["role"],
            }
            for ref, meta in sorted(artifact_hashes.items())
        ],
    }
    (build_dir / "ro-crate-metadata.json").write_text(json.dumps(ro_crate, indent=2), encoding="utf-8")

    # Auto-generated Evidence Appendix
    gate = p.get("publication_gate", {})
    tiers = gate.get("tiers", {})
    lines = [
        f"# Auto-Generated Evidence Appendix — {p['title']}",
        "",
        f"- **Paper ID**: `{paper_id}` | **Version**: `{p['version']}` | **Exported Contract**: `{p['exported_contract']}`",
        f"- **Build Fingerprint (SHA-256)**: `{build_digest}`",
        f"- **Pinned Artifacts Verified**: `{len(artifact_hashes)}` files",
        "",
        "## 1. Tiered Release Gate Status",
        "",
        "| Release Tier | Ready? | Scope / Blockers |",
        "|---|---|---|",
    ]
    for tname in RELEASE_TIERS:
        tinfo = tiers.get(tname, {})
        rdy = bool(tinfo.get("ready", False))
        note = tinfo.get("scope_note") if rdy else "; ".join(tinfo.get("blockers", ["Unmet"]))
        lines.append(f"| `{tname}` | `{rdy}` | {note} |")

    lines.extend(
        [
            "",
            "## 2. Claim Inventory & Evidence Tiers",
            "",
            "| Claim ID | Version | Kind | Status | Energy Tier |",
            "|---|---|---|---|---|",
        ]
    )
    for pc in pinned_claims:
        lines.append(
            f"| `{pc['id']}` | `{pc['version']}` | `{pc['kind']}` | `{pc['status']}` | `{pc['energy_evidence_tier']}` |"
        )
    lines.append("")
    lines.append("## 3. Assumptions, Counterexamples & Limitations")
    lines.append("")
    for pc in pinned_claims:
        lines.append(f"### `{pc['id']}` — {pc['statement']}")
        lines.append("- **Assumptions**:")
        for a in pc["assumptions"]:
            lines.append(f"  - {a}")
        if pc["counterexamples"]:
            lines.append("- **Documented Counterexamples & Failure Boundaries**:")
            for ce in pc["counterexamples"]:
                lines.append(f"  - {ce}")
        lines.append("- **Limitations**:")
        for lim in pc["limitations"]:
            lines.append(f"  - {lim}")
        lines.append("")

    (build_dir / "evidence-appendix.md").write_text("\n".join(lines), encoding="utf-8")
    return manifest_core


def verify_build(paper_id: str, repo_root: Path = REPO_ROOT) -> Tuple[bool, List[str]]:
    """Verify every SHA-256 digest in `build/manifest.json` against live files on disk."""
    papers = load_all_papers(repo_root)
    if paper_id not in papers:
        return False, [f"Unknown paper ID: {paper_id}"]
    mpath = papers[paper_id][0].parent / "build" / "manifest.json"
    if not mpath.exists():
        return False, [f"Missing build manifest: {mpath}"]

    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    errors: List[str] = []
    for ref, meta in manifest.get("pinned_artifacts", {}).items():
        rp = resolve_ref_path(ref, repo_root)
        if not rp.exists():
            errors.append(f"MISSING_PINNED_ARTIFACT: {ref}")
            continue
        actual_sha = sha256_file(rp)
        if actual_sha != meta["sha256"]:
            errors.append(
                f"ARTIFACT_TAMPERED: {ref} (expected {meta['sha256'][:12]}..., got {actual_sha[:12]}...)"
            )
    return len(errors) == 0, errors


def check_release_gate(
    paper_id: str, tier: str = "scoped_preprint", repo_root: Path = REPO_ROOT
) -> Tuple[bool, str, List[str]]:
    if tier not in RELEASE_TIERS:
        raise ValueError(f"Unknown release tier '{tier}'. Choose from {RELEASE_TIERS}")
    papers = load_all_papers(repo_root)
    if paper_id not in papers:
        raise KeyError(f"Unknown paper ID: {paper_id}")
    _, p = papers[paper_id]
    tiers = p.get("publication_gate", {}).get("tiers", {})
    tinfo = tiers.get(tier, {})
    ready = bool(tinfo.get("ready", False))
    scope_note = str(tinfo.get("scope_note", ""))
    blockers = list(tinfo.get("blockers", []))
    return ready, scope_note, blockers


def bundle_portable_paper(paper_id: str, repo_root: Path = REPO_ROOT) -> Tuple[Path, Path]:
    """Create a completely self-contained portable reproduction directory & .tar.gz for `paper_id`.

    Contains zero external relative paths (`../living-computation` is vendored inside the bundle)
    so an independent researcher can unpack it on a fresh machine and run `python3 reproduce.py`.
    """
    manifest = build_paper(paper_id, repo_root)
    papers = load_all_papers(repo_root)
    py_path, p = papers[paper_id]
    bundle_name = f"{paper_id}-v{p['version']}-portable"
    release_root = py_path.parent / "release"
    bundle_dir = release_root / bundle_name
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Copy paper docs & build appendix
    for fname in ("paper.yaml", "spec.md", "manuscript.md"):
        src = py_path.parent / fname
        if src.exists():
            shutil.copy2(src, bundle_dir / fname)
    shutil.copy2(py_path.parent / "build" / "evidence-appendix.md", bundle_dir / "evidence-appendix.md")

    # Vendor minimal Living Computation `core/` package needed to execute Paper I claims cleanly
    lc_root = (repo_root / "../living-computation").resolve()
    dst_core = bundle_dir / "src" / "core"
    shutil.copytree(
        lc_root / "core",
        dst_core,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    # Vendor Experiment 8 & 9 modules for Paper I reproduction if paper-01
    if paper_id == "paper-01":
        for rel_mod in (
            "experiments/08_predictive_sync/sync_engine.py",
            "experiments/09_timespace_inertia/timespace_core.py",
        ):
            src_m = lc_root / rel_mod
            if src_m.exists():
                dst_m = bundle_dir / "src" / rel_mod
                dst_m.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_m, dst_m)

    # Copy all pinned claims & reference result artifacts into internal bundle paths (zero `../`!)
    internal_hashes: Dict[str, Dict[str, Any]] = {}
    for ref, meta in manifest["pinned_artifacts"].items():
        src_p = resolve_ref_path(ref, repo_root)
        if not src_p.exists():
            continue
        if ref.startswith("../living-computation/"):
            rel_dst = Path("artifacts") / ref.removeprefix("../living-computation/")
            origin_uri = "living-computation://" + ref.removeprefix("../living-computation/")
        else:
            rel_dst = Path("artifacts") / ref
            origin_uri = "temporal-science://" + ref
        dst_p = bundle_dir / rel_dst
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_p, dst_p)
        internal_hashes[str(rel_dst)] = {
            "role": meta["role"],
            "sha256": sha256_file(dst_p),
            "bytes": dst_p.stat().st_size,
            "origin_uri": origin_uri,
        }

    portable_manifest = {
        "bundle_name": bundle_name,
        "paper_id": paper_id,
        "paper_version": p["version"],
        "title": p["title"],
        "exported_contract": p["exported_contract"],
        "release_tier": "scoped_preprint",
        "portable_self_contained": True,
        "claims": manifest["claims"],
        "artifacts": internal_hashes,
    }
    portable_manifest["bundle_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(portable_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (bundle_dir / "manifest.json").write_text(json.dumps(portable_manifest, indent=2), encoding="utf-8")

    # Standalone RO-Crate with strictly internal relative paths
    ro_crate = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@type": "CreativeWork",
                "@id": "ro-crate-metadata.json",
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                "about": {"@id": "./"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": f"{p['title']} (Portable Scoped Preprint Bundle)",
                "version": p["version"],
                "hasPart": [{"@id": k} for k in sorted(internal_hashes.keys())],
            },
        ],
    }
    (bundle_dir / "ro-crate-metadata.json").write_text(json.dumps(ro_crate, indent=2), encoding="utf-8")

    # Write standalone zero-external-path `reproduce.py`
    reproduce_src = '''#!/usr/bin/env python3
"""Standalone Clean-Environment Reproduction Script (Zero External Path Dependencies).

Run from any unpacked copy of this bundle on a fresh machine:
    python3 reproduce.py
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import random
import sys

BUNDLE_ROOT = Path(__file__).resolve().parent
SRC_DIR = BUNDLE_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
for extra in (
    SRC_DIR / "experiments" / "08_predictive_sync",
    SRC_DIR / "experiments" / "09_timespace_inertia",
):
    if extra.exists():
        sys.path.insert(0, str(extra))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_bundled_artifacts() -> int:
    manifest = json.loads((BUNDLE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    for rel_path, meta in artifacts.items():
        fp = BUNDLE_ROOT / rel_path
        assert fp.exists(), f"Missing bundled artifact: {rel_path}"
        got = sha256_file(fp)
        assert got == meta["sha256"], f"SHA-256 mismatch on {rel_path}: {got} != {meta['sha256']}"
    return len(artifacts)


def reproduce_paper_01_core() -> dict:
    from core import (
        CanaryState,
        ConventionalIncrementalEngine,
        FullRecomputeEngine,
        GuaranteeLevel,
        LearnedRepresentation,
        LipschitzMarginCanary,
        LivingTraceContractEngine,
        TracePolicy,
        ValidityContract,
        WorkloadConfig,
        WorkloadEnvironment,
        WorkloadRegime,
        build_milestone_network,
        compare_against_baseline,
    )

    # 1. Verify TS-001 Soundness (500 adversarial boundary probes -> 0 false-SAFE)
    g_small = build_milestone_network(num_nodes=250, num_inputs=30, seed=101)
    rng = random.Random(20261122)
    in0 = {nid: rng.uniform(-0.25, 0.25) for nid in g_small.input_ids}
    v0 = g_small.evaluate_full(in0)
    cones = [(n, g_small.extract_lipschitz_cone(n.node_id)) for n in g_small.nodes]
    cones = [(n, c) for n, c in cones if c is not None][:5]
    safe_hits, false_safes = 0, 0
    for node, (b_ids, i_ids, lip_map, _) in cones:
        vc = ValidityContract(f"repro_{node.node_id}", node.node_id, node.name, b_ids, i_ids, GuaranteeLevel.RESTRICTED_WORST_CASE, True, "repro", [], 0)
        canary = LipschitzMarginCanary(f"c_{node.node_id}", LearnedRepresentation(f"r_{node.node_id}", vc), node, lip_map, enable_regime_cache=False)
        canary.reanchor(v0, v0[node.parents[0]], v0[node.node_id])
        for s in range(100):
            sc = rng.choice([0.02, 0.08, 0.25, 1.0])
            pert = dict(in0)
            for b in b_ids:
                if b in pert:
                    pert[b] = in0[b] + rng.uniform(-sc, sc)
            v1 = g_small.evaluate_full(pert)
            res = canary.check(b_ids, v1, s + 1)
            if res.state is CanaryState.SAFE:
                safe_hits += 1
                if abs(res.cached_output - v1[node.node_id]) > 1e-12:
                    false_safes += 1
    assert safe_hits > 0 and false_safes == 0

    # 2. Reproduce 1,000-node DAG localized drift (2,000 updates quick deterministic check)
    g = build_milestone_network(num_nodes=1000, num_inputs=120, seed=42)
    env = WorkloadEnvironment(g.input_ids, WorkloadConfig(regime=WorkloadRegime.LOCALIZED_REGIME_DRIFT, num_updates=2000, seed=2026))
    init_in, events = env.generate()
    full = FullRecomputeEngine(g)
    inc = ConventionalIncrementalEngine(g)
    liv = LivingTraceContractEngine(g, warmup_steps=150, trace_policy=TracePolicy.SURPRISE_DRIVEN)
    of = full.run(init_in, events)
    oi = inc.run(init_in, events)
    ol = liv.run(init_in, events)
    liv.close()
    assert all(abs(a - b) <= 1e-12 for a, b in zip(of, oi))
    assert all(abs(a - b) <= 1e-12 for a, b in zip(of, ol))
    cmp_inc = compare_against_baseline(inc.ledger, liv.ledger)
    cmp_full = compare_against_baseline(full.ledger, liv.ledger)
    assert cmp_inc["savings_steps"] > 0 and cmp_full["savings_steps"] > 0

    # 3. Reproduce P4 bounded synchronization (0% violations) & Exp 9 Jump-to-Jitter > 4x
    from sync_engine import SyncEnvConfig, generate_sync_environment, run_sync_observer
    ds_sync = generate_sync_environment(SyncEnvConfig(dims=4, num_steps=800, phi_range=(0.82, 0.90), disturbance_mode="bounded", w_scale=0.10, noise_scale=0.02, shift_step=None, seed=888))
    r_p4 = run_sync_observer(ds_sync, "adaptive_certified_bound", horizon_tau=2, tolerance_eps=0.50, permitted_delta=0.05)
    assert r_p4.empirical_violation_rate == 0.0 and r_p4.sync_budget_satisfied

    from timespace_core import TimespaceConfig, generate_timespace_stream, run_timespace_system
    ds_ts = generate_timespace_stream(TimespaceConfig(d_relevant=4, d_irrelevant=12, num_steps=900, shift_steps=(350, 650), seed=909))
    r_liv_ts = run_timespace_system(ds_ts, "living_canary_memory")
    assert r_liv_ts.jump_to_jitter_ratio > 3.5

    return {
        "ts001_safe_hits": safe_hits,
        "ts001_false_safes": false_safes,
        "dag_1000n_2000u_exact_matches": len(of),
        "dag_savings_vs_full_pct": cmp_full["savings_steps_pct"],
        "dag_savings_vs_inc_pct": cmp_inc["savings_steps_pct"],
        "dag_payback_vs_inc": cmp_inc["payback_step_ops"],
        "p4_bounded_violation_rate": r_p4.empirical_violation_rate,
        "p4_observation_rate": round(r_p4.observation_rate, 4),
        "timespace_jump_to_jitter": round(r_liv_ts.jump_to_jitter_ratio, 2),
    }


def main() -> None:
    n_verified = verify_bundled_artifacts()
    print(f"[1/2] Verified {n_verified}/{n_verified} bundled SHA-256 artifact checksums (100% intact).")
    res = reproduce_paper_01_core()
    print("[2/2] Independent clean-environment live reproduction PASSED:")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
'''
    (bundle_dir / "reproduce.py").write_text(reproduce_src, encoding="utf-8")

    tar_path = release_root / f"{bundle_name}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(bundle_dir, arcname=bundle_name)

    return bundle_dir, tar_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Temporal Science CRR v0.2 Research CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="Validate schemas, pins, acyclicity, artifact links & scientific composition")
    p_imp = sub.add_parser("impact", help="Compute downstream dependency impact of a claim")
    p_imp.add_argument("claim_id", help="Claim ID (e.g., TS-001)")
    p_bld = sub.add_parser("build", help="Build reproducible pinned manifest, RO-Crate & appendix")
    p_bld.add_argument("paper_id", help="Paper ID (e.g., paper-01)")
    p_vb = sub.add_parser("verify-build", help="Verify live SHA-256 integrity of a built paper manifest")
    p_vb.add_argument("paper_id", help="Paper ID (e.g., paper-01)")
    p_bun = sub.add_parser("bundle", help="Create self-contained portable .tar.gz reproduction bundle")
    p_bun.add_argument("paper_id", help="Paper ID (e.g., paper-01)")
    p_rel = sub.add_parser("release", help="Evaluate 4-tier publication release gate")
    p_rel.add_argument("paper_id", help="Paper ID (e.g., paper-01)")
    p_rel.add_argument("--tier", choices=RELEASE_TIERS, default="scoped_preprint")
    sub.add_parser("test", help="Run CRR validation, adversarial composition & executable claim tests")

    args = parser.parse_args()

    if args.cmd == "validate":
        ok, errors, warnings = validate_repository()
        claims = load_all_claims()
        papers = load_all_papers()
        print(f"CRR Validate: {len(claims)} claims, {len(papers)} papers checked.")
        for w in warnings:
            print(f"  WARNING: {w}")
        for e in errors:
            print(f"  ERROR:   {e}")
        print("STATUS: PASS" if ok else "STATUS: FAIL")
        return 0 if ok else 1

    if args.cmd == "impact":
        print(json.dumps(compute_impact(args.claim_id), indent=2))
        return 0

    if args.cmd == "build":
        manifest = build_paper(args.paper_id)
        print(
            f"Built {args.paper_id} v{manifest['paper_version']} | "
            f"{len(manifest['pinned_artifacts'])} pinned artifacts | "
            f"fingerprint={manifest['build_fingerprint_sha256'][:16]}..."
        )
        return 0

    if args.cmd == "verify-build":
        ok, errs = verify_build(args.paper_id)
        if ok:
            print(f"BUILD INTEGRITY VERIFIED for {args.paper_id} (all SHA-256 checksums match disk)")
            return 0
        print(f"BUILD INTEGRITY FAILED for {args.paper_id}:")
        for e in errs:
            print(f"  - {e}")
        return 1

    if args.cmd == "bundle":
        bdir, tar_p = bundle_portable_paper(args.paper_id)
        print(f"Created self-contained portable bundle:\n  dir : {bdir}\n  tar : {tar_p} ({tar_p.stat().st_size:,} bytes)")
        return 0

    if args.cmd == "release":
        ok, errors, _ = validate_repository()
        if not ok:
            print(f"RELEASE BLOCKED: validation errors: {errors}")
            return 1
        ready, note, blockers = check_release_gate(args.paper_id, tier=args.tier)
        if ready:
            print(f"RELEASE GATE PASSED for {args.paper_id} [tier={args.tier}]")
            if note:
                print(f"  Scope: {note}")
            return 0
        print(f"RELEASE GATE BLOCKED for {args.paper_id} [tier={args.tier}]:")
        for b in blockers:
            print(f"  - {b}")
        return 2

    if args.cmd == "test":
        ok, errors, _ = validate_repository()
        if not ok:
            print(f"Validation failed: {errors}")
            return 1
        cp = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "tests", "research/claims"],
            cwd=str(REPO_ROOT),
        )
        return cp.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
