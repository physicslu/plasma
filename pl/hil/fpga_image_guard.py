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
import time

SYS = Path("/sys")
PROC = Path("/proc")
FIRMWARE = Path("/lib/firmware")
# Device Golden recovery Image: the PYNQ-Z2 factory PL ``base.bin`` that every
# protected Restore returns to. Pinned in this protected privileged tree and
# NEVER taken from an Image Manifest, Bundle or request: a user-supplied
# Manifest cannot redefine what "recovery" means. Changing it requires a
# reviewed privileged-source update (Root code Manifest re-provisioning).
GOLDEN_RECOVERY_NAME = "base.bin"
GOLDEN_RECOVERY_SHA256 = "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c"
# Retain the historic on-disk lock path so legacy SWD04 and this generic
# executor cannot both own/configure the same FPGA at once.
OWNER_DIR = Path("/run/plasma-z2-swd05")
GLOBAL_LOCK = OWNER_DIR / "supervisor.lock"
# Additional additive fence: each SWD Site holds LOCK_SH, Root reload LOCK_EX.
# Root Guard source-pin, provenance and supervisor.lock remain authoritative.
PPU_RELOAD_FENCE = Path("/run/lock/plasma-mmio.lock")
# Bounded wait when a Site admission overlaps Root configuration/reload.
SITE_ADMISSION_SUPERVISOR_WAIT_S = 30.0
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


def run_child(args: list[str], *, reload_fence_fd: int | None = None) -> None:
    """Bound the MMIO subprocess and do not reload PL with an unreaped child."""
    child_env = os.environ.copy()
    child_env.pop("PLASMA_ROOT_RELOAD_FENCE_FD", None)
    passed_fds: tuple[int, ...] = ()
    if reload_fence_fd is not None:
        need(type(reload_fence_fd) is int and reload_fence_fd >= 3,
             "INVALID_ROOT_RELOAD_FENCE_FD")
        child_env["PLASMA_ROOT_RELOAD_FENCE_FD"] = str(reload_fence_fd)
        passed_fds = (reload_fence_fd,)
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True, env=child_env,
                            pass_fds=passed_fds)
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


# Site admission image digest cache (U12). Lives in the root-only tmpfs owner
# directory, so a reboot empties it; the boot ID is also part of every entry.
IMAGE_SHA_CACHE = OWNER_DIR / "image-sha-cache.json"
IMAGE_SHA_CACHE_MAX_BYTES = 65536
# An entry is written only when the file's last change is older than this, so
# a write landing in the same coarse timestamp tick cannot keep an old stat.
IMAGE_SHA_CACHE_SETTLE_NS = 2_000_000_000
_STAT_KEYS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def _stat_identity(info: os.stat_result) -> list[int]:
    return [int(getattr(info, key)) for key in _STAT_KEYS]


