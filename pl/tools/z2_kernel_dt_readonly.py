"""Bounded, read-only kernel/DT/sysfs provenance *candidate* inventory.

Designed to run locally on a separately enrolled Z2, or with fake /sys and
/proc roots in tests. No SSH/client, subprocess, sysfs writes, mmap, MMIO,
driver binding, FPGA manager firmware loading, or network. JSON is deliberately
sanitized; complete raw local evidence remains a separate operator activity.

A snapshot cannot establish source-to-binary identity, atomic ownership,
AXI drain, device safety, or permission to reload PL. M1 always NO-GO.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re

MAX_SYSFS = 8192
MAX_CONFIG = 2 * 1024 * 1024
MAX_FDT = 4 * 1024 * 1024
FLAGS = (
    "CONFIG_FPGA_MGR_ZYNQ_FPGA",
    "CONFIG_FPGA_MGR_ZYNQ_AFI_FPGA",
    "CONFIG_FPGA_BRIDGE",
    "CONFIG_OF_FPGA_REGION",
    "CONFIG_UIO_PDRV_GENIRQ",
)


class InventoryRefused(ValueError):
    """Unsafe roots/escaping links or malformed mandatory observations."""


def _read(root: Path, relative: str, limit: int = MAX_SYSFS) -> bytes | None:
    """Whitelisted read; never follow a fixture link outside its root."""
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise InventoryRefused("Forbidden relative file path")
    base = root.resolve(strict=True)
    target = root / relative
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(base):
        raise InventoryRefused("Path resolves outside input root")
    if not resolved.is_file():
        return None
    try:
        with resolved.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError:
        return None
    if len(data) > limit:
        raise InventoryRefused("Read-only source too large: " + relative)
    return data


def _decode(raw: bytes | None) -> str | None:
    if not raw:
        return None
    try:
        value = raw.decode("utf-8").strip("\x00 \t\r\n")
    except UnicodeDecodeError:
        return None
    if not value or len(value) > 1024 or any(ord(c) < 32 and c not in "\n\t" for c in value):
        return None
    return value


def _raw_strings(raw: bytes | None) -> list[str] | None:
    if raw is None:
        return None
    result = [_decode(x) for x in raw.split(b"\x00") if x]
    return [x for x in result if x is not None]


def _sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _driver_name(root: Path, relative: str) -> str | None:
    link = root / relative
    if not link.is_symlink():
        return None
    base = root.resolve(strict=True)
    try:
        resolved = link.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(base):
        raise InventoryRefused("Driver link escapes sysfs")
    return resolved.name


def _entries(root: Path, relative: str, pattern: str) -> list[str] | None:
    directory = root / relative
    if not directory.exists():
        return None
    resolved = directory.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise InventoryRefused("Inventory directory escapes sysfs")
    if not resolved.is_dir():
        return None
    try:
        names = sorted(p.name for p in resolved.iterdir()
                       if re.fullmatch(pattern, p.name))
    except OSError:
        return None
    if len(names) > 128:
        raise InventoryRefused("Inventory directory unexpectedly large")
    return names


def _config(raw: bytes | None) -> dict:
    if raw is None:
        return {"status": "UNAVAILABLE", "compressed_sha256": None,
                "plain_sha256": None, "flags": None}
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            plain = gz.read(MAX_CONFIG + 1)
        if len(plain) > MAX_CONFIG:
            raise InventoryRefused("Kernel config decompressed data too large")
        decoded = plain.decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise InventoryRefused("Malformed /proc/config.gz") from exc
    selected = {}
    for flag in FLAGS:
        matched = re.findall(r"^" + flag + r"=(y|m|n)$", decoded, re.M)
        disabled = "# " + flag + " is not set" in decoded
        selected[flag] = matched[0] if len(matched) == 1 else ("n" if disabled else None)
    return {
        "status": "READ_ONLY",
        "compressed_sha256": _sha(raw),
        "plain_sha256": _sha(plain),
        "flags": selected,
    }


def collect(sysroot: Path, procroot: Path) -> dict:
    """Collect limited observations only. Always NOT_ATTESTED/NO-GO."""
    if not sysroot.is_dir() or not procroot.is_dir():
        raise InventoryRefused("Input /sys or /proc directory missing")
    boot = _decode(_read(procroot, "sys/kernel/random/boot_id"))
    release = _decode(_read(procroot, "sys/kernel/osrelease"))
    if not boot or not release:
        raise InventoryRefused("Missing boot ID or kernel release")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", boot):
        raise InventoryRefused("Invalid boot ID format")
    if len(release) > 256:
        raise InventoryRefused("Invalid kernel release")
    # Never print raw boot ID, /proc/version build username or private paths.
    version = _read(procroot, "version")
    config = _config(_read(procroot, "config.gz", MAX_CONFIG))
    model = _decode(_read(sysroot, "firmware/devicetree/base/model"))
    compat = _raw_strings(_read(sysroot, "firmware/devicetree/base/compatible"))
    fdt = _read(sysroot, "firmware/fdt", MAX_FDT)

    manager_ids = _entries(sysroot, "class/fpga_manager", r"fpga[0-9]+")
    region_ids = _entries(sysroot, "class/fpga_region", r"region[0-9]+")
    bridge_ids = _entries(sysroot, "class/fpga_bridge", r"[a-zA-Z0-9_.-]+")
    uio_ids = _entries(sysroot, "class/uio", r"uio[0-9]+")
    managers = []
    for name in manager_ids or []:
        prefix = "class/fpga_manager/" + name
        managers.append({
            "name": name,
            "state": _decode(_read(sysroot, prefix + "/state")),
            "driver": _driver_name(sysroot, prefix + "/device/driver"),
            "compatible": _raw_strings(_read(sysroot, prefix + "/device/of_node/compatible")),
            "syscon_property_sha256": _sha(_read(sysroot, prefix + "/device/of_node/syscon")),
        })
    regions = []
    for name in region_ids or []:
        prefix = "class/fpga_region/" + name
        regions.append({
            "name": name,
            "driver": _driver_name(sysroot, prefix + "/device/driver"),
            "dt_fpga_mgr_property_sha256": _sha(_read(sysroot, prefix + "/device/of_node/fpga-mgr")),
            "dt_fpga_bridges_property_sha256": _sha(_read(sysroot, prefix + "/device/of_node/fpga-bridges")),
        })
    uios = []
    for name in uio_ids or []:
        prefix = "class/uio/" + name
        maps = []
        for map_name in _entries(sysroot, prefix + "/maps", r"map[0-9]+") or []:
            sub = prefix + "/maps/" + map_name
            maps.append({
                "index": map_name,
                "addr": _decode(_read(sysroot, sub + "/addr")),
                "size": _decode(_read(sysroot, sub + "/size")),
                "offset": _decode(_read(sysroot, sub + "/offset")),
            })
        uios.append({
            "device": name,
            "name": _decode(_read(sysroot, prefix + "/name")),
            "driver": _driver_name(sysroot, prefix + "/device/driver"),
            "maps": maps,
        })
    return {
        "schema": "plasma-z2-kernel-dt-readonly-inventory-v1",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_kind": "CALLER_SUPPLIED_SYSROOT_PROCROOT_UNATTESTED",
        "boot_id_sha256": hashlib.sha256(boot.encode("utf-8")).hexdigest(),
        "kernel_release": release,
        "proc_version_sha256": _sha(version),
        "kernel_config": config,
        "device_tree": {
            "model": model,
            "compatible": compat,
            "firmware_fdt_sha256": _sha(fdt),
            "firmware_fdt_available": fdt is not None,
            "fdt_hash_is_complete_active_dt_attestation": False,
        },
        "fpga_managers": managers if manager_ids is not None else None,
        "fpga_regions": regions if region_ids is not None else None,
        "fpga_bridges": bridge_ids,
        "fabric_uio": uios if uio_ids is not None else None,
        "source_commit_matching_running_binary": "UNRESOLVED",
        "kernel_binary_identity": "UNRESOLVED",
        "kernel_patchset_identity": "UNRESOLVED",
        "dma_axi_quiescence_proven": False,
        "hardware_ready": False,
        "reload_authorized": False,
        "m1_verdict": "NO_GO",
        "observation_limit": "Snapshot only; no active source-to-binary or AXI-drain attestation",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Z2 read-only /proc,/sys inventory (M1 NO-GO)")
    parser.add_argument("--sysroot", type=Path, default=Path("/sys"))
    parser.add_argument("--procroot", type=Path, default=Path("/proc"))
    args = parser.parse_args(argv)
    try:
        result = collect(args.sysroot, args.procroot)
    except (OSError, InventoryRefused) as exc:
        result = {
            "schema": "plasma-z2-kernel-dt-readonly-inventory-v1",
            "m1_verdict": "NO_GO",
            "hardware_ready": False,
            "reload_authorized": False,
            "result": "BLOCKED",
            "error_class": type(exc).__name__,
        }
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
