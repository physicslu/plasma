"""Generic FPGA configuration Stage policy + data-only Image Descriptor.

One PPU-level, hardware-INERT maintenance/provisioning Stage; independent
download / read-only identity test / restore. Ordinary IC Programming Jobs
(Probe/Erase/Program/Read/Verify) NEVER perform FPGA image reloads.

Image Descriptor supplies board, AXI, clock, pin map, read-only identity
mask/value and historic offline artifact hashes. The policy may reject an
unqualified descriptor, but can NEVER grant root authority or prove live
AXI isolation, physical I/O or FPGA restoration. No Z2, FPGA Manager, MMIO,
network, USB, SWD or target access exists in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys

STAGES = frozenset(("download", "test", "restore"))
SOURCE = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
PROJECT = re.compile(r"pl/projects/[a-z0-9][a-z0-9-]{2,69}\Z")
PIN = re.compile(r"[A-Z][A-Z0-9]{0,9}\Z")
STAGE_RESULTS = {
    "PLAN_DOWNLOAD": "SIMULATED_LOADED_AND_HELD",
    "PLAN_READ_ONLY_ABI": "SIMULATED_IDENTITY_PASS",
    "PLAN_RESTORE": "SIMULATED_RESTORED_VERIFIED",
    "PLAN_RESTORED_NOOP": "SIMULATED_ALREADY_RESTORED",
}


class StageDenied(ValueError):
    """Fail closed without hardware operation or trusted Root Entry receipt."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise StageDenied(reason)


def hex_pin(value: object, length: int) -> bool:
    regex = SOURCE if length == 40 else DIGEST if length == 64 else None
    return (regex is not None and type(value) is str
            and regex.fullmatch(value) is not None
            and any(c != "0" for c in value))


def _u32(value: object) -> bool:
    return type(value) is int and 0 <= value <= 0xFFFFFFFF


def _pins(data: object) -> tuple[tuple[str, str], ...]:
    need(type(data) is dict and 1 <= len(data) <= 32,
         "IMAGE_DESCRIPTOR_PINS_INVALID")
    need(all(type(k) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,31}", k)
             and type(v) is str and PIN.fullmatch(v) is not None
             for k, v in data.items()) and len(set(data.values())) == len(data),
         "IMAGE_DESCRIPTOR_PINS_INVALID")
    return tuple(sorted(data.items()))


