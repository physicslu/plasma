"""Generic FPGA image-configuration policy, source-only and hardware-inert.

This module models *maintenance/provisioning* image selection and restoration.
A normal IC Probe/Erase/Program/Read/Verify Job must NEVER call it or reload
FPGA on target/profile changes. A future authorized Root Executor supplies
actual root ownership, AXI isolation, verified image/boot and restoration;
this library NEVER supplies those permissions, observability or I/O.

No FPGA Manager, MMIO, SSH, sockets, flash, USB or root execution hooks.
"""
from __future__ import annotations

import hashlib
import re
import sys

STAGES = frozenset(("download", "test", "restore"))
SOURCE = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
PROJECT = re.compile(r"pl/projects/[a-z0-9][a-z0-9-]{2,69}\Z")
STAGE_RESULTS = {
    "PLAN_DOWNLOAD": "SIMULATED_LOADED_AND_HELD",
    "PLAN_READ_ONLY_ABI": "SIMULATED_IDENTITY_PASS",
    "PLAN_RESTORE": "SIMULATED_RESTORED_VERIFIED",
    "PLAN_RESTORED_NOOP": "SIMULATED_ALREADY_RESTORED",
}


class StageDenied(ValueError):
    """Reject a malformed or unqualified simulated FPGA configuration."""


def need(valid: bool, reason: str) -> None:
    if not valid:
        raise StageDenied(reason)


def hex_pin(value: object, length: int) -> bool:
    regex = SOURCE if length == 40 else DIGEST if length == 64 else None
    return (regex is not None and type(value) is str
            and regex.fullmatch(value) is not None
            and any(digit != "0" for digit in value))


def validate_source_lock(*, project: str, expected_project: str,
                         reviewed_sha: str, installed_sha: str, build_sha: str,
                         bit_sha: str, hwh_sha: str, bin_sha: str,
                         original_sha: str) -> None:
    """The exact project/image source contract; *not* root provenance."""
    need(type(expected_project) is str and PROJECT.fullmatch(expected_project)
         is not None and type(project) is str and project == expected_project,
         "PROJECT_MISMATCH")
    need(all(hex_pin(x, 40) for x in
             (reviewed_sha, installed_sha, build_sha)), "SOURCE_SHA_INVALID")
    need(reviewed_sha == installed_sha == build_sha,
         "IMAGE_SOURCE_REBUILD_REQUIRED")
    need(all(hex_pin(x, 64) for x in
             (bit_sha, hwh_sha, bin_sha, original_sha)), "IMAGE_SHA_INVALID")
    need(original_sha != bin_sha, "CANDIDATE_IS_RECOVERY")


def validate_bundle(*, bit: bytes, hwh: bytes, binary: bytes,
                    original: bytes, bit_sha: str, hwh_sha: str,
                    bin_sha: str, original_sha: str) -> None:
    """Host fixture-byte digest validation; no implicit image admission."""
    sources = ((bit, bit_sha), (hwh, hwh_sha),
               (binary, bin_sha), (original, original_sha))
    need(all(type(data) is bytes and bool(data) for data, _ in sources),
         "BUNDLE_BYTES_MISSING")
    need(all(hex_pin(sha, 64) for _, sha in sources),
         "IMAGE_SHA_INVALID")
    for data, expected_sha in sources:
        need(hashlib.sha256(data).hexdigest() == expected_sha,
             "IMAGE_BUNDLE_HASH_MISMATCH")


def choose_stage(stage: str, phase: str) -> str:
    """Only independent image-maintenance stages, never an IC Job."""
    need(type(stage) is str and stage in STAGES, "STAGE_NOT_ALLOWLISTED")
    need(type(phase) is str and phase in ("BASE", "HELD"),
         "STALE_BOOT_OR_IN_FLIGHT_MANUAL_RECOVERY")
    if stage == "download":
        need(phase == "BASE", "DUPLICATE_DOWNLOAD_DENIED")
        return "PLAN_DOWNLOAD"
    if stage == "test":
        need(phase == "HELD", "TEST_REQUIRES_HELD_IMAGE")
        return "PLAN_READ_ONLY_ABI"
    return "PLAN_RESTORE" if phase == "HELD" else "PLAN_RESTORED_NOOP"


def validate_stage_plan(*, stage: str, phase: str, action: str,
                        expected_image_sha: str, candidate_sha: str,
                        original_sha: str) -> None:
    """Reject forged cross-stage/state/image plan without physical access."""
    need(type(action) is str and action in STAGE_RESULTS,
         "STAGE_PLAN_INVALID")
    need(hex_pin(expected_image_sha, 64) and hex_pin(candidate_sha, 64)
         and hex_pin(original_sha, 64), "STAGE_PLAN_TAMPERED")
    try:
        selected = choose_stage(stage, phase)
    except StageDenied:
        raise StageDenied("STAGE_PLAN_TAMPERED") from None
    wanted = candidate_sha if selected in ("PLAN_DOWNLOAD", "PLAN_READ_ONLY_ABI") else original_sha
    need(selected == action and expected_image_sha == wanted,
         "STAGE_PLAN_TAMPERED")


def main() -> int:
    print("GENERIC_FPGA_CONFIGURATION_LIVE_BACKEND_NOT_IMPLEMENTED",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
