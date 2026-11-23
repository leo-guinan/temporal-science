"""Fair, strong task executors for all 3 experimental conditions across Tasks T1-T6.

Conditions:
  1. `conventional`   : Strong ordinary tooling (regex/grep, Python file checks,
                        tarfile+hashlib build script, direct verifier execution).
  2. `modular_manual` : Manually maintained JSON reference/SHA-256 manifests.
  3. `crr_v02`        : Real Temporal Science CRR v0.2 (`tools/research.py`).

No condition is given artificially messy inputs; all three operate over identical
underlying proofs, experiment JSONs, and executable verification scripts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tarfile
import tempfile
import yaml

EXP_DIR = Path(__file__).resolve().parent
TS_ROOT = EXP_DIR.parents[1]
TOOLS_DIR = TS_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import research as crr  # type: ignore
from workloads import ResearchGraphSpec, SyntheticClaim


CLAIM_HEADING_RE = re.compile(r"^##\s+([A-Z0-9-]+):", re.MULTILINE)
DEPENDS_LINE_RE = re.compile(r"^- Depends On:\s*(.+)$", re.MULTILINE)
CID_TOKEN_RE = re.compile(r"\b(?:HO-\d{3}|TS-[A-Z0-9-]+)\b")
FILE_REF_RE = re.compile(r"evidence/[A-Za-z0-9_-]+\.(?:md|json|py)")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _exec_verifier(script_path: Path) -> bool:
    """Execute a claim's deterministic Python verification script cleanly in-process."""
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in dir(mod):
        if attr.startswith("verify_") and callable(getattr(mod, attr)):
            return bool(getattr(mod, attr)())
    raise RuntimeError(f"No verify_* function in {script_path}")


def ground_truth_transitive_impact(spec: ResearchGraphSpec, target_cid: str) -> Tuple[Set[str], Set[str]]:
    """Exact ground-truth downstream claims and affected papers."""
    rev: Dict[str, List[str]] = {c.cid: [] for c in spec.claims}
    claim_to_paper = {c.cid: c.paper_id for c in spec.claims}
    for c in spec.claims:
        for dep_id, _ in c.depends_on:
            if dep_id in rev:
                rev[dep_id].append(c.cid)
    visited: Set[str] = set()
    queue = list(rev.get(target_cid, []))
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        queue.extend(rev.get(cur, []))
    papers = {claim_to_paper[target_cid]} | {claim_to_paper[c] for c in visited}
    return visited, papers


# ---------------------------------------------------------------------------
# Task T1: Reproduce a published result (paper-01)
# ---------------------------------------------------------------------------


def task_t1_reproduce(condition: str, root: Path, paper_id: str) -> Dict[str, Any]:
    files_inspected = 0
    if condition == "conventional":
        md_path = root / "papers" / f"{paper_id}.md"
        txt = md_path.read_text(encoding="utf-8")
        files_inspected += 1
        refs = sorted(set(FILE_REF_RE.findall(txt)))
        passed = 0
        for rel in refs:
            p = root / rel
            assert p.exists(), f"Missing {rel}"
            files_inspected += 1
            if rel.endswith(".json"):
                data = json.loads(p.read_text(encoding="utf-8"))
                assert data["false_safe_errors"] == 0
            elif rel.endswith(".py"):
                assert _exec_verifier(p)
                passed += 1
        return {"verified_scripts": passed, "hashes_checked": 0, "files_inspected": files_inspected}

    if condition == "modular_manual":
        mpath = root / "manifests" / f"{paper_id}_manifest.json"
        m = json.loads(mpath.read_text(encoding="utf-8"))
        files_inspected += 1
        hashes_ok = 0
        passed = 0
        for rel, expected_sha in m["artifact_sha256"].items():
            p = root / rel
            assert p.exists() and _sha256_file(p) == expected_sha
            hashes_ok += 1
            files_inspected += 1
            if rel.endswith(".py"):
                assert _exec_verifier(p)
                passed += 1
        return {"verified_scripts": passed, "hashes_checked": hashes_ok, "files_inspected": files_inspected}

    if condition == "crr_v02":
        ok, errs = crr.verify_build(paper_id, repo_root=root)
        if not ok and any("Missing build manifest" in e for e in errs):
            crr.build_paper(paper_id, repo_root=root)
            ok, errs = crr.verify_build(paper_id, repo_root=root)
        assert ok, f"CRR verify_build failed: {errs}"
        mpath = root / "papers" / paper_id / "build" / "manifest.json"
        m = json.loads(mpath.read_text(encoding="utf-8"))
        passed = 0
        hashes_ok = len(m["pinned_artifacts"])
        files_inspected = hashes_ok + 1
        for ref in m["pinned_artifacts"]:
            if ref.endswith("_verifier.py"):
                assert _exec_verifier(root / ref)
                passed += 1
        return {"verified_scripts": passed, "hashes_checked": hashes_ok, "files_inspected": files_inspected}

    raise ValueError(condition)


