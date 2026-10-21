"""Root-owned, passive Z2 safety probe and shared FPGA lock for Path 2.

This implements the observable *read-only* part of the target Provider.
It deliberately cannot authorize FPGA Manager writes: a bound AXI/UIO
driver and a complete /proc scan do not prove PL/AXI quiescence.
No CLI, credentials, SSH, sudo escalation, shell, or hardware writes.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import time

from pl.hil import f1b
from pl.hil.swd04 import one_shot

SYS = Path("/sys")
PROC = Path("/proc")
FIRMWARE = Path("/lib/firmware")
GLOBAL_LOCK = one_shot.OWNER_LOCK
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class TargetSafetyDenied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise TargetSafetyDenied(code)


def _sha_file(path: Path, expected: str) -> str:
    """Review a protected immutable F1-B firmware file without reading MMIO."""
    need(SHA256.fullmatch(expected) is not None, "PINNED_IMAGE_HASH_DENIED")
    one_shot.protected(path)
    need(path.parent == FIRMWARE and path.is_file()
         and path.stat().st_size <= 16_000_000,
         "FIRMWARE_OR_RECOVERY_LOCATION_DENIED")
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    need(actual == expected, "FIRMWARE_BYTES_CHANGED")
    return actual


def _overlap(start: int, length: int) -> bool:
    return length > 0 and start < f1b.BASE + f1b.LENGTH and start + length > f1b.BASE


def classify_passive_facts(facts: object) -> dict:
    """No caller-supplied bool or historical one-shot waiver grants AXI safety."""
    required = {
        "root", "boot_id", "manager_state", "recovery_sha256",
        "candidate_sha256", "uio_overlaps", "platform_overlaps",
        "proc_complete", "proc_conflicts", "observation_kind",
        "axi_isolation_evidence", "active_image_attestation",
    }
    need(type(facts) is dict and set(facts) == required,
         "TARGET_FACT_SCHEMA_DENIED")
    need(facts["observation_kind"] == "LIVE_ROOT_READ_ONLY" and
         facts["root"] is True and type(facts["boot_id"]) is str and
         bool(facts["boot_id"]), "ROOT_TARGET_OR_BOOT_UNPROVEN")
    need(facts["manager_state"] == "operating" and
         facts["recovery_sha256"] == f1b.BASE_SHA and
         facts["candidate_sha256"] == f1b.BIN_SHA,
         "FIRMWARE_OR_MANAGER_UNPROVEN")
    need(type(facts["uio_overlaps"]) is list and
         type(facts["platform_overlaps"]) is list and
         type(facts["proc_conflicts"]) is list and
         all(type(x) is str and x for key in (
             "uio_overlaps", "platform_overlaps", "proc_conflicts")
             for x in facts[key]) and
         facts["proc_complete"] is True,
         "KERNEL_OR_PROCESS_VISIBILITY_UNPROVEN")
    # Even an empty list is *not* proof of bus idleness.
    blockers = []
    if facts["uio_overlaps"]:
        blockers.append("BOUND_UIO_IN_F1B_APERTURE")
    if facts["platform_overlaps"]:
        blockers.append("BOUND_PLATFORM_IN_F1B_APERTURE")
    if facts["proc_conflicts"]:
        blockers.append("RETAINED_MMIO_PROCESS_MAPPING")
    # No independently supported isolation observer exists in main. A
    # JSON string "PASS", owner verbal attestation or historical run is not one.
    if facts["axi_isolation_evidence"] != "INDEPENDENT_HARDWARE_PROOF":
        blockers.append("AXI_ISOLATION_UNPROVEN")
    # sysfs manager.state and dmesg alone cannot attest loaded BIT/BIN.
    if facts["active_image_attestation"] != "INDEPENDENT_TARGET_PROOF":
        blockers.append("ACTIVE_FPGA_IMAGE_UNATTESTED")
    return {"decision": "NO_GO", "blockers": blockers or
            ["LIVE_PROVIDER_AND_PROOF_AUTHORITY_NOT_REGISTERED"],
            "scope": "PASSIVE_OBSERVATION_ONLY",
            "hardware_write_authorized": False}


def scan_kernel_owners(*, sysroot: Path) -> tuple[list[str], list[str]]:
    """Any overlapping bound UIO/platform driver remains a hardware blocker."""
    uio, platform = [], []
    for item in sorted((sysroot / "class/uio").glob("uio*")):
        mapped = False
        for resource in sorted((item / "maps").glob("map*")):
            address = int((resource / "addr").read_text().strip(), 0)
            length = int((resource / "size").read_text().strip(), 0)
            mapped |= _overlap(address, length)
        if mapped and (item / "device/driver").exists():
            uio.append(item.name)
    for item in sorted((sysroot / "bus/platform/devices").iterdir()):
        if not (item / "driver").exists():
            continue
        name = re.match(r"^([0-9a-fA-F]+)\.", item.name)
        conflict = bool(name and _overlap(int(name[1], 16), 1))
        resource = item / "resource"
        if resource.exists():
            for line in resource.read_text().splitlines():
                parts = line.split()
                need(len(parts) == 3, "PLATFORM_RESOURCE_FORMAT_DENIED")
                lo, hi, flags = (int(x, 16) for x in parts)
                if flags & 0x200:
                    conflict |= _overlap(lo, hi + 1 - lo)
        if conflict:
            platform.append(item.name)
    return uio, platform


def scan_proc_consumers(*, procroot: Path) -> tuple[bool, list[str]]:
    """Full bounded live-process visibility; never read process command lines."""
    conflicts = []
    observed = 0
    for item in sorted(procroot.iterdir()):
        if not item.name.isdecimal():
            continue
        try:
            targets = []
            for fd in (item / "fd").iterdir():
                try:
                    targets.append(os.readlink(fd))
                except FileNotFoundError:
                    continue
            f1b.reject_retained_fds(targets)
            f1b.reject_retained_maps((item / "maps").read_text())
            observed += 1
        except FileNotFoundError:
            need(not item.exists(), "LIVE_PROCESS_SCAN_INCOMPLETE")
        except (ValueError, PermissionError, OSError) as exc:
            # A conflicting client is a concrete blocker, not permission to
            # continue the probe on incomplete enumeration.
            conflicts.append(item.name)
            if isinstance(exc, (PermissionError, OSError)):
                return False, conflicts
    return observed > 0, conflicts


def read_live_z2_facts(*, candidate: Path, recovery: Path) -> dict:
    """Target-side root-only passive collection; no candidate FPGA write."""
    need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
    need(candidate.parent == FIRMWARE and recovery == FIRMWARE / "base.bin",
         "UNREVIEWED_FIRMWARE_PATH")
    boot_before = (PROC / "sys/kernel/random/boot_id").read_text().strip()
    need(bool(boot_before), "BOOT_ID_UNAVAILABLE")
    candidate_sha = _sha_file(candidate, f1b.BIN_SHA)
    recovery_sha = _sha_file(recovery, f1b.BASE_SHA)
    compatible = (PROC / "device-tree/compatible").read_bytes().split(b"\0")
    need(b"xlnx,zynq-7000" in compatible, "ZYNQ_FAMILY_MISMATCH")
    manager = (SYS / "class/fpga_manager/fpga0/state").read_text().strip()
    uio, platform = scan_kernel_owners(sysroot=SYS)
    complete, conflicts = scan_proc_consumers(procroot=PROC)
    boot_after = (PROC / "sys/kernel/random/boot_id").read_text().strip()
    need(boot_before == boot_after, "BOOT_CHANGED_DURING_SCAN")
    return {
        "root": True, "boot_id": boot_before, "manager_state": manager,
        "recovery_sha256": recovery_sha, "candidate_sha256": candidate_sha,
        "uio_overlaps": uio, "platform_overlaps": platform,
        "proc_complete": complete, "proc_conflicts": conflicts,
        "observation_kind": "LIVE_ROOT_READ_ONLY",
        "axi_isolation_evidence": "UNPROVEN",
        "active_image_attestation": "UNPROVEN",
    }


class RootZ2TargetPort:
    """Shared-lock read-only portion of a future privileged TargetPort.

    This intentionally does NOT implement a write-capable Port. The caller
    must not cast an arbitrary test object into FPGA Manager authority.
    """

    def __init__(self, *, candidate: Path, recovery: Path, ledger: Path):
        self.candidate, self.recovery, self.ledger = candidate, recovery, ledger
        self._locked = False

    @contextmanager
    def exclusive(self):
        need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
        one_shot.protected(GLOBAL_LOCK.parent, file=False)
        need(self.ledger.parent.is_dir() and
             self.ledger.parent.resolve() == GLOBAL_LOCK.parent.resolve(),
             "GLOBAL_OWNER_LEDGER_LOCATION_DENIED")
        fd = os.open(GLOBAL_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and
                 st.st_nlink == 1 and st.st_mode & 0o077 == 0,
                 "GLOBAL_FPGA_LOCK_UNTRUSTED")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
            yield self
        finally:
            self._locked = False
            os.close(fd)

    def passive_report(self) -> dict:
        need(self._locked, "FPGA_OWNER_LOCK_REQUIRED")
        return classify_passive_facts(read_live_z2_facts(
            candidate=self.candidate, recovery=self.recovery))

    def now(self) -> int:
        need(self._locked, "FPGA_OWNER_LOCK_REQUIRED")
        return int(time.time())

    def qualification(self, stage: str) -> dict:
        need(stage in ("download", "test", "restore"), "STAGE_DENIED")
        report = self.passive_report()
        raise TargetSafetyDenied("TARGET_AXΙ_OR_IMAGE_ISOLATION_NO_GO: " +
                                 ",".join(report["blockers"]))

    def observation(self, observed_at: int) -> dict:
        raise TargetSafetyDenied("AUTHENTICATED_LOADED_IMAGE_OBSERVER_NOT_INSTALLED")

    def image_sha256(self, which: str) -> str:
        need(self._locked, "FPGA_OWNER_LOCK_REQUIRED")
        need(which in ("candidate", "recovery"), "IMAGE_NAME_DENIED")
        return _sha_file(self.candidate if which == "candidate" else self.recovery,
                         f1b.BIN_SHA if which == "candidate" else f1b.BASE_SHA)

    def load_candidate_once(self, bin_sha256: str) -> dict:
        raise TargetSafetyDenied("AXI_ISOLATION_UNPROVEN_NO_FPGA_WRITE")

    def read_f1b_identity_child(self) -> dict:
        raise TargetSafetyDenied("CURRENT_IMAGE_OR_CHILD_ADMISSION_NOT_QUALIFIED")

    def restore_original_once(self, recovery_sha256: str) -> dict:
        raise TargetSafetyDenied("SAFE_RECOVERY_CONTEXT_NOT_QUALIFIED")
