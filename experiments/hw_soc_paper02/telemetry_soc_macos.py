"""Dual-Layer Apple Silicon Hardware Energy Telemetry (`exp_hw02`).

Combines two independent macOS hardware telemetry sources simultaneously over
exact `[t_start, t_end]` execution windows:

1. **Process-Isolated CPU Hardware PMU** (`proc_pid_rusage(pid, RUSAGE_INFO_V6)`):
   - `ri_energy_nj` / `ri_penergy_nj`: Per-process CPU hardware energy (J)
   - `ri_instructions` / `ri_cycles`: Retired CPU instructions and clock cycles
   - `ri_user_time` / `ri_system_time`: User & kernel CPU seconds
   - `ri_diskio_byteswritten` / `ri_logical_writes`: OS storage write volume

2. **Whole-SoC Hardware Energy Model** (`libIOReport.dylib` "Energy Model" group —
   the exact Apple Silicon hardware telemetry backend read by `powermetrics`):
   - `CPU Energy` (mJ): Whole-chip CPU complex (E-cluster + P-clusters + SRAM + CPM)
   - `GPU Energy` (nJ): Whole-chip GPU complex
   - `ANE0` (mJ): Apple Neural Engine
   - `DRAM0` (mJ) + `DCS0` (mJ) + `AMCC0` (mJ): Hardware DRAM, DRAM controller, and
     Apple Memory Cache Controller / Fabric
   - `DISP0` + `DISPEXT0` + `ISP0` + `AVE0` + `MSR0` + `PCIe*`: Display/media/IO rails

Non-Overlapping Rail Accounting (Zero Double-Counting):
  - `soc_cpu_j`     = `CPU Energy`
  - `soc_compute_j` = `CPU Energy` + `GPU Energy` + `ANE0`  (equivalent to powermetrics Combined Power)
  - `soc_memory_j`  = `DRAM0` + `DCS0` + `AMCC0`
  - `soc_package_j` = `soc_compute_j` + `soc_memory_j`
  - `soc_all_exposed_j` = `soc_package_j` + display/media/PCIe rails

Explicit Unmeasured Boundary:
  - Whole-SoC `IOReport` estimates are **NOT wall-plug AC measurements**. They exclude
    AC/DC PSU conversion loss, display panel backlight, discrete SSD NAND flash rail,
    cooling fans, and battery charging circuitry.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import ctypes
import os
import subprocess
import sys

# Reuse verified RUSAGE_INFO_V6 reader from exp_hw01 (read-only import)
HW01_DIR = Path(__file__).resolve().parents[1] / "hw_energy_paper01"
if str(HW01_DIR) not in sys.path:
    sys.path.insert(0, str(HW01_DIR))

from telemetry_macos import (  # type: ignore
    HardwareSample,
    delta_sample as proc_delta_sample,
    get_machine_metadata as base_machine_metadata,
    snapshot_raw as proc_snapshot_raw,
)


_UNIT_SCALE_TO_JOULES = {
    "J": 1.0,
    "mJ": 1e-3,
    "uJ": 1e-6,
    "nJ": 1e-9,
}

_MEMORY_RAILS = {"DRAM0", "DCS0", "AMCC0"}
_DISPLAY_MEDIA_IO_PREFIXES = ("DISP", "ISP", "AVE", "MSR", "PCIe", "apciec")


@dataclass(frozen=True)
class SoCEnergySample:
    soc_cpu_j: float
    soc_gpu_j: float
    soc_ane_j: float
    soc_compute_j: float
    soc_dram_j: float
    soc_dcs_j: float
    soc_amcc_j: float
    soc_memory_j: float
    soc_package_j: float
    soc_disp_media_io_j: float
    soc_all_exposed_j: float
    channel_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IOReportEnergyReader:
    """Direct Apple Silicon `libIOReport.dylib` Energy Model accumulator reader."""

    def __init__(self) -> None:
        self._cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self._ior = ctypes.CDLL("/usr/lib/libIOReport.dylib")

        self._cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        self._cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        self._cf.CFDictionaryCreateMutableCopy.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
        self._cf.CFDictionaryCreateMutableCopy.restype = ctypes.c_void_p
        self._cf.CFDictionaryGetCount.argtypes = [ctypes.c_void_p]
        self._cf.CFDictionaryGetCount.restype = ctypes.c_long
        self._cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._cf.CFDictionaryGetValue.restype = ctypes.c_void_p
        self._cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        self._cf.CFArrayGetCount.restype = ctypes.c_long
        self._cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        self._cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        self._cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        self._cf.CFStringGetCString.restype = ctypes.c_bool
        self._cf.CFRelease.argtypes = [ctypes.c_void_p]

        self._ior.IOReportCopyChannelsInGroup.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64
        ]
        self._ior.IOReportCopyChannelsInGroup.restype = ctypes.c_void_p
        self._ior.IOReportCreateSubscription.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint64, ctypes.c_void_p
        ]
        self._ior.IOReportCreateSubscription.restype = ctypes.c_void_p
        self._ior.IOReportCreateSamples.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self._ior.IOReportCreateSamples.restype = ctypes.c_void_p
        self._ior.IOReportCreateSamplesDelta.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self._ior.IOReportCreateSamplesDelta.restype = ctypes.c_void_p
        self._ior.IOReportChannelGetChannelName.argtypes = [ctypes.c_void_p]
        self._ior.IOReportChannelGetChannelName.restype = ctypes.c_void_p
        self._ior.IOReportChannelGetUnitLabel.argtypes = [ctypes.c_void_p]
        self._ior.IOReportChannelGetUnitLabel.restype = ctypes.c_void_p
        self._ior.IOReportSimpleGetIntegerValue.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        self._ior.IOReportSimpleGetIntegerValue.restype = ctypes.c_int64

        self._k_channels = self._cfstr("IOReportChannels")
        chans = self._ior.IOReportCopyChannelsInGroup(self._cfstr("Energy Model"), None, 0, 0, 0)
        if not chans:
            raise RuntimeError("IOReportCopyChannelsInGroup('Energy Model') returned NULL")
        mchans = self._cf.CFDictionaryCreateMutableCopy(None, self._cf.CFDictionaryGetCount(chans), chans)
        self._cf.CFRelease(chans)
        self._sub_out = ctypes.c_void_p()
        self._sub = self._ior.IOReportCreateSubscription(None, mchans, ctypes.byref(self._sub_out), 0, None)
        self._cf.CFRelease(mchans)
        if not self._sub or not self._sub_out.value:
            raise PermissionError(
                "IOReportCreateSubscription('Energy Model') returned NULL (blocked by sandbox or OS policy)"
            )

    def _cfstr(self, s: str) -> ctypes.c_void_p:
        return self._cf.CFStringCreateWithCString(None, s.encode("utf-8"), 0x08000100)

    def _pystr(self, ptr: ctypes.c_void_p) -> str:
        if not ptr:
            return ""
        buf = ctypes.create_string_buffer(256)
        if self._cf.CFStringGetCString(ptr, buf, 256, 0x08000100):
            return buf.value.decode("utf-8", errors="replace")
        return ""

    def snapshot(self) -> ctypes.c_void_p:
        s = self._ior.IOReportCreateSamples(self._sub, self._sub_out, None)
        if not s:
            raise RuntimeError("IOReportCreateSamples returned NULL")
        return s

    def delta(self, s0: ctypes.c_void_p, s1: ctypes.c_void_p, release_inputs: bool = True) -> SoCEnergySample:
        d = self._ior.IOReportCreateSamplesDelta(s0, s1, None)
        if release_inputs:
            self._cf.CFRelease(s0)
            self._cf.CFRelease(s1)
        if not d:
            raise RuntimeError("IOReportCreateSamplesDelta returned NULL")
        arr = self._cf.CFDictionaryGetValue(d, self._k_channels)
        n = int(self._cf.CFArrayGetCount(arr)) if arr else 0

        cpu_j = gpu_j = ane_j = 0.0
        dram_j = dcs_j = amcc_j = 0.0
        disp_media_io_j = 0.0

        for idx in range(n):
            item = self._cf.CFArrayGetValueAtIndex(arr, idx)
            name = self._pystr(self._ior.IOReportChannelGetChannelName(item))
            unit = self._pystr(self._ior.IOReportChannelGetUnitLabel(item)).strip()
            scale = _UNIT_SCALE_TO_JOULES.get(unit)
            if scale is None:
                continue
            val_j = float(self._ior.IOReportSimpleGetIntegerValue(item, 0)) * scale

            if name == "CPU Energy":
                cpu_j = val_j
            elif name == "GPU Energy":
                gpu_j = val_j
            elif name == "ANE0":
                ane_j = val_j
            elif name == "DRAM0":
                dram_j = val_j
            elif name == "DCS0":
                dcs_j = val_j
            elif name == "AMCC0":
                amcc_j = val_j
            elif name.startswith(_DISPLAY_MEDIA_IO_PREFIXES):
                disp_media_io_j += val_j

        self._cf.CFRelease(d)
        compute_j = cpu_j + gpu_j + ane_j
        memory_j = dram_j + dcs_j + amcc_j
        package_j = compute_j + memory_j
        all_j = package_j + disp_media_io_j
        return SoCEnergySample(
            soc_cpu_j=cpu_j,
            soc_gpu_j=gpu_j,
            soc_ane_j=ane_j,
            soc_compute_j=compute_j,
            soc_dram_j=dram_j,
            soc_dcs_j=dcs_j,
            soc_amcc_j=amcc_j,
            soc_memory_j=memory_j,
            soc_package_j=package_j,
            soc_disp_media_io_j=disp_media_io_j,
            soc_all_exposed_j=all_j,
            channel_count=n,
        )


def get_system_context() -> Dict[str, Any]:
    """Record ambient load average, thermal state, and battery/AC status for controls."""
    load1, load5, load15 = os.getloadavg()
    therm = ""
    try:
        r = subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True, timeout=3)
        therm = " | ".join(line.strip() for line in r.stdout.splitlines() if line.strip())
    except Exception:
        therm = "unavailable"
    batt = ""
    try:
        r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3)
        batt = " | ".join(line.strip() for line in r.stdout.splitlines() if line.strip())
    except Exception:
        batt = "unavailable"
    return {
        "loadavg_1m": round(load1, 3),
        "loadavg_5m": round(load5, 3),
        "loadavg_15m": round(load15, 3),
        "pmset_therm": therm,
        "pmset_batt": batt,
    }


def get_soc_machine_metadata() -> Dict[str, Any]:
    meta = base_machine_metadata()
    meta["powermetrics_probe"] = {
        "samplers_listed": "tasks,battery,network,disk,interrupts,cpu_power,thermal,sfi,gpu_power,ane_power",
        "non_interactive_sudo_available": False,
        "soc_backend_used": "macOS libIOReport.dylib 'Energy Model' (325 channels; same hardware accumulator backend as powermetrics)",
    }
    meta["exposed_soc_rails"] = {
        "cpu_complex": "CPU Energy (mJ; covers EACC + PACC0 + PACC1 cores, SRAM, CPM)",
        "gpu_complex": "GPU Energy (nJ)",
        "ane": "ANE0 (mJ)",
        "memory_and_fabric": "DRAM0 (mJ) + DCS0 (mJ, DRAM controller) + AMCC0 (mJ, Apple Memory Cache Controller)",
        "display_media_io": "DISP0, DISPEXT0, ISP0, AVE0, MSR0, PCIe Port *, apciec*",
        "explicitly_unmeasured": (
            "Wall-plug AC power, AC/DC adapter conversion loss, display panel backlight, "
            "discrete SSD NAND flash rail, cooling fans, and battery charging circuit."
        ),
    }
    return meta


def snapshot_dual(ior: Optional[IOReportEnergyReader]) -> Tuple[Any, Optional[ctypes.c_void_p]]:
    p0 = proc_snapshot_raw()
    i0 = ior.snapshot() if ior is not None else None
    return p0, i0


def delta_dual(
    ior: Optional[IOReportEnergyReader],
    start: Tuple[Any, Optional[ctypes.c_void_p]],
    end: Tuple[Any, Optional[ctypes.c_void_p]],
) -> Tuple[HardwareSample, Optional[SoCEnergySample]]:
    p0, i0 = start
    p1, i1 = end
    proc = proc_delta_sample(p0, p1)
    soc = ior.delta(i0, i1, release_inputs=True) if (ior is not None and i0 and i1) else None
    return proc, soc
