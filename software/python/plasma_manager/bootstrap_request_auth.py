"""Manager-side client of PPU Bootstrap mutual request authentication.

Wire contract: ``plasma.ppu.bootstrap-request-auth.v1``. The single PPU-side
verifier is ``scripts/ppu_bootstrap_request_auth.py``; this client must produce
byte-identical request headers and accept exactly the PPU's response MACs
(enforced by a cross-implementation Host test). The paired credential is never
transmitted: the Manager MACs each request under a single-use PPU nonce and
accepts a response only when the PPU MACed it under the same credential.

Transport proof only. Not a license, login or manufacturer approval; the Owner
Operation Authorization, SHA/Target/ABI and all PPU safety checks still apply.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

SCHEMA = "plasma.ppu.bootstrap-request-auth.v1"
AUTH_SCHEME = "PLASMA-PPU-HMAC-V1"
RESPONSE_HEADER = "X-Plasma-PPU-Response-Auth"
CHALLENGE_PATH = "/v1/auth/challenge"

_DEVICE_RE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")
_HEX32_RE = re.compile(r"[0-9a-f]{32}\Z")
_RESPONSE_RE = re.compile(r"v1 mac=([0-9a-f]{64})\Z")
_METHODS = frozenset({"GET", "POST"})


class BootstrapRequestAuthError(ValueError):
    """Authentication failed; never carries credential material."""


@dataclass(frozen=True)
class RequestContext:
    method: str
    path: str
    device_id: str
    nonce: str
    cnonce: str
    mac: str


def _key(credential: str, purpose: str) -> bytes:
    if (type(credential) is not str or not 32 <= len(credential) <= 256
            or any(ch.isspace() for ch in credential)):
        raise BootstrapRequestAuthError("request authentication credential is invalid")
    return hmac.new(credential.encode("utf-8"), f"{SCHEMA}/{purpose}".encode("ascii"),
                    hashlib.sha256).digest()


def _mac(key: bytes, message: bytes) -> str:
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def valid_nonce(value: object) -> bool:
    return type(value) is str and _HEX32_RE.fullmatch(value) is not None


def sign_request(
    *, credential: str, method: str, path: str, body: bytes | None,
    device_id: str, nonce: str, cnonce: str | None = None,
) -> tuple[str, RequestContext]:
    if (type(method) is not str or method not in _METHODS or type(path) is not str
            or not path.startswith(("/v1/", "/api/")) or len(path) > 512
            or any(ch.isspace() or ord(ch) < 33 or ord(ch) > 126 for ch in path)):
        raise BootstrapRequestAuthError("request authentication target is invalid")
    if type(device_id) is not str or not _DEVICE_RE.fullmatch(device_id):
        raise BootstrapRequestAuthError("request authentication device identity is invalid")
    if not valid_nonce(nonce):
        raise BootstrapRequestAuthError("request authentication nonce is invalid")
    cnonce = secrets.token_hex(16) if cnonce is None else cnonce
    if not valid_nonce(cnonce):
        raise BootstrapRequestAuthError("request authentication client nonce is invalid")
    message = "\n".join((SCHEMA, "request", method, path, device_id, nonce, cnonce,
                         hashlib.sha256(body or b"").hexdigest())).encode("ascii")
    mac = _mac(_key(credential, "request-key"), message)
    header = f"{AUTH_SCHEME} device_id={device_id},nonce={nonce},cnonce={cnonce},mac={mac}"
    return header, RequestContext(method, path, device_id, nonce, cnonce, mac)


def verify_response(
    *, credential: str, context: RequestContext, status: int, body: bytes, header: object,
) -> None:
    match = _RESPONSE_RE.fullmatch(header) if type(header) is str else None
    if match is None or type(status) is not int or not 100 <= status <= 599:
        raise BootstrapRequestAuthError("PPU response authentication is missing or malformed")
    message = "\n".join((SCHEMA, "response", context.method, context.path, context.device_id,
                         context.nonce, context.cnonce, context.mac, str(status),
                         hashlib.sha256(body).hexdigest())).encode("ascii")
    expected = _mac(_key(credential, "response-key"), message)
    if not hmac.compare_digest(match.group(1), expected):
        raise BootstrapRequestAuthError("PPU response authentication failed")