def _read_image_sha_cache(path: Path) -> dict:
    """Best-effort read; anything unexpected means "no cache", never a denial.

    The owner must be the caller (root in production: the Root Guard runs as
    euid 0) and the file must not be readable or writable by anyone else.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return {}
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_mode & 0o077 or info.st_size > IMAGE_SHA_CACHE_MAX_BYTES):
            return {}
        data = json.loads(os.read(fd, IMAGE_SHA_CACHE_MAX_BYTES + 1))
    except (OSError, ValueError):
        return {}
    finally:
        os.close(fd)
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, dict) else {}


def _write_image_sha_cache(path: Path, entries: dict) -> None:
    """Atomic root-only replace; a failure only costs the next full hash."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, json.dumps({"version": 1, "entries": entries},
                                    sort_keys=True).encode())
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def sha_file_cached(path: Path, expected: str, *, boot_id: str) -> tuple[str, str]:
    """``sha_file`` for Site admission, reusing a proven digest.

    Returns ``(digest, "CACHE" | "FULL")``. A cached digest is reused only
    when the protected file's device, inode, size, mtime and ctime and the
    boot ID equal those recorded when the same bytes were fully hashed and
    matched ``expected``. Any replacement or rewrite of the file changes its
    ctime, which userspace cannot set. A miss, an unreadable cache or a file
    changed while being hashed falls back to (or stays) the full hash; the
    cache can never turn a mismatch into a match. FPGA Manager load, test and
    restore keep ``sha_file`` without the cache.
    """
    need(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
         "PINNED_IMAGE_HASH_DENIED")
    protected(path)
    need(path.parent == FIRMWARE and path.is_file() and
         0 < path.stat().st_size <= 16_000_000, "FIRMWARE_LOCATION_DENIED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        identity = _stat_identity(before)
        entries = _read_image_sha_cache(IMAGE_SHA_CACHE)
        entry = entries.get(path.name)
        if (isinstance(entry, dict) and entry.get("boot_id") == boot_id and
                entry.get("stat") == identity and entry.get("sha256") == expected):
            return expected, "CACHE"
        digest = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    need(digest.hexdigest() == expected, "FIRMWARE_BYTES_CHANGED")
    if (_stat_identity(after) == identity and
            time.time_ns() - before.st_ctime_ns > IMAGE_SHA_CACHE_SETTLE_NS):
        entries = {name: value for name, value in entries.items()
                   if name != path.name and isinstance(value, dict)}
        entries[path.name] = {"boot_id": boot_id, "stat": identity, "sha256": expected}
        _write_image_sha_cache(IMAGE_SHA_CACHE, entries)
    return expected, "FULL"


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


def site_lock_path(site: int) -> Path:
    """The native ``plasma_swd`` per-Site EX lock (``<fence>.site-N``)."""
    need(site in (1, 2), "SITE_INVALID")
    return PPU_RELOAD_FENCE.with_name(f"{PPU_RELOAD_FENCE.name}.site-{site}")


def site_admission_records() -> set[int]:
    """Sites holding an un-revoked Root admission record (any state)."""
    return {site for site in (1, 2)
            if os.path.lexists(OWNER_DIR / f"swd-site{site}-admission")}


def _site_record(site: int) -> dict | None:
    """A root-private ``key=value`` admission record, or None if unusable."""
    path = OWNER_DIR / f"swd-site{site}-admission"
    try:
        info = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_mode & 0o077 or info.st_size > 8192):
            return None
        fields = dict(line.split("=", 1)
                      for line in path.read_text().splitlines() if "=" in line)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return fields


def _proc_flocks(procroot: Path) -> dict[tuple[int, int], set[tuple[str, str]]]:
    """Granted FLOCKs from /proc/locks: (dev, inode) -> {(pid, READ|WRITE)}."""
    held: dict[tuple[int, int], set[tuple[str, str]]] = {}
    for line in (procroot / "locks").read_text().splitlines():
        fields = line.split()
        # "<n>: FLOCK ADVISORY WRITE <pid> <maj>:<min>:<ino> 0 EOF";
        # blocked waiters carry "->" and are not holders.
        if len(fields) < 6 or fields[1] != "FLOCK" or "->" in fields:
            continue
        major, minor, inode = fields[5].split(":")
        key = (os.makedev(int(major, 16), int(minor, 16)), int(inode))
        held.setdefault(key, set()).add((fields[4], fields[3]))
    return held


def site_page(release, site: int) -> tuple[int, int]:
    need(release.site_bitmap == 3 and release.axi_bytes == 0x2000 and
         site in (1, 2), "SITE_PAGE_DENIED")
    base = release.axi_base + (site - 1) * 0x1000
    return base, base + 0x1000


