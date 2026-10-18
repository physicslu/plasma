"""Read-only *offline* M1 Z2 hardware-boundary review of Phase-1 inventory JSON.

The input is untrusted observation text: it is NOT a source-to-binary
attestation, an atomic ownership audit, an AXI-drain measurement, or a
hardware authorization. This module never opens sysfs, /dev/uio, /dev/mem,
FPGA Manager, network sockets, or subprocesses.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class ReviewRefused(ValueError):
    """Malformed or falsely promoted inventory cannot enter M1 review."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReviewRefused(reason)


def _string(value: object, field: str) -> str:
    _require(type(value) is str and 1 <= len(value) <= 256
             and value.strip() == value and "\x00" not in value,
             field + ": exact nonempty text required")
    return value


def assess_z2_m1_inventory(snapshot: object) -> dict:
    """Review recorded Z2 inventory topology; NEVER return a GO capability.

    The observed 0x40000000/64-KiB UIO fabric map is a Z2 PoC fixture,
    not a board-independent resource contract. Even a perfectly shaped
    snapshot cannot certify source lineage, bridge *behavior*, kernel/DMA
    exclusion, outstanding AXI requests, or external recovery.
    """
    _require(type(snapshot) is dict, "Inventory must be an object")
    _require(snapshot.get("result") == "UIO_MAPPING_CANDIDATE_ONLY",
             "Only Phase-1 inventory candidates can be reviewed")
    for field, expected in (("read_only", True), ("hardware_ready", False),
                            ("reload_authorized", False)):
        _require(type(snapshot.get(field)) is bool
                 and snapshot[field] is expected,
                 "Invalid/unsafe inventory admission flag: " + field)
    _string(snapshot.get("boot_id"), "boot_id")
    _string(snapshot.get("kernel_release"), "kernel_release")
    uios = snapshot.get("uio")
    _require(type(uios) is list and 1 <= len(uios) <= 64, "UIO list unavailable")
    candidate = snapshot.get("candidate_ppu_window")
    _require(type(candidate) is dict, "Candidate UIO mapping unavailable")
    expected = {
        "map_index": 0,
        "mmap_selector_bytes": 0,
        "window_byte_index": 0,
        "physical_window_start": 0x40000000,
        "window_size": 0x10000,
        "driver": "uio_pdrv_genirq",
    }
    for field, value in expected.items():
        _require(type(candidate.get(field)) is type(value)
                 and candidate[field] == value,
                 "Wrong or unreviewed Z2 map0 field: " + field)
    device = _string(candidate.get("device"), "UIO device")
    _require(device.startswith("/dev/uio") and device[8:].isdigit(),
             "Candidate must reference /dev/uioN")
    matches = []
    overlapping = 0
    seen_devices: set[str] = set()
    for uio in uios:
        _require(type(uio) is dict, "Malformed UIO entry")
        dev = _string(uio.get("device"), "UIO entry device")
        _require(dev.startswith("/dev/uio") and dev[8:].isdigit()
                 and dev not in seen_devices,
                 "Duplicate or unrecognized UIO device")
        seen_devices.add(dev)
        maps = uio.get("maps")
        _require(type(maps) is list and maps, "UIO entry maps missing")
        seen_indices: set[int] = set()
        for m in maps:
            _require(type(m) is dict, "UIO map entry malformed")
            for field in ("index", "addr", "size", "offset"):
                _require(type(m.get(field)) is int, "UIO map integer required: " + field)
            index, addr, size, offset = (m["index"], m["addr"], m["size"], m["offset"])
            _require(index >= 0 and index not in seen_indices
                     and 0 <= addr <= 0xFFFFFFFF and 0 < size
                     and addr + size <= 0x100000000 and 0 <= offset < 4096,
                     "Malformed/duplicate UIO mapping interval")
            seen_indices.add(index)
            if addr < 0x40010000 and 0x40000000 < addr + size:
                overlapping += 1
            if (dev == device and
                    uio.get("driver") == "uio_pdrv_genirq" and
                    index == 0 and addr == 0x40000000 and
                    size == 0x10000 and offset == 0):
                matches.append(uio)
    _require(len(matches) == 1 and overlapping == 1,
             "Unique exact Z2 map0 not observed or extra overlapping UIO owner")
    bridge_entries = snapshot.get("fpga_bridge_sysfs_entries")
    _require(type(bridge_entries) is list and len(bridge_entries) <= 64,
             "FPGA bridge inventory unavailable")
    _require(all(type(s) is str and 0 < len(s) <= 128
                 and s.strip() == s and "/" not in s for s in bridge_entries)
             and len(set(bridge_entries)) == len(bridge_entries),
             "Malformed or duplicate bridge names")
    _string(snapshot.get("fpga_manager_state"), "FPGA Manager state")
    blockers = [
        "KERNEL_SOURCE_BINARY_PROVENANCE_UNVERIFIED",
        "MANAGER_SYSFS_PATH_NOT_EQUIVALENT_TO_REGION_BRIDGE_ISOLATION",
        "UIO_ADVISORY_OWNERSHIP_CANNOT_EXCLUDE_UNMANAGED_MAPPINGS",
        "INSTANTANEOUS_PROC_SCAN_CANNOT_EXCLUDE_RACING_OR_KERNEL_DMA_CONSUMERS",
        "PS_PL_AXI_DRAIN_AND_ABORT_CONTAINMENT_UNPROVEN",
        "EXTERNAL_DUT_SAFE_STATE_AND_INDEPENDENT_RECOVERY_UNQUALIFIED",
        "ABI_V1_COMPATIBLE_IMAGES_AND_READBACK_NOT_QUALIFIED",
    ]
    if not bridge_entries:
        blockers.insert(1, "NO_REGISTERED_FPGA_BRIDGE_OBSERVED")
    else:
        blockers.insert(1, "BRIDGE_SYSFS_NAME_NOT_PHYSICAL_ISOLATION_EVIDENCE")
    return {
        "verdict": "M1_NO_GO",
        "review_scope": "Z2_PHASE1_UIO_INVENTORY_ONLY",
        "inventory_is_attestation": False,
        "hardware_ready": False,
        "reload_authorized": False,
        "manager_operating_is_safety_proof": False,
        "observed_uio_map0": True,
        "observed_bridge_entry_count": len(bridge_entries),
        "blockers": blockers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline M1 NO-GO analysis; never authorizes a real FPGA load")
    parser.add_argument("--inventory", required=True, type=Path,
                        help="Existing Phase-1 JSON snapshot file (not live /sys)")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = assess_z2_m1_inventory(snapshot)
    except (OSError, ValueError) as exc:
        result = {"verdict": "M1_NO_GO", "hardware_ready": False,
                  "reload_authorized": False,
                  "error": "INVENTORY_INVALID: " + type(exc).__name__}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
