"""Protected Z2 FPGA Image observations and exclusive configuration owner.

Source-pinned, Image-independent. This is not an unrestricted MMIO/FPGA
writer; the Root entry and approved release control all possible operations.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading

SYS = Path("/sys")
PROC = Path("/proc")
FIRMWARE = Path("/lib/firmware")
# Retain the historic on-disk lock path so legacy SWD04 and this generic
# executor cannot both own/configure the same FPGA at once.
OWNER_DIR = Path("/run/plasma-z2-swd05")
GLOBAL_LOCK = OWNER_DIR / "supervisor.lock"
# Additional additive fence: each SWD Site holds LOCK_SH, Root reload LOCK_EX.
# Root Guard source-pin, provenance and supervisor.lock remain authoritative.
PPU_RELOAD_FENCE = Path("/run/lock/plasma-mmio.lock")
MANAGER = SYS / "class/fpga_manager/fpga0"


class TargetSafetyDenied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise TargetSafetyDenied(code)


def protected(path: Path, *, file: bool = True) -> None:
    """Enforce the same root ownership/path contract as the legacy supervisor."""
    need(path.is_absolute() and not path.is_symlink(), "Untrusted path")
    info = path.stat()
    need(info.st_uid == 0 and info.st_mode & 0o022 == 0, "Unprotected owner/mode")
    need(path.is_file() if file else path.is_dir(), "Unexpected object kind")
    parent = path.parent.stat()
    need(parent.st_uid == 0 and parent.st_mode & 0o022 == 0,
         "Unprotected parent")


def manager_last_load() -> str:
    """Read the most recent current-boot Linux FPGA Manager load record."""
    log = subprocess.run(["dmesg", "--color=never"], text=True, check=True,
                         capture_output=True, timeout=10).stdout
    loads = [line for line in log.splitlines()
             if "fpga_manager fpga0: writing " in line]
    need(bool(loads), "No current-boot FPGA Manager loading evidence")
    return loads[-1]


def manager_write(name: str) -> None:
    """Write a reviewed firmware basename; verify operating and load record."""
    need(bool(re.fullmatch(r"[A-Za-z0-9_.-]+", name)), "Illegal firmware name")
    with (MANAGER / "firmware").open("w") as stream:
        stream.write(name)
    need((MANAGER / "state").read_text().strip() == "operating",
         "FPGA Manager firmware load did not reach operating")
    need(f": writing {name} to " in manager_last_load(),
         "Firmware manager load provenance not observed")


def record_json(path: Path, data: dict) -> None:
    """Write exclusive result file and durably fsync it and parent directory."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write(chr(10))
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def run_child(args: list[str]) -> None:
    """Bound the MMIO subprocess and do not reload PL with an unreaped child."""
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        status = proc.wait(timeout=35)
    except subprocess.TimeoutExpired as exc:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise TargetSafetyDenied("MMIO_CHILD_UNREAPED_NO_RELOAD") from exc
        raise TargetSafetyDenied("MMIO_CHILD_TIMEOUT") from exc
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    raise TargetSafetyDenied("MMIO_CHILD_UNREAPED_NO_RELOAD")
        raise
    need(status == 0, "MMIO child failed or SIGBUS")


def sha_file(path: Path, expected: str) -> str:
    need(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
         "PINNED_IMAGE_HASH_DENIED")
    protected(path)
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