@dataclass(frozen=True)
class ImageDescriptor:
    """Trusted *candidate data format*, never a hardware admission credential."""
    schema: str
    project: str
    purpose: str
    site_count: int
    board: str
    axi_base: int
    axi_bytes: int
    fclk_hz: int
    pin_map: tuple[tuple[str, str], ...]
    read_only_identity: tuple[tuple[int, int, int], ...]
    image_build_source_sha: str
    bit_sha256: str
    hwh_sha256: str
    bin_sha256: str
    recovery_sha256: str | None
    runtime_admitted: bool
    external_io_timing: str
    evidence_run_id: int
    evidence_artifact_id: int

    @classmethod
    def from_mapping(cls, raw: object) -> "ImageDescriptor":
        need(type(raw) is dict and set(raw) == {
             "schema", "project", "purpose", "site_count", "board",
             "axi_base", "axi_bytes", "fclk_hz", "pin_map",
             "read_only_identity", "offline_image",
             "recovery_sha256", "runtime_admitted", "external_io_timing"},
             "IMAGE_DESCRIPTOR_SCHEMA_INVALID")
        need(type(raw["offline_image"]) is dict and
             set(raw["offline_image"]) == {
                 "build_source_sha", "bit_sha256", "hwh_sha256",
                 "bin_sha256", "github_run_id", "github_artifact_id",
                 "evidence"},
             "IMAGE_DESCRIPTOR_SCHEMA_INVALID")
        r = raw["read_only_identity"]
        need(type(r) is list and 1 <= len(r) <= 16 and
             all(type(x) is dict and set(x) == {"offset", "value", "mask"}
                 and all(_u32(x[k]) for k in ("offset", "value", "mask"))
                 and x["mask"] != 0 and x["value"] & ~x["mask"] == 0
                 for x in r), "IMAGE_DESCRIPTOR_IDENTITY_INVALID")
        im = raw["offline_image"]
        need(type(im["github_run_id"]) is int and im["github_run_id"] > 0 and
             type(im["github_artifact_id"]) is int and im["github_artifact_id"] > 0
             and type(im["evidence"]) is str and
             re.fullmatch(r"[A-Z0-9_]{8,80}", im["evidence"]) is not None,
             "IMAGE_DESCRIPTOR_PROVENANCE_INVALID")
        obj = cls(
            schema=raw["schema"], project=raw["project"],
            purpose=raw["purpose"], site_count=raw["site_count"],
            board=raw["board"], axi_base=raw["axi_base"],
            axi_bytes=raw["axi_bytes"], fclk_hz=raw["fclk_hz"],
            pin_map=_pins(raw["pin_map"]),
            read_only_identity=tuple((x["offset"], x["value"], x["mask"]) for x in r),
            image_build_source_sha=im["build_source_sha"],
            bit_sha256=im["bit_sha256"], hwh_sha256=im["hwh_sha256"],
            bin_sha256=im["bin_sha256"],
            recovery_sha256=raw["recovery_sha256"],
            runtime_admitted=raw["runtime_admitted"],
            external_io_timing=raw["external_io_timing"],
            evidence_run_id=im["github_run_id"],
            evidence_artifact_id=im["github_artifact_id"],
        )
        obj.validate()
        return obj

    def validate(self) -> None:
        need(self.schema == "plasma.fpga.image_descriptor.v1" and
             type(self.project) is str and PROJECT.fullmatch(self.project) is not None
             and type(self.purpose) is str and 3 <= len(self.purpose) <= 100
             and type(self.board) is str and 5 <= len(self.board) <= 100
             and type(self.site_count) is int and 1 <= self.site_count <= 8,
             "IMAGE_DESCRIPTOR_IDENTITY_INVALID")
        need(_u32(self.axi_base) and self.axi_base % 4096 == 0 and
             type(self.axi_bytes) is int and 4096 <= self.axi_bytes <= 65536
             and self.axi_bytes % 4096 == 0 and
             self.axi_base + self.axi_bytes <= 0x100000000 and
             type(self.fclk_hz) is int and 1_000_000 <= self.fclk_hz <= 300_000_000,
             "IMAGE_DESCRIPTOR_AXI_INVALID")
        need(type(self.pin_map) is tuple and 1 <= len(self.pin_map) <= 32
             and _pins(dict(self.pin_map)) == self.pin_map and
             len(dict(self.pin_map)) == len(self.pin_map),
             "IMAGE_DESCRIPTOR_PINS_INVALID")
        ids = self.read_only_identity
        need(type(ids) is tuple and 1 <= len(ids) <= 16 and
             all(type(x) is tuple and len(x) == 3 and
                 all(_u32(v) for v in x) and x[0] % 4 == 0
                 and x[0] + 4 <= self.axi_bytes and x[2] != 0 and
                 x[1] & ~x[2] == 0 for x in ids) and
             len({x[0] for x in ids}) == len(ids),
             "IMAGE_DESCRIPTOR_IDENTITY_INVALID")
        need(hex_pin(self.image_build_source_sha, 40) and
             all(hex_pin(s, 64) for s in
                 (self.bit_sha256, self.hwh_sha256, self.bin_sha256)) and
             (self.recovery_sha256 is None or
              hex_pin(self.recovery_sha256, 64)) and
             self.runtime_admitted is False and
             type(self.evidence_run_id) is int and self.evidence_run_id > 0 and
             type(self.evidence_artifact_id) is int and self.evidence_artifact_id > 0,
             "IMAGE_DESCRIPTOR_PROVENANCE_INVALID")
        # An unverified external-I/O timing declaration is not a runtime
        # admission credential. It must remain explicitly unqualified
        # until independent measured evidence and a reviewed authority
        # are available; merely writing "QUALIFIED" cannot change status.
        need(self.external_io_timing == "NOT_QUALIFIED",
             "IMAGE_DESCRIPTOR_EXTERNAL_IO_UNQUALIFIED")


def load_descriptor(path: Path) -> ImageDescriptor:
    """Read checked-in metadata only; it does not grant root/image authority."""
    need(isinstance(path, Path) and path.is_file() and not path.is_symlink() and
         path.stat().st_size <= 16384, "IMAGE_DESCRIPTOR_FILE_INVALID")
    try:
        return ImageDescriptor.from_mapping(json.loads(path.read_text()))
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, StageDenied):
            raise
        raise StageDenied("IMAGE_DESCRIPTOR_FILE_INVALID") from exc



