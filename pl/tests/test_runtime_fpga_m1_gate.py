"""Offline-only M1 blocker tests: never open a device or execute HIL."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from pl.tools.runtime_fpga_m1_gate import ReviewRefused, assess_z2_m1_inventory, main


@pytest.fixture
def z2_snapshot() -> dict:
    return {
        "result": "UIO_MAPPING_CANDIDATE_ONLY",
        "read_only": True,
        "hardware_ready": False,
        "reload_authorized": False,
        "boot_id": "fixture-boot-a",
        "kernel_release": "6.6.10-xilinx-fixture",
        "fpga_manager_state": "operating",
        "fpga_bridge_sysfs_entries": [],
        "uio": [{
            "device": "/dev/uio0",
            "name": "fabric",
            "driver": "uio_pdrv_genirq",
            "maps": [{"index": 0, "addr": 0x40000000,
                      "size": 0x10000, "offset": 0}],
        }],
        "candidate_ppu_window": {
            "device": "/dev/uio0", "driver": "uio_pdrv_genirq",
            "map_index": 0, "mmap_selector_bytes": 0,
            "window_byte_index": 0, "physical_window_start": 0x40000000,
            "window_size": 0x10000,
        },
    }


def test_known_z2_observation_remains_no_go(z2_snapshot):
    r = assess_z2_m1_inventory(z2_snapshot)
    assert r["verdict"] == "M1_NO_GO"
    assert not r["reload_authorized"] and not r["hardware_ready"]
    assert not r["inventory_is_attestation"]
    assert r["observed_uio_map0"] and r["observed_bridge_entry_count"] == 0
    assert "NO_REGISTERED_FPGA_BRIDGE_OBSERVED" in r["blockers"]
    assert "PS_PL_AXI_DRAIN_AND_ABORT_CONTAINMENT_UNPROVEN" in r["blockers"]
    assert "KERNEL_SOURCE_BINARY_PROVENANCE_UNVERIFIED" in r["blockers"]
    assert "ABI_V1_COMPATIBLE_IMAGES_AND_READBACK_NOT_QUALIFIED" in r["blockers"]


def test_invented_bridge_name_never_means_safe_isolation(z2_snapshot):
    z2_snapshot["fpga_bridge_sysfs_entries"] = ["fpga_bridge0"]
    r = assess_z2_m1_inventory(z2_snapshot)
    assert r["verdict"] == "M1_NO_GO"
    assert "BRIDGE_SYSFS_NAME_NOT_PHYSICAL_ISOLATION_EVIDENCE" in r["blockers"]
    assert "MANAGER_SYSFS_PATH_NOT_EQUIVALENT_TO_REGION_BRIDGE_ISOLATION" in r["blockers"]


@pytest.mark.parametrize("field,invalid", [
    ("hardware_ready", True), ("hardware_ready", None),
    ("reload_authorized", True), ("reload_authorized", 0),
    ("read_only", False), ("read_only", "true"),
    ("result", "HARDWARE_QUALIFIED"), ("boot_id", ""),
    ("boot_id", None), ("kernel_release", "not-safe\x00text"),
    ("fpga_manager_state", ""), ("fpga_bridge_sysfs_entries", None),
    ("fpga_bridge_sysfs_entries", ["bridge0", "bridge0"]),
    ("fpga_bridge_sysfs_entries", ["../../../malicious"]),
])
def test_unknown_or_unsafe_inventory_refused(z2_snapshot, field, invalid):
    z2_snapshot[field] = invalid
    with pytest.raises(ReviewRefused):
        assess_z2_m1_inventory(z2_snapshot)


@pytest.mark.parametrize("field,invalid", [
    ("map_index", 1), ("map_index", True),
    ("mmap_selector_bytes", 0x40000000),
    ("window_byte_index", 4096),
    ("physical_window_start", 0x50000000),
    ("window_size", 8192),
    ("driver", "other_driver"),
    ("device", "/dev/mem"),
])
def test_candidate_wrong_range_or_selector_refused(z2_snapshot, field, invalid):
    z2_snapshot["candidate_ppu_window"][field] = invalid
    with pytest.raises(ReviewRefused):
        assess_z2_m1_inventory(z2_snapshot)


@pytest.mark.parametrize("field,invalid", [
    ("driver", "other_driver"), ("device", "/dev/uio7"),
    ("maps", []), ("maps", "not-list"),
])
def test_observed_driver_or_map_must_match(z2_snapshot, field, invalid):
    z2_snapshot["uio"][0][field] = invalid
    with pytest.raises(ReviewRefused):
        assess_z2_m1_inventory(z2_snapshot)


@pytest.mark.parametrize("field,invalid", [
    ("index", 1), ("addr", 0x40001000), ("size", 0x1000),
    ("offset", 0x80),
])
def test_mapping_drift_is_not_a_valid_review(z2_snapshot, field, invalid):
    z2_snapshot["uio"][0]["maps"][0][field] = invalid
    with pytest.raises(ReviewRefused):
        assess_z2_m1_inventory(z2_snapshot)


def test_duplicate_mapping_does_not_claim_unique_uio_owner(z2_snapshot):
    z2_snapshot["uio"].append(deepcopy(z2_snapshot["uio"][0]))
    with pytest.raises(ReviewRefused):
        assess_z2_m1_inventory(z2_snapshot)


def test_offline_cli_sanitizes_input_and_never_reports_go(tmp_path, capsys,
                                                          z2_snapshot):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(z2_snapshot))
    assert main(["--inventory", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "M1_NO_GO"
    assert out["reload_authorized"] is False
    assert "fixture-boot-a" not in json.dumps(out)  # Never echo boot identity


def test_cli_rejects_malformed_or_missing_file(tmp_path, capsys):
    missing = tmp_path / "missing.json"
    assert main(["--inventory", str(missing)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "M1_NO_GO"
    assert out["hardware_ready"] is False
    missing.write_text('{"unexpected": 1}')
    assert main(["--inventory", str(missing)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert "INVENTORY_INVALID" in out["error"]
