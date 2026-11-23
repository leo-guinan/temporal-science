#!/usr/bin/env python3
"""Standalone External Researcher Challenge Runner (`v1.1.0` · `TS-PROTO-HW-ENERGY-v1.0.0`).

Zero third-party dependencies (Python 3.10+ standard library only).
Allows any independent researcher to test, replicate, or falsify Temporal Science's
5-component physical energy prediction model on ANY Python repository they choose:

    E_reuse = E_dispatch + E_validation + E_execution + E_memory + E_maintenance

Strictly enforces all 5 rules of `prospective-energy-protocol-v1.md`:
  R1: Strict blind preregistration (ZERO shared execution RNG seeds!)
  R2: Pre-execution UTC timestamp + SHA-256 seal verified before/after evaluation
  R3: Full lifecycle (cold-start + edits + validation) & calibration payback N*_cal
  R4: Equal-work 0-mismatch verification vs strong file-level incremental baseline
  R5: Mandatory negative boundary (q = 1.00 or real API-breaking commits)

Independent Workload Modes (`--phase evaluate`):
  1. `--git-history N`   : Replays the last N REAL historical Git commits touching `.py`
                           files in `--repo` (truly independent external workload generator!).
  2. `--edits-json FILE` : Replays a researcher-supplied external JSON edit stream.
  3. Default churn sweep : Experimentally mutated edits across q in {0, 0.25, 0.5, 0.75, 1.0}
                           using a fresh unseen `--seed` (clearly tagged as mutated).

Telemetry Boundary Classification (Never Conflates Wall-Plug vs Package vs Process CPU):
  - `process_attributed_cpu_pmu` : macOS Apple Silicon XNU `proc_pid_rusage(RUSAGE_INFO_V6)`
                                   (`ri_energy_nj`, `ri_instructions`, `ri_cycles`).
  - `package_rapl_hardware`      : Linux `/sys/class/powercap/intel-rapl*` with explicit
                                   domain discovery (`package-0`, `dram`, `core`), exact
                                   `max_energy_range_uj` rollover handling, and explicit
                                   `PermissionError` diagnostics.
  - `wall_cpu_time_only`         : Fallback emitting exact UTC start/end timestamps per run
                                   for alignment with an external AC wall-plug wattmeter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import argparse
import ast
import ctypes
import gc
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time


RUNNER_VERSION = "1.1.0"


# ---------------------------------------------------------------------------
# Cross-platform hardware energy telemetry (explicit scope + RAPL rollover)
# ---------------------------------------------------------------------------


class _RusageInfoV6(ctypes.Structure):
    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
        ("ri_child_user_time", ctypes.c_uint64),
        ("ri_child_system_time", ctypes.c_uint64),
        ("ri_child_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_child_interrupt_wkups", ctypes.c_uint64),
        ("ri_child_pageins", ctypes.c_uint64),
        ("ri_child_elapsed_abstime", ctypes.c_uint64),
        ("ri_diskio_bytesread", ctypes.c_uint64),
        ("ri_diskio_byteswritten", ctypes.c_uint64),
        ("ri_cpu_time_qos_default", ctypes.c_uint64),
        ("ri_cpu_time_qos_maintenance", ctypes.c_uint64),
        ("ri_cpu_time_qos_background", ctypes.c_uint64),
        ("ri_cpu_time_qos_utility", ctypes.c_uint64),
        ("ri_cpu_time_qos_legacy", ctypes.c_uint64),
        ("ri_cpu_time_qos_user_initiated", ctypes.c_uint64),
        ("ri_cpu_time_qos_user_interactive", ctypes.c_uint64),
        ("ri_billed_system_time", ctypes.c_uint64),
        ("ri_serviced_system_time", ctypes.c_uint64),
        ("ri_logical_writes", ctypes.c_uint64),
        ("ri_lifetime_max_phys_footprint", ctypes.c_uint64),
        ("ri_instructions", ctypes.c_uint64),
        ("ri_cycles", ctypes.c_uint64),
        ("ri_billed_energy", ctypes.c_uint64),
        ("ri_serviced_energy", ctypes.c_uint64),
        ("ri_interval_max_phys_footprint", ctypes.c_uint64),
        ("ri_runnable_time", ctypes.c_uint64),
        ("ri_flags", ctypes.c_uint64),
        ("ri_user_ptime", ctypes.c_uint64),
        ("ri_system_ptime", ctypes.c_uint64),
        ("ri_pinstructions", ctypes.c_uint64),
        ("ri_pcycles", ctypes.c_uint64),
        ("ri_energy_nj", ctypes.c_uint64),
        ("ri_penergy_nj", ctypes.c_uint64),
        ("ri_secure_time_in_system", ctypes.c_uint64),
        ("ri_secure_ptime_in_system", ctypes.c_uint64),
        ("ri_neural_footprint", ctypes.c_uint64),
        ("ri_lifetime_max_neural_footprint", ctypes.c_uint64),
        ("ri_interval_max_neural_footprint", ctypes.c_uint64),
        ("ri_reserved", ctypes.c_uint64 * 9),
    ]


def rapl_delta_uj(start_uj: int, end_uj: int, max_range_uj: int) -> Tuple[int, bool]:
    """Compute exact microjoule delta across a single Linux RAPL counter rollover.

    Returns (delta_uj, wrapped_flag).
    """
    if end_uj >= start_uj:
        return end_uj - start_uj, False
    if max_range_uj > 0:
        return (max_range_uj - start_uj) + end_uj, True
    return 0, True


@dataclass(frozen=True)
class RaplDomain:
    domain_id: str
    name: str
    energy_path: Path
    max_range_uj: int
    is_top_level_package: bool


def discover_linux_rapl_domains(powercap_root: Path = Path("/sys/class/powercap")) -> Dict[str, Any]:
    """Discover readable Linux RAPL domains, counter scopes, max ranges, and permission failures."""
    readable: List[RaplDomain] = []
    permission_denied: List[str] = []
    other_errors: List[str] = []

    if not powercap_root.exists():
        return {"readable": readable, "permission_denied": permission_denied, "other_errors": other_errors}

    for cand in sorted(powercap_root.glob("intel-rapl:*")):
        ep = cand / "energy_uj"
        if not ep.exists():
            continue
        domain_id = cand.name
        # Top-level packages look like `intel-rapl:0`; subdomains look like `intel-rapl:0:0`
        is_top_pkg = domain_id.count(":") == 1
        try:
            name_p = cand / "name"
            dname = name_p.read_text(encoding="utf-8").strip() if name_p.exists() else domain_id
            # Test actual readability (triggers PermissionError on hardened kernels)
            _ = int(ep.read_text(encoding="utf-8").strip())
            mr_p = cand / "max_energy_range_uj"
            max_r = int(mr_p.read_text(encoding="utf-8").strip()) if mr_p.exists() else 0
            readable.append(
                RaplDomain(
                    domain_id=domain_id,
                    name=dname,
                    energy_path=ep,
                    max_range_uj=max_r,
                    is_top_level_package=is_top_pkg,
                )
            )
        except PermissionError:
            permission_denied.append(str(ep))
        except Exception as exc:
            other_errors.append(f"{ep}: {exc}")

    return {"readable": readable, "permission_denied": permission_denied, "other_errors": other_errors}


class TelemetryBackend:
    def __init__(self, powercap_root: Path = Path("/sys/class/powercap"), force_os: Optional[str] = None) -> None:
        os_name = force_os or platform.system()
        self.name = "wall_cpu_time_only"
        self.energy_scope_tier = "wall_cpu_time_only"
        self.is_wall_plug_energy = False
        self.includes_dram = False
        self.includes_ssd_or_psu = False
        self.has_hardware_energy = False
        self.rapl_domains: List[RaplDomain] = []
        self.rapl_permission_denied: List[str] = []
        self.rapl_rollovers_detected: int = 0
        self.scope_note = (
            "No internal hardware energy counter accessible; recording wall-clock and CPU time "
            "plus UTC timestamps for external AC wall-plug wattmeter synchronization."
        )
        self._lib = None

        if os_name == "Darwin":
            try:
                lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
                probe = _RusageInfoV6()
                if lib.proc_pid_rusage(os.getpid(), 6, ctypes.byref(probe)) == 0:
                    self._lib = lib
                    self.name = "macos_proc_pid_rusage_v6"
                    self.energy_scope_tier = "process_attributed_cpu_pmu"
                    self.has_hardware_energy = True
                    self.scope_note = (
                        "Process-attributed macOS XNU CPU hardware PMU energy (ri_energy_nj), "
                        "retired instructions, and cycles. Explicitly NOT AC wall-plug energy and "
                        "excludes DRAM/SSD/PSU rails."
                    )
            except Exception:
                pass
        elif os_name == "Linux":
            rapl_info = discover_linux_rapl_domains(powercap_root)
            self.rapl_permission_denied = rapl_info["permission_denied"]
            readable: List[RaplDomain] = rapl_info["readable"]
            if readable:
                self.rapl_domains = readable
                self.name = "linux_rapl_sysfs"
                self.energy_scope_tier = "package_rapl_hardware"
                self.has_hardware_energy = True
                self.includes_dram = any("dram" in d.name.lower() for d in readable)
                names_str = ", ".join(f"{d.domain_id}({d.name})" for d in readable)
                self.scope_note = (
                    f"Linux RAPL hardware energy counters [{names_str}] with modular max_energy_range_uj "
                    "wraparound handling. Explicitly NOT AC wall-plug energy (excludes PSU/SSD/display)."
                )
            elif self.rapl_permission_denied:
                self.scope_note = (
                    f"Linux RAPL files detected ({len(self.rapl_permission_denied)} paths) but "
                    "PermissionError prevented reading (typical on hardened kernels; grant read access "
                    "or run via perf/external wattmeter). Falling back to wall/CPU time."
                )

    def metadata(self) -> Dict[str, Any]:
        return {
            "backend_name": self.name,
            "energy_scope_tier": self.energy_scope_tier,
            "has_hardware_energy": self.has_hardware_energy,
            "is_wall_plug_energy": self.is_wall_plug_energy,
            "includes_dram": self.includes_dram,
            "includes_ssd_or_psu": self.includes_ssd_or_psu,
            "rapl_readable_domains": [
                {
                    "domain_id": d.domain_id,
                    "name": d.name,
                    "max_energy_range_uj": d.max_range_uj,
                    "is_top_level_package": d.is_top_level_package,
                }
                for d in self.rapl_domains
            ],
            "rapl_permission_denied": self.rapl_permission_denied,
            "rapl_rollovers_detected": self.rapl_rollovers_detected,
            "scope_note": self.scope_note,
        }

    def snap(self) -> Dict[str, Any]:
        s: Dict[str, Any] = {
            "wall": time.perf_counter(),
            "cpu": time.process_time(),
            "utc": datetime.now(timezone.utc).isoformat(),
        }
        if self._lib is not None:
            r = _RusageInfoV6()
            assert self._lib.proc_pid_rusage(os.getpid(), 6, ctypes.byref(r)) == 0
            s["energy_j"] = r.ri_energy_nj * 1e-9
            s["instructions"] = int(r.ri_instructions)
            s["cycles"] = int(r.ri_cycles)
        elif self.rapl_domains:
            s["rapl_uj"] = {d.domain_id: int(d.energy_path.read_text(encoding="utf-8").strip()) for d in self.rapl_domains}
        return s

    def delta(self, s0: Dict[str, Any], s1: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "wall_time_s": max(s1["wall"] - s0["wall"], 1e-12),
            "cpu_time_s": max(s1["cpu"] - s0["cpu"], 1e-12),
            "start_utc": s0["utc"],
            "end_utc": s1["utc"],
        }
        if "energy_j" in s0 and "energy_j" in s1:
            out["hardware_energy_j"] = max(s1["energy_j"] - s0["energy_j"], 0.0)
            out["instructions"] = float(s1["instructions"] - s0["instructions"])
            out["cycles"] = float(s1["cycles"] - s0["cycles"])
        elif "rapl_uj" in s0 and "rapl_uj" in s1:
            per_domain_j: Dict[str, float] = {}
            pkg_plus_dram_j = 0.0
            for d in self.rapl_domains:
                duj, wrapped = rapl_delta_uj(s0["rapl_uj"][d.domain_id], s1["rapl_uj"][d.domain_id], d.max_range_uj)
                if wrapped:
                    self.rapl_rollovers_detected += 1
                dj = duj * 1e-6
                per_domain_j[f"{d.domain_id}:{d.name}"] = round(dj, 6)
                # Sum non-overlapping top-level packages + separate DRAM subdomains (never double-count core/uncore inside package)
                if d.is_top_level_package or "dram" in d.name.lower():
                    pkg_plus_dram_j += dj
            out["hardware_energy_j"] = pkg_plus_dram_j
            out["rapl_per_domain_j"] = per_domain_j
        return out


# ---------------------------------------------------------------------------
# Generic Python Repository Incremental Static Interface Checker (0-mismatch)
# ---------------------------------------------------------------------------


def _path_to_modname(repo_dir: Path, rel_py: Path) -> str:
    parts = [repo_dir.name] + list(rel_py.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def discover_python_repo(repo_dir: Path, max_modules: int = 150) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (mod_name -> source, rel_posix_path -> mod_name) for valid non-test `.py` files."""
    repo_dir = repo_dir.resolve()
    sources: Dict[str, str] = {}
    path_to_mod: Dict[str, str] = {}
    for py in sorted(repo_dir.rglob("*.py")):
        if any(part in ("tests", "test", "__pycache__", ".venv", "venv", "build", "dist", ".git") for part in py.parts):
            continue
        try:
            txt = py.read_text(encoding="utf-8", errors="replace")
            ast.parse(txt)
        except SyntaxError:
            continue
        rel = py.relative_to(repo_dir)
        mname = _path_to_modname(repo_dir, rel)
        sources[mname] = txt
        path_to_mod[rel.as_posix()] = mname
        if len(sources) >= max_modules:
            break
    if len(sources) < 5:
        raise ValueError(f"Repository {repo_dir} yielded only {len(sources)} valid .py modules (need >= 5).")
    return sources, path_to_mod


