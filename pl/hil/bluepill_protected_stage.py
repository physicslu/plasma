"""Blue Pill Site 1 protected-stage *policy model*, Host-only / NO hardware.

Future root-installed Stage must independently bind source manifest, device,
AXI isolation, FPGA owner, external electrical state and recovery. This module
has no privileged adapter or live execution entry. Injected observations are
test fixtures, never authorizations. In particular no F1-B risk waiver applies.

Stages are separately planned and acknowledged; an in-flight/crashed stage is
UNKNOWN and must stop for independently qualified manual recovery. Only a
future reviewed root backend can supply authenticated hardware observations.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys

from pl.hil import fpga_configuration_policy as core

PROJECT = "pl/projects/z2-bluepill-rbb"
MAGIC = 0x50425357
ABI = 0x00010000
BASE = 0x40008000
SIZE = 4096
CLOCK_HZ = 100_000_000
BOARD = "pynq-z2:xc7z020clg400-1"
# Generic image/configuration lifecycle shared across programming providers.
# This PoC retains only board-specific SWD GPIO identities and wiring.
STAGES = core.STAGES
StageDenied = core.StageDenied
need = core.need
hex_pin = core.hex_pin


@dataclass(frozen=True)
class ImageLock:
    """Input lock; NOT an on-device verified root-owned manifest."""
    project: str
    reviewed_source_sha: str
    installed_source_sha: str
    image_build_source_sha: str
    bit_sha256: str
    hwh_sha256: str
    bin_sha256: str
    recovery_sha256: str

    def validate(self) -> None:
        core.validate_source_lock(
            project=self.project, expected_project=PROJECT,
            reviewed_sha=self.reviewed_source_sha,
            installed_sha=self.installed_source_sha,
            build_sha=self.image_build_source_sha,
            bit_sha=self.bit_sha256, hwh_sha=self.hwh_sha256,
            bin_sha=self.bin_sha256, original_sha=self.recovery_sha256)

    def check_bundle(self, *, bit: bytes, hwh: bytes, binary: bytes,
                     original: bytes) -> None:
        """Host-only content hashes; no claim of root-installed image."""
        self.validate()
        core.validate_bundle(
            bit=bit, hwh=hwh, binary=binary, original=original,
            bit_sha=self.bit_sha256, hwh_sha=self.hwh_sha256,
            bin_sha=self.bin_sha256, original_sha=self.recovery_sha256)


@dataclass(frozen=True)
class Observed:
    """Synthetic test observation; has no credential or hardware authority."""
    boot_id: str
    board: str
    manager: str
    active_image_sha256: str
    candidate_sha256: str
    recovery_sha256: str
    gp0_base: int
    gp0_size: int
    fclk_hz: int
    swclk_pin: str
    swdio_pin: str
    source_manifest_verified: bool
    exclusive_fpga_owner: bool
    consumers_quiesced: bool
    axi_isolation_proved: bool
    rollback_available: bool
    pmod_disconnected: bool
    active_image_attested: bool


@dataclass(frozen=True)
class StageState:
    boot_id: str
    source_sha: str
    phase: str                    # BASE / HELD / UNKNOWN
    image_sha256: str


@dataclass(frozen=True)
class StagePlan:
    stage: str
    source_sha: str
    boot_id: str
    expected_image_sha256: str
    current: StageState
    action: str                   # model only; never executable


def _observe(lock: ImageLock, facts: Observed) -> None:
    need(isinstance(facts, Observed), "TARGET_OBSERVATION_MISSING")
    need(type(facts.boot_id) is str and len(facts.boot_id) >= 8
         and facts.board == BOARD and facts.manager == "operating",
         "TARGET_BOOT_OR_BOARD_UNPROVEN")
    need(facts.candidate_sha256 == lock.bin_sha256 and
         facts.recovery_sha256 == lock.recovery_sha256 and
         hex_pin(facts.active_image_sha256, 64),
         "TARGET_IMAGE_IDENTITY_MISMATCH")
    need(type(facts.gp0_base) is int and facts.gp0_base == BASE and
         type(facts.gp0_size) is int and facts.gp0_size == SIZE and
         type(facts.fclk_hz) is int and facts.fclk_hz == CLOCK_HZ and
         facts.swclk_pin == "W14" and facts.swdio_pin == "Y14",
         "TARGET_GP0_CLOCK_OR_PIN_MISMATCH")
    # Observed booleans below are synthetic and explicitly do NOT prove
    # live safety. The real root owner must gather these independently.
    need(all(type(x) is bool and x for x in (
         facts.source_manifest_verified, facts.exclusive_fpga_owner,
         facts.consumers_quiesced, facts.axi_isolation_proved,
         facts.rollback_available, facts.pmod_disconnected,
         facts.active_image_attested)), "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN")


def prepare(stage: str, lock: ImageLock, facts: Observed,
            state: StageState | None) -> StagePlan:
    """Check preconditions for a hypothetical *separately invoked* stage."""
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
        need(isinstance(state, StageState) and
             state.phase in ("BASE", "HELD") and
             state.boot_id == facts.boot_id and
             state.source_sha == lock.reviewed_source_sha,
             "STALE_BOOT_OR_IN_FLIGHT_MANUAL_RECOVERY")
        expected = (lock.recovery_sha256 if state.phase == "BASE"
                    else lock.bin_sha256)
        need(state.image_sha256 == expected and
             facts.active_image_sha256 == expected,
             "ACTIVE_IMAGE_OR_STATE_UNATTESTED")
        current = state
    action = core.choose_stage(stage, current.phase)
    target = (lock.bin_sha256 if action in
              ("PLAN_DOWNLOAD", "PLAN_READ_ONLY_ABI")
              else lock.recovery_sha256)
    return StagePlan(stage, lock.reviewed_source_sha, facts.boot_id,
                     target, current, action)


def confirm(plan: StagePlan, lock: ImageLock, after: Observed,
            *, abi_reads: tuple[int, ...] = (),
            write_count: int = 0) -> tuple[StageState, dict]:
    """Validate synthetic stage result, not an authenticated target receipt.

    Actual hardware execution must journal intent before any write, mark
    interrupted/failed transitions UNKNOWN and independently restore. A
    consumer must NEVER forward this simulation result to StageTransport.
    """
    need(isinstance(plan, StagePlan) and plan.action in (
         "PLAN_DOWNLOAD", "PLAN_READ_ONLY_ABI", "PLAN_RESTORE",
         "PLAN_RESTORED_NOOP"), "STAGE_PLAN_INVALID")
    need(isinstance(lock, ImageLock), "IMAGE_LOCK_MISSING")
    lock.validate()
    need(plan.current.boot_id == plan.boot_id and
         plan.current.source_sha == plan.source_sha and
         plan.current.phase in ("BASE", "HELD") and
         plan.current.image_sha256 ==
         (lock.recovery_sha256 if plan.current.phase == "BASE"
          else lock.bin_sha256), "STAGE_PLAN_STATE_INVALID")
    core.validate_stage_plan(
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
        need(type(abi_reads) is tuple and len(abi_reads) == 3 and
             all(type(x) is int and 0 <= x <= 0xFFFFFFFF for x in abi_reads)
             and abi_reads[0] == MAGIC and abi_reads[1] == ABI and
             abi_reads[2] & 0x0E == 0x08 and abi_reads[2] & ~0x0F == 0,
             "BLUEPILL_READ_ONLY_ABI_OR_SAFE_IO_MISMATCH")
    else:
        need(abi_reads == (), "UNEXPECTED_MMIO_OBSERVATION")
    phase = ("HELD" if plan.expected_image_sha256 == lock.bin_sha256
             else "BASE")
    result = core.STAGE_RESULTS[plan.action]
    state = StageState(plan.boot_id, plan.source_sha, phase,
                       plan.expected_image_sha256)
    receipt = {"model": "plasma.fpga.configuration.host-only.v1",
               "stage": plan.stage, "result": result, "real_z2": False,
               "hardware_authorized": False, "runtime_admitted": False,
               "boot_id": plan.boot_id, "source_sha": plan.source_sha,
               "project": PROJECT}
    return state, receipt


def main() -> int:
    """No root execution adapter is supplied by this Gate 1 candidate."""
    print("BLUEPILL_LIVE_STAGE_BACKEND_NOT_IMPLEMENTED", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
