#!/usr/bin/env python3
"""Single-machine, device-owned approval of exact Bundle v3 archives.

A SHA256 digest is content identity, NOT publisher authenticity. Approval is
an explicit local administrator action, held in a service-owned 0600 policy
file independent of uploaded Bundle bytes or the HTTP caller. Bundle v3
structural/target checks, FPGA qualification, Owner Locks and Recovery are
separate non-optional gates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

SCHEMA = "plasma.ppu.bundle-authority.v2"
METHOD = "device-local-exact-bundle-sha256"
STATUS = "LOCAL_APPROVED"
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
POLICY_FIELDS = {"schema", "generation", "approved_bundle_sha256"}


class BundleAuthorityDenied(ValueError):
    pass


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise BundleAuthorityDenied(code)


def _pairs(items):
    data = {}
    for key, value in items:
        if key in data:
            raise BundleAuthorityDenied("BUNDLE_AUTHORITY_DUPLICATE_FIELD")
        data[key] = value
    return data


def _read_device_policy(path: Path) -> tuple[dict[str, Any], str]:
    """Reject caller-writable policies, symlinks and malformed JSON."""
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
        _require(stat.S_ISREG(info.st_mode)
                 and info.st_uid == os.geteuid()
                 and info.st_mode & 0o077 == 0
                 and 0 < info.st_size <= 16384,
                 "BUNDLE_AUTHORITY_POLICY_UNTRUSTED")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(16385)
    finally:
        os.close(fd)
    _require(0 < len(raw) <= 16384, "BUNDLE_AUTHORITY_POLICY_UNTRUSTED")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: _require(
                              False, "BUNDLE_AUTHORITY_POLICY_INVALID"))
    except (ValueError, UnicodeDecodeError) as exc:
        if isinstance(exc, BundleAuthorityDenied):
            raise
        raise BundleAuthorityDenied("BUNDLE_AUTHORITY_POLICY_MALFORMED") from exc
    _require(type(data) is dict
             and set(data) == POLICY_FIELDS and data["schema"] == SCHEMA
             and type(data["generation"]) is int and data["generation"] > 0
             and type(data["approved_bundle_sha256"]) is list
             and len(data["approved_bundle_sha256"]) <= 128,
             "BUNDLE_AUTHORITY_POLICY_INVALID")
    ids = data["approved_bundle_sha256"]
    _require(all(type(x) is str and SHA64.fullmatch(x) for x in ids)
             and len(set(ids)) == len(ids),
             "BUNDLE_AUTHORITY_POLICY_INVALID")
    return data, hashlib.sha256(raw).hexdigest()


def approve_identity(*, archive_sha256: str, policy_path: Path) -> dict[str, Any]:
    """Live local approval: an exact already-verified Bundle digest only.

    Never authorizes executing a Package as root or accessing DUT/FPGA.
    Recheck on B2, B3 and every Runtime dispatch; owner may revoke any time
    by editing the protected file. No special publisher/expiry/source pin.
    """
    _require(type(archive_sha256) is str and SHA64.fullmatch(archive_sha256),
             "BUNDLE_AUTHORITY_INPUT_INVALID")
    policy, policy_sha = _read_device_policy(policy_path)
    _require(archive_sha256 in policy["approved_bundle_sha256"],
             "BUNDLE_AUTHORITY_DIGEST_NOT_APPROVED")
    return {
        "status": STATUS, "method": METHOD,
        "generation": policy["generation"],
        "policy_sha256": policy_sha,
        "archive_sha256": archive_sha256,
    }


def approve_verified_bundle(bundle, *, policy_path: Path) -> dict[str, Any]:
    _require(getattr(bundle, "schema", None) == "plasma.ppu.bundle.v3"
             and getattr(bundle, "kind", None) == "bundle"
             and type(getattr(bundle, "archive_sha256", None)) is str,
             "BUNDLE_AUTHORITY_CANONICAL_ONLY")
    return approve_identity(archive_sha256=bundle.archive_sha256,
                            policy_path=policy_path)