# ---------------------------------------------------------------------------
# Task T2: Locate a theorem's assumptions & supporting evidence
# ---------------------------------------------------------------------------


def task_t2_locate_assumptions(condition: str, root: Path, target_cid: str) -> Dict[str, Any]:
    if condition == "conventional":
        files_scanned = 0
        for md in sorted((root / "papers").glob("*.md")):
            files_scanned += 1
            txt = md.read_text(encoding="utf-8")
            marker = f"## {target_cid}:"
            pos = txt.find(marker)
            if pos != -1:
                next_pos = txt.find("\n## ", pos + len(marker))
                section = txt[pos : next_pos if next_pos != -1 else len(txt)]
                assumptions = re.findall(r"^  - (.+)$", section, re.MULTILINE)
                evidence = FILE_REF_RE.findall(section)
                return {
                    "found": True,
                    "assumptions_count": len(assumptions),
                    "evidence_count": len(evidence),
                    "files_scanned": files_scanned,
                }
        return {"found": False, "assumptions_count": 0, "evidence_count": 0, "files_scanned": files_scanned}

    if condition == "modular_manual":
        idx = json.loads((root / "manifests" / "reference_index.json").read_text(encoding="utf-8"))
        entry = idx.get(target_cid)
        return {
            "found": entry is not None,
            "assumptions_count": len(entry["assumptions"]) if entry else 0,
            "evidence_count": 3 if entry else 0,
            "files_scanned": 1,
        }

    if condition == "crr_v02":
        cpath = root / "research" / "claims" / target_cid / "claim.yaml"
        c = yaml.safe_load(cpath.read_text(encoding="utf-8"))
        ev_cnt = (
            len(c["evidence"].get("proofs", []))
            + len(c["evidence"].get("experiments", []))
            + len(c["provenance"].get("source_artifacts", []))
        )
        return {
            "found": True,
            "assumptions_count": len(c.get("assumptions", [])),
            "evidence_count": ev_cnt,
            "files_scanned": 1,
        }

    raise ValueError(condition)


# ---------------------------------------------------------------------------
# Task T3: Update upstream claim & identify ALL transitively affected findings
# ---------------------------------------------------------------------------


def _parse_conventional_paper_sections(root: Path) -> Tuple[Dict[str, Set[str]], Dict[str, str], int]:
    """Parse all paper Markdown files into claim->deps and claim->paper (strong iterative grep)."""
    deps_map: Dict[str, Set[str]] = {}
    claim_to_paper: Dict[str, str] = {}
    files_scanned = 0
    for md in sorted((root / "papers").glob("*.md")):
        files_scanned += 1
        pid = md.stem
        txt = md.read_text(encoding="utf-8")
        matches = list(CLAIM_HEADING_RE.finditer(txt))
        for i, m in enumerate(matches):
            cid = m.group(1)
            end = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
            sec = txt[m.start() : end]
            claim_to_paper[cid] = pid
            dm = DEPENDS_LINE_RE.search(sec)
            deps: Set[str] = set()
            if dm and "None" not in dm.group(1):
                deps = set(CID_TOKEN_RE.findall(dm.group(1)))
            deps_map[cid] = deps
    return deps_map, claim_to_paper, files_scanned


