#!/usr/bin/env python3
"""Operator-controlled local vault handoff for Microchip Phase 1 portable source.

NOT a remote store, immutable filesystem, long-term retention guarantee, or
Production source admission. Refuses replacing an existing evidence key. The
final receipt is written only after verifying the stored copy from disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import microchip_phase1_portable_custody_v1 as portable

KEY_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
BUNDLE_NAME = "original-evidence.zip"
RECEIPT_NAME = "local-deposit-receipt.json"
MAX_BYTES = portable.MAX_ZIP_BYTES


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate_key(value):
    require(isinstance(value, str) and KEY_RE.fullmatch(value) is not None,
            "invalid evidence key; use 1-64 lowercase letters/digits/underscore/hyphen")
    return value


def vault_root(path):
    path = Path(path)
    require(path.is_absolute(), "vault root must be an explicit absolute path")
    require(path.is_dir() and not path.is_symlink(),
            "vault root missing, symlinked or not a directory")
    require(not (path.stat().st_mode & stat.S_IWOTH),
            "vault root is world writable; restrict permissions")
    require("production" not in {part.lower() for part in path.parts},
            "Production root prohibited for Research evidence")
    return path


def vault_dir(path, key, present=False):
    root = vault_root(path)
    child = root / validate_key(key)
    require(not child.is_symlink(), "symlinked evidence key rejected")
    if present:
        require(child.is_dir(), "evidence key absent or not a directory")
    else:
        require(not child.exists(), "evidence key already exists; no overwrite")
    return child


def safe_file(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(),
            "source/destination must be a regular non-symlink file")
    require(path.stat().st_size <= MAX_BYTES, "evidence archive exceeds size cap")
    return path


def transfer_bytes(source, output):
    """Bounded streaming copy; exclusive target, no overwrites."""
    src = safe_file(source)
    h = hashlib.sha256()
    count = 0
    with src.open("rb") as reader, Path(output).open("xb") as writer:
        os.chmod(output, 0o600)
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            require(count <= MAX_BYTES, "source stream exceeds max archive size")
            writer.write(chunk)
            h.update(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return {"sha256": h.hexdigest(), "size_bytes": count}


def receipt_from_bundle(key, stored, verified):
    return {
        "schema_version": 1,
        "evidence_key": key,
        "custody_stage": "OPERATOR_SELECTED_LOCAL_FILESYSTEM_COPY",
        "stored_bundle_filename": BUNDLE_NAME,
        "stored_bundle_sha256": stored["sha256"],
        "stored_bundle_bytes": stored["size_bytes"],
        "portable_source_file_count": verified["source_file_count"],
        "offline_cold_replay_result": verified["offline_bundle_verification"],
        "original_source_replay_completed": verified[
            "source_originals_sha256_replayed"],
        "independent_mcp_pagination_replayed": verified[
            "original_mcp_dual_pagination_replayed"],
        "local_copy_verified": True,
        "independent_offsite_copy_verified": False,
        "durable_storage_verified": False,
        "immutable_object_lock_verified": False,
        "retention_policy_enforced": False,
        "authenticity_signature_verified": False,
        "production_write_authorized": False,
        "openocd_software_supported_claimed": False,
    }


def deposit(archive, root, key):
    """Exclusive-create an evidence key; a failed deposit remains incomplete."""
    archive = safe_file(archive)
    target = vault_dir(root, key)
    require(archive.resolve().parent != Path(root).resolve(),
            "archive source must be outside vault root")
    # Verify original archive first to avoid storing deliberately invalid data.
    before = portable.verify(archive)
    target.mkdir(mode=0o700)
    stored_path = target / BUNDLE_NAME
    copied = transfer_bytes(archive, stored_path)
    require(copied["sha256"] == before["bundle_sha256"],
            "bundle mutated between source replay and stored copy")
    # This new verifier always reads through the *stored* local copy.
    after = portable.verify(stored_path)
    require(after == before, "stored bundle cold replay does not match source")
    receipt = receipt_from_bundle(validate_key(key), copied, after)
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with (target / RECEIPT_NAME).open("xb") as f:
        os.chmod(target / RECEIPT_NAME, 0o600)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    # Single operator-managed local filesystem is not durable/offsite proof.
    return audit(root, key)


def audit(root, key):
    target = vault_dir(root, key, present=True)
    stored = safe_file(target / BUNDLE_NAME)
    rec_path = safe_file(target / RECEIPT_NAME)
    require(rec_path.stat().st_size <= 64 * 1024, "oversized local receipt")
    recorded = json.loads(rec_path.read_text(encoding="utf-8"))
    verified = portable.verify(stored)
    actual = {"sha256": verified["bundle_sha256"],
              "size_bytes": stored.stat().st_size}
    expected = receipt_from_bundle(validate_key(key), actual, verified)
    require(recorded == expected, "local receipt/verified original evidence mismatch")
    require(set(target.iterdir()) == {stored, rec_path},
            "unexpected files in local evidence key")
    return {**expected, "audit_result": "PASS",
            "offsite_or_immutable_archive_status": "NOT_VERIFIED"}


def restore(root, key, destination):
    # Audit the stored copy first, then *independently* copy out and cold replay.
    original_audit = audit(root, key)
    target = vault_dir(root, key, present=True)
    destination = Path(destination)
    require(not destination.exists() and not destination.is_symlink(),
            "restore destination already exists")
    require(destination.is_absolute() and destination.parent.is_dir(),
            "restore destination requires an explicit existing absolute directory")
    require(destination.resolve().parent != target.resolve(),
            "restored copy must be outside the evidence object directory")
    copied = transfer_bytes(target / BUNDLE_NAME, destination)
    require(copied["sha256"] == original_audit["stored_bundle_sha256"],
            "restored file SHA-256 mismatch")
    again = portable.verify(destination)
    require(again["bundle_sha256"] == copied["sha256"],
            "independent restored bundle replay mismatch")
    return {**original_audit, "restore_result": "PASS",
            "restore_sha256": copied["sha256"],
            "independent_restored_copy_cold_replayed": True,
            "independent_offsite_copy_verified": False,
            "durable_storage_verified": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--deposit", type=Path, metavar="ORIGINAL_ZIP")
    mode.add_argument("--audit", action="store_true")
    mode.add_argument("--restore", type=Path, metavar="RESTORED_ZIP")
    p.add_argument("--vault-root", type=Path, required=True)
    p.add_argument("--evidence-key", required=True)
    p.add_argument("--receipt", type=Path)
    args = p.parse_args()
    if args.deposit:
        result = deposit(args.deposit, args.vault_root, args.evidence_key)
    elif args.restore:
        result = restore(args.vault_root, args.evidence_key, args.restore)
    else:
        result = audit(args.vault_root, args.evidence_key)
    if args.receipt is not None:
        require(not args.receipt.exists() and not args.receipt.is_symlink(),
                "external receipt already exists")
        require(args.receipt.is_absolute() and args.receipt.parent.is_dir(),
                "receipt requires an explicit existing absolute parent")
        with args.receipt.open("x", encoding="utf-8") as f:
            json.dump(result, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
