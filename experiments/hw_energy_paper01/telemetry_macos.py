"""Apple Silicon macOS Hardware PMU Energy & Resource Telemetry (`proc_pid_rusage`).

Reads per-process hardware performance & energy telemetry directly from the macOS XNU
kernel via `proc_pid_rusage(pid, RUSAGE_INFO_V6)` (`<sys/resource.h>`):
  - `ri_energy_nj`   : Per-process CPU hardware energy in nanojoules (Apple Silicon PMU/CLPC)
  - `ri_penergy_nj`  : Per-process Performance-core hardware energy in nanojoules
  - `ri_instructions`: Hardware retired CPU instructions (PMC)
  - `ri_cycles`      : Hardware CPU clock cycles (PMC)
  - `ri_user_time`   : User-mode CPU time (Mach absolute ticks -> seconds via mach_timebase_info)
  - `ri_system_time` : Kernel/syscall CPU time (Mach absolute ticks -> seconds)
  - `ri_logical_writes` / `ri_diskio_byteswritten` : OS storage write volume
  - `ri_phys_footprint` / `ri_lifetime_max_phys_footprint` : Physical RAM footprint

Measurement Scope & Boundary (Explicit Honesty):
  - Isolates this benchmark process's CPU core + kernel-attributed CPU hardware energy
    (unlike whole-system `powermetrics`, which mixes background OS processes and display).
  - Does NOT directly meter off-package SSD flash controller rail power, external DRAM rail
    power, or AC wall-socket power. Those require `sudo powermetrics` or an external wattmeter.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict
import ctypes
import os
import platform
import subprocess
import time


RUSAGE_INFO_V6 = 6


class _MachTimebaseInfo(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


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


_LIBSYSTEM = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
_TIMEBASE = _MachTimebaseInfo()
_LIBSYSTEM.mach_timebase_info(ctypes.byref(_TIMEBASE))
_TICK_TO_SEC = (_TIMEBASE.numer / _TIMEBASE.denom) * 1e-9


@dataclass(frozen=True)
class HardwareSample:
    wall_time_s: float
    user_time_s: float
    system_time_s: float
    hardware_energy_j: float
    pcore_energy_j: float
    instructions: int
    cycles: int
    pinstructions: int
    pcycles: int
    ipc: float
    avg_power_w: float
    logical_writes_bytes: int
    disk_bytes_written: int
    disk_bytes_read: int
    phys_footprint_end_mb: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def snapshot_raw() -> tuple[float, _RusageInfoV6]:
    info = _RusageInfoV6()
    rc = _LIBSYSTEM.proc_pid_rusage(os.getpid(), RUSAGE_INFO_V6, ctypes.byref(info))
    if rc != 0:
        raise OSError(f"proc_pid_rusage(RUSAGE_INFO_V6) failed with rc={rc}")
    return time.perf_counter(), info


def delta_sample(
    start: tuple[float, _RusageInfoV6], end: tuple[float, _RusageInfoV6]
) -> HardwareSample:
    t0, r0 = start
    t1, r1 = end
    wall = max(t1 - t0, 1e-12)
    user_s = (r1.ri_user_time - r0.ri_user_time) * _TICK_TO_SEC
    sys_s = (r1.ri_system_time - r0.ri_system_time) * _TICK_TO_SEC
    e_j = (r1.ri_energy_nj - r0.ri_energy_nj) * 1e-9
    pe_j = (r1.ri_penergy_nj - r0.ri_penergy_nj) * 1e-9
    inst = int(r1.ri_instructions - r0.ri_instructions)
    cyc = int(r1.ri_cycles - r0.ri_cycles)
    pinst = int(r1.ri_pinstructions - r0.ri_pinstructions)
    pcyc = int(r1.ri_pcycles - r0.ri_pcycles)
    ipc = (inst / cyc) if cyc > 0 else 0.0
    avg_w = e_j / wall
    return HardwareSample(
        wall_time_s=wall,
        user_time_s=user_s,
        system_time_s=sys_s,
        hardware_energy_j=e_j,
        pcore_energy_j=pe_j,
        instructions=inst,
        cycles=cyc,
        pinstructions=pinst,
        pcycles=pcyc,
        ipc=ipc,
        avg_power_w=avg_w,
        logical_writes_bytes=int(r1.ri_logical_writes - r0.ri_logical_writes),
        disk_bytes_written=int(r1.ri_diskio_byteswritten - r0.ri_diskio_byteswritten),
        disk_bytes_read=int(r1.ri_diskio_bytesread - r0.ri_diskio_bytesread),
        phys_footprint_end_mb=r1.ri_phys_footprint / (1024.0 * 1024.0),
    )


def get_machine_metadata() -> Dict[str, Any]:
    def _sysctl(key: str) -> str:
        r = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True)
        return r.stdout.strip()

    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_brand": _sysctl("machdep.cpu.brand_string"),
        "logical_cores": int(_sysctl("hw.ncpu") or 0),
        "memory_gb": round(int(_sysctl("hw.memsize") or 0) / (1024**3), 2),
        "mach_timebase_ns_per_tick": f"{_TIMEBASE.numer}/{_TIMEBASE.denom}",
        "telemetry_api": "macOS XNU proc_pid_rusage(RUSAGE_INFO_V6) -> ri_energy_nj, ri_instructions, ri_cycles",
        "measurement_scope": (
            "Per-process Apple Silicon CPU core & kernel-attributed hardware PMU energy "
            "(ri_energy_nj / ri_penergy_nj), retired instructions, CPU cycles, and OS disk I/O bytes. "
            "Excludes off-package SSD controller rail, external DRAM rail, and AC wall-socket power."
        ),
    }


def run_linearity_calibration() -> Dict[str, Any]:
    """Verify hardware energy counter linearity across 1x, 2x, 4x deterministic CPU work."""
    # Warm up CPU P-core DVFS state before calibration so 1x is not measured at idle clock
    _warm = 0
    for i in range(2_000_000):
        _warm += (i * 7) ^ (i >> 2)
    results = []
    for n in (1_000_000, 2_000_000, 4_000_000):
        s0 = snapshot_raw()
        acc = 0
        for i in range(n):
            acc += (i * 7) ^ (i >> 2)
        s1 = snapshot_raw()
        d = delta_sample(s0, s1)
        results.append(
            {
                "iterations": n,
                "checksum": acc,
                "hardware_energy_j": round(d.hardware_energy_j, 6),
                "instructions": d.instructions,
                "cycles": d.cycles,
                "wall_time_s": round(d.wall_time_s, 6),
                "avg_power_w": round(d.avg_power_w, 3),
            }
        )
    e1 = results[0]["hardware_energy_j"]
    e2 = results[1]["hardware_energy_j"]
    e4 = results[2]["hardware_energy_j"]
    return {
        "samples": results,
        "ratio_2x_vs_1x_energy": round(e2 / e1, 4) if e1 > 0 else 0.0,
        "ratio_4x_vs_1x_energy": round(e4 / e1, 4) if e1 > 0 else 0.0,
        "ratio_4x_vs_2x_energy": round(e4 / e2, 4) if e2 > 0 else 0.0,
        "ratio_4x_vs_1x_instructions": round(results[2]["instructions"] / results[0]["instructions"], 4),
    }