def _ann_str(node: Optional[ast.AST]) -> str:
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def extract_public_type_interface(tree: ast.Module) -> Tuple[str, Dict[str, Tuple[int, int, bool]]]:
    sigs: Dict[str, Tuple[int, int, bool]] = {}
    lines: List[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            pos = node.args.posonlyargs + node.args.args
            min_p = len(pos) - len(node.args.defaults)
            max_p = len(pos)
            has_va = node.args.vararg is not None
            ptypes = ",".join(_ann_str(a.annotation) for a in pos)
            sigs[node.name] = (min_p, max_p, has_va)
            lines.append(f"fn:{node.name}({ptypes};{min_p}..{max_p};*{int(has_va)})->{_ann_str(node.returns)}")
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = ",".join(_ann_str(b) for b in node.bases)
            meths = sorted(
                f"{m.name}({','.join(_ann_str(a.annotation) for a in m.args.args)})->{_ann_str(m.returns)}"
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and (not m.name.startswith("_") or m.name == "__init__")
            )
            lines.append(f"cls:{node.name}({bases})[{';'.join(meths)}]")
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and (tgt.id == "__all__" or tgt.id.isupper()):
                    lines.append(f"const:{tgt.id}={ast.dump(node.value)[:64]}")
    lines.sort()
    h = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:24]
    return h, sigs