def cooperating_site_owners(*, release, admitting_site: int, boot_id: str,
                            session_id: str, procroot: Path = PROC,
                            now: float | None = None) -> dict[str, int]:
    """PIDs proven to be the *other* Site's admitted native owner.

    A PID qualifies only when ALL hold: the other Site has a root-private
    admission record of this boot and this Root IMAGE session that has not
    expired; /proc/locks shows that PID as the single WRITE holder of that
    Site's lock and a READ holder of the PPU fence. Process names are never
    used. Anything else yields no exemption, so the census stays fail-closed.
    """
    need(admitting_site in (1, 2), "SITE_INVALID")
    now = time.time() if now is None else now
    held = _proc_flocks(procroot)

    def key(path: Path) -> tuple[int, int] | None:
        try:
            info = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            return None
        return (info.st_dev, info.st_ino)

    fence = key(PPU_RELOAD_FENCE)
    owners: dict[str, int] = {}
    for other in (1, 2):
        if other == admitting_site:
            continue
        record = _site_record(other)
        try:
            valid = (record is not None and record.get("site_id") == str(other) and
                     record.get("boot_id") == boot_id and
                     record.get("root_image_session_id") == session_id and
                     int(record.get("record_expires_epoch", "0")) > now)
        except ValueError:
            valid = False
        lock = key(site_lock_path(other))
        if not valid or lock is None or fence is None:
            continue
        writers = [pid for pid, mode in held.get(lock, ()) if mode == "WRITE"]
        if len(writers) == 1 and (writers[0], "READ") in held.get(fence, ()):
            owners[writers[0]] = other
    return owners


#: Site admission only (2-Site HIL 2026-11-19): a PID proven to have exited
#: during the census held nothing any more and is skipped. FPGA Manager
#: download/test/restore keep the strict bounded full rescan ("rescan").
VANISHED_PID_POLICIES = ("rescan", "skip")


def _pid_start_time(item: Path) -> str | None:
    """Kernel start time of the process now at this PID (``stat`` field 22).

    A different value before and after reading a PID's fds and VMAs means
    the PID was reused by another process mid-read. Raises FileNotFoundError
    when the PID is gone; ``None`` only for a fixture without ``stat`` (a real
    procfs always has it for a live PID).
    """
    try:
        raw = (item / "stat").read_text()
    except FileNotFoundError:
        item.stat()  # FileNotFoundError here: the PID itself is gone
        return None
    fields = raw.rsplit(")", 1)[-1].split()
    need(len(fields) >= 20 and fields[19].isdecimal(), "MALFORMED_PROC_STAT")
    return fields[19]


_HARD_DEVICES = {"/dev/xdevcfg": "XDEVCFG", "/dev/fpga0": "FPGA0"}


def _read_pid(item: Path, where: list[str], prefix: str = "") -> tuple[str | None, list[str], str]:
    """One self-consistent read of a PID: (start time, fd targets, VMAs).

    ``where[0]`` names the phase being read for the denial diagnostic.
    """
    for look in (1, 2):
        where[0] = prefix + "STAT"
        born = _pid_start_time(item)
        where[0] = prefix + "FD"
        targets = []
        for fd in (item / "fd").iterdir():
            try:
                targets.append(os.readlink(fd))
            except FileNotFoundError:
                # A closed file descriptor is no longer an owner;
                # the subsequent full process VMA check is mandatory.
                continue
        where[0] = prefix + "MAPS"
        maps = (item / "maps").read_text()
        where[0] = prefix + "STAT"
        if _pid_start_time(item) == born:
            return born, targets, maps
        # Another process took this PID mid-read: the evidence
        # mixes two processes. Read the new one once more.
        need(look == 1, "PID_REUSED_DURING_SCAN")
    raise AssertionError("unreachable bounded PID read")


def _holdings(targets: list[str], maps: str, release):
    """(hard device class and stage | None, holds /dev/mem fd, owner-window /dev/mem VMAs)."""
    hard = None
    devmem_fd = False
    devmem_maps: list[tuple[int, int]] = []
    for target in targets:
        need(bool(target) and target != "UNKNOWN", "INCOMPLETE_FD_OBSERVATION")
        name = target.split(" (deleted)")[0]
        if target.startswith("/dev/uio") or name in _HARD_DEVICES:
            hard = hard or (_HARD_DEVICES.get(name, "UIO"), "FD")
        elif name == "/dev/mem":
            devmem_fd = True
    for line in maps.splitlines():
        fields = line.split()
        need(len(fields) >= 5, "MALFORMED_PROC_VMA")
        if len(fields) < 6:
            continue
        device = fields[5]
        if device.startswith("/dev/uio") or device in _HARD_DEVICES:
            hard = hard or (_HARD_DEVICES.get(device, "UIO"), "MAPS")
        elif device == "/dev/mem":
            lo, hi = (int(x, 16) for x in fields[0].split("-"))
            offset = int(fields[2], 16)
            if overlaps(offset, hi - lo, release.owner_base, release.owner_bytes):
                devmem_maps.append((offset, hi - lo))
    return hard, devmem_fd, devmem_maps