def task_t3_impact_analysis(
    condition: str, root: Path, target_cid: str, single_pass_grep: bool = False
) -> Dict[str, Any]:
    if condition == "conventional":
        if single_pass_grep:
            # Everyday single-pass `grep -rn <target_cid> papers/`: finds direct mentions only
            found_claims: Set[str] = set()
            found_papers: Set[str] = set()
            files_scanned = 0
            for md in sorted((root / "papers").glob("*.md")):
                files_scanned += 1
                pid = md.stem
                txt = md.read_text(encoding="utf-8")
                matches = list(CLAIM_HEADING_RE.finditer(txt))
                for i, m in enumerate(matches):
                    cid = m.group(1)
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
                    sec = txt[m.start() : end]
                    if cid == target_cid:
                        found_papers.add(pid)
                    elif target_cid in sec:
                        found_claims.add(cid)
                        found_papers.add(pid)
            return {
                "downstream_claims": sorted(found_claims),
                "affected_papers": sorted(found_papers),
                "files_scanned": files_scanned,
            }

        # Strong conventional baseline: iterative multi-hop fixed-point regex scan across all papers
        # (re-scans files per frontier wave as a researcher running iterative grep passes does)
        frontier: Set[str] = {target_cid}
        visited: Set[str] = set()
        affected_papers: Set[str] = set()
        total_scans = 0
        while frontier:
            deps_map, claim_to_paper, n_files = _parse_conventional_paper_sections(root)
            total_scans += n_files
            if target_cid in claim_to_paper:
                affected_papers.add(claim_to_paper[target_cid])
            next_frontier: Set[str] = set()
            for cid, deps in deps_map.items():
                if cid not in visited and cid != target_cid and (deps & frontier):
                    visited.add(cid)
                    next_frontier.add(cid)
                    affected_papers.add(claim_to_paper[cid])
            frontier = next_frontier
        return {
            "downstream_claims": sorted(visited),
            "affected_papers": sorted(affected_papers),
            "files_scanned": total_scans,
        }

    if condition == "modular_manual":
        idx = json.loads((root / "manifests" / "reference_index.json").read_text(encoding="utf-8"))
        rev: Dict[str, List[str]] = {cid: [] for cid in idx}
        for cid, info in idx.items():
            for dep in info.get("direct_refs", []):
                if dep in rev:
                    rev[dep].append(cid)
        visited: Set[str] = set()
        queue = list(rev.get(target_cid, []))
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            queue.extend(rev.get(cur, []))
        papers = {idx[target_cid]["paper_id"]} | {idx[c]["paper_id"] for c in visited}
        return {
            "downstream_claims": sorted(visited),
            "affected_papers": sorted(papers),
            "files_scanned": 1,
        }

    if condition == "crr_v02":
        imp = crr.compute_impact(target_cid, repo_root=root)
        return {
            "downstream_claims": list(imp["all_downstream_claims"]),
            "affected_papers": list(imp["affected_papers"]),
            "files_scanned": len(list((root / "research" / "claims").glob("*/claim.yaml"))),
        }

    raise ValueError(condition)


# ---------------------------------------------------------------------------
# Task T4: Detect broken dependencies, artifact tampering, & unsupported guarantees
# ---------------------------------------------------------------------------


DEFECT_TYPES = (
    "D1_MISSING_ARTIFACT",
    "D2_ARTIFACT_TAMPERED",
    "D3_INVALIDATED_UPSTREAM",
    "D4_FORMAL_STATUS_INFLATION",
    "D5_ENERGY_TIER_INFLATION",
    "D6_SIMULATED_SCOPE_MISUSE",
)


