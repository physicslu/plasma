#!/usr/bin/env python3
"""Operator recovery for ONE Bootstrap deployment refused before install.

Closes a ``recovery_required`` / ``coordinator_result_unreconciled`` API record
as ``failed`` / ``kit_preinstall_refused`` ONLY when the stored error is a kit
verification refusal and every observation proves no install ran: the
Coordinator journal, the current release and the Active Asset Set equal the
operator-supplied expected values, and the journal never names this
transaction. The original record is kept as a root-private backup with its
SHA-256. Never writes ``succeeded`` and never restores an older record.

Run on the PPU as root while ``plasma-bootstrap.service`` is stopped (it is the
only writer of the record); the Coordinator flock is held throughout.
Exit 0 = recovered, 1 = refused (nothing written), 2 = usage.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "plasma.ppu.bootstrap-preinstall-recovery.v1"
TX_RE = re.compile(r"[0-9a-f]{32}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
# Refusals raised only by the kit tool's verify_kit (no kit command executed).
ENGINE_PREFIX = "deployment engine failed with exit 2: ppu-bootstrap-kit: "
VERIFY_REFUSALS = (
    "Z2 PS kit is missing required deployment tooling",
    "Z2 PS kit artifact and sidecar are required",
    "kit file set does not exactly match SHA256SUMS",
)


class Refused(RuntimeError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Refused(code)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_json(path: Path) -> tuple[dict, bytes]:
    info = os.lstat(path)
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
         and not info.st_mode & 0o077, "RECORD_NOT_PRIVATE:" + path.name)
    raw = path.read_bytes()
    value = json.loads(raw)
    need(isinstance(value, dict), "RECORD_NOT_OBJECT:" + path.name)
    return value, raw


def atomic_private(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".recovery-new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def service_active(unit: str) -> bool:
    out = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True,
                         timeout=10)
    return out.stdout.strip() in ("active", "activating", "deactivating", "reloading")


def recover(args: argparse.Namespace, *, state_root: Path, product_root: Path,
            is_active=service_active, now=time.time) -> dict:
    need(os.geteuid() == 0 or args.allow_non_root_for_tests, "ROOT_REQUIRED")
    need(TX_RE.fullmatch(args.transaction_id) is not None, "TRANSACTION_ID_INVALID")
    for value in (args.expected_coordinator_sha256, args.expected_active_asset_set_sha256):
        need(SHA_RE.fullmatch(value) is not None, "EXPECTED_SHA_INVALID")
    need(not is_active("plasma-bootstrap.service"), "BOOTSTRAP_SERVICE_RUNNING")
    record_path = state_root / "deployment-api.json"
    journal_path = state_root / "deployment.json"
    lock_path = state_root / "deployment.lock"
    lock = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused("COORDINATOR_LOCK_HELD") from None
        record, raw = private_json(record_path)
        original_sha = hashlib.sha256(raw).hexdigest()
        # 1. The record is exactly this transaction, unreconciled, refused by verify_kit.
        need(record.get("schema_version") == 1 and record.get("transaction_id") == args.transaction_id,
             "RECORD_TRANSACTION_MISMATCH")
        need(record.get("state") == "recovery_required"
             and record.get("error_code") == "coordinator_result_unreconciled"
             and record.get("result") is None, "RECORD_STATE_NOT_ELIGIBLE")
        error = record.get("error")
        need(isinstance(error, str) and error.startswith(ENGINE_PREFIX)
             and error[len(ENGINE_PREFIX):].strip() in VERIFY_REFUSALS,
             "ERROR_NOT_KIT_VERIFY_REFUSAL")
        started = record.get("started_at_epoch_s")
        need(type(started) in (int, float), "RECORD_START_INVALID")
        # 2. The Coordinator never ran it: journal identical and not naming it.
        journal, journal_raw = private_json(journal_path)
        journal_sha = hashlib.sha256(journal_raw).hexdigest()
        need(journal_sha == args.expected_coordinator_sha256, "COORDINATOR_JOURNAL_CHANGED")
        need(journal.get("api_transaction_id") != args.transaction_id, "COORDINATOR_NAMES_TRANSACTION")
        need(journal.get("state") not in ("running", "installing", "activating"),
             "COORDINATOR_IN_FLIGHT")
        # 3. Runtime and Active Set unchanged; no install evidence after the start.
        current = product_root / "current"
        need(current.is_symlink() and os.readlink(current) == args.expected_current_release,
             "CURRENT_RELEASE_CHANGED")
        last_install = product_root / "install" / "last-install.json"
        need(last_install.is_file() and last_install.stat().st_mtime < started,
             "INSTALL_EVIDENCE_AFTER_TRANSACTION")
        releases = product_root / "releases"
        need(all(item.lstat().st_mtime < started for item in releases.iterdir()),
             "RELEASE_CREATED_AFTER_TRANSACTION")
        active = product_root / "assets" / "active.json"
        active_value = json.loads(active.read_bytes())
        need(isinstance(active_value, dict)
             and active_value.get("asset_set_sha256") == args.expected_active_asset_set_sha256,
             "ACTIVE_ASSET_SET_CHANGED")
        # 4. Backup, then one atomic write recording the confirmed failure.
        backups = state_root / "operator-recovery"
        backups.mkdir(mode=0o700, exist_ok=True)
        backup = backups / f"{args.transaction_id}-deployment-api.json.orig"
        need(not os.path.lexists(backup), "BACKUP_ALREADY_EXISTS")
        atomic_private(backup, raw)
        need(sha256(backup) == original_sha, "BACKUP_VERIFY_FAILED")
        evidence = {
            "schema": SCHEMA, "install_executed": False,
            "original_record_sha256": original_sha, "original_backup": str(backup),
            "coordinator_journal_sha256": journal_sha,
            "coordinator_transaction_id": journal.get("transaction_id"),
            "current_release": args.expected_current_release,
            "active_asset_set_sha256": args.expected_active_asset_set_sha256,
            "recovered_at_epoch_s": now(),
        }
        updated = {**record, "state": "failed", "error_code": "kit_preinstall_refused",
                   "updated_at_epoch_s": evidence["recovered_at_epoch_s"],
                   "operator_recovery": evidence}
        atomic_private(record_path, (json.dumps(updated, indent=2, sort_keys=True) + "\n").encode())
        reread, _ = private_json(record_path)
        need(reread == updated, "RECORD_VERIFY_FAILED")
        return {"result": "RECOVERED", **evidence, "transaction_id": args.transaction_id,
                "record_sha256": sha256(record_path)}
    finally:
        os.close(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--expected-coordinator-sha256", required=True)
    parser.add_argument("--expected-current-release", required=True)
    parser.add_argument("--expected-active-asset-set-sha256", required=True)
    parser.add_argument("--allow-non-root-for-tests", action="store_true", help=argparse.SUPPRESS)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        receipt = recover(args, state_root=Path("/var/lib/plasma-bootstrap"),
                          product_root=Path("/opt/plasma"))
        code = 0
    except Refused as exc:
        receipt, code = {"result": "REFUSED", "reason": str(exc)}, 1
    except (OSError, ValueError) as exc:
        receipt, code = {"result": "REFUSED", "reason": type(exc).__name__}, 1
    print("PLASMA_BOOTSTRAP_RECOVERY=" + json.dumps({"schema": SCHEMA, **receipt}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