def _devmem_unproven(pid: str, devmem_maps, owners: dict, release) -> tuple[str, str] | None:
    """None when ``pid`` is a proven other-Site owner mapping only its page."""
    if pid not in owners:
        return "OWNER_UNPROVEN", "LOCK"
    low, high = site_page(release, owners[pid])
    if not all(low <= offset and offset + size <= high for offset, size in devmem_maps):
        return "MAPPING_OUTSIDE_SITE_PAGE", "MAPS"
    return None


def _exit_confirmed(item: Path, exc: BaseException) -> bool:
    """Did reading this PID fail because the process is gone?

    procfs reports a vanished task in two ways: ENOENT (``FileNotFoundError``)
    when the entry is already unlinked, and ESRCH (``ProcessLookupError``)
    when the task was reaped between opening one of its files and reading it
    (2-Site HIL 2026-11-23: ``MAPS:ProcessLookupError``). Either error is only
    a hint. The exit is confirmed solely by a fresh ``stat`` of the PID entry
    raising ENOENT. A present entry (live, zombie, or the PID already reused
    by another process), any other stat error, and every other read error
    (EACCES, malformed data, ...) are NOT an exit: the census fails closed.
    """
    if not isinstance(exc, (FileNotFoundError, ProcessLookupError)):
        return False
    try:
        item.stat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def scan_proc_consumers(*, procroot: Path, release,
                        diagnostic: dict | None = None,
                        cooperating=None,
                        vanished_pids: str = "rescan",
                        ) -> tuple[bool, list[str]]:
    """Fail-closed /proc owner census.

    ``vanished_pids="rescan"`` (default; FPGA Manager download/test/restore):
    a vanished process invalidates that snapshot, so the *whole* read-only
    census restarts, at most three times. ``"skip"`` (Site admission only): a
    PID whose exit is CONFIRMED (its /proc entry is gone) holds no device and
    no mapping any more, so it is counted and skipped without a rescan; under
    concurrent Sites the peer's short-lived processes would otherwise exhaust
    the bounded rescans. Neither policy relaxes anything else: enumeration
    failure, a live but unreadable PID, malformed data and every conflict
    still fail closed. A PID reused by another process while it is read is
    re-examined once and refused if it changes again.

    ``cooperating`` (Site admission only) is a callable returning the PIDs
    proven by ``cooperating_site_owners`` right now. It is evaluated AFTER a
    PID's fds and VMAs were read, so an owner that attached during the scan
    is proven at observation. Such a PID may hold ``/dev/mem`` and map
    exactly inside its own Site page, nothing else.

    The proof is necessarily taken a little later than the fd/VMA read, and
    the native owner closes ``/dev/mem`` *before* dropping its locks; an owner
    exiting in that gap is seen holding ``/dev/mem`` but is no longer provable
    (2-Site HIL 2026-11-20, Site 1 Cycle 98). So, with ``cooperating`` only,
    an unproven ``/dev/mem`` holder is read ONCE more (same start time, fds,
    VMAs) and judged on that fresh read: exited or no longer holding
    ``/dev/mem`` -> no conflict; still holding -> proven again or a conflict;
    a reused PID, a missing start time or an unreadable live PID fails closed.
    Hard devices (``/dev/uio*``, ``xdevcfg``, ``fpga0``) are never revalidated.
    A conflict is described in ``diagnostic["conflict"]`` with numeric PID,
    start time and fixed tokens only, never command lines or environment.
    """
    need(vanished_pids in VANISHED_PID_POLICIES, "INVALID_VANISHED_PID_POLICY")
    for attempt in range(1, 4):
        conflicts, observed, skipped = [], 0, 0
        detail: dict | None = None
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
            where = ["STAT"]
            try:
                born, targets, maps = _read_pid(item, where)
                observed += 1
                hard, devmem_fd, devmem_maps = _holdings(targets, maps, release)
                revalidation = "NOT_RUN"
                if hard:
                    device, (reason, stage) = hard[0], ("HARD_DEVICE", hard[1])
                elif devmem_fd or devmem_maps:
                    device = "DEVMEM"
                    owners = cooperating() if cooperating is not None else {}
                    unproven = _devmem_unproven(item.name, devmem_maps, owners, release)
                    if unproven is not None and cooperating is not None:
                        # Bounded fresh revalidation of THIS PID, once. An
                        # exit (ENOENT/ESRCH) is confirmed below.
                        again, targets, maps = _read_pid(item, where, "REVALIDATE_")
                        need(born is not None, "PID_START_TIME_UNAVAILABLE")
                        need(again == born, "PID_REUSED_DURING_SCAN")
                        hard, devmem_fd, devmem_maps = _holdings(targets, maps, release)
                        revalidation = "STILL_HELD"
                        if hard:
                            device, unproven = hard[0], ("HARD_DEVICE", hard[1])
                        elif devmem_fd or devmem_maps:
                            unproven = _devmem_unproven(
                                item.name, devmem_maps, cooperating(), release)
                        else:
                            unproven = None  # closed and unmapped: holds nothing
                    if unproven is None:
                        continue
                    reason, stage = unproven
                else:
                    continue
                conflicts.append(item.name)
                if detail is None:
                    detail = {"pid": item.name, "start_time": born or "UNKNOWN",
                              "device": device, "reason": reason, "stage": stage,
                              "revalidation": revalidation}
            except (FileNotFoundError, PermissionError, OSError, ValueError) as exc:
                # An inaccessible PID is NOT a confirmed exit and must never
                # be skipped or rescanned; see _exit_confirmed.
                vanished = _exit_confirmed(item, exc)
                if vanished and (vanished_pids == "skip" or
                                 where[0].startswith("REVALIDATE_")):
                    # Exited: it holds no fd and no mapping any more. Any
                    # conflict already found still refuses at the end.
                    skipped += 1
                    continue
                # Never retry a known conflict even if another process vanished.
                if vanished and not conflicts and attempt < 3:
                    retry_pid = item.name
                    break
                reused = isinstance(exc, TargetSafetyDenied) and str(exc) == "PID_REUSED_DURING_SCAN"
                if diagnostic is not None:
                    diagnostic.update(
                        status=("PROC_CONFLICT_AND_INCOMPLETE" if conflicts else
                                "PID_REUSED_DURING_SCAN" if reused else
                                "VANISHED_PID_RESCAN_EXHAUSTED" if vanished else
                                "PROC_VISIBILITY_DENIED"),
                        pid=item.name, phase=where[0],
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
                conflicts=len(set(conflicts)), rescans=attempt - 1,
                vanished_skipped=skipped)
            if detail is not None:
                diagnostic["conflict"] = detail
        return observed > 0, sorted(set(conflicts))
    raise AssertionError("unreachable bounded process scan")


