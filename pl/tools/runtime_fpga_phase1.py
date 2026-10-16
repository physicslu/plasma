"""Host-only PLASMA Phase-1 ABI + Linux UIO inventory contract tool.

Never opens /dev/mem, /dev/uio*, FPGA Manager, or a PL register; does not
mmap, bind/unbind devices, run subprocesses or write a file. This is not a
hardware ownership audit or authorization for FPGA reload.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re


class Phase1Error(ValueError):
    """Fail-closed contract or read-only inventory refusal."""


def require(test: bool, message: str) -> None:
    if not test:
        raise Phase1Error(message)


def integer(value: object, label: str) -> int:
    require(type(value) is str, f"{label}: must be a hexadecimal string")
    try:
        n = int(value, 0)
    except ValueError as exc:
        raise Phase1Error(f"{label}: invalid hexadecimal integer") from exc
    require(0 <= n <= 0xFFFFFFFF, f"{label}: out of range")
    return n


def validate_contract(data: dict) -> dict:
    """Validate the proposed 64-KiB identity/site layout, not physical RTL."""
    require(type(data) is dict and
            data.get("contract") == "plasma-runtime-fpga-abi-v1-proposal" and
            data.get("status") == "proposed_not_implemented",
            "Unknown or improperly promoted ABI proposal")
    window = data.get("ppu_window")
    require(type(window) is dict, "Window missing")
    base = integer(window.get("base"), "ppu base")
    size = window.get("size_bytes")
    stride = window.get("aperture_size_bytes")
    count = window.get("max_sites")
    require(base == 0x40000000 and size == 65536 and stride == 4096 and
            count == 8 and base % 4096 == 0, "Unexpected proposed layout")
    wire = data.get("wire")
    require(type(wire) is dict and wire.get("endianness") == "little" and
            wire.get("register_access_width_bits") == 32 and
            wire.get("alignment_bytes") == 4 and data.get("abi_major") == 1,
            "Unsupported word/ABI contract")
    regions = data.get("regions")
    require(type(regions) is list and len(regions) == 12,
            "Expected identity + 3 reserved + 8 Site apertures")
    seen_bases: set[int] = set()
    site_ids: set[int] = set()
    for region in regions:
        require(type(region) is dict, "Invalid region")
        rb = integer(region.get("base"), "region base")
        rs = region.get("size_bytes")
        require(type(rs) is int and rs == stride and
                base <= rb and rb + rs <= base + size and
                (rb - base) % stride == 0 and rb not in seen_bases,
                "Region out of range, unaligned or overlapping")
        seen_bases.add(rb)
        registers = region.get("registers")
        require(type(registers) is list, "Register list missing")
        seen_offsets: set[int] = set()
        for reg in registers:
            require(type(reg) is dict and reg.get("access") == "ro" and
                    reg.get("width_bits") == 32, "Unsafe or unknown register")
            offset = integer(reg.get("offset"), "register offset")
            require(0 <= offset <= rs - 4 and offset % 4 == 0 and
                    offset not in seen_offsets, "Overlapping/unaligned register")
            seen_offsets.add(offset)
        slot = (rb - base) // stride
        role = region.get("role")
        if slot == 0:
            require(role == "identity" and region.get("name") == "identity" and
                    {r["name"] for r in registers} >=
                    {"magic", "abi_version", "capabilities_lo",
                     "capabilities_hi", "site_present_bitmap"},
                    "Incomplete identity register set")
        elif slot < 4:
            require(role == "reserved" and not registers,
                    "Reserved PL aperture must not expose registers")
        elif slot < 12:
            site_id = slot - 3
            require(role == "site" and region.get("site_id") == site_id and
                    region.get("name") == f"site_{site_id:02d}" and
                    {r["name"] for r in registers} >=
                    {"site_id", "site_abi_version", "site_status"},
                    "Invalid Site discovery aperture")
            site_ids.add(site_id)
    require(len(seen_bases) == 12 and site_ids == set(range(1, 9)),
            "Missing one or more Site slots")
    require(integer(data.get("magics", {}).get("ppu_identity_word"), "magic")
            == 0x4D534C50, "Unexpected identity magic")
    return {"base": base, "size": size, "sites": 8,
            "status": "VALID_PROPOSAL_NOT_HARDWARE_QUALIFIED"}


def _read_text(path: Path, label: str) -> str:
    try:
        result = path.read_text().strip()
    except OSError as exc:
        raise Phase1Error(f"{label}: unavailable ({type(exc).__name__})") from exc
    require(bool(result), f"{label}: empty")
    return result


def _hex_sysfs(path: Path, label: str) -> int:
    return integer(_read_text(path, label), label)


def _link_name(path: Path) -> str | None:
    return path.resolve(strict=True).name if path.is_symlink() else None


def read_uio_snapshot(sysroot: Path) -> list[dict]:
    root = sysroot / "class/uio"
    require(root.is_dir(), "No /sys/class/uio inventory")
    results: list[dict] = []
    try:
        uiopaths = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        raise Phase1Error("Cannot enumerate UIO inventory") from exc
    for uio in uiopaths:
        if not re.fullmatch(r"uio[0-9]+", uio.name):
            continue
        mapsroot = uio / "maps"
        require(mapsroot.is_dir(), f"{uio.name}: no maps directory")
        entries = []
        try:
            map_paths = sorted(mapsroot.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            raise Phase1Error(f"{uio.name}: map enumeration denied") from exc
        for d in map_paths:
            match = re.fullmatch(r"map([0-9]+)", d.name)
            if not match:
                continue
            index = int(match.group(1))
            lo = _hex_sysfs(d / "addr", f"{uio.name}/{d.name} addr")
            size = _hex_sysfs(d / "size", f"{uio.name}/{d.name} size")
            offset = _hex_sysfs(d / "offset", f"{uio.name}/{d.name} offset")
            require(size > 0 and lo + size <= 0x100000000,
                    "Invalid UIO physical range")
            require(0 <= offset < os.sysconf("SC_PAGE_SIZE"),
                    "Invalid UIO alignment offset")
            namepath = d / "name"
            entries.append({"index": index, "addr": lo, "size": size,
                            "offset": offset,
                            "name": namepath.read_text().strip()
                            if namepath.exists() else ""})
        require(bool(entries), f"{uio.name}: no valid maps")
        require(len({m["index"] for m in entries}) == len(entries),
                f"{uio.name}: duplicate map index")
        device = uio / "device"
        driver = device / "driver"
        ofcompat = device / "of_node/compatible"
        compat: list[str] = []
        if ofcompat.exists():
            data = ofcompat.read_bytes()
            require(len(data) <= 2048, "Oversized device-tree compatible")
            compat = [x.decode("utf-8", errors="replace")
                      for x in data.split(b"\x00") if x]
        results.append({
            "device": "/dev/" + uio.name,
            "name": _read_text(uio / "name", f"{uio.name} name"),
            "platform_device": _link_name(device),
            "driver": _link_name(driver),
            "device_tree_compatible": compat,
            "maps": entries,
        })
    require(bool(results), "No UIO entries found")
    return results


def resolve_mapping(uios: list[dict], start: int, size: int,
                    *, page_size: int = 4096) -> dict:
    """Translate UIO mapN selectors and physical subwindow (never mmap)."""
    require(type(start) is int and type(size) is int and size > 0 and
            0 <= start and start + size <= 0x100000000 and
            type(page_size) is int and page_size >= 4096,
            "Invalid requested physical window")
    matched = []
    for uio in uios:
        for m in uio["maps"]:
            if m["addr"] <= start and start + size <= m["addr"] + m["size"]:
                matched.append({
                    "device": uio["device"],
                    "map_index": m["index"],
                    "mmap_selector_bytes": m["index"] * page_size,
                    "window_byte_index": m["offset"] + start - m["addr"],
                    "physical_window_start": start,
                    "window_size": size,
                    "driver": uio["driver"],
                })
    require(len(matched) == 1,
            f"UIO mapping candidate ambiguous/unavailable: {len(matched)} matches")
    return matched[0]


def collect_inventory(sysroot: Path, procroot: Path, contract: dict) -> dict:
    validated = validate_contract(contract)
    uios = read_uio_snapshot(sysroot)
    mapping = resolve_mapping(uios, validated["base"], validated["size"],
                              page_size=os.sysconf("SC_PAGE_SIZE"))
    manager = sysroot / "class/fpga_manager/fpga0/state"
    boot = procroot / "sys/kernel/random/boot_id"
    state = _read_text(manager, "FPGA Manager state")
    boot_id = _read_text(boot, "boot_id")
    bridges = sysroot / "class/fpga_bridge"
    bridge_entries = sorted(p.name for p in bridges.iterdir()) if bridges.is_dir() else []
    return {
        "result": "UIO_MAPPING_CANDIDATE_ONLY",
        "hardware_ready": False,
        "reload_authorized": False,
        "read_only": True,
        "boot_id": boot_id,
        "fpga_manager_state": state,
        "fpga_bridge_sysfs_entries": bridge_entries,
        "uio": uios,
        "candidate_ppu_window": mapping,
        "missing_evidence": [
            "actual Device Tree region/bridge and PS-PL hardware isolation",
            "active kernel and userspace PL consumers + retained mmap audit",
            "image provenance, exact ABI readback and board safe-state",
            "external UART/independent power/SSH recovery qualification",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only FPGA UIO/ABI Phase-1 inventory")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--sysroot", type=Path, default=Path("/sys"))
    parser.add_argument("--procroot", type=Path, default=Path("/proc"))
    args = parser.parse_args(argv)
    try:
        contract = json.loads(args.contract.read_text())
        print(json.dumps(collect_inventory(args.sysroot, args.procroot, contract),
                         indent=2, sort_keys=True))
    except (Phase1Error, OSError, ValueError) as exc:
        print(json.dumps({"result": "BLOCKED", "hardware_ready": False,
                          "reload_authorized": False,
                          "reason": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
