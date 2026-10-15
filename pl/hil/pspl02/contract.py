"""PSPL-02/SWD-00 immutable baseline and offline preflight; no hardware I/O."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path

from pl.hil.swd04.contract import SafetyError, sha256_file, _require
from pl.hil.swd04.staging import bit_payload

SOURCE = "cbe2fb9d012d8ea3df3098ac9ceae0f3d2e468f9"
HASHES = {
    "bit": "df04dae96af5d3918600142efab5ae646fd8ba1e03f51ca2ecf95333edc27880",
    "hwh": "8e0abb1a1c7196e2ee51c5144a038a898a7af7a08887e55f33047ad925f174d5",
    "manifest": "2f7df31dc7760869b03d104f10609b7ed9a1150e89700af4cff2433311390ba8",
    "bin": "3d473eee307cf6dc36c66ffc9a80055a44141fa5b37c27acd0a850d0ab8f72e4",
    "base.bin": "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c",
    "base.hwh": "222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a",
}
SERVICES = ("jupyter.service", "plasma-bootstrap.service", "plasma-server.service",
            "plasma-web.service", "plasma-runtime-activation.service")
BASES = {"identity_0": 0x40000000, "control_0": 0x40001000, "swd_0": 0x40002000}
STAGES = ("IDENTITY", "PSPL02", "SWD00", "ERROR", "RESET")
PREREQUISITES = (
    "gate1_scope_approved", "uart_login_verified_now", "independent_power_recovery_ready",
    "operator_present", "no_external_dut_swd_or_pmod", "authorized_root_available",
    "metadata_backup_verified", "recovery_bytes_preserved", "driver_reconciliation_reviewed",
    "no_shared_service_changes_required", "no_asynchronous_pl_reconfiguration",
)


def json_object(path: Path) -> dict:
    value = json.loads(path.read_text())
    _require(type(value) is dict, "Expected JSON object")
    return value


def write_record(path: Path, value: dict) -> None:
    # Exclusive creation: evidence and failed runs must never be overwritten.
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def verify_artifacts(paths: dict[str, Path]) -> dict:
    _require(set(paths) == set(HASHES), "All candidate and original recovery files required")
    for key, digest in HASHES.items():
        _require(sha256_file(paths[key]) == digest, "Artifact mismatch: " + key)
    # Verify the conversion against every payload byte, not just its sync word.
    payload = bit_payload(paths["bit"].read_bytes())
    swapped = b"".join(payload[i:i+4][::-1] for i in range(0, len(payload), 4))
    _require(paths["bin"].read_bytes() == swapped + bytes.fromhex("00000020"),
             "BIN is not the reviewed Bootgen 2026.1 conversion")
    doc = json_object(paths["manifest"])
    _require(doc.get("source_git_sha") == SOURCE, "Wrong baseline source")
    _require(doc.get("design_variant") == "control_waveform_loopback", "Wrong variant")
    _require(doc.get("acceptance") == {"LB-HOST": "PASS", "LB-Z2": "NOT_RUN",
                                     "real_swd_target": "NOT_RUN"}, "Wrong qualification")
    return {"source": SOURCE, "sha256": dict(HASHES),
            "artifact_integrity": "PASS", "hardware_execution": "NOT_RUN"}


def preflight(inventory: dict, attestation: dict) -> None:
    """Operator facts supplement, and never replace, current privileged evidence."""
    _require(type(inventory) is dict and type(attestation) is dict, "Expected evidence objects")
    _require(attestation.get("schema_version") == 1, "Attestation schema missing")
    for field in PREREQUISITES:
        _require(attestation.get(field) is True, "Unverified prerequisite: " + field)
    _require(inventory.get("architecture") == "armv7l", "Not ARMv7")
    _require(inventory.get("pynq_version") == "3.1.1", "Unexpected PYNQ version")
    _require(inventory.get("device_model_confirmed") is True, "Board unverified")
    _require(inventory.get("fpga_manager_state") == "operating", "Manager not operating")
    _require(inventory.get("fclk0_hz") == 100_000_000
             and inventory.get("fclk0_enabled") is True, "FCLK0 unavailable")
    _require(inventory.get("root_audit_complete") is True, "Incomplete privileged audit")
    _require(inventory.get("pl_users") == [] and inventory.get("audit_errors") == [],
             "PL users or unreadable process mappings")
    _require(inventory.get("metadata_backup_matches") is True, "Metadata backup unverified")
    hashes = inventory.get("metadata_sha256")
    _require(type(hashes) is dict and bool(hashes)
             and all(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value)
                     for value in hashes.values()), "Original metadata hashes missing")
    _require(inventory.get("services") == dict.fromkeys(SERVICES, "active"),
             "Service baseline differs; service changes are outside this plan")
    _require(inventory.get("original_drivers_reviewed") is True, "Unreviewed drivers")
    _require(inventory.get("driver_bindings") == {
        "40000000.fabric": "uio_pdrv_genirq", "43c00000.audio-codec-ctrl": "uio_pdrv_genirq",
    }, "Original driver bindings differ")
    # Exactly the original resources; UIO index is not a stable identity.
    expected = {("fabric", "0x40000000", "0x00010000"),
                ("audio-codec-ctrl", "0x43C00000", "0x00010000")}
    rows = inventory.get("uio")
    _require(type(rows) is list and len(rows) == 2
             and all(type(x) is dict for x in rows), "Unexpected UIO topology")
    _require({(x.get("name"), x.get("address"), x.get("size")) for x in rows} == expected,
             "Original UIO topology differs")
    require_fresh(inventory.get("observed_utc"))


def require_fresh(stamp: str) -> None:
    try:
        observed = datetime.fromisoformat(stamp)
        _require(observed.utcoffset() is not None, "Timestamp requires timezone")
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        _require(0 <= age <= 600, "Inventory/session older than ten minutes or future-dated")
    except (ValueError, TypeError) as exc:
        raise SafetyError("Invalid evidence timestamp") from exc