def read_live_z2_facts(*, release, runtime_program_session: bool = False,
                       cooperating=None, timing_ms: dict[str, float] | None = None,
                       vanished_pids: str = "rescan",
                       image_hash_cache: bool = False) -> dict:
    """Keep kernel/image guards; runtime WordPort does not census all PIDs.

    Runtime call requires the same protected FPGA lock and is NOT a safe
    alternative for FPGA Manager load, test or restoration admission.
    """
    need(type(runtime_program_session) is bool, "INVALID_PROCESS_SCAN_POLICY")
    need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
    candidate = FIRMWARE / release.firmware_name
    recovery = FIRMWARE / GOLDEN_RECOVERY_NAME
    need(candidate != recovery and candidate.parent == FIRMWARE and
         recovery.parent == FIRMWARE, "UNREVIEWED_FIRMWARE_PATH")
    boot_before = (PROC / "sys/kernel/random/boot_id").read_text().strip()
    need(bool(boot_before), "BOOT_ID_UNAVAILABLE")
    hash_start_ns = time.monotonic_ns()
    need(type(image_hash_cache) is bool, "INVALID_IMAGE_HASH_POLICY")
    if image_hash_cache:
        candidate_sha, candidate_source = sha_file_cached(
            candidate, release.firmware_sha256, boot_id=boot_before)
        recovery_sha, recovery_source = sha_file_cached(
            recovery, GOLDEN_RECOVERY_SHA256, boot_id=boot_before)
    else:
        candidate_sha = sha_file(candidate, release.firmware_sha256)
        recovery_sha = sha_file(recovery, GOLDEN_RECOVERY_SHA256)
        candidate_source = recovery_source = "FULL"
    if timing_ms is not None:
        timing_ms["image_hash"] = round((time.monotonic_ns() - hash_start_ns) / 1e6, 3)
    kernel_start_ns = time.monotonic_ns()
    compatible = (PROC / "device-tree/compatible").read_bytes().split(b"\0")
    need(release.soc_compatible.encode("ascii") in compatible,
         "SOC_FAMILY_MISMATCH")
    manager = (SYS / "class/fpga_manager/fpga0/state").read_text().strip()
    uio, platform = scan_kernel_owners(sysroot=SYS, release=release)
    if timing_ms is not None:
        timing_ms["kernel_owners"] = round((time.monotonic_ns() - kernel_start_ns) / 1e6, 3)
    proc_start_ns = time.monotonic_ns()
    if runtime_program_session:
        # The session holds the global configuration lock. External device
        # consumers remain checked by the engine's scoped fuser preflight.
        # Do NOT fabricate proc_complete=True or a zero-conflict census.
        complete, conflicts = None, None
        proc_diagnostic = {"status": "NOT_RUN_PROGRAM_SESSION"}
    else:
        proc_diagnostic = {}
        complete, conflicts = scan_proc_consumers(
            procroot=PROC, release=release, diagnostic=proc_diagnostic,
            cooperating=cooperating, vanished_pids=vanished_pids)
    if timing_ms is not None:
        timing_ms["process_census"] = round((time.monotonic_ns() - proc_start_ns) / 1e6, 3)
    boot_after = (PROC / "sys/kernel/random/boot_id").read_text().strip()
    need(boot_before == boot_after, "BOOT_CHANGED_DURING_SCAN")
    return {
        "root": True, "boot_id": boot_before, "manager_state": manager,
        "recovery_sha256": recovery_sha, "candidate_sha256": candidate_sha,
        "uio_overlaps": uio, "platform_overlaps": platform,
        "proc_complete": complete, "proc_conflicts": conflicts,
        "proc_scan_diagnostic": proc_diagnostic,
        "image_hash_source": {"candidate": candidate_source,
                              "recovery": recovery_source},
        "observation_kind": "LIVE_ROOT_READ_ONLY",
        "axi_isolation_evidence": "UNPROVEN",
        "active_image_attestation": "UNPROVEN",
    }


