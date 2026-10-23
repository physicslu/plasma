"""Bind immutable generic FPGA image evidence to existing Path 2 held leases.

This module is **pure admission**: no FPGA Manager, root calls, SSH, SWD,
installer or Dispatcher registration. It does not turn an unverified
self-supplied manifest/receipt into independently observed target authority.

The existing held Provider remains F1-B-specific for identity testing;
generic Blue Pill DPIDR testing requires a separately reviewed target-side
test admission and must not be routed into F1-B's three-read callback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pl.hil.path2_generic_image_loader import (
    ImageProfile, LoaderDenied, VerifiedBundle, need,
)
from scripts import plasma_path2_persistent_lease as lease
from scripts import plasma_path2_held_provider as held

PROVENANCE_FIELDS = frozenset((
    "source_sha", "bit_sha256", "hwh_sha256", "bin_sha256",
    "build_qualification_sha256", "bootgen_evidence_sha256",
    "scope", "physical_load",
))


@dataclass(frozen=True)
class HeldBinding:
    """Hash-pinned offline binding only; never a rooted TargetPort."""
    profile: ImageProfile
    target_id: str
    lease_id: str
    boot_id: str
    source_sha: str
    candidate_bin_sha256: str
    recovery_bin_sha256: str
    candidate_bit_sha256: str
    candidate_hwh_sha256: str
    build_qualification_sha256: str
    bootgen_evidence_sha256: str
    test_route: str

    @property
    def hardware_authorized(self) -> bool:
        return False


def validate_held_binding(bundle: VerifiedBundle, *, intent: object,
                          provenance: object, at: int) -> HeldBinding:
    """Validate exactly existing Provider and Lease record inputs.

    This does not instantiate a port, create a ledger file, register a stage
    or make any assertion about FPGA quiescence or boot/image provenance.
    """
    need(type(bundle) is VerifiedBundle and
         type(bundle.profile) is ImageProfile, "HELD_IMAGE_BUNDLE_DENIED")
    need(type(intent) is dict and type(provenance) is dict,
         "HELD_BINDING_FIELDS_DENIED")
    need(set(provenance) == PROVENANCE_FIELDS and
         set(intent) == {
             "lease_id", "target_id", "profile_id", "source_sha",
             "artifact_sha256", "recovery_sha256", "boot_id", "owner_id",
             "restore_intent_sha256", "services_sha256", "uio_sha256",
             "lease_seconds",
         }, "HELD_BINDING_FIELDS_DENIED")
    p = bundle.profile
    need(intent["source_sha"] == p.source_sha and
         provenance["source_sha"] == p.source_sha and
         intent["profile_id"] == p.profile_id and
         intent["artifact_sha256"] == bundle.candidate_bin_sha256 and
         intent["recovery_sha256"] == bundle.recovery_bin_sha256,
         "HELD_INTENT_PROFILE_MISMATCH")
    need(provenance["scope"] == "BYTE_EQUIVALENCE_ONLY" and
         provenance["physical_load"] == "NOT_RUN" and
         provenance["bit_sha256"] == bundle.candidate_bit_sha256 and
         provenance["hwh_sha256"] == bundle.candidate_hwh_sha256 and
         provenance["bin_sha256"] == bundle.candidate_bin_sha256 and
         held.HEX64.fullmatch(provenance.get("build_qualification_sha256", "")) is not None and
         held.HEX64.fullmatch(provenance.get("bootgen_evidence_sha256", "")) is not None,
         "HELD_BUILD_PROVENANCE_MISMATCH")
    # Reuse the canonical bounded TTL/identifier/digest and lease validation.
    # This creates only an in-memory record; it never writes a hardware ledger.
    try:
        lease.create_record(intent, at)
    except (ValueError, TypeError) as exc:
        raise LoaderDenied("HELD_LEASE_SCHEMA_DENIED") from exc

    # F1-B's existing test asserts exactly 0x4D534C50, 0x10000, 1.
    # No generic profile may be falsely labeled as having passed this test.
    test_route = ("F1B_THREE_READS_ONLY"
                  if p.project == "pl/projects/z2-fixed-unified-site1" and
                  p.profile_id == "f1b-site1-v1"
                  else "GENERIC_TEST_BACKEND_NOT_REGISTERED")
    return HeldBinding(
        profile=p, target_id=intent["target_id"],
        lease_id=intent["lease_id"], boot_id=intent["boot_id"],
        source_sha=p.source_sha,
        candidate_bin_sha256=bundle.candidate_bin_sha256,
        recovery_bin_sha256=bundle.recovery_bin_sha256,
        candidate_bit_sha256=bundle.candidate_bit_sha256,
        candidate_hwh_sha256=bundle.candidate_hwh_sha256,
        build_qualification_sha256=provenance["build_qualification_sha256"],
        bootgen_evidence_sha256=provenance["bootgen_evidence_sha256"],
        test_route=test_route,
    )


def require_existing_f1b_identity_test(binding: HeldBinding) -> None:
    """Do not accidentally pass external SWD DPIDR as F1-B identity."""
    need(type(binding) is HeldBinding and
         binding.test_route == "F1B_THREE_READS_ONLY",
         "GENERIC_SWD_TEST_BACKEND_NOT_REGISTERED")


def root_port_not_registered(binding: HeldBinding) -> None:
    """Explicit and permanent fail-close until trusted Root executor review."""
    need(type(binding) is HeldBinding, "HELD_BINDING_NOT_VERIFIED")
    raise LoaderDenied("GENERIC_PROTECTED_ROOT_BACKEND_NOT_REGISTERED")
