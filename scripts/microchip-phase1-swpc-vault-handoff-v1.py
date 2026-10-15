#!/usr/bin/env python3
"""SWPC manual Evidence Vault handoff (dry-run by default).

This tool never downloads artifacts, changes permissions, creates a vault
root, configures a service, or claims offsite/durable evidence custody.
Use only with original manufacturer bytes independently pinned by SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
RESEARCH = REPO / "data/device-catalog/research"
sys.path.insert(0, str(RESEARCH))
import microchip_phase1_local_vault_v1 as local_vault  # noqa: E402
import microchip_phase1_portable_custody_v1 as portable  # noqa: E402

ARCHIVE = "portable-original-evidence.zip"
PACK_RECEIPT = "pack-receipt.json"
COLD_RECEIPT = "cold-replay-receipt.json"
PIN = "portable-original-evidence.sha256"
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def regular(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "missing/symlinked/nonregular artifact input")
    require(p.stat().st_size <= portable.MAX_ZIP_BYTES,
            "artifact file too large")
    return p


def directory(path, role):
    p = Path(path)
    require(p.is_absolute() and p.is_dir() and not p.is_symlink(),
            f"{role} must be a pre-existing absolute, nonsymlink directory")
    return p.resolve()


def sha256_stream(path):
    digest = hashlib.sha256()
    count = 0
    with regular(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            count += len(block)
            require(count <= portable.MAX_ZIP_BYTES,
                    "artifact stream exceeds size cap")
            digest.update(block)
    return digest.hexdigest(), count


def mount_observation(path):
    """Read-only kernel-side filesystem identity, not physical independence."""
    p = Path(path)
    result = {
        "st_dev": p.stat().st_dev,
        "mount_target": None, "mount_source": None,
        "filesystem_type": None, "mount_probe": "UNAVAILABLE",
    }
    if shutil.which("findmnt"):
        run = subprocess.run(
            ["findmnt", "--json", "-T", str(p),
             "-o", "TARGET,SOURCE,FSTYPE"], capture_output=True, text=True,
            timeout=10, check=False)
        if run.returncode == 0:
            data = json.loads(run.stdout)
            rows = data.get("filesystems", [])
            if len(rows) == 1:
                fs = rows[0]
                result.update(mount_target=fs.get("target"),
                              mount_source=fs.get("source"),
                              filesystem_type=fs.get("fstype"),
                              mount_probe="OBSERVED")
    return result


def preflight(artifact_dir, vault_root, restore_dir, key, expected_sha):
    require(isinstance(expected_sha, str) and SHA.fullmatch(expected_sha),
            "expected SHA-256 must be 64 lowercase hex characters")
    key = local_vault.validate_key(key)
    source = directory(artifact_dir, "artifact directory")
    vault = local_vault.vault_root(vault_root).resolve()
    restore = directory(restore_dir, "restore directory")
    require(source != vault and source != restore and vault != restore,
            "artifact/vault/restore directories must be distinct")
    require(not vault.is_relative_to(REPO) and not REPO.is_relative_to(vault),
            "vault must be outside Git checkout")
    require(not source.is_relative_to(vault) and not restore.is_relative_to(vault),
            "artifact/restore directory cannot be inside vault")
    require(not vault.is_relative_to(source) and not vault.is_relative_to(restore),
            "vault cannot be nested within staging or restore")
    local_vault.vault_dir(vault, key)
    restore_target = restore / f"{key}-restored.zip"
    require(not restore_target.exists() and not restore_target.is_symlink(),
            "restore target already exists; choose a new key")
    bundle = regular(source / ARCHIVE)
    received_sha, size = sha256_stream(bundle)
    require(received_sha == expected_sha,
            "actual source ZIP SHA-256 differs from separately pinned GitHub evidence")

    local_pin = regular(source / PIN).read_text(encoding="utf-8").strip().split()
    require(len(local_pin) == 2 and local_pin[0] == received_sha
            and Path(local_pin[1].lstrip("*")).name == ARCHIVE,
            "artifact SHA-256 sidecar mismatch")
    pack = json.loads(regular(source / PACK_RECEIPT).read_text(encoding="utf-8"))
    cold = json.loads(regular(source / COLD_RECEIPT).read_text(encoding="utf-8"))
    require(pack == cold and pack.get("bundle_sha256") == received_sha,
            "artifact pack and cold replay receipts disagree")

    actual = portable.verify(bundle)
    require(actual == pack and actual["offline_bundle_verification"] == "PASS",
            "fresh offline Microchip original-source replay mismatch")
    require(actual.get("durable_storage_verified") is False
            and actual.get("production_write_authorized") is False,
            "untrusted research evidence authorization")

    stat = os.statvfs(vault)
    free = stat.f_bavail * stat.f_frsize
    target_free = max(size * 3, 64 * 1024 * 1024)
    require(free >= target_free, "vault filesystem free space below safety margin")
    rest_stat = os.statvfs(restore)
    require(rest_stat.f_bavail * rest_stat.f_frsize >= target_free,
            "restore filesystem free space below safety margin")
    orig_fs = mount_observation(source)
    vault_fs = mount_observation(vault)
    restore_fs = mount_observation(restore)
    repo_fs = mount_observation(REPO)
    root_fs = mount_observation(Path("/"))
    return {
        "schema_version": 1,
        "preflight": "PASS",
        "execution_mode": "DRY_RUN_NO_VAULT_WRITE",
        "source_bundle_sha256": received_sha,
        "source_bundle_bytes": size,
        "source_originals_sha256_replayed": True,
        "independent_mcp_pagination_replayed": True,
        "original_source_file_count": actual["source_file_count"],
        "evidence_key": key,
        "vault_root": str(vault),
        "restore_directory": str(restore),
        "vault_free_bytes": free,
        "vault_required_safety_margin_bytes": target_free,
        "filesystem_observation": {
            "source": orig_fs, "vault": vault_fs,
            "restore": restore_fs, "repository": repo_fs,
            "system_root": root_fs,
        },
        "vault_on_different_kernel_device_from_repository": (
            vault_fs["st_dev"] != repo_fs["st_dev"]),
        "vault_on_different_kernel_device_from_system_root": (
            vault_fs["st_dev"] != root_fs["st_dev"]),
        "restore_on_different_kernel_device_from_vault": (
            restore_fs["st_dev"] != vault_fs["st_dev"]),
        "independent_physical_disk_verified": False,
        "durable_storage_verified": False,
        "independent_offsite_copy_verified": False,
        "immutable_retention_verified": False,
        "production_write_authorized": False,
    }


def execute(artifact_dir, vault_root, restore_dir, key, expected_sha):
    check = preflight(artifact_dir, vault_root, restore_dir, key, expected_sha)
    archive = directory(artifact_dir, "artifact directory") / ARCHIVE
    copied = local_vault.deposit(archive, vault_root, key)
    audited = local_vault.audit(vault_root, key)
    require(copied == audited and
            audited["stored_bundle_sha256"] == expected_sha,
            "local evidence deposit and read-back disagreed")
    restored_name = directory(restore_dir, "restore directory") / f"{key}-restored.zip"
    restored = local_vault.restore(vault_root, key, restored_name)
    require(restored["restore_result"] == "PASS" and
            restored["restore_sha256"] == expected_sha and
            restored["independent_restored_copy_cold_replayed"] is True,
            "restored manufacturer evidence validation failed")
    result = {
        **check,
        "execution_mode": "OPERATOR_SELECTED_LOCAL_DEPOSIT",
        "local_deposit": "PASS",
        "stored_bundle_audit": "PASS",
        "local_restore_and_offline_cold_replay": "PASS",
        "restored_bundle_sha256": restored["restore_sha256"],
        "vault_copy_verified": True,
        "independent_physical_disk_verified": False,
        "durable_storage_verified": False,
        "independent_offsite_copy_verified": False,
        "immutable_retention_verified": False,
        "production_write_authorized": False,
    }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-dir", type=Path, required=True)
    p.add_argument("--vault-root", type=Path, required=True)
    p.add_argument("--restore-dir", type=Path, required=True)
    p.add_argument("--evidence-key", required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--apply", action="store_true",
                   help="explicitly deposit, audit, restore; default is read-only")
    p.add_argument("--receipt", type=Path, help="existing parent; new file only")
    args = p.parse_args()
    if args.apply:
        result = execute(args.artifact_dir, args.vault_root, args.restore_dir,
                         args.evidence_key, args.expected_sha256)
    else:
        result = preflight(args.artifact_dir, args.vault_root, args.restore_dir,
                           args.evidence_key, args.expected_sha256)
    if args.receipt:
        require(args.receipt.is_absolute()
                and args.receipt.parent.is_dir()
                and not args.receipt.exists()
                and not args.receipt.is_symlink(),
                "output receipt requires absolute new file in existing directory")
        with args.receipt.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
