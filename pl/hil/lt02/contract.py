"""LT02-05 P0: inert, independently hash-bound five-aperture HIL preflight.

No /dev/mem, FPGA Manager writes, network calls, service restarts or DUT IO.
A software PASS never grants a live Z2 load or native MMIO authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

from pl.hil.swd04.contract import (
    REQUIRED_SERVICES, RECOVERY_BIN_SHA256, RECOVERY_HWH_SHA256,
)

PL = Path(__file__).resolve().parents[2]
LT02_ARTIFACT = PL / "projects/z2-lt02-axi/artifact.py"
AXI_BASES = {
    "identity_0": 0x40000000, "control_0": 0x40001000,
    "swd_0": 0x40002000, "transaction_0": 0x40003000,
    "lt02_0": 0x40004000,
}
OPERATOR_REQUIRED = (
    "exclusive_pl_ownership_confirmed",
    "uart_console_verified",
    "independent_power_recovery_verified",
    "maintenance_window_confirmed",
    "restoration_operator_ready",
    "no_external_dut_connected",
    "original_metadata_backed_up",
    "uio_driver_reconciliation_planned",
    "bitstream_to_bin_conversion_verified",
)


class SafetyError(RuntimeError):
    """One or more independent mandatory preflight gates failed."""


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise SafetyError(msg)


def digest(path: Path) -> str:
    require(path.is_file() and path.stat().st_size > 0, "Missing/nonempty file: " + str(path))
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_object(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text())
    require(type(obj) is dict, "Expected JSON object: " + str(path))
    return obj


def sha256_text(value: object) -> bool:
    return type(value) is str and bool(re.fullmatch(r"[0-9a-f]{64}", value))


@dataclass(frozen=True)
class Candidate:
    bit: Path
    hwh: Path
    manifest: Path
    candidate_bin: Path
    recovery_bin: Path
    recovery_hwh: Path


def verify_hwh(path: Path) -> dict[str, Any]:
    """Reuse the exact implemented-build HWH decoder/clock/reset checks."""
    spec = importlib.util.spec_from_file_location("lt02_artifact_p0", LT02_ARTIFACT)
    require(spec is not None and spec.loader is not None, "Missing LT02 HWH validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mapping = module.verify_hwh(path)
    require(type(mapping) is dict and set(mapping) == set(AXI_BASES),
            "HWH does not expose exactly five reviewed apertures")
    return mapping


def verify_candidate(candidate: Candidate, approved: dict[str, Any]) -> dict[str, str]:
    """Approved hashes are a separate operator-reviewed record, never inferred."""
    require(approved.get("schema_version") == 1, "Approval schema missing")
    src = approved.get("source_git_sha")
    require(type(src) is str and bool(re.fullmatch(r"[0-9a-f]{40}", src)),
            "Source Git SHA is not a full 40-hex commit")
    fields = {
        "candidate_bit_sha256": candidate.bit,
        "candidate_hwh_sha256": candidate.hwh,
        "candidate_manifest_sha256": candidate.manifest,
        "candidate_bin_sha256": candidate.candidate_bin,
        "recovery_bin_sha256": candidate.recovery_bin,
        "recovery_hwh_sha256": candidate.recovery_hwh,
    }
    hashes: dict[str, str] = {}
    for field, path in fields.items():
        expected = approved.get(field)
        require(sha256_text(expected), "Missing independently pinned digest: " + field)
        observed = digest(path)
        require(observed == expected, "Artifact SHA256 mismatch: " + field)
        hashes[field] = observed
    require(hashes["recovery_bin_sha256"] == RECOVERY_BIN_SHA256,
            "Recovery BIN differs from verified original PYNQ base.bin")
    require(hashes["recovery_hwh_sha256"] == RECOVERY_HWH_SHA256,
            "Recovery HWH differs from verified original PYNQ base.hwh")

    manifest = json_object(candidate.manifest)
    for key, expected in {
        "source_git_sha": src, "build_id": src[:32],
        "design_variant": "lt02_axi_scratchpad_internal_dpidr_fixture",
        "bitstream_sha256": hashes["candidate_bit_sha256"],
        "hwh_sha256": hashes["candidate_hwh_sha256"],
        "bitstream_file": candidate.bit.name,
        "hwh_file": candidate.hwh.name,
        "fpga_part": "xc7z020clg400-1",
        "board_part": "tul.com.tw:pynq-z2:part0:1.0",
        "bitstream_version": "0.1.0",
        "lt02_scratchpad_bytes": 2048,
        "lt02_reference_site_id": 1,
        "external_pl_io": False,
        "capability_flags": 0,
        "physical_programming_qualified": False,
        "hardware_runtime_ready": False,
        "target_programming_qualified": False,
        "loading_safety": "NOT_QUALIFIED",
    }.items():
        actual = manifest.get(key)
        require(type(actual) is type(expected) and actual == expected,
                "Manifest differs from reviewed LT02 contract: " + key)
    for name in (
        "identity_schema_version", "hardware_abi_version",
        "swd_command_abi_version", "swd_transaction_abi_version",
        "lt02_abi_version",
    ):
        require(type(manifest.get(name)) is int and manifest[name] == 1,
                "Missing/incompatible ABI: " + name)
    require(manifest.get("toolchain") == {"name": "Vivado", "version": "2026.1"},
            "Vivado 2026.1 toolchain unproven")
    require(manifest.get("acceptance") == {
        "LT02_HOST_RTL": "PASS", "LT02_IMPLEMENTED_HOST": "PASS",
        "Z2_HIL": "NOT_RUN", "physical_swd": "NOT_RUN",
        "real_ic_programming": "NOT_RUN",
    }, "Manifest acceptance improperly claims hardware evidence")
    actual_map = verify_hwh(candidate.hwh)
    require(manifest.get("axi_address_map") == actual_map,
            "Manifest and actual HWH five-aperture map differ")
    require(set(actual_map) == set(AXI_BASES), "Unexpected AXI aperture")
    for name, address in AXI_BASES.items():
        require(actual_map[name] == {
            "base_address": f"0x{address:08X}",
            "segment_size_bytes": 4096,
        }, "Unexpected AXI map: " + name)
    return hashes


def verify_readiness(inventory: dict[str, Any], operator: dict[str, Any]) -> None:
    """These are manually reviewed snapshots/assertions, not machine-proof."""
    require(inventory.get("architecture") == "armv7l", "Expected ARMv7 PYNQ-Z2")
    require(inventory.get("pynq_version") == "3.1.1", "Unknown PYNQ version")
    require(inventory.get("fpga_manager_state") == "operating",
            "FPGA manager not operating at inventory time")
    require(type(inventory.get("fclk0_hz")) is int and
            inventory["fclk0_hz"] == 100000000, "FCLK0 not 100MHz")
    require(inventory.get("sysfs_read_only") is True, "Inventory not read-only")
    require(inventory.get("device_model_confirmed") is True, "Z2 identity unverified")
    require(sha256_text(inventory.get("metadata_sha256")),
            "Preload PYNQ metadata digest missing")
    services = inventory.get("services")
    require(type(services) is dict, "No services inventory")
    for svc in REQUIRED_SERVICES:
        require(services.get(svc) == "active", "Original service is not active: " + svc)
    uio = inventory.get("uio")
    require(type(uio) is list, "UIO inventory absent")
    rows = [x for x in uio if type(x) is dict and x.get("name") == "fabric" and
            x.get("address") == "0x40000000" and x.get("size") == "0x00010000"]
    require(len(rows) == 1, "Original fabric UIO binding differs")
    require(operator.get("schema_version") == 1, "Operator schema missing")
    for field in OPERATOR_REQUIRED:
        require(operator.get(field) is True, "Operator prerequisite NO-GO: " + field)


def plan(candidate: Candidate, approved: dict[str, Any], inventory: dict[str, Any],
         operator: dict[str, Any]) -> dict[str, Any]:
    hashes = verify_candidate(candidate, approved)
    verify_readiness(inventory, operator)
    return {
        "qualification": "LT02-05", "stage": "P0_OFFLINE",
        "result": "PASS", "candidate_source": approved["source_git_sha"],
        "artifact_sha256": hashes,
        "go_live_authorization": "NOT_GRANTED",
        "fpga_loading": "NOT_RUN", "native_mmio_hil": "NOT_RUN",
        "recovery_execution": "NOT_RUN", "manager_ui": "NOT_IMPLEMENTED",
        "electrical_dut": "NOT_RUN",
        "warning": "P0 is an offline record consistency check, not physical attestation",
    }
