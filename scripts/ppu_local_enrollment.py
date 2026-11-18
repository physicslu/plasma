#!/usr/bin/env python3
"""Wire protocol of PLASMA PPU local enrollment (``plasma.ppu.local-enrollment.v1``).

Shared, stdlib-only (PYNQ Python 3.10) definitions used by the PPU enrollment
engine (``scripts/ppu_controller.py``) and the Manager enrollment client. The
Manager copy ``software/python/plasma_manager/local_enrollment.py`` is
byte-identical (enforced by a Host test).

Three arming entries feed ONE enrollment engine and ONE claim exchange:

* ``ps-gpio-button`` (prototype production entry): a Control Station first
  posts a button request carrying an ephemeral X25519 public key; a long press
  of the PPU-local button binds the window to exactly that single request.
  The ticket key is derived from the X25519 shared secret, so only the
  requesting station can prove the claim or unwrap the credential.
* ``engineering-cli`` (controlled development entry): root on the PPU (SSH or
  local console) under a root-owned Engineering Mode policy prints a one-time
  ticket.
* ``sd-boot-partition`` (rescue): a ticket file consumed at boot.

The credential is a device-specific machine secret, not a license or user
account. Integrity and proof only: no transport confidentiality is claimed for
the remaining fields; the credential itself is only sent wrapped.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Mapping

SCHEMA = "plasma.ppu.local-enrollment.v1"
TICKET_SCHEMA = "plasma.ppu.enrollment-ticket.v1"
TICKET_FILE = "plasma-enroll.json"
MAX_TICKET_FILE_BYTES = 4096
ENROLLMENT_WINDOW_S = 900
BUTTON_REQUEST_WINDOW_S = 120
MAX_CLAIM_FAILURES = 5
LEDGER_CAPACITY = 4096
MAX_LABEL_CHARS = 64

SOURCE_BUTTON = "ps-gpio-button"
SOURCE_ENGINEERING = "engineering-cli"
SOURCE_SD = "sd-boot-partition"
SOURCES = (SOURCE_BUTTON, SOURCE_ENGINEERING, SOURCE_SD)

MODE_NORMAL = "NORMAL"
MODE_RECOVERY_ONLY = "RECOVERY_ONLY"

HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
HEX32_RE = re.compile(r"[0-9a-f]{32}\Z")
DEVICE_RE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")


class EnrollmentProtocolError(ValueError):
    """Malformed enrollment material; never carries secrets."""


# --- tickets (engineering CLI and SD rescue) ----------------------------------

def make_ticket_file(ticket: str | None = None, note: str = "") -> bytes:
    ticket = ticket or secrets.token_hex(32)
    return json.dumps({"schema": TICKET_SCHEMA, "ticket": ticket, "note": note[:128]},
                      sort_keys=True).encode()


def parse_ticket_file(raw: bytes) -> str:
    """Strict SD ticket parser; any deviation is invalid (no partial accept)."""
    if type(raw) is not bytes or len(raw) > MAX_TICKET_FILE_BYTES:
        raise EnrollmentProtocolError("ticket file is invalid")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise EnrollmentProtocolError("ticket file is invalid") from exc
    if (type(doc) is not dict or doc.get("schema") != TICKET_SCHEMA
            or type(doc.get("ticket")) is not str or not HEX64_RE.fullmatch(doc["ticket"])
            or set(doc) - {"schema", "ticket", "note"}
            or ("note" in doc and (type(doc["note"]) is not str or len(doc["note"]) > 128))):
        raise EnrollmentProtocolError("ticket file is invalid")
    return doc["ticket"]


def valid_ticket(ticket: object) -> str:
    if type(ticket) is not str or not HEX64_RE.fullmatch(ticket):
        raise EnrollmentProtocolError("enrollment ticket must be 64 lowercase hex characters")
    return ticket


def ticket_id(ticket: str) -> str:
    return hashlib.sha256(("ticket-id\n" + valid_ticket(ticket)).encode()).hexdigest()[:32]


def ticket_key(ticket: str) -> bytes:
    return hmac.new(bytes.fromhex(valid_ticket(ticket)), f"{SCHEMA}/ticket-key".encode(),
                    hashlib.sha256).digest()


# --- X25519 (RFC 7748), pure Python for the PS-GPIO button entry --------------
# Ephemeral keys only (one per enrollment). Python big-int arithmetic is not
# constant time; the exposure is one short window per physical button press.

_P = 2 ** 255 - 19
_A24 = 121665


def _clamp(scalar: bytes) -> int:
    if type(scalar) is not bytes or len(scalar) != 32:
        raise EnrollmentProtocolError("X25519 scalar must be 32 bytes")
    value = bytearray(scalar)
    value[0] &= 248
    value[31] &= 127
    value[31] |= 64
    return int.from_bytes(value, "little")


def x25519(scalar: bytes, u_coordinate: bytes) -> bytes:
    if type(u_coordinate) is not bytes or len(u_coordinate) != 32:
        raise EnrollmentProtocolError("X25519 point must be 32 bytes")
    k = _clamp(scalar)
    u = bytearray(u_coordinate)
    u[31] &= 127
    x1 = int.from_bytes(u, "little") % _P
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        bit = (k >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a = (x2 + z2) % _P
        aa = a * a % _P
        b = (x2 - z2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x3 + z3) % _P
        d = (x3 - z3) % _P
        da = d * a % _P
        cb = c * b % _P
        x3 = (da + cb) * (da + cb) % _P
        z3 = x1 * (da - cb) * (da - cb) % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def x25519_keypair() -> tuple[bytes, str]:
    private = secrets.token_bytes(32)
    return private, x25519(private, (9).to_bytes(32, "little")).hex()


def valid_public_key(value: object) -> str:
    if type(value) is not str or not HEX64_RE.fullmatch(value):
        raise EnrollmentProtocolError("X25519 public key must be 64 lowercase hex characters")
    return value


def button_key(private: bytes, *, peer_public: str, device_id: str, request_id: str,
               controller_public: str, ppu_public: str) -> bytes:
    """Window key of a button enrollment, bound to the full transcript."""
    shared = x25519(private, bytes.fromhex(valid_public_key(peer_public)))
    if not any(shared):
        raise EnrollmentProtocolError("X25519 shared secret is degenerate")
    info = "\n".join((SCHEMA, "button-key", device_id, request_id, controller_public,
                      ppu_public)).encode()
    return hmac.new(shared, info, hashlib.sha256).digest()


# --- claim proof and credential wrap -----------------------------------------

def claim_mac(key: bytes, *, device_id: str, enrollment_id: str, nonce: str,
              controller_nonce: str, current_generation: int, label: str) -> str:
    message = "\n".join((SCHEMA, "claim", device_id, enrollment_id, nonce, controller_nonce,
                         str(current_generation), label)).encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _keystream(key: bytes, info: bytes, length: int) -> bytes:
    out, counter = b"", 0
    while len(out) < length:
        out += hmac.new(key, info + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def _wrap_info(nonce: str, controller_nonce: str, generation: int) -> bytes:
    return f"{SCHEMA}/wrap\n{nonce}\n{controller_nonce}\n{generation}\n".encode()


def wrap_credential(key: bytes, *, nonce: str, controller_nonce: str, generation: int,
                    credential: str) -> dict[str, str]:
    """HMAC-SHA256 CTR keystream + encrypt-then-MAC (stdlib only; PYNQ-safe)."""
    info = _wrap_info(nonce, controller_nonce, generation)
    plain = credential.encode()
    cipher = bytes(a ^ b for a, b in zip(plain, _keystream(key, info, len(plain))))
    tag = hmac.new(key, info + cipher, hashlib.sha256).hexdigest()
    return {"ciphertext": cipher.hex(), "tag": tag}


def unwrap_credential(key: bytes, *, nonce: str, controller_nonce: str, generation: int,
                      wrapped: Mapping[str, Any]) -> str:
    info = _wrap_info(nonce, controller_nonce, generation)
    try:
        cipher = bytes.fromhex(wrapped["ciphertext"])
        tag = wrapped["tag"]
    except (KeyError, TypeError, ValueError) as exc:
        raise EnrollmentProtocolError("wrapped credential is malformed") from exc
    if type(tag) is not str or not hmac.compare_digest(
            hmac.new(key, info + cipher, hashlib.sha256).hexdigest(), tag):
        raise EnrollmentProtocolError("wrapped credential tag invalid")
    return bytes(a ^ b for a, b in zip(cipher, _keystream(key, info, len(cipher)))).decode()


def claim_request(key: bytes, challenge: Mapping[str, Any], *, controller_nonce: str,
                  label: str) -> dict[str, Any]:
    """Client side: the claim body for a challenge under the window key."""
    if type(label) is not str or len(label) > MAX_LABEL_CHARS:
        raise EnrollmentProtocolError("controller label is invalid")
    return {
        "enrollment_id": challenge["enrollment_id"], "nonce": challenge["nonce"],
        "controller_nonce": controller_nonce, "label": label,
        "mac": claim_mac(key, device_id=challenge["device_id"],
                         enrollment_id=challenge["enrollment_id"], nonce=challenge["nonce"],
                         controller_nonce=controller_nonce,
                         current_generation=challenge["current_generation"], label=label),
    }
