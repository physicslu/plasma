"""Reusable root-side *read-only* Path 2 FPGA profile preflight.

Uses the already-reviewed generic one_shot native/owner/clock machinery.
This code never installs a dispatcher entry, opens a target or writes FPGA
Manager. Passing it is NOT independent AXI isolation, current loaded-image
attestation or electrical admission; a separate protected target backend
is still required for Download/Test/Restore.
"""
from __future__ import annotations

import json
from pathlib import Path

from pl.hil.path2_generic_image_loader import (
    ImageProfile, LoaderDenied, VerifiedBundle, need,
)
from pl.hil.swd04 import development, one_shot

# No Work Order may choose these constants as a dynamic programming route.
# Only separately reviewed, root-owned project-specific source may supply
# its exact HWH-qualified aperture topology to this helper.
GP0_FIRST = 0x40000000
GP0_LIMIT = 0x80000000


def hardware_profile(bundle: VerifiedBundle, *,
                     trusted_apertures: tuple[tuple[str, int, int], ...]
                     ) -> development.HardwareProfile:
    """Construct an existing native HardwareProfile; never grant HW access."""
    need(type(bundle) is VerifiedBundle and
         type(bundle.profile) is ImageProfile,
         "ROOT_PROFILE_INVALID")
    need(type(trusted_apertures) is tuple and
         0 < len(trusted_apertures) <= 8,
         "ROOT_APERTURE_COUNT_DENIED")
    ranges: list[tuple[int, int]] = []
    for item in trusted_apertures:
        need(type(item) is tuple and len(item) == 3,
             "ROOT_APERTURE_SCHEMA_DENIED")
        name, base, length = item
        need(type(name) is str and name.isidentifier() and
             type(base) is int and type(length) is int and
             GP0_FIRST <= base < GP0_LIMIT and
             length >= 4096 and (length & (length - 1)) == 0 and
             base % length == 0 and base + length <= GP0_LIMIT,
             "ROOT_APERTURE_LOCATION_DENIED")
        ranges.append((base, base + length))
    ordered = sorted(ranges)
    need(all(left[1] <= right[0] for left, right
             in zip(ordered, ordered[1:])),
         "ROOT_APERTURE_OVERLAP_DENIED")
    p = bundle.profile
    return development.HardwareProfile(
        source=p.source_sha,
        bit_sha256=bundle.candidate_bit_sha256,
        hwh_sha256=bundle.candidate_hwh_sha256,
        bin_sha256=bundle.candidate_bin_sha256,
        recovery_sha256=bundle.recovery_bin_sha256,
        apertures=trusted_apertures,
        abis=(),
        recovery_hwh_sha256=bundle.recovery_hwh_sha256,
        identity_words=(),
    )


def collect_root_preflight(
    bundle: VerifiedBundle, inputs: one_shot.Inputs, *,
    approved_source_sha: str,
    trusted_apertures: tuple[tuple[str, int, int], ...]
) -> dict:
    """Root-target read-only snapshot with strict reviewed source and files.

    This is intended for an already-installed/root-pinned executor. The
    caller must authenticate source and hardware topology separately. NO
    input from this function elevates AXI/FPGA Manager authority.
    """
    need(type(bundle) is VerifiedBundle and
         type(inputs) is one_shot.Inputs and
         type(bundle.profile) is ImageProfile and
         bundle.profile.source_sha == approved_source_sha,
         "ROOT_APPROVED_SOURCE_DENIED")
    p = bundle.profile
    need(inputs.candidate_bin.name == p.candidate_bin and
         inputs.recovery_bin.name == p.recovery_bin and
         bundle.candidate_bit_sha256 == p.candidate_bit_sha256 and
         bundle.candidate_hwh_sha256 == p.candidate_hwh_sha256 and
         bundle.candidate_bin_sha256 == p.candidate_bin_sha256 and
         bundle.recovery_hwh_sha256 == p.recovery_hwh_sha256 and
         bundle.recovery_bin_sha256 == p.recovery_bin_sha256,
         "ROOT_PROFILE_BUNDLE_MISMATCH")
    native = hardware_profile(bundle, trusted_apertures=trusted_apertures)
    # This existing function enforces root/ARMv7/CPython, protected paths,
    # candidate and recovery bytes, and pinned file basenames.
    one_shot.verify_inputs(inputs, profile=native)
    one_shot.protected(inputs.manifest)
    try:
        manifest = json.loads(inputs.manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LoaderDenied("ROOT_MANIFEST_UNREADABLE") from exc
    installed = ImageProfile.from_protected_manifest(
        manifest, approved_source_sha=approved_source_sha)
    need(installed == p, "ROOT_INSTALLED_MANIFEST_MISMATCH")

    boot_path = Path("/proc/sys/kernel/random/boot_id")
    boot_before = boot_path.read_text().strip()
    need(bool(boot_before), "ROOT_Z2_BOOT_ID_MISSING")
    compatible = Path("/proc/device-tree/compatible").read_bytes().split(b"\0")
    need(b"xlnx,zynq-7000" in compatible,
         "ROOT_ZYNQ_FAMILY_DENIED")
    one_shot.clock_and_owner(native)  # FPGA operating, FCLK, exact MMIO owners
    services = one_shot.service_snapshot()  # read only, no restarts
    current_load = one_shot.manager_last_load()  # same-boot kernel evidence
    need((": writing " + p.recovery_bin + " to ") in current_load,
         "ROOT_CURRENT_ORIGINAL_IMAGE_UNPROVEN")
    boot_after = boot_path.read_text().strip()
    need(boot_before == boot_after, "ROOT_BOOT_CHANGED")

    # Kernel provenance alone is NOT an independent image attestation.
    return {
        "status": "NO_GO",
        "profile_id": p.profile_id,
        "project": p.project,
        "source_sha": p.source_sha,
        "boot_id": boot_before,
        "candidate_bin_sha256": p.candidate_bin_sha256,
        "recovery_bin_sha256": p.recovery_bin_sha256,
        "apertures": [{"name": name, "base": base, "bytes": length}
                      for name, base, length in trusted_apertures],
        "services": services,
        "fpga_manager": "operating",
        "current_image": "MANAGER_LOG_ONLY_NOT_ATTESTED",
        "axi_isolation": "UNPROVEN",
        "external_swd_electrical": "NOT_ATTESTED",
        "safe_recovery": "NOT_INDEPENDENTLY_VERIFIED",
        "hardware_write_authorized": False,
        "fpga_load": "NOT_RUN",
        "physical_swd": "NOT_RUN",
        "flash_program": "NOT_RUN",
    }