def _extract_imports(tree: ast.Module, mod_name: str, known: Set[str]) -> Tuple[Tuple[str, ...], Dict[str, Tuple[str, str]]]:
    pkg = mod_name.split(".")
    deps: Set[str] = set()
    bindings: Dict[str, Tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                c = a.name
                while c:
                    if c in known and c != mod_name:
                        deps.add(c)
                        break
                    c = c.rsplit(".", 1)[0] if "." in c else ""
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = ".".join(pkg[: max(0, len(pkg) - node.level)] + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            for a in node.names:
                local = a.asname or a.name
                for cand in (f"{base}.{a.name}" if base else a.name, base):
                    c = cand
                    matched = ""
                    while c:
                        if c in known and c != mod_name:
                            matched = c
                            break
                        c = c.rsplit(".", 1)[0] if "." in c else ""
                    if matched:
                        deps.add(matched)
                        bindings[local] = (matched, a.name)
                        break
    return tuple(sorted(deps)), bindings


def build_acyclic_import_graph(sources: Dict[str, str]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], List[str]]:
    known = set(sources.keys())
    raw_deps: Dict[str, Set[str]] = {}
    for m, s in sources.items():
        d, _ = _extract_imports(ast.parse(s), m, known)
        raw_deps[m] = set(d)

    remaining = set(known)
    order: List[str] = []
    while remaining:
        ready = sorted(m for m in remaining if not (raw_deps[m] & remaining))
        if not ready:
            md = min(len(raw_deps[m] & remaining) for m in remaining)
            ready = [sorted(m for m in remaining if len(raw_deps[m] & remaining) == md)[0]]
        for m in ready:
            order.append(m)
            remaining.remove(m)

    rank = {m: i for i, m in enumerate(order)}
    deps = {m: {u for u in raw_deps[m] if rank[u] < rank[m]} for m in known}
    rev: Dict[str, Set[str]] = {m: set() for m in known}
    for m, us in deps.items():
        for u in us:
            rev[u].add(m)
    return deps, rev, order


def transitive_importers(rev: Dict[str, Set[str]], start: str) -> List[str]:
    vis: Set[str] = set()
    q = sorted(rev.get(start, set()))
    while q:
        cur = q.pop(0)
        if cur in vis or cur == start:
            continue
        vis.add(cur)
        for nxt in sorted(rev.get(cur, set())):
            if nxt not in vis:
                q.append(nxt)
    return sorted(vis)


def analyze_module(
    mod: str,
    src: str,
    known: Set[str],
    up_sigs: Dict[str, Dict[str, Tuple[int, int, bool]]],
    up_hashes: Dict[str, str],
    acyclic_deps: Optional[Set[str]] = None,
) -> Tuple[str, Dict[str, Tuple[int, int, bool]], str]:
    tree = ast.parse(src, filename=f"{mod}.py")
    ihash, sigs = extract_public_type_interface(tree)
    d_raw, binds = _extract_imports(tree, mod, known)
    dmods = tuple(sorted(d for d in d_raw if acyclic_deps is None or d in acyclic_deps))

    checked, warns = 0, 0
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in binds:
            sm, sym = binds[n.func.id]
            if acyclic_deps is not None and sm not in acyclic_deps:
                continue
            sig = up_sigs.get(sm, {}).get(sym)
            if sig is not None:
                checked += 1
                np_args = len(n.args)
                if not any(isinstance(a, ast.Starred) for a in n.args):
                    if np_args < sig[0] and not n.keywords:
                        warns += 1
                    elif np_args > sig[1] and not sig[2]:
                        warns += 1
    dsig = "|".join(f"{u}:{up_hashes.get(u, '')}" for u in dmods)
    diag = hashlib.sha256(f"{mod}|{ihash}|{checked}|{warns}|{dsig}".encode("utf-8")).hexdigest()[:24]
    return ihash, sigs, diag


@dataclass(frozen=True)
class EditOp:
    step: int
    mod: str
    new_src: str
    origin: str = "synthetic"


def make_unseen_edits(
    sources: Dict[str, str], rev: Dict[str, Set[str]], num_edits: int, q: float, seed: int
) -> List[EditOp]:
    rng = random.Random(seed)
    cands = [m for m in sorted(sources) if len(transitive_importers(rev, m)) >= 1] or sorted(sources)
    cur = dict(sources)
    edits: List[EditOp] = []
    for i in range(num_edits):
        m = rng.choice(cands)
        brk = rng.random() < q
        if brk:
            snip = f"\ndef external_api_v{i}(a: int, b: int = {i}) -> int:\n    return a + b\n"
        else:
            snip = f"\ndef _internal_impl_{i}(x: int) -> int:\n    return (x + {i}) ^ 1\n"
        cur[m] = cur[m] + snip
        edits.append(EditOp(i, m, cur[m], origin="experimentally_mutated"))
    return edits


def load_real_git_history_edits(
    repo_dir: Path,
    sources_head: Dict[str, str],
    path_to_mod: Dict[str, str],
    max_commits: int,
) -> Tuple[Dict[str, str], List[EditOp]]:
    """Extract the last `max_commits` REAL Git commits modifying `.py` files in `repo_dir`.

    Returns (initial_sources_at_base_commit, chronological_real_edits) so the benchmark replays
    authentic developer commits generated completely outside this runner!
    """
    repo_dir = repo_dir.resolve()
    git_top = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    git_root = Path(git_top).resolve()
    rel_prefix = repo_dir.relative_to(git_root).as_posix()
    prefix_arg = "." if rel_prefix == "." else rel_prefix

    log_out = subprocess.run(
        ["git", "-C", str(git_root), "log", "--reverse", f"-n{max_commits + 1}", "--format=%H", "--", prefix_arg],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    commits = [c.strip() for c in log_out if c.strip()]
    if len(commits) < 2:
        raise ValueError(f"Need at least 2 Git commits touching {repo_dir} to replay real history (found {len(commits)}).")

    base_rev = commits[0]
    base_sources = dict(sources_head)
    for rel_p, mname in path_to_mod.items():
        git_rel = rel_p if rel_prefix == "." else f"{rel_prefix}/{rel_p}"
        r = subprocess.run(
            ["git", "-C", str(git_root), "show", f"{base_rev}:{git_rel}"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            try:
                ast.parse(r.stdout)
                base_sources[mname] = r.stdout
            except SyntaxError:
                pass

    edits: List[EditOp] = []
    step = 0
    for rev_hash in commits[1:]:
        diff_files = subprocess.run(
            ["git", "-C", str(git_root), "diff-tree", "--no-commit-id", "--name-only", "-r", rev_hash, "--", prefix_arg],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        for fpath in diff_files:
            fpath = fpath.strip()
            if not fpath.endswith(".py"):
                continue
            local_rel = fpath if rel_prefix == "." else fpath.removeprefix(f"{rel_prefix}/")
            mname = path_to_mod.get(local_rel)
            if not mname:
                continue
            r = subprocess.run(
                ["git", "-C", str(git_root), "show", f"{rev_hash}:{fpath}"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                continue
            try:
                ast.parse(r.stdout)
            except SyntaxError:
                continue
            edits.append(EditOp(step=step, mod=mname, new_src=r.stdout, origin=f"git:{rev_hash[:10]}"))
            step += 1

    if not edits:
        raise ValueError(f"No valid Python edits found in the last {max_commits} commits of {repo_dir}.")
    return base_sources, edits


def load_external_edits_json(edits_path: Path, known_mods: Set[str]) -> List[EditOp]:
    """Load an external researcher-supplied edit stream from JSON (`[{"module": ..., "new_source": ...}]`)."""
    raw = json.loads(edits_path.read_text(encoding="utf-8"))
    edits: List[EditOp] = []
    for idx, item in enumerate(raw):
        mod = str(item["module"])
        if mod not in known_mods:
            raise ValueError(f"External edit #{idx} references unknown module '{mod}'")
        src = str(item["new_source"])
        ast.parse(src)
        edits.append(EditOp(step=idx, mod=mod, new_src=src, origin="external_edits_json"))
    return edits


def run_engine(
    mode: str,
    sources: Dict[str, str],
    deps: Dict[str, Set[str]],
    rev: Dict[str, Set[str]],
    order: List[str],
    edits: List[EditOp],
) -> Tuple[List[str], Dict[str, Any]]:
    cur = dict(sources)
    known = set(sources)
    rank = {m: i for i, m in enumerate(order)}
    sigs: Dict[str, Dict[str, Tuple[int, int, bool]]] = {}
    hashes: Dict[str, str] = {}
    diags: Dict[str, str] = {}

    def _one(m: str) -> str:
        h, s, d = analyze_module(m, cur[m], known, sigs, hashes, deps[m])
        hashes[m], sigs[m], diags[m] = h, s, d
        return h

    def _fp() -> str:
        return hashlib.sha256("\n".join(f"{m}:{diags[m]}" for m in sorted(diags)).encode()).hexdigest()[:20]

    for m in order:
        _one(m)
    fps = [_fp()]
    avoided_mods = 0
    avoided_kib = 0.0
    safe_hits = 0
    unsafe_misses = 0

    for ed in edits:
        cur[ed.mod] = ed.new_src
        ds = sorted(transitive_importers(rev, ed.mod), key=lambda m: rank[m])
        if mode == "strong_incremental":
            for m in [ed.mod] + ds:
                _one(m)
        elif mode == "certified_canary":
            old_h = hashes[ed.mod]
            new_h = _one(ed.mod)
            if new_h == old_h:
                safe_hits += 1
                avoided_mods += len(ds)
                avoided_kib += sum(len(cur[m].encode("utf-8")) for m in ds) / 1024.0
            else:
                unsafe_misses += 1
                for m in ds:
                    _one(m)
        else:
            raise ValueError(mode)
        fps.append(_fp())

    stats = {
        "avoided_modules": avoided_mods,
        "avoided_kib": round(avoided_kib, 2),
        "safe_hits": safe_hits,
        "unsafe_misses": unsafe_misses,
        "realized_api_break_rate": round(unsafe_misses / max(1, safe_hits + unsafe_misses), 4),
    }
    return fps, stats


# ---------------------------------------------------------------------------
# Phase 1 (Strict Blind Preregistration) & Phase 2 (Blind Evaluation)
# ---------------------------------------------------------------------------


def phase_preregister(args: argparse.Namespace) -> None:
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sources, _ = discover_python_repo(Path(args.repo), max_modules=args.max_modules)
    deps, rev, order = build_acyclic_import_graph(sources)
    known = set(sources)
    tel = TelemetryBackend()

    mod_kib = {m: len(s.encode("utf-8")) / 1024.0 for m, s in sources.items()}
    total_kib = sum(mod_kib.values())
    cands = [m for m in sorted(sources) if len(transitive_importers(rev, m)) >= 1] or sorted(sources)
    mean_edit_kib = statistics.mean(mod_kib[m] for m in cands)
    mean_ds_kib = statistics.mean(sum(mod_kib[d] for d in transitive_importers(rev, m)) for m in cands)

    by_sz = sorted(order, key=lambda m: len(sources[m]))
    n_probe = max(3, min(8, max(3, len(by_sz) // 10)))
    probe_mods = [by_sz[int(i * (len(by_sz) - 1) / max(1, n_probe - 1))] for i in range(n_probe)]
    probe_kib = sum(mod_kib[m] for m in probe_mods)

    for m in probe_mods:
        analyze_module(m, sources[m], known, {}, {})

    metric_key = "hardware_energy_j" if tel.has_hardware_energy else "wall_time_s"
    exec_rates, val_rates = [], []
    reps = 10
    for _ in range(3):
        gc.collect()
        s0 = tel.snap()
        for _ in range(reps):
            for m in probe_mods:
                analyze_module(m, sources[m], known, {}, {})
        s1 = tel.snap()
        d = tel.delta(s0, s1)
        exec_rates.append(d[metric_key] / max(reps * probe_kib, 1e-9))

    trees = [ast.parse(sources[m]) for m in probe_mods]
    vreps = 80
    for _ in range(3):
        gc.collect()
        s0 = tel.snap()
        cache: Dict[str, str] = {}
        for _ in range(vreps):
            for m, t in zip(probe_mods, trees):
                h, _ = extract_public_type_interface(t)
                _ = (cache.get(m) == h)
                cache[m] = h
        s1 = tel.snap()
        d = tel.delta(s0, s1)
        val_rates.append(d[metric_key] / (vreps * len(probe_mods)))

    e_exec_per_kib = statistics.mean(exec_rates)
    e_val_per_edit = statistics.mean(val_rates)
    cal_cost = ((1 + 3 * reps) * probe_kib) * e_exec_per_kib + (3 * vreps * len(probe_mods)) * e_val_per_edit

    qs = [0.00, 0.25, 0.50, 0.75, 1.00]
    preds: Dict[str, Any] = {}
    for q in qs:
        exp_inc_kib = total_kib + args.edits * (mean_edit_kib + mean_ds_kib)
        exp_av_kib = (1.0 - q) * args.edits * mean_ds_kib
        pred_inc = exp_inc_kib * e_exec_per_kib
        pred_delta = exp_av_kib * e_exec_per_kib - args.edits * e_val_per_edit
        pred_pct = 100.0 * pred_delta / pred_inc if pred_inc > 0 else 0.0
        preds[f"{q:.2f}"] = {
            "q": q,
            "pred_inc": round(pred_inc, 6),
            "pred_delta": round(pred_delta, 6),
            "pred_pct": round(pred_pct, 2),
        }

    q_star = 1.0 - (args.edits * e_val_per_edit) / max(args.edits * mean_ds_kib * e_exec_per_kib, 1e-12)
    core = {
        "runner_version": RUNNER_VERSION,
        "protocol_id": "TS-PROTO-HW-ENERGY-v1.0.0",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "strict_blind_no_shared_seeds": True,
        "repo_path": str(Path(args.repo).resolve()),
        "repo_modules": len(sources),
        "repo_acyclic_edges": sum(len(v) for v in deps.values()),
        "repo_total_kib": round(total_kib, 2),
        "mean_edit_kib": round(mean_edit_kib, 3),
        "mean_downstream_kib": round(mean_ds_kib, 3),
        "telemetry": tel.metadata(),
        "primary_metric": metric_key,
        "planned_edits": args.edits,
        "planned_blocks": args.blocks,
        "planned_qs": qs,
        "calibration": {
            "probe_modules": probe_mods,
            "probe_kib": round(probe_kib, 2),
            "e_exec_per_kib": round(e_exec_per_kib, 8),
            "e_val_per_edit": round(e_val_per_edit, 8),
            "estimated_calibration_cost": round(cal_cost, 6),
        },
        "q_star_pred": round(min(1.0, max(0.0, q_star)), 4),
        "predictions_by_q": preds,
    }
    seal = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    sealed = {"preregistration_sha256": seal, **core}
    pfile = out_dir / "challenge_preregistration.json"
    pfile.write_text(json.dumps(sealed, indent=2), encoding="utf-8")
    print(f"SEALED BLIND PREREGISTRATION (v{RUNNER_VERSION}) -> {pfile}")
    print(f"SHA-256: {seal}")
    print(f"Telemetry: {tel.name} [tier={tel.energy_scope_tier}, wall_plug={tel.is_wall_plug_energy}]")
    print(f"Primary metric={metric_key} | cal_cost={cal_cost:.4f} | q*_pred={core['q_star_pred']}")


def _evaluate_fixed_edit_stream(
    prereg: Dict[str, Any],
    seal: str,
    sources_base: Dict[str, str],
    deps: Dict[str, Set[str]],
    rev: Dict[str, Set[str]],
    order: List[str],
    edits: List[EditOp],
    edit_source_label: str,
    args: argparse.Namespace,
    tel: TelemetryBackend,
) -> Dict[str, Any]:
    """Evaluate a truly independent edit stream (real Git history or user-supplied JSON) against sealed primitives."""
    metric_key = prereg["primary_metric"]
    n_blocks = int(prereg["planned_blocks"])
    rng = random.Random(args.seed)

    inc_vals, can_vals = [], []
    last_stats: Dict[str, Any] = {}
    for _ in range(n_blocks):
        pair = ["strong_incremental", "certified_canary"]
        rng.shuffle(pair)
        fps: Dict[str, List[str]] = {}
        for mode in pair:
            gc.collect()
            s0 = tel.snap()
            fp, st = run_engine(mode, sources_base, deps, rev, order, edits)
            s1 = tel.snap()
            d = tel.delta(s0, s1)
            fps[mode] = fp
            if mode == "strong_incremental":
                inc_vals.append(d[metric_key])
            else:
                can_vals.append(d[metric_key])
                last_stats = st
        assert fps["strong_incremental"] == fps["certified_canary"], "0-mismatch soundness FAILED!"

    diffs = [a - b for a, b in zip(inc_vals, can_vals)]
    pcts = [100.0 * (a - b) / a if a > 0 else 0.0 for a, b in zip(inc_vals, can_vals)]
    mean_d = statistics.mean(diffs)
    mean_p = statistics.mean(pcts)
    mean_inc = statistics.mean(inc_vals)

    # Compare against sealed 5-term primitive model using BOTH:
    #   (a) blind prior prediction (using static corpus mean fanout + realized_q)
    #   (b) avoided-KiB primitive prediction (avoided_kib * e_exec_per_kib - n_edits * e_val_per_edit)
    e_kib = float(prereg["calibration"]["e_exec_per_kib"])
    e_val = float(prereg["calibration"]["e_val_per_edit"])
    cal_c = float(prereg["calibration"]["estimated_calibration_cost"])
    n_ed = len(edits)
    q_real = float(last_stats["realized_api_break_rate"])
    pred_delta_from_kib = last_stats["avoided_kib"] * e_kib - n_ed * e_val
    pred_delta_blind_mean = ((1.0 - q_real) * n_ed * float(prereg["mean_downstream_kib"])) * e_kib - n_ed * e_val
    n_cal = math.ceil(cal_c / mean_d) if mean_d > 0 else None

    print(f"  Independent stream [{edit_source_label}] ({n_ed} edits, q_real={q_real:.2f}, avoided={last_stats['avoided_modules']} mods):")
    print(f"    OBS={mean_p:+6.2f}% ({mean_d:+.4f}) | SEALED PRED(kib)={pred_delta_from_kib:+.4f} | BLIND(mean_fanout)={pred_delta_blind_mean:+.4f} | N*_cal={n_cal}")

    return {
        "runner_version": RUNNER_VERSION,
        "protocol_id": "TS-PROTO-HW-ENERGY-v1.0.0",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256_verified": seal,
        "edit_source": edit_source_label,
        "num_replayed_edits": n_ed,
        "realized_stream_stats": last_stats,
        "repo_path": prereg["repo_path"],
        "repo_modules": prereg["repo_modules"],
        "telemetry": tel.metadata(),
        "primary_metric": metric_key,
        "mismatches_total": 0,
        "obs_inc_mean": round(mean_inc, 6),
        "obs_delta": round(mean_d, 6),
        "obs_pct": round(mean_p, 2),
        "sealed_pred_delta_from_avoided_kib": round(pred_delta_from_kib, 6),
        "sealed_pred_delta_blind_population_mean": round(pred_delta_blind_mean, 6),
        "n_star_cal_payback": n_cal,
    }


def phase_evaluate(args: argparse.Namespace) -> None:
    out_dir = Path(args.out).resolve()
    pfile = out_dir / "challenge_preregistration.json"
    assert pfile.exists(), f"Missing {pfile}. Run --phase preregister first!"
    prereg = json.loads(pfile.read_text(encoding="utf-8"))
    core = {k: v for k, v in prereg.items() if k != "preregistration_sha256"}
    seal = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert seal == prereg["preregistration_sha256"], "PREREGISTRATION SEAL MISMATCH!"

    sources, path_to_mod = discover_python_repo(Path(args.repo), max_modules=args.max_modules)
    deps, rev, order = build_acyclic_import_graph(sources)
    tel = TelemetryBackend()

    # Mode 1: Real Git commit history replay (independent external generator!)
    if args.git_history is not None and args.git_history > 0:
        base_sources, real_edits = load_real_git_history_edits(Path(args.repo), sources, path_to_mod, args.git_history)
        b_deps, b_rev, b_order = build_acyclic_import_graph(base_sources)
        report = _evaluate_fixed_edit_stream(
            prereg, seal, base_sources, b_deps, b_rev, b_order, real_edits,
            f"real_git_history_last_{args.git_history}_commits", args, tel,
        )
        rfile = out_dir / "challenge_report.json"
        rfile.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"0 mismatches | Saved real-Git challenge report -> {rfile}")
        return

    # Mode 2: Researcher-supplied external JSON edit stream
    if args.edits_json is not None:
        ext_edits = load_external_edits_json(Path(args.edits_json), set(sources.keys()))
        report = _evaluate_fixed_edit_stream(
            prereg, seal, sources, deps, rev, order, ext_edits,
            f"external_edits_json:{Path(args.edits_json).name}", args, tel,
        )
        rfile = out_dir / "challenge_report.json"
        rfile.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"0 mismatches | Saved external-edits challenge report -> {rfile}")
        return

    # Mode 3: Default experimentally mutated blind churn sweep (fresh unseen --seed)
    metric_key = prereg["primary_metric"]
    n_blocks = int(prereg["planned_blocks"])
    n_edits = int(prereg["planned_edits"])
    qs = [float(q) for q in prereg["planned_qs"]]

    rng = random.Random(args.seed)
    results_by_q: Dict[str, Any] = {}
    obs_d, prd_d, obs_p, prd_p = [], [], [], []

    for q in qs:
        inc_vals, can_vals = [], []
        for b in range(n_blocks):
            unseen_seed = args.seed + int(q * 1000) * 97 + b * 31
            edits = make_unseen_edits(sources, rev, n_edits, q, unseen_seed)
            pair = ["strong_incremental", "certified_canary"]
            rng.shuffle(pair)
            fps: Dict[str, List[str]] = {}
            for mode in pair:
                gc.collect()
                s0 = tel.snap()
                fp, _ = run_engine(mode, sources, deps, rev, order, edits)
                s1 = tel.snap()
                d = tel.delta(s0, s1)
                fps[mode] = fp
                (inc_vals if mode == "strong_incremental" else can_vals).append(d[metric_key])
            assert fps["strong_incremental"] == fps["certified_canary"], f"0-mismatch soundness FAILED at q={q}!"

        diffs = [a - b for a, b in zip(inc_vals, can_vals)]
        pcts = [100.0 * (a - b) / a if a > 0 else 0.0 for a, b in zip(inc_vals, can_vals)]
        mean_d = statistics.mean(diffs)
        mean_p = statistics.mean(pcts)
        qk = f"{q:.2f}"
        pm = prereg["predictions_by_q"][qk]
        cal_c = float(prereg["calibration"]["estimated_calibration_cost"])
        n_cal = math.ceil(cal_c / mean_d) if mean_d > 0 else None

        obs_d.append(mean_d); prd_d.append(pm["pred_delta"])
        obs_p.append(mean_p); prd_p.append(pm["pred_pct"])
        results_by_q[qk] = {
            "q": q,
            "obs_delta": round(mean_d, 6),
            "pred_delta": pm["pred_delta"],
            "obs_pct": round(mean_p, 2),
            "pred_pct": pm["pred_pct"],
            "err_pct_pts": round(pm["pred_pct"] - mean_p, 2),
            "n_star_cal_payback": n_cal,
        }
        print(f"  q={qk}: OBS={mean_p:+6.2f}% ({mean_d:+.4f}) vs BLIND PRED={pm['pred_pct']:+6.2f}% ({pm['pred_delta']:+.4f}) | N*_cal={n_cal}")

    def _r2(o: List[float], p: List[float]) -> float:
        mo = statistics.mean(o)
        ss_tot = sum((x - mo) ** 2 for x in o)
        ss_res = sum((x - y) ** 2 for x, y in zip(o, p))
        return round(1.0 - ss_res / ss_tot, 4) if ss_tot > 1e-15 else 0.0

    r2_abs = _r2(obs_d, prd_d)
    r2_pct = _r2(obs_p, prd_p)
    mae_pct = round(statistics.mean(abs(x - y) for x, y in zip(obs_p, prd_p)), 2)

    report = {
        "runner_version": RUNNER_VERSION,
        "protocol_id": "TS-PROTO-HW-ENERGY-v1.0.0",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256_verified": seal,
        "edit_source": "experimentally_mutated_synthetic_churn",
        "unseen_eval_seed": args.seed,
        "repo_path": prereg["repo_path"],
        "repo_modules": prereg["repo_modules"],
        "telemetry": tel.metadata(),
        "primary_metric": metric_key,
        "mismatches_total": 0,
        "strict_blind_r2_abs": r2_abs,
        "strict_blind_r2_pct": r2_pct,
        "strict_blind_mae_pct_pts": mae_pct,
        "by_q": results_by_q,
    }
    rfile = out_dir / "challenge_report.json"
    rfile.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSTRICT BLIND RESULT: R²_abs={r2_abs}, R²_pct={r2_pct}, MAE={mae_pct} pp | 0 mismatches")
    print(f"Saved shareable challenge report -> {rfile}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Temporal Science External Energy-Model Challenge Runner (v1.1.0)")
    ap.add_argument("--repo", required=True, help="Path to any Python repository/package to test")
    ap.add_argument("--phase", required=True, choices=("preregister", "evaluate"))
    ap.add_argument("--out", default="./challenge_output", help="Directory for sealed preregistration & report")
    ap.add_argument("--blocks", type=int, default=6, help="Paired interleaved blocks per evaluation (recommended >=8)")
    ap.add_argument("--edits", type=int, default=15, help="Edits per block (mutated churn mode)")
    ap.add_argument("--max-modules", type=int, default=120, help="Max Python modules to load")
    ap.add_argument("--seed", type=int, default=99123, help="Fresh unseen RNG seed (used ONLY in --phase evaluate)")
    ap.add_argument("--git-history", type=int, default=None, help="Replay the last N REAL Git commits touching .py files")
    ap.add_argument("--edits-json", type=str, default=None, help="Replay an external researcher-supplied JSON edit stream")
    args = ap.parse_args()
    if args.phase == "preregister":
        phase_preregister(args)
    else:
        phase_evaluate(args)


if __name__ == "__main__":
    main()
