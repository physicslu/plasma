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
import threading

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
    uio_root = sysroot / "class/uio"
    platform_root = sysroot / "bus/platform/devices"
    # Glob silently accepts a missing directory: missing kernel ownership
    # visibility must never appear to be a clean FPGA configuration.
    need(uio_root.is_dir() and platform_root.is_dir(),
         "KERNEL_OWNER_VISIBILITY_UNPROVEN")
    for item in sorted(uio_root.iterdir()):
        if not re.fullmatch(r"uio[0-9]+", item.name):
            continue
        mapped = False
        maps = item / "maps"
        need(maps.is_dir(), "UIO_MAP_VISIBILITY_UNPROVEN")
        resources = sorted(maps.iterdir())
        need(bool(resources), "UIO_MAP_VISIBILITY_UNPROVEN")
        for resource in resources:
            need(re.fullmatch(r"map[0-9]+", resource.name) is not None,
                 "UIO_MAP_FORMAT_DENIED")
            address = int((resource / "addr").read_text().strip(), 0)
            length = int((resource / "size").read_text().strip(), 0)
            need(0 <= address < 2**32 and 0 < length <= 2**32 - address,
                 "UIO_MAP_RANGE_DENIED")
            mapped |= _overlap(address, length)
        if mapped and (item / "device/driver").exists():
            uio.append(item.name)
    for item in sorted(platform_root.iterdir()):
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
                    need(0 <= lo <= hi < 2**32,
                         "PLATFORM_RESOURCE_RANGE_DENIED")
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
                    # A disappearing FD may have retained an MMIO mapping.
                    return False, [*conflicts, item.name]
            maps = (item / "maps").read_text()
            observed += 1
            # Parse only after full per-process fd/maps collection. A
            # genuine conflict is different from incomplete visibility.
            try:
                f1b.reject_retained_fds(targets)
                f1b.reject_retained_maps(maps)
            except ValueError:
                conflicts.append(item.name)
        except FileNotFoundError:
            # A disappearing PID means this snapshot is incomplete, even
            # when it is a normal transient Linux process.
            return False, [*conflicts, item.name]
        except (PermissionError, OSError):
            return False, [*conflicts, item.name]
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
        self._lock_owner_pid: int | None = None
        self._lock_owner_thread: int | None = None

    def _require_locked(self) -> None:
        need(self._locked and self._lock_owner_pid == os.getpid() and
             self._lock_owner_thread == threading.get_ident(),
             "FPGA_OWNER_LOCK_REQUIRED")

    @contextmanager
    def exclusive(self):
        need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
        need(not self._locked, "REENTRANT_TARGET_LOCK_DENIED")
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
            self._lock_owner_pid = os.getpid()
            self._lock_owner_thread = threading.get_ident()
            yield self
        finally:
            # Guard ownership is bound to the calling process and thread,
            # not to an ambient Boolean shared with other callers.
            self._locked = False
            self._lock_owner_pid = None
            self._lock_owner_thread = None
            os.close(fd)

    def passive_report(self) -> dict:
        self._require_locked()
        return classify_passive_facts(read_live_z2_facts(
            candidate=self.candidate, recovery=self.recovery))

    def now(self) -> int:
        self._require_locked()
        return int(time.time())

    def qualification(self, stage: str) -> dict:
        need(stage in ("download", "test", "restore"), "STAGE_DENIED")
        report = self.passive_report()
        raise TargetSafetyDenied("TARGET_AXI_OR_IMAGE_ISOLATION_NO_GO: " +
                                 ",".join(report["blockers"]))

    def observation(self, observed_at: int) -> dict:
        raise TargetSafetyDenied("AUTHENTICATED_LOADED_IMAGE_OBSERVER_NOT_INSTALLED")

    def image_sha256(self, which: str) -> str:
        self._require_locked()
        need(which in ("candidate", "recovery"), "IMAGE_NAME_DENIED")
        return _sha_file(self.candidate if which == "candidate" else self.recovery,
                         f1b.BIN_SHA if which == "candidate" else f1b.BASE_SHA)

    def inspect_cross_trigger(self, stage: str) -> dict:
        """Current-boot checkpoint; never infer attestation from manager logs.

        This accepts only an existing durable target ledger for the held
        Testing/Restore triggers. It is read-only and cannot authorize
        reconfiguration, erase a stale lease, or reactivate unknown hardware.
        """
        self._require_locked()
        need(stage in ("testing", "restore"), "STAGE_DENIED")
        from scripts import plasma_path2_persistent_lease as lease
        record = lease.LeaseLedger(self.ledger).snapshot()
        need(record["status"] == "LOADED_AND_HELD" and
             record["load_attempts"] == 1 and
             record["restore_attempts"] == 0 and
             record["artifact_sha256"] == f1b.BIN_SHA and
             record["recovery_sha256"] == f1b.BASE_SHA,
             "CROSS_TRIGGER_LEASE_NOT_ACTIVE")
        now = self.now()
        need(now >= record["last_seen"] and now < record["lease_deadline"],
             "HELD_IMAGE_LEASE_EXPIRED")
        live = read_live_z2_facts(candidate=self.candidate,
                                  recovery=self.recovery)
        need(live["boot_id"] == record["boot_id"] and
             live["manager_state"] == "operating" and
             live["proc_complete"] is True and
             live["proc_conflicts"] == [],
             "CROSS_TRIGGER_BOOT_OR_MMIO_OWNER_CHANGED")
        last_load = one_shot.manager_last_load()
        need(": writing " + self.candidate.name + " to " in last_load,
             "HELD_IMAGE_MANAGER_PROVENANCE_UNPROVEN")
        # Metadata alone cannot attest loaded FPGA configuration bits.
        return {
            "stage": stage,
            "lease_id": record["lease_id"],
            "boot_id": record["boot_id"],
            "manager_state": live["manager_state"],
            "manager_last_load": last_load,
            "loaded_image_identity": "MANAGER_LOG_ONLY_UNATTESTED",
            "axi_isolation": "UNPROVEN",
            "live_uio_overlaps": live["uio_overlaps"],
            "live_platform_overlaps": live["platform_overlaps"],
            "status": "PASSIVE_CHECKPOINT_REVIEW_REQUIRED",
            "hardware_write_authorized": False,
        }

    def load_candidate_once(self, bin_sha256: str) -> dict:
        raise TargetSafetyDenied("AXI_ISOLATION_UNPROVEN_NO_FPGA_WRITE")

    def read_f1b_identity_child(self) -> dict:
        raise TargetSafetyDenied("CURRENT_IMAGE_OR_CHILD_ADMISSION_NOT_QUALIFIED")

    def restore_original_once(self, recovery_sha256: str) -> dict:
        raise TargetSafetyDenied("SAFE_RECOVERY_CONTEXT_NOT_QUALIFIED")