@dataclass(frozen=True)
class CandidateHardware:
    """Expected descriptor or independently measured host input, not attestation.

    No build provenance, uploader role, source manifest or executor SHA belongs
    to this image compatibility contract. A live owner must supply measurements.
    """
    board: str
    fpga_part: str
    abi: str
    axi_base: int
    axi_bytes: int
    fclk_hz: int
    site_count: int
    pin_map: tuple[tuple[str, str], ...]

    def validate(self) -> None:
        need(all(type(v) is str and 1 <= len(v) <= 100
                 for v in (self.board, self.fpga_part, self.abi)),
             "CANDIDATE_BOARD_PART_ABI_INVALID")
        need(_u32(self.axi_base) and self.axi_base % 4096 == 0 and
             type(self.axi_bytes) is int and 4096 <= self.axi_bytes <= 65536
             and self.axi_bytes % 4096 == 0 and
             self.axi_base + self.axi_bytes <= 0x100000000 and
             type(self.fclk_hz) is int and 1_000_000 <= self.fclk_hz <= 300_000_000
             and type(self.site_count) is int and 1 <= self.site_count <= 8,
             "CANDIDATE_HARDWARE_INVALID")
        need(type(self.pin_map) is tuple and 1 <= len(self.pin_map) <= 32
             and all(type(pair) is tuple and len(pair) == 2
                     and all(type(v) is str for v in pair)
                     for pair in self.pin_map) and
             _pins(dict(self.pin_map)) == self.pin_map and
             len(dict(self.pin_map)) == len(self.pin_map),
             "IMAGE_DESCRIPTOR_PINS_INVALID")


def validate_candidate(*, image: bytes, image_sha256: str,
                       descriptor: CandidateHardware, measured: CandidateHardware,
                       recovery: bytes, recovery_sha256: str,
                       exclusive_owner: bool, consumers_quiesced: bool,
                       axi_isolated: bool, external_io_isolated: bool,
                       all_sites_idle: bool, admission_locked: bool) -> None:
    """Pure host candidate check; no load, upload, lock acquisition or authority.

    Inputs must be derived by the existing owner under its shared admission
    lock. Success is compatibility/integrity only, never runtime admission.
    Protected executable source pins remain enforced by the existing root entry.
    Historical ImageLock below retains its legacy build/executor coupling until
    explicitly migrated; this function is not wired to that privileged path.
    """
    need(type(descriptor) is CandidateHardware and
         type(measured) is CandidateHardware, "CANDIDATE_DESCRIPTOR_REQUIRED")
    descriptor.validate()
    measured.validate()
    need(descriptor == measured, "CANDIDATE_HARDWARE_MISMATCH")
    need(type(image) is bytes and bool(image) and
         type(recovery) is bytes and bool(recovery), "BUNDLE_BYTES_MISSING")
    need(hex_pin(image_sha256, 64) and hex_pin(recovery_sha256, 64),
         "IMAGE_SHA_INVALID")
    need(hashlib.sha256(image).hexdigest() == image_sha256 and
         hashlib.sha256(recovery).hexdigest() == recovery_sha256,
         "IMAGE_BUNDLE_HASH_MISMATCH")
    need(image_sha256 != recovery_sha256, "CANDIDATE_IS_RECOVERY")
    need(all(type(v) is bool and v for v in (
        exclusive_owner, consumers_quiesced, axi_isolated, external_io_isolated,
        all_sites_idle, admission_locked)), "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN")


def validate_source_lock(*, project: str, expected_project: str,
                         reviewed_sha: str, installed_sha: str, build_sha: str,
                         bit_sha: str, hwh_sha: str, bin_sha: str,
                         original_sha: str) -> None:
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
    """IC Programming Jobs cannot become FPGA configuration commands."""
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
    need(type(action) is str and action in STAGE_RESULTS,
         "STAGE_PLAN_INVALID")
    need(hex_pin(expected_image_sha, 64) and hex_pin(candidate_sha, 64)
         and hex_pin(original_sha, 64), "STAGE_PLAN_TAMPERED")
    try:
        selected = choose_stage(stage, phase)
    except StageDenied:
        raise StageDenied("STAGE_PLAN_TAMPERED") from None
    wanted = (candidate_sha if selected in
              ("PLAN_DOWNLOAD", "PLAN_READ_ONLY_ABI") else original_sha)
    need(selected == action and expected_image_sha == wanted,
         "STAGE_PLAN_TAMPERED")


