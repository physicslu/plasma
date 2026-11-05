"""Manager-side issuer of PPU Owner Operation Authorizations.

Wire contract: ``plasma.ppu.owner-operation-authorization.v1``. The single
PPU-side verifier is ``scripts/ppu_owner_authorization.py``; this issuer must
produce byte-identical claims and MAC (enforced by a cross-implementation
Host test). The Manager issues exactly one authorization per explicit Console
operation, bound to the paired device, the archive SHA256 the user confirmed
and the B1/B2 transaction. It is not a per-Bundle allowlist, publisher
signature or parallel authorization database, and nothing is persisted.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

SCHEMA = "plasma.ppu.owner-operation-authorization.v1"
KEY_CONTEXT = b"plasma.ppu.owner-operation-authorization.v1/key"
ADMIT = "bundle.admit"
INSTALL = "bundle.install"
ACTIVATE = "bundle.activate"
ACTIVATE_FPGA_LOAD = "bundle.activate-fpga-load"
_BUNDLE_ACTIONS = frozenset({ADMIT, INSTALL, ACTIVATE, ACTIVATE_FPGA_LOAD})
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_ID32 = re.compile(r"[0-9a-f]{32}\Z")
_DEVICE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")


class OwnerAuthorizationError(ValueError):
    pass


def issue_bundle_operation(
    *, credential: str, action: str, device_id: str,
    subject_sha256: str, transaction_id: str,
) -> dict[str, Any]:
    """One Bundle B2/B3 owner operation. Runtime ``asset.execute`` is not
    issued by the Manager until a Runtime executor is qualified (Stage C)."""
    if (type(action) is not str or action not in _BUNDLE_ACTIONS
            or type(device_id) is not str or not _DEVICE.fullmatch(device_id)
            or type(subject_sha256) is not str or not _SHA64.fullmatch(subject_sha256)
            or type(transaction_id) is not str or not _ID32.fullmatch(transaction_id)
            or type(credential) is not str or not 32 <= len(credential) <= 256
            or any(ch.isspace() for ch in credential)):
        raise OwnerAuthorizationError("owner operation authorization input is invalid")
    claims = {
        "schema": SCHEMA, "action": action, "device_id": device_id,
        "subject_sha256": subject_sha256, "transaction_id": transaction_id,
        "package_identity_sha256": None,
    }
    key = hmac.new(credential.encode("utf-8"), KEY_CONTEXT, hashlib.sha256).digest()
    message = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**claims, "mac": hmac.new(key, message, hashlib.sha256).hexdigest()}
