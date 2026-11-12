#!/usr/bin/env python3
"""Explicit one-time provisioning of root-owned FPGA action source.

No FPGA, Runtime, service or DUT operation. A migration/install task must
be separately approved and its Z2 results recorded; factory refresh does NOT
silently activate this new privileged source or remove old recovery files.
"""
from __future__ import annotations
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

FACTORY_ROOT = Path("/opt/plasma/bootstrap")
DESTINATION = Path("/opt/plasma/privileged/fpga-root")
JOURNAL = Path("/var/lib/plasma-privileged/fpga-deployment-state.json")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
FPGA_MANAGER = Path("/sys/class/fpga_manager/fpga0/state")
ADMISSIONS = Path("/run/plasma-z2-swd05")
GLOBAL_LOCK = ADMISSIONS / "supervisor.lock"
RELOAD_FENCE = Path("/run/lock/plasma-mmio.lock")
SERVICES = ("plasma-server.service", "plasma-site-worker.service",
            "plasma-bootstrap.service", "plasma-package-control.service")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


class ProvisionDenied(RuntimeError):
    pass


def _verifier(factory_root: Path):
    src = factory_root / "ppu_privileged_source.py"
    spec = importlib.util.spec_from_file_location("plasma_qualified_fpga_code", src)
    if spec is None or spec.loader is None:
        raise ProvisionDenied("PRIVILEGED_VERIFIER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trusted(path: Path, uid: int, *, folder: bool) -> None:
    info = path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if folder else stat.S_ISREG(info.st_mode))
            or info.st_uid != uid or info.st_mode & 0o022):
        raise ProvisionDenied("PRIVILEGED_PROVISION_SOURCE_UNTRUSTED")


def provision(
    factory_root: Path = FACTORY_ROOT,
    destination: Path = DESTINATION,
    *,
    _test_uid: int | None = None,
) -> dict:
    # Test-only UID override cannot be supplied through the CLI.
    uid = 0 if _test_uid is None else _test_uid
    if os.geteuid() != uid:
        raise ProvisionDenied("PRIVILEGED_PROVISION_ROOT_REQUIRED")
    if not factory_root.is_absolute() or not destination.is_absolute():
        raise ProvisionDenied("PRIVILEGED_PROVISION_PATH_INVALID")
    _trusted(factory_root, uid, folder=True)
    _trusted(factory_root / "ppu_privileged_source.py", uid, folder=False)
    verifier = _verifier(factory_root)
    if destination.exists() or destination.is_symlink():
        raise ProvisionDenied("PRIVILEGED_PROVISION_ALREADY_INSTALLED")
    parent = destination.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _trusted(parent, uid, folder=True)
    stage = parent / (".fpga-root-provision-%d" % os.getpid())
    if stage.exists() or stage.is_symlink():
        raise ProvisionDenied("PRIVILEGED_PROVISION_STAGE_COLLISION")
    stage.mkdir(mode=0o700)
    try:
        inventory = {}
        for rel in sorted(verifier.CODE_FILES):
            original = factory_root / rel
            if any((factory_root / Path(*Path(rel).parts[:i])).is_symlink()
                   for i in range(1, len(Path(rel).parts) + 1)):
                raise ProvisionDenied("PRIVILEGED_PROVISION_SYMLINK_DENIED")
            _trusted(original, uid, folder=False)
            target = stage / rel
            directory = stage
            for part in Path(rel).parts[:-1]:
                directory /= part
                directory.mkdir(mode=0o700, exist_ok=True)
            shutil.copyfile(original, target)
            target.chmod(0o644)
            inventory[rel] = hashlib.sha256(target.read_bytes()).hexdigest()
        (stage / verifier.MANIFEST).write_text(json.dumps({
            "schema": verifier.SCHEMA, "files": inventory,
        }, sort_keys=True) + "\n", encoding="utf-8")
        (stage / verifier.MANIFEST).chmod(0o600)
        # Verify the staged closure before atomic publication. Ancestors of
        # the new root are qualified by the root-only CLI at live execution.
        verifier.verify_source(stage, expected_uid=uid)
        os.rename(stage, destination)  # No replacement of an existing tree.
        return {"result": "PROVISIONED_NOT_EXECUTED",
                "source_root": str(destination),
                "code_files": len(inventory), "fpga_loaded": False}
    finally:
        if stage.exists():
            shutil.rmtree(stage)



def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ProvisionDenied(code)