@dataclass(frozen=True)
class ImageLock:
    project: str                      # independent root-profile project claim
    descriptor: ImageDescriptor
    reviewed_source_sha: str
    installed_source_sha: str
    image_build_source_sha: str
    bit_sha256: str
    hwh_sha256: str
    bin_sha256: str
    recovery_sha256: str

    def validate(self) -> None:
        need(isinstance(self.descriptor, ImageDescriptor),
             "IMAGE_DESCRIPTOR_MISSING")
        d = self.descriptor
        d.validate()
        validate_source_lock(
            project=self.project, expected_project=d.project,
            reviewed_sha=self.reviewed_source_sha,
            installed_sha=self.installed_source_sha,
            build_sha=self.image_build_source_sha,
            bit_sha=self.bit_sha256, hwh_sha=self.hwh_sha256,
            bin_sha=self.bin_sha256, original_sha=self.recovery_sha256)
        need(d.image_build_source_sha == self.image_build_source_sha and
             d.bit_sha256 == self.bit_sha256 and
             d.hwh_sha256 == self.hwh_sha256 and
             d.bin_sha256 == self.bin_sha256, "IMAGE_DESCRIPTOR_HASH_OR_SOURCE_MISMATCH")
        # A null recovery in the real historical PoC descriptor is a
        # deliberate NO-GO. Synthetic tests may supply a fake fixture
        # descriptor with a fake matching recovery hash, but no live backend.
        need(d.recovery_sha256 is not None and
             d.recovery_sha256 == self.recovery_sha256,
             "RECOVERY_IMAGE_NOT_QUALIFIED")

    def check_bundle(self, *, bit: bytes, hwh: bytes, binary: bytes,
                     original: bytes) -> None:
        self.validate()
        validate_bundle(bit=bit, hwh=hwh, binary=binary, original=original,
                        bit_sha=self.bit_sha256, hwh_sha=self.hwh_sha256,
                        bin_sha=self.bin_sha256, original_sha=self.recovery_sha256)


@dataclass(frozen=True)
class Observed:
    """Injected observation for HOST TESTS ONLY; NEVER root attestation."""
    boot_id: str
    board: str
    manager: str
    active_image_sha256: str
    candidate_sha256: str
    recovery_sha256: str
    gp0_base: int
    gp0_size: int
    fclk_hz: int
    pin_map: tuple[tuple[str, str], ...]
    source_manifest_verified: bool
    exclusive_fpga_owner: bool
    consumers_quiesced: bool
    axi_isolation_proved: bool
    rollback_available: bool
    external_io_isolated: bool
    active_image_attested: bool


@dataclass(frozen=True)
class StageState:
    boot_id: str
    source_sha: str
    phase: str
    image_sha256: str


@dataclass(frozen=True)
class StagePlan:
    stage: str
    source_sha: str
    boot_id: str
    expected_image_sha256: str
    current: StageState
    action: str


def _observe(lock: ImageLock, facts: Observed) -> None:
    d = lock.descriptor
    need(isinstance(facts, Observed), "TARGET_OBSERVATION_MISSING")
    need(type(facts.boot_id) is str and len(facts.boot_id) >= 8
         and facts.board == d.board and facts.manager == "operating",
         "TARGET_BOOT_OR_BOARD_UNPROVEN")
    need(facts.candidate_sha256 == lock.bin_sha256 and
         facts.recovery_sha256 == lock.recovery_sha256 and
         hex_pin(facts.active_image_sha256, 64),
         "TARGET_IMAGE_IDENTITY_MISMATCH")
    need(type(facts.gp0_base) is int and facts.gp0_base == d.axi_base and
         type(facts.gp0_size) is int and facts.gp0_size == d.axi_bytes and
         type(facts.fclk_hz) is int and facts.fclk_hz == d.fclk_hz and
         type(facts.pin_map) is tuple and facts.pin_map == d.pin_map,
         "TARGET_GP0_CLOCK_OR_PIN_MISMATCH")
    # These flags are untrusted fixtures. A real root owner must derive
    # each fact independently; the policy has no route to hardware.
    need(all(type(x) is bool and x for x in (
         facts.source_manifest_verified, facts.exclusive_fpga_owner,
         facts.consumers_quiesced, facts.axi_isolation_proved,
         facts.rollback_available, facts.external_io_isolated,
         facts.active_image_attested)), "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN")


