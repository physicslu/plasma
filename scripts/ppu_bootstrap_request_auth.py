#!/usr/bin/env python3
"""Mutual request authentication for the PPU Bootstrap service.

Wire contract: ``plasma.ppu.bootstrap-request-auth.v1``. Replaces the former
``Authorization: Bearer <credential>`` scheme (Local Owner Mode LOM-P2A-1):

* The paired device credential is **never transmitted**. A client proves
  possession with an HMAC over the exact request and a single-use, short-lived
  PPU-issued nonce; a spoofed endpoint therefore cannot harvest the credential.
* The PPU proves possession of the same credential by MACing the exact
  response (status + body SHA256) bound to that request, so a client accepts
  device status/receipts only from the paired device.
* ``device_id`` is inside the signed request; the PPU rejects a request
  addressed to a different device identity.

This is a machine-to-machine transport proof. It is NOT a license, user
login, manufacturer approval or a replacement for the Owner Operation
Authorization (``ppu_owner_authorization.py``), SHA/Target/ABI checks, journals,
Site leases, SAFE_OFF, SEALED or OUTCOME_UNKNOWN recovery. The credential is
the current controller credential of ``ppu_controller.py`` (LOM-P2A-2); the same
proof binds Gateway (:18080) writes through the controller admission service (G13).

The Manager-side client mirror is
``software/python/plasma_manager/bootstrap_request_auth.py``; a cross-
implementation Host test enforces byte-identical headers and MACs.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

SCHEMA = "plasma.ppu.bootstrap-request-auth.v1"
AUTH_SCHEME = "PLASMA-PPU-HMAC-V1"
RESPONSE_HEADER = "X-Plasma-PPU-Response-Auth"
CHALLENGE_PATH = "/v1/auth/challenge"
NONCE_TTL_S = 60
MAX_OUTSTANDING_NONCES = 256

_DEVICE = r"ppu-device-[0-9a-f]{16,64}"
_DEVICE_RE = re.compile(_DEVICE + r"\Z")
_HEX32_RE = re.compile(r"[0-9a-f]{32}\Z")
_HEADER_RE = re.compile(
    AUTH_SCHEME
    + r" device_id=(" + _DEVICE + r"),nonce=([0-9a-f]{32}),cnonce=([0-9a-f]{32}),mac=([0-9a-f]{64})\Z"
)
_RESPONSE_RE = re.compile(r"v1 mac=([0-9a-f]{64})\Z")
_METHODS = frozenset({"GET", "POST"})
# Bootstrap (:18081) ``/v1/`` and Gateway (:18080) ``/api/`` targets (LOM-P2A-2 G13).
_TARGET_PREFIXES = ("/v1/", "/api/")
_HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")


class RequestAuthError(ValueError):
    """Authentication failed; never carries credential material."""


@dataclass(frozen=True)
class RequestContext:
    method: str
    path: str
    device_id: str
    nonce: str
    cnonce: str
    mac: str


def _valid_credential(credential: object) -> bytes:
    if (type(credential) is not str or not 32 <= len(credential) <= 256
            or any(ch.isspace() for ch in credential)):
        raise RequestAuthError("request authentication credential is invalid")
    return credential.encode("utf-8")


def _key(credential: str, purpose: str) -> bytes:
    return hmac.new(_valid_credential(credential), f"{SCHEMA}/{purpose}".encode("ascii"),
                    hashlib.sha256).digest()


def _check_target(method: object, path: object) -> None:
    if (type(method) is not str or method not in _METHODS or type(path) is not str
            or not path.startswith(_TARGET_PREFIXES) or len(path) > 512
            or any(ch.isspace() or ord(ch) < 33 or ord(ch) > 126 for ch in path)):
        raise RequestAuthError("request authentication target is invalid")


def _request_message(context: RequestContext, body_sha256: str) -> bytes:
    return "\n".join((SCHEMA, "request", context.method, context.path, context.device_id,
                      context.nonce, context.cnonce, body_sha256)).encode("ascii")


def _response_message(context: RequestContext, status: int, body_sha256: str) -> bytes:
    return "\n".join((SCHEMA, "response", context.method, context.path, context.device_id,
                      context.nonce, context.cnonce, context.mac, str(status),
                      body_sha256)).encode("ascii")


def _mac(key: bytes, message: bytes) -> str:
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def sign_request(
    *, credential: str, method: str, path: str, body: bytes | None,
    device_id: str, nonce: str, cnonce: str | None = None, body_sha256: str | None = None,
) -> tuple[str, RequestContext]:
    """Client side: the Authorization header value and its response context.

    ``body_sha256`` replaces ``body`` when only the digest is available (the
    Gateway forwards a digest to the PPU controller admission service).
    """
    _check_target(method, path)
    if body_sha256 is None:
        body_sha256 = hashlib.sha256(body or b"").hexdigest()
    elif body is not None or type(body_sha256) is not str or not _HEX64_RE.fullmatch(body_sha256):
        raise RequestAuthError("request authentication body digest is invalid")
    if type(device_id) is not str or not _DEVICE_RE.fullmatch(device_id):
        raise RequestAuthError("request authentication device identity is invalid")
    if type(nonce) is not str or not _HEX32_RE.fullmatch(nonce):
        raise RequestAuthError("request authentication nonce is invalid")
    cnonce = secrets.token_hex(16) if cnonce is None else cnonce
    if type(cnonce) is not str or not _HEX32_RE.fullmatch(cnonce):
        raise RequestAuthError("request authentication client nonce is invalid")
    unsigned = RequestContext(method, path, device_id, nonce, cnonce, "")
    mac = _mac(_key(credential, "request-key"), _request_message(unsigned, body_sha256))
    context = RequestContext(method, path, device_id, nonce, cnonce, mac)
    header = f"{AUTH_SCHEME} device_id={device_id},nonce={nonce},cnonce={cnonce},mac={mac}"
    return header, context


def sign_response(*, credential: str, context: RequestContext, status: int, body: bytes) -> str:
    """PPU side: response header value proving possession of the credential."""
    if type(status) is not int or not 100 <= status <= 599:
        raise RequestAuthError("response status is invalid")
    mac = _mac(_key(credential, "response-key"),
               _response_message(context, status, hashlib.sha256(body).hexdigest()))
    return f"v1 mac={mac}"


def verify_response(
    *, credential: str, context: RequestContext, status: int, body: bytes,
    header: object,
) -> None:
    """Client side: accept a response only when the paired PPU MACed it."""
    match = _RESPONSE_RE.fullmatch(header) if type(header) is str else None
    if match is None:
        raise RequestAuthError("PPU response authentication is missing or malformed")
    expected = sign_response(credential=credential, context=context, status=status, body=body)
    if not hmac.compare_digest(match.group(0), expected):
        raise RequestAuthError("PPU response authentication failed")


class NonceRegistry:
    """Bounded, single-use, monotonic-deadline PPU challenges (memory only).

    A Bootstrap restart drops all outstanding nonces; clients fetch a new one.
    Flooding the challenge endpoint can only evict nonces (bounded DoS on the
    controlled link), never authenticate a request.
    """

    def __init__(self, *, ttl_s: float = NONCE_TTL_S, capacity: int = MAX_OUTSTANDING_NONCES,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s, self._capacity, self._clock = ttl_s, capacity, clock
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self) -> str:
        nonce = secrets.token_hex(16)
        with self._lock:
            now = self._clock()
            for key in [key for key, deadline in self._nonces.items() if deadline <= now]:
                del self._nonces[key]
            while len(self._nonces) >= self._capacity:
                del self._nonces[next(iter(self._nonces))]
            self._nonces[nonce] = now + self._ttl_s
        return nonce

    def consume(self, nonce: str) -> bool:
        with self._lock:
            deadline = self._nonces.pop(nonce, None)
            return deadline is not None and self._clock() < deadline


@dataclass(frozen=True)
class AdmittedHeader:
    device_id: str
    nonce: str
    cnonce: str
    mac: str


def admit_request_header(*, header: object, device_id: str, nonces: NonceRegistry) -> AdmittedHeader:
    """PPU side, before reading any body: syntax, this device, one fresh nonce.

    The nonce is consumed here, before the MAC check, so one challenge never
    admits a second attempt (no online MAC guessing per nonce).
    """
    match = _HEADER_RE.fullmatch(header) if type(header) is str else None
    if match is None:
        raise RequestAuthError("request authentication header is missing or malformed")
    admitted = AdmittedHeader(*match.groups())
    fresh = nonces.consume(admitted.nonce)
    if admitted.device_id != device_id or not fresh:
        raise RequestAuthError("request authentication is not for this device or nonce")
    return admitted


def verify_request(
    *, credential: str, admitted: AdmittedHeader, method: str, path: str, body: bytes | None,
    body_sha256: str | None = None,
) -> RequestContext:
    """PPU side: the exact method/path/body (or body digest) under the admitted nonce."""
    _expected_header, context = sign_request(
        credential=credential, method=method, path=path, body=body,
        device_id=admitted.device_id, nonce=admitted.nonce, cnonce=admitted.cnonce,
        body_sha256=body_sha256,
    )
    if not hmac.compare_digest(context.mac, admitted.mac):
        raise RequestAuthError("request authentication failed")
    return context