def _quiescent() -> None:
    """Maintenance is offline: no Runtime, Bootstrap, Worker or OpenOCD."""
    for unit in SERVICES:
        try:
            r = subprocess.run(
                ["/bin/systemctl", "show", "--no-pager",
                 "--property=LoadState,ActiveState,SubState", unit],
                text=True, capture_output=True, timeout=8)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProvisionDenied("PRIVILEGED_UPGRADE_SERVICE_UNVERIFIED") from exc
        fields = dict(line.split("=", 1) for line in r.stdout.splitlines()
                      if "=" in line)
        _need(r.returncode == 0 and fields.get("LoadState") == "loaded"
              and fields.get("ActiveState") == "inactive"
              and fields.get("SubState") == "dead",
              "PRIVILEGED_UPGRADE_SERVICE_NOT_QUIESCENT")
    try:
        running = subprocess.run(["/usr/bin/pgrep", "-x", "openocd"],
                                 capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProvisionDenied("PRIVILEGED_UPGRADE_OPENOCD_UNVERIFIED") from exc
    _need(running.returncode == 1, "PRIVILEGED_UPGRADE_OPENOCD_PRESENT")
    _need(ADMISSIONS.is_dir() and not ADMISSIONS.is_symlink()
          and not list(ADMISSIONS.glob("swd-site*-admission")),
          "PRIVILEGED_UPGRADE_ADMISSION_OWNER_PRESENT")


def _held_image_fingerprint(uid: int) -> str:
    """Only read the protected journal and current Boot/Manager state."""
    _trusted(JOURNAL.parent, uid, folder=True)
    s = JOURNAL.lstat()
    _need(stat.S_ISREG(s.st_mode) and s.st_uid == uid and
          stat.S_IMODE(s.st_mode) == 0o600 and 0 < s.st_size <= 4096,
          "PRIVILEGED_UPGRADE_JOURNAL_UNTRUSTED")
    raw = JOURNAL.read_bytes()
    try:
        state = json.loads(raw)
        boot = BOOT_ID.read_text().strip()
        manager = FPGA_MANAGER.read_text().strip()
    except (OSError, ValueError) as exc:
        raise ProvisionDenied("PRIVILEGED_UPGRADE_IMAGE_UNVERIFIED") from exc
    _need(type(state) is dict and state.get("status") == "IMAGE" and
          state.get("boot_id") == boot and len(boot) >= 8 and
          manager == "operating",
          "PRIVILEGED_UPGRADE_IMAGE_UNVERIFIED")
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def _maintenance_locks(uid: int):
    """Same Root global→reload-fence ordering; refuse active owners."""
    _trusted(GLOBAL_LOCK.parent, uid, folder=True)
    handles = []
    try:
        for path, strict_owner in ((GLOBAL_LOCK, True), (RELOAD_FENCE, False)):
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            handles.append(fd)
            st = os.fstat(fd)
            _need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                  (not strict_owner or st.st_uid == uid) and
                  st.st_mode & 0o002 == 0 and
                  (not strict_owner or st.st_mode & 0o077 == 0),
                  "PRIVILEGED_UPGRADE_LOCK_UNTRUSTED")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ProvisionDenied("PRIVILEGED_UPGRADE_OWNER_BUSY") from exc
        yield
    finally:
        for fd in reversed(handles):
            os.close(fd)


def _sync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def upgrade(factory_root: Path = FACTORY_ROOT,
            destination: Path = DESTINATION, *,
            expected_current_manifest_sha256: str,
            _test_uid: int | None = None) -> dict:
    """Offline Root code replacement with immutable backup and explicit CAS.

    No systemctl mutations, FPGA writes, journal writes or service restarts.
    If interrupted after old→backup and before new→current, use rollback().
    """
    uid = 0 if _test_uid is None else _test_uid
    _need(os.geteuid() == uid, "PRIVILEGED_UPGRADE_ROOT_REQUIRED")
    _need(type(expected_current_manifest_sha256) is str and
          SHA64.fullmatch(expected_current_manifest_sha256) is not None,
          "PRIVILEGED_UPGRADE_EXPECTED_SHA_INVALID")
    _need(factory_root.is_absolute() and destination.is_absolute(),
          "PRIVILEGED_UPGRADE_PATH_INVALID")
    _trusted(factory_root, uid, folder=True)
    _trusted(factory_root / "ppu_privileged_source.py", uid, folder=False)
    _trusted(destination.parent, uid, folder=True)
    verifier = _verifier(factory_root)
    backup = destination.with_name(destination.name + ".previous")
    staged = destination.with_name(destination.name + ".next")
    _quiescent()
    with _maintenance_locks(uid):
        _quiescent()
        before = _held_image_fingerprint(uid)
        _need(not backup.exists() and not backup.is_symlink() and
              not staged.exists() and not staged.is_symlink(),
              "PRIVILEGED_UPGRADE_PENDING_RECOVERY")
        current = verifier.verify_source(destination, expected_uid=uid)
        _need(current["code_manifest_sha256"] == expected_current_manifest_sha256,
              "PRIVILEGED_UPGRADE_STALE_SOURCE")
        try:
            provision(factory_root, staged, _test_uid=uid)
            candidate = verifier.verify_source(staged, expected_uid=uid)
            _need(candidate["code_manifest_sha256"] != expected_current_manifest_sha256,
                  "PRIVILEGED_UPGRADE_NO_CHANGE")
        except Exception:
            # Nothing was activated: remove only the stage created by this
            # maintenance attempt. Preserve current verified Root unchanged.
            if staged.is_dir() and not staged.is_symlink():
                shutil.rmtree(staged)
            raise
        try:
            os.rename(destination, backup)
            _sync_dir(destination.parent)
            os.rename(staged, destination)
            _sync_dir(destination.parent)
            installed = verifier.verify_source(destination, expected_uid=uid)
            _need(installed["code_manifest_sha256"] == candidate["code_manifest_sha256"]
                  and _held_image_fingerprint(uid) == before,
                  "PRIVILEGED_UPGRADE_POSTVERIFY_FAILED")
        except Exception:
            # Best-effort restoration under the same exclusive locks.
            # A restoration failure is a stop condition, never a PASS.
            if backup.exists():
                if destination.exists() and not staged.exists():
                    os.rename(destination, staged)
                if not destination.exists():
                    os.rename(backup, destination)
                _sync_dir(destination.parent)
            raise
        return {"result": "UPGRADED_NOT_EXECUTED",
                "previous_manifest_sha256": expected_current_manifest_sha256,
                "current_manifest_sha256": candidate["code_manifest_sha256"],
                "backup": str(backup), "journal_sha256": before,
                "fpga_reloaded": False, "service_restarted": False,
                "dut": "NOT_RUN"}


