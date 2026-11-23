"""Automated end-to-end & unit verification of the hardened External Challenge Kit (v1.1.0)."""

from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tarfile

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTREACH_DIR = REPO_ROOT / "outreach"
KIT_RUNNER = OUTREACH_DIR / "challenge-kit-v1" / "challenge_runner.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("challenge_runner_mod", KIT_RUNNER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["challenge_runner_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_linux_rapl_wraparound_non_double_counting_and_permission_diagnostics(tmp_path: Path) -> None:
    cr = _load_runner_module()

    # 1. Exact modular counter rollover arithmetic
    delta_ok, wrapped_ok = cr.rapl_delta_uj(100_000, 350_000, 1_000_000)
    assert delta_ok == 250_000 and wrapped_ok is False

    delta_wrap, wrapped_flag = cr.rapl_delta_uj(950_000, 120_000, 1_000_000)
    assert delta_wrap == 170_000 and wrapped_flag is True

    # 2. Mock Linux sysfs powercap tree: package-0 + core (subdomain of package!) + dram
    pc = tmp_path / "powercap"
    for did, dname, init_uj, max_uj in (
        ("intel-rapl:0", "package-0", 900_000, 1_000_000),
        ("intel-rapl:0:0", "core", 400_000, 1_000_000),
        ("intel-rapl:0:1", "dram", 500_000, 1_000_000),
    ):
        d = pc / did
        d.mkdir(parents=True)
        (d / "name").write_text(dname + "\n", encoding="utf-8")
        (d / "energy_uj").write_text(f"{init_uj}\n", encoding="utf-8")
        (d / "max_energy_range_uj").write_text(f"{max_uj}\n", encoding="utf-8")

    tel = cr.TelemetryBackend(powercap_root=pc, force_os="Linux")
    assert tel.energy_scope_tier == "package_rapl_hardware"
    assert tel.is_wall_plug_energy is False
    assert tel.includes_dram is True
    assert len(tel.rapl_domains) == 3

    s0 = tel.snap()
    # Simulate package-0 wrapping around 1_000_000 (900k -> 100k = +200k uJ = 0.20 J),
    # core rising (+150k uJ, must NOT be double-counted with package-0!), dram rising (+50k uJ = 0.05 J)
    (pc / "intel-rapl:0" / "energy_uj").write_text("100000\n", encoding="utf-8")
    (pc / "intel-rapl:0:0" / "energy_uj").write_text("550000\n", encoding="utf-8")
    (pc / "intel-rapl:0:1" / "energy_uj").write_text("550000\n", encoding="utf-8")
    s1 = tel.snap()
    d = tel.delta(s0, s1)

    assert tel.rapl_rollovers_detected == 1
    assert abs(d["hardware_energy_j"] - 0.25) < 1e-9  # 0.20 J (pkg) + 0.05 J (dram), core NOT double-counted
    assert abs(d["rapl_per_domain_j"]["intel-rapl:0:package-0"] - 0.20) < 1e-9

    # 3. Mock PermissionError on hardened Linux kernel (chmod 000 on energy_uj)
    pc_locked = tmp_path / "powercap_locked"
    d_lock = pc_locked / "intel-rapl:0"
    d_lock.mkdir(parents=True)
    (d_lock / "name").write_text("package-0\n", encoding="utf-8")
    ep_lock = d_lock / "energy_uj"
    ep_lock.write_text("1000\n", encoding="utf-8")
    os.chmod(ep_lock, 0)
    try:
        tel_lock = cr.TelemetryBackend(powercap_root=pc_locked, force_os="Linux")
        assert tel_lock.energy_scope_tier == "wall_cpu_time_only"
        assert tel_lock.has_hardware_energy is False
        assert len(tel_lock.rapl_permission_denied) == 1
    finally:
        os.chmod(ep_lock, stat.S_IRUSR | stat.S_IWUSR)