def scan_proc_consumers(*, procroot: Path, release,
                        diagnostic: dict | None = None) -> tuple[bool, list[str]]:
    """Fail-closed /proc owner census; retry only a confirmed vanished PID.

    A vanished process invalidates that snapshot. We restart the *whole*
    read-only census, never just skip that PID. Existing conflicts, denied
    visibility or still-live but unreadable PIDs are not retryable.
    """
    for attempt in range(1, 4):
        conflicts, observed = [], 0
        try:
            processes = sorted(procroot.iterdir())
        except (OSError, ValueError) as exc:
            if diagnostic is not None:
                diagnostic.update(status="PROC_ENUMERATION_FAILED",
                                  attempt=attempt, error=type(exc).__name__)
            return False, []
        retry_pid = None
        for item in processes:
            if not item.name.isdecimal():
                continue
            phase = "FD"
            try:
                targets = []
                for fd in (item / "fd").iterdir():
                    try:
                        targets.append(os.readlink(fd))
                    except FileNotFoundError:
                        # A closed file descriptor is no longer an owner;
                        # the subsequent full process VMA check is mandatory.
                        continue
                phase = "MAPS"
                maps = (item / "maps").read_text()
                observed += 1
                for target in targets:
                    need(bool(target) and target != "UNKNOWN",
                         "INCOMPLETE_FD_OBSERVATION")
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
            except (FileNotFoundError, PermissionError, OSError, ValueError) as exc:
                # Never retry a known conflict even if another process vanished.
                # Check for ENOENT explicitly; an inaccessible PID is NOT
                # a confirmed exit and must never qualify for a rescan.
                vanished = False
                if isinstance(exc, FileNotFoundError):
                    try:
                        item.stat()
                    except FileNotFoundError:
                        vanished = True
                    except OSError:
                        pass
                if vanished and not conflicts and attempt < 3:
                    retry_pid = item.name
                    break
                if diagnostic is not None:
                    diagnostic.update(
                        status=("PROC_CONFLICT_AND_INCOMPLETE" if conflicts else
                                "VANISHED_PID_RESCAN_EXHAUSTED" if vanished else
                                "PROC_VISIBILITY_DENIED"),
                        pid=item.name, phase=phase,
                        error=type(exc).__name__, attempt=attempt)
                return False, sorted(set([*conflicts, item.name]))
        if retry_pid is not None:
            # Start again from a fresh /proc listing. No DUT/FPGA I/O.
            continue
        if diagnostic is not None:
            diagnostic.update(
                status=("PROC_CONFLICT" if conflicts else
                        "COMPLETE" if observed > 0 else "NO_PROCESS_OBSERVED"),
                attempt=attempt, observed=observed,
                conflicts=len(set(conflicts)), rescans=attempt - 1)
        return observed > 0, sorted(set(conflicts))
    raise AssertionError("unreachable bounded process scan")


def read_live_z2_facts(*, release, runtime_program_session: bool = False) -> dict:
    """Keep kernel/image guards; runtime WordPort does not census all PIDs.

    Runtime call requires the same protected FPGA lock and is NOT a safe
    alternative for FPGA Manager load, test or restoration admission.
    """
    need(type(runtime_program_session) is bool, "INVALID_PROCESS_SCAN_POLICY")
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
    if runtime_program_session:
        # The session holds the global configuration lock. External device
        # consumers remain checked by the engine's scoped fuser preflight.
        # Do NOT fabricate proc_complete=True or a zero-conflict census.
        complete, conflicts = None, None
        proc_diagnostic = {"status": "NOT_RUN_PROGRAM_SESSION"}
    else:
        proc_diagnostic = {}
        complete, conflicts = scan_proc_consumers(
            procroot=PROC, release=release, diagnostic=proc_diagnostic)
    boot_after = (PROC / "sys/kernel/random/boot_id").read_text().strip()
    need(boot_before == boot_after, "BOOT_CHANGED_DURING_SCAN")
    return {
        "root": True, "boot_id": boot_before, "manager_state": manager,
        "recovery_sha256": recovery_sha, "candidate_sha256": candidate_sha,
        "uio_overlaps": uio, "platform_overlaps": platform,
        "proc_complete": complete, "proc_conflicts": conflicts,
        "proc_scan_diagnostic": proc_diagnostic,
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
        OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
        protected(GLOBAL_LOCK.parent, file=False)
        fd = os.open(GLOBAL_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fence_fd = None
        try:
            st = os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and
                 st.st_nlink == 1 and st.st_mode & 0o077 == 0,
                 "GLOBAL_FPGA_LOCK_UNTRUSTED")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Existing exclusive Root Guard is held FIRST. The same PPU
            # lock is held SH by all new per-Site SWD processes; reload
            # cannot run until every cooperating Site releases. This is
            # additive, not a substitute for provenance/Root checks.
            fence_fd = os.open(PPU_RELOAD_FENCE,
                               os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            st = os.fstat(fence_fd)
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                 st.st_mode & 0o002 == 0,
                 "PPU_RELOAD_FENCE_UNTRUSTED")
            fcntl.flock(fence_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
            self._lock_owner_pid = os.getpid()
            self._lock_owner_thread = threading.get_ident()
            yield self
        finally:
            self._locked = False
            self._lock_owner_pid = None
            self._lock_owner_thread = None
            if fence_fd is not None:
                os.close(fence_fd)
            os.close(fd)

    def current_facts(self) -> dict:
        self._require_locked()
        return read_live_z2_facts(release=self.release)

    def runtime_program_facts(self) -> dict:
        """Read-only program admission, never FPGA reconfiguration authority."""
        self._require_locked()
        return read_live_z2_facts(
            release=self.release, runtime_program_session=True)

    def image_sha256(self, which: str) -> str:
        self._require_locked()
        need(which in ("candidate", "recovery"), "IMAGE_NAME_DENIED")
        filename = (self.release.firmware_name if which == "candidate"
                    else self.release.recovery_name)
        expected = (self.release.firmware_sha256 if which == "candidate"
                    else self.release.recovery_sha256)
        return sha_file(FIRMWARE / filename, expected)
