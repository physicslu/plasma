"""LT02-05 offline P0 fault injection. No board, /dev/mem or FPGA touched."""
from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from pl.hil.lt02 import contract as c
from pl.hil.lt02 import preflight
from pl.hil.swd04.contract import REQUIRED_SERVICES
from pl.tests.test_z2_lt02_axi_build import handoff


@pytest.fixture
def fixture(tmp_path: Path, monkeypatch):
    paths = {name: tmp_path / name for name in (
        "candidate.bit", "candidate.hwh", "candidate.bin",
        "base.bin", "base.hwh", "manifest.json",
    )}
    for name, path in paths.items():
        if not name.endswith((".hwh", ".json")):
            path.write_bytes(name.encode())
    ET.ElementTree(handoff()).write(paths["candidate.hwh"])
    monkeypatch.setattr(c, "RECOVERY_BIN_SHA256", c.digest(paths["base.bin"]))
    monkeypatch.setattr(c, "RECOVERY_HWH_SHA256", c.digest(paths["base.hwh"])
                        if paths["base.hwh"].exists() else "0" * 64)
    # Original PYNQ base HWH is only SHA-256 checked and never parsed as LT02.
    paths["base.hwh"].write_bytes(b"original PYNQ base HWH")
    monkeypatch.setattr(c, "RECOVERY_HWH_SHA256", c.digest(paths["base.hwh"]))
    source = "a" * 40
    manifest = {
        "source_git_sha": source, "build_id": source[:32],
        "design_variant": "lt02_axi_scratchpad_internal_dpidr_fixture",
        "bitstream_sha256": c.digest(paths["candidate.bit"]),
        "hwh_sha256": c.digest(paths["candidate.hwh"]),
        "bitstream_file": paths["candidate.bit"].name,
        "hwh_file": paths["candidate.hwh"].name,
        "fpga_part": "xc7z020clg400-1",
        "board_part": "tul.com.tw:pynq-z2:part0:1.0",
        "bitstream_version": "0.1.0",
        "identity_schema_version": 1,
        "hardware_abi_version": 1,
        "swd_command_abi_version": 1,
        "swd_transaction_abi_version": 1,
        "lt02_abi_version": 1,
        "lt02_scratchpad_bytes": 2048,
        "lt02_reference_site_id": 1,
        "external_pl_io": False, "capability_flags": 0,
        "physical_programming_qualified": False,
        "hardware_runtime_ready": False,
        "target_programming_qualified": False,
        "loading_safety": "NOT_QUALIFIED",
        "toolchain": {"name": "Vivado", "version": "2026.1"},
        "acceptance": {
            "LT02_HOST_RTL": "PASS", "LT02_IMPLEMENTED_HOST": "PASS",
            "Z2_HIL": "NOT_RUN", "physical_swd": "NOT_RUN",
            "real_ic_programming": "NOT_RUN",
        },
        "axi_address_map": {
            name: {"base_address": f"0x{addr:08X}", "segment_size_bytes": 4096}
            for name, addr in c.AXI_BASES.items()
        },
    }
    paths["manifest.json"].write_text(json.dumps(manifest))
    approval = {"schema_version": 1, "source_git_sha": source}
    for key, filename in (
        ("candidate_bit_sha256", "candidate.bit"),
        ("candidate_hwh_sha256", "candidate.hwh"),
        ("candidate_manifest_sha256", "manifest.json"),
        ("candidate_bin_sha256", "candidate.bin"),
        ("recovery_bin_sha256", "base.bin"),
        ("recovery_hwh_sha256", "base.hwh"),
    ):
        approval[key] = c.digest(paths[filename])
    inventory = {
        "architecture": "armv7l", "pynq_version": "3.1.1",
        "fpga_manager_state": "operating", "fclk0_hz": 100000000,
        "sysfs_read_only": True, "device_model_confirmed": True,
        "metadata_sha256": "b" * 64,
        "services": {service: "active" for service in REQUIRED_SERVICES},
        "uio": [{"name": "fabric", "address": "0x40000000",
                 "size": "0x00010000"}],
    }
    operator = {"schema_version": 1,
                **{name: True for name in c.OPERATOR_REQUIRED}}
    candidate = c.Candidate(
        paths["candidate.bit"], paths["candidate.hwh"],
        paths["manifest.json"], paths["candidate.bin"],
        paths["base.bin"], paths["base.hwh"],
    )
    return candidate, paths, approval, inventory, operator


def _resign_manifest(paths, approval):
    approval["candidate_manifest_sha256"] = c.digest(paths["manifest.json"])


def test_five_aperture_offline_pass_is_never_live_authorization(fixture):
    candidate, _, approval, inventory, operator = fixture
    result = c.plan(candidate, approval, inventory, operator)
    assert result["stage"] == "P0_OFFLINE"
    assert result["result"] == "PASS"
    assert result["go_live_authorization"] == "NOT_GRANTED"
    assert result["fpga_loading"] == "NOT_RUN"
    assert result["native_mmio_hil"] == "NOT_RUN"
    assert result["recovery_execution"] == "NOT_RUN"
    assert len(c.verify_hwh(candidate.hwh)) == 5


@pytest.mark.parametrize("filename", [
    "candidate.bit", "candidate.hwh", "candidate.bin", "base.bin",
    "base.hwh", "manifest.json",
])
def test_corrupted_bytes_fail_closed(fixture, filename):
    candidate, paths, approval, inventory, operator = fixture
    paths[filename].write_bytes(b"wrong byte sequence")
    with pytest.raises(c.SafetyError):
        c.plan(candidate, approval, inventory, operator)


