"""Host-only Phase-1 ABI contract and Linux UIO mapping tests.

All device metadata is synthesized under tmp_path; no MMIO or real FPGA access.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from pl.tools.runtime_fpga_phase1 import (
    Phase1Error, collect_inventory, main, read_uio_snapshot,
    resolve_mapping, validate_contract,
)

CONTRACT = (Path(__file__).resolve().parents[1] /
            "verification/runtime_fpga_abi_v1_proposal.json")


@pytest.fixture
def proposal() -> dict:
    return json.loads(CONTRACT.read_text())


def test_valid_proposal_only_not_physical_acceptance(proposal):
    result = validate_contract(proposal)
    assert result == {"base": 0x40000000, "size": 65536, "sites": 8,
                      "status": "VALID_PROPOSAL_NOT_HARDWARE_QUALIFIED"}
    assert all(r["access"] == "ro" for p in proposal["regions"]
               for r in p["registers"])


@pytest.mark.parametrize("change", [
    "wrong_status", "wrong_magic", "wrong_abi", "wrong_endianness",
    "wrong_capacity", "missing_site", "duplicate_site", "swapped_site_id",
    "reserved_write", "misaligned_register", "duplicate_register",
    "missing_reserved_replaced_by_extra_window",
    "writeable_register", "missing_identity", "wrong_physical_base",
])
def test_proposal_invalid_map_fails_closed(proposal, change):
    p = deepcopy(proposal)
    regions = p["regions"]
    if change == "wrong_status":
        p["status"] = "accepted"
    elif change == "wrong_magic":
        p["magics"]["ppu_identity_word"] = "0xDEADBEEF"
    elif change == "wrong_abi":
        p["abi_major"] = 2
    elif change == "wrong_endianness":
        p["wire"]["endianness"] = "big"
    elif change == "wrong_capacity":
        p["ppu_window"]["max_sites"] = 16
    elif change == "missing_site":
        regions.pop()
    elif change == "duplicate_site":
        regions[-1]["base"] = regions[-2]["base"]
    elif change == "swapped_site_id":
        regions[-1]["site_id"] = 7
    elif change == "missing_reserved_replaced_by_extra_window":
        regions[2]["base"] = "0x4000C000"
    elif change == "reserved_write":
        regions[1]["registers"] = [{"name": "poke", "offset": "0x000",
                                    "access": "ro", "width_bits": 32}]
    elif change == "misaligned_register":
        regions[0]["registers"][0]["offset"] = "0x001"
    elif change == "duplicate_register":
        regions[0]["registers"][1]["offset"] = "0x000"
    elif change == "writeable_register":
        regions[0]["registers"][0]["access"] = "rw"
    elif change == "missing_identity":
        regions[0]["registers"] = []
    elif change == "wrong_physical_base":
        p["ppu_window"]["base"] = "0x50000000"
    with pytest.raises(Phase1Error):
        validate_contract(p)


def _make_snapshot(tmp_path):
    sysroot, procroot = tmp_path / "sys", tmp_path / "proc"
    map0 = sysroot / "class/uio/uio3/maps/map0"
    map0.mkdir(parents=True)
    for name, value in (("addr", "0x40000000"), ("size", "0x10000"),
                        ("offset", "0x0"), ("name", "plasma-proposed-window")):
        (map0 / name).write_text(value)
    uio = map0.parents[1]
    (uio / "name").write_text("fabric-uio")
    manager = sysroot / "class/fpga_manager/fpga0/state"
    manager.parent.mkdir(parents=True)
    manager.write_text("operating")
    bridge = sysroot / "class/fpga_bridge/fpga_bridge0"
    bridge.parent.mkdir(parents=True)
    bridge.write_text("unknown")
    boot = procroot / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("synthetic-boot-id")
    return sysroot, procroot, map0


def test_single_uio_covers_candidate_64k_but_does_not_qualify_hardware(
        tmp_path, proposal):
    sysroot, procroot, _ = _make_snapshot(tmp_path)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    report = collect_inventory(sysroot, procroot, proposal)
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert report["result"] == "UIO_MAPPING_CANDIDATE_ONLY"
    assert report["hardware_ready"] is False
    assert report["reload_authorized"] is False
    assert report["boot_id"] == "synthetic-boot-id"
    assert report["fpga_bridge_sysfs_entries"] == ["fpga_bridge0"]
    assert report["candidate_ppu_window"]["mmap_selector_bytes"] == 0
    assert report["candidate_ppu_window"]["window_byte_index"] == 0
    assert len(report["missing_evidence"]) >= 4
    assert before == after  # No file changes, device access or service mutation.


def test_site_region_maps_inside_single_uio_map_zero(tmp_path):
    sysroot, _, _ = _make_snapshot(tmp_path)
    uios = read_uio_snapshot(sysroot)
    a = resolve_mapping(uios, 0x40004000, 4096)
    b = resolve_mapping(uios, 0x4000B000, 4096)
    assert a["map_index"] == 0 and b["map_index"] == 0
    assert a["mmap_selector_bytes"] == 0
    assert a["window_byte_index"] == 0x4000
    assert b["window_byte_index"] == 0xB000


def test_uio_map_index_is_file_selector_not_physical_offset(tmp_path):
    sysroot, _, map0 = _make_snapshot(tmp_path)
    map2 = map0.parent / "map2"
    map2.mkdir()
    for name, value in (("addr", "0x50000000"), ("size", "0x1000"),
                        ("offset", "0x80"), ("name", "alternate")):
        (map2 / name).write_text(value)
    uios = read_uio_snapshot(sysroot)
    m = resolve_mapping(uios, 0x50000200, 0x100, page_size=4096)
    assert m["map_index"] == 2
    assert m["mmap_selector_bytes"] == 8192
    assert m["window_byte_index"] == 0x80 + 0x200
    assert m["physical_window_start"] == 0x50000200


@pytest.mark.parametrize("bad", ["absent", "zero", "cross_boundary"])
def test_unmapped_or_ambiguous_window_fails_closed(tmp_path, bad):
    sysroot, _, map0 = _make_snapshot(tmp_path)
    if bad == "absent":
        windows = (0x50000000, 4096)
    elif bad == "zero":
        windows = (0x40000000, 0)
    else:
        windows = (0x4000F000, 8192)
    with pytest.raises(Phase1Error):
        resolve_mapping(read_uio_snapshot(sysroot), *windows)


def test_partial_overlap_cannot_be_ignored_as_a_safe_full_mapping(tmp_path):
    sysroot, _, _ = _make_snapshot(tmp_path)
    other = sysroot / "class/uio/uio4"
    map0 = other / "maps/map0"
    map0.mkdir(parents=True)
    (other / "name").write_text("partial-competing-owner")
    for name, value in (("addr", "0x4000F000"), ("size", "0x1000"),
                        ("offset", "0x0"), ("name", "overlap")):
        (map0 / name).write_text(value)
    with pytest.raises(Phase1Error, match="overlaps"):
        resolve_mapping(read_uio_snapshot(sysroot), 0x40000000, 65536)


def test_duplicate_uio_ownership_is_not_chosen_arbitrarily(tmp_path):
    sysroot, _, map0 = _make_snapshot(tmp_path)
    other = sysroot / "class/uio/uio4"
    (other / "maps/map0").mkdir(parents=True)
    (other / "name").write_text("another-owner")
    for item in map0.iterdir():
        (other / "maps/map0" / item.name).write_bytes(item.read_bytes())
    with pytest.raises(Phase1Error, match="ambiguous"):
        resolve_mapping(read_uio_snapshot(sysroot), 0x40000000, 65536)


@pytest.mark.parametrize("bad", ["missing_offset", "unaligned_offset",
                                  "bad_physical_range", "missing_class"])
def test_malformed_or_missing_sysfs_fails_closed(tmp_path, bad):
    sysroot, _, map0 = _make_snapshot(tmp_path)
    if bad == "missing_offset":
        (map0 / "offset").unlink()
    elif bad == "unaligned_offset":
        (map0 / "offset").write_text("0x10000")
    elif bad == "bad_physical_range":
        (map0 / "size").write_text("0xFFFFFFFF")
    else:
        # Simulate missing UIO sysfs (not evidence that there is no device).
        sysroot = tmp_path / "missing_sys"
    with pytest.raises(Phase1Error):
        read_uio_snapshot(sysroot)


def test_inventory_missing_manager_never_claims_ready(tmp_path, proposal):
    sysroot, procroot, _ = _make_snapshot(tmp_path)
    (sysroot / "class/fpga_manager/fpga0/state").unlink()
    with pytest.raises(Phase1Error, match="FPGA Manager"):
        collect_inventory(sysroot, procroot, proposal)


def test_cli_fail_closed_json_output_without_writes(tmp_path, proposal, capsys):
    sysroot, procroot, _ = _make_snapshot(tmp_path)
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(proposal))
    assert main(["--contract", str(contract), "--sysroot", str(sysroot),
                 "--procroot", str(procroot)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hardware_ready"] is False
    assert data["reload_authorized"] is False
    (sysroot / "class/fpga_manager/fpga0/state").unlink()
    assert main(["--contract", str(contract), "--sysroot", str(sysroot),
                 "--procroot", str(procroot)]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["result"] == "BLOCKED"
    assert data["hardware_ready"] is False
