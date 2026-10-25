"""Protected Z2 FPGA Image observations and exclusive configuration owner.

Source-pinned, Image-independent. This is not an unrestricted MMIO/FPGA
writer; the Root entry and approved release control all possible operations.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import threading

from pl.hil.swd04 import one_shot

SYS = Path("/sys")
PROC = Path("/proc")
FIRMWARE = Path("/lib/firmware")
GLOBAL_LOCK = one_shot.OWNER_LOCK


class TargetSafetyDenied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise TargetSafetyDenied(code)


def sha_file(path: Path, expected: str) -> str:
    need(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
         "PINNED_IMAGE_HASH_DENIED")
    one_shot.protected(path)
    need(path.parent == FIRMWARE and path.is_file() and
         0 < path.stat().st_size <= 16_000_000, "FIRMWARE_LOCATION_DENIED")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    need(digest.hexdigest() == expected, "FIRMWARE_BYTES_CHANGED")
    return digest.hexdigest()


def overlaps(start: int, size: int, base: int, length: int) -> bool:
    return size > 0 and start < base + length and start + size > base


def scan_kernel_owners(*, sysroot: Path, release) -> tuple[list[str], list[str]]:
    uio, platform = [], []
    base, size = release.owner_base, release.owner_bytes
    for item in sorted((sysroot / "class/uio").glob("uio*")):
        mapped = False
        for resource in sorted((item / "maps").glob("map*")):
            start = int((resource / "addr").read_text().strip(), 0)
            length = int((resource / "size").read_text().strip(), 0)
            mapped |= overlaps(start, length, base, size)
        if mapped and (item / "device/driver").exists():
            uio.append(item.name)
    for item in sorted((sysroot / "bus/platform/devices").iterdir()):
        if not (item / "driver").exists():
            continue
        name = re.match(r"^([0-9a-fA-F]+)\.", item.name)
        conflict = bool(name and overlaps(int(name[1], 16), 1, base, size))
        resource = item / "resource"
        if resource.exists():
            for line in resource.read_text().splitlines():
                parts = line.split()
                need(len(parts) == 3, "PLATFORM_RESOURCE_FORMAT_DENIED")
                lo, hi, flags = (int(x, 16) for x in parts)
                if flags & 0x200:
                    conflict |= overlaps(lo, hi + 1 - lo, base, size)
        if conflict:
            platform.append(item.name)
    return uio, platform


def scan_proc_consumers(*, procroot: Path, release) -> tuple[bool, list[str]]:
    conflicts, observed = [], 0
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
            maps = (item / "maps").read_text()
            observed += 1
            for target in targets:
                need(bool(target) and target != "UNKNOWN", "INCOMPLETE_FD_OBSERVATION")
                if target.startswith("/dev/uio") or target.split(" (deleted)")[0] in (
                        "/dev/mem", "/dev/xdevcfg", "/dev/fpga0"):
                    conflicts.append(item.name)
            for line in maps.splitlines():
                fields = line.split()
                need(len(fields) >= 5, "MALFORMED_PROC_VMA")
                if len(fields) < 6:
                    continue
                device = fields[5]
                if device.startswith("/dev/uio") or device in (
                        "/dev/xdevcfg", "/dev/fpga0"):
                    conflicts.append(item.name)
                elif device == "/dev/mem":
                    lo, hi = (int(x, 16) for x in fields[0].split("-"))
                    offset = int(fields[2], 16)
                    if overlaps(offset, hi - lo, release.owner_base,
                                release.owner_bytes):
                        conflicts.append(item.name)
        except (FileNotFoundError, PermissionError, OSError, ValueError):
            return False, sorted(set([*conflicts, item.name]))
    return observed > 0, sorted(set(conflicts))


def read_live_z2_facts(*, release) -> dict:
    need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
    candidate = FIRMWARE / release.firmware_name
    recovery = FIRMWARE / release.recovery_name
    need(candidate != recovery and candidate.parent == FIRMWARE and
         recovery.parent == FIRMWARE, "UNREVIEWED_FIRMWARE_PATH")
    boot_before = (PROC / "sys/kernel/random/boot_id").read_text().strip()
    need(bool(boot_before), "BOOT_ID_UNAVAILABLE")
    candidate_sha = sha_file(candidate, release.firmware_sha256)
    recovery_sha = sha_file(recovery, release.recovery_sha256)
    compatible = (PROC / "device-tree/compatible").read_bytes().split(b"\0")
    need(release.soc_compatible.encode("ascii") in compatible,
         "SOC_FAMILY_MISMATCH")
    manager = (SYS / "class/fpga_manager/fpga0/state").read_text().strip()
    uio, platform = scan_kernel_owners(sysroot=SYS, release=release)
    complete, conflicts = scan_proc_consumers(procroot=PROC, release=release)
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
    """Same exclusive global FPGA owner, bound to one source-authorized release."""
    def __init__(self, *, release):
        self.release = release
        self._locked = False
        self._lock_owner_pid = None
        self._lock_owner_thread = None

    def _require_locked(self) -> None:
        need(self._locked and self._lock_owner_pid == os.getpid() and
             self._lock_owner_thread == threading.get_ident(),
             "FPGA_OWNER_LOCK_REQUIRED")

    @contextmanager
    def exclusive(self):
        need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
        need(not self._locked, "REENTRANT_TARGET_LOCK_DENIED")
        one_shot.OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
        one_shot.protected(GLOBAL_LOCK.parent, file=False)
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
            self._locked = False
            self._lock_owner_pid = None
            self._lock_owner_thread = None
            os.close(fd)

    def current_facts(self) -> dict:
        self._require_locked()
        return read_live_z2_facts(release=self.release)

    def image_sha256(self, which: str) -> str:
        self._require_locked()
        need(which in ("candidate", "recovery"), "IMAGE_NAME_DENIED")
        filename = (self.release.firmware_name if which == "candidate"
                    else self.release.recovery_name)
        expected = (self.release.firmware_sha256 if which == "candidate"
                    else self.release.recovery_sha256)
        return sha_file(FIRMWARE / filename, expected)
