"""SWD-04 fail-closed offline qualification contracts (no hardware I/O).

This module intentionally does not load FPGA firmware, inspect /dev/mem, alter
drivers or send commands to a connected target. Evidence inputs are snapshots
from a *separate*, explicitly scheduled maintenance process.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCE_SHA = "d39e85194f27e20f0ae7f2eb7c0623b293ff1108"
BIT_SHA256 = "80e8a6ef0c86ac000f9f0b16af2ee25ba3f6f1bb61dd3f3e7ab232508bc4c38b"
HWH_SHA256 = "96ce1767ec2ca1ec4c45aaa0cdb4b674bd8349f5753e3f35728d18cf646843bc"
RECOVERY_BIN_SHA256 = "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c"
RECOVERY_HWH_SHA256 = "222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a"
DPIDR = 0x2BA01477

AXI_BASES = {
    "identity_0": 0x40000000,
    "control_0": 0x40001000,
    "swd_0": 0x40002000,
    "transaction_0": 0x40003000,
}
SEGMENT_SIZE = 4096

# Only these MMIO words are explicitly part of SWD-04's HIL-01/02/03.
IDENTITY_OFFSETS = tuple(range(0, 0x20, 4))
READ_WHITELIST = frozenset(
    {AXI_BASES["identity_0"] + x for x in IDENTITY_OFFSETS}
    | {AXI_BASES["control_0"] + 0x04}
    | {AXI_BASES["swd_0"] + x for x in (0x00, 0x1C)}
    | {AXI_BASES["transaction_0"] + x for x in (
        0x00, 0x08, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C
    )}
)
WRITE_WHITELIST = frozenset({
    AXI_BASES["transaction_0"] + 0x04,
    AXI_BASES["transaction_0"] + 0x08,
    AXI_BASES["transaction_0"] + 0x10,
})
COMMAND = AXI_BASES["transaction_0"] + 0x04
CONFIG = AXI_BASES["transaction_0"] + 0x08
HALF = AXI_BASES["transaction_0"] + 0x10
STATUS = AXI_BASES["transaction_0"] + 0x24
META = AXI_BASES["transaction_0"] + 0x28
RDATA = AXI_BASES["transaction_0"] + 0x2C
READY = 1 << 1
RESP_VALID = 1 << 2

REQUIRED_SERVICES = (
    "jupyter.service",
    "plasma-bootstrap.service",
    "plasma-server.service",
    "plasma-web.service",
    "plasma-runtime-activation.service",
)


class SafetyError(RuntimeError):
    """A hard safety/qualification gate did not pass."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SafetyError(message)


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    _require(type(data) is dict, "Expected JSON object: " + str(path))
    return data


@dataclass(frozen=True)
class Candidate:
    bit: Path
    hwh: Path
    manifest: Path
    recovery_bin: Path
    recovery_hwh: Path


def verify_artifacts(candidate: Candidate) -> dict[str, str]:
    """Independent, immutable verification; no device access."""
    paths = {
        "bit": (candidate.bit, BIT_SHA256),
        "hwh": (candidate.hwh, HWH_SHA256),
        "recovery_bin": (candidate.recovery_bin, RECOVERY_BIN_SHA256),
        "recovery_hwh": (candidate.recovery_hwh, RECOVERY_HWH_SHA256),
    }
    for name, (path, expected) in paths.items():
        _require(path.is_file() and path.stat().st_size > 0,
                 "Missing nonempty artifact: " + name)
        _require(sha256_file(path) == expected, "SHA256 mismatch: " + name)

    doc = _read_json(candidate.manifest)
    _require(doc.get("source_git_sha") == SOURCE_SHA, "Wrong source commit")
    _require(doc.get("bitstream_sha256") == BIT_SHA256, "BIT manifest hash differs")
    _require(doc.get("hwh_sha256") == HWH_SHA256, "HWH manifest hash differs")
    _require(doc.get("design_variant") == "swd03_axi_internal_dpidr_fixture",
             "Not the approved internal fixture design")
    _require(doc.get("hardware_runtime_ready") is False,
             "Manifest improperly claims runtime hardware qualification")
    _require(doc.get("physical_programming_qualified") is False,
             "Manifest improperly claims physical programming qualification")
    mapping = doc.get("axi_address_map", {})
    _require(type(mapping) is dict and set(mapping) == set(AXI_BASES),
             "Manifest four-aperture map missing/extra")
    for name, base in AXI_BASES.items():
        item = mapping.get(name, {})
        _require(
            type(item) is dict
            and item.get("base_address") == f"0x{base:08X}"
            and item.get("segment_size_bytes") == SEGMENT_SIZE,
            "Manifest AXI map mismatch: " + name,
        )
    return {name: digest for name, (_, digest) in paths.items()}


def verify_inventory(inventory: dict[str, Any], attestation: dict[str, Any]) -> None:
    """Fail closed on a stale or unsafe read-only Z2 inventory.

    Attestations are *operator assertions*, not machine-proven capability.
    Unknown/missing fields are an explicit NO-GO.
    """
    _require(inventory.get("architecture") == "armv7l", "Not proven ARMv7 target")
    _require(inventory.get("pynq_version") == "3.1.1", "Unexpected PYNQ version")
    _require(inventory.get("fpga_manager_state") == "operating",
             "FPGA Manager not operating")
    _require(inventory.get("fclk0_hz") == 100000000, "FCLK0 not 100MHz")
    _require(inventory.get("sysfs_read_only") is True,
             "Inventory is not marked read-only")
    _require(inventory.get("device_model_confirmed") is True,
             "PYNQ-Z2 board identity not independently confirmed")
    services = inventory.get("services")
    _require(type(services) is dict, "Service snapshot missing")
    for service in REQUIRED_SERVICES:
        _require(services.get(service) == "active",
                 "Preload service state unexpected: " + service)
    uio = inventory.get("uio")
    _require(type(uio) is list, "UIO inventory missing")
    fabric = [
        item for item in uio
        if type(item) is dict
        and item.get("name") == "fabric"
        and item.get("address") == "0x40000000"
    ]
    _require(len(fabric) == 1 and fabric[0].get("size") == "0x00010000",
             "Preload fabric UIO mapping differs from accepted HIL-PSPL-01")
    _require(inventory.get("potential_pl_users_cleared") is True,
             "Cannot prove PL consumer isolation by fd scan alone")
    required = (
        "uart_console_verified",
        "independent_power_recovery_verified",
        "maintenance_window_confirmed",
        "restoration_operator_ready",
        "no_external_dut_connected",
        "original_metadata_backed_up",
        "uio_driver_reconciliation_planned",
    )
    _require(attestation.get("schema_version") == 1, "Attestation schema mismatch")
    for key in required:
        _require(attestation.get(key) is True,
                 "Missing operator prerequisite (not self-proven): " + key)


def plan(candidate: Candidate, inventory: dict[str, Any],
         attestation: dict[str, Any]) -> dict[str, Any]:
    digests = verify_artifacts(candidate)
    verify_inventory(inventory, attestation)
    return {
        "qualification": "SWD-04",
        "preflight": "PASS",
        "candidate_source": SOURCE_SHA,
        "sha256": digests,
        "go_live_authorization": "NOT_GRANTED",
        "allowed_actions": ["staged_read_only_inventory", "offline_mmio_plan"],
        "hardware_access": "NOT_RUN",
        "fpga_loading": "NOT_RUN",
        "service_change": "NOT_RUN",
    }