def test_outreach_packet_and_standalone_challenge_kit_end_to_end(tmp_path: Path) -> None:
    assert (OUTREACH_DIR / "accelerator-packet" / "ACCELERATOR_BRIEF.md").exists()
    assert (OUTREACH_DIR / "accelerator-packet" / "RESEARCHER_OUTREACH_TEMPLATES.md").exists()
    tar_path = OUTREACH_DIR / "challenge-kit-v1.tar.gz"
    assert tar_path.exists()

    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(tmp_path)
    kit_dir = tmp_path / "challenge-kit-v1"
    for fname in (
        "README.md",
        "challenge_runner.py",
        "prospective-energy-protocol-v1.md",
        "prospective-energy-protocol-v1.yaml",
    ):
        assert (kit_dir / fname).exists(), f"Missing {fname} in challenge-kit-v1.tar.gz"

    # Build a real temporary Git repository with 4 authentic sequential commits (2 private refactors, 2 API changes)
    demo_repo = tmp_path / "demo_git_pkg"
    demo_repo.mkdir()
    (demo_repo / "__init__.py").write_text("from .core import base_fn\n", encoding="utf-8")
    (demo_repo / "core.py").write_text("def base_fn(x: int) -> int:\n    return x * 2 + 1\n", encoding="utf-8")
    for idx in range(5):
        (demo_repo / f"mod_{idx}.py").write_text(
            f"from .core import base_fn\n\ndef f_{idx}(v: int) -> int:\n    return base_fn(v) + {idx}\n",
            encoding="utf-8",
        )

    def _git(*gargs: str) -> None:
        subprocess.run(["git", "-C", str(demo_repo), *gargs], check=True, capture_output=True)

    _git("init")
    _git("config", "user.email", "test@temporal.science")
    _git("config", "user.name", "Test")
    _git("add", ".")
    _git("commit", "-m", "initial")

    # Commit 1: private implementation edit in core.py (public interface unchanged -> SAFE!)
    (demo_repo / "core.py").write_text(
        "def _helper(x: int) -> int:\n    return x * 2\n\ndef base_fn(x: int) -> int:\n    return _helper(x) + 1\n",
        encoding="utf-8",
    )
    _git("commit", "-am", "private refactor 1")

    # Commit 2: public API addition in core.py (UNSAFE!)
    (demo_repo / "core.py").write_text(
        "def _helper(x: int) -> int:\n    return x * 2\n\ndef base_fn(x: int) -> int:\n    return _helper(x) + 1\n\n"
        "def extra_api(y: int) -> int:\n    return y + 7\n",
        encoding="utf-8",
    )
    _git("commit", "-am", "public api addition")

    # Commit 3: private refactor 2 in core.py (SAFE!)
    (demo_repo / "core.py").write_text(
        "def _helper(x: int) -> int:\n    return x + x\n\ndef base_fn(x: int) -> int:\n    return _helper(x) + 1\n\n"
        "def extra_api(y: int) -> int:\n    return y + 7\n",
        encoding="utf-8",
    )
    _git("commit", "-am", "private refactor 2")

    out_dir = tmp_path / "run_out"
    r1 = subprocess.run(
        [
            sys.executable, str(kit_dir / "challenge_runner.py"),
            "--repo", str(demo_repo), "--phase", "preregister",
            "--out", str(out_dir), "--blocks", "2", "--edits", "4",
        ],
        capture_output=True, text=True, check=True,
    )
    assert "SEALED BLIND PREREGISTRATION" in r1.stdout

    # Test Mode 1: Real Git History replay (`--git-history 3`)
    r_git = subprocess.run(
        [
            sys.executable, str(kit_dir / "challenge_runner.py"),
            "--repo", str(demo_repo), "--phase", "evaluate",
            "--out", str(out_dir), "--git-history", "3",
        ],
        capture_output=True, text=True, check=True,
    )
    assert "0 mismatches" in r_git.stdout
    rep_git = json.loads((out_dir / "challenge_report.json").read_text(encoding="utf-8"))
    assert rep_git["edit_source"] == "real_git_history_last_3_commits"
    assert rep_git["telemetry"]["is_wall_plug_energy"] is False
    assert rep_git["realized_stream_stats"]["safe_hits"] == 2
    assert rep_git["realized_stream_stats"]["unsafe_misses"] == 1
    assert rep_git["mismatches_total"] == 0

    # Test Mode 2: External user-supplied JSON edit stream (`--edits-json`)
    ext_json = tmp_path / "user_edits.json"
    ext_json.write_text(
        json.dumps(
            [
                {
                    "module": "demo_git_pkg.core",
                    "new_source": "def _helper(x: int) -> int:\n    return (x << 1)\n\n"
                                  "def base_fn(x: int) -> int:\n    return _helper(x) + 1\n\n"
                                  "def extra_api(y: int) -> int:\n    return y + 7\n",
                }
            ]
        ),
        encoding="utf-8",
    )
    r_ext = subprocess.run(
        [
            sys.executable, str(kit_dir / "challenge_runner.py"),
            "--repo", str(demo_repo), "--phase", "evaluate",
            "--out", str(out_dir), "--edits-json", str(ext_json),
        ],
        capture_output=True, text=True, check=True,
    )
    assert "0 mismatches" in r_ext.stdout
    rep_ext = json.loads((out_dir / "challenge_report.json").read_text(encoding="utf-8"))
    assert rep_ext["edit_source"] == "external_edits_json:user_edits.json"
    assert rep_ext["realized_stream_stats"]["safe_hits"] == 1
    assert rep_ext["mismatches_total"] == 0