def prepare(stage: str, lock: ImageLock, facts: Observed,
            state: StageState | None) -> StagePlan:
    need(type(stage) is str and stage in STAGES, "STAGE_NOT_ALLOWLISTED")
    need(isinstance(lock, ImageLock), "IMAGE_LOCK_MISSING")
    lock.validate()
    _observe(lock, facts)
    if state is None:
        need(stage == "download", "DOWNLOAD_REQUIRED_BEFORE_TEST_OR_RESTORE")
        need(facts.active_image_sha256 == lock.recovery_sha256,
             "ORIGINAL_IMAGE_NOT_ATTESTED")
        current = StageState(facts.boot_id, lock.reviewed_source_sha,
                             "BASE", lock.recovery_sha256)
    else:
        need(isinstance(state, StageState) and state.phase in ("BASE", "HELD")
             and state.boot_id == facts.boot_id
             and state.source_sha == lock.reviewed_source_sha,
             "STALE_BOOT_OR_IN_FLIGHT_MANUAL_RECOVERY")
        expected = (lock.recovery_sha256 if state.phase == "BASE"
                    else lock.bin_sha256)
        need(state.image_sha256 == expected and
             facts.active_image_sha256 == expected,
             "ACTIVE_IMAGE_OR_STATE_UNATTESTED")
        current = state
    action = choose_stage(stage, current.phase)
    target = (lock.bin_sha256 if action in
              ("PLAN_DOWNLOAD", "PLAN_READ_ONLY_ABI")
              else lock.recovery_sha256)
    return StagePlan(stage, lock.reviewed_source_sha, facts.boot_id,
                     target, current, action)


def confirm(plan: StagePlan, lock: ImageLock, after: Observed,
            *, abi_reads: tuple[int, ...] = (),
            write_count: int = 0) -> tuple[StageState, dict]:
    """Only SIMULATED result; NEVER accepted as Root Entry evidence."""
    need(isinstance(plan, StagePlan) and plan.action in STAGE_RESULTS,
         "STAGE_PLAN_INVALID")
    need(isinstance(lock, ImageLock), "IMAGE_LOCK_MISSING")
    lock.validate()
    need(plan.current.boot_id == plan.boot_id and
         plan.current.source_sha == plan.source_sha and
         plan.current.phase in ("BASE", "HELD") and
         plan.current.image_sha256 ==
         (lock.recovery_sha256 if plan.current.phase == "BASE"
          else lock.bin_sha256), "STAGE_PLAN_STATE_INVALID")
    validate_stage_plan(
        stage=plan.stage, phase=plan.current.phase, action=plan.action,
        expected_image_sha=plan.expected_image_sha256,
        candidate_sha=lock.bin_sha256, original_sha=lock.recovery_sha256)
    _observe(lock, after)
    need(after.boot_id == plan.boot_id and
         plan.source_sha == lock.reviewed_source_sha and
         after.active_image_sha256 == plan.expected_image_sha256,
         "STAGE_AFTER_IDENTITY_OR_BOOT_MISMATCH")
    need(type(write_count) is int and write_count == 0,
         "UNEXPECTED_REGISTER_WRITE")
    if plan.action == "PLAN_READ_ONLY_ABI":
        checks = lock.descriptor.read_only_identity
        need(type(abi_reads) is tuple and len(abi_reads) == len(checks) and
             all(_u32(v) and (v & mask) == expected for v, (_, expected, mask)
                 in zip(abi_reads, checks)),
             "IMAGE_READ_ONLY_IDENTITY_OR_SAFE_IO_MISMATCH")
    else:
        need(abi_reads == (), "UNEXPECTED_MMIO_OBSERVATION")
    phase = ("HELD" if plan.expected_image_sha256 == lock.bin_sha256
             else "BASE")
    state = StageState(plan.boot_id, plan.source_sha, phase,
                       plan.expected_image_sha256)
    receipt = {
        "model": "plasma.fpga.configuration.host-only.v1",
        "stage": plan.stage, "result": STAGE_RESULTS[plan.action],
        "real_z2": False, "hardware_authorized": False,
        "runtime_admitted": False, "boot_id": plan.boot_id,
        "source_sha": plan.source_sha, "project": lock.descriptor.project,
    }
    return state, receipt


def main() -> int:
    print("GENERIC_FPGA_CONFIGURATION_LIVE_BACKEND_NOT_IMPLEMENTED",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
