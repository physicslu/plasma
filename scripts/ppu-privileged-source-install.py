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
TXN_SCHEMA = "plasma.ppu.privileged-upgrade-transaction.v1"


class ProvisionDenied(RuntimeError):
    pass


class _Interrupted(BaseException):
    """Test-only simulated power loss; never raised by production code."""


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


def _paths(destination: Path) -> dict:
    name = destination.name
    return {k: destination.with_name(name + suffix) for k, suffix in (
        ("backup", ".previous"), ("staged", ".next"), ("retired", ".retired"),
        ("rejected", ".rejected"), ("txn", ".transaction.json"))}


def _manifest_sha(verifier, root: Path, uid: int) -> str | None:
    """Verified Code Manifest SHA256, or None when absent/unverifiable."""
    if not root.exists() and not root.is_symlink():
        return None
    try:
        return verifier.verify_source(root, expected_uid=uid)["code_manifest_sha256"]
    except Exception:  # noqa: BLE001 - classification only, never activation
        return None


def _rename(src: Path, dst: Path) -> None:
    os.rename(src, dst)
    _sync_dir(dst.parent)


def _discard(path: Path) -> None:
    """Remove an inactive tree (never the active destination)."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    else:
        return
    _sync_dir(path.parent)


def _write_txn(txn: Path, state: dict, uid: int) -> None:
    """Durable transaction record: write tmp, fsync, atomic rename, fsync dir."""
    tmp = txn.with_name(txn.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (json.dumps(state, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rename(tmp, txn)
    _sync_dir(txn.parent)


def _read_txn(txn: Path, uid: int) -> dict | None:
    tmp = txn.with_name(txn.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()  # never renamed into place => never authoritative
    if not txn.exists() and not txn.is_symlink():
        return None
    info = txn.lstat()
    _need(stat.S_ISREG(info.st_mode) and info.st_uid == uid
          and info.st_mode & 0o077 == 0 and info.st_size <= 4096,
          "PRIVILEGED_UPGRADE_TRANSACTION_UNTRUSTED")
    try:
        state = json.loads(txn.read_bytes())
    except ValueError as exc:
        raise ProvisionDenied("PRIVILEGED_UPGRADE_TRANSACTION_INVALID") from exc
    _need(type(state) is dict and state.get("schema") == TXN_SCHEMA
          and state.get("phase") in ("PREPARED", "COMMITTED")
          and all(type(state.get(k)) is str and SHA64.fullmatch(state[k])
                  for k in ("old_sha256", "new_sha256")),
          "PRIVILEGED_UPGRADE_TRANSACTION_INVALID")
    return state


def _recover(verifier, destination: Path, uid: int) -> dict | None:
    """Finish an interrupted upgrade from its durable transaction record.

    PREPARED (not yet post-verified) => roll back to the old running tree,
    restoring the prior backup. COMMITTED => roll forward (drop the retired
    backup). Every step is an idempotent rename, so recovery itself may be
    interrupted and re-run.
    """
    p = _paths(destination)
    state = _read_txn(p["txn"], uid)
    if state is None:
        return None
    old, new = state["old_sha256"], state["new_sha256"]
    if state["phase"] == "COMMITTED":
        _discard(p["retired"])
        _discard(p["txn"])
        return {"recovered": "ROLLED_FORWARD", "current_manifest_sha256": new}
    current = _manifest_sha(verifier, destination, uid)
    if current == new or (current is None and destination.exists()):
        # Candidate (or a damaged tree) was activated but never confirmed.
        _discard(p["staged"])
        _rename(destination, p["staged"])
    if not destination.exists():
        _need(_manifest_sha(verifier, p["backup"], uid) == old,
              "PRIVILEGED_UPGRADE_RECOVERY_SOURCE_MISSING")
        _rename(p["backup"], destination)
    if not p["backup"].exists() and p["retired"].exists():
        _rename(p["retired"], p["backup"])
    _need(_manifest_sha(verifier, destination, uid) == old,
          "PRIVILEGED_UPGRADE_RECOVERY_FAILED")
    _discard(p["retired"])  # only reachable when backup was never rotated out
    _discard(p["staged"])
    _discard(p["txn"])
    return {"recovered": "ROLLED_BACK", "current_manifest_sha256": old}


def _clean_provision_stages(parent: Path) -> None:
    for leftover in parent.glob(".fpga-root-provision-*"):
        _discard(leftover)


def upgrade(factory_root: Path = FACTORY_ROOT,
            destination: Path = DESTINATION, *,
            expected_current_manifest_sha256: str,
            _test_uid: int | None = None,
            _fault=None) -> dict:
    """Offline Root code replacement with rotating backup and explicit CAS.

    V(n) -> V(n+1): afterwards the active tree is V(n+1) and `.previous` is
    exactly V(n), the tree running before this upgrade. An older `.previous`
    is rotated to `.retired` and only deleted after the new tree is
    post-verified and the COMMITTED transaction record is durable. An
    interrupted upgrade is recovered from that record on the next run.
    No systemctl mutations, FPGA writes, FPGA-journal writes or restarts.
    """
    uid = 0 if _test_uid is None else _test_uid
    fault = _fault or (lambda _step: None)  # test-only interruption hook
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
    p = _paths(destination)
    backup, staged, retired = p["backup"], p["staged"], p["retired"]
    _quiescent()
    with _maintenance_locks(uid):
        _quiescent()
        before = _held_image_fingerprint(uid)
        recovered = _recover(verifier, destination, uid)
        current = verifier.verify_source(destination, expected_uid=uid)
        _need(current["code_manifest_sha256"] == expected_current_manifest_sha256,
              "PRIVILEGED_UPGRADE_STALE_SOURCE")
        # Without a transaction record, `.next`/`.retired` were never active
        # (failed stage or quarantined rejected candidate) and are discarded.
        _discard(staged)
        _discard(retired)
        _clean_provision_stages(destination.parent)
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
        new_sha = candidate["code_manifest_sha256"]
        replaced = _manifest_sha(verifier, backup, uid)
        txn = {"schema": TXN_SCHEMA, "phase": "PREPARED",
               "old_sha256": expected_current_manifest_sha256,
               "new_sha256": new_sha}
        _write_txn(p["txn"], txn, uid)
        try:
            fault("prepared")
            if backup.exists() or backup.is_symlink():
                _rename(backup, retired)
            fault("backup_retired")
            _rename(destination, backup)
            fault("current_backed_up")
            _rename(staged, destination)
            fault("candidate_active")
            installed = verifier.verify_source(destination, expected_uid=uid)
            _need(installed["code_manifest_sha256"] == new_sha
                  and _held_image_fingerprint(uid) == before,
                  "PRIVILEGED_UPGRADE_POSTVERIFY_FAILED")
        except Exception:  # _Interrupted (simulated power loss) is not caught
            # Restore old active tree and old backup under the same locks;
            # the rejected candidate stays quarantined as `.next`.
            if destination.exists() and _manifest_sha(
                    verifier, destination, uid) != expected_current_manifest_sha256:
                _discard(staged)
                _rename(destination, staged)
            if not destination.exists():
                _rename(backup, destination)
            if not backup.exists() and retired.exists():
                _rename(retired, backup)
            _discard(p["txn"])
            raise
        txn["phase"] = "COMMITTED"
        _write_txn(p["txn"], txn, uid)
        fault("committed")
        _discard(retired)
        _discard(p["txn"])
        return {"result": "UPGRADED_NOT_EXECUTED",
                "previous_manifest_sha256": expected_current_manifest_sha256,
                "current_manifest_sha256": new_sha,
                "retired_backup_manifest_sha256": replaced,
                "recovered": recovered,
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
    p = _paths(destination)
    backup, rejected = p["backup"], p["rejected"]
    _quiescent()
    with _maintenance_locks(uid):
        _quiescent()
        before = _held_image_fingerprint(uid)
        recovered = _recover(verifier, destination, uid)
        if (recovered and recovered["current_manifest_sha256"]
                == expected_backup_manifest_sha256):
            # The interrupted upgrade was rolled back to the requested tree.
            return {"result": "ROLLED_BACK_NOT_EXECUTED",
                    "current_manifest_sha256": expected_backup_manifest_sha256,
                    "recovered": recovered, "rejected": None,
                    "journal_sha256": before, "fpga_reloaded": False,
                    "service_restarted": False, "dut": "NOT_RUN"}
        old = verifier.verify_source(backup, expected_uid=uid)
        _need(old["code_manifest_sha256"] == expected_backup_manifest_sha256,
              "PRIVILEGED_ROLLBACK_STALE_SOURCE")
        if destination.exists() or destination.is_symlink():
            verifier.verify_source(destination, expected_uid=uid)
            # An older rejected tree is inactive; replace it with this one.
            _discard(rejected)
            _rename(destination, rejected)
        try:
            _rename(backup, destination)
            restored = verifier.verify_source(destination, expected_uid=uid)
            _need(restored["code_manifest_sha256"] == expected_backup_manifest_sha256
                  and _held_image_fingerprint(uid) == before,
                  "PRIVILEGED_ROLLBACK_POSTVERIFY_FAILED")
        except Exception:
            if not destination.exists() and rejected.exists():
                _rename(rejected, destination)
            raise
        return {"result": "ROLLED_BACK_NOT_EXECUTED",
                "current_manifest_sha256": expected_backup_manifest_sha256,
                "recovered": recovered,
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