@pytest.mark.parametrize("field", [
    "candidate_bit_sha256", "candidate_hwh_sha256",
    "candidate_manifest_sha256", "candidate_bin_sha256",
    "recovery_bin_sha256", "recovery_hwh_sha256",
])
def test_missing_independently_approved_digest_fails(fixture, field):
    candidate, _, approval, inventory, operator = fixture
    approval.pop(field)
    with pytest.raises(c.SafetyError):
        c.plan(candidate, approval, inventory, operator)


@pytest.mark.parametrize(("field", "value"), [
    ("source_git_sha", "bad"),
    ("design_variant", "swd03_axi_internal_dpidr_fixture"),
    ("lt02_scratchpad_bytes", 4096),
    ("lt02_reference_site_id", 2),
    ("lt02_abi_version", 2),
    ("hardware_runtime_ready", True),
    ("external_pl_io", True),
    ("capability_flags", 1),
    ("physical_programming_qualified", True),
    ("loading_safety", "QUALIFIED"),
    ("toolchain", {"name": "Vivado", "version": "2025.1"}),
])
def test_semantic_manifest_forgery_rejected_even_when_rehashed(
        fixture, field, value):
    candidate, paths, approval, inventory, operator = fixture
    obj = json.loads(paths["manifest.json"].read_text())
    obj[field] = value
    paths["manifest.json"].write_text(json.dumps(obj))
    _resign_manifest(paths, approval)
    with pytest.raises(c.SafetyError):
        c.plan(candidate, approval, inventory, operator)


@pytest.mark.parametrize("fault", [
    "lt02_decoder", "lt02_address", "lt02_master", "lt02_clock",
    "lt02_reset", "lt02_missing", "external_pin",
])
def test_hwh_faults_rejected_even_when_approved_hashes_rewritten(fixture, fault):
    candidate, paths, approval, inventory, operator = fixture
    xml = ET.parse(paths["candidate.hwh"])
    root = xml.getroot()
    module = root.find("./MODULE[@INSTANCE='lt02_0']")
    addr = root.find("./MEMRANGE[@INSTANCE='lt02_0']")
    if fault == "lt02_decoder":
        module.find("./PARAMETER[@NAME='AXI_BASE_ADDRESS']").set("VALUE", "0x40005000")
    elif fault == "lt02_address":
        addr.set("HIGHVALUE", "0x40005FFF")
    elif fault == "lt02_master":
        addr.set("MASTERBUSINTERFACE", "M_AXI_GP1")
    elif fault == "lt02_clock":
        module.find("./PORT[@NAME='s_axi_aclk']").set("SIGNAME", "wrong")
    elif fault == "lt02_reset":
        module.find("./PORT[@NAME='s_axi_aresetn']").set("SIGNAME", "wrong")
    elif fault == "lt02_missing":
        root.remove(addr)
    elif fault == "external_pin":
        ET.SubElement(ET.SubElement(root, "EXTERNALPORTS"), "PORT",
                      NAME="PMOD_SWD")
    xml.write(paths["candidate.hwh"])
    approval["candidate_hwh_sha256"] = c.digest(paths["candidate.hwh"])
    manifest = json.loads(paths["manifest.json"].read_text())
    manifest["hwh_sha256"] = approval["candidate_hwh_sha256"]
    paths["manifest.json"].write_text(json.dumps(manifest))
    _resign_manifest(paths, approval)
    with pytest.raises((ValueError, KeyError, c.SafetyError)):
        c.plan(candidate, approval, inventory, operator)


@pytest.mark.parametrize("field", c.OPERATOR_REQUIRED)
def test_any_missing_operator_safety_gate_is_no_go(fixture, field):
    candidate, _, approval, inventory, operator = fixture
    operator[field] = False
    with pytest.raises(c.SafetyError):
        c.plan(candidate, approval, inventory, operator)


@pytest.mark.parametrize(("field", "value"), [
    ("architecture", "x86_64"),
    ("pynq_version", "3.0"),
    ("fclk0_hz", 0),
    ("device_model_confirmed", False),
    ("metadata_sha256", "unknown"),
    ("fpga_manager_state", "unknown"),
    ("sysfs_read_only", False),
    ("services", {}),
    ("uio", []),
])
def test_incomplete_readonly_z2_inventory_is_no_go(fixture, field, value):
    candidate, _, approval, inventory, operator = fixture
    inventory[field] = value
    with pytest.raises(c.SafetyError):
        c.plan(candidate, approval, inventory, operator)


def test_cli_does_not_read_mem_and_refuses_overwrite(tmp_path, fixture):
    candidate, paths, approval, inventory, operator = fixture
    inputs = {
        "approved": approval, "inventory": inventory, "operator": operator,
    }
    for key, value in inputs.items():
        (tmp_path / f"{key}.json").write_text(json.dumps(value))
    output = tmp_path / "p0.json"
    argv = [
        "--bit", str(candidate.bit), "--hwh", str(candidate.hwh),
        "--manifest", str(candidate.manifest),
        "--candidate-bin", str(candidate.candidate_bin),
        "--recovery-bin", str(candidate.recovery_bin),
        "--recovery-hwh", str(candidate.recovery_hwh),
        "--approved-hashes", str(tmp_path / "approved.json"),
        "--inventory", str(tmp_path / "inventory.json"),
        "--operator", str(tmp_path / "operator.json"),
        "--output", str(output),
    ]
    assert preflight.main(argv) == 0
    assert json.loads(output.read_text())["native_mmio_hil"] == "NOT_RUN"
    assert preflight.main(argv) == 2
