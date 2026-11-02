#!/usr/bin/env python3
"""One device-owned Bundle authority for ALL executable Asset kinds.

Development-stage Master approval uses a root-provisioned *exact complete
Bundle SHA256* grant. This is a genuine independent local authorization
decision, not a publisher cryptographic signature. A future publisher
signature verifier may replace the grant source, not the B2 semantics.

This module never executes an Asset, loads FPGA, mutates the policy, nor
creates a signing or HTTP API.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "plasma.ppu.bundle-authority.v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
TARGET = {"platform", "board", "fpga_part"}
POLICY_FIELDS = {"schema", "master_generation", "authorizations"}
GRANT_FIELDS = {
    "publisher", "archive_sha256", "source_commit", "purpose",
    "target", "allowed_kinds", "expires_epoch_s",
}


class BundleAuthorityDenied(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BundleAuthorityDenied(code)


def _pairs(items):
    data = {}
    for key, value in items:
        if key in data:
            raise BundleAuthorityDenied("BUNDLE_AUTHORITY_DUPLICATE_FIELD")
        data[key] = value
    return data


def _read_device_policy(path: Path) -> tuple[dict[str, Any], str]:
    """Use a root/service-owned file, never Bundle, upload, token or HTTP data."""
    _require(isinstance(path, Path) and path.is_absolute(),
             "BUNDLE_AUTHORITY_POLICY_PATH_INVALID")
    _require(not path.is_symlink() and not path.parent.is_symlink(),
             "BUNDLE_AUTHORITY_POLICY_UNTRUSTED")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise BundleAuthorityDenied("BUNDLE_AUTHORITY_NOT_PROVISIONED") from exc
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                 and info.st_mode & 0o077 == 0 and 0 < info.st_size <= 65536,
                 "BUNDLE_AUTHORITY_POLICY_UNTRUSTED")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(65537)
    finally:
        os.close(fd)
    _require(0 < len(raw) <= 65536, "BUNDLE_AUTHORITY_POLICY_UNTRUSTED")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: _require(
                              False, "BUNDLE_AUTHORITY_NONFINITE"))
    except (ValueError, UnicodeDecodeError) as exc:
        if isinstance(exc, BundleAuthorityDenied):
            raise
        raise BundleAuthorityDenied("BUNDLE_AUTHORITY_POLICY_MALFORMED") from exc
    _require(type(data) is dict and set(data) == POLICY_FIELDS
             and data["schema"] == SCHEMA
             and type(data["master_generation"]) is int
             and data["master_generation"] > 0
             and type(data["authorizations"]) is list
             and 1 <= len(data["authorizations"]) <= 128,
             "BUNDLE_AUTHORITY_POLICY_INVALID")
    return data, hashlib.sha256(raw).hexdigest()


def approve_identity(
    *, archive_sha256: str, source_commit: str, purpose: str,
    target: Mapping[str, str], package_kinds: tuple[str, ...] | list[str],
    policy_path: Path, now_epoch_s: int | None = None,
) -> dict[str, Any]:
    """Evaluate the exact verified Asset Set against a separate Master grant.

    Call ONLY with already verified Bundle/installed Asset Set identity.
    This grants authorization to select an Asset, NOT permission to execute
    code as root, reconfigure FPGA, or operate DUT.
    """
    if now_epoch_s is None:
        now_epoch_s = int(time.time())
    _require(type(now_epoch_s) is int and now_epoch_s >= 0
             and type(archive_sha256) is str and SHA64.fullmatch(archive_sha256)
             and type(source_commit) is str and SHA40.fullmatch(source_commit)
             and type(purpose) is str and NAME.fullmatch(purpose)
             and isinstance(target, Mapping) and set(target) == TARGET
             and all(type(v) is str and 0 < len(v) <= 128
                     for v in target.values())
             and type(package_kinds) in (tuple, list)
             and len(package_kinds) >= 1
             and all(type(k) is str and NAME.fullmatch(k)
                     for k in package_kinds),
             "BUNDLE_AUTHORITY_INPUT_INVALID")
    policy, policy_sha = _read_device_policy(policy_path)
    valid = []
    seen = set()
    for item in policy["authorizations"]:
        _require(type(item) is dict and set(item) == GRANT_FIELDS
                 and type(item["publisher"]) is str
                 and NAME.fullmatch(item["publisher"])
                 and type(item["archive_sha256"]) is str
                 and SHA64.fullmatch(item["archive_sha256"])
                 and type(item["source_commit"]) is str
                 and SHA40.fullmatch(item["source_commit"])
                 and type(item["purpose"]) is str
                 and NAME.fullmatch(item["purpose"])
                 and type(item["target"]) is dict
                 and set(item["target"]) == TARGET
                 and all(type(v) is str and 0 < len(v) <= 128
                         for v in item["target"].values())
                 and type(item["allowed_kinds"]) is list
                 and 1 <= len(item["allowed_kinds"]) <= 32
                 and all(type(k) is str and NAME.fullmatch(k)
                         for k in item["allowed_kinds"])
                 and len(set(item["allowed_kinds"])) == len(item["allowed_kinds"])
                 and type(item["expires_epoch_s"]) is int
                 and item["expires_epoch_s"] > 0,
                 "BUNDLE_AUTHORITY_GRANT_INVALID")
        _require(item["archive_sha256"] not in seen,
                 "BUNDLE_AUTHORITY_DUPLICATE_GRANT")
        seen.add(item["archive_sha256"])
        if item["archive_sha256"] == archive_sha256:
            valid.append(item)
    _require(len(valid) == 1, "BUNDLE_AUTHORITY_DIGEST_NOT_APPROVED")
    grant = valid[0]
    _require(grant["source_commit"] == source_commit
             and grant["purpose"] == purpose
             and grant["target"] == dict(target),
             "BUNDLE_AUTHORITY_SCOPE_MISMATCH")
    _require(grant["expires_epoch_s"] > now_epoch_s,
             "BUNDLE_AUTHORITY_EXPIRED")
    _require(set(package_kinds) <= set(grant["allowed_kinds"]),
             "BUNDLE_AUTHORITY_KIND_DENIED")
    return {
        "status": "MASTER_APPROVED",
        "method": "root-provisioned-exact-bundle-sha256",
        "publisher": grant["publisher"],
        "master_generation": policy["master_generation"],
        "policy_sha256": policy_sha,
        "archive_sha256": archive_sha256,
        "expires_epoch_s": grant["expires_epoch_s"],
        "allowed_kinds": sorted(set(grant["allowed_kinds"])),
    }


def approve_verified_bundle(bundle, *, policy_path: Path,
                            now_epoch_s: int | None = None) -> dict[str, Any]:
    _require(getattr(bundle, "schema", None) == "plasma.ppu.bundle.v3"
             and getattr(bundle, "kind", None) == "bundle",
             "BUNDLE_AUTHORITY_CANONICAL_ONLY")
    return approve_identity(
        archive_sha256=bundle.archive_sha256,
        source_commit=bundle.source_commit,
        purpose=bundle.purpose,
        target=bundle.target,
        package_kinds=[p.kind for p in bundle.packages],
        policy_path=policy_path, now_epoch_s=now_epoch_s,
    )
