#!/usr/bin/env python3
"""Owner Operation Authorization for user-programmable PPU Bundles.

PLASMA is an owner-operated, user-programmable IC programmer. An operator
who holds the device's paired Bootstrap credential (Console -> Manager ->
PPU) may admit, install and request execution of *their own* Bundle v3
Packages. There is NO per-Bundle SHA256 allowlist, no publisher pin and no
administrator pre-approval.

Each mutating operation carries a fresh authorization bound to exactly:

* ``action``          -- one of ACTIONS (admit / stage / activate /
                         activate+FPGA load / Asset execute); one authorization never covers a
                         different stage;
* ``device_id``       -- the target PPU's derived Bootstrap device identity;
* ``subject_sha256``  -- the exact Bundle archive (== Asset Set) SHA256 the
                         user confirmed;
* ``transaction_id``  -- the B1 upload, the current B2 admission, or the
                         Runtime Job, according to the action;
* ``package_identity_sha256`` -- only for ``asset.execute``.

The authorization is an HMAC-SHA256 under a key derived from the paired
credential. That does NOT add strength over the Bearer credential itself;
it binds the user's explicit choice to the exact operation so a receipt,
request field or earlier stage's authorization cannot be replayed for a
different action, Bundle, device or transaction, and rotating the pairing
credential invalidates every outstanding authorization.

Operator authorization is distinct from -- and never replaces -- Bundle v3
format and SHA256 integrity, Target, Package DAG, Active Asset Set, FPGA
qualification, Owner Lock, Journal, Recovery and Linux privilege checks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Mapping

SCHEMA = "plasma.ppu.owner-operation-authorization.v1"
METHOD = "paired-console-operation-hmac-sha256"
STATUS = "OWNER_AUTHORIZED"
KEY_CONTEXT = b"plasma.ppu.owner-operation-authorization.v1/key"
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ID32 = re.compile(r"[0-9a-f]{32}\Z")
DEVICE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")

ADMIT = "bundle.admit"
INSTALL = "bundle.install"
ACTIVATE = "bundle.activate"
ACTIVATE_FPGA_LOAD = "bundle.activate-fpga-load"
EXECUTE = "asset.execute"
ACTIONS = frozenset({ADMIT, INSTALL, ACTIVATE, ACTIVATE_FPGA_LOAD, EXECUTE})
FIELDS = frozenset({
    "schema", "action", "device_id", "subject_sha256", "transaction_id",
    "package_identity_sha256", "mac",
})


class OwnerAuthorizationDenied(ValueError):
    pass


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise OwnerAuthorizationDenied(code)


def _credential(credential: object) -> bytes:
    _require(type(credential) is str and 32 <= len(credential) <= 256
             and not any(ch.isspace() for ch in credential),
             "OWNER_AUTHORIZATION_CREDENTIAL_UNAVAILABLE")
    return hmac.new(credential.encode("utf-8"), KEY_CONTEXT, hashlib.sha256).digest()


def _claims(*, action: object, device_id: object, subject_sha256: object,
            transaction_id: object,
            package_identity_sha256: object) -> dict[str, Any]:
    _require(type(action) is str and action in ACTIONS,
             "OWNER_AUTHORIZATION_ACTION_DENIED")
    _require(type(device_id) is str and DEVICE.fullmatch(device_id) is not None,
             "OWNER_AUTHORIZATION_FIELDS_INVALID")
    _require(type(subject_sha256) is str and SHA64.fullmatch(subject_sha256) is not None,
             "OWNER_AUTHORIZATION_FIELDS_INVALID")
    _require(type(transaction_id) is str and ID32.fullmatch(transaction_id) is not None,
             "OWNER_AUTHORIZATION_FIELDS_INVALID")
    if action == EXECUTE:
        _require(type(package_identity_sha256) is str
                 and SHA64.fullmatch(package_identity_sha256) is not None,
                 "OWNER_AUTHORIZATION_FIELDS_INVALID")
    else:
        _require(package_identity_sha256 is None, "OWNER_AUTHORIZATION_FIELDS_INVALID")
    return {
        "schema": SCHEMA, "action": action, "device_id": device_id,
        "subject_sha256": subject_sha256, "transaction_id": transaction_id,
        "package_identity_sha256": package_identity_sha256,
    }


def _mac(key: bytes, claims: Mapping[str, Any]) -> str:
    message = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def issue(*, credential: str, action: str, device_id: str, subject_sha256: str,
          transaction_id: str, package_identity_sha256: str | None = None,
          ) -> dict[str, Any]:
    """Issued by the paired Manager for ONE explicit Console operation."""
    claims = _claims(action=action, device_id=device_id,
                     subject_sha256=subject_sha256, transaction_id=transaction_id,
                     package_identity_sha256=package_identity_sha256)
    return {**claims, "mac": _mac(_credential(credential), claims)}


def verify(authorization: object, *, credential: str, action: str, device_id: str,
           subject_sha256: str, transaction_id: str,
           package_identity_sha256: str | None = None) -> dict[str, Any]:
    """Verify on the PPU against facts the PPU derived itself.

    ``device_id``, ``subject_sha256`` and ``transaction_id`` must come from
    the device's own identity, the bytes it hashed and its current journal,
    never from the same request that carries the authorization.
    Returns a receipt summary that holds no secret and no MAC.
    """
    _require(isinstance(authorization, Mapping) and set(authorization) == FIELDS
             and authorization.get("schema") == SCHEMA,
             "OWNER_AUTHORIZATION_REQUIRED")
    supplied = _claims(
        action=authorization["action"], device_id=authorization["device_id"],
        subject_sha256=authorization["subject_sha256"],
        transaction_id=authorization["transaction_id"],
        package_identity_sha256=authorization["package_identity_sha256"],
    )
    mac = authorization["mac"]
    _require(type(mac) is str and SHA64.fullmatch(mac) is not None
             and hmac.compare_digest(mac, _mac(_credential(credential), supplied)),
             "OWNER_AUTHORIZATION_INVALID")
    _require(supplied["action"] == action, "OWNER_AUTHORIZATION_ACTION_MISMATCH")
    _require(supplied["device_id"] == device_id, "OWNER_AUTHORIZATION_DEVICE_MISMATCH")
    _require(supplied["subject_sha256"] == subject_sha256,
             "OWNER_AUTHORIZATION_SUBJECT_MISMATCH")
    _require(supplied["transaction_id"] == transaction_id,
             "OWNER_AUTHORIZATION_TRANSACTION_MISMATCH")
    _require(supplied["package_identity_sha256"] == package_identity_sha256,
             "OWNER_AUTHORIZATION_PACKAGE_MISMATCH")
    return {
        "status": STATUS, "method": METHOD, **supplied,
        "authorization_sha256": hashlib.sha256(
            json.dumps(dict(authorization), sort_keys=True,
                       separators=(",", ":")).encode("utf-8")).hexdigest(),
    }