def inject_defect(condition: str, root: Path, spec: ResearchGraphSpec, defect_type: str) -> None:
    """Inject an identical scientific or integrity defect into a workspace copy."""
    c_root = spec.claims[0]
    # Find a downstream formal theorem (depends on c_root or proved ancestor) and a late empirical claim
    formal_child = next(
        (c for c in spec.claims[1:] if c.kind == "theorem" and c.status == "formally_proved_under_assumptions" and c.depends_on),
        spec.claims[1],
    )
    emp_claim = next(
        (c for c in spec.claims if c.status != "formally_proved_under_assumptions"),
        spec.claims[-1],
    )
    sim_claim = next((c for c in spec.claims if "simulated" in c.scope), spec.claims[-2])
    down_of_sim = next(
        (c for c in spec.claims if any(d[0] == sim_claim.cid for d in c.depends_on)),
        spec.claims[-1],
    )

    if defect_type == "D1_MISSING_ARTIFACT":
        (root / "evidence" / f"{c_root.cid}_proof.md").unlink()
        return

    if defect_type == "D2_ARTIFACT_TAMPERED":
        p = root / "evidence" / f"{c_root.cid}_results.json"
        p.write_text(p.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return

    if defect_type == "D3_INVALIDATED_UPSTREAM":
        if condition in ("conventional", "modular_manual"):
            md = root / "papers" / f"{c_root.paper_id}.md"
            md.write_text(
                md.read_text(encoding="utf-8").replace(
                    f"## {c_root.cid}: {c_root.title}\n- Kind: {c_root.kind}\n- Status: {c_root.status}",
                    f"## {c_root.cid}: {c_root.title}\n- Kind: {c_root.kind}\n- Status: invalidated",
                ),
                encoding="utf-8",
            )
            if condition == "modular_manual":
                idx_p = root / "manifests" / "reference_index.json"
                idx = json.loads(idx_p.read_text(encoding="utf-8"))
                idx[c_root.cid]["status"] = "invalidated"
                idx_p.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        else:
            yp = root / "research" / "claims" / c_root.cid / "claim.yaml"
            d = yaml.safe_load(yp.read_text(encoding="utf-8"))
            d["status"] = "invalidated"
            yp.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
        return

    if defect_type == "D4_FORMAL_STATUS_INFLATION":
        # Make `formal_child` (formally_proved_under_assumptions theorem) depend on `emp_claim` (empirical)
        if condition in ("conventional", "modular_manual"):
            md = root / "papers" / f"{formal_child.paper_id}.md"
            txt = md.read_text(encoding="utf-8")
            old_dep = f"- Depends On: {', '.join(f'{x[0]} (v{x[1]})' for x in formal_child.depends_on)}"
            new_dep = old_dep + f", {emp_claim.cid} (v{emp_claim.version})"
            md.write_text(txt.replace(old_dep, new_dep, 1), encoding="utf-8")
            if condition == "modular_manual":
                idx_p = root / "manifests" / "reference_index.json"
                idx = json.loads(idx_p.read_text(encoding="utf-8"))
                idx[formal_child.cid]["direct_refs"].append(emp_claim.cid)
                idx_p.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        else:
            yp = root / "research" / "claims" / formal_child.cid / "claim.yaml"
            d = yaml.safe_load(yp.read_text(encoding="utf-8"))
            d["depends_on"].append({"id": emp_claim.cid, "version": emp_claim.version})
            yp.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
        return

    if defect_type == "D5_ENERGY_TIER_INFLATION":
        # Claim physically_measured_energy on `emp_claim` without hardware_energy_metered=True
        if condition in ("conventional", "modular_manual"):
            md = root / "papers" / f"{emp_claim.paper_id}.md"
            md.write_text(
                md.read_text(encoding="utf-8").replace(
                    f"Energy Tier: {emp_claim.energy_tier}",
                    "Energy Tier: physically_measured_energy",
                    1,
                ),
                encoding="utf-8",
            )
        else:
            yp = root / "research" / "claims" / emp_claim.cid / "claim.yaml"
            d = yaml.safe_load(yp.read_text(encoding="utf-8"))
            d["guarantee"]["energy_evidence_tier"] = "physically_measured_energy"
            d["guarantee"].pop("hardware_energy_metered", None)
            if not d["depends_on"]:
                d["depends_on"] = [{"id": c_root.cid, "version": c_root.version}]
            yp.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
        return

    if defect_type == "D6_SIMULATED_SCOPE_MISUSE":
        # Claim real_human_subjects while depending on simulated_agent_trials
        if condition in ("conventional", "modular_manual"):
            md = root / "papers" / f"{down_of_sim.paper_id}.md"
            md.write_text(
                md.read_text(encoding="utf-8").replace(
                    f"Scope: {down_of_sim.scope}",
                    "Scope: real_human_subjects",
                    1,
                ),
                encoding="utf-8",
            )
        else:
            # Ensure sim_claim has "simulated" in scope and down_of_sim depends on it with "real_human"
            yp_s = root / "research" / "claims" / sim_claim.cid / "claim.yaml"
            ds = yaml.safe_load(yp_s.read_text(encoding="utf-8"))
            ds["guarantee"]["scope"] = "simulated_agent_trials"
            yp_s.write_text(yaml.safe_dump(ds, sort_keys=False), encoding="utf-8")

            yp_d = root / "research" / "claims" / down_of_sim.cid / "claim.yaml"
            dd = yaml.safe_load(yp_d.read_text(encoding="utf-8"))
            dd["guarantee"]["scope"] = "real_human_subjects"
            if not any(x["id"] == sim_claim.cid for x in dd["depends_on"]):
                dd["depends_on"].append({"id": sim_claim.cid, "version": sim_claim.version})
            yp_d.write_text(yaml.safe_dump(dd, sort_keys=False), encoding="utf-8")
        return

    raise ValueError(f"Unknown defect type: {defect_type}")


def task_t4_detect_defects(condition: str, root: Path, paper_id: str) -> Dict[str, Any]:
    """Run each condition's realistic automated QA/verification check and report detected errors."""
    errors: List[str] = []
    if condition == "conventional":
        # Strong conventional CI: verify every referenced file in papers/*.md exists + JSON parses + verifiers pass
        for md in sorted((root / "papers").glob("*.md")):
            txt = md.read_text(encoding="utf-8")
            for rel in sorted(set(FILE_REF_RE.findall(txt))):
                p = root / rel
                if not p.exists():
                    errors.append(f"MISSING_FILE:{rel}")
                elif rel.endswith(".json"):
                    try:
                        json.loads(p.read_text(encoding="utf-8"))
                    except Exception as e:
                        errors.append(f"BAD_JSON:{rel}:{e}")
                elif rel.endswith(".py"):
                    if not _exec_verifier(p):
                        errors.append(f"VERIFIER_FAIL:{rel}")
        return {"detected": len(errors) > 0, "error_count": len(errors), "errors": errors}

    if condition == "modular_manual":
        # Modular manual CI: verify manifest SHA-256 digests + referenced claim existence + verifiers
        idx = json.loads((root / "manifests" / "reference_index.json").read_text(encoding="utf-8"))
        for cid, info in idx.items():
            for dep in info.get("direct_refs", []):
                if dep not in idx:
                    errors.append(f"MISSING_REF:{cid}->{dep}")
        for mp in sorted((root / "manifests").glob("*_manifest.json")):
            m = json.loads(mp.read_text(encoding="utf-8"))
            for rel, sha in m["artifact_sha256"].items():
                p = root / rel
                if not p.exists():
                    errors.append(f"MISSING_ARTIFACT:{rel}")
                elif _sha256_file(p) != sha:
                    errors.append(f"CHECKSUM_MISMATCH:{rel}")
                elif rel.endswith(".py") and not _exec_verifier(p):
                    errors.append(f"VERIFIER_FAIL:{rel}")
        return {"detected": len(errors) > 0, "error_count": len(errors), "errors": errors}

    if condition == "crr_v02":
        ok_val, val_errs, _ = crr.validate_repository(root)
        errors.extend(val_errs)
        ok_bld, bld_errs = crr.verify_build(paper_id, repo_root=root)
        if not ok_bld:
            errors.extend(bld_errs)
        return {"detected": len(errors) > 0, "error_count": len(errors), "errors": errors}

    raise ValueError(condition)


# ---------------------------------------------------------------------------
# Task T5: Assemble & verify a portable research package
# ---------------------------------------------------------------------------


def task_t5_assemble_and_verify_bundle(condition: str, root: Path, paper_id: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"pkg_{condition}_") as td:
        tdir = Path(td)
        stage = tdir / f"{paper_id}_pkg"
        stage.mkdir(parents=True, exist_ok=True)
        hashes: Dict[str, str] = {}

        if condition == "conventional":
            md_src = root / "papers" / f"{paper_id}.md"
            shutil.copy2(md_src, stage / f"{paper_id}.md")
            hashes[f"{paper_id}.md"] = _sha256_file(stage / f"{paper_id}.md")
            for rel in sorted(set(FILE_REF_RE.findall(md_src.read_text(encoding="utf-8")))):
                dst = stage / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / rel, dst)
                hashes[rel] = _sha256_file(dst)
            (stage / "checksums.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")

        elif condition == "modular_manual":
            mp = root / "manifests" / f"{paper_id}_manifest.json"
            m = json.loads(mp.read_text(encoding="utf-8"))
            shutil.copy2(mp, stage / f"{paper_id}_manifest.json")
            shutil.copy2(root / "papers" / f"{paper_id}.md", stage / f"{paper_id}.md")
            for rel, sha in m["artifact_sha256"].items():
                dst = stage / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / rel, dst)
                hashes[rel] = sha
            (stage / "checksums.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")

        elif condition == "crr_v02":
            manifest = crr.build_paper(paper_id, repo_root=root)
            pdir = root / "papers" / paper_id
            for fn in ("paper.yaml", "manuscript.md"):
                if (pdir / fn).exists():
                    shutil.copy2(pdir / fn, stage / fn)
            for fn in ("manifest.json", "ro-crate-metadata.json", "evidence-appendix.md"):
                shutil.copy2(pdir / "build" / fn, stage / fn)
            for ref, meta in manifest["pinned_artifacts"].items():
                dst = stage / "artifacts" / ref
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / ref, dst)
                hashes[f"artifacts/{ref}"] = meta["sha256"]
            (stage / "checksums.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
        else:
            raise ValueError(condition)

        tar_path = tdir / f"{paper_id}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(stage, arcname=stage.name)
        tar_bytes = tar_path.stat().st_size

        # Clean-directory unpack & verify
        clean = tdir / "clean_unpack"
        clean.mkdir()
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(clean)
        unpacked = clean / stage.name
        chk = json.loads((unpacked / "checksums.json").read_text(encoding="utf-8"))
        verified = 0
        for rel, expected in chk.items():
            assert _sha256_file(unpacked / rel) == expected
            verified += 1
            if rel.endswith("_verifier.py"):
                assert _exec_verifier(unpacked / rel)
        return {"tar_bytes": tar_bytes, "verified_files": verified}


# ---------------------------------------------------------------------------
# Task T6: Incorporate a new claim into an existing research project
#          (Explicitly charges CRR schema authoring + validation + rebuild overhead!)
# ---------------------------------------------------------------------------


def task_t6_incorporate_new_claim(
    condition: str,
    root: Path,
    paper_id: str,
    new_cid: str,
    parent_cid: str,
    parent_version: str = "0.1.0",
) -> Dict[str, Any]:
    # Write identical underlying evidence artifacts
    ev = root / "evidence"
    (ev / f"{new_cid}_proof.md").write_text(
        f"# Proof — {new_cid}\n\nDepends on {parent_cid}.\n", encoding="utf-8"
    )
    (ev / f"{new_cid}_results.json").write_text(
        json.dumps({"claim_id": new_cid, "false_safe_errors": 0, "savings_ops_pct": 14.5}, indent=2),
        encoding="utf-8",
    )
    ver_p = ev / f"{new_cid}_verifier.py"
    ver_p.write_text(
        f"def verify_{new_cid.replace('-', '_')}() -> bool:\n"
        f"    return sum((i * 5) ^ (i >> 1) for i in range(2500)) > 0\n",
        encoding="utf-8",
    )

    if condition == "conventional":
        md = root / "papers" / f"{paper_id}.md"
        addition = (
            f"\n## {new_cid}: New Incorporated Claim\n"
            f"- Kind: empirical_finding\n"
            f"- Status: empirically_supported\n"
            f"- Guarantee: conditional | Scope: seeded_benchmark_regimes | Energy Tier: modeled_proxy_energy\n"
            f"- Depends On: {parent_cid} (v{parent_version})\n"
            f"- Statement: Verified extension of {parent_cid}.\n"
            f"- Assumptions:\n  - Inherits {parent_cid} premises.\n"
            f"- Proof File: evidence/{new_cid}_proof.md\n"
            f"- Experiment Data: evidence/{new_cid}_results.json\n"
            f"- Verification Script: evidence/{new_cid}_verifier.py\n"
            f"- Limitations:\n  - Pending external replication.\n"
        )
        md.write_text(md.read_text(encoding="utf-8") + addition, encoding="utf-8")
        assert _exec_verifier(ver_p)
        return {"metadata_lines_edited": addition.count("\n"), "validated": True}

    if condition == "modular_manual":
        # Append markdown + manually update both JSON manifests and recompute hashes
        res = task_t6_incorporate_new_claim(
            "conventional", root, paper_id, new_cid, parent_cid, parent_version
        )
        mp = root / "manifests" / f"{paper_id}_manifest.json"
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["claims"].append(new_cid)
        m["direct_references"][new_cid] = [parent_cid]
        for suf in ("_proof.md", "_results.json", "_verifier.py"):
            rel = f"evidence/{new_cid}{suf}"
            m["artifact_sha256"][rel] = _sha256_file(root / rel)
        mp.write_text(json.dumps(m, indent=2), encoding="utf-8")

        idx_p = root / "manifests" / "reference_index.json"
        idx = json.loads(idx_p.read_text(encoding="utf-8"))
        idx[new_cid] = {
            "paper_id": paper_id,
            "version": "0.1.0",
            "status": "empirically_supported",
            "direct_refs": [parent_cid],
            "proof": f"evidence/{new_cid}_proof.md",
            "experiment": f"evidence/{new_cid}_results.json",
            "verifier": f"evidence/{new_cid}_verifier.py",
            "assumptions": [f"Inherits {parent_cid} premises."],
        }
        idx_p.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        return {"metadata_lines_edited": res["metadata_lines_edited"] + 18, "validated": True}

    if condition == "crr_v02":
        # Full CRR contract authoring + paper.yaml update + full repository validation + rebuild
        cdir = root / "research" / "claims" / new_cid
        cdir.mkdir(parents=True, exist_ok=True)
        cdoc = {
            "id": new_cid,
            "version": "0.1.0",
            "title": f"New Incorporated Claim {new_cid}",
            "kind": "empirical_finding",
            "status": "empirically_supported",
            "paper_id": paper_id,
            "statement": f"Verified extension of {parent_cid}.",
            "assumptions": [f"Inherits {parent_cid} premises."],
            "depends_on": [{"id": parent_cid, "version": parent_version}],
            "evidence": {
                "proofs": [f"evidence/{new_cid}_proof.md"],
                "experiments": [f"evidence/{new_cid}_results.json"],
                "counterexamples": [],
            },
            "guarantee": {
                "type": "conditional",
                "scope": "seeded_benchmark_regimes",
                "energy_evidence_tier": "modeled_proxy_energy",
            },
            "validity": {
                "requirements": [f"Valid {parent_cid}"],
                "invalidation_conditions": [f"Invalidated {parent_cid}"],
            },
            "provenance": {
                "contributors": ["crr-benchmark"],
                "source_artifacts": [f"evidence/{new_cid}_verifier.py"],
            },
            "limitations": ["Pending external replication."],
        }
        ctext = yaml.safe_dump(cdoc, sort_keys=False)
        (cdir / "claim.yaml").write_text(ctext, encoding="utf-8")

        pp = root / "papers" / paper_id / "paper.yaml"
        pdoc = yaml.safe_load(pp.read_text(encoding="utf-8"))
        pdoc["claims"].append(new_cid)
        pdoc["reference_experiments"].append(
            {"id": f"exp_{new_cid}", "path": f"evidence/{new_cid}_results.json", "figures": []}
        )
        pp.write_text(yaml.safe_dump(pdoc, sort_keys=False), encoding="utf-8")

        ok, errs, _ = crr.validate_repository(root)
        assert ok, f"CRR T6 validation failed: {errs}"
        crr.build_paper(paper_id, repo_root=root)
        assert _exec_verifier(ver_p)
        return {"metadata_lines_edited": ctext.count("\n") + 6, "validated": True}

    raise ValueError(condition)
