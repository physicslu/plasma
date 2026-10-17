"""PLASMA Phase 2A.1: *synthetic-host-only* PPU configuration owner.

This is a cooperative control-model for the regular-file-only UIOBackend
from Phase 2A. It has NO FPGA Manager call, real UIO adapter, driver unbind,
BIT/HWH load, DMA control, or hardware safety attestation. Synthetic evidence
cannot qualify a real PS/PL AXI isolation boundary or unblock M1.

Host "READY" below means the *test fixture* can admit work, not that a real
FPGA image or PPU has been admitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import fcntl
import os
from pathlib import Path
import stat
from threading import RLock
from uuid import uuid4

from .configuration_safety_contract import (
    ConfigurationPin, ContractRejected, IsolationEvidence, OwnershipEvidence,
    RetirementEvidence, VerificationEvidence, SyntheticTransitionReceipt,
    validate_synthetic_stage, validate_synthetic_transition,
)
from .linux_mmio import MMIOClosed, MMIOError
from .uio_backend import UIOBackend, UIOSiteLease


class OwnerError(RuntimeError):
    """A state, source, or ownership safety gate rejected the operation."""


class OwnerClosed(OwnerError):
    """The host owner/lease is retired, forked, or externally faulted."""


class Phase(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    QUIESCE = "QUIESCE"
    OWNERSHIP_AUDIT = "OWNERSHIP_AUDIT"
    SAFE_IO = "SAFE_IO"
    RELEASE = "RELEASE"
    MODEL_LOAD = "MODEL_LOAD"  # never an actual FPGA load
    VERIFY = "VERIFY"
    NEW_MAPPING_GENERATION = "NEW_MAPPING_GENERATION"
    FAULT = "FAULT"
    EXTERNAL_RECOVERY_REQUIRED = "EXTERNAL_RECOVERY_REQUIRED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class HostAudit:
    """Synthetic fixture claims ONLY; never real Kernel/physical evidence."""

    boot_id: str
    resource_id: str
    source_id: str
    proc_scan_complete: bool
    known_users_only: bool
    no_retained_mappings: bool
    dma_stopped: bool
    kernel_consumers_stopped: bool
    kind: str = "SYNTHETIC_FIXTURE"


@dataclass(frozen=True)
class HostSafety:
    """Assumed safety states used to exercise the host state machine only."""

    assumed_external_io_safe: bool
    assumed_axi_isolation: bool
    kind: str = "SYNTHETIC_FIXTURE"


@dataclass(frozen=True)
class HostVerification:
    candidate: str
    boot_id: str
    identity_match: bool
    resources_match: bool
    kernel_healthy: bool
    gateway_healthy: bool
    ssh_healthy: bool
    recovery_artifact_present: bool
    kind: str = "SYNTHETIC_FIXTURE"


@dataclass(frozen=True)
class OwnerStatus:
    phase: Phase
    generation: int
    epoch: str
    admissions_open: bool
    active_sites: tuple[int, ...]
    batch_ic: str | None
    reason: str | None
    host_only: bool = True


class ManagedSite:
    """A generation-scoped Site lease, never a raw UIO ownership capability."""

    def __init__(self, owner: ConfigurationOwner, port: UIOSiteLease,
                 site_id: int, generation: int) -> None:
        self._owner = owner
        self._port = port
        self.site_id = site_id
        self.base = port.base
        self.generation = generation
        self._active = True

    def read32(self, address: int) -> int:
        return self._owner._site_word(self, address, write=False)

    def write32(self, address: int, value: int) -> None:
        self._owner._site_word(self, address, write=True, value=value)

    def close(self) -> None:
        self._owner._release_site(self)

    def __enter__(self) -> ManagedSite:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ConfigurationOwner:
    """One cooperative configuration authority for a single Host fixture.

    A dedicated cross-process flock protects compliant owner instances;
    UIOBackend keeps its *different* existing MMIO flock. Neither excludes
    external privileged writers or Kernel DMA, hence hardware admission is
    categorically absent from this module.
    """

    def __init__(self, *, config_lock: Path, generation: int,
                 boot_id: str, resource_id: str, source_id: str) -> None:
        if not isinstance(config_lock, Path) or not config_lock.is_absolute() \
                or str(config_lock).startswith("/dev/"):
            raise OwnerError("An absolute Host configuration lock path is required")
        if type(generation) is not int or generation < 1:
            raise OwnerError("Generation must be a positive integer")
        for value in (boot_id, resource_id, source_id):
            if type(value) is not str or not value or len(value) > 256:
                raise OwnerError("Exact synthetic boot/resource/source pins required")
        self.config_lock = config_lock
        self.generation = generation
        self.boot_id, self.resource_id, self.source_id = boot_id, resource_id, source_id
        self.epoch = uuid4().hex  # same generation numbers from another owner are NOT interchangeable
        self._mutex = RLock()
        self._pid: int | None = None
        self._fd: int | None = None
        self._phase = Phase.IDLE
        self._backend: UIOBackend | None = None
        self._leases: dict[int, ManagedSite] = {}
        self._batch_ic: str | None = None
        self._candidate: str | None = None
        self._reason: str | None = None
        # Host-only transition; no real image operation or privileged capability.
        self._transition_pin: ConfigurationPin | None = None
        self._ownership: OwnershipEvidence | None = None
        self._isolation: IsolationEvidence | None = None
        self._retirement: RetirementEvidence | None = None
        self._verification: VerificationEvidence | None = None
        self._receipt: SyntheticTransitionReceipt | None = None
        self._host_mapping_retired = False

    def _clear_contract(self) -> None:
        self._transition_pin = None
        self._ownership = None
        self._isolation = None
        self._retirement = None
        self._verification = None
        self._receipt = None
        self._host_mapping_retired = False

    def _contract_stage(self, evidence: object, expected: type) -> None:
        pin = self._transition_pin
        if pin is None or type(evidence) is not expected:
            self._fault("Missing or incorrect Phase 2A.3 synthetic gate evidence")
        if (pin.boot_id, pin.resource_id, pin.source_sha,
                pin.mapping_generation, pin.owner_epoch) != (
                self.boot_id, self.resource_id, self.source_id,
                self.generation, self.epoch):
            self._fault("Phase 2A.3 owner/generation/source pin drift")
        try:
            validate_synthetic_stage(pin, evidence)
        except ContractRejected as exc:
            self._fault("Phase 2A.3 synthetic gate rejected: " + str(exc))

    def _active(self) -> None:
        if self._phase is Phase.CLOSED or self._fd is None:
            raise OwnerClosed("Configuration owner not opened or permanently closed")
        if self._pid != os.getpid():
            raise OwnerClosed("Fork-inherited configuration authority is invalid")

    def _require(self, phase: Phase) -> None:
        self._active()
        if self._phase is not phase:
            raise OwnerError(f"Operation requires {phase.value}, currently {self._phase.value}")

    def _fault(self, reason: str, *, external: bool = False) -> None:
        self._reason = reason
        self._clear_contract()
        self._phase = (Phase.EXTERNAL_RECOVERY_REQUIRED if external else Phase.FAULT)
        # Do not call real FPGA/restore code: none is linked.
        for lease in self._leases.values():
            lease._active = False
        # Never promote a faulted host model to READY.
        raise OwnerError(reason)

    def open(self) -> None:
        with self._mutex:
            if self._fd is not None or self._phase is Phase.CLOSED:
                raise OwnerClosed("Owner is open or retired")
            try:
                fd = os.open(self.config_lock,
                             os.O_RDWR | os.O_CREAT | os.O_CLOEXEC |
                             getattr(os, "O_NOFOLLOW", 0), 0o600)
            except OSError as exc:
                raise OwnerError("Host configuration lock is unavailable") from exc
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OwnerError("Configuration lock must be an ordinary file")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException as exc:
                os.close(fd)
                if isinstance(exc, OwnerError):
                    raise
                raise OwnerError("Another cooperating configuration owner exists") from exc
            self._fd, self._pid = fd, os.getpid()

    def __enter__(self) -> ConfigurationOwner:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> OwnerStatus:
        with self._mutex:
            return OwnerStatus(
                phase=self._phase, generation=self.generation, epoch=self.epoch,
                admissions_open=self._phase is Phase.READY and
                                self._fd is not None and self._pid == os.getpid(),
                active_sites=tuple(sorted(self._leases)),
                batch_ic=self._batch_ic, reason=self._reason,
            )

    def attach_host_backend(self, backend: UIOBackend) -> None:
        """Own and open an exact **Phase 2A regular-file-only** backend."""
        with self._mutex:
            self._require(Phase.IDLE)
            if type(backend) is not UIOBackend:
                raise OwnerError("Only the Phase 2A Host-only UIOBackend is supported")
            if self._backend is not None or self._leases:
                raise OwnerError("Host backend already attached")
            if backend.generation != self.generation:
                raise OwnerError("Stale backend mapping generation")
            if backend.owner_lock == self.config_lock:
                raise OwnerError("Configuration lock and MMIO lock must be separate")
            try:
                backend.open()
            except Exception as exc:
                self._fault(f"Cannot acquire Host backend: {type(exc).__name__}")
            self._backend = backend

    def admit_existing_host_fixture(self) -> None:
        with self._mutex:
            self._require(Phase.IDLE)
            if self._backend is None:
                raise OwnerError("Host-only backend must be attached before admission")
            self._phase = Phase.READY

    def claim_site(self, site_id: int, base: int, *, exact_ic: str) -> ManagedSite:
        with self._mutex:
            self._require(Phase.READY)
            if type(exact_ic) is not str or not exact_ic.strip() or len(exact_ic) > 128:
                raise OwnerError("A nonempty exact IC/profile identity is required")
            if self._batch_ic is not None and self._batch_ic != exact_ic:
                raise OwnerError("Concurrent Sites must share an exact IC/profile")
            if self._backend is None:
                raise OwnerError("No admitted Host backend")
            if site_id in self._leases:
                raise OwnerError("Site already admitted")
            try:
                port = self._backend.claim_site(site_id, base)
            except (MMIOClosed, MMIOError) as exc:
                raise OwnerError("Site admission rejected by Host backend") from exc
            lease = ManagedSite(self, port, site_id, self.generation)
            self._leases[site_id] = lease
            self._batch_ic = exact_ic
            return lease

    def _site_word(self, lease: ManagedSite, address: int, *,
                   write: bool, value: int = 0) -> int | None:
        with self._mutex:
            self._active()
            if self._phase not in (Phase.READY, Phase.QUIESCE):
                raise OwnerClosed("Site access blocked during configuration transition")
            if not lease._active or self._leases.get(lease.site_id) is not lease \
                    or lease.generation != self.generation:
                raise OwnerClosed("Old or revoked Site lease")
            try:
                return (lease._port.write32(address, value) if write else
                        lease._port.read32(address))
            except (MMIOError, MMIOClosed, OSError, ValueError) as exc:
                self._fault(f"Uncertain Host MMIO access: {type(exc).__name__}")

    def _release_site(self, lease: ManagedSite) -> None:
        with self._mutex:
            if not lease._active:
                return
            lease._active = False
            if self._leases.get(lease.site_id) is lease:
                del self._leases[lease.site_id]
            try:
                lease._port.close()
            except Exception as exc:
                self._reason = "Host Site close failed"
                self._clear_contract()
                self._phase = Phase.FAULT
                raise OwnerError("Host Site close failed") from exc
            if not self._leases:
                self._batch_ic = None

    def begin_quiesce(self, *, pin: ConfigurationPin | None = None) -> None:
        with self._mutex:
            self._require(Phase.READY)
            # Close admission before any new evidence or Site-idle snapshot.
            self._phase = Phase.QUIESCE
            self._clear_contract()
            # No pin is supported only for early QUIESCE negative/fault tests.
            # It can never advance through the full transition.
            if pin is None:
                return
            if type(pin) is not ConfigurationPin or (
                    pin.boot_id, pin.resource_id, pin.source_sha,
                    pin.mapping_generation, pin.owner_epoch) != (
                    self.boot_id, self.resource_id, self.source_id,
                    self.generation, self.epoch):
                self._fault("Invalid exact Host-only configuration transition pin")
            self._transition_pin = pin

    def confirm_sites_idle(self) -> None:
        with self._mutex:
            self._require(Phase.QUIESCE)
            if self._leases:
                raise OwnerError("Active Site jobs block ownership audit")
            self._phase = Phase.OWNERSHIP_AUDIT

    def submit_synthetic_audit(self, audit: HostAudit, *,
                               ownership: OwnershipEvidence | None = None) -> None:
        with self._mutex:
            self._require(Phase.OWNERSHIP_AUDIT)
            if type(audit) is not HostAudit or audit.kind != "SYNTHETIC_FIXTURE" \
                    or (audit.boot_id, audit.resource_id, audit.source_id) != (
                        self.boot_id, self.resource_id, self.source_id) or any(
                        type(v) is not bool or not v for v in (
                            audit.proc_scan_complete, audit.known_users_only,
                            audit.no_retained_mappings, audit.dma_stopped,
                            audit.kernel_consumers_stopped)):
                self._fault("Synthetic ownership/source/DT/DMA check unknown or failed")
            if self._leases:
                self._fault("Managed Sites still active during ownership audit")
            self._contract_stage(ownership, OwnershipEvidence)
            self._ownership = ownership
            self._phase = Phase.SAFE_IO

    def submit_synthetic_safe_io(self, evidence: HostSafety, *,
                                 isolation: IsolationEvidence | None = None) -> None:
        with self._mutex:
            self._require(Phase.SAFE_IO)
            if type(evidence) is not HostSafety or evidence.kind != "SYNTHETIC_FIXTURE" \
                    or type(evidence.assumed_external_io_safe) is not bool \
                    or type(evidence.assumed_axi_isolation) is not bool \
                    or not evidence.assumed_external_io_safe \
                    or not evidence.assumed_axi_isolation:
                self._fault("Synthetic safe-IO/isolation check unknown or failed")
            self._contract_stage(isolation, IsolationEvidence)
            if self._ownership is None:
                self._fault("Synthetic ownership gate was bypassed")
            self._isolation = isolation
            self._phase = Phase.RELEASE

    def release_host_mapping(self) -> None:
        with self._mutex:
            self._require(Phase.RELEASE)
            if self._leases or self._backend is None or self._isolation is None:
                self._fault("Active Site, missing backend or missing isolation at release")
            retiring_backend = self._backend
            try:
                self._backend.quiesce_for_reload()  # closes host regular-file mapping only
            except Exception as exc:
                self._fault(f"Host-only MMIO release failed: {type(exc).__name__}")
            if (not retiring_backend._retired or retiring_backend._fd is not None
                    or retiring_backend._map is not None):
                self._fault("Host mapping retirement incomplete")
            self._backend = None
            self._host_mapping_retired = True
            self._phase = Phase.MODEL_LOAD

    def confirm_synthetic_retirement(self, evidence: RetirementEvidence) -> None:
        """Confirm host regular-file mapping closed; synthetic VMA/DMA claims only."""
        with self._mutex:
            self._require(Phase.MODEL_LOAD)
            if not self._host_mapping_retired or self._backend is not None or self._leases:
                self._fault("Host backend/leases not retired")
            self._contract_stage(evidence, RetirementEvidence)
            self._retirement = evidence

    def simulate_image_switch(self, candidate_label: str, *,
                              candidate_sha256: str | None = None) -> None:
        """Record a candidate label in RAM; never change an FPGA image or sysfs state."""
        with self._mutex:
            self._require(Phase.MODEL_LOAD)
            if type(candidate_label) is not str or not candidate_label.strip() \
                    or len(candidate_label) > 128:
                self._fault("Invalid synthetic candidate identity")
            if self._retirement is None or self._transition_pin is None:
                self._fault("Synthetic mapping retirement evidence missing")
            # Caller assertion binds the label to the pinned expected digest;
            # no image bytes are read or authenticated by this host model.
            if type(candidate_sha256) is not str or (
                    candidate_sha256 != self._transition_pin.candidate_sha256):
                self._fault("Synthetic candidate digest does not match transition pin")
            self._candidate = candidate_label
            self._phase = Phase.VERIFY

    def submit_synthetic_verification(self, evidence: HostVerification, *,
                                      contract: VerificationEvidence | None = None) -> None:
        with self._mutex:
            self._require(Phase.VERIFY)
            if type(evidence) is not HostVerification \
                    or evidence.kind != "SYNTHETIC_FIXTURE" \
                    or evidence.candidate != self._candidate \
                    or evidence.boot_id != self.boot_id \
                    or any(type(v) is not bool or not v for v in (
                        evidence.identity_match, evidence.resources_match,
                        evidence.kernel_healthy, evidence.gateway_healthy,
                        evidence.ssh_healthy, evidence.recovery_artifact_present)):
                self._fault("Synthetic image identity/health/recovery check failed")
            self._contract_stage(contract, VerificationEvidence)
            if (self._ownership is None or self._isolation is None
                    or self._retirement is None or self._transition_pin is None):
                self._fault("Incomplete phase-scoped safety evidence")
            try:
                receipt = validate_synthetic_transition(
                    self._transition_pin, self._ownership, self._isolation,
                    self._retirement, contract)
            except ContractRejected as exc:
                self._fault("Synthetic safety contract validation rejected: " + str(exc))
            if receipt.grants_hardware_authority or not receipt.host_only:
                self._fault("Synthetic contract must not grant hardware authority")
            self._verification = contract
            self._receipt = receipt
            self._phase = Phase.NEW_MAPPING_GENERATION

    def publish_host_generation(self) -> int:
        with self._mutex:
            self._require(Phase.NEW_MAPPING_GENERATION)
            if self._backend is not None or self._leases or not self._host_mapping_retired:
                self._fault("Host mappings survived generation boundary")
            if (self._transition_pin is None or self._receipt is None
                    or self._receipt.pin != self._transition_pin
                    or self._receipt.next_generation != self.generation + 1
                    or self._transition_pin.mapping_generation != self.generation
                    or self._transition_pin.owner_epoch != self.epoch
                    or self._transition_pin.boot_id != self.boot_id
                    or self._transition_pin.resource_id != self.resource_id
                    or self._transition_pin.source_sha != self.source_id):
                self._fault("No exact host-only safety receipt for this generation")
            self.generation = self._receipt.next_generation
            self._candidate = None
            self._clear_contract()
            self._phase = Phase.IDLE  # NOT READY until another Host backend is attached
            return self.generation

    def external_recovery_required(self, reason: str) -> None:
        with self._mutex:
            self._active()
            self._fault("External recovery required: " + str(reason), external=True)

    def close(self) -> None:
        """Permanently retire this instance; no implicit recovery or reuse."""
        with self._mutex:
            if self._phase is Phase.CLOSED:
                return
            self._phase = Phase.CLOSED
            self._clear_contract()
            leases = tuple(self._leases.values())
            self._leases.clear()
            self._batch_ic = None
            failures = []
            try:
                for lease in leases:
                    lease._active = False
                    try:
                        lease._port.close()
                    except Exception as exc:
                        failures.append(exc)
                if self._backend is not None:
                    try:
                        self._backend.close()
                    except Exception as exc:
                        failures.append(exc)
                    finally:
                        self._backend = None
            finally:
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None
            if failures:
                raise OwnerError("Host owner retirement incomplete; do not reuse") from failures[0]