def rollback(factory_root: Path = FACTORY_ROOT,
             destination: Path = DESTINATION, *,
             expected_backup_manifest_sha256: str,
             _test_uid: int | None = None) -> dict:
    """Operator-requested offline rollback; also recovers missing current root."""
    uid = 0 if _test_uid is None else _test_uid
    _need(os.geteuid() == uid, "PRIVILEGED_UPGRADE_ROOT_REQUIRED")
    _need(type(expected_backup_manifest_sha256) is str and
          SHA64.fullmatch(expected_backup_manifest_sha256) is not None,
          "PRIVILEGED_UPGRADE_EXPECTED_SHA_INVALID")
    _trusted(factory_root, uid, folder=True)
    _trusted(factory_root / "ppu_privileged_source.py", uid, folder=False)
    _trusted(destination.parent, uid, folder=True)
    verifier = _verifier(factory_root)
    backup = destination.with_name(destination.name + ".previous")
    rejected = destination.with_name(destination.name + ".rejected")
    _quiescent()
    with _maintenance_locks(uid):
        _quiescent()
        before = _held_image_fingerprint(uid)
        _need(not rejected.exists() and not rejected.is_symlink(),
              "PRIVILEGED_ROLLBACK_REJECTED_PRESENT")
        old = verifier.verify_source(backup, expected_uid=uid)
        _need(old["code_manifest_sha256"] == expected_backup_manifest_sha256,
              "PRIVILEGED_ROLLBACK_STALE_SOURCE")
        if destination.exists() or destination.is_symlink():
            verifier.verify_source(destination, expected_uid=uid)
            os.rename(destination, rejected)
            _sync_dir(destination.parent)
        try:
            os.rename(backup, destination)
            _sync_dir(destination.parent)
            restored = verifier.verify_source(destination, expected_uid=uid)
            _need(restored["code_manifest_sha256"] == expected_backup_manifest_sha256
                  and _held_image_fingerprint(uid) == before,
                  "PRIVILEGED_ROLLBACK_POSTVERIFY_FAILED")
        except Exception:
            if not destination.exists() and rejected.exists():
                os.rename(rejected, destination)
                _sync_dir(destination.parent)
            raise
        return {"result": "ROLLED_BACK_NOT_EXECUTED",
                "current_manifest_sha256": expected_backup_manifest_sha256,
                "rejected": str(rejected) if rejected.exists() else None,
                "journal_sha256": before, "fpga_reloaded": False,
                "service_restarted": False, "dut": "NOT_RUN"}


def main(argv: list[str]) -> int:
    if os.geteuid() != 0 or (argv and not (
            len(argv) == 2 and argv[0] in ("upgrade", "rollback")
            and SHA64.fullmatch(argv[1]))):
        print("PRIVILEGED_PROVISION_ROOT_ONLY_FIXED_COMMAND", file=sys.stderr)
        return 2
    try:
        if not argv:
            receipt = provision()
        elif argv[0] == "upgrade":
            receipt = upgrade(expected_current_manifest_sha256=argv[1])
        else:
            receipt = rollback(expected_backup_manifest_sha256=argv[1])
        print(json.dumps(receipt, sort_keys=True))
    except (OSError, ProvisionDenied, Exception) as exc:
        print(type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