class RootZ2TargetPort:
    """Same exclusive global FPGA owner, bound to one source-authorized release."""
    def __init__(self, *, release):
        self.release = release
        self.admission_timing_ms: dict[str, float] = {}
        self._locked = False
        self._lock_owner_pid = None
        self._lock_owner_thread = None
        self._reload_fence_fd: int | None = None
        self._site: int | None = None
        self._site_session: tuple[str, str] | None = None

    def _require_locked(self) -> None:
        need(self._locked and self._lock_owner_pid == os.getpid() and
             self._lock_owner_thread == threading.get_ident(),
             "FPGA_OWNER_LOCK_REQUIRED")

    @contextmanager
    def exclusive(self, *, site: int | None = None):
        """Root owner. ``site=None``: PPU reload, fence EX (unchanged).

        ``site=1|2`` (ADR-0007 Site admission only): supervisor SH
        permits independent admissions while excluding Root configuration EX;
        the PPU fence SH, so another Site's running OpenOCD (also SH) stays
        compatible while any reload (EX) is excluded; and this Site's lock
        EX for the admission itself. A Site admission record is the
        admission-to-attach reservation: a second admission of the same Site
        and every reload are refused while any record exists.
        """
        need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
        need(not self._locked, "REENTRANT_TARGET_LOCK_DENIED")
        need(site in (None, 1, 2), "SITE_INVALID")
        OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
        protected(GLOBAL_LOCK.parent, file=False)
        fd = os.open(GLOBAL_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fence_fd = site_fd = None
        try:
            st = os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and
                 st.st_nlink == 1 and st.st_mode & 0o077 == 0,
                 "GLOBAL_FPGA_LOCK_UNTRUSTED")
            if site is None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                deadline = time.monotonic() + SITE_ADMISSION_SUPERVISOR_WAIT_S
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        need(time.monotonic() < deadline, "ROOT_SUPERVISOR_BUSY")
                        time.sleep(0.05)
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
            if site is None:
                fcntl.flock(fence_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # No reload between a Site admission and its OpenOCD attach.
                need(not site_admission_records(), "SITE_ADMISSION_RECORD_PRESENT")
            else:
                try:
                    fcntl.flock(fence_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    need(False, "PPU_RELOAD_IN_PROGRESS")
                site_fd = os.open(site_lock_path(site),
                                  os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                st = os.fstat(site_fd)
                need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                     st.st_mode & 0o002 == 0, "SITE_LOCK_UNTRUSTED")
                try:
                    fcntl.flock(site_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    need(False, "SITE_OWNER_PRESENT")
                need(site not in site_admission_records(),
                     "SITE_ADMISSION_RECORD_PRESENT")
            self._locked = True
            self._lock_owner_pid = os.getpid()
            self._lock_owner_thread = threading.get_ident()
            self._reload_fence_fd = fence_fd if site is None else None
            self._site = site
            yield self
        finally:
            self._locked = False
            self._lock_owner_pid = None
            self._lock_owner_thread = None
            self._reload_fence_fd = None
            self._site = None
            self._site_session = None
            if site_fd is not None:
                os.close(site_fd)
            if fence_fd is not None:
                os.close(fence_fd)
            os.close(fd)

    def bind_site_session(self, *, boot_id: str, session_id: str) -> None:
        """Pin the Root IMAGE session a cooperating Site record must match."""
        self._require_locked()
        need(self._site is not None and type(boot_id) is str and boot_id and
             type(session_id) is str and session_id, "SITE_SESSION_BINDING_INVALID")
        self._site_session = (boot_id, session_id)

    def inherited_reload_fence(self) -> int:
        """Return the held Root flock FD only to a bounded identity child."""
        self._require_locked()
        need(self._reload_fence_fd is not None,
             "ROOT_RELOAD_FENCE_NOT_HELD")
        return self._reload_fence_fd

    def current_facts(self) -> dict:
        self._require_locked()
        cooperating = None
        if self._site is not None:
            # Unbound Site admission exempts nothing (fail-closed).
            if self._site_session is not None:
                site, (boot_id, session_id) = self._site, self._site_session
                cooperating = lambda: cooperating_site_owners(  # noqa: E731 (evaluated per PID)
                    release=self.release, admitting_site=site,
                    boot_id=boot_id, session_id=session_id)
            else:
                cooperating = dict  # unbound Site admission exempts nothing
        # Only Site admission skips a confirmed-exited PID; the Root
        # reload/test/restore owner (site None) keeps the strict rescan.
        return read_live_z2_facts(
            release=self.release, cooperating=cooperating,
            timing_ms=self.admission_timing_ms if self._site is not None else None,
            vanished_pids="skip" if self._site is not None else "rescan",
            # Only Site admission reuses a proven image digest (U12).
            image_hash_cache=self._site is not None)

    def runtime_program_facts(self) -> dict:
        """Read-only program admission, never FPGA reconfiguration authority."""
        self._require_locked()
        return read_live_z2_facts(
            release=self.release, runtime_program_session=True)

    def image_sha256(self, which: str) -> str:
        self._require_locked()
        need(which in ("candidate", "recovery"), "IMAGE_NAME_DENIED")
        filename = (self.release.firmware_name if which == "candidate"
                    else GOLDEN_RECOVERY_NAME)
        expected = (self.release.firmware_sha256 if which == "candidate"
                    else GOLDEN_RECOVERY_SHA256)
        return sha_file(FIRMWARE / filename, expected)
