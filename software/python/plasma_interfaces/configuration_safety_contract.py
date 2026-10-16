"""Phase 2A.2 HOST-ONLY configuration safety contract.

This is a deterministic validation model, NOT a Linux/FPGA safety oracle.
No IO paths, callbacks, device handles, bitstream loader, or hardware tokens
are exposed. Passing synthetic evidence NEVER authorizes physical loading.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class ContractRejected(RuntimeError):
    """A configuration transition lacks complete exact synthetic evidence."""


class EvidenceKind(str, Enum):
    SYNTHETIC = "SYNTHETIC_FIXTURE"


def _hex_digest(value: str, lengths: tuple[int, ...]) -> bool:
    return type(value) is str and len(value) in lengths and all(
        char in "0123456789abcdef" for char in value
    )


@dataclass(frozen=True)
class ConfigurationPin:
    boot_id: str
    source_sha: str
    resource_id: str
    old_image_sha256: str
    candidate_sha256: str
    mapping_generation: int
    owner_epoch: str

    def __post_init__(self) -> None:
        for field in ("boot_id", "source_sha", "resource_id",
                      "old_image_sha256", "candidate_sha256", "owner_epoch"):
            value = getattr(self, field)
            if type(value) is not str or not value or value.strip() != value or len(value) > 256:
                raise ContractRejected("Missing/ambiguous exact pin: " + field)
        # Shape-check content-addressed identities; these synthetic pins do NOT
        # verify any actual source/image bytes or provide hardware attestation.
        if not _hex_digest(self.source_sha, (40, 64)):
            raise ContractRejected("Invalid source commit digest")
        if not _hex_digest(self.old_image_sha256, (64,)):
            raise ContractRejected("Invalid old image SHA-256")
        if not _hex_digest(self.candidate_sha256, (64,)):
            raise ContractRejected("Invalid candidate SHA-256")
        if type(self.mapping_generation) is not int or self.mapping_generation < 1:
            raise ContractRejected("Invalid mapping generation")


@dataclass(frozen=True)
class OwnershipEvidence:
    pin: ConfigurationPin
    admission_sealed: bool
    no_site_leases: bool
    all_processes_enumerated: bool
    no_retained_vmas: bool
    no_kernel_consumers: bool
    no_dma_masters: bool
    no_external_mmio_owners: bool
    kind: EvidenceKind = EvidenceKind.SYNTHETIC


@dataclass(frozen=True)
class IsolationEvidence:
    pin: ConfigurationPin
    safe_io_verified: bool
    axi_transactions_drained: bool
    axi_isolation_verified: bool
    external_recovery_available: bool
    kind: EvidenceKind = EvidenceKind.SYNTHETIC


@dataclass(frozen=True)
class RetirementEvidence:
    pin: ConfigurationPin
    old_mapping_retired: bool
    no_live_handles: bool
    no_outstanding_site_io: bool
    kind: EvidenceKind = EvidenceKind.SYNTHETIC


@dataclass(frozen=True)
class VerificationEvidence:
    pin: ConfigurationPin
    exact_candidate_verified: bool
    resources_verified: bool
    independent_health_verified: bool
    recovery_receipt_verified: bool
    kind: EvidenceKind = EvidenceKind.SYNTHETIC


@dataclass(frozen=True)
class SyntheticTransitionReceipt:
    pin: ConfigurationPin
    next_generation: int
    host_only: bool = True
    grants_hardware_authority: bool = False


def _require(pin: ConfigurationPin, evidence: object, cls: type, fields: tuple[str, ...]) -> None:
    if type(evidence) is not cls or evidence.pin != pin or type(evidence.pin) is not ConfigurationPin:
        raise ContractRejected("Evidence type or exact pin mismatch")
    if type(evidence.kind) is not EvidenceKind or evidence.kind is not EvidenceKind.SYNTHETIC:
        raise ContractRejected("Hardware or unknown evidence is not supported")
    for name in fields:
        if type(getattr(evidence, name)) is not bool or not getattr(evidence, name):
            raise ContractRejected("Incomplete synthetic safety gate: " + name)


OWNERSHIP: Final = ("admission_sealed", "no_site_leases", "all_processes_enumerated",
                    "no_retained_vmas", "no_kernel_consumers", "no_dma_masters",
                    "no_external_mmio_owners")
ISOLATION: Final = ("safe_io_verified", "axi_transactions_drained",
                    "axi_isolation_verified", "external_recovery_available")
RETIREMENT: Final = ("old_mapping_retired", "no_live_handles", "no_outstanding_site_io")
VERIFICATION: Final = ("exact_candidate_verified", "resources_verified",
                       "independent_health_verified", "recovery_receipt_verified")


def validate_synthetic_transition(
    pin: ConfigurationPin,
    ownership: OwnershipEvidence,
    isolation: IsolationEvidence,
    retirement: RetirementEvidence,
    verification: VerificationEvidence,
) -> SyntheticTransitionReceipt:
    """Validate model gates in sequence; NEVER perform or permit FPGA loading.

    A separate hardware qualification must independently prove PS/PL isolation,
    VMA/Kernel/DMA exclusion and recovery on the *real* device. In particular,
    this synthetic receipt cannot be exchanged for a physical capability.
    """
    if type(pin) is not ConfigurationPin:
        raise ContractRejected("Exact configuration pin required")
    _require(pin, ownership, OwnershipEvidence, OWNERSHIP)
    _require(pin, isolation, IsolationEvidence, ISOLATION)
    _require(pin, retirement, RetirementEvidence, RETIREMENT)
    _require(pin, verification, VerificationEvidence, VERIFICATION)
    return SyntheticTransitionReceipt(pin=pin, next_generation=pin.mapping_generation + 1)
